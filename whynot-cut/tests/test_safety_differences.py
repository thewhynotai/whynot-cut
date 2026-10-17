# SPDX-License-Identifier: GPL-3.0-or-later
# © 2026 The Why Not AI (thewhynot.ai)
"""3.0 Phase 4 Task 25 / K-T7 follow-up: one reader of what two takes of a line do not share in meaning (numbers and
doses, negation, timing). A retake whose takes differ in any of those is never pre-ticked, and the reason names the
differing words, Arabic first.
Run:  bash tools/test.sh -p test_safety_differences.py
"""
import sys as _sys
_sys.dont_write_bytecode = True  # keep the plugin folder free of __pycache__
import _isolation  # noqa: F401,E402  G79: sandbox the engine home first (tests/_isolation.py)
import unittest
from pathlib import Path

sys = _sys
SK = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SK / "engine" / "reel"))

from lib.safety import differences as D  # noqa: E402


def cmp(a, b):
    return D.compare(a.split(), b.split())


class TestNegation(unittest.TestCase):
    def test_a_negation_word_said_in_one_take_only(self):
        d = cmp("الدوا ده بيقلل الضغط", "الدوا ده مش بيقلل الضغط")
        self.assertEqual(set(d), {"negation"})
        self.assertEqual((d["negation"]["a"], d["negation"]["b"]), ([], ["مش"]))

    def test_a_negated_verb_and_english_contractions(self):
        for a, b in (("الدوا ده بيقلل الضغط", "الدوا ده مبيقللش الضغط"),
                     ("it raises the pressure", "it doesn't raise the pressure"),
                     ("it is safe", "it isn't safe"),
                     ("it is safe", "it isn’t safe")):
            with self.subTest(a=a, b=b):
                self.assertIn("negation", cmp(a, b))

    def test_two_ways_of_saying_not_are_the_same_meaning(self):
        self.assertEqual(cmp("الدوا ده مش بيقلل الضغط", "الدوا ده مبيقللش الضغط"), {})


class TestNumbersAndTiming(unittest.TestCase):
    def test_dose_value_differs(self):
        d = cmp("خدي ٥٠٠ مجم", "خدي 250 مجم")
        self.assertEqual(set(d), {"numbers"})
        self.assertEqual((d["numbers"]["a"], d["numbers"]["b"]), (["٥٠٠ مجم"], ["250 مجم"]))

    def test_same_dose_in_other_digits_is_the_same(self):
        self.assertEqual(cmp("خدي ٥٠٠ مجم", "خدي 500 مجم"), {})

    def test_one_pill_said_with_the_unit_first(self):
        self.assertIn("numbers", cmp("خدي حباية واحدة", "خدي حبايتين"))

    def test_time_of_day(self):
        d = cmp("خدي حباية واحدة الصبح", "خدي حباية واحدة بالليل")
        self.assertEqual(set(d), {"timing"})
        self.assertEqual((d["timing"]["a"], d["timing"]["b"]), (["الصبح"], ["بالليل"]))

    def test_meals_days_and_english(self):
        for a, b in (("خدي الدوا بعد الفطار", "خدي الدوا بعد الغدا"),
                     ("خدي الدوا قبل الأكل", "خدي الدوا بعد الأكل"),
                     ("الحقنة يوم السبت", "الحقنة يوم الحد"),
                     ("take it before meals", "take it after meals"),
                     ("take it in the morning", "take it at night")):
            with self.subTest(a=a, b=b):
                self.assertEqual(set(cmp(a, b)), {"timing"})

    def test_an_everyday_number_word_counts_only_against_a_number(self):
        """«واحد» (someone) in one take only is no number; «خمسة» → «ست» is (blind set b2)."""
        self.assertEqual(cmp("أنا كنت ماشي وشفت واحد", "أنا كنت ماشي وشفت راجل بيجري"), {})
        self.assertIn("numbers", cmp("خدي خمسة", "خدي ست"))

    def test_the_meal_or_sleep_word_within_reach(self):
        self.assertEqual(cmp("take it with food", "take it with a full meal"), {})       # blind set b3
        self.assertEqual(set(cmp("خديها قبل ما تنامي", "خديها بعد ما تنامي")), {"timing"})

    def test_a_clitic_does_not_make_another_time(self):
        self.assertEqual(cmp("خديها بالليل", "خديها الليل"), {})


