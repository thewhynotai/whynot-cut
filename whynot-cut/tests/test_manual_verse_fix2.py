# SPDX-License-Identifier: GPL-3.0-or-later
# © 2026 The Why Not AI (thewhynot.ai)
"""Manual verse, fix round 2 (review 91cd197, executor and plan-session rulings): a verse's first word (a divine name,
«ربنا», «تبارك», «سبحانه») is never taken into the cue; a verse cut away whole leaves no word in the -seq captions
and no graphic repeating it; after a span that ends on a pause the next caption run is HELD (fail-closed) until the
editor releases it (`manual_verse_release`); the NEEDS-YOU line always says to check the words right after a span;
the two surviving mutants of round 1; the P3s (invisible joiners, «قال الله يرحمه», the basmala on every graphic and
in the publish copy, the agent texts).
The fixture verse is a placeholder (tests/fixtures/manual_verse/speech.json): no Quran text.
Run:  bash tools/test.sh -p test_manual_verse_fix2.py
"""
import sys as _sys
_sys.dont_write_bytecode = True  # keep the plugin folder free of __pycache__
import _isolation  # noqa: F401,E402  G79: sandbox the engine home first (tests/_isolation.py)
import json
import unittest
from pathlib import Path

sys = _sys
SK = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SK / "engine" / "reel"))
sys.path.insert(0, str(SK / "tests"))

from lib import common  # noqa: E402
from lib.common import read_json, write_json  # noqa: E402
from test_manual_verse import (SC, VERSE, Base, build_words, cfg, decision, has_verse, verse_project,  # noqa: E402
                               verse_window, word_at)


def MV():
    from lib import manual_verse
    return manual_verse


def NY():
    from lib import needs_you
    return needs_you


def srt_text(p, name: str) -> str:
    from lib import srt as srtlib
    f = p.p(f"02_transcription/{name}.srt")
    return " ".join(c["text"] for c in srtlib.read_srt(f)) if f.exists() else ""


AFTER = "|900 وده معناه ان الصبر مفتاح كل خير في حياتنا كلها"     # the commentary after the verse (held)
HELD = ("وده", "معناه", "مفتاح", "خير", "حياتنا", "كلها")


def held_in(text: str) -> list:
    return [h for h in HELD if h in str(text).split() or f" {h} " in f" {text} "]


# --------------------------------------------------------------------------- P1-1 the verse's first word
class TestFirstWord(unittest.TestCase):
    LEADS = ("ربنا", "الله", "تبارك", "سبحانه")

    def test_lead_after_an_honorific_opens_the_span(self):
        for lead in self.LEADS:
            w = build_words(f"اهلا بيكم قال تعالى {lead} شجرة نهر جبل سحاب قمر |900 وده كلام")
            s = MV().detect(w, cfg(False))
            self.assertEqual([(x["src_start_ms"], x["src_end_ms"]) for x in s],
                             [(word_at(w, lead)["start_ms"], word_at(w, "قمر")["end_ms"])], lead)
            self.assertEqual(s[0]["cue_text"], "قال تعالى", lead)

    def test_a_second_name_after_a_name_opens_the_span(self):
        w = build_words("اهلا قال الله ربنا شجرة نهر جبل |900 وده")
        s = MV().detect(w, cfg(False))
        self.assertEqual([(x["src_start_ms"], x["cue_text"]) for x in s], [(word_at(w, "ربنا")["start_ms"], "قال الله")])

    def test_tabarak_right_after_the_verb_opens_the_span(self):
        w = build_words("اهلا قال تبارك شجرة نهر جبل |900 وده")
        s = MV().detect(w, cfg(False))
        self.assertEqual([(x["src_start_ms"], x["cue_text"]) for x in s], [(word_at(w, "تبارك")["start_ms"], "قال")])

    def test_honorific_pairs_stay_in_the_cue(self):
        for cue in ("يقول الله تبارك وتعالى", "قال تبارك وتعالى", "قال الله جل جلاله", "قال الله عز وجل",
                    "قال سبحانه وتعالى", "قال جل وعلا"):
            w = build_words(f"اهلا {cue} شجرة نهر جبل سحاب قمر |900 وده")
            s = MV().detect(w, cfg(False))
            self.assertEqual([x["src_start_ms"] for x in s], [word_at(w, "شجرة")["start_ms"]], cue)
            self.assertEqual(s[0]["cue_text"], cue, cue)


