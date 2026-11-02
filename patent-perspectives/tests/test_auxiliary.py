"""Source-bound auxiliary behavior using synthetic cached envelopes only."""
import base64
import copy
import hashlib
import json
import unittest

import test_integrity as fixtures

engine = fixtures.engine
SIGNATURE = 'SYNTHETIC_SIGNED_URL_MUST_STAY_PRIVATE'


class AuxiliaryTests(unittest.TestCase):
    def setUp(self):
        self.f = fixtures.IntegrityTests(methodName='runTest'); self.f.setUp()
        self.addCleanup(self.f.doCleanups); self.c = self.f.db; self.number = 0

    def envelope(self, kind='legal_status', records=None, stamp='2026-10-21T02:00:00+00:00', requested=None):
        pn = self.f.record()['pn']
        if records is None:
            if kind == 'legal_status': records = [{'pn': pn, 'simple_legal_status': ['有效']}]
            elif kind == 'family': records = [{'pn': pn, 'patent_family': {
                'simple_family': [{'country': 'CN', 'doc_number': '900000001', 'kind': 'A', 'sequence': 1}, {'country': 'CN', 'doc_number': '900000002', 'kind': 'A', 'sequence': 2}],
                'simple_family_id': 11,
                'inpadoc_family': [{'country': 'CN', 'doc_number': '900000001', 'kind': 'A', 'sequence': 1}], 'inpadoc_family_id': 22,
                'patsnap_family': [{'country': 'US', 'doc_number': '99999999', 'kind': 'A1', 'sequence': 1}], 'patsnap_family_id': 33}}]
            else: records = [{'pn': pn, 'abstract_drawing': {'num': '0001', 'path': 'https://example.test/drawing.png?X-Amz-Signature=' + SIGNATURE}}]
        argument = requested or ','.join(r['pn'] for r in records)
        raw = {'tool': kind, 'arguments': {'patent_number': argument}, 'acquired_at': stamp, 'status': 'ok',
               'response': {'result': {'isError': False, 'structuredContent': {'success': True, 'error_code': 0, 'data': records}}}}
        self.number += 1; artifact = self.f.directory / ('source-' + str(self.number) + '.json')
        artifact.write_text(json.dumps(raw, ensure_ascii=False), encoding='utf-8')
        p = {'kind': kind, 'publication_number': records[0]['pn'], 'source_artifact': artifact.name,
             'source_request': {'tool': kind, 'arguments': {'patent_number': argument}},
             'request_tool_path': ['tool'], 'request_arguments_path': ['arguments'],
             'response_path': ['response', 'result', 'structuredContent'], 'record_index': 0}
        return p, raw, artifact

    def write(self, raw, path): path.write_text(json.dumps(raw, ensure_ascii=False), encoding='utf-8')

    def apply(self, p):
        with self.c: return engine.import_auxiliary(self.c, p)

    def test_actual_batch_identity_raw_hash_time_and_idempotent_storage(self):
        self.f.seed([self.f.record(), self.f.record(2)])
        p, _, path = self.envelope(records=[{'pn': self.f.record()['pn'], 'simple_legal_status': ['有效']}, {'pn': self.f.record(2)['pn'], 'simple_legal_status': ['失效']}])
        before = self.c.execute('SELECT data FROM publications ORDER BY id').fetchall()
        item = engine.prepare_auxiliary(self.c, p)
        self.assertEqual(item['artifact_sha256'], hashlib.sha256(path.read_bytes()).hexdigest())
        self.assertEqual(item['record_path'], ['response', 'result', 'structuredContent', 'data', 0])
        self.assertEqual(item['acquired_at'], '2026-10-21T02:00:00+00:00')
        self.assertIn('not reconstructed', item['temporal_basis'])
        self.apply(p); self.apply(p)
        self.assertEqual(len(engine.auxiliary_module().records(self.c)), 1)
        self.assertEqual([r[0] for r in before], [r[0] for r in self.c.execute('SELECT data FROM publications ORDER BY id')])

    def test_batch_cannot_be_replaced_by_fabricated_single_request_or_concatenated_pn(self):
        self.f.seed([self.f.record(), self.f.record(2)])
        p, _, _ = self.envelope(records=[{'pn': self.f.record()['pn'], 'simple_legal_status': ['有效']}, {'pn': self.f.record(2)['pn'], 'simple_legal_status': ['失效']}])
        wrong = copy.deepcopy(p); wrong['source_request']['arguments']['patent_number'] = self.f.record()['pn']
        with self.assertRaisesRegex(engine.ValidationError, 'actual cached tool'): engine.prepare_auxiliary(self.c, wrong)
        wrong = copy.deepcopy(p); wrong['publication_number'] = self.f.record()['pn'] + self.f.record(2)['pn']
        with self.assertRaises(engine.ValidationError): engine.prepare_auxiliary(self.c, wrong)

    def test_wrong_pn_index_kind_paths_duplicate_records_and_outer_errors_rejected(self):
        self.f.seed([self.f.record(), self.f.record(2)])
        p, raw, path = self.envelope()
        for change in ({'record_index': True}, {'record_index': 1}, {'kind': 'family'}, {'record_path': ['wrong']}):
            with self.assertRaises(engine.ValidationError): engine.prepare_auxiliary(self.c, {**p, **change})
        modified = copy.deepcopy(raw); modified['response']['result']['structuredContent']['data'][0]['pn'] = self.f.record(2)['pn']; self.write(modified, path)
        with self.assertRaisesRegex(engine.ValidationError, 'different publication'): engine.prepare_auxiliary(self.c, p)
        modified = copy.deepcopy(raw); modified['response']['result']['structuredContent']['data'] *= 2; self.write(modified, path)
        with self.assertRaisesRegex(engine.ValidationError, 'duplicate target'): engine.prepare_auxiliary(self.c, p)
        for error in ('tool', 'business', 'transport'):
            modified = copy.deepcopy(raw)
            if error == 'tool': modified['response']['result']['isError'] = True
            elif error == 'business': modified['response']['result']['structuredContent']['success'] = False
            else: modified['error'] = {'code': 401}
            self.write(modified, path)
            with self.assertRaisesRegex(engine.ValidationError, 'outer transport'): engine.prepare_auxiliary(self.c, p)

    def test_artifact_path_hash_and_acquisition_time_cannot_be_forged(self):
        self.f.seed(); p, raw, path = self.envelope()
        for change in ({'source_artifact': '../outside.json'}, {'artifact_sha256': 'wrong'}, {'acquired_at': '2026-10-20T00:00:00Z'}):
            with self.assertRaises(engine.ValidationError): engine.prepare_auxiliary(self.c, {**p, **change})
        del raw['acquired_at']; self.write(raw, path)
        with self.assertRaisesRegex(engine.ValidationError, 'acquisition time'): engine.prepare_auxiliary(self.c, {**p, 'acquired_at': '2026-10-20'})
        raw['acquired_date'] = '2026-10-21'; self.write(raw, path)
        self.assertEqual(engine.prepare_auxiliary(self.c, p)['acquired_time_precision'], 'date')

    def test_distinct_legal_states_of_same_application_aggregate_unknown(self):
        r1 = self.f.record(); r2 = self.f.record(2, apno=r1['apno'])
        self.f.seed([r1, r2])
        p, _, _ = self.envelope(records=[{'pn': r1['pn'], 'simple_legal_status': ['有效']}, {'pn': r2['pn'], 'simple_legal_status': ['失效']}])
        p2 = {**p, 'publication_number': r2['pn'], 'record_index': 1}
        self.apply([p, p2]); pubs, apps = engine.legal_status_snapshot(self.c)
        self.assertEqual(pubs[r1['pn']]['status'], '有效')
        self.assertEqual(pubs[r2['pn']]['status'], '失效')
        app = next(iter(apps.values())); self.assertEqual(app['status'], 'unknown'); self.assertTrue(app['conflict'])
        self.assertEqual(engine.coverage(self.c)['legal_status_conflict_applications'], 1)

    def test_latest_observation_selected_without_deleting_older_observation(self):
        self.f.seed(); first, _, _ = self.envelope(stamp='2026-10-21T02:00:00+00:00'); self.apply(first)
        second, _, _ = self.envelope(records=[{'pn': self.f.record()['pn'], 'simple_legal_status': ['失效']}], stamp='2026-10-21T11:00:00+08:00'); self.apply(second)
        pubs, _ = engine.legal_status_snapshot(self.c)
        self.assertEqual(pubs[self.f.record()['pn']]['status'], '失效')
        self.assertEqual(len(pubs[self.f.record()['pn']]['observation_ids']), 2)

    def test_unknown_and_multivalue_legal_statuses_never_invent_known_state(self):
        self.f.seed()
        for values in ([], ['mystery'], ['有效', '失效']):
            p, _, _ = self.envelope(records=[{'pn': self.f.record()['pn'], 'simple_legal_status': values}])
            self.assertEqual(engine.prepare_auxiliary(self.c, p)['normalized']['status'], 'unknown')
        p, _, _ = self.envelope(records=[{'pn': self.f.record()['pn'], 'simple_legal_status': ['未确认']}]); self.apply(p)
        pubs, _ = engine.legal_status_snapshot(self.c)
        self.assertEqual(pubs[self.f.record()['pn']]['status'], 'unknown')
        self.assertEqual(engine.coverage(self.c)['legal_status_known'], 0)

    def test_date_only_observation_is_not_assumed_earlier_than_same_day_timestamp(self):
        self.f.seed(); first, raw, path = self.envelope()
        del raw['acquired_at']; raw['acquired_date'] = '2026-10-21'; self.write(raw, path); self.apply(first)
        second, _, _ = self.envelope(records=[{'pn': self.f.record()['pn'], 'simple_legal_status': ['失效']}], stamp='2026-10-21T03:00:00+00:00'); self.apply(second)
        pubs, _ = engine.legal_status_snapshot(self.c)
        self.assertEqual(pubs[self.f.record()['pn']]['status'], 'unknown')
        self.assertTrue(pubs[self.f.record()['pn']]['observation_conflict'])
        self.assertEqual(len(pubs[self.f.record()['pn']]['selected_observation_ids']), 2)

    def test_three_family_definitions_and_member_paths_stay_separate(self):
        self.f.seed([self.f.record(), self.f.record(2)]); p, _, _ = self.envelope('family'); self.apply(p)
        item = engine.auxiliary_module().records(self.c)[0]
        self.assertEqual([item['normalized'][k]['family_id'] for k in ('simple', 'inpadoc', 'patsnap')], [11, 22, 33])
        self.assertEqual(item['normalized']['simple']['members'][1]['source_path'][-3:], ['patent_family', 'simple_family', 1])
        mapping = {r['id']: r['application_id'] for r in self.c.execute('SELECT id,application_id FROM publications')}
        edges = engine.auxiliary_module().family_relations([item], mapping)
        self.assertEqual(len(edges), 1); self.assertEqual(edges[0]['type'], 'family_simple')
        self.assertEqual(edges[0]['kind'], 'fact'); self.assertEqual(edges[0]['auxiliary_source_id'], item['id'])
        self.assertNotIn('transfer', edges[0]['type'])

    def test_signed_image_url_stays_private_and_unknown_offline_without_local_file(self):
        self.f.seed(); p, _, _ = self.envelope('abstract_image'); self.apply(p)
        item = engine.auxiliary_module().records(self.c)[0]
        self.assertIn(SIGNATURE, item['record_original']['abstract_drawing']['path'])
        self.assertNotIn(SIGNATURE, json.dumps(engine.auxiliary_module().public_record(item)))
        self.assertEqual(item['normalized']['availability'], 'remote_only')
        _, details = engine.build_payload(self.c, engine.validate_run(self.c))
        self.assertEqual(next(iter(details.values()))['images'], [])

    def test_bound_local_image_export_contains_no_signed_url(self):
        appid, _ = self.f.complete_fixture(); p, raw, _ = self.envelope('abstract_image')
        image = self.f.directory / 'one.png'
        image.write_bytes(base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aV1UAAAAASUVORK5CYII='))
        digest = hashlib.sha256(image.read_bytes()).hexdigest()
        p['local_image'] = {'relative_path': image.name, 'sha256': digest, 'source_image_number': '0001',
                            'source_image_url': raw['response']['result']['structuredContent']['data'][0]['abstract_drawing']['path']}
        bad = copy.deepcopy(p); bad['local_image']['source_image_url'] = 'https://example.test/wrong'
        with self.assertRaisesRegex(engine.ValidationError, 'exact returned drawing'): engine.prepare_auxiliary(self.c, bad)
        bad = copy.deepcopy(p); bad['local_image']['sha256'] = 'wrong'
        with self.assertRaisesRegex(engine.ValidationError, 'image source hash'): engine.prepare_auxiliary(self.c, bad)
        self.apply(p)
        with self.c: engine.import_insights(self.c, [self.f.insight(role, appid) for role in engine.ROLES])
        out = self.f.directory / 'public-render'; engine.render(self.c, out)
        self.assertTrue((out / 'aux-images' / (digest + '.png')).exists())
        for path in out.rglob('*'):
            if path.is_file() and path.suffix in ('.json', '.js', '.html', '.svg'):
                self.assertNotIn(SIGNATURE, path.read_text(encoding='utf-8'), str(path))
        self.assertEqual(engine.coverage(self.c)['abstract_image_local_publications'], 1)
        image.write_bytes(b'CHANGED, NO LONGER AN IMAGE')
        changed = self.f.directory / 'changed-image-render'
        engine.render(self.c, changed)
        self.assertFalse((changed / 'aux-images').exists())
        self.assertIn('previously imported local image files', (changed / 'data/bootstrap.js').read_text(encoding='utf-8'))

    def test_auxiliary_source_changes_invalidate_prior_role_snapshot(self):
        self.f.complete_fixture(); p, _, _ = self.envelope(); self.apply(p)
        errors = {x['code'] for x in engine.validate_run(self.c)['errors']}
        self.assertIn('stale_role_insight', errors)
        self.assertEqual(engine.coverage(self.c)['technical_analyzed'], 1)


if __name__ == '__main__': unittest.main(verbosity=2)
