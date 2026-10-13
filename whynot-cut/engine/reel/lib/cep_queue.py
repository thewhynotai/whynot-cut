"""The file-queue protocol of the WhyNot Cut CEP bundle (one bundle; Premiere uses ppro-queue, After Effects ae-queue).

The bundle's hidden daemon writes `bridge.heartbeat` every second, claims `<id>.job.json` by renaming it, evaluates the
library named in the job with the job's data file, and writes `<id>.result.json`. These helpers are host-neutral:
ppro_bridge and ae_bridge pass their own queue folder and library.

Two families answer during 3.0 (lib/cep_bundle.py `family`; every other version is refused, `version_refusal`):
  * bundle 3.0.0, protocol 4: jobs carry `lib` (a library bundled in <extension>/jsx/); `job_mode` -> "lib" when the
    heartbeat's `libs` equal this engine's (cep_bundle.expected_libs), else a refusal (WHYNOT_BRIDGE_DEV=1: "script");
  * legacy 3.1.1 (no `protocol`): the engine syncs the libraries into <engine home>/{ppro,ae}-scripts and sends
    `script`; the libraries keep the 3.1.1 entry names as aliases for it. Removed in 3.1.

Queue files (protocol 4; the contract v4 adapter, engine/reel/contract/, mirrors these fields):
    bridge.heartbeat     {at: ms epoch, busy, role: "daemon", host, hostVersion, bundle, version (= bundle), protocol: 4,
                         build, libs: {name: sha256}, current: job id|null, action}. 3.1.1 writes {at, busy, version,
                         host, role, current, action}. Only the hidden daemon works the queue (the 3.1.1 visible panel
                         still takes over when no daemon beats; the 3.0.0 panel never does).
    <id>.data.json       the job's data (ASCII JSON): {...data, action, job_id, submitted}. Unchanged since 3.0.
    <id>.job.json        {id, action, lib | script, data_file, submitted, expires_at}. `lib` is a bundled library's file
                         name; `script` (the legacy and compatibility path) and `data_file` are resolved absolute paths.
                         `expires_at` (RFC 3339 with a zone) is the last instant the job may START: the bridge claims an
                         expired job and answers {ok: false, error: "expired"} without running it.
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
                "detail": f"no heartbeat: start {app} (WhyNot Cut starts by itself with it)"}
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
           # protocol 4 (bundle 3.0.0); absent from a 3.1.1 heartbeat
           "protocol": d.get("protocol"), "bundle": d.get("bundle"), "build": d.get("build"), "libs": d.get("libs"),
           "host_version": d.get("hostVersion"),
           "detail": "ok" if age < max_age_s else f"heartbeat {age:.0f}s old: {app} busy or quit"}
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
    """The running bridge must be one this engine drives: bundle `expect` speaking protocol 4 with this engine's
    libraries (`libs_match`), or the legacy 3.1.1 (no protocol). A host that was not restarted after a plugin update
    still runs another one. A refusal (`blocked`: exit 2); None = accepted."""
    from . import cep_bundle
    have, proto = st.get("bridge_version"), st.get("protocol")
    if proto is None and have == cep_bundle.LEGACY_VERSION:
        return None                                   # the legacy family (3.0 only)
    if proto == cep_bundle.PROTOCOL and have == expect:
        return None if libs_match(st) or _dev() else libs_refusal(app, st)
    if proto is None and have and _ver(have) and _ver(have) < _ver(cep_bundle.LEGACY_VERSION):
        # an older bridge of ours (before 3.1.1): the install replaces it without --force (T6.3 Task 6), and until
        # then nothing is queued to it
        error = (f"the WhyNot Cut extension running in {app} is the older {have}: update it (this engine needs "
                 f"WhyNot Cut {expect})")
        how = (f"Update the WhyNot Cut extension: run `reel ppro-install` (it replaces {have}), or install WhyNot Cut "
               f"with its installer. Restart {app} to load WhyNot Cut {expect}.")
        return {"ok": False, "error": error, "blocked": error, "how": how, "status": st}
    if proto is not None and proto != cep_bundle.PROTOCOL:
        error = (f"the WhyNot Cut extension running in {app} speaks protocol {proto}; this engine needs protocol "
                 f"{cep_bundle.PROTOCOL} (WhyNot Cut {expect})")
        newer = _ver(proto) > _ver(cep_bundle.PROTOCOL)
    else:
        error = (f"the WhyNot Cut extension running in {app} is {have or 'an unknown version'}; this engine needs "
                 f"WhyNot Cut {expect}")
        # a legacy bridge (no protocol) is never newer, whatever its number says (3.1.0 is older than bundle 3.0.0)
        newer = proto is not None and _ver(have) > _ver(expect)
    if newer:
        # a newer plugin installed it; `reel ppro-install` keeps a newer extension, so it would not help
        how = (f"The running extension is newer than this engine's {expect}: update the WhyNot Cut plugin to the "
               f"version that ships it. Only to go back to {expect} on purpose: `reel ppro-install --force`, then "
               f"restart {app}.")
    else:
        how = (f"Restart {app} to load WhyNot Cut {expect}. If it still reports {have or 'another version'}, run "
               "`reel ppro-install` first, then restart it.")
    return {"ok": False, "error": error, "blocked": error, "how": how, "status": st}


def libs_match(st: dict) -> bool:
    """The running bundle carries this engine's libraries (heartbeat `libs` vs cep_bundle.expected_libs)."""
    from . import cep_bundle
    libs = st.get("libs")
    return isinstance(libs, dict) and all(libs.get(k) == v for k, v in cep_bundle.expected_libs().items())


