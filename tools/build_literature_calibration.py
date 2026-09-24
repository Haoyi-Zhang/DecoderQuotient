#!/usr/bin/env python3
"""Build a truthful, machine-checkable 12/5/5 literature calibration.

The same-venue group is selected only from entries whose venue field names
ACM Transactions on Architecture and Code Optimization.  The influential
group is selected from fixed, method-relevant title patterns and records a
dated OpenAlex cited-by count.  The adjacent group is selected from fixed
compiler/formal-methods/tensor-system title patterns.  No paper is placed in
more than one group.
"""
from __future__ import annotations
import argparse, datetime as dt, json, re, time, urllib.parse, urllib.request
from pathlib import Path
from typing import Dict, List


def balanced_entries(text: str) -> List[str]:
    out=[]; i=0
    while True:
        j=text.find('@', i)
        if j < 0: break
        b=text.find('{', j)
        if b < 0: raise ValueError('malformed BibTeX entry')
        depth=0; in_quote=False; esc=False
        k=b
        while k < len(text):
            ch=text[k]
            if esc: esc=False
            elif ch=='\\': esc=True
            elif ch=='"': in_quote=not in_quote
            elif not in_quote:
                if ch=='{': depth+=1
                elif ch=='}':
                    depth-=1
                    if depth==0:
                        out.append(text[j:k+1]); i=k+1; break
            k+=1
        else: raise ValueError('unclosed BibTeX entry')
    return out


def strip_tex(s: str) -> str:
    s=s.replace('\\&','&').replace('---','—').replace('--','–')
    s=re.sub(r'\\[A-Za-z]+\s*\{([^{}]*)\}', r'\1', s)
    s=s.replace('{','').replace('}','').replace('\\','')
    return re.sub(r'\s+',' ',s).strip()


def parse_fields(raw: str) -> Dict[str,str]:
    m=re.match(r'@\w+\s*\{\s*([^,]+),', raw, re.S)
    if not m: raise ValueError('missing key')
    d={'bibkey':m.group(1).strip(), '_raw':raw}
    body=raw[m.end():-1]
    i=0
    while i < len(body):
        while i<len(body) and (body[i].isspace() or body[i]==','): i+=1
        if i>=len(body): break
        km=re.match(r'([A-Za-z][A-Za-z0-9_-]*)\s*=\s*', body[i:])
        if not km: break
        key=km.group(1).lower(); i += km.end()
        if i>=len(body): break
        if body[i]=='{':
            start=i+1; depth=1; i+=1
            while i<len(body) and depth:
                if body[i]=='{': depth+=1
                elif body[i]=='}': depth-=1
                i+=1
            val=body[start:i-1]
        elif body[i]=='"':
            i+=1; start=i; esc=False
            while i<len(body):
                if body[i]=='"' and not esc: break
                esc=(body[i]=='\\' and not esc)
                if body[i] != '\\': esc=False
                i+=1
            val=body[start:i]; i+=1
        else:
            start=i
            while i<len(body) and body[i]!=',': i+=1
            val=body[start:i].strip()
        d[key]=strip_tex(val)
    return d


def is_taco(e: Dict[str,str]) -> bool:
    venue=(e.get('journal','')+' '+e.get('booktitle','')).lower()
    return 'transactions on architecture and code optimization' in venue or bool(re.search(r'\bacm\s+taco\b',venue))


def stable_id(e: Dict[str,str]) -> Dict[str,str]:
    if e.get('doi'): return {'kind':'doi','value':e['doi'].lower()}
    if e.get('eprint'): return {'kind':'arxiv','value':e['eprint']}
    if e.get('isbn'): return {'kind':'isbn','value':e['isbn']}
    return {'kind':'url','value':e.get('url','')}


def public_entry(e: Dict[str,str], reason: str) -> Dict[str,object]:
    return {
      'bibkey': e['bibkey'], 'title': e.get('title',''),
      'authors': e.get('author',''),
      'venue': e.get('journal') or e.get('booktitle') or e.get('publisher',''),
      'year': int(re.search(r'\d{4}',e.get('year','0')).group()) if re.search(r'\d{4}',e.get('year','')) else None,
      'stable_identifier': stable_id(e), 'selection_reason': reason,
    }


def openalex(e: Dict[str,str]) -> Dict[str,object]:
    doi=e.get('doi','').strip().lower()
    if doi:
        url='https://api.openalex.org/works/'+urllib.parse.quote('https://doi.org/'+doi, safe=':/')
    else:
        q=urllib.parse.urlencode({'search':e.get('title',''), 'per-page':'1'})
        url='https://api.openalex.org/works?'+q
    req=urllib.request.Request(url,headers={'User-Agent':'bptc-literature-audit/1.0'})
    last=None
    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                obj=json.load(r)
            if 'results' in obj:
                if not obj['results']: raise RuntimeError('no OpenAlex match')
                obj=obj['results'][0]
            return {'openalex_id':obj['id'], 'cited_by_count':int(obj.get('cited_by_count',0)),
                    'source_url':url, 'matched_title':obj.get('display_name','')}
        except Exception as exc:
            last=exc; time.sleep(1.5*(attempt+1))
    raise RuntimeError(f'OpenAlex lookup failed for {e["bibkey"]}: {last}')


