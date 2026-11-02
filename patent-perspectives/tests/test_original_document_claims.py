"""Synthetic proof checks; these fixtures are not actual patent-office PDFs."""
import copy
import hashlib
import json
import unittest
import test_integrity as f

engine = f.engine


class OriginalClaimsTests(unittest.TestCase):
    setUp = f.IntegrityTests.setUp
    record = f.IntegrityTests.record
    search = f.IntegrityTests.search
    seed = f.IntegrityTests.seed
    doc_input = f.IntegrityTests.doc_input
    analysis_input = f.IntegrityTests.analysis_input
    analyze = f.IntegrityTests.analyze

    def write(self, name, value):
        path = self.directory / name
        path.write_bytes(value if isinstance(value, bytes) else json.dumps(value).encode())
        return {'artifact': name, 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}

    def fixture(self, composite=False):
        record = self.record(pn='HK900000001B', apno='HK42022000001', authority='HK') if composite else self.record()
        self.seed([record])
        pn, ap = record['pn'], record['apno']
        header = 'CN900000009B' if composite else pn
        pdf = self.write('synthetic.pdf', b'%PDF-1.4\nSYNTHETIC NON-PDF PROOF FIXTURE\n%%EOF\n')
        body1 = '1. A synthetic piston connects a chamber.\n2. The synthetic'
        body2 = 'valve controls a chamber.\n3. A synthetic controller regulates pressure.'
        pages = [{'page_number': 1, 'text': pn + '\n' + ap + '\nSynthetic office'}]
        if composite:
            pages[0]['text'] += '\nSTANDARD PATENT (R) SPECIFICATION\nCN900000009B\nCN20220000009.5'
            pages.append({'page_number': 2, 'text': 'CN900000009B\n20220000009.5\n权利要求书2页'})
        first = len(pages) + 1
        pages.extend([{'page_number': first, 'text': header + '\nClaims 1/2\n' + body1 + '\nSYNTHETIC FOOTER'},
                      {'page_number': first+1, 'text': header + '\nClaims 2/2\n' + body2 + '\nSYNTHETIC FOOTER'}])
        extraction = self.write('pages.json', {'publication_number': pn, 'pdf_sha256': pdf['sha256'],
            'extraction_tool': 'SYNTHETIC fixture, not PDF parsing', 'page_count': len(pages), 'pages': pages})
        at = '2026-10-21T00:00:00Z'
        url = 'https://patentimages.storage.googleapis.com/ab/cd/ef/0123456789abcd/' + pn + '.pdf'
        receipt = self.write('receipt.json', {'status': 200, 'source_url': url, 'final_url': url,
            'sha256': pdf['sha256'], 'bytes': (self.directory/'synthetic.pdf').stat().st_size,
            'content_type': 'application/pdf', 'acquired_at': at})
        regions = []
        for i, body in enumerate([body1, body2]):
            page = pages[first+i-1]['text'];start = page.index(body);end = start+len(body)
            regions.append({'page_number': first+i, 'start': start, 'end': end,
                'omitted_before': page[:start], 'omitted_after': page[end:], 'omissions_are_headers_footers_only': True,
                'section_page_label': {'page_number': first+i, 'quote': 'Claims '+str(i+1)+'/2'},
                'publication_header': {'page_number': first+i, 'quote': header}})
        review = {'kind': 'host_original_patent_claims_review', 'result': 'complete_claims_confirmed',
            'reviewer': 'SYNTHETIC reviewer', 'reviewed_at': at, 'publication_number': pn,
            'pdf_sha256': pdf['sha256'], 'extraction_sha256': extraction['sha256'], 'language': 'en',
            'patent_office': 'HK' if composite else 'CN', 'visual_review_performed': True, 'all_claims_pages_reviewed': True,
            'missing_or_unreadable_content': False, 'embedded_claim_images': [], 'machine_translation_used': False,
            'identity': {key: {'page_number': 1, 'quote': value} for key, value in
                         [('publication', pn), ('application', ap), ('office', 'Synthetic office')]},
            'claim_count': 3, 'claim_text_regions': regions}
        if composite:
            review['incorporated_specification'] = {'kind': 'explicitly_incorporated_original_specification',
                'publication_number': header, 'application_number': 'CN202200000095', 'basis': 'SYNTHETIC same-PDF cover linkage',
                'container_document_kind': {'page_number': 1, 'quote': 'STANDARD PATENT (R) SPECIFICATION'},
                'cover_link': {'page_number': 1, 'quote': header},
                'application': {'page_number': 2, 'quote': '20220000009.5'},
                'cover_application': {'page_number': 1, 'quote': 'CN20220000009.5'},
                'embedded_publication': {'page_number': 2, 'quote': header},
                'claims_section_declaration': {'page_number': 2, 'quote': '权利要求书2页'}}
        renderings = [{'page_number': i, 'pdf_sha256': pdf['sha256'], 'visually_reviewed': True,
                       **self.write('synthetic-page-'+str(i)+'.png', b'\x89PNG\r\n\x1a\nSYNTHETIC PAGE '+str(i).encode())}
                       for i in range(1, len(pages)+1)]
        self.review = review
        self.extraction = json.loads((self.directory/'pages.json').read_text())
        return self.doc_input(publication_number=pn, returned_publication_number=pn, application_number=ap,
            source_class='original_patent_document_mirror',
            source_provider='SYNTHETIC original-publication mirror fixture', source_label=engine.original_claims_module().LABEL,
            source_url=url, acquired_at=at, version='synthetic-original-pdf',
            text=body1+'\n'+body2, claim_count=3,
            original_document_proof={'pdf': pdf, 'extraction': extraction, 'receipt': receipt,
                'review': self.write('review.json', review), 'reviewed_renderings': renderings})

    def check(self, source):
        return engine.original_claims_module().verify(self.db, source, engine.original_claims_context())

    def rereview(self, source):
        source['original_document_proof']['review'] = self.write('review.json', self.review)

    def test_verified_spans_keep_cross_page_claim_and_export_immutable_original_pdf(self):
        source = self.fixture()
        public, path = self.check(source)
        self.assertEqual(public['claim_page_locators'][1], {'claim_number': 2, 'pdf_pages': [2, 3]})
        with self.db:
            doc = engine.import_document(self.db, source)
        self.analyze(doc)
        appids = {a['id'] for a in engine.included_applications(self.db)}
        records, blobs = engine.original_claims_module().prepare(self.db, appids, engine.original_claims_context())
        out = self.directory/'moved-offline';engine.original_claims_module().copy_verified(blobs, out, engine.original_claims_context())
        local = out/records[doc['document_id']]['offline_pdf_path']
        self.assertEqual(local.read_bytes(), path.read_bytes())
        _, details = engine.build_payload(self.db, engine.validate_run(self.db), original_document_records=records)
        value = next(iter(details.values()))['documents'][0]['original_document']
        self.assertNotIn('artifact', json.dumps(value))
        self.assertNotIn('review.json', json.dumps(value))

    def test_other_publication_url_cannot_supply_same_family_claims(self):
        s = self.fixture();s['source_url'] = s['source_url'].replace(self.record()['pn'], 'CN900000009A')
        with self.assertRaises(engine.ValidationError):self.check(s)

    def test_source_cannot_be_marked_official_or_undisclosed_mirror(self):
        s = self.fixture();s['source_class'] = 'official'
        with self.assertRaises(engine.ValidationError):engine.import_document(self.db, s)
        s['source_class'] = 'original_patent_document_mirror';s['source_label'] = 'Official patent data'
        with self.assertRaises(engine.ValidationError):self.check(s)

    def test_missing_page_rendering_or_false_visual_review_is_rejected(self):
        s = self.fixture();s['original_document_proof']['reviewed_renderings'].pop()
        with self.assertRaises(engine.ValidationError):self.check(s)
        self.review['visual_review_performed'] = False;self.rereview(s)
        with self.assertRaises(engine.ValidationError):self.check(s)

    def test_dropped_cross_page_continuation_rejected_even_when_all_claim_numbers_remain(self):
        s = self.fixture();s['text'] = s['text'].replace('valve controls a chamber.\n', '')
        self.assertEqual(len(engine.claim_blocks(s['text'])), 3)
        with self.assertRaises(engine.ValidationError):self.check(s)

    def test_claim_page_total_and_count_must_match_review(self):
        s = self.fixture();self.review['claim_text_regions'][0]['section_page_label']['quote'] = 'Claims 2/2';self.rereview(s)
        with self.assertRaises(engine.ValidationError):self.check(s)

    def test_pdf_byte_change_is_rejected_at_render_preparation(self):
        s = self.fixture()
        with self.db:engine.import_document(self.db, s)
        with (self.directory/'synthetic.pdf').open('ab') as f:f.write(b'changed')
        with self.assertRaises(engine.ValidationError):
            engine.original_claims_module().prepare(self.db, {a['id'] for a in engine.included_applications(self.db)}, engine.original_claims_context())

    def test_changed_pdf_after_preparation_is_not_copied_under_old_digest(self):
        s = self.fixture()
        with self.db:engine.import_document(self.db, s)
        _, blobs = engine.original_claims_module().prepare(self.db, {a['id'] for a in engine.included_applications(self.db)}, engine.original_claims_context())
        with (self.directory/'synthetic.pdf').open('ab') as f:f.write(b'changed after preparation')
        with self.assertRaises(engine.ValidationError):
            engine.original_claims_module().copy_verified(blobs, self.directory/'should-not-exist', engine.original_claims_context())
        self.assertFalse((self.directory/'should-not-exist').exists())

    def test_translation_images_truncation_and_outside_cache_are_rejected(self):
        s = self.fixture()
        for key, value in [('machine_translation_used', True), ('embedded_claim_images', ['missing-formula']), ('missing_or_unreadable_content', True)]:
            old = self.review[key];self.review[key] = value;self.rereview(s)
            with self.assertRaises(engine.ValidationError):self.check(s)
            self.review[key] = old
        self.rereview(s)
        s['original_document_proof']['pdf']['artifact'] = '../synthetic.pdf'
        with self.assertRaises(engine.ValidationError):self.check(s)

    def test_incorporated_specification_cannot_be_inferred_without_cover_evidence(self):
        s = self.fixture();self.review['incorporated_specification'] = {'kind': 'explicitly_incorporated_original_specification',
            'publication_number': 'US9999999B2', 'basis': 'SYNTHETIC family link is insufficient',
            'cover_link': {'page_number': 1, 'quote': 'US9999999B2'}};self.rereview(s)
        with self.assertRaises(engine.ValidationError):self.check(s)

    def test_composite_hk_preserves_both_identities_and_cross_page_claims(self):
        s = self.fixture(composite=True);public, _ = self.check(s)
        self.assertEqual(public['publication_number'], 'HK900000001B')
        self.assertEqual(public['incorporated_specification']['publication_number'], 'CN900000009B')
        self.assertEqual(public['incorporated_specification']['application_number'], 'CN202200000095')
        self.assertEqual(public['claim_page_locators'][1]['pdf_pages'], [3, 4])

    def test_composite_wrong_embedded_kind_or_section_declaration_is_rejected(self):
        s = self.fixture(composite=True)
        self.review['incorporated_specification']['publication_number'] = 'CN900000009A';self.rereview(s)
        with self.assertRaises(engine.ValidationError):self.check(s)
        self.review['incorporated_specification']['publication_number'] = 'CN900000009B'
        self.review['incorporated_specification']['claims_section_declaration']['quote'] = '权利要求书3页';self.rereview(s)
        with self.assertRaises(engine.ValidationError):self.check(s)

    def russian_fixture(self):
        record = self.record(pn='RU2024999999A', apno='RU2024999999', authority='RU')
        self.seed([record]);pn = record['pn'];at = '2026-10-21T00:00:00Z'
        office = 'ФЕДЕРАЛЬНАЯ СЛУЖБА\nПО ИНТЕЛЛЕКТУАЛЬНОЙ СОБСТВЕННОСТИ'
        kind = '(12) ЗАЯВКА НА ИЗОБРЕТЕНИЕ';heading = '(57) Формула изобретения'
        body1 = '1. Синтетическая камера содержит первое'
        body2 = 'отверстие.\n2. Синтетический клапан закрыт.\n3. Синтетическая крышка открыта.'
        front='(19)\nRU\n(11)\n2024 999 999\n(13)\nA'
        prefix = pn+'\n'+front+'\n2024999999\n'+office+'\n'+kind+'\n06.12.2021 CN 202111111111.1\n'+heading+'\n'
        footer = lambda n:'\nСтр.: '+str(n)+'\n'+pn+'\nRU 2024 999999 A'
        pages = [{'page_number':1,'text':prefix+body1+footer(1)},
                 {'page_number':2,'text':body2+footer(2)}]
        pdf = self.write('ru-synthetic.pdf',b'%PDF-1.4\nSYNTHETIC NOT A REAL PDF\n%%EOF\n')
        extraction = self.write('ru-pages.json',{'publication_number':pn,'pdf_sha256':pdf['sha256'],
            'extraction_tool':'SYNTHETIC fixture','page_count':2,'pages':pages})
        url='https://patentimages.storage.googleapis.com/ab/cd/ef/0123456789abcd/'+pn+'.pdf'
        receipt=self.write('ru-receipt.json',{'status':200,'source_url':url,'final_url':url,
            'sha256':pdf['sha256'],'bytes':(self.directory/'ru-synthetic.pdf').stat().st_size,
            'content_type':'application/pdf','acquired_at':at})
        regions=[]
        for i,body in enumerate((body1,body2),1):
            text=pages[i-1]['text'];start=text.index(body);end=start+len(body)
            regions.append({'page_number':i,'start':start,'end':end,'omitted_before':text[:start],
                'omitted_after':text[end:],'omissions_are_headers_footers_only':True,
                'publication_header':{'page_number':i,'quote':pn},
                'printed_publication_page':{'page_number':i,'quote':'Стр.: '+str(i)}})
        self.review={'kind':'host_original_patent_claims_review','result':'complete_claims_confirmed',
            'reviewer':'SYNTHETIC reviewer','reviewed_at':at,'publication_number':pn,'pdf_sha256':pdf['sha256'],
            'extraction_sha256':extraction['sha256'],'language':'RU','patent_office':'RU',
            'visual_review_performed':True,'all_claims_pages_reviewed':True,'missing_or_unreadable_content':False,
            'embedded_claim_images':[],'machine_translation_used':False,'claim_count':3,
            'identity':{key:{'page_number':1,'quote':value} for key,value in
                [('publication',pn),('publication_front',front),('application','2024999999'),('office',office)]},
            'completeness_mode':'whole_ru_application_publication','all_pdf_pages_reviewed':True,
            'pdf_contains_only_bibliography_and_claims':True,'claim_text_regions':regions,
            'publication_kind':{'page_number':1,'quote':kind},'claims_heading':{'page_number':1,'quote':heading},
            'last_claim_tail':{'page_number':2,'claim_number':3,'quote':'3. Синтетическая крышка открыта.'}}
        renderings=[{'page_number':i,'pdf_sha256':pdf['sha256'],'visually_reviewed':True,
            **self.write('ru-page-'+str(i)+'.png',b'\x89PNG\r\n\x1a\nSYNTHETIC '+str(i).encode())} for i in (1,2)]
        self.extraction=json.loads((self.directory/'ru-pages.json').read_text())
        return self.doc_input(publication_number=pn,returned_publication_number=pn,application_number=record['apno'],
            language='RU',source_class='original_patent_document_mirror',source_provider='SYNTHETIC mirror',
            source_label=engine.original_claims_module().LABEL,source_url=url,acquired_at=at,
            version='synthetic-whole-ru-publication',text=body1+'\n'+body2,claim_count=3,
            original_document_proof={'pdf':pdf,'extraction':extraction,'receipt':receipt,
                'review':self.write('review.json',self.review),'reviewed_renderings':renderings})

    def test_whole_russian_a_publication_keeps_cross_page_claim_without_fake_fraction(self):
        s=self.russian_fixture();public,_=self.check(s)
        self.assertEqual(public['claim_page_locators'][0]['pdf_pages'],[1,2])
        self.assertEqual(public['completeness_mode'],'whole_ru_application_publication')
        self.assertNotIn('artifact',json.dumps(public))
        self.assertNotIn(str(self.directory),json.dumps(public))
        with self.db:doc=engine.import_document(self.db,s)
        self.assertTrue(doc['qualified'])

    def test_whole_russian_requires_all_pages_and_actual_visual_review(self):
        s=self.russian_fixture()
        self.review['all_pdf_pages_reviewed']=False;self.rereview(s)
        with self.assertRaises(engine.ValidationError):self.check(s)
        self.review['all_pdf_pages_reviewed']=True;self.review['claim_text_regions'].pop();self.rereview(s)
        with self.assertRaises(engine.ValidationError):self.check(s)

    def test_whole_russian_rejects_false_fraction_and_wrong_page_number(self):
        s=self.russian_fixture();r=self.review['claim_text_regions'][0]
        r['section_page_label']={'page_number':1,'quote':'1/2'};self.rereview(s)
        with self.assertRaises(engine.ValidationError):self.check(s)
        r.pop('section_page_label');r['printed_publication_page']['quote']='Стр.: 2';self.rereview(s)
        with self.assertRaises(engine.ValidationError):self.check(s)

    def test_whole_russian_rejects_dropped_claim_continuation_even_if_numbers_remain(self):
        s=self.russian_fixture();r=self.review['claim_text_regions'][1]
        r['start']=len('отверстие.\n');r['omitted_before']='отверстие.\n'
        s['text']=s['text'].replace('отверстие.\n','');self.rereview(s)
        self.assertEqual(len(engine.claim_blocks(s['text'])),3)
        with self.assertRaises(engine.ValidationError):self.check(s)

    def test_whole_russian_rejects_last_claim_cut_and_unread_tail(self):
        s=self.russian_fixture();self.review['last_claim_tail']['quote']='3. Синтетическая крышка';self.rereview(s)
        with self.assertRaises(engine.ValidationError):self.check(s)
        s=self.russian_fixture();r=self.review['claim_text_regions'][1];cut=len(' открыта.')
        r['end']-=cut;page=self.extraction['pages'][1]['text'];r['omitted_after']=page[r['end']:]
        s['text']=s['text'][:-cut];self.review['last_claim_tail']['quote']='3. Синтетическая крышка';self.rereview(s)
        with self.assertRaises(engine.ValidationError):self.check(s)

    def test_whole_russian_rejects_wrong_kind_language_office_or_unknown_mode(self):
        s=self.russian_fixture()
        for key,value in [('completeness_mode','unrestricted_whole_pdf'),('language','CN'),
                          ('pdf_contains_only_bibliography_and_claims',False)]:
            old=self.review[key];self.review[key]=value;self.rereview(s)
            with self.assertRaises(engine.ValidationError):self.check(s)
            self.review[key]=old
        self.review['publication_kind']['quote']='(12) ОПИСАНИЕ ИЗОБРЕТЕНИЯ';self.rereview(s)
        with self.assertRaises(engine.ValidationError):self.check(s)

    def test_whole_russian_cannot_take_unstructured_front_identity_or_foreign_office(self):
        s=self.russian_fixture();self.review['identity']['publication_front']['quote']='RU2024999999A';self.rereview(s)
        with self.assertRaises(engine.ValidationError):self.check(s)
        # A foreign-office record cannot opt into the RU whole-publication mode.
        s=self.russian_fixture()
        row=self.db.execute('SELECT data FROM publications WHERE id=?',(s['publication_number'],)).fetchone()
        meta=json.loads(row[0]);meta['authority']='HK'
        self.db.execute('UPDATE publications SET data=? WHERE id=?',(json.dumps(meta),s['publication_number']))
        self.review['patent_office']='HK';self.rereview(s)
        with self.assertRaises(engine.ValidationError):self.check(s)


if __name__ == '__main__':unittest.main()
