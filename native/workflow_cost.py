#!/usr/bin/env python3
"""Same-contract native production, file publication, parsing and full replay.

SPDX-License-Identifier: MIT. Owned finite arithmetic only; no CUDA or network.
Historical records are never overwritten. Run serially in a new output path.
"""
from __future__ import annotations
import argparse
import ctypes
import gzip
import hashlib
import json
import os
from pathlib import Path
import platform
import statistics
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from native import bridge
from bptc.accumulator_checker import check_certificate, check_pair_certificate
from bptc.certificate_format import exact, strict_json_loads
from bptc.publication_budget import ObligationLedger
from native.workflow_context import measured_sources

require = bridge.require
SOURCES = ('native/workflow_cost.py', 'native/native_bridge.cpp', 'native/bridge.py',
           'bptc/accumulator_checker.py', 'bptc/certificate_format.py',
           'bptc/publication_budget.py', 'bptc/publication_cases.py')


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write(path, value):
    path.write_text(json.dumps(value, indent=2, sort_keys=True, allow_nan=False)+'\n',
                    encoding='utf-8', newline='\n')


def pin():
    if os.name == 'nt':
        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        kernel.GetCurrentProcess.restype = ctypes.c_void_p
        kernel.GetProcessAffinityMask.argtypes = [ctypes.c_void_p,
            ctypes.POINTER(ctypes.c_size_t), ctypes.POINTER(ctypes.c_size_t)]
        kernel.SetProcessAffinityMask.argtypes = [ctypes.c_void_p, ctypes.c_size_t]
        handle = kernel.GetCurrentProcess()
        allowed, system = ctypes.c_size_t(), ctypes.c_size_t()
        require(kernel.GetProcessAffinityMask(handle, ctypes.byref(allowed), ctypes.byref(system)),
                'query workflow affinity')
        mask = allowed.value & -allowed.value
        require(mask > 0 and kernel.SetProcessAffinityMask(handle, mask), 'pin workflow')
        actual = ctypes.c_size_t()
        require(kernel.GetProcessAffinityMask(handle, ctypes.byref(actual), ctypes.byref(system))
                and actual.value == mask, 'verify workflow affinity')
        return dict(original_mask=hex(allowed.value), actual_mask=hex(actual.value))
    allowed = os.sched_getaffinity(0)
    cpu = min(allowed)
    os.sched_setaffinity(0, {cpu})
    require(os.sched_getaffinity(0) == {cpu}, 'verify workflow affinity')
    return dict(original_cpus=sorted(allowed), actual_cpus=[cpu])


def consume(body, spec, arm, ledger):
    cert = strict_json_loads(body.decode('utf-8'))
    exact(cert['spec'], spec, 'workflow input binding')
    checker = check_certificate if arm == 'quotient' else check_pair_certificate
    result = checker(cert, ledger, 'workflow-'+arm)
    require(result['accepted'] is True, 'workflow replay must accept')
    return cert


def validate_samples(panel, samples, repetitions):
    names = [s['name'] for s in panel['accumulators']]
    require(len(names) == len(set(names)) == 79, 'complete declared panel required')
    require(len(samples) == len(names)*repetitions, 'workflow sample count')
    keys = set()
    for row in samples:
        require(row['case'] in names and type(row['pair']) is int and
                0 <= row['pair'] < repetitions, 'workflow sample identity')
        key = (row['case'], row['pair'])
        require(key not in keys, 'duplicate workflow pair')
        keys.add(key)
        exact(row['order'], ['pairs','quotient'] if row['pair']%2 == 0
              else ['quotient','pairs'], 'alternating workflow order')
        for arm in ('pairs','quotient'):
            entry = row[arm]
            for field in ('wall_ns','bytes','obligations'):
                require(type(entry[field]) is int and entry[field] > 0, 'workflow positive '+field)
            require(len(entry['sha256']) == 64, 'workflow output binding')
    exact(keys, {(n,i) for n in names for i in range(repetitions)}, 'complete paired panel')
    rows = []
    for spec in panel['accumulators']:
        selected = [s for s in samples if s['case'] == spec['name']]
        ratios = [s['pairs']['wall_ns']/s['quotient']['wall_ns'] for s in selected]
        rows.append(dict(case=spec['name'], original=not spec['name'].startswith('native-'),
                         median_ratio=statistics.median(ratios),
                         min_ratio=min(ratios), max_ratio=max(ratios),
                         quotient_slower_pairs=sum(r < 1 for r in ratios),
                         quotient_median_ns=statistics.median(s['quotient']['wall_ns'] for s in selected),
                         pairs_median_ns=statistics.median(s['pairs']['wall_ns'] for s in selected),
                         quotient_bytes=selected[0]['quotient']['bytes'],
                         pairs_bytes=selected[0]['pairs']['bytes']))
    return rows


