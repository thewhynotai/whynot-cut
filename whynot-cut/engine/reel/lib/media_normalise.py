# SPDX-License-Identifier: GPL-3.0-or-later
# © 2026 The Why Not AI (thewhynot.ai)
"""Intake media normalisation (Phase 4 Task 26, R-4.4): measure what the footage really is, decide what the editor
needs, and write evenly timed / standard-range INTERMEDIATES into output/ only. Originals, finals and client assets are
never touched.

  measure(src)   container rate, the REAL motion rate (near-duplicate frames counted over up to 3 sampled 10 s windows,
                 PyAV decode at 64x36 grey), VFR (frame-time spread), transfer (PQ / HLG / SDR from the colour tags),
                 bit depth, rotation, audio rate; suspicious tags as flags (HDR-tagged 8-bit; 10-bit BT.2020 without a
                 curve). Never raises.
  decide(m)      actions "cfr" (VFR, or a tag/real mismatch: a constant-rate copy at the real rate) and "tonemap"
                 (PQ/HLG -> BT.709 SDR with zscale + tonemap, when this FFmpeg build has both: probed per build), the
                 even-cadence check of a delivery rate (refused with the nearest even choice), plain lines AR / EN.
  conform(...)   the intermediate (x264 crf 16, BT.709-tagged after a tone-map, audio resampled to stay in sync), GPU
                 decode through accel's lane with the CPU fallback, a sidecar (source sha256, filters, reason), reuse
                 when nothing changed, a disk check first, only the given windows (+ 2 s handles) for an episode.
  intake_lines(m, d, lang)  the lines for the intake warnings (T4.8).
The measurement decodes on the CPU (PyAV, tiny frames, seconds of work); the conform decodes on the GPU lane the
calling verb holds (it never takes a slot itself). FFmpeg only by an absolute path (never from the current folder).
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import shutil
import stat
import subprocess
import time
from pathlib import Path

import numpy as np

STANDARD_FPS = (23.976, 24.0, 25.0, 29.97, 30.0, 47.952, 48.0, 50.0, 59.94, 60.0, 100.0, 119.88, 120.0)
SNAP_TOL = 0.01                  # a measured rate within 1 % of a standard one is that rate
MISMATCH = 0.01                  # tag and real rate differ by more than 1 %: a mismatch
DUP_ABS = 0.05                   # every frame difference under this (0-255 mean, 64x36 grey): a still picture
DUP_MAX = 0.5                    # a repeated frame differs by compression noise only: never more than this
DUP_GAP = 4.0                    # repeats and real motion are two groups at least this ratio apart (sorted diffs)
REPEAT_KS = (2.0, 2.5, 3.0, 4.0)  # the only tag / real ratios accepted (2.5 = 3:2 pulldown of 24 into 60)
REPEAT_TOL = 0.12                # share of runs allowed off the pattern (noise)
MIN_REAL_FPS = 10.0              # a measured real rate under this (or under a quarter of the tag) is never used
WINDOWS, WINDOW_S = 3, 10.0
VFR_SPREAD = 0.5                 # (p95 - p5) / median of the frame intervals above this: variable frame rate
HANDLE_S = 2.0
TIMEOUT_MIN_S = 3600.0           # an encode's time limit: at least this, else the span's length times the factor
TIMEOUT_X, TIMEOUT_X_TONEMAP = 4.0, 12.0
BITRATE_MBPS = 20                # the intermediate's size estimate for the disk check
DISK_MARGIN = 5 * 1024 ** 3
TRC = {16: "pq", 18: "hlg"}      # AVColorTransferCharacteristic: SMPTE ST 2084, ARIB STD-B67
BT2020 = 9

_FILTER_CACHE: dict = {}


# --------------------------------------------------------------------------- small helpers
def snap(fps):
    """The standard rate within SNAP_TOL of fps, else fps rounded to 3 decimals; None stays None."""
    if not isinstance(fps, (int, float)) or not math.isfinite(fps) or fps <= 0:
        return None
    best = min(STANDARD_FPS, key=lambda s: abs(s - fps))
    return best if abs(best - fps) / best <= SNAP_TOL else round(float(fps), 3)


def _fmt(fps) -> str:
    return "?" if fps is None else (str(int(fps)) if float(fps).is_integer() else f"{fps:g}")


def _abs_ffmpeg(p) -> str | None:
    """p when it is an absolute path to an existing file, else None (a bare name could run a program planted in the
    current folder: the SEC-1 class)."""
    try:
        return str(p) if p and Path(p).is_absolute() and Path(p).is_file() else None
    except (TypeError, ValueError, OSError):
        return None


def _engine_ffmpeg() -> str | None:
    try:
        from .common import ffmpeg_exe
        return _abs_ffmpeg(ffmpeg_exe())
    except Exception:  # noqa: BLE001
        return None


def filters_available(ff, runner=None) -> dict:
    """{"zscale": bool, "tonemap": bool} of this FFmpeg build (`ffmpeg -filters`), cached per build (path, size,
    modification time). No usable ffmpeg -> both False."""
    ff = _abs_ffmpeg(ff)
    if not ff:
        return {"zscale": False, "tonemap": False}
    st = Path(ff).stat()
    key = (ff, st.st_size, st.st_mtime_ns)
    if key not in _FILTER_CACHE:
        try:
            r = (runner or (lambda c: subprocess.run(c, capture_output=True, text=True, timeout=60)))(
                [ff, "-hide_banner", "-filters"])
            names = {ln.split()[1] for ln in str(r.stdout or "").splitlines() if len(ln.split()) > 2}
        except (OSError, subprocess.SubprocessError, ValueError):
            names = set()
        _FILTER_CACHE[key] = {"zscale": "zscale" in names, "tonemap": "tonemap" in names}
    return dict(_FILTER_CACHE[key])


# --------------------------------------------------------------------------- measure
def _windows(duration):
    if not duration or duration <= WINDOW_S * WINDOWS:
        return [0.0]
    return [duration * f for f in (0.1, 0.5, 0.85)]


def _sample(path: Path, starts, rate):
    """[(times, grey frames)] per window: frame times (s) and 64x36 grey arrays, decoded with PyAV."""
    import av
    out = []
    with av.open(str(path)) as c:
        s = c.streams.video[0]
        s.thread_type = "AUTO"
        for a in starts:
            ts, fr = [], []
            if a > 0:
                c.seek(int(a / s.time_base), stream=s, backward=True)
            for f in c.decode(s):
                if f.pts is None:
                    continue
                t = float(f.pts * s.time_base)
                if t < a - 1e-6:
                    continue
                if t >= a + WINDOW_S:
                    break
                ts.append(t)
                fr.append(f.reformat(width=64, height=36, format="gray").to_ndarray().astype(np.int16))
            out.append((ts, fr))
    return out


def repeats(diffs) -> int:
    """How many of the (ordered) frame-to-frame differences are repeated frames. A tag at k times the real rate repeats
    every frame k times, so the repeats are (1) a low group: the sorted differences split at a jump of DUP_GAP or more
    below DUP_MAX (compression noise vs motion), and (2) REGULAR: their share is 1 - 1/k for a whole k >= 2 and no run
    of repeats is longer than k - 1 (+1 for noise). Motion that stops and starts (a static shot, then movement) is not
    regular: no repeats, so a real rate is never halved by mistake. All under DUP_ABS: a still (all repeats)."""
    seq = np.asarray(diffs, dtype=float)
    if not seq.size:
        return 0
    if seq.max() < DUP_ABS:
        return int(seq.size)
    d = np.sort(seq)
    best, thr = 0.0, None
    for i in range(d.size - 1):
        if d[i] < DUP_MAX:
            ratio = d[i + 1] / max(d[i], 0.005)
            if ratio >= DUP_GAP and ratio > best:
                best, thr = ratio, d[i]
    if thr is None:
        return 0
    dup = seq <= thr
    frac = float(dup.mean())
    if frac >= 1:
        return int(seq.size)
    k = 1 / (1 - frac)
    want = min(REPEAT_KS, key=lambda x: abs(x - k))
    if abs(want - k) > 0.15:
        return 0
    runs, run = [], 0                          # repeats between two new frames
    for x in dup:
        if x:
            run += 1
        else:
            runs.append(run)
            run = 0
    inner = runs[1:]                           # the first run is cut by the window start
    if not inner:
        return 0
    allowed = {1, 2} if want == 2.5 else {int(want) - 1}
    off = sum(1 for r in inner if r not in allowed)
    return int(dup.sum()) if off <= REPEAT_TOL * len(inner) else 0


def _curve_flags(trc: int, prim: int, depth: int) -> tuple:
    """(transfer "pq" | "hlg" | None, flags): an HDR curve on 8-bit pictures is a wrong tag; 10-bit BT.2020 with NO
    curve named (unspecified) may be HDR that cannot be tone-mapped; a named SDR curve is SDR."""
    curve = TRC.get(trc)
    if curve and depth < 10:
        return None, ["tagged_hdr_8bit"]
    if curve:
        return curve, []
    if depth >= 10 and prim == BT2020 and trc in (0, 2):
        return None, ["possibly_hdr_untagged"]
    return None, []


def _rotation(src: Path) -> int:
    """The display rotation (the display matrix side data ffmpeg 7 writes, or the older rotate tag), 0 if none."""
    import re
    ff = _engine_ffmpeg()
    if not ff:
        return 0
    try:
        err = subprocess.run([ff, "-hide_banner", "-nostdin", "-i", str(src)], capture_output=True, text=True,
                             errors="replace", timeout=60).stderr or ""
    except (OSError, subprocess.SubprocessError):
        return 0
    mm = re.search(r"rotation of (-?\d+(?:\.\d+)?) degrees", err) or re.search(r"rotate\s*:\s*(-?\d+)", err)
    return int(round(float(mm.group(1)))) % 360 if mm else 0


def measure(src) -> dict:
    """What the footage is (see the module docstring). Errors are reported in "errors", never raised."""
    src = Path(src)
    m = {"path": str(src), "errors": [], "flags": [], "notes": [], "container_fps": None, "real_fps": None,
         "cfr_fps": None, "vfr": False, "rate_mismatch": False, "duplicate_ratio": None, "transfer": "sdr",
         "bit_depth": 8, "primaries": None, "rotation": 0, "audio_rate": None, "duration_s": None, "width": None,
         "height": None}
    try:
        import av
        with av.open(str(src)) as c:
            s = c.streams.video[0]
            cc = s.codec_context
            avg = float(s.average_rate) if s.average_rate else None
            base = float(s.base_rate) if s.base_rate else None
            m["duration_s"] = round(c.duration / 1e6, 3) if c.duration else None
            pix = cc.pix_fmt or ""
            m["width"], m["height"] = cc.width, cc.height
            m["bit_depth"] = 12 if "12" in pix else 10 if "10" in pix else 8
            trc, prim = int(cc.color_trc or 2), int(cc.color_primaries or 2)
            m["primaries"] = "bt2020" if prim == BT2020 else "bt709" if prim == 1 else None
            if c.streams.audio:
                m["audio_rate"] = c.streams.audio[0].codec_context.sample_rate
        m["container_fps"] = round(base, 3) if base else None
        m["rotation"] = _rotation(src)
        curve, flags = _curve_flags(trc, prim, m["bit_depth"])
        m["transfer"] = curve or "sdr"
        m["flags"] += flags
        windows = _sample(src, _windows(m["duration_s"]), base)
        intervals, frames_n, unique_n, span = [], 0, 0, 0.0
        for ts, fr in windows:
            if len(ts) < 2:
                continue
            d = np.diff(ts)
            intervals += list(d)
            frames_n += len(fr)
            diffs = [float(np.abs(a - b).mean()) for a, b in zip(fr, fr[1:])]
            unique_n += 1 + len(diffs) - repeats(diffs)
            span += ts[-1] - ts[0] + float(np.median(d))
        if intervals:
            iv = np.array(intervals)
            med = float(np.median(iv))
            spread = (float(np.percentile(iv, 95)) - float(np.percentile(iv, 5))) / med if med > 0 else 0.0
            m["vfr"] = bool(spread > VFR_SPREAD or (avg and base and abs(avg - base) / base > 0.005))
            m["duplicate_ratio"] = round(1 - unique_n / frames_n, 3) if frames_n else None
            if unique_n <= 1:
                m["notes"].append("still picture: the motion rate cannot be measured")
            elif span > 0:
                real = snap(unique_n / span)
                floor = max(MIN_REAL_FPS, (base or 0) / 4)
                m["real_fps"] = real if real and real >= floor else (snap(base) if base else None)
        container = base if not m["vfr"] else avg
        if m["real_fps"] and container and not m["vfr"]:
            m["rate_mismatch"] = abs(m["real_fps"] - container) / container > MISMATCH
        if m["vfr"]:                  # the stream's own nominal rate when standard, else the nearest standard rate
            ref = base if base and snap(base) in STANDARD_FPS else (avg or base)
            m["cfr_fps"] = min(STANDARD_FPS, key=lambda x: abs(x - ref)) if ref else None
        else:
            m["cfr_fps"] = m["real_fps"]
    except Exception as e:  # noqa: BLE001  unreadable, not a video, PyAV missing: reported, never raised
        m["errors"].append(f"{type(e).__name__}: {str(e)[:200]}")
    return m


# --------------------------------------------------------------------------- decide
def even_cadence(real, delivery) -> dict:
    """{"ok", "nearest"}: every source frame is shown for the same whole number of delivery frames (or every k-th is
    kept). nearest: the standard delivery rate closest to `delivery` that is even for `real`."""
    def even(r, d):
        if not r or not d:
            return True
        k = d / r if d >= r else r / d
        return abs(k - round(k)) < 1e-3
    ok = even(real, delivery)
    near = None if ok else min((s for s in STANDARD_FPS if even(real, s)), key=lambda s: abs(s - delivery), default=None)
    return {"ok": ok, "nearest": near}


LINES = {
    "vfr": ("This clip has a variable frame rate (typical of Zoom or phone recordings): an evenly timed copy at {fps} "
            "fps is used for editing; the original stays as it is.",
            "الفيديو ده معدل الفريمات فيه متغير (زي تسجيلات زوم أو الموبايل): هنشتغل على نسخة منتظمة {fps} فريم في "
            "الثانية، والأصلي زي ما هو."),
    "mismatch": ("The file says {tag} fps but the picture really moves at {fps} fps: the copy for editing runs at {fps} "
                 "fps.",
                 "الملف مكتوب عليه {tag} فريم في الثانية لكن الحركة الحقيقية {fps}: نسخة الشغل هتبقى {fps} فريم في الثانية."),
    "tonemap": ("This clip is HDR ({curve}): a tone-mapped standard-range (SDR) copy is used for editing; the original "
                "stays as it is.",
                "الفيديو ده HDR ({curve}): هنشتغل على نسخة SDR متظبطة الإضاءة، والأصلي زي ما هو."),
    "no_tonemap": ("This clip is HDR ({curve}), but this FFmpeg cannot tone-map it: the original is used and Premiere's "
                   "own HDR to SDR handling applies.",
                   "الفيديو ده HDR ({curve})، والـ FFmpeg ده مايقدرش يحوله: هنستخدم الأصلي وبريمير هيحول الإضاءة بنفسه."),
    "hdr_8bit": ("The file is marked HDR but has only 8-bit colour: it is treated as standard range (SDR).",
                 "الملف متعلم إنه HDR لكن ألوانه 8 بت بس: هنتعامل معاه على إنه SDR عادي."),
    "hdr_no_cfr": ("This clip is HDR and needs an evenly timed copy, but this FFmpeg cannot tone-map it: the original is "
                   "used as it is; ask for a constant-frame-rate export.",
                   "الفيديو ده HDR ومحتاج نسخة منتظمة، لكن الـ FFmpeg ده مايقدرش يحوله: هنستخدم الأصلي زي ما هو، اطلب نسخة "
                   "بمعدل فريمات ثابت."),
    "skip_ffmpeg": ("No usable FFmpeg was found, so no evenly timed / SDR copy was made: the original is used.",
                    "مفيش FFmpeg صالح، فماعملناش النسخة المظبوطة: هنستخدم الأصلي."),
    "failed": ("Making the evenly timed / SDR copy failed: the original is used.",
               "عمل النسخة المظبوطة فشل: هنستخدم الأصلي."),
    "timeout": ("Making the evenly timed / SDR copy took too long and was stopped: the original is used.",
                "عمل النسخة المظبوطة طوّل زيادة فوقفناه: هنستخدم الأصلي."),
    "in_use": ("The earlier copy of this clip is open (close it in Premiere), so the new one could not replace it: "
               "the original is used for now.",
               "النسخة القديمة من الكليب ده مفتوحة (اقفلها في بريمير)، فالنسخة الجديدة ماقدرتش تحل مكانها: هنستخدم "
               "الأصلي دلوقتي."),
    "not_output": ("The copy can only be written into the client's output folder: none was made, the original is used.",
                   "النسخة دي لازم تتكتب جوه فولدر output بتاع العميل: ماعملناهاش، وهنستخدم الأصلي."),
    "maybe_hdr": ("The file looks like HDR (10-bit, wide colour) but names no brightness curve: it is used as it is; "
                  "check the colours in Premiere.",
                  "الملف شكله HDR (10 بت وألوان واسعة) لكن من غير منحنى إضاءة: هنستخدمه زي ما هو، راجع الألوان في بريمير."),
    "cadence": ("Delivering {fps} fps footage at {d} fps would judder (frames shown unevenly): choose {n} fps instead.",
                "تسليم فيديو {fps} فريم بمعدل {d} هيخلي الحركة متقطعة: اختار {n} فريم في الثانية بدلها."),
}


def _line(key, **kw) -> tuple:
    en, ar = LINES[key]
    return en.format(**kw), ar.format(**kw)


def decide(m: dict, delivery_fps=None, *, ff=None) -> dict:
    """The actions and the plain lines for one measured file (see the module docstring)."""
    d = {"actions": [], "cfr_fps": None, "tonemap": None, "cadence": {"ok": True, "nearest": None},
         "duration_s": m.get("duration_s"), "has_audio": bool(m.get("audio_rate")), "width": m.get("width"),
         "height": m.get("height"), "src_fps": m.get("real_fps") or m.get("container_fps"),
         "lines": {"en": [], "ar": []}}
    if m.get("errors"):
        return d

    def say(key, **kw):
        en, ar = _line(key, **kw)
        d["lines"]["en"].append(en)
        d["lines"]["ar"].append(ar)
    if m.get("vfr") and m.get("cfr_fps"):
        d["actions"].append("cfr")
        d["cfr_fps"] = m["cfr_fps"]
        say("vfr", fps=_fmt(m["cfr_fps"]))
    elif m.get("rate_mismatch") and m.get("real_fps"):
        d["actions"].append("cfr")
        d["cfr_fps"] = m["real_fps"]
        say("mismatch", tag=_fmt(m.get("container_fps")), fps=_fmt(m["real_fps"]))
    curve = m.get("transfer")
    if curve in ("pq", "hlg"):
        name = "PQ" if curve == "pq" else "HLG"
        f = filters_available(ff or _engine_ffmpeg())
        if f["zscale"] and f["tonemap"]:
            d["actions"].append("tonemap")
            d["tonemap"] = curve
            say("tonemap", curve=name)
        elif "cfr" in d["actions"]:        # an 8-bit copy would keep HDR tags on SDR-range pictures: no copy at all
            d["actions"].remove("cfr")
            d["cfr_fps"] = None
            d["lines"] = {"en": [], "ar": []}
            say("hdr_no_cfr")
        else:
            say("no_tonemap", curve=name)
    if "tagged_hdr_8bit" in m.get("flags", []):
        say("hdr_8bit")
    if "possibly_hdr_untagged" in m.get("flags", []):
        say("maybe_hdr")
    real = m.get("real_fps") or m.get("cfr_fps")
    if delivery_fps and real:
        d["cadence"] = even_cadence(real, float(delivery_fps))
        if not d["cadence"]["ok"] and d["cadence"]["nearest"]:
            say("cadence", fps=_fmt(real), d=_fmt(float(delivery_fps)), n=_fmt(d["cadence"]["nearest"]))
    return d


def intake_lines(m: dict, d: dict, language: str = "ar") -> list:
    """The lines for the intake warnings (T4.8), in the editor's language."""
    return list((d or {}).get("lines", {}).get("en" if language == "en" else "ar", []))


