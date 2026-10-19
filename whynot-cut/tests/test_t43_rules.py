# SPDX-License-Identifier: GPL-3.0-or-later
# © 2026 The Why Not AI (thewhynot.ai)
"""3.0 Phase 4 T4.3: the learning loop (lib/rules_loop.py).

The revise skill records each round's comments, labelled with an intent, in the video's revision-notes.json
(`reel rules --record`); `--propose` groups them by meaning across the client's videos (two or more videos, or one
comment with a standing word) and lists conflicts, refusals and the wishes to do by hand; on the editor's confirmation
`--add` writes a dated rule (reel-profile/rules.json + a marked block in notes.md + the T4.2 knob in style.json);
`--list` / `--remove` manage them. A rule can never weaken a review, an approval gate or the QC.
Final round (executor ruling, option A): a learned preference is ONLY {area, phrase id} from the engine's vocabulary
(config/defaults/preference-phrases.json); the brief prints the vocabulary's text, never the editor's words; a wish
with no phrase of its own area is listed under `by_hand`. These tests label a preference with a real phrase.
Case list: D:/ClaudeData/claude-api-lane/work/S1-T4.3/cases.md. CLI, guard and skill hunks: hooks/S1-T4.3.
Run:  bash tools/test.sh -p test_t43_rules.py
"""
import sys as _sys
_sys.dont_write_bytecode = True  # keep the plugin folder free of __pycache__
import _isolation  # noqa: F401,E402  G79: sandbox the engine home first (tests/_isolation.py)
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SK = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SK / "engine" / "reel"))
sys.path.insert(0, str(SK / "tests"))

from lib import common, rules_loop as RL  # noqa: E402
from lib.common import CLIENT_PROFILE_REL, read_json, write_json  # noqa: E402
from lib.errors import Guidance  # noqa: E402

IS_WIN = os.name == "nt"
UP = {"knob": "caption_size_px", "direction": "up"}
DOWN = {"knob": "caption_size_px", "direction": "down"}
# real phrases of the engine's vocabulary (preference-phrases.json): the label a preference needs under option A
GLASS = {"topic": "glass_end", "area": "transitions", "phrase": "glass_end_only"}
LOGO_END = {"topic": "logo_end", "area": "ending", "phrase": "logo_end"}
MUSIC_ON = {"topic": "music_on", "area": "music", "phrase": "always_music"}       # group "presence": the two conflict
MUSIC_OFF = {"topic": "music_off", "area": "music", "phrase": "no_music"}
MUSIC_LOW = {"topic": "music_low", "area": "music", "phrase": "low_under_speech"}   # group "level"


def _link_dir(target: Path, link: Path) -> None:
    if IS_WIN:
        import _winapi
        _winapi.CreateJunction(str(target), str(link))
    else:
        os.symlink(target, link)


class Client(unittest.TestCase):
    """A client folder (Arabic name, a space) with five projects and an empty reel-profile."""
    NAME = "عيادة د. منى test"

    def setUp(self):
        self._tmp = Path(tempfile.mkdtemp())
        self.root = self._tmp / self.NAME
        for vid in ("C0001", "C0002", "C0003", "C0004", "C0005"):
            (self.root / "output" / "projects" / vid).mkdir(parents=True)
        self.prof = self.root / CLIENT_PROFILE_REL
        self.prof.mkdir(parents=True)
        common.set_context(self.root)
        self._links = []

    def tearDown(self):
        common.set_context(None)
        for link in self._links:                         # a link is removed as a name, never entered
            if IS_WIN:
                os.rmdir(link)
            else:
                os.unlink(link)
        shutil.rmtree(self._tmp, ignore_errors=True)

    def link(self, target: Path, link: Path):
        _link_dir(target, link)
        self._links.append(link)

    # helpers
    def rec(self, vid, *items, old=False, sealed=True):
        """Labelled comments go through record(); a plain string or an unlabelled item is an OLD note (written before
        the skill labelled comments), put straight into the file as an earlier version would have left it. `sealed`:
        the file carries a correct seal (so history() reads past the seal and the label checks themselves are
        tested); sealed=False is a hand-written file, which history() never counts (the seal tests use it)."""
        if not old and all(isinstance(i, dict) and i.get("intent") for i in items):
            return RL.record(self.root, vid, list(items))
        f = RL.notes_path(self.root, vid)
        doc = read_json(f, {"schema": 1, "video_id": vid, "notes": []})
        for i in items:
            i = i if isinstance(i, dict) else {"text": i}
            n = len(doc["notes"]) + 1
            doc["notes"].append({"id": f"N{n}", "at": "2026-10-01T10:00:00+03:00", "source": "comment", **i})
        if sealed:
            doc["seal"] = RL.seal_of(doc["notes"])
        write_json(f, doc)
        return {"ok": True}

    def props(self):
        return RL.propose(self.root)

    def one(self, r=None):
        r = r or self.props()
        self.assertEqual(len(r["proposals"]), 1, r["proposals"])
        return r["proposals"][0]

    def files(self):
        return {p.name: p.read_bytes() for p in self.prof.iterdir() if p.is_file() and not p.name.endswith(".lock")}

    def style(self):
        return read_json(self.prof / "style.json", {})

    def md(self):
        return (self.prof / "notes.md").read_text(encoding="utf-8")


