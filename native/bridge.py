#!/usr/bin/env python3
"""P053-only compiler/conformance harness. Measurements require an explicit slot.

SPDX-License-Identifier: MIT; original material covered by ../LICENSE.
No old campaign CLI, network, GPU, or global ledger is invoked.
"""
from __future__ import annotations
import argparse
from collections import defaultdict
from copy import deepcopy
import hashlib
from itertools import product
import json
import os
from pathlib import Path
import platform
import shutil
import statistics
import subprocess
import sys

ARTIFACT = Path(__file__).resolve().parents[1]
DEFAULT_OUT = ARTIFACT / 'results/native-reproduction'
sys.dont_write_bytecode = True
sys.path.insert(0, str(ARTIFACT))
# All imported arithmetic/source modules were fully reviewed before invocation.
from bptc.publication_cases import accumulator_specs, decoder_specs
from bptc.exact_accumulator import AccumulatorSpec, StageSpec, spec_to_dict, generate_certificate
from bptc.packed_decoder import spec_to_dict as decoder_dict
from bptc.accumulator_checker import check_certificate, validate_spec
from bptc.accumulator_oracle import run_oracle
from bptc.publication_budget import ObligationLedger


def dump(path, value):
    path.write_text(json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + '\n', encoding='utf-8')


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def controls():
    """Predeclared additional conformance cases, never mixed into old results."""
    cases = []
    for bits in (2, 32):
        for mode in ('wrap', 'saturate'):
            for initial in (-(1 << (bits-1))-1, (1 << (bits-1))):
                stage = StageSpec(((1, -1), (-1, 1), (0, 0)), bits, mode, bits, mode, True)
                cases.append(AccumulatorSpec(f'native-initial-{bits}-{mode}-{initial}', initial,
                                             (stage,), True, 'native-boundary-control'))
    # Separately declared unique-product and duplicate-product controls. Same
    # reachable mathematical products {-1,0,1}, varied length 4/8/16.
    for n in (4, 8, 16):
        for duplicated in (False, True):
            pairs = ((0, 0), (1, 1), (1, -1)) if not duplicated else (
                (0, 0), (0, 1), (1, 0), (1, 1), (-1, -1), (1, -1), (-1, 1))
            st = StageSpec(pairs, 8, 'wrap', 8, 'wrap', False)
            cases.append(AccumulatorSpec(f'native-scaling-{n}-' + ('duplicate' if duplicated else 'unique'),
                                         0, (st,)*n, True, 'native-scaling-control'))
    # No observed stages: arithmetic divergence alone does not imply failure.
    st = StageSpec(((2, 4), (-2, -4), (0, 0)), 4, 'wrap', 8, 'saturate', False)
    cases.append(AccumulatorSpec('native-no-observation', 8, (st, st), False, 'native-boundary-control'))
    return cases


def panel():
    return {'format': 'p053-native-panel-v1',
            'accumulators': [spec_to_dict(s) for s in accumulator_specs()+controls()],
            'decoders': [decoder_dict(s) for s in decoder_specs()]}


def panel_text(p):
    lines = [f"p053-native-panel-v1 {len(p['accumulators'])} {len(p['decoders'])}"]
    for s in p['accumulators']:
        lines.append(f"A {s['name']} {s['provenance']} {s['initial']} {int(s['final_observe'])} {len(s['stages'])}")
        for st in s['stages']:
            lines.append(f"S {st['term_bits']} {st['term_mode']} {st['acc_bits']} {st['acc_mode']} {int(st['observe'])} {len(st['pairs'])}")
            lines.extend(f'P {x} {y}' for x, y in st['pairs'])
    for d in p['decoders']:
        pairs = ' '.join(f'{x} {b}' for x, b in zip(d['maxima'], d['biases']))
        lines.append(f"D {d['name']} {d['provenance']} {d['scale']} {len(d['maxima'])} {pairs}")
    return '\n'.join(lines)+'\n'


def environment(out):
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE='1',
               ZIG_GLOBAL_CACHE_DIR=str(out/'cache/global'),
               ZIG_LOCAL_CACHE_DIR=str(out/'cache/local'),
               TEMP=str(out/'tmp'), TMP=str(out/'tmp'))
    for p in (out/'cache/global', out/'cache/local', out/'tmp'):
        p.mkdir(parents=True, exist_ok=True)
    return env


