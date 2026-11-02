"""Audited semantic source rejection regressions; synthetic files only."""
import importlib.util
import json
from pathlib import Path
import unittest

import test_integrity as fixtures

engine = fixtures.engine
spec = importlib.util.spec_from_file_location('review_materializer_for_rejections', fixtures.ROOT / 'scripts/materialize_review.py')
materializer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(materializer)


class DocumentReviewTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.IntegrityTests(methodName='runTest')
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.c = self.fixture.db

    def rejection(self, doc, **changes):
        p = {'document_id': doc['document_id'], 'application_id': doc['application_id'], 'decision': 'reject',
             'reason_code': 'missing_formula', 'reason': 'Synthetic source omits a formula after the stated condition.',
             'reviewer': 'Synthetic host reviewer',
             'evidence': [{'quote': 'synthetic piston', 'locator': {'claim_number': 1}}]}
        p.update(changes)
        return p

    def reject(self, doc, **changes):
        with self.c:
            return engine.import_document_reviews(self.c, self.rejection(doc, **changes))

    def fresh_analysis(self, doc):
        p = self.fixture.analysis_input(doc)
        old = p['evidence'][0]['id']; new = old + '-corrected'
        p['evidence'][0]['id'] = new
        p['summary']['evidence_ids'] = [new]
        for values in p['fields'].values():
            for finding in values: finding['evidence_ids'] = [new]
        with self.c: engine.import_analysis(self.c, p)
        return new

    def test_reject_preserves_source_and_invalidates_existing_analysis_with_audit(self):
        self.fixture.complete_fixture()
        row = self.c.execute('SELECT * FROM documents').fetchone()
        before = dict(row); doc = {'document_id': row['id'], 'application_id': row['application_id']}
        self.reject(doc)
        after = dict(self.c.execute('SELECT * FROM documents').fetchone())
        self.assertEqual(before, after)
        self.assertTrue(json.loads(after['data'])['qualified'])
        analysis = engine.rows_data(self.c, 'analyses')[0]
        self.assertEqual(analysis['analysis_status'], 'invalidated_source_review')
        self.assertEqual(engine.rows_data(self.c, 'analysis_invalidations')[0]['previous_analysis']['analysis_status'], 'complete')
        self.assertEqual(len(engine.rows_data(self.c, 'document_reviews')), 1)
        self.assertFalse(engine.document_is_eligible(self.c, row))

    def test_rejected_source_cannot_import_complete_or_contribute_coverage_or_render(self):
        self.fixture.seed(); doc = self.fixture.document(); self.fixture.analyze(doc)
        self.reject(doc)
        with self.assertRaisesRegex(engine.ValidationError, 'rejected source'):
            self.fixture.analyze(doc)
        cov = engine.coverage(self.c)
        self.assertEqual((cov['technical_fulltext'], cov['technical_analyzed'], cov['technical_completion']), (0, 0, 0))
        self.assertEqual((cov['rejected_documents'], cov['invalidated_analyses']), (1, 1))
        self.assertIn('source_rejected', {x['code'] for x in engine.validate_run(self.c)['errors']})
        self.fixture.assert_blocked_render('semantic-rejection-blocked')
        output = self.fixture.directory / 'work.jsonl'
        self.assertEqual(engine.export_work(self.c, output)['work_items'], 0)
        self.assertEqual(output.read_text(encoding='utf-8'), '')

    def test_identical_text_cannot_escape_by_changing_version_label(self):
        self.fixture.seed(); doc = self.fixture.document(); self.reject(doc)
        relabeled = self.fixture.document(version='synthetic-different-label')
        self.assertNotEqual(doc['document_id'], relabeled['document_id'])
        row = self.c.execute('SELECT * FROM documents WHERE id=?', (relabeled['document_id'],)).fetchone()
        self.assertFalse(engine.document_is_eligible(self.c, row))
        with self.assertRaisesRegex(engine.ValidationError, 'rejected source'): self.fixture.analyze(relabeled)
        self.assertEqual(engine.coverage(self.c)['technical_fulltext'], 0)

    def test_rejected_description_falls_back_to_same_application_complete_claims(self):
        self.fixture.seed()
        desc = self.fixture.document(document_type='description', version='synthetic-desc',
                                     text='[0001]A synthetic piston connects a chamber.\n[0002]Missing formula after stated condition:')
        claims = self.fixture.document()
        with self.c:
            engine.import_analysis(self.c, self.fixture.analysis_input(desc, locator={'paragraph': '0001'}))
        self.reject(desc, reason_code='truncated_tail', evidence=[{'quote': 'Missing formula after stated condition:', 'locator': {'paragraph': '0002'}}])
        path = self.fixture.directory / 'fallback.jsonl'
        self.assertEqual(engine.export_work(self.c, path)['work_items'], 1)
        exported = json.loads(path.read_text(encoding='utf-8'))
        self.assertEqual(exported['document_id'], claims['document_id'])
        self.assertEqual(exported['source']['document_type'], 'claims')
        self.assertEqual(engine.coverage(self.c)['technical_analyzed'], 0)
        self.assertEqual(engine.coverage(self.c)['technical_fulltext'], 1)

    def test_new_complete_source_can_replace_invalid_analysis_while_rejection_stays(self):
        appid, _ = self.fixture.complete_fixture()
        old = self.c.execute('SELECT * FROM documents').fetchone()
        self.reject({'document_id': old['id'], 'application_id': appid})
        new = self.fixture.document(version='synthetic-corrected',
            text='1. A synthetic piston connects a chamber with an explicitly complete condition.\n2. The synthetic valve regulates the chamber.')
        eid = self.fresh_analysis(new)
        with self.c:
            engine.import_insights(self.c, [{**self.fixture.insight(role, appid), 'evidence_ids': [eid]} for role in engine.ROLES])
        report = engine.validate_run(self.c)
        self.assertEqual(report['status'], 'complete')
        self.assertEqual(report['coverage']['technical_analyzed'], 1)
        self.assertEqual(report['coverage']['rejected_documents'], 1)
        self.assertEqual(len(engine.rows_data(self.c, 'analysis_invalidations')), 1)
        self.assertEqual(len(engine.rows_data(self.c, 'document_reviews')), 1)
        _, details = engine.build_payload(self.c, report)
        olddetail = next(d for d in details[appid]['documents'] if d['id'] == old['id'])
        self.assertFalse(olddetail['complete'])
        self.assertTrue(olddetail['structurally_qualified'])
        self.assertTrue(olddetail['rejection_review_ids'])

    def test_rejected_evidence_cannot_support_new_role_or_relation(self):
        appid, _ = self.fixture.complete_fixture()
        row = self.c.execute('SELECT * FROM documents').fetchone()
        self.reject({'document_id': row['id'], 'application_id': appid})
        with self.assertRaisesRegex(engine.ValidationError, 'rejected source'):
            engine.import_insights(self.c, self.fixture.insight('rd', appid))
        with self.assertRaisesRegex(engine.ValidationError, 'rejected source'):
            engine.import_relations(self.c, {'id': 'synthetic-link', 'source': appid, 'target': appid,
                'type': 'synthetic', 'kind': 'inference', 'basis': 'Synthetic basis', 'evidence_ids': ['evidence-' + appid]})

    def test_old_relation_retaining_rejected_evidence_blocks_even_after_fallback(self):
        appid, _ = self.fixture.complete_fixture()
        with self.c:
            engine.import_relations(self.c, {'id': 'synthetic-link', 'source': appid, 'target': appid,
                'type': 'synthetic', 'kind': 'inference', 'basis': 'Synthetic basis', 'evidence_ids': ['evidence-' + appid]})
        old = self.c.execute('SELECT * FROM documents').fetchone()
        self.reject({'document_id': old['id'], 'application_id': appid})
        new = self.fixture.document(version='corrected', text='1. A synthetic piston connects a chamber with a full condition.\n2. The synthetic valve regulates the chamber.')
        eid = self.fresh_analysis(new)
        with self.c: engine.import_insights(self.c, [{**self.fixture.insight(role, appid), 'evidence_ids': [eid]} for role in engine.ROLES])
        self.assertIn('relation_evidence_missing', {x['code'] for x in engine.validate_run(self.c)['errors']})

    def test_no_acceptance_override_and_missing_reason_or_invented_evidence_rejected(self):
        self.fixture.seed(); doc = self.fixture.document()
        for change in ({'decision': 'accept'}, {'decision': 'approve'}, {'reason': ''}, {'reviewer': ''},
                       {'reason_code': 'manual_override'}, {'evidence': []},
                       {'evidence': [{'quote': 'invented missing text', 'locator': {'claim_number': 1}}]}):
            with self.assertRaises(engine.ValidationError): self.reject(doc, **change)
        self.assertEqual(engine.rows_data(self.c, 'document_reviews'), [])

    def test_rejection_binds_application_publication_and_source_hash(self):
        self.fixture.seed(); doc = self.fixture.document()
        for change in ({'application_id': 'OTHER'}, {'publication_number': 'CN900000002A'}, {'source_text_hash': 'wrong'}):
            with self.assertRaises(engine.ValidationError): self.reject(doc, **change)

    def test_duplicate_review_is_idempotent(self):
        self.fixture.seed(); doc = self.fixture.document(); self.fixture.analyze(doc)
        first = self.reject(doc); second = self.reject(doc)
        self.assertEqual(first['document_reviews'][0]['review_id'], second['document_reviews'][0]['review_id'])
        self.assertTrue(second['document_reviews'][0]['cached'])
        self.assertEqual(len(engine.rows_data(self.c, 'document_reviews')), 1)
        self.assertEqual(len(engine.rows_data(self.c, 'analysis_invalidations')), 1)

    def test_materializer_rejects_source_despite_true_tail_attestation(self):
        self.fixture.seed(); doc = self.fixture.document(); self.reject(doc)
        text = self.fixture.doc_input()['text']
        host = {'document_id': doc['document_id'], 'application_id': doc['application_id'],
                'read_chunk_ids': doc['chunk_ids'], 'tail_check': {'complete': True, 'quote': text[-40:]}}
        with self.assertRaisesRegex(engine.ValidationError, 'source rejection'): materializer.build(self.c, host, engine)

    def test_optional_rejection_check_does_not_migrate_readonly_old_schema(self):
        self.fixture.seed(); doc = self.fixture.document()
        self.c.execute('DROP TABLE document_reviews')
        row = self.c.execute('SELECT * FROM documents WHERE id=?', (doc['document_id'],)).fetchone()
        self.assertTrue(engine.document_is_eligible(self.c, row))
        self.assertIsNone(self.c.execute("SELECT 1 FROM sqlite_master WHERE name='document_reviews'").fetchone())

    def test_jsonl_unicode_line_separators_remain_inside_patent_string(self):
        path = self.fixture.directory / 'unicode-source.jsonl'
        values = [{'source': 'paragraph\u2028not-a-record\u0085still-source'}, {'source': 'claim\u2029inside-string'}]
        path.write_text('\n'.join(json.dumps(v, ensure_ascii=False) for v in values), encoding='utf-8')
        self.assertEqual(engine.read_input(path), values)

    def test_document_review_cli_uses_same_gate(self):
        appid, doc = self.fixture.complete_fixture()
        path = self.fixture.directory / 'reject.json'
        path.write_text(json.dumps(self.rejection(doc)), encoding='utf-8')
        value, code = engine.cli(['--db', str(self.fixture.dbpath), 'document-review-import', '--input', str(path)])
        self.assertEqual(code, 0)
        self.assertEqual(value['document_reviews'][0]['decision'], 'reject')
        self.assertEqual(engine.coverage(self.c)['technical_analyzed'], 0)


if __name__ == '__main__':
    unittest.main(verbosity=2)