# ====================================================================== A. record
class TestRecord(Client):
    def test_a1_labelled_comments_are_stored_with_id_time_source(self):
        r = self.rec("C0001", {"text": "الكابشن صغير", "intent": UP}, {"text": "شيل الموسيقى", "intent": dict(MUSIC_OFF, direction="off"),
                                                                   "scope": "this_clip"})
        self.assertEqual((r["added"], r["ids"]), (2, ["N1", "N2"]))
        doc = read_json(RL.notes_path(self.root, "C0001"))
        self.assertEqual(doc["video_id"], "C0001")
        n1, n2 = doc["notes"]
        self.assertEqual(n1["intent"], UP)
        self.assertEqual((n2["intent"]["area"], n2["intent"]["phrase"]), ("music", "no_music"))
        self.assertEqual(n1["source"], "comment")
        self.assertTrue(n1["at"])
        self.assertEqual(n2["scope"], "this_clip")
        self.assertEqual(RL.notes_path(self.root, "C0001"),
                         self.root / "output/projects/C0001/01_analysis/revision-notes.json")

    def test_a2_an_exact_repeat_is_not_stored_twice_and_ids_continue(self):
        self.rec("C0001", {"text": "الكابشن صغير", "intent": UP})
        r = self.rec("C0001", {"text": "الكابشن  صغير!", "intent": UP}, {"text": "كبّر الخط", "intent": UP})
        self.assertEqual((r["added"], r["already_recorded"], r["ids"]), (1, 1, ["N2"]))

    def test_a3_bad_items_refuse_the_whole_batch_and_write_nothing(self):
        bad = [{"text": ""}, {"text": "x", "intent": {"knob": "caption_size_px", "direction": "on"}},
               {"text": "x", "intent": {"knob": "caption_size_px"}}, {"text": "x", "intent": {"knob": "hook_title_sfx",
                                                                                            "direction": "up"}},
               {"text": "x", "intent": {"knob": "highlight_colour", "direction": "value", "value": "pink"}},
               {"text": "x", "intent": {"knob": "caption_size_px", "direction": "value", "value": 72.5}},
               {"text": "x", "intent": {"topic": "a", "area": "other_style", "knob": "caption_size_px"}}, {"text": "x", "intent": "big"},
               {"text": "x", "intent": {"topic": "a", "area": "music", "phrase": "not a phrase id"}},       # a phrase is an id,
               {"text": "x", "intent": {"topic": "a", "area": "music", "phrase": "x{y}"}},                  # never free text
               {"text": "x", "intent": {"topic": "a", "area": "music", "phrase": 5}},
               {"text": "x", "intent": {"knob": "caption_size_px", "direction": "up", "phrase": "calm"}},
               {"text": "x", "scope": "forever"}, {"text": "x", "source": "email"}, {"text": "x" * 2001}, "x"]
        for b in bad:
            with self.subTest(b=b), self.assertRaises(Guidance):
                RL.record(self.root, "C0001", [{"text": "ok", "intent": UP}, b])
            self.assertFalse(RL.notes_path(self.root, "C0001").exists())
        with self.assertRaises(Guidance):
            RL.record(self.root, "C0001", [])

    def test_a4_an_unknown_knob_is_recorded_and_never_becomes_a_rule(self):
        self.rec("C0001", {"text": "use the round font", "intent": {"knob": "caption_font", "area": "fonts", "direction": "value"}})
        self.assertEqual(read_json(RL.notes_path(self.root, "C0001"))["notes"][0]["intent"]["knob"], "caption_font")
        self.rec("C0002", {"text": "the round font again", "intent": {"knob": "caption_font", "area": "fonts", "direction": "value"}})
        r = self.props()                                  # said on two videos, but no phrase: by hand, not a proposal
        self.assertEqual(r["proposals"], [])
        self.assertEqual([h["topic"] for h in r["by_hand"]], ["caption_font"])

    def test_a5_a_damaged_notes_file_is_refused_never_overwritten(self):
        p = RL.notes_path(self.root, "C0001")
        p.parent.mkdir(parents=True)
        p.write_bytes(b"{not json")
        with self.assertRaises(Guidance) as cm:
            self.rec("C0001", {"text": "x", "intent": UP})
        self.assertIn("revision-notes.json", cm.exception.error)
        self.assertEqual(p.read_bytes(), b"{not json")

    def test_a6_a_link_on_the_way_is_refused(self):
        elsewhere = self._tmp / "elsewhere"
        elsewhere.mkdir()
        self.link(elsewhere, self.root / "output/projects/C0001/01_analysis")
        with self.assertRaises(Guidance):
            self.rec("C0001", {"text": "x", "intent": UP})
        self.assertEqual(list(elsewhere.iterdir()), [])

    def test_a7_a_bad_video_id_is_refused(self):
        for vid in ("../C0001", "C0001/../../x", ""):
            with self.subTest(vid=vid), self.assertRaises((Guidance, SystemExit, ValueError)):
                self.rec(vid, {"text": "x", "intent": UP})


