#!/usr/bin/env python3
"""Delivery-only integrity checks for retained BPTC evidence.

This script reads JSON/CSV files and validates identifiers and aggregate counts.
It deliberately does not import or invoke producer, checker, semantics, SMT,
or closed-form scientific implementations.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def require(condition: bool, message: str, checks: list[dict[str, Any]]) -> None:
    checks.append({"check": message, "passed": bool(condition)})
    if not condition:
        raise AssertionError(message)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--results",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "results",
        help="retained results directory",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="optional JSON output path",
    )
    args = parser.parse_args()
    results = args.results.resolve()
    checks: list[dict[str, Any]] = []

    cases = load_json(results / "cases.json")
    certificates = load_json(results / "certificates.json")
    metadata = load_json(results / "case_metadata.json")
    summary = load_json(results / "summary.json")
    smt = load_json(results / "smt_queries.json")
    oracle = load_json(results / "oracle.json")
    faults = load_json(results / "certificate_faults.json")
    focused = load_json(results / "focused.json")
    closed = load_json(results / "closed_form.json")
    accounting = load_json(results / "campaign-accounting.json")
    clean_dir = results / "reproduced-clean"
    clean_focused = load_json(clean_dir / "focused.json")
    clean_closed = load_json(clean_dir / "closed_form.json")
    focused_budget = load_json(clean_dir / "focused-budget.json")
    closed_budget = load_json(clean_dir / "closed-form-budget.json")
    pilot_accounting = load_json(clean_dir / "pilot-accounting.json")
    combined_budget = load_json(clean_dir / "combined-budget.json")

    with (results / "raw.csv").open(newline="", encoding="utf-8") as handle:
        raw = list(csv.DictReader(handle))

    require(len(cases) == 142, "cases.json contains 142 cases", checks)
    require(len(certificates) == 142, "certificates.json contains 142 certificates", checks)
    require(len(metadata) == 142, "case_metadata.json contains 142 rows", checks)
    require(len(raw) == 142, "raw.csv contains 142 rows", checks)

    case_ids = [row["id"] for row in cases]
    cert_ids = [row["binding"]["id"] for row in certificates]
    metadata_ids = [row["id"] for row in metadata]
    raw_ids = [row["id"] for row in raw]
    require(len(set(case_ids)) == 142, "case identifiers are unique", checks)
    require(case_ids == cert_ids == metadata_ids == raw_ids, "case identifiers and order agree across retained files", checks)

    stage_counts = Counter(row["stage"] for row in raw)
    expected_stages = {"accepted": 84, "decode": 48, "accumulation": 5, "layout": 5}
    require(dict(stage_counts) == expected_stages, "raw stage totals are 84/48/5/5", checks)
    require(summary["cases"] == 142, "summary case count is 142", checks)
    require(summary["stages"] == expected_stages, "summary stage totals match raw.csv", checks)
    require(sum(summary["stages"].values()) == summary["cases"], "summary stages partition all cases", checks)
    require(summary["decoder_valid"] == 94, "summary decoder-valid count is 94", checks)

    require(len(smt) == 120, "smt_queries.json contains 120 queries", checks)
    smt_counts = Counter(row["result"] for row in smt)
    require(dict(smt_counts) == {"unsat": 72, "sat": 48}, "SMT results are 72 UNSAT and 48 SAT", checks)
    require(all(row["result"] == row["expected"] for row in smt), "all retained SMT results equal their expected classification", checks)
    require(summary["smt_queries"] == 120, "summary SMT query count is 120", checks)
    require(summary["smt_results"] == {"sat": 48, "unsat": 72}, "summary SMT totals match query file", checks)
    require(summary["smt_disagreements"] == 0, "summary reports zero SMT disagreements", checks)

    require(len(oracle["rows"]) == 40, "oracle contains 40 schema rows", checks)
    require(oracle["assignments"] == 3570, "oracle assignment count is 3,570", checks)
    require(oracle["packing_checks"] == 416, "oracle packing check count is 416", checks)
    require(summary["oracle_cases"] == 40 and summary["oracle_assignments"] == 3570, "summary oracle counts match", checks)
    require(summary["packing_checks"] == 416, "summary packing count matches", checks)

    require(faults["rejected"] == 96, "certificate fault suite reports 96 rejections", checks)
    require(len(faults["rows"]) == 96, "certificate fault file contains 96 rows", checks)
    require(all(row["rejected"] is True for row in faults["rows"]), "every selected certificate alteration is rejected", checks)
    require(summary["certificate_faults"] == 96, "summary fault count matches", checks)

    require(focused["checks"] == 6 and len(focused["rows"]) == 6, "focused record contains six checks", checks)
    require(sum(1 for row in focused["rows"] if row.get("rejected") is True) == 5, "five focused malformed-type records are rejected", checks)
    saturation_rows = [row for row in focused["rows"] if row.get("check") == "saturation-not-necessary"]
    require(len(saturation_rows) == 1, "focused record contains the saturation boundary example", checks)
    sat = saturation_rows[0]
    require(sat["reference"] == 6 and sat["target"] == 6 and sat["stage"] == "accumulation", "saturation boundary ends at equal value 6 while contract fails", checks)

    require(closed["cases"] == 142 and len(closed["rows"]) == 142, "closed-form record covers 142 cases", checks)
    table_comparisons = sum(len(row["tables"]) for row in closed["rows"])
    require(table_comparisons == 147, "closed-form record contains 147 table comparisons", checks)
    require(closed["table_comparisons"] == 147, "closed-form aggregate table count matches", checks)
    require(closed["disagreements"] == 0, "closed-form comparator reports zero disagreements", checks)
    require(closed["enumeration_charge"] == 1051, "closed-form decision-call count is 1,051", checks)

    require(summary["whole_interpreter_replays"] == 300, "summary records 300 whole-word/dot-product replays", checks)
    require(summary["scalar_false_accepts"] == 25, "summary scalar-ablation false accepts equal 25", checks)
    require(summary["guard_false_rejects"] == 8, "summary strict-guard false rejects equal 8", checks)
    require(summary["max_certificate_bytes"] == 82534, "maximum compact certificate size is 82,534 bytes", checks)
    require(summary["max_states"] == 16, "maximum retained carry-state count is 16", checks)

    components = accounting["atomic_lower_bound_components"]
    recomputed_lower_bound = (
        components["intake"]
        + components["retained_primary"]
        + components["focused"]
        + components["closed_form"]
        + components["completed_case_loops"] * components["case_126_scalar_checks_per_completed_case_loop"]
    )
    require(recomputed_lower_bound == 209282, "accounting components recompute to 209,282", checks)
    require(accounting["conservative_atomic_check_lower_bound"] == 209282, "recorded accounting lower bound is 209,282", checks)
    require(accounting["enumeration_ceiling"] == 200000, "recorded enumeration ceiling is 200,000", checks)
    require(accounting["conservative_atomic_check_lower_bound"] > accounting["enumeration_ceiling"], "conservative lower bound exceeds the ceiling", checks)
    require(accounting["ceiling_certified"] is False, "historical resource ceiling is explicitly uncertified", checks)

    require(clean_focused == focused, "clean focused run matches the retained focused result exactly", checks)
    require(clean_closed == closed, "clean closed-form run matches the retained closed-form result exactly", checks)
    require(focused_budget["status"] == "completed" and closed_budget["status"] == "completed", "both hard-metered confirmatory runs completed", checks)
    require(focused_budget["module"] == "bptc.focused" and closed_budget["module"] == "bptc.closed_form", "hard-meter ledgers name the intended frozen modules", checks)
    require(focused_budget["budget"]["used"] == 4489, "focused hard meter records 4,489 conservative events", checks)
    require(closed_budget["budget"]["used"] == 13950, "closed-form hard meter records 13,950 conservative events", checks)
    require(focused_budget["budget"]["used"] == focused_budget["budget"]["category_sum"], "focused meter categories reconcile", checks)
    require(closed_budget["budget"]["used"] == closed_budget["budget"]["category_sum"], "closed-form meter categories reconcile", checks)
    require(focused_budget["budget"]["used"] <= focused_budget["resource_limits"]["obligations"] and closed_budget["budget"]["used"] <= closed_budget["resource_limits"]["obligations"], "each hard-metered run stays below its obligation limit", checks)
    require(focused_budget["workers"] == 1 and closed_budget["workers"] == 1 and pilot_accounting["workers"] == 1, "all confirmatory executions use one worker", checks)
    require(focused_budget["measurements"]["cpu_seconds"] <= focused_budget["resource_limits"]["cpu_seconds"] and closed_budget["measurements"]["cpu_seconds"] <= closed_budget["resource_limits"]["cpu_seconds"], "each retained run stays below its CPU-time limit", checks)
    require(focused_budget["measurements"]["peak_rss_kib"] <= focused_budget["resource_limits"]["address_space_mib"] * 1024 and closed_budget["measurements"]["peak_rss_kib"] <= closed_budget["resource_limits"]["address_space_mib"] * 1024, "each retained run stays below its address-space limit", checks)
    require(focused_budget["meter_policy"]["charged_before_execution"] is True and closed_budget["meter_policy"]["charged_before_execution"] is True, "both ledgers record pre-execution charging", checks)
    require(pilot_accounting["total_used"] == 18441, "pre-integration pilots retain 18,441 conservative events", checks)
    require(combined_budget["used"] == sum(combined_budget["components"].values()) == 36880, "complete confirmatory campaign components reconcile to 36,880 events", checks)
    measured_cpu = focused_budget["measurements"]["cpu_seconds"] + closed_budget["measurements"]["cpu_seconds"] + sum(run["cpu_seconds"] for run in pilot_accounting["runs"].values())
    measured_peak = max(focused_budget["measurements"]["peak_rss_kib"], closed_budget["measurements"]["peak_rss_kib"], *(run["peak_rss_kib"] for run in pilot_accounting["runs"].values()))
    require(abs(combined_budget["cpu_seconds_sum"] - measured_cpu) < 1e-9, "combined CPU total reconciles to all four executions", checks)
    require(combined_budget["peak_rss_kib_max"] == measured_peak, "combined peak RSS reconciles to all four executions", checks)
    require(combined_budget["within_ceiling"] is True and combined_budget["used"] <= combined_budget["ceiling"], "confirmatory campaign remains within 200,000-event ceiling", checks)
    require(combined_budget["nonclaim"].startswith("This does not rehabilitate"), "confirmatory ledger preserves the historical full-campaign nonclaim", checks)

    artifact_root = Path(__file__).resolve().parents[1]
    try:
        results_label = str(results.relative_to(artifact_root))
    except ValueError:
        results_label = results.name

    report = {
        "audit_kind": "delivery-only retained-file integrity audit",
        "scientific_execution": False,
        "results_directory": results_label,
        "passed": True,
        "checks_passed": len(checks),
        "checks": checks,
        "summary": {
            "cases": len(cases),
            "stages": expected_stages,
            "smt": {"total": len(smt), "unsat": 72, "sat": 48},
            "oracle_cases": 40,
            "oracle_assignments": 3570,
            "packing_checks": 416,
            "certificate_faults_rejected": 96,
            "closed_form_table_comparisons": 147,
            "closed_form_decision_calls": 1051,
            "historical_resource_lower_bound": 209282,
            "resource_ceiling": 200000,
            "confirmatory_campaign_used": 36880,
            "confirmatory_campaign_within_ceiling": True,
        },
    }

    if args.out is not None:
        out = args.out.resolve()
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"passed": True, "checks_passed": len(checks), "summary": report["summary"]}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (AssertionError, FileNotFoundError, KeyError, TypeError, ValueError) as exc:
        print(f"static integrity audit failed: {exc}", file=sys.stderr)
        raise SystemExit(2)
