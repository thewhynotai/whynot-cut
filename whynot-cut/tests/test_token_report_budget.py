# SPDX-License-Identifier: GPL-3.0-or-later
# © 2026 The Why Not AI (thewhynot.ai)
"""Addendum M, M5-T2 (report-only at Gate 4): the budget section of `tools/token_report.py`.

Spec: docs/superpowers/specs/addendum-m/ADDENDUM-M-owner-requests-2026-10-16.md (M5.3 budgets, M5.5 M5-T2).
Cases: lane-4 work/task60/cases.md (A1-A8 evaluator, B9-B12 rows, C13 evidence) + premortem.md.
Fixtures: tests/fixtures/token_report/budget/ (built by make_budget_fixtures.py; synthetic, no real transcript).
The fixture runs' totals are hand-calculated in the builder's comments (r1 1,900,000, r2 2,100,000, r3 2,300,000 in
the M5.2 unit); the tests assert those numbers, never the tool's formula.
Run:  tools/test.sh -p test_token_report_budget.py
"""
import sys as _sys
_sys.dont_write_bytecode = True  # keep the plugin folder free of __pycache__
import _isolation  # noqa: F401,E402  G79: sandbox the engine home before anything else (see tests/_isolation.py)
import importlib.util
import io
import json
import shutil
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BUD = Path(__file__).resolve().parent / "fixtures" / "token_report" / "budget"
sys.path.insert(0, str(ROOT / "tools"))

import token_report as tr  # noqa: E402


