"""Build the native Windows launcher. --launch is used only by the user's BAT."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

HERE=Path(__file__).resolve().parent
ROOT=HERE.parent
sys.path.insert(0,str(ROOT/"workspace"))
from build_bot import compiler_command


def build():
    if os.name!="nt":raise RuntimeError("This launcher requires Windows")
    directory=HERE/"build";directory.mkdir(exist_ok=True)
    python=Path(sys.executable)
    if python.name.lower()=="pythonw.exe":python=python.with_name("python.exe")
    (directory/"python.txt").write_text(str(python.resolve()),encoding="utf-8")
    compiler=compiler_command()
    flags=["-std=c++17","-O2","-municode","-Wl,--subsystem,windows","-I",str(ROOT/"bots/vendor"),
           "-lcomdlg32","-lshell32","-lole32","-lcomctl32","-lgdi32"]
    env=os.environ.copy()
    for key,name in (("ZIG_GLOBAL_CACHE_DIR","zig-cache"),("ZIG_LOCAL_CACHE_DIR","zig-local-cache"),("TEMP","tmp"),("TMP","tmp")):
        path=ROOT/"workspace/build"/name;path.mkdir(parents=True,exist_ok=True);env[key]=str(path)
    version=subprocess.check_output([compiler[0],"version" if len(compiler)==2 else "--version"],
        env=env,text=True,encoding="utf-8",creationflags=subprocess.CREATE_NO_WINDOW).strip()
    sha=hashlib.sha256()
    for path in (HERE/"launcher.cpp",ROOT/"bots/vendor/nlohmann/json.hpp"):
        sha.update(path.read_bytes().replace(b"\r\n",b"\n"))
    sha.update(json.dumps([compiler,version,flags]).encode())
    binary=directory/("BaseballLauncher-"+sha.hexdigest()[:16]+".exe")
    metadata=binary.with_suffix(".json")
    cached=False
    if binary.exists() and metadata.exists():
        info=json.loads(metadata.read_text(encoding="utf-8"))
        cached=info.get("sha256")==hashlib.sha256(binary.read_bytes()).hexdigest()
    if not cached:
        command=compiler+flags+[str(HERE/"launcher.cpp"),"-o",str(binary)]
        result=subprocess.run(command,env=env,capture_output=True,text=True,encoding="utf-8",errors="replace",
                              timeout=180,creationflags=subprocess.CREATE_NO_WINDOW)
        log=directory/"compiler.log";log.write_text(result.stdout+result.stderr,encoding="utf-8")
        if result.returncode:raise RuntimeError("Launcher compilation failed; see "+str(log))
        metadata.write_text(json.dumps(dict(sha256=hashlib.sha256(binary.read_bytes()).hexdigest(),
            source_sha256=sha.hexdigest(),compiler=compiler,compiler_version=version,flags=flags),indent=2)+"\n",encoding="utf-8")
    (directory/"current.txt").write_text(binary.name,encoding="ascii")
    return binary


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument("--launch",action="store_true")
    args=parser.parse_args()
    try:
        binary=build()
        if args.launch:
            subprocess.Popen([str(binary)],cwd=ROOT,creationflags=subprocess.CREATE_NO_WINDOW)
        else:print(binary)
        return 0
    except Exception as error:
        if args.launch:
            import ctypes
            ctypes.windll.user32.MessageBoxW(None,str(error),"Baseball launcher",0x10)
        else:print(str(error),file=sys.stderr)
        return 1


if __name__=="__main__":sys.exit(main())
