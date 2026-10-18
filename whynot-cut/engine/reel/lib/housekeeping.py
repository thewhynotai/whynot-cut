# SPDX-License-Identifier: GPL-3.0-or-later
# © 2026 The Why Not AI (thewhynot.ai)
"""Engine "Free up space" (Phase 4 Task 15, T4.15): `reel clean`, the doctor's disk summary and the cache cap after a
handoff. The panel's "Free up space" button and uninstall's model removal call the same functions.

Deleting is a way to lose data, so every removal is bounded five ways:
  * dry run by default: `scan()` and `clean()` without `apply` only read (no lock file, no stamp, nothing);
  * an ALLOWLIST of engine-home categories, never a denylist. The keys are stable (the panel's i18n table):
      cache_other    <home>/cache/* except uv and accel.json; an entry changed in the last 10 minutes is in use
      logs           old copies <home>/logs/*.log.N; a live *.log above 5 MB is rotated. serve's own logs (serve*.log,
                     its audit trail with its own rotation) and time-saved.jsonl are never touched
      runtimes_old   runtimes other than the current one and one previous, through runtime.prune; and a runtime
                     folder with neither pyvenv.cfg nor WHYNOT_RUNTIME (half removed earlier: «نسخة ناقصة /
                     half-removed»), through safe_remove
      venv_legacy    <home>/venv, only when the current runtime starts, is up to date, and this process is not the venv
      cuda_redist    <home>/cuda, only when the current runtime's torch/lib holds both cuBLAS libraries (T4.12)
      queues         stale Adobe queue files, through cep_queue.sweep (never the heartbeat or a build lock)
      model_partial  models/**/blobs/*.incomplete older than 24 h (a younger one may be downloading now)
      models_unused  with --models only: a Whisper model the engine knows that no one picks (the settings
                     whisper_model, transcription.json default_model and fallback_models, every shipped profile and
                     every client under the clients root: its preferences whisper_model and its reel-profile), not
                     used in the last 24 h (its last-used stamp) and not downloading; none at all while a GPU lock is
                     held or can't be checked, or while any of those profiles can't be read (fail closed). Any other
                     model folder is kept.
      uv_cache       with --uv-cache only (its own opt-in, never in --apply alone nor after a handoff): `uv cache clean`
                     on <home>/cache/uv; «التثبيت الجاي هيحمّل تاني / the next setup downloads it again». Kept while
                     reel setup builds a runtime, or when a link inside it points outside it. It runs last.
    `locks/` and models/.locks are not in the allowlist: a lock file removed under a waiting process breaks the lock;
  * real-path confinement through lib/linksafe.py: the anchor is the engine home's REAL path (the home may itself be
    a junction); a link is removed as a name and never entered (COORDINATION rule 15, the 2026-10-14 incident);
  * never a client folder: a path in (or holding) the clients root, or a tree holding a folder with both assets/
    and data/, is refused even when no clients root is set; the whole run is refused when the engine home itself
    looks like a client folder, sits inside one, or is in (or holds) the clients root;
  * one item never stops the others: a locked file, a refused path or a failing uv is that item's `error` line.
"""
from __future__ import annotations

import contextlib
import datetime as _dt
import os
import re
import stat
import subprocess
import sys
import time
from pathlib import Path

from . import linksafe, plat, runtime
from .client_move_paths import FOLD_CASE, _is_client, inside
from .errors import Guidance

KEYS = ("cache_other", "logs", "runtimes_old", "venv_legacy", "cuda_redist", "queues", "model_partial",
        "models_unused", "uv_cache")     # the opt-in uv step last: it is the slow one (scan-to-apply windows stay short)
CACHE_CAP = 2 * 1024 ** 3        # auto_prune's default cap for <home>/cache
LOG_MAX = 5_000_000              # a live log above this is rotated
LOG_KEEP = 3                     # rotated copies kept by rotate_logs
FRESH_S = 600                    # a cache entry changed this recently is being written by a running step
PARTIAL_AGE_S = 24 * 3600        # a younger *.incomplete may be a download running in another session
MODEL_RECENT_S = 24 * 3600       # a model loaded this recently is in use (the CPU lane holds no GPU lock)
UV_TIMEOUT_S = 900               # reel clean --uv-cache: the editor asked and waits
STAMP = ".whynot-last-used"      # written into a model folder by the Whisper loader (mark_model_used)
HALF = "نسخة ناقصة / half-removed"                                   # ruling Q4: the dry-run line of a broken runtime
UV_AGAIN = "التثبيت الجاي هيحمّل تاني (~{mb} MB) / the next setup downloads it again"    # ruling Q1
_MAX_DEPTH = 256                 # deeper than this, a tree is refused instead of half removed
_LEGACY_REPOS = ("mobiuslabsgmbh/faster-whisper-large-v3-turbo",)   # large-v3-turbo's old repo (whisper_backends)
_REPARSE_POINT = 0x400
_FOLD = FOLD_CASE                # Windows / macOS: a runtime id written in another case names the same folder
_LOG_COPY = re.compile(r"^.+\.log\.\d+$", re.IGNORECASE)
_HOW_CLIENT = "the engine never deletes a client folder; move it out of the engine home by hand"
_PATHS = {"cache_other": ("cache",), "logs": ("logs",), "runtimes_old": ("runtimes",), "venv_legacy": ("venv",),
          "cuda_redist": ("cuda",), "queues": (), "model_partial": ("models",), "models_unused": ("models",),
          "uv_cache": ("cache", "uv")}


# ------------------------------------------------------------------------------------------------ small helpers
def _anchor(home=None) -> Path:
    """The engine home's REAL path: the trust anchor for every removal (the home itself may be a junction)."""
    return Path(os.path.realpath(os.path.abspath(os.fspath(home or plat.engine_home()))))


def _norm(p) -> str:
    return os.path.normcase(os.path.normpath(os.fspath(p)))


def _is_link(p) -> bool:
    """linksafe.is_link, failing closed: a path whose kind can't be read counts as a link (never entered)."""
    try:
        return linksafe.is_link(p)
    except Guidance:
        return True


def _link_st(p, st) -> bool:
    """From an lstat: a symlink, or a reparse point that linksafe calls a link (a OneDrive placeholder is not)."""
    if stat.S_ISLNK(st.st_mode) or getattr(st, "st_file_attributes", 0) & _REPARSE_POINT:
        return _is_link(p)
    return False


