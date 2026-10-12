"""Per-file lock for read-modify-write (3.0 T2.4, engine IM-11 / MI-23).

Parallel subagents of ONE session (several reels of one episode, the lead and a specialist) run `reel` commands at the
same time against the same client folder, and some commands update a shared file: read it, change it, write it back
(project-status.json, clip-ids.json, the reference-analysis cache, an episode's selection.json). `write_json` alone is
atomic (unique temp file + os.replace), but two read-modify-write cycles that overlap still lose one update. `locked`
serialises them: it holds an OS lock on `<file>.lock` next to the file for the whole cycle.

  * Windows: `msvcrt.locking` on byte 0 of the lock file; POSIX: `fcntl.flock`. Both are released by the operating
    system when the holder exits or crashes, so a lock is never stale and never needs a takeover (unlike the session
    lease `output/.whynot-lock`, lib/writer_lock.py, and the bridge build lock `.build.lock`, lib/cep_queue.py, which
    are records with a pid that outlive a process on purpose).
  * The lock file is created on first use and left in place (removing it would let a waiter lock a file that is no
    longer the one the next writer opens).
  * Re-entrant inside one process (a `set_status` inside a locked section on the same file does not deadlock itself)
    and exclusive between threads of one process (`reel serve`).
  * Waiting is bounded (`WAIT_S`): a holder that hangs gives the next command a `LockTimeout` guidance error, never
    an endless wait. A timeout is a "busy, try again" refusal: it carries `blocked`, so the CLI exits 2 like the
    writer-lease refusal.
  * A volume that cannot lock at all (macOS flock on SMB/AFP/NFS-without-lockd or a cloud-drive File Provider:
    ENOTSUP / ENOLCK; a Windows virtual drive that refuses byte-range locks: EINVAL) is not an error: the first
    refusal is noted in the engine log, and that folder goes on with the in-process lock only (the 2.x behaviour
    between processes).

Stdlib only (plus lib.errors); imported by lib.common.
"""
from __future__ import annotations

import contextlib
import errno
import os
import random
import threading
import time
from pathlib import Path

from .errors import Guidance

IS_WIN = os.name == "nt"
if IS_WIN:
    import msvcrt
else:
    import fcntl

LOCK_SUFFIX = ".lock"
WAIT_S = 120.0                      # a read-modify-write takes milliseconds; discovery passes its own, longer wait
OPEN_RETRY_S = 2.0                  # a lock file that cannot be opened: a scanner holds it for a moment, not for minutes
_BUSY = {errno.EACCES, errno.EAGAIN, errno.EWOULDBLOCK, errno.EDEADLK, getattr(errno, "EDEADLOCK", errno.EDEADLK)}
# "this volume cannot lock": POSIX flock refused by the filesystem; Windows maps ERROR_INVALID_FUNCTION /
# ERROR_NOT_SUPPORTED (a virtual or network drive without byte-range locks) to EINVAL.
_UNSUPPORTED = {getattr(errno, n) for n in ("ENOTSUP", "EOPNOTSUPP", "ENOLCK", "ENOSYS", "EINVAL") if hasattr(errno, n)}
_NO_OS_LOCK = -1                    # the descriptor value of a lock held in process only


class LockTimeout(Guidance):
    """Another process kept the file locked longer than the wait. `blocked`: errors.describe adds the `blocked` key,
    so the document exits 2 (a refusal: wait, then run again), like a live writer lease."""
    blocked = True

    def __init__(self, path: Path, waited_s: float):
        self.path, self.waited_s = Path(path), waited_s
        super().__init__(
            f"{self.path.name} is busy: another WhyNot Cut command kept it locked for {waited_s:g} s",
            "Another reel command (a parallel subagent or a second session) is updating the same file. Wait for it "
            "to finish, then run this command again. If nothing else is running, close the hung `reel` / python "
            "process (the lock goes away with it).",
            str(self.path))


class _Entry:
    __slots__ = ("rlock", "depth", "fd")

    def __init__(self):
        self.rlock = threading.RLock()
        self.depth = 0
        self.fd: int | None = None


_entries: dict[str, _Entry] = {}    # process-wide by nature: one OS lock per lock file per process
_entries_guard = threading.Lock()


def lock_path(path) -> Path:
    """`<file>.lock` next to the file."""
    p = Path(path)
    return p.with_name(p.name + LOCK_SUFFIX)


def _entry(lp: Path) -> _Entry:
    key = os.path.normcase(os.path.abspath(lp))
    with _entries_guard:
        e = _entries.get(key)
        if e is None:
            e = _entries[key] = _Entry()
        return e


