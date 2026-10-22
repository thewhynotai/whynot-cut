# SPDX-License-Identifier: GPL-3.0-or-later
# © 2026 The Why Not AI (thewhynot.ai)
"""Task 25 / K-T7 fix round 2 (review 4fb97dd FAIL, HIGH): cut proposals and takes never touch a recited verse, a
range cut is refused unless its words are one run in time order, an accepted cut made on an older transcript is an
error (never a silent recut), `reel takes` shows each take's time and text, an accepted proposal never removes the last
copy of a line, and the "Proposed cuts" table says what is in the cut.

No Quran text here: the recited span is the manual-verse fixture's neutral placeholder words (شجرة نهر جبل); only the
cue «قال تعالى» is real. Through the real CLI where the finding is reachable from it.
Run:  bash tools/test.sh -p test_t25_r2.py
"""
import sys as _sys
_sys.dont_write_bytecode = True  # keep the plugin folder free of __pycache__
import _isolation  # noqa: F401,E402  G79: sandbox the engine home first (tests/_isolation.py)
import hashlib
import json
import subprocess
import tempfile
import unittest
import wave
from pathlib import Path
from unittest import mock

sys = _sys
SK = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SK / "engine" / "reel"))
sys.path.insert(0, str(SK / "tests"))

from lib import common  # noqa: E402
from lib import cut_proposals as C  # noqa: E402
from lib import lead_steps  # noqa: E402
from lib.common import read_json, write_json  # noqa: E402
from lib.safety import switches  # noqa: E402
from test_manual_verse import build_words, verse_project  # noqa: E402

CLI = SK / "engine/reel/cli.py"
VERSE_WORDS = ("شجرة", "نهر", "جبل")          # the placeholder verse: never real verse text
# a doubled word INSIDE the recited span (after «قال تعالى», up to the 900 ms pause) and one outside it. The verse
# ends on a pause, so the caption run after it is HELD up to the first sentence end (manual_verse.held): «تمام.»
# closes that held run, and «الكلام الكلام» comes after it.
VERSE_TEXT = "مرحبا بيكم النهارده |900 قال تعالى شجرة نهر نهر جبل |900 تمام. وبعدين نكمل الكلام الكلام ده تمام"
PLAIN_TEXT = "مرحبا بيكم النهارده |900 وبعدين نكمل الكلام الكلام ده تمام"
# two takes of one line inside the span, and the same two takes in a plain clip
VERSE_TAKES = "مرحبا بيكم |900 قال تعالى |800 شجرة نهر جبل. شجرة نهر جبل. |900 وبعدين نكمل الكلام ده"
PLAIN_TAKES = "مرحبا بيكم |900 شجرة نهر جبل. شجرة نهر جبل. |900 وبعدين نكمل الكلام ده"
# probe2 of the review: two takes that differ in a word (no best take), and a retake proposal for the first
LINE_TAKES = "الدوا ده بيقلل الضغط. |900 الدوا ده بيقلل الضغط بسرعة. |900 تمام كده"
# the held run right after a pause-ended verse: a doubled word, and the first of two takes, inside it (words the
# plugin's own verse lines never use, so a leak scan cannot match them by chance)
HELD_TEXT = "مرحبا بيكم |900 قال تعالى شجرة نهر جبل |900 وبعدين نكمل البرتقال البرتقال ده. |900 تمام كده"
HELD_TAKES = "مرحبا بيكم |900 قال تعالى شجرة نهر جبل |900 الدوا ده مهم. الدوا ده مهم. |900 تمام كده"
# a retake inside one sentence: a retake proposal, no `reel takes` group
INNER_RETAKE = "الدوا ده بيقلل الدوا ده بيقلل الضغط. |900 تمام كده"


def env():
    from test_plugin import isolated_env
    return isolated_env()


def leaks(text: str) -> list:
    return [w for w in VERSE_WORDS if w in str(text)]