def run(command, out, log, timeout=60):
    result = subprocess.run([str(v) for v in command], capture_output=True, text=True,
                            encoding='utf-8', errors='replace', env=environment(out),
                            cwd=out, timeout=timeout)
    dump(out/(log+'.command.json'), {'command': [str(v) for v in command],
                                   'timeout_seconds': timeout, 'returncode': result.returncode})
    (out/(log+'.log')).write_text(result.stdout+result.stderr, encoding='utf-8')
    if result.returncode:
        raise RuntimeError(f'{log} failed ({result.returncode}): {result.stderr[:1000]}')
    return result.stdout


def independent_convert(value, bits, mode):
    """Arbitrary-precision reference, no native/error-state transition helper."""
    if mode == 'saturate':
        return max(-(2**(bits-1)), min(2**(bits-1)-1, value))
    residue = value & (2**bits-1)
    return residue if residue < 2**(bits-1) else residue-2**bits


def trace(s, indices):
    target = s['initial']
    first = s['stages'][0]
    actual = independent_convert(target, first['acc_bits'], first['acc_mode'])
    bad = -1
    steps = []
    for i, (st, index) in enumerate(zip(s['stages'], indices)):
        pair = st['pairs'][index]
        p = pair[0]*pair[1]
        term = independent_convert(p, st['term_bits'], st['term_mode'])
        target += p
        actual = independent_convert(actual+term, st['acc_bits'], st['acc_mode'])
        ref = independent_convert(target, st['acc_bits'], st['acc_mode'])
        observed = st['observe'] or (s['final_observe'] and i+1==len(s['stages']))
        if observed and actual != ref and bad < 0:
            bad = i
        steps.append({'stage': i, 'pair': pair, 'product': p, 'term': term,
                      'target': target, 'lowered': actual, 'reference': ref,
                      'observed': observed, 'first_bad': bad})
    return steps


