"""Source-bound auxiliary records; no network, inference or source replacement."""
from __future__ import annotations

import collections
import datetime as dt
import hashlib
import json
from pathlib import Path
import re
import shutil
from urllib.parse import urlsplit

KINDS = ('legal_status', 'family', 'abstract_image')
LEGAL_VALUES = {'有效', '审中', '失效', '未确认', 'PCT指定期内', 'PCT指定期满'}
FAMILY_TYPES = ('simple', 'inpadoc', 'patsnap')


def records(c):
    if not c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='auxiliary_records'").fetchone():
        return []
    return [json.loads(r[0]) for r in c.execute('SELECT data FROM auxiliary_records ORDER BY id')]


def image_info(path, e):
    data = path.read_bytes()
    if data.startswith(b'\x89PNG\r\n\x1a\n'): mime, suffix = 'image/png', '.png'
    elif data.startswith(b'\xff\xd8\xff'): mime, suffix = 'image/jpeg', '.jpg'
    elif data.startswith((b'GIF87a', b'GIF89a')): mime, suffix = 'image/gif', '.gif'
    elif len(data) >= 12 and data[:4] == b'RIFF' and data[8:12] == b'WEBP': mime, suffix = 'image/webp', '.webp'
    else: raise e.ValidationError('Local auxiliary image is not a supported raster file')
    return {'sha256': hashlib.sha256(data).hexdigest(), 'mime_type': mime, 'extension': suffix, 'bytes': len(data)}


def timestamp(value, e):
    e.require(isinstance(value, str) and value.strip(), 'Auxiliary acquisition time must come from the saved source envelope')
    try:
        if re.fullmatch(r'\d{4}-\d{2}-\d{2}', value):
            return dt.datetime.combine(dt.date.fromisoformat(value), dt.time(), dt.timezone.utc).timestamp(), 'date'
        actual = dt.datetime.fromisoformat(value.replace('Z', '+00:00'))
        e.require(actual.tzinfo is not None, 'Auxiliary acquisition timestamp must include a timezone')
        return actual.timestamp(), 'timestamp'
    except ValueError as error:
        raise e.ValidationError('Invalid auxiliary acquisition time') from error


