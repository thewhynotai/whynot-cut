# SPDX-License-Identifier: GPL-3.0-or-later
# © 2026 The Why Not AI (thewhynot.ai)
"""3.0 Phase 4 Task 25 (R-4.3) call sites, committed by the executor with the cli.py / plan.py / ppro_build.py /
guard.py hunks and config/defaults/cut-proposals.json: `reel cut-proposals` proposes and `--accept` adds the chosen
ids to the plan's cut list (the plan must then be approved again); a subagent may never `--accept`; edit-plan.md gets
the "Proposed cuts" table only when proposals exist (the golden plan is unchanged); the shipped config equals the
engine's starting values. The plan side (a take cut whole, the table, the Premiere markers) sits behind the switch
`task25_plan_proposals` in safety.json, off by default: while off, the plan is byte-identical to before Task 25.
Ported 2026-10-20 onto BL-15: `cut-proposals --accept` is a LEAD_STEPS row, so the engine runs it only with the guard's
token for that exact call (the tests issue it as the guard would for the lead's plain call).
Run:  bash tools/test.sh -p test_cut_proposals_hooks.py
"""
import sys as _sys
_sys.dont_write_bytecode = True  # keep the plugin folder free of __pycache__
import _isolation  # noqa: F401,E402  G79: sandbox the engine home first (tests/_isolation.py)
import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

sys = _sys
SK = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SK / "engine" / "reel"))

from lib import common  # noqa: E402
from lib import lead_steps  # noqa: E402  BL-15: a lead-only step runs with the guard's token
from lib import cut_proposals as C  # noqa: E402
from lib.common import read_json, write_json  # noqa: E402
from lib.safety import switches  # noqa: E402
from test_plugin import GUARD, ClientFixture, hook  # noqa: E402

CLI = SK / "engine/reel/cli.py"


def env():
    from test_plugin import isolated_env
    return isolated_env()


