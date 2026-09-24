#!/usr/bin/env python3
"""Standalone artifact acceptance without new scientific execution."""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path


def run(root: Path, command: list[str]) -> dict[str, object]:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(root)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    completed = subprocess.run(
        command,
        cwd=root,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    if completed.returncode:
        raise RuntimeError(f"command failed ({completed.returncode}): {' '.join(command)}\n{completed.stdout}")
    return {"command": command, "returncode": completed.returncode, "output": completed.stdout.strip()}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    default_root = Path(__file__).resolve().parents[1]
    parser.add_argument("--root", type=Path, default=default_root)
    parser.add_argument("--out", type=Path, default=default_root / "results/artifact-acceptance.json")
    args = parser.parse_args()
    root = args.root.resolve()
    commands = [
        [sys.executable, "tests/test_budget.py"],
        [sys.executable, "tests/static_integrity.py", "--out", "results/static-integrity-audit.json"],
        [sys.executable, "tests/reference_audit.py", "--bib", "evidence/references.bib", "--calibration", "literature-calibration.csv", "--out", "results/reference-audit.json", "--evidence-json", "evidence/reference-verification.json", "--evidence-tsv", "evidence/reference-verification.tsv"],
        [sys.executable, "tests/code_audit.py", "--root", ".", "--out", "results/code-audit.json"],
    ]
    results = [run(root, command) for command in commands]

    clean = root / "results/reproduced-clean"
    focused = json.loads((clean / "focused-budget.json").read_text(encoding="utf-8"))
    closed = json.loads((clean / "closed-form-budget.json").read_text(encoding="utf-8"))
    combined = json.loads((clean / "combined-budget.json").read_text(encoding="utf-8"))
    historical = json.loads((root / "results/campaign-accounting.json").read_text(encoding="utf-8"))
    assertions = {
        "hard_meter_runs_completed": focused["status"] == closed["status"] == "completed",
        "hard_meter_runs_below_individual_limits": all(
            record["budget"]["used"] <= record["resource_limits"]["obligations"]
            and record["measurements"]["cpu_seconds"] <= record["resource_limits"]["cpu_seconds"]
            and record["measurements"]["peak_rss_kib"] <= record["resource_limits"]["address_space_mib"] * 1024
            for record in (focused, closed)
        ),
        "hard_meter_runs_single_worker": focused["workers"] == closed["workers"] == combined["workers_max"] == 1,
        "hard_meter_charges_before_execution": focused["meter_policy"]["charged_before_execution"] is True and closed["meter_policy"]["charged_before_execution"] is True,
        "confirmatory_campaign_within_ceiling": combined["within_ceiling"] is True and combined["used"] == sum(combined["components"].values()) == 36880 and combined["ceiling"] == 200000,
        "historical_overrun_preserved": historical["conservative_atomic_check_lower_bound"] == 209282 and historical["ceiling_certified"] is False,
        "standalone_has_no_paper_dependency": not (root / "paper").exists(),
    }
    if not all(assertions.values()):
        raise AssertionError(assertions)

    report = {
        "audit_kind": "standalone artifact acceptance",
        "scientific_execution": False,
        "passed": True,
        "commands": results,
        "assertions": assertions,
        "summary": {
            "confirmatory_campaign_used": combined["used"],
            "confirmatory_campaign_ceiling": combined["ceiling"],
            "historical_full_campaign_lower_bound": historical["conservative_atomic_check_lower_bound"],
        },
    }
    out = args.out.resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"passed": True, "commands": len(results), "assertions": assertions}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (AssertionError, FileNotFoundError, KeyError, RuntimeError, TypeError, ValueError) as exc:
        print(f"artifact acceptance failed: {exc}", file=sys.stderr)
        raise SystemExit(2)
