# SPDX-License-Identifier: GPL-3.0-or-later
# © 2026 The Why Not AI (thewhynot.ai)
"""The engine GPU lock (3.0 Phase 4 T4.10, G-GPU): one GPU-heavy engine job at a time, machine-wide, and none while
Premiere or After Effects exports or renders.

    with gpu_slot("preview_video", wait_s=120) as lane:     # video: "cuda" | "videotoolbox" | "cpu"
        ...pass `lane` down to the ffmpeg calls...
    with whisper_slot("transcribe") as lane:                # Whisper: "cuda" | "mlx" | "cpu"
        make_runner(..., device=accel.whisper_device(lane))

  * Locks: Windows / Linux have ONE lock, `<engine home>/locks/gpu` (NVENC / NVDEC and CUDA Whisper share the card's
    VRAM). macOS has two: `locks/gpu-media` for VideoToolbox (the media engine) and `locks/gpu` for MLX Whisper (the
    GPU cores): they hardly contend, so a Mac encodes a preview while it transcribes.
  * Video slots follow accel.detect(): a machine whose ffmpeg has no usable GPU (also WHYNOT_ACCEL=off) gets "cpu" at
    once, with no lock and no wait. The Whisper slot follows Whisper's own device (`whisper_lane`: MLX chosen, or
    plat.gpu_info() "cuda"), never ffmpeg's: an NVENC-less ffmpeg must not let two CUDA Whispers run unlocked.
  * A slot waits up to `wait_s` IN TOTAL: first while `host_busy()` says Premiere / After Effects is exporting or
    rendering, then for the OS lock (lib/file_lock.py: released by the operating system when the holder exits or
    crashes, so it is never stale). A wait is never silent: one line when it starts (who has the card, or what the
    host is doing) and a progress line every PROGRESS_S, on stderr and in the job's pipeline.log (`log_to`). A host
    still busy, the lock still held after the wait, or a lock folder that cannot be used (a read-only engine home)
    gives "cpu" with one line naming why: the job runs, slower, and never fails on the lock. Even a wait-0 slot tries
    the lock for MIN_LOCK_WAIT_S, so another process's held() check (it takes the lock for an instant) never pushes a
    free GPU job onto the CPU.
  * While held, `<lock>.json` {pid, what, since} names the holder. It is only for messages; the OS lock decides.
    `held()` is the non-blocking check (T4.15).
  * Waits per caller (WAITS): transcription 600 s, the preview video and reel candidates 120 s, everything else 0
    (the CPU at once). Each verb takes its slot once at job level and passes the lane down; helpers (shot analysis,
    the overlay scan, frame grabs) never take one.

`host_busy()` reads `bridge.heartbeat` of the Premiere and After Effects queues through cep_queue.status(): only a
LIVE heartbeat whose `host_busy` field says "exporting" or "rendering" counts. A missing field (an older bridge),
"idle", "unknown", any other value, an unreadable or a stale heartbeat all mean "proceed" (unknown never blocks).
"""
from __future__ import annotations

import contextlib
import os
import threading
import time
from pathlib import Path

from . import accel, file_lock
from .errors import Guidance

WAITS = {"transcribe": 600.0, "preview_video": 120.0, "reel_candidates": 120.0}
BUSY_VALUES = ("exporting", "rendering")
LOCK_GPU = "gpu"                 # NVENC / NVDEC / CUDA (Windows, Linux); MLX Whisper (macOS)
LOCK_MEDIA = "gpu-media"         # VideoToolbox (macOS)
CPU_NOTE = "this step uses the processor (CPU) this time: slower, same result"
PROGRESS_S = 30.0                # a waiting slot prints a progress line this often
LOCK_STEP_S = 1.0                # the lock is retried in steps this long (so the progress lines come on time)
MIN_LOCK_WAIT_S = 0.2            # every slot tries the lock this long, also with wait_s=0

_guard = threading.Lock()
_depth: dict[str, int] = {}
_mine: dict[str, dict] = {}


def lock_for(kind: str) -> str:
    """The lock a video job of `kind` takes."""
    return LOCK_MEDIA if kind == "videotoolbox" else LOCK_GPU


def _files(name: str = LOCK_GPU) -> tuple[Path, Path]:
    from .common import current_context
    d = current_context().engine_home / "locks"
    return d / name, d / f"{name}.json"


