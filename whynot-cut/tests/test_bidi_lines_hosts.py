# SPDX-License-Identifier: GPL-3.0-or-later
# © 2026 The Why Not AI (thewhynot.ai)
"""3.0 Phase 4 Task 54 = Addendum M2-T1, the rewiring: the graphics stills (hb_text; ct_text on macOS), previews and
thumbnails (previews._text_block / _shape, publish.highlight_spans) take their line breaks and run order from
lib/bidi_lines instead of their own bidi rules and ae_builder.wrap_lines. Golden stills (Arabic, mixed, a wrapped
all-Latin line of an Arabic block) are drawn with the OFL IBM Plex Sans Arabic the panel already ships.
Run:  bash tools/test.sh -p test_bidi_lines_hosts.py
"""
import sys as _sys
_sys.dont_write_bytecode = True  # keep the plugin folder free of __pycache__
import _isolation  # noqa: F401,E402  G79: sandbox the engine home first (tests/_isolation.py)
import json
import os
import tempfile
import unicodedata
import unittest
from pathlib import Path
from unittest import mock

sys = _sys
SK = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SK / "engine" / "reel"))

from lib import bidi_lines as bl, ct_text, hb_text, plat, previews, publish  # noqa: E402
from bidi import get_display  # noqa: E402  python-bidi (LGPL, test-only cross-check), pinned in the engine locks

FIX = SK / "tests" / "fixtures" / "bidi"
LINES = json.loads((FIX / "lines.json").read_text(encoding="utf-8"))["lines"]
CONTROLS = {chr(c) for c in (0x2066, 0x2067, 0x2068, 0x2069, 0x200E, 0x200F, 0x061C,
                              0x202A, 0x202B, 0x202C, 0x202D, 0x202E)}
WRAPPED = "الدكتور طلب مني أعمل complete blood count test."     # line 2 is all Latin, inside an Arabic block
# the golden stills' font: OFL, already in the repo for the panel (adobe/panel-ui/fonts/ibmplexsansarabic/OFL.txt)
PANEL_FONTS = SK.parent / "adobe" / "panel-ui" / "fonts"
PLEX = PANEL_FONTS / "ibmplexsansarabic" / "IBMPlexSansArabic-Regular.ttf"
GOLDEN = FIX / "stills"
STILLS = {   # id -> (text, max_chars): the golden stills (M2.3 "golden stills AR/mixed")
    "ar": ("خد ٥٠٠ مجم مرتين في اليوم بعد الأكل لمدة ٣ أيام", 16),
    "mixed": ("عملت تحليل الـ MRI و CBC بـ 1500 EGP (مش غالي)، كلمنا على 010 1234 5678.", 22),
    "wrapped": (WRAPPED, 26),
    "block": ("عملت أشعة بالـMRI 2024 500 مرة", 14),         # its last line needs the block's levels (W7)
}


def arabic_font() -> Path | None:
    for d in plat.font_dirs():
        for c in ("arial.ttf", "tahoma.ttf", "segoeui.ttf", "GeezaPro.ttc", "SFArabic.ttf", "NotoSansArabic-Regular.ttf",
                  "DejaVuSans.ttf"):
            hits = list(d.rglob(c)) if d.is_dir() else []
            if hits:
                return hits[0]
    return None


# medical and mixed texts for the PIL-vs-HarfBuzz order check (doses, ranges, phones, brackets, «الـ», lam-alef,
# harakat, ZWNJ, the «الله» ligature)
MEDICAL = ["خد 500 مجم مرتين", "خد ٥٠٠ مجم بعد الأكل", "2.5 مل كل 8 ساعات", "10-20 وحدة أنسولين", "الضغط 120/80 تمام",
           "5 mg/kg للطفل", "٣٫٥ مجم/كجم يوميا", "1/2 قرص قبل النوم", "السكر التراكمي 7.5% - 8%", "نسبة ١٠٪ من الناس",
           "كلمنا على 010 1234 5678 أو 011 2345 6789", "العلاج (insulin) مهم جدا", "عملت الـ MRI و CBC امبارح",
           "لا تاخد 500 mg من غير استشارة", "الطِّبُّ الوقائي أهم", "لا" + chr(0x200C) + "مركزية في العلاج",
           "قال الله تعالى", "Vitamin D 1000 - 2000 وحدة يوميا"] + [t for t, _ in STILLS.values()]
HARAKAT = {chr(c) for c in range(0x064B, 0x0660)} | {chr(0x0670)}
MIRROR = str.maketrans("()[]{}«»‹›<>", ")(][}{»«›‹><")


def deshape(s: str) -> str:
    """A PIL-path string back to plain letters: Arabic presentation forms NFKC-folded (a ligature unfolds to its
    letters, reversed, since it stands in a right-to-left run); harakat left out."""
    out = []
    for c in s:
        if 0xFB50 <= ord(c) <= 0xFDFF or 0xFE70 <= ord(c) <= 0xFEFF:     # Arabic presentation forms A and B
            d = unicodedata.normalize("NFKC", c)
            out.append(d[::-1] if len(d) > 1 else d)
        else:
            out.append(c)
    return "".join(ch for ch in "".join(out) if ch not in HARAKAT)


