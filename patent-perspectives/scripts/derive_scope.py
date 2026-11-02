#!/usr/bin/env python3
"""Inspect or explicitly derive a time-window run; source DB is always read-only.

Default invocation only emits review artifacts. --create performs an SQLite
backup into a NEW database in the same folder, preserving relative cache paths.
No application, publication, search page, identity review, or auxiliary row is
deleted. The child uses dynamic temporal filtering for its analysis cohort.
"""
from __future__ import annotations
import argparse
from contextlib import closing
import datetime as dt
import importlib.util
import json
import os
import shutil
from pathlib import Path
import sqlite3
import uuid
import temporal_scope


def engine_module():
    spec = importlib.util.spec_from_file_location('pp_temporal_engine', Path(__file__).with_name('patent_perspectives.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def open_readonly(path):
    conn = sqlite3.connect(Path(path).resolve().as_uri() + '?mode=ro', uri=True, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA busy_timeout=30000')
    return conn


def table_counts(c):
    names = [r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")]
    return {name: c.execute('SELECT count(*) FROM "' + name.replace('"', '""') + '"').fetchone()[0] for name in names}


def inspect(c, window, engine=None):
    engine = engine or engine_module()
    run = engine.run_info(c)
    window = temporal_scope.validate_window(window, run['as_of_date'])
    identity = engine.population_state(c)
    decisions = temporal_scope.window_states(c, identity, window)
    summary = temporal_scope.cohort_summary(c, identity, window, decisions)
    summary.update({'parent_run_id': run['run_id'], 'publication_cutoff': run['as_of_date'],
                    'parent_table_counts': table_counts(c), 'inspection_only': True})
    anomalies = [{**item, 'identity_status': identity[appid]} for appid, item in decisions.items()
                 if item['status'] == 'pending' or item['date_conflict']]
    return summary, anomalies, decisions


def derive(parent, output, window, run_id=None, engine=None):
    engine = engine or engine_module()
    parent, output = Path(parent).resolve(), Path(output).resolve()
    if output == parent or output.parent != parent.parent:
        raise ValueError('Child database must be a new filename in the parent run directory; relative caches must remain valid')
    if output.exists():
        raise ValueError('Refusing to overwrite an existing child database')
    temporary = output.with_name(output.name + '.deriving-' + uuid.uuid4().hex)
    try:
        with closing(open_readonly(parent)) as source:
            source.execute('BEGIN')
            source.execute('SELECT count(*) FROM meta').fetchone()  # Freeze one SQLite snapshot, including WAL.
            with closing(sqlite3.connect(str(temporary))) as child:
                child.row_factory = sqlite3.Row
                source.backup(child)
                parent_run = engine.run_info(child)
                if parent_run.get('scope', {}).get('selection') is not None:
                    raise ValueError('Derive the filing-date window from the unselected parent snapshot, then freeze latest-N; do not carry a prior selection into a different run/window')
                summary, anomalies, decisions = inspect(child, window, engine)
                copied_counts = table_counts(child)
                if copied_counts != summary['parent_table_counts']:
                    raise ValueError('Backup row-count verification failed')
                stamp = dt.datetime.now(dt.timezone.utc).isoformat()
                derived_run = json.loads(json.dumps(parent_run))
                derived_run.update({'run_id': run_id or 'pp-' + uuid.uuid4().hex[:16], 'parent_run_id': parent_run['run_id'],
                                    'created_at': stamp, 'status': 'collecting'})
                if derived_run['run_id'] == parent_run['run_id']:
                    raise ValueError('Derived run_id must differ from parent_run_id')
                derived_run['scope']['analysis_window'] = summary['definition']
                derived_run['scope']['mode'] = 'window_analysis'
                derived_run['derivation'] = {'parent_database': parent.name, 'method': 'sqlite_backup_complete_database',
                    'source_snapshot_at': stamp, 'parent_table_counts': copied_counts,
                    'all_parent_records_retained': True, 'relative_cache_root_unchanged': True,
                    'parent_scope': parent_run['scope'], 'initial_cohort': summary,
                    'notice': 'First-stage filing-date cohort; parent historical records and search totals remain retained and independently reported. Child completion covers only this window.'}
                engine.set_meta(child, 'run', derived_run)
                engine.set_meta(child, 'temporal_scope_initial_summary', summary)
                engine.event(child, 'derive-analysis-window', {'parent_run_id': parent_run['run_id'], 'run_id': derived_run['run_id'], 'analysis_window': summary['definition']})
                child.commit()
                check = child.execute('PRAGMA quick_check').fetchone()[0]
                if check != 'ok':
                    raise ValueError('Derived database quick_check: ' + str(check))
        if output.exists():
            raise ValueError('Output appeared during derivation; refusing overwrite')
        # Exclusive creation also works in sandboxes that forbid hard links.
        # SQLite is closed and verified before the finished backup is copied.
        with output.open('xb') as final, temporary.open('rb') as finished:
            shutil.copyfileobj(finished, final)
            final.flush()
            os.fsync(final.fileno())
        temporary.unlink()
        return {'output': str(output), 'run_id': derived_run['run_id'], 'parent_run_id': parent_run['run_id'],
                'cohort': summary, 'anomalies': len(anomalies), 'parent_database_changed': False}
    finally:
        if temporary.exists():
            temporary.unlink()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--parent', required=True)
    parser.add_argument('--from', dest='start', required=True)
    parser.add_argument('--through', required=True)
    parser.add_argument('--report-dir', required=True)
    parser.add_argument('--output')
    parser.add_argument('--run-id')
    parser.add_argument('--create', action='store_true', help='Explicitly create the new child; default is inspection only')
    args = parser.parse_args()
    window = {'basis': 'filing_date', 'from': args.start, 'through': args.through}
    report = Path(args.report_dir)
    report.mkdir(parents=True, exist_ok=True)
    with closing(open_readonly(args.parent)) as conn:
        summary, anomalies, decisions = inspect(conn, window)
    (report / 'cohort-summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
    (report / 'date-anomalies.json').write_text(json.dumps(anomalies, ensure_ascii=False, indent=2), encoding='utf-8')
    with (report / 'temporal-decisions.jsonl').open('w', encoding='utf-8') as handle:
        for appid in sorted(decisions):
            handle.write(json.dumps(decisions[appid], ensure_ascii=False, separators=(',', ':')) + '\n')
    if args.create:
        if not args.output:
            parser.error('--create requires --output')
        result = derive(args.parent, args.output, window, args.run_id)
        (report / 'derivation.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
