"""Explicit official national-register adapters with original-source validation.

prepare(c,p,e) matches registration_members.prepare. No SQL writes, network,
family inference, national claims creation, or automatic source substitution.
Requires pypdf/Pillow/Poppler for the PDF evidence path.
"""
from __future__ import annotations
import datetime as dt
import hashlib
import importlib.util
import io
import json
import re
import shutil
import subprocess
import tempfile
from functools import lru_cache
from pathlib import Path
from urllib.parse import urlsplit
import xml.etree.ElementTree as ET

RELATION = 'national_register_member_of_european_application'
ADAPTERS = {'dpma_patentblatt_same_notice_v1', 'seeip_ep_register_v1'}
_REGISTRATION = None

def registration():
    global _REGISTRATION
    if _REGISTRATION is None:
        path = Path(__file__).resolve().parent / 'registration_members.py'
        spec = importlib.util.spec_from_file_location('explicit_registration_common', path)
        _REGISTRATION = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(_REGISTRATION)
    return _REGISTRATION

def sha(raw):
    return hashlib.sha256(raw).hexdigest()

def compact(value):
    return re.sub(r'\s', '', value)

def valid_date(value, e, label):
    e.require(isinstance(value, str), label + ' date required')
    try:
        parsed = dt.date.fromisoformat(value)
    except ValueError as exc:
        raise e.ValidationError(label + ' is not an ISO calendar date') from exc
    e.require(parsed.isoformat() == value, label + ' must preserve an exact ISO date')
    return value

def source(c, payload, host, media, e):
    raw, proof = registration().artifact(c, payload, host, media, e)
    u = urlsplit(payload['source_url'])
    e.require(not u.query and not u.fragment, 'Registration endpoint must not have an unvalidated query or fragment')
    try:
        acquired = dt.datetime.fromisoformat(payload['acquired_at'].replace('Z', '+00:00'))
    except (ValueError, TypeError) as exc:
        raise e.ValidationError('Invalid actual acquisition timestamp') from exc
    e.require(acquired.tzinfo is not None, 'Actual acquisition timestamp needs timezone')
    return raw, proof

def local_artifact(c, item, e):
    e.require(isinstance(item, dict), 'Local evidence item required')
    runroot = registration().root(c, e)
    name = item.get('artifact')
    e.require(isinstance(name, str) and not Path(name).is_absolute(), 'Local evidence must be run-relative')
    p = (runroot / name).resolve()
    e.require(p.is_relative_to(runroot) and p.is_file(), 'Local proof is outside evidence root or missing')
    raw = p.read_bytes()
    e.require(sha(raw) == item.get('sha256'), 'Local proof hash mismatch')
    return p, raw

@lru_cache(maxsize=4)
def pdf_reader(raw):
    from pypdf import PdfReader
    # Parse the PDF page tree, not the text of its hundreds of unused pages.
    # The cache key is original immutable bytes, never solely a filename.
    return PdfReader(io.BytesIO(raw), strict=True)

@lru_cache(maxsize=24)
def selected_page_text(raw, page):
    # Only this selected page is extracted; cache binds bytes plus page number.
    return pdf_reader(raw).pages[page-1].extract_text() or ''

def page_text(raw, page, e):
    e.require(type(page) is int and 1 <= page <= len(pdf_reader(raw).pages), 'Physical PDF page outside original file')
    return selected_page_text(raw, page)

@lru_cache(maxsize=24)
def rendered_png(raw, page):
    exe = shutil.which('pdftoppm')
    if exe is None:
        raise RuntimeError('Poppler pdftoppm is needed to verify actual page pixels')
    with tempfile.TemporaryDirectory(prefix='official-registration-') as td:
        pdf = Path(td) / 'source.pdf'
        pdf.write_bytes(raw)
        out = Path(td) / 'page'
        subprocess.run([exe, '-f', str(page), '-l', str(page), '-r', '300', '-png', '-singlefile', str(pdf), str(out)], check=True, capture_output=True)
        return out.with_suffix('.png').read_bytes()

