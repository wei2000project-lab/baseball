"""P3 mandatory rules matrix T08–T22 and timed fairness boundaries."""
import copy
import pytest
from baseball_engine import BaseballEngine
from configuration import default_config
from numeric import q, ONE
from contracts import validate_named
from test_p2 import ready_engine, pitch_scene, quick_config


def batted_engine(bases=()):
    e=pitch_scene();s=e.state
    s["runners"]=[e._new_runner(f"away.P{i+2:02}",base) for i,base in enumerate(bases)]
    for r in s["runners"]:e.player(r["id"])["position_q"]=e.config["field"]["bases_q"][r["last_legal_base"]][:]
    s["pitch_start_bases"]=copy.deepcopy(s["runners"])
    e._bat_contact();e._sub=0
    # Freeze the free ball for holder/running scenarios, away from all fielders.
    s["ball"].update(mode="rolling",position_q=[q(60),q(60),e.config["physics"]["ball_radius_q"]],velocity_q=["0"]*3,
                     has_touched_ground_since_bat=True,fair_foul_status="fair")
    return e


def batches(e,team,actions):return [e.validate_intents(team,actions)]


def holder(e,pid="home.P03",base=1):
    e.player(pid)["position_q"]=e.config["field"]["bases_q"][base%4][:]
    e.state["ball"].update(mode="fielder_held",holder_id=pid,origin="batted",velocity_q=["0"]*3)


