"""Offline original-pixel delivery regressions; synthetic runs only."""
import copy
import hashlib
import json
from pathlib import Path
import unittest

import test_integrity as fixtures
import test_image_transcription as image_fixtures
import test_auxiliary as auxiliary_fixtures

engine = fixtures.engine
composer = image_fixtures.composer
PRIVATE = 'SYNTHETIC_PRIVATE_IMAGE_ACCESS_NEVER_PUBLIC'


class DocumentImageExportTests(unittest.TestCase):
    def setUp(self):
        self.f = image_fixtures.ImageTranscriptionTests(methodName='runTest')
        self.f.setUp()
        self.addCleanup(self.f.doCleanups)
        self.c, self.root = self.f.c, self.f.root

    def compose_and_analyze(self, shared=False, second_version=False):
        if shared:
            first, second = self.f.manifest['images']
            (self.root / second['file']).write_bytes((self.root / first['file']).read_bytes())
            second.update(sha256=first['sha256'], bytes=first['bytes'])
            self.f.payload['images'][1]['sha256'] = first['sha256']
            self.f.write_json(self.f.manifest_path, self.f.manifest)
            self.f.payload['image_manifest_sha256'] = composer.sha(self.f.manifest_path)
        composed = self.f.compose()
        # Deliberately private provenance is allowed in the source cache but
        # must never be included in the exported image or document objects.
        composed['embedded_image_review']['private_access'] = {
            'url':'https://example.test/pixels?X-Amz-Signature=' + PRIVATE,
            'source_raw_artifact':'private/' + PRIVATE + '.json',
            'endpoint':'https://example.test/' + PRIVATE,
        }
        with self.c:
            doc = engine.import_document(self.c, composed)
            if second_version:
                other = copy.deepcopy(composed)
                other['version'] += '-second-fixture-version'
                engine.import_document(self.c, other)
            data = self.f.fixture.analysis_input(doc, quote='synthetic beam')
            data['summary']['text'] = 'Synthetic beam and formula; not a real patent.'
            data['fields']['technical_means'][0]['text'] = 'Synthetic beam formula.'
            engine.import_analysis(self.c, data)
        self.refresh_insights(doc['application_id'])
        return doc, composed

    def refresh_insights(self, appid):
        with self.c:
            engine.import_insights(self.c, [self.f.fixture.insight(role, appid) for role in engine.ROLES])
        self.assertEqual(engine.validate_run(self.c)['status'], 'complete')

    def update_document(self, doc, change):
        row = self.c.execute('SELECT * FROM documents WHERE id=?', (doc['document_id'],)).fetchone()
        data = json.loads(row['data'])
        change(data)
        with self.c:
            self.c.execute('UPDATE documents SET data=? WHERE id=?', (engine.dump(data), doc['document_id']))
        self.refresh_insights(doc['application_id'])

    def assert_render_rejected_before_output(self, name, expected):
        output = self.root / name
        with self.assertRaisesRegex(engine.ValidationError, expected):
            engine.render(self.c, output)
        self.assertFalse(output.exists())

    @staticmethod
    def details(output):
        result = {}
        for file in (output / 'data').glob('details-*.js'):
            result.update(json.loads(file.read_text(encoding='utf-8').removeprefix('window.PP_registerDetails(').removesuffix(');\n')))
        return result

    def test_copy_shared_bytes_once_but_keep_each_document_and_image_identity(self):
        doc, composed = self.compose_and_analyze(shared=True, second_version=True)
        before = [tuple(r) for r in self.c.execute('SELECT * FROM documents ORDER BY id')]
        output = self.root / 'shared-offline'
        engine.render(self.c, output)
        files = list((output / 'document-images').glob('*'))
        self.assertEqual(len(files), 1)
        expected = self.f.manifest['images'][0]['sha256']
        self.assertEqual(files[0].name, expected + '.png')
        self.assertEqual(hashlib.sha256(files[0].read_bytes()).hexdigest(), expected)
        detail = self.details(output)[doc['application_id']]
        images = detail['images']
        self.assertEqual(len(images), 4)
        self.assertEqual(len({x['document_id'] for x in images}), 2)
        self.assertEqual({x['image_id'] for x in images}, {'image-one','image-two'})
        for image in images:
            self.assertEqual(image['publication_number'], self.f.pn)
            self.assertIn(image['image_id'], image['caption'])
            self.assertIn('原文嵌图（文字经人工转写）', image['caption'])
            self.assertEqual(image['image_role'], 'original_document_embedded_image')
            self.assertNotIn('source_url', image)
            self.assertNotIn('file', image)
        displayed = [d for d in detail['documents'] if d['id'] == doc['document_id']][0]
        self.assertEqual(displayed['normalization_notice'], composed['normalization_notice'])
        self.assertNotIn('embedded_image_review', displayed)
        for file in output.rglob('*'):
            if file.is_file() and file.suffix in ('.json','.js','.svg','.html'):
                self.assertNotIn(PRIVATE, file.read_text(encoding='utf-8'), str(file))
        self.assertEqual(before, [tuple(r) for r in self.c.execute('SELECT * FROM documents ORDER BY id')])

    def test_missing_and_same_length_changed_required_image_stop_formal_render(self):
        self.compose_and_analyze()
        file = self.root / self.f.manifest['images'][0]['file']
        original = file.read_bytes()
        file.unlink()
        self.assert_render_rejected_before_output('missing', 'unavailable inside')
        file.write_bytes(bytes((original[0] ^ 1,)) + original[1:])
        self.assert_render_rejected_before_output('changed', 'hash changed')

    def test_byte_count_and_container_proof_changes_are_rejected(self):
        doc, composed = self.compose_and_analyze()
        for field, value, message in (('bytes', 999, 'byte count'),
                                      ('container_check', {'format':'JPEG'}, 'container changed')):
            with self.subTest(field=field):
                self.update_document(doc, lambda d: d['embedded_image_review']['images'][0].update({field:value}))
                self.assert_render_rejected_before_output('wrong-' + field, message)
                self.update_document(doc, lambda d: d.update(embedded_image_review=copy.deepcopy(composed['embedded_image_review'])))

    def test_truncated_container_rejected_even_if_hash_and_size_redeclared(self):
        doc, _ = self.compose_and_analyze()
        file = self.root / self.f.manifest['images'][0]['file']
        file.write_bytes(file.read_bytes()[:-12])
        self.update_document(doc, lambda d: d['embedded_image_review']['images'][0].update(
            sha256=composer.sha(file), bytes=file.stat().st_size))
        self.assert_render_rejected_before_output('truncated', 'Incomplete PNG')

    def test_outside_drive_unc_and_symlink_paths_are_rejected(self):
        doc, composed = self.compose_and_analyze()
        outside = self.root.parent / (self.root.name + '-outside.png')
        outside.write_bytes(image_fixtures.png())
        self.addCleanup(outside.unlink, missing_ok=True)
        values = ['../' + outside.name, str(outside), 'C:relative.png', '\\\\server\\share\\image.png']
        link = self.root / 'outside-link.png'
        try:
            link.symlink_to(outside)
            values.append(link.name)
        except OSError:
            pass  # Windows without symlink privilege still exercises traversal/drive/UNC.
        for i, value in enumerate(values):
            with self.subTest(path=value):
                self.update_document(doc, lambda d: d['embedded_image_review']['images'][0].update(file=value))
                self.assert_render_rejected_before_output('outside-' + str(i), 'run directory')
                self.update_document(doc, lambda d: d.update(embedded_image_review=copy.deepcopy(composed['embedded_image_review'])))

    def test_wrong_publication_original_or_marker_cannot_be_attached(self):
        doc, composed = self.compose_and_analyze()
        changes = [lambda r: r.update(source_publication_number='CN900000002A'),
                   lambda r: r.update(source_document_id=doc['document_id']),
                   lambda r: r['images'][0].update(marker='not in this text')]
        for i, change in enumerate(changes):
            with self.subTest(index=i):
                self.update_document(doc, lambda d: change(d['embedded_image_review']))
                self.assert_render_rejected_before_output('identity-' + str(i), 'different publication|identity mismatch|marker')
                self.update_document(doc, lambda d: d.update(embedded_image_review=copy.deepcopy(composed['embedded_image_review'])))

    def test_copy_uses_the_prepared_verified_bytes_if_source_changes_later(self):
        self.compose_and_analyze()
        module = engine.document_images_module()
        records, blobs = module.prepare(self.c, {a['id'] for a in engine.included_applications(self.c)}, engine.auxiliary_context())
        self.assertTrue(records)
        for item in self.f.manifest['images']:
            (self.root / item['file']).write_bytes(b'changed after prepare')
        output = self.root / 'prepared-copy'
        output.mkdir()
        module.copy_verified(blobs, output, engine.auxiliary_context())
        for name, data in blobs.items():
            self.assertEqual((output / name).read_bytes(), data)

    def test_old_run_without_embedded_review_remains_usable(self):
        plain = fixtures.IntegrityTests(methodName='runTest')
        plain.setUp(); self.addCleanup(plain.doCleanups)
        appid, doc = plain.complete_fixture()
        output = plain.directory / 'no-embedded'
        engine.render(plain.db, output)
        self.assertFalse((output / 'document-images').exists())
        detail = self.details(output)[appid]
        self.assertEqual(detail['images'], [])
        self.assertNotIn('normalization_notice', next(d for d in detail['documents'] if d['id'] == doc['document_id']))

    def test_unverified_search_image_dictionaries_and_signed_urls_never_export(self):
        plain = fixtures.IntegrityTests(methodName='runTest')
        plain.setUp(); self.addCleanup(plain.doCleanups)
        record = plain.record(images=[{'url':'https://example.test/pixel.png?X-Amz-Signature=' + PRIVATE,
                                      'caption':'unverified search source', 'private_access':PRIVATE}],
                              reference_note='Preserve this other bibliographic source value')
        appid = plain.seed([record])[0]
        doc = plain.document(); plain.analyze(doc)
        with plain.db:
            engine.import_insights(plain.db, [plain.insight(role, appid) for role in engine.ROLES])
        before = [tuple(r) for r in plain.db.execute('SELECT * FROM publications')]
        self.assertIn(PRIVATE, before[0][-1])
        output = plain.directory / 'no-search-image-urls'
        engine.render(plain.db, output)
        detail = self.details(output)[appid]
        self.assertEqual(detail['images'], [])
        public_raw = detail['publications'][0]['metadata_original']
        self.assertNotIn('images', public_raw)
        self.assertEqual(public_raw['reference_note'], record['reference_note'])
        for file in output.rglob('*'):
            if file.is_file() and file.suffix in ('.json','.js','.svg','.html'):
                self.assertNotIn(PRIVATE, file.read_text(encoding='utf-8'), str(file))
        self.assertEqual(before, [tuple(r) for r in plain.db.execute('SELECT * FROM publications')])

    def test_outside_window_aux_and_embedded_images_are_not_copied(self):
        # Keep parent evidence and records, but exclude their image files from
        # the current filing-date delivery. A missing outside image cannot block it.
        doc, _ = self.compose_and_analyze()
        records = [self.f.fixture.record(), self.f.fixture.record(2, filing_date='2024-01-01')]
        for kind in ('original','current'):
            self.f.fixture.search(records, qid='window-' + kind, kind=kind)
            with self.c:engine.complete_query(self.c, 'window-' + kind)
        new = self.f.fixture.document(2)
        self.f.fixture.analyze(new)
        run = engine.run_info(self.c)
        run['scope']['analysis_window'] = {'basis':'filing_date','from':'2021-10-21','through':'2026-10-20'}
        with self.c:engine.set_meta(self.c, 'run', run)
        # A real cached representative-image observation belongs to the old app.
        aux = auxiliary_fixtures.AuxiliaryTests(methodName='runTest')
        aux.f, aux.c, aux.number = self.f.fixture, self.c, 0
        proposal, raw, _ = aux.envelope('abstract_image')
        image = self.root / 'outside-period-representative.png'
        image.write_bytes(image_fixtures.png(111))
        digest = composer.sha(image)
        proposal['local_image'] = {'relative_path':image.name,'sha256':digest,'source_image_number':'0001',
                                  'source_image_url':raw['response']['result']['structuredContent']['data'][0]['abstract_drawing']['path']}
        with self.c:engine.import_auxiliary(self.c, proposal)
        self.refresh_insights(new['application_id'])
        tables = ('publications','documents','evidence','auxiliary_records')
        before = {t:[tuple(r) for r in self.c.execute('SELECT * FROM ' + t)] for t in tables}
        for item in self.f.manifest['images']:(self.root / item['file']).unlink()
        output = self.root / 'window-only'
        engine.render(self.c, output)
        self.assertFalse((output / 'aux-images').exists())
        self.assertFalse((output / 'document-images').exists())
        self.assertEqual(set(self.details(output)), {new['application_id']})
        self.assertTrue(image.is_file())
        self.assertEqual(before, {t:[tuple(r) for r in self.c.execute('SELECT * FROM ' + t)] for t in tables})


if __name__ == '__main__':
    unittest.main(verbosity=2)
