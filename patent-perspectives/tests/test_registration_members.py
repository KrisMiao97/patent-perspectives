"""Synthetic official-format evidence, never real patent data or remote requests."""
import copy,hashlib,json,unittest
import test_integrity as fixture_support
engine=fixture_support.engine

class RegistrationMemberTests(unittest.TestCase):
 setUp=fixture_support.IntegrityTests.setUp
 record=fixture_support.IntegrityTests.record
 search=fixture_support.IntegrityTests.search
 seed=fixture_support.IntegrityTests.seed
 doc_input=fixture_support.IntegrityTests.doc_input
 document=fixture_support.IntegrityTests.document
 analysis_input=fixture_support.IntegrityTests.analysis_input
 analyze=fixture_support.IntegrityTests.analyze
 insight=fixture_support.IntegrityTests.insight

 def fixtures(self):
  self.ep='EP:EP2022000001';self.de='DE:DE602022000001'
  self.ep_pn='EP9999001B1';self.de_pn='DE602022000001T2'
  self.seed([self.record(1,pn=self.ep_pn,apno='EP2022000001',authority='EP',legal_status='active',current_assignee='SYNTHETIC EP OWNER'),
             self.record(2,pn=self.de_pn,apno='DE602022000001',authority='DE',legal_status='expired',current_assignee='SYNTHETIC DE OWNER')])
  self.html=self.directory/'synthetic-register.html';self.xml=self.directory/'synthetic-epo.xml'
  self.html.write_text('<html><table id="stammdaten_tabelle">'+''.join('<tr><td data-th="Feld">'+k+'</td><td data-th="Inhalt">'+v+'</td></tr>' for k,v in [('DAKZ','60 2022 000001.1'),('EAKZ','22 00 0001.9'),('EPN','9999001')])+'</table></html>',encoding='utf-8')
  self.xml.write_text('<ep-patent-document country="EP" doc-number="9999001" kind="B1"><SDOBI><B200><B210>22000001.9</B210></B200></SDOBI></ep-patent-document>',encoding='utf-8')
  self.sources=[self.source(self.html,'https://register.dpma.de/DPMAregister/pat/register?AKZ=E220000019','text/html'),self.source(self.xml,'https://data.epo.org/publication-server/rest/v1.2/patents/EP9999001NWB1/document.xml','application/xml')]
  return {'adapter':'dpma_eakz_epn_v1','relation_type':'national_register_member_of_european_application',
    'member_application_id':self.de,'canonical_filing_application_id':self.ep,'member_publication_ids':[self.de_pn],
    'official_register':{**self.sources[0],'fields':{'DAKZ':'60 2022 000001.1','EAKZ':'22 00 0001.9','EPN':'9999001'}},
    'canonical_filing_evidence':{**self.sources[1],'publication_number':self.ep_pn},
    'reviewer':'Synthetic reviewer','basis':'SYNTHETIC exact same-record official-format identity fixture, not family matching.'}

 def source(self,file,url,media):
  sha=hashlib.sha256(file.read_bytes()).hexdigest();receipt=file.with_suffix('.receipt.json')
  value={'sha256':sha,'bytes':file.stat().st_size,'local_file':file.name,'final_url':url,'acquired_at':'2026-10-21T00:00:00Z','content_type':media,'status':200}
  receipt.write_text(json.dumps([value]),encoding='utf-8')
  return {'source_class':'official','artifact':file.name,'sha256':sha,'source_url':url,'acquired_at':value['acquired_at'],
    'receipt':{'artifact':receipt.name,'sha256':hashlib.sha256(receipt.read_bytes()).hexdigest(),'record_path':[0]}}

 def import_mapping(self,p):
  with self.db:return engine.import_registration_members(self.db,p)

 def ep_document(self):
  return self.document(publication_number=self.ep_pn,returned_publication_number=self.ep_pn,application_number='EP2022000001')

 def de_document(self):
  return self.document(publication_number=self.de_pn,returned_publication_number=self.de_pn,application_number='DE602022000001')

 def test_bridge_retains_every_source_and_query_and_demands_canonical_fulltext(self):
  p=self.fixtures();before={t:[tuple(r) for r in self.db.execute('SELECT * FROM '+t)] for t in ('applications','publications','pages','query_results','queries')}
  self.assertEqual(engine.coverage(self.db)['technical_applications'],2)
  self.import_mapping(p);cov=engine.coverage(self.db)
  self.assertEqual((cov['applications'],cov['technical_applications'],cov['raw_included_application_records'],cov['raw_technical_application_records']),(1,1,2,2))
  self.assertEqual(cov['registration_count_bridge']['adjustments'][0]['application_delta'],-1)
  self.assertEqual(cov['technical_fulltext'],0);self.assertEqual(cov['technical_analyzed'],0)
  self.assertEqual(cov['registration_member_qualified_own_texts'],0)
  for t,rows in before.items():self.assertEqual(rows,[tuple(r) for r in self.db.execute('SELECT * FROM '+t)],t)
  report=engine.validate_run(self.db);missing=[x['detail'] for x in report['errors'] if x['code']=='technical_analysis_missing']
  self.assertEqual(missing,[self.ep]);self.assertEqual(self.db.execute('SELECT count(*) FROM documents').fetchone()[0],0)

 def test_work_payload_and_member_own_status_do_not_copy_ep_text_or_owner(self):
  p=self.fixtures();epdoc=self.ep_document();self.import_mapping(p)
  output=self.directory/'work.jsonl';engine.export_work(self.db,output)
  work=[json.loads(x) for x in output.read_text(encoding='utf-8').splitlines()]
  self.assertEqual([x['application_id'] for x in work],[self.ep]);self.assertEqual(work[0]['source']['publication_number'],self.ep_pn)
  self.analyze(epdoc);payload,details=engine.build_payload(self.db,engine.validate_run(self.db))
  self.assertEqual([x['id'] for x in payload['patents']],[self.ep]);self.assertEqual(payload['stats']['application_count'],1)
  self.assertEqual(payload['stats']['by_authority'],{'EP':1});self.assertEqual(payload['stats']['by_jurisdiction_records'],{'EP':1,'DE':1})
  member=payload['registration_members'][0];self.assertEqual(member['id'],self.de)
  self.assertEqual(member['current_assignees'],['SYNTHETIC DE OWNER']);self.assertEqual(payload['patents'][0]['current_assignees'],['SYNTHETIC EP OWNER'])
  self.assertEqual(member['legal_status'],'expired');self.assertEqual(payload['patents'][0]['legal_status'],'active')
  self.assertFalse(member['own_fulltext_available']);self.assertEqual(member['documents'],[])
  self.assertEqual(details[self.ep]['documents'][0]['publication_number'],self.ep_pn)
  self.assertEqual(member['canonical_evidence_link']['source_authority'],'EP')
  self.assertEqual(payload['registration_relations'][0]['source'],self.de)

 def test_member_cannot_complete_from_native_or_canonical_text_as_extra_task(self):
  p=self.fixtures();de_doc=self.de_document();ep_doc=self.ep_document();self.import_mapping(p)
  with self.assertRaises(engine.ValidationError):self.analyze(de_doc)
  bad=self.analysis_input(ep_doc);bad['application_id']=self.de
  with self.assertRaises(engine.ValidationError):engine.import_analysis(self.db,bad)
  self.assertEqual(engine.coverage(self.db)['technical_analyzed'],0)

 def test_mapping_invalidates_role_hash_and_reimport_uses_single_unit(self):
  p=self.fixtures();doc=self.ep_document();self.analyze(doc)
  with self.db:engine.import_insights(self.db,[self.insight(role,self.ep) for role in engine.ROLES])
  old=engine.population_hash(self.db);self.import_mapping(p);self.assertNotEqual(old,engine.population_hash(self.db))
  self.assertIn('stale_role_insight',{r['code'] for r in engine.validate_run(self.db)['errors']})
  with self.db:engine.import_insights(self.db,[self.insight(role,self.ep) for role in engine.ROLES])
  self.assertEqual(engine.validate_run(self.db)['status'],'complete')
  bad=self.insight('management',self.ep);bad['patent_ids'].append(self.de);bad['metrics'][0].update(application_ids=[self.ep,self.de],value=2)
  with self.assertRaises(engine.ValidationError):engine.import_insights(self.db,[bad])

 def test_missing_changed_unofficial_or_wrong_receipt_artifacts_reject(self):
  p=self.fixtures()
  for mutate in ('wrong_hash','outside','unofficial','receipt_error','source_class'):
   bad=copy.deepcopy(p)
   if mutate=='wrong_hash':bad['official_register']['sha256']='0'*64
   elif mutate=='outside':bad['official_register']['artifact']='../unrelated.html'
   elif mutate=='unofficial':bad['official_register']['source_url']='https://example.test/not-official'
   elif mutate=='source_class':bad['official_register']['source_class']='patsnap'
   else:bad['official_register']['receipt']['sha256']='0'*64
   with self.subTest(mutate=mutate),self.assertRaises(engine.ValidationError):self.import_mapping(bad)
  self.assertEqual(engine.registration_module().records(self.db),[])

 def test_exact_pn_application_and_same_record_fields_required(self):
  p=self.fixtures()
  originals={x:x.read_bytes() for x in (self.html,self.xml,self.html.with_suffix('.receipt.json'),self.xml.with_suffix('.receipt.json'))}
  for mutate in ('unknown_app','unknown_pn','canonical_wrong_pn','field_value','field_table','eakz_xml','actual_pn_xml'):
   for path,value in originals.items():path.write_bytes(value)
   bad=copy.deepcopy(p)
   if mutate=='unknown_app':bad['canonical_filing_application_id']='EP:EP2099999999'
   elif mutate=='unknown_pn':bad['member_publication_ids']=['DE999999999T2']
   elif mutate=='canonical_wrong_pn':bad['canonical_filing_evidence']['publication_number']='EP9999002B1'
   elif mutate=='field_value':bad['official_register']['fields']['EAKZ']='22 00 0002.9'
   elif mutate=='field_table':
    self.html.write_text(self.html.read_text(encoding='utf-8').replace('stammdaten_tabelle','unrelated'),encoding='utf-8');bad['official_register'].update(self.source(self.html,p['official_register']['source_url'],'text/html'))
   elif mutate=='eakz_xml':
    self.xml.write_text(self.xml.read_text(encoding='utf-8').replace('22000001.9','22000002.9'),encoding='utf-8');bad['canonical_filing_evidence'].update(self.source(self.xml,p['canonical_filing_evidence']['source_url'],'application/xml'))
   else:
    self.xml.write_text(self.xml.read_text(encoding='utf-8').replace('9999001','9999002'),encoding='utf-8');bad['canonical_filing_evidence'].update(self.source(self.xml,p['canonical_filing_evidence']['source_url'],'application/xml'))
   with self.subTest(mutate=mutate),self.assertRaises(engine.ValidationError):self.import_mapping(bad)

 def test_graph_duplicate_chain_cycle_and_conflicting_revision_rejected(self):
  p=self.fixtures();self.import_mapping(p)
  self.import_mapping(p);self.assertEqual(len(engine.registration_module().records(self.db)),1)
  bad=copy.deepcopy(p);bad['basis']='Different revision without explicit supersession'
  with self.assertRaises(engine.ValidationError):self.import_mapping(bad)
  m=engine.registration_module();e=engine.registration_context()
  for edges in ([('a','b'),('b','c')],[('a','b'),('b','a')],[('a','b'),('a','c')]):
   with self.subTest(edges=edges),self.assertRaises(engine.ValidationError):m.check_graph([{'member_application_id':a,'canonical_filing_application_id':b} for a,b in edges],e)

 def test_tampered_source_does_not_silently_reduce_denominator(self):
  p=self.fixtures();self.import_mapping(p);self.html.write_text('changed',encoding='utf-8')
  cov=engine.coverage(self.db);self.assertEqual(cov['applications'],2);self.assertEqual(cov['registration_member_records'],0)
  self.assertIn('registration_mapping_invalid',{r['code'] for r in engine.validate_run(self.db)['errors']})

 def test_mapping_is_available_in_true_memory_backup(self):
  import sqlite3
  p=self.fixtures();self.import_mapping(p);self.db.commit();memory=sqlite3.connect(':memory:');memory.row_factory=sqlite3.Row;self.addCleanup(memory.close);self.db.backup(memory)
  self.assertEqual(engine.coverage(memory)['applications'],1)
  self.assertEqual(engine.registration_state(memory)['errors'],[])

 def test_changed_scope_preserves_record_and_reports_conflict(self):
  p=self.fixtures();self.import_mapping(p)
  with self.db:self.db.execute('INSERT INTO population_reviews VALUES(?,?)',(self.ep,engine.dump({'application_id':self.ep,'status':'excluded','candidate_snapshot_hash':engine.application_scope_snapshot(self.db,self.ep)})))
  state=engine.registration_state(self.db);self.assertEqual(state['active'],[]);self.assertTrue(state['errors'])
  self.assertEqual([a['id'] for a in engine.included_applications(self.db)],[self.de])

 def test_unresolved_classification_cannot_be_hidden_as_a_member(self):
  p=self.fixtures();row=self.db.execute('SELECT data FROM applications WHERE id=?',(self.de,)).fetchone();meta=json.loads(row[0]);meta['metadata_conflicts']=[{'field':'patent_type','old':'invention','new':'design'}]
  with self.db:self.db.execute('UPDATE applications SET data=? WHERE id=?',(engine.dump(meta),self.de))
  with self.assertRaises(engine.ValidationError):self.import_mapping(p)
  self.assertEqual(engine.coverage(self.db)['applications'],2)

 def test_date_counts_and_role_count_use_filing_units_and_keep_member_date(self):
  p=self.fixtures();meta=json.loads(self.db.execute('SELECT data FROM applications WHERE id=?',(self.de,)).fetchone()[0]);meta['filing_date']='2019-02-03'
  with self.db:self.db.execute('UPDATE applications SET data=? WHERE id=?',(engine.dump(meta),self.de))
  self.import_mapping(p);payload,details=engine.build_payload(self.db,engine.validate_run(self.db))
  self.assertEqual(payload['stats']['by_filing_year'],{'2020':1})
  self.assertEqual(payload['registration_members'][0]['filing_date'],'2019-02-03')
  self.assertEqual(payload['stats']['registration_count_bridge']['raw_included_application_records'],2)

 def test_official_xml_doctype_supported_but_custom_entities_rejected(self):
  p=self.fixtures();original=self.xml.read_text(encoding='utf-8');dtd='<!DOCTYPE ep-patent-document PUBLIC "-//EPO//EP PATENT DOCUMENT 1.7.1//EN" "ep-patent-document-v1-7-1.dtd">'
  self.xml.write_text(dtd+original,encoding='utf-8');p['canonical_filing_evidence'].update(self.source(self.xml,p['canonical_filing_evidence']['source_url'],'application/xml'))
  self.import_mapping(p)
  self.xml.write_text('<!DOCTYPE x [<!ENTITY foo "bar">]>'+original,encoding='utf-8')
  bad=copy.deepcopy(p);bad['canonical_filing_evidence'].update(self.source(self.xml,p['canonical_filing_evidence']['source_url'],'application/xml'))
  with self.assertRaises(engine.ValidationError):engine.registration_module().prepare(self.db,bad,engine.registration_context())

 def test_real_cli_route_imports_idempotently_without_source_mutation(self):
  p=self.fixtures();file=self.directory/'synthetic-mapping-input.json';file.write_text(json.dumps(p),encoding='utf-8');self.db.commit()
  result,code=engine.cli(['--db',str(self.dbpath),'registration-member-import','--input',str(file)])
  self.assertEqual(code,0);self.assertEqual(result['registration_members_imported'],1)
  result,code=engine.cli(['--db',str(self.dbpath),'registration-member-import','--input',str(file)])
  self.assertEqual(code,0);self.assertEqual(self.db.execute('SELECT count(*) FROM registration_members').fetchone()[0],1)
  self.assertEqual(self.db.execute('SELECT count(*) FROM publications').fetchone()[0],2)

 def test_public_mapping_proof_hides_cache_and_receipt_paths_but_keeps_locators(self):
  p=self.fixtures();doc=self.ep_document();self.analyze(doc);self.import_mapping(p)
  with self.db:engine.import_insights(self.db,[self.insight(role,self.ep) for role in engine.ROLES])
  stored=engine.registration_module().records(self.db)[0]
  self.assertEqual(stored['validated_proof']['official_register']['artifact'],self.html.name)
  payload,details=engine.build_payload(self.db,engine.validate_run(self.db))
  public=payload['registration_members'][0]['identity_mapping']
  source=public['validated_proof']['official_register']
  self.assertEqual(source['fields'],p['official_register']['fields'])
  self.assertEqual(source['locators']['DAKZ']['value'],p['official_register']['fields']['DAKZ'])
  self.assertEqual(source['sha256'],p['official_register']['sha256'])
  self.assertEqual(source['source_url'],p['official_register']['source_url'])
  self.assertEqual(public['validated_proof']['identity_snapshot']['canonical']['id'],self.ep)
  self.assertEqual(payload['registration_relations'][0]['source_proof'],public['validated_proof'])
  self.assertEqual(details[self.ep]['registration_members'][0]['identity_mapping'],public)
  self.assertEqual(payload['patents'][0]['jurisdictions'],['DE','EP'])
  self.assertEqual(details[self.ep]['jurisdictions'],['DE','EP'])
  # Future private acquisition additions must also remain private by default.
  future=copy.deepcopy(stored);future['validated_proof']['official_register']['private_future_path']='PRIVATE_FUTURE_PATH'
  self.assertNotIn('PRIVATE_FUTURE_PATH',engine.dump(engine.registration_module().public_record(future)))
  output=self.directory/'public-mapping';engine.render(self.db,output)
  for file in output.rglob('*'):
   if file.is_file() and file.suffix in ('.json','.js','.html','.svg'):
    content=file.read_text(encoding='utf-8')
    for private in (self.html.name,self.xml.name,self.html.with_suffix('.receipt.json').name,self.xml.with_suffix('.receipt.json').name,str(self.directory)):
     self.assertNotIn(private,content,str(file))
  self.assertEqual(stored,engine.registration_module().records(self.db)[0])

 def test_member_composed_text_never_bypasses_required_original_image_delivery(self):
  p=self.fixtures();epdoc=self.ep_document();dedoc=self.de_document();self.analyze(epdoc);self.import_mapping(p)
  # Model a retained member source with required image proof, but no delivered
  # original pixels. Even a locally qualified source is not complete UI text.
  row=self.db.execute('SELECT data FROM documents WHERE id=?',(dedoc['document_id'],)).fetchone();data=json.loads(row[0])
  data['embedded_image_review']={'schema_version':2,'images':[{'file':'PRIVATE_MISSING_MEMBER_IMAGE.png'}]}
  data['normalization_notice']='Synthetic retained image transcription source.'
  with self.db:
   self.db.execute('UPDATE documents SET data=? WHERE id=?',(engine.dump(data),dedoc['document_id']))
   engine.import_insights(self.db,[self.insight(role,self.ep) for role in engine.ROLES])
  payload,details=engine.build_payload(self.db,engine.validate_run(self.db))
  member=payload['registration_members'][0];display=member['documents'][0]
  self.assertFalse(member['own_fulltext_available']);self.assertFalse(display['complete'])
  self.assertTrue(display['source_qualified']);self.assertTrue(display['text_withheld']);self.assertFalse(display['required_embedded_images_delivered'])
  self.assertEqual(display['text'],'');self.assertIn('原图未随本页面交付',display['display_notice'])
  self.assertEqual(details[self.ep]['registration_members'][0]['documents'],member['documents'])
  output=self.directory/'withheld-member-image';engine.render(self.db,output)
  self.assertFalse((output/'document-images').exists())
  self.assertEqual(engine.coverage(self.db)['technical_analyzed'],1)
  for file in output.rglob('*'):
   if file.is_file() and file.suffix in ('.json','.js','.html','.svg'):
    self.assertNotIn('PRIVATE_MISSING_MEMBER_IMAGE.png',file.read_text(encoding='utf-8'))

 def test_plain_member_own_text_is_retained_without_changing_canonical_analysis(self):
  p=self.fixtures();epdoc=self.ep_document();dedoc=self.de_document();self.analyze(epdoc);self.import_mapping(p)
  payload,details=engine.build_payload(self.db,engine.validate_run(self.db));member=payload['registration_members'][0]
  self.assertTrue(member['own_fulltext_available']);self.assertTrue(member['documents'][0]['complete'])
  self.assertEqual(member['documents'][0]['publication_number'],self.de_pn)
  self.assertEqual(details[self.ep]['analysis']['document_id'],epdoc['document_id'])
  self.assertEqual(engine.coverage(self.db)['technical_analyzed'],1)

if __name__=='__main__':unittest.main()
