"""Bounded sequential campaign and deterministic result reconciliation."""
from __future__ import annotations
import argparse
import csv
import json
import resource
import time
from collections import Counter
from copy import deepcopy
from itertools import product
from pathlib import Path
from random import Random
from .budget import require_hard_meter
from .cases import inventory,base
from .producer import produce,make_table
from .checker import verify,Invalid
from .semantics import exhaustive_word,decode_word,execute,nibble_pack32,nibble_unpack32
from .smt import Solver,encode

ROOT=Path(__file__).resolve().parents[1]


def save(path: Path,obj) -> None:
    path.write_text(json.dumps(obj,sort_keys=True,indent=2)+'\n')


def conservative_signed_guard(c: dict) -> bool:
    """A sound but deliberately stricter guard for mul_sub only."""
    if c['arithmetic']!='mul_sub':return False
    H=1<<(c['bits']-1)
    return all(hi*c['scale']<H and -H<=c['scale']*(lo-c['zero'])
               and c['scale']*(hi-c['zero'])<H for lo,hi in c['domains'])


def scalar_only(c: dict) -> bool:
    """Unsound ablation: pretends each word multiplication is lane-isolated."""
    b=c['bits'];B=1<<b
    for lo,hi in c['domains']:
        for q in range(lo,hi+1):
            if c['arithmetic']=='sat_mul_sub':
                d=(min(q*c['scale'],B//2-1)-c['scale']*c['zero'])%B
            else:
                d=(c['scale']*(q-c['zero']))%B
            observed=d-B if d>=B//2 else d
            if observed!=c['scale']*(q-c['zero']):return False
    return True


def oracle_suite() -> dict:
    rows=[];assignments=0;transitions=0
    # 40 cases, 3,570 complete valuations: deliberately reduced alphabets at all four widths.
    for bits,s,zero,mode in product((4,8,16,32),(1,2),(3,),
                                  ('mul_sub','sub_mul','word_sub','word_affine','sat_mul_sub')):
        lanes=32//bits
        high=1 if bits==4 else 2 if bits==8 else 3
        domains=[[0,high]]*lanes
        t=make_table(domains,bits,s,zero,mode);transitions+=t['transitions']
        expected,count=exhaustive_word(domains,bits,s,zero,mode);assignments+=count
        if t['witness']!=expected:raise AssertionError(('oracle disagreement',bits,s,zero,mode))
        rows.append(dict(bits=bits,scale=s,zero=zero,mode=mode,assignments=count,witness=expected))
    # Pairwise byte/nibble oracle uses an independent mask expression, not the producer.
    pack_checks=0
    for a,b in product(range(16),repeat=2):
        byte=a+16*b
        if byte&15!=a or (byte>>4)&15!=b:raise AssertionError('nibble identity')
        pack_checks+=1
    for logical in range(32):
        for value in (0,1,7,8,15):
            q=[0]*32;q[logical]=value
            if nibble_unpack32(nibble_pack32(q))!=q:raise AssertionError('interleave identity')
            pack_checks+=1
    return dict(rows=rows,assignments=assignments,producer_transitions=transitions,packing_checks=pack_checks)


def fault_suite(cases,certificates) -> dict:
    rows=[];replay_cost=0;actual_cost=0
    selected=[0,6,12,20,120,126,127,131]
    for index in selected:
        c=cases[index];original=certificates[index]
        faults=[]
        def mutation(name,change):
            candidate=deepcopy(original);change(candidate);faults.append((name,candidate))
        mutation('claimed-stage',lambda t:t.__setitem__('stage','decode' if t['stage']=='accepted' else 'accepted'))
        mutation('decision',lambda t:t.__setitem__('decode_satisfied',not t['decode_satisfied']))
        mutation('input-domain-binding',lambda t:t['binding'].__setitem__('zero',(c['zero']+1)%16))
        mutation('initial-carry',lambda t:t['tables'][0]['layers'][0][0].__setitem__('carry',1))
        mutation('drop-final-layer',lambda t:t['tables'][0]['layers'].pop())
        mutation('flip-bad-state',lambda t:t['tables'][0]['layers'][-1][0].__setitem__('bad',not t['tables'][0]['layers'][-1][0]['bad']))
        mutation('witness',lambda t:t['tables'][0].__setitem__('witness',[99]))
        mutation('transition-count',lambda t:t['tables'][0].__setitem__('transitions',-1))
        mutation('duplicate-state',lambda t:t['tables'][0]['layers'][0].append(deepcopy(t['tables'][0]['layers'][0][0])))
        mutation('range-endpoint',lambda t:t['accumulation']['checks'][-1].__setitem__('upper',t['accumulation']['checks'][-1]['upper']+1))
        mutation('table-binding',lambda t:t['block_table'].__setitem__(0,len(t['tables'])))
        mutation('extra-field',lambda t:t.__setitem__('unchecked_extra',True))
        for name,bad in faults:
            # Conservative accounting charges a complete replay even for early rejection.
            replay_cost+=sum(t['transitions'] for t in original['tables'])
            meter={}
            try:verify(c,bad,meter)
            except (Invalid,TypeError,KeyError,IndexError) as e:
                rows.append(dict(id=c['id'],fault=name,rejected=True,reason=str(e)))
            else:raise AssertionError(('accepted corrupt certificate',c['id'],name))
            actual_cost+=meter.get('transitions',0)
    return dict(rows=rows,rejected=len(rows),conservative_transition_charge=replay_cost,actual_transition_charge=actual_cost)


def run(destination: Path, solver_enabled: bool=True, replay_from: Path | None = None) -> dict:
    require_hard_meter()
    destination.mkdir(parents=True,exist_ok=True)
    resource.setrlimit(resource.RLIMIT_AS,(2500*1024**2,2500*1024**2))
    resource.setrlimit(resource.RLIMIT_CPU,(110,119))
    start_cpu=time.process_time();start_wall=time.monotonic()
    cases,metadata=inventory();certificates=[];rows=[];queries=[]
    solver=Solver() if solver_enabled else None
    retained=json.loads((replay_from/"certificates.json").read_text()) if replay_from else None
    random=Random(20260914)
    replay_samples=0;transitions=0
    for case_index,(c,m) in enumerate(zip(cases,metadata)):
        t0=time.perf_counter_ns();cert=retained[case_index] if retained is not None else produce(c);t1=time.perf_counter_ns()
        verdict=verify(c,cert);t2=time.perf_counter_ns()
        transitions+=(1 if retained is not None else 2)*verdict['transitions']
        certificates.append(cert)
        row=dict(id=c['id'],family=m['family'],n=len(c['domains']),bits=c['bits'],
                 mode=c['arithmetic'],stage=verdict['stage'],accepted=verdict['accepted'],
                 unique_tables=verdict['unique_tables'],maximum_states=verdict['maximum_states'],
                 transitions=verdict['transitions'],certificate_bytes=len(json.dumps(cert,separators=(',',':')).encode()),
                 producer_ns=t1-t0,checker_ns=t2-t1,scalar_ablation=scalar_only(c),
                 conservative_guard=conservative_signed_guard(c),smt='not-run')
        # The SMT baseline checks one complete decoder word, not the full dot product or memory contract.
        if m['family']=='word-grid' and solver:
            begin=time.perf_counter_ns()
            text=encode(c['domains'],c['bits'],c['scale'],c['zero'],c['arithmetic'])
            encoded=time.perf_counter_ns();answer=solver.check(text);end=time.perf_counter_ns()
            row.update(smt=answer,smt_encode_ns=encoded-begin,smt_solve_ns=end-encoded)
            expected='unsat' if cert['decode_satisfied'] else 'sat'
            if answer not in (expected,'unknown'):raise AssertionError(('SMT disagreement',c['id'],answer,expected))
            queries.append({'id':c['id'],'query':text,'result':answer,'expected':expected})
        # Whole-word witness replay, different algorithm from both certificate implementations.
        for table in cert['tables']:
            if table['witness'] is not None:
                q=table['witness'];actual=decode_word(q,c['bits'],c['scale'],c['zero'],c['arithmetic'])
                reference=[c['scale']*(v-c['zero']) for v in q]
                if actual==reference:raise AssertionError('non-failing witness')
                replay_samples+=1
        # Representative full-kernel replay is testing, never a universal proof.
        if verdict['accepted']:
            for sample in range(3):
                q=[random.randint(lo,hi) for lo,hi in c['domains']]
                a=[random.randint(*c['activation_bounds']) for _ in q]
                ref,actual=execute(c,q,a);replay_samples+=1
                if ref!=actual:raise AssertionError(('accepted kernel disagrees',c['id']))
        rows.append(row)
    oracle=oracle_suite();faults=fault_suite(cases,certificates)
    counts=Counter(r['stage'] for r in rows)
    grid=[(c,r) for c,r in zip(cases,rows) if r['family']=='word-grid']
    summary=dict(cases=len(cases),stages=dict(sorted(counts.items())),
                 decoder_valid=sum(cert['decode_satisfied'] for cert in certificates),
                 smt_queries=len(queries),smt_results=dict(Counter(q['result'] for q in queries)),
                 smt_disagreements=0,oracle_cases=len(oracle['rows']),oracle_assignments=oracle['assignments'],
                 packing_checks=oracle['packing_checks'],certificate_faults=faults['rejected'],
                 whole_interpreter_replays=replay_samples,
                 scalar_false_accepts=sum(r['scalar_ablation'] and not cert['decode_satisfied']
                                          for r,cert in zip(rows,certificates)),
                 guard_false_rejects=sum(c['arithmetic']=='mul_sub' and cert['decode_satisfied']
                                          and not r['conservative_guard']
                                          for c,cert,r in zip(cases,certificates,rows)),
                 max_states=max(r['maximum_states'] for r in rows),
                 max_certificate_bytes=max(r['certificate_bytes'] for r in rows),
                 implementation_transitions=transitions+oracle['producer_transitions'],
                 conservative_fault_transition_charge=faults['conservative_transition_charge'],
                 actual_fault_transition_charge=faults['actual_transition_charge'])
    # Explicit enumeration accounting includes implementation transitions and oracle valuations.
    summary['enumeration_charge']=summary['implementation_transitions']+oracle['assignments']+oracle['packing_checks']+faults['actual_transition_charge']+len(queries)+replay_samples
    if summary['enumeration_charge']>75000:raise AssertionError(('planned enumeration allowance exceeded',summary['enumeration_charge']))
    resources=dict(cpu_seconds=time.process_time()-start_cpu,wall_seconds=time.monotonic()-start_wall,
                   peak_rss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
                   workers=1,solver_timeout_ms=2000,enumeration_charge=summary['enumeration_charge'])
    save(destination/'cases.json',cases);save(destination/'case_metadata.json',metadata)
    save(destination/'certificates.json',certificates);save(destination/'summary.json',summary)
    save(destination/'resources.json',resources);save(destination/'oracle.json',oracle)
    save(destination/'certificate_faults.json',faults);save(destination/'smt_queries.json',queries)
    with (destination/'raw.csv').open('w',newline='') as f:
        fields=sorted(set().union(*(r.keys() for r in rows)))
        writer=csv.DictWriter(f,fieldnames=fields);writer.writeheader();writer.writerows(rows)
    print(json.dumps(summary,indent=2));print(json.dumps(resources,indent=2))
    return summary


def compare(expected: Path,actual: Path) -> None:
    for name in ('cases.json','case_metadata.json','certificates.json','summary.json',
                 'oracle.json','certificate_faults.json','smt_queries.json'):
        left=json.loads((expected/name).read_text());right=json.loads((actual/name).read_text())
        if name=='summary.json':
            for key in ('implementation_transitions','enumeration_charge'):
                left.pop(key,None);right.pop(key,None)
        if left!=right:raise AssertionError('non-timing scientific result differs: '+name)
    for base in (expected, actual):
        with (base/'raw.csv').open(newline='') as stream:
            rows = [{k: v for k, v in row.items() if not k.endswith('_ns')}
                    for row in csv.DictReader(stream)]
        if base == expected:
            expected_rows = rows
        elif rows != expected_rows:
            raise AssertionError('non-timing scientific result differs: raw.csv')
    print('All retained non-timing outputs match exactly; timing/RSS are intentionally not compared.')


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--out',type=Path,required=True)
    parser.add_argument('--compare',type=Path)
    parser.add_argument('--without-solver',action='store_true')
    parser.add_argument('--replay-from',type=Path)
    args=parser.parse_args()
    run(args.out,not args.without_solver,args.replay_from)
    if args.compare:compare(args.compare,args.out)

if __name__=='__main__':main()
