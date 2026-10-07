"""Parse the supplied brace-delimited BibTeX records for offline consistency checks."""
from pathlib import Path
import re,json

def parse(text):
    entries=[]
    pattern=re.compile(r'@(\w+)\s*\{\s*([^,]+),')
    pos=0
    while (m:=pattern.search(text,pos)):
        d=1;i=m.end()
        while i<len(text) and d:
            if text[i]=='{' and (i==0 or text[i-1]!='\\'):d+=1
            elif text[i]=='}' and (i==0 or text[i-1]!='\\'):d-=1
            i+=1
        if d:raise ValueError('unbalanced entry '+m[2])
        raw=text[m.end():i-1];fields={};k=0
        fp=re.compile(r'\s*,?\s*(\w+)\s*=\s*')
        while k<len(raw):
            f=fp.match(raw,k)
            if not f:break
            k=f.end();start=k
            if raw[k]=='{':
                depth=1;k+=1;start=k
                while k<len(raw) and depth:
                    if raw[k]=='{' and (k==0 or raw[k-1]!='\\'):depth+=1
                    elif raw[k]=='}' and (k==0 or raw[k-1]!='\\'):depth-=1
                    k+=1
                v=raw[start:k-1]
            elif raw[k]=='"':
                k+=1;start=k
                while k<len(raw) and (raw[k]!='"' or raw[k-1]=='\\'):k+=1
                v=raw[start:k];k+=1
            else:
                while k<len(raw) and raw[k]!=',':k+=1
                v=raw[start:k].strip()
            fields[f[1].lower()]=v
        entries.append({'type':m[1].lower(),'key':m[2],**fields});pos=i
    return entries

def dump(entries):
    return '\n\n'.join('@'+e['type']+'{'+e['key']+',\n'+',\n'.join('  '+k+'={'+v+'}' for k,v in e.items() if k not in ['type','key'])+'\n}' for e in entries)+'\n'