def drawn_order(ln) -> str:
    """What the HarfBuzz path draws for a Line, as letters left to right: its runs in order, a right-to-left run
    reversed with its brackets mirrored (HarfBuzz's L4); harakat left out (the PIL path drops them)."""
    return "".join(ch for r in ln.runs for ch in (r.text[::-1].translate(MIRROR) if r.rtl else r.text)
                   if ch not in HARAKAT)


def bare(s: str) -> str:
    return "".join(c for c in s if c not in CONTROLS)


class RecordingFont:
    """A HarfBuzz/CoreText-like font for _text_block that records every render call (text, rgba, bidi)."""
    engine = "harfbuzz"

    def __init__(self):
        self.calls = []

    def getmetrics(self):
        return 10, 3

    def render(self, text, rgba=(255, 255, 255, 255), bidi=None):
        from PIL import Image
        self.calls.append((text, rgba, bidi))
        return Image.new("RGBA", (1, 1)), 0, 10.0 * len(text)


def fake_coretext():
    """pyobjc faked on every OS: returns (patch contexts, the NSAttributedString mock)."""
    ns = mock.MagicMock()
    return (mock.patch.object(ct_text, "NSAttributedString", ns, create=True),
            mock.patch.object(ct_text, "CoreText", mock.MagicMock(), create=True),
            mock.patch.object(ct_text, "Quartz", mock.MagicMock(), create=True)), ns


class TestHbTextRuns(unittest.TestCase):
    def test_runs_keep_every_character_and_the_fixture_direction(self):
        for e in LINES:
            with self.subTest(e["id"]):
                rtl, rs = hb_text.runs(e["text"])
                self.assertEqual(rtl, e["rtl"])
                self.assertEqual("".join(t for _, t in rs), bare(e["text"]))
                self.assertTrue(all(rs[k][0] != rs[k + 1][0] for k in range(len(rs) - 1)))

    def test_the_arabic_percent_sign_now_matches_the_captions(self):
        self.assertEqual(hb_text.runs("٧٠٪ من الناس")[1][:2], [("L", "٧٠"), ("R", "٪ من الناس")])

    def test_a_line_that_is_not_the_drawn_text_is_refused(self):
        ln = bl.lay_out(WRAPPED, 26)[1]
        with self.assertRaises(ValueError):
            hb_text.shape_line("another line", None, ln)


@unittest.skipUnless(hb_text.AVAILABLE, "HarfBuzz/FreeType missing (run with the engine runtime)")
class TestHbTextShape(unittest.TestCase):
    def setUp(self):
        self.font = arabic_font()
        if not self.font:
            self.skipTest("no Arabic-capable system font found")
        self.f = hb_text.HBFontSpec(str(self.font), 40)

    def gid(self, ch):
        return hb_text.shape_line(ch, self.f)[0][0]

    def test_shape_line_follows_the_hand_written_fixture_runs(self):
        for e in LINES:
            with self.subTest(e["id"]):
                want = [g for lvl, t in e["runs"] for g in hb_text._shape(t, "R" if lvl % 2 else "L", self.f)]
                self.assertEqual(hb_text.shape_line(e["text"], self.f), want)

    def test_percent_sign_left_and_phone_groups_as_dialled(self):
        g = [x[0] for x in hb_text.shape_line("٧٠٪ من الناس", self.f)]
        self.assertLess(g.index(self.gid("٪")), g.index(self.gid("٧")))
        g = [x[0] for x in hb_text.shape_line("كلمنا 010 1234 5678.", self.f)]
        self.assertEqual(g[:14], [self.gid(c) for c in ".010 1234 5678"])

    def test_a_wrapped_latin_line_keeps_the_paragraph_direction(self):
        lines = previews._wrap_block(WRAPPED, 26)
        self.assertEqual([ln.text for ln in lines], ["الدكتور طلب مني أعمل", "complete blood count test."])
        g = [x[0] for x in hb_text.shape_line(lines[1].text, self.f, lines[1])]
        self.assertEqual(g[0], self.gid("."))                  # the period on the paragraph's (left) side
        g = [x[0] for x in hb_text.shape_line(lines[1].text, self.f)]
        self.assertEqual(g[-1], self.gid("."))                 # alone, the same text is an LTR paragraph
        img, _, w = self.f.render(lines[1].text, (255, 255, 255, 255), bidi=lines[1])
        self.assertAlmostEqual(w, hb_text.measure(lines[1].text, self.f), delta=0.01)

    def test_latin_term_first_ends_up_rightmost(self):
        g = hb_text.shape_line("AI بيغيّر الطب", self.f)
        self.assertEqual(g[-1][0], self.gid("I"))

    def test_a_wrapped_line_keeps_the_levels_of_its_whole_block(self):
        """Review r1 (v2) P2: the line is shaped from the block's runs, never re-resolved alone with only its
        direction (W7/N0/N1 across the break): «2024 500» stays one run, as CoreText and the PIL path draw it."""
        differ = 0
        for text, w in (("عملت أشعة بالـMRI 2024 500 مرة", 14), ("نسبة السكر 7.5% - 8% عند الصايم", 10),
                        ("السعر 1500 EGP - 2000 EGP للجلسة الواحدة", 12), ("Vitamin D 1000 - 2000 وحدة يوميا", 12)):
            for ln in bl.lay_out(text, w, balanced=True):
                with self.subTest(text=text, line=ln.text):
                    block = [g for r in ln.runs for g in hb_text._shape(r.text, "R" if r.rtl else "L", self.f)]
                    self.assertEqual(hb_text.shape_line(ln.text, self.f, ln), block)
                    alone = bl.line_runs(bl.paragraph(ln.text, base=int(ln.rtl)))
                    if [(r.text, r.level) for r in alone] != [(r.text, r.level) for r in ln.runs]:
                        differ += 1
                        self.assertNotEqual(hb_text.shape_line(ln.text, self.f, ln),
                                            [g for r in alone for g in hb_text._shape(r.text, "R" if r.rtl else "L",
                                                                                       self.f)])
        self.assertGreaterEqual(differ, 4)                     # the cases really need the block's levels

    def test_arabic_indic_decimals_keep_their_order_on_the_drawn_path(self):
        """K-T5 on shape_line itself (hb_text.runs is a helper; the stills draw through shape_line)."""
        for text, num in (("٣٫٥ مجم", "٣٫٥"), ("خد ٥٠٠ مجم", "٥٠٠"), ("الجرعة 2.5 مجم", "2.5")):
            with self.subTest(text):
                g = [x[0] for x in hb_text.shape_line(text, self.f)]
                want = [self.gid(c) for c in num]
                self.assertTrue(any(g[i:i + len(want)] == want for i in range(len(g))), g)


