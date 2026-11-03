"""Assemble a company-independent reader from validated application evidence.

No network or model calls. Optional narratives and classifications are authored
by the host and must cite evidence already belonging to the application.
"""
import collections,datetime,json,copy,re,importlib.util
from pathlib import Path

class ReportDataError(ValueError):pass
def require(ok,message):
    if not ok:raise ReportDataError(message)
def write_js(out,name,global_name,data):
    literal=json.dumps(data,ensure_ascii=False,separators=(',',':')).replace('<','\\u003c').replace('\u2028','\\u2028').replace('\u2029','\\u2029')
    (Path(out)/'data'/name).write_text('window.'+global_name+'='+literal+';\n',encoding='utf8')
def known_date(value):
    try:return datetime.date.fromisoformat(value).isoformat()
    except (TypeError,ValueError):return ''
def normalized_row(p):
    p=copy.deepcopy(p)
    for field in ['filing_date','publication_date']:p[field]=known_date(p.get(field))
    p['authority']=p.get('authority') or 'unknown';p['legal_status']=p.get('legal_status') or 'unknown';p['patent_type']=p.get('patent_type') or 'unknown'
    p['publication_numbers']=p.get('publication_numbers') or [];p['verified_entity_names']=p.get('verified_entity_names') or []
    p['secondary_basis']=p.get('secondary_basis') or {};return p
