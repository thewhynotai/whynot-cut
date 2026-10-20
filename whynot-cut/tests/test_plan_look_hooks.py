# SPDX-License-Identifier: GPL-3.0-or-later
# © 2026 The Why Not AI (thewhynot.ai)
"""Task 23 (R-4.1) hooks in the executor's files: `reel plan` writes the clip's words on the sequence clock
(02_transcription/words-seq.json, each word keeping its source times; a stale file goes when there is no time map) and,
with a caption look, adds the looks' fit-or-fail notices; previews.render_captions hands a look to looks_captions
([] passes through as "no captions", None falls back to today's captions). No look = today's output (the golden plan in
test_long_lived stays byte-identical).
Task 28 (R-4.6) hooks: `reel plan` records the reel's caption look once per decision (01_analysis/look-choice.json) and,
with no look, offers the recommender's suggestion without applying it; `reel caption-looks --pick NAME --yes` records
an editor swap; `reel looks recommend` prints the reason line and the top three.
Run:  bash tools/test.sh -k test_plan_look_hooks
"""
import sys as _sys
_sys.dont_write_bytecode = True
import _isolation  # noqa: F401,E402  G79: sandbox the engine home first (tests/_isolation.py)
import contextlib
import io
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SK = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SK / "engine" / "reel"))
sys.path.insert(0, str(SK / "tests"))

from lib import common  # noqa: E402
from lib import lead_steps  # noqa: E402  BL-15: a lead-only step runs with the guard's token
from lib.common import read_json, write_json  # noqa: E402

WORDS_SEQ = "02_transcription/words-seq.json"


