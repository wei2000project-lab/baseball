import copy
import json
import math
from pathlib import Path
import pytest
from configuration import default_config,validate_config,VERSION
from native import Native
from numeric import q,ONE,digest
from test_p2 import pitch_scene,ready_engine
from test_p3 import batted_engine,batches


def contact(power=65535,tick=6,x="0",z=".875"):
    c=default_config();action=dict(power_u16=power,azimuth_mdeg=0,elevation_mdeg=38000)
    v,quality=Native().contact(action,[q(x),q('.75'),q(z)],int(tick*ONE),12*ONE,c)
    return v,int(quality)


def test_contact_center_timing_and_location_have_real_costs():
    best,bq=contact();late,lq=contact(tick=8);edge,eq=contact(x='.5');high,hq=contact(z='1.4')
    length=lambda v:math.isqrt(sum(int(a)**2 for a in v))
    assert bq==ONE and lq<bq and eq<bq and hq<bq
    assert length(best)<=int(q(35)) and all(length(v)<length(best) for v in (late,edge,high))
    assert late[0]!=best[0] and edge[0]!=best[0] and high[2]!=best[2]
    assert contact(tick=8)==contact(tick=8)


def test_power_narrows_sweet_spot_and_full_power_can_be_worse():
    assert contact(65535,8)[1]<contact(30000,8)[1]
    length=lambda v:math.isqrt(sum(int(a)**2 for a in v))
    assert length(contact(65535,3)[0])<length(contact(60000,3)[0])
    assert default_config()['rules']['decision_interval_ticks']==1


def test_dive_reaches_extra_ball_and_cannot_spam_or_reset_by_pa():
    e=batted_engine();p=e.player('home.P03');s=e.state
    action=dict(action_id='dive1',player_id=p['id'],kind='dive')
    assert e.validate_intents('home',[action])['accepted_intents']
    e._apply(action)
    assert e.validate_intents('home',[dict(action,action_id='dive2')])['accepted_intents']==[]
    skill=e.native.field_skill(0,['0','0'],['0','0','0'],e.config['physics'],True)
    radius=int(e.config['physics']['catch_radius_q'])
    assert skill[0]>radius and p['dive_ready_tick']>p['dive_until_tick']
    ready=p['dive_ready_tick'];e._start_pa();assert p['dive_ready_tick']==ready
    assert e.native.sweep_cylinder([q('1.5'),'0',q(1)],[q('1.5'),'0',q(1)],['0']*3,['0']*3,str(skill[0]),q('2.5'))>=0
    assert e.native.sweep_cylinder([q('1.5'),'0',q(1)],[q('1.5'),'0',q(1)],['0']*3,['0']*3,str(radius),q('2.5'))<0


def test_running_catch_error_and_throw_error_are_deterministic():
    n=Native();p=default_config()['physics'];ball=[q(-35),'0','0'];still=n.field_skill(0,['0','0'],ball,p)
    running=n.field_skill(0,[q(9),'0'],ball,p)
    assert still[1] and not running[1] and running[0]<still[0]
    throw=['0',q(40),'0']
    assert n.field_skill(1,['0','0'],throw,p)==throw
    moving=n.field_skill(1,[q(9),'0'],throw,p)
    assert int(moving[0])>0 and moving==n.field_skill(1,[q(9),'0'],throw,p)
    assert math.isqrt(sum(int(x)**2 for x in moving))<=int(q(40))
    e=batted_engine();f=e.player('home.P03');f['velocity_q']=[q(9),'0']
    e.state['ball']['velocity_q']=ball;e._sub=0
    assert e._caught(f['id'],0) is False
    assert e.events[-1]['type']=='FieldingError' and f['catch_ready_tick']>e.state['sim_tick']
    assert e.state['ball']['holder_id'] is None


def test_pitch_error_envelope_increases_quadratically_with_speed():
    n=Native();p=default_config()['physics'];errors=[]
    for power in (0,32768,65535):
        _,v=n.action('pitch',dict(power_u16=power,direction_i32=[0,-1000000,47000]),p)
        actual,error=n.pitch_scatter(v,q('18.44'),1,p);errors.append(int(error[2]))
        assert n.pitch_scatter(v,q('18.44'),1,p)==(actual,error)
    assert errors[0]<errors[1]<errors[2]
    assert errors[2]<=int(p['pitch_max_error_q'])


def test_new_versions_and_old_records_are_explicitly_unsupported():
    c=default_config();assert c['version']==c['physics']['version']==c['field']['version']==VERSION=='2.0.0'
    for group in (None,'physics','field'):
        old=copy.deepcopy(c);(old if group is None else old[group])['version']='1.0.0-dev.P7'
        with pytest.raises(ValueError,match='unsupported_version'):validate_config(old)


def test_throw_cannot_be_recaught_by_reenabling_catch_next_tick():
    from test_p3 import holder
    e=batted_engine();holder(e,base=2);p=e.player('home.P03')
    action=dict(action_id='release',player_id=p['id'],kind='throw',direction_i32=[0,-1000000,0],power_u16=65535)
    e.step(batches(e,'home',[action]))
    assert e.state['ball']['release_exclusion_id']==p['id']
    for tick in range(4):
        catch=dict(action_id='catch'+str(tick),player_id=p['id'],kind='catch',enabled=True)
        events=e.step(batches(e,'home',[catch]))['events']
        assert not any(x['type']=='BallCaught' and x['payload']['fielder_id']==p['id'] for x in events)


def test_balance_contact_and_skill_golden():
    n=Native();c=default_config();values=[]
    for power in (20000,45000,65535):
        for timing in (2,4,6,8):values.append(list(contact(power,timing)))
    expected=json.loads((Path(__file__).parent/'golden/balance-v2.json').read_text())
    assert expected['physics_version']==c['physics']['version']
    assert expected['config_hash']==digest(c)
    assert digest(values)==expected['contact_trace_sha256']
    skills=[];p=c['physics']
    for speed in (0,4,9):
        for ball in ([q(-35),'0','0'],['0',q(40),'0']):
            skills.append(n.field_skill(0,[q(speed),'0'],ball,p));skills.append(n.field_skill(1,[q(speed),'0'],ball,p))
    assert digest(skills)==expected['skill_trace_sha256']
    pitches=[]
    for power in (0,32768,65535):
        _,v=n.action('pitch',dict(power_u16=power,direction_i32=[0,-1000000,47000]),p)
        for phase in range(1,7):pitches.append(list(n.pitch_scatter(v,q('18.44'),phase,p)))
    assert digest(pitches)==expected['pitch_trace_sha256']
    roll=[];position=['0',q(10),q('.037')];velocity=[q(12),'0','0']
    for _ in range(400):
        parts=n.trace(position,velocity,c,rolling=True);roll+=parts
        position,velocity=parts[-1]['position_q'],parts[-1]['velocity_q']
    assert digest(roll)==expected['rolling_trace_sha256']
    movement=[];position=['0',q(20)];velocity=['0','0']
    for _ in range(600):
        result=n.move(position,velocity,[q(10),q(50)],p,q('.001'),field=c['field']);movement.append(result)
        position,velocity=result['position_q'],result['velocity_q']
    assert digest(movement)==expected['fielder_trace_sha256']