def compare(native, p, ledger):
    original = {s.name for s in accumulator_specs()}
    original_q = original_u = original_words = all_words = decoder_words = 0
    rows = []
    assert native['format']=='p053-native-conformance-v1' and not native['performance_measured']
    assert len(native['accumulators']) == len(p['accumulators'])
    for entry, s in zip(native['accumulators'], p['accumulators']):
        assert entry['name'] == s['name']
        cert = entry['quotient_certificate']
        validate_spec(s)
        if s['name'] in original:
            expected = json.loads((ARTIFACT/'results/publication/main/certificates'/f"{s['name']}.json").read_text(encoding='utf-8'))
        else:
            stages = tuple(StageSpec(tuple(map(tuple, st['pairs'])), st['term_bits'], st['term_mode'],
                                     st['acc_bits'], st['acc_mode'], st['observe']) for st in s['stages'])
            expected = generate_certificate(AccumulatorSpec(s['name'], s['initial'], stages,
                                            s['final_observe'], s['provenance']), ledger, 'native-reference-producer')
        assert cert == expected, s['name'] + ': complete native certificate differs'
        check_certificate(cert, ledger, 'native-certificate-replay')
        assert entry['baseline_decision'] == cert['decision']
        assert len(entry['baseline_layers']) == len(cert['layers'])
        for baseline, qlayer in zip(entry['baseline_layers'], cert['layers']):
            assert baseline['states'] == qlayer['states'] and baseline['index'] == qlayer['index']
        # Independently verify *every* pair edge of the matched native baseline.
        expected_count = 0
        for i, st in enumerate(s['stages']):
            edges = []
            for sr in cert['layers'][i]['states']:
                old = sr['state']
                prev = s['stages'][max(0, i-1)]
                actual = independent_convert(old[0], prev['acc_bits'], prev['acc_mode'])+old[1]
                for j, (x,y) in enumerate(st['pairs']):
                    ledger.charge('native-baseline-independent-edge')
                    exact_product = x*y
                    target = old[0]+exact_product
                    value = independent_convert(actual+independent_convert(exact_product, st['term_bits'], st['term_mode']), st['acc_bits'], st['acc_mode'])
                    error = value-independent_convert(target, st['acc_bits'], st['acc_mode'])
                    fail = (st['observe'] or (s['final_observe'] and i+1==len(s['stages']))) and error != 0
                    to = [target, error, old[2] or fail, i if fail and not old[2] else old[3]]
                    edges.append({'from': old, 'product': exact_product, 'representative_index': j, 'to': to})
            assert entry['baseline_layers'][i+1]['edges'] == edges
            expected_count += len(edges)
        assert entry['baseline_edges'] == expected_count == cert['metrics']['unquotiented_frontier_edges']
        words = entry['concrete']['traces']
        if entry['concrete']['whole_box_enumerated']:
            assert [w['indices'] for w in words] == [list(w) for w in product(*(range(len(st['pairs'])) for st in s['stages']))]
            oracle = run_oracle(s, ledger, 'native-independent-concrete-oracle')
            assert oracle['equivalent'] == cert['decision']['equivalent']
            cex=cert['decision']['least_counterexample']
            oc=oracle['least_counterexample']
            assert (None if cex is None else {k: cex[k] for k in ('indices','pairs','first_bad_stage')}) == oc
        for w in words:
            ledger.charge('native-trace-reference-word')
            assert w['steps'] == trace(s,w['indices']), s['name'] + ': concrete native trace differs'
        all_words += len(words)
        if s['name'] in original:
            original_q += cert['metrics']['quotient_frontier_edges']
            original_u += entry['baseline_edges']
            original_words += len(words)
        rows.append({'case': s['name'], 'quotient_edges': cert['metrics']['quotient_frontier_edges'],
                     'baseline_edges': entry['baseline_edges'], 'concrete_native_words': len(words),
                     'whole_box_enumerated': entry['concrete']['whole_box_enumerated'],
                     'complete_certificate_matches': True})
    assert (original_q, original_u, original_words)==(416,1016,5576)
    assert len(native['decoders'])==len(p['decoders'])
    full_dec_words = 0
    for e, d in zip(native['decoders'], p['decoders']):
        assert e['name']==d['name']
        cert=json.loads((ARTIFACT/'results/publication/main/decoder-certificates'/f"{d['name']}.json").read_text(encoding='utf-8'))
        assert e['equivalent']==cert['decision']['equivalent']
        assert e['max_carry_after_last_lane']==cert['closed_form']['max_carry_after_last_lane']
        if e['whole_box_enumerated']:
            assert [t['digits'] for t in e['traces']]==[list(t) for t in product(*(range(x+1) for x in d['maxima']))]
            full_dec_words += len(e['traces'])
        for t in e['traces']:
            ledger.charge('native-decoder-reference-word')
            w = sum(x << (8*i) for i,x in enumerate(t['digits']))
            multiplied = (w*d['scale']) % (256**len(d['maxima']))
            packed = sum((((multiplied >> (8*i)) & 255)+d['biases'][i]) % 256 << (8*i) for i in range(len(d['maxima'])))
            ref = sum((x*d['scale']+d['biases'][i]) % 256 << (8*i) for i,x in enumerate(t['digits']))
            assert (t['input_word'],t['packed_output'],t['reference_output']) == (w,packed,ref)
        decoder_words += len(e['traces'])
    assert full_dec_words==5120
    return {'format':'p053-native-semantic-comparison-v1', 'accumulator_cases':len(rows),
            'original_accumulator_cases':64, 'original_quotient_edges':original_q,
            'original_baseline_edges':original_u, 'original_native_accumulator_words':original_words,
            'all_native_accumulator_words':all_words, 'decoder_cases':len(p['decoders']),
            'original_full_decoder_words':full_dec_words, 'all_native_decoder_words':decoder_words,
            'disagreements':0, 'rows':rows}


