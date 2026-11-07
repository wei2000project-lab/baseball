"""Bounded external JSONL, watchdog and deterministic request correlation."""
import hashlib
import os
from pathlib import Path
import queue
import subprocess
import sys
import threading
import time
from numeric import canonical,strict_loads
from build_bot import build_cpp_bot,source_files

LIMIT=64*1024
PROTOCOL="1.0.0"


class BotFault(RuntimeError):pass


def bot_command(path):
    path=Path(path).resolve()
    if path.is_dir():
        descriptor=path/"bot.json"
        if descriptor.exists():
            config=strict_loads(descriptor.read_text(encoding="utf-8"))
            if set(config)!={"command"} or not isinstance(config["command"],list) or not config["command"] or not all(type(x)is str for x in config["command"]):raise ValueError("invalid_bot_descriptor")
            command=config["command"][:]
            if command[0]=="python":command[0]=sys.executable
            elif (path/command[0]).is_file():command[0]=str(path/command[0])
        elif (path/"bot.cpp").is_file():command=[str(path/"bot.cpp")]
        elif (path/"bot.py").is_file():command=[sys.executable,"-u",str(path/"bot.py")]
        else:raise ValueError("bot_not_found: expected bot.json, bot.cpp or bot.py")
        directory=path
    else:
        if not path.is_file():raise ValueError("bot_not_found")
        command=[sys.executable,"-u",str(path)] if path.suffix==".py" else [str(path)]
        directory=path.parent
    compiled=None
    if Path(command[0]).suffix.lower() in (".cpp",".cc",".cxx"):
        source=Path(command[0])
        compiled=build_cpp_bot(source if source.is_absolute() else directory/source)
        command[0]=str(compiled)
    # Only program and descriptor sources, no environment credentials.
    sources=sorted(source_files(directory,{".py",".js",".mjs",".cjs",".json",".exe",".dll",".so",".cpp",".cc",".cxx",".h",".hpp",".hxx",".inl"}))
    sha=hashlib.sha256()
    for p in sources:sha.update(str(p.relative_to(directory)).replace("\\","/").encode());sha.update(p.read_bytes())
    if compiled:sha.update(b"compiled_cpp_binary");sha.update(compiled.read_bytes())
    return command,directory,sha.hexdigest()


class BotHost:
    def __init__(self,path,team,seed,diagnostics,timeout=2.0,capabilities=None):
        command,directory,self.program_hash=bot_command(path)
        self.team=team;self.timeout=timeout;self.queue=queue.Queue(maxsize=2);self.error=None;self.closed=False
        diagnostics=Path(diagnostics);diagnostics.mkdir(parents=True,exist_ok=True)
        self.stderr_path=diagnostics/f"{team}.stderr.log"
        temporary=diagnostics/f"{team}-tmp";temporary.mkdir(exist_ok=True)
        env={k:v for k,v in os.environ.items() if k.upper() in {"SYSTEMROOT","WINDIR","PATH","COMSPEC"}}
        env.update(PYTHONIOENCODING="utf-8",PYTHONUNBUFFERED="1",TEMP=str(temporary.resolve()),TMP=str(temporary.resolve()))
        worker=Path(__file__).resolve().parent/"bot_worker.py"
        self.process=subprocess.Popen([sys.executable,"-u",str(worker),*command],cwd=directory,env=env,
            stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name=="nt" else 0)
        self.stdout_thread=threading.Thread(target=self._stdout,daemon=True);self.stdout_thread.start()
        self.stderr_thread=threading.Thread(target=self._stderr,daemon=True);self.stderr_thread.start()
        try:
            ready=self._read()
            capability=strict_loads(ready.decode("utf-8"))
            if capability!={"type":"host_ready","memory_limit_bytes":256*1024*1024,"active_process_limit":2}:raise BotFault("resource_limits_unavailable")
            self.capability=capability
            self.send({"type":"init","protocol_version":PROTOCOL,"team_id":team,"seed":str(seed),"capabilities":capabilities or {}})
            reply=strict_loads(self._read().decode("utf-8"))
            if reply!={"type":"ready","protocol_version":PROTOCOL}:raise BotFault("invalid_ready")
        except Exception:
            self.close();raise

    def _stdout(self):
        try:
            while True:
                line=self.process.stdout.readline(LIMIT+1)
                if not line:
                    self.error="process_exited";return
                if len(line)>LIMIT or not line.endswith(b"\n"):
                    self.error="output_line_limit";return
                try:self.queue.put_nowait(line)
                except queue.Full:self.error="unsolicited_output";return
        except (OSError,ValueError):self.error="stdout_io"

    def _stderr(self):
        total=0
        try:
            with open(self.stderr_path,"wb") as log:
                while True:
                    chunk=self.process.stderr.read(4096)
                    if not chunk:return
                    if total<1024*1024:log.write(chunk[:1024*1024-total])
                    total+=len(chunk)
                    if total>1024*1024:self.error="stderr_limit";return
        except (OSError,ValueError):self.error="stderr_io"

    def _read(self):
        deadline=time.monotonic()+self.timeout
        while True:
            if self.error:raise BotFault(self.error)
            try:return self.queue.get(timeout=min(.02,max(.001,deadline-time.monotonic())))
            except queue.Empty:
                if time.monotonic()>=deadline:raise BotFault("watchdog_timeout")

    def send(self,message):
        if self.error:raise BotFault(self.error)
        try:data=canonical(message)
        except ValueError:raise BotFault("stdin_io")
        self._send_bytes(data)

    def send_observation(self,decision_id,sim_tick,state_json,legal_action_types):
        """Reuse the same canonical public snapshot bytes for both teams."""
        envelope=canonical(dict(type='observe',protocol_version=PROTOCOL,decision_id=decision_id,
            sim_tick=sim_tick,team_id=self.team,state=None,legal_action_types=legal_action_types))
        self._send_bytes(envelope.replace(b'"state":null',b'"state":'+state_json,1))

    def _send_bytes(self,data):
        if self.error:raise BotFault(self.error)
        try:self.process.stdin.write(data+b"\n");self.process.stdin.flush()
        except (OSError,ValueError):raise BotFault("stdin_io")

    def receive(self,decision_id):
        raw=self._read().decode("utf-8",errors="strict")
        try:
            response=strict_loads(raw)
            if type(response)is not dict or set(response)!={"type","protocol_version","decision_id","actions"}:raise ValueError("invalid_envelope")
            if response["protocol_version"]!=PROTOCOL:raise ValueError("unsupported_protocol_version")
            if response["type"]!="action" or response["decision_id"]!=decision_id:raise ValueError("stale_decision_id")
            return response["actions"],raw,None
        except (ValueError,KeyError,TypeError) as error:return None,raw,str(error)

    def close(self):
        if self.closed:return
        self.closed=True
        try:
            if self.process.poll()is None:
                self.process.stdin.write(canonical({"type":"shutdown"})+b"\n");self.process.stdin.flush()
                self.process.wait(timeout=.5)
        except (OSError,ValueError,subprocess.TimeoutExpired):
            self.process.kill();self.process.wait(timeout=5)
        for pipe in (self.process.stdin,self.process.stdout,self.process.stderr):
            if pipe:pipe.close()
        self.stdout_thread.join(timeout=.5);self.stderr_thread.join(timeout=.5)