class TestCli(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="t25hook_"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.addCleanup(common.set_context, None)
        from test_long_lived import golden_project
        self.root, self.p = golden_project(self.tmp)

    def reel(self, *argv, token=True):
        args = ["--root", str(self.root), "--video-id", self.p.video_id, *argv]
        e = env()
        if token:
            lead_steps.issue_for(args, e)          # the lead's approval (nothing for a step outside the table)
        r = subprocess.run([sys.executable, "-B", str(CLI), *args], capture_output=True, env=e)
        return r.returncode, r.stdout.decode("utf-8"), r.stderr.decode("utf-8", "replace")

    def test_classified_as_a_writer_and_listed(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location("reel_cli_t25", CLI)
        m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(m)
        self.assertIn("cut-proposals", m.CORE_WRITES)
        self.assertIn("cut-proposals", m.command_table())
        self.assertIn("cut-proposals", m.registered_commands())

    def test_propose_then_accept_then_the_plan_needs_a_new_approval(self):
        fx = json.loads((SK / "tests/fixtures/cut_proposals/eg_doctor.json").read_text(encoding="utf-8"))
        write_json(self.p.p("02_transcription/words.json"), {"meta": {"language": "ar"}, "words": fx["words"]})
        code, out, err = self.reel("cut-proposals")
        self.assertEqual(code, 0, out + err)
        doc = read_json(self.p.p(C.FILE))
        word = [x["id"] for x in doc["proposals"] if x["kind"] in C.WORD_KINDS]
        ed0 = self.p.p("01_analysis/edit-decisions.json").read_bytes()
        self.assertTrue(word)
        code, out, err = self.reel("cut-proposals", "--accept", word[0])
        self.assertEqual(code, 0, out + err)
        if len(word) > 1:                                  # ids also go space separated (nargs="+")
            code, out, err = self.reel("cut-proposals", "--accept", word[0], word[1])
            self.assertEqual(code, 0, out + err)
        self.assertNotEqual(self.p.p("01_analysis/edit-decisions.json").read_bytes(), ed0)
        code, out, err = self.reel("cut-proposals", "--accept", "CP-999")
        self.assertNotEqual(code, 0)

    def test_accept_without_the_lead_token_is_refused_and_writes_nothing(self):
        """BL-15: `--accept` is a lead step; listing the proposals is not."""
        fx = json.loads((SK / "tests/fixtures/cut_proposals/eg_doctor.json").read_text(encoding="utf-8"))
        write_json(self.p.p("02_transcription/words.json"), {"meta": {"language": "ar"}, "words": fx["words"]})
        code, out, err = self.reel("cut-proposals", token=False)
        self.assertEqual(code, 0, out + err)
        word = [x["id"] for x in read_json(self.p.p(C.FILE))["proposals"] if x["kind"] in C.WORD_KINDS]
        ed0 = self.p.p("01_analysis/edit-decisions.json").read_bytes()
        code, out, err = self.reel("cut-proposals", "--accept", word[0], token=False)
        self.assertEqual(code, 2, out + err)
        self.assertTrue(json.loads(out)["blocked"].startswith("الخطوة دي للمحرر بس"))
        self.assertEqual(self.p.p("01_analysis/edit-decisions.json").read_bytes(), ed0)

    def switch(self, on):
        write_json(self.root / common.CLIENT_PROFILE_REL / "safety.json", {"switches": {switches.TASK25_PLAN_PROPOSALS: on}})

    def plan_bytes(self):
        from lib.plan import compile_plan
        from test_long_lived import GOLDEN_FILES
        common.set_context(self.root)
        compile_plan(self.p)
        strip = {"generated", "engine_version"}
        out = {}
        for rel in GOLDEN_FILES:
            if rel.endswith(".json"):
                out[rel] = {k: v for k, v in read_json(self.p.p(rel)).items() if k not in strip}
            else:
                out[rel] = self.p.p(rel).read_bytes()
        return out

    def accepted_take(self, with_range):
        """An accepted proposal in cut_words: two neighbouring words, with or without the proposal's range_ms."""
        ws = read_json(self.p.p("02_transcription/words.json"))["words"]
        a, b = ws[3], ws[4]
        ed = read_json(self.p.p("01_analysis/edit-decisions.json"))
        entry = {"word_ids": [a["id"], b["id"]], "reason": "CP-001 retake: test", "by": "editor"}
        if with_range:
            entry["range_ms"] = [a["start_ms"] - 10, b["end_ms"] + 10]
        ed.setdefault("global", {})["cut_words"] = [entry]
        write_json(self.p.p("01_analysis/edit-decisions.json"), ed)

    def test_switch_off_plan_is_byte_identical_to_before_task25(self):
        """Off (no safety.json, or the switch false): proposals on disk and an accepted range_ms change nothing; the
        plan is the one today's code compiles (cut_words word by word, no table)."""
        self.accepted_take(with_range=False)
        before = self.plan_bytes()                       # today's input: no proposals, no range_ms
        C.propose(self.p)
        self.accepted_take(with_range=True)
        for on in (None, False, "true", 1):
            with self.subTest(switch=on):
                if on is not None:
                    self.switch(on)
                self.assertEqual(self.plan_bytes(), before)

    def test_switch_on_cuts_the_take_whole_and_shows_the_table(self):
        self.accepted_take(with_range=False)
        before = self.plan_bytes()
        C.propose(self.p)
        self.accepted_take(with_range=True)
        self.switch(True)
        after = self.plan_bytes()
        self.assertNotEqual(after, before)
        self.assertIn("## اقتراحات القص — Proposed cuts".encode("utf-8"), after["01_analysis/edit-plan.md"])

    def test_premiere_markers_only_with_the_switch_on(self):
        from lib.plan import compile_plan
        from lib.ppro_build import job_data
        common.set_context(self.root)
        compile_plan(self.p)
        before = job_data(self.p, overwrite=True)["markers"]          # no proposals: today's markers
        C.propose(self.p)
        compile_plan(self.p)
        self.assertEqual(job_data(self.p, overwrite=True)["markers"], before)   # switch off: exactly the same
        self.switch(True)
        cp = [m for m in job_data(self.p, overwrite=True)["markers"] if m["name"].startswith("CP-")]
        self.assertTrue(cp)
        # the build contract's marker keys only (build_project.schema.json): the bridge refuses anything else
        schema = json.loads((SK / "engine/reel/contract/build_project.schema.json").read_text(encoding="utf-8"))
        allowed = set(schema["$defs"]["data"]["properties"]["markers"]["items"]["properties"])
        self.assertTrue(all(set(m) <= allowed for m in cp), cp[0])

    def test_edit_plan_table_only_when_proposals_exist(self):
        from lib.plan import compile_plan
        self.switch(True)
        common.set_context(self.root)
        compile_plan(self.p)
        before = self.p.p("01_analysis/edit-plan.md").read_text(encoding="utf-8")
        self.assertNotIn("Proposed cuts", before)
        C.propose(self.p)
        compile_plan(self.p)
        after = self.p.p("01_analysis/edit-plan.md").read_text(encoding="utf-8")
        self.assertIn("## اقتراحات القص — Proposed cuts", after)


class TestRangeCut(unittest.TestCase):
    """plan.word_cut_ranges honours an accepted proposal's range_ms (one range: no slivers of silence between the
    words of a take, the breath after it goes too) when `whole` (the switch, read by the caller) is on; off, word by
    word. Fix round 2 (review 4fb97dd P2-1/P2-2): a range that no longer fits its words is an error and nothing of it
    is cut (test_t25_r2.TestWordCutRanges has the cases)."""
    WORDS = [{"id": i, "word": w, "start_ms": a, "end_ms": b} for i, (w, a, b) in enumerate(
        [("قال", 0, 300), ("أول", 400, 650), ("حاجة", 710, 1000), ("لازم", 1060, 1360), ("أول", 1900, 2150)], 1)]

    def test_switch_off_is_word_by_word(self):
        from lib.plan import word_cut_ranges
        r, _, err = word_cut_ranges(self.WORDS, [{"word_ids": [2, 3, 4], "range_ms": [360, 1860]}], 5000, whole=False)
        self.assertEqual((len(r), err), (3, []))

    def test_range_is_one_cut(self):
        from lib.plan import word_cut_ranges
        r, cut, err = word_cut_ranges(self.WORDS, [{"word_ids": [2, 3, 4], "range_ms": [360, 1860]}], 5000, whole=True)
        self.assertEqual((r, err), ([(360, 1860)], []))
        self.assertEqual([c["word_id"] for c in cut], [2, 3, 4])

    def test_unsafe_range_is_refused(self):
        from lib.plan import word_cut_ranges
        for bad in ([200, 1860], [360, 2000], [500, 1860], [360, 1200], "x", [5, 1]):
            with self.subTest(range_ms=bad):
                r, cut, err = word_cut_ranges(self.WORDS, [{"word_ids": [2, 3, 4], "range_ms": bad}], 5000,
                                              whole=True)
                self.assertEqual((r, cut, len(err)), ([], [], 1))

    def test_range_with_no_or_unknown_words_is_refused(self):
        """A range on no words, or on a word not in words.json: an older transcript, nothing cut."""
        from lib.plan import word_cut_ranges
        for ids in ([], [2, 99]):
            with self.subTest(word_ids=ids):
                r, cut, err = word_cut_ranges(self.WORDS, [{"word_ids": ids, "range_ms": [360, 1860]}], 5000,
                                              whole=True)
                self.assertEqual((r, cut), ([], []))
                self.assertTrue(err and "older transcript" in err[0], err)


class TestGuard(ClientFixture):
    def run_as(self, cmd, agent):
        payload = {"tool_name": "Bash", "tool_input": {"command": cmd}, "cwd": str(self.root)}
        if agent:
            payload["agent_type"] = agent
        return hook(GUARD, payload)[0]

    def test_the_refusal_says_what_to_do_instead(self):
        payload = {"tool_name": "Bash", "tool_input": {"command": "reel cut-proposals --accept CP-001"},
                   "cwd": str(self.root), "agent_type": "whynot-cut:story-editor"}
        code, _, err = hook(GUARD, payload)
        self.assertEqual(code, 2)
        self.assertIn("`cut-proposals --accept`, a step only the lead editor runs", err)    # BL-15's one table

    def test_only_the_lead_accepts(self):
        self.assertEqual(self.run_as("reel cut-proposals --accept CP-001", "whynot-cut:story-editor"), 2)
        self.assertEqual(self.run_as("reel cut-proposals --acc CP-001", "whynot-cut:story-editor"), 2)
        self.assertEqual(self.run_as("reel cut-proposals", "whynot-cut:story-editor"), 0)
        self.assertEqual(self.run_as("reel cut-proposals --accept CP-001", None), 0)


class TestShippedConfig(unittest.TestCase):
    def test_config_equals_the_engine_starting_values(self):
        cfg = json.loads((SK / "config/defaults/cut-proposals.json").read_text(encoding="utf-8"))
        self.assertEqual({k: v["value"] for k, v in cfg["thresholds"].items()}, C.DEFAULTS)
        self.assertTrue(all(v["basis"] for v in cfg["thresholds"].values()))
        self.assertEqual({k: v for k, v in cfg["fillers"].items() if k != "note"}, C.FILLERS)


if __name__ == "__main__":
    unittest.main()
