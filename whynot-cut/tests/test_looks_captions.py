# SPDX-License-Identifier: GPL-3.0-or-later
# © 2026 The Why Not AI (thewhynot.ai)
"""Phase 4 Task 23 (R-4.1): caption looks: digits, grouping, font chain, fit-or-fail, rendering, the gallery.
Spec: docs/superpowers/specs/addendum-h/source-r-specs/R-4.1-caption-looks.md (§4 Arabic first, §6 fit-or-fail).
Run:  tools/test.sh -p test_looks_captions.py
"""
import sys as _sys
_sys.dont_write_bytecode = True  # keep the plugin folder free of __pycache__
import _isolation  # noqa: F401,E402  G79: sandbox the engine home before anything else (see tests/_isolation.py)
import sys
import unittest
from pathlib import Path

SK = Path(__file__).resolve().parents[1]
ROOT = SK.parent
sys.path.insert(0, str(SK / "engine" / "reel"))

from lib import looks_captions as LC  # noqa: E402

AI = "٤٠٪"          # «٤٠٪» as stored: Arabic-Indic 4, 0, then the Arabic percent sign (U+066A)


def W(spec: str, start: int = 0, gap: int = 80, dur: int = 260) -> list[dict]:
    """Timed words from a space-separated string; a token "|N|" inserts an N ms pause before the next word."""
    out, t, extra = [], start, 0
    for tok in spec.split():
        if tok.startswith("|") and tok.endswith("|"):
            extra += int(tok.strip("|"))
            continue
        t += extra
        extra = 0
        out.append({"id": len(out), "word": tok, "start_ms": t, "end_ms": t + dur})
        t += dur + gap
    return out


def texts(cues) -> list[str]:
    return [c["text"] for c in cues]


class TestDigits(unittest.TestCase):
    def test_arabic_indic_inside_arabic_runs(self):
        self.assertEqual(LC.localize_digits("الجرعة 50 مرة في اليوم", "arabic_indic"), "الجرعة ٥٠ مرة في اليوم")
        self.assertEqual(LC.localize_digits("النسبة 3.5 في المية", "arabic_indic"), "النسبة ٣٫٥ في المية")
        self.assertEqual(LC.localize_digits("دفعنا 12,000 جنيه", "arabic_indic"), "دفعنا ١٢٬٠٠٠ جنيه")

    def test_percent_is_stored_digits_first_then_u066a(self):
        out = LC.localize_digits("بنسبة 40% تقريبا", "arabic_indic")
        self.assertEqual(out, "بنسبة " + AI + " تقريبا")
        self.assertEqual([hex(ord(c)) for c in out.split()[1]], ["0x664", "0x660", "0x66a"])

    def test_latin_names_handles_urls_versions_never_change(self):
        for keep in ("GPT-4o", "@brand2024", "v3.0", "https://x.com/a1", "file_2.mp4", "name1@mail.com", "3.0.1"):
            line = f"جربنا {keep} امبارح"
            self.assertEqual(LC.localize_digits(line, "arabic_indic"), line, keep)

    def test_a_number_beside_a_latin_term_stays_western(self):
        line = "استخدمت iPhone 15 Pro النهارده"
        self.assertEqual(LC.localize_digits(line, "arabic_indic"), line)

    def test_an_english_line_never_changes(self):
        self.assertEqual(LC.localize_digits("it costs 50 dollars, 40%", "arabic_indic"), "it costs 50 dollars, 40%")

    def test_western_mode_turns_arabic_indic_back(self):
        self.assertEqual(LC.localize_digits("الجرعة ٥٠ مرة و ٣٫٥ و " + AI, "western"), "الجرعة 50 مرة و 3.5 و 40%")

    def test_unknown_digit_set_is_a_noop(self):
        self.assertEqual(LC.localize_digits("الجرعة 50", None), "الجرعة 50")


class TestGlue(unittest.TestCase):
    def test_number_and_unit_latin_runs_and_al_latin_stay_together(self):
        g = LC.glued(W("عندي 50 ملغ من insulin resistance و ال MRI كمان"))
        self.assertEqual([" ".join(x["word"] for x in grp) for grp in g],
                         ["عندي", "50 ملغ", "من", "insulin resistance", "و", "ال MRI", "كمان"])

    def test_a_latin_name_and_its_number_stay_together(self):
        g = LC.glued(W("الجديد iPhone 15 حلو"))
        self.assertEqual([len(x) for x in g], [1, 2, 1])

    def test_a_model_name_with_its_number_and_suffix_is_one_group(self):
        g = LC.glued(W("اشتريت iPhone 15 Pro Max امبارح"))
        self.assertEqual([len(x) for x in g], [1, 4, 1])

    def test_a_name_its_number_and_a_unit_stay_together_when_both_rules_apply(self):
        # no word-level signal tells "covid 19 | سنة" from "Pro Max | 15 سنة": gluing all removes a break point and
        # never makes a wrong split (fit-or-fail handles the longer run)
        g = LC.glued(W("من covid 19 سنة"))
        self.assertEqual([" ".join(x["word"] for x in grp) for grp in g], ["من", "covid 19 سنة"])
        g = LC.glued(W("عنده Pro Max 15 سنة"))
        self.assertEqual([" ".join(x["word"] for x in grp) for grp in g], ["عنده", "Pro Max 15 سنة"])
        g = LC.glued(W("عندي 15 سنة و 40 mg"))
        self.assertEqual([" ".join(x["word"] for x in grp) for grp in g], ["عندي", "15 سنة", "و", "40 mg"])

    def test_a_latin_run_after_a_number_still_stops_at_three_latin_words(self):
        g = LC.glued(W("قال model 3 is very good جدا"))
        self.assertEqual([len(x) for x in g], [1, 4, 1, 1])          # model 3 is very | good | جدا

    def test_english_speech_is_not_one_unbreakable_run(self):
        g = LC.glued(W("this is 50 mg today"))
        self.assertEqual([len(x) for x in g], [1, 1, 2, 1])

    def test_a_latin_term_is_at_most_three_words_and_never_crosses_punctuation(self):
        g = LC.glued(W("قال we can do this together يعني"))
        self.assertEqual([len(x) for x in g], [1, 3, 2, 1])
        g = LC.glued(W("قال insulin, resistance كمان"))
        self.assertEqual([len(x) for x in g], [1, 1, 1, 1])


class TestGrouping(unittest.TestCase):
    def test_word_mode_one_word_each_glued_runs_whole(self):
        cues = LC.group_words(W("السكر 50 ملغ insulin resistance خلاص"), "word")
        self.assertEqual(texts(cues), ["السكر", "50 ملغ", "insulin resistance", "خلاص"])
        self.assertEqual([c["words"][0]["id"] for c in cues], [0, 1, 3, 5])

    def test_phrase_mode_two_to_four_words(self):
        cues = LC.group_words(W("واحد اتنين تلاتة اربعة خمسة ستة سبعة"), "phrase")
        self.assertTrue(all(2 <= len(c["words"]) <= 4 for c in cues), texts(cues))
        self.assertEqual(" ".join(texts(cues)), "واحد اتنين تلاتة اربعة خمسة ستة سبعة")

    def test_phrase_never_crosses_a_pause_or_a_sentence_end(self):
        cues = LC.group_words(W("انا رحت |300| السوق امبارح. وبعدين رجعت"), "phrase")
        self.assertEqual(texts(cues), ["انا رحت", "السوق امبارح.", "وبعدين رجعت"])
        cues = LC.group_words(W("هو جه؟ ايوه جه"), "phrase")
        self.assertEqual(texts(cues), ["هو جه؟", "ايوه جه"])

    def test_a_short_pause_does_not_break_a_phrase(self):
        self.assertEqual(texts(LC.group_words(W("انا رحت |150| السوق"), "phrase")), ["انا رحت السوق"])

    def test_line_mode_breaks_at_arabic_clause_marks(self):
        for mark in ("،", "؛", "؟"):
            cues = LC.group_words(W(f"الكلام ده مهم{mark} وبعدين نكمل الشرح"), "line")
            self.assertEqual(texts(cues), [f"الكلام ده مهم{mark}", "وبعدين نكمل الشرح"], mark)

    def test_line_mode_breaks_at_a_350ms_pause_not_at_250(self):
        self.assertEqual(texts(LC.group_words(W("الكلام ده |260| مهم جدا"), "line")), ["الكلام ده مهم جدا"])
        self.assertEqual(texts(LC.group_words(W("الكلام ده |360| مهم جدا"), "line")), ["الكلام ده", "مهم جدا"])

    def test_english_and_mixed_lines(self):
        self.assertEqual(texts(LC.group_words(W("this is important, then we go on"), "line")),
                         ["this is important,", "then we go on"])
        cues = LC.group_words(W("الـ insulin resistance بتعمل كده"), "phrase")
        self.assertIn("insulin resistance", cues[0]["text"])

    def test_times_follow_the_words_and_never_overlap(self):
        cues = LC.group_words(W("واحد اتنين |400| تلاتة اربعة"), "phrase")
        self.assertEqual(cues[0]["start_ms"], 0)
        self.assertEqual(cues[0]["end_ms"], cues[0]["words"][-1]["end_ms"])
        for a, b in zip(cues, cues[1:]):
            self.assertLessEqual(a["end_ms"], b["start_ms"])

    def test_a_very_short_word_cue_is_held_to_the_minimum_without_overlap(self):
        ws = W("لا", dur=60) + W("ابدا", start=400)
        cues = LC.group_words(ws, "word")
        self.assertGreaterEqual(cues[0]["end_ms"] - cues[0]["start_ms"], 160)
        self.assertLessEqual(cues[0]["end_ms"], cues[1]["start_ms"])

    def test_empty_words_are_skipped(self):
        ws = W("واحد اتنين")
        ws.insert(1, {"id": 99, "word": "", "start_ms": 300, "end_ms": 310})
        self.assertEqual(texts(LC.group_words(ws, "phrase")), ["واحد اتنين"])


class TestEmphasisAndHidden(unittest.TestCase):
    def test_highlight_phrases_mark_word_indices(self):
        cues = LC.group_words(W("قلل السُّكَّر الأبيض النهارده"), "line")
        LC.mark_emphasis(cues, ["السكر الابيض"])
        self.assertEqual(cues[0]["emphasis"], [1, 2])

    def test_no_match_no_emphasis(self):
        cues = LC.group_words(W("قلل الملح"), "line")
        LC.mark_emphasis(cues, ["السكر"])
        self.assertEqual(cues[0]["emphasis"], [])

    def test_words_under_a_graphic_are_never_shown_twice(self):
        cues = LC.group_words(W("واحد اتنين تلاتة اربعة"), "line")        # one cue 0..1300 ms
        out = LC.apply_hidden(cues, [(300, 700)], "line")
        self.assertEqual(texts(out), ["واحد", "تلاتة اربعة"])
        self.assertEqual(LC.apply_hidden(cues, [(0, 5000)], "line"), [])

    def test_lead_in_never_steps_into_a_hidden_range(self):
        cues = LC.group_words(W("واحد |900| اتنين تلاتة"), "phrase")
        b = cues[1]["start_ms"]
        out = LC.apply_lead_in(cues, 300, hidden=[(b - 400, b - 100)])
        self.assertEqual(out[1]["start_ms"], b - 100)

    def test_a_line_never_runs_longer_than_its_max_time(self):
        cues = LC.group_words(W(" ".join(["كلمة"] * 30)), "line")      # 30 words, 10 s, no pause, no punctuation
        self.assertGreater(len(cues), 1)
        self.assertTrue(all(c["end_ms"] - c["start_ms"] <= 5500 for c in cues))

    def test_lead_in_never_over_the_previous_caption(self):
        cues = LC.group_words(W("واحد اتنين |500| تلاتة اربعة"), "phrase")
        out = LC.apply_lead_in(cues, 200)
        self.assertEqual(out[1]["start_ms"], max(cues[0]["end_ms"], cues[1]["start_ms"] - 200))
        self.assertEqual(out[0]["start_ms"], 0)