# ====================================================================== B. detection
class TestDetect(Client):
    def test_b1_three_wordings_with_one_label_are_one_group(self):
        self.rec("C0001", {"text": "الكابشن صغير", "intent": UP})
        self.rec("C0002", {"text": "كبّر الخط", "intent": UP})
        self.rec("C0003", {"text": "captions too small", "intent": UP})
        p = self.one()
        self.assertEqual(p["knob"], "caption_size_px")
        self.assertEqual(p["videos"], ["C0001", "C0002", "C0003"])
        self.assertEqual(p["value"], round(62 * 1.15))
        self.assertEqual(p["read_by"], ["label"])
        self.assertIn("71", p["ar"])
        self.assertIn("71 px", p["en"])

    def test_b2_bigger_and_smaller_are_a_conflict_not_a_group(self):
        self.rec("C0001", {"text": "كبّر الكابشن", "intent": UP})
        self.rec("C0002", {"text": "صغّر الكابشن", "intent": DOWN})
        r = self.props()
        self.assertEqual(len(r["conflicts"]), 1)
        self.assertEqual(len(r["proposals"]), 2)
        a, b = r["proposals"]
        self.assertEqual(a["conflicts_with"], [b["id"]])
        self.assertEqual({a["polarity"], b["polarity"]}, {"up", "down"})

    def test_b2b_two_one_off_disagreeing_comments_in_one_video_are_nothing(self):
        self.rec("C0001", {"text": "كبّر الكابشن", "intent": UP}, {"text": "صغّر الكابشن", "intent": DOWN})
        r = self.props()
        self.assertEqual((r["proposals"], r["conflicts"]), ([], []))

    def test_b3_same_labelled_comment_on_two_videos_is_a_group(self):
        """S1-T4.3: a comment counts with the skill's label (its area and a phrase id); the same words without a
        label are only a warning."""
        self.rec("C0001", {"text": "خلي الجلاس في الآخر بس", "intent": GLASS})
        self.rec("C0002", {"text": "خلّي الجلاس في الاخر بس.", "intent": GLASS})
        p = self.one()
        self.assertIsNone(p["knob"])
        self.assertEqual(p["target"], "notes.md")
        self.assertEqual(p["read_by"], ["label"])
        self.assertEqual((p["subject"], p["polarity"], p["phrase"], p["area"]),
                         ("phrase:transitions.style", "glass_end_only", "glass_end_only", "transitions"))
        self.assertEqual((p["ar"], p["en"]), ("جلاس في الآخر بس", "glass transition only at the end"))   # the vocabulary's words
        self.tearDown()
        self.setUp()
        self.rec("C0001", "خلي الجلاس في الآخر بس")
        self.rec("C0002", "خلّي الجلاس في الاخر بس.")
        r = self.props()
        self.assertEqual(r["proposals"], [])
        self.assertEqual(sum("relabel" in w for w in r["warnings"]), 2)

    def test_b3a_three_wordings_of_one_phrase_are_one_group_on_three_videos(self):
        for vid, text in (("C0001", "خلي الجلاس في الآخر بس"), ("C0002", "glass only at the end"),
                          ("C0003", "الجلاس بس في الاخر")):
            self.rec(vid, {"text": text, "intent": GLASS})
        p = self.one()
        self.assertEqual(p["videos"], ["C0001", "C0002", "C0003"])

    def test_b3c_a_wish_with_no_phrase_is_listed_by_hand_never_proposed(self):
        """Option A: a free topic (no phrase) is never a rule. Said on two videos it is listed under `by_hand`, with
        the engine's sentence («اتقال في N فيديوهات…») and the editor's own words for the editor to read."""
        free = {"topic": "glass_only_at_end", "area": "transitions"}
        self.rec("C0001", {"text": "خلي الجلاس في الآخر بس", "intent": free})
        self.rec("C0002", {"text": "glass only at the end", "intent": free})
        r = self.props()
        self.assertEqual((r["proposals"], r["conflicts"]), ([], []))
        self.assertEqual(len(r["by_hand"]), 1)
        h = r["by_hand"][0]
        self.assertEqual((h["topic"], h["area"], h["videos"], h["text"]),
                         ("glass_only_at_end", "transitions", ["C0001", "C0002"], "glass only at the end"))
        self.assertEqual((h["ar"], h["en"]), (RL.BY_HAND_AR.format(n=2), RL.BY_HAND_EN.format(n=2)))
        self.assertIn("2", h["ar"])
        self.assertEqual(r["summary"], [])                # the summary holds rules and proposals only
        with self.assertRaises(Guidance):
            RL.add(self.root, RL._gid("topic:glass_only_at_end", ""))
        self.assertEqual(self.files(), {})

    def test_b3d_a_one_off_wish_by_hand_is_not_listed_until_it_recurs_or_is_standing(self):
        free = {"topic": "glass", "area": "transitions"}
        self.rec("C0001", {"text": "glass at the end", "intent": free})
        self.assertEqual(self.props()["by_hand"], [])
        self.rec("C0002", {"text": "الجلاس في الآخر، دايماً", "intent": free})
        self.assertEqual(len(self.props()["by_hand"]), 1)
        self.tearDown()
        self.setUp()
        self.rec("C0001", {"text": "always glass at the end", "intent": free})       # a standing word alone is enough
        self.assertEqual(len(self.props()["by_hand"]), 1)
        self.tearDown()
        self.setUp()
        self.rec("C0001", {"text": "glass at the end, this video only", "intent": free})
        self.rec("C0002", {"text": "glass at the end", "intent": free, "scope": "this_clip"})
        self.assertEqual(self.props()["by_hand"], [])     # a comment for one clip never counts, by hand either

    def test_b3b_the_same_comment_twice_in_one_video_is_not_two_reels(self):
        self.rec("C0001", {"text": "خلي الجلاس في الآخر بس", "intent": GLASS},
                 {"text": "glass only at the end please", "intent": GLASS})
        r = self.props()
        self.assertEqual(r["proposals"], [])              # one video, no standing word: not a rule yet
        self.rec("C0002", {"text": "glass at the end again", "intent": GLASS})
        self.assertEqual(self.one()["videos"], ["C0001", "C0002"])

    def test_b4_a_standing_word_makes_one_comment_a_proposal(self):
        for text in ("always put the logo at the end", "never use red in the captions", "دايماً حط اللوجو في الآخر",
                     "دايما حط اللوجو في الآخر", "دائماً حط اللوجو في الآخر", "أبداً متحطش موسيقى",
                     "from now on no music", "بعد كده خلي المزيكا أهدى", "كل مرة حط اللوجو"):
            with self.subTest(text=text):
                self.tearDown()
                self.setUp()
                self.rec("C0001", {"text": text, "intent": LOGO_END})
                self.assertEqual(self.one()["why"], "standing word")
        for text in ("always put the logo at the end", "دايماً حط اللوجو في الآخر"):   # the same, no phrase: by hand
            with self.subTest(by_hand=text):
                self.tearDown()
                self.setUp()
                self.rec("C0001", {"text": text, "intent": {"topic": "t", "area": "ending"}})
                r = self.props()
                self.assertEqual(r["proposals"], [])
                self.assertEqual([h["videos"] for h in r["by_hand"]], [["C0001"]])

    def test_b5_a_negated_standing_word_is_not_standing(self):
        for text in ("مش دايماً حط اللوجو", "مش دايما حط اللوجو", "not always the logo", "doesn't always need music",
                     "مش كل مرة حط الاسم"):
            with self.subTest(text=text):
                self.assertFalse(RL.standing_word(text))
                self.tearDown()
                self.setUp()
                self.rec("C0001", {"text": text, "intent": LOGO_END})      # one video, no standing word: nothing yet
                r = self.props()
                self.assertEqual((r["proposals"], r["by_hand"]), ([], []))

    def test_b6_this_clip_only_never_counts(self):
        self.rec("C0001", {"text": "دايماً كبّر الكابشن في الفيديو ده بس", "intent": UP})
        self.rec("C0002", {"text": "bigger captions, this video only", "intent": UP})
        self.rec("C0003", {"text": "كبّر الكابشن", "intent": UP, "scope": "this_clip"})
        self.rec("C0004", {"text": "كبّر الكابشن", "intent": UP})
        self.assertEqual(self.props()["proposals"], [])

    def test_b6b_the_skills_standing_scope_counts_like_always(self):
        self.rec("C0001", {"text": "الكابشن صغير", "intent": UP, "scope": "standing"})
        self.assertEqual(self.one()["why"], "standing word")

    def test_b7_old_unlabelled_comments_never_count_and_the_keyword_reader_is_a_helper(self):
        self.rec("C0001", "make the captions bigger please")      # a (sealed) file whose notes carry no label
        self.rec("C0002", "كبّر الكابشن شوية")
        r = self.props()                                  # S1-T4.3 ruling: only labelled comments count
        self.assertEqual(r["proposals"], [])
        self.assertEqual(sum("no intent label" in w for w in r["warnings"]), 2)
        cases = {"captions too small": UP, "الكابشن صغير": UP, "الخط كبير اوي": DOWN, "smaller subtitles": DOWN,
                 "من غير صوت على العنوان": {"knob": "hook_title_sfx", "direction": "off"},
                 "no whoosh on the hook title": {"knob": "hook_title_sfx", "direction": "off"},
                 "سيب الكابشن على الهوك": {"knob": "captions_during_hook", "direction": "on"},
                 "highlight colour #ffcc00": {"knob": "highlight_colour", "direction": "value", "value": "#ffcc00"},
                 "move the name card": None, "الموسيقى عالية": None}
        for text, want in cases.items():
            with self.subTest(text=text):
                self.assertEqual(RL.read_intent(text), want)

    def test_b7b_a_negated_size_comment_is_not_read_as_a_knob(self):
        for text in ("الكابشن مش صغير", "the captions are not too small", "captions aren't too big",
                     "الخط مش كبير خالص", "don't make the captions bigger", "متكبرش الكابشن", "ما تكبرش الخط"):
            with self.subTest(text=text):
                self.assertIsNone(RL.read_intent(text))

    def test_b7c_same_time_comments_keep_their_order_past_n9(self):
        self.rec("C0001", *[{"text": f"note {i}", "intent": {"topic": f"t{i}", "area": "other_style"}} for i in range(1, 12)])
        ids = [n["id"] for n in RL.history(self.root)[0]]
        self.assertEqual(ids, [f"N{i}" for i in range(1, 12)])

    def test_b8_a_phrase_label_is_a_notes_only_proposal_a_free_topic_or_unknown_knob_is_by_hand(self):
        self.rec("C0001", {"text": "الجلاس في الآخر", "intent": GLASS})
        self.rec("C0002", {"text": "glass only at the end", "intent": GLASS})
        self.rec("C0003", {"text": "rounded font", "intent": {"knob": "caption_font", "area": "fonts", "direction": "value"}},
                 {"text": "a free topic", "intent": {"topic": "free_wish", "area": "fonts"}})
        self.rec("C0004", {"text": "the rounded font again", "intent": {"knob": "caption_font", "area": "fonts", "direction": "value"}},
                 {"text": "the free topic again", "intent": {"topic": "free_wish", "area": "fonts"}})
        r = self.props()
        self.assertEqual(len(r["proposals"]), 1)
        p = r["proposals"][0]
        self.assertIsNone(p["knob"])
        self.assertEqual(p["target"], "notes.md")
        self.assertEqual(p["phrase"], "glass_end_only")
        self.assertEqual(sorted(h["topic"] for h in r["by_hand"]), ["caption_font", "free_wish"])
        for h in r["by_hand"]:
            self.assertEqual((h["area"], h["videos"]), ("fonts", ["C0003", "C0004"]))

    def test_b9_a_damaged_notes_file_warns_and_the_others_still_count(self):
        self.rec("C0001", {"text": "الكابشن صغير", "intent": UP})
        self.rec("C0002", {"text": "كبر الخط", "intent": UP})
        bad = RL.notes_path(self.root, "C0003")
        bad.parent.mkdir(parents=True)
        bad.write_bytes(b"\xff\xfe broken")
        r = self.props()
        self.assertEqual(len(r["proposals"]), 1)
        self.assertTrue(any("C0003" in w for w in r["warnings"]))

    def test_b10_ids_are_stable_and_summary_has_both_languages(self):
        self.rec("C0001", {"text": "الكابشن صغير", "intent": UP})
        self.rec("C0002", {"text": "كبر الخط", "intent": UP})
        a, b = self.props(), self.props()
        self.assertEqual(a, b)
        s = a["summary"][0]
        self.assertTrue(s["ar"].startswith("مقترح: ") and s["en"].startswith("proposed: "))

    def test_b11_bool_and_enum_knobs_group_by_value(self):
        off = {"knob": "hook_title_sfx", "direction": "off"}
        self.rec("C0001", {"text": "من غير صوت على العنوان", "intent": off})
        self.rec("C0002", {"text": "no click on the title", "intent": {"knob": "hook_title_sfx", "direction": "value",
                                                                       "value": False}})
        p = self.one()
        self.assertEqual((p["knob"], p["value"]), ("hook_title_sfx", False))

    def test_b12_a_size_number_groups_with_its_direction_and_the_newest_number_wins(self):
        self.rec("C0001", {"text": "الكابشن 80", "intent": {"knob": "caption_size_px", "direction": "value",
                                                            "value": 80}})
        self.rec("C0002", {"text": "خليه 76", "intent": {"knob": "caption_size_px", "direction": "value",
                                                        "value": 76}})
        p = self.one()
        self.assertEqual((p["polarity"], p["value"]), ("up", 76))

    def test_b13_at_the_largest_size_bigger_is_not_proposed(self):
        write_json(self.prof / "style.json", {"caption_size_px": 140})
        self.rec("C0001", {"text": "الكابشن صغير", "intent": UP})
        self.rec("C0002", {"text": "كبر الخط", "intent": UP})
        self.assertEqual(self.props()["proposals"], [])

    def test_b14_no_projects_folder_is_empty_not_an_error(self):
        shutil.rmtree(self.root / "output" / "projects")
        r = self.props()
        self.assertEqual((r["proposals"], r["warnings"]), ([], []))


