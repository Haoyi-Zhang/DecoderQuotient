"""Check the actual two-folder package; do not interpret this as scientific approval."""
import argparse,ast,json,re,sys
import importlib.util
import math
from pathlib import Path
from unittest.mock import Mock
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from tools.generate_paper import generate
from tools.validate_results import validate_run,compare_runs
from tools.reference_check import check as check_references
from native.materialize_measured_context import measured_fixture
from native.workflow_report import inputs as workflow_inputs

TITLE='Exact Quotient Certificates for Packed-Integer Decoders and Mixed-Width Accumulators'
def require(ok,message):
    if not ok:raise ValueError(message)
def project_paths(root):
    paper=root/'paper';artifact=root/'artifact'
    require(paper.is_dir() and artifact.is_dir(),'missing paper or artifact directory')
    return artifact,paper

def check_tex_inputs(paper,doc):
    text=(paper/(doc+'.tex')).read_text()
    for rel in re.findall(r'\\input\{([^}]+)\}',text):
        include=paper/rel
        if not include.suffix:include=include.with_suffix('.tex')
        require(include.is_file(),'missing TeX include '+rel)

def check_generated_inputs(paper,artifact):
    """Bind the complete generated text, including display names and every number."""
    for name,text in generate(artifact).items():
        target=paper/'generated'/name
        require(target.is_file() and target.read_text()==text,'missing/stale generated TeX: '+name)

def check_edge_figure(paper,artifact):
    """Check the current consumer, data and executed bar geometry, without writing a PDF.

    ReportLab is the existing renderer's dependency. A recording canvas observes
    its actual xy/bars methods; this is not a freshness check of the retained PDF.
    """
    uncomment=lambda text:re.sub(r'%[^\n]*','',text)
    main=uncomment((paper/'main.tex').read_text())
    require(re.search(r'\\input\{figures/edge-counts(?:\.tex)?\}',main),
            'main must consume the edge-count figure')
    include=uncomment((paper/'figures/edge-counts.tex').read_text()).strip()
    require(include==r'\includegraphics{figures/edge-counts.pdf}',
            'edge-count figure must consume the checked PDF')
    pdf=paper/'figures/edge-counts.pdf'
    require(pdf.is_file() and pdf.read_bytes().startswith(b'%PDF-'),
            'missing/invalid edge-count PDF')
    source=paper/'figures/draw_evaluation.py'
    module_spec=importlib.util.spec_from_file_location('edge_count_renderer',source)
    renderer=importlib.util.module_from_spec(module_spec)
    module_spec.loader.exec_module(renderer)
    charts=[cfg for cfg in renderer.CHARTS if cfg['name']=='edge-counts']
    require(len(charts)==1,'expected one edge-count chart')
    cfg=charts[0]
    require(not cfg.get('ylog') and not cfg.get('xlog') and cfg['ylim'][0]==0,
            'bar plot must have linear axes and start at zero')
    require(all(math.isfinite(v) for v in cfg['xlim']+cfg['ylim']) and
            cfg['xlim'][0]<1<2<cfg['xlim'][1] and cfg['ylim'][1]>0,
            'invalid finite axis bounds for edge-count bars')
    require(any(value==0 and label=='0' for value,label in cfg['yticks']),
            'bar plot must display its zero tick')
    require(len(cfg['series'])==1,'expected one edge-count series')
    series=cfg['series'][0]
    require(series['kind']=='bar' and series.get('categorical') is True and
            (series['csv'],series['x'],series['y'])==
            ('figures/edge-counts.csv','representation','frontier_edges'),
            'edge-count series must bind the retained CSV columns')
    values=renderer.points(series)  # Includes the renderer's retained-snapshot check.
    counts=json.loads((artifact/'results/publication/main/summary.json').read_text())['accumulator']
    expected=[counts['unquotiented_frontier_edges'],counts['quotient_frontier_edges']]
    labels=['Unquotiented','Quotient']
    require([(x,y,row['representation']) for x,y,row in values]==
            [(i+1,float(n),labels[i]) for i,n in enumerate(expected)],
            'plotted edge counts differ from retained evidence')
    macros=dict(re.findall(r'\\newcommand\{\\(Pub\w+Edges)\}\{(\d+)\}',
                           (paper/'generated/publication_macros.tex').read_text()))
    require([macros.get(name) for name in ('PubUnquotientedEdges','PubQuotientEdges')]==
            [str(n) for n in expected],'edge-count macros differ from retained evidence')
    require(cfg['ylim'][1]>=max(expected)>0,'bar axis clips retained edge counts')
    require([label for x,label in cfg['xticks']]==labels and
            [x for x,label in cfg['xticks']]==[1,2],'edge-count category labels differ')
    plot=renderer.Plot.__new__(renderer.Plot)
    plot.cfg=cfg
    plot.left,plot.bottom,plot.width,plot.height=cfg['box']
    require(all(math.isfinite(v) for v in cfg['box']) and plot.width>0 and plot.height>0,
            'invalid plot box dimensions')
    plot.c=Mock()
    plot.label=Mock()  # Font/text layout is outside this geometry check.
    style=series['style']
    require(math.isfinite(style['width']) and style['width']>0,'invalid bar width')
    plot.bars(values,**style)
    rectangles=plot.c.rect.call_args_list
    require(len(rectangles)==len(expected),'renderer did not draw both data bars')
    for i,call in enumerate(rectangles):
        x=plot.left+plot.width*((i+1-cfg['xlim'][0])/(cfg['xlim'][1]-cfg['xlim'][0]))
        wanted=(x+style.get('shift',0)-style['width']/2,plot.bottom,
                style['width'],plot.height*expected[i]/cfg['ylim'][1])
        require(len(call.args)==4 and call.kwargs=={'fill':1} and
                all(math.isfinite(v) and math.isclose(v,w,rel_tol=1e-10,abs_tol=1e-8)
                    for v,w in zip(call.args,wanted)),
                'rendered bar geometry does not start at zero or match retained counts')
    return {'counts':expected,'axis_lower':0,'bars_checked':len(rectangles),
            'scope':'Current renderer/data/consumer and executed bar geometry; not retained PDF freshness.'}