class TestReviewRound1(unittest.TestCase):
    """Fresh-eyes review (Opus), round 1."""

    def test_c1_how_often_is_read(self):
        for a, b in (("خدي الحقنة كل أسبوع", "خدي الحقنة كل شهر"),
                     ("take it once a day with water", "take it once a week with water"),
                     ("مرة في اليوم", "مرة في الأسبوع"),
                     ("خديها يوميا", "خديها أسبوعيا")):
            with self.subTest(a=a, b=b):
                d = cmp(a, b)
                self.assertIn("timing", d)
                self.assertTrue(d["timing"]["a"] and d["timing"]["b"], d)
        for a, b in (("خديها يوميا", "خديها كل يوم"), ("take it daily", "take it every day")):
            with self.subTest(same=a):
                self.assertEqual(cmp(a, b), {})

    def test_c2_ghair_and_min_ghair_are_negation(self):
        self.assertIn("negation", cmp("ده دوا امن جدا للأطفال", "ده دوا غير امن للأطفال"))
        self.assertIn("negation", cmp("خدي الدوا بالأكل", "خدي الدوا من غير أكل"))
        self.assertEqual(cmp("خديه من غير أكل", "خديه بدون أكل"), {})

    def test_i1_ma_as_a_connector_and_wala_as_or_are_no_negation(self):
        for a, b in (("خدي الدوا قبل ما تنامي على طول", "خدي الدوا قبل النوم على طول"),
                     ("زي ما قلتلك الدوا ده مهم", "الدوا ده مهم جدا"),
                     ("الصبح أو بالليل", "الصبح ولا بالليل")):
            with self.subTest(a=a):
                self.assertNotIn("negation", cmp(a, b))
        for a, b in (("خدي الدوا ده", "ولا تاخدي الدوا ده"), ("فيه حاجة", "ولا حاجة"),
                     ("خدي ده", "لا ده ولا ده"), ("ما تاخديش الدوا", "تاخدي الدوا")):
            with self.subTest(neg=b):
                self.assertIn("negation", cmp(a, b))

    def test_i2_relative_days(self):
        for a, b in (("ابدأي الدوا النهارده", "ابدأي الدوا بكرة"), ("start it today", "start it tomorrow"),
                     ("خدتها امبارح", "خدتها النهارده")):
            with self.subTest(a=a):
                self.assertEqual(set(cmp(a, b)), {"timing"})


class TestReviewRound2(unittest.TestCase):
    """Fresh-eyes review (Opus), round 2."""

    def test_c1_split_negation_after_a_connector(self):
        for a, b in (("خدي الدوا بدري عشان ما تتعبيش", "خدي الدوا بدري عشان تتعبي"),
                     ("كلميني بعد ما تاخديش الجرعة", "كلميني بعد ما تاخدي الجرعة"),
                     ("لو يوم ما خدتيش الدوا", "لو يوم خدتي الدوا"),
                     ("زي ما بتاخديش", "زي ما بتاخدي"), ("كل ما تنسيش", "كل ما تنسي")):
            with self.subTest(a=a):
                self.assertIn("negation", cmp(a, b))

    def test_c2_ordinals(self):
        for a, b in (("الدوا ده ممنوع في الشهر التالت من الحمل", "الدوا ده ممنوع في الشهر السادس من الحمل"),
                     ("ابدأي الحقن في الأسبوع الأول", "ابدأي الحقن في الأسبوع التاني"),
                     ("stop it in the first trimester always", "stop it in the second trimester always"),
                     ("التلت شهور الأولانيين", "التلت شهور الأخرانيين")):
            with self.subTest(a=a):
                d = cmp(a, b)
                self.assertIn("numbers", d)
                self.assertTrue(d["numbers"]["a"] and d["numbers"]["b"], d)
        self.assertEqual(cmp("أول حاجة لازم تعرفي", "أول حاجة لازم تعرفيها كويس"), {})

    def test_i1_day_after_tomorrow_and_before_yesterday(self):
        self.assertEqual(set(cmp("ابدأي الحقن بعد بكرة", "ابدأي الحقن بكرة")), {"timing"})
        self.assertEqual(set(cmp("خدتها أول امبارح", "خدتها امبارح")), {"timing"})
        self.assertEqual(cmp("ابدأي الحقن بعد بكرة", "ابدأي الحقن بعد بكره"), {})


class TestReviewRound3(unittest.TestCase):
    def test_m1_openers_are_no_ordinals(self):
        for a, b in (("أول حاجة لازم تشربي مية كتير", "لازم تشربي مية كتير"),
                     ("آخر حاجة خدي الدوا", "خدي الدوا"),
                     ("first of all take it with food", "take it with food okay"),
                     ("أول ما تصحي خدي الدوا", "لما تصحي خدي الدوا")):
            with self.subTest(a=a):
                self.assertNotIn("numbers", cmp(a, b))
        self.assertIn("numbers", cmp("ابدأي في الأسبوع الأول", "ابدأي في الأسبوع"))
        self.assertIn("numbers", cmp("take it on the first of the month", "take it on the tenth of the month"))

    def test_m2_again_beside_a_dose_is_read(self):
        self.assertIn("numbers", cmp("خدي الحباية تاني بالليل", "خدي الحباية بالليل"))
        self.assertIn("numbers", cmp("take it again at night", "take it at night"))


class TestShape(unittest.TestCase):
    def test_plain_retake_has_no_difference(self):
        self.assertEqual(cmp("أول حاجة لازم تعرفي", "أول حاجة لازم تعرفيها كويس"), {})

    def test_empty_and_symmetric(self):
        self.assertEqual(D.compare([], []), {})
        a, b = "خدي حباية الصبح", "خدي حبايتين بالليل مش"
        ab, ba = cmp(a, b), cmp(b, a)
        self.assertEqual(set(ab), set(ba))
        self.assertTrue(all(ab[k]["a"] == ba[k]["b"] for k in ab))

    def test_describe_is_arabic_first_and_names_the_words(self):
        ar, en = D.describe(cmp("خدي حباية واحدة الصبح", "خدي حباية واحدة بالليل"))
        self.assertIn("«الصبح»", ar)
        self.assertIn("«بالليل»", ar)
        self.assertIn("توقيت", ar)
        self.assertIn("timing", en)
        self.assertEqual(D.describe({}), ("", ""))


if __name__ == "__main__":
    unittest.main()
