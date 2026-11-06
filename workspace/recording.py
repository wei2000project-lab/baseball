"""Append-only self-contained records, independent of Bot and viewer."""
import hashlib
from pathlib import Path
import os
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


def atomic_json(path, value):
    temp = path.with_suffix(path.suffix+".tmp")
    temp.write_bytes(canonical(value)+b"\n")
    os.replace(temp,path)


class Recorder:
    FILES = ("initial_state.json","actions.jsonl","events.jsonl","checkpoints.jsonl","summary.json")

    def __init__(self, path, engine, seed="42", bots=None, run_mode="diagnostic"):
        self.path = Path(path)
        if self.path.exists() and any(self.path.iterdir()): raise ValueError("output_not_empty")
        self.path.mkdir(parents=True,exist_ok=True)
        (self.path/"diagnostics").mkdir()
        self.manifest = {"schema_version":VERSION,"ruleset_version":engine.config["version"],
                         "physics_version":engine.config["physics"]["version"],"map_version":engine.config["field"]["version"],
                         "bot_protocol_version":"1.0.0","match_id":self.path.name,"seed":seed,"run_mode":run_mode,
                         "tick_rate_hz":120,"regulation_ticks":engine.config["rules"]["regulation_ticks"],
                         "rules_config":engine.config["rules"],"physics_config":engine.config["physics"],"field_config":engine.config["field"],
                         "config":engine.config,"bots":bots or {},"numeric_format":"Q32.32",
                         "canonicalization_version":"bb-canon-v1","hash_algorithm":"SHA-256","file_index":{},"record_status":"recording",
                         "engine_build_id":source_hash(),"native_build_id":source_hash(native=True)}
        atomic_json(self.path/"manifest.json",self.manifest)
        atomic_json(self.path/"initial_state.json",engine.snapshot())
        self.streams = {name:open(self.path/(name+".jsonl"),"wb") for name in ("actions","events","checkpoints")}
        self.last_checkpoint = -1
        self.checkpoint(engine)

    def append(self, name, value):
        self.streams[name].write(canonical(value)+b"\n")

    def checkpoint(self, engine):
        state = engine.snapshot()
        if state["sim_tick"] == self.last_checkpoint: return
        self.append("checkpoints",{"stage":"POST_BOUNDARY","resume_tick":state["sim_tick"],"state":state,
                                   "state_hash":digest(state),"action_cursor":state["action_cursor"],"last_event_seq":state["last_event_seq"]})
        self.last_checkpoint = state["sim_tick"]

    def write_step(self, engine, result, decisions=()):
        for record in decisions: self.append("actions",record)
        for event in result["events"]: self.append("events",event)
        if result["checkpoint"]: self.checkpoint(engine)
        if engine.state["sim_tick"] % 600 == 0:
            for stream in self.streams.values(): stream.flush()

    def finalize(self, engine):
        result = engine.terminal_result()
        if result is None: raise ValueError("cannot_finalize_running_match")
        self.checkpoint(engine)
        for stream in self.streams.values(): stream.flush();stream.close()
        atomic_json(self.path/"summary.json",result)
        self.manifest["file_index"] = {name:{"size_bytes":(self.path/name).stat().st_size,
                                               "sha256":hashlib.sha256((self.path/name).read_bytes()).hexdigest()} for name in self.FILES}
        self.manifest["record_status"] = "complete" if result["status"] == "completed" else "aborted"
        atomic_json(self.path/"manifest.json",self.manifest)
        return result

    def close(self):
        for stream in self.streams.values():
            if not stream.closed: stream.close()


def source_hash(native=False):
    root = Path(__file__).resolve().parent
    names = ["baseball.hpp","baseball.cpp","map.hpp","map.cpp","native_bindings.cpp"] if native else ["baseball_engine.py","numeric.py","configuration.py","contracts.py","native.py"]
    sha = hashlib.sha256()
    for name in names: sha.update(name.encode());sha.update((root/name).read_bytes().replace(b"\r\n",b"\n"))
    return sha.hexdigest()