def _dev() -> bool:
    """WHYNOT_BRIDGE_DEV=1 (off by default, 3.0 only): a bundle of another build runs the synced library by path."""
    return os.environ.get("WHYNOT_BRIDGE_DEV") == "1"


def libs_refusal(app: str, st: dict) -> dict:
    """A bundle whose libraries are not this engine's (another build): a refusal (`blocked`: exit 2)."""
    error = (f"the WhyNot Cut extension in {app} is from another build: restart {app}; if it persists, reinstall "
             "WhyNot Cut")
    return {"ok": False, "error": error, "blocked": error,
            "how": f"Restart {app}. If it persists, reinstall WhyNot Cut (`reel ppro-install`), then restart {app}.",
            "status": st}


def job_mode(st: dict, expect: str, app: str):
    """How to send a job to the running bridge: "lib" (bundle `expect` with this engine's libraries), "script" (the
    legacy 3.1.1, or a bundle of another build with WHYNOT_BRIDGE_DEV=1: the synced library by path), or a refusal
    document (`version_refusal`, `libs_refusal`)."""
    from . import cep_bundle
    refused = version_refusal(st, expect, app)        # also the libs check (another build, unless the dev loop)
    if refused:
        return refused
    if cep_bundle.family(st.get("bridge_version"), st.get("protocol")) == "legacy":
        return "script"
    return "lib" if libs_match(st) else "script"      # "script": the dev loop, the synced library by path


def _unlink(*paths: Path) -> None:
    for p in paths:
        try:
            p.unlink()
        except OSError:
            pass