FONTS = ROOT / "guide-ar" / "fonts"          # OFL fonts kept in the repo: the same pixels on every machine
PLEX = FONTS / "ibmplexsansarabic" / "IBMPlexSansArabic-Regular.ttf"
PLEX_SB = FONTS / "ibmplexsansarabic" / "IBMPlexSansArabic-SemiBold.ttf"
INTER = FONTS / "inter" / "Inter-Regular.ttf"
INTER_B = FONTS / "inter" / "Inter-Bold.ttf"
SYNE = FONTS / "syne" / "Syne-Bold.ttf"                 # Latin only: forces the Arabic fallback
ALEX = FONTS / "alexandria" / "Alexandria-Bold.ttf"     # Arabic + Latin


def face(path: Path, ps: str, family: str = "Brand", style: str = "Bold", weight: int = 700) -> dict:
    return {"file": str(path), "index": 0, "ps": ps, "family": family, "style": style, "weight": weight}


HOUSE = {"arabic": [face(PLEX_SB, "IBMPlexSansArabic-SemiBold", "House Arabic", "SemiBold", 600)],
         "latin": [face(INTER, "Inter-Regular", "House Latin", "Regular", 400)]}


def typography(*rows, roles=None) -> dict:
    """typography.json with one family per (family, [(style, file, ps)]) row."""
    fams = {}
    for fam, weights in rows:
        fams[fam] = {"weights": [{"style": s, "file": str(f), "postscript_name": ps} for s, f, ps in weights]}
    return {"families": fams, "roles": roles or {}}


def needs_hb(test):
    return unittest.skipUnless(LC.hb_available() and PLEX.exists(), "HarfBuzz or the repo fonts missing")(test)


class TestFontChain(unittest.TestCase):
    @needs_hb
    def test_latin_only_brand_font_gets_the_arabic_house_face(self):
        typ = typography(("Syne", [("Bold", SYNE, "Syne-Bold")]), roles={"caption": "Syne-Bold"})
        ch = LC.font_chain(typ, "caption", house=HOUSE)
        self.assertEqual([f["ps"] for f in ch["latin"]], ["Syne-Bold", "Inter-Regular"])
        self.assertEqual([f["ps"] for f in ch["arabic"]], ["IBMPlexSansArabic-SemiBold"])

    @needs_hb
    def test_an_arabic_brand_face_with_latin_glyphs_draws_latin_before_the_house(self):
        typ = typography(("Syne", [("Bold", SYNE, "Syne-Bold")]), ("Alexandria", [("Bold", ALEX, "Alexandria-Bold")]),
                         roles={"caption": "Syne-Bold", "body": "Alexandria-Bold"})
        ch = LC.font_chain(typ, "caption", house=HOUSE)
        self.assertEqual([f["ps"] for f in ch["arabic"]], ["Alexandria-Bold", "IBMPlexSansArabic-SemiBold"])
        self.assertEqual([f["ps"] for f in ch["latin"]], ["Syne-Bold", "Alexandria-Bold", "Inter-Regular"])

    @needs_hb
    def test_a_look_fallback_sits_before_the_house(self):
        typ = typography(("Syne", [("Bold", SYNE, "Syne-Bold")]), roles={"caption": "Syne-Bold"})
        ch = LC.font_chain(typ, "caption", house=HOUSE, look_fallback=face(ALEX, "Alexandria-Bold", "Alexandria"))
        self.assertEqual([f["ps"] for f in ch["arabic"]], ["Alexandria-Bold", "IBMPlexSansArabic-SemiBold"])

    @needs_hb
    def test_weight_step_finds_the_next_heavier_face_in_the_family(self):
        typ = typography(("Plex", [("Regular", PLEX, "IBMPlexSansArabic-Regular"),
                                   ("SemiBold", PLEX_SB, "IBMPlexSansArabic-SemiBold")]),
                         roles={"caption": "IBMPlexSansArabic-Regular"})
        ch = LC.font_chain(typ, "caption", house=HOUSE, weight_step=200)
        self.assertEqual(ch["arabic"][0]["ps"], "IBMPlexSansArabic-SemiBold")
        top = LC.font_chain(typ, "caption", house=HOUSE, weight_step=200)
        top2 = LC.font_chain(typography(("Plex", [("SemiBold", PLEX_SB, "IBMPlexSansArabic-SemiBold")]),
                                        roles={"caption": "IBMPlexSansArabic-SemiBold"}), "caption", house=HOUSE,
                             weight_step=200)
        self.assertEqual(top2["arabic"][0]["ps"], "IBMPlexSansArabic-SemiBold")    # already the heaviest: same face
        self.assertTrue(top2.get("notes"))


class TestLayout(unittest.TestCase):
    def setUp(self):
        if not (LC.hb_available() and PLEX.exists()):
            self.skipTest("HarfBuzz or the repo fonts missing")
        typ = typography(("Syne", [("Bold", SYNE, "Syne-Bold")]), roles={"caption": "Syne-Bold"})
        self.ts = LC.Typesetter(LC.font_chain(typ, "caption", house=HOUSE), 60)

    def test_mixed_line_shapes_each_run_with_its_own_font(self):
        ln = self.ts.line(["عندي", "insulin", "resistance"])
        faces = [[s["ps"] for s in it["segments"]] for it in ln["items"]]
        self.assertEqual(faces, [["IBMPlexSansArabic-SemiBold"], ["Syne-Bold"], ["Syne-Bold"]])
        self.assertTrue(ln["rtl"])
        self.assertEqual(ln["missing"], [])

    def test_rtl_visual_order_words_and_numbers(self):
        ln = self.ts.line(["عندي", "50", "سنة"])
        x = {it["text"]: it["x"] for it in ln["items"]}
        self.assertGreater(x["عندي"], x["50"])
        self.assertGreater(x["50"], x["سنة"])
        ln = self.ts.line(["استخدمت", "iPhone", "15", "Pro"])
        x = {it["text"]: it["x"] for it in ln["items"]}
        self.assertLess(x["iPhone"], x["15"])
        self.assertLess(x["15"], x["Pro"])
        self.assertGreater(x["استخدمت"], x["Pro"])

    def test_a_number_after_a_latin_word_joins_its_run(self):
        x = {it["text"]: it["x"] for it in self.ts.line(["الجديد", "iPhone", "15"])["items"]}
        self.assertLess(x["iPhone"], x["15"])
        self.assertLess(x["15"], x["الجديد"])
        x = {it["text"]: it["x"] for it in self.ts.line(["iPhone", "15", "جديد"])["items"]}
        self.assertLess(x["جديد"], x["iPhone"])
        self.assertLess(x["iPhone"], x["15"])

    def test_a_missing_mark_is_reported_never_a_box(self):
        w = self.ts.word("ب࣓ا")                 # a mark no font in the chain has
        self.assertEqual(w["missing"], ["U+08D3"])
        self.assertTrue(all(g[0] != 0 for s in w["segments"] for g in s["glyphs"]))

    def test_english_line_is_left_to_right(self):
        ln = self.ts.line(["this", "is", "fine"])
        self.assertFalse(ln["rtl"])
        xs = [it["x"] for it in ln["items"]]
        self.assertEqual(xs, sorted(xs))

    def test_arabic_indic_digits_keep_left_to_right_order(self):
        font = self.ts.engine.font(HOUSE["arabic"][0], 60)
        g4 = self.ts.engine.shape("٤", "ltr", font)[0][0]
        g0 = self.ts.engine.shape("٠", "ltr", font)[0][0]
        segs = self.ts.word("٤٠")["segments"]
        self.assertEqual([g[0] for s in segs for g in s["glyphs"]], [g4, g0])
        segs = self.ts.word(AI)["segments"]                      # «٤٠٪»: the percent sign sits left of the number
        gp = self.ts.engine.shape("٪", "rtl", font)[0][0]
        self.assertEqual([g[0] for s in segs for g in s["glyphs"]], [gp, g4, g0])

    def test_missing_glyph_moves_the_run_to_the_next_font(self):
        w = self.ts.word("ЖЖ")                    # Syne has no Cyrillic; the house Latin face has
        self.assertEqual([s["ps"] for s in w["segments"]], ["Inter-Regular"])
        self.assertEqual(w["missing"], [])

    def test_a_glyph_no_font_has_is_reported_as_u_plus(self):
        w = self.ts.word("漢字")
        self.assertEqual(sorted(w["missing"]), ["U+5B57", "U+6F22"])
        self.assertTrue(all(g[0] != 0 for s in w["segments"] for g in s["glyphs"]))    # never a .notdef box

    def test_line_width_is_words_plus_spaces(self):
        a, b = self.ts.word("مهم")["w"], self.ts.word("جدا")["w"]
        ln = self.ts.line(["مهم", "جدا"])
        self.assertAlmostEqual(ln["w"], a + b + ln["space"], places=3)


