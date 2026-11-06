"""V2 replaces P5 simulation checkpoints with lossless TXT deltas."""
import hashlib
import json
from pathlib import Path
import subprocess
import pytest
from baseball_engine import BaseballEngine
from recording import Recorder,decision_record,advance_recorded,atomic_json
from numeric import digest,RNG,strict_loads,stream_seed,q,ONE
from replay import ReplayRecord,ReplayError,file_digest,export_frames,frame
from test_p2 import quick_config,strikeout_actions


def make_record(path,capture=None):
    e=BaseballEngine(quick_config());rec=Recorder(path,e);seq=0
    if capture is not None:capture[0]=frame(e.state)
    while not e.terminal_result():
        records=[]
        for team in ("away","home"):
            actions=strikeout_actions(e.observe(team),team)
            if actions:seq+=1;records.append(decision_record(e,team,actions,seq))
        result=advance_recorded(e,records);rec.write_step(e,result,records)
        if capture is not None:capture[e.state["sim_tick"]]=frame(e.state)
    rec.finalize(e);return path


@pytest.fixture
def record_path(tmp_path):return make_record(tmp_path/"record")


def test_ten_reads_without_bot_or_native_execution(record_path,monkeypatch):
    def forbidden(*a,**k):raise AssertionError("TXT replay started a process or physics")
    from native import Native
    monkeypatch.setattr(subprocess,"Popen",forbidden);monkeypatch.setattr(Native,"__init__",forbidden)
    record=ReplayRecord(record_path);expected=record.verify()
    assert expected["verification_status"]=="verified_record"
    for _ in range(10):assert record.verify()==expected


def test_100_random_seeks_equal_live_engine_frames(tmp_path):
    expected={};path=make_record(tmp_path/"seeks",expected);r=ReplayRecord(path);rng=RNG(2026)
    ticks={0,r.final_tick};ticks.update(rng.next()%(r.final_tick+1) for _ in range(150))
    assert len(ticks)>=100
    for tick in ticks:assert frame(r.seek(tick))==expected[tick]


def test_txt_omits_unchanged_coordinates_and_idle_ticks(record_path):
    lines=(record_path/"match.txt").read_text().splitlines();ticks=[x for x in lines if x.startswith("T\t")]
    assert len(list(record_path.iterdir()))==1
    assert "a9x=" in ticks[0] and not any("a9x=" in x for x in ticks[1:])
    assert len(ticks)<=ReplayRecord(record_path).final_tick+1
    assert not any(x.startswith("E\t") and 'ActionAccepted' in x for x in lines)


def test_tampered_delta_and_event_fail_integrity(record_path):
    p=record_path/"match.txt";original=p.read_bytes()
    for old,new in ((b'scoreA=0',b'scoreA=9'),(b'StrikeCalled',b'StrikeEdited')):
        assert old in original;p.write_bytes(original.replace(old,new,1))
        with pytest.raises(ReplayError,match="file_integrity"):ReplayRecord(record_path)
    p.write_bytes(original)


def test_truncation_is_incomplete_and_unknown_versions_unsupported(record_path,tmp_path):
    p=record_path/"match.txt";original=p.read_bytes();p.write_bytes(original[:-12])
    assert ReplayRecord(record_path).verify()["verification_status"]=="incomplete"
    p.write_bytes(original.replace(b'2.0.0',b'9.0.0',1))
    with pytest.raises(ReplayError) as error:ReplayRecord(record_path)
    assert error.value.report['verification_status']=='unsupported_version'
    legacy=tmp_path/'legacy';legacy.mkdir();(legacy/'manifest.json').write_text('{}')
    with pytest.raises(ReplayError,match='legacy_json_record'):ReplayRecord(legacy)


def test_incomplete_record_does_not_claim_integrity(tmp_path):
    e=BaseballEngine(quick_config());rec=Recorder(tmp_path/"prefix",e)
    for _ in range(200):rec.write_step(e,e.step())
    rec.close();r=ReplayRecord(tmp_path/"prefix")
    assert r.verify()['verification_status']=='incomplete'
    assert 'no physics re-simulation' in r.verify()['verification_scope']


