"""Whisper transcription -> transcript.txt / transcript.json / words.json / subtitles.srt.

Backend: faster-whisper (CTranslate2). Word-level timestamps enabled.
Nothing is translated; the spoken language is kept as-is (Arabic, English or mixed).
"""
from __future__ import annotations

import re
import time
from pathlib import Path

from .common import (ENV_DIR, Paths, ffmpeg_exe, fmt_ts, log, parse_ts, read_json, run,
                     write_json, write_text, load_config)
from . import srt as srtlib

ARABIC = re.compile(r"[؀-ۿݐ-ݿﭐ-﷿ﹰ-﻿]")
LATIN = re.compile(r"[A-Za-z]")


def extract_audio(src: Path, dst: Path, rng: dict | None = None) -> Path:
    from .common import range_input_args
    ff = ffmpeg_exe()
    if not ff:
        raise RuntimeError("ffmpeg not available (run `reel setup`)")
    dst.parent.mkdir(parents=True, exist_ok=True)
    run([ff, "-y", "-hide_banner", "-loglevel", "error", *range_input_args(rng or {}), "-i", str(src),
         "-map", "0:a:0", "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", str(dst)])
    return dst


def whisper_audio(path: Path):
    """16 kHz mono float32 samples for Whisper, decoded here rather than by faster-whisper: its own decoder calls
    PyAV with an argument newer PyAV releases removed (TypeError: open() got an unexpected keyword argument
    'metadata_errors' with faster-whisper 1.2.1 + av 19), so a working Whisper can't depend on the PyAV version."""
    import wave
    import numpy as np
    path = Path(path)
    with wave.open(str(path)) as w:
        ok = w.getnchannels() == 1 and w.getframerate() == 16000 and w.getsampwidth() == 2
        if ok:
            return np.frombuffer(w.readframes(w.getnframes()), dtype="<i2").astype(np.float32) / 32768.0
    ff = ffmpeg_exe()
    if not ff:
        raise RuntimeError("ffmpeg not available (run `reel setup`)")
    tmp = path.with_name(path.stem + ".16k.wav")
    run([ff, "-y", "-hide_banner", "-loglevel", "error", "-i", str(path),
         "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", str(tmp)])
    try:
        return whisper_audio(tmp)
    finally:
        tmp.unlink(missing_ok=True)


def whisper_model(model_size: str, compute_type: str = "int8"):
    """Load faster-whisper on an NVIDIA GPU when one is usable (much faster on Windows/Linux), else on CPU.
    `transcription.json` device: auto | cpu | cuda. Returns (model, device, compute_type)."""
    from faster_whisper import WhisperModel
    cfg = load_config("transcription.json")
    want = (cfg.get("device") or "auto").lower()
    tries = []
    if want in ("auto", "cuda"):
        try:
            from . import plat
            import ctranslate2
            # skip the GPU when cuBLAS can't load: it only fails at the first inference, after loading 3 GB onto it
            if ctranslate2.get_cuda_device_count() > 0 and not plat.cuda_libs_missing():
                tries.append(("cuda", cfg.get("gpu_compute_type", "float16")))
        except Exception:
            pass
    if want != "cuda" or not tries:
        tries.append(("cpu", compute_type))
    last = None
    for dev, ct in tries:
        try:
            return WhisperModel(model_size, device=dev, compute_type=ct, download_root=str(ENV_DIR / "models")), dev, ct
        except Exception as e:  # noqa: BLE001  (e.g. CUDA runtime libraries missing -> CPU)
            last = e
    raise last


def _glossary_terms() -> list[str]:
    g = load_config("medical-glossary.json")
    return [t for grp in g.get("terms", {}).values() for t in grp]


