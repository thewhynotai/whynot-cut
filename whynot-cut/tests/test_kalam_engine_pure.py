# SPDX-License-Identifier: GPL-3.0-or-later
# © 2026 The Why Not AI (thewhynot.ai)
"""3.0 tools track, Task 9 (N4 part A): the WhyNot Kalam engine package, pure modules (lib/kalam/{rules,phrases,similar,
units,captions,clean}.py). Ported from the owner's Kalam engine tests (engine/tests/test_{rules,captions,clean,units}.py):
every upstream test function is one method here with the SAME name (48 tests: rules 12, captions 18, clean 9, units 9),
plus three package/provenance checks at the end; bodies are unchanged apart from the mechanical pytest -> unittest
rewrite (`assert a == b` -> assertEqual, other asserts -> assertTrue). tests/test_kalam_test_map.py guards that none
is dropped.

Fixture scan (Addendum A / global constraints): the four upstream files were scanned for "Sherif", "Rog 2", "/Users/",
"macstoreeg" and "Hoka": no hit, so no fixture text was replaced. The Arabic/Latin sample sentences are generic speech
or medical vocabulary. One deliberate keep: the credit-line strings in test_drop_hallucinations_removes_known_credit_lines
and test_drop_unspoken_removes_words_on_silence_far_from_speech are the Whisper hallucination the module itself lists
(clean.HALLUCINATIONS), i.e. the module's data under test, not a person in our fixtures.

The upstream test_units.py imports W and seq from test_captions.py; here they are the module-level helpers below. The
upstream test_clean.py has its own W (word dicts with a score): it is Wc here so both helpers can live in one module.
The two default_rules*.txt are the owner's text: byte-identical to the upstream files (checked when adobe/tools is
present: absent in the plugin zip, which ships tests/ but not adobe/).
"""
import sys as _sys
_sys.dont_write_bytecode = True
import _isolation  # noqa: F401,E402  G79: sandbox the engine home first (tests/_isolation.py)
import hashlib
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "engine" / "reel"))

import numpy as np  # noqa: E402

from lib.kalam.captions import fit_phrases, pack, split_long, to_srt, wrap  # noqa: E402
from lib.kalam.clean import clean_garbled, drop_hallucinations, drop_loops, drop_nonspeech_tags, drop_unspoken  # noqa: E402
from lib.kalam.phrases import phrases  # noqa: E402
from lib.kalam.rules import capitalize_latin, enforce, strip_diacritics, strip_punct  # noqa: E402
from lib.kalam.units import apply_units, join_continuations  # noqa: E402

PKG = Path(__file__).resolve().parents[1] / "engine" / "reel" / "lib" / "kalam"
UPSTREAM = Path(__file__).resolve().parents[2] / "adobe" / "tools" / "kalam" / "_upstream" / "engine" / "kalam"
MODULES = ("__init__", "captions", "clean", "phrases", "rules", "similar", "units")


def W(*items):
    """W(("word", start, end), ...) -> word dicts"""
    return [{"w": w, "s": s, "e": e} for w, s, e in items]


def seq(text, start, step=0.3, gap=0.02):
    """consecutive words with tiny gaps (one spoken phrase)"""
    out, t = [], start
    for w in text.split():
        out.append((w, t, t + step - gap))
        t += step
    return out


