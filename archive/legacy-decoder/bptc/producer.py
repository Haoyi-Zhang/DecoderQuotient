"""Untrusted certificate construction. No calls to the replay checker."""
from __future__ import annotations
from copy import deepcopy
from typing import Any

MODES = ('mul_sub','sub_mul','word_sub','word_affine','sat_mul_sub')


def _records(states: dict[tuple[int, bool], tuple[int, ...]]) -> list[dict]:
    return [{'carry': c, 'bad': bad, 'prefix': list(path)}
            for (c, bad), path in sorted(states.items())]


def make_table(domains: list[list[int]], bits: int, scale: int,
               zero: int, mode: str) -> dict:
    B = 1 << bits
    states: dict[tuple[int, bool], tuple[int, ...]] = {(0, False): ()}
    layers = [_records(states)]
    transitions = 0
    for low, high in domains:
        successors: dict[tuple[int, bool], tuple[int, ...]] = {}
        for (carry, bad), prefix in states.items():
            for q in range(low, high + 1):
                transitions += 1
                if mode == 'sub_mul':
                    total = scale * ((q-zero) % B) + carry
                    outgoing, digit = divmod(total, B)
                elif mode == 'word_sub':
                    total = scale*q - (scale*zero % B) + carry
                    outgoing, digit = divmod(total, B)
                elif mode == 'word_affine':
                    total = scale*(q-zero) + carry
                    outgoing, digit = divmod(total, B)
                elif mode == 'sat_mul_sub':
                    outgoing = 0
                    digit = (min(scale*q, B//2-1) - scale*zero) % B
                elif mode == 'mul_sub':
                    total = scale*q + carry
                    outgoing = total // B
                    digit = (total - scale*zero) % B
                else:
                    raise ValueError('unsupported arithmetic')
                observed = digit if digit < B//2 else digit-B
                key = (outgoing, bad or observed != scale*(q-zero))
                candidate = prefix + (q,)
                if key not in successors or candidate < successors[key]:
                    successors[key] = candidate
        states = successors
        layers.append(_records(states))
    failures = [p for (_, bad), p in states.items() if bad]
    return {'domains': deepcopy(domains), 'layers': layers,
            'witness': list(min(failures)) if failures else None,
            'transitions': transitions}


def layout_contract(case: dict) -> bool:
    n = len(case['domains'])
    address_limit = 1 << 32
    ib, ie = case['input_offset'], case['input_offset'] + (n+1)//2
    ob, oe = case['output_offset'], case['output_offset'] + 4
    return (sorted(case['layout']) == list(range(n)) and
            case['consume'] == case['layout'] and
            0 <= ib <= ie <= min(case['memory_bytes'], address_limit) and
            0 <= ob <= oe <= min(case['memory_bytes'], address_limit) and
            (ie <= ob or oe <= ib))


def accumulation(case: dict) -> dict:
    n = len(case['domains'])
    checkpoints = set(case['observations']) | {n}
    if case['acc_semantics'] == 'saturating':
        checkpoints.update(range(1, n+1))
    else:
        checkpoints.update(i for i in range(1,n)
                           if case['acc_widths'][i] > case['acc_widths'][i-1])
    lower = upper = 0
    checks = []
    for i, logical in enumerate(case['layout']):
        lo, hi = case['domains'][logical]
        wlo = case['scale']*(lo-case['zero'])
        whi = case['scale']*(hi-case['zero'])
        products = [a*w for a in case['activation_bounds'] for w in (wlo,whi)]
        lower += min(products)
        upper += max(products)
        if i+1 in checkpoints:
            b = case['acc_widths'][i]
            fits = -(1 << (b-1)) <= lower and upper < (1 << (b-1))
            checks.append({'prefix':i+1,'bits':b,'lower':lower,'upper':upper,'fits':fits})
    return {'checks':checks, 'satisfied':all(c['fits'] for c in checks)}


def produce(case: dict) -> dict:
    lanes = 32//case['bits']
    tables: list[dict] = []
    references = []
    known: dict[tuple, int] = {}
    for start in range(0,len(case['domains']),lanes):
        domains = [case['domains'][i] for i in case['layout'][start:start+lanes]]
        key = tuple(tuple(d) for d in domains)
        if key not in known:
            known[key] = len(tables)
            tables.append(make_table(domains,case['bits'],case['scale'],case['zero'],case['arithmetic']))
        references.append(known[key])
    layout_ok = layout_contract(case)
    decode_ok = all(t['witness'] is None for t in tables)
    acc = accumulation(case)
    stage = ('layout' if not layout_ok else 'decode' if not decode_ok else
             'accumulation' if not acc['satisfied'] else 'accepted')
    return {'binding':deepcopy(case), 'tables':tables, 'block_table':references,
            'layout_satisfied':layout_ok, 'decode_satisfied':decode_ok,
            'accumulation':acc, 'stage':stage}