def transcribe(paths: Paths, source_video: Path, model_size: str = "large-v3",
               language: str | None = None, initial_prompt: str | None = None,
               compute_type: str = "int8") -> dict:
    from .common import source_range
    out = paths.p("02_transcription")
    rng = source_range(paths)
    wav = extract_audio(source_video, out / "dialogue_16k_mono.wav", rng)
    if initial_prompt is None:
        initial_prompt = load_config("transcription.json").get("initial_prompt")
        vv = video_vocabulary(paths)
        if vv:   # names / terms of THIS video (e.g. from the client's reels plan), after the client-wide hint
            initial_prompt = ((initial_prompt or "").rstrip(" .،,") + "، " + "، ".join(vv) + ".").lstrip("، ")

    log(paths, f"Loading Whisper model {model_size}")
    t0 = time.time()
    model, device, compute_type = whisper_model(model_size, compute_type)
    log(paths, f"Whisper running on {device} ({compute_type})")
    try:
        segs, words, info = _run_whisper(model, wav, language, initial_prompt)
    except Exception as e:  # noqa: BLE001  (GPU libraries can fail only at the first inference)
        if device != "cuda":
            raise
        log(paths, f"GPU transcription failed ({type(e).__name__}: {e}); retrying on CPU"
                   + (" - run `reel gpu-enable` (with the editor's OK, ~550 MB) for GPU speed" if "cublas" in str(e).lower() else ""))
        from faster_whisper import WhisperModel
        model, device, compute_type = WhisperModel(model_size, device="cpu", compute_type="int8",
                                                   download_root=str(ENV_DIR / "models")), "cpu", "int8"
        segs, words, info = _run_whisper(model, wav, language, initial_prompt)
    elapsed = round(time.time() - t0, 1)
    log(paths, f"Transcribed {len(segs)} segments / {len(words)} words in {elapsed}s; "
               f"lang={info.language} p={info.language_probability:.2f}")

    meta = {"source_video": str(source_video), "source_range": rng or None, "audio": str(wav), "backend": "faster-whisper",
            "model": model_size, "compute_type": compute_type, "device": device,
            "language": info.language, "language_probability": round(info.language_probability, 3),
            "duration_ms": int(round(info.duration * 1000)), "initial_prompt": initial_prompt,
            "elapsed_s": elapsed, "translated": False}
    res = finalize(paths, meta, segs, words)
    out = paths.p("02_transcription")
    for name in ("transcript", "words"):   # a NEW machine transcript replaces the old machine originals
        (out / f"{name}.machine.json").write_bytes((out / f"{name}.json").read_bytes())
    return res


def _run_whisper(model, wav: Path, language, initial_prompt):
    segments, info = model.transcribe(
        whisper_audio(wav), language=language, task="transcribe", beam_size=5,
        word_timestamps=True, vad_filter=False, condition_on_previous_text=False,
        initial_prompt=initial_prompt, temperature=[0.0, 0.2, 0.4],
    )
    segs, words = [], []
    for s in segments:
        seg = {
            "id": len(segs) + 1,
            "start_ms": int(round(s.start * 1000)), "end_ms": int(round(s.end * 1000)),
            "text": s.text.strip(),
            "avg_logprob": round(s.avg_logprob, 3), "no_speech_prob": round(s.no_speech_prob, 3),
            "compression_ratio": round(s.compression_ratio, 3), "words": [],
        }
        for w in (s.words or []):
            wd = {"id": len(words) + 1, "segment_id": seg["id"], "word": w.word.strip(),
                  "start_ms": int(round(w.start * 1000)), "end_ms": int(round(w.end * 1000)),
                  "probability": round(w.probability, 3)}
            words.append(wd)
            seg["words"].append(wd["id"])
        segs.append(seg)
    return segs, words, info


def caption_cues(words: list) -> tuple[list, list]:
    """(subtitles, short captions) built from word timing with the client's subtitle style."""
    cfg = load_config("subtitle-style.json")
    cues = srtlib.build_cues_from_words(words, max_chars=cfg.get("max_chars_per_line", 32),
                                        max_lines=cfg.get("max_lines", 2),
                                        max_dur_ms=cfg.get("max_cue_ms", 4000),
                                        min_dur_ms=cfg.get("min_cue_ms", 700))
    short = srtlib.build_cues_from_words(words, max_chars=cfg.get("short_max_chars", 18),
                                         max_lines=1, max_dur_ms=1800, min_dur_ms=300,
                                         max_words=cfg.get("short_max_words", 4))
    return cues, short


