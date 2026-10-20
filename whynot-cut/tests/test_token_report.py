# SPDX-License-Identifier: GPL-3.0-or-later
# © 2026 The Why Not AI (thewhynot.ai)
"""Addendum M, M5-T1: `tools/token_report.py`, tokens per stage and per video from Claude Code transcripts.

Spec: docs/superpowers/specs/addendum-m/ADDENDUM-M-owner-requests-2026-10-16.md (M5.2, M5.3, M5.5 M5-T1).
Fixtures: tests/fixtures/token_report/ (synthetic JSONL with the real key names, built by make_fixtures.py; no real
transcript content). Expected numbers are hand-calculated in the comments, never recomputed with the tool's formula.
Prices: the published table (lead claude-opus-5-5: input $4, 5m write $5, 1h write $8, read $0.20, output $20 per
MTok -> relative 1 / 1.25 / 2 / 0.05 / 5).
Run:  tools/test.sh -p test_token_report.py
"""
import sys as _sys
_sys.dont_write_bytecode = True  # keep the plugin folder free of __pycache__
import _isolation  # noqa: F401,E402  G79: sandbox the engine home before anything else (see tests/_isolation.py)
import importlib.util
import io
import json
import os
import shutil
import sys
import tempfile
import tracemalloc
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
FIX = Path(__file__).resolve().parent / "fixtures" / "token_report"
sys.path.insert(0, str(ROOT / "tools"))

import token_report as tr  # noqa: E402


