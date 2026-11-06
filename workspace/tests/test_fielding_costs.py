"""Live-play timing boundaries, snapshot continuation, and held movement costs."""
from baseball_engine import BaseballEngine
from numeric import q,ONE
from txt_record import project,restore
from test_p3 import batted_engine,holder,batches


def throw(pid):
    return dict(action_id='throw',player_id=pid,kind='throw',direction_i32=[0,-1000000,0],power_u16=65535)


def test_catch_freezes_at_contact_and_blocks_until_exact_recovery_boundary():
    e=batted_engine();p=e.player('home.P03');p['velocity_q']=[q(4),'0']
    p['active_intents']['move']=[q(40),q(20)]
    e._move_fielders();expected=e._at(p['id'],ONE//2)
    e._caught(p['id'],ONE//2)
    assert p['position_q']==expected and p['velocity_q']==['0','0']
    assert p['catch_recovery_until_tick']==e.state['sim_tick']+1+e.config['rules']['catch_recovery_ticks']
    move=dict(action_id='move',player_id=p['id'],kind='move',target_q=[q(40),q(20)])
    while e.state['sim_tick']<p['catch_recovery_until_tick']:
        for action in (move,throw(p['id'])):
            assert not e.validate_intents('home',[action])['accepted_intents']
        e.step();assert p['position_q']==expected and p['velocity_q']==['0','0']
    assert e.validate_intents('home',[move])['accepted_intents']
    assert e.validate_intents('home',[throw(p['id'])])['accepted_intents']


def test_windup_cannot_be_restarted_or_bypassed_and_restores_deterministically():
    e=batted_engine();holder(e,base=2);p=e.player('home.P03');start=p['position_q'][:]
    p['velocity_q']=[q(4),'0'];events=e.step(batches(e,'home',[throw(p['id'])]))['events']
    assert any(x['type']=='ThrowWindupStarted' for x in events)
    assert not any(x['type']=='ThrowReleased' for x in events)
    release=p['throw_release_tick'];snapshot=e.snapshot();other=BaseballEngine();other.initialize(e.config,snapshot)
    while e.state['sim_tick']<=release:
        assert not e.validate_intents('home',[throw(p['id'])])['accepted_intents']
        hold=dict(action_id='hold',player_id=p['id'],kind='hold')
        a=e.step(batches(e,'home',[hold]));b=other.step(batches(other,'home',[hold]))
        assert a==b and e.snapshot()==other.snapshot()
        assert p['position_q']==start
        if a['events'] and any(x['type']=='ThrowReleased' for x in a['events']):
            event=next(x for x in a['events'] if x['type']=='ThrowReleased')
            assert event['sim_tick']==release and event['payload']['running_velocity_q']==[q(4),'0']
        else:assert e.state['ball']['holder_id']==p['id']
    assert e.state['ball']['holder_id'] is None and p['pending_throw'] is None


def test_held_speed_limit_and_runner_speed_are_independent():
    e=batted_engine();holder(e,base=2);p=e.player('home.P03')
    p['active_intents']['move']=[q(70),q(70)]
    maximum=int(e.native.numeric(0,e.config['physics']['fielder_speed_q'],e.config['physics']['held_speed_multiplier_q']))
    for _ in range(120):
        e._move_fielders()
        assert sum(int(v)**2 for v in p['velocity_q'])<=(maximum+8)**2
    assert sum(int(v)**2 for v in p['velocity_q'])>=(maximum-8)**2
    assert 8*ONE<=int(e.config['physics']['player_speed_q'])<=int(q(8.5))


def test_dead_ball_cancels_pending_throw_and_txt_preserves_busy_state():
    e=batted_engine();holder(e,base=2);p=e.player('home.P03')
    e.step(batches(e,'home',[throw(p['id'])]))
    rosters={t:[dict(id=x['id'],role=x['role']) for x in e.state['players'] if x['team_id']==t] for t in ('away','home')}
    decoded=restore(project(e.state),e.state['sim_tick'],rosters)
    replay_player=next(x for x in decoded['players'] if x['id']==p['id'])
    assert replay_player['pending_throw']==p['pending_throw'] and replay_player['throw_release_tick']==p['throw_release_tick']
    e._start_pa()
    assert p['pending_throw'] is None and p['throw_release_tick']==p['catch_recovery_until_tick']==0
    assert not any(x['type']=='ThrowReleased' for x in e.step()['events'])


def test_fielding_timing_golden():
    import json
    from pathlib import Path
    from configuration import default_config,VERSION
    from numeric import digest
    from regenerate_golden import fielding_trace
    expected=json.loads((Path(__file__).parent/'golden/fielding-v2.1.json').read_text())
    config=default_config()
    assert expected['ruleset_version']==expected['physics_version']==VERSION
    assert expected['config_hash']==digest(config)
    assert expected['trace_sha256']==digest(fielding_trace(config))


def test_throw_awards_capture_legal_bases_at_release_after_windup():
    e=batted_engine((1,));holder(e,base=3);r=e.state['runners'][0]
    e.step(batches(e,'home',[throw('home.P03')]))
    # A legal touch occurring while the ball is still held must change the award origin.
    r.update(last_legal_base=2,has_first=True,force_obligation=None)
    e.player(r['id'])['position_q']=e.config['field']['bases_q'][2][:]
    for _ in range(e.config['rules']['throw_windup_ticks']):e.step()
    assert next(x['base'] for x in e.state['throw_start_bases'] if x['id']==r['id'])==2
