# SPDX-License-Identifier: GPL-3.0-or-later
# © 2026 The Why Not AI (thewhynot.ai)
"""3.0 Phase 4 T4.3 hooks: the `reel rules` verb (--phrases lists the engine's preference vocabulary and only reads),
`reel plan`'s `client_rules`, and the guard (subagents may not
`rules --record` / `--add` / `--dismiss` / `--remove` in any spelling, nor write rules.json or revision-notes.json).
Goes in with the S1-T4.3 hunks (hooks/S1-T4.3: cli.py, guard.py); lane 2's T43 file, updated by builder B.
Run:  bash tools/test.sh -p test_t43_rules_hooks.py
"""
import sys as _sys
_sys.dont_write_bytecode = True  # keep the plugin folder free of __pycache__
import _isolation  # noqa: F401,E402  G79: sandbox the engine home first (tests/_isolation.py)
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SK = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SK / "engine" / "reel"))
sys.path.insert(0, str(SK / "tests"))

from lib import common  # noqa: E402
from lib.common import CLIENT_PROFILE_REL, read_json, write_json  # noqa: E402
from test_plugin import GUARD, ClientFixture, hook, isolated_env  # noqa: E402

CLI = SK / "engine/reel/cli.py"
UP = {"knob": "caption_size_px", "direction": "up"}
LOGO_END = {"topic": "logo_end", "area": "ending", "phrase": "logo_end"}      # a phrase of the engine's vocabulary


def reel(root, *argv, stdin: bytes | None = None):
    env = isolated_env()
    try:
        from lib import lead_steps                      # BL-15: the lead's token, as the guard issues it
    except ImportError:                                 # (a checkout before BL-15 has no lead tokens)
        lead_steps = None
    if lead_steps is not None:
        lead_steps.issue_for(["--root", str(root), *argv], env)
    r = subprocess.run([sys.executable, "-B", str(CLI), "--root", str(root), *argv], input=stdin,
                       capture_output=True, env=env)
    return r.returncode, r.stdout.decode("utf-8"), r.stderr.decode("utf-8", "replace")


def js(out: str) -> dict:
    return json.loads(out)


