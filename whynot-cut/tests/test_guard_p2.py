"""3.0 Phase 2 T2.19: guard minors carried from the Phase 1 gate review — CRLF continuations (Bash and PowerShell),
an escaped `\\$'` that opens no ANSI-C quote, a continued line that starts with `#`, `$((1 << n))` arithmetic that
opens no heredoc, and no "protection may be OFF" warning after a session that only read or chatted.
Run:  tools/test.sh -k test_guard_p2
"""
import sys as _sys
_sys.dont_write_bytecode = True  # keep the plugin folder free of __pycache__
import json
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path

from test_plugin import CTX, GUARD, SK, ClientFixture, hook

BS, CR, LF, BT = "\\", "\r", "\n", "`"


class TestGuardPhase2Minors(ClientFixture):
    def run_tool(self, tool, cmd):
        return hook(GUARD, {"tool_name": tool, "tool_input": {"command": cmd}, "cwd": str(self.root)})[0]

    def blocked(self, tool, cmds):
        for c in cmds:
            self.assertEqual(self.run_tool(tool, c), 2, repr(c))

    def allowed(self, tool, cmds):
        for c in cmds:
            self.assertEqual(self.run_tool(tool, c), 0, repr(c))

    def test_backslash_before_crlf_is_not_a_continuation(self):
        """bash reads `\\` + CR as an escaped CR; the LF still ends the command, so the next line runs on its own."""
        self.blocked("Bash", [f"ls output {BS}{CR}{LF}rm -rf data", f"ls output{BS}{CR}{LF}rm -rf data",
                              f"echo a{CR}{LF}rm -rf data{CR}{LF}"])
        self.allowed("Bash", [f"ls {BS}{LF} output", f"ls output {BS}{CR}{LF}ls data", f"ls output{CR}{LF}ls data"])

    def test_escaped_dollar_quote_opens_no_ansi_c_quote(self):
        """`\\$'x\\'` is a literal $ and the plain quote 'x\\' (closed by its second '), so the next line is a command."""
        self.blocked("Bash", [f"echo {BS}$'x{BS}'{LF}rm -rf data #'", f"echo {BS}$'x{BS}' # it's{LF}rm -rf data",
                              f"echo $$'x{BS}'{LF}rm -rf data #'"])
        self.blocked("Bash", [f"echo $'it{BS}'s' # x{LF}rm -rf data"])           # real $'..' (round 2, N6) still
        self.allowed("Bash", [f"echo $'a{BS}'b'{LF}ls data #'"])

    def test_continued_line_starting_with_hash_is_not_a_comment(self):
        """`ls output\\` + newline + `#; rm -rf data` is `ls output#; rm -rf data`: the `#` is inside a word."""
        self.blocked("Bash", [f"ls output{BS}{LF}#; rm -rf data", f"echo a{BS}{LF}#x && rm -rf data"])
        self.allowed("Bash", [f"ls output {BS}{LF}# a comment; rm -rf data", f"ls output {BS}{LF}#; rm -rf data",
                              f"{BS}{LF}# rm -rf data"])

    def test_arithmetic_shift_is_not_a_heredoc(self):
        """`<<` inside $(( )) or (( )) is a shift; the lines after it are commands, not a heredoc body."""
        self.blocked("Bash", [f"echo $((1 << bits)){LF}rm -rf data{LF}bits", f"echo $((1 << bits)){LF}rm -rf data",
                              f"(( x = 1 << bits )){LF}rm -rf data", f"if ((1<<n)); then ls; fi{LF}rm -rf data",
                              f"echo $(( (2+1) << bits )){LF}rm -rf data"])
        self.allowed("Bash", [f"cat <<EOF > output/n.md{LF}rm -rf data{LF}EOF",
                              f"echo $((1 << 2)); cat <<EOF > output/n.md{LF}rm -rf data{LF}EOF",
                              f"echo $((1 << bits)){LF}ls data"])

    def test_powershell_backtick_crlf_continues(self):
        """A backtick before CRLF continues the line in PowerShell (as before LF)."""
        self.blocked("PowerShell", [f"Remove-Item {BT}{CR}{LF}-Recurse data",
                                    f"Remove-Item -Recurse {BT}{CR}{LF}  -Force {BT}{CR}{LF}  data"])
        self.allowed("PowerShell", [f"Get-ChildItem {BT}{CR}{LF}-Path data -Recurse",
                                    f"Remove-Item {BT}{CR}{LF}-Recurse output/projects/C0001/cache",
                                    f"$s = @'{CR}{LF}Remove-Item data{CR}{LF}'@{CR}{LF}Write-Output $s"])

    def test_changelog_names_no_real_client_colour(self):
        self.assertNotIn("81613d", (SK / "CHANGELOG.md").read_text(encoding="utf-8").lower())


