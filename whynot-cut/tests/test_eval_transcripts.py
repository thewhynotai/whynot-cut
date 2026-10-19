# SPDX-License-Identifier: GPL-3.0-or-later
# © 2026 The Why Not AI (thewhynot.ai)
"""Addendum M, M5-T1 (Q57-2): `tools/eval_transcripts.py` keeps each eval run's transcripts.

`claude plugin eval --output-dir` writes only aggregate-result.json and report.html (checked 2026-10-18 on the
existing p3 output folders and `claude plugin eval --help`). Each run's trace sits at `tracePath`
(<temp>/out/trace.jsonl) and its Claude Code transcripts under the run's own config folder (<temp>/config/projects/),
and the runner deletes that temp folder unless `--keep-temp` is passed. This tool copies them, never moves them, into
<out>/<case>/<arm>-run<k>/ with a manifest that tools/token_report.py reads per case and per run.
Every folder here is synthetic; no real eval output is read.
Run:  tools/test.sh -p test_eval_transcripts.py
"""
import sys as _sys
_sys.dont_write_bytecode = True  # keep the plugin folder free of __pycache__
import _isolation  # noqa: F401,E402  G79: sandbox the engine home before anything else (see tests/_isolation.py)
import io
import json
import os
import shutil
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))

import eval_transcripts as et  # noqa: E402
import token_report as tr  # noqa: E402


def rec(mid, fresh, cmd=None):
    content = [{"type": "tool_use", "id": "t_" + mid, "name": "Bash", "input": {"command": cmd}}] if cmd else \
        [{"type": "text", "text": "ok"}]
    return {"type": "assistant", "isSidechain": False, "message": {
        "id": mid, "model": "claude-opus-5-5", "content": content,
        "usage": {"input_tokens": fresh, "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0,
                  "output_tokens": 0}}}


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def make_temp_run(self, name, fresh, with_projects=True, with_trace=True):
        """A fake runner temp folder: out/trace.jsonl + config/projects/<proj>/<s>.jsonl (+ a subagent)."""
        t = self.tmp / "runner-temp" / name
        (t / "out").mkdir(parents=True)
        if with_trace:
            (t / "out" / "trace.jsonl").write_text(json.dumps(rec("m_" + name, fresh, "reel qc --video-id C_1")) + "\n",
                                                   encoding="utf-8")
        if with_projects:
            pj = t / "config" / "projects" / "D--sandbox-case"
            (pj / "s" / "subagents").mkdir(parents=True)
            (pj / "s.jsonl").write_text(json.dumps(rec("m_" + name, fresh, "reel qc --video-id C_1")) + "\n",
                                        encoding="utf-8")
            (pj / "s" / "subagents" / "agent-a.jsonl").write_text(json.dumps(rec("sub_" + name, 3)) + "\n",
                                                                  encoding="utf-8")
            (pj / "s" / "subagents" / "agent-a.meta.json").write_text('{"toolUseId": "t_x"}', encoding="utf-8")
            (t / "config" / "plugins").mkdir()
            (t / "config" / "plugins" / "settings.json").write_text("{}", encoding="utf-8")   # not copied
        return t / "out" / "trace.jsonl"

    def aggregate(self, cases):
        """cases: {name: {"with": [tracePath, ...], "without": [...]}} -> aggregate-result.json path."""
        doc = {"schemaVersion": 1, "cases": [
            {"name": n, "arms": {arm: [{"score": 1, "passed": True, "tracePath": str(p) if p else None}
                                       for p in paths] for arm, paths in arms.items()}}
            for n, arms in cases.items()]}
        f = self.tmp / "results" / "aggregate-result.json"
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(json.dumps(doc), encoding="utf-8")
        return f

    def run_main(self, argv):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            rc = et.main(argv)
        return rc, out.getvalue(), err.getvalue()


