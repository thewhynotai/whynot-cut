"""BL-15 (Addendum L, L-G13): the guard's side of the lead-step approval token, and the real hook + engine together.

The guard writes a token only for the LEAD's own plain call of a lead-only step it allowed, and only when the session's
main transcript holds that exact call; never for a subagent, never for a payload fed to the guard by hand, never twice
for one tool call, never for a call it could not read exactly, never for another step. Nothing writes into a token
folder by hand (judged by the real path). The engine runs a lead-only step only with that token. Generic: a token is
present or absent, right or wrong (the guard's text rules have their own tests).
The guard, hooks.json and cli hunks arrive as executor patches (D:/ClaudeData/claude-api-lane/hooks/BL-15/); until
they are applied the classes that need them skip.
Run:  tools/test.sh -p test_lead_token_guard.py
"""
import sys as _sys
_sys.dont_write_bytecode = True  # keep the plugin folder free of __pycache__
import _isolation  # noqa: F401,E402  G79: sandbox the engine home first (tests/_isolation.py)
import json
import os
import re
import shutil
import statistics
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

from test_plugin import GUARD, hook, isolated_env, mark_client

SK = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SK / "engine" / "reel"))

from lib import lead_steps as ls  # noqa: E402

CLI = SK / "engine" / "reel" / "cli.py"
HOOKS = SK / "hooks" / "hooks.json"
SESSION = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
AGENT = "whynot-cut:story-editor"
GUARD_HAS_TOKENS = "lead_steps.hook_issue" in GUARD.read_text(encoding="utf-8")
HOOKS_COVER_TOKENS = "[Ll][Ee][Aa][Dd]-[Tt]" in HOOKS.read_text(encoding="utf-8")
ONBOARD = SK / "engine" / "reel" / "lib" / "onboard.py"
DOCTOR_CHECKS_TOKENS = "lead_steps.doctor_check" in ONBOARD.read_text(encoding="utf-8")


def load(path: Path, name: str):
    import importlib.util
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def known_commands() -> set:
    """The subcommands this checkout's CLI has (a table step whose CLI hunk has not landed yet is skipped)."""
    return set(load(CLI, "reel_cli_bl15g").registered_commands())


def step_argv(step: str, opts: tuple) -> list[str]:
    """One call of a table step with what it needs (values only where the option takes one)."""
    extra = {"--init": ["X"], "--adopt": ["C1"], "--record": [], "--pick": ["bold"], "--add": ["P1"],
             "--remove": ["R1"]}
    argv = [step]
    for o in opts:
        argv += [o] + extra.get(o, [])
    if step == "ae-probe":
        argv += ["ok"]
    if step == "approve-plan":
        argv += ["--by", "editor"]                  # required by the parser
    return argv


