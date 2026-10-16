# SPDX-License-Identifier: GPL-3.0-or-later
# © 2026 The Why Not AI (thewhynot.ai)
"""3.0 tools track, N6 - WhyNot Hush engine twins (lib/hush/{wav,detect,fillers,settings}.py) against the JS port.

Chat (`reel hush`) must produce what the panel's JavaScript produces, so the Python twins are tested two ways:

* HushTwinsCharacterization: the WHOLE characterization suite (test_hush_characterization.HushCharacterizationMixin: every
  case with its Python-side expected values) runs through the Python twin; when node and adobe/tools are present each
  call is also run on the JS port (adobe/tools/hush/src) and the results must be identical (the envelope: equal after
  float32 rounding or within 1 float32 ulp). Without node / adobe/tools (the plugin zip) the same cases still run on the
  twin alone.
* Corpus classes (need node + adobe/tools): seeded random envelopes x intensities x Tight x fps through settings, stats and
  plan; seeded word lists through find and untranscribed; generated WAV files (16/24/32-bit, float, stereo, odd chunk,
  streamed lengths) through header / decode / envelope and WAV -> stats -> plan; fmt on a 13 000-value grid. Derived outputs
  must be exactly equal, never "close".
* Python-only units: the JS arithmetic rules (Math.round is floor(x + 0.5), sums are not compensated, numbers print like JS),
  the envelope speed on a 10-minute file.
Run:  bash tools/test.sh -p test_hush_twins.py
"""
import sys as _sys
_sys.dont_write_bytecode = True  # keep the plugin folder free of __pycache__
import _isolation  # noqa: F401,E402  G79: sandbox the engine home first (tests/_isolation.py)
import math  # noqa: E402
import random  # noqa: E402
import struct  # noqa: E402
import tempfile  # noqa: E402
import time  # noqa: E402
import unittest  # noqa: E402
from pathlib import Path  # noqa: E402

import numpy as np  # noqa: E402

sys = _sys
SK = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SK / "engine" / "reel"))

import test_hush_characterization as HC  # noqa: E402  (module import: its TestCases are not collected twice)
from lib.hush import detect, fillers, settings, wav  # noqa: E402
from lib.hush._js import js_num_str  # noqa: E402

PORT = HC.ADOBE_TOOLS / "hush" / "src"
HAVE_JS = bool(HC.NODE) and HC.TOOLS_PRESENT
NEED_JS = "needs node and adobe/tools (not in the plugin zip)"
LOAD = ["js/wav.js", "js/detect.js", "js/fillers.js", "js/settings.js"]
ENV_FNS = ("HushWav.envelope", "HushDetect.envelope")
call = HC.call


# ------------------------------------------------------------------ the Python side of a js_runner request ---------
def _plain(v):
    """What js_runner prints for a JS value: typed arrays flat, Infinity/NaN as strings, numpy scalars as numbers."""
    if isinstance(v, np.ndarray):
        return [_plain(x) for x in v.astype(np.float64).tolist()]
    if isinstance(v, (np.floating, np.integer)):
        v = v.item()
    if isinstance(v, float):
        if v != v:
            return "NaN"
        if v in (math.inf, -math.inf):
            return "Infinity" if v > 0 else "-Infinity"
        return v
    if isinstance(v, dict):
        return {k: _plain(x) for k, x in v.items()}
    if isinstance(v, (list, tuple)):
        return [_plain(x) for x in v]
    return v


_FUNCS = {
    "HushWav.header": wav.header, "HushWav.decode": wav.decode, "HushWav.envelope": wav.envelope,
    "HushDetect.envelope": detect.envelope, "HushDetect.percentile": detect.percentile, "HushDetect.stats": detect.stats,
    "HushDetect.fromIntensity": detect.from_intensity, "HushDetect.silences": detect.silences,
    "HushDetect.cutsFromSilences": detect.cuts_from_silences, "HushDetect.combine": detect.combine,
    "HushDetect.snap": detect.snap, "HushDetect.total": detect.total, "HushDetect.plan": detect.plan,
    "HushDetect.fmt": detect.fmt, "HushFillers.norm": fillers.norm, "HushFillers.parseList": fillers.parse_list,
    "HushFillers.isHesitation": fillers.is_hesitation, "HushFillers.find": fillers.find,
    "HushFillers.untranscribed": fillers.untranscribed, "HushSettings.current": settings.current,
    "HushSettings.advFromSimple": settings.adv_from_simple, "HushSettings.readout": settings.readout,
}
_CONSTS = {"HushDetect.HOP": detect.HOP, "HushDetect.SIMPLE": detect.SIMPLE,
           "HushFillers.DEFAULT_STRONG": fillers.DEFAULT_STRONG, "HushFillers.DEFAULT_SOFT": fillers.DEFAULT_SOFT}


