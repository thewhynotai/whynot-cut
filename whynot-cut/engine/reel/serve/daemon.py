"""`reel serve` lifecycle (3.0 T6.2): run the daemon, start it once in the background, ask how it is, stop it.

    run(home)     the daemon itself (foreground). Takes the per-home instance lock <home>/bridge/serve.lock (a second
                  daemon on the same home exits with EXIT_LOCKED and touches nothing), binds 127.0.0.1:<free port>,
                  writes <home>/bridge/engine.json {port, token, pid, pid_created, version, protocol, started_at}
                  (atomic, user-only: security.write_engine_json), audits start and stop, turns require_bound_context
                  on (App.start), serves until an authenticated POST /shutdown (or Ctrl+C / SIGTERM), then closes the
                  app (bounded, every task awaited), drops the CEP queue calls that have not started, removes
                  engine.json only while it still names this pid, and releases the lock. A queue call stuck in submit
                  runs on a daemon thread and never holds the process. bridge/ and logs/ are made user-only
                  (security.private_dir), and so are serve.lock, serve.log and the audit logs. When the home is not
                  ~/.whynot-cut (the only home the UXP panel can compute), a discovery record with the same fields plus
                  `home` is written to ~/.whynot-cut/bridge/engine.json (same atomic user-only writer; never over a
                  live daemon's file) and removed, pid-guarded, on exit.
    ensure(home)  idempotent start (the SessionStart hook). A daemon whose engine.json pid is alive (same process start
                  time when recorded) and whose GET /status answers with the token within PROBE_TIMEOUT is returned as
                  is: no second daemon. Otherwise a stale file (dead pid) is removed and a detached daemon is started
                  with this interpreter (Windows DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP | CREATE_NO_WINDOW, with
                  CREATE_BREAKAWAY_FROM_JOB tried first so a hook's job object cannot take it down; POSIX
                  start_new_session=True), then it waits up to `wait` (ENSURE_WAIT) for engine.json + /status. Still
                  starting after that is {ok: true, state: starting}. Two ensures at once may both spawn; the instance
                  lock lets one daemon live and the other exits at once. A daemon of another plugin version or
                  protocol (left running by a plugin update, from a stale or deleted folder) is stopped through the
                  authenticated /shutdown and replaced: {state: restarted, previous_version, previous_protocol}; one
                  that does not stop is reported (not_answering), never killed.
    status(home)  reads engine.json and probes it; changes nothing.
    stop(home)    POST /shutdown with the token, then waits (STOP_WAIT) for engine.json to go and the process to
                  exit; a stale file (dead pid) is removed. A daemon that does not answer is reported, never killed
                  (its pid could belong to another program by now).
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
           "STOP_WAIT", "EXIT_OK", "EXIT_FAILED", "EXIT_LOCKED"]

PROBE_TIMEOUT = 0.3            # GET /status must answer within this
PROBE_TRIES = 3                # a live pid gets this many probes before a new daemon is tried (busy machine)
ENSURE_WAIT = 1.0              # how long ensure() waits for a new daemon
STOP_WAIT = 3.0                # how long stop() waits for the daemon to exit
POLL_S = 0.05
LOG_CAP = 1024 * 1024          # serve.log (the daemon's stderr) is rotated once above this
EXIT_OK, EXIT_FAILED, EXIT_LOCKED = 0, 1, 3
MAIN = Path(__file__).resolve().with_name("__main__.py")

_children: list = []           # the daemons this process started (tests reap them; a real `reel` exits right away)


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
    pid = os.getpid()
    token = security.make_token()
    audit = security.AuditLog(security.audit_log_path(home), token=token)
    lock = InstanceLock(home)
    try:
        locked = lock.acquire()
    except OSError as e:                   # the bridge folder or the lock file cannot be made user-only
        audit.log("daemon", outcome="failed", reason=f"pid {pid}: serve.lock ({type(e).__name__})")
        return EXIT_FAILED
    if not locked:
        audit.log("daemon", outcome="refused", reason=f"pid {pid}: another reel serve already holds this engine home")
        return EXIT_LOCKED
    app = App(home=home, token=token, version=version, audit=audit, **app_options)
    started = False
    discovery = None
    try:
        port = await app.start(port)
        record = {"port": port, "token": token, "pid": pid, "version": version,
                  "pid_created": writer_lock.process_created(pid),
                  "started_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
        try:
            security.private_dir(home / "logs")
            security.write_engine_json(home, **record)
        except (OSError, ValueError) as e:
            audit.log("daemon", outcome="failed", reason=f"engine.json could not be written ({type(e).__name__})")
            return EXIT_FAILED
        started = True
        audit.log("daemon", outcome="started", reason=f"127.0.0.1:{port} pid {pid} version {version}")
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
        security.remove_engine_json(home, pid)
        if discovery is not None:
            security.remove_engine_json(discovery, pid)
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
    port, token = info.get("port"), info.get("token")
    if (isinstance(port, bool) or not isinstance(port, int) or not 0 < port < 65536
            or not security.token_shape_ok(token)):
        return None, None
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
        return r.status, body
    except (OSError, http.client.HTTPException):
        return None, None
    finally:
        conn.close()


def _probe(info: dict, tries: int = 1) -> dict | None:
    """The daemon's /status answer when it is the daemon engine.json names (same pid and port), else None."""
    for _ in range(max(1, tries)):
        code, body = _http(info, "GET", "/status", PROBE_TIMEOUT)
        if code == 200 and isinstance(body, dict) and body.get("pid") == info.get("pid") \
                and body.get("port") == info.get("port"):
            return body
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
            flags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW
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
            st = _probe(info, PROBE_TRIES)
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
            if cur is not None and _alive(cur):
                st = _probe(cur, PROBE_TRIES)
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
    st = _probe(info, PROBE_TRIES)
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
    pid = info.get("pid")
    if not _alive(info):
        security.remove_engine_json(home, pid)
        return {"ok": True, "running": False, "state": "stale_removed", "pid": pid}
    code, _ = _http(info, "POST", "/shutdown", max(PROBE_TIMEOUT, 1.0))
    if code != 202:
        return {"ok": False, "running": False, "state": "not_answering", "pid": pid, "port": info.get("port"),
                "error": f"reel serve (pid {pid}) did not accept the shutdown request"
                         + (f" (HTTP {code})" if code else ""),
                "how": f"end process {pid} (Task Manager / kill), then run: reel serve --status"}
    own = pid == os.getpid()           # an in-process daemon (tests): its process does not exit
    deadline = time.monotonic() + max(0.0, float(wait))
    while True:
        gone = (security.read_engine_json(home) or {}).get("pid") != pid
        exited = None if own else not _alive(info)
        if gone and exited is not False:
            return {"ok": True, "running": False, "state": "stopped", "pid": pid, "exited": exited}
        if time.monotonic() >= deadline:
            return {"ok": False, "running": not gone, "state": "stopping", "pid": pid,
                    "error": f"reel serve (pid {pid}) did not exit within {wait:g}s",
                    "how": f"run: reel serve --status; if it is still there, end process {pid} (Task Manager / kill)"}
        time.sleep(POLL_S)
