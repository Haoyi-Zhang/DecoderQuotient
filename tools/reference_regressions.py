"""Negative controls for bibliography binding; no online or full-text certification."""
import argparse
import json
import shutil
import tempfile
from pathlib import Path
from tools.reference_check import check


def run(paper: Path, artifact: Path) -> dict:
    control, _ = check(paper, artifact)
    outcomes = []
    mutations = (
        ('reviewed_title_drift', 'references.bib', 'On-Device {LLM}', 'On-Device Unverified {LLM}'),
        ('reviewed_author_drift', 'references.bib', 'Lin, Ji and Tang, Jiaming', 'Lin, WrongName and Tang, Jiaming'),
        ('compcert_to_qserve', 'generated/citations.tex', r'\newcommand{\CiteCompCert}{\cite{compcert}}', r'\newcommand{\CiteCompCert}{\cite{qserve}}'),
    )
    for name, rel, before, after in mutations:
        with tempfile.TemporaryDirectory(prefix='reference-control-') as d:
            p = Path(d)/'paper'
            (p/'generated').mkdir(parents=True)
            for path in ('main.tex', 'references.bib', 'generated/citations.tex'):
                shutil.copyfile(paper/path, p/path)
            target=p/rel
            text=target.read_text()
            if before not in text:
                raise ValueError('negative control did not apply: '+name)
            target.write_text(text.replace(before,after,1))
            try:
                check(p,artifact)
            except ValueError as exc:
                outcomes.append({'control':name,'rejected':True,'reason':str(exc)})
            else:
                raise ValueError('negative control accepted: '+name)
    return {'status':'pass','positive_records':control['entries'],'negative_controls':outcomes,
            'scope':'Tests file/metadata binding, not the truth of the external publications.'}


def main() -> int:
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--paper-dir',type=Path,required=True)
    p.add_argument('--out',type=Path,required=True)
    args=p.parse_args()
    try:
        result=run(args.paper_dir,Path(__file__).resolve().parents[1])
    except Exception as exc:
        result={'status':'fail','error':str(exc)}
    args.out.parent.mkdir(parents=True,exist_ok=True)
    args.out.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result))
    return int(result['status']!='pass')

if __name__=='__main__':
    raise SystemExit(main())
