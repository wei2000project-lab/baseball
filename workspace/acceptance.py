"""Reproducible P4 multi-seed acceptance; results stay outside Git."""
import argparse
from pathlib import Path
from configuration import default_config
from match import run_match
from recording import atomic_json


def main():
    p=argparse.ArgumentParser();p.add_argument("--output",required=True);p.add_argument("--seeds",type=int,default=20)
    p.add_argument("--regulation-ticks",type=int,default=1200);args=p.parse_args()
    out=Path(args.output);out.mkdir(parents=True,exist_ok=True)
    config=default_config();config["rules"]["regulation_ticks"]=args.regulation_ticks
    results=[]
    for seed in range(args.seeds):
        summary=run_match("bots/base_bot","bots/base_bot",config,str(seed),out/f"seed-{seed:02}")
        results.append({"seed":str(seed),**summary})
        print(f"seed {seed}: {summary['status']} {summary['score']} ticks={summary['sim_tick']}",flush=True)
        atomic_json(out/"batch-summary.json",results)
        if summary["status"]!="completed":raise SystemExit(f"acceptance failed seed={seed}: {summary['reason']}")


if __name__=="__main__":main()
