#!/usr/bin/env python3
"""Validate/import existing collector auxiliary cache; read-only by default."""
from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path
import sqlite3


def load_engine():
    spec = importlib.util.spec_from_file_location('pp_auxiliary_adapter', Path(__file__).with_name('patent_perspectives.py'))
    engine = importlib.util.module_from_spec(spec); spec.loader.exec_module(engine)
    return engine


def plan(c, ledger, tool, run_root, e, limit=None):
    known = {r[0] for r in c.execute('SELECT id FROM publications')}
    specifications = []; skipped = 0
    sql = ('SELECT p.pn,p.source_index,p.acquired_at,c.raw_file,c.arguments_json '
           'FROM publication_cache p JOIN calls c ON c.cache_key=p.cache_key '
           'WHERE p.tool=? AND p.status=\'ok\' AND c.status=\'ok\' ORDER BY p.pn')
    for row in ledger.execute(sql, (tool,)):
        if row['pn'] not in known:
            skipped += 1; continue
        artifact = (Path(ledger.execute('PRAGMA database_list').fetchone()[2]).parent / row['raw_file']).resolve()
        e.require(artifact.is_relative_to(run_root), 'Collector raw source lies outside the run directory')
        specifications.append({'kind': tool, 'publication_number': row['pn'],
            'source_artifact': str(artifact.relative_to(run_root)),
            'source_request': {'tool': tool, 'arguments': json.loads(row['arguments_json'])},
            'request_tool_path': ['tool'], 'request_arguments_path': ['arguments'],
            'response_path': ['response', 'result', 'structuredContent'],
            'record_index': row['source_index'], 'acquired_at': row['acquired_at']})
        if limit is not None and len(specifications) >= limit: break
    return specifications, skipped


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--db', required=True)
    parser.add_argument('--ledger', required=True)
    parser.add_argument('--tool', choices=('legal_status', 'family', 'abstract_image'), required=True)
    parser.add_argument('--limit', type=int)
    parser.add_argument('--output', help='Optional cache-pointer input manifest, without signed URLs')
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--apply', action='store_true')
    mode.add_argument('--dry-run', action='store_true')
    args = parser.parse_args(); e = load_engine()
    e.require(args.limit is None or args.limit > 0, 'Limit must be positive')
    run_root = Path(args.db).resolve().parent
    ledger_path = Path(args.ledger).resolve()
    e.require(ledger_path.is_relative_to(run_root), 'Collector ledger must be inside run directory')
    source = sqlite3.connect(Path(args.db).resolve().as_uri() + '?mode=ro', uri=True); source.row_factory = sqlite3.Row
    ledger = sqlite3.connect(ledger_path.as_uri() + '?mode=ro', uri=True); ledger.row_factory = sqlite3.Row
    try:
        specifications, skipped = plan(source, ledger, args.tool, run_root, e, args.limit)
        cache = {}; errors = []; verified = []
        for p in specifications:
            try:
                item = e.prepare_auxiliary(source, p, cache)
                verified.append({'publication_number': p['publication_number'], 'id': item['id'], 'acquired_at': item['acquired_at']})
            except (e.ValidationError, OSError, ValueError, KeyError, TypeError) as error:
                errors.append({'publication_number': p['publication_number'], 'error_type': type(error).__name__, 'error': str(error)})
        if args.output:
            target = Path(args.output); target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(json.dumps(specifications, ensure_ascii=False, indent=2), encoding='utf-8')
    finally:
        ledger.close(); source.close()
    applied = 0
    if args.apply and not errors and specifications:
        writer = e.db_open(args.db)
        try:
            with writer:
                result = e.import_auxiliary(writer, specifications)
                applied = len(result['auxiliary_imported'])
        finally: writer.close()
    print(json.dumps({'mode': 'apply' if args.apply else 'dry_run', 'tool': args.tool,
        'selected': len(specifications), 'verified': len(verified), 'applied': applied,
        'unretained_publications_skipped': skipped, 'errors': errors,
        'run_database_modified': bool(applied), 'collector_ledger_modified': False, 'network_calls': 0}, ensure_ascii=False, indent=2))
    return 3 if errors else 0


if __name__ == '__main__':
    raise SystemExit(main())