def png_proofs(c, rs, raw, required_pages, e):
    from PIL import Image
    images = rs.get('reviewed_renderings')
    e.require(isinstance(images, list) and len(images) == len(required_pages), 'Complete cover/notice/index renderings required')
    e.require({x.get('pdf_page') for x in images} == set(required_pages), 'Rendered physical page coverage differs')
    renders = {}
    for item in images:
        page = item['pdf_page']
        page_text(raw, page, e)
        e.require(item.get('pdf_sha256') == sha(raw) and item.get('dpi') == 300, 'Rendering is not bound to this original PDF at 300 dpi')
        e.require(item.get('visually_reviewed') is True, 'Actual visual review required')
        _, png = local_artifact(c, item, e)
        actual = rendered_png(raw, page)
        # Compare pixels, not PNG encoder metadata or compression version.
        with Image.open(io.BytesIO(png)) as declared, Image.open(io.BytesIO(actual)) as rerendered:
            e.require(declared.size == rerendered.size and declared.convert('RGB').tobytes() == rerendered.convert('RGB').tobytes(), 'Saved page pixels differ from a fresh original-PDF rendering')
        renders[page] = (item, png)
    crops = rs.get('identity_crops')
    e.require(isinstance(crops, list) and {x.get('pdf_page') for x in crops} == set(required_pages)-{1} and len(crops)==2, 'Notice and index identity crops required')
    for crop in crops:
        _, rawcrop = local_artifact(c, crop, e)
        page = crop['pdf_page']
        render, png = renders[page]
        box = crop.get('bbox_pixels')
        e.require(crop.get('rendering_sha256') == render['sha256'] and crop.get('visually_reviewed') is True, 'Crop must bind reviewed page rendering')
        e.require(isinstance(box, list) and len(box)==4 and all(type(n) is int for n in box), 'Exact integer pixel crop box required')
        with Image.open(io.BytesIO(png)) as im, Image.open(io.BytesIO(rawcrop)) as actualcrop:
            e.require(0 <= box[0] < box[2] <= im.width and 0 <= box[1] < box[3] <= im.height, 'Identity crop outside page pixels')
            expected = im.crop(tuple(box)).convert('RGB')
            e.require(expected.size == actualcrop.size and expected.tobytes() == actualcrop.convert('RGB').tobytes(), 'Identity crop pixels do not match exact page box')
    return {'reviewed_renderings': images, 'identity_crops': crops, 'fresh_original_pdf_pixel_comparison': True}

