# SPDX-License-Identifier: GPL-3.0-or-later
# © 2026 The Why Not AI (thewhynot.ai)
"""Manual verse, fix round 1 (review c2c23e6, executor rulings): the 12 s cap never leaves a verse captioned; words
of a verse cut away whole are never named; the risk-first order never brings verse words back;
the recitation cue is a class («قال/يقول» + a divine name + honorifics); a hook title never shows the basmala; the
P3 items about verse words reaching a surface (owner decision 2026-10-19: P2-1 and the graphic part of P2-5 dropped).
The fixture verse is a placeholder (tests/fixtures/manual_verse/speech.json).
Run:  bash tools/test.sh -p test_manual_verse_fix1.py
"""
import sys as _sys
_sys.dont_write_bytecode = True  # keep the plugin folder free of __pycache__
import _isolation  # noqa: F401,E402  G79: sandbox the engine home first (tests/_isolation.py)
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys = _sys
SK = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SK / "engine" / "reel"))
sys.path.insert(0, str(SK / "tests"))

from lib import common  # noqa: E402
from lib.common import Paths, read_json, write_json  # noqa: E402
from test_manual_verse import (RELEASE, SC, VERSE, Base, build_words, cfg, decision, has_verse,  # noqa: E402
                               verse_project, verse_window, word_at)


def MV():
    from lib import manual_verse
    return manual_verse


def NY():
    from lib import needs_you
    return needs_you


def words_at(spec: list) -> list:
    """Words from (text, start, end) triples (exact times, for the boundary pins)."""
    return [{"id": i + 1, "word": t, "start_ms": a, "end_ms": b, "probability": 0.9} for i, (t, a, b) in enumerate(spec)]


LONG = "اهلا بيكم قال تعالى " + " ".join(VERSE * 8) + " |900 تمام. وده كلام جميل"   # 16 s of recitation, no pause
# (fix round 2: «تمام.» closes the held run after the verse, so the commentary after it is captioned)


# --------------------------------------------------------------------------- P1-1 the cap
class TestCap(unittest.TestCase):
    def test_cap_runs_to_the_first_pause_after_it(self):
        w = build_words(LONG)
        s = MV().detect(w, cfg())
        self.assertEqual([(x["src_start_ms"], x["src_end_ms"], x["end"], x["guessed_end"]) for x in s],
                         [(w[4]["start_ms"], word_at(w, "قمر", 7)["end_ms"], "cap_pause", True)])

    def test_cap_boundary_pinned(self):
        # one recited word exactly 12 000 ms long is not capped; 12 001 ms is (then: to the next pause)
        for length, guessed in ((12000, False), (12001, True)):
            w = words_at([("قال", 0, 300), ("تعالى", 350, 650), ("شجرة", 700, 700 + length),
                          ("وده", 700 + length + 900, 700 + length + 1200)])
            s = MV().detect(w, cfg())
            self.assertEqual([(x["src_end_ms"], x["guessed_end"]) for x in s], [(700 + length, guessed)], length)

    def test_pause_boundary_pinned(self):
        for gap, end_word in ((700, 2), (699, 4)):
            w = words_at([("قال", 0, 300), ("تعالى", 350, 650), ("شجرة", 700, 1050),
                          ("نهر", 1050 + gap, 1400 + gap), ("جبل", 1450 + gap, 1800 + gap), ("وده", 3000 + gap, 3300 + gap)])
            s = MV().detect(w, cfg())
            self.assertEqual([x["src_end_ms"] for x in s], [w[end_word]["end_ms"] if end_word != 2 else 1050], gap)

    def test_hard_limit_then_end_of_sentence(self):
        words = VERSE * 32                                   # 160 words, 64 s, no pause
        words[155] = words[155] + "."                        # a sentence ends at ~62 s
        w = build_words("قال تعالى " + " ".join(words) + " " + " ".join(VERSE) + " |900 وده")
        s = MV().detect(w, cfg())
        self.assertEqual([(x["src_end_ms"], x["end"], x["guessed_end"]) for x in s],
                         [(w[2 + 155]["end_ms"], "cap_sentence", True)])
        self.assertGreater(s[0]["src_end_ms"] - s[0]["src_start_ms"], MV().HARD_MS)

    def test_a_sentence_end_before_the_hard_limit_does_not_end_it(self):
        words = VERSE * 32                                   # mutation survivor A5
        words[50] = words[50] + "."                          # ~20 s: past the cap, before the hard limit
        words[155] = words[155] + "."
        w = build_words("قال تعالى " + " ".join(words) + " " + " ".join(VERSE) + " |900 وده")
        self.assertEqual([x["src_end_ms"] for x in MV().detect(w, cfg())], [w[2 + 155]["end_ms"]])

    def test_speech_ends_after_the_cap_is_guessed(self):
        w = build_words("قال تعالى " + " ".join(VERSE * 8))  # mutation survivor A7
        self.assertEqual([(x["end"], x["guessed_end"]) for x in MV().detect(w, cfg())], [("speech_end", True)])

    def test_turn_change_ends_the_span(self):
        w = build_words("قال تعالى " + " ".join(VERSE * 8) + " وده كلام")
        for x in w:
            x["speaker"] = "A"
        w[-2]["speaker"] = w[-1]["speaker"] = "B"
        s = MV().detect(w, cfg())
        self.assertEqual([(x["src_end_ms"], x["end"], x["guessed_end"]) for x in s], [(w[-3]["end_ms"], "cap_turn", True)])