def negative_inputs(out, exe, p):
    records = []
    cases = [
        ('product-overflow', 0, [2**62,4]),
        ('positive-prefix-overflow', 2**63-1, [1,1]),
        ('negative-prefix-overflow', -2**63, [-1,1]),
    ]
    for name, initial, pair in cases:
        bad = deepcopy(p); bad['accumulators']=bad['accumulators'][:1]; bad['decoders']=[]
        bad['accumulators'][0]['initial']=initial
        bad['accumulators'][0]['stages'][0]['pairs']=[pair]
        source=out/f'reject-{name}.txt';source.write_text(panel_text(bad),encoding='utf-8')
        target=out/f'reject-{name}.json'
        r=subprocess.run([str(exe),'conform',str(source),str(target)],capture_output=True,text=True,
                         env=environment(out),cwd=out,timeout=10)
        assert r.returncode==2 and 'outside int64 native subset' in r.stderr and not target.exists()
        records.append({'control':name,'exit_code':r.returncode,'stderr':r.stderr.strip(),'output_created':False})
    return records


def prepare(args):
    out=args.out.resolve();out.mkdir(parents=True,exist_ok=True)
    assert not (out/'conformance.json').exists(), 'refuse overwriting prior conformance'
    p=panel();dump(out/'panel.json',p);(out/'panel.txt').write_text(panel_text(p),encoding='utf-8')
    compiler_version=run([args.zig,'version'],out,'compiler-version').strip()
    commands=[]
    source=ARTIFACT/'native/native_bridge.cpp'
    common=[args.zig,'c++','-std=c++17','-target',args.target,'-Wall','-Wextra','-Wconversion','-Wno-sign-conversion']
    for label,flags in [('o3',['-O3','-DNDEBUG']),('checked',['-O0','-g','-ftrapv'])]:
        exe=out/f'native-{label}.exe';cmd=common+flags+[source,'-o',exe];commands.append(list(map(str,cmd)))
        run(cmd,out,f'compile-{label}',timeout=120)
        run([exe,'conform',out/'panel.txt',out/f'native-{label}.json'],out,f'conform-{label}',timeout=45)
    asm=out/'native-o3.s';cmd=common+['-O3','-DNDEBUG','-S','-masm=intel',source,'-o',asm]
    commands.append(list(map(str,cmd)));run(cmd,out,'assembly',timeout=120)
    ledger=ObligationLedger(100000)
    native=json.loads((out/'native-o3.json').read_text(encoding='utf-8'))
    checked=json.loads((out/'native-checked.json').read_text(encoding='utf-8'))
    assert native==checked, 'O3 and checked native executions differ'
    assert native['affinity']['verified_single_cpu'] and native['affinity']==checked['affinity']
    comparison=compare(native,p,ledger)
    negative=negative_inputs(out,out/'native-o3.exe',p)
    dump(out/'comparison.json',comparison);dump(out/'semantic-budget.json',ledger.to_dict())
    proof_sources=['bptc/exact_accumulator.py','bptc/accumulator_checker.py','bptc/accumulator_oracle.py',
                   'bptc/direct_state.py','bptc/packed_decoder.py','bptc/publication_cases.py']
    hashes={'native_source':digest(source),'harness':digest(Path(__file__)),
            'panel_json':digest(out/'panel.json'),'panel_text':digest(out/'panel.txt'),
            'binary_o3':digest(out/'native-o3.exe'),'binary_checked':digest(out/'native-checked.exe'),
            'assembly':digest(asm)}
    hashes.update({f'original:{f}':digest(ARTIFACT/f) for f in proof_sources})
    result={'format':'p053-native-readiness-v1','status':'READY_FOR_MEASUREMENT','performance_measured':False,
            'compiler':str(args.zig),'compiler_version':compiler_version,'compile_commands':commands,
            'python':sys.executable,'python_version':platform.python_version(),'os':platform.platform(),
            'cpu':platform.processor(),'affinity':native['affinity'],'native_target':args.target,
            'comparison':comparison,'negative_controls':negative,'hashes':hashes,
            'caps':{'native_event_limit_per_execution':2000000,'native_events_per_execution':native['charges'],
                    'reference_limit':ledger.limit,'reference_used':ledger.used,
                    'native_timeout_seconds':45,'oracle_words_per_plan_cap':10000,
                    'native_frontier_states_cap':50000,'native_graph_edges_cap':100000},
            'measurement_command':[sys.executable,str(Path(__file__)),'measure','--out',str(out),'--slot','COORDINATOR_RESERVED_SLOT'],
            'limits':['Reviewed local synthetic inputs only; no GPU, deployment or production claim.',
                      'Finite native int64 subset; overflowing products/prefixes rejected before semantic work.',
                      'No performance execution until explicit coordinator slot.',
                      'Main/supplement sources and existing scientific results unchanged; no PDFs built.',
                      'Exact page-count target requires coordinator integration/render audit.']}
    dump(out/'conformance.json',result);dump(out/'result.json',result)
    print(json.dumps({k:result[k] for k in ('status','performance_measured','caps')},indent=2))


