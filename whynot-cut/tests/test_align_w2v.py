# SPDX-License-Identifier: GPL-3.0-or-later
# © 2026 The Why Not AI (thewhynot.ai)
"""3.0 tools track, Task 12 (G-ALIGN): lib/align_w2v.py, the numpy CTC forced aligner that replaces
torchaudio.functional.forced_align (removed from torchaudio after 2.8) under WhyNot Kalam's word alignment.

What is pinned here (engine runtime: numpy, no torch):
* forced_align == a brute-force enumeration of every label sequence that collapses to the targets (>= 200 seeded
  cases incl. repeated tokens that need a blank, T = L + R and T = S edges); torchaudio's tie-breaking on fixtures;
  torchaudio's error cases (T < L + R, blank inside targets, empty targets).
* merge_tokens spans (token, start, end, mean score) like torchaudio's merge_tokens.
* mms_tokens == upstream Kalam roman() (imported from adobe/tools/kalam/_upstream by file path); ar_tokens mapping.
* _windows == upstream _windows on seeded word lists.
* Aligner.align with a fake model: audio window bounds, the two fallbacks, score rounding, the `|` separator.
* place_model / torch_device: the upstream device rule with fakes.
The torchaudio equality on real emissions is checked by adobe/tools/kalam/bench/g_align.py in the scratch venv.
Run:  bash tools/test.sh -p test_align_w2v.py
"""
import sys as _sys
_sys.dont_write_bytecode = True  # keep the plugin folder free of __pycache__
import _isolation  # noqa: F401,E402  G79: sandbox the engine home first (tests/_isolation.py)
import importlib.util  # noqa: E402
import itertools  # noqa: E402
import math  # noqa: E402
import subprocess  # noqa: E402
import sys  # noqa: E402
import unittest  # noqa: E402
import unicodedata  # noqa: E402
from pathlib import Path  # noqa: E402

import numpy as np  # noqa: E402

SK = Path(__file__).resolve().parents[1]
REPO = SK.parent
ENGINE = SK / "engine" / "reel"
sys.path.insert(0, str(ENGINE))
from lib import align_w2v as aw  # noqa: E402

UPSTREAM_ALIGN = REPO / "adobe" / "tools" / "kalam" / "_upstream" / "engine" / "kalam" / "align.py"


HAVE_UPSTREAM = UPSTREAM_ALIGN.is_file()
NO_UPSTREAM = "adobe/tools/kalam/_upstream is not in this tree (the plugin zip ships whynot-cut/ only)"


def _load_upstream():
    if not HAVE_UPSTREAM:
        return None
    spec = importlib.util.spec_from_file_location("kalam_upstream_align_t12", str(UPSTREAM_ALIGN))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # module top level imports json, os, numpy only (torch is lazy)
    return mod


UP = _load_upstream()

# The two models' vocabularies, in id order (vocab.json of the pinned revisions; see the module docstring).
MMS_VOCAB = {t: i for i, t in enumerate(
    ["<blank>", "<pad>", "</s>", "<unk>"] + list("aientousrmkldghybpwcvjzf'qx"))}
AR_VOCAB = {t: i for i, t in enumerate(
    ["<pad>", "<s>", "</s>", "<unk>", "|", "-"] + list("ءآأؤإئابةتثجحخدذرزسشصضطظعغـفقكلمنهوىي")
    + ["\u064b", "\u064c", "\u064d", "\u064e", "\u064f", "\u0650", "\u0651", "\u0652"])}
RATE = 16000


def _log_softmax(x):
    x = np.asarray(x, dtype=np.float64)
    m = x.max(axis=-1, keepdims=True)
    y = x - m - np.log(np.exp(x - m).sum(axis=-1, keepdims=True))
    return y.astype(np.float32)


def _collapse(seq, blank=0):
    out, prev = [], None
    for s in seq:
        if s != prev and s != blank:
            out.append(s)
        prev = s
    return out


def _brute(lp, targets):
    """every label sequence of length T over the C classes that collapses to targets: (best score, best path,
    second-best score). Independent of the DP: plain enumeration."""
    T, C = lp.shape
    best, best_p, second = -math.inf, None, -math.inf
    lp64 = lp.astype(np.float64)
    for seq in itertools.product(range(C), repeat=T):
        if _collapse(seq) != list(targets):
            continue
        sc = float(sum(lp64[t, s] for t, s in enumerate(seq)))
        if sc > best:
            best, best_p, second = sc, seq, best
        elif sc > second:
            second = sc
    return best, best_p, second


