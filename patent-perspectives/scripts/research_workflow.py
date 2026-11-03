"""Evidence-bound comparison records sharing the existing research-quality plan.

Importing a workflow can establish an unreviewed plan, never a passing review.
Legacy runs without these optional records keep their existing quality gates.
"""
import copy, json, re

STATES={'disclosed','not_disclosed','not_obtained','not_applicable'}
RELATIONS={'parallel','different_conditions','structural_change','improvement','inheritance','replacement','unknown'}
HISTORICAL={'improvement','inheritance','replacement'}
FIELDS={'application_field','technical_problem','technical_means','components','relationships','steps','conditions','claimed_effects'}

def current(c,e):
    return e.get_meta(c,'research_workflow')

def _text(value):
    return isinstance(value, str) and bool(value.strip())

def _same_text(left, right):
    return _text(left) and _text(right) and ' '.join(left.split()) == ' '.join(right.split())

def _plan(c,e,w,create=False):
    """Create only a missing plan; never overwrite an existing research question."""
    quality=e.research_quality_module()
    existing=next((p for p in quality.records(c,'research_plan') if p.get('id')=='active'),None)
    proposed=[]
    for q in w['questions']:
        apps=q.get('application_ids',w['application_ids'])
        e.require(isinstance(apps,list) and apps and all(_text(a) for a in apps)
                  and len(apps)==len(set(apps)) and set(apps)<=set(w['application_ids']),
                  'Research question needs unique applications within its workflow')
        basis=q.get('selection_reason',w['selection_reason'])
        e.require(_text(basis),'Research question selection reason required')
        proposed.append({'id':q['id'],'question':q['text'],
                         'application_ids':sorted(apps),'selection_basis':basis})
    if not existing and create:
        quality.initialize(c)
        quality.import_plan(c,{'questions':proposed},e.research_quality_context())
        existing=next(p for p in quality.records(c,'research_plan') if p.get('id')=='active')
    e.require(existing is not None,
              'Research workflow has no quality plan; re-import it as partial/pending to establish the plan')
    # Existing plans can contain further questions. Explicit plan revision remains
    # the sole path for adding/replacing questions or changing their meaning.
    plan=quality._prepare_plan(c,existing,e.research_quality_context())
    indexed={q['id']:q for q in plan['questions']}
    for q in proposed:
        saved=indexed.get(q['id'])
        e.require(saved is not None and _same_text(saved['question'],q['question'])
                  and set(saved['application_ids'])==set(q['application_ids']),
                  'Research question conflicts with the existing quality plan: '+q['id']
                  +'; revise explicitly with research-plan-import and revision_reason')
    return plan

def _review(c,e,plan,q):
    quality=e.research_quality_module()
    result=next((r for r in quality.records(c,'research_reviews') if r.get('question_id')==q['id']),None)
    if not result:return None,'not_reviewed'
    try:
        checked=quality._prepare_research(c,result,plan,e.research_quality_context())
    except (ValueError,KeyError,TypeError):
        return None,'stale'
    if checked['status']!='resolved':return checked,'insufficient_evidence'
    if checked['review_result']!='pass':return checked,'needs_revision'
    return checked,'current_resolved'

def binding(c,e,w):
    apps=w['application_ids']
    # Bind exact sources, evidence, analyses, original scope and population. A
    # rejection also invalidates population_hash; no separate validity bypass.
    docs=[dict(r) for a in apps for r in c.execute('SELECT * FROM documents WHERE application_id=? ORDER BY id',(a,))]
    evidence=[dict(r) for a in apps for r in c.execute('SELECT * FROM evidence WHERE application_id=? ORDER BY id',(a,))]
    # population_hash includes the semantic analyses and their source versions.
    # Quality plan/review imports do not change it, preventing a circular cycle
    # where completing a review would immediately expire the comparison work.
    return e.digest({'workflow':{k:v for k,v in w.items() if k!='binding_sha256'},'population':e.population_hash(c),'scope':e.run_info(c), 'documents':docs,'evidence':evidence,
      'relations':[json.loads(c.execute('SELECT data FROM relations WHERE id=?',(i,)).fetchone()[0]) if c.execute('SELECT 1 FROM relations WHERE id=?',(i,)).fetchone() else None for i in w['relation_ids']],
      'insights':[json.loads(c.execute('SELECT data FROM insights WHERE id=?',(i,)).fetchone()[0]) if c.execute('SELECT 1 FROM insights WHERE id=?',(i,)).fetchone() else None for i in w['insight_ids']]})

