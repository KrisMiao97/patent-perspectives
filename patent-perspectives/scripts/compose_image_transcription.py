#!/usr/bin/env python3
"""Bind host-read image transcriptions to original text, cache and image bytes.

This does not perform OCR or verify mathematical correctness. The host must
inspect every source image. A separate marked version is emitted; original
provider text and database rows are never changed here.
"""
import argparse, hashlib, html, importlib.util, json, re, sqlite3, struct, zlib
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlsplit, unquote

REVIEW_SCHEMA = 2
VOID = frozenset(('area','base','br','col','embed','hr','img','input','link','meta','param','source','track','wbr'))
MARKUP = re.compile(r'''</?[A-Za-z][A-Za-z0-9:-]*(?:\s+[A-Za-z_:][A-Za-z0-9_.:-]*(?:\s*=\s*(?:"[^"]*"|'[^']*'|[^\s<>`=]+))?)*\s*/?>|<!--[\s\S]*?-->''')

def preserve_literal_less_than(raw):
    pieces=[]; cursor=0
    while cursor<len(raw):
        start=raw.find('<',cursor)
        if start<0:pieces.append(raw[cursor:]);break
        pieces.append(raw[cursor:start]);match=MARKUP.match(raw,start)
        if match:pieces.append(match.group());cursor=match.end()
        else:pieces.append('&lt;');cursor=start+1
    return ''.join(pieces)

class Plain(HTMLParser):
    def __init__(self,preserve_typography=False):
        super().__init__(convert_charrefs=True)
        self.parts=[];self.images=[];self.stack=[];self.valid=True
        self.preserve_typography=preserve_typography;self.typography=[]
    def handle_data(self,text):self.parts.append(text)
    def handle_starttag(self,tag,attrs):
        if len({k for k,v in attrs})!=len(attrs):self.valid=False
        if tag=='img':self.images.append({'tag':self.get_starttag_text(),'attributes':dict(attrs)})
        if tag=='br':self.parts.append('\n')
        if tag in ('sup','sub') and self.preserve_typography:
            self.parts.append('^{' if tag=='sup' else '_{')
            self.typography.append((tag,len(self.parts)))
        if tag not in VOID:self.stack.append(tag)
    def handle_endtag(self,tag):
        if tag in VOID:return
        if not self.stack or self.stack[-1]!=tag:self.valid=False
        else:self.stack.pop()
        if tag in ('sup','sub') and self.preserve_typography:
            if not self.typography or self.typography[-1][0]!=tag:self.valid=False
            else:
                _,start=self.typography.pop()
                if not ''.join(self.parts[start:]).strip():self.valid=False
            self.parts.append('}')
        if tag in ('div','p'):self.parts.append('\n')
    def handle_startendtag(self,tag,attrs):
        self.handle_starttag(tag,attrs)
        if tag not in VOID:self.handle_endtag(tag)
    def text(self):return re.sub(r'\n[ \t]*\n+','\n',''.join(self.parts)).strip()

def parsed(raw,e=None,preserve_typography=False):
    parser=Plain(preserve_typography);parser.feed(preserve_literal_less_than(raw));parser.close()
    if e:e.require(parser.valid and not parser.stack,'Original source markup is unbalanced or ambiguous')
    return parser

def plain(raw):return parsed(raw).text()
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()

