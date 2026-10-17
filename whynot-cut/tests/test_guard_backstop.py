"""Guard backstop (3.0 P4 round 3): a subagent's Bash / PowerShell command that names a gated step (the word-plus-option
combinations of check_reel's gate rules) is denied by its text, however it is spelled or launched; only plain
read-only text searches may name one. The allowed subagent calls (transcript-verify --by agent, ref-style --record /
--adopt without --yes, needs-you, lock --status, verify, handoff) still pass. `reel py` naming the engine CLI or runpy
is denied for a subagent. A statement that starts with `(` is an engine call only after `&` / `.` (the lead too).
Brief: D:/ClaudeData/Temp/wnc-p4/psguard/backstop-brief.md
Run:  tools/test.sh -k guard_backstop
"""
import sys as _sys
_sys.dont_write_bytecode = True  # keep the plugin folder free of __pycache__
import _isolation  # noqa: F401,E402  G79: sandbox the engine home first (tests/_isolation.py)
import unittest

from test_plugin import GUARD, ClientFixture, hook

AGENT, OTHER = "whynot-cut:story-editor", "other-plugin:helper"

CASES = """
deny  | reel approve-plan --root . --video-id C0001
deny  | reel auto-approve --root . --video-id C0001
deny  | reel reels-select --root . --episode E1 --pick 1
deny  | reel lock --root . --release
deny  | reel handoff --root . --video-id C0001 --delivered
deny  | reel verify --root . --video-id C0001 --record pass
deny  | reel ref-style --root . --adopt C0001 --yes
deny  | reel transcript-verify --root . --video-id C0001 --by editor
deny  | python engine/reel/cli.py settings --init
deny  | & "D:\\wnc\\whynot-cut\\engine\\reel\\cli.py" lock --release
deny  | echo y | reel 'approve'-plan --root .
deny  | rg -n approve-plan docs | reel verify --rec pass
deny  | rg approve-plan docs; reel approve-plan
deny  | reel ve`rify --root . --record pass
deny  | &(Join-Path $r 'engine/reel/cli.py') approve-plan --root .
deny  | reel py -m reel.cli status
deny  | reel py -c "import runpy; runpy.run_module('cli')"
deny  | reel py D:/wnc/whynot-cut/engine/reel/cli.py status
allow | reel transcript-verify --root . --video-id C0001 --by agent
allow | reel ref-style --root . --record --by client-researcher
allow | reel ref-style --root . --adopt C0001
allow | reel needs-you --root .
allow | reel lock --root . --status
allow | reel verify --root . --video-id C0001
allow | reel handoff --root . --video-id C0001
allow | rg -n approve-plan whynot-cut/hooks
allow | grep -rn "handoff --delivered" docs | head -5
allow | Select-String -Path notes.md -Pattern 'verify --record'
allow | Get-Content notes.md | Select-String auto-approve
allow | cat notes.md | tail -3 | grep 'lock --release'
allow | reel plan --root . --video-id C0001
allow | reel py -c "import PIL, av, numpy"
allow | (Get-Content notes.txt) -eq 'ae-build'
"""
TABLE = [tuple(x.strip() for x in line.split("|", 1)) for line in CASES.strip().splitlines()]


class Base(ClientFixture):
    def run_tool(self, tool, cmd, agent=None):
        p = {"tool_name": tool, "tool_input": {"command": cmd}, "cwd": str(self.root)}
        if agent:
            p["agent_type"] = agent
        return hook(GUARD, p)[0]


class TestBackstopTable(Base):
    def test_table_for_subagents(self):
        for want, cmd in TABLE:
            for tool in ("Bash", "PowerShell"):
                for agent in ((AGENT, OTHER) if want == "deny" else (AGENT,)):
                    with self.subTest(want=want, tool=tool, agent=agent, cmd=cmd):
                        self.assertEqual(self.run_tool(tool, cmd, agent), 2 if want == "deny" else 0)


class TestParenthesisedRead(Base):
    def test_lead_paren_read_is_no_engine_call(self):
        for cmd in ("(Get-Content x) -match 'approve-plan'", "(Get-Content x) -like 'ae-build'"):
            with self.subTest(cmd=cmd):
                self.assertEqual(self.run_tool("PowerShell", cmd), 0)
        # a call operator before it still makes it the engine (extras rule for the lead)
        self.assertEqual(self.run_tool("PowerShell", "& (Get-Command reel) ae-build --root ."), 2)


if __name__ == "__main__":
    unittest.main()