def validate(c,e,w):
    req=e.require
    def ref_ids(value,label):
        req(isinstance(value,list) and all(isinstance(i,str) and i for i in value) and len(value)==len(set(value)),label+' must be an array of unique IDs')
        return set(value)
    def unique(items,label):
        req(isinstance(items,list),label+' must be an array')
        ids=[v.get('id') for v in items];req(all(ids) and len(ids)==len(set(ids)),label+' IDs missing or duplicated')
        return set(ids)
    retired=e.get_meta(c,'research_retired',{})
    req(not set(w.get('insight_ids',[]))&set(retired.get('insight_ids',[])) and not set(w.get('relation_ids',[]))&set(retired.get('relation_ids',[])),'Current research records cannot be retired')
    req(w.get('schema_version')==1 and w.get('id'),'Unsupported research workflow')
    for key in ('purpose','audience','work_context','scope','selection_reason'):
        req(isinstance(w.get(key),str) and w[key].strip(),'Research '+key+' required')
    apps=ref_ids(w.get('application_ids',[]),'Research applications'); req(apps and apps<={a['id'] for a in e.included_applications(c)},'Research application outside included population')
    qids=unique(w.get('questions'),'Question');req(qids,'Research questions required')
    req(sum(q.get('level')=='main' for q in w['questions'])==1,'One main research question required')
    for q in w['questions']:
        req(q.get('origin')=='researcher','Research questions must preserve researcher origin')
        req(q.get('level') in ('main','sub') and q.get('text') and q.get('required_evidence'),'Question text/level/required_evidence required')
        req(q.get('status') in ('answered','partial','pending') and q.get('answer') and isinstance(q.get('remaining'),list),'Question answer/status/remaining required')
        req(q['status']=='answered' or q['remaining'],'Partial/pending question must preserve remaining work')
    plan=_plan(c,e,w)
    for q in w['questions']:
        if q['status']=='answered':
            reviewed,state=_review(c,e,plan,q)
            req(state=='current_resolved',
                'Answered research question needs its current resolved/pass independent review: '+q['id'])
            req(_same_text(q['answer'],reviewed['answer']),
                'Answered research question contradicts its reviewed answer: '+q['id'])
    terms=unique(w.get('terminology',[]),'Term')
    dims=unique(w.get('dimensions'),'Dimension');req(dims,'Comparison dimensions required')
    for d in w['dimensions']:
        req(d.get('label') and d.get('definition') and ref_ids(d.get('question_ids',[]),'Dimension questions') and set(d['question_ids'])<=qids,'Dimension definition/question mismatch')
    evidence={r['id']:json.loads(r['data']) for r in c.execute('SELECT * FROM evidence')}
    documents={r['id']:r for r in c.execute('SELECT * FROM documents')}
    analyses={r['application_id']:json.loads(r['data']) for r in c.execute('SELECT * FROM analyses')}
    def source(s, need=True, allow_missing=False):
        req(s.get('application_id') in apps,'Research source application mismatch')
        if allow_missing and s.get('document_id') is None:
            pub=c.execute('SELECT application_id FROM publications WHERE id=?',(s.get('publication_number'),)).fetchone()
            req(pub and pub[0]==s['application_id'] and s.get('version'),'Missing-version source needs known same-application publication and intended version')
            req(not s.get('evidence_ids') and not s.get('claim_levels'),'Missing document cannot claim evidence or claim levels')
            return None, []
        doc=documents.get(s.get('document_id')); req(doc is not None and doc['application_id']==s['application_id'],'Research document/application mismatch')
        req(e.document_is_eligible(c,doc),'Research source is incomplete or rejected')
        analysis_row=c.execute('SELECT * FROM analyses WHERE application_id=?',(s['application_id'],)).fetchone()
        req(analysis_row and e.analysis_is_current(c,analysis_row),'Research source needs a current semantic analysis')
        ds=json.loads(doc['data']);req(s.get('publication_number')==doc['publication_id'] and s.get('version')==ds['version'],'Research document version mismatch')
        ids=s.get('evidence_ids',[]);req(isinstance(ids,list) and (ids or not need),'Research source evidence missing')
        for i in ids:
            v=evidence.get(i);req(v and v['application_id']==s['application_id'] and v['document_id']==doc['id'],'Research evidence crosses application/document')
            req(doc['text'][v['start']:v['end']]==v['quote'],'Research quote mismatch')
            req(i in analyses.get(s['application_id'],{}).get('evidence_ids',[]),'Research evidence outside active analysis')
        return doc, [evidence[i] for i in ids]
    for t in w.get('terminology',[]):
        req(t.get('concept') and t.get('scope') and t.get('equivalence') in ('contextual','distinct'),'Term concept/scope/equivalence required')
        req(t.get('entries'),'Term original entries required')
        for s in t['entries']:
            _,ev=source(s);req(s.get('original_term') and any(s['original_term'] in v['quote'] for v in ev),'Original term absent from cited evidence')
    cids=unique(w.get('comparisons'),'Comparison')
    for comp in w['comparisons']:
        req(comp.get('title') and comp.get('body') and comp.get('scope'),'Comparison title/body/scope required')
        req(ref_ids(comp.get('question_ids',[]),'Comparison questions') and set(comp['question_ids'])<=qids,'Comparison question mismatch')
        seen=set()
        for u in comp.get('units',[]):
            req(u.get('dimension_id') in dims,'Unknown comparison dimension')
            key=(u['application_id'],u['dimension_id']);req(key not in seen,'Duplicate comparison unit');seen.add(key)
            state=u.get('state');req(state in STATES and u.get('text') and u.get('conditions'),'Unit state/text/conditions required')
            doc,ev=source(u,need=state=='disclosed',allow_missing=state=='not_obtained')
            req(u.get('kind') in ('disclosed','inference','unknown'),'Unit disclosure/inference kind required')
            req(state!='disclosed' or u['kind']!='unknown','Disclosed unit must identify disclosure or inference')
            req(state=='disclosed' or u['kind']=='unknown','Unknown unit cannot become a negative conclusion')
            req(state=='disclosed' or u.get('reason'),'Unknown state needs reason')
            req(u['kind']!='inference' or u.get('basis'),'Inference basis required')
            req(set(u.get('field_refs',[]))<=FIELDS,'Unknown per-patent technical field')
            req(set(u.get('term_ids',[]))<=terms,'Unknown terminology reference')
            if state=='not_disclosed':
                claims=json.loads(doc['data']).get('claims',[])
                req(u.get('reviewed_claim_numbers')==[x['number'] for x in claims] and claims,'Not-disclosed needs complete reviewed claim scope')
            if ev and doc['document_type']=='claims':
                nums={v['locator']['claim_number'] for v in ev};levels=u.get('claim_levels',[])
                req({x.get('number') for x in levels}==nums,'Claim levels must match exact evidence')
                for level in levels:
                    req(level.get('level') in ('independent','dependent'),'Claim level required')
                    req(level['level']!='dependent' or isinstance(level.get('depends_on'),list) and level['depends_on'] and all(isinstance(n,int) and not isinstance(n,bool) and n>0 for n in level['depends_on']),'Dependent claim needs an integer parent-claim array')
        req(seen=={(a,d) for a in apps for d in dims},'Comparison must preserve explicit states for every application/dimension')
    relations={r['id']:json.loads(r['data']) for r in c.execute('SELECT * FROM relations')}
    for rid in w['relation_ids']:
        r=relations.get(rid);req(r,'Research relation missing')
        req(r.get('type') in RELATIONS and r.get('kind')=='inference','Technical relationship needs supported type and analysis nature')
        req(r.get('source') in apps and r.get('target') in apps and r['source']!=r['target'],'Technical relation endpoint missing')
        req(ref_ids(r.get('question_ids',[]),'Relation questions') and set(r['question_ids'])<=qids,'Relation question mismatch')
        req(r.get('similarities') and r.get('differences') and isinstance(r.get('limitations'),list) and r['limitations'] and r.get('basis'),'Relation technical basis/limitations required')
        req(r.get('comparison_ids') and set(r['comparison_ids'])<=cids,'Relation comparison missing')
        ends=r.get('endpoints',[]);req({s.get('application_id') for s in ends}=={r['source'],r['target']} and len(ends)==2,'Relation requires two source endpoints')
        ids=[]
        for s in ends: source(s);ids+=s['evidence_ids']
        req(set(ids)==set(r.get('evidence_ids',[])),'Relation evidence does not match both endpoints')
        req(r.get('historical_status') in ('unproven','supported'),'Historical support status required')
        if r['type'] in HISTORICAL:
            req(r['historical_status']=='supported' and r.get('history_evidence'),'Historical relation needs extra evidence beyond dates')
            for s in r['history_evidence']:source(s)
            req(set(i for s in r['history_evidence'] for i in s['evidence_ids'])-set(ids),'Historical evidence must be additional to structural comparison')
        else:req(r['historical_status']=='unproven','Comparative relation cannot imply historical evolution')
    insights={r['id']:json.loads(r['data']) for r in c.execute('SELECT * FROM insights')}
    req(w.get('insight_ids'),'At least one useful finding required; no positive-result quota')
    for iid in w['insight_ids']:
        f=insights.get(iid);req(f,'Research finding missing')
        req(ref_ids(f.get('question_ids',[]),'Finding questions') and set(f['question_ids'])<=qids,'Finding question mismatch')
        req(ref_ids(f.get('research_question_ids',[]),'Finding quality questions')==set(f['question_ids']),
            'Finding research_question_ids must equal its stable question_ids')
        req(f.get('comparison_ids') or f.get('relation_ids'),'Finding must link comparison or relation')
        req(set(f.get('comparison_ids',[]))<=cids and set(f.get('relation_ids',[]))<=set(w['relation_ids']),'Finding comparison/relation mismatch')
        req(f.get('use') and isinstance(f.get('alternatives'),list) and isinstance(f.get('next_checks'),list),'Finding use/alternatives/next checks required')
        req(set(f.get('patent_ids',[]))<=apps,'Finding scope exceeds research samples')
    # Each role is a view of the same facts, not a competing fact record.
    grouped={};role_sets={}
    for iid in w['insight_ids']:
        f=insights[iid];fid=f.get('finding_id');req(fid,'Finding shared identity required')
        core={k:f.get(k) for k in ('title','body','question_ids','research_question_ids','patent_ids','evidence_ids','scope','limitations','comparison_ids','relation_ids','use','alternatives','next_checks','kind')}
        if fid in grouped:req(core==grouped[fid],'Role views must preserve shared finding facts')
        req(f['role'] not in role_sets.setdefault(fid,set()),'Duplicate role for shared finding')
        role_sets[fid].add(f['role']);grouped[fid]=core
    req(all(roles==set(e.ROLES) for roles in role_sets.values()),'Each shared finding requires all three role views')
    answered={q for iid in w['insight_ids'] for q in insights[iid]['question_ids']}
    req(all(q['status']=='pending' or q['id'] in answered for q in w['questions']),'Answered question needs finding support')

