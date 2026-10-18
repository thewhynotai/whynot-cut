# SPDX-License-Identifier: GPL-3.0-or-later
# © 2026 The Why Not AI (thewhynot.ai)
"""3.0 Phase 4 Task 54 = Addendum M2-T1: mixed Arabic + English lines (lib/bidi_lines.py).

The paragraph direction is decided once (HL1: any Arabic letter = RTL, else P2/P3), the levels are resolved on the whole
paragraph (UAX #9 X1–I2), the paragraph is broken into lines, and only then is each line reordered (L1–L2). The fixture
table (tests/fixtures/bidi/lines.json, ≥ 60 lines) gives the expected visual runs by hand; each line is also checked
against an independent UAX #9 implementation (python-bidi, LGPL, already an engine runtime module: used here only) and a
sample of the Unicode conformance file (BidiCharacterTest.txt, Unicode License v3).
Run:  bash tools/test.sh -p test_bidi_lines.py
"""
import sys as _sys
_sys.dont_write_bytecode = True  # keep the plugin folder free of __pycache__
import _isolation  # noqa: F401,E402  G79: sandbox the engine home first (tests/_isolation.py)
import ast
import builtins
import json
import random
import time
import unicodedata
import unittest
from decimal import Decimal
from fractions import Fraction
from pathlib import Path
from unittest import mock

sys = _sys
SK = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SK / "engine" / "reel"))

from lib import bidi_lines as bl  # noqa: E402
from bidi import get_display  # noqa: E402  python-bidi 0.6.11 (LGPL, test-only), pinned in the engine locks

FX = SK / "tests" / "fixtures" / "bidi"
LINES = json.loads((FX / "lines.json").read_text(encoding="utf-8"))["lines"]
CONTROLS = {chr(c) for c in (0x2066, 0x2067, 0x2068, 0x2069, 0x200E, 0x200F, 0x061C,
                              0x202A, 0x202B, 0x202C, 0x202D, 0x202E)}


def runs(text, **kw):
    return [[r.level, r.text] for r in bl.line_runs(bl.paragraph(text, **kw))]


def lines(text, width):
    return [ln.text for ln in bl.lay_out(text, width)]


class TestFixtureTable(unittest.TestCase):
    def test_the_table_has_at_least_60_lines_and_covers_the_spec_list(self):
        self.assertGreaterEqual(len(LINES), 60)
        ids = " ".join(e["id"] for e in LINES)
        for kind in ("price", "dose", "percent", "range", "phone", "al-latin", "bracket", "quotes", "question",
                     "comma", "latin-only", "arabic-only", "url", "brand", "isolate", "harakat", "lam-alef"):
            self.assertIn(kind, ids, kind)
        self.assertEqual(len({e["id"] for e in LINES}), len(LINES))
        for e in LINES:                                         # HL3 rows name their phone; no other row has one
            self.assertEqual("hl3" in e["id"], "phone" in e, e["id"])
            if "phone" in e:
                self.assertEqual([e["text"][a:b] for a, b in bl.phone_spans(e["text"])], [e["phone"]], e["id"])
            elif e["rtl"]:
                self.assertEqual(bl.phone_spans(e["text"]), [], e["id"])

    def test_every_line_gives_the_expected_direction_and_visual_runs(self):
        for e in LINES:
            with self.subTest(e["id"]):
                par = bl.paragraph(e["text"])
                self.assertEqual(par.rtl, e["rtl"])
                self.assertEqual([[r.level, r.text] for r in bl.line_runs(par)], e["runs"])

    def test_every_line_matches_an_independent_uax9_implementation(self):
        for e in LINES:
            with self.subTest(e["id"]):
                par = bl.paragraph(e["text"])
                text = e["text"]
                if "phone" in e:                               # HL3, hand-given: the phone as LRO … PDF
                    text = text.replace(e["phone"], "\u202d" + e["phone"] + "\u202c")
                ref = "".join(c for c in get_display(text, base_dir="R" if par.rtl else "L") if c not in CONTROLS)
                self.assertEqual(bl.visual(par, mirror=False), ref)

    def test_unicode_conformance_sample(self):
        n = 0
        for ln in (FX / "BidiCharacterTest-sample.txt").read_text(encoding="utf-8").splitlines():
            if not ln or ln.startswith("#"):
                continue
            f = ln.split(";")
            text = "".join(chr(int(x, 16)) for x in f[0].split())
            par = bl.paragraph(text, base=None if f[1] == "2" else int(f[1]), hl1=False)
            lv = bl._line_levels(par, 0, len(text))
            with self.subTest(ln):
                self.assertEqual(par.base, int(f[2]))
                self.assertEqual(["x" if par.removed[i] else str(lv[i]) for i in range(len(text))], f[3].split())
                self.assertEqual([i for i in bl.reorder(lv) if not par.removed[i]], [int(x) for x in f[4].split()])
            n += 1
        self.assertGreater(n, 400)

    def test_sos_and_eos_come_from_the_explicit_levels(self):
        # BidiCharacterTest.txt lines an early draft failed: sos/eos read levels I1/I2 had already raised
        for ln in ("05D0 202A 05D1 202C 0020 0031 0020 0032;0;0;1 x 3 x 0 0 0 0;2 0 4 5 6 7",
                   "05D0 202B 0062 202C 0020 0031 0020 0032;1;1;1 x 4 x 1 2 1 2;7 6 5 4 2 0",
                   "0061 0028 0062 202B 0063 202C 0029 0020 0031;1;1;2 2 2 x 4 x 1 1 2;8 7 6 0 1 2 4"):
            f = ln.split(";")
            text = "".join(chr(int(x, 16)) for x in f[0].split())
            par = bl.paragraph(text, base=int(f[1]), hl1=False)
            lv = bl._line_levels(par, 0, len(text))
            with self.subTest(ln):
                self.assertEqual(["x" if par.removed[i] else str(lv[i]) for i in range(len(text))], f[3].split())
                self.assertEqual([i for i in bl.reorder(lv) if not par.removed[i]], [int(x) for x in f[4].split()])


class TestNamedCases(unittest.TestCase):
    """The four cases M2.3 names."""

    def test_latin_first_paragraph_with_arabic_stays_rtl_hl1(self):
        self.assertEqual(bl.direction("AI بيغيّر الطب"), 1)
        self.assertEqual(runs("AI بيغيّر الطب"), [[1, " بيغيّر الطب"], [2, "AI"]])

    def test_wrapped_second_line_all_latin_stays_rtl_with_the_period_on_the_left(self):
        out = bl.lay_out("الدكتور طلب مني أعمل complete blood count test.", 26)
        self.assertEqual([ln.text for ln in out], ["الدكتور طلب مني أعمل", "complete blood count test."])
        self.assertTrue(all(ln.rtl for ln in out))
        self.assertEqual([[r.level, r.text] for r in out[1].runs], [[1, "."], [2, "complete blood count test"]])

    def test_blood_sugar_level_keeps_its_order_inside_arabic_n1(self):
        self.assertEqual(runs("مستوى blood sugar level عالي"), [[1, " عالي"], [2, "blood sugar level"], [1, "مستوى "]])

    def test_western_digits_after_arabic_letters_order_as_arabic_numbers_w2(self):
        par = bl.paragraph("السعر 1,250 جنيه")
        self.assertEqual(par.levels[6:11], [2] * 5)            # «1,250» one AN unit (W2 then W4)
        self.assertEqual(runs("نسبة 50% من الناس"), [[1, "% من الناس"], [2, "50"], [1, "نسبة "]])
        self.assertEqual(runs("Vitamin D 3000 وحدة"), [[1, " وحدة"], [2, "Vitamin D 3000"]])   # after Latin: W7


class TestDirection(unittest.TestCase):
    def test_p2_p3_only_without_arabic_letters(self):
        self.assertEqual(bl.direction("This is fine"), 0)
        self.assertEqual(bl.direction("123 - 456"), 0)          # no strong letter: LTR
        self.assertEqual(bl.direction("١٢٣"), 0)                # Arabic-Indic digits are not letters
        self.assertEqual(bl.direction("שלום world"), 1)         # P2: first strong is R
        self.assertEqual(bl.direction("world שלום"), 0)

    def test_hl1_counts_arabic_letters_not_arabic_punctuation(self):
        self.assertEqual(bl.direction("Do you have diabetes؟"), 0)
        self.assertEqual(bl.direction("item one؛ item two"), 0)
        self.assertEqual(bl.direction("one، two"), 0)
        self.assertEqual(bl.direction("diabetes؟ يعني"), 1)

    def test_arabic_only_inside_an_isolate_does_not_make_the_paragraph_rtl(self):
        self.assertEqual(bl.direction("Hello \u2067مرحبا\u2069 world"), 0)

    def test_a_client_can_force_rtl(self):
        self.assertEqual(bl.direction("This is fine", force_rtl=True), 1)
        self.assertEqual(runs("This is fine", force_rtl=True), [[2, "This is fine"]])
        self.assertTrue(all(ln.rtl for ln in bl.lay_out("This is fine", force_rtl=True)))

    def test_the_direction_is_never_decided_per_line(self):
        out = bl.lay_out("شوف\nthe new results", None)
        self.assertEqual([ln.text for ln in out], ["شوف", "the new results"])
        self.assertTrue(out[1].rtl)
        self.assertEqual([[r.level, r.text] for r in out[1].runs], [[2, "the new results"]])
        out = bl.lay_out("سطر\r\nsecond, line\u2029ثالث", None)
        self.assertEqual([ln.text for ln in out], ["سطر", "second, line", "ثالث"])
        self.assertEqual([(ln.start, ln.end) for ln in out], [(0, 3), (5, 17), (18, 22)])