def twin(c):
    """Run one js_runner call on the Python twin and return the slot js_runner would print."""
    if c["fn"] in _CONSTS:
        return _plain(_CONSTS[c["fn"]])
    args = list(c.get("args", []))
    if c.get("bytes_file"):
        if args:
            args[0] = Path(c["bytes_file"]).read_bytes()
        else:
            args.append(Path(c["bytes_file"]).read_bytes())
    out = []
    for a in args:
        if isinstance(a, dict) and "$file" in a:
            a = Path(a["$file"]).read_bytes()
        out.append(a)
    drop = [i for i, a in enumerate(args) if isinstance(a, dict) and "$dataview" in a]  # header(bytes) has no DataView
    for k, name in (c.get("typed") or {}).items():
        assert name == "Float32Array", name
        out[int(k)] = np.asarray(out[int(k)], dtype=np.float32)
    out = [a for i, a in enumerate(out) if i not in drop]
    try:
        return _plain(_FUNCS[c["fn"]](*out))
    except wav.WavError as e:
        return {"error": str(e)}


def _ulps(a, b):
    """Distance in float32 steps between two doubles that are float32 values."""
    def key(x):
        i = struct.unpack("<i", struct.pack("<f", x))[0]
        return i if i >= 0 else -(i & 0x7FFFFFFF)
    return abs(key(a) - key(b))


def same(tc, c, py, js, where=""):
    """Identical JSON, except envelope arrays: equal after float32 rounding or within 1 float32 ulp."""
    if c["fn"] in ENV_FNS and not (isinstance(py, dict) and "error" in py):
        pe, je = (py["env"], js["env"]) if isinstance(py, dict) and "env" in py else (py, js)
        tc.assertEqual(len(pe), len(je), where)
        for k, (a, b) in enumerate(zip(pe, je)):
            tc.assertLessEqual(_ulps(a, b), 1, "%s env[%d]: %r vs %r" % (where, k, a, b))
        if isinstance(py, dict):
            tc.assertEqual({k: v for k, v in py.items() if k != "env"}, {k: v for k, v in js.items() if k != "env"}, where)
        return
    tc.assertEqual(py, js, "%s: twin and JS differ for %s" % (where, c["fn"]))


def run_both(tc, calls, chunk=1000):
    """The twin's results, after checking each one against the JS port (calls batched into few node runs)."""
    py = [twin(c) for c in calls]
    for i in range(0, len(calls), chunk):
        part = calls[i:i + chunk]
        js = HC.run_js(tc, PORT, LOAD, part)
        for k, (c, a, b) in enumerate(zip(part, py[i:i + chunk], js)):
            same(tc, c, a, b, "call %d" % (i + k))
    return py


# ------------------------------------------------------------------ 1. the whole characterization suite ------------
class HushTwinsCharacterization(HC.HushCharacterizationMixin, unittest.TestCase):
    """Every characterization test, through the Python twin (and, when possible, also compared with the JS port)."""

    ROOT = PORT

    def setUp(self):  # the mixin's setUp skips without node / adobe: the twin itself needs neither
        self._td = tempfile.TemporaryDirectory()
        self.tmp = Path(self._td.name)

    def js(self, calls, load=HC.LOAD):
        py = [twin(c) for c in calls]
        if HAVE_JS:
            js = HC.run_js(self, PORT, LOAD, calls)
            for k, (c, a, b) in enumerate(zip(calls, py, js)):
                same(self, c, a, b, "call %d" % k)
        return py

    test_fmt_rounding_edges_are_quirks = HC.HushCharacterizationPort.test_fmt_rounding_edges_are_quirks


# ------------------------------------------------------------------ 2. seeded corpora ---------------------------------
def make_env(rng):
    """A synthetic envelope: speech / silence stretches with noise, clicks inside silences, 0.01 dB resolution."""
    out, n = [], rng.randint(300, 700)
    speech = rng.uniform(-35, -8)
    floor = rng.choice([rng.uniform(-95, -50), rng.uniform(-80, -72), -100.0])
    while len(out) < n:
        if rng.random() < 0.5:
            out += [round(speech + rng.gauss(0, 3), 2) for _ in range(rng.randint(10, 120))]
        else:
            quiet = [round(floor + rng.gauss(0, 1.5), 2) for _ in range(rng.randint(5, 160))]
            for _ in range(rng.randint(0, 3)):  # clicks of 1..5 hops
                if len(quiet) > 12:
                    at, ln = rng.randrange(2, len(quiet) - 6), rng.randint(1, 5)
                    quiet[at:at + ln] = [round(speech + rng.gauss(0, 2), 2)] * ln
            out += quiet
    return out[:n]


def make_fillers(rng, length):
    out = []
    for _ in range(rng.choice([0, 0, 1, 2, 4])):
        s = round(rng.uniform(0, max(0.5, length - 0.5)), 3)
        item = {"s": s, "e": round(s + rng.uniform(0.1, 0.6), 3), "kind": "filler",
                "label": rng.choice(["um", "uh", "like", "\u064a\u0639\u0646\u064a", "", None]),
                "on": rng.random() < 0.5, "source": "word"}
        roll = rng.random()
        if roll < 0.08:
            del item["label"]  # a missing key is JS undefined (dropped from the JSON), unlike null
        elif roll < 0.13:
            item["kind"] = None
        elif roll < 0.18:
            del item["kind"]
        out.append(item)
    return out


