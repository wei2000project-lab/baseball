import math
from configuration import default_config
from numeric import q,ONE
from native import Native
from test_p2 import ready_engine


def test_fielder_target_does_not_use_runner_instant_stop_exception():
    e=ready_engine();p=e.player('home.P03');target=p['position_q'][:]
    p['position_q']=[str(int(target[0])-int(q('.01'))),target[1]]
    p['velocity_q']=[q(7),'0'];p['active_intents']={'move':target}
    e.step()
    assert int(p['velocity_q'][0])>0
    assert int(q(7))-int(p['velocity_q'][0])<=int(e.config['physics']['fielder_acceleration_q'])//120+2


def test_fielder_brakes_and_converges_at_ordinary_target():
    n=Native();c=default_config();p=[q(0),q(15)];v=['0','0'];goal=[q(7),q(20)]
    for _ in range(1000):
        before=v[:];r=n.move(p,v,goal,c['physics'],q('.001'),field=c['field']);p,v=r['position_q'],r['velocity_q']
        assert math.isqrt(sum((int(x)-int(y))**2 for x,y in zip(v,before)))<=int(c['physics']['fielder_acceleration_q'])//120+3
        if r['stopped']:break
    else:raise AssertionError('fielder failed to converge')
    assert v==['0','0']


def test_fair_wall_clamps_target_and_motion_but_keeps_foul_territory():
    n=Native();c=default_config();f=c['field']
    target=n.clamp_position(['0',q(104)],f)
    assert int(target[1])<=int(q(100))
    assert n.clamp_position([q(84),q(10)],f)==[q(84),q(10)]
    r=n.move(['0',q('99.99')],['0',q(7)],['0',q(104)],c['physics'],q('.001'),field=f)
    assert int(r['position_q'][1])<=int(q(100)) and r['velocity_q']==['0','0']
    assert r['stopped'] and 0<=r['touch_q']<=ONE


def test_P4_map_path_still_uses_original_target_and_stop():
    n=Native();c=default_config();f=dict(c['field'],version='1.0.0-dev.P4')
    assert n.clamp_position(['0',q(104)],f)==['0',q(104)]
    r=n.move([q('6.99'),q(20)],[q(7),'0'],[q(7),q(20)],c['physics'],q('.001'))
    assert r['velocity_q']==['0','0']


def test_initial_fielder_cannot_start_beyond_fair_wall():
    import pytest
    from configuration import validate_config
    c=default_config();c['field']['defense_q'][7]=['0',q(104)]
    with pytest.raises(ValueError,match='beyond_fair_wall'):validate_config(c)


def test_full_bot_message_contract_and_private_rng_exclusion():
    import json
    from pathlib import Path
    import pytest
    from contracts import validate
    e=ready_engine();schema=json.loads((Path(__file__).resolve().parents[2]/'bots/protocol/message.schema.json').read_text(encoding='utf-8'))
    validate({'type':'init','protocol_version':'1.0.0','team_id':'home','seed':'42','capabilities':{'field_config':e.config['field'],'physics_config':e.config['physics'],'rules_config':e.config['rules'],'action_types':['pitch','noop']}},schema)
    message={'type':'observe','protocol_version':'1.0.0','decision_id':'d1','sim_tick':e.state['sim_tick'],'team_id':'home','state':e.observe('home'),'legal_action_types':['pitch','noop']}
    validate(message,schema)
    message['state']['rng_stream_states']=e.state['rng_stream_states']
    with pytest.raises(ValueError):validate(message,schema)


def test_packaged_reference_verifies_without_bot_and_refuses_overwrite(tmp_path):
    import pytest
    from unpack_demo import unpack
    from replay import ReplayRecord
    path=tmp_path/'demo';info=unpack(path)
    result=ReplayRecord(path).verify()
    assert result['verification_status']=='verified_record' and result['summary']==info['summary']
    with pytest.raises(ValueError,match='output_not_empty'):unpack(path)


def test_reference_archive_tampering_and_traversal_fail_before_extraction(tmp_path):
    import hashlib,json,zipfile
    import pytest
    from unpack_demo import unpack
    archive=tmp_path/'bad.zip';metadata=tmp_path/'info.json';out=tmp_path/'out'
    with zipfile.ZipFile(archive,'w') as z:z.writestr('../escape','bad')
    metadata.write_text(json.dumps({'sha256':hashlib.sha256(archive.read_bytes()).hexdigest()}),encoding='utf-8')
    with pytest.raises(ValueError,match='unsafe_demo_entries'):unpack(out,archive,metadata)
    assert not out.exists() and not (tmp_path/'escape').exists()
    archive.write_bytes(archive.read_bytes()+b'changed')
    with pytest.raises(ValueError,match='demo_archive_integrity'):unpack(out,archive,metadata)


def test_future_payload_version_is_unsupported_before_current_schema(tmp_path):
    import json,pytest
    from unpack_demo import unpack
    from replay import ReplayRecord,ReplayError
    path=tmp_path/'future';unpack(path);file=path/'match.txt'
    file.write_bytes(file.read_bytes().replace(b'2.0.0',b'9.0.0'))
    with pytest.raises(ReplayError) as e:ReplayRecord(path)
    assert e.value.report['verification_status']=='unsupported_version'
