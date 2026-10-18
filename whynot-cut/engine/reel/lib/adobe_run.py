"""Run an ExtendScript (.jsx) inside After Effects or Photoshop on macOS or Windows (opt-in extras only).

macOS: AppleScript (`DoScriptFile` / `do javascript file`), as verified in production.
Windows: After Effects via `AfterFX.exe -r <jsx>` (hands the script to the running instance, or starts AE); a script
path `-r` would ignore (a space, a non-ASCII letter or a symbol) goes as a copy (stage_script), in this order:
<engine home>/tmp/ae-run; %ProgramData%/WhyNotCut/tmp/ae-run when no part of it is a link or another account's; the
8.3 short form of the engine-home copy; else the run is refused;
Photoshop via its COM automation object (`Photoshop.Application.DoJavaScriptFile`) from PowerShell.

Success is never judged from the return value (AE's DoScript always prints 0): callers pass `done()`, a check on the
files the script must write, and these runners wait for it.
"""
from __future__ import annotations

import datetime as _dt
import hashlib
import os
import re
import subprocess
import time
import uuid
from pathlib import Path
from typing import Callable

from . import ae_render, plat
from .common import run


def app_name(key: str) -> str | None:
    a = plat.newest_app(key)
    return a["name"] if a else None


def _as_string(s: str) -> str:
    """An AppleScript string literal (quotes and backslashes escaped)."""
    return '"' + str(s).replace("\\", "\\\\").replace('"', '\\"') + '"'


def osascript_argv(app: str, command: str, timeout: int, *args, pre: tuple = ()) -> list[str]:
    """osascript with the `on run argv` form (3.0 T2.15, review §10): the script file path travels as an argument,
    never inside the AppleScript source, so a `"` in a client folder name cannot end the string and run code. The app
    name stays a literal (discovered by plat, escaped): AppleScript needs it at compile time for DoScriptFile.
    `pre`: lines run before the `tell` block, outside the app's dictionary (a coercion the app must not see)."""
    lines = [*pre, f"with timeout of {int(timeout)} seconds", f"tell application {_as_string(app)} to {command}",
             "end timeout"]
    return ["osascript", "-e", "on run argv", *[x for ln in lines for x in ("-e", ln)], "-e", "end run",
            *[str(a) for a in args]]


# Photoshop: `POSIX file <variable>` inside `tell application "Photoshop"` is sent to Photoshop as an object specifier
# ("Can't get POSIX file ...", -1728; the old literal form was resolved at compile time). The alias is made first, by
# AppleScript itself, and only the finished alias goes to `do javascript` (T2.15 review I-2; not yet run on a Mac).
PS_ALIAS = "set jsxFile to ((item 1 of argv) as POSIX file) as alias"


def run_after_effects(jsx: Path, timeout: int, done: Callable[[], bool] | None = None, *,
                      lock_wait_s: float | None = None) -> dict:
    """Run `jsx` in After Effects under the bridge's build lock (Gate 2 minor: ae-build, mogrt-build and
    `motion-build --run-script` start a new project too, so they queue behind a bridge build and each other). A lock
    still held after `lock_wait_s` (default cep_queue.LOCK_WAIT_S): REFUSED with `blocked` (exit 2)."""
    app = plat.newest_app("after_effects")
    if not app:
        return {"status": "UNSUPPORTED", "msg": "After Effects not installed"}
    refused = plat.sandbox_refusal("launch After Effects")                                   # G79: never in tests
    if refused:
        return {"status": "REFUSED", "msg": refused["error"], "how": refused["how"]}
    from . import ae_bridge, cep_queue
    wait = cep_queue.LOCK_WAIT_S if lock_wait_s is None else lock_wait_s
    try:
        with ae_bridge.build_lock(f"After Effects script {Path(jsx).name}", hold_s=timeout + LOCK_GRACE_S,
                                    wait_s=wait):
            return _run_after_effects(app, jsx, timeout, done)
    except cep_queue.BuildLockBusy as e:
        r = cep_queue.lock_busy_result(e, "After Effects")
        return dict(r, status="REFUSED", msg=r["blocked"])