def image_integrity(data,e):
    """Reject incomplete containers; no pixel interpretation or OCR is attempted."""
    if data.startswith(b'\x89PNG\r\n\x1a\n'):
        cursor=8;types=[];compressed=[];dimensions=None
        while cursor<len(data):
            e.require(cursor+12<=len(data),'Incomplete PNG image container')
            size=struct.unpack('>I',data[cursor:cursor+4])[0];finish=cursor+12+size
            e.require(finish<=len(data),'Incomplete PNG image chunk')
            kind=data[cursor+4:cursor+8];payload=data[cursor+8:cursor+8+size]
            crc=struct.unpack('>I',data[cursor+8+size:finish])[0]
            e.require(zlib.crc32(kind+payload)&0xffffffff==crc,'PNG image checksum mismatch')
            types.append(kind)
            if kind==b'IHDR':
                e.require(len(types)==1 and size==13,'Invalid PNG image header')
                dimensions=struct.unpack('>II',payload[:8]);e.require(all(dimensions),'Empty PNG image dimensions')
            if kind==b'IDAT':compressed.append(payload)
            cursor=finish
            if kind==b'IEND':
                e.require(size==0 and cursor==len(data),'PNG image has unexpected trailing content');break
        e.require(types and types[0]==b'IHDR' and types[-1]==b'IEND' and compressed,'Incomplete PNG image')
        try:
            decoder=zlib.decompressobj();pixels=decoder.decompress(b''.join(compressed),64*1024*1024)
        except zlib.error:e.require(False,'Invalid PNG image compression')
        e.require(pixels and decoder.eof and not decoder.unused_data and not decoder.unconsumed_tail,'Incomplete or oversized PNG image data')
        return {'format':'PNG','width':dimensions[0],'height':dimensions[1]}
    # These are container boundary checks, not full codec or semantic checks.
    if data.startswith(b'\xff\xd8'):
        e.require(data.endswith(b'\xff\xd9') and len(data)>4,'Incomplete JPEG image');return {'format':'JPEG'}
    if data.startswith((b'GIF87a',b'GIF89a')):
        e.require(len(data)>13 and data.endswith(b';'),'Incomplete GIF image');return {'format':'GIF'}
    if data.startswith(b'RIFF'):
        e.require(len(data)>=20 and data[8:12]==b'WEBP' and struct.unpack('<I',data[4:8])[0]+8==len(data),'Incomplete WebP image')
        return {'format':'WebP'}
    e.require(False,'Invalid local image payload')

def supplemental_image_access(image,image_id,pn,source_record,local,root,e):
    """Prove access to an empty-src image by exact PDF-image identity.

    An image's list position, figure label or family membership cannot supply
    its identity. Signed storage URLs remain in the private cached response.
    """
    access=image.get('supplemental_image_access')
    e.require(isinstance(access,dict) and set(access)=={'source_raw_artifact','source_sha256','record_index'},
              'Empty source image needs exact supplemental access provenance')
    raw_path=local(access['source_raw_artifact']);raw_hash=sha(raw_path)
    e.require(access['source_sha256']==raw_hash,'Supplemental image cache hash changed')
    envelope=json.loads(raw_path.read_text(encoding='utf-8'))
    e.require(isinstance(envelope,dict),'Supplemental image source must be a Collector envelope')
    arguments=envelope.get('arguments')
    e.require(envelope.get('tool')=='intelligent_image' and isinstance(arguments,dict) and arguments.get('pn')==pn,
              'Supplemental image requires intelligent_image for this single exact publication')
    e.require(envelope.get('status')=='ok' and envelope.get('error_code') in (None,0,'0')
              and not envelope.get('error') and not envelope.get('isError'),
              'Supplemental image cache records a transport or service error')
    response=envelope.get('response')
    e.require(isinstance(response,dict) and not response.get('error') and not response.get('isError'),'Supplemental image transport error')
    result=response.get('result')
    e.require(isinstance(result,dict) and not result.get('isError'),'Supplemental image tool error')
    body=result.get('structuredContent',result)
    e.require(isinstance(body,dict) and body.get('success') is True and body.get('error_code') in (0,'0'),
              'Supplemental image provider error')
    data=body.get('data');index=access['record_index']
    records=data.get('pdf_images') if isinstance(data,dict) else None
    e.require(isinstance(records,list) and type(index) is int and 0<=index<len(records),
              'Supplemental access needs actual pdf_images record index')
    actual=records[index];patent_id=source_record.get('patent_id')
    e.require(isinstance(actual,dict) and isinstance(patent_id,str) and patent_id
              and actual.get('patent_id')==patent_id,'Supplemental image patent identity differs from original text record')
    storage=actual.get('storage_path')
    e.require(isinstance(storage,str) and storage,'Supplemental PDF image storage path missing')
    try:url=urlsplit(storage);port=url.port
    except ValueError:e.require(False,'Supplemental PDF image URL invalid')
    e.require(url.scheme=='https' and url.hostname=='data-fulltext-image.zhihuiya.com'
              and not url.username and not url.password and port in (None,443) and not url.fragment,
              'Supplemental PDF image must use trusted HTTPS storage host')
    source_path=unquote(url.path)
    e.require(source_path.startswith('/') and '\\' not in source_path and '\x00' not in source_path
              and not any(part in ('.','..') for part in source_path.split('/')),
              'Supplemental PDF image path invalid')
    basename=source_path.rsplit('/',1)[-1]
    e.require(any(basename==image_id+ext for ext in ('.png','.jpg','.jpeg','.gif','.webp')),
              'Supplemental PDF image filename must exactly match original img-id')
    record_path=['response','result']+(['structuredContent'] if 'structuredContent' in result else [])+['data','pdf_images',index]
    proof={'source_raw_artifact':str(raw_path.relative_to(root)),'source_sha256':raw_hash,'record_index':index,
           'tool':'intelligent_image','requested_publication_number':pn,'source_patent_id':patent_id,
           'source_record_path':record_path,'source_image_path':source_path,
           'binding':'original empty src; exact original img-id matches actual pdf_images filename and original text patent_id'}
    return source_path,proof

