"""Evidence-bound national register membership, never family deduplication.

The data model is jurisdiction-neutral; each official format needs an explicit
adapter. V1 implements DPMA DAKZ/EAKZ/EPN plus the exact EPO publication XML.
No network, ownership transfer, text copying or source-row mutation occurs.
"""
from __future__ import annotations
import hashlib,json,re
from pathlib import Path
from html.parser import HTMLParser
from urllib.parse import urlsplit,parse_qs
import xml.etree.ElementTree as ET

RELATION='national_register_member_of_european_application'
ADAPTER='dpma_eakz_epn_v1'

def _json(c,key,default=None):
 row=c.execute('SELECT value FROM meta WHERE key=?',(key,)).fetchone()
 return json.loads(row[0]) if row else default

def root(c,e):
 file=c.execute('PRAGMA database_list').fetchone()[2]
 value=Path(file).resolve().parent if file else Path(_json(c,'registration_evidence_root',''))
 e.require(value.is_absolute() and value.is_dir(),'Registration proof needs a known run evidence root')
 return value.resolve()

def records(c):
 if not c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='registration_members'").fetchone():return []
 return [json.loads(r[0]) for r in c.execute('SELECT data FROM registration_members ORDER BY id')]

def artifact(c,s,host,kind,e):
 e.require(isinstance(s,dict) and s.get('source_class')=='official','Official registration source required')
 try:url=urlsplit(s.get('source_url',''));port=url.port
 except ValueError as exc:raise e.ValidationError('Invalid official registration source URL') from exc
 e.require(url.scheme=='https' and url.hostname==host and not url.username and not url.password and port in (None,443),'Unexpected official registration source URL')
 runroot=root(c,e)
 def local(value):
  e.require(isinstance(value,str) and value and not Path(value).is_absolute(),'Evidence artifact must be run-relative')
  p=(runroot/value).resolve();e.require(p.is_relative_to(runroot) and p.is_file(),'Evidence artifact missing or outside run root');return p
 path=local(s.get('artifact'));raw=path.read_bytes();sha=hashlib.sha256(raw).hexdigest()
 e.require(s.get('sha256')==sha,'Official artifact hash mismatch')
 receipt=s.get('receipt');e.require(isinstance(receipt,dict),'Official acquisition receipt required')
 rp=local(receipt.get('artifact'));rb=rp.read_bytes();e.require(hashlib.sha256(rb).hexdigest()==receipt.get('sha256'),'Official receipt hash mismatch')
 value=json.loads(rb.decode('utf-8-sig'));pointer=receipt.get('record_path',[]);e.require(isinstance(pointer,list),'Receipt record_path must be explicit')
 try:
  for key in pointer:
   e.require(type(key) in (str,int),'Invalid receipt path component');value=value[key]
 except (KeyError,IndexError,TypeError):e.require(False,'Official receipt entry missing')
 e.require(isinstance(value,dict) and not value.get('error') and not value.get('isError'),'Official receipt records an error')
 e.require(value.get('status',200)==200 and value.get('sha256')==sha and value.get('bytes')==len(raw),'Official acquisition receipt does not bind artifact bytes')
 e.require(value.get('final_url')==s['source_url'] and value.get('acquired_at')==s.get('acquired_at') and bool(s.get('acquired_at')),'Official receipt URL or acquisition date differs')
 e.require(Path(value.get('local_file','').replace('\\','/')).name==path.name,'Official receipt local file differs')
 e.require(str(value.get('content_type','')).split(';')[0] in kind,'Official source media type differs')
 return raw,{'source_class':'official','source_url':s['source_url'],'artifact':str(path.relative_to(runroot)),
  'sha256':sha,'bytes':len(raw),'acquired_at':s['acquired_at'],'receipt':{'artifact':str(rp.relative_to(runroot)),'sha256':receipt['sha256'],'record_path':pointer}}

class RegisterParser(HTMLParser):
 def __init__(self):
  super().__init__(convert_charrefs=True);self.depth=0;self.tables=0;self.row=None;self.cell=None;self.rows=[]
 def handle_starttag(self,tag,attrs):
  a=dict(attrs)
  if tag=='table':
   if self.depth:self.depth+=1
   elif a.get('id')=='stammdaten_tabelle':self.depth=1;self.tables+=1
  if not self.depth:return
  if tag=='tr':self.row={}
  if tag=='td' and self.row is not None:self.cell=a.get('data-th');self.row[self.cell]=[]
  if tag=='br' and self.cell is not None:self.row[self.cell].append('\n')
 def handle_data(self,data):
  if self.depth and self.row is not None and self.cell is not None:self.row[self.cell].append(data)
 def handle_endtag(self,tag):
  if tag=='td':self.cell=None
  if tag=='tr' and self.depth and self.row is not None:self.rows.append({k:''.join(v).strip() for k,v in self.row.items()});self.row=None
  if tag=='table' and self.depth:self.depth-=1

def _identity(c,appid,e):
 r=c.execute('SELECT data FROM applications WHERE id=?',(appid,)).fetchone();e.require(r,'Unknown registration application: '+str(appid));return json.loads(r[0])

