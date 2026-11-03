"""Validate authored company-centred industry research; no retrieval or model calls.

Identity/reference checks do not certify the truth of the authored analysis.
"""
import copy, datetime, importlib.util, re
from pathlib import Path, PurePosixPath
from urllib.parse import urlsplit, unquote

class IndustryResearchError(ValueError): pass
KINDS = {'F','D','P','R','O','L'}
TASKS = {'project','competition','profile','selection','forecast'}
MODULES = ('transfer','forecast','maturity','selection')

def require(ok, message):
    if not ok: raise IndustryResearchError(message)

def text(value, label):
    require(isinstance(value,str) and bool(value.strip()), label+' requires text')
    return value

def date(value, label):
    text(value,label)
    try: require(datetime.date.fromisoformat(value).isoformat()==value,label+' must be YYYY-MM-DD')
    except ValueError as exc: raise IndustryResearchError(label+' must be YYYY-MM-DD') from exc

def array(value,label,nonempty=False):
    require(isinstance(value,list) and (not nonempty or bool(value)),label+' requires an array')
    require(all(isinstance(x,dict) for x in value),label+' requires object records')
    return value

def index(records,label):
    result={}
    for record in records:
        ident=text(record.get('id'),label+' id')
        require(re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.:-]*',ident),label+' id must be a stable ASCII identifier')
        require(ident not in result,'Duplicate '+label+' id: '+ident)
        result[ident]=record
    return result

def safe_link(source):
    url,local=source.get('url'),source.get('local_path')
    require(bool(url) or bool(local),'Source needs a URL or packaged relative local_path')
    if url:
        text(url,'Source URL')
        try:
            p=urlsplit(url)
            valid=p.scheme in ('http','https') and bool(p.hostname) and not p.username and not p.password
        except ValueError: valid=False
        require(valid and not any(c.isspace() or ord(c)<32 for c in url),'Unsafe source URL')
    if local:
        text(local,'Source local_path'); decoded=unquote(local)
        require(not any(c in decoded for c in ('\\',':','?','#')) and not any(ord(c)<32 for c in decoded)
                and not PurePosixPath(decoded).is_absolute() and '..' not in PurePosixPath(decoded).parts,
                'Source local_path must remain inside the delivery directory')

