#!/usr/bin/env python3
"""Static code and data hygiene audit; does not execute scientific routines."""
from __future__ import annotations

import argparse
import ast
import csv
import json
import re
import sys
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    root_default = Path(__file__).resolve().parents[1]
    parser.add_argument("--root", type=Path, default=root_default)
    parser.add_argument("--out", type=Path, default=root_default / "results/code-audit.json")
    args = parser.parse_args()
    root = args.root.resolve()
    checks: list[dict[str, object]] = []

    def require(condition: bool, label: str) -> None:
        checks.append({"check": label, "passed": bool(condition)})
        if not condition:
            raise AssertionError(label)

    python_files = sorted((root / "bptc").glob("*.py")) + sorted((root / "tests").glob("*.py"))
    require(bool(python_files), "Python source inventory is nonempty")
    parsed: dict[Path, ast.AST] = {}
    for path in python_files:
        parsed[path] = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    require(len(parsed) == len(python_files), "all Python sources parse")

    forbidden_calls: list[str] = []
    absolute_private_paths: list[str] = []
    for path, tree in parsed.items():
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in {"eval", "exec"}:
                forbidden_calls.append(f"{path.name}:{node.lineno}:{node.func.id}")
            if isinstance(node, ast.Constant) and isinstance(node.value, str) and re.search(r"/(?:mnt/data|home/oai|tmp)/", node.value):
                absolute_private_paths.append(f"{path.name}:{node.lineno}")
    require(not forbidden_calls, "no eval/exec calls exist")
    require(not absolute_private_paths, "source contains no private absolute runtime paths")

    for name in ("focused.py", "closed_form.py", "campaign.py"):
        text = (root / "bptc" / name).read_text(encoding="utf-8")
        require("require_hard_meter()" in text, f"{name} rejects unmetered scientific execution")
    runner = (root / "bptc/metered_runner.py").read_text(encoding="utf-8")
    require("charged_before_execution" in runner and "budget.reserve" in runner, "hard meter charges before operations")
    require("choices=(\"bptc.focused\", \"bptc.closed_form\")" in runner, "hard meter only admits frozen confirmatory modules")

    json_files = sorted((root / "results").rglob("*.json")) + sorted((root / "evidence").rglob("*.json"))
    for path in json_files:
        json.loads(path.read_text(encoding="utf-8"))
    require(bool(json_files), "all retained JSON files parse")

    csv_files = sorted(root.rglob("*.csv")) + sorted(root.rglob("*.tsv"))
    for path in csv_files:
        delimiter = "\t" if path.suffix == ".tsv" else ","
        with path.open(newline="", encoding="utf-8") as handle:
            rows = list(csv.reader(handle, delimiter=delimiter))
        if rows:
            width = len(rows[0])
            require(all(len(row) == width for row in rows), f"{path.relative_to(root)} has consistent row widths")

    require(not list(root.rglob("__pycache__")), "artifact contains no Python bytecode cache directories")
    require(not list(root.rglob("*.pyc")), "artifact contains no compiled Python bytecode")
    require(not list(root.rglob("*.zip")), "standalone artifact contains no nested archives")

    report = {
        "audit_kind": "static code and data hygiene audit",
        "scientific_execution": False,
        "passed": True,
        "checks_passed": len(checks),
        "python_files": len(python_files),
        "json_files": len(json_files),
        "tabular_files": len(csv_files),
        "checks": checks,
    }
    args.out.resolve().parent.mkdir(parents=True, exist_ok=True)
    args.out.resolve().write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({k: report[k] for k in ("passed", "checks_passed", "python_files", "json_files", "tabular_files")}, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (AssertionError, FileNotFoundError, SyntaxError, json.JSONDecodeError, csv.Error) as exc:
        print(f"code audit failed: {exc}", file=sys.stderr)
        raise SystemExit(2)
