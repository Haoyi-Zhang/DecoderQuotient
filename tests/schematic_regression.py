"""Schematic geometry, reproducibility and real consumer regressions."""
from pathlib import Path
import importlib.util
import sys
import tempfile
import unittest
from unittest.mock import patch
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.schematic_assets import NAMES, check_schematics
spec = importlib.util.spec_from_file_location('draw_schematics', ROOT/'figures/draw_schematics.py')
draw = importlib.util.module_from_spec(spec)
spec.loader.exec_module(draw)
class SchematicTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name)
    def fixture(self):
        paper, artifact = self.path/'paper', self.path/'artifact'
        (paper/'figures').mkdir(parents=True)
        (artifact/'figures').mkdir(parents=True)
        (artifact/'figures/draw_schematics.py').write_text('# fixture\n')
        for name in NAMES:
            (artifact/'figures'/(name+'.pdf')).write_bytes(b'%PDF-1.4\n')
            (paper/'figures'/(name+'.tex')).write_text(r'\includegraphics{../artifact/figures/'+name+'.pdf}')
        return paper, artifact
    def test_layout_relations_and_reproduction(self):
        edges, current = [], []
        edge, save = draw.Drawing.edge, draw.Drawing.save
        def record_edge(obj, a, b, *args, **kwargs):
            current.append((a, b)); return edge(obj, a, b, *args, **kwargs)
        def record_save(obj, output, name):
            edges.append((name, list(current))); current.clear()
            return save(obj, output, name)
        with patch.object(draw.Drawing, 'edge', record_edge), patch.object(draw.Drawing, 'save', record_save):
            draw.draw_all(self.path/'first')
        self.assertEqual(edges[0][1], [('src','imp'),('imp','dec'),('sch','acc'),('dec','chk'),('acc','chk'),('chk','claim')])
        self.assertEqual(edges[1][1], [('r0','p'),('r0','r1'),('p','r1')])
        draw.draw_all(self.path/'second')
        for name in NAMES:
            self.assertEqual((self.path/'first'/(name+'.pdf')).read_bytes(), (self.path/'second'/(name+'.pdf')).read_bytes())
    def test_valid_consumers(self):
        self.assertEqual(check_schematics(*self.fixture())['consumer_paths_checked'], 2)
    def test_missing_asset_rejected(self):
        paper, artifact = self.fixture()
        (artifact/'figures/evidence-flow.pdf').unlink()
        with self.assertRaisesRegex(ValueError, 'Missing or invalid'):
            check_schematics(paper, artifact)
    def test_wrong_consumer_rejected(self):
        paper, artifact = self.fixture()
        (paper/'figures/evidence-flow.tex').write_text(r'\includegraphics{old.pdf}')
        with self.assertRaisesRegex(ValueError, 'consume the generated'):
            check_schematics(paper, artifact)
if __name__ == '__main__':
    unittest.main(verbosity=2)
