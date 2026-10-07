"""Verify the fixed suite, saved evidence, aggregates, and independent-run equality.
Use --replay with a continuing --ledger to re-run semantic certificate checking.
Without --replay this is a structural/content audit, not a new semantic experiment.
"""
from __future__ import annotations
import argparse, csv, json, sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from bptc.publication_cases import accumulator_specs, decoder_specs
from bptc.exact_accumulator import spec_to_dict as acc_spec
from bptc.packed_decoder import spec_to_dict as dec_spec, check_decoder_certificate
from bptc.accumulator_checker import check_certificate
from bptc.certificate_format import exact, keys, integer, strict_json_loads
from bptc.publication_budget import ObligationLedger

def load(p):
    if not p.is_file(): raise ValueError(f"missing required file: {p}")
    return strict_json_loads(p.read_text(encoding="utf-8"))

def require(condition,message):
    if not condition: raise ValueError(message)

ACC_COLUMNS = ('case','provenance','exact_equivalent','sufficient_guard',
    'final_range_guard','term_fit_final_guard','direct_dp_transitions',
    'direct_dp_equivalent','concrete_assignments','failing_assignments',
    'reachable_final_states','quotient_edges','unquotiented_edges','edge_reduction',
    'least_counterexample')
DEC_COLUMNS = ('case','provenance','scale','maxima','equivalent',
    'closed_form_equivalent','concrete_assignments','reachable_final_states',
    'oracle_run','least_counterexample')

def rows(p,expected,columns):
    with p.open(newline='',encoding='utf-8') as f:
        reader=csv.DictReader(f)
        require(reader.fieldnames==list(columns),f"{p.name}: noncanonical CSV header")
        out=list(reader)
    require(all(set(row)==set(columns) and all(type(v) is str for v in row.values())
                for row in out),f"{p.name}: missing or extra CSV cells")
    require(len(out)==len(expected),f"{p.name}: row count")
    require({x['case'] for x in out}==set(expected),f"{p.name}: case identifiers")
    return {x['case']:x for x in out}

def recompute_guards(spec,ledger):
    """Independent interval implementation, not imported from the baseline module.

    Every member is charged three times up front, matching three declared
    baseline evaluations. The shared scan only avoids redundant arithmetic;
    it does not reduce the conservative obligation charge.
    """
    ledger.charge('saved-audit:baseline-pair',
                  3*sum(len(stage['pairs']) for stage in spec['stages']))
    low=high=spec['initial']
    bits=spec['stages'][0]['acc_bits']
    sufficient=-(1 << (bits-1)) <= low < (1 << (bits-1))
    terms_fit=True
    for stage in spec['stages']:
        products=[a*b for a,b in stage['pairs']]
        pmin,pmax=min(products),max(products)
        t=stage['term_bits']
        fits=-(1 << (t-1)) <= pmin and pmax < (1 << (t-1))
        terms_fit=terms_fit and fits
        low+=pmin;high+=pmax
        a=stage['acc_bits']
        sufficient=sufficient and fits and -(1 << (a-1)) <= low and high < (1 << (a-1))
    a=spec['stages'][-1]['acc_bits']
    final=-(1 << (a-1)) <= low and high < (1 << (a-1))
    return bool(sufficient),bool(final),bool(terms_fit and final)

def validate_oracle_counts(record,assignments,equivalent,label):
    keys(record,('assignments','equivalent','failing_assignments','least_counterexample'),label)
    integer(record['assignments'],label+'.assignments',1)
    integer(record['failing_assignments'],label+'.failing_assignments',0,assignments)
    exact(record['assignments'],assignments,label+'.assignments')
    exact(record['equivalent'],equivalent,label+'.equivalent')
    require((record['failing_assignments']==0)==equivalent,label+': inconsistent failing count')

def file_set(path,names):
    require(path.is_dir(),f"missing directory: {path}")
    require({p.name for p in path.iterdir()}=={n+'.json' for n in names},f"{path.name}: missing, extra, or duplicate case files")

def boolean(v):
    if v not in ('True','False'):raise ValueError('noncanonical CSV Boolean')
    return v=='True'

def prefix(c):
    return None if c is None else {k:c[k] for k in ('indices','pairs','first_bad_stage')}

