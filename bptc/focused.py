"""Focused grammar repairs and a counterexample to necessity of no saturation.

These checks are outside the frozen 142-case comparative corpus and do not
change that inventory. Their explicit transition charge is reported separately.
"""
from __future__ import annotations
import argparse
import json
import resource
import time
from copy import deepcopy
from pathlib import Path
from .budget import require_hard_meter
from .cases import base
from .producer import produce
from .checker import verify, Invalid
from .semantics import execute


def run(out: Path) -> dict:
    require_hard_meter()
    started = time.process_time()
    count = 0
    rows = []
    c = base(1, 32)
    c['id'] = 'grammar-control'
    good = produce(c)
    count += sum(t['transitions'] for t in good['tables'])
    meter = {}
    assert verify(c, good, meter)['accepted']
    count += meter.get('transitions', 0)
    for name, field in [('boolean-offset', 'input_offset'), ('float-scale', 'scale')]:
        bad = deepcopy(good)
        bad['binding'][field] = False if field == 'input_offset' else float(c[field])
        meter = {}
        try:
            verify(c, bad, meter)
        except Invalid:
            rows.append({'check': name, 'rejected': True})
        else:
            raise AssertionError(name)
        count += meter.get('transitions', 0)
    for name, field in [('boolean-prefix', 'prefix'), ('integer-fit', 'fits')]:
        bad = deepcopy(good)
        bad['accumulation']['checks'][0][field] = True if field == 'prefix' else 1
        meter = {}
        try:
            verify(c, bad, meter)
        except Invalid:
            rows.append({'check': name, 'rejected': True})
        else:
            raise AssertionError(name)
        count += meter.get('transitions', 0)
    c = base(8, 4, 2, 8, (0, 0))
    c['id'] = 'witness-type-control'
    cert = produce(c)
    count += sum(t['transitions'] for t in cert['tables'])
    bad = deepcopy(cert)
    bad['tables'][0]['witness'] = [False]*8
    meter = {}
    try:
        verify(c, bad, meter)
    except Invalid:
        rows.append({'check': 'boolean-witness', 'rejected': True})
    else:
        raise AssertionError('boolean witness accepted')
    count += meter.get('transitions', 0)
    c = base(8, 4, 1, 8)
    c['id'] = 'saturation-not-necessary'
    q = [15, 15, 0, 1, 1, 15, 15, 8]
    c['domains'] = [[v, v] for v in q]
    c['activation_bounds'] = [1, 1]
    c['acc_widths'] = [4]*8
    c['acc_semantics'] = 'saturating'
    cert = produce(c)
    count += sum(t['transitions'] for t in cert['tables'])
    meter = {}
    verdict = verify(c, cert, meter)
    count += meter.get('transitions', 0)
    reference, target = execute(c, q, [1]*8)
    count += 1
    assert verdict['stage'] == 'accumulation' and reference == target == 6
    rows.append({'check': c['id'], 'stage': verdict['stage'], 'reference': reference,
                 'target': target, 'terms': [v-8 for v in q], 'specification': c})
    result = {'checks': len(rows), 'enumeration_charge': count, 'rows': rows}
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2, sort_keys=True)+'\n')
    print(json.dumps({'checks': len(rows), 'enumeration_charge': count,
                      'cpu_seconds': time.process_time()-started,
                      'peak_rss_kib': resource.getrusage(resource.RUSAGE_SELF).ru_maxrss}))
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--compare', type=Path)
    args = parser.parse_args()
    result = run(args.out)
    if args.compare is not None:
        assert result == json.loads(args.compare.read_text()), 'focused outputs changed'
        print('Focused outputs match exactly.')
