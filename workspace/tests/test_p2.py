import copy
import json
from pathlib import Path
import sys
import pytest
from baseball_engine import BaseballEngine
from configuration import default_config
from numeric import ONE, q, digest
from contracts import validate_named
from recording import Recorder, decision_record, batch_from_record

sys.path.insert(0,str(Path(__file__).resolve().parents[2]/"bots/examples"))
from script_controller import strikeout_actions


def quick_config():
    c=default_config()
    c["rules"].update(regulation_ticks=1,plate_appearance_setup_ticks=1,pitch_reset_ticks=1,
                      half_inning_change_ticks=1,pitch_release_deadline_ticks=20,max_ticks=10000)
    return c


def ready_engine():
    e=BaseballEngine(quick_config()); e.step()
    assert e.state["phase"] == "PITCH_READY"
    return e


def pitch_scene(x="0",y="1",z="1",active=True):
    e=ready_engine(); s=e.state
    s["ball"].update(mode="pitched",origin="pitch",holder_id=None,
                     position_q=[q(x),q(y),q(z)],velocity_q=["0",q(-30),"0"])
    e._phase("PITCH_IN_FLIGHT")
    a={"action_id":"swing-fixture","player_id":s["batter_id"],"kind":"swing",
       "power_u16":32768,"azimuth_mdeg":0,"elevation_mdeg":20000}
    s["swing_windows"]={"start_tick":s["sim_tick"] if active else s["sim_tick"]+100,"end_tick":s["sim_tick"]+12 if active else s["sim_tick"]+112,"action":a}
    s["swing_used"]=True
    return e


def test_T01_strikes_balls_sphere_rectangle_and_corners():
    e=ready_engine(); c=e.config
    assert e.native.strike([q(".253"),"0",q(".80")],c)
    assert not e.native.strike([q(".2531"),"0",q(".80")],c)
    assert not e.native.strike([q(".25"),"0",q("1.13")],c)  # rounded corner, not enlarged AABB
    s=e.state
    for i in range(2):
        e._pitch_call(strike=True);assert s["strikes"] == i+1
    e._pitch_call(strike=True)
    assert s["outs"]==1 and s["batting_order_index_by_team"]["away"]==1
    for _ in range(4):e._pitch_call()
    assert len(s["runners"])==1 and s["runners"][0]["last_legal_base"]==1


def test_T02_two_strike_foul_and_swing_miss():
    e=ready_engine();s=e.state;s["strikes"]=2
    e._pitch_call(strike=True,foul=True)
    assert s["strikes"]==2 and s["outs"]==0
    e._pitch_call(strike=True)
    assert s["outs"]==1 and s["strikes"]==0


@pytest.mark.parametrize("when,contact",[("inside",True),("before",False),("after",False),("outside",False)])
def test_T03_geometric_swing_windows_and_single_contact(when,contact):
    e=pitch_scene(x="2" if when=="outside" else "0")
    if when=="before":e.state["swing_windows"]["start_tick"]+=10
    if when=="after":e.state["swing_windows"]["end_tick"]=e.state["sim_tick"]
    events=[]
    for _ in range(4):events+=e.step()["events"]
    assert sum(x["type"]=="BatContact" for x in events)==int(contact)
    if contact:
        a=e.state["swing_windows"]["action"]
        assert e.validate_intents("away",[a])["validation_results"][0]["status"]=="rejected"


def test_T04_clock_exact_tick_four_violations_walk():
    e=ready_engine(); deadline=e.state["phase_deadline_tick"];events=[]
    while not e.state["runners"]:
        events+=e.step()["events"]
    violations=[x for x in events if x["type"]=="PitchClockViolation"]
    assert len(violations)==4 and violations[0]["sim_tick"]==deadline
    assert e.state["pitches_total"]==4


def test_T05_body_vs_swing_and_bat_priority():
    e=pitch_scene(x="-.8",y=".2",active=False)
    result=e.step()
    assert any(x["type"]=="HitByPitch" for x in result["events"])
    e=pitch_scene(x="-.8",y=".2",active=True)
    result=e.step()
    assert any(x["type"]=="StrikeCalled" for x in result["events"])
    assert not any(x["type"]=="HitByPitch" for x in result["events"])
    e=pitch_scene(x="-.55",y=".2",active=True)
    result=e.step()
    assert sum(x["type"]=="BatContact" for x in result["events"])==1
    assert not any(x["type"] in ("HitByPitch","StrikeCalled") for x in result["events"])


def test_T06_T07_ground_fair_foul_finalization():
    e=ready_engine()
    assert e.adjudicate_fair([q(12),q(10),"0"],"ground")=="undecided"
    assert e.adjudicate_fair([q(14),q(10),"0"],"touch")=="foul"
    e.state["ball"]["fair_foul_status"]="undecided"
    assert e.adjudicate_fair([q(10),q(10),"0"],"stop")=="fair"
    assert e.adjudicate_fair([q(30),q(10),"0"],"touch")=="fair"
    e.state["ball"]["fair_foul_status"]="undecided"
    assert e.adjudicate_fair([q(-19),q(20),"0"],"ground")=="fair"
    assert e.adjudicate_fair([q(-30),q(22),"0"],"ground")=="fair"
    e.state["ball"]["fair_foul_status"]="undecided"
    assert e.adjudicate_fair([q(20),q(19),"0"],"base")=="fair"