class Base(unittest.TestCase):
    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.addCleanup(self._td.cleanup)
        self.tmp = Path(self._td.name)
        self.addCleanup(common.set_context, None)

    def project(self, text, domain="religious", glob=None):
        self.words = build_words(text)
        self.root, self.p = verse_project(self.tmp, self.words, domain=domain, glob=glob)
        return self.p

    def reel(self, *argv, token=True):
        args = ["--root", str(self.root), "--video-id", "CLIP1", *argv]
        e = env()
        if token:
            lead_steps.issue_for(args, e)
        r = subprocess.run([sys.executable, "-B", str(CLI), *args], capture_output=True, env=e)
        return r.returncode, r.stdout.decode("utf-8"), r.stderr.decode("utf-8", "replace")

    def switch(self, on=True):
        write_json(self.root / common.CLIENT_PROFILE_REL / "safety.json",
                   {"switches": {switches.TASK25_PLAN_PROPOSALS: on}})

    def ed(self):
        return read_json(self.p.p("01_analysis/edit-decisions.json"))

    def words_sha(self):
        return hashlib.sha1(self.p.p("02_transcription/words.json").read_bytes()).hexdigest()

    def at(self, text, n=0):
        return [w for w in self.words if w["word"] == text][n]

    def plan(self):
        from lib.plan import compile_plan
        common.set_context(self.root)
        return compile_plan(self.p)

    def edit_plan(self):
        return self.p.p("01_analysis/edit-plan.md").read_text(encoding="utf-8")

    def doc_with(self, proposals):
        """A cut-proposals.json that is current for this transcript and these inputs (as `reel cut-proposals` writes
        it), holding exactly `proposals`."""
        data = self.p.p("02_transcription/words.json").read_bytes()
        common.set_context(self.root)
        sha = C._inputs(self.p, data, json.loads(data.decode("utf-8-sig")))["sha1"]
        doc = {"schema": C.SCHEMA, "video_id": "CLIP1", "words_sha1": hashlib.sha1(data).hexdigest(),
               "inputs_sha1": sha, "language": "ar", "snapped": False, "proposals": proposals, "totals": {},
               "notes": []}
        write_json(self.p.p(C.FILE), doc)
        return doc

    def verse_proposal(self):
        b = self.at("نهر", 1)
        return {"id": "CP-001", "kind": "repeat_word", "start_ms": b["start_ms"] - 20, "end_ms": b["end_ms"] + 20,
                "word_ids": [b["id"]], "words": "نهر", "confidence": 0.9, "reason": "«نهر» اتقالت مرتين",
                "reason_en": '"نهر" said twice', "default": "proposed"}


# --------------------------------------------------------------------------- P1-1: the recited verse
class TestVerse(Base):
    def test_no_proposal_inside_a_verse_and_no_verse_word_anywhere(self):
        self.project(VERSE_TEXT)
        code, out, err = self.reel("cut-proposals")
        self.assertEqual(code, 0, out + err)
        doc = read_json(self.p.p(C.FILE))
        lo, hi = self.at("شجرة")["start_ms"], self.at("جبل")["end_ms"]
        self.assertEqual([p["id"] for p in doc["proposals"] if p["start_ms"] < hi and lo < p["end_ms"]], [])
        self.assertTrue([p for p in doc["proposals"] if p["kind"] == "repeat_word"])     # «الكلام الكلام» outside
        self.assertEqual(leaks(self.p.p(C.FILE).read_text(encoding="utf-8")), [])
        self.assertEqual(leaks(out), [])

    def test_the_same_words_without_the_cue_are_proposed(self):
        """Control: the fixture's doubled placeholder word is proposed when nobody recites."""
        self.project(VERSE_TEXT.replace("قال تعالى ", "وكمان "), domain=None)
        self.assertEqual(self.reel("cut-proposals")[0], 0)
        doc = read_json(self.p.p(C.FILE))
        self.assertIn("نهر", json.dumps(doc, ensure_ascii=False))

    def test_a_retake_whose_kept_take_is_in_a_verse_is_not_proposed(self):
        from lib import manual_verse
        self.project(PLAIN_TAKES, domain=None)
        b = [w for w in self.words if w["word"].startswith("جبل")][1]
        ed = self.ed()
        ed["manual_verse"] = [{"start_ms": b["start_ms"] - 1200, "end_ms": b["end_ms"]}]    # the second take only
        write_json(self.p.p("01_analysis/edit-decisions.json"), ed)
        self.assertEqual(self.reel("cut-proposals")[0], 0)
        self.assertEqual([p for p in read_json(self.p.p(C.FILE))["proposals"] if p["kind"] == "retake"], [])
        self.assertTrue(manual_verse)

    def test_takes_inside_a_verse_are_never_listed(self):
        self.project(VERSE_TAKES)
        code, out, err = self.reel("takes")
        self.assertEqual(code, 0, out + err)
        self.assertEqual(json.loads(out)["groups"], [])
        self.assertEqual(leaks(out), [])
        self.project(PLAIN_TAKES, domain=None)                 # control: the same takes, no cue
        code, out, _ = self.reel("takes")
        self.assertEqual(len(json.loads(out)["groups"]), 1)

    def test_accept_refuses_an_id_inside_a_verse(self):
        self.project(VERSE_TEXT)
        self.doc_with([self.verse_proposal()])
        before = self.p.p("01_analysis/edit-decisions.json").read_bytes()
        code, out, err = self.reel("cut-proposals", "--accept", "CP-001")
        self.assertNotEqual(code, 0, out + err)
        self.assertIn("recited verse", out + err)
        self.assertIn("آية", out + err)
        self.assertEqual(leaks(out + err), [])
        self.assertEqual(self.p.p("01_analysis/edit-decisions.json").read_bytes(), before)

    def test_table_and_markers_never_show_a_verse_proposal(self):
        self.project(VERSE_TEXT)
        self.switch(True)
        self.doc_with([self.verse_proposal()])
        res = self.plan()
        self.assertTrue(res["ok"], res["errors"])
        self.assertEqual(leaks(self.edit_plan()), [])
        self.assertNotIn("| CP-001 |", self.edit_plan())
        from lib.ppro_build import _cut_proposal_markers
        spec = read_json(self.p.p("01_analysis/timeline-spec.json"))
        self.assertEqual(_cut_proposal_markers(self.p, spec, 1 / 24), [])

    def test_a_held_run_after_a_verse_is_protected_too(self):
        """The verse fix round 2 (manual_verse.held, not on HEAD yet): an unreleased held run counts as verse."""
        from lib import manual_verse
        self.project(PLAIN_TEXT, domain=None)
        a, b = self.at("الكلام", 0), self.at("الكلام", 1)
        run = [{"id": "MV01H", "after": "MV01", "src_start_ms": a["start_ms"], "src_end_ms": b["end_ms"],
                "end": "sentence", "released": False}]
        with mock.patch.object(manual_verse, "held", create=True, return_value=(run, [], [])):
            common.set_context(self.root)
            doc = C.propose(self.p)
        self.assertEqual([p for p in doc["proposals"] if p["kind"] == "repeat_word"], [])
        run[0]["released"] = True                               # released by the editor: proposals come back
        with mock.patch.object(manual_verse, "held", create=True, return_value=(run, [], [])):
            doc = C.propose(self.p)
        self.assertTrue([p for p in doc["proposals"] if p["kind"] == "repeat_word"])

    def test_a_profile_that_cannot_be_read_fails_closed(self):
        """A damaged profile.json: the proposals still run, the verse is protected, and the religious verse phrases
        count (fail closed), as for a religious client."""
        from lib import manual_verse
        self.project(VERSE_TEXT, domain=None)
        write_json(self.root / common.CLIENT_PROFILE_REL / "profile.json", ["x"])
        with mock.patch.object(manual_verse, "config", wraps=manual_verse.config) as m:
            common.set_context(self.root)
            doc = C.propose(self.p)
        self.assertEqual(m.call_args.args[0], {"domain": "religious"})
        self.assertEqual(leaks(json.dumps(doc, ensure_ascii=False)), [])

    def test_a_cut_verse_word_keeps_its_reason_out_of_the_plan(self):
        """A hand-written cut on a verse word: the plan lists it as «…» and its reason as no text."""
        self.project(VERSE_TEXT)
        ed = self.ed()
        ed["global"]["cut_words"] = [{"word_ids": [self.at("نهر", 1)["id"]], "reason": "نهر مكررة"}]
        write_json(self.p.p("01_analysis/edit-decisions.json"), ed)
        res = self.plan()
        self.assertTrue(res["ok"], res["errors"])
        self.assertEqual(leaks(self.edit_plan()), [])
        self.assertEqual(leaks(self.p.p("01_analysis/timeline-spec.json").read_text(encoding="utf-8")), [])


