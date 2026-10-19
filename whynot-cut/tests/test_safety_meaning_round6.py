# SPDX-License-Identifier: GPL-3.0-or-later
# © 2026 The Why Not AI (thewhynot.ai)
"""3.0 Phase 4 Task 25 + K-T7, round 6 (executor ruling after review e4ed4c6, the last one):
- P1: a false start is never pre-ticked: always unticked with «بداية مقطوعة: راجعها قبل ما تشيلها» / "false start:
  check it before removing", still in the table (a short negation that starts the next word: «مش مشكلة», "not
  noticeable"), for a general and a medical client;
- P2: 1–3 letters right after a number written in digits are its unit ("5 m" ≠ "5 h", "2 d" ≠ "2 h", «٥ د» ≠ «٥ س»,
  glued "5m" / "5h" too): K-T7 ⚠ with no best, Task 25 unticked; «vitamin D», "D3", "B12", "vitamin D 1000" stay as
  they were;
- P3: a take of cap length ended by a pause only is capped (P3-1); "less" is a negating tail (P3-2); a Latin "sh"
  ending is a negation (P3-3).
Run:  bash tools/test.sh -p test_safety_meaning_round6.py
"""
import sys as _sys
_sys.dont_write_bytecode = True  # keep the plugin folder free of __pycache__
import _isolation  # noqa: F401,E402  G79: sandbox the engine home first (tests/_isolation.py)
import unittest
from pathlib import Path

sys = _sys
SK = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SK / "engine" / "reel"))

from lib import cut_proposals as C  # noqa: E402
from lib.safety import numbers as NU  # noqa: E402
from lib.safety import takes as T  # noqa: E402

GENERAL = {"never": False, "domains": ["medical", "religious"], "client": ["general"], "unset": False,
           "unclear": False, "problem": None, "problem_ar": None}
MEDICAL = {"never": True, "domains": ["medical", "religious"], "client": ["medical"], "unset": False,
           "unclear": False, "problem": None, "problem_ar": None}
RULES = (("general", GENERAL), ("medical", MEDICAL))
FS_AR = "بداية مقطوعة: راجعها قبل ما تشيلها"
FS_EN = "false start: check it before removing"
CAP_EN = "the retake is longer than the limit: check the cut by hand"


def cfg_with(**values):
    return {"values": {**C.DEFAULTS, **values}, "fillers": {k: list(v) for k, v in C.FILLERS.items()}}


def said(text, at, dur=200, gap=60, p=0.95):
    """One sentence, every word 300 ms with 60 ms between; the word at index `at` lasts `dur` ms, then `gap` ms."""
    out, t = [], 0
    for i, w in enumerate(text.split()):
        d, g = (dur, gap) if i == at else (300, 60)
        out.append({"id": i + 1, "segment_id": 1, "word": w, "start_ms": t, "end_ms": t + d,
                    "probability": p if i == at else 0.95})
        t += d + g
    return out


def two_takes(a, b, gap_ms=900):
    out, t, wid = [], 0, 1
    for s, text in enumerate((a, b), 1):
        toks = text.split()
        for k, tok in enumerate(toks):
            out.append({"id": wid, "segment_id": 1, "word": tok, "start_ms": t, "end_ms": t + 300, "probability": 0.95})
            wid += 1
            t += 300 + (gap_ms if k == len(toks) - 1 else 60)
    return out


def retake(ws, rule=GENERAL, lang="ar"):
    got = [p for p in C.compute(ws, lang=lang, rule=rule)["proposals"] if p["kind"] == "retake"]
    assert len(got) == 1, got
    return got[0]


def group(a, b):
    out, t, wid = [], 0, 1
    for s, text in enumerate((a, b), 1):
        toks = text.split()
        for k, tok in enumerate(toks):
            out.append({"id": wid, "segment_id": s, "word": tok, "start_ms": t, "end_ms": t + 300, "probability": 0.95})
            wid += 1
            t += 300 + (900 if k == len(toks) - 1 else 60)
    got = T.groups(out)
    assert len(got) == 1, (a, b, got)
    return got[0]


