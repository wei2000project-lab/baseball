import json
from pathlib import Path
import subprocess
import pytest
from baseball_engine import BaseballEngine
from recording import Recorder,decision_record,advance_recorded,atomic_json
from numeric import digest,RNG
from numeric import strict_loads,stream_seed,q,ONE
from replay import ReplayRecord,ReplayError,file_digest,export_frames
from test_p2 import quick_config,strikeout_actions


def make_record(path):
    e=BaseballEngine(quick_config());rec=Recorder(path,e);seq=0
    while not e.terminal_result():
        records=[]
        for team in ("away","home"):
            actions=strikeout_actions(e.observe(team),team)
            if actions:seq+=1;records.append(decision_record(e,team,actions,seq))
        result=advance_recorded(e,records);rec.write_step(e,result,records)
    rec.finalize(e);return path


@pytest.fixture
def record_path(tmp_path):return make_record(tmp_path/"record")


def reseal(path,name):
    manifest=json.loads((path/"manifest.json").read_text())
    manifest["file_index"][name]={"size_bytes":(path/name).stat().st_size,"sha256":file_digest(path/name)}
    atomic_json(path/"manifest.json",manifest)


def edit_line(path,name,predicate,edit):
    values=[json.loads(s) for s in (path/name).read_text().splitlines()]
    edit(next(v for v in values if predicate(v)))
    (path/name).write_text("".join(json.dumps(v,separators=(",",":"))+"\n" for v in values),encoding="utf-8",newline="\n")
    reseal(path,name)


def test_D1_ten_full_recalculations_without_bot_execution(record_path,monkeypatch):
    def forbidden(*a,**k):raise AssertionError("replay attempted to start a Bot")
    monkeypatch.setattr(subprocess,"Popen",forbidden)
    record=ReplayRecord(record_path);expected=None
    for _ in range(10):
        report=record.verify();assert report["verification_status"]=="verified_full"
        if expected is None:expected=report
        assert report==expected


def test_every_checkpoint_restores_to_same_terminal(record_path):
    record=ReplayRecord(record_path)
    for index in range(len(record.checkpoint_index)):
        result=record.verify(checkpoint=index)
        assert result["verification_status"]=="verified_prefix"
        assert result["summary"]==record.summary


def test_100_exact_random_seeks_equal_sequential_states(record_path):
    record=ReplayRecord(record_path);rng=RNG(2026)
    ticks={0,record.final_tick};ticks.update(rng.next()%(record.final_tick+1) for _ in range(120))
    e=BaseballEngine();e.initialize(record.manifest["config"],record.initial)
    inputs=record.actions();next_action=next(inputs,None);expected={}
    while True:
        t=e.state["sim_tick"]
        if t in ticks:expected[t]=e.canonical_state_hash()
        if e.terminal_result():break
        records,next_action=record._inputs(e,inputs,next_action);advance_recorded(e,records)
    assert len(expected)>=100
    for t,h in expected.items():assert digest(record.seek(t))==h


def test_rehashed_event_reports_first_field_difference(record_path):
    edit_line(record_path,"events.jsonl",lambda e:e["type"]=="StrikeCalled",lambda e:e["payload"].update(strikes=99))
    with pytest.raises(ReplayError) as error:ReplayRecord(record_path).verify()
    r=error.value.report
    assert r["reason"]=="event_difference" and r["field"]=="$.payload.strikes" and r["seq"]>0


def test_rehashed_accepted_intent_corruption_rejected(record_path):
    edit_line(record_path,"actions.jsonl",lambda a:bool(a["accepted_intents"]),lambda a:a["accepted_intents"][0].update(power_u16=1))
    with pytest.raises(ReplayError,match="accepted_intents"):ReplayRecord(record_path).verify()


def test_rehashed_checkpoint_corruption_rejected(record_path):
    def edit(cp):
        cp["state"]["score"]["away"]=9;cp["state_hash"]=digest(cp["state"])
    edit_line(record_path,"checkpoints.jsonl",lambda cp:cp["resume_tick"]>0,edit)
    with pytest.raises(ReplayError,match="checkpoint_state"):ReplayRecord(record_path).verify()


def test_truncation_fails_integrity_and_unknown_version_rejected(record_path):
    path=record_path/"events.jsonl";original=path.read_bytes();path.write_bytes(original[:-3])
    with pytest.raises(ReplayError,match="file_integrity"):ReplayRecord(record_path)
    path.write_bytes(original)
    manifest=json.loads((record_path/"manifest.json").read_text());manifest["schema_version"]="future"
    atomic_json(record_path/"manifest.json",manifest)
    with pytest.raises(ReplayError) as e:ReplayRecord(record_path)
    assert e.value.report["verification_status"]=="unsupported_version"


def test_incomplete_record_only_verifies_sealed_prefix(tmp_path):
    e=BaseballEngine(quick_config());rec=Recorder(tmp_path/"prefix",e)
    for _ in range(200):rec.write_step(e,e.step())
    rec.close();record=ReplayRecord(tmp_path/"prefix");report=record.verify()
    assert report["verification_status"]=="verified_prefix" and report["record_status"]=="incomplete"
    assert report["verified_through_tick"]<200


def test_regenerable_chunk_cache_and_stale_chunk_rebuild(record_path,tmp_path):
    record=ReplayRecord(record_path);out=tmp_path/"cache";a=export_frames(record,out)
    assert a["verification"]["verification_status"]=="verified_full"
    assert a["total_frames"]>0 and all(c["count"]<=600 for c in a["chunks"])
    first=out/"chunk-000000.json";data=first.read_bytes();first.write_bytes(b"broken")
    b=export_frames(record,out)
    assert b==a and first.read_bytes()==data
    first.unlink();assert export_frames(record,out)==a


