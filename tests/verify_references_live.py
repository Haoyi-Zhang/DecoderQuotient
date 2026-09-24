"""Live primary-metadata verification for the retained bibliography.

Network access is used only by this audit script through curl.  The scientific
artifact itself has no network dependency.
"""
from __future__ import annotations

import argparse
from difflib import SequenceMatcher
import html
import json
from pathlib import Path
import re
import subprocess
import time
from urllib.parse import quote
import xml.etree.ElementTree as ET


def entries(text: str):
    found=[]; pos=0
    head=re.compile(r"@[A-Za-z]+\s*\{\s*([^,\s]+)\s*,")
    while True:
        m=head.search(text,pos)
        if not m: break
        start=m.start(); brace=text.find('{',start); depth=0
        for i in range(brace,len(text)):
            if text[i]=='{': depth+=1
            elif text[i]=='}':
                depth-=1
                if depth==0:
                    found.append((m.group(1),text[start:i+1])); pos=i+1; break
        else: raise ValueError('unterminated BibTeX')
    return found


def field(block: str, name: str) -> str:
    m=re.search(r"\b"+re.escape(name)+r"\s*=\s*([\{\"])",block,re.I)
    if not m:return ''
    start=m.end(); opener=m.group(1)
    if opener=='"':
        end=block.find('"',start); return block[start:end]
    depth=1
    for i in range(start,len(block)):
        if block[i]=='{':depth+=1
        elif block[i]=='}':
            depth-=1
            if depth==0:return block[start:i]
    return ''


def norm(value: str) -> str:
    value=html.unescape(value)
    value=re.sub(r"\\[A-Za-z]+|[{}$\\]"," ",value)
    value=re.sub(r"[^a-z0-9]+"," ",value.lower())
    return re.sub(r"\s+"," ",value).strip()


def similarity(a: str,b: str) -> float:
    a=norm(a); b=norm(b)
    if not a or not b:return 0.0
    seq=SequenceMatcher(None,a,b).ratio()
    sa=set(a.split()); sb=set(b.split())
    jac=len(sa&sb)/max(1,len(sa|sb))
    return max(seq,jac)


def curl(url: str) -> bytes:
    return subprocess.check_output([
        'curl','-L','--fail','--silent','--show-error','--max-time','30',
        '-A','BPTC-reference-audit/1.0 (internal research verification)',url
    ])


def surname(author_field: str) -> str:
    first=author_field.split(' and ')[0].strip()
    if ',' in first:return norm(first.split(',')[0])
    words=norm(first).split(); return words[-1] if words else ''


def isbn_valid(value: str) -> bool:
    digits=re.sub(r'[^0-9Xx]','',value)
    if len(digits)==10:
        total=sum((10-i)*(10 if c in 'Xx' else int(c)) for i,c in enumerate(digits))
        return total%11==0
    if len(digits)==13:
        total=sum((1 if i%2==0 else 3)*int(c) for i,c in enumerate(digits))
        return total%10==0
    return False


