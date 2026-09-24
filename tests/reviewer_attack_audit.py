#!/usr/bin/env python3
"""Fail-closed audit of the most likely reviewer objections.

This is not peer review.  It checks traceability, evidence separation,
independent replay structure, case diversity, reference provenance, source
provenance, exact page contract, and explicit non-claims.
"""
from __future__ import annotations
import argparse,ast,csv,json,re,subprocess,sys
from pathlib import Path
from typing import Any

def walk(x:Any,p=''):
 if isinstance(x,dict):
  for k,v in x.items(): yield from walk(v,f'{p}.{k}' if p else k)
 elif isinstance(x,list):
  for i,v in enumerate(x): yield from walk(v,f'{p}[{i}]')
 else: yield p,x

def load(p): return json.loads(Path(p).read_text(encoding='utf-8'))

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--root',default='.');ap.add_argument('--project-root');ap.add_argument('--out',required=True);a=ap.parse_args()
 root=Path(a.root).resolve(); project=Path(a.project_root).resolve() if a.project_root else root.parent
 checks=[]
 def ck(name,cond,detail=''):
  checks.append({'name':name,'pass':bool(cond),'detail':str(detail)[:2000]})
  if not cond: raise AssertionError(f'{name}: {detail}')

 # Claim/evidence traceability.
 trace=load(root/'evidence/claim-traceability.json')
 ck('claim traceability status',trace.get('status')=='PASS')
 ck('claim count',len(trace.get('claims',[]))>=5,len(trace.get('claims',[])))
 ck('explicit nonclaims',len(trace.get('nonclaims',[]))>=5)
 for c in trace['claims']:
  ck('claim id '+str(c.get('id')),bool(c.get('claim')) and bool(c.get('status')))

 # Prospective resource ledger and historical segregation.
 budget=load(root/'results/publication/budget.json')
 leaves=dict(walk(budget))
 used_candidates=[int(v) for k,v in leaves.items() if isinstance(v,(int,float)) and k.lower().endswith(('events_used','used_events'))]
 limit_candidates=[int(v) for k,v in leaves.items() if isinstance(v,(int,float)) and k.lower().endswith(('limit','event_limit','events_limit'))]
 ck('budget exposes used events',bool(used_candidates),list(leaves)[:20])
 ck('budget exposes limit',bool(limit_candidates),list(leaves)[:20])
 used=max(used_candidates); limit=max(limit_candidates)
 ck('prospective budget within ceiling',used<=limit<=200000,f'{used}/{limit}')
 status=' '.join(str(v) for k,v in leaves.items() if 'status' in k.lower()).lower()
 ck('budget status pass',any(x in status for x in ('pass','within','complete')),status)
 readme=(root/'README.md').read_text(encoding='utf-8')
 state_file=project/'CURRENT-STATE.md'
 state_text=state_file.read_text(encoding='utf-8') if state_file.exists() else readme+'\n'+(root/'proofs/claim-boundary.md').read_text(encoding='utf-8')
 for token in ('209,282','historical','200,000'):
  ck('historical segregation '+token,token.lower() in (state_text+'\n'+readme).lower())

 # Deterministic main/reproduction agreement recorded by the campaign.
 combined=load(root/'results/publication/combined-summary.json')
 agreement=[(k,v) for k,v in walk(combined) if isinstance(v,bool) and re.search(r'(agree|identical|match|reproduc)',k,re.I)]
 ck('agreement flags present',bool(agreement),agreement)
 ck('all agreement flags true',all(v for _,v in agreement),agreement)
 disagreements=[(k,v) for k,v in walk(combined) if isinstance(v,(int,float)) and re.search(r'(cross.*disagree|producer.*disagree|checker.*disagree|oracle.*disagree|mismatch)',k,re.I)]
 ck('cross-check disagreement counters present',bool(disagreements),list(dict(walk(combined)))[:30])
 ck('zero cross-check disagreements',all(float(v)==0 for _,v in disagreements),disagreements)

 # Case breadth is declared rather than inferred from prose.
 acc_rows=list(csv.DictReader((root/'results/publication/main/accumulator-cases.csv').open(newline='',encoding='utf-8')))
 dec_rows=list(csv.DictReader((root/'results/publication/main/decoder-cases.csv').open(newline='',encoding='utf-8')))
 ck('accumulator case count',len(acc_rows)>=64,len(acc_rows))
 ck('decoder case count',len(dec_rows)>=30,len(dec_rows))
 famcols=[c for c in acc_rows[0] if 'family' in c.lower()]
 ck('accumulator family column',bool(famcols),list(acc_rows[0]))
 families={r[famcols[0]] for r in acc_rows}
 ck('accumulator semantic families',len(families)>=8,sorted(families))
 serialized=json.dumps(acc_rows).lower()
 ck('wrap schedules represented','wrap' in serialized)
 ck('saturating schedules represented',('saturat' in serialized or 'sat' in serialized))
 # Baseline failure modes must be observed, not merely discussed.
 numeric=dict((k,float(v)) for k,v in walk(combined) if isinstance(v,(int,float)))
 false_reject=[v for k,v in numeric.items() if re.search(r'(sufficient|no.?overflow).*false.?reject',k,re.I)]
 false_accept=[v for k,v in numeric.items() if re.search(r'(final.?range).*false.?accept',k,re.I)]
 ck('sound guard incompleteness witnessed',bool(false_reject) and max(false_reject)>0,false_reject)
 ck('final-range heuristic unsoundness witnessed',bool(false_accept) and max(false_accept)>0,false_accept)

 # Scalability descriptors and honest worst-case boundary.
 scale=load(root/'results/publication/scalability-audit.json')
 ck('scalability audit pass',scale.get('status')=='PASS')
 ck('multiple scale metrics',len(scale.get('reported_metrics',[]))>=4)
 paper_text=''
 main_pdf=project/'paper/main.pdf'
 if main_pdf.exists():
  cp=subprocess.run(['pdftotext','-layout',str(main_pdf),'-'],capture_output=True,text=True,check=True); paper_text=cp.stdout
  for phrase in ('exponentially','confidence intervals','not claimed as proof-assistant','209,282','No GPU','generative-AI'):
   ck('paper discloses '+phrase,phrase.lower() in paper_text.lower())

 # Independent implementation boundary: sharing data types is allowed; reusing
 # producer transitions/builders is not.
 checker_src=(root/'bptc/accumulator_checker.py').read_text(encoding='utf-8')
 oracle_src=(root/'bptc/accumulator_oracle.py').read_text(encoding='utf-8')
 checker_tree=ast.parse(checker_src); oracle_tree=ast.parse(oracle_src)
 forbidden=re.compile(r'(transition|advance|produce|build_certificate|generate_certificate)',re.I)
 bad=[]
 for tree,label in ((checker_tree,'checker'),(oracle_tree,'oracle')):
  for node in ast.walk(tree):
   if isinstance(node,ast.ImportFrom) and node.module and node.module.endswith('exact_accumulator'):
    for n in node.names:
     if forbidden.search(n.name): bad.append((label,n.name))
 ck('no producer transition reuse',not bad,bad)
 checker_defs={n.name.lower() for n in checker_tree.body if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef))}
 ck('checker owns arithmetic semantics',sum(any(t in n for t in ('wrap','satur','convert','step','apply')) for n in checker_defs)>=2,checker_defs)
 oracle_defs={n.name.lower() for n in oracle_tree.body if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef))}
 ck('oracle owns executable semantics',sum(any(t in n for t in ('wrap','satur','convert','eval','run','oracle')) for n in oracle_defs)>=2,oracle_defs)

 # Proof statements contain the key obligations and status boundary.
 proofs={
  'decoder':(root/'proofs/packed-decoder-closed-form.md').read_text().lower(),
  'accumulator':(root/'proofs/exact-accumulator-certificates.md').read_text().lower(),
 }
 for term in ('necessary','sufficient','least','carry','induction'):
  ck('decoder proof term '+term,term in proofs['decoder'])
 for term in ('quotient','reachability','observation','lexicographic','induction','checker'):
  ck('accumulator proof term '+term,term in proofs['accumulator'])

 # Frozen source and live provenance.
 prov=load(root/'evidence/source-provenance-live.json')
 ck('source provenance pass',prov.get('status')=='PASS')
 ck('source excerpt exact',prov.get('excerpt_exact_normalized_substring') is True)
 ck('upstream license exact',prov.get('license_exact_normalized_match') is True)
 ck('source scope narrow','narrow' in str(prov.get('scope','')).lower())
 anchor_text=(root/'bptc/source_anchor.py').read_text()
 for token in ('0x0F0F0F0F','__vadd4','packed_scales','packed_zeros'):
  ck('source parser token '+token,token in anchor_text or token in (root/'inputs/omniserve/share_to_reg_one_stage_B.cu').read_text())

 # Bibliography identity, online resolution, and calibration.
 ref=load(root/'evidence/reference-verification-live.json')
 ck('live bibliography audit pass',ref.get('status')=='PASS',ref.get('failed'))
 entries=int(ref.get('entries',0)); passed=int(ref.get('passed',-1)); failed=int(ref.get('failed',-1))
 ck('all bibliography records resolved',entries>=60 and passed==entries and failed==0,(entries,passed,failed))
 lit=load(root/'evidence/publication-literature-calibration.json')
 ck('literature calibration pass',lit.get('status')=='PASS')
 ck('12 true same-venue papers',len(lit.get('same_venue',[]))==12)
 ck('5 influence-evidenced papers',len(lit.get('influential',[]))==5)
 ck('5 adjacent papers',len(lit.get('adjacent',[]))==5)
 allkeys=[x['bibkey'] for g in ('same_venue','influential','adjacent') for x in lit[g]]
 ck('22 nonoverlapping calibration papers',len(allkeys)==len(set(allkeys))==22)
 ck('influence evidence dated',all(x.get('influence_evidence',{}).get('cited_by_count',0)>=50 for x in lit['influential']))

 # Paper-facing hygiene and page contract.
 if main_pdf.exists():
  info=subprocess.run(['pdfinfo',str(main_pdf)],capture_output=True,text=True,check=True).stdout
  m=re.search(r'^Pages:\s+(\d+)',info,re.M); ck('main PDF page count parsed',bool(m),info)
  ck('main contains references after content',int(m.group(1))>20,m.group(1))
  # Page 21 must begin the references section; check_pdf.py performs the exact extraction too.
  page21=subprocess.run(['pdftotext','-f','21','-l','21',str(main_pdf),'-'],capture_output=True,text=True,check=True).stdout
  ck('references begin page 21','references' in page21.lower(),page21[:200])
  ck('anonymous PDF metadata','author:' not in info.lower() or not re.search(r'^Author:\s*\S',info,re.M))

 # Venue evidence and external-use boundary.
 venue=load(root/'evidence/venue-rule-verification-live.json')
 ck('official venue pages reachable',venue.get('status')=='PASS',venue)
 ck('AI accountability state',('generative' in state_text.lower() and 'human' in state_text.lower()) or 'generative-ai' in paper_text.lower())

 out={'status':'PASS','checks':checks,'summary':{'checks_passed':len(checks),'budget_events_used':used,'budget_limit':limit,
      'accumulator_cases':len(acc_rows),'decoder_cases':len(dec_rows),'semantic_families':len(families),
      'bibliography_entries':entries,'calibration_distinct':22},
      'disclaimer':'This fail-closed self-audit is not independent peer review and does not predict acceptance.'}
 Path(a.out).write_text(json.dumps(out,indent=2,ensure_ascii=False)+'\n')
 print(f'reviewer attack audit: PASS ({len(checks)} checks)')
if __name__=='__main__': main()
