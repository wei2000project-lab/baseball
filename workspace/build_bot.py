"""Compile a C++17 JSONL Bot before its runtime resource/watchdog limits start."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import uuid

ROOT = Path(__file__).resolve().parent
VENDOR = ROOT.parent / "bots/vendor"
SOURCE_EXTENSIONS = {".cpp", ".cc", ".cxx", ".h", ".hpp", ".hxx", ".inl"}
EXCLUDED = {"build", "dist", "node_modules", "__pycache__", ".git", ".cache", ".tools", "results"}


def source_files(directory, extensions=SOURCE_EXTENSIONS):
    """Prune build/cache trees rather than traversing their potentially huge contents."""
    for root, directories, names in os.walk(directory):
        directories[:] = sorted(d for d in directories if d not in EXCLUDED and not Path(root, d).is_symlink())
        for name in sorted(names):
            path = Path(root, name)
            if path.suffix.lower() in extensions and path.is_file():
                yield path


def compiler_command(compiler=None):
    selected = compiler or os.environ.get("BASEBALL_BOT_CXX")
    if not selected:
        local = ROOT.parent / ".tools/ziglang" / ("zig.exe" if os.name == "nt" else "zig")
        if not local.exists():
            package = importlib.util.find_spec("ziglang")
            if package and package.origin:
                local = Path(package.origin).parent / ("zig.exe" if os.name == "nt" else "zig")
        selected = str(local) if local.exists() else shutil.which("clang++") or shutil.which("g++")
    if not selected:
        raise RuntimeError("cpp_compiler_missing: install ziglang or set BASEBALL_BOT_CXX")
    executable = Path(selected).expanduser()
    if not executable.is_file():
        found = shutil.which(str(selected))
        if not found:
            raise RuntimeError("cpp_compiler_not_found: " + str(selected))
        executable = Path(found)
    command = [str(executable.resolve())]
    if executable.stem.lower() == "zig":
        command.append("c++")
    return command


def build_cpp_bot(source, compiler=None, force=False):
    source = Path(source).resolve()
    if not source.is_file() or source.suffix.lower() not in (".cpp", ".cc", ".cxx"):
        raise ValueError("cpp_bot_source_missing: " + str(source))
    command = compiler_command(compiler)
    flags = ["-std=c++17", "-O2", "-I", str(VENDOR)]
    env = os.environ.copy()
    cache = ROOT / "build"
    cache.mkdir(exist_ok=True)
    for key, name in (("ZIG_GLOBAL_CACHE_DIR", "zig-cache"), ("ZIG_LOCAL_CACHE_DIR", "zig-local-cache"), ("TEMP", "tmp"), ("TMP", "tmp")):
        target = cache / name
        target.mkdir(exist_ok=True)
        env[key] = str(target)
    options = dict(env=env, capture_output=True, text=True, encoding="utf-8", errors="replace",
                   creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
    try:
        version = subprocess.run([command[0], "version" if len(command) == 2 else "--version"],
                                 timeout=15, check=True, **options).stdout.strip()
    except (OSError, subprocess.SubprocessError) as error:
        raise RuntimeError("cpp_compiler_unavailable: " + str(error)) from error
    inputs = {}
    for directory, label in ((source.parent, "bot"), (VENDOR, "vendor")):
        for path in source_files(directory):
            inputs[label + "/" + path.relative_to(directory).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    signature = dict(source=str(source), compiler=command, compiler_version=version, flags=flags, inputs=inputs)
    key = hashlib.sha256(json.dumps(signature, sort_keys=True).encode()).hexdigest()
    directory = cache / "cpp-bots" / key
    directory.mkdir(parents=True, exist_ok=True)
    stamp = directory / "build.json"
    if stamp.exists() and not force:
        try:
            metadata = json.loads(stamp.read_text(encoding="utf-8"))
            binary = (directory / metadata["program"]).resolve()
            binary.relative_to(directory)
            if metadata["signature"] == signature and binary.is_file() and hashlib.sha256(binary.read_bytes()).hexdigest() == metadata["binary_sha256"]:
                return binary
        except (ValueError, KeyError, OSError, TypeError):
            pass
    # Never overwrite an executable which another match may still have loaded.
    output = directory / uuid.uuid4().hex[:12]
    output.mkdir()
    binary = output / ("bot.exe" if os.name == "nt" else "bot")
    log = output / "compiler.log"
    try:
        result = subprocess.run(command + flags + [str(source), "-o", str(binary)],
                                cwd=source.parent, timeout=120, **options)
        log.write_text(result.stdout + result.stderr, encoding="utf-8")
        if result.returncode:
            raise RuntimeError("cpp_bot_compile_failed: see " + str(log))
    except (OSError, subprocess.TimeoutExpired) as error:
        log.write_text(str(error), encoding="utf-8")
        raise RuntimeError("cpp_bot_compile_failed: see " + str(log)) from error
    metadata = dict(signature=signature, program=binary.relative_to(directory).as_posix(),
                    binary_sha256=hashlib.sha256(binary.read_bytes()).hexdigest())
    temp = directory / (output.name + ".json.tmp")
    temp.write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    os.replace(temp, stamp)
    return binary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source");parser.add_argument("--compiler");parser.add_argument("--rebuild", action="store_true")
    args = parser.parse_args()
    try:
        print(build_cpp_bot(args.source, args.compiler, args.rebuild))
        return 0
    except (ValueError, RuntimeError, OSError) as error:
        print(str(error), file=sys.stderr)
        return 1


if __name__ == "__main__":sys.exit(main())