class ImportWithoutTorch(unittest.TestCase):
    def test_module_imports_with_torch_blocked(self):
        code = ("import sys; sys.modules['torch'] = None; sys.modules['torchaudio'] = None; "
                "sys.modules['transformers'] = None; sys.path.insert(0, sys.argv[1]); "
                "import lib.align_w2v as m; print('ok', 'torch' in sys.modules and sys.modules['torch'] is not None)")
        r = subprocess.run([sys.executable, "-B", "-c", code, str(ENGINE)], capture_output=True, text=True,
                           timeout=120, encoding="utf-8")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout.strip(), "ok False")


class ForcedAlignBruteForce(unittest.TestCase):
    def _cases(self):
        rng = np.random.default_rng(20261016)
        cases = []
        while len(cases) < 240:
            C = int(rng.integers(3, 5))
            L = int(rng.integers(1, 4))
            tg = [int(x) for x in rng.integers(1, C, L)]
            if len(cases) % 4 == 0 and L >= 2:  # force a repeat that needs a blank between
                tg[1] = tg[0]
            R = sum(1 for i in range(1, L) if tg[i] == tg[i - 1])
            S = 2 * L + 1
            kind = len(cases) % 6
            if kind == 1:
                T = L + R                       # the tightest fit
            elif kind == 2:
                T = S                           # T = S edge
            else:
                T = int(rng.integers(L + R, 7 if C == 4 else 8))
            T = max(T, 1)
            if C == 4 and T > 6:
                T = 6
            if T < L + R:
                continue
            lp = _log_softmax(rng.normal(scale=2.0, size=(T, C)))
            cases.append((lp, tg))
        return cases

    def test_viterbi_equals_brute_force(self):
        exact = repeats = tight = ts = 0
        for lp, tg in self._cases():
            T = lp.shape[0]
            L = len(tg)
            R = sum(1 for i in range(1, L) if tg[i] == tg[i - 1])
            repeats += R > 0
            tight += T == L + R
            ts += T == 2 * L + 1
            labels, scores = aw.forced_align(lp, np.array(tg, dtype=np.int32), blank=0)
            labels = np.asarray(labels)
            self.assertEqual(labels.shape, (T,))
            self.assertEqual(_collapse(labels.tolist()), tg, (lp, tg))
            np.testing.assert_array_equal(np.asarray(scores), lp[np.arange(T), labels])
            best, best_p, second = _brute(lp, tg)
            self.assertAlmostEqual(float(np.asarray(scores, dtype=np.float64).sum()), best, places=4, msg=(lp, tg))
            if best - second > 1e-4:
                self.assertEqual(tuple(labels.tolist()), best_p, (lp, tg))
                exact += 1
        self.assertGreaterEqual(exact, 200)
        self.assertGreater(repeats, 40)
        self.assertGreater(tight, 20)
        self.assertGreater(ts, 20)

    def test_batched_contract_like_torchaudio(self):
        rng = np.random.default_rng(7)
        lp = _log_softmax(rng.normal(size=(9, 4)))
        lab2, sc2 = aw.forced_align(lp, np.array([1, 2, 2], dtype=np.int32))
        lab3, sc3 = aw.forced_align(lp[None], np.array([[1, 2, 2]], dtype=np.int32))
        self.assertEqual(np.asarray(lab3).shape, (1, 9))
        self.assertEqual(np.asarray(sc3).shape, (1, 9))
        np.testing.assert_array_equal(np.asarray(lab3)[0], lab2)
        np.testing.assert_array_equal(np.asarray(sc3)[0], sc2)

    def test_tie_breaking_matches_torchaudio(self):
        # Expected label paths produced by torchaudio 2.8.0 functional.forced_align (CPU) in the scratch venv
        # (D:\ClaudeData\Temp\wnc-p4\align\runs\spike\ties.py). Rule: candidate "skip" (i-2) wins only when strictly
        # greater than both others, "advance" (i-1) only when strictly greater than both, otherwise "stay" (i);
        # at the end the last label wins over the trailing blank only when strictly greater.
        def U(T, C):
            return np.log(np.full((T, C), 1.0 / C)).astype(np.float32)
        q = np.log(np.array([[.5, .5, .0001], [.5, .5, .0001], [.0001, .5, .5], [.5, .0001, .5]])).astype(np.float32)
        fixtures = [
            (U(5, 3), [1, 2], [1, 2, 2, 2, 2]),
            (U(5, 3), [1, 1], [1, 0, 1, 1, 1]),
            (U(7, 3), [1, 2, 1], [1, 2, 1, 1, 1, 1, 1]),
            (U(2, 3), [1, 2], [1, 2]),
            (U(3, 3), [1, 1], [1, 0, 1]),
            (U(4, 3), [2], [2, 2, 2, 2]),
            (q, [1, 2], [1, 1, 1, 2]),
        ]
        for lp, tg, want in fixtures:
            lab, _ = aw.forced_align(lp, np.array(tg, dtype=np.int32))
            self.assertEqual(np.asarray(lab).tolist(), want, tg)

    def test_errors_like_torchaudio(self):
        lp = _log_softmax(np.zeros((3, 3)))
        with self.assertRaises(ValueError):                     # T < L + R: [1,1,1] needs 5 frames
            aw.forced_align(lp, np.array([1, 1, 1], dtype=np.int32))
        with self.assertRaises(ValueError):                     # blank inside the targets
            aw.forced_align(lp, np.array([0, 1], dtype=np.int32))
        with self.assertRaises(ValueError):                     # empty targets
            aw.forced_align(lp, np.array([], dtype=np.int32))
        lab, _ = aw.forced_align(lp, np.array([1, 1], dtype=np.int32))  # T == L + R: exactly fits
        self.assertEqual(np.asarray(lab).tolist(), [1, 0, 1])


