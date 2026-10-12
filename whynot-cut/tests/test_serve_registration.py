"""3.0 Addendum C2.1 — `reel serve` is a `reel` command, and SessionStart starts the panel link in the background.

* cli.py registers `serve` (verbs run | ensure | status | stop, or serve's own --ensure / --status / --stop /
  --foreground flags) and hands the parsed options to engine/reel/serve/cli.py unchanged (its JSON, its exit codes);
  `serve` needs no client folder and takes no writer lock; other commands never import the daemon module.
* hooks/session_context.py spawns `serve --ensure --quiet` fully detached after its context work (Windows
  CREATE_NO_WINDOW | DETACHED_PROCESS, POSIX start_new_session), never waits and never fails the hook; skipped when the
  preference `panel_link` is off, under WHYNOT_TEST_SANDBOX, or without an engine runtime.
Nothing here starts a real daemon: Popen is mocked, and `reel serve status` runs against a temp engine home.
Run:  bash tools/test.sh -p test_serve_registration.py
"""
import sys as _sys
_sys.dont_write_bytecode = True  # keep the plugin folder free of __pycache__
import _isolation  # noqa: F401,E402  G79: sandbox the engine home first (tests/_isolation.py)
import contextlib
import importlib.util
import io
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys = _sys
SK = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SK / "engine" / "reel"))

import cli  # noqa: E402
from lib import plat, settings  # noqa: E402

CTX = SK / "hooks" / "session_context.py"
SERVE_MAIN = SK / "engine" / "reel" / "serve" / "__main__.py"


def run_main(argv):
    """cli.main in-process -> (exit code, stdout, stderr)."""
    o, e = io.StringIO(), io.StringIO()
    code = 0
    with contextlib.redirect_stdout(o), contextlib.redirect_stderr(e):
        try:
            cli.main(list(argv))
        except SystemExit as x:
            code = x.code if isinstance(x.code, int) else (0 if x.code is None else 1)
    return code, o.getvalue(), e.getvalue()


# ------------------------------------------------------------------------------------------------ the command
class TestServeIsACommand(unittest.TestCase):
    def test_in_the_table_and_classified_as_a_machine_level_read(self):
        self.assertIn("serve", cli.command_table())
        self.assertIn("serve", cli.registered_commands())
        self.assertIn("serve", cli.NO_ROOT)
        self.assertIn("serve", cli.NO_ID)
        self.assertIn("serve", cli.CORE_READS)
        self.assertNotIn("serve", cli.CORE_WRITES)
        self.assertNotIn("serve", cli.WRITES_IF)
        self.assertTrue(callable(getattr(cli, "cmd_serve", None)))

    def test_reel_help_lists_it(self):
        code, out, _ = run_main(["--help"])
        self.assertEqual(code, 0)
        self.assertRegex(out, r"(?m)^\s+serve\s")

    def test_serve_help_shows_the_verbs_and_serves_own_options(self):
        code, out, _ = run_main(["serve", "--help"])
        self.assertEqual(code, 0)
        for word in ("ensure", "status", "stop", "run", "--ensure", "--foreground", "--quiet", "--wait"):
            self.assertIn(word, out)

    def test_other_commands_do_not_import_the_daemon(self):
        """serve.cli.add_args imports serve.daemon (asyncio, the app: ~0.1 s); only `reel serve` may pay for it."""
        code = ("import sys, argparse; sys.path.insert(0, %r); import cli\n"
                "class B(Exception): pass\n"
                "def cap(self, *a, **k): raise B()\n"
                "argparse.ArgumentParser.parse_args = cap\n"
                "for argv in (['next'], ['--help'], ['ppro-status']):\n"
                "    try: cli.main(argv)\n"
                "    except B: pass\n"
                "print('serve.daemon' in sys.modules)\n") % str(SK / "engine" / "reel")
        r = subprocess.run([sys.executable, "-B", "-c", code], capture_output=True, text=True, timeout=120)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout.strip(), "False")