class TestFirstWordPlan(Base):
    def test_no_surface_shows_the_lead_word(self):
        for lead in TestFirstWord.LEADS:
            with self.subTest(lead=lead):
                import tempfile
                self.tmp = Path(tempfile.mkdtemp(dir=self._td.name))
                w = build_words(f"اهلا بيكم النهارده هنتكلم عن الصبر قال تعالى {lead} شجرة نهر جبل سحاب قمر {AFTER}")
                root, p = verse_project(self.tmp, w)
                _res, spec = self.compile(p)
                for name in ("captions-short-seq", "subtitles-seq"):
                    txt = srt_text(p, name)
                    self.assertNotIn(lead, txt.split(), name)
                    self.assertEqual(has_verse(txt), [], name)
                    self.assertIn("هنتكلم", txt)
                surfaces = {"markers": json.dumps(spec["markers"], ensure_ascii=False),
                            "spec manual_verse": json.dumps(spec["manual_verse"], ensure_ascii=False),
                            "edit-plan": p.p("01_analysis/edit-plan.md").read_text(encoding="utf-8"),
                            "needs-you": " ".join(i["text_ar"] + " " + i["text"] for i in NY().collect(root)["items"]
                                                  if i["kind"] == "verse")}
                for where, txt in surfaces.items():
                    self.assertNotIn(lead, txt, where)
                self.assertEqual(spec["manual_verse"][0]["src_start_ms"], word_at(w, lead)["start_ms"])
                self.assertIn("بعد: قال تعالى", spec["markers"][0]["comment"])


# --------------------------------------------------------------------------- P3 cue class: invisible joiners, du'a
class TestCueEdges(unittest.TestCase):
    def test_invisible_joiners_between_or_inside_cue_words(self):
        for zw in ("\u200c", "\u200d", "\ufeff"):
            for word, drop in ((f"قال{zw}تعالى", True), (f"تعا{zw}لى", False), (f"{zw}قال", False)):
                w = build_words("اهلا قال تعالى شجرة نهر جبل |900 وده")
                if drop:
                    w[1]["word"] = word
                    del w[2]
                else:
                    w[2 if word.startswith("تعا") else 1]["word"] = word
                s = MV().detect(w, cfg(False))
                self.assertEqual([x["src_start_ms"] for x in s], [word_at(w, "شجرة")["start_ms"]], repr(word))

    def test_dua_after_the_name_is_not_a_citation(self):
        for cue in ("قال الله يرحمه", "قال ربنا يستر", "وقال ربنا يخليك", "قال الله يسامحه"):
            w = build_words(f"اهلا بيكم {cue} شجرة نهر جبل |900 وده كلام")
            self.assertEqual(MV().detect(w, cfg(False)), [], cue)

    def test_dua_word_after_an_honorific_still_fires(self):
        w = build_words("اهلا قال الله تعالى يرحمه شجرة |900 وده")
        self.assertEqual([x["src_start_ms"] for x in MV().detect(w, cfg(False))], [word_at(w, "يرحمه")["start_ms"]])

    def test_biyqul_fires(self):
        # round-1 survivor M16: «بيقول» dropped from the verbs
        w = build_words("اهلا بيقول الله تعالى شجرة نهر جبل |900 وده")
        self.assertEqual([x["src_start_ms"] for x in MV().detect(w, cfg(False))], [word_at(w, "شجرة")["start_ms"]])


