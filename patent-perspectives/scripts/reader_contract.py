"""Portable report-reading contract. Checks records, not semantic truth or consent itself."""
import html
import re
from datetime import date
import importlib.util
from pathlib import Path

_project_spec = importlib.util.spec_from_file_location('prism_project_report', Path(__file__).with_name('project_report.py'))
project_report = importlib.util.module_from_spec(_project_spec)
_project_spec.loader.exec_module(project_report)

ROLES = {'management': '管理导读', 'rd': '研发导读', 'ip': 'IP 核查'}
KINDS = {'emerging': '新兴技术', 'lifecycle': '发展阶段', 'gap': '技术空白', 'transfer': '跨领域匹配'}


def text(obj, key):
    value = obj.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError('Reader contract needs text: ' + key)
    return value


def require_contract_version(container):
    version = container.get("report_contract_version")
    contract = container.get("reader_contract")
    if version is not None and (version not in (1, 2) or not isinstance(contract, dict) or contract.get("version") != version):
        raise ValueError("Report and reader contract versions must match")


def publication_version(publication, version):
    # Describe these known document kinds. Do not infer present legal status or
    # generalize kind codes to other offices.
    for pattern, label in (
        (r"CN[0-9]+A|US[0-9]+A[1-9]", "发明申请公开"),
        (r"CN[0-9]+U", "实用新型授权公告"),
        (r"CN[0-9]+B|US[0-9]+B[12]", "发明授权文本"),
    ):
        if re.fullmatch(pattern, publication):
            return label + "（" + re.search(r"[A-Z][0-9]*$", publication).group() + "）"
    return version


def validate_reading_context(contract, evidence_ids, evidence_owners):
    context = contract.get("reading_context")
    if not isinstance(context, dict):
        raise ValueError("Set the readers’ starting knowledge and shared introduction")
    for key in ("reader_background", "scene_title", "scene"):
        text(context, key)
    date.fromisoformat(text(contract, "reviewed_on"))
    terms = context.get("terms", [])
    if not isinstance(terms, list):
        raise ValueError("Reader terms must be a list")
    for entry in terms:
        for key in ("name", "meaning"):
            text(entry, key)
    walkthroughs = context.get("walkthroughs", [])
    if not isinstance(walkthroughs, list):
        raise ValueError("Mechanism explanations must be a list")
    ids = set()
    allowed = set(evidence_ids)
    for section in walkthroughs:
        application_id = text(section, "application_id")
        if application_id in ids:
            raise ValueError("Write one shared explanation per analyzed application")
        ids.add(application_id)
        for key in ("title", "summary", "boundary"):
            text(section, key)
        blocks = section.get("blocks")
        validate_blocks(blocks)
        if not blocks:
            raise ValueError("A mechanism explanation needs at least one source-backed block")
        for block in blocks:
            if not isinstance(block, dict):
                raise ValueError("A mechanism block needs its own source and condition")
            text(block, "heading")
            anchors = block.get("evidence_ids")
            if not isinstance(anchors, list) or not anchors or any(not isinstance(anchor, str) or anchor not in allowed for anchor in anchors):
                raise ValueError("Mechanism block needs valid source anchors")
            if evidence_owners is not None and any(evidence_owners.get(anchor) != application_id for anchor in anchors):
                raise ValueError("Mechanism source belongs to another application")


