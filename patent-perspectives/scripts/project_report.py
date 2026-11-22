"""Project sections in the two report front ends; teaching assets are never project data."""
import base64
import hashlib
import html
import json
import struct
from datetime import date
from pathlib import Path

ASSETS = Path(__file__).resolve().parents[1] / 'assets'
ROLES = {'management': '企业决策者', 'rd': '研发总监', 'ip': '专利总监'}
MODULES = {
    'management': '本次决策 业务目标与边界 机会与威胁 能力与缺口 进入障碍与权利 经营方案比较 投入与经济性 阶段与停止条件 证据与决策记录'.split(),
    'rd': '本次研发决定 范围与证据 技术拆解与路线 竞争与技术演进 同工况路线比较 专利约束与改进 能力与外部资源 验证与通过条件 阶段计划与复审'.split(),
    'ip': '本次专利决定 范围与检索 权利与辖区 权项逐特征对照 自有组合与业务 申请与保密布局 处置方案比较 预算期限与责任 验收监测与复核'.split(),
}
TRACKS = {'near': '近期预研', 'reserve': '中长期储备'}
STANDING = {'proposed': '建议', 'approved': '已有授权', 'pending': '待判断'}
FIELDS = {'reason': '保留理由', 'maturity': '证据成熟程度', 'gap': '尚缺的证据及影响', 'next_step': '下一步与验收内容',
          'resources': '负责人和资源', 'review': '复核时间或触发条件', 'gate': '继续、调整或暂停的条件',
          'promote': '转入近期预研的条件', 'close': '关闭条件'}
esc = html.escape


def words(row, *keys):
    if not isinstance(row, dict) or any(not isinstance(row.get(k), str) or not row[k].strip() for k in keys):
        raise ValueError('Project report needs non-empty text: ' + ', '.join(keys))


def items(row, key, required=False):
    values = row.get(key, [])
    if not isinstance(values, list) or (required and not values) or not all(isinstance(v, dict) for v in values):
        raise ValueError('Invalid project list: ' + key)
    return values


def references(row, allowed, required=False):
    ids = row.get('source_ids', [])
    if (not isinstance(ids, list) or (required and not ids) or
            any(not isinstance(i, str) or i not in allowed for i in ids) or len(set(ids)) != len(ids)):
        raise ValueError('Missing, duplicated or unknown project source')


def fields(section):
    return (('gap', 'next_step', 'resources', 'gate') if section['horizon'] == 'near' else
            ('reason', 'maturity', 'gap', 'next_step', 'resources', 'review', 'promote', 'close'))


