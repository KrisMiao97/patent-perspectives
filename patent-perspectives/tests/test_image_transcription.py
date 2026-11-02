"""Source-tampering and all-image review regressions; temporary synthetic run only."""
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import sqlite3
import struct
import unittest
import zlib

import test_integrity as fixtures

engine=fixtures.engine
spec=importlib.util.spec_from_file_location('image_composer_under_test',fixtures.ROOT/'scripts/compose_image_transcription.py')
composer=importlib.util.module_from_spec(spec);spec.loader.exec_module(composer)


def png(value=0):
    def block(kind,data):return struct.pack('>I',len(data))+kind+data+struct.pack('>I',zlib.crc32(kind+data)&0xffffffff)
    return b'\x89PNG\r\n\x1a\n'+block(b'IHDR',struct.pack('>IIBBBBB',1,1,8,0,0,0,0))+block(b'IDAT',zlib.compress(bytes((0,value))))+block(b'IEND',b'')


class ImageTranscriptionTests(unittest.TestCase):
    def setUp(self):
        self.fixture=fixtures.IntegrityTests(methodName='runTest');self.fixture.setUp();self.addCleanup(self.fixture.doCleanups)
        self.c=self.fixture.db;self.root=self.fixture.directory;self.fixture.seed()
        self.pn=self.fixture.record()['pn']
        self.raw_html='<div num="1">1. A synthetic beam has S<L and a formula: <img src="https://example.test/patent/image-one.png?temporary=ignored" img-id="image-one"/></div><div num="2">2. A synthetic second formula: <IMG SRC=\'https://example.test/patent/image-two.png\' IMG-ID=\'image-two\'></div>'
        self.arguments={'patent_number':self.pn+',CN900000002A','replace_by_related':0}
        self.envelope={'tool':'claims','endpoint':'https://example.test/mcp','arguments':self.arguments,'cache_key':'synthetic-exact-batch','status':'ok','error_code':None,
            'response':{'jsonrpc':'2.0','id':1,'result':{'isError':False,'structuredContent':{'success':True,'error_code':0,'data':[
                {'pn':self.pn,'claim_count':2,'claims':[{'data_format':'original','lang':'en','claim_text':self.raw_html}]},
                {'pn':'CN900000002A','claim_count':2,'claims':[{'data_format':'original','lang':'en','claim_text':self.raw_html}]}]}}}}
        self.raw_path=self.root/'source-raw.json';self.manifest_path=self.root/'images.json'
        self.write_json(self.raw_path,self.envelope)
        images=[]
        for i,image_id in enumerate(('image-one','image-two')):
            path=self.root/(image_id+'.png');path.write_bytes(png(i))
            images.append({'image_id':image_id,'file':path.name,'source_image_path':'/patent/'+path.name,'status':'retrieved','bytes':path.stat().st_size,'sha256':composer.sha(path)})
        self.manifest={'publication_number':self.pn,'document_type':'claims','source_raw_artifact':self.raw_path.name,'source_sha256':composer.sha(self.raw_path),'images':images}
        self.write_json(self.manifest_path,self.manifest)
        self.doc=self.fixture.document(source_class='patsnap',source_provider='Patsnap synthetic fixture only',language='en',version='synthetic-original',
            text=composer.plain(self.raw_html),source_request={'tool':'claims','endpoint':self.envelope['endpoint'],'arguments':self.arguments},
            raw_artifact={'cache_key':self.envelope['cache_key'],'source_index':0})
        row=self.c.execute('SELECT * FROM documents WHERE id=?',(self.doc['document_id'],)).fetchone()
        self.payload={'document_id':row['id'],'publication_number':self.pn,'source_version':'synthetic-original','source_text_hash':row['text_hash'],
            'image_manifest':self.manifest_path.name,'image_manifest_sha256':composer.sha(self.manifest_path),'reviewer':'Synthetic visual reviewer','visual_review_complete':True,
            'images':[{'image_id':i['image_id'],'source_image_path':i['source_image_path'],'sha256':i['sha256'],'transcription':'x ≥ (a+b)/2 cot θ','visually_verified':True} for i in images]}

    @staticmethod
    def write_json(path,value):path.write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8')

    def update_raw_and_manifest(self,payload=None):
        self.write_json(self.raw_path,self.envelope)
        self.manifest['source_sha256']=composer.sha(self.raw_path)
        self.write_json(self.manifest_path,self.manifest)
        target=self.payload if payload is None else payload
        target['image_manifest_sha256']=composer.sha(self.manifest_path)

    def compose(self,payload=None):return composer.compose(self.c,self.payload if payload is None else payload,engine)

    def test_all_images_bound_and_new_marked_version_importable_without_mutating_original(self):
        before=dict(self.c.execute('SELECT * FROM documents WHERE id=?',(self.doc['document_id'],)).fetchone())
        result=self.compose()
        self.assertIn('S<L',result['text'])
        self.assertEqual(result['text'].count('【原文图片人工转写'),2)
        self.assertTrue(result['version'].endswith('-review-schema2'))
        self.assertNotEqual(result['version'],'synthetic-original')
        proof=result['embedded_image_review']
        self.assertEqual(proof['schema_version'],2)
        self.assertEqual(proof['source_record_path'],['response','result','structuredContent','data',0])
        self.assertEqual(proof['source_raw_sha256'],composer.sha(self.raw_path))
        self.assertEqual([x['number'] for x in result['claims']],[1,2])
        with self.c:new=engine.import_document(self.c,result)
        self.assertNotEqual(new['document_id'],before['id'])
        self.assertEqual(before,dict(self.c.execute('SELECT * FROM documents WHERE id=?',(before['id'],)).fetchone()))

    def test_all_images_must_be_reviewed_not_just_one_and_no_duplicate_review(self):
        for change in ('omit','duplicate','unverified'):
            p=copy.deepcopy(self.payload)
            if change=='omit':p['images'].pop()
            elif change=='duplicate':p['images'][1]=p['images'][0]
            else:p['images'][1]['visually_verified']=False
            with self.subTest(change=change),self.assertRaises(engine.ValidationError):self.compose(p)

    def typography_fixture(self,declared):
        raw=self.raw_html.replace('S<L','10<sup>4</sup>mm<sup>3</sup>/s and T<sub>n</sub> &lt; L')
        self.envelope['response']['result']['structuredContent']['data'][0]['claims'][0]['claim_text']=raw
        self.update_raw_and_manifest()
        extra={}
        if declared:
            extra={'normalization_transformations':[{'type':'html_superscript_subscript_preservation','policy_version':'supsub-v2',
                'representation':{'sup':'^{original content}','sub':'_{original content}'}}],
                'text_format_note':'Explicit typography extraction.'}
        text=composer.parsed(raw,preserve_typography=declared).text()
        doc=self.fixture.document(source_class='patsnap',source_provider='Patsnap synthetic fixture only',language='en',version='synthetic-supsub-v2' if declared else 'synthetic-flattened',
            text=text,source_request={'tool':'claims','endpoint':self.envelope['endpoint'],'arguments':self.arguments},
            raw_artifact={'cache_key':self.envelope['cache_key'],'source_index':0},**extra)
        row=self.c.execute('SELECT * FROM documents WHERE id=?',(doc['document_id'],)).fetchone()
        p=copy.deepcopy(self.payload);p.update(document_id=row['id'],source_version=json.loads(row['data'])['version'],source_text_hash=row['text_hash'])
        return p

    def test_image_composition_preserves_declared_superscripts_and_subscripts(self):
        result=self.compose(self.typography_fixture(True))
        self.assertIn('10^{4}mm^{3}/s and T_{n} < L',result['text'])
        self.assertEqual(result['text'].count('【原文图片人工转写'),2)
        self.assertIn('normalization_transformations',result)
        self.assertNotIn('104mm3/s',result['text'])
        with self.c:engine.import_document(self.c,result)

    def test_images_cannot_turn_a_flattened_exponent_source_into_complete_text(self):
        with self.assertRaisesRegex(engine.ValidationError,'sup/sub requires'):
            self.compose(self.typography_fixture(False))

    def test_empty_or_misnested_typography_is_not_repaired(self):
        for raw in ('x<sup> </sup>','x<sub></sub>','<sup><sub>2</sup></sub>'):
            with self.subTest(raw=raw),self.assertRaises(engine.ValidationError):
                composer.parsed(raw,engine,preserve_typography=True)

    def test_manifest_change_is_rejected_by_frozen_host_review_hash(self):
        self.manifest['images'][0]['source_image_path']='/another.png';self.write_json(self.manifest_path,self.manifest)
        with self.assertRaisesRegex(engine.ValidationError,'manifest hash'):self.compose()

    def test_changed_image_and_updated_manifest_cannot_rebind_previously_viewed_bytes(self):
        path=self.root/'image-one.png';path.write_bytes(png(255))
        self.manifest['images'][0].update(sha256=composer.sha(path),bytes=path.stat().st_size)
        self.write_json(self.manifest_path,self.manifest)
        self.payload['image_manifest_sha256']=composer.sha(self.manifest_path)
        with self.assertRaisesRegex(engine.ValidationError,'visually reviewed image hash'):self.compose()

    def test_truncated_png_rejected_even_with_updated_declared_hashes(self):
        path=self.root/'image-one.png';path.write_bytes(png()[:-12])
        self.manifest['images'][0].update(sha256=composer.sha(path),bytes=path.stat().st_size)
        self.payload['images'][0]['sha256']=composer.sha(path)
        self.write_json(self.manifest_path,self.manifest);self.payload['image_manifest_sha256']=composer.sha(self.manifest_path)
        with self.assertRaisesRegex(engine.ValidationError,'Incomplete PNG'):self.compose()

    def test_source_image_path_must_match_original_tag(self):
        self.manifest['images'][0]['source_image_path']='/invented.png'
        self.payload['images'][0]['source_image_path']='/invented.png'
        self.write_json(self.manifest_path,self.manifest);self.payload['image_manifest_sha256']=composer.sha(self.manifest_path)
        with self.assertRaisesRegex(engine.ValidationError,'Source image path'):self.compose()

    def test_raw_change_without_new_manifest_digest_is_rejected(self):
        self.envelope['response']['id']=2;self.write_json(self.raw_path,self.envelope)
        with self.assertRaisesRegex(engine.ValidationError,'cache hash changed'):self.compose()

    def test_provider_text_change_rejected_even_if_source_and_manifest_rehashed(self):
        self.envelope['response']['result']['structuredContent']['data'][0]['claims'][0]['claim_text']=self.raw_html.replace('S<L','S>L')
        self.update_raw_and_manifest()
        with self.assertRaisesRegex(engine.ValidationError,'every imported character'):self.compose()

    def test_request_publication_or_cache_identity_change_rejected(self):
        for key,value in (('arguments',{'patent_number':'CN900000002A','replace_by_related':0}),('tool','description'),('cache_key','other-cache'),('endpoint','https://other.example/mcp')):
            with self.subTest(key=key):
                saved=copy.deepcopy(self.envelope);self.envelope[key]=value;self.update_raw_and_manifest()
                with self.assertRaises(engine.ValidationError):self.compose()
                self.envelope=saved;self.update_raw_and_manifest()

    def test_wrong_actual_record_index_or_returned_pn_rejected(self):
        self.envelope['response']['result']['structuredContent']['data'][0]['pn']='CN900000002A';self.update_raw_and_manifest()
        with self.assertRaisesRegex(engine.ValidationError,'publication mismatch'):self.compose()

    def test_transport_business_and_truncation_flags_cannot_hide_behind_good_text(self):
        for change in ('transport','status','tool','business','truncated'):
            with self.subTest(change=change):
                saved=copy.deepcopy(self.envelope)
                if change=='transport':self.envelope['response']['error']={'code':-1}
                elif change=='status':self.envelope['status']='failed'
                elif change=='tool':self.envelope['response']['result']['isError']=True
                elif change=='business':self.envelope['response']['result']['structuredContent']['success']=False
                else:self.envelope['response']['result']['structuredContent']['data'][0]['truncated']=True
                self.update_raw_and_manifest()
                with self.assertRaises(engine.ValidationError):self.compose()
                self.envelope=saved;self.update_raw_and_manifest()

    def test_replacement_document_and_changed_text_or_version_rejected(self):
        for change in ('version','text'):
            with self.subTest(change=change):
                doc=self.fixture.document(source_class='patsnap',version='replacement-'+change,text=composer.plain(self.raw_html)+( ' Changed.' if change=='text' else ''))
                p=copy.deepcopy(self.payload);p['document_id']=doc['document_id']
                if change=='text':p['source_version']='replacement-'+change
                with self.assertRaisesRegex(engine.ValidationError,'source document, version or text hash'):self.compose(p)

    def test_source_database_text_hash_corruption_rejected(self):
        self.c.execute('UPDATE documents SET text=text || ? WHERE id=?',(' Changed.',self.doc['document_id']))
        with self.assertRaisesRegex(engine.ValidationError,'Stored source text integrity'):self.compose()

    def test_extra_manifest_image_and_source_duplicate_id_rejected(self):
        self.manifest['images'].append(copy.deepcopy(self.manifest['images'][0]));self.write_json(self.manifest_path,self.manifest)
        self.payload['image_manifest_sha256']=composer.sha(self.manifest_path)
        with self.assertRaisesRegex(engine.ValidationError,'Every embedded image'):self.compose()

    def test_duplicate_source_image_id_rejected_even_when_plain_text_is_identical(self):
        self.envelope['response']['result']['structuredContent']['data'][0]['claims'][0]['claim_text']=self.raw_html.replace("IMG-ID='image-two'","IMG-ID='image-one'")
        self.update_raw_and_manifest()
        with self.assertRaisesRegex(engine.ValidationError,'identity absent or duplicated'):self.compose()

    def test_single_image_hash_or_visual_attestation_is_mandatory(self):
        for change in ('hash','path','global_attestation','reviewer','empty_transcription'):
            p=copy.deepcopy(self.payload)
            if change=='hash':p['images'][0].pop('sha256')
            elif change=='path':p['images'][0].pop('source_image_path')
            elif change=='global_attestation':p['visual_review_complete']=False
            elif change=='reviewer':p['reviewer']=' '
            else:p['images'][0]['transcription']=' '
            with self.subTest(change=change),self.assertRaises(engine.ValidationError):self.compose(p)

    def test_transcription_is_preserved_not_ocr_corrected_and_changes_derived_version(self):
        first=self.compose();p=copy.deepcopy(self.payload)
        p['images'][0]['transcription']='a different human interpretation'
        other=self.compose(p)
        self.assertIn('a different human interpretation',other['text'])
        self.assertNotEqual(first['version'],other['version'])
        self.assertIn('not transcription correctness',other['normalization_notice'])

    def test_claim_number_injection_in_transcription_rejected(self):
        p=copy.deepcopy(self.payload);p['images'][0]['transcription']='formula\n99. An invented new claim.'
        with self.assertRaisesRegex(engine.ValidationError,'claim sequence'):self.compose(p)

    def test_outside_run_evidence_path_rejected(self):
        p=copy.deepcopy(self.payload);p['image_manifest']=str(fixtures.ROOT/'SKILL.md')
        with self.assertRaisesRegex(engine.ValidationError,'inside run directory'):self.compose(p)

    def supplemental_fixture(self):
        original=self.envelope['response']['result']['structuredContent']['data'][0]
        original['patent_id']='same-text-patent-id'
        original['claims'][0]['claim_text']=self.raw_html.replace('https://example.test/patent/image-one.png?temporary=ignored','')
        self.supplemental_path=self.root/'intelligent-image-raw.json'
        self.supplemental={'tool':'intelligent_image','endpoint':self.envelope['endpoint'],'arguments':{'pn':self.pn,'lang':'EN'},
            'status':'ok','error_code':None,'response':{'jsonrpc':'2.0','id':2,'result':{'isError':False,'structuredContent':{
                'success':True,'error_code':0,'data':{'pdf_images':[
                    {'patent_id':'unrelated-first-record','storage_path':'https://data-fulltext-image.zhihuiya.com/CN/first.png'},
                    {'patent_id':'same-text-patent-id','storage_path':'https://data-fulltext-image.zhihuiya.com/CN/image-one.png?sign=private-test-only'}],
                'patent_images':[]}}}}}
        self.manifest['images'][0].update(source_image_path='/CN/image-one.png',supplemental_image_access={
            'source_raw_artifact':self.supplemental_path.name,'source_sha256':'pending','record_index':1})
        self.payload['images'][0]['source_image_path']='/CN/image-one.png'
        self.refresh_supplemental()

    def refresh_supplemental(self):
        self.write_json(self.supplemental_path,self.supplemental)
        self.manifest['images'][0]['supplemental_image_access']['source_sha256']=composer.sha(self.supplemental_path)
        self.update_raw_and_manifest()

    def test_empty_src_exact_intelligent_pdf_image_binding_preserved_without_signed_url(self):
        self.supplemental_fixture();result=self.compose()
        proof=result['embedded_image_review']['images'][0]['supplemental_image_access']
        self.assertEqual(proof['record_index'],1)
        self.assertEqual(proof['source_patent_id'],'same-text-patent-id')
        self.assertEqual(proof['source_record_path'],['response','result','structuredContent','data','pdf_images',1])
        self.assertEqual(proof['source_sha256'],composer.sha(self.supplemental_path))
        self.assertEqual(proof['source_image_path'],'/CN/image-one.png')
        self.assertNotIn('private-test-only',json.dumps(result))
        with self.c:engine.import_document(self.c,result)

    def test_supplemental_cache_and_actual_record_index_must_be_exact(self):
        self.supplemental_fixture()
        for change in ('hash','negative','bool','out_of_range','wrong_actual_record','missing_proof_field','extra_proof_field','outside_run'):
            saved=copy.deepcopy(self.manifest)
            access=self.manifest['images'][0]['supplemental_image_access']
            if change=='hash':access['source_sha256']='0'*64
            elif change=='negative':access['record_index']=-1
            elif change=='bool':access['record_index']=True
            elif change=='out_of_range':access['record_index']=2
            elif change=='wrong_actual_record':access['record_index']=0
            elif change=='missing_proof_field':access.pop('record_index')
            elif change=='extra_proof_field':access['allow_override']=True
            else:access['source_raw_artifact']=str(fixtures.ROOT/'SKILL.md')
            self.update_raw_and_manifest()
            with self.subTest(change=change),self.assertRaises(engine.ValidationError):self.compose()
            self.manifest=saved
        self.update_raw_and_manifest()

    def test_supplemental_cannot_use_family_or_other_pn_or_other_tool(self):
        self.supplemental_fixture()
        for change in ('tool','other_pn','batch_pn','patent_number_alias','patent_id','source_patent_id_absent'):
            saved=copy.deepcopy(self.supplemental);source=self.envelope['response']['result']['structuredContent']['data'][0]
            if change=='tool':self.supplemental['tool']='abstract_image'
            elif change=='other_pn':self.supplemental['arguments']['pn']='CN900000002A'
            elif change=='batch_pn':self.supplemental['arguments']['pn']=self.pn+',CN900000002A'
            elif change=='patent_number_alias':self.supplemental['arguments']={'patent_number':self.pn}
            elif change=='patent_id':self.supplemental['response']['result']['structuredContent']['data']['pdf_images'][1]['patent_id']='family-member-patent-id'
            else:source.pop('patent_id')
            self.refresh_supplemental()
            with self.subTest(change=change),self.assertRaises(engine.ValidationError):self.compose()
            source['patent_id']='same-text-patent-id';self.supplemental=saved
        self.refresh_supplemental()

    def test_supplemental_never_guesses_from_pdf_order_or_patent_figures(self):
        self.supplemental_fixture();data=self.supplemental['response']['result']['structuredContent']['data']
        for change in ('filename','image_id','figure_only'):
            saved=copy.deepcopy(data);saved_id=self.manifest['images'][0]['image_id']
            if change=='filename':data['pdf_images'][1]['storage_path']='https://data-fulltext-image.zhihuiya.com/CN/another-equation.png'
            elif change=='image_id':data['pdf_images'][1]['storage_path']='https://data-fulltext-image.zhihuiya.com/CN/QLYQS_1.png'
            else:data['patent_images']=data.pop('pdf_images')
            self.refresh_supplemental()
            with self.subTest(change=change),self.assertRaises(engine.ValidationError):self.compose()
            data.clear();data.update(saved);self.manifest['images'][0]['image_id']=saved_id
        self.refresh_supplemental()

    def test_supplemental_requires_trusted_https_exact_host_and_filename(self):
        self.supplemental_fixture();rec=self.supplemental['response']['result']['structuredContent']['data']['pdf_images'][1]
        good=rec['storage_path']
        for url in ('http://data-fulltext-image.zhihuiya.com/CN/image-one.png',
                    'https://data-fulltext-image.zhihuiya.com.evil.test/CN/image-one.png',
                    'https://user:pass@data-fulltext-image.zhihuiya.com/CN/image-one.png',
                    'https://data-fulltext-image.zhihuiya.com:444/CN/image-one.png',
                    'https://data-fulltext-image.zhihuiya.com/CN/../image-one.png',
                    'https://data-fulltext-image.zhihuiya.com/CN/image-one.png.exe',
                    'https://data-fulltext-image.zhihuiya.com/CN/image-one.png#fragment'):
            rec['storage_path']=url;self.refresh_supplemental()
            with self.subTest(url=url),self.assertRaises(engine.ValidationError):self.compose()
        rec['storage_path']=good;self.refresh_supplemental()

    def test_supplemental_storage_path_still_matches_both_manifest_and_visual_review(self):
        self.supplemental_fixture();self.payload['images'][0]['source_image_path']='/CN/different.png'
        with self.assertRaisesRegex(engine.ValidationError,'Source image path'):self.compose()
        self.payload['images'][0]['source_image_path']='/CN/image-one.png'
        self.manifest['images'][0]['source_image_path']='/CN/different.png';self.update_raw_and_manifest()
        with self.assertRaisesRegex(engine.ValidationError,'Source image path'):self.compose()

    def test_supplemental_service_failure_cannot_hide_behind_pdf_images(self):
        self.supplemental_fixture()
        for change in ('status','outer_code','transport','tool','business','provider_code'):
            saved=copy.deepcopy(self.supplemental)
            if change=='status':self.supplemental['status']='failed'
            elif change=='outer_code':self.supplemental['error_code']=99
            elif change=='transport':self.supplemental['response']['error']={'code':-1}
            elif change=='tool':self.supplemental['response']['result']['isError']=True
            elif change=='business':self.supplemental['response']['result']['structuredContent']['success']=False
            else:self.supplemental['response']['result']['structuredContent']['error_code']=99
            self.refresh_supplemental()
            with self.subTest(change=change),self.assertRaises(engine.ValidationError):self.compose()
            self.supplemental=saved
        self.refresh_supplemental()

    def test_nonempty_original_src_cannot_be_bypassed_by_supplemental_access(self):
        self.supplemental_fixture()
        self.envelope['response']['result']['structuredContent']['data'][0]['claims'][0]['claim_text']=self.raw_html
        self.refresh_supplemental()
        with self.assertRaisesRegex(engine.ValidationError,'Nonempty or absent'):self.compose()

    def test_absent_src_does_not_count_as_verified_empty_src(self):
        self.supplemental_fixture()
        raw=self.envelope['response']['result']['structuredContent']['data'][0]['claims'][0]['claim_text']
        self.envelope['response']['result']['structuredContent']['data'][0]['claims'][0]['claim_text']=raw.replace('src="" ','')
        self.refresh_supplemental()
        with self.assertRaisesRegex(engine.ValidationError,'Nonempty or absent'):self.compose()


if __name__=='__main__':unittest.main(verbosity=2)
