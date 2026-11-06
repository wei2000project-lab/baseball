"""P4 external process, real Job memory limit, protocol and failure cases."""
import json
from pathlib import Path
import time
import pytest
from bot_host import BotHost,BotFault
from match import run_match
from recording import decision_record,advance_recorded
from test_p2 import quick_config
from test_p3 import batted_engine,holder,batches

ROOT=Path(__file__).resolve().parents[2]


def make_bot(tmp_path,behavior):
    path=tmp_path/"bot.py"
    path.write_text('import json,sys,time\nfor line in sys.stdin:\n m=json.loads(line)\n if m["type"]=="shutdown":break\n if m["type"]=="init":\n  print(json.dumps({"type":"ready","protocol_version":"1.0.0"}),flush=True)\n else:\n'+''.join('  '+line+'\n' for line in behavior.splitlines()),encoding="utf-8")
    return path


def observe(host):host.send({"type":"observe","decision_id":"d1","state":{}})


def test_external_replacement_and_effective_job_memory_limit(tmp_path):
    path=make_bot(tmp_path,'try:\n b=bytearray(300*1024*1024)\n raise AssertionError("memory limit ineffective")\nexcept MemoryError:\n print("memory_limit_enforced",file=sys.stderr,flush=True)\nprint(json.dumps({"type":"action","protocol_version":"1.0.0","decision_id":m["decision_id"],"actions":[]}),flush=True)')
    host=BotHost(path,"away",42,tmp_path/"diagnostics")
    try:
        assert host.capability["memory_limit_bytes"]==268435456
        observe(host);actions,raw,error=host.receive("d1")
        assert actions==[] and error is None
    finally:host.close()
    assert "memory_limit_enforced" in host.stderr_path.read_text()


@pytest.mark.parametrize("behavior,reason",[
    ('print("x"*70000,flush=True)',"output_line_limit"),
    ('time.sleep(3)',"watchdog_timeout"),
    ('sys.exit(3)',"process_exited"),
])
def test_host_faults_fail_explicitly(tmp_path,behavior,reason):
    path=make_bot(tmp_path,behavior);host=BotHost(path,"away",42,tmp_path/"diagnostics",timeout=.7)
    try:
        observe(host)
        with pytest.raises(BotFault,match=reason):host.receive("d1")
    finally:host.close()


@pytest.mark.parametrize("behavior,error",[
    ('print(json.dumps({"type":"action","protocol_version":"1.0.0","decision_id":"old","actions":[]}),flush=True)',"stale_decision_id"),
    ('print(\'{"type":"action","actions":NaN}\',flush=True)',"non_finite"),
])
def test_malformed_or_stale_reply_rejected_without_strategy(tmp_path,behavior,error):
    host=BotHost(make_bot(tmp_path,behavior),"home",42,tmp_path/"diagnostics")
    try:
        observe(host);actions,raw,parse=host.receive("d1")
        assert actions is None and error in parse and raw
    finally:host.close()


def test_match_crash_archives_aborted_and_terminal_checkpoint(tmp_path):
    path=make_bot(tmp_path,'sys.exit(3)')
    summary=run_match(path,ROOT/"bots/examples/minimal.py",quick_config(),"7",tmp_path/"result")
    assert summary["status"]=="aborted" and summary["winner"] is None
    manifest=json.loads((tmp_path/"result/manifest.json").read_text())
    assert manifest["record_status"]=="aborted" and manifest["file_index"]
    cps=[json.loads(x) for x in (tmp_path/"result/checkpoints.jsonl").read_text().splitlines()]
    assert cps[-1]["state_hash"]==summary["final_state_hash"]
    assert any(json.loads(x)["fault"] for x in (tmp_path/"result/actions.jsonl").read_text().splitlines())


def test_thrower_does_not_recatch_own_ball_at_release():
    e=batted_engine();holder(e,base=2);p=e.player("home.P03");p["active_intents"]["catch"]=True
    throw={"action_id":"throw-regression","player_id":p["id"],"kind":"throw","direction_i32":[0,-1000000,0],"power_u16":65535}
    events=e.step(batches(e,"home",[throw]))["events"]
    assert e.state["ball"]["holder_id"] is None
    assert not any(x["type"]=="BallCaught" and x["payload"]["fielder_id"]==p["id"] for x in events)


def test_public_observation_hides_engine_rng():
    e=batted_engine()
    assert "rng_stream_states" not in e.observe("away")
    assert "rng_stream_states" in e.snapshot()


def test_python_vs_javascript_passive_bots_complete_without_engine_changes(tmp_path):
    result=run_match(ROOT/"bots/examples/minimal.py",ROOT/"bots/examples/node_passive",quick_config(),"9",tmp_path/"replacement")
    assert result["status"]=="completed" and result["score"]=={"away":10,"home":10}
    assert result["completed_halves"]=={"away":1,"home":1}
