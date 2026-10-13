"""One writer per client folder (3.0 T1.8): `<client>/output/.whynot-lock`, a SESSION LEASE.

Two Claude sessions once took turns on one client folder over minutes and hours and their work crossed. The first
`reel` command of a session that writes into a client folder creates this lease (cli.py decides which commands
write); every later writing command of the same session refreshes it (touch + `command`), so the session keeps the
client between its commands. A writing command of ANOTHER session gets `{"blocked", "how"}` and exit 2.

The lease is JSON `{session_id, pid, pid_created, host, host_id, started_at, updated_at, command}`, created atomically
(O_CREAT | O_EXCL). `pid` is the holder that must stay alive:
  * CLAUDE_PID, the long-lived Claude Code process of the session, when it is set and running: a lease that
    outlives single commands;
  * else the command's own process (an editor at a plain terminal): the lock lasts for that command only and is
    removed when it ends.
It is stale, and the next writer takes it over with a line in output/logs/pipeline.log, when
  * its holder process is no longer running on this computer (`host_id`, else `host` for an older lease); a pid
    whose creation time differs from `pid_created` is a reused pid, so the holder is gone too; or
  * no writing command touched it for 2 h (also the only test for a lease from another computer on a shared
    drive). A long command touches it every 10 min while it runs.
A lease ends only by staleness, by `reel lock --release` (the lead, on the editor's word), or by the SessionEnd hook
(hooks/session_end.py), which removes the ending session's own lease only. A single command never removes a lease.
Same Claude Code process, new session id (3.0 T3.4, seen live with CLI 2.1.295): /clear ends session A (SessionEnd,
reason clear) and starts session B in the SAME process (CLAUDE_PID unchanged); Bash then sees CLAUDE_CODE_SESSION_ID=B.
SessionEnd hooks share a 1.5 s budget, so A's lease may survive /clear with a live holder. So B's SessionStart (source
clear or resume, 10 s budget) re-keys a lease whose holder is its own Claude Code process (same pid, same start time,
this computer) to B, with a log line (`rekey`, hooks/session_context.py). That is the only takeover of a live lease
(fix round 1): a writing command under a new session id at any other time is another writer and is refused (T1.8),
even in the same process (agent-team teammates must not pass the lease back and forth).

Session id (who "one writer" is), first match wins:
  WHYNOT_LOCK_SESSION    set by a writing `reel` for the processes it starts (a nested reel is the same writer)
  CLAUDE_SESSION_ID      if a host exports it
  CLAUDE_CODE_SESSION_ID what Claude Code gives Bash/PowerShell commands (the lead and its subagents share it, so
                         they are one writer: re-entrant, never blocked by each other)
  CLAUDE_PID             the Claude Code process, when only that is exported: "claude-pid-<pid>"
  else "pid-<pid of this reel>": never re-entrant, which errs on the safe side (blocks, never merges two writers).

Stdlib only: imported by cli.py (`lib.writer_lock`) and by the hooks (`writer_lock`).
"""
from __future__ import annotations

import functools
import hashlib
import json
import os
import re
import socket
import subprocess
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

LOCK_REL = "output/.whynot-lock"
LOG_REL = "output/logs/pipeline.log"
STALE_AFTER_S = 2 * 3600
TOUCH_EVERY_S = 600
WRITING_GRACE_S = 30            # an unreadable lock younger than this is being written right now
ENV = "WHYNOT_LOCK_SESSION"
IS_WIN = os.name == "nt"
IS_MAC = sys.platform == "darwin"


