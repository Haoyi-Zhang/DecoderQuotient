#!/usr/bin/env python3
"""Validate retained native samples and derive publication inputs; no timing.

SPDX-License-Identifier: MIT; original material covered by ../LICENSE.
"""
from __future__ import annotations
import argparse
from collections import defaultdict
from copy import deepcopy
import hashlib
import gzip
import json
from pathlib import Path
import statistics

ARTIFACT=Path(__file__).resolve().parents[1]


def load(path):
    def pairs(items):
        d={}
        for k,v in items:
            if k in d:raise ValueError('duplicate JSON member '+k)
            d[k]=v
        return d
    data=gzip.decompress(path.read_bytes()).decode('utf-8') if path.suffix=='.gz' else path.read_text(encoding='utf-8')
    return json.loads(data,object_pairs_hook=pairs,
                      parse_constant=lambda v: (_ for _ in ()).throw(ValueError(v)))


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def encoding(value):return json.dumps(value,indent=2,sort_keys=True,allow_nan=False)+'\n'


def analyze(root):
    panel=load(root/'panel.json')
    native_path=next(root/n for n in ('native-o3.json','native-conformance.json','native-conformance.json.gz') if (root/n).exists())
    native=load(native_path)
    raw=load(root/'raw-samples.json');saved=load(root/'measurement-summary.json')
    checker=load(root/'checker-samples.json');cs=load(root/'checker-summary.json')
    comparison=load(root/'comparison.json')
    assert checker['status']=='complete' and raw['slot']==saved['slot']==checker['slot']==cs['slot']
    assert raw['affinity']['actual_mask_hex']==checker['affinity']['actual_mask_hex']==native['affinity']['actual_mask_hex']
    assert raw['affinity']['verified_single_cpu'] and checker['affinity']['verified_single_cpu']
    specs={s['name']:s for s in panel['accumulators']}
    safe={d['name'] for d in native['decoders'] if d['equivalent']}
    assert len(specs)==79 and len(safe)==18 and comparison['disagreements']==0
    groups=defaultdict(list)
    for sample in raw['samples']:
        assert sample['batch']==16 and type(sample['pair']) is int and 0<=sample['pair']<21
        groups[(sample['kind'],sample['case'])].append(sample)
    assert set(groups)=={('accumulator',n) for n in specs}|{('decoder',n) for n in safe}
    saved_rows={(r['kind'],r['case']):r for r in saved['rows']}
    check_groups=defaultdict(list)
    for r in checker['samples']:check_groups[r['case']].append(r)
    assert set(check_groups)==set(specs)
    graph={r['case']:r for r in comparison['rows']}
    rows=[]
    for (kind,name),samples in sorted(groups.items()):
        samples.sort(key=lambda s:s['pair'])
        assert [s['pair'] for s in samples]==list(range(21))
        for s in samples:
            expected=('UQ','QU') if kind=='accumulator' else ('RP','PR')
            assert s['order']==expected[s['pair']%2]
            if kind=='decoder':assert s['words_per_batch']==1024
        q,u=('quotient_ns','baseline_ns') if kind=='accumulator' else ('packed_ns','reference_ns')
        assert all(type(s[q]) is int and type(s[u]) is int and s[q]>0 and s[u]>0 for s in samples)
        ratios=[s[u]/s[q] for s in samples]
        row=deepcopy(saved_rows[(kind,name)])
        assert row['median_paired_speedup']==statistics.median(ratios)
        assert row['min_paired_speedup']==min(ratios) and row['max_paired_speedup']==max(ratios)
        assert row['optimized_slower']==(statistics.median(ratios)<1)
        assert row['optimized_median_ns_per_call']==statistics.median(s[q]/s['batch'] for s in samples)
        assert row['baseline_median_ns_per_call']==statistics.median(s[u]/s['batch'] for s in samples)
        row['original_case']=not name.startswith('native-')
        row['slower_pair_count']=sum(r<1 for r in ratios)
        if kind=='accumulator':
            sums=[(s[u]+s['baseline_prepare_ns'])/(s[q]+s['quotient_prepare_ns']) for s in samples]
            assert row['median_paired_prepare_plus_walk_speedup']==statistics.median(sums)
            row['prepare_plus_walk_slower']=statistics.median(sums)<1
            row['prepare_plus_walk_min_pair_ratio']=min(sums)
            row['prepare_plus_walk_max_pair_ratio']=max(sums)
            row['quotient_edges']=graph[name]['quotient_edges'];row['baseline_edges']=graph[name]['baseline_edges']
            for key in ('quotient_prepare_ns','baseline_prepare_ns','quotient_serialize_ns'):
                assert row[key+'_median_per_call']==statistics.median(s[key]/s['batch'] for s in samples)
            row['median_paired_serialize_to_walk_ratio']=statistics.median(s['quotient_serialize_ns']/s[q] for s in samples)
            for key in ('stream_serialize_ns','quotient_fused_ns','stream_fused_ns'):
                assert all(type(s[key]) is int and s[key] > 0 for s in samples)
                row[key+'_median_per_call']=statistics.median(s[key]/s['batch'] for s in samples)
            for label,base,optimized in (
                ('serialize','stream_serialize_ns','quotient_serialize_ns'),
                ('fused','stream_fused_ns','quotient_fused_ns')):
                values=[s[base]/s[optimized] for s in samples]
                row[label+'_median_paired_speedup']=statistics.median(values)
                row[label+'_min_paired_speedup']=min(values)
                row[label+'_max_paired_speedup']=max(values)
                row[label+'_slower_pairs']=sum(x < 1 for x in values)
            checks=check_groups[name]
            assert sorted(c['sample'] for c in checks)==list(range(21)) and all(c['checker_ns']>0 for c in checks)
            row['median_checker_ns']=statistics.median(c['checker_ns'] for c in checks)
            assert row['median_checker_ns']==next(r['median_checker_ns'] for r in cs['rows'] if r['case']==name)
        rows.append(row)
    original=[r for r in rows if r['kind']=='accumulator' and r['original_case']]
    controls=[r for r in rows if r['kind']=='accumulator' and not r['original_case']]
    decoder=[r for r in rows if r['kind']=='decoder']
    def span(rs,key):return [min(r[key] for r in rs),max(r[key] for r in rs)]
    summary={'format':'p053-native-cpu-analysis-v1','slot':raw['slot'],'rows':rows,
             'case_counts':{'original_accumulator':len(original),'native_controls':len(controls),'safe_decoder':len(decoder)},
             'native_pairs':len(raw['samples']),'checker_samples':len(checker['samples']),
             'original_walk_case_median_range':span(original,'median_paired_speedup'),
             'original_prepare_plus_walk_case_median_range':span(original,'median_paired_prepare_plus_walk_speedup'),
             'safe_decoder_case_median_range':span(decoder,'median_paired_speedup'),
             'walk_slower_cases':[r['case'] for r in rows if r['optimized_slower']],
             'prepare_plus_walk_slower_cases':[r['case'] for r in rows if r.get('prepare_plus_walk_slower')],
             'original_serialization_to_walk_ratio_range':span(original,'median_paired_serialize_to_walk_ratio'),
             'original_serializer_speedup_range':span(original,'serialize_median_paired_speedup'),
             'original_fused_speedup_range':span(original,'fused_median_paired_speedup'),
             'serializer_slower_cases':[r['case'] for r in rows if r.get('serialize_median_paired_speedup',1)<1],
             'fused_slower_cases':[r['case'] for r in rows if r.get('fused_median_paired_speedup',1)<1],
             'original_checker_median_ns_range':span(original,'median_checker_ns'),
             'affinity':raw['affinity'],
             'component_sum_definition':'Median over pairs of (baseline walk + baseline preparation)/(quotient walk + quotient preparation), with components timed separately; not a fused end-to-end measurement.',
             'serialization_definition':'Buffered integer JSON versus ostream on the same frozen quotient graph; per-call buffer/stream allocation and output string materialization included, disk I/O excluded. Same field traversal and byte-identical output.',
             'fused_definition':'Separately timed preparation, quotient walk and full JSON materialization in one call, buffered versus ostream; no disk I/O or Python checker. Same quotient algorithm in both arms.',
             'scope':'One local x86-64 CPU, reviewed synthetic finite declarations and packed decoder examples only; no GPU or production deployment benefit.',
             'checker_obligations':checker['budget']['events_used']}
    assert len(original)==64 and len(controls)==15 and len(decoder)==18 and len(raw['samples'])==2037
    assert len(checker['samples'])==1659 and checker['budget']['events_used']==79266
    return summary