# --------------------------------------------------------------------------- P1-2 a verse cut away whole
class TestCutAwaySeq(Base):
    def project(self, cut_word=True, decisions=()):
        w = build_words(SC["recited"])
        a, b = verse_window(w)
        dur = w[-1]["end_ms"] + 1000
        glob = {"remove_pauses": True}
        if cut_word:
            glob["cut_words"] = [{"word_ids": [word_at(w, "نهر")["id"]], "reason": "x"}]
        root, p = verse_project(self.tmp, w, glob=glob, decisions=decisions,
                                pauses={"keep_ms": [[0, a - 30], [b + 30, dur]], "cuts_ms": [[a - 30, b + 30]]})
        return w, a, b, root, p

    def test_seq_srts_hold_no_word_of_it(self):
        for cut_word in (True, False):
            with self.subTest(cut_word=cut_word):
                import tempfile
                self.tmp = Path(tempfile.mkdtemp(dir=self._td.name))
                _w, _a, _b, _root, p = self.project(cut_word)
                _res, spec = self.compile(p)
                self.assertEqual([x["id"] for x in spec["verse_cut"]], ["MV01"])
                for name in ("captions-short-seq", "subtitles-seq"):
                    txt = srt_text(p, name)
                    self.assertEqual(has_verse(txt), [], name)
                    self.assertIn("هنتكلم", txt, name)
                sw = read_json(p.p("02_transcription/words-seq.json"))["words"]
                self.assertEqual([x for x in sw if x["word"] in VERSE], [])

    def test_graphic_repeating_a_cut_verse_is_dropped(self):
        w = build_words(SC["recited"])
        s = word_at(w, "هنتكلم")["start_ms"]
        d = decision("EDIT_001", "GFX_001", s, word_at(w, "الصبر")["end_ms"], "هنتكلم عن الصبر", "شجرة نهر جبل",
                     template="glass_card")
        _w, _a, _b, _root, p = self.project(False, decisions=[d])
        res, spec = self.compile(p)
        self.assertNotIn("GFX_001", [e["event_id"] for e in spec["events"]])
        self.assertTrue(any("GFX_001" in x for x in res["warnings"]), res["warnings"])

    def test_evidence_repeating_a_cut_verse_is_never_printed(self):
        # round-1 survivor M10: the evidence filter falling back to the live spans only
        w = build_words(SC["recited"])
        s = word_at(w, "هنتكلم")["start_ms"]
        d = decision("EDIT_001", "GFX_001", s, word_at(w, "الصبر")["end_ms"], "شجرة نهر جبل", "الصبر")
        _w, _a, _b, _root, p = self.project(False, decisions=[d])
        _res, spec = self.compile(p)
        ev = [e for e in spec["events"] if e["event_id"] == "GFX_001"]
        self.assertEqual([e["evidence"] for e in ev], [MV().PLACEHOLDER])
        self.assertEqual(has_verse(p.p("01_analysis/timeline-spec.json").read_text(encoding="utf-8")), [])