class TestPassThrough(unittest.TestCase):
    def parsed(self, *argv):
        seen = []
        with mock.patch("serve.cli.cmd_serve", side_effect=lambda a: seen.append(a)):
            code, out, err = run_main(["serve", *argv])
        return code, (seen[0] if seen else None), err

    def flags(self, a):
        return {k: bool(getattr(a, k)) for k in ("ensure", "status", "stop", "foreground")}

    def test_verbs_map_to_serves_flags(self):
        for verb, flag in (("ensure", "ensure"), ("status", "status"), ("stop", "stop"), ("run", "foreground")):
            with self.subTest(verb=verb):
                code, a, err = self.parsed(verb)
                self.assertEqual(code, 0, err)
                self.assertEqual(self.flags(a), {k: k == flag for k in ("ensure", "status", "stop", "foreground")})

    def test_serves_own_flags_and_options_pass_through(self):
        code, a, err = self.parsed("--ensure", "--wait", "2.5", "--quiet")
        self.assertEqual(code, 0, err)
        self.assertTrue(a.ensure)
        self.assertEqual((a.wait, a.quiet), (2.5, True))
        code, a, err = self.parsed("ensure", "--wait", "0", "--quiet")
        self.assertEqual(code, 0, err)
        self.assertEqual((a.ensure, a.wait, a.quiet), (True, 0.0, True))

    def test_bare_serve_is_serves_default(self):
        code, a, err = self.parsed()
        self.assertEqual(code, 0, err)
        self.assertEqual(self.flags(a), {"ensure": False, "status": False, "stop": False, "foreground": False})

    def test_a_verb_and_another_flag_is_a_usage_error(self):
        code, a, err = self.parsed("ensure", "--stop")
        self.assertEqual(code, 2)
        self.assertIsNone(a)
        self.assertIn("--stop", err)
        code, a, _ = self.parsed("stop", "--stop")            # the same action twice is harmless
        self.assertEqual(code, 0)
        self.assertTrue(a.stop)

    def test_abbreviations_and_unknown_verbs_are_refused(self):
        for argv in (["--ens"], ["--fore"], ["ens"], ["start"], ["--ensure", "--stop"]):
            with self.subTest(argv=argv):
                code, a, err = self.parsed(*argv)
                self.assertEqual(code, 2, err)
                self.assertIsNone(a)

    def test_no_client_folder_and_no_writer_lock(self):
        with tempfile.TemporaryDirectory() as t, mock.patch("cli.take_writer_lock") as lock:
            cwd = os.getcwd()
            os.chdir(t)                                       # not a client folder: no --root needed
            try:
                code, a, err = self.parsed("status")
            finally:
                os.chdir(cwd)
        self.assertEqual(code, 0, err)
        self.assertFalse(cli.writes(a))
        self.assertIsNone(a.root)
        lock.assert_called_once()                             # asked, and it is a read: take_writer_lock returns None


class TestServeOutputAndExitCodes(unittest.TestCase):
    def setUp(self):
        self.home = Path(tempfile.mkdtemp(prefix="wnc-serve-reg-"))

    def test_status_of_an_empty_home_is_serves_json(self):
        code, out, err = run_main(["serve", "status", "--home", str(self.home)])
        self.assertEqual(code, 0, err)
        self.assertEqual(json.loads(out), {"ok": True, "running": False, "state": "stopped"})

    def test_a_failure_document_exits_1_and_quiet_exits_0(self):
        bad = {"ok": False, "running": True, "state": "not_answering", "error": "x", "how": "y"}
        with mock.patch("serve.daemon.ensure", return_value=bad):
            code, out, _ = run_main(["serve", "ensure", "--home", str(self.home)])
            self.assertEqual(code, 1)
            self.assertEqual(json.loads(out)["state"], "not_answering")
            code, out, _ = run_main(["serve", "ensure", "--quiet", "--home", str(self.home)])
        self.assertEqual((code, out), (0, ""))

    def test_run_keeps_the_daemons_exit_code(self):
        from serve import daemon
        with mock.patch("serve.daemon.run", return_value=daemon.EXIT_LOCKED):
            code, out, _ = run_main(["serve", "run", "--home", str(self.home)])
        self.assertEqual(code, daemon.EXIT_LOCKED)
        self.assertEqual(json.loads(out)["state"], "refused")


# ------------------------------------------------------------------------------------------------ SessionStart
def load_hook():
    spec = importlib.util.spec_from_file_location("wnc_session_context_c21", CTX)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    mod.plat, mod.settings = plat, settings
    return mod