# --------------------------------------------------------------------------- conform
def _tonemap_chain(curve: str) -> str:
    """HDR -> BT.709 SDR. Mobius with its linear part up to half of SDR white keeps diffuse white and mid-tones where
    they were graded and compresses only the highlights (measured: the SDR test picture placed on PQ / HLG comes back
    within 6 % of its own mean luma; hable darkened it by 35 %, which a reference built from the same chain hid)."""
    tin = "smpte2084" if curve == "pq" else "arib-std-b67"
    return (f"zscale=tin={tin}:pin=bt2020:min=bt2020nc:t=linear:npl=100,format=gbrpf32le,zscale=p=bt709,"
            f"tonemap=tonemap=mobius:param=0.5:desat=0,zscale=t=bt709:m=bt709:r=tv,format=yuv420p")


def _filters(d: dict) -> list:
    out = []
    if d.get("tonemap"):
        out.append(_tonemap_chain(d["tonemap"]))
    if d.get("cfr_fps"):
        out.append(f"fps={_fmt(d['cfr_fps'])}" if float(d["cfr_fps"]).is_integer() else f"fps={d['cfr_fps']}")
    return out


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def timeout_s(span_s: float, tonemap: bool, px_rate: float | None = None) -> float:
    """The encode's time limit: TIMEOUT_MIN_S, or the span's length times TIMEOUT_X (HDR tone-map: TIMEOUT_X_TONEMAP)
    times the picture's pixel rate against 1080p30 (never under 1x) when that is longer: a 4K60 HDR tone-map on the
    CPU runs far below real time."""
    scale = max(1.0, float(px_rate or 0) / (1920 * 1080 * 30))
    return max(TIMEOUT_MIN_S, float(span_s or 0) * (TIMEOUT_X_TONEMAP if tonemap else TIMEOUT_X) * scale)