class TestVerb(unittest.TestCase):
    def setUp(self):
        self._tmp = Path(tempfile.mkdtemp())
        self.root = self._tmp / "عيادة test"
        for vid in ("C0001", "C0002"):
            (self.root / "output/projects" / vid).mkdir(parents=True)
        (self.root / "assets").mkdir()
        (self.root / "data/Raw").mkdir(parents=True)
        (self.root / CLIENT_PROFILE_REL).mkdir(parents=True)
        from test_plugin import mark_client
        mark_client(self.root)

    def tearDown(self):
        shutil.rmtree(self._tmp, ignore_errors=True)

    def send(self, vid, items):
        return reel(self.root, "--video-id", vid, "rules", "--record", "--from", "-",
                    stdin=json.dumps(items, ensure_ascii=False).encode("utf-8"))

    def test_h1_record_propose_add_list_remove(self):
        import cli
        self.assertIn("rules", cli.registered_commands())
        rc, out, err = self.send("C0001", [{"text": "الكابشن صغير", "intent": UP}])
        self.assertEqual(rc, 0, err)
        self.assertEqual(js(out)["added"], 1)
        self.assertEqual(self.send("C0002", [{"text": "captions too small", "intent": UP}])[0], 0)
        rc, out, err = reel(self.root, "rules", "--propose")
        self.assertEqual(rc, 0, err)
        props = js(out)["proposals"]
        self.assertEqual(len(props), 1)
        rc, out, err = reel(self.root, "rules", "--add", props[0]["id"], "--value", "80")
        self.assertEqual(rc, 0, err)
        self.assertEqual(read_json(self.root / CLIENT_PROFILE_REL / "style.json"), {"caption_size_px": 80})
        rc, out, _ = reel(self.root, "rules", "--list")
        self.assertEqual([r["id"] for r in js(out)["active"]], ["R1"])
        rc, out, err = reel(self.root, "rules", "--remove", "R1")
        self.assertEqual(rc, 0, err)
        self.assertEqual(read_json(self.root / CLIENT_PROFILE_REL / "style.json"), {})

    def test_h2_record_needs_from_and_a_refusal_writes_nothing(self):
        rc, out, err = reel(self.root, "--video-id", "C0001", "rules", "--record")
        self.assertNotEqual(rc, 0)
        self.assertIn("--from", out + err)
        rc, out, err = reel(self.root, "rules", "--add", "P-00000000")
        self.assertNotEqual(rc, 0)
        self.assertFalse((self.root / CLIENT_PROFILE_REL / "rules.json").exists())

    def test_h3_only_record_add_remove_take_the_writer_lease(self):
        import argparse
        import cli
        ns = lambda **k: argparse.Namespace(cmd="rules", **{"record": False, "add": None, "remove": None,  # noqa
                                                            "dismiss": None, "list": False, "propose": False,
                                                            "phrases": False, **k})
        self.assertFalse(cli.writes(ns()))
        self.assertFalse(cli.writes(ns(list=True)))
        self.assertFalse(cli.writes(ns(phrases=True)))
        self.assertTrue(cli.writes(ns(record=True)))
        self.assertTrue(cli.writes(ns(add="P-1")))
        self.assertTrue(cli.writes(ns(remove="R1")))
        self.assertTrue(cli.writes(ns(dismiss="P-1")))

    def test_h6_dismiss_through_the_cli(self):
        rc, out, err = self.send("C0001", [{"text": "always end on the logo", "scope": "standing",
                                            "intent": LOGO_END}])
        self.assertEqual(rc, 0, err)
        pid = js(reel(self.root, "rules", "--propose")[1])["proposals"][0]["id"]
        rc, out, err = reel(self.root, "rules", "--dismiss", pid)
        self.assertEqual(rc, 0, err)
        self.assertEqual(js(out)["dismissed"], pid)
        self.assertEqual(js(reel(self.root, "rules", "--propose")[1])["proposals"], [])
        rc, out, err = reel(self.root, "rules", "--dismiss", "P-00000000")
        self.assertNotEqual(rc, 0)

    def test_h4_two_modes_at_once_are_refused(self):
        rc, _out, _err = reel(self.root, "rules", "--list", "--remove", "R1")
        self.assertNotEqual(rc, 0)
        rc, _out, _err = reel(self.root, "rules", "--phrases", "--list")
        self.assertNotEqual(rc, 0)
        rc, _out, _err = reel(self.root, "rules", "--phrases", "--add", "P-1")
        self.assertNotEqual(rc, 0)

    def test_h7_phrases_lists_the_engines_vocabulary_and_writes_nothing(self):
        before = sorted(p.name for p in self.root.rglob("*"))
        rc, out, err = reel(self.root, "rules", "--phrases")
        self.assertEqual(rc, 0, err)
        vocab = js(out)
        doc = json.loads((SK / "config/defaults/preference-phrases.json").read_text(encoding="utf-8"))
        self.assertEqual(vocab, doc["areas"])                       # exactly the plugin's file, nothing else
        self.assertGreaterEqual(len(vocab), 17)
        self.assertEqual(sorted(vocab["music"]["no_music"]), ["ar", "en", "group"])
        self.assertEqual(sorted(p.name for p in self.root.rglob("*")), before)     # read-only: no file appeared
        # a client folder's own file with other phrases changes nothing
        write_json(self.root / CLIENT_PROFILE_REL / "preference-phrases.json",
                   {"schema": 1, "areas": {"music": {"calm": {"group": "mood", "en": "x", "ar": "y"}}}})
        rc, out, err = reel(self.root, "rules", "--phrases")
        self.assertEqual((rc, js(out)), (0, doc["areas"]))

    def test_h8_a_phrase_preference_end_to_end_through_the_cli(self):
        glass = {"topic": "glass_end", "area": "transitions", "phrase": "glass_end_only"}
        free = {"topic": "round_font", "area": "fonts"}
        for vid, text in (("C0001", "خلي الجلاس في الآخر بس"), ("C0002", "glass only at the end")):
            rc, out, err = self.send(vid, [{"text": text, "intent": glass}, {"text": "the round font", "intent": free}])
            self.assertEqual(rc, 0, err)
        rc, out, err = reel(self.root, "rules", "--propose")
        self.assertEqual(rc, 0, err)
        r = js(out)
        self.assertEqual([p["phrase"] for p in r["proposals"]], ["glass_end_only"])
        self.assertEqual([k for k in r if "hand" in k], [])          # no by-hand list (owner decision 2026-10-19)
        self.assertNotIn("round font", out)
        self.assertNotIn("glass only at the end", out)
        self.assertNotEqual(reel(self.root, "rules", "--propose", "--hand")[0], 0)   # there is no --hand
        rc, out, err = reel(self.root, "rules", "--add", r["proposals"][0]["id"])
        self.assertEqual(rc, 0, err)
        md = (self.root / CLIENT_PROFILE_REL / "notes.md").read_text(encoding="utf-8")
        self.assertIn("glass transition only at the end / جلاس في الآخر بس (preference only)", md)
        self.assertNotIn("glass only at the end", md)
        self.assertNotIn("round font", md)
        rc, out, err = self.send("C0001", [{"text": "x", "intent": {"topic": "t", "area": "music", "phrase": "not a phrase id"}}])
        self.assertNotEqual(rc, 0)                                  # a phrase is an id, never text

    def test_h5_value_and_replace_belong_to_add_and_null_is_no_value(self):
        for argv in (("rules", "--list", "--replace", "R1"), ("rules", "--propose", "--value", "80"),
                     ("rules", "--add", "P-1", "--value", "null")):
            with self.subTest(argv=argv):
                rc, out, err = reel(self.root, *argv)
                self.assertNotEqual(rc, 0, out)
        self.assertFalse((self.root / CLIENT_PROFILE_REL / "rules.json").exists())


