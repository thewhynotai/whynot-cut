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

Long clips (3.0 T2.13, engine review perf §9): ffmpeg does all the filtering; Python only MEASURES, and it reads the
audio in blocks of BLOCK samples (_iter_blocks), never the whole file as float32 arrays (90 min of 48 kHz stereo is
about 2 GB that way, plus copies). Every measurement is a per-window number (10 ms or 50 ms windows) or a running sum,
and a block is a whole number of windows, so the streamed result is the same number the whole-file code gave. The cut
proof reads only the audio around each cut (verify_cuts).
"""
from __future__ import annotations

import contextlib
import re
import wave
from pathlib import Path

import numpy as np

from .common import Paths, ffmpeg_exe, now_iso, read_json, run, write_json

SR = 48000
HOP = SR // 20           # 50 ms analysis windows (levels, noise floor, hum)
BLOCK = SR * 60          # streaming block: 60 s, a whole number of 10 ms and 50 ms windows


# --------------------------------------------------------------------------- reading
def _frame_array(fr) -> np.ndarray:
    a = fr.to_ndarray()
    if fr.format.is_planar:
        a = a.T
    else:
        a = a.reshape(-1, len(fr.layout.channels))
    if a.dtype.kind == "i":
        a = a.astype(np.float32) / float(np.iinfo(a.dtype).max)
    return a.astype(np.float32)


def _frames(path: Path):
    import av
    with av.open(str(path)) as c:
        for fr in c.decode(audio=0):
            yield _frame_array(fr)


def _read_stereo(path: Path) -> np.ndarray:
    """Any WAV (16/24-bit, WAVE_FORMAT_EXTENSIBLE) -> float32 [samples, channels] via PyAV. The WHOLE file in memory:
    only for short audio (reel previews, tests). The cleanup pipeline streams it with _iter_blocks."""
    with contextlib.closing(_frames(path)) as frames:
        return np.concatenate(list(frames), axis=0)


def _iter_blocks(path: Path, block: int | None = None):
    """The file as float32 [n, channels] blocks of exactly `block` samples (BLOCK by default), the last one shorter."""
    block = block or BLOCK
    buf, have = [], 0
    with contextlib.closing(_frames(path)) as frames:
        for a in frames:
            buf.append(a)
            have += len(a)
            if have >= block:
                cat = np.concatenate(buf, axis=0)
                k = len(cat) // block * block
                for i in range(0, k, block):
                    yield cat[i:i + block]
                buf, have = ([cat[k:]] if k < len(cat) else []), len(cat) - k
    if have:
        yield np.concatenate(buf, axis=0)


def _array_blocks(x: np.ndarray, block: int | None = None):
    """An in-memory signal as the same kind of block source as a file (the array API and tests use it)."""
    x = x if x.ndim == 2 else x[:, None]
    block = block or BLOCK
    return lambda: (x[i:i + block] for i in range(0, len(x), block))


def _n_samples(path: Path) -> int:
    try:
        with wave.open(str(path)) as w:
            return w.getnframes()
    except (wave.Error, EOFError):
        with contextlib.closing(_iter_blocks(path)) as blocks:
            return sum(len(b) for b in blocks)


def _pcm16(x: np.ndarray) -> bytes:
    return (np.clip(x, -1, 1) * 32767).astype(np.int16).tobytes()


def _to16k(x: np.ndarray) -> np.ndarray:
    """48 kHz mono float -> what Whisper reads: 16-bit, then 16 kHz mono float32, in-process with PyAV's
    libswresample. Bit-identical to transcribe.whisper_audio on a 16-bit WAV of x (ffmpeg -ac 1 -ar 16000), without
    a temp file and an ffmpeg process per reading. Each resampler leaves a filter graph in a reference cycle (~2 MB,
    freed only by the cycle collector), so the caller runs gc.collect() between windows."""
    import av
    pcm = (np.clip(x, -1, 1) * 32767).astype(np.int16)
    rs = av.AudioResampler(format="s16", layout="mono", rate=16000)
    out = []
    for i in range(0, len(pcm), SR):
        fr = av.AudioFrame.from_ndarray(pcm[None, i:i + SR], format="s16", layout="mono")
        fr.sample_rate = SR
        out += [f.to_ndarray().reshape(-1) for f in rs.resample(fr)]
    out += [f.to_ndarray().reshape(-1) for f in rs.resample(None)]
    return (np.concatenate(out) if out else np.zeros(0, np.int16)).astype(np.float32) / 32768.0


# --------------------------------------------------------------------------- levels
def _rms_db(x: np.ndarray) -> float:
    return float(20 * np.log10(np.sqrt(np.mean(x ** 2)) + 1e-9))


def _wpow(x: np.ndarray, hop: int) -> np.ndarray:
    """Mean power of each whole hop-sample window (a trailing part window is dropped)."""
    n = len(x) // hop
    return (x[:n * hop].reshape(n, hop) ** 2).mean(axis=1)


def _db(p: np.ndarray) -> np.ndarray:
    return 20 * np.log10(np.sqrt(p) + 1e-9)


def _win_db(x: np.ndarray, hop: int = HOP) -> np.ndarray:
    return _db(_wpow(x, hop))


def _stream_win_db(blocks, hop: int = HOP, sig=None) -> tuple[np.ndarray, int]:
    """_win_db over a block source (sig picks the signal from a block; default channel 1) and the length in samples.
    Identical to _win_db on the whole file: each window is reduced on its own and no window straddles two blocks."""
    parts, n = [], 0
    with contextlib.closing(blocks()) as it:   # closed (PyAV handle too) even if the loop raises
        for b in it:
            if n % hop:
                raise ValueError(f"streaming blocks must be whole {hop}-sample windows")
            parts.append(_wpow(b[:, 0] if sig is None else sig(b), hop))
            n += len(b)
    return (_db(np.concatenate(parts)) if parts else np.zeros(0, np.float32)), n


def _db_ss(ss: float, n: int) -> float:
    """dB of the RMS from a sum of squares over n samples (silence / no samples -> -180 dB)."""
    return float(20 * np.log10(np.sqrt(ss / n if n else 0.0) + 1e-9))


def _stats(d: np.ndarray) -> dict:
    return {"noise_floor_db": round(float(np.percentile(d, 10)), 1),
            "speech_level_db": round(float(np.percentile(d, 90)), 1),
            "speech_to_noise_db": round(float(np.percentile(d, 90) - np.percentile(d, 10)), 1)}


CLEAN_SNR_DB = 40.0      # a mastered / studio source: spectral denoise would only add artefacts
HUM_PROMINENCE_DB = 10.0  # a mains harmonic must stand this far above its neighbourhood (in the pauses) to be notched


def _hum(blocks, sig, d: np.ndarray, max_hz: int = 500) -> dict:
    """detect_hum over a block source. d = the 50 ms window levels of sig(block) (picks the quiet windows)."""
    none = {"mains_hz": None, "notch_hz": [], "prominence_db": {}}
    if len(d) < 20:
        return none
    quiet = d <= np.percentile(d, 20)
    use_quiet = int(quiet.sum()) * HOP >= 2 * SR   # else the whole signal
    han = np.hanning(SR)
    total, k, buf, w = None, 0, [], 0
    with contextlib.closing(blocks()) as it:   # closed (PyAV handle too) even if the loop raises
        for b in it:
            s = sig(b)
            if use_quiet:
                nw = len(s) // HOP
                s = s[:nw * HOP].reshape(nw, HOP)[quiet[w:w + nw]].reshape(-1)
                w += nw
            buf.append(s)
            if sum(len(v) for v in buf) >= SR:   # 1 s FFTs (1 Hz bins) over the concatenated quiet audio, averaged
                cat = np.concatenate(buf)
                m = len(cat) // SR
                spec = np.abs(np.fft.rfft(cat[:m * SR].reshape(m, SR) * han, axis=1)).sum(axis=0)
                total, k, buf = (spec if total is None else total + spec), k + m, [cat[m * SR:]]
    if k < 1:
        return none
    spec = total / k + 1e-12
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


def detect_hum(mono: np.ndarray, max_hz: int = 500) -> dict:
    """Mains hum measured where it is audible: the quietest 20 % of 50 ms windows (pauses), at least 2 s of them.
    Returns the mains frequency (50/60 Hz or None) and the harmonics worth a notch (100-500 Hz)."""
    mono = np.asarray(mono)
    return _hum(_array_blocks(mono), lambda b: b[:, 0], _win_db(mono), max_hz)


def _scan(blocks, segs=()) -> dict:
    """One pass over the source: per-channel (and channel-mean) 50 ms window powers, whole-file sums of squares of
    ch1, ch2 and ch1-ch2, and each transcript segment's sum of squares per channel."""
    bounds = [(int(s["start_ms"] * SR / 1000), int(s["end_ms"] * SR / 1000)) for s in segs]
    sa = np.array([a for a, _ in bounds], dtype=np.int64)
    sb = np.array([b for _, b in bounds], dtype=np.int64)
    ch, n = None, 0
    with contextlib.closing(blocks()) as it:   # closed (PyAV handle too) even if the loop raises
        for b in it:
            if ch is None:
                ch = b.shape[1]
                pw, pw_mean = [[] for _ in range(ch)], []
                ss, ss_diff = np.zeros(ch), 0.0
                seg_ss, seg_n = np.zeros((len(bounds), ch)), np.zeros(len(bounds), dtype=np.int64)
            for c in range(ch):
                pw[c].append(_wpow(b[:, c], HOP))
            sq = np.square(b, dtype=np.float64)
            ss += sq.sum(axis=0)
            if ch >= 2:
                pw_mean.append(_wpow(b.mean(axis=1), HOP))
                ss_diff += float(np.square(b[:, 0] - b[:, 1], dtype=np.float64).sum())
            p0, p1 = n, n + len(b)
            for i in np.nonzero((sa < p1) & (sb > p0))[0]:
                lo, hi = max(int(sa[i]), p0) - p0, min(int(sb[i]), p1) - p0
                seg_ss[i] += sq[lo:hi].sum(axis=0)
                seg_n[i] += hi - lo
            n = p1
    if ch is None:
        raise ValueError("no audio samples")
    return {"n": n, "channels": ch, "pw": [np.concatenate(v) for v in pw],
            "pw_mean": np.concatenate(pw_mean) if pw_mean else None, "ss": ss, "ss_diff": ss_diff,
            "seg_ss": seg_ss, "seg_n": seg_n}


