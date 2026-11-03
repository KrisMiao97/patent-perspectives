#!/usr/bin/env python3
"""Resolve evidence selected in a host's full-text semantic review.

The host reads one complete patent source and its tail, selects evidence, and authors all
technical findings, modules, tags and limitations. This standard-library helper
only resolves original spans and checks the input contract. It performs no
classification, summarization, inference, model call or network request.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import re
import sqlite3
from pathlib import Path


def load_engine():
    path = Path(__file__).with_name('patent_perspectives.py')
    spec = importlib.util.spec_from_file_location('pp_review_engine', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def string_list(value):
    return isinstance(value, list) and all(isinstance(x, str) and x.strip() for x in value)


def integer(value):
    return isinstance(value, int) and not isinstance(value, bool)


def validate_whole_document_review(value, doc, require):
    """Validate a source-bound reading attestation, not semantic understanding.

    This pure helper is also used by the core importer. It never loads the engine,
    partitions text, or changes legacy chunk records.
    """
    require(isinstance(value, dict), 'Whole-document review must be an object')
    text = doc['text']
    require(value.get('document_id') == doc['id'], 'Whole-document review document_id differs from selected source')
    require(value.get('source_text_hash') == doc['text_hash']
            and hashlib.sha256(text.encode('utf-8')).hexdigest() == doc['text_hash'],
            'Whole-document review source_text_hash differs from actual source')
    require(value.get('complete') is True, 'Whole-document review must explicitly confirm complete reading')
    mode = value.get('reading_mode')
    require(mode in ('whole', 'continuous'), 'Whole-document reading_mode must be whole or continuous')
    require(isinstance(value.get('capacity_basis'), str) and value['capacity_basis'].strip(),
            'Whole-document review needs a host-authored capacity_basis')
    result = {'document_id': doc['id'], 'source_text_hash': doc['text_hash'],
              'reading_mode': mode, 'complete': True, 'capacity_basis': value['capacity_basis'],
              'source_characters': len(text)}
    if mode == 'whole':
        require(not value.get('read_regions'), 'Whole reading must not contain partial read_regions')
    else:
        require(isinstance(value.get('reason'), str) and value['reason'].strip(),
                'Continuous whole-document reading requires a reason')
        regions = value.get('read_regions')
        require(isinstance(regions, list) and regions, 'Continuous reading requires actual read_regions')
        end_read, previous_start, checked = 0, -1, []
        for region in regions:
            require(isinstance(region, dict), 'Continuous read region must be an object')
            start, end = region.get('start'), region.get('end')
            require(integer(start) and integer(end) and 0 <= start < end <= len(text),
                    'Continuous read regions must be valid Unicode character indices')
            require(start >= previous_start and start <= end_read and end > end_read,
                    'Continuous read regions must cover the source in order without gaps or duplicate regions')
            checked.append({'start': start, 'end': end})
            end_read, previous_start = end, start
        require(end_read == len(text), 'Continuous read regions must cover the complete source through its end')
        result.update(reason=value['reason'], read_regions=checked)
    return result


def validate_tail_check(value, doc, require, description_intervals):
    """Validate exact ending and optional final structural identifier."""
    text, source = doc['text'], json.loads(doc['data'])
    require(isinstance(value, dict) and value.get('complete') is True
            and isinstance(value.get('quote'), str) and len(value['quote'].strip()) >= 12
            and text.rstrip().endswith(value['quote'].rstrip()),
            'Host must verify the actual final text; incomplete or false tail cannot complete review')
    if 'paragraph_number' in value:
        paragraphs = description_intervals(text) if doc['document_type'] == 'description' else {}
        require(doc['document_type'] == 'description' and paragraphs
                and integer(value['paragraph_number']) and value['paragraph_number'] == next(reversed(paragraphs)),
                'Tail paragraph does not match the actual final paragraph')
    if 'claim_number' in value:
        require(doc['document_type'] == 'claims' and source.get('claims')
                and integer(value['claim_number']) and value['claim_number'] == source['claims'][-1]['number'],
                'Tail claim does not match the actual final claim')
    return dict(value)


def paragraph_intervals(text, e):
    return e.description_intervals(text)


def explicit_locator(doc, source, paragraphs, locator, start, end, e):
    """Do not label an exact span as a different paragraph or claim."""
    e.require(isinstance(locator, dict) and locator, 'Explicit original span needs an object locator')
    if set(locator) == {'paragraph'}:
        raw = locator['paragraph']
        e.require(integer(raw) or isinstance(raw, str) and re.fullmatch(r'\d{4,}', raw),
                  'Paragraph locator must contain an integer or a padded paragraph number')
        number = int(raw)
        interval = paragraphs.get(number)
        e.require(doc['document_type'] == 'description' and interval
                  and interval[0] <= start < end <= interval[1],
                  'Explicit evidence span does not belong to specified paragraph')
        return {'paragraph': str(number).zfill(4)}
    if set(locator) == {'claim_number'}:
        number = locator['claim_number']
        e.require(integer(number), 'Claim locator number must be an integer')
        block = next((b for b in source.get('claims', []) if b['number'] == number), None)
        e.require(doc['document_type'] == 'claims' and block
                  and block['start'] <= start < end <= block['end'],
                  'Explicit evidence span does not belong to specified claim')
        return {'claim_number': number}
    e.require(doc['document_type'] == 'description' and locator == {'source_span': True},
              'Unnumbered description spans must use locator {source_span:true}; unverified page/paragraph labels are not accepted')
    return locator


def selected_span(doc, choice, e):
    """Resolve only the host-selected original paragraph, claim or exact span."""
    source=json.loads(doc['data']);text=doc['text']
    paragraphs=paragraph_intervals(text,e) if doc['document_type']=='description' else {}
    modes=int('paragraph_number' in choice)+int('claim_number' in choice)+int('start' in choice or 'end' in choice)
    e.require(modes==1,'Choose exactly one evidence selector: paragraph, claim or explicit span')
    if 'paragraph_number' in choice:
        number=choice['paragraph_number']
        e.require(integer(number) and doc['document_type']=='description' and number in paragraphs,
                  'Source paragraph absent or wrong text type')
        e.require('locator' not in choice,'Numbered selection derives its locator; do not override it')
        start,end=paragraphs[number];locator={'paragraph':str(number).zfill(4)}
    elif 'claim_number' in choice:
        number=choice['claim_number']
        e.require(integer(number) and doc['document_type']=='claims','Source claim absent or wrong text type')
        block=next((b for b in source.get('claims',[]) if b['number']==number),None)
        e.require(block,'Source claim absent or wrong text type')
        e.require('locator' not in choice,'Numbered selection derives its locator; do not override it')
        start,end=block['start'],block['end'];locator={'claim_number':number}
    else:
        start,end=choice.get('start'),choice.get('end')
        e.require(integer(start) and integer(end) and 0<=start<end<=len(text),
                  'Explicit original span start/end must be valid Unicode character indices')
        locator=explicit_locator(doc,source,paragraphs,choice.get('locator'),start,end,e)
    while start<end and text[start].isspace():start+=1
    while end>start and text[end-1].isspace():end-=1
    if 'quote' in choice:
        quote=choice['quote']
        e.require(isinstance(quote,str) and quote.strip(),'Optional quote must be a nonempty original string')
        positions=[m.start()+start for m in re.finditer(re.escape(quote),text[start:end])]
        e.require(len(positions)==1,'Optional quote must occur exactly once inside selected source interval')
        start,end=positions[0],positions[0]+len(quote)
    e.require(start<end,'Empty evidence span')
    return start,end,locator


def build(c, host, e):
    e.require(isinstance(host, dict), 'Host review must be an object')
    e.require(isinstance(host.get('application_id'), str) and isinstance(host.get('document_id'), str),
              'Host must retain exported application_id and document_id')
    doc = c.execute('SELECT * FROM documents WHERE id=?', (host['document_id'],)).fetchone()
    e.require(doc and doc['application_id'] == host['application_id'], 'Review source application/document mismatch')
    source = json.loads(doc['data'])
    text = doc['text']
    e.require(e.document_is_eligible(c, doc), 'Review requires qualified complete original text without a source rejection')
    if 'source_text_hash' in host:
        e.require(host['source_text_hash'] == doc['text_hash'], 'Host source text hash differs from selected version')
    expected = [r[0] for r in c.execute('SELECT id FROM chunks WHERE document_id=? ORDER BY ordinal', (doc['id'],))]
    scope = e.run_info(c).get('scope', {})
    strict = not scope.get('synthetic', False) or scope.get('require_whole_patent_review') is True
    whole_review = None
    if 'whole_document_review' in host:
        whole_review = validate_whole_document_review(host['whole_document_review'], doc, e.require)
        e.require(expected, 'Whole source has no stored compatibility coverage spans')
        read = expected
        if 'read_chunk_ids' in host:
            declared = host['read_chunk_ids']
            e.require(string_list(declared) and len(declared) == len(set(declared)) and set(declared) == set(expected),
                      'Legacy read_chunk_ids conflict with complete whole-document review')
    else:
        e.require(not strict, 'Whole-document review is required for this run; legacy chunk attestations alone are insufficient')
        read = host.get('read_chunk_ids')
        e.require(string_list(read) and len(read) == len(set(read)) and set(read) == set(expected) and expected,
                  'Host must attest reading every actual source chunk exactly once')
    author = host.get('analysis_author')
    e.require(not strict or isinstance(author, str) and author.strip(), 'Whole-patent analysis requires analysis_author')
    if author is not None:
        e.require(isinstance(author, str) and author.strip(), 'analysis_author must be a nonempty string')
    tail = validate_tail_check(host.get('tail_check'), doc, e.require, e.description_intervals)
    declared=host.get('support_documents',[])
    e.require(isinstance(declared,list),'support_documents must be an array')
    compact_support=[]
    for item in declared:
        e.require(isinstance(item,dict) and set(item)<={'document_id','source_text_hash','read_regions'},
                  'Supporting host input accepts document_id, optional source_text_hash and read_regions')
        support=c.execute('SELECT * FROM documents WHERE id=?',(item.get('document_id'),)).fetchone()
        e.require(support,'Supporting source absent')
        regions=item.get('read_regions')
        e.require(isinstance(regions,list) and regions,'Supporting description needs actual reviewed read_regions')
        resolved=[]
        for region in regions:
            e.require(isinstance(region,dict) and region.get('reviewed') is True
                      and set(region)<={'paragraph_number','start','end','locator','reviewed'},
                      'Supporting region needs an actual paragraph/span and explicit reviewed=true')
            start,end,locator=selected_span(support,region,e)
            resolved.append({'start':start,'end':end,'locator':locator,'reviewed':True})
        compact_support.append({**item,'read_regions':resolved})
    supports,sources=e.validate_support_documents(c,doc,compact_support)
    support_by_id={s['document_id']:s for s in supports}
    choices = host.get('evidence')
    e.require(isinstance(choices, list) and choices, 'Host must select original evidence in an array')
    spans, evidence = {}, []
    for choice in choices:
        e.require(isinstance(choice, dict), 'Each evidence selection must be an object')
        e.require(set(choice) <= {'key', 'document_id', 'paragraph_number', 'claim_number', 'start', 'end', 'locator', 'quote'},
                  'Unknown evidence selection field')
        key = choice.get('key')
        e.require(isinstance(key, str) and re.fullmatch(r'[A-Za-z0-9_-]+', key) and key not in spans,
                  'Unique compact evidence key required')
        sid=choice.get('document_id',doc['id'])
        e.require(sid in sources,'Evidence document_id is not the primary or a declared supporting source')
        actual=sources[sid]
        start,end,locator=selected_span(actual,choice,e)
        eid = 'ev-' + actual['publication_id'] + '-' + actual['id'][-8:] + '-' + key
        original = {'id': eid, 'document_id':sid,'quote':actual['text'][start:end], 'start': start, 'end': end, 'locator': locator}
        ev=e.make_evidence(c, actual, original)
        if sid!=doc['id']:e.require(e.evidence_in_read_regions(ev,support_by_id[sid]),'Supporting evidence lies outside actually reviewed regions')
        spans[key] = eid
        evidence.append(original)

    def finding(value):
        e.require(isinstance(value, dict) and isinstance(value.get('text'), str) and value['text'].strip(),
                  'Host-authored finding text required')
        e.require(value['text'].strip().casefold() not in {'unknown', 'n/a', 'none', 'null', '未知', '未披露', '不详', '?'},
                  'Unknown/undisclosed fields use []; explain the gap in limitations')
        e.require('evidence_ids' not in value, 'Compact findings use evidence keys, not prebuilt evidence_ids')
        keys = value.get('evidence')
        e.require(string_list(keys) and keys and len(keys) == len(set(keys)) and all(k in spans for k in keys),
                  'Finding references absent, duplicated or invalid selected evidence')
        result = {k: v for k, v in value.items() if k != 'evidence'}
        result.setdefault('kind', 'disclosed')
        if result['kind'] == 'inference':
            conditions = result.get('conditions')
            e.require(isinstance(result.get('basis'), str) and result['basis'].strip()
                      and (isinstance(conditions, str) and conditions.strip() or string_list(conditions) and conditions),
                      'Host-authored inference requires explicit basis and conditions')
        result['evidence_ids'] = [spans[k] for k in keys]
        e.validate_finding(result, set(spans.values()), 'host review')
        return result

    fields = host.get('fields')
    e.require(isinstance(fields, dict) and set(fields) == set(e.FIELDS),
              'Host must address exactly all eight fields; undisclosed fields use []')
    e.require(all(isinstance(values, list) for values in fields.values()),
              'Every technical field must be an array; unknown/undisclosed fields use []')
    converted = {key: [finding(value) for value in values] for key, values in fields.items()}
    e.require(isinstance(host.get('primary_module'), str) and host['primary_module'].strip(), 'Host must assign primary module')
    tags = host.get('tags', [])
    limitations = host.get('limitations', [])
    e.require(string_list(tags) and len(tags) == len(set(tags)), 'Host tags must be an array of unique nonempty strings')
    e.require(string_list(limitations), 'Host limitations must be an array of nonempty strings')
    e.require(not any(not values for values in converted.values()) or limitations,
              'Explain undisclosed/omitted technical fields in host-authored limitations')
    analysis = {'application_id': host['application_id'], 'document_id': doc['id'],
                'primary_module': host['primary_module'], 'tags': tags,
                'summary': finding(host.get('summary')), 'fields': converted, 'evidence': evidence,
                'completed_chunk_ids': read, 'limitations': limitations, 'tail_check': tail,
                'host_review_method': 'Full primary original text read by host; optional same-publication description regions read only as needed; selected spans materialized mechanically'}
    if whole_review:analysis['whole_document_review']=whole_review
    if author is not None:analysis['analysis_author']=author
    if supports:analysis['support_documents']=supports
    review = {'application_id': host['application_id'], 'document_id': doc['id'],
              'publication_number': doc['publication_id'], 'read_chunk_ids': read, 'tail_check': tail,
              'source_text_hash': doc['text_hash'], 'source_characters': len(text),
              'selected_evidence': len(evidence), 'fields_without_findings': [key for key, values in converted.items() if not values],
              'status': 'host_review_materialized_pending_formal_import',
              'semantic_decisions_authored_by_host': True,
              'support_documents':supports,
              'reading_attestation_limit': 'Whole-document, coverage and tail checks validate source identity and host attestations; they cannot prove semantic understanding or replace independent review.'}
    if whole_review:review['whole_document_review']=whole_review
    if author is not None:review['analysis_author']=author
    return analysis, review


def atomic_json(path, payload):
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')
    temporary.replace(path)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--db', required=True)
    parser.add_argument('--input', required=True)
    parser.add_argument('--outdir', required=True)
    parser.add_argument('--validate-import', action='store_true', help='Validate formal import in a disposable memory backup; never write the run DB')
    args = parser.parse_args()
    e = load_engine()
    source = sqlite3.connect(Path(args.db).resolve().as_uri() + '?mode=ro', uri=True)
    source.row_factory = sqlite3.Row
    memory = None
    try:
        hosts = e.as_list(e.read_input(args.input))
        e.require(hosts, 'Host review input must not be empty')
        built = [build(source, host, e) for host in hosts]
        e.require(len({a['application_id'] for a, _ in built}) == len(built), 'A materialization batch must contain one selected version per application')
        e.require(len({r['publication_number'] for _, r in built}) == len(built), 'Duplicate publication would overwrite a checkpoint')
        if args.validate_import:
            memory = sqlite3.connect(':memory:')
            memory.row_factory = sqlite3.Row
            source.backup(memory)
            for analysis, review in built:
                e.import_analysis(memory, analysis)
                review['import_validation'] = 'passed_in_memory'
                review['status'] = 'host_review_materialized_import_validated_in_memory'
        out = Path(args.outdir)
        out.mkdir(parents=True, exist_ok=True)
        for analysis, review in built:
            pn = review['publication_number']
            atomic_json(out / (pn + '-analysis.json'), [analysis])
            atomic_json(out / (pn + '-review.json'), review)
        atomic_json(out / 'analyses-ready.json', [analysis for analysis, _ in built])
        print(json.dumps({'materialized': [{'pn': review['publication_number'], 'evidence': len(analysis['evidence']),
                                           'chunks': len(analysis['completed_chunk_ids'])} for analysis, review in built],
                          'import_validation': 'passed_in_memory' if args.validate_import else 'not_requested',
                          'run_database_changed': False, 'network_calls': 0}, ensure_ascii=False, indent=2))
    except (e.ValidationError, json.JSONDecodeError) as error:
        parser.error(str(error))
    finally:
        if memory is not None:
            memory.close()
        source.close()


if __name__ == '__main__':
    main()
