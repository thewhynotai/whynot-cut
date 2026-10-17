# SPDX-License-Identifier: GPL-3.0-or-later
# © 2026 The Why Not AI (thewhynot.ai)
"""3.0 Phase 4 Task 25 round 2 / K-T7 fix 2 / K-T1 follow-ups (executor rulings 2026-10-17 20:10 and 21:00; reviews
d73c3e3, 7193e9a, b29d47f): one negation reader for every Egyptian form (a rule, not a word list), medical numbers
read exactly or flagged (never a guess), and takes that differ in meaning never get a proposed best or a pre-ticked
retake.
Run:  bash tools/test.sh -p test_safety_meaning_round2.py
"""
import sys as _sys
_sys.dont_write_bytecode = True  # keep the plugin folder free of __pycache__
import _isolation  # noqa: F401,E402  G79: sandbox the engine home first (tests/_isolation.py)
import time
import unittest
from pathlib import Path
from unittest import mock

sys = _sys
SK = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SK / "engine" / "reel"))

from lib import cut_proposals as C  # noqa: E402
from lib.safety import differences as D  # noqa: E402
from lib.safety import risk_words as R  # noqa: E402
from lib.safety import takes as T  # noqa: E402
from lib.safety.numbers import find_numbers, fold, quantities, tokens, values_in  # noqa: E402


def cmp(a, b):
    return D.compare(a.split(), b.split())


def neg(word, nxt=""):
    return R._negation(fold(word), fold(nxt))


def doses(text):
    return [(q["value"], q["kind"], bool(q.get("unsure"))) for q in quantities(tokens(text))]


def heard(text):
    """As a transcript gives it: one word per token (no "/" split)."""
    return [(q["value"], q["kind"], bool(q.get("unsure"))) for q in quantities([fold(w) for w in text.split()])]


def ws(spec):
    out, t = [], 0
    for i, (w, d, g) in enumerate(spec, 1):
        out.append({"id": i, "segment_id": 1, "word": w, "start_ms": t, "end_ms": t + d, "probability": 0.95})
        t += d + g
    return out


def retakes(a, b, lang="ar", **cfg):
    a, b = a.split(), b.split()
    spec = [(w, 300, 60) for w in a[:-1]] + [(a[-1], 300, 700)] + [(w, 300, 60) for w in b[:-1]] + [(b[-1], 300, 300)]
    res = C.compute(ws(spec), lang=lang, **cfg)
    return [p for p in res["proposals"] if p["kind"] == "retake"]


def two_takes(a, b):
    out, t, wid = [], 0, 1
    for s, text in enumerate((a, b), 1):
        toks = text.split()
        for k, tok in enumerate(toks):
            out.append({"id": wid, "segment_id": s, "word": tok, "start_ms": t, "end_ms": t + 300, "probability": 0.95})
            wid += 1
            t += 300 + (900 if k == len(toks) - 1 else 60)
    g = T.groups(out)
    assert len(g) == 1, g
    return g[0]


# d73c3e3 probe4 (the reader) and probe5 (end to end): every one must read a negation
READER_PROBES = [
    ("هو عنده سكر من زمان", "هو معندوش سكر من زمان"), ("هي خدت الجرعة امبارح", "هي مخدتش الجرعة امبارح"),
    ("هو خد الجرعة امبارح", "هو مخدش الجرعة امبارح"), ("كان بياخد الدوا", "مكانش بياخد الدوا"),
    ("الدوا ليه أعراض", "الدوا ملوش أعراض"), ("الدوا فيه كورتيزون", "الدوا مفيهوش كورتيزون"),
    ("حد ياخده", "محدش ياخده"), ("اقدر اوقفه", "مقدرش اوقفه"), ("اعرف الجرعة", "معرفش الجرعة"),
    ("شربت المية", "مشربتش المية"), ("بيقلل الضغط", "ومش بيقلل الضغط"), ("بيقلل الضغط", "فمش بيقلل الضغط"),
    ("بيقلل الضغط", "ولا بيقلل الضغط"), ("بيقلل الضغط", "وما بيقللش الضغط"), ("بيقلل الضغط", "فما بيقللش الضغط"),
    ("بيقلل الضغط", "ومبيقللش الضغط"), ("بيقلل الضغط", "فمبيقللش الضغط"), ("بيقلل الضغط", "لأ بيقلل الضغط"),
    ("الحامل تاخده", "الحامل ماتاخدوش"), ("it is safe", "it is not at all safe"), ("it is safe", "it ain't safe"),
    ("it is safe", "it is unsafe"), ("it works", "it never works"), ("you need it", "you don't need it"),
    ("you need it", "you do not need it"), ("you need it", "you dont need it"), ("you need it", "you hardly need it"),
    ("it is effective", "it is ineffective"), ("take it", "don’t take it"), ("take it", "DON'T take it"),
    ("you should take it", "you shouldn’t take it"), ("you would need it", "you wouldn't need it"),
    ("you could stop it", "you couldn't stop it"), ("you need it", "you needn't it"),
    ("he has diabetes", "he hasn't diabetes"), ("he had diabetes", "he hadn't diabetes"),
    ("they were sick", "they weren't sick")]