def test_regenerable_cache_and_stale_chunk_rebuild(record_path,tmp_path):
    r=ReplayRecord(record_path);out=tmp_path/'cache';a=export_frames(r,out)
    assert a['verification']['verification_status']=='verified_record'
    assert a['total_frames']>0 and all(c['count']<=600 for c in a['chunks'])
    first=out/'chunk-000000.json';data=first.read_bytes();first.write_bytes(b'broken')
    assert export_frames(r,out)==a and first.read_bytes()==data
    first.unlink();assert export_frames(r,out)==a


def test_rejected_fractions_never_change_authoritative_intents():
    e=BaseballEngine(quick_config());r=decision_record(e,'away',[{'action_id':.5,'kind':'swing','power_u16':.5}],1)
    assert r['accepted_intents']==[] and r['validation_results'][0]['status']=='rejected'


def test_early_swing_whiff_and_legacy_config_rejection():
    from test_p2 import pitch_scene
    from configuration import validate_config
    e=pitch_scene(x='2');e.state['swing_windows'].update(start_tick=0,end_tick=e.state['sim_tick'])
    for _ in range(4):e.step()
    assert (e.state['balls'],e.state['strikes'])==(0,1)
    c=quick_config();c['version']='1.0.0-dev.P4'
    with pytest.raises(ValueError,match='unsupported_version'):validate_config(c)


def test_unicode_boundary_and_contact_vectors():
    with pytest.raises(ValueError):strict_loads('"\\ud800"')
    assert [stream_seed('42',name) for name in ('setup','engine','bot:away')]==[16059173231784216673,6010439204905073236,15716365118942522187]
    from native import Native
    v=lambda *a:[q(x) for x in a]
    assert Native().sweep_cylinder(v(-2,0,1),v(2,0,1),v(0,0,0),v(0,0,0),q(1),q(2))==ONE//4


def test_same_tick_abort_is_preserved(tmp_path):
    e=BaseballEngine(quick_config());rec=Recorder(tmp_path/'aborted',e)
    r=decision_record(e,'away',None,1);r['fault']='watchdog_timeout'
    rec.write_step(e,advance_recorded(e,[r]),[r]);summary=rec.finalize(e)
    record=ReplayRecord(tmp_path/'aborted')
    assert record.final_tick==0 and record.verify()['summary']==summary
    assert record.seek(0)['terminal_status']=='aborted' and summary['winner'] is None


def test_bounded_legal_intent_fuzz_does_not_mutate_observation():
    e=BaseballEngine(quick_config());e.step();rng=RNG(1234);expected=e.canonical_state_hash()
    for i in range(100):
        action={"action_id":f"f{i}","player_id":"home.P01","kind":"pitch","direction_i32":[int(rng.next()%2000001)-1000000 for _ in range(3)],"power_u16":int(rng.next()%100000)-10000}
        try:
            result=e.validate_intents("home",[action]);assert result["accepted_intents"]
            assert 0<=result["accepted_intents"][0]["power_u16"]<=65535 and e.canonical_state_hash()==expected
        except Exception as error:
            path=Path(__file__).resolve().parents[2]/'results'/f'fuzz-seed-1234-case-{i}.json'
            path.parent.mkdir(exist_ok=True)
            atomic_json(path,{'seed':'1234','iteration':i,'config':e.config,'initial_state':e.snapshot(),'intent_batch':[action],'error':str(error)})
            raise


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


def test_entire_idle_tick_is_absent(tmp_path):
    c=quick_config();c['rules']['plate_appearance_setup_ticks']=20
    e=BaseballEngine(c);rec=Recorder(tmp_path/'idle',e)
    for _ in range(10):rec.write_step(e,e.step())
    rec.close();lines=(tmp_path/'idle/match.txt').read_text().splitlines()
    assert len([s for s in lines if s.startswith('T\t')])==2
