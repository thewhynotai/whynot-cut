# SPDX-License-Identifier: GPL-3.0-or-later
# © 2026 The Why Not AI (thewhynot.ai)
"""The G-GPU A/B (dev tool, not shipped in the plugin; 3.0 Phase 4 T4.10 step 8): every engine media site in the CPU
lane and in this machine's GPU lane, with the numbers that decide accel.SITE_LANES.

    <runtime python> tools/bench_media.py --root <client folder> --episode-root <podcast client folder> --out <dir>
        [--src <clip>] [--episode <episode file>] [--final-src <AE master>] [--repeat 3] [--sites a,b,...]

Run it only through heavy.sh (`bash "$HEAVY" gpu t410-ab -- ...`): one GPU job machine-wide, Premiere and After
Effects closed or idle. For every site and lane: the median wall time over --repeat runs, peak RAM and VRAM
(tools/footprint.py), the output size, and the SSIM of the GPU output against the CPU output (ffmpeg's ssim filter).
Each site's command mirrors the engine's call (the same decoder options, filters and encoder arguments from
lib/accel.py); decode-only sites write lossless FFV1 so their SSIM compares the decoded pictures.

The lane rule (lane_rule): a site keeps "gpu" only when the GPU run is >= 15 % faster AND its SSIM is >= 0.98.
Finals (final_rule: the motion MP4, libx264 crf 18 vs h264_nvenc -cq 18) never switch here: an SSIM >= 0.995 only
makes them a candidate for a later, separate decision after six frames are viewed side by side (G10).
Writes <out>/bench.json and <out>/bench.md (the table for docs/superpowers/evidence/<date>-g-gpu-ab.md).
"""
from __future__ import annotations

import argparse
import json
import os
import re
import statistics
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "whynot-cut" / "engine" / "reel"))

from lib import accel  # noqa: E402

MIN_GAIN = 0.15
MIN_SSIM = 0.98
FINAL_SSIM = 0.995
RUN_TIMEOUT_S = 1800                  # one site run (footprint kills its ffmpeg at this; the call waits a little longer)
SSIM_TIMEOUT_S = 900
VIDEO_EXT = {".mp4", ".mov", ".mxf", ".m4v", ".mkv", ".avi"}
EPISODE_SITES = ("reel_candidates", "thumbs")          # run on the episode; every other site on the clip
LOSSLESS = ["-c:v", "ffv1", "-level", "3"]


