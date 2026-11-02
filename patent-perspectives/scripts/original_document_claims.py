"""Verify complete original-publication claims hosted by a disclosed PDF mirror.

The host extracts and visually reads the PDF. The legacy standard-library verifier
checks immutable artifacts, exact page spans and that explicit review. It does
not treat mirror HTML, automatic translations or family similarity as evidence.
The explicit CN visual-region path additionally verifies exact PNG crops with Pillow.
"""
import hashlib
import io
import json
import re
from pathlib import Path
from urllib.parse import urlsplit

LABEL = '专利局原始公报的第三方托管副本'
VISUAL_MODE = 'cn_printed_claims_visual_regions_v1'


def verify_visual_regions(source,review,extraction,offsets,claims,renderings,load_spec,e):
    q=e.require;proof=source['original_document_proof']
    spec=proof.get('visual_region_transcriptions')
    _,raw=load_spec(spec,'visual region transcriptions')
    try:data=json.loads(raw.decode('utf-8-sig'))
    except (UnicodeError,ValueError):raise e.ValidationError('Visual region transcription proof must be JSON')
    q(isinstance(data,dict) and data.get('schema_version')==1 and data.get('mode')==VISUAL_MODE,
      'Unsupported visual region proof schema')
    q(data.get('publication_number')==source['publication_number'] and data.get('pdf_sha256')==proof['pdf']['sha256']
      and data.get('extraction_sha256')==proof['extraction']['sha256'],'Visual regions must bind the same publication, PDF and extraction')
    q(data.get('reviewer') and data.get('reviewed_at') and data.get('all_technical_regions_inventoried') is True
      and data.get('all_regions_actually_viewed') is True and source.get('normalization_notice'),
      'Visual regions need actual complete host inspection and an explicit transcription notice')
    regions=data.get('regions');inventory=review.get('embedded_claim_images')
    q(isinstance(regions,list) and regions and isinstance(inventory,list) and inventory,'Every original technical visual region must be inventoried')
    q(all(isinstance(r,dict) for r in regions),'Visual region entries must be objects')
    kinds={'formula','inline_math','table','chemical_structure','drawing'}
    seen={}
    for item in inventory:
        q(isinstance(item,dict) and isinstance(item.get('id'),str) and item['id'] and item['id'] not in seen
          and item.get('kind') in kinds and type(item.get('page_number')) is int,'Original visual inventory has missing or duplicate identity')
        seen[item['id']]={'kind':item['kind'],'page_number':item['page_number']}
    q(len(regions)==len(seen) and {r.get('id') for r in regions}==set(seen),'Visual inventory and transcriptions must cover exactly the same regions')
    bypage={o['page_number']:o for o in offsets};byclaim={c['number']:c for c in claims}
    try:from PIL import Image
    except ImportError:raise e.ValidationError('Visual region verification requires Pillow; artifacts remain preserved')
    for region in regions:
        q(isinstance(region,dict) and region.get('visually_verified') is True,'Every visual region requires actual host inspection')
        identity=seen[region['id']];page=region.get('page_number')
        q(region.get('kind')==identity['kind'] and page==identity['page_number'] and page in bypage,
          'Visual region identity or original claims page differs from inventory')
        rendering,pixels=renderings[page]
        q(region.get('rendering_sha256')==rendering['sha256'],'Visual crop must bind the exact reviewed original page pixels')
        start,end=region.get('page_start'),region.get('page_end');o=bypage[page]
        q(type(start) is int and type(end) is int and o['page_start']<=start<end<=o['page_start']+o['end']-o['start'],
          'Visual transcription must remain within the reviewed claims page span')
        transcription=region.get('transcription')
        q(isinstance(transcription,str) and transcription.strip() and extraction['pages'][page-1]['text'][start:end]==transcription,
          'Visual transcription must equal its exact extracted-page character interval')
        claim=byclaim.get(region.get('claim_number'));global_start=o['start']+start-o['page_start'];global_end=o['start']+end-o['page_start']
        q(claim and claim['start']<=global_start<global_end<=claim['end'],'Visual transcription must belong to the declared actual claim')
        bbox=region.get('bbox')
        q(isinstance(bbox,list) and len(bbox)==4 and all(type(x) is int for x in bbox),'Visual region bbox must contain four integer pixel coordinates')
        _,crop=load_spec(region.get('crop'),'visual region crop')
        q(crop.startswith(b'\x89PNG\r\n\x1a\n'),'Visual region crop must be a real PNG')
        try:
            with Image.open(io.BytesIO(pixels)) as full,Image.open(io.BytesIO(crop)) as cropped:
                full.load();cropped.load()
                q(0<=bbox[0]<bbox[2]<=full.width and 0<=bbox[1]<bbox[3]<=full.height,'Visual crop bbox outside original page')
                expected=full.convert('RGBA').crop(tuple(bbox));actual=cropped.convert('RGBA')
                q(actual.size==expected.size and actual.tobytes()==expected.tobytes(),'Visual crop pixels differ from the exact original page region')
        except e.ValidationError:raise
        except Exception:raise e.ValidationError('Visual region image cannot be completely decoded')
    return len(regions)


