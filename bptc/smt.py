"""Direct QF_BV baseline through the public Z3 C API.

The solver is not in the certificate checker's trusted computing base. The
encoding performs whole-word arithmetic, not the certificate carry recurrence.
"""
from __future__ import annotations
import ctypes
import re
from pathlib import Path


def _bv(n: int,b: int) -> str:
    return f'(_ bv{n % (1<<b)} {b})'


def encode(domains: list[list[int]], bits: int, scale: int, zero: int, mode: str) -> str:
    lanes=len(domains);width=bits*lanes
    lines=['(set-option :timeout 2000)','(set-option :smt.random_seed 0)',
           '(set-option :sat.random_seed 0)','(set-logic QF_BV)']
    for i,(low,high) in enumerate(domains):
        lines += [f'(declare-const q{i} (_ BitVec {bits}))',
                  f'(assert (and (bvuge q{i} {_bv(low,bits)}) (bvule q{i} {_bv(high,bits)})))']
    fields=[f'q{i}' if mode!='sub_mul' else f'(bvsub q{i} {_bv(zero,bits)})' for i in range(lanes)]
    packed=fields[-1]
    for f in reversed(fields[:-1]):packed=f'(concat {packed} {f})'
    word=f'(bvmul {packed} {_bv(scale,width)})'
    if mode in ('word_sub','word_affine'):
        offset=scale*zero
        if mode=='word_sub':offset %= 1<<bits
        correction=sum(offset*(1<<bits)**i for i in range(lanes))
        word=f'(bvsub {word} {_bv(correction,width)})'
    lines.append(f'(define-fun word () (_ BitVec {width}) {word})')
    differences=[]
    for i in range(lanes):
        qwide=f'((_ zero_extend {32-bits}) q{i})' if bits!=32 else f'q{i}'
        source=f'(bvmul (bvsub {qwide} {_bv(zero,32)}) {_bv(scale,32)})'
        digit=f'((_ extract {(i+1)*bits-1} {i*bits}) word)'
        if mode=='mul_sub':digit=f'(bvsub {digit} {_bv(scale*zero,bits)})'
        if mode=='sat_mul_sub':
            product=f'(bvmul {qwide} {_bv(scale,32)})'
            upper=(1<<(bits-1))-1
            sat=f'(ite (bvugt {product} {_bv(upper,32)}) {_bv(upper,32)} {product})'
            narrow=f'((_ extract {bits-1} 0) {sat})'
            digit=f'(bvsub {narrow} {_bv(scale*zero,bits)})'
        target=f'((_ sign_extend {32-bits}) {digit})' if bits!=32 else digit
        differences.append(f'(not (= {target} {source}))')
    lines += [f'(assert (or {" ".join(differences)}))','(check-sat)']
    return '\n'.join(lines)+'\n'


class Solver:
    def __init__(self, path: Path | None = None):
        path=path or Path(__file__).resolve().parents[1]/'vendor/libz3.so.4'
        self.lib=ctypes.CDLL(str(path))
        z=self.lib
        z.Z3_mk_config.restype=ctypes.c_void_p
        z.Z3_mk_context.argtypes=[ctypes.c_void_p];z.Z3_mk_context.restype=ctypes.c_void_p
        z.Z3_eval_smtlib2_string.argtypes=[ctypes.c_void_p,ctypes.c_char_p]
        z.Z3_eval_smtlib2_string.restype=ctypes.c_char_p
        z.Z3_del_context.argtypes=[ctypes.c_void_p];z.Z3_del_config.argtypes=[ctypes.c_void_p]

    def check(self,text: str) -> str:
        z=self.lib;cfg=z.Z3_mk_config();ctx=z.Z3_mk_context(cfg)
        try:
            answer=z.Z3_eval_smtlib2_string(ctx,text.encode('ascii')).decode('utf-8')
            result=answer.strip().splitlines()
            if len(result)!=1 or result[0] not in ('sat','unsat','unknown'):
                raise RuntimeError('unexpected solver result: '+answer[:200])
            return result[0]
        finally:
            z.Z3_del_context(ctx);z.Z3_del_config(cfg)