class TestPerLineOrder(unittest.TestCase):
    def test_a_latin_run_split_over_two_lines_keeps_logical_order_on_each(self):
        text = "عملت تحليل complete blood count test امبارح"
        out = bl.lay_out(text, 26)
        self.assertEqual([ln.text for ln in out], ["عملت تحليل complete blood", "count test امبارح"])
        self.assertEqual([[r.level, r.text] for r in out[0].runs], [[2, "complete blood"], [1, "عملت تحليل "]])
        self.assertEqual([[r.level, r.text] for r in out[1].runs], [[1, " امبارح"], [2, "count test"]])
        # reordering the whole paragraph first would put «امبارح» at the far left of line 1
        whole = bl.visual(bl.paragraph(text))
        self.assertTrue(whole.startswith("حرابما"))
        self.assertNotIn("حرابما", bl.visual(bl.paragraph(text), out[0].start, out[0].end))

    def test_levels_come_from_the_whole_paragraph_not_the_line(self):
        par = bl.paragraph("السعر\n500")
        self.assertEqual(par.levels[6:], [2, 2, 2])            # W2 sees «السعر» across the hard break
        out = bl.lay_out("السعر\n500")
        self.assertEqual([[r.level, r.text] for r in out[1].runs], [[2, "500"]])

    def test_l1_trailing_whitespace_takes_the_paragraph_level(self):
        self.assertEqual(runs("مرحبا \u2066abc \u2069"), [[1, " "], [2, "abc"], [1, "مرحبا "]])

    def test_reorder_l2(self):
        self.assertEqual(bl.reorder([0, 0, 1, 1, 2, 2, 1, 0]), [0, 1, 6, 4, 5, 3, 2, 7])
        self.assertEqual(bl.reorder([]), [])

    def test_runs_carry_no_controls_and_keep_joiners_and_marks(self):
        for e in LINES:
            for r in bl.line_runs(bl.paragraph(e["text"])):
                self.assertFalse(CONTROLS & set(r.text), e["id"])
        self.assertEqual(runs("لا\u200cمركزية"), [[1, "لا\u200cمركزية"]])   # ZWNJ (BN) stays with its letters
        self.assertEqual(runs("الطِّبُّ"), [[1, "الطِّبُّ"]])

    def test_visual_mirrors_brackets_in_rtl_runs_only(self):
        par = bl.paragraph("العلاج (insulin) مهم")
        self.assertEqual(bl.visual(par), "مهم"[::-1] + " (" + "insulin" + ") " + "العلاج"[::-1])
        self.assertEqual(bl.visual(par, mirror=False), "مهم"[::-1] + " )" + "insulin" + "( " + "العلاج"[::-1])
        self.assertEqual(bl.visual(bl.paragraph("Check (the) list")), "Check (the) list")

    def test_logical_runs_keep_logical_order(self):
        par = bl.paragraph("٧٠٪ من \u2066AI\u2069")
        self.assertEqual([(r.text, r.level) for r in bl.logical_runs(par)], [("٧٠", 2), ("٪ من ", 1), ("AI", 2)])
        self.assertEqual([(r.start, r.end) for r in bl.logical_runs(par)], [(0, 2), (2, 7), (8, 10)])

    def test_word_pieces_for_word_based_layout(self):
        def wp(ws, **kw):
            rtl, ps = bl.word_pieces(ws, **kw)
            return rtl, [(p.word, p.text, p.level) for p in ps]
        # one word in two pieces that are not neighbours: «MRI scan» is one Latin phrase left of «بالـ»
        self.assertEqual(wp(["بالـMRI", "scan"]),
                         (True, [(0, "MRI", 2), (None, " ", 2), (1, "scan", 2), (0, "بالـ", 1)]))
        self.assertEqual(wp(["السكر", "بيقل", "٤٠٪"]),
                         (True, [(2, "٪", 1), (2, "٤٠", 2), (None, " ", 1), (1, "بيقل", 1), (None, " ", 1),
                                 (0, "السكر", 1)]))
        # a moved period: no space between it and the word it now touches
        self.assertEqual(wp(["complete", "blood", "test."], base=1),
                         (True, [(2, ".", 1), (0, "complete", 2), (None, " ", 2), (1, "blood", 2), (None, " ", 2),
                                 (2, "test", 2)]))
        self.assertEqual(wp(["استخدمت", "iPhone", "15", "Pro"]),
                         (True, [(1, "iPhone", 2), (None, " ", 2), (2, "15", 2), (None, " ", 2), (3, "Pro", 2),
                                 (None, " ", 1), (0, "استخدمت", 1)]))
        self.assertEqual(wp(["this", "is"]), (False, [(0, "this", 0), (None, " ", 0), (1, "is", 0)]))
        self.assertEqual(bl.word_pieces(["this", "is"], force_rtl=True)[0], True)
        self.assertEqual(bl.word_pieces(["second", "line"], base=1)[1][0].level, 2)   # a wrapped line keeps the base
        self.assertEqual(bl.word_pieces([]), (False, []))
        for e in LINES:                                         # the pieces are the line, in visual order
            if any(c in CONTROLS for c in e["text"]):
                continue
            with self.subTest(e["id"]):
                ps = bl.word_pieces(e["text"].split(" "))[1]
                self.assertEqual("".join(p.text[::-1] if p.rtl else p.text for p in ps),
                                 bl.visual(bl.paragraph(e["text"]), mirror=False))

    def test_line_pieces_follow_the_drawn_runs_of_a_wrapped_line(self):
        out = bl.lay_out("عملت أشعة بالـMRI 2024 500 مرة", 14, balanced=True)
        last = out[-1]
        self.assertEqual(last.text, "2024 500 مرة")
        ps = [(p.word, p.text) for p in bl.line_pieces(last)]
        self.assertEqual(ps, [(2, "مرة"), (None, " "), (0, "2024"), (None, " "), (1, "500")])   # W7 across the break
        self.assertNotEqual([(p.word, p.text) for p in bl.word_pieces(last.text.split(" "), base=1)[1]], ps)
        import random
        rnd = random.Random(7)
        words = ["عملت", "بالـMRI", "2024", "500", "test.", "1.5", "(insulin)", "«AI»", "كده؟", "blood", "٤٠٪", "010",
                 "1234", "5678", "الـ", "CT", "$99", "-5", "\u2066x y\u2069"]
        for _ in range(1500):
            text = " ".join(rnd.choice(words) for _ in range(rnd.randint(1, 8)))
            for ln in bl.lay_out(text, rnd.choice([6, 10, 14, 30])):
                ps = bl.line_pieces(ln)
                self.assertEqual("".join(p.text[::-1] if p.rtl else p.text for p in ps),
                                 "".join(r.text[::-1] if r.rtl else r.text for r in ln.runs), text)
                ws = ln.text.split(" ")
                self.assertTrue(all(p.word is None or p.text in ws[p.word] for p in ps), text)

    def test_run_direction_names(self):
        r = bl.line_runs(bl.paragraph("AI بيغيّر"))
        self.assertEqual([(x.rtl, x.dir) for x in r], [(True, "rtl"), (False, "ltr")])


class TestNoBreak(unittest.TestCase):
    def test_al_and_its_latin_word(self):
        self.assertEqual(bl.word_breaks(["عملت", "الـ", "MRI", "امبارح"]), ["ok", "never", "ok"])
        self.assertEqual(bl.word_breaks(["روحت", "بالـ", "CT", "scan"]), ["ok", "never", "avoid"])
        self.assertEqual(bl.word_breaks(["الـ", "«MRI»"]), ["never"])
        self.assertEqual(bl.word_breaks(["الـ", "5G"]), ["never"])
        self.assertEqual(bl.word_breaks(["بالـ", "عربي"]), ["ok"])
        self.assertEqual(lines("عملت الـ MRI امبارح", 8), ["عملت", "الـ MRI", "امبارح"])

    def test_a_number_and_its_unit(self):
        self.assertEqual(bl.word_breaks(["خد", "٥٠٠", "mg", "مرتين"]), ["ok", "never", "ok"])
        self.assertEqual(bl.word_breaks(["السعر", "100", "جنيه"]), ["ok", "never"])
        self.assertEqual(bl.word_breaks(["50", "%"]), ["never"])
        self.assertEqual(bl.word_breaks(["2.5", "mg/dL."]), ["never"])
        self.assertEqual(bl.word_breaks(["$", "50"]), ["never"])
        self.assertEqual(bl.word_breaks(["السعر", "50", "$", "بس"]), ["ok", "never", "ok"])
        self.assertEqual(bl.word_breaks(["EGP", "1,500"]), ["never"])
        self.assertEqual(lines("خد ٥٠٠ mg مرتين", 6), ["خد", "٥٠٠ mg", "مرتين"])

    def test_phone_numbers_and_ranges(self):
        self.assertEqual(lines("كلمني على 010 1234 5678.", 8), ["كلمني", "على", "010 1234 5678."])
        self.assertEqual(bl.word_breaks(["السنوات", "2020", "2021", "2022"]), ["ok", "ok", "ok"])   # a list
        self.assertEqual(bl.word_breaks(["كلمنا", "010", "1234", "5678"]), ["ok", "never", "never"])
        self.assertEqual(bl.word_breaks(["رقمنا", "+20", "10", "12", "345"]), ["ok", "never", "never", "never"])
        self.assertEqual(bl.word_breaks(["من", "10", "-", "20", "قبل"]), ["ok", "never", "never", "ok"])
        self.assertEqual(bl.word_breaks(["10", "-", "20", "دقيقة"]), ["never", "never", "never"])
        self.assertEqual(lines("كلمنا على 010 1234 5678", 6), ["كلمنا", "على", "010 1234 5678"])

    def test_what_is_and_is_not_a_phone_number(self):
        def ph(t):
            return [t[a:b] for a, b in bl.phone_spans(t)]
        for t, want in (("اتصل 010 1234 5678 24 ساعة", ["010 1234 5678"]),       # a short number after it is not part
                        ("رقمي:010 1234 5678،", ["010 1234 5678"]),
                        ("+966 5 1234 5678", ["+966 5 1234 5678"]),
                        ("0100 123 4567", ["0100 123 4567"]), ("02 2345 6789", []),             # no cue: a list (ruling)
                        ("+201001234567", ["+201001234567"]),
                        ("010 1234 5678/9", []), ("010 1234 5678٪", []),          # glued: never a shorter prefix
                        ("الدقايق 05 10 15 20", []), ("10:00 15 20 30", []), ("٠١-٠٢-٢٠٢٤", []),
                        ("+20 10 12 34 56 78 90", []), ("0.5 مجم", []), ("05:30", []), ("01/02/2024", []),
                        ("19999", []), ("السنوات 2020 2021 2022 2023", []),
                        ("الخط الساخن 010 1234 5678 24/7", ["010 1234 5678"]),       # numbers around it
                        ("010 1234 5678 12:30", ["010 1234 5678"]), ("010 1234 5678 3.5", ["010 1234 5678"]),
                        ("اتصل 3 010 1234 5678", ["010 1234 5678"]), ("2024 010 1234 5678", ["010 1234 5678"]),
                        ("010 1234 5678-9", []),
                        ("010 1234 5678 011 2345 6789", ["010 1234 5678", "011 2345 6789"]),
                        ("(010 1234 5678)", ["010 1234 5678"]), ("010-1234-5678", ["010-1234-5678"]),
                        ("+20 1001 2345 6789 0123", []), ("+201001234567890", ["+201001234567890"]),
                        ("010 1234 5678 2024", ["010 1234 5678"]), ("+20 100 123 4567 2024", ["+20 100 123 4567"]),
                        ("2024-010-1234-5678", [])):
            with self.subTest(t):
                self.assertEqual(ph(t), want)
        bl.lay_out("السنوات " + " ".join(str(2000 + i) for i in range(23)), 30)
        assert_linear(self, lambda n: bl.phone_spans(" ".join(["123"] * n)), 3000, 12000,
                      "number list")                            # linear: a long list of numbers never stalls a render
        self.assertEqual(bl.word_breaks(["اتصل", "010", "1234", "5678", "24", "ساعة"]),
                         ["ok", "never", "never", "ok", "never"])

    def test_brackets_quotes_and_closing_punctuation(self):
        self.assertEqual(bl.word_breaks(["العلاج", "(", "insulin", ")", "مهم"]), ["ok", "never", "never", "ok"])
        self.assertEqual(bl.word_breaks(["«", "evidence", "based", "»"]), ["never", "avoid", "never"])
        self.assertEqual(bl.word_breaks(["قال", "كده", "!"]), ["ok", "never"])
        self.assertEqual(bl.word_breaks(["سكر", "،", "ضغط"]), ["never", "ok"])

    def test_short_latin_run_is_avoided_when_another_break_fits(self):
        self.assertEqual(bl.word_breaks(["عندي", "insulin", "resistance", "عالية"]), ["ok", "avoid", "ok"])
        self.assertEqual(lines("عندي insulin resistance عالية جدا", 20), ["عندي", "insulin resistance", "عالية جدا"])
        self.assertEqual(lines("insulin resistance", 10), ["insulin", "resistance"])        # no other break
        self.assertEqual(lines("insulin resistance عالية", 3), ["insulin resistance", "عالية"])  # overflow: "ok" first
        self.assertEqual(bl.word_breaks(["اشتريت", "iPhone", "15", "Pro"]), ["ok", "avoid", "avoid"])

    def test_a_latin_run_of_four_words_breaks_normally(self):
        self.assertEqual(bl.word_breaks(["complete", "blood", "count", "test"]), ["ok"] * 3)
        self.assertEqual(lines("complete blood count test", 15), ["complete blood", "count test"])

    def test_a_unit_wider_than_the_line_stays_whole(self):
        self.assertEqual(lines("عملت الـ MRI", 3), ["عملت", "الـ MRI"])
        self.assertEqual(lines("Supercalifragilistic", 5), ["Supercalifragilistic"])

    def test_no_break_spaces_are_never_break_points(self):
        self.assertEqual(lines("خد ٥٠٠\u00a0مجم\u202fيوميا", 3), ["خد", "٥٠٠\u00a0مجم\u202fيوميا"])

    def test_breaks_report_spans_and_skip_edges(self):
        self.assertEqual(bl.breaks("  عملت  الـ MRI "), [(6, 8, "ok")])
        self.assertEqual(lines("   ", 5), [""])
        self.assertEqual(bl.wrap("   ", 5), [])
        self.assertEqual(lines("سطر\n\nسطر", None), ["سطر", "", "سطر"])
        self.assertEqual(lines("سطر\n\nسطر", 10), ["سطر", "", "سطر"])
        self.assertEqual(bl.word_breaks([]), [])
        self.assertEqual(bl.word_breaks(["كلمة"]), [])

    def test_balanced_wrap_evens_the_lines_and_keeps_every_rule(self):
        self.assertEqual(lines("one two three four five six seven", 30), ["one two three four five six", "seven"])
        out = [ln.text for ln in bl.lay_out("one two three four five six seven", 30, balanced=True)]
        self.assertEqual(out, ["one two three four", "five six seven"])
        text = "قالي الدكتور إن الـ MRI و الـ CT scan مهمين جدا في الحالة دي"
        for w in range(6, 40):
            spans = bl.wrap(text, w, balanced=True)
            self.assertEqual(len(spans), len(bl.wrap(text, w)), w)
            allowed = {s for s, _, _ in bl.breaks(text)}
            for (_, e1), _ in zip(spans, spans[1:]):
                self.assertIn(e1, allowed, (w, spans))

    def test_balanced_wrap_is_fast_and_never_worse_than_greedy(self):
        import time
        for n, w in ((25, 14), (60, 12), (120, 30)):
            text = " ".join(["كلمة"] * n)
            t0 = time.perf_counter()
            g, b = bl.wrap(text, w), bl.wrap(text, w, balanced=True)
            self.assertLess(time.perf_counter() - t0, 2.0, n)
            self.assertEqual(len(b), len(g))
            self.assertLessEqual(max(e - s for s, e in b), max(e - s for s, e in g))
        # every option overflows: both keep the Latin term together (fewest "avoid" breaks among equal overflow lines)
        self.assertEqual(bl.wrap("insulin resistance عالية", 3, balanced=True), bl.wrap("insulin resistance عالية", 3))
        # the "ok" break comes first; the "avoid" break is still taken when it is the only one that fits
        self.assertEqual(lines("عندي insulin resistance", 12), ["عندي", "insulin", "resistance"])

    def test_measure_is_the_callers(self):
        self.assertEqual(bl.wrap("اا ب ج", 3), [(0, 2), (3, 6)])
        self.assertEqual(bl.wrap("اا ب ج", 3, measure=lambda s: len(s.replace(" ", ""))), [(0, 4), (5, 6)])


