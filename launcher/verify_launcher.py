"""Exercise only this launcher's hidden window; never opens a viewer or file dialog."""
import argparse
import json
from pathlib import Path
import struct
import subprocess
import sys
import uuid
from build_launcher import build,ROOT

sys.path.insert(0,str(ROOT/"workspace"))
from configuration import default_config
from replay import ReplayRecord


def verify(work):
    binary=build();data=binary.read_bytes();pe=struct.unpack_from("<I",data,0x3c)[0]
    assert struct.unpack_from("<H",data,pe+24+68)[0]==2, "Launcher must be a GUI executable"
    profile=default_config()
    profile["rules"].update(regulation_ticks=1,plate_appearance_setup_ticks=1,pitch_reset_ticks=1,
                            half_inning_change_ticks=1,pitch_release_deadline_ticks=20,max_ticks=10000)
    config=work/"config.json";config.write_text(json.dumps(profile),encoding="utf-8")
    results=[]
    for case in ("completed","cancelled","aborted"):
        directory=work/case;directory.mkdir(parents=True)
        request=dict(away="bots/examples/cpp_passive",home="bots/examples/minimal.py",config=str(config),
                     output_root=str(directory/"中文 輸出 with spaces"),report=str(directory/"report.json"))
        if case=="cancelled":
            long_profile=default_config();long_profile["rules"].update(regulation_ticks=1,plate_appearance_setup_ticks=1,
                pitch_reset_ticks=1,half_inning_change_ticks=1,pitch_release_deadline_ticks=200,max_ticks=100000)
            path=directory/"long.json";path.write_text(json.dumps(long_profile),encoding="utf-8")
            request.update(config=str(path),cancel_after_progress=True)
        elif case=="aborted":
            bad=directory/"invalid.cpp";bad.write_text("int main( not valid C++ );\n",encoding="utf-8")
            request.update(away=str(bad),expect_status="aborted")
        path=directory/"test.json";path.write_text(json.dumps(request),encoding="utf-8")
        process=subprocess.run([str(binary),"--self-test",str(path)],creationflags=subprocess.CREATE_NO_WINDOW,timeout=180)
        report=json.loads(Path(request["report"]).read_text(encoding="utf-8"))
        assert process.returncode==0 and report["passed"],report
        assert report["visible"] is False
        record=ReplayRecord(report["output"])
        status=record.verify()["verification_status"]
        if case=="cancelled":
            assert report["cancelled"] and report["owned_process_tree_stopped"] and status=="incomplete"
        else:
            assert status=="verified_record" and record.summary==report["summary"]
            assert record.summary["status"]==case
        results.append(dict(case=case,verification_status=status,**report))
    return dict(passed=True,mode="native hidden window; no desktop input, viewer, shell or file dialog",
                executable=str(binary),pe_subsystem=2,checks=sum(len(r["checks"]) for r in results),cases=results)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report",default=str(ROOT/"workspace/tests/reports/launcher.json"));args=parser.parse_args()
    work=ROOT/"workspace/build/launcher-acceptance"/uuid.uuid4().hex[:12];work.mkdir(parents=True)
    result=verify(work)
    Path(args.report).write_text(json.dumps(result,indent=2,ensure_ascii=True)+"\n",encoding="utf-8")
    print(json.dumps(dict(passed=True,checks=result["checks"],cases=len(result["cases"]))))


if __name__=="__main__":main()
