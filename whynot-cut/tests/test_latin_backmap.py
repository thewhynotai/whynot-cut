# SPDX-License-Identifier: GPL-3.0-or-later
# © 2026 The Why Not AI (thewhynot.ai)
"""Addendum M M2-T3 (Task 55, Gate 4 part): the deterministic Latin back-map and its pair list.
  * a word in Arabic letters whose spelling is in config/defaults/latin-terms.json is PROPOSED in Latin letters
    («إنسولين» → insulin) only when the audio and the context agree: every word of the term has probability >= the
    threshold (transcription.json low_confidence_threshold) AND a word within 3 words either side is in Latin letters,
    hits the entry's own review-domain lexicon, or is another pair-list term;
  * a clitic stays in Arabic in front of the Latin word («بالإنسولين» → «بالـ insulin», «وإنسولين» → «و insulin»);
  * never a profile person's name, never inside a recited verse, a hadith or a ﴿ ﴾ zone, never for a client with
    `latin_backmap: false`; multi-word terms span their word ids («إيه آي» → AI);
  * proposals are NEVER applied: write_proposals writes only 02_transcription/latin-proposals.json (deterministic bytes);
    transcript.json, words.json and transcript-corrections.json stay byte-identical; no words.json writes nothing;
  * the pair list is built only from our own review lexicons and the glossary (provenance checked), with no Arabic
    spelling mapped to two Latin terms.
Run: bash tools/test.sh -p test_latin_backmap.py
"""
import sys as _sys
_sys.dont_write_bytecode = True  # keep the plugin folder free of __pycache__
import _isolation  # noqa: F401,E402  G79: sandbox the engine home first (tests/_isolation.py)
import copy
import json
import shutil
import tempfile
import time
import unittest
from pathlib import Path

from lib import latin_backmap as LB  # noqa: E402
from lib.common import Paths, load_config  # noqa: E402
from lib.errors import Guidance  # noqa: E402

SK = Path(__file__).resolve().parents[1]
REAL_PAIRS = SK / "config" / "defaults" / "latin-terms.json"

FIXTURE_PAIRS = [
    {"latin": "insulin", "arabic": ["أنسولين"], "domain": "medical", "source": "test"},
    {"latin": "vitamin", "arabic": ["فيتامين"], "domain": "medical", "source": "test"},
    {"latin": "blood sugar", "arabic": ["بلود شوجر"], "domain": "medical", "source": "test"},
    {"latin": "AI", "arabic": ["إيه آي"], "domain": "ai", "source": "test"},
    {"latin": "Amal", "arabic": ["أمل"], "domain": "business", "source": "test"},
]
PLAIN = {"domain": "general", "people": []}          # a profile: not religious, no people, back-map on


def words(text: str, probs=None, gap_ms: int = 100):
    """words.json rows for a space-separated text, 300 ms per word."""
    out, t = [], 0
    for i, w in enumerate(text.split()):
        p = 0.9 if probs is None else (probs[i] if isinstance(probs, list) else probs.get(i, 0.9))
        row = {"id": i + 1, "segment_id": 1, "word": w, "start_ms": t, "end_ms": t + 300}
        if p is not None:
            row["probability"] = p
        out.append(row)
        t += 300 + gap_ms
    return out


def propose(text, probs=None, profile=None, pairs=None, **kw):
    return LB.propose(words(text, probs), pairs or FIXTURE_PAIRS, profile=PLAIN if profile is None else profile,
                      threshold=kw.pop("threshold", 0.5), **kw)


