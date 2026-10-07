"""Generate paper inputs ONLY from the complete, validated retained records."""
import argparse,csv,json,sys
from pathlib import Path
from collections import defaultdict
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from tools.validate_results import validate_run,compare_runs

def read(p):return json.loads(p.read_text())
def table_rows(p):return list(csv.DictReader(p.open(newline='')))
def esc(x):return str(x).replace('_',r'\_').replace('&',r'\&').replace('%',r'\%')
def generate(artifact):
    base=artifact/'results/publication';left=base/'main';right=base/'reproduction'
    validate_run(left);validate_run(right);compare_runs(left,right)
    s=read(left/'summary.json');a=s['accumulator'];d=s['decoder'];source=s['source_anchor']['mutation_test']
    accounts=[read((base/run)/'run-accounting.json') for run in ('main','reproduction')]
    used=sum(x['events_this_run'] for x in accounts)
    mapping={'PubDecoderCases':d['cases'],'PubAccumulatorCases':a['cases'],
      'PubDecoderOracleCases':d['oracle_cases'],'PubDecoderOracleAssignments':d['oracle_assignments'],
      'PubAccumulatorOracleAssignments':a['oracle_assignments'],'PubGuardFalseRejects':a['sufficient_guard_false_rejects'],
      'PubFinalFalseAccepts':a['final_range_false_accepts'],'PubTermFinalFalseAccepts':a['term_fit_final_false_accepts'],
      'PubUnquotientedEdges':a['unquotiented_frontier_edges'],'PubQuotientEdges':a['quotient_frontier_edges'],
      'PubEdgeReduction':a['edge_reduction'],'PubEdgeReductionPct':f"{100*a['edge_reduction_fraction']:.2f}",
      'PubSourceMutations':source['mutations'],'PubSourceMutationsRejected':source['rejected'],
      'PubAccumulatorMutations':a['certificate_mutations'],'PubAccumulatorMutationsRejected':a['certificate_mutations_rejected'],
      'PubDecoderMutations':d['certificate_mutations'],'PubDecoderMutationsRejected':d['certificate_mutations_rejected'],
      'PubBudgetUsed':used,'PubBudgetLimit':200000,'PubBudgetRemain':200000-used,
      'PubPeakRSS':max(x['resource_usage']['peak_rss_kib'] for x in accounts),
      'PubCPUSeconds':f"{sum(x['resource_usage']['cpu_seconds'] for x in accounts):.6f}"}
    out={'publication_macros.tex':'% Derived from results/publication; never edit values by hand.\n'+''.join('\\newcommand{\\%s}{%s}\n'%(k,v) for k,v in mapping.items())}
    def grouped(rows):
        g=defaultdict(list)
        for row in rows:g[row['provenance']].append(row)
        return g
    dr=table_rows(left/'decoder-cases.csv');ar=table_rows(left/'accumulator-cases.csv')
    dt=[r'\begin{tabular}{lrrrr}',r'\toprule',r'Profile & Cases & Equal & Unequal & Oracle inputs \\',r'\midrule']
    for family,rr in grouped(dr).items():
        eq=sum(r['equivalent']=='True' for r in rr);n=sum(int(r['concrete_assignments']) for r in rr if r['oracle_run']=='True')
        dt.append(f'{esc(family)} & {len(rr)} & {eq} & {len(rr)-eq} & {n} '+r'\\')
    dt += [r'\bottomrule',r'\end{tabular}'];out['decoder_families.tex']='\n'.join(dt)+'\n'
    at=[r'\begin{tabular}{lrrrrrr}',r'\toprule',r'Family & Cases & Equal & Suff. FR & Final FA & Term-fit FA & Edges saved \\',r'\midrule']
    labels={'safe-control':'Safe control','adversarial-overflow':'Visible saturation','cancellation-control':'Reconvergence','final-range-counterexample':'Final-range failure','mixed-width-term':'Term narrowing','mixed-width-schedule':'Width schedule','observation-schedule':'Observation schedule','systematic-product-box':'Mixed products'}
    for family,rr in grouped(ar).items():
        eq=sum(r['exact_equivalent']=='True' for r in rr)
        fr=sum(r['exact_equivalent']=='True' and r['sufficient_guard']=='False' for r in rr)
        fa=sum(r['exact_equivalent']=='False' and r['final_range_guard']=='True' for r in rr)
        ta=sum(r['exact_equivalent']=='False' and r['term_fit_final_guard']=='True' for r in rr)
        ed=sum(int(r['edge_reduction']) for r in rr)
        at.append(f'{esc(labels.get(family,family))} & {len(rr)} & {eq} & {fr} & {fa} & {ta} & {ed} '+r'\\')
    at += [r'\bottomrule',r'\end{tabular}'];out['accumulator_families.tex']='\n'.join(at)+'\n'
    boolstr=lambda s:'T' if s=='True' else 'F'
    acc=[r'{\small',r'\begin{longtable}{lrrrrrrrr}',r'\caption{Complete accumulator suite. S, F and TF are the three guards; Q/U count frontier edges.}\\',r'\toprule',r'Case & Eq. & S & F & TF & Inputs & Fail & Q & U \\',r'\midrule\endfirsthead',r'\toprule Case & Eq. & S & F & TF & Inputs & Fail & Q & U \\ \midrule\endhead']
    for r in ar:
        vals=[esc(r['case'])]+[boolstr(r[k]) for k in ('exact_equivalent','sufficient_guard','final_range_guard','term_fit_final_guard')]+[r[k] for k in ('concrete_assignments','failing_assignments','quotient_edges','unquotiented_edges')]
        acc.append(' & '.join(vals)+r' \\')
    acc += [r'\bottomrule\end{longtable}}'];out['supplement_acc_cases.tex']='\n'.join(acc)+'\n'
    dec=[r'{\small',r'\begin{longtable}{lrrrr}',r'\caption{Complete decoder suite. Enumeration is performed only for boxes with at most 4096 words.}\\',r'\toprule Case & Scale & Eq. & Inputs & Enumerated \\ \midrule\endfirsthead',r'\toprule Case & Scale & Eq. & Inputs & Enumerated \\ \midrule\endhead']
    for r in dr:dec.append(' & '.join([esc(r['case']),r['scale'],boolstr(r['equivalent']),r['concrete_assignments'],boolstr(r['oracle_run'])])+r' \\')
    dec += [r'\bottomrule\end{longtable}}'];out['supplement_decoder_cases.tex']='\n'.join(dec)+'\n'
    bt=[r'\begin{center}\begin{tabular}{lrrr}\toprule Run & Ledger before & Ledger after & Charged events \\ \midrule']
    for label,account in zip(('Main','Reproduction'),accounts):bt.append(f"{label} & {account['events_before']} & {account['events_after']} & {account['events_this_run']} "+r'\\')
    bt += [f'Two retained runs & --- & --- & {used} '+r'\\',r'\bottomrule\end{tabular}\end{center}'];out['supplement_budget.tex']='\n'.join(bt)+'\n'
    return out

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--paper-dir',type=Path,required=True);p.add_argument('--check',action='store_true');a=p.parse_args()
    root=Path(__file__).resolve().parents[1];generated=a.paper_dir/'generated';files=generate(root)
    if not a.check:generated.mkdir(parents=True,exist_ok=True)
    for name,text in files.items():
        target=generated/name
        if a.check:
            if not target.is_file() or target.read_text()!=text:raise SystemExit('missing or stale generated input: '+name)
        else:target.write_text(text)
    print('generated-input check passed' if a.check else 'six paper inputs generated from validated retained evidence')
if __name__=='__main__':main()