class TestDigitsAndPunctuation(unittest.TestCase):
    def test_set_digits_both_ways_with_separators(self):
        self.assertEqual(bl.set_digits("خد 2.5 مجم و 1,500 جنيه و 50%", "arabic"), "خد ٢٫٥ مجم و ١٬٥٠٠ جنيه و ٥٠٪")
        self.assertEqual(bl.set_digits("خد ٢٫٥ مجم و ٥٠٪", "western"), "خد 2.5 مجم و 50%")
        self.assertEqual(bl.set_digits("رقم ۱۲۳", "arabic"), "رقم ١٢٣")             # Persian digits normalised
        self.assertEqual(bl.set_digits("الساعة 10:30", "arabic"), "الساعة ١٠:٣٠")

    def test_numbers_glued_to_a_latin_unit_convert_lists_and_versions_do_not_change_meaning(self):
        self.assertEqual(bl.set_digits("خد 500mg و 2 حباية", "arabic"), "خد ٥٠٠mg و ٢ حباية")
        self.assertEqual(bl.set_digits("خد ٥٠٠mg.", "western"), "خد 500mg.")
        self.assertEqual(bl.set_digits("الأرقام 5,6,7", "arabic"), "الأرقام ٥,٦,٧")
        self.assertEqual(bl.set_digits("الإصدار 3.0.1", "arabic"), "الإصدار 3.0.1")
        self.assertEqual(bl.set_digits("المبلغ 1,250,000.50", "arabic"), "المبلغ ١٬٢٥٠٬٠٠٠٫٥٠")
        self.assertEqual(bl.set_digits("1.2.3mg و 500mg/kg", "arabic"), "1.2.3mg و ٥٠٠mg/kg")
        self.assertEqual(bl.set_digits("(500mg) 500mg، 3-5mg 500mg؟ «2mg»", "arabic"),
                         "(٥٠٠mg) ٥٠٠mg، ٣-٥mg ٥٠٠mg؟ «٢mg»")

    def test_numbers_glued_to_latin_and_urls_are_left_alone(self):
        s = "COVID-19 و H1N1 و MP4 على www.site.com/2026 و a1@b.com و iPhone 15"
        self.assertEqual(bl.set_digits(s, "arabic"), s.replace("iPhone 15", "iPhone ١٥"))

    def test_set_digits_is_idempotent_and_refuses_unknown_styles(self):
        once = bl.set_digits("زاد 12.5% في 2026", "arabic")
        self.assertEqual(bl.set_digits(once, "arabic"), once)
        with self.assertRaises(ValueError):
            bl.set_digits("1", "hindi")

    def test_punctuation_findings_detect_only(self):
        self.assertEqual([(f["index"], f["suggest"]) for f in bl.punctuation_findings("apples، oranges")], [(6, ",")])
        f = bl.punctuation_findings("عندك سكر?")
        self.assertEqual([(x["index"], x["suggest"]) for x in f], [(8, "؟")])
        self.assertEqual(bl.punctuation_findings("سكر، ضغط، cholesterol؟"), [])
        self.assertEqual(bl.punctuation_findings("السعر 1,500 جنيه"), [])
        self.assertEqual(bl.punctuation_findings("Is it MRI?"), [])


class TestContract(unittest.TestCase):
    def test_pure_deterministic_and_never_opens_a_file(self):
        with mock.patch.object(builtins, "open", side_effect=AssertionError("no file access")):
            a = [(ln.text, ln.runs) for e in LINES for ln in bl.lay_out(e["text"], 12)]
            b = [(ln.text, ln.runs) for e in LINES for ln in bl.lay_out(e["text"], 12)]
            bl.set_digits("1", "arabic")
            bl.punctuation_findings("a، b")
            bl.control_findings("a b")
            [bl.host_text(ln) for e in LINES for ln in bl.lay_out(e["text"], 12)]
        self.assertEqual(a, b)

    def test_refusals_raise_cleanly(self):
        with self.assertRaises(ValueError):
            bl.wrap("abc", 0)
        with self.assertRaises(ValueError):
            bl.paragraph("abc", base=2)
        with self.assertRaises(ValueError):
            bl.line_runs(bl.paragraph("abc"), 2, 9)

    def test_one_code_path_on_windows_and_macos(self):
        # no platform branch: the module imports no os/sys/platform/subprocess/pathlib and opens nothing, so
        # Windows and macOS run the same lines (the old darwin reload could not fail)
        tree = ast.parse((SK / "engine" / "reel" / "lib" / "bidi_lines.py").read_text(encoding="utf-8"))
        names = {a.name.split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
        names |= {n.module.split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) and n.module}
        self.assertEqual(names & {"os", "sys", "platform", "subprocess", "pathlib", "ctypes"}, set())
        self.assertFalse([n for n in ast.walk(tree) if isinstance(n, ast.Name) and n.id == "open"])

    def test_the_unicode_data_is_the_bracket_tables_version(self):
        # _BRACKETS is BidiBrackets.txt 15.0 and the conformance sample is 15.0.0: a Python whose unicodedata moves
        # on must re-check them first
        self.assertEqual(unicodedata.unidata_version, "15.0.0")
        head = (FX / "BidiCharacterTest-sample.txt").read_text(encoding="utf-8").splitlines()[:8]
        self.assertIn("# BidiCharacterTest-15.0.0.txt", head)
        self.assertIn("# © 2022 Unicode®, Inc.", head)
        self.assertFalse([h for h in head if "1991" in h])

    def test_hl3_never_overrides_the_authors_own_controls(self):
        self.assertEqual(runs("كلمنا \u202e010 1234 5678\u202c"), [[3, "010 1234 5678"], [1, "كلمنا "]])
        deep = "\u202b" * 124 + "كلمنا 010 1234 5678" + "\u202c" * 124
        self.assertEqual(bl.phone_spans(deep), [(130, 143)])
        self.assertEqual(bl.paragraph(deep).levels[130:143], bl.paragraph(deep, hl1=False).levels[130:143])

    def test_host_text_gives_a_full_uax9_engine_this_modules_order(self):
        # every logical run in embeddings up to its level, the last one an override of its direction; RLM/LRM first
        self.assertEqual(bl.host_text(bl.paragraph("AI بيغيّر الطب")),
                         "\u200f\u202a\u202dAI\u202c\u202c\u202e بيغيّر الطب\u202c")
        self.assertEqual(bl.host_text(bl.paragraph("hello world", base=0)), "\u200e\u202dhello world\u202c")
        self.assertEqual(bl.host_text(bl.paragraph("كلمنا \u2066010 1234 5678\u2069")).count("\u2066"), 0)   # resolved already
        self.assertIn("\u200d", bl.host_text(bl.paragraph("لا\u200dمركزية a\u200cb")))                       # joiners stay
        with self.assertRaises(ValueError):
            bl.host_text(bl.paragraph("x"), base=3)
        for e in LINES:                                         # a full UAX #9 engine + host_text = our order
            with self.subTest(e["id"]):
                par = bl.paragraph(e["text"])
                ref = get_display(bl.host_text(par), base_dir=None)
                self.assertEqual("".join(c for c in ref if c not in CONTROLS), bl.visual(par, mirror=False))

    def test_deep_nesting_overflow_is_safe(self):
        text = "\u202b" * 200 + "abc" + "\u202c" * 200 + " مرحبا"
        par = bl.paragraph(text)
        self.assertLessEqual(max(par.levels), bl.MAX_DEPTH + 1)
        self.assertEqual("".join(r.text for r in bl.line_runs(par)).replace(" ", ""), "مرحباabc")


def host_order(host):
    """What a full UAX #9 engine (python-bidi, standing in for CoreText) draws from host text: controls dropped."""
    return "".join(c for c in get_display(host, base_dir=None) if c not in CONTROLS)


def drawn(line):
    return "".join(r.text[::-1] if r.rtl else r.text for r in line.runs)


