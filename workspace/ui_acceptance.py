"""P6 real renderer acceptance in an invisible, isolated Electron window.

No desktop automation, input injection, focus changes or user-window access.
"""
import argparse
import json
from pathlib import Path
import shutil
import subprocess
import sys
import time
from baseball_engine import BaseballEngine
from configuration import default_config
from numeric import digest
from recording import Recorder,decision_record,advance_recorded
from replay import ReplayRecord,file_digest

ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT.parent/'bots/examples'))
from script_controller import strikeout_actions


def malicious_fixture(path):
    config=default_config();config['rules'].update(regulation_ticks=1,plate_appearance_setup_ticks=1,pitch_reset_ticks=1,half_inning_change_ticks=1,pitch_release_deadline_ticks=20,max_ticks=10000)
    e=BaseballEngine(config);rec=Recorder(path,e);seq=1
    action={'action_id':'<svg onload="window.__recordInjection=1">','kind':'noop'}
    r=decision_record(e,'away',[action],seq);rec.write_step(e,advance_recorded(e,[r]),[r])
    while not e.terminal_result():
        records=[]
        for team in ('away','home'):
            actions=strikeout_actions(e.observe(team),team)
            if actions:seq+=1;records.append(decision_record(e,team,actions,seq))
        rec.write_step(e,advance_recorded(e,records),records)
    rec.finalize(e)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input',required=True);parser.add_argument('--report',default=str(ROOT/'tests/reports/p6-ui.json'))
    args=parser.parse_args();source=Path(args.input).resolve();work=ROOT/'build/ui-acceptance'/str(time.time_ns())
    path=work/'record';path.mkdir(parents=True)
    originals={name:file_digest(source/name) for name in ('manifest.json',*Recorder.FILES)}
    for name in originals:shutil.copyfile(source/name,path/name)
    record=ReplayRecord(path);events=[json.loads(line) for line in (path/'events.jsonl').read_text().splitlines()]
    ticks={0,1000,1001,record.final_tick}
    types=('BatContact','GroundContact','BallCaught','HomeRun','RunPending','RunScored','RunnerOut')
    selected={}
    for kind in types:
        e=next((e for e in events if e['type']==kind),None)
        if e: selected[kind]=min(record.final_tick,e['sim_tick']+1);ticks.add(selected[kind])
    preview=min(record.final_tick,selected.get('BatContact',0)+150);ticks.add(preview)
    for e in events:
        if e['type'] in ('PitchReleased','PitchClockViolation','HalfInningStarted'):ticks.add(min(record.final_tick,e['sim_tick']+(e['type']!='HalfInningStarted')))
    expected={}
    for tick in sorted(ticks):
        s=record.seek(tick);expected[str(tick)]={'state_hash':digest(s),'score':s['score'],'outs':s['outs'],'balls':s['balls'],'strikes':s['strikes'],'height_m':round(int(s['ball']['position_q'][2])/(1<<32),2),'phase':s['phase']}
    xss=work/'audit-text';malicious_fixture(xss)
    data={'record':str(path),'audit_record':str(xss),'expected':expected,'selected':selected,'preview_tick':preview,'screenshot':str(work/'overview.png'),'report':str(Path(args.report).resolve()),'source':str(source)}
    config=work/'test.json';config.write_text(json.dumps(data,ensure_ascii=False),encoding='utf-8')
    result=subprocess.run([sys.executable,str(ROOT/'viewer.py'),'--background-test','--acceptance-config',str(config)],cwd=ROOT.parent,timeout=180)
    for name,h in originals.items():
        if file_digest(source/name)!=h:raise RuntimeError('acceptance changed source record: '+name)
    report=Path(args.report)
    if report.exists():
        data=json.loads(report.read_text(encoding='utf-8'))
        print(json.dumps({'passed':data['passed'],'checks':len(data['checks']),'source_record_unchanged':True,'error':data.get('error')},ensure_ascii=True),flush=True)
    raise SystemExit(result.returncode)


if __name__=='__main__':main()