class TestStillsWrap(unittest.TestCase):
    def test_the_block_wrap_keeps_the_no_break_rules(self):
        for text, w in (("عملت تحليل الـ MRI امبارح", 12), ("خد ٥٠٠ mg مرتين في اليوم", 8),
                        ("كلمني على 010 1234 5678.", 8), ("العلاج ( insulin ) مهم", 9)):
            with self.subTest(text):
                lines = [ln.text for ln in previews._wrap_block(text, w)]
                self.assertEqual(" ".join(lines), text)
                allowed = {s for s, _, _ in bl.breaks(text)}
                ends, pos = [], 0
                for ln in lines[:-1]:
                    pos += len(ln)
                    ends.append(pos)
                    pos += 1
                self.assertTrue(set(ends) <= allowed, lines)
        self.assertTrue(all(ln.rtl for ln in previews._wrap_block("سطر\\nsecond line", 30)))
        self.assertEqual([ln.text for ln in previews._wrap_block("a\n\nb", 30)], ["a", "b"])

    def test_blank_text_and_spacing_as_before(self):
        from PIL import Image, ImageDraw
        for blank in ("", "  ", "\n", "\\n"):
            with self.subTest(repr(blank)):
                self.assertEqual([ln.text for ln in previews._wrap_block(blank, 14)], [""])
                font = RecordingFont()
                self.assertEqual(len(previews._text_block(ImageDraw.Draw(Image.new("RGBA", (1, 1))), blank, font,
                                                          5, 5, (255, 255, 255), max_chars=14)), 1)
        self.assertEqual([ln.text for ln in previews._wrap_block("a  b\tc", 30)], ["a b c"])

    def test_max_chars_zero_or_less_is_one_word_per_line_as_before(self):
        for mc in (0, -3, 0.0):
            with self.subTest(mc):
                self.assertEqual([ln.text for ln in previews._wrap_block("خد ٥٠٠ mg مرتين", mc)],
                                 ["خد", "٥٠٠ mg", "مرتين"])        # «٥٠٠ mg» never splits
        self.assertEqual([ln.text for ln in previews._wrap_block("one two three", 24.0)], ["one two three"])

    def test_a_max_chars_that_is_not_a_number_gets_a_plain_message(self):
        from decimal import Decimal
        for mc in (None, "24", True, float("nan"), float("inf"), Decimal("NaN"), 3j, [24]):
            with self.subTest(repr(mc)):
                with self.assertRaises(ValueError) as cm:
                    previews._wrap_block("نص", mc)
                self.assertIn("max_chars", str(cm.exception))
                self.assertIn(repr(mc), str(cm.exception))
        with self.assertRaisesRegex(ValueError, "max_chars must be a number"):
            previews._wrap_block("نص", 10 ** 400)                # past float range: still the plain message
        with self.assertRaisesRegex(ValueError, "max_chars must be a number of characters, not an integer of"):
            previews._wrap_block("نص", 10 ** 5000)               # past the 4300-digit str limit too
        with self.assertRaises(ValueError) as cm:
            previews._wrap_block("نص", "x" * 10000)
        self.assertLess(len(str(cm.exception)), 120)                # the message stays short

    def test_unicode_spaces_are_one_space_as_before(self):
        """Review r1 (v2) P3: wrap_lines split on every whitespace; U+001F and the Unicode spaces still do."""
        for sp in ("\x1f", "\u2009", "\u2002", "\u3000", "\u205f", "\u1680", " \t\u2009 "):
            with self.subTest(hex(ord(sp[0]))):
                self.assertEqual([ln.text for ln in previews._wrap_block(f"قال{sp}MRI{sp}مهم", 30)], ["قال MRI مهم"])
        for keep in ("\u00a0", "\u2007", "\u202f"):                # no-break spaces still join
            with self.subTest(hex(ord(keep))):
                self.assertEqual([ln.text for ln in previews._wrap_block(f"د.{keep}أحمد علي", 3)],
                                 [f"د.{keep}أحمد", "علي"])
        for brk in ("\x1c", "\x85", "\u2029", "\x0b", "\x0c"):    # the other paragraph separators: forced breaks
            with self.subTest(hex(ord(brk))):
                self.assertEqual([ln.text for ln in previews._wrap_block(f"سطر{brk}تاني", 30)], ["سطر", "تاني"])

    def test_cr_and_line_separator_are_forced_breaks_and_nbsp_joins(self):
        self.assertEqual([ln.text for ln in previews._wrap_block("سطر\rتاني", 30)], ["سطر", "تاني"])
        self.assertEqual([ln.text for ln in previews._wrap_block("سطر\u2028تاني", 30)], ["سطر", "تاني"])
        self.assertEqual([ln.text for ln in previews._wrap_block("د.\u00a0أحمد علي", 3)], ["د.\u00a0أحمد", "علي"])

    def test_the_wrap_is_deterministic(self):
        a, b = previews._wrap_block(STILLS["mixed"][0], 22), previews._wrap_block(STILLS["mixed"][0], 22)
        self.assertEqual([(x.text, x.runs) for x in a], [(x.text, x.runs) for x in b])

    def test_a_change_to_bidi_lines_redraws_the_stills(self):
        self.assertIn("bidi_lines.py", previews._RENDERER_SOURCES)


