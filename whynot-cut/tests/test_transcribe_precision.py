# SPDX-License-Identifier: GPL-3.0-or-later
# © 2026 The Why Not AI (thewhynot.ai)
"""3.0 Phase 4 T4.14: one GPU precision per model (transcription.json gpu_compute_types), the WER/CER module the 6B
eval set reuses (lib/wer.py), and `reel bench --compute-type/--device/--reference`.
No test loads a model: runners are fakes. Case list: the lane's work/t414/cases.md (A-F).
Run:  bash tools/test.sh -p test_transcribe_precision.py
"""
import sys as _sys
_sys.dont_write_bytecode = True  # keep the plugin folder free of __pycache__
import _isolation  # noqa: F401,E402  G79: sandbox the engine home first (tests/_isolation.py)
import argparse
import contextlib
import io
import json
import os
import random
import shutil
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

import numpy as np

SK = Path(__file__).resolve().parents[1]
ENGINE = SK / "engine" / "reel"
if str(ENGINE) not in _sys.path:
    _sys.path.insert(0, str(ENGINE))

from lib import wer  # noqa: E402
from lib import whisper_backends as WB  # noqa: E402
from lib.common import read_json, write_json  # noqa: E402

SR = 16000


@contextlib.contextmanager
def quiet():
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        yield


