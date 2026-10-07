"""Two intentionally simple guards used as comparison baselines."""
from __future__ import annotations

from typing import Tuple


def _bounds(bits: int) -> Tuple[int, int]:
    return -(1 << (bits - 1)), (1 << (bits - 1)) - 1


def no_overflow_sufficient(spec: dict) -> bool:
    """Accept only when every term and every exact prefix fits its declared type."""
    low = high = spec["initial"]
    first_low, first_high = _bounds(spec["stages"][0]["acc_bits"])
    if not first_low <= low <= first_high:
        return False
    for stage in spec["stages"]:
        products = [left * right for left, right in stage["pairs"]]
        term_low, term_high = min(products), max(products)
        declared_term_low, declared_term_high = _bounds(stage["term_bits"])
        if term_low < declared_term_low or term_high > declared_term_high:
            return False
        low += term_low
        high += term_high
        declared_acc_low, declared_acc_high = _bounds(stage["acc_bits"])
        if low < declared_acc_low or high > declared_acc_high:
            return False
    return True


def term_fit_and_final_range(spec: dict) -> bool:
    """Unsound stronger heuristic: term-fit plus final exact interval."""
    low = high = spec["initial"]
    for stage in spec["stages"]:
        products = [left * right for left, right in stage["pairs"]]
        term_low, term_high = min(products), max(products)
        declared_term_low, declared_term_high = _bounds(stage["term_bits"])
        if term_low < declared_term_low or term_high > declared_term_high:
            return False
        low += term_low
        high += term_high
    final = spec["stages"][-1]
    declared_low, declared_high = _bounds(final["acc_bits"])
    return declared_low <= low and high <= declared_high


def final_range_only(spec: dict) -> bool:
    """Pure final-range heuristic: deliberately ignores narrowing and history."""
    low = high = spec["initial"]
    for stage in spec["stages"]:
        products = [left * right for left, right in stage["pairs"]]
        low += min(products)
        high += max(products)
    lo, hi = _bounds(spec["stages"][-1]["acc_bits"])
    return lo <= low <= high <= hi