def _publication(c,pn,appid,e):
 r=c.execute('SELECT application_id FROM publications WHERE id=?',(pn,)).fetchone();e.require(r and r[0]==appid,'Publication is not owned by the stated source application: '+str(pn))

def prepare(c,p,e):
 e.require(isinstance(p,dict) and p.get('adapter')==ADAPTER,'Unsupported official national-register adapter; no family inference allowed')
 e.require(p.get('relation_type')==RELATION,'Explicit official national registration relation required')
 member=p.get('member_application_id');target=p.get('canonical_filing_application_id')
 e.require(member and target and member!=target,'Distinct member and canonical filing IDs required')
 ma=_identity(c,member,e);ta=_identity(c,target,e)
 e.require(ma.get('authority')=='DE' and ta.get('authority')=='EP','DPMA adapter requires DE member and EP filing')
 e.require(ma.get('patent_type')=='invention' and ta.get('patent_type')=='invention','National registration mapping requires two resolved invention classifications')
 for app in (ma,ta):
  conflicts=app.get('metadata_conflicts',[])+e.bibliography_conflicts(c,app['id'])
  e.require(not any(x.get('field')=='patent_type' for x in conflicts),'Unresolved member/canonical patent-type conflict cannot be hidden by registration mapping')
 e.require(isinstance(p.get('member_publication_ids'),list) and p['member_publication_ids'],'Member provider publication identities required')
 for pn in p['member_publication_ids']:_publication(c,pn,member,e)
 e.require(len(set(p['member_publication_ids']))==len(p['member_publication_ids']),'Repeated member publication reference')
 rs=p.get('official_register');raw,rproof=artifact(c,rs,'register.dpma.de',{'text/html'},e)
 u=urlsplit(rs['source_url']);e.require(u.path=='/DPMAregister/pat/register','Not a case-level official DPMA register page')
 parser=RegisterParser();parser.feed(raw.decode('utf-8-sig'));parser.close()
 e.require(parser.tables==1 and parser.depth==0,'Need exactly one complete official register master-data table')
 values={};locators={}
 for field in ('DAKZ','EAKZ','EPN'):
  found=[(i,row) for i,row in enumerate(parser.rows) if row.get('Feld')==field]
  e.require(len(found)==1,'Same-record official '+field+' is missing or ambiguous')
  index,row=found[0];value=row.get('Inhalt','');e.require(value,'Official identity field is empty')
  values[field]=value;locators[field]={'table_id':'stammdaten_tabelle','row_index':index,'field_cell':'Feld','value_cell':'Inhalt','field':field,'value':value}
 e.require(rs.get('fields')==values,'Declared register fields differ from actual official record')
 dakz=re.sub(r'\s','',values['DAKZ']);eakz=re.sub(r'\s','',values['EAKZ'])
 e.require(re.fullmatch(r'\d{12}\.\d',dakz) and re.fullmatch(r'\d{8}\.\d',eakz) and re.fullmatch(r'\d+',values['EPN']),'Unsupported official file-number syntax')
 e.require(ma['application_number']=='DE'+dakz.split('.')[0],'Official DAKZ differs from member source identity')
 e.require(parse_qs(u.query).get('AKZ')==['E'+eakz.replace('.','')],'DPMA URL and actual EAKZ record differ')
 es=p.get('canonical_filing_evidence');xml,xproof=artifact(c,es,'data.epo.org',{'application/xml','text/xml'},e)
 e.require(b'<!ENTITY' not in xml.upper(),'Custom XML entities are not allowed')
 declarations=re.findall(br'<!DOCTYPE[^>]*>',xml,re.I)
 e.require(len(declarations)<=1 and all(re.fullmatch(br'<!DOCTYPE ep-patent-document PUBLIC "-//EPO//EP PATENT DOCUMENT [0-9.]+//EN" "ep-patent-document-v[0-9-]+\.dtd">',d) for d in declarations),'Unsupported XML document declaration')
 try:x=ET.fromstring(xml)
 except ET.ParseError as exc:raise e.ValidationError('Incomplete official EPO XML: '+str(exc)) from exc
 e.require(x.tag=='ep-patent-document','Not an official EPO publication XML root')
 references=x.findall('./SDOBI/B200/B210');e.require(len(references)==1,'Official EPO application reference is missing or ambiguous')
 pn=x.get('country','')+x.get('doc-number','')+x.get('kind','');apno=references[0].text
 e.require(pn==es.get('publication_number') and apno==eakz,'Official EPO PN/application and same-record EAKZ differ')
 e.require(x.get('country')=='EP' and x.get('doc-number')==values['EPN'],'Official EPN and exact EPO document number differ')
 e.require(ta['application_number']=='EP20'+eakz.split('.')[0],'Official EAKZ differs from canonical filing identity')
 _publication(c,pn,target,e)
 e.require(re.fullmatch(r'/publication-server/rest/v\d+\.\d+/(?:publication-dates/\d{8}/)?patents/EP'+re.escape(values['EPN'])+r'NW'+re.escape(x.get('kind',''))+r'/document\.xml',urlsplit(es['source_url']).path),'Official EPO URL does not identify the same PN')
 e.require(p.get('reviewer') and p.get('basis'),'Identity reviewer and explicit filing-unit basis required')
 snapshot={'member':{'id':member,'authority':ma['authority'],'application_number':ma['application_number'],'publication_ids':sorted(p['member_publication_ids'])},'canonical':{'id':target,'authority':ta['authority'],'application_number':ta['application_number'],'publication_number':pn}}
 proof={'adapter':ADAPTER,'official_register':{**rproof,'fields':values,'locators':locators},
  'canonical_filing_evidence':{**xproof,'publication_number':pn,'application_number':apno,'locators':{'publication':'/ep-patent-document/@country,@doc-number,@kind','application':'/ep-patent-document/SDOBI/B200/B210'}},'identity_snapshot':snapshot}
 return {**p,'id':'registration-'+e.digest([member,target])[:24],'national_jurisdiction':'DE','record_class':'ep_national_register_member',
  'count_as_additional_independent_filing':False,'validated_proof':proof,'proof_hash':e.digest(proof),
  'provider_publication_identity_notice':'Provider identity retained; this mapping does not establish an independently published national document.',
  'technical_source_notice':'Canonical EP evidence remains EP evidence; no member document or analysis is created or marked complete.',
  'legal_scope_notice':'Member owner, legal and auxiliary observations are independent; acquisition date is not a cutoff-date legal snapshot.'}

