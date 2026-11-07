"""Optimized copies/transport must preserve every public byte and fault rollback."""
import copy
import io
from pathlib import Path
from types import SimpleNamespace
import pytest
from bot_host import BotHost
from numeric import canonical,clone_json,digest
from recording import decision_record
from test_p3 import batted_engine


def test_json_tree_copy_preserves_values_and_nested_isolation():
    value={'nested':[{'big':(1<<64)-1,'q':'18446744073709551616','flags':[None,True,False]}],'text':'e\u0301'}
    cloned=clone_json(value)
    assert cloned==copy.deepcopy(value) and canonical(cloned)==canonical(value)
    cloned['nested'][0]['flags'].append('changed')
    assert value['nested'][0]['flags']==[None,True,False]
    e=batted_engine();snapshot=e.snapshot();signature=e.canonical_state_hash()
    snapshot['players'][0]['active_intents']['move']=['1','2']
    snapshot['rng_stream_states']['engine'][0]='0'
    assert e.canonical_state_hash()==signature
    restored=e.snapshot();e.restore(restored)
    restored['score']['away']=999
    assert e.canonical_state_hash()==signature


@pytest.mark.parametrize('team',['away','home'])
def test_shared_observation_wire_is_byte_identical_to_original_envelope(team):
    e=batted_engine();state=e.observe(team)
    assert state==e.observe('home' if team=='away' else 'away')
    assert 'rng_stream_states' not in state
    # Extra JSON values exercise NFC/control escaping and misleading marker text.
    state['fixture']={'text':'e\u0301\n\t"state":null','state':None}
    message=dict(type='observe',protocol_version='1.0.0',decision_id='d1',sim_tick=42,
        team_id=team,state=state,legal_action_types=['move','catch'])
    stream=io.BytesIO();host=BotHost.__new__(BotHost)
    host.team=team;host.error=None;host.process=SimpleNamespace(stdin=stream)
    host.send_observation('d1',42,canonical(state),['move','catch'])
    assert stream.getvalue()==canonical(message)+b'\n'


def test_precomputed_observation_digest_keeps_record_and_avoids_recopy(monkeypatch):
    e=batted_engine();expected=decision_record(e,'away',[],1,'raw')
    shared_hash=digest(e.observe('away'))
    def forbidden(*args):raise AssertionError('duplicated observation')
    monkeypatch.setattr(e,'observe',forbidden)
    assert decision_record(e,'away',[],1,'raw',observation_hash=shared_hash)==expected


def test_match_restores_last_valid_tick_on_midstep_fault(tmp_path,monkeypatch):
    import match
    from test_p2 import quick_config
    from replay import ReplayRecord
    step=match.BaseballEngine.step
    def broken(self,*args,**kw):
        if self.state['sim_tick']==4:
            self.state['score']['away']=999
            self.state['players'][0]['position_q'][0]='999'
            raise RuntimeError('injected_engine_fault')
        return step(self,*args,**kw)
    monkeypatch.setattr(match.BaseballEngine,'step',broken)
    bot=Path(__file__).resolve().parents[2]/'bots/examples/minimal.py'
    result=match.run_match(bot,bot,quick_config(),'42',tmp_path/'fault')
    assert result['status']=='aborted' and result['score']==dict(away=0,home=0)
    assert result['reason']=='engine:injected_engine_fault' and result['sim_tick']==4
    record=ReplayRecord(tmp_path/'fault')
    assert record.verify()['verification_status']=='verified_record'
    assert record.seek(4)['players'][0]['position_q'][0]!='999'
