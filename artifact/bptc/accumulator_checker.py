"""Independent replay checker for exact accumulator certificates.

This module intentionally reimplements integer casts and transitions instead
of importing the producer's transition function.
"""
from __future__ import annotations

from typing import Dict, List, Tuple

from .publication_budget import ObligationLedger
from .certificate_format import exact, keys, integer, boolean, text

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


def _stage_classes(stage: dict) -> List[dict]:
    pairs = [tuple(pair) for pair in stage["pairs"]]
    buckets: Dict[int, List[int]] = {}
    for position, pair in enumerate(pairs):
        if len(pair) != 2 or not all(type(value) is int for value in pair):
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
    is_observation = stage["observe"] or (
        final_observe and position == len(stages) - 1
    )
    new_failure = is_observation and error_new != 0
    if new_failure and not already_bad:
        first_bad = position
    return target_new, error_new, already_bad or new_failure, first_bad


def validate_spec(spec: dict) -> None:
    """Independent schema validation; does not construct producer dataclasses."""
    keys(spec, {"name", "initial", "final_observe", "provenance", "stages"}, "spec")
    text(spec["name"], "spec.name")
    text(spec["provenance"], "spec.provenance")
    integer(spec["initial"], "spec.initial")
    boolean(spec["final_observe"], "spec.final_observe")
    stages = spec["stages"]
    if type(stages) is not list or not 1 <= len(stages) <= 64:
        raise ValueError("requires 1..64 stages")
    for i, stage in enumerate(stages):
        keys(stage, {"pairs","term_bits","term_mode","acc_bits","acc_mode","observe"}, f"stage {i}")
        for field in ("term_bits", "acc_bits"):
            integer(stage[field], field, 2, 32)
        for field in ("term_mode", "acc_mode"):
            if type(stage[field]) is not str or stage[field] not in ("wrap", "saturate"):
                raise ValueError(f"invalid {field}")
        boolean(stage["observe"], "observe")
        pairs = stage["pairs"]
        if type(pairs) is not list or not 1 <= len(pairs) <= 4096:
            raise ValueError("requires 1..4096 pairs")
        seen = set()
        for pair in pairs:
            if type(pair) is not list or len(pair) != 2:
                raise ValueError("pair must be an integer pair")
            for v in pair: integer(v, "pair component")
            if tuple(pair) in seen: raise ValueError("duplicate pair")
            seen.add(tuple(pair))


def check_certificate(certificate: dict, ledger: ObligationLedger,
                      category_prefix: str = "accumulator-checker") -> dict:
    ledger.charge(f"{category_prefix}:schema")
    keys(certificate, {"format","spec","product_classes","layers","decision","metrics"}, "certificate")
    exact(certificate["format"], "bptc-exact-accumulator-certificate-v1", "format")
    spec = certificate["spec"]
    validate_spec(spec)
    stages = spec["stages"]
    classes = []
    for stage in stages:
        ledger.charge(f"{category_prefix}:partition-pair", len(stage["pairs"]))
        classes.append(_stage_classes(stage))
    initial = (spec["initial"], 0, False, -1)
    current = {initial: ()}
    reconstructed_layers = [{"index":0, "states":[{"state":list(initial), "least_witness_indices":[], "least_witness_pairs":[]}]}]
    transitions = 0
    unquotiented = 0
    concrete_assignments = 1
    product_sequences = 1
    for position, stage in enumerate(stages):
        concrete_assignments *= len(stage["pairs"])
        product_sequences *= len(classes[position])
        unquotiented += len(current) * len(stage["pairs"])
        following = {}
        edges = []
        for old_state, prefix in sorted(current.items(), key=lambda item:(item[0],item[1])):
            for product_class in classes[position]:
                ledger.charge(f"{category_prefix}:transition")
                transitions += 1
                new_state = _advance(old_state, product_class["product"], stages, position, spec["initial"], spec["final_observe"])
                candidate = prefix + (product_class["representative_index"],)
                if new_state not in following or candidate < following[new_state]:
                    following[new_state] = candidate
                edges.append({"from":list(old_state), "product":product_class["product"],
                              "representative_index":product_class["representative_index"], "to":list(new_state)})
        states = [{"state":list(state), "least_witness_indices":list(witness),
                   "least_witness_pairs":[stages[i]["pairs"][j] for i,j in enumerate(witness)]}
                  for state,witness in sorted(following.items(),key=lambda item:(item[0],item[1]))]
        reconstructed_layers.append({"index":position+1,"states":states,"edges":edges})
        current = following
    failures = [(w,s) for s,w in current.items() if s[2]]
    least = min(failures,default=None,key=lambda x:x[0])
    cex = None
    if least is not None:
        witness, state = least
        cex = {"indices":list(witness), "pairs":[stages[i]["pairs"][j] for i,j in enumerate(witness)],
               "first_bad_stage":state[3], "final_state":list(state)}
    decision = {"equivalent":least is None, "least_counterexample":cex,
                "reachable_final_states":len(current), "bad_final_states":len(failures)}
    metrics = {"concrete_assignments":concrete_assignments, "quotient_product_sequences":product_sequences,
               "producer_transitions":transitions, "unquotiented_frontier_edges":unquotiented,
               "quotient_frontier_edges":transitions}
    expected = {"format":"bptc-exact-accumulator-certificate-v1", "spec":spec, "product_classes":classes,
                "layers":reconstructed_layers,"decision":decision,"metrics":metrics}
    exact(certificate, expected)
    return {"accepted":True,"equivalent":least is None,"checked_transitions":transitions,
            "reachable_final_states":len(current), "bad_final_states":len(failures), "metrics":metrics}
