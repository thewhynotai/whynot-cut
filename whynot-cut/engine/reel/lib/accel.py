# SPDX-License-Identifier: GPL-3.0-or-later
# © 2026 The Why Not AI (thewhynot.ai)
"""GPU acceleration for the engine's intermediate media (3.0 Phase 4 T4.10, G-GPU).

FFmpeg decodes with NVDEC (`-hwaccel cuda`) and encodes with NVENC (`h264_nvenc`) on an NVIDIA card, and uses
VideoToolbox on macOS, for INTERMEDIATES only: the preview video (the proxy), reel candidates, the motion animatic,
the overlay-scan thumbnails and the shot-analysis frames (and, once the A/B says so, single grabbed frames). Finals stay
libx264 (`motion_render.render`, crf 18): a final gains seconds and risks the deliverable (G10).

  * `detect()` probes `ffmpeg -encoders`, then a real 0.1 s lavfi encode with the GPU encoder: listed but unusable (an
    Optimus laptop, an old driver) is the CPU with the reason in `why`, never an error. The answer is cached in
    `<engine home>/cache/accel.json`, keyed by the ffmpeg path, size and mtime_ns (another ffmpeg build probes again);
    a probe that failed because the card was busy (out of memory, an export holding the encoder) is not cached.
  * `WHYNOT_ACCEL=off` turns it all off (the CPU everywhere): the escape hatch, and what the test suite runs with.
  * Decoded frames go back to system memory (no `-hwaccel_output_format`), so the CPU filters and the rawvideo pipes
    of the call sites stay exactly as they were.
  * `run_ff()` runs an ffmpeg command in a lane and, on a GPU failure, runs it ONCE more on the CPU with a plain
    message: slower, same result.
  * `SITE_LANES` says per call site whether the GPU is used at all (set from the A/B, tools/bench_media.py).

The engine GPU lock (one GPU-heavy job at a time, waiting while Premiere or After Effects exports) is lib/gpu_lock.py.
"""
from __future__ import annotations

import os
import platform
import re
import subprocess
from typing import Callable

ENV = "WHYNOT_ACCEL"
_OFF = {"off", "0", "false", "no", "cpu", "none"}
PROBE_TIMEOUT_S = 30
CACHE_REL = ("cache", "accel.json")

# VideoToolbox has no CRF: -q:v 1-100 (higher is better), mapped from the libx264 CRF the site uses (the A/B may
# change these numbers, never the shape). The three anchors lie on q = 111 - 2 x crf, which maps any other CRF.
VT_Q = {18: 75, 23: 65, 28: 55}

# per call site: "gpu" (use the lane the job's slot gave) or "cpu" (always the CPU), set from the A/B (T4.10 step 8).
# The live A/B on the RTX 4060 laptop (docs/superpowers/evidence/2026-10-17-g-gpu-ab.md): every site was slower on
# the GPU (the engine's short jobs pay the CUDA start-up; 20 CPU threads are fast), so no site reached the >= 15 %
# rule and all stay on the CPU. Re-run tools/bench_media.py on another machine class before changing a value.
SITE_LANES: dict[str, str] = {
    "preview_video": "cpu",
    "reel_candidates": "cpu",
    "animatic": "cpu",
    "thumbs": "cpu",
    "shots": "cpu",
    "grab_frame": "cpu",
}

GPU_FALLBACK_EN = ("The graphics card couldn't do this step (it may be busy or out of memory), so the processor did "
                   "it: slower, same result.")
GPU_FALLBACK_AR = ("كارت الشاشة ماقدرش يعمل الخطوة دي (ممكن يكون مشغول أو ذاكرته مليانة)، فالمعالج عملها: "
                   "أبطأ شوية، والنتيجة هي هي.")

_GPU_ERR = re.compile(
    r"OpenEncodeSessionEx|No (?:NVENC )?capable devices|CUDA_ERROR|out of memory|"
    r"Cannot load (?:nvcuda|libcuda|libnvidia|nvEncodeAPI|nvcuvid)|nvenc API version|"
    # a GPU encoder's own line counts only when it names a GPU cause: ffmpeg 7 also prefixes generic lines with it
    # ("[vost#0:0/h264_nvenc @ ...] Could not open encoder before EOF" when the window held no frames)
    r"\[(?:[^\]\s/]*/)?(?:h264|hevc|av1)_(?:nvenc|videotoolbox|cuvid) @[^\]\n]*\][^\n]*?"
    r"(?:session|out of memory|cuda|nvenc|device|driver|compression|qscale|capab|hwaccel)|"
    r"Failed setup for format (?:cuda|videotoolbox)|hwaccel initiali[sz]ation returned error|"
    r"Device creation failed|VT(?:Compression|Decompression)Session|CUDA (?:error|context)",
    re.IGNORECASE)