def _runner_for(limit: float):
    def run(cmd):
        return subprocess.run(cmd, capture_output=True, timeout=limit)   # on timeout: the child is killed, then raises
    return run


def _drop(p: Path) -> bool:
    """Remove a file, retrying briefly (a just-killed encode or a virus scanner can hold it for a moment). Never
    raises; False when it is still there."""
    for i in range(5):
        try:
            p.unlink(missing_ok=True)
            return True
        except OSError:
            time.sleep(0.2 * (i + 1))
    return False


def _is_link(p) -> bool:
    """A symlink or a Windows junction / name-surrogate reparse point (never followed when writing)."""
    try:
        st = os.lstat(p)
    except OSError:
        return False
    if stat.S_ISLNK(st.st_mode):
        return True
    if getattr(st, "st_file_attributes", 0) & 0x400:                     # FILE_ATTRIBUTE_REPARSE_POINT
        tag = getattr(st, "st_reparse_tag", None)
        return True if tag is None else bool(tag & 0x20000000)            # IO_REPARSE_TAG name surrogate
    return False


def _under(child: str, parent: str) -> str | None:
    """child relative to parent ('' for the same folder), comparing normalised paths; None when outside."""
    c, p = os.path.normcase(child).rstrip("\\/"), os.path.normcase(parent).rstrip("\\/")
    if c == p:
        return ""
    return child[len(parent.rstrip("\\/")) + 1:] if c.startswith(p + os.sep) else None