class TestRules(unittest.TestCase):
    def test_strip_punct_removes_arabic_and_latin_marks(self):
        self.assertEqual(strip_punct("صحح، الكلام. ده! إزاي؟ (مثلا) \"كده\"…"), "صحح الكلام ده إزاي مثلا كده")

    def test_strip_punct_turns_hyphens_into_spaces(self):
        self.assertEqual(strip_punct("X-Ray و 50-60 سنتي"), "X Ray و 50 60 سنتي")

    def test_strip_punct_keeps_percent_and_article_tatweel(self):
        self.assertEqual(strip_punct("زادت 80% في الـ Fracture"), "زادت 80% في الـ Fracture")

    def test_strip_diacritics_keeps_only_tanween_fath(self):
        self.assertEqual(strip_diacritics("جدًّا مَثلًا فِعلًا"), "جدًا مثلًا فعلًا")

    def test_strip_diacritics_keeps_tatweel_of_article(self):
        self.assertEqual(strip_diacritics("الـ Fracture"), "الـ Fracture")

    def test_capitalize_latin_title_cases_each_word_and_keeps_acronyms(self):
        self.assertEqual(capitalize_latin("founder content CRP associated with broken bone"),
                         "Founder Content CRP Associated With Broken Bone")

    def test_enforce_never_puts_hamza_on_inta(self):
        self.assertEqual(enforce("إنت عارف وأنتو شايفين وإنتي فاهمة", {}), "انت عارف وانتو شايفين وانتي فاهمة")

    def test_enforce_applies_glossary_case_insensitively_on_whole_words(self):
        g = {"Granudacyn": ["graniodasin"], "ESR": ["esr"], "Masquelet Technique": ["muscular technique"]}
        self.assertEqual(enforce("استخدمنا GranioDasin و esr ثم muscular technique", g),
                         "استخدمنا Granudacyn و ESR ثم Masquelet Technique")

    def test_enforce_glossary_does_not_touch_parts_of_words(self):
        self.assertEqual(enforce("esrabc", {"ESR": ["esr"]}), "Esrabc")

    def test_enforce_full_line(self):
        self.assertEqual(enforce("الدرس، اللي اتعلمته: safety  الأمان!", {}), "الدرس اللي اتعلمته Safety الأمان")

    def test_english_mode_keeps_sentence_case_but_drops_punctuation(self):
        self.assertEqual(enforce("Hello, and welcome to this short test.", {}, mode="en"),
                         "Hello and welcome to this short test")

    def test_glossary_still_applies_in_english_mode(self):
        self.assertEqual(enforce("we used graniodasin here", {"Granudacyn": ["graniodasin"]}, mode="en"),
                         "we used Granudacyn here")