class TestFit(unittest.TestCase):
    def setUp(self):
        if not (LC.hb_available() and PLEX.exists()):
            self.skipTest("HarfBuzz or the repo fonts missing")
        typ = typography(("Plex", [("SemiBold", PLEX_SB, "IBMPlexSansArabic-SemiBold")]),
                         roles={"caption": "IBMPlexSansArabic-SemiBold"})
        self.chain = LC.font_chain(typ, "caption", house=HOUSE)

    def fit(self, cues, look="line-clean", safe=900, frame_w=1080):
        return LC.fit_cues(cues, look, self.chain, frame_w=frame_w, safe_w=safe)

    def test_a_line_that_fits_is_untouched(self):
        cues = LC.group_words(W("الكلام ده مهم"), "line")
        out, notes = self.fit(cues)
        self.assertEqual(texts(out), ["الكلام ده مهم"])
        self.assertEqual(notes, [])
        self.assertEqual(out[0]["size"], 72)

    def test_a_wide_line_is_regrouped_at_a_conjunction_then_the_middle(self):
        cues = LC.group_words(W("احنا النهارده هنتكلم عن موضوع مهم جدا لكن محتاجين نركز كويس عشان نفهمه"), "line")
        out, notes = self.fit(cues, safe=700)
        self.assertGreater(len(out), 1)
        self.assertTrue(any(c["text"].startswith("لكن") for c in out), texts(out))
        self.assertEqual(" ".join(texts(out)), cues[0]["text"])
        ts = LC.Typesetter(self.chain, 72)
        self.assertTrue(all(ts.line([w["text"] for w in c["words"]])["w"] <= 700 for c in out))
        self.assertTrue(any(n["kind"] == "regrouped" for n in notes))
        for a, b in zip(out, out[1:]):
            self.assertEqual(a["end_ms"], b["start_ms"])           # no blank frames between the parts

    def test_regroup_prefers_the_longest_pause(self):
        cues = [LC._cue([[w] for w in W("واحد اتنين تلاتة |200| اربعة خمسة ستة سبعة تمانية")])]
        out, _ = self.fit(cues, safe=520)
        self.assertEqual(out[0]["text"].split()[-1], "تلاتة")

    def test_a_single_run_shrinks_in_2px_steps_down_to_the_floor(self):
        cues = LC.group_words(W("الاستراتيجيات"), "word")
        ts = LC.Typesetter(self.chain, 84)
        w84 = ts.line(["الاستراتيجيات"])["w"]
        out, notes = self.fit(cues, look="word-clean", safe=int(w84 * 0.93))
        self.assertLess(out[0]["size"], 84)
        self.assertEqual((84 - out[0]["size"]) % 2, 0)
        self.assertGreaterEqual(out[0]["size"], LC.floor_px(84, 1080))
        self.assertTrue(any(n["kind"] == "shrunk" for n in notes))

    def test_still_too_wide_at_the_floor_hides_that_caption_and_names_the_cue(self):
        cues = LC.group_words(W("واحد |900| الاستراتيجيات"), "word")
        out, notes = self.fit(cues, look="word-clean", safe=100)
        hid = [n for n in notes if n["kind"] == "hidden"]
        self.assertEqual(len(hid), 2)
        self.assertTrue(all("too long for one line" in n["message"] for n in hid))
        self.assertTrue(all(c.get("hidden") for c in out))
        self.assertEqual(hid[1]["at_ms"], cues[1]["start_ms"])

    def test_floor_is_085_of_the_size_never_below_44_at_1080(self):
        self.assertAlmostEqual(LC.floor_px(84, 1080), 71.4)
        self.assertAlmostEqual(LC.floor_px(50, 1080), 44)
        self.assertAlmostEqual(LC.floor_px(50, 720), 44 * 720 / 1080)

    def test_missing_glyphs_are_plan_notices_with_the_cue_time(self):
        cues = LC.group_words(W("كلمة 漢 تانية", start=1500), "line")
        _, notes = self.fit(cues)
        miss = [n for n in notes if n["kind"] == "missing_glyph"]
        self.assertEqual([n["char"] for n in miss], ["U+6F22"])
        self.assertEqual(miss[0]["at_ms"], 1500)

    def test_size_scales_with_the_frame_width(self):
        out, _ = self.fit(LC.group_words(W("مهم"), "line"), frame_w=720, safe=600)
        self.assertEqual(out[0]["size"], 48)

    def test_emphasis_weight_and_tag_are_measured(self):
        cues = LC.group_words(W("ده مهم جدا"), "line")
        cues[0]["emphasis"] = [1]
        ts = LC.Typesetter(self.chain, 72)
        plain = ts.line(["ده", "مهم", "جدا"])["w"]
        tagged = ts.line(["ده", "مهم", "جدا"], emphasis={1}, mode="tag")["w"]
        self.assertGreater(tagged, plain)


PAL = {"primary": (0x1F, 0x6F, 0x8B), "accent": (0xE0, 0xA0, 0x00), "highlight": (0xFF, 0xD4, 0x00),
       "ink": (0x14, 0x1C, 0x26), "paper": (0xF4, 0xF0, 0xE8), "white": (0xFF, 0xFF, 0xFF)}


def frame(rgb, size=(1080, 1920)):
    from PIL import Image
    return Image.new("RGBA", size, tuple(rgb) + (255,))


def alpha_box(im):
    return im.getchannel("A").getbbox()


class PaintCase(unittest.TestCase):
    def setUp(self):
        if not (LC.hb_available() and PLEX.exists()):
            self.skipTest("HarfBuzz or the repo fonts missing")
        typ = typography(("Plex", [("Regular", PLEX, "IBMPlexSansArabic-Regular"),
                                   ("SemiBold", PLEX_SB, "IBMPlexSansArabic-SemiBold")]),
                         roles={"caption": "IBMPlexSansArabic-Regular"})
        self.chain = LC.font_chain(typ, "caption", house=HOUSE)
        self.heavy = LC.font_chain(typ, "caption", house=HOUSE, weight_step=200)

    def painter(self, look, emphasis="colour", **kw):
        return LC.CaptionPainter(look, self.chain, PAL, heavy=self.heavy, emphasis=emphasis, **kw)

    def cue(self, text="الكلام ده مهم جدا", emphasis=()):
        c = LC.group_words(W(text), "line")[0]
        c["emphasis"] = list(emphasis)
        c["size"] = None
        return c


