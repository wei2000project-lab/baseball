"""Measure real external-Bot matches and require identical TXT/results."""
import argparse
import hashlib
import json
from pathlib import Path
import statistics
import sys
import time
from configuration import default_config
from match import run_match
from recording import source_hash


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--away',default='bots/base_bot');p.add_argument('--home',default='bots/base_bot')
    p.add_argument('--seed',default='42');p.add_argument('--regulation-ticks',type=int,default=1200)
    p.add_argument('--n',type=int,default=3);p.add_argument('--output',required=True);p.add_argument('--report',required=True)
    p.add_argument('--reference',help='Earlier match.txt or match directory; require byte-identical output')
    args=p.parse_args()
    if args.n<1:p.error('--n must be positive')
    root=Path(__file__).resolve().parent;output=Path(args.output);output.mkdir(parents=True,exist_ok=False)
    expected=None
    if args.reference:
        ref=Path(args.reference);ref=ref/'match.txt' if ref.is_dir() else ref
        expected=hashlib.sha256(ref.read_bytes()).hexdigest()
    config=default_config();config['rules']['regulation_ticks']=args.regulation_ticks
    result=dict(config=config,seed=args.seed,away=args.away,home=args.home,python=sys.version,
        source_fingerprints=dict(engine=source_hash(),native=source_hash(True),
            **{name:hashlib.sha256((root/name).read_bytes()).hexdigest() for name in ('match.py','bot_host.py')}),
        reference_sha256=expected,runs=[])
    for i in range(args.n):
        path=output/f'run-{i:02}';start=time.perf_counter()
        summary=run_match(args.away,args.home,config,args.seed,path)
        elapsed=time.perf_counter()-start
        signature=hashlib.sha256((path/'match.txt').read_bytes()).hexdigest()
        if expected is None:expected=signature
        if summary['status']!='completed' or signature!=expected:
            raise RuntimeError(f'benchmark_result_mismatch: {path}: {summary}')
        result['runs'].append(dict(seconds=round(elapsed,6),txt_sha256=signature,summary=summary))
        print(f'run {i+1}/{args.n}: {elapsed:.3f}s, {summary["sim_tick"]} ticks, identical TXT',flush=True)
    seconds=[r['seconds'] for r in result['runs']]
    result.update(median_seconds=statistics.median(seconds),mean_seconds=statistics.mean(seconds),
        ticks_per_second=result['runs'][0]['summary']['sim_tick']/statistics.median(seconds),all_identical=True)
    report=Path(args.report);report.parent.mkdir(parents=True,exist_ok=True)
    report.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8',newline='\n')
    print(json.dumps(dict(median_seconds=result['median_seconds'],ticks_per_second=result['ticks_per_second'],report=str(report))))


if __name__=='__main__':main()