def _import_workflow(c,e,p):
    p=copy.deepcopy(e.sanitized(p));relations=p.pop('relations',[]);insights=p.pop('insights',[])
    # Display-only review state from a previous export is recomputed, not stored.
    for q in p.get('questions',[]):
        for key in ('recorded_status','quality_review_status'):q.pop(key,None)
    for finding in insights:
        if 'research_question_ids' not in finding:
            finding['research_question_ids']=copy.deepcopy(finding.get('question_ids',[]))
    p['relation_ids']=[r['id'] for r in relations];p['insight_ids']=[i['id'] for i in insights]
    req=e.require
    old=current(c,e)
    retired=e.get_meta(c,'research_retired',{'insight_ids':[],'relation_ids':[]})
    # Retain former records; IDs cannot overwrite unrelated legacy records.
    for table,items in [('relations',relations),('insights',insights)]:
        for item in items:
            row=c.execute('SELECT data FROM '+table+' WHERE id=?',(item['id'],)).fetchone()
            req(not row or item['id'] in set((old or {}).get(table[:-1]+'_ids',[]))|set(retired.get(table[:-1]+'_ids',[])),'Research ID collides with legacy '+table)
    # Validate the question structure before plan creation, including stable IDs.
    req(isinstance(p.get('questions'),list) and p['questions']
        and all(isinstance(q,dict) and _text(q.get('id')) and _text(q.get('text')) for q in p['questions']),
        'Research questions require stable IDs and text')
    req(len({q['id'] for q in p['questions']})==len(p['questions']),'Question IDs missing or duplicated')
    _plan(c,e,p,create=True)
    e.import_relations(c,relations);e.import_insights(c,insights)
    # Reactivated IDs become current before validation examines retirement.
    # All metadata and record writes remain within import_workflow's savepoint.
    for key in ('insight_ids','relation_ids'):
        retired[key]=sorted((set(retired.get(key,[]))|set((old or {}).get(key,[])))-set(p[key]))
    e.set_meta(c,'research_retired',retired)
    validate(c,e,p)
    p['binding_sha256']=binding(c,e,p)
    e.set_meta(c,'research_workflow',p);e.event(c,'research-import',{'id':p['id'],'questions':len(p['questions'])})
    return {'research_imported':p['id'],'questions':len(p['questions']),'comparisons':len(p['comparisons']),'relations':len(relations),'insights':len(insights)}

