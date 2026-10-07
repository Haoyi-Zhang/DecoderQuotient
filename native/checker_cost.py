#!/usr/bin/env python3
"""Separately time the delivered Python replay checker, only in a reserved slot.

SPDX-License-Identifier: MIT; see ../LICENSE. Not a native/Python speedup test.
"""
from __future__ import annotations
import argparse
import ctypes
import json
import os
from pathlib import Path
import platform
import statistics
import sys
import time
sys.dont_write_bytecode = True
ARTIFACT=Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ARTIFACT))
from bptc.accumulator_checker import check_certificate
from bptc.publication_budget import ObligationLedger


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--slot',required=True)
    parser.add_argument('--out',type=Path,default=ARTIFACT/'results/native-reproduction')
    args=parser.parse_args()
    out=args.out.resolve()
    assert args.slot!='COORDINATOR_RESERVED_SLOT' and args.slot
    native_measure=json.loads((out/'measurement-summary.json').read_text(encoding='utf-8'))
    assert native_measure['slot']==args.slot
    # Pin separate replay overhead to the same actual native logical CPU.
    cpu=native_measure['affinity']['selected_logical_cpu']
    if os.name=='nt':
        kernel=ctypes.WinDLL('kernel32',use_last_error=True)
        kernel.GetCurrentProcess.restype=ctypes.c_void_p
        kernel.SetProcessAffinityMask.argtypes=[ctypes.c_void_p,ctypes.c_size_t]
        kernel.GetProcessAffinityMask.argtypes=[ctypes.c_void_p,ctypes.POINTER(ctypes.c_size_t),ctypes.POINTER(ctypes.c_size_t)]
        handle=kernel.GetCurrentProcess();mask=1<<cpu
        assert kernel.SetProcessAffinityMask(handle,mask), 'cannot pin checker process'
        actual=ctypes.c_size_t();system=ctypes.c_size_t()
        assert kernel.GetProcessAffinityMask(handle,ctypes.byref(actual),ctypes.byref(system)) and actual.value==mask
        actual_mask=hex(actual.value)
    else:
        os.sched_setaffinity(0,{cpu})
        assert os.sched_getaffinity(0)=={cpu}
        actual_mask=hex(1<<cpu)
    assert actual_mask==native_measure['affinity']['actual_mask_hex']
    target=out/'checker-samples.json'
    assert not target.exists() and not (out/'checker-measurement-budget.json').exists()
    native=json.loads((out/'native-o3.json').read_text(encoding='utf-8'))
    # Parsing is outside timing. Replay revalidates all declaration and evidence.
    ledger=ObligationLedger(200000)
    samples=[]
    status='running'
    try:
        for entry in native['accumulators']:
            cert=entry['quotient_certificate']
            check_certificate(cert,ledger,'checker-cost-warmup')
            for rep in range(21):
                before=ledger.used
                start=time.perf_counter_ns()
                decision=check_certificate(cert,ledger,'checker-cost-measured')
                elapsed=time.perf_counter_ns()-start
                assert decision['accepted']
                samples.append({'case':entry['name'],'sample':rep,'checker_ns':elapsed,
                                'obligations':ledger.used-before})
            ledger.write(out/'checker-measurement-budget.json')
        status='complete'
    finally:
        ledger.write(out/'checker-measurement-budget.json')
        result={'format':'p053-python-checker-cost-v1','slot':args.slot,'status':status,
                'python':sys.executable,'python_version':platform.python_version(),
                'affinity':{'selected_logical_cpu':cpu,'actual_mask_hex':actual_mask,'verified_single_cpu':True},
                'samples':samples,'budget':ledger.to_dict(),
                'scope':'Delivered Python replay overhead, separate from native traversal; no cross-language speedup claim.'}
        target.write_text(json.dumps(result,indent=2,sort_keys=True)+'\n',encoding='utf-8')
    rows=[]
    for entry in native['accumulators']:
        values=[s['checker_ns'] for s in samples if s['case']==entry['name']]
        assert len(values)==21
        rows.append({'case':entry['name'],'samples':21,'median_checker_ns':statistics.median(values),
                     'min_checker_ns':min(values),'max_checker_ns':max(values)})
    (out/'checker-summary.json').write_text(json.dumps({'format':'p053-python-checker-summary-v1',
                          'slot':args.slot,'rows':rows},indent=2,sort_keys=True)+'\n',encoding='utf-8')
    print('Separate checker overhead complete:',len(rows),'cases;',ledger.used,'of',ledger.limit,'declared obligations.')


if __name__=='__main__':main()
