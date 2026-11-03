"""Reviewed research must reach the reader's existing role conclusions."""
import copy
import importlib.util
import json
import unittest

import test_research_quality as fixtures

engine = fixtures.engine
quality = fixtures.quality
spec = importlib.util.spec_from_file_location("research_delivery_under_test", fixtures.fixtures.ROOT / "scripts/research_delivery.py")
delivery = importlib.util.module_from_spec(spec)
spec.loader.exec_module(delivery)


class ResearchDeliveryTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.ResearchQualityTests(methodName="runTest")
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.c = self.fixture.c
        self.apps = self.fixture.apps
        self.directory = self.fixture.fixture.directory
        engine.import_insights(self.c, [self.fixture.fixture.insight(role, self.apps[0]) for role in engine.ROLES])
        self.fixture.complete()

    def insight(self, questions=None, evidence_ids=None, role="rd", identifier="research-reader-conclusion"):
        return {"id": identifier, "role": role,
                "title": "Synthetic chamber relationship comparison",
                "body": "Both reviewed synthetic versions connect a piston and chamber; this supports a bounded structural comparison, with no measured performance ranking.",
                "scope": "Two synthetic versions only", "limitations": ["Synthetic fixture only"],
                "kind": "observation", "patent_ids": self.apps,
                "evidence_ids": evidence_ids if evidence_ids is not None else ["evidence-" + app for app in self.apps],
                "research_question_ids": questions if questions is not None else ["q1"]}

    def import_insight(self, **changes):
        value = self.insight(**changes)
        engine.import_insights(self.c, [value])
        return value

    def validate(self, insights=None):
        return delivery.validate(self.c,
            insights=engine.active_insights(self.c) if insights is None else insights,
            population_hash=engine.population_hash(self.c), quality=quality,
            require=engine.require, check_refs=engine.check_refs)

    def second_question(self):
        plan = self.fixture.plan()
        plan["questions"].append({"id": "q2", "question": "What connection does the first source disclose?",
            "application_ids": [self.apps[0]], "selection_basis": "Bounded single-source structural explanation."})
        plan["revision_reason"] = "Add an independently bounded synthetic research question."
        quality.import_plan(self.c, plan, fixtures.CTX)
        first = self.fixture.research()
        second = copy.deepcopy(first)
        second.update(question_id="q2", evidence_ids=["evidence-" + self.apps[0]],
            answer="The first synthetic source connects the piston to the chamber.",
            comparison={"status": "not_comparable", "basis": "This question concerns one source, without claiming a cross-source ranking."})
        quality.import_research(self.c, [first, second], fixtures.CTX)

    def test_quality_complete_without_reader_mapping_blocks_formal_delivery(self):
        self.assertEqual(engine.validate_run(self.c)["status"], "complete")
        out = self.directory / "reader"
        with self.assertRaisesRegex(engine.ValidationError, "missing reader-facing insight.*q1"):
            engine.render(self.c, out)
        self.assertFalse(out.exists())
        self.assertEqual(list(out.parent.glob(".patent-report-*")), [])

    def test_one_appropriate_role_can_carry_the_answer_and_render(self):
        insight = self.import_insight()
        self.assertEqual(self.validate(), {"research_questions": 1, "mapped_questions": 1})
        out = self.directory / "reader"
        result = engine.render(self.c, out)
        self.assertEqual(result["status"], "complete")
        text = (out / "data/bootstrap.js").read_text(encoding="utf-8")
        payload = json.loads(text.removeprefix("window.PP_DATA=").removesuffix(";\n"))
        mapped = [item for item in payload["insights"] if item.get("research_question_ids")]
        self.assertEqual(len(mapped), 1)
        self.assertEqual(mapped[0]["role"], "rd")
        self.assertEqual(mapped[0]["body"], insight["body"])

    def test_unknown_question_and_malformed_links_are_rejected(self):
        for links in (["missing-question"], [], "q1", ["q1", "q1"]):
            with self.subTest(links=links):
                value = self.insight(questions=links)
                value["population_hash"] = engine.population_hash(self.c)
                with self.assertRaises(engine.ValidationError):
                    self.validate(insights=[value])

    def test_citing_only_one_side_of_reviewed_comparison_is_insufficient(self):
        self.import_insight(evidence_ids=["evidence-" + self.apps[0]])
        with self.assertRaisesRegex(engine.ValidationError, "omits reviewed evidence"):
            self.validate()

    def test_link_cannot_relabel_another_questions_evidence(self):
        self.second_question()
        self.import_insight()
        self.import_insight(questions=["q2"], identifier="wrongly-linked-question")
        with self.assertRaisesRegex(engine.ValidationError, "outside its linked question scope"):
            self.validate()

    def test_one_insight_can_cover_multiple_reviewed_questions(self):
        self.second_question()
        self.import_insight(questions=["q1", "q2"])
        self.assertEqual(self.validate(), {"research_questions": 2, "mapped_questions": 2})

    def test_current_question_answer_must_not_remain_unmapped(self):
        self.second_question()
        self.import_insight()
        with self.assertRaisesRegex(engine.ValidationError, "missing reader-facing insight.*q2"):
            self.validate()

    def test_stale_insight_does_not_cover_current_research(self):
        value = self.insight()
        value["population_hash"] = "an-earlier-population"
        with self.assertRaisesRegex(engine.ValidationError, "insight is stale"):
            self.validate(insights=[value])

    def test_changed_analysis_requires_fresh_research_before_mapping(self):
        self.import_insight()
        value = self.fixture.analysis(self.fixture.docs[0])
        value["summary"]["text"] = "A revised synthetic reading preserves its original connection evidence."
        engine.import_analysis(self.c, value)
        with self.assertRaisesRegex(engine.ValidationError, "current resolved and reviewed answer"):
            self.validate()

    def test_synthetic_opt_out_keeps_legacy_delivery_compatible(self):
        run = engine.run_info(self.c)
        run["scope"]["require_research_quality"] = False
        engine.set_meta(self.c, "run", run)
        result = engine.render(self.c, self.directory / "synthetic-legacy-reader")
        self.assertEqual(result["status"], "complete")

    def test_explicit_synthetic_preview_does_not_claim_formal_mapping(self):
        result = engine.render(self.c, self.directory / "synthetic-preview", preview=True)
        self.assertEqual(result["status"], "preview")


if __name__ == "__main__":
    unittest.main()
