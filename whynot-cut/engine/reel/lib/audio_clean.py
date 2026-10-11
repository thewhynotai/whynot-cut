"""Dialogue cleanup + pause detection (pipeline-side DSP; result is placed in Premiere, originals kept muted).

Why per-segment channel choice: shoots often record two different mics on ch1/ch2 (e.g. the speaker's
lav and an off-camera interviewer; on the first production clip the correlation was 0.13). Picking the
mic with the best signal-to-noise per transcript segment beats summing both (which doubles the noise).

The source is measured first (assess_source) and the chain follows what it needs:
  * identical channels (dual mono, a finished mix) or a mono file -> one channel, no per-segment switching
  * mains hum -> narrow notches only on the harmonics that actually stand out in the pauses (50 or 60 Hz mains)
  * already clean (speech-to-noise >= 40 dB, e.g. a mastered episode) -> no spectral denoise (it only adds artefacts)
Chain: high-pass -> [hum notches] -> [adaptive spectral denoise] -> gain + true-peak limiter.
Before/after metrics and spectrograms are written as evidence.
"""
from __future__ import annotations

import json
import re
import wave
from pathlib import Path

import numpy as np

from .common import ENV_DIR, Paths, ffmpeg_exe, now_iso, read_json, run, write_json

SR = 48000


def _read_stereo(path: Path) -> np.ndarray:
    """Any WAV (16/24-bit, WAVE_FORMAT_EXTENSIBLE) -> float32 [samples, channels] via PyAV."""
    import av
    chunks = []
    with av.open(str(path)) as c:
        for fr in c.decode(audio=0):
            a = fr.to_ndarray()
            if fr.format.is_planar:
                a = a.T
            else:
                a = a.reshape(-1, len(fr.layout.channels))
            if a.dtype.kind == "i":
                a = a.astype(np.float32) / float(np.iinfo(a.dtype).max)
            chunks.append(a.astype(np.float32))
    return np.concatenate(chunks, axis=0)


def _rms_db(x: np.ndarray) -> float:
    return float(20 * np.log10(np.sqrt(np.mean(x ** 2)) + 1e-9))