class TestCaptions(unittest.TestCase):
    def test_phrases_split_only_at_real_pauses(self):
        ws = W(*seq("Soft Tissue Injury", 1.0), *seq("انتو عارفين", 2.2))
        ps = phrases(ws, min_pause=0.22)
        self.assertEqual([p["text"] for p in ps], ["Soft Tissue Injury", "انتو عارفين"])
        self.assertTrue(ps[0]["s"] == 1.0 and abs(ps[0]["e"] - 1.88) < 1e-9)

    def test_captions_have_no_gaps_and_tail(self):
        ps = phrases(W(*seq("واحدة من المشاكل", 0.5), *seq("نبتدي من الأول", 3.0)), 0.22)
        caps = pack(ps)
        for a, b in zip(caps, caps[1:]):
            self.assertEqual(a["e"], b["s"])
        self.assertEqual(caps[0]["s"], 0.5)
        self.assertTrue(abs(caps[-1]["e"] - (3.0 + 0.9 - 0.02 + 0.3)) < 1e-9)

    def test_stop_pause_always_ends_a_caption(self):
        ps = phrases(W(*seq("رقم ممتاز", 1.0), *seq("رقم كويس", 2.3)), 0.22)   # 0.72 s pause
        self.assertEqual([c["text"] for c in pack(ps)], ["رقم ممتاز", "رقم كويس"])

    def test_short_phrases_join_until_full(self):
        ps = phrases(W(*seq("بصوا مثلًا", 1.0), *seq("الحالة دي", 1.9)), 0.22)       # 0.32 s pause
        self.assertEqual([c["text"] for c in pack(ps)], ["بصوا مثلًا الحالة دي"])

    def test_never_more_than_two_lines_of_32(self):
        words = W(*seq("الكسر صغير قوي لكن فعلًا لو قلت للنايب ابعتلي صورة الـ Soft Tissue أو نزلت تبص", 0.0, step=0.25))
        caps = pack(split_long(phrases(words, 0.22)))
        for c in caps:
            lines = c["text"].split("\n")
            self.assertTrue(len(lines) <= 2)
            self.assertTrue(all(len(l) <= 32 for l in lines))

    def test_long_phrase_splits_at_biggest_internal_gap(self):
        a = seq("الـ Timing Of Fixation مهم جدًا", 0.0, gap=0.02)
        b = seq("وبعد كده طريقة الـ Fixation مهمة جدًا", a[-1][2] + 0.15, gap=0.02)   # 0.15 s: below min_pause
        parts = split_long(phrases(W(*a, *b), 0.22))
        self.assertEqual([p["text"] for p in parts],
                         ["الـ Timing Of Fixation مهم جدًا", "وبعد كده طريقة الـ Fixation مهمة جدًا"])

    def test_term_is_not_split_when_it_fits(self):
        ps = phrases(W(*seq("بنحط Spanning External Fixator", 0.0)), 0.22)
        self.assertEqual([c["text"].replace("\n", " ") for c in pack(split_long(ps))], ["بنحط Spanning External Fixator"])

    def test_max_duration_ends_caption(self):
        ps = phrases(W(*seq("واحد", 0.0, step=2.0), *seq("اتنين", 2.3, step=2.0), *seq("تلاتة", 4.6, step=2.0)), 0.22)
        caps = pack(ps, max_dur=4.5)
        self.assertTrue(all(c["e"] - c["s"] <= 4.6 + 0.3 for c in caps) and len(caps) >= 2)

    def test_corrected_text_longer_than_two_lines_is_split_by_time(self):
        p = phrases(W(*seq("صفتشو انجري ده", 0.0)), 0.22)[0]
        p["text"] = "Soft Tissue Injury Associated With Broken Bone Zone Of Injury Example"   # grew after correction
        caps = pack([p])
        self.assertEqual(len(caps), 2)
        self.assertTrue(all(len(l) <= 32 for c in caps for l in c["text"].split("\n")))
        self.assertTrue(caps[0]["e"] == caps[1]["s"] and caps[0]["s"] == 0.0)

    def test_to_srt_format(self):
        srt = to_srt([{"s": 2.661, "e": 4.662, "text": "واحدة من المشاكل"}, {"s": 4.662, "e": 5.9, "text": "نبتدي"}])
        self.assertEqual(srt, "1\n00:00:02,661 --> 00:00:04,662\nواحدة من المشاكل\n\n2\n00:00:04,662 --> 00:00:05,900\nنبتدي\n")

    def test_sentence_end_is_preferred_over_filling_the_caption(self):
        a = seq("نبتدي من الأول.", 0.0)
        b = seq("شباب جراحين العظام", a[-1][2] + 0.3)
        c = seq("قلنا إن واحدة من المشاكل", b[-1][2] + 0.25)
        caps = pack(split_long(phrases(W(*a, *b, *c), 0.22)))
        texts = [x["text"].replace("\n", " ") for x in caps]
        self.assertEqual(texts[0], "نبتدي من الأول.")
        self.assertTrue(any(t.endswith("قلنا إن واحدة من المشاكل") for t in texts))

    def test_caption_never_ends_in_the_middle_of_a_short_sentence(self):
        a = seq("شباب جراحين العظام قلنا إن", 0.0)
        b = seq("واحدة من المشاكل اللي تعمل حاجة", a[-1][2] + 0.23)      # small breath inside one sentence
        caps = pack(split_long(phrases(W(*a, *b), 0.22)))
        self.assertTrue([x["text"].replace("\n", " ") for x in caps] == ["شباب جراحين العظام قلنا إن واحدة من المشاكل اللي تعمل حاجة"] or
                        all(not x["text"].endswith("إن") for x in caps))

    def test_wrap_keeps_latin_terms_on_one_line(self):
        # the most balanced break would be "Soft\nTissue"; a term stays on one line when another break fits
        self.assertEqual(wrap("هي إن يبقى عندنا Soft Tissue Injury انتو عارفين"), "هي إن يبقى عندنا\nSoft Tissue Injury انتو عارفين")

    def test_long_phrase_with_even_gaps_splits_after_sentence_end(self):
        ws = W(*seq("بصوا مثلًا الحالة دي لما يجيلك أشعة زي دي. الكسر صغير قوي لكن فعلًا لو قلت", 0.0, step=0.25))
        parts = split_long(phrases(ws, 0.22))
        self.assertTrue(parts[0]["text"].endswith("زي دي."))

    # ---- fit_phrases: split (corrected) phrases to fit, at real word onsets, never inside a term ----
    def test_fit_one_line_never_splits_a_latin_term(self):
        raw = W(*seq("بصوا هنا الزون اوف إنجري عند العيان ده قد إيه", 37.4, step=0.24))
        p = phrases(raw, 0.22)[0]
        p["text"] = "بصوا هنا الـ Zone Of Injury عند العيان ده قد إيه"
        parts = fit_phrases([p], max_line=32, max_lines=1)
        texts = [x["text"] for x in parts]
        self.assertTrue(all(len(t) <= 32 for t in texts))
        self.assertTrue(not any(t.endswith("Zone Of") or t.startswith("Injury") or t.endswith("Zone") for t in texts), texts)
        self.assertTrue(any("Zone Of Injury" in t for t in texts))

    def test_fit_split_starts_on_a_real_word_onset(self):
        raw = W(("واحد", 0.0, 0.3), ("اتنين", 0.35, 0.7), ("تلاتة", 0.75, 1.1), ("اربعة", 3.0, 3.4), ("خمسة", 3.45, 3.8))
        p = phrases(raw, 5.0)[0]                                     # one phrase (slow speaker)
        p["text"] = "Soft Tissue Injury Associated With Broken Bone Zone"  # grew after correction
        parts = fit_phrases([p], max_line=32, max_lines=1)
        onsets = {w["s"] for w in raw}
        self.assertTrue(len(parts) >= 2 and all(x["s"] in onsets for x in parts))

    def test_fit_unchanged_text_splits_at_biggest_pause(self):
        a = seq("الـ Timing Of Fixation مهم جدًا", 0.0)
        b = seq("وبعد كده طريقة الـ Fixation مهمة جدًا", a[-1][2] + 0.15)
        parts = fit_phrases(phrases(W(*a, *b), 0.22), max_line=32, max_lines=2)
        self.assertEqual([x["text"] for x in parts], ["الـ Timing Of Fixation مهم جدًا", "وبعد كده طريقة الـ Fixation مهمة جدًا"])
        self.assertEqual(parts[1]["s"], b[0][1])

    def test_fit_maps_corrected_words_to_the_right_raw_words(self):
        raw = W(*seq("المجهود اللي أنت حطه النهارده، حتى لأساس حاجات زي مثلا ال الربتيشن بتاعتك،", 0.0, step=0.3, gap=0.05))
        p = phrases(raw, 0.22)[0]
        p["text"] = "المجهود اللي انت حاطه النهارده حتى على أساس حاجات زي مثلًا الـ Reputation بتاعتك"
        parts = fit_phrases([p], max_line=32, max_lines=1)
        self.assertEqual(parts[0]["text"], "المجهود اللي انت حاطه النهارده", [x["text"] for x in parts])
        self.assertEqual(parts[1]["s"], raw[5]["s"])                      # "حتى" starts exactly when it is said
        self.assertTrue(not any(x["text"].endswith("الـ") for x in parts))


