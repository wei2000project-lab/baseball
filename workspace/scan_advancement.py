"""Fixed-seed multi-parameter search, resumable reports, untouched production Bots."""
import argparse
from concurrent.futures import ProcessPoolExecutor,as_completed
import copy
import hashlib
import itertools
import inspect
import json
import os
from pathlib import Path
import random
import time
from balance_batch import simulation_job,simulate,report
from configuration import default_config
from numeric import q
from recording import source_hash

ROOT=Path(__file__).resolve().parent
TARGETS={"runs_per_half":(1,3),"runner_advance_rate":(.35,.50),
         "outfield_extra_base_rate":(.55,.65),"double_play_rate":(0,.10)}


def source_inputs():
    return dict(engine=source_hash(),native=source_hash(True),
        controller=hashlib.sha256((ROOT/'experiments/advance_controller.py').read_bytes()).hexdigest(),
        metrics=hashlib.sha256((ROOT/'advancement_metrics.py').read_bytes()).hexdigest(),
        baseline_bot=hashlib.sha256((ROOT.parent/'bots/base_bot/bot.py').read_bytes()).hexdigest(),
        simulation_harness=hashlib.sha256('\n'.join(inspect.getsource(f).rstrip() for f in (simulate,simulation_job)).encode()).hexdigest(),targets=TARGETS)


def checks(r):
    return {k:r["metrics"].get(k) is not None and low<=r["metrics"][k]<=high for k,(low,high) in TARGETS.items()}


def loss(r):
    if r["completed"]!=r["n"]:return 10000
    value=0
    for k,(low,high) in TARGETS.items():
        x=r["metrics"].get(k)
        if x is None:value+=100;continue
        value+=max(low-x,0,x-high)/(high-low)+.03*abs(x-(low+high)/2)/(high-low)
    return value


def save(path,value):
    path.parent.mkdir(parents=True,exist_ok=True);temp=path.with_suffix('.tmp')
    temp.write_text(json.dumps(value,indent=2,allow_nan=False)+'\n',encoding='utf-8');os.replace(temp,path)


def candidates(count):
    # These ranges are declared before any candidate runs. No outcome-based Bot changes.
    names=('catch_recovery_ticks','throw_windup_ticks','runner_speed','fielder_speed','fielder_acceleration','catch_radius','throw_speed')
    grid=list(itertools.product((30,36,42),(24,27,30),(8,8.25,8.5),(8,8.25,8.5),(12,14),(.8,.9,.95),(26,28)))
    random.Random(20261107).shuffle(grid)
    return [dict(zip(names,row)) for row in grid[:count]]


def config_for(params):
    c=default_config();c['rules'].update(regulation_ticks=1200,catch_recovery_ticks=params['catch_recovery_ticks'],throw_windup_ticks=params['throw_windup_ticks'])
    c['physics'].update(player_speed_q=q(params['runner_speed']),fielder_speed_q=q(params['fielder_speed']),
        fielder_acceleration_q=q(params['fielder_acceleration']),catch_radius_q=q(params['catch_radius']),
        throw_max_speed_q=q(params['throw_speed']),held_speed_multiplier_q=q('.8'),dive_radius_bonus_q=q('.8'),catch_control_speed_q=q(44))
    return c


