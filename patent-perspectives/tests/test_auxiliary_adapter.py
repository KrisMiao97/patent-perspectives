"""Read-only cache adapter and all-or-nothing application regressions."""
import contextlib
import importlib.util
import io
import json
import sqlite3
import sys
import unittest
from unittest.mock import patch

import test_auxiliary as fixture_module

engine = fixture_module.engine
spec = importlib.util.spec_from_file_location('auxiliary_cache_adapter_tests', fixture_module.fixtures.ROOT / 'scripts/import_auxiliary_cache.py')
adapter = importlib.util.module_from_spec(spec); spec.loader.exec_module(adapter)


class AuxiliaryAdapterTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixture_module.AuxiliaryTests(methodName='runTest'); self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.f = self.fixture.f; self.c = self.fixture.c
        directory = self.f.directory / 'collector'; directory.mkdir()
        self.ledger_path = directory / 'ledger.sqlite'
        self.ledger = sqlite3.connect(self.ledger_path)
        self.addCleanup(self.ledger.close)
        self.ledger.executescript('CREATE TABLE calls(cache_key TEXT PRIMARY KEY,raw_file TEXT,arguments_json TEXT,status TEXT); CREATE TABLE publication_cache(tool TEXT,pn TEXT,cache_key TEXT,source_index INTEGER,status TEXT,acquired_at TEXT);')

    def cache(self, pn, source, p, index=0):
        key = pn
        self.ledger.execute('INSERT OR IGNORE INTO calls VALUES(?,?,?,?)', (key, '../' + source.name, json.dumps(p['source_request']['arguments']), 'ok'))
        self.ledger.execute('INSERT INTO publication_cache VALUES(?,?,?,?,?,?)', ('legal_status', pn, key, index, 'ok', '2026-10-21T02:00:00+00:00'))
        self.ledger.commit()

    def run_adapter(self, *extra):
        argv = ['import_auxiliary_cache.py', '--db', str(self.f.dbpath), '--ledger', str(self.ledger_path), '--tool', 'legal_status', *extra]
        stdout = io.StringIO()
        with patch.object(sys, 'argv', argv), contextlib.redirect_stdout(stdout): code = adapter.main()
        return code, json.loads(stdout.getvalue())

    def test_default_mode_is_readonly_even_with_valid_cache(self):
        self.f.seed(); p, _, source = self.fixture.envelope(); self.cache(self.f.record()['pn'], source, p)
        code, report = self.run_adapter()
        self.assertEqual((code, report['verified'], report['applied']), (0, 1, 0))
        self.assertFalse(report['run_database_modified'])
        self.assertEqual(engine.auxiliary_module().records(self.c), [])

    def test_one_bad_record_prevents_partial_apply_of_other_valid_record(self):
        self.f.seed([self.f.record(), self.f.record(2)])
        p, _, source = self.fixture.envelope()
        self.cache(self.f.record()['pn'], source, p)
        self.cache(self.f.record(2)['pn'], source, p)  # Wrong source index/PN, not an absent cache.
        code, report = self.run_adapter('--apply')
        self.assertEqual((code, report['verified'], report['applied']), (3, 1, 0))
        self.assertEqual(len(report['errors']), 1)
        self.assertEqual(engine.auxiliary_module().records(self.c), [])

    def test_apply_imports_only_verified_original_record(self):
        self.f.seed(); p, _, source = self.fixture.envelope(); self.cache(self.f.record()['pn'], source, p)
        code, report = self.run_adapter('--apply')
        self.assertEqual((code, report['verified'], report['applied']), (0, 1, 1))
        self.assertEqual(len(engine.auxiliary_module().records(self.c)), 1)
        self.assertEqual(self.ledger.execute('SELECT count(*) FROM publication_cache').fetchone()[0], 1)

    def test_unretained_cache_record_is_not_imported_as_a_new_patent(self):
        self.f.seed(); p, _, source = self.fixture.envelope(); self.cache('CN999999999A', source, p)
        code, report = self.run_adapter('--apply')
        self.assertEqual((code, report['selected'], report['applied']), (0, 0, 0))
        self.assertEqual(report['unretained_publications_skipped'], 1)
        self.assertEqual(self.c.execute('SELECT count(*) FROM publications').fetchone()[0], 1)


if __name__ == '__main__': unittest.main(verbosity=2)