# --------------------------------------------------------------------------- A. wer.py
class TestWer(unittest.TestCase):
    def test_wer_counts(self):
        self.assertEqual(wer.wer("a b c d".split(), "a x c".split()), {"wer": 0.5, "sub": 1, "del": 1, "ins": 0, "n": 4})

    def test_insertions(self):
        self.assertEqual(wer.wer(["a", "b"], ["a", "b", "c"]), {"wer": 0.5, "sub": 0, "del": 0, "ins": 1, "n": 2})

    def test_wer_arabic_is_normalised(self):
        ref = "فَتْحَة كـــبير أحمد إسلام آخر مدرسة مستشفى مسئول سؤال"
        hyp = "فتحه كبير احمد اسلام اخر مدرسه مستشفي مسؤول سوال"
        self.assertEqual(wer.wer(ref.split(), hyp.split())["wer"], 0.0)

    def test_digits_fold(self):
        self.assertEqual(wer.wer(["٣", "۳"], ["3", "3"])["wer"], 0.0)

    def test_decimals_keep_their_point(self):
        self.assertEqual(wer.wer(["3.5", "مجم"], ["3.5", "مجم"])["wer"], 0.0)
        self.assertEqual(wer.wer(["3.5", "مجم"], ["35", "مجم"]), {"wer": 0.5, "sub": 1, "del": 0, "ins": 0, "n": 2})
        self.assertEqual(wer.wer(["3.5", "مجم"], ["٣٫٥", "مجم"])["wer"], 0.0)      # Arabic decimal separator
        self.assertEqual(wer.wer(["3.5", "مجم"], ["3,5", "مجم"])["wer"], 0.0)      # decimal comma
        self.assertEqual(wer.tokens("3.5، مجم"), ["3.5", "مجم"])
        self.assertEqual(wer.tokens("3 . 5"), ["3", "5"])                          # a spoken point already split

    def test_punctuation_vanishes(self):
        self.assertEqual(wer.tokens("كلمة، ... ؟ word, «قال»"), ["كلمه", "word", "قال"])

    def test_mixed_arabic_english(self):
        self.assertEqual(wer.wer("نستخدم Zoom كل يوم".split(), "نستخدم zoom كل يوم".split())["wer"], 0.0)
        self.assertEqual(wer.tokens(["Botox", "بوتوكس"]), ["botox", "بوتوكس"])

    def test_empty_sides(self):
        self.assertEqual(wer.wer([], []), {"wer": 0.0, "sub": 0, "del": 0, "ins": 0, "n": 0})
        self.assertEqual(wer.wer([], ["a", "b"]), {"wer": None, "sub": 0, "del": 0, "ins": 2, "n": 0})
        self.assertEqual(wer.wer(["a", "b"], []), {"wer": 1.0, "sub": 0, "del": 2, "ins": 0, "n": 2})
        self.assertEqual(wer.wer(["،", "..."], ["؟"]), {"wer": 0.0, "sub": 0, "del": 0, "ins": 0, "n": 0})

    def test_junk_items_never_crash(self):
        self.assertEqual(wer.wer(["a", None, 5, "b"], ["a", "b"])["wer"], 0.0)
        self.assertEqual(wer.tokens(None), [])
        self.assertEqual(wer.cer(None, None), 0.0)

    def test_cer(self):
        self.assertEqual(wer.cer("abcd", "abxd"), 0.25)
        self.assertEqual(wer.cer("عبد الله", "عبدالله"), 0.0)               # word-splitting variants cost nothing in CER
        self.assertEqual(wer.wer("عبد الله".split(), "عبدالله".split())["n"], 2)
        self.assertEqual(wer.cer("", ""), 0.0)
        self.assertIsNone(wer.cer("", "abc"))
        self.assertEqual(wer.cer("مدرسة", "مدرسه"), 0.0)
        self.assertEqual(wer.cer("ab", ""), 1.0)

    def test_corpus_total_is_not_a_mean(self):
        a = wer.wer(["a"] * 10, ["a"] * 9 + ["x"])           # 1 error / 10
        b = wer.wer(["a", "b"], ["x", "y"])                   # 2 errors / 2
        c = wer.wer([], ["z"])                                # undefined WER, counts still add
        t = wer.total([a, b, c])
        self.assertEqual((t["n"], t["sub"], t["ins"]), (12, 3, 1))
        self.assertAlmostEqual(t["wer"], 4 / 12, places=4)
        self.assertIsNone(wer.total([])["wer"])

    def test_deterministic_and_fast(self):
        rnd = random.Random(7)
        words = [rnd.choice(["كلمة", "طبيب", "علاج", "مريض", "dose", "3.5"]) for _ in range(2000)]
        hyp = list(words)
        for i in range(0, 2000, 37):
            hyp[i] = "x"
        t0 = time.perf_counter()
        r1 = wer.wer(words, hyp)
        self.assertLess(time.perf_counter() - t0, 2.0)
        self.assertEqual(r1, wer.wer(words, hyp))
        self.assertEqual(r1["sub"], len(range(0, 2000, 37)))
        a = [rnd.choice("abcdef") for _ in range(500)]
        b = [rnd.choice("abcdef") for _ in range(500)]
        t0 = time.perf_counter()
        wer.wer(a, b)
        self.assertLess(time.perf_counter() - t0, 2.0)


