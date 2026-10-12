"""Watchable preview of the planned edit, rendered by the engine alone (no Premiere, macOS or Windows).

It mirrors what `ppro-build` gives Premiere: the same footage pieces (pause cuts, jump-cut zoom masks, punch-ins), the
same graphic and caption layers from `ppro_build.job_data()` with the same keyframe presets (bar_sweep, text_pop,
slide, push, card, flash, fade), the cleaned dialogue and the SFX cues. Use it at Gate 1 so the editor can WATCH the edit
before approving, and to review revisions quickly. It is a proxy (540x960 H.264), not the deliverable: the editor still
finishes, mixes and renders in Premiere.
"""
from __future__ import annotations

import subprocess
import time
import wave
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

from .common import fps_arg, frame_size, seq_fps, Paths, ffmpeg_exe, log, now_iso, read_json, write_json

SR = 48000
F = 1 / 24   # animation time unit (the Premiere JSX presets use the same 1/24 s), not the sequence rate


# --------------------------------------------------------------------------- animation (same presets as nh_ppro_lib.jsx)
def anim_state(g: dict, u: float) -> dict:
    """Opacity 0-1, scale, crop_left 0-1 (fraction hidden from the left) and x shift (px of the sequence frame) at local time u."""
    dur = g["end_s"] - g["start_s"]
    fo = min(g.get("fade_out_s") or 0, dur / 3)
    out = 1.0 if fo <= 0 or u < dur - fo else max(0.0, (dur - u) / fo)
    lin = lambda t, a, b, v0, v1: v0 if t <= a else v1 if t >= b else v0 + (v1 - v0) * (t - a) / (b - a)
    st = {"opacity": out, "scale": 1.0, "crop_left": 0.0, "dx": 0.0}
    a = g.get("anim")
    if a == "flash":
        peak = (g.get("peak") or 90) / 100
        st["opacity"] = lin(u, 0, dur / 2, 0, peak) if u < dur / 2 else lin(u, dur / 2, dur, peak, 0)
    elif a == "text_pop":
        st["opacity"] = min(out, lin(u, 0, 2 * F, 0, 1))
        st["scale"] = lin(u, 0, 4 * F, 0.9, 1.0)
    elif a == "bar_sweep":
        d0, sw = (g.get("delay_f") or 1) * F, (g.get("sweep_f") or 6) * F
        st["crop_left"] = lin(u, d0, d0 + sw, 1.0, 0.0)
    elif a == "slide":
        st["dx"] = lin(u, 0, 5 * F, 60, 0)
        st["opacity"] = min(out, lin(u, 0, 4 * F, 0, 1))
    elif a == "push":
        st["opacity"] = min(out, lin(u, 0, 6 * F, 0, 1))
        st["scale"] = lin(u, 0, dur, 1.0, 1.03)
    elif a == "card":
        fi = min(g.get("fade_in_s") or 10 * F, dur / 3)
        st["opacity"] = min(out, lin(u, 0, fi, 0, 1))
        st["scale"] = lin(u, 0, fi, 0.96, 1.0)
    else:
        st["opacity"] = min(out, lin(u, 0, 5 * F, 0, 1))
    return st


class _Stills:
    """Loads each still once at preview size (small LRU, stills are ~2 MB each at 540x960)."""

    def __init__(self, W: int, H: int, cap: int = 48):
        self.W, self.H, self.cap, self.cache = W, H, cap, {}

    def get(self, png: str) -> Image.Image:
        im = self.cache.pop(png, None)
        if im is None:
            im = Image.open(png).convert("RGBA").resize((self.W, self.H), Image.BILINEAR)
        self.cache[png] = im
        if len(self.cache) > self.cap:
            self.cache.pop(next(iter(self.cache)))
        return im


