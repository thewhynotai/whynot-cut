"""The file-queue protocol of the WhyNot Cut Bridge (one CEP bundle; Premiere uses ppro-queue, After Effects ae-queue).

The bridge's hidden daemon writes `bridge.heartbeat` every second, claims `<id>.job.json` by renaming it, evaluates the
whitelisted script named in the job with the job's data file, and writes `<id>.result.json`. These helpers are
host-neutral: ppro_bridge and ae_bridge pass their own queue folder and script.

Queue files (bridge 3.1.1; the contract v4 adapter, engine/reel/contract/, mirrors these fields):
    bridge.heartbeat     {at: ms epoch, busy, version, host, role: "daemon"|"panel", current: job id|null}. Only one copy
                         of the bridge works the queue: the hidden daemon; the visible panel shows its state and works
                         the queue itself only while no daemon heartbeat is fresh (the daemon did not load).
    <id>.data.json       the job's data (ASCII JSON): {...data, action, job_id, submitted}. Unchanged since 3.0.
    <id>.job.json        {id, action, script, data_file, submitted, expires_at}. `script` and `data_file` are resolved
                         absolute paths. `expires_at` (RFC 3339 with a zone) is the last instant the job may START: the
                         bridge claims an expired job and answers {ok: false, error: "expired"} without running it.
    <id>.running         the job, renamed by the bridge: the atomic claim (only one rename succeeds).
    <id>.claimed         {at, by}: written by the bridge right after the claim. The caller's result timeout starts here,
                         so time spent waiting behind another job never counts against it.
    <id>.job.cancelled   the caller timed out before any claim and renamed the job: it never runs (then removed).
    <id>.result.json     {ok, result | error, at}, written atomically by the bridge; the caller deletes it, the data
                         file and the claim marker once read.
    .build.lock          {pid, pid_created, host, what, started_at, expires_at}: one build at a time per host app,
                         machine-wide (ppro-build, ppro-frames, motion-build); see `build_lock`.
Anything else older than a day (a crashed run's leftovers) is removed by `sweep`, which every submit runs first.
"""
from __future__ import annotations

import contextlib
import datetime as _dt
import json
import os
import socket
import time
import uuid
from pathlib import Path

from . import plat
from .common import now_iso

SWEEP_AGE_S = 24 * 3600                  # queue files older than this are a crashed run's leftovers
ORPHAN_AGE_S = 21 * 60                   # a .running older than the bridge's own 20-minute job limit
CLAIM_CHECK_S = 2.0                      # how often an unclaimed wait re-reads the heartbeat
LOCK_NAME = ".build.lock"
# a second build waits this long for the first, then gets BRIDGE_BUSY. Not a bound on the first build: its bridge call
# may take claim 900 s + result 900 s in the worst case (submit's two clocks), so a long wait can still end busy
LOCK_WAIT_S = 1200.0
_SWEEP_SUFFIXES = (".data.json", ".result.json", ".job.json", ".running", ".claimed", ".job.cancelled", ".tmp",
                   ".result.tmp")


def _iso_utc(t: float) -> str:
    # milliseconds: a whole-second stamp would end a short claim window up to 1 s early (bridge.js Date.parse reads both)
    return _dt.datetime.fromtimestamp(t, _dt.timezone.utc).isoformat(timespec="milliseconds")