def verify_standard(c, source, e):
    q = e.require
    q(source.get('source_class') == 'original_patent_document_mirror', 'Wrong original claims source class')
    q(source.get('source_label') == LABEL, 'Original PDF mirror must disclose third-party hosting')
    q(source.get('document_type') == 'claims' and source.get('complete') is True
      and source.get('truncated') is False, 'Original mirror adapter accepts complete claims only')
    pn = source.get('publication_number')
    q(isinstance(pn, str) and pn == e.number(pn), 'Original claims PN must be exact')
    row = c.execute('SELECT data FROM publications WHERE id=?', (pn,)).fetchone()
    q(row, 'Original claims publication must already belong to the run')
    publication = json.loads(row[0])
    proof = source.get('original_document_proof')
    q(isinstance(proof, dict), 'Original claims PDF requires explicit source proof')
    u = urlsplit(source.get('source_url', ''))
    q(u.scheme == 'https' and u.netloc == 'patentimages.storage.googleapis.com'
      and not u.query and not u.fragment and re.fullmatch(
          r'/[a-f0-9]{2}/[a-f0-9]{2}/[a-f0-9]{2}/[a-f0-9]{14}/' + re.escape(pn) + r'\.pdf', u.path),
      'Original claims require the fixed exact-PN PDF mirror URL')
    dbfile = c.execute('PRAGMA database_list').fetchone()[2]
    q(dbfile, 'Original PDF verification requires a file-backed run')
    root = Path(dbfile).resolve().parent

    def load_spec(spec,key):
        q(isinstance(spec, dict), 'Missing original PDF artifact: ' + key)
        rel = spec.get('artifact')
        q(isinstance(rel, str) and rel and not Path(rel).is_absolute(), 'Original PDF artifact must be relative to run')
        path = (root / rel).resolve()
        q(path.is_relative_to(root) and path.is_file(), 'Original PDF artifact outside or absent from run')
        raw = path.read_bytes()
        q(re.fullmatch(r'[a-f0-9]{64}', str(spec.get('sha256', '')))
          and hashlib.sha256(raw).hexdigest() == spec['sha256'], 'Original PDF artifact hash mismatch: ' + key)
        return path, raw

    def artifact(key):return load_spec(proof.get(key),key)

    pdfpath, pdf = artifact('pdf')
    q(pdf.startswith(b'%PDF-') and b'%%EOF' in pdf[-2048:], 'Original PDF is missing or truncated')
    parsed = {}
    for key in ('extraction', 'review', 'receipt'):
        _, raw = artifact(key)
        try:
            parsed[key] = json.loads(raw.decode('utf-8-sig'))
        except (UnicodeError, ValueError):
            raise e.ValidationError('Original PDF proof must contain valid JSON: ' + key)
        q(isinstance(parsed[key], dict), 'Original PDF proof must contain objects')
    extraction, review, receipt = (parsed[k] for k in ('extraction', 'review', 'receipt'))
    pdfsha = proof['pdf']['sha256']
    q(receipt.get('status') == 200 and receipt.get('source_url') == source['source_url']
      and receipt.get('final_url') == source['source_url'] and receipt.get('sha256') == pdfsha
      and receipt.get('bytes') == len(pdf) and receipt.get('content_type', '').split(';')[0].strip() == 'application/pdf'
      and receipt.get('acquired_at') == source.get('acquired_at'), 'Original PDF acquisition receipt differs from source')
    count = extraction.get('page_count')
    pages = extraction.get('pages')
    q(type(count) is int and count > 0 and isinstance(pages, list) and len(pages) == count
      and [p.get('page_number') for p in pages] == list(range(1, count + 1))
      and all(isinstance(p.get('text'), str) for p in pages), 'Original PDF extraction must retain all ordered pages')
    q(extraction.get('pdf_sha256') == pdfsha and extraction.get('publication_number') == pn
      and extraction.get('extraction_tool'), 'Original PDF extraction identity mismatch')
    q(review.get('kind') == 'host_original_patent_claims_review' and review.get('result') == 'complete_claims_confirmed'
      and review.get('reviewer') and review.get('reviewed_at') and review.get('visual_review_performed') is True,
      'Original PDF claims need an explicit actual visual review')
    q(review.get('pdf_sha256') == pdfsha and review.get('publication_number') == pn
      and review.get('extraction_sha256') == proof['extraction']['sha256']
      and review.get('patent_office') == publication['authority']
      and review.get('language') == source.get('language'), 'Original PDF review identity/language mismatch')
    q(review.get('all_claims_pages_reviewed') is True and review.get('missing_or_unreadable_content') is False
      and review.get('machine_translation_used') is False,
      'Original PDF claims have missing, unreviewed, image or translated content')
    visual_mode=review.get('visual_content_mode')
    if visual_mode is None:
        q(review.get('embedded_claim_images')==[] and 'visual_region_transcriptions' not in proof,
          'Original PDF image or formula content requires the explicit supported visual-region proof path')
    else:
        q(visual_mode==VISUAL_MODE and publication['authority']=='CN'
          and review.get('completeness_mode','printed_claim_section_fraction')=='printed_claim_section_fraction'
          and review.get('incorporated_specification') is None,'Visual-region mode is verified only for original CN printed claims sections')

    def quote_at(item):
        q(isinstance(item, dict), 'Original PDF locator must be an object')
        page = item.get('page_number')
        quote = item.get('quote')
        q(type(page) is int and 1 <= page <= count and isinstance(quote, str) and quote.strip()
          and quote in pages[page - 1]['text'], 'Original PDF quote does not occur in the selected page')
        return page, quote

    identity = review.get('identity')
    q(isinstance(identity, dict), 'Original PDF requires a cover identity')
    cover, coverquote = quote_at(identity.get('publication'))
    _, appquote = quote_at(identity.get('application'))
    _, officequote = quote_at(identity.get('office'))
    q(identity['application']['page_number'] == cover and identity['office']['page_number'] == cover,
      'Original PDF publication, office and application must share the cover')
    check = identity.get('application_check_digit')
    application = publication['application_number'][2:]
    if check is not None:
        q(isinstance(check, str) and re.fullmatch(r'[0-9X]', check), 'Invalid explicitly retained application check digit')
        application_matches = re.sub(r'\s', '', appquote).endswith(application + '.' + check)
    else:
        application_matches = e.number(appquote).endswith(application)
    q(e.number(coverquote).endswith(pn[2:]) and application_matches, 'Original PDF cover PN/application mismatch')
    attachment = review.get('incorporated_specification')
    headerpn = pn
    if attachment is not None:
        q(isinstance(attachment, dict) and attachment.get('kind') == 'explicitly_incorporated_original_specification'
          and attachment.get('basis'), 'Original PDF attachment cannot be inferred from family similarity')
        q(publication['authority'] == 'HK', 'Composite mirror adapter is currently verified only for HK specifications')
        kp, kq = quote_at(attachment.get('container_document_kind'))
        q(kp == cover and 'STANDARD PATENT (R) SPECIFICATION' in kq,
          'Composite HK source must identify its transcribed-standard-specification kind')
        headerpn = attachment.get('publication_number')
        q(isinstance(headerpn, str) and re.fullmatch(r'[A-Z]{2}\d+[A-Z]\d*', headerpn), 'Invalid incorporated publication PN')
        cp, cq = quote_at(attachment.get('cover_link'))
        q(cp == cover and e.number(cq) == headerpn, 'Incorporated specification must be expressly named on the same PDF cover')
        ap, aq = quote_at(attachment.get('application'))
        cap, caq = quote_at(attachment.get('cover_application'))
        embedded_application = attachment.get('application_number')
        q(isinstance(embedded_application, str) and embedded_application.startswith(headerpn[:2])
          and embedded_application == e.number(embedded_application)
          and e.number(aq).endswith(embedded_application[2:])
          and cap == cover and e.number(caq).endswith(embedded_application), 'Incorporated application must match both covers in the same PDF')
        q(ap != cover, 'Incorporated application requires its own original-specification cover')
        ep, eq = quote_at(attachment.get('embedded_publication'))
        q(ep == ap and e.number(eq) == headerpn, 'Incorporated original cover must repeat the exact embedded PN/kind')
    regions = review.get('claim_text_regions')
    q(isinstance(regions, list) and regions, 'Original PDF claims page spans are missing')
    mode = review.get('completeness_mode', 'printed_claim_section_fraction')
    q(mode in ('printed_claim_section_fraction', 'whole_ru_application_publication'),
      'Unsupported original PDF completeness mode')
    whole_ru = mode == 'whole_ru_application_publication'
    if whole_ru:
        q(publication['authority'] == 'RU' and re.fullmatch(r'RU\d+A', pn)
          and str(source.get('language', '')).lower() == 'ru' and attachment is None,
          'Whole-publication mode is limited to original Russian A application publications')
        q(cover == 1 and review.get('all_pdf_pages_reviewed') is True
          and review.get('pdf_contains_only_bibliography_and_claims') is True
          and [r.get('page_number') for r in regions] == list(range(1, count + 1)),
          'Whole Russian publication requires every original PDF page and actual review')
        kp, kq = quote_at(review.get('publication_kind'))
        tp, tq = quote_at(review.get('claims_heading'))
        fp, fq = quote_at(identity.get('publication_front'))
        front = re.sub(r'\((?:19|11|13)\)', '', fq)
        q(fp == 1 and re.fullmatch(r'\(19\)\s*RU\s*\(11\)\s*[\d\s]+\(13\)\s*A', fq)
          and e.number(front) == pn,
          'Russian front INID country, publication number and A kind must identify this exact document')
        q(kp == tp == 1 and re.fullmatch(r'\(12\)\s*ЗАЯВКА НА ИЗОБРЕТЕНИЕ', kq)
          and re.fullmatch(r'\(57\)\s*Формула изобретения', tq),
          'Russian whole publication requires the original application kind and claims heading')
        q('ФЕДЕРАЛЬНАЯ СЛУЖБА' in officequote
          and 'ПО ИНТЕЛЛЕКТУАЛЬНОЙ СОБСТВЕННОСТИ' in officequote
          and e.number(coverquote) == pn,
          'Russian whole publication requires the exact RU cover and patent-office identity')
    if attachment is not None:
        dp, dq = quote_at(attachment.get('claims_section_declaration'))
        q(dp == attachment['application']['page_number']
          and re.search(r'权\s*利\s*要\s*求\s*书\s*' + str(len(regions)) + r'\s*页', dq),
          'Incorporated cover must declare the complete claims-section page count')
    q([r.get('page_number') for r in regions] == sorted({r.get('page_number') for r in regions})
      and all(regions[i]['page_number'] == regions[0]['page_number'] + i for i in range(len(regions))),
      'Original PDF claims pages must be unique, ordered and consecutive')
    pieces, offsets, offset = [], [], 0
    for i, region in enumerate(regions):
        page = region.get('page_number')
        q(type(page) is int and 1 <= page <= count, 'Original PDF claims page outside extraction')
        body = pages[page - 1]['text']
        start, end = region.get('start'), region.get('end')
        q(type(start) is int and type(end) is int and 0 <= start < end <= len(body), 'Invalid original claims page span')
        q(region.get('omitted_before') == body[:start] and region.get('omitted_after') == body[end:],
          'All omitted page material must be retained for visual review')
        q(region.get('omissions_are_headers_footers_only') is True, 'Original claims page may not omit claim content')
        part = body[start:end]
        q(part == part.strip() and part, 'Original claims body span must have exact nonblank boundaries')
        if whole_ru:
            q('section_page_label' not in region,
              'Russian page numbers must not fabricate printed fractional section labels')
            lp, lq = quote_at(region.get('printed_publication_page'))
            q(lp == page and re.fullmatch(r'Стр\.:\s*' + str(page), lq),
              'Russian publication page number must match the entire PDF sequence')
            prefix, suffix = body[:start], body[end:]
            if page == 1:
                q(prefix.endswith(tq + '\n') and body.count(tq) == 1
                  and all(v in prefix for v in (fq, appquote, officequote, kq))
                  and not re.search(r'(?m)^\s*\d+\.\s+\S', prefix),
                  'Russian first-page omission must be the reviewed bibliography and claims heading only')
            else:
                q(prefix == '', 'Russian continuation page may not drop leading claim text')
            foot = [line.strip() for line in suffix.split('\n') if line.strip()]
            q(len(foot) == 3 and foot[0] == lq and all(e.number(line) == pn for line in foot[1:]),
              'Russian page may omit only its exact printed footer and repeated original PN')
        else:
            label = region.get('section_page_label')
            lp, lq = quote_at(label)
            q(lp == page and re.search(r'(?<!\d)' + str(i + 1) + r'\s*/\s*' + str(len(regions)) + r'(?!\d)', lq),
              'Original claims need printed first/total page labels')
        header_kind = review.get('running_header_kind', 'publication_number')
        q(header_kind in ('publication_number', 'cn_application_number'), 'Unsupported original claims running header kind')
        if header_kind == 'cn_application_number':
            # Older Chinese publications print their full application number
            # instead of the PN on each claims page. The exact fixed PDF cover
            # still supplies the publication version; never relabel this header.
            q(publication['authority'] == 'CN' and attachment is None and not whole_ru,
              'Application-number running headers are verified only for original CN publications')
            q('publication_header' not in region, 'An application-number header must not be called a publication header')
            hp, hq = quote_at(region.get('application_header'))
            compact = re.sub(r'\s', '', hq)
            q(hp == page and re.fullmatch(r'\d{12}\.[0-9X]', compact)
              and e.number(compact) == application,
              'CN running header must contain the exact retained full application number and check digit')
            q(re.sub(r'\s', '', appquote).endswith(compact)
              and review.get('cover_check_digit_observed') == compact[-1],
              'CN running header and observed check digit must match the actual cover application quote')
        else:
            hp, hq = quote_at(region.get('publication_header'))
            q(hp == page and e.number(hq) == headerpn, 'Original claims page header identity mismatch')
        offsets.append({'page_number': page, 'start': offset, 'end': offset + len(part), 'page_start': start})
        pieces.append(part)
        offset += len(part) + 1
    text = '\n'.join(pieces)
    q(text == source.get('text'), 'Normalized original claims must equal exact reviewed PDF spans')
    q(review.get('claim_count') == source.get('claim_count') and type(source.get('claim_count')) is int,
      'Original PDF reviewer and source claim count differ')
    claims = e.claim_blocks(text)
    q([b['number'] for b in claims] == list(range(1, source['claim_count'] + 1)), 'Original PDF claims are incomplete or out of order')
    if whole_ru:
        tail_page, tail_quote = quote_at(review.get('last_claim_tail'))
        q(tail_page == count and tail_quote == claims[-1]['text']
          and review['last_claim_tail'].get('claim_number') == source['claim_count'],
          'Russian whole publication requires the exact complete final claim and its last-page location')
    required_pages = {cover, *(r['page_number'] for r in regions)}
    if attachment is not None:
        required_pages.add(attachment['application']['page_number'])
    renderings = proof.get('reviewed_renderings')
    q(isinstance(renderings, list) and {r.get('page_number') for r in renderings} == required_pages
      and len(renderings) == len(required_pages), 'Original claims need reviewed cover/claim-page renderings')
    rendered_pixels={}
    for rendering in renderings:
        q(rendering.get('pdf_sha256') == pdfsha and rendering.get('visually_reviewed') is True,
          'Original page rendering must bind the exact PDF and actual review')
        _,pixels=load_spec(rendering,'reviewed rendering')
        q(pixels.startswith(b'\x89PNG\r\n\x1a\n'), 'Original PDF reviewed rendering must be PNG')
        rendered_pixels[rendering['page_number']]=(rendering,pixels)
    visual_count=verify_visual_regions(source,review,extraction,offsets,claims,rendered_pixels,load_spec,e) if visual_mode else 0
    public = {'source_class': source['source_class'], 'source_label': LABEL, 'publication_number': pn,
              'pdf_sha256': pdfsha, 'extraction_sha256': proof['extraction']['sha256'],
              'source_url': source['source_url'], 'acquired_at': source['acquired_at'], 'page_count': count,
              'claims_pdf_pages': [r['page_number'] for r in regions],
              'claim_count': source['claim_count'], 'patent_office': publication['authority'],
              'completeness_mode': mode,
              'container_application_quote': appquote,
              'reviewer': review['reviewer'], 'reviewed_at': review['reviewed_at'],
              'source_notice': '依据本件原始公报内完整权利要求；第三方托管不代表已核实法律状态。',
              'claim_page_locators': [{'claim_number': b['number'], 'pdf_pages': [r['page_number'] for r in offsets
                                     if b['start'] < r['end'] and b['end'] > r['start']]} for b in claims]}
    if review.get('running_header_kind') == 'cn_application_number':
        public['running_header_kind'] = 'cn_application_number'
        public['source_notice'] += ' 权项页印有与封面一致的完整申请号，版本由同一PDF封面和连续页绑定。'
    if visual_mode:
        public['visual_content_mode']=visual_mode
        public['visually_transcribed_regions']=visual_count
        public['source_notice']+=' 本件公式、表格等图文区域含明确标记的人工转写；原始排版和符号可在离线原公报对应页核对。'
    if attachment is not None:
        public['incorporated_specification'] = {'publication_number': headerpn, 'cover_pdf_page': cover,
                                               'application_number': attachment['application_number'],
                                               'basis': attachment['basis']}
        public['source_notice'] += ' 本件封面明确收入的原始说明书为' + headerpn + '，保留两种身份，不据此合并申请或推定其他关系。'
    return public, pdfpath


