import json
from pathlib import Path
import subprocess
import sys
from test_p5 import make_record
from numeric import digest
from replay import ReplayRecord

ROOT=Path(__file__).resolve().parents[1]


def read_until(process,kind):
    for line in process.stdout:
        packet=json.loads(line)
        if packet['type']==kind:return packet
        assert packet['type']!='error',packet
    raise AssertionError('viewer worker ended early: '+process.stderr.read())


def test_persistent_worker_verifies_then_seeks_without_bot(tmp_path):
    path=make_record(tmp_path/'viewer-record')
    process=subprocess.Popen([sys.executable,str(ROOT/'viewer_worker.py'),'--input',str(path)],
        stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,encoding='utf-8')
    try:
        loaded=read_until(process,'loaded');assert loaded['metadata']['verification']['verification_status']=='verified_record'
        record=ReplayRecord(path)
        for request_id,tick in enumerate([0,123,600,record.final_tick],1):
            process.stdin.write(json.dumps({'id':request_id,'type':'seek','tick':tick})+'\n');process.stdin.flush()
            result=read_until(process,'seek_result')
            assert result['id']==request_id and result['frame']['tick']==tick
            assert result['state_hash']==digest(record.seek(tick))
        process.stdin.close();assert process.wait(timeout=5)==0
    finally:
        if process.poll() is None:process.kill();process.wait(timeout=5)


def test_electron_boundary_and_no_shell_or_untrusted_html():
    main=(ROOT/'electron/main.cjs').read_text(encoding='utf-8');preload=(ROOT/'electron/preload.cjs').read_text(encoding='utf-8');html=(ROOT/'viewer.html').read_text(encoding='utf-8')
    assert 'contextIsolation: true' in main and 'nodeIntegration: false' in main and 'sandbox: true' in main
    assert 'shell: false' in main and 'event.sender !== window.webContents' in main
    assert 'Content-Security-Policy' in html and "script-src 'self'" in html
    assert 'ipcRenderer.send' not in preload and 'exposeInMainWorld' in preload
    assert 'innerHTML' not in (ROOT/'viewer/app.mjs').read_text(encoding='utf-8')
