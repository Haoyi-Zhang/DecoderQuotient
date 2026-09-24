"""Concrete exhaustive oracle independent of the quotient producer/checker."""
from __future__ import annotations

from itertools import product
from typing import List, Tuple

from .publication_budget import ObligationLedger


def _clip_or_ring(value: int, width: int, mode: str) -> int:
    lower = -(1 << (width - 1))
    upper = (1 << (width - 1)) - 1
    if mode == "saturate":
        return lower if value < lower else upper if value > upper else value
    modulus = 1 << width
    unsigned = value % modulus
    return unsigned - modulus if unsigned >= (1 << (width - 1)) else unsigned


def run_oracle(spec: dict, ledger: ObligationLedger, category: str = "accumulator-oracle") -> dict:
    stages = spec["stages"]
    domains = [stage["pairs"] for stage in stages]
    total = 0
    failing = 0
    least_indices = None
    least_pairs = None
    least_first_bad = None

    for indices in product(*(range(len(domain)) for domain in domains)):
        ledger.charge(f"{category}:assignment")
        total += 1
        target = spec["initial"]
        lowered = _clip_or_ring(
            spec["initial"], stages[0]["acc_bits"], stages[0]["acc_mode"]
        )
        first_bad = None
        concrete_pairs: List[List[int]] = []
        for position, selected in enumerate(indices):
            stage = stages[position]
            left, right = stage["pairs"][selected]
            concrete_pairs.append([left, right])
            exact_product = left * right
            target += exact_product
            term = _clip_or_ring(exact_product, stage["term_bits"], stage["term_mode"])
            lowered = _clip_or_ring(
                lowered + term, stage["acc_bits"], stage["acc_mode"]
            )
            reference = _clip_or_ring(
                target, stage["acc_bits"], stage["acc_mode"]
            )
            observed = bool(stage["observe"]) or (
                bool(spec["final_observe"]) and position == len(stages) - 1
            )
            if observed and lowered != reference and first_bad is None:
                first_bad = position
        if first_bad is not None:
            failing += 1
            if least_indices is None or tuple(indices) < tuple(least_indices):
                least_indices = list(indices)
                least_pairs = concrete_pairs
                least_first_bad = first_bad

    return {
        "equivalent": failing == 0,
        "assignments": total,
        "failing_assignments": failing,
        "least_counterexample": None
        if least_indices is None
        else {
            "indices": least_indices,
            "pairs": least_pairs,
            "first_bad_stage": least_first_bad,
        },
    }