def submit(queue: Path, script: Path | None, action: str, data: dict | None = None, timeout: float = 600,
           poll_s: float = 0.5, st: dict | None = None, app: str = "the Adobe app", *,
           claim_timeout: float | None = None, expect_version: str | None = None, lib: str | None = None) -> dict:
    """Queue one job and wait for its result. `st` = a status already checked by the caller (else checked here).

    Two clocks: the bridge must CLAIM the job within `claim_timeout` (default: `timeout`), else the job is cancelled
    and never runs; once claimed, the result must come within `timeout`. `expect_version`: refuse unless the running
    bridge is one this engine drives (`version_refusal`). `lib`: the job names this bundled library instead of a
    `script` path (bundle 3.0.0)."""
    queue = Path(queue)
    if (lib is None) == (script is None):
        raise ValueError("cep_queue.submit needs exactly one of script and lib")
    refused = plat.sandbox_refusal(f"queue the {action} job", queue, *([script] if script is not None else []))
    if refused:
        return refused
    st = st if st is not None else status(queue, app=app)
    if not st["alive"]:
        return {"ok": False, "error": "bridge not running", "status": st}
    if expect_version:
        refused = version_refusal(st, expect_version, app)
        if refused:
            return refused
    try:
        queue.mkdir(parents=True, exist_ok=True)
        sweep(queue)
    except BaseException as e:          # nothing is queued yet: no job can run (T2.15, ppro_build relies on the flag)
        _flag_claimed(e, False)
        raise
    claim_s = timeout if claim_timeout is None else claim_timeout
    jid = time.strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:6]
    data_file, tmp, job_p = queue / f"{jid}.data.json", queue / f"{jid}.tmp", queue / f"{jid}.job.json"
    try:        # everything from the first file on: a Ctrl-C at any point must not leave a job that runs unwatched
        payload = dict(data or {}, action=action, job_id=jid, submitted=now_iso())
        data_file.write_text(json.dumps(payload, ensure_ascii=True), encoding="ascii")
        t0 = time.time()
        # resolved paths: the bridge compares realpath(script) with its whitelisted folder (a custom WHYNOT_HOME whose
        # drive-letter case or symlinks differ must not be rejected)
        job = {"id": jid, "action": action, "data_file": str(data_file.resolve()),
               "submitted": payload["submitted"], "expires_at": _iso_utc(t0 + claim_s)}
        if lib is not None:
            job["lib"] = lib
        else:
            job["script"] = str(Path(script).resolve())
        tmp.write_text(json.dumps(job), encoding="utf-8")
        tmp.rename(job_p)      # atomic: the bridge never sees a half-written job
        return _wait(queue, jid, t0, claim_s, timeout, poll_s, app)
    except BaseException as e:  # Ctrl-C (or a write error): a job nobody waits for must not run later
        claimed = True          # unless proven otherwise the host may still act on it (also if this cleanup is interrupted)
        try:
            claimed = _bridge_has_job(queue, jid)
        except BaseException as e2:       # a second Ctrl-C inside the cleanup: the job may still run
            _flag_claimed(e2, True)
            _flag_claimed(e, True)
            raise
        _flag_claimed(e, claimed)
        raise


def _flag_claimed(e: BaseException, claimed: bool) -> None:
    """`wnc_claimed` on the exception: False = the job was taken back or never existed, it will not run."""
    with contextlib.suppress(Exception):
        e.wnc_claimed = claimed


def _bridge_has_job(queue: Path, jid: str) -> bool:
    """Take the job back. False: it will not run (cancelled, or it never became visible to the bridge). True: the
    bridge has (or had) it, so Premiere / After Effects may still act on it."""
    if _cancel(queue, jid):
        return False
    res_p = queue / f"{jid}.result.json"
    if res_p.exists():            # the bridge finished it (T2.15): nothing more will happen, the old project goes back,
        return not _host_finished(res_p)    # unless that result is the bridge's own "no reply" timeout
    if any((queue / f"{jid}.{s}").exists() for s in ("job.json", "claimed", "running")):
        return True
    _unlink(queue / f"{jid}.tmp", queue / f"{jid}.data.json")      # interrupted before the job file was renamed in
    return False


