# SPDX-License-Identifier: GPL-3.0-or-later
# © 2026 The Why Not AI (thewhynot.ai)
"""3.0 Phase 4 Task 65 (Addendum K1, K-T5) — Arabic integrity QC: Arabic letters join, so text animates by whole words
or lines, never letters; a word is never split across lines, animation units or captions; the After Effects read-back
unit is checked; on-screen Arabic is free of pasted presentation forms, direction overrides, a font without Arabic, and
lost Quranic marks.
Run:  bash tools/test.sh -p test_safety_arabic_integrity.py
"""
import sys as _sys
_sys.dont_write_bytecode = True  # keep the plugin folder free of __pycache__
import _isolation  # noqa: F401,E402  G79: sandbox the engine home first (tests/_isolation.py)
import copy
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys = _sys
SK = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SK / "engine" / "reel"))

from lib import common  # noqa: E402
from lib.common import Paths, write_json  # noqa: E402
from lib.safety import arabic_integrity as AI  # noqa: E402


def el(name, text, reveal="word", lines=None, rtl=True, font_ps="SegoeUI-Bold"):
    lines = lines or [text]
    toks = [{"text": t, "cue_frame": k * 5, "word_id": None} for k, t in enumerate(" ".join(lines).split())]
    return {"kind": "text", "name": name, "lines": lines, "text": "\r".join(lines), "rtl": rtl, "reveal": reveal,
            "tokens": toks, "font_ps": font_ps}


def plan(*elements, sid="S01"):
    return {"scenes": [{"id": sid, "type": "kinetic_quote", "elements": list(elements)}]}


def rules(findings):
    return sorted({f["rule"] for f in findings})


class TestMotionPlan(unittest.TestCase):
    def test_per_letter_arabic_refused(self):
        for unit in ("char", "characters", "letter", "typewriter", "glyph"):
            with self.subTest(unit=unit):
                f = AI.check_motion_plan(plan(el("S01_text_1", "الضغط العالي خطر", reveal=unit), sid="S04"))
                self.assertEqual(rules(f), ["per_letter"])
                self.assertEqual(f[0]["scene"], "S04")
                self.assertTrue(f[0]["ar"].startswith("المشهد S04"))
        self.assertEqual(AI.check_motion_plan(plan(el("S01_text_1", "Hello world", reveal="char", rtl=False))), [])
        for unit in ("word", "line", "item", "none"):
            self.assertEqual(AI.check_motion_plan(plan(el("S01_text_1", "الضغط العالي خطر", reveal=unit))), [])

    def test_split_word_refused(self):
        bad = el("S01_text_1", "الضغط العالي", lines=["الضغ", "ط العالي"])
        bad["tokens"] = [{"text": t} for t in "الضغط العالي".split()]
        self.assertIn("split_word", rules(AI.check_motion_plan(plan(bad))))
        ok = el("S01_text_1", "الضغط العالي", lines=["الضغط", "العالي"])
        self.assertEqual(AI.check_motion_plan(plan(ok)), [])
        # a token that is half a word
        half = el("S01_text_1", "الضغط العالي")
        half["tokens"] = [{"text": "الضغ"}, {"text": "ط"}, {"text": "العالي"}]
        self.assertIn("split_word", rules(AI.check_motion_plan(plan(half))))

    def test_mixed_line_latin_run_whole(self):
        ok = el("S01_text_1", "جرعة الـ Vitamin D مهمة")
        self.assertEqual(AI.check_motion_plan(plan(ok)), [])
        split = el("S01_text_1", "جرعة الـ Vitamin D مهمة")
        split["tokens"] = [{"text": t} for t in ["جرعة", "الـ", "Vit", "amin", "D", "مهمة"]]
        self.assertIn("split_word", rules(AI.check_motion_plan(plan(split))))
        per_letter = el("S01_text_1", "جرعة الـ Vitamin D مهمة", reveal="character")
        self.assertEqual(rules(AI.check_motion_plan(plan(per_letter))), ["per_letter"])

    def test_lam_alef_and_tatweel_stay_whole(self):
        self.assertEqual(AI.check_motion_plan(plan(el("S01_text_1", "لا تاخد الدوا"))), [])
        self.assertEqual(AI.check_motion_plan(plan(el("S01_text_1", "مـــهم جدا"))), [])     # kashida is fine
        split = el("S01_text_1", "لا تاخد", lines=["ل", "ا تاخد"])
        split["tokens"] = [{"text": "لا"}, {"text": "تاخد"}]
        self.assertIn("split_word", rules(AI.check_motion_plan(plan(split))))

    def test_quran_diacritics_kept_from_the_script(self):
        verse = "إِنَّ مَعَ الْعُسْرِ يُسْرًا"
        script = {"scenes": [{"id": "S01", "type": "kinetic_quote", "text": verse}]}
        self.assertEqual(AI.check_motion_plan(plan(el("S01_text_1", verse)), script=script), [])
        stripped = "إن مع العسر يسرا"
        f = AI.check_motion_plan(plan(el("S01_text_1", stripped)), script=script)
        self.assertEqual(rules(f), ["marks_lost"])

    def test_broken_font_fallback(self):
        f = AI.check_motion_plan(plan(el("S01_text_1", "الضغط العالي", font_ps="SomeLatinOnly")),
                                 font_has_arabic=lambda ps: ps != "SomeLatinOnly")
        self.assertEqual(rules(f), ["font_no_arabic"])
        self.assertEqual(AI.check_motion_plan(plan(el("S01_text_1", "Hello", rtl=False, font_ps="SomeLatinOnly")),
                                              font_has_arabic=lambda ps: False), [])


