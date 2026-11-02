"""Identity boundaries with synthetic names; no real database access."""
import importlib.util
import json
from pathlib import Path
import sys
import unittest
sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('identity_names_engine',ROOT/'scripts/patent_perspectives.py')
engine=importlib.util.module_from_spec(spec);spec.loader.exec_module(engine)

class IdentityNameTests(unittest.TestCase):
    def setUp(self):
        self.c=engine.db_open(':memory:');self.addCleanup(self.c.close)
        engine.set_meta(self.c,'run',{'scope':{'require_population_review':True}})
        self.entities=[{'id':'current','name':'现受控（中国）公司','aliases':['Current Co., Ltd.'],'relation':'root','confirmed':True},
                       {'id':'exited','name':'已退出公司','relation':'historical','confirmed':True}]
        for e in self.entities:e.update(source_url='https://example.test/synthetic',source_locator='Synthetic identity fixture only')
        engine.import_entities(self.c,self.entities)
    def seed(self,original,current):
        raw={'pn':'CN999999991A','apno':'CN202000000001','apdt':20200101,'pbdt':20210101,'original_assignee':original,'current_assignee':current}
        pub=engine.normalize_record(raw,'synthetic');engine.merge_application(self.c,pub)
        self.c.execute('INSERT INTO queries(id,entity_id,kind,expected_count,request,complete) VALUES(?,?,?,?,?,?)',('q','current','original',1,'{}',1))
        self.c.execute('INSERT INTO query_results VALUES(?,?)',('q',pub['id']))
        self.c.commit()
        return pub
    def review(self,pub,entity,status='included'):
        return {'application_id':pub['application_id'],'status':status,'reason':'Synthetic verified identity boundary.',
                'reason_code':'target_entity','matched_entity_ids':[entity],
                'assignee_evidence':[{'publication_number':pub['id'],'field':f,'value':pub['metadata_original'][f],'matched_name':pub['metadata_original'][f]} for f in ('original_assignee','current_assignee') if pub['metadata_original'][f]]}
    def outside(self,pub):
        r=self.review(pub,'exited','excluded');r['reason_code']='outside_control_period'
        r['control_period_evidence']={'source_url':'https://www.cninfo.com.cn/synthetic-only','source_locator':'Synthetic period',
            'quote':'Synthetic entity exited before 2019','subject_name':'已退出公司','determination':'outside_control_period',
            'relevant_date':'2020-01-01','control_to':'2018-12-31'}
        return r
    def test_nfkc_parentheses_matches_without_raw_mutation(self):
        p=self.seed('现受控(中国)公司','现受控(中国)公司');r=self.review(p,'current')
        engine.import_population_reviews(self.c,r)
        self.assertEqual(engine.rows_data(self.c,'population_reviews')[0]['assignee_evidence'][0]['value'],'现受控(中国)公司')
        self.assertEqual(engine.application_population_status(self.c,p['application_id']),'included')
    def test_name_key_does_not_expand_or_convert_scripts(self):
        pairs=[('Current Co., Ltd.','CURRENT CO., LTD.'),('Current Co., Ltd.','Current Company Limited'),('九陽公司','九阳公司'),('台灣九陽','台湾九阳')]
        for a,b in pairs:self.assertNotEqual(engine.legal_name_key(a),engine.legal_name_key(b))
    def test_unverified_translation_cannot_claim_exact_entity(self):
        p=self.seed('Current Company Limited','');r=self.review(p,'current')
        with self.assertRaises(engine.ValidationError):engine.import_population_reviews(self.c,r)
    def test_exited_entity_current_name_does_not_protect_post_exit_filing(self):
        p=self.seed('已退出公司','已退出公司');engine.import_population_reviews(self.c,self.outside(p))
        self.assertEqual(engine.application_population_status(self.c,p['application_id']),'excluded')
    def test_current_root_nfkc_alias_blocks_historical_date_exclusion(self):
        p=self.seed('已退出公司','现受控(中国)公司')
        with self.assertRaisesRegex(engine.ValidationError,'Current verified target'):engine.import_population_reviews(self.c,self.outside(p))
    def test_verified_old_name_of_current_entity_also_protects(self):
        self.entities[0]['aliases'].append('现受控前身');engine.import_entities(self.c,self.entities)
        p=self.seed('已退出公司','现受控前身')
        with self.assertRaisesRegex(engine.ValidationError,'Current verified target'):engine.import_population_reviews(self.c,self.outside(p))
    def test_same_name_current_and_historical_legal_entities_remains_protected(self):
        self.entities[0]['aliases'].append('同名杭州');self.entities[1]['aliases']=['同名杭州'];engine.import_entities(self.c,self.entities)
        p=self.seed('已退出公司','同名杭州')
        with self.assertRaisesRegex(engine.ValidationError,'Current verified target'):engine.import_population_reviews(self.c,self.outside(p))
    def test_nfkc_target_cannot_be_excluded_as_different_identity(self):
        p=self.seed('现受控(中国)公司','');r=self.review(p,'current','excluded');r['reason_code']='different_entity'
        with self.assertRaisesRegex(engine.ValidationError,'verified target assignee'):engine.import_population_reviews(self.c,r)

if __name__=='__main__':unittest.main(verbosity=2)