def _assess(blocks, sc: dict) -> dict:
    ch, n = sc["channels"], sc["n"]
    identical = False
    if ch >= 2:
        # lossy stereo (AAC joint stereo) leaves the side signal ~35 dB down on a dual-mono source; two real mics differ by far more
        identical = _db_ss(sc["ss_diff"], n) - max(_db_ss(sc["ss"][0], n), _db_ss(sc["ss"][1], n)) < -30
    one = ch == 1 or identical
    d = _db(sc["pw"][0] if one else sc["pw_mean"])
    floor, speech = float(np.percentile(d, 10)), float(np.percentile(d, 90))
    return {"channels": ch, "identical_channels": identical, "noise_floor_db": round(floor, 1),
            "speech_level_db": round(speech, 1), "speech_to_noise_db": round(speech - floor, 1),
            "already_clean": speech - floor >= CLEAN_SNR_DB,
            "hum": _hum(blocks, (lambda b: b[:, 0]) if one else (lambda b: b.mean(axis=1)), d)}


def assess_source(x: np.ndarray) -> dict:
    """What the dialogue needs before any processing (identical channels, already clean, hum). In-memory form;
    clean() runs the same code streamed over the file."""
    blocks = _array_blocks(x)
    return _assess(blocks, _scan(blocks))