class PlanHookCase(unittest.TestCase):
    def setUp(self):
        from test_long_lived import golden_project
        self.tmp = Path(tempfile.mkdtemp(prefix="t23h_"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.root, self.p = golden_project(self.tmp)     # removed pauses (one protected) and word 3 cut
        common.set_context(self.root)
        self.addCleanup(common.set_context, None)

    def compile(self, **glob):
        from lib.plan import compile_plan
        if glob:
            ed = read_json(self.p.p("01_analysis/edit-decisions.json"))
            for k, v in glob.items():
                if v is None:
                    ed["global"].pop(k, None)
                else:
                    ed["global"][k] = v
            write_json(self.p.p("01_analysis/edit-decisions.json"), ed)
        res = compile_plan(self.p)
        self.assertTrue(res["ok"], res["errors"])
        return res


class TestWordsOnTheSequenceClock(PlanHookCase):
    def test_words_seq_keeps_source_times_and_drops_cut_words(self):
        self.compile()
        doc = read_json(self.p.p(WORDS_SEQ))
        words = doc["words"]
        self.assertTrue(words)
        self.assertNotIn(3, [w["id"] for w in words])                 # the cut word never comes back
        src = {w["id"]: w for w in read_json(self.p.p("02_transcription/words.json"))["words"]}
        spec = read_json(self.p.p("01_analysis/timeline-spec.json"))
        from lib.timemap import TimeMap
        tm = TimeMap(spec["time_map"]["keep_ms"])        # the looks' fallback: within a frame of the plan's own map
        frame_ms = 1000 / spec["fps"]
        for w in words:
            self.assertEqual((w["src_start_ms"], w["src_end_ms"]), (src[w["id"]]["start_ms"], src[w["id"]]["end_ms"]))
            self.assertLessEqual(abs(w["start_ms"] - tm.ms(w["src_start_ms"])), frame_ms)
        self.assertEqual([w["start_ms"] for w in words], sorted(w["start_ms"] for w in words))
        late = [w for w in words if w["src_start_ms"] > 4700]
        self.assertTrue(late and all(w["start_ms"] < w["src_start_ms"] for w in late))   # pauses removed before them

    def test_looks_read_the_plans_words(self):
        from lib import looks_captions
        self.compile()
        spec = read_json(self.p.p("01_analysis/timeline-spec.json"))
        self.assertEqual(looks_captions.seq_words(self.p, spec),
                         [w for w in read_json(self.p.p(WORDS_SEQ))["words"] if w["word"].strip()])

    def test_no_time_map_removes_a_stale_file(self):
        self.compile()
        self.assertTrue(self.p.p(WORDS_SEQ).exists())
        self.compile(remove_pauses=None, cut_words=None)
        self.assertIsNone(read_json(self.p.p("01_analysis/timeline-spec.json"))["time_map"])
        self.assertFalse(self.p.p(WORDS_SEQ).exists())

    def test_an_invalid_plan_leaves_the_words_of_the_last_valid_one(self):
        self.compile()
        before = self.p.p(WORDS_SEQ).read_bytes()
        from lib.plan import compile_plan
        ed = read_json(self.p.p("01_analysis/edit-decisions.json"))
        ed["global"].update(cut_words=[], main_footage="data/Raw/NOT_THERE.mov")      # other words, and an error
        write_json(self.p.p("01_analysis/edit-decisions.json"), ed)
        self.assertFalse(compile_plan(self.p)["ok"])
        self.assertEqual(self.p.p(WORDS_SEQ).read_bytes(), before)


class TestFitOrFailNotices(PlanHookCase):
    def test_no_look_reads_no_words_and_adds_nothing(self):
        with mock.patch("lib.looks_captions.plan_check", side_effect=AssertionError("called")), \
                mock.patch("lib.looks_captions.seq_words", side_effect=AssertionError("called")):
            res = self.compile()
        self.assertFalse(any("caption look" in w for w in res["warnings"]))

    def test_a_reel_look_adds_the_notices_with_the_hidden_ranges(self):
        with mock.patch("lib.looks_captions.plan_check", return_value=["NOTICE one"]) as pc:
            res = self.compile(caption_look="line-clean",
                               captions_hidden_ranges=[["00:00:10.000", "00:00:11.000"], ["bad", "x"]])
        self.assertIn("NOTICE one", res["warnings"])
        self.assertIn("NOTICE one", read_json(self.p.p("01_analysis/plan-validation.json"))["warnings"])
        paths, spec, resolved, hidden = pc.call_args.args
        self.assertEqual(resolved["look"], "line-clean")
        self.assertEqual(resolved["source"], "reel")
        hooks = [(e["start_ms"], e["end_ms"]) for e in spec["events"] if e["template"] == "hook_title"]
        self.assertTrue(hooks and all(h in hidden for h in hooks))      # graphics that carry the words
        from lib.timemap import TimeMap
        tm = TimeMap(spec["time_map"]["keep_ms"])
        self.assertIn((tm.ms(10000), tm.ms(11000)), hidden)          # source-time range on the sequence clock

    def test_a_style_file_that_is_not_an_object_keeps_todays_captions(self):
        write_json(self.root / common.CLIENT_PROFILE_REL / "style.json", [1, 2])
        with mock.patch("lib.looks_captions.plan_check", side_effect=AssertionError("called")):
            self.compile()


class TestPreviewsDelegation(PlanHookCase):
    def test_a_look_hands_over_and_an_empty_list_is_no_captions(self):
        self.compile(caption_look="line-clean")
        from lib import previews
        with mock.patch("lib.looks_captions.render_captions", return_value=[]) as rc:
            self.assertEqual(previews.render_captions(self.p, [[0, 100]], avoid=[], warnings=[]), [])
        self.assertEqual(rc.call_args.args[1]["look"], "line-clean")
        self.assertEqual(rc.call_args.args[2], [[0, 100]])

    def test_none_falls_back_to_todays_captions(self):
        self.compile(caption_look="line-clean")
        from lib import previews
        with mock.patch("lib.looks_captions.render_captions", return_value=None):
            caps = previews.render_captions(self.p, [], avoid=[], warnings=[])
        self.assertTrue(caps)
        self.assertTrue(all("look" not in c and Path(c["fg"]).exists() for c in caps))

    def test_no_look_never_asks_the_looks(self):
        self.compile()
        from lib import previews
        with mock.patch("lib.looks_captions.render_captions", side_effect=AssertionError("called")), \
                mock.patch("lib.looks_captions.seq_words", side_effect=AssertionError("called")):
            self.assertTrue(previews.render_captions(self.p, [], avoid=[], warnings=[]))


CHOICE = "01_analysis/look-choice.json"


class TestLookChoice(PlanHookCase):
    def test_a_decided_look_is_recorded_once(self):
        self.compile(caption_look="line-clean")
        first = read_json(self.p.p(CHOICE))["caption"]
        self.assertEqual((first["look"], first["source"]), ("line-clean", "reel"))
        self.compile()                                                 # the same look again: same decision
        self.assertEqual(read_json(self.p.p(CHOICE))["caption"], first)
        write_json(self.p.p(CHOICE), {"caption": dict(first, source="editor")})
        self.compile()
        self.assertEqual(read_json(self.p.p(CHOICE))["caption"]["source"], "editor")   # an editor swap is kept
        self.compile(caption_look="phrase-boxed")
        self.assertEqual(read_json(self.p.p(CHOICE))["caption"]["look"], "phrase-boxed")

    def test_a_client_look_is_recorded_as_the_clients(self):
        write_json(self.root / common.CLIENT_PROFILE_REL / "style.json",
                   {"captions": {"grouping": "line", "presentation": "clean"}})
        self.compile()
        self.assertEqual(read_json(self.p.p(CHOICE))["caption"]["source"], "client")

    def test_no_look_records_nothing_and_only_suggests(self):
        res = self.compile()
        self.assertFalse(self.p.p(CHOICE).exists())
        sug = res.get("caption_look_suggestion")
        self.assertTrue(sug and sug["look"] and sug["reason"])
        self.assertIn(f"reel caption-looks --pick {sug['look']}", sug["how"])
        self.assertFalse((self.root / common.CLIENT_PROFILE_REL / "style.json").exists())   # never applied
        self.assertNotIn(sug["reason"], res["warnings"])                 # not a warning: the golden plan stays

    def test_a_failing_recommender_never_fails_the_plan(self):
        with mock.patch("lib.looks.recommend", side_effect=RuntimeError("boom")):
            res = self.compile()
        self.assertNotIn("caption_look_suggestion", res)

    def test_a_reel_look_gets_no_suggestion(self):
        with mock.patch("lib.looks.recommend", side_effect=AssertionError("called")):
            res = self.compile(caption_look="line-clean")
        self.assertNotIn("caption_look_suggestion", res)


class TestLookVerbs(PlanHookCase):
    def reel(self, *argv):
        import cli
        so, se = io.StringIO(), io.StringIO()
        code = 0
        lead_steps.issue_for(["--root", str(self.root), "--video-id", "CLIP1", *argv])    # BL-15: the lead's token
        with contextlib.redirect_stdout(so), contextlib.redirect_stderr(se):
            try:
                cli.main(["--root", str(self.root), "--video-id", "CLIP1", *argv])
            except SystemExit as e:
                code = e.code if isinstance(e.code, int) else 1
        return code, so.getvalue(), se.getvalue()

    def test_pick_with_yes_records_an_editor_swap(self):
        code, out, err = self.reel("caption-looks", "--pick", "line-clean")
        self.assertEqual(code, 0, (out, err))
        self.assertTrue(json.loads(out)["diff"])
        self.assertFalse(self.p.p(CHOICE).exists())                    # a diff only
        code, out, err = self.reel("caption-looks", "--pick", "line-clean", "--yes")
        self.assertEqual(code, 0, (out, err))
        self.assertTrue(json.loads(out)["written"])
        ch = read_json(self.p.p(CHOICE))["caption"]
        self.assertEqual((ch["look"], ch["source"]), ("line-clean", "editor"))

    def test_recommend_prints_the_reason_and_the_top_three(self):
        code, out, err = self.reel("looks", "recommend", "--no-stills", "--lang", "en")
        self.assertEqual(code, 0, (out, err))
        lines = out.strip().splitlines()
        self.assertTrue(lines[0].strip())
        self.assertEqual([ln[:3] for ln in lines[1:4]], ["1. ", "2. ", "3. "])
        self.assertIn("reel caption-looks --pick", lines[-1])
        code, out, err = self.reel("looks", "recommend", "--no-stills", "--json")
        self.assertEqual(code, 0, (out, err))
        doc = json.loads(out)
        self.assertEqual(doc["kind"], "caption")
        self.assertEqual(len(doc["top"]), 3)
        self.assertFalse(self.p.p(CHOICE).exists())                    # it only suggests


if __name__ == "__main__":
    unittest.main()
