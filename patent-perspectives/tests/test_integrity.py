"""Behavioral integrity regressions using only clearly synthetic patent fixtures.

Run with Python unittest; never queries a provider or touches the real Joyoung run.
"""
import argparse
import copy
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("patent_perspectives_under_test", ROOT / "scripts" / "patent_perspectives.py")
engine = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(engine)


class IntegrityTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="patent-synthetic-")
        self.addCleanup(self.tmp.cleanup)
        self.directory = Path(self.tmp.name)
        self.dbpath = self.directory / "synthetic.sqlite"
        self.db = engine.db_open(self.dbpath)
        self.addCleanup(lambda: self.db.close())
        scope = self.directory / "scope.json"
        scope.write_text(json.dumps({"synthetic": True}), encoding="utf-8")
        with self.db:
            engine.init_run(self.db, argparse.Namespace(company="SYNTHETIC INTEGRITY FIXTURE", as_of="2026-10-20", scope=str(scope)))
            engine.import_entities(self.db, [{"id": "synthetic-root", "name": "Synthetic Test Entity", "relation": "root", "confirmed": True, "source_url": "https://example.test/synthetic", "source_locator": "synthetic fixture"}])
            engine.scope_confirm(self.db, {"confirmed": True, "basis": "Synthetic fixture only", "reviewed_through": "2026-10-20"})

    def record(self, n=1, **changes):
        value = {"pn": "CN90000000%dA" % n, "apno": "CN20200000000%d" % n, "title": "SYNTHETIC PATENT %d" % n, "patent_type": "invention", "filing_date": "2020-01-01", "publication_date": "2021-01-01", "original_assignee": "Synthetic Test Entity", "current_assignee": "Synthetic Test Entity", "family_id": "synthetic-common-family"}
        value.update(changes)
        return value

    def search(self, records, qid="synthetic-original", kind="original", expected=None, offset=0, result=None):
        expected = len(records) if expected is None else expected
        data = {"query": {"id": qid, "entity_id": "synthetic-root", "kind": kind, "provider": "Synthetic fixture", "expected_count": expected, "request": {"query": "SYNTHETIC ONLY", "cutoff": "2026-10-20"}}, "offset": offset, "result": result if result is not None else {"records": records, "total_search_result_count": expected}}
        with self.db:
            return engine.import_search(self.db, data)

    def seed(self, records=None):
        records = [self.record()] if records is None else records
        for kind in ("original", "current"):
            self.search(records, qid="synthetic-" + kind, kind=kind)
            with self.db:
                engine.complete_query(self.db, "synthetic-" + kind)
        return [engine.normalize_record(r, "Synthetic fixture")["application_id"] for r in records]

    def doc_input(self, n=1, **changes):
        value = {"publication_number": self.record(n)["pn"], "returned_publication_number": self.record(n)["pn"], "application_number": self.record(n)["apno"], "document_type": "claims", "identity_verified": True, "replace_by_related": False, "complete": True, "truncated": False, "text": "1. A synthetic piston connects a chamber.\n2. The synthetic valve regulates the chamber.", "claim_count": 2, "source_class": "synthetic", "source_provider": "Synthetic fixture", "source_url": "https://example.test/synthetic/claims", "acquired_at": "2026-10-20T00:00:00Z", "language": "en", "version": "synthetic-published", "completeness_basis": "Synthetic fixture contains exactly two numbered claims."}
        value.update(changes)
        return value

    def document(self, n=1, **changes):
        with self.db:
            return engine.import_document(self.db, self.doc_input(n, **changes))

    def analysis_input(self, doc, quote="synthetic piston", locator=None):
        eid = "evidence-" + doc["application_id"]
        return {"application_id": doc["application_id"], "document_id": doc["document_id"], "completed_chunk_ids": doc["chunk_ids"], "primary_module": "Synthetic mechanism", "tags": ["synthetic"], "summary": {"text": "Synthetic fixture describes a piston and chamber.", "evidence_ids": [eid], "kind": "disclosed"}, "fields": {"technical_means": [{"text": "Synthetic piston connection", "evidence_ids": [eid], "kind": "disclosed"}]}, "evidence": [{"id": eid, "quote": quote, "locator": locator or {"claim_number": 1}}], "limitations": ["Synthetic fixture; not a real patent."]}

    def analyze(self, doc, **changes):
        data = self.analysis_input(doc)
        data.update(changes)
        with self.db:
            return engine.import_analysis(self.db, data)

    def insight(self, role, appid, value=1):
        return {"id": "synthetic-insight-" + role, "role": role, "title": "Synthetic " + role, "body": "Synthetic evidence-backed role interpretation.", "scope": "Synthetic patent fixture only", "limitations": ["Not real company analysis"], "kind": "observation", "patent_ids": [appid], "evidence_ids": ["evidence-" + appid], "metrics": [{"metric": "application_count", "application_ids": [appid], "value": value}]}

    def complete_fixture(self):
        appid = self.seed()[0]
        doc = self.document()
        self.analyze(doc)
        with self.db:
            engine.import_insights(self.db, [self.insight(role, appid) for role in engine.ROLES])
        self.assertEqual(engine.validate_run(self.db)["status"], "complete")
        return appid, doc

    def assert_blocked_render(self, label="blocked"):
        out = self.directory / label
        with self.assertRaises(engine.ValidationError):
            engine.render(self.db, out)
        self.assertFalse(out.exists(), "Formal render must fail before creating delivery files")

    def test_missing_fulltext_never_completes_or_renders(self):
        self.seed()
        report = engine.validate_run(self.db)
        self.assertEqual(report["coverage"]["technical_fulltext"], 0)
        self.assertEqual(report["coverage"]["technical_completion"], 0)
        self.assertIn("technical_analysis_missing", {x["code"] for x in report["errors"]})
        self.assert_blocked_render()

    def test_partial_claims_are_retained_but_never_qualified(self):
        self.seed()
        doc = self.document(complete=False, truncated=True, text="1. A synthetic piston connects a chamber.", claim_count=2)
        self.assertFalse(doc["qualified"])
        self.assertEqual(doc["chunk_ids"], [])
        with self.assertRaises(engine.ValidationError):
            self.analyze(doc)
        self.assert_blocked_render()

    def test_declared_claim_count_catches_missing_claim(self):
        self.seed()
        with self.assertRaises(engine.ValidationError):
            self.document(text="1. A synthetic piston connects a chamber.", claim_count=2)
        self.assertEqual(self.db.execute("SELECT count(*) FROM documents").fetchone()[0], 0)

    def test_truncation_flag_overrides_complete_flag(self):
        self.seed()
        doc = self.document(complete=True, truncated=True)
        self.assertFalse(doc["qualified"])
        with self.assertRaises(engine.ValidationError):
            self.analyze(doc)
        self.assert_blocked_render()

    def test_same_family_different_publication_cannot_substitute(self):
        self.seed([self.record(1), self.record(2)])
        with self.assertRaises(engine.ValidationError):
            self.document(1, returned_publication_number=self.record(2)["pn"])
        with self.assertRaises(engine.ValidationError):
            self.document(1, replace_by_related=True)

    def test_analysis_cannot_use_other_application_document(self):
        ids = self.seed([self.record(1), self.record(2)])
        doc = self.document(1)
        with self.assertRaises(engine.ValidationError):
            self.analyze(doc, application_id=ids[1])

    def test_every_long_document_chunk_is_required(self):
        self.seed()
        text = "Synthetic description: synthetic piston.\n" + ("A distinct synthetic technical paragraph. " * 700)
        doc = self.document(document_type="description", text=text)
        self.assertGreater(len(doc["chunk_ids"]), 2)
        with self.assertRaises(engine.ValidationError):
            self.analyze(doc, completed_chunk_ids=doc["chunk_ids"][:-1])
        with self.assertRaises(engine.ValidationError):
            self.analyze(doc, completed_chunk_ids=doc["chunk_ids"] + doc["chunk_ids"][:1])

    def test_wrong_evidence_quote_is_rejected(self):
        self.seed()
        doc = self.document()
        data = self.analysis_input(doc, quote="THIS PHRASE IS ABSENT")
        with self.assertRaises(engine.ValidationError), self.db:
            engine.import_analysis(self.db, data)

    def test_wrong_claim_number_is_rejected(self):
        self.seed()
        doc = self.document()
        data = self.analysis_input(doc, quote="synthetic piston", locator={"claim_number": 2})
        with self.assertRaises(engine.ValidationError), self.db:
            engine.import_analysis(self.db, data)

    def test_repeated_quote_cannot_use_span_from_different_claim(self):
        self.seed()
        text = "1. A synthetic piston supports the chamber.\n2. A synthetic piston moves inside the chamber."
        doc = self.document(text=text)
        data = self.analysis_input(doc, locator={"claim_number": 2})
        start = text.index("synthetic piston")
        data["evidence"][0].update(start=start, end=start + len("synthetic piston"))
        with self.assertRaises(engine.ValidationError), self.db:
            engine.import_analysis(self.db, data)

    def test_caller_cannot_swap_numbered_claim_blocks(self):
        self.seed()
        first = "1. A synthetic piston connects a chamber."
        second = "2. The synthetic valve regulates the chamber."
        with self.assertRaises(engine.ValidationError):
            self.document(claims=[{"number": 1, "text": second}, {"number": 2, "text": first}])

    def test_known_error_and_html_are_not_fulltext(self):
        self.seed()
        for body in ("MCP API need a true tool rate!", "<html><body>Sign in</body></html>", "Unauthorized"):
            with self.subTest(body=body), self.assertRaises(engine.ValidationError):
                self.document(document_type="description", text=body)

    def test_mcp_outer_error_cannot_be_converted_to_zero_results(self):
        wrapped = {"isError": True, "structuredContent": {"records": [], "total_search_result_count": 0}}
        with self.assertRaises(engine.ValidationError):
            self.search([], expected=0, result=wrapped)
        self.assertEqual(self.db.execute("SELECT count(*) FROM queries").fetchone()[0], 0)

    def test_response_total_cannot_be_overridden_by_smaller_expected_count(self):
        with self.assertRaises(engine.ValidationError):
            self.search([self.record()], expected=1, result={"records": [self.record()], "total_search_result_count": 2})

    def test_missing_pagination_offset_prevents_query_completion(self):
        self.search([self.record(1)], expected=3)
        self.search([self.record(2)], expected=3, offset=2)
        with self.assertRaises(engine.ValidationError), self.db:
            engine.complete_query(self.db, "synthetic-original")
        self.assertFalse(self.db.execute("SELECT complete FROM queries").fetchone()[0])

    def test_repeated_and_overlapping_pages_are_rejected(self):
        self.search([self.record(1), self.record(2)], expected=4)
        with self.assertRaises(engine.ValidationError):
            self.search([self.record(1), self.record(2)], expected=4, offset=2)
        with self.assertRaises(engine.ValidationError):
            self.search([self.record(2), self.record(3)], expected=4, offset=2)
        self.assertEqual(self.db.execute("SELECT count(*) FROM query_results").fetchone()[0], 2)

    def test_page_cache_replay_is_idempotent(self):
        self.search([self.record()])
        with self.db:
            engine.complete_query(self.db, "synthetic-original")
        second = self.search([self.record()])
        self.assertTrue(second["cached"])
        self.assertEqual(self.db.execute("SELECT count(*) FROM pages").fetchone()[0], 1)
        self.assertEqual(self.db.execute("SELECT count(*) FROM applications").fetchone()[0], 1)
        self.assertTrue(self.db.execute("SELECT complete FROM queries").fetchone()[0])

    def test_cache_replay_ignores_only_acquisition_timestamp_changes(self):
        self.search([self.record(acquired_at="2026-10-20T00:00:00Z")])
        result = self.search([self.record(acquired_at="2026-10-20T00:01:00Z")])
        self.assertTrue(result["cached"])
        with self.assertRaises(engine.ValidationError):
            self.search([self.record(title="Changed source title", acquired_at="2026-10-20T00:01:00Z")])

    def test_frozen_query_and_page_cannot_silently_change(self):
        self.search([self.record()])
        with self.assertRaises(engine.ValidationError):
            self.search([self.record()], expected=2)
        with self.assertRaises(engine.ValidationError):
            self.search([self.record(title="Changed title")])

    def test_after_cutoff_result_rolls_back_the_entire_page(self):
        with self.assertRaises(engine.ValidationError):
            self.search([self.record(1), self.record(2, publication_date="2026-10-21")])
        self.assertEqual(self.db.execute("SELECT count(*) FROM applications").fetchone()[0], 0)
        self.assertEqual(self.db.execute("SELECT count(*) FROM queries").fetchone()[0], 0)

    def test_application_counts_deduplicate_publication_versions(self):
        original = self.record()
        grant = self.record(pn="CN900000001B", publication_date="2022-01-01")
        self.seed([original, grant])
        cov = engine.coverage(self.db)
        self.assertEqual(cov["applications"], 1)
        self.assertEqual(cov["publications"], 2)
        self.assertEqual(cov["technical_applications"], 1)

    def test_one_missing_application_prevents_formal_delivery(self):
        ids = self.seed([self.record(1), self.record(2)])
        self.analyze(self.document(1))
        with self.db:
            engine.import_insights(self.db, [self.insight(role, ids[0]) for role in engine.ROLES])
        report = engine.validate_run(self.db)
        self.assertEqual(report["coverage"]["technical_completion"], 50)
        self.assertEqual(report["status"], "incomplete")
        self.assert_blocked_render()

    def test_three_roles_share_canonical_counts_and_evidence(self):
        appid, doc = self.complete_fixture()
        report = engine.validate_run(self.db)
        payload, details = engine.build_payload(self.db, report)
        self.assertEqual(payload["stats"]["application_count"], 1)
        self.assertEqual({i["role"] for i in payload["insights"]}, set(engine.ROLES))
        for insight in payload["insights"]:
            self.assertEqual(insight["metrics"][0]["value"], 1)
            self.assertEqual(insight["patent_ids"], [appid])
            self.assertEqual(insight["evidence_ids"], ["evidence-" + appid])
        with self.assertRaises(engine.ValidationError), self.db:
            engine.import_insights(self.db, self.insight("management", appid, value=999))

    def test_resume_keeps_finished_analysis_and_exports_only_pending(self):
        ids = self.seed([self.record(1), self.record(2)])
        first = self.document(1)
        self.analyze(first)
        second = self.document(2)
        self.db.commit()
        self.db.close()
        self.db = engine.db_open(self.dbpath)
        out = self.directory / "synthetic-pending.jsonl"
        result = engine.export_work(self.db, out)
        self.assertEqual(result["work_items"], 1)
        pending = [json.loads(x) for x in out.read_text(encoding="utf-8").splitlines()]
        self.assertEqual(pending[0]["application_id"], ids[1])
        self.assertEqual(pending[0]["document_id"], second["document_id"])
        replay = self.document(1)
        self.assertTrue(replay["cached"])
        self.assertEqual(replay["document_id"], first["document_id"])
        self.assertEqual(engine.coverage(self.db)["technical_analyzed"], 1)

    def test_complete_claims_are_preferred_and_description_offered_for_targeted_reading(self):
        self.seed()
        claims = self.document()
        description = self.document(document_type="description", text="A synthetic piston description with all synthetic implementation content.")
        out = self.directory / "synthetic-pending.jsonl"
        engine.export_work(self.db, out)
        row = json.loads(out.read_text(encoding="utf-8"))
        self.assertEqual(row["document_id"], claims["document_id"])
        self.assertEqual(row["source"]["document_type"], "claims")
        self.assertEqual(row["support_document_candidates"][0]["document_id"],description["document_id"])
        self.assertNotIn("chunks",row["support_document_candidates"][0])

    def test_explicit_typography_notation_survives_source_evidence_and_detail_payload(self):
        appid=self.seed()[0]
        text="1. A synthetic flow range is 1.5×10^{4}mm^{3}/s≤A≤3.5×10^{5}mm^{3}/s.\n2. A synthetic condition uses x_{i}."
        note="Source superscripts/subscripts explicitly use ^{...}/_{...}; no exponent is inferred."
        doc=self.document(text=text,version="synthetic-typography-v2",text_format_note=note,
                          normalization_transformations=[{"type":"html_superscript_subscript_preservation","policy_version":"supsub-v2"}])
        analysis=self.analysis_input(doc,quote="1.5×10^{4}mm^{3}/s")
        engine.import_analysis(self.db,analysis)
        engine.import_insights(self.db,[self.insight(role,appid) for role in engine.ROLES])
        report=engine.validate_run(self.db);self.assertEqual(report["status"],"complete")
        _,details=engine.build_payload(self.db,report);detail=details[appid]
        self.assertEqual(detail["documents"][0]["text"],text)
        self.assertEqual(detail["documents"][0]["text_format_note"],note)
        self.assertEqual(detail["evidence"][0]["quote"],"1.5×10^{4}mm^{3}/s")
        source=json.loads(self.db.execute("SELECT data FROM documents WHERE id=?",(doc["document_id"],)).fetchone()[0])
        self.assertEqual(source["normalization_transformations"][0]["policy_version"],"supsub-v2")

    def test_claims_only_complete_fixture_renders_traceable_offline_payload(self):
        appid, doc = self.complete_fixture()
        out = self.directory / "synthetic-delivery"
        result = engine.render(self.db, out)
        self.assertEqual(result["status"], "complete")
        for name in ("index.html", "style.css", "app.js", "overview.svg", "validation.json", "data/bootstrap.js"):
            self.assertTrue((out / name).is_file(), name)
        bootstrap = (out / "data/bootstrap.js").read_text(encoding="utf-8")
        payload = json.loads(bootstrap[len("window.PP_DATA="):].rstrip(";\n"))
        self.assertEqual(payload["patents"][0]["text_basis"], "claims")
        shard = out / payload["detail_shards"][appid]
        text = shard.read_text(encoding="utf-8")
        detail = json.loads(text[len("window.PP_registerDetails("):].rstrip(");\n"))[appid]
        self.assertEqual(detail["evidence"][0]["publication_number"], self.record()["pn"])
        self.assertIn("synthetic piston", detail["documents"][0]["text"])
        self.assertEqual(detail["claims"][1]["number"], 2)
        self.assertIn("legal_status_partial", {w["code"] for w in json.loads((out / "validation.json").read_text(encoding="utf-8"))["warnings"]})

    def test_cached_source_corruption_prevents_render(self):
        appid, doc = self.complete_fixture()
        with self.db:
            self.db.execute("UPDATE documents SET text=text || ? WHERE id=?", (" CORRUPTED SYNTHETIC CACHE", doc["document_id"]))
        self.assertIn("stale_analysis", {x["code"] for x in engine.validate_run(self.db)["errors"]})
        self.assert_blocked_render()

    def test_scope_change_invalidates_previous_completion(self):
        self.complete_fixture()
        with self.db:
            engine.import_entities(self.db, [{"id": "synthetic-subsidiary", "name": "Synthetic subsidiary", "relation": "subsidiary", "confirmed": True, "source_url": "https://example.test/synthetic", "source_locator": "synthetic fixture"}])
        report = engine.validate_run(self.db)
        self.assertEqual(report["status"], "incomplete")
        self.assertIn("scope_unconfirmed", {x["code"] for x in report["errors"]})
        self.assert_blocked_render()


    def test_unverified_source_total_cannot_complete_query(self):
        data = {"query": {"id": "synthetic-unverified", "entity_id": "synthetic-root", "kind": "original", "expected_count": 1, "request": {"query": "SYNTHETIC ONLY"}}, "offset": 0, "result": {"records": [self.record()]}}
        try:
            with self.db:
                engine.import_search(self.db, data)
        except engine.ValidationError:
            return  # Early rejection is also an acceptable fail-closed implementation.
        with self.assertRaises(engine.ValidationError), self.db:
            engine.complete_query(self.db, "synthetic-unverified")

    def test_nested_successful_provider_response_keeps_source_count(self):
        result = {"structuredContent": {"data": {"records": [self.record()], "total_search_result_count": 1}}}
        self.search([self.record()], result=result)
        with self.db:
            completed = engine.complete_query(self.db, "synthetic-original")
        self.assertTrue(completed["complete"])

    def test_nested_provider_error_is_not_a_successful_empty_search(self):
        result = {"data": {"success": False, "records": [], "total_search_result_count": 0, "message": "Synthetic access failure"}}
        with self.assertRaises(engine.ValidationError):
            self.search([], expected=0, result=result)

    def test_json_error_object_is_not_technical_description(self):
        self.seed()
        bodies = [
            {"code": 403, "message": "Forbidden"},
            {"error_code": 401, "error_msg": "Synthetic unauthorized"},
            {"data": {"success": False, "message": "Synthetic denied"}},
        ]
        for body in bodies:
            with self.subTest(body=body), self.assertRaises(engine.ValidationError):
                self.document(document_type="description", text=json.dumps(body))

    def test_cli_validation_exit_codes_reflect_completeness(self):
        self.seed()
        self.db.commit()
        result, code = engine.cli(["--db", str(self.dbpath), "validate"])
        self.assertEqual(code, 3)
        self.assertEqual(result["status"], "incomplete")
        doc = self.document()
        self.analyze(doc)
        appid = doc["application_id"]
        with self.db:
            engine.import_insights(self.db, [self.insight(role, appid) for role in engine.ROLES])
        result, code = engine.cli(["--db", str(self.dbpath), "validate"])
        self.assertEqual(code, 0)
        self.assertEqual(result["status"], "complete")


    def test_page_beyond_declared_window_is_rejected_at_import(self):
        self.search([self.record(1)], expected=2)
        with self.assertRaises(engine.ValidationError):
            self.search([self.record(2)], expected=2, offset=2)
        self.assertEqual(self.db.execute("SELECT count(*) FROM pages").fetchone()[0], 1)
        self.assertEqual(self.db.execute("SELECT count(*) FROM query_results").fetchone()[0], 1)


    def test_changed_analysis_invalidates_old_roles_until_all_are_refreshed(self):
        appid, doc = self.complete_fixture()
        prior_hashes = {i["population_hash"] for i in engine.rows_data(self.db, "insights")}
        updated = self.analysis_input(doc)
        updated["fields"]["technical_means"][0]["text"] = "Updated synthetic interpretation of the evidenced piston connection."
        with self.db:
            engine.import_analysis(self.db, updated)
        stale = engine.validate_run(self.db)
        self.assertEqual(stale["coverage"]["technical_completion"], 100)
        self.assertEqual(stale["status"], "incomplete")
        self.assertEqual({e["detail"] for e in stale["errors"] if e["code"] == "stale_role_insight"}, {"synthetic-insight-" + role for role in engine.ROLES})
        self.assert_blocked_render("stale-role-delivery")
        with self.db:
            engine.import_insights(self.db, [self.insight(role, appid) for role in engine.ROLES])
        refreshed = engine.validate_run(self.db)
        self.assertEqual(refreshed["status"], "complete")
        self.assertNotEqual(prior_hashes, {i["population_hash"] for i in engine.rows_data(self.db, "insights")})


    def test_cli_json_preserves_chinese_under_legacy_console_encoding(self):
        import os
        import subprocess
        import sys
        dbpath = self.directory / "chinese-output.sqlite"
        environment = os.environ.copy()
        environment["PYTHONIOENCODING"] = "cp936"
        args = [sys.executable, str(ROOT / "scripts" / "patent_perspectives.py"),
                "--db", str(dbpath), "init", "--company", "九阳股份有限公司",
                "--as-of", "2026-10-20"]
        result = subprocess.run(args, env=environment, stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, check=True)
        output = json.loads(result.stdout.decode("utf-8"))
        self.assertIn("九阳股份有限公司", json.dumps(output, ensure_ascii=False))

    def test_real_run_cannot_bypass_full_population_gate_with_preview(self):
        with self.db:
            run = engine.run_info(self.db)
            run["scope"]["synthetic"] = False
            self.db.execute("UPDATE meta SET value=? WHERE key='run'",
                            (json.dumps(run, ensure_ascii=False),))
        with self.assertRaises(engine.ValidationError):
            engine.render(self.db, str(self.directory / "forbidden-real-preview"), True)
        self.assertFalse((self.directory / "forbidden-real-preview").exists())

    def require_population_review(self):
        run = engine.run_info(self.db)
        run["scope"]["require_population_review"] = True
        engine.set_meta(self.db, "run", run)

    def population_review(self, n=1, status="included", name="Synthetic Test Entity"):
        return {"application_id": engine.normalize_record(self.record(n), "Synthetic fixture")["application_id"],
                "status": status, "reason_code": "target_entity" if status == "included" else "different_entity",
                "reason": "Original assignee is the verified synthetic target." if status == "included" else "Official synthetic identity evidence establishes another applicant.",
                "matched_entity_ids": ["synthetic-root"] if status == "included" else [],
                "assignee_evidence": [{"publication_number": self.record(n)["pn"], "field": "original_assignee", "value": name, "matched_name": name}]}

    def foreign_review(self, n=2, name="Foreign Synthetic Applicant"):
        review = self.population_review(n, "excluded", name)
        review["identity_source"] = {"source_url": "https://www.uspto.gov/synthetic-test-record",
                                     "source_locator": "SYNTHETIC original applicant and address",
                                     "quote": name + ", SYNTHETIC foreign address", "subject_name": name,
                                     "determination": "different_entity"}
        return review

    def test_reviewed_false_positive_excluded_without_losing_search_reconciliation(self):
        self.require_population_review()
        foreign = self.record(2, original_assignee="Foreign Synthetic Applicant", current_assignee="Foreign Synthetic Applicant")
        ids = self.seed([self.record(1), foreign])
        with self.db:
            engine.import_population_reviews(self.db, [self.population_review(), self.foreign_review()])
        self.analyze(self.document(1))
        with self.db:
            engine.import_insights(self.db, [self.insight(role, ids[0]) for role in engine.ROLES])
        report = engine.validate_run(self.db)
        self.assertEqual(report["status"], "complete")
        cov = report["coverage"]
        self.assertEqual((cov["candidate_applications"], cov["included_applications"], cov["excluded_applications"], cov["pending_applications"]), (2, 1, 1, 0))
        self.assertEqual((cov["candidate_publications"], cov["publications"], cov["technical_applications"]), (2, 1, 1))
        self.assertEqual(self.db.execute("SELECT count(*) FROM query_results").fetchone()[0], 4)
        self.assertEqual(self.db.execute("SELECT count(*) FROM pages").fetchone()[0], 2)
        for q in self.db.execute("SELECT * FROM queries"):
            self.assertEqual((q["complete"], q["expected_count"], q["observed_count"]), (1, 2, 2))
        payload, details = engine.build_payload(self.db, report)
        self.assertEqual([p["id"] for p in payload["patents"]], [ids[0]])
        self.assertEqual(set(details), {ids[0]})
        self.assertEqual(payload["stats"]["application_count"], 1)

    def test_pending_candidate_blocks_formal_acceptance_and_stays_out_of_work_and_page(self):
        self.require_population_review()
        ids = self.seed([self.record(1), self.record(2)])
        self.document(1)
        self.document(2)
        with self.db:
            engine.import_population_reviews(self.db, self.population_review(1))
            engine.import_population_reviews(self.db, {"application_id": ids[1], "status": "pending", "reason": "Original applicant identity still needs verification."})
        out = self.directory / "reviewed-work.jsonl"
        result = engine.export_work(self.db, out)
        self.assertEqual(result["work_items"], 1)
        self.assertEqual(json.loads(out.read_text(encoding="utf-8"))["application_id"], ids[0])
        report = engine.validate_run(self.db)
        self.assertEqual(report["coverage"]["pending_applications"], 1)
        self.assertIn("population_review_pending", {e["code"] for e in report["errors"]})
        payload, details = engine.build_payload(self.db, report)
        self.assertEqual({p["id"] for p in payload["patents"]}, {ids[0]})
        self.assertEqual(set(details), {ids[0]})
        self.assert_blocked_render("pending-population")

    def test_missing_fulltext_cannot_be_used_to_exclude_a_candidate(self):
        self.require_population_review()
        self.seed()
        review = self.population_review(status="excluded")
        for code, reason in [("missing_text", "No full text was retrieved."), ("different_entity", "Missing full text; skip this application."), ("different_entity", "Treat the target applicant as another entity.")]:
            review.update(reason_code=code, reason=reason)
            with self.subTest(code=code, reason=reason), self.assertRaises(engine.ValidationError), self.db:
                engine.import_population_reviews(self.db, review)
        self.assertEqual(engine.coverage(self.db)["pending_applications"], 1)

    def test_included_candidate_still_requires_complete_technical_analysis(self):
        self.require_population_review()
        self.seed()
        with self.db:
            engine.import_population_reviews(self.db, self.population_review())
        report = engine.validate_run(self.db)
        self.assertEqual(report["coverage"]["technical_applications"], 1)
        self.assertEqual(report["coverage"]["technical_fulltext"], 0)
        self.assertIn("technical_analysis_missing", {e["code"] for e in report["errors"]})
        self.assert_blocked_render("included-missing-text")

    def test_review_requires_exact_source_assignee_and_verified_identity(self):
        self.require_population_review()
        self.seed()
        review = self.population_review()
        review["assignee_evidence"][0]["value"] = "SYNTHETIC NORMALIZED LABEL"
        with self.assertRaises(engine.ValidationError), self.db:
            engine.import_population_reviews(self.db, review)
        review = self.population_review()
        review["matched_entity_ids"] = ["unverified-entity"]
        with self.assertRaises(engine.ValidationError), self.db:
            engine.import_population_reviews(self.db, review)
        with self.assertRaises(engine.ValidationError):
            self.analyze(self.document())

    def test_population_review_change_invalidates_roles_and_new_version_requires_review(self):
        self.require_population_review()
        appid = self.seed()[0]
        review = self.population_review()
        with self.db:
            engine.import_population_reviews(self.db, review)
        self.analyze(self.document())
        with self.db:
            engine.import_insights(self.db, [self.insight(role, appid) for role in engine.ROLES])
        self.assertEqual(engine.validate_run(self.db)["status"], "complete")
        review["reason"] = "Rechecked original assignee against the verified synthetic target name."
        with self.db:
            engine.import_population_reviews(self.db, review)
        self.assertEqual(sum(e["code"] == "stale_role_insight" for e in engine.validate_run(self.db)["errors"]), 3)
        grant = self.record(pn="CN900000001B", publication_date="2022-01-01")
        self.search([grant], qid="synthetic-grant-review", expected=1)
        self.assertEqual(engine.population_state(self.db)[appid], "pending")
        self.assertEqual(engine.coverage(self.db)["included_applications"], 0)
        self.assertIn("population_review_pending", {e["code"] for e in engine.validate_run(self.db)["errors"]})

    def test_cached_patsnap_identity_must_match_original_party_and_address(self):
        self.require_population_review()
        name = "Foreign Synthetic Applicant"
        self.seed([self.record(2, original_assignee=name, current_assignee=name)])
        request = {"tool": "bibliography", "arguments": {"patent_number": self.record(2)["pn"]}}
        artifact = {"source_request": request, "response": {"success": True, "data": [{"pn": self.record(2)["pn"], "bibliographic_data": {"parties": {"applicants": [{"name": name, "address": "SYNTHETIC foreign address"}]}}}], "error_code": 0}}
        (self.directory / "original-bibliography.json").write_text(json.dumps(artifact), encoding="utf-8")
        review = self.population_review(2, "excluded", name)
        party = ["response", "data", 0, "bibliographic_data", "parties", "applicants", 0]
        review["identity_source"] = {"source_class": "patsnap", "source_artifact": "original-bibliography.json", "source_request": request,
                                     "returned_publication_number": self.record(2)["pn"], "response_path": ["response"], "publication_path": ["response", "data", 0, "pn"],
                                     "name_path": party + ["name"], "name_value": name, "address_path": party + ["address"], "address_value": "SYNTHETIC foreign address",
                                     "subject_name": name, "source_locator": "original bibliography applicant 1", "determination": "different_entity"}
        wrong = copy.deepcopy(review)
        wrong["identity_source"]["address_value"] = "fabricated address"
        with self.assertRaises(engine.ValidationError), self.db:
            engine.import_population_reviews(self.db, wrong)
        artifact["isError"] = True
        (self.directory / "original-bibliography.json").write_text(json.dumps(artifact), encoding="utf-8")
        with self.assertRaises(engine.ValidationError), self.db:
            engine.import_population_reviews(self.db, review)
        artifact.pop("isError")
        (self.directory / "original-bibliography.json").write_text(json.dumps(artifact), encoding="utf-8")
        with self.db:
            engine.import_population_reviews(self.db, review)
        self.assertEqual(engine.coverage(self.db)["excluded_applications"], 1)
        self.assertEqual(self.db.execute("SELECT count(*) FROM applications").fetchone()[0], 1)

    def counted_query(self, qid, kind, text, records, verification=False):
        with self.db:
            engine.import_search(self.db, {"query": {"id": qid, "entity_id": "synthetic-root", "kind": kind,
                "expected_count": len(records), "request": {"query_text": text, "verification_only": verification}},
                "offset": 0, "result": {"records": records, "total_search_result_count": len(records)}})
            engine.complete_query(self.db, qid)
        return qid

    def empty_set(self, kind="original", prefix="empty"):
        text = "AN:SYNTHETIC_EMPTY_" + prefix
        controls = []
        for n in (7, 8):
            qid = prefix + "-" + kind + "-" + str(n)
            self.counted_query(qid, kind, "(" + text + ") OR PN:" + self.record(n)["pn"], [self.record(n)], True)
            controls.append({"query_id": qid, "anchor_publication_number": self.record(n)["pn"]})
        return {"id": prefix + "-set-" + kind, "entity_id": "synthetic-root", "kind": kind, "query_text": text,
                "type": "empty_by_disjoint_anchors", "source_total_count": None, "derived_count": 0, "controls": controls}

    def direct_set(self, kind="original", prefix="direct", records=None):
        records = [self.record()] if records is None else records
        text = "AN:SYNTHETIC_" + prefix
        qid = self.counted_query(prefix + "-" + kind, kind, text, records)
        return {"id": prefix + "-set-" + kind, "entity_id": "synthetic-root", "kind": kind,
                "query_text": text, "type": "direct", "leaf_query_id": qid, "source_total_count": len(records)}

    def test_control_queries_cannot_satisfy_ordinary_entity_query_coverage(self):
        self.empty_set("original")
        self.empty_set("current")
        report = engine.validate_run(self.db)
        self.assertIn("missing_query", {x["code"] for x in report["errors"]})
        self.assertEqual(report["coverage"]["candidate_applications"], 0)
        self.assertEqual(report["coverage"]["control_only_stored_applications"], 2)

    def test_verified_empty_logical_sets_keep_null_source_total_and_allow_true_zero_population(self):
        sets = [self.empty_set(kind, "empty-" + kind) for kind in ("original", "current")]
        with self.db:
            engine.import_query_sets(self.db, sets)
            engine.query_plan_confirm(self.db, {"plan_hash": "a" * 64, "required_query_set_ids": [s["id"] for s in sets]})
        report = engine.validate_run(self.db)
        self.assertEqual(report["status"], "complete")
        self.assertEqual(report["coverage"]["candidate_publications"], 0)
        self.assertEqual(report["coverage"]["technical_applications"], 0)
        self.assertEqual(report["coverage"]["verification_queries"], 4)
        payload, details = engine.build_payload(self.db, report)
        self.assertEqual(payload["patents"], [])
        self.assertEqual(details, {})
        for s in engine.rows_data(self.db, "query_sets"):
            self.assertIsNone(s["source_total_count"])
            self.assertEqual(s["derived_count"], 0)
        for row in self.db.execute("SELECT * FROM queries"):
            self.assertEqual((row["expected_count"], row["observed_count"]), (1, 1))

    def test_empty_proof_rejects_fabricated_zero_same_anchor_and_wrong_parent(self):
        original = self.empty_set()
        bad = copy.deepcopy(original)
        bad["source_total_count"] = 0
        with self.assertRaises(engine.ValidationError):engine.import_query_sets(self.db, bad)
        bad = copy.deepcopy(original)
        bad["controls"][1] = copy.deepcopy(bad["controls"][0])
        with self.assertRaises(engine.ValidationError):engine.import_query_sets(self.db, bad)
        bad = copy.deepcopy(original)
        bad["query_text"] = "AN:ANOTHER_SYNTHETIC_QUERY"
        with self.assertRaises(engine.ValidationError):engine.import_query_sets(self.db, bad)
        bad = copy.deepcopy(original)
        bad["type"] = "direct";bad["leaf_query_id"] = original["controls"][0]["query_id"]
        bad["source_total_count"] = 1
        with self.assertRaises(engine.ValidationError):engine.import_query_sets(self.db, bad)

    def test_logical_set_rechecks_retained_raw_control_counts(self):
        spec = self.empty_set()
        with self.db:
            engine.import_query_sets(self.db, spec)
            engine.query_plan_confirm(self.db, {"plan_hash": "b" * 64, "required_query_set_ids": [spec["id"]]})
            qid = spec["controls"][0]["query_id"]
            row = self.db.execute("SELECT raw FROM pages WHERE query_id=?", (qid,)).fetchone()
            raw = json.loads(row[0]);raw["total_search_result_count"] = 0
            self.db.execute("UPDATE pages SET raw=? WHERE query_id=?", (json.dumps(raw), qid))
        report = engine.validate_run(self.db)
        self.assertIn("query_set_invalid", {e["code"] for e in report["errors"]})
        self.assert_blocked_render("invalid-empty-source")

    def test_frozen_plan_requires_every_named_set_and_cannot_change_requirements(self):
        spec = self.direct_set()
        missing = {"id": "missing-current", "entity_id": "synthetic-root", "kind": "current", "query_text": "ANC:SYNTHETIC_PENDING"}
        with self.db:
            engine.import_query_sets(self.db, spec)
            engine.query_plan_confirm(self.db, {"plan_hash": "c" * 64, "required_query_sets": [{k: spec[k] for k in ("id", "entity_id", "kind", "query_text")}, missing]})
        self.assertIn("required_query_set_missing", {e["code"] for e in engine.validate_run(self.db)["errors"]})
        with self.assertRaises(engine.ValidationError), self.db:
            engine.query_plan_confirm(self.db, {"plan_hash": "d" * 64, "required_query_set_ids": [spec["id"]]})

    def partition_set(self, prefix="partition", left_end="20200630", right_start="20200701"):
        text = "AN:SYNTHETIC_" + prefix
        records = [self.record(4, publication_date="2020-03-01"), self.record(5, publication_date="2021-03-01")]
        children = []
        for i, (lo, hi) in enumerate((("20200101", left_end), (right_start, "20261020"))):
            child_text = "(" + text + ") AND PBD:[" + lo + " TO " + hi + "]"
            qid = self.counted_query(prefix + "-child-" + str(i), "original", child_text, [records[i]])
            child = {"id": prefix + "-set-child-" + str(i), "entity_id": "synthetic-root", "kind": "original", "type": "direct", "query_text": child_text,
                     "leaf_query_id": qid, "source_total_count": 1}
            with self.db:engine.import_query_sets(self.db, child)
            children.append({"query_set_id": child["id"], "date_from": lo, "date_to": hi})
        return {"id": prefix + "-parent", "entity_id": "synthetic-root", "kind": "original", "type": "date_partition", "query_text": text,
                "date_start": "20200101", "date_end": "20261020", "source_total_count": 2, "children": children,
                "parent_source": {"request": {"query_text": text, "sort_order": "ASC", "sort_field": "PBDT_YEARMONTHDAY"},
                                  "raw_response": {"success": True, "data": {"total_search_result_count": 2, "results": records[:1]}}}}

    def test_date_partition_checks_raw_parent_total_and_nonoverlapping_complete_intervals(self):
        spec = self.partition_set()
        with self.db:
            result = engine.import_query_sets(self.db, spec)
        self.assertEqual(result[0]["logical_count"], 2)
        bad = copy.deepcopy(spec);bad["source_total_count"] = 0
        with self.assertRaises(engine.ValidationError):engine.import_query_sets(self.db, bad)
        overlapping = self.partition_set("overlap", "20200701", "20200701")
        with self.assertRaises(engine.ValidationError):engine.import_query_sets(self.db, overlapping)
        gap = self.partition_set("gap", "20200629", "20200701")
        with self.assertRaises(engine.ValidationError):engine.import_query_sets(self.db, gap)

    def test_logical_plan_change_invalidates_roles_until_shared_evidence_is_refreshed(self):
        appid, doc = self.complete_fixture()
        sets = [self.direct_set(kind, "logical-role-" + kind) for kind in ("original", "current")]
        with self.db:
            engine.import_query_sets(self.db, sets)
            engine.query_plan_confirm(self.db, {"plan_hash": "e" * 64, "required_query_set_ids": [s["id"] for s in sets]})
        self.assertEqual(sum(e["code"] == "stale_role_insight" for e in engine.validate_run(self.db)["errors"]), 3)
        with self.db:engine.import_insights(self.db, [self.insight(role, appid) for role in engine.ROLES])
        self.assertEqual(engine.validate_run(self.db)["status"], "complete")

    def test_retained_raw_transport_error_cannot_hide_behind_successful_result(self):
        payload = {"query": {"id": "raw-envelope-error", "entity_id": "synthetic-root", "kind": "original", "expected_count": 1,
                             "request": {"query_text": "AN:SYNTHETIC"}},
                   "result": {"records": [self.record()], "total_search_result_count": 1},
                   "raw": {"transport": {"jsonrpc": "2.0", "error": {"code": -32000, "message": "SYNTHETIC access denied"}},
                           "pagination": {"offset": 0, "limit": 1000}}}
        with self.assertRaises(engine.ValidationError), self.db:
            engine.import_search(self.db, payload)
        self.assertEqual(self.db.execute("SELECT count(*) FROM queries").fetchone()[0], 0)

    def test_cached_patsnap_identity_keeps_real_batch_request_and_matches_returned_record(self):
        self.require_population_review()
        name = "Foreign Synthetic Applicant"
        self.seed([self.record(2, original_assignee=name, current_assignee=name)])
        target = self.record(2)["pn"];other = self.record(9)["pn"]
        arguments = {"patent_number": other + ", " + target}
        artifact = {"tool": "bibliography", "arguments": arguments,
                    "response": {"success": True, "error_code": 0, "data": [
                        {"pn": other, "bibliographic_data": {"parties": {"applicants": [{"name": "Another Synthetic Party", "address": "Another address"}]}}},
                        {"pn": target, "bibliographic_data": {"parties": {"applicants": [{"name": name, "address": "SYNTHETIC foreign address"}]}}}]}}
        path = self.directory / "original-batch-bibliography.json"
        path.write_text(json.dumps(artifact), encoding="utf-8")
        party = ["response", "data", 1, "bibliographic_data", "parties", "applicants", 0]
        review = self.population_review(2, "excluded", name)
        review["identity_source"] = {"source_class": "patsnap", "source_artifact": path.name,
            "source_request": {"tool": "bibliography", "arguments": arguments}, "request_tool_path": ["tool"], "request_arguments_path": ["arguments"],
            "response_path": ["response"], "publication_path": ["response", "data", 1, "pn"], "returned_publication_number": target,
            "name_path": party + ["name"], "name_value": name, "address_path": party + ["address"], "address_value": "SYNTHETIC foreign address",
            "subject_name": name, "source_locator": "original batch bibliography applicant", "determination": "different_entity"}
        with self.db:engine.import_population_reviews(self.db, review)
        self.assertEqual(engine.coverage(self.db)["excluded_applications"], 1)
        fake_single = copy.deepcopy(review)
        fake_single["identity_source"]["source_request"]["arguments"]["patent_number"] = target
        with self.assertRaises(engine.ValidationError), self.db:engine.import_population_reviews(self.db, fake_single)
        wrong_record = copy.deepcopy(review)
        wrong_record["identity_source"]["publication_path"] = ["response", "data", 0, "pn"]
        with self.assertRaises(engine.ValidationError), self.db:engine.import_population_reviews(self.db, wrong_record)
        artifact["arguments"] = {"patent_number": other}
        path.write_text(json.dumps(artifact), encoding="utf-8")
        absent = copy.deepcopy(review)
        absent["identity_source"]["source_request"]["arguments"] = artifact["arguments"]
        with self.assertRaises(engine.ValidationError), self.db:engine.import_population_reviews(self.db, absent)


    def bibliography_input(self, record=None, provider_type="PATENT", **changes):
        """Actual-cache-shaped batch fixture; request is never synthesized as single PN."""
        record = self.record() if record is None else record
        pn = record["pn"]
        apno = engine.number(record["apno"])
        country = pn[:2]
        appdoc = apno if apno.startswith("PCT") else apno[len(country):]
        pubdoc = pn[len(country):-1]
        data = {"patent_type": provider_type,
                "application_reference": {"country": country, "doc_number": appdoc, "date": 20200101},
                "publication_reference": {"country": country, "doc_number": pubdoc, "kind": pn[-1], "date": 20210101},
                "parties": {"applicants": [{"name": record["original_assignee"], "address": "SYNTHETIC exact original address"}]},
                "classification_data": {"classification_ipcr": {"main_classification": {"section": "A", "class": "47", "sub_class": "J", "main_group": "31", "sub_group": "00"}}}}
        data.update(changes)
        arguments = {"patent_number": "CN900000009A, " + pn}
        artifact = {"endpoint": "https://connect.zhihuiya.com/958a46/mcp", "tool": "bibliography", "arguments": arguments,
                    "response": {"jsonrpc": "2.0", "result": {"isError": False, "structuredContent": {
                        "success": True, "error_code": 0, "data": [
                            {"pn": "CN900000009A", "bibliographic_data": {}}, {"pn": pn, "bibliographic_data": data}]}}}}
        path = self.directory / (pn + "-bibliography.json")
        path.write_text(json.dumps(artifact), encoding="utf-8")
        return {"publication_number": pn, "application_number": apno, "source_artifact": path.name,
                "source_request": {"tool": "bibliography", "arguments": arguments},
                "request_tool_path": ["tool"], "request_arguments_path": ["arguments"],
                "response_path": ["response", "result", "structuredContent"], "record_index": 1}, artifact, path

    def test_bibliography_fills_unknown_foreign_type_without_changing_search_evidence(self):
        record = self.record(pn="HK900001A", apno="HK201000001", patent_type="unknown")
        appid = self.seed([record])[0]
        before_pages = [tuple(r) for r in self.db.execute("SELECT * FROM pages")]
        before_queries = [tuple(r) for r in self.db.execute("SELECT * FROM queries")]
        before_raw = json.loads(self.db.execute("SELECT data FROM publications").fetchone()[0])["metadata_original"]
        payload, artifact, path = self.bibliography_input(record, "APPLICATION")
        with self.db:result = engine.import_bibliographies(self.db, payload)
        self.assertEqual(result[0]["type_updates"], ["publications", "applications"])
        self.assertEqual(result[0]["conflicts"], [])
        pub = json.loads(self.db.execute("SELECT data FROM publications").fetchone()[0])
        app = json.loads(self.db.execute("SELECT data FROM applications").fetchone()[0])
        self.assertEqual((pub["patent_type"], app["patent_type"]), ("invention", "invention"))
        self.assertEqual(pub["metadata_original"], before_raw)
        self.assertEqual([tuple(r) for r in self.db.execute("SELECT * FROM pages")], before_pages)
        self.assertEqual([tuple(r) for r in self.db.execute("SELECT * FROM queries")], before_queries)
        stored = engine.rows_data(self.db, "bibliographies")[0]
        self.assertEqual(stored["record_path"], ["response", "result", "structuredContent", "data", 1])
        self.assertEqual(stored["record_original"], artifact["response"]["result"]["structuredContent"]["data"][1])
        self.assertEqual(stored["parties_original"]["applicants"][0]["address"], "SYNTHETIC exact original address")
        self.assertEqual(stored["ipcs"][0]["symbol"], "A47J31/00")
        self.assertEqual(stored["artifact_sha256"], engine.hashlib.sha256(path.read_bytes()).hexdigest())
        with self.db:again = engine.import_bibliographies(self.db, payload)
        self.assertTrue(again[0]["cached"])
        self.assertEqual(again[0]["type_updates"], [])
        self.assertEqual(self.db.execute("SELECT count(*) FROM bibliographies").fetchone()[0], 1)
        self.assertEqual(engine.coverage(self.db)["technical_applications"], 1)
        self.assertIn("technical_analysis_missing", {e["code"] for e in engine.validate_run(self.db)["errors"]})

    def test_bibliography_requires_actual_batch_member_exact_record_and_application(self):
        self.seed()
        payload, artifact, path = self.bibliography_input()
        variants = []
        wrong = copy.deepcopy(payload);wrong["record_index"] = 0;variants.append((wrong, artifact))
        wrong = copy.deepcopy(payload);wrong["source_request"]["arguments"]["patent_number"] = self.record()["pn"];variants.append((wrong, artifact))
        absent = copy.deepcopy(artifact);absent["arguments"]["patent_number"] = "CN900000009A"
        wrong = copy.deepcopy(payload);wrong["source_request"]["arguments"] = absent["arguments"];variants.append((wrong, absent))
        different = copy.deepcopy(artifact);different["response"]["result"]["structuredContent"]["data"][1]["bibliographic_data"]["application_reference"]["doc_number"] = "202000000099"
        variants.append((payload, different))
        error = copy.deepcopy(artifact);error["response"]["error"] = {"code": -32000};variants.append((payload, error))
        error = copy.deepcopy(artifact);error["response"]["result"]["structuredContent"]["success"] = False;variants.append((payload, error))
        for value, source in variants:
            path.write_text(json.dumps(source), encoding="utf-8")
            with self.subTest(value=value), self.assertRaises(engine.ValidationError), self.db:
                engine.import_bibliographies(self.db, value)
        self.assertEqual(self.db.execute("SELECT count(*) FROM bibliographies").fetchone()[0], 0)

    def test_bibliography_preserves_pct_application_and_unrecognized_provider_type(self):
        record = self.record(pn="WO900001A", apno="PCT/CN2020/000001", patent_type="unknown")
        self.seed([record])
        payload, artifact, path = self.bibliography_input(record, "UNDEFINED_PROVIDER_CLASS")
        with self.db:result = engine.import_bibliographies(self.db, payload)
        self.assertEqual(result[0]["patent_type"], "unknown")
        self.assertEqual(result[0]["type_updates"], [])
        stored = engine.rows_data(self.db, "bibliographies")[0]
        self.assertEqual(stored["application_number"], "PCTCN2020000001")
        self.assertNotIn("CNPCT", stored["application_number"])
        self.assertEqual(stored["provider_patent_type"], "UNDEFINED_PROVIDER_CLASS")
        self.assertEqual(engine.canonical_application_reference({"country": "CN", "doc_number": "CN202000000001.2"}), "CN2020000000012")
        # Malaysia's local PI prefix is not a country code; keep MY + PI...
        self.assertEqual(engine.canonical_application_reference({"country": "MY", "doc_number": "PI2010001036"}), "MYPI2010001036")

    def test_bibliography_known_type_conflict_preserves_source_type_and_blocks_denominator(self):
        self.complete_fixture()
        payload, _, _ = self.bibliography_input(provider_type="DESIGN")
        with self.db:result = engine.import_bibliographies(self.db, payload)
        self.assertEqual(result[0]["type_updates"], [])
        self.assertEqual(result[0]["conflicts"][0]["field"], "patent_type")
        self.assertEqual(engine.rows_data(self.db, "applications")[0]["patent_type"], "invention")
        report = engine.validate_run(self.db)
        self.assertEqual(report["coverage"]["technical_completion"], 100.0)
        self.assertIn("bibliography_type_conflict", {e["code"] for e in report["errors"]})
        self.assert_blocked_render("bibliography-type-conflict")

    def test_missing_auxiliary_bibliography_fields_do_not_block_completed_technical_analysis(self):
        self.complete_fixture()
        payload, _, _ = self.bibliography_input(application_reference={"country": "CN", "doc_number": "202000000001"},
                                               publication_reference=None, classification_data=None, parties=None)
        with self.db:result = engine.import_bibliographies(self.db, payload)
        self.assertEqual(result[0]["conflicts"], [])
        self.assertEqual(result[0]["type_updates"], [])
        self.assertEqual(engine.validate_run(self.db)["status"], "complete")
        stored = engine.rows_data(self.db, "bibliographies")[0]
        self.assertEqual(stored["ipcs"], [])
        self.assertEqual(stored["dates"], {"filing_date": None, "publication_date": None})

    def test_bibliography_date_conflict_keeps_fulltext_complete_but_date_stats_unknown(self):
        appid, _ = self.complete_fixture()
        payload, _, _ = self.bibliography_input(application_reference={"country": "CN", "doc_number": "202000000001", "date": 20191231})
        with self.db:
            engine.import_bibliographies(self.db, payload)
            engine.import_insights(self.db, [self.insight(role, appid) for role in engine.ROLES])
        report = engine.validate_run(self.db)
        self.assertEqual(report["status"], "complete")
        self.assertEqual(report["coverage"]["technical_completion"], 100.0)
        self.assertIn("bibliography_date_conflicts", {w["code"] for w in report["warnings"]})
        output, details = engine.build_payload(self.db, report)
        self.assertIsNone(output["patents"][0]["filing_date"])
        self.assertEqual(output["stats"]["by_filing_year"], {"unknown": 1})
        self.assertEqual(engine.rows_data(self.db, "applications")[0]["filing_date"], "2020-01-01")
        self.assertEqual(details[appid]["bibliographies"][0]["dates"]["filing_date"], "2019-12-31")

    def test_bibliography_only_changed_type_requires_affected_review_to_be_rechecked(self):
        self.require_population_review()
        record = self.record(pn="HK900001A", apno="HK201000001", patent_type="unknown")
        appid = self.seed([record])[0]
        review = self.population_review();review["application_id"] = appid;review["assignee_evidence"][0]["publication_number"] = record["pn"]
        with self.db:engine.import_population_reviews(self.db, review)
        payload, _, _ = self.bibliography_input(record, "UTILITY")
        with self.db:engine.import_bibliographies(self.db, payload)
        self.assertEqual(engine.application_population_status(self.db, appid), "pending")
        with self.db:engine.import_population_reviews(self.db, review)
        self.assertEqual(engine.application_population_status(self.db, appid), "included")
        snapshot = engine.rows_data(self.db, "population_reviews")[0]["candidate_snapshot_hash"]
        # A source with the same known type is auxiliary and must not stale the identity review.
        with self.db:engine.import_bibliographies(self.db, payload)
        self.assertEqual(engine.application_population_status(self.db, appid), "included")
        self.assertEqual(engine.rows_data(self.db, "population_reviews")[0]["candidate_snapshot_hash"], snapshot)

    def test_search_version_date_conflict_has_the_same_nonblocking_unknown_date_policy(self):
        grant = self.record(pn="CN900000001B", filing_date="2019-12-31", publication_date="2022-01-01")
        appid = self.seed([self.record(), grant])[0]
        self.analyze(self.document())
        with self.db:engine.import_insights(self.db, [self.insight(role, appid) for role in engine.ROLES])
        report = engine.validate_run(self.db)
        self.assertEqual(report["status"], "complete")
        self.assertEqual(report["coverage"]["technical_completion"], 100.0)
        payload, details = engine.build_payload(self.db, report)
        self.assertIsNone(payload["patents"][0]["filing_date"])
        self.assertEqual(payload["stats"]["by_filing_year"], {"unknown": 1})
        sources = details[appid]["date_conflicts"][0]["publication_sources"]
        self.assertEqual({(x["publication_number"], x["value"]) for x in sources}, {("CN900000001A", "2020-01-01"), ("CN900000001B", "2019-12-31")})
        self.assertEqual(sources[0]["raw_fields"][0]["path"], ["metadata_original", "filing_date"])

    def test_search_version_filing_conflict_cannot_justify_control_period_exclusion(self):
        self.require_population_review()
        record = self.record(current_assignee="Foreign Synthetic Applicant")
        grant = self.record(pn="CN900000001B", current_assignee="Foreign Synthetic Applicant", filing_date="2019-12-31", publication_date="2022-01-01")
        self.seed([record, grant])
        review = self.population_review(status="excluded")
        review.update(reason_code="outside_control_period", reason="Synthetic application predates the evidenced control period.", matched_entity_ids=["synthetic-root"],
                      control_period_evidence={"source_url": "https://www.cninfo.com.cn/synthetic-test-record", "source_locator": "SYNTHETIC control period", "quote": "SYNTHETIC controlled from 2021", "subject_name": "Synthetic Test Entity", "determination": "outside_control_period", "relevant_date": "2020-01-01", "control_from": "2021-01-01"})
        with self.assertRaises(engine.ValidationError), self.db:engine.import_population_reviews(self.db, review)

    def test_bibliography_filing_conflict_invalidates_control_period_exclusion_only(self):
        self.require_population_review()
        record = self.record(current_assignee="Foreign Synthetic Applicant")
        appid = self.seed([record])[0]
        review = self.population_review(status="excluded")
        review.update(reason_code="outside_control_period", reason="Synthetic application predates the evidenced control period.", matched_entity_ids=["synthetic-root"],
                      control_period_evidence={"source_url": "https://www.cninfo.com.cn/synthetic-test-record", "source_locator": "SYNTHETIC control period", "quote": "SYNTHETIC controlled from 2021", "subject_name": "Synthetic Test Entity", "determination": "outside_control_period", "relevant_date": "2020-01-01", "control_from": "2021-01-01"})
        with self.db:engine.import_population_reviews(self.db, review)
        self.assertEqual(engine.application_population_status(self.db, appid), "excluded")
        payload, _, _ = self.bibliography_input(record, application_reference={"country": "CN", "doc_number": "202000000001", "date": 20220101})
        with self.db:engine.import_bibliographies(self.db, payload)
        self.assertEqual(engine.application_population_status(self.db, appid), "pending")
        with self.assertRaises(engine.ValidationError), self.db:engine.import_population_reviews(self.db, review)


if __name__ == "__main__":
    unittest.main(verbosity=2)
