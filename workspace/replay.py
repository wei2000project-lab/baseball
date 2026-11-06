"""Bot-free verification, checkpoint restoration, exact seek and frame cache."""
import argparse
import bisect
import hashlib
import json
from pathlib import Path
import sys
import time
from baseball_engine import BaseballEngine
from configuration import VERSION,validate_config,SUPPORTED_RULES,default_config
from contracts import validate_named,validate
from functools import lru_cache
from numeric import canonical,strict_loads,digest
from recording import Recorder,advance_recorded,batch_from_record,source_hash,atomic_json

LINE_LIMIT=1024*1024
FILE_LIMIT=1024*1024*1024
# P4's sealed traces use identical rules/physics. P5 only fixes recording of
# already-rejected fractional JSON audit values; all P4 sealed traces are replayed
# in the P5 acceptance suite before retaining this explicit compatibility entry.
COMPATIBLE_ENGINE_BUILDS={"7ce74ed271428d5d277567f08a1c4070f44638c33db89751be3f19eb534c80b7"}


@lru_cache
def record_schema(name):
    return strict_loads((Path(__file__).resolve().parent/"contracts/records"/f"{name}.schema.json").read_text(encoding="utf-8"))


def validate_record(name,value):
    try:validate(value,record_schema(name))
    except ValueError as error:raise ReplayError("mismatch","record_schema",record_type=name,detail=str(error))


class ReplayError(Exception):
    def __init__(self,status,reason,**details):
        self.report={"verification_status":status,"reason":reason,**details}
        super().__init__(reason)


def first_difference(expected,actual,path="$"):
    if type(expected)is not type(actual):return (path,expected,actual)
    if isinstance(expected,dict):
        for key in sorted(set(expected)|set(actual)):
            if key not in expected or key not in actual:return (path+"."+key,expected.get(key),actual.get(key))
            found=first_difference(expected[key],actual[key],path+"."+key)
            if found:return found
    elif isinstance(expected,list):
        if len(expected)!=len(actual):return (path+".length",len(expected),len(actual))
        for i,(a,b) in enumerate(zip(expected,actual)):
            found=first_difference(a,b,f"{path}[{i}]")
            if found:return found
    elif expected!=actual:return (path,expected,actual)
    return None


def file_digest(path):
    sha=hashlib.sha256()
    with open(path,"rb") as f:
        while chunk:=f.read(1024*1024):sha.update(chunk)
    return sha.hexdigest()


def lines(path,start_offset=0,allow_partial=False):
    with open(path,"rb") as file:
        file.seek(start_offset)
        while True:
            offset=file.tell();line=file.readline(LINE_LIMIT+1)
            if not line:return
            if len(line)>LINE_LIMIT:raise ReplayError("mismatch","line_size_limit",file=path.name,offset=offset)
            if not line.endswith(b"\n"):
                if allow_partial:return
                raise ReplayError("mismatch","truncated_line",file=path.name,offset=offset)
            try:obj=strict_loads(line.decode("utf-8"))
            except (ValueError,UnicodeError) as error:raise ReplayError("mismatch","invalid_json",file=path.name,offset=offset,detail=str(error))
            if type(obj)is not dict:raise ReplayError("mismatch","invalid_record_object",file=path.name,offset=offset)
            yield offset,obj