def validate_run(path:Path,ledger=None):
    aa={s.name:acc_spec(s) for s in accumulator_specs()}; dd={s.name:dec_spec(s) for s in decoder_specs()}
    require(len(aa)==64 and len(dd)==30,'suite identity/count changed')
    for folder in ('certificates','oracles','direct'):file_set(path/folder,aa)
    file_set(path/'decoder-certificates',dd)
    ac=rows(path/'accumulator-cases.csv',aa,ACC_COLUMNS); de=rows(path/'decoder-cases.csv',dd,DEC_COLUMNS)
    totals={'cases':64,'equivalent':0,'oracle_assignments':0,'producer_transitions':0,'checker_transitions':0,
        'direct_dp_transitions':0,'unquotiented_frontier_edges':0,'quotient_frontier_edges':0,
        'sufficient_guard_false_rejects':0,'final_range_false_accepts':0,'term_fit_final_false_accepts':0}
    for name,spec in aa.items():
        c=load(path/'certificates'/f'{name}.json');exact(c['spec'],spec,'suite binding')
        if ledger:check_certificate(c,ledger,'saved-audit:accumulator')
        o=load(path/'oracles'/f'{name}.json');d=load(path/'direct'/f'{name}.json');row=ac[name];m=c['metrics'];dec=c['decision']
        eq=dec['equivalent'];validate_oracle_counts(o,m['concrete_assignments'],eq,name+' oracle')
        keys(d,('equivalent','least_counterexample','reachable_final_states','transitions'),name+' direct')
        integer(d['reachable_final_states'],name+' direct states',1);integer(d['transitions'],name+' direct transitions',1)
        exact(d['equivalent'],eq);exact(row['provenance'],spec['provenance'],name+' provenance')
        exact(o['least_counterexample'],prefix(dec['least_counterexample']));exact(d['least_counterexample'],prefix(dec['least_counterexample']))
        exact(strict_json_loads(row['least_counterexample']),dec['least_counterexample'])
        require(boolean(row['exact_equivalent'])==eq and boolean(row['direct_dp_equivalent'])==eq,'CSV decision drift')
        for column,value in {'concrete_assignments':m['concrete_assignments'],'failing_assignments':o['failing_assignments'],
            'reachable_final_states':dec['reachable_final_states'],'quotient_edges':m['quotient_frontier_edges'],
            'unquotiented_edges':m['unquotiented_frontier_edges'],'direct_dp_transitions':d['transitions'],
            'edge_reduction':m['unquotiented_frontier_edges']-m['quotient_frontier_edges']}.items():
            require(int(row[column])==value,f'{name}: {column}')
        exact(d['reachable_final_states'],dec['reachable_final_states']);exact(d['transitions'],m['unquotiented_frontier_edges'])
        exact(o['assignments'],m['concrete_assignments'])
        totals['equivalent']+=eq;totals['oracle_assignments']+=o['assignments']
        totals['producer_transitions']+=m['producer_transitions'];totals['checker_transitions']+=sum(len(x.get('edges',[])) for x in c['layers'])
        totals['direct_dp_transitions']+=d['transitions'];totals['unquotiented_frontier_edges']+=m['unquotiented_frontier_edges'];totals['quotient_frontier_edges']+=m['quotient_frontier_edges']
        sg=boolean(row['sufficient_guard']);fg=boolean(row['final_range_guard']);tg=boolean(row['term_fit_final_guard'])
        if ledger:
            exact([sg,fg,tg],list(recompute_guards(spec,ledger)),name+' independently recomputed baseline verdicts')
        require(not sg or eq,'claimed sufficient guard unsound on saved case')
        totals['sufficient_guard_false_rejects']+=eq and not sg
        totals['final_range_false_accepts']+=not eq and fg;totals['term_fit_final_false_accepts']+=not eq and tg
    ds={'cases':30,'equivalent':0,'oracle_cases':0,'oracle_assignments':0};oracle_names=[]
    for name,spec in dd.items():
        c=load(path/'decoder-certificates'/f'{name}.json');exact(c['spec'],spec,'decoder suite binding')
        if ledger:check_decoder_certificate(c,ledger,'saved-audit:decoder')
        row=de[name];eq=c['decision']['equivalent'];m=c['metrics']
        exact(row['provenance'],spec['provenance'],name+' provenance')
        require(boolean(row['equivalent'])==eq and boolean(row['closed_form_equivalent'])==c['closed_form']['equivalent'],'decoder CSV verdict')
        exact(strict_json_loads(row['maxima']),spec['maxima']);require(int(row['scale'])==spec['scale'],'decoder CSV scale')
        exact(strict_json_loads(row['least_counterexample']),c['decision']['least_counterexample'])
        for f in ('concrete_assignments','reachable_final_states'):require(int(row[f])==m[f],f'{name}:{f}')
        expected_oracle=m['concrete_assignments']<=4096;require(boolean(row['oracle_run'])==expected_oracle,'oracle applicability')
        if expected_oracle:
            oracle_names.append(name);o=load(path/'decoder-oracles'/f'{name}.json')
            validate_oracle_counts(o,m['concrete_assignments'],eq,name+' decoder oracle')
            if not eq:
                for f in ('digits','first_bad_lane'):exact(o['least_counterexample'][f],c['decision']['least_counterexample'][f])
            else:exact(o['least_counterexample'],None)
            ds['oracle_cases']+=1;ds['oracle_assignments']+=o['assignments']
        ds['equivalent']+=eq
    file_set(path/'decoder-oracles',oracle_names)
    mutations=load(path/'mutations.json')
    expected={('accumulator',n,i) for n in list(aa)[:8] for i in range(5)}|{('decoder',n,i) for n in list(dd)[:5] for i in range(4)}
    require(len(mutations)==60 and {(m['kind'],m['case'],m['mutation']) for m in mutations}==expected,'mutation coverage')
    require(all(m['rejected'] is True and bool(m['diagnostic']) for m in mutations),'mutation rejection record')
    source=load(path/'source-report.json');sm=source['mutation_test']
    require(sm['mutations']==sm['rejected']==len(sm['records'])==22 and len({m['mutation'] for m in sm['records']})==22,'source mutation coverage')
    require(all(m['rejected'] is True for m in sm['records']) and source['accepted'] is True,'source acceptance')
    totals.update(inequivalent=64-totals['equivalent'],certificate_mutations=40,certificate_mutations_rejected=40,cross_check_disagreements=0,direct_dp_disagreements=0)
    totals['edge_reduction']=totals['unquotiented_frontier_edges']-totals['quotient_frontier_edges']
    totals['edge_reduction_fraction']=1-totals['quotient_frontier_edges']/totals['unquotiented_frontier_edges']
    ds.update(inequivalent=30-ds['equivalent'],certificate_mutations=20,certificate_mutations_rejected=20,cross_check_disagreements=0)
    s=load(path/'summary.json');exact(s['accumulator'],totals);exact(s['decoder'],ds);exact(s['source_anchor'],source);exact(s['all_cross_checks_agree'],True)
    account=load(path/'run-accounting.json');require(account['events_after']-account['events_before']==account['events_this_run']>0,'run accounting difference')
    return {'accumulator':totals,'decoder':ds,'source_anchor':source,'run_accounting':account}

