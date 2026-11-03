"""Review missing draft evidence and source-first packets, synthetic texts only."""
import copy
import json
import unittest

import test_research_quality as fixtures

engine, quality = fixtures.engine, fixtures.quality
CTX = engine.research_quality_context()


class IndependentReviewPacketTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.ResearchQualityTests(methodName="runTest")
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.c = self.fixture.c

    def omitted_condition(self):
        value = self.fixture.review()
        value["source_evidence"] = [{"id": "review-missing-condition",
            "document_id": self.fixture.docs[0]["document_id"],
            "quote": "The synthetic valve regulates the chamber.", "locator": {"claim_number": 2}}]
        value["evidence_ids"].append("review-missing-condition")
        value["checks"]["conditions"] = {"status": "fail", "basis": "The draft did not explain the second claim's valve condition.",
                                             "evidence_ids": ["review-missing-condition"]}
        value["result"] = "revise"
        return value

    def test_reviewer_records_omitted_original_without_modifying_draft(self):
        before = self.c.execute("SELECT * FROM analyses ORDER BY application_id").fetchall()
        evidence_count = self.c.execute("SELECT count(*) FROM evidence").fetchone()[0]
        value = self.omitted_condition()
        quality.import_review(self.c, value, CTX)
        stored = quality.records(self.c, "quality_reviews")[0]
        self.assertEqual(stored["analysis_fingerprint"], value["analysis_fingerprint"])
        self.assertEqual(stored["source_evidence"][0]["locator"], {"claim_number": 2})
        self.assertEqual([tuple(x) for x in before], [tuple(x) for x in self.c.execute("SELECT * FROM analyses ORDER BY application_id")])
        self.assertEqual(self.c.execute("SELECT count(*) FROM evidence").fetchone()[0], evidence_count)
        self.assertIn("semantic_review_invalid", {x["code"] for x in quality.validate(self.c, CTX)["errors"]})

    def test_review_cannot_pass_failed_check_or_use_other_patent_source(self):
        value = self.omitted_condition()
        value["result"] = "pass"
        with self.assertRaisesRegex(engine.ValidationError, "Failed check"):
            quality.import_review(self.c, value, CTX)
        value["result"] = "revise"
        value["source_evidence"][0]["document_id"] = self.fixture.docs[1]["document_id"]
        with self.assertRaisesRegex(engine.ValidationError, "same application and publication"):
            quality.import_review(self.c, value, CTX)

    def test_review_local_quote_must_match_its_claim_and_not_shadow_author_evidence(self):
        value = self.omitted_condition()
        value["source_evidence"][0]["locator"] = {"claim_number": 1}
        with self.assertRaisesRegex(engine.ValidationError, "specified claim"):
            quality.import_review(self.c, value, CTX)
        value = self.omitted_condition()
        value["source_evidence"][0]["id"] = value["evidence_ids"][0]
        with self.assertRaisesRegex(engine.ValidationError, "shadow"):
            quality.import_review(self.c, value, CTX)

    def test_reviewer_can_read_same_publication_description_not_quoted_in_draft(self):
        text = "[0001] A synthetic valve closes only when the chamber is pressurized."
        doc = self.fixture.fixture.document(document_type="description", text=text)
        value = self.omitted_condition()
        value["source_evidence"][0].update(document_id=doc["document_id"],
            quote="A synthetic valve closes only when the chamber is pressurized.", locator={"paragraph": "0001"})
        quality.import_review(self.c, value, CTX)
        stored = quality.records(self.c, "quality_reviews")[0]
        self.assertEqual(stored["source_evidence"][0]["source_type"], "description")

    def test_source_first_packet_contains_full_original_and_separate_draft(self):
        out = self.fixture.fixture.directory / "review-work.json"
        before = [tuple(x) for x in self.c.execute("SELECT * FROM analyses")]
        result = quality.export_work(self.c, out, CTX, review_packets=out.parent / "packets")
        manifest = json.loads(out.read_text(encoding="utf-8"))
        self.assertEqual(result["semantic_review_items"], 2)
        for item in manifest["semantic_reviews"]:
            from pathlib import Path
            source = json.loads(Path(item["review_packets"]["original_sources"]).read_text(encoding="utf-8"))
            draft = json.loads(Path(item["review_packets"]["draft_comparison"]).read_text(encoding="utf-8"))
            self.assertNotIn("analysis", source)
            self.assertNotIn("evidence_ids", source)
            self.assertNotIn("analysis_author", source)
            self.assertEqual(source["analysis_fingerprint"], draft["analysis_fingerprint"])
            original = self.c.execute("SELECT text FROM documents WHERE id=?", (item["document_id"],)).fetchone()[0]
            self.assertEqual(source["sources"][0]["text"], original)
            self.assertEqual(draft["analysis"]["application_id"], item["application_id"])
            self.assertEqual(source["material_availability"]["description"], "not_acquired_in_this_packet")
        self.assertEqual(before, [tuple(x) for x in self.c.execute("SELECT * FROM analyses")])
        self.assertEqual(quality.records(self.c, "quality_reviews"), [])

    def test_rejected_review_only_source_invalidates_record(self):
        text = "[0001] A synthetic valve closes only when the chamber is pressurized."
        doc = self.fixture.fixture.document(document_type="description", text=text)
        value = self.fixture.review()
        value["source_evidence"] = [{"id": "review-extra-source", "document_id": doc["document_id"],
            "quote": "A synthetic valve closes only when the chamber is pressurized.", "locator": {"paragraph": "0001"}}]
        value["evidence_ids"].append("review-extra-source")
        quality.import_review(self.c, value, CTX)
        self.assertEqual(quality.validate(self.c, CTX)["coverage"]["semantic_review_passed"], 1)
        engine.import_document_reviews(self.c, {"document_id": doc["document_id"], "decision": "reject",
            "reason_code": "missing_text", "reason": "Synthetic missing-source test.", "reviewer": "synthetic-reviewer",
            "evidence": [{"quote": "A synthetic valve", "locator": {"paragraph": "0001"}}]})
        self.assertEqual(quality.validate(self.c, CTX)["coverage"]["semantic_review_passed"], 0)


if __name__ == "__main__":
    unittest.main()
