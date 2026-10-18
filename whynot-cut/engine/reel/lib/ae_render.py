"""aerender (After Effects' command-line renderer) and frame extraction for motion projects and the AE probe.

aerender opens the SAVED project in its own AE instance, so the editor's open After Effects is never touched. A render
counts only when its output file exists and is newer than the call; frames are pulled from the render with ffmpeg.
"""
from __future__ import annotations

import os
import shutil
import stat
import subprocess
import tempfile
import time
from pathlib import Path

from . import plat
from .common import run, write_text

TIMEOUT_HOW = ("Open After Effects and close any dialog it shows (a missing font, footage or plug-in message stops "
               "aerender), check the project opens and plays, then render again; a long video may need a larger "
               "--timeout")


def timeout_message(timeout) -> str:
    return f"aerender did not finish within {timeout} s and was stopped (After Effects' renderer hung or is too slow)"


def _text(b) -> str:
    """Partial output of a timed-out process: bytes, str or None."""
    if b is None:
        return ""
    return b.decode("utf-8", "replace") if isinstance(b, bytes) else str(b)


def aerender_cmd(aerender: str, aep: Path, comp: str, out: Path, rs: str, om: str,
                 start_frame: int | None = None, end_frame: int | None = None) -> list[str]:
    cmd = [str(aerender), "-project", str(aep), "-comp", comp, "-RStemplate", rs, "-OMtemplate", om,
           "-output", str(out)]
    if start_frame is not None:
        cmd += ["-s", str(int(start_frame))]
    if end_frame is not None:
        cmd += ["-e", str(int(end_frame))]
    return cmd


def aerender_exe() -> str | None:
    from . import plat
    p = plat.aerender_path()
    return str(p) if p else None


class StageError(Exception):
    """The ASCII stage for aerender could not be made; str() is the message that says what to do."""


def sandbox_refused(exe) -> dict | None:
    """G79: a unit test never launches the real aerender (an engine error document), otherwise None."""
    return plat.sandbox_refusal("run aerender") if Path(str(exe)).stem.lower() == "aerender" else None


def _short_path(p) -> str | None:
    """The Windows 8.3 short form of an existing path (None when unavailable: 8.3 names are off on that volume)."""
    try:
        import ctypes
        buf = ctypes.create_unicode_buffer(32768)
        n = ctypes.windll.kernel32.GetShortPathNameW(str(p), buf, len(buf))
        return buf.value if 0 < n < len(buf) else None
    except Exception:  # noqa: BLE001  (not Windows, or the call failed)
        return None


FILE_ATTRIBUTE_REPARSE_POINT = 0x400
_WIN_LOCAL_SYSTEM_SID, _WIN_BUILTIN_ADMINISTRATORS_SID = 22, 26      # WELL_KNOWN_SID_TYPE


def _is_reparse(p) -> bool:
    """A link of any kind (symbolic link, junction, mount point), judged without following it."""
    try:
        st = os.lstat(p)
    except OSError:
        return False
    return stat.S_ISLNK(st.st_mode) or bool(getattr(st, "st_file_attributes", 0) & FILE_ATTRIBUTE_REPARSE_POINT)


def _owner_trusted(p) -> bool:
    """Windows: the folder's owner (GetNamedSecurityInfoW, OWNER_SECURITY_INFORMATION) is this process's user (the
    token user SID), SYSTEM or the Administrators group. Any failure counts as untrusted. Elsewhere True (the
    shared-folder routes are Windows-only)."""
    if not plat.IS_WIN:
        return True
    try:
        import ctypes
        from ctypes import wintypes
        adv = ctypes.WinDLL("advapi32", use_last_error=True)
        k32 = ctypes.WinDLL("kernel32", use_last_error=True)
        PV = ctypes.c_void_p
        adv.GetNamedSecurityInfoW.argtypes = [wintypes.LPCWSTR, ctypes.c_int, wintypes.DWORD, ctypes.POINTER(PV),
                                              ctypes.POINTER(PV), ctypes.POINTER(PV), ctypes.POINTER(PV),
                                              ctypes.POINTER(PV)]
        adv.GetNamedSecurityInfoW.restype = wintypes.DWORD
        adv.IsWellKnownSid.argtypes, adv.IsWellKnownSid.restype = [PV, ctypes.c_int], wintypes.BOOL
        adv.EqualSid.argtypes, adv.EqualSid.restype = [PV, PV], wintypes.BOOL
        adv.OpenProcessToken.argtypes = [wintypes.HANDLE, wintypes.DWORD, ctypes.POINTER(wintypes.HANDLE)]
        adv.OpenProcessToken.restype = wintypes.BOOL
        adv.GetTokenInformation.argtypes = [wintypes.HANDLE, ctypes.c_int, PV, wintypes.DWORD,
                                            ctypes.POINTER(wintypes.DWORD)]
        adv.GetTokenInformation.restype = wintypes.BOOL
        k32.GetCurrentProcess.argtypes, k32.GetCurrentProcess.restype = [], wintypes.HANDLE
        k32.CloseHandle.argtypes, k32.CloseHandle.restype = [wintypes.HANDLE], wintypes.BOOL
        k32.LocalFree.argtypes, k32.LocalFree.restype = [PV], PV
        owner, sd = PV(), PV()
        # SE_FILE_OBJECT = 1, OWNER_SECURITY_INFORMATION = 1
        if adv.GetNamedSecurityInfoW(str(p), 1, 1, ctypes.byref(owner), None, None, None, ctypes.byref(sd)) != 0:
            return False
        try:
            if not owner.value:            # FAT/exFAT, or a descriptor without an owner: nothing to trust
                return False
            if adv.IsWellKnownSid(owner, _WIN_LOCAL_SYSTEM_SID) or \
                    adv.IsWellKnownSid(owner, _WIN_BUILTIN_ADMINISTRATORS_SID):
                return True
            tok = wintypes.HANDLE()
            if not adv.OpenProcessToken(k32.GetCurrentProcess(), 0x0008, ctypes.byref(tok)):   # TOKEN_QUERY
                return False
            try:
                n = wintypes.DWORD()
                adv.GetTokenInformation(tok, 1, None, 0, ctypes.byref(n))                     # TokenUser: size
                buf = ctypes.create_string_buffer(n.value)
                if not n.value or not adv.GetTokenInformation(tok, 1, buf, n, ctypes.byref(n)):
                    return False
                user_sid = ctypes.cast(buf, ctypes.POINTER(PV))[0]     # TOKEN_USER.User.Sid
                return bool(adv.EqualSid(owner, user_sid))
            finally:
                k32.CloseHandle(tok)
        finally:
            k32.LocalFree(sd)
    except Exception:  # noqa: BLE001  (the call failed: do not trust the folder)
        return False