# ====================================================================== C. add
class TestAdd(Client):
    def two_up(self):
        self.rec("C0001", {"text": "الكابشن صغير", "intent": UP})
        self.rec("C0002", {"text": "captions too small", "intent": UP})
        return self.one()

    def test_c1_a_knob_rule_writes_style_notes_and_registry_with_the_date(self):
        p = self.two_up()
        with mock.patch.object(RL, "_today", return_value="2026-10-18"):
            r = RL.add(self.root, p["id"])
        self.assertEqual(r["rule"]["id"], "R1")
        self.assertEqual(self.style(), {"caption_size_px": 71})
        md = self.md()
        self.assertIn(RL.BLOCK_START, md)
        self.assertIn("- 2026-10-18 · R1 · captions at 71 px / الكابشن بحجم 71 بكسل (style.json)", md)
        reg = read_json(self.prof / "rules.json")
        self.assertEqual(reg["rules"][0]["status"], "active")
        self.assertEqual(reg["rules"][0]["from"], [["C0001", "N1"], ["C0002", "N1"]])

    def test_c2_running_it_again_changes_nothing_and_is_not_proposed_again(self):
        p = self.two_up()
        RL.add(self.root, p["id"])
        before = self.files()
        r = RL.add(self.root, p["id"])
        self.assertTrue(r["unchanged"])
        self.assertEqual(self.files(), before)
        props = self.props()
        self.assertEqual(props["proposals"], [])
        self.assertEqual([a["id"] for a in props["active"]], ["R1"])
        self.assertEqual(self.md().count("· R1 ·"), 1)

    def test_c3_a_notes_only_rule_leaves_style_json_alone_and_prints_the_vocabulary_not_the_comment(self):
        self.rec("C0001", {"text": "دايماً الجلاس في الآخر", "intent": GLASS})
        rule = RL.add(self.root, self.one()["id"])["rule"]
        self.assertFalse((self.prof / "style.json").exists())
        md = self.md()
        self.assertIn("preference only", md)                        # S1-T4.3: a preference, never "followed"
        self.assertIn(RL.PREFERENCES_HEADER, md)
        self.assertIn("glass transition only at the end / جلاس في الآخر بس (preference only)", md)   # the engine's words
        self.assertNotIn("دايماً الجلاس في الآخر", md)               # the editor's words never reach the brief
        row = read_json(self.prof / "rules.json")["rules"][0]
        self.assertEqual((row["phrase"], row["area"]), ("glass_end_only", "transitions"))
        self.assertNotIn("text", row)                               # no free-text field on a new row
        self.assertEqual((rule["ar"], rule["en"]), ("جلاس في الآخر بس", "glass transition only at the end"))

    def test_c4_value_is_checked_by_t42_and_a_bad_one_writes_nothing(self):
        p = self.two_up()
        for bad in (500, 72.5, "big", True, 0):
            with self.subTest(bad=bad), self.assertRaises(Guidance):
                RL.add(self.root, p["id"], value=bad)
            self.assertEqual(self.files(), {})
        RL.add(self.root, p["id"], value=90)
        self.assertEqual(self.style()["caption_size_px"], 90)

    def test_c4b_a_notes_rule_takes_no_value(self):
        self.rec("C0001", {"text": "always glass at the end", "intent": GLASS})
        with self.assertRaises(Guidance):
            RL.add(self.root, self.one()["id"], value=3)
        self.assertEqual(self.files(), {})

    def test_c5_a_contradiction_needs_replace_and_the_old_rule_is_kept_as_history(self):
        RL.add(self.root, self.two_up()["id"])
        self.rec("C0003", {"text": "الكابشن بقى كبير", "intent": DOWN, "scope": "standing"})
        p = self.one()
        self.assertEqual(p["conflicts_with_rule"], "R1")
        before = self.files()
        with self.assertRaises(Guidance) as cm:
            RL.add(self.root, p["id"])
        self.assertIn("--replace R1", cm.exception.how)
        self.assertEqual(self.files(), before)
        with self.assertRaises(Guidance):
            RL.add(self.root, p["id"], replace="R9")
        with mock.patch.object(RL, "_today", return_value="2026-10-20"):
            r = RL.add(self.root, p["id"], replace="R1")
        self.assertEqual(r["replaced"], "R1")
        self.assertEqual(self.style()["caption_size_px"], 62)       # 71 / 1.15
        lst = RL.list_rules(self.root)
        self.assertEqual([a["id"] for a in lst["active"]], ["R2"])
        self.assertEqual(lst["history"][0]["status"], "replaced")
        self.assertIn("R1 · captions at 71 px: replaced 2026-10-20 by R2", self.md())

    def test_c5b_never_two_active_rules_on_one_knob(self):
        RL.add(self.root, self.two_up()["id"])
        self.rec("C0003", {"text": "make it 90", "intent": {"knob": "caption_size_px", "direction": "value",
                                                           "value": 90}, "scope": "standing"})
        p = self.one()
        self.assertEqual(p["conflicts_with_rule"], "R1")           # same direction, another value: still one knob
        with self.assertRaises(Guidance):
            RL.add(self.root, p["id"])
        RL.add(self.root, p["id"], replace="R1")
        self.assertEqual(len(RL.list_rules(self.root)["active"]), 1)

    def test_c6_the_editors_prose_is_kept_and_broken_markers_refuse(self):
        (self.prof / "notes.md").write_text("# د. منى\n\nTone: calm.\n", encoding="utf-8")
        RL.add(self.root, self.two_up()["id"])
        md = self.md()
        self.assertTrue(md.startswith("# د. منى\n\nTone: calm.\n"))
        (self.prof / "notes.md").write_text(md + "\nMore prose by hand.\n", encoding="utf-8")
        RL.remove(self.root, "R1")
        self.assertTrue(self.md().endswith("\nMore prose by hand.\n"))
        self.assertTrue(self.md().startswith("# د. منى\n\nTone: calm.\n"))
        broken = self.md().replace(RL.BLOCK_END, "")
        (self.prof / "notes.md").write_text(broken, encoding="utf-8")
        self.rec("C0003", {"text": "always glass at the end", "intent": GLASS})
        before = self.files()
        with self.assertRaises(Guidance) as cm:
            RL.add(self.root, self.one()["id"])
        self.assertIn("markers", cm.exception.error)
        self.assertEqual(self.files(), before)

    def test_c6c_nothing_of_a_comment_reaches_the_block(self):
        """Option A: the block holds the engine's phrase text only, so a comment that carries the end marker, a
        comment opener or a line break cannot touch it: none of its words are printed at all."""
        evil = "always glass\n" + RL.BLOCK_END + "\n<!-- x --> at the end"
        self.rec("C0001", {"text": evil, "intent": GLASS})
        RL.add(self.root, self.one()["id"])
        md = self.md()
        self.assertEqual((md.count(RL.BLOCK_END), md.count("<!--")), (1, 2))      # our two markers only
        for piece in ("always glass", "<!-- x -->", "at the end\n", "x -->"):
            self.assertNotIn(piece, md)
        self.rec("C0002", {"text": "always no music", "intent": MUSIC_OFF})
        RL.add(self.root, self.one()["id"])                       # the block is still whole: a second write works
        self.assertEqual(self.md().count("· R2 ·"), 1)
        self.assertEqual((self.md().count(RL.BLOCK_END), self.md().count("<!--")), (1, 2))

    def test_c6b_crlf_notes_md_keeps_its_text(self):
        (self.prof / "notes.md").write_bytes("Tone: calm.\r\nNo jokes.\r\n".encode("utf-8"))
        RL.add(self.root, self.two_up()["id"])
        raw = (self.prof / "notes.md").read_bytes().decode("utf-8")
        self.assertTrue(raw.startswith("Tone: calm.\r\nNo jokes.\r\n"), raw[:40])

    def test_c7_style_json_keeps_other_keys_and_a_damaged_one_refuses(self):
        write_json(self.prof / "style.json", {"remove_pauses": 300, "highlight_color": "accent"})
        self.rec("C0001", {"text": "highlight #00ff00 always", "intent": {"knob": "highlight_colour",
                                                                         "direction": "value", "value": "#00ff00"}})
        RL.add(self.root, self.one()["id"])
        self.assertEqual(self.style(), {"remove_pauses": 300, "highlight_colour": "#00FF00"})
        (self.prof / "style.json").write_bytes(b"{bad")
        self.rec("C0002", {"text": "always no sound on the title", "intent": {"knob": "hook_title_sfx",
                                                                             "direction": "off"}})
        before = self.files()
        with self.assertRaises(Guidance) as cm:
            RL.add(self.root, self.one()["id"])
        self.assertIn("style.json", cm.exception.error)
        self.assertEqual(self.files(), before)

    def test_c8_a_linked_reel_profile_is_refused(self):
        p = self.two_up()
        real = self._tmp / "real-profile"
        shutil.move(str(self.prof), str(real))
        self.link(real, self.prof)
        with self.assertRaises(Guidance):
            RL.add(self.root, p["id"])
        self.assertEqual(sorted(x.name for x in real.iterdir()), [])

    def test_c9_unknown_id_is_refused(self):
        with self.assertRaises(Guidance):
            RL.add(self.root, "P-00000000")
        self.assertEqual(self.files(), {})

    def test_c10_a_failed_write_puts_every_file_back(self):
        write_json(self.prof / "style.json", {"remove_pauses": 300})
        (self.prof / "notes.md").write_text("Tone: calm.\n", encoding="utf-8")
        p = self.two_up()
        before = self.files()
        real = RL.linksafe.replace_atomic
        calls = []

        def flaky(path, root, data, within=None):
            calls.append(Path(path).name)
            if Path(path).name == "rules.json":
                raise OSError("disk full")
            return real(path, root, data, within)
        with mock.patch.object(RL.linksafe, "replace_atomic", side_effect=flaky), self.assertRaises(OSError):
            RL.add(self.root, p["id"])
        self.assertEqual(self.files(), before)

    def test_c11_hook_and_colour_knobs(self):
        self.rec("C0001", {"text": "سيب الكابشن على الهوك دايماً", "intent": {"knob": "captions_during_hook",
                                                                             "direction": "on"}})
        RL.add(self.root, self.one()["id"])
        self.assertEqual(self.style(), {"captions_during_hook": "show"})
        self.rec("C0002", {"text": "always no sound on the hook title", "intent": {"knob": "hook_title_sfx",
                                                                                  "direction": "off"}})
        RL.add(self.root, self.one()["id"])
        self.assertEqual(self.style(), {"captions_during_hook": "show", "hook_title_sfx": False})