def prepare(payload,details,context=None):
    raw=(context or {}).get('industry_research')
    if raw is None: return None
    require(isinstance(raw,dict),'industry_research must be an object')
    out=copy.deepcopy(raw)
    require(out.get('schema_version',1)==1,'Unsupported industry schema_version'); out['schema_version']=1
    scope=out.get('scope'); require(isinstance(scope,dict),'Industry scope is required')
    for key in ('topic','selection_basis'): text(scope.get(key),'scope.'+key)
    date(scope.get('as_of'),'scope.as_of')
    require(scope['as_of']==payload.get('run',{}).get('as_of_date'),'Industry cutoff must match run cutoff')
    companies=index(array(out.get('companies'),'companies',True),'company')
    target_id=out.get('target_company_id'); require(target_id in companies,'Target company must exist in companies')
    for c in companies.values(): text(c.get('name'),'Company name'); text(c.get('role'),'Company role')
    require(companies[target_id]['name']==payload.get('run',{}).get('company'),'Target company name must match selected run company')
    sources=index(array(out.get('sources'),'sources'),'source')
    patents={x['id']:x for x in payload.get('patents',[])}
    corpora={'main':{'payload':payload,'details':details,'patents':patents}}
    metadata=[]
    for corpus in array((context or {}).get('industry_reference_corpora',[]),'industry_reference_corpora'):
        cid=text(corpus.get('id'),'Reference corpus id')
        require(re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.:-]*',cid) and cid not in corpora,'Reference corpus id must be unique and not main')
        cp,cd=corpus.get('payload'),corpus.get('details')
        require(isinstance(cp,dict) and isinstance(cd,dict),'Reference corpus requires exported payload and details')
        run=cp.get('run'); require(isinstance(run,dict),'Reference corpus run missing')
        text(run.get('company'),'Reference corpus company'); date(run.get('as_of_date'),'Reference corpus cutoff')
        require(isinstance(run.get('scope'),(dict,str)) and bool(run.get('scope')),'Reference corpus scope required')
        text(run.get('status'),'Reference corpus run status')
        rows=array(cp.get('patents'),'Reference corpus patents',True)
        pi={text(row.get('id'),'Reference application id'):row for row in rows}
        require(len(pi)==len(rows) and set(pi)<=set(cd),'Reference application identities must be unique and have details')
        corpora[cid]={'payload':cp,'details':cd,'patents':pi}
        metadata.append({'id':cid,'company':run['company'],'as_of_date':run['as_of_date'],'scope':copy.deepcopy(run['scope']),
                         'declared_run_status':run['status'],'review_note':'仅核查导出记录的身份、完整文本和引用；未复验原运行的独立审阅门禁。'})
    # Corpus labels cannot hide conflicting originals for the same document identity.
    document_texts={}
    for cid,corpus in corpora.items():
        for aid in corpus['patents']:
            detail=corpus['details'].get(aid)
            require(isinstance(detail,dict),'Reference detail must be an object')
            for doc in array(detail.get('documents',[]),'Corpus documents'):
                if not doc.get('id'): continue
                identity=(aid,doc.get('publication_number'),doc.get('version'),doc.get('document_type'))
                keys=[('document_id',aid,doc['id']),('publication',)+identity]
                for key in keys:
                    current=(doc.get('text'),doc.get('complete'),bool(doc.get('rejection_review_ids')))
                    require(key not in document_texts or document_texts[key]==current,'Conflicting original document across industry corpora')
                    document_texts[key]=current
    out['reference_corpora']=metadata
    def refs(ids,label,required=True,kind=None,substantive=False,temporal_use=None):
        require(isinstance(ids,list) and all(isinstance(x,str) for x in ids),label+' needs source_ids')
        require(not required or bool(ids),label+' needs supporting sources')
        require(len(ids)==len(set(ids)),label+' has duplicate sources')
        require(all(x in sources for x in ids),label+' references unknown source')
        require(not any(sources[x].get('publication_after_cutoff') for x in ids) or temporal_use=='retrospective',label+' must explicitly mark retrospective use of later publication')
        if kind: require(all(sources[x]['kind']==kind for x in ids),label+' source category mismatch')
        if substantive and ids: require(any(sources[x]['kind']!='L' for x in ids),label+' cannot rely only on catalog leads')
    spec=importlib.util.spec_from_file_location('industry_claim_checks',Path(__file__).with_name('claim_comparison.py'))
    cc=importlib.util.module_from_spec(spec); spec.loader.exec_module(cc)
    for source in sources.values():
        require(source.get('kind') in KINDS,'Source kind must be F/D/P/R/O/L')
        for key in ('title','locator'): text(source.get(key),'Source '+key)
        safe_link(source)
        date(source.get('observed_at'),'Source observed_at')
        source['observed_after_cutoff']=source['observed_at']>scope['as_of']
        published=source.get('publication_date')
        if published is not None: date(published,'Source publication_date')
        source['publication_after_cutoff']=bool(published and published>scope['as_of'])
        if source['publication_after_cutoff']:
            require(source.get('temporal_use')=='retrospective','Later publication requires explicit retrospective source use')
        if source['kind'] not in ('F','D'): continue
        full_kind=source['kind']; expected_type='claims' if full_kind=='F' else 'description'
        appid,docid=source.get('application_id'),source.get('document_id')
        corpus_id=source.get('corpus_id','main')
        require(corpus_id in corpora,'F/D source references unknown corpus')
        corpus=corpora[corpus_id]; selected=corpus['patents']; selected_details=corpus['details']
        require(appid in selected and appid in selected_details,'F/D source must bind an application in its selected corpus')
        run=corpus['payload']['run']
        source.update(corpus_id=corpus_id,corpus_company=run['company'],corpus_as_of=run['as_of_date'])
        if corpus_id!='main':
            source['corpus_scope']=copy.deepcopy(run['scope'])
            source['corpus_review_note']='仅核查导出记录的身份、完整文本和引用；未复验原运行的独立审阅门禁。'
        detail=selected_details[appid]; doc=next((x for x in detail.get('documents',[]) if x.get('id')==docid),None)
        require(doc and doc.get('complete') is True and doc.get('document_type')==expected_type and not doc.get('rejection_review_ids'),
                'F/D source requires accepted complete same-document primary text')
        require(selected[appid].get('analysis_status')=='complete' and (detail.get('analysis') or {}).get('document_id')==docid,
                'F/D source requires completed reading of this primary document')
        pn,version=text(doc.get('publication_number'),'F publication'),text(doc.get('version'),'F version')
        require(version!='unknown','F source version cannot be unknown')
        require(source.get('publication_number',pn)==pn and source.get('version',version)==version,'F source publication/version mismatch')
        text(doc.get('text'),'F/D text'); blocks={}
        if full_kind=='F':
            try: blocks={x['number']:x for x in cc.claim_blocks(doc['text'])}
            except ValueError as exc: raise IndustryResearchError(str(exc)) from exc
        eids=source.get('evidence_ids')
        require(isinstance(eids,list) and bool(eids) and all(isinstance(x,str) for x in eids),'F source requires evidence_ids')
        evidence={x['id']:x for x in detail.get('evidence',[])}; resolved=[]
        for eid in eids:
            e=evidence.get(eid)
            require(e and e.get('application_id',appid)==appid and e.get('document_id')==docid and e.get('publication_number')==pn and e.get('version')==version,
                    'F evidence must belong to same application, publication and version')
            start,end=e.get('start'),e.get('end')
            require(type(start) is int and type(end) is int and 0<=start<end<=len(doc['text']) and doc['text'][start:end]==e.get('quote'),'F evidence quote/span mismatch')
            if full_kind=='F':
                try: number=cc.claim_number(e)
                except ValueError as exc: raise IndustryResearchError(str(exc)) from exc
                require(number in blocks and blocks[number]['start']<=start<end<=blocks[number]['end'],'F evidence must lie in declared claim')
            else: require(bool(e.get('locator')),'D evidence needs an original paragraph or page locator')
            resolved.append(copy.deepcopy(e))
        source.update(publication_number=pn,version=version,evidence=resolved)
    tasks=array(out.get('tasks'),'tasks',True); index(tasks,'task')
    for task in tasks:
        require(task.get('kind') in TASKS,'Unknown task kind')
        for key in ('question','answer','conditions'): text(task.get(key),'Task '+key)
        require(task.get('status') in ('supported','unknown'),'Task status must be supported or unknown')
        if task['status']=='unknown': text(task.get('reason'),'Unknown task reason')
        refs(task.get('source_ids'),'Task',task['status']=='supported',substantive=task['status']=='supported',temporal_use=task.get('temporal_use'))
    routes=index(array(out.get('routes'),'routes'),'route')
    for route in routes.values():
        for key in ('name','problem','mechanism','selection_reason'): text(route.get(key),'Route '+key)
        require(type(route.get('major')) is bool,'Route major must be explicit boolean')
        refs(route.get('source_ids'),'Route',substantive=route['major'],temporal_use=route.get('temporal_use'))
        for key in MODULES:
            module=route.get(key)
            if not route['major'] and module is None: continue
            require(isinstance(module,dict),'Major route requires '+key)
            require(module.get('status') in ('supported','unknown'),'Module status must be supported or unknown')
            for field in ('summary','conditions','unknowns'): text(module.get(field),key+'.'+field)
            supported=module['status']=='supported'; refs(module.get('source_ids'),key,supported,substantive=supported,temporal_use=module.get('temporal_use'))
            if not supported: continue
            if key=='transfer':
                records=array(module.get('candidates'),'transfer.candidates',True)
                fields=('domain','shared_function','mechanism','differences','adaptation','test')
            elif key=='forecast':
                records=array(module.get('hypotheses'),'forecast.hypotheses',True)
                fields=('horizon','change','driver','blocker','trigger','falsifier')
            elif key=='maturity':
                text(module.get('rubric'),'Maturity rubric')
                records=array(module.get('dimensions'),'maturity.dimensions',True); fields=('name','stage','basis')
            else:
                for field in ('scenario','recommendation','reversal'): text(module.get(field),'selection.'+field)
                records=array(module.get('criteria'),'selection.criteria',True); fields=('name','priority','measure')
            for record in records:
                for field in fields: text(record.get(field),key+' item.'+field)
                if key in ('maturity','selection'):
                    status=record.get('status','supported')
                    require(status in ('supported','unknown'),key+' item status must be supported or unknown')
                    record['status']=status
                    if status=='unknown': text(record.get('reason'),key+' unknown item reason')
                    refs(record.get('source_ids'),key+' item',status=='supported',substantive=status=='supported',temporal_use=record.get('temporal_use'))
                else: refs(record.get('source_ids'),key+' item',substantive=True,temporal_use=record.get('temporal_use'))
    matrix=array(out.get('matrix',[]),'matrix'); cells={}
    for cell in matrix:
        pair=(cell.get('company_id'),cell.get('route_id'))
        require(pair[0] in companies and pair[1] in routes,'Matrix company/route is unknown')
        require(pair not in cells,'Duplicate matrix cell')
        require('score' not in cell and 'rank' not in cell,'Matrix evidence categories are not strength scores')
        for claim in array(cell.get('claims'),'Matrix claims',True):
            kind=claim.get('kind'); require(kind in KINDS|{'U'},'Unknown matrix category'); text(claim.get('text'),'Matrix claim text')
            require('score' not in claim and 'rank' not in claim,'Matrix source kinds are not rankings')
            if kind=='U':
                require(claim.get('state','unknown')=='unknown' and claim.get('source_ids')==[],'U must remain unknown, never absent or zero')
                require('value' not in claim and 'count' not in claim,'Unknown cannot be encoded as zero'); claim['state']='unknown'
            else:
                require(claim.get('state','observed')=='observed','Supported matrix claim state must be observed')
                refs(claim.get('source_ids'),'Matrix claim',kind=kind,temporal_use=claim.get('temporal_use')); claim['state']='observed'
        cells[pair]=cell
    out['matrix']=[cells.get((c,r),{'company_id':c,'route_id':r,'claims':[{'kind':'U','state':'unknown','text':'本次尚未取得可用于判断的材料。','source_ids':[]}]}) for c in companies for r in routes]
    cases=array(out.get('jurisdiction_cases',[]),'jurisdiction_cases'); index(cases,'jurisdiction case')
    for case in cases:
        text(case.get('label'),'Jurisdiction case label'); require(case.get('company_id') in companies,'Jurisdiction company is unknown')
        text(case.get('application_id'),'Jurisdiction application identity'); date(case.get('observed_at'),'Jurisdiction observation date')
        refs(case.get('source_ids'),'Jurisdiction case',temporal_use=case.get('temporal_use')); seen=set()
        for authority in array(case.get('authorities'),'Jurisdiction authorities',True):
            code=authority.get('code')
            require(isinstance(code,str) and re.fullmatch('[A-Z]{2}',code) and code not in seen,'Jurisdiction codes must be unique two-letter codes'); seen.add(code)
            require(authority.get('status') in ('simple','extended','unknown'),'Unknown jurisdiction coverage state')
            text(authority.get('note'),'Jurisdiction note'); refs(authority.get('source_ids'),'Jurisdiction member',authority['status']!='unknown',temporal_use=authority.get('temporal_use'))
            members=authority.get('member_publication_numbers',[])
            require(isinstance(members,list) and all(isinstance(x,str) and x.strip() for x in members),'Jurisdiction members must be publication identifiers')
            require(authority['status']=='unknown' or bool(members),'Observed jurisdiction requires member publication numbers')
            require(authority['status']!='unknown' or not members,'Unknown jurisdiction cannot contain confirmed members')
            require('legal_status' not in authority and 'company_coverage' not in authority,'Selected family records do not establish legal status or company-wide coverage')
        case['scope_note']='仅所选案例的同族记录；不代表企业整体布局，也不证明权利有效。'
    out['jurisdiction_cases']=cases
    out['matrix_note']='颜色与字母表示证据来源类别，不是技术强弱；未知不等于没有。'
    out['scope_note']='本模块按上述研究范围呈现；不与主报告筛选自动联动。'
    return out
