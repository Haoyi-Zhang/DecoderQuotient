"""Prospective, deterministic publication campaign and clean reproduction."""
from __future__ import annotations

import argparse
import copy
import csv
import json
import resource
import time
from pathlib import Path
from typing import Dict, Iterable, List

from .accumulator_baselines import final_range_only, no_overflow_sufficient, term_fit_and_final_range
from .certificate_format import strict_json_loads
from .direct_state import solve as direct_solve
from .accumulator_checker import check_certificate
from .accumulator_oracle import run_oracle
from .exact_accumulator import generate_certificate
from .packed_decoder import (
    brute_force_decoder,
    check_decoder_certificate,
    generate_decoder_certificate,
)
from .publication_budget import ObligationLedger
from .publication_cases import accumulator_specs, decoder_specs
from .source_anchor import mutation_suite as source_mutation_suite
from .source_anchor import parse_frozen_file


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")


def _semantic_projection(value: object) -> object:
    if isinstance(value, dict):
        return {
            key: _semantic_projection(item)
            for key, item in sorted(value.items())
            if key not in {"run_label", "resource_usage"}
        }
    if isinstance(value, list):
        return [_semantic_projection(item) for item in value]
    return value


def _mutate_accumulator_certificate(certificate: dict, mutation: int) -> dict:
    changed = copy.deepcopy(certificate)
    kind = mutation % 5
    if kind == 0:
        changed["layers"][1]["edges"][0]["to"][1] += 1
    elif kind == 1:
        changed["product_classes"][0][0]["representative_index"] += 1
    elif kind == 2:
        changed["layers"][1]["states"][0]["least_witness_indices"][0] += 1
    elif kind == 3:
        changed["decision"]["equivalent"] = not changed["decision"]["equivalent"]
    else:
        changed["layers"][1]["states"].pop()
    return changed


def _mutate_decoder_certificate(certificate: dict, mutation: int) -> dict:
    changed = copy.deepcopy(certificate)
    kind = mutation % 4
    if kind == 0:
        changed["layers"][1]["edges"][0]["to"][0] += 1
    elif kind == 1:
        changed["layers"][1]["states"][0]["least_witness"][0] += 1
    elif kind == 2:
        changed["decision"]["equivalent"] = not changed["decision"]["equivalent"]
    else:
        changed["closed_form"]["equivalent"] = not changed["closed_form"]["equivalent"]
    return changed


