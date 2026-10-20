#!/usr/bin/env python3
"""PostToolUse / SessionStart / SessionEnd: the read-once reminder (BL-01, Addendum M §M5.4 technique 4, M5-T6).

A second FULL read of the same large, unchanged file by the same (session, agent) adds one line of context next to the
content it repeats: use what you read, or a ranged read / grep / `reel brief` instead. It never blocks and never
denies; the reminder is the only output this hook ever prints. (Measured on CLI 2.1.299: an unchanged re-read returns
the full content again, so the reminder still saves the tokens of a THIRD read and teaches the habit.)

What counts as "the same read":
  * tool Read with no range: `offset`, `limit`, `pages` (a PDF range) or any other key besides `file_path` makes it a
    ranged read, which is never recorded and never reminded (a false "already read in full" could make a model skip
    pages it never saw, so an unknown future key counts as a range);
  * the file exists and is at least LARGE_BYTES (about 5k tokens);
  * file key = normcase(realpath) (so `D:\\x\\a.json`, `d:/x/A.JSON` and a junction to it are one file; on macOS
    normcase does nothing and realpath does not fold case, so `Out.json` and `out.json` are two keys: a missed
    reminder, never a false one),
    fingerprint = (size, st_mtime_ns): an edited file is a new read;
  * state is per (session id, agent id): subagents share the lead's session id, so a subagent that reads a file the
    lead already read is NOT told "already read" (it has not seen it). The lead's agent key is "lead".
SessionStart with source "compact" clears the LEAD's records only (after the lead's compaction its content is gone from
the context, so a re-read is needed). SessionEnd removes every file of the session.
Known gap: a subagent's own compaction is not visible to hooks (no event carries it), so a subagent that compacts and
re-reads a file may get one false reminder. The Read still delivers the content, so it costs nothing but one line.

State: ONE file per (session, agent), <engine home>/run/read-once/<sha256(session id)>.<sha256(agent id)>.json =
{"v": 2, "files": {filekey: [size, mtime_ns, last_seen]}}, at most MAX_ENTRIES files per agent (oldest dropped).
The update of one agent's file is a LOCKED read-modify-write (lock file `<same name>.lock` next to it, created with
O_CREAT|O_EXCL, short bounded retry; a lock older than LOCK_STALE_S is taken over; no lock within LOCK_WAIT_S means no
reminder and no write, never an error). So parallel Reads of one agent in one turn, parallel subagents and the lead's
reset never lose or resurrect a record. Written and read only through lib/linksafe (confined to run/read-once, never
through a link): a damaged, missing or link-bearing state means no reminder. Every write also sweeps state files
older than STALE_DAYS (crashed sessions never reach SessionEnd), without following links.
Only a Read that returned the whole file counts: if the CLI reports numLines != totalLines the read is ignored.
Never in the client folder, the cwd or the plugin folder. A missing engine home means silence BY DESIGN (the plugin is
not set up yet; the hook creates nothing above run/read-once).

Never fails the session: any exception, malformed input, missing field, unwritable folder -> exit 0, no output.
Stdlib only (plus the engine's own stdlib-only lib/plat and lib/linksafe), Python 3.8+ syntax.
"""
from __future__ import annotations

import hashlib
import json
import contextlib
import os
import random
import re
import sys
import time
from pathlib import Path

sys.dont_write_bytecode = True        # the plugin folder stays clean of __pycache__
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "engine" / "reel"))
try:
    from lib import plat, linksafe  # noqa: E402  (stdlib only)
except Exception:                      # no engine next to the hook: stay silent
    plat = linksafe = None

LARGE_BYTES = 20_000                   # about 5k tokens
MAX_ENTRIES = 500                      # files per agent
STALE_DAYS = 2                         # older state files are swept on every write
LOCK_WAIT_S = 3.0                      # contention budget (the hook's own timeout is 10 s); over it: no reminder, no write
LOCK_STALE_S = 10.0                    # a lock older than this is a crashed holder's: taken over
WITHIN = "run/read-once"
LEAD = "lead"
_STATE_NAME = re.compile(r"^[0-9a-f]{64}(?:\.[0-9a-f]{64})?\.(?:json|lock)$")   # state and lock names (and the older one-file-per-session name)
_REMINDER = ("WhyNot Cut: you already read {name} in full in this session and it has not changed; use what you "
             "read, or a ranged read / grep / `reel brief` instead of reading it again.")


