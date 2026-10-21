"""OPS-07: recover after an intake run that a usage limit cut (Windows).

A Claude session that dies at its usage limit leaves its Bash children running, so heavy.sh still sees the owner as
alive and the suite keeps a heavy slot. The intake tags its review suites with `env WNC_RUN=<session id> …`; the next
intake ends exactly the suites carrying a dead run's tag. No CPU guessing (review OPS-07-r1: the venv python.exe is a
launcher stub at 0 CPU while its child works, so CPU heuristics would kill live suites).

  python -X utf8 stale_suites.py scan-tag <session id>   list the env.exe launchers carrying WNC_RUN=<session id>
  python -X utf8 stale_suites.py end-tag  <session id>   end those process trees (re-checked just before the kill)
  python -X utf8 stale_suites.py age <ISO time>         minutes since a zoned timestamp (e.g. list_task_runs started_at)
Lock helpers (the tested rules behind MASTER-INTAKE step 0.1): lock_line / parse_lock / run_alive / lock_stale.
"""
import datetime as dt, json, re, subprocess, sys

FMT = "%Y-%m-%d %H:%M"
SESSION_RE = re.compile(r"local_[0-9a-f-]{8,}")


def tagged(procs, session_id):
    """pids of env.exe launchers whose command line carries exactly WNC_RUN=<session_id>."""
    if not SESSION_RE.fullmatch(session_id or ""):
        return []
    pat = re.compile(rf"(^|\s)WNC_RUN={re.escape(session_id)}(\s|$)")
    # env.exe = a running suite; bash.exe = heavy.sh still waiting in the queue with the tagged command (r2 P2-2)
    return [p["pid"] for p in procs if p["name"].lower() in ("env.exe", "bash.exe") and pat.search(p["cmd"] or "")]


def age_minutes(iso, now=None):
    """Whole minutes since an ISO timestamp WITH a zone ('…Z' from list_task_runs, or '+03:00'); None if no zone.
    Routines must use this instead of doing time arithmetic themselves (2026-10-20 11:40 incident)."""
    try:
        t = dt.datetime.fromisoformat(iso.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return None
    if t.tzinfo is None:
        return None
    now = now or dt.datetime.now(dt.timezone.utc)
    return int((now - t).total_seconds() // 60)


def lock_line(until, session_id):
    return f"until {until:{FMT}} session {session_id}"


def parse_lock(text):
    """(until, session id or None); (None, None) when the line cannot be read."""
    m = re.match(r"\s*until (\d{4}-\d{2}-\d{2} \d{2}:\d{2})(?: session (\S+))?\s*$", text or "")
    if not m:
        return None, None
    return dt.datetime.strptime(m.group(1), FMT), m.group(2)


def run_alive(is_running, run_status):
    """Is the lock's intake run alive? is_running: get_session isRunning (None if unknown); run_status: that session's
    status in list_task_runs of whynot-cut-hq-intake (None if not listed). A live run waiting on its review can read
    isRunning false (2026-10-21 08:38 + 13:38: two intakes ran at once), so "running" in the run list wins."""
    if is_running or run_status == "running":
        return True
    if run_status in ("failed", "succeeded"):
        return False
    return is_running


def lock_stale(until, session_id, session_running, now):
    """session_running: True / False from get_session(isRunning), None when unknown or no session in the lock.
    Stale = unreadable, its own run is known to be dead, or expired while its run is not known to be alive (a live
    review may outlast its 6 h `until`: r2 P2-1). Unknown state before expiry is respected (never two intakes)."""
    if until is None:
        return True
    if session_id and session_running is not None:
        return session_running is False
    return now >= until


def _env_procs():
    ps = ("Get-CimInstance Win32_Process -Filter \"Name='env.exe' or Name='bash.exe'\" | "
          "% { [pscustomobject]@{pid=$_.ProcessId; name=$_.Name; cmd=$_.CommandLine} } | ConvertTo-Json -Compress")
    r = subprocess.run(["powershell.exe", "-NoProfile", "-Command", ps], capture_output=True, text=True, timeout=60)
    data = json.loads(r.stdout) if r.stdout.strip() else []
    return data if isinstance(data, list) else [data]


def main(argv):
    if len(argv) == 2 and argv[0] == "age":
        m = age_minutes(argv[1])
        print("unknown (timestamp has no zone)" if m is None else m)
        return 0 if m is not None else 2
    if len(argv) == 2 and argv[0] in ("scan-tag", "end-tag"):
        pids = tagged(_env_procs(), argv[1])
        for pid in pids:
            if argv[0] == "end-tag" and pid in tagged(_env_procs(), argv[1]):  # re-check: pid not reused
                rc = subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True, text=True)
                print(f"end pid={pid} rc={rc.returncode} {rc.stdout.strip()[:200]}")
            else:
                print(f"TAGGED pid={pid}")
        print(f"{len(pids)} suite(s) tagged WNC_RUN={argv[1]}")
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