def run_once(root: Path, out: Path, ledger: ObligationLedger, run_label: str,
             accumulator_suite=None, decoder_suite=None) -> dict:
    cpu_start = time.process_time()
    usage_start = resource.getrusage(resource.RUSAGE_SELF)
    if out.exists() and any(out.iterdir()):
        raise ValueError("result directory must be empty")
    out.mkdir(parents=True, exist_ok=True)
    certificate_dir = out / "certificates"
    decoder_dir = out / "decoder-certificates"
    certificate_dir.mkdir(exist_ok=True)
    decoder_dir.mkdir(exist_ok=True)

    source_path = root / "inputs" / "omniserve" / "share_to_reg_one_stage_B.cu"
    source_text = source_path.read_text()
    source_report = parse_frozen_file(source_path, ledger)
    source_mutations = source_mutation_suite(source_text, ledger)

    mutation_records = []
    accumulator_rows: List[dict] = []
    accumulator_certificates: List[dict] = []
    oracle_assignments = 0
    producer_transitions = 0
    checker_transitions = 0
    exact_equivalent = 0
    guard_false_rejects = 0
    final_false_accepts = 0
    oracle_disagreements = 0
    checker_disagreements = 0

    for spec in (accumulator_specs() if accumulator_suite is None else accumulator_suite):
        certificate = generate_certificate(spec, ledger, f"{run_label}:accumulator-producer")
        accumulator_certificates.append(certificate)
        checker = check_certificate(certificate, ledger, f"{run_label}:accumulator-checker")
        oracle = run_oracle(certificate["spec"], ledger, f"{run_label}:accumulator-oracle")
        direct = direct_solve(certificate["spec"], ledger, f"{run_label}:accumulator-direct")
        _write_json(out / "oracles" / f"{spec.name}.json", oracle)
        _write_json(out / "direct" / f"{spec.name}.json", direct)
        producer = certificate["decision"]
        if checker["equivalent"] != producer["equivalent"]:
            checker_disagreements += 1
        oracle_cex = oracle["least_counterexample"]
        producer_cex = producer["least_counterexample"]
        producer_prefix = None if producer_cex is None else {
            "indices": producer_cex["indices"],
            "pairs": producer_cex["pairs"],
            "first_bad_stage": producer_cex["first_bad_stage"],
        }
        if oracle["equivalent"] != producer["equivalent"] or oracle_cex != producer_prefix:
            oracle_disagreements += 1
        if direct["equivalent"] != producer["equivalent"] or direct["least_counterexample"] != producer_prefix:
            raise ValueError("unquotiented direct-state disagreement")
        if direct["reachable_final_states"] != checker["reachable_final_states"] or direct["transitions"] != checker["metrics"]["unquotiented_frontier_edges"]:
            raise ValueError("independent state/edge count disagreement")
        exact = producer["equivalent"]
        ledger.charge(f"{run_label}:baseline-pair",3*sum(len(st["pairs"]) for st in certificate["spec"]["stages"]))
        sufficient = no_overflow_sufficient(certificate["spec"])
        final_only = final_range_only(certificate["spec"])
        enhanced = term_fit_and_final_range(certificate["spec"])
        if sufficient and not exact:
            raise ValueError("sufficient guard accepted an inequivalent schedule")
        exact_equivalent += int(exact)
        guard_false_rejects += int(exact and not sufficient)
        final_false_accepts += int((not exact) and final_only)
        oracle_assignments += oracle["assignments"]
        producer_transitions += certificate["metrics"]["producer_transitions"]
        checker_transitions += checker["checked_transitions"]
        metrics = checker["metrics"]
        accumulator_rows.append(
            {
                "case": spec.name,
                "provenance": spec.provenance,
                "exact_equivalent": exact,
                "sufficient_guard": sufficient,
                "final_range_guard": final_only,
                "term_fit_final_guard": enhanced,
                "direct_dp_transitions": direct["transitions"],
                "direct_dp_equivalent": direct["equivalent"],
                "concrete_assignments": metrics["concrete_assignments"],
                "failing_assignments": oracle["failing_assignments"],
                "reachable_final_states": checker["reachable_final_states"],
                "quotient_edges": metrics["quotient_frontier_edges"],
                "unquotiented_edges": metrics["unquotiented_frontier_edges"],
                "edge_reduction": metrics["unquotiented_frontier_edges"] - metrics["quotient_frontier_edges"],
                "least_counterexample": producer_cex,
            }
        )
        _write_json(certificate_dir / f"{spec.name}.json", certificate)

    if oracle_disagreements or checker_disagreements:
        raise AssertionError("accumulator producer/checker/oracle disagreement")

    # Certificate mutation campaign: five failure modes across eight cases.
    accumulator_mutations = 0
    accumulator_mutations_rejected = 0
    for selected in accumulator_certificates[:8]:
        for mutation in range(5):
            accumulator_mutations += 1
            ledger.charge(f"{run_label}:accumulator-certificate-mutation")
            try:
                check_certificate(
                    _mutate_accumulator_certificate(selected, mutation),
                    ledger,
                    f"{run_label}:accumulator-mutant-checker",
                )
            except (ValueError, IndexError) as error:
                accumulator_mutations_rejected += 1
                mutation_records.append({"kind":"accumulator", "case":selected["spec"]["name"], "mutation":mutation, "rejected":True, "diagnostic":str(error)})
    if accumulator_mutations_rejected != accumulator_mutations:
        raise AssertionError("an accumulator certificate mutation escaped")

    decoder_rows: List[dict] = []
    decoder_certificates: List[dict] = []
    decoder_oracle_cases = 0
    decoder_oracle_assignments = 0
    decoder_disagreements = 0
    decoder_equivalent = 0
    for spec in (decoder_specs() if decoder_suite is None else decoder_suite):
        certificate = generate_decoder_certificate(spec, ledger, f"{run_label}:decoder-producer")
        decoder_certificates.append(certificate)
        checked = check_decoder_certificate(certificate, ledger, f"{run_label}:decoder-checker")
        oracle = None
        if certificate["metrics"]["concrete_assignments"] <= 4096:
            oracle = brute_force_decoder(spec, ledger, f"{run_label}:decoder-oracle")
            _write_json(out / "decoder-oracles" / f"{spec.name}.json", oracle)
            decoder_oracle_cases += 1
            decoder_oracle_assignments += oracle["assignments"]
            producer_cex = certificate["decision"]["least_counterexample"]
            if oracle["equivalent"] != certificate["decision"]["equivalent"]:
                decoder_disagreements += 1
            if producer_cex is not None:
                if oracle["least_counterexample"] is None or (
                    oracle["least_counterexample"]["digits"] != producer_cex["digits"]
                    or oracle["least_counterexample"]["first_bad_lane"] != producer_cex["first_bad_lane"]
                ):
                    decoder_disagreements += 1
        if checked["equivalent"] != certificate["decision"]["equivalent"]:
            decoder_disagreements += 1
        decoder_equivalent += int(certificate["decision"]["equivalent"])
        decoder_rows.append(
            {
                "case": spec.name,
                "provenance": spec.provenance,
                "scale": spec.scale,
                "maxima": list(spec.maxima),
                "equivalent": certificate["decision"]["equivalent"],
                "closed_form_equivalent": certificate["closed_form"]["equivalent"],
                "concrete_assignments": certificate["metrics"]["concrete_assignments"],
                "reachable_final_states": certificate["metrics"]["reachable_final_states"],
                "oracle_run": oracle is not None,
                "least_counterexample": certificate["decision"]["least_counterexample"],
            }
        )
        _write_json(decoder_dir / f"{spec.name}.json", certificate)
    if decoder_disagreements:
        raise AssertionError("decoder closed-form/DP/checker/oracle disagreement")

    decoder_mutations = 0
    decoder_mutations_rejected = 0
    for selected in decoder_certificates[:5]:
        for mutation in range(4):
            decoder_mutations += 1
            ledger.charge(f"{run_label}:decoder-certificate-mutation")
            try:
                check_decoder_certificate(
                    _mutate_decoder_certificate(selected, mutation),
                    ledger,
                    f"{run_label}:decoder-mutant-checker",
                )
            except (ValueError, IndexError) as error:
                decoder_mutations_rejected += 1
                mutation_records.append({"kind":"decoder", "case":selected["spec"]["name"], "mutation":mutation, "rejected":True, "diagnostic":str(error)})
    if decoder_mutations_rejected != decoder_mutations:
        raise AssertionError("a decoder certificate mutation escaped")

    with (out / "accumulator-cases.csv").open("w", newline="") as handle:
        fields = [
            "case", "provenance", "exact_equivalent", "sufficient_guard",
            "final_range_guard", "term_fit_final_guard", "direct_dp_transitions", "direct_dp_equivalent", "concrete_assignments", "failing_assignments",
            "reachable_final_states", "quotient_edges", "unquotiented_edges",
            "edge_reduction", "least_counterexample",
        ]
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in accumulator_rows:
            row = dict(row)
            row["least_counterexample"] = json.dumps(row["least_counterexample"], sort_keys=True)
            writer.writerow(row)
    with (out / "decoder-cases.csv").open("w", newline="") as handle:
        fields = [
            "case", "provenance", "scale", "maxima", "equivalent",
            "closed_form_equivalent", "concrete_assignments",
            "reachable_final_states", "oracle_run", "least_counterexample",
        ]
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in decoder_rows:
            row = dict(row)
            row["maxima"] = json.dumps(row["maxima"])
            row["least_counterexample"] = json.dumps(row["least_counterexample"], sort_keys=True)
            writer.writerow(row)

    total_unquotiented = sum(row["unquotiented_edges"] for row in accumulator_rows)
    total_quotient = sum(row["quotient_edges"] for row in accumulator_rows)
    summary = {
        "format": "bptc-publication-campaign-v1",
        "run_label": run_label,
        "source_anchor": {**source_report, "mutation_test": source_mutations},
        "decoder": {
            "cases": len(decoder_rows),
            "equivalent": decoder_equivalent,
            "inequivalent": len(decoder_rows) - decoder_equivalent,
            "oracle_cases": decoder_oracle_cases,
            "oracle_assignments": decoder_oracle_assignments,
            "cross_check_disagreements": decoder_disagreements,
            "certificate_mutations": decoder_mutations,
            "certificate_mutations_rejected": decoder_mutations_rejected,
        },
        "accumulator": {
            "cases": len(accumulator_rows),
            "equivalent": exact_equivalent,
            "inequivalent": len(accumulator_rows) - exact_equivalent,
            "oracle_assignments": oracle_assignments,
            "producer_transitions": producer_transitions,
            "checker_transitions": checker_transitions,
            "cross_check_disagreements": oracle_disagreements + checker_disagreements,
            "sufficient_guard_false_rejects": guard_false_rejects,
            "final_range_false_accepts": final_false_accepts,
            "term_fit_final_false_accepts": sum((not row["exact_equivalent"]) and row["term_fit_final_guard"] for row in accumulator_rows),
            "direct_dp_transitions": sum(row["direct_dp_transitions"] for row in accumulator_rows),
            "direct_dp_disagreements": 0,
            "unquotiented_frontier_edges": total_unquotiented,
            "quotient_frontier_edges": total_quotient,
            "edge_reduction": total_unquotiented - total_quotient,
            "edge_reduction_fraction": 0.0 if total_unquotiented == 0 else 1.0 - total_quotient / total_unquotiented,
            "certificate_mutations": accumulator_mutations,
            "certificate_mutations_rejected": accumulator_mutations_rejected,
        },
        "all_cross_checks_agree": True,
        "resource_usage": {
            "cpu_seconds": time.process_time() - cpu_start,
            "peak_rss_kib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
            "single_process": True,
            "workers": 1,
        },
    }
    _write_json(out / "mutations.json", mutation_records)
    _write_json(out / "source-report.json", {**source_report, "mutation_test":source_mutations})
    _write_json(out / "summary.json", summary)
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root",type=Path,default=Path("."))
    parser.add_argument("--out",type=Path,required=True)
    parser.add_argument("--label",choices=("main","reproduction"),required=True)
    parser.add_argument("--ledger",type=Path,required=True)
    parser.add_argument("--limit",type=int,default=200000)
    args=parser.parse_args()
    if not 1 <= args.limit <= 200000: raise ValueError("limit outside project ceiling")
    if args.ledger.exists():
        old=strict_json_loads(args.ledger.read_text())
        if old["limit"]!=args.limit:raise ValueError("ledger limit mismatch")
        ledger=ObligationLedger(args.limit,old["events_used"],old["categories"])
    else:ledger=ObligationLedger(args.limit)
    # Bound this single worker; no child or GPU execution is used.
    resource.setrlimit(resource.RLIMIT_AS,(int(2.5*1024**3),int(2.5*1024**3)))
    resource.setrlimit(resource.RLIMIT_CPU,(120,120))
    before=ledger.used
    try:
        summary=run_once(args.root.resolve(),args.out.resolve(),ledger,args.label)
        _write_json(args.out/"run-accounting.json",{"label":args.label,"events_before":before,"events_after":ledger.used,"events_this_run":ledger.used-before,"resource_usage":summary["resource_usage"]})
    finally:
        ledger.write(args.ledger)
    print(json.dumps({"out":str(args.out),"accumulator_cases":summary["accumulator"]["cases"],"decoder_cases":summary["decoder"]["cases"],"events_this_run":ledger.used-before,"events_cumulative":ledger.used}))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
