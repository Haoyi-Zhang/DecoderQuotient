"""Exact closed-form comparator for the frozen word language.

This later analytical control tests whether carry-state search is necessary
for the restricted grammar. It uses no producer, checker, interpreter or SMT
arithmetic helpers. Its comparison is post hoc, not a frozen timing baseline.
"""
from __future__ import annotations
import argparse
import json
import time
from copy import deepcopy
from pathlib import Path
from .budget import require_hard_meter


def equal_word(domains, bits, scale, zero, mode, meter=None):
    if meter is not None:
        meter['decision_calls'] = meter.get('decision_calls', 0)+1
    base = 2**bits
    half = base//2
    # Every observed reference must have a signed representation.
    if any(scale*(low-zero) < -half or scale*(high-zero) >= half
           for low, high in domains):
        return False
    if mode == 'sat_mul_sub':
        if scale == 0:
            return True
        last_unclipped = (half-1)//scale
        for low, high in domains:
            first_clipped = max(low, last_unclipped+1)
            if first_clipped > high:
                continue
            # Two adjacent clipped codes cannot both have an error divisible
            # by base, since 0 < scale < base.
            if first_clipped < high:
                return False
            if (scale*high-(half-1)) % base:
                return False
        return True
    for low, high in domains[:-1]:
        if mode == 'mul_sub':
            if scale*high >= base:
                return False
        elif mode == 'sub_mul':
            if scale >= 2 and low < zero:
                return False
        elif mode == 'word_sub':
            correction = (scale*zero) % base
            if scale*low-correction < 0 or scale*high-correction >= base:
                return False
        elif mode == 'word_affine':
            if scale*(low-zero) < 0:
                return False
        else:
            raise ValueError('arithmetic outside the grammar')
    return True


def first_failure(domains, bits, scale, zero, mode, meter=None):
    if equal_word(domains,bits,scale,zero,mode,meter):
        return None
    remaining = deepcopy(domains)
    for i in range(len(remaining)):
        low, high = remaining[i]
        while low < high:
            middle = (low+high)//2
            candidate = deepcopy(remaining)
            candidate[i] = [low,middle]
            if equal_word(candidate,bits,scale,zero,mode,meter):
                low = middle+1
            else:
                high = middle
        remaining[i] = [low,low]
    return [low for low,_ in remaining]


def run(reference, out):
    require_hard_meter()
    start = time.process_time()
    cases = json.loads((reference/'cases.json').read_text())
    certificates = json.loads((reference/'certificates.json').read_text())
    meter = {}; rows=[];table_count=0
    for case,cert in zip(cases,certificates):
        local=[]
        for table in cert['tables']:
            table_count += 1
            args=(table['domains'],case['bits'],case['scale'],case['zero'],case['arithmetic'])
            witness = first_failure(*args,meter=meter)
            assert witness == table['witness'], ('closed form differs',case['id'],witness,table['witness'])
            local.append({'equal': witness is None, 'witness': witness})
        rows.append({'id': case['id'], 'decoder_equal': all(x['equal'] for x in local),
                     'tables': local})
    result={'cases':len(rows),'table_comparisons':table_count,'disagreements':0,
            'enumeration_charge':meter['decision_calls'],'rows':rows}
    out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(result,sort_keys=True,indent=2)+'\n')
    print(json.dumps({k:v for k,v in result.items() if k!='rows'}))
    print(json.dumps({'cpu_seconds':time.process_time()-start}))
    return result


if __name__ == '__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--reference',type=Path,required=True)
    parser.add_argument('--out',type=Path,required=True)
    parser.add_argument('--compare',type=Path)
    args=parser.parse_args()
    result=run(args.reference,args.out)
    if args.compare:
        assert result==json.loads(args.compare.read_text()), 'closed-form outputs changed'
        print('Closed-form outputs match exactly.')