def run(args):
    out = args.out.resolve()
    require(not out.exists(), 'new workflow output directory required')
    require(3 <= args.pairs <= 21 and args.pairs%2 == 1, 'odd repetition count 3..21')
    ready = json.loads((args.native_dir/'conformance.json').read_text(encoding='utf-8'))
    for key, rel in [('native_source','native/native_bridge.cpp'),('harness','native/bridge.py')]:
        exact(sha(ROOT/rel), ready['hashes'][key], 'source-bound native preparation')
    executable = args.native_dir.resolve()/'native-o3.exe'
    exact(sha(executable), ready['hashes']['binary_o3'], 'native binary binding')
    out.mkdir(parents=True)
    (out/'inputs').mkdir()
    (out/'raw').mkdir()
    affinity = pin()
    panel = bridge.panel()
    write(out/'panel.json', panel)
    if os.name == 'nt':
        command = ['powershell','-NoProfile','-Command',
            '[Console]::OutputEncoding=[Text.UTF8Encoding]::new($false); @{cpu=(Get-CimInstance Win32_Processor | Select-Object Name,NumberOfCores,NumberOfLogicalProcessors);os=(Get-CimInstance Win32_OperatingSystem | Select-Object Caption,Version,OSArchitecture)} | ConvertTo-Json -Depth 4 -Compress']
        machine = strict_json_loads(subprocess.check_output(command, encoding='utf-8', timeout=30))
    else:
        machine = dict(platform=platform.platform(), processor=platform.processor())
    write(out/'environment.json', dict(machine=machine, python=platform.python_version(),
          python_optimization=sys.flags.optimize, python_executable=sys.executable,
          compiler_version=ready['compiler_version'], target=ready['native_target'],
          compile_commands=ready['compile_commands'], affinity=affinity,
          clock=dict(implementation=time.get_clock_info('perf_counter').implementation,
                     resolution_seconds=time.get_clock_info('perf_counter').resolution,
                     monotonic=time.get_clock_info('perf_counter').monotonic),
          physical_memory_peak=None, frequency_and_thermals='uncontrolled',
          disk_durability='close and same-filesystem hard-link publication; no fsync/power-loss guarantee'))
    samples, packets = [], []
    for case_index, spec in enumerate(panel['accumulators']):
        source = out/'inputs'/f'{case_index:02d}.txt'
        source.write_text(bridge.panel_text(dict(accumulators=[spec], decoders=[])), encoding='utf-8')
        first_bytes = {}
        # One complete untimed warmup per arm, then every predeclared paired call.
        for repetition in range(-1, args.pairs):
            order = ['pairs','quotient'] if repetition%2 == 0 else ['quotient','pairs']
            row = dict(case=spec['name'], pair=repetition, order=order)
            certificates = {}
            for arm in order:
                target = out/'raw'/f'{case_index:02d}-{repetition}-{arm}.json'
                before = time.perf_counter_ns()
                ledger = ObligationLedger(200000)
                completed = subprocess.run([str(executable), 'emit-'+arm, str(source), str(target)],
                    cwd=out, env=bridge.environment(args.native_dir.resolve()),
                    capture_output=True, timeout=30)
                require(completed.returncode == 0, completed.stderr.decode('utf-8',errors='replace'))
                body = target.read_bytes()
                cert = consume(body, spec, arm, ledger)
                elapsed = time.perf_counter_ns()-before
                certificates[arm] = cert
                if arm not in first_bytes:
                    first_bytes[arm] = body
                    packets.append(dict(case=spec['name'], arm=arm, body_utf8=body.decode('utf-8')))
                exact(body, first_bytes[arm], 'deterministic emitted certificate')
                row[arm] = dict(wall_ns=elapsed, bytes=len(body),
                                sha256=hashlib.sha256(body).hexdigest(), obligations=ledger.used)
            exact(certificates['pairs']['decision'], certificates['quotient']['decision'], 'same decision')
            exact([l['states'] for l in certificates['pairs']['layers']],
                  [l['states'] for l in certificates['quotient']['layers']], 'same least-state witnesses')
            if repetition >= 0:
                samples.append(row)
                write(out/'samples.json', samples)  # Preserve all completed pairs on ordinary failure.
        print('workflow case',case_index+1,'of',len(panel['accumulators']),spec['name'],flush=True)
    packed = gzip.compress(json.dumps(packets,sort_keys=True,allow_nan=False).encode(),mtime=0)
    (out/'packets.json.gz').write_bytes(packed)
    protocol = dict(format='p053-complete-workflow-v1', repetitions=args.pairs, cases=79,
        warmups_per_arm=1, samples=len(samples),
        timed='Per-arm ledger creation, native process startup/input admission/product preparation/full evidence construction/serialization/file close/publication, parent wait/read/strict JSON parsing/input binding and complete semantic replay.',
        excluded='Compiler build, declaration file creation, environment collection, correctness warmups, result statistics, sample logging and post-call cross-arm equality. No persistent-service, cold-cache, fsync or hardware-counter claim.',
        source_sha256={p:sha(ROOT/p) for p in SOURCES},
        binary_sha256=sha(executable), panel_sha256=sha(out/'panel.json'),
        packets_sha256=sha(out/'packets.json.gz'), samples_sha256=sha(out/'samples.json'),
        environment_sha256=sha(out/'environment.json'),
        complete_measured_output_files=2*79*args.pairs,
        retained_warmup_and_timed_output_files=2*79*(args.pairs+1))
    write(out/'protocol.json', protocol)
    write(out/'summary.json', dict(rows=validate_samples(panel,samples,args.pairs), scope=protocol['timed']))
    check(out)