class MergeTokens(unittest.TestCase):
    def test_spans(self):
        sp = aw.merge_tokens(np.array([0, 1, 1, 0, 2, 2, 2, 0]),
                             np.array([.1, .2, .3, .4, .5, .6, .7, .8], dtype=np.float32))
        self.assertEqual([(s.token, s.start, s.end) for s in sp], [(1, 1, 3), (2, 4, 7)])
        self.assertAlmostEqual(sp[0].score, 0.25, places=6)
        self.assertAlmostEqual(sp[1].score, 0.6, places=6)

    def test_edges_and_repeats(self):
        sp = aw.merge_tokens(np.array([3, 0, 3, 3]), np.array([1.0, 0.5, 0.2, 0.4], dtype=np.float32))
        self.assertEqual([(s.token, s.start, s.end) for s in sp], [(3, 0, 1), (3, 2, 4)])
        self.assertAlmostEqual(sp[1].score, 0.3, places=6)
        self.assertEqual(aw.merge_tokens(np.array([0, 0]), np.array([1.0, 1.0])), [])

    def test_blank_argument(self):
        sp = aw.merge_tokens(np.array([5, 1, 1, 5]), np.array([1.0, 0.5, 0.5, 1.0]), blank=5)
        self.assertEqual([(s.token, s.start, s.end) for s in sp], [(1, 1, 3)])