def status(queue: Path, max_age_s: float = 5.0, app: str = "the Adobe app") -> dict:
    """The bridge as the heartbeat shows it. `max_age_s` must stay below bridge.js DAEMON_STALE_MS (6.5 s): the panel
    takes over only after the engine has stopped counting the daemon alive."""
    queue = Path(queue)
    hb = queue / "bridge.heartbeat"
    if not hb.exists():
        return {"alive": False, "host": None,
                "detail": f"no heartbeat: start {app} (bridge auto-starts) or open Window > Extensions > WhyNot Cut Bridge"}
    d = None
    for _ in range(4):          # a bridge older than 3.1.1 rewrites the file in place every second: retry a torn read
        try:
            d = json.loads(hb.read_text(encoding="utf-8"))
            break
        except Exception:
            time.sleep(0.05)
    if not isinstance(d, dict):
        return {"alive": False, "host": None, "detail": "unreadable heartbeat"}
    try:
        age = time.time() - float(d["at"]) / 1000
    except (KeyError, TypeError, ValueError):
        return {"alive": False, "host": d.get("host"), "bridge_version": d.get("version"),
                "detail": f"the heartbeat has no time: the bridge in {app} is too old or broken - reinstall it "
                          "(`reel ppro-install`) and restart the app"}
    out = {"alive": age < max_age_s, "age_s": round(age, 1), "busy": d.get("busy"), "bridge_version": d.get("version"),
           "host": d.get("host"), "role": d.get("role"), "current": d.get("current"),
           "detail": "ok" if age < max_age_s else f"heartbeat {age:.0f}s old: panel closed or {app} busy/quit"}
    orphans = _orphans(queue, d.get("current"))
    if orphans:
        out["orphans"] = orphans
    return out


def _orphans(queue: Path, current) -> list[str]:
    """Claimed jobs the bridge never finished (a crash or a restart while running): reported, swept after a day."""
    out, now = [], time.time()
    for f in queue.glob("*.running"):
        jid = f.name[:-len(".running")]
        try:
            if jid != current and now - f.stat().st_mtime > ORPHAN_AGE_S:
                out.append(jid)
        except OSError:
            pass
    return sorted(out)


def sweep(queue: Path, max_age_s: float = SWEEP_AGE_S) -> list[str]:
    """Remove queue files older than `max_age_s` (never the heartbeat or a build lock). Returns the names removed."""
    gone, now = [], time.time()
    try:
        entries = list(Path(queue).iterdir())
    except OSError:
        return gone
    for f in entries:
        if not f.name.endswith(_SWEEP_SUFFIXES):
            continue
        try:
            if now - f.stat().st_mtime > max_age_s:
                f.unlink()
                gone.append(f.name)
        except OSError:
            pass
    return gone


def _ver(v) -> tuple:
    import re
    return tuple(int(x) for x in re.findall(r"\d+", str(v or ""))[:3])


def version_refusal(st: dict, expect: str, app: str) -> dict | None:
    """The running bridge must be the one this engine ships: a host that was not restarted after a plugin update
    still runs the old panel against the new scripts. A refusal (`blocked`: exit 2)."""
    have = st.get("bridge_version")
    if have == expect:
        return None
    error = f"the WhyNot Cut Bridge running in {app} is {have or 'an unknown version'}; this engine needs bridge {expect}"
    if have and _ver(have) > _ver(expect):
        # a newer plugin installed it; `reel ppro-install` keeps a newer bridge, so it would not help
        how = (f"The running bridge {have} is newer than this engine's {expect}: update the WhyNot Cut plugin to the "
               f"version that ships bridge {have}. Only to go back to {expect} on purpose: `reel ppro-install --force`, "
               f"then restart {app}.")
    else:
        how = (f"Restart {app} to load bridge {expect}. If it still reports {have or 'another version'}, run "
               "`reel ppro-install` first, then restart it.")
    return {"ok": False, "error": error, "blocked": error, "how": how, "status": st}


def _unlink(*paths: Path) -> None:
    for p in paths:
        try:
            p.unlink()
        except OSError:
            pass


