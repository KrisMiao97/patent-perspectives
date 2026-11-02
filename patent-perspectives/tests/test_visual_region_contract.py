"""Synthetic pixels and text: regression checks for the explicit visual paths."""
import copy
import io
import json
import unittest
from PIL import Image
import test_integrity


class VisualRegionContractTests(unittest.TestCase):
    def setUp(self):
        self.e = test_integrity.engine
        self.m = self.e.original_claims_module()
        full = Image.new('RGB', (8, 8), 'white')
        full.putpixel((2, 2), (0, 0, 0))
        def png(im):
            out = io.BytesIO(); im.save(out, format='PNG'); return out.getvalue()
        self.full = png(full)
        self.crop = png(full.crop((1, 1, 4, 4)))
        self.bad_crop = png(Image.new('RGB', (3, 3), 'white'))
        self.source = {'publication_number': 'CN900000001A', 'normalization_notice': 'Synthetic transcription only',
            'original_document_proof': {'visual_region_transcriptions': 'regions', 'pdf': {'sha256': 'pdf'},
                                        'extraction': {'sha256': 'extraction'}}}
        self.region = {'id': 'image-1', 'kind': 'formula', 'page_number': 1, 'visually_verified': True,
            'rendering_sha256': 'page', 'page_start': 0, 'page_end': 3, 'transcription': 'x=1',
            'claim_number': 1, 'bbox': [1, 1, 4, 4], 'crop': 'crop'}
        self.proof = {'schema_version': 1, 'publication_number': self.source['publication_number'],
            'pdf_sha256': 'pdf', 'extraction_sha256': 'extraction', 'reviewer': 'Synthetic fixture',
            'reviewed_at': '2026-10-26', 'all_technical_regions_inventoried': True,
            'all_regions_actually_viewed': True, 'regions': [self.region]}
        self.review = {'embedded_claim_images': [{'id': 'image-1', 'kind': 'formula', 'page_number': 1}]}

    def check(self, mode, fn):
        self.proof['mode'] = mode
        def load(spec, label):
            return None, json.dumps(self.proof).encode() if spec == 'regions' else self.crop
        return fn(self.source, self.review, {'pages': [{'text': 'x=1'}]},
            [{'page_number': 1, 'page_start': 0, 'start': 0, 'end': 3}],
            [{'number': 1, 'start': 0, 'end': 3}], {1: ({'sha256': 'page'}, self.full)}, load, self.e)

    def paths(self):
        return [(self.m.VISUAL_MODE, self.m.verify_visual_regions),
                (self.m.WO_VISUAL_MODE, self.m.verify_wo_visual_regions)]

    def test_exact_transcription_and_pixels_accept_both_supported_paths(self):
        for mode, fn in self.paths():
            with self.subTest(mode=mode): self.assertEqual(self.check(mode, fn), 1)

    def test_wrong_pixels_are_rejected_even_with_same_size_and_declared_hash(self):
        self.crop = self.bad_crop
        for mode, fn in self.paths():
            with self.subTest(mode=mode), self.assertRaises(self.e.ValidationError): self.check(mode, fn)

    def test_wrong_claim_and_missing_inventory_are_rejected(self):
        for change in ('claim', 'inventory'):
            self.region['claim_number'] = 2 if change == 'claim' else 1
            self.review['embedded_claim_images'] = [] if change == 'inventory' else [
                {'id': 'image-1', 'kind': 'formula', 'page_number': 1}]
            for mode, fn in self.paths():
                with self.subTest(change=change, mode=mode), self.assertRaises(self.e.ValidationError): self.check(mode, fn)

    def test_changed_transcription_is_rejected(self):
        self.region['transcription'] = 'x=2'
        for mode, fn in self.paths():
            with self.subTest(mode=mode), self.assertRaises(self.e.ValidationError): self.check(mode, fn)


if __name__ == '__main__': unittest.main()