class TestHeldRun(Base):
    """The verse fix round 2's hold (manual_verse.held, on HEAD since 89495fa): the caption run right after a verse
    that ends on a pause may still be the verse, so until the editor releases it (`manual_verse_release`) nothing in
    it is proposed or listed as a take. After the release it is the speaker's own words again."""
    def held_run(self):
        from lib import manual_verse as mv
        spans, _, _ = mv.resolve(mv.detect(self.words, mv.config({"domain": "religious"})), self.ed())
        runs, _, _ = mv.held(spans, self.words, self.ed())
        self.assertEqual(len(runs), 1, runs)
        return runs[0]

    def release(self, run):
        ed = self.ed()
        ed["manual_verse_release"] = [{"start_ms": run["src_start_ms"], "end_ms": run["src_end_ms"]}]
        write_json(self.p.p("01_analysis/edit-decisions.json"), ed)

    def test_no_proposal_in_a_held_run_until_it_is_released(self):
        self.project(HELD_TEXT)
        run = self.held_run()
        self.assertEqual(self.reel("cut-proposals")[0], 0)
        props = read_json(self.p.p(C.FILE))["proposals"]
        self.assertEqual([p["id"] for p in props if p["start_ms"] < run["src_end_ms"] and run["src_start_ms"] <
                          p["end_ms"]], [])
        self.assertEqual([p for p in props if p["kind"] == "repeat_word"], [])
        self.release(run)
        self.assertEqual(self.reel("cut-proposals")[0], 0)
        rep = [p for p in read_json(self.p.p(C.FILE))["proposals"] if p["kind"] == "repeat_word"]
        self.assertEqual(len(rep), 1, rep)
        self.assertIn(rep[0]["word_ids"], ([self.at("البرتقال", 0)["id"]], [self.at("البرتقال", 1)["id"]]))

    def test_switch_on_no_held_word_in_any_output(self):
        """Review 89495fa P2-6: with task25_plan_proposals ON, no word of an unreleased held run reaches
        cut-proposals.json, the "Proposed cuts" table in edit-plan.md or the CP markers of the Premiere job, even from
        a list that holds a proposal there (belt and braces: the table and the markers skip it too)."""
        from lib.plan import compile_plan
        from lib.ppro_build import _cut_proposal_markers
        self.project(HELD_TEXT)
        self.switch(True)
        held = ("وبعدين", "نكمل", "البرتقال")
        self.assertEqual(self.reel("cut-proposals")[0], 0)
        self.assertEqual([w for w in held if w in self.p.p(C.FILE).read_text(encoding="utf-8")], [])
        b = self.at("البرتقال", 1)
        self.doc_with([{"id": "CP-001", "kind": "repeat_word", "start_ms": b["start_ms"] - 20, "end_ms": b["end_ms"] + 20,
                        "word_ids": [b["id"]], "words": "البرتقال", "confidence": 0.9, "reason": "«البرتقال» اتقالت مرتين",
                        "reason_en": '"البرتقال" said twice', "default": "proposed"}])
        common.set_context(self.root)
        res = compile_plan(self.p)
        self.assertTrue(res["ok"], res["errors"])
        self.assertNotIn("| CP-001 |", self.edit_plan())
        self.assertEqual([w for w in held if w in self.edit_plan()], [])
        # the CP markers job_data adds to the bridge job (the full job needs real footage: test_cut_proposals_hooks
        # builds it on the golden project)
        spec = read_json(self.p.p("01_analysis/timeline-spec.json"))
        markers = _cut_proposal_markers(self.p, spec, 1 / 24)
        self.assertEqual(markers, [])
        self.assertEqual([w for w in held if w in json.dumps(markers, ensure_ascii=False)], [])

    def test_no_take_in_a_held_run_until_it_is_released(self):
        self.project(HELD_TAKES)
        run = self.held_run()
        code, out, err = self.reel("takes")
        self.assertEqual(code, 0, out + err)
        self.assertEqual(json.loads(out)["groups"], [])
        self.release(run)
        code, out, err = self.reel("takes")
        self.assertEqual(code, 0, out + err)
        g = json.loads(out)["groups"]
        self.assertEqual(len(g), 1, g)
        self.assertEqual([t["text"] for t in g[0]["takes"]], ["الدوا ده مهم.", "الدوا ده مهم."])


