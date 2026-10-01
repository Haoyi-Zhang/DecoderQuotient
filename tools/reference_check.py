"""Offline citation/bibliography consistency, with explicit provenance limits."""
import argparse,csv,json,re,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from bptc.certificate_format import strict_json_loads
from tools.bib_records import parse

def check(paper,artifact):
    entries=parse((paper/'references.bib').read_text());keys=[e['key'] for e in entries]
    if len(keys)!=len(set(keys)) or len(keys)<60:raise ValueError('bibliography count or duplicate key')
    for field in ('doi','title'):
        values=[re.sub(r'[^a-z0-9]','',e[field].lower()) for e in entries if field in e]
        if len(values)!=len(set(values)):raise ValueError('duplicate '+field)
    for e in entries:
        for f in ('author','title','year'):
            if not e.get(f):raise ValueError('missing identity field '+e['key']+':'+f)
        if not any(e.get(f) for f in ('doi','eprint','isbn','url')):raise ValueError('no scholarly identifier '+e['key'])
        if re.search(r'and others|TODO|placeholder|unknown author',e['author'],re.I):raise ValueError('incomplete author '+e['key'])
    macrotext=(paper/'generated/citations.tex').read_text()
    mapping=dict(re.findall(r'\\newcommand\{\\([A-Za-z]+)\}\{\\cite\{([^}]+)\}\}',macrotext))
    if mapping.get('CiteCompCert')!='compcert':raise ValueError('CompCert macro points at the wrong work')
    text=(paper/'main.tex').read_text()
    if '\\nocite' in text:raise ValueError('uncited bibliography inclusion')
    for name,value in sorted(mapping.items(),key=lambda x:-len(x[0])):
        text=re.sub(r'\\'+name+r'\b',lambda m:'\\cite{'+value+'}',text)
    occurrences=[];cited=set();current_section='Front matter'
    for line_number,line in enumerate(text.splitlines(),1):
        sec=re.search(r'\\(?:sub)?section\{([^}]+)\}',line)
        if sec:current_section=sec[1]
        for m in re.finditer(r'\\cite(?:t|p|author|year)?(?:\[[^]]*\])*\{([^}]+)\}',line):
            group=m[1].split(',')
            if len(group)>6:raise ValueError('unexplained citation group')
            for key in group:
                cited.add(key);occurrences.append({'key':key,'file':'paper/main.tex','line':line_number,'section':current_section,'paragraph':line.strip()})
    if cited!=set(keys):raise ValueError('uncited or undefined keys: '+str(sorted(cited^set(keys))))
    audit=strict_json_loads((artifact/'evidence/reference-audit.json').read_text())
    if set(audit['entries'])!=set(keys):raise ValueError('reference audit coverage mismatch')
    for item in audit['entries'].values():
        if not all(item.get(k) for k in ('primary_source','verification','citation_purpose')):raise ValueError('untracked reference')
    reviewed=strict_json_loads((artifact/'evidence/reference-reverification.json').read_text())
    records=reviewed.get('records',{})
    if len(records)!=len(entries) or set(records)!=set(keys):
        raise ValueError('fresh reference audit coverage mismatch')
    frozen=records
    for entry in entries:
        item=frozen[entry['key']]
        if item.get('bibliographic_record')!=entry:
            raise ValueError('bibliography changed after source review: '+entry['key'])
        if not item.get('access_scope') or not item.get('primary_source'):
            raise ValueError('source-review scope missing: '+entry['key'])
    # Wider source context is stored so a human can assess the actual supported clause.
    lines=text.splitlines()
    for o in occurrences:
        i=o['line']-1;start=i;end=i+1
        while start>0 and lines[start-1].strip():start-=1
        while end<len(lines) and lines[end].strip():end+=1
        o['paragraph']=' '.join(lines[start:end]);o['stated_citation_purpose']=audit['entries'][o['key']]['citation_purpose']
    return {'status':'pass','entries':len(entries),'cited_unique':len(cited),'citation_occurrences':len(occurrences),'missing_keys':[],'uncited_keys':[], 'scope':'Offline coverage and identity-field consistency. Primary-source reading is recorded in reference-audit.json, including partial-access and date-convention qualifications. This check does not establish full-text reading or universal accuracy.'},occurrences

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--paper-dir',type=Path,required=True);p.add_argument('--out',type=Path,required=True);p.add_argument('--contexts',type=Path);args=p.parse_args();artifact=Path(__file__).resolve().parents[1]
    try:
        report,rows=check(args.paper_dir,artifact)
        if args.contexts:
            args.contexts.parent.mkdir(parents=True,exist_ok=True)
            with args.contexts.open('w',newline='') as f:
                w=csv.DictWriter(f,fieldnames=rows[0].keys(),delimiter='\t');w.writeheader();w.writerows(rows)
    except Exception as e:report={'status':'fail','error':str(e)}
    args.out.parent.mkdir(parents=True,exist_ok=True);args.out.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report));return 0 if report['status']=='pass' else 1
if __name__=='__main__':raise SystemExit(main())
