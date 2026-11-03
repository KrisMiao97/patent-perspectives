"""Unified workflow/quality gates using synthetic originals and real imports."""
import copy
import json
import unittest

from test_research_workflow import ResearchTests


class UnifiedResearchTests(unittest.TestCase):
    setUp = ResearchTests.setUp
    load = ResearchTests.load
    complete = ResearchTests.complete

    def module(self):
        return self.e.research_module()

    def quality(self):
        return self.e.research_quality_module()

    def plan(self):
        return next(p for p in self.quality().records(self.c, 'research_plan') if p['id'] == 'active')

    def codes(self):
        return {v['code'] for v in self.module().check(self.c, self.e.research_context())}

    def test_initial_import_creates_same_stable_plan_without_reviews(self):
        self.load()
        self.assertEqual(self.plan()['questions'], [dict(id='q', question=self.p['questions'][0]['text'],
            application_ids=sorted(self.apps), selection_basis='Optics only')])
        self.assertEqual(self.quality().records(self.c, 'research_reviews'), [])
        self.assertEqual(self.quality().records(self.c, 'quality_reviews'), [])
        self.assertEqual(self.codes(), {'research_workflow_unfinished'})
        for finding in self.e.active_insights(self.c):
            self.assertEqual(finding['question_ids'], finding['research_question_ids'])

    def test_answered_import_cannot_create_passing_review_or_leave_half_records(self):
        p=copy.deepcopy(self.p);p['questions'][0].update(status='answered', remaining=[])
        with self.assertRaisesRegex(ValueError, 'resolved/pass'):
            self.load(p)
        self.assertIsNone(self.e.get_meta(self.c, 'research_workflow'))
        self.assertEqual(self.quality().records(self.c, 'research_plan'), [])
        self.assertEqual(self.quality().records(self.c, 'research_reviews'), [])
        self.assertEqual(self.e.rows_data(self.c, 'insights'), [])
        self.assertEqual(self.e.rows_data(self.c, 'relations'), [])

    def test_existing_plan_is_reused_without_silently_changing_selection_basis(self):
        self.quality().import_plan(self.c, dict(questions=[dict(id='q', question=self.p['questions'][0]['text'],
            application_ids=self.apps, selection_basis='Previously reviewed explicit selection reason.')]), self.e.research_quality_context())
        before=copy.deepcopy(self.plan())
        self.load()
        self.assertEqual(before, self.plan())

    def test_conflicting_existing_plan_is_not_overwritten(self):
        self.quality().import_plan(self.c, dict(questions=[dict(id='q', question='A different engineering question?',
            application_ids=self.apps, selection_basis='Explicit existing plan.')]), self.e.research_quality_context())
        self.c.commit()
        before=copy.deepcopy(self.plan())
        with self.assertRaisesRegex(ValueError, 'conflicts with the existing quality plan'):
            self.load()
        self.assertEqual(before, self.plan())
        self.assertEqual(self.e.rows_data(self.c, 'insights'), [])

    def test_existing_other_question_cannot_be_silently_replaced(self):
        self.quality().import_plan(self.c, dict(questions=[dict(id='old-question', question=self.p['questions'][0]['text'],
            application_ids=self.apps, selection_basis='Old stable ID.')]), self.e.research_quality_context())
        self.c.commit()
        with self.assertRaisesRegex(ValueError, 'conflicts with the existing quality plan'):
            self.load()
        self.assertEqual(self.plan()['questions'][0]['id'], 'old-question')

    def test_conflicting_mapping_is_rejected_atomically(self):
        p=copy.deepcopy(self.p)
        for f in p['insights']:f['research_question_ids']=['unrelated-question']
        with self.assertRaisesRegex(ValueError, 'research_question_ids'):
            self.load(p)
        self.assertEqual(self.e.rows_data(self.c, 'insights'), [])
        self.assertEqual(self.quality().records(self.c, 'research_plan'), [])

    def test_import_rollback_preserves_prior_workflow_even_if_caller_catches(self):
        self.load();before={table:self.e.rows_data(self.c,table) for table in ('insights','relations','events')}
        saved=copy.deepcopy(self.e.get_meta(self.c,'research_workflow'))
        p=copy.deepcopy(self.p);p['insights'][1]['body']='A conflicting factual account.'
        # Catch inside the caller's transaction. The module's own savepoint must
        # restore earlier inserts and events instead of relying on caller rollback.
        with self.c:
            try:self.module().import_workflow(self.c,self.e.research_context(),p)
            except ValueError:pass
            else:self.fail('Conflicting role facts unexpectedly imported')
        self.assertEqual(saved,self.e.get_meta(self.c,'research_workflow'))
        for table,rows in before.items():self.assertEqual(rows,self.e.rows_data(self.c,table))

    def test_partial_stays_unfinished_even_after_valid_quality_review(self):
        self.complete();self.load()
        self.assertEqual(self.quality().validate(self.c,self.e.research_quality_context())['errors'],[])
        self.assertEqual(self.codes(),{'research_workflow_unfinished'})
        self.f.assert_blocked_render()

    def test_pending_stays_unfinished(self):
        p=copy.deepcopy(self.p);p['questions'][0]['status']='pending'
        self.load(p);self.assertEqual(self.codes(),{'research_workflow_unfinished'})

    def test_answered_requires_the_reviewed_answer_not_just_passing_status(self):
        p=self.complete();p['questions'][0]['answer']='A different, unreviewed conclusion.'
        with self.assertRaisesRegex(ValueError, 'contradicts its reviewed answer'):
            self.load(p)
        self.assertEqual(self.codes(),set())

    def test_review_import_and_same_plan_import_do_not_expire_binding(self):
        self.complete();saved=self.e.get_meta(self.c,'research_workflow')['binding_sha256']
        quality=self.quality();ctx=self.e.research_quality_context()
        quality.import_plan(self.c,self.plan(),ctx)
        review=quality.records(self.c,'research_reviews')[0]
        quality.import_research(self.c,review,ctx)
        self.assertEqual(saved,self.module().binding(self.c,self.e.research_context(),self.e.get_meta(self.c,'research_workflow')))
        self.assertEqual(self.codes(),set())

    def test_analysis_semantics_change_invalidates_unchanged_source_workflow(self):
        self.complete()
        row=self.c.execute('SELECT * FROM analyses ORDER BY application_id LIMIT 1').fetchone()
        value=json.loads(row['data']);value['summary']['text']='Changed interpretation with the same original source.'
        self.c.execute('UPDATE analyses SET data=? WHERE application_id=?',(json.dumps(value),row['application_id']))
        self.assertEqual(self.codes(),{'research_workflow_invalid'})
        exported=self.module().export(self.c,self.e.research_context())
        self.assertEqual(exported['questions'][0]['status'],'partial')
        self.assertEqual(exported['questions'][0]['quality_review_status'],'stale')

    def test_plan_revision_invalidates_old_answer_review(self):
        self.complete();plan=self.plan();plan['questions'].append(dict(id='new-question',question='What remains untested?',application_ids=self.apps,selection_basis='Explicit extra synthetic question.'))
        plan.pop('plan_hash');plan['revision_reason']='Add a real unresolved question without hiding the old one.'
        self.quality().import_plan(self.c,plan,self.e.research_quality_context())
        self.assertEqual(self.codes(),{'research_workflow_invalid'})

    def test_review_marked_revise_cannot_support_answered(self):
        self.complete();quality=self.quality();review=quality.records(self.c,'research_reviews')[0]
        review['review_result']='revise';quality.import_research(self.c,review,self.e.research_quality_context())
        self.assertEqual(self.codes(),{'research_workflow_invalid'})
        self.assertEqual(self.module().export(self.c,self.e.research_context())['questions'][0]['status'],'partial')

    def test_export_does_not_display_answered_when_saved_answer_contradicts_review(self):
        self.complete();saved=self.e.get_meta(self.c,'research_workflow')
        saved['questions'][0]['answer']='An unreviewed claim of performance superiority.'
        self.e.set_meta(self.c,'research_workflow',saved)
        exported=self.module().export(self.c,self.e.research_context())
        self.assertEqual(exported['questions'][0]['status'],'partial')
        self.assertEqual(exported['questions'][0]['quality_review_status'],'answer_mismatch')

    def test_retired_findings_and_relations_can_be_reactivated_without_deleting_history(self):
        self.load();original_ids={f['id'] for f in self.e.active_insights(self.c)}
        replacement=copy.deepcopy(self.p);replacement['id']='replacement-workflow'
        replacement['relations'][0]['id']='replacement-relation'
        for finding in replacement['insights']:
            finding['id']='replacement-'+finding['id']
            finding['relation_ids']=['replacement-relation']
        self.load(replacement)
        self.assertFalse(original_ids & {f['id'] for f in self.e.active_insights(self.c)})
        self.load()
        self.assertEqual(original_ids,{f['id'] for f in self.e.active_insights(self.c)})
        self.assertEqual([r['id'] for r in self.e.active_relations(self.c)],['optics-parallel'])
        self.assertEqual(len(self.e.rows_data(self.c,'insights')),6)
        self.assertEqual(len(self.e.rows_data(self.c,'relations')),2)
        retired=self.e.get_meta(self.c,'research_retired')
        self.assertEqual(set(retired['insight_ids']),{f['id'] for f in replacement['insights']})
        self.assertEqual(retired['relation_ids'],['replacement-relation'])
        self.assertEqual(self.codes(),{'research_workflow_unfinished'})

    def test_old_workflow_without_plan_cannot_gain_completion_from_old_label(self):
        self.complete();self.c.execute('DELETE FROM research_plan');self.c.execute('DELETE FROM research_reviews')
        self.assertEqual(self.codes(),{'research_workflow_invalid'})
        with self.assertRaisesRegex(ValueError,'resolved/pass'):
            self.module().import_workflow(self.c,self.e.research_context(),self.module().export(self.c,self.e.research_context()) | {
                'questions':[dict(self.p['questions'][0],status='answered',remaining=[])]})
        self.load()
        self.assertEqual(self.codes(),{'research_workflow_unfinished'})
        self.assertEqual(self.quality().records(self.c,'research_reviews'),[])


if __name__=='__main__':unittest.main()