def check(out):
    p = strict_json_loads((out/'protocol.json').read_text(encoding='utf-8'))
    context = measured_sources(ROOT, p['source_sha256'], SOURCES)
    for name in ('panel','samples','packets','environment'):
        suffix = '.json.gz' if name == 'packets' else '.json'
        exact(sha(out/(name+suffix)), p[name+'_sha256'], 'workflow '+name+' binding')
    panel = strict_json_loads((out/'panel.json').read_text(encoding='utf-8'))
    exact(panel, bridge.panel(), 'workflow declared panel')
    samples = strict_json_loads((out/'samples.json').read_text(encoding='utf-8'))
    rows = validate_samples(panel, samples, p['repetitions'])
    exact(rows, strict_json_loads((out/'summary.json').read_text(encoding='utf-8'))['rows'], 'workflow statistics')
    packets = strict_json_loads(gzip.decompress((out/'packets.json.gz').read_bytes()).decode())
    require(len(packets) == 158, 'complete evidence pair packet count')
    seen = set()
    specs = {s['name']:s for s in panel['accumulators']}
    for packet in packets:
        key = (packet['case'], packet['arm'])
        require(key not in seen and key[0] in specs and key[1] in ('pairs','quotient'), 'packet identity')
        seen.add(key)
        body = packet['body_utf8'].encode('utf-8')
        cert = consume(body, specs[key[0]], key[1], ObligationLedger(200000))
        digest = hashlib.sha256(body).hexdigest()
        for sample in samples:
            if sample['case'] == key[0]:
                exact(sample[key[1]]['sha256'], digest, 'sample packet binding')
                exact(sample[key[1]]['bytes'], len(body), 'sample serialized byte count')
    print('workflow checked:',len(rows),'cases;',len(samples),'paired samples;',len(packets),'complete packets')
    print('Measured sources current:', context['measured_sources_are_current'])
    return context


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--native-dir', type=Path)
    parser.add_argument('--pairs', type=int, default=7)
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    if args.check: check(args.out)
    else:
        require(args.native_dir is not None, 'native preparation directory required')
        run(args)


if __name__ == '__main__':
    main()
