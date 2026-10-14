"""Benign native-domain, count-admission and result-publication regressions.

SPDX-License-Identifier: MIT. Native checks require supplied real executables;
no compiler installation, timing mode, historical-data update or GPU is used.
"""
from __future__ import annotations
import argparse
from copy import deepcopy
import gzip
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from native import bridge
from native.bridge import require
from bptc.exact_accumulator import AccumulatorSpec, StageSpec, generate_certificate, spec_to_dict
from bptc.accumulator_checker import check_certificate
from bptc.certificate_format import exact
from bptc.publication_budget import ObligationLedger

LOW, HIGH = -(2**63), 2**63-1


def schedule(name, pairs, count=1, initial=0):
    stage = StageSpec(tuple(pairs), 32, 'wrap', 32, 'wrap', False)
    return spec_to_dict(AccumulatorSpec(name, initial, (stage,)*count, True, 'native-admission-regression'))


def raw_text(spec):
    """Literal negative-control transport: intentionally bypass the adapter."""
    lines = ['p053-native-panel-v1 1 0',
             f"A {spec['name']} {spec['provenance']} {spec['initial']} {int(spec['final_observe'])} {len(spec['stages'])}"]
    for stage in spec['stages']:
        lines.append(f"S {stage['term_bits']} {stage['term_mode']} {stage['acc_bits']} {stage['acc_mode']} {int(stage['observe'])} {len(stage['pairs'])}")
        lines.extend(f'P {a} {b}' for a,b in stage['pairs'])
    return '\n'.join(lines)+'\n'


def as_spec(spec):
    return AccumulatorSpec(spec['name'], spec['initial'], tuple(
        StageSpec(tuple(map(tuple, s['pairs'])), s['term_bits'], s['term_mode'],
                  s['acc_bits'], s['acc_mode'], s['observe']) for s in spec['stages']),
        spec['final_observe'], spec['provenance'])


class AdapterAdmission(unittest.TestCase):
    def test_wide_zero_product_components_rejected_in_both_positions(self):
        for value in (LOW-1, HIGH+1, 2**80, -(2**80)):
            for pair in ((value,0), (0,value)):
                with self.subTest(pair=pair), self.assertRaisesRegex(ValueError, 'operand component'):
                    bridge.panel_text({'accumulators':[schedule('wide-zero', (pair,))], 'decoders':[]})

    def test_initial_and_strict_integer_admission(self):
        for initial in (LOW-1, HIGH+1):
            with self.assertRaisesRegex(ValueError, 'initial value'):
                bridge.validate_native_operands(schedule('wide-initial', ((0,0),), initial=initial))
        spec=schedule('strict', ((0,0),))
        for value in (True, 1.0):
            changed=deepcopy(spec);changed['stages'][0]['pairs'][0][0]=value
            with self.assertRaises(ValueError):bridge.validate_native_operands(changed)

    def test_valid_component_and_initial_endpoints(self):
        pairs=((LOW,0),(HIGH,0),(0,LOW),(0,HIGH))
        for initial in (LOW,0,HIGH):
            spec=schedule('valid-endpoints', pairs, initial=initial)
            bridge.validate_native_operands(spec)
            self.assertEqual(bridge.panel_text({'accumulators':[spec], 'decoders':[]}), raw_text(spec))

    def test_windows_ci_requires_both_real_builds_and_failure_gates(self):
        workflow=(ROOT/'.github/workflows/scientific-checks.yml').read_text(encoding='utf-8')
        native=workflow.split('  native-correctness:\n',1)[1]
        self.assertIn('runs-on: windows-2025',native)
        step=native.split('      - name: Run admission and publication controls on both real native builds\n',1)[1]
        step=step.split('      - name: ',1)[0]
        self.assertIn('python -B tests/native_admission_regression.py',step)
        self.assertEqual(step.count(' --exe '),2)
        self.assertEqual(step.count(' --conformance '),2)
        for mode in ('o3','checked'):
            self.assertIn(f'--exe "$env:RUNNER_TEMP/p053-native/native-{mode}.exe"',step)
            self.assertIn(f'--conformance "$env:RUNNER_TEMP/p053-native/native-{mode}.json"',step)
        self.assertIn("if ($LASTEXITCODE -ne 0) { throw 'Native admission/publication controls failed' }",step)
        self.assertIn('python -B native/bridge.py prepare --out "$env:RUNNER_TEMP/p053-native" --zig "$env:ZIG_EXE"',native)
        self.assertIn("throw 'Native conformance failed'",native)
        self.assertIn('python -B native/current_correctness.py --historical-project "$env:RUNNER_TEMP/p053-measured-native" --native-results "$env:RUNNER_TEMP/p053-native"',native)
        self.assertIn("throw 'Current native admission/source receipt failed'",native)
        self.assertIn('python -B "$measured/artifact/native/report.py" --results-dir "$measured/artifact/results/native-cpu" --paper-dir "$measured/paper" --check',workflow)
        self.assertNotIn('continue-on-error:',workflow)


