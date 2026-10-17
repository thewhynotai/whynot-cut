# SPDX-License-Identifier: GPL-3.0-or-later
# © 2026 The Why Not AI (thewhynot.ai)
"""Link-safe removal and write confinement (COORDINATION rule 15; Addendum J13.3; Phase 4 Task 15; Addendum L-T8).

The 2026-10-14 incident: a recursive move walked into a junction and deleted the real files it pointed to. Everything
here treats a link as a name, never as the thing it points to.

The trust anchor. Every call takes `root`: the client root or the engine home, never a narrower folder. The root may
itself sit behind a link (a clients folder on another drive, macOS /var → /private/var, the engine home junction);
it is resolved once. A narrower scope is `within` (relative to the root, e.g. "output/from_website"): from the root
down through `within` to the target, a link anywhere is refused, so a planted junction `output/from_website → assets`
can't redirect anything.

  * `is_link(p)`: a symlink, or a Windows reparse point that points elsewhere (junctions and symlinks carry the "name
    surrogate" tag bit; a OneDrive placeholder doesn't). It fails closed: any error but "missing" is a refusal.
  * `confine(path, root, within=None) -> real path`: refuses (Guidance) a path outside root/within (or equal to
    it), a link on the way down, a resolved path that leaves the resolved root, and names below the root that are not
    plain names (NUL and control characters; on Windows also `<>:"|?*`, device names, trailing dots or spaces, which
    the OS would silently strip). It returns the REAL path (L-T8 compares real paths, never text).
  * `makedirs(path, root, within=None)`: the missing folders only, each re-checked as it is made; a file in the way
    is Guidance; what it made is removed again when it fails.
  * `create_new(path, root, data, within=None)`: O_EXCL (+ O_NOFOLLOW where the OS has it), fsync; FileExistsError
    when the name is taken (a file, a folder or a hard link), so nothing is ever written through.
  * `replace_atomic(path, root, data, within=None)`: a fresh randomly named temp file + fsync + os.replace, which
    replaces a hard link instead of writing into its other name (L-G25). On Windows a momentary "access denied"
    from another writer replacing the same file is retried (up to 20 times, 10–50 ms apart).
  * `remove(path, root, within=None) -> bytes freed`: never removes the root or `within` itself; a link is unlinked
    as a name, never entered. POSIX walks by file descriptor (O_NOFOLLOW + dir_fd; a folder swapped for a link
    between two steps is refused by the OS) and never crosses into another device (a mount). Windows re-checks each
    folder's identity and link status before it is scanned and again before each of its entries is removed (the
    remaining window is the two system calls between that check and the delete). Read-only is cleared
    only on a file with one link (a hard link shares its attribute with the name outside). Hard-linked files free 0
    bytes. A locked or refused item doesn't stop the walk: `RemoveIncomplete` (a Guidance) at the end carries `freed`
    and `failures`.
A tree that legitimately holds a junction inside the anchor (e.g. a cache folder moved to another drive) is refused,
not followed: anchor the call at that folder's real path instead.
"""
from __future__ import annotations

import os
import random
import secrets
import stat
import sys
import time
from pathlib import Path

from .errors import Guidance

_REPARSE_POINT = 0x400
_NAME_SURROGATE = 0x20000000
_WIN_DEVICES = {"con", "prn", "aux", "nul", "conin$", "conout$", *(f"com{i}" for i in range(1, 10)),
                *(f"lpt{i}" for i in range(1, 10))}
_WIN_BAD_CHARS = set('<>:"|?*')
_HOW = "the engine never writes or deletes through a link; remove the link by hand, or pick another folder"
_MAX_DEPTH = 256
_REPLACE_TRIES = 20


class RemoveIncomplete(Guidance):
    """Some items could not be removed; everything else was. `freed` bytes, `failures` = [(path, why)]."""

    def __init__(self, freed: int, failures: list):
        super().__init__(f"{len(failures)} item(s) could not be removed", "close the program that holds them, then "
                         "try again", where=failures[0][0] if failures else None)
        self.freed, self.failures = freed, failures


def _refuse(what: str, path) -> Guidance:
    return Guidance(what, _HOW, where=str(path))


def is_link(p) -> bool:
    try:
        st = os.lstat(p)
    except (FileNotFoundError, NotADirectoryError):
        return False
    except (OSError, ValueError) as e:
        raise _refuse(f"can't tell whether this is a link ({type(e).__name__})", p) from None
    return _st_is_link(st)


def _st_is_link(st) -> bool:
    if stat.S_ISLNK(st.st_mode):
        return True
    if getattr(st, "st_file_attributes", 0) & _REPARSE_POINT:
        tag = getattr(st, "st_reparse_tag", None)
        return True if tag is None else bool(tag & _NAME_SURROGATE)
    return False


