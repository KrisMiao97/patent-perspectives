"""Synthetic, offline checks for conservative snapshot interpretation."""
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("snapshot_comparison_test", ROOT / "scripts/compare_snapshots.py")
helper = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(helper)
sys.path.insert(0, str(ROOT / "tests"))
import test_integrity as integrity


def seal(value):
    body = {k: v for k, v in value.items() if k not in ("data_sha256", "snapshot_id", "captured_at")}
    value["data_sha256"] = helper.digest(body)
    value["snapshot_id"] = "snapshot-" + value["data_sha256"][:24]
    value["captured_at"] = "2026-10-25T00:00:00+00:00"
    return value


def fixture(cutoff="2020-12-31", observed="2021-01-01T00:00:00+00:00"):
    return seal({"schema_version": 1, "kind": helper.KIND,
                 "run": {"run_id": "synthetic", "company": "Synthetic Company", "publication_cutoff": cutoff},
                 "comparison_basis": {"company": "Synthetic Company", "entities_sha256": "entities", "scope_sha256": "scope",
                    "query_plan_sha256": "query-plan", "source_providers": ["Synthetic Provider"], "count_unit": "retained_publication_with_application_id", "registration_mapping_sha256": "none"},
                 "directory": {"complete": True, "page_observations": [{"query_id": "q1", "offset": 0, "raw_sha256": "source", "observed_at": observed}]},
                 "applications": {"a1": {"id": "a1", "population_status": "included", "filing_date": "2019-01-01"}},
                 "publications": {"CN100A": {"id": "CN100A", "application_id": "a1", "publication_date": "2020-01-01"}},
                 "legal_observations": [], "objects": {name: {} for name in ("documents", "evidence", "analyses", "insights", "relations")}})