# --------------------------------------------------------------------------- accept: what it writes
class TestAccept(Base):
    def accepted(self):
        self.project(PLAIN_TEXT, domain=None)
        self.assertEqual(self.reel("cut-proposals")[0], 0)
        cp = next(p for p in read_json(self.p.p(C.FILE))["proposals"] if p["kind"] == "repeat_word")
        code, out, err = self.reel("cut-proposals", "--accept", cp["id"])
        self.assertEqual(code, 0, out + err)
        return cp, json.loads(out)

    def test_the_saved_entry_holds_no_words_and_names_the_editor(self):
        cp, _ = self.accepted()
        e = self.ed()["global"]["cut_words"][-1]
        self.assertEqual(e["reason"], f"{cp['id']} repeat_word")
        self.assertEqual(e["by"], "editor")
        self.assertEqual(e["words_sha1"], self.words_sha())
        self.assertEqual(e["word_ids"], cp["word_ids"])
        self.assertEqual(e["range_ms"], [cp["start_ms"], cp["end_ms"]])

    def test_switch_off_says_the_take_is_cut_word_by_word(self):
        _, res = self.accepted()
        self.assertIn("task25_plan_proposals", res["note"])
        self.assertIn("كلمة كلمة", res["note"])

    def test_switch_on_has_no_such_note(self):
        self.project(PLAIN_TEXT, domain=None)
        self.switch(True)
        self.assertEqual(self.reel("cut-proposals")[0], 0)
        cp = next(p for p in read_json(self.p.p(C.FILE))["proposals"] if p["kind"] == "repeat_word")
        code, out, err = self.reel("cut-proposals", "--accept", cp["id"])
        self.assertEqual(code, 0, out + err)
        self.assertNotIn("note", json.loads(out))

    def test_ids_go_space_or_comma_separated(self):
        self.project(PLAIN_TEXT, domain=None)
        self.assertEqual(self.reel("cut-proposals")[0], 0)
        ids = [p["id"] for p in read_json(self.p.p(C.FILE))["proposals"] if p["kind"] in C.WORD_KINDS]
        code, out, err = self.reel("cut-proposals", "--accept", *ids)
        self.assertEqual(code, 0, out + err)
        self.assertEqual(json.loads(out)["added"], ids)

    def test_the_last_copy_of_a_line_is_never_removed(self):
        """probe2: the editor dropped take 2; the retake proposal that drops take 1 is then refused."""
        self.project(LINE_TAKES, domain=None)
        self.assertEqual(self.reel("cut-proposals")[0], 0)
        retake = next(p for p in read_json(self.p.p(C.FILE))["proposals"] if p["kind"] == "retake")
        self.assertEqual(self.reel("takes")[0], 0)
        code, out, err = self.reel("takes", "--drop", "2")
        self.assertEqual(code, 0, out + err)
        before = self.p.p("01_analysis/edit-decisions.json").read_bytes()
        code, out, err = self.reel("cut-proposals", "--accept", retake["id"])
        self.assertNotEqual(code, 0, out + err)
        self.assertIn("last copy of the line", out + err)
        self.assertIn("الجملة هتختفي", out + err)
        self.assertEqual(self.p.p("01_analysis/edit-decisions.json").read_bytes(), before)

    def test_a_retake_whose_kept_take_was_cut_by_hand_is_refused(self):
        self.project(LINE_TAKES, domain=None)
        self.assertEqual(self.reel("cut-proposals")[0], 0)
        retake = next(p for p in read_json(self.p.p(C.FILE))["proposals"] if p["kind"] == "retake")
        ed = self.ed()
        ed["global"]["cut_words"] = [{"word_ids": list(retake["keep"]["word_ids"]), "reason": "by hand"}]
        write_json(self.p.p("01_analysis/edit-decisions.json"), ed)
        self.doc_with(read_json(self.p.p(C.FILE))["proposals"])        # the edit list changed nothing it hashes
        code, out, err = self.reel("cut-proposals", "--accept", retake["id"])
        self.assertNotEqual(code, 0, out + err)
        self.assertIn("last copy of the line", out + err)