def test_T07_live_rolling_boundary_keeps_fair_after_later_foul_position():
    e=ready_engine();s=e.state;e._phase("BALL_IN_PLAY")
    s["ball"].update(mode="rolling",origin="batted",holder_id=None,has_touched_ground_since_bat=True,
                     position_q=[q(10),q("19.39"),e.config["physics"]["ball_radius_q"]],velocity_q=["0",q(7),"0"])
    e.step()
    assert s["ball"]["fair_foul_status"]=="fair"
    s["ball"]["position_q"]=[q(30),q(20),e.config["physics"]["ball_radius_q"]]
    e.step()
    assert s["ball"]["fair_foul_status"]=="fair"


def test_T18_loaded_and_nonloaded_walk_batting_order_once():
    e=ready_engine();s=e.state
    s["runners"]=[e._new_runner(f"away.P{i+1:02}",i) for i in (1,2,3)]
    e._walk()
    assert s["score"]["away"]==1
    assert sorted(r["last_legal_base"] for r in s["runners"])==[1,2,3]
    assert s["batting_order_index_by_team"]["away"]==1
    e=ready_engine();s=e.state;s["runners"]=[e._new_runner("away.P04",3)]
    e._walk()
    assert s["score"]["away"]==0
    assert sorted(r["last_legal_base"] for r in s["runners"])==[1,3]


def test_reset_pitcher_catcher_other_fielders_and_runners():
    e=ready_engine();s=e.state
    e.player("home.P01")["position_q"]=[q(8),q(8)]
    e.player("home.P02")["position_q"]=[q(9),q(9)]
    e.player("home.P06")["position_q"]=[q(-17),q(20)]
    s["runners"]=[e._new_runner("away.P04",2)]
    e.player("away.P04")["position_q"]=[q(9),q(9)]
    e._start_pa()
    assert e.player("home.P01")["position_q"]==e.config["field"]["defense_q"][0]
    assert e.player("home.P02")["position_q"]==e.config["field"]["defense_q"][1]
    assert e.player("home.P06")["position_q"]==[q(-17),q(20)]
    assert e.player("away.P04")["position_q"]==e.config["field"]["bases_q"][2]
    assert s["ball"]["mode"]=="pitcher_held"


def test_contract_rejections_clamping_and_restore_mid_swing():
    e=ready_engine()
    a=strikeout_actions(e.state,"home")[0]
    assert e.validate_intents("away",[a])["validation_results"][0]["reason"]=="unauthorized_player"
    bad=dict(a,extra=1)
    assert e.validate_intents("home",[bad])["accepted_intents"]==[]
    clamped=e.validate_intents("home",[dict(a,power_u16=100000)])
    assert clamped["accepted_intents"][0]["power_u16"]==65535
    e=pitch_scene();snapshot=e.snapshot();h=e.canonical_state_hash();e.restore(snapshot)
    assert e.canonical_state_hash()==h
    validate_named(snapshot,"state")


def test_two_scripted_halves_with_complete_recomputable_record(tmp_path):
    e=BaseballEngine(quick_config());rec=Recorder(tmp_path/"match",e)
    inputs=[];events=[];seq=0
    while not e.terminal_result():
        records=[]
        for team in ("away","home"):
            actions=strikeout_actions(e.observe(team),team)
            if actions:
                seq+=1;r=decision_record(e,team,actions,seq);records.append(r);inputs.append(r)
        result=e.step([batch_from_record(r) for r in records]);events+=result["events"]
        rec.write_step(e,result,records)
    summary=rec.finalize(e)
    assert summary["status"]=="completed" and summary["completed_halves"]=={"away":1,"home":1}
    assert sum(x["type"]=="Strikeout" for x in events)==6
    assert summary["score"]=={"away":0,"home":0}
    assert e.state["pitches_total"]==18
    assert e.state["batting_order_index_by_team"]=={"away":3,"home":3}
    e2=BaseballEngine(quick_config());replayed=[];by_tick={r["applied_tick"]:r for r in inputs}
    while not e2.terminal_result():
        r=by_tick.get(e2.state["sim_tick"])
        replayed+=e2.step([batch_from_record(r)] if r else [])["events"]
    assert replayed==events and e2.canonical_state_hash()==summary["final_state_hash"]
    from replay import ReplayRecord
    assert ReplayRecord(tmp_path/"match").verify()["summary"]==summary
    assert [p.name for p in (tmp_path/"match").iterdir()]==["match.txt"]
    with pytest.raises(ValueError):Recorder(tmp_path/"match",e)


def test_half_inning_caps_on_silent_pitcher():
    e=BaseballEngine(quick_config());events=[]
    while not e.terminal_result():events+=e.step()["events"]
    assert e.terminal_result()["status"]=="completed"
    assert e.state["score"]=={"away":10,"home":10}
    assert sum(x["type"]=="HalfInningCapped" for x in events)==2
