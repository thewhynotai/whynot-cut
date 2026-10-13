"""Watchable preview of the planned edit, rendered by the engine alone (no Premiere, macOS or Windows).

It mirrors what `ppro-build` gives Premiere: the same footage pieces (pause cuts, jump-cut zoom masks, punch-ins), the
same graphic and caption layers from `ppro_build.job_data()` with the same keyframe presets (bar_sweep, text_pop,
slide, push, card, flash, fade), the cleaned dialogue and the SFX cues. Use it at Gate 1 so the editor can WATCH the edit
before approving, and to review revisions quickly. It is a proxy (540x960 H.264), not the deliverable: the editor still
finishes, mixes and renders in Premiere.
"""
from __future__ import annotations

import os
import subprocess
import tempfile
import threading
import time
import wave
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

from .common import fps_arg, frame_size, seq_fps, Paths, ffmpeg_exe, log, now_iso, read_json, run, write_json

SR = 48000
F = 1 / 24   # animation time unit (the Premiere JSX presets use the same 1/24 s), not the sequence rate


# --------------------------------------------------------------------------- animation (same presets as wnc_ppro_lib.jsx)
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
        run([ffmpeg_exe(), "-y", "-loglevel", "error", *off, "-i", str(src_video), "-map", "0:a:0", "-ac", "1",
             "-ar", str(SR), "-c:a", "pcm_s16le", str(raw)], check=True)        # T2.15 timeout (common.run)
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
PREVIEW_WORKERS = min(2, os.cpu_count() or 1)     # chunks rendered at once: each runs a decoder + an encoder (+ the B-roll
                                                   # decoder of the clip it is in), so <= ~6 ffmpeg (T2.14 review I2)
MIN_CHUNK_FRAMES = 240                             # a chunk is worth its own start-up from about 10 s of timeline
DLL_INIT_FAILED = (3221225794, -1073741502)        # 0xC0000142: Windows could not start the process (spawn load)


class _FFFailed(Exception):
    """An ffmpeg process of a chunk failed: `what` (source decoder / B-roll decoder / encoder), exit code, stderr tail."""

    def __init__(self, what: str, rc, tail: str = ""):
        super().__init__(f"the {what} ffmpeg exited with code {rc}" + (f": {tail}" if tail else ""))
        self.what, self.rc, self.tail = what, rc, tail

    @property
    def spawn(self) -> bool:
        return self.rc in DLL_INIT_FAILED


class _Timeout(Exception):
    pass


def chunk_timeout_s(dur_s: float) -> float:
    """The watchdog of a chunk of dur_s seconds of timeline: T2.15's ffmpeg rule, 10 s + 3 x the duration."""
    from .media_util import FF_TIMEOUT_BASE_S, FF_TIMEOUT_PER_MEDIA_S
    return FF_TIMEOUT_BASE_S + FF_TIMEOUT_PER_MEDIA_S * dur_s


