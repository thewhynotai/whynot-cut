"""audio-clean on long clips (3.0 T2.13, engine review perf §9 / IM-14 / §7.3 item 4).

The engine streams the dialogue in blocks (never the whole 48 kHz file as float32 arrays) and proves the pause cuts in
±3 s windows around each cut. These are also the first unit tests of detect_pauses and verify_cuts. Whisper is replaced
by a fake reader that "hears" tone bursts (one frequency = one word), so the two-reading cut proof runs for real.

The 60-minute memory test is slow (≈ 1-2 min): it runs only with WHYNOT_SLOW_TESTS=1.
"""
import sys as _sys
_sys.dont_write_bytecode = True
import _isolation  # noqa: F401,E402  G79: sandbox the engine home first (tests/_isolation.py)
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
import wave
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import numpy as np

SK = Path(__file__).resolve().parents[1]
ENGINE = SK / "engine" / "reel"
sys.path.insert(0, str(ENGINE))

from lib import audio_clean as AC  # noqa: E402
from lib import common  # noqa: E402
from lib.common import Paths, read_json, write_json  # noqa: E402

SR = 48000


# --------------------------------------------------------------------------- fixtures
def write_wav(path: Path, x: np.ndarray, sr: int = SR):
    x = x if x.ndim == 2 else x[:, None]
    with wave.open(str(path), "wb") as w:
        w.setnchannels(x.shape[1]); w.setsampwidth(2); w.setframerate(sr)
        w.writeframes((np.clip(x, -1, 1) * 32767).astype("<i2").tobytes())


def read_i16(path: Path) -> np.ndarray:
    with wave.open(str(path)) as w:
        return np.frombuffer(w.readframes(w.getnframes()), dtype="<i2").reshape(-1, w.getnchannels())


def label_hz(label: str) -> int:
    return 400 + 100 * int(label[1:])          # w1 = 500 Hz ... w12 = 1600 Hz


def tone_audio(words, dur_s: float, amp: float = 0.3, noise: float = 1e-4, seed: int = 0) -> np.ndarray:
    """Synthetic 'speech': each word is a tone burst at its own frequency, 5 ms ramps, on a faint noise floor."""
    rng = np.random.default_rng(seed)
    x = rng.normal(0, noise, int(dur_s * SR)).astype(np.float32)
    for lab, t0, ln, *a in words:
        i0, n = int(t0 * SR), int(ln * SR)
        t = np.arange(n) / SR
        env = np.minimum(1, np.minimum(np.arange(n), n - 1 - np.arange(n)) / (0.005 * SR))
        x[i0:i0 + n] += ((a[0] if a else amp) * env * np.sin(2 * np.pi * label_hz(lab) * t)).astype(np.float32)
    return x


def phrases(n_phr: int = 12, start: float = 0.3, every: float = 3.2):
    """n_phr phrases of 4 words (300 ms bursts every 500 ms), 1.4 s pauses between phrases."""
    out, k = [], 0
    for p in range(n_phr):
        for j in range(4):
            out.append((f"w{k % 12 + 1}", start + every * p + 0.5 * j, 0.3))
            k += 1
    return out


class ToneReader:
    """Fake faster-whisper model: reads 16 kHz audio, one word per tone burst (>= 100 ms), labelled by frequency."""

    def __init__(self):
        self.calls = []

    def transcribe(self, audio, **opts):
        self.calls.append((len(audio) / 16000, opts))
        hop = 160
        n = len(audio) // hop
        env = np.sqrt((np.asarray(audio[:n * hop], dtype=np.float64).reshape(n, hop) ** 2).mean(axis=1)) if n else np.zeros(0)
        on = env > 0.05
        words, i = [], 0
        while i < n:
            if on[i]:
                j = i
                while j < n and on[j]:
                    j += 1
                if j - i >= 10:
                    seg = np.asarray(audio[i * hop:j * hop], dtype=np.float64)
                    f = np.argmax(np.abs(np.fft.rfft(seg))) * 16000 / len(seg)
                    words.append(SimpleNamespace(word=f" w{int(round((f - 400) / 100))}", start=i / 100, end=j / 100))
                i = j
            else:
                i += 1
        segs = [SimpleNamespace(text="".join(w.word for w in words), words=words)] if words else []
        return iter(segs), None


def make_project(tmp: Path, video_id: str = "VID1") -> Paths:
    root = tmp / "CLIENT"
    for d in ("assets/Brand", "data/Raw"):
        (root / d).mkdir(parents=True)
    common.set_context(root)
    p = Paths(root, video_id)
    p.ensure_project()
    p.p("06_audio/dialogue").mkdir(parents=True, exist_ok=True)
    return p


def write_transcript(p: Paths, words, dur_ms: int):
    """transcript.json + words.json straight from the word list (no finalize: no caption files needed here)."""
    ws = [{"id": i + 1, "segment_id": 1, "word": lab, "start_ms": int(round(t0 * 1000)),
           "end_ms": int(round((t0 + ln) * 1000)), "probability": 0.9} for i, (lab, t0, ln, *_) in enumerate(words)]
    meta = {"language": "ar", "duration_ms": dur_ms, "initial_prompt": None}
    segs = [{"id": 1, "start_ms": ws[0]["start_ms"] if ws else 0, "end_ms": ws[-1]["end_ms"] if ws else dur_ms,
             "text": " ".join(w["word"] for w in ws), "words": [w["id"] for w in ws]}]
    write_json(p.p("02_transcription/transcript.json"), {"meta": meta, "segments": segs})
    write_json(p.p("02_transcription/words.json"), {"meta": meta, "words": ws})