def dpma(c, p, ma, e):
    rs = p['official_register']
    raw, proof = source(c, rs, 'register.dpma.de', {'application/pdf'}, e)
    path = urlsplit(rs['source_url']).path
    match = re.fullmatch(r'/DPMAregister/blattdownload/pat\.pdfdownload/5/Patentblatt_Nr\._(\d+)_vom_(\d{2})\.(\d{2})\.(\d{4})-Teil_5\.pdf', path)
    e.require(match is not None, 'Only the official Patentblatt Part 5 publication endpoint is supported')
    issue, day, month, year = match.groups()
    publication_date = valid_date(f'{year}-{month}-{day}', e, 'Official gazette')
    e.require(rs.get('gazette') == {'year':int(year), 'issue':int(issue), 'date':publication_date, 'section':5}, 'Declared gazette issue/date differs from official URL')
    e.require(raw.startswith(b'%PDF-') and b'%%EOF' in raw[-2048:], 'Complete original official PDF required')
    page_count = len(pdf_reader(raw).pages)
    notice = rs.get('notice', {})
    index = rs.get('index', {})
    nt = page_text(raw, notice.get('pdf_page'), e)
    it = page_text(raw, index.get('pdf_page'), e)
    stamp = f'Patentblatt 146. Jhrg. Heft {int(issue)} vom {day}.{month}.{year}'
    # Format-version gate: 2026/146. Jhrg., not an unbounded layout heuristic.
    e.require(year == '2026' and stamp in page_text(raw, 1, e) and stamp in nt and stamp in it, 'Official gazette year/volume/date/page headings differ')
    e.require('Erteilte europäische Patente' in nt and 'Hinweise auf DE-EP' in it, 'Wrong original gazette section')
    for meta, text in ((notice, nt), (index, it)):
        e.require(re.search(r'\n'+re.escape(str(meta.get('printed_page')))+r'\s*$', text) is not None, 'Printed page locator differs from original page footer')
    headings = list(re.finditer(r'^\(97\) EP ([0-9 ]+)(?:\*)?\s*$', nt, re.M))
    epn = rs.get('fields', {}).get('EPN')
    found = [(i, h) for i,h in enumerate(headings) if compact(h.group(1)) == epn]
    e.require(len(found) == 1, 'Exact EP notice header missing or ambiguous on declared physical page')
    i, start = found[0]
    end = headings[i+1].start() if i+1 < len(headings) else nt.index('Patentblatt 146.')
    block = nt[start.start():end]
    e.require(notice.get('block_text_sha256') == sha(block.encode('utf8')), 'Exact same-notice text block hash differs')
    patterns = {'DAKZ':r'^\(21\) Akz: (.+)$', 'EAKZ':r'^\(96\) EP-Akz: (.+)$', 'EP_PT':r'^\(45\) EP-PT (.+)$'}
    values = {'EPN':epn}
    locators = {'EPN':{'pdf_page':notice['pdf_page'],'printed_page':notice['printed_page'],'quote':start.group(0).strip()}}
    for field, pattern in patterns.items():
        hits = list(re.finditer(pattern, block, re.M))
        e.require(len(hits)==1, 'Same-notice '+field+' missing or ambiguous')
        values[field] = hits[0].group(1).strip()
        locators[field] = {'pdf_page':notice['pdf_page'], 'printed_page':notice['printed_page'], 'quote':hits[0].group(0).strip(), 'block_char_start':hits[0].start(), 'block_char_end':hits[0].end()}
    e.require(rs.get('fields') == values, 'Declared fields differ from actual same-notice official fields')
    dakz, eakz = compact(values['DAKZ']), compact(values['EAKZ'])
    e.require(re.fullmatch(r'60\d{10}\.\d', dakz) and re.fullmatch(r'\d{8}\.\d', eakz) and re.fullmatch(r'\d{7}', epn or ''), 'Unsupported exact official file-number syntax')
    e.require(ma['application_number'] == 'DE'+dakz.split('.')[0], 'Official DAKZ differs from retained national application')
    rows = list(re.finditer(r'^'+re.escape(eakz)+r' '+re.escape(epn)+r'\n([^\n]+)', it, re.M))
    e.require(len(rows)==1 and rows[0].group(1).startswith(values['DAKZ']+' '), 'Original DE-EP index does not independently pair the same EAKZ/EPN/DAKZ')
    e.require(index.get('quote') == rows[0].group(0), 'Declared exact DE-EP index quote differs')
    pixels = png_proofs(c, rs, raw, [1, notice['pdf_page'], index['pdf_page']], e)
    proof.update({'fields':values, 'locators':locators, 'gazette':rs['gazette'], 'notice':notice, 'index':index, 'original_pdf_page_count':page_count, 'text_extraction_physical_pages':[1,notice['pdf_page'],index['pdf_page']], **pixels})
    return proof, eakz, epn, dt.datetime.strptime(values['EP_PT'], '%d.%m.%Y').strftime('%Y%m%d'), 'DE'

