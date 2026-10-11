"""Audio for motion videos: the cleaned dialogue laid on the sequence clock exactly as the TimeMap quantises it (so
animation cue frames and the voice can never drift apart), its per-frame loudness for the voice pulse, synthesised SFX
files, and (for the animatic and a render without audio) a full mix.
"""
from __future__ import annotations

import wave
from pathlib import Path

import numpy as np

SR = 48000


def _read(path: Path) -> np.ndarray:
    with wave.open(str(path)) as w:
        sr, ch, n = w.getframerate(), w.getnchannels(), w.getnframes()
        x = np.frombuffer(w.readframes(n), dtype=np.int16).astype(np.float32) / 32768.0
    x = x.reshape(-1, ch) if ch > 1 else x.reshape(-1, 1)
    if sr != SR:                              # dialogue_clean.wav is 48 kHz; resample anything else linearly
        t = np.arange(int(len(x) * SR / sr)) * sr / SR
        x = np.stack([np.interp(t, np.arange(len(x)), x[:, c]) for c in range(x.shape[1])], axis=1)
    return x


def _write(path: Path, x: np.ndarray) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    x = np.clip(x, -1, 1)
    if x.ndim == 1:
        x = x.reshape(-1, 1)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(x.shape[1])
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes((x * 32767).astype(np.int16).tobytes())
    return path


def sequence_dialogue(paths, tmap) -> Path:
    """06_audio/dialogue/dialogue_motion_seq.wav: each kept piece of dialogue_clean.wav at its TimeMap frame."""
    src = paths.p("06_audio/dialogue/dialogue_clean.wav")
    if not src.exists():
        raise SystemExit("06_audio/dialogue/dialogue_clean.wav missing — run `reel audio-clean` for this motion project")
    x = _read(src)
    fms = tmap.frame_ms
    out = np.zeros((int(round(tmap.total_frames * fms * SR / 1000)), x.shape[1]), dtype=np.float32)
    for p in tmap.pieces:
        a = int(round(p["src_in_ms"] * SR / 1000))
        n = int(round((p["end_frame"] - p["start_frame"]) * fms * SR / 1000))
        o = int(round(p["start_frame"] * fms * SR / 1000))
        seg = x[a:a + n]
        out[o:o + len(seg)] = seg[: max(0, len(out) - o)]
    return _write(paths.p("06_audio/dialogue/dialogue_motion_seq.wav"), out)


def envelope(wav: Path, fps: float, n_frames: int) -> list[float]:
    """RMS per frame, normalised to 0-1 (95th percentile = 1), rounded to 3 decimals."""
    x = _read(Path(wav)).mean(axis=1)
    hop = SR / fps
    vals = []
    for k in range(n_frames):
        seg = x[int(k * hop):int((k + 1) * hop)]
        vals.append(float(np.sqrt(np.mean(seg ** 2))) if len(seg) else 0.0)
    ref = float(np.percentile(vals, 95)) if vals and max(vals) > 0 else 1.0
    return [round(min(1.0, v / ref), 3) if ref > 0 else 0.0 for v in vals]


def sfx_files(kinds: set[str], out_dir: Path) -> dict[str, Path]:
    from .sfx import synth
    out_dir.mkdir(parents=True, exist_ok=True)
    return {k: synth(k, out_dir / f"{k}.wav") for k in sorted(kinds)}


def _decode(path: Path) -> np.ndarray:
    """Any audio file -> float32 (n, 2) at 48 kHz (ffmpeg; SFX are 24-bit, music may be mp3/m4a)."""
    import subprocess
    from .common import ffmpeg_exe
    raw = subprocess.run([ffmpeg_exe(), "-loglevel", "error", "-i", str(path), "-ac", "2", "-ar", str(SR), "-f", "s16le",
                          "-"], capture_output=True).stdout or b""
    return (np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0).reshape(-1, 2)


def mix(plan: dict, root: Path, out: Path) -> Path:
    """Dialogue + music (recipe/decision level, fade-out) + each SFX at its frame, the plan's length, 48 kHz WAV."""
    fps = float(plan["fps"])
    n = int(round(plan["duration_frames"] / fps * SR))
    buf = np.zeros((n, 2), dtype=np.float32)

    def put(x: np.ndarray, at: int, gain: float = 1.0):
        if at >= n or not len(x):
            return
        m = min(len(x), n - at)
        buf[at:at + m] += x[:m] * gain
    a = plan["audio"]
    put(_decode(Path(a["dialogue"])), 0)
    if a.get("music"):
        mus = _decode(Path(a["music"]["file"]))[:n].copy()
        f = int(a["music"].get("fade_out_frames", 0) / fps * SR)
        if f and len(mus) >= n:
            mus[n - f:n] *= np.linspace(1, 0, f, dtype=np.float32)[:, None]
        put(mus, 0, 10 ** (float(a["music"].get("level_db", -24)) / 20))
    for c in a.get("sfx") or []:
        put(_decode(Path(c["file"])), int(round(c["frame"] / fps * SR)), 0.7)
    return _write(Path(out), buf)