def assemble(payload,details,context=None):
    ctx=context or {};run=payload['run'];pats=[normalized_row(p) for p in payload['patents']];index={p['id']:p for p in pats}
    require(len(index)==len(pats),'Duplicate independent applications in reader input')
    sources={};routes={};timeline={};families=[]
    def refs(appid,ids):
        require(ids and isinstance(ids,list),'A narrative/classification requires evidence_ids')
        for eid in ids:
            require(eid in sources.get(appid,{}),'Evidence must belong to this application: '+str(eid))
    for p in pats:
        id=p['id'];d=details[id];docs={v['id']:v for v in d.get('documents',[])};sources[id]={}
        for e in d.get('evidence',[]):
            doc=docs.get(e.get('document_id'));require(doc is not None,'Evidence document missing')
            require(e.get('application_id',id)==id,'Cross-application evidence')
            require(isinstance(e.get('start'),int) and isinstance(e.get('end'),int) and doc['text'][e['start']:e['end']]==e['quote'],'Evidence quote/span mismatch')
            sources[id][e['id']]=e
        a=d.get('analysis') or {};main=docs.get(a.get('document_id'))
        if p.get('analysis_status')=='complete':
            require(main and main.get('complete'),'Completed analysis requires qualified source document')
            r={}
            for field in ['application_field','technical_problem','technical_means','conditions','components','steps']:
                values=a.get(field,[]);values=values if isinstance(values,list) else [values];r[field]=[]
                for v in values:
                    if not isinstance(v,dict) or v.get('kind')=='unknown':continue
                    refs(id,v.get('evidence_ids'));r[field].append({'text':v['text'],'evidence_ids':v['evidence_ids']})
            require(r['technical_means'],'A completed technical analysis requires technical means')
            routes[id]=r;publication=next((v for v in d.get('publications',[]) if v.get('publication_number')==main['publication_number'] or v.get('id')==main['publication_number']),{})
            ev_ids=list(dict.fromkeys(eid for values in r.values() for v in values for eid in v['evidence_ids']))
            timeline[id]={'id':id,'document_id':main['id'],'document_type':main['document_type'],'publication_number':main['publication_number'],'document_publication_date':known_date(publication.get('publication_date')),'version':main.get('version','unknown'),'means':[v['text'] for v in r['technical_means']],'conditions':[v['text'] for v in r['conditions']],'evidence_ids':ev_ids,'source_quotes':[sources[id][eid] for eid in ev_ids]}
        for src in d.get('auxiliary_sources',[]):
            if src.get('kind')!='family':continue
            simple=(src.get('normalized') or {}).get('simple') or {}
            fid=simple.get('family_id') or simple.get('id')
            if fid:families.append({'application_id':id,'family_id':fid,'source_id':src['id'],'members':simple.get('members',[])})
    assignments={};classifications=ctx.get('classifications',{})
    require(set(classifications)<=set(index),'Classification references unknown application')
    for p in pats:
        id=p['id'];v=classifications.get(id)
        if v:
            if v.get('unknown'):require(v.get('reason'),'Unknown classification needs a reason')
            else:refs(id,v.get('evidence_ids'))
            assignments[id]={'group':v.get('product_group') or '产品待明确','line':v.get('product_line') or '应用产品待明确','method':v.get('reason','依据原文归纳应用场景'),'field':'同件原文','text':'\n'.join(sources[id][eid]['quote'] for eid in v.get('evidence_ids',[])),'matches':[],'evidence_ids':v.get('evidence_ids',[])}
            p['secondary_technology']=v.get('direction') or '实现方向待归类'
        else:
            assignments[id]={'group':'产品待明确','line':'应用产品待明确','method':'未提供有证据的产品归类','field':'未明确','text':'','matches':[],'evidence_ids':[]};p['secondary_technology']='实现方向待归类' if id in routes else '技术解读待补齐'
        p['secondary_basis']={'evidence_ids':v.get('evidence_ids',[]) if v else []};details[id]['secondary_technology']=p['secondary_technology']
    modules=[];directions=[]
    for m,n in collections.Counter(p['primary_module'] for p in pats if p['id'] in routes).most_common():
        ps=[p for p in pats if p['id'] in routes and p['primary_module']==m];subs=collections.Counter(p['secondary_technology'] for p in ps)
        modules.append({'module':m,'focus':'本类包括'+ '、'.join(subs.keys())+'。具体结构与条件见各方案原文。','ids':[p['id'] for p in ps]})
        for sub,num in subs.most_common():directions.append({'module':m,'direction':sub,'ids':[p['id'] for p in ps if p['secondary_technology']==sub]})
    featured=copy.deepcopy(ctx.get('featured',[]))
    for group in featured:
        require(group.get('label') and group.get('selection_reason'),'Featured theme needs label and selection reason')
        group.setdefault('difference',group['selection_reason'])
        for node in group['nodes']:
            require(node['id'] in timeline,'Featured node must have completed source analysis');refs(node['id'],node.get('evidence_ids'));require(node.get('title') and node.get('body'),'Featured node needs technical text')
    # Without curated themes, choose populous classes and annual end points transparently.
    if not featured:
        for m in modules[:8]:
            group={'label':m['module'],'module':m['module'],'difference':'按件数选择大类、各年首末申请选读；不作价值排序。','nodes':[]}
            ids=[id for id in m['ids'] if index[id]['filing_date']];years=sorted({index[id]['filing_date'][:4] for id in ids})
            for y in years:
                ys=sorted([id for id in ids if index[id]['filing_date'].startswith(y)],key=lambda id:(index[id]['filing_date'],id))
                for id in dict.fromkeys([ys[0],ys[-1]]):group['nodes'].append({'id':id,'title':index[id]['title'],'body':'；'.join(timeline[id]['means']),'evidence_ids':timeline[id]['evidence_ids']})
            if group['nodes']:featured.append(group)
    comparisons=ctx.get('comparisons',[])
    for v in comparisons:
        require(v.get('application_ids') and set(v['application_ids'])<=set(routes),'Comparison application missing')
        require(v.get('evidence_ids') and set(v['evidence_ids'])<=set(eid for id in v['application_ids'] for eid in sources[id]),'Comparison evidence mismatch')
    events=copy.deepcopy(ctx.get('business_events',{'events':[],'sources':{}}))
    for e in events['events']:
        require(e.get('source') in events['sources'],'Business event source missing');s=events['sources'][e['source']]
        require(s.get('url','').startswith(('https://','http://')) and s.get('locator') and s.get('title'),'Business source must have URL, locator and title')
        require(e.get('date') and e.get('kind') and e.get('precision'),'Business date/kind/precision required')
        e.setdefault('groups',[]);e.setdefault('lines',[])
    official=copy.deepcopy(ctx.get('official',{}))
    if official.get('owned'):
        o=official['owned'];require(all(official.get(k) for k in ['url','source_title','locator','period_end','definition']),'Owned metrics require source, date, definition and locator')
        require(known_date(official['period_end']) and official['url'].startswith(('https://','http://')),'Invalid owned metric date/source')
        require(isinstance(o.get('total'),int) and not isinstance(o['total'],bool) and o['total']>=0,'Owned total must be a nonnegative integer')
        for k in ['invention','utility_model','design']:
            if o.get(k) is not None:require(isinstance(o[k],int) and not isinstance(o[k],bool) and 0<=o[k]<=o['total'],'Invalid owned type count')
        if all(o.get(k) is not None for k in ['invention','utility_model','design']):require(sum(o[k] for k in ['invention','utility_model','design'])==o['total'],'Owned counts do not reconcile')
    dates=sorted(p['filing_date'] for p in pats if p['filing_date']);years=list(map(str,range(int(dates[0][:4]),int(dates[-1][:4])+1))) if dates else []
    boundary=ctx.get('filing_window',{});partial=set(ctx.get('partial_years',[]))
    for key,suffix in [('from','01-01'),('through','12-31')]:
        date=boundary.get(key)
        if date:require(known_date(date),'Invalid filing window');partial.update([date[:4]] if date[5:]!=suffix else [])
    cutoff=run['as_of_date'];require(known_date(cutoff),'Run cutoff must be an ISO date')
    if cutoff[5:]!='12-31':partial.add(cutoff[:4])
    # A sample/latest-N boundary is incomplete even if the first source record falls at a convenient date.
    label=ctx.get('analysis_label','本次所选申请')
    if ctx.get('selection_mode') in ['latest','sample'] and dates:partial.add(dates[0][:4]);partial.add(dates[-1][:4])
    full=[y for y in years if y not in partial];pair=ctx.get('comparison_years',full[-2:] if len(full)>=2 else [])
    require(not pair or len(pair)==2 and pair[0]<pair[1] and all(y in full for y in pair),'Comparison requires two ordered, complete years')
    home=ctx.get('home_authorities',[]);require(isinstance(home,list) and all(re.fullmatch('[A-Z]{2}',x) and x!='WO' for x in home),'Home authority codes must be explicit, not PCT')
    technical=[p for p in pats if p['patent_type'] in ['invention','utility_model']]
    settings={'analysis_label':label,'years':years,'partial_years':sorted(partial),'comparison_years':pair,'home_authorities':home,'status_observed_at':ctx.get('status_observed_at') or '未知','date_note':('申请日 '+dates[0]+' 至 '+dates[-1]) if dates else '申请日期未知','coverage_note':f"技术解读依据 {len(routes)} 件已读申请；目录中的技术申请为 {len(technical)} 件。产品或实现方向无明确依据的记录保留待明确标签。"}
    port=ctx.get('portfolio')
    if port:
        require(port.get('scope') and port.get('source') and port.get('rows') is not None,'Broader portfolio needs scope, source and records');rows=[normalized_row(p) for p in port['rows']];require(len({p['id'] for p in rows})==len(rows),'Duplicate broader portfolio records')
        portfolio={'rows':rows,'scope':port['scope'],'count_note':port.get('count_note','独立申请计数'),'source':port['source']}
    else:portfolio={'rows':pats,'scope':label+'（不是未经检索的企业全部拥有量）','count_note':'与技术分析相同的已纳入申请'}
    portfolio['type_counts']=dict(collections.Counter(p['patent_type'] for p in portfolio['rows']));portfolio['status_counts']=dict(collections.Counter(p['legal_status'] for p in portfolio['rows']))
    payload['patents']=pats
    spec=importlib.util.spec_from_file_location('patent_claim_comparison',Path(__file__).with_name('claim_comparison.py'))
    claim_module=importlib.util.module_from_spec(spec);spec.loader.exec_module(claim_module)
    try:claim_comparisons=claim_module.prepare(payload,details,ctx)
    except ValueError as exc:raise ReportDataError(str(exc)) from exc
    spec=importlib.util.spec_from_file_location('patent_industry_research',Path(__file__).with_name('industry_research.py'))
    industry_module=importlib.util.module_from_spec(spec);spec.loader.exec_module(industry_module)
    try:industry=industry_module.prepare(payload,details,ctx)
    except ValueError as exc:raise ReportDataError(str(exc)) from exc
    research = None
    if payload.get('research'):
        spec=importlib.util.spec_from_file_location('patent_research_workflow',Path(__file__).with_name('research_workflow.py'))
        research_module=importlib.util.module_from_spec(spec);spec.loader.exec_module(research_module)
        try:research=research_module.prepare(payload['research'],details)
        except (ValueError,KeyError,TypeError) as exc:raise ReportDataError(str(exc)) from exc
    return {'research.js':('PP_RESEARCH',research), 'industry-research.js':('PP_INDUSTRY',industry), 'report.js':('PP_REPORT',{'portfolio':portfolio,'simple_families':families,'settings':settings,'comparisons':comparisons}), 'routes.js':('PP_ROUTES',{'nodes':routes,'modules':modules,'directions':directions}), 'timelines.js':('PP_TIMELINES',{'nodes':timeline,'featured':featured}), 'products.js':('PP_PRODUCTS',{'applications':assignments,'groups':list(dict.fromkeys(v['group'] for v in assignments.values()))}), 'product-events.js':('PP_PRODUCT_EVENTS',events), 'official-metrics.js':('PP_OFFICIAL',official), 'claim-comparisons.js':('PP_CLAIM_COMPARISONS',claim_comparisons)}
def emit(out,assembled):
    for name,(global_name,data) in assembled.items():write_js(out,name,global_name,data)
