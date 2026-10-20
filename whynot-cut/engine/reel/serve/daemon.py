"""`reel serve` lifecycle (3.0 T6.2): run the daemon, start it once in the background, ask how it is, stop it.

    run(home)     the daemon itself (foreground). Takes the per-home instance lock <home>/bridge/serve.lock (a second
                  daemon on the same home exits with EXIT_LOCKED and touches nothing), binds one free port on both
                  loopbacks, 127.0.0.1 and ::1 (127.0.0.1 alone when IPv6 is unavailable; never anything else),
                  writes <home>/bridge/engine.json {port, token, pid, pid_created, version, protocol, started_at}
                  (atomic, user-only: security.write_engine_json), audits start and stop, turns require_bound_context
                  on (App.start), serves until an authenticated POST /shutdown (or Ctrl+C / SIGTERM), then closes the
                  app (bounded, every task awaited), drops the CEP queue calls that have not started, removes
                  engine.json only while it still names this pid, and releases the lock. A queue call stuck in submit
                  runs on a daemon thread and never holds the process. bridge/ and logs/ are made user-only
                  (security.private_dir), and so are serve.lock, serve.log and the audit logs. When the home is not
                  ~/.whynot-cut (the only home the UXP panel can compute), a discovery record with the same fields plus
                  `home` is written to ~/.whynot-cut/bridge/engine.json (same atomic user-only writer; never over a
                  live daemon's file) and removed, pid-guarded, on exit, BEFORE the home's own engine.json (so "own
                  record gone" implies "pointer gone"; a pointer that cannot be removed is audited). The start phases
                  are audited in one `startup` row, in ms since process entry (__main__.py marks entry and imports):
                  "entry=0ms imports=Nms lock=Nms listening=Nms engine.json=Nms" (names and numbers only: no path, no
                  token), so a slow start can be named from the audit log alone.
    ensure(home)  idempotent start (the SessionStart hook). A daemon whose engine.json pid is alive (same process start
                  time when recorded) and whose GET /status answers with the token within PROBE_TIMEOUT is returned as
                  is: no second daemon. A live pid whose /status TIMES OUT (it accepted the connection but answers late:
                  a loaded machine) is a slow daemon, not a dead one: it gets the longer SLOW_PROBE_TIMEOUTS probes
                  before a rival is ever spawned (a rival could only exit EXIT_LOCKED and turn a healthy daemon into
                  "not_answering"); one that answers none of them (~8 s in all) is still reported not_answering. A
                  refused connection gets no slow probes. Otherwise a stale file (dead pid) is removed and a detached
                  daemon is started with this interpreter (Windows CREATE_NEW_PROCESS_GROUP | CREATE_NO_WINDOW, with
                  CREATE_BREAKAWAY_FROM_JOB tried first so a hook's job object cannot take it down, never
                  DETACHED_PROCESS: with it Windows ignores CREATE_NO_WINDOW and the venv launcher's interpreter gets
                  a new VISIBLE console that kills the daemon when closed; POSIX start_new_session=True), then it
                  waits up to `wait` (ENSURE_WAIT) for engine.json + /status. Still
                  starting after that is {ok: true, state: starting}. Two ensures at once may both spawn; the instance
                  lock lets one daemon live and the other exits at once. A daemon of another plugin version or
                  protocol (left running by a plugin update, from a stale or deleted folder) is stopped through the
                  authenticated /shutdown and replaced: {state: restarted, previous_version, previous_protocol}; one
                  that does not stop is reported (not_answering), never killed.
    status(home)  reads engine.json and probes it (a slow daemon gets the slow probes too); changes nothing.
    stop(home)    POST /shutdown with the token, then waits (STOP_WAIT) for engine.json to go, for the discovery
                  record at ~/.whynot-cut to no longer record that daemon (pid + start time), and for the process to
                  exit; a stale file (dead pid) is removed, and so is its pointer. A pointer the exited daemon could
                  not remove is removed here (pid- and start-guarded: never another daemon's); if that fails too,
                  {state: stopped, discovery_left: true, warning, how} says so. A daemon that does not answer is
                  reported, never killed (its pid could belong to another program by now).
    A <home>/bridge/engine.json whose `home` field names another folder is the discovery copy of a daemon serving that
    other home (only ~/.whynot-cut gets one): ensure / status / stop of this home treat it as "no daemon here". It is
    never returned as running and never stopped; a new daemon for this home simply replaces it.
The detached daemon command (no cli.py needed, so it works before `reel serve` is registered):
    <this python> [-s] -B -P <plugin>/engine/reel/serve/__main__.py --foreground --home <engine home>
-P keeps the working directory off sys.path; cwd is the engine home (never the plugin folder, which is replaced on
update); WHYNOT_HOME is set to the engine home; stdout goes nowhere and stderr to <home>/logs/serve.log.
Nothing here prints, logs or returns the token.
"""
from __future__ import annotations

