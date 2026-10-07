"""Exact producer for bounded mixed-width accumulator certificates.

The producer explores a quotient of each operand-pair domain by its exact
integer product.  It stores a target/error normal form and the least witness
under the domain order.  The checker lives in a separate module.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Dict, Iterable, List, Sequence, Tuple

from .publication_budget import ObligationLedger

Pair = Tuple[int, int]
Witness = Tuple[int, ...]


@dataclass(frozen=True)
class StageSpec:
    pairs: Tuple[Pair, ...]
    term_bits: int
    term_mode: str
    acc_bits: int
    acc_mode: str
    observe: bool = False

    def __post_init__(self) -> None:
        if type(self.pairs) is not tuple or not 1 <= len(self.pairs) <= 4096:
            raise ValueError("a stage requires 1..4096 ordered operand pairs")
        if any(type(p) is not tuple or len(p) != 2 or any(type(x) is not int for x in p) for p in self.pairs):
            raise ValueError("pairs require strict integers")
        if len(set(self.pairs)) != len(self.pairs):
            raise ValueError("operand pairs must be unique")
        if any(type(w) is not int or not 2 <= w <= 32 for w in (self.term_bits, self.acc_bits)):
            raise ValueError("bit widths must be integers in 2..32")
        if self.term_mode not in {"wrap", "saturate"} or self.acc_mode not in {"wrap", "saturate"}:
            raise ValueError("unknown conversion mode")
        if type(self.observe) is not bool:
            raise ValueError("observation must be Boolean")


@dataclass(frozen=True)
class AccumulatorSpec:
    name: str
    initial: int
    stages: Tuple[StageSpec, ...]
    final_observe: bool = True
    provenance: str = "systematic"

    def __post_init__(self) -> None:
        if type(self.name) is not str or not self.name or type(self.provenance) is not str or not self.provenance:
            raise ValueError("name and provenance are required")
        if type(self.stages) is not tuple or not 1 <= len(self.stages) <= 64 or any(not isinstance(x, StageSpec) for x in self.stages):
            raise ValueError("requires 1..64 well-formed stages")
        if type(self.initial) is not int or type(self.final_observe) is not bool:
            raise ValueError("strict integer initial value and Boolean final observation required")


@dataclass(frozen=True, order=True)
class State:
    target: int
    error: int
    bad: bool
    first_bad: int


def signed_bounds(bits: int) -> Tuple[int, int]:
    return -(1 << (bits - 1)), (1 << (bits - 1)) - 1


def cast_signed(value: int, bits: int, mode: str) -> int:
    lo, hi = signed_bounds(bits)
    if mode == "saturate":
        return min(hi, max(lo, value))
    if mode != "wrap":
        raise ValueError("unknown conversion mode")
    modulus = 1 << bits
    raw = value % modulus
    return raw - modulus if raw >= (1 << (bits - 1)) else raw


def _classes(stage: StageSpec) -> List[dict]:
    by_product: Dict[int, List[int]] = {}
    for index, (left, right) in enumerate(stage.pairs):
        by_product.setdefault(left * right, []).append(index)
    out = []
    for product, indices in sorted(by_product.items(), key=lambda item: item[1][0]):
        rep = indices[0]
        out.append(
            {
                "product": product,
                "representative_index": rep,
                "representative_pair": list(stage.pairs[rep]),
                "member_indices": indices,
                "member_pairs": [list(stage.pairs[i]) for i in indices],
            }
        )
    return out


def _lowered_from_state(
    state: State, spec: AccumulatorSpec, stage_index: int
) -> int:
    if stage_index == 0:
        stage = spec.stages[0]
        ref = cast_signed(state.target, stage.acc_bits, stage.acc_mode)
    else:
        previous = spec.stages[stage_index - 1]
        ref = cast_signed(state.target, previous.acc_bits, previous.acc_mode)
    return ref + state.error


def _step(
    state: State,
    product: int,
    spec: AccumulatorSpec,
    stage_index: int,
) -> State:
    stage = spec.stages[stage_index]
    lower_before = _lowered_from_state(state, spec, stage_index)
    lower_term = cast_signed(product, stage.term_bits, stage.term_mode)
    return _step_prepared(state, product, lower_before, lower_term, spec, stage_index)


def _step_prepared(state: State, product: int, lower_before: int, lower_term: int,
                   spec: AccumulatorSpec, stage_index: int) -> State:
    """Apply an edge using values prepared locally after its ledger charge."""
    stage = spec.stages[stage_index]
    lower_after = cast_signed(lower_before + lower_term, stage.acc_bits, stage.acc_mode)
    target_after = state.target + product
    reference_after = cast_signed(target_after, stage.acc_bits, stage.acc_mode)
    error_after = lower_after - reference_after
    observed = stage.observe or (
        spec.final_observe and stage_index == len(spec.stages) - 1
    )
    mismatch = observed and error_after != 0
    first_bad = state.first_bad
    if mismatch and not state.bad:
        first_bad = stage_index
    return State(target_after, error_after, state.bad or mismatch, first_bad)


def spec_to_dict(spec: AccumulatorSpec) -> dict:
    return {
        "name": spec.name,
        "initial": spec.initial,
        "final_observe": spec.final_observe,
        "provenance": spec.provenance,
        "stages": [
            {
                "pairs": [list(pair) for pair in stage.pairs],
                "term_bits": stage.term_bits,
                "term_mode": stage.term_mode,
                "acc_bits": stage.acc_bits,
                "acc_mode": stage.acc_mode,
                "observe": stage.observe,
            }
            for stage in spec.stages
        ],
    }


def generate_certificate(
    spec: AccumulatorSpec,
    ledger: ObligationLedger,
    category_prefix: str = "accumulator-producer",
) -> dict:
    first = spec.stages[0]
    initial_lower = cast_signed(spec.initial, first.acc_bits, first.acc_mode)
    initial_ref = cast_signed(spec.initial, first.acc_bits, first.acc_mode)
    initial = State(spec.initial, initial_lower - initial_ref, False, -1)
    current: Dict[State, Witness] = {initial: ()}
    layers: List[dict] = [
        {
            "index": 0,
            "states": [
                {
                    "state": [initial.target, initial.error, initial.bad, initial.first_bad],
                    "least_witness_indices": [],
                    "least_witness_pairs": [],
                }
            ],
        }
    ]
    transition_count = 0
    concrete_prefixes = 1
    quotient_prefixes = 1
    class_tables: List[list] = []

    for stage_index, stage in enumerate(spec.stages):
        ledger.charge(f"{category_prefix}:partition-pair", len(stage.pairs))
        classes = _classes(stage)
        class_tables.append(classes)
        concrete_prefixes *= len(stage.pairs)
        quotient_prefixes *= len(classes)
        nxt: Dict[State, Witness] = {}
        edges = []
        lower_terms: Dict[int, int] = {}
        for state, witness in sorted(current.items(), key=lambda item: (item[0], item[1])):
            lower_before = None
            for product_class in classes:
                ledger.charge(f"{category_prefix}:transition")
                transition_count += 1
                # Each preparation is covered by its first original edge charge.
                # No preparation crosses a layer or a certificate invocation.
                if lower_before is None:
                    lower_before = _lowered_from_state(state, spec, stage_index)
                product = product_class["product"]
                if product not in lower_terms:
                    lower_terms[product] = cast_signed(product, stage.term_bits, stage.term_mode)
                successor = _step_prepared(state, product, lower_before,
                                           lower_terms[product], spec, stage_index)
                candidate = witness + (product_class["representative_index"],)
                old = nxt.get(successor)
                if old is None or candidate < old:
                    nxt[successor] = candidate
                edges.append(
                    {
                        "from": [state.target, state.error, state.bad, state.first_bad],
                        "product": product_class["product"],
                        "representative_index": product_class["representative_index"],
                        "to": [
                            successor.target,
                            successor.error,
                            successor.bad,
                            successor.first_bad,
                        ],
                    }
                )
        state_records = []
        for state, witness in sorted(nxt.items(), key=lambda item: (item[0], item[1])):
            pairs = [list(spec.stages[i].pairs[index]) for i, index in enumerate(witness)]
            state_records.append(
                {
                    "state": [state.target, state.error, state.bad, state.first_bad],
                    "least_witness_indices": list(witness),
                    "least_witness_pairs": pairs,
                }
            )
        layers.append({"index": stage_index + 1, "states": state_records, "edges": edges})
        current = nxt

    bad = [(witness, state) for state, witness in current.items() if state.bad]
    least_bad = min(bad, default=None, key=lambda item: item[0])
    equivalent = least_bad is None
    counterexample = None
    if least_bad is not None:
        witness, state = least_bad
        counterexample = {
            "indices": list(witness),
            "pairs": [list(spec.stages[i].pairs[index]) for i, index in enumerate(witness)],
            "first_bad_stage": state.first_bad,
            "final_state": [state.target, state.error, state.bad, state.first_bad],
        }

    return {
        "format": "bptc-exact-accumulator-certificate-v1",
        "spec": spec_to_dict(spec),
        "product_classes": class_tables,
        "layers": layers,
        "decision": {
            "equivalent": equivalent,
            "least_counterexample": counterexample,
            "reachable_final_states": len(current),
            "bad_final_states": sum(1 for state in current if state.bad),
        },
        "metrics": {
            "concrete_assignments": concrete_prefixes,
            "quotient_product_sequences": quotient_prefixes,
            "producer_transitions": transition_count,
            "unquotiented_frontier_edges": sum(
                len(layer["states"]) * len(spec.stages[i].pairs)
                for i, layer in enumerate(layers[:-1])
            ),
            "quotient_frontier_edges": transition_count,
        },
    }


def product_classes(stage: StageSpec) -> List[dict]:
    """Public read-only view used by reporting code, not by the checker."""
    return _classes(stage)
