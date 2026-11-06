"""P2 diagnostic end-to-end runner. Uses the external scripted controller."""
import argparse
from pathlib import Path
import sys
from configuration import default_config
from baseball_engine import BaseballEngine
from numeric import canonical
from recording import Recorder, decision_record, batch_from_record

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"bots/examples"))
from script_controller import strikeout_actions


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--output",required=True)
    p.add_argument("--regulation-ticks",type=int,default=108000)
    args=p.parse_args();config=default_config();config["rules"]["regulation_ticks"]=args.regulation_ticks
    engine=BaseballEngine(config);recorder=Recorder(args.output,engine);seq=0
    try:
        while not engine.terminal_result():
            records=[]
            for team in ("away","home"):
                actions=strikeout_actions(engine.observe(team),team)
                if actions:
                    seq+=1;records.append(decision_record(engine,team,actions,seq))
            result=engine.step([batch_from_record(r) for r in records])
            recorder.write_step(engine,result,records)
        print(canonical(recorder.finalize(engine)).decode())
    finally:recorder.close()


if __name__=="__main__":main()