# --------------------------------------------------------------------------- P2-1 / P2-2: the plan's word cuts
W = [{"id": i, "word": w, "start_ms": a, "end_ms": b} for i, (w, a, b) in enumerate(
    [("قال", 0, 300), ("أول", 400, 650), ("حاجة", 710, 1000), ("لازم", 1060, 1360), ("أول", 1900, 2150)], 1)]


class TestWordCutRanges(unittest.TestCase):
    def wcr(self, entries, whole=True, sha=None, words=W):
        from lib.plan import word_cut_ranges
        return word_cut_ranges(words, entries, 5000, whole=whole, words_sha1=sha)

    def test_a_good_range_is_one_cut_only_when_whole(self):
        e = [{"word_ids": [2, 3, 4], "range_ms": [360, 1860]}]
        self.assertEqual(self.wcr(e)[0], [(360, 1860)])
        self.assertEqual(len(self.wcr(e, whole=False)[0]), 3)
        self.assertEqual(self.wcr(e, whole=False)[2], [])

    def test_gap_ids_are_refused(self):
        for whole in (True, False):
            with self.subTest(whole=whole):
                r, cut, err = self.wcr([{"word_ids": [2, 4], "range_ms": [380, 1380]}], whole)
                self.assertEqual((r, cut), ([], []))
                self.assertTrue(any("not next to each other" in x and "مش ورا بعض" in x for x in err), err)

    def test_ids_out_of_time_order_are_refused(self):
        r, cut, err = self.wcr([{"word_ids": [3, 2], "range_ms": [360, 1030]}])
        self.assertEqual((r, cut), ([], []))
        self.assertTrue(any("not next to each other" in x for x in err), err)

    def test_a_word_between_them_in_time_is_refused(self):
        words = W + [{"id": 8, "word": "و", "start_ms": 660, "end_ms": 700}]
        r, cut, err = self.wcr([{"word_ids": [2, 3], "range_ms": [380, 1030]}], words=words)
        self.assertEqual((r, cut), ([], []))
        self.assertTrue(any("not next to each other" in x for x in err), err)

    def test_a_range_over_a_neighbour_is_an_older_transcript(self):
        for whole in (True, False):
            for bad in ([200, 1860], [360, 2000], [500, 1860], [360, 1200]):
                with self.subTest(whole=whole, range_ms=bad):
                    r, cut, err = self.wcr([{"word_ids": [2, 3, 4], "range_ms": bad, "reason": "CP-004 retake"}],
                                           whole)
                    self.assertEqual((r, cut), ([], []))
                    self.assertTrue(any("older transcript" in x and "تفريغ قديم" in x and "CP-004" in x
                                        for x in err), err)

    def test_an_unknown_word_in_a_range_entry_is_an_older_transcript(self):
        r, cut, err = self.wcr([{"word_ids": [2, 99], "range_ms": [360, 1030], "reason": "TK-3 take dropped"}])
        self.assertEqual((r, cut), ([], []))
        self.assertTrue(any("older transcript" in x and "TK-3" in x for x in err), err)

    def test_an_entry_made_on_other_words_is_an_older_transcript(self):
        e = [{"word_ids": [2, 3, 4], "range_ms": [360, 1860], "words_sha1": "a" * 40, "reason": "TK-2 x"}]
        for whole in (True, False):
            with self.subTest(whole=whole):
                r, cut, err = self.wcr(e, whole, sha="b" * 40)
                self.assertEqual((r, cut), ([], []))
                self.assertTrue(any("older transcript" in x for x in err), err)
        self.assertEqual(self.wcr(e, True, sha="a" * 40)[0], [(360, 1860)])

    def test_a_malformed_range_is_refused_never_a_crash(self):
        for bad in ([360, 1000, 1860], [True, 1860], [360, False], ["360", 1860], [1860, 360], "x", [360]):
            with self.subTest(range_ms=bad):
                r, cut, err = self.wcr([{"word_ids": [2, 3, 4], "range_ms": bad}])
                self.assertEqual((r, cut), ([], []))
                self.assertTrue(any("range_ms" in x for x in err), err)

    def test_a_repeated_id_is_refused(self):
        r, cut, err = self.wcr([{"word_ids": [2, 2, 3], "range_ms": [360, 1030]}])
        self.assertEqual((r, cut), ([], []))
        self.assertTrue(any("not next to each other" in x for x in err), err)

    def test_the_label_never_quotes_the_reason_text(self):
        r, cut, err = self.wcr([{"word_ids": [2, 4], "range_ms": [380, 1380], "reason": "نهر مكررة"}])
        self.assertTrue(err)
        self.assertFalse(any("نهر" in x for x in err), err)
        self.assertTrue(any("cut_words[0]" in x for x in err), err)

    def test_plain_entries_are_as_before(self):
        r, cut, err = self.wcr([{"word_ids": [2], "reason": "filler"}, 3, 99])
        self.assertEqual(len(r), 2)
        self.assertEqual(err, ["cut_words: word 99 not in words.json"])

    def test_the_switch_is_never_read_from_the_context(self):
        """P3-5: word_cut_ranges is pure: the switch comes in as `whole`."""
        from lib.plan import word_cut_ranges
        with mock.patch("lib.safety.switches.enabled", return_value=True):
            r, _, _ = word_cut_ranges(W, [{"word_ids": [2, 3, 4], "range_ms": [360, 1860]}], 5000)
        self.assertEqual(len(r), 3)