@functools.lru_cache(maxsize=1)
def _host_ids() -> tuple:
    """(host_id, the same id as 3.0 betas wrote it or None). macOS: the hardware UUID (ioreg), stored only as a short
    sha256 (T2.15 review m-6: the lease sits in client folders that are shared and synced; the beta wrote it in
    clear), else the Bonjour LocalHostName (scutil); elsewhere the computer name."""
    if IS_MAC:
        for cmd, pat, hashed in (
                (["ioreg", "-rd1", "-c", "IOPlatformExpertDevice"], r'"IOPlatformUUID"\s*=\s*"([^"]+)"', True),
                (["scutil", "--get", "LocalHostName"], r"^\s*(\S+)\s*$", False)):
            try:
                out = subprocess.run(cmd, capture_output=True, text=True, timeout=5).stdout or ""
            except (OSError, subprocess.SubprocessError):
                continue
            m = re.search(pat, out, re.M)
            if m:
                v = m.group(1)
                if hashed:
                    return "mac:" + hashlib.sha256(v.encode("utf-8")).hexdigest()[:16], "mac:" + v
                return "mac:" + v, None
    return socket.gethostname(), None


def host_id() -> str:
    """This computer, stably (3.0 T2.15): a Mac's hostname changes with the network, which would make a dead holder
    look like another computer's and disable the takeover (see _host_ids)."""
    return _host_ids()[0]


host_id.cache_clear = _host_ids.cache_clear       # type: ignore[attr-defined]   (tests clear the lookup)


def same_host(rec: dict) -> bool:
    """Was this lock record written on this computer? `host_id` when it has one (also the unhashed hardware UUID a
    3.0 beta lease holds), else (older records) `host`."""
    hid = rec.get("host_id")
    if not hid:
        return rec.get("host") == socket.gethostname()
    legacy = _host_ids()[1]
    return hid == host_id() or (legacy is not None and hid == legacy)


def lock_path(root) -> Path:
    return Path(root).expanduser() / LOCK_REL


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def session_id(env=None) -> str:
    env = os.environ if env is None else env
    for k in (ENV, "CLAUDE_SESSION_ID", "CLAUDE_CODE_SESSION_ID"):
        if (env.get(k) or "").strip():
            return env[k].strip()
    if (env.get("CLAUDE_PID") or "").strip().isdigit():
        return f"claude-pid-{env['CLAUDE_PID'].strip()}"
    return f"pid-{os.getpid()}"


def holder_pid(env=None) -> int:
    """The process whose life is the lease: the session's Claude Code process (CLAUDE_PID) when it runs, else ours."""
    env = os.environ if env is None else env
    v = (env.get("CLAUDE_PID") or "").strip()
    return int(v) if v.isdigit() and pid_alive(int(v)) else os.getpid()


def same_process(rec: dict, env=None) -> bool:
    """Is this lease held by the Claude Code process this command runs under (CLAUDE_PID: alive, same start time, this
    computer)? Used by `rekey` only, at SessionStart after /clear or /resume."""
    env = os.environ if env is None else env
    v = (env.get("CLAUDE_PID") or "").strip()
    if not v.isdigit() or not isinstance(rec, dict) or str(rec.get("pid")) != v or not same_host(rec):
        return False
    return pid_alive(int(v), rec.get("pid_created"))


# --------------------------------------------------------------------------- processes (Windows has no kill(pid, 0))
def _win_open(pid: int):
    """(kernel32, handle or None, error code)."""
    import ctypes
    from ctypes import wintypes
    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    k32.OpenProcess.restype = wintypes.HANDLE
    k32.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
    k32.GetExitCodeProcess.argtypes = (wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD))
    k32.GetProcessTimes.argtypes = (wintypes.HANDLE,) + (ctypes.POINTER(wintypes.FILETIME),) * 4
    k32.CloseHandle.argtypes = (wintypes.HANDLE,)
    h = k32.OpenProcess(0x1000, False, pid)          # PROCESS_QUERY_LIMITED_INFORMATION
    return k32, h, (0 if h else ctypes.get_last_error())


def _running(pid: int) -> bool:
    if IS_WIN:
        import ctypes
        from ctypes import wintypes
        k32, h, err = _win_open(pid)
        if not h:
            return err == 5                           # ERROR_ACCESS_DENIED: it exists (another user's process)
        try:
            code = wintypes.DWORD()
            return not k32.GetExitCodeProcess(h, ctypes.byref(code)) or code.value == 259   # STILL_ACTIVE
        finally:
            k32.CloseHandle(h)
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True