class Propose(unittest.TestCase):
    # 1. glossary hit next to a Latin word
    def test_glossary_hit_next_to_a_latin_word_is_proposed(self):
        props = propose("الجسم بيطلع إنسولين mg كل يوم")
        self.assertEqual(len(props), 1)
        p = props[0]
        self.assertEqual((p["word_id"], p["word_ids"], p["from"], p["to"], p["latin"], p["domain"]),
                         (3, [3], "إنسولين", "insulin", "insulin", "medical"))
        self.assertEqual(p["confidence"], 0.9)
        self.assertTrue(p["reason"])
        self.assertEqual(p["status"], "proposed")
        self.assertEqual((p["start_ms"], p["end_ms"]), (800, 1100))
        self.assertEqual(p["corrections"], [{"word_id": 3, "from": "إنسولين", "to": "insulin",
                                             "reason": p["reason"], "confidence": "high"}])

    # 2. low confidence, and the threshold boundary
    def test_low_confidence_is_never_proposed(self):
        self.assertEqual(propose("الجسم بيطلع إنسولين mg كل يوم", {2: 0.49}), [])
        self.assertEqual(len(propose("الجسم بيطلع إنسولين mg كل يوم", {2: 0.5})), 1, "the threshold itself passes")
        self.assertEqual(propose("الجسم بيطلع إنسولين mg كل يوم", {2: None}), [], "no probability = not confident")
        r = LB.analyse(words("الجسم بيطلع إنسولين mg كل يوم", {2: 0.3}), FIXTURE_PAIRS, profile=PLAIN, threshold=0.5)
        self.assertEqual([s["why"] for s in r["skipped"]], ["low_confidence"])

    def test_the_default_threshold_is_the_transcription_low_confidence_threshold(self):
        want = float(load_config("transcription.json").get("low_confidence_threshold"))
        self.assertEqual(LB.default_threshold(), want)
        w = words("الجسم بيطلع إنسولين mg كل يوم", {2: want - 0.01})
        self.assertEqual(LB.propose(w, FIXTURE_PAIRS, profile=PLAIN), [])
        w = words("الجسم بيطلع إنسولين mg كل يوم", {2: want})
        self.assertEqual(len(LB.propose(w, FIXTURE_PAIRS, profile=PLAIN)), 1)

    def test_every_word_of_a_multi_word_term_must_be_confident(self):
        self.assertEqual(propose("عندي بلود شوجر high جدا", {2: 0.3}), [])
        self.assertEqual(len(propose("عندي بلود شوجر high جدا", {1: 0.95, 2: 0.6})), 1)
        self.assertEqual(propose("عندي بلود شوجر high جدا", {1: 0.95, 2: 0.6})[0]["confidence"], 0.6)

    # 3. context disagreement, the window size, what counts as context
    def test_an_all_arabic_sentence_with_no_medical_word_near_is_not_proposed(self):
        self.assertEqual(propose("أنا قلت له إن إنسولين كلمة حلوة النهاردة"), [])
        r = LB.analyse(words("أنا قلت له إن إنسولين كلمة حلوة النهاردة"), FIXTURE_PAIRS, profile=PLAIN, threshold=0.5)
        self.assertEqual([s["why"] for s in r["skipped"]], ["no_context"])

    def test_a_medical_lexicon_word_near_is_context(self):
        self.assertEqual(len(propose("أنا باخد علاج إنسولين كل يوم")), 1)          # «علاج»: the medical lexicon
        self.assertEqual(len(propose("ارتفاع ضغط الدم إنسولين كل يوم")), 1)       # a two-word lexicon term

    def test_the_context_window_is_three_words_each_side(self):
        self.assertEqual(len(propose("mg هو كان إنسولين قوي جدا جدا")), 1, "Latin word 3 words before")
        self.assertEqual(propose("mg هو كان قال إنسولين قوي جدا جدا"), [], "4 words before is too far")
        self.assertEqual(len(propose("قال هو إنسولين قوي جدا mg خلاص")), 1, "Latin word 3 words after")
        self.assertEqual(propose("قال هو إنسولين قوي جدا كده mg خلاص"), [], "4 words after is too far")

    def test_the_term_itself_is_not_its_own_context(self):
        # «أنسولين» is a medical-lexicon term itself: only its neighbours may give the context
        self.assertEqual(propose("هو كان إنسولين قوي خالص"), [])

    def test_digits_are_not_latin_context_but_a_unit_is(self):
        self.assertEqual(propose("هو كان إنسولين 500 خالص"), [])
        self.assertEqual(len(propose("هو كان إنسولين 500 mg")), 1)

    def test_another_pair_list_term_near_is_context(self):
        props = propose("هو قال إيه آي و إنسولين ده كلام")
        self.assertEqual([p["latin"] for p in props], ["AI", "insulin"])

    def test_a_domain_lexicon_hit_counts_only_for_its_own_domain(self):
        # «ذكاء اصطناعي» is an ai-lexicon term: context for AI, not for insulin
        self.assertEqual(propose("ذكاء اصطناعي إنسولين حلو قوي"), [])
        self.assertEqual([p["latin"] for p in propose("ذكاء اصطناعي إيه آي حلو قوي")], ["AI"])

    # 5. spelling variants
    def test_spelling_variants_fold_to_the_same_entry(self):
        for v in ("انسولين", "أنسولين", "إنسولين", "إنسـولين", "إِنْسُولِين", "آنسولين"):
            props = propose(f"الجسم بيطلع {v} mg كل يوم")
            self.assertEqual([(p["latin"], p["from"]) for p in props], [("insulin", v)], v)

    # 6. clitics
    def test_a_clitic_stays_in_arabic_in_front_of_the_latin_word(self):
        cases = {"بالإنسولين": "بالـ insulin", "والإنسولين": "والـ insulin", "للإنسولين": "للـ insulin",
                 "الإنسولين": "الـ insulin", "وبالإنسولين": "وبالـ insulin", "وإنسولين": "و insulin",
                 "بإنسولين": "بـ insulin", "فالإنسولين": "فالـ insulin", "كالإنسولين": "كالـ insulin"}
        for heard, want in cases.items():
            props = propose(f"الجسم بيطلع {heard} mg كل يوم")
            self.assertEqual([p["to"] for p in props], [want], heard)
            self.assertNotIn("binsulin", props[0]["to"])

    def test_edge_punctuation_is_kept_around_the_latin_word(self):
        self.assertEqual(propose("الجسم بيطلع إنسولين، mg كل يوم")[0]["to"], "insulin،")
        self.assertEqual(propose("الجسم بيطلع «بالإنسولين» mg كل يوم")[0]["to"], "«بالـ insulin»")

    def test_a_clitic_needs_a_whole_spelling_after_it(self):
        self.assertEqual(propose("الجسم بيطلع بالإنسولينات mg كل يوم"), [])
        self.assertEqual(propose("الجسم بيطلع إنسولينا mg كل يوم"), [])

    # 7. names
    def test_a_profile_person_name_is_never_back_mapped(self):
        prof = {"domain": "general", "people": [{"name": "أمل حسن / Amal Hassan", "gender": "female"}]}
        self.assertEqual(propose("قالت أمل كده business deal", profile=prof), [])
        r = LB.analyse(words("قالت أمل كده business deal"), FIXTURE_PAIRS, profile=prof, threshold=0.5)
        self.assertEqual([s["why"] for s in r["skipped"]], ["name"])
        self.assertEqual(len(propose("قالت أمل كده business deal")), 1, "not a profile person: the entry applies")

    def test_a_name_with_a_clitic_is_still_a_name(self):
        prof = {"domain": "general", "people": [{"name": "أمل حسن", "gender": "female"}]}
        self.assertEqual(propose("قالت وأمل كده business deal", profile=prof), [])
        self.assertEqual(propose("قالت لأمل كده business deal", profile=prof), [])

    def test_the_client_display_name_is_a_name_too(self):
        prof = {"domain": "general", "people": [], "display_name": "عيادة أمل"}
        self.assertEqual(propose("قالت أمل كده business deal", profile=prof), [])

    # 8. verse / hadith / bracket zones
    def test_inside_a_recited_verse_no_proposal(self):
        w = words("قال تعالى إنسولين mg كلام")          # a span opens AFTER «قال تعالى» until a pause
        self.assertEqual(LB.propose(w, FIXTURE_PAIRS, profile=PLAIN, threshold=0.5), [])
        r = LB.analyse(w, FIXTURE_PAIRS, profile=PLAIN, threshold=0.5)
        self.assertEqual([s["why"] for s in r["skipped"]], ["religious_zone"])

    def test_inside_a_hadith_no_proposal(self):
        for cue in ("قال رسول الله", "قال النبي", "قال الرسول"):
            w = words(f"{cue} إنسولين mg كلام")
            self.assertEqual(LB.propose(w, FIXTURE_PAIRS, profile=PLAIN, threshold=0.5), [], cue)

    def test_the_basmala_and_a_joined_cue_open_a_zone(self):
        for text in ("بسم الله الرحمن الرحيم إنسولين mg كلام", "وقال تعالى إنسولين mg كلام", "فقال النبي إنسولين mg",
                     "يقول الله تعالى إنسولين mg", "عن رسول الله إنسولين mg"):
            self.assertEqual(LB.propose(words(text), FIXTURE_PAIRS, profile=PLAIN, threshold=0.5), [], text)
        self.assertEqual(len(LB.propose(words("قالت إنسولين mg كلام"), FIXTURE_PAIRS, profile=PLAIN, threshold=0.5)),
                         1, "«قالت» alone is no cue")

    def test_a_long_recited_verse_with_no_pause_stays_a_zone(self):
        # where a verse span ends without a pause is lib/manual_verse's rule; 10 s in is inside under any version of it
        inside = words("قال تعالى " + " ".join(["كلام"] * 25) + " إنسولين mg")
        self.assertEqual(LB.propose(inside, FIXTURE_PAIRS, profile=PLAIN, threshold=0.5), [])

    def test_a_hadith_zone_with_no_pause_ends_twelve_seconds_after_it_starts(self):
        inside = words("قال النبي " + " ".join(["كلام"] * 25) + " إنسولين mg")     # starts 10.0 s into the span
        self.assertEqual(LB.propose(inside, FIXTURE_PAIRS, profile=PLAIN, threshold=0.5), [])
        after = words("قال النبي " + " ".join(["كلام"] * 33) + " إنسولين mg")      # starts 13.2 s into the span
        self.assertEqual(len(LB.propose(after, FIXTURE_PAIRS, profile=PLAIN, threshold=0.5)), 1)
        edge = words("قال النبي " + " ".join(["كلام"] * 30) + " إنسولين mg")       # starts exactly at the 12 s cap
        self.assertEqual(len(LB.propose(edge, FIXTURE_PAIRS, profile=PLAIN, threshold=0.5)), 1)

    def test_a_pause_right_after_a_hadith_cue_does_not_end_the_zone(self):
        w = words("قال النبي")
        tail = words("إنسولين mg كلام")
        t0 = w[-1]["end_ms"] + 900                     # the speaker pauses after the cue, then quotes
        for x in tail:
            w.append(dict(x, id=len(w) + 1, start_ms=x["start_ms"] + t0, end_ms=x["end_ms"] + t0))
        self.assertEqual(LB.propose(w, FIXTURE_PAIRS, profile=PLAIN, threshold=0.5), [])

    def test_only_a_whole_cue_word_opens_a_hadith_zone(self):
        for text in ("يقال النبي إنسولين mg كلام", "قال بالنبي إنسولين mg كلام"):
            self.assertEqual(len(LB.propose(words(text), FIXTURE_PAIRS, profile=PLAIN, threshold=0.5)), 1, text)

    def test_a_hadith_zone_ends_at_a_pause(self):
        w = words("قال النبي كلام كلام")
        tail = words("الجسم بيطلع إنسولين mg كل يوم")
        t0 = w[-1]["end_ms"] + 800                     # a 0.8 s pause (>= 0.7 s) ends the hadith span
        for x in tail:
            w.append(dict(x, id=len(w) + 1, start_ms=x["start_ms"] + t0, end_ms=x["end_ms"] + t0))
        self.assertEqual([p["latin"] for p in LB.propose(w, FIXTURE_PAIRS, profile=PLAIN, threshold=0.5)], ["insulin"])

    def test_after_the_pause_that_ends_the_zone_the_back_map_applies(self):
        w = words("قال تعالى كلام كلام")
        tail = words("الجسم بيطلع إنسولين mg كل يوم")
        t0 = w[-1]["end_ms"] + 2000                    # a 2 s pause ends the recited span
        for i, x in enumerate(tail):
            w.append(dict(x, id=len(w) + 1, start_ms=x["start_ms"] + t0, end_ms=x["end_ms"] + t0))
        self.assertEqual([p["latin"] for p in LB.propose(w, FIXTURE_PAIRS, profile=PLAIN, threshold=0.5)], ["insulin"])

    def test_inside_brackets_no_proposal(self):
        self.assertEqual(propose("كلام ﴿ إنسولين mg ﴾ كلام"), [])
        self.assertEqual(propose("كلام ﴿إنسولين mg﴾ كلام"), [])

    def test_a_verse_phrase_quoted_alone_does_not_block_the_term_after_it(self):
        # «إن مع العسر يسرا» is a listed verse phrase: only its own words are the verse, never a pair-list spelling
        prof = {"domain": "religious", "people": []}
        for p in (PLAIN, prof):
            w = words("إن مع العسر يسرا mg إنسولين")
            self.assertEqual(len(LB.propose(w, FIXTURE_PAIRS, profile=p, threshold=0.5)), 1, p)

    # 9. back-map off
    def test_a_client_with_latin_backmap_false_gets_no_proposals(self):
        for off in (False, "false", "off", "no"):
            prof = {"domain": "general", "people": [], "latin_backmap": off}
            self.assertEqual(propose("الجسم بيطلع إنسولين mg كل يوم", profile=prof), [], off)
        for on in (True, None, "true"):
            prof = {"domain": "general", "people": [], "latin_backmap": on}
            self.assertEqual(len(propose("الجسم بيطلع إنسولين mg كل يوم", profile=prof)), 1, on)

    # 10. multi-word terms
    def test_a_multi_word_term_is_one_proposal_over_its_word_ids(self):
        props = propose("السكر عندي بلود شوجر high جدا")
        self.assertEqual(len(props), 1)
        p = props[0]
        self.assertEqual((p["word_ids"], p["from"], p["to"], p["latin"]), ([3, 4], "بلود شوجر", "blood sugar", "blood sugar"))
        self.assertEqual((p["start_ms"], p["end_ms"]), (800, 1500))
        self.assertEqual([(c["word_id"], c["from"], c["to"]) for c in p["corrections"]],
                         [(3, "بلود", "blood sugar"), (4, "شوجر", "")])

    def test_a_multi_word_term_with_a_clitic_on_its_first_word(self):
        self.assertEqual(propose("عندي والبلود شوجر high جدا")[0]["to"], "والـ blood sugar")

    def test_half_a_multi_word_term_is_not_a_hit(self):
        self.assertEqual(propose("عندي بلود كتير high جدا"), [])
        self.assertEqual(propose("قال إيه mg كده بس"), [], "«إيه» alone is everyday Arabic")

    def test_the_longest_term_with_the_same_first_word_wins(self):
        pairs = [{"latin": "blood", "arabic": ["بلود"], "domain": "medical", "source": "test"}] + FIXTURE_PAIRS
        props = propose("عندي بلود شوجر high جدا", pairs=pairs)
        self.assertEqual([(p["latin"], p["word_ids"]) for p in props], [("blood sugar", [2, 3])])
        props = propose("عندي بلود كتير high جدا", pairs=pairs)
        self.assertEqual([(p["latin"], p["word_ids"]) for p in props], [("blood", [2])])

    def test_the_longest_term_wins(self):
        pairs = FIXTURE_PAIRS + [{"latin": "GPT", "arabic": ["جي بي تي"], "domain": "ai", "source": "test"},
                                 {"latin": "ChatGPT", "arabic": ["شات جي بي تي"], "domain": "ai", "source": "test"}]
        props = propose("استخدمت شات جي بي تي و AI كتير", pairs=pairs)
        self.assertEqual([(p["latin"], p["word_ids"]) for p in props], [("ChatGPT", [2, 3, 4, 5])])

    def test_the_real_pair_list_maps_ai_and_insulin(self):
        pairs = LB.load_pairs()
        # AI's context: «الأنسولين», a pair-list term 3 words after it; insulin's: «جرعة» (medical), "mg"
        props = LB.propose(words("الدكتور قال إن إيه آي بيحسب جرعة الأنسولين mg"), pairs, profile=PLAIN, threshold=0.5)
        self.assertEqual([(p["latin"], p["to"]) for p in props], [("AI", "AI"), ("insulin", "الـ insulin")])

    # 11. hostile input
    def test_odd_unicode_inside_a_word_does_not_crash(self):
        for odd in ("إن‍سولين", "‏إنسولين‎", "⁧إنسولين⁩", "إنسولين﻿", "إنس​ولين"):
            props = propose(f"الجسم بيطلع {odd} mg كل يوم")
            self.assertEqual([p["latin"] for p in props], ["insulin"], repr(odd))
            self.assertEqual((props[0]["from"], props[0]["to"]), (odd, "insulin"))
        props = propose("الجسم بيطلع إنسولين،‏ mg كل يوم")       # a bidi mark after the comma
        self.assertEqual(props[0]["to"], "insulin،")
        for junk in ("", " ", "‍", "ـــ", "،", "ال", "و", "\U0001F600"):
            w = [{"id": 1, "word": junk, "start_ms": 0, "end_ms": 10, "probability": 0.9}]
            self.assertEqual(LB.propose(w, FIXTURE_PAIRS, profile=PLAIN, threshold=0.5), [], repr(junk))

    def test_bad_rows_are_skipped_not_fatal(self):
        w = words("الجسم بيطلع إنسولين mg كل يوم")
        bad = [None, 3, {"id": 99}, {"word": 5, "start_ms": 0, "end_ms": 1}, {"id": 98, "word": "x", "start_ms": "a"}]
        props = LB.propose(bad + w, FIXTURE_PAIRS, profile=PLAIN, threshold=0.5)
        self.assertEqual([p["word_ids"] for p in props], [[3]])

    def test_linear_time_on_a_long_transcript(self):
        unit = "الجسم بيطلع إنسولين mg كل يوم كلام عادي خالص هنا"
        def run(n):
            w = words(" ".join([unit] * n))
            t = time.perf_counter()
            props = LB.propose(w, FIXTURE_PAIRS, profile=PLAIN, threshold=0.5)
            return time.perf_counter() - t, len(props)
        run(50)                                          # warm the lexicon cache
        small, n_small = run(500)                        # 5,000 words
        big, n_big = run(5000)                           # 50,000 words
        self.assertEqual((n_small, n_big), (500, 5000))
        self.assertLess(big / max(small, 1e-3), 25, f"50k words took {big:.2f}s vs {small:.2f}s for 5k: not linear")

    # 12. determinism
    def test_same_input_same_proposals_in_the_same_order(self):
        text = "قال إيه آي و إنسولين و بالفيتامين mg و بلود شوجر high"
        a = propose(text)
        b = propose(text)
        self.assertEqual(a, b)
        self.assertEqual([p["word_ids"][0] for p in a], sorted(p["word_ids"][0] for p in a))
        shuffled = list(reversed(words(text)))
        self.assertEqual(LB.propose(shuffled, FIXTURE_PAIRS, profile=PLAIN, threshold=0.5), a, "input order ignored")

    def test_the_input_is_not_modified(self):
        w = words("الجسم بيطلع إنسولين mg كل يوم")
        before = copy.deepcopy(w)
        prof = {"domain": "general", "people": [{"name": "أمل"}]}
        pb = copy.deepcopy(prof)
        pairs = copy.deepcopy(FIXTURE_PAIRS)
        LB.propose(w, pairs, profile=prof, threshold=0.5)
        self.assertEqual((w, prof, pairs), (before, pb, FIXTURE_PAIRS))