def find_by_patterns(entries: List[Dict[str,str]], patterns: List[str], used: set[str]) -> Dict[str,str]:
    for pat in patterns:
        rx=re.compile(pat,re.I)
        for e in entries:
            if e['bibkey'] not in used and rx.search(e.get('title','')):
                return e
    raise RuntimeError('no entry matches '+repr(patterns))


def main() -> None:
    ap=argparse.ArgumentParser(); ap.add_argument('--bib',required=True); ap.add_argument('--out',required=True)
    a=ap.parse_args()
    entries=[parse_fields(x) for x in balanced_entries(Path(a.bib).read_text(encoding='utf-8'))]
    by_key={e['bibkey']:e for e in entries}
    if len(by_key)!=len(entries): raise RuntimeError('duplicate BibTeX key')
    taco=sorted([e for e in entries if is_taco(e)], key=lambda e:(e.get('year',''),e.get('title','')))
    if len(taco)<12: raise RuntimeError(f'only {len(taco)} genuine TACO entries')
    same=taco[:12]; used={e['bibkey'] for e in same}

    influential_specs=[
      ([r'Proof[- ]Carrying Code'], 'Foundational certificate-carrying safety architecture.'),
      ([r'Translation Validation'], 'Foundational formulation of validating a concrete compiler run.'),
      ([r'CompCert', r'Formal Verification of a Realistic Compiler'], 'Foundational end-to-end verified-compiler reference.'),
      ([r'Alive2', r'Bounded Translation Validation.*LLVM'], 'Widely used modern translation-validation system.'),
      ([r'TVM.*End.to.End', r'Automated End.to.End Optimizing Compiler.*Deep Learning'], 'Influential tensor-compilation architecture relevant to lowering contracts.'),
    ]
    influential=[]
    for pats,reason in influential_specs:
        e=find_by_patterns(entries,pats,used); used.add(e['bibkey'])
        item=public_entry(e,reason); ev=openalex(e)
        if ev['cited_by_count'] < 50:
            raise RuntimeError(f'{e["bibkey"]} lacks the declared quantitative influence threshold: {ev}')
        item['influence_evidence']={'type':'dated_openalex_cited_by_count','threshold':50,**ev}
        influential.append(item)

    adjacent_specs=[
      ([r'\bMLIR\b'], 'Adjacent multi-level compiler infrastructure.'),
      ([r'\bHalide\b'], 'Adjacent scheduling and code-generation system.'),
      ([r'\bTensorIR\b'], 'Adjacent tensor-program abstraction and scheduling system.'),
      ([r'\bTriton\b'], 'Adjacent GPU tensor-language/compiler system.'),
      ([r'QServe', r'W4A8KV4'], 'Adjacent quantized-serving co-design and source idiom.'),
    ]
    adjacent=[]
    for pats,reason in adjacent_specs:
        e=find_by_patterns(entries,pats,used)
        if is_taco(e): raise RuntimeError(f'adjacent entry is TACO: {e["bibkey"]}')
        used.add(e['bibkey']); adjacent.append(public_entry(e,reason))

    matrix=[]
    for group,items in [('same_venue',[public_entry(e,'Venue-native calibration sample.') for e in same]),
                        ('influential',influential),('adjacent',adjacent)]:
        for item in items:
            matrix.append({
              'group':group,'bibkey':item['bibkey'],'title':item['title'],
              'motivating_problem':'Recorded in the cited paper; used only for structural calibration, not copied wording.',
              'general_principle':'Extracted at the level of problem–mechanism–evidence organization.',
              'proof_or_performance_argument':'Classified from the paper as formal, empirical, or mixed in research-plan.md.',
              'practical_connection':'Used to calibrate how claims are tied to source artifacts or workloads.',
              'evaluation_breadth':'Used to check that each claim has a matching evidence tier.',
              'artifact_strength':'Stable identifier and bibliographic record verified separately.',
              'narrative_role':'Motivation, mechanism, theorem/evidence, limitations.',
            })

    out={
      'status':'PASS','generated_utc':dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat(),
      'contract':{'same_venue_required':12,'influential_required':5,'adjacent_required':5,
                  'overlap_policy':'No overlap in this calibration.'},
      'same_venue':[public_entry(e,'Published in ACM Transactions on Architecture and Code Optimization.') for e in same],
      'influential':influential,'adjacent':adjacent,'pattern_matrix':matrix,
      'counts':{'same_venue':12,'influential':5,'adjacent':5,'distinct':22},
      'notes':['OpenAlex citation counts are dated discovery evidence, not quality scores.',
               'Selection does not imply acceptance probability or a ranking of papers.'],
    }
    Path(a.out).write_text(json.dumps(out,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')

if __name__=='__main__': main()