import asyncio
import http.client
import json
import os
import signal
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from lib import plat, writer_lock

from . import adapters, security
from .app import App

__all__ = ["run", "ensure", "status", "stop", "daemon_command", "InstanceLock", "PROBE_TIMEOUT", "ENSURE_WAIT",
           "STOP_WAIT", "EXIT_OK", "EXIT_FAILED", "EXIT_LOCKED", "SLOW_PROBE_TIMEOUTS", "mark_phase"]

PROBE_TIMEOUT = 0.3            # GET /status must answer within this
PROBE_TRIES = 3                # a live pid gets this many probes before a new daemon is tried (busy machine)
SLOW_PROBE_TIMEOUTS = (1.0, 2.0, 4.0)   # then these, when a probe TIMED OUT (a slow daemon, not a dead one)
ENSURE_WAIT = 1.0              # how long ensure() waits for a new daemon
STOP_WAIT = 3.0                # how long stop() waits for the daemon to exit
POLL_S = 0.05
LOG_CAP = 1024 * 1024          # serve.log (the daemon's stderr) is rotated once above this
EXIT_OK, EXIT_FAILED, EXIT_LOCKED = 0, 1, 3
MAIN = Path(__file__).resolve().with_name("__main__.py")

_children: list = []           # the daemons this process started (tests reap them; a real `reel` exits right away)
_PHASES: dict = {}             # start phase -> time.monotonic(): "entry" and "imports" (marked by __main__.py)


def mark_phase(name: str, at: float | None = None) -> None:
    """Record when a start phase was reached (the first mark wins). __main__.py marks "entry" (its first line) and
    "imports" (serve.daemon and everything it pulls in, loaded); _serve adds lock, listening and engine.json."""
    _PHASES.setdefault(name, time.monotonic() if at is None else at)


def _phase_line(phases: dict) -> str:
    """'entry=0ms imports=812ms ...': ms since process entry, in the order reached. Names and numbers only."""
    t0 = phases["entry"]
    return " ".join(f"{k}={max(0, round((t - t0) * 1000))}ms" for k, t in phases.items())


def _home(home) -> Path:
    return Path(home).expanduser() if home else plat.engine_home()


def _version() -> str:
    from lib.selfid import plugin_info
    return plugin_info()["version"]


# ---------------------------------------------------------------------------------------------- instance lock
class InstanceLock:
    """One daemon per engine home: an OS lock on <home>/bridge/serve.lock, held for the daemon's life and dropped by
    the OS when the process ends (so a crashed daemon never blocks the next one, and a reused pid never holds it)."""

    def __init__(self, home):
        self.path = Path(home) / "bridge" / "serve.lock"
        self._f = None

    def acquire(self) -> bool:
        security.private_dir(self.path.parent)
        f = os.fdopen(security.open_private(self.path, os.O_RDWR), "r+b")   # 0600: no other user can flock it
        try:
            if os.name == "nt":
                import msvcrt
                f.seek(0)
                msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            f.close()
            return False
        self._f = f
        try:
            security.private_file(self.path)       # Windows: user-only (a no-op when the folder already made it so)
        except OSError:
            pass
        return True

    def release(self) -> None:
        f, self._f = self._f, None
        if f is None:
            return
        try:
            if os.name == "nt":
                import msvcrt
                f.seek(0)
                msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(f.fileno(), fcntl.LOCK_UN)
        except OSError:
            pass
        finally:
            f.close()


