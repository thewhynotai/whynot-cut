"""aerender (After Effects' command-line renderer) and frame extraction for motion projects and the AE probe.

aerender opens the SAVED project in its own AE instance, so the editor's open After Effects is never touched. A render
counts only when its output file exists and is newer than the call; frames are pulled from the render with ffmpeg.
"""
from __future__ import annotations

import shutil
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
    if not tempfile.gettempdir().isascii():
        raise StageError(f"aerender needs ASCII paths, and the temp folder {tempfile.gettempdir()} is not one either: "
                         "set TEMP to an ASCII folder, then render again")
    stage = Path(tempfile.mkdtemp(prefix="whynot-aerender-"))
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