def _bad_name(part: str) -> bool:
    return (part in ("", ".", "..") or part != part.rstrip(" .") or any(ch in ':*?"<>|' or ord(ch) < 32 for ch in part)
            or part.split(".")[0].upper() in {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(10)),
                                               *(f"LPT{i}" for i in range(10))})


def client_output(out_dir, client_root) -> Path | None:
    """The folder to write into when out_dir is the client's output/ folder or a folder under it, else None.
    `client_root` is the client folder (Paths.root; required: a folder that is merely named "output" proves nothing).
    output/ itself may be a link (a client whose output lives on another drive); below it, no existing folder may be a
    link (nothing is written through one) and no name may be one Windows mangles. `..` is resolved before the check.
    Returns the out_dir under the REAL output folder."""
    if client_root is None:
        return None
    root = os.path.abspath(str(client_root))
    lex = os.path.join(root, "output")
    real = os.path.realpath(lex)
    o = os.path.abspath(str(out_dir))
    rel = _under(o, lex)
    if rel is None:
        rel = _under(o, real)                       # the same folder written through its real (resolved) path
    if rel is None:
        return None
    parts = [x for x in rel.replace("\\", "/").split("/") if x]
    if any(_bad_name(x) for x in parts) or not os.path.isdir(root) or (os.path.lexists(real) and not os.path.isdir(real)):
        return None
    if _is_link(lex) and not os.path.isdir(real):
        return None                                 # a dangling output/ link: never build its target's tree
    if _under(os.path.realpath(root), real) is not None:
        return None                                 # output/ pointing at the client folder (or above it)
    cur = Path(real)
    for x in parts:
        cur = cur / x
        if _is_link(cur) or (cur.exists() and not cur.is_dir()):
            return None
    if any(_under(str(cur), os.path.realpath(os.path.join(root, x))) is not None for x in ("assets", "data")):
        return None                                 # the folder written into is the client's own footage
    return cur


