"""Check that reviewed research is carried into existing reader-facing insights.

This checks explicit links, source coverage and freshness. It neither writes
reader prose nor judges whether the prose correctly explains the evidence.
"""
from __future__ import annotations


def _identifiers(value):
    return (isinstance(value, list) and bool(value)
            and all(isinstance(item, str) and item.strip() for item in value)
            and len(value) == len(set(value)))


def validate(c, *, insights, population_hash, quality, require, check_refs):
    """Validate explicit research_question_ids on current active insights.

    The caller applies this only to formal deliveries with research quality
    enabled, after the ordinary completeness and quality checks have passed.
    """
    plan = next((item for item in quality.records(c, "research_plan")
                 if item.get("id") == "active"), None)
    if not plan:
        # A technical population without a plan is rejected by validate_run.
        # An empty technical population legitimately has no research plan.
        return {"research_questions": 0, "mapped_questions": 0}
    questions = {item["id"]: item for item in plan["questions"]}
    results = {item["id"]: item for item in quality.records(c, "research_reviews")}
    reviewed = {}
    for question_id in questions:
        result = results.get(question_id)
        require(result and result.get("status") == "resolved"
                and result.get("review_result") == "pass"
                and result.get("plan_hash") == plan["plan_hash"]
                and result.get("population_hash") == population_hash,
                "Research delivery needs a current resolved and reviewed answer: "
                + question_id + "; refresh its research review before rendering")
        reviewed[question_id] = result
    mapped = set()
    for insight in insights:
        if "research_question_ids" not in insight:
            continue
        question_ids = insight["research_question_ids"]
        require(_identifiers(question_ids),
                "Insight research_question_ids must be nonempty unique question IDs: " + str(insight.get("id")))
        unknown = set(question_ids) - set(questions)
        require(not unknown, "Insight maps unknown research question(s): " + ", ".join(sorted(unknown)))
        require(insight.get("population_hash") == population_hash,
                "Research-mapped insight is stale; reconsider and re-import it: " + str(insight.get("id")))
        evidence_ids = insight.get("evidence_ids")
        require(_identifiers(evidence_ids),
                "Research-mapped insight needs original evidence_ids: " + str(insight.get("id")))
        required_evidence = set().union(*(set(reviewed[q]["evidence_ids"]) for q in question_ids))
        missing_evidence = required_evidence - set(evidence_ids)
        require(not missing_evidence,
                "Research-mapped insight omits reviewed evidence for " + ", ".join(question_ids)
                + ": " + ", ".join(sorted(missing_evidence))
                + "; carry the reviewed answer and its source evidence into the insight")
        refs = check_refs(c, evidence_ids)
        allowed_apps = set().union(*(set(questions[q]["application_ids"]) for q in question_ids))
        require({ref["application_id"] for ref in refs} <= allowed_apps,
                "Research-mapped insight cites evidence outside its linked question scope: " + str(insight.get("id")))
        mapped.update(question_ids)
    missing = set(questions) - mapped
    require(not missing,
            "Research delivery missing reader-facing insight(s) for question(s): " + ", ".join(sorted(missing))
            + "; use insights-import to link an existing role insight with research_question_ids and the reviewed evidence_ids")
    return {"research_questions": len(questions), "mapped_questions": len(mapped)}