class Tokenizers(unittest.TestCase):
    WORDS = ["مرحبا", "السَّلامُ", "عليكم", "آمنة", "إسلام", "مؤمن", "رئيس", "ء", "شخص", "غرفة", "مستشفى", "جيجا",
             "گوگل", "Hello", "AI", "covid-19", "2026", "عام2026", "x7", "QUIZ", "", "привет", "日本", "ٱلكتاب",
             "ﻻ", "کتاب", "یوم", "ـــ", "ة", "زيـــت", "naïve"]

    def test_mms_tokens_by_hand(self):
        # upstream roman(): lower-case, Arabic letter -> latin sound (_AR), digit -> English word (_NUM), keep only
        # single characters present in the vocab
        cases = {"مرحبا": "mrhba", "شخص": "shkhs", "آمنة": "aamna", "ء": "", "Hello": "hello", "QUIZ": "quiz",
                 "2026": "twozerotwosix", "covid-19": "covidonenine", "привет": "", "گوگل": "gwgl",
                 "السَّلامُ": "alslam", "غرفة": "ghrfa", "x7": "xseven"}
        for w, want in cases.items():
            self.assertEqual(aw.mms_tokens(w, MMS_VOCAB), want, repr(w))

    @unittest.skipUnless(HAVE_UPSTREAM, NO_UPSTREAM)
    def test_mms_tokens_equals_upstream_roman(self):
        for w in self.WORDS:
            self.assertEqual(aw.mms_tokens(w, MMS_VOCAB), UP.roman(w, MMS_VOCAB), repr(w))

    @unittest.skipUnless(HAVE_UPSTREAM, NO_UPSTREAM)
    def test_mms_tables_are_upstream_tables(self):
        self.assertEqual(aw._AR, UP._AR)
        self.assertEqual(aw._NUM, UP._NUM)

    def test_ar_tokens(self):
        cases = {
            "مرحبا": "مرحبا",
            "السَّلامُ": "السَّلامُ",             # harakat are in the vocab: kept
            "ٱلكتاب": "الكتاب",                  # alef wasla -> alef
            "کتاب": "كتاب",                      # Persian kaf -> Arabic kaf
            "یوم": "يوم",                        # Persian yeh -> Arabic yeh
            "ھذا": "هذا",                        # heh doachashmee -> heh
            "گول": "جول",                        # Egyptian hard g written gaf -> jeem
            "پيتزا": "بيتزا",
            "ڤيديو": "فيديو",
            "چاي": "جاي",
            "عام2026": "عام",                    # ASCII digits dropped
            "١٩٩٠م": "م",                        # Arabic-Indic digits dropped
            "۲۰": "",                            # Extended Arabic-Indic digits dropped
            "Hello": "",                         # Latin dropped
            "زيـــت": "زيت",                     # tatweel carries no sound: dropped
            "أ-ب|ج": "أبج",                      # the vocab's "-" and "|" never come from a word
            "\u0627\u0653": "آ",                 # NFC: alef + madda -> alef madda
            "\u0627\u0654": "أ",                 # NFC: alef + hamza above -> alef hamza
            "\u064a\u0654": "ئ",
        }
        for w, want in cases.items():
            got = aw.ar_tokens(w, AR_VOCAB)
            self.assertEqual(got, want, repr(w))
            self.assertTrue(all(c in AR_VOCAB for c in got))
            self.assertEqual(got, unicodedata.normalize("NFC", got))


class Windows(unittest.TestCase):
    def test_windows_by_hand(self):
        w = [{"s": 0.0, "e": 8.0}, {"s": 8.1, "e": 12.0}, {"s": 14.0, "e": 20.0}, {"s": 20.1, "e": 24.0},
             {"s": 24.1, "e": 30.0}]
        # words 0..3 end within 25 s of word 0's start; the cut is the biggest gap after words 1..3 (lo = 0 + 3 // 2):
        # gaps 2.0 / 0.1 / 0.1 -> after word 1; words 2..4 then fit in one window
        self.assertEqual(aw._windows(w), [(0, 1), (2, 4)])
        self.assertEqual(aw._windows([]), [])
        self.assertEqual(aw._windows([{"s": 0.0, "e": 40.0}, {"s": 41.0, "e": 42.0}]), [(0, 0), (1, 1)])

    @unittest.skipUnless(HAVE_UPSTREAM, NO_UPSTREAM)
    def test_windows_equal_upstream(self):
        rng = np.random.default_rng(1813)
        for case in range(400):
            n = int(rng.integers(0, 120))
            t, words = float(rng.uniform(0, 2)), []
            for _ in range(n):
                s = t + float(rng.choice([0.0, rng.uniform(0, 0.3), rng.uniform(0, 3.0)]))
                e = s + float(rng.uniform(0.05, 1.2 if case % 5 else 30.0))
                words.append({"w": "x", "s": s, "e": e})
                t = e
            self.assertEqual(aw._windows(words), UP._windows(words), case)


class FakeRunner:
    """Deterministic emissions: T = len(chunk) // 320 frames (about wav2vec2's 20 ms stride); frames listed in
    `plan` (token, start, end, prob) favour that token, every other frame favours the blank (prob 0.9)."""

    def __init__(self, V, plans, frames=None):
        self.V, self.plans, self.frames = V, list(plans), frames
        self.chunks = []

    def __call__(self, chunk):
        self.chunks.append(np.array(chunk, copy=True))
        T = self.frames if self.frames is not None else len(chunk) // 320
        plan = self.plans[len(self.chunks) - 1] if self.plans else []
        lab = np.zeros(T, dtype=int)
        p = np.full(T, 0.9)
        for tok, s, e, pr in plan:
            lab[s:e] = tok
            p[s:e] = pr
        em = np.empty((T, self.V))
        for t in range(T):
            em[t, :] = (1 - p[t]) / (self.V - 1)
            em[t, lab[t]] = p[t]
        return np.log(em).astype(np.float32)


