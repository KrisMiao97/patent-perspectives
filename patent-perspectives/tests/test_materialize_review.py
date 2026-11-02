"""Host-review contract regressions, using synthetic sources in memory only."""
import copy
import importlib.util
import json
from pathlib import Path
import sys
import unittest

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('materializer_under_test', ROOT / 'scripts/materialize_review.py')
materializer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(materializer)
engine = materializer.load_engine()


class MaterializeTests(unittest.TestCase):
    def setUp(self):
        self.c = engine.db_open(':memory:')
        self.addCleanup(self.c.close)
        engine.set_meta(self.c, 'run', {'scope': {'synthetic': True}, 'as_of_date': '2026-10-20'})
        self.text = ('[0001]Synthetic piston joins a chamber. Repeated phrase. Repeated phrase.\n'
                     '[0002]' + 'Synthetic filler for a genuinely multi-chunk fixture. ' * 160
                     + '\n[0003]The source ends here with a complete synthetic final sentence.')
        self.doc = self.document(1, 'description', self.text)
        self.claim_text = '1. Synthetic piston joins the chamber.\n2. Synthetic valve regulates the same chamber.'
        self.claim_doc = self.document(2, 'claims', self.claim_text, claim_count=2)

    def document(self, n, kind, text, **extra):
        raw = {'pn': 'CN99000000%dA' % n, 'apno': 'CN20200000000%d' % n,
               'patent_type': 'invention', 'original_assignee': 'Synthetic Fixture Only'}
        pub = engine.normalize_record(raw, 'synthetic')
        engine.merge_application(self.c, pub)
        self.c.execute('INSERT INTO queries(id,entity_id,kind,expected_count,request,complete) VALUES(?,?,?,?,?,?)',
                       ('synthetic-q' + str(n), 'synthetic', 'original', 1, '{}', 1))
        self.c.execute('INSERT INTO query_results VALUES(?,?)', ('synthetic-q' + str(n), pub['id']))
        request = {'publication_number': raw['pn'], 'returned_publication_number': raw['pn'],
                   'application_number': raw['apno'], 'document_type': kind,
                   'identity_verified': True, 'replace_by_related': False,
                   'complete': True, 'truncated': False, 'text': text,
                   'source_class': 'synthetic', 'source_provider': 'Synthetic fixture',
                   'source_url': 'https://example.test/synthetic', 'acquired_at': '2026-10-20T00:00:00Z',
                   'language': 'en', 'version': 'synthetic',
                   'completeness_basis': 'Synthetic fixture has explicitly delimited complete text.'}
        request.update(extra)
        return engine.import_document(self.c, request)

    def host(self, claims=False):
        doc = self.claim_doc if claims else self.doc
        text = self.claim_text if claims else self.text
        return {'application_id': doc['application_id'], 'document_id': doc['document_id'],
                'read_chunk_ids': doc['chunk_ids'],
                'tail_check': {'complete': True, 'quote': text[-50:],
                               'claim_number' if claims else 'paragraph_number': 2 if claims else 3},
                'primary_module': 'Synthetic mechanism', 'tags': ['synthetic'],
                'summary': {'text': 'Host authored technical summary, not machine generated.', 'evidence': ['p1']},
                'fields': {key: [{'text': 'Host authored ' + key, 'evidence': ['p1']}] for key in engine.FIELDS},
                'evidence': [{'key': 'p1', 'claim_number' if claims else 'paragraph_number': 1}],
                'limitations': ['Synthetic regression only; no actual patent or performance.']}

    def reject(self, host, message):
        with self.assertRaisesRegex(engine.ValidationError, message):
            materializer.build(self.c, host, engine)

    def test_exact_paragraph_and_all_host_findings_preserved(self):
        host = self.host()
        analysis, review = materializer.build(self.c, host, engine)
        quote = analysis['evidence'][0]
        self.assertEqual(quote['quote'], self.text[quote['start']:quote['end']])
        self.assertEqual(quote['locator'], {'paragraph': '0001'})
        self.assertEqual(analysis['summary']['text'], host['summary']['text'])
        for key in engine.FIELDS:
            self.assertEqual(analysis['fields'][key][0]['text'], host['fields'][key][0]['text'])
        self.assertEqual(review['source_characters'], len(self.text))
        self.assertEqual(engine.import_analysis(self.c, analysis)['analysis_status'], 'complete')

    def test_exact_claim_and_formal_import(self):
        analysis, _ = materializer.build(self.c, self.host(True), engine)
        self.assertEqual(analysis['evidence'][0]['quote'], '1. Synthetic piston joins the chamber.')
        self.assertEqual(analysis['evidence'][0]['locator'], {'claim_number': 1})
        self.assertEqual(engine.import_analysis(self.c, analysis)['text_basis'], 'claims')

    def test_missing_duplicate_and_nonarray_read_chunks(self):
        self.assertGreater(len(self.doc['chunk_ids']), 1)
        for value in (self.doc['chunk_ids'][:-1], self.doc['chunk_ids'] * 2, 'not-an-array', [None]):
            host = self.host(); host['read_chunk_ids'] = value
            self.reject(host, 'every actual source chunk')

    def test_false_tail_and_unconfirmed_tail_never_complete(self):
        for tail in ({'complete': True, 'quote': 'An invented ending that does not exist.'},
                     {'complete': False, 'quote': self.text[-50:]},
                     {'quote': self.text[-50:]}, None):
            host = self.host(); host['tail_check'] = tail
            self.reject(host, 'actual final text')

    def test_wrong_last_paragraph_or_claim_rejected(self):
        for claims in (False, True):
            host = self.host(claims)
            host['tail_check']['claim_number' if claims else 'paragraph_number'] = 1
            self.reject(host, 'actual final')

    def test_missing_wrong_type_or_boolean_paragraph_claim_rejected(self):
        for claims, selector, number in ((False, 'paragraph_number', 9999), (False, 'claim_number', 1),
                                         (True, 'claim_number', 3), (True, 'paragraph_number', 1),
                                         (False, 'paragraph_number', True), (True, 'claim_number', True)):
            host = self.host(claims); host['evidence'] = [{'key': 'p1', selector: number}]
            self.reject(host, 'Source (paragraph|claim) absent')

    def test_optional_quote_cannot_be_borrowed_from_other_paragraph_or_claim(self):
        for claims, quote in ((False, 'The source ends here'), (True, 'Synthetic valve')):
            host = self.host(claims); host['evidence'][0]['quote'] = quote
            self.reject(host, 'inside selected source interval')

    def test_optional_repeated_or_invalid_quote_rejected(self):
        for quote in ('Repeated phrase.', '', 3, None):
            host = self.host(); host['evidence'][0]['quote'] = quote
            self.reject(host, 'Optional quote')

    def test_explicit_source_span_cannot_lie_about_paragraph(self):
        host = self.host(); start = self.text.index('Synthetic piston')
        host['evidence'] = [{'key': 'p1', 'start': start, 'end': start + 16, 'locator': {'paragraph': '0002'}}]
        self.reject(host, 'specified paragraph')
        host['evidence'][0]['locator'] = {'paragraph': '0001'}
        self.assertEqual(materializer.build(self.c, host, engine)[0]['evidence'][0]['quote'], 'Synthetic piston')

    def test_explicit_source_span_cannot_lie_about_claim(self):
        host = self.host(True); start = self.claim_text.index('Synthetic piston')
        host['evidence'] = [{'key': 'p1', 'start': start, 'end': start + 16, 'locator': {'claim_number': 2}}]
        self.reject(host, 'specified claim')

    def test_selector_ambiguity_and_locator_override_rejected(self):
        host = self.host(); host['evidence'][0]['claim_number'] = 1
        self.reject(host, 'exactly one evidence selector')
        host = self.host(); host['evidence'][0]['locator'] = {'paragraph': '0002'}
        self.reject(host, 'do not override')

    def test_missing_end_invalid_spans_and_unverified_page_locator_rejected(self):
        for start, end, locator in ((0, None, {'source_span': True}), (True, 5, {'source_span': True}),
                                    (0, len(self.text) + 1, {'source_span': True}), (7, 19, {'page': 50})):
            host = self.host(); host['evidence'] = [{'key': 'p1', 'start': start, 'end': end, 'locator': locator}]
            self.reject(host, 'Unicode character indices|unverified page')

    def test_dangling_duplicate_or_nonarray_references_rejected(self):
        for refs in (['absent'], ['p1', 'p1'], 'p1', [None], []):
            host = self.host(); host['fields']['components'][0]['evidence'] = refs
            self.reject(host, 'Finding references')

    def test_fields_exactly_eight_and_only_arrays(self):
        for change in ('missing', 'extra', 'null', 'object', 'string'):
            host = self.host()
            if change == 'missing': del host['fields']['steps']
            elif change == 'extra': host['fields']['invented_field'] = []
            else: host['fields']['steps'] = {'null': None, 'object': {}, 'string': 'unknown'}[change]
            self.reject(host, 'eight fields|must be an array')

    def test_unknown_fields_remain_empty_and_have_limitation(self):
        host = self.host(); host['fields']['claimed_effects'] = []
        analysis, review = materializer.build(self.c, host, engine)
        self.assertEqual(analysis['fields']['claimed_effects'], [])
        self.assertEqual(review['fields_without_findings'], ['claimed_effects'])
        host['limitations'] = []
        self.reject(host, 'Explain undisclosed')

    def test_unknown_placeholder_is_not_a_disclosed_finding(self):
        for value in ('unknown', '未知', '未披露', 'N/A'):
            host = self.host(); host['fields']['claimed_effects'][0]['text'] = value
            self.reject(host, r'fields use \[\]')

    def test_inference_requires_human_basis_and_conditions(self):
        host = self.host(); f = host['fields']['technical_means'][0]; f['kind'] = 'inference'
        self.reject(host, 'explicit basis and conditions')
        f.update(basis='Synthetic host interpretation', conditions=['Only under stated synthetic assumption'])
        self.assertEqual(materializer.build(self.c, host, engine)[0]['fields']['technical_means'][0]['basis'], f['basis'])

    def test_invalid_tag_limitation_or_summary_values_rejected(self):
        for key, value in (('tags', 'tag'), ('tags', [None]), ('tags', ['duplicate', 'duplicate']),
                           ('limitations', 'unknown'), ('summary', None)):
            host = self.host(); host[key] = value
            self.reject(host, 'Host tags|Host limitations|Host-authored finding')

    def test_wrong_application_and_version_hash_rejected(self):
        host = self.host(); host['application_id'] = self.claim_doc['application_id']
        self.reject(host, 'source application/document mismatch')
        host = self.host(); host['source_text_hash'] = 'not-the-selected-version'
        self.reject(host, 'source text hash differs')

    def test_empty_source_choices_duplicate_keys_and_prebuilt_refs_rejected(self):
        host = self.host(); host['evidence'] = []
        self.reject(host, 'select original evidence')
        host = self.host(); host['evidence'] *= 2
        self.reject(host, 'Unique compact evidence key')
        host = self.host(); host['summary']['evidence_ids'] = ['invented']
        self.reject(host, 'not prebuilt evidence_ids')


if __name__ == '__main__':
    unittest.main(verbosity=2)