def _client_shaped(d: str) -> bool:
    return os.path.lexists(os.path.join(d, "assets")) and os.path.lexists(os.path.join(d, "data"))


def _measure(path, links: list | None = None) -> dict:
    """Walk `path` without entering any link: {bytes (real files with one name; a hard link frees nothing), newest
    (mtime of the newest real entry; 0 for a link), client (the first folder holding assets/ and data/), too_deep}.
    `links` (a list) collects every link met, as a path (never followed)."""
    out = {"bytes": 0, "newest": 0.0, "client": None, "too_deep": False}
    p = os.fspath(path)
    try:
        st = os.lstat(p)
    except FileNotFoundError:
        return out
    if _link_st(p, st):
        if links is not None:
            links.append(p)
        return out
    if not stat.S_ISDIR(st.st_mode):
        out["bytes"] = st.st_size if st.st_nlink <= 1 else 0
        out["newest"] = st.st_mtime
        return out
    stack = [(p, st, 0)]
    while stack:
        d, dst, depth = stack.pop()
        if depth > _MAX_DEPTH:
            out["too_deep"] = True
            continue
        out["newest"] = max(out["newest"], dst.st_mtime)
        if out["client"] is None and _client_shaped(d):
            out["client"] = d
        try:
            names = [e.name for e in os.scandir(d)]
        except OSError:
            continue                                   # unreadable: linksafe reports it if a removal reaches it
        for name in names:
            c = os.path.join(d, name)
            try:
                cst = os.lstat(c)
            except OSError:
                continue
            if _link_st(c, cst):
                if links is not None:
                    links.append(c)
                continue
            if stat.S_ISDIR(cst.st_mode):
                stack.append((c, cst, depth + 1))
            else:
                out["newest"] = max(out["newest"], cst.st_mtime)
                if stat.S_ISREG(cst.st_mode) and cst.st_nlink <= 1:
                    out["bytes"] += cst.st_size
    return out


def _entries(d: Path) -> list[Path]:
    try:
        return sorted((Path(e.path) for e in os.scandir(d)), key=lambda p: p.name)
    except OSError:
        return []


def _plain_dir(d: Path) -> bool:
    """An existing folder that is not a link."""
    return os.path.isdir(d) and not _is_link(d)


def _line(e: BaseException, name: str | None = None) -> str:
    """One plain line for an item's error (never a traceback)."""
    if isinstance(e, linksafe.RemoveIncomplete):
        first = e.failures[0] if e.failures else ("?", "?")
        msg = (f"{len(e.failures)} item(s) could not be removed, e.g. {os.path.basename(first[0])} ({first[1]}); "
               "close the program that holds them, then try again")
    elif isinstance(e, Guidance):
        msg = e.error
    elif isinstance(e, OSError):
        msg = e.strerror or type(e).__name__
    else:
        msg = f"{type(e).__name__}: {e}"
    return f"{name}: {msg}" if name else msg


def _clients_root() -> Path | None:
    """The clients folder's real path, or None when none is set."""
    from .common import clients_root
    try:
        cr = clients_root()
    except (OSError, ValueError, TypeError) as e:
        raise Guidance(f"can't read the clients folder setting ({type(e).__name__})",
                       "fix the clients_root preference (reel settings), then try again") from None
    return Path(os.path.realpath(os.path.abspath(os.fspath(cr)))) if cr else None


def _os_key() -> str:
    return "windows" if plat.IS_WIN else "mac" if sys.platform == "darwin" else "linux"


# ------------------------------------------------------------------------------------------------ the one remover
def safe_remove(path, home_real, within: str | None = None) -> int:
    """Remove `path` (absolute, or relative to the home) and return the bytes freed. Built on linksafe.remove (the
    walk, the confinement, links removed as names); this adds the clients refusal and the client-shape check.
    Guidance when the path is the home itself, outside it (or outside `within`), behind a link, in or holding the
    clients root, holds a folder with assets/ and data/, or is nested too deep to check. linksafe.RemoveIncomplete
    (a Guidance with .freed and .failures) when some entries could not be removed."""
    a = os.fspath(_anchor(home_real))
    raw = os.fspath(path)
    p_abs = os.path.abspath(raw if os.path.isabs(raw) else os.path.join(a, raw))
    if _norm(p_abs) == _norm(a) or _norm(os.path.realpath(p_abs)) == _norm(a):
        raise Guidance("that is the engine home itself", "remove single items with reel clean", where=p_abs)
    if not os.path.lexists(p_abs):
        return linksafe.remove(p_abs, a, within)       # refuses a path outside the home; else nothing to do
    link = _is_link(p_abs)
    if link:                                           # a name in the home; its target is never looked at
        where = os.path.join(os.fspath(linksafe.confine(os.path.dirname(p_abs), a))
                             if _norm(os.path.dirname(p_abs)) != _norm(a) else a, os.path.basename(p_abs))
    else:
        where = os.fspath(linksafe.confine(p_abs, a, within))
    cr = _clients_root()
    if cr is not None and (inside(where, cr) or inside(cr, where)):
        raise Guidance("that path is in (or holds) the clients folder", _HOW_CLIENT, where=where)
    if not link:
        t = _measure(where)
        if t["too_deep"]:
            raise Guidance("folders nested too deep to check safely", "remove it by hand", where=where)
        if t["client"]:
            rel = os.path.relpath(t["client"], a)
            raise Guidance(f"{rel} holds a folder with assets/ and data/ (it may be a client folder)", _HOW_CLIENT,
                           where=t["client"])
    return linksafe.remove(p_abs, a, within)


# ------------------------------------------------------------------------------------------------ items
def _item(key: str, a: Path, nbytes: int = 0, removable: bool = False, why: str = "", do=None,
          problem: str | None = None) -> dict:
    return {"key": key, "path": str(a.joinpath(*_PATHS[key])), "bytes": int(nbytes), "removable": bool(removable),
            "why": why, "_do": do, "_problem": problem}