def record_call(transcript: Path, tool: str, command: str, sidechain: bool = False, session: str = SESSION) -> str:
    """Append one assistant tool call to a transcript the way Claude Code writes it (before PreToolUse runs)."""
    call_id = "toolu_" + os.urandom(12).hex()
    entry = {"type": "assistant", "isSidechain": sidechain, "sessionId": session, "uuid": os.urandom(8).hex(),
             "message": {"role": "assistant", "content": [
                 {"type": "text", "text": "running it"},
                 {"type": "tool_use", "id": call_id, "name": tool, "input": {"command": command, "description": "x"}}]}}
    with open(transcript, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return call_id


class Tmp(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="bl15g_"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.home = self.tmp / "home"
        self.home.mkdir()
        self.claude = self.tmp / "claude config"                    # Claude Code's own folder (CLAUDE_CONFIG_DIR)
        self.transcript = self.claude / "projects" / "D--work-client" / (SESSION + ".jsonl")
        self.transcript.parent.mkdir(parents=True)
        self.transcript.write_text("", encoding="utf-8")

    def tokens(self):
        d = self.home / "run" / "lead-tokens"
        return sorted(x.name for x in d.iterdir() if x.name.endswith(".tok")) if d.is_dir() else []

    def payload(self, command, tool="Bash", agent=None, recorded=True, cwd=None, **kw):
        p = {"tool_name": tool, "tool_input": {"command": command}, "cwd": str(cwd or self.tmp),
             "session_id": SESSION, "transcript_path": str(self.transcript)}
        if recorded:
            p["tool_use_id"] = record_call(self.transcript, tool, command, **kw)
        if agent:
            p["agent_type"] = agent
        return p


class TestPlainCall(unittest.TestCase):
    """What the guard reads as one plain engine call (generic categories, not spellings)."""

    def test_a_plain_call_gives_the_engine_arguments(self):
        for shell in ("bash", "powershell"):
            with self.subTest(shell=shell):
                self.assertEqual(ls.plain_call("reel approve-plan --by editor --note 'looks good'", shell),
                                 ["approve-plan", "--by", "editor", "--note", "looks good"])
        self.assertEqual(ls.plain_call("reel lock --release 2>&1 | tail -5", "bash"), ["lock", "--release"])
        self.assertEqual(ls.plain_call("reel lock --release 2>&1 | Select-Object -Last 5", "powershell"),
                         ["lock", "--release"])

    def test_python_and_the_engine_script(self):
        self.assertEqual(ls.plain_call('python "D:/w/whynot-cut/engine/reel/cli.py" verify --record', "bash"),
                         ["verify", "--record"])
        self.assertIsNone(ls.plain_call("python -X utf8 cli.py verify --record", "bash"))
        self.assertIsNone(ls.plain_call("python other.py verify --record", "bash"))

    def test_anything_else_is_not_plain(self):
        not_plain = ["cd x && reel approve-plan --by editor",          # chained, another folder
                     "reel approve-plan --by editor || tail -5",       # a second command on failure
                     "reel approve-plan --by $WHO",                     # a variable
                     "reel approve-plan --by \"$(whoami)\"",            # a substitution
                     "X=1 reel approve-plan --by editor",               # an environment prefix
                     "reel approve-plan --by editor > out.txt",         # a redirect
                     "reel approve-plan --by editor | tee log",         # a pipe into a writer
                     "echo y | reel approve-plan --by editor",          # the engine not first
                     "other approve-plan --by editor"]                  # not the engine
        for cmd in not_plain:
            for shell in ("bash", "powershell"):
                with self.subTest(cmd=cmd, shell=shell):
                    self.assertIsNone(ls.plain_call(cmd, shell))
        # Windows PowerShell 5.1 mangles a quoted argument that ends in a backslash on its way to the program
        self.assertIsNone(ls.plain_call("reel lock --release --root 'C:\\Clients\\X\\'", "powershell"))


class TestHookIssue(Tmp):
    """lead_steps.hook_issue, the guard's call: a token only for a real lead call of a lead-only step, once."""

    def issue(self, p):
        with mock.patch.dict(os.environ, {"WHYNOT_HOME": str(self.home), "CLAUDE_CONFIG_DIR": str(self.claude)}):
            return ls.hook_issue(p)

    def test_the_lead_call_gets_one_token(self):
        self.assertIsNotNone(self.issue(self.payload("reel lock --release")))
        self.assertEqual(len(self.tokens()), 1)

    def test_only_a_failed_engine_call_is_stamped_not_plain(self):
        """A lead grep that merely names a step leaves no "not-plain" mark, so the next refusal names the real cause;
        an engine call that is not plain does leave it (review r3 P3-3)."""
        seen = self.home / "run" / "lead-tokens" / ls.SEEN_FILE
        self.issue(self.payload("grep -n approve-plan notes.md"))
        self.assertFalse(seen.exists())
        self.issue(self.payload("cd x && reel approve-plan --by editor"))
        self.assertEqual(json.loads(seen.read_text(encoding="utf-8"))["result"], "not-plain")

    def test_a_transcript_outside_its_place_is_never_read(self):
        """Review 8bb853a: Claude Code writes a session's main transcript at exactly <projects>/<project>/<sid>.jsonl.
        The same file name anywhere deeper (<project>/memory/, a subagent folder) is never read as the transcript."""
        store = self.claude / "projects" / "D--work-client"
        for t in (store / "memory" / (SESSION + ".jsonl"), store / SESSION / "subagents" / (SESSION + ".jsonl")):
            with self.subTest(transcript=str(t.relative_to(self.claude))):
                t.parent.mkdir(parents=True, exist_ok=True)
                t.write_text("", encoding="utf-8")
                p = self.payload("reel lock --release")
                p["transcript_path"] = str(t)
                p["tool_use_id"] = record_call(t, "Bash", "reel lock --release")
                self.assertIsNone(self.issue(p))
        self.assertEqual(self.tokens(), [])
        self.assertIsNotNone(self.issue(self.payload("reel lock --release")))     # its real place still works

    def test_a_transcript_through_a_linked_project_folder_is_never_read(self):
        """The executor's r6 ruling: a link (symlink or junction) as the transcript's project folder is "no
        transcript", even when its real target is a real project folder."""
        link = self.claude / "projects" / "D--linked-client"
        try:
            if os.name == "nt":
                r = subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(self.transcript.parent)],
                                   capture_output=True)
                if r.returncode:
                    self.skipTest("junction not available")
            else:
                link.symlink_to(self.transcript.parent, target_is_directory=True)
        except OSError:
            self.skipTest("links not available")
        self.addCleanup(lambda: os.rmdir(link) if os.name == "nt" else link.unlink())
        p = self.payload("reel lock --release")
        p["transcript_path"] = str(link / self.transcript.name)
        self.assertIsNone(self.issue(p))
        self.assertEqual(self.tokens(), [])

    def test_no_token_for_a_subagent_or_another_step_or_tool(self):
        self.assertIsNone(self.issue(self.payload("reel lock --release", agent=AGENT)))
        self.assertIsNone(self.issue(self.payload("reel lock --status")))
        self.assertIsNone(self.issue({"tool_name": "Write", "tool_input": {"file_path": "x"}}))
        self.assertIsNone(self.issue({"tool_name": "Bash", "tool_input": None}))
        self.assertIsNone(self.issue("not a dict"))
        self.assertEqual(self.tokens(), [])

    def test_a_payload_fed_by_hand_gets_no_token(self):
        """A call that is not in the session's main transcript is not the lead's, whatever the payload says."""
        cases = {
            "not recorded": self.payload("reel lock --release", recorded=False),
            "recorded by a subagent": self.payload("reel lock --release", sidechain=True),
            "another command recorded": dict(self.payload("reel lock --status"),
                                             tool_input={"command": "reel lock --release"}),
            "another tool recorded": dict(self.payload("reel lock --release", tool="PowerShell"), tool_name="Bash"),
            "no transcript": dict(self.payload("reel lock --release"), transcript_path=""),
            "another session's transcript": dict(self.payload("reel lock --release"), session_id="other-session"),
            "a transcript outside Claude Code's store": self.forged_elsewhere("reel lock --release"),
        }
        for name, p in cases.items():
            with self.subTest(name):
                self.assertIsNone(self.issue(p))
        self.assertEqual(self.tokens(), [])

    def test_a_call_written_to_the_transcript_a_moment_late_still_counts(self):
        """Claude Code writes the transcript asynchronously: the call may land after the hook started."""
        import threading
        cmd, call_id = "reel lock --release", "toolu_" + os.urandom(12).hex()
        p = self.payload(cmd, recorded=False)
        p["tool_use_id"] = call_id

        def late():
            time.sleep(0.4)
            entry = {"type": "assistant", "isSidechain": False, "sessionId": SESSION,
                     "message": {"content": [{"type": "tool_use", "id": call_id, "name": "Bash",
                                              "input": {"command": cmd}}]}}
            with open(self.transcript, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry) + "\n")
        t = threading.Thread(target=late)
        t.start()
        try:
            self.assertIsNotNone(self.issue(p))
        finally:
            t.join(10)

    def test_a_teammate_gets_no_token(self):
        self.assertIsNone(self.issue(dict(self.payload("reel lock --release"), agent_id="teammate-1")))

    def forged_elsewhere(self, cmd):
        """A file named like the session's transcript, holding the call, but not in <claude config>/projects."""
        fake = self.tmp / "elsewhere" / (SESSION + ".jsonl")
        fake.parent.mkdir(exist_ok=True)
        fake.write_text("", encoding="utf-8")
        return dict(self.payload(cmd, recorded=False), transcript_path=str(fake),
                    tool_use_id=record_call(fake, "Bash", cmd))

    def test_one_tool_call_one_token(self):
        p = self.payload("reel lock --release")
        self.assertIsNotNone(self.issue(p))
        self.assertIsNone(self.issue(dict(p)))
        self.assertEqual(len(self.tokens()), 1)
        self.assertIsNotNone(self.issue(self.payload("reel lock --release")))   # a new call of the same step

    def test_hook_issue_latency(self):
        times = []
        for i in range(100):
            p = self.payload(f"reel verify --record --note n{i}")
            t0 = time.perf_counter()
            self.assertIsNotNone(self.issue(p))
            times.append(time.perf_counter() - t0)
        p95 = statistics.quantiles(times, n=20)[18]
        self.assertLess(p95, 0.020, f"hook_issue p95 {p95 * 1000:.1f} ms")