def process_created(pid) -> str | None:
    """When process `pid` started, as an opaque string (None: unknown). Same pid + other start = a reused pid."""
    try:
        pid = int(pid)
        if IS_WIN:
            import ctypes
            from ctypes import wintypes
            k32, h, _ = _win_open(pid)
            if not h:
                return None
            try:
                t = [wintypes.FILETIME() for _ in range(4)]
                if not k32.GetProcessTimes(h, *(ctypes.byref(x) for x in t)):
                    return None
                return str((t[0].dwHighDateTime << 32) | t[0].dwLowDateTime)
            finally:
                k32.CloseHandle(h)
        stat = Path(f"/proc/{pid}/stat")
        if stat.exists():                             # Linux: field 22 = start time in clock ticks since boot
            return stat.read_text().rsplit(")", 1)[1].split()[19]
        r = subprocess.run(["ps", "-o", "lstart=", "-p", str(pid)], capture_output=True, text=True, timeout=5)
        return r.stdout.strip() or None               # macOS
    except Exception:  # noqa: BLE001  (unknown start time: liveness alone decides)
        return None


def pid_alive(pid, created=None) -> bool:
    """Is process `pid` running on this computer (and, given `created`, still the same process)?"""
    try:
        pid = int(pid)
    except (TypeError, ValueError):
        return False
    if pid <= 0 or not _running(pid):
        return False
    if created:
        now = process_created(pid)
        if now is not None and now != str(created):
            return False
    return True


# --------------------------------------------------------------------------- the lock file
def read(root) -> dict | None:
    """The lock record, None when there is no lock; {} when the file exists but cannot be read as a record."""
    try:
        txt = lock_path(root).read_text(encoding="utf-8")
    except FileNotFoundError:
        return None
    except OSError:
        return {}
    try:
        rec = json.loads(txt)
    except ValueError:
        return {}
    return rec if isinstance(rec, dict) else {}


def _age_s(root) -> float | None:
    try:
        return time.time() - lock_path(root).stat().st_mtime
    except OSError:
        return None


def stale_reason(root, rec: dict | None = None) -> str | None:
    """Why the current lock may be taken over (None: it is held)."""
    rec = read(root) if rec is None else rec
    if rec is None:
        return None
    age = _age_s(root)
    if age is None:
        return "the lock is gone"
    if not rec:
        return f"unreadable lock file, {age / 60:.0f} min old" if age > WRITING_GRACE_S else None
    if same_host(rec) and not pid_alive(rec.get("pid"), rec.get("pid_created")):
        reused = pid_alive(rec.get("pid"))
        return (f"its process {rec.get('pid')} on {rec.get('host')} is no longer running"
                + (" (the process id now belongs to another program)" if reused else ""))
    if age > STALE_AFTER_S:
        return f"no writing command for over {STALE_AFTER_S // 3600} h ({age / 3600:.1f} h)"
    return None


def describe(rec: dict) -> str:
    return f"{rec.get('command') or 'a writing command'}, since {rec.get('started_at') or '?'}"


def client_log(root, msg: str):
    line = f"[{now_iso()}] {msg}"
    print(line, file=sys.stderr)
    try:
        f = Path(root).expanduser() / LOG_REL
        f.parent.mkdir(parents=True, exist_ok=True)
        with open(f, "a", encoding="utf-8") as fh:
            fh.write(line + "\n")
    except OSError:
        pass


class Busy(Exception):
    """Another session holds the client's lease."""

    def __init__(self, root, rec: dict):
        super().__init__(describe(rec))
        self.root, self.rec = Path(root), rec

    def refusal(self) -> dict:
        r = self.rec
        who = f"session {str(r.get('session_id') or '?')[:12]}, process {r.get('pid')} on {r.get('host')}"
        return {"blocked": f"another session is working in this client folder ({describe(r)}; {who}). One writer per "
                           f"client folder: this command would collide with its work.",
                "how": "Stop and tell the editor; never release another session's lock yourself. Read-only commands "
                       "still work (`reel next`, `reel status`, `reel inbox --no-refresh`, `reel lock --status`). The "
                       "lock ends when that session ends, after 2 h without a writing command from it, or when the "
                       "editor says that session is finished and the lead runs `reel lock --release`.",
                "lock": str(lock_path(self.root)), "holder": r}


