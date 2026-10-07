"""Unquotiented exact DP using (mathematical sum, actual value, bad, first).

No import from the producer/checker and no product-class construction. Input
is the canonical well-formed suite declaration, not an untrusted certificate.
"""
from .publication_budget import ObligationLedger

def convert(x,w,mode):
    lo=-(2**(w-1)); hi=2**(w-1)-1
    if mode=="saturate": return max(lo,min(hi,x))
    if mode!="wrap": raise ValueError("mode")
    return (x-lo)%(2**w)+lo

def solve(spec, ledger: ObligationLedger, category="direct-state"):
    stages=spec["stages"]
    first=stages[0]
    start=(spec["initial"],convert(spec["initial"],first["acc_bits"],first["acc_mode"]),False,-1)
    current={start:()}; transitions=0
    for i,stage in enumerate(stages):
        following={}
        for (target,actual,bad,first_bad),prefix in sorted(current.items()):
            for j,(left,right) in enumerate(stage["pairs"]):
                ledger.charge(f"{category}:pair-transition");transitions+=1
                p=left*right; total=target+p
                value=convert(actual+convert(p,stage["term_bits"],stage["term_mode"]),stage["acc_bits"],stage["acc_mode"])
                observed=stage["observe"] or (spec["final_observe"] and i==len(stages)-1)
                fail=observed and value!=convert(total,stage["acc_bits"],stage["acc_mode"])
                state=(total,value,bad or fail,i if fail and not bad else first_bad)
                word=prefix+(j,)
                if state not in following or word<following[state]:following[state]=word
        current=following
    failing=[(word,state) for state,word in current.items() if state[2]]
    least=min(failing,default=None)
    cex=None
    if least is not None:
        word,state=least
        cex={"indices":list(word),"pairs":[stages[i]["pairs"][j] for i,j in enumerate(word)],"first_bad_stage":state[3]}
    return {"equivalent":least is None,"least_counterexample":cex,"transitions":transitions,"reachable_final_states":len(current)}
