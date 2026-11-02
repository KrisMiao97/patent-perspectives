"""Narrow immutable original-publication identity provenance boundaries."""
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('mirror_identity_engine',ROOT/'scripts/patent_perspectives.py')
engine=importlib.util.module_from_spec(spec);spec.loader.exec_module(engine)

class OriginalIdentityMirrorTests(unittest.TestCase):
    def setUp(self):
        runtime=ROOT/'tests/.runtime';runtime.mkdir(exist_ok=True)
        self.tmp=tempfile.TemporaryDirectory(dir=runtime);self.root=Path(self.tmp.name)
        assert self.root.resolve().is_relative_to(runtime.resolve())
        self.addCleanup(self.tmp.cleanup)
        self.c=engine.db_open(self.root/'fixture.sqlite');self.addCleanup(self.c.close)
        self.pub=engine.normalize_record({'pn':'KR209999999Y1','apno':'KR20999999999','apdt':'19970808','pbdt':'20000201','original_assignee':'Synthetic Person'},'synthetic_original_mirror_fixture')
        engine.merge_application(self.c,self.pub);self.pubs={self.pub['id']:self.pub}
        self.name='(73) holder Synthetic Person';self.address='Synthetic foreign address 970-11'
        self.pdf=self.root/'original.pdf';self.pdf.write_bytes(b'%PDF-1.4\n% synthetic provenance fixture; no real patent claim\n%%EOF\n')
        self.sha=hashlib.sha256(self.pdf.read_bytes()).hexdigest()
        self.extracted={'pdf_sha256':self.sha,'publication_number':self.pub['id'],'extraction_tool':'synthetic_fixture','page_count':1,'pages':[{'page_number':1,'text':self.name+'\n'+self.address}]}
        self.review={'kind':'manual_original_patent_identity_review','result':'identity_confirmed','reviewer':'Synthetic fixture only','reviewed_at':'2026-10-21T00:00:00Z','publication_number':self.pub['id'],'pdf_sha256':self.sha,'page_number':1,'name_quote':self.name,'address_quote':self.address,'determination':'different_entity','patent_office':'KR','visual_review_performed':True}
        self.v={'source_class':'original_patent_document_mirror','source_url':'https://patentimages.storage.googleapis.com/48/61/26/a4d4f14d36508a/KR209999999Y1.pdf','source_artifact':'original.pdf','artifact_sha256':self.sha,'publication_number':self.pub['id'],'page_number':1,'text_artifact':'page.json','manual_review_artifact':'review.json','name_quote':self.name,'address_quote':self.address,'quote':self.name+'\n'+self.address,'subject_name':'Synthetic Person','source_locator':'Synthetic first page, holder','determination':'different_entity','source_label':'专利局原始公报的第三方托管副本'}
        self.write_evidence()
    def write_evidence(self):
        for key,path,obj in (('text_artifact_sha256','page.json',self.extracted),('manual_review_sha256','review.json',self.review)):
            data=json.dumps(obj,ensure_ascii=False).encode();(self.root/path).write_bytes(data);self.v[key]=hashlib.sha256(data).hexdigest()
    def verify(self,v=None):return engine.verify_identity_source(self.c,v or self.v,self.pubs)
    def test_exact_snapshot_accepted_without_official_domain_promotion(self):
        self.assertTrue(self.verify());self.assertFalse(engine.identity_source_valid(self.v));self.assertNotIn('patentimages.storage.googleapis.com',engine.OFFICIAL)
    def test_tampered_pdf_rejected(self):
        self.pdf.write_bytes(self.pdf.read_bytes()+b'changed');
        with self.assertRaisesRegex(engine.ValidationError,'SHA256'):self.verify()
    def test_off_domain_or_query_or_wrong_pn_rejected(self):
        for url in ('https://patents.google.com/48/61/26/a4d4f14d36508a/KR209999999Y1.pdf','http://patentimages.storage.googleapis.com/48/61/26/a4d4f14d36508a/KR209999999Y1.pdf',self.v['source_url']+'?x=1',self.v['source_url']+'?api_key=synthetic',self.v['source_url'].replace('KR209999999Y1','KR200000000Y1')):
            v=copy.deepcopy(self.v);v['source_url']=url
            with self.assertRaises(engine.ValidationError):self.verify(v)
    def test_other_application_publication_rejected(self):
        v=copy.deepcopy(self.v);v['publication_number']='KR200000000Y1'
        with self.assertRaisesRegex(engine.ValidationError,'same application'):self.verify(v)
    def test_path_escape_rejected(self):
        v=copy.deepcopy(self.v);v['source_artifact']='../outside.pdf'
        with self.assertRaisesRegex(engine.ValidationError,'inside the run'):self.verify(v)
    def test_unquoted_name_address_or_wrong_page_rejected(self):
        for key,value in (('name_quote','Different person'),('address_quote','Invented address'),('page_number',2)):
            v=copy.deepcopy(self.v);v[key]=value
            with self.assertRaises(engine.ValidationError):self.verify(v)
    def test_missing_visual_review_and_office_mismatch_rejected(self):
        for key,value in (('visual_review_performed',False),('patent_office','US'),('pdf_sha256','0'*64)):
            old=copy.deepcopy(self.review);self.review[key]=value;self.write_evidence()
            with self.assertRaises(engine.ValidationError):self.verify()
            self.review=old
    def test_extraction_or_review_tamper_rejected(self):
        for path in ('page.json','review.json'):
            original=(self.root/path).read_bytes();(self.root/path).write_bytes(original+b' ')
            with self.assertRaisesRegex(engine.ValidationError,'SHA256'):self.verify()
            (self.root/path).write_bytes(original)
    def test_importer_dispatches_mirror_identity(self):
        engine.set_meta(self.c,'run',{'scope':{'require_population_review':True}})
        self.c.execute('INSERT INTO queries(id,entity_id,kind,expected_count,request,complete) VALUES(?,?,?,?,?,?)',('q','root','original',1,'{}',1))
        self.c.execute('INSERT INTO query_results VALUES(?,?)',('q',self.pub['id']))
        row={'application_id':self.pub['application_id'],'status':'excluded','reason_code':'different_entity','reason':'Synthetic original public document confirms a different person.','matched_entity_ids':[],'assignee_evidence':[{'publication_number':self.pub['id'],'field':'original_assignee','value':'Synthetic Person','matched_name':'Synthetic Person'}],'identity_source':copy.deepcopy(self.v)}
        result=engine.import_population_reviews(self.c,row);self.assertEqual(result['counts'],{'excluded':1})

if __name__=='__main__':unittest.main(verbosity=2)