class TestGuard(ClientFixture):
    AGENT = "whynot-cut:story-editor"

    def run_tool(self, cmd, agent=AGENT, tool="Bash"):
        p = {"tool_name": tool, "tool_input": {"command": cmd}, "cwd": str(self.root)}
        if agent:
            p["agent_type"] = agent
        return hook(GUARD, p)[0]

    def test_g1_subagents_may_not_add_or_remove_a_rule(self):
        for cmd in ("reel rules --root . --add P-12345678", "reel rules --root . --remove R1",
                    "reel rules --root . --dismiss P-12345678", "reel rules --root . --video-id C0001 --record --from -",
                    "reel rules --root . --video-id C0001 --rec --from x.json",
                    "reel rules --root . --ad P-1", "reel rules --root . --add=P-1",
                    "python engine/reel/cli.py rules --remove R2", "reel 'rul'es --root . --add P-1"):
            for tool in ("Bash", "PowerShell"):
                with self.subTest(cmd=cmd, tool=tool):
                    self.assertEqual(self.run_tool(cmd, tool=tool), 2)

    def test_g1b_subagents_may_not_write_the_rules_file_or_call_the_module(self):
        rules = "output/client_database/reel-profile/rules.json"
        for tool, inp in (("Write", {"file_path": str(self.root / rules), "content": "{}"}),
                          ("Edit", {"file_path": str(self.root / rules), "old_string": "a", "new_string": "b"}),
                          ("Bash", {"command": f"echo '{{}}' > {rules}"}),
                          ("PowerShell", {"command": f"Set-Content -Path {rules} -Value '{{}}'"}),
                          ("Bash", {"command": "reel py -c \"from lib import rules_loop; rules_loop.add('.', 'P-1')\""}),
                          ("Bash", {"command": "python -c 'import lib.rules_loop as r; r.remove(\".\", \"R1\")'"})):
            with self.subTest(tool=tool, inp=inp):
                p = {"tool_name": tool, "tool_input": inp, "cwd": str(self.root), "agent_type": self.AGENT}
                self.assertEqual(hook(GUARD, p)[0], 2)
        notes = "output/projects/C0001/01_analysis/revision-notes.json"
        for tool, inp in (("Write", {"file_path": str(self.root / notes), "content": "{}"}),
                          ("Edit", {"file_path": str(self.root / notes), "old_string": "a", "new_string": "b"}),
                          ("Bash", {"command": f"echo '{{}}' > {notes}"}),
                          ("Bash", {"command": "cd output/client_database/reel-profile && echo {} > rules.json"}),
                          ("Bash", {"command": "python -c \"from pathlib import Path; "
                                               "Path('output/client_database/reel-profile', 'rules.json').write_text('{}')\""}),
                          ("PowerShell", {"command": r"Set-Content -Path 01_analysis\revision-notes.json -Value '{}'"})):
            with self.subTest(tool=tool, inp=inp):
                p = {"tool_name": tool, "tool_input": inp, "cwd": str(self.root), "agent_type": self.AGENT}
                self.assertEqual(hook(GUARD, p)[0], 2)
        self.assertEqual(self.run_tool(f"cat {rules}"), 0)                 # reading them is fine
        self.assertEqual(self.run_tool(f"cat {notes}"), 0)
        style = "output/client_database/reference_style/editing-rules.json"   # another file, not the registry
        p = {"tool_name": "Write", "tool_input": {"file_path": str(self.root / style), "content": "{}"},
             "cwd": str(self.root), "agent_type": "whynot-cut:client-researcher"}
        self.assertEqual(hook(GUARD, p)[0], 0)

    def test_g1c_the_reviewers_held_out_guard_payloads(self):
        """Review 3b4ec0e P2-1: 25 payloads written by the reviewer (tests/fixtures/t43_heldout/guard25.json), the 11
        spellings that slipped through included. <ROOT> is this fixture's client folder."""
        held = json.loads((SK / "tests/fixtures/t43_heldout/guard25.json").read_text(encoding="utf-8"))
        self.assertEqual(len(held), 25)
        for item in held:
            ti = json.loads(json.dumps(item["tool_input"]).replace("<ROOT>", str(self.root).replace("\\", "\\\\")))
            p = {"tool_name": item["tool"], "tool_input": ti, "cwd": str(self.root)}
            if item.get("agent_type"):
                p["agent_type"] = item["agent_type"]
            with self.subTest(tool=item["tool"], tool_input=ti):
                self.assertEqual(hook(GUARD, p)[0], 2 if item["expect"] == "block" else 0)

    def test_g1d_ordinary_path_forms(self):
        """The executor's list: relative, ./, .., quoted, a cd then a relative name, Windows backslashes."""
        for tool, cmd in (("Bash", "echo {} > ./output/client_database/reel-profile/rules.json"),
                          ("Bash", "cd output/client_database/reel-profile && echo {} > rules.json"),
                          ("Bash", "cd output/projects/C0001/01_analysis && echo {} > ../01_analysis/revision-notes.json"),
                          ("Bash", 'echo {} > "output/client_database/reel-profile/rules.json"'),
                          ("Bash", "cp x.json 'output/projects/C0001/01_analysis/revision-notes.json'"),
                          ("PowerShell", r"Set-Content -Path .\output\client_database\reel-profile\rules.json -Value '{}'"),
                          ("PowerShell", r"Copy-Item x.json -Destination output\projects\C0001\01_analysis\revision-notes.json"),
                          ("Bash", "f=rules; echo {} > output/client_database/reel-profile/$f.json")):
            with self.subTest(tool=tool, cmd=cmd):
                self.assertEqual(self.run_tool(cmd, tool=tool), 2)

    def test_g2_reading_stays_open_and_the_lead_may_record_add_dismiss_remove(self):
        for cmd in ("reel rules --root . --propose", "reel rules --root . --list", "reel rules --root . --phrases",
                    "rg -n 'rules --add' docs"):
            with self.subTest(cmd=cmd):
                self.assertEqual(self.run_tool(cmd), 0)
        for cmd in ("reel rules --root . --add P-1", "reel rules --root . --remove R1",
                    "reel rules --root . --dismiss P-1", "reel rules --root . --video-id C0001 --record --from x.json"):
            with self.subTest(lead=cmd):
                self.assertEqual(self.run_tool(cmd, agent=None), 0)


