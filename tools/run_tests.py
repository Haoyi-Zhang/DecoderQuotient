"""Run unit regressions and persist their actual semantic-work ledger."""
import argparse,json,sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from bptc.certificate_format import strict_json_loads
from bptc.publication_budget import ObligationLedger
from tests import test_contracts

def main():
    p=argparse.ArgumentParser();p.add_argument("--ledger",type=Path,required=True);p.add_argument("--out",type=Path,required=True)
    args=p.parse_args()
    if args.ledger.exists():
        old=strict_json_loads(args.ledger.read_text());ledger=ObligationLedger(old["limit"],old["events_used"],old["categories"])
    else:ledger=ObligationLedger(200000)
    test_contracts.LEDGER=ledger;before=ledger.used
    suite=unittest.defaultTestLoader.loadTestsFromModule(test_contracts)
    result=unittest.TextTestRunner(verbosity=2).run(suite)
    ledger.write(args.ledger)
    report={"tests":result.testsRun,"failures":[(str(t),trace) for t,trace in result.failures],"errors":[(str(t),trace) for t,trace in result.errors],"skipped":len(result.skipped),"success":result.wasSuccessful(),"events_this_run":ledger.used-before,"events_cumulative":ledger.used}
    args.out.parent.mkdir(parents=True,exist_ok=True);args.out.write_text(json.dumps(report,indent=2)+"\n")
    return 0 if result.wasSuccessful() else 1
if __name__=="__main__":raise SystemExit(main())