def scientific_files(path):
    folders=('certificates','decoder-certificates','oracles','direct','decoder-oracles')
    files=[p.relative_to(path).as_posix() for folder in folders for p in (path/folder).glob('*.json')]
    return sorted(files+['accumulator-cases.csv','decoder-cases.csv','mutations.json','source-report.json'])

def compare_runs(left,right):
    lf=scientific_files(left);rf=scientific_files(right);require(lf==rf and len(lf)==246,'complete scientific file set')
    for rel in lf:require((left/rel).read_bytes()==(right/rel).read_bytes(),f'byte mismatch: {rel}')
    a=load(left/'summary.json');b=load(right/'summary.json')
    for k in ('accumulator','decoder','source_anchor','format','all_cross_checks_agree'):exact(a[k],b[k],k)
    return {'byte_compared_scientific_files':len(lf),'byte_identical':True,'summary_comparison':'scientific fields equal; measured resource fields and labels intentionally excluded'}

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--results-dir',type=Path,required=True);p.add_argument('--compare-dir',type=Path);p.add_argument('--replay',action='store_true');p.add_argument('--ledger',type=Path);p.add_argument('--out',type=Path,required=True);a=p.parse_args()
    ledger=None
    if a.replay:
        if not a.ledger:raise ValueError('--replay requires --ledger')
        old=load(a.ledger);ledger=ObligationLedger(old['limit'],old['events_used'],old['categories'])
    before=None if ledger is None else ledger.used
    try:
        results=validate_run(a.results_dir,ledger)
        comp=None
        if a.compare_dir:
            other=validate_run(a.compare_dir,ledger);comp=compare_runs(a.results_dir,a.compare_dir)
        report={'status':'pass','audit_mode':'semantic certificate replay, independent baseline recomputation, and saved-record audit' if a.replay else 'saved-record structural audit only','results_dir':str(a.results_dir),'compare_dir':str(a.compare_dir) if a.compare_dir else None,'counts':{'accumulator':64,'decoder':30},'comparison':comp,'events_this_check':0 if ledger is None else ledger.used-before}
    except Exception as e:
        report={'status':'fail','error':str(e),'audit_mode':'semantic replay' if a.replay else 'structural'}
    finally:
        if ledger:ledger.write(a.ledger)
    a.out.parent.mkdir(parents=True,exist_ok=True);a.out.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report));return 0 if report['status']=='pass' else 1

if __name__=='__main__':raise SystemExit(main())