# --------------------------------------------------------------------------- B. gpu_compute_type_for
class TestComputeTypeFor(unittest.TestCase):
    def test_gpu_compute_type_per_model(self):
        cfg = {"gpu_compute_types": {"large-v3": "int8_float16"}}
        self.assertEqual(WB.gpu_compute_type_for("large-v3", cfg), "int8_float16")
        self.assertEqual(WB.gpu_compute_type_for("large-v3-turbo", cfg), "float16")
        self.assertEqual(WB.gpu_compute_type_for("large-v3", {"gpu_compute_type": "int8_float16"}), "int8_float16")
        self.assertEqual(WB.gpu_compute_type_for("large-v3", {}), "float16")

    def test_wrong_or_missing_entries_fall_back(self):
        for bad in ("fp16", "int4", 7, None, ""):
            self.assertEqual(WB.gpu_compute_type_for("large-v3", {"gpu_compute_types": {"large-v3": bad}}), "float16", bad)
            self.assertEqual(WB.gpu_compute_type_for("large-v3", {"gpu_compute_types": {"large-v3": bad},
                                                                   "gpu_compute_type": "int8_float16"}), "int8_float16")
        for bad_map in (["large-v3"], "int8_float16", 5):
            self.assertEqual(WB.gpu_compute_type_for("large-v3", {"gpu_compute_types": bad_map}), "float16")
        self.assertEqual(WB.gpu_compute_type_for("large-v3", {"gpu_compute_type": "fp16"}), "float16")
        self.assertEqual(WB.gpu_compute_type_for("C:/models/large-v3", {"gpu_compute_types": {"large-v3": "int8_float16"}}),
                         "float16")                        # exact model names only

    def test_device_tries_uses_the_model_type(self):
        cfg = {"gpu_compute_types": {"large-v3": "int8_float16", "large-v3-turbo": "float16"}}
        seen = []

        def tries(c, device, compute_type):
            seen.append((c.get("gpu_compute_type"), compute_type))
            return [("cpu", compute_type)]

        class FakeModel:
            def __init__(self, *a, **k):
                pass
        fw = mock.MagicMock(WhisperModel=FakeModel)
        with mock.patch.dict(_sys.modules, {"faster_whisper": fw}), mock.patch.object(WB, "_device_tries", tries), \
                mock.patch.object(WB, "load_config", return_value=cfg), \
                mock.patch.object(WB, "snapshot_dir", return_value=Path("snap")):
            WB.load_ct2("large-v3", "int8")
            WB.load_ct2("large-v3-turbo", "int8")
            WB.load_ct2("large-v3", "int8", gpu_compute_type="float16")        # a bench override reaches the GPU try only
        self.assertEqual(seen, [("int8_float16", "int8"), ("float16", "int8"), ("float16", "int8")])

    def test_cpu_stays_int8(self):
        import ctranslate2  # noqa: F401  (present in the engine runtime)
        cfg = {"gpu_compute_types": {"large-v3": "int8_float16"}, "gpu_compute_type": "float16"}
        with mock.patch("ctranslate2.get_cuda_device_count", return_value=0):
            self.assertEqual(WB._device_tries(dict(cfg, gpu_compute_type=WB.gpu_compute_type_for("large-v3", cfg)),
                                              None, "int8"), [("cpu", "int8")])
        with mock.patch("ctranslate2.get_cuda_device_count", return_value=1), \
                mock.patch("lib.plat.cuda_libs_missing", return_value=[]):
            self.assertEqual(WB._device_tries(dict(cfg, gpu_compute_type="int8_float16"), None, "int8"),
                             [("cuda", "int8_float16"), ("cpu", "int8")])

    def test_runner_fit_uses_the_models_gpu_type(self):
        seen = []

        def fit(model, ct, configured, free):
            seen.append((model, ct))
            return configured, "cuda"
        cfg = {"gpu_compute_types": {"large-v3": "int8_float16"}, "batch_size": 4}
        with mock.patch.object(WB, "load_config", return_value=cfg), \
                mock.patch.object(WB, "_device_tries", lambda c, d, ct: [("cuda", c.get("gpu_compute_type"))]), \
                mock.patch.object(WB, "vram_free_mb", return_value=99999), mock.patch.object(WB, "fit_batch", side_effect=fit), \
                mock.patch.object(WB, "load_ct2", return_value=(object(), "cuda", "int8_float16")), quiet():
            run =WB.make_runner("large-v3", vad=False, backend="ct2", batch_size=0)
            run.load()
        self.assertEqual(seen, [("large-v3", "int8_float16")])


# --------------------------------------------------------------------------- D. bench
def _fake_factory(calls, words=None, device="cuda", ct="float16", actual=None):
    def factory(model_size, vad, log_to=None, backend=None, batch_size=None, **kw):
        calls.append(kw)

        def run(a, s, lang, prompt):
            return {"segments": [], "words": [{"id": i + 1, "word": w, "start_ms": 100 + i * 400, "end_ms": 400 + i * 400}
                                              for i, w in enumerate(words or [])], "language": "ar",
                    "language_probability": 0.9}
        run.backend = "ct2"
        dev = actual or kw.get("device") or device              # actual: where it really loaded (a fallback)
        run.state = {"backend": "faster-whisper", "device": dev,
                     "compute_type": "int8" if dev == "cpu" else (kw.get("gpu_compute_type") or ct), "batch_size": 4}
        run.load = lambda: None
        return run
    return factory