def folder_trust_problem(folders) -> str | None:
    """None when each existing folder in `folders` is a plain folder (no link) owned by this account, SYSTEM or the
    Administrators; else why not. Such a folder under a place every account may write (%ProgramData%) could otherwise
    have its files swapped by another user before an Adobe app runs them as this one. A folder not made yet is fine:
    this account makes it on use."""
    for f in folders:
        if not os.path.lexists(f):
            continue
        if _is_reparse(f):
            return f"{f} is a link (reparse point)"
        if not _owner_trusted(f):
            return f"{f} is owned by another account"
    return None


def program_data_tmp(environ=None) -> Path | None:
    """%ProgramData%/WhyNotCut/tmp (Windows), else None: a machine folder outside the user profile, so it stays ASCII
    when an Arabic user name puts the profile (and an engine home inside it) out of reach of narrow command lines."""
    env = os.environ if environ is None else environ
    return Path(env["ProgramData"]) / "WhyNotCut" / "tmp" if env.get("ProgramData") else None


def _trust_chain(root, environ=None) -> list:
    """The folders of a stage root that need folder_trust_problem: WhyNotCut and tmp for %ProgramData%'s (every
    account may create folders there); none for the others (the engine home and %TEMP% are the user's own)."""
    pd = program_data_tmp(environ)
    if pd is not None and os.path.normcase(os.path.abspath(root)) == os.path.normcase(os.path.abspath(pd)):
        return [pd.parent, pd]
    return []


def ascii_stage_roots(temp=None, home=None, environ=None, short_path=_short_path) -> list[Path]:
    """Folders where the aerender stage may go, ASCII only, in order: the temp folder when it is ASCII; else (an
    Arabic Windows user name puts %TEMP% under C:/Users/<name>) the engine home's tmp/ (the user's own: not checked,
    as in adobe_run), %ProgramData%/WhyNotCut/tmp unless a part of it already there is a link or another account's
    (folder_trust_problem, checked again by stage_ascii after mkdir), then the 8.3 short form of %TEMP%; with none,
    stage_ascii refuses with a how. Never a folder at the root of the system drive: one made there inherits
    Authenticated Users: Modify, so another account could swap the staged project (no owner check can see that).
    Each is created on use; one that cannot be is skipped."""
    temp = str(temp if temp is not None else tempfile.gettempdir())
    if temp.isascii():
        return [Path(temp)]
    env = os.environ if environ is None else environ
    if home is None:
        try:
            home = plat.engine_home()
        except Exception:  # noqa: BLE001
            home = None
    roots = [Path(home) / "tmp"] if home is not None else []
    pd = program_data_tmp(env)
    if pd is not None and folder_trust_problem(_trust_chain(pd, env)) is None:
        roots.append(pd)
    sp = short_path(temp)
    if sp:
        roots.append(Path(sp))
    return [r for r in roots if str(r).isascii()]