class HookCase(unittest.TestCase):
    def setUp(self):
        self.t = Path(tempfile.mkdtemp(prefix="wnc-c21-"))
        self.home = self.t / "engine"
        self.py = plat.env_python(self.home / "venv")
        self.py.parent.mkdir(parents=True)
        self.py.write_bytes(b"")                              # an engine interpreter exists (never run: Popen mocked)
        self.ctx = load_hook()
        self.env = mock.patch.dict(os.environ, {"WHYNOT_TEST_SANDBOX": ""})
        self.env.start()
        del os.environ["WHYNOT_TEST_SANDBOX"]                 # the hook's own skip is tested separately
        self.addCleanup(self.env.stop)

    def link(self, st=None, windows=None, popen=None):
        calls = []

        def fake(cmd, **kw):
            calls.append((cmd, kw))
            if popen:
                return popen(cmd, **kw)
            return mock.Mock(spec=["pid", "wait", "communicate", "poll"])
        with mock.patch.object(self.ctx, "_popen", side_effect=fake), \
                mock.patch.object(self.ctx, "WINDOWS", os.name == "nt" if windows is None else windows):
            line = self.ctx.panel_link(self.home, dict(settings.DEFAULTS, **(st or {})))
        return line, calls


class TestPanelLink(HookCase):
    def test_windows_spawns_ensure_with_no_window_fully_detached(self):
        line, calls = self.link(windows=True)
        self.assertEqual(line, "")
        self.assertEqual(len(calls), 1)
        cmd, kw = calls[0]
        self.assertEqual(cmd, [str(self.py), "-s", "-B", "-P", str(SERVE_MAIN), "--ensure", "--quiet"])
        flags = kw["creationflags"]
        for bit in (0x08000000, 0x00000008, 0x00000200, 0x01000000):   # NO_WINDOW, DETACHED, NEW_GROUP, BREAKAWAY
            self.assertTrue(flags & bit, hex(bit))
        self.assertNotIn("start_new_session", kw)
        for k in ("stdin", "stdout", "stderr"):
            self.assertEqual(kw[k], subprocess.DEVNULL)          # never the hook's own pipes: Claude would wait on them
        self.assertTrue(kw["close_fds"])
        self.assertEqual(kw["cwd"], str(self.home))

    def test_windows_job_without_breakaway_starts_inside_it(self):
        def popen(cmd, **kw):
            if kw["creationflags"] & 0x01000000:
                raise PermissionError(5, "Access is denied")
            return mock.Mock()
        line, calls = self.link(windows=True, popen=popen)
        self.assertEqual(line, "")
        self.assertEqual(len(calls), 2)
        flags = calls[1][1]["creationflags"]
        self.assertFalse(flags & 0x01000000)
        self.assertTrue(flags & 0x08000000 and flags & 0x00000008)

    def test_posix_starts_a_new_session(self):
        line, calls = self.link(windows=False)
        self.assertEqual(line, "")
        cmd, kw = calls[0]
        self.assertEqual(cmd[-2:], ["--ensure", "--quiet"])
        self.assertIs(kw["start_new_session"], True)
        self.assertNotIn("creationflags", kw)

    def test_it_never_waits_for_the_child(self):
        child = mock.Mock()
        line, _ = self.link(popen=lambda cmd, **kw: child)
        self.assertEqual(line, "")
        child.wait.assert_not_called()
        child.communicate.assert_not_called()

    def test_opt_out(self):
        for value in (False, "off"):
            with self.subTest(value=value):
                st = settings.parse(f"---\npanel_link: {value if value == 'off' else 'false'}\n---\n")[0]
                self.assertIs(st["panel_link"], False)
                line, calls = self.link(st=st)
                self.assertEqual((line, calls), ("", []))

    def test_default_is_on(self):
        self.assertIs(settings.DEFAULTS["panel_link"], True)

    def test_sandbox_skips(self):
        with mock.patch.dict(os.environ, {"WHYNOT_TEST_SANDBOX": str(self.t)}):
            line, calls = self.link()
        self.assertEqual((line, calls), ("", []))

    def test_no_engine_runtime_is_silent(self):
        self.py.unlink()
        line, calls = self.link()
        self.assertEqual((line, calls), ("", []))

    def test_errors_become_one_short_line(self):
        def boom(cmd, **kw):
            raise FileNotFoundError(2, "The system cannot find the file specified")
        for windows in (True, False):
            with self.subTest(windows=windows):
                line, calls = self.link(windows=windows, popen=boom)
                self.assertTrue(line.startswith("WhyNot Cut panel link not started: "), line)
                self.assertNotIn("\n", line.strip())
                self.assertLess(len(line), 240)
        with mock.patch.object(self.ctx.plat, "venv_python", side_effect=RuntimeError("odd home")):
            line, _ = self.link()
        self.assertIn("odd home", line)


