#!/usr/bin/env python3
from __future__ import annotations
import argparse,json
from pathlib import Path

def flatten(x,p=''):
 out={}
 if isinstance(x,dict):
  for k,v in x.items(): out.update(flatten(v,f'{p}.{k}' if p else k))
 elif isinstance(x,list):
  # Lists are evidence objects; expose length and scalar items only.
  out[p+'.length' if p else 'length']=len(x)
  for i,v in enumerate(x):
   if not isinstance(v,(dict,list)): out[f'{p}[{i}]']=v
 else: out[p]=x
 return out

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--root',default='.');ap.add_argument('--out',required=True);a=ap.parse_args()
 root=Path(a.root)
 summary=json.loads((root/'results/publication/combined-summary.json').read_text())
 budget=json.loads((root/'results/publication/budget.json').read_text())
 claims=[
  {'id':'C1','claim':'For the frozen source-bounded packed decoder, the monotone carry envelope is a necessary-and-sufficient universal lane-isolation test and yields a least counterexample under the declared order.',
   'status':'proved-in-writing-and-executable-replay','proof':'proofs/packed-decoder-closed-form.md','producer':'bptc/packed_decoder.py','checker':'bptc/packed_decoder.py','tests':['tests/test_publication_core.py'],'results':['results/publication/main/decoder-cases.csv']},
  {'id':'C2','claim':'Product quotienting preserves exact accumulator reachability, monitored observations, and lexicographically least counterexamples for the declared finite schedule semantics.',
   'status':'proved-in-writing-and-independently-replayed','proof':'proofs/exact-accumulator-certificates.md','producer':'bptc/exact_accumulator.py','checker':'bptc/accumulator_checker.py','oracle':'bptc/accumulator_oracle.py','tests':['tests/test_publication_core.py'],'results':['results/publication/main/accumulator-cases.csv']},
  {'id':'C3','claim':'The narrow importer recognizes and cross-checks the declared eight-lane nibble/multiply/byte-add idiom in one immutable OmniServe source excerpt; it does not validate the whole CUDA kernel or binary.',
   'status':'source-anchored-structural-validation','proof':'proofs/source-import-boundary.md','source':'inputs/omniserve/share_to_reg_one_stage_B.cu','license':'inputs/omniserve/LICENSE','parser':'bptc/source_anchor.py','provenance':'evidence/source-provenance-live.json'},
  {'id':'C4','claim':'The no-overflow guard is sound but incomplete, and a final-range-only heuristic is unsound, for the declared observation semantics.',
   'status':'counterexample-backed','proof':'proofs/exact-accumulator-certificates.md','implementation':'bptc/accumulator_baselines.py','results':['results/publication/main/accumulator-cases.csv']},
  {'id':'C5','claim':'Prospective main evidence and clean reproduction share a fail-closed obligation ledger below the frozen 200,000-event ceiling; the historical 209,282 lower bound is segregated.',
   'status':'ledger-backed','implementation':'bptc/publication_budget.py','budget':'results/publication/budget.json','reproduction':'results/publication/reproduction'},
 ]
 required=[]
 for c in claims:
  for k,v in c.items():
   if k in {'proof','producer','checker','oracle','source','license','parser','provenance','implementation','budget','reproduction'}: required.append(v)
   elif k in {'tests','results'}: required.extend(v)
 missing=[x for x in required if not (root/x).exists()]
 if missing: raise SystemExit('traceability targets missing: '+repr(missing))
 out={'status':'PASS','scope':'Frozen integer decoder, mixed-width scalar accumulator schedule, and narrow source idiom only.',
      'claims':claims,'empirical_snapshot':flatten(summary),'budget_snapshot':flatten(budget),
      'nonclaims':['No whole-program C++/CUDA/PTX validation.','No floating-point scale or attention semantics.',
                   'No GPU throughput, serving speed, or model-quality result.','Written proofs are not proof-assistant mechanizations.',
                   'Passing finite checks is not presented as a general proof.']}
 Path(a.out).write_text(json.dumps(out,indent=2,ensure_ascii=False)+'\n')
if __name__=='__main__': main()