RETAKE_PROBES = [
    ("هي خدت الجرعة بتاعتها امبارح", "هي مخدتش الجرعة بتاعتها امبارح"),
    ("المريض عنده حساسية من البنسلين", "المريض معندوش حساسية من البنسلين"),
    ("الدوا ده ليه أعراض جانبية على الكلى", "الدوا ده ملوش أعراض جانبية على الكلى"),
    ("الكريم ده فيه كورتيزون", "الكريم ده مفيهوش كورتيزون"),
    ("كان بياخد الدوا بانتظام", "مكانش بياخد الدوا بانتظام"),
    ("والدوا ده بيقلل الضغط", "والدوا ده ومبيقللش الضغط"),
    ("الدوا ده بيقلل الضغط وبيقلل السكر", "الدوا ده بيقلل الضغط ومش بيقلل السكر"),
    ("الدوا ده بيقلل الضغط", "الدوا ده ومش بيقلل الضغط"), ("الدوا ده بيقلل الضغط", "الدوا ده فمش بيقلل الضغط"),
    ("الدوا ده بيقلل الضغط عند الكبار", "الدوا ده وما بيقللش الضغط عند الكبار"),
    ("take half a tablet at night", "take a tablet at night"), ("take half the dose", "take the dose"),
    ("take a double dose at night", "take a dose at night"),
    ("start it next month please", "start it next week please"), ("start it next week please", "start it this week please"),
    ("ابدأي الدوا الشهر ده", "ابدأي الدوا الشهر الجاي"), ("ابدأي الدوا الأسبوع ده", "ابدأي الدوا الأسبوع الجاي"),
    ("خدي الدوا لمدة أسبوع", "خدي الدوا لمدة شهر"), ("take it for a week", "take it for a month"),
    ("خدي البنادول بعد الأكل", "خدي الأسبرين بعد الأكل"), ("take ibuprofen after food", "take paracetamol after food")]
# 7193e9a P2-1: a later take that adds meaning to an earlier one without a full stop
TAKE_PROBES = [
    ("خدي حباية واحدة من الدوا ده الصبح", "خدي حباية واحدة من الدوا ده الصبح وحباية بالليل", "numbers"),
    ("الدوا ده آمن للحامل", "الدوا ده آمن للحامل بس مش في الشهور الأولى", "negation"),
    ("you can take this pill with food", "you can take this pill with food but not with alcohol.", "negation"),
    ("خدي حباية من الدوا ده", "خدي حباية من الدوا ده مرتين", "numbers")]