class Client(Tmp):
    def setUp(self):
        super().setUp()
        self.root = self.tmp / "client one"
        for d in ("assets", "data/Raw", "output"):
            (self.root / d).mkdir(parents=True)
        mark_client(self.root)
        self.env = {"WHYNOT_HOME": str(self.home), "CLAUDE_CODE_SESSION_ID": SESSION,
                    "CLAUDE_CONFIG_DIR": str(self.claude)}

    def guard(self, tool, ti, agent=None, recorded=None):
        """The real hook, the way Claude Code runs it: the lead's call is in the main transcript first."""
        if "command" in ti:
            p = self.payload(ti["command"], tool=tool, agent=agent, cwd=self.root,
                             recorded=(agent is None) if recorded is None else recorded)
            p["tool_input"] = ti
        else:
            p = {"tool_name": tool, "tool_input": ti, "cwd": str(self.root), "session_id": SESSION}
            if agent:
                p["agent_type"] = agent
        return hook(GUARD, p, env=self.env)

    def engine(self, argv):
        r = subprocess.run([sys.executable, "-B", str(CLI)] + argv, cwd=str(self.root), capture_output=True,
                           text=True, encoding="utf-8", env=isolated_env(self.env), stdin=subprocess.DEVNULL)
        return r.returncode, r.stdout, r.stderr


