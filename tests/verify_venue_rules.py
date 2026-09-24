#!/usr/bin/env python3
from __future__ import annotations
import datetime as dt, html, json, re, urllib.request
from pathlib import Path
URLS=[
 'https://dl.acm.org/journal/taco/author-guidelines',
 'https://www.acm.org/publications/authors/submissions',
]

def get(url):
 req=urllib.request.Request(url,headers={'User-Agent':'Mozilla/5.0 bptc-venue-audit/1.0'})
 with urllib.request.urlopen(req,timeout=45) as r:
  raw=r.read().decode('utf-8','replace'); code=getattr(r,'status',200); final=r.geturl()
 text=re.sub(r'<script\b.*?</script>|<style\b.*?</style>',' ',raw,flags=re.I|re.S)
 text=re.sub(r'<[^>]+>',' ',text); text=html.unescape(text); text=re.sub(r'\s+',' ',text).strip()
 return code,final,text

def contexts(text,patterns,n=150):
 out=[]
 for pat in patterns:
  for m in re.finditer(pat,text,re.I):
   c=text[max(0,m.start()-n):min(len(text),m.end()+n)]
   c=re.sub(r'\s+',' ',c).strip()
   if c not in out: out.append(c)
 return out[:8]

records=[]
for u in URLS:
 try:
  code,final,text=get(u)
  records.append({'url':u,'http_status':code,'final_url':final,'text_length':len(text),
    'page_limit_contexts':contexts(text,[r'20\s+pages?',r'25\s+pages?',r'page\s+limit']),
    'review_contexts':contexts(text,[r'double.{0,20}blind',r'anonym',r'review']),
    'supplement_contexts':contexts(text,[r'supplement',r'additional\s+files?'])})
 except Exception as e:
  records.append({'url':u,'error':type(e).__name__+': '+str(e)})
# The supplied project contract remains authoritative for the internal 20-page target.
# We record live evidence but do not convert absence in a dynamic page into a fabricated rule.
page_evidence=any(r.get('page_limit_contexts') for r in records)
reachable=all('error' not in r for r in records)
status='PASS' if reachable else 'HOLD'
out={'status':status,'retrieved_utc':dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat(),
     'records':records,'live_page_limit_text_found':page_evidence,
     'internal_contract':'20 content pages; references excluded, as frozen in research-plan.md',
     'note':'Dynamic publisher pages are recorded as retrieval evidence; absence of a phrase is not treated as proof of a contrary rule.'}
Path('evidence/venue-rule-verification-live.json').write_text(json.dumps(out,indent=2,ensure_ascii=False)+'\n')
if not reachable: raise SystemExit(2)