def _remove_all(targets, a: Path, within: str | None, extra=None, still=None):
    """A `_do` for a list of paths: (bytes removed, error line or None); every target is tried. `still(path)` is
    asked again right before each removal (the scan may be minutes old): False keeps that target."""
    def do():
        freed, errs = 0, []
        for p in targets:
            if still is not None and not still(p):
                continue
            try:
                freed += safe_remove(p, a, within)
            except linksafe.RemoveIncomplete as e:
                freed += e.freed
                errs.append(_line(e, p.name))
            except (Guidance, OSError) as e:
                errs.append(_line(e, p.name))
        if extra:
            more = extra()
            if more:
                errs.append(more)
        return freed, "; ".join(errs) or None
    return do


def _uv_exe(a: Path) -> Path | None:
    exe = a / "bin" / ("uv.exe" if plat.IS_WIN else "uv")
    if not os.path.lexists(exe):
        return None
    try:
        real = linksafe.confine(exe, a, within="bin")
    except Guidance:
        return None
    return real if real.is_file() else None


def _uv_clean(uv: Path, cache_dir: Path, timeout: float = UV_TIMEOUT_S):
    """`uv cache clean` on the engine's own uv cache: an argv list, no shell, no user config, bounded. (`uv cache
    prune` is not used: everything a runtime installed stays reachable, so it frees nothing; ruling Q1.)"""
    env = dict(os.environ, UV_CACHE_DIR=str(cache_dir), UV_NO_CONFIG="1")
    kw = {"creationflags": getattr(subprocess, "CREATE_NO_WINDOW", 0)} if plat.IS_WIN else {}
    how = "run reel setup to repair uv, then try again"
    try:
        r = subprocess.run([str(uv), "cache", "clean"], env=env, stdin=subprocess.DEVNULL, capture_output=True,
                           timeout=timeout, **kw)
    except subprocess.TimeoutExpired:
        raise Guidance(f"uv cache clean did not finish in {timeout:g} s (another uv may hold its cache)", how) from None
    except OSError as e:
        raise Guidance(f"uv could not start ({e.strerror or type(e).__name__})", how) from None
    if r.returncode != 0:
        tail = (r.stderr or b"").decode("utf-8", "replace").strip().splitlines()[-1:] or [""]
        raise Guidance(f"uv cache clean failed (exit {r.returncode}) {tail[0][:200]}".strip(), how)


def _uv_again(nbytes: int) -> str:
    """The ruling-Q1 line with the size in MB (at least 1 when anything is there)."""
    return UV_AGAIN.format(mb=max(1, round(nbytes / 1_000_000)) if nbytes else 0)


def _link_leaving(links: list, top) -> str | None:
    """The first of `links` whose target is outside `top` (both real), as a name; a target that can't be resolved
    counts as outside (fail closed)."""
    real = os.path.realpath(os.fspath(top))
    for p in links:
        try:
            t = os.path.realpath(p)
        except (OSError, ValueError):
            return os.path.basename(p)
        if not inside(t, real):
            return os.path.basename(p)
    return None


def _uv_cache_item(a: Path, opts: dict, now: float) -> dict:
    d = a / "cache" / "uv"
    if not os.path.lexists(d):
        return _item("uv_cache", a, 0, False, "no uv cache")
    if _is_link(a / "cache") or _is_link(d):
        return _item("uv_cache", a, 0, False, "kept: the cache folder is a link",
                     problem="cache/uv: a link; nothing is removed through it")
    links: list = []
    size = _measure(d, links)["bytes"]
    again = _uv_again(size)
    out = _link_leaving(links, d)
    if out:
        return _item("uv_cache", a, size, False, f"kept: {out} inside the uv cache is a link to outside it, and uv "
                     f"deletes its cache itself (remove that link by hand); {again}")
    uv = _uv_exe(a)
    if uv is None:
        return _item("uv_cache", a, size, False, "kept: uv is missing, and only uv itself cleans its cache "
                     f"(reel setup brings uv back); {again}")
    if _building(a / "runtimes"):
        return _item("uv_cache", a, size, False, f"kept: reel setup is building a runtime now (it uses this cache); "
                     f"{again}")
    if not opts.get("uv_cache"):
        return _item("uv_cache", a, size, False,
                     f"only with --uv-cache and the editor's yes: uv's downloaded packages; {again}")

    def do():
        if _building(a / "runtimes"):
            return 0, "reel setup started building a runtime meanwhile; the uv cache was not cleaned (run reel clean again)"
        now_links: list = []
        _measure(d, now_links)
        if _is_link(a / "cache") or not _plain_dir(d) or _link_leaving(now_links, d):
            return 0, "the uv cache changed meanwhile (a link appeared); it was not cleaned"
        _uv_clean(uv, Path(os.path.realpath(d)))
        return max(0, size - _measure(d)["bytes"]), None
    return _item("uv_cache", a, size, True, f"uv's downloaded packages (uv cache clean); {again}", do)


def _cache_entries(a: Path, now: float):
    """cache_other's candidates: (path, measure) for every entry but uv and accel.json; (fresh ones flagged)."""
    out = []
    for p in _entries(a / "cache"):
        if p.name.casefold() in ("uv", "accel.json"):
            continue
        out.append((p, _measure(p)))
    return out


def _cache_other_item(a: Path, opts: dict, now: float) -> dict:
    c = a / "cache"
    if not os.path.lexists(c):
        return _item("cache_other", a, 0, False, "no cache folder")
    if _is_link(c):
        return _item("cache_other", a, 0, False, "kept: the cache folder is a link",
                     problem="cache: a link; nothing is removed through it")
    go, fresh = [], 0
    for p, t in _cache_entries(a, now):
        if _fresh(t, now):
            fresh += 1
            continue
        go.append((p, t["bytes"]))
    why = "rebuilt when needed (font index, downloads, scratch)" + (
        f"; {fresh} entr{'y' if fresh == 1 else 'ies'} changed in the last 10 minutes kept (in use)" if fresh else "")
    return _item("cache_other", a, sum(b for _, b in go), bool(go), why,
                 _remove_all([p for p, _ in go], a, "cache", still=lambda p: not _fresh(_measure(p), time.time())))


def _fresh(t: dict, now: float) -> bool:
    """A cache entry some step changed in the last FRESH_S seconds (being written now)."""
    return bool(t["newest"]) and now - t["newest"] < FRESH_S


def _serve_log(name: str) -> bool:
    return name.casefold().startswith("serve")