@unittest.skipUnless(HAVE_JS, NEED_JS)
class HushTwinsCorpus(unittest.TestCase):
    INTENSITIES = (0, 25, 50, 80, 100)
    FPS = (24, 25, 29.97, 30, 60)

    def test_stats_settings_and_plan_on_200_seeded_envelopes(self):
        rng = random.Random(20261016)
        envs = [make_env(rng) for _ in range(200)]
        stats = run_both(self, [call("HushDetect.stats", e) for e in envs])
        # settings: Simple tab with Tight on and off, intensities 0..100, plus the Advanced passthrough
        adv = {"threshold": -41.5, "minSilence": 0.4, "padBefore": 0.07, "padAfter": 0.05}
        setting_calls, keys = [], []
        for ei, st in enumerate(stats):
            for i in self.INTENSITIES:
                for tight in (False, True):
                    setting_calls.append(call("HushSettings.current", {"tab": "simple", "intensity": i, "tight": tight,
                                                                       "adv": adv}, st))
                    keys.append((ei, i, tight))
        sett = run_both(self, setting_calls)
        self.assertEqual(len(sett), 2000)
        plan_calls = []
        for (ei, i, tight), st in zip(keys, sett):
            env = envs[ei]
            length = round(len(env) * 0.01, 2)
            fillers_ = make_fillers(rng, length)
            plan_calls.append(call("HushDetect.plan", env, st, fillers_, length, self.FPS[(ei + i) % 5]))
        # the full grid: every (envelope, intensity, tight) with each of the five frame rates
        grid = [dict(c, args=[c["args"][0], c["args"][1], c["args"][2], c["args"][3], fps])
                for c in plan_calls for fps in self.FPS]
        plans = run_both(self, grid)
        self.assertEqual(len(plans), 10000)
        cuts = sum(len(p["cuts"]) for p in plans)
        self.assertGreater(cuts, 10000)  # the corpus really cuts things

    def test_silence_primitives_on_the_corpus_with_odd_thresholds_and_hops(self):
        rng = random.Random(7)
        calls = []
        for _ in range(200):
            env = make_env(rng)
            th = round(rng.uniform(-70, -20), 1)
            ms = round(rng.uniform(0.1, 1.0), 2)
            calls.append(call("HushDetect.silences", env, th, ms, rng.choice([None, None, 0.01, 0.02, 0.005, 0.012])))
        sil = run_both(self, calls)
        cut_calls = []
        for c, s in zip(calls, sil):
            length = round(len(c["args"][0]) * 0.01, 2)
            o = {"padBefore": round(rng.uniform(0, 0.2), 2), "padAfter": round(rng.uniform(0, 0.2), 2)}
            if rng.random() < 0.3:
                o["minCut"] = rng.choice([0, 0.02, 0.3])
            cut_calls.append(call("HushDetect.cutsFromSilences", s, o, length))
        cuts = run_both(self, cut_calls)
        comb = run_both(self, [call("HushDetect.combine", c + make_fillers(rng, 5), round(rng.uniform(0, 0.4), 3))
                               for c in cuts])
        run_both(self, [call("HushDetect.snap", c, rng.choice([24, 25, 29.97, 30, 60]), rng.choice([None, 1, 2, 3]))
                        for c in comb])
        run_both(self, [call("HushDetect.total", c) for c in comb])

    def test_percentile_on_the_corpus(self):
        rng = random.Random(11)
        envs = [make_env(rng) for _ in range(50)]
        run_both(self, [call("HushDetect.percentile", e, p) for e in envs for p in (0, 0.1, 0.5, 0.9, 0.999, 1, 1.7)])

    def test_find_and_untranscribed_on_200_seeded_word_lists(self):
        rng = random.Random(424242)
        vocab = [
            "um", "Um,", "UMM.", "uh...", "uhh", "ummmm", "hmmmm", "aaah", "er", "erm", "hm", "mm", "mhm", "ah", "ahem", "hum",
            "so", "I", "mean", "you", "know", "You", "Know.", "like", "Like,", "basically", "actually", "well", "right",
            "the", "thing", "it's", "don\u2019t", "...", "\u2026", "-", "42", "foo,bar",
            "\u064a\u0639\u0646\u064a", "\u064a\u0639\u0646\u064a\u060c",
            "\u0637\u064a\u0628", "\u0623\u0635\u0644\u064b\u0627", "\u0622\u0647",
            "\u0627\u0645\u0645\u0645\u0645\u0645", "\u0622\u0622\u0622\u0647",
            "\u0627\u0647", "\u0647\u0645\u0645\u0645", "\u0627\u0648\u0647",
            "\u0639\u0644\u0649", "\u0645\u064e\u0631\u0652\u062d\u064e\u0628\u064b\u0627",
            "\u064a\u0639\u0640\u0640\u0646\u064a", "\u0628\u0642\u0649", "\u0627\u0645",
            "\u0627\u064a\u0647", "\u0625\u064a\u0647\u061f", "\u0645\u0631\u062d\u0628\u0629",
            " um ", "\tuh\n", "\u00a0um\u00a0", "\u3000hmm\u3000", "\u0130stanbul", "\u03a3\u0391\u03a3",
        ]
        lists = [None, "", "um, uh", "like\nyou know,i mean", "foo\u060cbar\nbaz", ",,\n,", fillers.DEFAULT_STRONG,
                 fillers.DEFAULT_SOFT, "\u0627\u0647\u060c \u0639\u0644\u064a", "ummmm, hum, \tuh ", "hm;mm", "undefined, null", "7, 1.5, 0, -2, null undefined"]
        find_calls, un_calls = [], []
        for _ in range(220):
            t, words = 0.0, []
            for _ in range(rng.randint(0, 25)):
                s = round(t + rng.uniform(0, 0.4), 3)
                words.append({"w": rng.choice(vocab), "s": s, "e": round(s + rng.uniform(0.05, 0.7), 3), "p": 0.9})
                roll = rng.random()
                if roll < 0.04:
                    del words[-1]["w"]          # JS String(undefined) = "undefined"
                elif roll < 0.08:
                    words[-1]["w"] = None       # JS String(null) = "null"
                elif roll < 0.11:
                    words[-1]["w"] = rng.choice([7, 1.5, 0, -2])
                t = words[-1]["e"]
            for _ in range(3):
                find_calls.append(call("HushFillers.find", words, rng.choice(lists), rng.choice(lists)))
            env = []
            while len(env) < max(60, int(t * 100) + 80):
                env += [round(rng.choice([-62, -48, -28, -18]) + rng.uniform(-2, 2), 1)] * rng.randint(3, 40)
            un_calls.append(call("HushFillers.untranscribed", env, 0.01, rng.choice([-40, -33.3, -50]), words,
                                 rng.choice([0.15, 0.1, 0.3]), rng.choice([1.2, 0.5, 2.0])))
        found = run_both(self, find_calls)
        self.assertGreater(sum(len(f) for f in found), 500)
        self.assertTrue(any(isinstance(h.get("label"), str) and " " in h["label"] for f in found for h in f))  # two-word phrases occur
        sounds = run_both(self, un_calls)
        self.assertGreater(sum(len(f) for f in sounds), 100)
        run_both(self, [call("HushFillers.norm", w) for w in vocab])
        run_both(self, [call("HushFillers.parseList", t) for t in lists])
        run_both(self, [call("HushFillers.isHesitation", fillers.norm(w)) for w in vocab])

    def test_null_and_missing_keys_behave_like_js(self):
        """kind / label: absent is JS undefined (dropped), null stays null; a word without w is String(undefined)."""
        ranges = [
            [{"s": 0, "e": 1, "kind": "filler", "label": None}], [{"s": 0, "e": 1, "kind": None, "label": "x"}],
            [{"s": 0, "e": 1}], [{"s": 0, "e": 1, "kind": "silence", "label": None}, {"s": 1.05, "e": 2, "kind": "filler"}],
            [{"s": 0, "e": 1, "kind": "filler", "label": None}, {"s": 0.5, "e": 2, "kind": "filler", "label": None}],
            [{"s": 0, "e": 1, "kind": "filler", "label": "um"}, {"s": 1.0, "e": 2, "kind": "filler", "label": None}],
            [{"s": 0, "e": 1, "kind": "filler", "label": "um"}, {"s": 1.0, "e": 2, "kind": "filler"}],
            [{"s": 1.0, "e": 2.0, "kind": None, "label": None}],
        ]
        out = run_both(self, [call("HushDetect.combine", r, 0.25) for r in ranges] +
                       [call("HushDetect.snap", r, 25) for r in ranges])
        self.assertEqual(out[0], [{"s": 0, "e": 1, "kind": "filler", "label": None}])  # the JS keeps the null
        words = [[{"s": 0, "e": 1}], [{"w": None, "s": 0, "e": 1}], [{"w": 7, "s": 0, "e": 1}],
                 [{"s": 0, "e": 1}, {"s": 1, "e": 2}], [{"w": "you", "s": 0, "e": 1}, {"s": 1, "e": 2}],
                 [{"w": None, "s": 0, "e": 1}, {"w": None, "s": 1, "e": 2}]]
        lists = [("undefined", ""), ("null", ""), ("7", ""), ("", "undefined undefined"), ("", "null null"),
                 ("", "you undefined")]
        found = run_both(self, [call("HushFillers.find", w, a, b) for w in words for a, b in lists])
        self.assertTrue(any(found))
        run_both(self, [call("HushFillers.norm", None), call("HushFillers.norm", 7), call("HushFillers.norm", 1.5)])

    def test_degenerate_wav_headers_match(self):
        """channels / bits 0 with an empty data chunk: JS frames is NaN (duration NaN); rate 0 gives Infinity."""
        cases = {"ch0": (1, 0, 8000, 16, b""), "bits0": (1, 1, 8000, 0, b""), "both0": (1, 0, 8000, 0, b""),
                 "rate0": (1, 1, 0, 16, b"\x01\x00\x02\x00"), "rate0_empty": (1, 1, 0, 16, b""),
                 "ch0_data": (1, 0, 8000, 16, b"\x01\x00\x02\x00"),
                 "bits12": (1, 1, 8000, 12, b"\x01\x00\x02\x00\x03\x00")}
        with tempfile.TemporaryDirectory() as td:
            calls = []
            for name, (tag, ch, rate, bits, raw) in cases.items():
                p = Path(td) / (name + ".wav")
                p.write_bytes(HC.riff(HC.chunk(b"fmt ", HC.fmt_payload(tag, ch, rate, bits)), HC.chunk(b"data", raw)))
                calls += [call("HushWav.header", HC.FILE(p), {"$dataview": 0}), call("HushWav.decode", HC.FILE(p)),
                          call("HushWav.envelope", HC.FILE(p), 0.01)]
            res = run_both(self, calls)
        self.assertEqual(res[2]["duration"], "NaN")  # channels 0, empty data
        self.assertEqual(res[2]["env"], [])

    def test_fmt_grid(self):
        values = [i / 100 for i in range(0, 13000)] + [599.96, 3599.96, 3725.04, 86399.96, 0.05, 0.15, 0.25, 0.35, 59.95,
                                                         9.95, 1e-7, 123456.789, -3]
        run_both(self, [call("HushDetect.fmt", v) for v in values], chunk=5000)

    def test_readout_matches_js_number_printing(self):
        rng = random.Random(5)
        sts = [{"threshold": round(rng.uniform(-90, -5), rng.choice([0, 1, 2])), "minSilence": round(rng.uniform(0.05, 1), 2),
                "padBefore": round(rng.uniform(0, 0.3), 2), "padAfter": round(rng.uniform(0, 0.3), 2)} for _ in range(200)]
        sts += [{"threshold": v, "minSilence": 0.57, "padBefore": 0, "padAfter": 0}
                for v in (-48, -48.0, 0, 1e-7, 1.5e-7, 123456789.125, 1e21, 1.5e21, -0.000001, 0.1 + 0.2, 100, 1e20)]
        run_both(self, [call("HushSettings.readout", st) for st in sts])


