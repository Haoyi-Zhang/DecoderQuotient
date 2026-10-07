"""Exact token allowlist for one frozen source block, not a CUDA frontend.

The reviewed token sequence is trusted input. Comments are lexed, not searched
for code. Every non-comment token must be consumed in the original order.
"""
from __future__ import annotations
import re
from pathlib import Path
from .publication_budget import ObligationLedger

EXPECTED = 'uint4 loaded = *((uint4 *)(src) + warp_offset_n / 32 * kSmemCol +\n                 shared_iter * 32 / 32 * kSmemCol + k_0_1 * INTRIN_K + threadIdx.x);\nuint32_t loaded_0 = loaded.x & 0x0F0F0F0F;\nuint32_t loaded_4 = (loaded.x & 0xF0F0F0F0) >> 4;\nuint32_t loaded_2 = loaded.y & 0x0F0F0F0F;\nuint32_t loaded_6 = (loaded.y & 0xF0F0F0F0) >> 4;\nuint32_t loaded_1 = loaded.z & 0x0F0F0F0F;\nuint32_t loaded_5 = (loaded.z & 0xF0F0F0F0) >> 4;\nuint32_t loaded_3 = loaded.w & 0x0F0F0F0F;\nuint32_t loaded_7 = (loaded.w & 0xF0F0F0F0) >> 4;\n\nauto ptr = (uint32_t *)dst + shared_iter * 8;\nint scales_zeros_offset = warp_offset_n + (threadIdx.x / 4) * 4 + shared_iter * 32;\nuint32_t packed_scales = *reinterpret_cast<uint32_t *>(scales_i8 + scales_zeros_offset);\nuint32_t packed_zeros = *reinterpret_cast<uint32_t *>(zeros + scales_zeros_offset);\n\nuint32_t scale_0 = packed_scales & 0xFF;\nuint32_t zero_point_0 = __byte_perm(packed_zeros, 0, 0x00000000);\nuint32_t ptr_0 = loaded_0 * scale_0;\nuint32_t ptr_1 = loaded_1 * scale_0;\nptr[0] = __vadd4(ptr_0, zero_point_0);\nptr[1] = __vadd4(ptr_1, zero_point_0);\n\nuint32_t scale_1 = (packed_scales & 0xFF00) >> 8;\nuint32_t zero_point_1 = __byte_perm(packed_zeros, 0, 0x00001111);\nuint32_t ptr_2 = loaded_2 * scale_1;\nuint32_t ptr_3 = loaded_3 * scale_1;\nptr[2] = __vadd4(ptr_2, zero_point_1);\nptr[3] = __vadd4(ptr_3, zero_point_1);\n\nuint32_t scale_2 = (packed_scales & 0xFF0000) >> 16;\nuint32_t zero_point_2 = __byte_perm(packed_zeros, 0, 0x00002222);\nuint32_t ptr_4 = loaded_4 * scale_2;\nuint32_t ptr_5 = loaded_5 * scale_2;\nptr[4] = __vadd4(ptr_4, zero_point_2);\nptr[5] = __vadd4(ptr_5, zero_point_2);\n\nuint32_t scale_3 = (packed_scales & 0xFF000000) >> 24;\nuint32_t zero_point_3 = __byte_perm(packed_zeros, 0, 0x00003333);\nuint32_t ptr_6 = loaded_6 * scale_3;\nuint32_t ptr_7 = loaded_7 * scale_3;\nptr[6] = __vadd4(ptr_6, zero_point_3);\nptr[7] = __vadd4(ptr_7, zero_point_3);\n'
_TOKEN = re.compile(r"//[^\n]*|/\*.*?\*/|\s+|0[xX][0-9A-Fa-f]+|[A-Za-z_][A-Za-z_0-9]*|[0-9]+|>>|<<|[()\[\]{}.;,*+&/<>=%-]",re.S)

