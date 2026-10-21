# SPDX-License-Identifier: GPL-3.0-or-later
# © 2026 The Why Not AI (thewhynot.ai)
"""3.0 Phase 4 Task 67 (K-T7) call sites, committed by the executor with the cli.py / guard.py hunks (after the
Task 25 ones): `reel takes` lists the numbered take groups, `--drop/--keep` writes the plan's cut list, `--undo` goes
back one step; a subagent may list but never change takes.
Ported 2026-10-20 onto BL-15: `takes --drop/--keep/--undo` are LEAD_STEPS rows, so the engine runs them only with the
guard's token for that exact call (the tests issue it as the guard would for the lead's plain call).
Run:  bash tools/test.sh -p test_safety_takes_hooks.py
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
from lib.common import Paths, read_json, write_json  # noqa: E402
from test_plugin import GUARD, ClientFixture, hook  # noqa: E402

CLI = SK / "engine/reel/cli.py"


def env():
    from test_plugin import isolated_env
    return isolated_env()


class TestCli(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="kt7hook_"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.root = self.tmp / "د. تجربة Dr Test"
        for d in ("assets", "data/Raw"):
            (self.root / d).mkdir(parents=True)
        (self.root / ".whynot-client").write_text("{}", encoding="utf-8")
        self.p = Paths(self.root, "C0001")
        fx = json.loads((SK / "tests/fixtures/safety/kt7/ar.json").read_text(encoding="utf-8"))
        write_json(self.p.p("02_transcription/words.json"), {"meta": {"language": "ar"}, "words": fx["words"]})
        write_json(self.p.p("01_analysis/edit-decisions.json"), {"global": {}, "decisions": []})

    def reel(self, *argv, token=True):
        args = ["--root", str(self.root), "--video-id", "C0001", *argv]
        e = env()
        if token:
            lead_steps.issue_for(args, e)          # the lead's approval (nothing for a step outside the table)
        r = subprocess.run([sys.executable, "-B", str(CLI), *args], capture_output=True, env=e)
        return r.returncode, r.stdout.decode("utf-8"), r.stderr.decode("utf-8", "replace")

    def test_classified_as_a_writer_and_listed(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location("reel_cli_kt7", CLI)
        m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(m)
        self.assertIn("takes", m.CORE_WRITES)
        self.assertIn("takes", m.command_table())
        self.assertIn("takes", m.registered_commands())

    def test_list_drop_undo_round_trip(self):
        ed = self.p.p("01_analysis/edit-decisions.json")
        b0 = ed.read_bytes()
        code, out, err = self.reel("takes")
        self.assertEqual(code, 0, out + err)
        self.assertIn("نفس الجملة", out)
        code, out, err = self.reel("takes", "--drop", "2,4", "--keep", "5")
        self.assertEqual(code, 0, out + err)
        self.assertEqual(len(read_json(ed)["global"]["cut_words"]), 2)
        code, out, err = self.reel("takes", "--undo")
        self.assertEqual(code, 0, out + err)
        self.assertEqual(ed.read_bytes(), b0)
        code, out, err = self.reel("takes", "--drop", "99")
        self.assertNotEqual(code, 0)
        self.assertEqual(ed.read_bytes(), b0)

    def test_keep_alone_brings_a_dropped_take_back(self):
        ed = self.p.p("01_analysis/edit-decisions.json")
        self.assertEqual(self.reel("takes")[0], 0)
        code, out, err = self.reel("takes", "--drop", "2,4")
        self.assertEqual(code, 0, out + err)
        self.assertEqual(len(read_json(ed)["global"]["cut_words"]), 2)
        code, out, err = self.reel("takes", "--keep", "2")
        self.assertEqual(code, 0, out + err)
        self.assertEqual(len(read_json(ed)["global"]["cut_words"]), 1)

    def test_undo_goes_alone(self):
        ed = self.p.p("01_analysis/edit-decisions.json")
        self.assertEqual(self.reel("takes")[0], 0)
        self.assertEqual(self.reel("takes", "--drop", "2")[0], 0)
        b1 = ed.read_bytes()
        for extra in (["--drop", "4"], ["--keep", "2"]):
            with self.subTest(extra=extra):
                code, out, err = self.reel("takes", "--undo", *extra)
                self.assertNotEqual(code, 0, out + err)
                self.assertIn("--undo goes alone", out + err)
                self.assertEqual(ed.read_bytes(), b1)

    def test_changing_takes_without_the_lead_token_is_refused_and_writes_nothing(self):
        """BL-15: --drop, --keep and --undo are lead steps; the listing is not."""
        ed = self.p.p("01_analysis/edit-decisions.json")
        b0 = ed.read_bytes()
        code, out, err = self.reel("takes", token=False)
        self.assertEqual(code, 0, out + err)
        for argv in (["--drop", "2"], ["--keep", "5"], ["--undo"]):
            with self.subTest(argv=argv):
                code, out, err = self.reel("takes", *argv, token=False)
                self.assertEqual(code, 2, out + err)
                self.assertTrue(json.loads(out)["blocked"].startswith("الخطوة دي للمحرر بس"))
                self.assertEqual(ed.read_bytes(), b0)


class TestGuard(ClientFixture):
    def run_as(self, cmd, agent):
        payload = {"tool_name": "Bash", "tool_input": {"command": cmd}, "cwd": str(self.root)}
        if agent:
            payload["agent_type"] = agent
        return hook(GUARD, payload)[0]

    def test_skill_text_says_no_proposal_when_the_meaning_differs(self):
        text = (SK / "skills/story-craft/SKILL.md").read_text(encoding="utf-8")
        self.assertIn("When the takes differ\n  in meaning (a number or dose, a negation, a timing) no take is proposed", text)

    def test_the_refusal_names_the_lead_step(self):
        for cmd, step in (("reel takes --drop 4", "takes --drop"), ("reel takes --undo", "takes --undo")):
            payload = {"tool_name": "Bash", "tool_input": {"command": cmd}, "cwd": str(self.root),
                       "agent_type": "whynot-cut:story-editor"}
            with self.subTest(cmd=cmd):
                code, _, err = hook(GUARD, payload)
                self.assertEqual(code, 2)
                self.assertIn(f"`{step}`, a step only the lead editor runs", err)    # BL-15's one table

    def test_only_the_lead_changes_takes(self):
        for cmd in ("reel takes --drop 4", "reel takes --keep 5", "reel takes --undo", "reel takes --dro 4"):
            with self.subTest(cmd=cmd):
                self.assertEqual(self.run_as(cmd, "whynot-cut:story-editor"), 2)
                self.assertEqual(self.run_as(cmd, None), 0)
        self.assertEqual(self.run_as("reel takes", "whynot-cut:story-editor"), 0)


if __name__ == "__main__":
    unittest.main()
