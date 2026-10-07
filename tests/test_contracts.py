"""Bounded regressions for certificate contracts and corrected boundaries."""
import copy
import json
import os
from pathlib import Path
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from bptc.publication_budget import ObligationLedger, BudgetExceeded
from bptc.exact_accumulator import AccumulatorSpec, StageSpec, generate_certificate, spec_to_dict
from bptc.accumulator_checker import check_certificate
from bptc.accumulator_oracle import run_oracle
from bptc.accumulator_baselines import no_overflow_sufficient, final_range_only, term_fit_and_final_range
from bptc.direct_state import solve
from bptc.packed_decoder import DecoderSpec, generate_decoder_certificate, check_decoder_certificate, brute_force_decoder
from bptc.publication_cases import accumulator_specs, decoder_specs, _pairs_for_product
from bptc.source_anchor import EXPECTED, parse_source, mutation_suite
from bptc.publication_campaign import run_once

LEDGER = ObligationLedger(200000)

def simple(initial=0, mode="saturate", values=(1,), observe=False, final=True):
    return AccumulatorSpec("boundary",initial,tuple(StageSpec(((p,1),),8,"wrap",4,mode,observe) for p in values),final,"bounded-regression")

def acc(): return generate_certificate(simple(), LEDGER,"test-producer")
def dec(): return generate_decoder_certificate(DecoderSpec("boundary",255,(3,3),(7,11)),LEDGER,"test-decoder")

class BudgetTests(unittest.TestCase):
    def test_atomic_rejection(self):
        b=ObligationLedger(3);b.charge("x",3);old=b.to_dict()
        with self.assertRaises(BudgetExceeded):b.charge("y")
        self.assertEqual(b.to_dict(),old)
    def test_boolean_not_integer(self):
        for value in (True,False,1.0,-1,0):
            with self.assertRaises(ValueError):ObligationLedger(value)
    def test_concurrency(self):
        b=ObligationLedger(11)
        def f(_):
            try:b.charge("x");return True
            except BudgetExceeded:return False
        with ThreadPoolExecutor(max_workers=2) as pool:self.assertEqual(sum(pool.map(f,range(20))),11)
        self.assertEqual(sum(b.categories.values()),11)
    def test_invalid_charge_unchanged(self):
        b=ObligationLedger(3)
        for x in (True,False,1.5,0,-1):
            with self.assertRaises(ValueError):b.charge("x",x)
        self.assertEqual(b.used,0)

class DomainTests(unittest.TestCase):
    def test_real_factor_pairs(self):
        for p in (-1,0,1,2,3,7):
            pairs=_pairs_for_product(p)
            self.assertEqual(len(pairs),len(set(pairs)))
            self.assertTrue(all(x*y==p for x,y in pairs))
        self.assertEqual(len(_pairs_for_product(1)),2)
        self.assertEqual(len(_pairs_for_product(-1)),2)
    def test_complete_suite(self):
        aa=accumulator_specs();dd=decoder_specs()
        self.assertEqual(len(aa),64);self.assertEqual(len({x.name for x in aa}),64)
        self.assertEqual(len(dd),30);self.assertEqual(len({x.name for x in dd}),30)
        for spec in aa:
            for st in spec.stages:self.assertEqual(len(st.pairs),len(set(st.pairs)))
    def test_producer_bad_types(self):
        for width in (True,1,0,4.0,33):
            with self.assertRaises(ValueError):StageSpec(((1,1),),width,"wrap",4,"wrap")
        with self.assertRaises(ValueError):StageSpec(((True,1),),4,"wrap",4,"wrap")
        with self.assertRaises(ValueError):DecoderSpec("x",1,(1,),(0,),lane_bits=4)
    def test_accumulator_empty_vacuity(self):
        c=acc();c["spec"]["stages"][0]["pairs"]=[];c["spec"]["stages"][0]["term_mode"]="invalid"
        c["product_classes"]=[[]];c["layers"][1]["states"]=[];c["layers"][1]["edges"]=[]
        with self.assertRaises(ValueError):check_certificate(c,LEDGER)
    def test_accumulator_invalid_domains(self):
        base=acc()
        changes=[("pairs",[]),("pairs",[[1,1],[1,1]]),("pairs",[[True,1]]),("pairs",[[1.0,1]]),
                 ("term_bits",0),("term_bits",1),("term_bits",4.0),("acc_bits",True),("term_mode","other"),
                 ("acc_mode","other"),("observe","false")]
        for field,value in changes:
            c=copy.deepcopy(base);c["spec"]["stages"][0][field]=value
            with self.subTest(field=field,value=value), self.assertRaises(ValueError):check_certificate(c,LEDGER)
    def test_decoder_invalid_domains(self):
        base=dec()
        for field,value in [("scale",-1),("scale",True),("scale",256),("maxima",[]),("maxima",[-1,3]),
                            ("maxima",[3.0,3]),("biases",[0]),("biases",[0,256]),("biases",[0,False]),("lane_bits",4),("lane_bits",8.0)]:
            c=copy.deepcopy(base);c["spec"][field]=value
            with self.subTest(field=field,value=value),self.assertRaises(ValueError):check_decoder_certificate(c,LEDGER)
    def test_extra_and_wrong_scalar_types(self):
        c=acc();c["spec"]["initial"]=True
        with self.assertRaises(ValueError):check_certificate(c,LEDGER)
        c=acc();c["spec"]["final_observe"]=1
        with self.assertRaises(ValueError):check_certificate(c,LEDGER)
        c=acc();c["layers"][0]["states"][0]["state"][2]=0
        with self.assertRaises(ValueError):check_certificate(c,LEDGER)

