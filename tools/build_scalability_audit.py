#!/usr/bin/env python3
from __future__ import annotations
import argparse,csv,json,math,statistics,re
from pathlib import Path

def num(v):
 try:
  if v is None or str(v).strip()=='' or str(v).lower() in {'true','false','none','nan'}: return None
  x=float(v)
  return x if math.isfinite(x) else None
 except: return None

def esc(s): return str(s).replace('\\','\\textbackslash{}').replace('_','\\_').replace('%','\\%').replace('&','\\&')

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--csv',required=True);ap.add_argument('--json-out',required=True);ap.add_argument('--tex-out',required=True);a=ap.parse_args()
 with open(a.csv,newline='',encoding='utf-8') as f: rows=list(csv.DictReader(f))
 if not rows: raise SystemExit('empty accumulator CSV')
 cols=list(rows[0])
 stats=[]
 keywords=re.compile(r'(state|layer|class|quot|pair|word|transition|edge|node|stage|time|rss|memory|domain|witness)',re.I)
 for c in cols:
  vals=[num(r.get(c)) for r in rows]; vals=[x for x in vals if x is not None]
  if vals and keywords.search(c):
   stats.append({'metric':c,'count':len(vals),'min':min(vals),'median':statistics.median(vals),'max':max(vals),'sum':sum(vals)})
 if len(stats)<4 or not any(re.search(r'(state|quot|class)',x['metric'],re.I) for x in stats):
  raise SystemExit('CSV does not expose enough reviewer-auditable scalability metrics: '+repr(cols))
 # Prefer semantically informative metrics and cap table length.
 priority=[]
 for s in stats:
  score=sum(10 for p in ('state','quot','class','pair','word','transition','stage','time','rss') if p in s['metric'].lower())
  priority.append((score,s))
 chosen=[x for _,x in sorted(priority,key=lambda z:(-z[0],z[1]['metric']))[:10]]
 out={'status':'PASS','cases':len(rows),'columns':cols,'numeric_metrics':stats,'reported_metrics':chosen,
      'note':'Statistics summarize deterministic case descriptors, not sampled performance populations.'}
 Path(a.json_out).write_text(json.dumps(out,indent=2,ensure_ascii=False)+'\n')
 lines=[r'\\begin{table}[t]',r'\\caption{Deterministic scale descriptors exposed by the retained accumulator cases. Medians summarize the fixed case suite; they are not statistical estimates.}',r'\\label{tab:scalability-audit}',r'\\centering',r'\\small',r'\\begin{tabular}{lrrr}',r'\\toprule',r'Metric & Min. & Median & Max. \\\\',r'\\midrule']
 def fmt(x):
  if abs(x-round(x))<1e-9:return f'{int(round(x)):,}'
  return f'{x:.3g}'
 for s in chosen: lines.append(f"\\texttt{{{esc(s['metric'])}}} & {fmt(s['min'])} & {fmt(s['median'])} & {fmt(s['max'])} \\\\")
 lines += [r'\\bottomrule',r'\\end{tabular}',r'\\end{table}']
 Path(a.tex_out).write_text('\n'.join(lines)+'\n')
if __name__=='__main__': main()
