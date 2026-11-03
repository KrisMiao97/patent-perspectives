"""Behavior tests: isolated SYNTHETIC optics; no real company or online calls."""
import copy,json,unittest
import test_integrity

class ResearchTests(unittest.TestCase):
 def setUp(self):
  self.f=test_integrity.IntegrityTests(methodName='test_missing_fulltext_never_completes_or_renders');self.f.setUp();self.addCleanup(self.f.doCleanups);self.e=test_integrity.engine;self.c=self.f.db
  self.apps=self.f.seed([self.f.record(1),self.f.record(2)])
  self.sources=[]
  for n,a in enumerate(self.apps,1):
   d=self.f.document(n,text='1. A synthetic lens is held in an optical housing.\n2. A synthetic lens uses a focus ring.')
   x=self.f.analysis_input(d,quote='synthetic lens');x['evidence'][0].update(start=5,end=19)
   doc=self.c.execute('SELECT * FROM documents WHERE id=?',(d['document_id'],)).fetchone()
   x.update(analysis_author='synthetic-author',fields={k:x['fields'].get(k,[]) for k in self.e.FIELDS},
      whole_document_review=dict(document_id=doc['id'],source_text_hash=doc['text_hash'],reading_mode='whole',complete=True,capacity_basis='Both short synthetic claims fit with reasoning space.'),
      tail_check=dict(complete=True,quote=doc['text'][-40:],claim_number=2))
   self.f.analyze(d,**x)
   self.sources.append(dict(application_id=a,document_id=d['document_id'],publication_number=doc['publication_id'],version=json.loads(doc['data'])['version'],evidence_ids=['evidence-'+a]))
  units=[dict(s,dimension_id='mount',state='disclosed',kind='disclosed',text='Synthetic optical mounting',conditions='No vibration test acquired',field_refs=['technical_means'],term_ids=['lens'],claim_levels=[dict(number=1,level='independent')]) for s in self.sources]
  rel=dict(id='optics-parallel',source=self.apps[0],target=self.apps[1],type='parallel',kind='inference',label='Optical mount comparison',endpoints=self.sources,evidence_ids=[i for s in self.sources for i in s['evidence_ids']],question_ids=['q'],comparison_ids=['c'],similarities='Both have optical housings',differences='Scope of separate synthetic claims',basis='Structural comparison only',historical_status='unproven',limitations=['No historical evidence'])
  finds=[dict(id='optics-'+r,finding_id='mount',role=r,kind='observation',title='Synthetic mount finding',body='Synthetic mount differences need test',scope='Two synthetic claims',limitations=['Synthetic only'],question_ids=['q'],comparison_ids=['c'],relation_ids=[rel['id']],patent_ids=self.apps,evidence_ids=rel['evidence_ids'],use='Compare optical assembly',alternatives=['No performance data'],next_checks=['Vibration tests']) for r in self.e.ROLES]
  self.p=dict(schema_version=1,id='synthetic-optics',purpose='Compare lens mounts',audience='Optical engineers',work_context='Fixture validation',scope='Two synthetic optics',selection_reason='Optics only',application_ids=self.apps,questions=[dict(id='q',level='main',origin='researcher',text='How are lenses held?',required_evidence='Synthetic original claims',status='partial',answer='Synthetic housing disclosed',remaining=['Vibration evidence'])],dimensions=[dict(id='mount',label='Optical mounting',definition='Lens and housing relationship',question_ids=['q'])],terminology=[dict(id='lens',concept='Lens',scope='Synthetic optic',equivalence='contextual',entries=[dict(s,original_term='synthetic lens') for s in self.sources])],comparisons=[dict(id='c',title='Optics comparison',body='Original synthetic structures',scope='Two synthetic claims',question_ids=['q'],units=units)],relations=[rel],insights=finds)
  run=self.e.run_info(self.c);run['scope']['require_research_quality']=True;self.e.set_meta(self.c,'run',run)
 def load(self,p=None):
  with self.c:return self.e.research_module().import_workflow(self.c,self.e.research_context(),p or self.p)
 def rejected(self,change):
  p=copy.deepcopy(self.p);change(p)
  with self.assertRaises((ValueError,KeyError)):self.load(p)
  self.assertIsNone(self.e.get_meta(self.c,'research_workflow'))
 def complete(self,p=None):
  p=copy.deepcopy(p or self.p);self.load(p)
  quality=self.e.research_quality_module();ctx=self.e.research_quality_context()
  path=self.f.directory/'quality-manifest.json';quality.export_work(self.c,path,ctx)
  manifest=json.loads(path.read_text(encoding='utf-8'));reviews=[]
  for item in manifest['semantic_reviews']:
   ids=item['evidence_ids']
   reviews.append(dict(application_id=item['application_id'],analysis_fingerprint=item['analysis_fingerprint'],analysis_author='synthetic-author',reviewer='synthetic-independent-reviewer',independent=True,reviewed_original_sources=True,result='pass',evidence_ids=ids,checks={k:dict(status='pass',basis='Checked complete synthetic original sources.',evidence_ids=ids) for k in quality.CHECKS}))
  quality.import_review(self.c,reviews,ctx)
  for q in p['questions']:
   item=next(v for v in manifest['research_reviews'] if v['question_id']==q['id'])
   quality.import_research(self.c,dict(question_id=q['id'],plan_hash=item['plan_hash'],population_hash=item['population_hash'],status='resolved',answer=q['answer'],conditions='Synthetic two-claim comparison only.',limitations=['Synthetic only'],evidence_ids=[i for s in self.sources for i in s['evidence_ids']],comparison=dict(status='compared',basis='Compared the complete synthetic claim sets.'),counterevidence=dict(search_scope='Both synthetic sources.',findings='No contradictory holding relationship.',impact='No performance conclusion supported.'),analysis_author='synthetic-research-author',reviewer='synthetic-research-reviewer',independent=True,reviewed_original_sources=True,review_result='pass'),ctx)
   q.update(status='answered',remaining=[])
  self.load(p);return p
 def test_generic_roundtrip_and_official_render(self):
  self.complete();self.assertEqual(self.e.validate_run(self.c)['status'],'complete')
  p=self.e.research_module().export(self.c,self.e.research_context());self.assertEqual(p['dimensions'][0]['label'],'Optical mounting')
  out=self.f.directory/'optics';self.e.render(self.c,out)
  data=json.loads((out/'data/research.js').read_text(encoding='utf-8')[len('window.PP_RESEARCH='):-2]);self.assertEqual(data['comparisons'][0]['units'][0]['state'],'disclosed');self.assertIn(self.sources[0]['document_id'],data['documents'])
 def test_missing_entire_document_supported(self):
  p=copy.deepcopy(self.p)
  for u in p['comparisons'][0]['units']:u.update(document_id=None,version='synthetic-unacquired-version',state='not_obtained',kind='unknown',reason='Whole version not acquired',evidence_ids=[],claim_levels=[])
  self.load(p);got=self.e.research_module().export(self.c,self.e.research_context());self.assertIsNone(got['comparisons'][0]['units'][0]['document_id'])
 def test_missing_document_wrong_publication_rejected(self):
  self.rejected(lambda p:p['comparisons'][0]['units'][0].update(document_id=None,publication_number='UNKNOWN',version='unacquired',state='not_obtained',kind='unknown',reason='Missing',evidence_ids=[],claim_levels=[]))
 def test_incomplete_role_views_rejected(self):self.rejected(lambda p:p['insights'].pop())
 def test_replacing_question_set_retires_old_views_without_deleting(self):
  self.load();oldids={v['id'] for v in self.e.active_insights(self.c)}
  p=copy.deepcopy(self.p);p['id']='second-workflow';p['questions'][0]['id']='new-q'
  for d in p['dimensions']:d['question_ids']=['new-q']
  for d in p['comparisons']:d['question_ids']=['new-q']
  for d in p['relations']:d.update(id='new-'+d['id'],question_ids=['new-q'])
  for d in p['insights']:d.update(id='new-'+d['id'],question_ids=['new-q'],relation_ids=[p['relations'][0]['id']])
  quality=self.e.research_quality_module();quality.import_plan(self.c,dict(questions=[dict(id='new-q',question=p['questions'][0]['text'],application_ids=self.apps,selection_basis='Optics only')],revision_reason='Explicit synthetic replacement question.'),self.e.research_quality_context())
  self.complete(p);self.assertEqual(self.e.validate_run(self.c)['status'],'complete')
  self.assertFalse(oldids&{v['id'] for v in self.e.active_insights(self.c)})
  self.assertEqual(len(self.e.rows_data(self.c,'insights')),6);self.assertEqual(len(self.e.active_relations(self.c)),1)
  self.assertEqual(len(self.e.rows_data(self.c,'relations')),2)
 def test_relation_limitations_string_rejected(self):self.rejected(lambda p:p['relations'][0].update(limitations='Wrong type'))
 def test_parent_claim_string_rejected(self):self.rejected(lambda p:p['comparisons'][0]['units'][0].update(claim_levels=[dict(number=1,level='dependent',depends_on='1')]))
 def test_question_id_string_rejected(self):self.rejected(lambda p:p['insights'][0].update(question_ids='q'))
 def test_question_reference_rejected(self):self.rejected(lambda p:p['insights'][0].update(question_ids=['absent']))
 def test_comparison_question_rejected(self):self.rejected(lambda p:p['comparisons'][0].update(question_ids=['absent']))
 def test_wrong_document_rejected(self):self.rejected(lambda p:p['comparisons'][0]['units'][0].update(document_id=self.sources[1]['document_id']))
 def test_wrong_version_rejected(self):self.rejected(lambda p:p['comparisons'][0]['units'][0].update(version='unacquired'))
 def test_relation_endpoint_rejected(self):self.rejected(lambda p:p['relations'][0].update(target='absent'))
 def test_one_sided_relation_rejected(self):self.rejected(lambda p:p['relations'][0].update(endpoints=[self.sources[0]]))
 def test_dates_cannot_prove_history(self):self.rejected(lambda p:p['relations'][0].update(type='inheritance',historical_status='supported',basis='2020 precedes 2021'))
 def test_unknown_states_roundtrip(self):
  for state in ['not_disclosed','not_obtained','not_applicable']:
   p=copy.deepcopy(self.p)
   for u in p['comparisons'][0]['units']:
    u.update(state=state,kind='unknown',reason='Synthetic missing scope',evidence_ids=[],claim_levels=[])
    if state=='not_disclosed':u['reviewed_claim_numbers']=[1,2]
   self.load(p);got=self.e.research_module().export(self.c,self.e.research_context());self.assertEqual(got['comparisons'][0]['units'][0]['state'],state)
 def test_absence_requires_full_scope(self):
  self.rejected(lambda p:p['comparisons'][0]['units'][0].update(state='not_disclosed',kind='unknown',reason='missing',reviewed_claim_numbers=[1]))
 def test_role_facts_cannot_diverge(self):self.rejected(lambda p:p['insights'][1].update(body='Contradictory fact'))
 def test_workflow_change_invalidates(self):
  self.load();w=self.e.get_meta(self.c,'research_workflow');w['scope']='Changed question scope';self.e.set_meta(self.c,'research_workflow',w);self.assertEqual(self.e.research_module().check(self.c,self.e.research_context())[0]['code'],'research_workflow_invalid')
 def test_scope_change_invalidates(self):
  self.load();r=self.e.run_info(self.c);r['as_of_date']='2026-10-21';self.e.set_meta(self.c,'run',r);self.assertEqual(self.e.research_module().check(self.c,self.e.research_context())[0]['code'],'research_workflow_invalid')
 def test_evidence_change_invalidates_and_blocks_render(self):
  self.load();row=self.c.execute('SELECT data FROM evidence LIMIT 1').fetchone();v=json.loads(row[0]);v['quote']='Changed';self.c.execute('UPDATE evidence SET data=? WHERE id=?',(json.dumps(v),v['id']));self.assertIn('research_workflow_invalid',{x['code'] for x in self.e.validate_run(self.c)['errors']});self.f.assert_blocked_render()
 def test_linked_relation_change_invalidates(self):
  self.load();v=self.e.rows_data(self.c,'relations')[0];v['differences']='Changed interpretation';self.c.execute('UPDATE relations SET data=? WHERE id=?',(json.dumps(v),v['id']));self.assertEqual(self.e.research_module().check(self.c,self.e.research_context())[0]['code'],'research_workflow_invalid')
 def test_legacy_without_workflow(self):
  run=self.e.run_info(self.c);run['scope']['require_research_quality']=False;self.e.set_meta(self.c,'run',run)
  for r in self.e.ROLES:self.e.import_insights(self.c,[self.f.insight(r,self.apps[0])])
  self.assertFalse(self.e.research_module().check(self.c,self.e.research_context()));self.assertIsNone(self.e.research_module().export(self.c,self.e.research_context()));self.assertEqual(self.e.validate_run(self.c)['status'],'complete')
if __name__=='__main__':unittest.main()