# ------------------------------------------------------------------------------------------------------- run
def run(home=None, *, port: int = 0, version: str | None = None, ready=None, app_options: dict | None = None,
        install_signals: bool = True) -> int:
    """Run the daemon until it is asked to stop. `ready(stop)` is called once it serves and engine.json is written;
    `stop()` (thread-safe) stops it. Returns EXIT_OK, EXIT_LOCKED (another daemon serves this home) or EXIT_FAILED."""
    home = _home(home)
    try:
        return asyncio.run(_serve(home, port=port, version=version or _version(), ready=ready,
                                  app_options=app_options or {}, install_signals=install_signals))
    except KeyboardInterrupt:          # Ctrl+C in a foreground run: _serve's cleanup already ran
        return EXIT_OK


async def _serve(home: Path, *, port, version, ready, app_options, install_signals) -> int:
    now = time.monotonic()             # an in-process run (tests) has no __main__ marks: its phases start here
    phases = {"entry": _PHASES.get("entry", now), "imports": _PHASES.get("imports", now)}
    pid = os.getpid()
    token = security.make_token()
    audit = security.AuditLog(security.audit_log_path(home), token=token)
    lock = InstanceLock(home)
    try:
        locked = lock.acquire()
    except OSError as e:                   # the bridge folder or the lock file cannot be made user-only
        audit.log("daemon", outcome="failed", reason=f"pid {pid}: serve.lock ({type(e).__name__})")
        audit.log("startup", outcome="phases", reason=_phase_line(phases))
        return EXIT_FAILED
    if not locked:
        audit.log("daemon", outcome="refused", reason=f"pid {pid}: another reel serve already holds this engine home")
        audit.log("startup", outcome="phases", reason=_phase_line(phases))
        return EXIT_LOCKED
    phases["lock"] = time.monotonic()
    app = App(home=home, token=token, version=version, audit=audit, **app_options)
    started = False
    discovery = None
    try:
        port = await app.start(port)
        phases["listening"] = time.monotonic()
        record = {"port": port, "token": token, "pid": pid, "version": version,
                  "pid_created": writer_lock.process_created(pid),
                  "started_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
        try:
            security.private_dir(home / "logs")
            security.write_engine_json(home, **record)
        except (OSError, ValueError) as e:
            audit.log("daemon", outcome="failed", reason=f"engine.json could not be written ({type(e).__name__})")
            audit.log("startup", outcome="phases", reason=_phase_line(phases))
            return EXIT_FAILED
        phases["engine.json"] = time.monotonic()
        started = True
        audit.log("daemon", outcome="started", reason=f"{' '.join(app.listening)} pid {pid} version {version}")
        audit.log("startup", outcome="phases", reason=_phase_line(phases))
        discovery = _write_discovery(home, record, audit)
        loop = asyncio.get_running_loop()
        if install_signals and os.name != "nt":
            for sig in (signal.SIGTERM, signal.SIGHUP):
                try:
                    loop.add_signal_handler(sig, app.stop_requested.set)
                except (NotImplementedError, RuntimeError, ValueError):
                    pass
        if ready is not None:
            ready(lambda: loop.call_soon_threadsafe(app.stop_requested.set))
        await app.wait_stop()
        return EXIT_OK
    finally:
        await app.close()
        adapters.cancel_queued()
        if discovery is not None:          # the pointer first: once this home's record is gone, so is the pointer
            _remove_discovery(discovery, pid, audit)
        security.remove_engine_json(home, pid)
        if started:
            audit.log("daemon", outcome="stopped", reason=f"pid {pid}")
        lock.release()


# ----------------------------------------------------------------------------------------------- discovery
def default_home() -> Path:
    """The only engine home the UXP panel can compute by itself: os.homedir()/.whynot-cut."""
    return Path.home() / plat.HOME_NAME


def _same_dir(a: Path, b: Path) -> bool:
    try:
        return os.path.normcase(os.path.realpath(a)) == os.path.normcase(os.path.realpath(b))
    except (OSError, ValueError):
        return False


def _write_discovery(home: Path, record: dict, audit) -> Path | None:
    """When this daemon's home is not ~/.whynot-cut (WHYNOT_HOME, the plugin option, a legacy home), also write
    ~/.whynot-cut/bridge/engine.json with the same fields plus `home`, so the UXP panel finds it. Same atomic,
    user-only writer; removed pid-guarded on exit. A live daemon's file there (any daemon) is never touched.
    Returns the discovery home when it was written."""
    disc = default_home()
    if _same_dir(home, disc):
        return None
    where = f"~/{plat.HOME_NAME}/bridge/engine.json"
    try:
        cur = security.read_engine_json(disc)
        if cur is not None and _alive(cur):
            audit.log("discovery", outcome="skipped", reason=f"{where} belongs to a running daemon (pid {cur.get('pid')})")
            return None
        security.write_engine_json(disc, **record, home=str(home))
    except (OSError, ValueError) as e:
        audit.log("discovery", outcome="failed", reason=f"{where} ({type(e).__name__})")
        return None
    audit.log("discovery", outcome="written", reason=f"{where} points at this engine home")
    return disc


def _discovery_for(home: Path) -> Path | None:
    """The home whose engine.json may hold this home's discovery record: ~/.whynot-cut, unless `home` is it."""
    disc = default_home()
    return None if _same_dir(home, disc) else disc


def _points_at(disc: Path | None, home: Path, pid, pid_created) -> bool:
    """True while `disc`'s engine.json is the discovery record of this home's daemon (same pid, process start time
    and home)."""
    if disc is None:
        return False
    cur = security.read_engine_json(disc)
    other = (cur or {}).get("home")
    return (cur is not None and cur.get("pid") == pid and cur.get("pid_created") == pid_created
            and isinstance(other, str) and bool(other) and _same_dir(Path(other), home))


def _remove_discovery(disc: Path, pid: int, audit) -> None:
    """Remove this daemon's discovery record (pid-guarded). When it cannot be removed (a sharing violation outlasting
    every retry: an antivirus scan, a reader holding it), that is audited; `reel serve --stop` removes it once this
    process has exited, and the next daemon's start replaces it."""
    security.remove_engine_json(disc, pid)
    cur = security.read_engine_json(disc)
    if cur is not None and cur.get("pid") == pid:
        audit.log("discovery", outcome="failed",
                  reason=f"~/{plat.HOME_NAME}/bridge/engine.json could not be removed (pid {pid}); "
                         "reel serve --stop or the next start removes it")


# ------------------------------------------------------------------------------------------------- probing
def _own_record(home: Path) -> dict | None:
    """<home>/bridge/engine.json when it is this home's daemon's record; None when missing or when it is the discovery
    copy of a daemon serving another home (its `home` field names another folder)."""
    info = security.read_engine_json(home)
    if info is None or "home" not in info:
        return info
    other = info.get("home")
    if isinstance(other, str) and other and _same_dir(Path(other), Path(home)):
        return info
    return None


def _alive(info: dict) -> bool:
    return writer_lock.pid_alive(info.get("pid"), info.get("pid_created"))


def _http(info: dict, method: str, path: str, timeout: float):
    """(status, parsed JSON body or None) of one authenticated request to the daemon, or (None, None)."""
    code, body, _ = _request(info, method, path, timeout)
    return code, body


def _request(info: dict, method: str, path: str, timeout: float):
    """_http plus whether it failed by TIMING OUT (the daemon is there but slow) rather than by a refusal, a broken
    connection or a bad answer: (status, body, timed_out)."""
    port, token = info.get("port"), info.get("token")
    if (isinstance(port, bool) or not isinstance(port, int) or not 0 < port < 65536
            or not security.token_shape_ok(token)):
        return None, None, False
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=timeout)
    try:
        conn.request(method, path, body=b"" if method == "POST" else None,
                     headers={"Authorization": f"Bearer {token}"})
        r = conn.getresponse()
        raw = r.read(65536)
        try:
            body = json.loads(raw)
        except ValueError:
            body = None
        return r.status, body, False
    except TimeoutError:               # socket.timeout: connected (or queued in the backlog) but no answer in time
        return None, None, True
    except (OSError, http.client.HTTPException):
        return None, None, False
    finally:
        conn.close()