class TestNegationReader(unittest.TestCase):
    def test_circumfix_is_a_rule_around_any_word(self):
        for w in ("مخدتش", "مخدش", "معندوش", "ملوش", "مفيهوش", "مكانش", "محدش", "مقدرش", "معرفش", "مشربتش",
                  "مبيقللش", "ماتاخدش", "ماتاخدوش", "مبقاش", "مشغلتهاش"):
            with self.subTest(w=w):
                self.assertEqual(neg(w), "verb")

    def test_words_that_only_look_negated(self):
        for w in ("مشروب", "مشمش", "مكتب", "معاش", "معلش", "مدهش", "منعش", "مفتش", "مفرش", "مغشوش", "منقوش",
                  "مفروش", "مشوش", "مقرمش", "مهمش", "مرتعش", "منكمش", "والمشمش", "ومعاش", "بالمشمش", "ماش"):
            with self.subTest(w=w):
                self.assertIsNone(neg(w))

    def test_separate_and_glued_forms(self):
        for w, nxt, kind in (("مش", "", "word"), ("ومش", "", "word"), ("فمش", "", "word"), ("ومفيش", "", "word"),
                             ("ومبيقللش", "", "verb"), ("فمبيقللش", "", "verb"), ("ومكانش", "", "verb"),
                             ("ما", "بيقللش", "word"), ("وما", "بيقللش", "word"), ("فما", "تاخدهاش", "word"),
                             ("فلا", "", "word"), ("hardly", "", "word"), ("nobody", "", "word")):
            with self.subTest(w=w, nxt=nxt):
                self.assertEqual(neg(w, nxt), kind)

    def test_glued_ma_alone_is_and_what(self):
        self.assertIsNone(neg("وما", "هو"))
        self.assertIsNone(neg("فما", "العلاج"))
        self.assertEqual(cmp("وما هو العلاج", "وما هو العلاج"), {})
        self.assertNotIn("negation", cmp("ايه العلاج", "وما هو العلاج"))

    def test_every_review_probe_reads_a_negation(self):
        for a, b in READER_PROBES:
            with self.subTest(a=a, b=b):
                self.assertIn("negation", cmp(a, b))

    def test_same_negation_said_two_ways_is_no_difference(self):
        for a, b in (("الدوا ده مش بيقلل الضغط", "الدوا ده مبيقللش الضغط"),
                     ("الدوا ده ما بيقللش الضغط", "الدوا ده مبيقللش الضغط"),
                     ("الدوا ده ومش بيقلل الضغط", "الدوا ده ومبيقللش الضغط"),
                     ("you do not need it", "you don't need it"), ("المشمش مفيد", "المشمش مفيد")):
            with self.subTest(a=a, b=b):
                self.assertEqual(cmp(a, b), {})

    def test_negated_core(self):
        for w, prev, core in (("مبيقللش", "", "بيقلل"), ("ومبيقللش", "", "بيقلل"), ("ماتاخدش", "", "تاخد"),
                              ("بيقللش", "ما", "بيقلل"), ("بيقلل", "", "بيقلل"), ("مشمش", "", "مشمش")):
            with self.subTest(w=w):
                self.assertEqual(R.negated_core(fold(w), fold(prev)), core)

    def test_risk_ranking_uses_the_same_reader(self):
        words = [{"id": i, "word": w, "start_ms": i * 400, "end_ms": i * 400 + 300, "probability": 0.4}
                 for i, w in enumerate("المريض معندوش حساسية من البنسلين".split())]
        risks = {e["text"]: e["risk"] for e in R.rank(words, domain="medical")}
        self.assertEqual(risks["معندوش"], "negation")
        words = [{"id": i, "word": w, "start_ms": i * 400, "end_ms": i * 400 + 300, "probability": 0.4}
                 for i, w in enumerate("الدوا ده وما بيقللش الضغط".split())]
        self.assertEqual({e["text"]: e["risk"] for e in R.rank(words)}["وما"], "negation")

    def test_no_slow_pattern_on_a_long_token(self):
        t0 = time.perf_counter()
        for tok in ("م" + "ب" * 20000 + "ش", "م" + "ب" * 20000, "و" * 20000):
            R._negation(tok)
        self.assertLess(time.perf_counter() - t0, 0.5)