class TestTextBlockWiring(unittest.TestCase):
    """Review P1: every renderer of a still gets the Line it draws (the block's direction and levels)."""

    def test_both_render_calls_get_the_line_of_the_block(self):
        from PIL import Image, ImageDraw
        font = RecordingFont()
        boxes = previews._text_block(ImageDraw.Draw(Image.new("RGBA", (400, 300))), WRAPPED, font, 200, 150,
                                     (255, 255, 255), max_chars=26)
        want = bl.lay_out(WRAPPED, 26, balanced=True)
        self.assertEqual(len(boxes), 2)
        self.assertEqual(len(font.calls), 4)                    # fill + shadow per line
        for k, (text, rgba, line) in enumerate(font.calls):
            with self.subTest(k):
                self.assertIsInstance(line, bl.Line)
                self.assertEqual(line.text, text)
                self.assertEqual((line.text, line.rtl, line.runs), (want[k // 2].text, True, want[k // 2].runs))
        self.assertEqual(font.calls[1][1], (0, 0, 0, 110))        # the shadow call
        self.assertEqual(bl.visual(font.calls[2][2].par, font.calls[2][2].par_start, font.calls[2][2].par_end),
                         ".complete blood count test")

    def test_no_shadow_renders_once_per_line(self):
        from PIL import Image, ImageDraw
        font = RecordingFont()
        previews._text_block(ImageDraw.Draw(Image.new("RGBA", (400, 300))), WRAPPED, font, 200, 150,
                             (255, 255, 255), max_chars=26, shadow=False)
        self.assertEqual([c[2].text for c in font.calls], ["الدكتور طلب مني أعمل", "complete blood count test."])

    def test_the_pil_fallback_draws_the_block_order(self):
        try:
            import arabic_reshaper
        except ImportError:                                   # pragma: no cover - the engine runtime ships it
            self.skipTest("arabic_reshaper missing (run with the engine runtime)")
        d = mock.Mock(spec=["textlength", "text"])
        d.textlength.return_value = 50.0
        font = mock.Mock(spec=["getmetrics"])
        font.getmetrics.return_value = (10, 3)
        previews._text_block(d, WRAPPED, font, 200, 150, (255, 255, 255), max_chars=26, shadow=False)
        drawn = [c.args[1] for c in d.text.call_args_list]
        self.assertEqual(drawn[1], ".complete blood count test")    # the Latin line keeps the block's RTL base
        self.assertEqual(drawn[0], arabic_reshaper.reshape("الدكتور طلب مني أعمل")[::-1])

    def test_the_band_counts_the_lines_the_block_draws(self):
        """Review P1 (M9): the caption band's height comes from _wrap_block, so a 3-line caption dodges a card that a
        1-line caption clears."""
        sys.path.insert(0, str(SK / "tests"))
        import test_pipeline as T
        from lib.common import write_json, load_config
        from lib.plan import compile_plan
        t = load_config("graphics-templates.json")["templates"]["highlight_caption"]

        def half(n):
            return n * t["size"] * t.get("line_gap", 1.3) / 2 + t.get("bar_pad_y", 8)
        top = t["y"] + half(1) + 12 + 6                       # out of a 1-line band's reach, inside a 3-line band
        with tempfile.TemporaryDirectory() as tmp:
            root, p, words = T.make_project(Path(tmp))
            tc = T.TestPlanToXML()
            tc.p = p
            tc._semantic_stub()
            write_json(p.p("01_analysis/edit-decisions.json"), tc.decisions())
            self.assertTrue(compile_plan(p)["ok"])
            for n, moved in ((1, False), (3, True)):
                seen = []
                with self.subTest(n=n), \
                        mock.patch.object(previews, "render_event", side_effect=lambda ev, *a, **k: seen.append(ev)), \
                        mock.patch.object(previews, "_wrap_block", return_value=[None] * n) as wb:
                    self.assertTrue(previews.render_captions(p, [], avoid=[(0, 10 ** 7, top, top + 100)]))
                    self.assertTrue(seen)
                    self.assertTrue(all(("y" in ev["params"]) is moved for ev in seen), [ev["params"] for ev in seen])
                    self.assertEqual(wb.call_args[0][1], t.get("max_chars", 30))
                    self.assertEqual(wb.call_args[0][0], seen[-1]["params"]["text"])


class TestHighlightBoxes(unittest.TestCase):
    def font(self):
        f = mock.Mock(engine="harfbuzz", spec=["engine", "render"])
        f.render.side_effect = lambda s, rgba: (None, 0, 10.0 * len(s))
        return f

    def test_thumbnail_highlight_boxes_use_the_same_lines(self):
        text = "عملت تحليل الـ MRI امبارح"
        lines = previews._wrap_block(text, 12)
        k = next(i for i, ln in enumerate(lines) if "MRI" in ln.text)
        self.assertIn("الـ MRI", lines[k].text)
        boxes = [(0, 100 * i, 300, 100 * i + 50) for i in range(len(lines))]
        spans = publish.highlight_spans(text, "MRI", boxes, self.font(), 12)
        self.assertEqual(len(spans), 1)
        self.assertEqual(spans[0][1], 100 * k - 10)

    def test_thumbnail_highlight_sits_on_the_drawn_word(self):
        font = self.font()
        lines = previews._wrap_block(WRAPPED, 26)
        self.assertEqual(lines[1].text, "complete blood count test.")
        boxes = [(100, 100 * i, 100 + 10 * len(ln.text), 100 * i + 50) for i, ln in enumerate(lines)]
        # drawn «.complete blood count test»: «complete» right after the period, at x 110-190
        self.assertEqual(publish.highlight_spans(WRAPPED, "complete", boxes, font, 26), [(106, 90, 194, 160)])
        self.assertEqual(publish.highlight_spans(WRAPPED, "test", boxes, font, 26), [(316, 90, 364, 160)])  # not «.»
        # levels come from the whole block (W7 across the break): «2024» drawn left of «500» on the last line
        text2 = "عملت أشعة بالـMRI 2024 500 مرة"
        lines2 = previews._wrap_block(text2, 14)
        self.assertEqual(lines2[-1].text, "2024 500 مرة")
        boxes2 = [(100, 100 * i, 100 + 10 * len(ln.text), 100 * i + 50) for i, ln in enumerate(lines2)]
        y = 100 * (len(lines2) - 1) - 10
        self.assertEqual(publish.highlight_spans(text2, "2024", boxes2, font, 14), [(136, y, 184, y + 70)])
        self.assertEqual(publish.highlight_spans(text2, "500", boxes2, font, 14), [(186, y, 224, y + 70)])
        # an Arabic line: «طلب» is the second word from the right
        b0 = boxes[0]
        sp = publish.highlight_spans(WRAPPED, "طلب", boxes, font, 26)
        self.assertEqual(sp, [(b0[2] - 10 * len("الدكتور طلب") - 4, -10, b0[2] - 10 * len("الدكتور ") + 4, 60)])

    def test_a_word_split_by_the_bidi_order_gets_a_box_per_drawn_part(self):
        """Review P3-5: «بالـMRI scan» is drawn «MRI scan بالـ»: the word «بالـMRI» gets two boxes, never one over
        «scan»."""
        text = "بالـMRI scan"
        self.assertEqual([p.text for p in bl.line_pieces(bl.lay_out(text)[0])], ["MRI", " ", "scan", "بالـ"])
        boxes = [(100, 0, 220, 50)]
        self.assertEqual(publish.highlight_spans(text, "بالـMRI", boxes, self.font(), 30),
                         [(96, -10, 134, 60), (176, -10, 224, 60)])
        self.assertEqual(publish.highlight_spans(text, "scan", boxes, self.font(), 30), [(136, -10, 184, 60)])

    def test_the_arabic_percent_sign_is_inside_its_numbers_box(self):
        text = "٤٠٪ من الناس"
        self.assertEqual([p.text for p in bl.line_pieces(bl.lay_out(text)[0])][-2:], ["٪", "٤٠"])
        boxes = [(0, 0, 120, 50)]
        self.assertEqual(publish.highlight_spans(text, "٤٠٪", boxes, self.font(), 30), [(86, -10, 124, 60)])

    def test_words_joined_by_a_no_break_space_match_one_by_one(self):
        """Review P3-6: the wrap keeps «د.\u00a0أحمد» whole; the phrase «أحمد» still finds it."""
        text = "مع د.\u00a0أحمد علي"
        boxes = [(0, 0, 140, 50)]                            # drawn «علي», « », «د. أحمد», « », «مع» from x 0
        sp = publish.highlight_spans(text, "أحمد", boxes, self.font(), 30)
        self.assertEqual(sp, [(10 * len("علي ") - 4, -10, 10 * len("علي د.\u00a0أحمد") + 4, 60)])


    def test_a_word_matches_only_when_all_its_tokens_are_phrase_words(self):
        """Review r1 (v2) P3: «19» never boxes «COVID-19», «g» never boxes «e.g.»; the phrase «COVID-19» does."""
        text = "Take COVID-19 vitamins e.g. zinc"
        boxes = [(0, 0, 10 * len(text), 50)]
        f = self.font()
        self.assertEqual(publish.highlight_spans(text, "19", boxes, f, 60), [])
        self.assertEqual(publish.highlight_spans(text, "g", boxes, f, 60), [])
        self.assertEqual(publish.highlight_spans(text, "COVID-19", boxes, f, 60), [(46, -10, 134, 60)])
        self.assertEqual(publish.highlight_spans(text, "zinc", boxes, f, 60), [(276, -10, 324, 60)])

    def test_unicode_spaces_split_words_for_the_boxes(self):
        text = "قال\u2009MRI\u2009مهم"                              # one box over «MRI» only
        boxes = [(0, 0, 110, 50)]
        self.assertEqual(publish.highlight_spans(text, "MRI", boxes, self.font(), 30), [(36, -10, 74, 60)])


class TestCoreTextControls(unittest.TestCase):
    """CoreText runs its own UAX #9: it gets bidi_lines.host_text (faked pyobjc: this runs on every OS)."""

    def drawn(self, ns):
        return ns.alloc.return_value.initWithString_attributes_.call_args[0][0]

    def test_a_wrapped_line_gets_the_host_text_of_its_line(self):
        patches, ns = fake_coretext()
        with patches[0], patches[1], patches[2]:
            font = mock.Mock(_font=object())
            for ln in bl.lay_out(WRAPPED, 26):
                ct_text._line(ln.text, font, (0, 0, 0), bidi=ln)
                self.assertEqual(self.drawn(ns), bl.host_text(ln))
            ln = bl.lay_out(WRAPPED, 26)[1]
            self.assertTrue(self.drawn(ns).startswith("\u200f"))          # the block's RTL base
            with self.assertRaises(ValueError):
                ct_text._line("another line", font, (0, 0, 0), bidi=ln)

    def test_one_line_text_is_one_paragraph(self):
        patches, ns = fake_coretext()
        with patches[0], patches[1], patches[2]:
            font = mock.Mock(_font=object())
            for text, base in (("AI بيغيّر الطب", None), ("بيغيّر AI", None), ("كلمنا 010 1234 5678.", None),
                               ("complete blood count test.", 1), ("Hello world", None),
                               ("\u200fevidence إنها ممكن تساعد", None)):         # looks_type's mark-first text
                with self.subTest(text):
                    ct_text._line(text, font, (0, 0, 0), base)
                    self.assertEqual(self.drawn(ns), bl.host_text(bl.paragraph(text, base=base)))
                    self.assertEqual(bare(get_display(self.drawn(ns), base_dir=None)),
                                     bl.visual(bl.paragraph(text, base=base), mirror=False))

    def test_one_line_per_call(self):
        """A paragraph separator inside the text is refused loudly (previews._wrap_block splits them first)."""
        patches, ns = fake_coretext()
        with patches[0], patches[1], patches[2]:
            for text in ("سطر\nتاني", "سطر\u2029تاني"):
                with self.subTest(repr(text)), self.assertRaises(ValueError):
                    ct_text._line(text, mock.Mock(_font=object()), (0, 0, 0))

    def test_render_line_hands_the_line_on(self):
        ln = bl.lay_out(WRAPPED, 26)[1]
        with mock.patch.object(ct_text, "_line", side_effect=RuntimeError("stop")) as m:
            with self.assertRaises(RuntimeError):
                ct_text.render_line(ln.text, object(), (1, 2, 3, 4), bidi=ln)
        self.assertIs(m.call_args.kwargs.get("bidi"), ln)
        spec = ct_text.CTFontSpec.__new__(ct_text.CTFontSpec)
        with mock.patch.object(ct_text, "render_line", return_value="ok") as m:
            self.assertEqual(spec.render(ln.text, (1, 2, 3, 4), bidi=ln), "ok")
        self.assertEqual(m.call_args[0][3], ln)

    def test_coretext_draws_the_harfbuzz_order_on_wrapped_lines(self):
        """Review P2-2: the three wrapped lines where a per-line host string gave CoreText another order. An
        independent UAX #9 (python-bidi standing in for CoreText) resolves the host text to our order."""
        patches, ns = fake_coretext()
        with patches[0], patches[1], patches[2]:
            font = mock.Mock(_font=object())
            for text, w in (("عملت أشعة بالـMRI 2024 500 مرة", 14), ("نسبة السكر 7.5% - 8% عند الصايم", 10),
                            ("السعر 1500 EGP - 2000 EGP للجلسة الواحدة", 12)):
                for ln in bl.lay_out(text, w, balanced=True):
                    with self.subTest(text=text, line=ln.text):
                        ct_text._line(ln.text, font, (0, 0, 0), bidi=ln)
                        ours = "".join(r.text[::-1] if r.rtl else r.text for r in ln.runs)
                        self.assertEqual(bare(get_display(self.drawn(ns), base_dir=None)), ours)


class TestPreviewsShape(unittest.TestCase):
    def setUp(self):
        try:
            import arabic_reshaper  # noqa: F401
        except ImportError:                                   # pragma: no cover - the engine runtime ships it
            self.skipTest("arabic_reshaper missing (run with the engine runtime)")

    def test_the_pil_order_is_the_harfbuzz_order(self):
        """Review 081cb9f P3-4, independent of bidi_lines.visual() (the call _shape makes): the PIL string read back to
        plain letters (NFKC folds Arabic presentation forms; a ligature such as «ﻻ» unfolds to its letters in drawn,
        right-to-left order) is what the HarfBuzz path draws: the line's runs left to right, each right-to-left run
        reversed with its brackets mirrored. arabic_reshaper drops harakat, so they are left out on both sides. Every
        fixture line and the medical texts below, unwrapped and at five widths."""
        n = 0
        for text in [e["text"] for e in LINES] + MEDICAL:
            for width in (None, 6, 10, 14, 22, 30):
                for ln in bl.lay_out(text, width):
                    with self.subTest(text, width=width, line=ln.text):
                        self.assertEqual(deshape(previews._shape(ln)), drawn_order(ln))
                    n += 1
        self.assertGreater(n, 900)

    def test_phone_groups_brackets_and_the_block_direction(self):
        one = lambda s: previews._shape(bl.lay_out(s)[0])      # noqa: E731
        self.assertTrue(one("كلمنا على 010 1234 5678").startswith("010 1234 5678"))
        self.assertIn("(insulin)", one("العلاج (insulin) مهم"))   # mirrored back to reading shape
        self.assertEqual(one("Plain English (text)"), "Plain English (text)")
        self.assertEqual(previews._shape(bl.lay_out(WRAPPED, 26)[1]), ".complete blood count test")

    def test_per_run_reshaping_keeps_a_lam_alef_ligature_in_place(self):
        import arabic_reshaper
        ln = bl.lay_out("لا تاخد 500 mg من غير استشارة", 12)[0]
        self.assertEqual(previews._shape(ln), bl.visual(ln.par, ln.par_start, ln.par_end,
                                                        shape=arabic_reshaper.reshape))
        self.assertIn("ﻻ", previews._shape(ln))             # «لا» as one presentation form

    def test_errors_are_never_swallowed(self):
        """Executor ruling 2026-10-18: a wrong call or a bidi_lines bug raises; it never draws logical order."""
        with self.assertRaises(TypeError):
            previews._shape("نص")                                   # a bare string: which block? refused
        ln = bl.lay_out("نص", 10)[0]
        with mock.patch.object(bl, "visual", side_effect=TypeError("boom")):
            with self.assertRaises(TypeError):
                previews._shape(ln)
        with mock.patch.object(bl, "visual", side_effect=RuntimeError("boom")):
            with self.assertRaises(RuntimeError):
                previews._shape(ln)


@unittest.skipUnless(PLEX.is_file(), "not a repo checkout (the panel fonts are not next to the plugin)")
class TestPillowLastResortLayout(unittest.TestCase):
    """Review 081cb9f P3-3: the last-resort PIL path hands Pillow a string already in visual order (_shape). A Pillow
    with RAQM (libraqm + a libfribidi found at run time, e.g. Homebrew on a Mac) would reorder it again, so every
    Pillow font of that path is opened with the BASIC layout. RAQM is faked here (this runtime has none)."""

    def setUp(self):
        from PIL import ImageFont
        self.ImageFont = ImageFont
        self.raqm = mock.patch.object(ImageFont.core, "HAVE_RAQM", True)     # Pillow's own default would be RAQM
        self.raqm.start()
        self.addCleanup(self.raqm.stop)

    def test_the_brand_pillow_font_is_basic(self):
        IF, real, seen = self.ImageFont, self.ImageFont.truetype, []

        def recording(*a, **k):
            seen.append(k.get("layout_engine"))
            if k.get("layout_engine") != IF.Layout.BASIC:
                return mock.Mock(layout_engine=k.get("layout_engine"))      # never built with RAQM here
            return real(*a, **k)
        brand = previews.Brand.__new__(previews.Brand)
        brand.engines = set()
        with mock.patch.object(hb_text, "AVAILABLE", False), mock.patch.object(ct_text, "AVAILABLE", False),                 mock.patch.object(IF, "truetype", side_effect=recording):
            f = brand._font({"file": str(PLEX), "ps": "IBMPlexSansArabic-Regular"}, 40)
        self.assertEqual(brand.engines, {"pillow-fallback"})
        self.assertEqual(seen, [IF.Layout.BASIC])
        self.assertEqual(f.layout_engine, IF.Layout.BASIC)

    def test_the_default_font_is_basic(self):
        """A block with no font at all draws with Pillow's ImageFont.load_default(), which Pillow itself opens BASIC
        (12.3, the pinned version): a Pillow that changed that would fail here."""
        aware = previews._ArabicAware(None, None, previews.Brand.__new__(previews.Brand), None)
        aware.brand._fallbacks_used = {}
        for text in ("abc", "نص"):
            with self.subTest(text):
                self.assertEqual(aware.for_text(text).layout_engine, self.ImageFont.Layout.BASIC)

    def test_a_basic_font_draws_the_shaped_string_as_given(self):
        """BASIC draws characters left to right as given: the PIL still of a mixed line equals the still drawn from the
        same characters one by one, so nothing reorders the visual string a second time."""
        from PIL import Image, ImageDraw
        f = previews._pil_font(str(PLEX), 40)
        s = previews._shape(bl.lay_out("كلمنا على 010 1234 5678", 40)[0])
        whole = Image.new("L", (900, 80))
        ImageDraw.Draw(whole).text((10, 10), s, font=f, fill=255)
        piece = Image.new("L", (900, 80))
        d, x = ImageDraw.Draw(piece), 10.0
        for c in s:
            d.text((x, 10), c, font=f, fill=255)
            x += f.getlength(c)
        self.assertLess(sum(abs(a - b) for a, b in zip(whole.getdata(), piece.getdata())) / (900 * 80), 8)


@unittest.skipUnless(hb_text.AVAILABLE, "HarfBuzz/FreeType missing (run with the engine runtime)")
@unittest.skipUnless(PANEL_FONTS.is_dir(), "not a repo checkout (the panel fonts are not next to the plugin)")
class TestGoldenStills(unittest.TestCase):
    """M2.3 golden stills: each still is drawn by previews._text_block with the HarfBuzz engine and the OFL panel font.
    The glyph order per line is exact; the picture may differ by FreeType's anti-aliasing only. Regenerate (after a
    human looks at the PNGs): WNC_WRITE_GOLDEN=1 bash tools/test.sh -p test_bidi_lines_hosts.py -k Golden"""

    def draw(self, text, mc):
        from PIL import Image, ImageDraw
        self.assertTrue(PLEX.is_file(), f"panel font missing: {PLEX}")
        font = hb_text.HBFontSpec(str(PLEX), 44)
        im = Image.new("RGBA", (720, 420), (0, 0, 0, 0))
        boxes = previews._text_block(ImageDraw.Draw(im), text, font, 360, 210, (255, 255, 255), max_chars=mc)
        glyphs = [[g[0] for g in hb_text.shape_line(ln.text, font, ln)] for ln in previews._wrap_block(text, mc)]
        return im, {"lines": [ln.text for ln in previews._wrap_block(text, mc)], "glyphs": glyphs,
                    "boxes": [[round(v, 2) for v in b] for b in boxes]}

    def test_the_stills_match_their_golden(self):
        import numpy as np
        from PIL import Image
        write = os.environ.get("WNC_WRITE_GOLDEN") == "1"
        table_path = GOLDEN / "stills.json"
        table = {} if write else json.loads(table_path.read_text(encoding="utf-8"))
        for sid, (text, mc) in STILLS.items():
            with self.subTest(sid):
                im, rec = self.draw(text, mc)
                png = GOLDEN / f"{sid}.png"
                if write:
                    GOLDEN.mkdir(parents=True, exist_ok=True)
                    im.save(png)
                    table[sid] = dict(rec, text=text, max_chars=mc)
                    continue
                want = table[sid]
                self.assertEqual((want["text"], want["max_chars"]), (text, mc))
                self.assertEqual(rec["lines"], want["lines"])
                self.assertEqual(rec["glyphs"], want["glyphs"])         # the run order, glyph by glyph
                self.assertEqual(rec["boxes"], want["boxes"])
                ref = np.asarray(Image.open(png).convert("RGBA"), dtype=np.int16)
                got = np.asarray(im, dtype=np.int16)
                self.assertEqual(ref.shape, got.shape)
                diff = np.abs(ref - got)
                self.assertLess(float(diff[..., 3].mean()), 0.5, f"{sid}: the still differs from {png.name}")
                self.assertLess(int((diff[..., 3] > 64).sum()), 40, f"{sid}: glyphs moved in {png.name}")
        if write:
            rows = ",\n".join(f" {json.dumps(k)}: {json.dumps(v, ensure_ascii=False)}" for k, v in table.items())
            table_path.write_text("{\n" + rows + "\n}\n", encoding="utf-8", newline="\n")
            self.fail("golden stills rewritten: look at the PNGs, then run again without WNC_WRITE_GOLDEN")

    def test_write_mode_never_passes_silently(self):
        """Review r1 (v2) P3: WNC_WRITE_GOLDEN rewrites the fixtures and then FAILS, so a leaked variable can't turn
        the gate off."""
        with tempfile.TemporaryDirectory() as tmp, mock.patch.dict(os.environ, {"WNC_WRITE_GOLDEN": "1"}), \
                mock.patch(f"{__name__}.GOLDEN", Path(tmp) / "stills"):
            case = TestGoldenStills("test_the_stills_match_their_golden")
            with self.assertRaisesRegex(AssertionError, "golden stills rewritten"):
                case.test_the_stills_match_their_golden()
            self.assertEqual(sorted(p.name for p in (Path(tmp) / "stills").iterdir()),
                             sorted([f"{k}.png" for k in STILLS] + ["stills.json"]))

    def test_the_goldens_pin_the_reading_order(self):
        """Independent of the picture: the golden table itself says what an Arabic reader meets first."""
        table = json.loads((GOLDEN / "stills.json").read_text(encoding="utf-8"))
        font = hb_text.HBFontSpec(str(PLEX), 44)
        gid = lambda ch: hb_text.shape_line(ch, font)[0][0]      # noqa: E731
        wrapped = table["wrapped"]["glyphs"][1]
        self.assertEqual(wrapped[0], gid("."))                    # the period on the block's left side
        mixed = [g for line in table["mixed"]["glyphs"] for g in line]
        phone = [gid(c) for c in "010"]
        k = next(i for i in range(len(mixed)) if mixed[i:i + 3] == phone)
        self.assertEqual(mixed[k:k + 13], [gid(c) for c in "010 1234 5678"])   # as dialled
        ar = table["ar"]["glyphs"]
        line = next(g for g in ar if gid("٥") in g)
        self.assertEqual(line[line.index(gid("٥")):line.index(gid("٥")) + 3], [gid("٥"), gid("٠"), gid("٠")])
        self.assertEqual(table["block"]["lines"][-1], "2024 500 مرة")
        last = table["block"]["glyphs"][-1]                       # «2024» left of «500»: one run (W7 of the block)
        self.assertEqual(last[-8:], [gid(c) for c in "2024 500"])


if __name__ == "__main__":
    unittest.main()
