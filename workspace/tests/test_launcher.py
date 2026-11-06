"""The launcher transport must not change rules, scheduling or record contents."""
import json
import os
from pathlib import Path
import subprocess
from match import run_match
from test_p2 import quick_config

ROOT=Path(__file__).resolve().parents[2]


def test_progress_is_optional_and_does_not_change_match_or_txt(tmp_path):
    away=ROOT/"bots/examples/minimal.py";home=ROOT/"bots/examples/minimal.py"
    plain=run_match(away,home,quick_config(),"42",tmp_path/"plain")
    updates=[]
    observed=run_match(away,home,quick_config(),"42",tmp_path/"progress",progress=updates.append)
    assert observed==plain
    assert (tmp_path/"plain/match.txt").read_bytes()==(tmp_path/"progress/match.txt").read_bytes()
    assert updates and all(x["type"]=="progress" and x["sim_tick"]%600==0 for x in updates)
    assert [x["sim_tick"] for x in updates]==sorted(x["sim_tick"] for x in updates)
    assert all(set(x["score"])=={"away","home"} for x in updates)


def test_launcher_batch_bootstraps_from_its_own_location(tmp_path):
    # This flag runs the real BAT/bootstrap without showing a window.
    batch=ROOT/"launcher/啟動遊戲.bat"
    process=subprocess.run([os.environ.get("COMSPEC","cmd.exe"),"/d","/c",str(batch),"--check"],
        cwd=tmp_path,capture_output=True,text=True,encoding="utf-8",errors="replace",timeout=180,
        creationflags=subprocess.CREATE_NO_WINDOW)
    assert process.returncode==0,(process.stdout,process.stderr)
    binary=Path(process.stdout.strip())
    assert binary.is_file() and binary.parent==ROOT/"launcher/build" and binary.suffix==".exe"
