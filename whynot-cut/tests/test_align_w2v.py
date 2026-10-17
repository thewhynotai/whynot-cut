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
            "السَّلامُ": "السلام",                # harakat: in the vocab but never emitted by the model: stripped (I4)
            "وَلِلَّهِ": "ولله",                   # fully vocalised (Quranic) text: only the letters remain
            "اٰ": "ا",                 # dagger alef stripped
            "هٰذا": "هذا",   # هٰذا: dagger alef stripped
            "إ": "إ",                 # NFC first: alef + hamza below -> alef with hamza below
            "بٓ": "ب",                 # a madda that does not compose is stripped
            "ﻻ": "لا",                      # presentation form lam-alef (NFKC, M1)
            "ﷲ": "الله",                    # ligature Allah (NFKC); its small alef is stripped
            "ﷺ": "صلىاللهعليهوسلم",         # ligature sallallahu alayhi wa sallam (NFKC, spaces dropped)
            "ﺍﺑﺩ": "ابد",         # isolated / initial presentation forms
            "ڨال": "قال",                        # Gulf / Maghrebi qaf with three dots -> qaf (M1)
            "ڭلب": "كلب",                        # ng (Maghrebi) -> kaf (M1)
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
            self.assertFalse(any(0x064B <= ord(c) <= 0x0655 or ord(c) in (0x0670, 0x0640) for c in got), repr(w))

    def test_ar_readable(self):
        # a word is aligned only when every letter and digit in it has a sound in the Arabic vocab (I1)
        for w in ["مرحبا", "السَّلامُ", "ٱلكتاب", "کتاب", "ﷺ", "مرحبا،", "«قال»", "قال؟"]:
            self.assertTrue(aw.ar_readable(w, AR_VOCAB), repr(w))
        for w in ["MRI", "2024", "٢٠٢٤", "covid-19", "بالـMRI", "عام2026", "Hello", "привет", "", "!!", "ـــ"]:
            self.assertFalse(aw.ar_readable(w, AR_VOCAB), repr(w))


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

    def test_unromanizable_word_keeps_its_times_only(self):
        # per word for every kind (fix round 1, I1 as corrected): upstream gave BOTH words 0.5 and transcriber times;
        # now only the unreadable word keeps its time (aligned False), "با" is aligned
        words = [{"w": "привет", "s": 1.0, "e": 1.5}, {"w": "با", "s": 2.0, "e": 2.4}]
        v = MMS_VOCAB
        fr = FakeRunner(len(v), [[(v["b"], 100, 105, 0.9), (v["a"], 105, 110, 0.9)]])
        out = aw.Aligner("mms", runner=fr, vocab=v).align(self.audio, words)
        self.assertEqual(len(fr.chunks), 1)
        self.assertEqual((out[0]["s"], out[0]["e"], out[0]["score"], out[0]["aligned"]), (1.0, 1.5, 0.5, False))
        self.assertIs(out[1]["aligned"], True)
        self.assertLessEqual(out[0]["e"], out[1]["s"])

    def test_mms_aligns_latin_words_and_flags_every_word(self):
        words = [{"w": "MRI", "s": 1.0, "e": 1.5}, {"w": "با", "s": 2.0, "e": 2.4}]
        out = aw.Aligner("mms", runner=FakeRunner(len(MMS_VOCAB), []), vocab=MMS_VOCAB).align(self.audio, words)
        self.assertEqual([w["aligned"] for w in out], [True, True])        # "mri" is in MMS's latin vocab
        words = [{"w": "日本", "s": 1.0, "e": 1.5}]                          # nothing readable: no model call
        fr = FakeRunner(len(MMS_VOCAB), [])
        out = aw.Aligner("mms", runner=fr, vocab=MMS_VOCAB).align(self.audio, words)
        self.assertEqual((fr.chunks, out[0]["aligned"], out[0]["score"]), ([], False, 0.5))

    def test_ar_unknown_word_keeps_its_times_only(self):
        # I1: per word, not per window - "سلام" is still aligned (was: both words 0.5 with transcriber times)
        words = [{"w": "Hello", "s": 1.0, "e": 1.5}, {"w": "سلام", "s": 2.0, "e": 2.4}]
        v = AR_VOCAB                                          # "سلام" placed near its transcriber time (~2.0-2.4 s)
        fr = FakeRunner(len(v), [[(v["س"], 100, 105, 0.9), (v["ل"], 105, 110, 0.9), (v["ا"], 110, 115, 0.9),
                                  (v["م"], 115, 120, 0.9)]])
        out = aw.Aligner("ar", runner=fr, vocab=AR_VOCAB).align(self.audio, words)
        self.assertEqual(len(fr.chunks), 1)
        self.assertEqual((out[0]["s"], out[0]["e"], out[0]["score"], out[0]["aligned"]), (1.0, 1.5, 0.5, False))
        self.assertIs(out[1]["aligned"], True)
        self.assertLessEqual(out[0]["e"], out[1]["s"])

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


