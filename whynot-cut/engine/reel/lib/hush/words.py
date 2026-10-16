# SPDX-License-Identifier: GPL-3.0-or-later
# © 2026 The Why Not AI (thewhynot.ai)
"""WhyNot Hush: word-timed transcription for filler detection (engine side of the owner's py/hush_whisper.py).

usage (a process):  python -m lib.hush.words <audio.wav> <out.json> [language|auto]     (run from engine/reel)
Prints one JSON object per line on stdout: {"stage": "loading"}, {"stage": "transcribing"}, then {"stage": "done", ...}
(or {"stage": "error", "error": "..."} and exit 1). Writes {"language", "duration", "words": [{"w","s","e","p"}],
"elapsed"} to out.json; `duration` (seconds of audio) is added to the upstream result (PRD 7.2).

The decoding is lib.whisper_backends.make_runner: faster-whisper large-v3-turbo (CUDA fp16, else CPU int8, which the
backend decides) or mlx-whisper on Apple Silicon, with VAD off (a voice-activity filter would drop the very hesitations
this tool looks for). Whisper tends to drop disfluencies, so a prompt full of them (PROMPTS, copied unchanged from the
upstream) is passed per language; auto-detect uses the mixed prompt. Offline: HF_HUB_OFFLINE=1 while the model loads and
decodes (the call restores the variable afterwards). HUSH_WHISPER_MODEL overrides the model: a size name
(large-v3-turbo, large-v3, medium, small), a local model folder, or the upstream's repo id (mapped back to its size).
"""
from __future__ import annotations

import contextlib
import importlib
import json
import os
import sys
import time
import wave
from pathlib import Path

__all__ = ["DEFAULT_MODEL", "PROMPTS", "model_name", "load_wav", "transcribe", "main"]

DEFAULT_MODEL = "large-v3-turbo"

# Whisper tends to drop disfluencies; a prompt full of them makes it write them down.
PROMPTS = {
    "en": "Umm, uh, so, uhh... I mean, like, hmm, you know, erm, ah.",
    "ar": "\u0627\u0645\u0645\u0645\u060c \u0622\u0647\u060c \u064a\u0639\u0646\u064a\u060c \u0627\u0627\u0647\u060c \u0627\u0645\u0645... \u0637\u064a\u0628\u060c \u0647\u0645\u0645\u0645\u060c \u064a\u0639\u0646\u064a \u0625\u064a\u0647.",
    None: "Umm, uh, hmm... \u0627\u0645\u0645\u0645\u060c \u0622\u0647\u060c \u064a\u0639\u0646\u064a\u060c \u0627\u0627\u0647... like, you know, erm.",
}


def model_name(env=None) -> str:
    """The model to load: HUSH_WHISPER_MODEL, else large-v3-turbo. A repo id of the CT2 or MLX list maps to its size."""
    value = str((env if env is not None else os.environ).get("HUSH_WHISPER_MODEL", "") or "").strip()
    if not value:
        return DEFAULT_MODEL
    if "/" in value and not Path(value).is_dir():
        from .. import whisper_backends as wb
        for repos in (wb.MLX_REPOS, wb.CT2_REPOS):
            for size, repo in repos.items():
                if repo == value:
                    return size
    return value


