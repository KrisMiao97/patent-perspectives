"""Synthetic evidence/role contract checks; no provider calls or case data."""
import copy
import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('claim_comparison', ROOT / 'scripts/claim_comparison.py')
comparison = importlib.util.module_from_spec(spec)
spec.loader.exec_module(comparison)


def fixture():
    payload, details, cases, cells = {'patents': []}, {}, [], []
    for n in (1, 2):
        appid, docid, eid, pn = f'app-{n}', f'doc-{n}', f'evidence-{n}', f'ZZSYNTHETIC{n}A'
        text = '1. A synthetic housing holds a lens.\n2. A synthetic ring fixes the lens.'
        quote = 'synthetic housing'
        start = text.index(quote)
        payload['patents'].append({'id': appid})
        details[appid] = {'publication_numbers': [pn], 'publications': [{'publication_number': pn}],
                         'documents': [{'id': docid, 'publication_number': pn, 'document_type': 'claims',
                                        'version': 'synthetic-published', 'language': 'en', 'complete': True, 'text': text}],
                         'evidence': [{'id': eid, 'application_id': appid, 'document_id': docid, 'publication_number': pn,
                                       'version': 'synthetic-published', 'locator': {'claim_number': 1},
                                       'quote': quote, 'start': start, 'end': start + len(quote)}]}
        cases.append({'id': f'case-{n}', 'label': f'合成光学样例 {n}', 'application_id': appid, 'document_id': docid})
        cells.append({'case_id': f'case-{n}', 'state': 'disclosed', 'text': '合成壳体用于支撑镜片。', 'evidence_ids': [eid]})
    context = {'claim_comparisons': [{'id': 'synthetic-elements', 'mode': 'applications', 'title': '合成要素对照',
                                     'summary': '仅用于行为检查，不是真实专利。', 'scope': '两件合成独立申请的所引权利要求',
                                     'selection_reason': '检查不同申请的同类要素及各自证据。', 'cases': cases,
                                     'rows': [{'id': 'housing', 'label': '镜片的支撑部件', 'category': 'components',
                                               'question': '由哪个部件支撑镜片？', 'cells': cells}]}]}
    return payload, details, context