class TestStaleThroughTheCli(Base):
    def plan_cli(self):
        for rel, body in (("01_analysis/editing-style.json", "{}"), ("01_analysis/main-topic.md", "topic"),
                          ("01_analysis/narrative-segments.json", "{}"),
                          ("01_analysis/transcript-semantic-analysis.json", "{}"),
                          ("01_analysis/medical-content-review.md", "none")):
            if not self.p.p(rel).exists():
                self.p.p(rel).write_text(body, encoding="utf-8")
        return self.reel("plan")

    def test_a_re_transcription_after_accept_stops_the_plan(self):
        self.project(PLAIN_TEXT, domain=None)
        self.assertEqual(self.reel("cut-proposals")[0], 0)
        cp = next(p for p in read_json(self.p.p(C.FILE))["proposals"] if p["kind"] == "repeat_word")
        self.assertEqual(self.reel("cut-proposals", "--accept", cp["id"])[0], 0)
        code, out, err = self.plan_cli()
        self.assertEqual(code, 0, out + err)                    # the plan compiles before the new transcription
        wj = read_json(self.p.p("02_transcription/words.json"))
        for w in wj["words"]:                                   # the same ids, other words (a new transcription)
            if w["id"] in cp["word_ids"]:
                w["word"] = "مش"
        write_json(self.p.p("02_transcription/words.json"), wj)
        code, out, err = self.plan_cli()
        self.assertNotEqual(code, 0, out + err)
        self.assertIn("older transcript", out + err)
        self.assertIn("تفريغ قديم", out + err)

    def test_a_dropped_take_on_an_older_transcript_stops_the_plan(self):
        self.project(LINE_TAKES, domain=None)
        self.assertEqual(self.reel("takes")[0], 0)
        self.assertEqual(self.reel("takes", "--drop", "2")[0], 0)
        e = self.ed()["global"]["cut_words"][-1]
        self.assertEqual(e["words_sha1"], self.words_sha())
        code, out, err = self.plan_cli()
        self.assertEqual(code, 0, out + err)
        wj = read_json(self.p.p("02_transcription/words.json"))
        wj["words"][-1]["word"] = "خلاص"
        write_json(self.p.p("02_transcription/words.json"), wj)
        code, out, err = self.plan_cli()
        self.assertNotEqual(code, 0, out + err)
        self.assertIn("older transcript", out + err)


