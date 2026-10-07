"""Finite literal-word reference, independent of both arithmetic implementations.

SPDX-License-Identifier: MIT. Run directly from any working directory. No timer,
compiler, historical implementation, private path, or campaign is used.
"""
from copy import deepcopy
from itertools import product
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from bptc.exact_accumulator import AccumulatorSpec, StageSpec, generate_certificate
from bptc.accumulator_checker import check_certificate
from bptc.publication_budget import ObligationLedger, BudgetExceeded


def conversion(value, width, mode):
    half = 2 ** (width - 1)
    if mode == 'saturate':
        return max(-half, min(half - 1, value))
    return (value + half) % (2 * half) - half


def execute_word(spec, word):
    total = spec['initial']
    st = spec['stages'][0]
    actual = conversion(total, st['acc_bits'], st['acc_mode'])
    first = -1
    for i, j in enumerate(word):
        st = spec['stages'][i]
        a, b = st['pairs'][j]
        total += a * b
        actual = conversion(actual + conversion(a * b, st['term_bits'], st['term_mode']),
                            st['acc_bits'], st['acc_mode'])
        if (st['observe'] or (spec['final_observe'] and i + 1 == len(spec['stages']))) \
                and actual != conversion(total, st['acc_bits'], st['acc_mode']) and first == -1:
            first = i
    return (total, actual - conversion(total, st['acc_bits'], st['acc_mode']), first != -1, first)


def literal_certificate(spec):
    """Enumerate all concrete prefixes; no quotient traversal or error recurrence."""
    stages = spec['stages']
    words = 1
    classes = []
    for st in stages:
        words *= len(st['pairs'])
        if words > 4096:
            raise ValueError('literal reference limited to 4096 full words')
        table = []
        for j, (a, b) in enumerate(st['pairs']):
            found = next((row for row in table if row['product'] == a * b), None)
            if found is None:
                found = dict(product=a*b, representative_index=j, representative_pair=[a,b],
                             member_indices=[], member_pairs=[])
                table.append(found)
            found['member_indices'].append(j)
            found['member_pairs'].append([a,b])
        classes.append(table)
    layers = []
    transitions = 0
    unquotiented = 0
    previous = None
    for depth in range(len(stages) + 1):
        states = {}
        for word in product(*(range(len(st['pairs'])) for st in stages[:depth])):
            state = execute_word(spec, word)
            if state not in states or word < states[state]:
                states[state] = word
        records = [dict(state=list(state), least_witness_indices=list(word),
                        least_witness_pairs=[stages[i]['pairs'][j] for i,j in enumerate(word)])
                   for state, word in sorted(states.items())]
        layer = dict(index=depth, states=records)
        if depth:
            edges = []
            for state, word in sorted(previous.items()):
                for row in classes[depth-1]:
                    edges.append(dict(from_=list(state), product=row['product'],
                                      representative_index=row['representative_index'],
                                      to=list(execute_word(spec, word + (row['representative_index'],)))))
                    edges[-1]['from'] = edges[-1].pop('from_')
            layer['edges'] = edges
            transitions += len(edges)
            unquotiented += len(previous) * len(stages[depth-1]['pairs'])
        layers.append(layer)
        previous = states
    bad = sorted((word,state) for state,word in states.items() if state[2])
    cex = None
    if bad:
        word,state = bad[0]
        cex = dict(indices=list(word), pairs=[stages[i]['pairs'][j] for i,j in enumerate(word)],
                   first_bad_stage=state[3], final_state=list(state))
    quotient_words = 1
    for table in classes:
        quotient_words *= len(table)
    return dict(format='bptc-exact-accumulator-certificate-v1', spec=deepcopy(spec),
                product_classes=classes, layers=layers,
                decision=dict(equivalent=not bad, least_counterexample=cex,
                              reachable_final_states=len(states), bad_final_states=len(bad)),
                metrics=dict(concrete_assignments=words, quotient_product_sequences=quotient_words,
                             producer_transitions=transitions, quotient_frontier_edges=transitions,
                             unquotiented_frontier_edges=unquotiented))


def as_spec(s):
    return AccumulatorSpec(s['name'], s['initial'], tuple(
        StageSpec(tuple(map(tuple,st['pairs'])), st['term_bits'], st['term_mode'],
                  st['acc_bits'], st['acc_mode'], st['observe']) for st in s['stages']),
        s['final_observe'], s['provenance'])


