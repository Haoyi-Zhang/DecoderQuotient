"""Deterministic decoder and accumulator evaluation suites."""
from __future__ import annotations

from typing import Iterable, List, Sequence, Tuple

from .exact_accumulator import AccumulatorSpec, StageSpec
from .packed_decoder import DecoderSpec

Pair = Tuple[int, int]


def _pairs_for_product(product: int, count: int = 3) -> Tuple[Pair, ...]:
    candidates: List[Pair] = []
    if product == 0:
        candidates = [(0, 0), (0, 1), (1, 0), (0, -1), (-1, 0)]
    else:
        for left in range(-32, 33):
            if left != 0 and product % left == 0:
                candidates.append((left, product // left))
        candidates.extend([(1, product), (product, 1), (-1, -product), (-product, -1)])
    unique: List[Pair] = []
    for pair in candidates:
        if pair not in unique:
            unique.append(pair)
    unique.sort(key=lambda pair: (max(abs(pair[0]), abs(pair[1])), abs(pair[0]) + abs(pair[1]), pair))
    if type(count) is not int or count < 1:
        raise ValueError("count must be positive")
    # +/-1 have only two distinct integer factor pairs. Use available pairs;
    # never duplicate a member to manufacture compression.
    return tuple(unique[:count])


def _domain(products: Sequence[int], each: int = 3) -> Tuple[Pair, ...]:
    pairs: List[Pair] = []
    for product in products:
        for pair in _pairs_for_product(product, each):
            if pair not in pairs:
                pairs.append(pair)
    return tuple(pairs)


def _stage(
    products: Sequence[int],
    term_bits: int,
    term_mode: str,
    acc_bits: int,
    acc_mode: str,
    observe: bool = False,
    each: int = 3,
) -> StageSpec:
    return StageSpec(
        pairs=_domain(products, each=each),
        term_bits=term_bits,
        term_mode=term_mode,
        acc_bits=acc_bits,
        acc_mode=acc_mode,
        observe=observe,
    )


def accumulator_specs() -> List[AccumulatorSpec]:
    specs: List[AccumulatorSpec] = []
    for variant in range(8):
        bits = 4 + (variant % 4)
        high = (1 << (bits - 1)) - 1
        wide = bits + 4

        products = [1, -1, 2, -2]
        specs.append(
            AccumulatorSpec(
                name=f"safe-saturating-{variant:02d}",
                initial=0,
                stages=tuple(
                    _stage([p], wide, "saturate", wide, "saturate", observe=(variant % 2 == 0))
                    for p in products
                ),
                final_observe=True,
                provenance="safe-control",
            )
        )

        products = [high, 2, -1, 0]
        specs.append(
            AccumulatorSpec(
                name=f"visible-saturation-{variant:02d}",
                initial=0,
                stages=tuple(
                    _stage([p], wide, "saturate", bits, "saturate", observe=(i == 1 and variant % 2 == 0))
                    for i, p in enumerate(products)
                ),
                final_observe=True,
                provenance="adversarial-overflow",
            )
        )

        # The first step saturates, but a later large negative term drives both
        # executions to the same final lower bound.  A no-overflow guard rejects.
        products = [high + 1, -4 * high, 0, 0]
        specs.append(
            AccumulatorSpec(
                name=f"saturation-reconvergence-{variant:02d}",
                initial=0,
                stages=tuple(
                    _stage([p], wide, "saturate", bits, "saturate", observe=False)
                    for p in products
                ),
                final_observe=True,
                provenance="cancellation-control",
            )
        )

        # The final exact target is zero, but an earlier saturation loses one.
        products = [high + 1, -(high + 1), 0, 0]
        specs.append(
            AccumulatorSpec(
                name=f"final-range-unsound-{variant:02d}",
                initial=0,
                stages=tuple(
                    _stage([p], wide, "saturate", bits, "saturate", observe=False)
                    for p in products
                ),
                final_observe=True,
                provenance="final-range-counterexample",
            )
        )

        products = [high + 1, 0, 0, 0]
        specs.append(
            AccumulatorSpec(
                name=f"term-narrowing-{variant:02d}",
                initial=0,
                stages=tuple(
                    _stage([p], bits, "wrap", wide, "wrap", observe=False)
                    for p in products
                ),
                final_observe=True,
                provenance="mixed-width-term",
            )
        )

        products = [high + 1, -2, 1, 0]
        acc_widths = [bits, wide, bits, wide]
        specs.append(
            AccumulatorSpec(
                name=f"width-schedule-{variant:02d}",
                initial=0,
                stages=tuple(
                    _stage(
                        [p],
                        wide,
                        "saturate",
                        acc_widths[i],
                        "saturate" if i != 1 else "wrap",
                        observe=(i == 2 and variant % 2 == 1),
                    )
                    for i, p in enumerate(products)
                ),
                final_observe=True,
                provenance="mixed-width-schedule",
            )
        )

        products = [high + 1, -1, -4 * high, 0]
        specs.append(
            AccumulatorSpec(
                name=f"intermediate-observation-{variant:02d}",
                initial=0,
                stages=tuple(
                    _stage([p], wide, "saturate", bits, "saturate", observe=(i == 1))
                    for i, p in enumerate(products)
                ),
                final_observe=True,
                provenance="observation-schedule",
            )
        )

        product_sets = ([0, 1], [high, high + 1], [-high, -(high + 1)], [0, 1])
        specs.append(
            AccumulatorSpec(
                name=f"mixed-product-domain-{variant:02d}",
                initial=0,
                stages=tuple(
                    _stage(
                        values,
                        wide,
                        "saturate",
                        bits,
                        "saturate",
                        observe=(i == 1 and variant % 3 == 0),
                        each=2,
                    )
                    for i, values in enumerate(product_sets)
                ),
                final_observe=True,
                provenance="systematic-product-box",
            )
        )
    if len(specs) != 64 or len({spec.name for spec in specs}) != 64:
        raise AssertionError("accumulator suite construction failed")
    return specs


def decoder_specs() -> List[DecoderSpec]:
    scales = [1, 7, 15, 16, 17, 18, 31, 63, 127, 255]
    profiles = [
        ((15, 15, 15, 15), "full-nibble-box"),
        ((3, 3, 3, 3), "tiny-oracle-box"),
        ((15, 0, 15, 0), "alternating-lanes"),
    ]
    specs: List[DecoderSpec] = []
    for profile_index, (maxima, provenance) in enumerate(profiles):
        for scale in scales:
            biases = tuple((scale * (lane + 1) + profile_index) % 256 for lane in range(4))
            specs.append(
                DecoderSpec(
                    name=f"decoder-{provenance}-{scale:03d}",
                    scale=scale,
                    maxima=maxima,
                    biases=biases,
                    provenance=provenance,
                )
            )
    if len(specs) != 30:
        raise AssertionError("decoder suite construction failed")
    return specs
