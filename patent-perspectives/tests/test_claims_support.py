"""Claims-first and targeted same-publication explanation regressions."""
import copy
import importlib.util
import json
import unittest
import test_integrity as fixtures

engine=fixtures.engine
spec=importlib.util.spec_from_file_location('claims_support_materializer',fixtures.ROOT/'scripts/materialize_review.py')
materializer=importlib.util.module_from_spec(spec);spec.loader.exec_module(materializer)


class ClaimsSupportTests(unittest.TestCase):
    def setUp(self):
        self.fixture=fixtures.IntegrityTests(methodName='runTest');self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups);self.c=self.fixture.db
        self.appid=self.fixture.seed()[0]
        self.claims=self.fixture.document()
        self.text='[0001]Synthetic piston uses a vent to equalize pressure.\n[0002]Synthetic chamber communicates with the vent.\n[0003]Unrelated synthetic embodiment ends completely.'
        self.desc=self.fixture.document(document_type='description',version='synthetic-description',text=self.text)

    def row(self,doc):
        return self.c.execute('SELECT * FROM documents WHERE id=?',(doc['document_id'],)).fetchone()

    def support(self,doc=None,paragraph=1):
        doc=self.desc if doc is None else doc;row=self.row(doc)
        start,end=engine.description_intervals(row['text'])[paragraph]
        return {'document_id':doc['document_id'],'read_regions':[{'start':start,'end':end,'locator':{'paragraph':str(paragraph).zfill(4)},'reviewed':True}]}

    def analysis(self):
        result=self.fixture.analysis_input(self.claims)
        result['support_documents']=[self.support()]
        result['evidence'].append({'id':'synthetic-support-vent','document_id':self.desc['document_id'],
                                   'quote':'vent to equalize pressure','locator':{'paragraph':'0001'}})
        result['fields']['technical_problem']=[{'text':'Synthetic vent explains the pressure mechanism.',
                                              'evidence_ids':['synthetic-support-vent'],'kind':'disclosed'}]
        return result

    def host(self):
        result={'application_id':self.appid,'document_id':self.claims['document_id'],'read_chunk_ids':self.claims['chunk_ids'],
            'tail_check':{'complete':True,'quote':self.row(self.claims)['text'][-55:],'claim_number':2},
            'primary_module':'Synthetic mechanism','tags':['synthetic'],
            'summary':{'text':'Host authored primary-claim mechanism with targeted explanation.','evidence':['c1','p1']},
            'fields':{key:[] for key in engine.FIELDS},'limitations':['Synthetic fixture only; undisclosed fields remain empty.'],
            'support_documents':[{'document_id':self.desc['document_id'],'read_regions':[{'paragraph_number':1,'reviewed':True}]}],
            'evidence':[{'key':'c1','claim_number':1},{'key':'p1','document_id':self.desc['document_id'],
                         'paragraph_number':1,'quote':'vent to equalize pressure'}]}
        result['fields']['technical_means']=[{'text':'Host explains only the selected source mechanism.','evidence':['c1','p1']}]
        return result

    def fails(self,p,message):
        with self.assertRaisesRegex(engine.ValidationError,message):engine.import_analysis(self.c,p)

    def test_partial_description_read_keeps_exact_attribution_and_validates_full_delivery(self):
        result=self.analysis();engine.import_analysis(self.c,result)
        primary=self.c.execute('SELECT * FROM evidence WHERE id=?',(result['evidence'][0]['id'],)).fetchone()
        auxiliary=self.c.execute('SELECT * FROM evidence WHERE id=?',('synthetic-support-vent',)).fetchone()
        self.assertEqual(primary['document_id'],self.claims['document_id'])
        self.assertEqual(auxiliary['document_id'],self.desc['document_id'])
        saved=engine.rows_data(self.c,'analyses')[0]
        self.assertEqual(saved['support_documents'][0]['source_text_hash'],self.row(self.desc)['text_hash'])
        self.assertEqual(saved['support_documents'][0]['reading_scope'],'selected_regions')
        self.assertNotIn('completed_chunk_ids',saved['support_documents'][0])
        self.assertLess(saved['support_documents'][0]['read_regions'][0]['end'],len(self.text))
        engine.import_insights(self.c,[self.fixture.insight(role,self.appid) for role in engine.ROLES])
        report=engine.validate_run(self.c)
        self.assertEqual(report['status'],'complete',report['errors'])
        payload,details=engine.build_payload(self.c,report)
        detail=details[self.appid]
        self.assertEqual(detail['analysis']['text_basis'],'claims')
        self.assertEqual(detail['analysis']['support_documents'][0]['document_id'],self.desc['document_id'])

    def test_primary_claims_still_need_all_chunks(self):
        p=self.analysis();p['completed_chunk_ids']=[]
        self.fails(p,'Every source chunk')

    def test_cross_publication_even_within_one_application_is_rejected(self):
        raw=self.fixture.record(pn='CN900000001B');pub=engine.normalize_record(raw,'Synthetic fixture')
        engine.merge_application(self.c,pub)
        wrong=engine.import_document(self.c,self.fixture.doc_input(publication_number=raw['pn'],returned_publication_number=raw['pn'],
                     document_type='description',version='synthetic-granted-description',text=self.text))
        p=self.analysis();p['support_documents']=[self.support(wrong)]
        self.fails(p,'same publication and application')

    def test_cross_application_family_is_rejected(self):
        self.fixture.search([self.fixture.record(2)],qid='synthetic-extra');wrong=self.fixture.document(2,document_type='description',text=self.text)
        p=self.analysis();p['support_documents']=[self.support(wrong)]
        self.fails(p,'same publication and application')

    def test_unqualified_and_rejected_support_are_blocked(self):
        bad=self.fixture.document(document_type='description',version='synthetic-partial',text=self.text,complete=False,truncated=True)
        p=self.analysis();p['support_documents']=[self.support(bad)]
        self.fails(p,'qualified and not rejected')
        engine.import_document_reviews(self.c,{'document_id':self.desc['document_id'],'decision':'reject','reason_code':'missing_formula',
            'reason':'Synthetic omitted formula.','reviewer':'Synthetic reviewer','evidence':[{'quote':'vent to equalize pressure','locator':{'paragraph':'0001'}}]})
        self.fails(self.analysis(),'qualified and not rejected')

    def test_read_regions_need_real_bounds_locator_and_explicit_review(self):
        for bad in ({'start':0,'end':999999,'locator':{'source_span':True},'reviewed':True},
                    {'start':True,'end':8,'locator':{'source_span':True},'reviewed':True},
                    {'start':8,'end':20,'locator':{'paragraph':'0002'},'reviewed':True},
                    {'start':8,'end':20,'locator':{'page':1},'reviewed':True},
                    {'start':8,'end':20,'locator':{'source_span':True},'reviewed':False}):
            p=self.analysis();p['support_documents'][0]['read_regions']=[bad]
            self.fails(p,'Supporting (read region|paragraph)')

    def test_missing_duplicate_overlapping_regions_and_stale_source_are_rejected(self):
        p=self.analysis();p['support_documents'][0]['read_regions']=[];self.fails(p,'actual reviewed')
        p=self.analysis();p['support_documents']*=2;self.fails(p,'Duplicate/primary')
        p=self.analysis();p['support_documents'][0]['read_regions']*=2;self.fails(p,'repeat or overlap')
        p=self.analysis();p['support_documents'][0]['source_text_hash']='wrong';self.fails(p,'Stale supporting')

    def test_undeclared_or_unread_auxiliary_evidence_is_rejected(self):
        p=self.analysis();p['evidence'][1]['document_id']='not-a-document';self.fails(p,'not the primary or a declared')
        p=self.analysis();p['evidence'][1]['quote']='communicates with the vent';p['evidence'][1]['locator']={'paragraph':'0002'}
        self.fails(p,'outside actually reviewed')
        p=self.analysis();p['evidence']=p['evidence'][1:];self.fails(p,'must cite its fully read primary')

    def test_support_quote_cannot_carry_another_paragraph_label(self):
        p=self.analysis();p['evidence'][1]['locator']={'paragraph':'0002'}
        self.fails(p,'does not belong to specified paragraph')
        p=self.analysis();p['evidence'][1]['locator']={'page':1}
        self.fails(p,'exact paragraph or source_span')

    def test_wrong_language_and_description_primary_cannot_use_support(self):
        other=self.fixture.document(document_type='description',version='synthetic-wrong-language',language='CN',text=self.text)
        p=self.analysis();p['support_documents']=[self.support(other)];self.fails(p,'languages differ')
        p=self.fixture.analysis_input(self.desc,locator={'paragraph':'0001'});p['support_documents']=[self.support()]
        self.fails(p,'Only complete primary claims')

    def test_make_evidence_never_silently_reassigns_an_explicit_source(self):
        p=self.analysis()['evidence'][1]
        with self.assertRaisesRegex(engine.ValidationError,'cannot be rewritten'):engine.make_evidence(self.c,self.row(self.claims),p)

    def test_support_rejection_invalidates_analysis_and_keeps_audit(self):
        engine.import_analysis(self.c,self.analysis())
        engine.import_document_reviews(self.c,{'document_id':self.desc['document_id'],'decision':'reject','reason_code':'missing_formula',
            'reason':'Synthetic source defect in supporting explanation.','reviewer':'Synthetic reviewer',
            'evidence':[{'quote':'vent to equalize pressure','locator':{'paragraph':'0001'}}]})
        self.assertEqual(engine.rows_data(self.c,'analyses')[0]['analysis_status'],'invalidated_source_review')
        self.assertEqual(len(engine.rows_data(self.c,'analysis_invalidations')),1)
        self.assertEqual(engine.coverage(self.c)['technical_analyzed'],0)
        self.assertIn('supporting_source_invalid',{e['code'] for e in engine.validate_run(self.c)['errors']})
        output=self.fixture.directory/'restart.jsonl';engine.export_work(self.c,output)
        work=json.loads(output.read_text(encoding='utf-8'))
        self.assertEqual(work['document_id'],self.claims['document_id']);self.assertEqual(work['support_document_candidates'],[])

    def test_legacy_full_description_analysis_is_not_reprocessed(self):
        p=self.fixture.analysis_input(self.desc,quote='Synthetic piston',locator={'paragraph':'0001'});engine.import_analysis(self.c,p)
        output=self.fixture.directory/'legacy.jsonl'
        self.assertEqual(engine.export_work(self.c,output)['work_items'],0)
        self.assertTrue(engine.analysis_is_current(self.c,self.c.execute('SELECT * FROM analyses').fetchone()))

    def test_complete_description_fallback_when_claims_rejected(self):
        engine.import_document_reviews(self.c,{'document_id':self.claims['document_id'],'decision':'reject','reason_code':'missing_formula',
            'reason':'Synthetic missing claim formula.','reviewer':'Synthetic reviewer',
            'evidence':[{'quote':'synthetic piston','locator':{'claim_number':1}}]})
        output=self.fixture.directory/'fallback.jsonl';engine.export_work(self.c,output)
        self.assertEqual(json.loads(output.read_text(encoding='utf-8'))['document_id'],self.desc['document_id'])

    def test_compact_support_resolves_only_attested_paragraph_and_keeps_source(self):
        analysis,review=materializer.build(self.c,self.host(),engine)
        engine.import_analysis(self.c,analysis)
        self.assertEqual(analysis['evidence'][1]['document_id'],self.desc['document_id'])
        self.assertEqual(analysis['evidence'][1]['quote'],'vent to equalize pressure')
        self.assertEqual(review['support_documents'][0]['reading_scope'],'selected_regions')
        self.assertEqual(review['read_chunk_ids'],self.claims['chunk_ids'])

    def test_compact_unread_and_false_support_regions_fail_without_formal_import(self):
        host=self.host();host['support_documents'][0]['read_regions'][0]['reviewed']=False
        with self.assertRaisesRegex(engine.ValidationError,'reviewed=true'):materializer.build(self.c,host,engine)
        host=self.host();host['support_documents'][0]['read_regions']=[{'paragraph_number':2,'reviewed':True}]
        with self.assertRaisesRegex(engine.ValidationError,'outside actually reviewed'):materializer.build(self.c,host,engine)
        host=self.host();host['support_documents'][0]['read_regions']=[{'claim_number':1,'reviewed':True}]
        with self.assertRaisesRegex(engine.ValidationError,'actual paragraph/span'):materializer.build(self.c,host,engine)


if __name__=='__main__':unittest.main()