class TestPlanNamesTheRules(unittest.TestCase):
    """`reel plan` (the real CLI) lists the client rules its compiled plan applied."""

    def test_p1_plan_output_has_client_rules(self):
        import test_pipeline as T
        from lib.client_db import build
        from lib.discover import run_discovery
        from lib.media import preflight
        tmp = Path(tempfile.mkdtemp())
        try:
            root, p, _ = T.make_project(tmp)
            build(p, run_discovery(p)["inventory"])
            preflight(p, [root / "data/Raw/CLIP1.mov"])
            tc = T.TestPlanToXML()
            tc.p = p
            tc._semantic_stub()
            write_json(p.p("01_analysis/edit-decisions.json"), tc.decisions())
            common.set_context(root)
            from lib import rules_loop
            rules_loop.record(root, p.video_id, [{"text": "always bigger captions", "intent": UP},
                                                 {"text": "always end on the logo", "intent": LOGO_END}])
            for prop in sorted(rules_loop.propose(root)["proposals"], key=lambda x: x["knob"] is None):
                rules_loop.add(root, prop["id"])
            rc, out, err = reel(root, "--video-id", p.video_id, "plan")
            self.assertEqual(rc, 0, out + err)
            r = js(out)
            self.assertEqual([(x["id"], x["applied"]) for x in r["client_rules"]], [("R1", True), ("R2", "brief")])
            self.assertIn("71", r["client_rules"][0]["ar"])
            self.assertEqual((r["client_rules"][1]["ar"], r["client_rules"][1]["en"]),
                             ("النهاية على اللوجو", "end on the logo"))
        finally:
            common.set_context(None)
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
