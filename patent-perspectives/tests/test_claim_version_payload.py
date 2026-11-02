"""Do not lose publication/version identity when exporting structured claims."""
import json
import unittest
import test_integrity as f
engine=f.engine

class ClaimVersionPayloadTests(unittest.TestCase):
    setUp=f.IntegrityTests.setUp
    record=f.IntegrityTests.record
    search=f.IntegrityTests.search
    seed=f.IntegrityTests.seed
    doc_input=f.IntegrityTests.doc_input
    document=f.IntegrityTests.document
    analysis_input=f.IntegrityTests.analysis_input
    analyze=f.IntegrityTests.analyze

    def sources(self):
        self.seed([self.record(),self.record(pn='CN900000001B')])
        self.a=self.document(version='synthetic-application-A')
        self.b=self.document(publication_number='CN900000001B',returned_publication_number='CN900000001B',
            version='synthetic-grant-B',text='1. A synthetic piston connects a chamber with a shield.\n2. The synthetic valve regulates the chamber.')
        self.analyze(self.b)

    def test_every_claim_links_exact_publication_version_and_primary_source(self):
        self.sources();_,details=engine.build_payload(self.db,engine.validate_run(self.db));p=next(iter(details.values()))
        self.assertEqual(p['analysis']['document_id'],self.b['document_id'])
        docs={d['id']:d for d in p['documents']}
        self.assertEqual({d['publication_number'] for d in docs.values()},{'CN900000001A','CN900000001B'})
        self.assertEqual(len(p['claims']),4)
        for claim in p['claims']:
            d=docs[claim['document_id']]
            self.assertIn(claim['text'],d['text'])
            if 'shield' in claim['text']:
                self.assertEqual((d['publication_number'],d['version']),('CN900000001B','synthetic-grant-B'))

    def test_rejected_version_keeps_identity_and_cannot_look_like_current_primary(self):
        self.sources()
        with self.db:engine.import_document_reviews(self.db,{'document_id':self.a['document_id'],'decision':'reject',
            'reason_code':'missing_formula','reason':'SYNTHETIC rejection state fixture only','reviewer':'SYNTHETIC reviewer',
            'evidence':[{'quote':'synthetic valve','locator':{'claim_number':2}}]})
        _,details=engine.build_payload(self.db,engine.validate_run(self.db));p=next(iter(details.values()));docs={d['id']:d for d in p['documents']}
        self.assertFalse(docs[self.a['document_id']]['complete']);self.assertTrue(docs[self.b['document_id']]['complete'])
        self.assertEqual(p['analysis']['document_id'],self.b['document_id'])
        self.assertEqual(len([x for x in p['claims'] if x['document_id']==self.a['document_id']]),2)

    def test_unqualified_signed_source_text_is_withheld_without_rewriting_original(self):
        self.seed()
        original='1. A synthetic piston. <img src="https://example.test/image?access_token=SYNTHETIC_ONLY">'
        doc=self.document(text=original,claim_count=1,complete=False,truncated=True)
        _,details=engine.build_payload(self.db,engine.validate_run(self.db));p=next(iter(details.values()))
        self.assertEqual(p['documents'][0]['text'],'')
        self.assertTrue(p['documents'][0]['text_withheld'])
        self.assertEqual(p['claims'],[])
        self.assertEqual(self.db.execute('SELECT text FROM documents WHERE id=?',(doc['document_id'],)).fetchone()[0],original)

    def test_mathematical_double_backslashes_are_not_private_paths(self):
        notation=r'f_m(x)=\begin{cases}0,x=0\\255,x=1\end{cases}'
        self.assertTrue(engine.source_text_public_safe(notation))
        self.assertFalse(engine.source_text_public_safe('https://example.test/source?signature=SYNTHETIC_ONLY'))

if __name__=='__main__':unittest.main()