def test_rejected_fractional_json_is_audited_and_replayable(tmp_path):
    e=BaseballEngine(quick_config());rec=Recorder(tmp_path/"fractional",e)
    r=decision_record(e,"away",[{"action_id":.5,"player_id":"away.P01","kind":"swing","power_u16":.5}],1)
    rec.write_step(e,advance_recorded(e,[r]),[r]);seq=1
    while not e.terminal_result():
        inputs=[]
        for team in ("away","home"):
            actions=strikeout_actions(e.observe(team),team)
            if actions:seq+=1;inputs.append(decision_record(e,team,actions,seq))
        rec.write_step(e,advance_recorded(e,inputs),inputs)
    rec.finalize(e)
    assert ReplayRecord(tmp_path/"fractional").verify()["verification_status"]=="verified_full"


def test_bounded_legal_intent_fuzz_does_not_mutate_observation():
    e=BaseballEngine(quick_config());e.step();rng=RNG(1234);expected=e.canonical_state_hash()
    for i in range(100):
        action={"action_id":f"f{i}","player_id":"home.P01","kind":"pitch","direction_i32":[int(rng.next()%2000001)-1000000 for _ in range(3)],"power_u16":int(rng.next()%100000)-10000}
        result=e.validate_intents("home",[action]);assert result["accepted_intents"]
        assert 0<=result["accepted_intents"][0]["power_u16"]<=65535 and e.canonical_state_hash()==expected


def test_early_swing_whiff_is_strike_and_P4_behavior_is_versioned():
    from test_p2 import pitch_scene
    for legacy in (False,True):
        e=pitch_scene(x="2");e.state["swing_windows"].update(start_tick=0,end_tick=e.state["sim_tick"])
        if legacy:
            config=e.config.copy();config["version"]="1.0.0-dev.P4"
            state=e.snapshot();state.update(schema_version="1.0.0-dev.P4",ruleset_version="1.0.0-dev.P4",config_hash=digest(config))
            e.initialize(config,state)
        for _ in range(4):e.step()
        assert (e.state["balls"],e.state["strikes"])==((1,0) if legacy else (0,1))


def test_unpaired_surrogates_rejected_at_json_boundary():
    with pytest.raises(ValueError):strict_loads('"\\ud800"')


def test_derived_rng_and_exact_contact_golden_vectors():
    assert [stream_seed("42",name) for name in ("setup","engine","bot:away")]==[16059173231784216673,6010439204905073236,15716365118942522187]
    from native import Native
    n=Native();v=lambda *a:[q(x) for x in a]
    assert n.sweep_cylinder(v(-2,0,1),v(2,0,1),v(0,0,0),v(0,0,0),q(1),q(2))==ONE//4


def test_aborted_trace_at_same_tick_as_initial_checkpoint(tmp_path):
    e=BaseballEngine(quick_config());rec=Recorder(tmp_path/"aborted",e)
    record=decision_record(e,"away",None,1);record["fault"]="watchdog_timeout"
    rec.write_step(e,advance_recorded(e,[record]),[record]);rec.finalize(e)
    r=ReplayRecord(tmp_path/"aborted");report=r.verify()
    assert report["verification_status"]=="verified_full" and report["summary"]["status"]=="aborted"
    assert report["summary"]["winner"] is None


@pytest.mark.parametrize("scene",["swing","return"])
def test_rich_checkpoint_states_replay_every_suffix_to_terminal(tmp_path,scene):
    from test_p2 import pitch_scene
    from test_p3 import batted_engine
    if scene=="swing":e=pitch_scene(x="2")
    else:
        e=batted_engine((1,));r=next(r for r in e.state["runners"] if r["origin_base"]==1)
        r.update(target_base=2,leg_base=2);e.player(r["id"])["position_q"]=[q(15),q(24)]
        e.state["ball"]["has_touched_ground_since_bat"]=False;e._move_fielders();e._caught("home.P01",0)
    path=tmp_path/scene;rec=Recorder(path,e);seq=0
    while not e.terminal_result():
        records=[]
        for team in ("away","home"):
            actions=strikeout_actions(e.observe(team),team)
            if team==e.offense and e.state["phase"]=="BALL_IN_PLAY":
                for r in e.state["runners"]:
                    if r["retouch_obligation"] is not None and r["target_base"]!=r["retouch_obligation"]:
                        actions.append({"action_id":f"return-{seq}","player_id":r["id"],"kind":"return_to_base","target_base":r["retouch_obligation"]})
            if actions:seq+=1;records.append(decision_record(e,team,actions,seq))
        rec.write_step(e,advance_recorded(e,records),records)
        if e.state["sim_tick"] in (3,50):rec.checkpoint(e)
    rec.finalize(e);record=ReplayRecord(path)
    assert record.verify()["verification_status"]=="verified_full"
    for i in range(len(record.checkpoint_index)):
        assert record.verify(checkpoint=i)["summary"]==record.summary


def test_mapping_insertion_and_team_reply_order_do_not_change_state():
    from test_p2 import ready_engine
    a=ready_engine();b=BaseballEngine()
    def reverse(v):
        if isinstance(v,dict):return {k:reverse(x) for k,x in reversed(list(v.items()))}
        if isinstance(v,list):return [reverse(x) for x in v]
        return v
    b.initialize(reverse(a.config),reverse(a.snapshot()))
    pitch=strikeout_actions(a.observe("home"),"home")
    swing=[{"action_id":"simultaneous","player_id":"away.P01","kind":"swing","power_u16":30000,"azimuth_mdeg":0,"elevation_mdeg":10000}]
    home=a.validate_intents("home",pitch);away=a.validate_intents("away",swing)
    assert a.step([home,away])==b.step([away,home])
    assert a.canonical_state_hash()==b.canonical_state_hash()