def stage_ascii(aep: Path, out: Path | None = None) -> tuple[Path | None, Path, Path | None]:
    """(stage, aep to pass, output to pass). aerender on Windows reads its command line in the ANSI code page: a
    non-ASCII path (an Arabic client folder) arrives as "???". Then an ASCII copy of the project is rendered (into an
    ASCII file when out is given, for the caller to move into place) and the caller removes `stage` afterwards; After
    Effects finds the footage and the project's own render-queue outputs through the project's Unicode paths. stage is
    None when the paths go as they are (ASCII, or macOS, which passes UTF-8). Raises StageError."""
    aep = Path(aep)
    out = Path(out) if out is not None else None
    if not (plat.IS_WIN and not (str(aep).isascii() and (out is None or str(out).isascii()))):
        return None, aep, out
    stage, tried = None, []
    for root in ascii_stage_roots():
        tried.append(str(root))
        try:
            Path(root).mkdir(parents=True, exist_ok=True)
            bad = folder_trust_problem(_trust_chain(root))      # again after mkdir: it may have been made meanwhile
            if bad:
                tried[-1] += f" ({bad})"
                continue
            stage = Path(tempfile.mkdtemp(prefix="whynot-aerender-", dir=str(root)))
            break
        except OSError:
            continue
    if stage is None:
        raise StageError(f"aerender needs ASCII paths, and no ASCII folder could hold its stage (the temp folder "
                         f"{tempfile.gettempdir()} is not ASCII; tried: {', '.join(tried) or 'none'}): run "
                         "`setx WHYNOT_HOME C:\\whynot` (or `setx TEMP C:\\Temp` after creating that folder) in a "
                         "terminal, open a new Claude Code session, then render again")
    try:
        r_aep = stage / "project.aep"
        shutil.copy2(aep, r_aep)
    except BaseException:
        shutil.rmtree(stage, ignore_errors=True)
        raise
    return stage, r_aep, (stage / ("render" + out.suffix) if out is not None else None)


def render(aep: Path, comp: str, out: Path, rs: str, om: str, start_frame: int | None = None,
           end_frame: int | None = None, timeout: int = 3600, log: Path | None = None) -> dict:
    exe = aerender_exe()
    aep, out = Path(aep), Path(out)
    if not exe or not Path(exe).exists() or not aep.exists():
        return {"status": "SKIPPED", "returncode": None, "output": str(out), "elapsed_s": 0,
                "log": None, "msg": f"aerender={exe} aep_exists={aep.exists()}"}
    refused = sandbox_refused(exe)
    if refused:
        return {"status": "REFUSED", "returncode": None, "output": str(out), "elapsed_s": 0, "log": None,
                "msg": refused["error"], "how": refused["how"]}
    out.parent.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    try:
        # aerender on Windows reads its command line in the ANSI code page: see stage_ascii
        stage, r_aep, r_out = stage_ascii(aep, out)
    except StageError as e:
        return {"status": "FAILED", "returncode": None, "output": str(out), "elapsed_s": 0, "log": None, "msg": str(e)}
    try:
        p = run(aerender_cmd(exe, r_aep, comp, r_out, rs, om, start_frame, end_frame), check=False, timeout=timeout)
    except subprocess.TimeoutExpired as e:      # 3.0 T2.2: a FAILED result that says what to do, not a traceback
        if stage is not None:
            shutil.rmtree(stage, ignore_errors=True)
        if log:
            write_text(Path(log), _text(e.stdout) + "\n" + _text(e.stderr))
        return {"status": "FAILED", "returncode": None, "output": str(out), "elapsed_s": round(time.time() - t0, 1),
                "log": str(log) if log else None, "msg": timeout_message(timeout), "how": TIMEOUT_HOW}
    except BaseException:
        if stage is not None:
            shutil.rmtree(stage, ignore_errors=True)
        raise
    if log:
        write_text(Path(log), (p.stdout or "") + "\n" + (p.stderr or ""))
    if stage is not None:
        if r_out.exists() and r_out.stat().st_size > 0:
            try:
                out.unlink(missing_ok=True)
                shutil.move(str(r_out), str(out))
            except OSError as e:        # never throw away a finished render: it stays in the stage
                return {"status": "FAILED", "returncode": p.returncode, "output": str(out), "kept": str(r_out),
                        "elapsed_s": round(time.time() - t0, 1), "log": str(log) if log else None,
                        "msg": f"the render finished but could not replace {out} ({e.strerror or e}): it is kept at "
                               f"{r_out} - close the file (or free disk space), then move it there or render again"}
        shutil.rmtree(stage, ignore_errors=True)
    fresh = out.exists() and out.stat().st_mtime >= t0 - 1 and out.stat().st_size > 0
    return {"status": "RENDERED" if fresh else "FAILED", "returncode": p.returncode, "output": str(out),
            "elapsed_s": round(time.time() - t0, 1), "log": str(log) if log else None}


def extract_frames(video: Path, frames: list[int], fps: float, out_dir: Path,
                   names: list[str] | None = None) -> list[Path]:
    """One PNG per frame number. Input seeking drops frames that start before the seek point, so seek a quarter frame
    BEFORE the frame's start: the first frame out is that frame, also when the file's timebase is 30000/1001."""
    from .media_util import grab_frame_file
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    outs = []
    for i, f in enumerate(frames):
        name = names[i] if names else f"frame_{int(f):06d}.png"
        o = grab_frame_file(video, (int(f) - 0.25) / float(fps), out_dir / name, ss_digits=4)
        if o:
            outs.append(o)
    return outs
