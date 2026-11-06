"""Recheck archived a-f parameters with the final, fair/foul-aware statistician.

New mechanics absent in an archived step use neutral C++ parameters. This is
an experiment harness, not a second physics implementation or a game option.
"""
import argparse
from concurrent.futures import ProcessPoolExecutor
from contextlib import redirect_stderr
import hashlib
import json
from pathlib import Path
import sys
from balance_batch import simulate,report,Bot
from configuration import default_config
from experiments.p7_bot import Bot as P7Bot
from recording import source_hash

ROOT=Path(__file__).resolve().parent
NAMES=("01-a","02-b","03-c","04-d","05-e","06-f")


def task(args):
    seed,config,legacy=args
    with open("NUL" if sys.platform=="win32" else "/dev/null","w") as sink,redirect_stderr(sink):
        return simulate(seed,config,P7Bot if legacy else Bot)


def parameters(step):
    archive=json.loads((ROOT/"balance_reports"/(NAMES[step]+".json")).read_text())
    c=default_config()
    for group in ("rules","physics","field"):c[group].update(archive["config"][group])
    c["version"]=c["physics"]["version"]=c["field"]["version"]="2.0.0"
    p=c["physics"]
    if step<3:
        p["fielder_speed_q"]=p["player_speed_q"];p["fielder_acceleration_q"]=p["player_acceleration_q"]
    if step<4:
        p.update(catch_running_radius_loss_q="0",catch_control_speed_q=str(100*(1<<32)),
                 catch_running_control_loss_q="0",throw_running_error_q="0")
    if step<5:p["pitch_max_error_q"]="0"
    return c


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument("--n",type=int,default=20)
    parser.add_argument("--workers",type=int,default=2);args=parser.parse_args()
    for step,name in enumerate(NAMES):
        config=parameters(step)
        with ProcessPoolExecutor(max_workers=args.workers) as pool:
            games=list(pool.map(task,[(seed,config,step<3) for seed in range(args.n)]))
        r=report(games,config,"fair-foul-recheck-"+name)
        botfile=ROOT/"experiments/p7_bot.py" if step<3 else ROOT.parent/"bots/base_bot/bot.py"
        r.update(bot_sha256=hashlib.sha256(botfile.read_bytes()).hexdigest(),engine_build_id=source_hash(),
            native_build_id=source_hash(native=True),source_parameter_report=name+".json",
            measurement_note="Archived cumulative parameters on consolidated v2 kernel; inactive features neutral. Correctly excludes foul fly catches. Original progression reports retained.")
        (ROOT/"balance_reports"/f"10-recheck-{name[-1]}.json").write_text(json.dumps(r,indent=2)+"\n")
        print(name,r["metrics"],flush=True)
        if r["completed"]!=args.n:raise RuntimeError("incomplete_step")


if __name__=="__main__":main()