# ====================================================================== D. list / remove
class TestRemove(Client):
    def setUp(self):
        super().setUp()
        self.rec("C0001", {"text": "الكابشن صغير", "intent": UP})
        self.rec("C0002", {"text": "captions too small", "intent": UP})
        RL.add(self.root, self.one()["id"])

    def test_d1_remove_reverts_the_knob_and_keeps_history(self):
        write_json(self.prof / "style.json", {**self.style(), "remove_pauses": 300})
        with mock.patch.object(RL, "_today", return_value="2026-10-21"):
            RL.remove(self.root, "R1")
        self.assertEqual(self.style(), {"remove_pauses": 300})
        lst = RL.list_rules(self.root)
        self.assertEqual((lst["active"], lst["history"][0]["removed"]), ([], "2026-10-21"))
        self.assertIn("removed 2026-10-21", self.md())
        self.assertIn("(no active rule)", self.md())
        self.assertEqual(self.props()["proposals"], [])                # its comments do not come back

    def test_d2_a_value_changed_by_hand_is_kept(self):
        write_json(self.prof / "style.json", {"caption_size_px": 88})
        r = RL.remove(self.root, "R1")
        self.assertEqual(self.style(), {"caption_size_px": 88})
        self.assertIn("changed by hand", r["warnings"][0])

    def test_d3_unknown_or_removed_ids_are_refused(self):
        RL.remove(self.root, "R1")
        before = self.files()
        for rid in ("R1", "R7", "x"):
            with self.subTest(rid=rid), self.assertRaises(Guidance):
                RL.remove(self.root, rid)
        self.assertEqual(self.files(), before)

    def test_d4_new_comments_after_a_removal_can_propose_again(self):
        RL.remove(self.root, "R1")
        self.rec("C0003", {"text": "bigger captions, always", "intent": UP})
        self.assertEqual(self.one()["videos"], ["C0003"])

    def test_d5_a_damaged_registry_refuses(self):
        (self.prof / "rules.json").write_bytes(b"[1]")
        for fn in (lambda: RL.list_rules(self.root), lambda: RL.remove(self.root, "R1"), self.props):
            with self.assertRaises(Guidance):
                fn()