def _logs_item(a: Path, opts: dict, now: float) -> dict:
    d = a / "logs"
    if not os.path.lexists(d):
        return _item("logs", a, 0, False, "no logs folder")
    if _is_link(d):
        return _item("logs", a, 0, False, "kept: the logs folder is a link",
                     problem="logs: a link; nothing is removed through it")
    copies, big = [], []
    for p in _entries(d):
        if _serve_log(p.name):
            continue
        try:
            st = os.lstat(p)
        except OSError:
            continue
        if _link_st(p, st) or not stat.S_ISREG(st.st_mode):
            continue
        if _LOG_COPY.match(p.name):
            copies.append((p, st.st_size))
        elif p.name.casefold().endswith(".log") and st.st_size > LOG_MAX:
            big.append(p.name)

    def rotate():
        done = rotate_logs(d, LOG_MAX, LOG_KEEP)
        left = [n for n in big if n not in done]
        return f"{', '.join(left)}: in use; rotated next time" if left else None
    why = "old log copies; the live logs stay (a log above 5 MB is rotated); serve's logs are its own"
    return _item("logs", a, sum(b for _, b in copies), bool(copies or big), why,
                 _remove_all([p for p, _ in copies], a, "logs", rotate))


def _runtime_status(a: Path) -> dict:
    st = runtime.status(a)
    return st if isinstance(st, dict) else {}


def _current_ok(st: dict) -> bool:
    return st.get("kind") == "runtime" and bool(st.get("id")) and not st.get("broken") and bool(st.get("up_to_date"))


def _keep_runtimes(d: Path, current: str) -> set[str]:
    """Current + one previous for rollback. setup_env.keep_runtimes keeps the runtime `current` named before the
    switch; that name is not recorded, so the previous one here is the newest COMPLETED other runtime (its
    WHYNOT_RUNTIME stamp is written only after an install passed, so an abandoned build never wins), by the stamp's
    created_at, else the folder time; with no completed one, the newest other runtime. `current` is matched
    case-folded on Windows/macOS (`R-CUR` names the folder `r-cur`), and the folder's own name is returned."""
    done, other = [], []
    for p in _entries(d):
        if _same_id(p.name, current):
            current = p.name
            continue
        if p.name.startswith(".") or p.name.endswith(".building") or not _plain_dir(p):
            continue
        if not (p / "pyvenv.cfg").is_file():
            continue
        try:
            mtime = p.stat().st_mtime
        except OSError:
            continue
        other.append((mtime, p.name))
        st = runtime.read_stamp(p)["runtime"]
        if st:
            done.append((str(st.get("created_at") or ""), mtime, p.name))
    prev = max(done)[2] if done else max(other)[1] if other else None
    return {current} | ({prev} if prev else set())


def _same_id(x: str, y: str) -> bool:
    return x.casefold() == y.casefold() if _FOLD else x == y


def _is_half(p: Path) -> bool:
    """A runtime folder with neither its pyvenv.cfg nor its WHYNOT_RUNTIME stamp: an earlier removal stopped half way
    (a file was locked), it can't start, and runtime.prune no longer sees it (ruling Q4)."""
    return _plain_dir(p) and not os.path.lexists(p / "pyvenv.cfg") and not os.path.lexists(p / runtime.STAMP)


def _half_runtimes(d: Path, keep: set[str], current: str) -> list[Path]:
    """The half-removed runtime folders: a valid runtime id, never `current` or the kept previous one, never a
    link (runtime.prune unlinks those as names)."""
    out = []
    for p in _entries(d):
        n = p.name
        if n.startswith(".") or n.endswith(".building") or not plat._RUNTIME_ID.match(n) or ".." in n:
            continue
        if _same_id(n, current) or any(_same_id(n, k) for k in keep):
            continue
        if _is_half(p):
            out.append(p)
    return out


def _building(d: Path) -> bool:
    """A runtime is being built now (reel setup's .<id>.building lock)."""
    return any(p.name.startswith(".") and p.name.endswith(".building") for p in _entries(d))


def _prune_is_link_safe() -> bool:
    """runtime.prune removes through linksafe and has a candidates-only mode (hooks/T4.15 runtime.py.patch)."""
    return bool(getattr(runtime, "PRUNE_LINK_SAFE", False))


def _runtimes_old_item(a: Path, opts: dict, now: float) -> dict:
    d = a / "runtimes"
    if not os.path.lexists(d):
        return _item("runtimes_old", a, 0, False, "no runtimes folder")
    if _is_link(d):
        return _item("runtimes_old", a, 0, False, "kept: the runtimes folder is a link",
                     problem="runtimes: a link; nothing is removed through it")
    st = _runtime_status(a)
    current = st.get("id") if st.get("kind") == "runtime" and not st.get("broken") else None
    if not current:
        size = sum(_measure(p)["bytes"] for p in _entries(d) if _plain_dir(p))
        return _item("runtimes_old", a, size, False, "kept: no working current runtime, so every runtime stays")
    keep = _keep_runtimes(d, current)
    half = {p.name: _measure(p)["bytes"] for p in _half_runtimes(d, keep, current)}
    others = sum(_measure(p)["bytes"] for p in _entries(d)
                 if p.name not in keep and p.name not in half and _plain_dir(p))
    if _building(d):
        return _item("runtimes_old", a, others + sum(half.values()), False,
                     "kept: reel setup is building a runtime now")
    link_safe = _prune_is_link_safe()
    if not link_safe and not half:
        return _item("runtimes_old", a, others, False, "kept: this engine's runtime cleanup is not the link-safe one "
                     "yet; reel setup removes old runtimes")
    cands = [r for r in (runtime.prune(a, keep, dry_run=True).get("removed") or []) if r not in half] \
        if link_safe else []
    sizes = {rid: _measure(d / rid)["bytes"] for rid in cands}
    why = f"runtimes other than the current one and one previous (kept: {', '.join(sorted(keep))})"
    if half:
        why += f"; {HALF}: {', '.join(sorted(half))} (an earlier removal stopped half way; it can't start)"
    if not link_safe and others:
        why += "; the complete old runtimes stay: this engine's runtime cleanup is not the link-safe one yet"

    def still_half(p: Path) -> bool:        # right before removal: setup may have rebuilt it or made it current
        cur = plat.current_runtime_id(a) or current
        return _is_half(p) and not _same_id(p.name, cur) and not any(
            _same_id(p.name, k) for k in _keep_runtimes(d, current))

    def do():
        st2 = _runtime_status(a)            # the scan may be minutes old: setup may have switched `current` since
        cur2 = st2.get("id") if st2.get("kind") == "runtime" and not st2.get("broken") else None
        if cur2 != current or _building(d):
            return 0, "reel setup changed the runtimes meanwhile; nothing removed (run reel clean again)"
        freed, errs = 0, []
        if cands:
            res = runtime.prune(a, _keep_runtimes(d, current), dry_run=False)
            errs += [f"{rid}: {why}" for rid, why in sorted((res.get("failed") or {}).items())]
            freed += sum(sizes.get(rid, 0) for rid in res.get("removed") or [])
        if half:
            got, err = _remove_all([d / n for n in sorted(half)], a, plat.RUNTIMES_DIR, still=still_half)()
            freed += got
            errs += [err] if err else []
        return freed, "; ".join(errs) or None
    return _item("runtimes_old", a, sum(sizes.values()) + sum(half.values()), bool(cands or half), why, do)


