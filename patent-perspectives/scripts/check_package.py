#!/usr/bin/env python3
"""Check this package's deliberately simple skill metadata and local resources, without dependencies."""
import ast
import json
import re
import sys
from pathlib import Path
def check(root):
    root=Path(root).resolve();errors=[];checked=[]
    for rel in ("SKILL.md","ORIGINALITY.md","agents/openai.yaml","scripts/patent_perspectives.py","references/acquisition.md","references/data-contract.md","references/analysis-roles.md","assets/panorama/index.html","assets/panorama/style.css","assets/panorama/app.js","assets/panorama/timeline-zoom.css","assets/panorama/timeline-zoom.js","assets/panorama/timeline-reading.css","assets/panorama/timeline-reading.js","references/compact-timelines.md","references/claim-comparison.md","references/data-reuse.md","references/incremental-analysis.md","scripts/claim_comparison.py","scripts/export_reuse.py","scripts/compare_snapshots.py","assets/panorama/ip-comparison.js","assets/panorama/ip-comparison.css","scripts/industry_research.py","scripts/industry_exports.py","references/company-research-tasks.md","references/route-assessment.md","references/evidence-matrix.md","references/industry-data-contract.md","assets/panorama/industry-research.js","assets/panorama/industry-research.css"):
        if not (root/rel).is_file():errors.append("Missing "+rel)
    skill=root/"SKILL.md"
    for rel in ("DESIGN.md","references/material-research.md","references/reader-template.md","scripts/materials.py","scripts/render_reader.py","assets/reader/index.html","assets/reader/report.css","assets/reader/report.js","assets/reader/example.json"):
        if not (root/rel).is_file():errors.append("Missing "+rel)
    for rel in ("scripts/research_workflow.py","scripts/research_quality.py","scripts/research_delivery.py","references/research-workflow.md","references/whole-patent-research.md","assets/panorama/research.js","assets/panorama/research.css"):
        if not (root/rel).is_file():errors.append("Missing "+rel)
    if skill.is_file():
        text=skill.read_text(encoding="utf-8")
        m=re.match(r"\A---\r?\n(.*?)\r?\n---(?:\r?\n|$)",text,re.S)
        if not m:errors.append("Missing YAML frontmatter boundaries")
        else:
            # This package intentionally uses only two single-line scalar entries.
            entries={}
            for line in m.group(1).splitlines():
                if not line.strip():continue
                pair=re.fullmatch(r"(name|description):[ \t]+(.+)",line)
                if not pair:errors.append("Unsupported metadata line: "+line);continue
                key,val=pair.groups()
                if key in entries:errors.append("Duplicate metadata key: "+key)
                if val[0:1] in ("'",'"'):
                    try:val=ast.literal_eval(val)
                    except (ValueError,SyntaxError):errors.append("Invalid quoted scalar: "+key);continue
                elif re.search(r":\s|(?:^|\s)#",val):errors.append("Quote ambiguous YAML scalar: "+key)
                entries[key]=val
            if set(entries)!={"name","description"}:errors.append("Require name and description")
            if entries.get("name")!="patent-perspectives":errors.append("Unexpected skill name")
            if not 1<=len(entries.get("description",""))<=1024:errors.append("Invalid description length")
    for p in root.rglob("*.md"):
        text=p.read_text(encoding="utf-8")
        for target in re.findall(r"\[[^\]]*\]\(([^)]+)\)",text):
            target=target.strip("<>").split("#")[0]
            if not target or re.match(r"^[a-z]+:",target,re.I):continue
            destination=(p.parent/target).resolve()
            if not destination.is_relative_to(root):errors.append("Reference escapes package: "+target)
            elif not destination.exists():errors.append("Broken local reference: "+str(p.relative_to(root))+":"+target)
        checked.append(str(p.relative_to(root)))
    for p in root.rglob("*.py"):
        if "__pycache__" in p.parts:continue
        try:compile(p.read_text(encoding="utf-8"),str(p),"exec")
        except SyntaxError as e:errors.append(str(e))
    for p in root.rglob("*"):
        if p.is_file() and (p.name in (".env","config.toml","auth.json") or p.suffix.lower() in (".sqlite",".db",".zip")):errors.append("Runtime/private artifact in package: "+str(p.relative_to(root)))
    ui=root/"agents"/"openai.yaml"
    if ui.is_file():
        text=ui.read_text(encoding="utf-8")
        for key in ("display_name","short_description","default_prompt"):
            if not re.search(r"^\s*"+key+r':\s*".*"\s*$',text,re.M):errors.append("Missing quoted UI field: "+key)
        if "$patent-perspectives" not in text:errors.append("Default prompt must invoke the skill")
    return {"status":"passed" if not errors else "failed","validator":"package-specific standard-library checks","official_quick_validate":"separate_validation_required","checked_documents":checked,"errors":errors}
if __name__=="__main__":
    result=check(Path(sys.argv[1]) if len(sys.argv)>1 else Path(__file__).resolve().parents[1])
    print(json.dumps(result,ensure_ascii=False,indent=2))
    sys.exit(0 if not result["errors"] else 1)