def finite_specs():
    domains = [[[0,0],[0,1],[2,1],[1,2],[-2,1]], [[8,1],[-8,1],[1,1]]]
    for width, tm, am, initial_index, obs, final in product(
            (2,3,4,8,32), ('wrap','saturate'), ('wrap','saturate'), range(6), (False,True), (False,True)):
        half = 2 ** (width-1)
        initial = (-half-1,-half,0,half-1,half,2**80)[initial_index]
        yield dict(name='finite', provenance='literal-regression', initial=initial, final_observe=final,
                   stages=[dict(pairs=deepcopy(domains[i]), term_bits=width if not i else 2,
                                term_mode=tm if not i else am, acc_bits=2 if not i else width,
                                acc_mode=am if not i else tm, observe=obs if not i else not obs)
                           for i in range(2)])
    # Deep singleton traces cover full schedule admission, sticky failure and
    # reconvergence without making the literal enumerator exponential.
    for n, final in product((1,3,8,32,64), (False,True)):
        yield dict(name='chain', provenance='literal-regression', initial=-9, final_observe=final,
                   stages=[dict(pairs=[[p,1]], term_bits=4, term_mode='wrap', acc_bits=4 if i%2==0 else 32,
                                acc_mode='saturate' if i%2==0 else 'wrap', observe=i%3==0)
                           for i,p in enumerate(([8,-1,-28,0]*16)[:n])])


class TraceLedger(ObligationLedger):
    def __post_init__(self):
        super().__post_init__()
        self.attempts = []

    def charge(self, category, count=1):
        self.attempts.append((category,count))
        return super().charge(category,count)


class HoistingRegression(unittest.TestCase):
    def test_literal_full_packets_and_charges(self):
        for spec in finite_specs():
            expected = literal_certificate(spec)
            producer = TraceLedger(200000)
            current = generate_certificate(as_spec(spec), producer, 'p')
            self.assertEqual(current, expected)
            checker = TraceLedger(200000)
            result = check_certificate(current, checker, 'c')
            self.assertTrue(result['accepted'])
            self.assertEqual(result['metrics'], expected['metrics'])
            wanted = []
            for st, layer in zip(spec['stages'], expected['layers'][1:]):
                wanted += [('p:partition-pair',len(st['pairs']))] + [('p:transition',1)]*len(layer['edges'])
            self.assertEqual(producer.attempts, wanted)
            wanted = [('c:schema',1)] + [('c:partition-pair',len(st['pairs'])) for st in spec['stages']]
            wanted += [('c:transition',1)]*expected['metrics']['producer_transitions']
            self.assertEqual(checker.attempts, wanted)

    def test_caps_mutants_and_fresh_calls(self):
        spec = next(finite_specs())
        original = literal_certificate(spec)
        for cap in range(1, 40):
            for operation in (lambda ledger: generate_certificate(as_spec(spec),ledger),
                              lambda ledger: check_certificate(original,ledger)):
                ledger = TraceLedger(cap)
                try:
                    operation(ledger)
                except BudgetExceeded:
                    self.assertLessEqual(ledger.used, cap)
                    self.assertEqual(sum(ledger.categories.values()), ledger.used)
        for path in ('state','edge','witness','class','count','decision'):
            c = deepcopy(original)
            if path == 'state': c['layers'][1]['states'][0]['state'][1] += 1
            if path == 'edge': c['layers'][1]['edges'].reverse()
            if path == 'witness': c['layers'][1]['states'][0]['least_witness_indices'][0] += 1
            if path == 'class': c['product_classes'][0][0]['member_indices'].pop()
            if path == 'count': c['metrics']['producer_transitions'] += 1
            if path == 'decision': c['decision']['equivalent'] = not c['decision']['equivalent']
            with self.assertRaises(ValueError): check_certificate(c, ObligationLedger(200000))
        changed = deepcopy(spec)
        changed['stages'][0]['acc_bits'] = 32
        changed['stages'][0]['acc_mode'] = 'wrap'
        other = generate_certificate(as_spec(changed), ObligationLedger(200000))
        self.assertEqual(other, literal_certificate(changed))
        check_certificate(other, ObligationLedger(200000))
        self.assertEqual(generate_certificate(as_spec(spec), ObligationLedger(200000)), original)

    def test_strict_admission_and_diagnostic_order(self):
        base = literal_certificate(next(finite_specs()))
        for field,value in (('term_bits',True),('acc_bits',1),('term_mode','unknown'),
                            ('observe',1),('pairs',[]),('pairs',[[1,1],[1,1]]),('pairs',[[False,1]])):
            c = deepcopy(base)
            c['spec']['stages'][0][field] = value
            c['layers'] = None  # Declaration admission precedes evidence replay.
            with self.assertRaises(ValueError): check_certificate(c, TraceLedger(200000))
        c = deepcopy(base)
        c['spec']['initial'] = True
        c['spec']['stages'] = []
        with self.assertRaisesRegex(ValueError,'spec.initial: invalid integer'):
            check_certificate(c, TraceLedger(200000))


if __name__ == '__main__':
    unittest.main()