class Lock:
    """This command's hold on the client: touches the lease while the command runs; removes the lock at the end only
    when the lock lives just for this command (holder = this process, no Claude Code session process)."""

    def __init__(self, root, sid: str, per_command: bool):
        self.root, self.sid, self.per_command = Path(root), sid, per_command
        self._stop = threading.Event()
        threading.Thread(target=self._touch, name="whynot-lock-touch", daemon=True).start()

    def _mine(self) -> bool:
        return (read(self.root) or {}).get("session_id") == self.sid

    def _touch(self):
        while not self._stop.wait(TOUCH_EVERY_S):
            if self._mine():
                try:
                    os.utime(lock_path(self.root))
                except OSError:
                    pass

    def release(self):
        self._stop.set()
        rec = read(self.root) or {}
        if self.per_command and rec.get("session_id") == self.sid and rec.get("pid") == os.getpid():
            try:
                lock_path(self.root).unlink()
            except OSError:
                pass
        self.per_command = False

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.release()


def _create(path: Path, rec: dict) -> bool:
    try:
        fd = os.open(str(path), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
    except FileExistsError:
        return False
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(rec, f, ensure_ascii=False)
    return True


def _refresh(root, cur: dict, command: str):
    """A later writing command of the holding session: the lease shows it (`command`, `updated_at`, mtime)."""
    path = lock_path(root)
    tmp = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    try:
        tmp.write_text(json.dumps(dict(cur, command=command, updated_at=now_iso()), ensure_ascii=False),
                       encoding="utf-8")
        os.replace(tmp, path)
    except OSError:
        try:
            tmp.unlink()
        except OSError:
            pass
        try:
            os.utime(path)
        except OSError:
            pass


def _restore(aside: Path, path: Path):
    """Put a lock we moved aside back, never over a lock another writer created meanwhile: a hard link (fails when
    the path is taken), else (no hard links: FAT, some shares) an exclusive create with the aside content. When the
    path is taken, the aside file is kept, so the record is not lost."""
    try:
        os.link(aside, path)
    except FileExistsError:
        return
    except OSError:
        try:
            data = aside.read_bytes()
            fd = os.open(str(path), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
        except OSError:
            return
        with os.fdopen(fd, "wb") as f:
            f.write(data)
    try:
        aside.unlink()
    except OSError:
        pass


def _remove_stale(path: Path, seen: dict, why: str, root) -> bool:
    """Move the stale lock aside and check it is the one we judged (not a fresh lock another writer just created)."""
    aside = path.with_name(f"{path.name}.stale-{os.getpid()}")
    try:
        os.replace(path, aside)
    except FileNotFoundError:
        return True                                    # someone else removed it: try to create ours
    except OSError:
        return False
    try:
        got = json.loads(aside.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        got = {}
    if got != seen:                                    # we grabbed a newer lock: put it back, its writer holds it
        _restore(aside, path)
        return False
    try:
        aside.unlink()
    except OSError:
        pass
    client_log(root, f"writer lock: took over the stale lock of session {seen.get('session_id') or '?'} "
                     f"({describe(seen)}): {why}")
    return True


def acquire(root, command: str, env=None) -> Lock:
    """Take the client's lease for `command`, or refresh it when this session holds it; raise Busy when another
    session holds it. Sets WHYNOT_LOCK_SESSION in this process, so the reel processes it starts are the same writer."""
    root = Path(root).expanduser()
    env = os.environ if env is None else env
    sid = session_id(env)
    os.environ[ENV] = sid
    path = lock_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    hp = holder_pid(env)
    rec = {"session_id": sid, "pid": hp, "pid_created": process_created(hp), "host": socket.gethostname(),
           "host_id": host_id(), "started_at": now_iso(), "updated_at": now_iso(), "command": command}
    for _ in range(5):
        if _create(path, rec):
            return Lock(root, sid, per_command=hp == os.getpid())
        cur = read(root)
        if cur is None:
            continue                                   # released between our two steps
        why = stale_reason(root, cur)
        if not why and not cur:
            time.sleep(0.1)                            # another writer is writing its record right now
            continue
        if not why and cur.get("session_id") == sid:
            _refresh(root, cur, command)               # re-entrant: this session already holds the client
            return Lock(root, sid, per_command=False)
        if not why:
            raise Busy(root, cur)
        if not _remove_stale(path, cur, why, root):
            time.sleep(0.05)
    raise Busy(root, read(root) or {})


def _minutes_since(iso) -> int | None:
    try:
        return max(0, round((datetime.now().astimezone() - datetime.fromisoformat(str(iso)).astimezone())
                            .total_seconds() / 60))
    except (TypeError, ValueError):
        return None


def status(root, env=None) -> dict:
    """`reel lock --status`: the holder, age_min (since it started), idle_min (since its last writing command: the
    file's mtime, the clock of the 2 h rule) and how the lease ends."""
    rec = read(root)
    sid = session_id(env)
    idle = _age_s(root) if rec is not None else None
    return {"lock": str(lock_path(root)), "held": rec is not None, "holder": rec, "stale": stale_reason(root, rec),
            "mine": bool(rec) and rec.get("session_id") == sid, "session_id": sid,
            "age_min": _minutes_since((rec or {}).get("started_at")) if rec else None,
            "idle_min": round(idle / 60) if idle is not None else None,
            "how": f"ends when the holding session closes or after {STALE_AFTER_S // 3600} h idle; the lead may run "
                   "`reel lock --release` on the editor's word"}


def release(root) -> dict:
    """`reel lock --release` (the editor, through the lead): remove whatever lock is there, with a log line."""
    rec = read(root)
    if rec is None:
        return {"released": False, "note": "no lock: nobody is writing in this client folder"}
    try:
        lock_path(root).unlink()
    except FileNotFoundError:
        return {"released": False, "note": "no lock: it was released meanwhile"}
    client_log(root, f"writer lock: released by `reel lock --release` (was {describe(rec or {})}, "
                     f"session {(rec or {}).get('session_id') or '?'})")
    return {"released": True, "was": rec}


def release_own(root, sid: str | None) -> bool:
    """SessionEnd: remove the lease only when the ending session holds it."""
    rec = read(root)
    if not sid or not rec or rec.get("session_id") != sid:
        return False
    try:
        lock_path(root).unlink()
    except OSError:
        return False
    client_log(root, f"writer lock: released at the end of session {sid} (was {describe(rec)})")
    return True


def other_writer(root, own_session: str | None) -> dict | None:
    """The live lease of ANOTHER session (for the SessionStart warning), else None."""
    rec = read(root)
    if not rec or stale_reason(root, rec) or (own_session and rec.get("session_id") == own_session):
        return None
    return rec


def rekey(root, new_sid: str, env=None) -> bool:
    """SessionStart after /clear or /resume (3.0 T3.4, fix round 1): a live lease held by this Claude Code process
    (same_process) under an earlier session id becomes `new_sid`'s, with a pipeline.log line. Anything else: False."""
    rec = read(root)
    if (not rec or not new_sid or rec.get("session_id") == new_sid or stale_reason(root, rec)
            or not same_process(rec, env)):
        return False
    _refresh(root, dict(rec, session_id=new_sid), str(rec.get("command") or ""))
    if (read(root) or {}).get("session_id") != new_sid:
        return False
    client_log(root, f"writer lock: session {new_sid} continues the lease of session {rec.get('session_id') or '?'} "
                     f"(same Claude Code process {rec.get('pid')}: /clear or /resume, at SessionStart)")
    return True