# a probe that failed for a reason that passes (VRAM full, every NVENC session taken by an export): never cached
_TRANSIENT = re.compile(r"out of memory|did not finish|busy|incompatible client key", re.IGNORECASE)


def off() -> bool:
    """WHYNOT_ACCEL=off (or 0 / false / no / cpu / none): every step on the CPU."""
    return os.environ.get(ENV, "").strip().lower() in _OFF


def _ffmpeg() -> str | None:
    from .common import ffmpeg_exe
    return ffmpeg_exe()


def _cpu(why: str | None) -> dict:
    return {"kind": "cpu", "h264": "libx264", "hevc": None, "decode": [], "name": None, "why": why}


def _cache_path():
    from .common import current_context
    home = current_context().engine_home
    return home.joinpath(*CACHE_REL)


def _nvidia_smi() -> str | None:
    """nvidia-smi by an absolute path: %SystemRoot%\\System32 on Windows, else the ABSOLUTE PATH folders (never the
    current folder: a planted nvidia-smi there must not run, SEC-1)."""
    if os.name == "nt":
        p = os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "System32", "nvidia-smi.exe")
        if os.path.isfile(p):
            return p
    try:
        from .kalam.platform import find_on_path
        hit = find_on_path("nvidia-smi", os.environ.get("PATH", ""))
    except Exception:  # noqa: BLE001
        hit = None
    return str(hit) if hit else None


def _driver_files(system: str) -> list:
    """The files an NVIDIA driver update replaces (Windows: System32 nvcuda.dll, nvml.dll, nvidia-smi.exe; Linux:
    nvidia-smi); none on a Mac."""
    if system == "Darwin":
        return []
    out = []
    if os.name == "nt":
        sys32 = os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "System32")
        out += [os.path.join(sys32, n) for n in ("nvcuda.dll", "nvml.dll")]
    smi = _nvidia_smi()
    return out + ([smi] if smi else [])


def _driver_stamp(system: str) -> list:
    """[[file name, size, mtime_ns], ...] of the driver's files: a few stat calls, never a process (the key is read
    by every detect(); nvidia-smi takes 1-2 s to start)."""
    stamp = []
    for f in _driver_files(system):
        try:
            st = os.stat(f)
        except (OSError, ValueError):
            continue
        stamp.append([os.path.basename(str(f)).lower(), st.st_size, st.st_mtime_ns])
    return stamp


def _resolve(ff: str) -> str:
    """The ffmpeg path to stat: itself when absolute (the engine's ffmpeg always is), else the PATH walk."""
    if os.path.isabs(ff):
        return ff
    try:
        from .kalam.platform import find_on_path
        hit = find_on_path(ff, os.environ.get("PATH", ""))
    except Exception:  # noqa: BLE001
        hit = None
    return str(hit) if hit else ff


def _cache_key(ff: str, system: str) -> dict | None:
    path = _resolve(ff)
    try:
        st = os.stat(path)
    except (OSError, ValueError):
        return None                         # nothing to key on: probe, do not cache
    return {"ffmpeg": os.path.normcase(os.path.abspath(path)), "size": st.st_size, "mtime_ns": st.st_mtime_ns,
            "system": system, "driver": _driver_stamp(system)}


def forget() -> None:
    """Drop the cached answer (after a GPU step failed: the next job asks the card again)."""
    try:
        _cache_path().unlink(missing_ok=True)
    except Exception:  # noqa: BLE001 — a cache that cannot be removed only means one stale answer
        pass


def _cache_read(key: dict) -> dict | None:
    from .common import read_json
    try:
        doc = read_json(_cache_path(), {}) or {}
    except Exception:  # noqa: BLE001 — a damaged cache is a cache miss
        return None
    res = doc.get("result") if isinstance(doc, dict) and doc.get("key") == key else None
    return dict(res) if isinstance(res, dict) and res.get("kind") in ("cuda", "videotoolbox", "cpu") else None


