"""Portable evidence checks shared by the four standalone patent skills."""

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path, PurePosixPath


def required_text(value, field):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} 必须是非空文本")
    return value


def indexed(rows, field):
    if not isinstance(rows, list) or not rows:
        raise ValueError(f"{field} 至少需要一条记录")
    result = {}
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError(f"{field} 的记录必须是对象")
        identity = required_text(row.get("id"), f"{field}.id")
        if identity in result:
            raise ValueError(f"{field} 重复 ID: {identity}")
        result[identity] = row
    return result


def source_path(value):
    value = required_text(value, "sources.path")
    parts = PurePosixPath(value)
    if parts.is_absolute() or re.search(r"[\\:\x00-\x1f]", value) or ".." in parts.parts or not parts.parts:
        raise ValueError("sources.path 必须是原件目录内的相对路径")
    return parts


def validate(packet):
    if not isinstance(packet, dict) or type(packet.get("schema_version")) is not int or packet["schema_version"] != 1:
        raise ValueError("交接文件的 schema_version 必须是 1")
    sources = indexed(packet.get("sources"), "sources")
    evidence = indexed(packet.get("evidence"), "evidence")
    for source in sources.values():
        if "publication" not in source:
            raise ValueError("必须明确记录公开号，未公开时填 null 并写明原因")
        if source["publication"] is None:
            required_text(source.get("publication_note"), "sources.publication_note")
        else:
            required_text(source["publication"], "sources.publication")
        required_text(source.get("version"), "sources.version")
        if not re.fullmatch(r"[0-9a-f]{64}", required_text(source.get("sha256"), "sources.sha256")):
            raise ValueError("sources.sha256 必须为原件字节的 64 位小写 SHA-256")
        source_path(source.get("path"))
    for item in evidence.values():
        sid = required_text(item.get("source_id"), "evidence.source_id")
        if sid not in sources:
            raise ValueError(f"未登记的原件 ID: {sid}")
        locations = item.get("locations")
        if not isinstance(locations, list) or not locations:
            raise ValueError("evidence.locations 至少记录一处原件位置")
        for loc in locations:
            required_text(loc, "evidence.locations")
        conditions = item.get("conditions")
        if not isinstance(conditions, dict) or conditions.get("state") not in ("stated", "unknown", "not_applicable"):
            raise ValueError("conditions.state 必须是 stated、unknown 或 not_applicable")
        values = conditions.get("values")
        if not isinstance(values, list) or (conditions["state"] == "stated" and not values):
            raise ValueError("conditions.values 必须是数组，stated 至少保留一项成立条件")
        for value in values:
            required_text(value, "conditions.values")
        if conditions["state"] != "stated":
            required_text(conditions.get("reason"), "conditions.reason")
        if item.get("kind") not in ("disclosure", "claimed_effect", "inference", "test", "unknown"):
            raise ValueError("evidence.kind 必须明确证据性质")
        required_text(item.get("statement"), "evidence.statement")
    return sources, evidence


def digest(path):
    with path.open("rb") as stream:
        value = hashlib.sha256()
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def source_issues(sources, root):
    root = root.resolve(strict=True)
    issues = {}
    for sid, source in sources.items():
        path = (root / source_path(source["path"])).resolve()
        if not path.is_relative_to(root):
            raise ValueError(f"原件路径越过指定目录: {sid}")
        try:
            actual = digest(path)
        except OSError:
            issues[sid] = "source_unavailable"
            continue
        if actual != source["sha256"]:
            issues[sid] = "source_bytes_changed"
    return issues


def compare(accepted, current, root):
    original_sources, original_evidence = validate(accepted)
    sources, evidence = validate(current)
    problems = source_issues(sources, root)
    handoff = []
    for eid in sorted(set(original_evidence) | set(evidence)):
        before, after = original_evidence.get(eid), evidence.get(eid)
        reasons = []
        if before is None:
            reasons.append("evidence_added")
        elif after is None:
            reasons.append("evidence_removed")
        else:
            source_before = original_sources[before["source_id"]]
            source_after = sources[after["source_id"]]
            for field in ("publication", "publication_note", "version", "sha256"):
                if source_before.get(field) != source_after.get(field):
                    reasons.append(f"{field}_changed")
            for field in ("source_id", "locations", "conditions", "kind", "statement"):
                if before[field] != after[field]:
                    reasons.append(f"{field}_changed")
        if after and after["source_id"] in problems:
            reasons.append(problems[after["source_id"]])
        if reasons:
            handoff.append({"evidence_id": eid, "source_id": (after or before)["source_id"], "reasons": reasons})
    return {"status": "recheck" if handoff or problems else "unchanged",
            "source_issues": problems, "evidence_to_recheck": handoff}


def main():
    parser = argparse.ArgumentParser(description="校验四项专利 Skill 的交接原件及证据变化")
    parser.add_argument("accepted", type=Path, help="上次实际采纳的交接文件，保持原样")
    parser.add_argument("current", type=Path, help="本次待采纳的交接文件")
    parser.add_argument("--source-root", type=Path, required=True, help="当前原件所在目录")
    args = parser.parse_args()
    try:
        result = compare(json.loads(args.accepted.read_text(encoding="utf-8-sig")),
                         json.loads(args.current.read_text(encoding="utf-8-sig")), args.source_root)
    except (OSError, ValueError) as exc:
        print(json.dumps({"status": "invalid", "error": str(exc)}, ensure_ascii=False))
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 1 if result["status"] == "recheck" else 0


if __name__ == "__main__":
    sys.exit(main())
