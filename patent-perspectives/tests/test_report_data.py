"""Portable, clearly synthetic report data. No provider calls or real company records."""
import copy,importlib.util,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('report_data',ROOT/'scripts/report_data.py');reader=importlib.util.module_from_spec(spec);spec.loader.exec_module(reader)
def fixture(company='SYNTHETIC OPTICS',start=2018,home='US'):
    pats=[];details={};classes={}
    for i in range(4):
        id=f'{home}:SYNTHETIC{i}';eid=f'quote-{i}';docid=f'doc-{i}';pn=f'{home}SYNTHETIC{i}A';date=f'{start+i//2}-04-12';text='1. A synthetic optical housing supports a lens.';quote='optical housing';a=text.index(quote)
        p={'id':id,'title':'Synthetic optical assembly '+str(i),'application_number':id,'authority':home if i<2 else 'WO' if i==2 else 'DE','filing_date':date,'publication_numbers':[pn],'primary_module':'光学结构','patent_type':'invention','legal_status':'有效' if i<2 else '审中','analysis_status':'complete','summary':'支架将镜片固定在壳体内。','text_basis':'claims','verified_entity_names':[company],'tags':['镜片定位']}
        evidence={'id':eid,'application_id':id,'document_id':docid,'publication_number':pn,'version':'published','quote':quote,'start':a,'end':a+len(quote),'locator':{'claim_number':1}}
        finding={'text':'支架将镜片固定在壳体内。','evidence_ids':[eid],'kind':'disclosed'}
        d={**p,'analysis':{'document_id':docid,'summary':finding,'technical_means':[finding],'application_field':[],'technical_problem':[],'conditions':[],'components':[],'steps':[]},'documents':[{'id':docid,'text':text,'complete':True,'document_type':'claims','publication_number':pn,'version':'published'}],'evidence':[evidence],'claims':[{'number':1,'text':text,'document_id':docid}],'publications':[{'publication_number':pn,'publication_date':f'{start+i//2+1}-06-01'}],'images':[],'relations':[]}
        pats.append(p);details[id]=d;classes[id]={'product_group':'光学设备','product_line':'成像模组','direction':'镜片定位','evidence_ids':[eid],'reason':'合成测试用原文结构，不是真实专利'}
    run={'company':company,'as_of_date':f'{start+2}-12-31','scope':{'synthetic':True},'status':'preview','coverage':{},'limitations':['Synthetic fixture only']}
    payload={'run':run,'patents':pats,'insights':[],'relations':[],'modules':[],'entities':[],'detail_shards':{}}
    context={'classifications':classes,'home_authorities':[home],'selection_mode':'period','filing_window':{'from':f'{start}-01-01','through':f'{start+1}-12-31'},'analysis_label':'合成测试 · 光学设备期间申请','status_observed_at':f'{start+2}-12-31'}
    return payload,details,context
class ReportDataTests(unittest.TestCase):
    def test_dynamic_years_company_and_domicile(self):
        for company,start,home in [('SYNTHETIC OPTICS',2018,'US'),('SYNTHETIC AUTOMATION',2011,'JP')]:
            p,d,c=fixture(company,start,home);a=reader.assemble(p,d,c);s=a['report.js'][1]['settings']
            self.assertEqual(s['years'],[str(start),str(start+1)]);self.assertEqual(s['home_authorities'],[home]);self.assertEqual(len(a['routes.js'][1]['nodes']),4)
    def test_cross_application_classification_rejected(self):
        p,d,c=fixture();c['classifications'][p['patents'][0]['id']]['evidence_ids']=['quote-1']
        with self.assertRaises(reader.ReportDataError):reader.assemble(p,d,c)
    def test_tampered_source_span_rejected(self):
        p,d,c=fixture();d[p['patents'][0]['id']]['evidence'][0]['quote']='unread source'
        with self.assertRaises(reader.ReportDataError):reader.assemble(p,d,c)
    def test_partial_year_not_used_as_full_comparison(self):
        p,d,c=fixture();c['filing_window']['from']='2018-03-01';a=reader.assemble(p,d,c)
        self.assertEqual(a['report.js'][1]['settings']['comparison_years'],[])
        c['comparison_years']=['2018','2019']
        with self.assertRaises(reader.ReportDataError):reader.assemble(p,d,c)
    def test_missing_company_facts_remain_absent(self):
        p,d,c=fixture();a=reader.assemble(p,d,{})
        self.assertFalse(a['official-metrics.js'][1]);self.assertEqual(a['report.js'][1]['settings']['home_authorities'],[])
        self.assertTrue(all(x['group']=='产品待明确' for x in a['products.js'][1]['applications'].values()))
    def test_owned_denominator_must_reconcile(self):
        p,d,c=fixture();c['official']={'url':'https://example.test/annual','source_title':'Synthetic disclosure','locator':'page 1','period_end':'2020-12-31','definition':'Synthetic owned count','owned':{'total':100,'invention':70,'utility_model':20,'design':20}}
        with self.assertRaises(reader.ReportDataError):reader.assemble(p,d,c)
    def test_unknown_date_not_invented(self):
        p,d,c=fixture();p['patents'][0]['filing_date']=None;a=reader.assemble(p,d,c)
        self.assertEqual(p['patents'][0]['filing_date'],'');self.assertEqual(len(a['routes.js'][1]['nodes']),4)
    def test_pct_not_permitted_as_home(self):
        p,d,c=fixture();c['home_authorities']=['WO']
        with self.assertRaises(reader.ReportDataError):reader.assemble(p,d,c)
    def test_business_event_without_source_rejected(self):
        p,d,c=fixture();c['business_events']={'sources':{},'events':[{'date':'2019','source':'missing'}]}
        with self.assertRaises(reader.ReportDataError):reader.assemble(p,d,c)
if __name__=='__main__':unittest.main()
