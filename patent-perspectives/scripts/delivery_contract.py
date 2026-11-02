"""Frozen exception delivery: retains full-run failures and permits only reviewed gaps.

The host reviews technical meaning and records the user's applicable direction.
This module cannot authorize delivery or turn missing evidence into completion.
"""
import hashlib
import json
from pathlib import Path

MODE = "reviewed_with_exceptions"
CODES = {"population_review_pending", "technical_analysis_missing"}


def hash_json(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
        separators=(",", ":")).encode("utf-8")).hexdigest()


def database_digest(c):
    """Bind all stored facts and reviews, excluding only append-only event logging."""
    h = hashlib.sha256()
    names = [r[0] for r in c.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")
        if r[0] != "events"]
    for name in names:
        quoted = '"' + name.replace('"', '""') + '"'
        columns = list(c.execute("PRAGMA table_info(" + quoted + ")"))
        primary = sorted((r[5], r[1]) for r in columns if r[5])
        order = ",".join('"' + key.replace('"', '""') + '"' for _, key in primary) or "rowid"
        h.update(hash_json({"table": name, "columns": [tuple(r) for r in columns]}).encode())
        for row in c.execute("SELECT * FROM " + quoted + " ORDER BY " + order):
            h.update(hash_json(list(row)).encode())
    return h.hexdigest()


def errors(report, require):
    keys = []
    for error in report["errors"]:
        require(set(error) == {"code", "detail"} and error["code"] in CODES
                and isinstance(error["detail"], str) and error["detail"],
                "Exception delivery cannot defer this validation error: " + str(error.get("code")))
        keys.append((error["code"], error["detail"]))
    require(len(keys) == len(set(keys)), "Duplicate validation errors")
    require(keys and report["status"] == "incomplete", "Use ordinary render for a complete run")
    return sorted(keys)


def bindings(c, engine, report, context, records):
    return {
        "run_id": engine.run_info(c)["run_id"],
        "database_sha256": database_digest(c),
        "native_validation_sha256": hash_json(report),
        "report_context_sha256": hash_json(engine.sanitized(context or {})),
        "analysis_records_sha256": hashlib.sha256(records.encode("utf-8")).hexdigest(),
        "display_application_ids_sha256": hash_json(sorted(a["id"] for a in engine.included_applications(c))),
        "coverage": report["coverage"],
    }


def draft(c, engine, context, records):
    engine.require(isinstance(records, str) and records.strip(), "Analysis records are required")
    report = engine.validate_run(c)
    keys = errors(report, engine.require)
    return {
        "schema_version": 1, "delivery_mode": MODE, "reviewed_by_host": False,
        "user_direction": "", "report_scope_statement": "",
        "full_run_completion_claimed": False, "allow_additional_errors": False,
        "bindings": bindings(c, engine, report, context, records),
        "exceptions": [{"code": code, "application_id": app,
            "issue_id": "", "reason": "", "effect_on_report": "", "next_step": ""}
            for code, app in keys],
    }


def check(c, engine, report, contract, context, records):
    require = engine.require
    require(isinstance(contract, dict) and contract.get("schema_version") == 1
        and contract.get("delivery_mode") == MODE, "Unsupported exception contract")
    require(contract.get("reviewed_by_host") is True, "Exception draft has not been reviewed")
    require(contract.get("full_run_completion_claimed") is False
        and contract.get("allow_additional_errors") is False, "Cannot relax completion or error boundaries")
    require(all(isinstance(contract.get(k), str) and contract[k].strip()
        for k in ("user_direction", "report_scope_statement")), "Record user direction and truthful report scope")
    require(isinstance(records, str) and records.strip(), "Analysis records are required")
    expected = errors(report, require)
    items = contract.get("exceptions")
    require(isinstance(items, list), "Individual exception inventory required")
    accepted, ids = [], []
    for item in items:
        require(isinstance(item, dict) and all(isinstance(item.get(k), str) and item[k].strip()
            for k in ("code", "application_id", "issue_id", "reason", "effect_on_report", "next_step")),
            "Each exception needs an ID, reason, effect and next step")
        accepted.append((item["code"], item["application_id"]))
        ids.append(item["issue_id"])
        require(item["issue_id"] in records and item["application_id"] in records,
            "Each exception must be traceable in analysis records")
    require(len(ids) == len(set(ids)) and sorted(accepted) == expected,
        "Actual errors do not match exact reviewed exceptions")
    require(contract.get("bindings") == bindings(c, engine, report, context, records),
        "Database, scope, context, notes or validation changed after review")
    cov = report["coverage"]
    require(cov["invalidated_analyses"] == 0 and cov["registration_mapping_errors"] == 0,
        "Invalidated analysis or identity mapping cannot be deferred")
    require(cov["technical_applications"] - cov["technical_analyzed"] ==
        sum(code == "technical_analysis_missing" for code, _ in expected),
        "Technical denominator does not reconcile")
    # For selected periods/latest-N, native coverage can also count pending
    # candidates outside the selected scope. Bind the native coverage in full;
    # only actual selected-scope validation errors are accepted.
    require(cov["pending_applications"] >= sum(code == "population_review_pending" for code, _ in expected),
        "Pending identity denominator does not reconcile")
    return {"schema_version": 1, "delivery_mode": MODE,
        "delivery_gate": "passed_with_listed_exceptions",
        "native_full_run_status": report["status"], "full_run_completion_claimed": False,
        "contract_sha256": hash_json(contract), "accepted_exceptions": items,
        "bindings": contract["bindings"]}


def apply(payload, report, contract, gate):
    cov = report["coverage"]
    payload["run"]["status"] = MODE
    payload["run"]["full_run_status"] = report["status"]
    payload["run"]["full_run_completion_claimed"] = False
    payload["run"]["delivery"] = {
        "mode": MODE, "scope_statement": contract["report_scope_statement"],
        "contract_sha256": gate["contract_sha256"],
        "technical_analyzed": cov["technical_analyzed"],
        "technical_applications": cov["technical_applications"],
        "design_catalogue": cov["design_applications"],
        "population_pending": cov["pending_applications"],
    }
    statement = ("本次目录含" + str(cov["applications"]) + "件独立申请，技术结论依据"
        + str(cov["technical_analyzed"]) + "/" + str(cov["technical_applications"])
        + "件技术申请；外观设计" + str(cov["design_applications"])
        + "件单列。未完成技术事项不作为已读依据，主体待核候选不并入公司目录。")
    payload["run"]["limitations"].append(statement)


def emit(out, contract, gate, records):
    (out / "delivery-contract.json").write_text(json.dumps(contract, ensure_ascii=False, indent=2), encoding="utf-8")
    (out / "delivery-validation.json").write_text(json.dumps(gate, ensure_ascii=False, indent=2), encoding="utf-8")
    (out / "分析记录与后续补充说明.md").write_text(records, encoding="utf-8")