def gap_cuts(words, pad_ms: int = 80):
    """keep_ms that remove every inter-phrase pause (gap >= 1 s) minus pad, like detect_pauses would."""
    keep, t = [], 0
    for (_, a0, al, *_), (_, b0, _, *_) in zip(words, words[1:]):
        e, s = int(round((a0 + al) * 1000)), int(round(b0 * 1000))
        if s - e >= 1000:
            keep.append([t, e + pad_ms])
            t = s - pad_ms
    return keep, t


def old_tight(x: np.ndarray, keep_ms) -> np.ndarray:
    """The pre-3.0 construction of dialogue_tight_check.wav (whole file in memory), the reference."""
    parts = [x[int(a * SR / 1000):int(b * SR / 1000)].copy() for a, b in keep_ms]
    xf = int(0.01 * SR)
    for i in range(1, len(parts)):
        parts[i - 1][-xf:] *= np.linspace(1, 0, xf)
        parts[i][:xf] *= np.linspace(0, 1, xf)
    return (np.clip(np.concatenate(parts), -1, 1) * 32767).astype(np.int16)


def old_assess(x: np.ndarray) -> dict:
    """The pre-3.0 assess_source + detect_hum (whole file in float32 memory), the reference."""
    def rms_db(v):
        return float(20 * np.log10(np.sqrt(np.mean(v ** 2)) + 1e-9))

    def win_db(v, hop=SR // 20):
        n = len(v) // hop
        return 20 * np.log10(np.sqrt((v[:n * hop].reshape(n, hop) ** 2).mean(axis=1)) + 1e-9)

    def hum(mono, max_hz=500):
        hop = SR // 20
        n = len(mono) // hop
        win = mono[:n * hop].reshape(n, hop)
        d = 20 * np.log10(np.sqrt((win ** 2).mean(axis=1)) + 1e-9)
        quiet = win[d <= np.percentile(d, 20)].reshape(-1)
        if len(quiet) < 2 * SR:
            quiet = mono
        k = len(quiet) // SR
        spec = np.mean([np.abs(np.fft.rfft(quiet[i * SR:(i + 1) * SR] * np.hanning(SR))) for i in range(k)], axis=0) + 1e-12
        best = None
        for mains in (50, 60):
            prom = {}
            for h in range(mains, max_hz + 1, mains):
                nb = np.r_[spec[max(1, h - 15):h - 3], spec[h + 4:h + 16]]
                prom[h] = round(float(20 * np.log10(spec[h - 1:h + 2].max() / np.median(nb))), 1)
            score = sum(v for v in prom.values() if v >= 10.0)
            if best is None or score > best[0]:
                best = (score, mains, prom)
        score, mains, prom = best
        return {"mains_hz": mains if score else None, "notch_hz": [h for h, v in prom.items() if v >= 10.0 and h >= 90],
                "prominence_db": prom}

    ch = x.shape[1]
    identical = ch >= 2 and rms_db(x[:, 0] - x[:, 1]) - max(rms_db(x[:, 0]), rms_db(x[:, 1])) < -30
    mono = x[:, 0] if ch == 1 or identical else x.mean(axis=1)
    d = win_db(mono)
    floor, speech = float(np.percentile(d, 10)), float(np.percentile(d, 90))
    return {"channels": ch, "identical_channels": bool(identical), "noise_floor_db": round(floor, 1),
            "speech_level_db": round(speech, 1), "speech_to_noise_db": round(speech - floor, 1),
            "already_clean": speech - floor >= 40.0, "hum": hum(mono)}


class _Proj(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.p = make_project(self.tmp)

    def tearDown(self):
        common.set_context(None)
        shutil.rmtree(self.tmp, ignore_errors=True)


# --------------------------------------------------------------------------- streaming = in-memory
class TestStreamingEquivalence(_Proj):
    def test_iter_blocks_and_win_db_match_whole_file(self):
        rng = np.random.default_rng(3)
        x = (rng.normal(0, 0.1, (SR * 3 + 777, 2))).astype(np.float32)
        f = self.tmp / "s.wav"
        write_wav(f, x)
        whole = AC._read_stereo(f)
        with mock.patch.object(AC, "BLOCK", 28800):          # 0.6 s blocks: windows cross many block edges
            blocks = list(AC._iter_blocks(f))
            self.assertTrue(all(len(b) == 28800 for b in blocks[:-1]))
            np.testing.assert_array_equal(np.concatenate(blocks), whole)
            for hop in (480, 2400):
                d, n = AC._stream_win_db(lambda: AC._iter_blocks(f), hop)
                self.assertEqual(n, len(whole))
                np.testing.assert_array_equal(d, AC._win_db(whole[:, 0], hop=hop))

    def test_cut_proof_resampling_is_whisper_audio(self):
        from lib.transcribe import whisper_audio
        x = (0.2 * np.random.default_rng(4).normal(size=SR * 3 + 123)).astype(np.float32)
        f = self.tmp / "r.wav"
        write_wav(f, x)
        np.testing.assert_array_equal(AC._to16k(x), whisper_audio(f))   # in-process, bit-identical to ffmpeg's

    def test_assess_streamed_equals_in_memory(self):
        n = SR * 6
        t = np.arange(n) / SR
        rng = np.random.default_rng(1)
        speech = (np.sin(2 * np.pi * 220 * t) * 0.3) * (np.sin(2 * np.pi * 0.5 * t) > 0)
        hum = sum(0.004 * np.sin(2 * np.pi * h * t) for h in (100, 150, 200))
        a = (speech + hum + rng.normal(0, 0.0005, n)).astype(np.float32)
        b = rng.normal(0, 0.05, n).astype(np.float32)
        for x in (np.stack([a, a], axis=1), np.stack([a, b], axis=1), a[:, None]):
            f = self.tmp / "a.wav"
            write_wav(f, x)
            xr = AC._read_stereo(f)
            ref = json.dumps(old_assess(xr), sort_keys=True)
            self.assertEqual(json.dumps(AC.assess_source(xr), sort_keys=True), ref)
            with mock.patch.object(AC, "BLOCK", 28800):
                blocks = lambda: AC._iter_blocks(f)          # noqa: E731
                got = AC._assess(blocks, AC._scan(blocks))
            self.assertEqual(json.dumps(got, sort_keys=True), ref)
        self.assertEqual(AC.assess_source(np.stack([a, a], axis=1))["hum"]["mains_hz"], 50)

    def test_channel_plan_matches_old_formula(self):
        rng = np.random.default_rng(2)
        n = SR * 5
        x = np.stack([rng.normal(0, 0.01, n), rng.normal(0, 0.01, n)], axis=1).astype(np.float32)
        x[SR:2 * SR, 0] += 0.3 * np.sin(np.arange(SR) / 7)        # seg 1 loud on ch1
        x[3 * SR:4 * SR, 1] += 0.3 * np.sin(np.arange(SR) / 7)    # seg 2 loud on ch2
        segs = [{"id": 1, "start_ms": 1000, "end_ms": 2000, "text": "a"},
                {"id": 2, "start_ms": 3000, "end_ms": 4000, "text": "b"}]
        floors = [float(np.percentile(AC._win_db(x[:, c]), 10)) for c in range(2)]
        ref = []
        for s in segs:                                           # the pre-3.0 choose_channels, in memory
            a, b = int(s["start_ms"] * SR / 1000), int(s["end_ms"] * SR / 1000)
            snr = [AC._rms_db(x[a:b, c]) - floors[c] for c in range(2)]
            ref.append((int(np.argmax(snr)) + 1, [round(v, 1) for v in snr]))
        with mock.patch.object(AC, "BLOCK", 28800):
            sc = AC._scan(AC._array_blocks(x), segs)
        got = [(q["channel"], q["snr_db"]) for q in AC._channel_plan(segs, sc, 2)]
        self.assertEqual(got, ref)
        self.assertEqual([g[0] for g in got], [1, 2])

    def test_crossfade_weights_match_convolution(self):
        n = 50000
        regions = [(0, 300, 1), (300, 610, 2), (610, 800, 1), (800, 1042, 2)]   # last ch2 region runs past the end
        w = np.zeros(n, dtype=np.float32)
        for ra, rb, c in regions:
            if c == 2:
                w[int(ra * SR / 1000):min(n, int(rb * SR / 1000))] = 1.0
        xf = int(0.04 * SR)
        ref = np.convolve(w, np.ones(xf, dtype=np.float32) / xf, mode="same")
        got = np.concatenate([AC._xfade_weights(regions, n, a, min(n, a + 7000)) for a in range(0, n, 7000)])
        np.testing.assert_allclose(got, ref, atol=2e-6)

    def test_clean_same_result_for_any_block_size(self):
        n = SR * 6
        t = np.arange(n) / SR
        rng = np.random.default_rng(5)
        on1 = (t < 3).astype(np.float32)
        x = np.stack([0.3 * np.sin(2 * np.pi * 220 * t) * on1 + 0.004 * np.sin(2 * np.pi * 100 * t),
                      0.3 * np.sin(2 * np.pi * 330 * t) * (1 - on1)], axis=1).astype(np.float32)
        x += rng.normal(0, 0.002, x.shape).astype(np.float32)
        src = self.p.data / "Raw" / "C1.wav"
        write_wav(src, x)
        words = [("w1", 0.5, 0.3), ("w2", 1.5, 0.3), ("w3", 3.5, 0.3), ("w4", 4.5, 0.3)]
        write_transcript(self.p, words, 6000)
        tj = read_json(self.p.p("02_transcription/transcript.json"))
        tj["segments"] = [{"id": 1, "start_ms": 400, "end_ms": 2900, "text": "w1 w2", "words": [1, 2]},
                          {"id": 2, "start_ms": 3400, "end_ms": 5900, "text": "w3 w4", "words": [3, 4]}]
        write_json(self.p.p("02_transcription/transcript.json"), tj)
        outs = []
        for block in (AC.BLOCK, 28800):
            with mock.patch.object(AC, "BLOCK", block):
                r = AC.clean(self.p, src)
            r.pop("generated")
            outs.append((json.dumps(r, sort_keys=True), self.p.p("06_audio/dialogue/dialogue_clean.wav").read_bytes()))
        self.assertEqual([q["channel"] for q in json.loads(outs[0][0])["channel_plan"]], [1, 2])
        self.assertEqual(outs[0][0], outs[1][0])
        self.assertEqual(outs[0][1], outs[1][1])


# --------------------------------------------------------------------------- detect_pauses
class TestDetectPauses(_Proj):
    def _setup(self, words, dur_s=40.0):
        write_wav(self.p.p("06_audio/dialogue/dialogue_clean.wav"), np.repeat(tone_audio(words, dur_s)[:, None], 2, axis=1))
        write_transcript(self.p, [w for w in words if len(w) == 3], int(dur_s * 1000))   # quiet bursts: no word

    def test_cuts_the_pauses_between_phrases_only(self):
        words = phrases()
        self._setup(words)
        r = AC.detect_pauses(self.p)
        self.assertEqual(r["source_duration_ms"], 40000)
        self.assertEqual(r["cuts_ms"][0], (0, 220))                   # lead-in: 300 ms - 80 ms breath, from 0
        self.assertEqual(r["cuts_ms"][-1][1], 40000)                  # tail runs to the end (no pad there)
        inner = r["cuts_ms"][1:-1]
        self.assertEqual(len(inner), 11)                              # one per gap between 12 phrases
        for k, (cs, ce) in enumerate(inner):
            gap0, gap1 = (0.3 + 3.2 * k + 1.8) * 1000, (0.3 + 3.2 * (k + 1)) * 1000
            self.assertAlmostEqual(cs, gap0 + 80, delta=20)
            self.assertAlmostEqual(ce, gap1 - 80, delta=20)
        for cs, ce in r["cuts_ms"]:                                   # never inside a burst (word)
            for _, t0, ln in words:
                self.assertFalse(cs < (t0 + ln) * 1000 and ce > t0 * 1000, (cs, ce, t0))
        keep = r["keep_ms"]                                           # keep = the complement of the cuts
        self.assertEqual(keep[0][0], 220)
        self.assertEqual(sum(b - a for a, b in keep) + r["removed_ms"], 40000)
        self.assertEqual(r["new_duration_ms"], 40000 - r["removed_ms"])
        self.assertEqual(read_json(self.p.p("06_audio/dialogue/pauses.json"))["cuts_ms"],
                         [list(c) for c in r["cuts_ms"]])

    def test_min_pause_and_pad(self):
        self._setup(phrases())
        r = AC.detect_pauses(self.p, min_pause_ms=1500)              # 1.4 s gaps are not pauses any more
        self.assertEqual(len(r["cuts_ms"]), 1)
        self.assertEqual(r["cuts_ms"][0][1], 40000)
        r = AC.detect_pauses(self.p, pad_ms=200)
        cs, ce = r["cuts_ms"][1]
        self.assertAlmostEqual(cs, (0.3 + 1.8) * 1000 + 200, delta=20)
        self.assertAlmostEqual(ce, 3500 - 200, delta=20)

    def test_quiet_word_core_is_never_cut(self):
        # a whispered word (below the threshold) in the middle of a pause: its core splits the pause in two;
        # a "word" longer than 500 ms over a pause is a stretched timestamp and does not protect anything
        words = phrases(3) + [("w3", 2.45, 0.3, 2e-4)]
        self._setup(words, dur_s=10.0)
        ws = read_json(self.p.p("02_transcription/words.json"))
        ws["words"] += [{"id": 99, "word": "hush", "start_ms": 2450, "end_ms": 2750, "segment_id": 1},
                        {"id": 100, "word": "long", "start_ms": 5300, "end_ms": 6300, "segment_id": 1}]
        write_json(self.p.p("02_transcription/words.json"), ws)
        r = AC.detect_pauses(self.p)
        core = (2450 + 60, 2750 - 60)
        for cs, ce in r["cuts_ms"]:
            self.assertFalse(cs < core[1] and ce > core[0], (cs, ce))
        self.assertTrue(any(ce <= core[0] for cs, ce in r["cuts_ms"] if cs > 2000))   # cut before the core
        self.assertTrue(any(cs >= core[1] for cs, ce in r["cuts_ms"] if ce < 3500))   # and after it
        self.assertTrue(any(cs < 5800 < ce for cs, ce in r["cuts_ms"]))                # the long "word" is cut

    def test_block_size_does_not_change_the_result(self):
        self._setup(phrases())
        a = AC.detect_pauses(self.p)
        with mock.patch.object(AC, "BLOCK", 28800):
            b = AC.detect_pauses(self.p)
        a.pop("generated"); b.pop("generated")
        self.assertEqual(a, b)


# --------------------------------------------------------------------------- verify_cuts
class TestVerifyCuts(_Proj):
    def setUp(self):
        super().setUp()
        self.words = phrases()
        self.x = tone_audio(self.words, 40.0)
        write_wav(self.p.p("06_audio/dialogue/dialogue_clean.wav"), np.repeat(self.x[:, None], 2, axis=1))
        write_transcript(self.p, self.words, 40000)
        self.reader = ToneReader()
        self.models = []
        patcher = mock.patch("lib.transcribe.whisper_model", side_effect=self._model)
        patcher.start()
        self.addCleanup(patcher.stop)

    def _model(self, *a, **k):
        self.models.append(a)
        return self.reader, "cpu", "int8"

    def _pauses(self, keep):
        write_json(self.p.p("06_audio/dialogue/pauses.json"), {"keep_ms": keep, "source_duration_ms": 40000})

    def _gap_keep(self):
        keep, t = gap_cuts(self.words)
        return keep + [[t, 40000]]

    def test_clean_cuts_pass_with_two_identical_readings(self):
        keep = self._gap_keep()
        self._pauses(keep)
        r = AC.verify_cuts(self.p)
        self.assertTrue(r["ok"], r)
        self.assertEqual(r["missing"], [])
        self.assertEqual(r["cuts"], 11)
        self.assertGreaterEqual(r["coverage"], 0.85)
        self.assertEqual(r["orig_words"], 48)        # each word counted once, also where two windows share a keep
        self.assertGreaterEqual(r["tight_words"], 48)
        self.assertTrue(all(w["uncut_words"] and not w["short_audio"] for w in r["windows"]), r["windows"])
        self.assertEqual((r["windows_without_words"], r["windows_short_audio"]), ([], []))
        # G57: both readings deterministic and identical in settings (temperature 0, same hint, same model)
        opts = [o for _, o in self.reader.calls]
        self.assertEqual(len(opts) % 2, 0)
        self.assertTrue(all(o == opts[0] for o in opts))
        self.assertEqual(opts[0]["temperature"], 0.0)
        self.assertFalse(opts[0]["condition_on_previous_text"])
        self.assertEqual(len(self.models), 1)
        # every reading (uncut and cut) stays <= 20 s: Whisper never gets a long decode it could skip through
        self.assertTrue(all(d <= 20.01 for d, _ in self.reader.calls), self.reader.calls)
        # the tightened check file is still written, sample-identical to the old whole-file construction
        got = read_i16(self.p.p("06_audio/dialogue/dialogue_tight_check.wav"))[:, 0]
        ref = old_tight(AC._read_stereo(self.p.p("06_audio/dialogue/dialogue_clean.wav"))[:, 0], keep)
        np.testing.assert_array_equal(got, ref)

    def test_only_three_seconds_around_each_cut_are_read(self):
        keep = self._gap_keep()
        k5 = keep[5]                                   # one cut only: the pause after phrase 5
        self._pauses([[0, k5[1]], [keep[6][0], 40000]])
        r = AC.verify_cuts(self.p)
        self.assertTrue(r["ok"], r)
        self.assertEqual((r["cuts"], r["chunks"]), (1, 1))
        lo, hi = r["windows_ms"][0]
        self.assertLessEqual(lo, k5[1] - 3000)        # >= 3 s of uncut audio before the cut ...
        self.assertGreaterEqual(hi, keep[6][0] + 3000)  # ... and after it
        self.assertLess(hi - lo, 9000)
        base_s = self.reader.calls[0][0]
        self.assertAlmostEqual(base_s, (hi - lo) / 1000, delta=0.01)
        self.assertLess(r["orig_words"], 16)          # 48 words in the clip, only the window's are read
        with mock.patch.object(AC, "BLOCK", 28800):   # streaming block size does not matter
            r2 = AC.verify_cuts(self.p)
        self.assertEqual({k: r[k] for k in ("ok", "coverage", "orig_words", "windows_ms", "missing")},
                         {k: r2[k] for k in ("ok", "coverage", "orig_words", "windows_ms", "missing")})

    def test_word_heard_in_the_silent_pause_is_not_called_lost_speech(self):
        keep = self._gap_keep()
        one = [[0, keep[5][1]], [keep[6][0], 40000]]
        self._pauses(one)
        lo = AC._cut_windows(one, read_json(self.p.p("02_transcription/words.json"))["words"], 40000)[0]["lo"]
        cut_mid = (keep[5][1] + keep[6][0]) / 2
        read, n = self.reader.transcribe, [0]

        def ghost(audio, **o):          # the uncut reading "hears" a word in the removed (silent) pause
            segs = list(read(audio, **o)[0])
            n[0] += 1
            if n[0] == 1:
                t = (cut_mid - lo) / 1000
                segs.append(SimpleNamespace(text=" w11", words=[SimpleNamespace(word=" w11", start=t, end=t + 0.2)]))
            return iter(segs), None
        self.reader.transcribe = ghost
        r = AC.verify_cuts(self.p)
        self.assertEqual(r["missing"], [])
        self.assertEqual([h["words"] for h in r["possible_hallucinations"]], ["w11"])
        self.assertFalse(r["ok"])                     # never a pass: the editor listens
        self.assertIn("possible hallucination", r["verdict"])

    def test_window_edges_do_not_split_a_word(self):
        keep = self._gap_keep()
        self._pauses([[0, keep[5][1]], [keep[6][0], 40000]])
        r = AC.verify_cuts(self.p)
        lo, hi = r["windows_ms"][0]
        for _, t0, ln in self.words:
            a, b = t0 * 1000, (t0 + ln) * 1000
            self.assertFalse(a < lo < b or a < hi < b, (lo, hi, a, b))

    def _bad_keep(self):
        keep = self._gap_keep()
        _, t0, ln = self.words[21]                   # 2nd word of phrase 5 (inside a phrase, not a pause)
        a, b = int(t0 * 1000) - 50, int((t0 + ln) * 1000) + 50
        bad = []
        for ka, kb in keep:
            if ka < a and kb > b:
                bad += [[ka, a], [b, kb]]
            else:
                bad.append([ka, kb])
        self._pauses(bad)
        return a, b

    def test_a_cut_through_a_word_is_caught(self):
        self._bad_keep()
        r = AC.verify_cuts(self.p)
        self.assertFalse(r["ok"])
        self.assertEqual([m["words"] for m in r["missing"]], [self.words[21][0]])
        self.assertTrue(r["missing"][0]["cuts_nearby"])
        self.assertEqual(r["cuts"], 12)

    def test_protected_pause_is_not_cut_or_tested(self):
        a, b = self._bad_keep()
        write_json(self.p.p("01_analysis/edit-decisions.json"),
                   {"global": {"remove_pauses": {"protect": [[a - 10, b + 10]]}}, "decisions": []})
        r = AC.verify_cuts(self.p)
        self.assertTrue(r["ok"], r)
        self.assertEqual(r["protected_ranges_ms"], [[a - 10, b + 10]])
        self.assertEqual(r["cuts"], 11)

    def test_lead_in_and_tail_cuts_are_proved_too(self):
        keep = self._gap_keep()
        keep[0][0], keep[-1][1] = 220, 39500                 # clean lead-in and tail cuts: nothing lost
        self._pauses(keep)
        r = AC.verify_cuts(self.p)
        self.assertTrue(r["ok"], r)
        self.assertEqual(r["cuts"], 13)
        self.assertEqual((r["windows_ms"][0][0], r["windows_ms"][-1][1]), (0, 40000))
        keep[0][0] = 700                                       # a lead-in cut that eats the first word
        self._pauses(keep)
        r = AC.verify_cuts(self.p)
        self.assertFalse(r["ok"])
        self.assertEqual([m["words"] for m in r["missing"]], ["w1"])

    def test_no_cuts_nothing_to_prove(self):
        self._pauses([[0, 40000]])
        r = AC.verify_cuts(self.p)
        self.assertTrue(r["ok"])
        self.assertEqual((r["cuts"], r["missing"]), (0, []))
        self.assertEqual(self.models, [])            # Whisper is not even loaded
        self.assertTrue(read_json(self.p.p("06_audio/dialogue/cut-verification.json"))["ok"])

    def test_dense_cuts_share_windows_capped_at_20s(self):
        keep = self._gap_keep()
        self._pauses(keep)
        r = AC.verify_cuts(self.p)
        self.assertGreater(r["chunks"], 1)
        self.assertLess(r["chunks"], r["cuts"])      # neighbouring cuts are read together
        for lo, hi in r["windows_ms"]:
            self.assertLessEqual(hi - lo, 20000)    # the uncut reading too (it also holds the removed pauses)
        covered = [any(lo <= ka - 1 and kb + 1 <= hi for lo, hi in r["windows_ms"])
                   for ka, kb in zip([k[1] for k in keep[:-1]], [k[0] for k in keep[1:]])]
        self.assertTrue(all(covered), covered)       # every cut sits inside a window


class TestLongRemovedSpans(_Proj):
    """A single cut that removes a long span is read uncut in <= 20 s pieces (G24: a long decode lets Whisper skip
    speech); windows that heard nothing or run past the audio are not proved."""
    DUR = 115.0

    def setUp(self):
        super().setUp()
        self.reader = ToneReader()
        patcher = mock.patch("lib.transcribe.whisper_model", side_effect=lambda *a, **k: (self.reader, "cpu", "int8"))
        patcher.start()
        self.addCleanup(patcher.stop)

    def _clip(self, mid_phrase: bool):
        words = phrases(4) + ([(f"w{j + 5}", 50.0 + 0.5 * j, 0.3) for j in range(4)] if mid_phrase else []) + \
            phrases(6, start=90.3)
        write_wav(self.p.p("06_audio/dialogue/dialogue_clean.wav"),
                  np.repeat(tone_audio(words, self.DUR)[:, None], 2, axis=1))
        write_transcript(self.p, words, int(self.DUR * 1000))
        return words

    def _verify(self, keep, dur_ms=None):
        write_json(self.p.p("06_audio/dialogue/pauses.json"),
                   {"keep_ms": keep, "source_duration_ms": dur_ms or int(self.DUR * 1000)})
        return AC.verify_cuts(self.p)

    def test_twenty_second_silence_removed_in_pieces(self):
        self._clip(mid_phrase=True)
        r = self._verify([[0, 13000], [33000, 115000]])
        self.assertTrue(r["ok"], r)
        self.assertGreater(r["windows_ms"][0][1] - r["windows_ms"][0][0], 20000)
        self.assertEqual(r["windows"][0]["pieces"], 2)
        self.assertTrue(all(d <= 20.01 for d, _ in self.reader.calls), self.reader.calls)

    def test_seventy_four_seconds_removed_with_speech_inside_is_caught(self):
        self._clip(mid_phrase=True)
        r = self._verify([[0, 13000], [87000, 115000]])
        self.assertFalse(r["ok"])
        self.assertEqual(sorted(m["words"] for m in r["missing"] if m.get("heard_inside_removed_span")),
                         ["w5", "w6", "w7", "w8"])
        self.assertGreaterEqual(r["windows"][0]["pieces"], 4)
        self.assertTrue(all(d <= 20.01 for d, _ in self.reader.calls), self.reader.calls)
        # the cut reading of a multi-piece window is only the kept context, joined: 3.2 s + 3 s
        self.assertAlmostEqual(self.reader.calls[-1][0], 6.2, delta=0.05)

    def test_seventy_four_seconds_of_silence_removed_passes(self):
        self._clip(mid_phrase=False)
        r = self._verify([[0, 13000], [87000, 115000]])
        self.assertTrue(r["ok"], r)
        self.assertTrue(all(d <= 20.01 for d, _ in self.reader.calls), self.reader.calls)

    def _splits(self, keep):
        words = read_json(self.p.p("02_transcription/words.json"))["words"]
        win = AC._cut_windows(keep, words, int(self.DUR * 1000))[0]
        return [q[3] for q in win["pieces"][:-1]]

    def test_word_on_a_split_point_is_caught_and_counted_once(self):
        keep = [[0, 13000], [87000, 115000]]
        self._clip(mid_phrase=False)
        splits = self._splits(keep)
        # a 160 ms word centred on one split (half of it in each piece without the overlap: too short to be heard)
        # and a 300 ms word on another (heard whole by both overlapping pieces: must count once)
        words = phrases(4) + [("w9", splits[0] / 1000 - 0.08, 0.16), ("w10", splits[1] / 1000 - 0.15, 0.3)] + \
            phrases(6, start=90.3)
        write_wav(self.p.p("06_audio/dialogue/dialogue_clean.wav"),
                  np.repeat(tone_audio(words, self.DUR)[:, None], 2, axis=1))
        write_transcript(self.p, words, int(self.DUR * 1000))
        self.assertEqual(self._splits(keep), splits)
        r = self._verify(keep)
        self.assertFalse(r["ok"])
        self.assertEqual(sorted(m["words"] for m in r["missing"] if m.get("heard_inside_removed_span")), ["w10", "w9"])
        self.assertTrue(all(d <= 20.01 for d, _ in self.reader.calls), self.reader.calls)
        pieces = r["windows"][0]["pieces_ms"]
        self.assertTrue(all(a[1] - b[0] >= 900 for a, b in zip(pieces, pieces[1:])), pieces)   # 1 s overlaps

    def test_word_heard_in_silence_is_a_possible_hallucination(self):
        self._clip(mid_phrase=False)
        read = self.reader.transcribe

        def hallucinating(audio, **o):
            segs, info = read(audio, **o)
            segs = list(segs)
            if len(audio) / 16000 > 15:   # the long uncut pieces: Whisper "hears" a word in the silence
                segs.append(SimpleNamespace(text=" w11", words=[SimpleNamespace(word=" w11", start=8.0, end=8.3)]))
            return iter(segs), info
        self.reader.transcribe = hallucinating
        r = self._verify([[0, 13000], [87000, 115000]])
        self.assertFalse(r["ok"])
        self.assertEqual(r["missing"], [])
        self.assertTrue(r["possible_hallucinations"])
        self.assertTrue(all(h["level_db"] < -70 for h in r["possible_hallucinations"]))
        self.assertIn("possible hallucination", r["verdict"])

    def test_window_that_heard_nothing_is_not_proved(self):
        self._clip(mid_phrase=False)
        r = self._verify([[0, 30000], [31000, 115000]])        # a cut deep inside the silence
        self.assertFalse(r["ok"])
        self.assertEqual(r["windows_without_words"], [[27000, 34000]])
        self.assertIn("heard no word", r["verdict"])

    def test_pauses_past_the_end_of_the_audio_are_not_proved(self):
        self._clip(mid_phrase=False)
        r = self._verify([[0, 112000]], dur_ms=130000)          # pauses.json says 130 s, the file has 115 s
        self.assertFalse(r["ok"])
        self.assertEqual(len(r["windows_short_audio"]), 1)
        self.assertIn("past the end of the audio", r["verdict"])

    def test_a_failing_proof_closes_its_files(self):
        self._clip(mid_phrase=False)
        self.reader.transcribe = mock.Mock(side_effect=RuntimeError("CUDA failed"))
        with self.assertRaises(RuntimeError):
            self._verify([[0, 13000], [33000, 115000]])
        # Windows refuses to delete a file a handle still holds: the wave writer and the PyAV reader are closed
        self.p.p("06_audio/dialogue/dialogue_tight_check.wav").unlink()
        self.p.p("06_audio/dialogue/dialogue_clean.wav").unlink()


# --------------------------------------------------------------------------- 60-minute memory budget
HARNESS = r"""
import json, sys, time
sys.path.insert(0, sys.argv[1])
from pathlib import Path
from lib import common, transcribe
from lib.common import Paths

def peak_rss():
    try:
        import psutil
        mi = psutil.Process().memory_info()
        if hasattr(mi, "peak_wset"):
            return mi.peak_wset
    except ImportError:
        pass
    if sys.platform == "win32":
        import ctypes
        from ctypes import wintypes as wt
        class PMC(ctypes.Structure):
            _fields_ = [("cb", wt.DWORD), ("PageFaultCount", wt.DWORD)] + [(n, ctypes.c_size_t) for n in (
                "PeakWorkingSetSize", "WorkingSetSize", "QuotaPeakPagedPoolUsage", "QuotaPagedPoolUsage",
                "QuotaPeakNonPagedPoolUsage", "QuotaNonPagedPoolUsage", "PagefileUsage", "PeakPagefileUsage")]
        c = PMC(); c.cb = ctypes.sizeof(c)
        k32 = ctypes.windll.kernel32
        k32.GetCurrentProcess.restype = wt.HANDLE
        ctypes.windll.psapi.GetProcessMemoryInfo.argtypes = [wt.HANDLE, ctypes.POINTER(PMC), wt.DWORD]
        ctypes.windll.psapi.GetProcessMemoryInfo(k32.GetCurrentProcess(), ctypes.byref(c), c.cb)
        return c.PeakWorkingSetSize
    import resource
    r = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return r if sys.platform == "darwin" else r * 1024

class Silent:   # fake Whisper: the memory budget is about the audio, not the model
    def transcribe(self, audio, **kw):
        return iter([]), None

transcribe.whisper_model = lambda *a, **k: (Silent(), "cpu", "int8")
root, vid, src = Path(sys.argv[2]), sys.argv[3], Path(sys.argv[4])
common.set_context(root)
p = Paths(root, vid)
from lib.audio_clean import clean, detect_pauses, verify_cuts
t = time.time(); r = clean(p, src); t1 = time.time()
q = detect_pauses(p); t2 = time.time()
v = verify_cuts(p); t3 = time.time()
print(json.dumps({"peak_rss": peak_rss(), "clean_s": round(t1 - t, 1), "pauses_s": round(t2 - t1, 1),
                  "verify_s": round(t3 - t2, 1), "total_s": round(t3 - t, 1), "cuts": len(q["cuts_ms"]),
                  "duration_ms": q["source_duration_ms"], "windows": v.get("chunks"),
                  "spectrograms": all(Path(f).stat().st_size > 0 for f in r["metrics"]["spectrograms"]),
                  "mics": sorted({q["channel"] for q in r["channel_plan"]})}))
"""


@unittest.skipUnless(os.environ.get("WHYNOT_SLOW_TESTS") == "1", "set WHYNOT_SLOW_TESTS=1 for the 60-minute memory test")
class TestLongClipMemory(_Proj):
    MINUTES = 60
    BUDGET = 1.5 * 1024 ** 3

    def test_sixty_minutes_under_budget(self):
        d = self.MINUTES * 60
        src = self.p.data / "Raw" / "LONG.wav"
        # mono 48 kHz: a 220 Hz "voice" 3 s on / 1 s off over a faint noise floor -> one pause every 4 s
        subprocess.run([common.ffmpeg_exe(), "-y", "-loglevel", "error",
                        "-f", "lavfi", "-i", f"sine=f=220:r=48000:d={d}",
                        "-f", "lavfi", "-i", f"anoisesrc=r=48000:a=0.002:d={d}:seed=7",
                        "-filter_complex", "[0]volume=0.3,volume='lt(mod(t,4),3)':eval=frame[s];"
                                           "[s][1]amix=inputs=2:normalize=0",
                        "-ac", "1", "-c:a", "pcm_s16le", str(src)], check=True)
        self._run(src, d, [1])

    def test_sixty_minutes_two_mics_under_budget(self):
        d = self.MINUTES * 60
        src = self.p.data / "Raw" / "LONG2.wav"
        # stereo 48 kHz, two different mics taking turns (4 s each): every switch is a crossfaded splice
        subprocess.run([common.ffmpeg_exe(), "-y", "-loglevel", "error",
                        "-f", "lavfi", "-i", f"sine=f=220:r=48000:d={d}",
                        "-f", "lavfi", "-i", f"sine=f=330:r=48000:d={d}",
                        "-f", "lavfi", "-i", f"anoisesrc=r=48000:a=0.002:d={d}:seed=7",
                        "-f", "lavfi", "-i", f"anoisesrc=r=48000:a=0.002:d={d}:seed=8",
                        "-filter_complex", "[0]volume=0.3,volume='lt(mod(t,8),3)':eval=frame[a];"
                                           "[1]volume=0.3,volume='between(mod(t,8),4,7)':eval=frame[b];"
                                           "[a][2]amix=inputs=2:normalize=0[l];[b][3]amix=inputs=2:normalize=0[r];"
                                           "[l][r]amerge=inputs=2",
                        "-ac", "2", "-c:a", "pcm_s16le", str(src)], check=True)
        self._run(src, d, [1, 2])

    def _run(self, src, d, mics):
        words = [(f"w{(k % 12) + 1}", 4 * c + 0.5 * j, 0.4) for c in range(d // 4) for j, k in
                 ((j, c * 6 + j) for j in range(6))]
        write_transcript(self.p, words, d * 1000)
        tj = read_json(self.p.p("02_transcription/transcript.json"))     # one segment per 4 s cycle
        tj["segments"] = [{"id": c + 1, "start_ms": 4000 * c, "end_ms": 4000 * c + 3000, "text": "w",
                           "words": []} for c in range(d // 4)]
        write_json(self.p.p("02_transcription/transcript.json"), tj)
        r = subprocess.run([sys.executable, "-B", "-c", HARNESS, str(ENGINE), str(self.p.root), self.p.video_id, str(src)],
                           capture_output=True, text=True, timeout=3600)
        self.assertEqual(r.returncode, 0, r.stderr[-3000:])
        m = json.loads(r.stdout.strip().splitlines()[-1])
        sys.stderr.write(f"\n[T2.13] {self.MINUTES}-min {len(mics)}-mic clip: peak RSS {m['peak_rss'] / 1024 ** 2:.0f} MB, {m}\n")
        self.assertEqual(m["duration_ms"], d * 1000)
        self.assertGreater(m["cuts"], d // 4 - 5)
        self.assertTrue(m["spectrograms"])
        self.assertEqual(m["mics"], mics)
        self.assertLess(m["peak_rss"], self.BUDGET)


if __name__ == "__main__":
    unittest.main()
