"""Reproduce a SYNTHETIC software fixture; no network, model or real review."""
from pathlib import Path
import argparse
import copy
import importlib.util
import json
import sys

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
SKILL = REPO / "patent-perspectives"


def generate(output):
    output = Path(output).resolve()
    if output.exists() and any(output.iterdir()):
        raise ValueError("Use a new or empty output directory; preserve previous runs")
    if output.is_relative_to(SKILL.resolve()):
        raise ValueError("Demo output must stay outside the reusable skill")
    output.mkdir(parents=True, exist_ok=True)
    spec = importlib.util.spec_from_file_location("synthetic_demo_engine", SKILL / "scripts/patent_perspectives.py")
    engine = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(engine)
    data = json.loads((HERE / "fixture.json").read_text(encoding="utf-8"))
    database = output / "synthetic.sqlite"
    log = []

    def call(command, *args):
        result, code = engine.cli(["--db", str(database), command, *map(str, args)])
        log.append({"command": command, "exit_code": code})
        if code and command != "validate":
            raise ValueError("Demo command failed: " + command)
        return result

    def load(command, value, name):
        path = output / (name + ".json")
        path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
        return call(command, "--input", path)

    scope = output / "scope.json"
    scope.write_text(json.dumps(data["scope"]), encoding="utf-8")
    call("init", "--company", "SYNTHETIC OPTICAL MECHANISM DEMO", "--as-of", "2026-11-02", "--scope", scope)
    load("entities-import", data["entities"], "entities")
    load("scope-confirm", data["scope_confirmation"], "scope-confirmation")
    for search in data["searches"]:
        load("search-import", search, "search-" + search["query"]["kind"])
        call("query-complete", "--query-id", search["query"]["id"])
    for n, document in enumerate(data["documents"], 1):
        load("document-import", document, "document-" + str(n))
    load("analysis-import", data["analyses"], "analyses")
    load("research-import", data["research"], "research-partial")
    incomplete = call("validate")
    assert incomplete["status"] == "incomplete", incomplete
    manifest_file = output / "review-manifest.json"
    call("export-quality-work", "--output", manifest_file, "--review-packets", output / "review-packets")
    manifest = json.loads(manifest_file.read_text(encoding="utf-8"))

    # Explicit test-fixture construction, not a claim of new independent reading.
    # Real research must obtain these records from an actual different reviewer.
    versions = {r["application_id"]: r for r in manifest["semantic_reviews"]}
    reviews = copy.deepcopy(data["semantic_review_fixtures"])
    for review in reviews:
        review["analysis_fingerprint"] = versions[review["application_id"]]["analysis_fingerprint"]
    load("semantic-review-import", reviews, "synthetic-review-fixtures")
    research_review = copy.deepcopy(data["research_review_fixture"])
    version = next(r for r in manifest["research_reviews"] if r["question_id"] == research_review["question_id"])
    research_review.update(plan_hash=version["plan_hash"], population_hash=version["population_hash"])
    load("research-review-import", research_review, "synthetic-topic-review-fixture")
    still_partial = call("validate")
    assert still_partial["status"] == "incomplete"
    assert {r["code"] for r in still_partial["errors"]} == {"research_workflow_unfinished"}
    answered = copy.deepcopy(data["research"])
    answered["questions"][0].update(status="answered", answer=research_review["answer"], remaining=[])
    load("research-import", answered, "research-answered")
    final = call("validate")
    assert final["status"] == "complete", final
    context = output / "report-context.json"
    context.write_text(json.dumps(data["report_context"], ensure_ascii=False, indent=2), encoding="utf-8")
    call("render", "--output", output / "report", "--report-context", context)
    (output / "commands.json").write_text(json.dumps(log, indent=2), encoding="utf-8")
    (output / "validation.json").write_text(json.dumps(final, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"status": "complete", "synthetic": True, "review_mode": "fixed_test_fixture_only",
            "report": str(output / "report/index.html")}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(generate(args.output), ensure_ascii=False, indent=2))