class _Unsupported(Exception):
    """The OS lock call says this volume cannot lock."""

    def __init__(self, err: OSError):
        super().__init__(str(err))
        self.err = err


_unsupported_noted: set[str] = set()


def _note_unsupported(lp: Path, err: OSError):
    """Once per folder: say in the engine log (never stdout) that this folder is locked in process only."""
    key = os.path.normcase(os.path.abspath(lp.parent))
    with _entries_guard:
        if key in _unsupported_noted:
            return
        _unsupported_noted.add(key)
    try:
        import datetime as _dt
        from .common import engine_home
        log = engine_home() / "logs" / "pipeline.log"
        log.parent.mkdir(parents=True, exist_ok=True)
        now = _dt.datetime.now().astimezone().isoformat(timespec="seconds")
        with open(log, "a", encoding="utf-8") as f:
            f.write(f"[{now}] file_lock: {lp.parent} cannot take OS file locks ({errno.errorcode.get(err.errno, err.errno)}"
                    f": {err.strerror or err}); updates there are serialised inside this process only\n")
    except Exception:  # noqa: BLE001 — a note about a missing lock must never fail the command
        pass


def _try_lock(fd: int) -> bool:
    try:
        if IS_WIN:
            os.lseek(fd, 0, os.SEEK_SET)
            msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
        else:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return True
    except OSError as e:
        if e.errno in _BUSY:
            return False
        if e.errno in _UNSUPPORTED:
            raise _Unsupported(e) from e
        raise


def _unlock(fd: int):
    if fd == _NO_OS_LOCK:
        return
    try:
        if IS_WIN:
            os.lseek(fd, 0, os.SEEK_SET)
            msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
        else:
            fcntl.flock(fd, fcntl.LOCK_UN)
    except OSError:
        pass                        # closing the descriptor releases it anyway
    finally:
        os.close(fd)


def _open(lp: Path, deadline: float) -> int:
    flags = os.O_RDWR | os.O_CREAT | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOINHERIT", 0) | \
        getattr(os, "O_CLOEXEC", 0)
    give_up = min(deadline, time.monotonic() + OPEN_RETRY_S)
    while True:
        try:
            lp.parent.mkdir(parents=True, exist_ok=True)
            return os.open(str(lp), flags, 0o666)
        except OSError as e:
            # PermissionError on Windows: a scanner or indexer has the file open for a moment, so retry briefly. A
            # lock file that still cannot be made (read-only folder, an ACL) is not a wait: say which folder.
            if isinstance(e, PermissionError) and time.monotonic() < give_up:
                time.sleep(0.01)
                continue
            raise Guidance(
                f"cannot create the lock file {lp.name} in {lp.parent}: {e.strerror or e}",
                f"Check that the folder {lp.parent} is not read-only, is not full or offline (a cloud or network drive "
                "may be syncing), and that this user may write there, then run the command again",
                str(lp.parent)) from e


def _acquire(lp: Path, target: Path, wait: float, t0: float) -> int:
    deadline = t0 + wait
    fd = _open(lp, deadline)
    try:
        delay = 0.002
        while not _try_lock(fd):
            if time.monotonic() >= deadline:
                raise LockTimeout(target, round(wait, 1))
            time.sleep(delay * (0.5 + random.random()))       # jitter: waiters do not retry in lockstep
            delay = min(delay * 1.5, 0.05)
    except _Unsupported as u:                                  # this volume cannot lock: in-process lock only
        os.close(fd)
        _note_unsupported(lp, u.err)
        return _NO_OS_LOCK
    except BaseException:
        os.close(fd)
        raise
    return fd


@contextlib.contextmanager
def locked(path, wait_s: float | None = None):
    """Hold the lock of `path` (the file being updated, not the lock file) for the with-block; yields the lock file's
    path. Raises LockTimeout when it is still held elsewhere after `wait_s` (default WAIT_S) seconds."""
    target = Path(path)
    lp = lock_path(target)
    wait = WAIT_S if wait_s is None else max(0.0, float(wait_s))
    t0 = time.monotonic()
    e = _entry(lp)
    if not e.rlock.acquire(timeout=wait if wait > 0 else 0.001):
        raise LockTimeout(target, round(wait, 1))
    try:
        if e.depth == 0:
            e.fd = _acquire(lp, target, max(0.0, wait - (time.monotonic() - t0)), time.monotonic())
        e.depth += 1
        try:
            yield lp
        finally:
            e.depth -= 1
            if e.depth == 0:
                fd, e.fd = e.fd, None
                _unlock(fd)
    finally:
        e.rlock.release()
