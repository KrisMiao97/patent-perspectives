#!/usr/bin/env python3
"""Original patent-perspectives data engine. Python 3.10+; standard library only."""
from __future__ import annotations
import argparse, collections, datetime as dt, hashlib, importlib.util, json, re, shutil, sqlite3, sys, unicodedata, zipfile, tempfile
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode
SCHEMA_VERSION=1
SKILL_RELEASE="2026.11.10-reader2"
def materials_module():
    spec=importlib.util.spec_from_file_location("patent_materials",Path(__file__).with_name("materials.py"))
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module

def material_engine():
    from types import SimpleNamespace
    return SimpleNamespace(**globals())

ROLES=("management","rd","ip")
FIELDS=("application_field","technical_problem","technical_means","components","relationships","steps","conditions","claimed_effects")
SECRET=re.compile(r"^((?:x[-_])?api[_-]?key|authorization|(?:access[_-]?|refresh[_-]?)?token|password|(?:client[_-]?)?secret|bearer)$",re.I)
OFFICIAL=("cnipa.gov.cn","wipo.int","epo.org","uspto.gov","inpit.go.jp","kipo.go.kr","jpo.go.jp","dpma.de","ipaustralia.gov.au","ised-isde.canada.ca","ic.gc.ca","gov.uk","ipindia.gov.in")
BIBLIO_TYPE_SOURCE="https://open.zhihuiya.com/devportal/api-reference/basic-patent-data/bibliography"
# P012 official definitions: invention application / granted invention / utility / design.
BIBLIO_TYPES={"APPLICATION":"invention","PATENT":"invention","UTILITY":"utility_model","DESIGN":"design"}
class ValidationError(ValueError): pass
def now(): return dt.datetime.now(dt.timezone.utc).isoformat()
def dump(v): return json.dumps(v,ensure_ascii=False,sort_keys=True,separators=(",",":"))
def digest(v): return hashlib.sha256((v if isinstance(v,str) else dump(v)).encode()).hexdigest()
def require(c,m):
    if not c: raise ValidationError(m)
def read_input(f):
    text=Path(f).read_text(encoding="utf-8-sig").strip()
    require(text,"Empty input file")
    try: return json.loads(text)
    # JSONL records are delimited by LF, not Unicode U+2028/U+0085 characters
    # that may legitimately appear inside a JSON string containing patent text.
    except json.JSONDecodeError: return [json.loads(x) for x in text.split("\n") if x.strip()]
def as_list(v): return v if isinstance(v,list) else [v]
def date_value(v):
    if v in (None,"","unknown"): return None
    t=str(v).strip()
    if re.fullmatch(r"\d{8}",t): t=t[:4]+"-"+t[4:6]+"-"+t[6:]
    try: return dt.date.fromisoformat(t[:10]).isoformat()
    except ValueError: raise ValidationError("Invalid date: "+t)
def number(v): return re.sub(r"[^A-Z0-9]","",str(v or "").upper())
def array(v):
    if v is None: return []
    if isinstance(v,list): return [str(x).strip() for x in v if str(x).strip()]
    return [x.strip() for x in re.split(r"[|;；]",str(v)) if x.strip()]
def legal_name_key(value):
    # Character compatibility only: no translation, case folding, punctuation
    # deletion, abbreviation expansion, word reordering or script conversion.
    # Raw field values and exact matched_name tokens remain unchanged.
    return unicodedata.normalize("NFKC",str(value))
def safe_url(v):
    if not v: return ""
    u=urlsplit(str(v))
    require(u.scheme in ("http","https") and bool(u.netloc) and not u.username and not u.password,"Evidence URL must be HTTP(S) without credentials")
    q=[(k,x) for k,x in parse_qsl(u.query,keep_blank_values=True) if not SECRET.match(k)]
    return urlunsplit((u.scheme,u.netloc,u.path,urlencode(q),u.fragment))
def sanitized(v):
    if isinstance(v,dict): return {str(k):("[REDACTED]" if SECRET.match(str(k)) else sanitized(x)) for k,x in v.items()}
    if isinstance(v,list): return [sanitized(x) for x in v]
    if isinstance(v,str):
        v=re.sub(r"(?i)Bearer\s+[A-Za-z0-9._~+/=-]+","Bearer [REDACTED]",v)
        if v.startswith(("http://","https://")):
            try: return safe_url(v)
            except ValidationError: return "[REDACTED_URL]"
    return v
def db_open(f):
    p=Path(f); p.parent.mkdir(parents=True,exist_ok=True)
    c=sqlite3.connect(str(p),timeout=30); c.row_factory=sqlite3.Row
    c.execute("PRAGMA journal_mode=WAL").fetchall()
    c.execute("PRAGMA busy_timeout=30000")
    c.execute("PRAGMA foreign_keys=ON")
    c.executescript("""
    CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY,value TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS entities(id TEXT PRIMARY KEY,data TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS queries(id TEXT PRIMARY KEY,entity_id TEXT NOT NULL,kind TEXT NOT NULL,expected_count INTEGER NOT NULL,request TEXT NOT NULL,complete INTEGER NOT NULL DEFAULT 0,error TEXT);
    CREATE TABLE IF NOT EXISTS pages(query_id TEXT NOT NULL,offset INTEGER NOT NULL,body_hash TEXT NOT NULL,record_count INTEGER NOT NULL,raw TEXT NOT NULL,PRIMARY KEY(query_id,offset),FOREIGN KEY(query_id) REFERENCES queries(id));
    CREATE TABLE IF NOT EXISTS applications(id TEXT PRIMARY KEY,data TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS registration_members(id TEXT PRIMARY KEY,member_application_id TEXT NOT NULL UNIQUE,canonical_filing_application_id TEXT NOT NULL,data TEXT NOT NULL,FOREIGN KEY(member_application_id) REFERENCES applications(id),FOREIGN KEY(canonical_filing_application_id) REFERENCES applications(id));
    CREATE TABLE IF NOT EXISTS population_reviews(application_id TEXT PRIMARY KEY,data TEXT NOT NULL,FOREIGN KEY(application_id) REFERENCES applications(id));
    CREATE TABLE IF NOT EXISTS publications(id TEXT PRIMARY KEY,application_id TEXT NOT NULL,data TEXT NOT NULL,FOREIGN KEY(application_id) REFERENCES applications(id));
    CREATE INDEX IF NOT EXISTS publications_application ON publications(application_id);
    CREATE TABLE IF NOT EXISTS bibliographies(id TEXT PRIMARY KEY,publication_id TEXT NOT NULL,application_id TEXT NOT NULL,data TEXT NOT NULL,conflicts TEXT NOT NULL DEFAULT '[]',FOREIGN KEY(publication_id) REFERENCES publications(id),FOREIGN KEY(application_id) REFERENCES applications(id));
    CREATE INDEX IF NOT EXISTS bibliographies_publication ON bibliographies(publication_id);
    CREATE INDEX IF NOT EXISTS bibliographies_application ON bibliographies(application_id);
    CREATE TABLE IF NOT EXISTS query_results(query_id TEXT NOT NULL,publication_id TEXT NOT NULL,PRIMARY KEY(query_id,publication_id),FOREIGN KEY(query_id) REFERENCES queries(id));
    CREATE TABLE IF NOT EXISTS query_sets(id TEXT PRIMARY KEY,entity_id TEXT NOT NULL,kind TEXT NOT NULL,data TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS documents(id TEXT PRIMARY KEY,application_id TEXT NOT NULL,publication_id TEXT NOT NULL,document_type TEXT NOT NULL,text TEXT NOT NULL,text_hash TEXT NOT NULL,data TEXT NOT NULL,FOREIGN KEY(application_id) REFERENCES applications(id),FOREIGN KEY(publication_id) REFERENCES publications(id));
    CREATE TABLE IF NOT EXISTS document_reviews(id TEXT PRIMARY KEY,document_id TEXT NOT NULL,application_id TEXT NOT NULL,data TEXT NOT NULL,FOREIGN KEY(document_id) REFERENCES documents(id));
    CREATE TABLE IF NOT EXISTS analysis_invalidations(id TEXT PRIMARY KEY,application_id TEXT NOT NULL,document_id TEXT NOT NULL,data TEXT NOT NULL,FOREIGN KEY(document_id) REFERENCES documents(id));
    CREATE TABLE IF NOT EXISTS auxiliary_records(id TEXT PRIMARY KEY,kind TEXT NOT NULL,publication_id TEXT NOT NULL,application_id TEXT NOT NULL,data TEXT NOT NULL,FOREIGN KEY(publication_id) REFERENCES publications(id),FOREIGN KEY(application_id) REFERENCES applications(id));
    CREATE INDEX IF NOT EXISTS auxiliary_publication_kind ON auxiliary_records(publication_id,kind);
    CREATE INDEX IF NOT EXISTS auxiliary_application ON auxiliary_records(application_id);
    CREATE INDEX IF NOT EXISTS documents_application ON documents(application_id,document_type,id);
    CREATE TABLE IF NOT EXISTS chunks(id TEXT PRIMARY KEY,document_id TEXT NOT NULL,ordinal INTEGER NOT NULL,start INTEGER NOT NULL,end INTEGER NOT NULL,FOREIGN KEY(document_id) REFERENCES documents(id));
    CREATE INDEX IF NOT EXISTS chunks_document ON chunks(document_id,ordinal);
    CREATE TABLE IF NOT EXISTS analyses(application_id TEXT PRIMARY KEY,document_id TEXT NOT NULL,data TEXT NOT NULL,FOREIGN KEY(application_id) REFERENCES applications(id),FOREIGN KEY(document_id) REFERENCES documents(id));
    CREATE TABLE IF NOT EXISTS evidence(id TEXT PRIMARY KEY,application_id TEXT NOT NULL,document_id TEXT NOT NULL,data TEXT NOT NULL,FOREIGN KEY(document_id) REFERENCES documents(id));
    CREATE TABLE IF NOT EXISTS insights(id TEXT PRIMARY KEY,data TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS relations(id TEXT PRIMARY KEY,data TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS capabilities(id TEXT PRIMARY KEY,data TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS events(id INTEGER PRIMARY KEY AUTOINCREMENT,created_at TEXT NOT NULL,kind TEXT NOT NULL,data TEXT NOT NULL);
    """)
    if "observed_count" not in {r[1] for r in c.execute("PRAGMA table_info(queries)")}:
        c.execute("ALTER TABLE queries ADD COLUMN observed_count INTEGER")
    if "conflicts" not in {r[1] for r in c.execute("PRAGMA table_info(bibliographies)")}:
        c.execute("ALTER TABLE bibliographies ADD COLUMN conflicts TEXT NOT NULL DEFAULT '[]'")
    row=c.execute("SELECT value FROM meta WHERE key='schema_version'").fetchone()
    require(not row or json.loads(row[0])==SCHEMA_VERSION,"Unsupported database schema")
    set_meta(c,"schema_version",SCHEMA_VERSION)
    research_quality_module().initialize(c)
    return c
def set_meta(c,k,v): c.execute("INSERT OR REPLACE INTO meta VALUES(?,?)",(k,dump(v)))
def get_meta(c,k,default=None):
    row=c.execute("SELECT value FROM meta WHERE key=?",(k,)).fetchone()
    return json.loads(row[0]) if row else default
def event(c,k,v): c.execute("INSERT INTO events(created_at,kind,data) VALUES(?,?,?)",(now(),k,dump(sanitized(v))))
def rows_data(c,table): return [json.loads(r[0]) for r in c.execute("SELECT data FROM "+table)]
def run_info(c):
    r=get_meta(c,"run"); require(r,"Run is not initialized; use init first"); return r
def research_quality_module():
    name="patent_perspectives_research_quality"
    if name not in sys.modules:
        spec=importlib.util.spec_from_file_location(name,Path(__file__).with_name("research_quality.py"))
        module=importlib.util.module_from_spec(spec);sys.modules[name]=module;spec.loader.exec_module(module)
    return sys.modules[name]
def research_quality_context():
    return {name:globals()[name] for name in ("require","dump","digest","sanitized","event","check_refs","population_hash","analysis_is_current","included_applications","run_info","make_evidence","document_is_eligible","validate_support_evidence_locator")}
def whole_review_module():
    name="patent_perspectives_whole_review"
    if name not in sys.modules:
        spec=importlib.util.spec_from_file_location(name,Path(__file__).with_name("materialize_review.py"))
        module=importlib.util.module_from_spec(spec);sys.modules[name]=module;spec.loader.exec_module(module)
    return sys.modules[name]
def whole_review_required(c):
    scope=run_info(c)["scope"]
    return not scope.get("synthetic",False) or scope.get("require_whole_patent_review") is True
def research_quality_required(c):
    scope=run_info(c)["scope"]
    return not scope.get("synthetic",False) or scope.get("require_research_quality") is True
def population_review_required(c):
    scope=run_info(c)["scope"]
    return scope.get("require_population_review",not scope.get("synthetic",False)) is True
def candidate_applications(c):
    if run_info(c)["scope"].get("acquisition_mode")=="materials" and get_meta(c,"material_manifest"):
        return rows_data(c,"applications")
    ordinary={q["id"] for q in c.execute("SELECT id,request FROM queries") if not json.loads(q["request"]).get("verification_only",False)}
    appids={r["application_id"] for r in c.execute("SELECT q.query_id,p.application_id FROM query_results q JOIN publications p ON p.id=q.publication_id") if r["query_id"] in ordinary}
    return [a for a in rows_data(c,"applications") if a["id"] in appids]

def application_population_status(c,appid):
    ordinary=any(not json.loads(r[0]).get("verification_only",False) for r in c.execute("SELECT q.request FROM queries q JOIN query_results qr ON qr.query_id=q.id JOIN publications p ON p.id=qr.publication_id WHERE p.application_id=?",(appid,)))
    if run_info(c)["scope"].get("acquisition_mode")=="materials" and get_meta(c,"material_manifest"):ordinary=True
    if not ordinary:return "verification_only"
    row=c.execute("SELECT data FROM population_reviews WHERE application_id=?",(appid,)).fetchone()
    review=json.loads(row[0]) if row else None
    if review and review.get("reason_code")=="outside_control_period" and any(x["field"]=="filing_date" for x in application_date_conflicts(c,appid)):return "pending"
    if review and review.get("candidate_snapshot_hash")==application_scope_snapshot(c,appid):return review["status"]
    return "pending" if review or population_review_required(c) else "included"
def application_scope_snapshot(c,appid,entity_hash=None):
    # Bind identity decisions to every candidate version and the reviewed entity names.
    pubs=[json.loads(r[0]) for r in c.execute("SELECT data FROM publications WHERE application_id=? ORDER BY id",(appid,))]
    entity_hash=entity_hash or digest(sorted(rows_data(c,"entities"),key=lambda e:e["id"]))
    return digest({"publications":stable_page(pubs),"entity_hash":entity_hash})
def population_state(c):
    reviews={r["application_id"]:json.loads(r["data"]) for r in c.execute("SELECT * FROM population_reviews")}
    required=population_review_required(c);out={};entity_hash=digest(sorted(rows_data(c,"entities"),key=lambda e:e["id"]))
    date_conflicted={x["application_id"] for x in application_date_conflicts(c) if x["field"]=="filing_date"}
    for app in candidate_applications(c):
        review=reviews.get(app["id"])
        if review and review.get("reason_code")=="outside_control_period" and app["id"] in date_conflicted:out[app["id"]]="pending"
        elif review and review.get("candidate_snapshot_hash")==application_scope_snapshot(c,app["id"],entity_hash):out[app["id"]]=review["status"]
        elif review or required:out[app["id"]]="pending"
        else:out[app["id"]]="included"  # Backwards-compatible explicitly synthetic fixtures.
    return out
def unselected_source_records(c):
    states=population_state(c)
    selected=[a for a in rows_data(c,"applications") if states.get(a["id"])=="included"]
    temporal=temporal_scope_module().window_states(c,[a["id"] for a in selected])
    # Do not expose a chosen canonical day for an all-inside date conflict.
    # The original database values remain retained in temporal source evidence.
    return [{**a,"filing_date":None,"analysis_window_date_conflict":temporal[a["id"]]} if temporal and temporal[a["id"]]["date_for_statistics"]=="unknown" else a
            for a in selected if not temporal or temporal[a["id"]]["status"]=="included"]

def included_source_records(c):
    records=unselected_source_records(c)
    return latest_selection_module().filter_records(c,records,latest_selection_context()) if run_info(c)["scope"].get("selection") is not None else records

_REGISTRATION_MODULE=None
def registration_module():
    global _REGISTRATION_MODULE
    if _REGISTRATION_MODULE is None:
        spec=importlib.util.spec_from_file_location("pp_registration_members",Path(__file__).with_name("registration_members.py"))
        _REGISTRATION_MODULE=importlib.util.module_from_spec(spec);spec.loader.exec_module(_REGISTRATION_MODULE)
    return _REGISTRATION_MODULE

def registration_context():
    return argparse.Namespace(require=require,ValidationError=ValidationError,digest=digest,dump=dump,event=event,as_list=as_list,included_source_records=included_source_records,bibliography_conflicts=bibliography_conflicts)

def registration_state(c,source_records=None):
    return registration_module().state(c,included_source_records(c) if source_records is None else source_records,registration_context())

def included_applications(c):
    records=included_source_records(c)
    members={r["member_application_id"] for r in registration_state(c,records)["active"]}
    return [a for a in records if a["id"] not in members]

def import_registration_members(c,payload):
    return registration_module().import_records(c,sanitized(payload),registration_context())

def registration_count_bridge(c,source_records=None,unit_records=None,state=None):
    raw=included_source_records(c) if source_records is None else source_records
    state=registration_state(c,raw) if state is None else state
    members={m["member_application_id"] for m in state["active"]}
    units=[a for a in raw if a["id"] not in members] if unit_records is None else unit_records
    technical=lambda items:sum(a["patent_type"] in ("invention","utility_model") for a in items)
    return {"count_unit":"independent_filing_application","raw_included_application_records":len(raw),
      "raw_technical_application_records":technical(raw),"independent_application_units":len(units),
      "independent_technical_application_units":technical(units),"registration_member_records":len(members),
      "adjustments":[{"mapping_id":m["id"],"member_application_id":m["member_application_id"],
         "canonical_filing_application_id":m["canonical_filing_application_id"],"application_delta":-1,"technical_application_delta":-1,
         "reason":"Official same-record national member already represented by its European filing; no source row removed."} for m in state["active"]],
      "source_rows_preserved":True,"member_legal_owner_and_text_independent":True}

_TEMPORAL_SCOPE_MODULE=None
def temporal_scope_module():
    global _TEMPORAL_SCOPE_MODULE
    if _TEMPORAL_SCOPE_MODULE is None:
        spec=importlib.util.spec_from_file_location("pp_temporal_scope",Path(__file__).with_name("temporal_scope.py"))
        _TEMPORAL_SCOPE_MODULE=importlib.util.module_from_spec(spec);spec.loader.exec_module(_TEMPORAL_SCOPE_MODULE)
    return _TEMPORAL_SCOPE_MODULE