class TestCapPlan(Base):
    def test_no_verse_word_captioned_after_the_cap(self):
        w = build_words(LONG)
        root, p = verse_project(self.tmp, w)
        res, spec = self.compile(p)
        from lib import srt as srtlib
        for name in ("captions-short-seq", "subtitles-seq"):
            txt = " ".join(c["text"] for c in srtlib.read_srt(p.p(f"02_transcription/{name}.srt")))
            self.assertEqual(has_verse(txt), [], name)
            self.assertIn("جميل", txt)
        self.assertTrue(spec["manual_verse"][0]["guessed_end"])
        it = [i for i in NY().collect(root)["items"] if i["kind"] == "verse"]
        self.assertEqual(len(it), 1)
        self.assertIn("متخمّنة", it[0]["text_ar"])
        self.assertTrue(it[0]["span"]["guessed_end"])

    def test_publish_srt_after_the_cap(self):
        from lib.episode import EpisodePaths
        from lib.transcribe import finalize
        w = build_words(LONG)
        root = self.tmp / "CLIENT"
        for d in ("assets", "data"):
            (root / d).mkdir(parents=True, exist_ok=True)
        common.set_context(root)
        ep = EpisodePaths(root, "EP12")
        ep.ensure_project()
        segs = [{"id": 1, "start_ms": w[0]["start_ms"], "end_ms": w[-1]["end_ms"], "text": " ".join(x["word"] for x in w),
                 "avg_logprob": -0.2, "no_speech_prob": 0.01, "compression_ratio": 1.2, "words": [x["id"] for x in w]}]
        finalize(ep, {"source_video": "x", "backend": "test", "model": "none", "language": "ar",
                      "language_probability": 1.0, "duration_ms": 60000}, segs, [dict(x) for x in w])
        write_json(ep.p("publish/publish.json"), {"youtube": {"titles": ["أ", "ب", "ج"]}})
        from lib import publish
        publish.check(ep)
        srt = ep.p("publish/EP12.srt").read_text(encoding="utf-8")
        self.assertEqual(has_verse(srt), [])
        self.assertIn("جميل", srt)