class _Watch:
    """The ffmpeg processes of one chunk: stderr kept in a temp file (for the error), registered with the parallel map
    (Ctrl+C kills them) and a deadline (T2.15's 10 s + 3 x the duration) after which they are all killed."""

    def __init__(self, seconds: float):
        from .parallel import kill_tree
        self.kill_tree, self.procs, self.fired = kill_tree, [], False
        self.timer = threading.Timer(seconds, self._fire)
        self.timer.daemon = True
        self.timer.start()

    def _fire(self):
        self.fired = True
        for p in list(self.procs):
            self.kill_tree(p)

    def spawn(self, cmd, **kw) -> subprocess.Popen:
        from .parallel import track
        err = tempfile.TemporaryFile()
        try:
            p = subprocess.Popen(cmd, stderr=err, **kw)
        except BaseException:
            err.close()
            raise
        p.wnc_err = err
        self.procs.append(p)
        track(p)
        if self.fired:
            self.kill_tree(p)
        return p

    @staticmethod
    def tail(p) -> str:
        try:
            p.wnc_err.seek(0)
            lines = p.wnc_err.read().decode("utf-8", "replace").strip().splitlines()
        except (OSError, ValueError):
            return ""
        return " | ".join(lines[-3:])[-400:]

    def finish(self, p, what: str, read_any: bool):
        """A decoder whose output ended: raise unless it exited 0 having delivered at least one frame."""
        try:
            rc = p.wait(timeout=10)
        except subprocess.TimeoutExpired:
            self.kill_tree(p)
            rc = p.wait()
        if self.fired:
            raise _Timeout()
        if rc != 0:
            raise _FFFailed(what, rc, self.tail(p))
        if not read_any:
            raise _FFFailed(what, rc, self.tail(p) or "no frame decoded")

    def close(self, p):
        """Stop a process and reap it (no zombie ffmpeg, no ResourceWarning)."""
        from .parallel import untrack
        if p.poll() is None:
            p.kill()                     # first: closing the pipe under a running decoder makes it print "Broken pipe"
        for s in (p.stdin, p.stdout):
            if s is not None:
                try:
                    s.close()
                except OSError:
                    pass
        p.wait()
        p.wnc_err.close()
        untrack(p)
        if p in self.procs:
            self.procs.remove(p)

    def stop(self):
        self.timer.cancel()
        for p in list(self.procs):
            self.close(p)


def _unlink(path: Path, tries: int = 10) -> None:
    """Delete a temp file of the render, never raising. On Ctrl+C the main thread gets here right after the chunks'
    ffmpeg were killed (TerminateProcess is asynchronous): a handle still open (WinError 32) must not replace the
    KeyboardInterrupt (T2.14 review 2, M2). Retried briefly; a file that stays locked is left (the next render
    overwrites it)."""
    for i in range(tries):
        try:
            path.unlink(missing_ok=True)
            return
        except OSError:
            if i + 1 < tries:
                time.sleep(0.05)