class AlignArPerWord(unittest.TestCase):
    """kind "ar": a word the Arabic model cannot represent (Latin, digits) keeps its transcriber time, is flagged
    aligned=False and never costs its window's other words their alignment (I1); every ar word carries the flag"""

    V = AR_VOCAB

    def setUp(self):
        self.audio = np.zeros(20 * RATE, dtype=np.float32)

    def _words(self, odd=None, odd_s=None, odd_e=None):
        ws = []
        for k in range(20):
            s = 1.0 + 0.5 * k
            ws.append({"w": "با", "s": s, "e": s + 0.4, "k": k})
        if odd is not None:
            ws[10]["w"] = odd
            if odd_s is not None:
                ws[10]["s"], ws[10]["e"] = odd_s, odd_e
        return ws

    def _plan(self, ks, sep=False):
        """word k's two tokens at frames [50+25k, 56+25k) and [56+25k, 62+25k): near its transcriber time"""
        v = self.V
        plan = []
        for n, k in enumerate(ks):
            if sep and n:
                plan.append((v["|"], 50 + 25 * k - 6, 50 + 25 * k - 2, 0.9))
            plan += [(v["ب"], 50 + 25 * k, 56 + 25 * k, 0.9), (v["ا"], 56 + 25 * k, 62 + 25 * k, 0.8)]
        return plan

    def _check(self, out, words, fr, skipped):
        self.assertEqual(len(fr.chunks), 1)
        n = len(fr.chunks[0])
        a0 = max(0.0, words[0]["s"] - 1.5)
        ratio = n / (n // 320) / RATE
        for k, w in enumerate(out):
            self.assertEqual(w["k"], k)
            if k in skipped:
                self.assertIs(w["aligned"], False)
                self.assertEqual(w["score"], 0.5)
            else:
                self.assertIs(w["aligned"], True, k)
                self.assertEqual(w["s"], round(a0 + (50 + 25 * k) * ratio, 3), k)
                self.assertEqual(w["e"], round(a0 + (62 + 25 * k) * ratio, 3), k)
                self.assertEqual(w["score"], round((0.9 + 0.8) / 2, 3))
        for a, b in zip(out, out[1:]):                    # monotonic, non-overlapping
            self.assertLessEqual(a["s"], a["e"])
            self.assertLessEqual(a["e"], b["s"])

    def test_latin_word_inside_arabic_window(self):
        for sep in (False, True):
            words = self._words("MRI")
            fr = FakeRunner(len(self.V), [self._plan([k for k in range(20) if k != 10], sep)])
            out = aw.Aligner("ar", runner=fr, vocab=self.V, word_sep=sep).align(self.audio, words)
            self._check(out, words, fr, {10})
            self.assertEqual((out[10]["s"], out[10]["e"]), (6.0, 6.4))       # transcriber time kept

    def test_digits_only_word_inside_arabic_window(self):
        for odd in ("2024", "٢٠٢٤", "covid-19", "بالـMRI"):
            words = self._words(odd)
            fr = FakeRunner(len(self.V), [self._plan([k for k in range(20) if k != 10])])
            out = aw.Aligner("ar", runner=fr, vocab=self.V).align(self.audio, words)
            self._check(out, words, fr, {10})
            self.assertEqual((out[10]["s"], out[10]["e"]), (6.0, 6.4), odd)

    def test_unaligned_word_is_clamped_between_aligned_neighbours(self):
        words = self._words("MRI", 5.2, 7.1)                  # overlaps words 9 and 11 as aligned
        fr = FakeRunner(len(self.V), [self._plan([k for k in range(20) if k != 10])])
        out = aw.Aligner("ar", runner=fr, vocab=self.V).align(self.audio, words)
        self._check(out, words, fr, {10})
        self.assertEqual(out[10]["s"], out[9]["e"])
        self.assertEqual(out[10]["e"], out[11]["s"])

    def test_english_only_clip_keeps_transcriber_times_without_a_model(self):
        clip = ["This", "is", "an", "MRI", "scan", "2024"]
        words = [{"w": w, "s": 0.5 + k, "e": 0.9 + k} for k, w in enumerate(clip)]
        fr = FakeRunner(len(self.V), [])
        out = aw.Aligner("ar", runner=fr, vocab=self.V).align(self.audio, words)
        self.assertEqual(fr.chunks, [])                       # no aligner at all
        self.assertEqual([(w["s"], w["e"]) for w in out], [(w["s"], w["e"]) for w in words])
        self.assertTrue(all(w["aligned"] is False for w in out))
        al = aw.Aligner("ar", model_dir=None, vocab=self.V)   # no runner, no model dir: never loads a model
        out = al.align(self.audio, words)
        self.assertTrue(all(w["aligned"] is False for w in out))

    def test_whole_unreadable_window_next_to_an_aligned_one(self):
        words = [{"w": "Hello", "s": 1.0, "e": 1.4}, {"w": "world", "s": 1.5, "e": 1.9},
                 {"w": "با", "s": 40.0, "e": 40.4}]
        audio = np.zeros(45 * RATE, dtype=np.float32)
        fr = FakeRunner(len(self.V), [[(self.V["ب"], 60, 64, 0.9), (self.V["ا"], 64, 70, 0.9)]])
        out = aw.Aligner("ar", runner=fr, vocab=self.V).align(audio, words)
        self.assertEqual(len(fr.chunks), 1)
        self.assertEqual([w["aligned"] for w in out], [False, False, True])
        self.assertEqual([(w["s"], w["e"]) for w in out[:2]], [(1.0, 1.4), (1.5, 1.9)])


class AlignNeverRaises(unittest.TestCase):
    """a window whose targets need more frames than the audio has (L + repeats > T) falls back instead of raising
    (I5); upstream raised out of align() here (torchaudio error) - recorded A0 deviation: crash -> score 0.0"""

    def test_forty_heh_laughter_in_a_short_file(self):
        audio = np.zeros(int(1.25 * RATE), dtype=np.float32)
        words = [{"w": "ه" * 40, "s": 0.1, "e": 1.1}]
        fr = FakeRunner(len(AR_VOCAB), [], frames=60)         # T = 60 >= L = 40 but < L + R = 79
        out = aw.Aligner("ar", runner=fr, vocab=AR_VOCAB).align(audio, words)
        self.assertEqual((out[0]["s"], out[0]["e"], out[0]["score"]), (0.1, 1.1, 0.0))
        self.assertIs(out[0]["aligned"], False)

    def test_repeats_need_blanks(self):
        audio = np.zeros(5 * RATE, dtype=np.float32)
        for kind, vocab in (("ar", AR_VOCAB), ("mms", MMS_VOCAB)):
            words = [{"w": "ببب", "s": 1.0, "e": 1.5}, {"w": "دم", "s": 2.0, "e": 2.4}]
            fr = FakeRunner(len(vocab), [], frames=6)             # L = 5 < T = 6 < L + R = 7
            out = aw.Aligner(kind, runner=fr, vocab=vocab).align(audio, words)
            self.assertEqual([(w["s"], w["e"], w["score"]) for w in out], [(1.0, 1.5, 0.0), (2.0, 2.4, 0.0)], kind)

    def test_cross_word_repeat_without_separator(self):
        audio = np.zeros(5 * RATE, dtype=np.float32)
        words = [{"w": "ها", "s": 1.0, "e": 1.5}, {"w": "اب", "s": 2.0, "e": 2.4}]   # ...ا ا... : one repeat
        fr = FakeRunner(len(AR_VOCAB), [], frames=4)               # L = 4 = T: the ">=" guard, as before
        out = aw.Aligner("ar", runner=fr, vocab=AR_VOCAB).align(audio, words)
        self.assertEqual([w["score"] for w in out], [0.0, 0.0])
        fr = FakeRunner(len(AR_VOCAB), [], frames=5)               # T = 5 = L + R: fits exactly
        out = aw.Aligner("ar", runner=fr, vocab=AR_VOCAB).align(audio, words)
        self.assertTrue(all(w["aligned"] for w in out))


class AlignInputContract(unittest.TestCase):
    def test_audio_must_be_mono_float(self):
        words = [{"w": "با", "s": 1.0, "e": 1.5}]
        al = aw.Aligner("ar", runner=FakeRunner(len(AR_VOCAB), []), vocab=AR_VOCAB)
        with self.assertRaises(ValueError):
            al.align(np.zeros((2, 3 * RATE), dtype=np.float32), words)          # stereo
        with self.assertRaises(ValueError):
            al.align(np.zeros(3 * RATE, dtype=np.int16), words)                 # integer PCM
        out = al.align(audio_16k=np.zeros(3 * RATE, dtype=np.float32), words=words)
        self.assertEqual(len(out), 1)


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
