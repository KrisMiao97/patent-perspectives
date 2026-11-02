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


if __name__ == '__main__':
    unittest.main()