# --------------------------------------------------------------------------- P1-2 a verse cut away whole
class TestCutAway(Base):
    def project(self, **kw):
        w = build_words(SC["recited"])
        a, b = verse_window(w)
        dur = w[-1]["end_ms"] + 1000
        kw.setdefault("extra", RELEASE)
        root, p = verse_project(self.tmp, w, flags={"سحاب", "مفتاح"},
                                glob={"remove_pauses": True,                    # a cut word inside it: survivor E6
                                      "cut_words": [{"word_ids": [word_at(w, "نهر")["id"]], "reason": "x"}]},
                                pauses={"keep_ms": [[0, a - 30], [b + 30, dur]], "cuts_ms": [[a - 30, b + 30]]}, **kw)
        return w, a, b, root, p

    def test_cut_away_verse_words_never_named(self):
        _w, a, b, root, p = self.project()
        res, spec = self.compile(p)
        self.assertNotIn("manual_verse", spec)
        self.assertEqual([(x["id"], x["src_start_ms"], x["src_end_ms"]) for x in spec["verse_cut"]], [("MV01", a, b)])
        for f in ("01_analysis/plan-validation.json", "01_analysis/edit-plan.md", "01_analysis/timeline-spec.json"):
            self.assertEqual(has_verse(p.p(f).read_text(encoding="utf-8")), [], f)
        doc = NY().collect(root)
        self.assertEqual(has_verse(json.dumps(doc, ensure_ascii=False)), [])
        self.assertIn("مفتاح", json.dumps(doc, ensure_ascii=False))           # the word outside the verse still is
        self.assertEqual([i for i in doc["items"] if i["kind"] == "verse"], [])    # nothing to add: it is not in the reel

    def test_evidence_not_found_inside_a_verse_is_not_quoted(self):
        w = build_words(SC["recited"])
        a, b = verse_window(w)
        d = decision("EDIT_001", "GFX_001", a, b, "شجرةٌ مختلفة نهر", "كلام", template="glass_card")
        _root, p = verse_project(self.tmp, w, decisions=[d])
        from lib.plan import compile_plan
        res = compile_plan(p)
        self.assertFalse(res["ok"])
        ev = [e for e in res["errors"] if e.startswith("EDIT_001: evidence")]
        self.assertEqual(len(ev), 1, res["errors"])
        self.assertIn("MV01", ev[0])
        self.assertEqual(has_verse(" ".join(res["errors"] + res["warnings"])), [])


# --------------------------------------------------------------------------- P1-3 the risk-first order
class TestRiskOrder(Base):
    SPEECH = "اهلا بيكم النهارده هنتكلم عن الصبر قال تعالى شجرة ٥٠ مجم جبل ٣ حباية قمر |900 وده معناه ان الصبر مفتاح"

    def run_case(self, switch: bool, graphic=False):
        w = build_words(self.SPEECH)
        for x in w:
            if x["word"] in ("٥٠", "مجم", "٣", "حباية"):
                x["probability"] = 0.4
        decs = []
        if graphic:
            s, e = word_at(w, "وده")["start_ms"], w[-1]["end_ms"]
            decs = [decision("EDIT_001", "GFX_001", s, e, "وده معناه ان الصبر", "٥٠ مجم", template="stat_card",
                             value="٥٠ مجم")]
        root, p = verse_project(self.tmp, w, flags={"مفتاح"}, decisions=decs, extra=RELEASE)
        write_json(root / common.CLIENT_PROFILE_REL / "safety.json", {"switches": {"k_t1_plan_block": switch}})
        from lib.plan import compile_plan
        res = compile_plan(p)
        return root, p, res

    def test_switch_on_and_off_never_requotes_verse_words(self):
        for switch in (False, True):
            with self.subTest(switch=switch):
                self.tmp = Path(tempfile.mkdtemp(dir=self._td.name))
                root, _p, res = self.run_case(switch)
                self.assertTrue(res["ok"], res["errors"])
                words = [i for i in NY().collect(root)["items"] if i["kind"] == "words"]
                self.assertEqual(len(words), 1, words)
                for bad in ("٥٠", "مجم", "حباية", "«٣»"):
                    self.assertNotIn(bad, words[0]["text_ar"])
                self.assertIn("مفتاح", words[0]["text_ar"])

    def test_the_risk_order_still_runs_outside_the_verse(self):
        # mutation survivor F1: a risky word OUTSIDE the verse that only the risk-first order lists (0.6: above
        # today's 0.5 threshold, under the risk threshold) is listed with the switch ON, not OFF
        self.SPEECH = TestRiskOrder.SPEECH + ' وخد ٢ حباية كل يوم'
        for switch in (False, True):
            with self.subTest(switch=switch):
                self.tmp = Path(tempfile.mkdtemp(dir=self._td.name))
                w = build_words(self.SPEECH)
                for x in w[-4:-2]:
                    x['probability'] = 0.6
                root, p = verse_project(self.tmp, w, flags={'مفتاح'}, extra=RELEASE)
                write_json(root / common.CLIENT_PROFILE_REL / 'safety.json', {'switches': {'k_t1_plan_block': switch}})
                from lib.plan import compile_plan
                compile_plan(p)
                txt = ' '.join(i['text_ar'] for i in NY().collect(root)['items'] if i['kind'] == 'words')
                self.assertEqual('«٢»' in txt, switch, txt)
                self.assertNotIn('مجم', txt)

    def test_plan_block_error_masks_a_verse_word(self):
        _root, _p, res = self.run_case(True, graphic=True)
        risk = [e for e in res["errors"] if e.startswith("GFX_001")]
        self.assertTrue(risk, res["errors"])
        for e in risk:
            self.assertNotIn("مجم", e)                       # the risk word sits inside MV01: named by id and time only
            self.assertIn("MV01", e)