def video_vocabulary(paths: Paths) -> list:
    """Names and terms of this one video (00_inputs/vocabulary.txt, one per line or comma-separated), written by the
    lead from the client's plan before transcribing. Client-wide names stay in the profile's transcription.json."""
    f = paths.p("00_inputs/vocabulary.txt")
    if not f.exists():
        return []
    return [t.strip() for t in re.split(r"[\n,،;]+", f.read_text(encoding="utf-8")) if t.strip() and not t.startswith("#")]


# Phrases Whisper invents on silence, music or noise (end screens of the videos it was trained on)
HALLUCINATIONS = ["اشتركوا في القناة", "اشتركوا في القناه", "لا تنسوا الاشتراك في القناة", "شكرا على المشاهدة",
                  "شكرا لكم على المشاهدة", "ترجمة نانسي قنقر", "ترجمة نانسي", "Thanks for watching",
                  "Thank you for watching", "Subtitles by the Amara.org community", "Please subscribe"]


def drop_hallucinations(segs: list, words: list) -> tuple[list, list, list]:
    """Remove segments that are a known Whisper hallucination AND cannot be speech (no-speech probability >= 0.5 or
    more than 6 words a second). Seen on a real reel: «اشتركوا في القناة» in 0.32 s at the out-point, no_speech 0.93."""
    from .plan import norm
    known = {norm(h) for h in HALLUCINATIONS}
    drop = []
    for s in segs:
        dur = max(1, s["end_ms"] - s["start_ms"]) / 1000
        n = len(s["text"].split())
        if norm(s["text"]) in known and (s.get("no_speech_prob", 0) >= 0.5 or n / dur > 6):
            drop.append(s)
    if not drop:
        return segs, words, []
    gone = {wid for s in drop for wid in s.get("words", [])}
    return ([s for s in segs if s not in drop], [w for w in words if w["id"] not in gone],
            [{"text": s["text"], "start_ms": s["start_ms"], "end_ms": s["end_ms"],
              "no_speech_prob": s.get("no_speech_prob")} for s in drop])


def finalize(paths: Paths, meta: dict, segs: list, words: list) -> dict:
    out = paths.p("02_transcription")
    cfg = load_config("subtitle-style.json")
    segs, words, dropped = drop_hallucinations(segs, words)
    if dropped:
        meta["dropped_hallucinations"] = (meta.get("dropped_hallucinations") or []) + dropped
    meta["video_vocabulary"] = video_vocabulary(paths) or meta.get("video_vocabulary")
    meta["scripts"] = _script_mix(" ".join(s["text"] for s in segs))
    write_json(out / "transcript.json", {"meta": meta, "segments": segs})
    write_json(out / "words.json", {"meta": meta, "words": words})
    write_text(out / "transcript.txt", "\n".join(
        f"[{fmt_ts(s['start_ms'], '.')} --> {fmt_ts(s['end_ms'], '.')}] {s['text']}" for s in segs) + "\n")

    cues, short = caption_cues(words)
    srtlib.write_srt(out / "subtitles.srt", cues)          # 1) readable 1-2 line subtitles
    srtlib.write_srt(out / "captions-short.srt", short)    # 2) short social captions (1-4 words)
    try:
        quotes = document_quotes(paths, words)
    except Exception as e:  # noqa: BLE001  (a cross-check aid; never blocks the transcript)
        quotes = [{"error": f"{type(e).__name__}: {e}"}]
    review = subtitle_review(meta, segs, words, quotes)
    write_text(out / "subtitle-review.md", review)
    return {"meta": meta, "segments": len(segs), "words": len(words), "cues": len(cues),
            "short_cues": len(short)}


def _script_mix(text: str) -> dict:
    a, l = len(ARABIC.findall(text)), len(LATIN.findall(text))
    tot = max(1, a + l)
    return {"arabic_ratio": round(a / tot, 3), "latin_ratio": round(l / tot, 3),
            "mixed": a > 0 and l > 0, "rtl_primary": a >= l}


GLOSSARY_LABEL = {"medical": "Medical terminology", "religious": "Religious wording (verses, hadith, rulings)",
                  "general": "Glossary terms"}


def _stem(t: str) -> str:
    for pre in ("وال", "بال", "فال", "لل", "ال", "و", "ب", "ف"):
        if t.startswith(pre) and len(t) - len(pre) >= 3:
            return t[len(pre):]
    return t


