"""Exact certificates for the source-anchored packed-byte multiply idiom."""
from __future__ import annotations

from dataclasses import dataclass
from itertools import product
from typing import Dict, List, Tuple

from .publication_budget import ObligationLedger


@dataclass(frozen=True)
class DecoderSpec:
    name: str
    scale: int
    maxima: Tuple[int, ...]
    biases: Tuple[int, ...]
    lane_bits: int = 8
    provenance: str = "systematic"

    def __post_init__(self) -> None:
        if not self.name or len(self.maxima) == 0:
            raise ValueError("decoder name and lanes are required")
        if len(self.maxima) != len(self.biases):
            raise ValueError("bias count must equal lane count")
        base = 1 << self.lane_bits
        if not (0 <= self.scale < base):
            raise ValueError("scale must be an unsigned lane value")
        if any(value < 0 or value > 15 for value in self.maxima):
            raise ValueError("source-anchored nibble maxima must lie in 0..15")
        if any(value < 0 or value >= base for value in self.biases):
            raise ValueError("bias must be a lane value")


def spec_to_dict(spec: DecoderSpec) -> dict:
    return {
        "name": spec.name,
        "scale": spec.scale,
        "maxima": list(spec.maxima),
        "biases": list(spec.biases),
        "lane_bits": spec.lane_bits,
        "provenance": spec.provenance,
    }


def _transition(carry: int, digit: int, scale: int, base: int) -> Tuple[int, bool]:
    aggregate = scale * digit + carry
    lowered_lane = aggregate % base
    reference_lane = (scale * digit) % base
    return aggregate // base, lowered_lane != reference_lane


def generate_decoder_certificate(
    spec: DecoderSpec,
    ledger: ObligationLedger,
    category_prefix: str = "decoder-producer",
) -> dict:
    base = 1 << spec.lane_bits
    # For nibble digits and an unsigned byte scale, every carry is less than base.
    source_bound = spec.scale < base and max(spec.maxima) <= 15
    current: Dict[Tuple[int, bool, int], Tuple[int, ...]] = {(0, False, -1): ()}
    layers = [{"index": 0, "states": [{"state": [0, False, -1], "least_witness": []}]}]
    max_carry = 0
    closed_form_safe = True
    transitions = 0

    for lane, maximum in enumerate(spec.maxima):
        # Closed-form upper-envelope recurrence.  Under source_bound, safety is
        # equivalent to zero carry entering every observed lane.
        if lane > 0 and max_carry != 0:
            closed_form_safe = False
        max_carry = (spec.scale * maximum + max_carry) // base

        nxt: Dict[Tuple[int, bool, int], Tuple[int, ...]] = {}
        edges = []
        for state, witness in sorted(current.items(), key=lambda item: (item[0], item[1])):
            carry, bad, first_bad = state
            for digit in range(maximum + 1):
                ledger.charge(f"{category_prefix}:transition")
                transitions += 1
                next_carry, mismatch = _transition(carry, digit, spec.scale, base)
                now_bad = bad or mismatch
                now_first = lane if mismatch and not bad else first_bad
                successor = (next_carry, now_bad, now_first)
                candidate = witness + (digit,)
                previous = nxt.get(successor)
                if previous is None or candidate < previous:
                    nxt[successor] = candidate
                edges.append(
                    {
                        "from": list(state),
                        "digit": digit,
                        "to": list(successor),
                    }
                )
        states = [
            {"state": list(state), "least_witness": list(witness)}
            for state, witness in sorted(nxt.items(), key=lambda item: (item[0], item[1]))
        ]
        layers.append({"index": lane + 1, "states": states, "edges": edges})
        current = nxt

    bad = [(witness, state) for state, witness in current.items() if state[1]]
    least = min(bad, default=None, key=lambda item: item[0])
    equivalent = least is None
    if not source_bound:
        raise ValueError("closed form is certified only for the source parameter bound")
    if closed_form_safe != equivalent:
        raise AssertionError("closed form and reachable-carry decision disagree")
    counterexample = None
    if least is not None:
        witness, state = least
        counterexample = {
            "digits": list(witness),
            "first_bad_lane": state[2],
            "final_carry": state[0],
        }

    return {
        "format": "bptc-packed-decoder-certificate-v1",
        "spec": spec_to_dict(spec),
        "source_parameter_bound": source_bound,
        "closed_form": {
            "equivalent": closed_form_safe,
            "max_carry_after_last_lane": max_carry,
        },
        "layers": layers,
        "decision": {
            "equivalent": equivalent,
            "least_counterexample": counterexample,
        },
        "metrics": {
            "producer_transitions": transitions,
            "concrete_assignments": _product(maximum + 1 for maximum in spec.maxima),
            "reachable_final_states": len(current),
        },
    }