def _bounds(words, i, j, dur):
    """the audio window of words[i..j], written out from the brief (upstream align.py)"""
    ws = words[i:j + 1]
    prev_e = words[i - 1]["e"] if i else 0.0
    next_s = words[j + 1]["s"] if j + 1 < len(words) else dur
    a0 = max(0.0, ws[0]["s"] - 1.5, (prev_e + ws[0]["s"]) / 2 if i else 0.0)
    a1 = min(dur, ws[-1]["e"] + 1.5, max(ws[-1]["e"] + 0.3, (ws[-1]["e"] + next_s) / 2))
    return a0, a1


class AlignFakeModel(unittest.TestCase):
    def setUp(self):
        self.audio = (np.sin(np.arange(20 * RATE) / 7.0) * 0.1).astype(np.float32)   # 20 s

    def test_single_window_times_and_score_rounding(self):
        words = [{"w": "با", "s": 5.0, "e": 5.5, "id": 1}, {"w": "دم", "s": 6.0, "e": 6.4}]
        # mms tokens: "با" -> "ba", "دم" -> "dm"
        v = MMS_VOCAB
        plan = [(v["b"], 20, 25, 0.81234), (v["a"], 25, 30, 0.7), (v["d"], 60, 64, 0.95), (v["m"], 66, 70, 0.6)]
        fr = FakeRunner(len(v), [plan])
        al = aw.Aligner("mms", runner=fr, vocab=v)
        out = al.align(self.audio, words)
        a0, a1 = _bounds(words, 0, 1, 20.0)
        self.assertAlmostEqual(a0, 3.5)
        self.assertAlmostEqual(a1, 7.9)
        n = int(a1 * RATE) - int(a0 * RATE)
        self.assertEqual(len(fr.chunks), 1)
        self.assertEqual(len(fr.chunks[0]), n)
        np.testing.assert_array_equal(fr.chunks[0], self.audio[int(a0 * RATE):int(a1 * RATE)])
        T = n // 320
        ratio = n / T / RATE
        self.assertEqual(out[0]["s"], round(a0 + 20 * ratio, 3))
        self.assertEqual(out[0]["e"], round(a0 + 30 * ratio, 3))
        self.assertEqual(out[1]["s"], round(a0 + 60 * ratio, 3))
        self.assertEqual(out[1]["e"], round(a0 + 70 * ratio, 3))
        self.assertEqual(out[0]["score"], round((0.81234 + 0.7) / 2, 3))     # 0.75617 -> 0.756
        self.assertEqual(out[0]["score"], 0.756)
        self.assertEqual(out[1]["score"], round((0.95 + 0.6) / 2, 3))
        self.assertEqual(out[0]["id"], 1)                                       # other keys kept
        self.assertEqual(words[0]["s"], 5.0)                                    # input not mutated
        self.assertNotIn("score", words[0])

    def test_multi_window_bounds(self):
        words, t = [], 0.4
        for k in range(36):
            gap = 0.9 if k == 22 else 0.15
            words.append({"w": "با", "s": round(t, 3), "e": round(t + 0.8, 3)})
            t += 0.8 + gap
        dur = 40.0
        audio = np.zeros(int(dur * RATE), dtype=np.float32)
        wins = aw._windows(words)                    # == upstream: Windows.test_windows_equal_upstream
        self.assertGreater(len(wins), 1)
        fr = FakeRunner(len(MMS_VOCAB), [])          # blank everywhere: forced path still places every token
        out = aw.Aligner("mms", runner=fr, vocab=MMS_VOCAB).align(audio, words)
        self.assertEqual(len(fr.chunks), len(wins))
        for (i, j), ch in zip(wins, fr.chunks):
            # upstream updates the words in place window by window: the previous window's end is the ALIGNED one
            state = out[:i] + words[i:]
            a0, a1 = _bounds(state, i, j, dur)
            self.assertEqual(len(ch), int(a1 * RATE) - int(a0 * RATE))
        self.assertTrue(all(0.0 <= w["score"] <= 1.0 for w in out))

    def test_unromanizable_word_keeps_times_score_half(self):
        words = [{"w": "привет", "s": 1.0, "e": 1.5}, {"w": "با", "s": 2.0, "e": 2.4}]
        fr = FakeRunner(len(MMS_VOCAB), [])
        out = aw.Aligner("mms", runner=fr, vocab=MMS_VOCAB).align(self.audio, words)
        self.assertEqual(fr.chunks, [])
        self.assertEqual([(w["s"], w["e"], w["score"]) for w in out], [(1.0, 1.5, 0.5), (2.0, 2.4, 0.5)])

    def test_ar_unknown_word_keeps_times_score_half(self):
        words = [{"w": "Hello", "s": 1.0, "e": 1.5}, {"w": "سلام", "s": 2.0, "e": 2.4}]
        out = aw.Aligner("ar", runner=FakeRunner(len(AR_VOCAB), []), vocab=AR_VOCAB).align(self.audio, words)
        self.assertEqual([(w["s"], w["e"], w["score"]) for w in out], [(1.0, 1.5, 0.5), (2.0, 2.4, 0.5)])

    def test_too_many_targets_score_zero(self):
        words = [{"w": "بابا", "s": 1.0, "e": 1.5}]          # "baba": 4 targets
        for frames in (3, 4):                                # len(targets) >= T -> 0.0 (">=" as upstream)
            out = aw.Aligner("mms", runner=FakeRunner(len(MMS_VOCAB), [], frames=frames),
                             vocab=MMS_VOCAB).align(self.audio, words)
            self.assertEqual((out[0]["s"], out[0]["e"], out[0]["score"]), (1.0, 1.5, 0.0), frames)
        out = aw.Aligner("mms", runner=FakeRunner(len(MMS_VOCAB), [], frames=5),
                         vocab=MMS_VOCAB).align(self.audio, words)
        self.assertGreater(out[0]["score"], 0.0)

    def test_ar_word_separator(self):
        v = AR_VOCAB
        words = [{"w": "با", "s": 5.0, "e": 5.5}, {"w": "دم", "s": 6.0, "e": 6.4}]
        seen = []

        def fa(lp, targets, blank=0):
            seen.append(np.asarray(targets).tolist())
            return aw.forced_align(lp, targets, blank=blank)
        plan = [(v["ب"], 20, 25, 0.9), (v["ا"], 25, 30, 0.9), (v["|"], 40, 45, 0.9), (v["د"], 60, 64, 0.9),
                (v["م"], 66, 70, 0.9)]
        out = aw.Aligner("ar", runner=FakeRunner(len(v), [plan]), vocab=v, word_sep=True, fa=fa).align(
            self.audio, words)
        self.assertEqual(seen, [[v["ب"], v["ا"], v["|"], v["د"], v["م"]]])
        a0, a1 = _bounds(words, 0, 1, 20.0)
        n = int(a1 * RATE) - int(a0 * RATE)
        ratio = n / (n // 320) / RATE
        self.assertEqual((out[0]["s"], out[0]["e"]), (round(a0 + 20 * ratio, 3), round(a0 + 30 * ratio, 3)))
        self.assertEqual((out[1]["s"], out[1]["e"]), (round(a0 + 60 * ratio, 3), round(a0 + 70 * ratio, 3)))
        seen.clear()
        aw.Aligner("ar", runner=FakeRunner(len(v), [plan]), vocab=v, fa=fa).align(self.audio, words)
        self.assertEqual(seen, [[v["ب"], v["ا"], v["د"], v["م"]]])           # no separator by default

    def test_bad_kind(self):
        with self.assertRaises(ValueError):
            aw.Aligner("xx", runner=FakeRunner(3, []), vocab={"<pad>": 0})


class DevicePlacement(unittest.TestCase):
    class _M:
        def __init__(self):
            self.moves = []

        def to(self, dev):
            self.moves.append(dev)
            return self

    def test_torch_device(self):
        self.assertEqual(aw.torch_device(probe=lambda: True), "cuda")
        self.assertEqual(aw.torch_device(probe=lambda: False), "cpu")

        def boom():
            raise RuntimeError("no driver")
        self.assertEqual(aw.torch_device(probe=boom), "cpu")

    def test_place_model_probe(self):
        m = self._M()
        got, dev = aw.place_model(m, "cuda", probe=lambda model, d: None)
        self.assertEqual((dev, m.moves), ("cuda", ["cuda"]))

        def fail(model, d):
            raise RuntimeError("no kernel image is available for execution on the device")
        m = self._M()
        got, dev = aw.place_model(m, "cuda", probe=fail)
        self.assertEqual((dev, m.moves), ("cpu", ["cuda", "cpu"]))
        m = self._M()
        got, dev = aw.place_model(m, "cpu", probe=fail)
        self.assertEqual((dev, m.moves), ("cpu", ["cpu"]))


if __name__ == "__main__":
    unittest.main()