class _Home(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="whynot-t414-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.home = self.tmp / "home"
        self.home.mkdir()
        env = mock.patch.dict(os.environ, {"WHYNOT_HOME": str(self.home)})
        env.start()
        self.addCleanup(env.stop)


class TestBench(_Home):
    def test_bench_key_has_compute_type_and_reference_wer(self):
        ref = self.tmp / "transcript.json"
        write_json(ref, {"words": [{"word": w, "start_ms": 100 + i * 400} for i, w in enumerate(["أهلا", "بيك", "دكتور", "سامي"])]})
        calls = []
        with mock.patch.object(WB, "make_runner", side_effect=_fake_factory(calls, ["اهلا", "بيك", "دكتور"])), quiet():
            r16 = WB.bench(np.zeros(SR * 10, np.float32), model="large-v3", compute_type="float16", reference=ref)
            r8 = WB.bench(np.zeros(SR * 10, np.float32), model="large-v3", compute_type="int8_float16", reference=ref)
        self.assertEqual(r16["key"], "ct2/large-v3/cuda/batch4/no-hint")              # the historic default: old key
        self.assertEqual(r8["key"], "ct2/large-v3/cuda+int8_float16/batch4/no-hint")
        self.assertNotEqual(r16["key"], r8["key"])
        self.assertEqual(calls[1].get("gpu_compute_type"), "int8_float16")
        self.assertEqual((r8["wer"], r8["reference_kind"]), (0.25, "given"))             # one deletion of four
        self.assertEqual(r8["cer"], round(wer.cer("أهلا بيك دكتور سامي", "اهلا بيك دكتور"), 4))
        cache = read_json(self.home / "bench" / "whisper-bench.json")
        self.assertEqual(set(cache["results"]), {r16["key"], r8["key"]})

    def test_reference_is_cut_to_the_decoded_window(self):
        ref = self.tmp / "t.json"
        write_json(ref, {"words": [{"word": "a", "start_ms": 1000}, {"word": "b", "start_ms": 9800},
                                   {"word": "late", "start_ms": 30000}]})
        with mock.patch.object(WB, "make_runner", side_effect=_fake_factory([], ["a"])), quiet():
            r = WB.bench(np.zeros(SR * 10, np.float32), model="large-v3", reference=ref)
        self.assertEqual(r["wer"], 0.0)          # "b" (in the last 500 ms) and "late" are outside the compared window
        self.assertEqual(r["reference_words"], 1)

    def test_bad_reference_is_refused_before_the_model_loads(self):
        made = []
        bad = self.tmp / "bad.json"
        bad.write_text("{{{", encoding="utf-8")
        nowords = self.tmp / "nowords.json"
        write_json(nowords, {"segments": "x"})
        for r in (bad, nowords, self.tmp / "missing.json"):
            with mock.patch.object(WB, "make_runner", side_effect=lambda *a, **k: made.append(1)), self.assertRaises(ValueError):
                WB.bench(np.zeros(SR, np.float32), model="large-v3", reference=r)
        self.assertEqual(made, [])

    def test_segments_reference_is_accepted(self):
        ref = self.tmp / "segs.json"
        write_json(ref, {"segments": [{"start_ms": 0, "end_ms": 900, "text": "أهلا بيك"}]})
        with mock.patch.object(WB, "make_runner", side_effect=_fake_factory([], ["اهلا", "بيك"])), quiet():
            self.assertEqual(WB.bench(np.zeros(SR * 10, np.float32), model="large-v3", reference=ref)["wer"], 0.0)

    def test_no_reference_no_wer_and_hypothesis_saved(self):
        with mock.patch.object(WB, "make_runner", side_effect=_fake_factory([], ["كلمة"])), quiet():
            r = WB.bench(np.zeros(SR * 10, np.float32), model="large-v3")
        self.assertNotIn("wer", r)
        self.assertNotIn("cer", r)
        hyp = read_json(Path(r["hypothesis"]))
        self.assertEqual(hyp["words"], ["كلمة"])
        self.assertTrue(Path(r["hypothesis"]).is_relative_to(self.home))

    def test_cpu_device_and_cpu_float16_refused(self):
        calls = []
        with mock.patch.object(WB, "make_runner", side_effect=_fake_factory(calls, device="cpu", ct="int8")), quiet():
            r = WB.bench(np.zeros(SR * 10, np.float32), model="large-v3", device="cpu")
            self.assertEqual(r["key"], "ct2/large-v3/cpu/batch4/no-hint")
            self.assertEqual(calls[0].get("device"), "cpu")
            with self.assertRaises(ValueError):
                WB.bench(np.zeros(SR, np.float32), model="large-v3", device="cpu", compute_type="float16")
        self.assertEqual(len(calls), 1)

    def test_old_keys_still_read(self):
        write_json(self.home / "bench" / "whisper-bench.json",
                   {"latest": "ct2/large-v3/cuda/batch8/no-hint", "results": {"ct2/large-v3/cuda/batch8/no-hint": {
                       "rt_factor": 12.5, "backend": "ct2", "model": "large-v3", "device": "cuda", "batch_size": 8}}})
        self.assertEqual(WB.read_bench()["rt_factor"], 12.5)

    def test_bench_args(self):
        ap = argparse.ArgumentParser()
        WB.add_cli_args("bench", ap)
        a = ap.parse_args(["--compute-type", "int8_float16", "--device", "cuda", "--reference", "t.json"])
        self.assertEqual((a.compute_type, a.device, a.reference), ("int8_float16", "cuda", "t.json"))
        for bad in (["--compute-type", "int4"], ["--device", "tpu"]):
            with quiet(), self.assertRaises(SystemExit):
                ap.parse_args(bad)
        ap2 = argparse.ArgumentParser()
        WB.add_cli_args("transcribe", ap2)
        with quiet(), self.assertRaises(SystemExit):
            ap2.parse_args(["--compute-type", "float16"])                 # bench only


# --------------------------------------------------------------------------- E. the pick rule
def row(f16, i8, ref=True):
    return {"clip": "c", "reference": ref, "float16": f16, "int8_float16": i8}


def m(w, c, rtf, vram):
    return {"wer": w, "cer": c, "rtf": rtf, "peak_vram_mb": vram}


class TestPickRule(unittest.TestCase):
    def test_int8_wins_only_when_every_clip_passes(self):
        good = row(m(0.10, 0.05, 10.0, 5000), m(0.104, 0.052, 11.5, 4500))
        self.assertEqual(WB.pick_compute_type([good])["choice"], "int8_float16")
        bad = row(m(0.10, 0.05, 10.0, 5000), m(0.12, 0.05, 20.0, 2000))          # +2 pp WER
        self.assertEqual(WB.pick_compute_type([good, bad])["choice"], "float16")

    def test_boundaries_as_written(self):
        base = m(0.10, 0.05, 10.0, 5000)
        self.assertEqual(WB.pick_compute_type([row(base, m(0.105, 0.053, 11.0, 5000))])["choice"], "int8_float16")
        self.assertEqual(WB.pick_compute_type([row(base, m(0.1051, 0.05, 11.0, 5000))])["choice"], "float16")
        self.assertEqual(WB.pick_compute_type([row(base, m(0.10, 0.0531, 11.0, 5000))])["choice"], "float16")
        self.assertEqual(WB.pick_compute_type([row(base, m(0.10, 0.05, 10.99, 5000))])["choice"], "float16")   # 9.9 %
        self.assertEqual(WB.pick_compute_type([row(base, m(0.10, 0.05, 10.0, 3976))])["choice"], "int8_float16")  # 1 GB
        self.assertEqual(WB.pick_compute_type([row(base, m(0.10, 0.05, 10.0, 3977))])["choice"], "float16")

    def test_better_quality_counts_as_within(self):
        self.assertEqual(WB.pick_compute_type([row(m(0.10, 0.05, 10, 5000), m(0.08, 0.04, 12, 5000))])["choice"],
                         "int8_float16")

    def test_no_reference_stays_float16_not_verified(self):
        r = WB.pick_compute_type([row(m(None, None, 10, 5000), m(None, None, 20, 2000), ref=False)])
        self.assertEqual(r["choice"], "float16")
        self.assertIn("Not verified: no reference", r["reason"])
        r = WB.pick_compute_type([])
        self.assertEqual(r["choice"], "float16")
        self.assertIn("Not verified: not measured", r["reason"])


# --------------------------------------------------------------------------- F. config
class TestConfig(unittest.TestCase):
    def test_measured_vram_constants(self):
        self.assertEqual((WB.MODEL_VRAM_MB[("large-v3", "float16")], WB.MODEL_VRAM_MB[("large-v3", "int8_float16")],
                          WB.PER_BATCH_MB), (3279, 2223, 900))
        self.assertEqual(WB.MODEL_VRAM_MB[("large-v3-turbo", "float16")], 1800)       # not measured: starting value
        # the measuring card idle (7424 MB free): batch 2 of 4 leaves the 1.5 GB for Premiere (batch 4 peaked 6245)
        self.assertEqual(WB.fit_batch("large-v3", "float16", 4, 7424), (2, "cuda"))
        self.assertEqual(WB.fit_batch("large-v3", "int8_float16", 4, 7424), (4, "cuda"))

    def test_shipped_transcription_json(self):
        d = json.loads((SK / "config" / "defaults" / "transcription.json").read_text(encoding="utf-8"))
        self.assertEqual(set(d["gpu_compute_types"]), {"large-v3", "large-v3-turbo"})
        for v in d["gpu_compute_types"].values():
            self.assertIn(v, WB.GPU_COMPUTE_TYPES)
        self.assertIn("g13-transcription-precision", d["gpu_compute_types_note"])
        self.assertEqual(d["compute_type"], "int8")                         # the CPU


# --------------------------------------------------------------------------- independent review round 1
class TestReview1Wer(unittest.TestCase):
    def test_format_marks_never_break_a_decimal(self):
        for t in ("3.5‏", "‏3.5", "3.‎5", "​3.5"):
            self.assertEqual(wer.tokens(t), ["3.5"], repr(t))
        self.assertEqual(wer.wer(["كلمة‏"], ["كلمة"])["wer"], 0.0)

    def test_arabic_comma_decimal_and_glued_units(self):
        self.assertEqual(wer.tokens("٣،٥"), ["3.5"])
        self.assertEqual(wer.tokens("3.5mg"), ["3.5", "mg"])
        self.assertEqual(wer.tokens("3.5مجم"), ["3.5", "مجم"])
        self.assertEqual(wer.wer(["3.5mg"], ["3.5", "mg"])["wer"], 0.0)

    def test_cer_is_fast_on_an_episode(self):
        rnd = random.Random(3)
        a = "".join(rnd.choice("ابتثجحخدذرزسشصضطظعغفقكلمنهوي ") for _ in range(30000))
        b = list(a)
        for i in range(0, len(b), 50):
            b[i] = "ق"
        b = "".join(b)
        t0 = time.perf_counter()
        c = wer.cer(a, b)
        self.assertLess(time.perf_counter() - t0, 5.0)
        ra, rb = "".join(wer.tokens(a)), "".join(wer.tokens(b))
        self.assertGreater(c, 0)
        self.assertEqual(wer._distance("kitten", "sitting"), 3)
        self.assertEqual(wer._distance("", "abc"), 3)
        self.assertEqual(wer._distance("flaw", "lawn"), 2)
        self.assertEqual(wer._distance("a" * 70, "b" * 70), 70)          # longer than one machine word
        self.assertEqual(wer._distance("ab" * 50, "ba" * 50), 2)
        self.assertLessEqual(c, 1.0)
        del ra, rb


class TestReview1Bench(_Home):
    def test_segments_reference_drops_segments_past_the_window(self):
        ref = self.tmp / "segs.json"
        write_json(ref, {"segments": [{"start_ms": 0, "end_ms": 4000, "text": "أهلا بيك"},
                                      {"start_ms": 9000, "end_ms": 12000, "text": "كلام بعد نهاية الصوت"}]})
        with mock.patch.object(WB, "make_runner", side_effect=_fake_factory([], ["اهلا", "بيك"])), quiet():
            r = WB.bench(np.zeros(SR * 10, np.float32), model="large-v3", reference=ref)
        self.assertEqual((r["wer"], r["reference_words"]), (0.0, 2))

    def test_explicit_gpu_that_fell_back_is_refused_or_flagged(self):
        with mock.patch.object(WB, "make_runner", side_effect=_fake_factory([], ["a"], device="cpu", ct="int8", actual="cpu")), quiet():
            with self.assertRaises(WB.BenchArgError):
                WB.bench(np.zeros(SR * 10, np.float32), model="large-v3", device="cuda")
            r = WB.bench(np.zeros(SR * 10, np.float32), model="large-v3", compute_type="int8_float16")
        self.assertTrue(r["fell_back"])
        self.assertEqual(r["key"], "ct2/large-v3/cpu/batch4/no-hint")

    def test_cache_is_written_even_if_the_hypothesis_cannot_be(self):
        with mock.patch.object(WB, "make_runner", side_effect=_fake_factory([], ["a"])), \
                mock.patch.object(WB, "write_json", side_effect=lambda f, d: (_ for _ in ()).throw(OSError("full"))
                                  if "hypotheses" in str(f) else write_json(f, d)), quiet():
            r = WB.bench(np.zeros(SR * 10, np.float32), model="large-v3")
        self.assertIsNone(r.get("hypothesis"))
        self.assertIn(r["key"], read_json(self.home / "bench" / "whisper-bench.json")["results"])


class TestReview1CliBench(_Home):
    def project(self, verified=True):
        from lib.common import Paths
        root = self.tmp / "c"
        (root / "assets").mkdir(parents=True)
        (root / "data").mkdir()
        p = Paths(root, "V1")
        out = p.p("02_transcription")
        out.mkdir(parents=True)
        (out / "dialogue_16k_mono.wav").write_bytes(b"RIFF")
        write_json(out / "words.json", {"words": [{"id": 1, "word": "أهلا", "start_ms": 100, "end_ms": 400}]})
        write_json(out / "transcript.json", {"segments": [{"start_ms": 0, "end_ms": 60000, "text": "أهلا وكلام كتير"}]})
        if verified:
            write_json(out / "verification.json", {"verified": True})
        return p

    def args(self, **kw):
        return argparse.Namespace(**{"audio": None, "seconds": 10.0, "model": "large-v3", "backend": None,
                                     "batch_size": None, "compute_type": None, "device": None, "reference": None, **kw})

    def go(self, a, p):
        seen = {}

        def fake_bench(audio, **kw):
            seen.update(kw)
            return {"ok": True}
        with mock.patch("lib.transcribe.extract_audio", side_effect=lambda src, dst, rng=None: dst), \
                mock.patch("lib.transcribe.whisper_audio", return_value=np.zeros(SR, np.float32)), \
                mock.patch.object(WB, "bench", side_effect=fake_bench):
            WB.cli_bench(a, p)
        return seen

    def test_verified_project_uses_its_words(self):
        p = self.project()
        seen = self.go(self.args(), p)
        self.assertEqual(Path(seen["reference"]).name, "words.json")
        self.assertEqual(seen["reference_kind"], "verified")

    def test_unverified_project_has_no_reference(self):
        seen = self.go(self.args(), self.project(verified=False))
        self.assertIsNone(seen["reference"])

    def test_other_audio_never_takes_the_project_reference(self):
        p = self.project()
        other = self.tmp / "other.wav"
        other.write_bytes(b"RIFF")
        seen = self.go(self.args(audio=str(other)), p)
        self.assertIsNone(seen["reference"])

    def test_arguments_errors_are_guidance_other_errors_are_not_rewritten(self):
        from lib.errors import Guidance
        p = self.project(verified=False)
        with mock.patch("lib.transcribe.extract_audio", side_effect=lambda src, dst, rng=None: dst), \
                mock.patch("lib.transcribe.whisper_audio", return_value=np.zeros(SR, np.float32)):
            with mock.patch.object(WB, "bench", side_effect=WB.BenchArgError("bad reference")), self.assertRaises(Guidance):
                WB.cli_bench(self.args(), p)
            with mock.patch.object(WB, "bench", side_effect=ValueError("float16 not supported")), self.assertRaises(ValueError) as cm:
                WB.cli_bench(self.args(), p)
            self.assertNotIsInstance(cm.exception, Guidance)


class TestReview1Types(unittest.TestCase):
    def test_cpu_try_stays_int8_through_load_ct2(self):
        tried = []

        class FakeModel:
            def __init__(self, path, device=None, compute_type=None, **kw):
                tried.append((device, compute_type))
                if device == "cuda":
                    raise RuntimeError("no CUDA here")
        fw = mock.MagicMock(WhisperModel=FakeModel)
        cfg = {"gpu_compute_types": {"large-v3": "int8_float16"}}
        with mock.patch.dict(_sys.modules, {"faster_whisper": fw}), mock.patch.object(WB, "load_config", return_value=cfg), \
                mock.patch.object(WB, "snapshot_dir", return_value=Path("snap")), \
                mock.patch("ctranslate2.get_cuda_device_count", return_value=1), \
                mock.patch("lib.plat.cuda_libs_missing", return_value=[]):
            _m, dev, ct = WB.load_ct2("large-v3", "int8")
        self.assertEqual(tried, [("cuda", "int8_float16"), ("cpu", "int8")])
        self.assertEqual((dev, ct), ("cpu", "int8"))

    def test_runner_signature_uses_the_models_type(self):
        seen = []
        cfg = {"gpu_compute_types": {"large-v3": "int8_float16"}, "batch_size": 4}

        def tries(c, d, ct):
            seen.append(c.get("gpu_compute_type"))
            return [("cuda", c.get("gpu_compute_type"))]
        with mock.patch.object(WB, "load_config", return_value=cfg), mock.patch.object(WB, "_device_tries", tries), quiet():
            WB.make_runner("large-v3", vad=True, backend="ct2").signature()
            WB.make_runner("large-v3", vad=True, backend="ct2", gpu_compute_type="float16").signature()
        self.assertEqual(seen, ["int8_float16", "float16"])


class TestReview1Pick(unittest.TestCase):
    def test_an_unmeasured_side_blocks_the_pick(self):
        good = row(m(0.10, 0.05, 10.0, 5000), m(0.104, 0.052, 11.5, 4500))
        half = {"clip": "worst", "reference": True, "float16": m(0.10, 0.05, 10.0, 5000), "int8_float16": None}
        r = WB.pick_compute_type([good, half])
        self.assertEqual(r["choice"], "float16")
        self.assertIn("Not verified: incomplete on worst", r["reason"])

    def test_only_verified_references_count(self):
        given = row(m(0.10, 0.05, 10.0, 5000), m(0.104, 0.052, 11.5, 4500), ref="given")
        r = WB.pick_compute_type([given])
        self.assertEqual(r["choice"], "float16")
        self.assertIn("no reference", r["reason"])
        self.assertEqual(WB.pick_compute_type([row(m(0.10, 0.05, 10.0, 5000), m(0.104, 0.052, 11.5, 4500),
                                                   ref="verified")])["choice"], "int8_float16")


if __name__ == "__main__":
    unittest.main()