def glossary_hits(words: list, terms: list) -> list:
    """Glossary terms (single words or phrases) found in the words, compared after Arabic normalisation
    (آمنوا = امنوا, ة = ه, no diacritics), so spelling variants of the same word still count."""
    from .plan import norm, _AR_DIAC

    def light(x):   # short terms keep hamza / ta marbuta: آية (verse) must not match Egyptian ايه ("what")
        return re.sub(r"[^\w\s]", " ", _AR_DIAC.sub("", x or "").replace("ـ", "")).strip()
    toks = [(norm(w["word"]), w) for w in words]
    toks = [(t, w) for t, w in toks if t]
    hits = []
    for term in terms:
        parts = norm(term).split()
        if not parts:
            continue
        if len(parts) == 1 and len(parts[0]) <= 3:
            exact = light(term)
            hits += [{"term": term, "word_ids": [w["id"]], "start_ms": w["start_ms"], "heard": w["word"]}
                     for w in words if light(w["word"]) == exact]
            continue
        n = len(parts)
        for i in range(len(toks) - n + 1):
            win = [toks[i + k][0] for k in range(n)]
            if all(p == t or _stem(t) == _stem(p) or (len(p) >= 4 and p in t) for p, t in zip(parts, win)):
                hits.append({"term": term, "word_ids": [toks[i + k][1]["id"] for k in range(n)],
                             "start_ms": toks[i][1]["start_ms"],
                             "heard": " ".join(toks[i + k][1]["word"] for k in range(n))})
    return sorted(hits, key=lambda h: h["start_ms"])


def vocabulary_misses(words: list, prompt: str | None, min_ratio: float = 0.65) -> list:
    """Words of the profile's spelling hint (names, programme title, key terms) that never appear verbatim in the
    transcript, each with the closest word Whisper did write: e.g. hint `نادال`, heard `نضال`. Whisper often keeps
    its own spelling of a name despite the hint, at high confidence, so these are candidates to check by ear."""
    import difflib
    from .plan import norm
    heard = [(norm(w["word"]), w) for w in words]
    stems = {_stem(t) for t, _ in heard}
    out = []
    for raw in dict.fromkeys(re.split(r"[\s،,.؛;:!؟?]+", prompt or "")):
        v = norm(raw)
        if len(v) < 4 or LATIN.search(v) or any(_stem(v) in t for t in stems):   # heard, or a word form of it
            continue
        best = None
        for t, w in heard:
            if len(t) < 3:
                continue
            r = difflib.SequenceMatcher(None, _stem(t), _stem(v)).ratio()
            if r >= min_ratio and (best is None or r > best[0]):
                best = (r, w)
        if best:
            out.append({"expected": raw, "heard": best[1]["word"], "word_id": best[1]["id"],
                        "start_ms": best[1]["start_ms"], "similarity": round(best[0], 2)})
    return sorted(out, key=lambda m: -m["similarity"])


QUOTE_RE = re.compile(r'«([^»]{6,200})»|"([^"\n]{6,200})"|“([^”]{6,200})”')