class ClaimComparisonTests(unittest.TestCase):
    def test_optional_empty_comparisons(self):
        self.assertEqual(comparison.prepare({'patents': []}, {}, {})['groups'], [])

    def test_uses_exact_existing_source_identity(self):
        p, d, c = fixture()
        group = comparison.prepare(p, d, c)['groups'][0]
        e = group['rows'][0]['cells'][0]['evidence'][0]
        self.assertEqual((e['publication_number'], e['version'], e['claim_number']), ('ZZSYNTHETIC1A', 'synthetic-published', 1))
        self.assertEqual(group['cases'][0]['document']['text'][e['start']:e['end']], e['quote'])

    def test_cross_application_evidence_rejected(self):
        p, d, c = fixture()
        d['app-1']['evidence'].append(copy.deepcopy(d['app-2']['evidence'][0]))
        c['claim_comparisons'][0]['rows'][0]['cells'][0]['evidence_ids'] = ['evidence-2']
        with self.assertRaises(comparison.ClaimComparisonError): comparison.prepare(p, d, c)

    def test_cross_version_evidence_rejected(self):
        p, d, c = fixture()
        d['app-1']['evidence'][0]['version'] = 'synthetic-granted'
        with self.assertRaises(comparison.ClaimComparisonError): comparison.prepare(p, d, c)

    def test_wrong_publication_rejected(self):
        p, d, c = fixture()
        d['app-1']['evidence'][0]['publication_number'] = 'ZZSYNTHETIC1B'
        with self.assertRaises(comparison.ClaimComparisonError): comparison.prepare(p, d, c)

    def test_tampered_quote_rejected(self):
        p, d, c = fixture()
        d['app-1']['evidence'][0]['quote'] = 'imaginary housing'
        with self.assertRaises(comparison.ClaimComparisonError): comparison.prepare(p, d, c)

    def test_wrong_claim_locator_rejected(self):
        p, d, c = fixture()
        d['app-1']['evidence'][0]['locator']['claim_number'] = 2
        with self.assertRaises(comparison.ClaimComparisonError): comparison.prepare(p, d, c)

    def test_legacy_string_claim_locator_is_supported(self):
        p, d, c = fixture()
        d['app-1']['evidence'][0]['locator'] = '权利要求1'
        self.assertEqual(comparison.prepare(p, d, c)['groups'][0]['rows'][0]['cells'][0]['evidence'][0]['claim_number'], 1)

    def test_incomplete_and_rejected_claims_rejected(self):
        for patch in ({'complete': False}, {'rejection_review_ids': ['rejected-1']}, {'document_type': 'description'}):
            p, d, c = fixture()
            d['app-1']['documents'][0].update(patch)
            with self.assertRaises(comparison.ClaimComparisonError): comparison.prepare(p, d, c)

    def test_missing_numbered_claims_rejected(self):
        p, d, c = fixture()
        d['app-1']['documents'][0]['text'] = d['app-1']['documents'][0]['text'].replace('\n2.', '\n3.')
        with self.assertRaises(comparison.ClaimComparisonError): comparison.prepare(p, d, c)

    def test_disclosed_cell_without_evidence_rejected(self):
        p, d, c = fixture()
        c['claim_comparisons'][0]['rows'][0]['cells'][0]['evidence_ids'] = []
        with self.assertRaises(comparison.ClaimComparisonError): comparison.prepare(p, d, c)

    def test_not_disclosed_needs_full_reading_declaration(self):
        p, d, c = fixture()
        cell = c['claim_comparisons'][0]['rows'][0]['cells'][0]
        cell.update(state='not_disclosed', text='所引完整权利要求中未披露柔性密封。', evidence_ids=[])
        for reviewed in (None, [1], [1, 1, 2]):
            cell['reviewed_claim_numbers'] = reviewed
            with self.assertRaises(comparison.ClaimComparisonError): comparison.prepare(p, d, c)
        cell['reviewed_claim_numbers'] = [1, 2]
        self.assertEqual(comparison.prepare(p, d, c)['groups'][0]['rows'][0]['cells'][0]['state'], 'not_disclosed')

    def test_versions_require_same_application(self):
        p, d, c = fixture()
        c['claim_comparisons'][0]['mode'] = 'versions'
        with self.assertRaises(comparison.ClaimComparisonError): comparison.prepare(p, d, c)

    def test_unavailable_version_retains_identity_without_inventing_text(self):
        p, d, c = fixture()
        group = c['claim_comparisons'][0]
        group['mode'] = 'versions'
        d['app-1']['publications'].append({'publication_number': 'ZZSYNTHETIC1B'})
        group['cases'][1] = {'id': 'case-2', 'label': '合成授权版', 'application_id': 'app-1', 'publication_number': 'ZZSYNTHETIC1B'}
        group['rows'][0]['cells'][1] = {'case_id': 'case-2', 'state': 'not_acquired', 'text': '本版本完整权利要求尚未取得。'}
        result = comparison.prepare(p, d, c)['groups'][0]
        self.assertIsNone(result['cases'][1]['document'])
        self.assertEqual(result['rows'][0]['cells'][1]['evidence'], [])
        group['cases'][1]['publication_number'] = 'ZZUNRELATEDB'
        with self.assertRaises(comparison.ClaimComparisonError): comparison.prepare(p, d, c)

    def test_available_document_cannot_be_hidden_as_unavailable(self):
        p, d, c = fixture()
        c['claim_comparisons'][0]['cases'][0].update(document_id=None, publication_number='ZZSYNTHETIC1A')
        c['claim_comparisons'][0]['rows'][0]['cells'][0].update(state='not_acquired', evidence_ids=[])
        with self.assertRaises(comparison.ClaimComparisonError): comparison.prepare(p, d, c)

    def test_every_case_has_one_cell_and_group_ids_are_unique(self):
        p, d, c = fixture()
        c['claim_comparisons'][0]['rows'][0]['cells'][1]['case_id'] = 'case-1'
        with self.assertRaises(comparison.ClaimComparisonError): comparison.prepare(p, d, c)
        p, d, c = fixture()
        c['claim_comparisons'].append(copy.deepcopy(c['claim_comparisons'][0]))
        with self.assertRaises(comparison.ClaimComparisonError): comparison.prepare(p, d, c)

    def test_unicode_offsets_preserve_non_bmp_characters(self):
        p, d, c = fixture()
        doc = d['app-1']['documents'][0]
        doc['text'] = doc['text'].replace('A synthetic', 'A 🔬 synthetic', 1)
        e = d['app-1']['evidence'][0]
        e['start'] = doc['text'].index(e['quote']); e['end'] = e['start'] + len(e['quote'])
        result = comparison.prepare(p, d, c)['groups'][0]['rows'][0]['cells'][0]['evidence'][0]
        self.assertEqual(doc['text'][result['start']:result['end']], result['quote'])


if __name__ == '__main__': unittest.main()