def evaluate(pool,items,seeds,stage,directory,identity,inputs):
    reports={};jobs={};games={}
    for cid,params in items:
        config=config_for(params);path=directory/cid/(stage+'.json')
        if path.exists():
            r=json.loads(path.read_text(encoding='utf-8'))
            if r.get('search_identity')==identity and r['seeds']==list(seeds) and r['config']==config:
                reports[cid]=r;continue
        games[cid]=[]
        for seed in seeds:jobs[pool.submit(simulation_job,(seed,config,'advancement'))]=(cid,params,config)
    for future in as_completed(jobs):
        cid,params,config=jobs[future]
        try:game=future.result()
        except Exception as error:raise RuntimeError(f'{stage}/{cid}: {error}') from error
        games[cid].append(game)
        if len(games[cid])==len(seeds):
            r=report(sorted(games[cid],key=lambda g:g['seed']),config,f'{stage}-{cid}')
            r.update(parameters=params,controller='advancement',search_identity=identity,targets=TARGETS,
                     source_inputs=inputs,target_checks=checks(r),loss=loss(r))
            save(directory/cid/(stage+'.json'),r);reports[cid]=r
            print(json.dumps(dict(stage=stage,candidate=cid,metrics=r['metrics'],passed=all(checks(r).values())),ensure_ascii=True),flush=True)
    return reports


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',default=str(ROOT/'balance_reports/advancement-scan'))
    parser.add_argument('--candidates',type=int,default=32);parser.add_argument('--screen-games',type=int,default=6)
    parser.add_argument('--finalists',type=int,default=6);parser.add_argument('--workers',type=int,default=3)
    parser.add_argument('--apply',action='store_true',help='Write selected validated config after the entire search; never modify Bot policy')
    args=parser.parse_args();directory=Path(args.output);directory.mkdir(parents=True,exist_ok=True)
    if min(args.candidates,args.screen_games,args.finalists,args.workers)<1:parser.error('counts/workers must be positive')
    inputs=source_inputs();identity=hashlib.sha256(json.dumps(inputs,sort_keys=True).encode()).hexdigest()
    options=[(f'c{i:03}',p) for i,p in enumerate(candidates(args.candidates))]
    manifest=dict(search_identity=identity,source_inputs=inputs,candidates=dict(options),screen_seeds=list(range(args.screen_games)),
        validation_seeds=list(range(20)),holdout_seeds=list(range(20,40)),targets=TARGETS,
        policy='One frozen test controller; all completed games counted; null denominators fail; production Bots unchanged')
    save(directory/'manifest.json',manifest);started=time.perf_counter()
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        screen=evaluate(pool,options,range(args.screen_games),'screen',directory,identity,inputs)
        ids=sorted(screen,key=lambda cid:(loss(screen[cid]),cid))[:args.finalists]
        validation=evaluate(pool,[(cid,dict(options)[cid]) for cid in ids],range(20),'validation',directory,identity,inputs)
        finalists=sorted(validation,key=lambda cid:(loss(validation[cid]),cid))[:3]
        holdout=evaluate(pool,[(cid,dict(options)[cid]) for cid in finalists],range(20,40),'holdout',directory,identity,inputs)
    combined={}
    for cid in finalists:
        r=report(validation[cid]['games']+holdout[cid]['games'],validation[cid]['config'],'combined-'+cid)
        r.update(parameters=dict(options)[cid],controller='advancement',search_identity=identity,
                 source_inputs=inputs,targets=TARGETS,target_checks=checks(r),loss=loss(r),
                 validation_checks=checks(validation[cid]),holdout_checks=checks(holdout[cid]))
        save(directory/cid/'combined.json',r);combined[cid]=r
    winners=[cid for cid,r in combined.items() if r['completed']==40 and all(checks(r).values())]
    winners.sort(key=lambda cid:(loss(combined[cid]),cid))
    selected=winners[0] if winners else None
    summary=dict(**manifest,selected=selected,winners=winners,screen_ranking=sorted(screen,key=lambda cid:loss(screen[cid])),
                 finalists=finalists,combined={cid:dict(metrics=r['metrics'],target_checks=r['target_checks']) for cid,r in combined.items()},
                 wall_seconds=round(time.perf_counter()-started,3))
    save(directory/'summary.json',summary)
    if args.apply and selected:
        config=copy.deepcopy(combined[selected]['config']);config['rules']['regulation_ticks']=108000
        save(ROOT/'config/default.json',config)
    print(json.dumps(dict(selected=selected,winners=winners,report=str(directory/'summary.json'))))
    return 0 if selected else 2


if __name__=='__main__':raise SystemExit(main())