# ====================================================================== F. safety cannot be learned away
class TestSafety(Client):
    WEAKEN = ("من غير مراجعة الدكتور", "دايماً من غير مراجعة الدكتور", "بلاش المراجعة الطبية", "skip the review",
              "always skip the medical review", "turn off QC", "no disclaimer", "شيل التنويه", "auto approve always",
              "no need for approval from now on", "مش محتاجين موافقة الدكتور", "always ignore the reviewer",
              "الشيخ مش لازم يراجع")
    FINE = ("الكابشن صغير", "always put the logo at the end", "keep the music low", "خلي الجلاس في الآخر بس")
    # The class rule (review round 1): a rule never speaks about the review process, in either direction. So these
    # can never become a standing rule (the comment itself is still done for its video): a deliberate over-block.
    NEVER_A_RULE = ("review the caption size", "never skip the review", "always send it for approval",
                    "راجع الكابشن", "always show the doctor's name")

    def test_f1_weakening_comments_are_refused_with_a_plain_sentence(self):
        for text in self.WEAKEN:
            with self.subTest(text=text):
                self.assertTrue(RL.weakens_safety(text))
                for label in ({"topic": "x", "area": "other_style"},      # refused whatever the label, a valid
                              {"topic": "x", "area": "music", "phrase": "no_music"}):     # phrase of its area too
                    self.tearDown()
                    self.setUp()
                    self.rec("C0001", {"text": text, "scope": "standing", "intent": label})
                    self.rec("C0002", {"text": text, "intent": label})
                    r = self.props()
                    self.assertEqual(r["proposals"], [])
                    self.assertEqual(r["by_hand"], [])
                    self.assertEqual(len(r["refused"]), 2)
                    self.assertIn("المراجعة", r["refused"][0]["ar"])
                    self.assertIn("review", r["refused"][0]["en"])

    def test_f2_ordinary_comments_are_not_refused(self):
        for text in self.FINE:
            with self.subTest(text=text):
                self.assertFalse(RL.weakens_safety(text))
        for text in self.NEVER_A_RULE:
            with self.subTest(text=text):
                self.assertTrue(RL.weakens_safety(text))

    def test_f3_safety_labels_are_refused_whatever_the_words(self):
        for intent in ({"topic": "auto_approve", "area": "other_style"}, {"topic": "skip_medical_review", "area": "other_style"}, {"topic": "no_qc", "area": "other_style"},
                       {"knob": "approval", "direction": "off", "area": "other_style"}, {"knob": "k_t5_arabic_qc_in_motion_qc",
                                                                  "direction": "off", "area": "other_style"},
                       {"topic": "disclaimer", "area": "other_style", "direction": "off"},
                       {"topic": "auto_approve", "area": "music", "phrase": "no_music"},          # a phrase does not clear it
                       {"topic": "skip_doctor", "area": "ending", "phrase": "logo_end"}):
            with self.subTest(intent=intent):
                self.assertTrue(RL.weakens_safety("make it nicer", intent))
                self.tearDown()
                self.setUp()
                self.rec("C0001", {"text": "always like this", "intent": intent})
                self.assertEqual(self.props()["proposals"], [])
                with self.assertRaises(Guidance):
                    RL.add(self.root, RL._gid(*RL._target(intent, "always like this")[:2]))
                self.assertEqual(self.files(), {})

    def test_f4_the_four_knobs_are_never_refused(self):
        for intent in (UP, {"knob": "hook_title_sfx", "direction": "off"},
                       {"knob": "captions_during_hook", "direction": "off"}):
            self.assertFalse(RL.weakens_safety("", intent))


# ====================================================================== R. review round 1 (fresh-eyes Opus, FAIL)
class TestReview1(Client):
    SLIPS = ("always skip the doctor", "never send it to the doctor", "always approve automatically",
             "always auto-publish", "turn off K1", "always skip the fact-checking",
             "دايما من غير ما الدكتور يشوف الفيديو", "دايما متخليش الدكتور يراجع", "مش محتاجين الشيخ",
             "لا داعي لمراجعة الطبيب", "دون مراجعة الطبيب", "لا حاجة للموافقة", "always publish it straight away",
             "never skip the review", "الدكتورة مش لازم تشوفه", "انشر على طول من غير ما حد يشوف",
             "بلاش نبعته للدكتور", "اعتمده انت", "خليه يتنشر اوتوماتيك")
    STYLE = ("من غير موسيقى على كلام الدكتور", "always show the doctor's name", "never put text over the safe zone",
             "never put text over the safety zone", "always publish the caption with 3 hashtags",
             "الدكتور يظهر في الأول دايماً", "no music when the doctor talks", "صوت الدكتور أعلى من المزيكا",
             "always put the sheikh's name card", "always bigger captions", "كبر الكابشن دايما")

    def test_r1_slips_past_the_review_are_refused_end_to_end(self):
        for text in self.SLIPS:
            with self.subTest(text=text):
                self.assertTrue(RL.weakens_safety(text), text)
                self.tearDown()
                self.setUp()
                self.rec("C0001", {"text": text, "intent": {"topic": "publish_directly", "area": "other_style"}, "scope": "standing"})
                r = self.props()
                self.assertEqual(r["proposals"], [])
                self.assertEqual(len(r["refused"]), 1)

    def test_r1b_style_comments_naming_a_reviewer_are_an_accepted_over_block(self):
        """S1-T4.3 ruling 3: as a preference they are refused (over-block accepted); a knob label is never refused."""
        plain = {"never put text over the safe zone", "never put text over the safety zone", "always bigger captions",
                 "كبر الكابشن دايما"}
        for text in self.STYLE:
            with self.subTest(text=text):
                self.assertEqual(RL.weakens_safety(text, {"topic": "x", "area": "other_style"}), text not in plain)
                self.assertFalse(RL.weakens_safety(text, UP), text)

    def test_r1c_the_block_says_rules_never_touch_the_review(self):
        self.rec("C0001", {"text": "always glass at the end", "intent": GLASS})
        RL.add(self.root, self.one()["id"])
        self.assertIn(RL.PREFERENCES_HEADER, self.md())

    def test_r2_always_and_never_on_one_thing_conflict(self):
        """Two phrases of one group (music: always_music / no_music, group "presence") exclude each other."""
        self.rec("C0001", {"text": "always put music", "intent": MUSIC_ON})
        self.rec("C0002", {"text": "never put music", "intent": MUSIC_OFF})
        r = self.props()
        self.assertEqual(len(r["conflicts"]), 1)
        self.assertEqual(r["conflicts"][0]["subject"], "phrase:music.presence")
        a = r["proposals"][0]
        RL.add(self.root, a["id"])
        other = self.one()
        self.assertTrue(other.get("conflicts_with_rule"))
        with self.assertRaises(Guidance):
            RL.add(self.root, other["id"])

    def test_r2b_another_phrase_of_the_same_group_conflicts_with_the_active_rule(self):
        self.rec("C0001", {"text": "always use glass only at the end", "intent": GLASS})
        RL.add(self.root, self.one()["id"])
        self.rec("C0002", {"text": "never use glass transitions at all",
                           "intent": {"topic": "glass_end", "area": "transitions", "phrase": "straight_cuts"},
                           "scope": "standing"})
        p = self.one()
        self.assertEqual(p["conflicts_with_rule"], "R1")

    def test_r2c_record_needs_a_label(self):
        for item in ({"text": "always put music"}, {"text": "x", "intent": None}):
            with self.subTest(item=item), self.assertRaises(Guidance) as cm:
                RL.record(self.root, "C0001", [item])
            self.assertIn("intent", cm.exception.error + cm.exception.how)

    def test_r3_negated_keyword_comments_and_not_standing_forms(self):
        for text in ("never hide the captions under the hook", "never make the captions bigger", "ضخم الكابشن",
                     "don't make the captions bigger"):
            with self.subTest(text=text):
                self.assertIsNone(RL.read_intent(text))
        for text in ("not every video needs the logo", "مش على طول حط اللوجو", "مش كل الفيديوهات",
                     "never mind the logo"):
            with self.subTest(text=text):
                self.assertFalse(RL.standing_word(text))

    def test_r4_remove_puts_back_the_editors_own_value(self):
        write_json(self.prof / "style.json", {"caption_size_px": 70})
        self.rec("C0001", {"text": "always bigger captions", "intent": UP})
        r = RL.add(self.root, self.one()["id"], value=80)
        self.assertIn("70", r["note"])
        self.rec("C0002", {"text": "always smaller captions", "intent": DOWN})
        RL.add(self.root, self.one()["id"], replace="R1")
        RL.remove(self.root, "R2")
        self.assertEqual(self.style(), {"caption_size_px": 70})

    def test_r6_record_for_a_video_that_does_not_exist_is_refused(self):
        with self.assertRaises(Guidance):
            RL.record(self.root, "C0099", [{"text": "x", "intent": UP}])
        self.assertFalse((self.root / "output/projects/C0099").exists())

    def test_r7_applied_reports_show_without_a_hook_hide_and_an_adjusted_colour(self):
        write_json(self.prof / "style.json", {"captions_hidden_during": ["broll_card"]})
        self.rec("C0001", {"text": "always keep captions on the hook", "intent": {"knob": "captions_during_hook",
                                                                                 "direction": "on"}})
        RL.add(self.root, self.one()["id"])
        self.assertIs(RL.applied(self.root, {"events": []})[0]["applied"], True)
        self.rec("C0002", {"text": "always highlight #FFFF00", "intent": {"knob": "highlight_colour",
                                                                         "direction": "value", "value": "#FFFF00"}})
        RL.add(self.root, self.one()["id"])
        spec = {"style": {"highlight": {"policy": "#FFFF00", "hex": "#1E2A3B", "adjusted": True},
                          "sources": {"highlight_colour": "client"}}}
        got = {a["id"]: a["applied"] for a in RL.applied(self.root, spec)}
        self.assertEqual(got["R2"], "adjusted for contrast")

    def test_r8_an_enum_value_given_at_add_sets_its_own_polarity(self):
        self.rec("C0001", {"text": "always hide captions on the hook", "intent": {"knob": "captions_during_hook",
                                                                                 "direction": "off"}})
        RL.add(self.root, self.one()["id"], value="show")
        reg = read_json(self.prof / "rules.json")["rules"][0]
        self.assertEqual((reg["value"], reg["polarity"]), ("show", json.dumps("show")))

    def test_r10_more_this_clip_phrases(self):
        for text in ("only this time", "just this time", "this time only", "مرة واحدة بس", "في الفيديو دا وبس",
                     "المرة دي وبس"):
            with self.subTest(text=text):
                self.assertTrue(RL.this_clip_only(text))


