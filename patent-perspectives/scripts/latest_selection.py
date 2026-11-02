"""Immutable, reproducibly ranked latest-N independent technical applications.

Selection follows reviewed identity and an optional filing-date window. Text,
analysis availability, and reading length are deliberately absent from ranking.
"""
from __future__ import annotations
import datetime as dt
import json

KIND = 'latest_technical_applications'
TABLE = 'application_selections'


def definition(count, e):
    e.require(type(count) is int and count > 0, 'Latest selection count must be a positive integer')
    return {'kind': KIND, 'count': count, 'date_field': 'filing_date',
            'date_order': 'desc', 'tie_break': 'application_id_asc'}


def current(c, e):
    return e.run_info(c).get('scope', {}).get('selection')


def snapshot(c, e):
    """Recompute the complete eligible pool, independent of a stored selection."""
    run = e.run_info(c)
    queries = list(c.execute('SELECT * FROM queries'))
    e.require(queries, 'Latest selection requires a retrieved candidate population')
    for row in queries:
        observed = c.execute('SELECT count(*) FROM query_results WHERE query_id=?', (row['id'],)).fetchone()[0]
        e.require(row['complete'] and row['expected_count'] == row['observed_count'] == observed,
                  'Latest selection requires complete reconciled source queries: ' + row['id'])
    contract = e.get_meta(c, 'query_plan_contract', {})
    if run['scope'].get('require_query_sets', not run['scope'].get('synthetic', False)):
        e.require(contract and contract.get('required_query_sets'), 'Latest selection requires its frozen logical query contract')
        stored = {x['id']: x for x in e.rows_data(c, 'query_sets')}
        for spec in contract['required_query_sets']:
            actual = stored.get(spec['id'])
            e.require(actual and all(actual.get(k) == spec.get(k) for k in ('id', 'entity_id', 'kind', 'query_text')),
                      'Latest selection query contract is missing or changed: ' + spec['id'])
            e.query_set_evaluate(c, actual)
    identity = e.population_state(c)
    temporal = e.temporal_scope_module()
    window = temporal.analysis_window(c)
    dates = temporal.filing_observations(c, identity)
    decisions = temporal.window_states(c, identity, window) if window else {}
    base = e.unselected_source_records(c)
    registration = e.registration_state(c, base)
    e.require(not registration['errors'], 'Latest selection has invalid national-registration mappings: ' + e.dump(registration['errors']))
    members = {x['member_application_id']: x['canonical_filing_application_id'] for x in registration['active']}
    candidates = []
    for app in sorted(e.candidate_applications(c), key=lambda x: x['id']):
        appid = app['id']; state = identity.get(appid)
        if state == 'excluded' or app.get('patent_type') == 'design':
            continue
        if decisions and decisions[appid]['status'] == 'outside':
            continue
        e.require(state == 'included', 'Latest selection candidate identity is pending: ' + appid)
        e.require(app.get('patent_type') in ('invention', 'utility_model'),
                  'Latest selection candidate patent type is unresolved: ' + appid)
        if decisions:
            e.require(decisions[appid]['status'] == 'included',
                      'Latest selection candidate filing-date window is pending: ' + appid)
        values = dates.get(appid, [])
        days = sorted({v['date'] for v in values if v.get('date')})
        e.require(len(days) == 1 and not any(v.get('invalid') for v in values),
                  'Latest selection requires one unambiguous filing date for every candidate: ' + appid)
        e.require(days[0] <= run['as_of_date'], 'Candidate filing date follows the frozen public cutoff: ' + appid)
        if appid in members:
            continue
        conflicts = app.get('metadata_conflicts', []) + e.bibliography_conflicts(c, appid)
        e.require(not any(x.get('field') == 'patent_type' for x in conflicts),
                  'Latest selection candidate patent-type observations conflict: ' + appid)
        candidates.append({'application_id': appid, 'filing_date': days[0], 'patent_type': app['patent_type'],
            'publication_ids': [r[0] for r in c.execute('SELECT id FROM publications WHERE application_id=? ORDER BY id', (appid,))],
            'filing_observations': sorted(values, key=e.dump)})
    candidates.sort(key=lambda x: (-dt.date.fromisoformat(x['filing_date']).toordinal(), x['application_id']))
    result = {'publication_cutoff': run['as_of_date'], 'analysis_window': window,
              'ranked_candidates': candidates,
              'registration_members': [{'mapping_id': x['id'], 'proof_hash': x['proof_hash'],
                  'member_application_id': x['member_application_id'],
                  'canonical_filing_application_id': x['canonical_filing_application_id']}
                  for x in sorted(registration['active'], key=lambda x: x['id'])]}
    return result


