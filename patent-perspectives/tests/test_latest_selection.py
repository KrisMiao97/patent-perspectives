"""Synthetic latest-N ranking, immutable membership and full-backup regressions."""
import copy
from contextlib import closing
from contextlib import redirect_stdout
import io
import json
import sqlite3
import sys
import unittest
from unittest.mock import patch
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import derive_latest
import derive_scope
import test_integrity as fixtures
import test_temporal_scope as temporal_fixtures
import test_registration_members as registration_fixtures
engine=fixtures.engine
WINDOW={'basis':'filing_date','from':'2021-10-21','through':'2026-10-20'}


class LatestSelectionTests(unittest.TestCase):
    setUp=fixtures.IntegrityTests.setUp
    record=fixtures.IntegrityTests.record
    search=fixtures.IntegrityTests.search
    seed=fixtures.IntegrityTests.seed
    doc_input=fixtures.IntegrityTests.doc_input
    document=fixtures.IntegrityTests.document
    analysis_input=fixtures.IntegrityTests.analysis_input
    analyze=fixtures.IntegrityTests.analyze
    insight=fixtures.IntegrityTests.insight
    change_dates=temporal_fixtures.TemporalScopeTests.change_dates

    def pool(self):
        records=[self.record(1,filing_date='2026-10-10'),self.record(2,filing_date='2026-10-10'),
                 self.record(3,filing_date='2025-01-01'),self.record(4,filing_date='2026-10-20',patent_type='design'),
                 self.record(5,filing_date='2026-09-01',patent_type='utility_model'),
                 self.record(6,filing_date='2020-01-01')]
        self.ids=self.seed(records)
        run=engine.run_info(self.db);run['scope']['analysis_window']=copy.deepcopy(WINDOW)
        with self.db:engine.set_meta(self.db,'run',run)
        return records

    def child(self,n=2):
        self.db.commit();path=self.directory/'latest.sqlite'
        result=derive_latest.derive(self.dbpath,path,n,engine=engine)
        return path,result

    def test_complete_pool_rank_tie_design_exclusion_and_cross_document_dedup(self):
        records=self.pool()
        # Add a B publication of the same filing; it is still one ranking slot.
        pn={**records[0],'pn':'CN900000001B'}
        self.search([pn],qid='synthetic-extra-publication')
        with self.db:engine.complete_query(self.db,'synthetic-extra-publication')
        plan=derive_latest.inspect(self.db,2,engine)
        self.assertEqual(plan['selected_application_ids'],self.ids[:2])
        self.assertEqual(plan['candidate_count'],4)
        self.assertEqual(len(plan['candidate_snapshot']['ranked_candidates'][0]['publication_ids']),2)
        self.assertEqual(plan['boundary_tie']['candidate_count_on_day'],2)
        self.assertEqual(plan['boundary_tie']['selected_count_on_day'],2)
        self.assertEqual(plan['publication_cutoff'],'2026-10-20')
        self.assertEqual(derive_latest.inspect(self.db,1,engine)['boundary_tie']['first_excluded_application_id'],self.ids[1])

    def test_any_eligible_missing_invalid_or_conflicting_date_prevents_ranking(self):
        self.pool()
        # Even an older candidate outside the selected top 2 cannot be skipped.
        self.change_dates(self.ids[2],None,None)
        with self.assertRaises(engine.ValidationError):derive_latest.inspect(self.db,2,engine)
        self.change_dates(self.ids[2],'2025-01-01','2025-01-02')
        with self.assertRaises(engine.ValidationError):derive_latest.inspect(self.db,2,engine)
        self.change_dates(self.ids[2],'2025-01-01','2025-01-01','2025-99-99')
        with self.assertRaises(engine.ValidationError):derive_latest.inspect(self.db,2,engine)

    def test_unknown_type_pending_identity_and_insufficient_n_are_not_silently_skipped(self):
        self.pool()
        for n in (0,-1,True,5):
            with self.assertRaises(engine.ValidationError):derive_latest.inspect(self.db,n,engine)
        app=json.loads(self.db.execute('SELECT data FROM applications WHERE id=?',(self.ids[2],)).fetchone()[0])
        app['patent_type']='unknown'
        with self.db:self.db.execute('UPDATE applications SET data=? WHERE id=?',(engine.dump(app),self.ids[2]))
        with self.assertRaises(engine.ValidationError):derive_latest.inspect(self.db,2,engine)
        app['patent_type']='invention'
        with self.db:
            self.db.execute('UPDATE applications SET data=? WHERE id=?',(engine.dump(app),self.ids[2]))
            self.db.execute('INSERT INTO population_reviews VALUES(?,?)',(self.ids[2],engine.dump({'status':'pending','candidate_snapshot_hash':engine.application_scope_snapshot(self.db,self.ids[2])})))
        with self.assertRaises(engine.ValidationError):derive_latest.inspect(self.db,2,engine)

    def test_backup_keeps_every_parent_row_and_child_denominator_is_selected_n(self):
        self.pool();before_run=copy.deepcopy(engine.run_info(self.db))
        before={t:[tuple(r) for r in self.db.execute('SELECT * FROM '+t)] for t in ('queries','pages','applications','publications','query_results','analyses','documents','population_reviews')}
        path,result=self.child()
        self.assertEqual(engine.run_info(self.db),before_run)
        for t,rows in before.items():self.assertEqual([tuple(r) for r in self.db.execute('SELECT * FROM '+t)],rows)
        self.assertFalse(self.db.execute("SELECT 1 FROM sqlite_master WHERE name='application_selections'").fetchone())
        with closing(derive_scope.open_readonly(path)) as c:
            for t,rows in before.items():self.assertEqual([tuple(r) for r in c.execute('SELECT * FROM '+t)],rows,t)
            self.assertEqual({a['id'] for a in engine.included_applications(c)},set(self.ids[:2]))
            cov=engine.coverage(c)
            self.assertEqual((cov['applications'],cov['technical_applications'],cov['design_applications']),(2,2,0))
            self.assertEqual(cov['candidate_applications'],6)
            self.assertEqual(cov['selection']['candidate_count'],4)
            self.assertEqual(cov['analysis_window']['selected_applications'],5)
            self.assertTrue(cov['analysis_window']['before_latest_selection'])
            self.assertEqual(engine.run_info(c)['parent_run_id'],before_run['run_id'])
            self.assertEqual(engine.run_info(c)['scope']['analysis_window'],WINDOW)
        self.assertFalse(result['parent_database_changed'])

    def test_analysis_reuse_does_not_choose_older_completed_or_shorter_documents(self):
        self.pool();d1=self.document(1);d3=self.document(3);self.analyze(d1);self.analyze(d3)
        with self.db:engine.import_insights(self.db,[self.insight(role,self.ids[0]) for role in engine.ROLES])
        old_hash=engine.population_hash(self.db);path,_=self.child()
        with closing(engine.db_open(path)) as c:
            self.assertNotEqual(old_hash,engine.population_hash(c))
            self.assertTrue(engine.analysis_is_current(c,c.execute('SELECT * FROM analyses WHERE application_id=?',(self.ids[0],)).fetchone()))
            self.assertEqual(engine.coverage(c)['technical_analyzed'],1)
            report=engine.validate_run(c)
            self.assertIn('missing_role_insights',{x['code'] for x in report['errors']})
            self.assertIn('historical_role_insights_retained',{x['code'] for x in report['warnings']})
            self.assertEqual(engine.active_insights(c),[])
            self.assertEqual([x['detail'] for x in report['errors'] if x['code']=='technical_analysis_missing'],[self.ids[1]])
            before=engine.latest_selection_module().validate(c,engine.latest_selection_context())['candidate_snapshot_hash']
            # New text and analysis evidence do not change the filing-date pool.
            doc=engine.import_document(c,self.doc_input(2));data=self.analysis_input(doc)
            engine.import_analysis(c,data);c.commit()
            self.assertEqual(engine.latest_selection_module().validate(c,engine.latest_selection_context())['candidate_snapshot_hash'],before)
            self.assertEqual(engine.coverage(c)['technical_completion'],100)
            fresh=[{**self.insight(role,self.ids[0]),'id':'new-selection-'+role,
                'scope':'Synthetic selected 2 technical applications only',
                'selection_scope':engine.insight_selection_scope(c)} for role in engine.ROLES]
            with c:engine.import_insights(c,fresh)
            self.assertEqual(c.execute('SELECT count(*) FROM insights').fetchone()[0],6)
            self.assertEqual(engine.validate_run(c)['status'],'complete')
            payload,_=engine.build_payload(c,engine.validate_run(c))
            self.assertEqual({x['id'] for x in payload['insights']},{x['id'] for x in fresh})
            self.assertNotIn('selected_application_ids',engine.dump(payload['run']))
            self.assertNotIn('candidate_snapshot',engine.dump(payload['run']))
        # Reopening is continuation of the same immutable selection.
        with closing(derive_scope.open_readonly(path)) as c:
            self.assertEqual(len(engine.included_applications(c)),2)
        with self.assertRaises(ValueError):derive_latest.derive(self.dbpath,path,2,engine=engine)

    def test_manifest_immutable_and_even_rehashed_arbitrary_membership_is_rejected(self):
        self.pool();path,_=self.child()
        with closing(engine.db_open(path)) as c:
            row=c.execute('SELECT * FROM application_selections').fetchone()
            with self.assertRaises(sqlite3.IntegrityError):c.execute('UPDATE application_selections SET data=? WHERE id=?',(row['data'],row['id']))
            with self.assertRaises(sqlite3.IntegrityError):c.execute('DELETE FROM application_selections')
            value=json.loads(row['data']);value['selected_application_ids']=[self.ids[2],self.ids[4]]
            value['manifest_id']='forged-membership'
            value['manifest_sha256']=engine.digest({k:v for k,v in value.items() if k!='manifest_sha256'})
            c.execute('INSERT INTO application_selections VALUES(?,?)',(value['manifest_id'],engine.dump(value)))
            run=engine.run_info(c);run['scope']['selection']=engine.latest_selection_module().public_summary(value)
            engine.set_meta(c,'run',run);c.commit()
            with self.assertRaises(engine.ValidationError):engine.included_applications(c)

    def test_changed_candidate_source_invalidates_frozen_selection_but_not_parent(self):
        self.pool();path,_=self.child()
        with closing(engine.db_open(path)) as c:
            row=c.execute('SELECT id,data FROM publications WHERE application_id=?',(self.ids[2],)).fetchone()
            value=json.loads(row['data']);value['filing_date']='2026-10-19'
            c.execute('UPDATE publications SET data=? WHERE id=?',(engine.dump(value),row['id']));c.commit()
            with self.assertRaises(engine.ValidationError):engine.coverage(c)
        self.assertEqual(derive_latest.inspect(self.db,2,engine)['selected_application_ids'],self.ids[:2])

    def test_role_scope_cannot_be_omitted_or_relabel_an_old_selection(self):
        self.pool();self.analyze(self.document(1));path,_=self.child()
        with closing(engine.db_open(path)) as c:
            old=self.insight('management',self.ids[0])
            with self.assertRaises(engine.ValidationError):engine.import_insights(c,[old])
            wrong={**old,'selection_scope':{**engine.insight_selection_scope(c),'count':3000}}
            with self.assertRaises(engine.ValidationError):engine.import_insights(c,[wrong])
            fresh={**old,'selection_scope':engine.insight_selection_scope(c)}
            engine.import_insights(c,[fresh]);c.commit()
            self.assertEqual(len(engine.active_insights(c)),1)
            errors=engine.validate_run(c)['errors']
            self.assertEqual({x['detail'] for x in errors if x['code']=='missing_role_insights'},{'rd','ip'})

    def test_incomplete_queries_and_hand_filled_public_selection_do_not_freeze(self):
        self.pool()
        with self.db:self.db.execute('UPDATE queries SET complete=0 WHERE id=?',('synthetic-original',))
        with self.assertRaises(engine.ValidationError):derive_latest.inspect(self.db,2,engine)
        with self.db:
            self.db.execute('UPDATE queries SET complete=1 WHERE id=?',('synthetic-original',))
            run=engine.run_info(self.db);run['scope']['selection']={'kind':'latest_technical_applications','count':2,
                'selected_application_ids':self.ids[:2]};engine.set_meta(self.db,'run',run)
        with self.assertRaises(engine.ValidationError):engine.included_applications(self.db)

    def test_new_selection_from_existing_child_uses_retained_full_pool(self):
        self.pool();path,_=self.child(1)
        nextpath=self.directory/'latest-three.sqlite'
        derive_latest.derive(path,nextpath,3,engine=engine)
        with closing(derive_scope.open_readonly(nextpath)) as c:
            self.assertEqual(c.execute('SELECT count(*) FROM application_selections').fetchone()[0],2)
            value=engine.latest_selection_module().validate(c,engine.latest_selection_context())
            self.assertEqual(value['selected_application_ids'],[self.ids[0],self.ids[1],self.ids[4]])
            self.assertEqual(value['candidate_count'],4)
        with self.assertRaises(ValueError):derive_scope.derive(path,self.directory/'bad-window.sqlite',WINDOW,engine=engine)

    def test_real_cli_inspects_then_creates_exact_frozen_artifact_and_never_overwrites(self):
        self.pool();self.db.commit();report=self.directory/'inspection'
        args=['derive_latest.py','--parent',str(self.dbpath),'--count','2','--report-dir',str(report)]
        with patch.object(sys,'argv',args),redirect_stdout(io.StringIO()) as out:derive_latest.main()
        self.assertTrue(json.loads(out.getvalue())['inspection_only'])
        self.assertFalse((report/'selection-manifest.private.json').exists())
        child=self.directory/'child-cli.sqlite'
        with patch.object(sys,'argv',args+['--create','--output',str(child)]),redirect_stdout(io.StringIO()):derive_latest.main()
        value=json.loads((report/'selection-manifest.private.json').read_text(encoding='utf-8'))
        plan=json.loads((report/'selection-plan.private.json').read_text(encoding='utf-8'))
        self.assertEqual(value['selected_application_ids'],self.ids[:2])
        self.assertEqual(plan['candidate_snapshot_hash'],value['candidate_snapshot_hash'])
        with self.assertRaises(ValueError):derive_latest.derive(self.dbpath,child,2,engine=engine)
        with self.assertRaises(ValueError):derive_latest.derive(self.dbpath,self.dbpath,2,engine=engine)
        with self.assertRaises(ValueError):derive_latest.derive(self.dbpath,self.directory/'different-dir'/'child.sqlite',2,engine=engine)

    def test_failed_derivation_leaves_no_partial_child_or_parent_change(self):
        self.pool();before=copy.deepcopy(engine.run_info(self.db));self.db.commit()
        child=self.directory/'insufficient.sqlite'
        with self.assertRaises(engine.ValidationError):derive_latest.derive(self.dbpath,child,5,engine=engine)
        self.assertFalse(child.exists());self.assertFalse(list(self.directory.glob('*.deriving-*')))
        self.assertEqual(engine.run_info(self.db),before)


