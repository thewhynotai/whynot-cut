"""Run one job command from a spec file: `python trampoline.py <spec.json>` (standalone, stdlib only).

heavy.sh runs this once it holds a slot. The job's argv never crosses bash's command line (MSYS would re-quote it,
glob it and rewrite /x/... paths); it is read here from JSON and started directly. The `started` file it writes tells
the runner the slot wait is over, so the job's timeout counts execution only. Exit code = the job's exit code.
"""
import json
import os
import subprocess
import sys
import time


def main() -> int:
    with open(sys.argv[1], encoding="utf-8") as f:
        spec = json.load(f)
    started = spec["started_file"]
    with open(started + ".tmp", "w", encoding="utf-8") as f:
        f.write(str(time.time()))
    os.replace(started + ".tmp", started)
    env = dict(os.environ)
    env.update(spec.get("env") or {})
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")     # the runner reads UTF-8 (a pipe is cp1252 here)
    sys.stdout.write(f"[wnc-queue] exec {subprocess.list2cmdline(spec['argv'])}\n")
    sys.stdout.flush()
    try:
        p = subprocess.Popen(spec["argv"], cwd=spec["cwd"], env=env, stdin=subprocess.DEVNULL)
    except OSError as e:
        sys.stdout.write(f"[wnc-queue] cannot start: {e}\n")
        return 127
    return p.wait()


if __name__ == "__main__":
    sys.exit(main())
