"""Check report integrity and portable input handling; not patent fact validation."""
import copy
import json
from pathlib import Path
import re
import sys
import tempfile
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from render_report import render, write_report

def fixture(count=1):
    return {'schema_version':1,'title':'测试报告','cutoff':'2026-11-10',
            'finding':'测试数据，无研究结论','opportunity':'未验证的产品机会',
            'judgment':'保留条件判断','boundary':'仅用于格式测试',
            'directions':[{'id':f'D{i+1}','name':f'方向{i+1}','benefit':'可能能力','tradeoff':'代价',
                           'judgment':'条件取舍','evidence_state':'待复核','decision_state':'探索',
                           'reasoning':[{'title':'具体判断','text':'原文与推断分别说明','evidence':['E1']} for _ in range(5)],
                           'conditions':[{'if':'出现条件','then':'改变判断'}]} for i in range(count)],
            'evidence':[{'id':'E1','title':'原始资料','summary':'结构披露','source_role':'直接披露','in_sample':False,
                         'location':'第 1 页','disclosure':'具体结构','limitation':'尚无实测',
                         'documents':[{'number':'文件 1','url':'https://example.org/source'}]}]}

class ReportTests(unittest.TestCase):
    def test_variable_direction_counts(self):
        for n in [0,1,5]:
            with self.subTest(n=n):
                output=render(fixture(n))
                self.assertEqual(output.count('<article class="route"'),n)
                self.assertEqual(output.count('class="step-role"'),n*5)
    def test_empty_evidence_is_explicit(self):
        data=fixture(0);data['evidence']=[]
        self.assertIn('0 个条目',render(data))
    def test_duplicate_ids_rejected(self):
        data=fixture();data['evidence'].append(copy.deepcopy(data['evidence'][0]))
        with self.assertRaises(ValueError):render(data)
    def test_unresolved_evidence_rejected(self):
        data=fixture();data['directions'][0]['reasoning'][0]['evidence']=['E99']
        with self.assertRaises(ValueError):render(data)
    def test_incomplete_reasoning_rejected(self):
        data=fixture();data['directions'][0]['reasoning'].pop()
        with self.assertRaises(ValueError):render(data)
    def test_missing_condition_rejected(self):
        data=fixture();data['directions'][0]['conditions']=[]
        with self.assertRaises(ValueError):render(data)
    def test_bad_date_and_time_order_rejected(self):
        data=fixture();data['cutoff']='2026-02-30'
        with self.assertRaises(ValueError):render(data)
        data=fixture();data['timeline']=[{'date':d,'title':'节点','change':'结构变化','evidence':['E1']} for d in ['2026-11-10','2026-11-09']]
        with self.assertRaises(ValueError):render(data)
    def test_unsafe_source_links_rejected(self):
        for url in ['javascript:alert(1)','file:///secret','data:text/html,test']:
            data=fixture();data['evidence'][0]['documents'][0]['url']=url
            with self.assertRaises(ValueError):render(data)
    def test_external_figure_rejected(self):
        data=fixture();data['directions'][0]['figure']='https://example.org/image.png'
        with self.assertRaises(ValueError):render(data)
    def test_text_cannot_close_data_script(self):
        data=fixture();data['finding']='</script><script>alert("x")</script>'
        output=render(data)
        self.assertNotIn(data['finding'],output)
        payload=re.search(r'<script id="report-data" type="application/json">(.*?)</script>',output,re.S)[1]
        self.assertEqual(json.loads(payload)['finding'],data['finding'])
    def test_invalid_input_preserves_previous_report(self):
        with tempfile.TemporaryDirectory() as folder:
            output=Path(folder)/'report.html';output.write_text('previous',encoding='utf-8')
            data=fixture();data['evidence']=[]
            with self.assertRaises(ValueError):write_report(data,output)
            self.assertEqual(output.read_text(encoding='utf-8'),'previous')
            write_report(fixture(),output)
            self.assertIn('测试报告',output.read_text(encoding='utf-8'))
            self.assertEqual(len(list(Path(folder).iterdir())),1)

if __name__=='__main__':unittest.main()