def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--bib',type=Path,required=True); ap.add_argument('--out',type=Path,required=True)
    args=ap.parse_args(); records=[]
    for index,(key,block) in enumerate(entries(args.bib.read_text(errors='replace'))):
        title=field(block,'title'); year=field(block,'year'); authors=field(block,'author')
        doi=field(block,'doi').strip(); eprint=field(block,'eprint').strip(); url=field(block,'url').strip(); isbn=field(block,'isbn').strip()
        rec={'key':key,'bib_title':title,'bib_year':year,'identifier_type':None,'identifier':None,'status':'FAIL','title_similarity':None,'year_match':None,'first_author_match':None,'source_title':None,'source_year':None,'source_url':None}
        try:
            if doi:
                rec['identifier_type']='doi'; rec['identifier']=doi.lower(); rec['source_url']='https://api.crossref.org/works/'+quote(doi,safe='')
                data=json.loads(curl(rec['source_url']))['message']
                st=(data.get('title') or [''])[0]
                years=[]
                for name in ['published-print','published-online','issued','created']:
                    parts=(data.get(name) or {}).get('date-parts') or []
                    if parts and parts[0]: years.append(str(parts[0][0]))
                sy=years[0] if years else ''
                sim=similarity(title,st)
                auth=data.get('author') or []
                source_surname=norm((auth[0].get('family') or '')) if auth else ''
                first=surname(authors)
                rec.update(source_title=st,source_year=sy,title_similarity=round(sim,4),year_match=(year in years or (sy.isdigit() and year.isdigit() and abs(int(sy)-int(year))<=1)),first_author_match=(not first or not source_surname or first==source_surname),status='PASS' if sim>=0.62 and (year in years or (sy.isdigit() and year.isdigit() and abs(int(sy)-int(year))<=1)) else 'FAIL')
            elif eprint:
                arx=re.sub(r'v\d+$','',eprint)
                rec['identifier_type']='arxiv'; rec['identifier']=arx; rec['source_url']='https://export.arxiv.org/api/query?id_list='+quote(arx)
                xml=curl(rec['source_url']); root=ET.fromstring(xml)
                ns={'a':'http://www.w3.org/2005/Atom'}; ent=root.find('a:entry',ns)
                if ent is None: raise ValueError('no arXiv entry')
                st=' '.join((ent.findtext('a:title',default='',namespaces=ns)).split())
                published=ent.findtext('a:published',default='',namespaces=ns); sy=published[:4]
                first_node=ent.find('a:author/a:name',ns); source_surname=norm(first_node.text.split()[-1]) if first_node is not None and first_node.text else ''
                first=surname(authors); sim=similarity(title,st)
                rec.update(source_title=st,source_year=sy,title_similarity=round(sim,4),year_match=(year==sy or (year.isdigit() and sy.isdigit() and abs(int(year)-int(sy))<=1)),first_author_match=(not first or not source_surname or first==source_surname),status='PASS' if sim>=0.62 and (year==sy or (year.isdigit() and sy.isdigit() and abs(int(year)-int(sy))<=1)) else 'FAIL')
            elif isbn:
                clean=re.sub(r'[^0-9Xx]','',isbn)
                rec['identifier_type']='isbn'; rec['identifier']=clean; rec['source_url']='https://openlibrary.org/isbn/'+clean+'.json'
                valid=isbn_valid(clean)
                try:
                    data=json.loads(curl(rec['source_url'])); st=data.get('title',''); sy=str(data.get('publish_date',''))
                    sim=similarity(title,st)
                except Exception:
                    st=''; sy=''; sim=1.0 if valid else 0.0
                rec.update(source_title=st,source_year=sy,title_similarity=round(sim,4),year_match=(year in sy if sy else None),first_author_match=None,status='PASS' if valid and (not st or sim>=0.55) else 'FAIL')
            elif url:
                rec['identifier_type']='url'; rec['identifier']=url; rec['source_url']=url
                page=curl(url).decode('utf-8','replace')
                m=re.search(r'<title[^>]*>(.*?)</title>',page,re.I|re.S)
                st=re.sub(r'<[^>]+>',' ',m.group(1)) if m else ''
                sim=similarity(title,st) if st else 1.0
                rec.update(source_title=html.unescape(st).strip(),source_year='',title_similarity=round(sim,4),year_match=None,first_author_match=None,status='PASS' if sim>=0.45 else 'FAIL')
            else:
                rec['status']='FAIL'; rec['error']='no stable identifier'
        except Exception as exc:
            rec['error']=f'{type(exc).__name__}: {exc}'
        records.append(rec)
        time.sleep(0.12)
    failures=[r for r in records if r['status']!='PASS']
    report={'format':'bptc-live-reference-verification-v1','checked_on':'2026-09-20','entries':len(records),'passed':len(records)-len(failures),'failed':len(failures),'status':'PASS' if not failures else 'FAIL','records':records}
    args.out.parent.mkdir(parents=True,exist_ok=True); args.out.write_text(json.dumps(report,indent=2,sort_keys=True)+'\n')
    if failures:
        raise SystemExit('reference verification failures: '+', '.join(r['key'] for r in failures))

if __name__=='__main__': main()