def tokens(text: str) -> list[str]:
    if type(text) is not str: raise ValueError("source must be text")
    # Backslash line splicing and strings are outside the accepted grammar.
    if "\\" in text: raise ValueError("line splicing/escapes are unsupported")
    out=[]; position=0
    while position<len(text):
        match=_TOKEN.match(text,position)
        if match is None: raise ValueError(f"unknown source token at {position}")
        token=match.group(); position=match.end()
        if token.isspace() or token.startswith("//") or token.startswith("/*"): continue
        out.append(token)
    return out

_EXPECTED_TOKENS=tokens(EXPECTED)

def parse_source(text: str, ledger: ObligationLedger, category: str="source-import") -> dict:
    ledger.charge(f"{category}:parse")
    if tokens(text)!=_EXPECTED_TOKENS:
        raise ValueError("source differs from the complete frozen token sequence")
    return {"accepted":True,"loaded_vectors":8,"whole_word_multiplies":8,"bytewise_corrections":8,
            "scale_bytes":4,"parameter_bounds":{"lane_bits":8,"scale_min":0,"scale_max":255,"digit_min":0,"digit_max":15},
            "method":"complete frozen-token equality, ignoring whitespace and comments only",
            "assumptions":["valid loads and stores", "defined __byte_perm and __vadd4 intrinsic semantics", "no concurrent interference"],
            "trusted_boundary":"No control-flow, alias, memory-safety, MMA, floating-point, or whole-kernel validation."}

def parse_frozen_file(path: Path, ledger: ObligationLedger) -> dict:
    return parse_source(path.read_text(),ledger)

def mutation_suite(text: str, ledger: ObligationLedger) -> dict:
    edits=[
      ("low-mask","0x0F0F0F0F","0x0E0E0E0E"),
      ("high-mask","0xF0F0F0F0","0xE0E0E0E0"),
      ("shift",">> 4",">> 3"),
      ("component","loaded.y","loaded.x"),
      ("duplicate-index","loaded_7 =","loaded_6 ="),
      ("scale-mask","packed_scales & 0xFF;","packed_scales;"),
      ("scale-shift",">> 16",">> 15"),
      ("zero-selector","0x00002222","0x00001111"),
      ("comment-decoy","uint32_t ptr_0 = loaded_0 * scale_0;","/* uint32_t ptr_0 = loaded_0 * scale_0; */ uint32_t ptr_0 = 0;"),
      ("extra-assignment","uint32_t ptr_0 = loaded_0 * scale_0;","uint32_t ptr_0 = loaded_0 * scale_0; ptr_0 = 0;"),
      ("extra-statement","ptr[7] = __vadd4(ptr_7, zero_point_3);","ptr[7] = __vadd4(ptr_7, zero_point_3); unknown();"),
      ("early-store","uint32_t ptr_0 = loaded_0 * scale_0;","ptr[0] = __vadd4(ptr_0, zero_point_0); uint32_t ptr_0 = loaded_0 * scale_0;"),
      ("lost-correction","ptr[7] = __vadd4(ptr_7, zero_point_3);","ptr[7] = ptr_7;"),
      ("destination","ptr[6] = __vadd4(ptr_6, zero_point_3);","ptr[5] = __vadd4(ptr_6, zero_point_3);"),
    ]
    for i in range(8):
        edits.append((f"scale-pair-{i}",f"ptr_{i} = loaded_{i} * scale_{i//2}",f"ptr_{i} = loaded_{i} * scale_{(i//2+1)%4}"))
    records=[]
    for name,old,new in edits:
        if text.count(old)<1: raise ValueError(f"mutation target missing: {name}")
        mutant=text.replace(old,new,1)
        ledger.charge("source-import:mutation")
        rejected=False
        try: parse_source(mutant,ledger,"source-mutant")
        except ValueError: rejected=True
        records.append({"mutation":name,"rejected":rejected})
        if not rejected: raise ValueError(f"source mutant accepted: {name}")
    return {"mutations":len(records),"rejected":sum(x["rejected"] for x in records),"records":records}