def _channel_plan(segs: list[dict], sc: dict, nch: int) -> list[dict]:
    """Per Whisper segment: channel with the best (segment level - channel noise floor), over the first nch channels."""
    floors = [float(np.percentile(_db(sc["pw"][c]), 10)) for c in range(nch)]
    plan = []
    for i, s in enumerate(segs):
        snr = [_db_ss(sc["seg_ss"][i, c], int(sc["seg_n"][i])) - floors[c] for c in range(nch)]
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


XFADE = int(0.04 * SR)   # 40 ms crossfade where the chosen mic switches


def _xfade_weights(regions, n: int, p0: int, p1: int, xf: int = XFADE) -> np.ndarray:
    """Samples [p0, p1) of the ch2 weight (0 = ch1, 1 = ch2): 1 inside channel-2 regions, smoothed into linear
    crossfades. The same numbers as np.convolve(w2, ones(xf) / xf, "same") over the whole clip (zeros outside 0..n),
    from a running count, so a block needs no more than itself plus one crossfade of context."""
    a = p0 - xf // 2                 # convolve "same": sample i averages [i - xf//2, i + (xf-1)//2]
    m = p1 - p0
    raw = np.zeros(m + xf - 1, dtype=np.int32)
    for ra, rb, c in regions:
        if c == 2:
            s, e = max(0, int(ra * SR / 1000), a), min(n, int(rb * SR / 1000), a + len(raw))
            if e > s:
                raw[s - a:e - a] = 1
    cs = np.concatenate([[0], np.cumsum(raw)])
    return ((cs[xf:xf + m] - cs[:m]) / xf).astype(np.float32)


