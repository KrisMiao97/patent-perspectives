"""Contract safety tests use synthetic evidence, not patent-effect assertions."""
import copy
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import reader_contract as rc

def fixture():
    return {'version':1,'purpose':'解释机构','scope':'仅一件文献','as_of':'2026-11-16',
        'primary_role':'rd','common_boundary':'目标效果未验证',
        'market_search':{'permission':'not_requested','performed':False,'statement':'未开展市场搜索'},
        'role_guides':{'rd':{'question':'如何动作','answer':'沿导向移动','focus':'阅读原文','evidence_ids':['E1']}},
        'questions':[{'id':'Q1','question':'如何工作','answer':'沿导向移动','boundary':'仅结构记载','status':'answered','evidence_ids':['E1']}]}

class ReaderContractTests(unittest.TestCase):
    def test_no_market_confirmation_blocks_performed_search(self):
        d=fixture();d['market_search']['performed']=True
        with self.assertRaisesRegex(ValueError,'confirmation'):rc.validate(d,['E1'])
    def test_approval_needs_scope_and_user_record(self):
        d=fixture();d['market_search']['permission']='approved'
        with self.assertRaises(ValueError):rc.validate(d,['E1'])
        d['market_search'].update(confirmation='user message 1',scope={k:'明确范围' for k in ('question','objects','regions','period','sources','depth')},performed=True)
        rc.validate(d,['E1'])
    def test_cannot_drop_promised_question_without_confirmation(self):
        d=fixture();d['questions'][0]['status']='scope_changed'
        with self.assertRaisesRegex(ValueError,'user_confirmation'):rc.validate(d,['E1'])
    def test_unknown_original_evidence_is_rejected(self):
        d=fixture();d['role_guides']['rd']['evidence_ids']=['invented']
        with self.assertRaisesRegex(ValueError,'unknown evidence'):rc.validate(d,['E1'])
    def test_patent_alone_does_not_support_adoption_stage(self):
        d=fixture();d['assessments']=[dict(kind='lifecycle',status='supported',subject='滤网',conclusion='增长',reasoning='数量增加',boundary='样本',review_trigger='新资料',evidence_ids=['E1'],comparison_basis='早期样本',alternative_explanation='重复申请')]
        with self.assertRaisesRegex(ValueError,'external evidence'):rc.validate(d,['E1'])
        d['assessments'][0].update(status='undetermined',conclusion='阶段未定')
        rc.validate(d,['E1'])
    def test_reading_steps_survive_and_are_escaped(self):
        result=rc.blocks_html([{'heading':'动作','text':'部件位置','steps':['压回','<script>not executable</script>']}])
        self.assertIn('<ol',result);self.assertIn('&lt;script&gt;',result);self.assertNotIn('<script>',result)
    def test_all_roles_share_visible_boundary(self):
        d=fixture();d['role_guides']['ip']=copy.deepcopy(d['role_guides']['rd'])
        rc.validate(d,['E1']);result=rc.render(d)
        self.assertEqual(result.count('目标效果未验证'),1)
        self.assertLess(result.index('目标效果未验证'),result.index('data-reader-guide'))

    def test_scene_and_mechanism_blocks_use_shared_owned_evidence(self):
        d=fixture()
        d.update(version=2, reviewed_on='2026-11-16', reading_context={
            'reader_background':'无先备经验',
            'scene_title':'怎样开盖',
            'scene':'按下卡扣，才能从容器上拿起盖子。',
            'walkthroughs':[{
                'application_id':'app1', 'title':'卡扣',
                'summary':'按压带动卡扣离开卡槽',
                'boundary':'仅记载按压操作',
                'blocks':[{'heading':'按压开盖','text':'从外侧按下卡扣','evidence_ids':['E1']}],
            }],
        })
        rc.validate(d,['E1'],evidence_owners={'E1':'app1'})
        brief=rc.render(d)
        self.assertLess(brief.index('怎样开盖'),brief.index('data-reader-guide'))
        self.assertIn('data-reader-source="E1"',rc.render(d,'mechanisms'))
        with self.assertRaisesRegex(ValueError,'belongs to another application'):
            rc.validate(d,['E1'],evidence_owners={'E1':'app2'})
        d['reading_context']['walkthroughs'][0]['blocks'][0]['evidence_ids']=[]
        with self.assertRaisesRegex(ValueError,'source anchors'):
            rc.validate(d,['E1'])

    def test_many_source_links_fold_without_hiding_boundary(self):
        d=fixture();d['role_guides']['rd']['evidence_ids']=['E1','E2','E3','E4']
        rc.validate(d,['E1','E2','E3','E4']);result=rc.render(d)
        self.assertIn('<details class="reader-source-list">',result)
        self.assertNotIn('<details class="reader-source-list" open',result)
        self.assertLess(result.index('reader-boundary'),result.index('reader-source-list'))
        self.assertEqual(result.count('data-reader-source='),4)

if __name__=='__main__':unittest.main()