# --- P1: a false start is never pre-ticked ------------------------------------------------------------------------------
REVIEW_FORMS = (      # review e4ed4c6 P1-1: (sentence, index of the short negation)
    ("الدكتور قال إن الدوا ده مش مشكلة خالص للحامل.", 5),
    ("الصيام للحامل مش مشروع في الحالة دي.", 2),
    ("الدكتور مش مشغول النهاردة خالص.", 1),
    ("هو ما ماشيش على الدوا ده.", 1),
    ("الدكتور قال لا لازم تاخدي الدوا.", 2),
    ("the side effect is not noticeable at all.", 4),
    ("this risk is not notable for you.", 3),
    ("your result is no normal thing.", 3),
)
OWN_FORMS = (         # not in the review
    ("الحباية دي مش مشهورة في مصر خالص.", 2),
    ("الفستان ده لا لايق عليكي خالص.", 2),
    ("الدوا ده مو موجود في الصيدلية.", 2),
    ("there was no notice before the change.", 2),
    ("she was not notified about the dose.", 2),
    ("this pill is never nevertheless safe.", 3),
)
TIMINGS = ((200, 60, 0.95), (240, 60, 0.95), (200, 400, 0.95), (300, 60, 0.5))   # review: 200, 240 ms, 400 ms gap, p 0.5


class TestAFalseStartIsNeverTicked(unittest.TestCase):
    def check(self, text, at, rule, cfg=None, timing=(200, 60, 0.95)):
        lang = "en" if text.isascii() else "ar"
        ws = said(text, at, *timing)
        res = C.compute(ws, lang=lang, rule=rule, cfg=cfg)
        neg = ws[at]["id"]
        ticked = [p for p in res["proposals"] if p["default"] == "proposed" and neg in p["word_ids"]]
        self.assertEqual(ticked, [], (text, timing))
        fs = [p for p in res["proposals"] if p["kind"] == "false_start"]
        self.assertTrue(fs, (text, timing, res["proposals"]))        # still in the table for the editor
        for p in fs:
            self.assertEqual(p["default"], "keep")
            self.assertIn(FS_AR, p["reason"])
            self.assertIn(FS_EN, p["reason_en"])
            self.assertLessEqual(p["confidence"], (cfg or {"values": C.DEFAULTS})["values"]["conf_on_purpose"])
        self.assertEqual([p["word_ids"] for p in fs], [[neg]])

    def test_f1_the_review_forms(self):
        for text, at in REVIEW_FORMS:
            for name, rule in RULES:
                for timing in TIMINGS:
                    with self.subTest(text=text, client=name, timing=timing):
                        self.check(text, at, rule, timing=timing)

    def test_f2_forms_not_in_the_review(self):
        for text, at in OWN_FORMS:
            for name, rule in RULES:
                with self.subTest(text=text, client=name):
                    self.check(text, at, rule)

    def test_f3_also_when_the_client_trusts_repeats(self):
        for text, at in REVIEW_FORMS[:1] + REVIEW_FORMS[5:6]:
            with self.subTest(text=text):
                self.check(text, at, GENERAL, cfg_with(conf_on_purpose=0.95))

    def test_f4_a_real_false_start_is_still_shown(self):
        ws = said("أنا عاو عاوزك تاخدي بالك.", 1, 150, 100, 0.4)
        fs = [p for p in C.compute(ws, rule=GENERAL)["proposals"] if p["kind"] == "false_start"]
        self.assertEqual([(p["words"], p["default"]) for p in fs], [(["عاو"], "keep")])
        self.assertIn(FS_AR, fs[0]["reason"])
        self.assertIn("«عاوزك»", fs[0]["reason"])            # the reason still names the word said again


# --- P2: 1–3 letters after a digit are a unit -------------------------------------------------------------------------------
HM_PAIRS = (
    ("the doctor said rest for 5 m.", "the doctor said rest for 5 h."),
    ("the doctor said wait 2 d before the next dose.", "the doctor said wait 2 h before the next dose."),
    ("the doctor said rest for 5m.", "the doctor said rest for 5h."),
    ("الدكتور قال ترتاحي ٥ د.", "الدكتور قال ترتاحي ٥ س."),
    ("الدكتور قال ترتاحي ٥د.", "الدكتور قال ترتاحي ٥س."),
)