def check_native(executables, work, conformance=()):
    """Execute bounded controls and compare supplied full current conformance."""
    work=Path(work).resolve()
    if work.exists():raise ValueError('use a fresh native regression directory')
    work.mkdir(parents=True)
    records=[]
    invalid=[('wide-zero', schedule('wide-zero', ((2**80,0),)), 'signed int64'),
             ('wide-zero-right', schedule('wide-zero-right', ((0,LOW-1),)), 'signed int64'),
             ('duplicate-count', schedule('duplicate-count', ((0,0),(0,1)), 63), 'assignment count'),
             ('unique-count', schedule('unique-count', ((0,0),(1,1)), 63), 'assignment count')]
    valid=[schedule('component-endpoints', ((LOW,0),(HIGH,0),(0,LOW),(0,HIGH))),
           schedule('product-endpoints', ((LOW,1),(HIGH,1))),
           schedule('initial-low', ((1,1),), initial=LOW),
           schedule('initial-high', ((-1,1),), initial=HIGH),
           schedule('duplicate-count-fit', ((0,0),(0,1)), 62),
           schedule('unique-count-fit', ((0,0),(1,1)), 62)]
    # Accepted arithmetic/count domain but one edge beyond the existing graph
    # cap: bounded to 100,001 edges, used only to exercise failure after staging.
    growing=schedule('graph-cap', ((0,0),))
    growing['stages']=[dict(pairs=[[0,0],[1,2**i]], term_bits=32, term_mode='wrap',
                            acc_bits=32, acc_mode='wrap', observe=False) for i in range(17)]

    for number, executable in enumerate(executables):
        executable=Path(executable).resolve()
        if not executable.is_file():raise ValueError('native executable missing: '+str(executable))
        folder=work/str(number);folder.mkdir()

        def execute(spec, name=None):
            name=name or spec['name']
            source=folder/(name+'.txt');source.write_text(raw_text(spec),encoding='utf-8')
            target=folder/(name+'.json')
            result=subprocess.run([str(executable),'conform',str(source),str(target)],
                capture_output=True,text=True,encoding='utf-8',cwd=folder,timeout=30)
            return result,target

        # Every proper token prefix is an incomplete declared panel. Test the
        # native parser directly, before a serializer can reject the input.
        complete = (
            'p053-native-panel-v1 1 1\n'
            'A prefix native-admission-regression 0 1 1\n'
            'S 8 wrap 8 wrap 1 1\nP 1 1\n'
            'D decoder native-admission-regression 1 1 1 0\n'
        ).split()
        for end in range(len(complete)):
            source = folder/f'truncated-{end}.txt'
            source.write_text(' '.join(complete[:end])+'\n', encoding='utf-8')
            target = folder/f'truncated-{end}.json'
            result = subprocess.run(
                [str(executable), 'conform', str(source), str(target)],
                capture_output=True, text=True, encoding='utf-8', cwd=folder,
                timeout=10)
            require(result.returncode == 2 and 'truncated' in result.stderr,
                    ('truncated panel prefix', end, result.returncode, result.stderr))
            require(not target.exists() and not Path(str(target)+'.partial').exists(),
                    'truncated panel must fail before result staging')
            records.append(dict(build=number, control=f'truncated-prefix-{end}',
                                rejected=True, final_output=False))

        for name,spec,diagnostic in invalid:
            result,target=execute(spec)
            require(result.returncode == 2 and diagnostic in result.stderr, (name, result.stderr))
            require(not target.exists() and (not Path(str(target) + '.partial').exists()), name)
            records.append(dict(build=number,control=name,rejected=True,final_output=False))
        for spec in valid:
            result,target=execute(spec)
            require(result.returncode == 0, result.stderr)
            actual=json.loads(target.read_text(encoding='utf-8'))['accumulators'][0]
            certificate=generate_certificate(as_spec(spec),ObligationLedger(200000))
            exact(actual['quotient_certificate'],certificate)
            check_certificate(actual['quotient_certificate'],ObligationLedger(200000))
            exact(actual['baseline_decision'],certificate['decision'])
            require(actual['baseline_edges'] == certificate['metrics']['unquotiented_frontier_edges'], 'native evidence condition failed')
            require(not Path(str(target) + '.partial').exists(), 'native evidence condition failed')
            records.append(dict(build=number,control=spec['name'],accepted=True,certificate_matches=True))
        result,target=execute(growing)
        require(result.returncode == 2 and 'per-graph size cap' in result.stderr, result.stderr)
        require(not target.exists() and (not Path(str(target) + '.partial').exists()), 'native evidence condition failed')
        records.append(dict(build=number,control='graph-cap',rejected=True,final_output=False))
        small=valid[0]
        result,target=execute(small,'no-overwrite')
        require(result.returncode == 0, result.stderr)
        original=target.read_bytes()
        result,again=execute(small,'no-overwrite')
        require(result.returncode == 2 and 'refuse output overwrite' in result.stderr, 'native evidence condition failed')
        require(again.read_bytes() == original, 'native evidence condition failed')
        records.append(dict(build=number,control='no-overwrite',existing_result_unchanged=True))
        staging=folder/'existing-staging.json.partial';staging.mkdir()
        marker=staging/'owned-by-earlier-run';marker.write_bytes(b'preserve')
        result,target=execute(small,'existing-staging')
        require(result.returncode == 2 and 'refuse staging overwrite' in result.stderr, 'native evidence condition failed')
        require(not target.exists() and marker.read_bytes() == b'preserve', 'native evidence condition failed')
        records.append(dict(build=number,control='existing-staging',existing_staging_unchanged=True))

    retained=json.loads(gzip.decompress((ROOT/'results/native-cpu/native-conformance.json.gz').read_bytes()))
    for source in conformance:
        current=json.loads(Path(source).read_text(encoding='utf-8'))
        for field in ('format','performance_measured','accumulators','decoders','charges','cap'):
            exact(current[field],retained[field],'unchanged native '+field)
        records.append(dict(control='retained-scientific-output',accumulator_certificates=79,
                            complete_baselines=79,decoder_configurations=30,unchanged=True))
    return records


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--exe',type=Path,action='append',default=[])
    parser.add_argument('--conformance',type=Path,action='append',default=[])
    parser.add_argument('--out',type=Path)
    args=parser.parse_args()
    result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(AdapterAdmission))
    if not result.wasSuccessful():return 1
    if args.exe:
        if args.out is None:parser.error('--exe requires a fresh --out directory')
        records=check_native(args.exe,args.out,args.conformance)
        (args.out/'controls.json').write_text(json.dumps(records,indent=2,sort_keys=True)+'\n',encoding='utf-8')
        print('Real native controls passed:',len(records),'records; no timing mode.')
    else:
        print('Python adapter controls passed; native execution not requested.')
    return 0


if __name__=='__main__':raise SystemExit(main())