class TestText(unittest.TestCase):
    def test_isolated_presentation_forms_refused(self):
        f = AI.check_text("ﺍﻟﻀﻐﻂ ﺍﻟﻌﺎﻟﻲ", "S01")                    # pasted "isolated forms"
        self.assertEqual(rules(f), ["presentation_forms"])
        self.assertEqual(AI.check_text("الضغط العالي", "S01"), [])

    def test_reversed_run_overrides_refused(self):
        self.assertEqual(rules(AI.check_text("‮مجم ٥٠٠‬", "S01")), ["bidi_override"])
        self.assertEqual(rules(AI.check_text("⁧خد ٥٠٠ مجم⁩", "S01")), ["bidi_isolate"])   # a warning

    def test_zwj_zwnj_inside_a_word_is_a_warning(self):
        f = AI.check_text("الض‌غط", "S01")
        self.assertEqual(rules(f), ["zero_width_joiner"])
        self.assertEqual(f[0]["level"], "warning")
        self.assertEqual(AI.check_text("الضغط ‌ العالي", "S01"), [])      # between words: harmless

    def test_eastern_arabic_digits_are_fine(self):
        self.assertEqual(AI.check_text("خد ٥٠٠ مجم و٣٫٥ مل", "S01"), [])


class TestCuesAndReadback(unittest.TestCase):
    WORDS = [{"id": i, "word": w} for i, w in enumerate("الضغط العالي مرض صامت".split(), 1)]

    def test_caption_cues_keep_words_whole(self):
        good = [{"text": "الضغط العالي", "word_ids": [1, 2]}, {"text": "مرض\nصامت", "word_ids": [3, 4]}]
        self.assertEqual(AI.check_cues(good, self.WORDS), [])
        split = [{"text": "الضغط الع", "word_ids": [1, 2]}, {"text": "الي مرض صامت", "word_ids": [2, 3, 4]}]
        self.assertEqual(rules(AI.check_cues(split, self.WORDS)), ["split_word"])

    def test_readback_unit_parsed(self):
        rb = {"scenes": [{"id": "S01", "layers": [
            {"name": "S01_text_1", "kind": "text", "text": "الضغط العالي",
             "animators": [{"name": "Reveal", "based_on": "words"}, {"name": "Emphasis", "based_on": 3}]},
            {"name": "S01_text_2", "kind": "text", "text": "الضغط العالي",
             "animators": [{"name": "Typewriter", "based_on": "characters"}]},
            {"name": "S01_text_3", "kind": "text", "text": "Hello",
             "animators": [{"name": "Typewriter", "based_on": 1}]},
            {"name": "S01_text_4", "kind": "text", "text": "الضغط"}]}]}
        units = AI.readback_units(rb)
        self.assertEqual(units["S01_text_1"], ["words", "words"])
        self.assertEqual(units["S01_text_2"], ["characters"])
        self.assertEqual(units["S01_text_3"], ["characters"])
        self.assertEqual(units["S01_text_4"], [])
        f = AI.check_readback(rb)
        self.assertEqual([(x["rule"], x["layer"]) for x in f], [("readback_unit", "S01_text_2")])