class LatestRegistrationTests(unittest.TestCase):
    setUp=registration_fixtures.RegistrationMemberTests.setUp
    record=registration_fixtures.RegistrationMemberTests.record
    search=registration_fixtures.RegistrationMemberTests.search
    seed=registration_fixtures.RegistrationMemberTests.seed
    source=registration_fixtures.RegistrationMemberTests.source
    fixtures=registration_fixtures.RegistrationMemberTests.fixtures
    import_mapping=registration_fixtures.RegistrationMemberTests.import_mapping

    def test_national_member_follows_selected_canonical_without_consuming_a_slot(self):
        self.import_mapping(self.fixtures());self.db.commit()
        path=self.directory/'latest.sqlite';derive_latest.derive(self.dbpath,path,1,engine=engine)
        with closing(derive_scope.open_readonly(path)) as c:
            value=engine.latest_selection_module().validate(c,engine.latest_selection_context())
            self.assertEqual(value['candidate_count'],1)
            self.assertEqual(value['selected_application_ids'],[self.ep])
            self.assertEqual({a['id'] for a in engine.included_source_records(c)},{self.ep,self.de})
            self.assertEqual([a['id'] for a in engine.included_applications(c)],[self.ep])
            cov=engine.coverage(c)
            self.assertEqual(cov['technical_applications'],1)
            self.assertEqual(cov['raw_technical_application_records'],2)
            self.assertEqual(cov['registration_member_records'],1)
            self.assertEqual(cov['registration_count_bridge']['independent_technical_application_units'],1)

    def test_nonselected_canonical_member_stays_stored_but_does_not_enter_n(self):
        self.import_mapping(self.fixtures())
        record=self.record(3,filing_date='2026-10-01')
        self.search([record],qid='synthetic-newer-ordinary')
        with self.db:engine.complete_query(self.db,'synthetic-newer-ordinary')
        self.db.commit();path=self.directory/'latest.sqlite'
        derive_latest.derive(self.dbpath,path,1,engine=engine)
        with closing(derive_scope.open_readonly(path)) as c:
            self.assertEqual([a['application_number'] for a in engine.included_applications(c)],[record['apno']])
            self.assertEqual(len(engine.included_source_records(c)),1)
            self.assertEqual(c.execute('SELECT count(*) FROM registration_members').fetchone()[0],1)
            self.assertEqual(c.execute('SELECT count(*) FROM applications').fetchone()[0],3)


if __name__=='__main__':unittest.main()
