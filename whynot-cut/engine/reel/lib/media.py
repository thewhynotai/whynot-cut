"""Media inspection (ffprobe-equivalent via PyAV) and preflight checks."""
from __future__ import annotations

from fractions import Fraction
from pathlib import Path

from .common import Paths, ffmpeg_exe, run, write_json, write_text, fmt_ts, load_config, now_iso

import re

_ROT = re.compile(r"rotation of (-?[0-9.]+) degrees")


def _rotation(path: Path) -> int:
    ff = ffmpeg_exe()
    if not ff:
        return 0
    p = run([ff, "-hide_banner", "-i", str(path)], check=False)
    m = _ROT.search(p.stderr)
    return int(round(float(m.group(1)))) if m else 0


def probe(path: Path) -> dict:
    import av  # local import: only available inside the venv
    path = Path(path)
    info = {"path": str(path), "name": path.name, "size_bytes": path.stat().st_size,
            "video": None, "audio": [], "data_streams": 0, "errors": []}
    try:
        c = av.open(str(path))
    except Exception as e:  # unreadable / unsupported
        info["errors"].append(f"open failed: {e}")
        return info
    info["container"] = c.format.name
    info["duration_s"] = round(c.duration / 1e6, 3) if c.duration else None
    info["container_meta"] = {k: v for k, v in c.metadata.items()}
    for s in c.streams:
        cc = s.codec_context
        if s.type == "video" and info["video"] is None:
            rate = s.average_rate or s.base_rate
            rot = _rotation(path)
            w, h = s.width, s.height
            dw, dh = (h, w) if abs(rot) in (90, 270) else (w, h)
            info["video"] = {
                "codec": cc.name, "profile": getattr(cc, "profile", None),
                "coded_width": w, "coded_height": h, "rotation": rot,
                "display_width": dw, "display_height": dh,
                "aspect": str(Fraction(dw, dh)), "orientation": "vertical" if dh > dw else "horizontal",
                "fps": float(rate) if rate else None, "fps_fraction": str(rate) if rate else None,
                "time_base": str(s.time_base), "frames": s.frames, "pix_fmt": cc.pix_fmt,
                "sar": str(cc.sample_aspect_ratio or "1"),
                "timecode": s.metadata.get("timecode"),
                "start_s": float(s.start_time * s.time_base) if s.start_time is not None else 0.0,
            }
        elif s.type == "audio":
            info["audio"].append({"codec": cc.name, "sample_rate": cc.sample_rate,
                                  "channels": cc.channels, "time_base": str(s.time_base),
                                  "start_s": float(s.start_time * s.time_base) if s.start_time is not None else 0.0})
        elif s.type == "data":
            info["data_streams"] += 1
            tc = s.metadata.get("timecode")
            if tc and info["video"] is not None and not info["video"].get("timecode"):
                info["video"]["timecode"] = tc
    c.close()
    return info


def _hist(im) -> list:
    small = im.resize((64, 36)).convert("RGB")
    h = small.histogram()                       # 3 x 256 bins
    tot = float(sum(h)) or 1.0
    return [x / tot for x in h]


def _similarity(a: list, b: list) -> float:
    return sum(min(x, y) for x, y in zip(a, b))      # histogram intersection, 0..1


def cutaway_ranges(speaker: list, fps: float, duration_s: float, min_s: float = 1.0, bridge_s: float = 1.0) -> list:
    """Per-sample speaker flags -> [[a_ms, b_ms]] of non-speaker stretches >= min_s (edges halfway to the neighbouring
    samples; stretches closer than bridge_s are merged)."""
    runs, cur = [], None
    for i, sp in enumerate(speaker):
        t = i / fps
        if not sp:
            cur = [t, t] if cur is None else [cur[0], t]
        elif cur is not None:
            runs.append(cur)
            cur = None
    if cur is not None:
        runs.append(cur)
    half, merged = 0.5 / fps, []
    for a, b in runs:
        a, b = max(0.0, a - half), (min(duration_s, b + half) if duration_s else b + half)
        if merged and a - merged[-1][1] < bridge_s:
            merged[-1][1] = b
        else:
            merged.append([a, b])
    return [[int(round(a * 1000)), int(round(b * 1000))] for a, b in merged if b - a >= min_s]