# --------------------------------------------------------------------------- P2-1 the hold after a pause
class TestHoldDetect(unittest.TestCase):
    def spans(self, text, ed=None):
        w = build_words(text)
        spans, _e, _w = MV().resolve(MV().detect(w, cfg(False)), ed or {})
        return w, spans, MV().held(spans, w, ed or {})

    def test_hold_runs_to_the_sentence_end(self):
        w, _s, (holds, errs, warns) = self.spans("اهلا قال تعالى شجرة نهر جبل |900 وده معناه. ان الصبر مفتاح")
        self.assertEqual([(h["id"], h["after"], h["src_start_ms"], h["src_end_ms"], h["end"]) for h in holds],
                         [("MV01H", "MV01", word_at(w, "وده")["start_ms"], word_at(w, "معناه.")["end_ms"], "sentence")])
        self.assertEqual((errs, warns), ([], []))

    def test_hold_runs_at_most_ten_seconds(self):
        w, _s, (holds, _e, _w) = self.spans("اهلا قال تعالى شجرة نهر |900 " + " ".join(["كلام"] * 40))
        start = holds[0]["src_start_ms"]
        last = [x for x in w if x["start_ms"] - start < MV().HOLD_MS][-1]
        self.assertEqual((holds[0]["src_end_ms"], holds[0]["end"]), (last["end_ms"], "time"))
        nxt = w[w.index(last) + 1]
        self.assertGreaterEqual(nxt["start_ms"] - start, MV().HOLD_MS)

    def test_hold_ends_at_a_change_of_speaker(self):
        # mutation survivor M18 (fix round 2): the other speaker's words are not the reciter's verse
        w = build_words("اهلا قال تعالى شجرة نهر |900 وده معناه ان الصبر مفتاح")
        for x in w:
            x["speaker"] = "A"
        w[-2]["speaker"] = w[-1]["speaker"] = "B"
        spans, _e, _w = MV().resolve(MV().detect(w, cfg(False)), {})
        holds = MV().held(spans, w, {})[0]
        self.assertEqual([(h["src_end_ms"], h["end"]) for h in holds], [(word_at(w, "ان")["end_ms"], "turn")])

    def test_hold_to_the_speech_end(self):
        w, _s, (holds, _e, _w) = self.spans(SC["recited"])
        self.assertEqual([(h["src_start_ms"], h["src_end_ms"], h["end"]) for h in holds],
                         [(word_at(w, "وده")["start_ms"], w[-1]["end_ms"], "speech_end")])

    def test_no_hold_without_a_pause_end(self):
        # an editor's span (its end is the editor's), a verse phrase (exact words), a span to the speech end
        w = build_words(SC["plain"])
        spans, _e, _w = MV().resolve([], {"manual_verse": [{"start_ms": w[2]["start_ms"], "end_ms": w[4]["end_ms"]}]})
        self.assertEqual(MV().held(spans, w, {})[0], [])
        w = build_words(SC["phrase"])
        spans, _e, _w = MV().resolve(MV().detect(w, cfg(True, ["سحاب قمر نجم"])), {})
        self.assertEqual(MV().held(spans, w, {})[0], [])
        w = build_words("اهلا قال تعالى " + " ".join(VERSE))
        spans, _e, _w = MV().resolve(MV().detect(w, cfg(False)), {})
        self.assertEqual(MV().held(spans, w, {})[0], [])

    def test_hold_after_a_guessed_end(self):
        w = build_words("اهلا قال تعالى " + " ".join(VERSE * 8) + " |900 وده كلام")
        spans, _e, _w = MV().resolve(MV().detect(w, cfg(False)), {})
        self.assertEqual([h["src_start_ms"] for h in MV().held(spans, w, {})[0]], [word_at(w, "وده")["start_ms"]])

    def test_release(self):
        w, _s, (holds, _e, _w) = self.spans(SC["recited"])
        h = holds[0]
        rel = {"manual_verse_release": [{"start_ms": h["src_start_ms"], "end_ms": h["src_start_ms"] + 10}]}
        _w2, _s2, (holds2, errs, warns) = self.spans(SC["recited"], rel)
        self.assertEqual(([x["released"] for x in holds2], errs, warns), ([True], [], []))   # listed, released
        self.assertEqual([x["released"] for x in holds], [False])
        _w3, _s3, (holds3, errs3, warns3) = self.spans(SC["recited"], {"manual_verse_release": [{"start_ms": 0,
                                                                                                "end_ms": 50}]})
        self.assertEqual((len(holds3), errs3, len(warns3)), (1, [], 1))
        self.assertIn("manual_verse_release", warns3[0])
        _w4, _s4, (_h4, errs4, _w4b) = self.spans(SC["recited"], {"manual_verse_release": "x"})
        self.assertEqual(len(errs4), 1)

    def test_hold_marker_comment_names_no_word(self):
        w, _s, (holds, _e, _w) = self.spans(SC["recited"])
        c = MV().hold_comment(holds[0])
        self.assertIn(common.fmt_ts(holds[0]["src_start_ms"], "."), c)
        self.assertIn("MV01", c)
        self.assertEqual(held_in(c), [])


