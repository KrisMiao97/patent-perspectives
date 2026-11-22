"""Project arguments and sources are separate from the evidence underlying research answers."""
import copy
import json
import sqlite3
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
import reader_contract as rc


def fixture():
    return {'version':2,'purpose':'比较接口','scope':'一份合成文献','as_of':'2026-11-01','reviewed_on':'2026-11-18',
            'reading_context':{'reader_background':'项目负责人','scene_title':'接口','scene':'比较装配动作。'},
            'primary_role':'rd','common_boundary':'未测效果',
            'market_search':{'permission':'not_requested','performed':False,'statement':'未检索市场'},
            'role_guides':{'rd':{'question':'哪里接触？','answer':'见原文','focus':'位置','evidence_ids':['E1']}},
            'questions':[{'id':'Q1','question':'资料能说明什么？','status':'answered','answer':'记录了终态。',
                          'boundary':'不能还原动作。','evidence_ids':['E1']}],
            'project_report':{'context':'接口评审','sections':[{'role':'rd','horizon':'near','module':3,
               'question_id':'Q1','decision':'先记录装配。','standing':'proposed','gap':'缺动作记录',
               'next_step':'拍摄装配','resources':'责任人待指定','gate':'记录可复核后再比较。'}]}}


class ProjectReportTests(unittest.TestCase):
    def test_optional_for_legacy_and_pure_research(self):
        d=fixture();del d['project_report'];rc.validate(d,['E1'])
        self.assertEqual(rc.project_report.insert('old',d,'missing'),'old')
        d['project_report']=None
        with self.assertRaises(ValueError):rc.validate(d,['E1'])

    def test_tracks_questions_resources_and_approval_are_checked(self):
        d=fixture();rc.validate(d,['E1']);s=d['project_report']['sections'][0]
        for values in ({'horizon':'unknown'},{'role':'bad'},{'question_id':'missing'},
                       {'standing':'approved'}, {'module':10},{'horizon':'reserve','module':None}):
            with self.subTest(values=values),self.assertRaises(ValueError):
                c=copy.deepcopy(d);c['project_report']['sections'][0].update(values);rc.validate(c,['E1'])
        del s['gate']
        with self.assertRaises(ValueError):rc.validate(d,['E1'])

    def test_verbatim_claim_and_separate_observations(self):
        d=fixture();s=d['project_report']['sections'][0]
        s['right']={'territory':'教学范围','version':'教学权项1','status':'unknown'}
        s['claims']=[{'source_id':'E1','wording':'使滤芯移动','need':'观察位移是谁造成。',
                      'cases':[{'label':'A','status':'pending','observation':'待查'}]}]
        with self.assertRaisesRegex(ValueError,'verbatim'):rc.validate(d,['E1'],source_quotes={'E1':'施加轴向力'})
        rc.validate(d,['E1'],source_quotes={'E1':'锁紧件使滤芯移动。'})
        s['right']['source_ids']=['does-not-exist']
        with self.assertRaisesRegex(ValueError,'unknown project source'):rc.validate(d,['E1'])
        del s['right']['source_ids']
        s['claims'][0]['cases'][0]['status']='observed'
        with self.assertRaises(ValueError):rc.validate(d,['E1'])

    def test_figure_and_source_integrity(self):
        d=fixture();s=d['project_report']['sections'][0];s['figures']=['P1']
        with self.assertRaises(ValueError):rc.validate(d,['E1'])
        d['project_report']['materials']=[dict(id='P1',title='图',origin='图册',version='R1',locator='图1',
             observed_on='2026-11-18',excerpt='图上位置',limit='终态',figure={'png_base64':'eA==','sha256':'bad','caption':'接触处'})]
        with self.assertRaisesRegex(ValueError,'PNG'):rc.validate(d,['E1'])

    def test_real_answer_matches_review_and_examples_cannot_be_imported(self):
        d=fixture()
        with sqlite3.connect(':memory:') as c:
            c.execute('CREATE TABLE research_reviews(id TEXT,data TEXT)')
            with self.assertRaisesRegex(ValueError,'reviewed research'):rc.project_report.bind_questions(d,c,False)
            r={'status':'resolved','review_result':'pass','answer':'记录了终态。','evidence_ids':['E1'],'conditions':'同一版本。','limitations':['没有连续录像。']}
            c.execute('INSERT INTO research_reviews VALUES(?,?)',('Q1',json.dumps(r)))
            rc.project_report.bind_questions(d,c,False)
            self.assertIn('没有连续录像。',rc.project_report.render(d))
            d['questions'][0]['evidence_ids'].append('another')
            with self.assertRaisesRegex(ValueError,'reviewed research'):rc.project_report.bind_questions(d,c,False)
            d['questions'][0]['evidence_ids'].pop()
            d['questions'][0]['answer']='证明了锁紧动作。'
            with self.assertRaisesRegex(ValueError,'reviewed research'):rc.project_report.bind_questions(d,c,False)
            d['project_report']['materials']=[{'id':'DEMO-001'}]
            with self.assertRaisesRegex(ValueError,'Teaching'):rc.project_report.bind_questions(d,c,False)