@unittest.skipUnless(GUARD_HAS_TOKENS, "guard.py has no BL-15 token support yet (executor patch)")
class TestGuardIssues(Client):
    def test_lead_plain_call_of_each_step_gets_one_matching_token(self):
        for step, opts in ls.LEAD_STEPS:
            argv = ["--root", str(self.root)] + step_argv(step, opts)
            cmd = "reel " + " ".join(f'"{a}"' for a in argv)
            with self.subTest(step=step, opts=opts):
                rc, _, err = self.guard("Bash", {"command": cmd})
                self.assertEqual(rc, 0, err)
                toks = self.tokens()
                self.assertEqual(len(toks), 1, toks)
                self.assertTrue(toks[0].startswith(ls.key(argv, str(self.root)) + "."))
                with mock.patch.dict(os.environ, {"CLAUDE_CODE_SESSION_ID": SESSION}):
                    self.assertTrue(ls.consume(argv, str(self.root), home=self.home))

    def test_powershell_lead_call_gets_a_token(self):
        rc, _, err = self.guard("PowerShell", {"command": f"reel lock --release --root '{self.root}'"})
        self.assertEqual(rc, 0, err)
        self.assertEqual(len(self.tokens()), 1)

    def test_subagent_never_gets_a_token(self):
        for step, opts in ls.LEAD_STEPS:
            cmd = "reel " + " ".join(step_argv(step, opts))
            with self.subTest(step=step, opts=opts):
                rc, _, _ = self.guard("Bash", {"command": cmd}, agent=AGENT, recorded=True)
                self.assertEqual(rc, 2)
        self.assertEqual(self.tokens(), [])

    def test_a_hand_fed_lead_payload_gets_no_token(self):
        rc, _, _ = self.guard("Bash", {"command": f'reel lock --release --root "{self.root}"'}, recorded=False)
        self.assertEqual(rc, 0)
        self.assertEqual(self.tokens(), [])

    def test_lead_call_that_is_not_plain_or_not_lead_only_gets_none(self):
        for cmd in (f'cd "{self.root}" && reel lock --release', "reel lock --status", "reel status"):
            with self.subTest(cmd=cmd):
                self.guard("Bash", {"command": cmd})
        self.assertEqual(self.tokens(), [])

    def test_nothing_writes_into_the_token_folder(self):
        d = self.home / "run" / "lead-tokens"
        for tool, key in (("Write", "file_path"), ("Edit", "file_path"), ("MultiEdit", "file_path"),
                          ("NotebookEdit", "notebook_path")):
            for agent in (None, AGENT):
                with self.subTest(tool=tool, agent=agent):
                    rc, _, err = self.guard(tool, {key: str(d / ("0" * 64 + "." + "1" * 32 + ".tok"))}, agent)
                    self.assertEqual(rc, 2)
                    self.assertIn("lead-tokens", err)

    def link_to_tokens(self) -> Path:
        d = self.home / "run" / "lead-tokens"
        d.mkdir(parents=True, exist_ok=True)
        link = self.tmp / "innocent"
        try:
            if os.name == "nt":
                r = subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(d)], capture_output=True)
                if r.returncode:
                    self.skipTest("junction not available")
            else:
                link.symlink_to(d, target_is_directory=True)
        except OSError:
            self.skipTest("links not available")
        self.addCleanup(lambda: os.rmdir(link) if os.name == "nt" else link.unlink())
        return link

    def test_the_token_folder_through_a_link_is_refused(self):
        """Judged by the real path: a write through a link whose name says nothing is refused, by every tool."""
        link = self.link_to_tokens()
        target = (link / "x.tok").as_posix()
        for tool, ti in (("Write", {"file_path": str(link / "x.tok"), "content": "{}"}),
                         ("Bash", {"command": f'cp notes.txt "{target}"'}),
                         ("Bash", {"command": f'echo x > "{target}"'}),
                         ("PowerShell", {"command": f"Set-Content -Path '{link / 'x.tok'}' -Value x"})):
            for agent in (None, AGENT):
                with self.subTest(tool=tool, agent=agent, cmd=ti):
                    rc, _, err = self.guard(tool, ti, agent, recorded=False)
                    self.assertEqual(rc, 2, err)

    def test_ordinary_globs_are_not_the_token_folder(self):
        """A glob that does not spell the folder's name is ordinary work, for the lead and for subagents."""
        (self.root / "output" / "tmp").mkdir(parents=True, exist_ok=True)
        (self.root / "output" / "tmp" / "a.txt").write_text("x", encoding="utf-8")
        for agent, tool, cmd in ((None, "Bash", "rm -f output/tmp/*"), (AGENT, "Bash", "ls output/*"),
                                 (AGENT, "Bash", "du -sh */"), (AGENT, "PowerShell", "Get-ChildItem output\\*"),
                                 (None, "Bash", "rm -f output/tmp/*token*"), (AGENT, "Bash", "ls *lead*")):
            with self.subTest(agent=agent, cmd=cmd):
                rc, _, err = self.guard(tool, {"command": cmd}, agent, recorded=False)
                self.assertEqual(rc, 0, err)

    def test_nobody_writes_claude_codes_transcripts(self):
        target = self.transcript
        for agent in (None, AGENT):
            for tool, ti in (("Write", {"file_path": str(target), "content": "{}"}),
                             ("Edit", {"file_path": str(target), "old_string": "a", "new_string": "b"}),
                             ("Bash", {"command": f'echo x >> "{target.as_posix()}"'})):
                with self.subTest(agent=agent, tool=tool):
                    rc, _, err = self.guard(tool, ti, agent, recorded=False)
                    self.assertEqual(rc, 2, err)
                    self.assertIn("transcript", err)

    def test_a_subagent_may_not_run_the_hook_script_by_hand(self):
        """Review r3 P2-1: a hand-run guard.py with a payload of its own is how a forged transcript line could become a
        token. A subagent's shell text naming the script, in any spelling the guard reads, is refused."""
        script = (SK / "hooks" / "guard.py").as_posix()
        runner = (SK / "hooks" / "run_python.sh").as_posix()
        for tool, cmd in (("Bash", f'python "{script}" < payload.json'),
                          ("Bash", f'bash "{runner}" "{script}" < p.json'),
                          ("Bash", "cd hooks && python gua*.py < p.json"),
                          ("Bash", 'python hooks/g"uard".py < p.json'),
                          ("PowerShell", f"Get-Content p.json | python '{script}'")):
            with self.subTest(tool=tool, cmd=cmd):
                rc, _, err = self.guard(tool, {"command": cmd}, AGENT)
                self.assertEqual(rc, 2, err)
                self.assertIn("guard.py", err)
        for cmd in ("python tools/other.py", "rg -n guard docs"):           # other scripts, the word alone
            with self.subTest(cmd=cmd):
                self.assertEqual(self.guard("Bash", {"command": cmd}, AGENT, recorded=False)[0], 0)

    def test_a_copy_into_the_transcript_store_is_refused_for_everyone(self):
        """Review r3 P2-1: a copy whose destination is a folder in <claude config>/projects (the file keeps its name)
        is refused like a named .jsonl; Claude Code's memory notes there stay writable."""
        evil = self.claude / "projects" / "evil"
        evil.mkdir()
        (self.root / "x.jsonl").write_text("{}", encoding="utf-8")
        for agent in (None, AGENT):
            for tool, ti in (("Bash", {"command": f'cp x.jsonl "{evil.as_posix()}/"'}),
                             ("Bash", {"command": f'cp x.jsonl "{evil.as_posix()}"'}),
                             ("PowerShell", {"command": f"Copy-Item x.jsonl -Destination '{evil}'"})):
                with self.subTest(agent=agent, cmd=ti):
                    rc, _, err = self.guard(tool, ti, agent, recorded=False)
                    self.assertEqual(rc, 2, err)
                    self.assertIn("transcript", err)
        memory = self.claude / "projects" / "D--work-client" / "memory" / "notes.md"
        rc, _, err = self.guard("Write", {"file_path": str(memory), "content": "x"}, recorded=False)
        self.assertEqual(rc, 0, err)

    def test_every_write_into_the_store_is_refused_but_memory(self):
        """Review 8d04064 P2-1, option (a): any target inside <claude config>/projects is refused, whatever its name
        (a new folder, a moved folder) and whoever writes; a writing command run with the store as its working folder
        (an archive extracted there) too; Claude Code's own <project>/memory/** stays open."""
        store = self.claude / "projects"
        (self.root / "pack").mkdir()
        (self.root / "pack" / "x.jsonl").write_text("{}", encoding="utf-8")
        for agent in (None, AGENT):
            for tool, ti in (("Bash", {"command": f'cp -r pack "{(store / "brand-new").as_posix()}"'}),
                             ("Bash", {"command": f'mv pack "{(store / "moved-here").as_posix()}"'}),
                             ("PowerShell", {"command": f"Copy-Item -Recurse pack -Destination '{store / 'new-name'}'"}),
                             ("Write", {"file_path": str(store / "brand-new" / "notes.txt"), "content": "x"})):
                with self.subTest(agent=agent, tool=tool, ti=ti):
                    rc, _, err = self.guard(tool, ti, agent, recorded=False)
                    self.assertEqual(rc, 2, err)
                    self.assertIn("transcript", err)
        p = {"tool_name": "Bash", "tool_input": {"command": "tar -xf /tmp/pack.tar"}, "cwd": str(store),
             "session_id": SESSION}
        self.assertEqual(hook(GUARD, p, env=self.env)[0], 2)                # extraction with the store as cwd
        p["tool_input"]["command"] = "ls -la"
        self.assertEqual(hook(GUARD, p, env=self.env)[0], 0)                # reading there is fine
        memory = store / "D--work-client" / "memory"
        for agent in (None, AGENT):                                         # review 8bb853a: never a .jsonl there
            for tool, ti in (("Write", {"file_path": str(memory / (SESSION + ".jsonl")), "content": "{}"}),
                             ("Write", {"file_path": str(memory / "x" / (SESSION + ".JSONL")), "content": "{}"}),
                             ("Bash", {"command": f'cp pack/x.jsonl "{(memory / (SESSION + ".jsonl")).as_posix()}"'})):
                with self.subTest(memory_jsonl=tool, agent=agent):
                    self.assertEqual(self.guard(tool, ti, agent, recorded=False)[0], 2)
        for tool, ti in (("Write", {"file_path": str(memory / "MEMORY.md"), "content": "x"}),
                         ("Bash", {"command": f'echo x > "{(memory / "notes.md").as_posix()}"'})):
            with self.subTest(memory=tool):
                self.assertEqual(self.guard(tool, ti, None, recorded=False)[0], 0)

    def test_the_transcript_store_through_a_link_is_refused(self):
        """Judged by the real path: a folder link whose name says nothing, pointing into the store."""
        link = self.tmp / "innocent store"
        try:
            if os.name == "nt":
                r = subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(self.transcript.parent)],
                                   capture_output=True)
                if r.returncode:
                    self.skipTest("junction not available")
            else:
                link.symlink_to(self.transcript.parent, target_is_directory=True)
        except OSError:
            self.skipTest("links not available")
        self.addCleanup(lambda: os.rmdir(link) if os.name == "nt" else link.unlink())
        (self.root / "x.jsonl").write_text("{}", encoding="utf-8")
        for agent in (None, AGENT):
            for tool, ti in (("Write", {"file_path": str(link / "y.jsonl"), "content": "{}"}),
                             ("Bash", {"command": f'cp x.jsonl "{link.as_posix()}/"'})):
                with self.subTest(agent=agent, tool=tool):
                    self.assertEqual(self.guard(tool, ti, agent, recorded=False)[0], 2)

    def test_the_store_is_compared_without_case_on_macos(self):
        """POSIX normcase keeps case (on Windows it already folds it, so it is replaced here): macOS (APFS) folds,
        Linux does not."""
        import posixpath
        g = load(GUARD, "guard_bl15_fold")
        with mock.patch.object(g.os.path, "normcase", posixpath.normcase):
            with mock.patch.object(g.sys, "platform", "darwin"):
                self.assertEqual(g._fold("/Users/Ed/.CLAUDE/Projects"), g._fold("/users/ed/.claude/projects"))
            with mock.patch.object(g.sys, "platform", "linux"):
                self.assertNotEqual(g._fold("/Users/Ed/.CLAUDE/Projects"), g._fold("/users/ed/.claude/projects"))

    def test_a_glob_names_the_folder_only_when_it_spells_its_name(self):
        """Review r3 P3-1: the glob branch; 6 literal characters or more, matching the folder's name."""
        g = load(GUARD, "guard_bl15_glob")
        for text in ("ls run/lead-tok*", "rm run/*-tokens/x", "cat run/[l]ead-token?/a.tok"):
            with self.subTest(text=text):
                self.assertTrue(g.names_token_dir(text))
        for text in ("ls *lead*", "rm -f output/tmp/*token*", "ls *", "du -sh */", "ls x*"):
            with self.subTest(text=text):
                self.assertFalse(g.names_token_dir(text))

    def test_subagent_shell_text_naming_the_folder_is_refused(self):
        d = self.home / "run" / "lead-tokens"
        for tool in ("Bash", "PowerShell"):
            with self.subTest(tool=tool):
                rc, _, _ = self.guard(tool, {"command": f'ls "{d}"'}, AGENT)
                self.assertEqual(rc, 2)
        rc, _, _ = self.guard("Bash", {"command": f'ls "{d}"'})
        self.assertEqual(rc, 0)

    def test_guard_copy_of_the_table_is_the_shared_table(self):
        g = load(GUARD, "guard_bl15")
        self.assertEqual(tuple(g.LEAD_STEPS), tuple(ls.LEAD_STEPS))
        self.assertEqual(tuple(g.TOKEN_DIR), tuple(ls.TOKEN_DIR))
        self.assertEqual([(s, o) for s, o, roles in g.BACKSTOP_STEPS if roles is None], list(ls.LEAD_STEPS))

    def test_check_reel_refuses_every_table_row_for_a_subagent(self):
        """The guard's own engine rules (not only the text backstop) cover the whole table."""
        g = load(GUARD, "guard_bl15b")
        for step, opts in ls.LEAD_STEPS:
            argv = ["reel"] + step_argv(step, opts)
            with self.subTest(argv=argv), mock.patch("sys.stderr"):
                with self.assertRaises(SystemExit) as cm:
                    g.check_reel("reel", argv, AGENT, self.root)
                self.assertEqual(cm.exception.code, 2)
                g.check_reel("reel", argv, None, self.root)                 # the lead may

    def test_an_ordinary_call_does_not_load_the_token_module(self):
        """The token code costs only the lead's call of a lead-only step, not every guarded call."""
        for cmd in ("ls -la", "reel status", "git log --oneline -3", "reel lock --status", "grep -n verify notes.md",
                    "reel settings --set language=ar", "git log --grep handoff"):
            p = {"tool_name": "Bash", "tool_input": {"command": cmd}, "cwd": str(self.root), "session_id": SESSION}
            r = subprocess.run([sys.executable, "-X", "importtime", str(GUARD)], input=json.dumps(p),
                               capture_output=True, text=True, encoding="utf-8", env=isolated_env(self.env))
            with self.subTest(cmd=cmd):
                self.assertEqual(r.returncode, 0, r.stderr[-400:])
                self.assertNotIn("lead_steps", r.stderr)