class TestHostTextPerLine(unittest.TestCase):
    """Review 530e2e7 P1: a wrapped line handed to the host on its own lost the paragraph's W2/W7/N0/N1 context."""

    def test_a_wrapped_dose_range_keeps_its_order_on_the_host(self):
        text = "خد Vitamin D 1000 - 2000 وحدة يوميا"
        out = bl.lay_out(text, 16)
        self.assertEqual([ln.text for ln in out], ["خد", "Vitamin D", "1000 - 2000 وحدة", "يوميا"])
        self.assertEqual(drawn(out[2]), "ةدحو 1000 - 2000")
        for ln in out:
            with self.subTest(ln.text):
                self.assertEqual(host_order(bl.host_text(ln)), drawn(ln))
        self.assertEqual(host_order(bl.host_text(bl.paragraph(out[2].text, 1))), "ةدحو 2000 - 1000")   # the line alone: reversed

    def test_every_wrapped_line_matches_a_full_uax9_engine(self):
        words = ["عملت", "الـ", "MRI", "٥٠٠", "mg", "(", "insulin", ")", "«", "AI", "»", "010", "1234", "5678",
                 "-", "10", "%", "٪", "$", "50", "blood", "sugar", "الطِّبُّ", "لا\u200cمركزية", "a\u200db",
                 "x\u00a0y", "\u2066abc\u2069",
                 "،", "؟", "2–3", "+20", "iPhone", "15", "Vitamin", "D", "1000", "2000", "وحدة", "1.5", "CT", "-5",
                 "$99", "[", "]", "!", "\u202eعكس\u202c", "\u2067x 1\u2069", "\u202d٥٠٠ مجم\u202c", "٢٠٢٤", "١٫٥", "\t"]
        rnd, n = random.Random(54), 0
        for _ in range(500):
            text = " ".join(rnd.choice(words) for _ in range(rnd.randint(1, 14)))
            for w in (4, 9, 15, 24):
                for ln in bl.lay_out(text, w, balanced=w == 15):
                    n += 1
                    self.assertEqual(host_order(bl.host_text(ln)), drawn(ln), (text, w, ln.text))
        self.assertGreater(n, 4000)

    def test_a_number_list_the_paragraph_rejected_is_not_a_phone_on_the_host(self):
        text = "اتصل 010 1234 5678 123"                            # ambiguous: no HL3 for the paragraph
        self.assertEqual(bl.phone_spans(text), [])
        out = bl.lay_out(text, 13, measure=lambda s: len(s) + 2 * sum("\u0600" <= c <= "\u06ff" for c in s))
        self.assertEqual([ln.text for ln in out], ["اتصل", "010 1234 5678", "123"])
        self.assertEqual(drawn(out[1]), "5678 1234 010")
        self.assertEqual(host_order(bl.host_text(out[1])), "5678 1234 010")
        self.assertEqual(host_order(bl.host_text(bl.paragraph(out[1].text, 1))), "010 1234 5678")      # the line alone: a phone

    def test_line_paragraph_and_text_sources_agree(self):
        text = "قال الدكتور الـ MRI بيكشف 90% من الحالات"
        par = bl.paragraph(text)
        with self.assertRaises(TypeError):                         # review 29d31c5 P3-7: a bare string is refused
            bl.host_text(text)
        for ln in bl.lay_out(text, 12):
            self.assertEqual(bl.host_text(ln), bl.host_text(par, start=ln.start, end=ln.end))
        with self.assertRaises(ValueError):
            bl.host_text(par, base=0)
        with self.assertRaises(ValueError):
            bl.host_text(bl.lay_out(text)[0], base=0)
        with self.assertRaises(ValueError):
            bl.host_text(par, start=5, end=999)

    def test_tabs_and_trailing_space_reset_by_the_hosts_own_l1(self):
        for text in ("سكر\tsugar 50", "sugar\tسكر 50 ", "a b\tج د\te f"):
            par = bl.paragraph(text)
            with self.subTest(text):
                self.assertEqual(host_order(bl.host_text(par)), bl.visual(par, mirror=False))

    def test_marks_and_isolates_still_split_reversals_on_the_host(self):
        # review round 2: an undrawn mark or isolate control holds a level that splits an L2 reversal
        for text in ("الجرعة 500\u200f250 mg", "Speakers \u2068أحمد\u2069\u2068محمد\u2069 today",
                     "خد \u2066500\u2069\u2066mg\u2069 مرتين", "x<\u061c) \u200f", "٥٠٠\u061c٢٥٠ مجم"):
            par = bl.paragraph(text)
            with self.subTest(ascii(text)):
                self.assertEqual(host_order(bl.host_text(par)), bl.visual(par, mirror=False))
        self.assertEqual(bl.visual(bl.paragraph("الجرعة 500\u200f250 mg")), "mg 250500 ةعرجلا")

    def test_words_joined_without_spaces_with_marks_and_isolates(self):
        words = ["عملت", "MRI", "٥٠٠", "mg", "(", ")", "AI", "010", "1234", "-", "%", "$", "50", "أحمد", "x<", "<", ">",
                 "\u200f", "\u200e", "\u061c", "\u2066", "\u2067", "\u2068", "\u2069", "\t", "\u0301", "\u202bنص\u202c",
                 "a\u200db", "١٫٥", "!"]
        rnd, n = random.Random(2), 0
        for _ in range(500):
            text = "".join(rnd.choice(words) + rnd.choice((" ", "")) for _ in range(rnd.randint(1, 14)))
            for w in (5, 12, 30):
                for ln in bl.lay_out(text, w):
                    n += 1
                    self.assertEqual(host_order(bl.host_text(ln)), drawn(ln), (ascii(text), w))
        self.assertGreater(n, 1500)

    def test_one_line_per_call(self):
        with self.assertRaises(ValueError):
            bl.host_text(bl.paragraph("abc\nعربي 123 456"))
        with self.assertRaises(ValueError):
            bl.host_text(bl.Line("abc", 0, 3, False, []))                # not from lay_out: no paragraph
        two = bl.lay_out("abc\nعربي 123 456")
        self.assertEqual([host_order(bl.host_text(ln)) for ln in two], ["abc", "456 123 يبرع"])

    def test_nesting_is_renumbered_and_too_deep_a_line_is_refused(self):
        deep = "\u202b" * 62 + "سكر a" + "\u202c" * 62 + " سكر"          # levels 1, 125, 126: renumbered 3, 5, 6
        par = bl.paragraph(deep)
        self.assertEqual(sorted(set(par.levels)), [1, 125, 126])
        self.assertEqual(host_order(bl.host_text(par)), bl.visual(par, mirror=False))
        ladder = "س" + "\u202bس" * 62                                     # every odd level 1 … 125 holds a letter
        with self.assertRaises(ValueError):
            bl.host_text(bl.paragraph(ladder))


class TestReviewRound1(unittest.TestCase):
    """Review 530e2e7 P2/P3: phones, units, hostile controls, hard breaks and the test gaps the mutation run found."""

    def test_number_lists_are_not_phones(self):
        for t in ("خد 0 250 500 mg", "الجرعة 0-250-500 mg", "قيم 05 100 200 300", "زاد +100 200 300 نقطة",
                  "٠ ١٠٠ ٢٠٠٠", "الجرعة 05 250 500 مجم", "خد ٠٥ ٢٥٠ ٥٠٠ مجم", "قيم 05 125 250",
                  "زاد +150 250 350 نقطة", "+120 140 160", "الضغط 090 120 140 مم", "قلل 05 500 250 125",
                  "قيم 05 100 100 100", "قيم 05 100 100 200"):
            with self.subTest(t):
                self.assertEqual(bl.phone_spans(t), [])
                self.assertEqual(bl.visual(bl.paragraph(t)),
                                 bl.visual(bl.paragraph(t, base=bl.direction(t), hl1=False)))   # plain UAX #9
        self.assertEqual(bl.visual(bl.paragraph("خد 0 250 500 mg")), "mg 500 250 0 دخ")
        self.assertEqual(bl.phone_spans("خد 0 251 503 mg"), [])               # a one-digit zero head is a list
        for t in ("+1 202 555 0100", "050 123 4567", "02 2345 6780", "010 1234 5678", "+20 100 123 4567",
                  "٠١٠ ١٢٣٤ ٥٦٧٨", "02 2345 6789", "010 1230 5670", "050 1234500", "02 2400 1100",
                  "+1 800 300 2000", "012 0000 0000", "+20 10 12 345", "+966 50 123 4567", "07911 123 456",
                  "0555 123 456", "0501 234 567", "٠٥٥٥ ١٢٣ ٤٥٦", "+966 512 600 789", "+962 791 534 267",
                  "+971 501 502 503", "+34 612 700 800", "050 123 456", "0555 120 140"):
            with self.subTest(t):
                self.assertEqual(bl.phone_spans("اتصل " + t), [(5, 5 + len(t))])

    def test_a_phone_written_with_no_break_spaces_reads_as_dialled(self):
        for sp in ("\u00a0", "\u202f", "\u2007"):
            t = "كلمنا 010" + sp + "1234" + sp + "5678"
            with self.subTest(hex(ord(sp))):
                self.assertEqual(bl.phone_spans(t), [(6, len(t))])
                self.assertEqual(bl.visual(bl.paragraph(t)), "010" + sp + "1234" + sp + "5678 انملك")
                t = "اتصل 3" + sp + "010" + sp + "1234" + sp + "5678"           # a number joined in front is not part
                self.assertEqual(bl.phone_spans(t), [(7, len(t))])

    def test_phone_spans_is_linear(self):
        assert_linear(self, lambda n: bl.phone_spans(" ".join(["0123"] * n)), 7500, 30000,
                      "0123 list")                              # was 39.8 s (a slice per candidate)
        assert_linear(self, lambda n: bl.breaks(" ".join(["010 1234 5678"] * n)), 750, 3000, "phones")

    def test_more_units_stay_with_their_number(self):
        self.assertEqual(lines("خد ٢ ملعقة بعد الأكل", 4), ["خد", "٢ ملعقة", "بعد", "الأكل"])
        for u in ("ملعقة", "ملاعق", "مللي", "ملي", "جرامات", "كبسولة", "كبسولات", "حقنة", "دقيقه", "وحده", "مره",
                  "مرّات", "مَجم", "ng/ml", "°C", "°F", "tablets", "mEq", "IU/kg", "mg/ml", "drops", "مجم/كجم", "سم٣",
                  "أمبول", "أمبولات", "لزقة", "غ", "tsp", "tbsp", "cm³"):
            with self.subTest(u):
                self.assertEqual(bl.word_breaks(["5", u, "كمان"]), ["never", "ok"])
        for w in ("ناس", "كلمة", "سكر", "مريض", "بعد"):                 # an ordinary word after a number: a break
            with self.subTest(w):
                self.assertEqual(bl.word_breaks(["٣", w]), ["ok"])

    def test_hostile_bidi_controls_are_findings(self):
        f = bl.control_findings("خد \u202e500 mg\u202c مرتين")
        self.assertEqual([(x["index"], x["name"]) for x in f],
                         [(3, "RIGHT-TO-LEFT OVERRIDE"), (10, "POP DIRECTIONAL FORMATTING")])
        self.assertIn("reverses", f[0]["why"])
        self.assertNotIn("reverses", f[1]["why"])
        self.assertEqual([x["index"] for x in bl.control_findings("\u200fسكر \u2066a\u2069 \u202ab\u202c \u061c")],
                         [5, 7, 9, 11])
        self.assertEqual(bl.control_findings("خد ٥٠٠ mg مرتين"), [])
        self.assertEqual(bl.visual(bl.paragraph("خد \u202e500 mg\u202c مرتين")), "نيترم gm 005 دخ")   # still honoured

    def test_every_hard_break(self):
        for sep in ("\n", "\r", "\r\n", "\x0b", "\x0c", "\x1c", "\x1d", "\x1e", "\x85", "\u2028", "\u2029"):
            with self.subTest(hex(ord(sep[-1]))):
                self.assertEqual(lines("سطر" + sep + "تاني", None), ["سطر", "تاني"])
                self.assertEqual(lines("سطر" + sep + "تاني", 20), ["سطر", "تاني"])

    def test_lay_out_refuses_a_zero_or_negative_width_like_wrap(self):
        for w in (0, -3):
            with self.assertRaises(ValueError):
                bl.lay_out("سطر طويل", w)
        self.assertEqual(lines("سطر طويل", None), ["سطر طويل"])

    def test_bracket_pairs_nested_four_deep_resolve(self):
        self.assertEqual(runs("a ((((b)))) سكر"), [[1, " سكر"], [2, "a ((((b))))"]])

    def test_canonically_equivalent_brackets_pair(self):
        self.assertEqual(runs("a \u2329b\u3009 سكر"), [[1, " سكر"], [2, "a \u2329b\u3009"]])
        self.assertEqual(runs("a \u3008b\u232a سكر"), [[1, " سكر"], [2, "a \u3008b\u232a"]])

    def test_a_combining_mark_after_a_paired_bracket_takes_its_direction(self):
        self.assertEqual(runs("a(b)\u0301 سكر"), [[1, " سكر"], [2, "a(b)\u0301"]])

    def test_a_leading_removed_character_takes_the_first_level(self):
        self.assertEqual(runs("\u200dabc سكر"), [[1, " سكر"], [2, "\u200dabc"]])

    def test_the_bare_article_and_padded_words(self):
        self.assertEqual(bl.word_breaks(["عملت", "ال", "MRI"]), ["ok", "never"])
        self.assertEqual(bl.word_breaks(["50 ", " mg"]), ["never"])
        self.assertEqual(bl.word_breaks([" الـ", "MRI "]), ["never"])

    def test_set_digits_is_linear_on_a_huge_token(self):
        self.assertEqual(bl.set_digits("1" * 40000, "arabic"), "١" * 40000)
        assert_linear(self, lambda n: bl.set_digits("1" * n, "arabic"), 10000, 40000, "digits")   # was 13 s
        assert_linear(self, lambda n: bl.set_digits("1." * n, "arabic"), 5000, 20000, "versions")

    def test_set_digits_leaves_a_url_or_handle_without_latin_letters(self):
        self.assertEqual(bl.set_digits("تابعنا @2024 و 50", "arabic"), "تابعنا @2024 و ٥٠")

    def test_balanced_tie_breaks_avoid_and_overflow_lines(self):
        def bal(t, w):
            return [t[a:b] for a, b in bl.wrap(t, w, balanced=True)]
        self.assertEqual(bal("دم MRI MRI ضغط", 9), ["دم", "MRI MRI", "ضغط"])       # fewer "avoid" breaks
        self.assertEqual(bal("sugar MRI دم", 8), ["sugar", "MRI دم"])              # fewer overflowing lines

    def test_balanced_is_never_worse_than_greedy(self):
        words = ["كلمة", "سكر", "ضغط", "insulin", "resistance", "blood", "sugar", "الـ", "MRI", "٥٠٠", "mg", "عالية",
                 "(", ")", "010", "1234", "5678", "iPhone", "15", "Pro"]
        rnd = random.Random(530)
        for _ in range(1500):
            t = " ".join(rnd.choice(words) for _ in range(rnd.randint(2, 18)))
            w = rnd.randint(3, 30)
            g, b = bl.wrap(t, w), bl.wrap(t, w, balanced=True)
            avoid = {s for s, _, k in bl.breaks(t) if k == "avoid"}
            og, ob = sum(e - s > w for s, e in g), sum(e - s > w for s, e in b)
            ag, ab = sum(e in avoid for _, e in g[:-1]), sum(e in avoid for _, e in b[:-1])
            self.assertEqual(len(b), len(g), (t, w))
            self.assertTrue(ob < og or (ob == og and ab <= ag), (t, w, g, b))

    def test_greedy_wrap_is_linear_and_the_balance_cap_is_named(self):
        rnd = random.Random(1)
        text = " ".join(rnd.choice(["كلمة", "test", "500", "mg", "الـ", "MRI"]) for _ in range(5000))
        words = text.split(" ")
        assert_linear(self, lambda n: bl.wrap(" ".join(words[:n]), 30), 1250, 5000, "wrap")   # was 1.5 s
        assert_linear(self, lambda n: bl.lay_out(" ".join(words[:n]), 30), 1250, 5000, "lay_out")
        self.assertEqual(bl.BALANCE_MAX_BREAKS, 120)
        big = " ".join(["كلمة"] * (bl.BALANCE_MAX_BREAKS + 2))
        self.assertEqual(bl.wrap(big, 12, balanced=True), bl.wrap(big, 12))