class SnapshotComparisonTests(unittest.TestCase):
    def test_same_evidence_with_new_packaging_time_is_not_reobservation(self):
        first = fixture()
        second = copy.deepcopy(first)
        second["captured_at"] = "2026-11-01T00:00:00+00:00"
        result = helper.compare(first, second)
        self.assertTrue(result["comparability"]["same_data"])
        self.assertIsNone(result["counts"]["newly_published_documents"])
        self.assertIsNone(result["counts"]["legal_status_observation_changes"])
        self.assertEqual(result["changes"], [])

    def test_distinguishes_new_publications_from_newly_discovered_old_records(self):
        first = fixture()
        second = fixture("2021-12-31", "2022-01-01T00:00:00+00:00")
        second["publications"]["CN100B"] = {"id": "CN100B", "application_id": "a1", "publication_date": "2021-03-01"}
        second["publications"]["CN050A"] = {"id": "CN050A", "application_id": "a1", "publication_date": "2010-03-01"}
        result = helper.compare(first, seal(second))
        self.assertEqual(result["counts"]["newly_published_documents"], 1)
        self.assertEqual(result["counts"]["newly_discovered_old_publications"], 1)
        self.assertEqual(result["review_candidates"]["application_ids"], ["a1"])

    def test_no_publication_increment_without_complete_two_observations(self):
        for modification in ("incomplete", "missing-time", "same-time", "unknown-date", "pending-entity"):
            with self.subTest(modification=modification):
                first = fixture()
                second = fixture("2021-12-31", "2022-01-01T00:00:00+00:00")
                second["publications"]["CN100B"] = {"id": "CN100B", "application_id": "a1", "publication_date": "2021-03-01"}
                if modification == "incomplete": second["directory"]["complete"] = False
                if modification == "missing-time": second["directory"]["page_observations"][0]["observed_at"] = None
                if modification == "same-time": second["directory"]["page_observations"][0]["observed_at"] = "2021-01-01T00:00:00+00:00"
                if modification == "unknown-date": second["publications"]["CN100B"]["publication_date"] = None
                if modification == "pending-entity": second["applications"]["a1"]["population_status"] = "pending"
                result = helper.compare(first, seal(second))
                addition = next(x for x in result["changes"] if x["id"] == "CN100B")
                self.assertEqual(addition["category"], "added_record_pending_review")

    def test_changed_scope_is_not_new_business_activity(self):
        first = fixture()
        second = fixture("2021-12-31", "2022-01-01T00:00:00+00:00")
        second["comparison_basis"]["scope_sha256"] = "different-region"
        second["publications"]["CN100B"] = {"id": "CN100B", "application_id": "a1", "publication_date": "2021-03-01"}
        result = helper.compare(first, seal(second))
        self.assertIsNone(result["counts"]["newly_published_documents"])
        self.assertIn("scope_sha256", result["comparability"]["mismatched_fields"])
        self.assertEqual(result["changes"][0]["category"], "scope_or_source_membership_change")

    def test_legal_status_change_needs_same_source_and_later_actual_observation(self):
        first, second = fixture(), fixture()
        obs = {"id": "legal1", "publication_number": "CN100A", "application_id": "a1", "source_provider": "Provider",
               "observed_at": "2020-01-02T11:00:00+08:00", "status": "审中", "source_sha256": "raw1", "conflict": False}
        first["legal_observations"] = [obs]
        second["legal_observations"] = [dict(obs, id="legal2", observed_at="2020-02-02T11:00:00+08:00", status="有效", source_sha256="raw2")]
        result = helper.compare(seal(first), seal(second))
        self.assertEqual(result["counts"]["legal_status_observation_changes"], 1)
        self.assertEqual(result["changes"][0]["before"]["observed_at"], [obs["observed_at"]])
        second["legal_observations"][0]["observed_at"] = obs["observed_at"]
        result = helper.compare(first, seal(second))
        self.assertIsNone(result["counts"]["legal_status_observation_changes"])
        self.assertEqual(result["changes"][0]["category"], "legal_observation_pending_review")

    def test_date_only_overlap_is_not_ordered_as_two_observations(self):
        first, second = fixture(), fixture()
        obs = {"id": "legal1", "publication_number": "CN100A", "application_id": "a1", "source_provider": "Provider", "observed_at": "2020-01-02", "status": "审中"}
        first["legal_observations"] = [obs]
        second["legal_observations"] = [dict(obs, id="legal2", observed_at="2020-01-02T12:00:00+00:00", status="有效")]
        result = helper.compare(seal(first), seal(second))
        self.assertIsNone(result["counts"]["legal_status_observation_changes"])

    def test_evidence_changes_find_dependent_insights_without_declaring_them_wrong(self):
        first, second = fixture(), fixture()
        first["objects"]["evidence"]["e1"] = {"sha256": "old", "application_ids": ["a1"], "evidence_ids": []}
        second["objects"]["evidence"]["e1"] = {"sha256": "new", "application_ids": ["a1"], "evidence_ids": []}
        second["objects"]["insights"]["i1"] = {"sha256": "insight", "application_ids": ["a1"], "evidence_ids": ["e1"]}
        result = helper.compare(seal(first), seal(second))
        self.assertEqual(result["review_candidates"]["evidence_ids"], ["e1"])
        self.assertEqual(result["review_candidates"]["insight_ids"], ["i1"])

    def test_existing_publication_correction_finds_application_and_unchanged_insight(self):
        first, second = fixture(), fixture()
        insight = {"sha256": "unchanged-insight", "application_ids": ["a1"], "evidence_ids": []}
        first["objects"]["insights"]["i1"] = insight
        second["objects"]["insights"]["i1"] = copy.deepcopy(insight)
        second["publications"]["CN100A"]["publication_date"] = "2020-02-01"
        result = helper.compare(seal(first), seal(second))
        self.assertEqual(len(result["changes"]), 1)
        self.assertEqual(result["changes"][0]["category"], "record_correction_or_enrichment_review")
        self.assertEqual(result["review_candidates"]["application_ids"], ["a1"])
        self.assertEqual(result["review_candidates"]["insight_ids"], ["i1"])

    def test_corrected_publication_association_tracks_both_applications(self):
        first, second = fixture(), fixture()
        for value in (first, second):
            value["applications"]["a2"] = {"id": "a2", "population_status": "included"}
            for appid in ("a1", "a2"):
                value["objects"]["insights"]["i-" + appid] = {"sha256": appid, "application_ids": [appid], "evidence_ids": []}
        second["publications"]["CN100A"]["application_id"] = "a2"
        result = helper.compare(seal(first), seal(second))
        self.assertEqual(result["review_candidates"]["application_ids"], ["a1", "a2"])
        self.assertEqual(result["review_candidates"]["insight_ids"], ["i-a1", "i-a2"])

    def test_application_and_source_table_changes_preserve_dependency_tracking(self):
        for table in ("applications", "documents", "analyses", "evidence", "relations"):
            with self.subTest(table=table):
                first, second = fixture(), fixture()
                insight = {"sha256": "unchanged-insight", "application_ids": ["a1"], "evidence_ids": ["e1"]}
                first["objects"]["insights"]["i1"] = insight
                second["objects"]["insights"]["i1"] = copy.deepcopy(insight)
                if table == "relations":
                    evidence = {"sha256": "unchanged-evidence", "application_ids": ["a1"], "evidence_ids": []}
                    first["objects"]["evidence"]["e1"] = evidence
                    second["objects"]["evidence"]["e1"] = copy.deepcopy(evidence)
                if table == "applications":
                    second[table]["a1"]["filing_date"] = "2019-02-01"
                else:
                    # Relations carry evidence dependencies, not necessarily a direct app list.
                    appids = [] if table == "relations" else ["a1"]
                    first["objects"][table]["e1"] = {"sha256": "old", "application_ids": appids, "evidence_ids": ["e1"]}
                    second["objects"][table]["e1"] = {"sha256": "new", "application_ids": appids, "evidence_ids": ["e1"]}
                result = helper.compare(seal(first), seal(second))
                self.assertEqual(result["review_candidates"]["insight_ids"], ["i1"])
                self.assertEqual(result["review_candidates"]["application_ids"], ["a1"])

    def test_detects_tampered_snapshot_and_rejects_presentation_manifest(self):
        first = fixture()
        second = copy.deepcopy(first)
        second["run"]["company"] = "tampered"
        with self.assertRaises(helper.SnapshotError): helper.compare(first, second)
        with self.assertRaises(helper.SnapshotError): helper.compare(first, {"kind": "presentation", "packaged_at": "2026-10-25"})

    def test_json_publish_does_not_overwrite_checkpoint(self):
        with tempfile.TemporaryDirectory() as temp:
            out = Path(temp) / "snapshot.json"
            helper.write_new(out, {"value": 1})
            with self.assertRaises(helper.SnapshotError): helper.write_new(out, {"value": 2})
            self.assertEqual(json.loads(out.read_text()), {"value": 1})
            self.assertEqual([p.name for p in Path(temp).iterdir()], ["snapshot.json"])

    def test_snapshot_uses_read_only_database_and_retains_pending_record(self):
        fixture_case = integrity.IntegrityTests(methodName="test_missing_fulltext_never_completes_or_renders")
        fixture_case.setUp()
        try:
            fixture_case.seed()
            fixture_case.db.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            before = hashlib.sha256(fixture_case.dbpath.read_bytes()).hexdigest()
            result = helper.snapshot(fixture_case.dbpath)
            self.assertEqual(len(result["applications"]), 1)
            self.assertEqual(len(result["publications"]), 1)
            self.assertTrue(result["directory"]["complete"])
            self.assertIsNone(result["directory"]["page_observations"][0]["observed_at"])
            self.assertEqual(hashlib.sha256(fixture_case.dbpath.read_bytes()).hexdigest(), before)
            helper.validate_snapshot(result)
        finally:
            fixture_case.doCleanups()

    def test_receipt_is_bound_to_exact_page_and_time(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            receipt = {"acquired_at": "2026-10-24T10:00:00+08:00", "response": {"results": [], "total_search_result_count": 0}}
            source = root / "source.json"
            source.write_text(json.dumps(receipt), encoding="utf-8")
            manifest = root / "observations.json"
            entry = {"query_id": "q1", "offset": 0, "file": "source.json", "sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
                     "response_path": ["response"], "observed_at_path": ["acquired_at"]}
            manifest.write_text(json.dumps({"pages": [entry]}), encoding="utf-8")
            pages = [{"query_id": "q1", "offset": 0, "raw": receipt["response"]}]
            result = helper.collection_observations(pages, manifest, helper.load_engine())
            self.assertEqual(result[0]["observed_at"], receipt["acquired_at"])
            pages[0]["raw"] = {"results": [{"pn": "OTHER"}], "total_search_result_count": 1}
            with self.assertRaises(helper.SnapshotError): helper.collection_observations(pages, manifest, helper.load_engine())


if __name__ == "__main__":
    unittest.main()