def measure(args):
    out=args.out.resolve()
    readiness=json.loads((out/'conformance.json').read_text(encoding='utf-8'))
    assert args.slot and args.slot!='COORDINATOR_RESERVED_SLOT', 'actual assigned slot required'
    assert readiness['status']=='READY_FOR_MEASUREMENT' and not readiness['performance_measured']
    for key,path in [('native_source',ARTIFACT/'native/native_bridge.cpp'),('harness',Path(__file__)),
                     ('panel_json',out/'panel.json'),('panel_text',out/'panel.txt'),('binary_o3',out/'native-o3.exe')]:
        assert digest(path)==readiness['hashes'][key], f'conformance binding changed: {key}'
    # Only the human/coordinator should invoke this mode after assigning the slot.
    run([out/'native-o3.exe','measure',out/'panel.txt',out/'raw-samples.json',args.slot],out,'measurement',timeout=180)
    raw=json.loads((out/'raw-samples.json').read_text(encoding='utf-8'))
    assert raw['affinity']['verified_single_cpu'] and raw['affinity']['actual_mask_hex']==readiness['affinity']['actual_mask_hex']
    grouped=defaultdict(list)
    for s in raw['samples']:grouped[(s['kind'],s['case'])].append(s)
    rows=[]
    for (kind,case),samples in sorted(grouped.items()):
        assert len(samples)==21 and sorted(s['pair'] for s in samples)==list(range(21))
        if kind=='accumulator':
            q='quotient_ns';u='baseline_ns'
        else:q='packed_ns';u='reference_ns'
        ratios=[s[u]/s[q] for s in samples]
        row={'kind':kind,'case':case,'paired_samples':21,'median_paired_speedup':statistics.median(ratios),
             'min_paired_speedup':min(ratios),'max_paired_speedup':max(ratios),
             'optimized_median_ns_per_call':statistics.median(s[q]/s['batch'] for s in samples),
             'baseline_median_ns_per_call':statistics.median(s[u]/s['batch'] for s in samples),
             'optimized_slower':statistics.median(ratios)<1}
        if kind=='accumulator':
            for key in ('quotient_prepare_ns','baseline_prepare_ns','quotient_serialize_ns'):
                row[key+'_median_per_call']=statistics.median(s[key]/s['batch'] for s in samples)
            row['median_paired_prepare_plus_walk_speedup']=statistics.median(
                (s[u]+s['baseline_prepare_ns'])/(s[q]+s['quotient_prepare_ns']) for s in samples)
        rows.append(row)
    result={'format':'p053-native-measurement-summary-v1','slot':args.slot,'rows':rows,
            'affinity':raw['affinity'],
            'slower_cases':[r['case'] for r in rows if r['optimized_slower']],
            'scope':'Local x86-64 CPU-native execution of the declared synthetic panel only.',
            'checker_timing':'Not included in native traversal; certificate replay correctness recorded separately.',
            'raw_samples_sha256':digest(out/'raw-samples.json')}
    dump(out/'measurement-summary.json',result)
    print(json.dumps(result,indent=2))


def main():
    parser=argparse.ArgumentParser();parser.add_argument('mode',choices=['prepare','measure'])
    parser.add_argument('--out',type=Path,default=DEFAULT_OUT);parser.add_argument('--zig',type=Path)
    parser.add_argument('--target',default='x86_64-windows-gnu' if os.name=='nt' else 'x86_64-linux-gnu')
    parser.add_argument('--slot');args=parser.parse_args()
    if args.mode=='prepare':
        selected=str(args.zig) if args.zig is not None else shutil.which('zig')
        if not selected:parser.error('Zig compiler not found; supply --zig or put zig on PATH')
        args.zig=Path(selected).resolve()
    prepare(args) if args.mode=='prepare' else measure(args)


if __name__=='__main__':main()