class TestCollect(Base):
    def test_copies_trace_and_transcripts_per_case_and_run(self):
        t1, t2 = self.make_temp_run("r1", 10), self.make_temp_run("r2", 20)
        t3 = self.make_temp_run("r3", 5)
        agg = self.aggregate({"edit-a": {"with": [t1, t2]}, "motion-b": {"with": [t3], "without": []}})
        out = self.tmp / "kept"
        rc, so, se = self.run_main([str(agg), "--out", str(out)])
        self.assertEqual(rc, 0, se)
        d = out / "edit-a" / "with-run1"
        self.assertTrue((d / "trace.jsonl").is_file())
        self.assertTrue((d / "projects" / "D--sandbox-case" / "s.jsonl").is_file())
        self.assertTrue((d / "projects" / "D--sandbox-case" / "s" / "subagents" / "agent-a.jsonl").is_file())
        self.assertTrue((d / "projects" / "D--sandbox-case" / "s" / "subagents" / "agent-a.meta.json").is_file())
        self.assertFalse((d / "plugins").exists())
        self.assertFalse(any(p.name == "settings.json" for p in out.rglob("*")))
        m = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(m["tool"], "eval_transcripts")
        self.assertEqual([(r["case"], r["run"], r["status"]) for r in m["runs"]],
                         [("edit-a", "with-run1", "collected"), ("edit-a", "with-run2", "collected"),
                          ("motion-b", "with-run1", "collected")])
        self.assertEqual(m["runs"][0]["files"], 4)
        self.assertEqual(m["source"], "aggregate-result.json")

    def test_sources_are_copied_never_moved(self):
        t1 = self.make_temp_run("r1", 10)
        before = sorted(str(p) for p in (self.tmp / "runner-temp").rglob("*"))
        agg = self.aggregate({"edit-a": {"with": [t1]}})
        self.assertEqual(self.run_main([str(agg), "--out", str(self.tmp / "kept")])[0], 0)
        self.assertEqual(sorted(str(p) for p in (self.tmp / "runner-temp").rglob("*")), before)

    def test_missing_temp_is_reported_with_the_keep_temp_hint(self):
        t1 = self.make_temp_run("r1", 10)
        gone = self.tmp / "runner-temp" / "deleted" / "out" / "trace.jsonl"
        agg = self.aggregate({"edit-a": {"with": [t1, gone, None]}})
        out = self.tmp / "kept"
        rc, so, se = self.run_main([str(agg), "--out", str(out)])
        self.assertEqual(rc, 3)
        self.assertIn("--keep-temp", se)
        m = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual([r["status"] for r in m["runs"]], ["collected", "missing", "missing"])
        self.assertEqual(m["runs"][1]["files"], 0)
        self.assertFalse((out / "edit-a" / "with-run2").exists())

    def test_trace_only_or_transcripts_only_still_collects(self):
        a = self.make_temp_run("a", 1, with_projects=False)
        b = self.make_temp_run("b", 1, with_trace=False)
        agg = self.aggregate({"c": {"with": [a, b]}})
        out = self.tmp / "kept"
        self.assertEqual(self.run_main([str(agg), "--out", str(out)])[0], 0)
        m = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual([r["files"] for r in m["runs"]], [1, 3])

    def test_unsafe_case_names_are_never_used_as_folders(self):
        t1 = self.make_temp_run("r1", 10)
        agg = self.aggregate({"../escape": {"with": [t1]}, "a/b": {"with": [t1]}, "": {"with": [t1]},
                              "ok-case": {"with": [t1]}})
        out = self.tmp / "kept"
        rc, so, se = self.run_main([str(agg), "--out", str(out)])
        self.assertEqual(rc, 3)
        self.assertFalse((self.tmp / "escape").exists())
        self.assertEqual(sorted(p.name for p in out.iterdir()), ["manifest.json", "ok-case"])
        m = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual([r["status"] for r in m["runs"]], ["unsafe-name", "unsafe-name", "unsafe-name",
                                                            "collected"])

    def test_refuses_a_non_empty_out_folder(self):
        t1 = self.make_temp_run("r1", 10)
        agg = self.aggregate({"c": {"with": [t1]}})
        out = self.tmp / "kept"
        out.mkdir()
        (out / "old.txt").write_text("keep me", encoding="utf-8")
        rc, so, se = self.run_main([str(agg), "--out", str(out)])
        self.assertEqual(rc, 2)
        self.assertIn("not empty", se)
        self.assertEqual([p.name for p in out.iterdir()], ["old.txt"])

    def test_an_empty_existing_out_folder_is_fine(self):
        t1 = self.make_temp_run("r1", 10)
        agg = self.aggregate({"c": {"with": [t1]}})
        out = self.tmp / "kept"
        out.mkdir()
        self.assertEqual(self.run_main([str(agg), "--out", str(out)])[0], 0)

    def test_bad_aggregate_is_refused(self):
        bad = self.tmp / "bad.json"
        bad.write_text("{not json", encoding="utf-8")
        rc, so, se = self.run_main([str(bad), "--out", str(self.tmp / "k")])
        self.assertEqual(rc, 2)
        self.assertFalse((self.tmp / "k").exists())
        rc, so, se = self.run_main([str(self.tmp / "nope.json"), "--out", str(self.tmp / "k")])
        self.assertEqual(rc, 2)
        bad.write_text('{"cases": 5}', encoding="utf-8")
        rc, so, se = self.run_main([str(bad), "--out", str(self.tmp / "k")])
        self.assertEqual(rc, 2)
        bad.write_text('{"cases": []}', encoding="utf-8")
        rc, so, se = self.run_main([str(bad), "--out", str(self.tmp / "k")])
        self.assertEqual(rc, 2)
        self.assertIn("no runs", se)

    def test_odd_run_entries_are_tolerated(self):
        t1 = self.make_temp_run("r1", 10)
        doc = {"cases": [{"name": "c", "arms": {"with": ["x", {"tracePath": 5}, {"tracePath": str(t1)}],
                                                "odd": "notalist"}}, "notadict", {"name": "d"}]}
        agg = self.tmp / "a.json"
        agg.write_text(json.dumps(doc), encoding="utf-8")
        out = self.tmp / "kept"
        rc, so, se = self.run_main([str(agg), "--out", str(out)])
        self.assertEqual(rc, 3)
        m = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual([(r["run"], r["status"]) for r in m["runs"]],
                         [("with-run1", "missing"), ("with-run2", "missing"), ("with-run3", "collected")])

    def test_links_inside_the_temp_folder_are_not_followed(self):
        t1 = self.make_temp_run("r1", 10)
        outside = self.tmp / "outside"
        outside.mkdir()
        (outside / "private.jsonl").write_text(json.dumps(rec("priv", 999)) + "\n", encoding="utf-8")
        link = t1.parent.parent / "config" / "projects" / "linked"
        try:
            if os.name == "nt":
                import _winapi
                _winapi.CreateJunction(str(outside), str(link))      # no shell (review efe8910 P3-8)
            else:
                os.symlink(outside, link, target_is_directory=True)
        except OSError as e:
            self.skipTest(f"cannot make a directory link here: {e}")
        agg = self.aggregate({"c": {"with": [t1]}})
        out = self.tmp / "kept"
        self.assertEqual(self.run_main([str(agg), "--out", str(out)])[0], 0)
        self.assertFalse(any(p.name == "private.jsonl" for p in out.rglob("*")))
        self.assertTrue((outside / "private.jsonl").is_file())

    def test_a_linked_trace_file_is_not_copied(self):
        t1 = self.make_temp_run("r1", 10, with_trace=False)
        real = self.tmp / "elsewhere.jsonl"
        real.write_text(json.dumps(rec("priv", 999)) + "\n", encoding="utf-8")
        try:
            os.symlink(real, t1)
        except OSError as e:
            self.skipTest(f"cannot make a file symlink here: {e}")
        agg = self.aggregate({"c": {"with": [t1]}})
        out = self.tmp / "kept"
        self.assertEqual(self.run_main([str(agg), "--out", str(out)])[0], 0)
        self.assertFalse((out / "c" / "with-run1" / "trace.jsonl").exists())

    def test_a_copy_error_is_recorded_and_the_manifest_still_written(self):
        """Review P3-7: a failing copy (disk full, a locked file) never ends in a traceback without manifest.json."""
        t1, t2 = self.make_temp_run("r1", 10), self.make_temp_run("r2", 20)
        agg = self.aggregate({"c": {"with": [t1, t2]}})
        out = self.tmp / "kept"
        real_copy = shutil.copyfile

        def flaky(src, dst, *a, **k):
            if "/runner-temp/r1/" in str(src).replace("\\", "/") and str(src).endswith("s.jsonl"):
                raise OSError(28, "No space left on device")
            return real_copy(src, dst, *a, **k)
        with mock.patch.object(et.shutil, "copyfile", flaky):
            rc, so, se = self.run_main([str(agg), "--out", str(out)])
        self.assertEqual(rc, 3)
        self.assertNotIn("Traceback", se)
        m = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual([r["status"] for r in m["runs"]], ["copy-failed", "collected"])
        self.assertIn("No space left", m["runs"][0]["reason"])
        self.assertEqual(m["runs"][1]["files"], 4)

    def test_case_names_that_differ_only_by_case_never_share_a_folder(self):
        """Review P3-7: `Clip` and `clip` (and `clip.`, which Windows trims) would land in one folder on Windows
        and default macOS; the second is refused, never mixed into the first."""
        t1, t2, t3 = self.make_temp_run("r1", 10), self.make_temp_run("r2", 20), self.make_temp_run("r3", 30)
        agg = self.aggregate({"Clip": {"with": [t1]}, "clip": {"with": [t2]}, "clip.": {"with": [t3]}})
        out = self.tmp / "kept"
        rc, so, se = self.run_main([str(agg), "--out", str(out)])
        self.assertEqual(rc, 3)
        m = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual([(r["case"], r["status"]) for r in m["runs"]],
                         [("Clip", "collected"), ("clip", "name-collision"), ("clip.", "unsafe-name")])
        r = tr.build_report([out], date="2026-10-18", commit="x")
        self.assertEqual(sorted(r["runs"]), ["Clip/with-run1"])
        self.assertEqual(r["runs"]["Clip/with-run1"]["raw"]["fresh"], 13)

    def test_a_trailing_dot_or_space_name_is_unsafe(self):
        self.assertIsNone(et.SAFE_NAME.fullmatch("clip."))
        self.assertIsNone(et.SAFE_NAME.fullmatch("clip "))
        self.assertIsNotNone(et.SAFE_NAME.fullmatch("clip.v2"))
        self.assertIsNone(tr.SAFE_NAME.fullmatch("clip."))

    def test_end_to_end_with_token_report(self):
        """Case 28: the collected folder is reported per case and per run (trace + transcript dedupe per run)."""
        t1, t2 = self.make_temp_run("r1", 10), self.make_temp_run("r2", 20)
        agg = self.aggregate({"edit-a": {"with": [t1, t2]}})
        out = self.tmp / "kept"
        self.assertEqual(self.run_main([str(agg), "--out", str(out)])[0], 0)
        r = tr.build_report([out], date="2026-10-18", commit="x", raw_ids=True)
        self.assertEqual(r["runs"]["edit-a/with-run1"]["raw"]["fresh"], 13)     # m 10 once + subagent 3
        self.assertEqual(r["runs"]["edit-a/with-run2"]["raw"]["fresh"], 23)
        self.assertEqual(r["by_item"]["C_1"]["by_stage"]["qc"]["raw"]["fresh"], 30)
        self.assertEqual(r["by_stage"]["unattributed-subagent"]["raw"]["fresh"], 6)


if __name__ == "__main__":
    unittest.main()
