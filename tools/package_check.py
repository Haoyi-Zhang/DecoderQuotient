"""Check the actual two-folder package; do not interpret this as scientific approval."""
import argparse,ast,json,re,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from tools.generate_paper import generate
from tools.validate_results import validate_run,compare_runs
from tools.reference_check import check as check_references

TITLE='Exact Quotient Certificates for Packed-Integer Decoders and Mixed-Width Accumulators'
def require(ok,message):
    if not ok:raise ValueError(message)
def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--project-root',type=Path,required=True);p.add_argument('--out',type=Path,required=True);args=p.parse_args();root=args.project_root.resolve();a=root/'Artifacts';paper=root/'paper';steps=[]
    try:
        require({p.name for p in root.iterdir()}=={'paper','Artifacts'},'mixed or unexpected project root')
        for f in ['main.tex','supplement.tex','main.pdf','supplement.pdf','references.bib','build.sh','README.md','acmart.cls','ACM-Reference-Format.bst']:
            require((paper/f).is_file() and (paper/f).stat().st_size>0,'missing paper file: '+f)
        for f in ('main.pdf','supplement.pdf'):require((paper/f).read_bytes().startswith(b'%PDF-'),'not a PDF: '+f)
        for f in (paper/'README.md',a/'README.md'):require(TITLE in f.read_text(),'README/manuscript identity mismatch')
        require(TITLE in (paper/'main.tex').read_text(),'main identity mismatch');steps.append('two-folder structure, paper source, actual PDF files and matching README titles')
        for run in ('main','reproduction'):validate_run(a/'results/publication'/run)
        comparison=compare_runs(a/'results/publication/main',a/'results/publication/reproduction');steps.append('complete 64+30 evidence sets for each run and independent-run byte comparison')
        for name,text in generate(a).items():require((paper/'generated'/name).is_file() and (paper/'generated'/name).read_text()==text,'missing/stale generated TeX: '+name)
        steps.append('all six generated TeX inputs equal regenerated evidence-derived text')
        ref,contexts=check_references(paper,a);steps.append(str(ref['entries'])+'-record bibliography/citation mapping and source-audit coverage')
        sources=list((a/'bptc').glob('*.py'))+list((a/'tools').glob('*.py'))+list((a/'tests').glob('*.py'))
        for f in sources:ast.parse(f.read_text(),filename=f.name)
        for name in ('accumulator_checker.py','accumulator_oracle.py','direct_state.py'):
            tree=ast.parse((a/'bptc'/name).read_text())
            for node in ast.walk(tree):
                if isinstance(node,ast.ImportFrom):require('exact_accumulator' not in (node.module or ''),'producer import in '+name)
                if isinstance(node,ast.Name):require(node.id!='generate_certificate','producer call name in '+name)
        steps.append('active Python syntax and direct producer-import exclusion (not a complete call-graph proof)')
        for doc in ('main','supplement'):
            text=(paper/(doc+'.tex')).read_text()
            for rel in re.findall(r'\\input\{([^}]+)\}',text):require((paper/(rel+'.tex')).is_file(),'missing TeX include '+rel)
            log=(paper/'build-logs'/(doc+'.log')).read_text()
            for pattern in ('Undefined control sequence','There were undefined references','There were undefined citations','! LaTeX Error','Overfull \\hbox'):
                require(pattern not in log,'LaTeX log problem: '+pattern)
        steps.append('all TeX includes present and current logs free of errors, undefined references and horizontal overflow')
        # The reproduction command is part of the delivered interface.
        campaign_tree=ast.parse((a/'bptc/publication_campaign.py').read_text())
        label_choices=None
        for node in ast.walk(campaign_tree):
            if isinstance(node,ast.Call) and isinstance(node.func,ast.Attribute) and node.func.attr=='add_argument' and any(isinstance(x,ast.Constant) and x.value=='--label' for x in node.args):
                for kw in node.keywords:
                    if kw.arg=='choices':label_choices=ast.literal_eval(kw.value)
        require(bool(label_choices),'campaign label contract not found')
        for doc in (a/'README.md',paper/'supplement.tex'):
            for label in re.findall(r'--label\s+([A-Za-z_-]+)',doc.read_text()):
                require(label in label_choices,'invalid documented campaign label: '+label)
        steps.append('documented campaign labels agree with the actual CLI choices')
        require('ymin=0' in (paper/'figures/edge-counts.tex').read_text(),'bar plot must start at zero')
        for f in root.rglob('*'):
            require(f.name not in ('.git','__pycache__'),'unexpected cache/version directory')
            require(f.suffix not in ('.pyc','.zip'),'bytecode or nested archive')
        ledger=json.loads((a/'results/repair-budget.json').read_text())
        require(sum(ledger['categories'].values())==ledger['events_used']<=ledger['limit'],'repair ledger totals')
        report={'status':'pass','meaning':'File/evidence consistency only; not a guarantee of novelty, general correctness or journal readiness.','checks':steps,'reference_check':ref,'scientific_file_comparison':comparison,'active_python_files':len(sources),'repair_events':ledger['events_used'],'historical_budget_overrun_remains':True}
    except Exception as e:report={'status':'fail','error':str(e),'completed_checks':steps}
    args.out.parent.mkdir(parents=True,exist_ok=True);args.out.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report));return 0 if report['status']=='pass' else 1
if __name__=='__main__':raise SystemExit(main())
