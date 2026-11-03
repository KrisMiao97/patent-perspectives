"""Reader integration uses declared synthetic optics, with no online calls."""
import copy,json,tempfile,unittest
from pathlib import Path
import test_report_data


def packet(payload,details):
    apps=[p['id'] for p in payload['patents'][:2]]
    sources=[]
    for app in apps:
        doc=details[app]['documents'][0]
        ev=details[app]['evidence'][0]
        sources.append(dict(application_id=app,document_id=doc['id'],publication_number=doc['publication_number'],version=doc['version'],evidence_ids=[ev['id']]))
    evid=[e for source in sources for e in source['evidence_ids']]
    relation=dict(id='mount-relation',label='合成镜片固定关系',type='parallel',similarities='壳体固定镜片。',differences='合成方案的条件分别保留。',basis='限定在两件合成权利要求中。',historical_status='unproven',comparison_ids=['mount-comparison'],question_ids=['Q1'],evidence_ids=evid,limitations=['没有实际性能资料。'])
    findings=[dict(id='mount-'+role,finding_id='mount-finding',role=role,title='合成镜片固定比较',body='两件均披露镜片壳体，现有资料不足以排序性能。',scope='两件明确标记的合成案例。',kind='observation',role_note='本条用于界面行为检查。',question_ids=['Q1','Q2'],comparison_ids=['mount-comparison'],relation_ids=[relation['id']],use='比较镜片固定结构。',limitations=['仅限合成案例。'],alternatives=['没有同工况实测。'],next_checks=['补充合成工况定义。'],evidence_ids=evid) for role in ('management','rd','ip')]
    questions=[dict(id='Q1',level='main',origin='researcher',text='合成镜片如何固定？',status='partial',answer='壳体支持镜片。',required_evidence='完整合成权利要求。',remaining=['没有性能资料。']),dict(id='Q2',level='sub',origin='researcher',text='是否能够确定性能？',status='pending',answer='当前不能确定。',required_evidence='相同工况实测。',remaining=['等待同工况资料。'])]
    units=[dict(source,dimension_id='mount',state='disclosed',kind='disclosed',text='壳体支持镜片。',conditions='合成结构条件。',claim_levels=[dict(number=1,level='independent',depends_on=[])]) for source in sources]
    return dict(schema_version=1,id='synthetic-reader',application_ids=apps,purpose='合成界面验收，不代表真实专利事实。',audience='合成光学研究者',work_context='离线证据阅读',scope='两件合成文献。',selection_reason='用于集成测试。',questions=questions,dimensions=[dict(id='mount',label='镜片固定',definition='部件位置和连接。',question_ids=['Q1'])],terminology=[dict(id='lens',concept='镜片',scope='仅合成语境。',equivalence='contextual',entries=[dict(source,original_term='lens') for source in sources])],comparisons=[dict(id='mount-comparison',title='合成光学比较',body='比较已披露结构。',scope='两件合成文献。',question_ids=['Q1'],units=units)],relations=[relation],insights=findings)


class ResearchReaderDataTests(unittest.TestCase):
    def test_legacy_report_emits_explicit_empty_research(self):
        p,d,c=test_report_data.fixture()
        result=test_report_data.reader.assemble(p,d,c)
        self.assertEqual(result['research.js'],('PP_RESEARCH',None))
        self.assertIn('industry-research.js',result)
        self.assertIn('claim-comparisons.js',result)

    def test_research_assembly_embeds_same_version_offline_sources(self):
        p,d,c=test_report_data.fixture();p['research']=packet(p,d)
        result=test_report_data.reader.assemble(p,d,c)['research.js'][1]
        for source in result['sources'].values():
            document=result['documents'][source['document_id']]
            self.assertEqual(document['text'][source['start']:source['end']],source['quote'])
            self.assertEqual(document['publication_number'],source['publication_number'])
            self.assertEqual(document['version'],source['version'])
        self.assertEqual(len(result['insights']),3)
        self.assertNotIn('sources',p['research'])

    def test_emit_research_escapes_script_text(self):
        p,d,c=test_report_data.fixture();p['research']=packet(p,d)
        p['research']['questions'][0]['answer']='合成 </script> 条件'
        result=test_report_data.reader.assemble(p,d,c)
        with tempfile.TemporaryDirectory() as folder:
            output=Path(folder);(output/'data').mkdir()
            test_report_data.reader.emit(output,result)
            js=(output/'data/research.js').read_text(encoding='utf8')
            self.assertNotIn('</script>',js)
            data=json.loads(js[len('window.PP_RESEARCH='):-2])
            self.assertEqual(data['questions'][0]['answer'],'合成 </script> 条件')

if __name__=='__main__':unittest.main()