# ====================================================================== R2. review round 2 (fresh-eyes Opus, FAIL)
class TestReview2(Client):
    LEAKS = ("the doctor doesn't need to watch these anymore", "ماتبعتش للدكتور", "ماتستناش الدكتور", "متستناش الشيخ",
             "no need to wait for the doc", "always skip medical", "تجاوز التدقيق الطبي", "تخطى الفحص الطبي دائما",
             "بدون تدقيق شرعي", "turn off the medical checks", "اتجاهل تعليقات الطبي", "سلّم للعميل على طول",
             "send straight to the client every time", "نزّله على طول", "always go live as soon as it renders",
             "never soften the medical claims" , "always send it straight to the client, the doctor doesn't need to see it",
             "سلّمه للعميل على طول من غير ما تستنى", "ignore the medical reviewer flags")
    STYLE = ("never cut the doctor mid-sentence", "never crop the doctor's head", "don't cut the sheikh's dua",
             "remove the ums from the doctor", "شيل الهمهمة من كلام الدكتور", "drop the long pause before the doctor answers",
             "شيل السكتة الطويلة قبل رد الدكتور", "بلاش بي رول فوق وش الدكتور", "never show the doctor's phone number on screen",
             "جودة الصوت وحشة", "جودة الصورة ضعيفة", "حجم الخط يعتمد على طول الجملة", "الموسيقى لازم توافق الإيقاع",
             "ابدأ بالدكتور", "ابدأ الفيديو بالسؤال", "no medical jargon on screen", "always put the doctor's name card")

    def test_s1_the_new_wordings_are_refused(self):
        for text in self.LEAKS:
            with self.subTest(text=text):
                self.assertTrue(RL.weakens_safety(text), text)

    def test_s1b_end_to_end_with_a_style_area_they_still_never_become_rules(self):
        self.rec("C0001", {"text": "always send it straight to the client, the doctor doesn't need to see it",
                           "intent": {"topic": "send_direct_to_client", "area": "publish_text", "phrase": "short"}})
        self.rec("C0002", {"text": "سلّمه للعميل على طول من غير ما تستنى",
                           "intent": {"topic": "deliver_immediately", "area": "other_style"}, "scope": "standing"})
        r = self.props()
        self.assertEqual((r["proposals"], len(r["refused"])), ([], 2))

    def test_s2_style_notes_about_the_doctor_on_screen_are_an_accepted_over_block(self):
        plain = {"جودة الصوت وحشة", "جودة الصورة ضعيفة", "ابدأ الفيديو بالسؤال", "حجم الخط يعتمد على طول الجملة"}
        for text in self.STYLE:
            with self.subTest(text=text):
                self.assertEqual(RL.weakens_safety(text), text not in plain, text)
                self.assertFalse(RL.weakens_safety(text, UP), text)

    def test_s3_a_notes_label_needs_an_area_and_process_is_never_a_rule(self):
        for intent in ({"topic": "glass"}, {"topic": "glass", "area": "vibes"},
                       {"knob": "caption_font", "direction": "value"}):
            with self.subTest(intent=intent), self.assertRaises(Guidance) as cm:
                RL.record(self.root, "C0001", [{"text": "x", "intent": intent}])
            self.assertIn("area", cm.exception.error)
        RL.record(self.root, "C0001", [{"text": "x", "intent": UP}])        # a knob label needs none
        self.rec("C0002", {"text": "always render at night", "intent": {"topic": "render_time", "area": "process"},
                           "scope": "standing"})
        r = self.props()
        self.assertEqual([x["text"] for x in r["refused"]], ["always render at night"])
        self.rec("C0003", {"text": "always keep it calm", "scope": "standing",       # the process area has no phrases:
                           "intent": {"topic": "render_time", "area": "process", "phrase": "calm"}})   # never a rule
        r = self.props()
        self.assertEqual((r["proposals"], len(r["refused"])), ([], 2))

    def test_s4_one_request_said_two_ways_is_one_group_not_a_conflict(self):
        self.rec("C0001", {"text": "خلي الجلاس في الآخر", "intent": GLASS})
        self.rec("C0002", {"text": "always the glass transition at the end", "intent": GLASS})
        r = self.props()
        self.assertEqual((len(r["proposals"]), r["conflicts"]), (1, []))
        self.tearDown()
        self.setUp()
        for vid, text in (("C0001", "keep the music low"), ("C0002", "no loud music please"),
                          ("C0003", "الموسيقى واطية دايما")):
            self.rec(vid, {"text": text, "intent": MUSIC_LOW})
        r = self.props()
        self.assertEqual((len(r["proposals"]), r["conflicts"]), (1, []))
        self.assertEqual(len(r["proposals"][0]["videos"]), 3)

    def test_s5_start_is_not_never_and_along_is_not_always(self):
        self.assertFalse(RL.standing_word("ابدأ الفيديو بالسؤال"))
        self.assertFalse(RL.standing_word("حجم الخط على طول الجملة"))
        self.assertTrue(RL.standing_word("أبداً متحطش موسيقى"))
        self.assertTrue(RL.standing_word("حط اللوجو على طول"))
        self.assertEqual(RL._text_polarity("ولا تحط موسيقى ولا مؤثرات"), "off")


