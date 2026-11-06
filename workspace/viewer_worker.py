"""Persistent Bot-free replay worker for Electron: verify/cache, then exact seeks."""
import argparse
from pathlib import Path
import sys
import time
from numeric import canonical,strict_loads,digest
from replay import ReplayRecord,ReplayError,export_frames,frame


def send(packet):print(canonical(packet).decode(),flush=True)


def main():
    p=argparse.ArgumentParser();p.add_argument("--input",required=True);args=p.parse_args()
    try:
        record=ReplayRecord(args.input)
        meta=export_frames(record,record.root/"cache/frames",progress=lambda t,total:send({"type":"progress","sim_tick":t,"total_ticks":total}))
        send({"type":"loaded","metadata":meta})
        while True:
            line=sys.stdin.buffer.readline(65537)
            if not line:return
            if len(line)>65536:raise ValueError("worker_request_limit")
            request=strict_loads(line.decode("utf-8"));request_id=request.get("id")
            if type(request_id)is not int:raise ValueError("invalid_request_id")
            try:
                if set(request)!={"id","type","tick"} or request["type"]!="seek":raise ValueError("unsupported_worker_request")
                start=time.perf_counter();state=record.seek(request["tick"])
                send({"type":"seek_result","id":request_id,"frame":frame(state,cut=True),"state_hash":digest(state),"elapsed_ms":round((time.perf_counter()-start)*1000)})
            except (ReplayError,ValueError) as error:
                send({"type":"request_error","id":request_id,"report":error.report if isinstance(error,ReplayError) else {"reason":str(error)}})
    except (ReplayError,ValueError,KeyError,OSError,RuntimeError) as error:
        send({"type":"error","report":error.report if isinstance(error,ReplayError) else {"verification_status":"mismatch","reason":str(error)}})
        raise SystemExit(2)


if __name__=="__main__":main()