def document_quotes(paths: Paths, words: list, min_ratio: float = 0.6) -> list:
    """Speaker quotes in the client's documents (a reels plan, a brief: «...», "...", “...”) located in this transcript.
    A person wrote those lines down after listening, so where they differ from Whisper they are strong evidence for a
    correction (e.g. plan «شوف هي الفكرة في إيمانهم», Whisper «شوف هي الفكرة في آمانه»). Exact matches confirm."""
    import difflib
    from .discover import read_document
    from .plan import norm
    inv = read_json(paths.output / "discovery/input-inventory.json", {"files": []})
    docs = [f for f in inv["files"] if f["role"] in ("editing_reference_doc", "client_brief")]
    toks = [(norm(w["word"]), w) for w in words]
    toks = [(t, w) for t, w in toks if t]
    seq = [t for t, _ in toks]
    out, seen = [], set()
    for d in docs:
        try:
            text = read_document(Path(d["path"]))
        except Exception:  # noqa: BLE001
            continue
        for m in QUOTE_RE.finditer(text):
            q = next(g for g in m.groups() if g)
            qt = norm(q).split()
            if len(qt) < 3 or q in seen or not ARABIC.search(q) and not LATIN.search(q):
                continue
            seen.add(q)
            # the quote's own length first, so a differing word stays inside the window and shows; one word more or
            # less only when no same-length window matches (the writer dropped or added a word)
            r, i, n, aligned = 0.0, 0, 0, -1
            for lens in ([len(qt)], [len(qt) - 1, len(qt) + 1]):
                for n_ in lens:
                    for i_ in range(0, max(0, len(seq) - n_) + 1) if n_ >= 2 else []:
                        win = seq[i_:i_ + n_]
                        r_ = difflib.SequenceMatcher(None, qt, win).ratio()
                        al = sum(a == b for a, b in zip(qt, win))     # ties: the window whose words line up
                        if (r_, al) > (r, aligned):
                            r, i, n, aligned = r_, i_, n_, al
                if r >= min_ratio:
                    break
            if r < min_ratio:
                continue
            ws = [w for _, w in toks[i:i + n]]
            out.append({"doc": d["rel"], "quote": q, "transcript": " ".join(w["word"] for w in ws),
                        "word_ids": [ws[0]["id"], ws[-1]["id"]], "start_ms": ws[0]["start_ms"],
                        "match": round(r, 2), "exact": r >= 0.999})
    return sorted(out, key=lambda x: x["start_ms"])