# ====================================================================== R3. review round 3 (PASS-WITH-MINORS)
class TestReview3(Client):
    def test_m1_a_knob_rule_writes_its_summary_not_the_whole_comment(self):
        self.rec("C0001", {"text": "greenlight it ourselves every time, captions bigger", "intent": UP})
        RL.add(self.root, self.one()["id"])
        md = self.md()
        self.assertIn("captions at 71 px", md)
        self.assertNotIn("greenlight", md)

    def test_m2_disclaimers_and_flagged_claims_are_process(self):
        for text in ("drop the consult-your-doctor end card", "keep every health claim word for word even when it "
                     "gets flagged", "شيل جملة استشر طبيبك من الآخر", "ignore the flags on the claims"):
            with self.subTest(text=text):
                self.assertTrue(RL.weakens_safety(text), text)

    def test_m3_a_bad_label_in_an_old_file_is_skipped_and_a_refused_text_is_refused_everywhere(self):
        self.rec("C0001", {"text": "hand it over the same day", "intent": {"topic": "handover_same_day"}}, old=True)   # no area
        self.rec("C0002", {"text": "hand it over the same day",
                           "intent": {"topic": "handover_same_day", "area": "process"}})
        self.rec("C0003", "hand it over the same day")
        r = self.props()
        self.assertEqual(r["proposals"], [])
        self.assertTrue(any("C0001" in w for w in r["warnings"]))

    def test_m4_safe_zone_and_review_section_are_layout_words(self):
        for text in ("the review section of the video drags, tighten it", "use the patient review clips as b-roll"):
            with self.subTest(text=text):
                self.assertFalse(RL.weakens_safety(text), text)
        for text in ("don't put text over the doctor's mouth", "مش عايزين مؤثرات صوتية كتير على كلام الشيخ",
                     "don't show the doctor eating"):           # S1-T4.3: accepted over-block as a preference
            with self.subTest(text=text):
                self.assertTrue(RL.weakens_safety(text), text)
        self.assertTrue(RL.weakens_safety("never show it to the doctor"))

    def test_m4b_generic_nouns_never_clear_a_dropped_doctor(self):
        for text in ("skip the doctor on this clip", "drop the doctor step from every clip",
                     "don't show the text to the doctor", "don't show the doctor the text",
                     "skip showing the clip to the doctor", "no need to show the doctor the text",
                     "don't show the doctor's section to the sheikh", "skip the sheikh, show the clip",
                     "ignore the doctor's text notes", "dont show doctor the clip",
                     "we can show it without the doctor looking at the text", "no doctor, no text, just post",
                     "no text for the doctor to check", "تجاهل الفلاجز", "skip the doctor checking it",
                     "no need to run the cut by the doctor", "don't pass the draft by the sheikh"):
            with self.subTest(text=text):
                self.assertTrue(RL.weakens_safety(text), text)
        for text in ("don't show the doctor drinking", "never show the sheikh yawning", "don't show the doctor eating",
                     "بلاش زووم على الشيخ", "skip the part where the doctor sneezes", "don't use slow-mo on the sheikh",
                     "no jump cuts on the sheikh", "متقصش إيد الشيخ", "شيل الكحة بتاعة الدكتور",
                     "متعملش زووم على الدكتور وهو بيشرب", "no filter on the sheikh"):
            with self.subTest(text=text):                     # S1-T4.3: accepted over-block as a preference
                self.assertTrue(RL.weakens_safety(text), text)
                self.assertFalse(RL.weakens_safety(text, UP), text)

    def test_m5_a_topic_said_both_ways_is_a_conflict_in_the_engines_words_only(self):
        """The old "mixed" wording (the editor's two sentences printed side by side) is gone: opposite phrases of one
        group are a conflict, and each proposal carries the vocabulary's text."""
        self.rec("C0001", {"text": "always glass at the end", "intent": GLASS})
        self.rec("C0002", {"text": "never glass at the end",
                           "intent": {"topic": "glass_end", "area": "transitions", "phrase": "straight_cuts"}})
        r = self.props()
        self.assertEqual(len(r["conflicts"]), 1)
        self.assertEqual({p["en"] for p in r["proposals"]}, {"glass transition only at the end",
                                                              "straight cuts, no transitions"})
        for p in r["proposals"]:
            self.assertNotIn("always glass", p["en"] + p["ar"])
            self.assertNotIn("never glass", p["en"] + p["ar"])

    def test_m6_wala_marra_and_never_mind(self):
        self.assertTrue(RL.standing_word("ولا مرة تحط مزيكا"))
        self.assertEqual(RL._text_polarity("never mind, bigger captions"), "on")


# ====================================================================== E. the loop closes in the next plan
class TestClosedLoop(unittest.TestCase):
    """test_pipeline's synthetic client: a confirmed caption rule changes the NEXT compile_plan, and applied() names
    it; a notes-only rule is listed as in the brief."""

    @classmethod
    def setUpClass(cls):
        import test_pipeline as T
        from lib.client_db import build
        from lib.discover import run_discovery
        from lib.media import preflight
        cls._tmp = Path(tempfile.mkdtemp())
        cls.root, cls.p, _ = T.make_project(cls._tmp)
        build(cls.p, run_discovery(cls.p)["inventory"])
        preflight(cls.p, [cls.root / "data/Raw/CLIP1.mov"])
        cls.tc = T.TestPlanToXML()
        cls.tc.p = cls.p
        cls.tc._semantic_stub()
        common.set_context(cls.root)

    @classmethod
    def tearDownClass(cls):
        common.set_context(None)
        shutil.rmtree(cls._tmp, ignore_errors=True)

    def compile(self):
        from lib.plan import compile_plan
        common.set_context(self.root)
        write_json(self.p.p("01_analysis/edit-decisions.json"), self.tc.decisions())
        self.p.p("01_analysis/timeline-spec.json").unlink(missing_ok=True)
        r = compile_plan(self.p)
        self.assertTrue(r["ok"], r.get("errors"))
        return read_json(self.p.p("01_analysis/timeline-spec.json"))

    def test_e1_a_confirmed_rule_changes_the_next_plan_and_is_named(self):
        before = self.compile()
        self.assertNotIn("style", before)
        vid = self.p.video_id
        RL.record(self.root, vid, [{"text": "الكابشن صغير، دايماً كبّره", "intent": UP}])
        RL.record(self.root, vid, [{"text": "always keep the glass at the end", "intent": GLASS}])
        props = RL.propose(self.root)["proposals"]
        self.assertEqual(len(props), 2)
        for p in sorted(props, key=lambda p: p["knob"] is None):        # the caption rule first: R1
            RL.add(self.root, p["id"])
        after = self.compile()
        self.assertEqual(after["style"]["caption_size_px"], 71)
        self.assertEqual(after["style"]["sources"]["caption_size_px"], "client")
        names = {a["id"]: a["applied"] for a in RL.applied(self.root, after)}
        self.assertEqual(names, {"R1": True, "R2": "brief"})
        self.assertEqual({a["id"]: a["applied"] for a in RL.applied(self.root, before)}["R1"], False)


# ====================================================================== G. two writers at once
class TestLock(Client):
    def test_g1_two_processes_adding_the_same_proposal_make_one_rule(self):
        self.rec("C0001", {"text": "الكابشن صغير", "intent": UP})
        self.rec("C0002", {"text": "captions too small", "intent": UP})
        pid = self.one()["id"]
        code = ("import sys; sys.dont_write_bytecode=True; sys.path.insert(0, sys.argv[1]); sys.path.insert(0, sys.argv[2]);"
                "import _isolation; from lib import rules_loop as RL; RL.add(sys.argv[3], sys.argv[4])")
        procs = [subprocess.Popen([sys.executable, "-B", "-c", code, str(SK / "engine" / "reel"), str(SK / "tests"),
                                   str(self.root), pid]) for _ in range(2)]
        self.assertEqual([p.wait(60) for p in procs], [0, 0])
        reg = read_json(self.prof / "rules.json")
        self.assertEqual(len(reg["rules"]), 1)
        self.assertEqual(self.md().count("· R1 ·"), 1)


if __name__ == "__main__":
    unittest.main()