def Wc(*items):
    return [{"w": w, "s": s, "e": e, "score": sc} for w, s, e, sc in items]


def env_with_speech(total_s, speech_spans, loud=-20.0, quiet=-90.0, hop=0.01):
    env = np.full(int(total_s / hop), quiet, dtype=np.float32)
    for a, b in speech_spans:
        env[int(a / hop):int(b / hop)] = loud
    return env


class TestClean(unittest.TestCase):
    def test_drop_loops_removes_runs_of_the_same_word(self):
        ws = Wc(*[("exca", i * 0.2, i * 0.2 + 0.1, 0.5) for i in range(6)], ("تمام", 1.4, 1.6, 0.9))
        self.assertEqual([w["w"] for w in drop_loops(ws, max_repeat=3)], ["تمام"])

    def test_drop_loops_keeps_natural_repeats(self):
        ws = Wc(("جدًا", 0, 0.3, 0.9), ("جدًا", 0.3, 0.6, 0.9), ("مهم", 0.6, 0.9, 0.9))
        self.assertEqual(len(drop_loops(ws, max_repeat=3)), 3)

    def test_drop_unspoken_keeps_low_score_word_inside_speech(self):
        env = env_with_speech(10, [(1.0, 5.0)])
        ws = Wc(("نبتدي", 2.0, 2.4, 0.9), ("الأول", 4.9, 5.3, 0.01))   # half on speech, aligner unsure
        self.assertEqual([w["w"] for w in drop_unspoken(ws, env)], ["نبتدي", "الأول"])

    def test_drop_unspoken_removes_words_on_silence_far_from_speech(self):
        env = env_with_speech(12, [(1.0, 5.0)])
        ws = Wc(("كلام", 2.0, 2.4, 0.9), ("ترجمة", 9.0, 9.4, 0.0), ("نانسي", 9.4, 9.8, 0.0))
        self.assertEqual([w["w"] for w in drop_unspoken(ws, env)], ["كلام"])

    def test_drop_hallucinations_removes_known_credit_lines(self):
        ws = Wc(("كلام", 0, 0.4, 0.9), ("ترجمة", 1, 1.3, 0.9), ("نانسي", 1.3, 1.6, 0.9), ("قنقر", 1.6, 1.9, 0.9))
        self.assertEqual([w["w"] for w in drop_hallucinations(ws)], ["كلام"])

    def test_nonspeech_tags_are_removed(self):
        ws = Wc(("[موسيقى]", 0, 1, 0.9), ("كلام", 1, 1.4, 0.9), ("♪", 1.5, 1.6, 0.9), ("(Music)", 2, 3, 0.9),
                ("[تصفيق", 3, 3.5, 0.9), ("حار]", 3.5, 4, 0.9), ("مهم", 4.2, 4.6, 0.9))
        self.assertEqual([w["w"] for w in drop_nonspeech_tags(ws)], ["كلام", "مهم"])

    def test_room_tone_with_little_speech_still_counts_as_silence(self):
        rng = np.random.default_rng(1)
        env = (-60 + rng.uniform(-3, 3, 6000)).astype(np.float32)          # 60 s room tone
        env[100:400] = -20                                                  # 3 s of speech
        ws = Wc(("كلام", 1.5, 2.0, 0.9), ("شكرا", 40.0, 40.4, 0.0), ("للمشاهدة", 40.4, 41.0, 0.0))
        self.assertEqual([w["w"] for w in drop_unspoken(ws, env)], ["كلام"])

    def test_garbled_whisper_tokens_are_cleaned(self):
        ws = Wc(("وحيرقوك،", 65.98, 66.6, 0.66), ("غيرqub", 66.62, 68.22, 0.64), ("-", 68.22, 68.4, 0.5),
                ("g", 68.4, 68.42, 0.003), ("up,", 68.5, 68.96, 0.0), ("Soft", 70.0, 70.3, 0.6), ("Tissue", 70.3, 70.7, 0.5))
        out = clean_garbled(ws, mode="ar")
        self.assertEqual([w["w"] for w in out], ["وحيرقوك،", "غير", "Soft", "Tissue"])

    def test_garbled_cleanup_keeps_english_speech_in_english_mode(self):
        ws = Wc(("we", 0, 0.2, 0.04), ("go", 0.2, 0.4, 0.03), ("up", 0.4, 0.6, 0.02))
        self.assertEqual(len(clean_garbled(ws, mode="en")), 3)