def submit(queue: Path, script: Path, action: str, data: dict | None = None, timeout: float = 600,
           poll_s: float = 0.5, st: dict | None = None, app: str = "the Adobe app", *,
           claim_timeout: float | None = None, expect_version: str | None = None) -> dict:
    """Queue one job and wait for its result. `st` = a status already checked by the caller (else checked here).

    Two clocks: the bridge must CLAIM the job within `claim_timeout` (default: `timeout`), else the job is cancelled
    and never runs; once claimed, the result must come within `timeout`. `expect_version`: refuse unless the running
    bridge reports exactly this version."""
    queue = Path(queue)
    refused = plat.sandbox_refusal(f"queue the {action} job", queue, script)          # G79: never in tests
    if refused:
        return refused
    st = st if st is not None else status(queue, app=app)
    if not st["alive"]:
        return {"ok": False, "error": "bridge not running", "status": st}
    if expect_version:
        refused = version_refusal(st, expect_version, app)
        if refused:
            return refused
    queue.mkdir(parents=True, exist_ok=True)
    sweep(queue)
    claim_s = timeout if claim_timeout is None else claim_timeout
    jid = time.strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:6]
    payload = dict(data or {}, action=action, job_id=jid, submitted=now_iso())
    data_file = queue / f"{jid}.data.json"
    data_file.write_text(json.dumps(payload, ensure_ascii=True), encoding="ascii")
    t0 = time.time()
    # resolved paths: the bridge compares realpath(script) with its whitelisted folder (a custom WHYNOT_HOME whose
    # drive-letter case or symlinks differ must not be rejected)
    job = {"id": jid, "action": action, "script": str(Path(script).resolve()), "data_file": str(data_file.resolve()),
           "submitted": payload["submitted"], "expires_at": _iso_utc(t0 + claim_s)}
    tmp = queue / f"{jid}.tmp"
    tmp.write_text(json.dumps(job), encoding="utf-8")
    job_p = queue / f"{jid}.job.json"
    tmp.rename(job_p)      # atomic: the bridge never sees a half-written job
    try:
        return _wait(queue, jid, t0, claim_s, timeout, poll_s, app)
    except BaseException as e:  # Ctrl-C while waiting: a job nobody waits for must not run later
        cancelled = _cancel(queue, jid)
        with contextlib.suppress(Exception):
            e.wnc_claimed = not cancelled     # True: the bridge has (or had) the job, the host may still act on it
        raise


def _cancel(queue: Path, jid: str) -> bool:
    """Take back a job the bridge has not claimed (True): it never runs. False = it was claimed meanwhile."""
    job_p, gone = queue / f"{jid}.job.json", queue / f"{jid}.job.cancelled"
    try:
        job_p.rename(gone)
    except OSError:
        return False
    _unlink(gone, queue / f"{jid}.data.json")
    return True


def _wait(queue: Path, jid: str, t0: float, claim_s: float, timeout: float, poll_s: float, app: str) -> dict:
    res_p, job_p = queue / f"{jid}.result.json", queue / f"{jid}.job.json"
    claim_p, run_p = queue / f"{jid}.claimed", queue / f"{jid}.running"
    claimed_at, checked = None, t0
    while True:
        now = time.time()
        if res_p.exists():
            try:
                r = json.loads(res_p.read_text(encoding="utf-8"))
            except ValueError:          # a bridge older than 3.1.1 is still writing it
                time.sleep(0.2)
                continue
            _unlink(res_p, claim_p, queue / f"{jid}.data.json")
            if r.get("error") == "expired":
                return {"ok": False, "error": f"timeout: the job expired before {app} could start it",
                        "how": f"{app} was busy (another job or a dialog). Dismiss any dialog, then run the command again.",
                        "expired": True, "job": jid}
            inner = r.get("result")
            try:
                inner = json.loads(inner) if isinstance(inner, str) else inner
            except Exception:
                pass
            out = {"ok": bool(r.get("ok")) and isinstance(inner, dict) and inner.get("ok", False),
                   "bridge_ok": r.get("ok"), "response": inner, "elapsed_s": round(time.time() - t0, 1), "job": jid}
            if not r.get("ok") and r.get("error") and inner is None:
                out["error"] = r["error"]           # the bridge's own refusal (script not whitelisted, no reply)
            return out
        if claimed_at is None:
            if claim_p.exists() or run_p.exists() or not job_p.exists():
                claimed_at = now                    # (no job file and no result yet: claimed this instant)
            elif now - t0 >= claim_s:
                if _cancel(queue, jid):
                    return {"ok": False, "error": f"timeout: {app} did not start the job within {claim_s:g}s; it was "
                                                  "cancelled and will not run",
                            "how": f"{app} is busy with another job or shows a dialog: dismiss it, then run the "
                                   "command again.", "cancelled": True, "job": jid}
                claimed_at = now
            elif now - checked >= CLAIM_CHECK_S:
                checked = now
                st = status(queue, app=app)
                if not st["alive"] and _cancel(queue, jid):
                    return {"ok": False, "error": "bridge stopped before it started the job (cancelled)",
                            "status": st, "cancelled": True, "job": jid}
        elif now - claimed_at >= timeout:
            return {"ok": False, "error": f"timeout after {timeout:g}s ({app} may show a dialog)", "claimed": True,
                    "job": jid}
        time.sleep(poll_s)