def prepare(c, appids, e):
    mapping, blobs = {}, {}
    for row in c.execute('SELECT * FROM documents ORDER BY id'):
        if row['application_id'] not in appids:
            continue
        source = json.loads(row['data'])
        if source.get('source_class') != 'original_patent_document_mirror':
            continue
        public, path = verify(c, {**source, 'text': row['text']}, e)
        relative = 'source-documents/' + public['pdf_sha256'] + '.pdf'
        public['offline_pdf_path'] = relative
        mapping[row['id']] = public
        blobs[relative] = {'path': path, 'sha256': public['pdf_sha256']}
    return mapping, blobs


def copy_verified(blobs, output, e):
    for relative, source in blobs.items():
        raw = source['path'].read_bytes()
        e.require(hashlib.sha256(raw).hexdigest() == source['sha256'], 'Original PDF changed between verification and copy')
        dest = Path(output) / relative
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(raw)


# Narrow WO Chinese scanned-publication extension.
WO_COMPLETENESS_MODE = 'whole_wo_application_publication_claims_range'
WO_VISUAL_MODE = 'wo_scanned_claims_visual_regions_v1'


def verify_wo(c, source, e):
    """Only Chinese WO A1 whole-publication PDFs with a bounded claims range.

    The raw scan carrier, actual PDF rendering and technical crop are distinct
    artifacts. Native rendering is checked here; host visual transcription still
    remains a declared human/host reading act, never inferred from this check.
    """
    import subprocess
    import tempfile
    from PIL import Image
    from pypdf import PdfReader
    q = e.require
    pn = source.get('publication_number')
    q(isinstance(pn, str) and re.fullmatch(r'WO\d{10}A1', pn), 'WO mode requires the exact original WO A1 PN')
    q(source.get('original_document_completeness_mode') == WO_COMPLETENESS_MODE,
      'WO source must explicitly select its narrow completeness mode')
    q(source.get('source_class') == 'original_patent_document_mirror' and source.get('source_label') == LABEL,
      'WO original PDF must disclose the mirror source class and label')
    q(source.get('document_type') == 'claims' and source.get('complete') is True
      and source.get('truncated') is False and source.get('replace_by_related') is False,
      'WO original PDF accepts complete same-publication claims only')
    row = c.execute('SELECT data FROM publications WHERE id=?', (pn,)).fetchone()
    q(row, 'WO original publication must already belong to the retained run')
    publication = json.loads(row[0])
    q(publication.get('authority') == 'WO' and str(source.get('language', '')).lower() in ('cn', 'zh'),
      'WO scanned mode is verified only for Chinese WO publications, without relabelling jurisdiction')
    u = urlsplit(source.get('source_url', ''))
    q(u.scheme == 'https' and u.netloc == 'patentimages.storage.googleapis.com' and not u.query and not u.fragment
      and re.fullmatch(r'/[a-f0-9]{2}/[a-f0-9]{2}/[a-f0-9]{2}/[a-f0-9]{14}/' + re.escape(pn) + r'\.pdf', u.path),
      'WO mode needs the fixed exact-PN original PDF mirror URL')
    dbfile = c.execute('PRAGMA database_list').fetchone()[2]
    q(dbfile, 'WO proof requires a file-backed run')
    root = Path(dbfile).resolve().parent
    proof = source.get('original_document_proof')
    q(isinstance(proof, dict), 'WO source requires original-document proof')

    def load_spec(spec, key):
        q(isinstance(spec, dict) and isinstance(spec.get('artifact'), str) and spec['artifact']
          and not Path(spec['artifact']).is_absolute(), 'WO artifact needs a run-relative path: ' + key)
        p = (root / spec['artifact']).resolve()
        q(p.is_relative_to(root) and p.is_file(), 'WO artifact absent or outside run: ' + key)
        raw = p.read_bytes()
        q(re.fullmatch(r'[a-f0-9]{64}', str(spec.get('sha256', '')))
          and hashlib.sha256(raw).hexdigest() == spec['sha256'], 'WO artifact hash mismatch: ' + key)
        return p, raw

    def json_spec(spec, key):
        _, raw = load_spec(spec, key)
        try: value = json.loads(raw.decode('utf-8-sig'))
        except (ValueError, UnicodeError): raise e.ValidationError('WO proof JSON invalid: ' + key)
        q(isinstance(value, dict), 'WO proof must be an object: ' + key)
        return value

    pdfpath, pdf = load_spec(proof.get('pdf'), 'PDF')
    q(pdf.startswith(b'%PDF-') and b'%%EOF' in pdf[-2048:], 'WO PDF missing or truncated')
    pdfsha = proof['pdf']['sha256']
    receipt = json_spec(proof.get('receipt'), 'receipt')
    extraction = json_spec(proof.get('extraction'), 'visual extraction')
    review = json_spec(proof.get('review'), 'review')
    raw_extraction = json_spec(proof.get('raw_extraction'), 'original raw extraction')
    q(receipt.get('status') == 200 and receipt.get('source_url') == source['source_url']
      and receipt.get('final_url') == source['source_url'] and receipt.get('sha256') == pdfsha
      and receipt.get('bytes') == len(pdf) and receipt.get('content_type', '').split(';')[0].strip() == 'application/pdf'
      and receipt.get('acquired_at') == source.get('acquired_at'), 'WO acquisition receipt differs from original source')
    reader = PdfReader(io.BytesIO(pdf))
    count = len(reader.pages)
    for value, name in ((extraction, 'visual'), (raw_extraction, 'raw')):
        q(value.get('page_count') == count and value.get('pdf_sha256') == pdfsha
          and (value.get('publication_number') or value.get('publication_number_requested')) == pn
          and value.get('extraction_tool') and isinstance(value.get('pages'), list)
          and [p.get('page_number') for p in value['pages']] == list(range(1, count + 1))
          and all(isinstance(p.get('text'), str) for p in value['pages']), 'WO ' + name + ' extraction must preserve all ordered pages')
    q(all((p.extract_text() or '') == raw_extraction['pages'][i]['text'] for i, p in enumerate(reader.pages)),
      'WO raw extraction differs from the actual same-PDF native text layer')
    q(extraction.get('manual_visual_transcription') is True and source.get('normalization_notice'),
      'WO scanned text requires an explicit complete manual-visual transcription notice')
    q(review.get('kind') == 'host_original_patent_claims_review'
      and review.get('result') == 'complete_claims_confirmed' and review.get('reviewer') and review.get('reviewed_at')
      and review.get('visual_review_performed') is True and review.get('all_claims_pages_reviewed') is True
      and review.get('missing_or_unreadable_content') is False and review.get('machine_translation_used') is False,
      'WO claims require actual complete original visual reading')
    q(review.get('publication_number') == pn and review.get('pdf_sha256') == pdfsha
      and review.get('extraction_sha256') == proof['extraction']['sha256'] and review.get('patent_office') == 'WO'
      and review.get('language') == source.get('language') and review.get('completeness_mode') == WO_COMPLETENESS_MODE
      and review.get('visual_content_mode') == WO_VISUAL_MODE and review.get('incorporated_specification') is None,
      'WO review identity, language, completeness or visual mode mismatch')
    pages = extraction['pages']

    def quote_at(item):
        q(isinstance(item, dict), 'WO locator must be an object')
        page, quote = item.get('page_number'), item.get('quote')
        q(type(page) is int and 1 <= page <= count and isinstance(quote, str) and quote.strip()
          and quote in pages[page - 1]['text'], 'WO quote absent from exact original page transcription')
        return page, quote

    identity = review.get('identity')
    q(isinstance(identity, dict), 'WO cover identity is required')
    cp, cq = quote_at(identity.get('publication'))
    ap, aq = quote_at(identity.get('application'))
    op, oq = quote_at(identity.get('office'))
    kp, kq = quote_at(review.get('publication_kind'))
    lp, lq = quote_at(review.get('publication_language'))
    q(cp == ap == op == kp == lp == 1 and e.number(cq) == pn
      and e.number(aq) == e.number(publication.get('application_number', ''))
      and re.fullmatch(r'PCT/[A-Z]{2}\d{4}/\d{6}', re.sub(r'\s', '', aq)),
      'WO cover must bind exact publication kind and actual PCT application, on the same first page')
    q('世界知识产权组织' in re.sub(r'\s', '', oq) and '国际局' in re.sub(r'\s', '', oq)
      and re.fullmatch(r'\(12\)\s*按照专利合作条约所公布的国际申请', kq)
      and re.fullmatch(r'\(26\)\s*公布语言\s*[:：]?\s*中文', lq),
      'WO cover must show WIPO international publication kind and Chinese publication language')
    regions = review.get('claim_text_regions')
    q(isinstance(regions, list) and regions and all(isinstance(r, dict) for r in regions), 'WO complete claims spans required')
    physical = [r.get('page_number') for r in regions]
    q(all(type(n) is int for n in physical) and physical == list(range(physical[0], physical[-1] + 1))
      and 1 < physical[0] <= physical[-1] < count, 'WO claims physical range must be unique, continuous and bounded')
    hp, hq = quote_at(review.get('claims_heading'))
    q(hp == physical[0] and re.fullmatch(r'权\s*利\s*要\s*求\s*书', hq), 'WO first claims page needs its actual claims heading')
    boundaries = review.get('claims_range_boundaries')
    q(isinstance(boundaries, dict), 'WO claims need actual immediately adjacent before/after boundaries')
    bp, bq = quote_at(boundaries.get('before'))
    ep, eq = quote_at(boundaries.get('after'))
    q(bp == physical[0] - 1 and ep == physical[-1] + 1
      and boundaries['before'].get('kind') == 'description_end'
      and boundaries['after'].get('kind') == 'drawings_start'
      and boundaries['before'].get('visually_reviewed') is True and boundaries['after'].get('visually_reviewed') is True
      and re.search(r'图\s*1', eq) and not re.search(r'(?m)^\s*权\s*利\s*要\s*求\s*书\s*$', pages[bp - 1]['text'])
      and not re.search(r'(?m)^\s*权\s*利\s*要\s*求\s*书\s*$', pages[ep - 1]['text']),
      'WO boundaries must be immediately adjacent actual description end and drawings start')
    pieces, offsets, offset, printed = [], [], 0, []
    for i, region in enumerate(regions):
        page = region['page_number'];body = pages[page - 1]['text']
        start, end = region.get('start'), region.get('end')
        q(type(start) is int and type(end) is int and 0 <= start < end <= len(body), 'WO page body span invalid')
        q(region.get('omitted_before') == body[:start] and region.get('omitted_after') == body[end:]
          and region.get('omissions_are_headers_footers_only') is True and 'section_page_label' not in region,
          'WO spans must retain all omissions and must never invent a fractional section label')
        part = body[start:end]
        q(part and part == part.strip(), 'WO claim body boundaries must be exact nonblank text')
        pp, pq = quote_at(region.get('publication_header'));pa, pqa = quote_at(region.get('application_header'))
        q(pp == pa == page and e.number(pq) == pn[:-2] and e.number(pqa) == e.number(aq),
          'Every WO claims page must repeat its exact WO publication and PCT application header')
        fp, fq = quote_at(region.get('printed_publication_page'));number = region['printed_publication_page'].get('number')
        q(fp == page and type(number) is int and number >= 1 and fq == str(number)
          and [z.strip() for z in body[end:].splitlines() if z.strip()] == [fq],
          'WO claims use the actual integer publication footer, not a section fraction')
        printed.append(number)
        expected_prefix = [pq, pqa] + ([hq] if i == 0 else [])
        q([z.strip() for z in body[:start].splitlines() if z.strip()] == expected_prefix,
          'WO prefix omission may contain only the actual two running headers and first claims heading')
        offsets.append({'page_number': page, 'start': offset, 'end': offset + len(part), 'page_start': start})
        pieces.append(part);offset += len(part) + 1
    q(printed == list(range(printed[0], printed[0] + len(printed))), 'WO real printed publication page sequence has a gap')
    text = '\n'.join(pieces)
    q(text == source.get('text'), 'WO normalized claims must equal exact complete reviewed page spans')
    claims = e.claim_blocks(text)
    q(type(source.get('claim_count')) is int and review.get('claim_count') == source['claim_count']
      and [v['number'] for v in claims] == list(range(1, source['claim_count'] + 1)), 'WO actual claims are incomplete, missing or out of order')
    tp, tq = quote_at(review.get('last_claim_tail'))
    q(tp == physical[-1] and review['last_claim_tail'].get('claim_number') == source['claim_count']
      and tq == claims[-1]['text'], 'WO proof needs the full actual final claim and its final-page location')
    required = {1, bp, ep, *physical};renderings = proof.get('reviewed_renderings')
    q(isinstance(renderings, list) and len(renderings) == len(required)
      and {r.get('page_number') for r in renderings} == required, 'WO cover, all claims and both boundary renderings must be reviewed')
    pixels = {}
    for r in renderings:
        q(r.get('pdf_sha256') == pdfsha and r.get('visually_reviewed') is True and r.get('dpi') == 300,
          'WO page rendering requires same PDF hash, actual visual review and exact 300dpi')
        _, raw = load_spec(r, 'reviewed WO PNG')
        q(raw.startswith(b'\x89PNG\r\n\x1a\n'), 'WO reviewed rendering must be a real PNG')
        pixels[r['page_number']] = (r, raw)
    # Re-render actual immutable PDF, not a substituted page image. No shell or network.
    with tempfile.TemporaryDirectory(prefix='wo-original-pixels-') as tmp:
        for n in sorted(required):
            dest = Path(tmp) / ('page-' + str(n))
            try:
                subprocess.run(['pdftoppm', '-f', str(n), '-l', str(n), '-r', '300', '-png', '-singlefile', str(pdfpath), str(dest)],
                               check=True, capture_output=True, timeout=60)
            except (OSError, subprocess.SubprocessError): raise e.ValidationError('WO actual PDF rendering unavailable; artifacts remain preserved')
            with Image.open(dest.with_suffix('.png')) as expected, Image.open(io.BytesIO(pixels[n][1])) as actual:
                expected.load();actual.load()
                q(expected.size == actual.size and expected.convert('RGBA').tobytes() == actual.convert('RGBA').tobytes(),
                  'WO reviewed page pixels differ from actual same-PDF 300dpi rendering')
    carriers = review.get('page_bitmap_carriers')
    q(isinstance(carriers, list) and len(carriers) == len(physical)
      and {v.get('page_number') for v in carriers} == set(physical), 'WO scans need a distinct complete page-bitmap carrier inventory')
    for carrier in carriers:
        n = carrier['page_number'];images = list(reader.pages[n - 1].images)
        q(carrier.get('actually_viewed') is True and carrier.get('pdf_sha256') == pdfsha
          and carrier.get('rendering_sha256') == pixels[n][0]['sha256'] and len(images) == 1
          and carrier.get('native_image_name') == images[0].name
          and carrier.get('native_image_stream_sha256') == hashlib.sha256(images[0].indirect_reference.get_object()._data).hexdigest(),
          'WO page carrier must identify the single actual original PDF scan, separate from technical regions')
        _, raw = load_spec(carrier.get('decoded_bitmap'), 'decoded PDF scan carrier')
        with Image.open(io.BytesIO(raw)) as actual:
            actual.load();expected = images[0].image.convert('RGBA')
            q(actual.size == expected.size and actual.convert('RGBA').tobytes() == expected.tobytes(),
              'WO decoded page carrier pixels differ from native PDF scan')
    visual_count = verify_wo_visual_regions(source, review, extraction, offsets, claims, pixels, load_spec, e)
    return {'source_class': source['source_class'], 'source_label': LABEL, 'publication_number': pn,
            'pdf_sha256': pdfsha, 'extraction_sha256': proof['extraction']['sha256'], 'source_url': source['source_url'],
            'acquired_at': source['acquired_at'], 'page_count': count, 'claims_pdf_pages': physical,
            'printed_publication_pages': printed, 'claim_count': source['claim_count'], 'patent_office': 'WO',
            'completeness_mode': WO_COMPLETENESS_MODE, 'visual_content_mode': WO_VISUAL_MODE,
            'container_application_quote': aq, 'reviewer': review['reviewer'], 'reviewed_at': review['reviewed_at'],
            'visually_transcribed_regions': visual_count,
            'source_notice': '本件WO国际申请公报完整权利要求；第三方托管，逐页人工图文转录并保留真实连续公报页码，不假造节页数，不代表法律状态核验。',
            'claim_page_locators': [{'claim_number': b['number'], 'pdf_pages': [r['page_number'] for r in offsets
                                     if b['start'] < r['end'] and b['end'] > r['start']]} for b in claims]}, pdfpath