class TestHookMain(HookCase):
    """The whole hook, in-process: context first, then the spawn; an error is one line in the context, never a
    failure, and an unrelated folder stays silent when all is well."""

    def run_hook(self, cwd: Path, popen=None, st_text=None):
        if st_text is not None:
            (cwd / ".claude").mkdir(parents=True, exist_ok=True)
            (cwd / ".claude" / settings.FILE).write_text(st_text, encoding="utf-8")
        calls, out = [], io.StringIO()

        def fake(cmd, **kw):
            calls.append(cmd)
            if popen:
                return popen(cmd, **kw)
            return mock.Mock()
        env = {"WHYNOT_HOME": str(self.home), "WHYNOT_CLIENTS_ROOT": str(self.t / "no-clients"),
               "HOME": str(self.t), "USERPROFILE": str(self.t)}
        with mock.patch.dict(os.environ, env), mock.patch.object(self.ctx, "_popen", side_effect=fake), \
                mock.patch.object(sys, "stdin", io.StringIO(json.dumps({"cwd": str(cwd)}))), \
                contextlib.redirect_stdout(out):
            for k in ("CLAUDE_PLUGIN_DATA", "CLAUDE_ENV_FILE"):
                os.environ.pop(k, None)
            self.ctx.run()
        return out.getvalue(), calls

    def test_unrelated_folder_spawns_and_stays_silent(self):
        (self.t / "elsewhere").mkdir()
        out, calls = self.run_hook(self.t / "elsewhere")
        self.assertEqual(out, "")
        self.assertEqual(len(calls), 1)

    def test_an_error_is_one_line_of_context(self):
        (self.t / "elsewhere").mkdir()
        out, _ = self.run_hook(self.t / "elsewhere", popen=lambda c, **k: (_ for _ in ()).throw(OSError("denied")))
        ctx = json.loads(out)["hookSpecificOutput"]["additionalContext"]
        self.assertTrue(ctx.startswith("WhyNot Cut panel link not started: "), ctx)
        self.assertIn("denied", ctx)

    def test_client_context_comes_first_then_the_error_line(self):
        root = self.t / "Client"
        for d in ("assets", "data"):
            (root / d).mkdir(parents=True)
        (root / ".whynot-client").write_text('{"whynot_client": 1}', encoding="utf-8")
        out, _ = self.run_hook(root, popen=lambda c, **k: (_ for _ in ()).throw(OSError("denied")))
        ctx = json.loads(out)["hookSpecificOutput"]["additionalContext"]
        self.assertIn("this is a client folder", ctx)
        self.assertLess(ctx.index("this is a client folder"), ctx.index("panel link not started"))

    def test_opt_out_in_the_preferences_file(self):
        (self.t / "elsewhere").mkdir()
        out, calls = self.run_hook(self.t / "elsewhere", st_text="---\npanel_link: off\n---\n")
        self.assertEqual(calls, [])
        self.assertNotIn("panel link", out)

    def test_the_script_never_fails(self):
        """Run as a file under the test sandbox: the hook exits 0 and starts nothing."""
        r = subprocess.run([sys.executable, "-B", str(CTX)], input=json.dumps({"cwd": str(self.t)}),
                           capture_output=True, text=True, timeout=60,
                           env=dict(os.environ, WHYNOT_TEST_SANDBOX=str(self.t), WHYNOT_HOME=str(self.home)))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertNotIn("panel link", r.stdout)


if __name__ == "__main__":
    unittest.main()