def validate(contract, evidence_ids, *, evidence_owners=None, source_quotes=None):
    if not isinstance(contract, dict) or contract.get('version') not in (1, 2):
        raise ValueError('Unsupported reader contract version')
    if contract['version'] == 2:
        validate_reading_context(contract, evidence_ids, evidence_owners)
    for key in ('purpose', 'scope', 'common_boundary', 'as_of'):
        text(contract, key)
    if contract.get('primary_role') not in ROLES:
        raise ValueError('Unknown primary reader role')
    market = contract.get('market_search', {})
    if market.get('permission') not in ('not_requested', 'declined', 'approved'):
        raise ValueError('Record the user market-search decision')
    if not isinstance(market.get('performed'), bool):
        raise ValueError('Record whether market search was performed')
    if market['performed'] and market['permission'] != 'approved':
        raise ValueError('Market search requires user confirmation before execution')
    if market['permission'] == 'approved':
        text(market, 'confirmation')
        for key in ('question', 'objects', 'regions', 'period', 'sources', 'depth'):
            text(market.get('scope', {}), key)
    text(market, 'statement')
    allowed = set(evidence_ids)

    def refs(row):
        ids = row.get('evidence_ids', [])
        if not isinstance(ids, list) or any(not isinstance(x, str) or x not in allowed for x in ids):
            raise ValueError('Reader contract has unknown evidence')
        if len(ids) != len(set(ids)):
            raise ValueError('Reader contract repeats evidence IDs')

    guides = contract.get('role_guides', {})
    if contract['primary_role'] not in guides or not set(guides) <= set(ROLES):
        raise ValueError('Reader guide does not cover the primary role')
    for guide in guides.values():
        for key in ('question', 'answer', 'focus'):
            text(guide, key)
        refs(guide)
    questions = contract.get('questions')
    if not isinstance(questions, list) or not questions:
        raise ValueError('Reader contract needs the agreed research questions')
    ids = []
    for row in questions:
        for key in ('id', 'question', 'answer', 'boundary'):
            text(row, key)
        ids.append(row['id'])
        if row.get('status') not in ('answered', 'insufficient', 'scope_changed'):
            raise ValueError('Unknown research-question outcome')
        refs(row)
        if row['status'] == 'answered' and not row.get('evidence_ids'):
            raise ValueError('Answered research question needs evidence')
        if row['status'] == 'scope_changed':
            text(row, 'user_confirmation')
    if len(ids) != len(set(ids)):
        raise ValueError('Research questions must keep unique identities')
    for item in contract.get('assessments', []):
        if item.get('kind') not in KINDS or item.get('status') not in ('supported', 'candidate', 'undetermined'):
            raise ValueError('Unknown technology assessment')
        for key in ('subject', 'conclusion', 'reasoning', 'boundary', 'review_trigger'):
            text(item, key)
        refs(item)
        if item['status'] != 'undetermined' and not item.get('evidence_ids'):
            raise ValueError('Technology assessment needs source evidence')
        if item['kind'] in ('emerging', 'lifecycle') and item['status'] == 'supported':
            text(item, 'comparison_basis')
            text(item, 'alternative_explanation')
        if item['kind'] == 'lifecycle' and item['status'] == 'supported':
            external = item.get('external_evidence', [])
            if not external or (not market['performed'] and not market.get('provided_materials')):
                raise ValueError('Lifecycle stage needs acquired or supplied external evidence; otherwise keep undetermined')
    for item in contract.get('decision_summary', []):
        for key in ('action', 'basis', 'uncertainty', 'if_reversed'):
            text(item, key)
        refs(item)
    if 'project_report' in contract:
        project_report.check(contract, allowed, source_quotes)


def validate_blocks(blocks):
    if not isinstance(blocks, list):
        raise ValueError('Narrative blocks must be a list')
    for block in blocks:
        if isinstance(block, str):
            if not block.strip(): raise ValueError('Empty narrative paragraph')
            continue
        if not isinstance(block, dict): raise ValueError('Invalid narrative block')
        text(block, 'text')
        if 'heading' in block: text(block, 'heading')
        if 'steps' in block and (not isinstance(block['steps'], list) or not block['steps'] or
                any(not isinstance(s, str) or not s.strip() for s in block['steps'])):
            raise ValueError('Narrative steps must be substantive strings')


def blocks_html(blocks):
    validate_blocks(blocks)
    esc = lambda value: html.escape(str(value), quote=True)
    result = ''
    for block in blocks:
        if isinstance(block, str):
            result += '<p>' + esc(block) + '</p>'
            continue
        if block.get('heading'): result += '<h4>' + esc(block['heading']) + '</h4>'
        result += '<p>' + esc(block['text']) + '</p>'
        if block.get('steps'):
            result += '<ol class="mechanism-steps">' + ''.join('<li>' + esc(s) + '</li>' for s in block['steps']) + '</ol>'
    return result