class ReplayRecord:
    def __init__(self,path):
        self.root=Path(path).resolve()
        if not self.root.is_dir():raise ReplayError("mismatch","record_directory_missing")
        self.manifest=self.read_json("manifest.json")
        validate_record("manifest",self.manifest)
        m=self.manifest
        if m["schema_version"] not in SUPPORTED_RULES:raise ReplayError("unsupported_version","schema_version",actual=m["schema_version"])
        defaults=default_config()
        for field,expected in (("ruleset_version",m["schema_version"]),("physics_version",defaults["physics"]["version"]),("map_version",defaults["field"]["version"]),
                               ("engine_build_id",source_hash()),("native_build_id",source_hash(native=True))):
            if m.get(field)!=expected and not (field=="engine_build_id" and m.get(field) in COMPATIBLE_ENGINE_BUILDS and m["schema_version"]=="1.0.0-dev.P4"):raise ReplayError("unsupported_version",field,expected=expected,actual=m.get(field))
        try:validate_config(m["config"])
        except (ValueError,KeyError) as e:raise ReplayError("mismatch","invalid_config",detail=str(e))
        if any(m[k]!=m["config"][sub] for k,sub in (("rules_config","rules"),("physics_config","physics"),("field_config","field"))):raise ReplayError("mismatch","config_snapshot_disagreement")
        self.incomplete=m.get("record_status") not in ("complete","aborted")
        if not self.incomplete:
            index=m.get("file_index",{})
            if set(index)!=set(Recorder.FILES):raise ReplayError("mismatch","invalid_file_index")
            for name,entry in index.items():
                file=self.safe_file(name)
                if file.stat().st_size!=entry["size_bytes"] or file_digest(file)!=entry["sha256"]:
                    raise ReplayError("mismatch","file_integrity",file=name)
        self.initial=self.read_json("initial_state.json")
        try:validate_named(self.initial,"state")
        except ValueError as error:raise ReplayError("mismatch","initial_state_schema",detail=str(error))
        if not m["seed"].isdecimal() or not 0<=int(m["seed"])<1<<64:raise ReplayError("mismatch","invalid_seed")
        if m["initial_defense"]!={p["id"]:p["position_q"] for p in self.initial["players"]}:raise ReplayError("mismatch","initial_defense_disagreement")
        for team in ("away","home"):
            players=[p for p in self.initial["players"] if p["team_id"]==team]
            if m["rosters"][team]!=[{"id":p["id"],"role":p["role"]} for p in players] or m["batting_orders"][team]!=[p["id"] for p in players]:raise ReplayError("mismatch","roster_or_order_disagreement")
        self.summary=None if self.incomplete else self.read_json("summary.json")
        if self.summary:validate_record("summary",self.summary)
        if self.summary and (self.summary["status"]=="completed")!=(m["record_status"]=="complete"):raise ReplayError("mismatch","summary_record_status_disagreement")
        self.action_index=[]
        previous_tick=-1
        for offset,record in lines(self.safe_file("actions.jsonl"),allow_partial=self.incomplete):
            validate_record("action_record",record)
            seq=record.get("seq");tick=record.get("applied_tick")
            if type(tick)is not int or tick<previous_tick or seq!=len(self.action_index)+1 or record.get("decision_id")!=f"d{seq:09}":
                raise ReplayError("mismatch","action_order",offset=offset)
            if record.get("observation_tick")!=tick:raise ReplayError("mismatch","observation_tick")
            self.action_index.append((tick,offset));previous_tick=tick
        self.checkpoint_index=[]
        previous=(-1,-1)
        for offset,cp in lines(self.safe_file("checkpoints.jsonl"),allow_partial=self.incomplete):
            validate_record("checkpoint",cp)
            key=(cp.get("resume_tick",-1),cp.get("action_cursor",-1))
            if key<previous or cp.get("stage")!="POST_BOUNDARY":raise ReplayError("mismatch","checkpoint_order")
            if digest(cp["state"])!=cp["state_hash"]:raise ReplayError("mismatch","checkpoint_self_hash",tick=key[0])
            if cp["state"]["sim_tick"]!=key[0] or cp["state"]["action_cursor"]!=key[1] or cp["state"]["last_event_seq"]!=cp["last_event_seq"]:raise ReplayError("mismatch","checkpoint_envelope",tick=key[0])
            self.checkpoint_index.append((key[0],key[1],offset));previous=key
        if not self.checkpoint_index:raise ReplayError("verified_prefix","incomplete_no_checkpoint",verified_through_tick=0)
        self.final_tick=self.checkpoint_index[-1][0] if self.incomplete else self.summary["sim_tick"]
        self.identity=digest({"initial":self.initial,"engine":m["engine_build_id"],"index":m.get("file_index",{}),"final_tick":self.final_tick})

    def safe_file(self,name):
        if name not in ("manifest.json",*Recorder.FILES):raise ReplayError("mismatch","path_not_allowed")
        path=self.root/name
        if path.is_symlink() or path.resolve().parent!=self.root or not path.is_file():raise ReplayError("mismatch","unsafe_or_missing_file",file=name)
        if path.stat().st_size>FILE_LIMIT:raise ReplayError("mismatch","file_size_limit",file=name)
        return path

    def read_json(self,name):
        path=self.safe_file(name)
        if path.stat().st_size>4*1024*1024:raise ReplayError("mismatch","json_file_size_limit",file=name)
        try:
            value=strict_loads(path.read_text(encoding="utf-8"))
            if type(value)is not dict:raise ValueError("object_required")
            return value
        except (ValueError,UnicodeError) as error:raise ReplayError("mismatch","invalid_json",file=name,detail=str(error))

    def checkpoint(self,index):
        return next(lines(self.safe_file("checkpoints.jsonl"),self.checkpoint_index[index][2]))[1]

    def actions(self,cursor=0):
        if cursor>=len(self.action_index):return iter(())
        return (r for _,r in lines(self.safe_file("actions.jsonl"),self.action_index[cursor][1],self.incomplete))

    def _inputs(self,engine,iterator,next_record):
        records=[];tick=engine.state["sim_tick"]
        while next_record is not None and next_record["applied_tick"]==tick:
            record=next_record
            if record["seq"]!=engine.state["action_cursor"]+len(records)+1:raise ReplayError("mismatch","action_cursor",tick=tick)
            observation=engine.observe(record["team_id"])
            if digest(observation)!=record["observation_hash"]:raise ReplayError("mismatch","observation_hash",tick=tick,seq=record["seq"])
            if not record.get("fault"):
                checked=engine.validate_intents(record["team_id"],record["requested_actions"])
                difference=first_difference(checked,batch_from_record(record))
                if difference:raise ReplayError("mismatch","accepted_intents",tick=tick,field=difference[0],expected=difference[1],actual=difference[2])
                if record.get("raw_response") and record.get("parse_error") is None:
                    raw=strict_loads(record["raw_response"])
                    if raw.get("actions")!=record["requested_actions"] or raw.get("decision_id")!=record["decision_id"]:raise ReplayError("mismatch","raw_response",tick=tick)
            records.append(record);next_record=next(iterator,None)
        if next_record and next_record["applied_tick"]<tick:raise ReplayError("mismatch","stale_action",tick=tick)
        return records,next_record

    def verify(self,checkpoint=None,progress=None,on_state=None):
        engine=BaseballEngine();start=0
        if checkpoint is None:engine.initialize(self.manifest["config"],self.initial)
        else:
            cp=self.checkpoint(checkpoint);engine.initialize(self.manifest["config"],cp["state"]);start=checkpoint+1
        inputs=self.actions(engine.state["action_cursor"]);next_action=next(inputs,None)
        # Freeze the starting sequence; engine mutates while the generator advances.
        first_seq=engine.state["last_event_seq"]
        expected_events=(e for _,e in lines(self.safe_file("events.jsonl"),allow_partial=self.incomplete) if e["seq"]>first_seq)
        cp_cursor=start;last_verified=engine.state["sim_tick"];steps=0
        def compare_checkpoints():
            nonlocal cp_cursor
            while cp_cursor<len(self.checkpoint_index):
                tick,cursor,_=self.checkpoint_index[cp_cursor]
                actual=(engine.state["sim_tick"],engine.state["action_cursor"])
                if (tick,cursor)>actual:break
                if (tick,cursor)<actual:raise ReplayError("mismatch","missed_checkpoint",tick=tick)
                cp=self.checkpoint(cp_cursor)
                difference=first_difference(cp["state"],engine.snapshot())
                if difference:raise ReplayError("mismatch","checkpoint_state",tick=tick,field=difference[0],expected=difference[1],actual=difference[2])
                if engine.canonical_state_hash()!=cp["state_hash"]:raise ReplayError("mismatch","checkpoint_hash",tick=tick)
                cp_cursor+=1
        compare_checkpoints()
        if on_state:on_state(engine,[])
        while not engine.terminal_result() and (not self.incomplete or engine.state["sim_tick"]<self.final_tick):
            records,next_action=self._inputs(engine,inputs,next_action)
            try:result=advance_recorded(engine,records)
            except (ValueError,RuntimeError,OverflowError) as error:raise ReplayError("mismatch","engine_recompute_error",tick=engine.state["sim_tick"],detail=str(error),verified_through_tick=last_verified)
            for event in result["events"]:
                expected=next(expected_events,None)
                if expected is not None:validate_named(expected,"event")
                difference=first_difference(expected,event)
                if difference:raise ReplayError("mismatch","event_difference",tick=event["sim_tick"],seq=event["seq"],field=difference[0],expected=difference[1],actual=difference[2],verified_through_tick=last_verified)
            compare_checkpoints();last_verified=engine.state["sim_tick"];steps+=1
            if on_state:on_state(engine,result["events"])
            if progress and steps%600==0:progress(last_verified,self.final_tick)
            if steps>self.manifest["config"]["rules"]["max_ticks"]+1:raise ReplayError("mismatch","recompute_guard")
        if self.incomplete:return {"verification_status":"verified_prefix","record_status":"incomplete","verified_through_tick":last_verified,"source_hash":self.identity}
        if next_action is not None or next(expected_events,None)is not None or cp_cursor!=len(self.checkpoint_index):raise ReplayError("mismatch","unconsumed_record_tail",tick=last_verified)
        difference=first_difference(self.summary,engine.terminal_result())
        if difference:raise ReplayError("mismatch","summary_difference",tick=last_verified,field=difference[0],expected=difference[1],actual=difference[2])
        return {"verification_status":"verified_full" if checkpoint is None else "verified_prefix","record_status":self.manifest["record_status"],"verified_from_tick":0 if checkpoint is None else self.checkpoint_index[checkpoint][0],"verified_through_tick":last_verified,"source_hash":self.identity,"summary":engine.terminal_result()}

    def seek(self,tick):
        if type(tick)is not int or not 0<=tick<=self.final_tick:raise ReplayError("mismatch","seek_tick_out_of_range")
        index=bisect.bisect_right(self.checkpoint_index,(tick,10**12,10**12))-1
        if index<0:raise ReplayError("mismatch","checkpoint_missing_before_tick")
        cp=self.checkpoint(index);engine=BaseballEngine();engine.initialize(self.manifest["config"],cp["state"])
        inputs=self.actions(engine.state["action_cursor"]);next_action=next(inputs,None)
        while engine.state["sim_tick"]<tick and not engine.terminal_result():
            records,next_action=self._inputs(engine,inputs,next_action);advance_recorded(engine,records)
        return engine.snapshot()