def _cache_write(key: dict, res: dict) -> None:
    from .common import now_iso, write_json
    try:
        write_json(_cache_path(), {"key": key, "result": res, "at": now_iso()})
    except Exception:  # noqa: BLE001 — a cache that cannot be written only costs the next probe
        pass


def _text(x) -> str:
    if x is None:
        return ""
    return x.decode("utf-8", "replace") if isinstance(x, (bytes, bytearray)) else str(x)


def _last(text: str, n: int = 2) -> str:
    lines = [ln.strip() for ln in _text(text).splitlines() if ln.strip()]
    return " | ".join(lines[-n:])[-300:]


def _listed(text: str, name: str) -> bool:
    return re.search(rf"(?m)^\s*V\S*\s+{re.escape(name)}(?:\s|$)", _text(text)) is not None


def _gpu_name(runner) -> str | None:
    """The card's name, from nvidia-smi on a cache miss only (by its absolute path; an injected test runner may get
    the bare name)."""
    smi = _nvidia_smi() or (None if runner is subprocess.run else "nvidia-smi")
    if not smi:
        return None
    try:
        r = runner([smi, "--query-gpu=name", "--format=csv,noheader"], capture_output=True, text=True,
                   encoding="utf-8", errors="replace", timeout=10)
    except Exception:  # noqa: BLE001 — the name is for the doctor line only
        return None
    lines = [ln.strip() for ln in _text(getattr(r, "stdout", "")).splitlines() if ln.strip()]
    return lines[0] if getattr(r, "returncode", 1) == 0 and lines else None


def _probe(ff: str, system: str, runner) -> tuple[dict, bool]:
    """(the detect result, whether it may be cached)."""
    if system == "Darwin":
        kind, h264, hevc = "videotoolbox", "h264_videotoolbox", "hevc_videotoolbox"
    else:
        kind, h264, hevc = "cuda", "h264_nvenc", "hevc_nvenc"
    kw = dict(capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=PROBE_TIMEOUT_S)
    try:
        enc = runner([ff, "-hide_banner", "-encoders"], **kw)
    except subprocess.TimeoutExpired:
        return _cpu(f"ffmpeg did not finish listing its encoders within {PROBE_TIMEOUT_S} s"), False
    except Exception as e:  # noqa: BLE001 — never an error: the CPU with the reason
        return _cpu(f"ffmpeg could not list its encoders ({type(e).__name__}: {e})"), False
    out = _text(getattr(enc, "stdout", ""))
    if getattr(enc, "returncode", 1) != 0:
        return _cpu(f"ffmpeg could not list its encoders: {_last(getattr(enc, 'stderr', '')) or 'no output'}"), True
    if not _listed(out, h264):
        return _cpu(f"this ffmpeg has no {h264} encoder"), True
    # the engine's real encoder arguments (preset / rc / cq, VideoToolbox -q:v): an Intel Mac without qscale or a
    # driver without preset p4 fails HERE, not in the editor's first preview
    test = [ff, "-hide_banner", "-nostdin", "-loglevel", "error", "-f", "lavfi", "-i",
            "color=c=black:s=256x256:r=30:d=0.1", *h264_args(kind, 23), "-pix_fmt", "yuv420p", "-f", "null", "-"]
    try:
        r = runner(test, **kw)
    except subprocess.TimeoutExpired:
        return _cpu(f"{h264} is listed but its test encode did not finish within {PROBE_TIMEOUT_S} s"), False
    except Exception as e:  # noqa: BLE001
        return _cpu(f"{h264} is listed but its test encode could not run ({type(e).__name__}: {e})"), False
    if getattr(r, "returncode", 1) != 0:
        why = f"{h264} is listed but did not work: {gpu_reason(getattr(r, 'stderr', '')) or 'no error text'}"
        return _cpu(why), not _TRANSIENT.search(why)
    name = (_gpu_name(runner) or "NVIDIA GPU") if kind == "cuda" else "Apple VideoToolbox"
    return {"kind": kind, "h264": h264, "hevc": hevc if _listed(out, hevc) else None, "decode": decode_args(kind),
            "name": name, "why": None}, True