def _load_builder():
    spec = importlib.util.spec_from_file_location("wnc_budget_fixtures", BUD / "make_budget_fixtures.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


BF = _load_builder()
MF = BF.MF
DATE = "2026-10-19"
TOOL_COMMIT = "0" * 40
PASSQ = {"status": "pass", "failed": [], "graders": 2}
C1 = "a" * 40


def budget(runs, **kw):
    """The budget report of a runs file path (or a runs dict, written to a temp file next to nothing)."""
    kw.setdefault("date", DATE)
    kw.setdefault("commit", TOOL_COMMIT)
    if isinstance(runs, dict):
        d = Path(tempfile.mkdtemp())
        try:
            p = d / "runs.json"
            p.write_text(json.dumps(runs), encoding="utf-8")
            return tr.build_budget_report(p, **kw)
        finally:
            shutil.rmtree(d, True)
    return tr.build_budget_report(Path(runs), **kw)


def row(run, w, status="complete", quality=PASSQ, commit=C1, lead="claude-opus-5-5", source="clean-run", **kw):
    """A minimal measured row for the pure evaluator."""
    r = {"run": run, "weighted_m52": w, "status": status, "quality": quality, "commit": commit, "lead_model": lead,
         "source": source, "partial": False, "unpriced": False, "messages": 10,
         "incomplete_reason": None if status == "complete" else "usage-limit"}
    r.update(kw)
    return r


def entry(run, folder, **kw):
    """A runs-file entry pointing at a committed fixture run folder (absolute path)."""
    e = {"mode": "single-clip", "run": run, "transcripts": [str(BUD / "single-clip" / folder / BF.PROJECT_DIR)],
         "status": "complete",
         "quality": [{"grader": g, "passed": True} for g in BF.GRADERS]}
    e.update(kw)
    return e


def doc(*entries, **kw):
    d = {"tool": "budget_runs", "version": 1, "commit": BF.COMMIT, "runs": list(entries)}
    d.update(kw)
    return d


# --- A. The evaluator -----------------------------------------------------------------------------------------------
class TestBudgets(unittest.TestCase):
    def test_a1_budgets_from_m53(self):
        self.assertEqual(tr.BUDGETS["single-clip"]["budget"], 2_500_000)
        self.assertEqual(tr.BUDGETS["single-clip"]["stretch"], 1_500_000)
        self.assertEqual(tr.BUDGETS["podcast-reel"]["budget"], 2_500_000)
        self.assertEqual(tr.BUDGETS["podcast-reel"]["stretch"], 1_500_000)
        self.assertEqual(tr.BUDGETS["motion"]["budget"], 3_500_000)
        self.assertIsNone(tr.BUDGETS["motion"]["stretch"])
        self.assertTrue(tr.BUDGETS["motion"]["placeholder"])
        self.assertFalse(tr.BUDGETS["single-clip"]["placeholder"])
        self.assertFalse(tr.BUDGETS["podcast-reel"]["placeholder"])
        self.assertEqual(tr.BUDGET_SLACK, 1.25)
        self.assertEqual(tr.MIN_RUNS, 3)

    def test_a1b_stretch_and_placeholder_are_printed_not_judged(self):
        # median 1.9M is over the 1.5M stretch: still a PASS (stretch is not judged)
        v = tr.budget_verdict("single-clip", [row("a", 1_900_000), row("b", 1_900_000), row("c", 1_900_000)])
        self.assertEqual(v["result"], "PASS")
        self.assertEqual(v["stretch"], 1_500_000)
        rep = budget(BF.HERE / "runs.json")
        text = tr.render_budget_summary(rep)
        md = tr.render_budget_md(rep)
        self.assertIn("stretch 1,500,000", text)
        self.assertIn("placeholder", text)            # motion's 3.5M is labelled a placeholder
        self.assertIn("placeholder", md)
        self.assertIn("1,500,000", md)


class TestEvaluatorBoundaries(unittest.TestCase):
    def v(self, *ws):
        return tr.budget_verdict("single-clip", [row(f"r{i + 1}", w) for i, w in enumerate(ws)])

    def test_a2_median_exactly_the_budget_passes(self):
        v = self.v(2_000_000, 2_500_000, 2_600_000)
        self.assertEqual(v["median"], 2_500_000)
        self.assertEqual(v["result"], "PASS", v["reasons"])

    def test_a2b_median_one_over_the_budget_fails(self):
        v = self.v(2_000_000, 2_500_001, 2_600_000)
        self.assertEqual(v["result"], "FAIL")
        self.assertTrue(any("median" in r for r in v["reasons"]), v["reasons"])

    def test_a2c_a_run_at_exactly_125_percent_passes(self):
        v = self.v(2_000_000, 2_100_000, 3_125_000)
        self.assertEqual(v["run_cap"], 3_125_000)
        self.assertEqual(v["result"], "PASS", v["reasons"])

    def test_a2d_a_run_one_over_125_percent_fails_and_is_named(self):
        v = self.v(2_000_000, 2_100_000, 3_125_001)
        self.assertEqual(v["result"], "FAIL")
        self.assertEqual(len(v["reasons"]), 1, v["reasons"])
        self.assertIn("r3", v["reasons"][0])
        self.assertIn("1.25", v["reasons"][0])

    def test_a2e_float_noise_at_the_boundary_is_not_a_fail(self):
        v = self.v(2_000_000, 2_500_000.0000001, 3_125_000.0000004)
        self.assertEqual(v["result"], "PASS", v["reasons"])

    def test_a2f_the_motion_placeholder_has_its_own_cap(self):
        v = tr.budget_verdict("motion", [row("m1", 3_500_000), row("m2", 3_500_000), row("m3", 4_375_000)])
        self.assertEqual(v["result"], "PASS", v["reasons"])
        self.assertTrue(v["placeholder"])
        v = tr.budget_verdict("motion", [row("m1", 3_500_000), row("m2", 3_500_000), row("m3", 4_375_001)])
        self.assertEqual(v["result"], "FAIL")


class TestFixtureRuns(unittest.TestCase):
    def test_a3_the_plain_fixture_passes(self):
        rep = budget(BF.HERE / "runs.json")
        m = rep["modes"]["single-clip"]
        v = m["verdict"]
        self.assertEqual(v["result"], "PASS", v["reasons"])
        got = {r["run"]: r["weighted_m52"] for r in m["runs"]}
        self.assertEqual(sorted(got), ["r1", "r2", "r3"])
        self.assertAlmostEqual(got["r1"], 1_900_000, places=3)       # hand-calculated in the builder
        self.assertAlmostEqual(got["r2"], 2_100_000, places=3)
        self.assertAlmostEqual(got["r3"], 2_300_000, places=3)
        self.assertAlmostEqual(v["median"], 2_100_000, places=3)
        self.assertAlmostEqual(v["max"], 2_300_000, places=3)

    def test_a3b_the_planted_over_budget_run_fails_with_the_run_named(self):
        rep = budget(BF.HERE / "runs-planted.json")
        v = rep["modes"]["single-clip"]["verdict"]
        self.assertEqual(v["result"], "FAIL")
        planted = [r for r in rep["modes"]["single-clip"]["runs"] if r["run"] == "r2x3"][0]
        self.assertAlmostEqual(planted["weighted_m52"], 6_300_000, places=3)      # 3 x 2,100,000
        self.assertEqual(len(v["reasons"]), 1, v["reasons"])                     # median 2.3M still <= 2.5M
        self.assertIn("r2x3", v["reasons"][0])
        self.assertIn("3,125,000", v["reasons"][0])

    def test_a3c_the_planted_run_breaks_the_guard_rail(self):
        rep = budget(BF.HERE / "runs-planted.json")
        rows = {r["run"]: r for r in rep["modes"]["single-clip"]["runs"]}
        self.assertEqual(rows["r1"]["guard_rail"], "within 150,000")
        self.assertTrue(rows["r2x3"]["guard_rail"].startswith("over on "), rows["r2x3"]["guard_rail"])
        self.assertEqual(rows["r2x3"]["lead_context"]["max"], 3 * BF.TURN_CONTEXT)


class TestQualityAndCompleteness(unittest.TestCase):
    def test_a4_token_pass_with_a_quality_fail_is_a_fail(self):
        bad = {"status": "fail", "failed": ["qc-frames"], "graders": 2}
        v = tr.budget_verdict("single-clip", [row("r1", 1_000_000), row("r2", 1_000_000, quality=bad),
                                              row("r3", 1_000_000)])
        self.assertEqual(v["result"], "FAIL")
        self.assertEqual(v["reasons"], ["r2: quality (qc-frames failed)"])

    def test_a4b_quality_from_the_runs_file(self):
        e2 = entry("r2", "r2", quality=[{"grader": "qc-frames", "passed": False},
                                        {"grader": "plan-validation", "passed": True}])
        rep = budget(doc(entry("r1", "r1"), e2, entry("r3", "r3")))
        v = rep["modes"]["single-clip"]["verdict"]
        self.assertEqual(v["result"], "FAIL")
        self.assertEqual(v["reasons"], ["r2: quality (qc-frames failed)"])
        r2 = [r for r in rep["modes"]["single-clip"]["runs"] if r["run"] == "r2"][0]
        self.assertEqual(r2["quality"], {"status": "fail", "failed": ["qc-frames"], "graders": 2})

    def test_a5_missing_quality_is_a_fail_never_a_pass(self):
        for q in (None, []):
            v = tr.budget_verdict("single-clip", [row("r1", 1_000_000),
                                                  row("r2", 1_000_000, quality={"status": "not measured",
                                                                                "failed": [], "graders": 0}),
                                                  row("r3", 1_000_000)])
            self.assertEqual(v["result"], "FAIL")
            self.assertEqual(v["reasons"], ["r2: quality not measured"])
            e2 = entry("r2", "r2")
            if q is None:
                del e2["quality"]
            else:
                e2["quality"] = q
            rep = budget(doc(entry("r1", "r1"), e2, entry("r3", "r3")))
            v = rep["modes"]["single-clip"]["verdict"]
            self.assertEqual(v["result"], "FAIL", q)
            self.assertEqual(v["reasons"], ["r2: quality not measured"], q)
        e2 = entry("r2", "r2", quality=None)
        rep = budget(doc(entry("r1", "r1"), e2, entry("r3", "r3")))
        self.assertEqual(rep["modes"]["single-clip"]["verdict"]["reasons"], ["r2: quality not measured"])

    def test_a6_fewer_than_three_complete_runs_is_insufficient(self):
        v = tr.budget_verdict("single-clip", [row("r1", 1_000_000), row("r2", 9_000_000)])
        self.assertEqual(v["result"], "INSUFFICIENT")
        self.assertEqual(v["text"], "insufficient runs (n=2)")
        self.assertEqual(v["label"], "report-only, n=2")
        rep = budget(doc(entry("r1", "r1")))
        v = rep["modes"]["single-clip"]["verdict"]
        self.assertEqual(v["result"], "INSUFFICIENT")
        self.assertEqual(v["text"], "insufficient runs (n=1)")
        self.assertNotIn(v["result"], ("PASS", "FAIL"))

    def test_a7_an_incomplete_run_is_excluded_from_the_median_and_listed(self):
        v = tr.budget_verdict("single-clip", [row("r1", 2_400_000), row("r2", 2_400_000), row("r3", 2_600_000),
                                              row("r4", 10, status="incomplete")])
        self.assertEqual(v["median"], 2_400_000)        # with r4 counted it would be 2,400,000 too: check n
        self.assertEqual(v["n"], 3)
        self.assertEqual(v["excluded"], [{"run": "r4", "reason": "usage-limit"}])
        self.assertEqual(v["result"], "PASS", v["reasons"])
        # a cheap incomplete run never pulls the median under the budget
        v = tr.budget_verdict("single-clip", [row("r1", 2_600_000), row("r2", 2_600_000), row("r3", 2_000_000),
                                              row("r4", 10, status="incomplete"),
                                              row("r5", 10, status="incomplete")])
        self.assertEqual(v["median"], 2_600_000)
        self.assertEqual(v["result"], "FAIL")
        # from the runs file: r2 cut by a usage limit -> n=2, insufficient, r2 listed
        e2 = entry("r2", "r2", status="incomplete", incomplete_reason="usage-limit")
        del e2["quality"]
        rep = budget(doc(entry("r1", "r1"), e2, entry("r3", "r3")))
        v = rep["modes"]["single-clip"]["verdict"]
        self.assertEqual(v["text"], "insufficient runs (n=2)")
        self.assertEqual(v["excluded"], [{"run": "r2", "reason": "usage-limit"}])
        self.assertIn("r2", tr.render_budget_md(rep))

    def test_a8_every_verdict_is_report_only_and_not_binding(self):
        for rep in (budget(BF.HERE / "runs.json"), budget(BF.HERE / "runs-planted.json")):
            self.assertIs(rep["binding"], False)
            self.assertEqual(rep["binding_from"], "Gate 6")
            for mode, m in rep["modes"].items():
                self.assertIs(m["verdict"]["binding"], False, mode)
            text = tr.render_budget_summary(rep)
            self.assertIn("report-only", text)
            self.assertIn("binding from Gate 6", text)
            self.assertIn("report-only", tr.render_budget_md(rep))

    def test_a9_runs_from_different_commits_are_never_compared_silently(self):
        v = tr.budget_verdict("single-clip", [row("r1", 1_000_000), row("r2", 1_000_000, commit="b" * 40),
                                              row("r3", 1_000_000)])
        self.assertEqual(v["result"], "NOT COMPARABLE")
        v = tr.budget_verdict("single-clip", [row("r1", 1_000_000), row("r2", 1_000_000, lead="claude-sonnet-5-5"),
                                              row("r3", 1_000_000)])
        self.assertEqual(v["result"], "NOT COMPARABLE")

    def test_a10_unmeasurable_tokens_never_pass(self):
        for kw, word in (({"weighted_m52": None}, "tokens not measured"), ({"messages": 0}, "tokens not measured"),
                         ({"unpriced": True}, "unpriced"), ({"partial": True}, "partial")):
            rows = [row("r1", 1_000_000), row("r2", 1_000_000), row("r3", 1_000_000)]
            rows[1].update(kw)
            v = tr.budget_verdict("single-clip", rows)
            self.assertEqual(v["result"], "FAIL", kw)
            self.assertTrue(any(r.startswith("r2:") and word in r for r in v["reasons"]), (kw, v["reasons"]))

    def test_a11_modes_without_runs_are_not_measured_with_the_reason(self):
        rep = budget(BF.HERE / "runs.json")
        for mode in ("podcast-reel", "motion"):
            v = rep["modes"][mode]["verdict"]
            self.assertEqual(v["result"], "NOT MEASURED")
            self.assertEqual(v["not_measured_reason"], f"fixture: no recorded {mode} run")
        rep = budget(doc(entry("r1", "r1")))
        self.assertEqual(rep["modes"]["motion"]["verdict"]["not_measured_reason"], "no runs given")
        self.assertIn("not measured", tr.render_budget_md(rep))


# --- B. Rows --------------------------------------------------------------------------------------------------------
class TestRows(unittest.TestCase):
    FIELDS = ("mode", "run", "source", "status", "item", "weighted", "weighted_m52", "raw", "raw_total",
              "speech_minutes", "speech_source", "tokens_per_speech_minute", "lead_context", "guard_rail", "commit",
              "lead_model", "model_mix", "quality", "label")

    def test_b9_every_row_has_the_fields(self):
        rep = budget(BF.HERE / "runs.json")
        rows = rep["modes"]["single-clip"]["runs"]
        self.assertEqual(len(rows), 3)
        for r in rows:
            for f in self.FIELDS:
                self.assertIn(f, r, f)
            self.assertEqual(r["label"], "report-only, n=3")
            self.assertEqual(r["commit"], BF.COMMIT)
            self.assertEqual(r["lead_model"], "claude-opus-5-5")
            self.assertEqual(sorted(r["model_mix"]), ["claude-opus-5-5", "claude-sonnet-5-5"])
            self.assertAlmostEqual(sum(r["model_mix"].values()), 1.0, places=9)
            self.assertEqual(sorted(r["lead_context"]), ["guard_rail", "max", "median", "over", "p90", "turns"])
            self.assertEqual(r["item"], "item-01")
        r1 = rows[0]
        # raw tokens of r1, hand count: fresh 2,000+100+50+100+100+14x100+24,750 + sub 1,000 = 29,500
        self.assertEqual(r1["raw"]["fresh"], 29_500)
        self.assertEqual(r1["raw"]["output"], 1_000 + 500 + 800 + 2_000 + 1_000 + 14 * 20_000 + 20_000)
        self.assertEqual(r1["raw_total"], sum(r1["raw"].values()))
        self.assertEqual(r1["lead_context"]["max"], BF.TURN_CONTEXT)
        self.assertEqual(r1["guard_rail"], "within 150,000")
        # the Sonnet subagent: 123,000 of 1,900,000 in the M5.2 unit
        self.assertAlmostEqual(r1["model_mix_m52"]["claude-sonnet-5-5"], 123_000 / 1_900_000, places=9)

    def test_b10_speech_minutes_from_the_transcript_duration(self):
        rep = budget(BF.HERE / "runs.json")
        rows = {r["run"]: r for r in rep["modes"]["single-clip"]["runs"]}
        self.assertAlmostEqual(rows["r1"]["speech_minutes"], 54_300 / 60_000, places=9)
        self.assertAlmostEqual(rows["r1"]["tokens_per_speech_minute"], 1_900_000 / (54_300 / 60_000), places=3)
        self.assertEqual(rows["r1"]["speech_source"], "transcript")
        self.assertAlmostEqual(rows["r2"]["speech_minutes"], 1.0, places=9)
        self.assertAlmostEqual(rows["r2"]["tokens_per_speech_minute"], 2_100_000, places=3)
        self.assertIsNone(rows["r3"]["speech_minutes"])                 # no transcript: null, never a divide by 0
        self.assertIsNone(rows["r3"]["tokens_per_speech_minute"])
        self.assertEqual(rows["r3"]["speech_source"], "none")

    def test_b10b_a_transcript_without_a_duration_or_unreadable_is_null(self):
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp, True)
        (tmp / "zero.json").write_text(json.dumps({"meta": {"duration_ms": 0}}), encoding="utf-8")
        (tmp / "nometa.json").write_text(json.dumps({"segments": []}), encoding="utf-8")
        (tmp / "bad.json").write_text("{not json", encoding="utf-8")
        (tmp / "bool.json").write_text(json.dumps({"meta": {"duration_ms": True}}), encoding="utf-8")
        self.assertEqual(tr.speech_minutes(tmp / "zero.json"), (None, "no duration"))
        self.assertEqual(tr.speech_minutes(tmp / "nometa.json"), (None, "no duration"))
        self.assertEqual(tr.speech_minutes(tmp / "bool.json"), (None, "no duration"))
        self.assertEqual(tr.speech_minutes(tmp / "bad.json"), (None, "unreadable"))
        self.assertEqual(tr.speech_minutes(tmp / "missing.json"), (None, "unreadable"))
        self.assertEqual(tr.speech_minutes(None), (None, "none"))
        rep = budget(doc(entry("r1", "r1", speech_transcript=str(tmp / "zero.json"))))
        r = rep["modes"]["single-clip"]["runs"][0]
        self.assertIsNone(r["speech_minutes"])
        self.assertIsNone(r["tokens_per_speech_minute"])
        self.assertEqual(r["speech_source"], "no duration")

    def test_b11_rows_are_anonymised(self):
        rep = budget(BF.HERE / "runs-planted.json")
        outs = [json.dumps(rep, ensure_ascii=False), json.dumps(rep), tr.render_budget_summary(rep),
                tr.render_budget_md(rep)]
        for out in outs:
            low = out.lower()
            for planted in (MF.PLANTED_CLIENT, MF.PLANTED_PATH, MF.PLANTED_PROMPT, MF.PROJECT_DIR, "zorblax",
                            "quentaro", json.dumps(MF.PLANTED_PATH)[1:-1], str(BUD), "single-clip/r1"):
                self.assertNotIn(planted.lower(), low, planted)
        self.assertTrue(rep["anonymised"])
        raw = budget(BF.HERE / "runs.json", raw_ids=True)
        self.assertFalse(raw["anonymised"])
        self.assertEqual(raw["modes"]["single-clip"]["runs"][0]["item"], BF.VIDEO_ID)

    def test_b12_deterministic_output(self):
        a, b = budget(BF.HERE / "runs-planted.json"), budget(BF.HERE / "runs-planted.json")
        self.assertEqual(json.dumps(a, sort_keys=True), json.dumps(b, sort_keys=True))
        self.assertEqual(tr.render_budget_md(a), tr.render_budget_md(b))
        self.assertEqual(tr.render_budget_summary(a), tr.render_budget_summary(b))
        # the runs file order does not change the report
        d = json.loads((BF.HERE / "runs.json").read_text(encoding="utf-8"))
        for e in d["runs"]:
            e["transcripts"] = [str(BF.HERE / t) for t in e["transcripts"]]
            if "speech_transcript" in e:
                e["speech_transcript"] = str(BF.HERE / e["speech_transcript"])
        fwd = budget(d)
        d["runs"].reverse()
        rev = budget(d)
        self.assertEqual(json.dumps(fwd, sort_keys=True), json.dumps(rev, sort_keys=True))

    def test_b13_baseline_rows_are_provisional_and_never_in_the_verdict(self):
        base = [entry(f"b{i}", "r2x3", source="baseline") for i in (1, 2)]
        for b in base:
            del b["quality"]
        rep = budget(doc(entry("r1", "r1"), entry("r2", "r2"), entry("r3", "r3"), *base))
        m = rep["modes"]["single-clip"]
        self.assertEqual(m["verdict"]["result"], "PASS", m["verdict"]["reasons"])
        self.assertEqual(m["verdict"]["n"], 3)
        self.assertEqual([r["run"] for r in m["baseline"]], ["b1", "b2"])
        for r in m["baseline"]:
            self.assertEqual(r["label"], "provisional, n=2")
        self.assertIn("provisional, n=2", tr.render_budget_md(rep))

    def test_b14_an_eval_run_and_an_item_filter(self):
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp, True)
        out = tmp / "collected"
        for case_run, folder in (("case-a/run-1", "r1"), ("case-a/run-2", "r2")):
            shutil.copytree(BUD / "single-clip" / folder / BF.PROJECT_DIR, out / case_run / "projects")
        (out / "manifest.json").write_text(json.dumps({"tool": "eval_transcripts", "runs": [
            {"case": "case-a", "run": "run-1", "status": "collected"},
            {"case": "case-a", "run": "run-2", "status": "collected"}]}), encoding="utf-8")
        e = entry("e1", "r1", transcripts=[str(out)], eval_run="case-a/run-2")
        rep = budget(doc(e))
        self.assertAlmostEqual(rep["modes"]["single-clip"]["runs"][0]["weighted_m52"], 2_100_000, places=3)
        # an eval folder with several runs needs eval_run; an unknown eval_run is refused
        with self.assertRaises(tr.BudgetError):
            budget(doc(entry("e1", "r1", transcripts=[str(out)])))
        with self.assertRaises(tr.BudgetError):
            budget(doc(entry("e1", "r1", transcripts=[str(out)], eval_run="case-a/run-9")))
        # an item the run never names: no usage -> tokens not measured, not a zero-cost pass
        rep = budget(doc(entry("r1", "r1", item="OTHER_C99"), entry("r2", "r2"), entry("r3", "r3")))
        r1 = rep["modes"]["single-clip"]["runs"][0]
        self.assertEqual(r1["messages"], 0)
        self.assertIn("r1: tokens not measured", rep["modes"]["single-clip"]["verdict"]["reasons"])