# ------------------------------------------------------------------ WAV corpus ---------------------------------------
def signal(rng, frames, rate):
    """Speech-like test signal in -1..1: bursts of a noisy sine with silence between."""
    x = np.zeros(frames)
    pos = 0
    while pos < frames:
        ln = rng.randint(rate // 20, rate // 2)
        if rng.random() < 0.55:
            amp = rng.uniform(0.02, 0.8)
            t = np.arange(min(ln, frames - pos)) / rate
            x[pos:pos + len(t)] = amp * np.sin(2 * np.pi * rng.uniform(100, 1500) * t) + \
                np.array([rng.gauss(0, amp / 8) for _ in range(len(t))])
        else:
            n = min(ln, frames - pos)
            x[pos:pos + n] = np.array([rng.gauss(0, 0.0005) for _ in range(n)])
        pos += ln
    return np.clip(x, -1, 1)


def encode(x, ch, bits, kind):
    """Interleave x (mono -1..1, shifted a little per channel) into raw sample bytes."""
    cols = [np.clip(x * (1 - 0.1 * c), -1, 1) for c in range(ch)]
    inter = np.stack(cols, axis=1).reshape(-1)
    if kind == "float":
        return inter.astype("<f4" if bits == 32 else "<f8").tobytes()
    if bits == 8:
        return np.round(inter * 127 + 128).astype(np.uint8).tobytes()
    if bits == 16:
        return np.round(inter * 32767).astype("<i2").tobytes()
    if bits == 24:
        v = np.round(inter * 8388607).astype(np.int32)
        return b"".join(struct.pack("<i", int(i))[:3] for i in v)
    return np.round(inter * 2147483647).astype("<i4").tobytes()


@unittest.skipUnless(HAVE_JS, NEED_JS)
class HushTwinsWavCorpus(unittest.TestCase):
    def test_header_decode_envelope_and_the_chain_to_a_plan(self):
        rng = random.Random(99)
        with tempfile.TemporaryDirectory() as td:
            files = []
            variants = [(1, 16, "pcm"), (2, 16, "pcm"), (1, 24, "pcm"), (2, 24, "pcm"), (1, 32, "pcm"), (1, 8, "pcm"),
                        (1, 32, "float"), (2, 32, "float"), (1, 64, "float")]
            for k in range(36):
                ch, bits, kind = variants[k % len(variants)]
                rate = rng.choice([8000, 16000, 22050, 44100, 48000])
                frames = rng.randint(rate // 2, rate * 6) + rng.randint(0, 50)
                raw = encode(signal(rng, frames, rate), ch, bits, kind)
                fmt_chunk = HC.fmt_payload(3 if kind == "float" else 1, ch, rate, bits)
                chunks = [HC.chunk(b"fmt ", fmt_chunk)]
                if k % 4 == 1:
                    chunks.append(HC.chunk(b"LIST", b"INFOx"))  # odd length: padded
                lf = {2: 0, 3: 0xFFFFFFFF}.get(k % 4)
                chunks.append(HC.data_chunk(raw, length_field=lf) if lf is not None else HC.chunk(b"data", raw))
                if k % 7 == 3:
                    chunks[-1] = HC.chunk(b"data", raw + b"\x01")  # a stray byte: not a whole frame
                p = Path(td) / ("w%02d.wav" % k)
                p.write_bytes(HC.riff(*chunks))
                files.append(p)
            calls = []
            for p in files:
                calls += [call("HushWav.header", HC.FILE(p), {"$dataview": 0}), call("HushWav.decode", HC.FILE(p)),
                          call("HushWav.envelope", HC.FILE(p), 0.01), call("HushWav.envelope", HC.FILE(p), 0.0125)]
            py = run_both(self, calls)
            # the chain: each side's own envelope -> stats -> settings -> plan must be exactly equal
            envs_py = [py[i]["env"] for i in range(2, len(py), 4)]
            js_env = [r["env"] for r in HC.run_js(self, PORT, LOAD, [c for c in calls if c["fn"] == "HushWav.envelope"
                                                                      and c["args"][1] == 0.01])]
            self.assertEqual(len(envs_py), len(js_env))
            stats_calls = [call("HushDetect.stats", e) for e in envs_py]
            st_py = [twin(c) for c in stats_calls]
            st_js = HC.run_js(self, PORT, LOAD, [call("HushDetect.stats", e) for e in js_env])
            self.assertEqual(st_py, st_js)  # exactly equal, not close
            plan_py, plan_js = [], []
            for e_py, e_js, st in zip(envs_py, js_env, st_py):
                cfg = {"tab": "simple", "intensity": 50, "tight": False, "adv": {}}
                s = twin(call("HushSettings.current", cfg, st))
                length = len(e_py) * 0.01
                plan_py.append(twin(call("HushDetect.plan", e_py, s, [], length, 25)))
                plan_js.append(call("HushDetect.plan", e_js, s, [], length, 25))
            self.assertEqual(plan_py, HC.run_js(self, PORT, LOAD, plan_js))

    def test_errors_match(self):
        with tempfile.TemporaryDirectory() as td:
            bad = {"text": b"nope", "empty": b"", "nodata": HC.riff(HC.chunk(b"fmt ", HC.fmt_payload(1, 1, 8000, 16))),
                   "nofmt": HC.riff(HC.chunk(b"data", b"\0\0")), "avi": b"RIFF\x04\0\0\0AVI " + b"\0" * 16}
            calls = []
            for n, b in bad.items():
                p = Path(td) / (n + ".wav")
                p.write_bytes(b)
                calls += [call("HushWav.header", HC.FILE(p), {"$dataview": 0}), call("HushWav.decode", HC.FILE(p)),
                          call("HushWav.envelope", HC.FILE(p), 0.01)]
            res = run_both(self, calls)
            self.assertTrue(all(set(r) == {"error"} for r in res))


# ------------------------------------------------------------------ Python-only units --------------------------------
class HushTwinUnits(unittest.TestCase):
    def test_math_round_is_half_up_not_bankers(self):
        # FR-10: 0.9 - 0.65 * 0.5 is 0.57499999999999996 in doubles, so the setting is 0.57 (never 0.58 via round/Decimal)
        got = detect.from_intensity(50, {"floor": -60, "speech": -20})
        self.assertEqual(got, {"threshold": -48.0, "minSilence": 0.57, "padBefore": 0.12, "padAfter": 0.12})
        self.assertEqual([wav.js_round(x) for x in (0.5, 1.5, 2.5, -0.5, -1.5, 57.49999999999999)], [1, 2, 3, 0, -1, 57])

    def test_math_round_ties_are_rounded_up_everywhere_round_is_used(self):
        # exact binary ties, where Python's round() goes to the even neighbour and JS Math.round goes up:
        # threshold: -59.75 + 40 * 0.15 = -53.75, x 10 = -537.5 -> JS -537 (Python round: -538) -> -53.7
        got = detect.from_intensity(0, {"floor": -59.75, "speech": -19.75})
        self.assertEqual(got["threshold"], -53.7)
        # the blip allowance is round(0.03 / hop): 0.03 / 0.012 is exactly 2.5 -> 3 hops (Python round: 2).
        # 50 quiet hops, a 3-hop click, 50 quiet hops stay ONE silence at hop 0.012 (control: 4 hops split it)
        env = [-60.0] * 50 + [-20.0] * 3 + [-60.0] * 50
        self.assertEqual(len(detect.silences(env, -40, 0.3, 0.012)), 1)
        self.assertEqual(len(detect.silences([-60.0] * 50 + [-20.0] * 4 + [-60.0] * 50, -40, 0.3, 0.012)), 2)
        # js_num / readout rounding of milliseconds: 0.0005 * 1000 = 0.5 -> 1, 0.0015 * 1000 = 1.5 -> 2, 0.0025 -> 3
        self.assertEqual(settings.readout({"threshold": -1, "minSilence": 0.0005, "padBefore": 0.0015, "padAfter": 0.0025}),
                         "-1 dB  |  1 ms min  |  2/3 ms pad")

    def test_js_round_is_exact_math_round(self):
        # floor(x + 0.5) is wrong for 0.49999999999999994 (x + 0.5 rounds up to 1.0) and for odd integers >= 2**52
        cases = [(0.49999999999999994, 0), (0.5, 1), (1.5, 2), (2.5, 3), (-0.5, 0), (-1.5, -1), (-2.5, -2), (0.4, 0),
                 (-0.49999999999999994, 0), (2.0 ** 52 + 1, 2 ** 52 + 1), (2.0 ** 53, 2 ** 53),
                 (-(2.0 ** 52 + 1), -(2 ** 52 + 1)), (57.49999999999999, 57), (1e300, int(1e300))]
        for x, want in cases:
            self.assertEqual(wav.js_round(x), want, repr(x))
        self.assertEqual(wav.js_round(math.inf), math.inf)
        self.assertEqual(wav.js_round(-math.inf), -math.inf)
        self.assertTrue(math.isnan(wav.js_round(math.nan)))

    def test_combine_and_snap_keep_kind_and_label_that_are_present_even_as_none(self):
        # JSON null is not JS undefined: {"label": null} stays, a missing label stays missing
        self.assertEqual(detect.combine([{"s": 0, "e": 1, "kind": "filler", "label": None}], 0.1),
                         [{"s": 0, "e": 1, "kind": "filler", "label": None}])
        self.assertEqual(detect.combine([{"s": 0, "e": 1, "kind": None}], 0.1), [{"s": 0, "e": 1, "kind": None}])
        self.assertEqual(detect.combine([{"s": 0, "e": 1}], 0.1), [{"s": 0, "e": 1}])
        self.assertEqual(detect.snap([{"s": 1.0, "e": 2.0, "kind": None, "label": None}], 25),
                         [{"s": 1.0, "e": 2.0, "kind": None, "label": None}])
        self.assertEqual(detect.snap([{"s": 1.0, "e": 2.0}], 25), [{"s": 1.0, "e": 2.0}])
        # a null label next to a labelled filler still joins as an empty string, like `r.label || ''`
        got = detect.combine([{"s": 0, "e": 1, "kind": "filler", "label": "um"},
                              {"s": 1.0, "e": 2, "kind": "filler", "label": None}], 0.25)
        self.assertEqual(got, [{"s": 0, "e": 2, "kind": "filler", "label": "um "}])

    def test_word_without_w_is_string_undefined_and_null_is_string_null(self):
        self.assertEqual(fillers.norm(None), "null")
        hit = fillers.find([{"s": 0, "e": 1}], "undefined", "")
        self.assertEqual(hit, [{"s": 0, "e": 1, "kind": "filler", "on": True, "source": "word"}])  # no label key
        hit = fillers.find([{"w": None, "s": 0, "e": 1}], "null", "")
        self.assertEqual(hit, [{"s": 0, "e": 1, "label": None, "kind": "filler", "on": True, "source": "word"}])
        self.assertEqual(fillers.find([{"w": None, "s": 0, "e": 1}], "undefined", ""), [])
        self.assertEqual(fillers.find([{"s": 0, "e": 1}], "null", ""), [])
        two = fillers.find([{"s": 0, "e": 1}, {"s": 1, "e": 2}], "", "undefined undefined")
        self.assertEqual(two, [{"s": 0, "e": 2, "label": "undefined undefined", "kind": "filler", "on": False,
                                "source": "word"}])

    def test_zero_channel_or_zero_bit_wav_with_no_data_has_nan_duration(self):
        for ch, bits in ((0, 16), (1, 0), (0, 0)):
            data = HC.riff(HC.chunk(b"fmt ", HC.fmt_payload(1, ch, 8000, bits)), HC.chunk(b"data", b""))
            r = wav.envelope(data, 0.01)
            self.assertTrue(math.isnan(r["duration"]), (ch, bits))
            self.assertEqual(len(r["env"]), 0)
            self.assertEqual(len(wav.decode(data)["samples"]), 0)
        data = HC.riff(HC.chunk(b"fmt ", HC.fmt_payload(1, 1, 0, 16)), HC.chunk(b"data", b"\x01\x00\x02\x00"))
        self.assertEqual(wav.envelope(data, 0.01)["duration"], math.inf)  # 2 frames / rate 0

    def test_envelope_docstring_says_the_input_is_coerced_to_float32(self):
        doc = detect.envelope.__doc__.lower()
        self.assertIn("float32", doc)
        self.assertIn("coerc", doc)

    def test_total_is_a_plain_left_to_right_sum(self):
        # Python 3.12's sum() of floats is compensated and would give 1.0; the JS loop (and so this twin) gives 0.99999...
        rs = [{"s": 0, "e": 0.1}] * 10
        self.assertEqual(detect.total(rs), 0.9999999999999999)
        self.assertNotEqual(sum(0.1 for _ in range(10)), 0.9999999999999999)  # the trap exists on this interpreter
        self.assertEqual(detect.total([]), 0)

    def test_js_number_printing(self):
        cases = [(-48, "-48"), (-48.0, "-48"), (-44.4, "-44.4"), (0.1 + 0.2, "0.30000000000000004"), (1e-7, "1e-7"),
                 (1.5e-7, "1.5e-7"), (0.000001, "0.000001"), (1e21, "1e+21"), (1e20, "100000000000000000000"),
                 (123456789.125, "123456789.125"), (-0.0, "0"), (0, "0"), (100, "100"), (0.57, "0.57")]
        for v, want in cases:
            self.assertEqual(js_num_str(v), want, v)

    def test_fmt_matches_js_to_fixed_half_up_on_exact_ties(self):
        # 0.25 and 0.75 are exact binary ties: JS toFixed(1) picks the larger, so 0.3 / 0.8
        self.assertEqual([detect.fmt(x) for x in (0.25, 0.75, 0.35, 59.96, 9.96, 125.04)],
                         ["0:00.3", "0:00.8", "0:00.3", "1:00.0", "0:10.0", "2:05.0"])

    def test_norm_whitespace_is_the_js_set(self):
        # NBSP, ideographic space and the BOM are JS whitespace; U+0085 and U+001C are not (Python's \s says they are)
        self.assertEqual(fillers.norm("\u00a0um\u3000"), "um")
        self.assertEqual(fillers.norm("\ufeffuh\u2003"), "uh")
        self.assertEqual(fillers.norm("a\u0085b"), "a\u0085b")
        self.assertEqual(fillers.norm("a\x1cb"), "a\x1cb")
        self.assertEqual(fillers.norm("a\u00a0 \u3000b"), "a b")

    def test_default_lists_and_constants(self):
        self.assertEqual(detect.HOP, 0.01)
        self.assertEqual(detect.SIMPLE, {"soft": 25, "medium": 50, "strong": 80})
        self.assertEqual(len(fillers.parse_list(fillers.DEFAULT_STRONG)), 24)
        self.assertEqual(len(fillers.parse_list(fillers.DEFAULT_SOFT)), 11)
        self.assertIn("\u0627\u0648\u0647", fillers.parse_list(fillers.DEFAULT_STRONG))

    def test_find_example_and_labels(self):
        words = [{"w": "So", "s": 0, "e": 0.2}, {"w": "um,", "s": 0.3, "e": 0.5}, {"w": "you", "s": 0.6, "e": 0.7},
                 {"w": "Know.", "s": 0.7, "e": 0.9}]
        got = fillers.find(words, "um", "you know")
        self.assertEqual(got, [{"s": 0.3, "e": 0.5, "label": "um,", "kind": "filler", "on": True, "source": "word"},
                               {"s": 0.6, "e": 0.9, "label": "you Know.", "kind": "filler", "on": False, "source": "word"}])

    def test_envelope_is_float32_and_sequential_on_a_sine(self):
        rate, n = 48000, 24000
        ints = np.round(0.5 * 32768 * np.sin(2 * np.pi * 1000 * np.arange(n) / rate)).astype("<i2")
        data = HC.riff(HC.chunk(b"fmt ", HC.fmt_payload(1, 1, rate, 16)), HC.chunk(b"data", ints.tobytes()))
        r = wav.envelope(data, 0.01)
        self.assertEqual(r["env"].dtype, np.float32)
        self.assertEqual(len(r["env"]), 50)
        self.assertTrue(np.allclose(r["env"], 20 * math.log10(0.5 / math.sqrt(2)), atol=0.01))
        self.assertEqual(r["duration"], 0.5)
        self.assertEqual(wav.decode(data)["samples"].dtype, np.float32)

    def test_envelope_speed_on_a_ten_minute_file(self):
        rate, frames = 48000, 10 * 60 * 48000
        rng = np.random.default_rng(1)
        with tempfile.TemporaryDirectory() as td:
            t = np.arange(rate * 2) / rate
            burst = (0.3 * np.sin(2 * np.pi * 440 * t) * 32767).astype("<i2")
            quiet = rng.integers(-30, 30, rate * 3).astype("<i2")
            block = np.concatenate([burst, quiet])
            pcm = np.tile(block, frames // len(block) + 1)[:frames]
            p = Path(td) / "ten.wav"
            p.write_bytes(HC.riff(HC.chunk(b"fmt ", HC.fmt_payload(1, 1, rate, 16)), HC.chunk(b"data", pcm.tobytes())))
            data = p.read_bytes()
            t0 = time.perf_counter()
            r = wav.envelope(data, 0.01)
            took = time.perf_counter() - t0
        sys.stderr.write("\n[hush twin] envelope of 10 min 48 kHz mono 16-bit: %.2f s (%d hops)\n" % (took, len(r["env"])))
        self.assertEqual(len(r["env"]), 60000)
        self.assertEqual(r["duration"], 600.0)
        self.assertLess(took, 60.0)  # a per-sample Python loop needs minutes
        # spot check hops against a plain sequential reference (hop 0 is the 440 Hz burst, hop 250 is the noise)
        for i in (0, 7, 199, 250, 59999):
            seg = pcm[i * 480:(i + 1) * 480].astype(np.float64) / 32768
            s = 0.0
            for v in seg.tolist():
                s += v * v
            rms = math.sqrt(s / len(seg))
            want = 20 * math.log10(rms) if rms > 1e-5 else -100.0
            self.assertLessEqual(_ulps(float(r["env"][i]), float(np.float32(want))), 1, i)


if __name__ == "__main__":
    unittest.main()