def _norm(p: str) -> str:
    return os.path.normcase(os.path.normpath(p))


def _inside(child: str, parent: str) -> bool:
    c, p = _norm(child), _norm(parent)
    return c != p and c.startswith(p.rstrip(os.sep) + os.sep)


def _bad_name(part: str) -> str | None:
    if any(ord(ch) < 32 for ch in part):
        return "a control character or NUL"
    if sys.platform == "win32":
        if part in (".", ".."):
            return None
        if any(ch in _WIN_BAD_CHARS for ch in part):
            return "a character Windows doesn't allow"
        if part.endswith((".", " ")):
            return "a trailing dot or space (Windows would drop it)"
        if part.split(".", 1)[0].strip().lower() in _WIN_DEVICES:
            return "a Windows device name"
    return None


def _check_raw(path, root_abs: str):
    """Names below the root, read BEFORE abspath (which on Windows drops trailing dots and spaces)."""
    raw = os.fspath(path)
    if "\x00" in raw:
        raise _refuse("the path holds a NUL character", repr(raw))
    if os.path.isabs(raw):
        real = os.path.realpath(root_abs)
        if _norm(raw).startswith(_norm(root_abs)):
            raw = raw[len(root_abs):]
        elif _norm(raw).startswith(_norm(real)):
            raw = raw[len(real):]
        else:
            raw = os.path.splitdrive(raw)[1]                # can't line it up with the root: check every name
    if sys.platform == "win32":
        joined = os.path.join(root_abs, os.fspath(path))
        if _norm(os.path.abspath(joined)) != _norm(os.path.normpath(joined)) and \
                os.path.splitdrive(os.fspath(path))[0] == "" and not os.fspath(path).startswith(("\\", "/")):
            raise _refuse("Windows would change that name (a trailing dot or space)", path)
    for part in raw.replace("\\", "/").split("/") if sys.platform == "win32" else raw.split("/"):
        if part == "":
            continue
        why = _bad_name(part)
        if why:
            raise _refuse(f"{part!r} is not a plain file or folder name: {why}", path)


class _Target:
    __slots__ = ("given", "real", "base", "parts")

    def __init__(self, given, real, base, parts):
        self.given, self.real, self.base, self.parts = given, real, base, parts


def _resolve(path, root, within=None, allow_scope: bool = False) -> _Target:
    root_abs = os.path.abspath(os.fspath(root))
    _check_raw(path, root_abs)
    root_real = os.path.realpath(root_abs)
    raw = os.fspath(path)
    p_abs = os.path.abspath(raw if os.path.isabs(raw) else os.path.join(root_abs, raw))
    if _inside(p_abs, root_abs):
        base = root_abs
    elif _inside(p_abs, root_real):
        base = root_real
    else:
        raise _refuse("that path is outside the folder this command may use", p_abs)
    parts = os.path.relpath(p_abs, base).split(os.sep)
    if within:
        scope = [s for s in str(within).replace("\\", "/").split("/") if s]
        n = len(scope)
        same = [_norm(a) for a in parts[:n]] == [_norm(b) for b in scope]
        if not same or (len(parts) == n and not allow_scope):
            raise _refuse(f"that path is outside {'/'.join(scope)}", p_abs)
    cur = base
    for part in parts:
        cur = os.path.join(cur, part)
        if is_link(cur):
            raise _refuse("a link (junction or symlink) is on that path", cur)
    real = os.path.realpath(p_abs)
    if not _inside(real, root_real):
        raise _refuse("that path leads outside the folder this command may use", p_abs)
    return _Target(p_abs, real, base, parts)


def confine(path, root, within=None) -> Path:
    """The REAL path for writing `path` (absolute, or relative to `root`) inside root/within; else Guidance."""
    return Path(_resolve(path, root, within).real)


def makedirs(path, root, within=None) -> list:
    """Create the missing folders of `path`, one at a time, each re-checked; returns the folders made."""
    t = _resolve(path, root, within, allow_scope=True)
    made, cur = [], t.base
    try:
        for part in t.parts:
            cur = os.path.join(cur, part)
            if is_link(cur):
                raise _refuse("a link (junction or symlink) is on that path", cur)
            if os.path.lexists(cur):
                if not os.path.isdir(cur):
                    raise _refuse("a file is in the way of that folder", cur)
                continue
            try:
                os.mkdir(cur)
            except OSError as e:
                raise _refuse(f"can't make that folder ({e.strerror or type(e).__name__})", cur) from None
            made.append(Path(cur))
            if is_link(cur) or not _inside(os.path.realpath(cur), os.path.realpath(t.base)):
                raise _refuse("that folder turned into a link while it was being made", cur)
    except BaseException:
        for d in reversed(made):
            try:
                os.rmdir(d)
            except OSError:
                pass
        raise
    return made