class TestRunsFileValidation(unittest.TestCase):
    def bad(self, d):
        with self.assertRaises(tr.BudgetError) as cm:
            budget(d)
        return cm.exception.errors

    def test_v1_bad_runs_files_are_refused_with_every_error(self):
        self.assertTrue(self.bad({"tool": "other", "version": 1, "runs": []}))
        self.assertTrue(self.bad(doc(entry("r1", "r1", mode="feature-film"))))
        self.assertTrue(self.bad(doc(entry("r1", "r1", status="done"))))
        self.assertTrue(self.bad(doc(entry("r1", "r1", status="incomplete"))))          # no reason
        self.assertTrue(self.bad(doc(entry("r1", "r1", status="incomplete", incomplete_reason="free text here"))))
        self.assertTrue(self.bad(doc(entry("r1", "r1"), entry("r1", "r2"))))              # duplicate run name
        self.assertTrue(self.bad(doc(entry("../x", "r1"))))
        self.assertTrue(self.bad(doc(entry("r1", "r1", transcripts=[]))))
        self.assertTrue(self.bad(doc(entry("r1", "r1", transcripts=[str(BUD / "nope")]))))
        self.assertTrue(self.bad(doc(entry("r1", "r1", quality=[{"grader": "a b/c", "passed": True}]))))
        self.assertTrue(self.bad(doc(entry("r1", "r1", quality=[{"grader": "qc", "passed": "yes"}]))))
        self.assertTrue(self.bad(doc(entry("r1", "r1", commit="not-a-sha"))))
        self.assertTrue(self.bad(doc(entry("r1", "r1", source="guess"))))
        self.assertTrue(self.bad(doc(entry("r1", "r1"), not_measured=[{"mode": "single-clip", "reason": "x"}])))
        errs = self.bad(doc(entry("r1", "r1", mode="x"), entry("r2", "r2", status="y")))
        self.assertGreaterEqual(len(errs), 2)

    def test_v2_cli_refuses_and_writes_nothing(self):
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp, True)
        runs = tmp / "runs.json"
        runs.write_text(json.dumps(doc(entry("r1", "r1", mode="x"))), encoding="utf-8")
        err = io.StringIO()
        with redirect_stderr(err), redirect_stdout(io.StringIO()):
            rc = tr.main(["--budget", str(runs), "--json", str(tmp / "o.json"), "--md", str(tmp / "o.md")])
        self.assertEqual(rc, 2)
        self.assertFalse((tmp / "o.json").exists())
        self.assertFalse((tmp / "o.md").exists())
        self.assertIn("mode", err.getvalue())
        with redirect_stderr(io.StringIO()), redirect_stdout(io.StringIO()):
            self.assertEqual(tr.main(["--budget", str(tmp / "missing.json")]), 2)
            self.assertEqual(tr.main(["--budget", str(BUD / "runs.json"), str(BUD)]), 2)   # no PATH with --budget