def verify_wo_visual_regions(source,review,extraction,offsets,claims,renderings,load_spec,e):
    q=e.require;proof=source['original_document_proof']
    spec=proof.get('visual_region_transcriptions')
    _,raw=load_spec(spec,'visual region transcriptions')
    try:data=json.loads(raw.decode('utf-8-sig'))
    except (UnicodeError,ValueError):raise e.ValidationError('Visual region transcription proof must be JSON')
    q(isinstance(data,dict) and data.get('schema_version')==1 and data.get('mode')==WO_VISUAL_MODE,
      'Unsupported visual region proof schema')
    q(data.get('publication_number')==source['publication_number'] and data.get('pdf_sha256')==proof['pdf']['sha256']
      and data.get('extraction_sha256')==proof['extraction']['sha256'],'Visual regions must bind the same publication, PDF and extraction')
    q(data.get('reviewer') and data.get('reviewed_at') and data.get('all_technical_regions_inventoried') is True
      and data.get('all_regions_actually_viewed') is True and source.get('normalization_notice'),
      'Visual regions need actual complete host inspection and an explicit transcription notice')
    regions=data.get('regions');inventory=review.get('embedded_claim_images')
    q(isinstance(regions,list) and regions and isinstance(inventory,list) and inventory,'Every original technical visual region must be inventoried')
    q(all(isinstance(r,dict) for r in regions),'Visual region entries must be objects')
    kinds={'formula','inline_math','table','chemical_structure','drawing'}
    seen={}
    for item in inventory:
        q(isinstance(item,dict) and isinstance(item.get('id'),str) and item['id'] and item['id'] not in seen
          and item.get('kind') in kinds and type(item.get('page_number')) is int,'Original visual inventory has missing or duplicate identity')
        seen[item['id']]={'kind':item['kind'],'page_number':item['page_number']}
    q(len(regions)==len(seen) and {r.get('id') for r in regions}==set(seen),'Visual inventory and transcriptions must cover exactly the same regions')
    bypage={o['page_number']:o for o in offsets};byclaim={c['number']:c for c in claims}
    try:from PIL import Image
    except ImportError:raise e.ValidationError('Visual region verification requires Pillow; artifacts remain preserved')
    for region in regions:
        q(isinstance(region,dict) and region.get('visually_verified') is True,'Every visual region requires actual host inspection')
        identity=seen[region['id']];page=region.get('page_number')
        q(region.get('kind')==identity['kind'] and page==identity['page_number'] and page in bypage,
          'Visual region identity or original claims page differs from inventory')
        rendering,pixels=renderings[page]
        q(region.get('rendering_sha256')==rendering['sha256'],'Visual crop must bind the exact reviewed original page pixels')
        start,end=region.get('page_start'),region.get('page_end');o=bypage[page]
        q(type(start) is int and type(end) is int and o['page_start']<=start<end<=o['page_start']+o['end']-o['start'],
          'Visual transcription must remain within the reviewed claims page span')
        transcription=region.get('transcription')
        q(isinstance(transcription,str) and transcription.strip() and extraction['pages'][page-1]['text'][start:end]==transcription,
          'Visual transcription must equal its exact extracted-page character interval')
        claim=byclaim.get(region.get('claim_number'));global_start=o['start']+start-o['page_start'];global_end=o['start']+end-o['page_start']
        q(claim and claim['start']<=global_start<global_end<=claim['end'],'Visual transcription must belong to the declared actual claim')
        bbox=region.get('bbox')
        q(isinstance(bbox,list) and len(bbox)==4 and all(type(x) is int for x in bbox),'Visual region bbox must contain four integer pixel coordinates')
        _,crop=load_spec(region.get('crop'),'visual region crop')
        q(crop.startswith(b'\x89PNG\r\n\x1a\n'),'Visual region crop must be a real PNG')
        try:
            with Image.open(io.BytesIO(pixels)) as full,Image.open(io.BytesIO(crop)) as cropped:
                full.load();cropped.load()
                q(0<=bbox[0]<bbox[2]<=full.width and 0<=bbox[1]<bbox[3]<=full.height,'Visual crop bbox outside original page')
                expected=full.convert('RGBA').crop(tuple(bbox));actual=cropped.convert('RGBA')
                q(actual.size==expected.size and actual.tobytes()==expected.tobytes(),'Visual crop pixels differ from the exact original page region')
        except e.ValidationError:raise
        except Exception:raise e.ValidationError('Visual region image cannot be completely decoded')
    return len(regions)



def verify(c, source, e):
    if source.get('original_document_completeness_mode') == WO_COMPLETENESS_MODE:
        return verify_wo(c, source, e)
    return verify_standard(c, source, e)
