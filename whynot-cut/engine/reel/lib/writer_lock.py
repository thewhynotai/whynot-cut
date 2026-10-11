"""One writer per client folder (3.0 T1.8): `<client>/output/.whynot-lock`.

Two Claude sessions once worked on one client folder at the same time and their writes crossed. Every `reel` command
that writes into a client folder now holds this lock for its duration (cli.py decides which commands write); a
command of ANOTHER session gets `{"blocked", "how"}` and exit 2 while the lock is held.

The lock file is JSON `{session_id, pid, host, started_at, command}`, created atomically (O_CREAT | O_EXCL) and
touched every 10 min while its command runs (its mtime is the last sign of life). It is stale, and the next writer
takes it over with a line in output/logs/pipeline.log, when
  * its process (`pid`) is no longer running on this computer (`host`), or
  * it shows no activity for 2 h (the only test for a lock written by another computer on a shared drive).

Session id (who "one writer" is), first match wins:
  WHYNOT_LOCK_SESSION    set by a writing `reel` for the processes it starts (a nested reel is the same writer)
  CLAUDE_SESSION_ID      if a host exports it
  CLAUDE_CODE_SESSION_ID what Claude Code gives Bash/PowerShell commands (the lead and its subagents share it)
  CLAUDE_PID             the Claude Code process, when only that is exported: "claude-pid-<pid>"
  else "pid-<pid of this reel>": an editor at a plain terminal runs one command at a time, so a per-process id is
  enough there; it is never re-entrant, which errs on the safe side (blocks, never merges two writers).
Sequential commands of one session never meet a lock (each releases its own at the end); the session id makes
overlapping commands of the SAME session (parallel subagents, a nested reel) re-entrant: they run without taking
the lock and never remove it.

Stdlib only: imported by cli.py (`lib.writer_lock`) and by hooks/session_context.py (`writer_lock`).
"""
from __future__ import annotations

import json
import os
import socket
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


def lock_path(root) -> Path:
    return Path(root).expanduser() / LOCK_REL


def session_id(env=None) -> str:
    env = os.environ if env is None else env
    for k in (ENV, "CLAUDE_SESSION_ID", "CLAUDE_CODE_SESSION_ID"):
        if (env.get(k) or "").strip():
            return env[k].strip()
    if (env.get("CLAUDE_PID") or "").strip().isdigit():
        return f"claude-pid-{env['CLAUDE_PID'].strip()}"
    return f"pid-{os.getpid()}"


def pid_alive(pid) -> bool:
    """Is process `pid` running on this computer? Windows has no kill(pid, 0): ask OpenProcess + GetExitCodeProcess."""
    try:
        pid = int(pid)
    except (TypeError, ValueError):
        return False
    if pid <= 0:
        return False
    if IS_WIN:
        import ctypes
        from ctypes import wintypes
        k32 = ctypes.WinDLL("kernel32", use_last_error=True)
        k32.OpenProcess.restype = wintypes.HANDLE
        k32.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
        k32.GetExitCodeProcess.argtypes = (wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD))
        k32.CloseHandle.argtypes = (wintypes.HANDLE,)
        h = k32.OpenProcess(0x1000, False, pid)          # PROCESS_QUERY_LIMITED_INFORMATION
        if not h:
            return ctypes.get_last_error() == 5           # ERROR_ACCESS_DENIED: it exists (another user's process)
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
    if rec.get("host") == socket.gethostname() and not pid_alive(rec.get("pid")):
        return f"its process {rec.get('pid')} on {rec.get('host')} is no longer running"
    if age > STALE_AFTER_S:
        return f"no activity for over {STALE_AFTER_S // 3600} h ({age / 3600:.1f} h)"
    return None


def describe(rec: dict) -> str:
    return f"{rec.get('command') or 'a writing command'}, since {rec.get('started_at') or '?'}"


def client_log(root, msg: str):
    line = f"[{datetime.now().astimezone().isoformat(timespec='seconds')}] {msg}"
    print(line, file=sys.stderr)
    try:
        f = Path(root).expanduser() / LOG_REL
        f.parent.mkdir(parents=True, exist_ok=True)
        with open(f, "a", encoding="utf-8") as fh:
            fh.write(line + "\n")
    except OSError:
        pass


