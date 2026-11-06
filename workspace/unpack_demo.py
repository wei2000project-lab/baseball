"""Extract the versioned offline reference record; never overwrite results."""
import argparse
import hashlib
import json
from pathlib import Path
import zipfile

ROOT=Path(__file__).resolve().parent
FILES={'match.txt'}


def unpack(output,archive=None,metadata=None):
    archive=Path(archive or ROOT/'examples/demo-0042.bbrec.zip')
    info=json.loads(Path(metadata or ROOT/'examples/demo-0042.json').read_text(encoding='utf-8'))
    if hashlib.sha256(archive.read_bytes()).hexdigest()!=info['sha256']:raise ValueError('demo_archive_integrity')
    output=Path(output).resolve()
    if output.exists() and any(output.iterdir()):raise ValueError('output_not_empty')
    with zipfile.ZipFile(archive) as source:
        if len(source.infolist())!=len(FILES) or set(source.namelist())!=FILES:raise ValueError('unsafe_demo_entries')
        if sum(i.file_size for i in source.infolist())>128*1024*1024:raise ValueError('demo_size_limit')
        output.mkdir(parents=True,exist_ok=True)
        for name in sorted(FILES):
            target=output/name
            if target.is_symlink():raise ValueError('unsafe_demo_output')
            target.write_bytes(source.read(name))
    return info


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',required=True);args=p.parse_args()
    info=unpack(args.output);print(json.dumps({'output':str(Path(args.output).resolve()),'summary':info['summary']}))


if __name__=='__main__':main()
