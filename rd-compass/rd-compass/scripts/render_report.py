"""Render a portable R&D report with Python 3.10+; no third-party dependencies."""
from pathlib import Path
import argparse
import html
import json
import re
import os
import tempfile
from datetime import date
from urllib.parse import urlsplit

ROLES = ['材料披露', '方案差异', '可能能力', '成立条件', '尚存假设']
def esc(value): return html.escape(str(value), quote=True)
def para(value): return '<p>'+esc(value)+'</p>'

def validate(data):
    if not isinstance(data,dict) or data.get('schema_version')!=1: raise ValueError('schema_version must be 1')
    for key in ['title','cutoff','finding','opportunity','judgment','boundary']:
        if not isinstance(data.get(key),str) or not data[key].strip(): raise ValueError(f'Missing text: {key}')
    date.fromisoformat(data['cutoff'])
    for key in ['directions','evidence']:
        if not isinstance(data.get(key),list): raise ValueError(f'{key} must be a list')
    dirs=data['directions']; evidence=data['evidence']
    def ids(items,prefix):
        result=[x['id'] for x in items]
        if len(set(result))!=len(result) or any(not re.fullmatch(prefix+r'[1-9]\d*',x) for x in result): raise ValueError('Duplicate or invalid '+prefix+' IDs')
        return set(result)
    ds=ids(dirs,'D');es=ids(evidence,'E')
    def links(values):
        if not isinstance(values,list) or any(x not in es for x in values): raise ValueError('Unresolved evidence reference')
    for d in dirs:
        for key in ['name','benefit','tradeoff','judgment','evidence_state','decision_state']:
            if not isinstance(d.get(key),str) or not d[key].strip(): raise ValueError(d['id']+': missing '+key)
        if len(d.get('reasoning',[]))!=5: raise ValueError(d['id']+': requires five reasoning steps')
        for step in d['reasoning']:
            if not step.get('title') or not step.get('text'): raise ValueError('Incomplete reasoning step')
            links(step.get('evidence',[]))
        if not d.get('conditions') or any(not c.get('if') or not c.get('then') for c in d['conditions']): raise ValueError('Missing conditional judgment')
        if d.get('figure'):
            if not re.fullmatch(r'data:image/(?:svg\+xml|png|jpeg);base64,[A-Za-z0-9+/=\s]+',d['figure']): raise ValueError('Figures must be embedded image data')
            if not d.get('caption'): raise ValueError('Figure requires an explanatory caption')
    for e in evidence:
        for key in ['title','summary','source_role','location','disclosure','limitation']:
            if not isinstance(e.get(key),str) or not e[key].strip(): raise ValueError(e['id']+': missing '+key)
        if not isinstance(e.get('in_sample'),bool): raise ValueError('in_sample must explicitly be true or false')
        if any(x not in ds for x in e.get('directions',[])): raise ValueError('Unresolved direction reference')
        for doc in e.get('documents',[]):
            u=urlsplit(doc['url'])
            if u.scheme not in ['http','https'] or not u.netloc: raise ValueError('Invalid public source URL')
    previous=''
    for node in data.get('timeline',[]):
        date.fromisoformat(node['date'])
        if node['date']<previous: raise ValueError('Timeline must be sorted by publication date')
        previous=node['date'];links(node.get('evidence',[]))
    for row in data.get('periods',[]):
        if not row.get('conclusion') or not row.get('basis'): raise ValueError('Period needs a conclusion and basis')
    for log in data.get('worklog',[]):
        if not all(log.get(x) for x in ['question','action','finding','remaining']): raise ValueError('Incomplete evidence work log')
    for source in data.get('references',[]):
        u=urlsplit(source['url'])
        if not source.get('title') or u.scheme not in ['http','https'] or not u.netloc: raise ValueError('Invalid reference source')