def _venv_item(a: Path, opts: dict, now: float) -> dict:
    d = a / "venv"
    if not os.path.lexists(d):
        return _item("venv_legacy", a, 0, False, "no legacy venv")
    size = _measure(d)["bytes"]
    st = _runtime_status(a)
    if not _current_ok(st):
        return _item("venv_legacy", a, size, False, "kept: the engine still needs it (no up-to-date runtime that "
                     "starts; reel setup builds one)")
    if inside(os.path.realpath(sys.prefix), os.path.realpath(d)):
        return _item("venv_legacy", a, size, False, "kept: this command runs from it")
    if not _found_without_venv(a):
        return _item("venv_legacy", a, size, False, "kept: the engine finds this home through its venv folder (an "
                     "older install's home); removing it would move the engine to an empty home")
    return _item("venv_legacy", a, size, True, "the old 2.x environment; the current runtime replaces it",
                 _remove_all([d], a, None, still=lambda p: _current_ok(_runtime_status(a))))


def _same_home(p, a: Path) -> bool:
    return _norm(os.path.realpath(os.path.abspath(os.fspath(p)))) == _norm(a)


def _found_without_venv(a: Path) -> bool:
    """Would plat.engine_home() (and bin/reel, same order) still find this home with no venv/ in it, from ANY
    launcher? Only the persistent sources count: the saved plugin option names it, or it is ~/.whynot-cut with a
    `current` file. An environment variable lives only in the process that has it (the Adobe bridge or a fresh
    terminal may not), and a legacy home (~/.reel-editor ...) is found only through its venv/."""
    saved = plat.saved_options().get("engine_home")
    if saved:
        return _same_home(Path(plat.native_path(saved)).expanduser(), a)
    new = Path.home() / plat.HOME_NAME
    return _same_home(new, a) and (new / plat.CURRENT_FILE).is_file()


def _torch_lib_dirs(rt: Path, key: str) -> list[Path]:
    if key == "windows":
        return [rt / "Lib" / "site-packages" / "torch" / "lib"]
    return sorted(rt.glob("lib/python*/site-packages/torch/lib"))


def _cuda_item(a: Path, opts: dict, now: float) -> dict:
    d = a / "cuda"
    if not os.path.lexists(d):
        return _item("cuda_redist", a, 0, False, "no separate CUDA download")
    size = _measure(d)["bytes"]
    key = _os_key()
    libs = plat.CUDA_LIBS.get(key)
    st = _runtime_status(a)
    if not libs:
        return _item("cuda_redist", a, size, False, "kept: no NVIDIA CUDA on this system")
    if not _current_ok(st) or not st.get("dir"):
        return _item("cuda_redist", a, size, False, "kept: no up-to-date runtime that carries its own CUDA libraries")
    if not any(all((t / n).is_file() for n in libs) for t in _torch_lib_dirs(Path(st["dir"]), key)):
        return _item("cuda_redist", a, size, False, "kept: the current runtime does not carry cuBLAS, so Whisper on "
                     "the NVIDIA GPU needs this download")
    return _item("cuda_redist", a, size, True, "the current runtime carries the same CUDA libraries (torch/lib)",
                 _remove_all([d], a, None, still=lambda p: _current_ok(_runtime_status(a))))


def _queues_item(a: Path, opts: dict, now: float) -> dict:
    from . import cep_queue
    stale, problems, queues = {}, [], []
    for name in ("ppro-queue", "ae-queue"):
        q = a / name
        if not os.path.lexists(q):
            continue
        if _is_link(q):
            problems.append(f"{name}: a link; nothing is removed through it")
            continue
        queues.append(q)
        for p in _entries(q):
            try:
                st = os.lstat(p)
            except OSError:
                continue
            if stat.S_ISDIR(st.st_mode) or not p.name.endswith(cep_queue._SWEEP_SUFFIXES):
                continue
            if now - st.st_mtime > cep_queue.SWEEP_AGE_S:
                stale[(name, p.name)] = st.st_size if stat.S_ISREG(st.st_mode) and st.st_nlink <= 1 else 0

    def do():
        freed, errs = 0, []
        for q in queues:
            try:
                real = linksafe.confine(q, a)
            except Guidance as e:
                errs.append(_line(e, q.name))
                continue
            gone = set(cep_queue.sweep(real))
            freed += sum(b for (qn, n), b in stale.items() if qn == q.name and n in gone)
            left = [n for (qn, n) in stale if qn == q.name and n not in gone and os.path.lexists(real / n)]
            if left:
                errs.append(f"{q.name}: {len(left)} file(s) could not be removed (in use), e.g. {sorted(left)[0]}")
        return freed, "; ".join(errs) or None
    return _item("queues", a, sum(stale.values()), bool(stale),
                 "leftovers of Premiere / After Effects jobs older than a day (never the heartbeat or a build lock)",
                 do, "; ".join(problems) or None)


