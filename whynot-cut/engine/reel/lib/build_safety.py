"""Build safety shared by the Premiere and After Effects builds (Addendum G2 R1).

    free_space_refusal(target, estimate)   a refusal (nothing written) when the disk that holds `target` has less than
                                           estimate x 2 + 500 MB free; None when there is room or the disk cannot say
    is_disk_full(e) / disk_full_message    a write that failed because the disk is full (ENOSPC, Windows' disk-full
                                           errors), told in one plain sentence that names the drive
    reel_for_target(target, rel_dir)       the reel a `reel serve` build names by its output file
                                           (<root>/output/projects/<id>/<rel_dir>/<file>), or why it names none
    serve_context(root)                    the Context a serve build of that reel runs in (the request's, when it is
                                           for the same client)
    serve_answer(r, ok_status, readback)   a build result as reel serve answers it: {ok, readback} or {ok: false,
                                           error, how?}
"""
from __future__ import annotations

import errno
import os
import shutil
from pathlib import Path

HEADROOM_BYTES = 500 * 2 ** 20                   # on top of twice the estimate
DISK_FULL_ERRNOS = {errno.ENOSPC} | ({errno.EDQUOT} if hasattr(errno, "EDQUOT") else set())
DISK_FULL_WINERRORS = {39, 112}                  # ERROR_HANDLE_DISK_FULL, ERROR_DISK_FULL


def _existing(p: Path) -> Path:
    while not p.exists() and p.parent != p:
        p = p.parent
    return p


def drive_name(target) -> str:
    """`D:` on Windows; elsewhere the mount point that holds `target` (`/`, `/Volumes/Work`)."""
    p = Path(target)
    if p.drive:
        return p.drive
    p = _existing(p.resolve())
    while not os.path.ismount(p) and p.parent != p:
        p = p.parent
    return str(p)


def files_size(files) -> int:
    n = 0
    for f in files:
        try:
            n += Path(f).stat().st_size
        except OSError:
            pass
    return n


def _gb(n: int) -> str:
    return f"{n / 2 ** 30:.1f} GB"


def free_space_refusal(target, estimate: int) -> dict | None:
    """Refuse a build before it writes anything when the disk is short of estimate x 2 + 500 MB."""
    need = int(estimate) * 2 + HEADROOM_BYTES
    try:
        free = shutil.disk_usage(_existing(Path(target))).free
    except OSError:
        return None                              # the disk cannot say: a full disk is still told plainly (ENOSPC)
    if free >= need:
        return None
    drive = drive_name(target)
    return {"status": "NO_DISK_SPACE", "ok": False, "blocked": "not enough free disk space",
            "error": f"There is not enough free space on {drive} for this build (it needs about {_gb(need)}, "
                     f"{_gb(free)} is free): nothing was changed.",
            "how": f"Free up space on {drive}, then build again.", "free_bytes": free, "needed_bytes": need}


def is_disk_full(e: BaseException) -> bool:
    return isinstance(e, OSError) and (e.errno in DISK_FULL_ERRNOS
                                       or getattr(e, "winerror", None) in DISK_FULL_WINERRORS)


def disk_full_message(target) -> str:
    return f"The disk is full: free up space on {drive_name(target)} and try again"


# ------------------------------------------------------------------------------------------------- reel serve
def reel_for_target(target, rel_dir: str):
    """(Paths, None) for `<root>/output/projects/<id>/<rel_dir>/<file>` in a client folder (assets/ and data/), else
    (None, why). reel serve names the reel only by the file the build writes."""
    from .common import Paths
    if not isinstance(target, str) or not target.strip():
        return None, "The build request names no project file."
    p = Path(target)
    parts = rel_dir.split("/")
    k = len(parts)
    up = p.parents
    if not p.is_absolute() or len(up) < k + 4 or [up[i].name for i in range(k)][::-1] != parts \
            or up[k + 1].name != "projects" or up[k + 2].name != "output":
        return None, (f"{p.name} is not inside a WhyNot Cut reel folder (output/projects/<reel>/{rel_dir}): nothing "
                      "was built.")
    root, vid = up[k + 3], up[k].name
    if not ((root / "assets").is_dir() and (root / "data").is_dir()):
        return None, f"{root} is not a client folder (it needs assets/ and data/): nothing was built."
    try:
        return Paths(root, vid), None
    except Exception:  # noqa: BLE001 — check_project_id's Guidance: an id that is not one plain folder name
        return None, f"{vid!r} is not a reel id: nothing was built."


def serve_context(root: Path):
    """The request's Context when it is for this client (or names none: a new one with its profile and engine home);
    None when it is bound to another client folder."""
    from .common import Context, current_context
    ctx = current_context()
    if ctx.root is None:
        return Context(root=root, profile=ctx.profile, home=ctx.engine_home)
    return ctx if Path(ctx.root).resolve() == Path(root).resolve() else None


def serve_answer(r: dict, ok_status: str, readback_key: str) -> dict:
    """{ok: True, readback} for a build that ended in `ok_status`; else {ok: False, error, how?} in the build's own
    words (refusals included)."""
    if not isinstance(r, dict):
        return {"ok": False, "error": "The build did not report a result."}
    if r.get("status") == ok_status and r.get("ok") is not False:
        return {"ok": True, "readback": r.get(readback_key) or {}}
    failed = [k for k, v in (r.get("checks") or {}).items() if not v]
    reasons = "; ".join(x for x in r.get("reasons") or [] if isinstance(x, str))
    error = next((x for x in (r.get("error"), r.get("refused"), reasons, r.get("blocked"), r.get("detail"),
                              r.get("premiere_error")) if isinstance(x, str) and x.strip()), None)
    if r.get("status") == "PRPROJ_BUILT_WITH_ISSUES" and failed:
        error = "The project was built and saved, but these checks failed: " + ", ".join(failed) + "."
    out = {"ok": False, "error": error or f"The build did not finish ({r.get('status') or 'no status'})."}
    how = r.get("how") or r.get("fix")
    if r.get("status") == "EXISTS":
        how = "Set overwrite_existing to true to rebuild it (the current file is then kept as a *_prev_* backup)."
    if isinstance(how, str) and how.strip():
        out["how"] = how
    return out
