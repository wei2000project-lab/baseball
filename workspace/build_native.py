"""Build locally: python workspace/build_native.py [--compiler path/to/zig.exe]."""
import argparse
import os
from pathlib import Path
import shutil
import subprocess
import sys
import hashlib
import json
import importlib.util

ROOT = Path(__file__).resolve().parent


def source_digest():
    sha=hashlib.sha256()
    for name in ("baseball.hpp","baseball.cpp","map.hpp","map.cpp","native_bindings.cpp"):
        sha.update(name.encode());sha.update((ROOT/name).read_bytes().replace(b"\r\n",b"\n"))
    return sha.hexdigest()


# A new build never overwrites a DLL held by an already-running viewer.
LIB = ROOT / "build" / ("native-"+source_digest()[:16]) / ("baseball.dll" if os.name == "nt" else "libbaseball.so")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--compiler")
    parser.add_argument("--cache-root",help="Optional explicit shared compiler cache; project output stays local")
    args = parser.parse_args()
    local = ROOT.parent / ".tools/ziglang" / ("zig.exe" if os.name == "nt" else "zig")
    if not local.exists():
        package=importlib.util.find_spec("ziglang")
        if package and package.origin:local=Path(package.origin).parent/("zig.exe" if os.name=="nt" else "zig")
    compiler = args.compiler or (str(local) if local.exists() else shutil.which("clang++") or shutil.which("g++"))
    if not compiler:
        sys.exit("Install: python -m pip install --target .tools ziglang==0.13.0")
    command = [compiler]
    if Path(compiler).stem == "zig":
        command += ["c++"]
    LIB.parent.mkdir(parents=True,exist_ok=True)
    command += ["-std=c++17", "-O2", "-shared", str(ROOT / "native_bindings.cpp"),
                str(ROOT / "baseball.cpp"), str(ROOT / "map.cpp"), "-o", str(LIB)]
    if os.name != "nt":
        command += ["-fPIC"]
    env = os.environ.copy()
    env["ZIG_GLOBAL_CACHE_DIR"] = str(Path(args.cache_root).resolve() if args.cache_root else ROOT / "build/zig-cache")
    env["ZIG_LOCAL_CACHE_DIR"] = str(ROOT / "build/zig-local-cache")
    temp = ROOT / "build/tmp"
    temp.mkdir(exist_ok=True)
    env["TEMP"] = env["TMP"] = str(temp)
    subprocess.run(command, env=env, check=True)
    (LIB.parent/"native-build.json").write_text(json.dumps({"source_sha256":source_digest(),
        "binary_sha256":hashlib.sha256(LIB.read_bytes()).hexdigest(),
        "compiler_version":subprocess.check_output([compiler,"version"] if Path(compiler).stem=="zig" else [compiler,"--version"],text=True).strip(),
        "flags":["-std=c++17","-O2","-shared"]},indent=2),encoding="utf-8")
    print(LIB)


if __name__ == "__main__":
    main()