class TestMedicalNumbers(unittest.TestCase):
    def test_arabic_comma_is_a_decimal_mark(self):
        self.assertEqual(doses("٣،٥ مجم"), [(3.5, "dose", False)])
        self.assertEqual(heard("٣،٥ مجم"), [(3.5, "dose", False)])
        self.assertEqual(doses("٠،٢٥ مجم"), [(0.25, "dose", False)])

    def test_arabic_comma_before_three_digits_is_unsure(self):
        self.assertEqual(doses("٣،٥٠٠ مجم"), [(None, "dose", True)])

    def test_fractions_are_read_as_fractions(self):
        for text, v in (("⅕ حباية", 0.2), ("3⁄4 مجم", 0.75), ("1 3⁄4 مجم", 1.75), ("3 ½ مجم", 3.5), ("3½ مجم", 3.5),
                        ("⅛ حباية", 0.125), ("٢ ½ مجم", 2.5)):
            with self.subTest(text=text):
                self.assertEqual(doses(text)[0][:2], (v, "dose"))
                self.assertEqual(heard(text)[0][:2], (v, "dose"))

    def test_superscripts_are_never_digits(self):
        for text in ("3² مجم", "٣² مجم", "5₂ مجم"):
            with self.subTest(text=text):
                self.assertEqual(doses(text), [(None, "dose", True)])
                self.assertNotIn(32, values_in(text))
        self.assertEqual(doses("٥ م²"), [(5, "number", False)])

    def test_odd_writings_are_unsure_never_a_guess(self):
        for text in ("3..5 مجم", "3,5,7 مجم", "1.2.3 مجم"):
            with self.subTest(text=text):
                self.assertEqual(doses(text), [(None, "dose", True)])
        self.assertEqual(heard("1/2 حباية"), [(None, "dose", True)])
        self.assertEqual(doses("1/2 حباية"), [(None, "dose", True)])
        self.assertEqual(values_in("1/2 حباية"), set())

    def test_blood_pressure_still_two_numbers(self):
        self.assertEqual(values_in("١٢٠/٨٠"), {120, 80})
        self.assertEqual(values_in("الضغط 140/90"), {140, 90})

    def test_unsure_number_is_flagged_for_the_editor(self):
        words = [{"id": i, "word": w, "start_ms": i * 400, "end_ms": i * 400 + 300, "probability": 1.0}
                 for i, w in enumerate("خدي 3² مجم".split())]
        items = R.rank(words, domain="medical")
        dose = next(e for e in items if e["risk"] == "dose")
        self.assertEqual(dose["text"], "3² مجم")
        self.assertGreaterEqual(dose["doubt"], 0.5)
        self.assertIn(R.UNSURE_WHY, dose["why"])
        self.assertNotIn("value", dose)
        for shown in ("خدي 3² مجم", "خدي 32 مجم", "خدي ٩ مجم", "خدي تسعة مجم", "½ حباية", "نص حباية"):
            with self.subTest(shown=shown):                 # P1-6: any number on the graphic may be it
                self.assertTrue(R._shown(dose, shown))
        self.assertFalse(R._shown(dose, "خدي الدوا بعد الأكل"))
        dash = R.rank([{"id": 1, "word": "3-4", "start_ms": 0, "end_ms": 300, "probability": 1.0},
                       {"id": 2, "word": "حبايات", "start_ms": 400, "end_ms": 700, "probability": 1.0}])[0]
        self.assertTrue(R._shown(dash, "3-4 حبايات"))      # the same writing on the graphic, split by the dash
        dot = R.rank([{"id": 1, "word": "1.500", "start_ms": 0, "end_ms": 300, "probability": 1.0},
                      {"id": 2, "word": "mg", "start_ms": 400, "end_ms": 700, "probability": 1.0}])[0]
        self.assertIn(R.UNSURE_WHY, dot["why"])             # two readings: flagged, both matched
        self.assertEqual((dot["value"], dot["alts"]), (1.5, [1500]))

    def test_unsure_numbers_compare_by_their_writing(self):
        self.assertEqual(cmp("خدي 3² مجم", "خدي 3² مجم"), {})
        self.assertIn("numbers", cmp("خدي 3² مجم", "خدي 32 مجم"))
        self.assertIn("numbers", cmp("خدي 1/2 حباية", "خدي 0.5 حباية"))

    def test_more_units_and_durations(self):
        self.assertEqual(doses("خمس قطرات"), [(5, "dose", False)])
        self.assertEqual(doses("عشرين يومًا"), [(20, "duration", False)])

    def test_english_dose_words(self):
        self.assertEqual(doses("take half a tablet"), [(0.5, "dose", False)])
        self.assertEqual(doses("take half the dose"), [(0.5, "dose", False)])
        self.assertEqual(doses("take a double dose"), [(2, "dose", False)])
        self.assertEqual(doses("take a tablet"), [(1, "dose", False)])
        self.assertEqual(doses("double check it"), [])

    def test_a_dose_said_by_its_noun(self):
        self.assertEqual(doses("خدي حباية"), [(1, "dose", False)])
        self.assertEqual(doses("خدي حباية وحباية"), [(2, "dose", False)])
        self.assertEqual(doses("خدي حباية و حباية"), [(2, "dose", False)])
        for text in ("الحباية دي", "كل حباية", "استني حبة", "نقطة مهمة"):
            with self.subTest(text=text):
                self.assertEqual(doses(text), [])
        d = cmp("خدي حباية", "خدي حباية وحباية")                    # 7193e9a P3-2
        self.assertEqual(d["numbers"], {"a": ["حباية"], "b": ["حباية وحباية"]})
        d = cmp("خدي حباية", "خدي حبايتين")
        self.assertEqual(d["numbers"], {"a": ["حباية"], "b": ["حبايتين"]})

    def test_old_readings_unchanged(self):
        for text, vals in (("خد ٣٫٥ مجم", {3.5}), ("خمسمية", {500}), ("نص حباية", {0.5}), ("ست حبايات", {6}),
                           ("ست جميلة", set()), ("مرتين يوميًا", {2}), ("1,500 مجم", {1500}), ("1.500 مجم", {1.5, 1500})):
            with self.subTest(text=text):
                self.assertEqual(values_in(text), vals)