def _note(msg: str, log_to=None) -> None:
    """stderr, and the job's pipeline.log when `log_to` is a clip / episode Paths."""
    from .common import log
    log(log_to if getattr(log_to, "video_id", None) else None, msg)


def host_busy(queues: list[Path] | None = None) -> str | None:
    """"exporting" | "rendering" when a live Premiere / After Effects heartbeat says so, else None."""
    from . import cep_queue
    if queues is None:
        from . import ae_bridge, ppro_bridge
        queues = [ppro_bridge.queue_dir(), ae_bridge.queue_dir()]
    for q in queues:
        try:
            st = cep_queue.status(Path(q))
        except Exception:  # noqa: BLE001 — an unreadable queue is "unknown": proceed
            continue
        v = st.get("host_busy")
        if st.get("alive") and isinstance(v, str) and v in BUSY_VALUES:
            return v
    return None


def _read_info(info: Path) -> dict | None:
    from .common import read_json
    try:
        rec = read_json(info, None)
    except Exception:  # noqa: BLE001
        return None
    return rec if isinstance(rec, dict) else None


def _enter(name: str, info: Path, what: str) -> None:
    from .common import now_iso, write_json
    with _guard:
        _depth[name] = _depth.get(name, 0) + 1
        if _depth[name] > 1:
            return
        _mine[name] = {"pid": os.getpid(), "what": what, "since": now_iso()}
        rec = dict(_mine[name])
    try:
        write_json(info, rec)
    except Exception:  # noqa: BLE001 — the record is for messages only
        pass


def _leave(name: str, info: Path) -> None:
    with _guard:
        _depth[name] = _depth.get(name, 1) - 1
        if _depth[name] > 0:
            return
        _mine.pop(name, None)
    rec = _read_info(info)
    if rec and rec.get("pid") == os.getpid():
        with contextlib.suppress(OSError):
            info.unlink()


def held(name: str | None = None) -> dict | None:
    """The holder's record ({pid, what, since}) while some job holds the GPU lock `name` (default: either lock),
    else None. Never waits."""
    for n in ([name] if name else [LOCK_GPU, LOCK_MEDIA]):
        lock, info = _files(n)
        with _guard:
            if _depth.get(n) and n in _mine:
                return dict(_mine[n])
        try:
            with file_lock.locked(lock, wait_s=0):
                continue
        except file_lock.LockTimeout:
            return _read_info(info) or {"pid": None, "what": None, "since": None}
        except (Guidance, OSError):     # a lock folder that cannot be used: nobody can hold it either
            continue
    return None


def _holder_text(info: Path) -> str:
    rec = _read_info(info) or {}
    who = rec.get("what") or "another job"
    return f"{who}, pid {rec['pid']}" if rec.get("pid") else who


@contextlib.contextmanager
def _slot(what: str, lane: str, name: str, wait_s: float, poll_s: float, clock, sleep, log_to=None):
    t0 = clock()

    def left() -> float:
        return max(0.0, float(wait_s) - (clock() - t0))
    busy = host_busy()
    if busy and left() > 0:
        _note(f"{what}: waiting for Premiere or After Effects to finish {busy} (up to {float(wait_s):.0f} s, then "
              "the processor, CPU)", log_to)
        last = clock()
    while busy and left() > 0:
        sleep(min(float(poll_s), left()))
        busy = host_busy()
        if busy and left() > 0 and clock() - last >= PROGRESS_S:
            _note(f"{what}: still waiting for Premiere or After Effects ({busy}): {clock() - t0:.0f} s of "
                  f"{float(wait_s):.0f} s", log_to)
            last = clock()
    if busy:
        _note(f"{what}: Premiere or After Effects is {busy} (the graphics card, GPU, is in use), so {CPU_NOTE}.",
              log_to)
        yield "cpu"
        return
    lock, info = _files(name)
    stack = contextlib.ExitStack()
    why = None
    # the lock phase runs on the real clock (file_lock waits in real time); its budget is what the host phase left
    budget, r0 = left(), time.monotonic()

    def rleft() -> float:
        return max(0.0, budget - (time.monotonic() - r0))
    announced, last = False, r0
    while True:
        step = MIN_LOCK_WAIT_S if not announced else max(0.0, min(LOCK_STEP_S, PROGRESS_S, rleft()))
        try:
            stack.enter_context(file_lock.locked(lock, wait_s=step))
            break
        except file_lock.LockTimeout:
            if rleft() <= 0:
                why = f"the graphics card (GPU) is busy with another WhyNot Cut job ({_holder_text(info)})"
                break
            now = time.monotonic()
            if not announced:
                _note(f"{what}: waiting for the graphics card (another WhyNot Cut job: {_holder_text(info)}); up to "
                      f"{budget:.0f} s, then the processor (CPU)", log_to)
                announced, last = True, now
            elif now - last >= PROGRESS_S:
                _note(f"{what}: still waiting for the graphics card ({_holder_text(info)}): {now - r0:.0f} s of "
                      f"{budget:.0f} s", log_to)
                last = now
        except (Guidance, OSError) as e:    # a read-only or offline engine home: no lock possible, so no GPU
            msg = getattr(e, "error", None) or getattr(e, "strerror", None) or str(e)
            why = f"the GPU lock in {lock.parent} cannot be used ({msg})"
            break
    if why:
        _note(f"{what}: {why}, so {CPU_NOTE}.", log_to)
        yield "cpu"
        return
    with stack:
        _enter(name, info, what)
        try:
            yield lane
        finally:
            _leave(name, info)


