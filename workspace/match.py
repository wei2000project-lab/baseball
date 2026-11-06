"""Single-match entry point. Bot scheduling and recording; no baseball rulings."""
import argparse
from contextlib import ExitStack
from pathlib import Path
import sys
import time
from baseball_engine import BaseballEngine
from bot_host import BotHost,BotFault
from configuration import default_config,validate_config
from numeric import canonical,strict_loads,stream_seed
from recording import Recorder,decision_record,advance_recorded,atomic_json


def run_match(away,home,config,seed,output,timeout=2.0,max_record_bytes=512*1024*1024):
    engine=BaseballEngine(validate_config(config),str(seed));recorder=Recorder(output,engine,str(seed),run_mode="formal")
    hosts={};seq=0;started=time.perf_counter();last_phase=None
    try:
        for team,path in (("away",away),("home",home)):
            bot_seed=stream_seed(str(seed),"bot:"+team)
            try:
                hosts[team]=BotHost(path,team,bot_seed,recorder.diagnostics_path,timeout,capabilities={
                    "field_config":config["field"],"physics_config":config["physics"],"rules_config":config["rules"],
                    "action_types":["pitch","swing","take","move","catch","dive","throw","tag","run_to_base","return_to_base","hold","appeal_return","noop"]})
                recorder.manifest["bots"][team]={"program_sha256":hosts[team].program_hash,"seed":str(bot_seed),"resource_limits":hosts[team].capability}
            except Exception as error:
                seq+=1;record=decision_record(engine,team,None,seq)
                record["fault"]=str(error)[:256]
                result=advance_recorded(engine,[record]);recorder.write_step(engine,result,[record]);break
        if not engine.terminal_result():recorder.update_bots()
        while not engine.terminal_result():
            records=[];s=engine.state
            if s["sim_tick"]%config["rules"]["decision_interval_ticks"]==0 or s["phase"]!=last_phase:
                last_phase=s["phase"];requests={};observations={team:engine.observe(team) for team in ("away","home")}
                faults={}
                for team in ("away","home"):
                    seq+=1;decision_id=f"d{seq:09}";requests[team]=(seq,decision_id)
                    try:hosts[team].send({"type":"observe","protocol_version":"1.0.0","decision_id":decision_id,
                        "sim_tick":s["sim_tick"],"team_id":team,"state":observations[team],
                        "legal_action_types":legal_types(engine,team)})
                    except Exception as error:faults[team]=str(error)[:256]
                for team in ("away","home"):
                    raw=None;parse_error=None;actions=None
                    if team not in faults:
                        try:actions,raw,parse_error=hosts[team].receive(requests[team][1])
                        except Exception as error:faults[team]=str(error)[:256]
                    record=decision_record(engine,team,actions,requests[team][0],raw)
                    record["fault"]=faults.get(team);record["parse_error"]=parse_error
                    records.append(record)
            before=engine.snapshot()
            try:result=advance_recorded(engine,records)
            except (ValueError,OverflowError,RuntimeError) as error:
                engine.restore(before);seq+=1
                fault=decision_record(engine,"away",None,seq);fault["fault"]={"source":"engine","reason":str(error)[:256]}
                records.append(fault);result=advance_recorded(engine,records)
            recorder.write_step(engine,result,records)
            if engine.state["sim_tick"]%600==0:
                size=sum(p.stat().st_size for p in recorder.path.iterdir() if p.is_file())
                if size>max_record_bytes and not engine.terminal_result():
                    record=decision_record(engine,"away",None,seq+1);record["fault"]={"source":"host","reason":"record_size_limit"}
                    seq+=1;result=advance_recorded(engine,[record]);recorder.write_step(engine,result,[record])
        summary=recorder.finalize(engine)
        atomic_json(recorder.diagnostics_path/"performance.json",{"wall_seconds_ms":round((time.perf_counter()-started)*1000),
                    "sim_ticks":engine.state["sim_tick"],"python":sys.version,"bot_watchdog_ms":round(timeout*1000)})
        return summary
    finally:
        for host in hosts.values():host.close()
        recorder.close()


def legal_types(engine,team):
    phase=engine.state["phase"]
    if team==engine.offense:
        return ["swing","take","noop"] if phase in ("PITCH_READY","PITCH_IN_FLIGHT") else ["run_to_base","return_to_base","hold","noop"] if phase=="BALL_IN_PLAY" else ["noop"]
    return ["move","catch","hold","pitch","noop"] if phase=="PITCH_READY" else ["move","catch","dive","hold","throw","tag","appeal_return","noop"] if phase=="BALL_IN_PLAY" else ["move","catch","hold","noop"] if phase in ("PLATE_APPEARANCE_SETUP","PITCH_RESET","PITCH_IN_FLIGHT") else ["noop"]


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--away",required=True);p.add_argument("--home",required=True)
    p.add_argument("--seed",default="42");p.add_argument("--config",default="workspace/config/default.json")
    p.add_argument("--output",required=True);p.add_argument("--regulation-ticks",type=int)
    args=p.parse_args()
    try:
        config=strict_loads(Path(args.config).read_text(encoding="utf-8"))
        if args.regulation_ticks is not None:config["rules"]["regulation_ticks"]=args.regulation_ticks
        result=run_match(args.away,args.home,config,args.seed,args.output)
        print(canonical(result).decode());return 0 if result["status"]=="completed" else 2
    except (ValueError,OSError,RuntimeError) as error:
        print(str(error),file=sys.stderr);return 1


if __name__=="__main__":sys.exit(main())
