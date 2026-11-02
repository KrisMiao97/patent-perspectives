"""Exception delivery behavior, using explicitly synthetic data only."""
import copy
import json
import test_integrity
from pathlib import Path
import unittest

class ExceptionDeliveryTests(unittest.TestCase):
    def setUp(self):
        self.f = test_integrity.IntegrityTests(methodName="test_missing_fulltext_never_completes_or_renders")
        self.f.setUp()
        self.addCleanup(self.f.doCleanups)
        self.e = test_integrity.engine
        self.ids = self.f.seed([self.f.record(1), self.f.record(2)])
        self.f.analyze(self.f.document(1))
        with self.f.db:
            self.e.import_insights(self.f.db,[self.f.insight(role,self.ids[0]) for role in self.e.ROLES])
        self.records = "# Synthetic test records\nsource-1 " + self.ids[1] + "\nMissing test source."
        self.context = {}
        self.contract = self.e.delivery_module().draft(self.f.db,self.e.delivery_context(),self.context,self.records)
        self.contract.update(reviewed_by_host=True,user_direction="Synthetic authorized exception test",
            report_scope_statement="One complete synthetic source and one recorded missing source.")
        self.contract["exceptions"][0].update(issue_id="source-1",reason="Synthetic source absent",
            effect_on_report="No technical conclusions for missing source",next_step="Acquire exact synthetic source")

    def run_render(self, name="report", **kw):
        values=dict(delivery_contract=self.contract,analysis_records=self.records,report_context=self.context)
        values.update(kw)
        return self.e.render(self.f.db,self.f.directory/name,**values)

    def test_approved_delivery_preserves_incomplete_run_and_pending_row(self):
        before=self.e.validate_run(self.f.db)
        result=self.run_render()
        self.assertEqual(result["status"],"reviewed_with_exceptions")
        self.assertEqual(self.e.validate_run(self.f.db),before)
        out=self.f.directory/"report"
        report=json.loads((out/"validation.json").read_text(encoding="utf-8"))
        self.assertEqual(report["status"],"incomplete")
        payload=json.loads((out/"data/bootstrap.js").read_text(encoding="utf-8")[len("window.PP_DATA="):-2])
        self.assertEqual(len(payload["patents"]),2)
        self.assertFalse(payload["run"]["full_run_completion_claimed"])
        pending=next(p for p in payload["patents"] if p["id"]==self.ids[1])
        self.assertEqual(pending["analysis_status"],"pending")
        self.assertTrue((out/"分析记录与后续补充说明.md").exists())
        with self.assertRaises(self.e.ValidationError):
            self.e.render(self.f.db,self.f.directory/"ordinary")

    def test_unreviewed_draft_is_rejected_without_partial_output(self):
        self.contract["reviewed_by_host"]=False
        with self.assertRaises(self.e.ValidationError):self.run_render()
        self.assertFalse((self.f.directory/"report").exists())

    def test_context_and_notes_changes_require_review(self):
        for name,kw in [("context",{"report_context":{"analysis_label":"Changed"}}),
                        ("notes",{"analysis_records":self.records+"Changed"})]:
            with self.assertRaises(self.e.ValidationError):self.run_render(name,**kw)
            self.assertFalse((self.f.directory/name).exists())

    def test_source_change_is_detected_even_when_counts_unchanged(self):
        row=self.f.db.execute("SELECT data FROM applications WHERE id=?",(self.ids[1],)).fetchone()
        data=json.loads(row[0]);data["title"]="Changed synthetic title"
        with self.f.db:self.f.db.execute("UPDATE applications SET data=? WHERE id=?",(json.dumps(data),self.ids[1]))
        with self.assertRaises(self.e.ValidationError):self.run_render()

    def test_additional_error_cannot_be_covered_by_existing_inventory(self):
        with self.f.db:self.f.db.execute("DELETE FROM insights WHERE id=?",("synthetic-insight-ip",))
        with self.assertRaises(self.e.ValidationError):self.run_render()

    def test_invented_or_omitted_exception_is_rejected(self):
        self.contract["exceptions"]=[]
        with self.assertRaises(self.e.ValidationError):self.run_render()

    def test_real_exception_delivery_never_uses_preview(self):
        with self.assertRaises(self.e.ValidationError):self.run_render(preview=True)

    def test_cli_uses_readonly_source_and_preserves_database_bytes(self):
        self.f.db.commit()
        ctx=self.f.directory/"context.json";ctx.write_text("{}",encoding="utf-8")
        notes=self.f.directory/"notes.md";notes.write_text(self.records,encoding="utf-8")
        con=self.f.directory/"contract.json";con.write_text(json.dumps(self.contract),encoding="utf-8")
        before=self.e.delivery_module().database_digest(self.f.db)
        result,code=self.e.cli(["--db",str(self.f.dbpath),"render","--output",str(self.f.directory/"cli"),
            "--report-context",str(ctx),"--delivery-contract",str(con),"--analysis-records",str(notes)])
        self.assertEqual(code,0)
        self.assertEqual(result["status"],"reviewed_with_exceptions")
        self.assertEqual(self.e.delivery_module().database_digest(self.f.db),before)

if __name__=="__main__":unittest.main()