def _product(values) -> int:
    answer = 1
    for value in values:
        answer *= value
    return answer


def check_decoder_certificate(
    certificate: dict,
    ledger: ObligationLedger,
    category_prefix: str = "decoder-checker",
) -> dict:
    """Independent replay, with arithmetic restated rather than delegated."""
    if certificate.get("format") != "bptc-packed-decoder-certificate-v1":
        raise ValueError("unknown decoder certificate")
    spec = certificate["spec"]
    width = spec["lane_bits"]
    radix = 2**width
    scale = spec["scale"]
    maxima = spec["maxima"]
    if not (scale < radix and max(maxima) <= 15):
        raise ValueError("source parameter bound does not hold")
    current: Dict[Tuple[int, bool, int], Tuple[int, ...]] = {(0, False, -1): ()}
    layers = certificate["layers"]
    if layers[0]["states"] != [{"state": [0, False, -1], "least_witness": []}]:
        raise ValueError("bad initial decoder layer")

    checked = 0
    envelope = 0
    safe = True
    for lane_number, upper in enumerate(maxima):
        if lane_number and envelope:
            safe = False
        envelope = (scale * upper + envelope) // radix
        expected_edges = []
        following: Dict[Tuple[int, bool, int], Tuple[int, ...]] = {}
        for old, prefix in sorted(current.items(), key=lambda item: (item[0], item[1])):
            incoming, failed, first = old
            for digit in range(upper + 1):
                ledger.charge(f"{category_prefix}:transition")
                checked += 1
                combined = scale * digit + incoming
                outgoing = combined // radix
                differs = (combined % radix) != ((scale * digit) % radix)
                failed_new = failed or differs
                first_new = lane_number if differs and not failed else first
                state_new = (outgoing, failed_new, first_new)
                witness_new = prefix + (digit,)
                previous = following.get(state_new)
                if previous is None or witness_new < previous:
                    following[state_new] = witness_new
                expected_edges.append(
                    {"from": list(old), "digit": digit, "to": list(state_new)}
                )
        layer = layers[lane_number + 1]
        expected_states = [
            {"state": list(state), "least_witness": list(witness)}
            for state, witness in sorted(following.items(), key=lambda item: (item[0], item[1]))
        ]
        if layer.get("edges") != expected_edges or layer.get("states") != expected_states:
            raise ValueError(f"decoder replay mismatch at lane {lane_number}")
        current = following

    bad = [(w, s) for s, w in current.items() if s[1]]
    least = min(bad, default=None, key=lambda item: item[0])
    decision = certificate["decision"]
    if decision["equivalent"] != (least is None):
        raise ValueError("decoder decision mismatch")
    expected_counterexample = None
    if least is not None:
        witness, state = least
        expected_counterexample = {
            "digits": list(witness),
            "first_bad_lane": state[2],
            "final_carry": state[0],
        }
    if decision["least_counterexample"] != expected_counterexample:
        raise ValueError("decoder counterexample mismatch")
    if certificate["closed_form"]["equivalent"] != safe:
        raise ValueError("closed-form result mismatch")
    return {"accepted": True, "equivalent": least is None, "checked_transitions": checked}


def brute_force_decoder(
    spec: DecoderSpec,
    ledger: ObligationLedger,
    category_prefix: str = "decoder-oracle",
) -> dict:
    base = 1 << spec.lane_bits
    modulus = base ** len(spec.maxima)
    least = None
    failures = 0
    assignments = 0
    for digits in product(*(range(maximum + 1) for maximum in spec.maxima)):
        ledger.charge(f"{category_prefix}:assignment")
        assignments += 1
        packed = sum(digit * (base**lane) for lane, digit in enumerate(digits))
        multiplied = (packed * spec.scale) % modulus
        bad_lane = None
        for lane, digit in enumerate(digits):
            lowered = ((multiplied // (base**lane)) % base + spec.biases[lane]) % base
            reference = ((digit * spec.scale) % base + spec.biases[lane]) % base
            if lowered != reference and bad_lane is None:
                bad_lane = lane
        if bad_lane is not None:
            failures += 1
            if least is None:
                least = {"digits": list(digits), "first_bad_lane": bad_lane}
    return {
        "equivalent": failures == 0,
        "assignments": assignments,
        "failing_assignments": failures,
        "least_counterexample": least,
    }
