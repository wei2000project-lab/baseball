"""Direct TXT delta playback. Checks integrity, never claims physics re-simulation."""
import argparse
import bisect
import copy
import hashlib
from pathlib import Path
from types import SimpleNamespace
import sys
from configuration import VERSION,validate_config
from numeric import canonical,digest,strict_loads,ONE
from recording import atomic_json
from txt_record import MAGIC,restore


class ReplayError(ValueError):
    def __init__(self,status,reason,**details):
        self.report=dict(verification_status=status,reason=reason,**details)
        super().__init__(reason)


def file_digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


class ReplayRecord:
    def __init__(self,path):
        given=Path(path).resolve()
        self.root=given.parent if given.is_file() else given
        self.path=given if given.is_file() else given/"match.txt"
        if not self.path.exists():
            if (self.root/"manifest.json").exists():raise ReplayError("unsupported_version","legacy_json_record")
            raise ReplayError("mismatch","match_txt_missing")
        if self.path.is_symlink():raise ReplayError("mismatch","unsafe_record_path")
        self.deltas=[];self.ticks=[];self.events_by_tick={};self.snapshots=[];self.snapshot_ticks=[]
        self.manifest=None;self.summary=None;self.incomplete=True;values={};last=-1;sha=hashlib.sha256()
        with self.path.open("rb") as stream:
            first=stream.readline(1048577)
            if first.decode("utf-8").rstrip("\r\n")!=MAGIC:raise ReplayError("unsupported_version","txt_format_version")
            sha.update(first)
            for raw in stream:
                if len(raw)>1048576:raise ReplayError("mismatch","record_line_limit")
                if not raw.endswith(b"\n"):break # interrupted final write; no complete footer
                line=raw.decode("utf-8").rstrip("\r\n");parts=line.split("\t")
                if parts[0]=="END":
                    if not self.incomplete:raise ReplayError("mismatch","duplicate_footer")
                    footer=strict_loads(parts[1])
                    if footer["sha256"]!=sha.hexdigest():raise ReplayError("mismatch","file_integrity")
                    if footer.get("summary_sha256")!=digest(footer["summary"]):raise ReplayError("mismatch","summary_integrity")
                    self.summary=footer["summary"];self.incomplete=False
                    if stream.read(1):raise ReplayError("mismatch","record_tail")
                    break
                sha.update(raw)
                if parts[0]=="M" and self.manifest is None:
                    self.manifest=strict_loads(parts[1])
                    if any(self.manifest[k]!=VERSION for k in ("schema_version","ruleset_version","physics_version","map_version")):
                        raise ReplayError("unsupported_version","rules_or_physics_version")
                    try:validate_config(self.manifest["config"])
                    except ValueError as error:
                        raise ReplayError("unsupported_version" if "unsupported_version" in str(error) else "mismatch","record_config",detail=str(error)) from error
                elif self.manifest is None:raise ReplayError("mismatch","metadata_missing")
                elif parts[0]=="B":self.manifest["bots"]=strict_loads(parts[1])
                elif parts[0]=="T":
                    tick=int(parts[1]);delta={}
                    if tick<last or tick<0:raise ReplayError("mismatch","tick_order")
                    for item in parts[2:]:
                        key,sep,value=item.partition("=")
                        if not sep or key in delta or values and key not in values:raise ReplayError("mismatch","invalid_delta_key")
                        delta[key]=strict_loads(value)
                    if not delta:raise ReplayError("mismatch","empty_delta")
                    values.update(delta);last=tick
                    self.deltas.append(delta);self.ticks.append(tick)
                    if not self.snapshots or tick-self.snapshot_ticks[-1]>=600:
                        self.snapshots.append((len(self.deltas),copy.deepcopy(values)))
                        self.snapshot_ticks.append(tick)
                elif parts[0]=="E":
                    tick=int(parts[1]);event=strict_loads(parts[2])
                    if tick<last:raise ReplayError("mismatch","event_tick_order")
                    self.events_by_tick.setdefault(tick,[]).append(event)
                else:raise ReplayError("mismatch","unknown_record_line")
        if not self.manifest or not self.deltas or self.ticks[0]!=0:raise ReplayError("mismatch","initial_delta_missing")
        self.final_tick=self.summary["sim_tick"] if self.summary else max(last,max(self.events_by_tick,default=0))
        if last>self.final_tick:raise ReplayError("mismatch","summary_tick")
        self.identity=file_digest(self.path)
        self.initial=self.seek(0)
        final=self.seek(self.final_tick)
        if self.summary and digest(final)!=self.summary.get("replay_state_hash"):
            raise ReplayError("mismatch","final_projection_hash")
        if self.summary and (self.summary["score"]!=final["score"] or self.summary["status"]!=final["terminal_status"]):
            raise ReplayError("mismatch","summary_projection_difference")

    def seek(self,tick):
        if type(tick)is not int or not 0<=tick<=self.final_tick:raise ReplayError("mismatch","seek_tick_out_of_range")
        i=bisect.bisect_right(self.snapshot_ticks,tick)-1
        cursor,values=self.snapshots[i];values=copy.deepcopy(values)
        end=bisect.bisect_right(self.ticks,tick)
        for delta in self.deltas[cursor:end]:values.update(delta)
        return restore(values,tick,self.manifest["rosters"])

    def verify(self,checkpoint=None,progress=None,on_state=None):
        if checkpoint is not None:raise ReplayError("unsupported_version","txt_has_no_simulation_checkpoints")
        if file_digest(self.path)!=self.identity:raise ReplayError("mismatch","file_changed")
        if on_state:
            values={};cursor=0
            for tick in range(self.final_tick+1):
                while cursor<len(self.ticks) and self.ticks[cursor]==tick:
                    values.update(self.deltas[cursor]);cursor+=1
                on_state(SimpleNamespace(state=restore(values,tick,self.manifest["rosters"])),self.events_by_tick.get(tick,[]))
                if progress and tick%600==0:progress(tick,self.final_tick)
        return dict(verification_status="incomplete" if self.incomplete else "verified_record",
            verification_scope="TXT SHA-256 integrity and final viewer projection; no physics re-simulation",
            record_status="incomplete" if self.incomplete else self.summary["status"],
            verified_through_tick=self.final_tick,source_hash=self.identity,summary=self.summary)


