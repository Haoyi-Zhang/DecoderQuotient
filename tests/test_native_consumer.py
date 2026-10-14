"""Owned retained arithmetic packets: consumer checks must survive python -O.

SPDX-License-Identifier: MIT. These are local evidence perturbations, not
third-party program executions or security certification.
"""
from copy import deepcopy
import gzip
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from native import bridge
from bptc.publication_budget import ObligationLedger

ROOT = Path(__file__).resolve().parents[1]


class NativeConsumerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.packet = json.loads(gzip.decompress(
            (ROOT/'results/native-cpu/native-conformance.json.gz').read_bytes()))
        cls.panel = bridge.panel()

    def test_complete_native_packet(self):
        result = bridge.compare(self.packet, self.panel, ObligationLedger(100000))
        self.assertEqual(result['accumulator_cases'], 79)
        self.assertEqual(result['disagreements'], 0)

    def test_wrong_transport_identity(self):
        for field, value in [('format', 'wrong'), ('performance_measured', True)]:
            changed = deepcopy(self.packet)
            changed[field] = value
            with self.subTest(field=field), self.assertRaises((ValueError, AssertionError)):
                bridge.compare(changed, self.panel, ObligationLedger(100000))

    def test_baseline_decision_edges_and_counts(self):
        for kind in ('decision', 'edge', 'count', 'name', 'state'):
            changed = deepcopy(self.packet)
            entry = changed['accumulators'][0]
            if kind == 'decision': entry['baseline_decision']['equivalent'] = False
            if kind == 'edge': entry['baseline_layers'][1]['edges'][0]['to'][1] += 1
            if kind == 'count': entry['baseline_edges'] += 1
            if kind == 'name': entry['name'] += '-wrong'
            if kind == 'state': entry['baseline_layers'][0]['states'][0]['state'][0] += 1
            with self.subTest(kind=kind), self.assertRaises((ValueError, AssertionError)):
                bridge.compare(changed, self.panel, ObligationLedger(100000))

    def test_native_concrete_accumulator_trace(self):
        changed = deepcopy(self.packet)
        changed['accumulators'][0]['concrete']['traces'][0]['steps'][0]['lowered'] += 1
        with self.assertRaises((ValueError, AssertionError)):
            bridge.compare(changed, self.panel, ObligationLedger(100000))

    def test_native_decoder_trace_and_verdict(self):
        for kind in ('trace', 'decision'):
            changed = deepcopy(self.packet)
            entry = changed['decoders'][0]
            if kind == 'trace': entry['traces'][0]['packed_output'] += 1
            else: entry['equivalent'] = not entry['equivalent']
            with self.subTest(kind=kind), self.assertRaises((ValueError, AssertionError)):
                bridge.compare(changed, self.panel, ObligationLedger(100000))

    def test_strict_boolean_and_integer_identity(self):
        changed = deepcopy(self.packet)
        changed['accumulators'][0]['baseline_layers'][0]['states'][0]['state'][2] = 0
        with self.assertRaises((ValueError, AssertionError)):
            bridge.compare(changed, self.panel, ObligationLedger(100000))

    def test_retained_analysis_requires_complete_valid_measurements(self):
        from native import report
        original_load = report.load
        for control in ('checker-status','comparison','batch'):
            def changed_load(path):
                value = deepcopy(original_load(path))
                if control == 'checker-status' and path.name == 'checker-samples.json':
                    value['status'] = 'incomplete'
                if control == 'comparison' and path.name == 'comparison.json':
                    value['disagreements'] = 1
                if control == 'batch' and path.name == 'raw-samples.json':
                    value['samples'][0]['batch'] = 15
                return value
            with self.subTest(control=control), patch.object(report,'load',side_effect=changed_load):
                with self.assertRaises((ValueError, AssertionError)):
                    report.analyze(ROOT/'results/native-cpu')


if __name__ == '__main__':
    unittest.main()