class _Unsafe(Exception):
    """The state folder cannot be trusted (a link, an odd path, a damaged folder): do nothing."""


def _home() -> Path:
    return Path(plat.engine_home())


def _sha(text) -> str:
    return hashlib.sha256(str(text).encode("utf-8", "surrogatepass")).hexdigest()


def state_path(session_id, agent=None) -> Path:
    """The state file of one (session, agent) (not created here); the lead when `agent` is empty."""
    return _home() / "run" / "read-once" / f"{_sha(session_id)}.{_sha(agent or LEAD)}.json"


def _load(path: Path) -> dict:
    """One agent's records {filekey: [size, mtime_ns, last_seen]}; {} when none or damaged. _Unsafe on a link."""
    try:
        real = linksafe.confine(path, _home(), WITHIN)
    except Exception:
        raise _Unsafe()
    try:
        with open(real, "rb") as fh:
            data = json.loads(fh.read().decode("utf-8"))
    except (OSError, ValueError):
        return {}
    files = data.get("files") if isinstance(data, dict) and data.get("v") == 2 else None
    if not isinstance(files, dict):
        return {}
    return {k: v for k, v in files.items()
            if isinstance(k, str) and isinstance(v, list) and len(v) == 3
            and all(isinstance(x, (int, float)) and not isinstance(x, bool) for x in v)}


def _save(path: Path, files: dict) -> None:
    body = json.dumps({"v": 2, "files": files}, separators=(",", ":")).encode("utf-8")
    linksafe.replace_atomic(path, _home(), body, WITHIN)


def _lock_path(path: Path) -> Path:
    return path.with_suffix(".lock")


def _break_stale(lock: Path) -> None:
    """A lock older than LOCK_STALE_S belongs to a crashed hook: move it aside (atomic, so only one waiter wins), drop it."""
    try:
        if time.time() - os.stat(lock).st_mtime <= LOCK_STALE_S:
            return
        gone = lock.with_name(f"{lock.name}.stale{random.randrange(1 << 30)}")
        os.replace(lock, gone)
        os.unlink(gone)
    except OSError:
        pass


def _take_lock(lock: Path) -> bool:
    """Create the lock file (O_EXCL; the folder is made and confined first). False: no lock within the budget."""
    home = _home()
    deadline = time.monotonic() + LOCK_WAIT_S
    failures = 0
    while True:
        try:
            linksafe.makedirs(lock.parent, home, WITHIN)       # parallel first writes race here: retried below
            real = linksafe.confine(lock, home, WITHIN)
        except Exception:                                       # a half-made folder (transient), a link or a bad path
            failures += 1
            if failures >= 3:
                return False
        else:
            try:
                flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
                os.close(os.open(real, flags, 0o600))
                return True
            except (FileExistsError, PermissionError):          # held (or being deleted): wait for it
                _break_stale(lock)
            except OSError:
                failures += 1
                if failures >= 3:
                    return False
        if time.monotonic() >= deadline:
            return False
        time.sleep(0.004 + 0.02 * random.random())


@contextlib.contextmanager
def _locked(path: Path):
    """Hold the agent file's lock around read -> merge -> atomic replace. Yields False when it could not be had."""
    lock = _lock_path(path)
    got = _take_lock(lock)
    try:
        yield got
    finally:
        if got:
            try:
                linksafe.remove(lock, _home(), WITHIN)
            except Exception:
                try:
                    os.unlink(lock)
                except OSError:
                    pass


def _sweep(folder: Path, home: Path) -> None:
    """Remove state files whose mtime is older than STALE_DAYS. Links are skipped, never followed. Never raises."""
    try:
        limit = time.time() - STALE_DAYS * 86400
        with os.scandir(folder) as it:
            for e in it:
                try:
                    if (_STATE_NAME.match(e.name) and e.is_file(follow_symlinks=False)
                            and e.stat(follow_symlinks=False).st_mtime < limit):
                        linksafe.remove(e.path, home, WITHIN)
                except Exception:
                    pass
    except Exception:
        pass


