"""aerender (After Effects' command-line renderer) and frame extraction for motion projects and the AE probe.

aerender opens the SAVED project in its own AE instance, so the editor's open After Effects is never touched. A render
counts only when its output file exists and is newer than the call; frames are pulled from the render with ffmpeg.
"""
from __future__ import annotations

import shutil
import tempfile
import time
from pathlib import Path

from .common import ffmpeg_exe, run, write_text


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


def render(aep: Path, comp: str, out: Path, rs: str, om: str, start_frame: int | None = None,
           end_frame: int | None = None, timeout: int = 3600, log: Path | None = None) -> dict:
    exe = aerender_exe()
    aep, out = Path(aep), Path(out)
    if not exe or not Path(exe).exists() or not aep.exists():
        return {"status": "SKIPPED", "returncode": None, "output": str(out), "elapsed_s": 0,
                "log": None, "msg": f"aerender={exe} aep_exists={aep.exists()}"}
    out.parent.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    stage, r_aep, r_out = None, aep, out
    if not (str(aep).isascii() and str(out).isascii()):
        # aerender reads its command line in the ANSI code page: a non-ASCII path (an Arabic client folder) arrives as
        # "???". Render an ASCII copy of the project into an ASCII file and move that into place; After Effects finds
        # the footage itself through the project's own (Unicode) paths.
        if not tempfile.gettempdir().isascii():
            return {"status": "FAILED", "returncode": None, "output": str(out), "elapsed_s": 0, "log": None,
                    "msg": f"aerender needs ASCII paths, and the temp folder {tempfile.gettempdir()} is not one either: "
                           "set TEMP to an ASCII folder, then render again"}
        stage = Path(tempfile.mkdtemp(prefix="whynot-aerender-"))
        r_aep, r_out = stage / "project.aep", stage / ("render" + out.suffix)
        shutil.copy2(aep, r_aep)
    try:
        p = run(aerender_cmd(exe, r_aep, comp, r_out, rs, om, start_frame, end_frame), check=False, timeout=timeout)
        if stage is not None and r_out.exists() and r_out.stat().st_size > 0:
            out.unlink(missing_ok=True)
            shutil.move(str(r_out), str(out))
    finally:
        if stage is not None:
            shutil.rmtree(stage, ignore_errors=True)
    if log:
        write_text(Path(log), (p.stdout or "") + "\n" + (p.stderr or ""))
    fresh = out.exists() and out.stat().st_mtime >= t0 - 1 and out.stat().st_size > 0
    return {"status": "RENDERED" if fresh else "FAILED", "returncode": p.returncode, "output": str(out),
            "elapsed_s": round(time.time() - t0, 1), "log": str(log) if log else None}


def extract_frames(video: Path, frames: list[int], fps: float, out_dir: Path,
                   names: list[str] | None = None) -> list[Path]:
    """One PNG per frame number. Input seeking drops frames that start before the seek point, so seek a quarter frame
    BEFORE the frame's start: the first frame out is that frame, also when the file's timebase is 30000/1001."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    outs = []
    for i, f in enumerate(frames):
        name = names[i] if names else f"frame_{int(f):06d}.png"
        o = out_dir / name
        run([ffmpeg_exe(), "-y", "-loglevel", "error", "-ss", f"{max(0.0, (int(f) - 0.25) / float(fps)):.4f}", "-i", str(video),
             "-frames:v", "1", str(o)], check=False)
        if o.exists():
            outs.append(o)
    return outs
