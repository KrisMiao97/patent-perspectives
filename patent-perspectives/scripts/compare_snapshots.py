#!/usr/bin/env python3
"""Read-only research snapshots and conservative, source-bound delta JSON.

Snapshot capture times are not acquisition times. No network or model calls.
The output belongs beside the single analysis/continuation note, not in the reader.
"""
from __future__ import annotations

import argparse
import collections
import datetime as dt
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sqlite3
import tempfile

KIND = "patent-perspectives-research-snapshot"
SCHEMA = 1


class SnapshotError(ValueError):
    pass


def require(ok, message):
    if not ok:
        raise SnapshotError(message)


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def digest(value):
    return hashlib.sha256(canonical(value).encode("utf-8")).hexdigest()


def date(value):
    if not isinstance(value, str) or len(value) != 10:
        return None
    try:
        return dt.date.fromisoformat(value).isoformat()
    except (ValueError, TypeError):
        return None


def interval(value):
    """Keep date-only evidence as an interval; do not invent a precise time."""
    if not isinstance(value, str):
        return None
    try:
        if len(value) == 10:
            start = dt.datetime.combine(dt.date.fromisoformat(value), dt.time(), dt.timezone.utc)
            return start.timestamp(), (start + dt.timedelta(days=1)).timestamp()
        stamp = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
        if stamp.tzinfo is None:
            return None
        return stamp.timestamp(), stamp.timestamp()
    except ValueError:
        return None


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def write_new(path, data):
    """Publish a complete JSON file without replacing an existing checkpoint."""
    out = Path(path).resolve()
    require(not out.exists(), "Output already exists; preserve the earlier checkpoint")
    out.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".snapshot-", suffix=".tmp", dir=out.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as stream:
            json.dump(data, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        # Windows rename refuses an existing destination and avoids hard-link privileges.
        # POSIX rename would replace a checkpoint, so use an exclusive hard link there.
        if os.name == "nt":
            os.rename(temporary, out)
        else:
            os.link(temporary, out)
    finally:
        Path(temporary).unlink(missing_ok=True)


def load_engine():
    path = Path(__file__).with_name("patent_perspectives.py")
    spec = importlib.util.spec_from_file_location("pp_snapshot_engine", path)
    engine = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(engine)
    return engine


def at(value, path):
    require(isinstance(path, list), "Source JSON locator must be an array")
    for key in path:
        try:
            value = value[key]
        except (KeyError, IndexError, TypeError) as error:
            raise SnapshotError("Source JSON locator does not exist") from error
    return value


def collection_observations(pages, manifest_path, engine):
    """Bind optional acquisition receipts to every saved ordinary query page."""
    bindings = {}
    if manifest_path:
        manifest_path = Path(manifest_path).resolve()
        manifest = read_json(manifest_path)
        require(isinstance(manifest, dict) and isinstance(manifest.get("pages"), list), "Observation manifest needs pages")
        page_index = {(p["query_id"], p["offset"]): p for p in pages}
        for entry in manifest["pages"]:
            key = (entry["query_id"], entry["offset"])
            require(key in page_index and key not in bindings, "Observation page is absent or duplicated")
            relative = Path(entry["file"])
            path = (manifest_path.parent / relative).resolve()
            require(not relative.is_absolute() and path.is_relative_to(manifest_path.parent) and path.is_file(), "Observation source must be inside the manifest directory")
            raw = path.read_bytes()
            require(hashlib.sha256(raw).hexdigest() == entry.get("sha256"), "Observation receipt hash mismatch")
            source = json.loads(raw.decode("utf-8-sig"))
            response = engine.sanitized(at(source, entry["response_path"]))
            require(response == page_index[key]["raw"], "Observation receipt response differs from retained query page")
            observed_at = at(source, entry["observed_at_path"])
            require(interval(observed_at) is not None, "Acquisition time must be an ISO date or timezone-aware timestamp")
            bindings[key] = {"observed_at": observed_at, "receipt_sha256": entry["sha256"]}
    result = []
    for page in pages:
        key = (page["query_id"], page["offset"])
        binding = bindings.get(key, {})
        raw = page["raw"]
        stamp = binding.get("observed_at")
        if not stamp and isinstance(raw, dict):
            stamp = raw.get("acquired_at") or raw.get("retrieved_at")
        # Timestamps generated by snapshot/export/packaging are deliberately ignored.
        result.append({"query_id": key[0], "offset": key[1], "raw_sha256": digest(raw),
                       "observed_at": stamp if interval(stamp) else None,
                       "receipt_sha256": binding.get("receipt_sha256")})
    return result


def snapshot(db, observation_manifest=None):
    path = Path(db).resolve()
    require(path.is_file(), "Snapshot database does not exist")
    engine = load_engine()
    # One read transaction sees a consistent committed SQLite snapshot, including WAL.
    connection = sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    try:
        connection.execute("PRAGMA query_only=ON")
        connection.execute("BEGIN")
        run = engine.run_info(connection)
        report = engine.validate_run(connection)
        states = engine.population_state(connection)
        tables = {r[0] for r in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}

        def rows(table):
            return [json.loads(row[0]) for row in connection.execute("SELECT data FROM " + table)] if table in tables else []

        applications = {}
        for item in rows("applications"):
            fields = ("id", "application_number", "authority", "filing_date", "patent_type", "title", "original_assignees", "current_assignees")
            applications[item["id"]] = {**{k: item.get(k) for k in fields}, "population_status": states.get(item["id"], "verification_only")}
        publications = {}
        for row in connection.execute("SELECT id,application_id,data FROM publications ORDER BY id"):
            item = json.loads(row["data"])
            fields = ("publication_date", "filing_date", "source_provider", "patent_type", "authority", "title")
            publications[row["id"]] = {"id": row["id"], "application_id": row["application_id"], **{k: item.get(k) for k in fields}}
        query_rows = list(connection.execute("SELECT * FROM queries ORDER BY id"))
        ordinary = {r["id"] for r in query_rows if not json.loads(r["request"]).get("verification_only", False)}
        pages = [{"query_id": r["query_id"], "offset": r["offset"], "raw": json.loads(r["raw"])}
                 for r in connection.execute("SELECT query_id,offset,raw FROM pages ORDER BY query_id,offset") if r["query_id"] in ordinary]
        observations = collection_observations(pages, observation_manifest, engine)
        # Completion of technical reading is independent of source-directory reconciliation.
        blocking = {"scope_unconfirmed", "scope_changed", "no_entities", "query_plan_unconfirmed", "query_set_invalid", "required_query_set_missing", "query_set_contract_changed", "required_query_set_incomplete", "missing_query_set", "query_set_incomplete", "missing_query", "query_incomplete", "no_queries", "query_count_mismatch", "population_review_pending", "analysis_window_pending", "latest_selection_count_mismatch"}
        directory_errors = [e for e in report["errors"] if e["code"] in blocking or e["code"].startswith("registration_")]
        entities = [{k: x.get(k) for k in ("id", "name", "relation", "confirmed", "control_from", "control_through")} for x in rows("entities")]
        sources = sorted({x["source_provider"] for x in publications.values() if x.get("source_provider")})
        plan = engine.get_meta(connection, "query_plan_contract", {})
        basis = {"company": run["company"], "entities_sha256": digest(sorted(entities, key=lambda x: x["id"])),
                 "scope_sha256": digest(run["scope"]), "query_plan_sha256": digest(plan), "source_providers": sources,
                 "count_unit": "retained_publication_with_application_id", "registration_mapping_sha256": digest(sorted(rows("registration_members"), key=lambda x: x["id"]))}
        legal = []
        for x in rows("auxiliary_records"):
            if x.get("kind") == "legal_status":
                legal.append({"id": x["id"], "publication_number": x["publication_number"], "application_id": x["application_id"],
                              "source_provider": x.get("source_provider"), "observed_at": x.get("acquired_at"),
                              "status": x.get("normalized", {}).get("status", "unknown"), "source_sha256": x.get("artifact_sha256"),
                              "conflict": x.get("normalized", {}).get("conflict_or_unrecognized", False)})
        objects = {}
        for table, key in (("documents", "id"), ("evidence", "id"), ("analyses", "application_id"), ("insights", "id"), ("relations", "id")):
            entries = {}
            for row in connection.execute("SELECT * FROM " + table):
                data = json.loads(row["data"])
                application_ids = [row["application_id"]] if "application_id" in row.keys() else data.get("patent_ids", [])
                if table == "relations":
                    application_ids = sorted(set(application_ids) | {data[k] for k in ("source", "target") if data.get(k) in applications})
                entries[str(row[key])] = {"sha256": digest(dict(row)), "application_ids": application_ids,
                                         "evidence_ids": data.get("evidence_ids", [])}
            objects[table] = entries
        content = {"schema_version": SCHEMA, "kind": KIND, "run": {"run_id": run["run_id"], "company": run["company"], "publication_cutoff": run["as_of_date"]},
                   "comparison_basis": basis, "directory": {"complete": bool(ordinary) and not directory_errors,
                   "validation_error_codes": sorted({x["code"] for x in directory_errors}), "query_ids": sorted(ordinary), "page_observations": observations},
                   "applications": applications, "publications": publications, "legal_observations": sorted(legal, key=lambda x: x["id"]), "objects": objects}
        content["data_sha256"] = digest(content)
        content["snapshot_id"] = "snapshot-" + content["data_sha256"][:24]
        content["captured_at"] = dt.datetime.now(dt.timezone.utc).isoformat()
        return content
    finally:
        connection.close()


def validate_snapshot(value):
    require(isinstance(value, dict) and value.get("kind") == KIND and value.get("schema_version") == SCHEMA, "Expected a research snapshot, not an HTML/report/package manifest")
    material = {k: v for k, v in value.items() if k not in ("data_sha256", "snapshot_id", "captured_at")}
    require(digest(material) == value.get("data_sha256"), "Snapshot content hash mismatch")
    require(value.get("snapshot_id") == "snapshot-" + value["data_sha256"][:24], "Snapshot identifier does not match its content")
    require(date(value.get("run", {}).get("publication_cutoff")), "Snapshot cutoff is invalid")
    for key in ("comparison_basis", "directory", "applications", "publications", "objects"):
        require(isinstance(value.get(key), dict), "Snapshot field is invalid: " + key)
    require(isinstance(value.get("legal_observations"), list), "Snapshot legal observations are invalid")


def search_window(value):
    pages = value["directory"]["page_observations"]
    times = [interval(p.get("observed_at")) for p in pages]
    if not times or any(x is None for x in times):
        return None
    return min(x[0] for x in times), max(x[1] for x in times)


def latest_legal(value):
    groups = collections.defaultdict(list)
    for x in value["legal_observations"]:
        if interval(x.get("observed_at")):
            groups[x["publication_number"]].append(x)
    result = {}
    for pn, items in groups.items():
        latest_start = max(interval(x["observed_at"])[0] for x in items)
        selected = [x for x in items if interval(x["observed_at"])[1] >= latest_start]
        statuses = {x["status"] for x in selected}
        providers = {x.get("source_provider") for x in selected}
        result[pn] = {"status": next(iter(statuses)) if len(statuses) == 1 and not any(x.get("conflict") for x in selected) else "unknown",
                      "providers": sorted(str(p) for p in providers), "observation_ids": sorted(x["id"] for x in selected),
                      "observed_at": sorted({x["observed_at"] for x in selected}), "application_id": selected[0]["application_id"],
                      "window": [min(interval(x["observed_at"])[0] for x in selected), max(interval(x["observed_at"])[1] for x in selected)]}
    return result


def compare(before, after):
    validate_snapshot(before)
    validate_snapshot(after)
    mismatches = [k for k in sorted(set(before["comparison_basis"]) | set(after["comparison_basis"])) if before["comparison_basis"].get(k) != after["comparison_basis"].get(k)]
    old_cutoff, cutoff = before["run"]["publication_cutoff"], after["run"]["publication_cutoff"]
    if cutoff < old_cutoff:
        mismatches.append("publication_cutoff_reversed")
    compatible = not mismatches and bool(after["comparison_basis"].get("source_providers"))
    old_search, new_search = search_window(before), search_window(after)
    search_reobserved = bool(old_search and new_search and new_search[0] > old_search[1])
    complete = before["directory"]["complete"] and after["directory"]["complete"]
    search_comparable = bool(compatible and complete and search_reobserved)
    changes = []

    def add(category, obj, identity, old=None, new=None, reason=None):
        item = {"category": category, "object_type": obj, "id": identity, "before": old, "after": new}
        if reason:
            item["reason"] = reason
        changes.append(item)

    old_pubs, pubs = before["publications"], after["publications"]
    for pn in sorted(set(pubs) - set(old_pubs)):
        record = pubs[pn]
        pub_date = date(record.get("publication_date"))
        included = after["applications"].get(record["application_id"], {}).get("population_status") == "included"
        if not compatible:
            category, reason = "scope_or_source_membership_change", "Scope/source basis changed; not a business increment"
        elif search_comparable and included and pub_date and old_cutoff < pub_date <= cutoff:
            category, reason = "newly_published_document", "Publication date is inside the two cutoff dates and both source directories reconcile"
        elif search_comparable and included and pub_date and pub_date <= old_cutoff:
            category, reason = "newly_discovered_old_publication", "This older publication was absent from the earlier retained directory"
        else:
            category, reason = "added_record_pending_review", "Missing independent search observation, coverage, date or included-entity evidence"
        add(category, "publication", pn, new=record, reason=reason)
    for pn in sorted(set(old_pubs) - set(pubs)):
        add("removed_record_pending_review", "publication", pn, old=old_pubs[pn], reason="Absence from a later snapshot is not a loss of legal rights")
    for table in ("applications", "publications"):
        for identity in sorted(set(before[table]) & set(after[table])):
            a, b = before[table][identity], after[table][identity]
            changed = {key: {"before": a.get(key), "after": b.get(key)} for key in sorted(set(a) | set(b)) if a.get(key) != b.get(key)}
            if changed:
                category = "scope_membership_change" if "population_status" in changed else "record_correction_or_enrichment_review"
                add(category, table, identity, new=changed, reason="Field differences require source review; not automatically a real-world event")
    old_legal, legal = latest_legal(before), latest_legal(after)
    compared_legal = []
    for pn in sorted(set(old_legal) | set(legal)):
        a, b = old_legal.get(pn), legal.get(pn)
        if a == b:
            continue
        if a and b and compatible and a["providers"] == b["providers"] and b["window"][0] > a["window"][1]:
            compared_legal.append(pn)
            if a["status"] != b["status"]:
                known = a["status"] not in (None, "", "unknown", "未确认") and b["status"] not in (None, "", "unknown", "未确认")
                add("legal_status_observation_changed" if known else "legal_status_evidence_changed", "publication", pn, a, b,
                    "Acquisition-time observations differ; the legal event date is not inferred")
        else:
            add("legal_observation_pending_review", "publication", pn, a, b, "No comparable later observation for this publication")
    affected_apps, affected_evidence = set(), set()
    for table in ("documents", "evidence", "analyses", "insights", "relations"):
        aa, bb = before["objects"].get(table, {}), after["objects"].get(table, {})
        for identity in sorted(set(aa) | set(bb)):
            if aa.get(identity) == bb.get(identity):
                continue
            add("source_or_analysis_material_changed", table, identity, aa.get(identity), bb.get(identity), "Review whether this is a correction, added evidence or changed interpretation")
            for item in (aa.get(identity), bb.get(identity)):
                if item:
                    affected_apps.update(item.get("application_ids", []))
                    affected_evidence.update(item.get("evidence_ids", []))
            if table == "evidence":
                affected_evidence.add(identity)
    for item in changes:
        # Added/removed and legal changes use singular publication; common-table
        # field corrections retain the table name. Both carry the same PN key.
        pn = item["id"] if item["object_type"] in ("publication", "publications") else None
        if pn:
            # A corrected application association affects both the old and new owner.
            for record in (old_pubs.get(pn), pubs.get(pn)):
                if record:
                    affected_apps.add(record["application_id"])
        if item["object_type"] == "applications":
            affected_apps.add(item["id"])
    for source in (before, after):
        for identity in affected_evidence:
            affected_apps.update(source["objects"].get("evidence", {}).get(identity, {}).get("application_ids", []))
    insight_ids = set()
    for source in (before, after):
        for identity, item in source["objects"].get("insights", {}).items():
            if set(item.get("application_ids", [])) & affected_apps or set(item.get("evidence_ids", [])) & affected_evidence:
                insight_ids.add(identity)
    counts = collections.Counter(x["category"] for x in changes)
    return {"schema_version": SCHEMA, "kind": "patent-perspectives-research-delta", "before_snapshot_id": before["snapshot_id"], "after_snapshot_id": after["snapshot_id"],
            "before_data_sha256": before["data_sha256"], "after_data_sha256": after["data_sha256"],
            "comparability": {"same_data": before["data_sha256"] == after["data_sha256"], "basis_matches": compatible, "mismatched_fields": mismatches,
                              "both_directories_reconciled": bool(complete), "independent_search_observations": search_reobserved,
                              "publication_changes_computable": search_comparable, "legal_publications_reobserved": compared_legal},
            "counts": {"newly_published_documents": counts["newly_published_document"] if search_comparable else None,
                       "newly_discovered_old_publications": counts["newly_discovered_old_publication"] if search_comparable else None,
                       "legal_status_observation_changes": counts["legal_status_observation_changed"] if compared_legal else None,
                       "retained_record_and_material_differences": len(changes)},
            "changes": changes, "review_candidates": {"application_ids": sorted(affected_apps), "evidence_ids": sorted(affected_evidence), "insight_ids": sorted(insight_ids)},
            "limitations": ["Snapshot capture and file modification times are not acquisition times.",
                            "Counts describe retained publications, not newly filed independent applications or all company rights.",
                            "Missing observations remain null; same data does not prove the outside world is unchanged.",
                            "Review candidates identify dependencies; they do not assert that every affected conclusion is wrong.",
                            "Write findings into the single analysis/continuation note; do not add an incremental-status module to the interactive report."]}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    capture = sub.add_parser("snapshot", help="Capture a consistent read-only database snapshot")
    capture.add_argument("--db", required=True)
    capture.add_argument("--observation-manifest", help="Optional source-bound acquisition timestamps for search pages")
    capture.add_argument("--output", required=True)
    delta = sub.add_parser("compare", help="Compare two hashed research snapshots")
    delta.add_argument("--before", required=True)
    delta.add_argument("--after", required=True)
    delta.add_argument("--output", required=True)
    args = parser.parse_args(argv)
    try:
        value = snapshot(args.db, args.observation_manifest) if args.command == "snapshot" else compare(read_json(args.before), read_json(args.after))
        write_new(args.output, value)
    except (SnapshotError, ValueError, OSError, sqlite3.Error, KeyError) as error:
        parser.exit(1, "Snapshot comparison failed: " + str(error) + "\n")
    print(json.dumps({"output": str(Path(args.output).resolve()), "kind": value["kind"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