def tex_inputs(a):
    vals={'NativeOriginalCases':64,'NativeControlCases':15,'NativeSafeDecoderCases':18,
          'NativePairs':a['native_pairs'],'NativeCheckerSamples':a['checker_samples']}
    for macro,key in [('NativeWalk','original_walk_case_median_range'),('NativeSum','original_prepare_plus_walk_case_median_range'),('NativeDecoder','safe_decoder_case_median_range')]:
        vals[macro+'Min']=f'{a[key][0]:.3f}';vals[macro+'Max']=f'{a[key][1]:.3f}'
    vals['NativeSerializeRatioMin']=f"{a['original_serialization_to_walk_ratio_range'][0]:.1f}"
    vals['NativeSerializeRatioMax']=f"{a['original_serialization_to_walk_ratio_range'][1]:.1f}"
    vals['NativeCheckerUsMin']=f"{a['original_checker_median_ns_range'][0]/1000:.1f}"
    vals['NativeCheckerUsMax']=f"{a['original_checker_median_ns_range'][1]/1000:.1f}"
    for macro,key in [('NativeSerializer','original_serializer_speedup_range'),('NativeFused','original_fused_speedup_range')]:
        vals[macro+'Min']=f'{a[key][0]:.2f}';vals[macro+'Max']=f'{a[key][1]:.2f}'
    macros='% Derived from separately retained CPU-native samples; original publication inputs unchanged.\n'
    macros+=''.join('\\newcommand{\\'+k+'}{'+str(v)+'}\n' for k,v in vals.items())
    table='\\begin{tabular}{lrrr}\n\\toprule\nPanel & Cases & Walk ratio & Prep.+walk ratio \\\\\n\\midrule\n'
    table+='Original accumulator & 64 & '+f"{a['original_walk_case_median_range'][0]:.3f}--{a['original_walk_case_median_range'][1]:.3f}"+' & '+f"{a['original_prepare_plus_walk_case_median_range'][0]:.3f}--{a['original_prepare_plus_walk_case_median_range'][1]:.3f}"+' \\\\\n'
    for n in (4,8,16):
        r=next(r for r in a['rows'] if r['case']==f'native-scaling-{n}-unique')
        table+=f"Unique products, {n} stages & 1 & {r['median_paired_speedup']:.3f} & {r['median_paired_prepare_plus_walk_speedup']:.3f}"+' \\\\\n'
    table+='Safe decoder & 18 & '+f"{a['safe_decoder_case_median_range'][0]:.3f}--{a['safe_decoder_case_median_range'][1]:.3f}"+' & --- \\\\\n\\bottomrule\n\\end{tabular}\n'
    all_cases='{\\small\n\\begin{longtable}{lrrr}\n\\caption{CPU-native per-case median paired ratios. Accumulator sums use separately timed components; decoder rows compare packed and lane-wise batches.}\\label{tab:native-all}\\\\\n\\toprule Case & Walk/batch & Prep.+walk & Checker ($\\mu$s) \\\\\n\\midrule\\endfirsthead\n\\toprule Case & Walk/batch & Prep.+walk & Checker ($\\mu$s) \\\\ \\midrule\\endhead\n'
    for r in a['rows']:
        prep=f"{r['median_paired_prepare_plus_walk_speedup']:.3f}" if r['kind']=='accumulator' else '---'
        check=f"{r['median_checker_ns']/1000:.1f}" if r['kind']=='accumulator' else '---'
        all_cases+=r['case']+f" & {r['median_paired_speedup']:.3f} & {prep} & {check}"+' \\\\\n'
    all_cases+='\\bottomrule\\end{longtable}}\n'
    return {'native_cpu_macros.tex':macros,'native_cpu_summary.tex':table,'supplement_native_cases.tex':all_cases}