class TestHoldPlan(Base):
    """The plan-session ruling: the held run is absent from every caption file, the caption words and the spec's
    words before the release, and back after it."""

    def test_held_until_released(self):
        w = build_words(SC["recited"])
        root, p = verse_project(self.tmp, w, flags={"هنتكلم", "مفتاح"})
        res, spec = self.compile(p)
        for name in ("captions-short-seq", "subtitles-seq"):
            txt = srt_text(p, name)
            self.assertEqual(held_in(txt), [], name)
            self.assertEqual(has_verse(txt), [], name)
            self.assertIn("هنتكلم", txt, name)
        sw = [x["word"] for x in read_json(p.p("02_transcription/words-seq.json"))["words"]]
        self.assertEqual([x for x in sw if x in HELD], [])
        h = word_at(w, "وده")
        self.assertEqual([(x["id"], x["after"], x["src_start_ms"], x["src_end_ms"], x["released"])
                          for x in spec["verse_hold"]], [("MV01H", "MV01", h["start_ms"], w[-1]["end_ms"], False)])
        self.assertEqual(set(spec["verse_hold"][0]), {"id", "src_start_ms", "src_end_ms", "start_ms", "end_ms",
                                                      "start_frame", "end_frame", "start_tc", "end_tc", "after",
                                                      "released"})       # the shape ADOBE-G4 reads (coordinator)
        self.assertEqual(set(spec["manual_verse"][0]) & {"after", "released"}, set())   # manual_verse keeps its shape
        mk = [m for m in spec["markers"] if m["kind"] == "verse_hold"]
        self.assertEqual([(m["name"], m["start_frame"]) for m in mk], [(MV().HOLD_NAME, common.ms_to_frame(h["start_ms"]))])
        self.assertEqual(held_in(json.dumps(spec["markers"], ensure_ascii=False)), [])
        self.assertTrue(any("MV01H" in x for x in res["warnings"]), res["warnings"])
        # needs-approval: one religious line for the hold, naming no word; the words list skips the held run
        doc = NY().collect(root)
        hold = [i for i in doc["items"] if i["ref"] == "MV01H"]
        self.assertEqual([i["kind"] for i in hold], ["religious"])
        self.assertIn("manual_verse_release", hold[0]["text"])
        self.assertEqual(held_in(hold[0]["text_ar"] + " " + hold[0]["text"]), [])
        words = " ".join(i["text_ar"] for i in doc["items"] if i["kind"] == "words")
        self.assertIn("هنتكلم", words)
        self.assertNotIn("مفتاح", words)
        # released: the story-editor records the editor's decision, the plan runs again
        ed = read_json(p.p("01_analysis/edit-decisions.json"))
        ed["manual_verse_release"] = [{"start_ms": h["start_ms"], "end_ms": h["end_ms"]}]
        write_json(p.p("01_analysis/edit-decisions.json"), ed)
        _res2, spec2 = self.compile(p)
        for name in ("captions-short-seq", "subtitles-seq"):
            txt = srt_text(p, name)
            self.assertIn("مفتاح", txt, name)
            self.assertEqual(has_verse(txt), [], name)
        sw = [x["word"] for x in read_json(p.p("02_transcription/words-seq.json"))["words"]]
        self.assertIn("مفتاح", sw)
        self.assertEqual([(x["id"], x["released"]) for x in spec2["verse_hold"]], [("MV01H", True)])
        self.assertEqual([m["kind"] for m in spec2["markers"]], ["manual_verse"])
        self.assertEqual([i for i in NY().collect(root)["items"] if i["ref"] == "MV01H"], [])

    def test_a_held_word_is_never_named_in_a_message(self):
        # mutation survivor M27: the held run is in the message mask like a span (a flagged word on a graphic)
        w = build_words(SC["recited"])
        s = word_at(w, "هنتكلم")["start_ms"]
        d = decision("EDIT_001", "GFX_001", s, word_at(w, "الصبر")["end_ms"], "هنتكلم عن الصبر", "مفتاح",
                     template="glass_card")
        _root, p = verse_project(self.tmp, w, flags={"مفتاح"}, decisions=[d])
        from lib.plan import compile_plan
        res = compile_plan(p)
        bad = [e for e in res["errors"] if e.startswith("GFX_001")]
        self.assertTrue(bad, res["errors"])
        for e in bad + res["warnings"]:
            self.assertNotIn("مفتاح", e)

    def test_a_cut_word_never_comes_back_at_a_span_edge(self):
        # mutation survivor M23: a cue split at a span edge is rebuilt from the kept words only
        from lib import srt as srtlib
        w = build_words(SC["recited"])
        q, t = word_at(w, "قال"), word_at(w, "شجرة")
        hand = [{"start_ms": w[0]["start_ms"], "end_ms": t["end_ms"],
                 "text": "اهلا بيكم النهارده هنتكلم عن الصبر قال تعالى شجرة"}]
        _root, p = verse_project(self.tmp, w, glob={"cut_words": [{"word_ids": [word_at(w, "هنتكلم")["id"]],
                                                                    "reason": "x"}]})
        for name in ("captions-short", "subtitles"):
            srtlib.write_srt(p.p(f"02_transcription/{name}.srt"), hand)
        self.compile(p)
        for name in ("captions-short-seq", "subtitles-seq"):
            txt = srt_text(p, name)
            self.assertNotIn("هنتكلم", txt, name)
            self.assertIn("النهارده", txt, name)
            self.assertLess(txt.find("النهارده"), txt.find(q["word"]) if q["word"] in txt else 10 ** 6)

    def test_graphic_repeating_the_held_run_waits_for_the_release(self):
        w = build_words(SC["recited"])
        s = word_at(w, "هنتكلم")["start_ms"]
        d = decision("EDIT_001", "GFX_001", s, word_at(w, "الصبر")["end_ms"], "هنتكلم عن الصبر",
                     "الصبر مفتاح كل خير", template="glass_card")
        _root, p = verse_project(self.tmp, w, decisions=[d])
        _res, spec = self.compile(p)
        self.assertNotIn("GFX_001", [e["event_id"] for e in spec["events"]])

    def test_previews_hide_the_held_run(self):
        w = build_words(SC["recited"])
        _root, p = verse_project(self.tmp, w)
        _res, spec = self.compile(p)
        from unittest import mock
        from lib import looks, looks_captions, previews
        seen = {}

        def fake(paths, res, hidden_ms, avoid=None, warnings=None):
            seen["hidden"] = list(hidden_ms)
            return []
        with mock.patch.object(looks, "resolve", return_value={"look": "clean", "source": "client"}), \
                mock.patch.object(looks_captions, "render_captions", side_effect=fake):
            previews.render_captions(p, [])
        hv = spec["verse_hold"][0]
        self.assertIn((hv["start_ms"], hv["end_ms"]), seen["hidden"])
        caps = previews.render_captions(p, [])                    # today's caption stills: none of the held words
        self.assertEqual([c for c in caps if held_in(c["text"])], [])


