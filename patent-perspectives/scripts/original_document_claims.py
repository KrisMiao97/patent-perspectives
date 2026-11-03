"""Verify complete original-publication claims hosted by a disclosed PDF mirror.

The host extracts and visually reads the PDF. This standard-library verifier
checks immutable artifacts, exact page spans and that explicit review. It does
not treat mirror HTML, automatic translations or family similarity as evidence.
"""
import hashlib
import json
import re
from pathlib import Path
from urllib.parse import urlsplit

LABEL = '专利局原始公报的第三方托管副本'


def verify(c, source, e):
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

    def artifact(key):
        spec = proof.get(key)
        q(isinstance(spec, dict), 'Missing original PDF artifact: ' + key)
        rel = spec.get('artifact')
        q(isinstance(rel, str) and rel and not Path(rel).is_absolute(), 'Original PDF artifact must be relative to run')
        path = (root / rel).resolve()
        q(path.is_relative_to(root) and path.is_file(), 'Original PDF artifact outside or absent from run')
        raw = path.read_bytes()
        q(re.fullmatch(r'[a-f0-9]{64}', str(spec.get('sha256', '')))
          and hashlib.sha256(raw).hexdigest() == spec['sha256'], 'Original PDF artifact hash mismatch: ' + key)
        return path, raw

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
      and review.get('embedded_claim_images') == [] and review.get('machine_translation_used') is False,
      'Original PDF claims have missing, unreviewed, image or translated content')

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
    for rendering in renderings:
        q(rendering.get('pdf_sha256') == pdfsha and rendering.get('visually_reviewed') is True,
          'Original page rendering must bind the exact PDF and actual review')
        proof['_rendering'] = rendering
        try:
            _, pixels = artifact('_rendering')
        finally:
            proof.pop('_rendering', None)
        q(pixels.startswith(b'\x89PNG\r\n\x1a\n'), 'Original PDF reviewed rendering must be PNG')
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
