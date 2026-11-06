"""P5 verify sealed acceptance matches without starting any Bot."""
import argparse
from pathlib import Path
from replay import ReplayRecord
from recording import atomic_json


def main():
    p=argparse.ArgumentParser();p.add_argument("--input",required=True);p.add_argument("--report",required=True);args=p.parse_args()
    results=[]
    for path in sorted(Path(args.input).glob("seed-*")):
        result=ReplayRecord(path).verify();assert result["verification_status"]=="verified_record"
        results.append({"match":path.name,**result});print(f"{path.name}: verified_record through tick {result['verified_through_tick']}",flush=True)
    if len(results)<20:raise SystemExit("Expected at least 20 seeds")
    atomic_json(Path(args.report),results)


if __name__=="__main__":main()