def frame(state,cut=False):
    ball=state["ball"]
    return {"tick":state["sim_tick"],"phase":state["phase"],"inning":state["inning"],"half":state["half"],
            "score":dict(state["score"]),"outs":state["outs"],"balls":state["balls"],"strikes":state["strikes"],
            "batter_id":state["batter_id"],"regulation_expired":state["regulation_expired"],"finish_after_inning":state["finish_after_inning"],
            "ball":{k:copy_value(ball[k]) for k in ("mode","position_q","velocity_q","holder_id","origin","fair_foul_status")},
            "players":[{k:copy_value(p[k]) for k in ("id","role","team_id","position_q","active_intents")} for p in state["players"]],
            "runners":[{k:r[k] for k in ("id","last_legal_base","target_base","force_obligation","retouch_obligation")} for r in state["runners"]],
            "pending_runs":[r["runner_id"] for r in state["pending_runs"]],"cut":cut}


def copy_value(v):
    import copy
    return copy.deepcopy(v)


def export_frames(record,output,progress=None,force=False):
    out=Path(output).resolve()
    if out==record.root or out in record.root.parents:raise ReplayError("mismatch","unsafe_cache_output")
    out.mkdir(parents=True,exist_ok=True)
    meta_path=out/"metadata.json"
    if meta_path.exists() and not force:
        try:
            meta=strict_loads(meta_path.read_text(encoding="utf-8"))
            if meta.get("format")=="bb-frames-v1" and meta.get("source_hash")==record.identity and meta.get("cache_status")=="ready" and meta.get("verification",{}).get("verification_status")=="verified_full":
                for c in meta["chunks"]:
                    path=out/f"chunk-{c['index']:06}.json"
                    if path.is_symlink() or file_digest(path)!=c["sha256"]:raise ValueError("cache_chunk_mismatch")
                return meta
        except (ValueError,KeyError,OSError):pass
    if meta_path.exists():
        try:old=strict_loads(meta_path.read_text(encoding="utf-8"))
        except ValueError:old={}
        if old.get("format")!="bb-frames-v1":raise ReplayError("mismatch","cache_output_not_owned")
    elif any(out.iterdir()):raise ReplayError("mismatch","cache_output_not_empty")
    atomic_json(meta_path,{"format":"bb-frames-v1","cache_status":"building","source_hash":record.identity})
    chunks=[];frames=[];events=[];navigation=[];counts={};total=0
    def flush():
        nonlocal frames,events,total
        if not frames:return
        index=len(chunks);path=out/f"chunk-{index:06}.json"
        if path.is_symlink():raise ReplayError("mismatch","unsafe_cache_chunk")
        atomic_json(path,{"frames":frames,"events":events})
        chunks.append({"index":index,"first_tick":frames[0]["tick"],"last_tick":frames[-1]["tick"],"count":len(frames),"sha256":file_digest(path)})
        total+=len(frames);frames=[];events=[]
    def capture(engine,step_events):
        s=engine.state
        significant=[e for e in step_events if e["type"] not in ("ActionAccepted","ActionClamped")]
        for e in significant:
            counts[e["type"]]=counts.get(e["type"],0)+1;events.append(e)
            if e["type"] in ("PitchReleased","PitchClockViolation","HalfInningStarted"):
                navigation.append({"tick":e["sim_tick"]+int(e["sub_tick_q"]>0),"type":e["type"],"payload":e["payload"]})
        if s["sim_tick"]%4==0 or significant or s["terminal_status"]:
            cut=any(e["type"] in ("BatContact","BallCaught","RunnerOut","HomeRun","PlayEnded","HalfInningStarted") for e in significant)
            frames.append(frame(s,cut))
            if len(frames)>=600:flush()
    verification=record.verify(progress=progress,on_state=capture);flush()
    meta={"format":"bb-frames-v1","cache_status":"ready","source_hash":record.identity,"tick_rate_hz":120,
          "frame_interval_ticks":4,"total_ticks":record.final_tick,"total_frames":total,"chunks":chunks,
          "navigation":navigation,"event_counts":counts,"field":record.manifest["field_config"],
          "verification":verification,"schema_version":VERSION}
    atomic_json(meta_path,meta);return meta


