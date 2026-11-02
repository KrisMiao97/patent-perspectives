"""Revalidate and export only reviewed original embedded image bytes.

The private review contains cached responses and access provenance. None of
those paths, URLs, requests or raw fields enter the public image metadata.
This is a render-time integrity check, not OCR or a fresh visual review.
"""
import hashlib
import importlib.util
import json
from pathlib import Path, PureWindowsPath
import re

_COMPOSER = None
EXTENSIONS = {'PNG': '.png', 'JPEG': '.jpg', 'GIF': '.gif', 'WebP': '.webp'}


def image_container(data, e):
    global _COMPOSER
    if _COMPOSER is None:
        spec = importlib.util.spec_from_file_location('pp_image_composer', Path(__file__).with_name('compose_image_transcription.py'))
        _COMPOSER = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(_COMPOSER)
    return _COMPOSER.image_integrity(data, e)


def prepare(c, application_ids, e):
    """Check every declared schema2 image before any delivery files are made.

    Returns public per-document metadata and immutable verified bytes. Copies
    use these same bytes, avoiding a second read of a potentially changed file.
    Documents without an embedded review retain their previous behavior.
    """
    selected = set(application_ids)
    checked = []
    for row in c.execute('SELECT * FROM documents ORDER BY id'):
        if row['application_id'] not in selected:
            continue
        sd = json.loads(row['data'])
        if 'embedded_image_review' in sd:
            checked.append((row, sd))
    if not checked:
        return {}, {}
    database = c.execute('PRAGMA database_list').fetchone()[2]
    e.require(database, 'Embedded image export requires a file-backed run')
    root = Path(database).resolve().parent
    by_document, blobs = {}, {}
    for row, sd in checked:
        review = sd['embedded_image_review']
        e.require(isinstance(review, dict) and review.get('schema_version') == 2,
                  'Embedded image export requires review schema 2')
        pn = row['publication_id']
        e.require(e.digest(row['text']) == row['text_hash'], 'Embedded image document text hash changed')
        e.require(review.get('source_publication_number') == pn,
                  'Embedded image review belongs to a different publication')
        original = c.execute('SELECT * FROM documents WHERE id=?', (review.get('source_document_id'),)).fetchone()
        e.require(original is not None and original['id'] != row['id']
                  and original['application_id'] == row['application_id'] and original['publication_id'] == pn
                  and original['document_type'] == row['document_type'],
                  'Embedded image original document identity mismatch')
        original_data = json.loads(original['data'])
        e.require(original['text_hash'] == review.get('source_text_hash') == e.digest(original['text'])
                  and original_data.get('version') == review.get('source_version')
                  and original_data.get('language') == sd.get('language'),
                  'Embedded image original document version or text hash changed')
        images = review.get('images')
        e.require(isinstance(images, list) and images,
                  'Embedded image review must inventory original images')
        e.require(isinstance(sd.get('normalization_notice'), str) and sd['normalization_notice'].strip(),
                  'Embedded image transcription notice is missing')
        seen, public = set(), []
        for image in images:
            e.require(isinstance(image, dict), 'Embedded image review entry invalid')
            image_id = image.get('image_id')
            e.require(isinstance(image_id, str) and 0 < len(image_id) <= 240
                      and not re.search(r'[\x00-\x1f\x7f]|://', image_id)
                      and image_id not in seen,
                      'Embedded image identity is invalid or duplicated')
            seen.add(image_id)
            e.require(image.get('visually_verified') is True,
                      'Embedded image lacks explicit visual review')
            transcription = image.get('transcription')
            marker = '【原文图片人工转写 ' + image_id + '：' + transcription + '】' if isinstance(transcription, str) else None
            e.require(marker and transcription.strip() and image.get('marker') == marker
                      and row['text'].count(marker) == 1,
                      'Embedded image transcription marker does not match this document')
            name = image.get('file')
            e.require(isinstance(name, str) and name and not re.search(r'[:\x00-\x1f\x7f]', name)
                      and not Path(name).is_absolute() and not PureWindowsPath(name).drive,
                      'Embedded image path must be relative to the run directory')
            try:
                path = (root / name).resolve()
                e.require(path.is_relative_to(root) and path.is_file(),
                          'Reviewed embedded image must exist inside the run directory')
                data = path.read_bytes()
            except (OSError, ValueError):
                e.require(False, 'Reviewed embedded image is unavailable inside the run directory')
            expected_hash = image.get('sha256')
            actual_hash = hashlib.sha256(data).hexdigest()
            e.require(isinstance(expected_hash, str) and re.fullmatch(r'[0-9a-f]{64}', expected_hash)
                      and expected_hash == actual_hash,
                      'Reviewed embedded image hash changed')
            e.require(type(image.get('bytes')) is int and image['bytes'] > 0 and len(data) == image['bytes'],
                      'Reviewed embedded image byte count changed')
            container = image_container(data, e)
            e.require(container == image.get('container_check'),
                      'Reviewed embedded image container changed')
            relative = 'document-images/' + actual_hash + EXTENSIONS[container['format']]
            # A repeated source image shares one output file, but every document
            # keeps its own identity, caption and source-document association.
            if relative in blobs:
                e.require(blobs[relative] == data, 'Embedded image hash collision')
            else:
                blobs[relative] = data
            public.append({'path': relative, 'document_id': row['id'], 'publication_number': pn,
                           'image_id': image_id, 'sha256': actual_hash,
                           'caption': pn + ' · img-id: ' + image_id + ' · 原文嵌图（文字经人工转写）',
                           'image_role': 'original_document_embedded_image',
                           'view_scope': 'original_embedded_transcribed'})
        by_document[row['id']] = public
    return by_document, blobs


def copy_verified(blobs, output, e):
    """Write only the exact prepared bytes under deterministic digest names."""
    output = Path(output).resolve()
    directory = output / 'document-images'
    if blobs:
        directory.mkdir(exist_ok=True)
        e.require(directory.resolve().is_relative_to(output), 'Embedded image output escaped delivery directory')
    for relative, data in blobs.items():
        target = output / relative
        e.require(target.resolve().is_relative_to(directory.resolve()), 'Embedded image output path escaped')
        if target.exists():
            e.require(target.is_file() and target.read_bytes() == data, 'Existing embedded image output changed')
        else:
            with target.open('xb') as f:
                f.write(data)
