"""Audio for motion videos: the cleaned dialogue laid on the sequence clock exactly as the TimeMap quantises it (so
animation cue frames and the voice can never drift apart), its per-frame loudness for the voice pulse, synthesised SFX
files, and (for the animatic and a render without audio) a full mix.
"""
from __future__ import annotations

import wave
from pathlib import Path

import numpy as np

SR = 48000


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
    """06_audio/dialogue/dialogue_motion_seq_<hash>.wav: each kept piece of dialogue_clean.wav at its TimeMap frame.
    Content-addressed: After Effects keeps imported audio open (Windows), so an unchanged file is never rewritten and
    changed audio gets a new name the next build imports."""
    src = paths.p("06_audio/dialogue/dialogue_clean.wav")
    if not src.exists():
        raise SystemExit("06_audio/dialogue/dialogue_clean.wav missing — run `reel audio-clean` for this motion project")
    x = _decode(src)            # any PCM width (audio-clean writes 24-bit), via ffmpeg
    fms = tmap.frame_ms
    out = np.zeros((int(round(tmap.total_frames * fms * SR / 1000)), x.shape[1]), dtype=np.float32)
    for p in tmap.pieces:
        a = int(round(p["src_in_ms"] * SR / 1000))
        n = int(round((p["end_frame"] - p["start_frame"]) * fms * SR / 1000))
        o = int(round(p["start_frame"] * fms * SR / 1000))
        seg = x[a:a + n]
        out[o:o + len(seg)] = seg[: max(0, len(out) - o)]
    import hashlib
    pcm = (np.clip(out, -1, 1) * 32767).astype(np.int16)
    dst = paths.p(f"06_audio/dialogue/dialogue_motion_seq_{hashlib.sha1(pcm.tobytes()).hexdigest()[:8]}.wav")
    if not dst.exists():
        tmp = dst.with_suffix(".tmp")
        _write(tmp, out)
        tmp.replace(dst)
    _prune_dialogue(paths, keep=dst)
    return dst


def _prune_dialogue(paths, keep: Path) -> None:
    """Removes older sequence dialogues that nothing names any more: not the plan, not the last build job, not any
    project .aep (backups included; After Effects stores footage paths as text, a refused build or a fallback-script
    build leaves no job naming them). Names, not paths: the content hash is the identity, and a project moved from
    another computer keeps its old paths. One that After Effects (or a player) still holds open stays until a later
    run (Windows refuses to delete it)."""
    from pathlib import PureWindowsPath     # splits on / and \ alike
    from .common import read_json
    plan = read_json(paths.p("01_analysis/motion-plan.json"), {}) or {}
    job = (read_json(paths.p("04_after_effects/data/motion-job.json"), {}) or {}).get("plan") or {}
    named = {keep.name} | {PureWindowsPath(p["audio"]["dialogue"]).name for p in (plan, job)
                           if (p.get("audio") or {}).get("dialogue")}
    olds = [f for f in keep.parent.glob("dialogue_motion_seq_*.wav") if f.name not in named]
    if not olds:
        return
    projects = [a.read_bytes() for a in paths.p("04_after_effects/project").rglob("*.aep")]
    for f in olds:
        if any(f.name.encode("utf-8") in b or f.name.encode("utf-16-le") in b for b in projects):
            continue
        try:
            f.unlink()
        except PermissionError:
            pass


def envelope(wav: Path, fps: float, n_frames: int) -> list[float]:
    """RMS per frame, normalised to 0-1 (95th percentile = 1), rounded to 3 decimals."""
    x = _decode(Path(wav)).mean(axis=1)
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
    # an existing file is reused: synthesis is deterministic and After Effects may hold the old file open
    return {k: (out_dir / f"{k}.wav") if (out_dir / f"{k}.wav").exists() else synth(k, out_dir / f"{k}.wav")
            for k in sorted(kinds)}


def _decode(path: Path) -> np.ndarray:
    """Any audio file -> float32 (n, 2) at 48 kHz (ffmpeg; SFX are 24-bit, music may be mp3/m4a)."""
    import subprocess
    from .common import ffmpeg_exe
    from .media_util import ff_timeout
    cmd = [ffmpeg_exe(), "-loglevel", "error", "-i", str(path), "-ac", "2", "-ar", str(SR), "-f", "s16le", "-"]
    raw = subprocess.run(cmd, capture_output=True, timeout=ff_timeout(cmd)).stdout or b""
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