def test_T08_foul_fly_catch_and_ground_tie():
    e=batted_engine();b=e.state["ball"]
    b.update(mode="batted_airborne",position_q=[q(-5),q(-2),q(1)],velocity_q=["0"]*3,
             has_touched_ground_since_bat=False,fair_foul_status="undecided")
    p=e.player("home.P02");p["position_q"]=[q(-5),q(-2)];p["active_intents"]["catch"]=True
    events=e.step()["events"]
    assert any(x["type"]=="RunnerOut" and x["payload"]["reason"]=="flyout" for x in events)
    assert e.state["outs"]==1
    e=batted_engine();e.config["physics"]["gravity_q"]="1";p=e.player("home.P01");p["position_q"]=["0","0"];p["active_intents"]["catch"]=True
    radius=int(e.config["physics"]["catch_radius_q"]);ball_radius=int(e.config["physics"]["ball_radius_q"])
    e.state["ball"].update(mode="batted_airborne",position_q=[str(-radius-42*ONE//120),"0",str(ball_radius+60*ONE//120)],
                           velocity_q=[q(42),"0",q(-60)],has_touched_ground_since_bat=False)
    events=e.step()["events"]+e.step()["events"]
    assert any(x["type"]=="GroundContact" for x in events)
    assert not any(x["type"]=="RunnerOut" and x["payload"]["reason"]=="flyout" for x in events)


def test_T09_multi_catch_stable_ids_and_throw_catch_not_flyout():
    e=batted_engine();s=e.state
    s["ball"].update(mode="thrown",origin="throw",position_q=["0",q(15),q(1)],velocity_q=["0"]*3,has_touched_ground_since_bat=False)
    for pid in ("home.P05","home.P03"):
        p=e.player(pid);p.update(position_q=["0",q(15)],active_intents={"catch":True})
    events=e.step()["events"]
    assert s["ball"]["holder_id"]=="home.P03" and s["outs"]==0
    assert sum(x["type"]=="BallCaught" for x in events)==1


def test_T10_wall_hr_and_bounced_double_awards():
    e=batted_engine((1,2));s=e.state
    s["ball"].update(mode="batted_airborne",origin="batted",position_q=["0",q("99.99"),q(4)],velocity_q=["0",q(10),"0"],has_touched_ground_since_bat=False)
    events=e.step()["events"]
    assert any(x["type"]=="HomeRun" for x in events) and s["score"]["away"]==3
    e=batted_engine((1,2));s=e.state
    s["ball"].update(position_q=[q("84.99"),q(10),e.config["physics"]["ball_radius_q"]],velocity_q=[q(10),"0","0"])
    events=e.step()["events"]
    assert s["score"]["away"]==1 and sorted(r["last_legal_base"] for r in s["runners"])==[2,3]
    assert any(x["type"]=="BaseAwarded" and x["payload"]["reason"]=="ground_rule_double" for x in events)
    e=batted_engine();s=e.state
    s["ball"].update(mode="batted_airborne",position_q=["0",q("99.99"),q(1)],velocity_q=["0",q(10),"0"])
    assert any(x["type"]=="WallContact" for x in e.step()["events"])
    assert s["phase"]=="BALL_IN_PLAY"


def test_T11_non_holder_base_no_out_then_force():
    e=batted_engine();s=e.state
    e.player("home.P03")["position_q"]=e.config["field"]["bases_q"][1][:]
    e.step();assert s["outs"]==0
    holder(e);events=e.step()["events"]
    assert s["outs"]==1 and any(x["type"]=="RunnerOut" and x["payload"]["is_force"] for x in events)


def test_T12_arrival_force_same_time_safe():
    e=batted_engine();s=e.state;r=s["runners"][0];base=e.config["field"]["bases_q"][1]
    e.player(r["id"])["position_q"]=base[:];r.update(target_base=1,leg_base=1)
    holder(e);events=e.step()["events"]
    assert s["outs"]==0 and r["last_legal_base"]==1 and r["force_obligation"] is None
    assert any(x["type"]=="BaseTouched" for x in events)


def test_T13_double_play_and_removed_pressure_clears_force():
    e=batted_engine((1,));s=e.state;holder(e,base=2)
    e.step();assert s["outs"]==1
    holder(e,base=1);e.step();assert s["outs"]==2
    e=batted_engine((1,));s=e.state;holder(e,base=1)
    e.step();assert s["outs"]==1
    original=s["runners"][0];assert original["force_obligation"] is None
    holder(e,base=2);e.step();assert s["outs"]==1


def test_T14_batter_reaches_first_keeps_existing_force():
    e=batted_engine((1,));s=e.state;batter=next(r for r in s["runners"] if r["id"]==s["batter_id"])
    e.player(batter["id"])["position_q"]=e.config["field"]["bases_q"][1][:];batter.update(target_base=1,leg_base=1)
    e.step()
    original=next(r for r in s["runners"] if r["id"]!=s["batter_id"])
    assert original["force_obligation"]==2


@pytest.mark.parametrize("force,before_first",[(True,False),(False,True)])
def test_T15_third_force_or_batter_before_first_cancels_all(force,before_first):
    e=batted_engine();s=e.state;s["pending_runs"]=[{"runner_id":"away.P09","time":[0,0],"order":0}]
    s["third_out"]={"time":[s["sim_tick"],10],"is_force":force,"batter_before_first":before_first};s["outs"]=3
    e._finish_play()
    assert s["score"]["away"]==0 and any(x["type"]=="RunCancelled" for x in e.events)


@pytest.mark.parametrize("delta,score",[(-1,1),(0,0),(1,0)])
def test_T16_nonforce_third_time_strict(delta,score):
    e=batted_engine();s=e.state;s["pending_runs"]=[{"runner_id":"away.P09","time":[s["sim_tick"],100+delta],"order":0}]
    s["third_out"]={"time":[s["sim_tick"],100],"is_force":False,"batter_before_first":False};s["outs"]=3
    e._finish_play();assert s["score"]["away"]==score


def test_T17_fly_return_appeal_and_completed_return():
    e=batted_engine((1,));s=e.state;r=next(r for r in s["runners"] if r["origin_base"]==1)
    e.player(r["id"])["position_q"]=[q(15),q(24)]
    s["ball"]["has_touched_ground_since_bat"]=False
    e._move_fielders();e._caught("home.P01",0)
    assert s["outs"]==1 and r["force_obligation"] is None and r["retouch_obligation"]==1
    holder(e,base=1)
    e.player("home.P03")["active_intents"]["appeal_return"]=r["id"]
    assert any(x["type"]=="RunnerOut" and x["payload"]["reason"]=="appeal" for x in e.step()["events"])
    e=batted_engine((1,));s=e.state;r=next(r for r in s["runners"] if r["origin_base"]==1)
    s["ball"]["has_touched_ground_since_bat"]=False
    e._move_fielders();e._caught("home.P01",0)
    assert r["retouch_obligation"] is None


def test_T19_overtaking_and_base_ownership():
    e=batted_engine((1,));s=e.state
    lead=next(r for r in s["runners"] if r["origin_base"]==1);back=next(r for r in s["runners"] if r["origin_base"]==0)
    back.update(last_legal_base=1,leg_base=2,has_first=True,force_obligation=None)
    e.player(back["id"])["position_q"]=e.config["field"]["bases_q"][1][:]
    e._move_fielders();assert not e._safe(back)
    e.player(back["id"])["position_q"]=e.config["field"]["bases_q"][2][:]
    events=e.step()["events"]
    assert any(x["type"]=="RunnerOut" and x["payload"]["reason"]=="overtaking" for x in events)


def test_T20_throw_out_uses_release_legal_bases():
    e=batted_engine((1,));s=e.state;holder(e,base=3)
    action={"action_id":"throw1","player_id":"home.P03","kind":"throw","direction_i32":[1000000,0,0],"power_u16":65535}
    e.step(batches(e,"home",[action]))
    for _ in range(e.config['rules']['throw_windup_ticks']):e.step()
    s["ball"].update(position_q=[q("84.99"),q(1),q(1)],velocity_q=[q(20),"0","0"])
    events=e.step()["events"]
    assert sorted(r["last_legal_base"] for r in s["runners"])==[2,3]
    assert any(x["type"]=="BaseAwarded" and x["payload"]["reason"]=="throw_out" for x in events)


def test_T21_pending_runner_or_return_prevents_recovery():
    e=batted_engine();s=e.state;e.config["rules"]["loose_ball_recovery_ticks"]=2
    for _ in range(5):e.step()
    assert s["phase"]=="BALL_IN_PLAY" and s["recovery_counter"]==0
    r=s["runners"][0];r.update(last_legal_base=1,leg_base=2,force_obligation=None,retouch_obligation=1)
    e.player(r["id"])["position_q"]=e.config["field"]["bases_q"][1][:]
    for _ in range(5):e.step()
    assert s["phase"]=="BALL_IN_PLAY" and s["recovery_counter"]==0


def test_T22_safe_stopped_loose_recovery_exact_wait():
    e=batted_engine();s=e.state;s["runners"]=[];e.config["rules"]["loose_ball_recovery_ticks"]=3
    assert not any(x["type"]=="AdministrativeBallRecovery" for x in e.step()["events"])
    assert not any(x["type"]=="AdministrativeBallRecovery" for x in e.step()["events"])
    assert any(x["type"]=="AdministrativeBallRecovery" for x in e.step()["events"])
    assert s["phase"]=="PLATE_APPEARANCE_SETUP"


def test_runner_path_stops_and_live_holder_settles():
    e=batted_engine();s=e.state;r=s["runners"][0];holder(e,"home.P01",base=2)
    e.config["rules"]["settle_ticks"]=3
    a={"action_id":"run1","player_id":r["id"],"kind":"run_to_base","target_base":1}
    e.step(batches(e,"away",[a]))
    for _ in range(1000):
        result=e.step()
        if s["phase"]!="BALL_IN_PLAY":break
    else:pytest.fail("running did not settle")
    assert s["runners"][0]["last_legal_base"]==1
    assert e.player(s["runners"][0]["id"])["velocity_q"]==["0","0"]


@pytest.mark.parametrize("half,transition",[("top",False),("bottom",False),("top",True),("bottom",True)])
def test_time_expiry_in_play_or_transition(half,transition):
    e=ready_engine();s=e.state;s["inning"]=3;s["half"]=half;s["regulation_expired"]=False;s["finish_after_inning"]=None
    s["completed_halves"]={"away":2 if half=="top" else 3,"home":2}
    e.config["rules"]["regulation_ticks"]=s["sim_tick"]+1
    if transition:
        s["outs"]=3;e._finish_half()
    events=e.step()["events"]
    assert s["finish_after_inning"]==3
    assert sum(x["type"]=="RegulationExpired" for x in events)==1
    if half=="bottom" and transition:assert s["terminal_status"]=="completed"
    else:assert not s["terminal_status"]


@pytest.mark.parametrize("offset",[-1,0,1])
def test_time_third_out_boundary_and_transition_end(offset):
    e=ready_engine();s=e.state;s["half"]="bottom";s["completed_halves"]={"away":1,"home":0};s["regulation_expired"]=False;s["finish_after_inning"]=None
    s["outs"]=3;e._finish_half();end=s["phase_deadline_tick"]
    e.config["rules"]["regulation_ticks"]=end+offset
    events=[]
    for _ in range(4):
        events+=e.step()["events"]
        if s["terminal_status"]:break
    if offset<=0:
        assert s["terminal_status"]=="completed" and s["finish_after_inning"]==1
    else:
        assert s["inning"]==2 and s["finish_after_inning"]==2


def test_normal_finish_precedes_guard_and_pa_cap():
    e=ready_engine();s=e.state;s.update(half="bottom",outs=3,regulation_expired=True,finish_after_inning=1)
    s["completed_halves"]={"away":1,"home":0};e._finish_half();e.config["rules"]["max_ticks"]=s["sim_tick"]+1
    e.step();assert s["terminal_status"]=="completed"
    e=ready_engine();e.state["half_pa"]=15;e._finish_pa()
    assert e.state["phase"]=="HALF_TRANSITION" and any(x["type"]=="HalfInningCapped" for x in e.events)
    e=ready_engine();e.config["rules"]["max_ticks"]=e.state["sim_tick"]+1;e.step()
    assert e.terminal_result()["status"]=="aborted" and e.terminal_result()["winner"] is None


def test_return_running_and_snapshot_restore_have_same_future():
    e=batted_engine((1,));s=e.state;r=next(r for r in s["runners"] if r["origin_base"]==1)
    r.update(target_base=2,leg_base=2)
    e.player(r["id"])["position_q"]=[q(15),q(24)]
    s["ball"]["has_touched_ground_since_bat"]=False
    e._move_fielders();e._caught("home.P01",0)
    assert r["retouch_obligation"]==1
    action={"action_id":"return1","player_id":r["id"],"kind":"return_to_base","target_base":1}
    e.step(batches(e,"away",[action]));snapshot=e.snapshot();validate_named(snapshot,"state")
    restored=BaseballEngine();restored.initialize(e.config,snapshot)
    for _ in range(200):
        assert restored.step()==e.step()
        assert restored.canonical_state_hash()==e.canonical_state_hash()
    assert r["retouch_obligation"] is None and r["last_legal_base"]==1


def test_actual_tag_unsafe_forced_runner_and_safe_owner():
    e=batted_engine((1,));s=e.state;r=next(r for r in s["runners"] if r["origin_base"]==1)
    holder(e,base=1)
    e.player("home.P03")["position_q"][0]=str(int(e.player("home.P03")["position_q"][0])+int(q(".4")))
    tag={"action_id":"tag1","player_id":"home.P03","kind":"tag","runner_id":r["id"]}
    result=e.step(batches(e,"home",[tag]))
    assert any(x["type"]=="RunnerOut" and x["payload"]["reason"]=="tag" for x in result["events"])
    e=batted_engine();s=e.state;r=s["runners"][0];r.update(last_legal_base=1,leg_base=2,force_obligation=None,has_first=True)
    e.player(r["id"])["position_q"]=e.config["field"]["bases_q"][1][:];holder(e,base=1)
    tag["runner_id"]=r["id"]
    e.step(batches(e,"home",[tag]));assert s["outs"]==0


def test_unconverged_bot_hits_guard_and_events_monotonic():
    config=quick_config();config["rules"]["max_ticks"]=100
    e=BaseballEngine(config);events=[]
    while not e.terminal_result():events+=e.step()["events"]
    assert e.terminal_result()["status"]=="aborted"
    assert e.terminal_result()["winner"] is None
    times=[(x["sim_tick"],x["sub_tick_q"]) for x in events]
    assert times==sorted(times)
    assert sum(x["type"]=="GameAborted" for x in events)==1
