#!/usr/bin/env python3
"""Portable CI cache-contract tests; compiler/native execution is always mocked.

SPDX-License-Identifier: MIT. Read only the current artifact's workflow and
resource-wrapper functions. No historical implementation, private path, timing,
network, scientific campaign, or global dependency is required.
"""
from __future__ import annotations

import ast
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import textwrap
import types
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / '.github/workflows/scientific-checks.yml'


def current_resource_wrappers():
    """Execute just the reviewed mkdir/subprocess wrappers, not scientific code."""
    tree = ast.parse((ROOT / 'native/bridge.py').read_text(encoding='utf-8'))
    wanted = ('dump', 'environment', 'run')
    functions = [node for node in tree.body
                 if isinstance(node, ast.FunctionDef) and node.name in wanted]
    if {node.name for node in functions} != set(wanted):
        raise ValueError('current bridge resource wrapper missing')
    namespace = dict(os=os, subprocess=subprocess, json=json)
    # The selected current functions were read; all process calls below are mocked.
    exec(compile(ast.Module(body=functions, type_ignores=[]),
                 'current bridge resource wrappers', 'exec'), namespace)
    return namespace


def warmup_source():
    workflow = WORKFLOW.read_text(encoding='utf-8')
    step = workflow.split('      - name: Populate the cold compiler cache with the optimized native build\n', 1)[1]
    step = step.split('      - name: Compile both native modes and check all declared semantics\n', 1)[0]
    source = step.split("          @'\n", 1)[1].split("          '@ | python -B -", 1)[0]
    return textwrap.dedent(source)


def warmup(resource, temporary, side_effect=None):
    package = types.ModuleType('native')
    package.__path__ = []
    module = types.ModuleType('native.bridge')
    module.environment = resource['environment']
    overrides = {'RUNNER_TEMP': str(temporary), 'ZIG_EXE': 'owned-compiler-with-spaces.exe',
                 'ZIG_GLOBAL_CACHE_DIR': 'wrong-parent-global-cache',
                 'ZIG_LOCAL_CACHE_DIR': 'wrong-parent-local-cache',
                 'TEMP': 'wrong-parent-temp', 'TMP': 'wrong-parent-tmp'}
    with patch.dict(sys.modules, {'native': package, 'native.bridge': module}), \
            patch.dict(os.environ, overrides), \
            patch.object(Path, 'cwd', return_value=ROOT), \
            patch.object(subprocess, 'run', side_effect=side_effect) as called:
        exec(compile(warmup_source(), 'current workflow cold-build step', 'exec'), {})
        return called.call_args


class CompilerCacheContract(unittest.TestCase):
    def test_exact_command_environment_cwd_and_finite_budgets(self):
        resource = current_resource_wrappers()
        with tempfile.TemporaryDirectory(prefix='p053 cache contract ') as temporary:
            temporary = Path(temporary)
            out = temporary / 'p053-native'
            actual = warmup(resource, temporary)
            command = ['owned-compiler-with-spaces.exe', 'c++', '-std=c++17', '-target',
                       'x86_64-windows-gnu', '-Wall', '-Wextra', '-Wconversion',
                       '-Wno-sign-conversion', '-O3', '-DNDEBUG',
                       str(ROOT / 'native/native_bridge.cpp'), '-o', str(out / 'native-o3.exe')]
            self.assertEqual(list(map(str, actual.args[0])), command)
            self.assertIs(actual.kwargs['check'], True)
            self.assertEqual(actual.kwargs['timeout'], 600)
            self.assertEqual(actual.kwargs['cwd'], out)
            # Independent literal resource contract, not equality of two implementations only.
            expected = {'PYTHONDONTWRITEBYTECODE': '1',
                        'ZIG_GLOBAL_CACHE_DIR': str(out / 'cache/global'),
                        'ZIG_LOCAL_CACHE_DIR': str(out / 'cache/local'),
                        'TEMP': str(out / 'tmp'), 'TMP': str(out / 'tmp')}
            for key, value in expected.items():
                self.assertEqual(actual.kwargs['env'][key], value)
            for relative in ('cache/global', 'cache/local', 'tmp'):
                self.assertTrue((out / relative).is_dir())
            completed = subprocess.CompletedProcess(command, 0, stdout='', stderr='')
            with patch.object(subprocess, 'run', return_value=completed) as compiled:
                resource['run'](command, out, 'mocked-compile', timeout=120)
            self.assertEqual(compiled.call_args.args[0], command)
            self.assertEqual(compiled.call_args.kwargs['cwd'], out)
            self.assertEqual(compiled.call_args.kwargs['timeout'], 120)
            for key, value in expected.items():
                self.assertEqual(compiled.call_args.kwargs['env'][key], value)

    def test_compiler_failure_and_timeout_are_not_suppressed(self):
        resource = current_resource_wrappers()
        with tempfile.TemporaryDirectory(prefix='p053 cache rejection ') as temporary:
            for error in (subprocess.CalledProcessError(2, ['owned-compiler']),
                          subprocess.TimeoutExpired(['owned-compiler'], 600)):
                with self.subTest(error=type(error).__name__):
                    with self.assertRaises(type(error)):
                        warmup(resource, Path(temporary), side_effect=error)

    def test_required_gates_and_native_modes_remain(self):
        workflow = WORKFLOW.read_text(encoding='utf-8')
        self.assertIn('timeout-minutes: 20', workflow.split('  native-correctness:\n', 1)[1])
        self.assertIn('          python -B tests/compiler_cache_regression.py\n', workflow)
        self.assertIn('          python -B tests/hoisting_regression.py\n', workflow)
        self.assertIn('          python -B tools/run_tests.py --ledger "$RAW/budget.json" --out "$RAW/tests.json"\n', workflow)
        self.assertIn('python -B native/bridge.py prepare --out "$env:RUNNER_TEMP/p053-native" --zig "$env:ZIG_EXE"', workflow)
        self.assertIn("throw 'Cold native compilation failed'", workflow)
        self.assertIn("throw 'Native conformance failed'", workflow)
        self.assertNotIn('continue-on-error:', workflow)
        tree = ast.parse((ROOT / 'native/bridge.py').read_text(encoding='utf-8'))
        prepare = next(node for node in tree.body
                       if isinstance(node, ast.FunctionDef) and node.name == 'prepare')
        modes = next(node for node in prepare.body if isinstance(node, ast.For))
        self.assertEqual(ast.literal_eval(modes.iter),
                         [('o3', ['-O3', '-DNDEBUG']), ('checked', ['-O0', '-g', '-ftrapv'])])
        calls = [node for node in ast.walk(prepare)
                 if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                 and node.func.id == 'run']
        deadlines = [ast.literal_eval(keyword.value) for node in calls
                     for keyword in node.keywords if keyword.arg == 'timeout']
        self.assertCountEqual(deadlines, [120, 45, 120])
        self.assertTrue(any(isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                            and node.func.id == 'compare' for node in ast.walk(prepare)))
        self.assertTrue(any(isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                            and node.func.id == 'negative_inputs' for node in ast.walk(prepare)))
        self.assertFalse(any(isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                             and node.func.id == 'measure' for node in ast.walk(prepare)))


if __name__ == '__main__':
    unittest.main(verbosity=2)
