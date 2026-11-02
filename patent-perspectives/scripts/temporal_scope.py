#!/usr/bin/env python3
"""Filing-date analysis cohorts; original search and identity records stay intact.

Only explicit application filing dates are considered. Priority, publication and
national-entry dates are never substituted. Multiple retained filing dates are
all evaluated, without selecting the first source or silently resolving conflicts.
"""
from __future__ import annotations
import collections
import datetime as dt
import json
import re


def _meta(c, key, default=None):
    row = c.execute('SELECT value FROM meta WHERE key=?', (key,)).fetchone()
    return json.loads(row[0]) if row else default


def strict_date(value):
    """Exact calendar dates only; do not truncate an incomplete/invalid value."""
    if value is None or value == '' or str(value).lower() in ('unknown', '0'):
        return None
    text = str(value)
    if re.fullmatch(r'\d{8}', text):
        text = text[:4] + '-' + text[4:6] + '-' + text[6:]
    if not re.fullmatch(r'\d{4}-\d{2}-\d{2}', text):
        raise ValueError('Invalid filing date: ' + str(value))
    return dt.date.fromisoformat(text).isoformat()


def validate_window(value, cutoff=None):
    if not isinstance(value, dict) or value.get('basis') != 'filing_date':
        raise ValueError('analysis_window requires basis:filing_date')
    start, through = strict_date(value.get('from')), strict_date(value.get('through'))
    if not start or not through or start > through:
        raise ValueError('analysis_window requires an ordered inclusive from/through')
    if cutoff and through > strict_date(cutoff):
        raise ValueError('analysis_window cannot extend beyond the publication cutoff')
    return {'basis': 'filing_date', 'from': start, 'through': through}


def analysis_window(c):
    run = _meta(c, 'run', {})
    window = run.get('scope', {}).get('analysis_window')
    return validate_window(window, run.get('as_of_date')) if window is not None else None


def filing_observations(c, appids=None):
    """Return source-bound values, including bad observations for explicit review.

    Canonical application dates are retained alongside each publication version
    and imported bibliography. Missing fields in one source do not negate a known
    filing date from another, but no known date or any malformed nonempty date is
    pending. Historical conflict payloads are also read so a merged canonical date
    cannot conceal an earlier retained value.
    """
    wanted = None if appids is None else set(appids)
    result = collections.defaultdict(list)

    def add(appid, raw, source, path):
        if wanted is not None and appid not in wanted:
            return
        if raw is None or raw == '' or str(raw).lower() in ('unknown', '0'):
            return
        item = {'source': source, 'path': path, 'value': raw}
        try:
            item['date'] = strict_date(raw)
        except (ValueError, TypeError):
            item['date'] = None
            item['invalid'] = True
        if item not in result[appid]:
            result[appid].append(item)

    def conflicts(appid, entries, source):
        for index, conflict in enumerate(entries):
            if conflict.get('field') != 'filing_date':
                continue
            for key in ('search_value', 'bibliography_value', 'old', 'new'):
                if key in conflict:
                    add(appid, conflict[key], source, ['conflicts', index, key])
            for key in ('values', 'search_values'):
                values = conflict.get(key, [])
                if isinstance(values, list):
                    for j, value in enumerate(values):
                        add(appid, value, source, ['conflicts', index, key, j])

    for appid, data in c.execute('SELECT id,data FROM applications ORDER BY id'):
        if wanted is not None and appid not in wanted:
            continue
        meta = json.loads(data)
        add(appid, meta.get('filing_date'), 'application:' + appid, ['filing_date'])
        conflicts(appid, meta.get('metadata_conflicts', []), 'application:' + appid)
    for pn, appid, data in c.execute('SELECT id,application_id,data FROM publications ORDER BY id'):
        if wanted is not None and appid not in wanted:
            continue
        meta = json.loads(data)
        add(appid, meta.get('filing_date'), 'publication:' + pn, ['filing_date'])
        raw = meta.get('metadata_original', {})
        for key in ('apdt', 'filing_date'):
            if key in raw:
                add(appid, raw[key], 'publication:' + pn, ['metadata_original', key])
    exists = c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='bibliographies'").fetchone()
    if exists:
        for bid, appid, data in c.execute('SELECT id,application_id,data FROM bibliographies ORDER BY id'):
            if wanted is not None and appid not in wanted:
                continue
            meta = json.loads(data)
            add(appid, meta.get('dates', {}).get('filing_date'), 'bibliography:' + bid, ['dates', 'filing_date'])
            reference = meta.get('record_original', {}).get('bibliographic_data', {}).get('application_reference', {})
            if isinstance(reference, dict):
                add(appid, reference.get('date'), 'bibliography:' + bid,
                    ['record_original', 'bibliographic_data', 'application_reference', 'date'])
            conflicts(appid, meta.get('conflicts', []), 'bibliography:' + bid)
    return dict(result)


def decide(application_id, observations, window):
    dates = sorted({x['date'] for x in observations if x.get('date')})
    invalid = [x for x in observations if x.get('invalid')]
    inside = [x for x in dates if window['from'] <= x <= window['through']]
    outside = [x for x in dates if x not in inside]
    if invalid:
        status, reason = 'pending', 'invalid_filing_date_observation'
    elif not dates:
        status, reason = 'pending', 'missing_filing_date'
    elif inside and outside:
        status, reason = 'pending', 'conflicting_dates_cross_window'
    elif inside:
        status, reason = 'included', 'all_observed_dates_in_window'
    else:
        status, reason = 'outside', 'all_observed_dates_outside_window'
    return {'application_id': application_id, 'status': status, 'reason': reason,
            'observed_dates': dates, 'date_conflict': len(dates) > 1,
            'date_for_statistics': dates[0] if len(dates) == 1 and not invalid else 'unknown',
            'observations': observations}


def window_states(c, appids=None, window=None):
    window = window or analysis_window(c)
    if window is None:
        return {}
    window = validate_window(window)
    appids = list(appids) if appids is not None else [r[0] for r in c.execute('SELECT id FROM applications ORDER BY id')]
    observations = filing_observations(c, appids)
    return {appid: decide(appid, observations.get(appid, []), window) for appid in appids}


def cohort_summary(c, identity_states, window=None, decisions=None):
    window = window or analysis_window(c)
    if window is None:
        return None
    decisions = decisions if decisions is not None else window_states(c, identity_states, window)
    cross = collections.Counter((identity_states[appid], item['status']) for appid, item in decisions.items() if appid in identity_states)
    selected = {appid for appid, item in decisions.items() if identity_states.get(appid) == 'included' and item['status'] == 'included'}
    kinds = collections.Counter(json.loads(data).get('patent_type', 'unknown') for appid, data in c.execute('SELECT id,data FROM applications') if appid in selected)
    pending = sorted(appid for appid, item in decisions.items() if identity_states.get(appid) != 'excluded' and item['status'] == 'pending')
    return {'definition': window, 'bounds_inclusive': True, 'parent_candidate_applications': len(identity_states),
            'selected_applications': len(selected), 'selected_by_type': dict(sorted(kinds.items())),
            'pending_applications': len(pending), 'pending_application_ids': pending,
            'selected_unknown_date_statistics': sum(decisions[k]['date_for_statistics'] == 'unknown' for k in selected),
            'identity_temporal_cross_counts': [{'identity_status': key[0], 'temporal_status': key[1], 'applications': value} for key, value in sorted(cross.items())],
            'outside_window_records_retained': True, 'date_basis_notice': 'Application filing dates only; not priority/publication/national-entry dates. All retained conflicting filing-date values are considered.'}