# --------------------------------------------------------------------------- pure parts (unit-tested)
def site_cmd(site: str, lane: str, *, ff: str, src: str, out: str) -> list[str]:
    """The ffmpeg argv of one site in one lane: the engine call's decoder options, filters and encoder arguments,
    reading `src` and writing `out` (both passed through unchanged)."""
    hw = accel.decode_args(lane)
    head = [ff, "-y", "-hide_banner", "-nostdin", "-loglevel", "error"]
    if site == "preview_video":           # the proxy: 24 fps, 540 wide, x264 crf 23 (preview_video.render)
        return head + [*hw, "-t", "30", "-i", src, "-an", "-vf",
                       "fps=24,scale=540:960:force_original_aspect_ratio=increase,crop=540:960",
                       *accel.h264_args(lane, 23), "-pix_fmt", "yuv420p", out]
    if site == "reel_candidates":         # reels.render_candidates: letterboxed 540x960, crf 28, the episode audio
        return head + [*hw, "-ss", "60", "-t", "30", "-i", src, "-vf",
                       "scale=540:-2,pad=540:960:0:(oh-ih)/2:color=0x111111", "-map", "0:v:0", "-map", "0:a:0?",
                       *accel.h264_args(lane, 28), "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "96k", out]
    if site == "animatic":                # motion_animatic: 10 fps, crf 26 (its frames come from a pipe; here a clip)
        return head + [*hw, "-t", "30", "-i", src, "-an", "-vf",
                       "fps=10,scale=540:960:force_original_aspect_ratio=increase,crop=540:960",
                       *accel.h264_args(lane, 26), "-pix_fmt", "yuv420p", out]
    if site == "thumbs":                  # overlay_scan.decode_thumbs: one 320x180 thumbnail per second
        return head + [*hw, "-ss", "0", "-i", src, "-t", "300", "-an", "-sn", "-vf",
                       "fps=1,scale=320:180:flags=area,format=rgb24", *LOSSLESS, out]
    if site == "shots":                   # shots.analyze_window: 2 fps, 640x360 padded
        return head + [*hw, "-ss", "0", "-t", "60", "-i", src, "-an", "-vf",
                       "fps=2,scale=640:360:force_original_aspect_ratio=decrease,pad=640:360:(ow-iw)/2:(oh-ih)/2,"
                       "format=rgb24", *LOSSLESS, out]
    if site == "grab_frame":              # media_util.grab_frame_file: one frame, input seeking
        return head + [*hw, "-ss", "10.000", "-i", src, "-frames:v", "1", *LOSSLESS, out]
    if site == "final":                   # motion_render.render: the deliverable MP4 (never decoded on the GPU)
        venc = ["-c:v", "libx264", "-crf", "18"] if lane == "cpu" else accel.h264_args(lane, 18)
        return head + ["-i", src, *venc, "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k",
                       "-movflags", "+faststart", out]
    raise ValueError(f"unknown site {site!r}")


def ssim_cmd(ff: str, a: str, b: str) -> list[str]:
    return [ff, "-hide_banner", "-nostdin", "-i", a, "-i", b, "-lavfi", "ssim", "-f", "null", "-"]


def parse_ssim(text: str) -> float | None:
    """The overall SSIM ("All:0.98...") the ssim filter prints last, or None."""
    hits = re.findall(r"All:\s*([0-9]*\.?[0-9]+)", text or "")
    return float(hits[-1]) if hits else None


def lane_rule(cpu_s: float | None, gpu_s: float | None, ssim: float | None) -> str:
    """"gpu" only when the GPU run is >= 15 % faster than the CPU run and its picture has SSIM >= 0.98."""
    if not cpu_s or gpu_s is None or ssim is None:
        return "cpu"
    return "gpu" if (cpu_s - gpu_s) / cpu_s >= MIN_GAIN - 1e-9 and ssim >= MIN_SSIM else "cpu"


def final_rule(ssim: float | None) -> dict:
    """Finals stay libx264 here (the default, G10). SSIM >= 0.995 makes NVENC only a candidate: six frames side by side
    and a separate later commit decide."""
    cand = ssim is not None and ssim >= FINAL_SSIM
    return {"switch": False, "candidate": cand, "ssim": ssim,
            "why": ("SSIM >= 0.995: view 6 frames side by side; a switch is a separate later commit" if cand else
                    "SSIM below 0.995 (or no GPU result): finals stay libx264 crf 18")}


# --------------------------------------------------------------------------- the run
def _first_video(folder: Path) -> Path | None:
    if not folder.is_dir():
        return None
    vids = sorted(p for p in folder.iterdir() if p.suffix.lower() in VIDEO_EXT and not p.name.startswith("._"))
    return vids[0] if vids else None


def _ext(site: str) -> str:
    return ".mkv" if site in ("thumbs", "shots", "grab_frame") else ".mp4"


def _measure(cmd: list[str], fp_json: Path) -> dict:
    """One run under tools/footprint.py: wall time, peaks, return code."""
    fp = [sys.executable, str(ROOT / "tools" / "footprint.py"), "--out", str(fp_json), "--timeout",
          str(RUN_TIMEOUT_S), "--", *cmd]
    t0 = time.monotonic()
    try:
        r = subprocess.run(fp, capture_output=True, text=True, encoding="utf-8", errors="replace",
                           timeout=RUN_TIMEOUT_S + 60)
    except subprocess.TimeoutExpired:
        return {"rc": "timeout", "wall_s": None, "peak_rss_mb": None, "peak_vram_mb": None, "peak_gpu_pct": None}
    wall = time.monotonic() - t0
    try:
        rep = json.loads(fp_json.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        rep = {}
    return {"rc": rep.get("returncode", r.returncode), "wall_s": rep.get("wall_s", round(wall, 2)),
            "peak_rss_mb": (rep.get("rss_mb") or {}).get("peak"), "peak_vram_mb": (rep.get("vram_mb") or {}).get("peak"),
            "peak_gpu_pct": (rep.get("gpu_pct") or {}).get("peak")}


def run_site(site: str, lane: str, ff: str, src: Path, out_dir: Path, repeat: int) -> dict:
    d = out_dir / site
    d.mkdir(parents=True, exist_ok=True)
    out = d / f"{lane}{_ext(site)}"
    runs = [_measure(site_cmd(site, lane, ff=ff, src=str(src), out=str(out)), d / f"{lane}-{k}.footprint.json")
            for k in range(max(1, repeat))]
    ok = [x for x in runs if x["rc"] == 0]
    return {"site": site, "lane": lane, "ok": len(ok) == len(runs), "out": str(out),
            "wall_s": round(statistics.median(x["wall_s"] for x in ok), 2) if ok else None,
            "peak_rss_mb": max((x["peak_rss_mb"] or 0) for x in runs), "peak_vram_mb": max((x["peak_vram_mb"] or 0)
                                                                                           for x in runs),
            "size_bytes": out.stat().st_size if out.exists() else None, "runs": runs}


def ssim_of(ff: str, a: str, b: str) -> float | None:
    try:
        r = subprocess.run(ssim_cmd(ff, a, b), capture_output=True, text=True, encoding="utf-8", errors="replace",
                           timeout=SSIM_TIMEOUT_S)
    except subprocess.TimeoutExpired:
        return None
    return parse_ssim(r.stderr) if r.returncode == 0 else None


def table(rows: list[dict], final: dict | None) -> str:
    lines = ["| site | lane | wall s | peak RAM MB | peak VRAM MB | size | SSIM vs CPU | verdict |",
             "|---|---|---|---|---|---|---|---|"]
    for r in rows:
        for x in (r["cpu"], r["gpu"]):
            lines.append(f"| {r['site']} | {x['lane']} | {x['wall_s']} | {x['peak_rss_mb']} | {x['peak_vram_mb']} | "
                         f"{x['size_bytes']} | {r['ssim'] if x is r['gpu'] else '-'} | "
                         f"{r['verdict'] if x is r['gpu'] else ''} |")
    out = "\n".join(lines) + "\n\nSITE_LANES = " + json.dumps({r["site"]: r["verdict"] for r in rows}, indent=2) + "\n"
    if final:
        out += f"\nFinal (motion MP4, libx264 crf 18 vs NVENC -cq 18): SSIM {final['ssim']}; {final['why']}\n"
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="G-GPU A/B of the engine's media sites (T4.10)")
    ap.add_argument("--root", required=True, help="a test client folder (data/Raw has the clip)")
    ap.add_argument("--episode-root", required=True, help="a podcast test client (data/Episodes has the episode)")
    ap.add_argument("--out", required=True)
    ap.add_argument("--src", help="the clip (default: the first video in <root>/data/Raw)")
    ap.add_argument("--episode", help="the episode (default: the first video in <episode-root>/data/Episodes)")
    ap.add_argument("--final-src", help="an After Effects master for the final A/B (default: the clip)")
    ap.add_argument("--repeat", type=int, default=3)
    ap.add_argument("--sites", default=",".join(list(accel.SITE_LANES) + ["final"]))
    a = ap.parse_args(argv)
    from lib.common import ffmpeg_exe
    ff = ffmpeg_exe()
    det = accel.detect(refresh=True)
    if det["kind"] == "cpu":
        print(json.dumps({"ok": False, "error": f"no GPU lane on this machine: {det['why']}"}, ensure_ascii=False))
        return 2
    clip = Path(a.src) if a.src else _first_video(Path(a.root) / "data" / "Raw")
    ep = Path(a.episode) if a.episode else _first_video(Path(a.episode_root) / "data" / "Episodes")
    final_src = Path(a.final_src) if a.final_src else clip
    if not clip or not ep:
        print(json.dumps({"ok": False, "error": "no clip in <root>/data/Raw or no episode in "
                                                "<episode-root>/data/Episodes (pass --src / --episode)"}))
        return 2
    out_dir = Path(a.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    rows, final = [], None
    for site in [s.strip() for s in a.sites.split(",") if s.strip()]:
        src = final_src if site == "final" else ep if site in EPISODE_SITES else clip
        cpu = run_site(site, "cpu", ff, src, out_dir, a.repeat)
        gpu = run_site(site, det["kind"], ff, src, out_dir, a.repeat)
        ssim = ssim_of(ff, gpu["out"], cpu["out"]) if cpu["ok"] and gpu["ok"] else None
        if site == "final":
            final = dict(final_rule(ssim), cpu=cpu, gpu=gpu)
            continue
        rows.append({"site": site, "cpu": cpu, "gpu": gpu, "ssim": ssim,
                     "verdict": lane_rule(cpu["wall_s"], gpu["wall_s"] if gpu["ok"] else None, ssim)})
        print(f"{site}: cpu {cpu['wall_s']} s, {det['kind']} {gpu['wall_s']} s, SSIM {ssim} -> {rows[-1]['verdict']}",
              file=sys.stderr)
    doc = {"machine": det, "clip": str(clip), "episode": str(ep), "repeat": a.repeat, "sites": rows, "final": final,
           "rule": {"min_gain": MIN_GAIN, "min_ssim": MIN_SSIM, "final_ssim": FINAL_SSIM},
           "site_lanes": {r["site"]: r["verdict"] for r in rows}}
    (out_dir / "bench.json").write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (out_dir / "bench.md").write_text(table(rows, final), encoding="utf-8")
    print(json.dumps(doc["site_lanes"], indent=2))
    return 0


if __name__ == "__main__":
    os.environ.setdefault("PYTHONUTF8", "1")
    sys.exit(main())
