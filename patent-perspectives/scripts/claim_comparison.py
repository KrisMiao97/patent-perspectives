"""Validate authored claim-element comparisons against existing same-version evidence.

The host writes technical interpretations. This module only binds their references,
preserves unavailable versions, and prepares offline data for the IP reader.
"""
import re


class ClaimComparisonError(ValueError):
    pass


def require(value, message):
    if not value:
        raise ClaimComparisonError(message)


def nonempty(value, name):
    require(isinstance(value, str) and value.strip(), name + " must be nonempty text")
    return value


def claim_blocks(text):
    # Same canonical numbering and Python-Unicode offsets as the document importer.
    matches = list(re.finditer(r"(?m)^\s*(\d{1,4})\s*[.、．]\s*", text))
    result = []
    for i, match in enumerate(matches):
        start = match.start(1)
        end = matches[i + 1].start(1) if i + 1 < len(matches) else len(text)
        while end > start and text[end - 1].isspace():
            end -= 1
        result.append({"number": int(match.group(1)), "start": start, "end": end})
    require(result and [x["number"] for x in result] == list(range(1, len(result) + 1)),
            "Comparison document requires complete consecutive original claim numbering")
    return result


def claim_number(evidence):
    locator = evidence.get("locator")
    value = locator.get("claim_number") if isinstance(locator, dict) else None
    if value is None and isinstance(locator, str):
        match = re.search(r"(?:权利要求|[Cc]laim)\s*(\d+)", locator)
        value = int(match.group(1)) if match else None
    require(type(value) is int and value > 0, "Comparison evidence requires its actual claim number")
    return value