def check(contract, evidence, quotes=None):
    project = contract.get('project_report')
    if not isinstance(project, dict):
        raise ValueError('project_report must be an object')
    if contract['version'] != 2:
        raise ValueError('Project reports require reader contract v2')
    words(project, 'context')
    docs = {}
    for doc in items(project, 'materials'):
        words(doc, 'id', 'title', 'origin', 'version', 'locator', 'observed_on', 'excerpt', 'limit')
        key = doc['id']
        if key in docs or key in evidence:
            raise ValueError('Project material collides with another source: ' + key)
        docs[key] = doc
        if 'figure' in doc:
            image = doc['figure']
            words(image, 'png_base64', 'sha256', 'caption')
            data = base64.b64decode(image['png_base64'], validate=True)
            if len(data)<33 or not data.startswith(b'\x89PNG\r\n\x1a\n') or data[12:16]!=b'IHDR' or hashlib.sha256(data).hexdigest() != image['sha256']:
                raise ValueError('Project figure bytes do not match the registered PNG')
            width,height=struct.unpack('>II',data[16:24])
            if not width or not height:
                raise ValueError('Invalid project image dimensions')
            if 'detail' in image:
                box=image['detail']
                if not isinstance(box,list) or len(box)!=4 or any(type(i) is not int for i in box):
                    raise ValueError('Expected detail [x,y,width,height] in original pixels')
                x,y,w,h=box
                if min(x,y)<0 or min(w,h)<=0 or x+w>width or y+h>height:
                    raise ValueError('Figure detail falls outside the original')

    allowed = set(evidence) | docs.keys()
    questions = {q['id']: q for q in contract['questions']}
    seen = set()
    for section in items(project, 'sections', True):
        words(section, 'role', 'horizon', 'question_id', 'decision', 'standing')
        role, track, num = section['role'], section['horizon'], section.get('module')
        if role not in ROLES or role not in contract['role_guides'] or track not in TRACKS or section['standing'] not in STANDING:
            raise ValueError('Unknown project role, horizon or decision status')
        if (track == 'near' and (type(num) is not int or not 1 <= num <= 9)) or (track == 'reserve' and num is not None):
            raise ValueError('Use a near module 1–9 or a reserve section without module number')
        key = role, track, num
        if key in seen or section['question_id'] not in questions:
            raise ValueError('Duplicate project module or unknown research question')
        seen.add(key)
        words(section, *fields(section))
        references(section, allowed)
        if section['standing'] == 'approved' and docs.get(section.get('approval_ref'), {}).get('kind') != 'authorization':
            raise ValueError('An approved action needs an identified project authorization record')
        for signal in items(section, 'signals'):
            words(signal, 'organization', 'document', 'time', 'finding', 'implication')
            references(signal, allowed, True)
        routes = items(section, 'routes')
        if routes and len(routes) < 2:
            raise ValueError('A comparison needs at least two routes')
        for route in routes:
            words(route, 'label', 'observation')
            references(route, allowed, True)
        pics = section.get('figures', [])
        if not isinstance(pics, list) or any(not isinstance(i,str) or i not in docs or 'figure' not in docs[i] for i in pics) or len(pics) != len(set(pics)):
            raise ValueError('Figure must refer to a registered project image')
        claim_rows = items(section, 'claims')
        if claim_rows:
            right = section.get('right')
            words(right, 'territory', 'version', 'status')
            if right['status'] not in ('unknown', 'observed'):
                raise ValueError('Identify the legal status as unknown or observed')
            references(right, allowed, right['status'] == 'observed')
            if right['status'] == 'observed':
                words(right, 'as_of', 'finding')
                date.fromisoformat(right['as_of'])
        for row in claim_rows:
            words(row, 'source_id', 'wording', 'need')
            src = row['source_id']
            if src not in allowed:
                raise ValueError('Unknown claim source')
            if src in docs and docs[src].get('kind') != 'claim':
                raise ValueError('Use the recorded claim text, not a product drawing')
            original = docs[src]['excerpt'] if src in docs else (quotes or {}).get(src)
            if original is not None and row['wording'] not in original:
                raise ValueError('Claim limitation must quote its source verbatim')
            for case in items(row, 'cases', True):
                words(case, 'label', 'observation', 'status')
                if case['status'] not in ('observed', 'pending'):
                    raise ValueError('Unknown feature observation status')
                references(case, allowed, case['status'] == 'observed')
            for obs in items(row, 'observations'):
                words(obs, 'stage', 'check')
    if not any(key[0] == contract['primary_role'] for key in seen):
        raise ValueError('Project sections must include the primary role')


