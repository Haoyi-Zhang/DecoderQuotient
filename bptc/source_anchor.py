"""Narrow structural importer for the frozen OmniServe packed-dequant block."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Dict, List

from .publication_budget import ObligationLedger

EXPECTED_LOADS = {
    0: ("x", "low"),
    4: ("x", "high"),
    2: ("y", "low"),
    6: ("y", "high"),
    1: ("z", "low"),
    5: ("z", "high"),
    3: ("w", "low"),
    7: ("w", "high"),
}
EXPECTED_SCALE = {0: 0, 1: 0, 2: 1, 3: 1, 4: 2, 5: 2, 6: 3, 7: 3}


def parse_source(text: str, ledger: ObligationLedger, category: str = "source-import") -> dict:
    ledger.charge(f"{category}:parse")
    loads: Dict[int, tuple] = {}
    low_pattern = re.compile(
        r"uint32_t\s+loaded_(\d)\s*=\s*loaded\.([xyzw])\s*&\s*0x0F0F0F0F\s*;"
    )
    high_pattern = re.compile(
        r"uint32_t\s+loaded_(\d)\s*=\s*\(loaded\.([xyzw])\s*&\s*0xF0F0F0F0\)\s*>>\s*4\s*;"
    )
    for match in low_pattern.finditer(text):
        loads[int(match.group(1))] = (match.group(2), "low")
    for match in high_pattern.finditer(text):
        loads[int(match.group(1))] = (match.group(2), "high")
    if loads != EXPECTED_LOADS:
        raise ValueError(f"nibble extraction map mismatch: {loads}")

    products: Dict[int, tuple] = {}
    for match in re.finditer(
        r"uint32_t\s+ptr_(\d)\s*=\s*loaded_(\d)\s*\*\s*scale_(\d)\s*;", text
    ):
        products[int(match.group(1))] = (int(match.group(2)), int(match.group(3)))
    expected_products = {index: (index, EXPECTED_SCALE[index]) for index in range(8)}
    if products != expected_products:
        raise ValueError(f"multiply pairing mismatch: {products}")

    stores: Dict[int, tuple] = {}
    for match in re.finditer(
        r"ptr\[(\d)\]\s*=\s*__vadd4\(ptr_(\d),\s*zero_point_(\d)\)\s*;", text
    ):
        stores[int(match.group(1))] = (int(match.group(2)), int(match.group(3)))
    expected_stores = {index: (index, EXPECTED_SCALE[index]) for index in range(8)}
    if stores != expected_stores:
        raise ValueError(f"bytewise correction pairing mismatch: {stores}")

    return {
        "accepted": True,
        "loaded_vectors": 8,
        "whole_word_multiplies": 8,
        "bytewise_corrections": 8,
        "load_map": {str(key): list(value) for key, value in sorted(loads.items())},
        "scale_map": {str(key): value for key, value in sorted(EXPECTED_SCALE.items())},
        "trusted_boundary": (
            "The importer checks the frozen restricted expression block; it does not "
            "parse CUDA control flow, memory safety, ldmatrix, MMA, or floating epilogues."
        ),
    }


def parse_frozen_file(path: Path, ledger: ObligationLedger) -> dict:
    return parse_source(path.read_text(), ledger)


def mutation_suite(text: str, ledger: ObligationLedger) -> dict:
    mutations: List[str] = []
    mutations.append(text.replace("0x0F0F0F0F", "0x0E0E0E0E", 1))
    mutations.append(text.replace("0xF0F0F0F0", "0xE0E0E0E0", 1))
    mutations.append(text.replace("loaded_7 =", "loaded_6 =", 1))
    mutations.append(text.replace("ptr_7 = loaded_7 * scale_3", "ptr_7 = loaded_7 * scale_2", 1))
    mutations.append(text.replace("ptr[7] = __vadd4(ptr_7, zero_point_3)", "ptr[7] = ptr_7", 1))
    mutations.append(text.replace("ptr[6] = __vadd4(ptr_6, zero_point_3)", "ptr[5] = __vadd4(ptr_6, zero_point_3)", 1))
    mutations.append(text.replace(">> 4", ">> 3", 1))
    mutations.append(text.replace("loaded.y", "loaded.x", 1))
    # Create additional one-site pairing mutations deterministically.
    for index in range(8):
        expected = f"ptr_{index} = loaded_{index} * scale_{EXPECTED_SCALE[index]}"
        wrong_scale = (EXPECTED_SCALE[index] + 1) % 4
        mutations.append(text.replace(expected, f"ptr_{index} = loaded_{index} * scale_{wrong_scale}", 1))
    rejected = 0
    for mutant in mutations:
        ledger.charge("source-import:mutation")
        try:
            parse_source(mutant, ledger, category="source-import-mutation-replay")
        except ValueError:
            rejected += 1
    if rejected != len(mutations):
        raise AssertionError("a source-structure mutation escaped the importer")
    return {"mutations": len(mutations), "rejected": rejected}
