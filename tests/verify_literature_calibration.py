#!/usr/bin/env python3
from __future__ import annotations
import argparse,json,re
from pathlib import Path
from tools.build_literature_calibration import balanced_entries,parse_fields,is_taco

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--bib',required=True);ap.add_argument('--calibration',required=True);ap.add_argument('--out',required=True);a=ap.parse_args()
 entries=[parse_fields(x) for x in balanced_entries(Path(a.bib).read_text(encoding='utf-8'))]; by={e['bibkey']:e for e in entries}
 d=json.loads(Path(a.calibration).read_text(encoding='utf-8'))
 checks=[]
 def ck(name,cond,detail=''):
  checks.append({'name':name,'pass':bool(cond),'detail':detail});
  if not cond: raise AssertionError(f'{name}: {detail}')
 ck('calibration status',d.get('status')=='PASS')
 for group,n in [('same_venue',12),('influential',5),('adjacent',5)]:
  ck(group+' count',len(d.get(group,[]))>=n,str(len(d.get(group,[]))))
 keys=[]
 for group in ('same_venue','influential','adjacent'):
  for x in d[group]:
   k=x.get('bibkey'); keys.append(k); ck(k+' exists',k in by)
   sid=x.get('stable_identifier',{}); ck(k+' stable id',bool(sid.get('value')))
 ck('22 distinct selections',len(keys)==len(set(keys))==22,str(keys))
 for x in d['same_venue']: ck(x['bibkey']+' is TACO',is_taco(by[x['bibkey']]),x.get('venue',''))
 for x in d['adjacent']: ck(x['bibkey']+' is adjacent',not is_taco(by[x['bibkey']]),x.get('venue',''))
 for x in d['influential']:
  ev=x.get('influence_evidence',{}); ck(x['bibkey']+' dated OpenAlex evidence',ev.get('type')=='dated_openalex_cited_by_count')
  ck(x['bibkey']+' influence threshold',int(ev.get('cited_by_count',0))>=int(ev.get('threshold',50)),str(ev))
 ck('pattern matrix size',len(d.get('pattern_matrix',[]))==22)
 out={'status':'PASS','checks':checks,'counts':d['counts']}
 Path(a.out).write_text(json.dumps(out,indent=2,ensure_ascii=False)+'\n')
if __name__=='__main__': main()