def import_workflow(c,e,p):
    """Atomic even when a caller catches a failed import inside its transaction."""
    c.execute('SAVEPOINT research_workflow_import')
    try:
        result=_import_workflow(c,e,p)
    except BaseException:
        c.execute('ROLLBACK TO SAVEPOINT research_workflow_import')
        c.execute('RELEASE SAVEPOINT research_workflow_import')
        raise
    c.execute('RELEASE SAVEPOINT research_workflow_import')
    return result

def check(c,e):
    w=current(c,e)
    if not w:return []
    try:
        validate(c,e,w)
        e.require(w.get('binding_sha256')==binding(c,e,w),'Research sources/scope/linked findings changed; host review and research-import required')
        pending=[q['id'] for q in w['questions'] if q['status']!='answered']
        if pending:
            return [{'code':'research_workflow_unfinished','detail':'Unanswered research questions: '+', '.join(pending)}]
    except (ValueError,KeyError,TypeError) as exc:
        return [{'code':'research_workflow_invalid','detail':str(exc)}]
    return []

def export(c,e):
    w=copy.deepcopy(current(c,e))
    if not w:return None
    for table in ('relations','insights'):
        w[table]=[json.loads(c.execute('SELECT data FROM '+table+' WHERE id=?',(i,)).fetchone()[0]) for i in w.pop(table[:-1]+'_ids')]
    try:plan=_plan(c,e,w)
    except (ValueError,KeyError,TypeError):plan=None
    for question in w['questions']:
        reviewed,state=_review(c,e,plan,question) if plan else (None,'no_matching_plan')
        if state=='current_resolved' and not _same_text(question['answer'],reviewed['answer']):
            state='answer_mismatch'
        question['quality_review_status']=state
        if question['status']=='answered' and state!='current_resolved':
            question['recorded_status']='answered'
            question['status']='partial'
            question['remaining']=list(question.get('remaining',[]))+['Current independent research review required.']
    return w

def prepare(packet,details):
    """Embed only cited same-version sources for an offline evidence reader."""
    if not packet:return None
    result=copy.deepcopy(packet);apps=result['application_ids'];result['sources']={};result['documents']={}
    for a in apps:
        d=details[a];result['sources'].update({v['id']:v for v in d['evidence']})
        result['documents'].update({v['id']:v for v in d['documents']})
    return result