@contextlib.contextmanager
def gpu_slot(what: str, *, wait_s: float = 0.0, poll_s: float = 2.0, clock=time.monotonic, sleep=time.sleep,
             log_to=None):
    """Yields the video lane for job `what`: the GPU's ("cuda" / "videotoolbox") when it is free in time, else "cpu".
    `log_to`: the job's Paths (its waiting lines go to its pipeline.log too)."""
    kind = accel.detect().get("kind", "cpu")
    if kind not in ("cuda", "videotoolbox"):
        yield "cpu"
        return
    with _slot(what, kind, lock_for(kind), wait_s, poll_s, clock, sleep, log_to) as lane:
        yield lane


def whisper_lane(backend: str | None = None) -> str:
    """Where Whisper would run: "mlx" (Apple Silicon, MLX chosen), "cuda" (plat.gpu_info() whisper_device) or
    "cpu" (WHYNOT_ACCEL=off, transcription.json device cpu, or no usable GPU). Never queries CUDA when off."""
    if accel.off():
        return "cpu"
    from .common import load_config
    cfg = load_config("transcription.json")
    if str(cfg.get("device") or "auto").lower() == "cpu":
        return "cpu"
    try:
        from .whisper_backends import choose_backend
        name = choose_backend(cfg, backend)[0]
    except ValueError:
        name = "ct2"
    if name == "mlx":
        return "mlx"
    from . import plat
    try:
        dev = plat.gpu_info().get("whisper_device")
    except Exception:  # noqa: BLE001 — no answer: Whisper decides by itself, unlocked as before
        dev = None
    return "cuda" if dev == "cuda" else "cpu"


@contextlib.contextmanager
def whisper_slot(what: str = "transcribe", *, backend: str | None = None, wait_s: float | None = None,
                 poll_s: float = 2.0, clock=time.monotonic, sleep=time.sleep, log_to=None):
    """Yields the Whisper lane ("cuda" | "mlx" | "cpu") for a transcription; it locks `locks/gpu` (shared with NVENC
    on Windows, ML only on a Mac) when Whisper would use the GPU. Wait: WAITS["transcribe"] by default."""
    lane = whisper_lane(backend)
    if lane == "cpu":
        yield "cpu"
        return
    with _slot(what, lane, LOCK_GPU, WAITS["transcribe"] if wait_s is None else wait_s, poll_s, clock, sleep,
               log_to) as got:
        yield got


@contextlib.contextmanager
def site_slot(site: str, *, wait_s: float | None = None, log_to=None):
    """gpu_slot for a call site of accel.SITE_LANES: "cpu" at once (no lock) when the site stays on the CPU. The wait
    defaults to WAITS (0 for a site not listed there)."""
    if accel.SITE_LANES.get(site) != "gpu":
        yield "cpu"
        return
    with gpu_slot(site, wait_s=WAITS.get(site, 0.0) if wait_s is None else wait_s, log_to=log_to) as lane:
        yield lane
