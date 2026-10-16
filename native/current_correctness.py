#!/usr/bin/env python3
"""Current Python/native correctness receipt; historical timings stay historical.

SPDX-License-Identifier: MIT. Supplied freshly compiled native binaries are
rerun for conformance and benign admission controls, never timing. The unchanged
original report --check must succeed in a separate measured-source context.
"""
from __future__ import annotations
import argparse
import gzip
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

ARTIFACT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ARTIFACT))
from native import report, bridge
from bptc.certificate_format import exact
from bptc.exact_accumulator import generate_certificate
from bptc.publication_budget import ObligationLedger
from tests.hoisting_regression import as_spec
from tests.native_admission_regression import check_native

CHANGED = {'bptc/exact_accumulator.py', 'bptc/accumulator_checker.py',
           'native/native_bridge.cpp', 'native/bridge.py', 'native/report.py',
           'native/checker_cost.py'}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def current_native(results):
    """Regenerate the current native context from source-bound real binaries."""
    results = results.resolve()
    ready = report.load(results/'conformance.json')
    require(ready['status'] == 'READY_FOR_MEASUREMENT' and ready['performance_measured'] is False,
            'fresh correctness-only native preparation required')
    paths = {'native_source':ARTIFACT/'native/native_bridge.cpp',
             'harness':ARTIFACT/'native/bridge.py',
             'panel_json':results/'panel.json', 'panel_text':results/'panel.txt',
             'binary_o3':results/'native-o3.exe', 'binary_checked':results/'native-checked.exe'}
    for key, path in paths.items():
        require(report.sha(path) == ready['hashes'][key], 'current native preparation binding: '+key)
    for key, digest in ready['hashes'].items():
        if key.startswith('original:'):
            require(report.sha(ARTIFACT/key.split(':',1)[1]) == digest,
                    'current native reference source binding: '+key)
    panel = report.load(results/'panel.json')
    exact(panel, bridge.panel(), 'current native declaration')
    with tempfile.TemporaryDirectory(prefix='current-conformance-',dir=results/'tmp') as temporary:
        temporary = Path(temporary)
        outputs = []
        executables = []
        for label in ('o3', 'checked'):
            executable = results/f'native-{label}.exe'
            target = temporary/f'native-{label}.json'
            run = subprocess.run([str(executable),'conform',str(results/'panel.txt'),str(target)],
                                 capture_output=True,text=True,timeout=45,
                                 env=bridge.environment(results),cwd=results)
            require(run.returncode == 0, 'current native conformance failed: '+run.stderr)
            outputs.append(target);executables.append(executable)
        native = report.load(outputs[0])
        exact(native, report.load(outputs[1]), 'current optimized/checked native execution')
        comparison = bridge.compare(native, panel, ObligationLedger(100000))
        controls = check_native(executables, temporary/'admission', outputs)
    return {'comparison':{k:v for k,v in comparison.items() if k != 'rows'},
            'admission_controls':controls,
            'scope':'Fresh execution of current source-bound native binaries, complete retained scientific-output equality and benign boundary controls; no timing.'}


