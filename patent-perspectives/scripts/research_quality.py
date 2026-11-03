"""Evidence-bound review and research records; no model calls or truth scoring.

Checks attestations, coverage and freshness. A passing record is not proof that
its author understood the source or that a research conclusion is true.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import tempfile
from pathlib import Path

CHECKS = ("mechanism", "conditions", "embodiments", "figures", "source_attribution")
TABLES = ("quality_reviews", "research_plan", "research_reviews")
LIMIT = "Review checks establish recorded evidence, coverage and freshness; they do not prove semantic correctness or independent human judgment."


def initialize(c):
    # Separate executes preserve an enclosing caller transaction.
    c.execute("CREATE TABLE IF NOT EXISTS quality_reviews(application_id TEXT PRIMARY KEY,data TEXT NOT NULL)")
    c.execute("CREATE TABLE IF NOT EXISTS research_plan(id TEXT PRIMARY KEY,data TEXT NOT NULL)")
    c.execute("CREATE TABLE IF NOT EXISTS research_reviews(id TEXT PRIMARY KEY,data TEXT NOT NULL)")


def records(c, table):
    if table not in TABLES:
        raise ValueError("Unsupported quality table")
    if not c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone():
        return []
    return [json.loads(r[0]) for r in c.execute("SELECT data FROM " + table)]


def _text(v):
    return isinstance(v, str) and bool(v.strip())


def _strings(v, nonempty=False):
    return isinstance(v, list) and (bool(v) or not nonempty) and all(_text(x) for x in v) and len(v) == len(set(v))


def _items(payload, ctx):
    values = payload if isinstance(payload, list) else [payload]
    ctx["require"](values and all(isinstance(x, dict) for x in values), "Quality input needs nonempty objects")
    return values


def _independent(p, ctx):
    require = ctx["require"]
    require(_text(p.get("analysis_author")) and _text(p.get("reviewer")), "Review needs named analysis_author and reviewer")
    require(p["analysis_author"].strip().casefold() != p["reviewer"].strip().casefold(), "Review author and reviewer must differ")
    require(p.get("independent") is True and p.get("reviewed_original_sources") is True,
            "Review needs explicit independent and original-source review attestations")


def _evidence(c, ids, allowed_apps, ctx):
    require = ctx["require"]
    require(_strings(ids, True), "Quality evidence_ids must be nonempty unique identifiers")
    refs = ctx["check_refs"](c, ids)
    require({r["application_id"] for r in refs} <= set(allowed_apps), "Quality evidence comes from an application outside the reviewed scope")
    for row in refs:
        analysis = c.execute("SELECT * FROM analyses WHERE application_id=?", (row["application_id"],)).fetchone()
        require(analysis and ctx["analysis_is_current"](c, analysis), "Quality evidence needs a current completed analysis")
        require(row["id"] in json.loads(analysis["data"]).get("evidence_ids", []), "Quality evidence is not in the current analysis")
    return refs


def _fingerprint(c, appid, ctx):
    row = c.execute("SELECT * FROM analyses WHERE application_id=?", (appid,)).fetchone()
    ctx["require"](row and ctx["analysis_is_current"](c, row), "Semantic review needs a current completed analysis")
    analysis = json.loads(row["data"])
    analysis.pop("completed_at", None)
    evidence = [dict(r) for r in _evidence(c, analysis.get("evidence_ids"), {appid}, ctx)]
    return ctx["digest"]({"analysis": analysis, "evidence": sorted(evidence, key=lambda x: x["id"])})


def _review_source_evidence(c, p, analysis, ctx):
    """Keep a reviewer's new original-source observations outside the draft.

    A reviewer must be able to expose a condition the author never quoted.
    These spans do not become author evidence or change the reviewed fingerprint.
    """
    require = ctx["require"]
    selected = p.get("source_evidence", [])
    require(isinstance(selected, list), "Review source_evidence must be an array")
    if not selected:
        return []
    primary = c.execute("SELECT * FROM documents WHERE id=?", (analysis["document_id"],)).fetchone()
    primary_meta = json.loads(primary["data"])
    prepared, seen = [], set()
    for item in selected:
        require(isinstance(item, dict) and _text(item.get("id")), "Review source evidence needs its own id")
        require(item["id"] not in seen, "Duplicate review source evidence id")
        require(not c.execute("SELECT 1 FROM evidence WHERE id=?", (item["id"],)).fetchone(),
                "Review source evidence ids must not shadow saved analysis evidence")
        seen.add(item["id"])
        doc = c.execute("SELECT * FROM documents WHERE id=?", (item.get("document_id", primary["id"]),)).fetchone()
        require(doc and doc["application_id"] == primary["application_id"]
                and doc["publication_id"] == primary["publication_id"],
                "Review source evidence must use the same application and publication version")
        require(ctx["document_is_eligible"](c, doc), "Review source evidence cannot use an incomplete or rejected source")
        require(ctx["digest"](doc["text"]) == doc["text_hash"], "Review original source no longer matches its saved hash")
        meta = json.loads(doc["data"])
        require(str(meta.get("language", "")).strip().casefold() == str(primary_meta.get("language", "")).strip().casefold(),
                "Review source evidence must use the same original language")
        if "source_text_hash" in item:
            require(item["source_text_hash"] == doc["text_hash"], "Review source evidence text hash changed")
        evidence = ctx["make_evidence"](c, doc, item)
        if doc["document_type"] == "description":
            ctx["validate_support_evidence_locator"](doc, evidence)
        evidence["source_text_hash"] = doc["text_hash"]
        prepared.append(evidence)
    return prepared


def _prepare_review(c, p, ctx):
    require = ctx["require"]
    appid = p.get("application_id")
    require(appid in {a["id"] for a in ctx["included_applications"](c)}, "Semantic review application is outside the included population")
    fingerprint = _fingerprint(c, appid, ctx)
    require(_text(p.get("analysis_fingerprint")), "Semantic review requires the analysis_fingerprint from export-quality-work")
    require(p["analysis_fingerprint"] == fingerprint, "Stale semantic review: analysis or evidence changed")
    _independent(p, ctx)
    analysis = json.loads(c.execute("SELECT data FROM analyses WHERE application_id=?", (appid,)).fetchone()[0])
    if _text(analysis.get("analysis_author")):
        require(p["analysis_author"] == analysis["analysis_author"], "Review analysis_author must match the saved analysis author")
    require(p.get("result") in ("pass", "revise"), "Semantic review result must be pass or revise")
    own_evidence = _review_source_evidence(c, p, analysis, ctx)
    own_ids = {x["id"] for x in own_evidence}
    ids = p.get("evidence_ids")
    require(_strings(ids, True) and own_ids <= set(ids), "Review must cite all its own source evidence")
    saved_ids = [eid for eid in ids if eid not in own_ids]
    if saved_ids:
        _evidence(c, saved_ids, {appid}, ctx)
    checks = p.get("checks")
    require(isinstance(checks, dict) and set(checks) == set(CHECKS), "Semantic review must address all five checks")
    for name, check in checks.items():
        require(isinstance(check, dict) and check.get("status") in ("pass", "fail", "not_applicable") and _text(check.get("basis")),
                "Semantic review check needs status and explanation: " + name)
        if check["status"] in ("pass", "fail"):
            require(_strings(check.get("evidence_ids"), True) and set(check["evidence_ids"]) <= set(ids),
                    "Check evidence must be included in the review evidence_ids")
    require(checks["source_attribution"]["status"] != "not_applicable", "Source attribution is always applicable")
    require(p["result"] != "pass" or all(x["status"] != "fail" for x in checks.values()), "Failed check cannot produce a passing semantic review")
    result = dict(p)
    if own_evidence:
        result["source_evidence"] = own_evidence
    result.update(analysis_fingerprint=fingerprint, verification_limit=LIMIT)
    return result


def _save(c, table, key, item, ctx):
    column = "application_id" if table == "quality_reviews" else "id"
    previous = c.execute("SELECT data FROM " + table + " WHERE " + column + "=?", (key,)).fetchone()
    if previous:
        ctx["event"](c, "quality-record-superseded", {"table": table, "key": key, "previous": json.loads(previous[0])})
    item = ctx["sanitized"](dict(item))
    item["recorded_at"] = dt.datetime.now(dt.timezone.utc).isoformat()
    c.execute("INSERT OR REPLACE INTO " + table + " VALUES(?,?)", (key, ctx["dump"](item)))


def import_review(c, payload, ctx):
    values = [_prepare_review(c, p, ctx) for p in _items(payload, ctx)]
    ctx["require"](len({x["application_id"] for x in values}) == len(values), "Duplicate applications in semantic review batch")
    for item in values:
        _save(c, "quality_reviews", item["application_id"], item, ctx)
    return {"semantic_reviews_imported": len(values)}


def _prepare_plan(c, payload, ctx):
    require = ctx["require"]
    require(isinstance(payload, dict), "Research plan must be an object")
    questions = payload.get("questions")
    require(isinstance(questions, list) and questions, "Research plan needs explicit nonempty questions")
    apps = {a["id"] for a in ctx["included_applications"](c)}
    normalized = []
    for q in questions:
        require(isinstance(q, dict) and all(_text(q.get(k)) for k in ("id", "question", "selection_basis")), "Research question needs id, question and selection_basis")
        require(_strings(q.get("application_ids"), True) and set(q["application_ids"]) <= apps, "Research question needs included applications")
        normalized.append({"id": q["id"], "question": q["question"], "selection_basis": q["selection_basis"], "application_ids": sorted(q["application_ids"])})
    require(len({q["id"] for q in normalized}) == len(normalized), "Duplicate research question identifiers")
    normalized.sort(key=lambda q: q["id"])
    plan_hash = ctx["digest"](normalized)
    if "plan_hash" in payload:
        require(payload["plan_hash"] == plan_hash, "Research plan hash disagrees with questions")
    result = {"id": "active", "questions": normalized, "plan_hash": plan_hash}
    if _text(payload.get("revision_reason")):
        result["revision_reason"] = payload["revision_reason"]
    return result


def import_plan(c, payload, ctx):
    plan = _prepare_plan(c, payload, ctx)
    old = next((x for x in records(c, "research_plan") if x.get("id") == "active"), None)
    if old and old["plan_hash"] != plan["plan_hash"]:
        ctx["require"](_text(plan.get("revision_reason")), "Changing research questions requires revision_reason; previous plan is retained in events")
    _save(c, "research_plan", "active", plan, ctx)
    return {"research_questions": len(plan["questions"]), "plan_hash": plan["plan_hash"]}


def _prepare_research(c, p, plan, ctx):
    require = ctx["require"]
    question = next((q for q in plan["questions"] if q["id"] == p.get("question_id")), None)
    require(question is not None, "Research review refers to an unknown planned question")
    population = ctx["population_hash"](c)
    require(_text(p.get("plan_hash")) and _text(p.get("population_hash")),
            "Research review requires plan_hash and population_hash from export-quality-work")
    require(p["plan_hash"] == plan["plan_hash"], "Stale research review: plan changed")
    require(p["population_hash"] == population, "Stale research review: population or analysis changed")
    require(p.get("status") in ("resolved", "insufficient_evidence"), "Research status must be resolved or insufficient_evidence")
    require(_text(p.get("answer")) and _text(p.get("conditions")) and _strings(p.get("limitations")), "Research needs answer, conditions and explicit limitations array")
    refs = _evidence(c, p.get("evidence_ids"), question["application_ids"], ctx)
    comparison = p.get("comparison")
    require(isinstance(comparison, dict) and comparison.get("status") in ("compared", "not_comparable") and _text(comparison.get("basis")), "Research comparison needs status and reasoning")
    if comparison["status"] == "compared":
        require(len({x["application_id"] for x in refs}) >= 2, "Cross-patent comparison needs evidence from at least two applications")
    counter = p.get("counterevidence")
    require(isinstance(counter, dict) and all(_text(counter.get(k)) for k in ("search_scope", "findings", "impact")), "Research needs counterevidence search scope, findings and impact; honestly record when none was found")
    _independent(p, ctx)
    require(p.get("review_result") in ("pass", "revise"), "Research independent review needs pass or revise")
    if p["status"] == "insufficient_evidence":
        require(p["limitations"], "Insufficient research evidence needs explicit limitations")
    result = dict(p)
    result.update(id=p["question_id"], plan_hash=plan["plan_hash"], population_hash=population, verification_limit=LIMIT)
    return result


def import_research(c, payload, ctx):
    plan = next((x for x in records(c, "research_plan") if x.get("id") == "active"), None)
    ctx["require"](plan is not None, "Import the research plan before its results")
    plan = _prepare_plan(c, plan, ctx)
    values = [_prepare_research(c, p, plan, ctx) for p in _items(payload, ctx)]
    ctx["require"](len({x["id"] for x in values}) == len(values), "Duplicate questions in research review batch")
    for item in values:
        _save(c, "research_reviews", item["id"], item, ctx)
    return {"research_reviews_imported": len(values)}


def _protect_database_output(c, path, ctx):
    protected = []
    for row in c.execute("PRAGMA database_list"):
        if row[2]:
            database = Path(row[2]).resolve()
            protected.extend((database, Path(str(database) + "-wal"), Path(str(database) + "-shm")))
    for database_file in protected:
        same = path.resolve() == database_file.resolve()
        if not same and path.exists() and database_file.exists():
            same = path.samefile(database_file)
        ctx["require"](not same, "Quality export must not overwrite an open database or its WAL/SHM files (including aliases)")


def _write_manifest(c, path, payload, ctx):
    _protect_database_output(c, path, ctx)
    path.parent.mkdir(parents=True, exist_ok=True)
    # Replacement changes the directory entry rather than truncating an existing
    # inode. Hard links and symlinks must never turn an export into a DB write.
    fd, temporary = tempfile.mkstemp(prefix=".quality-export-", suffix=".tmp", dir=path.parent)
    temporary = Path(temporary)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
            stream.flush()
            os.fsync(stream.fileno())
        _protect_database_output(c, path, ctx)
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def _export_review_packet(c, root, appid, fingerprint, analysis, primary, ctx):
    """One intact source packet per patent; draft findings are a separate file."""
    folder = Path(root) / ("patent-" + ctx["digest"]([appid, fingerprint])[:24])
    primary_meta = json.loads(primary["data"])
    candidates = [primary]
    for doc in c.execute("SELECT * FROM documents WHERE application_id=? AND publication_id=? ORDER BY id",
                         (appid, primary["publication_id"])):
        meta = json.loads(doc["data"])
        if (doc["id"] != primary["id"] and doc["document_type"] == "description"
                and ctx["document_is_eligible"](c, doc)
                and str(meta.get("language", "")).strip().casefold() == str(primary_meta.get("language", "")).strip().casefold()):
            candidates.append(doc)
    sources, seen = [], set()
    for doc in candidates:
        key = (doc["document_type"], doc["text_hash"])
        if key in seen:
            continue
        seen.add(key)
        meta = json.loads(doc["data"])
        sources.append({"document_id": doc["id"], "publication_number": doc["publication_id"],
            "document_type": doc["document_type"], "version": meta.get("version"), "language": meta.get("language"),
            "source_url": meta.get("source_url", ""), "source_text_hash": doc["text_hash"],
            "text": doc["text"], "character_count": len(doc["text"]),
            "reading_scope": "primary_full_text" if doc["id"] == primary["id"] else "available_for_targeted_reading",
            "claim_index": [{k: v for k, v in block.items() if k != "text"} for block in meta.get("claims", [])]})
    blind = {"application_id": appid, "analysis_fingerprint": fingerprint, "primary_document_id": primary["id"],
        "reading_unit": "whole_patent", "sources": sources,
        "material_availability": {"original_texts": "included_in_full",
            "description": "included_in_full" if any(s["document_type"] == "description" for s in sources) else "not_acquired_in_this_packet",
            "figures": "not_embedded_check_original_publication_and_run_materials"},
        "instructions": "Read this patent's original sources first and save independent observations before opening draft-comparison.json. Sources are complete and unpartitioned; assess actual capacity and record selected description/image reading honestly. The fingerprint identifies the draft version; it is not a quality score."}
    original = folder / "original-sources.json"
    comparison = folder / "draft-comparison.json"
    _write_manifest(c, original, ctx["sanitized"](blind), ctx)
    _write_manifest(c, comparison, ctx["sanitized"]({"application_id": appid,
        "analysis_fingerprint": fingerprint, "analysis": analysis,
        "instructions": "Open only after independently reading original-sources.json. Compare the saved draft against your observations; cite omitted original text with review-local source_evidence without changing this draft."}), ctx)
    return {"original_sources": str(original), "draft_comparison": str(comparison)}


def export_work(c, output, ctx, review_packets=None):
    """Export exact versions to inspect; never creates a passing review or writes the DB.

    Includes current passing records with an explicit state so this manifest also
    supports deliberate re-review. Authors must carry these fingerprints into
    their results, not refresh an old judgment with newly obtained hashes.
    """
    _protect_database_output(c, Path(output), ctx)
    reviews = {x["application_id"]: x for x in records(c, "quality_reviews")}
    semantic, unavailable = [], []
    for app in ctx["included_applications"](c):
        if app.get("patent_type") not in ("invention", "utility_model"):
            continue
        try:
            fingerprint = _fingerprint(c, app["id"], ctx)
            row = c.execute("SELECT * FROM analyses WHERE application_id=?", (app["id"],)).fetchone()
            analysis = json.loads(row["data"])
            doc = c.execute("SELECT * FROM documents WHERE id=?", (row["document_id"],)).fetchone()
            old = reviews.get(app["id"])
            state = "pending"
            if old:
                try:
                    checked = _prepare_review(c, old, ctx)
                    state = "current_pass" if checked["result"] == "pass" else "revise"
                except (ValueError, KeyError, TypeError):
                    state = "stale"
            source_ids = [doc["id"]] + [s["document_id"] for s in analysis.get("support_documents", [])]
            sources = []
            for source_id in source_ids:
                source = c.execute("SELECT * FROM documents WHERE id=?", (source_id,)).fetchone()
                meta = json.loads(source["data"])
                sources.append({"document_id": source_id, "publication_number": source["publication_id"],
                    "document_type": source["document_type"], "source_text_hash": source["text_hash"],
                    "version": meta.get("version"), "language": meta.get("language"), "source_url": meta.get("source_url", "")})
            item = {"application_id": app["id"], "analysis_author": analysis.get("analysis_author"),
                "analysis_fingerprint": fingerprint, "document_id": doc["id"], "source_text_hash": doc["text_hash"],
                "evidence_ids": analysis["evidence_ids"], "review_state": state,
                "analysis_reference": {"table": "analyses", "application_id": app["id"]},
                "source_references": sources}
            if review_packets is not None:
                item["review_packets"] = _export_review_packet(c, review_packets, app["id"], fingerprint, analysis, doc, ctx)
            semantic.append(item)
        except (ValueError, KeyError, TypeError) as error:
            unavailable.append({"application_id": app["id"], "reason": str(error)})
    plan = next((x for x in records(c, "research_plan") if x.get("id") == "active"), None)
    research, plan_error = [], None
    if plan:
        try:
            plan = _prepare_plan(c, plan, ctx)
            population = ctx["population_hash"](c)
            existing = {x["id"]: x for x in records(c, "research_reviews")}
            for question in plan["questions"]:
                state = "pending"
                old = existing.get(question["id"])
                if old:
                    try:
                        checked = _prepare_research(c, old, plan, ctx)
                        state = "current_pass" if checked["status"] == "resolved" and checked["review_result"] == "pass" else "revise"
                    except (ValueError, KeyError, TypeError):
                        state = "stale"
                research.append({"question_id": question["id"], "plan_hash": plan["plan_hash"],
                    "population_hash": population, "question": question, "application_ids": question["application_ids"],
                    "review_state": state})
        except (ValueError, KeyError, TypeError) as error:
            plan_error = str(error)
    else:
        plan_error = "No research plan has been imported."
    payload = ctx["sanitized"]({"schema_version": 1, "semantic_reviews": semantic, "research_reviews": research,
        "unavailable_analyses": unavailable, "research_plan_issue": plan_error, "verification_limit": LIMIT,
        "instructions": "Inspect the exact source versions and current analysis/question. Return the exported fingerprints unchanged in the review input. A changed fingerprint requires a fresh review; never relabel a prior judgment."})
    path = Path(output)
    _write_manifest(c, path, payload, ctx)
    return {"output": str(path), "semantic_review_items": len(semantic), "research_review_items": len(research),
        "unavailable_analyses": len(unavailable), "semantic_pending": sum(x["review_state"] != "current_pass" for x in semantic),
        "research_pending": sum(x["review_state"] != "current_pass" for x in research)}


def validate(c, ctx):
    """Read-only validation; safe on legacy DBs without the three quality tables."""
    errors, warnings = [], []
    scope = ctx["run_info"](c)["scope"]
    required = scope.get("require_research_quality", not scope.get("synthetic", False)) is True
    if not scope.get("synthetic", False) and not required:
        errors.append({"code": "quality_gate_disabled", "detail": "Real runs cannot disable research-quality review"})
        required = True
    apps = [a for a in ctx["included_applications"](c) if a.get("patent_type") in ("invention", "utility_model")]
    coverage = {"research_quality_required": required, "semantic_review_required": len(apps), "semantic_review_passed": 0,
                "research_questions": 0, "research_questions_resolved": 0}
    if not required:
        return {"errors": errors, "warnings": warnings, "coverage": coverage}
    warnings.append({"code": "quality_attestation_limit", "detail": LIMIT})
    reviews = {x["application_id"]: x for x in records(c, "quality_reviews")}
    for app in apps:
        p = reviews.get(app["id"])
        if not p:
            errors.append({"code": "semantic_review_missing", "detail": app["id"]})
            continue
        try:
            checked = _prepare_review(c, p, ctx)
            ctx["require"](checked["result"] == "pass", "Semantic review requires revision")
            coverage["semantic_review_passed"] += 1
        except (ValueError, KeyError, TypeError) as error:
            errors.append({"code": "semantic_review_invalid", "detail": app["id"] + ": " + str(error)})
    if not apps:
        return {"errors": errors, "warnings": warnings, "coverage": coverage}
    plan = next((x for x in records(c, "research_plan") if x.get("id") == "active"), None)
    if not plan:
        errors.append({"code": "research_plan_missing", "detail": "Explicit research questions and comparison scope are required"})
    else:
        try:
            plan = _prepare_plan(c, plan, ctx)
        except (ValueError, KeyError, TypeError) as error:
            errors.append({"code": "research_plan_invalid", "detail": str(error)})
            return {"errors": errors, "warnings": warnings, "coverage": coverage}
        coverage["research_questions"] = len(plan["questions"])
        results = {x["id"]: x for x in records(c, "research_reviews")}
        for question in plan["questions"]:
            p = results.get(question["id"])
            if not p:
                errors.append({"code": "research_question_unresolved", "detail": question["id"]})
                continue
            try:
                checked = _prepare_research(c, p, plan, ctx)
                ctx["require"](checked["status"] == "resolved" and checked["review_result"] == "pass", "Research question is unresolved or needs revision")
                coverage["research_questions_resolved"] += 1
            except (ValueError, KeyError, TypeError) as error:
                errors.append({"code": "research_review_invalid", "detail": question["id"] + ": " + str(error)})
    return {"errors": errors, "warnings": warnings, "coverage": coverage}