def create_new(path, root, data: bytes, within=None) -> Path:
    """Write a new file: never an existing name (FileExistsError), never through a link (Guidance)."""
    t = _resolve(path, root, within)
    p = Path(t.given)
    if os.path.lexists(p):
        raise FileExistsError(17, "the name is taken", str(p))
    made = makedirs(p.parent, root, within) if len(t.parts) > 1 else []
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(p, flags, 0o644)
    except FileExistsError:
        raise
    except OSError as e:
        for d in reversed(made):
            try:
                os.rmdir(d)
            except OSError:
                pass
        if os.path.isdir(p):
            raise FileExistsError(17, "a folder has that name", str(p)) from None
        raise _refuse(f"can't create that file ({e.strerror or type(e).__name__})", p) from None
    try:
        with os.fdopen(fd, "wb") as fh:
            fd = None
            fh.write(data)
            fh.flush()
            os.fsync(fh.fileno())
    except BaseException:
        if fd is not None:
            os.close(fd)
        try:
            os.unlink(p)
        except OSError:
            pass
        raise
    return p


def replace_atomic(path, root, data: bytes, within=None) -> Path:
    """Write `data` to `path` through a fresh temp file + os.replace: a hard link is replaced, not written through."""
    t = _resolve(path, root, within)
    p = Path(t.given)
    for _ in range(8):
        tmp = p.with_name(f".{p.name}.{secrets.token_hex(6)}.tmp")
        try:
            create_new(tmp, root, data, within)
            break
        except FileExistsError:
            continue
    else:
        raise _refuse("could not make a temporary file beside it", p)
    try:
        for attempt in range(_REPLACE_TRIES):
            try:
                os.replace(tmp, p)
                break
            except PermissionError:                        # Windows: another writer is replacing it this instant
                if sys.platform != "win32" or attempt == _REPLACE_TRIES - 1:
                    raise
                time.sleep(0.01 + 0.04 * random.random())
    except BaseException as e:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        if isinstance(e, OSError):
            raise _refuse(f"can't replace that file ({e.strerror or type(e).__name__})", p) from None
        raise
    return p


# ------------------------------------------------------------------------------------------------- removal
def _unlink_link(p: str, st):
    if sys.platform == "win32" and getattr(st, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_DIRECTORY:
        os.rmdir(p)                                        # a junction or a directory symlink: removes the link
    else:
        os.unlink(p)


def _unlink_file(p: str, st) -> int:
    """Delete a regular file; returns the bytes it frees (0 for a hard link: the data stays under its other name)."""
    try:
        os.unlink(p)
    except PermissionError:
        if st.st_nlink != 1 or sys.platform != "win32":
            raise                                          # never touch an attribute shared with a name outside
        os.chmod(p, stat.S_IWRITE | stat.S_IREAD)
        os.unlink(p)
    return st.st_size if st.st_nlink == 1 else 0


def _same(a, b) -> bool:
    return (a.st_dev, a.st_ino) == (b.st_dev, b.st_ino)


def _still(d: str, ident) -> bool:
    try:
        st = os.lstat(d)
    except OSError:
        return False
    return not _st_is_link(st) and _same(st, ident) and stat.S_ISDIR(st.st_mode)


def _rm_windows(top: str, top_st, failures: list) -> int:
    freed = 0
    stack = [(top, top_st, False)]
    while stack:
        d, ident, done = stack.pop()
        if done:
            try:
                os.rmdir(d)
            except OSError as e:
                failures.append((d, e.strerror or type(e).__name__))
            continue
        try:
            st = os.lstat(d)
        except OSError as e:
            failures.append((d, e.strerror or type(e).__name__))
            continue
        if _st_is_link(st):                                # swapped for a link after it was seen: unlink, never enter
            try:
                _unlink_link(d, st)
            except OSError as e:
                failures.append((d, e.strerror or type(e).__name__))
            continue
        if not _same(st, ident) or not stat.S_ISDIR(st.st_mode):
            failures.append((d, "changed while it was being removed"))
            continue
        stack.append((d, ident, True))
        try:
            with os.scandir(d) as it:
                names = [e.name for e in it]
        except OSError as e:
            failures.append((d, e.strerror or type(e).__name__))
            continue
        for name in names:
            if not _still(d, ident):                       # swapped for a link after the scan: stop here
                failures.append((d, "changed while it was being removed"))
                break
            p = os.path.join(d, name)
            try:
                est = os.lstat(p)
            except OSError as e:
                failures.append((p, e.strerror or type(e).__name__))
                continue
            try:
                if _st_is_link(est):
                    _unlink_link(p, est)
                elif stat.S_ISDIR(est.st_mode):
                    stack.append((p, est, False))
                else:
                    freed += _unlink_file(p, est)
            except OSError as e:
                failures.append((p, e.strerror or type(e).__name__))
    return freed


def _rm_posix_fd(dfd: int, where: str, dev: int, failures: list, depth: int) -> int:
    if depth > _MAX_DEPTH:
        failures.append((where, "folders nested too deep"))
        return 0
    freed = 0
    try:
        with os.scandir(dfd) as it:
            names = [e.name for e in it]
    except OSError as e:
        failures.append((where, e.strerror or type(e).__name__))
        return 0
    for name in names:
        p = os.path.join(where, name)
        try:
            st = os.stat(name, dir_fd=dfd, follow_symlinks=False)
        except OSError as e:
            failures.append((p, e.strerror or type(e).__name__))
            continue
        try:
            if stat.S_ISDIR(st.st_mode):
                if st.st_dev != dev:
                    failures.append((p, "another drive is mounted here; not crossed"))
                    continue
                cfd = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=dfd)
                try:
                    if not _same(os.fstat(cfd), st):
                        failures.append((p, "changed while it was being removed"))
                        continue
                    freed += _rm_posix_fd(cfd, p, dev, failures, depth + 1)
                finally:
                    os.close(cfd)
                os.rmdir(name, dir_fd=dfd)
            else:                                          # a symlink is removed as a name, like a file
                os.unlink(name, dir_fd=dfd)
                if stat.S_ISREG(st.st_mode) and st.st_nlink == 1:
                    freed += st.st_size
        except OSError as e:
            failures.append((p, e.strerror or type(e).__name__))
    return freed


