# SPDX-License-Identifier: GPL-3.0-or-later
# © 2026 The Why Not AI (thewhynot.ai)
"""3.0 Phase 4 Task 25 + K-T7, round 4, the shared reader part (lane 5 b563d74 P1-4): a number with «و», «ب», «ف»,
«ل» or «ك» written onto it is read as the number («بربع ساعة», «بخمستاشر يوم», «ب٥ دقايق»), and the short English
time units ("hrs", "min", "secs", "wks", "yrs") are time words. Goes with numbers-glued-and-short-units.patch.
Run:  bash tools/test.sh -p test_safety_meaning_round4_reader.py
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
from lib.safety import differences as D  # noqa: E402
from lib.safety.numbers import fold, quantities  # noqa: E402


def q(text):
    return [(x["value"], x["kind"], x["unit"]) for x in quantities([fold(w) for w in text.split()])]


class TestGluedNumbers(unittest.TestCase):
    def test_each_clitic_before_a_number_word_or_digits(self):
        for text, want in (("قبل الأكل بربع ساعة", [(0.25, "duration", "hour")]),
                           ("قبل الأكل بنص ساعة", [(0.5, "duration", "hour")]),
                           ("قبل العملية بخمستاشر يوم", [(15, "duration", "day")]),
                           ("قبل العملية بخمس أيام", [(5, "duration", "day")]),
                           ("قبل الأكل ب٥ دقايق", [(5, "duration", "minute")]),
                           ("قبل الأكل ب٥٠ دقيقة", [(50, "duration", "minute")]),
                           ("خدي الدوا لعشرة أيام", [(10, "duration", "day")]),
                           ("خدي فخمسة مجم", [(5, "dose", "mg")]),
                           ("كتسعة أيام كده", [(9, "duration", "day")])):
            with self.subTest(text=text):
                self.assertEqual(q(text), want)

    def test_everyday_words_are_not_read_as_numbers(self):
        for text in ("لست متأكد من الكلام ده", "اشربي الدوا بمية", "بالليل قبل النوم", "كده كويس", "بساعة"):
            with self.subTest(text=text):
                self.assertEqual([x for x in q(text) if x[1] != "duration" or x[0] is not None], [])

    def test_the_takes_now_differ_in_number_or_timing(self):
        for a, b in (("الأنسولين قبل الأكل بربع ساعة", "الأنسولين قبل الأكل بساعة"),
                     ("وقفي الدوا قبل العملية بخمستاشر يوم", "وقفي الدوا قبل العملية بخمس أيام"),
                     ("الأنسولين قبل الأكل ب٥ دقايق", "الأنسولين قبل الأكل ب٥٠ دقيقة")):
            with self.subTest(a=a):
                self.assertTrue(set(D.compare(a.split(), b.split())) & {"numbers", "timing"})


class TestShortUnits(unittest.TestCase):
    def test_short_english_time_units(self):
        for text, want in (("wait 2 hrs", [(2, "duration", "hour")]), ("wait 2 hr", [(2, "duration", "hour")]),
                           ("wait 5 min", [(5, "duration", "minute")]), ("wait 5 mins", [(5, "duration", "minute")]),
                           ("hold 30 secs", [(30, "duration", "second")]), ("for 2 wks", [(2, "duration", "week")]),
                           ("for 3 yrs", [(3, "duration", "year")])):
            with self.subTest(text=text):
                self.assertEqual(q(text), want)

    def test_takes_in_short_units_differ_in_numbers(self):
        for a, b in (("wait 2 hrs before eating", "wait 2 mins before eating"),
                     ("wait 5 min before eating", "wait 5 hr before eating")):
            with self.subTest(a=a):
                self.assertIn("numbers", D.compare(a.split(), b.split()))

    def test_the_same_duration_in_two_writings_is_no_difference(self):
        self.assertEqual(D.compare("wait 2 hours before eating".split(), "wait 2 hrs before eating".split()), {})

    def test_vitamin_d_is_not_a_day(self):
        self.assertEqual(q("take vitamin d"), [])


class TestCutProposalsWithTheReader(unittest.TestCase):
    def test_case_a_differs_in_meaning(self):
        pre = "يا جماعة الدكتور قال الأنسولين قبل الأكل "
        a, b = pre + "بربع ساعة وده مهم جدا للمريض", pre + "بساعة وده مهم جدا للمريض"
        words, t = [], 0
        for i, w in enumerate(a.split() + b.split(), 1):
            words.append({"id": i, "segment_id": 1, "word": w, "start_ms": t, "end_ms": t + 300, "probability": 0.95})
            t += 300 + (700 if i == len(a.split()) else 60)
        [r] = [p for p in C.compute(words)["proposals"] if p["kind"] == "retake"]
        self.assertEqual(r["default"], "keep")
        self.assertTrue(set(r["differs"]) & {"numbers", "timing"})


if __name__ == "__main__":
    unittest.main()
