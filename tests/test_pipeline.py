"""Narrow controls for the actual reproduction interface, not a TeX build."""
from pathlib import Path
import tempfile
import unittest

from tools.package_check import project_paths, check_tex_inputs
from tools.run_tests import regression_suite


class PipelineTests(unittest.TestCase):
    def test_project_paths_allow_root_readme(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "artifact").mkdir()
            (root / "paper").mkdir()
            (root / "README.md").write_text("Usage")
            artifact, paper = project_paths(root)
            self.assertEqual(artifact, root / "artifact")
            self.assertEqual(paper, root / "paper")

    def test_extensionless_and_explicit_tex_inputs(self):
        with tempfile.TemporaryDirectory() as td:
            paper = Path(td)
            (paper / "main.tex").write_text(r"\input{a}\input{b.tex}")
            (paper / "a.tex").write_text("a")
            (paper / "b.tex").write_text("b")
            check_tex_inputs(paper, "main")
            (paper / "b.tex").unlink()
            with self.assertRaisesRegex(ValueError, "missing TeX include b.tex"):
                check_tex_inputs(paper, "main")

    def test_runner_includes_continuing_ledger_controls(self):
        def identifiers(suite):
            for item in suite:
                if isinstance(item, unittest.TestSuite):
                    yield from identifiers(item)
                else:
                    yield item.id()
        cases = set(identifiers(regression_suite()))
        self.assertIn("tests.test_campaign_cli.CampaignCliTests.test_existing_ledger_is_preserved_across_commands", cases)
        self.assertIn("tests.test_contracts.ReplayTests.test_minimality_product_merge", cases)
        self.assertTrue(any("test_pipeline.PipelineTests" in name for name in cases))
