from __future__ import annotations

import copy
import unittest

from bptc.accumulator_checker import check_certificate
from bptc.accumulator_oracle import run_oracle
from bptc.exact_accumulator import generate_certificate
from bptc.packed_decoder import check_decoder_certificate, generate_decoder_certificate
from bptc.publication_budget import BudgetExceeded, ObligationLedger
from bptc.publication_cases import accumulator_specs, decoder_specs


class BudgetTests(unittest.TestCase):
    def test_fail_closed(self):
        ledger = ObligationLedger(2)
        ledger.charge("x", 2)
        before = ledger.to_dict()
        with self.assertRaises(BudgetExceeded):
            ledger.charge("x")
        self.assertEqual(before, ledger.to_dict())


class AccumulatorTests(unittest.TestCase):
    def test_three_way_agreement(self):
        for spec in accumulator_specs()[:8]:
            ledger = ObligationLedger(100000)
            certificate = generate_certificate(spec, ledger)
            checked = check_certificate(certificate, ledger)
            oracle = run_oracle(certificate["spec"], ledger)
            self.assertEqual(certificate["decision"]["equivalent"], checked["equivalent"])
            self.assertEqual(certificate["decision"]["equivalent"], oracle["equivalent"])

    def test_mutation_rejected(self):
        ledger = ObligationLedger(100000)
        certificate = generate_certificate(accumulator_specs()[0], ledger)
        mutant = copy.deepcopy(certificate)
        mutant["layers"][1]["edges"][0]["to"][1] += 1
        with self.assertRaises(ValueError):
            check_certificate(mutant, ledger)


class DecoderTests(unittest.TestCase):
    def test_closed_form_and_checker(self):
        for spec in decoder_specs():
            ledger = ObligationLedger(100000)
            certificate = generate_decoder_certificate(spec, ledger)
            checked = check_decoder_certificate(certificate, ledger)
            self.assertEqual(certificate["closed_form"]["equivalent"], checked["equivalent"])


if __name__ == "__main__":
    unittest.main()