def check_package_assets(root):
    required = root/'artifact/data/measured_context.zip'
    for f in root.rglob('*'):
        require(f.name not in ('.git','__pycache__'),'unexpected cache/version directory')
        require(f.suffix != '.pyc','bytecode in package')
        if f.suffix == '.zip':
            require(f == required,'unexpected nested archive: '+str(f.relative_to(root)))
    require(required.is_file(),'missing measured-source fixture')
    measured_fixture(root/'artifact')

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--project-root',type=Path,required=True);p.add_argument('--out',type=Path,required=True);args=p.parse_args();root=args.project_root.resolve();steps=[]
    try:
        a,paper=project_paths(root)
        for f in ['main.tex','supplement.tex','main.pdf','supplement.pdf','references.bib','build.sh','README.md','acmart.cls','ACM-Reference-Format.bst']:
            require((paper/f).is_file() and (paper/f).stat().st_size>0,'missing paper file: '+f)
        for f in ('main.pdf','supplement.pdf'):require((paper/f).read_bytes().startswith(b'%PDF-'),'not a PDF: '+f)
        for f in (paper/'README.md',a/'README.md'):require(TITLE in f.read_text(),'README/manuscript identity mismatch')
        require(TITLE in (paper/'main.tex').read_text(),'main identity mismatch');steps.append('two-folder structure, paper source, actual PDF files and matching README titles')
        for run in ('main','reproduction'):validate_run(a/'results/publication'/run)
        comparison=compare_runs(a/'results/publication/main',a/'results/publication/reproduction');steps.append('complete 64+30 evidence sets for each run and independent-run byte comparison')
        check_generated_inputs(paper,a)
        steps.append('all six generated TeX inputs equal regenerated evidence-derived text')
        _,workflow_macros,workflow_csv=workflow_inputs(a/'results/workflow-cost')
        require((paper/'generated/workflow_macros.tex').read_text()==workflow_macros,
                'stale complete-workflow macros')
        require((paper/'figures/workflow-cost.csv').read_text()==workflow_csv,
                'stale complete-workflow plot data')
        require((paper/'figures/workflow-cost.pdf').read_bytes().startswith(b'%PDF-'),
                'missing complete-workflow vector figure')
        require(r'\includegraphics{figures/workflow-cost.pdf}' in (paper/'main.tex').read_text(),
                'main must consume complete-workflow figure')
        steps.append('complete workflow declarations, raw sample/packet bindings, both semantic consumers, derived macros/CSV and figure consumer; retained PDF freshness requires separate render review')
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
            check_tex_inputs(paper,doc)
            log=(paper/'build-logs'/(doc+'.log')).read_text()
            for pattern in ('Undefined control sequence','There were undefined references','There were undefined citations','! LaTeX Error','Overfull \\hbox'):
                require(pattern not in log,'LaTeX log problem: '+pattern)
        steps.append('all TeX includes present; retained build logs free of errors, undefined references and horizontal overflow (not a fresh build or source/log binding)')
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
        figure=check_edge_figure(paper,a)
        steps.append('current edge-count consumer, retained CSV/macros and executed zero-baseline bar geometry (not PDF freshness)')
        check_package_assets(root)
        ledger=json.loads((a/'results/repair-budget.json').read_text())
        require(sum(ledger['categories'].values())==ledger['events_used']<=ledger['limit'],'repair ledger totals')
        report={'status':'pass','meaning':'File/evidence consistency only; not a guarantee of novelty, general correctness or journal readiness.','checks':steps,'figure_check':figure,'reference_check':ref,'scientific_file_comparison':comparison,'active_python_files':len(sources),'repair_events':ledger['events_used'],'historical_budget_overrun_remains':True}
    except Exception as e:report={'status':'fail','error':str(e),'completed_checks':steps}
    args.out.parent.mkdir(parents=True,exist_ok=True);args.out.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report));return 0 if report['status']=='pass' else 1
if __name__=='__main__':raise SystemExit(main())
