"""Execute one BPTC scientific module under a hard conservative event budget.

The meter charges, before execution, every Python function call, ``FOR_ITER``
opcode, and backward jump whose source file is in ``bptc/``.  Metering support
files themselves are excluded to avoid recursive self-counting.  These events
strictly over-approximate the declared proof/mutation/synthesis/replay work in
the two bounded confirmatory modules used by the final artifact.
"""
from __future__ import annotations

import argparse
import dis
import json
import os
import resource
import runpy
import sys
import time
from pathlib import Path
from types import FrameType
from typing import Callable

from .budget import BudgetExceeded, ObligationBudget, activate_hard_meter


_PACKAGE_ROOT = Path(__file__).resolve().parent
_EXCLUDED = {Path(__file__).resolve(), (_PACKAGE_ROOT / "budget.py").resolve()}
_JUMP_OPS = set(dis.hasjabs) | set(dis.hasjrel)


def _positive_cli_int(value: str) -> int:
    try:
        parsed = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("expected an integer") from exc
    if parsed <= 0:
        raise argparse.ArgumentTypeError("value must be positive")
    return parsed


def _safe_arg(value: str, artifact_root: Path) -> str:
    """Keep command provenance without embedding private absolute paths."""
    try:
        path = Path(value)
        if path.is_absolute():
            resolved = path.resolve()
            if resolved == artifact_root or artifact_root in resolved.parents:
                return str(resolved.relative_to(artifact_root)) or "."
            return f"<external:{resolved.name}>"
    except (OSError, ValueError):
        pass
    return value


def _instruction_map(code) -> dict[int, dis.Instruction]:
    return {instruction.offset: instruction for instruction in dis.get_instructions(code)}


def _is_target(filename: str) -> bool:
    try:
        path = Path(filename).resolve()
    except OSError:
        return False
    return path not in _EXCLUDED and (path == _PACKAGE_ROOT or _PACKAGE_ROOT in path.parents)


def _backward(instruction: dis.Instruction) -> bool:
    if instruction.opcode not in _JUMP_OPS:
        return False
    target = instruction.argval
    return isinstance(target, int) and target < instruction.offset


def _make_tracer(budget: ObligationBudget) -> Callable:
    cache: dict[object, dict[int, dis.Instruction]] = {}

    def trace(frame: FrameType, event: str, arg):
        if not _is_target(frame.f_code.co_filename):
            return None
        if event == "call":
            budget.reserve("python_function_call")
            frame.f_trace_opcodes = True
            return trace
        if event == "opcode":
            instructions = cache.get(frame.f_code)
            if instructions is None:
                instructions = _instruction_map(frame.f_code)
                cache[frame.f_code] = instructions
            instruction = instructions.get(frame.f_lasti)
            if instruction is not None:
                if instruction.opname == "FOR_ITER":
                    budget.reserve("for_iter")
                elif _backward(instruction):
                    budget.reserve("backward_jump")
            return trace
        return trace

    return trace


def _set_limits(cpu_seconds: int, address_space_mib: int) -> None:
    cpu_soft = int(cpu_seconds)
    cpu_hard = cpu_soft + 1
    resource.setrlimit(resource.RLIMIT_CPU, (cpu_soft, cpu_hard))
    address_space = int(address_space_mib) * 1024 * 1024
    current_soft, current_hard = resource.getrlimit(resource.RLIMIT_AS)
    hard = address_space if current_hard == resource.RLIM_INFINITY else min(current_hard, address_space)
    soft = min(address_space, hard)
    resource.setrlimit(resource.RLIMIT_AS, (soft, hard))


def _write_ledger(path: Path, record: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--module", required=True, choices=("bptc.focused", "bptc.closed_form"))
    parser.add_argument("--limit", required=True, type=_positive_cli_int)
    parser.add_argument("--ledger", required=True, type=Path)
    parser.add_argument("--cpu-seconds", type=_positive_cli_int, default=120)
    parser.add_argument("--address-space-mib", type=_positive_cli_int, default=2500)
    parser.add_argument("module_args", nargs=argparse.REMAINDER)
    args = parser.parse_args()

    if args.module_args[:1] == ["--"]:
        args.module_args = args.module_args[1:]
    artifact_root = Path(__file__).resolve().parents[1]
    ledger = args.ledger.resolve()
    budget = ObligationBudget(args.limit, label=args.module)
    started_wall = time.monotonic()
    started_cpu = time.process_time()
    status = "running"
    error: dict[str, object] | None = None
    exit_code = 0

    _set_limits(args.cpu_seconds, args.address_space_mib)
    old_argv = sys.argv[:]
    old_trace = sys.gettrace()
    sys.argv = [args.module, *args.module_args]
    tracer = _make_tracer(budget)
    try:
        with activate_hard_meter(budget):
            sys.settrace(tracer)
            runpy.run_module(args.module, run_name="__main__", alter_sys=False)
        status = "completed"
    except BudgetExceeded as exc:
        status = "budget_exceeded"
        error = {
            "type": type(exc).__name__,
            "message": str(exc),
            "requested": exc.requested,
            "category": exc.category,
        }
        exit_code = 3
    except SystemExit as exc:
        code = exc.code if isinstance(exc.code, int) else 1
        status = "completed" if code == 0 else "module_failed"
        exit_code = code
        if code:
            error = {"type": "SystemExit", "message": str(exc.code)}
    except Exception as exc:  # record then preserve a nonzero result
        status = "module_failed"
        error = {"type": type(exc).__name__, "message": str(exc)}
        exit_code = 2
    finally:
        sys.settrace(old_trace)
        sys.argv = old_argv
        usage = resource.getrusage(resource.RUSAGE_SELF)
        snapshot = budget.snapshot()
        record: dict[str, object] = {
            "schema": "bptc-hard-meter-v1",
            "module": args.module,
            "command_arguments": [_safe_arg(value, artifact_root) for value in args.module_args],
            "status": status,
            "scientific_execution": True,
            "workers": 1,
            "meter_policy": {
                "charged_before_execution": True,
                "events": ["python function call", "FOR_ITER", "backward jump"],
                "source_scope": "artifact/bptc excluding budget.py and metered_runner.py",
                "interpretation": "conservative upper bound on bounded confirmatory work",
            },
            "resource_limits": {
                "cpu_seconds": args.cpu_seconds,
                "address_space_mib": args.address_space_mib,
                "obligations": args.limit,
            },
            "budget": snapshot,
            "measurements": {
                "cpu_seconds": time.process_time() - started_cpu,
                "wall_seconds": time.monotonic() - started_wall,
                "peak_rss_kib": usage.ru_maxrss,
            },
            "error": error,
        }
        _write_ledger(ledger, record)
        print(json.dumps({"status": status, "budget": snapshot, "ledger": _safe_arg(str(ledger), artifact_root)}, sort_keys=True))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