def _stamp(at: float) -> str:
    return datetime.fromtimestamp(at, timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def _tool_line(name: str, at: float) -> str:
    return json.dumps({"type": "assistant", "timestamp": _stamp(at), "message": {
        "role": "assistant", "content": [{"type": "tool_use", "id": "toolu_x", "name": name, "input": {}}]}})


class TestHeartbeatAfterReadOnlySessions(ClientFixture):
    """The SessionStart warning needs evidence: the previous session (its transcript or its subagents') made a tool call
    the guard inspects, after it started, and guard-ok is older than that start."""

    def setUp(self):
        super().setUp()
        self.data = Path(self.tmp.name) / "pdata"
        self.data.mkdir()
        self.tdir = Path(self.tmp.name) / "transcripts"
        self.tdir.mkdir()

    def start(self, name: str) -> str:
        """A SessionStart for the session whose transcript is <name>.jsonl; returns its additionalContext."""
        code, out, err = hook(CTX, {"cwd": str(self.root), "session_id": name, "source": "startup",
                                    "transcript_path": str(self.tdir / f"{name}.jsonl")},
                              {"CLAUDE_PLUGIN_DATA": str(self.data)})
        self.assertEqual(code, 0, err)
        return json.loads(out)["hookSpecificOutput"]["additionalContext"]

    def transcript(self, name: str, *lines: str, sub: str | None = None):
        f = self.tdir / name / "subagents" / f"agent-{sub}.jsonl" if sub else self.tdir / f"{name}.jsonl"
        f.parent.mkdir(parents=True, exist_ok=True)
        user = json.dumps({"type": "user", "timestamp": _stamp(time.time()), "message": {"role": "user", "content": "hi"}})
        f.write_text("\n".join([user, *lines]) + "\n", encoding="utf-8")

    def test_no_warning_after_a_read_only_session(self):
        now = time.time
        self.assertNotIn("protection may be OFF", self.start("s1"))           # new install
        self.transcript("s1", _tool_line("Read", now()), _tool_line("Grep", now()))
        self.assertNotIn("protection may be OFF", self.start("s2"))           # s1 only read: /clear, no alarm
        self.assertNotIn("protection may be OFF", self.start("s3"))           # s2 never wrote a transcript (closed)
        self.transcript("s3", _tool_line("Bash", now()))
        self.assertIn("protection may be OFF", self.start("s4"))              # s3 ran Bash, the guard never beat
        (self.data / "guard-ok").write_text("1", encoding="utf-8")
        self.transcript("s4", _tool_line("PowerShell", now()))
        self.assertNotIn("protection may be OFF", self.start("s5"))           # the guard ran in s4

    def test_only_calls_after_the_previous_start_count(self):
        """A resumed or compacted transcript holds earlier turns: a Bash call from before the previous start (when the
        guard did run) is no evidence about the session since."""
        old = time.time() - 2 * 86400
        self.start("s1")
        hb = self.data / "guard-ok"
        hb.write_text("1", encoding="utf-8")
        os.utime(hb, (old, old))
        self.transcript("s1", _tool_line("Edit", time.time() - 3600))
        self.assertNotIn("protection may be OFF", self.start("s2"))
        self.transcript("s2", _tool_line("Agent", time.time()))
        self.transcript("s2", _tool_line("Write", time.time()), sub="a1")       # a subagent's call counts
        self.assertIn("protection may be OFF", self.start("s3"))

    def test_guarded_tools_match_the_hook_matcher(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location("session_context_t219", CTX)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        hooks = json.loads((SK / "hooks/hooks.json").read_text(encoding="utf-8"))["hooks"]["PreToolUse"]
        guard = next(h for h in hooks if "guard.py" in h["hooks"][0]["command"])
        self.assertEqual(set(mod.GUARDED_TOOLS), set(re.split(r"\|", guard["matcher"])))