def ladder(n):
    """A right-to-left paragraph with a letter at every odd level 1 … 2n + 1."""
    return bl.paragraph("س" + "\u202bس" * n)


class TestReviewRound2(unittest.TestCase):
    """Review 29d31c5 P3: values before a unit, «00» phones, boundary constants, compound and dual units, marks next
    to digits, host_text(str), a NaN width."""

    def test_a_number_chain_before_a_value_unit_is_never_a_phone(self):
        for t in ("الجرعات 05 250 500 1000 مجم", "خد 02 500 1000 mg", "نسب 05 120 135 %", "الجرعات 05 250 500 1000 مجم.",
                  "قيس 080 120 135 150 mg/dl", "خد ٠٢ ٥٠٠ ١٠٠٠ مجم", "السعر 0100 1234 5678 جنيه"):
            with self.subTest(t):
                self.assertEqual(bl.phone_spans(t), [])
                self.assertEqual(bl.visual(bl.paragraph(t)),
                                 bl.visual(bl.paragraph(t, base=bl.direction(t), hl1=False)))   # plain UAX #9
        for t, tail in (("اتصل 010 1234 5678", " مرة تانية"), ("كلمنا 010 1234 5678", " يوم الجمعة"),
                        ("اتصل 010 1234 5678", " 24 ساعة"), ("اتصل 010 1234 5678", " بعد ساعة"),
                        ("call 010 1234 5678", " 2 times"), ("اتصل 010 1234 5678", "\u00a0مرتين")):
            with self.subTest(t + tail):                       # time and count words follow a phone: still a phone
                self.assertEqual(bl.phone_spans(t + tail), [(len(t) - 13, len(t))])

    def test_no_part_of_a_chain_before_a_value_unit_is_a_phone(self):
        # self-review r1 P2-1: a dropped «year» or short tail must not leave a "phone" in front of the unit
        for t in ("خد 02 500 1000 2000 وحدة", "الجرعات 05 250 500 1000 2000 مجم", "نسب 05 120 135 15 %",
                  "الجرعات 05 250 500 1000 – 2000 مجم", "الجرعات 05 250 500 1000 - 2000 mg", "قيس +5 2500 3000 mg",
                  "خد 05 250 500 مرة/يوم", "خد 02 500 1000 ملليجرام", "خد 02 500 1000 ميللي", "خصم 05 120 135 بالمائة",
                  "السعر 02 500 1000 LE", "السعر 02 500 1000 L.E", "خد 02 500 1000\u2009mg", "خد 02 500 1000\tمجم",
                  "خد 02 500 1000\u00a0مجم", "خد 02 500 1000 مجم،"):
            with self.subTest(ascii(t)):
                self.assertEqual(bl.phone_spans(t), [])
                self.assertEqual(bl.visual(bl.paragraph(t)),
                                 bl.visual(bl.paragraph(t, base=bl.direction(t), hl1=False)))   # plain UAX #9
        self.assertEqual(bl.phone_spans("قيس +5 2500 3000"), [(4, 16)])          # no unit: dialled
        for t, tail in (("اتصل 010 1234 5678", " سعر الكشف 300 جنيه"), ("اتصل 010 1234 5678", " كيلو 21 الساحل"),
                        ("اتصل 010 1234 5678", " ألف مبروك"), ("اتصل 010 1234 5678", " كم مرة"),
                        ("call 010 1234 5678", " days only"),
                        ("اتصل 010 1234 5678", "\nمجم"), ("اتصل +20 100 123 4567", " في ظرف ساعة")):
            with self.subTest(ascii(t + tail)):                # everyday words, and a unit on the next line
                self.assertEqual(bl.phone_spans(t + tail)[:1], [(len(t) - len(t.split(" ", 1)[1]), len(t))])

    def test_a_phone_with_the_00_international_prefix(self):
        for t in ("00966 50 123 4567", "0020 100 123 4567", "٠٠٩٦٦ ٥٠ ١٢٣ ٤٥٦٧", "00966-50-123-4567", "001 202 555 0100",
                  "0020 1001234567", "00201 001234567890", "00966 5 123"):
            with self.subTest(t):
                self.assertEqual(bl.phone_spans("اتصل " + t), [(5, 5 + len(t))])
        for t in ("00966 50", "00 15", "005 250 500", "002011 001234567890", "00201001234567", "0096 5 123",
                  "00 966 50 123 4567", "00966-5012-34"):
            with self.subTest(t):                              # < 7 digits, no country code, a list, > 15, one group, 6, a lone «00», a short last group
                self.assertEqual(bl.phone_spans("اتصل " + t), [])
        self.assertEqual(bl.visual(bl.paragraph("اتصل 00966 50 123 4567")), "00966 50 123 4567 لصتا")

    def test_phone_digit_bounds(self):
        yes = ("05 25001", "+20 12345", "0100 1234 5678", "+201 100 123 456789")    # 7, 7, 12, 15 digits
        no = ("05 2500", "+20 1234", "01000 1234 5678", "+2011 100 123 456789")    # 6, 6, 13, 16 digits
        for t in yes:
            with self.subTest(t):
                self.assertEqual(bl.phone_spans("رقمنا " + t), [(6, 6 + len(t))])
        for t in no:
            with self.subTest(t):
                self.assertEqual(bl.phone_spans("رقمنا " + t), [])

    def test_value_list_bounds(self):
        self.assertEqual(bl.phone_spans("اتصل 010 500 250 750"), [(5, 20)])      # turns: not a list
        self.assertEqual(bl.phone_spans("رقمنا 0100 100 200"), [(6, 18)])        # head not below every value
        self.assertEqual(bl.phone_spans("رقمنا 0100 101 200"), [(6, 18)])        # not round
        self.assertEqual(bl.phone_spans("رقمنا 099 100 200"), [])                # head below every value

    def test_the_next_phone_after_a_phone_is_7_to_12_digits(self):
        t = "رقمنا 010 1234 5678 012 3456"                                       # 7 digits: the next phone
        self.assertEqual(bl.phone_spans(t), [(6, 19), (20, 28)])
        t = "رقمنا 010 1234 5678 0100 1234 5678"                                 # 12 digits
        self.assertEqual(bl.phone_spans(t), [(6, 19), (20, 34)])
        self.assertEqual(bl.phone_spans("رقمنا 010 1234 5678 0123 4567 89012"), [])   # 13: not a phone's tail

    def test_unit_spelling_folds(self):
        for u in ("مللى", "مل\u0670ي", "مُلِّي", "إقراص", "ملعقه"):                          # ى, dagger alef, harakat, alef, ة
            with self.subTest(ascii(u)):
                self.assertEqual(bl.word_breaks(["خد", "2", u]), ["ok", "never"])

    def test_compound_and_dual_units_stay_with_their_number(self):
        for u in ("مجم/مل", "مل/ساعة", "ml/kg/h", "mg/kg/day", "وحدة/كجم/ساعة", "ملعقتين", "قرصين", "حبتين",
                  "مرتين", "كبسولتين", "جرعتين", "ساعتين", "يومين", "ملعقتان"):
            with self.subTest(u):
                self.assertEqual(bl.word_breaks(["خد", "20", u]), ["ok", "never"])
        for w in ("24/7", "كمان", "سمين", "a/b", "ناس/ناس", "/مل", "مل/", "اثنين", "بين", "مليان", "ألفين", "سعرين"):
            with self.subTest(w):
                self.assertEqual(bl.word_breaks(["خد", "20", w]), ["ok", "ok"])

    def test_a_directional_mark_next_to_a_digit_is_a_finding(self):
        def marks(t):
            return [(x["index"], x["char"]) for x in bl.control_findings(t) if x["char"] in "\u200e\u200f\u061c"]
        self.assertEqual(marks("خد \u200e1000 - 2000\u200e وحدة"), [(3, "\u200e"), (15, "\u200e")])
        self.assertEqual(marks("خد 250\u200e 500 وحدة"), [(6, "\u200e")])
        self.assertEqual(marks("٥٠٠\u061c مجم"), [(3, "\u061c")])
        self.assertEqual(marks("Dose 250\u200f 500 mg"), [(8, "\u200f")])          # reorders a Latin line too
        self.assertEqual(marks("خد 250\u200e\u200f\u2066 500"), [(6, "\u200e"), (7, "\u200f")])   # through controls
        self.assertEqual(marks("خد 250\u200e\u200f سكر"), [(6, "\u200e"), (7, "\u200f")])        # through a mark
        # self-review r1 P2-2: spaces, brackets, signs and joiners between the mark and the digit do not cut its effect
        for t, at in (("خد \u200e 1000 - 2000 وحدة", 3), ("خد\u200e 1000 - 2000 وحدة", 2), ("خد \u200e(1000 - 2000) وحدة", 3),
                      ("Dose \u200f 1000 - 2000 mg", 5), ("خد 250\u200d\u200e 500", 7), ("خد 50%\u200e سكر", 6),
                      ("الساعة 5\u200f.", 8)):                                  # the last one is harmless: still checked
            with self.subTest(ascii(t)):
                self.assertEqual(marks(t), [(at, t[at])])
        for t in ("مرحبا\u200f.", "\u200fسكر 500", "سكر \u200e(a) 5", "a\u200e b 5", "5 سكر \u200f. علم", "5\nسكر\u200f"):
            with self.subTest(ascii(t)):
                self.assertEqual(marks(t), [])
        f = bl.control_findings("خد 250\u200e 500")
        self.assertIn("number", f[0]["why"])
        self.assertEqual(bl.visual(bl.paragraph("خد 250\u200e 500 وحدة")), "ةدحو 250 500 دخ")   # honoured: read 500, 250
        self.assertEqual([x["index"] for x in bl.control_findings("\u200fسكر \u2066a\u2069 \u202ab\u202c \u061c")],
                         [5, 7, 9, 11])

    def test_review_round_3_minors(self):
        # ranges and alternatives before the unit, a mark or joiner before the unit, abbreviations
        for t in ("الجرعات 05 250 500 1000 – 2000 – 3000 مجم", "خد 02 500 1000 أو 2000 مجم", "خد 02 500 1000 2000 إلى 3000 مجم",
                  "خد 02 500 1000 2000 — 3000 mg", "خد 02 500 1000 2000 − 3000 mg", "take 02 500 1000 2000 or 3000 mg",
                  "خد 02 500 1000 2000 \u200eمجم", "خد 02 500 1000 2000\u200f مجم", "خد 02 500 1000 2000\u200d مجم", "خد 02 500 1000 2000 مجم\u200f",
                  "خد 02 500 1000 مج", "خد 02 500 1000 م.ج"):
            with self.subTest(ascii(t)):
                self.assertEqual(bl.phone_spans(t), [])
        for t, tail in (("Call 010 1234 5678", " Le Caire"), ("Call 010 1234 5678", " m"),
                        ("اتصل 010 1234 5678", " مليون مبروك"),
                        ("اتصل 010 1234 5678", "\u2028مجم")):
            with self.subTest(ascii(t + tail)):
                self.assertEqual(bl.phone_spans(t + tail), [(5, len(t))])
        self.assertEqual(bl.word_breaks(["خد", "20", "يومان"]), ["ok", "never"])          # the «…ان» dual
        f = [x["index"] for x in bl.control_findings("خد \u200e\n1000") if x["char"] == "\u200e"]
        self.assertEqual(f, [])                                       # a paragraph separator stops the look
        # self-review r3: each «05» is a chain; was quadratic (10.5 s at 8,000 repeats). Growth ratios, not a
        # wall-clock bound: the 3 s bound failed at 3.76 s under full-suite load (4babf5e suite)
        for label, fn, n in (("spaces", lambda k: bl.phone_spans("05 250" + " " * k + "x"), 25000),
                             ("dash values", lambda k: bl.phone_spans(("05 250 - " * k) + "مجم"), 5000),
                             ("dash heads", lambda k: bl.phone_spans("05 " + "- 05 " * k), 5000),
                             ("or heads", lambda k: bl.phone_spans("05 " + "أو 5 " * k), 5000),
                             ("lay out", lambda k: bl.lay_out("خد " + "1 - " * k + "مجم", 20), 2500)):
            with self.subTest(label):
                assert_linear(self, fn, n, 4 * n, label)

    def test_control_findings_are_linear(self):
        assert_linear(self, lambda n: bl.control_findings("5" + "\u200e" * n + "5"), 50000, 200000, "marks")

    def test_host_text_refuses_a_bare_string(self):
        for src in ("abc", "خد 1000 - 2000 وحدة", ""):
            with self.subTest(src), self.assertRaises(TypeError) as cm:
                bl.host_text(src)
            self.assertIn("lay_out", str(cm.exception))
        with self.assertRaises(TypeError):
            bl.host_text(None)

    def test_the_host_depth_limit_is_exactly_125(self):
        ok = ladder(61)                                       # levels 1 … 123: renumbered 3 … 125
        self.assertEqual(max(ok.levels), 123)
        self.assertEqual(host_order(bl.host_text(ok)), bl.visual(ok, mirror=False))
        with self.assertRaises(ValueError) as cm:
            bl.host_text(ladder(62))                          # … 127
        self.assertIn("125", str(cm.exception))

    def test_a_width_that_is_not_a_positive_finite_number_is_refused(self):
        for w in (float("nan"), float("inf"), -float("inf"), Decimal("NaN"), Decimal("sNaN"), Decimal("Infinity"),
                  True, "5", b"5", 3j):
            with self.subTest(repr(w)):
                with self.assertRaises(ValueError):
                    bl.lay_out("سطر طويل", w)
                with self.assertRaises(ValueError):
                    bl.wrap("سطر طويل", w)
        with self.assertRaises(ValueError):
            bl.wrap("سطر طويل", None)
        for w in (Decimal("4"), Fraction(9, 2), 4.5):                 # any positive finite number
            self.assertEqual(lines("سطر طويل", w), ["سطر", "طويل"])