def compose(c,p,e):
    database=c.execute('PRAGMA database_list').fetchone()[2]
    e.require(database,'Image evidence needs a file-backed read-only source database')
    root=Path(database).resolve().parent
    def local(value):
        e.require(isinstance(value,str) and value,'Evidence path required')
        path=(root/value).resolve()
        e.require(path.is_relative_to(root) and path.is_file(),'Evidence file must exist inside run directory')
        return path
    row=c.execute('SELECT * FROM documents WHERE id=?',(p.get('document_id'),)).fetchone()
    e.require(row,'Source document absent')
    source=json.loads(row['data']);pn=row['publication_id'];kind=row['document_type']
    e.require(kind in ('description','claims') and source.get('source_class')=='patsnap' and source.get('qualified') is True,'Only structurally qualified same-publication original source can be composed')
    e.require(not source.get('embedded_image_review') and not source.get('normalization_notice'),'Source must be the original uncomposed document')
    e.require(p.get('publication_number')==pn and p.get('source_version')==source.get('version') and p.get('source_text_hash')==row['text_hash'],'Visual review source document, version or text hash mismatch')
    e.require(e.digest(row['text'])==row['text_hash'],'Stored source text integrity mismatch')
    e.require(isinstance(p.get('reviewer'),str) and p['reviewer'].strip() and p.get('visual_review_complete') is True,'Host visual inspection must be explicit')
    manifest_path=local(p.get('image_manifest'))
    e.require(p.get('image_manifest_sha256')==sha(manifest_path),'Visual review image manifest hash mismatch')
    manifest=json.loads(manifest_path.read_text(encoding='utf-8'))
    e.require(manifest.get('publication_number')==pn and manifest.get('document_type')==kind,'Embedded image manifest document mismatch')
    raw_path=local(manifest.get('source_raw_artifact'))
    e.require(sha(raw_path)==manifest.get('source_sha256'),'Original source cache hash changed')
    envelope=json.loads(raw_path.read_text(encoding='utf-8'))
    request=source.get('source_request',{});arguments=request.get('arguments')
    e.require(isinstance(arguments,dict) and request.get('tool')==kind,'Imported source request kind missing or different')
    e.require(envelope.get('tool')==kind and envelope.get('arguments')==arguments and envelope.get('endpoint')==request.get('endpoint'),'Cached source request differs from imported text')
    requested=str(arguments.get('patent_number','')).split(',')
    e.require(arguments.get('replace_by_related')==0 and pn in requested,'Same-publication request with family replacement disabled required')
    artifact=source.get('raw_artifact',{})
    e.require(envelope.get('cache_key') and envelope.get('cache_key')==artifact.get('cache_key'),'Cache identity differs from imported source')
    e.require(envelope.get('status')=='ok' and envelope.get('error_code') in (None,0,'0'),'Source cache records a transport or service error')
    response=envelope.get('response',{})
    e.require(isinstance(response,dict) and not response.get('error'),'Source transport error')
    result=response.get('result')
    e.require(isinstance(result,dict) and not result.get('isError'),'Source tool error')
    body=result.get('structuredContent',result)
    e.require(isinstance(body,dict) and body.get('success') is True and body.get('error_code') in (0,'0'),'Source provider error')
    records=body.get('data');index=artifact.get('source_index')
    e.require(isinstance(records,list) and type(index) is int and 0<=index<len(records),'Actual source record index missing or invalid')
    record=records[index]
    e.require(isinstance(record,dict) and record.get('pn')==pn,'Returned source publication mismatch')
    originals=[x for x in record.get(kind,[]) if x.get('data_format')=='original' and x.get('lang')==source.get('language')]
    e.require(len(originals)==1,'Unique exact original source language required')
    original=originals[0]
    e.require(not any(x.get(k) is True for x in (record,original) for k in ('truncated','is_truncated','partial')),'Original source reports truncation')
    raw=original.get('text' if kind=='description' else 'claim_text')
    e.require(isinstance(raw,str) and raw.strip(),'Original source text missing')
    has_typography=bool(re.search(r'<(?:sup|sub)\b',raw,re.I))
    declared_typography=any(isinstance(t,dict) and t.get('type')=='html_superscript_subscript_preservation'
        and t.get('policy_version')=='supsub-v2'
        and t.get('representation')=={'sup':'^{original content}','sub':'_{original content}'}
        for t in source.get('normalization_transformations',[]))
    e.require(not has_typography or declared_typography,'Original sup/sub requires declared preserving re-extraction before image composition')
    parser=parsed(raw,e,preserve_typography=declared_typography)
    e.require(parser.text()==row['text'],'Independent source reconstruction must match every imported character')
    annotations=p.get('images');images=manifest.get('images')
    e.require(isinstance(annotations,list) and isinstance(images,list) and parser.images and len(parser.images)==len(annotations)==len(images),'Every embedded image must be visually read and transcribed')
    actual={}
    for image in parser.images:
        image_id=image['attributes'].get('img-id')
        e.require(image_id and image_id not in actual,'Source image identity absent or duplicated')
        actual[image_id]=image
    byid={i.get('image_id'):i for i in images}
    e.require(len(byid)==len(images) and set(byid)==set(actual),'Manifest must inventory all and only actual source images')
    seen=set();composed=preserve_literal_less_than(raw);proof=[]
    for item in annotations:
        image_id=item.get('image_id')
        e.require(image_id in actual and image_id not in seen,'Unique actual source image required');seen.add(image_id)
        image=byid[image_id];tag=actual[image_id]
        path=local(image.get('file'));raw_src=tag['attributes'].get('src');access_proof=None
        if raw_src=='':
            source_path,access_proof=supplemental_image_access(image,image_id,pn,record,local,root,e)
        else:
            e.require('supplemental_image_access' not in image,'Nonempty or absent source src cannot use supplemental access')
            e.require(isinstance(raw_src,str) and raw_src,'Original source image src missing')
            source_path=unquote(urlsplit(raw_src).path)
        e.require(source_path and source_path==image.get('source_image_path')==item.get('source_image_path'),'Source image path differs from original source tag or host review')
        filehash=sha(path)
        e.require(image.get('status')=='retrieved' and filehash==image.get('sha256')==item.get('sha256'),'Downloaded image or visually reviewed image hash mismatch')
        data=path.read_bytes()
        e.require(type(image.get('bytes')) is int and len(data)==image['bytes'],'Downloaded image byte count mismatch')
        container=image_integrity(data,e)
        transcription=item.get('transcription')
        e.require(isinstance(transcription,str) and transcription.strip() and item.get('visually_verified') is True,'Host-authored complete image transcription required')
        marker='【原文图片人工转写 '+image_id+'：'+transcription+'】'
        e.require(marker not in row['text'],'Transcription marker already present')
        composed=composed.replace(tag['tag'],html.escape(marker),1)
        image_proof={'image_id':image_id,'source_image_path':source_path,'source_tag_sha256':e.digest(tag['tag']),
                      'file':str(path.relative_to(root)),'sha256':filehash,'bytes':len(data),'container_check':container,
                      'transcription':transcription,'marker':marker,'visually_verified':True}
        if access_proof:image_proof['supplemental_image_access']=access_proof
        proof.append(image_proof)
    reconstructed=parsed(composed,e,preserve_typography=declared_typography)
    e.require(not reconstructed.images and seen==set(actual),'Untranscribed original image remains')
    text=reconstructed.text();e.require(text!=row['text'],'Image composition must add missing original content')
    if kind=='claims':
        expected=source.get('claim_count')
        e.require(type(expected) is int and record.get('claim_count')==expected,'Source claim count mismatch')
        claims=e.claim_blocks(text)
        e.require([claim['number'] for claim in claims]==list(range(1,expected+1)),'Image transcription changed numbered claim sequence')
    proof.sort(key=lambda item:item['image_id'])
    output=dict(source)
    output.update(text=text,version=source['version']+'-image-transcription-'+e.digest(proof)[:10]+'-review-schema2',
        completeness_basis=source['completeness_basis']+' Embedded technical images visually read by host; original text/cache, exact record and all image bytes bound to review schema 2; transcriptions explicitly marked.',
        embedded_image_review={'schema_version':REVIEW_SCHEMA,'reviewer':p['reviewer'],'reviewed_at':e.now(),
            'source_document_id':row['id'],'source_text_hash':row['text_hash'],'source_version':source['version'],
            'image_manifest':str(manifest_path.relative_to(root)),'image_manifest_sha256':sha(manifest_path),
            'source_raw_artifact':str(raw_path.relative_to(root)),'source_raw_sha256':sha(raw_path),
            'source_request':request,'source_record_path':['response','result','structuredContent','data',index] if 'structuredContent' in result else ['response','result','data',index],
            'source_publication_number':pn,'images':proof},
        normalization_notice='Marked image transcriptions were authored by the host from the original pixels; these characters were not returned by the provider text field. This adapter verifies provenance and all-image coverage, not transcription correctness or legal sufficiency.')
    if kind=='claims':output['claims']=claims
    return output

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--db',required=True);p.add_argument('--input',required=True);p.add_argument('--output',required=True);a=p.parse_args()
    spec=importlib.util.spec_from_file_location('image_source_engine',Path(__file__).with_name('patent_perspectives.py'));e=importlib.util.module_from_spec(spec);spec.loader.exec_module(e)
    c=sqlite3.connect(Path(a.db).resolve().as_uri()+'?mode=ro',uri=True);c.row_factory=sqlite3.Row
    try:result=compose(c,e.read_input(a.input),e)
    finally:c.close()
    path=Path(a.output);path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'publication_number':result['publication_number'],'images_composed':len(result['embedded_image_review']['images']),'text_characters':len(result['text']),'review_schema':REVIEW_SCHEMA,'database_changed':False,'network_calls':0},ensure_ascii=False))
if __name__=='__main__':main()