class TestTimingAndClaims(unittest.TestCase):
    def test_which_period(self):
        for a, b in (("ابدأي الدوا الشهر ده", "ابدأي الدوا الشهر الجاي"), ("ابدأي الدوا الأسبوع ده", "ابدأي الدوا الأسبوع الجاي"),
                     ("start it next month", "start it next week"), ("start it next week", "start it this week"),
                     ("خدي الدوا لمدة أسبوع", "خدي الدوا لمدة شهر"), ("take it for a week", "take it for a month")):
            with self.subTest(a=a, b=b):
                self.assertEqual(set(cmp(a, b)), {"timing"})
        self.assertEqual(cmp("ابدأي الدوا الشهر الجاي", "ابدأي الدوا الشهر الجاي"), {})
        self.assertEqual(cmp("خدي مرتين في اليوم", "خدي مرتين يوميا"), {})
        r = D.reading("take it for a week".split())
        self.assertNotIn(("per", "week"), [k for k, _ in r["timing"]])     # how long, not how often

    def test_meal_or_sleep_said_as_an_instruction(self):
        d = cmp("خدي حباية وبعدين نامي", "خدي حباية وبعدين اتغدي")             # 7193e9a P3-3
        self.assertEqual(d["timing"], {"a": ["نامي"], "b": ["اتغدي"]})

    def test_medicines_opposites_and_organs(self):
        for a, b in (("خدي البنادول بعد الأكل", "خدي الأسبرين بعد الأكل"), ("take ibuprofen after food", "take paracetamol after food"),
                     ("الدوا ده آمن", "الدوا ده خطر"), ("الأكل ده حلو", "الأكل ده وحش"), ("it is safe", "it is dangerous"),
                     ("بيقلل الضغط", "بيرفع الضغط"), ("it lowers the pressure", "it raises the pressure"),
                     ("it hurts the liver", "it hurts the kidney"), ("بيأثر على الكبد", "بيأثر على الكلى")):
            with self.subTest(a=a, b=b):
                self.assertIn("claim", cmp(a, b))
        for a, b in (("أول حاجة لازم تعرفي", "أول حاجة لازم تعرفيها كويس"), ("الدوا ده آمن", "الدوا ده آمن جدا"),
                     ("بيقلل الضغط", "مبيقللش الضغط"), ("بيقلل الضغط", "ما بيقللش الضغط")):
            with self.subTest(a=a, b=b):
                self.assertNotIn("claim", cmp(a, b))
        ar, en = D.describe(cmp("الدوا ده آمن", "الدوا ده خطر"))
        self.assertIn("كلام طبي مختلف: «آمن» مقابل «خطر»", ar)
        self.assertIn("a different medical word", en)


class TestTask25Retakes(unittest.TestCase):
    def test_every_review_probe_is_never_pre_ticked(self):
        for a, b in RETAKE_PROBES:
            with self.subTest(a=a, b=b):
                rt = retakes(a, b, "en" if a.isascii() else "ar")
                self.assertTrue(rt, "no retake found")
                self.assertEqual([p["default"] for p in rt], ["keep"] * len(rt))
                self.assertTrue(rt[0]["differs"])

    def test_default_keep_is_pinned_not_left_to_the_confidence(self):
        # d73c3e3 P3: a client whose conf_on_purpose is at or above keep_below would tick by confidence alone
        cfg = {"values": {**C.DEFAULTS, "conf_on_purpose": 0.95, "keep_below": 0.6},
               "fillers": {k: list(v) for k, v in C.FILLERS.items()}}
        for a, b in (("الدوا ده بيقلل الضغط.", "الدوا ده مبيقللش الضغط."),
                     ("خدي حباية الصبح من الدوا ده.", "خدي حباية بالليل من الدوا ده."),
                     ("خدي ٥٠٠ مجم من الدوا ده.", "خدي ٥٠٠ مجم من الدوا ده.")):
            with self.subTest(a=a):
                rt = retakes(a, b, cfg=cfg)
                self.assertTrue(rt)
                self.assertGreaterEqual(rt[0]["confidence"], cfg["values"]["keep_below"])
                self.assertEqual(rt[0]["default"], "keep")
        for spec, lang in (([("مرتين", 300, 60), ("مرتين", 300, 60), ("في", 200, 60), ("اليوم.", 300, 300)], "ar"),
                           ([("twice", 300, 60), ("twice", 300, 60), ("a", 200, 60), ("day.", 300, 300)], "en"),
                           ([("خدي", 300, 60), ("٥٠٠", 300, 60), ("٥٠٠", 300, 60), ("مجم.", 300, 300)], "ar")):
            with self.subTest(spec=spec[0][0]):
                res = C.compute(ws(spec), lang=lang, cfg=cfg)
                rep = [p for p in res["proposals"] if p["kind"] == "repeat_word"]
                self.assertEqual([p["default"] for p in rep], ["keep"])

    def test_aya_with_a_hidden_joiner_is_never_a_filler(self):
        for raw in ("آ‍يه", "آ‌ية", "‏آية"):
            with self.subTest(raw=ascii(raw)):
                self.assertTrue(C._never_filler(raw))
        self.assertFalse(C._never_filler("إيه"))