def subtitle_review(meta: dict, segs: list, words: list, quotes: list | None = None) -> str:
    from .common import content_domain
    thr = load_config("transcription.json").get("low_confidence_threshold", 0.5)
    domain = content_domain()
    low = [w for w in words if w["probability"] < thr]
    latin = [w for w in words if LATIN.search(w["word"])]
    hits = glossary_hits(words, _glossary_terms())
    # this video's own names at the normal threshold; the client-wide hint (show title, names that may not occur in
    # this video) only for close matches, or every reel lists noise (seen: «حلمي» vs «حمرى», «نادال» vs «نازل»)
    vv = meta.get("video_vocabulary") or []
    misses = vocabulary_misses(words, "، ".join(vv)) if vv else []
    seen_m = {m["expected"] for m in misses}
    client_hint = load_config("transcription.json").get("initial_prompt") or ""
    misses += [m for m in vocabulary_misses(words, client_hint, min_ratio=0.8) if m["expected"] not in seen_m]
    risky = [s for s in segs if s["avg_logprob"] < -0.8 or s["compression_ratio"] > 2.4
             or s["no_speech_prob"] > 0.6]
    L = [f"# Subtitle Review — {Path(meta['source_video']).name}", "",
         f"- Backend: {meta['backend']} / model `{meta['model']}` on {meta.get('device', 'cpu')}",
         f"- Detected language: **{meta['language']}** (p={meta['language_probability']})",
         f"- Script mix: {meta['scripts']}",
         f"- Duration: {fmt_ts(meta['duration_ms'], '.')} — {len(segs)} segments, {len(words)} words",
         f"- Translation: none (original speech preserved)", "",
         "**Status: MACHINE TRANSCRIPT — requires human verification before captions are final.**", "",
         f"## Low-confidence words (p < {thr}) — {len(low)}", ""]
    L += [f"- `{fmt_ts(w['start_ms'], '.')}` **{w['word']}** (p={w['probability']})" for w in low] or ["- none"]
    dh = meta.get("dropped_hallucinations") or []
    if dh:
        L += ["", f"## Dropped Whisper hallucinations — {len(dh)}", "",
              "Known phrases Whisper invents on silence/music, at a speed or no-speech level no person speaks at. "
              "If the speaker really said it, add it back by ear.", ""]
        L += [f"- `{fmt_ts(h['start_ms'], '.')}` «{h['text']}» (no-speech {h.get('no_speech_prob')})" for h in dh]
    L += ["", f"## Profile vocabulary not heard verbatim — {len(misses)}", "",
          "Names and terms from the profile's spelling hint that Whisper wrote differently. Confidence is often high "
          "on these, so check each by ear; correct only if the speaker said the expected word.", ""]
    L += [f"- `{fmt_ts(m['start_ms'], '.')}` expected **{m['expected']}**, heard **{m['heard']}** "
          f"(word {m['word_id']}, similarity {m['similarity']})" for m in misses] or ["- none"]
    quotes = [q for q in (quotes or []) if "error" not in q]
    diff_q = [q for q in quotes if not q["exact"]]
    L += ["", f"## Quotes in the client's documents — {len(quotes)} found, {len(diff_q)} differ", "",
          "Lines a person wrote down from this talk (reels plan, brief). Where one differs from Whisper it is evidence "
          "for a correction: check the words that differ (and by ear when it matters).", ""]
    L += [f"- `{fmt_ts(q['start_ms'], '.')}` {'✓' if q['exact'] else '≠'} {q['doc']}: «{q['quote']}»"
          + ("" if q["exact"] else f" — transcript «{q['transcript']}» (words {q['word_ids'][0]}-{q['word_ids'][1]}, "
                                   f"match {q['match']})") for q in quotes] or ["- none"]
    L += ["", f"## Latin-script / English terms inside speech — {len(latin)}", "",
          "Check spelling and that mixed-direction rendering is correct in captions.", ""]
    L += [f"- `{fmt_ts(w['start_ms'], '.')}` {w['word']} (p={w['probability']})" for w in latin] or ["- none"]
    L += ["", f"## {GLOSSARY_LABEL[domain]} — {len(hits)}", ""]
    if domain == "religious" and hits:
        L += ["Spoken verses are approximations: never copy a verse from the transcript onto a graphic (exact Mushaf "
              "wording and reference only, with the content owner's approval).", ""]
    L += [f"- `{fmt_ts(h['start_ms'], '.')}` {h['heard']} (term: {h['term']}; words {h['word_ids'][0]}"
          f"{'-' + str(h['word_ids'][-1]) if len(h['word_ids']) > 1 else ''})" for h in hits] or ["- none detected by glossary"]
    L += ["", f"## Segments with weak decoding statistics — {len(risky)}", ""]
    L += [f"- #{s['id']} `{fmt_ts(s['start_ms'], '.')}` logprob={s['avg_logprob']} "
          f"cr={s['compression_ratio']} nospeech={s['no_speech_prob']}: {s['text']}" for s in risky] or ["- none"]
    L += ["", "## How to correct", "",
          "Add word-level fixes to `02_transcription/transcript-corrections.json`",
          '(`{"corrections":[{"word_id":N,"from":"…","to":"…","reason":"…","confidence":"high|medium"}]}`;',
          '`"to": ""` merges the word into the previous one) and run `reel transcript-correct`.',
          "SRTs, words.json and transcript.json are rebuilt; machine originals are kept as *.machine.json.",
          "Timings are never changed to 'fit' a correction. Then `reel transcript-verify` once checked by ear."]
    return "\n".join(L) + "\n"


def verify_existing_srt(srt_path: Path, media_duration_ms: int) -> dict:
    """Decide whether a supplied SRT plausibly belongs to this footage."""
    cues = srtlib.read_srt(srt_path)
    if not cues:
        return {"usable": False, "reason": "empty or unparsable"}
    last = cues[-1]["end_ms"]
    first = cues[0]["start_ms"]
    issues = []
    if last > media_duration_ms + 1000:
        issues.append(f"last cue {fmt_ts(last)} beyond media end {fmt_ts(media_duration_ms)}")
    if last < media_duration_ms * 0.6:
        issues.append("cues cover < 60% of media duration")
    overl = sum(1 for a, b in zip(cues, cues[1:]) if b["start_ms"] < a["end_ms"])
    if overl:
        issues.append(f"{overl} overlapping cues")
    return {"usable": not issues, "cues": len(cues), "first_ms": first, "last_ms": last,
            "issues": issues,
            "note": "Content must still be spot-checked against audio; reuse only if verified."}


