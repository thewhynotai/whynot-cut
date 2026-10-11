"""Editing-reference VIDEO analysis (objective measurements only).

Produces, per reference video:
  * cut list (scene-change detection) -> shot durations, cuts/min
  * contact sheets (1 frame / N s) and a frame at every detected cut, for visual review
  * audio loudness envelope (RMS per 100 ms) -> music/SFX density hints
The *interpretation* (typography style, B-roll style, motion language) is written ONCE per client by the
client-researcher after viewing the sheets, into output/client_database/reference_style/ (see ref_style.py).
"""
from __future__ import annotations

import math
import re
import statistics
from pathlib import Path

from .common import Paths, ffmpeg_exe, log, run, write_json

SHOWINFO_T = re.compile(r"pts_time:([0-9.]+)")


def detect_cuts(video: Path, threshold: float = 0.30) -> list[float]:
    ff = ffmpeg_exe()
    p = run([ff, "-hide_banner", "-nostats", "-i", str(video), "-an",
             "-vf", f"scale=270:-2,select='gt(scene,{threshold})',showinfo", "-f", "null", "-"],
            check=False)
    return [float(t) for t in SHOWINFO_T.findall(p.stderr)]


def contact_sheet(video: Path, out: Path, every_s: float = 1.0, cols: int = 8, width: int = 180,
                  start: float = 0.0, max_frames: int = 64) -> Path:
    ff = ffmpeg_exe()
    rows = math.ceil(max_frames / cols)
    out.parent.mkdir(parents=True, exist_ok=True)
    run([ff, "-y", "-hide_banner", "-loglevel", "error", "-ss", str(start), "-i", str(video),
         "-vf", f"fps=1/{every_s},scale={width}:-2,drawtext=text='%{{pts\\:hms}}':x=4:y=4:"
                f"fontsize=14:fontcolor=yellow:box=1:boxcolor=black@0.6,tile={cols}x{rows}:padding=2",
         "-frames:v", "1", str(out)], check=False)
    if not out.exists():  # drawtext needs a font on some builds -> retry without timestamps
        run([ff, "-y", "-hide_banner", "-loglevel", "error", "-ss", str(start), "-i", str(video),
             "-vf", f"fps=1/{every_s},scale={width}:-2,tile={cols}x{rows}:padding=2",
             "-frames:v", "1", str(out)])
    return out


def frames_at(video: Path, times: list[float], out_dir: Path, width: int = 360) -> list[Path]:
    from .media_util import grab_frame_file
    out_dir.mkdir(parents=True, exist_ok=True)
    got = [grab_frame_file(video, t, out_dir / f"t{t:07.2f}.jpg", vf=f"scale={width}:-2", quality=4) for t in times]
    return [o for o in got if o]


def loudness_envelope(video: Path, hop_ms: int = 100) -> list[float]:
    """RMS dBFS per hop using ffmpeg astats; returns list of dB values."""
    ff = ffmpeg_exe()
    n = int(48000 * hop_ms / 1000)
    p = run([ff, "-hide_banner", "-nostats", "-i", str(video), "-vn", "-af",
             f"aresample=48000,asetnsamples=n={n}:p=0,astats=metadata=1:reset=1,"
             "ametadata=print:key=lavfi.astats.Overall.RMS_level", "-f", "null", "-"], check=False)
    vals = re.findall(r"RMS_level=(-?[0-9.]+|-inf)", p.stderr)
    return [(-120.0 if v == "-inf" else float(v)) for v in vals]


def analyze_reference(video: Path, out_dir: Path, duration_s: float) -> dict:
    cuts = detect_cuts(video)
    bounds = [0.0] + cuts + [duration_s]
    shots = [round(b - a, 3) for a, b in zip(bounds, bounds[1:]) if b - a > 0.04]
    sheet_dir = out_dir / video.stem
    sheets = []
    per_sheet = 64
    every = 1.0
    t = 0.0
    k = 0
    while t < duration_s:
        sheets.append(str(contact_sheet(video, sheet_dir / f"sheet_{k:02d}.jpg", every_s=every,
                                        start=t, max_frames=per_sheet)))
        t += per_sheet * every
        k += 1
    cut_frames = frames_at(video, [c + 0.08 for c in cuts], sheet_dir / "cuts")
    env = loudness_envelope(video)
    voiced = [v for v in env if v > -50]
    res = {
        "video": str(video), "duration_s": duration_s,
        "cuts_s": [round(c, 3) for c in cuts], "cut_count": len(cuts),
        "cuts_per_minute": round(len(cuts) / duration_s * 60, 2) if duration_s else 0,
        "shot_durations_s": shots,
        "shot_stats": {
            "mean": round(statistics.mean(shots), 2) if shots else None,
            "median": round(statistics.median(shots), 2) if shots else None,
            "min": min(shots) if shots else None, "max": max(shots) if shots else None,
        },
        "first_cut_s": cuts[0] if cuts else None,
        "audio": {"hop_ms": 100, "rms_db_mean": round(statistics.mean(voiced), 1) if voiced else None,
                  "silence_ratio": round(1 - len(voiced) / max(1, len(env)), 3),
                  "envelope_db": [round(v, 1) for v in env]},
        "contact_sheets": sheets, "cut_frames": [str(c) for c in cut_frames],
        "note": "Scene detection also fires on hard graphic/B-roll changes and big punch-ins.",
    }
    write_json(sheet_dir / "measurements.json", res)
    return res


def analyze_all(paths: Paths, refs: list[Path], durations: dict) -> dict:
    """Reference edits belong to the CLIENT: each one is analysed once into output/client_database/reference_analysis
    (cached by path, size and modification time) and every video's 01_analysis gets the summary. Ten reels from one
    episode no longer re-analyse the same references ten times. Without a video id (onboarding a client) only the
    client cache is written."""
    import json
    cache_dir = paths.output / "client_database" / "reference_analysis"
    cache_dir.mkdir(parents=True, exist_ok=True)
    idx_f = cache_dir / "cache.json"
    try:
        idx = json.loads(idx_f.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        idx = {}
    results = []
    for v in refs:
        st = Path(v).stat()
        key = f"{Path(v).resolve()}|{st.st_size}|{int(st.st_mtime)}"
        hit = idx.get(key)
        if hit and all(Path(s).exists() for s in hit.get("contact_sheets", [])):
            log(paths, f"Reference {v.name}: cached client analysis")
            results.append(hit)
            continue
        log(paths, f"Analyzing reference {v.name}")
        r = analyze_reference(v, cache_dir, durations.get(str(v), 0))
        idx[key] = r
        results.append(r)
    write_json(idx_f, idx)
    agg_shots = [s for r in results for s in r["shot_durations_s"]]
    summary = {
        "references": [{k: r[k] for k in ("video", "duration_s", "cut_count", "cuts_per_minute",
                                          "shot_stats", "first_cut_s", "contact_sheets")} for r in results],
        "aggregate": {
            "cuts_per_minute_mean": round(statistics.mean([r["cuts_per_minute"] for r in results]), 2) if results else None,
            "shot_median_s": round(statistics.median(agg_shots), 2) if agg_shots else None,
            "shot_mean_s": round(statistics.mean(agg_shots), 2) if agg_shots else None,
        },
    }
    if paths.video_id:
        write_json(paths.p("01_analysis/reference_analysis") / "reference-measurements.json", summary)
    write_json(cache_dir / "reference-measurements.json", summary)
    return summary