def chunk_bounds(total: int, workers: int, min_chunk: int = MIN_CHUNK_FRAMES) -> list[int]:
    """Frame boundaries [0, ..., total] of the chunks a timeline of `total` frames is rendered in: at most `workers`,
    none shorter than `min_chunk` frames (a short preview is one chunk: the plain single pass)."""
    n = max(1, min(int(workers), total // max(1, int(min_chunk))))
    return [round(total * i / n) for i in range(n + 1)]


def render(paths: Paths, width: int = 540, label: bool = True, workers: int | None = None,
           min_chunk_frames: int = MIN_CHUNK_FRAMES) -> dict:
    """Render the preview MP4. The timeline is cut into up to `workers` chunks that are rendered at the same time and
    joined with ffmpeg's concat demuxer (same codec parameters, so the join is lossless); `workers=1` is one pass."""
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
    fsize = cw_ * ch_ * 3
    layers = sorted(data["graphics"], key=lambda g: g["track_index"])
    from .ppro_build import sharpen_settings
    _sh = sharpen_settings(spec)
    sharp = ImageFilter.UnsharpMask(radius=1.2, percent=int(_sh["amount"] * 4), threshold=2) if _sh else None
    segs = spec["main_segments"]
    brolls = [e for e in spec["events"] if e["template"] == "broll_video"]
    total = spec["duration_frames"]
    fps_n, fps_s = seq_fps(), fps_arg()               # read once, here: the workers below never ask the Context
    tag = None
    if label:
        tag = Image.new("RGBA", (W, 22), (0, 0, 0, 120))
        ImageDraw.Draw(tag).text((6, 5), f"WhyNot Cut preview - {paths.video_id} - not the final render", fill=(255, 255, 255, 220))
    bounds = chunk_bounds(total, PREVIEW_WORKERS if workers is None else workers, min_chunk_frames)
    nch = len(bounds) - 1

    def seg_index(f):
        si = 0
        while si < len(segs) - 1 and f >= segs[si]["end_frame"]:
            si += 1
        return si

    def source_frame(f, seg):
        """Index of the decoded source frame the timeline frame f shows."""
        src_ms = seg.get("src_in_ms", seg["start_frame"] * 1000 / fps_n) + (f - seg["start_frame"]) * 1000 / fps_n
        return int(round(src_ms * fps_n / 1000))

    threads = ["-threads", str(max(1, (os.cpu_count() or 1) // nch))] if nch > 1 else []   # chunks share the cores

    def chunk_deadline_s(f0, f1):
        """The watchdog of the chunk f0..f1-1. Its decoder decodes the source from the in-point (`-ss`) up to the chunk's
        last frame (the frames before f0 are decoded and dropped by `trim`), which is longer than the chunk's timeline
        span, and longer still when pauses were removed: the deadline counts that source span (T2.14 review 2, M3)."""
        last = max(f0, f1 - 1)
        src_s = (max(0, source_frame(last, segs[seg_index(last)])) + 1) / fps_n
        return chunk_timeout_s(max((f1 - f0) / fps_n, src_s))
    from .parallel import check as cancel_check

    def render_range(f0, f1, enc, watch):
        """Timeline frames f0..f1-1 into the encoder's stdin. A range that does not start at frame 0 has its decoders
        skip the frames before it INSIDE ffmpeg (`trim` after the same `fps` filter, so every frame is the one a single
        pass would have used); the one starting at 0 is the plain sequential pass. A decoder that fails, or delivers no
        frame, raises _FFFailed (never a silent black or speaker-only chunk, T2.14 review I3)."""
        skip = source_frame(f0, segs[seg_index(f0)]) if f0 else 0
        trim = f",trim=start_frame={skip},setpts=PTS-STARTPTS" if skip else ""
        # `-r` after a trim: without it ffmpeg falls back to the SOURCE's rate for the output and duplicates frames
        dec = watch.spawn([ff, "-loglevel", "error", *threads, *off, "-i", str(src), "-an", "-vf",
                           f"fps={fps_s}{trim},scale={cw_}:{ch_}", *(["-r", fps_s] if skip else []),
                           "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], stdout=subprocess.PIPE)
        src_idx, cur = skip - 1, Image.new("RGB", (cw_, ch_))
        dec_read, dec_end = 0, False
        stills = _Stills(W, H, cap=max(12, 48 // nch))
        si = 0
        bdec, blast, bread, bdone = {}, {}, {}, set()

        binto = {}

        def open_broll(ev, into):
            """The decoder of a B-roll clip from its in-point, skipping `into` frames inside ffmpeg (as for the source)."""
            pp = ev["params"]
            cx, cy = (pp.get("crop_center") or [0.5, 0.5])[:2]
            return watch.spawn(
                [ff, "-loglevel", "error", *threads, "-ss", str(float(pp.get("in", 0) or 0)), "-i", str(paths.root / pp["video"]), "-an",
                 "-vf", f"fps={fps_s}" + (f",trim=start_frame={into},setpts=PTS-STARTPTS" if into else "") +
                        f",scale={W}:{H}:force_original_aspect_ratio=increase,"
                        f"crop={W}:{H}:x='(iw-{W})*{float(cx)}':y='(ih-{H})*{float(cy)}'",
                 *(["-r", fps_s] if into else []), "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], stdout=subprocess.PIPE)

        def broll_frame(ev, f):
            """Next frame of a B-roll clip (its own decoder, started at the clip's in-point), cover-cropped to WxH."""
            eid = ev["event_id"]
            what = f"B-roll decoder ({ev['params'].get('video')})"
            if eid in bdone:                                    # the clip's decoder ended: hold its last frame
                return blast.get(eid)
            if eid not in bdec:
                binto[eid] = max(0, f - ev["start_frame"]) if f0 else 0   # a range that starts inside the clip's event
                bdec[eid] = open_broll(ev, binto[eid])
                bread[eid] = 0
            buf = bdec[eid].stdout.read(W * H * 3)
            if len(buf) == W * H * 3:
                blast[eid] = Image.frombuffer("RGB", (W, H), buf, "raw", "RGB", 0, 1)
                bread[eid] += 1
            else:       # the clip ended (exit 0 after a frame: hold it) or its decoder failed (raise)
                bdone.add(eid)
                p = bdec.pop(eid)
                late = bread[eid] == 0 and binto[eid] > 0       # this range starts after the clip's last frame
                try:
                    watch.finish(p, what, bread[eid] > 0 or late)
                finally:
                    watch.close(p)
                if late:
                    # the clip is shorter than its event and ended before this range: the single pass holds the clip's
                    # last frame here, so decode the clip once more from its in-point (no trim: the same command as the
                    # single pass, at most `into` frames) and hold the last frame it delivers (T2.14 review 2, I1)
                    p, n, last = open_broll(ev, 0), 0, None
                    try:
                        while True:
                            buf = p.stdout.read(W * H * 3)
                            if len(buf) < W * H * 3:
                                break
                            last, n = buf, n + 1
                        watch.finish(p, what, n > 0)
                    finally:
                        watch.close(p)
                    blast[eid] = Image.frombuffer("RGB", (W, H), last, "raw", "RGB", 0, 1)
            return blast.get(eid)
        try:
            for f in range(f0, f1):
                cancel_check()                          # Ctrl+C on the parallel map: stop at the next frame
                for be in brolls:                       # a clip whose event is over: its decoder is not needed any more
                    if be["event_id"] in bdec and f >= be["end_frame"]:
                        watch.close(bdec.pop(be["event_id"]))
                        bdone.add(be["event_id"])
                while si < len(segs) - 1 and f >= segs[si]["end_frame"]:
                    si += 1
                seg = segs[si]
                want = source_frame(f, seg)
                while src_idx < want and not dec_end:
                    buf = dec.stdout.read(fsize)
                    if len(buf) < fsize:
                        dec_end = True                  # source ended (exit 0: hold the last frame) or the decoder failed
                        watch.finish(dec, "source decoder", dec_read > 0)
                        break
                    cur = Image.frombuffer("RGB", (cw_, ch_), buf, "raw", "RGB", 0, 1)
                    src_idx += 1
                    dec_read += 1
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
                        bf = broll_frame(be, f)
                        if bf is not None:
                            frame = bf
                frame = frame.convert("RGBA")
                t = f / fps_n
                for g in layers:
                    if g["start_s"] <= t < g["end_s"]:
                        im = _apply(stills.get(g["png"]), anim_state(g, t - g["start_s"]), k)
                        if im is not None:
                            frame.alpha_composite(im)
                if tag is not None:
                    frame.alpha_composite(tag)
                enc.stdin.write(frame.convert("RGB").tobytes())
        finally:
            for p in [dec, *bdec.values()]:     # stop the decoders and reap them (no zombie ffmpeg, no ResourceWarning)
                watch.close(p)

    def encode_once(f0, f1, dest, audio):
        """Render f0..f1 and encode it to `dest` (with the dialogue when `audio`: the single-pass file). Same codec
        parameters for every chunk, which is what makes the concatenation lossless. Raises _FFFailed / _Timeout."""
        cmd = [ff, "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", fps_s, "-i", "-"]
        if audio:
            cmd += ["-i", str(wav)]
        cmd += ["-c:v", "libx264", "-preset", "veryfast", "-crf", "23", "-pix_fmt", "yuv420p", *threads]
        cmd += ["-c:a", "aac", "-b:a", "160k", "-shortest", "-movflags", "+faststart"] if audio else []
        # T2.15 watchdog: 10 s + 3 x the chunk's work (its source span), then every process of the chunk is killed
        watch = _Watch(chunk_deadline_s(f0, f1))
        try:
            enc = watch.spawn(cmd + [str(dest)], stdin=subprocess.PIPE)
            try:
                render_range(f0, f1, enc, watch)
            except OSError:                     # the encoder died under us (broken pipe): its exit code says why
                if enc.poll() is None and not watch.fired:
                    raise
            finally:
                try:
                    enc.stdin.close()
                except OSError:
                    pass
            enc.wait()
            if watch.fired:
                raise _Timeout()
            if enc.returncode != 0:
                raise _FFFailed("encoder", enc.returncode, watch.tail(enc))
        finally:
            watch.stop()

    def encode(f0, f1, dest, audio):
        """encode_once, retried once when Windows could not start one of its ffmpeg (0xC0000142 under process-creation
        load); any other failure is a Guidance (ok: false with what failed and what to do)."""
        from .errors import Guidance
        what = f"timeline frames {f0}-{f1 - 1}"
        for attempt in (1, 2):
            try:
                return encode_once(f0, f1, dest, audio)
            except _FFFailed as e:
                if e.spawn and attempt == 1:
                    log(paths, f"preview video: {e} ({what}); Windows could not start ffmpeg, retrying once")
                    continue
                raise Guidance(f"preview-video could not render {what}: {e}",
                               "Check that the footage (and any B-roll clip) opens: `reel preflight`, then run `reel "
                               "preview-video` again. Exit code 3221225794 (0xC0000142) means Windows could not start "
                               "another process: close other renders or exports and retry.") from e
            except _Timeout:
                raise Guidance(f"preview-video stopped: {what} did not finish within "
                               f"{chunk_deadline_s(f0, f1):.0f} s",
                               "The footage may be on a stalled network share or a sleeping drive: copy it to a local "
                               "disk or wake the drive, then run `reel preview-video` again.") from None
    chunk_files = [out_dir / f"_preview_chunk_{i}.mp4" for i in range(nch)] if nch > 1 else []
    listing = out_dir / "_preview_chunks.txt"
    err = None
    try:
        if nch <= 1:
            encode(0, total, mp4, True)
        else:
            from .parallel import parallel_map
            done = parallel_map(lambda i: encode(bounds[i], bounds[i + 1], chunk_files[i], False), range(nch), nch)
            for good, v in done:
                if not good:
                    raise v
            # the concat demuxer joins the chunks without re-encoding; the dialogue is encoded once over the whole
            listing.write_text("".join(f"file '{c.name}'\n" for c in chunk_files), encoding="utf-8")
            cat = run([ff, "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", listing.name,
                       "-i", str(wav), "-c:v", "copy", "-c:a", "aac", "-b:a", "160k", "-shortest",
                       "-movflags", "+faststart", str(mp4)], check=False, cwd=out_dir)     # T2.15 timeout
            if cat.returncode != 0:
                err = f"joining the chunks failed (ffmpeg exit {cat.returncode}): " + \
                      " | ".join((cat.stderr or "").strip().splitlines()[-3:])[-400:]
    finally:
        for f in (wav, out_dir / "_camera_audio.wav", listing, *chunk_files):
            _unlink(f)
    ok = err is None
    ok = ok and mp4.exists() and mp4.stat().st_size > 1000
    res = {"ok": ok, "video": str(mp4), "size": f"{W}x{H}", "frames": total, "seconds": round(total / seq_fps(), 2),
           "layers": len(layers), "chunks": nch, "elapsed_s": round(time.time() - t0, 1), "at": now_iso(),
           "dialogue": "cleaned" if paths.p("06_audio/dialogue/dialogue_clean.wav").exists() else "camera (not cleaned yet)",
           "note": "Proxy preview for review only. The deliverable is the Premiere project; the editor renders the final."}
    if err:
        res["error"] = err
    write_json(out_dir / "preview-result.json", res)
    log(paths, f"preview video: {mp4} ({res['seconds']} s, {res['elapsed_s']} s to render)")
    return res