class TestK7Takes(unittest.TestCase):
    def test_every_review_probe_gets_no_best(self):
        for a, b, kind in TAKE_PROBES:
            with self.subTest(a=a):
                g = two_takes(a, b)
                self.assertIsNone(g["best"])
                self.assertIn(kind, g["differ"])
                self.assertIn("اسمعهم واختار انت", g["line_ar"])
                self.assertIn("يمكن تكون وقفت قبل", g["line_ar"])         # an explanation, never a reason to pick
                self.assertNotIn("الأفضل", g["line_ar"])

    def test_negation_forms_and_contractions_are_no_word_difference(self):
        for a, b in (("الدوا ده ما بيقللش الضغط خالص عند الكبار يا جماعة.", "الدوا ده مبيقللش الضغط خالص عند الكبار يا جماعة."),
                     ("you should not take this pill at all.", "you shouldn't take this pill at all."),
                     ("it does not lower the pressure at all.", "it doesn't lower the pressure at all."),
                     ("you do not need this pill at all.", "you don't need this pill at all.")):
            with self.subTest(a=a):
                g = two_takes(a, b)
                self.assertEqual(g["differ"], {})
                self.assertIsNotNone(g["best"])
                self.assertNotIn("⚠", g["line_ar"])

    def test_a_dose_said_by_repeating_the_unit(self):
        g = two_takes("خدي حباية من الدوا ده الصبح.", "خدي حباية وحباية من الدوا ده الصبح.")
        self.assertIsNone(g["best"])
        self.assertIn("حباية وحباية", g["differ"]["numbers"])