def public_record(mapping):
 """Explicit public allowlist; private acquisition paths stay in the cache."""
 proof=mapping['validated_proof']
 public_proof={'adapter':proof['adapter'],'identity_snapshot':proof['identity_snapshot']}
 for name in ('official_register','canonical_filing_evidence'):
  source=proof[name]
  public_proof[name]={key:source[key] for key in ('source_class','source_url','sha256','bytes','acquired_at','fields','locators','publication_number','application_number') if key in source}
 result={key:mapping[key] for key in ('id','adapter','relation_type','member_application_id','canonical_filing_application_id','member_publication_ids','national_jurisdiction','record_class','count_as_additional_independent_filing','reviewer','basis','proof_hash','provider_publication_identity_notice','technical_source_notice','legal_scope_notice') if key in mapping}
 result['validated_proof']=public_proof
 return result

def check_graph(items,e):
 by_member={}
 for item in items:
  member=item['member_application_id'];target=item['canonical_filing_application_id']
  e.require(member not in by_member,'Conflicting or repeated registration member mapping')
  by_member[member]=target
 e.require(not (set(by_member)&set(by_member.values())),'Registration mapping chains or cycles are not allowed')

def import_records(c,payload,e):
 file=c.execute('PRAGMA database_list').fetchone()[2];e.require(file,'Import registration proof into a file-backed run; use a temporary file for tests')
 staged=[prepare(c,p,e) for p in e.as_list(payload)];old=records(c);old_by_id={x['id']:x for x in old}
 scope={a['id'] for a in e.included_source_records(c)}
 for p in staged:e.require({p['member_application_id'],p['canonical_filing_application_id']}<=scope,'Registration endpoints must both be reviewed included records in this analysis scope')
 for p in staged:
  previous=old_by_id.get(p['id']);e.require(previous is None or e.dump(previous)==e.dump(p),'Conflicting registration mapping revision; retained mappings are immutable')
 prospective=old+[p for p in staged if p['id'] not in old_by_id];check_graph(prospective,e)
 for p in staged:
  c.execute('INSERT OR IGNORE INTO registration_members VALUES(?,?,?,?)',(p['id'],p['member_application_id'],p['canonical_filing_application_id'],e.dump(p)))
 c.execute('INSERT OR REPLACE INTO meta VALUES(?,?)',('registration_evidence_root',e.dump(str(Path(file).resolve().parent))))
 e.event(c,'registration-member-import',{'count':len(staged),'members':[p['member_application_id'] for p in staged]})
 return {'registration_members_imported':len(staged),'mapping_ids':[p['id'] for p in staged],'source_rows_modified':False,'technical_text_or_analysis_created':False}

def state(c,scope_records,e):
 selected={a['id'] for a in scope_records};active=[];errors=[];all_records=records(c)
 try:check_graph(all_records,e)
 except e.ValidationError as exc:return {'active':[],'errors':[{'code':'registration_mapping_graph_invalid','detail':str(exc)}]}
 for item in all_records:
  if item['member_application_id'] not in selected:continue
  try:
   e.require(item['canonical_filing_application_id'] in selected,'Member and canonical filing scope disagree; do not silently remove the member')
   checked=prepare(c,item,e);e.require(checked['validated_proof']==item.get('validated_proof') and checked['proof_hash']==item.get('proof_hash'),'Stored registration proof or source identity changed')
   active.append(item)
  except (e.ValidationError,OSError,ValueError,KeyError,TypeError) as exc:errors.append({'code':'registration_mapping_invalid','detail':item.get('id','unknown')+': '+str(exc)})
 return {'active':active,'errors':errors}
