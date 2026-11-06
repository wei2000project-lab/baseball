"""Install a pinned npm locally when Node exists without npm. No global writes."""
import base64
import hashlib
import json
from pathlib import Path
import tarfile
import urllib.request

VERSION="12.2.2"
INTEGRITY="KglgbZyacf7jH+FHuNRqVuCzQi8VhI2a7J87Ix43FsPTuZoGWmIXXGdZtBUOA79vwL+IJREqURVzupA7PsQTcA=="


def main():
    root=Path(__file__).resolve().parents[1]/".tools";root.mkdir(exist_ok=True)
    archive=root/f"npm-{VERSION}.tgz"
    data=urllib.request.urlopen(f"https://registry.npmjs.org/npm/-/npm-{VERSION}.tgz",timeout=60).read()
    if base64.b64encode(hashlib.sha512(data).digest()).decode()!=INTEGRITY:raise RuntimeError("npm_integrity_mismatch")
    archive.write_bytes(data);dest=root/"npm-runtime";dest.mkdir(exist_ok=True)
    with tarfile.open(archive) as tar:tar.extractall(dest,filter="data")
    print(dest/"package/bin/npm-cli.js")
    package=json.loads((root.parent/"workspace/package.json").read_text(encoding="utf-8"))
    print(json.dumps({"electron_version":package["devDependencies"]["electron"]}))


if __name__=="__main__":main()
