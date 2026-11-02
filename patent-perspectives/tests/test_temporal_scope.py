"""Synthetic temporal membership and complete SQLite backup regressions."""
import copy
from contextlib import closing
import importlib.util
import json
from pathlib import Path
import sqlite3
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import temporal_scope as temporal
import derive_scope
import test_integrity as fixtures
engine = fixtures.engine

WINDOW = {'basis': 'filing_date', 'from': '2021-10-21', 'through': '2026-10-20'}


class TemporalScopeTests(unittest.TestCase):
    setUp = fixtures.IntegrityTests.setUp
    record = fixtures.IntegrityTests.record
    search = fixtures.IntegrityTests.search
    seed = fixtures.IntegrityTests.seed

    def window(self):
        run = engine.run_info(self.db)
        run['scope']['analysis_window'] = copy.deepcopy(WINDOW)
        with self.db:
            engine.set_meta(self.db, 'run', run)

    def change_dates(self, appid, application, publication, raw=None):
        with self.db:
            app = json.loads(self.db.execute('SELECT data FROM applications WHERE id=?', (appid,)).fetchone()[0])
            app['filing_date'] = application
            self.db.execute('UPDATE applications SET data=? WHERE id=?', (engine.dump(app), appid))
            for row in self.db.execute('SELECT id,data FROM publications WHERE application_id=?', (appid,)).fetchall():
                pub = json.loads(row['data'])
                pub['filing_date'] = publication
                pub['metadata_original'] = {'filing_date': raw if raw is not None else publication}
                self.db.execute('UPDATE publications SET data=? WHERE id=?', (engine.dump(pub), row['id']))

    def test_inclusive_boundaries_and_publication_date_is_not_basis(self):
        ids = self.seed([self.record(1, filing_date=WINDOW['from']),
                         self.record(2, filing_date=WINDOW['through']),
                         self.record(3, filing_date='2021-10-20', publication_date='2025-01-01')])
        self.window()
        self.assertEqual({x['id'] for x in engine.included_applications(self.db)}, set(ids[:2]))
        cov = engine.coverage(self.db)
        self.assertEqual(cov['candidate_applications'], 3)
        self.assertEqual(cov['included_applications'], 3)  # Identity total, never relabeled as a smaller search.
        self.assertEqual(cov['applications'], 2)
        self.assertEqual(cov['analysis_window']['selected_applications'], 2)
        after = temporal.decide('synthetic-after', [{'date': '2026-10-21'}], WINDOW)
        self.assertEqual(after['status'], 'outside')

    def test_all_conflicting_dates_inside_remain_selected_but_statistics_unknown(self):
        appid = self.seed([self.record(filing_date='2022-01-01')])[0]
        self.change_dates(appid, '2022-01-01', '2023-02-02')
        self.window()
        state = temporal.window_states(self.db)[appid]
        self.assertEqual(state['status'], 'included')
        self.assertTrue(state['date_conflict'])
        self.assertEqual(state['date_for_statistics'], 'unknown')
        self.assertIsNone(engine.included_applications(self.db)[0]['filing_date'])
        stored = json.loads(self.db.execute('SELECT data FROM applications WHERE id=?', (appid,)).fetchone()[0])
        self.assertEqual(stored['filing_date'], '2022-01-01')
        self.assertEqual(engine.coverage(self.db)['analysis_window']['selected_unknown_date_statistics'], 1)

    def test_cross_window_conflict_remains_pending_and_blocks_completion(self):
        appid = self.seed([self.record(filing_date='2022-01-01')])[0]
        self.change_dates(appid, '2022-01-01', '2021-10-20')
        self.window()
        self.assertEqual(engine.included_applications(self.db), [])
        report = engine.validate_run(self.db)
        self.assertIn('analysis_window_pending', {x['code'] for x in report['errors']})
        self.assertEqual(report['coverage']['analysis_window']['pending_application_ids'], [appid])

    def test_missing_dates_do_not_use_publication_or_priority(self):
        appid = self.seed([self.record(filing_date='2022-01-01', publication_date='2024-01-01')])[0]
        self.change_dates(appid, None, None)
        self.window()
        self.assertEqual(temporal.window_states(self.db)[appid]['reason'], 'missing_filing_date')

    def test_invalid_nonempty_raw_date_is_pending_even_with_good_canonical_date(self):
        appid = self.seed([self.record(filing_date='2022-01-01')])[0]
        self.change_dates(appid, '2022-01-01', '2022-01-01', '2022-02-30')
        self.window()
        self.assertEqual(temporal.window_states(self.db)[appid]['reason'], 'invalid_filing_date_observation')

    def test_bibliography_dates_and_original_application_reference_all_count(self):
        appid = self.seed([self.record(filing_date='2022-01-01')])[0]
        pn = self.record()['pn']
        bib = {'dates': {'filing_date': '2022-01-01'}, 'record_original': {'bibliographic_data': {'application_reference': {'date': 20211020}}}}
        with self.db:
            self.db.execute('INSERT INTO bibliographies VALUES(?,?,?,?,?)', ('synthetic-bib', pn, appid, engine.dump(bib), '[]'))
        self.window()
        self.assertEqual(temporal.window_states(self.db)[appid]['status'], 'pending')

    def test_outside_conflicts_do_not_become_selected_or_get_false_statistical_date(self):
        decision = temporal.decide('synthetic', [{'date': '2018-01-01'}, {'date': '2020-01-01'}], WINDOW)
        self.assertEqual(decision['status'], 'outside')
        self.assertEqual(decision['date_for_statistics'], 'unknown')

    def test_identity_exclusion_is_separate_from_time_membership(self):
        appid = self.seed([self.record(filing_date='2022-01-01')])[0]
        review = {'status': 'excluded', 'reason': 'Synthetic identity exclusion',
                  'candidate_snapshot_hash': engine.application_scope_snapshot(self.db, appid)}
        with self.db:
            self.db.execute('INSERT INTO population_reviews VALUES(?,?)', (appid, engine.dump(review)))
        self.window()
        cov = engine.coverage(self.db)
        self.assertEqual(cov['applications'], 0)
        self.assertEqual(cov['analysis_window']['identity_temporal_cross_counts'],
                         [{'identity_status': 'excluded', 'temporal_status': 'included', 'applications': 1}])

    def test_no_window_leaves_parent_population_unchanged(self):
        self.seed([self.record(1), self.record(2, filing_date='2022-01-01')])
        self.assertEqual(len(engine.included_applications(self.db)), 2)
        self.assertIsNone(engine.coverage(self.db)['analysis_window'])

    def test_backup_derivation_preserves_all_parent_rows_and_run_identity(self):
        self.seed([self.record(1), self.record(2, filing_date='2022-01-01')])
        self.db.commit()
        parent_run = copy.deepcopy(engine.run_info(self.db))
        parent_counts = derive_scope.table_counts(self.db)
        output = self.directory / 'child.sqlite'
        result = derive_scope.derive(self.dbpath, output, WINDOW, engine=engine)
        self.assertNotEqual(result['run_id'], parent_run['run_id'])
        self.assertEqual(engine.run_info(self.db), parent_run)
        self.assertEqual(derive_scope.table_counts(self.db), parent_counts)
        with closing(derive_scope.open_readonly(output)) as child:
            child_run = engine.run_info(child)
            self.assertEqual(child_run['parent_run_id'], parent_run['run_id'])
            self.assertEqual(child_run['scope']['analysis_window'], WINDOW)
            self.assertEqual(len(engine.included_applications(child)), 1)
            child_counts = derive_scope.table_counts(child)
            for table, count in parent_counts.items():
                if table not in ('meta', 'events'):
                    self.assertEqual(child_counts[table], count, table)
            self.assertEqual(child.execute('PRAGMA quick_check').fetchone()[0], 'ok')
        self.assertFalse(list(self.directory.glob('*.deriving-*')))

    def test_inspection_never_creates_child_and_overwrite_is_refused(self):
        self.seed([self.record(filing_date='2022-01-01')])
        self.db.commit()
        with closing(derive_scope.open_readonly(self.dbpath)) as source:
            summary, anomalies, decisions = derive_scope.inspect(source, WINDOW, engine=engine)
        self.assertEqual(summary['selected_applications'], 1)
        self.assertEqual(anomalies, [])
        self.assertEqual(len(decisions), 1)
        self.assertFalse((self.directory / 'child.sqlite').exists())
        with self.assertRaises(ValueError):
            derive_scope.derive(self.dbpath, self.dbpath, WINDOW, engine=engine)
        with self.assertRaises(ValueError):
            derive_scope.derive(self.dbpath, self.directory / 'other' / 'child.sqlite', WINDOW, engine=engine)

    def test_window_is_exact_and_cannot_extend_cutoff(self):
        for bad in ({**WINDOW, 'basis': 'publication_date'}, {**WINDOW, 'from': '2021-10'},
                    {**WINDOW, 'from': '2026-11-01'}, {**WINDOW, 'through': '2026-10-21'}):
            with self.assertRaises(ValueError):
                temporal.validate_window(bad, '2026-10-20')


if __name__ == '__main__':
    unittest.main()
