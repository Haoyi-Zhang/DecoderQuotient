"""Portable literal-byte and absent-only admission tests, not a scientific oracle.

SPDX-License-Identifier: MIT. No private paths, historical implementation copy,
native execution, subprocess, file deletion or measured-result updates.
"""
import contextlib
import hashlib
import importlib.util
import io
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('context_copy', ROOT/'native/prepare_current_context.py')
helper = importlib.util.module_from_spec(spec)
spec.loader.exec_module(helper)
ABC = (3, 'ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad')


class Destination:
    """Test-local literal exclusive-creation filesystem; never touches disk."""
    def __init__(self, name, store, operations):
        self.name, self.store, self.operations = name, store, operations
        self.parent = self
    def mkdir(self, **kwargs):
        self.operations.append(('mkdir', self.name, kwargs))
    def open(self, mode):
        self.operations.append(('open', self.name, mode))
        if mode != 'xb' or self.name in self.store:
            raise FileExistsError(self.name)
        owner = self
        class Writer:
            def __enter__(self):
                owner.store[owner.name] = b''
                return self
            def write(self, body):
                owner.store[owner.name] += body
            def __exit__(self, *args):
                return False
        return Writer()


class ContextRegression(unittest.TestCase):
    def test_literal_byte_oracle_and_exact_three_declarations(self):
        self.assertEqual(hashlib.sha256(b'abc').hexdigest(), ABC[1])
        payload = b'abc'
        self.assertIs(helper.checked_bytes(payload, ABC), payload)
        self.assertEqual(set(helper.INPUTS), {'native_cpu_macros.tex', 'native_cpu_summary.tex', 'supplement_native_cases.tex'})
        self.assertEqual([value[0] for value in helper.INPUTS.values()], [837, 375, 5429])
        self.assertEqual(sum(value[0] for value in helper.INPUTS.values()), 6641)

    def test_byte_identity_and_type_rejections(self):
        for body, expected in [(b'ab', ABC), (b'abcd', ABC), (b'abd', ABC),
                               (bytearray(b'abc'), ABC), ('abc', ABC),
                               (b'abc', (True, ABC[1])), (b'abc', (-1, ABC[1])),
                               (b'abc', (3, '0'*64)), (b'abc', (3, ABC[1].upper()))]:
            with self.subTest(body=body, expected=expected), self.assertRaises(ValueError):
                helper.checked_bytes(body, expected)

    def test_all_destination_admission_before_input_read(self):
        with patch.object(helper, 'plain_path', side_effect=lambda p:Path(p).absolute()), \
             patch.object(Path, 'exists', side_effect=[False, True]), \
             patch.object(helper, 'read_input') as read:
            with self.assertRaisesRegex(ValueError, 'already exists'):
                helper.preflight(Path('historical'), Path('current/paper'))
            read.assert_not_called()

    def test_late_bad_input_cannot_start_writes(self):
        with patch.object(helper, 'plain_path', side_effect=lambda p:Path(p).absolute()), \
             patch.object(Path, 'exists', return_value=False), \
             patch.object(helper, 'read_input', side_effect=[b'first', ValueError('bad second')]), \
             patch.object(Path, 'mkdir') as mkdir, patch.object(Path, 'open') as opened:
            with self.assertRaisesRegex(ValueError, 'bad second'):
                helper.install_inputs(Path('historical'), Path('current/paper'))
            mkdir.assert_not_called()
            opened.assert_not_called()

    def test_exclusive_copy_literal_reference_and_repeat_refusal(self):
        store, operations = {}, []
        prepared = [(Destination(name, store, operations), body)
                    for name, body in [('a', b'abc'), ('b', b''), ('c', b'\x00\xff\n')]]
        with patch.object(helper, 'preflight', return_value=prepared), patch.object(helper, 'plain_path'):
            result = helper.install_inputs(None, None)
            self.assertEqual(store, {'a': b'abc', 'b': b'', 'c': b'\x00\xff\n'})
            self.assertEqual([r['bytes'] for r in result], [3, 0, 3])
            self.assertEqual([op[2] for op in operations if op[0]=='open'], ['xb']*3)
            snapshot = dict(store)
            with self.assertRaises(FileExistsError):
                helper.install_inputs(None, None)
            self.assertEqual(store, snapshot)

    def test_historical_destination_and_links_rejected(self):
        with patch.object(helper, 'plain_path', side_effect=lambda p:Path(p).absolute()), \
             patch.object(helper, 'read_input') as read:
            with self.assertRaisesRegex(ValueError, 'historical context'):
                helper.preflight(Path('historical'), Path('historical/paper'))
            read.assert_not_called()
        with patch.object(Path, 'is_symlink', return_value=True):
            with self.assertRaisesRegex(ValueError, 'linked'):
                helper.plain_path(Path('owned'))

    def test_cli_default_project_paper_and_explicit_destination(self):
        for extra, expected in [([], helper.ARTIFACT.parent/'paper'),
                                (['--paper-dir', 'owned/paper'], Path('owned/paper'))]:
            with patch.object(sys, 'argv', ['prepare', '--historical-project', 'historical']+extra), \
                 patch.object(helper, 'install_inputs', return_value=[]) as install, \
                 contextlib.redirect_stdout(io.StringIO()):
                helper.main()
            self.assertEqual(install.call_args.args, (Path('historical'), expected))


if __name__ == '__main__':
    unittest.main()
