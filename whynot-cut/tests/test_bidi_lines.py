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
import builtins
import importlib
import json
import unittest
from pathlib import Path
from unittest import mock

sys = _sys
SK = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SK / "engine" / "reel"))

from lib import bidi_lines as bl  # noqa: E402

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
        try:
            from bidi import get_display
        except ImportError:                                   # pragma: no cover - the engine runtime ships it
            self.skipTest("python-bidi missing: the cross-check needs the engine runtime (tools/test.sh)")
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
                        ("0100 123 4567", ["0100 123 4567"]), ("02 2345 6789", ["02 2345 6789"]),
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
        import time
        t0 = time.perf_counter()
        bl.lay_out("السنوات " + " ".join(str(2000 + i) for i in range(23)), 30)
        bl.phone_spans(" ".join(["123"] * 3000))
        self.assertLess(time.perf_counter() - t0, 2.0)          # linear: a long list of numbers never stalls a render
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
        self.assertEqual(a, b)

    def test_refusals_raise_cleanly(self):
        with self.assertRaises(ValueError):
            bl.wrap("abc", 0)
        with self.assertRaises(ValueError):
            bl.paragraph("abc", base=2)
        with self.assertRaises(ValueError):
            bl.line_runs(bl.paragraph("abc"), 2, 9)

    def test_same_result_on_darwin(self):
        want = [[[r.level, r.text] for r in bl.line_runs(bl.paragraph(e["text"]))] for e in LINES]
        try:
            with mock.patch.object(sys, "platform", "darwin"):
                mod = importlib.reload(bl)
                got = [[[r.level, r.text] for r in mod.line_runs(mod.paragraph(e["text"]))] for e in LINES]
        finally:
            importlib.reload(bl)
        self.assertEqual(got, want)

    def test_hl3_never_overrides_the_authors_own_controls(self):
        self.assertEqual(runs("كلمنا \u202e010 1234 5678\u202c"), [[3, "010 1234 5678"], [1, "كلمنا "]])
        deep = "\u202b" * 124 + "كلمنا 010 1234 5678" + "\u202c" * 124
        self.assertEqual(bl.phone_spans(deep), [(130, 143)])
        self.assertEqual(bl.paragraph(deep).levels[130:143], bl.paragraph(deep, hl1=False).levels[130:143])

    def test_host_text_gives_a_full_uax9_engine_this_modules_order(self):
        self.assertEqual(bl.host_text("AI بيغيّر الطب"), "\u200fAI بيغيّر الطب")
        self.assertEqual(bl.host_text("بيغيّر AI"), "بيغيّر AI")
        self.assertEqual(bl.host_text("complete blood count test.", base=1), "\u200fcomplete blood count test.")
        self.assertEqual(bl.host_text("שלום world", base=0), "\u200eשלום world")
        self.assertEqual(bl.host_text("كلمنا 010 1234 5678."), "كلمنا \u202d010 1234 5678\u202c.")
        self.assertEqual(bl.host_text("كلمنا \u2066010 1234 5678\u2069"), "كلمنا \u2066010 1234 5678\u2069")
        with self.assertRaises(ValueError):
            bl.host_text("x", base=3)
        try:
            from bidi import get_display
        except ImportError:                                   # pragma: no cover
            return
        for e in LINES:                                         # a full UAX #9 engine + host_text = our order
            with self.subTest(e["id"]):
                par = bl.paragraph(e["text"])
                ref = get_display(bl.host_text(e["text"]), base_dir=None)
                self.assertEqual("".join(c for c in ref if c not in CONTROLS), bl.visual(par, mirror=False))

    def test_deep_nesting_overflow_is_safe(self):
        text = "\u202b" * 200 + "abc" + "\u202c" * 200 + " مرحبا"
        par = bl.paragraph(text)
        self.assertLessEqual(max(par.levels), bl.MAX_DEPTH + 1)
        self.assertEqual("".join(r.text for r in bl.line_runs(par)).replace(" ", ""), "مرحباabc")


if __name__ == "__main__":
    unittest.main()