def analyze_shots(path: Path, duration_s: float, fps: float = 2.0, threshold: float = 0.55) -> dict:
    """Find CUTAWAYS: stretches without the speaker, such as full-screen graphic cards burned into a finished episode,
    B-roll or another camera. Cropping a 16:9 card to 9:16 cuts its text, so the plan shows cutaways whole.
    The source is decoded once at `fps` (small frames); a sample is the speaker when a face is found OR it looks like
    the frames that have a face (colour-histogram intersection >= threshold), so a speaker turning away stays the
    speaker. Runs of >= 1 s of non-speaker samples are cutaways (dissolves included; a cut detector misses those).
    Measured on a real episode: speaker frames 0.89-0.93 (also without a face), graphic card 0.17-0.38."""
    import subprocess
    from PIL import Image
    from .previews import _face_center
    W, H = 480, 270
    p = subprocess.Popen([ffmpeg_exe(), "-loglevel", "error", "-i", str(path), "-an", "-vf", f"fps={fps},scale={W}:{H}",
                          "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], stdout=subprocess.PIPE)
    rows = []
    try:
        while True:
            b = p.stdout.read(W * H * 3)
            if len(b) < W * H * 3:
                break
            im = Image.frombuffer("RGB", (W, H), b, "raw", "RGB", 0, 1)
            rows.append({"t": len(rows) / fps, "face": bool(_face_center(im)), "hist": _hist(im)})
    finally:
        p.stdout.close()
        p.wait()
    ref = [r["hist"] for r in rows if r["face"]]
    if not ref:
        return {"samples": len(rows), "cutaways_ms": [], "note": "no face found anywhere: cutaway detection skipped"}
    mean = [sum(c) / len(ref) for c in zip(*ref)]
    for r in rows:
        r["sim"] = round(_similarity(r.pop("hist"), mean), 3)
        r["speaker"] = r["face"] or r["sim"] >= threshold
    cut = cutaway_ranges([r["speaker"] for r in rows], fps, duration_s)
    return {"samples": len(rows), "fps": fps, "threshold": threshold, "cutaways_ms": cut,
            "speaker_similarity_median": sorted(r["sim"] for r in rows if r["face"])[len(ref) // 2]}


def auto_reframe(path: Path, v: dict, duration_s: float, sw: int, sh: int, samples: int = 9) -> dict:
    """Fill the vertical frame from a wider (e.g. 16:9 episode) source, centred on the speaker: scale to cover, then shift
    horizontally so the median detected face centre sits in the middle (clamped so the frame stays filled)."""
    import statistics
    from .previews import _face_center
    from PIL import Image
    dw, dh = v["display_width"], v["display_height"]
    cover = max(sw / dw, sh / dh)
    sx, sy = [], []
    ff = ffmpeg_exe()
    if ff and duration_s:
        import tempfile
        for k in range(samples):
            t = duration_s * (k + 0.5) / samples
            fd, tmp = tempfile.mkstemp(suffix=".png")
            import os
            os.close(fd)
            run([ff, "-y", "-loglevel", "error", "-ss", f"{t:.2f}", "-i", str(path), "-frames:v", "1", tmp], check=False)
            try:
                with Image.open(tmp) as im:
                    c = _face_center(im.convert("RGB"))
                if c:
                    sx.append(c[0])
                    sy.append(c[1])
            except Exception:
                pass
            finally:
                Path(tmp).unlink(missing_ok=True)
    fx = statistics.median(sx) if sx else 0.5
    scaled_w, scaled_h = dw * cover, dh * cover
    ox = -(fx - 0.5) * scaled_w
    lim_x = max(0.0, (scaled_w - sw) / 2)
    ox = max(-lim_x, min(lim_x, ox))
    return {"base_scale_percent": round(cover * 100, 3), "offset_x": round(ox, 1), "offset_y": 0.0,
            "face_x": round(fx, 3), "face_y": round(statistics.median(sy), 3) if sy else None,
            "faces": len(sx), "samples": samples if ff and duration_s else 0}


def preflight(paths: Paths, main_footage: list[Path]) -> dict:
    seq = load_config("sequence-settings.json")
    sw, sh, sfps = seq["general"]["frame_width"], seq["general"]["frame_height"], seq["general"]["timebase"]
    srate = seq["audio"]["sample_rate"]
    report = {"generated": now_iso(), "sequence": {"w": sw, "h": sh, "fps": sfps, "audio_hz": srate},
              "files": [], "valid": [], "issues": [], "conversions": []}
    for f in main_footage:
        if not Path(f).exists():
            report["issues"].append({"file": str(f), "severity": "error", "msg": "missing"})
            continue
        pr = probe(f)
        report["files"].append(pr)
        v = pr["video"]
        if pr["errors"] or not v:
            report["issues"].append({"file": str(f), "severity": "error", "msg": "; ".join(pr["errors"]) or "no video stream"})
            continue
        report["valid"].append(str(f))
        if v["fps"] and abs(v["fps"] - sfps) > 0.01:
            report["issues"].append({"file": str(f), "severity": "warning",
                "msg": f"source {v['fps']} fps vs {sfps} fps sequence — keep native speed (no interpret-footage "
                       f"change); Premiere drops/duplicates frames for display, audio sync preserved. "
                       f"Source frames are mapped with ms->frame at the source rate."})
        if (v["display_width"], v["display_height"]) != (sw, sh):
            sc = min(sw / v["display_width"], sh / v["display_height"])
            report["conversions"].append({"file": str(f), "type": "scale",
                "msg": f"display {v['display_width']}x{v['display_height']} -> scale {sc*100:.2f}% to fill {sw}x{sh}",
                "scale_percent": round(sc * 100, 3)})
            if Fraction(v["display_width"], v["display_height"]) != Fraction(sw, sh):
                rf = auto_reframe(Path(f), v, pr.get("duration_s") or 0, sw, sh)
                try:
                    shots = analyze_shots(Path(f), pr.get("duration_s") or 0)
                except Exception as e:  # noqa: BLE001  (shot analysis is an aid; never block preflight)
                    shots = {"cutaways_ms": [], "error": f"{type(e).__name__}: {e}"}
                rf["cutaways_ms"] = shots["cutaways_ms"]
                rf["cutaway_analysis"] = {k: v for k, v in shots.items() if k != "cutaways_ms"}
                report.setdefault("reframe", {})[str(f)] = rf
                if shots["cutaways_ms"]:
                    report["issues"].append({"file": str(f), "severity": "warning",
                        "msg": "source contains cutaways without the speaker (graphic cards / B-roll burned into the "
                               "footage) at " + ", ".join(f"{a / 1000:.1f}-{b / 1000:.1f}s" for a, b in shots["cutaways_ms"])
                               + ": shown whole over a blurred fill instead of cropped; replace or cover them in the edit if "
                                 "the card's text matters"})
                report["issues"].append({"file": str(f), "severity": "info" if rf.get("faces") else "warning",
                    "msg": f"aspect differs from 9:16: auto-reframe to fill the frame ({rf['base_scale_percent']}%, "
                           f"x offset {rf['offset_x']} px, face found in {rf.get('faces', 0)}/{rf.get('samples', 0)} "
                           f"sample frames). Used when edit-decisions global.base_scale_percent is \"auto\" or absent."})
        if v["rotation"]:
            report["issues"].append({"file": str(f), "severity": "info",
                "msg": f"display-matrix rotation {v['rotation']}° (Premiere honors it; coded {v['coded_width']}x{v['coded_height']})"})
        if not pr["audio"]:
            report["issues"].append({"file": str(f), "severity": "error", "msg": "no audio stream"})
        elif len(pr["audio"]) > 1:
            desc = "; ".join(f"#{k} {a['codec']} {a['channels']}ch" for k, a in enumerate(pr["audio"]))
            report["issues"].append({"file": str(f), "severity": "info",
                                     "msg": f"{len(pr['audio'])} audio streams ({desc}): the first is used for transcript, "
                                            f"cleanup and the timeline. If another stream holds the clean dialogue, export "
                                            f"the clip with that stream first."})
        for a in pr["audio"]:
            if a["sample_rate"] != srate:
                report["issues"].append({"file": str(f), "severity": "warning", "msg": f"audio {a['sample_rate']} Hz (sequence {srate}) — Premiere conforms"})
            if abs(a["start_s"] - v["start_s"]) > 0.001:
                report["issues"].append({"file": str(f), "severity": "warning",
                    "msg": f"audio/video start offset {a['start_s'] - v['start_s']:+.3f}s — check sync"})
        if v["pix_fmt"] and "10" in v["pix_fmt"]:
            report["issues"].append({"file": str(f), "severity": "info", "msg": f"{v['pix_fmt']} 10-bit source; no color changes applied (already graded)"})
    report["ok"] = not any(i["severity"] == "error" for i in report["issues"])
    write_json(paths.p("00_inputs/preflight.json"), report)
    L = ["# Media Preflight", "", f"Generated {report['generated']}", "",
         f"Sequence target: {sw}x{sh} @ {sfps} fps, {srate} Hz", "", "## Files", ""]
    for pr in report["files"]:
        v = pr["video"] or {}
        L.append(f"- **{pr['name']}** — {pr.get('duration_s')}s, {v.get('codec')} {v.get('coded_width')}x{v.get('coded_height')} "
                 f"(display {v.get('display_width')}x{v.get('display_height')}, rot {v.get('rotation')}), {v.get('fps')} fps, "
                 f"{v.get('pix_fmt')}, TC {v.get('timecode')}; audio "
                 + ", ".join(f"{a['codec']} {a['sample_rate']}Hz {a['channels']}ch" for a in pr["audio"]))
    L += ["", "## Issues", ""] + [f"- [{i['severity']}] {Path(i['file']).name}: {i['msg']}" for i in report["issues"]] + \
         ["", "## Required conversions", ""] + ([f"- {c['msg']}" for c in report["conversions"]] or ["- none"]) + \
         ["", f"**Preflight {'PASSED' if report['ok'] else 'FAILED'}**"]
    write_text(paths.p("00_inputs/preflight-report.md"), "\n".join(L) + "\n")
    return report
