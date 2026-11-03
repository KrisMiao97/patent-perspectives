"""Behavioural checks using synthetic optics evidence, never real patent findings."""
import copy, importlib.util, unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def load(name,path):
    s=importlib.util.spec_from_file_location(name,path); m=importlib.util.module_from_spec(s); s.loader.exec_module(m); return m
industry=load('industry_research',ROOT/'scripts/industry_research.py')
report=load('industry_report_data',ROOT/'scripts/report_data.py')
base=load('industry_base_fixture',ROOT/'tests/test_report_data.py')

def make_fixture():
    p,d,c=base.fixture(); appid=p['patents'][0]['id']; doc=d[appid]['documents'][0]
    def module(summary):
        return {'status':'supported','summary':summary,'conditions':'仅用于合成光学案例的行为检查。','unknowns':'尚无现场长期运行数据。','source_ids':['S-P']}
    transfer=module('可研究其他设备的镜片固定方法。')
    transfer['candidates']=[{'domain':'合成测量仪器','shared_function':'保持镜片位置','mechanism':'通过弹性支撑限制镜片移动','differences':'振动和温度条件不同','adaptation':'重新选择支撑材料与预紧量','test':'同温度和振动条件下测量位移','source_ids':['S-R']}]
    forecast=module('候选演进为降低装配校准步骤，尚未验证。')
    forecast['hypotheses']=[{'horizon':'未来三年，取决于测试结果','change':'减少装配调节步骤','driver':'减少定位误差','blocker':'制造公差尚未验证','trigger':'相同工况试验通过','falsifier':'热循环后位移增大','source_ids':['S-F','S-P']}]
    maturity=module('组件已有公开结构，系统集成仍待验证。')
    maturity.update(rubric='组件验证：公开可复查样件结果；系统验证：同工况整机结果；部署验证：真实使用记录。',dimensions=[{'name':'组件','stage':'已描述，验证不足','basis':'合成权利要求只披露结构','source_ids':['S-F']},{'name':'系统集成','stage':'待验证','basis':'手册没有提供整机长期测试','source_ids':['S-P']}])
    selection=module('在合成轻载场景中保留候选，不给性能排名。')
    selection.update(scenario='合成相机模组的轻载镜片固定',criteria=[{'name':'位移','priority':'必要约束','measure':'相同温度及振动下测量'},{'name':'装配','priority':'次要偏好','measure':'记录相同步骤与良率'}],recommendation='先做同工况样件测试，再决定是否入选。',reversal='若热循环位移超限，撤回候选推荐。')
    route={'id':'route-a','name':'弹性镜片定位（合成示例）','problem':'定位稳定性','mechanism':'支架安装在壳体内并固定镜片。','major':True,'selection_reason':'对应本次明确研究的问题，非专利数量排名。','source_ids':['S-F'], 'transfer':transfer,'forecast':forecast,'maturity':maturity,'selection':selection}
    route2={'id':'route-b','name':'刚性镜片定位（合成示例）','problem':'装配定位','mechanism':'手册描述刚性夹持，内部实现未核实。','major':False,'selection_reason':'用作对照候选。','source_ids':['S-P']}
    data={'schema_version':1,'target_company_id':'target','scope':{'topic':'合成光学研究演示，不代表真实公司事实','as_of':p['run']['as_of_date'],'selection_basis':'本次选取的合成申请及对照资料。'},'companies':[{'id':'target','name':p['run']['company'],'role':'合成目标公司'},{'id':'peer','name':'SYNTHETIC REFERENCE','role':'合成比较对象'}], 'sources':[
        {'id':'S-F','kind':'F','title':'合成完整权利要求','locator':'权利要求1','url':'https://example.test/patent','application_id':appid,'document_id':doc['id'],'evidence_ids':['quote-0']},
        {'id':'S-P','kind':'P','title':'合成官方产品手册','locator':'第2页，定位结构','url':'https://example.test/manual'},
        {'id':'S-R','kind':'R','title':'合成实验研究','locator':'方法第3节','url':'https://example.test/research'},
        {'id':'S-O','kind':'O','title':'合成公司业务自述','locator':'技术业务段落','url':'https://example.test/company'},
        {'id':'S-L','kind':'L','title':'合成同族目录记录','locator':'本件简单同族列表','url':'https://example.test/family'}],
        'tasks':[{'id':'task-'+kind,'kind':kind,'status':'supported','question':'该合成案例的'+kind+'研究问题是什么？','answer':'此处仅为合成测试，结论不用于实际决策。','conditions':'限定为合成案例的已取得资料。','source_ids':['S-F','S-P']} for kind in ('project','competition','profile','selection','forecast')],
        'routes':[route,route2], 'matrix':[
            {'company_id':'target','route_id':'route-a','claims':[{'kind':'F','text':'壳体内的支架固定镜片。','source_ids':['S-F']},{'kind':'P','text':'手册描述定位功能，未证明采用某件专利。','source_ids':['S-P']}]},
            {'company_id':'peer','route_id':'route-a','claims':[{'kind':'R','text':'研究讨论相似工况的定位问题。','source_ids':['S-R']},{'kind':'O','text':'公司公开描述其定位业务。','source_ids':['S-O']}]},
            {'company_id':'target','route_id':'route-b','claims':[{'kind':'U','text':'本次待补证。','source_ids':[]}]},
            {'company_id':'peer','route_id':'route-b','claims':[{'kind':'L','text':'目录中存在定位线索，全文未取得。','source_ids':['S-L']}]}],
        'jurisdiction_cases':[{'id':'case-a','label':'合成选定案例','company_id':'target','application_id':appid,'observed_at':p['run']['as_of_date'],'source_ids':['S-L'],'authorities':[{'code':'US','status':'simple','source_ids':['S-L'],'note':'合成简单同族记录中存在。'},{'code':'EP','status':'extended','source_ids':['S-L'],'note':'仅合成扩展同族记录，未核权。'},{'code':'JP','status':'unknown','source_ids':[],'note':'未取得相关记录，非无布局。'}]}]}
    for source in data['sources']: source['observed_at']=p['run']['as_of_date']; source['publication_date']=None
    for criterion in selection['criteria']: criterion['source_ids']=['S-P']; criterion['status']='supported'
    data['jurisdiction_cases'][0]['authorities'][0]['member_publication_numbers']=['USSYNTHETIC0A']
    data['jurisdiction_cases'][0]['authorities'][1]['member_publication_numbers']=['EPSYNTHETIC0A']
    c['industry_research']=data
    return p,d,c