def _probe_once(info: dict, timeout: float) -> tuple[dict | None, bool]:
    """(the /status answer when it is the daemon engine.json names (same pid and port) else None, timed out)."""
    code, body, timed_out = _request(info, "GET", "/status", timeout)
    if code == 200 and isinstance(body, dict) and body.get("pid") == info.get("pid") \
            and body.get("port") == info.get("port"):
        return body, False
    return None, timed_out


def _probe(info: dict, tries: int = 1) -> dict | None:
    """The daemon's /status answer when it is the daemon engine.json names (same pid and port), else None."""
    for _ in range(max(1, tries)):
        st, _ = _probe_once(info, PROBE_TIMEOUT)
        if st is not None:
            return st
    return None


def _probe_live(info: dict) -> dict | None:
    """_probe for a pid known to be alive: PROBE_TRIES short probes, then, when one of them TIMED OUT (the daemon took
    the connection but answers late: a loaded machine), one probe per SLOW_PROBE_TIMEOUTS before it is given up on
    (bounded: ~8 s in all). A slow daemon is not a dead one; a rival spawned next to it only exits EXIT_LOCKED. A
    refused connection or a wrong answer ends the slow probes at once (nothing slow is listening there)."""
    slow = False
    for _ in range(PROBE_TRIES):
        st, timed_out = _probe_once(info, PROBE_TIMEOUT)
        if st is not None:
            return st
        slow = slow or timed_out
    if not slow:
        return None
    for t in SLOW_PROBE_TIMEOUTS:
        st, timed_out = _probe_once(info, t)
        if st is not None or not timed_out:
            return st
    return None