def _source_tag(src: Path, client_root=None) -> str:
    """A short hash naming the source: cam A's and cam B's `C0001.MP4` get different intermediates (the stem alone
    let the second overwrite the first). The path relative to the client folder (case-folded on Windows, '/'
    separators), so a moved client or a new drive letter keeps its intermediates; the resolved path when the source
    lives outside the client. A changed file keeps its name and is redone in place (the sidecar's sha256). Callers
    pass the path under the client folder (a source reached through its real path, past a link inside the client,
    gets the real path's tag)."""
    full = os.path.realpath(str(src))
    rel = None
    if client_root is not None:
        rel = _under(os.path.abspath(str(src)), os.path.abspath(str(client_root))) or \
              _under(full, os.path.realpath(str(client_root)))
    key = os.path.normcase(rel if rel else full).replace("\\", "/")
    return hashlib.sha256(key.encode("utf-8", "surrogatepass")).hexdigest()[:10]


def conform(src, out_dir, decision: dict, *, ff=None, lane: str = "cpu", ranges=None, runner=None,
            disk=shutil.disk_usage, crf: int = 16, client_root=None) -> dict:
    """Write the intermediate(s) for `decision` into out_dir, which must be the client's output/ folder or a folder
    under it (`client_output`, with client_root = the client folder; refused otherwise, before anything is written).
    Named <stem (60 chars at most)>.<source tag>.conform[.r<from>-<to>].mp4. Returns {ok, path, parts, sidecar, lane,
    reused, fps, skipped, reason, lines}. Never raises."""
    src, out_dir = Path(src), Path(out_dir)
    res = {"ok": True, "path": None, "parts": [], "sidecar": None, "lane": lane, "reused": False, "skipped": None,
           "reason": None, "fps": decision.get("cfr_fps"), "lines": {"en": [], "ar": []}}
    try:
        if not decision.get("actions"):
            return res
        target = client_output(out_dir, client_root)
        if target is None:
            res.update(ok=False, skipped="not output", reason=f"{out_dir} is not inside the client's output/ folder")
            res["lines"] = dict(zip(("en", "ar"), ([x] for x in LINES["not_output"])))
            return res
        out_dir = target
        ff = _abs_ffmpeg(ff) if ff else _engine_ffmpeg()
        if not ff:
            res.update(ok=False, skipped="no ffmpeg", reason="no ffmpeg by an absolute path: the original is used")
            res["lines"] = dict(zip(("en", "ar"), ([x] for x in LINES["skip_ffmpeg"])))
            return res
        dur = float(decision.get("duration_s") or 0)
        if ranges:
            spans = []
            for a, b in sorted((max(0.0, float(a) - HANDLE_S), min(dur or float(b) + HANDLE_S, float(b) + HANDLE_S))
                               for a, b in ranges):
                if spans and a <= spans[-1][1]:            # overlapping windows: one part, never encoded twice
                    spans[-1] = (spans[-1][0], max(spans[-1][1], b))
                else:
                    spans.append((a, b))
        else:
            spans = [(0.0, dur)]
        px = (decision.get("width") or 1920) * (decision.get("height") or 1080)
        mbps = max(BITRATE_MBPS, BITRATE_MBPS * px / (1920 * 1080))
        est = sum(b - a for a, b in spans) * mbps * 1e6 / 8
        probe_dir = out_dir if out_dir.exists() else next((p for p in out_dir.parents if p.exists()), out_dir.anchor)
        if disk(str(probe_dir)).free < 2 * est + DISK_MARGIN:
            res.update(ok=False, skipped="disk", reason="not enough free space for the copy: the original is used")
            res["lines"] = {"en": ["Not enough free disk space for the evenly timed / SDR copy: the original is used."],
                            "ar": ["مفيش مساحة كفاية للنسخة المظبوطة: هنستخدم الأصلي."]}
            return res
        filters = _filters(decision)
        source_sha = _sha256(src)
        stem = f"{src.stem[:60]}.{_source_tag(src, client_root)}"
        px_rate = px * float(decision.get("cfr_fps") or decision.get("src_fps") or 30)
        out_dir.mkdir(parents=True, exist_ok=True)
        for a, b in spans:
            tag = "" if not ranges else f".r{int(a * 1000)}-{int(b * 1000)}"
            out = out_dir / f"{stem}.conform{tag}.mp4"
            side = out.with_suffix(".json")
            want = {"source_sha256": source_sha, "filters": filters, "from_s": a, "to_s": b, "crf": crf}
            old = {}
            try:
                old = json.loads(side.read_text(encoding="utf-8")) if side.is_file() else {}
            except ValueError:
                old = {}
            if out.is_file() and all(old.get(k) == v for k, v in want.items()):
                res["reused"] = True
            else:
                tmp = out.with_name(out.stem + ".partial.mp4")
                def build(ln, a=a, b=b, out=tmp):
                    from . import accel
                    cmd = [ff, "-nostdin", "-y", "-v", "error", *accel.decode_args(ln)]
                    if ranges:
                        cmd += ["-ss", f"{a:.3f}", "-t", f"{b - a:.3f}"]
                    cmd += ["-i", str(src), "-map", "0:v:0", "-map", "0:a:0?", "-vf", ",".join(filters) or "null"]
                    if decision.get("cfr_fps"):
                        cmd += ["-fps_mode", "cfr"]
                    cmd += ["-c:v", "libx264", "-preset", "medium", "-crf", str(crf), "-pix_fmt", "yuv420p"]
                    if decision.get("tonemap"):
                        cmd += ["-color_primaries", "bt709", "-color_trc", "bt709", "-colorspace", "bt709"]
                    if decision.get("has_audio"):
                        cmd += ["-af", "aresample=async=1:first_pts=0", "-c:a", "aac", "-b:a", "192k"]
                    return cmd + [str(out)]
                from . import accel
                try:
                    r, used = accel.run_ff(build, lane, runner=runner or _runner_for(
                        timeout_s(b - a, bool(decision.get("tonemap")), px_rate)))
                except subprocess.TimeoutExpired:
                    gone = _drop(tmp)
                    res.update(ok=False, skipped="timeout", reason="the encode took too long and was stopped"
                               + ("" if gone else f"; {tmp.name} could not be removed yet"))
                    res["lines"] = dict(zip(("en", "ar"), ([x] for x in LINES["timeout"])))
                    return res
                except BaseException:
                    _drop(tmp)                                 # no half-written copy is ever left behind
                    raise
                res["lane"] = used
                if getattr(r, "returncode", 1) != 0 or not tmp.is_file():
                    err = r.stderr.decode("utf-8", "replace") if isinstance(r.stderr, bytes) else str(r.stderr or "")
                    res.update(ok=False, reason=f"ffmpeg failed: {err.strip()[-300:]}")
                    res["lines"] = dict(zip(("en", "ar"), ([x] for x in LINES["failed"])))
                    _drop(tmp)
                    return res
                try:
                    tmp.replace(out)                           # only a finished encode gets the final name
                except OSError:                                # the old copy is open (Premiere) or locked
                    gone = _drop(tmp)
                    res.update(ok=False, skipped="in use", reason=f"{out.name} is in use and could not be replaced"
                               + ("" if gone else f"; {tmp.name} could not be removed yet"))
                    res["lines"] = dict(zip(("en", "ar"), ([x] for x in LINES["in_use"])))
                    return res                                 # the old copy keeps its sidecar: still consistent
                side.write_text(json.dumps(dict(want, reason=decision.get("actions"), encoder="libx264",
                                                lane=used), indent=1), encoding="utf-8")
            res["parts"].append({"path": str(out), "sidecar": str(side), "from_s": a, "to_s": b})
        res["path"], res["sidecar"] = res["parts"][0]["path"], res["parts"][0]["sidecar"]
        return res
    except Exception as e:  # noqa: BLE001  G10: the original stays the one used
        res.update(ok=False, reason=f"{type(e).__name__}: {str(e)[:200]}")
        res["lines"] = dict(zip(("en", "ar"), ([x] for x in LINES["failed"])))
        return res