def plan(c, count, e):
    d = definition(count, e); source = snapshot(c, e); ranked = source['ranked_candidates']
    e.require(len(ranked) >= count, 'Not enough eligible independent technical applications: '
              + str(len(ranked)) + ' available, ' + str(count) + ' requested')
    chosen = ranked[:count]; oldest = chosen[-1]['filing_date']
    boundary = {'filing_date': oldest,
        'candidate_count_on_day': sum(x['filing_date'] == oldest for x in ranked),
        'selected_count_on_day': sum(x['filing_date'] == oldest for x in chosen),
        'last_selected_application_id': chosen[-1]['application_id'],
        'first_excluded_application_id': ranked[count]['application_id'] if len(ranked) > count and ranked[count]['filing_date'] == oldest else None}
    return {**d, 'publication_cutoff': source['publication_cutoff'], 'analysis_window': source['analysis_window'],
            'candidate_count': len(ranked), 'candidate_snapshot_hash': e.digest(source),
            'candidate_snapshot': source, 'selected_application_ids': [x['application_id'] for x in chosen],
            'latest_filing_date': chosen[0]['filing_date'], 'oldest_filing_date': oldest,
            'boundary_tie': boundary}


def public_summary(manifest):
    return {key: manifest[key] for key in ('kind', 'count', 'date_field', 'date_order', 'tie_break',
            'candidate_count', 'latest_filing_date', 'oldest_filing_date', 'boundary_tie',
            'manifest_id', 'manifest_sha256')}


def freeze(c, count, parent_run_id, child_run_id, frozen_at, e):
    """Append a new immutable manifest; caller commits only in the child backup."""
    value = {**plan(c, count, e), 'schema_version': 1, 'parent_run_id': parent_run_id,
             'run_id': child_run_id, 'frozen_at': frozen_at}
    value['manifest_id'] = 'latest-' + e.digest(value)[:24]
    value['manifest_sha256'] = e.digest(value)
    c.execute('CREATE TABLE IF NOT EXISTS ' + TABLE + '(id TEXT PRIMARY KEY,data TEXT NOT NULL)')
    c.execute("CREATE TRIGGER IF NOT EXISTS application_selections_no_update BEFORE UPDATE ON " + TABLE
              + " BEGIN SELECT RAISE(ABORT,'Frozen application selections are immutable'); END")
    c.execute("CREATE TRIGGER IF NOT EXISTS application_selections_no_delete BEFORE DELETE ON " + TABLE
              + " BEGIN SELECT RAISE(ABORT,'Frozen application selections are immutable'); END")
    c.execute('INSERT INTO ' + TABLE + ' VALUES(?,?)', (value['manifest_id'], e.dump(value)))
    return value


def validate(c, e, records=None):
    selection = current(c, e)
    if selection is None:
        return None
    e.require(isinstance(selection, dict) and selection.get('kind') == KIND, 'Unsupported analysis selection')
    e.require(c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (TABLE,)).fetchone(),
              'Frozen latest-selection manifest is missing')
    row = c.execute('SELECT data FROM ' + TABLE + ' WHERE id=?', (selection.get('manifest_id'),)).fetchone()
    e.require(row, 'Frozen latest-selection membership is missing')
    value = json.loads(row[0]); sha = value.get('manifest_sha256')
    e.require(value.get('schema_version') == 1 and sha == e.digest({k: v for k, v in value.items() if k != 'manifest_sha256'}),
              'Frozen latest-selection manifest hash changed')
    run = e.run_info(c)
    e.require(value.get('run_id') == run['run_id'] and value.get('parent_run_id') == run.get('parent_run_id'),
              'Frozen latest-selection parent/child identity differs')
    e.require(selection == public_summary(value), 'Public latest-selection definition differs from its immutable manifest')
    expected = plan(c, value['count'], e)
    e.require(all(value.get(key) == item for key, item in expected.items()),
              'Latest-selection membership no longer equals the complete frozen candidate ranking')
    return value


def filter_records(c, records, e):
    value = validate(c, e, records)
    if value is None:
        return records
    selected = set(value['selected_application_ids'])
    retained_members = {x['member_application_id'] for x in value['candidate_snapshot']['registration_members']
                        if x['canonical_filing_application_id'] in selected}
    return [a for a in records if a['id'] in selected or a['id'] in retained_members]