class TestUnits(unittest.TestCase):
    def test_apply_units_marks_breaks_after_enforcing_each_unit(self):
        p = {"text": "raw", "s": 0, "e": 1, "words": []}
        apply_units(p, "لو ما حدش شايف إن انت جامد، | حتى لو كنت بتقدم كل حاجة في معادها |", {}, "ar")
        self.assertEqual(p["text"], "لو ما حدش شايف إن انت جامد حتى لو كنت بتقدم كل حاجة في معادها")
        self.assertTrue(p["unit_breaks"] == {7} and p["unit_end"] is True)

    def test_apply_units_line_that_continues(self):
        p = {"text": "raw", "s": 0, "e": 1, "words": []}
        apply_units(p, "لو ما حدش شايف", {}, "ar")
        self.assertTrue(p["unit_breaks"] == set() and p["unit_end"] is False)

    def test_apply_units_without_markers_from_a_fallback(self):
        p = {"text": "raw", "s": 0, "e": 1, "words": []}
        apply_units(p, None, {}, "ar")
        self.assertTrue(p["unit_end"] is None and p["unit_breaks"] == set() and p["text"] == "raw")

    def test_fit_breaks_only_at_meaning_units_and_lets_a_unit_run_long(self):
        text = "مش هيرقيك لو ما حدش شايف إن انت جامد حتى لو كنت بتقدم كل حاجة في معادها"
        p = phrases(W(*seq(text, 0.0, step=0.25)), 0.22)[0]
        apply_units(p, "مش هيرقيك | لو ما حدش شايف إن انت جامد | حتى لو كنت بتقدم كل حاجة في معادها |", {}, "ar")
        parts = fit_phrases([p], max_line=32, max_lines=1)
        self.assertEqual([x["text"] for x in parts],
                         ["مش هيرقيك", "لو ما حدش شايف إن انت جامد", "حتى لو كنت بتقدم كل حاجة في معادها"])

    def test_pack_joins_a_line_that_continues_across_a_pause(self):
        a, b = seq("لو ما حدش شايف", 0.0), seq("إن انت جامد", 1.5)          # 0.32 s breath mid-sentence
        ps = phrases(W(*a, *b), 0.22)
        apply_units(ps[0], "لو ما حدش شايف", {}, "ar")
        apply_units(ps[1], "إن انت جامد |", {}, "ar")
        self.assertEqual([c["text"] for c in pack(fit_phrases(ps, 32, 1), max_line=32, max_lines=1)], ["لو ما حدش شايف إن انت جامد"])

    def test_pack_keeps_complete_units_as_their_own_captions(self):
        a, b = seq("الشغل الجامد", 0.0), seq("مش هيرقيك", 1.0)
        ps = phrases(W(*a, *b), 0.22)
        apply_units(ps[0], "الشغل الجامد |", {}, "ar")
        apply_units(ps[1], "مش هيرقيك |", {}, "ar")
        self.assertEqual([c["text"] for c in pack(fit_phrases(ps, 32, 1), max_line=32, max_lines=1)], ["الشغل الجامد", "مش هيرقيك"])

    def test_a_long_whole_unit_is_one_caption_never_none(self):
        p = phrases(W(*seq("حتى لو كنت بتقدم كل حاجة في معادها", 0.0)), 0.22)[0]
        apply_units(p, "حتى لو كنت بتقدم كل حاجة في معادها |", {}, "ar")
        caps = pack(fit_phrases([p], 32, 1), max_line=32, max_lines=1)
        self.assertEqual([c["text"] for c in caps], ["حتى لو كنت بتقدم كل حاجة في معادها"])

    def test_a_line_that_continues_is_joined_before_splitting(self):
        a = seq("لأن", 9.05, step=0.3)
        b = seq("الترقية ما بتحصلش بس على أساس المجهود اللي انت حاطه النهارده", 9.68, step=0.25)
        ps = phrases(W(*a, *b), 0.22)
        apply_units(ps[0], "لأن", {}, "ar")
        apply_units(ps[1], "الترقية ما بتحصلش بس | على أساس المجهود اللي انت حاطه النهارده |", {}, "ar")
        joined = join_continuations(ps)
        self.assertTrue(len(joined) == 1 and joined[0]["s"] == 9.05 and joined[0]["unit_breaks"] == {5})
        caps = pack(fit_phrases(joined, 32, 1), max_line=32, max_lines=1)
        self.assertEqual([c["text"] for c in caps], ["لأن الترقية ما بتحصلش بس", "على أساس المجهود اللي انت حاطه النهارده"])

    def test_no_one_letter_caption_when_it_can_join_a_neighbour(self):
        a = seq("ناس مقدرة ف", 26.0, step=0.4)
        b = seq("دي حاجات الإدارة بتكون حطاها في الاعتبار", a[-1][2] + 0.3, step=0.3)
        ps = phrases(W(*a, *b), 0.22)
        apply_units(ps[0], "ناس مقدرة | ف", {}, "ar")
        apply_units(ps[1], "دي حاجات الإدارة بتكون حطاها في الاعتبار |", {}, "ar")
        caps = pack(fit_phrases(join_continuations(ps), 32, 1), max_line=32, max_lines=1)
        self.assertTrue(all(len(c["text"]) > 3 for c in caps), [c["text"] for c in caps])