# --------------------------------------------------------------------------- the path `-r` receives (Windows)
# Found live 2026-10-17 (docs/adobe/photoshop-route.md section 4): with After Effects running, `AfterFX.exe -r <jsx>`
# silently does nothing when the path has a space, and the launcher exits 0. Non-ASCII is treated the same way
# (assumed, not seen live): AE's command-line tools read the ANSI code page (aerender turns Arabic into "???",
# ae_render.stage_ascii). What else -r's re-parsing breaks on is unknown, so the rule is an allowlist (R_SAFE). A
# script outside it runs from a copy with a hex name, never beside the client files: <engine home>/tmp/ae-run, else
# %ProgramData%/WhyNotCut/tmp/ae-run (ae_render.program_data_tmp, shared with aerender's stage) when none of its three
# folders is a link or owned by another account, else the 8.3 short form of the engine-home copy; else the run is
# refused. Never a root folder of a drive (other users may write there and swap the script).
# Not verified live (risk R-L3): that the `~` of an 8.3 short path survives -r's re-parsing, like the non-ASCII
# assumption above. That doubt is the only reason the shared %ProgramData% folder is tried before the user's own 8.3
# path; once 8.3 is proven live, it could come first.
AE_RUN = "ae-run"
LOCK_GRACE_S = 300                # the build lock is held for timeout + this; an unconfirmed copy lives exactly as long
CONFIRMED_KEEP_S = 60             # a confirmed run's copy stays this long more, so a late -r never meets a missing file
# A copy is written, then its deadline (mtime) set: never sweep one younger than this. FAT/exFAT's 2 s mtime steps sit
# well inside it; FAT stores local time, so a DST change (or a clock jump) can move a deadline by up to an hour -
# accepted: the build lock already serialises runs of one engine home, so only another user's copy could be swept early.
SWEEP_MARGIN_S = 60
R_SAFE = re.compile(r"[A-Za-z0-9._\-\\/:~]+")
COPY_NAME = re.compile(r"[0-9a-f]{16}-\d+-[0-9a-f]{12}\.jsx")


def _now() -> float:
    """The run's clock (tests replace it here alone; the build lock keeps the real time.time)."""
    return time.time()


class ScriptReadError(OSError):
    """The source .jsx itself could not be read (missing, locked): not a staging-folder problem."""


class ScriptPathError(Exception):
    """No path `-r` would accept could be made for the script; str() says why, .how what to do."""

    def __init__(self, msg: str, how: str):
        super().__init__(msg)
        self.how = how


def r_safe(path) -> bool:
    """True when `AfterFX.exe -r` can take this path: letters, digits and . _ - \\ / : ~ only (8.3 names keep their
    ~), and not a UNC or device path (\\\\server\\share, \\\\?\\, \\\\.\\)."""
    s = str(path)
    return bool(R_SAFE.fullmatch(s)) and not s.startswith(("\\\\", "//"))


def stage_dirs() -> list[tuple[Path, bool]]:
    """Where a copy may go, in order, absolute, as (folder, shared) pairs: (<engine home>/tmp/ae-run, False), then
    (%ProgramData%/WhyNotCut/tmp/ae-run, True). A shared folder is trust-checked wherever it sits in the list. Under
    the test sandbox (G79) %ProgramData% counts only inside the sandbox: a unit test never writes to the machine's."""
    pd = ae_render.program_data_tmp()
    box = os.environ.get(plat.SANDBOX_ENV)
    if pd is not None and box:
        b, p = os.path.normcase(os.path.abspath(box)), os.path.normcase(os.path.abspath(pd))
        if not p.startswith(b.rstrip("\\/") + os.sep):
            pd = None
    return [(Path(os.path.abspath(r)) / AE_RUN, shared)
            for r, shared in ((plat.engine_home() / "tmp", False), (pd, True)) if r is not None]


def _copy_name(data: bytes) -> str:
    """<content sha256, 16 hex>-<pid>-<uuid4, 12 hex>.jsx: the hash ties a copy to its script, the pid to its process,
    and the random part keeps two runs of the same script in one process (threads) or a reused pid apart."""
    return f"{hashlib.sha256(data).hexdigest()[:16]}-{os.getpid()}-{uuid.uuid4().hex[:12]}.jsx"


def _sweep_expired(folder: Path) -> None:
    """Remove this module's copies whose deadline (their mtime, see _write_copy) has passed. A live copy's deadline
    lies ahead, so another run's file (another process, another user's under %ProgramData%) is never touched early."""
    limit = time.time() - SWEEP_MARGIN_S
    try:
        entries = [f for f in folder.iterdir() if COPY_NAME.fullmatch(f.name)]
    except OSError:
        return
    for f in entries:
        try:
            if not f.is_symlink() and f.is_file() and f.stat().st_mtime < limit:
                f.unlink()
        except OSError:
            pass


