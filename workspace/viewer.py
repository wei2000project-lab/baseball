"""Start the locally installed Electron viewer without requiring global npm."""
from pathlib import Path
import os
import subprocess
import sys

root=Path(__file__).resolve().parent
binary=root/"node_modules/electron/dist"/("electron.exe" if os.name=="nt" else "electron")
if not binary.exists():raise SystemExit("Install dependencies: npm ci --prefix workspace (or local npm in .tools)")
env=os.environ.copy();env.pop("ELECTRON_RUN_AS_NODE",None)
env["BASEBALL_PYTHON"]=sys.executable
sys.exit(subprocess.call([str(binary),str(root),*sys.argv[1:]],env=env))