def prepare(payload, details, context=None):
    """Return {schema_version, groups}; omitted comparisons produce an empty group list.

    Each group contains mode (applications/versions), title, scope,
    selection_reason, cases and rows. Cases bind a document_id, or a known
    publication_number with document_id omitted when claims are unavailable.
    Each row has one cell per case: state, authored text and evidence_ids.
    A not_disclosed cell additionally declares reviewed_claim_numbers for the
    entire selected complete document. It never means absence in all patents.
    """
    groups = (context or {}).get("claim_comparisons", [])
    require(isinstance(groups, list), "claim_comparisons must be an array")
    appids = {p["id"] for p in payload["patents"]}
    output, groupids = [], set()
    for group in groups:
        require(isinstance(group, dict), "Each comparison group must be an object")
        gid = nonempty(group.get("id"), "Comparison id")
        require(gid not in groupids, "Duplicate comparison group id")
        groupids.add(gid)
        mode = group.get("mode", "applications")
        require(mode in ("applications", "versions"), "Comparison mode must be applications or versions")
        result = {"id": gid, "mode": mode,
                  "title": nonempty(group.get("title"), "Comparison title"),
                  "scope": nonempty(group.get("scope"), "Comparison scope"),
                  "selection_reason": nonempty(group.get("selection_reason"), "Comparison selection_reason"),
                  "summary": group.get("summary", ""), "cases": [], "rows": []}
        require(isinstance(result["summary"], str), "Comparison summary must be text")
        cases = group.get("cases")
        require(isinstance(cases, list) and len(cases) >= 2, "A comparison needs at least two columns")
        caseids, docs, evidence_index = set(), {}, {}
        for case in cases:
            require(isinstance(case, dict), "Comparison case must be an object")
            cid = nonempty(case.get("id"), "Comparison case id")
            require(cid not in caseids, "Duplicate case id in comparison")
            caseids.add(cid)
            appid = nonempty(case.get("application_id"), "Comparison application_id")
            require(appid in appids and appid in details, "Comparison case is outside the report population")
            detail = details[appid]
            document_id = case.get("document_id")
            require(document_id is None or isinstance(document_id, str) and bool(document_id.strip()),
                    "Comparison document_id must be nonempty text or omitted")
            selected = {"id": cid, "label": nonempty(case.get("label"), "Comparison case label"),
                        "application_id": appid, "document_id": document_id,
                        "filing_date": detail.get("filing_date"), "document": None}
            if document_id:
                document = next((d for d in detail.get("documents", []) if d["id"] == document_id), None)
                require(document and document.get("document_type") == "claims" and document.get("complete") is True,
                        "Comparison requires eligible complete claims from this application")
                require(not document.get("rejection_review_ids"), "Rejected document cannot support comparisons")
                pn = nonempty(document.get("publication_number"), "Document publication number")
                version = nonempty(document.get("version"), "Document version")
                require(version != "unknown", "Comparison document version must be identified")
                require(case.get("publication_number", pn) == pn, "Case publication does not match selected document")
                require(case.get("version", version) == version, "Case version does not match selected document")
                source_text = nonempty(document.get("text"), "Document text")
                blocks = claim_blocks(source_text)
                docs[cid] = (document, {b["number"]: b for b in blocks})
                selected.update(publication_number=pn, version=version,
                                document={"id": document_id, "application_id": appid,
                                          "publication_number": pn, "version": version,
                                          "language": document.get("language", "unknown"), "text": source_text,
                                          "claim_numbers": [b["number"] for b in blocks]})
                evidence_index[cid] = {e["id"]: e for e in detail.get("evidence", [])}
            else:
                pn = nonempty(case.get("publication_number"), "Unavailable version publication number")
                known = set(detail.get("publication_numbers", []))
                known.update(p.get("publication_number", p.get("id")) for p in detail.get("publications", []))
                require(pn in known, "Unavailable version must still have same-application bibliographic identity")
                require(not any(d.get("publication_number") == pn and d.get("document_type") == "claims"
                                and d.get("complete") is True for d in detail.get("documents", [])),
                        "Existing eligible claims cannot be labelled not acquired")
                selected.update(publication_number=pn, version="正文未取得")
                evidence_index[cid] = {}
            result["cases"].append(selected)
        apps = [c["application_id"] for c in result["cases"]]
        if mode == "versions":
            require(len(set(apps)) == 1, "Version comparison must stay within one independent application")
            require(len({c["publication_number"] for c in result["cases"]}) == len(cases),
                    "Version comparison needs distinct identified publication numbers")
        else:
            require(len(set(apps)) == len(apps), "Application comparison needs distinct independent applications")
        rowids = set()
        rows = group.get("rows")
        require(isinstance(rows, list) and rows, "Comparison must contain authored element rows")
        for row in rows:
            require(isinstance(row, dict), "Comparison row must be an object")
            rid = nonempty(row.get("id"), "Comparison row id")
            require(rid not in rowids, "Duplicate comparison row id")
            rowids.add(rid)
            target = {"id": rid, "label": nonempty(row.get("label"), "Comparison row label"),
                      "category": row.get("category", "other"), "question": row.get("question", ""), "cells": []}
            require(isinstance(target["category"], str) and isinstance(target["question"], str),
                    "Comparison category and question must be text")
            cells = row.get("cells")
            require(isinstance(cells, list) and len(cells) == len(cases)
                    and all(isinstance(c, dict) and isinstance(c.get("case_id"), str) for c in cells)
                    and {c["case_id"] for c in cells} == caseids,
                    "Every comparison row needs exactly one cell for every case")
            for cell in cells:
                cid, state = cell["case_id"], cell.get("state")
                require(state in ("disclosed", "not_disclosed", "not_acquired"), "Unknown comparison cell state")
                text = nonempty(cell.get("text"), "Comparison cell explanation")
                ids = cell.get("evidence_ids", [])
                require(isinstance(ids, list) and all(isinstance(eid, str) for eid in ids)
                        and len(ids) == len(set(ids)), "Comparison evidence_ids must be unique strings")
                outcell = {"case_id": cid, "state": state, "text": text, "evidence": []}
                if state == "not_acquired":
                    require(cid not in docs and not ids, "Not-acquired cell cannot use an available document or evidence")
                else:
                    require(cid in docs, "A technical assertion requires an acquired complete document")
                    document, blocks = docs[cid]
                    selected = next(c for c in result["cases"] if c["id"] == cid)
                    if state == "disclosed":
                        require(ids, "Disclosed comparison cell requires exact source evidence")
                    else:
                        reviewed = cell.get("reviewed_claim_numbers")
                        require(isinstance(reviewed, list) and all(type(n) is int for n in reviewed)
                                and len(reviewed) == len(set(reviewed)) and set(reviewed) == set(blocks),
                                "Not-disclosed statement requires an explicit complete claim-reading declaration")
                        outcell["reviewed_claim_numbers"] = reviewed
                    for eid in ids:
                        ev = evidence_index[cid].get(eid)
                        require(ev and ev.get("application_id") == selected["application_id"]
                                and ev.get("document_id") == document["id"], "Cross-application or cross-document comparison evidence")
                        require(ev.get("publication_number") == document["publication_number"]
                                and ev.get("version") == document["version"], "Comparison evidence publication/version mismatch")
                        start, end, quote = ev.get("start"), ev.get("end"), ev.get("quote")
                        require(type(start) is int and type(end) is int and 0 <= start < end <= len(document["text"])
                                and isinstance(quote, str) and document["text"][start:end] == quote,
                                "Comparison source quotation does not match exact text span")
                        number = claim_number(ev)
                        block = blocks.get(number)
                        require(block and block["start"] <= start < end <= block["end"],
                                "Comparison quotation is outside its declared claim")
                        outcell["evidence"].append({"evidence_id": eid, "document_id": document["id"],
                            "application_id": selected["application_id"], "publication_number": document["publication_number"],
                            "version": document["version"], "claim_number": number,
                            "start": start, "end": end, "quote": quote})
                target["cells"].append(outcell)
            result["rows"].append(target)
        output.append(result)
    return {"schema_version": 1, "groups": output}