_LATEST_SELECTION_MODULE=None
def latest_selection_module():
    global _LATEST_SELECTION_MODULE
    if _LATEST_SELECTION_MODULE is None:
        spec=importlib.util.spec_from_file_location("pp_latest_selection",Path(__file__).with_name("latest_selection.py"))
        _LATEST_SELECTION_MODULE=importlib.util.module_from_spec(spec);spec.loader.exec_module(_LATEST_SELECTION_MODULE)
    return _LATEST_SELECTION_MODULE

def latest_selection_context():
    return argparse.Namespace(require=require,ValidationError=ValidationError,digest=digest,dump=dump,
      run_info=run_info,get_meta=get_meta,rows_data=rows_data,population_state=population_state,
      unselected_source_records=unselected_source_records,registration_state=registration_state,
      temporal_scope_module=temporal_scope_module,candidate_applications=candidate_applications,
      bibliography_conflicts=bibliography_conflicts,query_set_evaluate=query_set_evaluate)
def identity_source_valid(value):
    if not isinstance(value,dict) or not all(value.get(k) for k in ("source_url","source_locator","quote","subject_name","determination")):return False
    host=(urlsplit(safe_url(value["source_url"])).hostname or "").lower()
    domains=OFFICIAL+("cninfo.com.cn","szse.cn","sse.com.cn","bse.cn","gov.cn","gov.hk","sec.gov","companieshouse.gov.uk")
    return any(host==d or host.endswith("."+d) for d in domains)
def verify_original_patent_document_identity(c,value,pubs):
    """Verify cached original office publication mirrors, not mirror web claims.

    The core remains standard-library-only. PDF interpretation is an explicit
    human/host visual review, bound to immutable PDF bytes and page extraction;
    this verifier validates that provenance and exact quoted page text.
    """
    require(value.get("source_class")=="original_patent_document_mirror","Unsupported original document source class")
    required=("source_url","source_artifact","artifact_sha256","publication_number","page_number","text_artifact","text_artifact_sha256","manual_review_artifact","manual_review_sha256","name_quote","address_quote","quote","subject_name","source_locator","determination")
    require(all(value.get(k) for k in required),"Original document mirror requires PDF, hashes, PN, page, name/address quotes, extraction and manual review")
    pn=value["publication_number"]
    require(isinstance(pn,str) and pn==number(pn) and pn in pubs,"Original document publication must be a retained version of the same application")
    safe_url(value["source_url"])
    url=urlsplit(str(value["source_url"]))
    require(url.scheme=="https" and url.netloc=="patentimages.storage.googleapis.com" and not url.query and not url.fragment,"Only the fixed HTTPS original patent PDF mirror is supported")
    require(re.fullmatch(r"/[0-9a-f]{2}/[0-9a-f]{2}/[0-9a-f]{2}/[0-9a-f]{14}/"+re.escape(pn)+r"\.pdf",url.path),"Original document URL must contain the exact fixed PN.pdf path")
    require(value.get("source_label")=="专利局原始公报的第三方托管副本","Mirror evidence must disclose third-party hosting")
    require(value["determination"] in ("target_entity","different_entity"),"Invalid original document identity determination")
    dbfile=c.execute("PRAGMA database_list").fetchone()[2]
    require(dbfile,"Original document cache verification requires a file-backed run")
    root=Path(dbfile).resolve().parent
    def checked_artifact(field,hash_field):
        path=(root/str(value[field])).resolve()
        require(path.is_relative_to(root) and path.is_file(),"Original identity artifacts must exist inside the run directory")
        data=path.read_bytes();expected=value[hash_field]
        require(isinstance(expected,str) and re.fullmatch(r"[0-9a-f]{64}",expected) and hashlib.sha256(data).hexdigest()==expected,"Original identity artifact SHA256 mismatch")
        return data
    pdf=checked_artifact("source_artifact","artifact_sha256")
    require(pdf.startswith(b"%PDF-") and b"%%EOF" in pdf[-2048:],"Original identity PDF bytes are absent or truncated")
    try:
        extracted=json.loads(checked_artifact("text_artifact","text_artifact_sha256").decode("utf-8-sig"))
        reviewed=json.loads(checked_artifact("manual_review_artifact","manual_review_sha256").decode("utf-8-sig"))
    except (UnicodeDecodeError,json.JSONDecodeError):raise ValidationError("Original identity extraction/review must be valid JSON")
    page=value["page_number"]
    require(isinstance(page,int) and not isinstance(page,bool) and page>=1,"Original identity page number must be one-based")
    require(extracted.get("pdf_sha256")==value["artifact_sha256"] and extracted.get("publication_number")==pn,"Page extraction must identify the exact original PDF and PN")
    require(extracted.get("extraction_tool") and extracted.get("page_count",0)>=page,"Page extraction provenance or page count is missing")
    pages=[x for x in extracted.get("pages",[]) if x.get("page_number")==page]
    require(len(pages)==1 and isinstance(pages[0].get("text"),str),"Original identity page extraction is absent or duplicated")
    text=pages[0]["text"]
    require(all(isinstance(value[k],str) and value[k].strip() and value[k] in text for k in ("name_quote","address_quote","quote")),"Identity quotes must occur exactly in the selected original page")
    require(value["subject_name"] in value["name_quote"] and value["name_quote"] in value["quote"] and value["address_quote"] in value["quote"],"Identity quote must connect the original party name and address on one page")
    require(reviewed.get("kind")=="manual_original_patent_identity_review" and reviewed.get("result")=="identity_confirmed" and reviewed.get("reviewer") and reviewed.get("reviewed_at"),"Original publication identity requires an explicit manual/host review record")
    for field,expected in (("publication_number",pn),("pdf_sha256",value["artifact_sha256"]),("page_number",page),("name_quote",value["name_quote"]),("address_quote",value["address_quote"]),("determination",value["determination"])):
        require(reviewed.get(field)==expected,"Original identity manual review disagrees with the cited PDF/page/quotes")
    require(reviewed.get("patent_office")==pubs[pn]["authority"] and reviewed.get("visual_review_performed") is True,"Original office identity and visual review must be confirmed")
    return True
def verify_identity_source(c,value,pubs):
    if value.get("source_class")=="patsnap":return verify_patsnap_identity(c,value,pubs)
    if value.get("source_class")=="original_patent_document_mirror":return verify_original_patent_document_identity(c,value,pubs)
    require(identity_source_valid(value),"External identity evidence needs an official source, locator, quote, subject and determination")
    return True
def verify_patsnap_identity(c,value,pubs):
    require(value.get("source_class")=="patsnap","Unsupported identity source class")
    require(all(value.get(k) for k in ("source_artifact","source_request","returned_publication_number","response_path","publication_path","name_path","name_value","address_path","address_value","source_locator","determination")),"Patsnap identity needs cached original bibliography, request, name/address paths and values")
    dbfile=c.execute("PRAGMA database_list").fetchone()[2]
    require(dbfile,"Cached Patsnap identity verification requires a file-backed run")
    root=Path(dbfile).resolve().parent;artifact=(root/value["source_artifact"]).resolve()
    require(artifact.is_relative_to(root) and artifact.is_file(),"Identity source artifact must exist inside the run directory")
    original=json.loads(artifact.read_text(encoding="utf-8-sig"))
    def at_path(tokens):
        require(isinstance(tokens,list) and tokens,"Original response path must be a nonempty array")
        node=original
        try:
            for token in tokens:node=node[token]
        except (KeyError,IndexError,TypeError):raise ValidationError("Identity path is absent from cached original response")
        return node
    if value.get("request_tool_path") or value.get("request_arguments_path"):
        require(value.get("request_tool_path") and value.get("request_arguments_path") and not value.get("request_path"),"Dual request paths must be supplied together without an ambiguous request_path")
        request={"tool":at_path(value["request_tool_path"]),"arguments":at_path(value["request_arguments_path"])}
    else:request=at_path(value.get("request_path",["source_request"]))
    require(request==value["source_request"] and request.get("tool")=="bibliography","Identity request must exactly match cached bibliography request")
    response=at_path(value["response_path"])
    for length in range(len(value["response_path"])+1):
        ancestor=original if not length else at_path(value["response_path"][:length])
        if isinstance(ancestor,dict):
            require(not ancestor.get("isError") and ancestor.get("success",True) is not False and ancestor.get("error_code",0) in (0,"0",None) and not ancestor.get("error"),"Identity source has an outer provider error")
    require(isinstance(response,dict) and response.get("success") is True and response.get("error_code",0) in (0,"0") and not response.get("isError"),"Cached identity bibliography is not a successful provider response")
    base=value["response_path"]
    for field in ("publication_path","name_path","address_path"):
        require(value[field][:len(base)]==base,"Identity field must belong to the declared original response")
    party_path=value["name_path"][len(base):]
    require(len(party_path)==7 and party_path[:1]==["data"] and isinstance(party_path[1],int) and party_path[2:4]==["bibliographic_data","parties"] and party_path[4] in ("applicants","assignees") and isinstance(party_path[5],int),"Identity name must be an original applicant/assignee, not an inventor or normalized search label")
    pn=number(value["returned_publication_number"])
    requested=request.get("arguments",{}).get("patent_number")
    require(isinstance(requested,str) and requested.strip(),"Identity bibliography request must retain its real patent_number string")
    requested_numbers={number(token.strip()) for token in requested.split(",") if token.strip()}
    require(pn in pubs and pn in requested_numbers,"Identity request/publication mismatch")
    require(value["publication_path"]==base+["data",party_path[1],"pn"],"Identity party and publication must come from the same bibliography record")
    require(number(at_path(value.get("publication_path",[])))==pn,"Cached bibliography returned a different publication")
    require(at_path(value["name_path"])==value["name_value"]==value.get("subject_name"),"Identity name differs from cached original value")
    require(at_path(value["address_path"])==value["address_value"],"Identity address/country differs from cached original value")
    require(value["name_path"][:-1]==value["address_path"][:-1] and value["name_path"][-1]=="name" and value["address_path"][-1] in ("address","country"),"Name and address/country must belong to the same original party record")
    require(isinstance(value["address_value"],str) and value["address_value"].strip(),"Identity address/country is empty")
    value["artifact_sha256"]=hashlib.sha256(artifact.read_bytes()).hexdigest()
    return True
def canonical_application_reference(reference):
    require(isinstance(reference,dict),"Bibliography application_reference is absent")
    doc=reference.get("doc_number");country=str(reference.get("country") or "").strip().upper()
    require(isinstance(doc,str) and doc.strip(),"Bibliography application document number is absent")
    value=number(doc)
    # PCT/CN... already carries an application identifier, never CNPCT/CN....
    if value.startswith("PCT") or (country and value.startswith(country)) or (not country and re.match(r"^[A-Z]{2}",value)):return value
    require(re.fullmatch(r"[A-Z]{2}",country),"Bibliography application country is absent")
    return country+value
def bibliography_ipcs(record_path,data):
    classification=data.get("classification_data");out=[]
    if not isinstance(classification,dict):return out
    ipcr=classification.get("classification_ipcr",{})
    if not isinstance(ipcr,dict):return out
    for field in ("main_classification","further_classification"):
        for index,value in enumerate(as_list(ipcr.get(field,[]))):
            symbol=None
            if isinstance(value,str):
                raw=re.sub(r"\s+","",value).upper()
                if re.fullmatch(r"[A-H]\d{2}[A-Z]\d{1,4}/\d{2,6}",raw):symbol=raw
            elif isinstance(value,dict):
                bits=[str(value.get(k,"")) for k in ("section","class","sub_class","main_group","sub_group")]
                if re.fullmatch(r"[A-H]",bits[0]) and re.fullmatch(r"\d{1,2}",bits[1]) and re.fullmatch(r"[A-Z]",bits[2]) and re.fullmatch(r"\d{1,4}",bits[3]) and re.fullmatch(r"\d{2,6}",bits[4]):
                    symbol=bits[0]+bits[1].zfill(2)+bits[2]+bits[3]+"/"+bits[4]
            if symbol:
                path=record_path+["bibliographic_data","classification_data","classification_ipcr",field]
                if isinstance(ipcr.get(field),list):path=path+[index]
                out.append({"symbol":symbol,"source_path":path})
    return out
def prepare_bibliography(c,p):
    pn=number(p.get("publication_number"));row=c.execute("SELECT * FROM publications WHERE id=?",(pn,)).fetchone()
    require(row,"Bibliography publication must already be a retained search record")
    meta=json.loads(row["data"]);appid=row["application_id"]
    dbfile=c.execute("PRAGMA database_list").fetchone()[2];require(dbfile,"Bibliography cache import requires a file-backed run")
    root=Path(dbfile).resolve().parent;relative=p.get("source_artifact")
    require(isinstance(relative,str) and relative,"Bibliography needs the original cache artifact")
    path=(root/relative).resolve();require(path.is_relative_to(root) and path.is_file(),"Bibliography source must exist inside the run directory")
    original_bytes=path.read_bytes();original=json.loads(original_bytes.decode("utf-8-sig"))
    def at_path(tokens):
        require(isinstance(tokens,list) and tokens,"Bibliography source path must be a nonempty array")
        node=original
        try:
            for token in tokens:node=node[token]
        except (KeyError,IndexError,TypeError):raise ValidationError("Bibliography source path is absent")
        return node
    if p.get("request_tool_path") or p.get("request_arguments_path"):
        require(p.get("request_tool_path") and p.get("request_arguments_path") and not p.get("request_path"),"Bibliography request paths are incomplete/ambiguous")
        request={"tool":at_path(p["request_tool_path"]),"arguments":at_path(p["request_arguments_path"])}
    else:request=at_path(p.get("request_path",["source_request"]))
    require(request==p.get("source_request") and request.get("tool")=="bibliography","Bibliography request differs from the original cache")
    arguments=request.get("arguments",{});requested=arguments.get("patent_number")
    require(isinstance(requested,str) and pn in {number(x.strip()) for x in requested.split(",") if x.strip()},"Bibliography publication was not requested in the original batch")
    response_path=p.get("response_path");response=at_path(response_path)
    for length in range(len(response_path)+1):
        ancestor=original if not length else at_path(response_path[:length])
        if isinstance(ancestor,dict):
            require(not ancestor.get("error") and not ancestor.get("isError") and ancestor.get("success",True) is not False and ancestor.get("status",True) is not False and ancestor.get("error_code",0) in (0,"0",None),"Bibliography source contains a transport/tool/business error")
    require(isinstance(response,dict) and response.get("success") is True and isinstance(response.get("data"),list),"Bibliography source is not a successful original data array")
    index=p.get("record_index")
    require(isinstance(index,int) and not isinstance(index,bool) and 0<=index<len(response["data"]),"Bibliography source record index is invalid")
    record_path=response_path+["data",index]
    if "record_path" in p:require(p["record_path"]==record_path,"Bibliography record path/index mismatch")
    record=response["data"][index]
    require(isinstance(record,dict) and number(record.get("pn"))==pn,"Bibliography returned a different publication at the declared index")
    data=record.get("bibliographic_data");require(isinstance(data,dict),"Bibliography bibliographic_data is absent")
    source_apno=canonical_application_reference(data.get("application_reference"))
    require(source_apno==meta["application_number"],"Bibliography application_reference differs from retained application")
    if p.get("application_number"):require(number(p["application_number"])==source_apno,"Bibliography requested application number mismatch")
    publication_reference=data.get("publication_reference")
    if not isinstance(publication_reference,dict):publication_reference={}
    if all(publication_reference.get(k) for k in ("country","doc_number","kind")):
        country=str(publication_reference["country"]).upper();doc=number(publication_reference["doc_number"])
        assembled=(doc if doc.startswith(country) else country+doc)+number(publication_reference["kind"])
        require(assembled==pn,"Bibliography publication_reference differs from returned PN")
    raw_type=data.get("patent_type");mapped=BIBLIO_TYPES.get(str(raw_type),"unknown")
    dates={}
    for field,ref in (("filing_date",data.get("application_reference",{})),("publication_date",publication_reference)):
        value=ref.get("date");dates[field]=None if value in (None,"",0,"0") else date_value(value)
    artifact_hash=hashlib.sha256(original_bytes).hexdigest();bid="bib-"+digest([pn,str(path.relative_to(root)),artifact_hash,record_path])[:24]
    app=json.loads(c.execute("SELECT data FROM applications WHERE id=?",(appid,)).fetchone()[0]);conflicts=[]
    known_types={meta.get("patent_type"),app.get("patent_type")}-{None,"unknown"}
    known_types|={json.loads(r[0]).get("patent_type") for r in c.execute("SELECT data FROM publications WHERE application_id=?",(appid,))}-{None,"unknown"}
    if mapped!="unknown" and any(t!=mapped for t in known_types):
        conflicts.append({"field":"patent_type","search_values":sorted(known_types),"bibliography_value":mapped,"provider_value":raw_type,"source_id":bid})
    for field,value in dates.items():
        if not value:continue
        existing={"publication":meta.get(field)}
        if field=="filing_date":existing["application"]=app.get(field)
        for target,old in existing.items():
            if old and old!=value:conflicts.append({"field":field,"target":target,"search_value":old,"bibliography_value":value,"source_id":bid})
    return sanitized({"id":bid,"publication_number":pn,"application_id":appid,"application_number":source_apno,
        "source_class":"patsnap","source_provider":p.get("source_provider") or "Patsnap Patent Briefing CN",
        "source_artifact":str(path.relative_to(root)),"artifact_sha256":artifact_hash,"record_path":record_path,
        "source_request":request,"response_path":response_path,"record_index":index,
        "acquired_at":original.get("acquired_at") or p.get("acquired_at"),"source_endpoint":safe_url(original.get("endpoint")),
        "record_original":record,"parties_original":data.get("parties",{}),"classifications_original":data.get("classification_data",{}),
        "ipcs":bibliography_ipcs(record_path,data),"provider_patent_type":raw_type,"normalized_patent_type":mapped,
        "type_mapping_source":BIBLIO_TYPE_SOURCE,"dates":dates,"conflicts":conflicts})
def import_bibliographies(c,payload):
    out=[]
    for p in as_list(payload):
        item=prepare_bibliography(c,p);bid=item["id"];pn=item["publication_number"];appid=item["application_id"]
        previous=c.execute("SELECT data FROM bibliographies WHERE id=?",(bid,)).fetchone()
        if previous:
            old=json.loads(previous[0]);require(old["record_original"]==item["record_original"],"Bibliography cache identity collision")
            item["conflicts"]=[json.loads(s) for s in sorted({dump(x) for x in old.get("conflicts",[])+item["conflicts"]})]
        c.execute("INSERT OR REPLACE INTO bibliographies(id,publication_id,application_id,data,conflicts) VALUES(?,?,?,?,?)",(bid,pn,appid,dump(item),dump(item["conflicts"])))
        changes=[];mapped=item["normalized_patent_type"]
        if mapped!="unknown" and not any(x["field"]=="patent_type" for x in item["conflicts"]):
            for table,key in (("publications",pn),("applications",appid)):
                row=c.execute("SELECT data FROM "+table+" WHERE id=?",(key,)).fetchone();meta=json.loads(row[0])
                if meta.get("patent_type")=="unknown":
                    meta["patent_type"]=mapped;meta["type_basis"]="bibliography_explicit"
                    meta["bibliography_type_source"]={"id":bid,"provider_value":item["provider_patent_type"],"field_path":item["record_path"]+["bibliographic_data","patent_type"],"mapping_source":BIBLIO_TYPE_SOURCE}
                    c.execute("UPDATE "+table+" SET data=? WHERE id=?",(dump(meta),key));changes.append(table)
        out.append({"id":bid,"publication_number":pn,"application_id":appid,"patent_type":mapped,"type_updates":changes,"conflicts":item["conflicts"],"cached":bool(previous)})
    event(c,"bibliography-import",{"records":len(out),"type_updates":sum(bool(x["type_updates"]) for x in out)})
    return out
