"""3.0 Phase 2 T2.19: guard minors carried from the Phase 1 gate review — CRLF continuations (Bash and PowerShell),
an escaped `\\$'` that opens no ANSI-C quote, a continued line that starts with `#`, `$((1 << n))` arithmetic that
opens no heredoc, and no "protection may be OFF" warning after a session that only read or chatted.
Run:  tools/test.sh -k test_guard_p2
"""
import sys as _sys
_sys.dont_write_bytecode = True  # keep the plugin folder free of __pycache__
import _isolation  # noqa: F401,E402  G79: sandbox the engine home first (tests/_isolation.py)
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

    def test_r1_heredoc_opener_split_at_its_own_operator(self):
        """Fix round 1, M1: the heredoc's opener is cut at the matched `<<DELIM`, not at the first `<<` of the line (an
        arithmetic shift before it hid `bash`); the delimiter word itself is no command (`<<sh` feeds no shell)."""
        self.blocked("Bash", [f"echo $((1<<2)) && bash <<EOF{LF}rm -rf data{LF}EOF",
                              f"echo $((x << 1)); cat <<EOF | sh{LF}rm -rf data{LF}EOF",
                              f"ls output && bash <<EOF{LF}rm -rf data{LF}EOF"])
        self.allowed("Bash", [f"cat <<sh > output/x.md{LF}rm -rf data{LF}sh",
                              f"echo $((1<<2)) && cat <<EOF > output/x.md{LF}rm -rf data{LF}EOF"])

    def test_r1_powershell_lone_cr_ends_a_line(self):
        """Fix round 1, M5: PowerShell ends a statement at a lone CR too."""
        self.blocked("PowerShell", [f"Get-ChildItem data{CR}Remove-Item -Recurse data",
                                    f"Remove-Item {BT}{CR}-Recurse data"])
        self.allowed("PowerShell", [f"Get-ChildItem data{CR}Get-ChildItem output{CR}"])

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

    @staticmethod
    def module():
        import importlib.util
        spec = importlib.util.spec_from_file_location("session_context_t219", CTX)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod

    def test_r1_only_the_tail_written_since_the_start_is_read(self):
        """Fix round 1, I1: SessionStart records the transcript's size; the next start reads only what was written
        after it (a 100 MB resumed transcript cost 668 ms). The ~24 MB head here holds a Bash call that would count."""
        big = self.tdir / "s1.jsonl"
        later = time.time() + 600
        pad = json.dumps({"type": "user", "timestamp": _stamp(later), "message": {"role": "user", "content": "x" * 4000}})
        with open(big, "w", encoding="utf-8", newline="\n") as fh:
            fh.write((pad + "\n") * 6000 + _tool_line("Bash", later) + "\n")
        size = big.stat().st_size
        self.assertGreater(size, 20_000_000)
        self.assertNotIn("protection may be OFF", self.start("s1"))           # records (time, s1.jsonl, size)
        self.assertEqual((self.data / "last-session-start").read_text(encoding="utf-8").splitlines()[1:],
                         [str(big), str(size)])
        mod, since = self.module(), time.time() - 5
        self.assertIs(mod.guarded_calls_since(str(big), since, 0, None), True)          # the head would count ...
        t0 = time.perf_counter()
        self.assertIs(mod.guarded_calls_since(str(big), since, size, None), False)      # ... but is never read
        self.assertLess(time.perf_counter() - t0, 0.1)
        self.assertNotIn("protection may be OFF", self.start("s2"))           # guard-ok missing, nothing new in s1
        with open(big, "a", encoding="utf-8", newline="\n") as fh:
            fh.write(_tool_line("Edit", time.time()) + "\n")
        self.assertIs(mod.guarded_calls_since(str(big), since, size, None), True)       # the tail is read
        self.assertIs(mod.guarded_calls_since(str(big), since, size * 2, None), True)   # shrank/rewritten: from 0

    def test_r1_a_call_after_the_last_heartbeat_counts(self):
        """Fix round 1, M2: a guard that ran early in the session and then stopped is caught; a call before the beat
        (the guard saw it) is not."""
        self.start("s1")
        beat = time.time() + 30
        hb = self.data / "guard-ok"
        hb.write_text("1", encoding="utf-8")
        os.utime(hb, (beat, beat))
        self.transcript("s1", _tool_line("Bash", beat - 20))
        self.assertNotIn("protection may be OFF", self.start("s2"))
        self.transcript("s2", _tool_line("Bash", beat - 10), _tool_line("Write", beat + 90))
        self.assertIn("protection may be OFF", self.start("s3"))              # guard-ok is newer than s2's start

    def test_r1_unknown_transcript_format_keeps_the_old_rule(self):
        """Fix round 1, M4: lines written but no record this code knows (a changed format) -> the old rule (guard-ok
        missing or older than the previous start), never silence; a transcript with nothing new stays silent."""
        self.start("s1")
        (self.tdir / "s1.jsonl").write_text('{"kind": "event", "tool": "Bash"}\n', encoding="utf-8")
        self.assertIn("protection may be OFF", self.start("s2"))
        (self.tdir / "s2.jsonl").write_text("", encoding="utf-8")
        self.assertNotIn("protection may be OFF", self.start("s3"))

    def test_guarded_tools_match_the_hook_matcher(self):
        mod = self.module()
        hooks = json.loads((SK / "hooks/hooks.json").read_text(encoding="utf-8"))["hooks"]["PreToolUse"]
        guard = next(h for h in hooks if "guard.py" in h["hooks"][0]["command"])
        self.assertEqual(set(mod.GUARDED_TOOLS), set(re.split(r"\|", guard["matcher"])))