def render(data):
    validate(data)
    chip=lambda xs: ''.join(f'<a class="e-link" href="#e-{esc(x)}">{esc(x)} 证据</a>' for x in xs)
    heading=lambda id,title,desc: f'<section id="{id}"><div class="section-head"><h2>{esc(title)}</h2><p>{esc(desc)}</p></div>'
    dirs=data['directions'];ev=data['evidence']; parts=[]
    nav=[('summary','研究结论'),('compare','方向比较'),('routes','结构与依据')]
    if data.get('timeline') or data.get('periods'):nav.append(('timeline','时间与变化'))
    nav.extend([('evidence','证据索引'),('next','补证与边界')])
    parts.append('<header class="top"><div class="wrap"><span class="brand">研发罗盘</span><nav aria-label="报告目录">'+''.join(f'<a href="#{a}">{b}</a>' for a,b in nav)+'</nav></div></header><main class="wrap">')
    parts.append(f'<div id="summary"><p class="meta">研发方向预研 · 资料截至 {esc(data["cutoff"])}</p><h1>{esc(data["title"])}</h1><div class="executive">')
    for k,label in [('finding','研究发现'),('opportunity','产品机会'),('judgment','当前判断')]:parts.append(f'<p><strong>{label}：</strong>{esc(data[k])}</p>')
    parts.append('</div>'+para(data['boundary']).replace('<p>','<p class="boundary">'))
    parts.append('<div class="scope">'+''.join(f'<span>{esc(x)}</span>' for x in data.get('scope',[]))+'</div><p class="key">D 为方向编号，E 为证据编号；编号不表示优先级。披露、推断与实测分别说明。</p><div class="toolbar"><a class="btn" id="data-download" download="research-data.json">下载研究数据</a><button class="btn" id="print">打印完整报告</button></div></div>')
    parts.append(heading('compare','机会在哪里，什么条件下更合适','同一列比较全部方向；具体结构和依据在下方展开。'))
    if dirs:
        fields=['可能形成的产品能力','主要取舍','当前判断']
        parts.append('<label class="compare-control">比较项<select id="compare-field">'+''.join(f'<option value="{i}" {"selected" if i==2 else ""}>{x}</option>' for i,x in enumerate(fields))+'</select></label><div class="table-wrap"><table class="comparison" data-field="2"><thead><tr><th>候选方向</th>'+''.join(f'<th data-column="{i}">{x}</th>' for i,x in enumerate(fields))+'</tr></thead><tbody>')
        for d in dirs:parts.append(f'<tr><th scope="row"><a href="#r-{d["id"]}">{d["id"]} {esc(d["name"])}</a></th>'+''.join(f'<td data-column="{i}">{esc(d[k])}</td>' for i,k in enumerate(['benefit','tradeoff','judgment']))+'</tr>')
        parts.append('</tbody></table></div>')
    else:parts.append('<p class="empty">当前资料尚不足以形成具体方向；已知发现与覆盖边界见上方。</p>')
    parts.append('</section>'+heading('routes','结构差异怎样形成产品机会','材料披露说明来源事实；可能能力是比较推断；尚存假设保留待验证部分。'))
    for d in dirs:
        parts.append(f'<article class="route" id="r-{d["id"]}"><h3>{d["id"]} {esc(d["name"])}</h3><p class="judgment">{esc(d["judgment"])}</p><div class="states"><span>证据状态：{esc(d["evidence_state"])}</span><span>决策阶段：{esc(d["decision_state"])}</span></div><div class="route-grid {"" if d.get("figure") else "no-figure"}">')
        if d.get('figure'):parts.append(f'<figure><div class="figure-scroll" tabindex="0" role="region" aria-label="{d["id"]} 结构图，可横向滚动查看"><img src="{esc(d["figure"])}" alt="{esc(d["caption"])}"></div><figcaption><span class="figure-hint">结构图可左右滑动查看。</span>{esc(d["caption"])}</figcaption></figure>')
        parts.append('<ol class="steps">')
        for role,step in zip(ROLES,d['reasoning']):parts.append(f'<li><span class="step-role">{role}</span><h4>{esc(step["title"])}</h4>{para(step["text"])}{chip(step.get("evidence",[]))}</li>')
        parts.append('</ol></div><div class="conditions"><h4>哪些条件会改变取舍</h4><dl>'+''.join(f'<dt>{esc(c["if"])}</dt><dd>{esc(c["then"])}</dd>' for c in d['conditions'])+'</dl></div></article>')
    parts.append('</section>')
    if data.get('timeline') or data.get('periods'):
        parts.append(heading('timeline','公开时间与技术变化','按公开时间展示并行做法；时间先后不代表继承、上市或行业采用。'))
        parts.append('<ol class="timeline">'+''.join(f'<li><time datetime="{n["date"]}">{n["date"]}</time><h3>{esc(n["title"])}</h3>{para(n["change"])}{chip(n.get("evidence",[]))}</li>' for n in data.get('timeline',[]))+'</ol>')
        parts.append('<div class="periods">'+''.join(f'<article class="period"><span class="meta">{esc(n["label"])}</span><h3>{esc(n["conclusion"])}</h3>{para(n["basis"])}</article>' for n in data.get('periods',[]))+'</div></section>')
    parts.append(heading('evidence','逐条看了哪些证据','每条先显示披露要点，再展开原文位置、来源与限制。'))
    parts.append('<div class="filter"><input id="e-search" type="search" aria-label="搜索证据" placeholder="搜索编号、标题或结构"><select id="e-filter" aria-label="按方向筛选"><option value="">全部方向</option>'+''.join(f'<option value="{d["id"]}">{d["id"]} {esc(d["name"])}</option>' for d in dirs)+f'</select><button class="btn" id="e-reset">重置筛选</button><output id="e-count" aria-live="polite">{len(ev)} 个条目</output></div><div class="evidence-list">')
    for e in ev:
        meta=e['source_role']+' · '+('计入主样本' if e['in_sample'] else '未计入主样本')
        docs=' · '.join(f'<a href="{esc(d["url"])}" rel="noopener">{esc(d["number"])}</a>' for d in e.get('documents',[]))
        parts.append(f'<details class="evidence-item" id="e-{e["id"]}" data-routes="{esc(" ".join(e.get("directions",[])))}"><summary><strong>{e["id"]} {esc(e["title"])}</strong><span class="e-summary">{esc(e["summary"])}</span><span class="e-meta">{esc(meta)}</span></summary><div class="e-detail">{para(e.get("publication",""))}<p>{docs}</p><p><strong>原文位置：</strong>{esc(e["location"])}</p>{para(e["disclosure"])}<p><strong>判断边界：</strong>{esc(e["limitation"])}</p></div></details>')
    parts.append(f'</div><p class="empty" id="e-empty" {"hidden" if ev else ""}>没有匹配的证据，可更换关键词或重置筛选。</p></section>')
    parts.append(heading('next','已完成的补证与当前边界','先说明已经解决了什么，再说明哪份新资料会改变判断。'))
    parts.append('<ol class="worklog">'+''.join(f'<li><h3>{esc(n["question"])}</h3><p><strong>已完成：</strong>{esc(n["action"])}</p><p><strong>判断变化：</strong>{esc(n["finding"])}</p><p><strong>剩余未知：</strong>{esc(n["remaining"])}</p></li>' for n in data.get('worklog',[]))+'</ol>')
    parts.append('<p class="judgment">'+esc(data.get('decision_boundary',data['boundary']))+'</p>')
    if data.get('appendix') or data.get('references'):
        parts.append('<details class="appendix"><summary>检索记录、方法与完整边界</summary><div class="appendix-body">'+''.join(para(p) for p in data.get('appendix',[])))
        if data.get('references'):parts.append('<p><strong>补充来源与方法：</strong></p><ul>'+''.join(f'<li><a href="{esc(s["url"])}" rel="noopener">{esc(s["title"])}</a></li>' for s in data['references'])+'</ul>')
        parts.append('</div></details>')
    parts.append('</section><footer>研发罗盘 · 证据支撑的条件判断</footer></main>')
    template=(Path(__file__).resolve().parents[1]/'assets/report.html').read_text(encoding='utf-8')
    payload=json.dumps(data,ensure_ascii=False).replace('<','\\u003c').replace('\u2028','\\u2028').replace('\u2029','\\u2029')
    return template.replace('<title>研发罗盘</title>',f'<title>{esc(data["title"])}</title>').replace('<!-- REPORT_BODY -->',''.join(parts)).replace('__REPORT_DATA__',payload)

def write_report(data, output):
    result=render(data)
    output=Path(output);output.parent.mkdir(parents=True,exist_ok=True)
    temporary=None
    try:
        with tempfile.NamedTemporaryFile(mode='w',encoding='utf-8',dir=output.parent,suffix='.tmp',delete=False) as handle:
            temporary=Path(handle.name);handle.write(result)
        os.replace(temporary,output)
    finally:
        if temporary is not None and temporary.exists():temporary.unlink()

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('data',type=Path);parser.add_argument('--output',required=True,type=Path);args=parser.parse_args()
    try:
        write_report(json.loads(args.data.read_text(encoding='utf-8-sig')),args.output)
        print('Report generated:',args.output)
    except (ValueError,KeyError,TypeError,OSError) as error:parser.exit(1,'Report not generated: '+str(error)+'\n')
