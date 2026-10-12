"""Focused current-figure controls; no benchmark, TeX build or source mutation."""
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from tools.package_check import check_edge_figure

PROJECT=Path(__file__).resolve().parents[2]


class PackageFigureTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root=Path(self.temp.name)
        self.paper=root/'paper'
        self.artifact=root/'artifact'
        for rel in ('paper/main.tex','paper/figures/edge-counts.tex',
                    'paper/figures/edge-counts.csv','paper/figures/edge-counts.pdf',
                    'paper/figures/draw_evaluation.py',
                    'paper/generated/publication_macros.tex',
                    'artifact/results/publication/main/summary.json'):
            target=root/rel
            target.parent.mkdir(parents=True,exist_ok=True)
            shutil.copy2(PROJECT/rel,target)

    def replace(self,rel,old,new):
        path=self.paper/rel
        text=path.read_text()
        self.assertIn(old,text)
        path.write_text(text.replace(old,new),encoding='utf-8')

    def check(self):
        return check_edge_figure(self.paper,self.artifact)

    def test_current_includegraphics_and_real_geometry_pass(self):
        self.assertNotIn('ymin=0',(self.paper/'figures/edge-counts.tex').read_text())
        self.assertEqual(self.check()['counts'],[1016,416])
        self.assertEqual(self.check()['bars_checked'],2)

    def test_nonzero_axis_is_rejected(self):
        self.replace('figures/draw_evaluation.py','"ylim": [\n      0,','"ylim": [\n      100,')
        with self.assertRaisesRegex(ValueError,'start at zero'):self.check()

    def test_log_axis_is_rejected(self):
        self.replace('figures/draw_evaluation.py','"xgrid": False,','"xgrid": False, "ylog": True,')
        with self.assertRaisesRegex(ValueError,'linear axes'):self.check()

    def test_changed_actual_bar_baseline_is_rejected(self):
        self.replace('figures/draw_evaluation.py','if self.cfg.get("ylog") else 0',
                     'if self.cfg.get("ylog") else 100')
        with self.assertRaisesRegex(ValueError,'rendered bar geometry'):self.check()

    def test_changed_actual_coordinate_mapping_is_rejected(self):
        self.replace('figures/draw_evaluation.py','return (v - bounds[0]) /',
                     'return (v - bounds[0] + 100) /')
        with self.assertRaisesRegex(ValueError,'rendered bar geometry'):self.check()

    def test_nonfinite_axis_is_rejected(self):
        self.replace('figures/draw_evaluation.py','"ylim": [\n      0,\n      1200',
                     '"ylim": [\n      0,\n      float("inf")')
        with self.assertRaisesRegex(ValueError,'finite axis bounds'):self.check()

    def test_zero_height_plot_box_is_rejected(self):
        self.replace('figures/draw_evaluation.py','383.5,\n      77.1','383.5,\n      0')
        with self.assertRaisesRegex(ValueError,'plot box dimensions'):self.check()

    def test_changed_csv_snapshot_is_rejected(self):
        self.replace('figures/edge-counts.csv','Unquotiented,1016','Unquotiented,1015')
        with self.assertRaisesRegex(ValueError,'Retained CSV changed'):self.check()

    def test_cochanged_csv_and_snapshot_still_bind_evidence(self):
        for rel in ('figures/edge-counts.csv','figures/draw_evaluation.py'):
            self.replace(rel,'Unquotiented,1016','Unquotiented,1015')
        with self.assertRaisesRegex(ValueError,'retained evidence'):self.check()

    def test_wrong_series_binding_is_rejected(self):
        self.replace('figures/draw_evaluation.py','"y": "frontier_edges"','"y": "representation"')
        with self.assertRaisesRegex(ValueError,'retained CSV columns'):self.check()

    def test_macro_drift_is_rejected(self):
        self.replace('generated/publication_macros.tex',r'\PubQuotientEdges}{416}',r'\PubQuotientEdges}{417}')
        with self.assertRaisesRegex(ValueError,'macros differ'):self.check()

    def test_changed_summary_is_rejected(self):
        path=self.artifact/'results/publication/main/summary.json'
        data=json.loads(path.read_text())
        data['accumulator']['quotient_frontier_edges']=417
        path.write_text(json.dumps(data),encoding='utf-8')
        with self.assertRaisesRegex(ValueError,'retained evidence'):self.check()

    def test_axis_clipping_is_rejected(self):
        self.replace('figures/draw_evaluation.py','"ylim": [\n      0,\n      1200',
                     '"ylim": [\n      0,\n      1000')
        with self.assertRaisesRegex(ValueError,'clips'):self.check()

    def test_wrong_consumed_pdf_is_rejected_even_with_old_token(self):
        self.replace('figures/edge-counts.tex','edge-counts.pdf','other.pdf')
        with (self.paper/'figures/edge-counts.tex').open('a') as stream:
            stream.write('% ymin=0\n')
        with self.assertRaisesRegex(ValueError,'consume the checked PDF'):self.check()

    def test_missing_pdf_is_rejected(self):
        (self.paper/'figures/edge-counts.pdf').unlink()
        with self.assertRaisesRegex(ValueError,'missing/invalid'):self.check()


if __name__=='__main__':
    unittest.main(verbosity=2)
