"""Whole-source delivery and deferred-input regressions, synthetic data only."""
import json
import os
import unittest
import test_integrity as integrity
engine=integrity.engine


class WholePatentPipelineTests(unittest.TestCase):
    def setUp(self):
        self.fixture=integrity.IntegrityTests(methodName='runTest')
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.c=self.fixture.db
        self.fixture.seed()

    def test_export_keeps_long_text_once_and_preserves_source(self):
        text='1. A synthetic piston connects a chamber.\n2. '+('A synthetic valve closes after the piston moves. '*700)
        doc=self.fixture.document(text=text)
        out=self.fixture.directory/'whole.jsonl'
        report=engine.export_work(self.c,out)
        packet=json.loads(out.read_text(encoding='utf-8'))
        self.assertEqual(report['work_items'],1)
        self.assertEqual(packet['primary_document']['text'],text)
        self.assertEqual(packet['primary_document']['source_text_hash'],engine.digest(text))
        self.assertNotIn('chunks',packet)
        self.assertTrue(all('text' not in x for x in packet['source']['claims']))
        self.assertEqual(packet['coverage']['legacy_chunk_ids'],doc['chunk_ids'])
        self.assertEqual(self.c.execute('SELECT text FROM documents').fetchone()[0],text)

    def test_capacity_defers_entire_source_without_reducing_population(self):
        text=self.fixture.doc_input()['text']
        doc=self.fixture.document()
        out=self.fixture.directory/'capacity.jsonl'
        report=engine.export_work(self.c,out,max_primary_characters=len(text)-1)
        self.assertEqual(report['work_items'],0)
        self.assertEqual(report['deferred_items'],1)
        self.assertEqual(out.read_text(encoding='utf-8'),'')
        pending=json.loads((out.parent/(out.name+'.deferred.json')).read_text(encoding='utf-8'))
        self.assertEqual(pending[0]['document_id'],doc['document_id'])
        self.assertEqual(engine.coverage(self.c)['technical_applications'],1)
        self.assertEqual(engine.export_work(self.c,out,max_primary_characters=len(text))['work_items'],1)
        self.assertEqual(json.loads((out.parent/(out.name+'.deferred.json')).read_text(encoding='utf-8')),[])

    def test_legacy_completed_analysis_returns_for_whole_review_when_adopted(self):
        doc=self.fixture.document()
        self.fixture.analyze(doc)
        out=self.fixture.directory/'adopt.jsonl'
        self.assertEqual(engine.export_work(self.c,out)['work_items'],0)
        run=engine.run_info(self.c)
        run['scope']['require_whole_patent_review']=True
        engine.set_meta(self.c,'run',run)
        self.assertEqual(engine.export_work(self.c,out)['work_items'],1)
        self.assertEqual(self.c.execute('SELECT count(*) FROM analyses').fetchone()[0],1)

    def test_core_import_cannot_omit_eight_fields_in_whole_mode(self):
        doc=self.fixture.document()
        payload=self.fixture.analysis_input(doc)
        source=self.c.execute('SELECT * FROM documents').fetchone()
        payload.update(whole_document_review={'document_id':source['id'],'source_text_hash':source['text_hash'],'reading_mode':'whole','complete':True,'capacity_basis':'Synthetic text fits with reasoning and output space.'},
                       tail_check={'complete':True,'quote':source['text'][-24:],'claim_number':2},analysis_author='synthetic-reader')
        with self.assertRaises(engine.ValidationError):
            engine.import_analysis(self.c,payload)
        payload['fields']={name:payload['fields'].get(name,[]) for name in engine.FIELDS}
        engine.import_analysis(self.c,payload)

    def test_work_export_rejects_database_and_hardlink_targets(self):
        self.fixture.document()
        with self.assertRaises(engine.ValidationError):
            engine.export_work(self.c,self.fixture.dbpath)
        alias=self.fixture.directory/'database-alias.jsonl'
        try:
            os.link(self.fixture.dbpath,alias)
        except OSError:
            self.skipTest('Filesystem does not support this hardlink fixture')
        with self.assertRaises(engine.ValidationError):
            engine.export_work(self.c,alias)
        self.assertEqual(self.fixture.dbpath.read_bytes()[:16],b'SQLite format 3\x00')


if __name__=='__main__':
    unittest.main()