class TestLettersAfterADigitAreAUnit(unittest.TestCase):
    def test_u1_kt7_warns_and_task25_unticks(self):
        for a, b in HM_PAIRS:
            lang = "en" if a.isascii() else "ar"
            with self.subTest(kt7=a):
                self.assertIn("numbers", C.compare_takes(a.split(), b.split()))
                g = group(a, b)
                self.assertIsNone(g["best"], g["differ"])
                self.assertIn("⚠", g["line_ar"])
                self.assertTrue(g["differ"].get("pairs"))
            for name, rule in RULES:
                with self.subTest(a=a, client=name):
                    p = retake(two_takes(a, b), rule, lang)
                    self.assertEqual(p["default"], "keep")
                    self.assertIn("numbers", p["differs"])
                    self.assertIn("differ in meaning", p["reason_en"])

    def test_u2_the_same_letters_are_the_same(self):
        for a, _ in HM_PAIRS:
            with self.subTest(a=a):
                self.assertEqual(C.compare_takes(a.split(), a.split()), {})

    def test_u3_vitamin_d_d3_b12_stay_safe(self):
        def q(s):
            return [(x["value"], x["kind"], x["unit"]) for x in NU.quantities([NU.fold(w) for w in s.split()])]
        self.assertEqual(q("vitamin D 1000"), [(1000, "number", None)])
        self.assertEqual(q("vitamin D 5 mg"), [(5, "dose", "mg")])
        self.assertEqual(q("take vitamin D3 daily"), [])
        self.assertEqual(q("take vitamin B12 daily"), [])
        self.assertEqual(C.compare_takes("take vitamin D 1000 daily".split(), "take vitamin D 1000 daily".split()), {})
        self.assertEqual(C.compare_takes("take vitamin D3 daily".split(), "take vitamin D3 daily".split()), {})
        a, b = "the doctor said take vitamin D 1000 every day.", "the doctor said take vitamin D 1000 every day please."
        self.assertNotIn("numbers", group(a, b)["differ"])

    def test_u4_linking_words_pronouns_and_ordinals_are_no_unit(self):
        def q(s):
            return [(x["value"], x["unit"]) for x in NU.quantities([NU.fold(w) for w in s.split()])]
        for w in ("m", "h", "d", "s", "am", "pm", "د", "س", "م"):
            self.assertEqual(NU.digit_unit(NU.fold(w)), NU.fold(w))
        for w in ("or", "a", "x", "to", "in", "you", "st", "th", "او", "في", "و", "من", "mins", "", "5", "m5"):
            with self.subTest(w=w):
                self.assertIsNone(NU.digit_unit(NU.fold(w)))
        # (only after digits: a spelled number keeps its reading, "rest five m")
        for s in ("take 2 or 3", "the 1st day", "take 5 x", "خدي ٢ او ٣", "خدي ٢ في ٣", "٥ و ٦", "rest five m",
                  "ترتاحي خمسة د"):
            with self.subTest(s=s):
                self.assertFalse([u for _, u in q(s) if u and u.startswith("?")], q(s))
        self.assertEqual(q("take 5 a day")[0][1], q("take 5 every day")[0][1])
        self.assertEqual(q("rest 5 m"), [(5, "?m")])
        self.assertEqual(q("rest 5h"), [(5, "?h")])
        self.assertEqual(q("ترتاحي ٥ د"), [(5, "?د")])


# --- P3 ---------------------------------------------------------------------------------------------------------------------
L13 = "الدكتور قال إن الحباية دي للحامل في الشهور الأولى والتانية مش آمنة خالص."


class TestCheapP3s(unittest.TestCase):
    def test_p3_1_a_take_of_cap_length_ended_by_a_pause_only_is_capped(self):
        ws = two_takes(L13, L13)
        n = len(L13.split())
        k = n + 12 - 1                                         # word 12 of the second take
        shift = 400 - (ws[k + 1]["start_ms"] - ws[k]["end_ms"])
        for w in ws[k + 1:]:
            w["start_ms"] += shift
            w["end_ms"] += shift
        p = retake(ws, GENERAL)
        self.assertEqual(p["default"], "keep", p["reason_en"])
        self.assertIn(CAP_EN, p["reason_en"])
        # a closed 12-word take and a short take that ends at a pause are not capped
        L12 = "الدكتور قال إن الحباية دي للحامل في الشهور الأولى مش آمنة خالص."
        self.assertNotIn(CAP_EN, retake(two_takes(L12, L12))["reason_en"])
        self.assertNotIn(CAP_EN, retake(two_takes("الحباية دي آمنة للحامل.", "الحباية دي آمنة للحامل"))["reason_en"])

    def test_p3_2_less_is_a_negating_tail(self):
        for frag, word in (("harm", "harmless"), ("care", "careless"), ("use", "useless"), ("pain", "painless")):
            with self.subTest(word=word):
                self.assertFalse(C.cut_off(frag, [word]))
        p = retake(two_takes("the doctor said this pill is harm", "the doctor said this pill is harmless for women."),
                   GENERAL, "en")
        self.assertEqual(p["default"], "keep")
        self.assertTrue(C.cut_off("preg", ["pregnant"]))

    def test_p3_3_a_latin_sh_ending_is_a_negation(self):
        for frag, word in (("byakol", "byakolsh"), ("me", "mesh"), ("bey2ool", "bey2oolshi"), ("3ando", "3andosh")):
            with self.subTest(word=word):
                self.assertFalse(C.cut_off(frag, [word]))
        p = retake(two_takes("el doctor 2al el dawa da byakol", "el doctor 2al el dawa da byakolsh el daght khales."),
                   GENERAL, "en")
        self.assertEqual(p["default"], "keep")


if __name__ == "__main__":
    unittest.main()
