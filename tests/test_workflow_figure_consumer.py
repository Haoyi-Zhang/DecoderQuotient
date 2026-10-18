"""Regression tests for source-level workflow-figure consumption, not PDF freshness."""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from tools.package_check import check_workflow_figure_consumer


class WorkflowFigureConsumerTests(unittest.TestCase):
    def check(self,text):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            (root/'main.tex').write_text(text,encoding='utf-8')
            check_workflow_figure_consumer(root)

    def test_width_option_is_a_real_consumer(self):
        self.check(r'\includegraphics[width=\linewidth]{figures/workflow-cost.pdf}')

    def test_unsized_consumer_remains_valid(self):
        self.check(r'\includegraphics{figures/workflow-cost.pdf}')

    def test_comment_is_not_a_consumer(self):
        with self.assertRaisesRegex(ValueError,'consume complete-workflow'):
            self.check('% '+r'\includegraphics[width=\linewidth]{figures/workflow-cost.pdf}')

    def test_wrong_asset_is_rejected(self):
        with self.assertRaisesRegex(ValueError,'consume complete-workflow'):
            self.check(r'\includegraphics[width=\linewidth]{figures/different-cost.pdf}')


if __name__=='__main__':
    unittest.main()
