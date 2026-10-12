"""Actual Git checkout-byte regressions for the flat artifact repository.

SPDX-License-Identifier: MIT. Only private local Git/index fixtures are used.
No remote, compiler, native execution, campaign or performance measurement.
The original measured verifier is run unchanged, in check-only mode.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
PROVENANCE = json.loads((ROOT/'results/native-cpu/provenance.json').read_bytes())
RECEIPT = json.loads((ROOT/'evidence/current-accumulator-correctness.json').read_bytes())
ORACLE = 'bptc/accumulator_oracle.py'


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


class CheckoutByteFidelity(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(
            prefix='p', dir=os.environ.get('RUNNER_TEMP'))
        self.addCleanup(self.temporary.cleanup)
        self.work = Path(self.temporary.name).resolve()
        self.checkout_count = self.materialize_count = 0
        self.environment = dict(os.environ, PYTHONDONTWRITEBYTECODE='1',
                                GIT_CONFIG_NOSYSTEM='1', GIT_CONFIG_GLOBAL=os.devnull)
        for name in ('PYTHONOPTIMIZE', 'GIT_DIR', 'GIT_WORK_TREE', 'GIT_INDEX_FILE'):
            self.environment.pop(name, None)

    def run_command(self, command, cwd, expect=0):
        result = subprocess.run(list(map(str, command)), cwd=cwd,
                                env=self.environment, capture_output=True, timeout=60)
        if expect is not None:
            self.assertEqual(result.returncode, expect,
                             result.stderr.decode('utf-8', errors='replace'))
        return result

    def flat_checkout(self, label, protected, autocrlf):
        """Real index checkout, rooted exactly as actions/checkout artifact CI."""
        # Short fixture names also fit the long private Windows workspace path.
        number = self.checkout_count
        self.checkout_count += 1
        seed = self.work/('i'+str(number))
        seed.mkdir()
        files = set(PROVENANCE['scientific_sources']) | set(RECEIPT['current_sources'])
        files |= set(PROVENANCE['retained_certificate_files'])
        files |= {'results/native-cpu/provenance.json', 'data/measured_context.zip',
                  'evidence/current-accumulator-correctness.json'}
        files |= {'results/native-cpu/'+name for name in PROVENANCE['evidence_files']}
        if protected:
            files.add('.gitattributes')
        for name in sorted(files):
            source = (ROOT/name).resolve()
            self.assertTrue(source.is_relative_to(ROOT.resolve()), name)
            destination = seed/name
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, destination)
        git = ['git', '-c', 'core.safecrlf=false', '-c', 'core.longpaths=true']
        self.run_command(git+['init', '--quiet'], seed)
        # Index the supplied exact LF bytes without a checkout conversion.
        self.run_command(git+['-c', 'core.autocrlf=false', 'add', '--all'], seed)
        checkout = self.work/('p'+str(number))/'artifact'
        checkout.mkdir(parents=True)
        self.run_command(git+['-c', 'core.autocrlf='+autocrlf, 'checkout-index',
                              '--all', '--prefix='+checkout.as_posix()+'/'], seed)
        self.assertTrue((checkout/'bptc').is_dir())
        self.assertTrue((checkout/'native').is_dir())
        self.assertFalse((checkout/'artifact').exists())
        return seed, checkout, sorted(files)

    def materialize(self, checkout, name, expect=0):
        destination = self.work/('m'+str(self.materialize_count))
        self.materialize_count += 1
        result = self.run_command(
            [sys.executable, '-B', checkout/'native/materialize_measured_context.py',
             '--out', destination], checkout, expect)
        return destination, result

    def test_unprotected_windows_checkout_reproduces_source_failure(self):
        self.assertEqual(digest(ROOT/ORACLE), PROVENANCE['scientific_sources'][ORACLE])
        seed, checkout, _ = self.flat_checkout('unprotected', False, 'true')
        indexed = self.run_command(['git', 'show', ':'+ORACLE], seed).stdout
        original = (ROOT/ORACLE).read_bytes()
        self.assertEqual(indexed, original)  # Original Git blob did not change.
        self.assertNotIn(b'\r\n', original)
        converted = (checkout/ORACLE).read_bytes()
        self.assertEqual(converted, original.replace(b'\n', b'\r\n'))
        self.assertNotEqual(digest(checkout/ORACLE),
                            PROVENANCE['scientific_sources'][ORACLE])
        _, result = self.materialize(checkout, 'bad-measured', expect=None)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(b'Measured source context differs: '+ORACLE.encode(),
                      result.stderr)
        print('Observed unprotected oracle checkout:',
              json.dumps(dict(blob_sha256=hashlib.sha256(indexed).hexdigest(),
                              checkout_sha256=digest(checkout/ORACLE),
                              lf=original.count(b'\n'),
                              crlf=converted.count(b'\r\n')), sort_keys=True))

    def test_protected_flat_checkouts_preserve_all_bindings(self):
        for autocrlf in ('true', 'false'):
            with self.subTest(autocrlf=autocrlf):
                _, checkout, files = self.flat_checkout('protected-'+autocrlf,
                                                       True, autocrlf)
                # No normalized hash or LF/CRLF equivalence is accepted.
                for name in files:
                    self.assertEqual((checkout/name).read_bytes(),
                                     (ROOT/name).read_bytes(), name)
                for name, expected in RECEIPT['current_sources'].items():
                    self.assertEqual(digest(checkout/name), expected, name)
                restored, _ = self.materialize(checkout, 'measured-'+autocrlf)
                for name, expected in PROVENANCE['scientific_sources'].items():
                    self.assertEqual(digest(restored/'artifact'/name), expected, name)
                report = self.run_command(
                    [sys.executable, '-B', restored/'artifact/native/report.py',
                     '--results-dir', restored/'artifact/results/native-cpu',
                     '--paper-dir', restored/'paper', '--check'], checkout)
                self.assertIn(b'no performance rerun', report.stdout)
                print('Exact checkout/restoration bindings:', autocrlf,
                      len(files), 'files;', len(RECEIPT['current_sources']),
                      'current sources;', len(PROVENANCE['scientific_sources']),
                      'measured sources; unchanged historical report passed')

    def test_real_source_tamper_still_fails_measured_gate(self):
        _, checkout, _ = self.flat_checkout('tamper', True, 'true')
        source = checkout/ORACLE
        source.write_bytes(source.read_bytes()+b'# benign byte-tamper control\n')
        self.assertNotEqual(digest(source), RECEIPT['current_sources'][ORACLE])
        _, result = self.materialize(checkout, 'tampered-measured', expect=None)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(b'Measured source context differs: '+ORACLE.encode(),
                      result.stderr)

    def test_both_ci_layouts_require_checkout_regression(self):
        workflow = (ROOT/'.github/workflows/scientific-checks.yml').read_text(encoding='utf-8')
        linux = workflow.split('  retained-current-correctness:\n', 1)[1].split(
            '  native-correctness:\n', 1)[0]
        windows = workflow.split('  native-correctness:\n', 1)[1]
        self.assertIn('python -B project/artifact/tests/checkout_byte_regression.py', linux)
        self.assertIn('python -B tests/checkout_byte_regression.py', windows)
        self.assertIn("throw 'Checkout byte-fidelity regression failed'", windows)
        self.assertLess(windows.index('tests/checkout_byte_regression.py'),
                        windows.index('native/bridge.py prepare'))
        self.assertNotIn('continue-on-error:', workflow)


if __name__ == '__main__':
    unittest.main(verbosity=2)
