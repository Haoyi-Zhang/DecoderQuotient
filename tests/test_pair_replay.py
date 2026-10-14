"""Identity-partition consumer, same semantic guarantees as product replay.

SPDX-License-Identifier: MIT. Bounded literal prefixes, no compiler/network.
"""
from copy import deepcopy
import unittest
from bptc.accumulator_checker import check_certificate, check_pair_certificate
from bptc.exact_accumulator import spec_to_dict
from bptc.publication_budget import ObligationLedger
from bptc.publication_cases import accumulator_specs
from tests.hoisting_regression import literal_certificate, execute_word, finite_specs


def identity_packet(spec):
    packet = literal_certificate(spec)
    packet['format'] = 'bptc-pair-accumulator-certificate-v1'
    packet['product_classes'] = [
        [dict(product=a*b, representative_index=j, representative_pair=[a,b],
              member_indices=[j], member_pairs=[[a,b]])
         for j,(a,b) in enumerate(stage['pairs'])] for stage in spec['stages']]
    transitions = 0
    for i, stage in enumerate(spec['stages']):
        edges = []
        for row in packet['layers'][i]['states']:
            for j,(a,b) in enumerate(stage['pairs']):
                word = tuple(row['least_witness_indices'])+(j,)
                edges.append({'from':row['state'], 'product':a*b, 'representative_index':j,
                              'to':list(execute_word(spec, word))})
        packet['layers'][i+1]['edges'] = edges
        transitions += len(edges)
    packet['metrics'].update(quotient_product_sequences=packet['metrics']['concrete_assignments'],
                           producer_transitions=transitions, quotient_frontier_edges=transitions)
    return packet


class PairReplayTests(unittest.TestCase):
    def test_workflow_plot_csv_has_canonical_lf_bytes(self):
        from pathlib import Path
        from native.workflow_report import inputs
        root=Path(__file__).resolve().parents[1]
        _,_,csv_text=inputs(root/'results/workflow-cost')
        self.assertNotIn('\r',csv_text)
        self.assertEqual(len(csv_text.splitlines()),80)

    def test_all_original_and_literal_boundary_schedules(self):
        for spec in [spec_to_dict(s) for s in accumulator_specs()]+list(finite_specs()):
            with self.subTest(name=spec['name'], initial=spec['initial']):
                baseline = identity_packet(spec)
                verdict = check_pair_certificate(baseline, ObligationLedger(200000))
                quotient = literal_certificate(spec)
                qverdict = check_certificate(quotient, ObligationLedger(200000))
                self.assertEqual(verdict['equivalent'], qverdict['equivalent'])
                self.assertEqual(baseline['decision'], quotient['decision'])
                self.assertEqual([l['states'] for l in baseline['layers']],
                                 [l['states'] for l in quotient['layers']])

    def test_consumers_do_not_admit_each_others_partition(self):
        spec = spec_to_dict(accumulator_specs()[0])
        with self.assertRaises(ValueError):
            check_certificate(identity_packet(spec), ObligationLedger(200000))
        with self.assertRaises(ValueError):
            check_pair_certificate(literal_certificate(spec), ObligationLedger(200000))

    def test_complete_baseline_fields_and_edge_multiplicity(self):
        base = identity_packet(spec_to_dict(accumulator_specs()[0]))
        for kind in ('edge','member','witness','metric','boolean','decision','format'):
            changed = deepcopy(base)
            if kind == 'edge': changed['layers'][1]['edges'].pop()
            if kind == 'member': changed['product_classes'][0][0]['member_indices'].append(1)
            if kind == 'witness': changed['layers'][1]['states'][0]['least_witness_indices'][0] = 1
            if kind == 'metric': changed['metrics']['producer_transitions'] += 1
            if kind == 'boolean': changed['layers'][0]['states'][0]['state'][2] = 0
            if kind == 'decision': changed['decision']['equivalent'] = False
            if kind == 'format': changed['format'] = 'unknown'
            with self.subTest(kind=kind), self.assertRaises(ValueError):
                check_pair_certificate(changed, ObligationLedger(200000))


if __name__ == '__main__':
    unittest.main()
