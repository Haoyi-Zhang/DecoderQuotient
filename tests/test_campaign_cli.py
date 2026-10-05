"""Continuing-ledger controls for the campaign command entry point."""
import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from bptc.publication_budget import ObligationLedger
from bptc.publication_campaign import main


class CampaignCliTests(unittest.TestCase):
    def test_existing_ledger_is_preserved_across_commands(self):
        def bounded_campaign(root, out, ledger, run_label):
            out.mkdir(parents=True)
            ledger.charge("cli-control", 2)
            return {
                "accumulator": {"cases": 0},
                "decoder": {"cases": 0},
                "resource_usage": {},
            }

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            ledger_path = root / "budget.json"
            ObligationLedger(20, 3, {"prior": 3}).write(ledger_path)
            for index, label in enumerate(("main", "reproduction")):
                out = root / label
                argv = ["campaign", "--root", str(root), "--out", str(out),
                        "--label", label, "--ledger", str(ledger_path),
                        "--limit", "20"]
                with patch("sys.argv", argv), \
                     patch("bptc.publication_campaign.resource.setrlimit"), \
                     patch("bptc.publication_campaign.run_once", side_effect=bounded_campaign), \
                     contextlib.redirect_stdout(io.StringIO()):
                    self.assertEqual(main(), 0)
                accounting = json.loads((out / "run-accounting.json").read_text())
                current = json.loads(ledger_path.read_text())
                self.assertEqual(accounting["events_before"], 3 + 2 * index)
                self.assertEqual(accounting["events_after"], 5 + 2 * index)
                self.assertEqual(accounting["events_this_run"], 2)
                self.assertEqual(current["events_used"], 5 + 2 * index)
                self.assertEqual(current["categories"], {"prior": 3, "cli-control": 2 * (index + 1)})

    def test_ambiguous_or_nonfinite_existing_ledger_is_rejected(self):
        sources = (
            '{"limit":20,"events_used":3,"events_used":0,"categories":{"prior":3}}',
            '{"limit":20,"events_used":NaN,"categories":{"prior":3}}',
        )
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            ledger_path = root / "budget.json"
            for source in sources:
                ledger_path.write_text(source)
                argv = ["campaign", "--out", str(root / "unused"),
                        "--label", "main", "--ledger", str(ledger_path),
                        "--limit", "20"]
                with patch("sys.argv", argv), \
                     patch("bptc.publication_campaign.run_once") as runner, \
                     patch("bptc.publication_campaign.resource.setrlimit") as limits:
                    with self.assertRaises(ValueError):
                        main()
                    runner.assert_not_called()
                    limits.assert_not_called()
                self.assertEqual(ledger_path.read_text(), source)
                self.assertFalse((root / "unused").exists())