class Busy(Exception):
    """Another session holds the client's lock."""

    def __init__(self, root, rec: dict):
        super().__init__(describe(rec))
        self.root, self.rec = Path(root), rec

    def refusal(self) -> dict:
        r = self.rec
        who = f"session {str(r.get('session_id') or '?')[:12]}, process {r.get('pid')} on {r.get('host')}"
        return {"blocked": f"another session is writing in this client folder ({describe(r)}; {who}). One writer per "
                           f"client folder: this command would collide with it.",
                "how": "Wait until that command finishes, or work on another client. Read-only commands still work "
                       "(`reel next`, `reel status`, `reel inbox --no-refresh`, `reel lock --status`). If the editor "
                       "says that session is closed or stuck, they run `reel lock --release` (the lead only). The lock "
                       "goes stale by itself when its process ends or after 2 h without activity.",
                "lock": str(lock_path(self.root)), "holder": r}


class Lock:
    """The lock this process holds (owned) or joined (re-entrant: same session id, never removed by us)."""

    def __init__(self, root, owned: bool):
        self.root, self.owned = Path(root), owned
        self._stop = threading.Event()
        if owned:
            threading.Thread(target=self._touch, name="whynot-lock-touch", daemon=True).start()

    def _touch(self):
        while not self._stop.wait(TOUCH_EVERY_S):
            if (read(self.root) or {}).get("pid") == os.getpid():
                try:
                    os.utime(lock_path(self.root))
                except OSError:
                    pass

    def release(self):
        self._stop.set()
        if self.owned and (read(self.root) or {}).get("pid") == os.getpid():
            try:
                lock_path(self.root).unlink()
            except OSError:
                pass
        self.owned = False

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
    if got != seen:                                    # we grabbed a newer lock: put it back, the writer holds it
        try:
            os.link(aside, path)
        except OSError:
            pass
        try:
            aside.unlink()
        except OSError:
            pass
        return False
    try:
        aside.unlink()
    except OSError:
        pass
    client_log(root, f"writer lock: took over the stale lock of session {seen.get('session_id') or '?'} "
                     f"({describe(seen)}): {why}")
    return True


def acquire(root, command: str, env=None) -> Lock:
    """Take the client's lock for `command` or join it (same session); raise Busy when another session holds it.
    Sets WHYNOT_LOCK_SESSION in this process, so the reel processes it starts are the same writer."""
    root = Path(root).expanduser()
    sid = session_id(env)
    os.environ[ENV] = sid
    path = lock_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    rec = {"session_id": sid, "pid": os.getpid(), "host": socket.gethostname(),
           "started_at": datetime.now().astimezone().isoformat(timespec="seconds"), "command": command}
    for _ in range(5):
        if _create(path, rec):
            return Lock(root, owned=True)
        cur = read(root)
        if cur is None:
            continue                                   # released between our two steps
        why = stale_reason(root, cur)
        if not why and not cur:
            time.sleep(0.1)                            # another writer is writing its record right now
            continue
        if not why and cur.get("session_id") == sid:
            return Lock(root, owned=False)             # re-entrant: this session already writes here
        if not why:
            raise Busy(root, cur)
        if not _remove_stale(path, cur, why, root):
            time.sleep(0.05)
    cur = read(root) or {}
    raise Busy(root, cur)


def status(root, env=None) -> dict:
    rec = read(root)
    sid = session_id(env)
    return {"lock": str(lock_path(root)), "held": rec is not None, "holder": rec, "stale": stale_reason(root, rec),
            "mine": bool(rec) and rec.get("session_id") == sid, "session_id": sid}


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


def other_writer(root, own_session: str | None) -> dict | None:
    """The live lock of ANOTHER session (for the SessionStart warning), else None."""
    rec = read(root)
    if not rec or stale_reason(root, rec) or (own_session and rec.get("session_id") == own_session):
        return None
    return rec
