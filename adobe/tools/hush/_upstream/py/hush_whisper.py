"""Hush — word-timed transcription for filler detection (mlx-whisper, Apple GPU).

usage: hush_whisper.py <audio.wav> <out.json> [language|auto]
Prints one JSON object per line on stdout: {"stage": ...} progress, then {"stage": "done"}.
Writes {"language", "duration", "words": [{"w", "s", "e", "p"}]} to out.json.
"""
import json
import os
import sys
import time

MODEL = os.environ.get("HUSH_WHISPER_MODEL", "mlx-community/whisper-large-v3-turbo")

# Whisper tends to drop disfluencies; a prompt full of them makes it write them down.
PROMPTS = {
    "en": "Umm, uh, so, uhh... I mean, like, hmm, you know, erm, ah.",
    "ar": "اممم، آه، يعني، ااه، امم... طيب، هممم، يعني إيه.",
    None: "Umm, uh, hmm... اممم، آه، يعني، ااه... like, you know, erm.",
}


def load_wav(path):
    """WAV -> mono float32 at 16 kHz, without ffmpeg (Premiere's export is plain PCM)."""
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


def main():
    if len(sys.argv) < 3:
        print(__doc__, file=sys.stderr)
        return 2
    audio, out = sys.argv[1], sys.argv[2]
    lang = sys.argv[3] if len(sys.argv) > 3 and sys.argv[3] not in ("", "auto") else None
    t0 = time.time()
    say(stage="loading")
    import mlx_whisper  # heavy import

    say(stage="transcribing")
    res = mlx_whisper.transcribe(
        load_wav(audio) if audio.lower().endswith(".wav") else audio,
        path_or_hf_repo=MODEL,
        language=lang,
        word_timestamps=True,
        initial_prompt=PROMPTS.get(lang, PROMPTS[None]),
        condition_on_previous_text=False,
        verbose=None,
    )
    words = []
    for seg in res.get("segments", []):
        for w in seg.get("words", []) or []:
            words.append({"w": w["word"].strip(), "s": round(w["start"], 3), "e": round(w["end"], 3),
                          "p": round(w.get("probability", 0.0), 3)})
    with open(out, "w", encoding="utf-8") as f:
        json.dump({"language": res.get("language"), "words": words, "elapsed": round(time.time() - t0, 2)},
                  f, ensure_ascii=False)
    say(stage="done", words=len(words), language=res.get("language"), elapsed=round(time.time() - t0, 2))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:  # report to the panel instead of a bare traceback
        say(stage="error", error=f"{type(e).__name__}: {e}")
        sys.exit(1)
