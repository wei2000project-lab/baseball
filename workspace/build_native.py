"""Build locally: python workspace/build_native.py [--compiler path/to/zig.exe]."""
import argparse
import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parent
LIB = ROOT / "build" / ("baseball.dll" if os.name == "nt" else "libbaseball.so")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--compiler")
    args = parser.parse_args()
    local = ROOT.parent / ".tools/ziglang" / ("zig.exe" if os.name == "nt" else "zig")
    compiler = args.compiler or (str(local) if local.exists() else shutil.which("clang++") or shutil.which("g++"))
    if not compiler:
        sys.exit("Install: python -m pip install --target .tools ziglang==0.13.0")
    command = [compiler]
    if Path(compiler).stem == "zig":
        command += ["c++"]
    LIB.parent.mkdir(exist_ok=True)
    command += ["-std=c++17", "-O2", "-shared", str(ROOT / "native_bindings.cpp"),
                str(ROOT / "map.cpp"), "-o", str(LIB)]
    if os.name != "nt":
        command += ["-fPIC"]
    env = os.environ.copy()
    env["ZIG_GLOBAL_CACHE_DIR"] = str(ROOT / "build/zig-cache")
    env["ZIG_LOCAL_CACHE_DIR"] = str(ROOT / "build/zig-local-cache")
    temp = ROOT / "build/tmp"
    temp.mkdir(exist_ok=True)
    env["TEMP"] = env["TMP"] = str(temp)
    subprocess.run(command, env=env, check=True)
    print(LIB)


if __name__ == "__main__":
    main()