def _remove(f: Path | None) -> None:
    if f is not None:
        try:
            f.unlink()
        except OSError:
            pass                  # gone already, or briefly locked: swept after its deadline


def _stamp(f: Path, keep_until: float) -> None:
    """The copy's deadline is its mtime (a later run's sweep reads it)."""
    os.utime(f, (keep_until, keep_until))


def _write_copy(folder: Path, data: bytes, keep_until: float) -> Path:
    """A new file in `folder` (exclusive create: never another run's file) whose mtime is its deadline. A failed or
    interrupted write leaves nothing behind."""
    folder.mkdir(parents=True, exist_ok=True)
    _sweep_expired(folder)
    for _ in range(5):
        copy = folder / _copy_name(data)
        try:
            with open(copy, "xb") as fh:
                fh.write(data)
        except FileExistsError:
            continue
        except BaseException:
            _remove(copy)
            raise
        try:
            _stamp(copy, keep_until)
        except BaseException:
            _remove(copy)
            raise
        return copy
    raise OSError(f"could not make a new script copy in {folder}")


def _iso(t: float) -> str:
    return _dt.datetime.fromtimestamp(t).astimezone().isoformat(timespec="seconds")


def _run_script_yourself(jsx) -> str:
    return f"run the script yourself in After Effects (File > Scripts > Run Script File...): {jsx}"


def stage_script(jsx: Path, keep_until: float) -> tuple[Path | None, str]:
    """(copy, argument for -r). The path is made absolute first (AE resolves a relative one in ITS folder). A safe path
    goes as it is (copy None). Otherwise the copy goes to the first stage_dirs() folder that is safe and writable (and,
    for %ProgramData%, has no link and no other account's folder on the way), else to the engine home's under its 8.3
    short form. The copy's mtime is `keep_until`: a later run sweeps it after that. Raises ScriptPathError (no safe
    path: a refusal) or OSError (the script cannot be read or copied)."""
    jsx = Path(os.path.abspath(jsx))
    if r_safe(jsx):
        return None, str(jsx)
    try:
        data = jsx.read_bytes()
    except OSError as e:
        raise ScriptReadError(e.errno, e.strerror or str(e), str(jsx)) from e
    dirs, problems = stage_dirs(), []            # problems: (folder, why) pairs
    for folder, shared in dirs:
        if not r_safe(folder):
            problems.append((folder, f"{folder} is not a path -r takes"))
            continue
        try:
            folder.mkdir(parents=True, exist_ok=True)
            # %ProgramData% is shared by every account on the PC: whoever owns WhyNotCut, tmp or ae-run (or made one
            # a link) could swap the copy before After Effects runs it as this user
            bad = ae_render.folder_trust_problem([folder.parent.parent, folder.parent, folder]) if shared else None
            if bad:
                problems.append((folder, bad))
                continue
            copy = _write_copy(folder, data, keep_until)
        except OSError as e:
            problems.append((folder, f"{folder}: {e}"))
            continue
        return copy, str(copy)
    own = next(folder for folder, shared in dirs if not shared)          # the engine home's: the user's own
    if r_safe(own):                            # the engine home is safe but not writable: no 8.3 route helps
        raise OSError("; ".join(why for _, why in problems))
    copy = _write_copy(own, data, keep_until)
    short = ae_render._short_path(copy)
    if short and r_safe(short):
        return copy, short
    _remove(copy)
    others = [why for folder, why in problems if folder != own]      # the engine home has its own sentence
    why = (f"its 8.3 short form {short} still has one" if short and short != str(copy) else
           "Windows gave no 8.3 short name for it (short names are off on that drive, or the folder was made before "
           "they were turned on)")
    raise ScriptPathError(
        f"After Effects ignores `AfterFX.exe -r` when the script path has a space, a non-ASCII letter or a symbol, and "
        f"no safe path could be made for {jsx}: the engine home {plat.engine_home()} has one too, {why}"
        + (f"; also tried: {'; '.join(others)}" if others else ""),
        "move the engine home to a folder whose whole path has only English letters, digits and . _ - (no spaces) "
        "and that only your account can change (not a new folder at the top of a drive: other users may write there): "
        "run `setx WHYNOT_HOME <that folder>` in a terminal, open a new Claude Code session, then `reel setup`; or "
        + _run_script_yourself(jsx))