def render(contract, part='intro', evidence_link=None):
    esc = lambda value: html.escape(str(value), quote=True)
    def refs(item):
        links = '<div class="reader-sources">' + ''.join(
            evidence_link(eid) if evidence_link else '<button type="button" data-reader-source="' + esc(eid) + '">原文 ' + esc(eid) + '</button>'
            for eid in item.get('evidence_ids', [])) + '</div>'
        if len(item.get('evidence_ids', [])) > 3:
            return '<details class="reader-source-list"><summary>查看原文依据（' + str(len(item['evidence_ids'])) + '处）</summary>' + links + '</details>'
        return links
    if part == 'intro':
        result = '<section class="reader-brief" id="reader-brief">'
        context = contract.get('reading_context')
        if context:
            result += '<h2>' + esc(context['scene_title']) + '</h2><p>' + esc(context['scene']) + '</p>'
        else:
            result += '<h2>从本次问题开始阅读</h2><p>' + esc(contract['purpose']) + '</p>'
        result += '<p class="reader-boundary">' + esc(contract['scope']) + ' ' + esc(contract['common_boundary']) + '</p>'
        result += '<p class="reader-market">' + esc(contract['market_search']['statement']) + '</p><div class="reader-role-tabs" role="group" aria-label="阅读导读">'
        for role in contract['role_guides']:
            result += '<button type="button" data-guide-role="' + role + '" aria-pressed="' + str(role == contract['primary_role']).lower() + '">' + ROLES[role] + '</button>'
        result += '</div>'
        for role, guide in contract['role_guides'].items():
            result += '<div class="reader-guide" data-reader-guide="' + role + '"' + ('' if role == contract['primary_role'] else ' hidden') + '><h3>' + esc(guide['question']) + '</h3><p>' + esc(guide['answer']) + '</p><p class="reader-focus">' + esc(guide['focus']) + '</p>' + refs(guide) + '</div>'
        if context and context.get('terms'):
            result += '<details><summary>读报告常用的几个词</summary><dl>'
            for term in context['terms']:
                result += '<dt><strong>' + esc(term['name']) + '</strong></dt><dd>' + esc(term['meaning']) + '</dd>'
            result += '</dl></details>'
        return result + '<a href="#research-answers">查看研究问题与判断边界</a></section>'
    if part == 'mechanisms':
        walkthroughs = contract.get('reading_context', {}).get('walkthroughs', [])
        if not walkthroughs:
            return ''
        result = '<section class="reader-answers"><h2>结构与工作过程</h2>'
        for section in walkthroughs:
            result += '<article><h3>' + esc(section['title']) + '</h3><p>' + esc(section['summary']) + '</p>'
            for block in section['blocks']:
                result += blocks_html([block]) + refs(block)
            result += '<p class="reader-boundary">' + esc(section['boundary']) + '</p></article>'
        return result + '</section>'
    result = '<section class="reader-answers" id="research-answers"><h2>本次研究回答了什么</h2>'
    states = {'answered': '已有依据的回答', 'insufficient': '仍不能判断', 'scope_changed': '经确认调整范围'}
    for row in contract['questions']:
        result += '<article><h3>' + esc(row['question']) + '</h3><p class="reader-state">' + states[row['status']] + '</p><p>' + esc(row['answer']) + '</p><p class="reader-boundary">' + esc(row['boundary']) + '</p>' + refs(row) + '</article>'
    for item in contract.get('assessments', []):
        result += '<article class="technology-assessment" data-assessment="' + item['kind'] + '"><h3>' + KINDS[item['kind']] + '：' + esc(item['subject']) + '</h3><p>' + esc(item['conclusion']) + '</p><p>' + esc(item['reasoning']) + '</p><p class="reader-boundary">' + esc(item['boundary']) + '</p><p>回查条件：' + esc(item['review_trigger']) + '</p>' + refs(item) + '</article>'
    if contract.get('decision_summary'):
        result += '<h3>当前建议及改变判断的条件</h3>'
        for item in contract['decision_summary']:
            result += '<article><p><strong>' + esc(item['action']) + '</strong></p><p>依据：' + esc(item['basis']) + '</p><p>待核：' + esc(item['uncertainty']) + '</p><p>若结果相反：' + esc(item['if_reversed']) + '</p>' + refs(item) + '</article>'
    date_label = '报告复核日期' if contract.get('reviewed_on') else '判断资料截止'
    result += '<p class="reader-date">' + date_label + ' ' + esc(contract.get('reviewed_on', contract['as_of'])) + '。新原文、需求或测试资料到来后，同步回查导读、正文与依据。</p></section>'
    return result


STYLE = '''
.reader-brief,.reader-answers{margin:24px 0;padding:24px;background:#f5f9ff;border:1px solid #cddff0;border-radius:16px;color:#193449;line-height:1.8;overflow-wrap:anywhere}
.reader-source-list{margin:12px 0}.reader-source-list summary{cursor:pointer;color:#154c76}.reader-source-list[open] summary{margin-bottom:10px}
.reader-brief h2,.reader-answers h2{margin:0 0 12px}.reader-brief h3,.reader-answers h3{font-size:1.12rem;margin:18px 0 8px}
.reader-boundary{border-left:3px solid #7ca3bd;padding:8px 12px;background:#fff}.reader-market,.reader-state,.reader-date{font-size:.9rem;color:#465e70}
.reader-role-tabs{display:flex;flex-wrap:wrap;gap:8px;margin:12px 0}.reader-role-tabs button,.reader-sources button{padding:6px 12px;border:1px solid #9fbdd4;border-radius:8px;background:white;color:#154c76;cursor:pointer}
.reader-role-tabs button[aria-pressed=true]{background:#e0edff;border-color:#275a8b}.reader-sources{display:flex;flex-wrap:wrap;gap:8px;margin:10px 0;font-size:.85rem}
.reader-answers article+article{border-top:1px solid #d9e4ed;padding-top:12px;margin-top:20px}.mechanism-steps{padding-left:1.5em;line-height:1.9}.mechanism-steps li{margin:8px 0}
@media(max-width:600px){.reader-brief,.reader-answers{padding:16px}.reader-role-tabs button{flex:1}}
@media print{.reader-guide[hidden]{display:block!important}.reader-role-tabs{display:none}.reader-answers article{break-inside:avoid}}
'''

SCRIPT = '''
window.PP_READER_GUIDE={show(role){document.querySelectorAll('[data-reader-guide]').forEach(n=>n.hidden=n.dataset.readerGuide!==role);document.querySelectorAll('[data-guide-role]').forEach(n=>n.setAttribute('aria-pressed',String(n.dataset.guideRole===role)));}};
document.addEventListener('click',e=>{const b=e.target.closest('[data-guide-role]');if(b){window.PP_READER_GUIDE.show(b.dataset.guideRole);document.dispatchEvent(new CustomEvent('reader-role',{detail:b.dataset.guideRole}));}const s=e.target.closest('[data-reader-source]');if(s)document.dispatchEvent(new CustomEvent('reader-source',{detail:s.dataset.readerSource}));});
'''
