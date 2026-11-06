"""Real C++ compilation, JSONL exchange, full observations and engine control."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import pytest
from bot_host import BotHost, bot_command
from build_bot import build_cpp_bot
from match import run_match, legal_types
from numeric import ONE
from replay import ReplayRecord
from test_p2 import quick_config, ready_engine

ROOT = Path(__file__).resolve().parents[2]
PASSIVE = ROOT / "bots/examples/cpp_passive"


def test_cpp_folder_source_and_executable_entrypoints(tmp_path):
    folder, cwd, signature = bot_command(PASSIVE)
    direct, direct_cwd, direct_signature = bot_command(PASSIVE / "bot.cpp")
    assert folder == direct and cwd == direct_cwd == PASSIVE
    assert signature == direct_signature and len(signature) == 64
    command, directory, _ = bot_command(folder[0])
    assert command == folder and directory == Path(folder[0]).parent
    (tmp_path / "bot.json").write_text(json.dumps({"command": [str(PASSIVE / "bot.cpp")]}))
    described, directory, _ = bot_command(tmp_path)
    assert described == folder and directory == tmp_path
    host = BotHost(folder[0], "away", 42, ROOT / "workspace/build/cpp-exe-diagnostics")
    host.close()


def test_cpp_cache_tracks_local_headers_and_preserves_loaded_builds(tmp_path):
    source = tmp_path / "bot.cpp";header = tmp_path / "settings.hpp"
    source.write_text('#include "settings.hpp"\nint main(){return VALUE;}\n')
    header.write_text('#define VALUE 11\n')
    first = build_cpp_bot(source)
    assert build_cpp_bot(source) == first
    old_bytes = first.read_bytes()
    options = dict(creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
    assert subprocess.run([str(first)], **options).returncode == 11
    header.write_text('#define VALUE 22\n')
    second = build_cpp_bot(source)
    assert second != first and first.read_bytes() == old_bytes
    assert subprocess.run([str(second)], **options).returncode == 22


def test_cpp_compile_failure_is_explicit_and_has_diagnostic(tmp_path):
    source = tmp_path / "bot.cpp";source.write_text('int main( this is not C++ );\n')
    with pytest.raises(RuntimeError, match="cpp_bot_compile_failed: see") as error:
        build_cpp_bot(source)
    log = Path(str(error.value).split(": see ", 1)[1])
    assert log.is_file() and "error" in log.read_text(encoding="utf-8").lower()


def test_descriptor_precedes_cpp_and_missing_entry_fails(tmp_path):
    (tmp_path / "bot.cpp").write_text('invalid C++ must not be compiled')
    (tmp_path / "bot.py").write_text('')
    (tmp_path / "bot.json").write_text(json.dumps({"command": ["python", "bot.py"]}))
    command, cwd, _ = bot_command(tmp_path)
    assert command == [sys.executable, "bot.py"] and cwd == tmp_path
    empty = tmp_path / "empty";empty.mkdir()
    with pytest.raises(ValueError, match="bot_not_found"):bot_command(empty)


def test_cpp_reads_every_player_and_controls_its_own_id(tmp_path):
    source = tmp_path / "bot.cpp"
    (tmp_path / "marker.txt").write_text("source-folder-cwd")
    source.write_text(r'''
#include <nlohmann/json.hpp>
#include <fstream>
#include <iostream>
#include <string>
using J = nlohmann::json;
int main(){
 std::string line,team,seed;
 while(std::getline(std::cin,line)){
  J m=J::parse(line),reply;
  if(m.at("type")=="shutdown")break;
  if(m.at("type")=="init"){
   team=m.at("team_id");seed=m.at("seed");
   reply={{"type","ready"},{"protocol_version","1.0.0"}};
  }else{
   const J& s=m.at("state");std::string marker;std::ifstream("marker.txt")>>marker;
   std::cerr<<J({{"players",s.at("players")},{"ball",s.at("ball")},
    {"private_rng",s.contains("rng_stream_states")},{"seed",seed},{"cwd_marker",marker}}).dump()<<std::endl;
   J actions=J::array();
   for(const auto& p:s.at("players"))if(p.at("id")==team+".P03"){
    std::string x=std::to_string(std::stoll(p.at("position_q").at(0).get<std::string>())+4294967296LL);
    actions.push_back({{"action_id","fixture-move"},{"player_id",p.at("id")},{"kind","move"},
     {"target_q",J::array({x,p.at("position_q").at(1)})},{"catch_enabled",true}});
   }
   reply={{"type","action"},{"protocol_version","1.0.0"},{"decision_id",m.at("decision_id")},{"actions",actions}};
  }
  std::cout<<reply.dump()<<std::endl;
 }
}
''', encoding="utf-8")
    e = ready_engine();state = e.observe("home")
    host = BotHost(source, "home", (1 << 64) - 1, tmp_path / "diagnostics")
    try:
        assert host.capability["memory_limit_bytes"] == 256 * 1024 * 1024
        host.send(dict(type="observe", protocol_version="1.0.0", decision_id="cpp-9", sim_tick=state["sim_tick"],
                       team_id="home", state=state, legal_action_types=legal_types(e, "home")))
        actions, _, error = host.receive("cpp-9")
        assert error is None and actions[0]["player_id"] == "home.P03"
        batch = e.validate_intents("home", actions)
        assert batch["accepted_intents"] == actions
        before = int(e.player("home.P03")["position_q"][0])
        e.step([batch])
        assert before < int(e.player("home.P03")["position_q"][0]) < before + ONE
        updated = e.observe("home")
        host.send(dict(type="observe", protocol_version="1.0.0", decision_id="cpp-10", sim_tick=updated["sim_tick"],
                       team_id="home", state=updated, legal_action_types=legal_types(e, "home")))
        next_actions, _, error = host.receive("cpp-10")
        assert error is None
        assert int(next_actions[0]["target_q"][0]) == int(e.player("home.P03")["position_q"][0]) + ONE
    finally:host.close()
    packet, next_packet = map(json.loads, host.stderr_path.read_text(encoding="utf-8").splitlines())
    assert packet["players"] == state["players"] and len(packet["players"]) == 18
    assert {p["id"] for p in packet["players"]} == {f"{t}.P{i:02}" for t in ("away", "home") for i in range(1, 10)}
    assert packet["ball"] == state["ball"] and packet["private_rng"] is False
    assert packet["seed"] == str((1 << 64) - 1) and packet["cwd_marker"] == "source-folder-cwd"
    assert next_packet["players"] == updated["players"] and next_packet["players"] != packet["players"]


@pytest.mark.parametrize("opponent", [PASSIVE, ROOT / "bots/examples/minimal.py"])
def test_cpp_bot_completes_match_with_cpp_or_python(opponent, tmp_path):
    result = run_match(PASSIVE, opponent, quick_config(), "42", tmp_path / "match")
    assert result["status"] == "completed" and result["completed_halves"] == {"away": 1, "home": 1}
    assert result["score"] == {"away": 10, "home": 10}
    record = ReplayRecord(tmp_path / "match")
    assert record.verify()["verification_status"] == "verified_record"
    assert record.summary == result


def test_vendored_json_matches_pinned_upstream_release():
    header = ROOT / "bots/vendor/nlohmann/json.hpp"
    assert hashlib.sha256(header.read_bytes()).hexdigest() == "9bea4c8066ef4a1c206b2be5a36302f8926f7fdc6087af5d20b417d0cf103ea6"
    assert "MIT License" in (header.parent / "LICENSE.MIT").read_text(encoding="utf-8")