class ReplayTests(unittest.TestCase):
    def test_all_accumulator_metrics(self):
        base=acc()
        for key in base["metrics"]:
            c=copy.deepcopy(base);c["metrics"][key]+=1
            with self.subTest(key=key),self.assertRaises(ValueError):check_certificate(c,LEDGER)
    def test_accumulator_counts_and_indices(self):
        base=acc()
        for key in ("reachable_final_states","bad_final_states"):
            c=copy.deepcopy(base);c["decision"][key]+=1
            with self.assertRaises(ValueError):check_certificate(c,LEDGER)
        for i in range(len(base["layers"])):
            c=copy.deepcopy(base);c["layers"][i]["index"]+=1
            with self.assertRaises(ValueError):check_certificate(c,LEDGER)
    def test_decoder_metrics_envelope_and_layers(self):
        base=dec()
        for key in base["metrics"]:
            c=copy.deepcopy(base);c["metrics"][key]+=1
            with self.assertRaises(ValueError):check_decoder_certificate(c,LEDGER)
        c=copy.deepcopy(base);c["closed_form"]["max_carry_after_last_lane"]+=1
        with self.assertRaises(ValueError):check_decoder_certificate(c,LEDGER)
        c=copy.deepcopy(base);c["source_parameter_bound"]=False
        with self.assertRaises(ValueError):check_decoder_certificate(c,LEDGER)
        c=copy.deepcopy(base);c["layers"].append(c["layers"][-1])
        with self.assertRaises(ValueError):check_decoder_certificate(c,LEDGER)
        c=copy.deepcopy(base);c["layers"][0]["index"]=True
        with self.assertRaises(ValueError):check_decoder_certificate(c,LEDGER)
    def test_unknown_fields_rejected(self):
        for make,check in [(acc,check_certificate),(dec,check_decoder_certificate)]:
            c=make();c["extra"]=0
            with self.assertRaises(ValueError):check(c,LEDGER)
            c=make();c["layers"][0]["extra"]=0
            with self.assertRaises(ValueError):check(c,LEDGER)
    def test_nonzero_initial_counterexample(self):
        s=simple(initial=8,values=(-1,));c=generate_certificate(s,LEDGER);q=check_certificate(c,LEDGER)
        o=run_oracle(c["spec"],LEDGER);d=solve(c["spec"],LEDGER)
        self.assertFalse(no_overflow_sufficient(c["spec"]))
        self.assertFalse(q["equivalent"]);self.assertFalse(o["equivalent"]);self.assertEqual(o["least_counterexample"],d["least_counterexample"])
        self.assertEqual(c["decision"]["least_counterexample"]["final_state"][:2],[7,-1])
    def test_signed_initial_guard_grid(self):
        for initial in (-9,-8,-7,0,7,8,9):
            for mode in ("wrap","saturate"):
                for p in (-1,0,1):
                    s=simple(initial,mode,(p,));spec=spec_to_dict(s)
                    LEDGER.charge("test-baseline",1)
                    guard=no_overflow_sufficient(spec);o=run_oracle(spec,LEDGER)
                    c=generate_certificate(s,LEDGER);check_certificate(c,LEDGER)
                    self.assertEqual(c["decision"]["equivalent"],o["equivalent"])
                    self.assertFalse(guard and not o["equivalent"])
    def test_two_final_guards_distinguished(self):
        s=AccumulatorSpec("term",0,(StageSpec(((8,1),),4,"wrap",8,"wrap"),))
        spec=spec_to_dict(s)
        self.assertTrue(final_range_only(spec));self.assertFalse(term_fit_and_final_range(spec));self.assertFalse(run_oracle(spec,LEDGER)["equivalent"])
    def test_reconvergence_observation(self):
        final_only=simple(values=(8,-1,-28));observed=simple(values=(8,-1,-28),observe=True)
        self.assertTrue(run_oracle(spec_to_dict(final_only),LEDGER)["equivalent"])
        self.assertFalse(run_oracle(spec_to_dict(observed),LEDGER)["equivalent"])
    def test_no_observation_is_vacuous_by_contract(self):
        s=simple(values=(8,-8),final=False)
        c=generate_certificate(s,LEDGER);check_certificate(c,LEDGER)
        self.assertTrue(c["decision"]["equivalent"])
    def test_minimality_product_merge(self):
        pairs=((2,1),(1,2),(-1,-2),(0,0),(-2,1),(1,-2))
        s=AccumulatorSpec("branch",7,tuple(StageSpec(pairs,4,"wrap",4,"saturate",i==0) for i in range(2)))
        c=generate_certificate(s,LEDGER);check_certificate(c,LEDGER);o=run_oracle(c["spec"],LEDGER);d=solve(c["spec"],LEDGER)
        self.assertEqual(o["least_counterexample"],d["least_counterexample"])
        cex=c["decision"]["least_counterexample"]
        self.assertEqual(cex["indices"],o["least_counterexample"]["indices"])
    def test_materialized_witness_quadratic(self):
        for n in (1,2,4,8,16):
            c=generate_certificate(simple(values=(0,)*n),LEDGER);check_certificate(c,LEDGER)
            size=sum(len(st["least_witness_indices"]) for layer in c["layers"] for st in layer["states"])
            self.assertEqual(size,n*(n+1)//2)
    def test_decoder_discard_final_carry(self):
        s=DecoderSpec("top",255,(15,),(9,));c=generate_decoder_certificate(s,LEDGER)
        check_decoder_certificate(c,LEDGER);o=brute_force_decoder(s,LEDGER)
        self.assertTrue(o["equivalent"]);self.assertGreater(c["closed_form"]["max_carry_after_last_lane"],0)

class SourceTests(unittest.TestCase):
    def test_retained_implementation_attribution(self):
        path=Path(__file__).resolve().parents[1]/'inputs/omniserve/share_to_reg_one_stage_B.cu'
        text=path.read_text(encoding='utf-8')
        self.assertIn('// Implemented by Haotian Tang and Shang Yang.',text)
        self.assertTrue(parse_source(text,LEDGER)['accepted'])
    def test_positive_whitespace_comments(self):
        self.assertTrue(parse_source(EXPECTED,LEDGER)["accepted"])
        self.assertTrue(parse_source("/* harmless */\n"+EXPECTED.replace(";","; // comment\n"),LEDGER)["accepted"])
    def test_full_mutation_suite(self):
        x=mutation_suite(EXPECTED,LEDGER);self.assertEqual(x["mutations"],x["rejected"])
    def test_source_order(self):
        old="uint32_t ptr_0 = loaded_0 * scale_0;\nuint32_t ptr_1 = loaded_1 * scale_0;"
        new="uint32_t ptr_1 = loaded_1 * scale_0;\nuint32_t ptr_0 = loaded_0 * scale_0;"
        self.assertIn(old,EXPECTED)
        with self.assertRaises(ValueError):parse_source(EXPECTED.replace(old,new),LEDGER)

class ExportTests(unittest.TestCase):
    def test_end_to_end_single_case(self):
        root=Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as td:
            out=Path(td)/"one"
            result=run_once(root,out,LEDGER,"smoke",[accumulator_specs()[0]],[decoder_specs()[0]])
            self.assertEqual(result["accumulator"]["cases"],1)
            self.assertEqual(len(list((out/"certificates").glob("*.json"))),1)
            self.assertTrue((out/"accumulator-cases.csv").is_file())
            self.assertTrue((out/"decoder-cases.csv").is_file())
            self.assertTrue(result["all_cross_checks_agree"])


class SavedEvidenceTests(unittest.TestCase):
    def test_complete_saved_evidence(self):
        from tools.validate_results import validate_run,compare_runs
        root=Path(__file__).resolve().parents[1]/"results/publication"
        validate_run(root/"main");validate_run(root/"reproduction")
        self.assertEqual(compare_runs(root/"main",root/"reproduction")["byte_compared_scientific_files"],246)
    def test_both_empty_are_rejected(self):
        from tools.validate_results import validate_run
        with tempfile.TemporaryDirectory() as td:
            for run in ('a','b'):
                path=Path(td)/run;path.mkdir()
                with self.assertRaises(ValueError):validate_run(path)
    def test_matching_deleted_certificate_is_rejected(self):
        import shutil
        from tools.validate_results import validate_run
        source=Path(__file__).resolve().parents[1]/"results/publication/main"
        with tempfile.TemporaryDirectory() as td:
            for name in ('a','b'):
                target=Path(td)/name;shutil.copytree(source,target)
                next((target/'certificates').glob('*.json')).unlink()
                with self.assertRaises(ValueError):validate_run(target)
    def test_new_directory_tampering_is_rejected(self):
        import shutil,json
        from tools.validate_results import validate_run,compare_runs
        source=Path(__file__).resolve().parents[1]/"results/publication/main"
        with tempfile.TemporaryDirectory() as td:
            target=Path(td)/'new';shutil.copytree(source,target)
            file=next((target/'certificates').glob('*.json'))
            data=json.loads(file.read_text());data['metrics']['producer_transitions']+=1
            file.write_text(json.dumps(data))
            with self.assertRaises((ValueError,AssertionError)):validate_run(target)
            with self.assertRaises(ValueError):compare_runs(source,target)

class ReverificationTests(unittest.TestCase):
    """Regression controls for defects observed in the inherited result validator."""
    def test_duplicate_json_members_rejected(self):
        from bptc.certificate_format import strict_json_loads
        for source in ('{"accepted":false,"accepted":true}',
                       '{"outer":{"x":1,"x":2}}'):
            with self.assertRaises(ValueError):strict_json_loads(source)
        self.assertEqual(strict_json_loads('{"a":1,"b":[false,null]}'),
                         {'a':1,'b':[False,None]})
    def test_nonfinite_json_rejected(self):
        from bptc.certificate_format import strict_json_loads
        for value in ('NaN','Infinity','-Infinity','1e10000'):
            with self.assertRaises(ValueError):strict_json_loads('{"x":'+value+'}')
    def test_csv_duplicate_header_rejected(self):
        from tools.validate_results import rows
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/'rows.csv';p.write_text('case,case\na,a\n')
            with self.assertRaises(ValueError):rows(p,{'a'},('case','value'))
    def test_csv_missing_extra_cells_rejected(self):
        from tools.validate_results import rows
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/'rows.csv'
            for data in ('case,value\na,1,extra\n','case,value\na\n'):
                p.write_text(data)
                with self.assertRaises(ValueError):rows(p,{'a'},('case','value'))
    def test_oracle_bad_failure_counts_rejected(self):
        from tools.validate_results import validate_oracle_counts
        for failures in (-1,True,1.0,5,1):
            record={'assignments':4,'equivalent':True,'failing_assignments':failures,
                    'least_counterexample':None}
            with self.assertRaises(ValueError):validate_oracle_counts(record,4,True,'control')
    def test_coordinated_baseline_tamper_rejected(self):
        import shutil,csv
        from tools.validate_results import validate_run
        source=Path(__file__).resolve().parents[1]/'results/publication/main'
        with tempfile.TemporaryDirectory() as td:
            target=Path(td)/'copy';shutil.copytree(source,target)
            path=target/'accumulator-cases.csv'
            with path.open(newline='') as f:
                reader=csv.DictReader(f);fields=reader.fieldnames;table=list(reader)
            row=next(x for x in table if x['case']=='safe-saturating-00')
            self.assertEqual(row['sufficient_guard'],'True');row['sufficient_guard']='False'
            with path.open('w',newline='') as f:
                writer=csv.DictWriter(f,fieldnames=fields);writer.writeheader();writer.writerows(table)
            path=target/'summary.json';summary=json.loads(path.read_text())
            summary['accumulator']['sufficient_guard_false_rejects']+=1
            path.write_text(json.dumps(summary))
            # A structural cross-file agreement is not a semantic baseline proof.
            with self.assertRaisesRegex(ValueError,'recomputed baseline'):
                validate_run(target,LEDGER)
    def test_provenance_drift_rejected(self):
        import shutil,csv
        from tools.validate_results import validate_run
        source=Path(__file__).resolve().parents[1]/'results/publication/main'
        with tempfile.TemporaryDirectory() as td:
            target=Path(td)/'copy';shutil.copytree(source,target)
            path=target/'accumulator-cases.csv'
            with path.open(newline='') as f:
                reader=csv.DictReader(f);fields=reader.fieldnames;table=list(reader)
            table[0]['provenance']='invented-source'
            with path.open('w',newline='') as f:
                w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(table)
            with self.assertRaisesRegex(ValueError,'provenance'):validate_run(target)
    def test_independent_guard_matches_boundary_baselines(self):
        from tools.validate_results import recompute_guards
        for initial in (-9,-8,0,7,8):
            for mode in ('wrap','saturate'):
                spec=spec_to_dict(simple(initial,mode,(-1,)))
                actual=recompute_guards(spec,LEDGER)
                LEDGER.charge('reverification:baseline-control',3)
                expected=(no_overflow_sufficient(spec),final_range_only(spec),
                          term_fit_and_final_range(spec))
                self.assertEqual(actual,expected)