def apply_corrections(paths: Paths) -> dict:
    """Apply 02_transcription/transcript-corrections.json to the MACHINE transcript (idempotent)."""
    out = paths.p("02_transcription")
    corr = read_json(out / "transcript-corrections.json")
    if not corr:
        raise FileNotFoundError("transcript-corrections.json missing")
    for name in ("transcript", "words"):
        m = out / f"{name}.machine.json"
        if not m.exists():
            m.write_bytes((out / f"{name}.json").read_bytes())
    tj = read_json(out / "transcript.machine.json")
    wj = read_json(out / "words.machine.json")
    words = {w["id"]: dict(w) for w in wj["words"]}
    applied, problems, reanchored = [], [], []

    def anchor(item, key="from"):
        """The correction's word: by id when it still says `from`; after a re-transcription (new range, new model) the
        ids shift, so re-anchor to the word with the same text nearest to the old id (within 12 words)."""
        wid, txt = item.get("word_id"), item.get(key)
        w = words.get(wid)
        if w is None or (txt and w["word"] != txt):
            near = sorted((abs(k - (wid or 0)), k) for k, x in words.items() if txt and x["word"] == txt)
            if near and near[0][0] <= 12:
                reanchored.append(f"{wid}->{near[0][1]} '{txt}'")
                item["word_id"] = near[0][1]
                return words[near[0][1]]
        return w
    for f in corr.get("flags", []):   # uncertain words: the editor confirms them by ear; never on a graphic until then
        w = anchor(f, "heard")
        if not w:
            problems.append(f"flag: word_id {f.get('word_id')} not found")
            continue
        w["flagged"] = {"note": f.get("note") or f.get("reason") or "uncertain", "suggest": f.get("suggest")}
    for c in corr.get("corrections", []):
        w = anchor(c)
        if not w:
            problems.append(f"word_id {c['word_id']} not found")
            continue
        if c.get("from") and c["from"] != w["word"] and w["word"] == c.get("to"):
            continue    # the new transcript already says it (e.g. Whisper wrote the hamza this time)
        if c.get("from") and c["from"] != w["word"]:
            problems.append(f"word_id {c['word_id']}: expected {c['from']!r}, found {w['word']!r}")
            continue
        w["machine_word"] = w["word"]
        w["word"] = c["to"]
        w["corrected"] = {"reason": c.get("reason", ""), "confidence": c.get("confidence", "medium")}
        applied.append(c["word_id"])
    # merge emptied words into the previous kept word (timing union; starts never move)
    order = [words[k] for k in sorted(words)]
    kept = []
    for w in order:
        if w["word"] == "" and kept:
            kept[-1]["end_ms"] = max(kept[-1]["end_ms"], w["end_ms"])
            if w.get("flagged") and not kept[-1].get("flagged"):
                kept[-1]["flagged"] = w["flagged"]
        elif w["word"] != "":
            kept.append(w)
    for s in tj["segments"]:
        ids = set(s["words"])
        s["machine_text"] = s["text"]
        s["text"] = " ".join(w["word"] for w in kept if w["id"] in ids)
        s["words"] = [w["id"] for w in kept if w["id"] in ids]
    meta = dict(tj["meta"], corrections_applied=len(applied), corrections_file=str(out / "transcript-corrections.json"))
    res = finalize(paths, meta, tj["segments"], kept)
    # append correction log to the review
    rv = out / "subtitle-review.md"
    L = ["", "## Corrections applied (machine → corrected)", ""]
    for c in corr.get("corrections", []):
        if c["word_id"] in applied:
            L.append(f"- #{c['word_id']} `{c.get('from')}` → `{c['to'] or '(merged)'}` — {c.get('reason','')} [{c.get('confidence','medium')}]")
    fl = [w for w in kept if w.get("flagged")]
    L += ["", f"## Flagged for the editor's ear — {len(fl)}", "",
          "Not corrected because the audio or context isn't clear enough. These words stay in the captions as heard, "
          "and `reel plan` refuses them on any graphic until the editor confirms the transcript "
          "(`reel transcript-verify`) or the flag is resolved here.", ""]
    L += [f"- #{w['id']} `{fmt_ts(w['start_ms'], '.')}` **{w['word']}** — {w['flagged']['note']}"
          + (f" (maybe: {w['flagged']['suggest']})" if w["flagged"].get("suggest") else "") for w in fl] or ["- none"]
    L += [f"- PROBLEM: {p}" for p in problems]
    rv.write_text(rv.read_text(encoding="utf-8") + "\n".join(L) + "\n", encoding="utf-8")
    if reanchored:
        rv.write_text(rv.read_text(encoding="utf-8") + "\n## Re-anchored after re-transcription\n\n"
                      + "\n".join(f"- {r}" for r in reanchored) + "\n", encoding="utf-8")
    return dict(res, applied=len(applied), flagged=len(fl), reanchored=reanchored, problems=problems)