class TestProject(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="kt5_"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.addCleanup(common.set_context, None)
        self.root = self.tmp / "د. تجربة Dr Test"
        for d in ("assets", "data/Raw"):
            (self.root / d).mkdir(parents=True)
        (self.root / ".whynot-client").write_text("{}", encoding="utf-8")
        self.p = Paths(self.root, "C0001")
        common.set_context(self.root)

    def snapshot(self):
        return {str(f.relative_to(self.root)): f.read_bytes() for f in self.root.rglob("*") if f.is_file()}

    def test_nothing_to_check_is_a_plain_line_and_nothing_is_written(self):
        before = self.snapshot()
        rep = AI.run(self.p)
        self.assertEqual(rep["findings"], [])
        self.assertTrue(rep["notes"][0].startswith("مفيش"))
        self.assertEqual(self.snapshot(), before)

    def test_run_reads_the_plan_and_a_damaged_plan_is_refused_plainly(self):
        write_json(self.p.p("01_analysis/motion-plan.json"), plan(el("S01_text_1", "الضغط العالي", reveal="char")))
        rep = AI.run(self.p)
        self.assertEqual(rules(rep["findings"]), ["per_letter"])
        self.assertFalse(rep["ok"])
        a = AI.run(self.p)
        with mock.patch.object(sys, "platform", "darwin"):
            self.assertEqual(AI.run(self.p), a)
        self.p.p("01_analysis/motion-plan.json").write_text("{x", encoding="utf-8")
        rep = AI.run(self.p)
        self.assertTrue(rep["ok"])                         # a damaged plan is its own step's error: a warning here
        self.assertEqual(rules(rep["findings"]), ["unreadable"])


# --- review round 1 (independent reviewer, 2026-10-17): C1, I1–I5, M1–M4 ---------------------------------------------
class TestReviewRound1(TestProject):
    def test_c1_run_reads_the_build_read_back(self):
        from lib.motion_build import RESULT
        write_json(self.p.p(RESULT), {"status": "PROJECT_ASSEMBLED", "readback": {"scenes": [{"id": "S02", "layers": [
            {"name": "S02_text_1", "kind": "text", "text": "الضغط العالي",
             "animators": [{"name": "Typewriter", "based_on": 1}]}]}]}})
        rep = AI.run(self.p)
        self.assertEqual(rules(rep["findings"]), ["readback_unit"])
        self.assertFalse(rep["ok"])

    def test_m2_a_font_after_effects_substituted(self):
        rb = {"scenes": [{"id": "S01", "layers": [{"name": "S01_text_1", "kind": "text", "text": "الضغط",
                                                   "substitute": True}]}]}
        self.assertEqual(rules(AI.check_readback(rb)), ["font_no_arabic"])

    def test_i5_a_word_split_in_a_caption_file(self):
        write_json(self.p.p("02_transcription/words.json"),
                   {"words": [{"id": i, "word": w} for i, w in enumerate("الضغط العالي مرض صامت".split(), 1)]})
        srt = self.p.p("02_transcription/captions-short.srt")
        srt.write_text("1\n00:00:00,000 --> 00:00:01,000\nالضغط الع\n\n2\n00:00:01,000 --> 00:00:02,000\nالي مرض صامت\n",
                       encoding="utf-8")
        self.assertEqual(rules(AI.run(self.p)["findings"]), ["split_word"])


class TestReviewRound1Text(unittest.TestCase):
    def test_i1_verse_brackets_and_single_character_words_are_fine(self):
        self.assertEqual(AI.check_text("﴿إِنَّ مَعَ الْعُسْرِ يُسْرًا﴾", "S01"), [])
        self.assertEqual(AI.check_text("قال النبي ﷺ", "S01"), [])
        self.assertEqual(AI.check_text("﷽", "S01"), [])

    def test_i2_isolates_are_a_warning_overrides_an_error(self):
        f = AI.check_text("\u2067خد ٥٠٠ مجم\u2069", "S01")
        self.assertEqual([(x["rule"], x["level"]) for x in f], [("bidi_isolate", "warning")])
        f = AI.check_text("\u202eمجم ٥٠٠\u202c", "S01")
        self.assertEqual([(x["rule"], x["level"]) for x in f], [("bidi_override", "error")])

    def test_i3_per_letter_units_however_spelled(self):
        for unit in ("by_char", "per-letter", "Characters Excluding Spaces", "BY_CHARACTER", "typewriter_fast"):
            with self.subTest(unit=unit):
                self.assertEqual(rules(AI.check_motion_plan(plan(el("S01_text_1", "الضغط العالي", reveal=unit)))),
                                 ["per_letter"])

    def test_i4_split_word_without_tokens_caught_against_the_script(self):
        e = el("S01_text_1", "x")
        e.update(lines=["مر", "حبا بيكم"], text="مر\rحبا بيكم", tokens=[])
        script = {"scenes": [{"id": "S01", "type": "kinetic_quote", "text": "مرحبا بيكم"}]}
        self.assertEqual(rules(AI.check_motion_plan(plan(e), script=script)), ["split_word"])
        ok = el("S01_text_1", "x")
        ok.update(lines=["مرحبا", "بيكم"], text="مرحبا\rبيكم", tokens=[])
        self.assertEqual(AI.check_motion_plan(plan(ok), script=script), [])

    def test_r2_short_elements_inside_longer_words_are_no_split(self):
        for elem, sources in (("ما", ["ماذا تفعل"]), ("ما", ["ماذا تفعل", "ما"]), ("٥٠", ["٢٥٠ مجم"]),
                              ("في", ["الفيروس"]), ("mg", ["500mg يوميا"])):
            with self.subTest(elem=elem):
                e = el("S01_text_1", elem)
                e["tokens"] = []
                script = {"scenes": [{"id": "S01", "type": "kinetic_quote", "items": [{"text": s} for s in sources]}]}
                self.assertEqual(AI.check_motion_plan(plan(e), script=script), [])

    def test_r2_caption_spacing_reading_is_a_warning(self):
        words = [{"id": 1, "word": "خد"}, {"id": 2, "word": "5mg"}]
        f = AI.check_cues([{"text": "خد 5"}, {"text": "mg"}], words)
        self.assertEqual([(x["rule"], x["level"]) for x in f], [("split_word", "warning")])

    def test_m1_an_unmarked_copy_elsewhere_in_the_scene_is_no_loss(self):
        script = {"scenes": [{"id": "S01", "type": "kinetic_quote", "text": "إِنَّ مَعَ الْعُسْرِ يُسْرًا",
                              "subtitle": "إن مع العسر يسرا"}]}
        self.assertEqual(AI.check_motion_plan(plan(el("S01_text_2", "إن مع العسر يسرا")), script=script), [])

    def test_m4_zwnj_after_a_non_joining_letter_is_fine(self):
        self.assertEqual(AI.check_text("دا\u200cر", "S01"), [])


if __name__ == "__main__":
    unittest.main()