def _apply(layer: Image.Image, st: dict, k: float) -> Image.Image | None:
    if st["opacity"] <= 0.003 or st["crop_left"] >= 0.999:
        return None
    W, H = layer.size
    im = layer
    if abs(st["scale"] - 1) > 1e-3:
        sw, sh = max(1, round(W * st["scale"])), max(1, round(H * st["scale"]))
        big = layer.resize((sw, sh), Image.BILINEAR)
        im = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        if st["scale"] > 1:
            im.alpha_composite(big, (0, 0), ((sw - W) // 2, (sh - H) // 2))
        else:
            im.alpha_composite(big, ((W - sw) // 2, (H - sh) // 2))
    if st["dx"]:
        sh_ = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        dx = round(st["dx"] * k)
        sh_.alpha_composite(im.crop((0, 0, W - dx, H)), (dx, 0))
        im = sh_
    if st["crop_left"] > 0 or st["opacity"] < 0.997:
        a = np.array(im.getchannel("A"), dtype=np.float32) * st["opacity"]
        if st["crop_left"] > 0:
            a[:, :int(round(W * st["crop_left"]))] = 0
        im = im.copy()
        im.putalpha(Image.fromarray(a.astype(np.uint8)))   # HxW uint8 -> L
    return im


# --------------------------------------------------------------------------- audio
def _mono(path: Path) -> np.ndarray:
    from .audio_clean import _read_stereo
    x = _read_stereo(path)
    return x.mean(axis=1) if x.ndim == 2 else x


def build_audio(paths: Paths, spec: dict, out: Path, src_video: Path) -> Path:
    clean = paths.p("06_audio/dialogue/dialogue_clean.wav")
    if clean.exists():
        dia = _mono(clean)
    else:   # no cleanup yet: the camera's own audio
        raw = out.with_name("_camera_audio.wav")
        off = ["-ss", f"{(spec.get('source_in_ms') or 0) / 1000:.3f}"] if spec.get("source_in_ms") else []
        subprocess.run([ffmpeg_exe(), "-y", "-loglevel", "error", *off, "-i", str(src_video), "-map", "0:a:0", "-ac", "1",
                        "-ar", str(SR), "-c:a", "pcm_s16le", str(raw)], check=True)
        dia = _mono(raw)
    n = round(spec["duration_frames"] * SR / seq_fps())
    mix = np.zeros(n, dtype=np.float32)
    fade = int(0.005 * SR)
    for seg in spec["main_segments"]:
        a = round(seg["start_frame"] * SR / seq_fps())
        ln = round((seg["end_frame"] - seg["start_frame"]) * SR / seq_fps())
        s0 = round(seg.get("src_in_ms", seg["start_frame"] * 1000 / seq_fps()) * SR / 1000)
        piece = dia[s0:s0 + ln].copy()
        if len(piece) > 2 * fade:
            piece[:fade] *= np.linspace(0, 1, fade)
            piece[-fade:] *= np.linspace(1, 0, fade)
        mix[a:a + len(piece)] += piece[:max(0, n - a)]
    for c in read_json(paths.p("06_audio/audio-cue-sheet.json"), {"cues": []})["cues"]:
        f = paths.p(c["source_file"])
        if not f.exists():
            continue
        x = _mono(f) * (10 ** (c.get("gain_db", -14) / 20))
        a = round(c["start_frame"] * SR / seq_fps())
        if a < n:
            mix[a:a + len(x)] += x[:n - a]
    mu = spec.get("music") or {}
    if mu.get("status") == "PLACED" and mu.get("file") and (paths.root / mu["file"]).exists():
        # the licensed bed under the dialogue, as placed on A06: from frame 0, recipe level, linear fade-out
        x = _mono(paths.root / mu["file"])[:n] * (10 ** (float(mu.get("level_db", -24)) / 20))
        fo = min(len(x), int(float(mu.get("fade_out_s", 2.0)) * SR))
        if fo:
            x[-fo:] *= np.linspace(1, 0, fo)
        mix[:len(x)] += x
    peak = float(np.max(np.abs(mix))) if len(mix) else 0
    if peak > 0.99:
        mix *= 0.99 / peak
    st = (np.clip(np.repeat(mix[:, None], 2, axis=1), -1, 1) * 32767).astype(np.int16)
    with wave.open(str(out), "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(st.tobytes())
    return out


# --------------------------------------------------------------------------- video
def render(paths: Paths, width: int = 540, label: bool = True) -> dict:
    from .ppro_build import job_data
    t0 = time.time()
    from .stamps import read_compiled
    spec = read_compiled(paths.p("01_analysis/timeline-spec.json"))
    if not spec:
        return {"ok": False, "error": "timeline-spec.json missing - run `reel plan` first"}
    data = job_data(paths)
    if data["_missing"]:
        return {"ok": False, "error": "graphics stills missing - run `reel previews` first", "missing": data["_missing"][:10]}
    from .common import spec_footage
    src = spec_footage(paths, spec)
    SW, SH = frame_size(paths)                  # the sequence frame (profile); the preview keeps its aspect
    W = int(width) // 2 * 2
    H = int(round(W * SH / SW)) // 2 * 2
    k = W / SW
    out_dir = paths.p("08_quality_control/preview")
    out_dir.mkdir(parents=True, exist_ok=True)
    mp4 = out_dir / f"{paths.video_id}_preview.mp4"
    wav = build_audio(paths, spec, out_dir / "_preview_audio.wav", src)
    ff = ffmpeg_exe()
    # decoder: the WHOLE source frame at 24 fps, scaled by the base scale (fit, or the cover scale of a face-centred
    # reframe) but never cropped here, so per-piece zooms can also zoom OUT (source cutaways shown whole)
    pre = read_json(paths.p("00_inputs/preflight.json"), {"files": []})
    mp = next((f for f in pre["files"] if f.get("video") and Path(f["path"]).name == src.name), None)
    dw, dh = (mp["video"]["display_width"], mp["video"]["display_height"]) if mp else (SW, SH)
    s = (spec.get("base_scale_percent") or min(SW / dw, SH / dh) * 100) / 100 * k
    cw_, ch_ = max(2, round(dw * s / 2) * 2), max(2, round(dh * s / 2) * 2)
    box, boy = spec.get("base_offset_x", 0.0), spec.get("base_offset_y", 0.0)
    off = ["-ss", f"{(spec.get('source_in_ms') or 0) / 1000:.3f}"] if spec.get("source_in_ms") else []
    dec = subprocess.Popen([ff, "-loglevel", "error", *off, "-i", str(src), "-an", "-vf", f"fps={fps_arg()},scale={cw_}:{ch_}",
                            "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], stdout=subprocess.PIPE)
    enc = subprocess.Popen([ff, "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}",
                            "-r", fps_arg(), "-i", "-", "-i", str(wav), "-c:v", "libx264", "-preset", "veryfast",
                            "-crf", "23", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "160k", "-shortest",
                            "-movflags", "+faststart", str(mp4)], stdin=subprocess.PIPE)
    fsize = cw_ * ch_ * 3
    src_idx, cur = -1, Image.new("RGB", (cw_, ch_))
    layers = sorted(data["graphics"], key=lambda g: g["track_index"])
    stills = _Stills(W, H)
    from .ppro_build import sharpen_settings
    _sh = sharpen_settings(spec)
    sharp = ImageFilter.UnsharpMask(radius=1.2, percent=int(_sh["amount"] * 4), threshold=2) if _sh else None
    segs = spec["main_segments"]
    si = 0
    brolls = [e for e in spec["events"] if e["template"] == "broll_video"]
    bdec, blast = {}, {}

    def broll_frame(ev):
        """Next frame of a B-roll clip (its own decoder, started at the clip's in-point), cover-cropped to WxH."""
        eid = ev["event_id"]
        if eid not in bdec:
            pp = ev["params"]
            cx, cy = (pp.get("crop_center") or [0.5, 0.5])[:2]
            bdec[eid] = subprocess.Popen(
                [ff, "-loglevel", "error", "-ss", str(float(pp.get("in", 0) or 0)), "-i", str(paths.root / pp["video"]), "-an",
                 "-vf", f"fps={fps_arg()},scale={W}:{H}:force_original_aspect_ratio=increase,"
                        f"crop={W}:{H}:x='(iw-{W})*{float(cx)}':y='(ih-{H})*{float(cy)}'",
                 "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], stdout=subprocess.PIPE)
        buf = bdec[eid].stdout.read(W * H * 3)
        if len(buf) == W * H * 3:
            blast[eid] = Image.frombuffer("RGB", (W, H), buf, "raw", "RGB", 0, 1)
        return blast.get(eid)
    total = spec["duration_frames"]
    tag = None
    if label:
        tag = Image.new("RGBA", (W, 22), (0, 0, 0, 120))
        ImageDraw.Draw(tag).text((6, 5), f"WhyNot Cut preview - {paths.video_id} - not the final render", fill=(255, 255, 255, 220))
    try:
        for f in range(total):
            while si < len(segs) - 1 and f >= segs[si]["end_frame"]:
                si += 1
            seg = segs[si]
            src_ms = seg.get("src_in_ms", seg["start_frame"] * 1000 / seq_fps()) + (f - seg["start_frame"]) * 1000 / seq_fps()
            want = int(round(src_ms * seq_fps() / 1000))
            while src_idx < want:
                buf = dec.stdout.read(fsize)
                if len(buf) < fsize:
                    break                                   # source ended: hold the last frame
                cur = Image.frombuffer("RGB", (cw_, ch_), buf, "raw", "RGB", 0, 1)
                src_idx += 1
            # Premiere: output = (source - centre) * scale + frame centre + offset  ->  invert for the source window
            sc = seg.get("scale_factor", 1.0) or 1.0
            ox = (box + (seg.get("offset_x") or 0.0)) * k
            oy = (boy + (seg.get("offset_y") or 0.0)) * k
            x0, x1 = cw_ / 2 - (W / 2 + ox) / sc, cw_ / 2 + (W / 2 - ox) / sc
            y0, y1 = ch_ / 2 - (H / 2 + oy) / sc, ch_ / 2 + (H / 2 - oy) / sc
            win = seg.get("window") if seg.get("decision_id") != "AUTO_CUTAWAY" else None
            if seg.get("decision_id") == "AUTO_CUTAWAY" or win:
                # source cutaway: the whole card over a blurred cover copy of itself; 4:5 framing: the speaker cropped
                # to the window over the same blurred fill (same as the Premiere build)
                bx, by = box * k, boy * k
                bg = cur.crop((round(cw_ / 2 - (W / 2 + bx)), round(ch_ / 2 - (H / 2 + by)),
                               round(cw_ / 2 + (W / 2 - bx)), round(ch_ / 2 + (H / 2 - by)))).resize((W, H), Image.BILINEAR)
                frame = bg.filter(ImageFilter.GaussianBlur(radius=max(4, round(28 * k))))
                cw2, ch2 = max(2, round(cw_ * sc)), max(2, round(ch_ * sc))
                px, py = round(W / 2 - cw2 / 2 + ox), round(H / 2 - ch2 / 2 + oy)
                img = cur.resize((cw2, ch2), Image.BILINEAR)
                if win:   # only the rows inside the window (the build's Crop)
                    wy0, wy1 = round(win["y"] * k), round((win["y"] + win["h"]) * k)
                    t0, t1 = max(0, wy0 - py), min(ch2, wy1 - py)
                    img = img.crop((0, t0, cw2, max(t0 + 1, t1)))
                    py += t0
                frame.paste(img, (px, py))
            else:
                frame = cur.crop((round(x0), round(y0), round(x1), round(y1))).resize((W, H), Image.BILINEAR)
                if sharp:   # Premiere Sharpen on V1 (approximation: unsharp mask at preview size)
                    frame = frame.filter(sharp)
            for be in brolls:                       # full-screen licensed B-roll replaces the picture (hard cut)
                if be["start_frame"] <= f < be["end_frame"]:
                    bf = broll_frame(be)
                    if bf is not None:
                        frame = bf
            frame = frame.convert("RGBA")
            t = f / seq_fps()
            for g in layers:
                if g["start_s"] <= t < g["end_s"]:
                    im = _apply(stills.get(g["png"]), anim_state(g, t - g["start_s"]), k)
                    if im is not None:
                        frame.alpha_composite(im)
            if tag is not None:
                frame.alpha_composite(tag)
            enc.stdin.write(frame.convert("RGB").tobytes())
    finally:
        enc.stdin.close()
        enc.wait()
        for d_ in [dec, *bdec.values()]:     # stop the decoders and reap them (no zombie ffmpeg, no ResourceWarning)
            d_.stdout.close()
            d_.kill()
            d_.wait()
        wav.unlink(missing_ok=True)
        (out_dir / "_camera_audio.wav").unlink(missing_ok=True)
    ok = enc.returncode == 0 and mp4.exists() and mp4.stat().st_size > 1000
    res = {"ok": ok, "video": str(mp4), "size": f"{W}x{H}", "frames": total, "seconds": round(total / seq_fps(), 2),
           "layers": len(layers), "elapsed_s": round(time.time() - t0, 1), "at": now_iso(),
           "dialogue": "cleaned" if paths.p("06_audio/dialogue/dialogue_clean.wav").exists() else "camera (not cleaned yet)",
           "note": "Proxy preview for review only. The deliverable is the Premiere project; the editor renders the final."}
    write_json(out_dir / "preview-result.json", res)
    log(paths, f"preview video: {mp4} ({res['seconds']} s, {res['elapsed_s']} s to render)")
    return res