def _doc(info: dict, st: dict, state: str, **extra) -> dict:
    out = {"ok": True, "running": True, "state": state, "pid": info.get("pid"), "port": info.get("port"),
           "version": info.get("version"), "protocol": info.get("protocol"), "started_at": info.get("started_at"),
           "sessions": len(st.get("sessions") or []), "uptime_s": st.get("uptime_s")}
    out.update(extra)
    return out


# ------------------------------------------------------------------------------------------------- ensure
def daemon_command(home) -> list[str]:
    cmd = [sys.executable]
    if sys.flags.no_user_site:
        cmd.append("-s")
    return cmd + ["-B", "-P", str(MAIN), "--foreground", "--home", str(home)]


def _rotate_log(path: Path) -> None:
    try:
        if path.stat().st_size > LOG_CAP:
            os.replace(path, path.with_name(path.name + ".1"))
    except OSError:
        pass


def _popen(cmd, **kw):
    """subprocess.Popen for the daemon command only (tests replace this, not the module-wide Popen)."""
    return subprocess.Popen(cmd, **kw)


def _spawn(home: Path):
    """Start a detached daemon for `home`; returns its Popen (on Windows a venv's python.exe may be a launcher whose
    pid differs from the daemon's: engine.json holds the daemon's own pid)."""
    home = Path(home)
    logs = security.private_dir(home / "logs")
    log_path = logs / "serve.log"
    _rotate_log(log_path)
    env = dict(os.environ, WHYNOT_HOME=str(home), PYTHONDONTWRITEBYTECODE="1", PYTHONUTF8="1",
               PYTHONIOENCODING="utf-8")
    cmd = daemon_command(home)
    with os.fdopen(security.open_private(log_path, os.O_WRONLY | os.O_APPEND), "ab") as err:
        security.private_file(log_path)
        kw = {"stdin": subprocess.DEVNULL, "stdout": subprocess.DEVNULL, "stderr": err, "cwd": str(home),
              "env": env, "close_fds": True}
        if os.name == "nt":
            flags = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW   # a hidden console of its own
            try:
                proc = _popen(cmd, creationflags=flags | subprocess.CREATE_BREAKAWAY_FROM_JOB, **kw)
            except OSError:            # the job (e.g. a hook runner's) forbids breakaway: start inside it
                proc = _popen(cmd, creationflags=flags, **kw)
        else:
            proc = _popen(cmd, start_new_session=True, **kw)
    _children.append(proc)
    return proc