def load_wav(path):
    """WAV -> mono float32 at 16 kHz, without ffmpeg (Premiere's export is plain PCM). The upstream function, unchanged."""
    import wave
    import numpy as np
    with wave.open(path, "rb") as w:
        ch, width, rate, n = w.getnchannels(), w.getsampwidth(), w.getframerate(), w.getnframes()
        raw = w.readframes(n)
    if width == 2:
        a = np.frombuffer(raw, dtype="<i2").astype(np.float32) / 32768.0
    elif width == 3:
        b = np.frombuffer(raw, dtype=np.uint8).reshape(-1, 3).astype(np.int32)
        a = ((b[:, 0] | (b[:, 1] << 8) | (b[:, 2] << 16)) << 8 >> 8).astype(np.float32) / 8388608.0
    elif width == 4:
        a = np.frombuffer(raw, dtype="<i4").astype(np.float32) / 2147483648.0
    else:
        a = (np.frombuffer(raw, dtype=np.uint8).astype(np.float32) - 128.0) / 128.0
    a = a.reshape(-1, ch).mean(axis=1)
    if rate != 16000:
        if rate % 16000 == 0:
            k = rate // 16000
            a = a[: len(a) // k * k].reshape(-1, k).mean(axis=1)
        else:
            t = np.arange(0, len(a) / rate, 1 / 16000.0)
            a = np.interp(t, np.arange(len(a)) / rate, a)
    return a.astype(np.float32)


def say(**kw):
    print(json.dumps(kw, ensure_ascii=False), flush=True)


@contextlib.contextmanager
def _offline():
    before = os.environ.get("HF_HUB_OFFLINE")
    os.environ["HF_HUB_OFFLINE"] = "1"
    try:
        yield
    finally:
        if before is None:
            os.environ.pop("HF_HUB_OFFLINE", None)
        else:
            os.environ["HF_HUB_OFFLINE"] = before


@contextlib.contextmanager
def _default_slot(backend=None):
    """The engine's one-GPU-heavy-job-at-a-time slot (lib.gpu_lock.whisper_slot), when that module is there: the lane
    it yields ("cuda" | "mlx" | "cpu") tells which device to ask Whisper for. Without it the job just runs."""
    try:
        gpu_lock = importlib.import_module(__package__.rsplit(".", 1)[0] + ".gpu_lock")
    except ImportError:
        gpu_lock = None
    if gpu_lock is None:
        yield None
        return
    with gpu_lock.whisper_slot("hush", backend=backend) as lane:
        yield lane


def _default_make_runner(*a, **kw):
    from ..whisper_backends import make_runner
    return make_runner(*a, **kw)


def _language(language):
    return None if language in (None, "", "auto") else language


def _wav_seconds(path):
    try:
        with wave.open(str(path), "rb") as w:
            return round(w.getnframes() / w.getframerate(), 3)
    except (wave.Error, EOFError, ZeroDivisionError, OSError):
        return None


def transcribe(audio, language=None, *, runner=None, make_runner=None, slot=None, say=None, model=None,
               backend=None, clock=time.time) -> dict:
    """Word-timed transcription of `audio` (a path; a .wav is read here, anything else is handed to Whisper as a path).
    `runner` (run(audio, start_ms, language, prompt)) skips building one; `make_runner` and `slot` are the seams the
    tests use (defaults: lib.whisper_backends.make_runner, lib.gpu_lock.whisper_slot). `say(stage=...)` reports progress."""
    say = say or (lambda **kw: None)
    lang = _language(language)
    path = str(audio)
    t0 = clock()
    say(stage="loading")
    with _offline():
        if runner is not None:
            say(stage="transcribing")
            res = _decode(runner, path, lang)
        else:
            with (slot or _default_slot)(backend) as lane:
                device = None if lane in (None, "cuda", "mlx") else "cpu"
                run = (make_runner or _default_make_runner)(model or model_name(), vad=False, backend=backend,
                                                            device=device)
                say(stage="transcribing")
                res = _decode(run, path, lang)
    words = [{"w": w["word"].strip(), "s": round(w["start_ms"] / 1000, 3), "e": round(w["end_ms"] / 1000, 3),
              "p": round(w.get("probability", 0.0), 3)} for w in res.get("words") or []]
    duration = _wav_seconds(path) if path.lower().endswith(".wav") else None
    if duration is None:
        duration = max([w["e"] for w in words] or [0.0])
    return {"language": res.get("language"), "duration": duration, "words": words,
            "elapsed": round(clock() - t0, 2)}


def _decode(run, path, lang):
    audio = load_wav(path) if path.lower().endswith(".wav") else path
    return run(audio, 0, lang, PROMPTS.get(lang, PROMPTS[None]))


def main(argv=None, *, runner=None) -> int:
    argv = sys.argv[1:] if argv is None else list(argv)
    if len(argv) < 2:
        print(__doc__, file=sys.stderr)
        return 2
    audio, out = argv[0], argv[1]
    lang = argv[2] if len(argv) > 2 and argv[2] not in ("", "auto") else None
    try:
        res = transcribe(audio, lang, runner=runner, say=say)
        with open(out, "w", encoding="utf-8", newline="\n") as f:
            json.dump(res, f, ensure_ascii=False)
            f.write("\n")
        say(stage="done", words=len(res["words"]), language=res["language"], elapsed=res["elapsed"])
        return 0
    except Exception as e:  # report to the caller instead of a bare traceback
        say(stage="error", error=f"{type(e).__name__}: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