class WriteProposals(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.paths = Paths(self.tmp / "C", "V1")
        self.tr = self.paths.p("02_transcription")
        self.tr.mkdir(parents=True)
        w = words("الجسم بيطلع إنسولين mg كل يوم و بالإنسولين برضه mg")
        (self.tr / "words.json").write_text(json.dumps({"meta": {"language": "ar"}, "words": w}, ensure_ascii=False,
                                                       indent=2), encoding="utf-8")
        (self.tr / "transcript.json").write_text(json.dumps({"segments": [], "text": "x"}), encoding="utf-8")
        (self.tr / "transcript-corrections.json").write_text('{"corrections": []}\n', encoding="utf-8")

    def snapshot(self):
        return {p.name: p.read_bytes() for p in sorted(self.tr.iterdir()) if p.name != "latin-proposals.json"}

    # 4. never applied
    def test_only_the_proposals_file_is_written(self):
        before = self.snapshot()
        res = LB.write_proposals(self.paths, profile=PLAIN, pairs=FIXTURE_PAIRS, threshold=0.5)
        self.assertEqual(self.snapshot(), before, "transcript, words and corrections stay byte-identical")
        self.assertEqual(sorted(p.name for p in self.tr.iterdir()),
                         ["latin-proposals.json", "transcript-corrections.json", "transcript.json", "words.json"])
        doc = json.loads((self.tr / "latin-proposals.json").read_text(encoding="utf-8"))
        self.assertEqual(doc["status"], "proposed")
        self.assertEqual([p["to"] for p in doc["proposals"]], ["insulin", "بالـ insulin"])
        self.assertIn("never applied", doc["note"])
        self.assertEqual(res["proposals"], 2)
        self.assertEqual(Path(res["file"]).name, "latin-proposals.json")

    def test_the_file_bytes_are_deterministic(self):
        LB.write_proposals(self.paths, profile=PLAIN, pairs=FIXTURE_PAIRS, threshold=0.5)
        a = (self.tr / "latin-proposals.json").read_bytes()
        time.sleep(0.05)                              # past the clock's resolution: a timestamp would show
        LB.write_proposals(self.paths, profile=PLAIN, pairs=FIXTURE_PAIRS, threshold=0.5)
        self.assertEqual((self.tr / "latin-proposals.json").read_bytes(), a)

    def test_the_file_names_the_words_it_was_made_from(self):
        import hashlib
        LB.write_proposals(self.paths, profile=PLAIN, pairs=FIXTURE_PAIRS, threshold=0.5)
        doc = json.loads((self.tr / "latin-proposals.json").read_text(encoding="utf-8"))
        self.assertEqual(doc["words_sha1"], hashlib.sha1((self.tr / "words.json").read_bytes()).hexdigest())
        self.assertEqual((doc["threshold"], doc["context_words"]), (0.5, 3))

    def test_back_map_off_writes_an_off_file_with_no_proposals(self):
        res = LB.write_proposals(self.paths, profile={"domain": "general", "latin_backmap": False},
                                 pairs=FIXTURE_PAIRS, threshold=0.5)
        doc = json.loads((self.tr / "latin-proposals.json").read_text(encoding="utf-8"))
        self.assertEqual((doc["status"], doc["proposals"], res["proposals"]), ("off", [], 0))

    def test_no_words_json_is_refused_and_writes_nothing(self):
        (self.tr / "words.json").unlink()
        before = self.snapshot()
        with self.assertRaises(Guidance):
            LB.write_proposals(self.paths, profile=PLAIN, pairs=FIXTURE_PAIRS, threshold=0.5)
        self.assertEqual(self.snapshot(), before)
        self.assertFalse((self.tr / "latin-proposals.json").exists())

    def test_a_words_list_file_is_read_too(self):
        (self.tr / "words.json").write_text(json.dumps(words("الجسم بيطلع إنسولين mg كل يوم"), ensure_ascii=False),
                                            encoding="utf-8")
        self.assertEqual(LB.write_proposals(self.paths, profile=PLAIN, pairs=FIXTURE_PAIRS, threshold=0.5)["proposals"], 1)

    def test_review_lines_list_every_proposal_for_the_editor(self):
        LB.write_proposals(self.paths, profile=PLAIN, pairs=FIXTURE_PAIRS, threshold=0.5)
        doc = json.loads((self.tr / "latin-proposals.json").read_text(encoding="utf-8"))
        lines = LB.review_lines(doc)
        text = "\n".join(lines)
        self.assertIn("Latin term proposals", lines[0])
        self.assertIn("بالـ insulin", text)
        self.assertIn("إنسولين", text)
        self.assertIn("never applied", text)
        self.assertEqual(LB.review_lines({"status": "off", "proposals": []})[1:2],
                         ["Off for this client (profile.json `latin_backmap: false`)."])
        self.assertEqual(LB.review_lines(None), [])
        self.assertEqual(lines[0], "## Latin term proposals — 2")
        self.assertIn("- `00:00:00.800` «إنسولين» → **insulin** (word 3, p=0.9)", lines)
        none = LB.review_lines({"status": "none", "proposals": [],
                                "skipped": [{"why": "no_context"}, {"why": "no_context"}, {"why": "name"}]})
        self.assertEqual(none[0], "## Latin term proposals — 0")
        self.assertIn("- none", none)
        self.assertIn("Not proposed: 1 × a person's or the client's name; 2 × no English or domain word near it", none)


class PairList(unittest.TestCase):
    # 13. structure, duplicates, provenance
    def test_the_shipped_pair_list_is_clean(self):
        doc = json.loads(REAL_PAIRS.read_text(encoding="utf-8"))
        self.assertEqual(LB.check_pairs(doc), [])
        self.assertGreaterEqual(len(doc["terms"]), 5)
        for t in doc["terms"]:
            self.assertEqual(set(t) - {"latin", "arabic", "domain", "source"}, set())
        self.assertIn("No third-party word list", doc["provenance"])
        self.assertEqual(LB.load_pairs(), doc["terms"])

    def test_every_shipped_latin_term_and_spelling_is_in_our_own_lexicon(self):
        from lib import review_domains as RD
        doc = json.loads(REAL_PAIRS.read_text(encoding="utf-8"))
        for t in doc["terms"]:
            lex = RD.lexicon(t["domain"])
            terms = [x for r in lex["rules"] + lex.get("supporting", []) for x in r.get("terms", [])]
            low = [x.rstrip("*").casefold() for x in terms]
            self.assertIn(t["latin"].casefold(), low, t)
            self.assertIn(t["source"].split("#")[0], f"lexicons/{t['domain']}.json")
            for a in t["arabic"]:
                self.assertIn(RD.normalize(a), [RD.normalize(x.rstrip("*")) for x in terms], a)

    def test_structure_problems_are_named(self):
        good = {"schema": 1, "terms": [{"latin": "insulin", "arabic": ["أنسولين"], "domain": "medical",
                                        "source": "lexicons/medical.json#treatment"}]}
        self.assertEqual(LB.check_pairs(good), [])
        bad = [
            ({"schema": 2, "terms": []}, "schema"),
            ({"schema": 1}, "terms"),
            ({"schema": 1, "terms": [{"arabic": ["أنسولين"], "domain": "medical", "source": "x"}]}, "latin"),
            ({"schema": 1, "terms": [{"latin": "insulin", "arabic": [], "domain": "medical", "source": "x"}]}, "arabic"),
            ({"schema": 1, "terms": [{"latin": "insulin", "arabic": ["insulin"], "domain": "medical", "source": "x"}]},
             "Arabic letters"),
            ({"schema": 1, "terms": [{"latin": "انسولين", "arabic": ["أنسولين"], "domain": "medical", "source": "x"}]},
             "Latin letters"),
            ({"schema": 1, "terms": [{"latin": "insulin", "arabic": ["أنسولين"], "domain": "nope", "source": "x"}]},
             "domain"),
            ({"schema": 1, "terms": [{"latin": "insulin", "arabic": ["أنسولين"], "domain": "medical"}]}, "source"),
        ]
        for doc, word in bad:
            probs = LB.check_pairs(doc)
            self.assertTrue(probs, doc)
            self.assertTrue(any(word in p for p in probs), (word, probs))

    def test_one_arabic_spelling_never_maps_to_two_latin_terms(self):
        doc = {"schema": 1, "terms": [
            {"latin": "insulin", "arabic": ["أنسولين"], "domain": "medical", "source": "lexicons/medical.json#treatment"},
            {"latin": "vitamin", "arabic": ["انسولين"], "domain": "medical", "source": "lexicons/medical.json#treatment"}]}
        self.assertTrue(any("two Latin terms" in p for p in LB.check_pairs(doc)), LB.check_pairs(doc))

    def test_a_term_not_in_our_lexicons_fails_the_provenance_check(self):
        doc = {"schema": 1, "terms": [{"latin": "blood sugar", "arabic": ["بلود شوجر"], "domain": "medical",
                                       "source": "lexicons/medical.json#condition"}]}
        probs = LB.check_pairs(doc)
        self.assertTrue(any("blood sugar" in p and "lexicon" in p for p in probs), probs)
        self.assertTrue(any("بلود شوجر" in p for p in probs), probs)

    def test_the_glossary_is_a_valid_source(self):
        doc = {"schema": 1, "terms": [{"latin": "metformin", "arabic": ["ميتفورمين"], "domain": "medical",
                                       "source": "medical-glossary.json"}]}
        self.assertTrue(LB.check_pairs(doc))
        gl = {"terms": {"english": ["Metformin"], "arabic": ["ميتفورمين"]}}
        self.assertEqual(LB.check_pairs(doc, glossary=gl), [])

    def test_a_broken_pair_file_is_refused_on_load(self):
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp, True)
        f = tmp / "latin-terms.json"
        f.write_text(json.dumps({"schema": 1, "terms": [{"latin": "x"}]}), encoding="utf-8")
        with self.assertRaises(Guidance):
            LB.load_pairs(f)


if __name__ == "__main__":
    unittest.main()