def prepare(c, p, e, cache=None):
    e.require(isinstance(p, dict) and p.get('kind') in KINDS, 'Auxiliary kind must be legal_status, family or abstract_image')
    kind = p['kind']; pn = e.number(p.get('publication_number'))
    pub = c.execute('SELECT * FROM publications WHERE id=?', (pn,)).fetchone()
    e.require(pub, 'Auxiliary publication must already be a retained search record')
    dbfile = c.execute('PRAGMA database_list').fetchone()[2]
    e.require(dbfile, 'Auxiliary source verification requires a file-backed run')
    root = Path(dbfile).resolve().parent
    relative = p.get('source_artifact')
    e.require(isinstance(relative, str) and relative and not Path(relative).is_absolute(), 'Auxiliary source artifact must be a run-relative path')
    path = (root / relative).resolve()
    e.require(path.is_relative_to(root) and path.is_file(), 'Auxiliary source artifact must exist inside the run directory')
    cache = {} if cache is None else cache
    if path not in cache:
        data = path.read_bytes()
        cache[path] = (json.loads(data.decode('utf-8-sig')), hashlib.sha256(data).hexdigest())
    original, artifact_hash = cache[path]
    if 'artifact_sha256' in p: e.require(p['artifact_sha256'] == artifact_hash, 'Auxiliary source artifact hash mismatch')

    def at_path(tokens):
        e.require(isinstance(tokens, list) and tokens, 'Auxiliary source path must be a nonempty array')
        node = original
        for token in tokens:
            if isinstance(node, dict):
                e.require(isinstance(token, str) and token in node, 'Auxiliary source path is absent')
            elif isinstance(node, list):
                e.require(isinstance(token, int) and not isinstance(token, bool) and 0 <= token < len(node), 'Auxiliary source array index is invalid')
            else: raise e.ValidationError('Auxiliary source path crosses a scalar')
            node = node[token]
        return node

    if p.get('request_tool_path') or p.get('request_arguments_path'):
        e.require(p.get('request_tool_path') and p.get('request_arguments_path') and not p.get('request_path'), 'Auxiliary request paths are incomplete or ambiguous')
        request = {'tool': at_path(p['request_tool_path']), 'arguments': at_path(p['request_arguments_path'])}
    else: request = at_path(p.get('request_path', ['source_request']))
    e.require(request == p.get('source_request') and request.get('tool') == kind, 'Auxiliary request differs from actual cached tool and arguments')
    argument = request.get('arguments', {}).get('patent_number')
    e.require(isinstance(argument, str), 'Auxiliary source must retain the actual patent_number batch string')
    requested = [e.number(x.strip()) for x in argument.split(',') if x.strip()]
    e.require(requested and pn in requested and all(re.fullmatch(r'[A-Z]{2}[A-Z0-9]+', x) for x in requested), 'Auxiliary publication was not in the actual requested batch')
    response_path = p.get('response_path'); response = at_path(response_path)
    for length in range(len(response_path) + 1):
        ancestor = original if not length else at_path(response_path[:length])
        if isinstance(ancestor, dict):
            e.require(not ancestor.get('error') and not ancestor.get('isError') and ancestor.get('success') is not False
                      and ancestor.get('status') not in (False, 'error', 'failed', 'failure')
                      and ancestor.get('error_code', 0) in (0, '0', None), 'Auxiliary source contains an outer transport, tool or provider error')
    e.require(isinstance(response, dict) and response.get('success') is True and isinstance(response.get('data'), list), 'Auxiliary source is not a successful original data array')
    index = p.get('record_index')
    e.require(isinstance(index, int) and not isinstance(index, bool) and 0 <= index < len(response['data']), 'Auxiliary record index is invalid')
    record_path = response_path + ['data', index]
    if 'record_path' in p: e.require(p['record_path'] == record_path, 'Auxiliary record path and index disagree')
    record = response['data'][index]
    e.require(isinstance(record, dict) and e.number(record.get('pn')) == pn, 'Auxiliary returned a different publication at the selected index')
    e.require(sum(isinstance(r, dict) and e.number(r.get('pn')) == pn for r in response['data']) == 1, 'Auxiliary response contains duplicate target publication records')
    acquired = original.get('acquired_at') or original.get('acquired_date')
    sort_time, precision = timestamp(acquired, e)
    if 'acquired_at' in p: e.require(p['acquired_at'] == acquired, 'Auxiliary acquisition time differs from saved source')
    normalized = {}
    if kind == 'legal_status':
        values = record.get('simple_legal_status')
        e.require(isinstance(values, list) and all(isinstance(x, str) for x in values), 'Simple legal status must be the original string array')
        known = sorted(set(values) & LEGAL_VALUES)
        normalized = {'provider_statuses': values, 'status': known[0] if len(set(values)) == 1 and len(known) == 1 else 'unknown',
                      'conflict_or_unrecognized': len(set(values)) > 1 or any(v not in LEGAL_VALUES for v in values)}
    elif kind == 'family':
        family = record.get('patent_family')
        e.require(isinstance(family, dict), 'Auxiliary family record lacks patent_family')
        for typ in FAMILY_TYPES:
            key = typ + '_family'; members = family.get(key)
            if members is None:
                normalized[typ] = {'coverage': 'unknown', 'members': [], 'family_id': family.get(key + '_id')}; continue
            e.require(isinstance(members, list), 'Family members must be the original array')
            canonical = []
            for n, member in enumerate(members):
                e.require(isinstance(member, dict), 'Family member must be an original object')
                country, doc, suffix = member.get('country'), member.get('doc_number'), member.get('kind')
                e.require(isinstance(country, str) and re.fullmatch(r'[A-Z]{2}', country)
                          and isinstance(doc, str) and doc.strip() and isinstance(suffix, str) and suffix.strip(), 'Family member needs explicit country, document number and kind')
                number = e.number(doc); number = (number if number.startswith(country) else country + number) + e.number(suffix)
                canonical.append({'publication_number': number, 'source_path': record_path + ['patent_family', key, n], 'sequence': member.get('sequence')})
            normalized[typ] = {'coverage': 'available', 'family_id': family.get(key + '_id'), 'members': canonical,
                               'source_path': record_path + ['patent_family', key]}
    else:
        drawing = record.get('abstract_drawing')
        e.require(drawing is None or isinstance(drawing, dict), 'Abstract drawing must be an original object or absent')
        drawing = drawing or {}; url = drawing.get('path')
        remote = isinstance(url, str) and urlsplit(url).scheme in ('https', 'http') and bool(urlsplit(url).hostname) and not urlsplit(url).username
        normalized = {'image_number': drawing.get('num'), 'availability': 'remote_only' if remote else 'unknown',
                      'source_url_sha256': hashlib.sha256(url.encode()).hexdigest() if isinstance(url, str) else None}
        local = p.get('local_image')
        if local is not None:
            e.require(isinstance(local, dict) and remote and local.get('source_image_url') == url
                      and local.get('source_image_number') == drawing.get('num'), 'Local image must bind the exact returned drawing URL and number')
            image_relative = local.get('relative_path')
            e.require(isinstance(image_relative, str) and not Path(image_relative).is_absolute(), 'Local image must use a run-relative path')
            image = (root / image_relative).resolve()
            e.require(image.is_relative_to(root) and image.is_file(), 'Local image must exist inside run directory')
            info = image_info(image, e)
            e.require(local.get('sha256') == info['sha256'], 'Local image source hash mismatch')
            normalized.update(availability='local', local_image={'relative_path': str(image.relative_to(root)), **info})
    item = {'id': 'aux-' + e.digest([kind, pn, str(path.relative_to(root)), artifact_hash, record_path])[:24],
            'kind': kind, 'publication_number': pn, 'application_id': pub['application_id'],
            'source_provider': p.get('source_provider') or 'Patsnap Patent Briefing', 'source_class': 'patsnap',
            'source_artifact': str(path.relative_to(root)), 'artifact_sha256': artifact_hash,
            'source_request': request, 'response_path': response_path, 'record_path': record_path,
            'record_sha256': e.digest(record), 'record_original': record, 'normalized': normalized,
            'acquired_at': acquired, 'acquired_time_precision': precision, 'observation_sort_time': sort_time,
            'provider_response_timestamp': response.get('timestamp'),
            'temporal_basis': 'Observed at acquisition; not reconstructed as of the patent-search cutoff.'}
    return item


