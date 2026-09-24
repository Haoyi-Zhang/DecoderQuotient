"""Independent replay checker for exact accumulator certificates.

This module intentionally reimplements integer casts and transitions instead
of importing the producer's transition function.
"""
from __future__ import annotations

from typing import Dict, List, Tuple

from .publication_budget import ObligationLedger

StateTuple = Tuple[int, int, bool, int]
Witness = Tuple[int, ...]


def _limits(width: int) -> Tuple[int, int]:
    return -(2 ** (width - 1)), 2 ** (width - 1) - 1


def _convert(number: int, width: int, policy: str) -> int:
    low, high = _limits(width)
    if policy == "saturate":
        if number < low:
            return low
        if number > high:
            return high
        return number
    if policy != "wrap":
        raise ValueError("unsupported conversion policy")
    ring = 2**width
    residue = number - (number // ring) * ring
    if residue >= 2 ** (width - 1):
        residue -= ring
    return residue


def _parse_state(raw: List[object]) -> StateTuple:
    if len(raw) != 4:
        raise ValueError("state must have four fields")
    target, error, bad, first_bad = raw
    if not isinstance(target, int) or not isinstance(error, int):
        raise ValueError("non-integer state")
    if not isinstance(bad, bool) or not isinstance(first_bad, int):
        raise ValueError("malformed state flags")
    return target, error, bad, first_bad


def _stage_classes(stage: dict) -> List[dict]:
    pairs = [tuple(pair) for pair in stage["pairs"]]
    buckets: Dict[int, List[int]] = {}
    for position, pair in enumerate(pairs):
        if len(pair) != 2 or not all(isinstance(value, int) for value in pair):
            raise ValueError("malformed operand pair")
        buckets.setdefault(pair[0] * pair[1], []).append(position)
    return [
        {
            "product": product,
            "representative_index": members[0],
            "representative_pair": list(pairs[members[0]]),
            "member_indices": members,
            "member_pairs": [list(pairs[index]) for index in members],
        }
        for product, members in sorted(buckets.items(), key=lambda item: item[1][0])
    ]


def _advance(
    old: StateTuple,
    product: int,
    stages: List[dict],
    position: int,
    initial: int,
    final_observe: bool,
) -> StateTuple:
    target, error, already_bad, first_bad = old
    if position == 0:
        prior_width = stages[0]["acc_bits"]
        prior_policy = stages[0]["acc_mode"]
    else:
        prior_width = stages[position - 1]["acc_bits"]
        prior_policy = stages[position - 1]["acc_mode"]
    lowered = _convert(target, prior_width, prior_policy) + error
    stage = stages[position]
    term = _convert(product, stage["term_bits"], stage["term_mode"])
    lowered_new = _convert(lowered + term, stage["acc_bits"], stage["acc_mode"])
    target_new = target + product
    reference_new = _convert(target_new, stage["acc_bits"], stage["acc_mode"])
    error_new = lowered_new - reference_new
    is_observation = bool(stage["observe"]) or (
        final_observe and position == len(stages) - 1
    )
    new_failure = is_observation and error_new != 0
    if new_failure and not already_bad:
        first_bad = position
    return target_new, error_new, already_bad or new_failure, first_bad


def check_certificate(
    certificate: dict,
    ledger: ObligationLedger,
    category_prefix: str = "accumulator-checker",
) -> dict:
    if certificate.get("format") != "bptc-exact-accumulator-certificate-v1":
        raise ValueError("unsupported certificate format")
    spec = certificate["spec"]
    stages = spec["stages"]
    if not stages:
        raise ValueError("empty accumulator")
    classes = [_stage_classes(stage) for stage in stages]
    if classes != certificate["product_classes"]:
        raise ValueError("product partition mismatch")

    first = stages[0]
    initial_ref = _convert(spec["initial"], first["acc_bits"], first["acc_mode"])
    initial: StateTuple = (spec["initial"], 0, False, -1)
    if initial_ref != _convert(spec["initial"], first["acc_bits"], first["acc_mode"]):
        raise AssertionError("unreachable")
    current: Dict[StateTuple, Witness] = {initial: ()}
    layers = certificate["layers"]
    if len(layers) != len(stages) + 1:
        raise ValueError("wrong layer count")

    expected_initial = [{"state": list(initial), "least_witness_indices": [], "least_witness_pairs": []}]
    if layers[0].get("states") != expected_initial:
        raise ValueError("initial layer mismatch")

    checked_transitions = 0
    for position, stage in enumerate(stages):
        successor_map: Dict[StateTuple, Witness] = {}
        expected_edges = []
        for old_state, old_witness in sorted(current.items(), key=lambda item: (item[0], item[1])):
            for product_class in classes[position]:
                ledger.charge(f"{category_prefix}:transition")
                checked_transitions += 1
                new_state = _advance(
                    old_state,
                    product_class["product"],
                    stages,
                    position,
                    spec["initial"],
                    bool(spec["final_observe"]),
                )
                candidate = old_witness + (product_class["representative_index"],)
                previous = successor_map.get(new_state)
                if previous is None or candidate < previous:
                    successor_map[new_state] = candidate
                expected_edges.append(
                    {
                        "from": list(old_state),
                        "product": product_class["product"],
                        "representative_index": product_class["representative_index"],
                        "to": list(new_state),
                    }
                )
        actual_layer = layers[position + 1]
        if actual_layer.get("edges") != expected_edges:
            raise ValueError(f"edge mismatch at layer {position + 1}")
        expected_states = []
        for state, witness in sorted(successor_map.items(), key=lambda item: (item[0], item[1])):
            expected_states.append(
                {
                    "state": list(state),
                    "least_witness_indices": list(witness),
                    "least_witness_pairs": [
                        stages[i]["pairs"][index] for i, index in enumerate(witness)
                    ],
                }
            )
        if actual_layer.get("states") != expected_states:
            raise ValueError(f"state or least-witness mismatch at layer {position + 1}")
        current = successor_map

    failures = [(witness, state) for state, witness in current.items() if state[2]]
    least = min(failures, default=None, key=lambda item: item[0])
    expected_equivalent = least is None
    decision = certificate["decision"]
    if decision.get("equivalent") is not expected_equivalent:
        raise ValueError("decision mismatch")
    if expected_equivalent:
        if decision.get("least_counterexample") is not None:
            raise ValueError("spurious counterexample")
    else:
        witness, state = least
        expected_counterexample = {
            "indices": list(witness),
            "pairs": [stages[i]["pairs"][index] for i, index in enumerate(witness)],
            "first_bad_stage": state[3],
            "final_state": list(state),
        }
        if decision.get("least_counterexample") != expected_counterexample:
            raise ValueError("least counterexample mismatch")

    return {
        "accepted": True,
        "equivalent": expected_equivalent,
        "checked_transitions": checked_transitions,
        "reachable_final_states": len(current),
    }
