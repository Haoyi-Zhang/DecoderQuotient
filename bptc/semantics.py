"""Whole-word interpreter: deliberately does not import producer or checker."""
from __future__ import annotations
from itertools import product
from typing import Iterable


def signed(value: int, bits: int) -> int:
    residue = value % (1 << bits)
    return residue - (1 << bits) if residue >= (1 << (bits - 1)) else residue


def decode_word(q: list[int], bits: int, scale: int, zero: int, mode: str) -> list[int]:
    """Execute a word, then slice it. No carry recurrence is used here."""
    base = 1 << bits
    modulus = base ** len(q)
    if mode == 'sub_mul':
        operands = [(x-zero) % base for x in q]
    else:
        operands = q
    packed = sum(x * base**j for j, x in enumerate(operands))
    word = (packed * scale) % modulus
    if mode == 'word_sub':
        correction = sum((scale*zero % base) * base**j for j in range(len(q)))
        word = (word - correction) % modulus
    elif mode == 'word_affine':
        correction = scale*zero * sum(base**j for j in range(len(q)))
        word = (word - correction) % modulus
    elif mode not in ('mul_sub', 'sub_mul', 'sat_mul_sub'):
        raise ValueError('unsupported arithmetic')
    result = []
    for j, x in enumerate(q):
        digit = (word >> (j*bits)) & (base-1)
        if mode == 'mul_sub':
            digit = (digit - scale*zero) % base
        elif mode == 'sat_mul_sub':
            digit = (min(scale*x, base//2-1) - scale*zero) % base
        result.append(signed(digit, bits))
    return result


def exhaustive_word(domains: list[list[int]], bits: int, scale: int,
                    zero: int, mode: str) -> tuple[list[int] | None, int]:
    first = None
    count = 0
    for values in product(*(range(lo, hi+1) for lo, hi in domains)):
        q = list(values)
        count += 1
        if decode_word(q, bits, scale, zero, mode) != [scale*(x-zero) for x in q]:
            if first is None:
                first = q
    return first, count


def execute(case: dict, q: list[int], activations: list[int]) -> tuple[int, int]:
    n = len(case['domains'])
    if len(q) != n or len(activations) != n:
        raise ValueError('wrong tensor length')
    for x, (lo, hi) in zip(q, case['domains']):
        if not lo <= x <= hi:
            raise ValueError('weight outside input contract')
    if any(not case['activation_bounds'][0] <= x <= case['activation_bounds'][1]
           for x in activations):
        raise ValueError('activation outside input contract')
    s, z, b = case['scale'], case['zero'], case['bits']
    lanes = 32//b
    physical = [q[i] for i in case['layout']]
    decoded = []
    for start in range(0, n, lanes):
        decoded.extend(decode_word(physical[start:start+lanes], b, s, z,
                                   case['arithmetic']))
    mathematical = sum(a*s*(x-z) for a, x in zip(activations, q))
    machine = 0
    for j, w in enumerate(decoded):
        width = case['acc_widths'][j]
        raw = machine + activations[case['consume'][j]] * w
        if case['acc_semantics'] == 'saturating':
            machine = max(-(1 << (width-1)), min((1 << (width-1))-1, raw))
        else:
            machine = signed(raw, width)
    return mathematical, machine


def nibble_pack32(q: list[int]) -> list[int]:
    """Original implementation of the paper's 32-code interleave schema."""
    if len(q) != 32 or any(type(x) is not int or not 0 <= x <= 15 for x in q):
        raise ValueError('32 unsigned four-bit codes required')
    return [sum((q[4*j+i] | (q[16+4*j+i] << 4)) << (8*i)
                for i in range(4)) for j in range(4)]


def nibble_unpack32(words: list[int]) -> list[int]:
    if len(words) != 4 or any(type(x) is not int or not 0 <= x < 2**32 for x in words):
        raise ValueError('four 32-bit words required')
    result = []
    for shift in (0, 4):
        for word in words:
            separated = (word >> shift) & 0x0F0F0F0F
            result.extend((separated >> (8*i)) & 255 for i in range(4))
    return result
