#!/usr/bin/env python3
"""Inspect or derive latest-N ranked technical applications; parent is read-only.

No rows are deleted. --create backs up all rows into a new same-folder database,
appends an immutable ranking manifest, and gives the child its own run identity.
"""
from __future__ import annotations
import argparse
from contextlib import closing
import datetime as dt
import json
import os
from pathlib import Path
import shutil
import sqlite3
import uuid
import derive_scope


def inspect(c, count, engine=None):
    engine = engine or derive_scope.engine_module()
    return engine.latest_selection_module().plan(c, count, engine.latest_selection_context())


def derive(parent, output, count, run_id=None, engine=None):
    engine = engine or derive_scope.engine_module()
    parent, output = Path(parent).resolve(), Path(output).resolve()
    if parent == output or parent.parent != output.parent:
        raise ValueError('Latest child must use a new filename in the parent run directory')
    if output.exists():
        raise ValueError('Refusing to overwrite an existing latest-selection run; resume that database directly')
    temporary = output.with_name(output.name + '.deriving-' + uuid.uuid4().hex)
    try:
        with closing(derive_scope.open_readonly(parent)) as source:
            source.execute('BEGIN');source.execute('SELECT count(*) FROM meta').fetchone()
            with closing(sqlite3.connect(str(temporary))) as child:
                child.row_factory = sqlite3.Row
                source.backup(child)
                parent_run = engine.run_info(child)
                original_counts = derive_scope.table_counts(child)
                stamp = dt.datetime.now(dt.timezone.utc).isoformat()
                child_id = run_id or 'pp-' + uuid.uuid4().hex[:16]
                if child_id == parent_run['run_id']:
                    raise ValueError('Latest child run ID must differ from its parent')
                manifest = engine.latest_selection_module().freeze(child, count, parent_run['run_id'], child_id,
                                                                   stamp, engine.latest_selection_context())
                after = derive_scope.table_counts(child)
                if any(after.get(key) != value for key, value in original_counts.items() if key != 'application_selections'):
                    raise ValueError('Latest-selection backup changed parent source rows')
                run = json.loads(json.dumps(parent_run))
                run.update({'run_id': child_id, 'parent_run_id': parent_run['run_id'], 'created_at': stamp,
                            'status': 'collecting'})
                run['scope']['selection'] = engine.latest_selection_module().public_summary(manifest)
                run['scope']['mode'] = 'latest_technical_analysis'
                run['derivation'] = {'parent_database': parent.name, 'method': 'sqlite_backup_complete_database',
                    'source_snapshot_at': stamp, 'parent_table_counts': original_counts,
                    'all_parent_records_retained': True, 'relative_cache_root_unchanged': True,
                    'parent_scope': parent_run['scope'], 'selection_manifest_id': manifest['manifest_id'],
                    'notice': 'Completion covers only the ranked frozen technical selection; parent search, designs and historical evidence remain stored.'}
                engine.set_meta(child, 'run', run)
                engine.event(child, 'derive-latest-technical-selection', {'parent_run_id': parent_run['run_id'],
                    'run_id': child_id, 'selection': run['scope']['selection']})
                engine.latest_selection_module().validate(child, engine.latest_selection_context())
                child.commit()
                if child.execute('PRAGMA quick_check').fetchone()[0] != 'ok':
                    raise ValueError('Latest-selection child SQLite quick_check failed')
        if output.exists():
            raise ValueError('Output appeared during derivation; refusing overwrite')
        with output.open('xb') as final, temporary.open('rb') as finished:
            shutil.copyfileobj(finished, final);final.flush();os.fsync(final.fileno())
        temporary.unlink()
        return {'output': str(output), 'run_id': child_id, 'parent_run_id': parent_run['run_id'],
                'selection': run['scope']['selection'], 'parent_database_changed': False,
                'all_parent_records_retained': True}
    finally:
        if temporary.exists():
            temporary.unlink()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--parent', required=True)
    parser.add_argument('--count', type=int, required=True)
    parser.add_argument('--report-dir', required=True)
    parser.add_argument('--output')
    parser.add_argument('--run-id')
    parser.add_argument('--create', action='store_true')
    args = parser.parse_args()
    report = Path(args.report_dir);report.mkdir(parents=True, exist_ok=True)
    with closing(derive_scope.open_readonly(args.parent)) as c:
        c.execute('BEGIN');c.execute('SELECT count(*) FROM meta').fetchone()
        plan = inspect(c, args.count)
    if args.create:
        if not args.output:
            parser.error('--create requires --output')
        result = derive(args.parent, args.output, args.count, args.run_id)
        # A parent may have advanced after the inspection. Report the exact
        # frozen backup actually created, never the earlier preview as proof.
        engine = derive_scope.engine_module()
        with closing(derive_scope.open_readonly(args.output)) as child:
            value = engine.latest_selection_module().validate(child, engine.latest_selection_context())
        (report/'selection-manifest.private.json').write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
        plan = {key: value[key] for key in plan}
        (report/'derivation.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    else:
        result = {k: plan[k] for k in ('kind', 'count', 'date_field', 'date_order', 'tie_break',
                    'candidate_count', 'candidate_snapshot_hash', 'latest_filing_date', 'oldest_filing_date', 'boundary_tie')}
        result['inspection_only'] = True
    (report/'selection-plan.private.json').write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':main()
