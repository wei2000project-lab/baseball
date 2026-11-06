"""Isolate sources/build/output; reuse only explicitly recorded toolchain caches."""
import argparse
import importlib.metadata
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

ROOT=Path(__file__).resolve().parents[1]


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--report',default=str(ROOT/'workspace/tests/reports/v2-cleanroom.json'))
    args=parser.parse_args()
    target=ROOT/'workspace/build/cleanroom'/str(time.time_ns());target.mkdir(parents=True)
    names=subprocess.check_output(['git','-c','core.quotepath=false','ls-files','-z','--cached','--others','--exclude-standard'],cwd=ROOT).decode('utf-8').split('\0')
    for name in filter(None,names):
        relative=Path(name)
        if relative.is_absolute() or '..' in relative.parts:raise ValueError('unsafe_source_path')
        dest=(target/relative).resolve();dest.relative_to(target)
        dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(ROOT/relative,dest)
    commands=[];env=os.environ.copy()
    env['npm_config_cache']=str(ROOT/'.tools/npm-cache')
    env['BASEBALL_ELECTRON_CACHE']=str(ROOT/'workspace/build/electron-cache')
    compiler=ROOT/'.tools/ziglang/zig.exe';npm=ROOT/'.tools/npm-runtime/package/bin/npm-cli.js'
    def run(args):
        print('CHECK '+args[0]+' '+str(args[1:4]),flush=True)
        start=time.perf_counter();p=subprocess.run(args,cwd=target,env=env,capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=240)
        commands.append({'args':args,'exit_code':p.returncode,'elapsed_ms':round((time.perf_counter()-start)*1000),'stdout_tail':p.stdout[-3500:],'stderr_tail':p.stderr[-1500:]})
        if p.returncode:raise RuntimeError(p.stdout+'\n'+p.stderr)
    report={'passed':False,'source_files':len(list(filter(None,names))),'source_directory':str(target),'toolchain_cache_reused':True,'python':sys.version,'pywin32':importlib.metadata.version('pywin32'),'pytest':importlib.metadata.version('pytest'),'commands':commands}
    try:
        run([sys.executable,'workspace/build_native.py','--compiler',str(compiler),'--cache-root',str(ROOT/'workspace/build/zig-cache')])
        run(['node',str(npm),'ci','--prefix','workspace','--offline','--no-audit','--no-fund'])
        run([sys.executable,'-m','pytest','workspace/tests','-q'])
        run(['node','--test','workspace/tests/viewer.test.mjs'])
        run([sys.executable,'workspace/match.py','--away','bots/base_bot','--home','bots/base_bot','--seed','42','--regulation-ticks','1200','--output','results/cleanroom-match'])
        run([sys.executable,'workspace/replay.py','verify','--input','results/cleanroom-match','--from-start'])
        run([sys.executable,'workspace/replay.py','frames','--input','results/cleanroom-match','--output','results/cleanroom-match/cache/frames'])
        run([sys.executable,'workspace/unpack_demo.py','--output','results/offline-demo'])
        run([sys.executable,'workspace/replay.py','verify','--input','results/offline-demo'])
        report['passed']=True
    except Exception as e:report['error']=str(e);raise
    finally:
        Path(args.report).write_text(json.dumps(report,indent=2,ensure_ascii=True)+'\n',encoding='utf-8',newline='\n')
    print(json.dumps({'passed':True,'commands':len(commands),'isolated_root':str(target)}),flush=True)


if __name__=='__main__':main()