# --------------------------------------------------------------------------- P2-2 the cue class
class TestCueClass(unittest.TestCase):
    FIRE = ("قال سبحانه وتعالى", "قال الله عز وجل", "قال الله سبحانه وتعالى", "يقول الحق سبحانه", "قال ربنا",
            "قال جل وعلا",                                            # the reviewer's missed forms
            "قال المولى عز وجل", "وقال ربنا سبحانه وتعالى في كتابه الكريم", "يقول الله تبارك وتعالى", "قال رب العزة",
            "قال تعالى", "قوله تعالى", "فقال الله تعالى")
    QUIET = ("قال والله", "قال الحق", "قال رب البيت", "آية", "قال لي", "سورة البقرة", "في الآية دي", "والله قال لي",
             "ربنا بيقول")                             # a name first: everyday paraphrase, left to the story-editor

    def test_class_fires(self):
        for cue in self.FIRE:
            w = build_words(f"اهلا بيكم {cue} شجرة نهر جبل سحاب قمر |900 وده كلام")
            s = MV().detect(w, cfg(False))
            self.assertEqual([(x["src_start_ms"], x["src_end_ms"]) for x in s], [verse_window(w)], cue)
            self.assertEqual(s[0]["cue"], "say", cue)
            self.assertIn(MV().tokens(cue)[-1], MV().tokens(s[0]["cue_text"]), cue)

    def test_class_stays_quiet(self):
        for cue in self.QUIET:
            w = build_words(f"اهلا بيكم {cue} شجرة نهر جبل سحاب قمر |900 وده كلام")
            self.assertEqual(MV().detect(w, cfg(False)), [], cue)

    def test_zero_width_space_inside_a_token(self):
        w = build_words("اهلا قال تعالى شجرة نهر جبل |900 وده")
        w[1]["word"] = "قال​تعالى"
        del w[2]
        self.assertEqual(len(MV().detect(w, cfg(False))), 1)


# --------------------------------------------------------------------------- P2-5 (text part) the basmala on a hook
class TestBasmalaHook(Base):
    def test_hook_text_with_the_basmala_is_rewritten(self):
        # the hook runs past the verse (it is shortened to the part after it, today's rule); its own text loses the
        # basmala, with a warning (owner decision 2026-10-19: only the text rewrite of P2-5)
        w = build_words("بسم الله الرحمن الرحيم النهارده هنتكلم عن السكر والضغط |900 وازاي نتابعهم كل يوم في البيت")
        d = decision("EDIT_001", "GFX_001", w[0]["start_ms"], w[-1]["end_ms"],
                     "وازاي نتابعهم كل يوم", "بسم الله الرحمن الرحيم وازاي نتابعهم", template="hook_title")
        _root, p = verse_project(self.tmp, w, domain="medical", decisions=[d])
        res, spec = self.compile(p)
        ev = [e for e in spec["events"] if e["event_id"] == "GFX_001"]
        self.assertEqual([e["params"]["text"] for e in ev], ["وازاي نتابعهم"])
        self.assertTrue(any("GFX_001" in x and "basmala" in x for x in res["warnings"]), res["warnings"])
        self.assertNotIn("الرحيم", json.dumps(spec["events"], ensure_ascii=False))


