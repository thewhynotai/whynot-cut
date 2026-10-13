"""3.0 Phase 3 T3.6 visibility: the plugin's settings.json (only keys a plugin may ship), the subagent status line script
and its command, and the optional editor output style (valid frontmatter, never forced).
Run:  tools/test.sh -p test_visibility.py
"""
import sys as _sys
_sys.dont_write_bytecode = True  # keep the plugin folder free of __pycache__
import _isolation  # noqa: F401,E402  G79: sandbox the engine home first (tests/_isolation.py)
import importlib.util
import json
import os
import re
import shutil
import subprocess
import tempfile
import time
import unittest
from pathlib import Path

SK = Path(__file__).resolve().parents[1]
SETTINGS = SK / "settings.json"
SCRIPT = SK / "hooks" / "subagent_status.py"
STYLE = SK / "output-styles" / "whynot-cut-editor.md"

# Keys a plugin's own settings.json may carry. Claude Code 2.1.295 keeps exactly these two and drops every other key
# (plugin loader: allow-list ["agent", "subagentStatusLine"]); documented at
# https://code.claude.com/docs/en/plugins-reference (plugin settings.json) and
# https://code.claude.com/docs/en/statusline (subagentStatusLine). `agent` is allowed by Claude Code but would make
# WhyNot Cut the main thread for every session, so this plugin must not ship it (tested below).
ALLOWED_PLUGIN_SETTINGS = {"agent", "subagentStatusLine"}
# Output style frontmatter, https://code.claude.com/docs/en/output-styles (the loader's strict schema).
ALLOWED_STYLE_KEYS = {"name", "description", "keep-coding-instructions", "force-for-plugin"}