def export(args):
    src=args.results_dir.resolve();dst=args.out.resolve();paper=args.paper_dir.resolve()
    assert not dst.exists(),'refuse existing public evidence directory'
    a=analyze(src);conf=load(src/'conformance.json');private=load(src/'result.json')
    assert sha(ARTIFACT/'native/native_bridge.cpp')==conf['hashes']['native_source']
    assert sha(ARTIFACT/'native/bridge.py')==conf['hashes']['harness']
    dst.mkdir(parents=True)
    for name in ('panel.json','comparison.json','raw-samples.json','measurement-summary.json','checker-summary.json'):
        (dst/name).write_text(encoding(load(src/name)),encoding='utf-8')
    checker=load(src/'checker-samples.json');checker['python']=Path(checker['python']).name
    (dst/'checker-samples.json').write_text(encoding(checker),encoding='utf-8')
    # Preserve the complete concrete traces without expanding 12 MB of compact
    # native output into an unnecessarily large pretty-printed copy.
    (dst/'native-conformance.json').write_text((src/'native-o3.json').read_text(encoding='utf-8'),encoding='utf-8')
    public_summary=load(dst/'measurement-summary.json');public_summary['raw_samples_sha256']=sha(dst/'raw-samples.json')
    (dst/'measurement-summary.json').write_text(encoding(public_summary),encoding='utf-8')
    env={'format':'p053-native-cpu-environment-v1','cpu':private.get('cpu_name',conf['cpu']).split(' (')[0],
         'os':conf['os'],'compiler_driver':'Zig '+conf['compiler_version'],
         'compiler_backend':load(src/'raw-samples.json')['environment']['compiler'],'native_target':conf['native_target'],
         'optimization_flags':['-O3','-DNDEBUG'],'checked_flags':['-O0','-g','-ftrapv'],
         'affinity':a['affinity'],'python_version':checker['python_version'],
         'clock_frequency_controls':'Not modified; no fixed-frequency, thermal, or cross-host assumption.',
         'source_bindings':conf['hashes'],'native_certificate_schema':'bptc-exact-accumulator-certificate-v1',
         'public_normalization':['JSON indentation/key order/newlines normalized without changing sample values.',
                                 'Python executable stored by basename; exact machine path remains in private provenance.'],
         'private_raw_samples_sha256':sha(src/'raw-samples.json')}
    (dst/'environment.json').write_text(encoding(env),encoding='utf-8')
    wanted={'p053_convert','p053_advance','p053_packed','p053_lane_reference'}
    captured=[];active=False;done=set();current=None
    with (src/'native-o3.s').open(encoding='utf-8') as assembly:
        for line in assembly:
            name=line.split(':',1)[0]
            if name in wanted:
                active=True;current=name
            if active:
                line=line.replace(str(ARTIFACT/'native/native_bridge.cpp'),'native/native_bridge.cpp')
                line=line.replace(str(ARTIFACT/'native/native_bridge.cpp').replace('\\','/'),'native/native_bridge.cpp')
                # CodeView debug directives may contain escaped local paths.
                # These are instruction excerpts, not a standalone debug unit.
                if not line.lstrip().startswith('.cv_'):captured.append(line)
            if active and '.seh_endproc' in line:
                active=False;done.add(current)
                if done==wanted:break
    assert done==wanted
    (dst/'assembly-excerpts.txt').write_text('# Compiler-generated x86-64 function excerpts, not a standalone assembly unit.\n# CodeView debug/path directives omitted; executable instructions retained.\n'+''.join(captured),encoding='utf-8')
    a['public_raw_samples_sha256']=sha(dst/'raw-samples.json')
    (dst/'analysis.json').write_text(encoding(a),encoding='utf-8')
    for name,content in tex_inputs(a).items():
        target=paper/'generated'/name;assert not target.exists(),'refuse existing TeX input';target.write_text(content,encoding='utf-8')
    print(json.dumps({k:a[k] for k in ('native_pairs','checker_samples','walk_slower_cases','prepare_plus_walk_slower_cases','original_serialization_to_walk_ratio_range','original_checker_median_ns_range')},indent=2))