def seeip(c, p, ma, e):
    rs = p['official_register']
    raw, proof = source(c, rs, 'seeip.patentamt.at', {'application/json'}, e)
    path = urlsplit(rs['source_url']).path
    match = re.fullmatch(r'/api/data/patent/detail/([A-F0-9]{8}(?:-[A-F0-9]{4}){3}-[A-F0-9]{12})/EuropeanPatent', path)
    e.require(match is not None, 'Only the exact official seeip EuropeanPatent detail endpoint is supported')
    payload = json.loads(raw)
    e.require(isinstance(payload, dict) and set(payload)=={'data'} and isinstance(payload['data'], dict), 'Unexpected seeip detail JSON schema')
    data = payload['data']
    fields = {k:data.get(k) for k in ('id','protectionType','eNo','applicationNo','publicationNo','applicationDate','publicationDate','registrationDate','atPublicationDate','registerEntryDate')}
    e.require(rs.get('fields')==fields and all(v is not None for v in fields.values()), 'Declared seeip fields missing or differ from original JSON')
    e.require(fields['id']==match[1] and fields['protectionType']=='EuropeanPatent', 'Official endpoint and same-record ID/type differ')
    e.require(re.fullmatch(r'\d{7}', fields['eNo']) and re.fullmatch(r'20\d{8}',fields['applicationNo']) and re.fullmatch(r'\d{7}',fields['publicationNo']), 'Unexpected seeip number syntax')
    e.require(ma['application_number']=='AT'+fields['applicationNo']+'T', 'Official Austrian application differs from retained national record')
    e.require(p['member_publication_ids']==['AT'+fields['eNo']+'T'], 'Official eNo differs from retained AT provider publication identity')
    for key in ('applicationDate','publicationDate','registrationDate','atPublicationDate','registerEntryDate'):
        valid_date(fields[key], e, 'seeip '+key)
    e.require(fields['registrationDate']==fields['publicationDate']==fields['registerEntryDate'], 'Unsupported seeip registration/publication date relationship')
    e.require(isinstance(data.get('epPublicationDates'), list) and sum(x.get('kindCode')=='B1' and x.get('publicationDate')==fields['publicationDate'] for x in data['epPublicationDates'])==1, 'Same-record EP B1 date missing or ambiguous')
    search = p.get('official_search')
    sr, sp = source(c, search, 'seeip.patentamt.at', {'application/json'}, e)
    e.require(urlsplit(search['source_url']).path=='/api/data/patent', 'Wrong official seeip search endpoint')
    request = {'searchCriteria':{'eNumbers':[fields['eNo']]},'pageIndex':0,'pageSize':20}
    e.require(search.get('method')=='POST' and search.get('request_body')==request, 'Official eNumber query must be exact and retained')
    receipt_path = registration().root(c,e)/search['receipt']['artifact']
    receipt = json.loads(receipt_path.read_text(encoding='utf-8-sig'))
    for key in search['receipt']['record_path']:
        receipt = receipt[key]
    e.require(receipt.get('method')=='POST' and receipt.get('request_body')==request, 'Actual acquisition receipt does not bind the eNumber query body')
    results = json.loads(sr).get('data', {})
    content = results.get('content')
    e.require(isinstance(content,list) and len(content)==1 and results.get('numberOfElements')==1 and results.get('first') is True and results.get('last') is True and results.get('number')==0, 'eNumber query is not one exact complete record')
    e.require(all(content[0].get(k)==fields[k] for k in ('id','applicationNo','publicationNo','protectionType')), 'Search result and exact national detail record differ')
    proof.update({'fields':fields, 'locators':{k:{'json_pointer':'/data/'+k,'value':v} for k,v in fields.items()}, 'official_search':{**sp,'method':'POST','request_body':request,'same_record_id':fields['id']}, 'retained_status_observation':{k:data.get(k) for k in ('status','statusCode','deletionCode','deletionDate','deletionDoneDate','aPageEntries','aPageHistoryEntries')}})
    # seeip exposes the ten-digit application number, while B210 retains the
    # eight-digit EP number plus its check digit. The exact XML supplies the
    # check digit; no check digit or national publication is invented.
    return proof, fields['applicationNo'][2:], fields['publicationNo'], fields['publicationDate'].replace('-',''), 'AT'