def _load_script():
    spec = importlib.util.spec_from_file_location("subagent_status", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _run_script(payload, raw=None):
    data = raw if raw is not None else json.dumps(payload)
    r = subprocess.run([_sys.executable, "-I", str(SCRIPT)], input=data, capture_output=True, text=True, encoding="utf-8")
    return r.returncode, r.stdout, r.stderr


def _task(**kw):
    t = {"id": "t1", "agentType": "whynot-cut:story-editor", "status": "running", "description": "Edit C0239",
         "startTime": int((time.time() - 75) * 1000)}
    t.update(kw)
    return t


class TestPluginSettings(unittest.TestCase):
    def setUp(self):
        self.cfg = json.loads(SETTINGS.read_text(encoding="utf-8"))

    def test_only_keys_a_plugin_may_ship(self):
        self.assertIsInstance(self.cfg, dict)
        self.assertEqual(set(self.cfg) - ALLOWED_PLUGIN_SETTINGS, set())

    def test_does_not_force_the_main_agent(self):
        self.assertNotIn("agent", self.cfg)

    def test_subagent_status_line_is_a_command_for_the_hook_script(self):
        line = self.cfg["subagentStatusLine"]
        self.assertEqual(set(line), {"type", "command"})
        self.assertEqual(line["type"], "command")
        cmd = line["command"]
        for part in ("${CLAUDE_PLUGIN_ROOT}", "hooks/run_python.sh", "hooks/subagent_status.py", "plugin-root.json"):
            self.assertIn(part, cmd)
        self.assertTrue((SK / "hooks" / "run_python.sh").is_file())
        self.assertTrue(SCRIPT.is_file())

    @unittest.skipUnless(shutil.which("bash"), "bash not found")
    def test_command_finds_the_plugin_without_the_variable(self):
        """Claude Code does not expand ${CLAUDE_PLUGIN_ROOT} in a plugin's settings.json (found in the 2.1.295 loader):
        the command falls back to the root SessionStart records in ~/.whynot-cut/plugin-root.json."""
        cmd = self.cfg["subagentStatusLine"]["command"]
        payload = json.dumps({"columns": 100, "tasks": [_task()]})
        with tempfile.TemporaryDirectory() as home:
            env = {k: v for k, v in os.environ.items() if k != "CLAUDE_PLUGIN_ROOT"}
            env.update(HOME=home, USERPROFILE=home, WHYNOT_HOME=str(Path(home) / "eng"))
            run = lambda: subprocess.run(["bash", "-c", cmd], input=payload, capture_output=True, text=True,
                                         encoding="utf-8", env=env, timeout=60)
            r = run()                                       # no variable, no pointer: silent, exit 0
            self.assertEqual((r.returncode, r.stdout), (0, ""))
            (Path(home) / ".whynot-cut").mkdir()
            ptr = {"root": str(SK), "version": "x", "at": "x"}
            (Path(home) / ".whynot-cut" / "plugin-root.json").write_text(json.dumps(ptr, indent=1) + "\n", encoding="utf-8")
            r = run()                                       # pointer (Windows backslashes doubled in the JSON)
            self.assertEqual(r.returncode, 0, r.stderr)
            row = json.loads(r.stdout.strip().splitlines()[0])
            self.assertEqual(row["id"], "t1")
            self.assertIn("story-editor", row["content"])
            self.assertIn("C0239", row["content"])


class TestStatusScript(unittest.TestCase):
    def test_row_has_agent_stage_clip(self):
        code, out, _ = _run_script({"columns": 120, "tasks": [_task()]})
        self.assertEqual(code, 0)
        rows = [json.loads(line) for line in out.splitlines()]
        self.assertEqual([r["id"] for r in rows], ["t1"])
        parts = [p.strip() for p in rows[0]["content"].split("|")]
        self.assertEqual(parts[:3], ["story-editor", "story and plan", "C0239"])
        self.assertRegex(parts[-1], r"^\d+m\d\ds$")

    def test_every_agent_has_a_stage_word(self):
        mod = _load_script()
        agents = {p.stem for p in (SK / "agents").glob("*.md")}
        self.assertEqual(agents - set(mod.STAGE), set())
        self.assertEqual(set(mod.STAGE) - agents, set())

    def test_stage_words_are_plain_ascii_without_internals(self):
        mod = _load_script()
        for word in mod.STAGE.values():
            self.assertTrue(word.isascii(), word)
            self.assertNotRegex(word, r"(?i)gate|stage\s*\d|^\d")

    def test_other_agents_are_left_to_claude_code(self):
        tasks = [_task(id="a", agentType="general-purpose"), _task(id="b", agentType=None), _task(id="c", agentType="Explore")]
        self.assertEqual(_run_script({"tasks": tasks})[1], "")

    def test_clip_only_when_it_looks_like_a_clip_id(self):
        mod = _load_script()
        self.assertEqual(mod._clip({"description": "Plan EP02_C0239_MO now"}), "EP02_C0239_MO")
        self.assertEqual(mod._clip({"description": "transcribe CLIP_6EB37C"}), "CLIP_6EB37C")
        self.assertEqual(mod._clip({"description": "Edit the new clip for the doctor", "label": "ريلز"}), "")
        row = mod.row(_task(description="تحليل المقطع"), time.time())
        self.assertIn("| - |", row)

    def test_states_and_truncation(self):
        out = _run_script({"columns": 24, "tasks": [_task(status="completed")]})[1]
        self.assertLessEqual(len(json.loads(out)["content"]), 24)
        out = _run_script({"columns": 200, "tasks": [_task(status="failed")]})[1]
        self.assertIn("| failed |", json.loads(out)["content"])

    def test_never_fails(self):
        for raw in ("", "not json", "[]", "null", '{"tasks": 5}', '{"tasks": [1, "x", {"id": 3}]}',
                    '{"columns": "wide", "tasks": [{"id": "z", "agentType": "whynot-cut:qc-reviewer", "startTime": "soon"}]}'):
            code, out, err = _run_script(None, raw=raw)
            self.assertEqual(code, 0, raw)
            self.assertEqual(err, "", raw)
            for line in out.splitlines():
                json.loads(line)

    def test_fast_and_stdlib_only(self):
        src = SCRIPT.read_text(encoding="utf-8")
        self.assertEqual(sorted(set(re.findall(r"^import (\w+)", src, re.M))), ["json", "re", "sys", "time"])
        t = time.time()
        _run_script({"tasks": [_task()]})
        self.assertLess(time.time() - t, 5)


class TestOutputStyle(unittest.TestCase):
    def setUp(self):
        text = STYLE.read_text(encoding="utf-8")
        self.assertTrue(text.startswith("---\n"))
        head, self.body = text[4:].split("\n---\n", 1)
        self.fm = {}
        for line in head.splitlines():
            key, _, val = line.partition(":")
            self.fm[key.strip()] = val.strip().strip('"')

    def test_frontmatter_keys_and_values(self):
        self.assertEqual(set(self.fm) - ALLOWED_STYLE_KEYS, set())
        self.assertEqual(self.fm["name"], "whynot-cut-editor")
        self.assertEqual(self.fm["name"], STYLE.stem)
        self.assertTrue(self.fm["description"])
        self.assertIn(self.fm.get("keep-coding-instructions"), ("true", "false"))

    def test_not_forced_on_anyone(self):
        self.assertNotIn("force-for-plugin", self.fm)

    def test_carries_the_three_report_parts_and_the_rtl_rule(self):
        for part in ("**Verified", "**Not verified", "**Needs you"):
            self.assertIn(part, self.body)
        self.assertRegex(self.body, r"(?i)own fenced code block")
        self.assertIn("Arabic", self.body)

    def test_three_verbs_and_no_internal_words(self):
        for verb in ("drop files", "say what you want", "approve the plan"):
            self.assertIn(verb, self.body)
        self.assertNotRegex(self.body.replace('"Gate 0/1/2"', ""), r"(?i)gate\s*\d")
        self.assertNotIn("Claude Code", self.body)

    def test_plugin_has_no_other_output_styles_to_force(self):
        self.assertEqual([p.name for p in (SK / "output-styles").iterdir()], ["whynot-cut-editor.md"])


if __name__ == "__main__":
    unittest.main()
