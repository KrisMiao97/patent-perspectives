"""Frozen, file-backed material intake; never fabricates provider search totals."""
import hashlib
import json
from pathlib import Path

def verify_files(manifest, require):
    sources = manifest.get('sources', [])
    require(bool(sources), 'Material sources are required')
    ids = set()
    for source in sources:
        require(source.get('id') and source['id'] not in ids, 'Unique material source IDs required')
        ids.add(source['id'])
        path = Path(source.get('path', ''))
        require(path.is_absolute() and path.is_file(), 'Downloaded/uploaded material must exist at an absolute path')
        require(hashlib.sha256(path.read_bytes()).hexdigest() == source.get('sha256'), 'Material file hash mismatch: ' + source['id'])
        require(source.get('received_at') and source.get('kind') in ('catalogue', 'claims', 'description', 'abstract', 'excerpt', 'other'), 'Material kind/time required')
    return {s['id']: s for s in sources}

def import_manifest(c, payload, engine):
    require = engine.require
    run = engine.run_info(c)
    require(payload.get('confirmed') is True and payload.get('scope_label'), 'Confirm the material boundary first')
    require(payload.get('boundary') and payload.get('excluded_or_unavailable') is not None, 'Record subject, geography, dates and missing materials')
    sources = verify_files(payload, require)
    records = payload.get('records', [])
    material_mode = run['scope'].get('acquisition_mode') == 'materials'
    if material_mode:
        require(records, 'Material research requires a frozen catalogue')
        require(not c.execute('SELECT 1 FROM queries').fetchone(), 'Use a separate material run; retain the search run')
    old = engine.get_meta(c, 'material_manifest')
    clean = engine.sanitized(payload)
    if old:
        require(old == clean, 'Material manifest is frozen; make a new snapshot to extend it')
        return {'cached': True, 'scope': payload['scope_label']}
    if material_mode:
        require(not c.execute('SELECT 1 FROM publications').fetchone(), 'Material intake must begin with an empty catalogue')
    for record in records:
        require(record.get('material_source_id') in sources and record.get('material_locator'), 'Each record requires a material source and location')
        item = engine.normalize_record(record, 'material-catalogue')
        if material_mode:
            engine.merge_application(c, item)
        else:
            known = c.execute('SELECT application_id FROM publications WHERE id=?', (item['id'],)).fetchone()
            require(known and known[0] == item['application_id'], 'Supplement must match an existing search publication')
    engine.set_meta(c, 'material_manifest', clean)
    engine.event(c, 'materials-import', {'sources': len(sources), 'records': len(records), 'mode': 'materials' if material_mode else 'supplement'})
    return {'sources': len(sources), 'records': len(records), 'scope': payload['scope_label'], 'company_full_population': False}

def validate_manifest(c, engine):
    manifest = engine.get_meta(c, 'material_manifest')
    engine.require(manifest, 'Frozen material manifest missing')
    verify_files(manifest, engine.require)
    if engine.run_info(c)['scope'].get('acquisition_mode') == 'materials':
        expected = {engine.normalize_record(r, 'material-catalogue')['id'] for r in manifest['records']}
        actual = {r[0] for r in c.execute('SELECT id FROM publications')}
        engine.require(actual == expected, 'Material catalogue differs from frozen manifest')
    return manifest

def verify_document(c, p, engine):
    manifest = validate_manifest(c, engine)
    source = next((s for s in manifest['sources'] if s['id'] == p.get('material_source_id')), None)
    engine.require(source and source['kind'] == p['document_type'], 'Abstracts/excerpts cannot become complete technical sources')
    engine.require(engine.number(p['publication_number']) in [engine.number(x) for x in source.get('publication_numbers', [])], 'Material publication identity mismatch')
    proof = p.get('material_review', {})
    engine.require(proof.get('source_sha256') == source['sha256'], 'Document review must bind the source bytes')
    engine.require(proof.get('reviewer') and proof.get('reviewed_at') and proof.get('page_range') and proof.get('identity_locator') and proof.get('end_locator'), 'Record actual identity, full page range and document ending review')
    engine.require(proof.get('text_sha256') == hashlib.sha256(p['text'].encode()).hexdigest(), 'Reviewed text hash mismatch')
    return source