# --------------------------------------------------------------------------- one build at a time (machine-wide)
class BuildLockBusy(RuntimeError):
    def __init__(self, holder: dict, waited_s: float):
        self.holder, self.waited_s = holder, waited_s
        super().__init__(f"another build is running: {describe_lock(holder)}")


def describe_lock(rec: dict) -> str:
    return (f"{rec.get('what') or 'a build'} (process {rec.get('pid')} on {rec.get('host')}, since "
            f"{rec.get('started_at') or '?'})")


def read_lock(queue: Path) -> dict | None:
    try:
        rec = json.loads((Path(queue) / LOCK_NAME).read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except (OSError, ValueError):
        return {}
    return rec if isinstance(rec, dict) else {}


def lock_stale(queue: Path, rec: dict | None) -> bool:
    """A lock may be taken over when its process on this computer is gone (pid + creation time), or, held from another
    computer, when it expired. A live holder on this computer is never stale: it does not renew its expiry, and a build
    may run past it."""
    from .writer_lock import pid_alive
    if rec is None:
        return False
    if not rec:                                  # unreadable: being written right now, unless it is old
        try:
            return time.time() - (Path(queue) / LOCK_NAME).stat().st_mtime > 30
        except OSError:
            return True
    if rec.get("host") == socket.gethostname():
        return not pid_alive(rec.get("pid"), rec.get("pid_created"))
    try:
        return time.time() > float(rec.get("expires_at") or 0)
    except (TypeError, ValueError):
        return True


@contextlib.contextmanager
def build_lock(queue: Path, what: str, *, hold_s: float = 1800.0, wait_s: float = LOCK_WAIT_S, poll_s: float = 1.0):
    """Hold `<queue>/.build.lock` around one build: a second build (another session, another reel) waits up to
    `wait_s` for it, so its own bridge timeout never runs out while it queues. The record carries the pid (a crashed
    holder's lock is taken over) and an expiry `hold_s` ahead. Raises BuildLockBusy when still held after `wait_s`."""
    from .writer_lock import process_created
    queue = Path(queue)
    queue.mkdir(parents=True, exist_ok=True)
    lock = queue / LOCK_NAME
    t0 = time.time()
    while True:
        rec = {"pid": os.getpid(), "pid_created": process_created(os.getpid()), "host": socket.gethostname(),
               "what": what, "started_at": now_iso(), "expires_at": time.time() + hold_s}
        try:
            fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError:
            held = read_lock(queue)
            if lock_stale(queue, held):
                stale = lock.with_name(f"{LOCK_NAME}.stale-{uuid.uuid4().hex[:6]}")
                try:
                    lock.rename(stale)          # only one waiter wins the takeover
                except OSError:
                    continue
                try:
                    took = json.loads(stale.read_text(encoding="utf-8"))
                except (OSError, ValueError):
                    took = {}
                # another waiter took over first (also when we read the lock while it was unreadable): that lock is
                # live, put it back
                if isinstance(took, dict) and took and took != held:
                    with contextlib.suppress(OSError):
                        stale.rename(lock)
                _unlink(stale)
                continue
            if time.time() - t0 >= wait_s:
                raise BuildLockBusy(held or {}, round(time.time() - t0, 1))
            time.sleep(poll_s)
            continue
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(rec, f)
        break
    try:
        yield rec
    finally:
        if read_lock(queue) == rec:
            _unlink(lock)


def lock_busy_result(e: BuildLockBusy, app: str) -> dict:
    """The engine's refusal when the lock wait ran out."""
    return {"blocked": f"another build is running in {app}: {describe_lock(e.holder)}; waited {e.waited_s:g}s",
            "how": f"Let it finish (one build at a time per {app}), then run the command again."}