def ensure(home=None, *, wait: float = ENSURE_WAIT) -> dict:
    """The running daemon ({ok, running, state: running, started: false, pid, port, ...}), else start one."""
    home = _home(home)
    info = _own_record(home)
    previous: dict = {}
    if info is not None:
        if _alive(info):
            st = _probe_live(info)         # a slow daemon gets its slow probes here, before any rival is spawned
            if st is not None:
                old_version, old_protocol = st.get("daemon_version", info.get("version")), st.get("protocol")
                if old_version == _version() and old_protocol == security.PROTOCOL:
                    return _doc(info, st, "running", started=False)
                # a daemon of another plugin version (or protocol) would keep running from a stale or deleted
                # plugin folder: stop it (authenticated, never killed), then start this version's
                res = stop(home)
                if not res.get("ok"):
                    return {"ok": False, "running": True, "state": "not_answering", "pid": info.get("pid"),
                            "version": old_version,
                            "error": f"reel serve {old_version} (pid {info.get('pid')}) is not this plugin's version "
                                     f"({_version()}) and did not stop: {res.get('error', 'no answer')}",
                            "how": res.get("how") or f"end process {info.get('pid')} (Task Manager / kill), then "
                                                     "run: reel serve --ensure"}
                previous = {"previous_version": old_version, "previous_protocol": old_protocol}
        else:
            security.remove_engine_json(home, info.get("pid"))
    proc = _spawn(home)
    deadline = time.monotonic() + max(0.0, float(wait))
    while True:
        cur = _own_record(home)
        if cur is not None and cur != info and _alive(cur):
            st = _probe(cur)
            if st is not None:
                return _doc(cur, st, "restarted" if previous else "running", started=True, **previous)
        code = proc.poll()
        if code is not None:
            cur = _own_record(home)
            if cur is not None and _alive(cur):    # the record probed above already had its slow probes
                st = _probe(cur, PROBE_TRIES) if cur == info else _probe_live(cur)
                if st is not None:                 # another ensure's daemon won the instance lock
                    return _doc(cur, st, "running", started=False)
            if code == EXIT_LOCKED:
                pid = (cur or {}).get("pid", "?")
                return {"ok": False, "running": False, "state": "not_answering",
                        "error": f"reel serve (pid {pid}) holds this engine home but does not answer",
                        "how": f"run: reel serve --stop; if it stays stuck, end process {pid} (Task Manager / kill), "
                               "then run: reel serve --ensure"}
            return {"ok": False, "running": False, "state": "failed",
                    "error": f"reel serve exited while starting (exit code {code})",
                    "how": f"see {home / 'logs' / 'serve.log'} and {security.audit_log_path(home)}, then run: "
                           "reel doctor"}
        if time.monotonic() >= deadline:
            return {"ok": True, "running": False, "state": "starting", "started": True, "pid": proc.pid,
                    "how": "it is still starting: reel serve --status shows when it answers"}
        time.sleep(POLL_S)


# ------------------------------------------------------------------------------------------------- status / stop
def status(home=None) -> dict:
    home = _home(home)
    info = _own_record(home)
    if info is None:
        return {"ok": True, "running": False, "state": "stopped"}
    if not _alive(info):
        return {"ok": True, "running": False, "state": "stale", "pid": info.get("pid"),
                "how": "reel serve --ensure starts a new daemon (it replaces the stale engine.json)"}
    st = _probe_live(info)
    if st is None:
        return {"ok": False, "running": False, "state": "not_answering", "pid": info.get("pid"),
                "port": info.get("port"), "error": f"reel serve (pid {info.get('pid')}) does not answer",
                "how": "run: reel serve --stop, then reel serve --ensure"}
    return _doc(info, st, "running")