# --------------------------------------------------------------------------- P3
class TestP3(Base):
    def test_note_stays_in_the_spec_only(self):
        w = build_words(SC["plain"])
        note = "ملاحظة_الستوري_إديتور"
        root, p = verse_project(self.tmp, w, domain=None,
                                extra={"manual_verse": [{"start_ms": w[3]["start_ms"], "end_ms": w[5]["end_ms"],
                                                         "note": note}]})
        _res, spec = self.compile(p)
        self.assertEqual(spec["manual_verse"][0]["note"], note)
        self.assertNotIn(note, json.dumps(spec["markers"], ensure_ascii=False))
        self.assertNotIn(note, p.p("01_analysis/edit-plan.md").read_text(encoding="utf-8"))
        self.assertNotIn(note, json.dumps(NY().collect(root), ensure_ascii=False))

    def test_publish_tags_are_checked(self):
        from lib.episode import EpisodePaths
        from lib.transcribe import finalize
        w = build_words(SC["recited"])
        root = self.tmp / "CLIENT"
        for d in ("assets", "data"):
            (root / d).mkdir(parents=True, exist_ok=True)
        write_json(root / common.CLIENT_PROFILE_REL / "profile.json", {"domain": "religious"})
        common.set_context(root)
        ep = EpisodePaths(root, "EP12")
        ep.ensure_project()
        segs = [{"id": 1, "start_ms": w[0]["start_ms"], "end_ms": w[-1]["end_ms"], "text": " ".join(x["word"] for x in w),
                 "avg_logprob": -0.2, "no_speech_prob": 0.01, "compression_ratio": 1.2, "words": [x["id"] for x in w]}]
        finalize(ep, {"source_video": "x", "backend": "test", "model": "none", "language": "ar",
                      "language_probability": 1.0, "duration_ms": 60000}, segs, [dict(x) for x in w])
        write_json(ep.p("publish/publish.json"), {"youtube": {"titles": ["أ", "ب", "ج"], "tags": ["شجرة نهر جبل"]}})
        from lib import publish
        res = publish.check(ep)
        self.assertTrue(any(e.startswith("tag") and "verse" in e for e in res["errors"]), res["errors"])

    def test_episode_words_skip_a_reels_editor_span(self):
        from lib.episode import EpisodePaths
        from lib.transcribe import finalize
        w = build_words(SC["plain"])
        w[4]["flagged"] = {"note": "unsure"}
        root = self.tmp / "CLIENT"
        for d in ("assets", "data"):
            (root / d).mkdir(parents=True, exist_ok=True)
        common.set_context(root)
        ep = EpisodePaths(root, "EP12")
        ep.ensure_project()
        segs = [{"id": 1, "start_ms": w[0]["start_ms"], "end_ms": w[-1]["end_ms"], "text": " ".join(x["word"] for x in w),
                 "avg_logprob": -0.2, "no_speech_prob": 0.01, "compression_ratio": 1.2, "words": [x["id"] for x in w]}]
        finalize(ep, {"source_video": "x", "backend": "test", "model": "none", "language": "ar",
                      "language_probability": 1.0, "duration_ms": 60000}, segs, [dict(x) for x in w])
        # a reel cut from 1 s of the episode, whose plan has the story-editor's span over the flagged word
        rp = Paths(root, "EP12_R01")
        rp.ensure_project()
        write_json(rp.p("00_inputs/source.json"), {"kind": "episode_reel", "episode_id": "EP12", "in_ms": 1000})
        a, b = w[4]["start_ms"] - 1000, w[4]["end_ms"] - 1000
        write_json(rp.p("01_analysis/timeline-spec.json"), {
            "events": [], "source_in_ms": 1000, "music": {"status": "PLACED"},
            "manual_verse": [{"id": "MV01", "src_start_ms": a, "src_end_ms": b, "start_ms": a, "end_ms": b}]})
        doc = NY().collect(root)
        ep_words = [i for i in doc["items"] if i["kind"] == "words" and i["item"] == "EP12"]
        self.assertEqual(ep_words, [])
        # and the episode's upload SRT leaves that span out too
        write_json(ep.p("publish/publish.json"), {"youtube": {"titles": ["أ", "ب", "ج"]}})
        from lib import publish
        publish.check(ep)
        srt = ep.p("publish/EP12.srt").read_text(encoding="utf-8").split()
        self.assertNotIn(w[4]["word"], srt)
        self.assertIn(w[5]["word"], srt)


class TestSkillText(unittest.TestCase):
    def test_no_skill_promises_a_verse_on_screen(self):
        for rel in ("skills/medical-accuracy/SKILL.md", "skills/motion/SKILL.md", "skills/podcast/SKILL.md"):
            t = (SK / rel).read_text(encoding="utf-8")
            self.assertNotIn("Quran wording from the Mushaf", t, rel)
            self.assertNotIn("every verse,", t, rel)


if __name__ == "__main__":
    unittest.main()