def _splice(ch1: Path, ch2: Path | None, regions, out: Path) -> None:
    """Splice the denoised mics region by region with crossfades, block by block, into a 16-bit mono WAV."""
    n = _n_samples(ch1) if ch2 is None else min(_n_samples(ch1), _n_samples(ch2))
    g1 = _iter_blocks(ch1)
    g2 = _iter_blocks(ch2) if ch2 is not None else None
    pos = 0
    with contextlib.closing(g1), contextlib.closing(g2) if g2 else contextlib.nullcontext(), \
            wave.open(str(out), "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(SR)
        for b1 in g1:
            if pos >= n:
                break
            m = min(len(b1), n - pos)
            c1 = b1[:m, 0]
            if g2 is None:     # no channel-2 region: the weight is 0 everywhere
                mix = c1
            else:
                w2 = _xfade_weights(regions, n, pos, pos + m)
                mix = c1 * (1 - w2) + next(g2)[:m, 0] * w2
            w.writeframes(_pcm16(mix))
            pos += m


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
    segs = read_json(paths.p("02_transcription/transcript.json"))["segments"]
    blocks = lambda: _iter_blocks(raw)  # noqa: E731  (two passes: levels, then hum in the quiet windows)
    sc = _scan(blocks, segs)
    dur_ms = int(sc["n"] * 1000 / SR)
    src_info = _assess(blocks, sc)
    single = sc["channels"] == 1 or src_info["identical_channels"]
    plan = _channel_plan(segs, sc, 1 if single else sc["channels"])
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
        cleaned[c] = p
    spliced = out_dir / "dialogue_spliced.wav"
    _splice(cleaned[1], cleaned.get(2), regions, spliced)
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
    metrics["denoise_only_main_mic"] = _stats(_stream_win_db(lambda: _iter_blocks(pre))[0])
    decisions = []
    if single:
        decisions.append("one channel used: " + ("the file is mono" if sc["channels"] == 1 else
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


SPECTRO_LONG_MS = 10 * 60_000


def evidence(paths: Paths, raw: Path, final: Path, plan: list[dict]) -> dict:
    """Noise floor (10th pct of 50 ms windows) and speech level before/after, plus spectrograms."""
    ff = ffmpeg_exe()
    segs = [(int(p["start_ms"] * SR / 1000), int(p["end_ms"] * SR / 1000), p["channel"] - 1) for p in plan]
    parts, pos = [], 0
    with contextlib.closing(_iter_blocks(raw)) as it:   # closed (PyAV handle too) even if the loop raises
        for b in it:  # compare like with like: raw = the same channel choice, unprocessed
            p0, p1 = pos, pos + len(b)
            best_raw = np.zeros(len(b), dtype=np.float32)
            for a, e, c in segs:
                lo, hi = max(a, p0), min(e, p1)
                if hi > lo:
                    best_raw[lo - p0:hi - p0] = b[lo - p0:hi - p0, c]
            parts.append(_wpow(best_raw, HOP))
            pos = p1
    before = _db(np.concatenate(parts)) if parts else np.zeros(0, np.float32)
    after = _stream_win_db(lambda: _iter_blocks(final))[0]
    qc = paths.p("08_quality_control/audio")
    qc.mkdir(parents=True, exist_ok=True)
    # showspectrumpic holds its whole input in memory (1.6 GB for 60 min of 48 kHz stereo): a long clip's picture is
    # drawn from 16 kHz mono (a third, then half of that), which still holds everything shown (0-8 kHz)
    pre = "aresample=16000,aformat=channel_layouts=mono," if pos * 1000 // SR > SPECTRO_LONG_MS else ""
    for name, f in (("before", raw), ("after", final)):
        run([ff, "-y", "-loglevel", "error", "-i", str(f), "-lavfi",
             pre + "showspectrumpic=s=1600x400:mode=combined:color=intensity:scale=log:legend=1:stop=8000",
             str(qc / f"spectrogram_{name}.png")], check=False)
    return {"before_selected_mic": _stats(before), "after": _stats(after),
            "lufs_before": _lufs(raw), "lufs_after": _lufs(final),
            "spectrograms": [str(qc / "spectrogram_before.png"), str(qc / "spectrogram_after.png")]}


def detect_pauses(paths: Paths, min_pause_ms: int = 250, pad_ms: int = 80, margin_db: float = 9.0) -> dict:
    """Pauses = windows below (cleaned noise floor + margin) for >= min_pause_ms, cross-checked with word gaps.
    Returns keep-segments in SOURCE ms; pad_ms of breath kept on each side of every cut."""
    final = paths.p("06_audio/dialogue/dialogue_clean.wav")
    hop_ms = 10
    d, n_samples = _stream_win_db(lambda: _iter_blocks(final), hop=SR * hop_ms // 1000)
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
    dur_ms = int(n_samples * 1000 / SR)
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


# --------------------------------------------------------------------------- cut proof
CUT_CONTEXT_MS = 3000    # uncut audio read on each side of a cut
READ_MAX_MS = 20000      # longest stretch one Whisper reading may hold (close cuts share a reading)
EDGE_PAD_MS = 100        # a window edge that falls inside a word moves out to just before / after that word
EDGE_MOVE_MAX_MS = 1500  # ... but never further than this (a run of touching words keeps the plain 3 s edge)
FADE = int(0.01 * SR)    # 10 ms fades at each join (what Premiere's cut + default audio looks like)
PIECE_OVERLAP_MS = 1000  # neighbouring pieces of a long removed span overlap: a word on a split is read whole once
INSIDE_MARGIN_MS = 150   # a word heard this far inside a long removed span is lost speech (not a timestamp wobble)
HALLUCINATION_DB = 3.0   # ... unless its audio is within this of the noise floor: Whisper invents words in silence


def _cut_windows(keeps: list, words: list, dur_ms: int) -> list[dict]:
    """Every cut (each gap between keeps, plus a removed lead-in or tail) grouped into reading windows in SOURCE ms.
    Each cut gets >= 3 s of kept audio on both sides (less only where the neighbouring cut or the clip edge comes
    first), window edges are moved out of words, and neighbouring cuts share a window while it stays <= 20 s. A window
    ends inside the keeps next to its own cuts, so it never contains a cut it does not own; two windows may share a
    stretch of one keep. A single cut whose removed span makes its window longer than 20 s is read in <= 20 s pieces
    split inside the removed span; neighbouring pieces overlap by 1 s and each OWNS the stretch up to the split, so a
    word on a split is read whole and counted once. `pieces` = [(read_lo, read_hi, own_lo, own_hi)]; a short window
    is one piece that reads and owns all of it."""
    ws = np.array([w["start_ms"] for w in words], dtype=float)
    we = np.array([w["end_ms"] for w in words], dtype=float)

    def out_of_words(t, bound, lo_side):
        inside = (ws < t) & (we > t)
        if not inside.any():
            return t
        if lo_side:   # into the gap before the word that holds the edge
            s = ws[inside].min()
            prev = we[we <= s]
            e = prev.max() if prev.size else -np.inf
            new = (e + s) / 2 if e > s - EDGE_PAD_MS else s - EDGE_PAD_MS
            return t if t - new > EDGE_MOVE_MAX_MS else max(bound, int(new))
        e = we[inside].max()   # into the gap after it
        nxt = ws[ws >= e]
        s = nxt.min() if nxt.size else np.inf
        new = (e + s) / 2 if s < e + EDGE_PAD_MS else e + EDGE_PAD_MS
        return t if new - t > EDGE_MOVE_MAX_MS else min(bound, int(np.ceil(new)))

    start_of = {kb: ka for ka, kb in keeps}   # keep ending where a cut starts -> its start
    end_of = {ka: kb for ka, kb in keeps}     # keep starting where a cut ends -> its end
    cuts = [(keeps[i][1], keeps[i + 1][0]) for i in range(len(keeps) - 1)]
    if not keeps:
        cuts = [(0, dur_ms)] if dur_ms > 0 else []
    else:
        cuts = ([(0, keeps[0][0])] if keeps[0][0] > 0 else []) + cuts + \
               ([(keeps[-1][1], dur_ms)] if dur_ms > keeps[-1][1] else [])
    wins = []
    for ra, rb in cuts:
        bound_lo, bound_hi = start_of.get(ra, ra), end_of.get(rb, rb)
        lo = out_of_words(max(bound_lo, ra - CUT_CONTEXT_MS), bound_lo, True)
        hi = out_of_words(min(bound_hi, rb + CUT_CONTEXT_MS), bound_hi, False)
        if wins and lo < wins[-1]["hi"] and hi - wins[-1]["lo"] <= READ_MAX_MS:
            wins[-1]["hi"] = hi
            wins[-1]["cuts"].append((ra, rb))
        else:
            wins.append({"lo": lo, "hi": hi, "cuts": [(ra, rb)]})
    for w in wins:
        lo, hi = w["lo"], w["hi"]
        if hi - lo <= READ_MAX_MS:
            w["pieces"] = [(lo, hi, lo, hi)]
            continue
        # only a single cut can make a window this long (merging stops at READ_MAX_MS): split it into equal pieces of
        # <= 19 s, every split inside the removed span [ra, rb] (the kept context on each side is <= 4.5 s, a piece
        # >= 9.5 s); each reading adds half the overlap on each inner side, so it stays <= 20 s
        ra, rb = w["cuts"][0]
        half = PIECE_OVERLAP_MS // 2
        n = -(-(hi - lo) // (READ_MAX_MS - PIECE_OVERLAP_MS))
        edges = [lo] + [min(max(lo + (hi - lo) * j // n, ra), rb) for j in range(1, n)] + [hi]
        w["pieces"] = [(max(lo, a - half), min(hi, b + half), a, b) for a, b in zip(edges, edges[1:]) if b > a]
    return wins


def _faded(seg: np.ndarray, g0: int, k: int, ks: list) -> np.ndarray:
    """seg = samples [g0, g0 + len) of keep k (keep sample bounds ks): the 10 ms fade-in at its start (if a join is
    there) then the fade-out at its end, by absolute sample index, as the old whole-file construction did."""
    out = seg.copy()
    a, b = ks[k]
    g1 = g0 + len(seg)
    if k > 0:
        lo, hi = max(g0, a), min(g1, a + FADE)
        if hi > lo:
            out[lo - g0:hi - g0] = out[lo - g0:hi - g0] * np.linspace(0, 1, FADE)[lo - a:hi - a]
    if k < len(ks) - 1:
        lo, hi = max(g0, b - FADE), min(g1, b)
        if hi > lo:
            out[lo - g0:hi - g0] = out[lo - g0:hi - g0] * np.linspace(1, 0, FADE)[lo - b + FADE:hi - b + FADE]
    return out


def _tight_pass(clean: Path, keeps: list, spans_ms: list, tight_out: Path):
    """ONE pass over the cleaned dialogue: writes the whole tightened check file (tight_out, to listen to) and yields
    (span index, uncut samples of that span, keep sample bounds) for each [lo, hi) ms span, in order (spans are sorted
    and each is <= 20 s, so only a few seconds of audio are ever held). A span past the end of the file comes back
    short or empty."""
    ks = [(int(a * SR / 1000), int(b * SR / 1000)) for a, b in keeps]
    spans = [(int(a * SR / 1000), int(b * SR / 1000)) for a, b in spans_ms]
    kp, nxt, opened, pos = 0, 0, {}, 0
    with wave.open(str(tight_out), "wb") as w, contextlib.closing(_iter_blocks(clean)) as blocks:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(SR)
        for b in blocks:
            s, p0, p1 = b[:, 0], pos, pos + len(b)
            pos = p1
            while kp < len(ks) and ks[kp][1] <= p0:
                kp += 1
            k, out = kp, []
            while k < len(ks) and ks[k][0] < p1:
                lo, hi = max(ks[k][0], p0), min(ks[k][1], p1)
                if hi > lo:
                    out.append(_faded(s[lo - p0:hi - p0], lo, k, ks))
                k += 1
            if out:
                w.writeframes(_pcm16(np.concatenate(out)))
            while nxt < len(spans) and spans[nxt][0] < p1:
                opened[nxt], nxt = [], nxt + 1
            for i in list(opened):
                a, e = spans[i]
                lo, hi = max(a, p0), min(e, p1)
                if hi > lo:
                    opened[i].append(s[lo - p0:hi - p0].copy())
                if e <= p1:
                    yield i, np.concatenate(opened.pop(i) or [np.zeros(0, np.float32)]), ks
        for i in list(opened) + list(range(nxt, len(spans))):   # spans that run past the end of the file
            yield i, np.concatenate(opened.pop(i, None) or [np.zeros(0, np.float32)]), ks


def verify_cuts(paths: Paths, model_size: str = "large-v3") -> dict:
    """Evidence that pause removal cut NO speech. For every cut, the same Whisper model, with the same hint and
    deterministic settings (temperature 0), reads the UNCUT source around it and the same span with the cut applied;
    a word of the uncut reading missing from the cut one, next to a cut, is a bad cut. (Comparing with the corrected
    transcript instead blamed the cuts for every correction, vocabulary spelling and fast colloquial phrase Whisper
    reads differently: 77-82 % "coverage" on a clean reel.)

    Windows, not the whole clip (3.0 T2.13): each cut is read with >= 3 s of kept audio on each side (to the next cut
    or the clip edge if nearer); close cuts share one window of <= 20 s. This proves the same thing as reading the
    whole clip twice: a word only counts as `missing` within 60 ms of a cut, so words farther away can never fail
    the proof, and they are identical audio in both readings anyway. Each cut keeps Whisper's local context (3 s+
    each side, edges moved out of words; the old chunks were <= 20 s too), so a word lost at a cut drops out of the
    window's reading exactly as it dropped out of the chunk's. Coverage (>= 85 %) is now measured around the cuts,
    not diluted by long stretches of untouched audio, so that gate can only get stricter; and every cut is now
    compared: the old chunks were split AT cuts, so a cut on a chunk boundary, the removed lead-in and the removed
    tail were never read.

    No reading is ever longer than 20 s (one long decode lets Whisper skip a whole 30 s window: G24). A single cut that
    removes a long span is read uncut in <= 20 s pieces split inside the removed span, overlapping by 1 s (a word on
    a split is read whole by the piece that holds its centre, and counted once). A word heard more than 150 ms inside
    the removed span is missing by definition, unless its audio sits at the noise floor: Whisper invents words in
    silence, so that one is a possible hallucination (inconclusive, listen). The rest is compared with the cut
    reading (the kept context, joined). A window is not proved when the uncut reading heard no word at all or its
    audio is shorter than the span (the pauses run past the end of the file): `ok` is then false with an
    "inconclusive" verdict."""
    import difflib
    import gc
    import re as _re
    from .plan import norm, to_ms, union_ranges
    from .transcribe import _glossary_terms, whisper_model
    pz = dict(read_json(paths.p("06_audio/dialogue/pauses.json")))
    # pauses the edit protects (global.remove_pauses.protect, e.g. a joke's timing) are never cut: check only real cuts
    rp = (read_json(paths.p("01_analysis/edit-decisions.json"), {}) or {}).get("global", {}).get("remove_pauses")
    prot = [[to_ms(a), to_ms(b)] for a, b in ((rp or {}).get("protect") or [])] if isinstance(rp, dict) else []
    if prot:
        pz["keep_ms"] = union_ranges(pz["keep_ms"], prot)
    keeps = [list(k) for k in pz["keep_ms"]]
    clean = paths.p("06_audio/dialogue/dialogue_clean.wav")
    words = (read_json(paths.p("02_transcription/words.json"), {}) or {}).get("words") or []
    wins = _cut_windows(keeps, words, int(pz.get("source_duration_ms") or (keeps[-1][1] if keeps else 0)))
    spans = [(wi, pi) for wi, w in enumerate(wins) for pi in range(len(w["pieces"]))]
    out = paths.p("06_audio/dialogue/dialogue_tight_check.wav")
    tj = read_json(paths.p("02_transcription/transcript.json"))
    lang = tj["meta"].get("language")
    # the same vocabulary hint for both readings (without it Whisper drops English loanwords, verified on C0238)
    vocab = sorted({w for s in tj["segments"] for w in _re.findall(r"[A-Za-z][A-Za-z ]+", s["text"])})
    prompt = (tj["meta"].get("initial_prompt") or "") + " " + ", ".join(vocab + _glossary_terms()[:40])
    # deterministic readings (temperature 0, same options): Whisper's default temperature fallback samples randomly on
    # hard passages, so two readings of IDENTICAL audio differed (seen on a fast colloquial joke) and looked like cuts
    opts = dict(language=lang, beam_size=5, condition_on_previous_text=False, initial_prompt=prompt, temperature=0.0,
                word_timestamps=True)
    m = whisper_model(model_size)[0] if wins else None   # no cut, nothing to prove: Whisper is not loaded
    floor_db = pz.get("noise_floor_db")
    floor_db = -70.0 if floor_db is None else float(floor_db)
    missing, asr_variance, changed, texts, report, halluc = [], [], [], [], [], []
    matched = total = n_tight = 0
    st = None
    with contextlib.closing(_tight_pass(clean, keeps, [wins[wi]["pieces"][pi][:2] for wi, pi in spans], out)) as passes:
        for si, uncut, ks in passes:
            wi, pi = spans[si]
            win = wins[wi]
            if pi == 0:
                st = {"base": [], "tight": [], "short": False}
            a0, b0, own0, own1 = win["pieces"][pi]
            last = pi == len(win["pieces"]) - 1
            g0 = int(a0 * SR / 1000)
            if len(uncut) < int(b0 * SR / 1000) - g0 - SR // 100:
                st["short"] = True       # the pauses run past the end of the audio: this span was not all read
            bsegs, _ = m.transcribe(_to16k(uncut), **opts)
            for sg in bsegs:
                for w in (sg.words or []):
                    s0, s1 = a0 + w.start * 1000, a0 + w.end * 1000
                    c = (s0 + s1) / 2
                    if len(win["pieces"]) > 1 and not (own0 <= c < own1 or (last and c == own1)):
                        continue     # the overlapping neighbour piece owns this word: count it once
                    i0, i1 = max(0, int((s0 - a0) * SR / 1000)), max(0, int((s1 - a0) * SR / 1000))
                    db = _rms_db(uncut[i0:i1]) if i1 > i0 and i0 < len(uncut) else -180.0
                    st["base"] += [(t, s0, s1, db) for t in norm(w.word).split()]
            go0, go1 = int(own0 * SR / 1000), int(own1 * SR / 1000)
            for k in range(len(ks)):     # the kept parts this piece owns, faded at the joins
                lo, hi = max(ks[k][0], go0, g0), min(ks[k][1], go1, g0 + len(uncut))
                if hi > lo:
                    st["tight"].append(_faded(uncut[lo - g0:hi - g0], lo, k, ks))
            if not last:
                gc.collect()
                continue
            # the window is complete: one reading of the same span with its cuts applied, then compare
            tsegs, _ = m.transcribe(_to16k(np.concatenate(st["tight"]) if st["tight"] else np.zeros(0, np.float32)),
                                    **opts)
            txt = " ".join(sg.text for sg in tsegs)
            texts.append(txt)
            b = norm(txt).split()
            removed = win["cuts"]
            base, gone = st["base"], []
            if len(win["pieces"]) > 1:   # a long removed span: a word heard inside it is missing by definition
                ra, rb = removed[0]
                inside = [ra + INSIDE_MARGIN_MS < (x[1] + x[2]) / 2 < rb - INSIDE_MARGIN_MS for x in base]
                gone = [x for x, i in zip(base, inside) if i]
                base = [x for x, i in zip(base, inside) if not i]
                for t, s0, s1, db in gone:
                    item = {"words": t, "src_ms": [round(s0), round(s1)], "cuts_nearby": [(ra, rb)],
                            "heard_inside_removed_span": True, "level_db": round(db, 1)}
                    (halluc if db < floor_db + HALLUCINATION_DB else missing).append(item)
            a = [x[0] for x in base]

            def near_cut(i1, i2, slack=60):
                e0, e1 = base[i1][1], base[i2 - 1][2]
                return [(ra, rb) for ra, rb in removed if ra < e1 + slack and rb > e0 - slack]
            sm = difflib.SequenceMatcher(a=a, b=b, autojunk=False)
            ghost = np.zeros(len(a), dtype=bool)   # uncut words classed as possible hallucinations (not coverage)

            def lost(i1, i2, item):
                """A lost run next to a cut is missing speech, unless all of its audio sits at the noise floor:
                Whisper hears words in silence (seen on a real clip: a 25 s removed silence read as a loop of one
                word), so that run is a possible hallucination (inconclusive, listen), never a pass."""
                if not item["cuts_nearby"]:
                    asr_variance.append(item)
                elif all(base[i][3] < floor_db + HALLUCINATION_DB for i in range(i1, i2)):
                    ghost[i1:i2] = True
                    halluc.append(dict(item, level_db=round(max(base[i][3] for i in range(i1, i2)), 1)))
                else:
                    missing.append(item)
            for op, i1, i2, j1, j2 in sm.get_opcodes():
                if op == "delete":
                    lost(i1, i2, {"words": " ".join(a[i1:i2]), "src_ms": [round(base[i1][1]), round(base[i2 - 1][2])],
                                  "cuts_nearby": near_cut(i1, i2)})
                elif op == "replace":
                    item = {"orig": " ".join(a[i1:i2]), "tight": " ".join(b[j1:j2]),
                            "src_ms": [round(base[i1][1]), round(base[i2 - 1][2])], "cuts_nearby": near_cut(i1, i2)}
                    # many words heard as few is lost speech, not a different reading
                    if (i2 - i1) - (j2 - j1) >= 3 and (j2 - j1) < 0.5 * (i2 - i1):
                        lost(i1, i2, {"words": item["orig"], "src_ms": item["src_ms"], "cuts_nearby": item["cuts_nearby"],
                                      "heard_as": item["tight"]})
                    else:
                        changed.append(item)
            # coverage counts each uncut word once: a stretch of keep read by the previous window too belongs to it
            owned_from = wins[wi - 1]["hi"] if wi else -np.inf
            hit = np.zeros(len(a), dtype=bool)
            for bl in sm.get_matching_blocks():
                hit[bl.a:bl.a + bl.size] = True
            own = np.array([x[1] >= owned_from for x in base], dtype=bool) & ~ghost
            matched += int((hit & own).sum())
            total += int(own.sum()) + sum(1 for x in gone if x[1] >= owned_from and x[3] >= floor_db + HALLUCINATION_DB)
            n_tight += len(b)
            report.append({"ms": [win["lo"], win["hi"]], "cuts": len(removed), "pieces": len(win["pieces"]),
                           "pieces_ms": [list(q[:2]) for q in win["pieces"]],
                           "uncut_words": len(st["base"]), "cut_words": len(b), "short_audio": st["short"]})
            st = None
            gc.collect()   # the resamplers' filter graphs (see _to16k): memory stays flat over hundreds of windows
    coverage = round(matched / max(1, total), 3) if wins else 1.0
    unread = [r["ms"] for r in report if not r["uncut_words"]]
    short = [r["ms"] for r in report if r["short_audio"]]
    ok = not missing and coverage >= 0.85 and not unread and not short and not halluc
    res = {"ok": ok, "coverage": coverage, "orig_words": total, "tight_words": n_tight, "chunks": len(wins),
           "cuts": sum(len(w["cuts"]) for w in wins), "windows_ms": [[w["lo"], w["hi"]] for w in wins],
           "windows": report, "windows_without_words": unread, "windows_short_audio": short,
           "protected_ranges_ms": prot,
           "missing": missing, "possible_hallucinations": halluc, "noise_floor_db": floor_db,
           "asr_variance_not_near_cuts": asr_variance, "changed": changed,
           "rule": "per cut: the same model reads the uncut source around it (>= 3 s each side; close cuts share one "
                   "<= 20 s window; a long removed span is read in <= 20 s pieces overlapping by 1 s, and a word "
                   "heard > 150 ms inside it is missing, or a possible hallucination when its audio is at the noise "
                   "floor) and the same span with the cuts applied; missing = a word of the uncut reading absent from "
                   "(or collapsed in) the cut reading AND within 60 ms of a cut; ok also needs >= 85 % matched and "
                   "every window read (words heard, audio not short)",
           "tight_transcript": "  ".join(texts).strip(), "at": now_iso()}
    if not wins:
        res["note"] = "no cuts: nothing was removed, so there is nothing to prove"
    elif not ok and not missing:
        why = [f"{len(short)} window(s) run past the end of the audio" if short else "",
               f"{len(unread)} window(s) where the uncut reading heard no word" if unread else "",
               f"{len(halluc)} word(s) heard only in near-silence at a cut (possible hallucination: Whisper hears words in silence)"
               if halluc else "",
               "the two readings matched too few words to prove the cuts" if coverage < 0.85 else ""]
        res["verdict"] = "inconclusive: " + "; ".join(x for x in why if x) + "; listen to them"
    write_json(paths.p("06_audio/dialogue/cut-verification.json"), res)
    return res
