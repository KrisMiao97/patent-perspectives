"""Delivery integration checks with isolated synthetic inputs only."""
import json
import tempfile
import unittest
from pathlib import Path

import test_integrity


class RenderDeliveryTests(unittest.TestCase):
    def setUp(self):
        self.fixture = test_integrity.IntegrityTests(
            methodName='test_missing_fulltext_never_completes_or_renders')
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.engine = test_integrity.engine
        self.appid = self.fixture.seed()[0]
        self.doc = self.fixture.document()
        self.fixture.analyze(self.doc)
        with self.fixture.db:
            self.engine.import_insights(self.fixture.db, [
                self.fixture.insight(role, self.appid) for role in self.engine.ROLES])

    def test_invalid_comparison_does_not_publish_and_can_retry(self):
        destination = self.fixture.directory / 'reader'
        with self.assertRaises(self.engine.ValidationError):
            self.engine.render(self.fixture.db, destination,
                report_context={'claim_comparisons': [{'id': 'invalid'}]})
        self.assertFalse(destination.exists())
        self.assertEqual(list(destination.parent.glob('.patent-report-*')), [])
        result = self.engine.render(self.fixture.db, destination)
        self.assertEqual(result['status'], 'complete')
        self.assertTrue((destination / 'ip-comparison.js').is_file())
        self.assertTrue((destination / 'ip-comparison.css').is_file())
        js = (destination / 'data/claim-comparisons.js').read_text(encoding='utf-8')
        self.assertIn('window.PP_CLAIM_COMPARISONS=', js)

    def test_existing_delivery_is_preserved(self):
        destination = self.fixture.directory / 'existing'
        destination.mkdir()
        sentinel = destination / 'keep.txt'
        sentinel.write_text('frozen delivery', encoding='utf-8')
        with self.assertRaises(self.engine.ValidationError):
            self.engine.render(self.fixture.db, destination)
        self.assertEqual(sentinel.read_text(encoding='utf-8'), 'frozen delivery')

    def test_shared_body_limits_and_scope_are_linked_in_render(self):
        source = self.fixture.db
        records = [dict(self.fixture.insight(role, self.appid), limitations=['仅限所引版本的文本记载'],
                        shared_fact={'id': 'shared', 'statement': '文献描述固定方式。'}) for role in self.engine.ROLES]
        self.engine.import_insights(source, records)
        accepted = self.engine.active_insights(source)
        for changed in ({'scope': '扩大到所有产品'}, {'limitations': ['']}, {'body': '已经实施并受专利有效保护'}):
            amended = dict(records[0], **changed)
            with self.assertRaises(self.engine.ValidationError):
                self.engine.import_insights(source, [amended])
        self.assertEqual(self.engine.active_insights(source), accepted)
        destination = self.fixture.directory / 'role-boundaries'
        self.engine.render(source, destination)
        self.assertTrue((destination / 'role-evidence.js').is_file())
        script = (destination / 'data' / 'bootstrap.js').read_text(encoding='utf-8')
        payload = json.loads(script.removeprefix('window.PP_DATA=').removesuffix(';\n'))
        self.assertEqual(payload['shared_role_facts']['shared']['statement'], '文献描述固定方式。')
        self.assertEqual({item['shared_fact_id'] for item in payload['insights']}, {'shared'})
        self.assertTrue(all(item['boundary']['versions'] for item in payload['insights']))

    def test_verified_coverage_uses_observations_instead_of_text_version(self):
        pending_author_metadata = {'publication_number':'TEST1A1','status':'审中','observation_ids':[]}
        grant_observation = {'publication_number':'TEST1B1','status':'有效','observation_ids':['retained-register-observation']}
        self.assertEqual(self.engine.observed_legal_status({'publication_observations':[pending_author_metadata]}), 'unknown')
        self.assertEqual(self.engine.observed_legal_status({'publication_observations':[pending_author_metadata, grant_observation]}), '有效')
        conflict = dict(grant_observation, observation_conflict=True)
        self.assertEqual(self.engine.observed_legal_status({'publication_observations':[conflict]}), 'unknown')


if __name__ == '__main__':
    unittest.main()