def stop(home=None, *, wait: float = STOP_WAIT) -> dict:
    home = _home(home)
    info = _own_record(home)
    if info is None:
        return {"ok": True, "running": False, "state": "not_running"}
    pid, created = info.get("pid"), info.get("pid_created")
    disc = _discovery_for(home)        # its pointer at ~/.whynot-cut, when this home is not that one
    if not _alive(info):
        if _points_at(disc, home, pid, created):
            security.remove_engine_json(disc, pid, pid_created=created)
        security.remove_engine_json(home, pid)
        return {"ok": True, "running": False, "state": "stale_removed", "pid": pid}
    code, _ = _http(info, "POST", "/shutdown", max(PROBE_TIMEOUT, 1.0))
    if code != 202:
        return {"ok": False, "running": False, "state": "not_answering", "pid": pid, "port": info.get("port"),
                "error": f"reel serve (pid {pid}) did not accept the shutdown request"
                         + (f" (HTTP {code})" if code else ""),
                "how": f"end process {pid} (Task Manager / kill), then run: reel serve --status"}
    own = _in_process(pid)             # an in-process daemon (tests): its process does not exit
    where = f"~/{plat.HOME_NAME}/bridge/engine.json"
    deadline = time.monotonic() + max(0.0, float(wait))
    while True:
        gone = (security.read_engine_json(home) or {}).get("pid") != pid
        exited = None if own else (not _alive(info) or (gone and _zombie(pid)))   # a zombie only once it let go
        pointer = gone and _points_at(disc, home, pid, created)
        if pointer and exited:         # the daemon exited without removing it (its retries ran out): a dead pid's
            security.remove_engine_json(disc, pid, pid_created=created)     # record, removed pid- and start-guarded
            pointer = _points_at(disc, home, pid, created)
        if gone and not pointer and exited is not False:
            return {"ok": True, "running": False, "state": "stopped", "pid": pid, "exited": exited}
        if time.monotonic() >= deadline:
            if gone and pointer and exited:
                return {"ok": True, "running": False, "state": "stopped", "pid": pid, "exited": True,
                        "discovery_left": True,
                        "warning": f"{where} still points at the stopped daemon (pid {pid}) and could not be removed "
                                   "(another program holds it open)",
                        "how": f"reel serve --ensure replaces it; or delete {where} once nothing holds it open"}
            return {"ok": False, "running": not gone, "state": "stopping", "pid": pid,
                    "error": f"reel serve (pid {pid}) did not remove {where} within {wait:g}s"
                             if gone and pointer and exited is None else
                             f"reel serve (pid {pid}) did not exit within {wait:g}s",
                    "how": f"run: reel serve --status; if it is still there, end process {pid} (Task Manager / kill)"}
        time.sleep(POLL_S)


def _in_process(pid) -> bool:
    return pid == os.getpid()


def _zombie(pid) -> bool:
    """Has POSIX process `pid` ended but not been reaped yet (a zombie)? Its parent (a test, a launcher) may not have
    waited for it, and os.kill(pid, 0) and `ps` still report a zombie; it runs no code and holds no port. Windows has
    none. Linux reads /proc/<pid>/stat, macOS / BSD runs ps with fixed arguments (no shell)."""
    if os.name == "nt":
        return False
    try:
        pid = int(pid)
    except (TypeError, ValueError):
        return False
    if pid <= 0:
        return False
    try:                               # the state is the first field after the ")" that closes the command name
        stat = Path(f"/proc/{pid}/stat").read_text(encoding="ascii", errors="replace")
        return stat.rpartition(")")[2].split()[:1] == ["Z"]
    except OSError:
        if os.path.isdir("/proc/self"):  # Linux: no stat file = no such process
            return False
    ps = next((p for p in ("/bin/ps", "/usr/bin/ps") if os.path.exists(p)), None)
    if ps is None:
        return False
    try:
        out = subprocess.run([ps, "-o", "stat=", "-p", str(pid)], stdin=subprocess.DEVNULL, capture_output=True,
                             text=True, timeout=2.0).stdout
    except (OSError, subprocess.SubprocessError):
        return False
    return out.strip().startswith("Z")