def bind_questions(contract, connection, synthetic):
    if not contract.get('project_report') or synthetic:
        return
    if any(d['id'].upper().startswith('DEMO-') or d.get('synthetic') is True for d in contract['project_report'].get('materials', [])):
        raise ValueError('Teaching materials cannot enter a real project report')
    built_in = ASSETS.parent / 'references/report-templates/figures'
    submitted = {d['figure']['sha256'] for d in contract['project_report'].get('materials', []) if 'figure' in d}
    if submitted and any(hashlib.sha256(p.read_bytes()).hexdigest() in submitted for p in built_in.glob('*.png')):
        raise ValueError('A template drawing cannot be used as a real project original')
    for section in contract['project_report']['sections']:
        for row in section.get('claims', []):
            registered = connection.execute('SELECT data FROM evidence WHERE id=?', (row['source_id'],)).fetchone()
            if registered:
                locator = json.loads(registered[0]).get('locator', {})
                if not isinstance(locator, dict) or not (locator.get('claim_number') or 'claim' in str(locator.get('section','')).lower() or '权利要求' in str(locator.get('section',''))):
                    raise ValueError('A claim limitation needs evidence located in the claims')
    reviewed = {k: json.loads(v) for k, v in connection.execute('SELECT id,data FROM research_reviews')}
    questions = {q['id']: q for q in contract['questions']}
    for key in {s['question_id'] for s in contract['project_report']['sections']}:
        q = questions[key]
        q.pop('reviewed_limits', None)
        if q['status'] != 'answered':
            continue
        record = reviewed.get(key)
        if (not record or record['status'] != 'resolved' or record['review_result'] != 'pass' or
                record['answer'] != q['answer'] or set(record['evidence_ids']) != set(q['evidence_ids'])):
            raise ValueError('Project section must retain the reviewed research answer and its evidence: ' + key)
        # These are the actual approved conditions, even when the role summary is shorter.
        q['reviewed_limits'] = list(dict.fromkeys(x for x in [record.get('conditions'), *record.get('limitations', [])] if x))



def title(s):
    if s['horizon'] == 'reserve':
        return '中长期储备'
    n = s['module']
    return f'{n:02d} ' + MODULES[s['role']][n-1]