def _host_finished(res_p: Path) -> bool:
    """A result.json the HOST answered. False for the bridge's own 20-min "no reply from <host>" timeout (bridge.js
    writes it and frees the queue while ExtendScript may still be running and saving) and for a result still being
    written (unreadable): the job may still act, so it counts as claimed (T2.15 review m-3)."""
    try:
        r = json.loads(res_p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    return _host_finished_doc(r)


def _host_finished_doc(r) -> bool:
    """False for the bridge's own "no reply" timeout result (or anything that is not a result document)."""
    err = r.get("error") if isinstance(r, dict) else None
    return isinstance(r, dict) and not (isinstance(err, str) and err.startswith("no reply"))


CANCEL_TRIES, CANCEL_RETRY_S = 5, 0.1      # a Windows sharing lock on job.json passes within moments


def _cancel(queue: Path, jid: str) -> bool:
    """Take back a job the bridge has not claimed (True): it never runs. False = it was claimed meanwhile."""
    job_p, gone = queue / f"{jid}.job.json", queue / f"{jid}.job.cancelled"
    for i in range(CANCEL_TRIES):
        try:
            job_p.rename(gone)
            break
        except FileNotFoundError:
            return False                     # claimed (renamed by the bridge) or already gone
        except OSError:                      # a sharing violation (antivirus, the indexer, the panel reading it)
            if i == CANCEL_TRIES - 1:
                return False
            time.sleep(CANCEL_RETRY_S)
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
                out["error"] = r["error"]           # the bridge's own refusal (script not allowed, no reply)
            if not _host_finished_doc(r):
                # Gate 2 B3: the bridge's own "no reply from <host>" timeout freed the queue while ExtendScript may
                # still run and save: claimed, so ppro_build keeps the old project parked instead of restoring over it
                out["claimed"] = True
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
    def __init__(self, holder: dict, waited_s: float, queue: Path | None = None):
        self.holder, self.waited_s, self.queue = holder, waited_s, queue
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
    from .writer_lock import pid_alive, same_host
    if rec is None:
        return False
    if not rec:                                  # unreadable: being written right now, unless it is old
        try:
            return time.time() - (Path(queue) / LOCK_NAME).stat().st_mtime > 30
        except OSError:
            return True
    if same_host(rec):
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
    from .writer_lock import host_id, process_created
    queue = Path(queue)
    queue.mkdir(parents=True, exist_ok=True)
    lock = queue / LOCK_NAME
    t0 = time.time()
    while True:
        rec = {"pid": os.getpid(), "pid_created": process_created(os.getpid()), "host": socket.gethostname(),
               "host_id": host_id(), "what": what, "started_at": now_iso(), "expires_at": time.time() + hold_s}
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
                raise BuildLockBusy(held or {}, round(time.time() - t0, 1), queue)
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
    how = f"Let it finish (one build at a time per {app}), then run the command again."
    stuck = _stuck_holder(e.holder, e.queue)
    if stuck:
        how = f"{how} But {stuck}"
    return {"blocked": f"another build is running in {app}: {describe_lock(e.holder)}; waited {e.waited_s:g}s",
            "how": how}


def _stuck_holder(h: dict, queue: Path | None) -> str:
    """Guidance when the holder runs on this computer but is past its expected end, or cannot be told apart from a
    reused pid: such a lock is never taken over by itself (a long build must not be), so a hung holder needs a person."""
    from .writer_lock import same_host
    if not h or not same_host(h):
        return ""
    try:
        past = time.time() > float(h.get("expires_at") or 0)
    except (TypeError, ValueError):
        past = True
    if not past and h.get("pid_created"):
        return ""
    try:
        age = time.time() - _dt.datetime.fromisoformat(str(h.get("started_at"))).timestamp()
        held = f"has held it for {max(1, round(age / 60))} min"
    except (TypeError, ValueError):
        held = "has held it for an unknown time"
    lock = Path(queue) / LOCK_NAME if queue else f"<queue>/{LOCK_NAME}"
    why = "is past its expected end" if past else "cannot be told apart from a reused process id"
    return (f"process {h.get('pid')} {held} and {why}. If it is not a reel build that is still working, stop "
            f"process {h.get('pid')} or delete {lock}, then run the command again.")
