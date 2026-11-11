"""Synthetic regressions for bounded intake and real-reader gate integration."""
import hashlib
import importlib.util
import json
import unittest
from pathlib import Path
import test_integrity
engine=test_integrity.engine

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('reader',ROOT/'scripts/render_reader.py')
reader=importlib.util.module_from_spec(spec);spec.loader.exec_module(reader)

class MaterialReaderTests(unittest.TestCase):
    def setUp(self):
        self.helper=test_integrity.IntegrityTests();self.helper.setUp();self.addCleanup(self.helper.doCleanups)
        self.db=self.helper.db;self.directory=self.helper.directory
    def manifest(self,kind='claims'):
        text=self.helper.doc_input()['text'];file=self.directory/'source.txt';file.write_text(text,encoding='utf-8')
        record=self.helper.record();record.update(material_source_id='m1',material_locator='page 1')
        return {'confirmed':True,'scope_label':'Synthetic frozen supplied set','boundary':{'subjects':['Synthetic Test Entity'],'jurisdictions':['CN'],'dates':'2020'},'excluded_or_unavailable':[],
          'sources':[{'id':'m1','path':str(file),'sha256':hashlib.sha256(file.read_bytes()).hexdigest(),'received_at':'2026-10-20','kind':kind,'publication_numbers':[record['pn']]}],'records':[record]}
    def material_mode(self):
        with self.db:
            run=engine.run_info(self.db);run['scope']['acquisition_mode']='materials';engine.set_meta(self.db,'run',run)
    def intake(self,p):
        with self.db:return engine.materials_module().import_manifest(self.db,p,engine.material_engine())
    def test_material_can_complete_without_fake_queries(self):
        self.material_mode();self.intake(self.manifest())
        doc=self.helper.document();self.helper.analyze(doc)
        with self.db:engine.import_insights(self.db,[self.helper.insight(role,doc['application_id']) for role in engine.ROLES])
        result=engine.validate_run(self.db)
        self.assertEqual(result['status'],'complete',result['errors'])
        self.assertIn('material_scope_only',[x['code'] for x in result['warnings']])
        self.assertEqual(self.db.execute('SELECT count(*) FROM queries').fetchone()[0],0)
        (self.directory/'source.txt').write_text('changed',encoding='utf-8')
        self.assertIn('material_scope_invalid',[x['code'] for x in engine.validate_run(self.db)['errors']])
    def test_default_search_gates_still_fail(self):
        errors=[x['code'] for x in engine.validate_run(self.db)['errors']]
        self.assertIn('no_queries',errors);self.assertIn('missing_query',errors)
        run=engine.run_info(self.db);run['scope']['synthetic']=False;engine.set_meta(self.db,'run',run)
        self.assertIn('query_plan_unconfirmed',[x['code'] for x in engine.validate_run(self.db)['errors']])
    def test_search_supplement_retains_original_query_counts(self):
        self.helper.complete_fixture();self.db.commit();count=self.db.execute('SELECT count(*) FROM queries').fetchone()[0]
        m=self.manifest();m['records'][0]['pn']='CN0000001A'
        with self.assertRaises(engine.ValidationError):self.intake(m)
        self.intake(self.manifest())
        self.assertEqual(count,self.db.execute('SELECT count(*) FROM queries').fetchone()[0])
        self.assertNotEqual(engine.run_info(self.db)['scope'].get('acquisition_mode'),'materials')
    def test_design_catalogue_does_not_require_technical_text(self):
        data=json.loads((ROOT/'assets/reader/example.json').read_text(encoding='utf-8'))
        design=next(r for r in data['records'] if r['type']=='design');design['evidence_ids']=[]
        reader.validate(data)
        design['type']='invention'
        with self.assertRaises(ValueError):reader.validate(data)
    def test_manifest_is_frozen_and_sources_are_verified(self):
        self.material_mode();m=self.manifest();m['sources'][0]['sha256']='bad'
        with self.assertRaises(engine.ValidationError):self.intake(m)
        m=self.manifest();self.intake(m);m['scope_label']='new scope'
        with self.assertRaises(engine.ValidationError):self.intake(m)
    def test_uploaded_text_requires_full_review_and_rejects_abstract(self):
        self.material_mode();m=self.manifest();self.intake(m)
        p=self.helper.doc_input(source_class='uploaded_patent_document',material_source_id='m1')
        with self.assertRaises(engine.ValidationError):engine.import_document(self.db,p)
        p['material_review']={'source_sha256':m['sources'][0]['sha256'],'text_sha256':hashlib.sha256(p['text'].encode()).hexdigest(),'reviewer':'Synthetic reviewer','reviewed_at':'2026-10-20','page_range':'1','identity_locator':'cover','end_locator':'claim 2'}
        with self.db:self.assertTrue(engine.import_document(self.db,p)['qualified'])
        m['sources'][0]['kind']='abstract';engine.set_meta(self.db,'material_manifest',m)
        with self.assertRaises(engine.ValidationError):engine.import_document(self.db,p)
    def test_reader_binds_real_database_and_rejects_changed_quote(self):
        self.helper.complete_fixture();self.db.commit()
        data=json.loads((ROOT/'assets/reader/example.json').read_text(encoding='utf-8'))
        data['synthetic']=False;run=engine.run_info(self.db);data['company']=run['company'];data['scope']['mode']='search';data['scope']['as_of']=run['as_of_date']
        app=engine.included_applications(self.db)[0];ev=dict(self.db.execute('SELECT * FROM evidence').fetchone());evd=json.loads(ev['data']);doc=dict(self.db.execute('SELECT * FROM documents').fetchone())
        data['sources']=[{'id':ev['id'],'title':'Synthetic source','publication':doc['publication_id'],'version':'bound by DB','locator':'bound by DB','quote':evd['quote'],'text':doc['text']}]
        data['records']=[{'id':app['id'],'title':app['title'],'publication':app['publication_numbers'][0],'type':app['patent_type'],'filing_date':app['filing_date'],'product':'Synthetic product','evidence_ids':[ev['id']]}]
        for role in data['roles'].values():
            for point in role['reasons']:point['evidence_ids']=[ev['id']]
        for chapter in data['chapters']:chapter['evidence_ids']=[ev['id']]
        reader.bind_run(data,str(self.helper.dbpath));reader.validate(data)
        reader.build(data,self.directory/'portable.html');self.assertTrue((self.directory/'portable.html').exists())
        data['sources'][0]['quote']='invented'
        with self.assertRaises(ValueError):reader.bind_run(data,str(self.helper.dbpath))

if __name__=='__main__':unittest.main()
