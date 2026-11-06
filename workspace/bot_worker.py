"""Trusted process launcher. Install Job limits before starting untrusted Bot.

Job rules: https://learn.microsoft.com/en-us/windows/win32/procthread/job-objects
This is process/resource isolation, not a filesystem or network security sandbox.
"""
import json
import os
import subprocess
import sys


def main():
    if os.name!="nt":raise RuntimeError("unsupported_resource_isolation_platform")
    import win32api
    import win32job
    job=win32job.CreateJobObject(None,"")
    info=win32job.QueryInformationJobObject(job,win32job.JobObjectExtendedLimitInformation)
    info["BasicLimitInformation"]["LimitFlags"]=(win32job.JOB_OBJECT_LIMIT_JOB_MEMORY |
        win32job.JOB_OBJECT_LIMIT_ACTIVE_PROCESS | win32job.JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE)
    info["BasicLimitInformation"]["ActiveProcessLimit"]=2  # trusted worker + one Bot
    info["JobMemoryLimit"]=256*1024*1024
    win32job.SetInformationJobObject(job,win32job.JobObjectExtendedLimitInformation,info)
    win32job.AssignProcessToJobObject(job,win32api.GetCurrentProcess())
    check=win32job.QueryInformationJobObject(job,win32job.JobObjectExtendedLimitInformation)
    if check["JobMemoryLimit"]!=256*1024*1024:raise RuntimeError("job_limit_not_effective")
    print(json.dumps({"type":"host_ready","memory_limit_bytes":check["JobMemoryLimit"],"active_process_limit":2}),flush=True)
    child=subprocess.Popen(sys.argv[1:],stdin=sys.stdin.buffer,stdout=sys.stdout.buffer,stderr=sys.stderr.buffer,
                           creationflags=subprocess.CREATE_NO_WINDOW)
    code=child.wait()
    # Keep the job handle alive through Bot completion. OS kills the tree if worker dies.
    sys.exit(code)


if __name__=="__main__":main()