def best_time(fn, arg, tries=3):
    out = []
    for _ in range(tries):
        t0 = time.perf_counter()
        fn(arg)
        out.append(time.perf_counter() - t0)
    return min(out)


def assert_linear(test, fn, small, big, label):
    """`fn(big)` on 4× the input of `fn(small)` takes < 10× as long: linear grows 4×, quadratic 16×. A ratio, not a
    wall-clock bound, so a loaded machine does not fail it (the 3 s bound failed at 3.76 s in the 4babf5e suite)."""
    t1, t4 = best_time(fn, small), best_time(fn, big)
    test.assertLess(t4, 10 * max(t1, 0.01), (label, t1, t4))


def ph(t):
    return [t[a:b] for a, b in bl.phone_spans(t)]


def plain(t):
    return bl.visual(bl.paragraph(t, base=bl.direction(t), hl1=False))


class TestExecutorRuling(unittest.TestCase):
    """Executor ruling 2026-10-18 (review ad85d58 FAIL r3): a digit chain is a phone ONLY with a positive cue (Egyptian
    01[0125] + 8 digits, «+», «00», or a cue word right before it); a number before a dose unit is never drawn
    reversed; review P3-3 … P3-6."""
    MOBILE = "اتصل 010 1234 5678"

    def test_without_a_cue_a_leading_zero_chain_is_a_list(self):
        for t in ("02 2345 6789", "050 123 4567", "0555 123 456", "05 250 500", "قيس السكر 080 120 135 150",
                  "07911 123 456", "النتيجة 02 2400 1100", "٠٢ ٢٣٤٥ ٦٧٨٩", "0100 1234 5678"):
            with self.subTest(t):
                self.assertEqual(bl.phone_spans(t), [])
                self.assertEqual(bl.visual(bl.paragraph(t)), plain(t))       # plain UAX #9: read right to left

    def test_the_egyptian_mobile_shape_is_a_cue_alone(self):
        for t in ("010 1234 5678", "0100 123 4567", "011 2345 6789", "012 3456 7890", "015 5555 0000", "0101 234 5678",
                  "٠١٠ ١٢٣٤ ٥٦٧٨", "۰۱۰ ۱۲۳۴ ۵۶۷۸", "010 1234 5678", "010-1234-5678", "015 555 50000"):
            with self.subTest(ascii(t)):
                self.assertEqual(ph("الجديد " + t), [t])
        for t in ("013 1234 5678", "014 1234 5678", "016 1234 5678", "01 250 500 750", "010 1234 567",
                  "010 1234 56789", "01 0123 45678", "020 1234 5678"):
            with self.subTest(t):                                       # not 01[0125], first group < 3, 10 / 12 digits
                self.assertEqual(ph("الجديد " + t), [])

    def test_plus_and_00_are_cues(self):
        for t in ("+966 5 1234 5678", "+20 2 2345 6789", "00966 50 123 4567", "0020 2 2345 6789", "۰۰۹۶۶ ۵۰ ۱۲۳ ۴۵۶۷"):
            with self.subTest(ascii(t)):
                self.assertEqual(ph("الجديد " + t), [t])

    def test_every_cue_word_makes_a_landline_a_phone(self):
        for cue in ("رقم", "رقمي", "رقمنا", "الرقم", "برقم", "ورقم", "عالرقم", "للرقم", "رقمه", "تليفون", "التليفون",
                    "تليفوني", "تلفون", "التلفون", "موبايل", "الموبايل", "موبايلي", "واتساب", "الواتساب", "واتس", "الواتس",
                    "هاتف", "الهاتف", "جوال", "الجوال", "جوالي", "اتصل", "اتصلوا", "اتصلي", "واتصل", "تتصل", "هتتصل",
                    "يتصل", "اتصال", "للاتصال", "كلمنا", "كلمونا", "كلمني", "كلموني", "وكلمنا", "call", "Call", "CALL",
                    "phone", "Phone:", "phone:", "WhatsApp", "whatsapp", "tel", "Tel.", "Tel:", "mobile", "hotline",
                    "رقمي:", "الرقم:", "رقمنا،", "رقمٌ", "الرقـم", "Phone-"):
            t = cue + " 02 2345 6789"
            with self.subTest(cue):
                self.assertEqual(ph(t), ["02 2345 6789"])
        self.assertEqual(ph("رقمي:02 2345 6789"), ["02 2345 6789"])               # glued after a colon
        self.assertEqual(ph("رقمي: 02 2345 6789."), ["02 2345 6789"])

    def test_fillers_between_the_cue_and_the_number(self):
        for t in ("اتصلوا بينا على 02 2345 6789", "كلمنا على الرقم ده 02 2345 6789", "رقم الواتساب بتاعنا 02 2345 6789",
                  "call us at 02 2345 6789", "Call us on: 02 2345 6789", "رقم التليفون هو 02 2345 6789",
                  "ابعتلنا واتساب على 02 2345 6789", "رقمنا الجديد 02 2345 6789", "call our number 02 2345 6789",
                  "كلمني ع 02 2345 6789", "اتصل الآن 02 2345 6789", "اتصل حالا على 02 2345 6789",
                  "اتصل على على على على 02 2345 6789", "اتصل - 02 2345 6789", "Phone : 02 2345 6789"):   # 4 back
            with self.subTest(t):
                self.assertEqual(ph(t), ["02 2345 6789"])

    def test_a_word_that_is_not_a_filler_cuts_the_cue(self):
        for t in ("رقم السكر 080 120 135 150", "اتصل بالدكتور لو السكر 080 120 135 150", "call the doctor if 080 120 135 150",
                  "رقم الضغط النهارده 080 120 135 150", "اتصل بينا على طول يا جماعة 02 2345 6789",
                  "اتصل بالدكتور لو 080 120 135 150", "رقم الجرعة 080 120 135 150"):
            with self.subTest(t):
                self.assertEqual(bl.phone_spans(t), [])
                self.assertEqual(bl.visual(bl.paragraph(t)), plain(t))

    def test_a_cue_after_the_number_on_another_line_or_sentence_is_not_a_cue(self):
        for t in ("قيس 080 120 135 150 واتصل", "02 2345 6789 رقمنا", "اتصل\n02 2345 6789", "اتصل. 02 2345 6789",
                  "اتصل؟ 02 2345 6789", "اتصل! 02 2345 6789", "call; 02 2345 6789", "اتصل\u2029 02 2345 6789",
                  "اتصل بينا على على على على 02 2345 6789",               # > 4 words back
                  "اتصل . 02 2345 6789", "اتصل ؟ 02 2345 6789", "call ... 02 2345 6789"):
            with self.subTest(ascii(t)):
                self.assertEqual(bl.phone_spans(t), [])

    def test_words_that_look_like_cues_but_are_not(self):
        for t in ("الأرقام 080 120 135 150", "ارقام 080 120 135 150", "كلمة 02 2345 6789", "كلمه 02 2345 6789",
                  "الكلمات 02 2345 6789", "الرقمية 02 2345 6789", "telescope 02 2345 6789", "phones? 02 2345 6789",
                  "recall 02 2345 6789", "متصل 02 2345 6789", "الاتصالات 02 2345 6789"):
            with self.subTest(t):
                self.assertEqual(bl.phone_spans(t), [])

    def test_a_cued_value_list_stays_a_list(self):
        for t in ("رقمنا 05 250 500", "رقمنا 099 100 200", "اتصل 05 100 200 300"):
            with self.subTest(t):
                self.assertEqual(bl.phone_spans(t), [])

    DOSE_UNITS = (
        "mg", "MG", "mcg", "µg", "ml", "mL", "IU", "iu", "mmol", "mg/dl", "mg/dL", "mmol/L", "mIU/L", "mIU/ml", "mgs",
        "mIU", "gm", "gms", "gram", "grams", "milligram", "milligrams", "microgram", "micrograms", "units", "cc", "drops",
        "tablets", "mmHg", "bpm", "°C", "ng/ml",
        "مجم", "مج", "م.ج", "ملجم", "ملغ", "مغ", "ملغم", "مكجم", "ميكروغرام", "ميكروجرام", "نانوجرام", "نانوغرام",
        "ملغرام", "ميلليجرام", "ملجرام", "مليجرامات", "ملليجرامات", "مليجرام", "ملليجرام", "ميليجرام", "مليغرام",
        "جم", "غم", "غرام", "جرام", "جرامات", "دل", "ديسيلتر", "مل", "ملل", "مللي", "ملي", "ميلي", "لتر", "مليمول",
        "ملم", "مم", "وحدة", "وحدات", "وحده", "و.د", "نبضة", "نبضات", "قرص", "أقراص", "قرصين", "كبسولة", "حقنة",
        "ملعقة", "بخة", "جرعة", "أمبول", "لزقة", "فيال", "سيسي", "سم٣",
        "مـجـم", "بالمجم", "بالملي", "والمجم", "مجم/دل", "ملجم/دل", "مليمول/لتر", "مجم/ديسيلتر", "ملغ/دل", "مغ/دل",
        "جم/دل", "و.د/مل", "مرة/يوم", "مجم،", "مجم.", "(مجم)", "مَجم",
        "مليلتر", "ملليلتر", "مكغ", "مكغم", "مغم", "ملج", "ملغرامات", "ميكروجرامات", "ملمول", "مليمول/ل", "µmol", "umol",
        "U", "U/L", "قطرة", "قطرات", "بخاخ", "لبوس", "تحاميل", "مجم/", "حبة", "حبات", "ظرف", "كيس", "درجة", "درجات",
        "نقطة", "نقط", "درجتين", "حبتين", "℃", "tablet", "unit", "g", "mg/kg", "حقن", "كبسولات", "مجم/كجم",
        "ميكروجم", "مكروجرام", "ملليليتر", "ضربة", "ممول/ل", "ميكرو", "ميكروغ", "سم³", "سم3", "I.U.",
        "i.u", "c.c", "m.g", "مول/ل", "مجم-", "cm3", "ميليغرام", "يونت", "يونيت", "يونتات", "شرطة", "شرط", "سنتي",
        "ابرة", "إبرة", "ابر", "رشة", "رشات", "°م", "مئوية", "مجم/كغ", "ملغم/كغ", "مجم/دسل", "pills", "مجمات", "نانو")

    def test_every_dose_unit_after_a_cued_phone_shape_is_absolute(self):
        self.assertEqual(ph(self.MOBILE + " كمان"), ["010 1234 5678"])           # the base is a phone
        for u in self.DOSE_UNITS:
            for t in (self.MOBILE + " " + u, "رقمنا 02 2345 6789 " + u, "+20 2 2345 6789 " + u):
                with self.subTest(t):
                    self.assertEqual(bl.phone_spans(t), [])
                    self.assertEqual(bl.visual(bl.paragraph(t)), plain(t))

    def test_the_reviews_dose_lists(self):
        for t in ("قيس السكر 080 120 135 150 مجم/دل", "خد 05 120 135 ثم 150 مجم", "قيس السكر 080 120 135 150 ملغم",
                  "خد 05 120 135 و 150 مجم", "خد 05 120 135 لـ 150 مجم", "خد 05 120 135 حتى 150 مجم"):
            with self.subTest(t):
                self.assertEqual(bl.phone_spans(t), [])
                self.assertEqual(bl.visual(bl.paragraph(t)), plain(t))

    def test_dose_connectors_reach_the_unit(self):
        for c in (" و 150", " و150", " ثم 150", " لـ 150", " ل 150", " لحد 150", " حتى 150", " till 150", " then 150",
                  " and 150", " ، 150", "، 150", ", 150", " / 150", " الى 150", " او 150", " to 150", " إلى 150",
                  " أو 150", " or 150", " - 150", " – 150", " وبعدين 150"):
            t = self.MOBILE + c + " مجم"
            with self.subTest(t):
                self.assertEqual(bl.phone_spans(t), [])
        for c in (" toe 150", " xto 150", " الىx 150", " ثمن 150", " وكمان 150"):          # not connectors: a word
            t = self.MOBILE + c + " مجم"
            with self.subTest(t):
                self.assertEqual(ph(t), ["010 1234 5678"])

    def test_the_look_past_values_stops_after_15(self):
        self.assertEqual(bl.phone_spans(self.MOBILE + " - 5" * 15 + " مجم"), [])
        self.assertEqual(ph(self.MOBILE + " - 5" * 16 + " مجم"), ["010 1234 5678"])
        self.assertEqual(bl.phone_spans(self.MOBILE + " ثم 5" * 15 + " مجم"), [])
        self.assertEqual(ph(self.MOBILE + " ثم 5" * 16 + " مجم"), ["010 1234 5678"])

    def test_a_money_size_or_percent_word_does_not_undo_a_cued_phone(self):
        # review ad85d58 P3-3: «اتصل 010 1234 5678 جنيه بس» was drawn reversed
        for tail in (" جنيه بس", " جنيه", " دولار", " ريال", " درهم", " دينار", " يورو", " % من الناس", " ٪", " سم", " كم",
                     " بالمية", " بالمائة", " percent", " pct", " ‰", " EGP", " LE", " $", " مليون", " مليار", " ألف",
                     " km", " cm", " GB", " k", " سعر", " كيلو"):
            for head, phone in ((self.MOBILE, "010 1234 5678"), ("رقمنا 02 2345 6789", "02 2345 6789")):
                t = head + tail
                with self.subTest(t):
                    self.assertEqual(ph(t)[:1], [phone])

    def test_a_second_phone_joined_by_or_keeps_the_cue(self):
        for t in ("رقمنا 02 2345 6789 أو 02 3456 7890", "اتصل 02 2345 6789 و 02 3456 7890",
                  "call 02 2345 6789 or 02 3456 7890", "اتصل 02 2345 6789 - 02 3456 7890", "رقمنا 02 2345 6789، 02 3456 7890"):
            with self.subTest(t):
                self.assertEqual(ph(t), ["02 2345 6789", "02 3456 7890"])
        self.assertEqual(ph("رقمنا 02 2345 6789 والسكر 02 3456 7890"), ["02 2345 6789"])
        self.assertEqual(ph("رقمنا 02 2345 6789. 02 3456 7890"), ["02 2345 6789"])
        self.assertEqual(ph("رقمنا 02 2345 6789\nأو 02 3456 7890"), ["02 2345 6789"])          # another line
        self.assertEqual(ph("رقمنا 02 2345 6789 و أو و 02 3456 7890"), ["02 2345 6789"])       # 3 joiners
        self.assertEqual(ph("رقمنا 02 2345 6789 أو  و 02 3456 7890"), ["02 2345 6789", "02 3456 7890"])
        self.assertEqual(ph("رقمنا 02 2345 6789" + " " * 14 + "أو 02 3456 7890"), ["02 2345 6789"])   # > 16 chars
        self.assertEqual(ph("رقمنا 02 2345 6789" + " " * 6 + "أو" + " " * 6 + "02 3456 7890"),
                         ["02 2345 6789", "02 3456 7890"])                                     # 14 chars

    def test_a_phone_before_the_word_unit_is_the_documented_cost(self):
        # «وحدة» is the insulin unit: a dose unit is absolute (ruling), so this real phone reads as numbers
        self.assertEqual(bl.phone_spans("اتصل 010 1234 5678 وحدة الكلى"), [])

    def test_time_and_count_words_keep_the_phone(self):
        for w in ("h", "hr", "hrs", "min", "mins", "sec", "s", "ms", "x", "times", "day", "days", "week", "weeks", "wk",
                  "m", "ساعة", "ساعات", "دقيقة", "دقايق", "دقائق", "ثانية", "ثواني", "سنة", "سنين", "سنوات", "يوم",
                  "أيام", "شهر", "شهور", "أشهر", "أسبوع", "أسابيع", "مرة", "مرات", "سعر", "سعرة", "كيلو", "ألف", "آلاف",
                  "مليون", "مليار", "كم", "مرتين", "يومين", "ساعتين"):
            with self.subTest(w):
                self.assertEqual(ph(self.MOBILE + " " + w), ["010 1234 5678"])

    def test_single_spellings_and_duals_stay_with_their_number(self):
        for u in ("ميليجرام", "مليغرام", "ميلي", "درجتين", "ملغم", "مكجم", "ميكروغرام", "دل", "مليمول", "نبضة", "مـجـم",
                  "مجم/دل", "mIU/L", "grams"):
            with self.subTest(u):
                self.assertEqual(bl.word_breaks(["خد", "2", u]), ["ok", "never"])
        for w in ("بالغ", "والغ", "الم", "بس", "بالك"):          # «بال» + a one-letter unit («غ») is a word: «adult»
            with self.subTest(w):
                self.assertEqual(bl.word_breaks(["سن", "18", w]), ["ok", "ok"])
                self.assertEqual(ph(self.MOBILE + " " + w), ["010 1234 5678"])

    def test_dose_words_that_are_also_everyday_words_are_absolute(self):
        # review r1 P2-3(b) + ruling: «حبة», «نقطة», «ظرف», «كيس», «درجة» after a cued phone shape: never a phone
        for w in ("حبة", "حبة حبة", "ظرف", "ظرف ساعة", "كيس", "درجة", "درجة أولى", "درجات", "نقطة", "نقط", "درجتين"):
            with self.subTest(w):
                self.assertEqual(bl.phone_spans(self.MOBILE + " " + w), [])
        self.assertEqual(ph("اتصل +20 100 123 4567 في ظرف ساعة"), ["+20 100 123 4567"])     # a word between

    def test_every_unit_of_the_module_is_classified_and_tested(self):
        # ruling: each unit gets a test. Every unit the module knows is a dose unit (it undoes a cued phone) unless it
        # is one of the explicit money/size/percent or time/count words below (they keep the phone)
        soft = {"egp", "usd", "sar", "aed", "kwd", "qar", "eur", "gbp", "$", "€", "£", "¥", "le", "l.e", "k", "km", "m",
                "cm", "kb", "mb", "gb", "tb", "hz", "khz", "km/h", "m2", "m3", "m²", "m³", "cm2", "cm²", "mm2", "mm²", "%",
                "percent", "pct", "‰", "kcal", "cal", "جنيه", "جنيهات", "ج.م", "دولار", "ريال", "درهم", "يورو", "دينار",
                "مليون", "مليار", "ألف", "آلاف", "سم", "كم", "م٢", "م٣", "سم٢", "بالمية", "بالمئة", "بالمائة", "٪", "سعر",
                "سعرة", "سعرات", "كالوري"}
        count = {"h", "hr", "hrs", "min", "mins", "sec", "s", "ms", "x", "times", "day", "days", "week", "weeks", "wk",
                 "ساعة", "ساعات", "دقيقة", "دقايق", "دقائق", "ثانية", "ثواني", "سنة", "سنين", "سنوات", "يوم", "أيام",
                 "شهر", "شهور", "أشهر", "أسبوع", "أسابيع", "مرة", "مرات", "كيلو"}
        units = sorted(bl._LATIN_UNITS | bl._ARABIC_UNITS)
        self.assertGreater(len(units), 200)
        for u in units:
            keeps = u in soft or u in count or bl._fold(u) in {bl._fold(w) for w in soft | count}
            for t in (self.MOBILE + " " + u, "اتصل 02 2345 6789 " + u):
                with self.subTest(t):
                    self.assertEqual(bl.phone_spans(t) == [], not keeps)

    def test_a_weak_cue_needs_a_dialled_looking_number(self):
        # review r1 P2-2: «رقم» is also "a reading"; a weak cue needs a group of 4+ digits
        for t in ("الرقم هو 080 120 135 150", "الرقم ده 080 120 135 150", "الرقم بتاعي 080 120 135 150",
                  "رقمه دلوقتي 080 120 135 150", "الرقم الجديد 080 120 135 150", "رقمي 05 120 135 150",
                  "رقمنا 080 120 135 150 %", "رقمنا 080 120 135 150 سم", "محمول 080 120 135 150", "number 080 120 135",
                  "رقمنا 050 123 456"):                                    # the cost: a 3-3-3 number with a weak cue
            with self.subTest(t):
                self.assertEqual(bl.phone_spans(t), [])
        for t, want in (("الرقم ده 02 2345 6789", "02 2345 6789"), ("رقمي 0555 123 456", "0555 123 456"),
                        ("محمول 02 2345 6789", "02 2345 6789"), ("اتصل 050 123 456", "050 123 456"),
                        ("call our number 050 123 456", "050 123 456"), ("number 02 2345 6789", "02 2345 6789"),
                        ("النمرة 02 2345 6789", "02 2345 6789"), ("نمرتي 02 2345 6789", "02 2345 6789")):
            with self.subTest(t):
                self.assertEqual(ph(t), [want])

    def test_more_cue_words_and_fillers(self):
        for t in ("للحجز 02 2345 6789", "للاستفسار 02 2345 6789", "للتواصل 02 2345 6789", "Contact 02 2345 6789",
                  "Mob: 02 2345 6789", "ت: 02 2345 6789", "واتس اب 02 2345 6789", "اتصل بنا 0555 123 456",
                  "اتصلوا علينا 02 2345 6789", "احجز 02 2345 6789", "احجزوا على 02 2345 6789"):
            with self.subTest(t):
                self.assertEqual(len(bl.phone_spans(t)), 1)
        for t in ("عالموبايل 02 2345 6789", "بالتليفون 02 2345 6789", "وعالواتساب 02 2345 6789"):    # prefixed
            with self.subTest(t):
                self.assertEqual(ph(t), ["02 2345 6789"])
        for t in ("الرقمي 02 2345 6789", "التليفوني 02 2345 6789", "الرقمنا 02 2345 6789"):   # article + possessive
            with self.subTest(t):
                self.assertEqual(bl.phone_spans(t), [])

    def test_the_cue_belongs_to_the_first_group_of_the_chain(self):
        # review r1 P3-5: «رقم 1 080 …» / a joined list
        self.assertEqual(bl.phone_spans("رقم 1 080 120 135 150"), [])
        self.assertEqual(bl.phone_spans("اتصل 1 02 2345 6789"), [])
        self.assertEqual(ph("اتصل 010 1234 5678 و 080 120 135 150"), ["010 1234 5678"])
        self.assertEqual(ph("رقمنا 010 1234 5678 012 3456"), ["010 1234 5678", "012 3456"])
        # review r2 P3-4: a strong cue gives the next phone in the same chain only a weak one
        self.assertEqual(ph("اتصل 010 1234 5678 080 120 135 150"), ["010 1234 5678"])
        self.assertEqual(ph("اتصل 010 1234 5678 02 3456 7890"), ["010 1234 5678", "02 3456 7890"])

    def test_more_connectors_and_decimals_reach_the_unit(self):
        # review r1 P3-4
        for c in (" لغاية 150", " لين 150", " الين 150", " إلين 150", " ولا 150", " بعدين 150", " مع 150", " ثمَّ 150",
                  " ثمّ 150", " up to 150", " up  to 150", " & 150", " × 150", " ؛ 150", " 0.5", " 1.5 - 2.5", " ٠٫٥",
                  " 1.5", ",5", " 2 و 2.5", " لغايه 150", " الي 150", " إلي 150", " حتي 150", " ثـم 150", " To 150",
                  " Or 150", " And 150", " Up to 150", " x 150", " X 150", " -- 150", " ‒ 150", " ― 150", " ~ 150", " : 150",
                  " ; 150", " … 150", " + 150", " يا 150", " ثم بعدين 150", " أو حتى 150", " and then 150", " .5", " ٫٥",
                  " ½", " ¼", " .. 150", " ... 150", " ولحد 150", " وحتى 150", " ولغاية 150", " وإلى 150", " والى 150",
                  " وبعدها 150", " بعدها 150", " وبعد كده 150", " الى ان 150", " ف 150", " فـ 150", " through 150",
                  " ـ 150", " ثُمَّ 150", " 2 و 1٫5", " 2 و ١٬٥٠٠", " 2 - ٢٫٥"):
            t = self.MOBILE + c + " مجم"
            with self.subTest(t):
                self.assertEqual(bl.phone_spans(t), [])
        self.assertEqual(bl.phone_spans("الرقم هو 05 120 135 1.5 مجم"), [])
        self.assertEqual(ph(self.MOBILE + " 0.5 كمان"), ["010 1234 5678"])
        self.assertEqual(ph(self.MOBILE + " upto 150 مجم"), ["010 1234 5678"])                  # not «up to»
        for c in (" وبعدينوبعدين 150", " ثمن 150", " xo 150", " Andrew 150", " يارب 150"):          # not connectors
            with self.subTest(c):
                self.assertEqual(ph(self.MOBILE + c + " مجم"), ["010 1234 5678"])

    def test_everyday_words_after_a_phone_keep_it_and_joined_phones_end_in_four_digits(self):
        # review r3 P3-5: «سي محمد», «مول العرب» (a mall) are words; «مول» is a unit only inside «مول/ل»
        for tail in (" سي محمد", " مول العرب", " سي سي"):
            with self.subTest(tail):
                self.assertEqual(ph(self.MOBILE + tail), ["010 1234 5678"])
        # review r3 P3-4: a reading right after a phone is not a second phone
        for t in ("اتصل 010 1234 5678 0120 135 150", "اتصل 010 1234 5678 أو 0120 135 150",
                  "رقمنا 02 2345 6789 أو 0555 123 456"):                # the cost: a 4-3-3 second phone
            with self.subTest(t):
                self.assertEqual(len(bl.phone_spans(t)), 1)

    def test_the_article_only_joins_a_dose_unit(self):
        # review r2 P3-5: «اليوم», «الملل» (boredom), «السم» (poison) are words, not units
        for w in ("اليوم", "المرة", "الكم", "السم", "الملل", "الغم", "والسعر", "الدرجة", "الوحدة"):
            with self.subTest(w):
                self.assertEqual(bl.word_breaks(["عندي", "5", w]), ["ok", "ok"])
        self.assertEqual(ph(self.MOBILE + " الدرجة الأولى"), ["010 1234 5678"])
        for w in ("بالمجم", "والملي", "بالمليجرام", "الجرام"):
            with self.subTest(w):
                self.assertEqual(bl.word_breaks(["خد", "5", w]), ["ok", "never"])
                self.assertEqual(bl.phone_spans(self.MOBILE + " " + w), [])

    def test_00_phones_in_every_digit_script(self):
        for t in ("اتصل ۰۰۹۶۶ ۵۰ ۱۲۳ ۴۵۶۷", "اتصل ٠٠٩٦٦ ٥٠ ١٢٣ ٤٥٦٧", "اتصل 00966 50 123 4567"):
            with self.subTest(ascii(t)):
                self.assertEqual(bl.phone_spans(t), [(5, len(t))])

    def test_a_leading_mark_that_flips_the_paragraph_direction_is_a_finding(self):
        # review ad85d58 P3-4: «[RLM]x ٥٨٧٩ 2040» reverses the number order with no digit next to the mark
        def marks(t):
            return [x["index"] for x in bl.control_findings(t) if x["char"] in "\u200e\u200f\u061c"]
        for t, want in (("\u200fx ٥٨٧٩ 2040", [0]), ("\u061cx ٥ ٦", [0]), ("\u061cx 5 6", []), ("\u200fx 5\nhello", []), ("abc\n\u200fx 5 6", []), ("\u200fhello\n5 6 2040", [0]),
                        ("\u200ex ٥ ٦", []), ("\u200fhello", []), ("\u200fhello world.", []), ("\u200fسكر 500", []), ("x \u200fy 5 6", []),
                        ("\u2066\u200f\u2069x 5 6", []), (". \u200fx 5 6", [2])):
            with self.subTest(ascii(t)):
                self.assertEqual(marks(t), want)
        f = [x for x in bl.control_findings("\u200fx ٥٨٧٩ 2040") if x["index"] == 0][0]
        self.assertIn("direction", f["why"])
        self.assertEqual(marks("\u200f5 6"), [0])                         # near a digit AND deciding: one finding
        self.assertEqual(marks("\u200fx ٥\u200e ٦"), [0, 4])               # in text order

    def test_phone_findings_name_a_forced_phone_on_a_line_with_a_dose(self):
        f = bl.phone_findings("اتصل 010 1234 5678 وخد 500 مجم")
        self.assertEqual([(x["start"], x["end"], x["text"]) for x in f], [(5, 18, "010 1234 5678")])
        self.assertIn("dose", f[0]["why"])
        for t in ("اتصل 010 1234 5678", "اتصل 010 1234 5678\nخد 500 مجم", "خد 500 مجم", "اتصل 010 1234 5678 جنيه"):
            with self.subTest(ascii(t)):
                self.assertEqual(bl.phone_findings(t), [])
        self.assertEqual(len(bl.phone_findings("خد 500 mg ثم اتصل 010 1234 5678")), 1)
        self.assertEqual(bl.phone_findings("Call 010 1234 5678, take 500 mg"), [])     # LTR caption: no HL3
        f = bl.phone_findings("سطر\nاتصل 010 1234 5678 وخد 500 مجم")
        self.assertEqual([(x["start"], x["end"]) for x in f], [(9, 22)])               # indices in the whole text
        self.assertEqual(len(bl.phone_findings("Call 010 1234 5678, take 500 mg", force_rtl=True)), 1)
        self.assertEqual(bl.phone_findings("اتصل 010 1234 5678 \u2066x\u2069 خد 500 مجم"), [])   # author's controls: no HL3
        self.assertEqual(len(bl.phone_findings("اتصل 010 1234 5678 وخد 500مجم")), 1)     # a glued dose
        for t in ("اتصل 010 1234 5678 وخد (500مجم)", "اتصل 010 1234 5678 خد 500-mg"):
            with self.subTest(t):
                self.assertEqual(len(bl.phone_findings(t)), 1)

    def test_the_test_file_has_no_raw_invisible_characters(self):
        # review ad85d58 P3-5: a raw U+2028 read as a space in the diff
        src = Path(__file__).read_text(encoding="utf-8")
        bad = [(i, hex(ord(c))) for i, c in enumerate(src)
               if unicodedata.category(c) in ("Cf", "Zl", "Zp", "Co", "Cn") or (unicodedata.category(c) == "Cc" and c != "\n")]
        self.assertEqual(bad, [])

    def test_linear_paths_by_growth_ratio(self):
        cases = (("spaces", lambda n: bl.phone_spans("05 250" + " " * n + "x"), 50000),
                 ("dash values", lambda n: bl.phone_spans(("05 250 - " * n) + "مجم"), 5000),
                 ("dash heads", lambda n: bl.phone_spans("05 " + "- 05 " * n), 5000),
                 ("or heads", lambda n: bl.phone_spans("05 " + "أو 5 " * n), 5000),
                 ("then heads", lambda n: bl.phone_spans("05 " + "ثم 5 " * n), 5000),
                 ("cue words", lambda n: bl.phone_spans("اتصل على " * n + "02 2345 6789 " * n), 2000),
                 ("phones", lambda n: bl.phone_spans("رقمنا 02 2345 6789 " * n), 2000),
                 ("dose lines", lambda n: bl.phone_findings(("اتصل 010 1234 5678 خد 5 مجم\n") * n), 1000),
                 ("lay out", lambda n: bl.lay_out("خد " + "1 - " * n + "مجم", 20), 2500),
                 ("marks", lambda n: bl.control_findings(("\u200fx 5 6\n") * n), 5000),
                 ("colon ones", lambda n: bl.phone_spans("اتصل " + ":1" * n), 5000),
                 ("paren ones", lambda n: bl.phone_spans("(1" * n), 5000),
                 ("paren lay out", lambda n: bl.lay_out("خد " + "(1)" * n, 40), 1000),
                 ("paren findings", lambda n: bl.phone_findings("اتصل " + "(1" * n + " مجم"), 2000),
                 ("long word", lambda n: bl.phone_spans("ا" * n + ":02 2345 6789"), 50000),
                 ("decimals", lambda n: bl.phone_spans("010 1234 5678 " + "1.5 - " * n), 3000),
                 ("comma values", lambda n: bl.phone_spans("010 1234 5678 " + "1,5," * n), 3000),
                 ("mark tails", lambda n: bl.phone_spans(("1" + chr(0x200F) + ":") * n), 2000),
                 ("zero-width tails", lambda n: bl.phone_spans(("1" + chr(0x200B) * 40) * n), 1000),
                 ("dash runs", lambda n: bl.phone_spans("010 1234 5678 " + "-" * n + " مجم"), 20000),
                 ("glued connectors", lambda n: bl.phone_spans("010 1234 5678 " + "وبعدين" * n + " 5"), 5000),
                 ("tatweel la", lambda n: bl.lay_out("خد 5 " + "لـ " * n + "دلوقتي", 30), 3000),
                 ("tatweel la phone", lambda n: bl.phone_spans("اتصل 010 1234 5678 " + "لـــ " * n + "x"), 3000),
                 ("dot runs", lambda n: bl.phone_spans("010 1234 5678 " + "." * n + "x"), 20000),
                 ("connector runs", lambda n: bl.phone_spans("010 1234 5678 " + "و ثم لـ ف ـ . " * n + "x"), 3000))
        for label, fn, n in cases:
            with self.subTest(label):
                assert_linear(self, fn, n, 4 * n, label)


if __name__ == "__main__":
    unittest.main()
