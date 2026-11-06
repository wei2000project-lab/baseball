"""Append-only self-contained records, independent of Bot and viewer."""
import hashlib
from pathlib import Path
import os
import json
from numeric import canonical, digest
from configuration import VERSION

BATCH_FIELDS = ("team_id","requested_actions","accepted_intents","validation_results")


def batch_from_record(record):
    return {k:record[k] for k in BATCH_FIELDS}


def decision_record(engine, team, requested, seq, raw_response=None):
    return {"seq":seq,"decision_id":f"d{seq:09}","observation_tick":engine.state["sim_tick"],
            "applied_tick":engine.state["sim_tick"],"observation_hash":digest(engine.observe(team)),
            "raw_response":raw_response,"parse_error":None,"fault":None,"fallback":None,
            **engine.validate_intents(team,requested)}


def advance_recorded(engine,records):
    faults=[r for r in records if r.get("fault")]
    if faults:
        engine.events=[];engine._sub=0
        engine.state["action_cursor"]+=len(records)
        r=sorted(faults,key=lambda r:r["team_id"])[0]
        fault=r["fault"]
        reason=f"{fault['source']}:{fault['reason']}" if isinstance(fault,dict) else f"bot:{r['team_id']}:{fault}"
        engine.abort(reason)
        return {"sim_tick":engine.state["sim_tick"],"events":engine.events,"terminal":True,"checkpoint":True,"phase":engine.state["phase"]}
    return engine.step([batch_from_record(r) for r in records])


def atomic_json(path, value):
    temp = path.with_suffix(path.suffix+".tmp")
    temp.write_bytes(canonical(value)+b"\n")
    os.replace(temp,path)


class Recorder:
    """One human-readable match.txt; unchanged coordinates are never repeated."""
    def __init__(self,path,engine,seed="42",bots=None,run_mode="diagnostic"):
        from txt_record import MAGIC,encode,project,delta_line
        self.path=Path(path)
        if self.path.exists() and any(self.path.iterdir()):raise ValueError("output_not_empty")
        self.path.mkdir(parents=True,exist_ok=True)
        self.diagnostics_path=Path(__file__).resolve().parent/"build/runlogs"/hashlib.sha256(str(self.path.resolve()).encode()).hexdigest()[:16]
        self.diagnostics_path.mkdir(parents=True,exist_ok=True)
        self.manifest={"schema_version":engine.config["version"],"ruleset_version":engine.config["version"],
            "physics_version":engine.config["physics"]["version"],"map_version":engine.config["field"]["version"],
            "config":engine.config,"field_config":engine.config["field"],"seed":str(seed),"bots":bots or {},
            "run_mode":run_mode,"tick_rate_hz":120,"numeric_format":"Q32.32 integer units; metres = value / 4294967296",
            "rosters":{team:[{"id":p["id"],"role":p["role"]} for p in engine.state["players"] if p["team_id"]==team] for team in ("away","home")}}
        self.stream=open(self.path/"match.txt","wb");self.sha=hashlib.sha256();self.closed=False
        self._write(MAGIC+"\n");self._write("M\t"+encode(self.manifest)+"\n")
        self.previous=project(engine.state);self._write(delta_line(engine.state["sim_tick"],{},self.previous))

    def _write(self,line,hashed=True):
        data=line.encode("utf-8");self.stream.write(data)
        if hashed:self.sha.update(data)

    def update_bots(self):
        from txt_record import encode
        self._write("B\t"+encode(self.manifest["bots"])+"\n")

    def write_step(self,engine,result,decisions=()):
        from txt_record import encode,project,delta_line
        current=project(engine.state);line=delta_line(engine.state["sim_tick"],self.previous,current)
        if line:self._write(line)
        self.previous=current
        for event in result["events"]:
            if event["type"] not in ("ActionAccepted","ActionClamped"):
                self._write("E\t"+str(engine.state["sim_tick"])+"\t"+encode(event)+"\n")
        if engine.state["sim_tick"]%600==0:self.stream.flush()

    def finalize(self,engine):
        from txt_record import encode,project,restore
        result=engine.terminal_result()
        if result is None:raise ValueError("cannot_finalize_running_match")
        # Abort may happen without advancing the clock; persist that final delta too.
        self.write_step(engine,{"events":[]})
        state=restore(self.previous,engine.state["sim_tick"],self.manifest["rosters"])
        result["replay_state_hash"]=digest(state)
        footer={"summary":result,"summary_sha256":digest(result),"sha256":self.sha.hexdigest()}
        self._write("END\t"+encode(footer)+"\n",hashed=False);self.close()
        return result

    def close(self):
        if not self.closed:self.stream.close();self.closed=True


def source_hash(native=False):
    root = Path(__file__).resolve().parent
    names = ["baseball.hpp","baseball.cpp","map.hpp","map.cpp","native_bindings.cpp"] if native else ["baseball_engine.py","numeric.py","configuration.py","contracts.py","native.py","recording.py","txt_record.py"]
    if not native:names+=sorted("contracts/"+p.name for p in (root/"contracts").glob("*.json"))
    sha = hashlib.sha256()
    for name in names: sha.update(name.encode());sha.update((root/name).read_bytes().replace(b"\r\n",b"\n"))
    return sha.hexdigest()