def _load_fixture_builder():
    spec = importlib.util.spec_from_file_location("wnc_token_report_fixtures", FIX / "make_fixtures.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


MF = _load_fixture_builder()
PROJ = FIX / MF.PROJECT_DIR
DATE = "2026-10-18"


def report(paths, **kw):
    kw.setdefault("date", DATE)
    kw.setdefault("commit", "0" * 40)
    return tr.build_report([Path(p) for p in paths], **kw)


def u(fresh=0, w5=0, w1=0, read=0, out=0, speed="standard", split=True):
    return MF.usage(fresh=fresh, w5=w5, w1=w1, read=read, out=out, speed=speed, split=split)


def rec(mid, usage, content=None, model="claude-opus-5-5", **kw):
    return MF.asst(MF.Seq("t"), "sx", mid, usage, content, model=model, **kw)


def dir_link(link: Path, target: Path) -> None:
    """A directory junction on Windows (no shell: _winapi.CreateJunction), a symlink elsewhere."""
    if os.name == "nt":
        import _winapi
        _winapi.CreateJunction(str(target), str(link))
    else:
        os.symlink(target, link, target_is_directory=True)


class TmpProject(unittest.TestCase):
    """A temp project folder; files are written with write(name, records)."""
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.proj = self.tmp / "D--tmp-proj"
        self.proj.mkdir()

    def write(self, rel, records, raw_lines=None):
        f = self.proj / rel
        f.parent.mkdir(parents=True, exist_ok=True)
        with open(f, "w", encoding="utf-8", newline="\n") as fh:
            for r in records:
                fh.write(json.dumps(r) + "\n")
            for line in raw_lines or []:
                fh.write(line + "\n")
        return f


# ---------------------------------------------------------------------------------------------------------------- A
class TestParsingAndDedupe(TmpProject):
    def test_a1_streamed_records_of_one_id_count_once(self):
        """Case 1: one id on 5 records with identical usage -> counted once."""
        self.write("s.jsonl", [rec("m", u(fresh=1000, w5=2000, out=100)) for _ in range(5)])
        r = report([self.proj])
        self.assertEqual(r["totals"]["raw"], {"fresh": 1000, "write_5m": 2000, "write_1h": 0, "read": 0, "output": 100})
        self.assertEqual(r["totals"]["messages"], 1)
        self.assertEqual(r["totals"]["weighted"], 4000.0)          # 1000 + 2000*1.25 + 100*5

    def test_a2_all_zero_tail_record_keeps_the_real_usage(self):
        """Case 2: a later all-zero record of the same id never zeroes the message."""
        self.write("s.jsonl", [rec("m", u(fresh=10, read=3000, out=200)), rec("m", u())])
        r = report([self.proj])
        self.assertEqual(r["totals"]["raw"]["output"], 200)
        self.assertEqual(r["totals"]["raw"]["read"], 3000)

    def test_a2b_progressive_output_keeps_the_last_record(self):
        """Streaming writes growing output_tokens under one id (seen on this PC): the last non-zero record wins."""
        self.write("s.jsonl", [rec("m", u(fresh=10, out=50)), rec("m", u(fresh=10, out=200)), rec("m", u())])
        r = report([self.proj])
        self.assertEqual(r["totals"]["raw"]["output"], 200)
        self.assertEqual(r["totals"]["raw"]["fresh"], 10)

    def test_a2c_a_stale_replay_never_undercounts_whatever_the_file_order(self):
        """Review P3-1: a later-sorting file holding a stale copy (out=50) of an id whose final record is out=200.
        Session file names are random, so the result must not depend on which file sorts first."""
        for stale_name in ("zz-replay.jsonl", "00-replay.jsonl"):
            with self.subTest(stale_name=stale_name):
                shutil.rmtree(self.proj)
                self.proj.mkdir()
                self.write("m-main.jsonl", [rec("m", u(fresh=10, read=100, out=50)),
                                            rec("m", u(fresh=10, read=100, out=200))])
                self.write(stale_name, [rec("m", u(fresh=10, read=100, out=50))])
                r = report([self.proj])
                self.assertEqual(r["totals"]["raw"]["output"], 200)
                self.assertEqual(r["totals"]["messages"], 1)

    def test_a2d_the_rule_is_the_record_with_the_most_tokens(self):
        """Review P3-1 pins the rule: per id the record with the largest token total wins (ties by output, then
        read, 1h write, 5m write, fresh), in any order. Not "last non-zero", not "largest output"."""
        big = u(fresh=1, read=1000, out=10)       # total 1011
        late = u(fresh=1, read=0, out=50)         # total 51, larger output, written later
        for order in ((big, late), (late, big)):
            with self.subTest(order=[x["output_tokens"] for x in order]):
                self.write("s.jsonl", [rec("m", order[0]), rec("m", order[1])])
                r = report([self.proj])
                self.assertEqual(r["totals"]["raw"], {"fresh": 1, "write_5m": 0, "write_1h": 0, "read": 1000,
                                                      "output": 10})
        tie_a, tie_b = u(fresh=5, out=10), u(fresh=10, out=5)            # same total: the larger output wins
        for order in ((tie_a, tie_b), (tie_b, tie_a)):
            self.write("s.jsonl", [rec("m", order[0]), rec("m", order[1])])
            self.assertEqual(report([self.proj])["totals"]["raw"]["output"], 10)
        tie_c, tie_d = u(read=7, w1=3), u(read=3, w1=7)                  # then read, then the 1h write
        for order in ((tie_c, tie_d), (tie_d, tie_c)):
            self.write("s.jsonl", [rec("m", order[0]), rec("m", order[1])])
            self.assertEqual(report([self.proj])["totals"]["raw"]["read"], 7)
        tie_e, tie_f = u(w1=4, w5=1), u(w1=1, w5=4)
        for order in ((tie_e, tie_f), (tie_f, tie_e)):
            self.write("s.jsonl", [rec("m", order[0]), rec("m", order[1])])
            self.assertEqual(report([self.proj])["totals"]["raw"]["write_1h"], 4)
        tie_g, tie_h = u(w5=4, fresh=1), u(w5=1, fresh=4)
        for order in ((tie_g, tie_h), (tie_h, tie_g)):
            self.write("s.jsonl", [rec("m", order[0]), rec("m", order[1])])
            self.assertEqual(report([self.proj])["totals"]["raw"]["write_5m"], 4)
        tie_i, tie_j = u(out=10, read=5), u(out=5, read=10)                 # output before read (mutant N08)
        for order in ((tie_i, tie_j), (tie_j, tie_i)):
            self.write("s.jsonl", [rec("m", order[0]), rec("m", order[1])])
            self.assertEqual(report([self.proj])["totals"]["raw"]["output"], 10)

    def test_a2e_full_ties_are_order_independent_too(self):
        """Mutant N06: equal counts. The record carrying the 5m/1h split wins over one without it, then the larger
        model key; so even a full tie gives one answer in any order."""
        split, nosplit = u(w5=100, out=1), u(w5=100, out=1, split=False)
        for order in ((split, nosplit), (nosplit, split)):
            self.write("s.jsonl", [rec("m", order[0]), rec("m", order[1])])
            r = report([self.proj])
            self.assertFalse(any("5-minute" in a for a in r["assumptions"]), r["assumptions"])
        for order in (("claude-opus-5-5", "claude-sonnet-5-5"), ("claude-sonnet-5-5", "claude-opus-5-5")):
            self.write("s.jsonl", [rec("m", u(fresh=4), model=order[0]), rec("m", u(fresh=4), model=order[1]),
                                   rec("x", u(fresh=1)), rec("y", u(fresh=1))])
            self.assertIn("claude-sonnet-5-5", report([self.proj])["by_model"])

    def test_a3_resumed_session_replay_counts_once_across_files(self):
        """Case 3: the same id in the main file and in a resumed session file -> once across the report."""
        self.write("s1.jsonl", [rec("m", u(fresh=7, out=3))])
        self.write("s2.jsonl", [rec("m", u(fresh=7, out=3)), rec("n", u(fresh=1))])
        r = report([self.proj])
        self.assertEqual(r["totals"]["raw"]["fresh"], 8)
        self.assertEqual(r["totals"]["messages"], 2)

    def test_a3b_a_replay_keeps_the_stage_of_its_first_file(self):
        """Mutant M07: a resumed session replays a message before any reel command of its own; the message keeps
        the stage and video it had where it was first seen."""
        self.write("s1.jsonl", [rec("a", u(fresh=1), [MF.bash("reel qc --video-id A_1", "t")]), rec("b", u(fresh=5))])
        self.write("s2.jsonl", [rec("b", u(fresh=5)), rec("c", u(fresh=7))])
        r = report([self.proj], raw_ids=True)
        self.assertEqual(r["by_item"]["A_1"]["by_stage"]["qc"]["raw"]["fresh"], 6)
        self.assertEqual(r["by_stage"]["setup"]["raw"]["fresh"], 7)

    def test_a4_malformed_line_is_skipped_with_its_line_and_the_report_is_partial(self):
        """Case 4: a malformed line -> skipped [{file, line}], the rest counted, partial: true."""
        f = self.write("s.jsonl", [rec("a", u(fresh=5))], raw_lines=['{"type": "assistant", "message": {',
                                                                        json.dumps(rec("b", u(fresh=6)))])
        r = report([self.proj])
        self.assertTrue(r["partial"])
        self.assertEqual(r["skipped"], [{"file": f.name, "line": 2}])
        self.assertEqual(r["totals"]["raw"]["fresh"], 11)

    def test_a4d_a_deeply_nested_line_is_skipped_not_a_crash(self):
        """Review P3-4: 200,000 `[` raise RecursionError in json; the line is skipped, the report still comes."""
        f = self.write("s.jsonl", [rec("a", u(fresh=5))], raw_lines=["[" * 200_000, json.dumps(rec("b", u(fresh=6)))])
        r = report([self.proj])
        self.assertEqual(r["skipped"], [{"file": f.name, "line": 2}])
        self.assertTrue(r["partial"])
        self.assertEqual(r["totals"]["raw"]["fresh"], 11)

    def test_a4b_clean_input_is_not_partial(self):
        self.write("s.jsonl", [rec("a", u(fresh=5))])
        r = report([self.proj])
        self.assertFalse(r["partial"])
        self.assertEqual(r["skipped"], [])

    def test_a4c_blank_lines_and_non_object_json_are_not_errors(self):
        self.write("s.jsonl", [rec("a", u(fresh=5))], raw_lines=["", "   ", "[1, 2]", "42"])
        r = report([self.proj])
        self.assertFalse(r["partial"])
        self.assertEqual(r["totals"]["raw"]["fresh"], 5)

    def test_a5_non_assistant_records_are_ignored(self):
        """Case 5: user, attachment, system, file-history, queue, title and cost-state records carry no usage."""
        seq = MF.Seq("n")
        recs = MF.noise(seq, "sx") + [MF.user(seq, "sx", "hi"), rec("a", u(fresh=5))]
        recs.append({"type": "user", "message": {"role": "user", "content": "x", "usage": {"input_tokens": 999}},
                     "toolUseResult": {"usage": {"input_tokens": 5000, "output_tokens": 5000}}})
        self.write("s.jsonl", recs)
        r = report([self.proj])
        self.assertEqual(r["totals"]["raw"], {"fresh": 5, "write_5m": 0, "write_1h": 0, "read": 0, "output": 0})
        self.assertEqual(r["totals"]["messages"], 1)

    def test_a5b_assistant_record_without_usage_is_ignored(self):
        self.write("s.jsonl", [{"type": "assistant", "message": {"id": "q", "model": "claude-opus-5-5"}},
                               {"type": "assistant", "message": "not a dict"}, rec("a", u(fresh=5))])
        r = report([self.proj])
        self.assertEqual(r["totals"]["messages"], 1)

    def test_a6_api_error_records_are_reported_apart(self):
        """Case 6: isApiErrorMessage records go to `errors`, never into stage totals."""
        self.write("s.jsonl", [rec("a", u(fresh=5)), rec("e", u(fresh=3, out=7), error=True)])
        r = report([self.proj])
        self.assertEqual(r["errors"]["count"], 1)
        self.assertEqual(r["errors"]["raw"]["output"], 7)
        self.assertEqual(r["errors"]["raw"]["fresh"], 3)
        self.assertEqual(r["totals"]["raw"]["output"], 0)
        self.assertEqual(sum(s["raw"]["output"] for s in r["by_stage"].values()), 0)
        self.assertNotIn("<synthetic>", r["by_model"])

    def test_a6b_error_flag_on_any_record_of_the_id_marks_the_message(self):
        e = rec("e", u(fresh=3), error=True)
        e["message"]["model"] = "claude-opus-5-5"
        self.write("s.jsonl", [rec("e", u(fresh=3)), e])
        r = report([self.proj])
        self.assertEqual(r["errors"]["count"], 1)
        self.assertEqual(r["totals"]["messages"], 0)

    def test_a7_message_without_id_counts_once_per_record(self):
        a = rec("x", u(fresh=4))
        del a["message"]["id"]
        self.write("s.jsonl", [a, a])
        r = report([self.proj])
        self.assertEqual(r["totals"]["raw"]["fresh"], 8)


# ---------------------------------------------------------------------------------------------------------------- B
class TestSubagents(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.r = report([PROJ], raw_ids=True)

    def test_b7_subagent_usage_goes_to_the_spawn_stage(self):
        """Case 7: agent-aa11 (toolUseId toolu_A1, spawned during previews of EP02_C0238).
        aa11 on claude-sonnet-5-5 (relative 0.5 / 0.625 / 1 / 0.025 / 2.5):
          a1 = 100*0.5 + 1000*0.625 + 500*2.5 = 1925;  a2 = 10*0.5 + 2000*0.025 + 100*2.5 = 305."""
        prev = self.r["by_stage"]["previews"]
        # previews = m2 3160 + m3 1830 + aa11 2230 + bb22 350
        self.assertAlmostEqual(prev["weighted"], 7570.0, places=6)
        self.assertEqual(prev["messages"], 5)

    def test_b8_subagent_without_meta_is_unattributed_but_counted(self):
        """Case 8: agent-cc33 has no meta.json -> unattributed-subagent (10*0.5 + 10*2.5 = 30), still in totals."""
        un = self.r["by_stage"]["unattributed-subagent"]
        self.assertAlmostEqual(un["weighted"], 30.0, places=6)
        self.assertEqual(self.r["subagents"]["unattributed_messages"], 1)
        self.assertAlmostEqual(self.r["totals"]["weighted"], 17503.0, places=6)

    def test_b8b_unknown_tool_use_id_is_unattributed(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "proj"
            (p / "s" / "subagents").mkdir(parents=True)
            (p / "s.jsonl").write_text(json.dumps(rec("m", u(fresh=1))) + "\n", encoding="utf-8")
            (p / "s" / "subagents" / "agent-zz.jsonl").write_text(
                json.dumps(rec("z", u(fresh=9), sidechain=True)) + "\n", encoding="utf-8")
            (p / "s" / "subagents" / "agent-zz.meta.json").write_text('{"toolUseId": "toolu_nowhere"}',
                                                                        encoding="utf-8")
            r = report([p])
        self.assertEqual(r["by_stage"]["unattributed-subagent"]["raw"]["fresh"], 9)

    def test_b8c_unreadable_meta_is_unattributed(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "proj"
            (p / "s" / "subagents").mkdir(parents=True)
            (p / "s.jsonl").write_text(json.dumps(rec("m", u(fresh=1), [MF.agent("toolu_Q")])) + "\n",
                                       encoding="utf-8")
            (p / "s" / "subagents" / "agent-zz.jsonl").write_text(
                json.dumps(rec("z", u(fresh=9), sidechain=True)) + "\n", encoding="utf-8")
            (p / "s" / "subagents" / "agent-zz.meta.json").write_text('{"toolUseId": "toolu_Q"', encoding="utf-8")
            r = report([p])
        self.assertEqual(r["by_stage"]["unattributed-subagent"]["raw"]["fresh"], 9)

    def test_b9_nested_subagent_rolls_up_to_the_top_level_spawn(self):
        """Case 9: agent-bb22 (spawnDepth 2, spawned by aa11's toolu_B2) -> previews / EP02_C0238.
        bb22 on claude-haiku-4-5 (relative 0.25 / ... / 1.25): 400*0.25 + 200*1.25 = 350."""
        item = self.r["by_item"]["EP02_C0238"]["by_stage"]["previews"]
        self.assertAlmostEqual(item["weighted"], 7570.0, places=6)
        self.assertNotIn("EP77_C7777", self.r["by_item"])     # a reel command inside a subagent moves nothing

    def test_b9b_spawn_cycle_does_not_hang(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "proj"
            sub = p / "s" / "subagents"
            sub.mkdir(parents=True)
            (p / "s.jsonl").write_text(json.dumps(rec("m", u(fresh=1))) + "\n", encoding="utf-8")
            (sub / "agent-x.jsonl").write_text(json.dumps(rec("x", u(fresh=2), [MF.agent("toolu_Y")],
                                                               sidechain=True)) + "\n", encoding="utf-8")
            (sub / "agent-x.meta.json").write_text('{"toolUseId": "toolu_X"}', encoding="utf-8")
            (sub / "agent-y.jsonl").write_text(json.dumps(rec("y", u(fresh=3), [MF.agent("toolu_X")],
                                                               sidechain=True)) + "\n", encoding="utf-8")
            (sub / "agent-y.meta.json").write_text('{"toolUseId": "toolu_Y"}', encoding="utf-8")
            r = report([p])
        self.assertEqual(r["by_stage"]["unattributed-subagent"]["raw"]["fresh"], 5)

    def test_b10_infile_sidechain_layout_parses_like_the_folder_layout(self):
        """Case 10: twin fixtures (folder layout vs older in-file isSidechain layout) give the same totals,
        stages, items and model mix."""
        a = report([FIX / "twin_folder"], raw_ids=True)
        b = report([FIX / "twin_infile"], raw_ids=True)
        for k in ("totals", "by_stage", "by_item", "by_model", "errors"):
            self.assertEqual(a[k], b[k], k)
        # m1..m9 of the twin, no cc33: 17503 - 30 (cc33) - 200 (no m10 resumed session) - weighted of nothing else
        self.assertAlmostEqual(a["totals"]["weighted"], 17273.0, places=6)

    def test_b10b_sidechain_records_never_count_as_lead_turns(self):
        a = report([FIX / "twin_folder"])
        b = report([FIX / "twin_infile"])
        self.assertEqual(a["lead_context"], b["lead_context"])
        self.assertEqual(a["lead_context"]["turns"], 8)

    def test_b11_stream_json_parent_tool_use_id_is_a_subagent_record(self):
        """`claude -p --output-format stream-json` traces mark subagent messages with parent_tool_use_id."""
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "run"
            p.mkdir()
            spawn = rec("m", u(fresh=1), [MF.bash("reel qc --video-id EP05_C0005", "t1"), MF.agent("toolu_S")])
            child = rec("c", u(fresh=40))
            child["parent_tool_use_id"] = "toolu_S"
            orphan = rec("o", u(fresh=2))
            orphan["parent_tool_use_id"] = "toolu_missing"
            (p / "trace.jsonl").write_text("".join(json.dumps(x) + "\n" for x in (spawn, child, orphan)),
                                           encoding="utf-8")
            r = report([p], raw_ids=True)
        self.assertEqual(r["by_item"]["EP05_C0005"]["by_stage"]["qc"]["raw"]["fresh"], 41)
        self.assertEqual(r["by_stage"]["unattributed-subagent"]["raw"]["fresh"], 2)
        self.assertEqual(r["lead_context"]["turns"], 1)

    def test_b11b_older_task_tool_name_is_a_spawn(self):
        """Mutant M57: older Claude Code versions named the subagent tool `Task`."""
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "proj"
            (p / "s" / "subagents").mkdir(parents=True)
            spawn = rec("m", u(fresh=1), [MF.bash("reel plan --video-id A_1", "t1"),
                                          {"type": "tool_use", "id": "toolu_T", "name": "Task", "input": {}}])
            (p / "s.jsonl").write_text(json.dumps(spawn) + "\n", encoding="utf-8")
            (p / "s" / "subagents" / "agent-t.jsonl").write_text(
                json.dumps(rec("t", u(fresh=60), sidechain=True)) + "\n", encoding="utf-8")
            (p / "s" / "subagents" / "agent-t.meta.json").write_text('{"toolUseId": "toolu_T"}', encoding="utf-8")
            r = report([p], raw_ids=True)
        self.assertEqual(r["by_item"]["A_1"]["by_stage"]["plan"]["raw"]["fresh"], 61)
        self.assertNotIn("unattributed-subagent", r["by_stage"])

    def test_b11c_a_single_main_file_brings_its_subagents(self):
        """Mutant M84: a .jsonl argument also reads <session>/subagents/ (17503 without m10 = 17303)."""
        r = report([PROJ / "s1.jsonl"])
        self.assertAlmostEqual(r["totals"]["weighted"], 17303.0, places=6)
        self.assertEqual(r["subagents"]["messages"], 4)

    def test_b12_subagent_share(self):
        """Subagents: aa11 2230 + bb22 350 + cc33 30 = 2610 of 17503 weighted."""
        self.assertAlmostEqual(self.r["subagents"]["share_weighted"], 2610 / 17503, places=9)
        self.assertEqual(self.r["subagents"]["messages"], 4)


# ---------------------------------------------------------------------------------------------------------------- C
class TestStageMarkers(unittest.TestCase):
    """Command lines are written the way the skills write them: the video id is always `--video-id` (or `--episode`);
    the reel CLI has no positional video id (review efe8910 P2-1)."""
    def m(self, cmd, shell="bash"):
        return tr.reel_markers(cmd, shell)

    def p(self, cmd):
        return tr.reel_markers(cmd, "powershell")

    def test_c11_the_invocation_forms(self):
        """Case 11, on real CLI shapes."""
        self.assertEqual(self.m("reel previews --video-id EP02_C0238"), [("previews", "EP02_C0238")])
        self.assertEqual(self.m('bash "$CLAUDE_PLUGIN_ROOT/bin/run_python.sh" -s engine/x reel plan --video-id X_1'),
                         [("plan", "X_1")])
        self.assertEqual(self.m("python -m reel.cli qc --video-id EP03_C0101"), [("qc", "EP03_C0101")])
        self.assertEqual(self.m("python -m reel qc --video-id EP03_C0101"), [("qc", "EP03_C0101")])
        self.assertEqual(self.m("reel.cmd ppro-build --video-id EP02_C0238"), [("ppro-build", "EP02_C0238")])

    def test_c11b_paths_launchers_and_env(self):
        self.assertEqual(self.p('& "C:\\Users\\a b\\.whynot-cut\\bin\\reel.cmd" qc --video-id C0239'),
                         [("qc", "C0239")])
        self.assertEqual(self.m("/Users/x/.whynot-cut/bin/reel previews --video-id C0239"), [("previews", "C0239")])
        self.assertEqual(self.m("WHYNOT_ACCEL=off FOO=1 reel audio-clean --video-id C0239"),
                         [("audio-clean", "C0239")])
        self.assertEqual(self.m("python3.12 -B -m reel.cli plan --video-id C0239"), [("plan", "C0239")])
        self.assertEqual(self.m("timeout 600 reel ppro-build --video-id C0239"), [("ppro-build", "C0239")])
        self.assertEqual(self.m("py engine/reel/cli.py motion-plan --video-id EP1_C2_MO"),
                         [("motion-plan", "EP1_C2_MO")])
        self.assertEqual(self.m("bash -c 'reel qc --video-id C0239'"), [("qc", "C0239")])
        self.assertEqual(self.m("cmd /c reel.bat qc --video-id C0239"), [("qc", "C0239")])
        self.assertEqual(self.m("REEL.CMD QC --video-id C0239"), [])                  # verbs are lower case

    def test_c11f_engine_script_forms_the_guard_treats_as_reel_runs(self):
        """Review P3-2 (hooks/guard.py reel_args): interpreter options with values, `-m reel.cli`, `-m cli` and
        `cli.py` from engine/reel, and an interpreter held in a variable."""
        self.assertEqual(self.m("python -X utf8 -W ignore engine/reel/cli.py plan --video-id C0239"),
                         [("plan", "C0239")])
        self.assertEqual(self.m('$PY "D:/x/engine/reel/cli.py" plan --video-id C0239'), [("plan", "C0239")])
        self.assertEqual(self.m('"${PY}" engine/reel/cli.py qc --video-id C0239'), [("qc", "C0239")])
        self.assertEqual(self.p('& $py "D:\\x\\engine\\reel\\cli.py" qc --video-id C0239'), [("qc", "C0239")])
        self.assertEqual(self.m("cd engine/reel && python cli.py plan --video-id C0239"), [("plan", "C0239")])
        self.assertEqual(self.m("cd whynot-cut/engine/reel; python -m cli qc --video-id C0239"), [("qc", "C0239")])
        self.assertEqual(self.m("python cli.py plan --video-id C0239"), [])          # not in engine/reel
        self.assertEqual(self.m("python -m cli plan --video-id C0239"), [])
        self.assertEqual(self.m("cd engine/other && python cli.py plan --video-id C0239"), [])
        self.assertEqual(self.m("python -c 'import reel' plan"), [])
        self.assertEqual(self.m("$EDITOR notes.md"), [])
        self.assertEqual(self.m("echo ${HOME} reel plan --video-id A_1"), [])                   # N18
        self.assertEqual(self.m('python -c "reel plan --video-id A_1"'), [])                   # N25

    def test_c11c_video_only_from_video_id_or_episode(self):
        """Review P2-1: option values and positional words are never a video."""
        self.assertEqual(self.m('reel --root "D:\\Fixture Clients\\Zorblax Quentaro" plan --video-id c0239'),
                         [("plan", "C0239")])
        self.assertEqual(self.m("reel model-download --model large-v3"), [("model-download", None)])
        self.assertEqual(self.m("reel transcribe --model large-v3"), [("transcribe", None)])
        self.assertEqual(self.m("reel range --in 02:04 --out 10 --snap"), [("range", None)])
        self.assertEqual(self.m("reel perf-report --since 2026-10-18"), [("perf-report", None)])
        self.assertEqual(self.m("reel plan EP02_C0238"), [("plan", None)])              # no positional id
        self.assertEqual(self.m("reel caption-looks --video-id C0239 --pick look_2"), [("caption-looks", "C0239")])
        self.assertEqual(self.m("reel transcribe --root X --video-id EP02_C0238 data/Raw/x.mp4"),
                         [("transcribe", "EP02_C0238")])
        self.assertEqual(self.m("reel next --video-id=EP02_C0238"), [("next", "EP02_C0238")])
        self.assertEqual(self.m("reel reels-plan --episode EP02"), [("reels-plan", "EP02")])
        self.assertEqual(self.m("reel --episode EP02 qc --video-id C0239"), [("qc", "C0239")])
        self.assertEqual(self.m("reel --video-id A_1 plan --episode EP02"), [("plan", "A_1")])
        self.assertEqual(self.m("reel --profile p1 doctor"), [("doctor", None)])
        self.assertEqual(self.m("reel plan --video-id EP02_C0238 --from 3"), [("plan", "EP02_C0238")])
        self.assertEqual(self.m("reel --json plan --video-id EP02_C0238"), [("plan", "EP02_C0238")])
        self.assertEqual(self.m("reel plan --video-id 'bad/id'"), [("plan", None)])
        self.assertEqual(self.m("reel plan 2>&1"), [("plan", None)])
        self.assertEqual(self.m("reel 2>&1 plan --video-id A_1"), [("plan", "A_1")])   # fd number is no word
        self.assertEqual(self.m("reel plan --video-id EP02_C0238 > out_1.txt"), [("plan", "EP02_C0238")])
        self.assertEqual(self.m("reel > out-log plan --video-id A_1"), [("plan", "A_1")])  # redirect target skipped
        self.assertEqual(self.m("reel --version"), [])
        self.assertEqual(self.m("reel --root"), [])

    def test_c11d_several_commands_in_one_line(self):
        self.assertEqual(self.m("reel qc --video-id A_1 && reel ppro-build --video-id B_2; echo done | tee x"),
                         [("qc", "A_1"), ("ppro-build", "B_2")])
        self.assertEqual(self.m("cd 'D:/x' && reel plan --video-id A_1 || reel doctor"),
                         [("plan", "A_1"), ("doctor", None)])
        self.assertEqual(self.m("reel qc --video-id A_1 &\nreel plan --video-id B_2"), [("qc", "A_1"), ("plan", "B_2")])
        self.assertEqual(self.m("(reel qc --video-id A_1)"), [("qc", "A_1")])

    def test_c11g_compound_commands(self):
        """Review P3-2: if/then, loops, brace groups, `!`, and PowerShell's `; if ($?) { ... }` chaining."""
        self.assertEqual(self.m("if reel qc --video-id A_1; then reel plan --video-id B_2; else reel doctor; fi"),
                         [("qc", "A_1"), ("plan", "B_2"), ("doctor", None)])
        self.assertEqual(self.m("for f in a b; do reel qc --video-id A_1; done"), [("qc", "A_1")])
        self.assertEqual(self.m("while true; do reel next; done"), [("next", None)])
        self.assertEqual(self.m("{ reel qc --video-id A_1; }"), [("qc", "A_1")])
        self.assertEqual(self.m("! reel qc --video-id A_1"), [("qc", "A_1")])
        self.assertEqual(self.m("${ROOT}/bin/reel plan --video-id A_1"), [("plan", "A_1")])
        self.assertEqual(self.p("reel qc --video-id A_1; if ($?) { reel plan --video-id B_2 }"),
                         [("qc", "A_1"), ("plan", "B_2")])
        self.assertEqual(self.m("reel qc --video-id A_1; if ($?) { reel plan --video-id B_2 }"),
                         [("qc", "A_1"), ("plan", "B_2")])

    def test_c11h_powershell_quoting(self):
        """Review P3-2: PowerShell has no backslash escape, uses the backtick, and has here-strings and <# #>."""
        self.assertEqual(self.p('Write-Host "C:\\dir\\" ; reel plan --video-id B_2'), [("plan", "B_2")])
        self.assertEqual(self.p("$t = @'\nit's\nreel plan --video-id B_2\n'@\nreel qc --video-id A_1"),
                         [("qc", "A_1")])
        self.assertEqual(self.p('$t = @"\nsay "hi"\nreel plan --video-id B_2\n"@; reel qc --video-id A_1'),
                         [("qc", "A_1")])
        self.assertEqual(self.p('Write-Host "a `" b" ; reel qc --video-id A_1'), [("qc", "A_1")])
        self.assertEqual(self.p("Write-Host a`;b; reel qc --video-id A_1"), [("qc", "A_1")])
        self.assertEqual(self.p("<# reel plan --video-id B_2 #> reel qc --video-id A_1"), [("qc", "A_1")])
        self.assertEqual(self.p("<# open comment reel plan --video-id B_2"), [])
        self.assertEqual(self.p("$t = @'\nreel plan --video-id B_2"), [])                   # unterminated
        self.assertEqual(self.p("# reel plan --video-id B_2\nreel qc --video-id A_1"), [("qc", "A_1")])
        self.assertEqual(self.m('echo "C:\\dir\\" ; reel plan --video-id B_2'), [])       # bash: \" is a quote
        self.assertEqual(tr.reel_markers("reel qc --video-id A_1", "fish"), [("qc", "A_1")])  # unknown -> bash
        self.assertEqual(self.p("Get-ChildItem C:\\dir\\; reel plan --video-id B_2"), [("plan", "B_2")])  # N11
        self.assertEqual(self.p("Write-Host 'a''' ; reel qc --video-id A_1"), [("qc", "A_1")])            # N15
        self.assertEqual(self.p("reel qc --video-id 'A''B'"), [("qc", None)])        # N15: A'B is not an id
        self.assertEqual(self.m("pwsh -Command 'Write-Host \"C:\\dir\\\" ; reel plan --video-id B_2'"),
                         [("plan", "B_2")])                                                               # N26

    def test_c13_heredoc_echo_comment_and_quotes_are_not_markers(self):
        """Case 13: only the command position counts."""
        self.assertEqual(self.m(MF.HEREDOC), [])
        self.assertEqual(self.m("echo reel plan --video-id A_1"), [])
        self.assertEqual(self.m('grep -n "reel plan" notes.md'), [])
        self.assertEqual(self.m("# reel plan --video-id A_1"), [])
        self.assertEqual(self.m("ls  # reel plan --video-id A_1"), [])
        self.assertEqual(self.m("reel qc --video-id A_1 # ; reel plan --video-id B_2"), [("qc", "A_1")])
        self.assertEqual(self.m("echo a#b; reel qc --video-id A_1"), [("qc", "A_1")])
        self.assertEqual(self.m("cat <<-EOF\n\treel plan --video-id A_1\n\tEOF\nreel qc --video-id B_2"),
                         [("qc", "B_2")])
        self.assertEqual(self.m('cat <<"END" | wc\nreel plan --video-id A_1\nEND'), [])
        self.assertEqual(self.m("git commit -m 'reel plan --video-id A_1'"), [])
        self.assertEqual(self.m("python tools/x.py reel plan --video-id A_1"), [])
        self.assertEqual(self.m("reelx plan --video-id A_1"), [])
        self.assertEqual(self.m("cat reel"), [])
        self.assertEqual(self.m("unterminated 'reel plan --video-id A_1"), [])

    def test_c13b_escapes_and_line_continuation(self):
        self.assertEqual(self.m("reel \\\n  qc --video-id A_1"), [("qc", "A_1")])
        self.assertEqual(self.m('reel qc --video-id "A_1"'), [("qc", "A_1")])
        self.assertEqual(self.m("echo \\; reel qc --video-id A_1"), [])
        self.assertEqual(self.m('echo "a \\" b" ; reel qc --video-id A_1'), [("qc", "A_1")])

    def test_c13c_odd_inputs(self):
        self.assertEqual(self.m(""), [])
        self.assertEqual(self.m(None), [])
        self.assertEqual(self.m(123), [])

    def test_c13d_verbs_from_the_engine_command_table(self):
        """Review P3-2: the stage verbs are the `reel` command table (read from the engine source without importing
        it); read-only verbs never start a stage."""
        verbs = tr.known_verbs()
        for v in ("previews", "plan", "ppro-build", "qc", "audio-clean", "motion-plan", "reels-plan", "doctor"):
            self.assertIn(v, verbs)
        for v in ("help", "nonsense", "py-x"):
            self.assertNotIn(v, verbs)
        self.assertTrue(set(tr.NON_STAGE_VERBS) <= verbs)
        with tempfile.TemporaryDirectory() as d:
            self.assertIsNone(tr.known_verbs(Path(d)))                     # no engine there: any verb
            (Path(d) / "lib").mkdir()
            (Path(d) / "cli.py").write_text("CORE_COMMANDS = {'alpha': 'x', 'beta-two': 'y'}\n", encoding="utf-8")
            (Path(d) / "lib" / "podcast_cli.py").write_text("HELP: dict = {'gamma': 'z'}\n", encoding="utf-8")
            (Path(d) / "lib" / "motion_cli.py").write_text("X = 1\nHELP = {'delta': 'w', 5: 'n'}\n",
                                                          encoding="utf-8")
            self.assertEqual(tr.known_verbs(Path(d)), {"alpha", "beta-two", "gamma", "delta"})
            (Path(d) / "cli.py").write_text("def broken(:\n", encoding="utf-8")
            self.assertIsNone(tr.known_verbs(Path(d)))
            (Path(d) / "cli.py").write_text("OTHER = {}\n", encoding="utf-8")
            self.assertIsNone(tr.known_verbs(Path(d)))
            with mock.patch.object(tr, "ENGINE", Path(d)):                   # N36: the report says so
                r = report([PROJ])
            self.assertTrue(any("command table" in a for a in r["assumptions"]), r["assumptions"])
        self.assertFalse(any("command table" in a for a in report([PROJ])["assumptions"]))

    def test_c13e_unknown_and_read_only_verbs_in_a_report(self):
        """`reel help`, a mistyped verb: no stage. `reel next/doctor/status`: the video may change, the stage not."""
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "proj"
            p.mkdir()
            recs = [rec("a", u(fresh=1), [MF.bash("reel qc --video-id A_1", "t1")]),
                    rec("b", u(fresh=2), [MF.bash("reel help plan", "t2")]),
                    rec("c", u(fresh=4), [MF.bash("reel nonsense --video-id X_9", "t3")]),
                    rec("d", u(fresh=8), [MF.bash("reel doctor", "t4")]),
                    rec("e", u(fresh=16), [MF.bash("reel next --video-id B_2", "t5")])]
            (p / "s.jsonl").write_text("".join(json.dumps(x) + "\n" for x in recs), encoding="utf-8")
            r = report([p], raw_ids=True)
        self.assertEqual(sorted(r["by_stage"]), ["qc"])
        self.assertEqual(r["by_item"]["A_1"]["raw"]["fresh"], 15)
        self.assertEqual(r["by_item"]["B_2"]["by_stage"]["qc"]["raw"]["fresh"], 16)
        self.assertNotIn("X_9", r["by_item"])
        self.assertEqual(r["unknown_verbs"], 2)

    def test_c12_usage_before_the_first_reel_command_is_setup(self):
        """Case 12: m1 (4000) runs before any reel command."""
        r = report([PROJ], raw_ids=True)
        self.assertAlmostEqual(r["by_stage"]["setup"]["weighted"], 4000.0, places=6)
        self.assertAlmostEqual(r["by_item"]["unattributed"]["by_stage"]["setup"]["weighted"], 4000.0, places=6)

    def test_c11e_fixture_stages(self):
        """previews 7570, plan m4 = 20 + 500*2 + 5000*0.05 + 400*5 = 3270, qc = m5 830 + m6 601 + m10 200 = 1631,
        ppro-build = m7 702 + m9 (fast: 100*2 + 10*10 = 300) = 1002."""
        r = report([PROJ], raw_ids=True)
        got = {k: round(v["weighted"], 6) for k, v in r["by_stage"].items()}
        self.assertEqual(got, {"setup": 4000.0, "previews": 7570.0, "plan": 3270.0, "qc": 1631.0,
                               "ppro-build": 1002.0, "unattributed-subagent": 30.0})

    def test_c14_interleaved_items_add_up_to_the_total(self):
        """Case 14: EP02 11842 + EP03 1631 + unattributed 4030 = 17503; `--model large-v3` is no video."""
        r = report([PROJ], raw_ids=True)
        got = {k: round(v["weighted"], 6) for k, v in r["by_item"].items()}
        self.assertEqual(got, {"EP02_C0238": 11842.0, "EP03_C0101": 1631.0, "unattributed": 4030.0})
        for cat in tr.CATS:
            self.assertEqual(sum(v["raw"][cat] for v in r["by_item"].values()), r["totals"]["raw"][cat])
        self.assertEqual(sum(v["messages"] for v in r["by_item"].values()), r["totals"]["messages"])

    def test_c14b_command_without_an_id_keeps_the_current_item(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "proj"
            p.mkdir()
            recs = [rec("a", u(fresh=1), [MF.bash("reel qc --video-id A_1", "t1")]),
                    rec("b", u(fresh=2), [MF.bash("reel model-download --model large-v3", "t2")]),
                    rec("c", u(fresh=4), [MF.text()])]
            (p / "s.jsonl").write_text("".join(json.dumps(x) + "\n" for x in recs), encoding="utf-8")
            r = report([p], raw_ids=True)
        self.assertEqual(r["by_item"]["A_1"]["raw"]["fresh"], 7)
        self.assertEqual(r["by_item"]["A_1"]["by_stage"]["model-download"]["raw"]["fresh"], 6)
        self.assertEqual(sorted(r["by_item"]), ["A_1"])                       # no LARGE-V3 phantom video

    def test_c14c_marker_order_inside_one_message_and_spawn_after_marker(self):
        """Blocks of one message apply in order: an Agent call after a reel command gets the new stage."""
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "proj"
            (p / "s" / "subagents").mkdir(parents=True)
            recs = [rec("a", u(fresh=1), [MF.bash("reel qc --video-id A_1", "t1"), MF.agent("toolu_Z"),
                                          MF.bash("reel plan --video-id B_2", "t2")])]
            (p / "s.jsonl").write_text("".join(json.dumps(x) + "\n" for x in recs), encoding="utf-8")
            (p / "s" / "subagents" / "agent-z.jsonl").write_text(
                json.dumps(rec("z", u(fresh=50), sidechain=True)) + "\n", encoding="utf-8")
            (p / "s" / "subagents" / "agent-z.meta.json").write_text('{"toolUseId": "toolu_Z"}', encoding="utf-8")
            r = report([p], raw_ids=True)
        self.assertEqual(r["by_item"]["A_1"]["by_stage"]["qc"]["raw"]["fresh"], 50)
        self.assertEqual(r["by_item"]["B_2"]["by_stage"]["plan"]["raw"]["fresh"], 1)

    def test_c14d_marked_only_keeps_sessions_with_a_reel_command(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "proj"
            p.mkdir()
            (p / "a.jsonl").write_text(json.dumps(rec("a", u(fresh=1), [MF.bash("reel qc --video-id A_1", "t")]))
                                       + "\n", encoding="utf-8")
            (p / "b.jsonl").write_text(json.dumps(rec("b", u(fresh=100))) + "\n", encoding="utf-8")
            (p / "c.jsonl").write_text(json.dumps(rec("c", u(fresh=1000), [MF.bash("reel help", "t")])) + "\n",
                                       encoding="utf-8")
            r = report([p], marked_only=True)
            full = report([p])
        self.assertEqual(r["totals"]["raw"]["fresh"], 1)
        self.assertEqual(r["sessions"], 1)
        self.assertEqual(full["totals"]["raw"]["fresh"], 1101)
        self.assertEqual(full["sessions"], 3)

    def test_c14e_marked_only_ignores_markers_inside_subagent_records(self):
        """Mutant M71: a reel command run only by a subagent (in-file sidechain or stream-json child) does not
        make the session a pipeline session."""
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "proj"
            p.mkdir()
            side = rec("a", u(fresh=1), [MF.bash("reel qc --video-id A_1", "t")], sidechain=True)
            child = rec("b", u(fresh=2), [MF.bash("reel qc --video-id A_1", "t2")])
            child["parent_tool_use_id"] = "toolu_x"
            (p / "s.jsonl").write_text(json.dumps(side) + "\n" + json.dumps(child) + "\n"
                                       + json.dumps(rec("c", u(fresh=4))) + "\n", encoding="utf-8")
            r = report([p], marked_only=True)
        self.assertEqual(r["sessions"], 0)
        self.assertEqual(r["totals"]["messages"], 0)

    def test_c14f_powershell_tool_commands_use_powershell_quoting(self):
        """The fixture's m7 (PowerShell tool): `Write-Host "C:\\fixture\\" ; & ...reel.cmd ppro-build` is found."""
        r = report([PROJ], raw_ids=True)
        self.assertAlmostEqual(r["by_item"]["EP02_C0238"]["by_stage"]["ppro-build"]["weighted"], 1002.0, places=6)


# ---------------------------------------------------------------------------------------------------------------- D
class TestWeighting(TmpProject):
    def test_d15_hand_calculation_standard_model_and_lead_scaling(self):
        """Case 15 on claude-opus-4-8 ($5 / 6.25 / 10 / 0.50 / 25, standard 0.1 read) as the lead:
        1000 fresh + 400 w5 + 300 w1 + 10000 read + 200 out = 1000 + 500 + 600 + 1000 + 1000 = 4100.
        A claude-sonnet-4-6 message ($3 ...; relative 0.6 to the lead) with the same tokens = 4100 * 0.6 = 2460."""
        self.write("s.jsonl", [rec("a", u(fresh=1000, w5=400, w1=300, read=10000, out=200), model="claude-opus-4-8"),
                               rec("b", u(fresh=1000, w5=400, w1=300, read=10000, out=200),
                                   model="claude-sonnet-4-6")])
        r = report([self.proj], lead_model="claude-opus-4-8")
        self.assertAlmostEqual(r["by_model"]["claude-opus-4-8"]["weighted"], 4100.0, places=6)
        self.assertAlmostEqual(r["by_model"]["claude-sonnet-4-6"]["weighted"], 2460.0, places=6)
        self.assertAlmostEqual(r["totals"]["weighted"], 6560.0, places=6)
        self.assertEqual(r["prices"]["lead_model"], "claude-opus-4-8")

    def test_d15b_fixture_totals_and_published_read_rate(self):
        """The fixture: opus-5-5 reads at 0.05x (published), so the weighted total is 17503 and the M5.2 unit
        (read 0.1x everywhere) is 17503 + 34000*0.05 (opus reads) + 2000*0.025 (sonnet reads) = 19253."""
        r = report([PROJ])
        self.assertAlmostEqual(r["totals"]["weighted"], 17503.0, places=6)
        self.assertAlmostEqual(r["totals"]["weighted_m52"], 19253.0, places=6)
        self.assertEqual(r["totals"]["raw"], {"fresh": 1738, "write_5m": 3100, "write_1h": 1500, "read": 36000,
                                              "output": 2050})
        self.assertEqual(r["totals"]["messages"], 13)
        self.assertEqual(r["errors"]["count"], 1)

    def test_d15c_lead_defaults_to_the_most_used_main_model(self):
        self.write("s.jsonl", [rec("a", u(fresh=10), model="claude-sonnet-4-6"),
                               rec("b", u(fresh=10), model="claude-sonnet-4-6"),
                               rec("c", u(fresh=10), model="claude-opus-4-8"),
                               rec("d", u(fresh=10), model="claude-opus-4-8", sidechain=True),
                               rec("e", u(fresh=10), model="claude-opus-4-8", sidechain=True)])
        r = report([self.proj])
        self.assertEqual(r["prices"]["lead_model"], "claude-sonnet-4-6")
        self.assertAlmostEqual(r["by_model"]["claude-sonnet-4-6"]["weighted"], 20.0, places=6)
        self.assertAlmostEqual(r["by_model"]["claude-opus-4-8"]["weighted"], 30 * 5 / 3, places=6)

    def test_d15d_lead_tie_breaks_by_name(self):
        self.write("s.jsonl", [rec("a", u(fresh=10), model="claude-sonnet-4-6"),
                               rec("b", u(fresh=10), model="claude-opus-4-8")])
        self.assertEqual(report([self.proj])["prices"]["lead_model"], "claude-opus-4-8")

    def test_d15e_dated_model_ids_normalise(self):
        self.assertEqual(tr.normalize_model("claude-haiku-4-5-20251001"), "claude-haiku-4-5")
        self.assertEqual(tr.normalize_model("claude-opus-4-8[1m]"), "claude-opus-4-8")
        self.assertEqual(tr.normalize_model(" claude-opus-5-5 "), "claude-opus-5-5")
        self.assertEqual(tr.normalize_model(None), "unknown")
        self.assertEqual(tr.normalize_model(""), "unknown")

    def test_d15f_haiku_5_5_long_prompt_tier(self):
        """Haiku 5.5 prices a request whose prompt (input + cache read + cache write) is over 100,000 tokens at
        $0.50 / 0.625 / 1 / 0.05 / 2.50; at or under it $0.10 / 0.125 / 0.20 / 0.01 / 0.50."""
        self.assertEqual(tr.price_row("claude-haiku-5-5", 100_000), (0.10, 0.125, 0.20, 0.01, 0.50))
        self.assertEqual(tr.price_row("claude-haiku-5-5", 100_001), (0.50, 0.625, 1.0, 0.05, 2.50))
        self.write("s.jsonl", [rec("a", u(fresh=1, read=100_000, out=10), model="claude-haiku-5-5"),
                               rec("l", u(fresh=4), model="claude-opus-5-5"),
                               rec("m", u(fresh=4), model="claude-opus-5-5")])
        r = report([self.proj])
        # long tier relative to opus-5-5 input $4: (1*0.5 + 100000*0.05 + 10*2.5) / 4 = 5025.5 / 4
        self.assertAlmostEqual(r["by_model"]["claude-haiku-5-5"]["weighted"], 5025.5 / 4, places=6)

    def test_d15g_price_table_rows(self):
        """Spot checks against the published page (read 2026-10-18)."""
        self.assertEqual(tr.price_row("claude-opus-5-5", 0), (4, 5, 8, 0.20, 20))
        self.assertEqual(tr.price_row("claude-sonnet-5-5", 0), (2, 2.5, 4, 0.10, 10))
        self.assertEqual(tr.price_row("claude-sonnet-5", 0), (2, 2.5, 4, 0.20, 10))
        self.assertEqual(tr.price_row("claude-fable-5-1", 0), (10, 12.5, 20, 0.25, 50))
        self.assertEqual(tr.price_row("claude-opus-4-8", 0), (5, 6.25, 10, 0.50, 25))
        self.assertEqual(tr.price_row("claude-haiku-4-5", 0), (1, 1.25, 2, 0.10, 5))
        self.assertIsNone(tr.price_row("claude-imaginary-9", 0))
        self.assertIn("pricing", tr.PRICES_SOURCE)
        self.assertEqual(tr.PRICES_READ_ON, "2026-10-18")

    def test_d16_cache_write_without_split_is_five_minute_and_noted(self):
        """Case 16: cache_creation_input_tokens without the cache_creation split -> 5-minute writes, noted."""
        self.write("s.jsonl", [rec("a", u(w5=800, split=False))])
        r = report([self.proj])
        self.assertEqual(r["totals"]["raw"]["write_5m"], 800)
        self.assertEqual(r["totals"]["raw"]["write_1h"], 0)
        self.assertTrue(any("5-minute" in a and "1 message" in a for a in r["assumptions"]), r["assumptions"])

    def test_d16b_split_never_exceeds_the_total(self):
        bad = u(w5=0, w1=0)
        bad["cache_creation_input_tokens"] = 100
        bad["cache_creation"] = {"ephemeral_5m_input_tokens": 0, "ephemeral_1h_input_tokens": 300}
        part = u()
        part["cache_creation_input_tokens"] = 100
        part["cache_creation"] = {"ephemeral_5m_input_tokens": 0, "ephemeral_1h_input_tokens": 40}
        self.write("s.jsonl", [rec("a", bad), rec("b", part)])
        r = report([self.proj])
        self.assertEqual(r["totals"]["raw"]["write_1h"], 140)
        self.assertEqual(r["totals"]["raw"]["write_5m"], 60)
        self.assertFalse(any("5-minute" in a for a in r["assumptions"]))

    def test_d16c_non_numeric_usage_fields_count_as_zero(self):
        bad = u(fresh=5)
        bad["output_tokens"] = None
        bad["cache_read_input_tokens"] = "12"
        bad["cache_creation"] = "x"
        neg = u(fresh=-50, read=-7, out=3)                      # mutant M24: negative counts are not tokens
        self.write("s.jsonl", [rec("a", bad), rec("n", neg)])
        r = report([self.proj])
        self.assertEqual(r["totals"]["raw"], {"fresh": 5, "write_5m": 0, "write_1h": 0, "read": 0, "output": 3})

    def test_d16d_booleans_are_not_token_counts(self):
        bad = u(fresh=5)
        bad["output_tokens"] = True
        self.write("s.jsonl", [rec("a", bad)])
        self.assertEqual(report([self.proj])["totals"]["raw"]["output"], 0)

    def test_d17_unknown_model_is_unpriced(self):
        """Case 17: an unknown model id -> unpriced row with raw tokens; the weighted total excludes it."""
        self.write("s.jsonl", [rec("a", u(fresh=10)), rec("b", u(fresh=500, out=5), model="claude-imaginary-9")])
        r = report([self.proj])
        self.assertEqual(r["unpriced"], {"claude-imaginary-9": {"fresh": 500, "write_5m": 0, "write_1h": 0,
                                                                "read": 0, "output": 5}})
        self.assertTrue(r["totals"]["weighted_excludes_unpriced"])
        self.assertAlmostEqual(r["totals"]["weighted"], 10.0, places=6)
        self.assertIsNone(r["by_model"]["claude-imaginary-9"]["weighted"])
        self.assertEqual(r["totals"]["raw"]["fresh"], 510)
        self.assertNotIn("claude-imaginary-9", r["models"]["mix"])

    def test_d17d_zero_token_placeholder_models_are_not_unpriced(self):
        """Found on this PC's transcripts: `<synthetic>` placeholder records without the error flag carry zero
        usage. They are no API call, so they do not make the weighted total `excludes unpriced`."""
        self.write("s.jsonl", [rec("a", u(fresh=10)), rec("p", u(), model="<synthetic>")])
        r = report([self.proj])
        self.assertEqual(r["unpriced"], {})
        self.assertFalse(r["totals"]["weighted_excludes_unpriced"])
        self.assertIsNone(r["by_model"]["<synthetic>"]["weighted"])

    def test_d17b_all_priced_says_so(self):
        self.write("s.jsonl", [rec("a", u(fresh=10))])
        r = report([self.proj])
        self.assertFalse(r["totals"]["weighted_excludes_unpriced"])
        self.assertEqual(r["unpriced"], {})

    def test_d17c_unpriced_lead_gives_no_weighted_numbers(self):
        self.write("s.jsonl", [rec("a", u(fresh=10), model="claude-imaginary-9")])
        r = report([self.proj])
        self.assertIsNone(r["totals"]["weighted"])
        self.assertIsNone(r["totals"]["weighted_m52"])
        self.assertTrue(any("lead model" in a for a in r["assumptions"]))

    def test_d18_model_mix_sums_to_one(self):
        """Case 18: opus 14593 + opus+fast 300 + sonnet 2260 + haiku 350 = 17503."""
        r = report([PROJ])
        mix = r["models"]["mix"]
        self.assertAlmostEqual(sum(mix.values()), 1.0, delta=1e-9)
        self.assertAlmostEqual(mix["claude-opus-5-5"], 14593 / 17503, places=9)
        self.assertAlmostEqual(mix["claude-opus-5-5+fast"], 300 / 17503, places=9)
        self.assertAlmostEqual(mix["claude-sonnet-5-5"], 2260 / 17503, places=9)
        self.assertAlmostEqual(mix["claude-haiku-4-5"], 350 / 17503, places=9)
        self.assertEqual(r["models"]["seen"], ["claude-haiku-4-5", "claude-opus-5-5", "claude-opus-5-5+fast",
                                               "claude-sonnet-5-5"])

    def test_d18b_empty_weighted_gives_an_empty_mix(self):
        self.write("s.jsonl", [rec("a", u())])
        self.assertEqual(report([self.proj])["models"]["mix"], {})

    def test_d19_fast_mode_is_its_own_key(self):
        """Case 19: speed fast -> <model>+fast at the fast rates ($8 / $40 on opus-5-5; cache multipliers on top:
        5m 10, 1h 16, read 0.05x of 8 = 0.40)."""
        self.assertEqual(tr.price_row("claude-opus-5-5+fast", 0), (8, 10.0, 16, 0.4, 40))
        self.assertEqual(tr.price_row("claude-opus-4-8+fast", 0), (10, 12.5, 20, 1.0, 50))
        self.assertIsNone(tr.price_row("claude-sonnet-5-5+fast", 0))
        self.write("s.jsonl", [rec("a", u(fresh=4)), rec("b", u(fresh=4)),
                               rec("f", u(fresh=100, read=1000, out=10, speed="fast"))])
        r = report([self.proj])
        # (100*8 + 1000*0.4 + 10*40) / 4 = 400
        self.assertAlmostEqual(r["by_model"]["claude-opus-5-5+fast"]["weighted"], 400.0, places=6)
        self.assertAlmostEqual(r["by_model"]["claude-opus-5-5"]["weighted"], 8.0, places=6)


# ---------------------------------------------------------------------------------------------------------------- E
class TestLeadContext(TmpProject):
    def test_e20_median_p90_max_and_guard_rail(self):
        """Case 20: per-turn lead context = fresh + read + writes on main-chain records; 151k is flagged."""
        recs = [rec(f"m{i}", u(fresh=1000 * i, read=0)) for i in range(1, 10)]
        recs.append(rec("big", u(fresh=1000, w5=50_000, w1=0, read=100_000)))          # 151,000
        recs.append(rec("edge", u(fresh=150_000)))                                     # exactly 150k: not over
        recs.append(rec("side", u(fresh=500_000), sidechain=True))                     # not a lead turn
        recs.append(rec("err", u(fresh=900_000), error=True))                          # not a lead turn
        self.write("s.jsonl", recs)
        lc = report([self.proj])["lead_context"]
        self.assertEqual(lc["turns"], 11)
        self.assertEqual(lc["guard_rail"], 150_000)
        self.assertEqual(lc["max"], 151_000)
        self.assertEqual(lc["median"], 6000)
        self.assertEqual(lc["p90"], 150_000)              # nearest rank: ceil(0.9 * 11) = 10th of 11
        self.assertEqual(lc["over"], 1)
        self.assertEqual(lc["over_turns"], [{"session": "s.jsonl", "turn": 10, "context": 151_000}])

    def test_e20b_fixture_lead_context(self):
        """Fixture main turns: 3000, 4010, 4105, 5520, 6030, 7001, 8002, 100 (m9), 1050 (m10)."""
        lc = report([PROJ])["lead_context"]
        self.assertEqual((lc["turns"], lc["median"], lc["p90"], lc["max"], lc["over"]), (9, 4105, 8002, 8002, 0))

    def test_e20c_even_count_median_and_empty(self):
        self.write("s.jsonl", [rec("a", u(fresh=10)), rec("b", u(fresh=21))])
        lc = report([self.proj])["lead_context"]
        self.assertEqual(lc["median"], 15.5)
        self.assertEqual(lc["p90"], 21)
        self.write("s.jsonl", [rec("a", u(fresh=10), sidechain=True)])
        lc = report([self.proj])["lead_context"]
        self.assertEqual((lc["turns"], lc["median"], lc["p90"], lc["max"], lc["over"]), (0, None, None, None, 0))

    def test_e20d_percentile_helper(self):
        self.assertEqual(tr.nearest_rank([5, 1, 3, 2, 4], 0.9), 5)
        self.assertEqual(tr.nearest_rank(list(range(1, 11)), 0.9), 9)
        self.assertEqual(tr.nearest_rank(list(range(1, 21)), 0.9), 18)
        self.assertIsNone(tr.nearest_rank([], 0.9))


# ---------------------------------------------------------------------------------------------------------------- F
class TestOutput(unittest.TestCase):
    def run_main(self, argv):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            rc = tr.main(argv)
        return rc, out.getvalue(), err.getvalue()

    def test_f21_anonymised_text_and_json(self):
        """Case 21: the planted client name, absolute path, prompt sentence, project folder name, raw item ids and
        tool inputs never appear in the text or JSON output."""
        with tempfile.TemporaryDirectory() as d:
            jp = Path(d) / "r.json"
            rc, out, err = self.run_main([str(PROJ), "--json", str(jp), "--date", DATE])
            self.assertEqual(rc, 0, err)
            blob = jp.read_text(encoding="utf-8")
        json_text = json.dumps(json.loads(blob), ensure_ascii=False)
        for planted in (MF.PLANTED_CLIENT, MF.PLANTED_PATH, MF.PLANTED_PROMPT, MF.PROJECT_DIR, "Zorblax",
                        "Fixture Clients", "EP02_C0238", "EP03_C0101", "fixture helper", "run_python.sh",
                        json.dumps(MF.PLANTED_PATH)[1:-1]):
            for name, text in (("text", out), ("json", blob), ("json-decoded", json_text)):
                self.assertNotIn(planted, text, f"{planted!r} leaked into the {name} output")
        r = json.loads(blob)
        self.assertEqual(sorted(r["by_item"]), ["item-01", "item-02", "unattributed"])
        self.assertAlmostEqual(r["by_item"]["item-01"]["weighted"], 11842.0, places=6)    # EP02 appears first
        self.assertTrue(r["anonymised"])

    def test_f21b_raw_ids_is_opt_in_and_still_hides_paths(self):
        r = report([PROJ], raw_ids=True)
        blob = json.dumps(r, ensure_ascii=False)
        self.assertIn("EP02_C0238", blob)
        self.assertFalse(r["anonymised"])
        for planted in (MF.PLANTED_CLIENT, MF.PLANTED_PATH, MF.PLANTED_PROMPT, MF.PROJECT_DIR):
            self.assertNotIn(planted, blob)

    def test_f21c_skipped_file_labels_hold_no_folder_names(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "D--Fixture-Clients-Zorblax-Quentaro"
            (p / "s1" / "subagents").mkdir(parents=True)
            (p / "s1.jsonl").write_text("{bad\n", encoding="utf-8")
            (p / "s1" / "subagents" / "agent-q.jsonl").write_text("{bad\n", encoding="utf-8")
            r = report([p])
        self.assertEqual(r["skipped"], [{"file": "s1.jsonl", "line": 1},
                                        {"file": "s1/subagents/agent-q.jsonl", "line": 1}])

    def test_f22_stamps(self):
        """Case 22: commit sha, tool version, model ids, report date and the price source are present."""
        r = tr.build_report([PROJ], date=DATE)
        self.assertEqual(r["tool"], "token_report")
        self.assertEqual(r["version"], tr.VERSION)
        self.assertEqual(r["report_date"], DATE)
        self.assertEqual(r["commit"], tr.repo_commit(ROOT))
        if (ROOT / ".git").exists():
            self.assertRegex(r["commit"], r"^[0-9a-f]{40}$")
        self.assertEqual(r["prices"]["source"], tr.PRICES_SOURCE)
        self.assertEqual(r["prices"]["read_on"], tr.PRICES_READ_ON)
        self.assertIn("claude-opus-5-5", r["models"]["seen"])

    def test_f22b_repo_commit_reads_git_files_without_running_git(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            self.assertIsNone(tr.repo_commit(root))
            g = root / ".git"
            (g / "refs" / "heads").mkdir(parents=True)
            (g / "HEAD").write_text("ref: refs/heads/release/3.0\n", encoding="utf-8")
            (g / "refs" / "heads" / "release").mkdir()
            (g / "refs" / "heads" / "release" / "3.0").write_text("a" * 40 + "\n", encoding="utf-8")
            self.assertEqual(tr.repo_commit(root), "a" * 40)
            (g / "refs" / "heads" / "release" / "3.0").unlink()
            (g / "packed-refs").write_text("# pack-refs with: peeled\n" + "b" * 40 + " refs/heads/other\n"
                                           + "c" * 40 + " refs/heads/release/3.0\n^" + "d" * 40 + "\n",
                                           encoding="utf-8")
            self.assertEqual(tr.repo_commit(root), "c" * 40)
            (g / "HEAD").write_text("e" * 40 + "\n", encoding="utf-8")                  # detached
            self.assertEqual(tr.repo_commit(root), "e" * 40)
            (g / "HEAD").write_text("garbage\n", encoding="utf-8")
            self.assertIsNone(tr.repo_commit(root))
            (g / "HEAD").write_text("ref: refs/heads/gone\n", encoding="utf-8")
            self.assertIsNone(tr.repo_commit(root))
            shutil.rmtree(g)
            wt = root / "wt-git"
            wt.mkdir()
            (wt / "HEAD").write_text("f" * 40 + "\n", encoding="utf-8")
            (root / ".git").write_text("gitdir: wt-git\n", encoding="utf-8")                 # worktree pointer
            self.assertEqual(tr.repo_commit(root), "f" * 40)
            (root / ".git").write_text("nonsense\n", encoding="utf-8")
            self.assertIsNone(tr.repo_commit(root))

    def test_f22c_worktree_head_ref_resolves_in_the_common_dir(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            common = root / "main-git"
            wt = common / "worktrees" / "w1"
            wt.mkdir(parents=True)
            (common / "refs" / "heads").mkdir(parents=True)
            (common / "refs" / "heads" / "b1").write_text("1" * 40 + "\n", encoding="utf-8")
            (wt / "HEAD").write_text("ref: refs/heads/b1\n", encoding="utf-8")
            (wt / "commondir").write_text("../..\n", encoding="utf-8")
            (root / ".git").write_text(f"gitdir: {wt}\n", encoding="utf-8")
            self.assertEqual(tr.repo_commit(root), "1" * 40)

    def test_f23_deterministic_json(self):
        """Case 23: two runs on the same fixtures give byte-identical JSON."""
        with tempfile.TemporaryDirectory() as d:
            a, b = Path(d) / "a.json", Path(d) / "b.json"
            self.assertEqual(self.run_main([str(PROJ), "--json", str(a), "--date", DATE])[0], 0)
            self.assertEqual(self.run_main([str(PROJ), "--json", str(b), "--date", DATE])[0], 0)
            self.assertEqual(a.read_bytes(), b.read_bytes())

    def test_f24_default_is_a_short_summary_and_json_writes_the_full_form(self):
        """Case 24."""
        rc, out, err = self.run_main([str(PROJ), "--date", DATE])
        self.assertEqual(rc, 0, err)
        self.assertLessEqual(len(out.splitlines()), 30)
        self.assertIn("weighted", out)
        self.assertIn("17,503", out)
        self.assertIn("--json", out)              # tells where the full form comes from
        self.assertNotIn("{", out)
        with tempfile.TemporaryDirectory() as d:
            jp = Path(d) / "sub dir" / "full.json"
            rc, out, err = self.run_main([str(PROJ), "--json", str(jp), "--date", DATE])
            self.assertEqual(rc, 0, err)
            self.assertIn(str(jp), out)
            full = json.loads(jp.read_text(encoding="utf-8"))
        for k in ("totals", "by_stage", "by_item", "by_model", "lead_context", "models", "errors", "skipped"):
            self.assertIn(k, full)

    def test_f24b_json_to_stdout(self):
        rc, out, err = self.run_main([str(PROJ), "--json", "-", "--date", DATE])
        self.assertEqual(rc, 0, err)
        self.assertAlmostEqual(json.loads(out)["totals"]["weighted"], 17503.0, places=6)

    def test_f24c_summary_mentions_partial_unpriced_errors_and_guard_rail(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "proj"
            p.mkdir()
            recs = [rec("a", u(fresh=151_000)), rec("b", u(fresh=5), model="claude-imaginary-9"),
                    rec("e", u(fresh=1), error=True)]
            (p / "s.jsonl").write_text("".join(json.dumps(x) + "\n" for x in recs) + "{bad\n", encoding="utf-8")
            rc, out, err = self.run_main([str(p), "--date", DATE])
        self.assertEqual(rc, 0, err)
        low = out.lower()
        self.assertIn("partial", low)
        self.assertIn("unpriced", low)
        self.assertIn("api error", low)
        self.assertIn("over the 150,000 guard rail", low)

    def test_f24d_bad_date_is_refused(self):
        rc, out, err = self.run_main([str(PROJ), "--date", "18/10/2026"])
        self.assertEqual(rc, 2)
        self.assertIn("date", err)

    def test_f24e_json_write_failure_leaves_no_half_file(self):
        with tempfile.TemporaryDirectory() as d:
            jp = Path(d) / "r.json"
            with mock.patch.object(tr.json, "dump", side_effect=OSError("disk full")):
                rc, out, err = self.run_main([str(PROJ), "--json", str(jp), "--date", DATE])
            self.assertEqual(rc, 2)
            self.assertFalse(jp.exists())
            self.assertEqual(list(Path(d).iterdir()), [])


# ---------------------------------------------------------------------------------------------------------------- G
class TestPlatformAndPaths(unittest.TestCase):
    def run_main(self, argv, env=None):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err), mock.patch.dict(os.environ, env or {}):
            rc = tr.main(argv)
        return rc, out.getvalue(), err.getvalue()

    def test_g25_projects_dir_resolution(self):
        """Case 25: CLAUDE_CONFIG_DIR wins; else the home of the platform (Windows USERPROFILE, macOS HOME)."""
        self.assertEqual(tr.default_projects_dir({"CLAUDE_CONFIG_DIR": "/cfg"}, "darwin"), Path("/cfg") / "projects")
        self.assertEqual(tr.default_projects_dir({"CLAUDE_CONFIG_DIR": "C:\\cfg", "USERPROFILE": "C:\\u"}, "win32"),
                         Path("C:\\cfg") / "projects")
        self.assertEqual(tr.default_projects_dir({"HOME": "/Users/x"}, "darwin"),
                         Path("/Users/x") / ".claude" / "projects")
        self.assertEqual(tr.default_projects_dir({"USERPROFILE": "C:\\Users\\x", "HOME": "/wrong"}, "win32"),
                         Path("C:\\Users\\x") / ".claude" / "projects")
        self.assertEqual(tr.default_projects_dir({"HOMEDRIVE": "C:", "HOMEPATH": "\\Users\\y"}, "win32"),
                         Path("C:\\Users\\y") / ".claude" / "projects")
        self.assertEqual(tr.default_projects_dir({"CLAUDE_CONFIG_DIR": ""}, "linux"),
                         Path.home() / ".claude" / "projects")

    def test_g25b_default_root_and_project_option_read_the_sandboxed_config(self):
        """Unset paths -> CLAUDE_CONFIG_DIR/projects (the _isolation sandbox here); --project picks a folder."""
        with tempfile.TemporaryDirectory() as d:
            cfg = Path(d) / "مجلد تجربة 1"                    # spaces and Arabic letters
            proj = cfg / "projects" / "D--مشروع-أ"
            shutil.copytree(PROJ, proj)
            other = cfg / "projects" / "other"
            other.mkdir()
            (other / "x.jsonl").write_text(json.dumps(rec("zz_other", u(fresh=10))) + "\n", encoding="utf-8")
            rc, out, err = self.run_main(["--project", "D--مشروع-أ", "--json", "-", "--date", DATE],
                                         env={"CLAUDE_CONFIG_DIR": str(cfg)})
            self.assertEqual(rc, 0, err)
            self.assertAlmostEqual(json.loads(out)["totals"]["weighted"], 17503.0, places=6)
            rc, out, err = self.run_main(["--json", "-", "--date", DATE], env={"CLAUDE_CONFIG_DIR": str(cfg)})
            self.assertEqual(rc, 0, err)
            self.assertAlmostEqual(json.loads(out)["totals"]["weighted"], 17503.0 + 10.0, places=6)
            rc, out, err = self.run_main(["--project", "..", "--date", DATE], env={"CLAUDE_CONFIG_DIR": str(cfg)})
            self.assertEqual(rc, 2)
            self.assertIn("project", err)

    def test_g25c_a_single_file_argument(self):
        r = report([PROJ / "s2.jsonl"], raw_ids=True)
        self.assertEqual(r["sessions"], 1)
        self.assertEqual(r["totals"]["messages"], 3)          # m4, m5 (replayed), m10

    def test_g25d_links_are_not_followed(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d) / "root"
            root.mkdir()
            shutil.copytree(FIX / "twin_folder", root / "real")
            try:
                dir_link(root / "link", root / "real")
            except OSError as e:
                self.skipTest(f"cannot make a directory link here: {e}")
            r = report([root])
        self.assertAlmostEqual(r["totals"]["weighted"], 17273.0, places=6)
        self.assertEqual(r["sessions"], 1)

    def test_g26_large_file_streams_in_bounded_memory(self):
        """Case 26: a 200 MB synthetic file streams line by line; peak memory grows far less than the file."""
        def make(path, mb):
            filler = "x" * (1 << 20)
            line = json.dumps({"type": "user", "message": {"role": "user", "content": filler}}) + "\n"
            a = json.dumps(rec("same", u(fresh=1, out=1))) + "\n"
            with open(path, "w", encoding="utf-8", newline="\n") as fh:
                for i in range(mb):
                    fh.write(line)
                    fh.write(a)

        def peak(path):
            tracemalloc.start()
            try:
                r = tr.build_report([path], date=DATE, commit="x")
                return tracemalloc.get_traced_memory()[1], r
            finally:
                tracemalloc.stop()

        with tempfile.TemporaryDirectory() as d:
            small, big = Path(d) / "small" / "s.jsonl", Path(d) / "big" / "s.jsonl"
            small.parent.mkdir()
            big.parent.mkdir()
            make(small, 20)
            make(big, 200)
            self.assertGreater(big.stat().st_size, 200 * (1 << 20))
            p_small, _ = peak(small)
            p_big, r = peak(big)
        self.assertEqual(r["totals"]["raw"]["fresh"], 1)
        self.assertLess(p_big / p_small, 1.5, (p_small, p_big))
        self.assertLess(p_big, 40 * (1 << 20))

    def test_g27_refusal_writes_nothing(self):
        """Case 27: no transcripts, or a missing folder -> a clear message, exit 2, no JSON file."""
        with tempfile.TemporaryDirectory() as d:
            empty = Path(d) / "empty"
            empty.mkdir()
            (empty / "notes.txt").write_text("x", encoding="utf-8")
            jp = Path(d) / "r.json"
            rc, out, err = self.run_main([str(empty), "--json", str(jp)])
            self.assertEqual(rc, 2)
            self.assertIn("no Claude Code transcripts", err)
            self.assertFalse(jp.exists())
            rc, out, err = self.run_main([str(Path(d) / "missing"), "--json", str(jp)])
            self.assertEqual(rc, 2)
            self.assertIn("cannot read", err)
            self.assertFalse(jp.exists())
            self.assertNotIn(str(Path(d)), err.replace(str(Path(d) / "missing"), ""))

    def test_g27b_unreadable_file_is_skipped_not_a_crash(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "proj"
            p.mkdir()
            (p / "a.jsonl").write_text(json.dumps(rec("a", u(fresh=3))) + "\n", encoding="utf-8")
            (p / "b.jsonl").write_text(json.dumps(rec("b", u(fresh=4))) + "\n", encoding="utf-8")
            real_open = open

            def fake_open(path, *a, **k):
                if str(path).endswith("b.jsonl"):
                    raise PermissionError("locked")
                return real_open(path, *a, **k)
            with mock.patch("builtins.open", fake_open):
                r = report([p])
        self.assertTrue(r["partial"])
        self.assertEqual(r["skipped"], [{"file": "b.jsonl", "line": 0}])
        self.assertEqual(r["totals"]["raw"]["fresh"], 3)

    def test_g27c_invalid_utf8_is_not_a_crash(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "proj"
            p.mkdir()
            (p / "a.jsonl").write_bytes(json.dumps(rec("a", u(fresh=3))).encode() + b"\n\xff\xfe{\n")
            r = report([p])
        self.assertEqual(r["totals"]["raw"]["fresh"], 3)
        self.assertEqual(r["skipped"], [{"file": "a.jsonl", "line": 2}])

    def test_g27d_an_unreadable_folder_is_listed_and_the_report_is_partial(self):
        """Review P3-3: a folder that cannot be listed (permission, a path over MAX_PATH) is never dropped
        silently: it is listed in skipped and the report says partial."""
        real_scandir = os.scandir

        def fake_scandir(path):
            if str(path).replace("\\", "/").endswith("s1/subagents"):
                raise PermissionError("denied")
            return real_scandir(path)
        with mock.patch.object(tr.os, "scandir", fake_scandir):
            r = report([PROJ])
        self.assertTrue(r["partial"])
        self.assertIn({"file": "s1/subagents/", "line": 0}, r["skipped"])
        self.assertEqual(r["subagents"]["messages"], 0)

    def test_g27e_an_entry_that_cannot_be_inspected_is_listed(self):
        """Review P3-3: an entry whose lstat fails is listed in skipped (not taken for a link and dropped)."""
        real_lstat = os.lstat

        def fake_lstat(path, *a, **k):
            if str(path).endswith("s2.jsonl"):
                raise OSError("cannot stat")
            return real_lstat(path, *a, **k)
        with mock.patch.object(tr.os, "lstat", fake_lstat):
            r = report([PROJ])
        self.assertTrue(r["partial"])
        self.assertIn({"file": "s2.jsonl", "line": 0}, r["skipped"])
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "proj"
            (p / "s9").mkdir(parents=True)
            (p / "s9" / "subagents").mkdir()
            (p / "a.jsonl").write_text(json.dumps(rec("a", u(fresh=2))) + "\n", encoding="utf-8")

            def fake_lstat2(path, *a, **k):
                if str(path).endswith("s9"):
                    raise OSError("cannot stat")
                return real_lstat(path, *a, **k)
            with mock.patch.object(tr.os, "lstat", fake_lstat2):
                r = report([p])
        self.assertIn({"file": "(folder)/", "line": 0}, r["skipped"])

    def test_g27g_an_uninspectable_subagents_folder_of_a_file_argument_is_listed(self):
        """Mutant N52: `token_report s1.jsonl` whose s1/subagents cannot be inspected says so."""
        real_lstat = os.lstat

        def fake_lstat(path, *a, **k):
            if str(path).replace("\\", "/").endswith("s1/subagents"):
                raise OSError("cannot stat")
            return real_lstat(path, *a, **k)
        with mock.patch.object(tr.os, "lstat", fake_lstat):
            r = report([PROJ / "s1.jsonl"])
        self.assertTrue(r["partial"])
        self.assertEqual(r["skipped"], [{"file": "s1/subagents/", "line": 0}])

    def test_g27f_nothing_readable_is_a_refusal(self):
        """Review P3-6: transcripts whose every line is malformed -> exit 2, nothing written."""
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "proj"
            p.mkdir()
            (p / "a.jsonl").write_text("{bad\n{worse\n", encoding="utf-8")
            jp = Path(d) / "r.json"
            rc, out, err = self.run_main([str(p), "--json", str(jp)])
            self.assertEqual(rc, 2)
            self.assertIn("no readable transcript records", err)
            self.assertFalse(jp.exists())
            (p / "b.jsonl").write_text(json.dumps({"type": "user", "message": {"content": "x"}}) + "\n",
                                       encoding="utf-8")
            rc, out, err = self.run_main([str(p), "--json", str(jp)])
            self.assertEqual(rc, 0, err)                 # a readable record, even without usage: a report
            self.assertTrue(jp.exists())

    def test_g25e_non_utf8_stdout_and_an_arabic_report_path(self):
        """Review P3-5: stdout in cp1252 (PYTHONUTF8 unset, piped) and an Arabic --json path: no crash, the
        summary comes out as UTF-8."""
        import subprocess
        with tempfile.TemporaryDirectory() as d:
            jp = Path(d) / "تقرير" / "r.json"
            env = dict(os.environ, PYTHONIOENCODING="cp1252", PYTHONUTF8="0")
            for args in (["--json", str(jp)], ["--json", "-"]):
                p = subprocess.run([sys.executable, "-s", "-B", str(ROOT / "tools" / "token_report.py"),
                                    str(PROJ), "--date", DATE] + args, capture_output=True, env=env, timeout=120)
                self.assertEqual(p.returncode, 0, p.stderr.decode("utf-8", "replace"))
                self.assertNotIn(b"Traceback", p.stderr)
            self.assertTrue(jp.exists())
            p = subprocess.run([sys.executable, "-s", "-B", str(ROOT / "tools" / "token_report.py"), str(PROJ),
                                "--date", DATE, "--json", str(jp)], capture_output=True, env=env, timeout=120)
            self.assertIn(str(jp), p.stdout.decode("utf-8"))


# ---------------------------------------------------------------------------------------------------------------- H
class TestEvalRuns(unittest.TestCase):
    """Cases 28-29: a folder collected by tools/eval_transcripts.py (manifest.json + <case>/<run>/...) is reported
    per case and per run; each run de-duplicates on its own."""
    def make(self, root):
        root.mkdir(parents=True)
        runs = []
        for case, run, fresh in (("edit-a", "with-run1", 10), ("edit-a", "with-run2", 20),
                                 ("motion-b", "with-run1", 5)):
            d = root / case / run
            d.mkdir(parents=True)
            recs = [rec("same_id", u(fresh=fresh), [MF.bash("reel qc --video-id C_1", "t")])]
            (d / "trace.jsonl").write_text("".join(json.dumps(x) + "\n" for x in recs), encoding="utf-8")
            pj = d / "projects" / "D--x"
            pj.mkdir(parents=True)
            (pj / "sess.jsonl").write_text("".join(json.dumps(x) + "\n" for x in recs), encoding="utf-8")
            runs.append({"case": case, "run": run, "status": "collected"})
        runs.append({"case": "gone", "run": "with-run1", "status": "missing"})
        (root / "manifest.json").write_text(json.dumps({"tool": "eval_transcripts", "runs": runs}), encoding="utf-8")

    def test_h28_per_case_and_per_run(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d) / "collected"
            self.make(root)
            r = report([root])
        self.assertEqual(sorted(r["runs"]), ["edit-a/with-run1", "edit-a/with-run2", "motion-b/with-run1"])
        self.assertEqual(r["runs"]["edit-a/with-run1"]["raw"]["fresh"], 10)       # trace + transcript: once
        self.assertEqual(r["runs"]["edit-a/with-run2"]["raw"]["fresh"], 20)
        self.assertAlmostEqual(r["runs"]["motion-b/with-run1"]["weighted"], 5.0, places=6)
        self.assertEqual(r["totals"]["raw"]["fresh"], 35)                          # same id in 3 runs: 3 messages
        self.assertEqual(r["runs_missing"], ["gone/with-run1"])
        self.assertIn("lead_context", r["runs"]["edit-a/with-run1"])

    def test_h28b_a_folder_without_manifest_has_no_runs(self):
        self.assertNotIn("runs", report([PROJ]))

    def test_h28c_unsafe_run_names_in_the_manifest_are_ignored(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d) / "collected"
            self.make(root)
            m = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
            m["runs"].append({"case": "..", "run": "x", "status": "collected"})
            m["runs"].append({"case": "a/b", "run": "x", "status": "collected"})
            m["runs"].append({"case": "..", "run": root.name, "status": "collected"})   # would point at root
            m["runs"].append({"case": "edit-a", "run": "..", "status": "collected"})
            (root / "manifest.json").write_text(json.dumps(m), encoding="utf-8")
            r = report([root])
        self.assertEqual(sorted(r["runs"]), ["edit-a/with-run1", "edit-a/with-run2", "motion-b/with-run1"])
        self.assertEqual(r["runs_missing"], ["gone/with-run1"])
        self.assertEqual(r["totals"]["raw"]["fresh"], 35)

    def test_h28d_a_foreign_or_broken_manifest_is_an_ordinary_folder(self):
        """Mutant M85: only a manifest written by eval_transcripts switches to per-run mode."""
        for body in ('{"tool": "something-else", "runs": []}', "{broken", '{"tool": "eval_transcripts", "runs": 5}',
                     "[1, 2]"):
            with tempfile.TemporaryDirectory() as d:
                p = Path(d) / "proj"
                p.mkdir()
                (p / "manifest.json").write_text(body, encoding="utf-8")
                (p / "s.jsonl").write_text(json.dumps(rec("a", u(fresh=9))) + "\n", encoding="utf-8")
                r = report([p])
            self.assertNotIn("runs", r, body)
            self.assertEqual(r["totals"]["raw"]["fresh"], 9, body)

    def test_h28e_manifest_rows_that_are_not_objects_are_skipped(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d) / "collected"
            self.make(root)
            m = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
            m["runs"] += ["text", 5, {"case": 1, "run": "x"}]
            (root / "manifest.json").write_text(json.dumps(m), encoding="utf-8")
            r = report([root])
        self.assertEqual(len(r["runs"]), 3)


class TestFixturesHaveNoDrift(unittest.TestCase):
    def test_committed_fixtures_equal_the_builder(self):
        built = MF.build()
        on_disk = {p.relative_to(FIX).as_posix(): p.read_text(encoding="utf-8")
                   for p in FIX.rglob("*") if p.is_file() and p.name != "make_fixtures.py"
                   and "__pycache__" not in p.parts
                   and p.relative_to(FIX).parts[0] != "budget"}   # M5-T2's own builder + drift test
        self.assertEqual(sorted(on_disk), sorted(built))
        for rel, body in built.items():
            self.assertEqual(on_disk[rel], body, rel)


if __name__ == "__main__":
    unittest.main()