def receipt(historical_project, native_results):
    historical = historical_project.resolve() / 'artifact'
    root = ARTIFACT / 'results/native-cpu'
    old_root = historical / 'results/native-cpu'
    require(historical != ARTIFACT, 'historical project must be a separate original checkout')
    provenance = report.load(root / 'provenance.json')
    require((root/'provenance.json').read_bytes() == (old_root/'provenance.json').read_bytes(),
            'historical native provenance was changed')
    bindings = {}
    for rel, old_hash in provenance['scientific_sources'].items():
        require(report.sha(historical/rel) == old_hash, 'historical source binding: '+rel)
        now = report.sha(ARTIFACT/rel)
        if rel not in CHANGED:
            require(now == old_hash, 'unsupported native source change: '+rel)
        bindings[rel] = {'historical':old_hash, 'current':now}
    require(CHANGED <= bindings.keys(), 'missing affected historical source bindings')
    # Run the unchanged, exact original verifier in its original source context.
    # No ignored hash, fallback verifier, or patched report module is used.
    checked = subprocess.run(
        [sys.executable, '-B', '-E', str(historical/'native/report.py'), '--results-dir',
         str(old_root), '--paper-dir', str(historical_project.resolve()/'paper'), '--check'],
        capture_output=True, text=True, timeout=60,
        env=dict(os.environ, PYTHONDONTWRITEBYTECODE='1'))
    require(checked.returncode == 0, 'historical report --check failed: '+checked.stderr)
    for rel, old_hash in provenance['retained_certificate_files'].items():
        require(report.sha(ARTIFACT/rel) == old_hash, 'retained certificate changed: '+rel)
    for name, meta in provenance['evidence_files'].items():
        path = root/name
        require(path.stat().st_size == meta['bytes'] and report.sha(path) == meta['sha256'],
                'retained evidence changed: '+name)
    body = gzip.decompress((root/'native-conformance.json.gz').read_bytes())
    meta = provenance['complete_native_output']
    require(len(body) == meta['uncompressed_bytes'], 'native uncompressed byte count')
    import hashlib
    require(hashlib.sha256(body).hexdigest() == meta['uncompressed_sha256'], 'native uncompressed binding')
    analysis = report.analyze(root)  # Recompute statistics; never measure them.
    exact(report.load(root/'analysis.json')['rows'], analysis['rows'])
    require(report.load(root/'analysis.json')['public_raw_samples_sha256'] == report.sha(root/'raw-samples.json'),
            'analysis raw sample binding')
    require(report.load(root/'measurement-summary.json')['raw_samples_sha256'] == report.sha(root/'raw-samples.json'),
            'measurement raw sample binding')
    env = report.load(root/'environment.json')
    require(report.sha(historical/'native/native_bridge.cpp') == env['source_bindings']['native_source'], 'measured native source binding')
    require(report.sha(historical/'native/bridge.py') == env['source_bindings']['harness'], 'measured native harness binding')
    for name, content in report.tex_inputs(analysis).items():
        require((ARTIFACT.parent/'paper/generated'/name).read_text(encoding='utf-8') == content,
                'retained TeX input changed: '+name)
    native = report.load(root/'native-conformance.json.gz')
    panel = report.load(root/'panel.json')
    exact(panel, bridge.panel(), 'current native panel')
    producer = ObligationLedger(100000)
    for entry, spec in zip(native['accumulators'], panel['accumulators']):
        exact(generate_certificate(as_spec(spec), producer, 'current-producer'),
              entry['quotient_certificate'], 'current ordered native certificate')
    replay = ObligationLedger(100000)
    comparison = bridge.compare(native, panel, replay)
    exact(comparison, report.load(root/'comparison.json'), 'current ordered native replay')
    native_check = current_native(native_results)
    # Literal regressions have their own finite counters, not the campaign ledger.
    reg = subprocess.run([sys.executable, '-B', str(ARTIFACT/'tests/hoisting_regression.py')],
                         capture_output=True, text=True, timeout=60,
                         env=dict(os.environ, PYTHONDONTWRITEBYTECODE='1'))
    require(reg.returncode == 0, 'literal regression failed: '+reg.stderr)
    sources = sorted(set(bindings) | {'native/current_correctness.py','tests/hoisting_regression.py',
        'native/materialize_measured_context.py','native/measured_native_sources.py',
        'tests/native_admission_regression.py', 'data/measured_reporting_sources.json',
        'native/workflow_cost.py', 'native/workflow_report.py',
        'native/workflow_context.py', 'data/workflow_measured_sources.json',
        'tests/test_workflow_context.py',
        'tests/test_native_consumer.py', 'tests/test_pair_replay.py'})
    return {
        'format':'p053-current-accumulator-correctness-v1',
        'scope':'Current Python replay and fresh source-bound native conformance/admission; original measurement sources and timings remain historical.',
        'historical_verifier':'Unchanged native/report.py --check in an explicit original project; all original gates required.',
        'historical_provenance_sha256':report.sha(root/'provenance.json'),
        'historical_sources':bindings,
        'current_sources':{rel:report.sha(ARTIFACT/rel) for rel in sources},
        'literal_regression_groups':3,
        'comparison':{k:v for k,v in comparison.items() if k != 'rows'},
        'current_producer_budget':producer.to_dict(), 'current_replay_budget':replay.to_dict(),
        'current_native':native_check,
        'measured_sources_are_current':False,
        'limitations':['Not a full campaign, compiler proof, deployment test, or timing rerun.',
                       'Historical checker-cost samples do not measure these changed Python sources.']}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--historical-project', type=Path, required=True)
    parser.add_argument('--native-results', type=Path, required=True,
                        help='fresh correctness-only native/bridge.py prepare output')
    parser.add_argument('--receipt', type=Path, default=ARTIFACT/'evidence/current-accumulator-correctness.json')
    parser.add_argument('--emit', action='store_true', help='print fresh JSON; do not write files')
    args = parser.parse_args()
    fresh = receipt(args.historical_project, args.native_results)
    if args.emit:
        print(json.dumps(fresh, indent=2, sort_keys=True))
    else:
        exact(report.load(args.receipt), fresh, 'current correctness receipt')
        print('Current Python/native receipt, fresh conformance/admission, literal regressions and all unchanged historical gates checked; no timings.')


if __name__ == '__main__':
    main()
