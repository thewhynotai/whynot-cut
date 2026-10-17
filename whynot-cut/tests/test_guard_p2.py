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
import shutil
import tempfile
import time
import unittest
from unittest import mock
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

    def test_abbreviated_lead_only_flags_are_still_lead_only(self):
        """T2.16 review (Minor 1): argparse expanded `--deliv` to `--delivered`, and the guard matched only the exact
        string. The CLI now refuses abbreviations (allow_abbrev=False); the guard treats any prefix, and `--flag=value`,
        as the flag too."""
        def run(cmd, agent):
            return hook(GUARD, {"tool_name": "Bash", "tool_input": {"command": cmd}, "cwd": str(self.root),
                                "agent_type": agent})[0]
        for cmd in ("reel handoff --deliv --video-id C1", "reel handoff --delivered=1 --video-id C1",
                    "reel --video-id C1 handoff --del", "reel verify --rec --verdict pass --video-id C1",
                    "reel verify --record=1 --verdict pass", "reel lock --rel", "reel settings --ini x",
                    "reel ae-probe --reco ok", "reel transcript-verify --b editor", "reel transcript-verify --by=editor",
                    # argparse keeps the LAST --by; the guard blocks when ANY occurrence is `editor`
                    "reel transcript-verify --by agent --by editor", "reel transcript-verify --by=agent --b editor",
                    "reel transcript-verify --by editor --by agent", "reel transcript-verify --by=agent --by=Editor",
                    "reel transcript-verify --by agent --by=agent --b 'editor'"):
            with self.subTest(cmd=cmd):
                self.assertEqual(run(cmd, "whynot-cut:premiere-builder"), 2)
        self.assertEqual(run("reel ref-style --app", "whynot-cut:qc-reviewer"), 2)
        self.assertEqual(run("reel doctor --fi", "whynot-cut:setup-doctor"), 2)
        for cmd in ("reel handoff --video-id C1", "reel verify --video-id C1", "reel transcript-verify --by agent",
                    "reel transcript-verify --by agent --by=agent --b agent",
                    "reel handoff --note delivered --video-id C1"):
            with self.subTest(allowed=cmd):
                self.assertEqual(run(cmd, "whynot-cut:premiere-builder"), 0)

    def test_option_value_is_the_last_occurrence_like_argparse(self):
        """Only `transcript-verify --by` reads an option's value (every other guarded flag is presence-only via
        has_opt, which already matches any occurrence). `opt_value` returns the last value, `opt_values` all of them."""
        import importlib.util
        spec = importlib.util.spec_from_file_location("guard_under_test", GUARD)
        g = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(g)
        argv = ["reel", "transcript-verify", "--by", "agent", "--b=editor"]
        self.assertEqual(g.opt_values(argv, "--by"), ["agent", "editor"])
        self.assertEqual(g.opt_value(argv, "--by"), "editor")
        self.assertIsNone(g.opt_value(["reel", "verify"], "--by"))

    def test_changelog_names_no_real_client_colour(self):
        self.assertNotIn("81613d", (SK / "CHANGELOG.md").read_text(encoding="utf-8").lower())


def _load_guard():
    import importlib.util
    spec = importlib.util.spec_from_file_location("guard_g1", GUARD)
    g = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(g)
    return g


class TestGuardBackslashPathsOffWindows(unittest.TestCase):
    r"""Gate 3 Mac full run (38847096252): on macOS/Linux `Path("data\Raw\x")` is ONE file name, so PowerShell
    (pwsh, or Claude Code's PowerShell tool) commands with Windows-style relative paths reached a client's data/ and
    assets/ unchecked, while PowerShell on macOS treats `\` as a separator and would delete data/Raw/x. Off Windows
    the guard checks the `/` form too (it may block a harmless name with a literal backslash: safer)."""
    WIN_STYLE = "data" + chr(92) + "Raw" + chr(92) + "C0001.MP4"

    def setUp(self):
        self.g = _load_guard()

    def test_off_windows_a_backslash_path_is_also_checked_in_its_slash_form(self):
        with mock.patch.object(self.g, "IS_WIN", False):
            self.assertEqual(self.g.path_forms(self.WIN_STYLE), [self.WIN_STYLE, "data/Raw/C0001.MP4"])
            self.assertEqual(self.g.path_forms("data/Raw/C0001.MP4"), ["data/Raw/C0001.MP4"])

    def test_on_windows_the_path_is_checked_once(self):
        with mock.patch.object(self.g, "IS_WIN", True):
            self.assertEqual(self.g.path_forms(self.WIN_STYLE), [self.WIN_STYLE])

    @unittest.skipIf(os.name == "nt", "Windows paths split on a backslash already")
    def test_off_windows_paths_of_names_the_real_file(self):
        cwd = Path(tempfile.mkdtemp(prefix="wnc-bs-"))
        self.addCleanup(shutil.rmtree, cwd, True)
        self.assertIn(cwd / "data" / "Raw" / "C0001.MP4", self.g.paths_of(self.WIN_STYLE, cwd))