def _walk_files(top: Path):
    """(path, lstat) for every real file under top; links are never entered, depth is bounded."""
    stack = [(os.fspath(top), 0)]
    while stack:
        d, depth = stack.pop()
        if depth > _MAX_DEPTH:
            continue
        try:
            names = sorted(e.name for e in os.scandir(d))
        except OSError:
            continue
        for n in names:
            p = os.path.join(d, n)
            try:
                st = os.lstat(p)
            except OSError:
                continue
            if _link_st(p, st):
                continue
            if stat.S_ISDIR(st.st_mode):
                stack.append((p, depth + 1))
            elif stat.S_ISREG(st.st_mode):
                yield Path(p), st


def _model_partial_item(a: Path, opts: dict, now: float) -> dict:
    m = a / "models"
    if not os.path.lexists(m):
        return _item("model_partial", a, 0, False, "no models folder")
    if _is_link(m):
        return _item("model_partial", a, 0, False, "kept: the models folder is a link",
                     problem="models: a link; nothing is removed through it")
    go = [(p, st.st_size if st.st_nlink <= 1 else 0) for p, st in _walk_files(m)
          if p.name.endswith(".incomplete") and p.parent.name == "blobs" and now - st.st_mtime > PARTIAL_AGE_S]
    return _item("model_partial", a, sum(b for _, b in go), bool(go),
                 "unfinished model downloads older than a day (a newer one may be downloading now)",
                 _remove_all([p for p, _ in go], a, "models", still=lambda p: _old_partial(p, time.time())))


def _old_partial(p: Path, now: float) -> bool:
    try:
        st = os.lstat(p)
    except OSError:
        return False
    return stat.S_ISREG(st.st_mode) and now - st.st_mtime > PARTIAL_AGE_S


def _folder(repo: str) -> str:
    return "models--" + repo.replace("/", "--")


def _whisper_repos() -> dict[str, str]:
    """{repo folder (casefolded): model name} for every Whisper model the engine downloads."""
    from .whisper_backends import CT2_REPOS, MLX_REPOS
    out = {}
    for table in (CT2_REPOS, MLX_REPOS):
        for name, repo in table.items():
            out[_folder(repo).casefold()] = name
    for repo in _LEGACY_REPOS:
        out[_folder(repo).casefold()] = "large-v3-turbo"
    return out


def _model_names(v) -> list[str]:
    """A model name or a list of them, as given in a config or a preferences file."""
    vals = v if isinstance(v, (list, tuple)) else [v]
    return [x.strip() for x in vals if isinstance(x, str) and x.strip()]


def _client_models(d: Path, add) -> str | None:
    """Every model the client folder `d` picks (its preferences whisper_model, any layer; its reel-profile and the
    shipped profile that one names: default_model + fallback_models), passed to add(name, where). A file that can't
    be read gives its reason (the caller then removes no model)."""
    from . import common, settings as S
    where = f"client {d.name}"
    try:
        for _layer, f in S.layer_files(d):
            vals, _body, probs = S.read_file(f)
            if any(p.startswith("unreadable") or "not UTF-8" in p for p in probs):
                return f"its preferences file {f.name} can't be read as UTF-8 text"
            for n in _model_names(vals.get("whisper_model")):
                add(n, where)
        for n in _model_names(S.load(d).get("whisper_model")):
            add(n, where)
        cfg = common.Context(root=d).config("transcription.json")
    except (OSError, ValueError) as e:            # common.read_json: FileFormatError is a ValueError
        return _line(e)
    for n in _model_names(cfg.get("default_model")) + _model_names(cfg.get("fallback_models")):
        add(n, where)
    return None


def _wanted_models() -> tuple[dict[str, str], str | None]:
    """({model name: who picks it}, problem). Ruling Q3: the settings whisper_model, transcription.json default_model
    and fallback_models (the default chain), every shipped profile's, and every client's under the clients root (its
    preferences and its reel-profile). `problem` (any of them can't be read, the clients folder is set but can't be
    listed: an unplugged disk) means no model may be removed: fail closed."""
    from . import common, settings as S
    want: dict[str, str] = {}

    def add(n: str, where: str):
        want.setdefault(n, where)
    try:
        for n in _model_names(S.load().get("whisper_model") or "large-v3"):
            add(n, "settings")
        cfg = common.load_config("transcription.json")
    except (OSError, ValueError) as e:
        return want, f"the engine's transcription settings can't be read ({_line(e)})"
    for n in _model_names(cfg.get("default_model")):
        add(n, "the default model")
    for n in _model_names(cfg.get("fallback_models")):
        add(n, "a fallback model")
    shipped = Path(common.PROFILES_DIR)
    try:
        profiles = sorted(p for p in shipped.iterdir() if p.is_dir() and not p.name.startswith(("_", "."))) \
            if shipped.is_dir() else []
        for p in profiles:
            pc = common.read_json(p / "transcription.json", {}) or {}
            for n in _model_names(pc.get("default_model")) + _model_names(pc.get("fallback_models")):
                add(n, f"profile {p.name}")
    except (OSError, ValueError) as e:
        return want, f"a shipped profile can't be read ({_line(e)})"
    try:
        cr = _clients_root()
    except Guidance as e:
        return want, e.error
    if cr is None:
        return want, None
    try:
        kids = sorted(p for p in cr.iterdir() if (p / "assets").is_dir() and (p / "data").is_dir())
    except OSError as e:
        return want, f"the clients folder {cr.name} can't be read ({_line(e)}; is its disk plugged in?)"
    for d in kids:
        why = _client_models(d, add)
        if why:
            return want, f"the client profile of {d.name} can't be read ({why})"
    return want, None


def _gpu_held(a: Path) -> str | None:
    """Why a model must not be removed now, from the GPU locks of this home (None: free). Only probes a lock file that
    already exists (a dry run writes nothing); fails closed: a linked locks folder or lock file, or a lock that can't
    be checked, counts as held."""
    from . import file_lock, gpu_lock
    locks = a / "locks"
    if not os.path.lexists(locks):
        return None
    if _is_link(locks):
        return "the locks folder is a link, so the GPU lock can't be checked"
    for name in (gpu_lock.LOCK_GPU, gpu_lock.LOCK_MEDIA):
        lp = file_lock.lock_path(locks / name)
        if not os.path.lexists(lp):
            continue
        if _is_link(lp):
            return f"the GPU lock file {lp.name} is a link, so it can't be checked"
        try:
            with file_lock.locked(locks / name, wait_s=0):
                pass
        except file_lock.LockTimeout:
            return "a transcription or GPU job is running now (the GPU lock is held)"
        except (Guidance, OSError) as e:
            return f"the GPU lock can't be checked ({_line(e)})"
    return None