def bibliography_conflicts(c,appid=None):
    sql="SELECT application_id,publication_id,conflicts FROM bibliographies"+(" WHERE application_id=?" if appid else "")
    return [{**conflict,"application_id":r["application_id"],"publication_number":r["publication_id"]} for r in c.execute(sql,(appid,) if appid else ()) for conflict in json.loads(r["conflicts"])]

_AUXILIARY_MODULE=None
def auxiliary_module():
    global _AUXILIARY_MODULE
    if _AUXILIARY_MODULE is None:
        spec=importlib.util.spec_from_file_location("pp_auxiliary",Path(__file__).with_name("auxiliary_records.py"))
        _AUXILIARY_MODULE=importlib.util.module_from_spec(spec);spec.loader.exec_module(_AUXILIARY_MODULE)
    return _AUXILIARY_MODULE

def auxiliary_context():
    return argparse.Namespace(require=require,ValidationError=ValidationError,number=number,digest=digest,dump=dump,event=event,as_list=as_list)

_DOCUMENT_IMAGES_MODULE=None

def document_images_module():
    global _DOCUMENT_IMAGES_MODULE
    if _DOCUMENT_IMAGES_MODULE is None:
        spec=importlib.util.spec_from_file_location("pp_document_images",Path(__file__).with_name("document_images.py"))
        _DOCUMENT_IMAGES_MODULE=importlib.util.module_from_spec(spec);spec.loader.exec_module(_DOCUMENT_IMAGES_MODULE)
    return _DOCUMENT_IMAGES_MODULE

_ORIGINAL_CLAIMS_MODULE=None

def original_claims_module():
    global _ORIGINAL_CLAIMS_MODULE
    if _ORIGINAL_CLAIMS_MODULE is None:
        spec=importlib.util.spec_from_file_location("pp_original_claims",Path(__file__).with_name("original_document_claims.py"))
        _ORIGINAL_CLAIMS_MODULE=importlib.util.module_from_spec(spec);spec.loader.exec_module(_ORIGINAL_CLAIMS_MODULE)
    return _ORIGINAL_CLAIMS_MODULE

def original_claims_context():
    return argparse.Namespace(require=require,ValidationError=ValidationError,number=number,claim_blocks=claim_blocks)

def prepare_auxiliary(c,p,cache=None):return auxiliary_module().prepare(c,p,auxiliary_context(),cache)
def import_auxiliary(c,payload):return auxiliary_module().import_records(c,payload,auxiliary_context())

def legal_status_snapshot(c,items=None):
    module=auxiliary_module();items=module.records(c) if items is None else items
    observed,_=module.views(items);by_app=collections.defaultdict(list)
    for row in c.execute("SELECT id,application_id,data FROM publications ORDER BY id"):
        meta=json.loads(row["data"]);state=observed.get(row["id"])
        by_app[row["application_id"]].append(state or {"publication_number":row["id"],"status":meta.get("legal_status") or "unknown",
            "observation_ids":[],"latest_observed_at":None,"basis":"retained_search_metadata; acquisition-time status not independently verified"})
    aggregate={}
    for appid,values in by_app.items():
        statuses={v["status"] for v in values};known=statuses-{None,"","unknown"}
        aggregate[appid]={"status":next(iter(statuses)) if len(statuses)==1 and known else "unknown",
            "conflict":len(known)>1 or any(v.get("observation_conflict") for v in values),
            "partial":any(not v["observation_ids"] for v in values),"publication_observations":values,
            "temporal_basis":"Acquisition-time observations; not a reconstruction of status at the search cutoff."}
    return observed,aggregate

def application_date_conflicts(c,appid=None):
    """Retain date disagreements from both search versions and bibliography sources."""
    dates=[x for x in bibliography_conflicts(c,appid) if x["field"] in ("filing_date","publication_date")]
    sql="SELECT id,data FROM applications"+(" WHERE id=?" if appid else "")
    for row in c.execute(sql,(appid,) if appid else ()):
        for conflict in json.loads(row["data"]).get("metadata_conflicts",[]):
            if conflict.get("field") in ("filing_date","publication_date"):
                sources=[];keys=("apdt","filing_date") if conflict["field"]=="filing_date" else ("pbdt","pub_date","publication_date")
                for pubrow in c.execute("SELECT id,data FROM publications WHERE application_id=? ORDER BY id",(row["id"],)):
                    pub=json.loads(pubrow["data"]);raw=pub.get("metadata_original",{})
                    sources.append({"publication_number":pubrow["id"],"value":pub.get(conflict["field"]),"raw_fields":[{"path":["metadata_original",key],"value":raw[key]} for key in keys if key in raw]})
                dates.append({**conflict,"application_id":row["id"],"source_class":"retained_search_versions","source_id":"search:"+row["id"],"publication_sources":sources})
    return dates

def import_population_reviews(c,payload):
    entities={e["id"]:e for e in rows_data(c,"entities")}
    entity_hash=digest(sorted(entities.values(),key=lambda e:e["id"]))
    target={k:e for k,e in entities.items() if e.get("confirmed") and e.get("relation") in ("root","subsidiary","historical")}
    names=lambda e:{legal_name_key(x) for x in {e["name"],*array(e.get("aliases"))}}
    target_names=set().union(*(names(e) for e in target.values())) if target else set()
    current_target={k:e for k,e in target.items() if e.get("relation") in ("root","subsidiary") and not e.get("same_legal_entity_as")}
    current_target_names=set().union(*(names(e) for e in current_target.values())) if current_target else set()
    count=0
    for item in as_list(payload):
        p=dict(item);appid=p.get("application_id");status=p.get("status")
        app=c.execute("SELECT data FROM applications WHERE id=?",(appid,)).fetchone()
        require(app,"Population review references unknown candidate application")
        require(status in ("included","excluded","pending"),"Population status must be included/excluded/pending")
        require(isinstance(p.get("reason"),str) and p["reason"].strip(),"Population review requires an explicit reason")
        pubs={r["id"]:json.loads(r["data"]) for r in c.execute("SELECT id,data FROM publications WHERE application_id=?",(appid,))}
        evidence=p.get("assignee_evidence",[]);require(isinstance(evidence,list),"assignee_evidence must be an array")
        observed_names=set()
        for ev in evidence:
            pub=pubs.get(number(ev.get("publication_number")));field=ev.get("field")
            require(pub and field in ("original_assignee","original_assignees","applicant","current_assignee","current_assignees"),"Review evidence must identify a candidate publication and raw assignee field")
            raw=pub["metadata_original"]
            require(field in raw and dump(raw[field])==dump(ev.get("value")),"Review assignee evidence differs from exact original value")
            choices=array(raw[field]);name=ev.get("matched_name")
            require(name in choices,"matched_name must exactly match one raw assignee token")
            observed_names.add(name)
        ids=p.get("matched_entity_ids",[])
        require(isinstance(ids,list) and len(ids)==len(set(ids)),"matched_entity_ids must be a unique array")
        matched=[]
        for eid in ids:
            e=entities.get(eid)
            require(e and e.get("confirmed") and {legal_name_key(x) for x in observed_names}&names(e),"Matched entity must be verified and NFKC-equivalent to evidenced raw assignee")
            matched.append(e)
        external=p.get("identity_source")
        if external:
            verify_identity_source(c,external,pubs)
            require(external["subject_name"] in observed_names,"Official identity subject must match evidenced raw assignee")
        if status!="pending":require(evidence,"Decided candidate requires exact raw assignee evidence")
        if status=="included":
            require(p.get("reason_code")=="target_entity","Included candidate requires target_entity reason")
            external_target=external and external["determination"]=="target_entity" and external.get("target_entity_id") in target
            require(any(e["id"] in target for e in matched) or external_target,"Included candidate needs a verified target entity match or official identity link")
        elif status=="excluded":
            require(p.get("reason_code") in ("different_entity","outside_control_period"),"Exclusion must establish different identity or an evidenced control-period boundary; missing text is not an exclusion reason")
            require(not re.search(r"(?i)(缺.{0,3}(全文|说明书|权利要求)|没.{0,3}(文本|全文)|无.{0,3}(文本|全文)|missing.{0,20}(text|claim|description)|no.{0,5}full.?text|quota|额度|解析失败)",p["reason"]),"Missing full text, resource limits or parsing failure cannot justify exclusion")
            all_names={legal_name_key(x) for pub in pubs.values() for x in pub["original_assignees"]+pub["current_assignees"]}
            if p["reason_code"]=="different_entity":
                require(not (all_names&target_names),"Candidate contains a verified target assignee; different_entity cannot exclude it")
                foreign=any(e.get("relation") in ("excluded","related") for e in matched)
                require(foreign or (external and external["determination"]=="different_entity"),"Different-entity exclusion needs verified non-target identity or official identity evidence")
            else:
                require(not any(x["field"]=="filing_date" for x in application_date_conflicts(c,appid)),"Conflicting filing dates cannot justify control-period exclusion")
                period=p.get("control_period_evidence",{})
                require(isinstance(period,dict) and identity_source_valid(period),"Control-period exclusion needs official period evidence")
                require(period.get("subject_name") in observed_names and period.get("determination")=="outside_control_period","Control-period evidence subject/determination mismatch")
                require(any(e["id"] in target for e in matched),"Control-period exclusion must identify the verified historical target entity")
                relevant=date_value(period.get("relevant_date"));before=date_value(period.get("control_from"));after=date_value(period.get("control_to"))
                require(relevant and (before or after) and ((before and relevant<before) or (after and relevant>after)),"Relevant date is not outside the evidenced control period")
                require(relevant==json.loads(app[0]).get("filing_date"),"Control-period relevant date must equal the candidate filing date")
                current={legal_name_key(x) for pub in pubs.values() for x in pub["current_assignees"]}
                require(not current&current_target_names,"Current verified target holding cannot be excluded solely by a historical filing date")
        p.update({"candidate_snapshot_hash":application_scope_snapshot(c,appid,entity_hash),"reviewed_at":p.get("reviewed_at") or now()})
        c.execute("INSERT OR REPLACE INTO population_reviews VALUES(?,?)",(appid,dump(sanitized(p))));count+=1
    event(c,"population-review-import",{"count":count})
    return {"population_reviews_imported":count,"counts":dict(collections.Counter(population_state(c).values()))}
def normalize_type(raw,pn,authority):
    v=str(raw.get("patent_type") or raw.get("type") or "").lower()
    m={"发明":"invention","发明专利":"invention","invention":"invention","实用新型":"utility_model","utility":"utility_model","utility_model":"utility_model","外观设计":"design","design":"design"}
    if v in m: return m[v],"provider"
    if authority=="CN":
        if re.search(r"[UYSD]\d?$",pn): return ("utility_model" if re.search(r"[UY]\d?$",pn) else "design"),"CN_document_kind"
        if re.search(r"[ABC]\d?$",pn): return "invention","CN_document_kind"
    if authority=="US" and pn.startswith("USD"): return "design","US_design_number"
    if authority in ("WO","EP","US") and re.search(r"[AB]\d?$",pn): return "invention","document_kind"
    return "unknown","unresolved"
def normalize_record(raw,provider):
    require(isinstance(raw,dict),"Patent record must be object")
    pn=number(raw.get("pn") or raw.get("publication_number") or raw.get("pub_number"))
    ap=number(raw.get("apno") or raw.get("application_number") or raw.get("app_number"))
    require(pn and re.match(r"^[A-Z]{2}",pn),"Missing/invalid publication number")
    require(ap,"Application number required for application-level completion")
    authority=str(raw.get("authority") or pn[:2]).upper()
    require(authority==pn[:2],"Publication authority mismatch")
    if not re.match(r"^[A-Z]{2}",ap): ap=authority+ap
    typ,tbasis=normalize_type(raw,pn,authority)
    return {"id":pn,"application_id":authority+":"+ap,"application_number":ap,"publication_number":pn,
      "patent_id":raw.get("patent_id"),"authority":authority,"title":str(raw.get("title") or ""),
      "patent_type":typ,"type_basis":tbasis,"filing_date":date_value(raw.get("apdt") or raw.get("filing_date")),
      "publication_date":date_value(raw.get("pbdt") or raw.get("pub_date") or raw.get("publication_date")),
      "original_assignees":array(raw.get("original_assignee") or raw.get("original_assignees") or raw.get("applicant")),
      "current_assignees":array(raw.get("current_assignee") or raw.get("current_assignees")),
      "inventors":array(raw.get("inventor") or raw.get("inventors")),"ipc":array(raw.get("ipc") or raw.get("ipc_class")),
      "legal_status":raw.get("legal_status") or "unknown","source_provider":provider,"source_url":safe_url(raw.get("source_url")),
      "acquired_at":raw.get("acquired_at") or now(),"metadata_original":sanitized(raw)}
def merge_application(c,item):
    appid=item["application_id"]
    row=c.execute("SELECT data FROM applications WHERE id=?",(appid,)).fetchone()
    app=json.loads(row[0]) if row else {"id":appid,"application_number":item["application_number"],"authority":item["authority"],"publication_numbers":[],"original_assignees":[],"current_assignees":[],"inventors":[],"ipc":[],"patent_type":item["patent_type"],"type_basis":item["type_basis"],"title":item["title"],"filing_date":item["filing_date"],"publication_date":None,"legal_status":"unknown","metadata_conflicts":[]}
    for k in ("original_assignees","current_assignees","inventors","ipc"): app[k]=sorted(set(app.get(k,[])+item.get(k,[])))
    app["publication_numbers"]=sorted(set(app["publication_numbers"]+[item["publication_number"]]))
    if item["patent_type"]!="unknown":
        require(app["patent_type"] in ("unknown",item["patent_type"]),"Conflicting patent types for "+appid)
        app["patent_type"]=item["patent_type"]
    if item["filing_date"] and app.get("filing_date") and item["filing_date"]!=app["filing_date"]:
        conflict={"field":"filing_date","values":[app["filing_date"],item["filing_date"]]}
        if conflict not in app["metadata_conflicts"]: app["metadata_conflicts"].append(conflict)
    if not app.get("filing_date"): app["filing_date"]=item["filing_date"]
    if not app.get("publication_date") or (item["publication_date"] and item["publication_date"]>=app["publication_date"]):
        app["publication_date"]=item["publication_date"]; app["title"]=item["title"] or app["title"]; app["legal_status"]=item["legal_status"]
    c.execute("INSERT OR REPLACE INTO applications VALUES(?,?)",(appid,dump(app)))
    old=c.execute("SELECT application_id FROM publications WHERE id=?",(item["id"],)).fetchone()
    require(not old or old[0]==appid,"Publication assigned to conflicting application")
    c.execute("INSERT OR REPLACE INTO publications VALUES(?,?,?)",(item["id"],appid,dump(item)))
def init_run(c,a):
    require(not get_meta(c,"run"),"Already initialized; new snapshot requires new database")
    asof=date_value(a.as_of) or dt.datetime.now(dt.timezone(dt.timedelta(hours=8))).date().isoformat()
    scope=read_input(a.scope) if a.scope else {}
    scope.setdefault("jurisdictions","all"); scope.setdefault("start_date",None)
    scope.setdefault("technical_types",["invention","utility_model"]); scope.setdefault("design_mode","catalogue")
    scope.setdefault("require_population_review",not scope.get("synthetic",False))
    run={"run_id":"pp-"+digest(a.company+now())[:16],"company":a.company,"as_of_date":asof,"created_at":now(),"scope":scope,"status":"collecting","scope_confirmed":False,"limitations":[]}
    set_meta(c,"run",run); event(c,"init",run); return run
def import_entities(c,p):
    for e in as_list(p):
        require(isinstance(e,dict) and e.get("id") and e.get("name"),"Entity id/name required")
        require(e.get("relation") in ("root","subsidiary","historical","alias","related","excluded"),"Invalid entity relation")
        if e.get("confirmed"): require(e.get("source_url") and e.get("source_locator"),"Confirmed entity requires source/locator")
        e=dict(e); e["source_url"]=safe_url(e.get("source_url"))
        c.execute("INSERT OR REPLACE INTO entities VALUES(?,?)",(e["id"],dump(sanitized(e))))
    run=run_info(c); run["scope_confirmed"]=False; set_meta(c,"run",run)
    event(c,"entities-import",{"count":len(as_list(p))}); return {"entities_imported":len(as_list(p))}
def scope_confirm(c,p):
    included=[e for e in rows_data(c,"entities") if e.get("confirmed") and e.get("relation") in ("root","subsidiary","historical")]
    require(included,"No confirmed included entities")
    require(p.get("confirmed") is True and p.get("basis"),"Confirmation requires confirmed:true and basis")
    require(p.get("reviewed_through")==run_info(c)["as_of_date"],"Scope must be reviewed through cutoff")
    r=run_info(c); r["scope_confirmed"]=True; r["scope_confirmation"]=sanitized(p)
    r["entity_snapshot_hash"]=digest(sorted(included,key=lambda x:x["id"])); set_meta(c,"run",r)
    event(c,"scope-confirm",p); return {"scope_confirmed":True,"included_entities":len(included)}
def import_capabilities(c,p):
    for x in as_list(p):
        require(x.get("id") and x.get("status") in ("verified","unavailable","failed","unverified"),"Invalid capability")
        if x["status"]=="verified": require(x.get("checked_at") and x.get("evidence"),"Verified capability requires time/evidence")
        c.execute("INSERT OR REPLACE INTO capabilities VALUES(?,?)",(x["id"],dump(sanitized(x))))
    event(c,"capability-import",{"count":len(as_list(p))}); return {"capabilities_imported":len(as_list(p))}
def unwrap_result(p):
    v=p
    for _ in range(6):
        require(isinstance(v,dict),"Provider payload must be an object")
        require(not v.get("isError") and v.get("success",True) is not False,"Provider error is not an empty result")
        require(not v.get("error"),"Provider transport error is not an empty result")
        if "error_code" in v: require(v["error_code"] in (0,"0",None),"Provider business error is not an empty result")
        if "transport" in v:v=v["transport"];continue
        if "jsonrpc" in v and "result" in v:v=v["result"];continue
        if "structuredContent" in v:
            v=v["structuredContent"];continue
        if "data" in v:
            v=v["data"];continue
        if "content" in v and not any(k in v for k in ("records","results")):
            try:v=json.loads("\n".join(x.get("text","") for x in v["content"] if x.get("type")=="text"))
            except json.JSONDecodeError:raise ValidationError("Tool result is not structured patent data")
            continue
        return v
    raise ValidationError("Provider wrappers nested too deeply")