class TestPackage(unittest.TestCase):
    """Not upstream tests: the package carries its provenance and the owner's rules text is byte-identical."""

    def test_modules_carry_the_licence_header_and_provenance(self):
        for name in MODULES:
            head = (PKG / (name + ".py")).read_text(encoding="utf-8").splitlines()[:3]
            self.assertEqual(head[0], "# SPDX-License-Identifier: GPL-3.0-or-later", name)
            self.assertEqual(head[1], "# © 2026 The Why Not AI (thewhynot.ai)", name)
            self.assertEqual(head[2], "# Ported unchanged from the owner's Kalam engine (kalam/%s.py); "
                                      "see adobe/tools/README.md" % name, name)

    def test_default_rules_files_are_the_owners_text_byte_identical(self):
        if not UPSTREAM.is_dir():
            self.skipTest("adobe/tools is not part of the plugin zip")
        for name in ("default_rules.txt", "default_rules_en.txt"):
            ours, theirs = (PKG / name).read_bytes(), (UPSTREAM / name).read_bytes()
            self.assertEqual(hashlib.sha256(ours).hexdigest(), hashlib.sha256(theirs).hexdigest(), name)
            self.assertEqual(ours, theirs, name)

    def test_pure_modules_are_the_upstream_code_after_the_header(self):
        if not UPSTREAM.is_dir():
            self.skipTest("adobe/tools is not part of the plugin zip")
        for name in MODULES:
            ours = (PKG / (name + ".py")).read_bytes().decode("utf-8")
            theirs = (UPSTREAM / (name + ".py")).read_bytes().decode("utf-8")
            body = ours.split("\n", 3)[3] if ours.count("\n") >= 3 else ""
            self.assertEqual(body, theirs, name)


if __name__ == "__main__":
    unittest.main()