@contextlib.contextmanager
def _gpu_locks(a: Path):
    """Take both GPU locks of this home without waiting (apply only: the lock files may be created). Yields None
    when both are held by us, else the line saying what really failed (a job holds one, the locks folder is a
    link, the lock could not be taken)."""
    from . import file_lock, gpu_lock
    locks = a / "locks"
    if os.path.lexists(locks) and _is_link(locks):
        yield "the locks folder is a link; no model was removed"
        return
    with contextlib.ExitStack() as stack:
        try:
            linksafe.makedirs(locks, a)
            for name in (gpu_lock.LOCK_GPU, gpu_lock.LOCK_MEDIA):
                stack.enter_context(file_lock.locked(locks / name, wait_s=0))
        except file_lock.LockTimeout:
            why = "a GPU job started meanwhile; no model was removed"
        except (Guidance, OSError) as e:
            why = f"the GPU lock could not be taken ({_line(e)}); no model was removed"
        else:
            why = None
        yield why


def _recently_used(repo: Path, now: float) -> bool:
    try:
        st = os.lstat(repo / STAMP)
    except OSError:
        return False
    return not _link_st(repo / STAMP, st) and now - st.st_mtime < MODEL_RECENT_S


def _downloading(repo: Path, now: float) -> bool:
    for p in _entries(repo / "blobs"):
        try:
            if p.name.endswith(".incomplete") and now - os.lstat(p).st_mtime <= PARTIAL_AGE_S:
                return True
        except OSError:
            continue
    return False


def _model_verdicts(m: Path, now: float):
    """(candidates [(path, name, bytes)], kept [(name, why)], problem) for the folders directly under models/;
    `problem` (a profile can't be read) means none may go."""
    known = _whisper_repos()
    wanted, problem = _wanted_models()
    go, kept = [], []
    for p in _entries(m):
        if not p.name.startswith("models--") or not _plain_dir(p):
            continue
        name = known.get(p.name.casefold())
        if name is None:
            kept.append((p.name[len("models--"):].replace("--", "/"), "not a Whisper model the engine manages"))
        elif name in wanted:
            kept.append((name, f"in use: {wanted[name]}"))
        elif _recently_used(p, now):
            kept.append((name, "used in the last 24 h"))
        elif _downloading(p, now):
            kept.append((name, "a download is running"))
        else:
            go.append((p, name, _measure(p)["bytes"]))
    return go, kept, problem


def _models_unused_item(a: Path, opts: dict, now: float) -> dict:
    m = a / "models"
    if not os.path.lexists(m):
        return _item("models_unused", a, 0, False, "no models folder")
    if _is_link(m):
        return _item("models_unused", a, 0, False, "kept: the models folder is a link",
                     problem="models: a link; nothing is removed through it")
    go, kept, problem = _model_verdicts(m, now)
    size = sum(b for _, _, b in go)
    names = ", ".join(sorted({n for _, n, _ in go}))
    tail = "; kept: " + ", ".join(f"{n} ({w})" for n, w in sorted(kept)) if kept else ""
    if problem:
        return _item("models_unused", a, size, False, f"kept: {problem}, so no model is removed (a client may use "
                     "any of them)" + tail)
    held = _gpu_held(a)
    if held:
        return _item("models_unused", a, size, False, f"kept: {held}, so no model is removed" + tail)
    if not opts.get("models"):
        return _item("models_unused", a, size, False,
                     (f"only with --models and the editor's yes: {names}" if go else "only with --models") + tail)

    def do():
        with _gpu_locks(a) as why:      # held for the whole removal: no GPU job loads a model meanwhile
            if why:
                return 0, why
            later = time.time()         # re-checked under the lock: stamped or downloading since the scan stays
            targets = [p for p, _, _ in go if not _recently_used(p, later) and not _downloading(p, later)]
            return _remove_all(targets, a, "models")()
    return _item("models_unused", a, size, bool(go),
                 (f"Whisper models the engine does not use: {names}" if go else "every model is in use") + tail, do)


_BUILDERS = (("cache_other", "_cache_other_item"), ("logs", "_logs_item"), ("runtimes_old", "_runtimes_old_item"),
             ("venv_legacy", "_venv_item"), ("cuda_redist", "_cuda_item"), ("queues", "_queues_item"),
             ("model_partial", "_model_partial_item"), ("models_unused", "_models_unused_item"),
             ("uv_cache", "_uv_cache_item"))


def _home_refusal(a: Path) -> str | None:
    """Why nothing at all may be removed from this engine home (review P3-6): the per-item client check sees only
    each item's own tree, never the home or the folders above it. A home that looks like a client folder (assets/
    and data/), sits inside a WhyNot client folder, or is in (or holds) the clients root is refused whole."""
    if _client_shaped(os.fspath(a)):
        return "the engine home holds assets/ and data/ (it looks like a client folder); nothing is removed"
    for anc in a.parents:
        if _is_client(anc):
            return f"the engine home is inside a client folder ({anc.name}); nothing is removed"
    try:
        cr = _clients_root()
    except Guidance as e:
        return f"{e.error}; nothing is removed until the clients folder setting is fixed"
    if cr is not None and (inside(a, cr) or inside(cr, a)):
        return "the engine home is in (or holds) the clients folder; nothing is removed"
    return None


def _plan(a: Path, opts: dict) -> list[dict]:
    now = time.time()
    refusal = _home_refusal(a)
    if refusal:
        out = []
        for key in KEYS:
            it = _item(key, a, 0, False, "kept: " + refusal, problem=refusal)
            it["_failed"] = True
            out.append(it)
        return out
    out = []
    for key, fn in _BUILDERS:
        try:
            it = globals()[fn](a, opts, now)
        except Exception as e:  # noqa: BLE001  one item that can't be checked is its own error line, never a stop
            it = _item(key, a, 0, False, "could not be checked", problem=_line(e))
            it["_failed"] = True
        out.append(it)
    return out