def render(contract, synthetic=False):
    project = contract['project_report']
    docs = {d['id']: d for d in project.get('materials', [])}
    questions = {q['id']: q for q in contract['questions']}
    def links(ids):
        parts = []
        for key in dict.fromkeys(ids):
            attr = 'data-project-source' if key in docs else 'data-reader-source'
            parts.append(f'<button type="button" {attr}="{esc(key)}">原文 {esc(key)}</button>')
        return '<div class="project-links">' + ''.join(parts) + '</div>' if parts else ''

    def block(label, text):
        return '<div><strong>' + esc(label) + '</strong><p>' + esc(text) + '</p></div>'

    roles = {s['role'] for s in project['sections']}
    start = contract['primary_role']
    buf = [f'<section id="project-report" data-initial-role="{start}" aria-label="项目评审与储备">',
           '<div class="project-context">' + ('模拟案例 · ' if synthetic else '') + esc(project['context']) + '</div>',
           '<div class="project-controls"><div role="group" aria-label="报告读者">']
    for role, label in ROLES.items():
        if role in roles:
            buf.append(f'<button type="button" data-project-role="{role}" aria-pressed="{str(role == start).lower()}">{label}</button>')
    buf.append('</div><label>当前模块 <select id="project-module"></select></label></div>')
    for s in project['sections']:
        role, track = s['role'], s['horizon']
        num = str(s.get('module') or 'reserve')
        q = questions[s['question_id']]
        buf += [f'<article class="project-module" data-project-key="{role}/{num}" data-track="{track}" data-title="{esc(title(s))}" hidden>',
                '<p class="project-meta">' + esc(ROLES[role] + ' · ' + TRACKS[track]) + '</p>',
                '<h2>' + esc(q['question']) + '</h2>',
                '<div class="project-answer"><strong>本节决定 · ' + STANDING[s['standing']] + '</strong><p>' + esc(s['decision']) + '</p>',
                '<p class="project-boundary">' + esc(q['boundary']) + '</p></div>']
        if q.get('reviewed_limits'):
            buf.append(block('研究结论成立的条件',' '.join(q['reviewed_limits'])))
        if s['standing'] == 'approved':
            buf.append(links([s['approval_ref']]))
        buf += [block({'insufficient':'目前仍待核实','answered':'研究发现','scope_changed':'范围调整后的判断'}[q['status']], q['answer']),
                links(q.get('evidence_ids', []) + s.get('source_ids', []))]
        for signal in s.get('signals', []):
            buf += [block('竞争动向', signal['organization'] + ' · ' + signal['time'] + ' · ' + signal['document']),
                    block('观察到什么',signal['finding']), block('影响哪项选择',signal['implication']),links(signal['source_ids'])]
        if s.get('figures'):
            buf.append('<div class="project-figures">')
            for key in s['figures']:
                d = docs[key]; pic = d['figure']
                detail=''
                if 'detail' in pic:
                    x,y,w,h=pic['detail']
                    full_width=struct.unpack('>I',base64.b64decode(pic['png_base64'][:32])[16:20])[0]
                    detail=(f' data-cx="{x+w/2}" data-cy="{y+h/2}" style="--crop-ratio:{w}/{h};'
                            f'--crop-width:{full_width*100/w:.5f}%;--crop-x:{-x*100/w:.5f}%;--crop-y:{-y*100/h:.5f}%"')
                buf += [f'<figure><figcaption>{esc(d["title"])}</figcaption><button type="button" class="project-zoom"{detail} aria-label="放大原图：{esc(d["title"])}"><img alt="{esc(pic["caption"])}" src="data:image/png;base64,{pic["png_base64"]}"><span>放大原图</span></button>',
                        '<p>'+esc(pic['caption'])+'</p>'+links([key])+'</figure>']
            buf.append('</div>')
        for route in s.get('routes', []):
            buf += [block(route['label'],route['observation']),links(route['source_ids'])]
        if s.get('claims'):
            right=s['right']
            status=('当前法律状态未核实' if right['status']=='unknown' else right['as_of']+' 观察：'+right['finding'])
            buf+= [block('权项版本与法域',right['territory']+' · '+right['version']+' · '+status),links(right.get('source_ids',[]))]
        for row in s.get('claims', []):
            buf += ['<section class="project-claim"><h3>'+esc(row['wording'])+'</h3>',links([row['source_id']]),'<div class="project-cases">']
            for case in row['cases']:
                buf += ['<div>'+block(case['label'] + (' · 已观察' if case['status']=='observed' else ' · 待核'),case['observation']),links(case.get('source_ids',[]))+'</div>']
            buf += ['</div>',block('必须取得的证据或复核',row['need'])]
            for obs in row.get('observations', []):
                buf.append(block(obs['stage'],obs['check']))
            buf.append('</section>')
        buf.extend(block(FIELDS[k],s[k]) for k in fields(s))
        buf.append('</article>')
    buf.append('<details class="project-search"><summary>搜索项目章节</summary><label>搜索原文与取证要求 <input type="search"></label><div role="status"></div></details>')
    for d in docs.values():
        buf.append('<details class="project-material" data-project-material="'+esc(d['id'])+'"><summary>'+esc(d['id']+' · '+d['title'])+'</summary>'
                   +block('来源与位置',' · '.join(d[k] for k in ('origin','version','locator','observed_on')))
                   +block('原文或图示记录',d['excerpt'])+block('使用边界',d['limit'])+'</details>')
    buf.append('<dialog class="project-dialog"><button type="button" class="project-close">关闭</button><h3></h3><div tabindex="0"><img alt=""></div><p></p></dialog></section>')
    return ''.join(buf)


def insert(page, contract, before, synthetic=False):
    if not contract.get('project_report'):
        return page
    if any(page.count(marker) != 1 for marker in (before, '</head>', '</body>')):
        raise ValueError('Project report entry not found in report shell')
    return (page.replace(before, render(contract, synthetic)+before,1)
            .replace('</head>', '<style>'+(ASSETS/'project-report.css').read_text('utf8')+'</style></head>')
            .replace('</body>', '<script>'+(ASSETS/'project-report.js').read_text('utf8')+'</script></body>'))