def import_records(c, payload, e):
    result = []; cache = {}
    for p in e.as_list(payload):
        item = prepare(c, p, e, cache)
        previous = c.execute('SELECT data FROM auxiliary_records WHERE id=?', (item['id'],)).fetchone()
        e.require(not previous or json.loads(previous[0]) == item, 'Auxiliary source identity collision')
        if not previous:
            c.execute('INSERT INTO auxiliary_records VALUES(?,?,?,?,?)', (item['id'], item['kind'], item['publication_number'], item['application_id'], e.dump(item)))
        result.append({'id': item['id'], 'kind': item['kind'], 'publication_number': item['publication_number'], 'cached': bool(previous)})
    e.event(c, 'auxiliary-import', {'records': len(result)})
    return {'auxiliary_imported': result}


def public_record(item):
    # Signed remote image URLs and raw response contents remain private.
    return {key: item.get(key) for key in ('id', 'kind', 'publication_number', 'application_id', 'source_provider', 'source_class',
        'source_artifact', 'artifact_sha256', 'record_sha256', 'record_path', 'acquired_at', 'acquired_time_precision',
        'provider_response_timestamp', 'temporal_basis', 'normalized')}


def copy_local_images(c, items, output, e):
    root = Path(c.execute('PRAGMA database_list').fetchone()[2]).resolve().parent
    copied, unavailable = {}, []
    for item in items:
        local = item.get('normalized', {}).get('local_image')
        if item['kind'] != 'abstract_image' or not local: continue
        source = (root / local['relative_path']).resolve()
        if not source.is_relative_to(root) or not source.is_file():
            unavailable.append(item['id']); continue
        try: info = image_info(source, e)
        except (OSError, e.ValidationError):
            unavailable.append(item['id']); continue
        if info['sha256'] != local['sha256']:
            unavailable.append(item['id']); continue
        relative = 'aux-images/' + info['sha256'] + info['extension']
        target = output / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.exists(): shutil.copy2(source, target)
        copied[item['id']] = relative
    return copied, unavailable


def views(items):
    legal = collections.defaultdict(list)
    for item in items:
        if item['kind'] == 'legal_status': legal[item['publication_number']].append(item)
    by_publication = {}
    by_app = collections.defaultdict(list)
    for pn, values in legal.items():
        latest = max(x['observation_sort_time'] for x in values)
        # A date-only acquisition is an interval, not an invented midnight
        # observation. Keep overlapping observations if their order is unknown.
        selected = [x for x in values if x['observation_sort_time'] + (86400 - 0.000001 if x['acquired_time_precision'] == 'date' else 0) >= latest]
        statuses = {'unknown' if x['normalized']['status'] == '未确认' else x['normalized']['status'] for x in selected}
        status = next(iter(statuses)) if len(statuses) == 1 and 'unknown' not in statuses else 'unknown'
        value = {'publication_number': pn, 'status': status, 'latest_observed_at': '；'.join(sorted({x['acquired_at'] for x in selected})),
                 'observation_ids': [x['id'] for x in values], 'selected_observation_ids': [x['id'] for x in selected],
                 'observation_conflict': len(statuses) > 1 or any(x['normalized']['conflict_or_unrecognized'] for x in selected)}
        by_publication[pn] = value; by_app[selected[0]['application_id']].append(value)
    app_status = {}
    for appid, values in by_app.items():
        statuses = {x['status'] for x in values}
        app_status[appid] = {'status': next(iter(statuses)) if len(statuses) == 1 and 'unknown' not in statuses else 'unknown',
                            'conflict': len(statuses) > 1 or any(x['observation_conflict'] for x in values),
                            'publication_observations': values,
                            'temporal_basis': 'Acquisition-time observations; not status at search cutoff.'}
    return by_publication, app_status


def family_relations(items, publication_to_application):
    result = []
    for item in items:
        if item['kind'] != 'family': continue
        source = publication_to_application.get(item['publication_number'])
        if not source: continue
        for typ in FAMILY_TYPES:
            group = item['normalized'][typ]
            for member in group['members']:
                target = publication_to_application.get(member['publication_number'])
                if not target or target == source: continue
                result.append({'id': item['id'] + '-' + typ + '-' + member['publication_number'], 'source': source, 'target': target,
                               'type': 'family_' + typ, 'kind': 'fact', 'label': {'simple': '简单同族', 'inpadoc': 'INPADOC同族', 'patsnap': 'PatSnap同族'}[typ],
                               'auxiliary_source_id': item['id'], 'source_locator': member['source_path'], 'acquired_at': item['acquired_at'],
                               'family_id': group['family_id'], 'evidence_ids': [],
                               'limitations': 'Provider family assertion only; no ownership transfer, legal conclusion or text substitution inferred.'})
    return result