def stable_page(value):
    if isinstance(value,dict):
        return {k:stable_page(v) for k,v in value.items() if k not in ("acquired_at","retrieved_at","fetched_at","fetch_timestamp")}
    if isinstance(value,list):return [stable_page(v) for v in value]
    return value
def import_search(c,p):
    q=p.get("query"); require(q and q.get("id"),"search-import requires query")
    require(q.get("kind") in ("original","current"),"Query kind must be original/current")
    require(q.get("entity_id"),"Query entity_id required")
    require(c.execute("SELECT 1 FROM entities WHERE id=?",(q["entity_id"],)).fetchone(),"Unknown entity")
    qid=q["id"]; off=p.get("offset",0); require(isinstance(off,int) and off>=0,"Invalid offset")
    result=unwrap_result(p.get("result",p)); records=p.get("records",result.get("records",result.get("results")))
    require(isinstance(records,list),"records/results must be array")
    expected=q.get("expected_count",result.get("total_search_result_count"))
    require(isinstance(expected,int) and expected>=0,"Expected count required")
    observed=result.get("total_search_result_count")
    if isinstance(p.get("raw"),dict):
        raw_result=unwrap_result(p["raw"])
        raw_total=raw_result.get("total_search_result_count")
        if raw_total is not None:
            require(observed in (None,raw_total),"Conflicting provider totals")
            observed=raw_total
    if observed is not None:
        require(isinstance(observed,int) and observed>=0 and observed==expected,"Provider total conflicts with expected_count")
    if "result_count" in result:require(result["result_count"]==len(records),"Provider page count conflicts with records")
    require(off+len(records)<=expected,"Page extends beyond expected population")
    req=sanitized(q.get("request",{})); old=c.execute("SELECT * FROM queries WHERE id=?",(qid,)).fetchone()
    require("verification_only" not in req or isinstance(req["verification_only"],bool),"verification_only must be an explicit boolean")
    if old:
        require(old["expected_count"]==expected and old["request"]==dump(req) and old["entity_id"]==q["entity_id"] and old["kind"]==q["kind"],"Frozen query changed")
    else: c.execute("INSERT INTO queries(id,entity_id,kind,expected_count,request) VALUES(?,?,?,?,?)",(qid,q["entity_id"],q["kind"],expected,dump(req)))
    if observed is not None:
        c.execute("UPDATE queries SET observed_count=? WHERE id=?",(observed,qid))
    items=[normalize_record(x,q.get("provider","Patsnap Advanced Patent Search")) for x in records]
    require(len({x["id"] for x in items})==len(items),"Duplicate publication within page")
    # Exclude retrieval timestamps from page identity so cache replay is idempotent.
    pagehash=digest(stable_page(items))
    page=c.execute("SELECT * FROM pages WHERE query_id=? AND offset=?",(qid,off)).fetchone()
    if page:
        require(page["body_hash"]==pagehash,"Frozen page changed"); return {"query_id":qid,"offset":off,"cached":True,"records":len(items)}
    for oldp in c.execute("SELECT body_hash FROM pages WHERE query_id=?",(qid,)):
        require(not items or oldp[0]!=pagehash,"Repeated page at a different offset")
    oldids={r[0] for r in c.execute("SELECT publication_id FROM query_results WHERE query_id=?",(qid,))}
    require(not({x["id"] for x in items}&oldids),"Overlapping pages within query; reconcile pagination")
    cutoff=run_info(c)["as_of_date"]
    for item in items:
        require(item["publication_date"],"Publication date required for cutoff check")
        require(item["publication_date"]<=cutoff,"Publication after frozen cutoff; fix query boundary")
        merge_application(c,item); c.execute("INSERT INTO query_results VALUES(?,?)",(qid,item["id"]))
    c.execute("INSERT INTO pages VALUES(?,?,?,?,?)",(qid,off,pagehash,len(items),dump(sanitized(p.get("raw",result)))))
    c.execute("UPDATE queries SET complete=0 WHERE id=?",(qid,))
    event(c,"search-import",{"query_id":qid,"offset":off,"count":len(items)})
    return {"query_id":qid,"offset":off,"records":len(items),"expected_count":expected}
def complete_query(c,qid):
    q=c.execute("SELECT * FROM queries WHERE id=?",(qid,)).fetchone(); require(q,"Unknown query")
    require(q["observed_count"]==q["expected_count"],"Provider total has not been verified")
    pages=list(c.execute("SELECT * FROM pages WHERE query_id=? ORDER BY offset",(qid,))); require(pages,"No pages")
    cursor=0
    for p in pages:
        require(p["offset"]==cursor,"Missing/noncontiguous page at offset "+str(cursor)); cursor+=p["record_count"]
    unique=c.execute("SELECT count(*) FROM query_results WHERE query_id=?",(qid,)).fetchone()[0]
    require(cursor==q["expected_count"]==unique,"Expected/raw/unique counts do not reconcile")
    c.execute("UPDATE queries SET complete=1,error=NULL WHERE id=?",(qid,))
    event(c,"query-complete",{"query_id":qid,"count":unique}); return {"query_id":qid,"complete":True,"count":unique}

def source_search_data(value):
    require(isinstance(value,dict) and not value.get("error") and not value.get("isError") and value.get("success",True) is not False and value.get("error_code",0) in (0,"0",None),"Source search transport error")
    if "transport" in value:return source_search_data(value["transport"])
    return unwrap_result(value.get("result",value))
def verified_query(c,qid,cache=None):
    cache={} if cache is None else cache
    if ("query",qid) in cache:return cache[("query",qid)]
    q=c.execute("SELECT * FROM queries WHERE id=?",(qid,)).fetchone();require(q,"Unknown leaf query: "+str(qid))
    require(q["complete"] and q["expected_count"]==q["observed_count"],"Leaf query is not source-count complete: "+qid)
    cursor=0;pubs=[]
    for page in c.execute("SELECT * FROM pages WHERE query_id=? ORDER BY offset",(qid,)):
        require(page["offset"]==cursor,"Leaf pages are not contiguous: "+qid)
        data=source_search_data(json.loads(page["raw"]));records=data.get("results",data.get("records"))
        require(isinstance(records,list),"Leaf raw results absent: "+qid)
        total=data.get("total_search_result_count")
        require(isinstance(total,int) and not isinstance(total,bool) and total==q["expected_count"],"Leaf raw provider total changed: "+qid)
        require(page["record_count"]==len(records) and data.get("result_count",len(records))==len(records),"Leaf raw page count changed: "+qid)
        pubs.extend(number(r.get("pn") or r.get("publication_number") or r.get("pub_number")) for r in records);cursor+=len(records)
    actual={r[0] for r in c.execute("SELECT publication_id FROM query_results WHERE query_id=?",(qid,))}
    require(cursor==len(pubs)==len(set(pubs))==q["expected_count"] and set(pubs)==actual,"Leaf result population changed: "+qid)
    answer={"id":qid,"entity_id":q["entity_id"],"kind":q["kind"],"count":cursor,"publications":actual,"request":json.loads(q["request"])}
    cache[("query",qid)]=answer;return answer
def query_set_evaluate(c,item,stack=None,cache=None):
    cache={} if cache is None else cache;stack=set() if stack is None else stack
    sid=item.get("id");require(sid and sid not in stack,"Missing/cyclic logical query set")
    if ("set",sid,digest(item)) in cache:return cache[("set",sid,digest(item))]
    require(item.get("entity_id") and c.execute("SELECT 1 FROM entities WHERE id=?",(item["entity_id"],)).fetchone(),"Unknown query-set entity")
    require(item.get("kind") in ("original","current") and item.get("query_text"),"Query set needs role and query text")
    stack=stack|{sid};typ=item.get("type");pubs=set();leafids=set()
    def leaf(qid,verification):
        q=verified_query(c,qid,cache)
        require(q["entity_id"]==item["entity_id"] and q["kind"]==item["kind"],"Logical set and leaf entity/role mismatch")
        require(bool(q["request"].get("verification_only",False))==verification,"Control/ordinary query role mismatch")
        leafids.add(qid);return q
    if typ=="direct":
        q=leaf(item.get("leaf_query_id"),False)
        require(q["request"].get("query_text")==item["query_text"],"Direct set query text differs from source leaf")
        require(item.get("source_total_count")==q["count"] and not isinstance(item.get("source_total_count"),bool),"Direct logical count differs from source")
        pubs=q["publications"]
    elif typ=="empty_by_disjoint_anchors":
        require("source_total_count" in item and item["source_total_count"] is None and item.get("derived_count")==0 and not isinstance(item.get("derived_count"),bool),"Empty set must retain unknown source total and a separate derived zero")
        controls=item.get("controls",[]);require(isinstance(controls,list) and len(controls)==2,"Empty proof needs two singleton controls")
        anchors=[]
        for control in controls:
            anchor=number(control.get("anchor_publication_number"));q=leaf(control.get("query_id"),True)
            require(anchor and q["count"]==1 and q["publications"]=={anchor},"Control is not its explicit singleton anchor")
            require(q["request"].get("query_text")=="("+item["query_text"]+") OR PN:"+anchor,"Control request does not prove this empty query")
            anchors.append(anchor)
        require(len(set(anchors))==2 and len(leafids)==2,"Empty proof anchors/queries must be distinct")
    elif typ=="date_partition":
        evidence=item.get("parent_source",{});request=evidence.get("request",{})
        require(request.get("query_text")==item["query_text"] and request.get("sort_order")=="ASC" and request.get("sort_field")=="PBDT_YEARMONTHDAY","Partition parent needs the original ascending-date source request")
        data=source_search_data(evidence.get("raw_response",{}));total=data.get("total_search_result_count")
        require(isinstance(total,int) and not isinstance(total,bool) and total==item.get("source_total_count"),"Partition parent total lacks matching raw source evidence")
        records=data.get("results",data.get("records"));require(isinstance(records,list) and records,"Partition parent probe needs source records")
        earliest=min(date_value(r.get("pbdt") or r.get("publication_date")) for r in records)
        children=item.get("children",[]);require(isinstance(children,list) and len(children)>=2,"Partition needs date children")
        lower=date_value(item.get("date_start"));upper=date_value(item.get("date_end"));require(lower and upper and lower<=earliest<=upper<=run_info(c)["as_of_date"],"Partition does not cover earliest probe/cutoff")
        intervals=[];summed=0
        for child in children:
            row=c.execute("SELECT data FROM query_sets WHERE id=?",(child.get("query_set_id"),)).fetchone();require(row,"Missing child logical query set")
            spec=json.loads(row[0]);lo=date_value(child.get("date_from"));hi=date_value(child.get("date_to"))
            require(lo and hi and lower<=lo<=hi<=upper,"Child date interval outside parent")
            expected="("+item["query_text"]+") AND PBD:["+lo.replace("-","")+" TO "+hi.replace("-","")+"]"
            require(spec.get("query_text")==expected and spec.get("entity_id")==item["entity_id"] and spec.get("kind")==item["kind"],"Partition child does not restrict the same parent entity/query")
            result=query_set_evaluate(c,spec,stack,cache);intervals.append((lo,hi));summed+=result["logical_count"]
            require(not pubs&result["publications"],"Duplicate publication across date partitions")
            for pn in result["publications"]:
                meta=json.loads(c.execute("SELECT data FROM publications WHERE id=?",(pn,)).fetchone()[0])
                require(meta.get("publication_date") and lo<=meta["publication_date"]<=hi,"Publication falls outside its declared partition")
            pubs|=result["publications"];leafids|=result["leaf_query_ids"]
        intervals.sort();require(intervals[0][0]==lower and intervals[-1][1]==upper,"Partition dates do not cover parent interval")
        for previous,current in zip(intervals,intervals[1:]):require((dt.date.fromisoformat(previous[1])+dt.timedelta(days=1)).isoformat()==current[0],"Partition dates overlap or leave a gap")
        require(summed==len(pubs)==total,"Partition child totals/unique records do not equal parent source total")
    else:raise ValidationError("Unknown logical query set type")
    answer={"id":sid,"entity_id":item["entity_id"],"kind":item["kind"],"type":typ,"logical_count":len(pubs),"source_total_count":item.get("source_total_count"),"publications":pubs,"leaf_query_ids":leafids}
    cache[("set",sid,digest(item))]=answer;return answer
def import_query_sets(c,payload):
    result=[]
    for item in as_list(payload):
        item=sanitized(dict(item));value=query_set_evaluate(c,item)
        c.execute("INSERT OR REPLACE INTO query_sets VALUES(?,?,?,?)",(item["id"],item["entity_id"],item["kind"],dump(item)))
        result.append({k:v for k,v in value.items() if k not in ("publications","leaf_query_ids")})
    event(c,"query-set-import",{"sets":len(result)});return result
def query_plan_confirm(c,p):
    require(re.fullmatch(r"[a-f0-9]{64}",str(p.get("plan_hash",""))),"Frozen query plan needs its SHA256")
    specs=p.get("required_query_sets")
    if specs is None:
        specs=[]
        for sid in p.get("required_query_set_ids",[]):
            row=c.execute("SELECT data FROM query_sets WHERE id=?",(sid,)).fetchone();require(row,"Required query set absent; supply explicit planned spec for pending sets")
            item=json.loads(row[0]);specs.append({k:item[k] for k in ("id","entity_id","kind","query_text")})
    require(isinstance(specs,list) and specs and len({s.get("id") for s in specs})==len(specs),"Plan needs unique required logical sets")
    for spec in specs:
        require(all(spec.get(k) for k in ("id","entity_id","kind","query_text")) and spec["kind"] in ("original","current"),"Incomplete required query-set specification")
        require(c.execute("SELECT 1 FROM entities WHERE id=?",(spec["entity_id"],)).fetchone(),"Required query-set entity absent")
    contract={"plan_hash":p["plan_hash"],"required_query_sets":sorted(specs,key=lambda s:s["id"]),"required_query_set_ids":sorted(s["id"] for s in specs)}
    old=get_meta(c,"query_plan_contract")
    require(not old or old==contract,"Query plan is frozen; changed requirements need a new run snapshot")
    set_meta(c,"query_plan_contract",contract)
    run=run_info(c);run["scope"]["require_query_sets"]=True;set_meta(c,"run",run)
    event(c,"query-plan-confirm",{"plan_hash":contract["plan_hash"],"required_sets":len(specs)})
    return {"plan_hash":contract["plan_hash"],"required_query_sets":len(specs)}

def source_is_official(url):
    host=(urlsplit(url).hostname or "").lower()
    return any(host==x or host.endswith("."+x) for x in OFFICIAL)
def claim_blocks(text):
    matches=list(re.finditer(r"(?m)^\s*(\d{1,4})\s*[.、．]\s*",text))
    out=[]
    for i,m in enumerate(matches):
        start=m.start(1);end=matches[i+1].start(1) if i+1<len(matches) else len(text)
        while end>start and text[end-1].isspace():end-=1
        out.append({"number":int(m.group(1)),"text":text[start:end],"start":start,"end":end})
    return out