# --------------------------------------------------------------------------- P2-1 the NEEDS-YOU line
class TestNeedsYouAfter(Base):
    def test_every_verse_line_says_check_the_words_after_it(self):
        for text in (SC["recited"], "اهلا قال تعالى " + " ".join(VERSE) + " وده كلام" ,
                     "اهلا بيكم قال تعالى " + " ".join(VERSE * 8) + " |900 وده كلام جميل"):
            with self.subTest(text=text[:20]):
                import tempfile
                self.tmp = Path(tempfile.mkdtemp(dir=self._td.name))
                w = build_words(text)
                root, p = verse_project(self.tmp, w)
                self.compile(p)
                it = [i for i in NY().collect(root)["items"] if i["kind"] == "verse"]
                self.assertEqual(len(it), 1)
                self.assertIn(MV().AFTER_AR, it[0]["text_ar"])
                self.assertIn(MV().AFTER_EN, it[0]["text"])


# --------------------------------------------------------------------------- P3 the basmala anywhere on screen
class TestBasmalaEverywhere(Base):
    def test_any_graphic_loses_the_basmala(self):
        w = build_words(SC["plain"])
        s, e = w[0]["start_ms"], w[4]["end_ms"]
        bar = decision("EDIT_001", "GFX_001", s, e, "اهلا بيكم النهارده", "بسم الله الرحمن الرحيم اهلا بيكم")
        only = decision("EDIT_002", "GFX_002", w[6]["start_ms"], w[-1]["end_ms"], "نتابعهم كل يوم",
                        "بسم الله الرحمن الرحيم", template="glass_card")
        _root, p = verse_project(self.tmp, w, domain=None, decisions=[bar, only])
        res, spec = self.compile(p)
        ev = {e["event_id"]: e for e in spec["events"]}
        self.assertEqual(ev["GFX_001"]["params"]["text"], "اهلا بيكم")
        self.assertNotIn("GFX_002", ev)
        self.assertNotIn("الرحيم", json.dumps(spec["events"], ensure_ascii=False))
        self.assertTrue(any("GFX_001" in x and "basmala" in x for x in res["warnings"]), res["warnings"])

    def test_publish_copy_with_the_basmala_is_an_error(self):
        from lib.episode import EpisodePaths
        from lib.transcribe import finalize
        w = build_words(SC["plain"])
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
        from lib import publish
        for where, pub in (("title 1", {"youtube": {"titles": ["بسم الله الرحمن الرحيم حلقة", "ب", "ج"]}}),
                           ("thumbnail 1", {"youtube": {"titles": ["أ", "ب", "ج"]},
                                            "thumbnail": {"designs": [{"text": "بسم الله الرحمن الرحيم"}]}}),
                           ("tag 1", {"youtube": {"titles": ["أ", "ب", "ج"], "tags": ["أعوذ بالله من الشيطان الرجيم"]}})):
            write_json(ep.p("publish/publish.json"), pub)
            res = publish.check(ep)
            bad = [e for e in res["errors"] if e.startswith(where) and "basmala" in e]
            self.assertEqual(len(bad), 1, (where, res["errors"]))
            self.assertNotIn("الرحيم", bad[0])
            self.assertNotIn("الرجيم", bad[0])