class IndustryTests(unittest.TestCase):
    def run_valid(self,fixture=None):
        p,d,c=fixture or make_fixture(); return industry.prepare(p,d,c)
    def reject(self,edit):
        p,d,c=make_fixture(); edit(p,d,c)
        with self.assertRaises(industry.IndustryResearchError): industry.prepare(p,d,c)
    def test_absent_keeps_legacy_behaviour(self):
        p,d,c=base.fixture(); self.assertIsNone(industry.prepare(p,d,c))
    def test_complete_fixture_and_multisource_cell(self):
        result=self.run_valid(); self.assertEqual(len(result['matrix']),4)
        self.assertEqual([x['kind'] for x in result['matrix'][0]['claims']],['F','P'])
        self.assertEqual(result['sources'][0]['version'],'published')
    def test_identity_cutoff_and_target_match(self):
        self.reject(lambda p,d,c:c['industry_research']['scope'].update(as_of='1999-01-01'))
        self.reject(lambda p,d,c:c['industry_research']['companies'][0].update(name='Different company'))
    def test_unknown_reference_rejected(self):
        self.reject(lambda p,d,c:c['industry_research']['matrix'][0]['claims'][0].update(source_ids=['missing']))
    def test_source_category_cannot_be_promoted(self):
        self.reject(lambda p,d,c:c['industry_research']['matrix'][0]['claims'][0].update(source_ids=['S-P']))
    def test_partial_or_description_is_not_full_claims(self):
        for patch in ({'complete':False},{'document_type':'description'},{'rejection_review_ids':['rejected']}):
            self.reject(lambda p,d,c,patch=patch:d[p['patents'][0]['id']]['documents'][0].update(patch))
    def test_full_source_must_be_actually_read_as_main_document(self):
        self.reject(lambda p,d,c:p['patents'][0].update(analysis_status='pending'))
        self.reject(lambda p,d,c:d[p['patents'][0]['id']]['analysis'].update(document_id='another-doc'))
    def test_cross_version_quote_or_span_rejected(self):
        for patch in ({'version':'granted'},{'quote':'not in original'},{'end':999},{'application_id':'other'}):
            self.reject(lambda p,d,c,patch=patch:d[p['patents'][0]['id']]['evidence'][0].update(patch))
    def test_major_route_needs_all_four_modules(self):
        for field in industry.MODULES:
            self.reject(lambda p,d,c,field=field:c['industry_research']['routes'][0].pop(field))
    def test_unknown_modules_are_allowed_and_not_scored(self):
        p,d,c=make_fixture(); r=c['industry_research']['routes'][0]
        r['maturity']={'status':'unknown','summary':'成熟度暂不能判定。','conditions':'缺整机测试。','unknowns':'需要同工况整机证据。','source_ids':[]}
        self.assertEqual(self.run_valid((p,d,c))['routes'][0]['maturity']['status'],'unknown')
    def test_maturity_needs_rubric_and_forecast_needs_falsifier(self):
        self.reject(lambda p,d,c:c['industry_research']['routes'][0]['maturity'].pop('rubric'))
        self.reject(lambda p,d,c:c['industry_research']['routes'][0]['forecast']['hypotheses'][0].pop('falsifier'))
    def test_unsubstantiated_task_requires_unknown_reason(self):
        self.reject(lambda p,d,c:c['industry_research']['tasks'][0].update(source_ids=[]))
        p,d,c=make_fixture(); c['industry_research']['tasks'][0].update(status='unknown',source_ids=[],reason='本次资料不足。')
        self.run_valid((p,d,c))
    def test_unknown_never_absence_or_zero(self):
        self.reject(lambda p,d,c:c['industry_research']['matrix'][2]['claims'][0].update(state='absent'))
        self.reject(lambda p,d,c:c['industry_research']['matrix'][2]['claims'][0].update(count=0))
    def test_missing_cells_fill_as_unknown_only(self):
        p,d,c=make_fixture(); c['industry_research']['matrix']=[]
        self.assertTrue(all(x['claims'][0]['kind']=='U' for x in self.run_valid((p,d,c))['matrix']))
    def test_family_cannot_claim_companywide_status(self):
        self.reject(lambda p,d,c:c['industry_research']['jurisdiction_cases'][0]['authorities'][0].update(legal_status='有效'))
        self.reject(lambda p,d,c:c['industry_research']['jurisdiction_cases'][0]['authorities'][0].update(status='absent'))
    def test_unsafe_source_links_rejected(self):
        for url in ('javascript:alert(1)','data:text/html,test','https://user:secret@example.test/x','https://example.test/\npath'):
            self.reject(lambda p,d,c,url=url:c['industry_research']['sources'][1].update(url=url))
        for path in ('../secret.pdf','C:/secret.pdf','%2e%2e/secret.pdf','\\server\\secret'):
            self.reject(lambda p,d,c,path=path:c['industry_research']['sources'][1].update(local_path=path))
    def test_description_fallback_has_distinct_source_class(self):
        p,d,c=make_fixture(); src=c['industry_research']['sources'][0]; src['kind']='D'
        doc=d[p['patents'][0]['id']]['documents'][0]; doc['document_type']='description'
        doc['text']='The synthetic optical housing holds a lens.'
        e=d[p['patents'][0]['id']]['evidence'][0]; e['start']=doc['text'].index(e['quote']); e['end']=e['start']+len(e['quote']); e['locator']={'paragraph':'0003'}
        c['industry_research']['matrix'][0]['claims'][0]['kind']='D'
        self.assertEqual(self.run_valid((p,d,c))['sources'][0]['kind'],'D')
    def test_actual_observation_after_cutoff_is_not_rewritten(self):
        p,d,c=make_fixture(); c['industry_research']['sources'][0]['observed_at']='2025-01-10'
        source=self.run_valid((p,d,c))['sources'][0]
        self.assertEqual(source['observed_at'],'2025-01-10'); self.assertTrue(source['observed_after_cutoff'])
    def test_source_observation_date_is_required(self):
        self.reject(lambda p,d,c:c['industry_research']['sources'][0].pop('observed_at'))
    def test_later_publication_requires_explicit_retrospective_use(self):
        p,d,c=make_fixture(); c['industry_research']['sources'][2]['publication_date']='2025-01-10'
        with self.assertRaises(industry.IndustryResearchError): self.run_valid((p,d,c))
        c['industry_research']['sources'][2]['temporal_use']='retrospective'
        with self.assertRaises(industry.IndustryResearchError): self.run_valid((p,d,c))
        c['industry_research']['routes'][0]['transfer']['candidates'][0]['temporal_use']='retrospective'
        c['industry_research']['matrix'][1]['claims'][0]['temporal_use']='retrospective'
        self.assertTrue(self.run_valid((p,d,c))['sources'][2]['publication_after_cutoff'])
    def test_selection_criterion_requires_evidence_or_explicit_unknown(self):
        self.reject(lambda p,d,c:c['industry_research']['routes'][0]['selection']['criteria'][0].update(source_ids=[]))
        p,d,c=make_fixture(); c['industry_research']['routes'][0]['selection']['criteria'][0].update(status='unknown',reason='缺少同工况指标要求。',source_ids=[])
        self.run_valid((p,d,c))
    def test_one_unknown_maturity_dimension_does_not_erase_other_evidence(self):
        p,d,c=make_fixture(); dimensions=c['industry_research']['routes'][0]['maturity']['dimensions']
        dimensions[1].update(status='unknown',reason='没有整机测试数据。',source_ids=[])
        result=self.run_valid((p,d,c))['routes'][0]['maturity']['dimensions']
        self.assertEqual(result[0]['status'],'supported'); self.assertEqual(result[1]['status'],'unknown')
    def test_family_presence_requires_member_identifiers(self):
        self.reject(lambda p,d,c:c['industry_research']['jurisdiction_cases'][0]['authorities'][0].pop('member_publication_numbers'))

    def test_external_reference_corpus_never_changes_target_population(self):
        p,d,c=make_fixture(); peer,peer_details,_=base.fixture('SYNTHETIC REFERENCE',2014,'JP')
        c['industry_reference_corpora']=[{'id':'peer-run','payload':peer,'details':peer_details}]
        c['industry_research']['sources'].append({'id':'S-PEER-F','kind':'F','title':'合成对照公司完整权利要求','locator':'权利要求1','url':'https://example.test/peer-patent','observed_at':'2020-12-31','application_id':peer['patents'][0]['id'],'document_id':'doc-0','evidence_ids':['quote-0'],'corpus_id':'peer-run'})
        c['industry_research']['matrix'][1]['claims'].append({'kind':'F','text':'合成对照的壳体固定镜片。','source_ids':['S-PEER-F']})
        result=report.assemble(p,d,c)
        self.assertEqual(len(result['report.js'][1]['portfolio']['rows']),4)
        source=result['industry-research.js'][1]['sources'][-1]
        self.assertEqual(source['corpus_company'],'SYNTHETIC REFERENCE')
        self.assertIn('未复验',source['corpus_review_note'])
        self.assertTrue(all(x['id'].startswith('US:') for x in p['patents']))
    def test_external_corpus_cannot_mask_conflicting_originals(self):
        p,d,c=make_fixture(); peer,peer_details=copy.deepcopy(p),copy.deepcopy(d)
        peer_details[p['patents'][0]['id']]['documents'][0]['text']+=' Changed source.'
        c['industry_reference_corpora']=[{'id':'conflicting','payload':peer,'details':peer_details}]
        with self.assertRaises(industry.IndustryResearchError): self.run_valid((p,d,c))
    def test_missing_or_reserved_reference_corpus_rejected(self):
        self.reject(lambda p,d,c:c['industry_research']['sources'][0].update(corpus_id='missing'))
        p,d,c=make_fixture(); c['industry_reference_corpora']=[{'id':'main','payload':copy.deepcopy(p),'details':copy.deepcopy(d)}]
        with self.assertRaises(industry.IndustryResearchError): self.run_valid((p,d,c))

    def test_no_input_mutation(self):
        p,d,c=make_fixture(); before=copy.deepcopy(c); self.run_valid((p,d,c)); self.assertEqual(c,before)
    def test_report_data_integration_optional_and_present(self):
        p,d,c=make_fixture(); assembled=report.assemble(p,d,c)
        self.assertEqual(assembled['industry-research.js'][0],'PP_INDUSTRY')
        self.assertEqual(assembled['industry-research.js'][1]['target_company_id'],'target')
        c.pop('industry_research'); self.assertIsNone(report.assemble(p,d,c)['industry-research.js'][1])
    def test_js_emitter_escapes_html_breakouts(self):
        import tempfile
        with tempfile.TemporaryDirectory() as folder:
            (Path(folder)/'data').mkdir(); report.write_js(folder,'fixture.js','TEST',{'text':'</script><script>alert(1)</script>'})
            result=(Path(folder)/'data/fixture.js').read_text(encoding='utf8')
            self.assertNotIn('</script>',result); self.assertIn('\\u003c',result)

if __name__=='__main__': unittest.main()