def reset(session_id, agent=None) -> None:
    """Forget ONE agent's records (the lead's when `agent` is empty): the lead's compaction. Never raises."""
    try:
        if not session_id or plat is None or linksafe is None:
            return
        home = _home()
        sp = state_path(session_id, agent)
        linksafe.confine(sp, home, WITHIN)           # a link on the path: refuse, remove nothing
        linksafe.remove(sp, home, WITHIN)
    except Exception:
        pass


def forget(session_id) -> None:
    """Remove every state file of the session (all agents): SessionEnd. Never raises."""
    try:
        if not session_id or plat is None or linksafe is None:
            return
        home = _home()
        folder = home / "run" / "read-once"
        prefix = _sha(session_id) + "."
        with os.scandir(folder) as it:
            names = [e.name for e in it if e.name.startswith(prefix) and e.name.endswith(".json")
                     and e.is_file(follow_symlinks=False)]
        for name in names:                           # remove() refuses a link anywhere on the way: nothing is deleted through it
            try:
                linksafe.remove(folder / name, home, WITHIN)
            except Exception:
                pass
    except Exception:
        pass


def _full_read_target(data: dict):
    """(real path, size, mtime_ns, shown name) of a FULL read of a large existing file, else None."""
    ti = data.get("tool_input")
    if not isinstance(ti, dict) or any(v is not None for k, v in ti.items() if k != "file_path"):
        return None                                  # offset / limit / pages / any other key: a ranged read
    fp = ti.get("file_path")
    if not isinstance(fp, str) or not fp or "\x00" in fp:
        return None
    cwd = data.get("cwd")
    base = cwd if isinstance(cwd, str) and cwd else os.getcwd()
    path = fp if os.path.isabs(fp) else os.path.join(base, fp)
    real = os.path.normcase(os.path.realpath(path))
    st = os.stat(real)
    if not os.path.isfile(real) or st.st_size < LARGE_BYTES:
        return None
    return real, st.st_size, st.st_mtime_ns, os.path.basename(path.rstrip("/\\"))


def _truncated(data: dict) -> bool:
    """True when the CLI says this Read returned only part of the file (numLines != totalLines)."""
    tr = data.get("tool_response")
    fi = tr.get("file") if isinstance(tr, dict) else None
    if not isinstance(fi, dict):
        return False
    n, t = fi.get("numLines"), fi.get("totalLines")
    return isinstance(n, int) and isinstance(t, int) and not isinstance(n, bool) and not isinstance(t, bool) and n != t


def handle(data) -> "str | None":
    """One hook input -> the stdout text (a JSON line) or None. Never raises."""
    try:
        return _handle(data)
    except Exception:
        return None


def _handle(data) -> "str | None":
    if not isinstance(data, dict) or plat is None or linksafe is None:
        return None
    sid = data.get("session_id")
    if not isinstance(sid, str) or not sid:
        return None
    agent = data.get("agent_id")
    agent = agent if isinstance(agent, str) and agent else LEAD
    event = data.get("hook_event_name")
    if event == "SessionEnd":
        forget(sid)
        return None
    if event == "SessionStart":
        if data.get("source") == "compact":
            reset(sid, agent)
        return None
    if event not in (None, "PostToolUse") or data.get("tool_name") != "Read":
        return None
    if _truncated(data):
        return None
    target = _full_read_target(data)
    if target is None:
        return None
    real, size, mtime_ns, name = target
    path = state_path(sid, agent)
    with _locked(path) as got:
        if not got:
            return None
        try:
            files = _load(path)
        except _Unsafe:
            return None
        old = files.pop(real, None)                   # re-inserted last: dict order = oldest first
        repeated = isinstance(old, list) and old[0] == size and old[1] == mtime_ns
        files[real] = [size, mtime_ns, int(time.time())]
        while len(files) > MAX_ENTRIES:
            del files[next(iter(files))]
        _save(path, files)
    _sweep(path.parent, _home())
    if not repeated:
        return None
    ctx = _REMINDER.format(name=name or "this file")
    return json.dumps({"hookSpecificOutput": {"hookEventName": "PostToolUse", "additionalContext": ctx}},
                      ensure_ascii=False)


def main() -> None:
    try:
        raw = sys.stdin.buffer.read().decode("utf-8-sig")
        out = handle(json.loads(raw))
    except Exception:
        out = None
    if out:
        try:
            sys.stdout.buffer.write((out + "\n").encode("utf-8"))
            sys.stdout.flush()
        except Exception:
            pass


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass
    sys.exit(0)