def _win_db(x: np.ndarray, hop: int = SR // 20) -> np.ndarray:
    n = len(x) // hop
    return 20 * np.log10(np.sqrt((x[:n * hop].reshape(n, hop) ** 2).mean(axis=1)) + 1e-9)


CLEAN_SNR_DB = 40.0      # a mastered / studio source: spectral denoise would only add artefacts
HUM_PROMINENCE_DB = 10.0  # a mains harmonic must stand this far above its neighbourhood (in the pauses) to be notched


def detect_hum(mono: np.ndarray, max_hz: int = 500) -> dict:
    """Mains hum measured where it is audible: the quietest 20 % of 50 ms windows (pauses), at least 2 s of them.
    Returns the mains frequency (50/60 Hz or None) and the harmonics worth a notch (100-500 Hz)."""
    hop = SR // 20
    n = len(mono) // hop
    if n < 20:
        return {"mains_hz": None, "notch_hz": [], "prominence_db": {}}
    win = mono[:n * hop].reshape(n, hop)
    d = 20 * np.log10(np.sqrt((win ** 2).mean(axis=1)) + 1e-9)
    quiet = win[d <= np.percentile(d, 20)].reshape(-1)
    if len(quiet) < 2 * SR:
        quiet = mono
    seg = SR  # 1 s FFTs (1 Hz bins), averaged
    k = len(quiet) // seg
    if k < 1:
        return {"mains_hz": None, "notch_hz": [], "prominence_db": {}}
    spec = np.mean([np.abs(np.fft.rfft(quiet[i * seg:(i + 1) * seg] * np.hanning(seg))) for i in range(k)], axis=0) + 1e-12
    best = None
    for mains in (50, 60):
        prom = {}
        for h in range(mains, max_hz + 1, mains):
            peak = spec[h - 1:h + 2].max()
            nb = np.r_[spec[max(1, h - 15):h - 3], spec[h + 4:h + 16]]
            prom[h] = round(float(20 * np.log10(peak / np.median(nb))), 1)
        score = sum(v for v in prom.values() if v >= HUM_PROMINENCE_DB)
        if best is None or score > best[0]:
            best = (score, mains, prom)
    score, mains, prom = best
    notch = [h for h, v in prom.items() if v >= HUM_PROMINENCE_DB and h >= 90]
    return {"mains_hz": mains if score else None, "notch_hz": notch, "prominence_db": prom}


def assess_source(x: np.ndarray) -> dict:
    """What the dialogue needs before any processing (identical channels, already clean, hum)."""
    ch = x.shape[1]
    identical = False
    if ch >= 2:
        # lossy stereo (AAC joint stereo) leaves the side signal ~35 dB down on a dual-mono source; two real mics differ by far more
        identical = _rms_db(x[:, 0] - x[:, 1]) - max(_rms_db(x[:, 0]), _rms_db(x[:, 1])) < -30
    mono = x[:, 0] if ch == 1 or identical else x.mean(axis=1)
    d = _win_db(mono)
    floor, speech = float(np.percentile(d, 10)), float(np.percentile(d, 90))
    return {"channels": ch, "identical_channels": identical, "noise_floor_db": round(floor, 1),
            "speech_level_db": round(speech, 1), "speech_to_noise_db": round(speech - floor, 1),
            "already_clean": speech - floor >= CLEAN_SNR_DB, "hum": detect_hum(mono)}


def choose_channels(paths: Paths, x: np.ndarray) -> list[dict]:
    """Per Whisper segment: channel with the best (segment level - channel noise floor)."""
    segs = read_json(paths.p("02_transcription/transcript.json"))["segments"]
    floors = [float(np.percentile(_win_db(x[:, c]), 10)) for c in range(x.shape[1])]
    plan = []
    for s in segs:
        a, b = int(s["start_ms"] * SR / 1000), int(s["end_ms"] * SR / 1000)
        snr = [_rms_db(x[a:b, c]) - floors[c] for c in range(x.shape[1])]
        plan.append({"segment_id": s["id"], "start_ms": s["start_ms"], "end_ms": s["end_ms"],
                     "channel": int(np.argmax(snr)) + 1, "snr_db": [round(v, 1) for v in snr], "text": s["text"][:60]})
    return plan


def _channel_regions(plan: list[dict], dur_ms: int) -> list[tuple[int, int, int]]:
    """Merge segment choices into contiguous regions [start,end,channel]; switch at gap midpoints."""
    regs = []
    for i, p in enumerate(plan):
        start = 0 if i == 0 else (plan[i - 1]["end_ms"] + p["start_ms"]) // 2
        end = dur_ms if i == len(plan) - 1 else (p["end_ms"] + plan[i + 1]["start_ms"]) // 2
        if regs and regs[-1][2] == p["channel"]:
            regs[-1] = (regs[-1][0], end, p["channel"])
        else:
            regs.append((start, end, p["channel"]))
    return regs


def _loudness(path: Path) -> tuple[float, float]:
    """Integrated LUFS and true peak (dBTP)."""
    e = run([ffmpeg_exe(), "-hide_banner", "-nostats", "-i", str(path), "-af", "ebur128=peak=true", "-f", "null", "-"], check=False).stderr
    return float(re.findall(r"I:\s+(-?[0-9.]+) LUFS", e)[-1]), float(re.findall(r"Peak:\s+(-?[0-9.]+) dBFS", e)[-1])


def clean(paths: Paths, src: Path, nr_db: float | None = None, target_lufs: float = -14.0,
          hum_notches_hz="auto", expander: bool = False) -> dict:
    """nr_db None = decide from the source (24 dB, or 0 when it is already clean); hum_notches_hz "auto" = the
    harmonics detect_hum finds, or a list of Hz to force, or () for none."""
    ff = ffmpeg_exe()
    out_dir = paths.p("06_audio/dialogue")
    out_dir.mkdir(parents=True, exist_ok=True)
    raw = out_dir / "dialogue_raw_48k.wav"
    from .common import range_input_args, source_range
    run([ff, "-y", "-loglevel", "error", *range_input_args(source_range(paths)), "-i", str(src), "-map", "0:a:0",
         "-ar", str(SR), "-c:a", "pcm_s16le", str(raw)])
    x = _read_stereo(raw)
    dur_ms = int(len(x) * 1000 / SR)
    src_info = assess_source(x)
    single = x.shape[1] == 1 or src_info["identical_channels"]
    plan = choose_channels(paths, x[:, :1] if single else x)
    regions = _channel_regions(plan, dur_ms)
    if nr_db is None:
        nr_db = 0 if src_info["already_clean"] else 24
    if hum_notches_hz == "auto":
        hum_notches_hz = src_info["hum"]["notch_hz"]
    # denoise each channel fully (keeps noise tracking continuous), then splice regions with 40 ms crossfades
    # Measured on the first production clip (speaker mic, 7 s+): raw contrast 15.5 dB -> 23.4 dB with this chain. 89 % of the residual
    # noise was mains hum at 100 Hz (+31 dB) and harmonics, which afftdn alone cannot remove -> narrow notches.
    stages = ["highpass=f=90", "highpass=f=90"] + [f"bandreject=f={f}:width_type=q:w=25" for f in hum_notches_hz]
    if nr_db and nr_db > 0:
        stages.append(f"afftdn=nr={nr_db}:nf=-32:tn=1")
    denoise = ",".join(stages)
    # No compressor and no dynamic loudnorm: both lift the noise floor with the speech. Measured on C0238 (doctor's mic):
    # denoise 23.7 dB S/N -> +compressor+loudnorm 16.5 dB; -> plain gain + true-peak limiter 22.8 dB. Optional gentle
    # downward expander between words (27.7 dB) can sound choppy, so it is opt-in (--expander).
    chain = denoise + (",agate=threshold=0.016:ratio=3:range=0.4:attack=5:release=150:knee=4" if expander else "")
    cleaned = {}
    for c in sorted({r[2] for r in regions} | {1}):
        p = out_dir / f"ch{c}_denoised.wav"
        run([ff, "-y", "-loglevel", "error", "-i", str(raw), "-af", f"pan=mono|c0=c{c - 1},{chain}",
             "-ar", str(SR), "-c:a", "pcm_s16le", str(p)])
        cleaned[c] = _read_stereo(p)[:, 0]
    cleaned.setdefault(2, cleaned[1])
    n = min(len(v) for v in cleaned.values())
    # per-sample weight for ch2 (0 = ch1, 1 = ch2), smoothed into 40 ms linear crossfades at switches
    w2 = np.zeros(n, dtype=np.float32)
    for (ra, rb, c) in regions:
        if c == 2:
            w2[int(ra * SR / 1000):min(n, int(rb * SR / 1000))] = 1.0
    xf = int(0.04 * SR)
    w2 = np.convolve(w2, np.ones(xf, dtype=np.float32) / xf, mode="same")
    mix = cleaned[1][:n] * (1 - w2) + cleaned[2][:n] * w2
    spliced = out_dir / "dialogue_spliced.wav"
    with wave.open(str(spliced), "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(SR)
        w.writeframes((np.clip(mix, -1, 1) * 32767).astype(np.int16).tobytes())
    # loudness: plain gain + true-peak limiter, corrected once (the limiter shaves a little loudness off the peaks)
    final = out_dir / "dialogue_clean.wav"
    gain = target_lufs - _loudness(spliced)[0]
    for _ in range(2):
        run([ff, "-y", "-loglevel", "error", "-i", str(spliced), "-af",
             f"volume={gain:.2f}dB,alimiter=limit=0.84:attack=3:release=60:level=false,aformat=channel_layouts=stereo",
             "-ar", str(SR), "-c:a", "pcm_s24le", str(final)])
        lufs, tp = _loudness(final)
        if abs(lufs - target_lufs) <= 0.5:
            break
        gain += target_lufs - lufs
    metrics = evidence(paths, raw, final, plan)
    pre = out_dir / "dialogue_denoise_only.wav"
    run([ff, "-y", "-loglevel", "error", "-i", str(raw), "-af",
         f"pan=mono|c0=c{max(set(r[2] for r in regions), key=lambda c: sum(b - a for a, b, cc in regions if cc == c)) - 1},{denoise}",
         "-c:a", "pcm_s16le", str(pre)])
    d = _win_db(_read_stereo(pre)[:, 0])
    metrics["denoise_only_main_mic"] = {"noise_floor_db": round(float(np.percentile(d, 10)), 1),
                                        "speech_level_db": round(float(np.percentile(d, 90)), 1),
                                        "speech_to_noise_db": round(float(np.percentile(d, 90) - np.percentile(d, 10)), 1)}
    decisions = []
    if single:
        decisions.append("one channel used: " + ("the file is mono" if x.shape[1] == 1 else
                                                 "both channels carry the same signal (dual mono / finished mix)"))
    decisions.append(f"hum notches at {', '.join(map(str, hum_notches_hz))} Hz" if hum_notches_hz else
                     "no hum notches (no mains hum stands out in the pauses)")
    decisions.append(f"spectral denoise {nr_db} dB" if nr_db else
                     f"no spectral denoise: the source is already clean ({src_info['speech_to_noise_db']} dB speech-to-noise)")
    res = {"generated": now_iso(), "source": str(src), "output": str(final), "source_assessment": src_info,
           "decisions": decisions, "channel_plan": plan,
           "regions_ms": regions, "chain": chain, "loudness_target": target_lufs, "metrics": metrics,
           "loudness": {"gain_db": round(gain, 2), "lufs": lufs, "true_peak_dbtp": tp},
           "note": "Original camera audio is kept (muted) in the Premiere project for A/B."}
    write_json(out_dir / "dialogue-clean-report.json", res)
    return res


def _lufs(path: Path) -> float | None:
    p = run([ffmpeg_exe(), "-hide_banner", "-nostats", "-i", str(path), "-af", "ebur128=peak=true", "-f", "null", "-"], check=False)
    m = re.findall(r"I:\s+(-?[0-9.]+) LUFS", p.stderr)
    return float(m[-1]) if m else None


def evidence(paths: Paths, raw: Path, final: Path, plan: list[dict]) -> dict:
    """Noise floor (10th pct of 50 ms windows) and speech level before/after, plus spectrograms."""
    ff = ffmpeg_exe()
    xr = _read_stereo(raw)
    xf = _read_stereo(final)[:, 0]
    best_raw = np.zeros(len(xr), dtype=np.float32)
    for p in plan:  # compare like with like: raw = the same channel choice, unprocessed
        a, b = int(p["start_ms"] * SR / 1000), int(p["end_ms"] * SR / 1000)
        best_raw[a:b] = xr[a:b, p["channel"] - 1]
    def stats(v):
        d = _win_db(v)
        return {"noise_floor_db": round(float(np.percentile(d, 10)), 1),
                "speech_level_db": round(float(np.percentile(d, 90)), 1),
                "speech_to_noise_db": round(float(np.percentile(d, 90) - np.percentile(d, 10)), 1)}
    qc = paths.p("08_quality_control/audio")
    qc.mkdir(parents=True, exist_ok=True)
    for name, f in (("before", raw), ("after", final)):
        run([ff, "-y", "-loglevel", "error", "-i", str(f), "-lavfi",
             "showspectrumpic=s=1600x400:mode=combined:color=intensity:scale=log:legend=1:stop=8000",
             str(qc / f"spectrogram_{name}.png")], check=False)
    return {"before_selected_mic": stats(best_raw), "after": stats(xf),
            "lufs_before": _lufs(raw), "lufs_after": _lufs(final),
            "spectrograms": [str(qc / "spectrogram_before.png"), str(qc / "spectrogram_after.png")]}


def detect_pauses(paths: Paths, min_pause_ms: int = 250, pad_ms: int = 80, margin_db: float = 9.0) -> dict:
    """Pauses = windows below (cleaned noise floor + margin) for >= min_pause_ms, cross-checked with word gaps.
    Returns keep-segments in SOURCE ms; pad_ms of breath kept on each side of every cut."""
    final = paths.p("06_audio/dialogue/dialogue_clean.wav")
    x = _read_stereo(final)[:, 0]
    hop_ms = 10
    d = _win_db(x, hop=SR * hop_ms // 1000)
    floor = float(np.percentile(d, 10))
    thr = floor + margin_db
    quiet = d < thr
    words = read_json(paths.p("02_transcription/words.json"))["words"]
    speech = np.zeros(len(d), dtype=bool)
    for w in words:  # never cut inside a short word's core; words > 500 ms usually contain a stretched-over pause
        a, b = w["start_ms"], w["end_ms"]
        if b - a > 500:
            continue
        core0, core1 = a + 0.2 * (b - a), b - 0.2 * (b - a)
        speech[int(core0 // hop_ms):int(core1 // hop_ms) + 1] = True
    quiet &= ~speech
    pauses, i = [], 0
    while i < len(quiet):
        if quiet[i]:
            j = i
            while j < len(quiet) and quiet[j]:
                j += 1
            s, e = i * hop_ms, j * hop_ms
            if e - s >= min_pause_ms:
                pauses.append((s, e))
            i = j
        else:
            i += 1
    dur_ms = int(len(x) * 1000 / SR)
    cuts = []
    for s, e in pauses:
        cs = s + pad_ms if s > 0 else 0
        ce = e - pad_ms if e < dur_ms else dur_ms
        if ce - cs >= 60:
            cuts.append((cs, ce))
    keep, t = [], 0
    for cs, ce in cuts:
        if cs > t:
            keep.append((t, cs))
        t = ce
    if t < dur_ms:
        keep.append((t, dur_ms))
    removed = sum(ce - cs for cs, ce in cuts)
    res = {"generated": now_iso(), "threshold_db": round(thr, 1), "noise_floor_db": round(floor, 1),
           "min_pause_ms": min_pause_ms, "pad_ms": pad_ms, "pauses_ms": pauses, "cuts_ms": cuts,
           "keep_ms": keep, "removed_ms": removed, "source_duration_ms": dur_ms,
           "new_duration_ms": dur_ms - removed}
    write_json(paths.p("06_audio/dialogue/pauses.json"), res)
    return res


def verify_cuts(paths: Paths, model_size: str = "large-v3") -> dict:
    """Evidence that pause removal cut NO speech. The tightened dialogue is built and read by Whisper in <= 20 s chunks
    split at the cuts; each chunk's UNCUT source span is read by the same model with the same hint, and the two readings
    are compared. A word in the uncut reading that is missing from the cut one, next to a cut, is a bad cut.
    (Comparing with the corrected transcript instead blamed the cuts for every correction, vocabulary spelling and fast
    colloquial phrase Whisper reads differently: 77-82 % "coverage" on a clean reel.)"""
    import difflib
    import re as _re
    from .plan import norm, to_ms, union_ranges
    from .transcribe import _glossary_terms, whisper_audio, whisper_model
    pz = dict(read_json(paths.p("06_audio/dialogue/pauses.json")))
    # pauses the edit protects (global.remove_pauses.protect, e.g. a joke's timing) are never cut: check only real cuts
    rp = (read_json(paths.p("01_analysis/edit-decisions.json"), {}) or {}).get("global", {}).get("remove_pauses")
    prot = [[to_ms(a), to_ms(b)] for a, b in ((rp or {}).get("protect") or [])] if isinstance(rp, dict) else []
    if prot:
        pz["keep_ms"] = union_ranges(pz["keep_ms"], prot)
    clean = paths.p("06_audio/dialogue/dialogue_clean.wav")
    x = _read_stereo(clean)[:, 0]
    parts = [x[int(a * SR / 1000):int(b * SR / 1000)].copy() for a, b in pz["keep_ms"]]
    xf = int(0.01 * SR)
    for i in range(1, len(parts)):  # 10 ms fades at each join (what Premiere's cut + default audio looks like)
        parts[i - 1][-xf:] *= np.linspace(1, 0, xf)
        parts[i][:xf] *= np.linspace(0, 1, xf)
    tight = np.concatenate(parts)
    # chunks of the tightened audio, split at cut points (silence), each <= 20 s: one long decode lets Whisper skip a
    # whole 30 s window (seen on a real clip: 36 s of speech came back as one word), which looks like lost speech
    chunks, pos = [], 0
    for (ka, kb), part in zip(pz["keep_ms"], parts):
        if not chunks or (pos - chunks[-1]["t0"] + len(part) > 20 * SR and pos > chunks[-1]["t0"]):
            if chunks:
                chunks[-1]["t1"] = pos
            chunks.append({"t0": pos, "keeps": []})
        chunks[-1]["keeps"].append((ka, kb))
        pos += len(part)
    if chunks:
        chunks[-1]["t1"] = pos
    out = paths.p("06_audio/dialogue/dialogue_tight_check.wav")
    with wave.open(str(out), "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(SR)
        w.writeframes((np.clip(tight, -1, 1) * 32767).astype(np.int16).tobytes())
    m, _dev, _ct = whisper_model(model_size)
    tj = read_json(paths.p("02_transcription/transcript.json"))
    lang = tj["meta"].get("language")
    # the same vocabulary hint for both readings (without it Whisper drops English loanwords, verified on C0238)
    vocab = sorted({w for s in tj["segments"] for w in _re.findall(r"[A-Za-z][A-Za-z ]+", s["text"])})
    prompt = (tj["meta"].get("initial_prompt") or "") + " " + ", ".join(vocab + _glossary_terms()[:40])
    tight16, base16 = whisper_audio(out), whisper_audio(clean)
    # deterministic readings (temperature 0, same options): Whisper's default temperature fallback samples randomly on
    # hard passages, so two readings of IDENTICAL audio differed (seen on a fast colloquial joke) and looked like cuts
    opts = dict(language=lang, beam_size=5, condition_on_previous_text=False, initial_prompt=prompt, temperature=0.0,
                word_timestamps=True)
    missing, asr_variance, changed, texts = [], [], [], []
    matched = total = n_tight = 0
    for c in chunks:
        s0, s1 = c["keeps"][0][0], c["keeps"][-1][1]
        bsegs, _ = m.transcribe(base16[int(s0 * 16):int(s1 * 16)], **opts)
        base = [(t, s0 + w.start * 1000, s0 + w.end * 1000) for sg in bsegs for w in (sg.words or [])
                for t in norm(w.word).split()]
        tsegs, _ = m.transcribe(tight16[c["t0"] // 3:c["t1"] // 3], **opts)
        txt = " ".join(sg.text for sg in tsegs)
        texts.append(txt)
        b = norm(txt).split()
        a = [t for t, _, _ in base]
        removed = [(c["keeps"][i][1], c["keeps"][i + 1][0]) for i in range(len(c["keeps"]) - 1)]

        def near_cut(i1, i2, slack=60):
            e0, e1 = base[i1][1], base[i2 - 1][2]
            return [(ra, rb) for ra, rb in removed if ra < e1 + slack and rb > e0 - slack]
        sm = difflib.SequenceMatcher(a=a, b=b, autojunk=False)
        for op, i1, i2, j1, j2 in sm.get_opcodes():
            if op == "delete":
                item = {"words": " ".join(a[i1:i2]), "src_ms": [round(base[i1][1]), round(base[i2 - 1][2])],
                        "cuts_nearby": near_cut(i1, i2)}
                (missing if item["cuts_nearby"] else asr_variance).append(item)
            elif op == "replace":
                item = {"orig": " ".join(a[i1:i2]), "tight": " ".join(b[j1:j2]),
                        "src_ms": [round(base[i1][1]), round(base[i2 - 1][2])], "cuts_nearby": near_cut(i1, i2)}
                # many words heard as few is lost speech, not a different reading
                if (i2 - i1) - (j2 - j1) >= 3 and (j2 - j1) < 0.5 * (i2 - i1):
                    (missing if item["cuts_nearby"] else asr_variance).append(
                        {"words": item["orig"], "src_ms": item["src_ms"], "cuts_nearby": item["cuts_nearby"],
                         "heard_as": item["tight"]})
                else:
                    changed.append(item)
        matched += sum(bl.size for bl in sm.get_matching_blocks())
        total += len(a)
        n_tight += len(b)
    coverage = round(matched / max(1, total), 3)
    ok = not missing and coverage >= 0.85
    res = {"ok": ok, "coverage": coverage, "orig_words": total, "tight_words": n_tight, "chunks": len(chunks),
           "cuts": sum(len(c["keeps"]) - 1 for c in chunks), "protected_ranges_ms": prot,
           "missing": missing, "asr_variance_not_near_cuts": asr_variance, "changed": changed,
           "rule": "per chunk: the same model reads the uncut span and the cut audio; missing = a word of the uncut reading "
                   "absent from (or collapsed in) the cut reading AND within 60 ms of a cut; ok also needs >= 85 % matched",
           "tight_transcript": "  ".join(texts).strip(), "at": now_iso()}
    if not ok and not missing:
        res["verdict"] = "inconclusive: the two readings matched too few words to prove the cuts; listen to them"
    write_json(paths.p("06_audio/dialogue/cut-verification.json"), res)
    return res