# --------------------------------------------------------------------------- quality check (tests, evidence)
def tonemap_quality(src, out, curve: str, ff=None, size=(160, 90), reference=None) -> dict:
    """{clipped_white, mean_luma_delta}: the share of the intermediate's pixels at full white, and its mean luma against
    a reference: `reference` (an SDR file of the same pictures, independent of our filter chain) when given, else a
    tone-map of the same source frames (zscale + tonemap hable on the CPU)."""
    ff = _abs_ffmpeg(ff) if ff else _engine_ffmpeg()
    w, h = size
    if reference is not None:
        ref_cmd = [ff, "-nostdin", "-v", "error", "-i", str(reference), "-vf", f"scale={w}:{h},format=gray", "-f",
                   "rawvideo", "-"]
    else:
        ref_cmd = [ff, "-nostdin", "-v", "error", "-i", str(src), "-vf",
                   _tonemap_chain(curve) + f",scale={w}:{h},format=gray", "-f", "rawvideo", "-"]
    out_cmd = [ff, "-nostdin", "-v", "error", "-i", str(out), "-vf", f"scale={w}:{h},format=gray", "-f", "rawvideo", "-"]
    ref = subprocess.run(ref_cmd, capture_output=True, timeout=600).stdout or b""
    got = subprocess.run(out_cmd, capture_output=True, timeout=600).stdout or b""
    a = np.frombuffer(ref[:len(ref) // (w * h) * w * h], np.uint8).astype(float)
    b = np.frombuffer(got[:len(got) // (w * h) * w * h], np.uint8).astype(float)
    if not a.size or not b.size:
        return {"clipped_white": None, "mean_luma_delta": None}
    return {"clipped_white": round(float((b >= 254).mean()), 4),
            "mean_luma_delta": round(float((b.mean() - a.mean()) / max(1.0, a.mean())), 4)}