def words_fingerprint(paths: Paths) -> str:
    import hashlib
    f = paths.p("02_transcription/words.json")
    return hashlib.sha1(f.read_bytes()).hexdigest() if f.exists() else ""


def transcript_verified(paths: Paths) -> bool:
    """The editor confirmed THIS transcript by ear (a later correction or re-transcription makes it stale)."""
    v = read_json(paths.p("02_transcription/verification.json"), {}) or {}
    return bool(v.get("verified")) and v.get("words_sha1") in (None, words_fingerprint(paths))


def transcript_flags(paths: Paths) -> list:
    """Words still flagged as uncertain (empty once the editor has verified the current transcript)."""
    if transcript_verified(paths):
        return []
    from .plan import norm
    wj = read_json(paths.p("02_transcription/words.json"), {"words": []})
    return [dict(id=w["id"], word=w["word"], start_ms=w["start_ms"], norm=norm(w["word"]), **w["flagged"])
            for w in wj["words"] if w.get("flagged")]


def relisten(paths: Paths, word_ids: list | None = None, model_size: str = "large-v3",
             before_ms: int = 2500, after_ms: int = 2000) -> dict:
    """Second opinions on uncertain words: re-decode a few seconds around each one (flagged words by default)
    three ways — no hint, the profile hint, and a warmer temperature — so the editor gets candidates to check by ear.
    Never applied automatically: the editor's ear decides, then transcript-corrections.json records it."""
    out = paths.p("02_transcription")
    wj = read_json(out / "words.json", {"words": []})
    words = {w["id"]: w for w in wj["words"]}
    ids = word_ids or [w["id"] for w in wj["words"] if w.get("flagged")]
    ids = [i for i in ids if i in words]
    if not ids:
        return {"windows": [], "note": "no flagged words (flag them in transcript-corrections.json, or pass --words)"}
    wins = []
    for i in sorted(ids, key=lambda k: words[k]["start_ms"]):
        a, b = max(0, words[i]["start_ms"] - before_ms), words[i]["end_ms"] + after_ms
        if wins and a <= wins[-1]["b"]:
            wins[-1]["b"] = max(wins[-1]["b"], b)
            wins[-1]["ids"].append(i)
        else:
            wins.append({"a": a, "b": b, "ids": [i]})
    audio = whisper_audio(out / "dialogue_16k_mono.wav")
    model, device, _ct = whisper_model(model_size)
    lang = read_json(out / "transcript.json", {}).get("meta", {}).get("language")
    hint = load_config("transcription.json").get("initial_prompt")
    res = []
    for w in wins:
        clip = audio[int(w["a"] * 16):int(w["b"] * 16)]
        heard = " ".join(words[k]["word"] for k in sorted(words) if w["a"] <= words[k]["start_ms"] < w["b"])
        alts = {}
        for label, kw in (("no_hint", {}), ("profile_hint", {"initial_prompt": hint}), ("warmer", {"temperature": 0.4})):
            if label == "profile_hint" and not hint:
                continue
            segs, _ = model.transcribe(clip, language=lang, beam_size=5, condition_on_previous_text=False, **kw)
            alts[label] = " ".join(s.text.strip() for s in segs)
        res.append({"from": fmt_ts(w["a"], "."), "to": fmt_ts(w["b"], "."), "word_ids": w["ids"],
                    "flagged": [words[k]["word"] for k in w["ids"]], "transcript": heard, "alternatives": alts})
    rep = {"generated": __import__("time").strftime("%Y-%m-%dT%H:%M:%S"), "device": device, "windows": res,
           "note": "candidates only: correct a word only when the editor hears it (or the alternatives agree and "
                   "the context makes it clear), via transcript-corrections.json"}
    write_json(out / "relisten.json", rep)
    return rep