@unittest.skipUnless(HOOKS_COVER_TOKENS, "hooks.json does not route token-folder writes yet (executor patch)")
class TestHooksRouteTokenWrites(unittest.TestCase):
    """Claude Code starts the guard for Write/Edit/NotebookEdit only on paths an `if` matches: a write into a token
    folder must match one, under any engine home (default, custom, a junction's real target, an 8.3 short name)."""
    PATHS = ["C:/Users/ed/.whynot-cut/run/lead-tokens/a.tok", "D:/Claude/whynot-cut-home/run/lead-tokens/a.tok",
             "E:/WNC Home/run/lead-tokens/a.tok", "C:/Users/ed/WHYNOT~1/run/LEAD-T~1/a.tok",
             "/Users/ed/.whynot-cut/run/lead-tokens/a.tok", "/Volumes/Work/Home/run/Lead-Tokens/a.tok"]

    @staticmethod
    def glob_re(glob: str) -> re.Pattern:
        """The `if` glob (gitignore style, `//` = from the root) as a regex over a /-path without its leading /."""
        g, out, i = glob[2:] if glob.startswith("//") else glob, "", 0
        while i < len(g):
            if g.startswith("**/", i):
                out, i = out + "(?:.*/)?", i + 3
            elif g.startswith("/**", i) and i + 3 == len(g):
                out, i = out + "/.*", i + 3
            elif g[i] == "*":
                out, i = out + "[^/]*", i + 1
            elif g[i] == "?":
                out, i = out + "[^/]", i + 1
            elif g[i] == "[":
                j = g.index("]", i)
                out, i = out + g[i:j + 1], j + 1
            else:
                out, i = out + re.escape(g[i]), i + 1
        return re.compile(out + r"\Z")

    TRANSCRIPTS = ["C:/Users/ed/.claude/projects/D--work-client/0f.jsonl", "D:/Claude/projects/x/0f.jsonl",
                   "E:/cfg dir/projects/D--w/sub/0f.jsonl", "/Users/ed/.claude/projects/-Users-ed-w/0f.jsonl",
                   "/home/ed/.config/claude/Projects/x/0f.JSONL"]

    def test_every_write_tool_routes_transcript_paths_to_the_guard(self):
        """Review r3 P2-1: a Write into the transcript store reaches the guard (default, custom CLAUDE_CONFIG_DIR, a
        junction's real target)."""
        hooks = json.loads(HOOKS.read_text(encoding="utf-8"))["hooks"]["PreToolUse"]
        ifs = [h.get("if", "") for block in hooks for h in block["hooks"] if "guard.py" in h.get("command", "")]
        for tool in ("Write", "Edit", "NotebookEdit"):
            pats = [self.glob_re(m.group(1)) for m in (re.match(rf"^{tool}\((.*)\)$", x) for x in ifs) if m]
            for path in self.TRANSCRIPTS:
                with self.subTest(tool=tool, path=path):
                    self.assertTrue(any(p.match(path.lstrip("/")) for p in pats))

    def test_every_write_tool_routes_token_paths_to_the_guard(self):
        hooks = json.loads(HOOKS.read_text(encoding="utf-8"))["hooks"]["PreToolUse"]
        ifs = [h.get("if", "") for block in hooks for h in block["hooks"]
               if "guard.py" in h.get("command", "")]
        for tool in ("Write", "Edit", "NotebookEdit"):
            pats = [self.glob_re(m.group(1)) for m in (re.match(rf"^{tool}\((.*)\)$", x) for x in ifs) if m]
            for path in self.PATHS:
                with self.subTest(tool=tool, path=path):
                    self.assertTrue(any(p.match(path.lstrip("/")) for p in pats))