def main():
    p=argparse.ArgumentParser(description=__doc__);sub=p.add_subparsers(dest="command",required=True)
    for name in ("verify","seek","frames"):
        a=sub.add_parser(name);a.add_argument("--input",required=True)
        if name=="verify":a.add_argument("--from-start",action="store_true");a.add_argument("--checkpoint",type=int);a.add_argument("--progress",action="store_true")
        elif name=="seek":a.add_argument("--tick",required=True,type=int)
        else:a.add_argument("--output",required=True);a.add_argument("--force",action="store_true");a.add_argument("--progress",action="store_true")
    args=p.parse_args()
    try:
        record=ReplayRecord(args.input)
        if args.command=="seek":report={"verification_status":"unverified","state":record.seek(args.tick)}
        elif args.command=="verify":
            progress=(lambda t,total:print(canonical({"type":"progress","sim_tick":t,"total_ticks":total}).decode(),flush=True)) if args.progress else None
            report=record.verify(checkpoint=args.checkpoint,progress=progress)
        else:
            progress=(lambda t,total:print(canonical({"type":"progress","sim_tick":t,"total_ticks":total}).decode(),flush=True)) if args.progress else None
            meta=export_frames(record,args.output,progress=progress,force=args.force)
            report={"verification_status":meta["verification"]["verification_status"],"cache_status":meta["cache_status"],"output":str(Path(args.output).resolve()),"total_frames":meta["total_frames"],"source_hash":meta["source_hash"]}
        print(canonical(report).decode());return 0 if report["verification_status"] in ("verified_full","verified_prefix","unverified") else 2
    except ReplayError as error:print(canonical(error.report).decode());return 2
    except (ValueError,KeyError,OSError,RuntimeError,UnicodeError) as error:
        print(canonical({"verification_status":"mismatch","reason":"record_or_runtime_error","detail":str(error)}).decode());return 2


if __name__=="__main__":sys.exit(main())