def detect(ff: str | None = None, *, system: str | None = None, runner=subprocess.run, refresh: bool = False) -> dict:
    """What this machine's ffmpeg can use: {"kind": "cuda" | "videotoolbox" | "cpu", "h264": encoder, "hevc": encoder
    or None, "decode": the -hwaccel args, "name": the card (or "Apple VideoToolbox"), "why": why it is the CPU}."""
    if off():
        return _cpu(f"turned off ({ENV}=off)")
    ff = ff or _ffmpeg()
    if not ff:
        return _cpu("no ffmpeg found (run `reel setup`)")
    system = system or platform.system()
    key = _cache_key(str(ff), system)
    if key and not refresh:
        hit = _cache_read(key)
        if hit:
            return hit
    res, cacheable = _probe(str(ff), system, runner)
    if key and cacheable:
        _cache_write(key, res)
    return res


def decode_args(lane: str) -> list[str]:
    """The input options of a decoder in `lane` (before its -i); frames come back to system memory."""
    return ["-hwaccel", lane] if lane in ("cuda", "videotoolbox") else []


def h264_args(lane: str, crf: int) -> list[str]:
    """The H.264 encoder options of `lane` for the quality libx264 gets at `crf`. The CPU lane is exactly the engine's
    pre-3.0 encoder argv."""
    if lane == "cuda":
        return ["-c:v", "h264_nvenc", "-preset", "p4", "-rc", "vbr", "-cq", str(crf), "-b:v", "0"]
    if lane == "videotoolbox":
        q = VT_Q.get(int(crf), max(1, min(100, 111 - 2 * int(crf))))
        return ["-c:v", "h264_videotoolbox", "-q:v", str(q)]
    return ["-c:v", "libx264", "-preset", "veryfast", "-crf", str(crf)]


def site_lane(site: str, lane: str) -> str:
    """`lane` when SITE_LANES lets this call site use the GPU, else "cpu"."""
    return lane if SITE_LANES.get(site) == "gpu" and lane in ("cuda", "videotoolbox") else "cpu"


def is_gpu_failure(stderr) -> bool:
    """ffmpeg's error text says the GPU (NVENC / NVDEC / CUDA / VideoToolbox) failed, not the input or the command."""
    return bool(stderr) and _GPU_ERR.search(_text(stderr)) is not None


def gpu_reason(stderr) -> str:
    """The FIRST line of `stderr` that names the GPU failure (ffmpeg prints the reason first, then generic task /
    thread / muxer lines), for the log and `why`."""
    lines = [ln.strip() for ln in _text(stderr).splitlines() if ln.strip()]
    hit = [ln for ln in lines if _GPU_ERR.search(ln)]
    return (hit[0] if hit else _last(stderr))[-300:]


def note_fallback(log_to, what: str, stderr) -> None:
    """The plain message (English, then Arabic) when a GPU step was redone on the CPU."""
    from .common import log
    target = log_to if getattr(log_to, "video_id", None) else None
    log(target, f"{GPU_FALLBACK_EN} ({what}: {gpu_reason(stderr)})")
    log(target, GPU_FALLBACK_AR)
    forget()


def whisper_device(lane: str) -> str | None:
    """The device transcription asks Whisper for in the Whisper slot's `lane` (gpu_lock.whisper_slot): None (Whisper's
    own choice, as before) for "cuda" / "mlx"; "cpu" when the slot was not had (Premiere / After Effects busy,
    another GPU job), acceleration is off, or Whisper has no GPU here."""
    return None if lane in ("cuda", "mlx") else "cpu"


def run_ff(build: Callable[[str], list], lane: str, *, log_to=None, runner=None) -> tuple[subprocess.CompletedProcess, str]:
    """Run `build(lane)`; on a GPU failure run `build("cpu")` once (with the plain message). Returns the result and
    the lane actually used. `runner(cmd)` defaults to common.run(cmd, check=False) (its ffmpeg timeout)."""
    if runner is None:
        def runner(cmd):
            from . import common
            return common.run(cmd, check=False)
    res = runner(build(lane))
    if lane != "cpu" and getattr(res, "returncode", 0) != 0 and is_gpu_failure(getattr(res, "stderr", "")):
        note_fallback(log_to, "ffmpeg", res.stderr)
        lane = "cpu"
        res = runner(build(lane))
    return res, lane