def compact_public(args):
    """One-time mechanical compaction of the already exported evidence.

    Private originals are read only. Complete native JSON is gzip-compressed,
    not summarized away; raw timer bytes are copied unchanged. No execution.
    """
    root=args.results_dir.resolve();src=args.private_records.resolve()
    assert not (root/'provenance.json').exists(),'refuse a second compaction'
    a=analyze(root)
    assert load(root/'raw-samples.json')==load(src/'raw-samples.json')
    native=load(root/'native-conformance.json')
    assert native==load(src/'native-o3.json')==load(src/'native-checked.json')
    (root/'raw-samples.json').write_bytes((src/'raw-samples.json').read_bytes())
    summary=load(root/'measurement-summary.json');summary['raw_samples_sha256']=sha(root/'raw-samples.json')
    (root/'measurement-summary.json').write_text(encoding(summary),encoding='utf-8')
    a['public_raw_samples_sha256']=sha(root/'raw-samples.json')
    (root/'analysis.json').write_text(encoding(a),encoding='utf-8')
    env=load(root/'environment.json')
    checked_hash=load(src/'result.json')['hashes']['checker_cost_source']
    assert checked_hash==sha(ARTIFACT/'native/checker_cost.py')
    env['source_bindings']['checker_cost_source']=checked_hash
    env['public_normalization']=[
        'Raw native timer bytes copied unchanged; all raw pairs retained.',
        'Other JSON indentation/key order/newlines normalized without changing scientific values.',
        'Complete native JSON compressed once with gzip; checked equal duplicate retained privately.',
        'Python executable stored by basename; machine paths and actual commands retained privately.']
    (root/'environment.json').write_text(encoding(env),encoding='utf-8')
    protocol=load(src/'protocol.json')
    public_protocol={k:protocol[k] for k in ('format','implementation','host','panel','paired_design','cost_components','limits','checker_limits')}
    public_protocol['status']='executed-protocol'
    public_protocol['slot']=a['slot']
    public_protocol['cost_components']['preparation']='Separate phase samples; reported preparation-plus-walk ratio sums paired phase times, not a timed fused end-to-end path. Serialization and Python checking excluded.'
    (root/'protocol.json').write_text(encoding(public_protocol),encoding='utf-8')
    plain=root/'native-conformance.json';body=plain.read_bytes()
    packed=gzip.compress(body,compresslevel=6,mtime=0)
    assert gzip.decompress(packed)==body
    (root/'native-conformance.json.gz').write_bytes(packed)
    assert plain.resolve().parent==root
    plain.unlink()  # Only the public duplicate; neither private build output is changed.
    sources={'native/native_bridge.cpp':env['source_bindings']['native_source'],
             'native/bridge.py':env['source_bindings']['harness'],
             'native/checker_cost.py':checked_hash,'native/report.py':sha(ARTIFACT/'native/report.py')}
    sources.update({k.split(':',1)[1]:v for k,v in env['source_bindings'].items() if k.startswith('original:')})
    assert all(sha(ARTIFACT/k)==v for k,v in sources.items())
    certs={}
    for entry in native['accumulators']:
        if not entry['name'].startswith('native-'):
            rel='results/publication/main/certificates/'+entry['name']+'.json'
            assert entry['quotient_certificate']==load(ARTIFACT/rel)
            certs[rel]=sha(ARTIFACT/rel)
    for entry in native['decoders']:
        rel='results/publication/main/decoder-certificates/'+entry['name']+'.json'
        assert entry['equivalent']==load(ARTIFACT/rel)['decision']['equivalent']
        certs[rel]=sha(ARTIFACT/rel)
    evidence={p.name:{'bytes':p.stat().st_size,'sha256':sha(p)} for p in sorted(root.iterdir()) if p.is_file() and p.name!='README.md'}
    provenance={'format':'p053-native-cpu-provenance-v1','scientific_sources':sources,
                'evidence_files':evidence,'retained_certificate_files':certs,
                'complete_native_output':{'file':'native-conformance.json.gz','uncompressed_bytes':len(body),
                    'uncompressed_sha256':hashlib.sha256(body).hexdigest(),
                    'private_optimized_output_sha256':sha(src/'native-o3.json'),
                    'private_checked_output_sha256':sha(src/'native-checked.json'),
                    'optimized_checked_json_equal':True},
                'raw_native_timer_bytes_unchanged':True,
                'original_result_aggregates_unchanged':True,
                'binding_scope':'Integrity/lineage binding, not a compiler proof or independent authorship claim.'}
    (root/'provenance.json').write_text(encoding(provenance),encoding='utf-8')
    for name,content in tex_inputs(a).items():
        (args.paper_dir/'generated'/name).write_text(content,encoding='utf-8')
    print(json.dumps({'files':{p.name:p.stat().st_size for p in sorted(root.iterdir()) if p.is_file()},'no_native_or_checker_execution':True},indent=2))


