"""Exact certificates for the source-anchored packed-byte multiply idiom."""
from __future__ import annotations

from dataclasses import dataclass
from itertools import product
from typing import Dict, List, Tuple

from .publication_budget import ObligationLedger
from .certificate_format import exact, keys, integer, text


@dataclass(frozen=True)
class DecoderSpec:
    name: str
    scale: int
    maxima: Tuple[int, ...]
    biases: Tuple[int, ...]
    lane_bits: int = 8
    provenance: str = "systematic"

    def __post_init__(self) -> None:
        if type(self.name) is not str or not self.name or type(self.provenance) is not str or not self.provenance:
            raise ValueError("name and provenance required")
        if type(self.lane_bits) is not int or self.lane_bits != 8:
            raise ValueError("source fragment uses byte lanes")
        if type(self.maxima) is not tuple or type(self.biases) is not tuple or not 1 <= len(self.maxima) <= 4 or len(self.maxima) != len(self.biases):
            raise ValueError("requires 1..4 lanes and matching biases")
        if type(self.scale) is not int or not 0 <= self.scale < 256:
            raise ValueError("scale must be an unsigned byte")
        if any(type(x) is not int or not 0 <= x <= 15 for x in self.maxima):
            raise ValueError("maxima must be integer nibbles")
        if any(type(x) is not int or not 0 <= x < 256 for x in self.biases):
            raise ValueError("biases must be unsigned bytes")


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


def check_decoder_certificate(certificate: dict, ledger: ObligationLedger,
                              category_prefix: str = "decoder-checker") -> dict:
    """Recompute every field without calling the certificate producer."""
    ledger.charge(f"{category_prefix}:schema")
    keys(certificate,{"format","spec","source_parameter_bound","closed_form","layers","decision","metrics"},"certificate")
    exact(certificate["format"],"bptc-packed-decoder-certificate-v1","format")
    spec = certificate["spec"]
    keys(spec,{"name","scale","maxima","biases","lane_bits","provenance"},"spec")
    text(spec["name"],"name"); text(spec["provenance"],"provenance")
    integer(spec["lane_bits"],"lane_bits",8,8)
    integer(spec["scale"],"scale",0,255)
    maxima = spec["maxima"]; biases = spec["biases"]
    if type(maxima) is not list or not 1 <= len(maxima) <= 4:
        raise ValueError("requires 1..4 lanes")
    if type(biases) is not list or len(biases) != len(maxima):
        raise ValueError("bias count mismatch")
    for x in maxima: integer(x,"maximum",0,15)
    for x in biases: integer(x,"bias",0,255)
    radix = 256; scale = spec["scale"]
    current = {(0,False,-1):()}
    rebuilt = [{"index":0,"states":[{"state":[0,False,-1],"least_witness":[]}]}]
    checked = 0; envelope = 0; safe = True; assignments = 1
    for lane_number, upper in enumerate(maxima):
        assignments *= upper + 1
        if lane_number and envelope: safe = False
        envelope = (scale*upper + envelope)//radix
        edges = []; following = {}
        for old,prefix in sorted(current.items(),key=lambda item:(item[0],item[1])):
            incoming,failed,first = old
            for digit in range(upper+1):
                ledger.charge(f"{category_prefix}:transition"); checked += 1
                combined = scale*digit+incoming
                differs = combined % radix != (scale*digit) % radix
                state = (combined//radix, failed or differs, lane_number if differs and not failed else first)
                witness = prefix+(digit,)
                if state not in following or witness < following[state]: following[state]=witness
                edges.append({"from":list(old),"digit":digit,"to":list(state)})
        states=[{"state":list(st),"least_witness":list(w)} for st,w in sorted(following.items(),key=lambda item:(item[0],item[1]))]
        rebuilt.append({"index":lane_number+1,"states":states,"edges":edges}); current=following
    failures=[(w,st) for st,w in current.items() if st[1]]
    least=min(failures,default=None,key=lambda x:x[0])
    cex=None if least is None else {"digits":list(least[0]),"first_bad_lane":least[1][2],"final_carry":least[1][0]}
    expected={"format":"bptc-packed-decoder-certificate-v1","spec":spec,"source_parameter_bound":True,
              "closed_form":{"equivalent":safe,"max_carry_after_last_lane":envelope},"layers":rebuilt,
              "decision":{"equivalent":least is None,"least_counterexample":cex},
              "metrics":{"producer_transitions":checked,"concrete_assignments":assignments,"reachable_final_states":len(current)}}
    exact(certificate,expected)
    return {"accepted":True,"equivalent":least is None,"checked_transitions":checked,
            "metrics":expected["metrics"]}


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