class TestEpisodeHold(Base):
    def episode(self, text: str):
        from lib.episode import EpisodePaths
        from lib.transcribe import finalize
        w = build_words(text)
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
        return ep

    def test_upload_srt_leaves_the_held_run_out(self):
        ep = self.episode(SC["recited"] + " |900 تمام. وبعدين نكمل")
        write_json(ep.p("publish/publish.json"), {"youtube": {"titles": ["أ", "ب", "ج"]}})
        from lib import publish
        publish.check(ep)
        srt = ep.p("publish/EP12.srt").read_text(encoding="utf-8")
        self.assertEqual(has_verse(srt), [])
        self.assertEqual(held_in(srt), [])                    # an episode has no release: fail-closed
        self.assertIn("هنتكلم", srt)
        self.assertIn("نكمل", srt)                            # after the held run's sentence end

    def test_thumbnail_with_the_basmala_is_never_drawn(self):
        from unittest import mock
        from lib import episode, media_util, publish
        ep = self.episode(SC["plain"])
        write_json(ep.p("publish/publish.json"), {"youtube": {"titles": ["أ", "ب", "ج"]},
                                                 "thumbnail": {"designs": [{"frame_ms": 500,
                                                                            "text": "بسم الله الرحمن الرحيم"}]}})
        grab = mock.Mock(return_value=None)
        with mock.patch.object(episode, "load_episode", return_value={"duration_ms": 60000}), \
                mock.patch.object(episode, "episode_file", return_value=Path("x.mov")), \
                mock.patch.object(media_util, "grab_frame_file", grab):
            res = publish.render_thumbnails(ep)
        errs = [e for e in res.get("errors") or [] if e.startswith("design 1") and "basmala" in e]
        self.assertEqual(len(errs), 1, res)
        self.assertNotIn("الرحيم", errs[0])
        grab.assert_not_called()


class TestReleaseSchema(unittest.TestCase):
    def test_release_validates(self):
        from lib import schemas
        base = {"video_id": "CLIP1", "global": {"main_footage": "data/Raw/CLIP1.mov"}, "decisions": []}
        self.assertEqual(schemas.validate(dict(base, manual_verse_release=[{"start_ms": 1200, "end_ms": "00:00:04.500"}]),
                                          "edit-decisions"), [])
        self.assertNotEqual(schemas.validate(dict(base, manual_verse_release=[{"start_ms": 1}]), "edit-decisions"), [])


class TestAgentText(unittest.TestCase):
    def test_agents_never_write_a_verse(self):
        for rel in ("agents/publish-writer.md", "agents/motion-director.md", "agents/episode-analyst.md",
                    "agents/story-editor.md"):
            t = (SK / rel).read_text(encoding="utf-8")
            self.assertIn("never writes Quran text", t, rel)


if __name__ == "__main__":
    unittest.main()