def canonical(c, p, ta, eakz, epn, date, jurisdiction, e):
    es = p['canonical_filing_evidence']
    xml, proof = source(c, es, 'data.epo.org', {'application/xml','text/xml'}, e)
    e.require(b'<!ENTITY' not in xml.upper(), 'Custom XML entities are not allowed')
    declarations = re.findall(br'<!DOCTYPE[^>]*>', xml, re.I)
    e.require(len(declarations)<=1 and all(re.fullmatch(br'<!DOCTYPE ep-patent-document PUBLIC "-//EPO//EP PATENT DOCUMENT [0-9.]+//EN" "ep-patent-document-v[0-9-]+\.dtd">', x) for x in declarations), 'Unsupported official EPO XML declaration')
    x = ET.fromstring(xml)
    refs = x.findall('./SDOBI/B200/B210')
    e.require(x.tag=='ep-patent-document' and len(refs)==1, 'Exact EPO root/application reference required')
    apno = refs[0].text or ''
    pn = x.get('country','')+x.get('doc-number','')+x.get('kind','')
    e.require(re.fullmatch(r'\d{8}\.\d',apno) and x.get('country')=='EP' and x.get('doc-number')==epn and x.get('kind')=='B1' and pn==es.get('publication_number'), 'Canonical EPO publication differs from same national record')
    e.require(apno==eakz if jurisdiction=='DE' else apno.split('.')[0]==eakz, 'Canonical EPO B210 differs from exact national application field')
    e.require(ta['application_number']=='EP20'+apno.split('.')[0] and x.get('date-publ')==date, 'Canonical application or original grant publication date differs')
    expected = '/publication-server/rest/v1.2/publication-dates/'+date+'/patents/EP'+epn+'NWB1/document.xml'
    e.require(urlsplit(es['source_url']).path==expected, 'Official EPO URL does not name this exact publication/date')
    registration()._publication(c,pn,ta['id'],e)
    proof.update({'publication_number':pn,'application_number':apno,'publication_date':date,'locators':{'publication':'/ep-patent-document/@country,@doc-number,@kind,@date-publ','application':'/ep-patent-document/SDOBI/B200/B210'}})
    return proof

def prepare(c, p, e):
    e.require(isinstance(p,dict) and p.get('adapter') in ADAPTERS, 'Unsupported explicit national-registration adapter')
    e.require(p.get('relation_type')==RELATION, 'Explicit national-register relation required')
    member, target = p.get('member_application_id'), p.get('canonical_filing_application_id')
    e.require(member and target and member!=target, 'Distinct national member and canonical EP application required')
    ma, ta = registration()._identity(c,member,e), registration()._identity(c,target,e)
    jurisdiction = 'DE' if p['adapter']=='dpma_patentblatt_same_notice_v1' else 'AT'
    e.require(ma.get('authority')==jurisdiction and ta.get('authority')=='EP', 'Adapter jurisdiction and retained identities differ')
    e.require(ma.get('patent_type')==ta.get('patent_type')=='invention', 'Resolved invention classifications required')
    for app in (ma,ta):
        conflicts=app.get('metadata_conflicts',[])+e.bibliography_conflicts(c,app['id'])
        e.require(not any(x.get('field')=='patent_type' for x in conflicts), 'Unresolved patent-type conflict')
    pns=p.get('member_publication_ids')
    e.require(isinstance(pns,list) and pns and len(pns)==len(set(pns)), 'Distinct retained member publications required')
    for pn in pns:
        registration()._publication(c,pn,member,e)
    e.require(p.get('reviewer') and p.get('basis'), 'Reviewer and explicit mapping basis required')
    rp, eakz, epn, date, jurisdiction = (dpma if jurisdiction=='DE' else seeip)(c,p,ma,e)
    cp = canonical(c,p,ta,eakz,epn,date,jurisdiction,e)
    snapshot={'member':{'id':member,'authority':ma['authority'],'application_number':ma['application_number'],'publication_ids':sorted(pns)},'canonical':{'id':target,'authority':ta['authority'],'application_number':ta['application_number'],'publication_number':cp['publication_number']}}
    proof={'adapter':p['adapter'],'official_register':rp,'canonical_filing_evidence':cp,'identity_snapshot':snapshot}
    return {**p,'id':'registration-'+e.digest([member,target])[:24],'national_jurisdiction':jurisdiction,'record_class':'ep_national_register_member','count_as_additional_independent_filing':False,'validated_proof':proof,'proof_hash':e.digest(proof),'provider_publication_identity_notice':'Provider identity retained; this mapping does not establish an independently published national document.','technical_source_notice':'Canonical EP evidence remains EP evidence; no member document or analysis is created or marked complete.','legal_scope_notice':'National register observations and dated events remain independent; actual acquisition date is not a cutoff-date legal snapshot.'}
