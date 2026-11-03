import importlib.util, json, tempfile, unittest
from pathlib import Path
import test_render_delivery
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('industry_exports_test',ROOT/'scripts/industry_exports.py');exports=importlib.util.module_from_spec(spec);spec.loader.exec_module(exports)
class IndustryExportTests(test_render_delivery.RenderDeliveryTests):
    def context(self):
        run=self.engine.run_info(self.fixture.db)
        return {'industry_research':{'target_company_id':'target','scope':{'topic':'合成流程检查','as_of':run['as_of_date'],'selection_basis':'仅用于测试'},'companies':[{'id':'target','name':run['company'],'role':'合成目标'}],'sources':[],'tasks':[{'id':'task','kind':'profile','question':'合成问题','answer':'资料尚不足','conditions':'仅合成测试','status':'unknown','reason':'等待证据','source_ids':[]}],'routes':[],'matrix':[],'jurisdiction_cases':[]}}
    def test_integrated_exports_and_assets(self):
        out=self.fixture.directory/'industry'
        self.engine.render(self.fixture.db,out,report_context=self.context())
        for name in ['industry-research.js','industry-research.css','data/industry-research.js','industry-research.json','industry-research.md','industry-sources.csv','industry-matrix.csv']:
            self.assertTrue((out/name).is_file(),name)
        data=json.loads((out/'industry-research.json').read_text(encoding='utf-8'))
        self.assertEqual(data['tasks'][0]['status'],'unknown')
        self.assertIn('资料尚不足',(out/'industry-research.md').read_text(encoding='utf-8'))
    def test_bad_industry_does_not_publish(self):
        ctx=self.context();ctx['industry_research']['tasks'][0]['status']='supported'
        out=self.fixture.directory/'bad-industry'
        with self.assertRaises(self.engine.ValidationError):self.engine.render(self.fixture.db,out,report_context=ctx)
        self.assertFalse(out.exists())
    def test_missing_local_material_blocks_delivery(self):
        ctx=self.context();ctx['industry_research']['sources']=[{'id':'s','kind':'O','title':'合成文件','locator':'测试段落','observed_at':ctx['industry_research']['scope']['as_of'],'local_path':'industry-materials/missing.txt'}]
        out=self.fixture.directory/'missing-local'
        with self.assertRaises(self.engine.ValidationError):self.engine.render(self.fixture.db,out,report_context=ctx)
        self.assertFalse(out.exists())
    def test_material_copy_and_escape(self):
        with tempfile.TemporaryDirectory() as temp:
            base=Path(temp);src=base/'input';out=base/'report';out.mkdir();(src/'industry-materials').mkdir(parents=True)
            (src/'industry-materials/a.txt').write_text('Synthetic original',encoding='utf-8')
            exports.package_materials(out,{'sources':[{'local_path':'industry-materials/a.txt'}]},src)
            self.assertEqual((out/'industry-materials/a.txt').read_text(),'Synthetic original')
            with self.assertRaises(ValueError):exports.package_materials(out,{'sources':[{'local_path':'../escape.txt'}]},src)
            with self.assertRaises(ValueError):exports.package_materials(out,{'sources':[{'local_path':'industry-materials/script.html'}]},src)
    def test_reference_corpus_preserved(self):
        import test_industry_research
        payload, details, ctx = test_industry_research.make_fixture()
        prepared = test_industry_research.industry.prepare(payload, details, ctx)
        corpus = [{'id':'reference','payload':payload,'details':details}]
        with tempfile.TemporaryDirectory() as temp:
            exports.emit(temp,prepared,corpus)
            saved=json.loads((Path(temp)/'industry-reference-corpora.json').read_text(encoding='utf-8'))
            self.assertEqual(saved,corpus)
    def test_csv_formula_neutralized(self):
        self.assertEqual(exports.csv_cell('=1+1'),"'=1+1")
        self.assertEqual(exports.csv_cell('  @cmd'),"'  @cmd")
if __name__=='__main__':unittest.main()