@unittest.skipUnless(DOCTOR_CHECKS_TOKENS, "reel doctor has no BL-15 check yet (executor patch)")
class TestDoctor(unittest.TestCase):
    """`reel doctor` shows whether lead-only steps can be approved: the guard hook registered and a token round
    trip; a failure is one fix line for the editor."""

    def test_doctor_reports_it_and_gives_a_fix(self):
        from lib import onboard
        rep = onboard.doctor()
        self.assertTrue(rep["lead_tokens"]["ok"], rep["lead_tokens"])
        self.assertFalse(any("lead-only steps" in f["item"] for f in rep["fixes"]))
        bad = {"ok": False, "registered": False, "round_trip": True, "fix": "reinstall"}
        with mock.patch.object(ls, "doctor_check", lambda: bad):
            rep = onboard.doctor()
        hits = [f for f in rep["fixes"] if "lead-only steps" in f["item"]]
        self.assertEqual(len(hits), 1, rep["fixes"])
        self.assertEqual((hits[0]["who"], hits[0]["fix"]), ("editor", "reinstall"))
        self.assertIn("not registered", hits[0]["item"])


# keyed on the guard patch only: the cli patch lands with it, and a cli without the check must FAIL here, never skip
@unittest.skipUnless(GUARD_HAS_TOKENS, "guard/cli have no BL-15 support yet (executor patches)")
class TestHookAndEngine(Client):
    ARGV = ["lock", "--release"]

    def lead(self, argv):
        rc, _, err = self.guard("Bash", {"command": "reel " + " ".join(f'"{a}"' for a in argv)})
        self.assertEqual(rc, 0, err)

    def test_lead_call_through_the_real_hook_runs(self):
        argv = ["--root", str(self.root)] + self.ARGV
        self.lead(argv)
        code, out, err = self.engine(argv)
        self.assertNotEqual(code, 2, out + err)
        self.assertNotIn("blocked", out)
        self.assertEqual(self.tokens(), [])

    def test_lead_call_without_root_binds_the_folder(self):
        self.lead(self.ARGV)
        code, out, err = self.engine(self.ARGV)
        self.assertNotEqual(code, 2, out + err)

    def test_every_step_without_a_token_is_refused_and_writes_nothing(self):
        before = sorted(str(p.relative_to(self.root)) for p in self.root.rglob("*"))
        known = known_commands()
        for step, opts in ls.LEAD_STEPS:
            if step not in known:
                continue
            argv = ["--root", str(self.root), "--video-id", "C0001"] + step_argv(step, opts)
            with self.subTest(step=step, opts=opts):
                code, out, _ = self.engine(argv)
                self.assertEqual(code, 2, out)
                doc = json.loads(out)
                self.assertTrue(doc["blocked"].startswith("الخطوة دي للمحرر بس"))
                self.assertIn("one plain call", doc["how"])
        code, out, _ = self.engine(["--root", str(self.root), "transcript-verify", "--by", "editor"])
        self.assertEqual(code, 2, out)
        self.assertEqual(sorted(str(p.relative_to(self.root)) for p in self.root.rglob("*")), before)

    def test_a_subagent_call_leaves_nothing_for_the_engine(self):
        argv = ["--root", str(self.root)] + self.ARGV
        self.guard("Bash", {"command": "reel " + " ".join(f'"{a}"' for a in argv)}, agent=AGENT, recorded=True)
        self.assertEqual(self.engine(argv)[0], 2)

    def test_a_hand_fed_payload_leaves_nothing_for_the_engine(self):
        argv = ["--root", str(self.root)] + self.ARGV
        self.guard("Bash", {"command": "reel " + " ".join(f'"{a}"' for a in argv)}, recorded=False)
        self.assertEqual(self.engine(argv)[0], 2)

    def test_a_token_is_single_use_end_to_end(self):
        argv = ["--root", str(self.root)] + self.ARGV
        self.lead(argv)
        self.assertNotEqual(self.engine(argv)[0], 2)
        self.assertEqual(self.engine(argv)[0], 2)

    def test_another_session_cannot_use_it(self):
        argv = ["--root", str(self.root)] + self.ARGV
        self.lead(argv)
        self.env["CLAUDE_CODE_SESSION_ID"] = "another-session"
        self.assertEqual(self.engine(argv)[0], 2)
        self.env.pop("CLAUDE_CODE_SESSION_ID")
        self.assertEqual(self.engine(argv)[0], 2)                   # nor an engine without a session id

    def test_a_step_that_is_not_lead_only_needs_no_token(self):
        code, out, err = self.engine(["--root", str(self.root), "lock", "--status"])
        self.assertNotEqual(code, 2, out + err)
        self.assertFalse((self.home / "run" / "lead-tokens").exists())

    def test_a_lead_call_loads_only_the_token_module(self):
        """What the lead's call of a lead-only step adds to the hook is the token module and what it needs (the
        engine home's rules in plat, and the standard library): never another engine module or onboard/doctor. (Wall time
        on a shared machine is noise; the in-process cost is test_hook_issue_latency, the import cost is measured in
        the close-out.)"""
        def imported(cmd):
            p = self.payload(cmd, cwd=self.root)
            r = subprocess.run([sys.executable, "-X", "importtime", str(GUARD)], input=json.dumps(p),
                               capture_output=True, text=True, encoding="utf-8", env=isolated_env(self.env))
            self.assertEqual(r.returncode, 0, r.stderr[-400:])
            return {line.split("|")[-1].strip() for line in r.stderr.splitlines() if line.startswith("import time:")}
        base = imported(f'reel status --root "{self.root}"')
        lead = imported(f'reel lock --release --root "{self.root}"')
        self.assertEqual(len(self.tokens()), 1)
        added = {m.split(".")[0] for m in lead - base}
        ours = {m for m in added if m not in sys.stdlib_module_names}
        self.assertEqual(ours, {"lead_steps", "plat"}, added)       # no engine module, no onboard/doctor

if __name__ == "__main__":
    unittest.main()