class TestGuardSeesEveryEngineLaunch(ClientFixture):
    """Gate 2 fix round G1 (C1-C4, C6): the guard finds the reel subcommand whatever way the engine is started
    (interpreter flags, -m, a bare cli.py after cd, normalised paths, PowerShell `& $py`), reads it by position, keeps
    brace expansion bounded and blocks when checking a guarded call fails."""
    SUB = "whynot-cut:premiere-builder"

    def setUp(self):
        super().setUp()
        self.cli = (SK / "engine" / "reel" / "cli.py").as_posix()
        self.reel_dir = (SK / "engine" / "reel").as_posix()

    def call(self, cmd, agent=SUB, tool="Bash"):
        payload = {"tool_name": tool, "tool_input": {"command": cmd}, "cwd": str(self.root)}
        if agent:
            payload["agent_type"] = agent
        return hook(GUARD, payload)

    def blocked(self, cmds, agent=SUB, tool="Bash"):
        for c in cmds:
            with self.subTest(blocked=c, agent=agent, tool=tool):
                self.assertEqual(self.call(c, agent, tool)[0], 2, c)

    def allowed(self, cmds, agent=SUB, tool="Bash"):
        for c in cmds:
            with self.subTest(allowed=c, agent=agent, tool=tool):
                code, _, err = self.call(c, agent, tool)
                self.assertEqual(code, 0, f"{c}: {err}")

    def test_c1_interpreter_flags_before_the_script(self):
        cli = self.cli
        self.blocked([f'python -X utf8 "{cli}" handoff --delivered',
                      f'python -W ignore "{cli}" transcript-verify --by editor',
                      f'python -Xutf8 -W ignore::DeprecationWarning "{cli}" handoff --delivered',
                      f'python -BX utf8 "{cli}" verify --record --verdict pass',
                      f'py -3 -X utf8 "{cli}" approve-plan',
                      f'python "{cli}" --root "{self.root}" --video-id C1 handoff --delivered'])
        self.blocked([f'python -X utf8 "{cli}" ppro-build'], agent="whynot-cut:qc-reviewer")
        self.blocked([f'python -X utf8 "{cli}" ae-build', f'python -W ignore "{cli}" --video-id C1 mogrt-build'],
                     agent=None)
        self.allowed([f'python -X utf8 "{cli}" ae-build --extras'], agent=None)
        self.allowed([f'python -X utf8 "{cli}" handoff --video-id C1',
                      f'python -W ignore "{cli}" transcript-verify --by agent',
                      f'python -X utf8 "{cli}" range --in 00:01 --out 00:05 --label "x --delivered"'])

    def test_c2_other_launch_forms_are_reel(self):
        cli, rd = self.cli, self.reel_dir
        self.blocked([f'cd "{self.root}" && python -m reel.cli handoff --delivered',
                      f'cd "{rd}" && python -m cli handoff --delivered',
                      f'cd "{rd}" && python cli.py handoff --delivered',
                      f'cd "{rd}" && python ./cli.py verify --record --verdict pass',
                      f'cd "{rd}/lib" && python ../cli.py handoff --delivered',
                      f'python "{rd}/./cli.py" handoff --delivered',
                      f'python "{rd}/lib/../cli.py" handoff --delivered',
                      f'python -s -B -E -I "{cli}" handoff --delivered',
                      f'python -s -B -E -I -X utf8 -W ignore "{cli}" approve-plan',
                      'PY=python; "$PY" "$ROOT/engine/reel/cli.py" handoff --delivered',
                      f'"{cli}" handoff --delivered'])
        win = cli.replace("/", "\\")
        self.blocked(['& $py "$root\\engine\\reel\\cli.py" handoff --delivered',
                      '& "C:\\Py\\python.exe" -X utf8 "$root\\engine\\reel\\cli.py" verify --record --verdict pass',
                      f"& python '{win}' approve-plan",
                      f"Set-Location '{rd}'; python cli.py handoff --delivered"], tool="PowerShell")
        self.allowed([f'cd "{rd}" && python cli.py next', "python -m reel.cli next",
                      f'cat "{cli}" | grep -n delivered', f'grep -n "handoff --delivered" "{cli}"',
                      f'git log --oneline -- "{cli}"'])
        self.allowed(['& $py "$root\\engine\\reel\\cli.py" next'], tool="PowerShell")
        # not the engine, but the text names a gated step: a subagent is denied (backstop, deny by default); the lead
        # is not (the parser reads them as not the engine)
        named = [f'cd "{rd}" && python -m pytest cli.py handoff --delivered',
                 f'cd "{self.root}" && python -m cli handoff --delivered',       # not the engine folder
                 f'python -c "import sys" "{cli}" handoff --delivered',
                 "python other/cli.py handoff --delivered",
                 'echo "python -X utf8 cli.py handoff --delivered" && echo done']
        self.blocked(named)
        self.allowed(named, agent=None)
        named_ps = ['Write-Output "python -m reel.cli handoff --delivered"']
        self.blocked(named_ps, tool="PowerShell")
        self.allowed(named_ps, agent=None, tool="PowerShell")

    def test_c3_subcommand_found_by_position(self):
        self.blocked(["reel --root handoff handoff --delivered", "reel --video-id verify verify --record",
                      "reel --episode approve-plan --root x approve-plan"])
        self.allowed(["reel --root handoff next", "reel --video-id verify status"])

    def test_c3_global_value_options_match_the_real_parser(self):
        """GLOBAL_VALUE_OPTS is the reel parser's own top-level options that take a value (derived here from the
        parser cli.main builds, so a new global option fails this test until the guard knows it)."""
        import argparse
        from unittest import mock
        import cli

        class Built(Exception):
            pass

        def capture(self, *a, **kw):
            raise Built(self)

        with mock.patch.object(argparse.ArgumentParser, "parse_args", capture):
            with self.assertRaises(Built) as cm:
                cli.main(["next"])
        ap = cm.exception.args[0]
        opts = {s for act in ap._actions if act.option_strings and act.nargs != 0
                and not isinstance(act, (argparse._HelpAction, argparse._VersionAction))
                for s in act.option_strings}
        self.assertEqual(opts, set(_load_guard().GLOBAL_VALUE_OPTS))

    def test_c4_brace_expansion_is_bounded(self):
        g = _load_guard()
        word = "{a,b}" * 24 + "/x"
        t0 = time.perf_counter()
        with self.assertRaises(SystemExit) as cm:
            g.brace_expand(word)
        self.assertEqual(cm.exception.code, 2)
        self.assertLess(time.perf_counter() - t0, 1.0)
        deep = "{a," * 400 + "b" + "}" * 400                # nested: each level adds a group after substitution
        t0 = time.perf_counter()
        with self.assertRaises(SystemExit):
            g.brace_expand(deep)
        self.assertLess(time.perf_counter() - t0, 1.0)
        self.assertEqual(sorted(g.brace_expand("{assets,data}/x")), ["assets/x", "data/x"])
        self.assertEqual(len(g.brace_expand("{a,b}" * 6)), 64)
        t0 = time.perf_counter()
        code, _, err = self.call("rm -rf " + word)
        self.assertEqual(code, 2, err)
        self.assertIn("brace", err)
        self.assertLess(time.perf_counter() - t0, 5.0)
        self.blocked(["rm -rf {output,da}{ta,x}", "rm -rf {x,{y,data}}"])
        self.allowed(["ls {output,assets}", "echo {1,2}{3,4}"])

    def test_c6_a_crash_while_checking_blocks(self):
        import subprocess
        for p in ({"tool_name": "Bash", "tool_input": "rm -rf data", "cwd": str(self.root)},
                  {"tool_name": "Bash", "tool_input": {"command": ["rm", "-rf", "data"]}, "cwd": str(self.root)},
                  {"tool_name": "PowerShell", "tool_input": {"command": 7}, "cwd": str(self.root)},
                  {"tool_name": "Write", "tool_input": {"file_path": ["data/x"]}, "cwd": str(self.root)},
                  {"tool_name": "Bash", "tool_input": {"command": "ls"}, "cwd": 12}):
            with self.subTest(payload=p):
                code, _, err = hook(GUARD, p)
                self.assertEqual(code, 2, err)
                self.assertIn("could not check", err)
        for raw in ("not json", "[1, 2]"):                   # bad JSON: documented fail-open (exit 0)
            r = subprocess.run([_sys.executable, str(GUARD)], input=raw, capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, raw)
        self.assertEqual(hook(GUARD, {"tool_name": "Read", "tool_input": "x", "cwd": 3})[0], 0)   # not guarded

    def test_c6_the_guard_blocks_past_its_deadline(self):
        """A check that runs past DEADLINE blocks (exit 2) instead of letting the 10 s hook timeout pass the call."""
        import subprocess
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            drv = Path(d) / "drv.py"
            drv.write_text(
                "import importlib.util, io, json, sys, time\n"
                f"spec = importlib.util.spec_from_file_location('g', {str(GUARD)!r})\n"
                "g = importlib.util.module_from_spec(spec); spec.loader.exec_module(g)\n"
                "g.DEADLINE = 0.3\n"
                "g.check_bash = lambda *a: time.sleep(5)\n"
                "sys.stdin = io.StringIO(json.dumps({'tool_name': 'Bash', 'tool_input': {'command': 'ls'}}))\n"
                "g.main()\n", encoding="utf-8")
            t0 = time.perf_counter()
            r = subprocess.run([_sys.executable, str(drv)], capture_output=True, text=True)
            self.assertEqual(r.returncode, 2, r.stderr)
            self.assertIn("longer than", r.stderr)
            self.assertLess(time.perf_counter() - t0, 4.0)

    def test_no_false_positives_for_ordinary_commands(self):
        note = 'reel handoff --note "remember --delivered later" --video-id C1'
        self.blocked([note])                    # a subagent: the text names `handoff --delivered` (backstop)
        self.allowed([note], agent=None)        # the lead: --delivered is only the note's text
        self.allowed(["echo --delivered && grep -rn -- --record output | head",
                      "reel range --in 00:01 --out 00:03 --footage data/Raw/C0001.MP4",
                      "reel verify --video-id C1", "reel transcript-verify --by agent",
                      "reel --root . --video-id C1 next", "python -m pip --version"])


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

    def test_g1_unreadable_transcript_keeps_the_old_rule(self):
        """Gate 2 G1 (C5): a transcript that cannot be read (a directory, or its folder is gone: a moved transcript
        location) is no evidence of a quiet session -> the old rule (guard-ok missing or older than the previous
        start), never silence. A transcript file simply not written yet in an existing folder stays silent (T2.19)."""
        self.start("s1")
        (self.tdir / "s1.jsonl").mkdir()
        self.assertIn("protection may be OFF", self.start("s2"))
        mod = self.module()
        self.assertIsNone(mod.guarded_calls_since(str(self.tdir / "s1.jsonl"), time.time() - 5, 0, None))
        self.assertIsNone(mod.guarded_calls_since(str(self.tdir / "gone" / "x.jsonl"), time.time() - 5, 0, None))
        self.assertIs(mod.guarded_calls_since(str(self.tdir / "never.jsonl"), time.time() - 5, 0, None), False)

    def test_guarded_tools_match_the_hook_matcher(self):
        mod = self.module()
        hooks = json.loads((SK / "hooks/hooks.json").read_text(encoding="utf-8"))["hooks"]["PreToolUse"]
        guarded = {t for h in hooks if any("guard.py" in x["command"] for x in h["hooks"])
                   for t in re.split(r"\|", h["matcher"])}            # T3.4: one group per filter kind
        self.assertEqual(set(mod.GUARDED_TOOLS), guarded)