class TestSelfReviewRound1(unittest.TestCase):
    """The lane's own fresh-eyes review, round 1 (work/T25-neg/review): every repro is a test."""

    def test_p1_shi_ending_and_moosh(self):
        for w in ("مبيقللشي", "ماتاخدهوشي", "مخدتشي"):
            with self.subTest(w=w):
                self.assertEqual(neg(w), "verb")
        for w in ("موش", "مفش", "مافش"):
            with self.subTest(w=w):
                self.assertEqual(neg(w), "word")
        self.assertIsNone(neg("معاشي"))
        self.assertIsNone(neg("ماشي"))
        self.assertEqual(R.negated_core(fold("مبيقللشي")), "بيقلل")
        for b in ("الدوا ده مبيقللشي الضغط", "الدوا ده موش بيقلل الضغط"):
            with self.subTest(b=b):
                self.assertIn("negation", cmp("الدوا ده بيقلل الضغط", b))
                self.assertEqual(cmp(b, "الدوا ده مبيقللش الضغط"), {})

    def test_p1_conditions_and_exceptions(self):
        for a, b in (("take it if you have a fever today", "take it unless you have a fever today"),
                     ("take it if you have a fever today", "take it only if you have a fever today"),
                     ("خديه لو عندك سخونية", "خديه إلا لو عندك سخونية"),
                     ("take it with food except on fasting days", "take it with food on fasting days"),
                     ("الدوا ده آمن للحامل", "الدوا ده آمن للحامل بس في الشهور الأخيرة")):
            with self.subTest(a=a):
                self.assertIn("condition", cmp(a, b))
                rt = retakes(a, b, "en" if a.isascii() else "ar")
                self.assertEqual([p["default"] for p in rt], ["keep"] * len(rt))
        for a, b in (("لو سمحت خدي الدوا", "خدي الدوا"), ("بس خدي الدوا الصبح", "خدي الدوا الصبح"),
                     ("but take it in the morning", "take it in the morning")):
            with self.subTest(a=a):
                self.assertNotIn("condition", cmp(a, b))

    def test_p1_a_negation_that_moves(self):
        for a, b in (("مش بيقلل الضغط وبيقلل السكر", "بيقلل الضغط ومش بيقلل السكر"),
                     ("it is not safe for kids but safe for adults", "it is safe for kids but not safe for adults")):
            with self.subTest(a=a):
                self.assertIn("negation", cmp(a, b))
        g = two_takes("الدوا ده مش بيقلل الضغط وبيقلل السكر عند الكبار.", "الدوا ده بيقلل الضغط ومش بيقلل السكر عند الكبار.")
        self.assertIsNone(g["best"])

    def test_p1_leading_decimal_and_glued_half(self):
        self.assertEqual(heard(".5 mg"), [(0.5, "dose", False)])
        self.assertEqual(heard("٫٥ مجم"), [(0.5, "dose", False)])
        self.assertEqual(heard("٣ونص حباية"), [(3.5, "dose", False)])
        self.assertIn("numbers", cmp(".5 mg", ".25 mg"))
        self.assertIn("numbers", cmp("خدي ٣ونص حباية", "خدي ٣ حباية"))
        self.assertEqual(cmp("خدي ٣ونص حباية", "خدي ٣ ونص حباية"), {})

    def test_p2_two_readings_odd_fractions_split_commas_and_minus(self):
        self.assertIn("numbers", cmp("خدي ١٫٥٠٠ مجم", "خدي ١٫٥ مجم"))
        self.assertIn("numbers", cmp("take 10.000 IU", "take 10 IU"))
        self.assertEqual(heard("1⅟2 tablet"), [(None, "dose", True)])
        self.assertEqual(doses("1⅟2 tablet"), [(None, "dose", True)])
        for text in ("٣ ، ٥ مجم", "٣، ٥ مجم", "3 , 5 mg"):
            with self.subTest(text=text):
                self.assertEqual(heard(text), [(None, "dose", True)])
        self.assertEqual(heard("3 . 5 mg"), [(3.5, "dose", False)])         # Whisper's split decimal point stays
        self.assertEqual(heard("خدي ٣، وبعدين"), [(3, "number", False)])
        for text in ("−5 mg", "-5 mg"):
            with self.subTest(text=text):
                self.assertEqual(heard(text), [(None, "dose", True)])
        self.assertEqual(values_in("٣-٤ مرات"), {3, 4})

    def test_p3_more_everyday_words_are_no_negation(self):
        for w in ("مجروش", "مزركش", "مناقيش", "مناقش", "محشش", "مكرش", "مهروش", "مدردش", "مفشفش", "متحرش", "متوحش"):
            with self.subTest(w=w):
                self.assertIsNone(neg(w))
        for w in ("مخدوش", "معيش", "متاخدش"):                 # also negations: never guarded away
            with self.subTest(w=w):
                self.assertEqual(neg(w), "verb")