# --------------------------------------------------------------------------- P2-3: what `reel takes` shows
class TestTakesOutput(Base):
    def test_each_take_has_its_time_and_text(self):
        self.project(PLAIN_TAKES, domain=None)
        code, out, err = self.reel("takes")
        self.assertEqual(code, 0, out + err)
        g = json.loads(out)["groups"][0]
        self.assertEqual([t["n"] for t in g["takes"]], [2, 3])
        first = [w for w in self.words if w["word"] == "شجرة"]
        self.assertEqual(g["takes"][0]["from"], common.fmt_ts(first[0]["start_ms"], "."))
        self.assertEqual(g["takes"][1]["from"], common.fmt_ts(first[1]["start_ms"], "."))
        self.assertEqual(g["takes"][0]["to"], common.fmt_ts(first[0]["start_ms"] + 3 * 350 + 2 * 50, "."))
        self.assertEqual(g["takes"][0]["text"], "شجرة نهر جبل.")
        self.assertEqual(set(g["takes"][0]), {"n", "from", "to", "text"})
        self.assertIs(json.loads(out)["audio"], False)

    def test_the_audio_is_measured_when_it_is_there(self):
        self.project(PLAIN_TAKES, domain=None)
        wav = self.p.p("02_transcription/dialogue_16k_mono.wav")
        with wave.open(str(wav), "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(16000)
            w.writeframes(b"\x10\x00" * (16000 * 6))
        code, out, err = self.reel("takes")
        self.assertEqual(code, 0, out + err)
        self.assertIs(json.loads(out)["audio"], True)
        self.assertEqual(self.reel("cut-proposals")[0], 0)
        self.assertIs(read_json(self.p.p(C.FILE))["snapped"], True)

    def test_drop_switch_off_note(self):
        self.project(LINE_TAKES, domain=None)
        self.assertEqual(self.reel("takes")[0], 0)
        code, out, err = self.reel("takes", "--drop", "2")
        self.assertEqual(code, 0, out + err)
        self.assertIn("task25_plan_proposals", json.loads(out)["note"])


# --------------------------------------------------------------------------- P2-4 / P3: the table and the markers
class TestTable(Base):
    def setup_table(self):
        self.project(PLAIN_TEXT, domain=None)
        self.switch(True)
        a, b = self.at("النهارده"), self.at("وبعدين")              # the 900 ms pause: a pause proposal
        write_json(self.p.p("06_audio/dialogue/pauses.json"), {"cuts_ms": [[a["end_ms"] + 100, b["start_ms"] - 100]]})
        self.assertEqual(self.reel("cut-proposals")[0], 0)
        doc = read_json(self.p.p(C.FILE))
        rep = next(p for p in doc["proposals"] if p["kind"] == "repeat_word")
        return doc, rep

    def row(self, pid):
        return next(x for x in self.edit_plan().splitlines() if x.startswith(f"| {pid} |"))

    def test_accepted_rows_are_ticked_and_the_footer_says_so(self):
        doc, rep = self.setup_table()
        self.assertEqual(self.reel("cut-proposals", "--accept", rep["id"])[0], 0)
        res = self.plan()
        self.assertTrue(res["ok"], res["errors"])
        t = self.edit_plan()
        self.assertIn("في القص؟ / in the cut?", t)
        self.assertTrue(self.row(rep["id"]).rstrip(" |").endswith("✔"), self.row(rep["id"]))
        self.assertIn("اللي عليه ✔ بس هو اللي هيتقص بعد موافقتك", t)
        self.assertIn("only ✔ rows are cut once you approve", t)
        self.assertNotIn("nothing is cut before your approval", t)
        self.assertIn("من (المصدر، ث) / from (source s)", t)
        self.assertTrue([p for p in doc["proposals"] if p["kind"] == "pause"])
        for p in doc["proposals"]:
            if p["kind"] == "pause":
                self.assertIn("بيتشال بالسكتات / via remove_pauses", self.row(p["id"]))
            elif p["id"] != rep["id"]:
                self.assertNotIn("✔", self.row(p["id"]))

    def test_switch_on_cuts_the_accepted_range_whole(self):
        """The switch read in _read_inputs reaches the time map: the accepted range itself is the removed piece."""
        doc, rep = self.setup_table()
        self.assertEqual(self.reel("cut-proposals", "--accept", rep["id"])[0], 0)
        res = self.plan()
        self.assertTrue(res["ok"], res["errors"])
        keep = read_json(self.p.p("01_analysis/timeline-spec.json"))["time_map"]["keep_ms"]
        gaps = [(x[1], y[0]) for x, y in zip(keep, keep[1:])]
        self.assertIn((rep["start_ms"], rep["end_ms"]), [tuple(g) for g in gaps])

    def test_an_unaccepted_row_is_not_ticked(self):
        doc, rep = self.setup_table()
        self.assertTrue(self.plan()["ok"])
        self.assertNotIn("✔ |", self.row(rep["id"]))

    def test_stale_proposals_show_no_rows_and_no_markers(self):
        doc, rep = self.setup_table()
        wj = read_json(self.p.p("02_transcription/words.json"))
        wj["words"][0]["word"] = "أهلا"
        write_json(self.p.p("02_transcription/words.json"), wj)
        self.assertTrue(self.plan()["ok"])
        t = self.edit_plan()
        self.assertIn("قديمة / stale", t)
        self.assertNotIn(f"| {rep['id']} |", t)
        from lib.ppro_build import _cut_proposal_markers
        self.assertEqual(_cut_proposal_markers(self.p, read_json(self.p.p("01_analysis/timeline-spec.json")),
                                               1 / 24), [])

    def test_markers_sit_on_the_sequence_clock(self):
        doc, rep = self.setup_table()
        from lib.ppro_build import _cut_proposal_markers
        keep = [[0, 300], [rep["start_ms"] - 100, 60000]]
        m = _cut_proposal_markers(self.p, {"time_map": {"keep_ms": keep}}, 1 / 24)
        mine = next(x for x in m if x["name"].startswith(rep["id"]))
        self.assertAlmostEqual(mine["t"], (300 + 100) / 1000, places=3)
        self.assertEqual(set(mine), {"t", "name", "comment"})


class TestEmphasisGetsTheSwitch(Base):
    def test_gather_reads_the_switch_once(self):
        from lib import emphasis
        self.project(PLAIN_TEXT, domain=None)
        common.set_context(self.root)
        self.assertIs(emphasis.gather(self.p, audio=False)["t25_whole"], False)
        self.switch(True)
        self.assertIs(emphasis.gather(self.p, audio=False)["t25_whole"], True)

    def test_build_hands_the_switch_to_the_word_cuts(self):
        from lib import emphasis, plan
        self.project(PLAIN_TEXT, domain=None)
        common.set_context(self.root)
        inp = emphasis.gather(self.p, audio=False)
        for on in (True, False):
            with self.subTest(whole=on), mock.patch("lib.plan.word_cut_ranges", wraps=plan.word_cut_ranges) as m:
                emphasis.build(dict(inp, t25_whole=on))
                self.assertIs(m.call_args.kwargs.get("whole"), on)


class TestMoreGuards(Base):
    def test_a_verse_marked_after_the_list_makes_it_stale(self):
        """The verse ranges are part of what the list depends on: a manual_verse added later means a new list."""
        self.project(PLAIN_TEXT, domain=None)
        self.assertEqual(self.reel("cut-proposals")[0], 0)
        cp = next(p for p in read_json(self.p.p(C.FILE))["proposals"] if p["kind"] == "repeat_word")
        ed = self.ed()
        ed["manual_verse"] = [{"start_ms": cp["start_ms"] - 50, "end_ms": cp["end_ms"] + 50}]
        write_json(self.p.p("01_analysis/edit-decisions.json"), ed)
        code, out, err = self.reel("cut-proposals", "--accept", cp["id"])
        self.assertNotEqual(code, 0, out + err)
        self.assertIn("changed after these proposals", out + err)

    def test_a_retake_inside_one_sentence_keeps_its_last_copy(self):
        self.project(INNER_RETAKE, domain=None)
        self.assertEqual(self.reel("cut-proposals")[0], 0)
        retake = next(p for p in read_json(self.p.p(C.FILE))["proposals"] if p["kind"] == "retake")
        ed = self.ed()
        ed["global"]["cut_words"] = [{"word_ids": list(retake["keep"]["word_ids"]), "reason": "by hand"}]
        write_json(self.p.p("01_analysis/edit-decisions.json"), ed)
        code, out, err = self.reel("cut-proposals", "--accept", retake["id"])
        self.assertNotEqual(code, 0, out + err)
        self.assertIn("last copy of the line", out + err)
        self.assertIn(retake["id"], out + err)

    def test_a_take_group_keeps_its_last_copy_whatever_the_proposal(self):
        """A non-retake proposal that cuts the last take left of a `reel takes` group is refused too."""
        self.project(LINE_TAKES, domain=None)
        self.assertEqual(self.reel("takes")[0], 0)
        self.assertEqual(self.reel("takes", "--drop", "2")[0], 0)
        t1 = [w for w in self.words if w["id"] <= 4]
        self.doc_with([{"id": "CP-001", "kind": "false_start", "start_ms": t1[0]["start_ms"] - 20,
                        "end_ms": t1[-1]["end_ms"] + 20, "word_ids": [w["id"] for w in t1], "words": "x",
                        "confidence": 0.9, "reason": "x", "reason_en": "x", "default": "keep"}])
        code, out, err = self.reel("cut-proposals", "--accept", "CP-001")
        self.assertNotEqual(code, 0, out + err)
        self.assertIn("TK-1 / TK-2", out + err)

    def test_a_line_already_gone_does_not_block_an_accept(self):
        self.project(INNER_RETAKE, domain=None)
        self.assertEqual(self.reel("cut-proposals")[0], 0)
        retake = next(p for p in read_json(self.p.p(C.FILE))["proposals"] if p["kind"] == "retake")
        ed = self.ed()
        ed["global"]["cut_words"] = [{"word_ids": list(retake["word_ids"]), "reason": "by hand"},
                                     {"word_ids": list(retake["keep"]["word_ids"]), "reason": "by hand"}]
        write_json(self.p.p("01_analysis/edit-decisions.json"), ed)
        code, out, err = self.reel("cut-proposals", "--accept", retake["id"])
        self.assertEqual(code, 0, out + err)
        self.assertEqual(json.loads(out)["already"], [retake["id"]])

    def test_drop_works_next_to_a_verse(self):
        """The take numbers listed beside a verse are the ones --drop accepts (both read the verse the same way)."""
        self.project(VERSE_TAKES.replace("وبعدين نكمل الكلام ده",
                                         "تمام. الدوا ده مهم. |900 الدوا ده مهم. |900 تمام"))
        code, out, err = self.reel("takes")
        self.assertEqual(code, 0, out + err)
        g = json.loads(out)["groups"]
        self.assertEqual(len(g), 1)
        code, out, err = self.reel("takes", "--drop", str(g[0]["takes"][0]["n"]))
        self.assertEqual(code, 0, out + err)

    def test_spec_verse_reads_every_kind_of_range(self):
        spec = {"manual_verse": [{"src_start_ms": 1, "src_end_ms": 2}],
                "verse_cut": [{"src_start_ms": 3, "src_end_ms": 4}],
                "verse_hold": [{"src_start_ms": 5, "src_end_ms": 6, "released": False},
                               {"src_start_ms": 7, "src_end_ms": 8, "released": True}]}
        self.assertEqual(C.spec_verse(spec), [(1, 2), (3, 4), (5, 6)])
        self.assertEqual(C.spec_verse({}), [])


if __name__ == "__main__":
    unittest.main()
