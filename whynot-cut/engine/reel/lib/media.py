"""Media inspection (ffprobe-equivalent via PyAV) and preflight checks."""
from __future__ import annotations

from fractions import Fraction
from pathlib import Path

from .common import Paths, ffmpeg_exe, file_locked, read_json, run, write_json, write_text, fmt_ts, load_config, now_iso

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
                # variable frame rate (Zoom / Riverside / phone recordings): average rate far from the stream's base rate
                "fps_base": float(s.base_rate) if s.base_rate else None,
                "vfr": bool(s.average_rate and s.base_rate and
                            abs(float(s.average_rate) - float(s.base_rate)) / float(s.base_rate) > 0.005),
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


def _hist_np(im):
    """`_hist` as a NumPy vector: the same 768 bins, the same values (integer counts / the same total)."""
    import numpy as np
    a = np.asarray(im.resize((64, 36)).convert("RGB"))             # 36 x 64 x 3, uint8
    h = np.concatenate([np.bincount(a[:, :, c].ravel(), minlength=256) for c in range(3)]).astype(np.float64)
    return h / (float(h.sum()) or 1.0)


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


def analyze_shots(path: Path, duration_s: float, fps: float = 2.0, threshold: float = 0.55, start_s: float = 0.0) -> dict:
    """Find CUTAWAYS: stretches without the speaker, such as full-screen graphic cards burned into a finished episode,
    B-roll or another camera. Cropping a 16:9 card to 9:16 cuts its text, so the plan shows cutaways whole.
    The source is decoded once at `fps` (small frames); a sample is the speaker when a face is found OR it looks like
    the frames that have a face (colour-histogram intersection >= threshold), so a speaker turning away stays the
    speaker. Runs of >= 1 s of non-speaker samples are cutaways (dissolves included; a cut detector misses those).
    Measured on a real episode: speaker frames 0.89-0.93 (also without a face), graphic card 0.17-0.38."""
    import subprocess
    import numpy as np
    from PIL import Image
    from .previews import _face_center
    W, H = 480, 270
    rng = ["-ss", f"{start_s:.3f}", "-t", f"{duration_s:.3f}"] if start_s else []
    from .media_util import ff_popen
    rows = []
    # ff_popen: a watchdog kills a decoder stuck on a corrupt file or a stalled share (T2.15, MI-17)
    with ff_popen([ffmpeg_exe(), "-loglevel", "error", *rng, "-i", str(path), "-an", "-vf", f"fps={fps},scale={W}:{H}",
                   "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], stdout=subprocess.PIPE) as p:
        while True:
            b = p.stdout.read(W * H * 3)
            if len(b) < W * H * 3:
                break
            im = Image.frombuffer("RGB", (W, H), b, "raw", "RGB", 0, 1)
            rows.append({"t": len(rows) / fps, "face": bool(_face_center(im)), "hist": _hist_np(im)})
    face = np.array([r["face"] for r in rows], dtype=bool)
    if not face.any():
        return {"samples": len(rows), "cutaways_ms": [], "other_people_ms": [],
                "note": "no face found anywhere: cutaway detection skipped"}
    H_ = np.stack([r["hist"] for r in rows])                   # samples x 768 bins, every row one frame's histogram
    sim_to = lambda rows_idx, m: np.minimum(H_[rows_idx], m).sum(axis=1)     # histogram intersection with the mean
    fi = np.flatnonzero(face)
    mean = H_[fi].mean(axis=0)
    # a face is not enough: a two-person show cuts to the HOST (measured on a real episode: speaker 0.87-0.93, host
    # 0.65-0.67 with a face, graphic card 0.18-0.38). The speaker is whoever looks like the bulk of the face frames:
    # threshold = their median - 0.12 (never under `threshold`), and a second pass rebuilds the reference from them only
    face_sims = sim_to(fi, mean)
    sims = sorted(face_sims.tolist())
    thr = max(threshold, sims[len(sims) // 2] - 0.12)
    ref2 = fi[face_sims >= thr]
    if len(ref2):
        mean = H_[ref2].mean(axis=0)
        sims = sorted(sim_to(ref2, mean).tolist())
        thr = max(threshold, sims[len(sims) // 2] - 0.12)
    for r, sim in zip(rows, sim_to(slice(None), mean).tolist()):
        r.pop("hist")
        r["sim"] = round(sim, 3)
        r["speaker"] = r["sim"] >= thr
    cut = cutaway_ranges([r["speaker"] for r in rows], fps, duration_s)
    other = []
    for a, b in cut:   # mostly faces inside = another person on camera (host, guest), else a card / B-roll
        inside = [r for r in rows if a <= r["t"] * 1000 < b]
        if inside and sum(r["face"] for r in inside) >= 0.5 * len(inside):
            other.append([a, b])
    return {"samples": len(rows), "fps": fps, "threshold": round(thr, 3), "cutaways_ms": cut, "other_people_ms": other,
            "speaker_similarity_median": round(sims[len(sims) // 2], 3) if sims else None}


def auto_reframe(path: Path, v: dict, duration_s: float, sw: int, sh: int, samples: int = 9, start_s: float = 0.0) -> dict:
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
            t = start_s + duration_s * (k + 0.5) / samples
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
    from .common import source_range
    rng = source_range(paths)
    seq = load_config("sequence-settings.json")
    from .common import frame_size, seq_fps
    (sw, sh), sfps = frame_size(paths), seq_fps()        # T2.16: validated (common.frame_size), not read raw
    srate = seq["audio"]["sample_rate"]
    report = {"generated": now_iso(), "sequence": {"w": sw, "h": sh, "fps": round(sfps, 5), "audio_hz": srate},
              "files": [], "valid": [], "issues": [], "conversions": []}
    for f in main_footage:
        if not Path(f).exists():
            report["issues"].append({"file": str(f), "severity": "error", "msg": "missing"})
            continue
        pr = probe(f)
        report["files"].append(pr)
        v = pr["video"]
        start_s, dur_s = 0.0, pr.get("duration_s") or 0
        if rng and Path(f).name == Path(rng["footage"]).name:   # a reel cut from this file: analyse only its range
            start_s, dur_s = rng["in_ms"] / 1000, (rng["out_ms"] - rng["in_ms"]) / 1000
            pr["range"] = {"in_ms": rng["in_ms"], "out_ms": rng["out_ms"]}
            report["issues"].append({"file": str(f), "severity": "info",
                                     "msg": f"range {rng['in_ms'] / 1000:.3f}-{rng['out_ms'] / 1000:.3f}s of the file "
                                            f"({dur_s:.1f} s); times in this project are relative to the in-point"})
        if pr["errors"] or not v:
            report["issues"].append({"file": str(f), "severity": "error", "msg": "; ".join(pr["errors"]) or "no video stream"})
            continue
        report["valid"].append(str(f))
        nd = None
        try:                         # R-4.4: the real motion rate, VFR, HDR; intermediates are conformed later, in output/
            from .media_normalise import decide, intake_lines, measure
            nm = measure(f)
            nd = decide(nm, sfps)
            pr["normalise"] = {"measure": nm, "decision": {k: nd[k] for k in ("actions", "cfr_fps", "tonemap", "cadence")}}
            for ar, en in zip(intake_lines(nm, nd, "ar"), intake_lines(nm, nd, "en")):   # Arabic first, then English
                report["issues"].append({"file": str(f), "severity": "info", "msg": f"{ar}\n{en}",
                                         "msg_ar": ar, "msg_en": en})
        except Exception:  # noqa: BLE001  advisory: never stops the preflight
            nd = None
        # T26 wiring: a file whose decision has "cfr" gets its evenly timed copy made automatically (the conform step
        # after this preflight), so the old advice to ask for a constant-frame-rate export holds only without one
        cfr = bool(nd and "cfr" in (nd.get("actions") or []) and nd.get("cfr_fps"))
        if v.get("vfr"):
            head = (f"variable frame rate (average {v['fps']:.3f} fps vs base {v.get('fps_base') or 0:.3f} fps; typical of "
                    "Zoom/Riverside/phone recordings): ")
            if cfr:
                report["issues"].append({"file": str(f), "severity": "info",
                    "msg": head + f"an evenly timed copy at {nd['cfr_fps']:g} fps is made automatically for editing "
                                  "(in output/, recorded as normalise.conform in preflight.json) and Premiere imports it "
                                  "once it is ready; the original stays as it is."})
            else:
                report["issues"].append({"file": str(f), "severity": "warning",
                    "msg": head + "Premiere can drift out of sync on long files. Ask for a "
                                  "constant-frame-rate export of this file (e.g. HandBrake 'Constant Framerate') before "
                                  "editing."})
        # the rate Premiere will see: the copy's (the real motion rate) when one is made, else the file's own
        rate = float(nd["cfr_fps"]) if cfr else v["fps"]
        if rate and abs(rate - sfps) > 0.01:
            what = f"source {rate:.5g} fps" + (" (the real motion rate: the copy for editing runs at it)" if cfr else "")
            report["issues"].append({"file": str(f), "severity": "warning",
                "msg": f"{what} vs {sfps:.5g} fps sequence: Premiere drops/duplicates frames (motion "
                       f"judders), audio sync is preserved. If the client's reels are {rate:.5g} fps, set the profile's "
                       f"sequence rate: reel-profile/sequence-settings.json "
                       + ('{"general": {"timebase": %d, "ntsc": %s}}' % (round(rate), 'true' if abs(rate - round(rate)) > 0.001 else 'false'))})
        if (v["display_width"], v["display_height"]) != (sw, sh):
            sc = min(sw / v["display_width"], sh / v["display_height"])
            report["conversions"].append({"file": str(f), "type": "scale",
                "msg": f"display {v['display_width']}x{v['display_height']} -> scale {sc*100:.2f}% to fill {sw}x{sh}",
                "scale_percent": round(sc * 100, 3)})
            wider = Fraction(v["display_width"], v["display_height"]) != Fraction(sw, sh)
            if wider and rng.get("kind") == "episode_reel" and Path(f).name == Path(rng["footage"]).name:
                # podcast reel cut from a finished episode: framing per SHOT inside the window (shots.py); the plan
                # composes it with the story camera moves. One global crop would cut faces off at every camera change.
                from .gpu_lock import site_slot
                from .shots import analyze_window
                try:
                    with site_slot("shots", log_to=paths) as lane:      # T4.10: the verb takes the slot once, the helper gets the lane
                        report["shots"] = analyze_window(Path(f), int(rng["in_ms"]), int(rng["out_ms"] - rng["in_ms"]),
                                                         lane=lane)
                except Exception as e:  # noqa: BLE001  (analysis is an aid: the plan falls back to a centred crop)
                    report["shots"] = {"shots": [], "error": f"{type(e).__name__}: {e}"}
                    report["issues"].append({"file": str(f), "severity": "warning",
                                             "msg": f"shot analysis failed ({type(e).__name__}): the reel is centre-cropped"})
                cover = max(sw / v["display_width"], sh / v["display_height"])
                shots_ = report["shots"].get("shots", [])
                report.setdefault("reframe", {})[str(f)] = {
                    "base_scale_percent": round(cover * 100, 3), "offset_x": 0.0, "offset_y": 0.0, "cutaways_ms": [],
                    "mode": "per-shot", "shots": len(shots_), "faces": sum(1 for s in shots_ if s.get("n_faces"))}
                report["issues"].append({"file": str(f), "severity": "info",
                    "msg": f"per-shot 9:16 reframe: {len(shots_)} shots in the reel, faces found in "
                           f"{sum(1 for s in shots_ if s.get('n_faces'))}; wide shots follow the speaker "
                           "(00_inputs/speakers.json), shots without a face are shown whole"
                           + (f". {report['shots']['note']}" if report["shots"].get("note") else "")})
            elif wider:
                rf = auto_reframe(Path(f), v, dur_s, sw, sh, start_s=start_s)
                try:
                    shots = analyze_shots(Path(f), dur_s, start_s=start_s)
                except Exception as e:  # noqa: BLE001  (shot analysis is an aid; never block preflight)
                    shots = {"cutaways_ms": [], "error": f"{type(e).__name__}: {e}"}
                rf["cutaways_ms"] = shots["cutaways_ms"]
                rf["cutaway_analysis"] = {k: v for k, v in shots.items() if k != "cutaways_ms"}
                report.setdefault("reframe", {})[str(f)] = rf
                others = shots.get("other_people_ms") or []
                rf["other_people_ms"] = others
                cards = [c for c in shots["cutaways_ms"] if c not in others]
                if cards:
                    report["issues"].append({"file": str(f), "severity": "warning",
                        "msg": "source contains cutaways without the speaker (graphic cards / B-roll burned into the "
                               "footage) at " + ", ".join(f"{a / 1000:.1f}-{b / 1000:.1f}s" for a, b in cards)
                               + ": shown whole over a blurred fill instead of cropped; replace or cover them in the edit if "
                                 "the card's text matters"})
                if others:
                    report["issues"].append({"file": str(f), "severity": "warning",
                        "msg": "another person is on camera (host / second guest) at "
                               + ", ".join(f"{a / 1000:.1f}-{b / 1000:.1f}s" for a, b in others)
                               + ": shown whole over a blurred fill. The words there may be THEIRS, not the speaker's: check "
                                 "who speaks before quoting them on a graphic, or end the range before them"})
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
    pf = paths.p("00_inputs/preflight.json")
    pf.parent.mkdir(parents=True, exist_ok=True)
    with file_locked(pf):            # T26: the conform job updates this file too (read-modify-write under its lock)
        _initial_conform(paths, report, _read_doc(pf))
        write_json(pf, report)
    L = ["# Media Preflight", "", f"Generated {report['generated']}", "",
         f"Sequence target: {sw}x{sh} @ {sfps} fps, {srate} Hz", "", "## Files", ""]
    for pr in report["files"]:
        v = pr["video"] or {}
        L.append(f"- **{pr['name']}** — {pr.get('duration_s')}s, {v.get('codec')} {v.get('coded_width')}x{v.get('coded_height')} "
                 f"(display {v.get('display_width')}x{v.get('display_height')}, rot {v.get('rotation')}), {v.get('fps')} fps, "
                 f"{v.get('pix_fmt')}, TC {v.get('timecode')}; audio "
                 + ", ".join(f"{a['codec']} {a['sample_rate']}Hz {a['channels']}ch" for a in pr["audio"]))
    L += ["", "## Issues", ""] + [f"- [{i['severity']}] {Path(i['file']).name}: " + i["msg"].replace("\n", "\n  ")
                                   for i in report["issues"]] + \
         ["", "## Required conversions", ""] + ([f"- {c['msg']}" for c in report["conversions"]] or ["- none"]) + \
         ["", f"**Preflight {'PASSED' if report['ok'] else 'FAILED'}**"]
    write_text(paths.p("00_inputs/preflight-report.md"), "\n".join(L) + "\n")
    return report


def snap_range_points(path: Path, in_ms: int, out_ms: int, search_ms: int = 2500, min_quiet_ms: int = 250,
                      lead_ms: int = 100, tail_ms: int = 150) -> dict:
    """In/out-points of a range moved to the nearest pause, so a reel never starts or ends mid-word.
    Seen on a real reel: the in-point landed in the last syllable of the previous sentence (0.6 s of speech, then 1 s
    of silence). Quiet = 10 ms windows 30 dB under the loud speech of the area (relative, works on any level).
    In: just before speech resumes after a quiet run (run end - lead_ms). Out: just after speech stops (run start +
    tail_ms). A point already inside a quiet run stays."""
    import numpy as np
    ff = ffmpeg_exe()

    def env(t0_ms, dur_ms):
        t0_ms = max(0, t0_ms)
        import subprocess
        from .media_util import ff_timeout
        cmd = [ff, "-loglevel", "error", "-ss", f"{t0_ms / 1000:.3f}", "-t", f"{dur_ms / 1000:.3f}", "-i", str(path),
               "-map", "0:a:0", "-ac", "1", "-ar", "16000", "-f", "s16le", "-"]
        r = subprocess.run(cmd, capture_output=True, timeout=ff_timeout(cmd))         # T2.15: never hangs
        x = np.frombuffer(r.stdout or b"", dtype="<i2").astype(np.float32) / 32768
        h = 160
        n = len(x) // h
        return t0_ms, (20 * np.log10(np.sqrt((x[:n * h].reshape(n, h) ** 2).mean(axis=1)) + 1e-9) if n else np.zeros(0))

    def quiet_runs(t0, d):
        if not len(d):
            return []
        q = d < (np.percentile(d, 90) - 30)
        runs, i = [], 0
        while i < len(q):
            if q[i]:
                j = i
                while j < len(q) and q[j]:
                    j += 1
                if (j - i) * 10 >= min_quiet_ms:
                    runs.append((t0 + i * 10, t0 + j * 10))
                i = j
            else:
                i += 1
        return runs

    out = {}
    for kind, t in (("in", in_ms), ("out", out_ms)):
        if t is None:
            continue
        t0, d = env(t - search_ms, 2 * search_ms)
        runs = quiet_runs(t0, d)
        if any(a <= t <= b for a, b in runs):
            out[kind] = {"requested_ms": t, "suggested_ms": t, "moved_ms": 0, "note": "already in a pause"}
            continue
        cands = [b - lead_ms if kind == "in" else a + tail_ms for a, b in runs]
        cands = [c for c in cands if c >= 0]
        if not cands:
            out[kind] = {"requested_ms": t, "suggested_ms": t, "moved_ms": 0,
                         "note": f"no pause of {min_quiet_ms} ms within ±{search_ms / 1000:g} s: check it by ear"}
            continue
        best = min(cands, key=lambda c: abs(c - t))
        out[kind] = {"requested_ms": t, "suggested_ms": int(best), "moved_ms": int(best - t),
                     "note": "speech at the requested point: moved to the nearest pause"}
    return out


# --------------------------------------------------------------------------- T26 wiring: the conform step
# After a preflight, each main-footage file whose normalise.decision.actions is not empty gets its evenly timed / SDR
# copy (media_normalise.conform) in 00_inputs/intermediates/, recorded in preflight.json files[i].normalise.conform as
# hooks/t26/CONTRACT.md says (the Adobe half, ppro_build, imports it only when `ready`):
#   {state: ready | pending | failed | not_needed, path, parts: [{path, from_ms, to_ms}], cfr_fps, source_tag,
#    source_size, reason, lines: {ar, en}, at}
# Paths are relative to the client root, POSIX, always inside output/ (BL-14). `ready` = the copy exists, is a plain
# file under output/ with no link on the way, PyAV opens it, and the source still has the size, tag and age it had;
# anything else turns it back to `pending` and the job makes it again (reused when the sidecar still matches).
# The job: `reel conform --wait` (also what preflight starts in the background), one per item (the OS lock on
# 00_inputs/conform-job.lock, plus the claim 00_inputs/conform-job.claim for volumes without OS locks), the GPU lane
# from gpu_lock.site_slot("conform"), every record written under
# preflight.json's own file lock (common.file_locked + the atomic write_json). A preflight.json without normalise
# records (before Task 26) is never written. Nothing here ever fails the intake: a failure is a `failed` record.
CONFORM_ENV = "WHYNOT_CONFORM"          # background (default) | inline | off; inside the test sandbox: inline
CONFORM_MODES = ("background", "inline", "off")
CONFORM_KEYS = ("state", "path", "parts", "cfr_fps", "source_tag", "source_size", "reason", "lines", "at")
INTERMEDIATES_REL = "00_inputs/intermediates"
JOB_REL = "00_inputs/conform-job"       # its OS lock file is conform-job.lock (released by the OS when the job ends)
CLAIM_REL = "00_inputs/conform-job.claim"   # the running job's own record (O_EXCL: pid, process start, computer): the
                                        # exclusion where the volume takes no OS locks (macOS SMB/AFP, cloud drives)
CLAIM_WRITING_S = 10.0                  # an unreadable claim younger than this is still being written
JOB_START_S = 120.0                     # a `pending` record older than this with no live job: its job died
JOB_LOG_REL = "logs/conform-job.log"
JOB_WAIT_S = 12 * 3600.0                # `reel conform --wait` waits this long for a job that is already running
STALE_PASSES = 2                        # a source that changes during its encode is made again, at most this often
MTIME_SLACK_S = 2.0                     # FAT / SMB keep times in 2 s steps
_CHILDREN: list = []                    # background jobs started by this process (never collected while running)
_PENDING = ("The evenly timed / SDR copy of this clip is being made in the background: until it is ready, the "
            "original is used.",
            "النسخة المظبوطة من الفيديو ده بتتعمل في الخلفية: لحد ما تخلص هنستخدم الأصلي.")
_UNVERIFIED = ("The evenly timed / SDR copy was made but could not be checked: the original is used.",
               "النسخة المظبوطة اتعملت بس ماقدرناش نتأكد منها: هنستخدم الأصلي.")
_FAILED = ("Making the evenly timed / SDR copy failed: the original is used.",
           "عمل النسخة المظبوطة فشل: هنستخدم الأصلي.")
_NO_COPY_ADVICE = ("Without that copy Premiere can drift out of sync or judder on this file: ask for a "
                   "constant-frame-rate export of it (e.g. HandBrake 'Constant Framerate') before editing.",
                   "من غير النسخة دي بريمير ممكن الصوت يبعد عن الصورة أو الحركة تتقطع في الملف ده: اطلب نسخة منه "
                   "بمعدل فريمات ثابت (زي HandBrake «Constant Framerate») قبل المونتاج.")
_JOB_DIED = ("The background job making the evenly timed / SDR copy stopped before it finished (it was closed or "
             "stopped, or the computer restarted): the original is used. Run `reel conform --wait` to make it.",
             "الشغل اللي في الخلفية بتاع النسخة المظبوطة وقف قبل ما يخلص (اتقفل أو اتوقف أو الجهاز اتعمله ريستارت): "
             "هنستخدم الأصلي. شغّل reel conform --wait عشان تتعمل.")
_BUILD_PENDING = ("The constant-frame-rate copy is still being made: this build uses the original file. Build again "
                  "once it is ready.",
                  "النسخة الثابتة لسه بتتعمل: البناء ده من الملف الأصلي. ابنِ تاني بعد ما تخلص.")   # CONTRACT.md step 3
_BUILD_STALE = ("The evenly timed / SDR copy is out of date ({why}): this build uses the original file. Run "
                "`reel conform --wait`, then build again.",
                "النسخة المظبوطة مابقتش مطابقة للملف ({why}): البناء ده من الملف الأصلي. شغّل reel conform --wait "
                "وبعدين ابنِ تاني.")


def _read_doc(pf: Path):
    """preflight.json as a dict, or None (missing, unreadable, not JSON): never raises."""
    try:
        doc = read_json(pf)
    except (OSError, ValueError):
        return None
    return doc if isinstance(doc, dict) else None


def _lines(pair) -> dict:
    en, ar = pair
    return {"ar": [ar], "en": [en]}


def _same_file(a, b) -> bool:
    import os
    return os.path.normcase(os.path.abspath(str(a))) == os.path.normcase(os.path.abspath(str(b)))


def _src_rel(paths: Paths, src) -> str:
    """The source as the summary names it: client-root-relative POSIX when inside the client, else as recorded."""
    import os
    from .media_normalise import _under
    rel = _under(os.path.abspath(str(src)), os.path.abspath(str(paths.root)))
    return rel.replace("\\", "/") if rel else str(src)


def client_rel(paths: Paths, p) -> str | None:
    """A copy's path as the record keeps it: relative to the client root, POSIX, `output/...` (a copy written into a
    linked output/ folder, through its real folder, is named through output/ too). None when it is not inside output/
    (never recorded: the contract allows nothing else)."""
    import os
    from .media_normalise import _under
    if not p:
        return None
    a = os.path.abspath(str(p))
    out = os.path.join(os.path.abspath(str(paths.root)), "output")
    for base in (out, os.path.realpath(out)):
        rel = _under(a, base)
        if rel:                                             # '' is output/ itself: never a copy
            parts = rel.replace("\\", "/").split("/")
            if "" in parts or "." in parts or ".." in parts:
                return None
            return "output/" + "/".join(parts)
    return None


def conform_windows(paths: Paths, src):
    """The source windows (seconds, source clock) this item uses: the Gate 0 window of a reel cut from an episode (or
    any range, `reel range`) when `src` is its footage; None for a whole clip (the whole file is conformed)."""
    from .common import source_range
    rng = source_range(paths)
    if not rng or rng.get("out_ms") is None or not _same_file(src, Path(paths.root) / rng["footage"]):
        return None                                         # by its path: cam A's C0001.MP4 is not cam B's
    return [(int(rng["in_ms"]) / 1000, int(rng["out_ms"]) / 1000)]


def _facts(paths: Paths, src) -> dict | None:
    """{tag, size, mtime} of the source now, or None when it is gone."""
    import os
    from . import media_normalise as MN
    try:
        st = os.stat(src)
    except OSError:
        return None
    return {"tag": MN._source_tag(Path(src), paths.root), "size": int(st.st_size), "mtime": st.st_mtime}


def _record(paths: Paths, src, state: str, *, cfr_fps=None, path=None, parts=(), reason=None, lines=None,
            facts=None) -> dict:
    from . import media_normalise as MN
    facts = facts or _facts(paths, src) or {"tag": MN._source_tag(Path(src), paths.root), "size": 0}
    ln = lines or {}
    ar, en = list(ln.get("ar") or []), list(ln.get("en") or [])
    if state == "failed" and cfr_fps and _NO_COPY_ADVICE[0] not in en:   # no evenly timed copy: the old advice again
        en.append(_NO_COPY_ADVICE[0])
        ar.append(_NO_COPY_ADVICE[1])
    return {"state": state, "path": path, "parts": [dict(x) for x in parts],
            "cfr_fps": float(cfr_fps) if cfr_fps else None, "source_tag": facts["tag"],
            "source_size": int(facts["size"]), "reason": reason, "lines": {"ar": ar, "en": en}, "at": now_iso()}


def _pending(paths: Paths, src, decision: dict, reason: str) -> dict:
    return _record(paths, src, "pending", cfr_fps=(decision or {}).get("cfr_fps"), reason=reason,
                   lines=_lines(_PENDING))


def _copy_problem(paths: Paths, rel) -> str | None:
    """Why the copy named `rel` can't be used (None = it can): a client-relative output/ path, its folder inside the
    client's output/ with no link on the way (media_normalise.client_output, fails closed), a plain file (never a link
    or a hard link) with bytes in it."""
    from . import media_normalise as MN
    if not isinstance(rel, str) or not rel.startswith("output/") or "\\" in rel or ".." in rel.split("/"):
        return f"{rel!r} is not a client-relative path inside output/"
    full = Path(paths.root) / rel
    if MN.client_output(full.parent, paths.root) is None:
        return f"{rel} is not inside the client's output/ folder (or a link is on the way)"
    if not MN._plain_file(full):
        return f"{rel} is missing (or is a link)"
    if full.stat().st_size <= 0:
        return f"{rel} is empty"
    return None


def conform_current(paths: Paths, src, rec, decision=None, windows=None) -> str | None:
    """None when the `ready` record `rec` still describes a usable copy of `src`, else why not: the source's size, tag
    (its client-relative path) or age changed (newer than its copy), the copy is gone / not a plain file under output/,
    the decision's rate changed, or the copies no longer cover this item's windows (`windows` as conform_windows
    gives them; None = a whole-file copy)."""
    import os
    if not isinstance(rec, dict) or rec.get("state") != "ready":
        return "it is not ready"
    facts = _facts(paths, src)
    if facts is None:
        return "the source file is gone"
    if facts["size"] != rec.get("source_size"):
        return "the source size changed"
    if facts["tag"] != rec.get("source_tag"):
        return "the source tag changed (the file was moved or renamed)"
    if decision is not None and (decision.get("cfr_fps") or None) != (rec.get("cfr_fps") or None):
        return "the frame rate to conform to changed"
    whole, parts = rec.get("path"), rec.get("parts") or []
    if bool(whole) == bool(parts):
        return "the record names no copy (or both a whole copy and parts)"
    if windows is None and not whole:
        return "this item uses the whole file but the record has parts"
    if windows is not None:
        if whole:
            return "this item uses windows but the record has a whole-file copy"
        for a, b in windows:
            if not any(isinstance(x, dict) and x.get("from_ms") is not None and x.get("to_ms") is not None
                       and x["from_ms"] <= round(a * 1000) and x["to_ms"] >= round(b * 1000) for x in parts):
                return f"no part covers the window {a:g}-{b:g} s"
    for rel in ([whole] if whole else [x.get("path") if isinstance(x, dict) else None for x in parts]):
        why = _copy_problem(paths, rel)
        if why:
            return why
        if facts["mtime"] > os.stat(Path(paths.root) / rel).st_mtime + MTIME_SLACK_S:
            return "the source is newer than its copy"
    return None


def _initial_conform(paths: Paths, report: dict, old: dict | None) -> None:
    """preflight: the conform record of each measured file. Nothing to change -> not_needed; a copy from the last run
    that is still current -> kept `ready`; everything else -> `pending` (the conform step after the preflight makes
    it). Never raises (a record that can't be built is `failed`, with the reason)."""
    olds = [x for x in ((old or {}).get("files") or []) if isinstance(x, dict)]
    for pr in report["files"]:
        nz = pr.get("normalise")
        if not isinstance(nz, dict) or not isinstance(nz.get("decision"), dict):
            continue
        src, dec = pr["path"], nz["decision"]
        try:
            if not dec.get("actions"):
                nz["conform"] = _record(paths, src, "not_needed")
                continue
            prev = next((((x.get("normalise") or {}).get("conform")) for x in olds
                         if x.get("path") and _same_file(x["path"], src)), None)
            if isinstance(prev, dict) and prev.get("state") == "ready" and \
                    conform_current(paths, src, prev, dec, conform_windows(paths, src)) is None:
                nz["conform"] = prev
                continue
            nz["conform"] = _pending(paths, src, dec, "queued: the copy is made after the preflight")
        except Exception as e:  # noqa: BLE001  the preflight never fails because of the copy
            nz["conform"] = _record(paths, src, "failed", cfr_fps=dec.get("cfr_fps"),
                                    reason=f"{type(e).__name__}: {str(e)[:200]}", lines=_lines(_FAILED),
                                    facts={"tag": "0" * 10, "size": 0})


def _measured(doc) -> list:
    """The file records of preflight.json that carry a normalise decision (Task 26 and later)."""
    return [x for x in ((doc or {}).get("files") or []) if isinstance(x, dict) and x.get("path")
            and isinstance(x.get("normalise"), dict) and isinstance(x["normalise"].get("decision"), dict)]


def _refresh(paths: Paths, retry_failed: bool) -> list:
    """Under preflight.json's lock: a stale `ready` (or a not_needed whose source changed) -> pending, a missing
    record -> pending or not_needed, a `failed` one -> pending when `retry_failed`. Writes only when something changed.
    Returns the sources still to make (pending)."""
    pf = paths.p("00_inputs/preflight.json")
    todo = []
    with file_locked(pf):
        doc = _read_doc(pf)
        changed = False
        for fr in _measured(doc):
            nz, src = fr["normalise"], fr["path"]
            dec, rec = nz["decision"], nz.get("conform")
            state = rec.get("state") if isinstance(rec, dict) else None
            new = rec
            if not dec.get("actions"):
                f = _facts(paths, src)
                if state == "not_needed" and f and (f["tag"], f["size"]) == (rec.get("source_tag"),
                                                                             rec.get("source_size")):
                    continue
                if state is None:
                    new = _record(paths, src, "not_needed")
                elif state != "pending":
                    new = _pending(paths, src, dec, "the source changed: it is measured again")
            elif state == "ready":
                why = conform_current(paths, src, rec, dec, conform_windows(paths, src))
                if why:
                    new = _pending(paths, src, dec, f"the copy is stale ({why}): it is made again")
            elif state == "failed" and not retry_failed:
                continue
            elif state != "pending":
                new = _pending(paths, src, dec, "queued: the copy is made again" if state == "failed" else
                               "queued: the copy is made after the preflight")
            if new is not rec:
                nz["conform"] = new
                changed = True
            if isinstance(new, dict) and new.get("state") == "pending":
                todo.append(src)
        if changed:
            write_json(pf, doc)
    return todo


def _store(paths: Paths, src, rec: dict, nm=None, nd=None) -> None:
    """One file's record (and its fresh measurement, when the job measured again) into preflight.json, under its
    lock; a file the preflight no longer lists is left alone."""
    pf = paths.p("00_inputs/preflight.json")
    with file_locked(pf):
        doc = _read_doc(pf)
        fr = next((x for x in _measured(doc) if _same_file(x["path"], src)), None)
        if fr is None:
            return
        if nd is not None:
            fr["normalise"]["measure"] = nm
            fr["normalise"]["decision"] = {k: nd[k] for k in ("actions", "cfr_fps", "tonemap", "cadence")}
        fr["normalise"]["conform"] = rec
        write_json(pf, doc)


def _verify(paths: Paths, rel: str) -> str | None:
    """The engine's check before `ready`: a usable path (_copy_problem) that PyAV opens with a video stream and a
    duration (the ffprobe-equivalent the engine uses everywhere)."""
    why = _copy_problem(paths, rel)
    if why:
        return why
    pr = probe(Path(paths.root) / rel)
    if pr.get("errors") or not pr.get("video") or not pr.get("duration_s"):
        return f"{rel} does not open as a video ({'; '.join(pr.get('errors') or []) or 'no video stream'})"
    return None


def _conform_one(paths: Paths, src, lane: str):
    """Measure the source again, make (or reuse) its copy, verify it. Returns (record, measure, decision); never
    raises (a failure is a `failed` record with the reason and the plain lines)."""
    from . import media_normalise as MN
    from .common import seq_fps
    before = _facts(paths, src)
    if before is None:
        return _record(paths, src, "failed", reason="the source file is gone", lines=_lines(_FAILED),
                       facts={"tag": MN._source_tag(Path(src), paths.root), "size": 0}), None, None
    nm = nd = None
    try:
        nm = MN.measure(src)
        nd = MN.decide(nm, seq_fps())
        if nm.get("errors"):
            return _record(paths, src, "failed", reason="the source could not be measured: " + "; ".join(nm["errors"]),
                           lines=_lines(_FAILED), facts=before), nm, nd
        if not nd.get("actions"):
            return _record(paths, src, "not_needed", facts=before), nm, nd
        windows = conform_windows(paths, src)
        res = MN.conform(Path(src), paths.p(INTERMEDIATES_REL), nd, lane=lane, ranges=windows, client_root=paths.root)
    except Exception as e:  # noqa: BLE001  the original stays the one used
        return _record(paths, src, "failed", cfr_fps=(nd or {}).get("cfr_fps"), reason=f"{type(e).__name__}: "
                       f"{str(e)[:300]}", lines=_lines(_FAILED), facts=before), nm, nd
    cfr = nd.get("cfr_fps")
    if not res.get("ok"):
        reason = res.get("reason") or (f"skipped: {res['skipped']}" if res.get("skipped") else "the copy was not made")
        return _record(paths, src, "failed", cfr_fps=cfr, reason=reason, lines=res.get("lines") or _lines(_FAILED),
                       facts=before), nm, nd
    if windows:
        parts = [{"path": client_rel(paths, x.get("path")), "from_ms": int(round(float(x["from_s"]) * 1000)),
                  "to_ms": int(round(float(x["to_s"]) * 1000))} for x in res.get("parts") or []]
        whole, rels = None, [x["path"] for x in parts]
    else:
        parts, whole = [], client_rel(paths, res.get("path"))
        rels = [whole]
    if not rels or any(r is None for r in rels):
        return _record(paths, src, "failed", cfr_fps=cfr, reason="the copy was written outside the client's output/ "
                       "folder: it is never used", lines=_lines(_UNVERIFIED), facts=before), nm, nd
    for rel in rels:
        why = _verify(paths, rel)
        if why:
            return _record(paths, src, "failed", cfr_fps=cfr, reason=f"the copy could not be verified: {why}",
                           lines=_lines(_UNVERIFIED), facts=before), nm, nd
    if _facts(paths, src) != before:                      # the editor replaced the file during the encode
        return _pending(paths, src, nd, "the source changed while its copy was made: it is made again"), nm, nd
    return _record(paths, src, "ready", cfr_fps=cfr, path=whole, parts=parts, reason=res.get("reason"),
                   lines=res.get("lines"), facts=before), nm, nd


def conform_summary(paths: Paths) -> dict:
    """{state, files: [{file, state, path, parts, cfr_fps, reason, lines}], job, pid}. state: "none" (no record:
    no preflight yet, or one from before Task 26), else pending > failed > ready > not_needed."""
    doc = _read_doc(paths.p("00_inputs/preflight.json")) if getattr(paths, "video_id", None) else None
    files = []
    for fr in _measured(doc):
        rec = fr["normalise"].get("conform")
        if isinstance(rec, dict):
            files.append({"file": _src_rel(paths, fr["path"]), **{k: rec.get(k) for k in
                          ("state", "path", "parts", "cfr_fps", "reason", "lines")}})
    states = {x["state"] for x in files}
    state = next((s for s in ("pending", "failed", "ready", "not_needed") if s in states), "none")
    return {"state": state, "files": files, "job": None, "pid": None}


def _read_claim(cp: Path):
    """The claim record: None when there is none, {} when it can't be read as one."""
    import json
    try:
        rec = json.loads(cp.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except (OSError, ValueError):
        return {}
    return rec if isinstance(rec, dict) else {}


def _claim_live(cp: Path, rec=None) -> bool:
    """Does the claim `cp` belong to a job that is still running? This computer: its pid is alive and still the same
    process (never this process: here the OS lock's in-process part already excludes a second job). Another computer:
    younger than JOB_WAIT_S (its pid can't be checked from here). Unreadable: younger than CLAIM_WRITING_S."""
    import os
    import time
    from . import writer_lock as WL
    rec = _read_claim(cp) if rec is None else rec
    if rec is None:
        return False
    try:
        age = time.time() - os.stat(cp).st_mtime
    except OSError:
        return False
    if not rec:
        return age < CLAIM_WRITING_S
    if WL.same_host(rec):
        return str(rec.get("pid")) != str(os.getpid()) and WL.pid_alive(rec.get("pid"), rec.get("pid_created"))
    return age < JOB_WAIT_S


def _job_claim(paths: Paths, wait_s: float):
    """Hold the item's job claim (CLAIM_REL) for the with-block: created with O_EXCL; a claim whose job is gone
    (_claim_live) is moved aside, checked to be the one judged, and replaced; the claim is removed at the end when it
    is still ours. Raises LockTimeout when a live job keeps it longer than `wait_s`."""
    import contextlib
    import os
    import socket
    import time
    from . import writer_lock as WL
    from .file_lock import LockTimeout

    @contextlib.contextmanager
    def held():
        cp = paths.p(CLAIM_REL)
        me = {"pid": os.getpid(), "pid_created": WL.process_created(os.getpid()), "host": socket.gethostname(),
              "host_id": WL.host_id(), "started_at": now_iso()}
        deadline = time.monotonic() + max(0.0, float(wait_s))
        while not WL._create(cp, me):                       # the writer lease's own exclusive create
            seen = _read_claim(cp)
            if seen is not None and not _claim_live(cp, seen):
                aside = cp.with_name(f"{cp.name}.stale-{os.getpid()}")
                try:
                    os.replace(cp, aside)
                except FileNotFoundError:
                    continue
                except OSError:
                    pass
                else:
                    if _read_claim(aside) == seen:          # the claim judged dead, not a new one made meanwhile
                        with contextlib.suppress(OSError):
                            aside.unlink()
                        continue
                    WL._restore(aside, cp)                  # a live job's fresh claim: put back, never over another
            if time.monotonic() >= deadline:
                raise LockTimeout(cp, round(float(wait_s), 1))
            time.sleep(0.25)
        try:
            yield cp
        finally:
            if _read_claim(cp) == me:
                with contextlib.suppress(OSError):
                    cp.unlink()
    return held()


def _job_running(paths: Paths) -> bool:
    """A conform job of this item runs: it holds the OS lock (another process, or another thread here), or a live
    claim (the volume takes no OS locks)."""
    from .file_lock import LockTimeout
    try:
        with file_locked(paths.p(JOB_REL), 0):
            pass
    except LockTimeout:
        return True
    return _claim_live(paths.p(CLAIM_REL))


def run_conform_job(paths: Paths, wait_s: float = 0.0) -> dict:
    """The conform job of one item (in this process): every pending file is made, verified and recorded; stale
    copies found on the way are made again (STALE_PASSES). One job per item (the OS lock, plus the claim for volumes
    without OS locks): with another one running, it waits up to `wait_s` for it (`job: "running"` when it is still
    running; a dead job's claim is taken over). Returns conform_summary() with job "done"."""
    import contextlib
    import time
    from .file_lock import LockTimeout
    pf = paths.p("00_inputs/preflight.json")
    if not _measured(_read_doc(pf)):
        return conform_summary(paths)                       # nothing to do, and an old file is never written
    stack = contextlib.ExitStack()
    t0 = time.monotonic()
    try:
        stack.enter_context(file_locked(paths.p(JOB_REL), wait_s))
        stack.enter_context(_job_claim(paths, max(0.0, wait_s - (time.monotonic() - t0))))
    except LockTimeout:
        stack.close()
        return dict(conform_summary(paths), job="running")
    with stack:
        for _ in range(STALE_PASSES + 1):
            todo = _refresh(paths, retry_failed=False)
            if not todo:
                break
            try:
                from . import gpu_lock
                with gpu_lock.site_slot("conform", log_to=paths) as lane:
                    for src in todo:
                        rec, nm, nd = _conform_one(paths, src, lane)
                        _store(paths, src, rec, nm, nd)
            except Exception as e:  # noqa: BLE001  a slot or a write that broke: the files left pending are failed
                why = f"{type(e).__name__}: {str(e)[:300]}"
                try:
                    for fr in _measured(_read_doc(pf)):
                        rec = fr["normalise"].get("conform")
                        if isinstance(rec, dict) and rec.get("state") == "pending":
                            _store(paths, fr["path"], _record(paths, fr["path"], "failed", cfr_fps=rec.get("cfr_fps"),
                                                              reason=why, lines=_lines(_FAILED)))
                except Exception:  # noqa: BLE001  that write broke too: the records stay pending (`--wait` makes them)
                    pass
                break
    return dict(conform_summary(paths), job="done")


def _popen(cmd, **kw):
    """subprocess.Popen for the background job only (tests replace this)."""
    import subprocess
    return subprocess.Popen(cmd, **kw)


def _spawn_job(paths: Paths) -> int:
    """Start `reel conform --wait` for this item as a detached process (the same interpreter and engine; Windows
    CREATE_NEW_PROCESS_GROUP | CREATE_NO_WINDOW, CREATE_BREAKAWAY_FROM_JOB tried first so the caller's job object
    can't take it down; POSIX a new session), its output appended to logs/conform-job.log. Never DETACHED_PROCESS
    (review 99f6357 P2-1): with it Windows ignores CREATE_NO_WINDOW, so the venv's python.exe launcher's interpreter
    and every ffmpeg the job starts got a NEW visible console, and closing that window killed the job. Without it the
    job owns a hidden console of its own, which its children inherit, and which is not the caller's terminal (closing
    the terminal never reaches it). It inherits WHYNOT_LOCK_SESSION, so it is the same writer of the client folder.
    Returns its pid."""
    import os
    import subprocess
    import sys
    cli = Path(__file__).resolve().parents[1] / "cli.py"
    cmd = [sys.executable, *(["-s"] if sys.flags.no_user_site else []), "-B", str(cli), "--root", str(paths.root)]
    cmd += ["--episode", paths.episode_id] if getattr(paths, "episode_id", None) else ["--video-id", str(paths.video_id)]
    cmd += ["conform", "--wait"]
    log_path = paths.p(JOB_LOG_REL)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ, PYTHONUTF8="1", PYTHONIOENCODING="utf-8", PYTHONDONTWRITEBYTECODE="1")
    env[CONFORM_ENV] = "inline"                             # the job itself never starts another one
    with open(log_path, "ab") as logf:
        logf.write(f"[{now_iso()}] conform job started for {paths.video_id}\n".encode("utf-8"))
        logf.flush()
        kw = {"stdin": subprocess.DEVNULL, "stdout": logf, "stderr": logf, "cwd": str(cli.parent), "env": env,
              "close_fds": True}
        if os.name == "nt":
            flags = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW
            try:
                proc = _popen(cmd, creationflags=flags | subprocess.CREATE_BREAKAWAY_FROM_JOB, **kw)
            except OSError:                                  # the caller's job forbids breakaway: start inside it
                proc = _popen(cmd, creationflags=flags, **kw)
        else:
            proc = _popen(cmd, start_new_session=True, **kw)
    _CHILDREN.append(proc)
    return proc.pid


def _mode(mode=None) -> str:
    import os
    from .plat import SANDBOX_ENV
    m = str(mode or os.environ.get(CONFORM_ENV) or "").strip().lower()
    if m in CONFORM_MODES:
        return m
    return "inline" if os.environ.get(SANDBOX_ENV) else "background"   # a unit test never leaves a process behind


def start_conform(paths: Paths, mode: str | None = None) -> dict:
    """The conform step after the preflight (and `reel conform` without --wait): refresh the records (a failed one is
    tried again, a stale `ready` is made again), then make what is pending: in a detached background job (default), in
    this process ("inline"), or not at all ("off": the records stay pending). WHYNOT_CONFORM chooses when `mode` is
    None. Returns conform_summary() with job: None (nothing to do) | "started" (+ pid) | "running" | "inline" | "off".
    Never raises: anything that breaks is a `failed` record with the reason."""
    pf = paths.p("00_inputs/preflight.json")
    if not _measured(_read_doc(pf)):
        return conform_summary(paths)
    m = _mode(mode)
    try:
        todo = _refresh(paths, retry_failed=True)
        if not todo:
            return conform_summary(paths)
        if m == "off":
            return dict(conform_summary(paths), job="off")
        if m == "inline":
            return dict(run_conform_job(paths), job="inline")
        if _job_running(paths):
            return dict(conform_summary(paths), job="running")
        pid = _spawn_job(paths)
        return dict(conform_summary(paths), job="started", pid=pid)
    except Exception as e:  # noqa: BLE001  the intake never fails because of the copy
        why = f"{type(e).__name__}: {str(e)[:300]}"
        try:
            for fr in _measured(_read_doc(pf)):
                rec = fr["normalise"].get("conform")
                if isinstance(rec, dict) and rec.get("state") == "pending":
                    _store(paths, fr["path"], _record(paths, fr["path"], "failed", cfr_fps=rec.get("cfr_fps"),
                                                      reason=why, lines=_lines(_FAILED)))
        except Exception:  # noqa: BLE001
            pass
        return dict(conform_summary(paths), state="failed", reason=why, lines=_lines(_FAILED))


def _age_s(iso) -> float:
    """Seconds since an ISO time (a record's `at`); infinite when it can't be read."""
    import datetime as dt
    try:
        t = dt.datetime.fromisoformat(str(iso))
    except (TypeError, ValueError):
        return float("inf")
    if t.tzinfo is None:
        t = t.astimezone()
    return (dt.datetime.now().astimezone() - t).total_seconds()


def _reap_dead_job(paths: Paths, src) -> dict | None:
    """`src`'s pending record when its job died (review 99f6357 P3-2: no job of this item runs, and it was queued
    over JOB_START_S ago): recorded as failed (_JOB_DIED), under preflight.json's lock. Returns that record; None
    when the record is left as it is."""
    pf = paths.p("00_inputs/preflight.json")
    with file_locked(pf):
        doc = _read_doc(pf)
        fr = next((x for x in _measured(doc) if _same_file(x["path"], src)), None)
        rec = fr["normalise"].get("conform") if fr else None
        if not isinstance(rec, dict) or rec.get("state") != "pending" or _age_s(rec.get("at")) < JOB_START_S \
                or _job_running(paths):
            return None
        new = _record(paths, src, "failed", cfr_fps=rec.get("cfr_fps"), lines=_lines(_JOB_DIED),
                      reason="the background job stopped before the copy was made: run `reel conform --wait`")
        fr["normalise"]["conform"] = new
        write_json(pf, doc)
        return new


def conform_import(paths: Paths, src) -> dict:
    """ppro_build's one call before it imports main footage (hooks/t26/CONTRACT.md, the Adobe half): what Premiere
    imports for `src` (absolute, or relative to the client root; a bare file name only when exactly one measured file
    has that name). {use: "copy" | "original", state, path, parts, reason, lines: {ar, en}}:
      * use "copy" only for a `ready` record that is still current NOW (conform_current: the source's size, tag and
        age, the copy a plain non-empty file under output/ with no link on the way, this item's windows covered):
        `path` (a whole-file copy) or `parts` [{path, from_ms, to_ms}], client-relative POSIX, resolved by the caller
        against the client root;
      * else use "original" (path None, parts []) and `lines` = the one build warning: pending -> CONTRACT's line;
        failed -> the engine's own lines; a ready copy no longer current -> why, and `reel conform --wait`. A pending
        record whose job died is recorded as failed first (_reap_dead_job). state "none" (no record: a preflight.json
        from before Task 26, or none) and "not_needed" have no lines.
    Never raises (anything unexpected: the original, with the failure's lines)."""
    import os
    res = {"use": "original", "state": "none", "path": None, "parts": [], "reason": None,
           "lines": {"ar": [], "en": []}}
    try:
        s = Path(src)
        full = s if s.is_absolute() else Path(paths.root) / s
        doc = _read_doc(paths.p("00_inputs/preflight.json")) if getattr(paths, "video_id", None) else None
        frs = _measured(doc)
        fr = next((x for x in frs if _same_file(x["path"], full)), None)
        if fr is None and not s.is_absolute() and len(s.parts) == 1:
            named = [x for x in frs if os.path.normcase(Path(x["path"]).name) == os.path.normcase(s.name)]
            fr = named[0] if len(named) == 1 else None
        rec = fr["normalise"].get("conform") if fr else None
        state = rec.get("state") if isinstance(rec, dict) else None
        if state not in ("ready", "pending", "failed", "not_needed"):
            return res
        res["state"] = state
        if state == "not_needed":
            return res
        if state == "pending":
            dead = _reap_dead_job(paths, fr["path"])
            if dead is None:
                return dict(res, reason=rec.get("reason"), lines=_lines(_BUILD_PENDING))
            rec, state = dead, "failed"
            res["state"] = state
        if state == "failed":
            ln = rec.get("lines") if isinstance(rec.get("lines"), dict) else {}
            return dict(res, reason=rec.get("reason"), lines={"ar": list(ln.get("ar") or []),
                                                              "en": list(ln.get("en") or [])})
        why = conform_current(paths, fr["path"], rec, fr["normalise"]["decision"], conform_windows(paths, fr["path"]))
        if why:
            en, ar = _BUILD_STALE
            return dict(res, reason=why, lines={"ar": [ar.format(why=why)], "en": [en.format(why=why)]})
        return dict(res, use="copy", path=rec.get("path") or None, reason=rec.get("reason"),
                    parts=[{k: x[k] for k in ("path", "from_ms", "to_ms")} for x in rec.get("parts") or []])
    except Exception as e:  # noqa: BLE001  the build never fails because of the copy
        return dict(res, use="original", state="failed", path=None, parts=[], reason=f"{type(e).__name__}: {e}"[:300],
                    lines=_lines(_FAILED))