class TestSelfReviewRound2(unittest.TestCase):
    """The lane's own fresh-eyes review, round 2: every repro is a test."""
    LINE = "خديه بعد الأكل يا حبيبتي كل يوم"

    def test_p1_more_condition_words(self):
        for a, b in ((self.LINE, self.LINE + " فقط"), (self.LINE, self.LINE + " ماعدا الجمعة"),
                     (self.LINE, self.LINE + " عدا الجمعة"), ("خديه في حالة الصداع", "خديه وقت الصداع"),
                     ("take it even if you have a fever", "take it if you have a fever"),
                     ("take it just in case", "take it in case"), ("خديه حتى لو عندك سخونية", "خديه لو عندك سخونية")):
            with self.subTest(a=a, b=b):
                self.assertIn("condition", cmp(a, b))
                rt = retakes(a, b, "en" if a.isascii() else "ar")
                self.assertEqual([p["default"] for p in rt], ["keep"] * len(rt))

    def test_p2_a_comma_or_a_dot_said_apart(self):
        for text in ("3 ,5 mg", "1 ,500 mg", ". 5 mg", "٫ ٥ مجم", "..5 mg"):
            with self.subTest(text=text):
                self.assertEqual(heard(text), [(None, "dose", True)])
        self.assertIn("numbers", cmp("خدي ٣ ، ٥ مجم", "خدي ٣ ٥ مجم"))
        self.assertIn("numbers", cmp("خدي ٣، ٥ مجم", "خدي ٣ ٥ مجم"))

    def test_p3_minus_said_apart_and_figure_dash(self):
        for text in ("- 5 mg", "‒5 mg", "- ½ tablet"):
            with self.subTest(text=text):
                self.assertEqual(heard(text), [(None, "dose", True)])

    def test_p3_but_that_is_all_is_no_clause(self):
        for a, b in (("خديه بس كده", "خديه"), ("خديه بس خلاص", "خديه"), ("بس خديه", "خديه")):
            with self.subTest(a=a):
                self.assertNotIn("condition", cmp(a, b))
        # round 3 P2: «بعد الأكل بس» is "only after food", before «يا» or at the end alike
        for a, b in (("خديه بعد الأكل بس يا حبيبتي", "خديه بعد الأكل يا حبيبتي"), ("خديه بعد الأكل بس", "خديه بعد الأكل")):
            with self.subTest(a=a):
                self.assertIn("condition", cmp(a, b))
                rt = retakes(a, b)
                self.assertEqual([p["default"] for p in rt], ["keep"] * len(rt))

    def test_round3_a_comma_on_its_own_reaches_the_takes_reader(self):
        for sep in ("،", ","):
            with self.subTest(sep=sep):
                g = two_takes(f"خدي ٣ {sep} ٥ مجم من الدوا ده كل يوم.", "خدي ٣ ٥ مجم من الدوا ده كل يوم.")
                self.assertIsNone(g["best"])
                self.assertIn("numbers", g["differ"])

    def test_round3_when_said_two_ways_and_water(self):
        self.assertNotIn("condition", cmp("خديه لما تصحي", "خديه أول ما تصحي"))
        self.assertNotIn("condition", cmp("take it when you wake up", "take it as soon as you wake up"))
        self.assertEqual(heard("اشربي مية كتير"), [])
        self.assertEqual(heard("مية جرام"), [(100, "dose", False)])

    def test_p3_the_line_names_what_is_negated_when_the_words_look_the_same(self):
        d = cmp("مش لازم تاخديه", "مش ضروري تاخديه")
        self.assertEqual(d["negation"], {"a": ["مش لازم تاخديه"], "b": ["مش ضروري تاخديه"]})
        d = cmp("الدوا ده بيقلل الضغط", "الدوا ده مش بيقلل الضغط")
        self.assertEqual(d["negation"], {"a": [], "b": ["مش"]})


class TestEpisodeReason(unittest.TestCase):
    """b29d47f P3-2: a reel's copy of its episode's verification that still blocks says why."""

    def test_every_reason_is_named(self):
        meta = {"meta": {"episode_transcript": "/x/ep/02_transcription/words.json"}}
        self.assertEqual(R._episode_reason({}, b"w", {}), "none")
        self.assertEqual(R._episode_reason(meta, None, None), "missing")
        self.assertEqual(R._episode_reason(meta, b"w", None), "missing")
        self.assertEqual(R._episode_reason(meta, b"w", {"verified": False}), "not_verified")
        self.assertEqual(R._episode_reason(meta, b"w", {"verified": True, "words_sha1": "0" * 40}), "changed")
        import hashlib
        ok = {"verified": True, "words_sha1": hashlib.sha1(b"w").hexdigest(), "by": "Claude"}
        self.assertEqual(R._episode_reason(meta, b"w", ok), ["by", "claude"])
        for reason in ("none", "missing", "not_verified", "changed", ["by", "claude"], ["by", ""]):
            with self.subTest(reason=reason):
                h = R._episode_hint(reason)
                self.assertIn("reel transcript-verify --by editor", h)
                self.assertLess(h.find("—"), h.find("/"))                       # Arabic first
        self.assertEqual(R._episode_hint(None), "")

    def test_the_plan_error_carries_the_reason(self):
        rep = {"items": [{"risk": "dose", "high": True, "flagged": False, "text": "٥٠٠ مجم", "value": 500,
                          "word_ids": [3, 4], "start_ms": 0, "why": [("x", "x")]}],
               "domain": "medical", "verified_by": None, "unfingerprinted": False, "episode": "changed"}
        with mock.patch("lib.plan.onscreen_strings", lambda params: ["خدي ٥٠٠ مجم"]):
            errs = R._errors(rep, [{"event_id": "G1", "params": {}}])
        self.assertEqual(len(errs), 1)
        self.assertIn(R.EPISODE_REASONS["changed"][0], errs[0])
        self.assertIn(R.EPISODE_REASONS["changed"][1], errs[0])


if __name__ == "__main__":
    unittest.main()