def chunk_plan(text,size=6000,overlap=240):
    """Legacy span reconstruction only; new imports use one whole source span."""
    spans=[]; start=0
    while start<len(text):
        end=min(len(text),start+size)
        if end<len(text):
            sep=text.rfind("\n",start+size//2,end)
            if sep>start: end=sep+1
        spans.append((start,end))
        if end==len(text): break
        start=max(start+1,end-overlap)
    return spans
def import_document(c,p):
    pn=number(p.get("publication_number"))
    row=c.execute("SELECT * FROM publications WHERE id=?",(pn,)).fetchone()
    require(row,"Publication must be imported before its text")
    meta=json.loads(row["data"]); appid=row["application_id"]
    require(p.get("document_type") in ("description","claims"),"Only description or claims can support technical completion")
    require(p.get("identity_verified") is True,"Source document identity has not been verified")
    require(number(p.get("returned_publication_number"))==pn,"Returned publication differs from requested publication")
    if p.get("application_number"):
        ap=number(p["application_number"])
        if not re.match(r"^[A-Z]{2}",ap): ap=meta["authority"]+ap
        require(ap==meta["application_number"],"Returned application mismatch")
    require(p.get("replace_by_related") is False,"Family replacement must explicitly be false")
    require(isinstance(p.get("complete"),bool) and isinstance(p.get("truncated"),bool),"Explicit complete/truncated booleans required")
    text=p.get("text")
    require(isinstance(text,str) and text.strip(),"Empty technical source")
    require(not re.match(r"(?is)^\s*(<!doctype html|<html|MCP API need|access denied|unauthorized)",text),"Error/HTML landing page is not a technical text")
    if text.lstrip().startswith(("{","[")):
        try:
            body=json.loads(text)
            require(not isinstance(body,(dict,list)),"JSON tool payload is not normalized technical source text")
        except json.JSONDecodeError:pass
    require(p.get("source_provider") and p.get("acquired_at") and p.get("language") and p.get("version"),"Source provider, acquired_at, language and version required")
    url=safe_url(p.get("source_url"))
    require(url or p.get("source_request"),"Source URL or exact MCP source_request required")
    source_class=p.get("source_class") or ("patsnap" if "patsnap" in p["source_provider"].lower() or "智慧芽" in p["source_provider"] else "official")
    if source_class=="official": require(url and source_is_official(url),"Official fallback must use a verified patent-office domain")
    if source_class=="synthetic": require(run_info(c)["scope"].get("synthetic") is True,"Synthetic source cannot enter a real run")
    require(source_class in ("patsnap","official","synthetic","original_patent_document_mirror","uploaded_patent_document"),"Unsupported source class")
    if source_class=="uploaded_patent_document":materials_module().verify_document(c,p,material_engine())
    mirror_proof=None
    if source_class=="original_patent_document_mirror":
        mirror_proof,_=original_claims_module().verify(c,p,original_claims_context())
    qualified=p["complete"] is True and p["truncated"] is False
    if qualified:
        require(p.get("completeness_basis"),"Complete source needs a verifiable completeness basis")
        require(not re.fullmatch(r"(?i)\s*(long|length|长|很长|长度.*)\s*",str(p["completeness_basis"])),"Text length alone is not completeness evidence")
    claims=[]
    if p["document_type"]=="claims":
        claims=claim_blocks(text)
        supplied=p.get("claims")
        if supplied is not None:
            require(isinstance(supplied,list) and len(supplied)==len(claims),"Structured claim blocks must match full source numbering")
            for provided,actual in zip(supplied,claims):
                require(provided.get("number")==actual["number"] and provided.get("text","").strip()==actual["text"],
                        "Claim number/text does not match the original numbered interval")
                if "depends_on" in provided:actual["depends_on"]=provided["depends_on"]
        if qualified:
            n=p.get("claim_count")
            require(isinstance(n,int) and n>=1,"Complete claims require source-declared claim_count")
            require([x["number"] for x in claims]==list(range(1,n+1)),"Missing/repeated/out-of-order claims")
    source=sanitized({k:v for k,v in p.items() if k not in ("text","claims")})
    source.update({"publication_number":pn,"application_id":appid,"source_url":url,"source_class":source_class,
                   "qualified":qualified,"claims":claims})
    if mirror_proof:source["verified_original_document"]=mirror_proof
    docid="doc-"+digest([pn,p["document_type"],p["version"],p["language"],digest(text)])[:24]
    old=c.execute("SELECT data FROM documents WHERE id=?",(docid,)).fetchone()
    if old:
        previous=json.loads(old[0])
        require(previous["qualified"]==qualified,"Identical text with changed qualification requires explicit new source version")
        return {"document_id":docid,"application_id":appid,"cached":True,"qualified":qualified,
                "chunk_ids":[x[0] for x in c.execute("SELECT id FROM chunks WHERE document_id=? ORDER BY ordinal",(docid,))]}
    c.execute("INSERT INTO documents VALUES(?,?,?,?,?,?,?)",(docid,appid,pn,p["document_type"],text,digest(text),dump(source)))
    ids=[]
    if qualified:
        # One source document is one reading unit. Existing multi-span records
        # remain untouched so historical evidence and completion IDs stay valid.
        for i,(start,end) in enumerate([(0,len(text))]):
            cid=docid+"-c"+str(i).zfill(4);ids.append(cid)
            c.execute("INSERT INTO chunks VALUES(?,?,?,?,?)",(cid,docid,i,start,end))
    event(c,"document-import",{"document_id":docid,"qualified":qualified,"application_id":appid})
    return {"document_id":docid,"application_id":appid,"qualified":qualified,"chunk_ids":ids}
def optional_rows_data(c,table):
    # Read-only consumers can inspect pre-migration snapshots without changing them.
    require(table in ("document_reviews","analysis_invalidations"),"Unsupported optional audit table")
    return rows_data(c,table) if c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",(table,)).fetchone() else []

def document_rejection_key(doc):
    return (doc["application_id"],doc["document_type"],doc["text_hash"])

def document_rejection_index(c):
    index=collections.defaultdict(list)
    for review in optional_rows_data(c,"document_reviews"):
        index[(review["application_id"],review["document_type"],review["source_text_hash"])].append(review["id"])
    return index

def document_is_eligible(c,doc,rejections=None):
    if not doc or json.loads(doc["data"]).get("qualified") is not True:return False
    index=document_rejection_index(c) if rejections is None else rejections
    return not index.get(document_rejection_key(doc))

def source_language(value):
    raw=str(value or "").strip().upper().replace("_","-")
    if raw in ("","UNKNOWN","UNDETERMINED"):return None
    return {"CN":"zh","ZH":"zh","ZH-CN":"zh","CHS":"zh","CNT":"zh-Hant","CHT":"zh-Hant","ZH-TW":"zh-Hant",
            "EN":"en","KR":"ko","KO":"ko","JP":"ja","JA":"ja"}.get(raw,raw.lower())

def description_intervals(text):
    """Actual anchored source paragraph intervals; never infer missing labels."""
    matches=list(re.finditer(r"(?m)^[ \t]*\[(\d{4,})\]",text));result={}
    for i,m in enumerate(matches):
        n=int(m.group(1));require(n not in result,"Repeated source paragraph number")
        result[n]=(m.end(),matches[i+1].start() if i+1<len(matches) else len(text))
    return result

def validate_support_documents(c,primary,payload,rejections=None):
    """Validate same-publication description regions supporting full claims.

    A support source remains independently qualified; reading selected regions
    does not attest full-description reading or fill primary-claim omissions.
    """
    require(isinstance(payload,list),"support_documents must be an array")
    require(not payload or primary["document_type"]=="claims","Only complete primary claims may use supporting descriptions")
    sources={primary["id"]:primary};normalized=[]
    primary_source=json.loads(primary["data"])
    for item in payload:
        require(isinstance(item,dict) and isinstance(item.get("document_id"),str),"Supporting source document_id required")
        sid=item["document_id"];require(sid not in sources,"Duplicate/primary document in support_documents")
        doc=c.execute("SELECT * FROM documents WHERE id=?",(sid,)).fetchone()
        require(doc and doc["application_id"]==primary["application_id"] and doc["publication_id"]==primary["publication_id"],
                "Supporting description must be the same publication and application as primary claims")
        require(doc["document_type"]=="description" and document_is_eligible(c,doc,rejections),"Supporting description must be qualified and not rejected")
        source=json.loads(doc["data"])
        require(source_language(source["language"]) and source_language(source["language"])==source_language(primary_source["language"]),"Primary and supporting original text languages differ or are unknown")
        if "source_text_hash" in item:require(item["source_text_hash"]==doc["text_hash"],"Stale supporting source text hash")
        regions=item.get("read_regions")
        require(isinstance(regions,list) and regions,"Supporting description needs actual reviewed read_regions")
        intervals=description_intervals(doc["text"]);checked=[]
        for region in regions:
            require(isinstance(region,dict) and region.get("reviewed") is True,"Supporting read region needs explicit reviewed=true")
            start,end=region.get("start"),region.get("end")
            require(type(start) is int and type(end) is int and 0<=start<end<=len(doc["text"]),"Supporting read region is outside exact source text")
            locator=region.get("locator")
            require(isinstance(locator,dict),"Supporting read region needs a verified source locator")
            if set(locator)=={"paragraph"}:
                raw=locator["paragraph"]
                require(type(raw) is int or isinstance(raw,str) and re.fullmatch(r"\d{4,}",raw),"Supporting paragraph locator invalid")
                number=int(raw);span=intervals.get(number)
                require(span and span[0]<=start<end<=span[1],"Supporting read region does not belong to specified paragraph")
                locator={"paragraph":str(number).zfill(4)}
            else:require(locator=={"source_span":True},"Supporting read region must identify an actual paragraph or exact source_span")
            checked.append({"start":start,"end":end,"locator":locator,"reviewed":True})
        checked.sort(key=lambda r:(r["start"],r["end"]))
        require(all(a["end"]<=b["start"] for a,b in zip(checked,checked[1:])),"Supporting read regions repeat or overlap")
        normalized.append({"document_id":sid,"source_text_hash":doc["text_hash"],"publication_number":doc["publication_id"],
            "document_type":"description","language":source["language"],"version":source["version"],
            "reading_scope":"selected_regions","read_regions":checked})
        sources[sid]=doc
    return normalized,sources

def evidence_in_read_regions(ev,support):
    return any(r["start"]<=ev["start"]<ev["end"]<=r["end"] for r in support["read_regions"])

def validate_support_evidence_locator(doc,ev):
    locator=ev["locator"]
    require(isinstance(locator,dict),"Supporting evidence needs an exact paragraph or source_span locator")
    if set(locator)=={"paragraph"}:
        raw=locator["paragraph"]
        require(type(raw) is int or isinstance(raw,str) and re.fullmatch(r"\d{4,}",raw),"Supporting evidence paragraph locator invalid")
        span=description_intervals(doc["text"]).get(int(raw))
        require(span and span[0]<=ev["start"]<ev["end"]<=span[1],"Supporting evidence does not belong to specified paragraph")
    else:require(locator=={"source_span":True},"Supporting evidence needs an exact paragraph or source_span locator")

def analysis_is_current(c,row,rejections=None):
    p=json.loads(row["data"])
    doc=c.execute("SELECT * FROM documents WHERE id=?",(row["document_id"],)).fetchone()
    if not (p.get("analysis_status")=="complete" and doc and doc["application_id"]==row["application_id"]
            and p.get("source_text_hash")==doc["text_hash"] and document_is_eligible(c,doc,rejections)):return False
    try:validate_support_documents(c,doc,p.get("support_documents",[]),rejections)
    except (ValidationError,KeyError,TypeError):return False
    return True

def import_document_reviews(c,payload):
    """Append source rejections; no acceptance/override command exists.

    The original text and structural qualification stay unchanged. Identical text
    under another version label remains rejected; a new complete source must be
    imported and read in full before it can support another analysis.
    """
    results=[]
    for p in as_list(payload):
        require(isinstance(p,dict) and p.get("decision")=="reject","Document review supports only explicit reject; no manual acceptance override")
        doc=c.execute("SELECT * FROM documents WHERE id=?",(p.get("document_id"),)).fetchone()
        require(doc,"Document review source is absent")
        if "application_id" in p:require(p["application_id"]==doc["application_id"],"Document review application mismatch")
        if "publication_number" in p:require(number(p["publication_number"])==doc["publication_id"],"Document review publication mismatch")
        if "source_text_hash" in p:require(p["source_text_hash"]==doc["text_hash"],"Document review text hash mismatch")
        require(p.get("reason_code") in ("truncated_tail","missing_formula","missing_text","parse_failure","wrong_document_content"),"Unsupported source rejection reason")
        require(all(isinstance(p.get(k),str) and p[k].strip() for k in ("reason","reviewer")),"Document rejection needs host-authored reason and reviewer")
        selected=p.get("evidence")
        require(isinstance(selected,list) and selected,"Document rejection requires exact original evidence for the observed defect")
        evidence=[]
        for i,choice in enumerate(selected):
            require(isinstance(choice,dict),"Document rejection evidence must be object")
            item=dict(choice);item["id"]="source-review-evidence-"+digest([doc["id"],i,choice])[:24]
            evidence.append(make_evidence(c,doc,item))
        review={"document_id":doc["id"],"application_id":doc["application_id"],"publication_number":doc["publication_id"],
                "document_type":doc["document_type"],"source_text_hash":doc["text_hash"],"decision":"reject",
                "reason_code":p["reason_code"],"reason":p["reason"],"reviewer":p["reviewer"],"evidence":evidence}
        rid="document-review-"+digest(review)[:24]
        previous=c.execute("SELECT data FROM document_reviews WHERE id=?",(rid,)).fetchone()
        if previous:
            results.append({"review_id":rid,"document_id":doc["id"],"cached":True});continue
        review.update(id=rid,reviewed_at=now())
        c.execute("INSERT INTO document_reviews VALUES(?,?,?,?)",(rid,doc["id"],doc["application_id"],dump(sanitized(review))))
        invalidated=[]
        for row in c.execute("SELECT * FROM analyses WHERE application_id=?",(doc["application_id"],)).fetchall():
            old=json.loads(row["data"])
            source_ids=[row["document_id"]]+[s.get("document_id") for s in old.get("support_documents",[]) if isinstance(s,dict)]
            source_docs=[c.execute("SELECT * FROM documents WHERE id=?",(sid,)).fetchone() for sid in source_ids]
            if not any(d and document_rejection_key(d)==document_rejection_key(doc) for d in source_docs):continue
            audit={"application_id":row["application_id"],"document_id":row["document_id"],"review_id":rid,
                   "previous_analysis":old,"invalidated_at":now()}
            audit["id"]="analysis-invalidation-"+digest([rid,row["application_id"],row["document_id"],old])[:24]
            c.execute("INSERT INTO analysis_invalidations VALUES(?,?,?,?)",(audit["id"],row["application_id"],row["document_id"],dump(audit)))
            old.update(analysis_status="invalidated_source_review",invalidated_at=audit["invalidated_at"],
                       invalidated_by_document_reviews=sorted(set(old.get("invalidated_by_document_reviews",[])+[rid])))
            c.execute("UPDATE analyses SET data=? WHERE application_id=?",(dump(old),row["application_id"]))
            invalidated.append(row["application_id"])
        event(c,"document-review-import",{"review_id":rid,"document_id":doc["id"],"invalidated_analyses":invalidated})
        results.append({"review_id":rid,"document_id":doc["id"],"decision":"reject","invalidated_analyses":invalidated})
    return {"document_reviews":results}

def make_evidence(c,doc,p):
    require(p.get("id") and p.get("quote") and p.get("locator"),"Evidence id, quote and locator required")
    if "document_id" in p:require(p["document_id"]==doc["id"],"Evidence document_id must match its actual source; source attribution cannot be rewritten")
    if "application_id" in p:require(p["application_id"]==doc["application_id"],"Evidence application_id differs from actual source")
    if "publication_number" in p:require(number(p["publication_number"])==doc["publication_id"],"Evidence publication differs from actual source")
    quote=p["quote"];text=doc["text"];source=json.loads(doc["data"])
    start=p.get("start"); end=p.get("end")
    if start is None:
        occurrences=[m.start() for m in re.finditer(re.escape(quote),text)]
        require(len(occurrences)==1,"Evidence quote missing or repeated; provide exact start/end")
        start=occurrences[0];end=start+len(quote)
    require(isinstance(start,int) and isinstance(end,int) and start>=0 and end>start and text[start:end]==quote,"Evidence span does not exactly match source")
    if doc["document_type"]=="claims":
        locator=p["locator"]
        no=locator.get("claim_number") if isinstance(locator,dict) else None
        if no is None and isinstance(locator,str):
            m=re.search(r"(?:权利要求|[Cc]laim)\s*(\d+)",locator)
            if m: no=int(m.group(1))
        require(isinstance(no,int),"Claims evidence needs locator.claim_number or 权利要求N")
        block=next((x for x in source["claims"] if x["number"]==no),None)
        require(block and block["start"]<=start<end<=block["end"] and quote in block["text"],"Evidence span does not belong to specified claim")
    ev={"id":str(p["id"]),"application_id":doc["application_id"],"document_id":doc["id"],
        "publication_number":doc["publication_id"],"source_type":doc["document_type"],
        "quote":quote,"text":quote,"start":start,"end":end,"locator":p["locator"],
        "url":source["source_url"],"version":source["version"],"language":source["language"],
        "source_provider":source["source_provider"],"acquired_at":source["acquired_at"]}
    old=c.execute("SELECT data FROM evidence WHERE id=?",(ev["id"],)).fetchone()
    require(not old or old[0]==dump(ev),"Evidence ID collision with different source/content")
    return ev
def validate_finding(value,allowed,label):
    if value in (None,[],{}): return
    for finding in as_list(value):
        require(isinstance(finding,dict) and isinstance(finding.get("text"),str),"Finding must have text and evidence_ids: "+label)
        refs=finding.get("evidence_ids",[])
        require(refs and set(refs)<=allowed,"Missing/invalid evidence in "+label)
        require(finding.get("kind","disclosed") in ("disclosed","inference"),"Finding kind must be disclosed/inference")
def import_analysis(c,p):
    p=dict(p)
    appid=p.get("application_id");docid=p.get("document_id")
    require(appid and docid,"Analysis application_id/document_id required")
    require(application_population_status(c,appid)=="included","Candidate application must be included by the population review before technical analysis")
    require(not any(m["member_application_id"]==appid for m in registration_module().records(c)),"National registration members do not add an independent technical-analysis task; cite canonical evidence under its own identity")
    doc=c.execute("SELECT * FROM documents WHERE id=?",(docid,)).fetchone()
    require(doc and doc["application_id"]==appid,"Analysis source is a different application")
    source=json.loads(doc["data"]); require(document_is_eligible(c,doc),"Unqualified or rejected source cannot complete analysis")
    app=json.loads(c.execute("SELECT data FROM applications WHERE id=?",(appid,)).fetchone()[0])
    require(app["patent_type"] in ("invention","utility_model"),"Technical analysis is only for invention/utility_model")
    expected={x[0] for x in c.execute("SELECT id FROM chunks WHERE document_id=?",(docid,))}
    strict=whole_review_required(c)
    whole=p.get("whole_document_review")
    if strict or whole is not None:
        require(whole is not None,"Whole-patent analysis requires whole_document_review; legacy records remain stored but need an explicit current review")
        reviewer=whole_review_module()
        p["whole_document_review"]=reviewer.validate_whole_document_review(whole,doc,require)
        p["tail_check"]=reviewer.validate_tail_check(p.get("tail_check"),doc,require,description_intervals)
        require(isinstance(p.get("analysis_author"),str) and p["analysis_author"].strip(),"Whole-patent analysis requires its actual analysis_author")
        if "completed_chunk_ids" not in p:p["completed_chunk_ids"]=sorted(expected)
    supplied=p.get("completed_chunk_ids",[])
    require(isinstance(supplied,list) and len(supplied)==len(set(supplied)) and set(supplied)==expected and expected,
            "Every source chunk must be processed exactly once")
    supports,sources=validate_support_documents(c,doc,p.get("support_documents",[]))
    support_by_id={s["document_id"]:s for s in supports}
    evidence=[]
    for selected in p.get("evidence",[]):
        require(isinstance(selected,dict),"Analysis evidence must be an object")
        sid=selected.get("document_id",docid)
        require(sid in sources,"Evidence document_id is not the primary or a declared supporting source")
        ev=make_evidence(c,sources[sid],selected)
        if sid!=docid:
            require(evidence_in_read_regions(ev,support_by_id[sid]),"Supporting evidence lies outside actually reviewed regions")
            validate_support_evidence_locator(sources[sid],ev)
        evidence.append(ev)
    require(evidence,"Analysis requires original-source evidence")
    require(any(ev["document_id"]==docid for ev in evidence),"Analysis must cite its fully read primary source")
    ids={e["id"] for e in evidence}
    require(len(ids)==len(evidence),"Duplicate evidence ids in analysis")
    require(isinstance(p.get("primary_module"),str) and p["primary_module"].strip(),"Primary module required")
    require(isinstance(p.get("tags",[]),list),"Tags must be array")
    validate_finding(p.get("summary"),ids,"summary")
    require(p.get("summary"),"Evidence-backed summary required")
    fields=p.get("fields",{});require(isinstance(fields,dict),"fields must be object")
    if strict or whole is not None:
        require(set(fields)==set(FIELDS) and all(isinstance(v,list) for v in fields.values()),"All eight technical fields must be arrays; undisclosed fields stay empty with limitations")
        require(isinstance(p.get("limitations"),list) and all(isinstance(x,str) and x.strip() for x in p["limitations"]),"Limitations must be an array of explicit statements")
        require(all(fields.values()) or p["limitations"],"Explain fields without disclosed findings in limitations")
        for finding in [p["summary"]]+[item for values in fields.values() for item in values]:
            require(isinstance(finding,dict) and isinstance(finding.get("text"),str) and finding["text"].strip(),"A finding needs a nonempty explanation")
            if finding.get("kind")=="inference":
                cond=finding.get("conditions")
                require(isinstance(finding.get("basis"),str) and finding["basis"].strip() and ((isinstance(cond,str) and cond.strip()) or (isinstance(cond,list) and cond and all(isinstance(x,str) and x.strip() for x in cond))),"An inference needs explicit basis and conditions")
    for k,v in fields.items():
        require(k in FIELDS,"Unknown technical field: "+k); validate_finding(v,ids,k)
    # Claimed effects are disclosures, never measured commercial performance.
    analysis=dict(p);analysis.update({"text_basis":doc["document_type"],"source_text_hash":doc["text_hash"],
        "analysis_status":"complete","completed_at":now(),"rules_version":SCHEMA_VERSION,
        "evidence_ids":sorted(ids),"evidence":evidence})
    if supports:analysis["support_documents"]=supports
    for ev in evidence: c.execute("INSERT OR REPLACE INTO evidence VALUES(?,?,?,?)",(ev["id"],appid,ev["document_id"],dump(ev)))
    c.execute("INSERT OR REPLACE INTO analyses VALUES(?,?,?)",(appid,docid,dump(sanitized(analysis))))
    event(c,"analysis-import",{"application_id":appid,"document_id":docid,"evidence_count":len(evidence)})
    return {"application_id":appid,"analysis_status":"complete","text_basis":doc["document_type"]}
def check_refs(c,refs):
    require(isinstance(refs,list) and refs,"Evidence references required")
    out=[]
    for eid in refs:
        row=c.execute("SELECT * FROM evidence WHERE id=?",(eid,)).fetchone()
        require(row,"Unknown evidence: "+str(eid))
        doc=c.execute("SELECT * FROM documents WHERE id=?",(row["document_id"],)).fetchone()
        require(document_is_eligible(c,doc),"Evidence comes from an unqualified or rejected source: "+str(eid));out.append(row)
    return out
def population_hash(c):
    apps=[json.loads(r[0]) for r in c.execute("SELECT data FROM applications ORDER BY id")]
    pubs=[r[0] for r in c.execute("SELECT id FROM publications ORDER BY id")]
    analyses=[]
    for r in c.execute("SELECT application_id,document_id,data FROM analyses ORDER BY application_id"):
        a=json.loads(r["data"]);a.pop("completed_at",None)
        analyses.append([r["application_id"],r["document_id"],a])
    run=run_info(c)
    reviews=rows_data(c,"population_reviews")
    for review in reviews:review.pop("reviewed_at",None)
    registration_records=registration_module().records(c)
    return digest({"applications":apps,"publications":pubs,"analyses":analyses,"cutoff":run["as_of_date"],"entity_hash":run.get("entity_snapshot_hash"),"population_review_required":population_review_required(c),"population_reviews":sorted(reviews,key=lambda r:r["application_id"]),"query_plan_contract":get_meta(c,"query_plan_contract"),"query_sets":sorted(rows_data(c,"query_sets"),key=lambda s:s["id"]),"bibliography_conflicts":sorted(bibliography_conflicts(c),key=dump),"document_review_ids":sorted(r["id"] for r in optional_rows_data(c,"document_reviews")),"auxiliary_source_ids":sorted(r["id"] for r in auxiliary_module().records(c)),**({"registration_members":registration_records} if registration_records else {}),**({"analysis_scope":{k:run["scope"][k] for k in ("analysis_window","selection") if k in run["scope"]}} if any(k in run["scope"] for k in ("analysis_window","selection")) else {})})
def research_module():
    spec=importlib.util.spec_from_file_location("pp_research_workflow",Path(__file__).with_name("research_workflow.py"))
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module
def research_context():
    return argparse.Namespace(**globals())
def active_relations(c):
    retired=set(get_meta(c,"research_retired",{}).get("relation_ids",[]))
    return [r for r in rows_data(c,"relations") if r["id"] not in retired]
def active_insights(c):
    retired=set(get_meta(c,"research_retired",{}).get("insight_ids",[]))
    values=[i for i in rows_data(c,"insights") if i["id"] not in retired]
    if run_info(c)["scope"].get("selection") is None:return values
    current=population_hash(c)
    scope=insight_selection_scope(c)
    return [i for i in values if i.get("population_hash")==current and i.get("selection_scope")==scope]
def insight_selection_scope(c):
    selection=run_info(c)["scope"].get("selection")
    return {k:selection[k] for k in ("kind","manifest_id","manifest_sha256","count","date_field","date_order","tie_break")} if selection else None
def import_insights(c,payload):
    for p in as_list(payload):
        require(p.get("id") and p.get("role") in ROLES and p.get("title") and p.get("body"),"Insight id/role/title/body required")
        require(p.get("scope") and isinstance(p.get("limitations",[]),list),"Insight scope and limitations required")
        selection_scope=insight_selection_scope(c)
        if selection_scope is not None:require(p.get("selection_scope")==selection_scope,"New role insights must explicitly bind the current latest-selection scope; do not relabel a parent-scope conclusion")
        require(p.get("kind") in ("observation","hypothesis","research_action"),"Unsupported insight kind")
        refs=check_refs(c,p.get("evidence_ids"))
        apps=set(p.get("patent_ids",[]))
        require(apps and {r["application_id"] for r in refs}<=apps,"Insight patent_ids must contain source applications")
        require(apps<={a["id"] for a in included_applications(c)},"Role insight cannot cite an excluded or pending candidate")
        for app in apps: require(c.execute("SELECT 1 FROM applications WHERE id=?",(app,)).fetchone(),"Unknown insight application")
        for metric in p.get("metrics",[]):
            require(metric.get("metric")=="application_count","Unsupported metric; compute it in engine")
            ids=set(metric.get("application_ids",[]))
            require(ids<=apps and metric.get("value")==len(ids),"Role metric conflicts with canonical application count")
        item=dict(p);item["population_hash"]=population_hash(c)
        c.execute("INSERT OR REPLACE INTO insights VALUES(?,?)",(p["id"],dump(sanitized(item))))
    event(c,"insights-import",{"count":len(as_list(payload))});return {"insights_imported":len(as_list(payload))}
def import_relations(c,payload):
    for p in as_list(payload):
        require(p.get("id") and p.get("source") and p.get("target") and p.get("type"),"Relation id/source/target/type required")
        require(p.get("kind") in ("fact","inference"),"Relation kind required")
        if p["kind"]=="inference":
            check_refs(c,p.get("evidence_ids"));require(p.get("basis"),"Inferred relation needs explicit basis")
        else:
            if p.get("evidence_ids"): check_refs(c,p["evidence_ids"])
            else:
                require(p.get("source_url") and p.get("source_locator"),"Factual relation needs source URL/locator")
                safe_url(p["source_url"])
        c.execute("INSERT OR REPLACE INTO relations VALUES(?,?)",(p["id"],dump(sanitized(p))))
    event(c,"relations-import",{"count":len(as_list(payload))});return {"relations_imported":len(as_list(payload))}
def export_work(c,output,max_primary_characters=None):
    require(max_primary_characters is None or max_primary_characters>0,"Whole-document capacity limit must be positive")
    path=Path(output);path.parent.mkdir(parents=True,exist_ok=True);count=0
    deferred_path=path.with_suffix(path.suffix+".deferred.json")
    for target in (path,deferred_path):
        for database in c.execute("PRAGMA database_list"):
            if not database[2]:continue
            for protected in (Path(database[2]),Path(database[2]+"-wal"),Path(database[2]+"-shm"),Path(database[2]+"-journal")):
                same=target.resolve()==protected.resolve() or (target.exists() and protected.exists() and target.samefile(protected))
                require(not same,"Work export cannot overwrite its database or transaction files")
    deferred=[]
    included={a["id"] for a in included_applications(c)}
    rejections=document_rejection_index(c)
    with path.open("w",encoding="utf-8") as f:
        for app in c.execute("SELECT * FROM applications ORDER BY id"):
            if app["id"] not in included:continue
            meta=json.loads(app["data"])
            if meta["patent_type"] not in ("invention","utility_model"): continue
            existing=c.execute("SELECT * FROM analyses WHERE application_id=?",(app["id"],)).fetchone()
            if existing and analysis_is_current(c,existing,rejections):
                existing_data=json.loads(existing["data"])
                if not whole_review_required(c) or existing_data.get("whole_document_review"):continue
            candidates=list(c.execute("SELECT * FROM documents WHERE application_id=? ORDER BY CASE document_type WHEN 'claims' THEN 0 ELSE 1 END,id",(app["id"],)))
            qualified=[d for d in candidates if document_is_eligible(c,d,rejections)]
            if not qualified: continue
            doc=qualified[0];source=json.loads(doc["data"])
            support_candidates=[{"document_id":d["id"],"publication_number":d["publication_id"],"source":json.loads(d["data"]),
                 "reading_scope":"available_for_targeted_reading_only"} for d in qualified if doc["document_type"]=="claims" and d["document_type"]=="description"
                 and d["publication_id"]==doc["publication_id"] and source_language(json.loads(d["data"])["language"])==source_language(source["language"])]
            if max_primary_characters is not None and len(doc["text"])>max_primary_characters:
                deferred.append({"application_id":app["id"],"document_id":doc["id"],"character_count":len(doc["text"]),"reason":"whole_document_exceeds_requested_character_limit","next_action":"Use a suitable context or the same-reader continuous whole-document review; never truncate or split into independent analyses."})
                continue
            legacy_ids=[r[0] for r in c.execute("SELECT id FROM chunks WHERE document_id=? ORDER BY ordinal",(doc["id"],))]
            # Keep anchors but include the source text only once in the packet.
            packet_source=dict(source)
            packet_source["claims"]=[{k:v for k,v in item.items() if k!="text"} for item in source.get("claims",[])]
            f.write(dump({"application_id":app["id"],"patent":meta,"document_id":doc["id"],
                "source":packet_source,"reading_unit":"whole_patent","primary_document":{"document_id":doc["id"],"text":doc["text"],"source_text_hash":doc["text_hash"],"character_count":len(doc["text"]),"claim_index":packet_source["claims"]},
                "material_availability":{"primary_document":"included_in_full","description":"included_as_primary" if doc["document_type"]=="description" else ("available_in_run_not_embedded" if support_candidates else "not_acquired"),"figures":"not_embedded_check_original_publication_and_run_materials"},
                "coverage":{"legacy_chunk_ids":legacy_ids},"support_document_candidates":support_candidates,
                "instructions":"One patent is one coherent analysis task owned by one reader. Read the full selected primary document and actual tail; use a clean context with necessary product background. Assess capacity including figures, reasoning and output; character count is not a model token guarantee. If too long, preserve the same task and record continuous reading coverage and cross-section dependencies, never silently truncate or distribute independent fragments. Default complete claims first; for mechanism questions read relevant same-publication description and figures and record actual support_documents/read_regions. Claims-only is not full-description or image review. Save whole_document_review, tail_check, analysis_author, all eight fields with evidence, and unresolved questions. Independent semantic review and planned cross-patent research are separate completion gates."})+"\n")
            count+=1
    deferred_path.write_text(json.dumps(deferred,ensure_ascii=False,indent=2),encoding="utf-8")
    return {"work_items":count,"output":str(path),"deferred_items":len(deferred),"deferred_output":str(deferred_path),"reading_unit":"whole_patent"}

def coverage(c):
    run=run_info(c);raw_apps=included_source_records(c);registration=registration_state(c,raw_apps)
    memberids={m["member_application_id"] for m in registration["active"]};apps=[a for a in raw_apps if a["id"] not in memberids]
    appids={a["id"] for a in apps};raw_appids={a["id"] for a in raw_apps};docs=list(c.execute("SELECT * FROM documents"))
    states=population_state(c);population_counts=collections.Counter(states.values())
    rejections=document_rejection_index(c)
    analysis_rows=[r for r in c.execute("SELECT * FROM analyses") if r["application_id"] in appids]
    analyses={r["application_id"]:json.loads(r["data"]) for r in analysis_rows if analysis_is_current(c,r,rejections)}
    tech=[a for a in apps if a["patent_type"] in ("invention","utility_model")]
    design=[a for a in apps if a["patent_type"]=="design"]
    gooddocs={d["application_id"] for d in docs if document_is_eligible(c,d,rejections)}
    basis=collections.Counter(a["text_basis"] for a in analyses.values())
    queries=list(c.execute("SELECT * FROM queries"))
    ordinary={q["id"] for q in queries if not json.loads(q["request"]).get("verification_only",False)}
    candidate_pubs={r["publication_id"] for r in c.execute("SELECT query_id,publication_id FROM query_results") if r["query_id"] in ordinary}
    contract=get_meta(c,"query_plan_contract",{})
    auxiliary=auxiliary_module().records(c);observed,legal=legal_status_snapshot(c,auxiliary)
    selected_aux=[item for item in auxiliary if item["application_id"] in appids]
    window_summary=temporal_scope_module().cohort_summary(c,states)
    selection=run["scope"].get("selection")
    window_records=unselected_source_records(c) if selection and window_summary else raw_apps
    window_registration=registration_state(c,window_records) if selection and window_summary else registration
    window_members={m["member_application_id"] for m in window_registration["active"]}
    window_apps=[a for a in window_records if a["id"] not in window_members]
    if window_summary and (window_registration["active"] or selection):
        window_summary.update({"selected_source_application_records":window_summary["selected_applications"],
          "selected_source_record_by_type":window_summary["selected_by_type"],"selected_applications":len(window_apps),
          "selected_by_type":dict(sorted(collections.Counter(a["patent_type"] for a in window_apps).items())),
          "selected_unknown_date_statistics":sum(not a.get("filing_date") for a in window_apps),
          "selected_count_unit":"independent_filing_application","identity_temporal_cross_count_unit":"source_application_records"})
    if selection and window_summary:window_summary["before_latest_selection"]=True
    return {"applications":len(apps),"publications":sum(r[0] in appids for r in c.execute("SELECT application_id FROM publications")),
      "analysis_window":window_summary,
      **({"selection":{**selection,"validation":"complete_candidate_ranking_verified","selected_source_application_records":len(raw_apps),"selected_independent_technical_applications":len(tech)}} if selection else {}),
      "registration_count_bridge":registration_count_bridge(c,raw_apps,apps,registration),
      "raw_included_application_records":len(raw_apps),"raw_technical_application_records":sum(a["patent_type"] in ("invention","utility_model") for a in raw_apps),
      "registration_member_records":len(memberids),"registration_mapping_errors":len(registration["errors"]),
      "registration_member_qualified_own_texts":len(memberids&gooddocs),
      "registration_member_legal_status_known":sum(legal.get(k,{}).get("status","unknown") not in (None,"","unknown") for k in memberids),
      "registration_member_auxiliary_observations":sum(i["application_id"] in memberids for i in auxiliary),
      "raw_included_source_publications":sum(r[0] in raw_appids for r in c.execute("SELECT application_id FROM publications")),
      "candidate_applications":len(states),"included_applications":population_counts["included"],"excluded_applications":population_counts["excluded"],"pending_applications":population_counts["pending"],
      "candidate_publications":len(candidate_pubs),"stored_source_publications":c.execute("SELECT count(*) FROM publications").fetchone()[0],"verification_queries":len(queries)-len(ordinary),"control_only_stored_applications":c.execute("SELECT count(*) FROM applications").fetchone()[0]-len(states),"population_review_required":population_review_required(c),
      "logical_query_sets":c.execute("SELECT count(*) FROM query_sets").fetchone()[0],"required_query_sets":len(contract.get("required_query_set_ids",[])),
      "bibliography_publications":c.execute("SELECT count(DISTINCT publication_id) FROM bibliographies").fetchone()[0],"bibliography_applications":c.execute("SELECT count(DISTINCT application_id) FROM bibliographies").fetchone()[0],
      "technical_applications":len(tech),"design_applications":len(design),
      "unknown_type_applications":sum(a["patent_type"]=="unknown" for a in apps),
      "technical_fulltext":sum(a["id"] in gooddocs for a in tech),
      "technical_analyzed":sum(a["id"] in analyses for a in tech),
      "rejected_documents":sum(d["application_id"] in appids and bool(rejections.get(document_rejection_key(d))) for d in docs),
      "document_rejection_reviews":len(optional_rows_data(c,"document_reviews")),
      "invalidated_analyses":len(analysis_rows)-len(analyses),
      "description_based":basis["description"],"claims_based":basis["claims"],
      "technical_completion":round(100*sum(a["id"] in analyses for a in tech)/len(tech),3) if tech else None,
      "queries":len(queries),"completed_queries":sum(q["complete"] for q in queries),
      "legal_status_known":sum(legal.get(a["id"],{}).get("status","unknown") not in (None,"","unknown") for a in apps),
      "legal_status_observed_publications":len({i["publication_number"] for i in selected_aux if i["kind"]=="legal_status"}),
      "legal_status_conflict_applications":sum(legal.get(a["id"],{}).get("conflict",False) for a in apps),
      "family_observed_publications":len({i["publication_number"] for i in selected_aux if i["kind"]=="family"}),
      "abstract_image_observed_publications":len({i["publication_number"] for i in selected_aux if i["kind"]=="abstract_image"}),
      "abstract_image_local_publications":len({i["publication_number"] for i in selected_aux if i["kind"]=="abstract_image" and i["normalized"].get("availability")=="local"}),
      "evidence":sum(r["application_id"] in appids and document_is_eligible(c,c.execute("SELECT * FROM documents WHERE id=?",(r["document_id"],)).fetchone(),rejections) for r in c.execute("SELECT application_id,document_id FROM evidence")),
      "retained_evidence":sum(r[0] in appids for r in c.execute("SELECT application_id FROM evidence")),
      "scope_confirmed":run.get("scope_confirmed",False)}
def validate_run(c):
    run=run_info(c);cov=coverage(c);errors=[];warnings=[]
    def check(ok,code,detail):
        if not ok: errors.append({"code":code,"detail":detail})
    registration=registration_state(c)
    errors.extend(registration["errors"])
    if registration["active"]:warnings.append({"code":"national_registration_count_unit","detail":"Independent filing units exclude only official evidence-bound national register members. Original member rows, query totals, jurisdiction, owner, legal status and text gaps remain separate. Canonical EP evidence is not a national-member text or legal-state substitute."})
    included=[e for e in rows_data(c,"entities") if e.get("confirmed") and e.get("relation") in ("root","subsidiary","historical")]
    check(run.get("scope_confirmed"),"scope_unconfirmed","Group/historical scope not reviewed through cutoff")
    check(bool(included),"no_entities","No confirmed included entities")
    if run.get("scope_confirmed"):
        check(run.get("entity_snapshot_hash")==digest(sorted(included,key=lambda x:x["id"])),"scope_changed","Entity snapshot changed")
    material_mode=run["scope"].get("acquisition_mode")=="materials"
    if material_mode:
        try:materials_module().validate_manifest(c,material_engine())
        except (ValidationError,OSError,KeyError,TypeError) as exc:check(False,"material_scope_invalid",str(exc))
        warnings.append({"code":"material_scope_only","detail":"Completion covers the frozen supplied material catalogue, not company-wide patent coverage."})
    else:
        queries=list(c.execute("SELECT * FROM queries"))
        query_sets={s["id"]:s for s in rows_data(c,"query_sets")};contract=get_meta(c,"query_plan_contract")
        query_sets_required=run["scope"].get("require_query_sets",not run["scope"].get("synthetic",False))
        valid_sets={};cache={}
        if query_sets_required:check(bool(contract),"query_plan_unconfirmed","Real full-population run needs a frozen logical query plan")
        for sid,spec in query_sets.items():
            try:valid_sets[sid]=query_set_evaluate(c,spec,cache=cache)
            except (ValidationError,TypeError,KeyError,ValueError) as exc:check(False,"query_set_invalid",sid+": "+str(exc))
        required_specs=contract.get("required_query_sets",[]) if contract else []
        for spec in required_specs:
            actual=query_sets.get(spec["id"])
            check(actual is not None,"required_query_set_missing",spec["id"])
            if actual:check(all(actual.get(k)==spec.get(k) for k in ("id","entity_id","kind","query_text")),"query_set_contract_changed",spec["id"])
            check(spec["id"] in valid_sets,"required_query_set_incomplete",spec["id"])
        for e in included:
            for kind in ("original","current"):
                if query_sets_required:
                    qs=[s for s in required_specs if s["entity_id"]==e["id"] and s["kind"]==kind]
                    check(bool(qs),"missing_query_set",e["id"]+":"+kind)
                    check(bool(qs) and all(s["id"] in valid_sets for s in qs),"query_set_incomplete",e["id"]+":"+kind)
                    continue
                qs=[q for q in queries if q["entity_id"]==e["id"] and q["kind"]==kind and not json.loads(q["request"]).get("verification_only",False)]
                check(bool(qs),"missing_query",e["id"]+":"+kind)
                check(bool(qs) and all(q["complete"] for q in qs),"query_incomplete",e["id"]+":"+kind)
        check(bool(queries),"no_queries","No query evidence")
        for q in queries:
            n=c.execute("SELECT count(*) FROM query_results WHERE query_id=?",(q["id"],)).fetchone()[0]
            check(bool(q["complete"]) and n==q["expected_count"]==q["observed_count"],"query_count_mismatch",q["id"])
    if get_meta(c,"material_manifest") and not material_mode:
        try:materials_module().validate_manifest(c,material_engine())
        except (ValidationError,OSError,KeyError,TypeError) as exc:check(False,"material_source_invalid",str(exc))
    states=population_state(c)
    temporal=temporal_scope_module().window_states(c,states)
    selection=run["scope"].get("selection")
    selected_sources={a["id"] for a in included_source_records(c)} if selection else None
    for appid,state in states.items():
        if selected_sources is not None and appid not in selected_sources:continue
        if not temporal or temporal[appid]["status"]!="outside":check(state!="pending","population_review_pending",appid)
        if temporal and state!="excluded":check(temporal[appid]["status"]!="pending","analysis_window_pending",appid+":"+temporal[appid]["reason"])
    if temporal:warnings.append({"code":"analysis_window_boundary","detail":"Technical completion covers only the inclusive filing-date analysis window. All parent search records and identity decisions are retained; date conflicts crossing the window remain pending. Parent identity totals and the selected analysis cohort are separate counts."})
    if selection:
        check(cov["technical_applications"]==selection["count"] and cov["applications"]==selection["count"],"latest_selection_count_mismatch","Completion denominator must equal every selected independent technical application")
        warnings.append({"code":"latest_technical_selection_boundary","detail":"Completion covers only the immutable latest-N independent technical selection, ranked by filing date descending and application ID ascending within the retained identity/window scope. All parent rows and national registration members remain retained; designs do not consume N."})
    apps=included_applications(c); appids={a["id"] for a in apps}
    pubs={r["id"] for r in c.execute("SELECT id,application_id FROM publications") if r["application_id"] in appids}
    rejections=document_rejection_index(c)
    evidence={r["id"]:r for r in c.execute("SELECT * FROM evidence") if r["application_id"] in appids
              and document_is_eligible(c,c.execute("SELECT * FROM documents WHERE id=?",(r["document_id"],)).fetchone(),rejections)}
    analyses={r["application_id"]:r for r in c.execute("SELECT * FROM analyses") if r["application_id"] in appids}
    biblio_conflicts=bibliography_conflicts(c)
    for conflict in biblio_conflicts:
        if conflict["application_id"] in appids and conflict["field"]=="patent_type":check(False,"bibliography_type_conflict",conflict["application_id"]+":"+conflict["source_id"])
    date_conflicts=application_date_conflicts(c)
    if date_conflicts:warnings.append({"code":"bibliography_date_conflicts","detail":"Conflicting source dates are retained; affected canonical page dates and date statistics are unknown. Full technical text completion is independent of this auxiliary-field conflict."})
    for a in apps:
        check(a["patent_type"]!="unknown","unknown_patent_type",a["id"])
        check(not any(x.get("field") not in ("filing_date","publication_date") for x in a.get("metadata_conflicts",[])),"metadata_conflict",a["id"])
        if a["patent_type"] not in ("invention","utility_model"): continue
        ana=analyses.get(a["id"])
        if not ana:
            errors.append({"code":"technical_analysis_missing","detail":a["id"]});continue
        p=json.loads(ana["data"]);d=c.execute("SELECT * FROM documents WHERE id=?",(ana["document_id"],)).fetchone()
        check(d and d["application_id"]==a["id"],"wrong_document_application",a["id"])
        if not d: continue
        sd=json.loads(d["data"])
        check(sd.get("qualified") and sd.get("complete") is True and sd.get("truncated") is False,"source_not_complete",a["id"])
        check(not rejections.get(document_rejection_key(d)),"source_rejected",a["id"]+":"+d["id"])
        check(p.get("analysis_status")=="complete","analysis_invalidated",a["id"])
        check(p.get("source_text_hash")==d["text_hash"] and digest(d["text"])==d["text_hash"],"stale_analysis",a["id"])
        expected={x[0] for x in c.execute("SELECT id FROM chunks WHERE document_id=?",(d["id"],))}
        check(expected==set(p.get("completed_chunk_ids",[])),"unprocessed_chunks",a["id"])
        try:
            supports,source_docs=validate_support_documents(c,d,p.get("support_documents",[]),rejections)
        except (ValidationError,KeyError,TypeError) as error:
            check(False,"supporting_source_invalid",a["id"]+":"+str(error));supports=[];source_docs={d["id"]:d}
        support_by_id={s["document_id"]:s for s in supports}
        for eid in p.get("evidence_ids",[]):
            ev=evidence.get(eid);check(ev and ev["application_id"]==a["id"] and ev["document_id"] in source_docs,"wrong_evidence_application",str(eid))
            if ev:
                x=json.loads(ev["data"])
                actual=source_docs.get(ev["document_id"])
                check(actual and x.get("document_id")==actual["id"] and actual["text"][x["start"]:x["end"]]==x["quote"],"quote_mismatch",eid)
                if ev["document_id"] in support_by_id:
                    check(evidence_in_read_regions(x,support_by_id[ev["document_id"]]),"supporting_evidence_unread",eid)
                    try:validate_support_evidence_locator(actual,x)
                    except (ValidationError,KeyError,TypeError) as error:check(False,"supporting_evidence_locator",eid+":"+str(error))
    insights=active_insights(c)
    historical_insights=len(rows_data(c,"insights"))-len(insights)
    if historical_insights:warnings.append({"code":"historical_role_insights_retained","detail":str(historical_insights)+" previous role insights remain stored but are inactive for the current research questions or frozen selection. Current evidence-backed insights are required for all three roles."})
    if cov["technical_applications"]:
        for role in ROLES: check(any(i["role"]==role for i in insights),"missing_role_insights",role)
    current_population=population_hash(c)
    for insight in insights:
        check(insight.get("population_hash")==current_population,"stale_role_insight",insight["id"])
        check(bool(insight.get("evidence_ids")),"insight_without_evidence",insight["id"])
        check(set(insight.get("patent_ids",[]))<=appids,"insight_unknown_application",insight["id"])
        for eid in insight.get("evidence_ids",[]):
            ev=evidence.get(eid)
            check(ev and ev["application_id"] in insight.get("patent_ids",[]),"insight_evidence_mismatch",insight["id"]+":"+eid)
    moduleids={"module:"+digest(json.loads(r["data"])["primary_module"])[:12] for r in analyses.values()}
    endpoints=appids|pubs|set(evidence)|moduleids|{e["id"] for e in rows_data(c,"entities")}|{i["id"] for i in insights}
    hidden=(set(states)-appids)|{r["id"] for r in c.execute("SELECT id,application_id FROM publications") if r["application_id"] not in appids}|{r["id"] for r in c.execute("SELECT id,application_id FROM evidence") if r["application_id"] not in appids}
    for relation in active_relations(c):
        if relation["source"] in hidden or relation["target"] in hidden or set(relation.get("evidence_ids",[]))&hidden:continue
        check(relation["source"] in endpoints and relation["target"] in endpoints,"relation_endpoint_missing",relation["id"])
        for eid in relation.get("evidence_ids",[]): check(eid in evidence,"relation_evidence_missing",relation["id"])
    if auxiliary_module().records(c):warnings.append({"code":"auxiliary_observation_dates","detail":"Legal status and family data describe observations at each acquisition time, which may follow the frozen search cutoff; no historical legal state is reconstructed. Simple, INPADOC and PatSnap families remain distinct."})
    if cov["document_rejection_reviews"]:warnings.append({"code":"source_rejections_retained","detail":"Host-observed source defects are retained with exact source evidence; rejected text cannot support completion, including identical text under a new version label."})
    if cov["legal_status_known"]<cov["applications"]: warnings.append({"code":"legal_status_partial","detail":"Unknown status stays unknown; technical completeness is independent."})
    warnings.append({"code":"population_boundary","detail":"Completeness is bounded by frozen entities, queries, data sources and publication cutoff; unpublished applications are unobservable."})
    if research_quality_required(c):
        quality=research_quality_module().validate(c,research_quality_context())
        errors.extend(quality["errors"]);warnings.extend(quality["warnings"])
        cov["research_quality"]=quality["coverage"]
        for appid,ana in analyses.items():
            p=json.loads(ana["data"])
            check(bool(p.get("whole_document_review")) and bool(p.get("analysis_author")),"whole_document_review_missing",appid)
    errors.extend(research_module().check(c,research_context()))
    status="complete" if not errors else "incomplete"
    return {"schema_version":SCHEMA_VERSION,"run_id":run["run_id"],"status":status,"coverage":cov,"errors":errors,"warnings":warnings}
def status_run(c):
    report=validate_run(c);run=run_info(c)
    counts=collections.Counter(e["code"] for e in report["errors"])
    return {"run":run,"status":report["status"],"coverage":report["coverage"],
       "blocker_counts":dict(counts),"blockers":report["errors"][:30],
       "capabilities":rows_data(c,"capabilities"),"warnings":report["warnings"]}
def js_literal(value):
    # Data is generated code, never injected HTML. Escape JS/HTML boundary characters.
    return dump(value).replace("<","\\u003c").replace(">","\\u003e").replace("&","\\u0026").replace("\u2028","\\u2028").replace("\u2029","\\u2029")
def text_of(value):
    if value is None: return ""
    if isinstance(value,str): return value
    if isinstance(value,dict): return str(value.get("text",value.get("value","")))
    if isinstance(value,list): return "；".join(text_of(v) for v in value)
    return str(value)
def build_payload(c,report,local_image_paths=None,document_image_records=None,original_document_records=None):
    run=run_info(c);cov=report["coverage"];run=dict(run)
    run.update({"status":report["status"],"skill_release":SKILL_RELEASE,"coverage":cov,"completion":cov["technical_completion"],
      "limitations":run.get("limitations",[])+[w["detail"] for w in report["warnings"]]})
    entities=rows_data(c,"entities");raw_apps=included_source_records(c);registration=registration_state(c,raw_apps)
    memberids={m["member_application_id"] for m in registration["active"]};apps=[a for a in raw_apps if a["id"] not in memberids];appids={a["id"] for a in apps}
    auxiliary=auxiliary_module();aux_items=[i for i in auxiliary.records(c) if i["application_id"] in appids]
    _,legal=legal_status_snapshot(c,aux_items);local_image_paths=local_image_paths or {};document_image_records=document_image_records or {}
    aux_by_app=collections.defaultdict(list)
    for item in aux_items:aux_by_app[item["application_id"]].append(item)
    rejections=document_rejection_index(c)
    analyses={r["application_id"]:json.loads(r["data"]) for r in c.execute("SELECT * FROM analyses") if r["application_id"] in appids and analysis_is_current(c,r,rejections)}
    modules=collections.Counter(); patents=[]; details={}; relations=active_relations(c)
    date_conflicts=collections.defaultdict(list)
    for conflict in application_date_conflicts(c):
        date_conflicts[conflict["application_id"]].append(conflict)
    pub_to_app={r["id"]:r["application_id"] for r in c.execute("SELECT id,application_id FROM publications") if r["application_id"] in appids}
    relations+=auxiliary.family_relations(aux_items,pub_to_app)
    hidden={r["id"] for r in c.execute("SELECT id,application_id FROM publications") if r["application_id"] not in appids}|(set(population_state(c))-appids)
    hidden|={r["id"] for r in c.execute("SELECT id,application_id FROM evidence") if r["application_id"] not in appids}
    relations=[r for r in relations if r.get("source") not in hidden and r.get("target") not in hidden and not set(r.get("evidence_ids",[]))&hidden]
    for a in sorted(apps,key=lambda x:(x.get("filing_date") or "",x["id"]),reverse=True):
        ana=analyses.get(a["id"]);p=dict(a)
        p["legal_status_details"]=legal.get(a["id"],{"status":"unknown","publication_observations":[]})
        p["legal_status"]=p["legal_status_details"]["status"]
        if date_conflicts[a["id"]]:
            p["date_conflicts"]=date_conflicts[a["id"]];p["date_source_values"]={}
            for field in {x["field"] for x in date_conflicts[a["id"]]}:
                p["date_source_values"][field]=p.get(field);p[field]=None
        p["primary_module"]=ana["primary_module"] if ana else ("外观设计" if a["patent_type"]=="design" else "待分析")
        p["tags"]=ana.get("tags",[]) if ana else []
        p["analysis_status"]="complete" if ana else ("catalogue" if a["patent_type"]=="design" else "pending")
        p["text_basis"]=ana.get("text_basis","unknown") if ana else "unknown"
        p["summary"]=text_of(ana.get("summary")) if ana else ""
        p["module_id"]="module:"+digest(p["primary_module"])[:12]
        modules[p["primary_module"]]+=1
        public=[]
        for row in c.execute("SELECT data FROM publications WHERE application_id=? ORDER BY id",(a["id"],)):
            item=json.loads(row[0])
            # Preserve bibliographic source values, but never forward raw image
            # dictionaries or their temporary access URLs to the offline UI.
            item["metadata_original"]={key:value for key,value in item["metadata_original"].items() if key!="images"}
            public.append(item)
        documents=[];allclaims=[];images=[];embedded_images=[]
        for row in c.execute("SELECT * FROM documents WHERE application_id=? ORDER BY id",(a["id"],)):
            sd=json.loads(row["data"])
            documents.append({"id":row["id"],"publication_number":row["publication_id"],"document_type":row["document_type"],
              "language":sd["language"],"version":sd["version"],"source_url":sd["source_url"],
              "source_provider":sd["source_provider"],"complete":document_is_eligible(c,row,rejections),
              "structurally_qualified":sd["qualified"],"rejection_review_ids":rejections.get(document_rejection_key(row),[]),
              "text_format_note":sd.get("text_format_note"),"text":row["text"],
              **({"normalization_notice":sd["normalization_notice"]} if sd.get("normalization_notice") else {}),
              **({"original_document":(original_document_records or {}).get(row["id"],sd["verified_original_document"])} if sd.get("verified_original_document") else {})})
            embedded_images.extend(document_image_records.get(row["id"],[]))
            if row["document_type"]=="claims":
                allclaims.extend({**claim,"document_id":row["id"]} for claim in sd.get("claims",[]))
        ev=[json.loads(r["data"]) for r in c.execute("SELECT * FROM evidence WHERE application_id=?",(a["id"],)) if document_is_eligible(c,c.execute("SELECT * FROM documents WHERE id=?",(r["document_id"],)).fetchone(),rejections)]
        for item in aux_by_app[a["id"]]:
            if item["kind"]=="abstract_image" and item["id"] in local_image_paths:
                images.append({"path":local_image_paths[item["id"]],"source_id":item["id"],"publication_number":item["publication_number"],
                    "image_number":item["normalized"]["image_number"],"sha256":item["normalized"]["local_image"]["sha256"],"acquired_at":item["acquired_at"],
                    "caption":item["publication_number"]+" · 代表图／摘要图（非全部设计视图）","view_scope":"representative_only"})
        images.extend(embedded_images)
        p["images"]=images
        analysis={}
        if ana:
            analysis={"summary":ana["summary"],**ana.get("fields",{}),"limitations":ana.get("limitations",[]),"evidence_ids":ana["evidence_ids"],
                "document_id":ana["document_id"],"text_basis":ana["text_basis"],"support_documents":ana.get("support_documents",[])}
            relations.append({"id":"module-edge-"+digest(a["id"])[:16],"source":p["module_id"],"target":a["id"],
               "type":"classified_under","kind":"inference","label":"技术归类","evidence_ids":ana["evidence_ids"],"basis":"Evidence-backed primary module assigned during technical analysis."})
        details[a["id"]]={**p,"analysis":analysis,"evidence":ev,"documents":documents,
            "auxiliary_sources":[auxiliary.public_record(i) for i in aux_by_app[a["id"]]],
            "document_reviews":[r for r in optional_rows_data(c,"document_reviews") if r["application_id"]==a["id"]],
            "bibliographies":[json.loads(r[0]) for r in c.execute("SELECT data FROM bibliographies WHERE application_id=? ORDER BY id",(a["id"],))],
            "claims":allclaims,"images":images,"publications":public,
            "relations":[r for r in relations if r.get("source") in ([a["id"]]+a["publication_numbers"]) or r.get("target") in ([a["id"]]+a["publication_numbers"])]}
        patents.append(p)
    for rel in relations:
        rel["source"]=pub_to_app.get(rel["source"],rel["source"])
        rel["target"]=pub_to_app.get(rel["target"],rel["target"])
    member_payload=[];raw_by_id={a["id"]:a for a in raw_apps}
    all_aux=[i for i in auxiliary.records(c) if i["application_id"] in memberids]
    _,member_legal=legal_status_snapshot(c,all_aux)
    for mapping in registration["active"]:
        mid=mapping["member_application_id"];cid=mapping["canonical_filing_application_id"];source=dict(raw_by_id[mid])
        own_publications=[]
        for row in c.execute("SELECT data FROM publications WHERE application_id=? ORDER BY id",(mid,)):
            pub=json.loads(row[0]);pub["metadata_original"]={k:v for k,v in pub["metadata_original"].items() if k!="images"};own_publications.append(pub)
        own_documents=[]
        for row in c.execute("SELECT * FROM documents WHERE application_id=? ORDER BY id",(mid,)):
            sd=json.loads(row["data"])
            # Register members are auxiliary observations, not extra analysis
            # tasks. Their composed text must not bypass the image gate used
            # for canonical documents. Until original pixels are delivered for
            # that member, publish metadata and an explicit withholding notice.
            composed="embedded_image_review" in sd
            own_documents.append({"id":row["id"],"publication_number":row["publication_id"],"document_type":row["document_type"],
               "language":sd["language"],"version":sd["version"],"text":"" if composed else row["text"],
               "complete":not composed and document_is_eligible(c,row,rejections),
               "source_qualified":document_is_eligible(c,row,rejections),
               "source_url":sd["source_url"],"source_provider":sd["source_provider"],"source_identity":"member_own_document_only",
               **({"text_withheld":True,"required_embedded_images_delivered":False,
                   "display_notice":"本件正文含人工转写的原文嵌图；登记成员所需原图未随本页面交付，因此不展示该正文，也不将其计为可展示的完整文本。",
                   "normalization_notice":sd.get("normalization_notice")} if composed else {})})
        public_mapping=registration_module().public_record(mapping)
        source.update({"record_class":mapping["record_class"],"count_as_additional_independent_filing":False,
           "canonical_filing_application_id":cid,"identity_mapping":public_mapping,"publications":own_publications,"documents":own_documents,
           "own_fulltext_available":any(d["complete"] for d in own_documents),
           "technical_analysis_required_as_additional_unit":False,
           "canonical_evidence_link":{"application_id":cid,"publication_number":mapping["validated_proof"]["canonical_filing_evidence"]["publication_number"],
              "source_authority":"EP","notice":"EP source link only; no DE text or DE legal status is inferred."},
           "legal_status_details":member_legal.get(mid,{"status":"unknown","publication_observations":[]}),
           "auxiliary_sources":[auxiliary.public_record(i) for i in all_aux if i["application_id"]==mid],
           "bibliographies":[json.loads(r[0]) for r in c.execute("SELECT data FROM bibliographies WHERE application_id=? ORDER BY id",(mid,))]})
        source["legal_status"]=source["legal_status_details"]["status"];member_payload.append(source)
        details[cid].setdefault("registration_members",[]).append(source)
        for patent in patents:
            if patent["id"]==cid:
                patent.setdefault("registration_member_ids",[]).append(mid)
                patent["jurisdictions"]=sorted(set(patent.get("jurisdictions",[patent["authority"]]))|{source["authority"]})
                details[cid]["jurisdictions"]=patent["jurisdictions"]
    stats={"count_unit":"independent_filing_application" if registration["active"] else "application","application_count":len(apps),"publication_count":cov["publications"],
       "registration_count_bridge":cov["registration_count_bridge"],
       "jurisdiction_record_count":len(raw_apps),"by_jurisdiction_records":dict(collections.Counter(a["authority"] for a in raw_apps)),
       "by_type":dict(collections.Counter(a["patent_type"] for a in apps)),
       "by_authority":dict(collections.Counter(a["authority"] for a in apps)),
       "by_filing_year":dict(sorted(collections.Counter(a["filing_date"][:4] if a.get("filing_date") else "unknown" for a in patents).items())),
       "historical_original_query_ids":[r["id"] for r in c.execute("SELECT id,request FROM queries WHERE kind='original'") if not json.loads(r["request"]).get("verification_only",False)],
       "current_owner_query_ids":[r["id"] for r in c.execute("SELECT id,request FROM queries WHERE kind='current'") if not json.loads(r["request"]).get("verification_only",False)]}
    payload={"schema_version":SCHEMA_VERSION,"run":run,"stats":stats,"entities":entities,
       "modules":[{"id":"module:"+digest(k)[:12],"label":k,"count":v} for k,v in modules.most_common()],
       "patents":patents,"registration_members":member_payload,
       "registration_relations":[{"id":m["id"],"source":m["member_application_id"],"target":m["canonical_filing_application_id"],"type":m["relation_type"],"kind":"fact","source_proof":registration_module().public_record(m)["validated_proof"]} for m in registration["active"]],
       "insights":[i for i in active_insights(c) if set(i.get("patent_ids",[]))<=appids],"relations":relations,"detail_shards":{}}
    return payload,details
def render(c,output,preview=False,report_context=None):
    """Publish a report only after all data and asset checks succeed."""
    out=Path(output).resolve()
    require(not out.exists() or out.is_dir() and not any(out.iterdir()),"Output directory must be empty; preserve previous frozen delivery")
    out.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".patent-report-",dir=out.parent) as temporary:
        draft=Path(temporary)/"report"
        result=_render_staged(c,draft,preview,report_context)
        require(not out.exists() or out.is_dir() and not any(out.iterdir()),"Output changed while rendering; preserve existing delivery")
        if out.exists():out.rmdir()
        draft.replace(out)
    result["output"]=str(out)
    event(c,"render",{"path":str(out),"preview":preview,"status":result["status"]})
    return result

