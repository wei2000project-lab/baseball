"""P5 D2: repeat a full external-Bot match ten times and compare authority."""
import argparse
import json
from pathlib import Path
from configuration import default_config
from match import run_match
from numeric import digest
from recording import atomic_json
from replay import file_digest,ReplayRecord


def main():
    p=argparse.ArgumentParser();p.add_argument("--output",required=True);p.add_argument("--report",required=True)
    p.add_argument("--repeats",type=int,default=10);p.add_argument("--seed",default="42");args=p.parse_args()
    out=Path(args.output);out.mkdir(parents=True,exist_ok=True);config=default_config();config["rules"]["regulation_ticks"]=1200
    expected=None;results=[]
    for i in range(args.repeats):
        path=out/f"repeat-{i:02}";summary=run_match("bots/base_bot","bots/base_bot",config,args.seed,path)
        signature={"txt_sha256":file_digest(path/"match.txt"),"summary":summary}
        if expected is None:expected=signature
        assert signature==expected and summary["status"]=="completed"
        results.append({"repeat":i,**signature});print(f"repeat {i}: same TXT deltas, events and terminal hash",flush=True)
    verification=ReplayRecord(out/"repeat-00").verify();assert verification["verification_status"]=="verified_record"
    atomic_json(Path(args.report),{"repeats":args.repeats,"seed":args.seed,"config":config,"results":results,"first_match_verification":verification})


if __name__=="__main__":main()