class TestCli(unittest.TestCase):
    def test_c1_cli_writes_json_and_markdown(self):
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp, True)
        out = io.StringIO()
        with redirect_stdout(out):
            rc = tr.main(["--budget", str(BUD / "runs-planted.json"), "--json", str(tmp / "b.json"),
                          "--md", str(tmp / "b.md"), "--date", DATE])
        self.assertEqual(rc, 0)
        rep = json.loads((tmp / "b.json").read_text(encoding="utf-8"))
        self.assertEqual(rep["section"], "budget")
        self.assertEqual(rep["modes"]["single-clip"]["verdict"]["result"], "FAIL")
        md = (tmp / "b.md").read_text(encoding="utf-8")
        self.assertTrue(md.startswith(tr.BUDGET_MD_HEADER.format(version=tr.VERSION)), md[:200])
        self.assertIn("single-clip: FAIL", out.getvalue())
        self.assertIn("report-only", out.getvalue())


# --- C. Evidence ----------------------------------------------------------------------------------------------------
class TestEvidence(unittest.TestCase):
    def test_c13_the_evidence_holds_a_tool_generated_block(self):
        ev = ROOT / "docs" / "superpowers" / "evidence" / "2026-10-19-m5-budget-report.md"
        text = ev.read_text(encoding="utf-8")
        self.assertIn(tr.BUDGET_MD_HEADER.format(version=tr.VERSION), text)
        self.assertIn(tr.BUDGET_MD_END, text)
        self.assertIn("report-only", text)
        self.assertIn("Not verified", text)


class TestBudgetFixturesHaveNoDrift(unittest.TestCase):
    def test_committed_budget_fixtures_equal_the_builder(self):
        built = BF.build()
        on_disk = {p.relative_to(BUD).as_posix(): p.read_text(encoding="utf-8")
                   for p in BUD.rglob("*") if p.is_file() and p.name != "make_budget_fixtures.py"
                   and "__pycache__" not in p.parts}
        self.assertEqual(sorted(on_disk), sorted(built))
        for rel, body in built.items():
            self.assertEqual(on_disk[rel], body, rel)


if __name__ == "__main__":
    unittest.main()