def _render_staged(c,output,preview=False,report_context=None):
    require(not preview or run_info(c)["scope"].get("synthetic") is True,"Test previews are restricted to explicitly synthetic runs")
    report=validate_run(c)
    require(preview or report["status"]=="complete","Formal render blocked: full-population gates failed; inspect validate/status")
    if not preview and research_quality_required(c):
        spec=importlib.util.spec_from_file_location("patent_perspectives_research_delivery",Path(__file__).with_name("research_delivery.py"))
        research_delivery=importlib.util.module_from_spec(spec);spec.loader.exec_module(research_delivery)
        research_delivery.validate(c,insights=active_insights(c),population_hash=population_hash(c),
            quality=research_quality_module(),require=require,check_refs=check_refs)
    # Required original pixels are checked before creating a delivery folder.
    # Unlike optional representative drawings, these support composed text.
    document_images=document_images_module()
    displayed_appids={a["id"] for a in included_applications(c)}
    embedded_images,embedded_blobs=document_images.prepare(c,displayed_appids,auxiliary_context())
    original_documents,original_blobs=original_claims_module().prepare(c,displayed_appids,original_claims_context())
    out=Path(output).resolve();pkg=Path(__file__).resolve().parents[1];assets=pkg/"assets"/"panorama"
    require(assets.is_dir(),"Panorama assets missing")
    require(not out.exists() or not any(out.iterdir()),"Output directory must be empty; preserve previous frozen delivery")
    out.mkdir(parents=True,exist_ok=True);(out/"data").mkdir(exist_ok=True)
    for name in ("index.html","style.css","app.js","timeline-zoom.css","timeline-zoom.js","timeline-reading.css","timeline-reading.js","ip-comparison.css","ip-comparison.js","industry-research.css","industry-research.js","research.css","research.js"):
        require((assets/name).is_file(),"Missing frontend asset "+name);shutil.copy2(assets/name,out/name)
    auxiliary=auxiliary_module();aux_items=auxiliary.records(c)
    image_paths,unavailable_images=auxiliary.copy_local_images(c,[item for item in aux_items if item["application_id"] in displayed_appids],out,auxiliary_context())
    document_images.copy_verified(embedded_blobs,out,auxiliary_context())
    original_claims_module().copy_verified(original_blobs,out,original_claims_context())
    payload,details=build_payload(c,report,image_paths,embedded_images,original_documents)
    payload["research"]=research_module().export(c,research_context())
    spec=importlib.util.spec_from_file_location("patent_perspectives_report_data",pkg/"scripts"/"report_data.py")
    report_data=importlib.util.module_from_spec(spec);spec.loader.exec_module(report_data)
    try:assembled=report_data.assemble(payload,details,sanitized(report_context or {}))
    except report_data.ReportDataError as exc:raise ValidationError(str(exc)) from exc
    report_data.emit(out,assembled)
    industry_data=assembled.get("industry-research.js",(None,None))[1]
    if industry_data is not None:
        export_spec=importlib.util.spec_from_file_location("patent_industry_exports",pkg/"scripts"/"industry_exports.py")
        industry_export=importlib.util.module_from_spec(export_spec);export_spec.loader.exec_module(industry_export)
        try:
            industry_export.package_materials(out,industry_data,(report_context or {}).get("industry_materials_root"))
            industry_export.emit(out,industry_data,sanitized(report_context or {}).get("industry_reference_corpora"))
        except ValueError as exc:raise ValidationError(str(exc)) from exc
    if unavailable_images:payload["run"]["limitations"].append("Some previously imported local image files are now missing or changed; those images remain unknown: "+str(len(unavailable_images)))
    if preview:
        payload["run"]["status"]="preview"
        payload["run"]["limitations"].insert(0,"TEST PREVIEW: not an accepted full-population delivery.")
    ids=list(details)
    for start in range(0,len(ids),40):
        chunkids=ids[start:start+40];filename="data/details-"+str(start//40).zfill(5)+".js"
        part={k:details[k] for k in chunkids}
        (out/filename).write_text("window.PP_registerDetails("+js_literal(part)+");\n",encoding="utf-8")
        for key in chunkids: payload["detail_shards"][key]=filename
    for p in payload["patents"]: p["detail_shard"]=payload["detail_shards"][p["id"]]
    (out/"data"/"bootstrap.js").write_text("window.PP_DATA="+js_literal(payload)+";\n",encoding="utf-8")
    (out/"validation.json").write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
    (out/"sources-and-coverage.json").write_text(json.dumps({"run":payload["run"],
      "registration_members":[registration_module().public_record(m) for m in registration_state(c)["active"]],
      "queries":[dict(r) for r in c.execute("SELECT * FROM queries")],
      "query_sets":rows_data(c,"query_sets"),"query_plan_contract":get_meta(c,"query_plan_contract"),
      "bibliography_sources":[{k:item.get(k) for k in ("id","publication_number","application_id","source_provider","source_artifact","artifact_sha256","record_path","provider_patent_type","normalized_patent_type","type_mapping_source","conflicts")} for item in rows_data(c,"bibliographies")],
      "population_reviews":rows_data(c,"population_reviews"),"candidate_review_states":population_state(c),
      "document_reviews":optional_rows_data(c,"document_reviews"),"analysis_invalidations":optional_rows_data(c,"analysis_invalidations"),
      "semantic_reviews":research_quality_module().records(c,"quality_reviews"),
      "research_plans":research_quality_module().records(c,"research_plan"),
      "research_reviews":research_quality_module().records(c,"research_reviews"),
       "research_workflow":research_module().export(c,research_context()),
       "research_retired":get_meta(c,"research_retired",{}),
      "auxiliary_sources":[auxiliary.public_record(i) for i in aux_items],
      "capabilities":rows_data(c,"capabilities")},ensure_ascii=False,indent=2),encoding="utf-8")
    overview_svg(out,payload)
    return {"output":str(out),"status":payload["run"]["status"],"applications":len(ids)}
def overview_svg(out,payload):
    import html
    run=payload["run"];cov=run["coverage"];mods=payload["modules"][:9]
    esc=lambda x:html.escape(str(x),quote=True)
    pieces=['<svg xmlns="http://www.w3.org/2000/svg" width="1280" height="800" viewBox="0 0 1280 800">',
      '<rect width="1280" height="800" fill="#f2f6fe"/>',
      '<text x="64" y="75" font-size="34" font-family="Microsoft YaHei,sans-serif" fill="#16396b">'+esc(run["company"])+' · 专利三视角</text>',
      '<text x="64" y="113" font-size="16" fill="#59718e">同源证据 · 管理层 / 研发 / 知识产权 · '+esc(run["as_of_date"])+'</text>']
    for i,(label,value) in enumerate([("范围内公开申请",cov["applications"]),("发明申请",sum(p["patent_type"]=="invention" for p in payload["patents"])),("授权有效",sum(p["legal_status"]=="有效" for p in payload["patents"])),("申请中 / 审查中",sum(p["legal_status"]=="审中" for p in payload["patents"]))]):
        x=64+i*292
        pieces.extend([f'<rect x="{x}" y="150" width="270" height="120" rx="14" fill="white" stroke="#d7e5fb"/>',
          f'<text x="{x+20}" y="187" font-size="16" fill="#59718e">{esc(label)}</text>',
          f'<text x="{x+20}" y="238" font-size="30" fill="#276dd7">{esc(value)}</text>'])
    for i,m in enumerate(mods):
        x=64+(i%3)*390;y=305+(i//3)*125
        pieces.extend([f'<rect x="{x}" y="{y}" width="368" height="105" rx="12" fill="white" stroke="#d7e5fb"/>',
          f'<text x="{x+18}" y="{y+38}" font-size="19" fill="#16396b">{esc(m["label"][:17])}</text>',
          f'<text x="{x+18}" y="{y+77}" font-size="17" fill="#276dd7">{m["count"]} 件申请</text>'])
    pieces.append('<text x="64" y="758" font-size="14" fill="#59718e">技术全文、法律状态与图片覆盖分别计算；详情与原文依据见交互页面。</text></svg>')
    (out/"overview.svg").write_text("\n".join(pieces),encoding="utf-8")
def package_skill(output):
    root=Path(__file__).resolve().parents[1];dest=Path(output).resolve()
    require(dest.suffix.lower()==".zip","Package output must be .zip")
    require(not dest.is_relative_to(root),"ZIP must be outside skill directory")
    dest.parent.mkdir(parents=True,exist_ok=True)
    allowed_dirs={"scripts","references","assets","agents","tests"}
    allowed_files={"SKILL.md","DESIGN.md","ORIGINALITY.md","README.md","LICENSE","LICENSE.txt","CHANGELOG.md"}
    files=[]
    for p in root.rglob("*"):
        if not p.is_file() or any(part in p.parts for part in ("__pycache__",".runtime",".pytest_cache",".git")) or p.suffix in (".pyc",".sqlite",".db",".zip"):continue
        rel=p.relative_to(root)
        if rel.parts[0] in allowed_dirs or str(rel) in allowed_files: files.append(p)
    require((root/"SKILL.md") in files,"SKILL.md missing")
    with zipfile.ZipFile(dest,"w",compression=zipfile.ZIP_DEFLATED) as z:
        for p in sorted(files):z.write(p,Path(root.name)/p.relative_to(root))
    return {"output":str(dest),"release":SKILL_RELEASE,"files":len(files),"sha256":hashlib.sha256(dest.read_bytes()).hexdigest()}
def cli(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version",action="version",version="%(prog)s "+SKILL_RELEASE)
    parser.add_argument("--db",help="Run SQLite path; run files must remain outside the skill package")
    sub=parser.add_subparsers(dest="command",required=True)
    p=sub.add_parser("init");p.add_argument("--company",required=True);p.add_argument("--as-of");p.add_argument("--scope")
    for name in ("entities-import","scope-confirm","capability-import","materials-import","search-import","query-set-import","query-plan-confirm","bibliography-import","auxiliary-import","population-review-import","registration-member-import","document-import","document-review-import","analysis-import","insights-import","relations-import","semantic-review-import","research-plan-import","research-review-import","research-import"):
        p=sub.add_parser(name);p.add_argument("--input",required=True)
    p=sub.add_parser("query-complete");p.add_argument("--query-id",required=True)
    p=sub.add_parser("export-work");p.add_argument("--output",required=True);p.add_argument("--max-primary-characters",type=int,help="Defer whole documents exceeding this user-chosen character limit; never truncate. Not a token budget.")
    p=sub.add_parser("export-quality-work");p.add_argument("--output",required=True);p.add_argument("--review-packets",help="Optional directory for per-patent original-source packets and separately stored draft comparisons")
    p=sub.add_parser("research-export");p.add_argument("--output",required=True)
    sub.add_parser("status");sub.add_parser("validate")
    p=sub.add_parser("render");p.add_argument("--output",required=True);p.add_argument("--report-context",help="Source-backed product classifications, reporting scope and optional corporate facts JSON");p.add_argument("--preview",action="store_true",help="Explicit test preview, never an accepted full report")
    p=sub.add_parser("package");p.add_argument("--output",required=True)
    args=parser.parse_args(argv)
    if args.command=="package":return package_skill(args.output),0
    require(args.db,"--db required")
    dbpath=Path(args.db).resolve();root=Path(__file__).resolve().parents[1]
    require(not dbpath.is_relative_to(root),"Run database must be outside reusable skill package")
    conn=db_open(dbpath)
    try:
        with conn:
            if args.command=="init":result=init_run(conn,args)
            else:
                run_info(conn)
                if args.command=="entities-import":result=import_entities(conn,read_input(args.input))
                elif args.command=="scope-confirm":result=scope_confirm(conn,read_input(args.input))
                elif args.command=="materials-import":result=materials_module().import_manifest(conn,read_input(args.input),material_engine())
                elif args.command=="capability-import":result=import_capabilities(conn,read_input(args.input))
                elif args.command=="search-import":result=import_search(conn,read_input(args.input))
                elif args.command=="query-set-import":result=import_query_sets(conn,read_input(args.input))
                elif args.command=="query-plan-confirm":result=query_plan_confirm(conn,read_input(args.input))
                elif args.command=="bibliography-import":result=import_bibliographies(conn,read_input(args.input))
                elif args.command=="auxiliary-import":result=import_auxiliary(conn,read_input(args.input))
                elif args.command=="population-review-import":result=import_population_reviews(conn,read_input(args.input))
                elif args.command=="registration-member-import":result=import_registration_members(conn,read_input(args.input))
                elif args.command=="query-complete":result=complete_query(conn,args.query_id)
                elif args.command=="document-import":result=[import_document(conn,x) for x in as_list(read_input(args.input))]
                elif args.command=="document-review-import":result=import_document_reviews(conn,read_input(args.input))
                elif args.command=="analysis-import":result=[import_analysis(conn,x) for x in as_list(read_input(args.input))]
                elif args.command=="insights-import":result=import_insights(conn,read_input(args.input))
                elif args.command=="relations-import":result=import_relations(conn,read_input(args.input))
                elif args.command=="research-import":result=research_module().import_workflow(conn,research_context(),read_input(args.input))
                elif args.command=="research-export":
                    destination=Path(args.output)
                    require(not destination.exists(),"Preserve existing research export")
                    destination.parent.mkdir(parents=True,exist_ok=True)
                    destination.write_text(json.dumps(research_module().export(conn,research_context()),ensure_ascii=False,indent=2),encoding="utf-8")
                    result={"output":str(destination)}
                elif args.command=="semantic-review-import":result=research_quality_module().import_review(conn,read_input(args.input),research_quality_context())
                elif args.command=="research-plan-import":result=research_quality_module().import_plan(conn,read_input(args.input),research_quality_context())
                elif args.command=="research-review-import":result=research_quality_module().import_research(conn,read_input(args.input),research_quality_context())
                elif args.command=="export-quality-work":result=research_quality_module().export_work(conn,args.output,research_quality_context(),review_packets=args.review_packets)
                elif args.command=="export-work":result=export_work(conn,args.output,args.max_primary_characters)
                elif args.command=="status":result=status_run(conn)
                elif args.command=="validate":result=validate_run(conn)
                elif args.command=="render":result=render(conn,args.output,args.preview,read_input(args.report_context) if args.report_context else None)
                else:raise ValidationError("Unknown command")
        return result, (3 if args.command=="validate" and result["status"]!="complete" else 0)
    finally:conn.close()
def main():
    # JSON output must keep Chinese text portable across Windows console code pages.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    try:
        result,code=cli();print(json.dumps(result,ensure_ascii=False,indent=2));return code
    except (ValidationError,OSError,sqlite3.Error,json.JSONDecodeError) as exc:
        print(json.dumps({"error":str(exc),"type":type(exc).__name__},ensure_ascii=False),file=sys.stderr);return 2
if __name__=="__main__":sys.exit(main())
