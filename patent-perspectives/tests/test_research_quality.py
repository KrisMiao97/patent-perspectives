"""Synthetic evidence-bound review/research gates; no network or real corpus."""
import copy
import importlib.util
import json
import os
import unittest
from pathlib import Path

import test_integrity as fixtures

engine = fixtures.engine
spec = importlib.util.spec_from_file_location("research_quality_under_test", fixtures.ROOT / "scripts/research_quality.py")
quality = importlib.util.module_from_spec(spec)
spec.loader.exec_module(quality)
CTX = {name: getattr(engine, name) for name in (
    "require", "dump", "digest", "sanitized", "event", "check_refs", "population_hash",
    "analysis_is_current", "included_applications", "run_info")}


class ResearchQualityTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.IntegrityTests(methodName="runTest")
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.c = self.fixture.db
        quality.initialize(self.c)
        self.apps = self.fixture.seed([self.fixture.record(1), self.fixture.record(2)])
        self.docs = [self.fixture.document(n) for n in (1, 2)]
        for doc in self.docs:
            engine.import_analysis(self.c, self.analysis(doc))
        run = engine.run_info(self.c)
        run["scope"]["require_research_quality"] = True
        engine.set_meta(self.c, "run", run)

    def analysis(self, doc):
        value = self.fixture.analysis_input(doc)
        value["fields"] = {key: value["fields"].get(key, []) for key in engine.FIELDS}
        row = self.c.execute("SELECT * FROM documents WHERE id=?", (doc["document_id"],)).fetchone()
        value.update(analysis_author="synthetic-author",
            whole_document_review={"document_id": doc["document_id"], "source_text_hash": row["text_hash"],
                "reading_mode": "whole", "complete": True, "capacity_basis": "The two short synthetic claims fit in the reading task."},
            tail_check={"complete": True, "quote": row["text"][-40:], "claim_number": 2})
        return value

    def review(self, n=0):
        ids = ["evidence-" + self.apps[n]]
        manifest = self.work()
        version = next(x for x in manifest["semantic_reviews"] if x["application_id"] == self.apps[n])
        return {"application_id": self.apps[n], "analysis_fingerprint": version["analysis_fingerprint"],
                "analysis_author": "synthetic-author", "reviewer": "synthetic-reviewer",
                "independent": True, "reviewed_original_sources": True, "result": "pass", "evidence_ids": ids,
                "checks": {key: {"status": "pass", "basis": "Checked synthetic source; source relationships are preserved.", "evidence_ids": ids}
                           for key in quality.CHECKS}}

    def work(self):
        path = self.fixture.directory / "quality-work.json"
        quality.export_work(self.c, path, CTX)
        return json.loads(path.read_text(encoding="utf-8"))

    def plan(self):
        return {"questions": [{"id": "q1", "question": "Which disclosed chamber relationships can be compared?",
                "application_ids": self.apps, "selection_basis": "Synthetic examples selected for explicit connection comparison."}]}

    def research(self):
        if not quality.records(self.c, "research_plan"):
            quality.import_plan(self.c, self.plan(), CTX)
        version = self.work()["research_reviews"][0]
        return {"question_id": "q1", "plan_hash": version["plan_hash"], "population_hash": version["population_hash"],
                "status": "resolved", "answer": "Both synthetic sources expressly connect the piston and chamber.",
                "evidence_ids": ["evidence-" + a for a in self.apps],
                "comparison": {"status": "compared", "basis": "Compared both complete synthetic claim sets under the same scope."},
                "counterevidence": {"search_scope": "Both synthetic claim sets and their two numbered claims.",
                    "findings": "No contrary connection was disclosed in this synthetic corpus.", "impact": "Only a bounded corpus observation is supported."},
                "conditions": "Only the two synthetic published versions; no performance superiority is claimed.",
                "limitations": ["Synthetic fixture; no real patent conclusion."],
                "analysis_author": "synthetic-research-author", "reviewer": "synthetic-research-reviewer",
                "independent": True, "reviewed_original_sources": True, "review_result": "pass"}

    def complete(self):
        quality.import_review(self.c, [self.review(0), self.review(1)], CTX)
        quality.import_plan(self.c, self.plan(), CTX)
        quality.import_research(self.c, self.research(), CTX)

    def codes(self):
        return {x["code"] for x in quality.validate(self.c, CTX)["errors"]}

    def test_missing_reviews_and_plan_block_completion(self):
        self.assertEqual(self.codes(), {"semantic_review_missing", "research_plan_missing"})

    def test_complete_records_are_counted_with_truth_limit_warning(self):
        self.complete()
        result = quality.validate(self.c, CTX)
        self.assertEqual(result["errors"], [])
        self.assertEqual(result["coverage"]["semantic_review_passed"], 2)
        self.assertEqual(result["coverage"]["research_questions_resolved"], 1)
        self.assertEqual(result["warnings"][0]["code"], "quality_attestation_limit")

    def test_core_validation_cannot_complete_without_review_then_accepts_complete_research(self):
        engine.import_insights(self.c, [self.fixture.insight(role, self.apps[0]) for role in engine.ROLES])
        before = engine.validate_run(self.c)
        self.assertEqual(before["status"], "incomplete")
        self.assertIn("semantic_review_missing", {x["code"] for x in before["errors"]})
        self.complete()
        after = engine.validate_run(self.c)
        self.assertEqual(after["status"], "complete", after["errors"])

    def test_same_author_cannot_claim_independent_review(self):
        value = self.review()
        value["reviewer"] = " SYNTHETIC-AUTHOR "
        with self.assertRaisesRegex(engine.ValidationError, "must differ"):
            quality.import_review(self.c, value, CTX)

    def test_wrong_application_evidence_and_missing_checks_are_rejected(self):
        value = self.review()
        value["evidence_ids"] = ["evidence-" + self.apps[1]]
        with self.assertRaisesRegex(engine.ValidationError, "outside"):
            quality.import_review(self.c, value, CTX)
        value = self.review()
        del value["checks"]["conditions"]
        with self.assertRaisesRegex(engine.ValidationError, "all five"):
            quality.import_review(self.c, value, CTX)

    def test_failed_check_cannot_pass_but_revision_is_recorded_as_unfinished(self):
        value = self.review()
        value["checks"]["conditions"]["status"] = "fail"
        with self.assertRaisesRegex(engine.ValidationError, "Failed check"):
            quality.import_review(self.c, value, CTX)
        value["result"] = "revise"
        quality.import_review(self.c, value, CTX)
        self.assertIn("semantic_review_invalid", self.codes())

    def test_not_applicable_is_explained_but_source_attribution_cannot_be_skipped(self):
        value = self.review()
        value["checks"]["figures"] = {"status": "not_applicable", "basis": "Synthetic plain-text claims have no figures."}
        quality.import_review(self.c, value, CTX)
        value["checks"]["source_attribution"]["status"] = "not_applicable"
        with self.assertRaisesRegex(engine.ValidationError, "always applicable"):
            quality.import_review(self.c, value, CTX)

    def test_changed_analysis_invalidates_review_and_research(self):
        old_review, old_research = self.review(), self.research()
        self.complete()
        value = self.analysis(self.docs[0])
        value["summary"]["text"] = "A changed synthetic source interpretation needing a new review."
        engine.import_analysis(self.c, value)
        self.assertIn("semantic_review_invalid", self.codes())
        self.assertIn("research_review_invalid", self.codes())
        with self.assertRaisesRegex(engine.ValidationError, "Stale semantic"):
            quality.import_review(self.c, old_review, CTX)
        with self.assertRaisesRegex(engine.ValidationError, "Stale research"):
            quality.import_research(self.c, old_research, CTX)
        del old_review["analysis_fingerprint"]
        del old_research["population_hash"]
        with self.assertRaisesRegex(engine.ValidationError, "requires the analysis_fingerprint"):
            quality.import_review(self.c, old_review, CTX)
        with self.assertRaisesRegex(engine.ValidationError, "requires plan_hash and population_hash"):
            quality.import_research(self.c, old_research, CTX)
        self.assertEqual(quality.validate(self.c, CTX)["coverage"]["semantic_review_passed"], 1)
        self.assertEqual(quality.validate(self.c, CTX)["coverage"]["research_questions_resolved"], 0)

    def test_review_cannot_substitute_another_analysis_author(self):
        value = self.review()
        value["analysis_author"] = "a-different-synthetic-author"
        with self.assertRaisesRegex(engine.ValidationError, "saved analysis author"):
            quality.import_review(self.c, value, CTX)

    def test_rejected_source_invalidates_quality_records(self):
        self.complete()
        engine.import_document_reviews(self.c, {"document_id": self.docs[0]["document_id"], "decision": "reject",
            "reason_code": "missing_text", "reason": "Synthetic intentional source rejection.", "reviewer": "synthetic-source-reviewer",
            "evidence": [{"quote": "synthetic piston", "locator": {"claim_number": 1}}]})
        self.assertIn("semantic_review_invalid", self.codes())
        self.assertIn("research_review_invalid", self.codes())

    def test_plan_revision_preserves_previous_plan_and_invalidates_result(self):
        self.complete()
        old_result = self.research()
        value = self.plan()
        value["questions"][0]["question"] = "What limits the comparison of these connections?"
        with self.assertRaisesRegex(engine.ValidationError, "revision_reason"):
            quality.import_plan(self.c, value, CTX)
        value["revision_reason"] = "Clarify the engineering question after source review."
        quality.import_plan(self.c, value, CTX)
        self.assertIn("research_review_invalid", self.codes())
        with self.assertRaisesRegex(engine.ValidationError, "Stale research review: plan"):
            quality.import_research(self.c, old_result, CTX)
        del old_result["plan_hash"]
        with self.assertRaisesRegex(engine.ValidationError, "requires plan_hash and population_hash"):
            quality.import_research(self.c, old_result, CTX)
        event = self.c.execute("SELECT data FROM events WHERE kind='quality-record-superseded' ORDER BY id DESC").fetchone()
        self.assertEqual(json.loads(event[0])["previous"]["questions"][0]["question"], self.plan()["questions"][0]["question"])

    def test_unresolved_question_and_single_source_comparison_cannot_complete(self):
        quality.import_plan(self.c, self.plan(), CTX)
        value = self.research()
        value["evidence_ids"] = value["evidence_ids"][:1]
        with self.assertRaisesRegex(engine.ValidationError, "at least two"):
            quality.import_research(self.c, value, CTX)
        value = self.research()
        value["status"] = "insufficient_evidence"
        quality.import_research(self.c, value, CTX)
        self.assertIn("research_review_invalid", self.codes())

    def test_counterexample_not_found_is_valid_but_no_search_record_is_not(self):
        quality.import_plan(self.c, self.plan(), CTX)
        value = self.research()
        value["counterevidence"]["search_scope"] = ""
        with self.assertRaisesRegex(engine.ValidationError, "counterevidence"):
            quality.import_research(self.c, value, CTX)
        quality.import_research(self.c, self.research(), CTX)
        self.assertEqual(quality.validate(self.c, CTX)["coverage"]["research_questions_resolved"], 1)

    def test_legacy_database_without_quality_tables_is_readable_and_incomplete(self):
        for table in quality.TABLES:
            self.c.execute("DROP TABLE " + table)
        self.assertIn("research_plan_missing", self.codes())
        self.assertIn("semantic_review_missing", self.codes())

    def test_real_scope_cannot_disable_gate(self):
        run = engine.run_info(self.c)
        run["scope"].update(synthetic=False, require_research_quality=False)
        engine.set_meta(self.c, "run", run)
        self.assertIn("quality_gate_disabled", self.codes())

    def test_explicit_synthetic_opt_out_retains_fixture_compatibility(self):
        run = engine.run_info(self.c)
        run["scope"]["require_research_quality"] = False
        engine.set_meta(self.c, "run", run)
        self.assertEqual(quality.validate(self.c, CTX)["errors"], [])

    def test_review_inputs_require_explicit_exported_version_fingerprints(self):
        value = self.review()
        del value["analysis_fingerprint"]
        with self.assertRaisesRegex(engine.ValidationError, "requires the analysis_fingerprint"):
            quality.import_review(self.c, value, CTX)
        for field in ("plan_hash", "population_hash"):
            value = self.research()
            del value[field]
            with self.assertRaisesRegex(engine.ValidationError, "requires plan_hash and population_hash"):
                quality.import_research(self.c, value, CTX)

    def test_version_manifest_is_read_only_and_identifies_source_and_review_state(self):
        quality.import_plan(self.c, self.plan(), CTX)
        before = self.c.total_changes
        result = self.work()
        self.assertEqual(self.c.total_changes, before)
        item = result["semantic_reviews"][0]
        row = self.c.execute("SELECT * FROM documents WHERE id=?", (item["document_id"],)).fetchone()
        self.assertEqual(item["source_text_hash"], row["text_hash"])
        self.assertEqual(item["analysis_author"], "synthetic-author")
        self.assertEqual(item["review_state"], "pending")
        self.assertEqual(item["evidence_ids"], ["evidence-" + item["application_id"]])
        self.assertNotIn("text", item["source_references"][0])
        self.assertEqual(result["research_reviews"][0]["question"]["question"], self.plan()["questions"][0]["question"])
        self.complete()
        completed = self.work()
        self.assertTrue(all(x["review_state"] == "current_pass" for x in completed["semantic_reviews"]))
        self.assertEqual(completed["research_reviews"][0]["review_state"], "current_pass")

    def test_version_export_cannot_overwrite_the_database(self):
        with self.assertRaisesRegex(engine.ValidationError, "must not overwrite"):
            quality.export_work(self.c, self.fixture.dbpath, CTX)

    def test_version_export_rejects_database_hardlink_without_changing_source(self):
        target = self.fixture.directory / "database-alias.json"
        try:
            os.link(self.fixture.dbpath, target)
        except (OSError, NotImplementedError) as error:
            self.skipTest("Hard links unavailable on this test filesystem: " + str(error))
        before = self.fixture.dbpath.read_bytes()
        with self.assertRaisesRegex(engine.ValidationError, "must not overwrite"):
            quality.export_work(self.c, target, CTX)
        self.assertEqual(self.fixture.dbpath.read_bytes(), before)
        self.assertTrue(target.samefile(self.fixture.dbpath))
        self.assertEqual(self.c.execute("PRAGMA integrity_check").fetchone()[0], "ok")
        target.unlink()

    def test_version_export_protects_wal_shm_names_and_existing_wal_alias(self):
        for suffix in ("-wal", "-shm"):
            target = Path(str(self.fixture.dbpath) + suffix)
            # Windows can lock the SHM contents while still allowing stat; this
            # probe needs to establish protection without bypassing that lock.
            before = (target.stat().st_size, target.stat().st_mtime_ns) if target.exists() else None
            with self.assertRaisesRegex(engine.ValidationError, "must not overwrite"):
                quality.export_work(self.c, target, CTX)
            self.assertEqual((target.stat().st_size, target.stat().st_mtime_ns) if target.exists() else None, before)
        wal = Path(str(self.fixture.dbpath) + "-wal")
        if not wal.exists():
            return
        target = self.fixture.directory / "wal-alias.json"
        try:
            os.link(wal, target)
        except (OSError, NotImplementedError) as error:
            self.skipTest("Hard links unavailable on this test filesystem: " + str(error))
        before = wal.read_bytes()
        with self.assertRaisesRegex(engine.ValidationError, "must not overwrite"):
            quality.export_work(self.c, target, CTX)
        self.assertEqual(wal.read_bytes(), before)
        target.unlink()

    def test_manifest_replaces_normal_output_atomically_without_truncating_other_hardlinks(self):
        target = self.fixture.directory / "existing-work.json"
        original = self.fixture.directory / "other-file.txt"
        original.write_text("preserved original bytes", encoding="utf-8")
        try:
            os.link(original, target)
        except (OSError, NotImplementedError) as error:
            self.skipTest("Hard links unavailable on this test filesystem: " + str(error))
        quality.export_work(self.c, target, CTX)
        self.assertEqual(original.read_text(encoding="utf-8"), "preserved original bytes")
        self.assertFalse(target.samefile(original))
        self.assertIn("semantic_reviews", json.loads(target.read_text(encoding="utf-8")))
        self.assertEqual(list(self.fixture.directory.glob(".quality-export-*.tmp")), [])


if __name__ == "__main__":
    unittest.main()