def main():
    p=argparse.ArgumentParser();p.add_argument('--results-dir',type=Path,required=True)
    p.add_argument('--out',type=Path,default=ARTIFACT/'results/native-cpu')
    p.add_argument('--paper-dir',type=Path,default=ARTIFACT.parent/'paper');p.add_argument('--check',action='store_true')
    p.add_argument('--compact-retained',action='store_true');p.add_argument('--private-records',type=Path)
    args=p.parse_args()
    if args.compact_retained:
        assert not args.check and args.private_records is not None
        compact_public(args);return
    if args.check:
        a=analyze(args.results_dir)
        retained=load(args.results_dir/'analysis.json')
        env=load(args.results_dir/'environment.json')
        provenance=load(args.results_dir/'provenance.json')
        assert all(sha(ARTIFACT/k)==v for k,v in provenance['scientific_sources'].items())
        assert all(sha(ARTIFACT/k)==v for k,v in provenance['retained_certificate_files'].items())
        for name,meta in provenance['evidence_files'].items():
            file=args.results_dir/name
            assert file.stat().st_size==meta['bytes'] and sha(file)==meta['sha256'],name
        body=gzip.decompress((args.results_dir/'native-conformance.json.gz').read_bytes())
        assert len(body)==provenance['complete_native_output']['uncompressed_bytes']
        assert hashlib.sha256(body).hexdigest()==provenance['complete_native_output']['uncompressed_sha256']
        assert sha(ARTIFACT/'native/native_bridge.cpp')==env['source_bindings']['native_source']
        assert sha(ARTIFACT/'native/bridge.py')==env['source_bindings']['harness']
        assert retained['rows']==a['rows'] and retained['public_raw_samples_sha256']==sha(args.results_dir/'raw-samples.json')
        assert load(args.results_dir/'measurement-summary.json')['raw_samples_sha256']==sha(args.results_dir/'raw-samples.json')
        for name,content in tex_inputs(a).items():assert (args.paper_dir/'generated'/name).read_text(encoding='utf-8')==content
        print('97 case statistics, 2037 raw pairs, 1659 checker samples, native source binding and TeX inputs checked; no performance rerun.')
    else:export(args)


if __name__=='__main__':main()
