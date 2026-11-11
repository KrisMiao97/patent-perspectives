"""Render the reusable reader shell. Real reports retain the existing research gates."""
import argparse
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def validate(data):
    for key in ('company','business','scope','roles','orders','chapters','records','sources'):
        if not data.get(key): raise ValueError('Missing reader field: '+key)
    if data['scope'].get('mode') not in ('search','materials'): raise ValueError('Explicit search/materials scope required')
    for key in ('label','as_of','status_observed_at','partial_years'):
        if key not in data['scope']: raise ValueError('Missing scope '+key)
    ids=[str(p['id']) for p in data['records']]
    if len(ids)!=len(set(ids)): raise ValueError('Duplicate application IDs')
    chapter_ids=[c['id'] for c in data['chapters']]
    if len(chapter_ids)!=len(set(chapter_ids)): raise ValueError('Duplicate chapter IDs')
    sources={s['id']:s for s in data['sources']}
    if len(sources)!=len(data['sources']): raise ValueError('Duplicate evidence IDs')
    for source in sources.values():
        if not source.get('quote') or source['quote'] not in source.get('text',''): raise ValueError('Quote does not match source text')
    def refs(item):
        if not item.get('evidence_ids') or any(x not in sources for x in item['evidence_ids']): raise ValueError('Missing or unknown evidence')
    for p in data['records']:
        if p.get('type')=='design' and not p.get('evidence_ids'):
            p['evidence_ids']=[]
        else:refs(p)
    for role in ('management','rd','ip'):
        r=data['roles'][role]
        if not all(r.get(k) for k in ('title','answer','scope_label','reasons')): raise ValueError('Role needs answer, scope and reasons')
        for point in r['reasons']:refs(point)
        if sorted(data['orders'][role])!=sorted(chapter_ids):raise ValueError('Each role must have the complete shared chapter set')
    for chapter in data['chapters']:
        if not chapter.get('conclusion') or not chapter.get('scope_label'):raise ValueError('Every chapter needs a conclusion and its scope')
        refs(chapter)

def bind_run(data, db):
    spec=importlib.util.spec_from_file_location('reader_engine',ROOT/'scripts/patent_perspectives.py')
    engine=importlib.util.module_from_spec(spec);spec.loader.exec_module(engine)
    if not Path(db).is_file():raise ValueError('Existing research database required')
    c=engine.db_open(db)
    try:
        result=engine.validate_run(c)
        if result['status']!='complete':raise ValueError('Research gates have not passed; inspect validate/status')
        run=engine.run_info(c)
        if data['company']!=run['company'] or data['scope']['as_of']!=run['as_of_date']:raise ValueError('Reader company/date differs from research run')
        expected_mode='materials' if run['scope'].get('acquisition_mode')=='materials' else 'search'
        if data['scope']['mode']!=expected_mode:raise ValueError('Reader scope mode differs from research run')
        apps={a['id']:a for a in engine.included_applications(c)}
        if {str(r['id']) for r in data['records']}!=set(apps):raise ValueError('Reader catalogue must equal the validated independent-application scope')
        evidence={r['id']:dict(r) for r in c.execute('SELECT * FROM evidence')}
        for source in data['sources']:
            ev=evidence.get(source['id'])
            if not ev:raise ValueError('Reader source must reference a research evidence ID')
            doc=c.execute('SELECT * FROM documents WHERE id=?',(ev['document_id'],)).fetchone()
            ev_data=json.loads(ev['data'])
            if source['quote']!=ev_data['quote'] or source['text']!=doc['text'] or source['publication']!=doc['publication_id']:raise ValueError('Reader evidence differs from stored original')
            source['version']=json.loads(doc['data'])['version']
            location=ev_data['locator']
            labels={'claim_number':'权利要求','paragraph':'段落','paragraph_number':'段落','page':'页码','page_number':'页码','figure':'附图','section':'章节','start':'起始位置','end':'结束位置'}
            source['locator']='；'.join(f'{labels[k]} {v}' for k,v in location.items() if k in labels) if isinstance(location,dict) else str(location)
            source['locator_details']=location
        for record in data['records']:
            app=apps[str(record['id'])]
            if any(evidence.get(eid,{}).get('application_id')!=app['id'] for eid in record.get('evidence_ids',[])):raise ValueError('Record evidence belongs to another application')
            if record['type']!=app['patent_type'] or record['filing_date']!=app['filing_date']:raise ValueError('Reader type/date differs from the research database')
            if record['publication'] not in app['publication_numbers']:raise ValueError('Reader publication differs from application')
            record['status']=app['legal_status'];record['read_complete']=app['patent_type']!='design'
        data['validation']={'run_id':run['run_id'],'status':result['status'],'scope_mode':expected_mode}
    finally:c.close()

def build(data, output):
    validate(data)
    assets=ROOT/'assets/reader'
    html=(assets/'index.html').read_text(encoding='utf-8')
    encoded=json.dumps(data,ensure_ascii=False).replace('<','\\u003c').replace('\u2028','\\u2028').replace('\u2029','\\u2029')
    for marker,value in [('/*READER_CSS*/',(assets/'report.css').read_text(encoding='utf-8')),('/*READER_JS*/',(assets/'report.js').read_text(encoding='utf-8')),('/*READER_DATA*/',encoded)]:
        if html.count(marker)!=1:raise ValueError('Template marker missing')
        html=html.replace(marker,value)
    output=Path(output);output.parent.mkdir(parents=True,exist_ok=True);output.write_text(html,encoding='utf-8')

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--input',required=True);p.add_argument('--output',required=True)
    group=p.add_mutually_exclusive_group(required=True);group.add_argument('--db');group.add_argument('--demo',action='store_true')
    args=p.parse_args();data=json.loads(Path(args.input).read_text(encoding='utf-8-sig'))
    if args.demo:
        if data.get('synthetic') is not True:raise ValueError('Demo requires explicitly synthetic data')
    else:
        if data.get('synthetic'):raise ValueError('Synthetic data cannot enter a real report')
        bind_run(data,args.db)
    build(data,args.output);print(args.output)