def frame(state,cut=False):
    ball=state["ball"]
    return {"tick":state["sim_tick"],"phase":state["phase"],"inning":state["inning"],"half":state["half"],
            "score":dict(state["score"]),"outs":state["outs"],"balls":state["balls"],"strikes":state["strikes"],
            "batter_id":state["batter_id"],"regulation_expired":state["regulation_expired"],"finish_after_inning":state["finish_after_inning"],
            "ball":{k:copy_value(ball[k]) for k in ("mode","position_q","velocity_q","holder_id","origin","fair_foul_status")},
            "players":[{k:copy_value(p[k]) for k in ("id","role","team_id","position_q","active_intents","dive_until_tick","dive_ready_tick","catch_ready_tick")} for p in state["players"]],
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
            if meta.get("format")=="bb-frames-v2" and meta.get("source_hash")==record.identity and meta.get("cache_status")=="ready" and meta.get("verification",{}).get("verification_status")=="verified_record":
                for c in meta["chunks"]:
                    path=out/f"chunk-{c['index']:06}.json"
                    if path.is_symlink() or file_digest(path)!=c["sha256"]:raise ValueError("cache_chunk_mismatch")
                return meta
        except (ValueError,KeyError,OSError):pass
    if meta_path.exists():
        try:old=strict_loads(meta_path.read_text(encoding="utf-8"))
        except ValueError:old={}
        if old.get("format")!="bb-frames-v2":raise ReplayError("mismatch","cache_output_not_owned")
    elif any(out.iterdir()):raise ReplayError("mismatch","cache_output_not_empty")
    atomic_json(meta_path,{"format":"bb-frames-v2","cache_status":"building","source_hash":record.identity})
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
    meta={"format":"bb-frames-v2","cache_status":"ready","source_hash":record.identity,"tick_rate_hz":120,
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
        print(canonical(report).decode());return 0 if report["verification_status"] in ("verified_record","verified_prefix","unverified") else 2
    except ReplayError as error:print(canonical(error.report).decode());return 2
    except (ValueError,KeyError,OSError,RuntimeError,UnicodeError) as error:
        print(canonical({"verification_status":"mismatch","reason":"record_or_runtime_error","detail":str(error)}).decode());return 2


if __name__=="__main__":sys.exit(main())