# ------------------------------------------------------------------------------------------------ public API
def scan(home=None, *, models: bool = False, uv_cache: bool = False) -> dict:
    """What can go and how big it is (read-only): {"home", "total_bytes", "items": [{key, path, bytes, removable,
    why}]} in the KEYS order. `bytes` is reported for kept items too (the editor sees what a yes would free).
    models / uv_cache: the two opt-in items (each needs the editor's own yes)."""
    a = _anchor(home)
    items = [{k: v for k, v in it.items() if not k.startswith("_")}
             for it in _plan(a, {"models": bool(models), "uv_cache": bool(uv_cache)})]
    return {"home": str(a), "total_bytes": sum(i["bytes"] for i in items), "items": items}


def clean(home=None, *, apply: bool = False, models: bool = False, uv_cache: bool = False) -> dict:
    """The scan's items with `removed` bytes and an `error` line each; removes only with apply=True, models only with
    models=True, the uv cache only with uv_cache=True. Never raises for one item."""
    a = _anchor(home)
    items, freed, ok = [], 0, True
    for it in _plan(a, {"models": bool(models), "uv_cache": bool(uv_cache)}):
        do, err = it.pop("_do"), it.pop("_problem")
        ok = ok and not it.pop("_failed", False)       # an item that could not be checked is a failure
        removed = 0                                    # a kept link is a note (error line), not a failure
        if apply and it["removable"] and do is not None:
            try:
                removed, e2 = do()
            except Exception as e:  # noqa: BLE001  reported on the item, the other items still run
                e2 = _line(e)
            ok = ok and not e2
            err = "; ".join(x for x in (err, e2) if x) or None
        it.update(removed=int(removed), error=err)
        freed += removed
        items.append(it)
    return {"home": str(a), "apply": bool(apply), "models": bool(models), "uv_cache": bool(uv_cache), "ok": ok,
            "total_bytes": sum(i["bytes"] for i in items), "freed_bytes": freed, "items": items}


def rotate_logs(folder, max_bytes: int = LOG_MAX, keep: int = LOG_KEEP) -> list[str]:
    """Rotate every live `*.log` in `folder` above `max_bytes`: name.log -> name.log.1 -> ... -> name.log.<keep> (the
    oldest copy is dropped). serve's own logs, links and anything not `.log` are left alone; so is a log another
    program holds (Windows refuses the rename; it is rotated next time). Returns the names rotated."""
    d = Path(folder)
    if not os.path.isdir(d) or _is_link(d):
        return []
    keep = max(1, int(keep))
    out = []
    for p in _entries(d):
        n = p.name
        if not n.casefold().endswith(".log") or _serve_log(n):
            continue
        try:
            st = os.lstat(p)
        except OSError:
            continue
        if _link_st(p, st) or not stat.S_ISREG(st.st_mode) or st.st_size <= max_bytes:
            continue
        try:
            for i in range(keep - 1, 0, -1):
                src = d / f"{n}.{i}"
                if os.path.lexists(src):
                    os.replace(src, d / f"{n}.{i + 1}")
            os.replace(p, d / f"{n}.1")
        except OSError:
            continue                                   # in use: rotated on a later run
        out.append(n)
    return out


def auto_prune(home=None, *, cap_bytes: int = CACHE_CAP) -> dict:
    """After a handoff: when <home>/cache (the uv cache not counted) is over `cap_bytes`, cache_other entries go
    OLDEST FIRST until it is back under the cap (never everything; an entry in use now and accel.json stay); logs
    are rotated. The uv cache is never touched here: cleaning it is the editor's own opt-in (`reel clean --uv-cache`,
    ruling Q1), so it is reported as `uv_bytes` and stays outside the cap. Nothing at all when the home itself is
    refused (_home_refusal). Best effort: never raises; problems are in "errors"."""
    rep = {"cap_bytes": int(cap_bytes), "cache_bytes_before": 0, "cache_bytes_after": 0, "uv_bytes": 0,
           "removed": [], "freed": 0, "rotated": [], "errors": []}
    try:
        a = _anchor(home)
        refusal = _home_refusal(a)
        if refusal:
            rep["errors"].append(refusal)
            return rep
        c = a / "cache"
        if _plain_dir(c):
            def managed() -> tuple[int, int]:
                uv = _measure(c / "uv")["bytes"] if _plain_dir(c / "uv") else 0
                return max(0, _measure(c)["bytes"] - uv), uv
            total, rep["uv_bytes"] = managed()
            rep["cache_bytes_before"] = total
            if total > cap_bytes:
                now = time.time()
                entries = _cache_entries(a, now)
                old = sorted(((t["newest"], p.name, p, t["bytes"]) for p, t in entries if not _fresh(t, now)),
                             key=lambda x: (x[0], x[1]))
                fixed = total - sum(x[3] for x in old)      # accel.json and entries in use stay
                if fixed > cap_bytes:                       # removing the rest could never reach the cap
                    old = []
                    rep["errors"].append("what cannot go (accel.json, entries in use now) is over the cap; nothing "
                                         "else removed (reel clean shows the sizes)")
                for _, name, p, _ in old:
                    if total <= cap_bytes:
                        break
                    try:
                        got = safe_remove(p, a, "cache")
                    except linksafe.RemoveIncomplete as e:
                        got = e.freed
                        rep["errors"].append(_line(e, name))
                    except (Guidance, OSError) as e:
                        rep["errors"].append(_line(e, name))
                        continue
                    rep["removed"].append(name)
                    rep["freed"] += got
                    total -= got
            rep["cache_bytes_after"] = managed()[0]
        rep["rotated"] = rotate_logs(a / "logs")
    except Exception as e:  # noqa: BLE001  best effort after a handoff: reported, never a failed handoff
        rep["errors"].append(_line(e))
    return rep


def mark_model_used(repo_dir, home=None) -> bool:
    """Called by the Whisper loader: touch `<model folder>/.whynot-last-used`, so `--models` keeps a model the CPU lane
    (no GPU lock) used in the last 24 h. Written through linksafe inside models/ (never through a link). False when
    it can't be written: the model still loads; only the 24 h guard is missing for it."""
    try:
        root = os.path.abspath(os.fspath(home or plat.engine_home()))   # as given: models_dir() may be the junction form
        stamp = Path(os.path.abspath(os.fspath(repo_dir))) / STAMP
        when = _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds")
        linksafe.replace_atomic(stamp, root, (when + "\n").encode("utf-8"), within="models")
        return True
    except (Guidance, OSError):
        return False
