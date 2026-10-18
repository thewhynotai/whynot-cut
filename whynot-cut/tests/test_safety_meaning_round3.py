# SPDX-License-Identifier: GPL-3.0-or-later
# © 2026 The Why Not AI (thewhynot.ai)
"""3.0 Phase 4 Task 25 round 3 / K-T7 (review 62efd2d, FAIL round 2): the shared meaning reader also reads standard
Arabic negation («لست», «ليسوا», «دون», «منغير») and English contractions written without the apostrophe; a dose
is compared by its unit too (mg / g / mcg / ml, pill / capsule, teaspoon / tablespoon, per kilo); a fraction or a
vague word before a count noun is never read as one; thousands and millions are read whole or flagged; a limit
(«أكتر من», "at most"), an obligation ("must" / "may"), how often ("always" / "sometimes") and what a claim is
about (a measure, a route, who takes it, causes / prevents) count as meaning. Takes that differ so are never
pre-ticked and never get a proposed best.
Run:  bash tools/test.sh -p test_safety_meaning_round3.py
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
from lib.safety import risk_words as R  # noqa: E402
from lib.safety import takes as T  # noqa: E402
from lib.safety.numbers import canon, fold, quantities, tokens, values_in  # noqa: E402


def cmp(a, b):
    return D.compare(a.split(), b.split())


def neg(word, nxt=""):
    return R._negation(fold(word), fold(nxt))


def heard(text):
    """As a transcript gives it: one word per token; (value, kind, unit, unsure)."""
    return [(None if q["value"] is None else canon(q["value"]), q["kind"], q.get("unit"), bool(q.get("unsure")))
            for q in quantities([fold(w) for w in text.split()])]


def ws(spec):
    out, t = [], 0
    for i, (w, d, g) in enumerate(spec, 1):
        out.append({"id": i, "segment_id": 1, "word": w, "start_ms": t, "end_ms": t + d, "probability": 0.95})
        t += d + g
    return out


def proposals(a, b, lang):
    a, b = a.split(), b.split()
    spec = [(w, 300, 60) for w in a[:-1]] + [(a[-1], 300, 700)] + [(w, 300, 60) for w in b[:-1]] + [(b[-1], 300, 300)]
    return C.compute(ws(spec), lang=lang)["proposals"]


def best(a, b):
    out, t, wid = [], 0, 1
    for s, text in enumerate((a, b), 1):
        toks = text.split()
        for k, tok in enumerate(toks):
            out.append({"id": wid, "segment_id": s, "word": tok, "start_ms": t, "end_ms": t + 300, "probability": 0.95})
            wid += 1
            t += 300 + (900 if k == len(toks) - 1 else 60)
    g = T.groups(out)
    return g[0]["best"] if g else None


# (take a, take b, the kind of difference that must be named): review 62efd2d probe2, probe3, probe6, probe8
PROBES = [
    # P1-1 standard Arabic negation, «دون» / «منغير»
    ("أنت بحاجة إلى المضاد الحيوي ده", "أنت لست بحاجة إلى المضاد الحيوي ده", "negation"),
    ("المرضى بحاجة إلى المضاد الحيوي", "المرضى ليسوا بحاجة إلى المضاد الحيوي", "negation"),
    ("نحن بحاجة إلى جرعة إضافية", "لسنا بحاجة إلى جرعة إضافية", "negation"),
    ("ممكن تاخديه دون وصفة طبية", "ممكن تاخديه بوصفة طبية", "negation"),
    ("ممكن تاخديه منغير روشتة", "ممكن تاخديه بروشتة", "negation"),
    ("أنت لست بحاجة إلى المضاد الحيوي في الحالة دي", "أنت بحاجة إلى المضاد الحيوي في الحالة دي", "negation"),
    # P2-1 English contractions without the apostrophe
    ("he has diabetes and takes insulin", "he hasnt diabetes and takes insulin", "negation"),
    ("she was taking the pill daily", "she wasnt taking the pill daily", "negation"),
    ("you could take it with milk", "you couldnt take it with milk", "negation"),
    ("they have side effects in kids", "they havent side effects in kids", "negation"),
    ("they were taking it daily", "they werent taking it daily", "negation"),
    # P1-2 the unit of a dose
    ("خدي ٥ مجم من الدوا ده الصبح بعد الفطار", "خدي ٥ جم من الدوا ده الصبح بعد الفطار", "numbers"),
    ("خدي ٥ مجم من الدوا ده الصبح بعد الفطار", "خدي ٥ ميكروجرام من الدوا ده الصبح بعد الفطار", "numbers"),
    ("خدي ٥ مجم من الدوا ده الصبح بعد الفطار", "خدي ٥ مل من الدوا ده الصبح بعد الفطار", "numbers"),
    ("خدي ٥ مل من الشراب ده الصبح بعد الفطار", "خدي ٥ معالق من الشراب ده الصبح بعد الفطار", "numbers"),
    ("خدي ٢ حباية من الدوا ده الصبح بعد الفطار", "خدي ٢ كبسولة من الدوا ده الصبح بعد الفطار", "numbers"),
    ("take 5 mg of this drug every morning after breakfast", "take 5 g of this drug every morning after breakfast",
     "numbers"),
    ("take 5 mg of this drug every morning after breakfast",
     "take 5 mcg of this drug every morning after breakfast", "numbers"),
    ("take 5 mg of this drug every morning after breakfast", "take 5 ml of this drug every morning after breakfast",
     "numbers"),
    ("give the baby 5 ml of the syrup every morning after breakfast",
     "give the baby 5 teaspoons of the syrup every morning after breakfast", "numbers"),
    ("خدي معلقة صغيرة من الشراب ده الصبح بعد الفطار", "خدي معلقة كبيرة من الشراب ده الصبح بعد الفطار", "numbers"),
    ("take one teaspoon of the syrup every morning after breakfast",
     "take one tablespoon of the syrup every morning after breakfast", "numbers"),
    ("الجرعة القصوى ٤ جرام في اليوم للكبار", "الجرعة القصوى ٤ مجم في اليوم للكبار", "numbers"),
    ("خدي ٥٠٠ مجم كل ٨ ساعات بعد الأكل", "خدي ٥٠٠ ميكروجرام كل ٨ ساعات بعد الأكل", "numbers"),
    ("الجرعة ٥ مجم لكل كيلو من وزن الطفل", "الجرعة ٥ مجم من وزن الطفل", "numbers"),
    ("الدوا ده بنصح بيه للناس اللي عندها ضغط عالي ٥ مجم الصبح",
     "الدوا ده بنقول عليه للمرضى اللي بيعانوا من الضغط ٥ جم الصبح", "numbers"),
    ("خدي الدوا ده خمس أيام بعد الأكل", "خدي الدوا ده خمس أسابيع بعد الأكل", "numbers"),
    # P1-3 a fraction or a vague word before a count noun
    ("خدي حباية من الدوا ده الصبح بعد الفطار", "خدي تلتين حباية من الدوا ده الصبح بعد الفطار", "numbers"),
    ("خدي حباية من الدوا ده الصبح بعد الفطار", "خدي تلت تربع حباية من الدوا ده الصبح بعد الفطار", "numbers"),
    ("خدي حباية من الدوا ده الصبح", "خدي تلاتة أرباع حباية من الدوا ده الصبح", "numbers"),
    ("خدي حباية من الدوا ده الصبح بعد الفطار", "خدي كام حباية من الدوا ده الصبح بعد الفطار", "numbers"),
    ("خدي حباية من الدوا ده الصبح بعد الفطار", "خدي أكتر من حباية من الدوا ده الصبح بعد الفطار", "numbers"),
    ("متاخديش أكتر من حباية من الدوا ده الصبح", "متاخديش حباية من الدوا ده الصبح", "numbers"),
    ("take a tablet of this drug every morning after breakfast",
     "take up to a tablet of this drug every morning after breakfast", "numbers"),
    ("never take more than a tablet of this drug in the morning", "never take a tablet of this drug in the morning",
     "numbers"),
    # P1-4 thousands, millions, numbers said apart
    ("خدي ٥٠ ألف وحدة فيتامين د كل أسبوع", "خدي ألف وحدة فيتامين د كل أسبوع", "numbers"),
    ("خدي ١ / ٢ حباية من الدوا ده الصبح", "خدي ٢ حباية من الدوا ده الصبح", "numbers"),
    ("خدي ألف و ٥٠٠ مجم من الدوا ده", "خدي ٥٠٠ مجم من الدوا ده", "numbers"),
    # P2-2 limits, obligation, how often
    ("take it at most twice a day", "take it at least twice a day", "numbers"),
    ("take more than two tablets", "take less than two tablets", "numbers"),
    ("الجرعة أكتر من خمسمية مجم", "الجرعة أقل من خمسمية مجم", "numbers"),
    ("الدوا ده للأطفال فوق سنتين", "الدوا ده للأطفال تحت سنتين", "numbers"),
    ("you must take it daily", "you may take it daily", "modal"),
    ("لازم تكملي الكورس ده للآخر", "ممكن تكملي الكورس ده للآخر", "modal"),
    ("always take it with food", "sometimes take it with food", "timing"),
    ("دايما خديه بعد الأكل", "أحيانا خديه بعد الأكل", "timing"),
    # P3 what a claim is about
    ("الدوا ده بيقلل السكر", "الدوا ده بيقلل الضغط", "claim"),
    ("الدوا ده بيسبب نزيف", "الدوا ده بيمنع النزيف", "claim"),
    ("الحباية دي بتتاخد بالفم", "الحباية دي بتتاخد حقن", "claim"),
    ("الحقنة دي في العضل", "الحقنة دي في الوريد", "claim"),
    ("خدي الدوا ده للأطفال", "خدي الدوا ده للكبار", "claim"),
]


class TestNegationRound3(unittest.TestCase):
    def test_standard_arabic_negation(self):
        for w in ("لست", "لستي", "لسنا", "لستم", "لستن", "ليسوا", "ليسا", "ليستا", "دون", "منغير", "ولست", "فليسوا",
                  "ودون"):
            with self.subTest(w=w):
                self.assertEqual(neg(w), "word")

    def test_english_contractions_without_the_apostrophe(self):
        for w in ("hasnt", "havent", "hadnt", "wasnt", "werent", "couldnt", "wouldnt", "neednt", "mightnt", "aint",
                  "hasn't", "wasn’t", "Couldn't", "HAVENT"):
            with self.subTest(w=w):
                self.assertEqual(neg(w), "word")

    def test_look_alikes_are_no_negation(self):
        for w in ("want", "plant", "count", "isotonic", "giant", "event", "لسته", "دونات", "دوني"):
            with self.subTest(w=w):
                self.assertIsNone(neg(w))

    def test_risk_ranking_reads_the_new_forms(self):
        words = [{"id": i, "word": w, "start_ms": i * 300, "end_ms": i * 300 + 250, "probability": 0.5}
                 for i, w in enumerate("أنت لست بحاجة إلى الدوا ده".split(), 1)]
        ranked = R.rank(words, domain="medical")
        self.assertIn("negation", [e["risk"] for e in ranked if e["text"] == "لست"])


class TestDoseUnits(unittest.TestCase):
    def test_unit_is_part_of_a_dose(self):
        for text, unit in (("٥ مجم", "mg"), ("5 mg", "mg"), ("500mg", "mg"), ("٥ جم", "g"), ("5 g", "g"),
                           ("٥ ميكروجرام", "mcg"), ("5 mcg", "mcg"), ("5 µg", "mcg"), ("٥ مل", "ml"), ("5 ml", "ml"),
                           ("٥ سي سي", "ml"), ("5 cc", "ml"), ("٥ معالق", "spoon"), ("5 teaspoons", "teaspoon"),
                           ("one tablespoon", "tablespoon"), ("معلقة صغيرة", "teaspoon"),
                           ("معلقة كبيرة", "tablespoon"), ("٢ حباية", "tablet"), ("٢ قرص", "tablet"),
                           ("حبايتين", "tablet"), ("٢ كبسولة", "capsule"), ("كبسولتين", "capsule"),
                           ("٥٠٠ وحدة", "iu"), ("1000 IU", "iu"), ("خدي حباية", "tablet"), ("٥ مجم لكل كيلو", "mg/kg"),
                           ("5 mg per kg", "mg/kg"), ("خمس أيام", "day"), ("خمس أسابيع", "week"),
                           ("٨ ساعات", "hour"), ("يومين", "day")):
            with self.subTest(text=text):
                self.assertIn(unit, [q[2] for q in heard(text)])

    def test_same_unit_written_two_ways_is_no_difference(self):
        for a, b in (("خدي ٥ مجم الصبح", "خدي ٥ mg الصبح"), ("take 5 mg", "take 5 milligrams"),
                     ("خدي ٢ حباية", "خدي ٢ قرص"), ("take 2 tablets", "take 2 pills"), ("خدي ٥ مل", "خدي ٥ سي سي"),
                     ("خدي حبايتين", "خدي ٢ حباية"), ("take 1000 IU", "take 1000 units")):
            with self.subTest(a=a, b=b):
                self.assertNotIn("numbers", cmp(a, b))


class TestNumbersRound3(unittest.TestCase):
    def test_two_thirds_is_read_exactly(self):
        for text in ("تلتين حباية", "ثلثين حباية"):
            with self.subTest(text=text):
                self.assertEqual([(q[0], q[1]) for q in heard(text)], [(round(2 / 3, 4), "dose")])

    def test_plural_fractions_are_unsure_never_one(self):
        for text in ("تلت تربع حباية", "تلاتة أرباع حباية", "three quarters of a tablet", "two thirds of a tablet",
                     "خمس اتمان حباية"):
            with self.subTest(text=text):
                got = heard(text)
                self.assertTrue(any(q[3] for q in got), got)
                self.assertNotIn(1, [q[0] for q in got if q[1] == "dose"])

    def test_vague_amount_before_a_count_noun_is_not_one(self):
        for text in ("كام حباية", "كذا حباية", "شوية حباية", "a few tablet", "several tablet"):
            with self.subTest(text=text):
                self.assertNotIn(1, [q[0] for q in heard(text)])

    def test_thousands_and_millions(self):
        for text, value in (("٥ آلاف وحدة", 5000), ("5 آلاف وحدة", 5000), ("٥٠ ألف وحدة", 50000),
                            ("٥٠ الف وحدة", 50000), ("خمس آلاف وحدة", 5000), ("ألف و ٥٠٠ مجم", 1500),
                            ("ألف و500 مجم", 1500), ("ألف وخمسمية مجم", 1500), ("ألف ونص مجم", 1500),
                            ("مية ونص مجم", 150), ("٢ مليون وحدة", 2000000), ("مليون وحدة", 1000000),
                            ("مليون ونص وحدة", 1500000), ("2 million units", 2000000), ("1.2 million units", 1200000),
                            ("5 thousand units", 5000), ("ميتين و ٥٠ مجم", 250)):
            with self.subTest(text=text):
                got = heard(text)
                self.assertEqual([(q[0], q[1], q[3]) for q in got], [(value, "dose", False)], got)

    def test_numbers_said_apart_are_unsure(self):
        for text in ("50 000 IU", "٥٠ ٠٠٠ وحدة", "500 000 IU", "٥ ٠٠ مجم", "١ / ٢ حباية", "١/ ٢ حباية", "١ /٢ حباية",
                     "10k IU", "١٠ك وحدة", "خدي ٢ ٣ حبايات", "1000 و 500 مجم", "١٠٠٠ و٥٠٠ مجم", "100 and 50 mg"):
            with self.subTest(text=text):
                got = heard(text)
                self.assertTrue(got and all(q[3] for q in got if q[1] == "dose"), got)
                self.assertTrue(any(q[3] for q in got), got)
        self.assertEqual(heard("٣ ٣ حبايات"), [(3, "number", None, False), (3, "dose", "tablet", False)])  # a repeat

    def test_written_numbers_split_by_the_writer(self):
        written = lambda t: [(q["value"], bool(q.get("unsure"))) for q in quantities(tokens(t))]   # noqa: E731
        self.assertEqual(written("١٢٠/٨٠"), [(120, False), (80, False)])
        self.assertEqual(written("١٢٠ / ٨٠"), [(120, False), (80, False)])
        self.assertEqual(written("٣-٤ مرات"), [(3, False), (4, False)])
        for t in ("١ / ٢ حباية", "1 /2 tablet", "1/ 2 tablet"):
            with self.subTest(t=t):
                self.assertEqual(written(t), [(None, True)])

    def test_old_readings_unchanged(self):
        for text, want in (("٣ ونص مجم", [(3.5, "dose", "mg", False)]), ("خمسمية مجم", [(500, "dose", "mg", False)]),
                           ("نص حباية", [(0.5, "dose", "tablet", False)]),
                           ("حباية وحباية", [(2, "dose", "tablet", False)]),
                           ("١٢٠ على ٨٠", [(120, "number", None, False), (80, "number", None, False)])):
            with self.subTest(text=text):
                self.assertEqual(heard(text), want)


class TestTakesRound3(unittest.TestCase):
    def test_every_review_probe_is_never_pre_ticked_and_gets_no_best(self):
        for a, b, kind in PROBES:
            with self.subTest(a=a, b=b):
                d = cmp(a, b)
                self.assertIn(kind, d, d)
                lang = "en" if a.replace(" ", "").isascii() else "ar"
                ticked = [p for p in proposals(a, b, lang) if p["kind"] == "retake" and p["default"] != "keep"]
                self.assertEqual(ticked, [])
                self.assertIsNone(best(a, b))

    def test_the_reason_names_the_new_kinds(self):
        ar, en = D.describe(cmp("you must take it daily", "you may take it daily"))
        self.assertIn("must", en)
        self.assertIn("may", en)
        self.assertTrue(ar.startswith(D.LABEL["modal"][0]))
        ar, en = D.describe(cmp("take 5 mg daily", "take 5 g daily"))
        self.assertIn("5 mg", en)
        self.assertIn("5 g", en)

    def test_a_repeated_count_noun_or_unit_is_kept(self):
        for a in ("خدي حباية حباية من الدوا ده", "خدي ٥ مجم مجم من الدوا ده", "take a tablet tablet daily"):
            with self.subTest(a=a):
                res = C.compute(ws([(x, 300, 60) for x in a.split()]), lang="en" if a.isascii() else "ar")
                reps = [p for p in res["proposals"] if p["kind"] == "repeat_word"]
                self.assertTrue(reps)
                self.assertTrue(all(p["default"] == "keep" for p in reps))

    def test_same_words_are_still_no_difference(self):
        for a in ("خدي ٥ مجم الصبح بعد الفطار", "you must take it daily", "لازم تكملي الكورس", "always take it with food",
                  "الجرعة أكتر من خمسمية مجم", "الدوا ده بيقلل السكر عند الأطفال", "الحقنة في العضل",
                  "أنت لست بحاجة إلى المضاد الحيوي"):
            with self.subTest(a=a):
                self.assertEqual(cmp(a, a), {})


# the lane's own fresh-eyes review, round 1: more everyday phrasings
PROBES_R1 = [
    ("خدي تلاتة أربعة حبايات من الدوا ده", "خدي سبعة حبايات من الدوا ده", "numbers"),
    ("take three four tablets of this drug", "take seven tablets of this drug", "numbers"),
    ("خدي حباية الصبح ونص حباية بالليل", "خدي حباية الصبح وحباية بالليل", "numbers"),
    ("خدي نصين حباية من الدوا ده", "خدي حباية من الدوا ده", "numbers"),
    ("خدي مية مية مجم من الدوا ده", "خدي عشرة آلاف مجم من الدوا ده", "numbers"),
    ("خدي ٥ و٢٠ مجم من الدوا ده", "خدي ٥ و٣٠ مجم من الدوا ده", "numbers"),
    ("خدي خمستلاف وحدة فيتامين د", "خدي تلاتلاف وحدة فيتامين د", "numbers"),
    ("this drug is for children older than 12 years", "this drug is for children younger than 12 years", "numbers"),
    ("الدوا ده للأطفال أكبر من ١٢ سنة", "الدوا ده للأطفال أصغر من ١٢ سنة", "numbers"),
    ("call us if the sugar is higher than 200", "call us if the sugar is lower than 200", "numbers"),
    ("خديه قبل الأكل بأكتر من ساعة", "خديه قبل الأكل بأقل من ساعة", "numbers"),
    ("take it more than an hour before food", "take it less than an hour before food", "numbers"),
    ("never take more than the recommended dose", "never take the recommended dose", "numbers"),
    ("the dose is 5 mg/kg for kids", "the dose is 5 g/kg for kids", "numbers"),
    ("give the baby 5 tsp of the syrup", "give the baby 5 tbsp of the syrup", "numbers"),
    ("اشربي كوباية من الشراب ده", "اشربي فنجان من الشراب ده", "numbers"),
    ("drink two cups of this tea daily", "drink two glasses of this tea daily", "numbers"),
    ("you may take it with food daily", "take it with food daily", "modal"),
    ("you must take it with food", "you take it with food", "modal"),
    ("this test is necessary for you", "this test is optional for you", "modal"),
    ("لازم تاخدي الدوا ده بعد الأكل", "يفضل تاخدي الدوا ده بعد الأكل", "modal"),
    ("the test was negative for the virus", "the test was positive for the virus", "claim"),
    ("حطي النقط في العين الشمال كل يوم", "حطي النقط في العين اليمين كل يوم", "claim"),
    ("خديه على معدة فاضية الصبح", "خديه على معدة مليانة الصبح", "claim"),
    ("call your doctor immediately if it hurts", "call your doctor later if it hurts", "claim"),
]


class TestSelfReviewRound1(unittest.TestCase):
    def test_every_probe_is_never_pre_ticked_and_gets_no_best(self):
        for a, b, kind in PROBES_R1:
            with self.subTest(a=a, b=b):
                self.assertIn(kind, cmp(a, b))
                lang = "en" if a.replace(" ", "").replace("/", "").isascii() else "ar"
                ticked = [p for p in proposals(a, b, lang) if p["kind"] == "retake" and p["default"] != "keep"]
                self.assertEqual(ticked, [])
                self.assertIsNone(best(a, b))

    def test_numbers_read_whole(self):
        for text, value in (("خمستلاف وحدة", 5000), ("٥٠ألف وحدة", 50000), ("و٥٠ ألف وحدة", 50000),
                            ("٢ مليون و ٥٠٠ ألف وحدة", 2500000), ("half a million units", 500000),
                            ("نص مليون وحدة", 500000), ("ربع مليون وحدة", 250000), ("ونص حباية", 0.5),
                            ("حباية ونص", 1.5), ("twenty five mg", 25), ("خمسة وعشرين مجم", 25),
                            ("ألف خمسمية مجم", 1500), ("two hundred thousand units", 200000)):
            with self.subTest(text=text):
                self.assertEqual([(q[0], q[1], q[3]) for q in heard(text)], [(value, "dose", False)])

    def test_numbers_that_are_not_one_for_sure(self):
        for text in ("تلاتة أربعة حبايات", "three four tablets", "خمسة ستة أيام", "عشرة عشرين مجم", "واحدة اتنين حباية",
                     "تلت تلاف وحدة", "تلت مية مجم", "مية مية مجم", "ألف ألف وحدة", "نصين حباية", "ربعين حباية",
                     "one and a half thousand units", "ألف ٥٠٠ مجم", "٥ آلاف ٥٠٠ وحدة", "10 k IU",
                     "three quarter tablet", "١٠٠ ونص مجم"):
            with self.subTest(text=text):
                self.assertEqual([(q[0], q[3]) for q in heard(text)], [(None, True)])

    def test_units_written_short_or_by_weight(self):
        for text, unit in (("5 mg/kg", "mg/kg"), ("5 g/kg", "g/kg"), ("5 tsp", "teaspoon"), ("5 tbsp", "tablespoon"),
                           ("5 mgs", "mg"), ("كوباية", "cup"), ("فنجان", "fincan"), ("two cups", "cup"),
                           ("two glasses", "glass"), ("كيس", "sachet")):
            with self.subTest(text=text):
                self.assertEqual([q[2] for q in heard(text)], [unit])

    def test_written_dates_and_ranges_keep_every_number(self):
        self.assertEqual(values_in("1/2/2024"), {1, 2, 2024})
        self.assertEqual(values_in("1 / 2 / 3"), {1, 2, 3})
        self.assertEqual(values_in("٣ - ٤ مرات"), {3, 4})

    def test_the_same_said_two_ways_is_still_no_difference(self):
        for a, b in (("take it twice a day", "take it two times a day"), ("take 5 mgs daily", "take 5 mg daily"),
                     ("take 5 mg per kg daily", "take 5 mg/kg daily"), ("خدي الدوا مرتين في اليوم",
                                                                        "خدي الدوا مرتين في اليوم"),
                     ("Sleep is the first thing you should fix.", "Sleep is the first thing you"),
                     ("you should not take this pill", "you shouldn't take this pill"),
                     ("مينفعش تاخديه مع اللبن", "ما ينفعش تاخديه مع اللبن")):
            with self.subTest(a=a, b=b):
                self.assertEqual(cmp(a, b), {})

    def test_a_word_only_the_dropped_take_says_keeps_the_retake(self):
        res = proposals("خدي الدوا ده مع الأكل الخفيف", "خدي الدوا ده مع الأكل.", "ar")   # the later take is kept
        rt = [p for p in res if p["kind"] == "retake"]
        self.assertTrue(rt)
        self.assertEqual(rt[0]["default"], "keep")
        self.assertIn("الخفيف", rt[0]["reason"])
        self.assertEqual(rt[0]["differs"], {"words": {"a": ["الخفيف"], "b": []}})
        # the same meaning in other words, compared by the reader ("with food" / "with a meal"), is no loss
        res = proposals("you should take it with food", "you should take it with a meal.", "en")
        self.assertEqual([p["default"] for p in res if p["kind"] == "retake"], ["proposed"])
        # but a word the reader did not compare ("full") is a word the kept take adds: since Task 25 round 4 the
        # exemption after an abandoned take holds only at a real cut-off (EXECUTOR RULINGS 2026-10-18 (2) item 2)
        res = proposals("you should take it with food", "you should take it with a full meal.", "en")
        [r] = [p for p in res if p["kind"] == "retake"]
        self.assertEqual((r["default"], r["differs"]), ("keep", {"words": {"a": [], "b": ["full"]}}))


PROBES_R2 = [
    ("take it before the evening meal", "take it before the morning meal", "timing"),
    ("you may also stop the drug after meals", "you stop the drug after meals.", "modal"),
    ("ممكن كمان تاخدي الدوا ده بعد الأكل", "تاخدي الدوا ده بعد الأكل.", "modal"),
    ("خدي تلات حبايات ونص بالليل", "خدي تلات حبايات بالليل", "numbers"),
    ("استني ساعتين ونص بعد الأكل", "استني ساعتين بعد الأكل", "numbers"),
    ("خديه مرة أو مرتين في اليوم", "خديه مرتين في اليوم", "numbers"),
]


class TestSelfReviewRound2(unittest.TestCase):
    def test_every_probe_is_never_pre_ticked_and_gets_no_best(self):
        for a, b, kind in PROBES_R2:
            with self.subTest(a=a, b=b):
                self.assertIn(kind, cmp(a, b))
                lang = "en" if a.replace(" ", "").isascii() else "ar"
                ticked = [p for p in proposals(a, b, lang) if p["kind"] == "retake" and p["default"] != "keep"]
                self.assertEqual(ticked, [])
                self.assertIsNone(best(a, b))

    def test_a_word_between_before_and_the_meal_is_not_hidden(self):
        rt = [p for p in proposals("take it after a fatty meal", "take it after a meal.", "en") if p["kind"] == "retake"]
        self.assertEqual([p["default"] for p in rt], ["keep"])
        self.assertIn("fatty", rt[0]["reason"])

    def test_a_half_after_a_unit_or_a_dual(self):
        for text, want in (("تلات حبايات ونص", (3.5, "tablet", False)), ("ساعتين ونص", (2.5, "hour", False)),
                           ("كبسولتين ونص", (2.5, "capsule", False)), ("كيسين", (2, "sachet", False)),
                           ("٥٠٠ مجم ونص", (None, "mg", True))):
            with self.subTest(text=text):
                self.assertEqual([(q[0], q[2], q[3]) for q in heard(text)], [want])

    def test_a_number_and_a_glued_number_are_unsure(self):
        for text in ("خمسة و٢٠ مجم", "٥ و ٢٠ مجم", "٥ و٢٠ مجم"):
            with self.subTest(text=text):
                self.assertEqual([(q[0], q[3]) for q in heard(text)], [(None, True)])

    def test_a_very_long_number_does_not_raise(self):
        self.assertEqual(canon(int("5" * 400)), int("5" * 400))
        self.assertTrue(values_in("٥" * 400))
        self.assertEqual(cmp("خدي " + "٥" * 400 + " مجم", "خدي " + "٥" * 400 + " مجم"), {})


PROBES_R3 = [
    ("this drug at night you can take with a glass of water", "take this drug with a glass of water at night.",
     "modal"),
    ("the drug with food you must take every day for a week", "take the drug every day for a week with food.", "modal"),
    ("الدوا ده مع الأكل لازم تاخديه كل يوم لمدة أسبوع", "تاخدي الدوا ده كل يوم لمدة أسبوع مع الأكل.", "modal"),
    ("خديه قبل وجبة العشا", "خديه قبل وجبة الغدا.", "timing"),
    ("خديه قبل وجبة", "خديه قبل وجبة العشا.", "timing"),
    ("استني ساعة ونص بعد الأكل", "استني ساعة بعد الأكل", "numbers"),
    ("wait an hour and a half after food", "wait an hour after food", "numbers"),
    ("خديه مرة ولا مرتين في اليوم", "خديه مرتين في اليوم.", "numbers"),
    # round 4: a verb said in another form is no cut short
    ("الحباية دي مع الأكل الكبير كل يوم الصبح ممكن تبطليها", "بطلي الحباية دي مع الأكل الكبير كل يوم الصبح.", "modal"),
]


class TestSelfReviewRound3(unittest.TestCase):
    def test_every_probe_is_never_pre_ticked_and_gets_no_best(self):
        for a, b, kind in PROBES_R3:
            with self.subTest(a=a, b=b):
                self.assertIn(kind, cmp(a, b))
                lang = "en" if a.replace(" ", "").replace(".", "").isascii() else "ar"
                ticked = [p for p in proposals(a, b, lang) if p["kind"] == "retake" and p["default"] != "keep"]
                self.assertEqual(ticked, [])
                self.assertIsNone(best(a, b))

    def test_a_take_cut_short_before_the_modal_is_still_no_difference(self):
        for a, b in (("Sleep is the first thing you should fix.", "Sleep is the first thing"),
                     ("uhh الـ content اللي بتنزله", "الـ content اللي بتنزله لازم يكون قصير.")):
            with self.subTest(a=a, b=b):
                self.assertNotIn("modal", cmp(a, b))

    def test_durations_with_a_half_and_less_a_part(self):
        for text, want in (("ساعة ونص", [(1.5, "hour", False)]), ("an hour and a half", [(1.5, "hour", False)]),
                           ("يوم ونص", [(1.5, "day", False)]), ("ساعتين الا ربع", [(None, "hour", True)]),
                           ("خمسمية وألف مجم", [(None, "mg", True)]), ("حباية الا ربع", [(None, "tablet", True)]),
                           ("كبسولة الا ربع", [(None, "capsule", True)]), ("ساعة ونص الا ربع", [(None, "hour", True)]),
                           ("تلات حبايات الا ربع", [(None, "tablet", True)])):
            with self.subTest(text=text):
                self.assertEqual([(q[0], q[2], q[3]) for q in heard(text)], want)

    def test_an_endless_number_is_never_a_value(self):
        self.assertEqual([(q[0], q[3]) for q in heard("1" + "0" * 400 + ".5 mg")], [(None, True)])


if __name__ == "__main__":
    unittest.main()
