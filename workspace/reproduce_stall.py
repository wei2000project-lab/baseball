"""Capture an unresolved live-play snapshot without waiting for max_ticks.

This is a bounded diagnostic run, not a new game rule or a completed match.
"""
import argparse
import json
from pathlib import Path
import time
from unittest.mock import patch
from match import run_match
from configuration import default_config
from recording import Recorder,source_hash


class CaptureFinished(Exception):pass


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--away',default='bots/base_bot');p.add_argument('--home',default='bots/GPT_tactical_cpp')
    p.add_argument('--seed',default='42');p.add_argument('--output',required=True);p.add_argument('--report',required=True)
    p.add_argument('--idle-ticks',type=int,default=600);p.add_argument('--max-ticks',type=int,default=20000)
    args=p.parse_args()
    if min(args.idle_ticks,args.max_ticks)<1:p.error('diagnostic budgets must be positive')
    config=default_config();config['rules']['regulation_ticks']=1200
    original=Recorder.write_step;idle=0;captured=None;started=time.perf_counter()
    def watch(recorder,engine,result,decisions=()):
        nonlocal idle,captured
        previous=recorder.previous
        original(recorder,engine,result,decisions)
        idle=idle+1 if engine.state['phase']=='BALL_IN_PLAY' and recorder.previous==previous else 0
        if idle>=args.idle_ticks or engine.state['sim_tick']>=args.max_ticks:
            captured=dict(capture_only=True,formal_outcome=None,
                reason='unchanged_live_play' if idle>=args.idle_ticks else 'diagnostic_tick_budget',
                unchanged_ticks=idle,config=engine.config,seed=args.seed,away=args.away,home=args.home,
                engine_source_sha256=source_hash(),bots=recorder.manifest['bots'],
                state_hash=engine.canonical_state_hash(),state=engine.snapshot())
            raise CaptureFinished()
    with patch.object(Recorder,'write_step',watch):
        try:summary=run_match(args.away,args.home,config,args.seed,args.output)
        except CaptureFinished:summary=None
    report=captured or dict(capture_only=True,reason='match_ended_without_capture',summary=summary)
    report['wall_seconds']=round(time.perf_counter()-started,3)
    report['record_note']='Diagnostic stop leaves match.txt incomplete; do not count it as completed or a win.'
    target=Path(args.report);target.parent.mkdir(parents=True,exist_ok=True)
    target.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8',newline='\n')
    print(json.dumps(dict(reason=report['reason'],sim_tick=report.get('state',{}).get('sim_tick'),report=str(target))))
    return 0 if captured and captured['reason']=='unchanged_live_play' else 2


if __name__=='__main__':raise SystemExit(main())