def _run_after_effects(app: dict, jsx: Path, timeout: int, done: Callable[[], bool] | None) -> dict:
    t0 = _now()
    if plat.IS_MAC:
        p = run(osascript_argv(app["name"], "DoScriptFile (item 1 of argv)", timeout, jsx),
                check=False, timeout=timeout + 30)
        res = {"returncode": p.returncode, "stdout": p.stdout.strip(), "stderr": p.stderr.strip()}
    else:
        keep_until = t0 + timeout + LOCK_GRACE_S
        try:
            copy, arg = stage_script(jsx, keep_until)
        except ScriptPathError as e:
            return {"status": "REFUSED", "ok": False, "refused": "ae-script-path", "msg": str(e), "how": e.how,
                    "jsx": str(jsx)}
        except ScriptReadError as e:
            return {"status": "SCRIPT_STAGE_FAILED", "ok": False, "jsx": str(jsx),
                    "msg": f"the After Effects script {jsx} could not be read: {e.strerror}",
                    # the file itself is unreadable: running it by hand cannot help
                    "how": "run the command again so the script is made again"}
        except OSError as e:
            own = next(folder for folder, shared in stage_dirs() if not shared)
            return {"status": "SCRIPT_STAGE_FAILED", "ok": False, "jsx": str(jsx),
                    "msg": f"the After Effects script {jsx} could not be copied to a path `-r` accepts: {e}",
                    "how": f"free space or fix the permissions on {own}, then run it again; or "
                           + _run_script_yourself(jsx)}
        launched = confirmed = False
        try:
            # -r returns at once when AE is already running; when it has to start AE the launcher keeps running, so
            # we never wait on the process itself, only on the files the script writes.
            subprocess.Popen([app["exe"], "-r", arg], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            launched = True
            res = {"returncode": None, "stdout": "", "stderr": "", "launched": app["exe"]}
            if copy is not None:
                res["script_copy_used"] = arg
            while done is not None and _now() - t0 < timeout:
                if done():
                    confirmed = True
                    break
                time.sleep(2)
        finally:
            # Never removed under a running After Effects: removed at once only when AE never got it. Confirmed: kept
            # CONFIRMED_KEEP_S more (an earlier copy's late run can satisfy done() before AE has read this one).
            # Otherwise (timeout, a failed done(), no done()) AE may still be starting or behind a dialog: the copy
            # keeps the build lock's own deadline. A later run sweeps it.
            if copy is not None and not launched:
                _remove(copy)
            elif copy is not None and confirmed:
                sooner = _now() + CONFIRMED_KEEP_S
                try:
                    _stamp(copy, sooner)
                    keep_until = sooner
                except OSError:
                    pass          # it keeps the longer deadline
        if copy is not None:
            res["script_copy_kept_until"] = _iso(keep_until)
    res.update(app=app["name"], elapsed_s=round(_now() - t0, 1))
    return res


def run_photoshop(jsx: Path, timeout: int) -> dict:
    app = plat.newest_app("photoshop")
    if not app:
        return {"status": "UNSUPPORTED", "msg": "Photoshop not installed"}
    refused = plat.sandbox_refusal("launch Photoshop")                                       # G79: never in tests
    if refused:
        return {"status": "REFUSED", "msg": refused["error"], "how": refused["how"]}
    t0 = time.time()
    if plat.IS_MAC:
        p = run(osascript_argv(app["name"], "do javascript jsxFile", timeout, jsx, pre=(PS_ALIAS,)),
                check=False, timeout=timeout + 30)
    else:
        ps = ("$ErrorActionPreference='Stop'; $app = New-Object -ComObject Photoshop.Application; "
              f"$r = $app.DoJavaScriptFile('{str(jsx).replace(chr(39), chr(39) * 2)}'); Write-Output $r")
        exe = "powershell"
        p = run([exe, "-NoProfile", "-NonInteractive", "-Command", ps], check=False, timeout=timeout + 30)
    return {"app": app["name"], "returncode": p.returncode, "stdout": p.stdout.strip(), "stderr": p.stderr.strip(),
            "elapsed_s": round(time.time() - t0, 1)}


def aerender() -> str | None:
    p = plat.aerender_path()
    return str(p) if p else None
