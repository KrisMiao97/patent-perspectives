"""Export validated industry research and package explicit local materials."""
import csv
import json
import shutil
from pathlib import Path
from urllib.parse import unquote

LABELS = {'project':'立项探索','competition':'竞争格局','profile':'公司画像','selection':'路线选择','forecast':'条件化预测','transfer':'跨行业借鉴','maturity':'成熟度','summary':'判断','conditions':'成立条件','unknowns':'未知与待验证','candidates':'借鉴候选','hypotheses':'预测假设','dimensions':'评价维度','criteria':'选型指标','domain':'来源行业','shared_function':'共同功能','mechanism':'作用机理','differences':'场景差异','adaptation':'迁移改造','test':'验证方法','horizon':'时间窗口','change':'变化假设','driver':'推动条件','blocker':'阻碍因素','trigger':'观察信号','falsifier':'反证','rubric':'判定方法','name':'名称','stage':'证据阶段','basis':'依据','scenario':'应用场景','recommendation':'推荐','reversal':'重新评价条件','priority':'约束属性','measure':'评价方法','source_ids':'来源','status':'状态','reason':'原因'}

def package_materials(out, data, materials_root=None):
    if data is None: return
    out=Path(out).resolve()
    base=Path(materials_root).resolve() if materials_root else None
    allowed={'.pdf','.png','.jpg','.jpeg','.webp','.txt','.md','.csv','.json'}
    for source in data['sources']:
        local=source.get('local_path')
        if not local: continue
        rel=Path(unquote(local))
        dest=(out/rel).resolve()
        if not dest.is_relative_to(out) or dest==out or dest.suffix.lower() not in allowed:
            raise ValueError('Industry local material must be a safe document within output: '+local)
        if dest.is_file(): continue  # Original documents already copied by existing renderer.
        if base is None: raise ValueError('Missing industry_materials_root for local material: '+local)
        if not rel.parts or rel.parts[0]!='industry-materials':
            raise ValueError('New local industry material must use industry-materials/ prefix')
        src=(base/rel).resolve()
        if not src.is_relative_to(base) or not src.is_file():
            raise ValueError('Missing or outside-root industry material: '+local)
        dest.parent.mkdir(parents=True,exist_ok=True)
        shutil.copy2(src,dest)

def csv_cell(value):
    value=str(value or '')
    return "'"+value if value.lstrip().startswith(('=','+','-','@')) else value

def write_csv(path, fields, rows):
    with path.open('w',encoding='utf-8-sig',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=fields);writer.writeheader()
        for row in rows:writer.writerow({k:csv_cell(row.get(k,'')) for k in fields})

def describe(value, depth=0):
    lines=[]
    if isinstance(value,dict):
        for k,v in value.items():
            if k=='source_ids':lines.append('  '*depth+'- 来源：'+', '.join(v));continue
            label=LABELS.get(k,k)
            if isinstance(v,(dict,list)):
                lines.append('  '*depth+'- '+label+'：');lines.extend(describe(v,depth+1))
            else:lines.append('  '*depth+'- '+label+'：'+str(v))
    elif isinstance(value,list):
        for i,v in enumerate(value,1):
            if isinstance(v,dict):lines.append('  '*depth+str(i)+'.');lines.extend(describe(v,depth+1))
            else:lines.append('  '*depth+'- '+str(v))
    return lines

def emit(out, data, reference_corpora=None):
    if data is None:return
    out=Path(out)
    (out/'industry-research.json').write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
    if reference_corpora:
        (out/'industry-reference-corpora.json').write_text(json.dumps(reference_corpora,ensure_ascii=False,indent=2),encoding='utf-8')
    sources=data['sources'];companies={c['id']:c for c in data['companies']};routes={r['id']:r for r in data['routes']}
    write_csv(out/'industry-sources.csv',['id','kind','title','locator','observed_at','publication_date','url','local_path','application_id','document_id','publication_number','version'],sources)
    rows=[]
    for cell in data['matrix']:
        for claim in cell['claims']:
            rows.append({'company':companies[cell['company_id']]['name'],'direction':routes[cell['route_id']]['name'],'source_kind':claim['kind'],'statement':claim['text'],'source_ids':';'.join(claim['source_ids'])})
    write_csv(out/'industry-matrix.csv',['company','direction','source_kind','statement','source_ids'],rows)
    lines=['# '+companies[data['target_company_id']]['name']+' · 公司技术研究','',data['scope']['topic'],'','研究截止：'+data['scope']['as_of'],'','范围：'+data['scope']['selection_basis'],'',data['matrix_note'],'']
    for task in data['tasks']:
        lines+=['## '+LABELS[task['kind']], '',task['question'],'',task['answer'],'','成立条件：'+task['conditions'],'','来源：'+', '.join(task['source_ids']),'']
        if task.get('reason'):lines+=['缺口：'+task['reason'],'']
    for route in data['routes']:
        lines+=['## 技术路线：'+route['name'],'','研究理由：'+route['selection_reason'],'','工程问题：'+route['problem'],'','实现过程：'+route['mechanism'],'','来源：'+', '.join(route['source_ids']),'']
        for key in ('transfer','forecast','maturity','selection'):
            if key in route:lines+=['### '+LABELS[key],'']+describe(route[key])+['']
    lines+=['## 公司与方向的证据','']
    for row in rows:lines+=['- '+row['company']+' / '+row['direction']+'：'+row['source_kind']+' '+row['statement']+' ['+row['source_ids']+']']
    if data.get('jurisdiction_cases'):
        lines+=['','## 选定案例地域观察','','仅选定案例的同族记录，不代表企业整体布局或权利有效。','']
        lines+=describe(data['jurisdiction_cases'])
    lines+=['','## 来源','']
    for s in sources:
        lines+=['- ['+s['id']+'] '+s['kind']+' '+s['title']+'；'+s['locator']+'；观察日期：'+s.get('observed_at','未知')+'；'+(s.get('url') or s.get('local_path',''))]
    (out/'industry-research.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