def _rm_posix(top: str, top_st, failures: list) -> int:
    fd = os.open(top, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        if not _same(os.fstat(fd), top_st):
            failures.append((top, "changed while it was being removed"))
            return 0
        freed = _rm_posix_fd(fd, top, top_st.st_dev, failures, 0)
    finally:
        os.close(fd)
    try:
        os.rmdir(top)
    except OSError as e:
        failures.append((top, e.strerror or type(e).__name__))
    return freed


def remove(path, root, within=None) -> int:
    """Delete `path` inside root/within without ever following a link; returns the bytes of real files freed.
    RemoveIncomplete (a Guidance, with `freed` and `failures`) when some items could not be removed."""
    t = _resolve_for_remove(path, root, within)
    if t is None:
        return 0
    p = t.given
    try:
        st = os.lstat(p)
    except FileNotFoundError:
        return 0
    failures = []
    if _st_is_link(st):
        try:
            _unlink_link(p, st)
        except OSError as e:
            raise RemoveIncomplete(0, [(p, e.strerror or type(e).__name__)]) from None
        return 0
    if not stat.S_ISDIR(st.st_mode):
        try:
            return _unlink_file(p, st)
        except OSError as e:
            raise RemoveIncomplete(0, [(p, e.strerror or type(e).__name__)]) from None
    freed = _rm_windows(p, st, failures) if sys.platform == "win32" else _rm_posix(p, st, failures)
    if failures:
        raise RemoveIncomplete(freed, failures)
    return freed


def _resolve_for_remove(path, root, within) -> _Target | None:
    """Like _resolve, but the last part may itself be a link (it is removed as a name) and may be missing."""
    root_abs = os.path.abspath(os.fspath(root))
    _check_raw(path, root_abs)
    raw = os.fspath(path)
    p_abs = os.path.abspath(raw if os.path.isabs(raw) else os.path.join(root_abs, raw))
    if not _scope_parent_ok(p_abs, root_abs, within):
        raise _refuse("that path is outside the folder this command may delete in", p_abs)
    d = os.path.dirname(p_abs)
    if _norm(d) in (_norm(root_abs), _norm(os.path.realpath(root_abs))):
        parent = _Target(d, os.path.realpath(d), d, [])      # a direct child of the root (the root may be a link)
    else:
        parent = _resolve(d, root, within, allow_scope=True)
    if not os.path.lexists(p_abs):
        return None
    return _Target(p_abs, os.path.realpath(p_abs), parent.base, parent.parts + [os.path.basename(p_abs)])


def _scope_parent_ok(p_abs: str, root_abs: str, within) -> bool:
    """The item must be strictly below root/within, so neither the root nor the scope itself is ever removed."""
    for base in (root_abs, os.path.realpath(root_abs)):
        if not _inside(p_abs, base):
            continue
        parts = os.path.relpath(p_abs, base).split(os.sep)
        if not within:
            return True
        scope = [s for s in str(within).replace("\\", "/").split("/") if s]
        return len(parts) > len(scope) and [_norm(a) for a in parts[:len(scope)]] == [_norm(b) for b in scope]
    return False