class TestPaint(PaintCase):
    def test_boxed_has_an_ink_plate_with_an_accent_foot(self):
        lay = self.painter("line-boxed").layers(self.cue())
        plate = lay["plate"]
        x0, y0, x1, y1 = alpha_box(plate)
        mid = plate.getpixel(((x0 + x1) // 2, (y0 + y1) // 2))
        foot = plate.getpixel(((x0 + x1) // 2, y1 - 2))
        self.assertLess(sum(abs(a - b) for a, b in zip(mid[:3], PAL["ink"])), 30)
        self.assertLess(sum(abs(a - b) for a, b in zip(foot[:3], PAL["accent"])), 30)
        tx0, ty0, tx1, ty1 = alpha_box(lay["fg"])
        self.assertTrue(x0 < tx0 and tx1 < x1 and y0 < ty0 and ty1 < y1)     # the text sits inside its plate

    def test_the_boxed_plate_is_squared_not_a_rounded_pill(self):
        plate = self.painter("line-boxed").layers(self.cue())["plate"]
        x0, y0, x1, y1 = alpha_box(plate)
        for x, y in ((x0 + 2, y0 + 2), (x1 - 3, y0 + 2)):
            self.assertGreater(plate.getpixel((x, y))[3], 200, "corner radius grew: our plate is squared (R-4.1 §1)")

    def test_clean_has_a_soft_drop_plate_below_the_text_and_no_stroke(self):
        lay = self.painter("line-clean").layers(self.cue())
        a = lay["plate"].getchannel("A")
        self.assertLessEqual(max(a.getdata()), int(255 * 0.35) + 1)
        self.assertGreater(alpha_box(lay["plate"])[3], alpha_box(lay["fg"])[3])     # reaches below the text
        fg = lay["fg"]
        colours = {fg.getpixel((x, y))[:3] for x in range(0, fg.width, 3) for y in range(*alpha_box(fg)[1::2], 3)
                   if fg.getpixel((x, y))[3] > 250}
        self.assertEqual(colours, {PAL["white"]})                                      # one fill colour: no outline

    def test_highlight_keeps_the_soft_drop_plate_under_its_text(self):
        lay = self.painter("line-highlight").layers(self.cue())
        self.assertIsNotNone(lay["plate"])
        self.assertLessEqual(max(lay["plate"].getchannel("A").getdata()), int(255 * 0.35) + 1)

    def test_highlight_underlay_sits_low_and_spans_each_word_right_to_left(self):
        lay = self.painter("line-highlight").layers(self.cue())
        spans = lay["spans"]
        self.assertEqual([s["i"] for s in spans], [0, 1, 2, 3])
        self.assertTrue(all(s["x0"] < s["x1"] for s in spans))
        self.assertGreater(spans[0]["x0"], spans[-1]["x1"])                # the first word is on the right
        ub = alpha_box(lay["underlay"])
        fb = alpha_box(lay["fg"])
        self.assertGreater(ub[1], (fb[1] + fb[3]) / 2 - 1)                   # it starts low, below the text's middle
        self.assertEqual(spans[1]["start_ms"], lay["cue"]["words"][1]["start_ms"])

    def test_text_is_centred_and_inside_the_safe_width(self):
        lay = self.painter("line-clean").layers(self.cue())
        x0, _, x1, _ = alpha_box(lay["fg"])
        self.assertLess(abs((x0 + x1) / 2 - 540), 6)
        self.assertGreaterEqual(x0, 90)
        self.assertLessEqual(x1, 990)

    def test_colour_emphasis_draws_the_word_in_the_highlight_colour(self):
        lay = self.painter("line-boxed").layers(self.cue(emphasis=[2]))
        sp = lay["word_boxes"][2]
        fg = lay["fg"]
        hits = [fg.getpixel((x, y))[:3] for x in range(int(sp[0]), int(sp[2])) for y in range(int(sp[1]), int(sp[3]))
                if fg.getpixel((x, y))[3] > 250]
        self.assertTrue(hits and all(sum(abs(a - b) for a, b in zip(h, PAL["highlight"])) < 40 for h in hits[:50]))

    def test_colour_emphasis_on_a_bright_frame_is_stepped_or_neutral_with_a_note(self):
        from lib import looks
        from lib.legibility import needed
        from lib.motion_layout import contrast
        lay = self.painter("line-clean").layers(self.cue(emphasis=[2]), frame=frame((250, 250, 245)))
        c = lay["colors"]                              # the scrim carries the brand colour: kept, and it reads
        self.assertTrue(c["scrim"])
        self.assertEqual(c["emphasis"], PAL["highlight"])
        self.assertGreaterEqual(min(contrast(c["emphasis"], b) for b in c["bgs"]) + 1e-6, needed(lay["size"]))
        weak = looks.caption_catalog()
        weak["presentations"]["clean"]["drop_plate"]["max_opacity"] = 0.35  # no stronger plate: the colour steps
        lay = LC.CaptionPainter("line-clean", self.chain, PAL, cat=weak).layers(self.cue(emphasis=[2]),
                                                                                frame=frame((250, 250, 245)))
        self.assertNotEqual(lay["colors"]["emphasis"], PAL["highlight"])
        self.assertTrue(any("الكلمة المميزة" in n for n in lay["notes"]))

    def test_the_emphasis_note_names_a_dark_background_on_a_dark_frame(self):
        pal = dict(PAL, highlight=(70, 50, 20))
        lay = LC.CaptionPainter("line-clean", self.chain, pal, heavy=self.heavy).layers(self.cue(emphasis=[1]),
                                                                                       frame=frame((15, 15, 18)))
        self.assertTrue(any("الغامقة" in n for n in lay["notes"]), lay["notes"])

    def test_white_text_on_a_bright_frame_is_never_left_unreadable(self):
        from lib.legibility import needed
        from lib.motion_layout import contrast
        lay = self.painter("line-clean").layers(self.cue(), frame=frame((250, 250, 245)))
        c = lay["colors"]
        self.assertGreaterEqual(min(contrast(c["text"], b) for b in c["bgs"]), needed(lay["size"]))

    def test_on_a_bright_frame_the_plate_gets_stronger_before_the_text_changes(self):
        lay = self.painter("line-clean").layers(self.cue(), frame=frame((235, 235, 230)))
        self.assertEqual(lay["colors"]["text"], PAL["white"])
        self.assertGreater(lay["colors"]["plate_opacity"], 0.35)
        plain = self.painter("line-clean").layers(self.cue())
        self.assertGreater(max(lay["plate"].getchannel("A").getdata()), max(plain["plate"].getchannel("A").getdata()))

    def test_the_contrast_needed_follows_the_reference_size_not_the_frame_width(self):
        cue = self.cue()
        tall = self.painter("line-boxed").layers(cue, frame=frame((40, 40, 40)))
        wide = LC.CaptionPainter("line-boxed", self.chain, PAL, frame_size=(1920, 1080), heavy=self.heavy).layers(
            cue, frame=frame((40, 40, 40), size=(1920, 1080)))
        self.assertEqual(tall["colors"]["need"], wide["colors"]["need"])

    def test_a_strip_is_judged_by_its_brightest_and_darkest_tenth(self):
        from PIL import ImageDraw
        from lib.looks_paint import _regions
        fr = frame((0, 0, 0))
        ImageDraw.Draw(fr).rectangle((0, 0, 1080, 1000), fill=(255, 255, 255, 255))    # top half white
        got = _regions(fr, (100, 950, 140, 1050))                                    # one strip across the edge
        self.assertIn((255, 255, 255), got)
        self.assertIn((0, 0, 0), got)
        flat = _regions(frame((110, 118, 126)), (100, 950, 220, 1050))
        self.assertEqual(set(flat), {(110, 118, 126)})

    def test_busy_footage_is_judged_by_its_worst_strip_not_its_average(self):
        from PIL import ImageDraw
        fr = frame((0, 0, 0))
        d = ImageDraw.Draw(fr)
        for x in range(0, 1080, 160):                     # white and black bars: the average is a readable grey
            d.rectangle((x, 0, x + 79, 1920), fill=(255, 255, 255, 255))
        from lib import looks
        from lib.legibility import needed
        from lib.motion_layout import contrast
        lay = self.painter("line-clean").layers(self.cue(), frame=fr)
        c = lay["colors"]
        self.assertGreater(c["plate_opacity"], 0.35)                        # judged on the white bars, not the mean
        self.assertGreaterEqual(min(contrast(c["text"], b) for b in c["bgs"]), needed(lay["size"]))
        weak = looks.caption_catalog()
        weak["presentations"]["clean"]["drop_plate"]["max_opacity"] = 0.35  # no stronger plate allowed
        lay = LC.CaptionPainter("line-clean", self.chain, PAL, cat=weak).layers(self.cue(), frame=fr)
        self.assertTrue(any("boxed" in n for n in lay["notes"]), lay["notes"])
        lay = self.painter("line-boxed").layers(self.cue(), frame=fr)
        self.assertEqual(lay["notes"], [])                 # the plate carries it

    BARS = ((255, 230, 0), (0, 200, 60), (0, 230, 255), (255, 255, 255))

    def bars(self):
        from PIL import ImageDraw
        fr = frame((0, 0, 0))
        d = ImageDraw.Draw(fr)
        for k, x in enumerate(range(0, 1080, 120)):
            d.rectangle((x, 0, x + 119, 1920), fill=self.BARS[k % 4] + (255,))
        return fr

    def behind_text(self, painter, lay, fr):
        """The background the text really sits on: plate (and band) composited over the frame, per 40 px strip."""
        from PIL import ImageStat
        # every row of every word that is not the one being spoken: no band, the whole line box
        under = painter.composite(dict(lay, fg=None, underlay=None), state=None, background=fr).convert("RGB")
        x0, y0, x1, y1 = (int(round(v)) for v in lay["box"])
        out = []
        for x in range(x0, x1, 40):      # each strip's brightest tenth: what white letters there really meet
            crop = under.crop((x, y0, min(x1, x + 40), y1))
            px = sorted(crop.getdata(), key=lambda c: 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2])
            top = px[-max(1, len(px) // 10):]
            out.append(tuple(round(sum(c[i] for c in top) / len(top)) for i in range(3)))
        return out

    def test_clean_text_reads_on_bright_bars_judged_on_the_real_pixels(self):
        from lib.legibility import needed
        from lib.motion_layout import contrast
        from lib import looks
        fr = self.bars()
        target = looks.caption_catalog()["presentations"]["clean"]["drop_plate"]["scrim"]["target_contrast"]
        self.assertGreaterEqual(target, 4.5)          # moving footage: a scrim aims past the large-text minimum
        for look in ("line-clean", "phrase-clean", "line-highlight"):
            p = self.painter(look)
            lay = p.layers(self.cue(), frame=fr)
            worst = min(contrast(lay["colors"]["text"], b) for b in self.behind_text(p, lay, fr))
            self.assertGreaterEqual(worst + 0.1, max(target, needed(lay["size"])), look)
            self.assertTrue(lay["colors"]["scrim"], look)

    def test_the_scrim_never_darkens_the_band(self):
        fr = self.bars()
        p = self.painter("line-highlight", emphasis="weight")
        lay = p.layers(self.cue(), frame=fr)
        im = p.composite(dict(lay, fg=None), state=1, background=fr)
        sp = next(x for x in lay["spans"] if x["i"] == 1)
        px = im.getpixel((int((sp["x0"] + sp["x1"]) / 2), int((sp["y0"] + sp["y1"]) / 2)))
        self.assertLess(sum(abs(a - b) for a, b in zip(px[:3], PAL["highlight"])), 24, px)

    def test_the_highlight_scrim_covers_the_descenders_with_no_hard_edge(self):
        fr = self.bars()
        lay = self.painter("line-highlight", emphasis="weight").layers(self.cue(), frame=fr)
        self.assertTrue(lay["colors"]["scrim"])
        a = lay["plate"].getchannel("A")
        x0, y0, x1, _ = lay["box"]
        sp = lay["spans"][0]
        side = int(x0) - 12                              # beside the first word: scrim only, no glyph shadow
        for y in range(int(y0), int(sp["y1"]) + 6):     # the letters' bodies, the band rows and the descenders
            self.assertGreater(a.getpixel((side, y)), 100, f"no scrim at y={y}")

    def test_a_dark_or_mid_frame_keeps_the_soft_drop_plate_only(self):
        for bg in ((30, 30, 34), (110, 118, 126)):
            lay = self.painter("line-clean").layers(self.cue(), frame=frame(bg))
            self.assertFalse(lay["colors"]["scrim"], bg)
            x0, y0, x1, y1 = lay["box"]
            gap = lay["plate"].getpixel((int(x0) - 18, int((y0 + y1) / 2)))[3]    # beside the line: no plate there
            self.assertLess(gap, 8, bg)

    def test_a_tag_in_a_clean_look_stands_on_a_highlight_foot_rule(self):
        from lib import looks
        t = looks.caption_catalog()["emphasis"]["tag"]
        rule = round(float(t["foot_px"]))
        for look, want in (("line-clean", PAL["highlight"]), ("line-highlight", PAL["highlight"]),
                           ("line-boxed", PAL["accent"])):
            lay = self.painter(look, emphasis="tag").layers(self.cue(emphasis=[1]))
            fg = lay["fg"]
            x0, _, x1, _ = lay["word_boxes"][1]
            col = [y for y in range(fg.height) if fg.getpixel((int(x0) + 3, y))[3] == 255]
            bottom = max(col)
            got = fg.getpixel((int(x0) + 3, bottom - rule // 2))[:3]
            self.assertLess(sum(abs(a - b) for a, b in zip(got, want)), 12, (look, got))
            above = fg.getpixel((int(x0) + 3, bottom - rule - 3))[:3]
            self.assertLess(sum(abs(a - b) for a, b in zip(above, PAL["accent"])), 12, (look, above))

    def test_the_tag_is_squared_and_sits_on_the_plates_bottom_line(self):
        lay = self.painter("line-boxed", emphasis="tag").layers(self.cue(emphasis=[1]))
        fg = lay["fg"]
        x0, y0, x1, y1 = lay["word_boxes"][1]
        acc = [(x, y) for x in range(int(x0) - 20, int(x1) + 20) for y in range(int(y0) - 40, int(y1) + 40)
               if 0 <= x < fg.width and 0 <= y < fg.height and fg.getpixel((x, y))[3] == 255
               and sum(abs(a - b) for a, b in zip(fg.getpixel((x, y))[:3], PAL["accent"])) < 12]
        tx0, ty0 = min(x for x, _ in acc), min(y for _, y in acc)
        ty1 = max(y for _, y in acc)
        self.assertGreater(fg.getpixel((tx0 + 2, ty0 + 2))[3], 200, "the tag's corners must stay squared")
        self.assertLessEqual(abs(ty1 - alpha_box(lay["plate"])[3]), 2, "the tag sits on the plate's bottom line")

    def test_tag_emphasis_puts_an_accent_tag_behind_the_word(self):
        lay = self.painter("line-clean", emphasis="tag").layers(self.cue(emphasis=[1]))
        x0, y0, x1, y1 = lay["word_boxes"][1]
        fg = lay["fg"]
        px = fg.getpixel((int(x0) + 3, int((y0 + y1) / 2)))
        self.assertLess(sum(abs(a - b) for a, b in zip(px[:3], PAL["accent"])), 30)
        self.assertEqual(px[3], 255)

    def test_weight_emphasis_uses_the_heavier_face(self):
        lay = self.painter("line-clean", emphasis="weight").layers(self.cue(emphasis=[1]))
        self.assertEqual(lay["faces"][1], ["IBMPlexSansArabic-SemiBold"])
        self.assertEqual(lay["faces"][0], ["IBMPlexSansArabic-Regular"])

    def test_motion_metadata_is_ours(self):
        m = self.painter("line-clean").motion(30)
        self.assertEqual((m["entrance"], m["enter_frames"], m["scale_from"], m["travel_px"], m["exit_frames"]),
                         ("focus_in", 6, 0.96, 0, 4))
        self.assertEqual(self.painter("line-clean").motion(60)["enter_frames"], 12)
        self.assertEqual(self.painter("line-clean", entrance="none").motion(30)["entrance"], "none")
        self.assertEqual(self.painter("line-highlight").motion(30)["underlay_slide_frames"], 4)      # the moving foot: a 4-frame slide (R2 round 5)

    def test_a_card_in_the_caption_band_moves_the_caption(self):
        p = self.painter("line-boxed")
        plain = alpha_box(p.layers(self.cue())["fg"])
        moved = alpha_box(p.layers(self.cue(), avoid=[(0, 5000, plain[1] - 40, plain[3] + 40)])["fg"])
        self.assertTrue(moved[3] < plain[1] - 40 or moved[1] > plain[3] + 40)

    def test_the_band_keeps_the_brand_highlight_colour_on_every_frame(self):
        for bg in ((110, 118, 126), (20, 22, 26), (240, 240, 236), None):
            lay = self.painter("phrase-highlight").layers(self.cue(), frame=frame(bg) if bg else None)
            self.assertEqual(lay["colors"]["underlay"], PAL["highlight"], bg)

    def test_the_moving_foot_sits_under_the_lines_lowest_ink_on_one_y(self):
        # R2 round 5 (designer's pick B): the system's foot rule sliding under the spoken word, never through it
        from lib import looks
        u = looks.caption_catalog()["presentations"]["highlight"]["underlay"]
        for text in ("والإنسولين بيقل جدا", "insulin drops fast", "السكر بيقل ٤٠٪ مع الرياضة"):
            p = self.painter("line-highlight", emphasis="weight")
            lay = p.layers(self.cue(text))
            size = lay["size"]
            ink_bottom = lay["fg"].getchannel("A").getbbox()[3]
            ys = {(round(sp["y0"], 1), round(sp["y1"], 1)) for sp in lay["spans"]}
            self.assertEqual(len(ys), 1, "one y for the whole line: the foot never jumps between words")
            y0, y1 = ys.pop()
            self.assertGreaterEqual(y0, ink_bottom, text)
            low = max(ink_bottom, lay["box"][3])           # the lowest ink, or the font's descender line
            self.assertAlmostEqual(y0, low + u["gap_em"] * size, delta=2.0)
            self.assertAlmostEqual(y1 - y0, u["height_px"], delta=1.0)
            x0, _, x1, _ = alpha_box(lay["underlay"])
            band = lay["underlay"].getpixel(((x0 + x1) // 2, int((y0 + y1) / 2)))
            self.assertEqual(band[:3], PAL["highlight"])
        self.assertEqual(p.ORDER, ("plate", "underlay", "fg"))    # scrim and shadow, then the foot, then the text
        self.assertEqual(p.motion(30)["underlay_slide_frames"], 4)

    def test_the_moving_foot_keeps_its_place_from_caption_to_caption(self):
        # a line with no descenders must not lift the foot: it would jump between cues (R2 round 6)
        p = self.painter("line-highlight", emphasis="weight")
        rel = []
        for text in ("insulin was low", "jumping quickly", "السكر بيقل جدا"):
            lay = p.layers(self.cue(text))
            rel.append(round(lay["spans"][0]["y0"] - lay["baseline"], 1))
        self.assertLessEqual(max(rel) - min(rel), 1.0, rel)

    def test_the_foot_takes_the_clients_highlight_colour_when_one_is_set(self):
        lay = self.painter("line-highlight", emphasis="weight", highlight=(0xE0, 0xB7, 0x6B)).layers(
            self.cue("السكر بيقل جدا"), frame=frame((30, 30, 34)))
        self.assertEqual(lay["colors"]["underlay"], (0xE0, 0xB7, 0x6B))

    def test_a_foot_that_would_vanish_takes_the_next_brand_colour_then_warns(self):
        # the foot carries no text (no G68), but it must show: at least 3:1 against what is behind it
        from lib.motion_layout import contrast
        lay = self.painter("line-highlight", emphasis="weight", highlight=(0x1E, 0x2A, 0x3B)).layers(
            self.cue("السكر بيقل جدا"), frame=frame((30, 30, 34)))
        self.assertEqual(lay["colors"]["underlay"], PAL["highlight"])
        self.assertTrue(any("foot" in n for n in lay["notes"]), lay["notes"])
        grey = (120, 120, 120)
        pal = dict(PAL, highlight=grey, accent=grey, primary=grey)
        lay = LC.CaptionPainter("line-highlight", self.chain, pal, heavy=self.heavy, emphasis="weight").layers(
            self.cue("السكر بيقل جدا"), frame=frame(grey))
        self.assertLess(min(contrast(lay["colors"]["underlay"], b) for b in lay["colors"]["foot_bgs"]), 3.0)
        self.assertTrue(any("no brand colour" in n for n in lay["notes"]), lay["notes"])

    def test_the_clients_highlight_colours_the_emphasis_and_the_tag_rule_too(self):
        client = (0xE0, 0xB7, 0x6B)
        lay = self.painter("line-clean", emphasis="colour", highlight=client).layers(
            self.cue("السكر بيقل جدا", emphasis=[1]), frame=frame((30, 30, 34)))
        self.assertEqual(lay["colors"]["emphasis"], client)
        for look in ("line-clean", "line-highlight"):
            lay = self.painter(look, emphasis="tag", highlight=client).layers(
                self.cue("السكر بيقل جدا", emphasis=[1]), frame=frame((30, 30, 34)))
            fg = lay["fg"]
            x0 = int(lay["word_boxes"][1][0]) + 3
            bottom = max(y for y in range(fg.height) if fg.getpixel((x0, y))[3] == 255)
            want = lay["colors"]["underlay"] if look == "line-highlight" else client
            self.assertEqual(fg.getpixel((x0, bottom - 1))[:3], tuple(want), look)

    def test_the_foot_check_samples_wherever_the_foot_can_land(self):
        p = self.painter("line-highlight", emphasis="weight")
        for text in ("جمـــيل يقلق", "السكر بيقل جدا", "jumping quickly", "insulin was low"):
            lay = p.layers(self.cue(text))
            _, ry0, _, ry1 = p._foot_rows(lay["size"], lay["box"])
            sp = lay["spans"][0]
            self.assertTrue(ry0 <= sp["y0"] and sp["y1"] <= ry1, (text, (ry0, ry1), (sp["y0"], sp["y1"])))
            self.assertGreaterEqual(ry1 - ry0, 0.25 * lay["size"])

    def test_a_t42_highlight_that_is_not_a_colour_is_ignored(self):
        for style in (None, {"highlight": None}, {"highlight": "#E0B76B"}, {"highlight": {"hex": "brand"}}, "x"):
            self.assertIsNone(LC._t42_highlight({"style": style}), style)

    def test_a_word_with_no_ink_still_gets_a_foot(self):
        lay = self.painter("line-highlight", emphasis="weight").layers(self.cue("السكر 漢 جدا"))
        for sp in lay["spans"]:
            self.assertGreater(sp["x1"] - sp["x0"], 4, sp)

    def test_the_moving_foot_spans_the_words_ink_plus_a_little(self):
        from lib import looks
        pad = looks.caption_catalog()["presentations"]["highlight"]["underlay"]["pad_em"]
        lay = self.painter("line-highlight", emphasis="weight").layers(self.cue("insulin drops fast"))
        a = lay["fg"].getchannel("A")
        for sp in lay["spans"]:
            wx0, _, wx1, _ = lay["word_boxes"][sp["i"]]
            cols = [x for x in range(int(wx0) - 4, int(wx1) + 4) if any(a.getpixel((x, y)) > 128 for y in range(a.height // 2 - 300, a.height // 2 + 300))]
            self.assertAlmostEqual(sp["x0"], min(cols) - pad * lay["size"], delta=2.5)
            self.assertAlmostEqual(sp["x1"], max(cols) + 1 + pad * lay["size"], delta=2.5)

    def test_a_tag_and_the_moving_foot_share_one_bottom_line(self):
        lay = self.painter("line-highlight", emphasis="tag").layers(self.cue("السكر بيقل جدا", emphasis=[1]))
        fg = lay["fg"]
        x0, _, _, _ = lay["word_boxes"][1]
        col = [y for y in range(fg.height) if fg.getpixel((int(x0) + 3, y))[3] == 255]
        sp = lay["spans"][0]
        self.assertAlmostEqual(max(col) + 1, sp["y1"], delta=1.5)

    def test_the_moving_foot_never_crosses_a_stroke(self):
        # Arabic letters join ON the baseline and their dots and bowls hang under it: a band in that zone crossed 23 %
        # of a regular word's ink and read as a broken squiggle (graphic check, 2026-10-17). The foot crosses none:
        # AR and EN, regular and bold (the weight emphasis), lam-alef, kashida and deep descenders included.
        cases = (("والإنسولين بيقل جدا", 1), ("السكر بيقل جدا", 0), ("لا الإسلام كلام", 0), ("جمـــيل يقلق", 0),
                 ("قيمة الغذاء", 1), ("insulin drops fast", 1), ("jumping quickly", 0),
                 ("بِنتٍ جِيبي", 0), ("يجيب بيبي", 1), ("فِي بيتٍ", 1))         # dots below, kasra, tanwin kasr
        for text, i in cases:
            for emph in ([], [i]):
                lay = self.painter("line-highlight", emphasis="weight").layers(self.cue(text, emphasis=emph))
                a = lay["fg"].getchannel("A")
                for sp in lay["spans"]:
                    crossing = [1 for x in range(int(sp["x0"]), int(sp["x1"]) + 1)
                                for y in range(int(sp["y0"]), int(round(sp["y1"])) + 1) if a.getpixel((x, y)) > 0]
                    self.assertEqual(crossing, [], (text, emph, sp["i"]))

    def test_colour_emphasis_on_a_moving_band_becomes_a_weight_step(self):
        p = self.painter("phrase-highlight", emphasis="colour")
        self.assertEqual(p.emphasis, "weight")
        self.assertTrue(any("weight" in n for n in p.notes))

    def test_a_tagged_word_hides_the_band_behind_its_tag(self):
        lay = self.painter("line-highlight", emphasis="tag").layers(self.cue(emphasis=[1]))
        sp = next(s for s in lay["spans"] if s["i"] == 1)
        x0, y0, x1, y1 = lay["word_boxes"][1]
        self.assertGreaterEqual(sp["x0"], x0 - 0.5)
        self.assertLessEqual(sp["x1"], x1 + 0.5)

    def test_english_line_reads_left_to_right(self):
        lay = self.painter("line-highlight").layers(self.cue("this is fine"))
        self.assertLess(lay["spans"][0]["x1"], lay["spans"][-1]["x0"])


GOLDEN_TEXT = {"word": "السكر", "phrase": "الـ insulin بيقل ٤٠٪", "line": "السكر بيقل ٤٠٪ مع الرياضة"}
GOLDEN_EMPHASIS = {"word-clean": "colour", "word-boxed": "colour", "phrase-clean": "colour", "phrase-boxed": "tag",
                   "phrase-highlight": "colour", "line-clean": "weight", "line-boxed": "colour", "line-highlight": "tag"}
GRID = (54, 8)
GOLDEN_BG = (110, 118, 126)          # mid grey: plates, bands, text and colours all show against it


def signature(painter, name: str, bg=GOLDEN_BG) -> str:
    """A coarse picture of one look (golden still, R-4.1 acceptance): the caption band of a fixed cue on a fixed
    frame, averaged into GRID cells, each cell's R, G, B in 16 levels (three hex digits). Coarse on purpose: FreeType
    versions differ by sub-pixels between machines; layout, plates, colours and emphasis do not."""
    from PIL import Image
    cue = LC.group_words(W(GOLDEN_TEXT[name.split("-")[0]]), "line")[0]
    cue["emphasis"] = [1] if len(cue["words"]) > 1 else [0]
    cue["size"] = None
    lay = painter.layers(cue, frame=frame(bg))
    im = painter.composite(lay, state=1 if len(cue["words"]) > 1 else 0, background=frame(bg)).convert("RGB")
    y = int((lay["box"][1] + lay["box"][3]) / 2)
    band = im.crop((0, y - 80, 1080, y + 80)).resize(GRID, Image.BOX)
    return "".join("%x%x%x" % (r // 16, g // 16, b // 16) for r, g, b in band.getdata())


def sig_distance(a: str, b: str) -> float:
    """The share of cells where some channel moved by 3 levels (of 16) or more."""
    cells = lambda s: [tuple(int(c, 16) for c in s[i:i + 3]) for i in range(0, len(s), 3)]
    ca, cb = cells(a), cells(b)
    bad = sum(1 for x, y in zip(ca, cb) if max(abs(p - q) for p, q in zip(x, y)) >= 3)
    return (bad + abs(len(ca) - len(cb))) / max(len(ca), len(cb), 1)


GOLDEN = {          # reviewed on the sheet 2026-10-17 after R2 round 5 (moving foot, scrim; looks track); regenerate only after a reviewed look change
    # M2-T4 hook (Task 56): phrase-boxed and phrase-highlight regenerated: their Latin word is drawn at the font pair's
    # latin_scale (Plex 0.7248), its x-height on the Arabic body (the before/after sheet travels with the patch)
    "word-clean": (
        "677677677677677677677677677677677677677677677677677677677677677677677677677677677677677677677677677677677677"
        "677677677677677677677677677677677677677677677677677677677677677677677677677677677677677677677677677677677677"
        "677677677677677677677677677677677677677677677677677677677677677677677677677677677677677677677677677677677677"
        "677677677677677677677677677677677677677677677677677677677677677677677677886995677677677886885777677677677677"
        "677677677677677677677677677677677677677677677677677677677677677677677677677677677677677677677677677677677677"
        "677677677677677677a94677677677677886984777677677677677677677677677677677677677677677677677677677677677677677"
        "677677677677677677677677677677677677677677677677677677677677677677677885994776886885885885984777677677677677"
        "677677677677677677677677677677677677677677677677677677677677677677677677677677677677677677677677677677677677"
        "677677677677677a93885985985985985994776777677677677677677677677677677677677677677677677677677677677677677677"
        "677677677677677677677677677677677677677677677677677677677677677677885777677677677677677677677677677677677677"
        "677677677677677677677677677677677677677677677677677677677677677677677677677677677677677677677677677677677677"
        "677677677677677677677677677677677677677677677677677677677677677677677677677677677677677677677677677677677677"
    ),
    "word-boxed": (
        "677677677677677677677677677677677677677677677677677677677677677556344344344344344344344344344344556677677677"
        "677677677677677677677677677677677677677677677677677677677677677677677677677677677677677677677677677677677677"
        "677677677445122122122122122122122122122122445677677677677677677677677677677677677677677677677677677677677677"
        "677677677677677677677677677677677677677677677677677677677677677445122122222651122122122442442122445677677677"
        "677677677677677677677677677677677677677677677677677677677677677677677677677677677677677677677677677677677677"
        "677677677445122122761122122122122552552122445677677677677677677677677677677677677677677677677677677677677677"
        "677677677677677677677677677677677677677677677677677677677677677445122442651442442442552651552122445677677677"
        "677677677677677677677677677677677677677677677677677677677677677677677677677677677677677677677677677677677677"
        "677677677445122761552542552552552552332122445677677677677677677677677677677677677677677677677677677677677677"
        "677677677677677677677677677677677677677677677677677677677677677445332232122122122122122122122122445677677677"
        "677677677677677677677677677677677677677677677677677677677677677677677677677677677677677677677677677677677677"
        "677677677775973973973973973973973973973973775677677677677677677677677677677677677677677677677677677677677677"
    ),
    "phrase-clean": (
        "677677677677677677677677677677677677677677677677677677677677677677677677677677677677677677677677677677677677"
        "677677677677677677677677677677677677677677677677677677677677677677677677677677677677677677677677677677677677"
        "677677677677677677677677677677677677677677677677677677677677677677677677677677677677677677677677677677677677"
        "677677677677677677677677677677677677677677677677677677677677677778778778677677777777677677677677777777677677"
        "677778778677677677677677677677677677677677677677677677677677677677677677677677677677677677677677677788889899"
        "77867767777889999a677778776885885886776786995885886885677899899677677677677677677677677677677677677677677677"
        "677677677677677677677677677677677677677677677788889aaa899788788778aabaaa9aa999886984885885885994a94994885885"
        "77899a899677677677677677677677677677677677677677677677677677677677677677677677677677677677677677677777777778"
        "77767789999a788677889788677677677777677777677777677677677777677677677677677677677677677677677677677677677677"
        "677677677677677677677677677677677677677677677677677677677677677677677677677677677677677677677677677677677677"
        "677677677677677677677677677677677677677677677677677677677677677677677677677677677677677677677677677677677677"
        "677677677677677677677677677677677677677677677677677677677677677677677677677677677677677677677677677677677677"
    ),
    "phrase-boxed": (
        "677677677677677677677677677677677677677677677677677677677677677677677677677677677677677677677677677677677677"
        "677677677677677677677677677677677677677677677677677677677677677677677677677677677677677677677677677223123123"
        "123123123123123123123123123651861861861861861861861222123123223677677677677677677677677677677677677677677677"
        "677677677677677677677677677677677677677677677123122122122122122122223223223122122a80ea0ea0ea0ea0ea0ea0ea0222"
        "223223122677677677677677677677677677677677677677677677677677677677677677677677677677677677677677677123334455"
        "455233122122445445555122223a80c90d90d90d90b80d90d90222455455122677677677677677677677677677677677677677677677"
        "677677677677677677677677677677677677677677677123334455677556334334445788778677555a70970a70a70970960b80b80333"
        "666455122677677677677677677677677677677677677677677677677677677677677677677677677677677677677677677123122123"
        "223123122455667223223444233a80d90d90d90d90d90d90d90332123122122677677677677677677677677677677677677677677677"
        "677677677677677677677677677677677677677677677751751751751751751751751751751751751c80ea0ea0ea0ea0ea0ea0ea0761"
        "751751751677677677677677677677677677677677677677677677677677677677677677677677677677677677677677677677677677"
        "677677677677677677677677677677677677677677677677677677677677677677677677677677677677677677677677677677677677"
    ),
    "phrase-highlight": (
        "677677677677677677677677677677677677677677677677677677677677677677677677677677677677677677677677677677677677"
        "677677677677677677677677677677677677677677677677677677677677677677677677677677677677677677677677677677677677"
        "677677677677677677677677677677677677677677677677677677677677677677677677677677677677677677677677677677677677"
        "677677677677677677677677677677677677677677677677677677677677677677677778778677677677677677677677677677677677"
        "778778677677677677677677677677677677677677677677677677677677677677677677677677677677677677677677677677788889"
        "8897886776776778999aa677778778888778788778889889788677899899677677677677677677677677677677677677677677677677"
        "6776776776776776776776776776776776776776776776777788999aa999788788677aabbbb9aa99a788abbaaaaabccc99abbc9aa778"
        "999899677677677677677677677677677677677677677677677677677677677677677677677677677677677677677677677677778677"
        "777778677889999889677889788677677677677677677677677778677677677677677677677677677677677677677677677677677677"
        "677677677677677677677677677677677677677677677677677677677677677677677677677677677886a94a94a94a94a94a94a94677"
        "677677677677677677677677677677677677677677677677677677677677677677677677677677677677677677677677677677677677"
        "677677677677677677677677677777777777777777777777777677677677677677677677677677677677677677677677677677677677"
    ),
    "line-clean": (
        "677677677677677677677677677677677677677677677677677677677677677677677677677677677677677677677677677677677677"
        "677677677677677677677677677677677677677677677677677677677677677677677677677677677677677677677677677677677677"
        "677677677677677677677677677677677677677677677677677677677677677677677677677677677677677677677677677677677677"
        "67767767767767767767767767778878867767767778867767778878867767767767767767767767767767767767777878899a677677"
        "677677677889778677677788788677677677677677677677677677677677677677677677677677677788889677899778999778677999"
        "89967799a888778677788899889999677677677778999bbb778677778677999888677677677999899677677677677677677677677677"
        "677677677677677677677677677aaa9999aa89999a999999889999899677aaa899aab9997778998999aa889677889778bbbbbcabb9aa"
        "9aa778899aaa889889899999899677677677677677677677677677677677677677677677677677677677888888899778889999aaa888"
        "77878888899a788778778677788899677677aabbbb99a78899aaaa88889999a788889889889888778677677677677677677677677677"
        "677677677677677677677677677677677677677677677677677677677677999788677677677677677677677677677778677677677677"
        "677778677677677677677677677677677677677677677677677677677677677677677677677677677677677677677677677677677677"
        "677677677677677677677677677677677677677677677677677677677677677677677677677677677677677677677677677677677677"
    ),
    "line-boxed": (
        "677677677677677677677677677677677677677677677677677677677677677677677677677677677677677677677677677677677677"
        "677677677677677677677677677677677677677677677677677677677677677677677677677677677677677445233233233233233233"
        "233233233233233233233233233233233233233233233233233233233233233233233233445677677677677677677677677677677677"
        "677677677677677677677677677677677344122223122122223122122223223122122122122122122122122122122222222122122122"
        "122223122122233123334677677677677677677677677677677677677677677677677677677677677677677344122667122455556223"
        "122455455334445223122334445566122122122542651122222122666233122122667233334677677677677677677677677677677677"
        "677677677677677677677677677677677344344677777677778667445666455455778788445455445888334332122871771661442445"
        "777566677667677233334677677677677677677677677677677677677677677677677677677677677677677344122122122122122344"
        "555122122555556122122122122122122232552332122332222455122122122122122122334677677677677677677677677677677677"
        "677677677677677677677677677677677764862862862862862862862862862862862862862862862862862862862862862862862862"
        "862862862862862862764677677677677677677677677677677677677677677677677677677677677677677677677677677677677677"
        "677677677677677677677677677677677677677677677677677677677677677677677677677677677677677677677677677677677677"
    ),
    "line-highlight": (
        "677677677677677677677677677677677677677677677677677677677677677677677677677677677677677677677677677677677677"
        "677677677677677677677677677677677677677677677677677677677677677677677677677677677677677677677677677677677677"
        "677677677677677677677677677677677985984984984984984777677677677677677677677677677677677677677677677677677677"
        "677677677677677677677677677677677677777677677677778677677788677677677677677677677677677d90ea0d90d90ea0ea0776"
        "677778677677778778677677677677677677677677677677677677677677677677677677677677677677677677889888778899889778"
        "677aab677999778778788889899778677d90ea0a70970ea0d90776788899677677889899677677677677677677677677677677677677"
        "6776776776776776776776776776776776779999aaabb99a99a88999aaaa677aaaaaaaaa7788999aa899778b81d90861861970b80776"
        "99aaaa99a9aaaaa889677677677677677677677677677677677677677677677677677677677677677677677677677677677677677889"
        "788677778999778677677677677677677c90a70c90ea0c80d90887788677677677677677677677677677677677677677677677677677"
        "677677677677677677677677677677677677677677677677677677677677677677677677677677677677677a94a94a94a94a94a94777"
        "677677677677677677677677677677677677677677677677677677677677677677677677677677677677677677677677677677677677"
        "677677677677677677677677677677677677677677677677677677677677677677677677677677677677677677677677677677677677"
    ),
}


class TestGolden(PaintCase):
    def test_golden_still_per_look(self):
        missing = [n for n in GOLDEN_EMPHASIS if n not in GOLDEN]
        self.assertEqual(missing, [], "no golden signature for these looks")
        for name, emph in GOLDEN_EMPHASIS.items():
            got = signature(self.painter(name, emphasis=emph), name)
            self.assertLessEqual(sig_distance(got, GOLDEN[name]), 0.02, f"{name} drifted from its golden still")

    def test_the_signature_tells_looks_apart(self):
        sigs = {n: signature(self.painter(n, emphasis=e), n) for n, e in GOLDEN_EMPHASIS.items()}
        names = sorted(sigs)
        for i, a in enumerate(names):
            for b in names[i + 1:]:
                self.assertGreater(sig_distance(sigs[a], sigs[b]), 0.02, f"{a} and {b} look the same")


class ClipCase(unittest.TestCase):
    """A client with the repo's Plex font, brand roles, one compiled clip (no time map) and its words."""
    VID = "C0001"
    SPEECH = "النهارده هنتكلم عن السكر، السكر بيقل 40% مع الرياضة |600| وده مهم جدا"

    def setUp(self):
        if not (LC.hb_available() and PLEX.exists()):
            self.skipTest("HarfBuzz or the repo fonts missing")
        import shutil
        import tempfile
        from lib import common
        from lib.common import Paths, write_json
        from lib.stamps import stamp
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.root = self.tmp / "CLIENT"
        db = self.root / "output/client_database"
        write_json(db / "branding/typography.json", typography(
            ("Plex", [("Regular", PLEX, "IBMPlexSansArabic-Regular"), ("SemiBold", PLEX_SB, "IBMPlexSansArabic-SemiBold")]),
            roles={"caption": "IBMPlexSansArabic-Regular"}))
        write_json(db / "branding/brand-tokens.json", {"roles": {"primary": {"hex": "#1F6F8B"}, "accent": {"hex": "#E0A000"},
                                                                 "highlight": {"hex": "#FFD400"}}})
        common.set_context(self.root)
        self.addCleanup(common.set_context, None)
        self.paths = Paths(self.root, self.VID)
        self.paths.ensure_project()
        self.words = W(self.SPEECH, start=500)
        write_json(self.paths.p("02_transcription/words.json"), {"meta": {}, "words": self.words})
        self.spec = {"fps": 30, "events": [], "caption_highlights": [{"text": "الرياضة", "at_ms": None}],
                     "caption_source": "02_transcription/captions-short.srt", "time_map": None,
                     "main_footage": "data/none.mp4", "duration_ms": 9000}
        write_json(self.paths.p("01_analysis/timeline-spec.json"), stamp(self.spec))

    def resolved(self, look, **kw):
        from lib import looks
        return looks.resolve(words=self.words, override=look, **kw)


class TestHook(ClipCase):
    def test_the_foot_colour_is_decided_once_for_the_clip(self):
        # a colour flipping from caption to caption pumps like the scrim did; one choice, one note at most
        from unittest import mock
        from lib import previews
        from lib.common import write_json
        from lib.stamps import stamp
        write_json(self.paths.p("01_analysis/timeline-spec.json"),
                   stamp(dict(self.spec, style={"highlight": {"policy": "#1E2A3B", "hex": "#1E2A3B"}})))
        self.footage()
        calls = []

        def grab(main, ms, size):
            calls.append(ms)
            return frame((30, 30, 34)) if len(calls) % 2 else frame((235, 235, 235))
        warns = []
        with mock.patch.object(previews, "grab_frame", side_effect=grab):
            items = LC.render_captions(self.paths, self.resolved("line-highlight"), [], warnings=warns)
        self.assertGreater(len(items), 1)
        self.assertEqual(len({it["foot"] for it in items}), 1, [it["foot"] for it in items])
        self.assertLessEqual(sum(1 for w in warns if "moving foot" in w), 1, warns)

    def test_the_foot_follows_the_t42_highlight_colour_in_the_compiled_spec(self):
        from PIL import Image
        from lib.common import write_json
        from lib.stamps import stamp
        write_json(self.paths.p("01_analysis/timeline-spec.json"),
                   stamp(dict(self.spec, style={"highlight": {"policy": "#E0B76B", "hex": "#E0B76B"}})))
        items = LC.render_captions(self.paths, self.resolved("line-highlight"), [])
        with Image.open(items[0]["band"]) as im:
            box = im.getchannel("A").getbbox()
            px = im.convert("RGB").getpixel(((box[0] + box[2]) // 2, (box[1] + box[3]) // 2))
        self.assertEqual(px, (0xE0, 0xB7, 0x6B))

    def footage(self):
        from lib.common import spec_footage
        main = Path(spec_footage(self.paths, self.spec))
        main.parent.mkdir(parents=True, exist_ok=True)
        main.write_bytes(b"")
        return main

    def test_the_scrim_never_pumps_between_neighbouring_captions(self):
        from unittest import mock
        from lib import previews
        self.footage()
        bright, dark = frame((250, 250, 245)), frame((25, 25, 30))
        calls = []

        def grab(main, ms, size):                 # every other request is a bright frame
            calls.append(ms)
            return bright if len(calls) % 2 else dark
        with mock.patch.object(previews, "grab_frame", side_effect=grab):
            items = LC.render_captions(self.paths, self.resolved("phrase-clean"), [])
        self.assertGreater(len(items), 2)
        self.assertGreater(len(calls), 1)
        for a, b in zip(items, items[1:]):
            if b["start_ms"] - a["start_ms"] <= 4000:
                self.assertEqual(a["scrim"], b["scrim"], (a["text"], b["text"]))
        self.assertTrue(all(it["scrim"] > 0 for it in items))

    def test_one_frame_at_a_time_and_at_most_two_grabs_a_second(self):
        # a full frame is 8 MB: a reel's worth held at once is gigabytes (G10 on an 8 GB Mac)
        import gc
        import weakref
        from unittest import mock
        from lib import previews
        self.footage()
        alive, peak, calls = [], [0], []

        def grab(main, ms, size):
            gc.collect()
            live = [r for r in alive if r() is not None]
            peak[0] = max(peak[0], len(live))
            calls.append(ms)
            fr = frame((250, 250, 245) if len(calls) % 2 else (25, 25, 30))
            alive.append(weakref.ref(fr))
            return fr
        with mock.patch.object(previews, "grab_frame", side_effect=grab):
            items = LC.render_captions(self.paths, self.resolved("word-clean"), [])
        self.assertGreater(len(items), 8)
        self.assertLessEqual(peak[0], 1, "frames kept alive between grabs")
        span_s = (items[-1]["end_ms"] - items[0]["start_ms"]) / 1000
        self.assertLessEqual(len(calls), int(span_s * 2) + 2)

    def test_a_failed_grab_still_takes_its_neighbours_steady_scrim(self):
        from unittest import mock
        from lib import previews
        self.footage()
        calls = []

        def grab(main, ms, size):
            calls.append(ms)
            return None if len(calls) == 2 else frame((250, 250, 245))
        with mock.patch.object(previews, "grab_frame", side_effect=grab):
            items = LC.render_captions(self.paths, self.resolved("phrase-clean"), [])
        self.assertTrue(all(it["scrim"] > 0 for it in items[:3]), [it["scrim"] for it in items])

    def test_the_frame_behind_a_caption_is_taken_at_its_own_time(self):
        from unittest import mock
        from lib import previews
        self.footage()
        calls = []
        with mock.patch.object(previews, "grab_frame", side_effect=lambda m, ms, size: calls.append(ms) or frame((40, 40, 40))):
            items = LC.render_captions(self.paths, self.resolved("phrase-clean"), [])
        mids = [(it["start_ms"] + it["end_ms"]) / 2 for it in items]
        for ms in calls:
            self.assertLess(min(abs(ms - m) for m in mids), 260, (ms, mids))

    def test_render_captions_writes_layers_and_a_manifest(self):
        from lib.common import read_json
        warns = []
        items = LC.render_captions(self.paths, self.resolved("phrase-boxed"), [], warnings=warns)
        self.assertTrue(items)
        for it in items:
            self.assertTrue(Path(it["fg"]).exists() and Path(it["plate"]).exists())
            self.assertEqual(Path(it["fg"]).parent, self.paths.p("03_broll/captions"))
            self.assertNotIn("bar", it)                     # no RTL sweep: our looks focus in
            self.assertEqual(it["look"], "phrase-boxed")
            self.assertEqual(it["motion"]["entrance"], "focus_in")
        man = read_json(self.paths.p("03_broll/captions/captions-manifest.json"))
        self.assertEqual(man["look"]["look"], "phrase-boxed")
        self.assertEqual(len(man["captions"]), len(items))
        self.assertTrue(any(it["emphasis_words"] for it in items))      # «الرياضة» is a caption highlight

    def test_highlight_writes_the_band_and_word_spans(self):
        items = LC.render_captions(self.paths, self.resolved("line-highlight"), [])
        for it in items:
            self.assertTrue(Path(it["band"]).exists())
            self.assertEqual(len(it["spans"]), len(it["text"].split()))
            self.assertEqual(it["spans"][0]["start_ms"], it["start_ms"])

    def test_hidden_ranges_drop_the_words_a_graphic_shows(self):
        a, b = self.words[0]["start_ms"], self.words[2]["end_ms"]
        items = LC.render_captions(self.paths, self.resolved("phrase-clean"), [(a, b)])
        shown = " ".join(it["text"] for it in items)
        self.assertNotIn("النهارده", shown)
        self.assertIn("الرياضة", shown)

    def test_digits_follow_the_client_choice(self):
        from lib.common import CLIENT_PROFILE_REL, write_json
        write_json(self.root / CLIENT_PROFILE_REL / "style.json", {"captions": {"digits": "arabic_indic"}})
        items = LC.render_captions(self.paths, self.resolved("line-clean"), [])
        self.assertIn(AI, " ".join(it["text"] for it in items))

    def test_word_mode_digits_follow_the_client_choice_too(self):
        from lib.common import CLIENT_PROFILE_REL, write_json
        write_json(self.root / CLIENT_PROFILE_REL / "style.json", {"captions": {"digits": "arabic_indic"}})
        items = LC.render_captions(self.paths, self.resolved("word-clean"), [])
        self.assertIn(AI, [it["text"] for it in items])

    def test_no_fonts_or_no_harfbuzz_falls_back_to_todays_captions(self):
        self.paths.client_db.joinpath("branding/typography.json").unlink()
        warns = []
        self.assertIsNone(LC.render_captions(self.paths, self.resolved("phrase-clean"), [], warnings=warns))
        self.assertTrue(any("today's captions" in w for w in warns), warns)
        self.assertTrue(any("today's captions" in w for w in LC.plan_check(self.paths, self.spec,
                                                                            self.resolved("phrase-clean"))))

    def test_fit_notices_reach_the_warnings(self):
        from lib.common import write_json
        write_json(self.paths.p("02_transcription/words.json"),
                   {"meta": {}, "words": W("الاستراتيجياتوالتكنولوجياتالمتقدمةجداجداجدا")})
        warns = []
        items = LC.render_captions(self.paths, self.resolved("word-boxed"), [], warnings=warns)
        self.assertEqual(items, [])
        self.assertTrue(any("too long for one line" in w for w in warns), warns)

    def test_words_follow_the_time_map(self):
        from lib.common import write_json
        from lib.stamps import stamp
        spec = dict(self.spec, time_map={"keep_ms": [[0, 1000], [2000, 9000]], "words_cut": []})
        write_json(self.paths.p("01_analysis/timeline-spec.json"), stamp(spec))
        ws = LC.seq_words(self.paths, spec)
        src = {w["id"]: w for w in self.words}
        moved = [w for w in ws if src[w["id"]]["start_ms"] >= 2000]
        self.assertTrue(moved)
        self.assertTrue(all(abs(w["start_ms"] - (src[w["id"]]["start_ms"] - 1000)) <= 34 for w in moved))
        gone = [w for w in self.words if 1000 <= w["start_ms"] and w["end_ms"] <= 2000]
        self.assertFalse({w["id"] for w in gone} & {w["id"] for w in ws})

    def test_the_plans_sequence_words_win(self):
        from lib.common import write_json
        write_json(self.paths.p("02_transcription/words-seq.json"), {"words": [dict(self.words[0], start_ms=7)]})
        self.assertEqual([w["start_ms"] for w in LC.seq_words(self.paths, self.spec)], [7])

    def test_plan_check_reports_without_drawing(self):
        from lib.common import write_json
        write_json(self.paths.p("02_transcription/words.json"),
                   {"meta": {}, "words": W("كلمة 漢 |900| الاستراتيجياتوالتكنولوجياتالمتقدمةجداجداجدا")})
        out = LC.plan_check(self.paths, self.spec, self.resolved("word-boxed"))
        self.assertTrue(any("too long for one line" in w for w in out))
        self.assertTrue(any("U+6F22" in w for w in out))
        self.assertFalse(self.paths.p("03_broll/captions/captions-manifest.json").exists())
        self.assertEqual(LC.plan_check(self.paths, self.spec, {"look": None}), [])

    def test_no_look_means_nothing_is_written(self):
        self.assertEqual(LC.render_captions(self.paths, {"look": None}, []), [])
        self.assertFalse(self.paths.p("03_broll/captions/captions-manifest.json").exists())


class TestGallery(ClipCase):
    def test_eight_looks_on_two_frames_and_one_sheet_in_qc_never_broll(self):
        before = sorted(p.name for p in self.paths.p("03_broll").rglob("*"))
        res = LC.render(self.paths)
        out = self.paths.p("08_quality_control/previews/caption-looks")
        self.assertEqual(len(res["looks"]), 8)
        for lk in res["looks"]:
            self.assertEqual(len(lk["pngs"]), 2)
            self.assertTrue(all(Path(p).exists() and Path(p).parent == out for p in lk["pngs"]))
            self.assertEqual(lk["png"], lk["pngs"][0])
        self.assertTrue(Path(res["sheet"]).exists() and Path(res["sheet"]).parent == out)
        self.assertEqual(sorted(p.name for p in self.paths.p("03_broll").rglob("*")), before)
        self.assertIn("elapsed_s", res)

    def test_every_tile_shows_its_emphasis_and_the_band_on_that_word(self):
        res = LC.render(self.paths, frames=[frame((60, 60, 60)), frame((200, 200, 200))])
        for lk in res["looks"]:
            self.assertTrue(lk["emphasised"], lk["name"])
            self.assertIn(lk["emphasised"], lk["shown"].split(), lk["name"])
            if lk["name"].endswith("-highlight"):
                self.assertEqual(lk["band_word"], lk["emphasised"])

    def test_a_tag_on_a_highlight_look_leaves_the_band_visible_on_another_word(self):
        res = LC.render(self.paths, looks=["phrase-highlight", "line-highlight"], emphasis="tag",
                        frames=[frame((60, 60, 60)), frame((200, 200, 200))])
        for lk in res["looks"]:
            self.assertTrue(lk["band_word"] and lk["emphasised"], lk)
            self.assertNotEqual(lk["band_word"], lk["emphasised"], lk["name"])
            self.assertIn(lk["band_word"], lk["shown"].split(), lk["name"])

    def test_the_tile_label_says_when_the_emphasis_was_mapped(self):
        res = LC.render(self.paths, looks=["phrase-highlight", "phrase-clean"], emphasis="colour")
        self.assertEqual([lk["label"] for lk in res["looks"]],
                         ["phrase-highlight · colour → weight", "phrase-clean · colour"])

    def test_a_long_tile_label_never_runs_into_the_next_tile(self):
        from PIL import Image
        tmp = self.paths.p("08_quality_control")
        tmp.mkdir(parents=True, exist_ok=True)
        frames = []
        for k in range(2):
            f = tmp / f"t{k}.png"
            Image.new("RGB", (1080, 1920), (90, 90, 90)).save(f)
            frames.append(str(f))
        face = {"file": str(INTER)}
        out = LC._sheet([(frames[0], "phrase-highlight · colour → weight · extra words"), (frames[1], "")],
                        tmp / "s.png", (1080, 1920), face)
        with Image.open(out) as im:
            th = round(270 * 1920 / 1080)
            row = [im.getpixel((x, y)) for x in range(272, 540) for y in range(th + 2, th + 32)]
            self.assertTrue(all(px == (24, 24, 24) for px in row), "the first label spilled into the second tile")

    def test_a_subset_and_task16_names(self):
        res = LC.render(self.paths, looks=["box", "line-highlight"])
        self.assertEqual([lk["name"] for lk in res["looks"]], ["phrase-boxed", "line-highlight"])

    def test_over_the_time_budget_is_a_warning_not_an_error(self):
        res = LC.render(self.paths, looks=["phrase-clean"], budget_s=0.0)
        self.assertTrue(any("budget" in w for w in res["warnings"]))

    def test_the_frames_can_be_given(self):
        res = LC.render(self.paths, looks=["phrase-clean"], frames=[frame((200, 40, 40)), frame((40, 200, 40))])
        from PIL import Image
        with Image.open(res["looks"][0]["pngs"][0]) as im:
            self.assertEqual(im.convert("RGB").getpixel((5, 5)), (200, 40, 40))

    def test_pick_round_trips_into_the_client_style(self):
        from lib import looks
        res = LC.pick(self.paths, "line-boxed", yes=False)
        self.assertFalse(res["written"])
        self.assertTrue(res["diff"])
        res = LC.pick(self.paths, "line-boxed", yes=True)
        self.assertTrue(res["written"])
        self.assertEqual(looks.resolve(words=self.words)["look"], "line-boxed")


class TestSafeWidth(unittest.TestCase):
    def test_safe_width_from_the_subtitle_safe_area(self):
        self.assertEqual(LC.safe_width(1080), 900)
        self.assertEqual(LC.safe_width(720), 600)


class FakeCTFont:
    def __init__(self, face, size):
        self.face, self.size = face, size


class FakeCTEngine:
    """Stands in for macOS CoreText (lib/ct_text): every character is 10 px per 20 px of size; 'Q' is missing in the
    brand face. The darwin branch must take its widths and its missing-glyph answers from this engine."""
    name = "coretext"

    def font(self, face, size):
        return FakeCTFont(face, size)

    def advance(self, text, direction, font):
        return len(text) * font.size / 2

    def shape(self, text, direction, font):
        g = [(ord(c), font.size / 2, 0.0, 0.0) for c in text]
        return list(reversed(g)) if direction == "rtl" else g

    def missing(self, text, font):
        return [c for c in text if c == "Q" and font.face["ps"] == "Brand-Bold"]

    def space(self, font):
        return font.size / 4


class TestWeightStep(unittest.TestCase):
    def test_the_weight_emphasis_steps_200_units_up(self):
        from lib import looks_type as LT
        typ = typography(("Fam", [("Regular", "r.ttf", "Fam-Regular"), ("Medium", "m.ttf", "Fam-Medium"),
                                  ("Bold", "b.ttf", "Fam-Bold"), ("Black", "k.ttf", "Fam-Black")]))
        f, _ = LT._heavier(typ, {"file": "r.ttf", "ps": "Fam-Regular", "family": "Fam"}, 200)
        self.assertEqual(f["ps"], "Fam-Bold")
        f, note = LT._heavier(typ, {"file": "k.ttf", "ps": "Fam-Black", "family": "Fam"}, 200)
        self.assertEqual(f["ps"], "Fam-Black")
        self.assertTrue(note)


class TestDarwinPath(unittest.TestCase):
    def test_coretext_engine_measures_and_reports(self):
        chain = {"arabic": [face(Path("x.ttf"), "Brand-Bold")], "latin": [face(Path("x.ttf"), "Brand-Bold"),
                                                                           face(Path("y.ttf"), "House-Regular")]}
        ts = LC.Typesetter(chain, 40, engine=FakeCTEngine())
        ln = ts.line(["abc", "Qz"])
        self.assertAlmostEqual(ln["w"], 3 * 20 + 2 * 20 + 10)
        self.assertEqual([s["ps"] for s in ln["items"][1]["segments"]], ["House-Regular"])
        self.assertEqual(ts.engines, {"coretext"})

    def test_ctengine_asks_coretext_for_each_character(self):
        import types
        from unittest import mock
        from lib import looks_type as LT
        calls = []
        fake_ct = types.ModuleType("CoreText")

        def glyphs_for(font, chars, glyphs, n):
            calls.append((font, chars, glyphs, n))
            return (chars != "Q", None)
        fake_ct.CTFontGetGlyphsForCharacters = glyphs_for
        font = types.SimpleNamespace(_font="CTFONT")
        with mock.patch.dict(sys.modules, {"CoreText": fake_ct}):
            self.assertEqual(LT.CTEngine().missing("aQَ", font), ["Q"])
        self.assertEqual([c[1] for c in calls], ["a", "Q", "َ"])
        self.assertTrue(all(c[0] == "CTFONT" and c[2] is None and c[3] == 1 for c in calls))
        from lib import ct_text
        with mock.patch.object(ct_text, "measure", side_effect=lambda t, f: len(t)) as m:
            self.assertEqual(LT.CTEngine().advance("abc", "rtl", font), 4)
            self.assertTrue(m.call_args[0][0].startswith("\u200f"))

    @unittest.skipUnless(sys.platform == "darwin", "CoreText exists only on macOS (the Mac CI runner)")
    def test_real_coretext_measures_and_finds_missing_glyphs(self):
        from lib import ct_text, looks_type as LT
        if not ct_text.AVAILABLE:
            self.skipTest("pyobjc CoreText missing")
        eng = LT.CTEngine()
        font = eng.font({"ps": "Helvetica"}, 40)
        self.assertGreater(eng.advance("Hello", "ltr", font), 40)
        self.assertEqual(eng.missing("ب", font), ["ب"])           # Helvetica has no Arabic
        img, base, w = eng.render("Hello", "ltr", font)
        self.assertGreater(w, 40)

    def test_engine_choice_follows_the_platform(self):
        e = LC.pick_engine(face(PLEX, "IBMPlexSansArabic-Regular"), ct_available=True, ct_exact=lambda ps: True)
        self.assertEqual(e.name, "coretext")
        e = LC.pick_engine(face(PLEX, "IBMPlexSansArabic-Regular"), ct_available=True, ct_exact=lambda ps: False)
        self.assertEqual(e.name, "harfbuzz")
        e = LC.pick_engine(face(PLEX, "IBMPlexSansArabic-Regular"), ct_available=False, ct_exact=lambda ps: True)
        self.assertEqual(e.name, "harfbuzz")


if __name__ == "__main__":
    unittest.main()
