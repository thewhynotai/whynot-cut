# SPDX-License-Identifier: GPL-3.0-or-later
# © 2026 The Why Not AI (thewhynot.ai)
"""3.0 tools track, Task 10 (N4 part B): WhyNot Kalam correction contract, faithfulness gate, Claude discovery, platform
(lib/kalam/correct.py and platform.py). Ported from the owner's Kalam engine tests (engine/tests/test_correct.py 17,
engine/tests/test_platform.py 5): every upstream test function is one method here with the SAME name; bodies are
unchanged apart from the mechanical pytest -> unittest rewrite (assert -> assertEqual / assertTrue, tmp_path ->
TemporaryDirectory, monkeypatch -> unittest.mock) and the substitutions below. tests/test_kalam_test_map.py guards that
none is dropped. Class TestCorrect = test_correct.py, TestPlatform = test_platform.py, the rest are new tests.

Substitutions (each one listed here, as the global constraints require):
  * `anthropic` and `httpx2`: the upstream test imports them for real; the engine runtime has neither (and they are never
    installed for a test), so the tests that need them install tiny fakes in sys.modules for their duration
    (fake_api_modules(): APIError, APIConnectionError(request=), Anthropic(**kw), httpx2.Request).
  * The upstream test_every_user_approved_demo_correction_passes reads the upstream demo pair (a raw-model SRT and its
    user-approved corrected twin, 28 captions each); those files were never supplied and name a real person. They are
    replaced by a fictional Egyptian-Arabic pair written for this test, same structure (28 SRT blocks each, the model's
    raw lines with Arabic-script spellings of English terms and spelling slips, and the corrected lines with the Latin
    terms and fixed spelling, every pair must pass the faithfulness gate): tests/test_kalam_fixtures/
    example_raw_model.srt and example_corrected.srt (a home-bakery talk, no real names).
  * Fixture scan: the two upstream files hold no real name or machine path other than the demo file names of that pair.

New tests (audit §3.1/§5): the macOS candidate strings on Windows, WhyNot Cut discovery (exe first, `.cmd` last, PATHEXT
instead of X_OK, sandbox rules) with a parity test against installer/core/wnc_installer/claude.py, `.cmd` handling (never
cmd.exe with JSON on argv), the temp-folder prefix, kill-tree on cancel, lazy `anthropic`.
"""
import sys as _sys
_sys.dont_write_bytecode = True
import _isolation  # noqa: F401,E402  G79: sandbox the engine home first (tests/_isolation.py)
import contextlib
import importlib
import json
import os
import re
import subprocess
import sys
import tempfile
import time
import types
import unittest
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "engine" / "reel"))

from lib.kalam import correct as _correct_module  # noqa: E402
from lib.kalam import platform as P  # noqa: E402
from lib.kalam.correct import ClaudeCodeClient, _run_cli, correct, default_rules, faithful, make_client, rules_for  # noqa: E402

FIXTURES = HERE / "test_kalam_fixtures"
CORE = HERE.parent / "installer" / "core"          # installer/core/wnc_installer (ships inside whynot-cut/)


class _Block:
    def __init__(self, text):
        self.type, self.text = "text", text


class _Resp:
    def __init__(self, lines, stop="end_turn"):
        self.content = [_Block(json.dumps({"lines": lines}, ensure_ascii=False))]
        self.stop_reason = stop


class FakeClient:
    """records requests; replies with a scripted list of line-lists (or exceptions)"""
    def __init__(self, *replies):
        self.replies, self.requests = list(replies), []
        self.beta = self
        self.messages = self

    def create(self, **kw):
        self.requests.append(kw)
        r = self.replies.pop(0)
        if isinstance(r, Exception):
            raise r
        if isinstance(r, _Resp):
            return r
        return _Resp(r)


SRC = ["صفتشو انجري انتم عارفين", "ان احنا ما فيش حاجة اسمها فراكشر", "عبارة عن سوفت ايش وانجري"]
FIXED = ["Soft Tissue Injury انتو عارفين", "إن احنا مفيش حاجة اسمها Fracture", "عبارة عن Soft Tissue Injury"]


@contextlib.contextmanager
def fake_api_modules():
    """tiny stand-ins for the `anthropic` and `httpx2` packages, installed in sys.modules for the duration"""
    anthropic = types.ModuleType("anthropic")

    class APIError(Exception):
        pass

    class APIConnectionError(APIError):
        def __init__(self, *, request):
            super().__init__("Connection error.")
            self.request = request

    class Anthropic:
        made = []

        def __init__(self, **kw):
            Anthropic.made.append(kw)
            self.beta = self.messages = FakeClient(FIXED)

    anthropic.APIError, anthropic.APIConnectionError, anthropic.Anthropic = APIError, APIConnectionError, Anthropic
    httpx2 = types.ModuleType("httpx2")

    class Request:
        def __init__(self, method, url):
            self.method, self.url = method, url

    httpx2.Request = Request
    with mock.patch.dict(sys.modules, {"anthropic": anthropic, "httpx2": httpx2}):
        yield anthropic, httpx2


FAKE_IDENTITY = {"email": "ali.example@example.invalid", "orgId": "org-0000-example", "orgName": "Example Org",
                 "subscriptionType": "max", "apiProvider": "firstParty", "token": "sk-ant-fake-0000-not-a-key"}


def auth_json(method="claude.ai", logged_in=True, **extra):
    """what `claude auth status` prints (real shape, Claude Code 2.1.299), with fictional values"""
    d = {"loggedIn": logged_in, "authMethod": method, "apiProvider": "firstParty", "analyticsDisabled": True,
         "projectsDirectory": "/example/projects", "configDirectory": "/example/.claude", "email": FAKE_IDENTITY["email"],
         "orgId": FAKE_IDENTITY["orgId"], "orgName": FAKE_IDENTITY["orgName"], "subscriptionType": "max"}
    d.update(extra)
    return json.dumps(d)


def OK_AUTH(args, cwd):
    return 0, auth_json()


def touch(p: Path, text: str = "x") -> Path:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")
    return p


class TestCorrect(unittest.TestCase):
    def test_reply_with_same_count_is_used(self):
        c = FakeClient(FIXED)
        out, stats = correct(SRC, "rules", {}, "key", client=c)
        self.assertTrue(out == FIXED and stats["changed"] == 3 and stats["fallback"] == 0)
        req = c.requests[0]
        self.assertTrue(req["model"] == "claude-opus-5-5" and req["fallbacks"] == "default")
        self.assertIn("server-side-fallback-2026-07-01", req["betas"])
        self.assertEqual(req["output_config"]["format"]["type"], "json_schema")

    def test_wrong_count_is_retried_once_then_source_kept(self):
        c = FakeClient(FIXED[:2], FIXED[:2])
        out, stats = correct(SRC, "rules", {}, "key", client=c)
        self.assertTrue(out == SRC and len(c.requests) == 2 and stats["fallback"] == 3)

    def test_wrong_count_then_right_count_uses_retry(self):
        c = FakeClient(FIXED[:2], FIXED)
        out, _ = correct(SRC, "rules", {}, "key", client=c)
        self.assertEqual(out, FIXED)

    def test_shortened_line_falls_back_to_source(self):
        c = FakeClient([FIXED[0], "مفيش", FIXED[2]])
        out, stats = correct(SRC, "rules", {}, "key", client=c)
        self.assertTrue(out == [FIXED[0], SRC[1], FIXED[2]] and stats["fallback"] == 1)

    def test_connection_error_keeps_all_source(self):
        with fake_api_modules() as (anthropic, httpx2):
            err = anthropic.APIConnectionError(request=httpx2.Request("POST", "https://api.anthropic.com/v1/messages"))
            out, stats = correct(SRC, "rules", {}, "key", client=FakeClient(err))
        self.assertTrue(out == SRC and stats["error"])

    def test_refusal_keeps_source(self):
        out, stats = correct(SRC, "rules", {}, "key", client=FakeClient(_Resp(FIXED, stop="refusal")))
        self.assertTrue(out == SRC and stats["error"] == "refusal")

    def test_no_key_and_no_client_returns_source(self):
        out, stats = correct(SRC, "rules", {}, "", client=None)
        self.assertTrue(out == SRC and stats["error"] == "no_api_key")

    def test_long_input_is_batched_with_context_and_glossary(self):
        src = ["كلمة %d هنا" % i for i in range(130)]
        c = FakeClient(*[src[i:i + 60] for i in range(0, 130, 60)])
        out, stats = correct(src, "rules", {"Granudacyn": ["graniodasin"]}, "key", client=c)
        self.assertTrue(out == src and len(c.requests) == 3)
        second = c.requests[1]["messages"][0]["content"]
        self.assertIn("كلمة 59 هنا", second)            # context from the previous batch
        self.assertIn("Granudacyn", c.requests[0]["system"])

    def test_default_rules_follow_the_mode(self):
        self.assertIn("الهمزات", default_rules("ar"))
        en = default_rules("en")
        self.assertTrue("English" in en and "الهمزات" not in en)
        self.assertEqual(default_rules("other"), en)

    # ---- Claude subscription backend (Claude Code CLI) ----
    def test_claude_code_client_runs_cli_safely_and_parses_structured_output(self):
        seen = {}

        def runner(args, stdin, cwd):
            seen.update(args=args, stdin=stdin, cwd=cwd,
                        system=Path(args[args.index("--system-prompt-file") + 1]).read_text(encoding="utf-8"))
            return 0, json.dumps({"type": "result", "is_error": False, "structured_output": {"lines": FIXED}})

        out, stats = correct(SRC, "rules", {}, "", client=ClaudeCodeClient("/x/claude", runner=runner, auth_runner=OK_AUTH))
        self.assertTrue(out == FIXED and stats["error"] is None)
        a = seen["args"]
        self.assertTrue(a[0] == "/x/claude" and "-p" in a and "--safe-mode" in a and "--no-session-persistence" in a)
        self.assertTrue(a[a.index("--tools") + 1] == "" and a[a.index("--output-format") + 1] == "json")
        self.assertEqual(json.loads(a[a.index("--json-schema") + 1])["required"], ["lines"])
        self.assertTrue(seen["system"].startswith("rules"))
        self.assertEqual(json.loads(seen["stdin"])["lines"], SRC)        # the phrases go in on stdin, never on argv

    def test_claude_code_client_error_keeps_source(self):
        def runner(args, stdin, cwd):
            return 1, json.dumps({"type": "result", "is_error": True, "result": "Not logged in"})
        out, stats = correct(SRC, "rules", {}, "", client=ClaudeCodeClient("/x/claude", runner=runner, auth_runner=OK_AUTH))
        self.assertTrue(out == SRC and "Not logged in" in stats["error"])

    def test_make_client_defaults_to_subscription(self):
        c, notice = make_client({}, finder=lambda: "/x/claude")
        self.assertTrue(isinstance(c, ClaudeCodeClient) and notice is None)
        c, notice = make_client({"backend": "subscription"}, finder=lambda: None)
        self.assertTrue(c is None and notice == "claude_code_missing")
        c, notice = make_client({"backend": "api", "api_key": "k"}, finder=lambda: "/x/claude")
        self.assertTrue(c is None and notice is None)

    # ---- faithfulness gate: a correction may fix words, never rewrite, translate or add ----
    def test_every_user_approved_demo_correction_passes(self):
        def _srt_texts(p):
            return [" ".join(b.split("\n")[2:]) for b in p.read_text(encoding="utf-8").strip().split("\n\n")]

        raw, fixed = _srt_texts(FIXTURES / "example_raw_model.srt"), _srt_texts(FIXTURES / "example_corrected.srt")
        self.assertTrue(len(raw) == len(fixed) == 28)
        bad = [(r, f) for r, f in zip(raw, fixed) if not faithful(r, f)]
        self.assertFalse(bad, bad)

    def test_rewrite_translation_and_added_sentence_are_rejected(self):
        src = "ان احنا ما فيش حاجة اسمها فراكشر"
        self.assertFalse(faithful(src, "إننا لا يوجد لدينا شيء يسمى الكسر"))            # MSA rewrite, same length
        self.assertFalse(faithful(src, "we do not have anything called a fracture"))      # translation
        self.assertFalse(faithful(src, src + " وده كلام مهم جدا لازم كله يعرفه كويس"))    # added sentence
        self.assertFalse(faithful("ده", "ده كلام مهم جدا جدا جدا"))                       # short source, big growth

    def test_custom_rules_reach_every_mode(self):
        self.assertEqual(rules_for({"rules": "my english rules"}, "en"), "my english rules")
        self.assertEqual(rules_for({"rules": "قواعدي"}, "ar"), "قواعدي")
        self.assertTrue(rules_for({}, "en") == default_rules("en") and rules_for({"rules": "  "}, "ar") == default_rules("ar"))

    def test_unit_markers_pass_the_faithfulness_gate_and_fallbacks_are_reported(self):
        marked = ["Soft Tissue Injury | انتو عارفين |", "إن احنا مفيش حاجة اسمها Fracture", "مفيش"]
        out, stats = correct(SRC, "rules", {}, "key", client=FakeClient(marked))
        self.assertTrue(out[:2] == marked[:2] and out[2] == SRC[2])
        self.assertEqual(stats["kept_source"], [2])

    def test_contract_asks_for_meaning_unit_markers(self):
        c = FakeClient(FIXED)
        correct(SRC, "rules", {}, "key", client=c)
        self.assertIn("|", c.requests[0]["system"])


class TestPlatform(unittest.TestCase):
    def test_claude_candidates_windows(self):
        home = Path("C:/Users/Ali")
        c = P.claude_candidates({"APPDATA": "C:/Users/Ali/AppData/Roaming"}, home, windows=True)
        self.assertIn(str(home / ".local" / "bin" / "claude.exe"), c)
        self.assertIn(str(Path("C:/Users/Ali/AppData/Roaming") / "npm" / "claude.cmd"), c)
        self.assertFalse(any(x.startswith("/opt/") for x in c))

    def test_claude_candidates_mac(self):
        c = P.claude_candidates({}, Path("/Users/x"), windows=False)
        self.assertIn("/opt/homebrew/bin/claude", c)
        self.assertIn("/Users/x/.local/bin/claude", c)        # was "\Users\x\.local\bin\claude" on Windows (Path)

    def test_backend_env_forces_portable(self):
        with mock.patch.dict(os.environ, {"KALAM_BACKEND": "portable"}):
            self.assertEqual(P.backend(), "portable")

    def test_backend_is_portable_off_mac(self):
        with mock.patch.dict(os.environ):
            os.environ.pop("KALAM_BACKEND", None)
            with mock.patch.object(P.sys, "platform", "win32"):
                self.assertEqual(P.backend(), "portable")

    def test_run_cli_utf8(self):
        with tempfile.TemporaryDirectory() as tmp_path:
            code, out = _run_cli([sys.executable, "-c", "import sys; sys.stdout.write(sys.stdin.read())"],
                                 "هيرقيك Reputation", str(tmp_path))
        self.assertTrue(code == 0 and out == "هيرقيك Reputation")


class TestMacStringsOnWindows(unittest.TestCase):
    """New: the macOS candidate strings are POSIX strings on every host."""

    def test_exact_mac_list_has_no_backslash(self):
        c = P.claude_candidates({}, Path("/Users/x"), windows=False)
        self.assertEqual(c, ["/Users/x/.local/bin/claude", "/opt/homebrew/bin/claude", "/usr/local/bin/claude"])
        self.assertFalse(any("\\" in x for x in c))

    def test_home_given_as_a_deeper_path_stays_posix(self):
        c = P.claude_candidates({}, Path("/Users/example user/x"), windows=False)
        self.assertEqual(c[0], "/Users/example user/x/.local/bin/claude")

    def test_windows_list_is_unchanged(self):
        home = Path("C:/Users/Ali")
        self.assertEqual(P.claude_candidates({}, home, windows=True), [str(home / ".local" / "bin" / "claude.exe")])


class TestRunnable(unittest.TestCase):
    def test_windows_uses_pathext_not_x_ok(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            plain, txt = touch(d / "claude"), touch(d / "claude.txt")
            exe, cmd = touch(d / "claude.exe"), touch(d / "claude.CMD")
            with mock.patch("os.access", return_value=True):          # what os.access(X_OK) says on Windows: yes, always
                self.assertFalse(P.runnable(plain, {}, True))
                self.assertFalse(P.runnable(txt, {}, True))
                self.assertTrue(P.runnable(exe, {}, True))
                self.assertTrue(P.runnable(cmd, {}, True))
            self.assertFalse(P.runnable(d / "missing.exe", {}, True))
            self.assertFalse(P.runnable(exe, {"PATHEXT": ".BAT;.CMD"}, True))      # PATHEXT decides, not the name
            self.assertTrue(P.runnable(txt, {"PATHEXT": ".TXT"}, True))

    def test_posix_needs_the_execute_bit(self):
        with tempfile.TemporaryDirectory() as d:
            f = touch(Path(d) / "claude")
            with mock.patch("os.access", return_value=False):
                self.assertFalse(P.runnable(f, {}, False))
            with mock.patch("os.access", return_value=True) as acc:
                self.assertTrue(P.runnable(f, {}, False))
                self.assertEqual(acc.call_args[0][1], os.X_OK)
            self.assertFalse(P.runnable(Path(d), {}, False))             # a folder is not a program


class TestDiscovery(unittest.TestCase):
    """WhyNot Cut's Claude Code discovery: exe first, `.cmd` last, sandbox rules, parity with the installer."""

    def _tree(self, d: Path) -> tuple:
        home = d / "home"
        appdata, local = home / "AppData" / "Roaming", home / "AppData" / "Local"
        pathdir = d / "pathbin"
        for rel in ("pathbin/claude.exe", "pathbin/claude",
                    "home/AppData/Local/Programs/claude/claude.exe", "home/.local/bin/claude.exe",
                    "home/.local/bin/claude", "home/.claude/local/claude", "home/AppData/Roaming/npm/claude.cmd",
                    "home/AppData/Roaming/Claude/claude-code/2.9.0/h1/claude.exe",
                    "home/AppData/Roaming/Claude/claude-code/2.10.1/h2/claude.exe",
                    "home/AppData/Roaming/Claude/claude-code/2.11.0/claude.exe",
                    "home/Library/Application Support/Claude/claude-code/2.9.0/h1/claude",
                    "home/Library/Application Support/Claude/claude-code/2.10.1/h2/claude",
                    "home/Library/Application Support/Claude/claude-code/2.11.0/claude",
                    "own/my-claude.exe", "own/stand-in.exe"):
            touch(d / rel)
        env = {"PATH": str(pathdir), "APPDATA": str(appdata), "LOCALAPPDATA": str(local),
               "CLAUDE_CLI": str(d / "own" / "my-claude.exe"), "WNC_CLAUDE_CLI": str(d / "own" / "stand-in.exe")}
        return home, env

    def _wnc_claude(self):
        if not (CORE / "wnc_installer" / "claude.py").is_file():
            self.skipTest("installer/core is not in this layout")
        with mock.patch.object(sys, "path", [str(CORE)] + sys.path):
            try:
                return importlib.import_module("wnc_installer.claude")
            except ImportError as e:
                self.skipTest("wnc_installer cannot be imported here: %s" % e)

    def test_parity_with_the_installer_discovery(self):
        wnc = self._wnc_claude()
        with tempfile.TemporaryDirectory() as d:
            home, env = self._tree(Path(d))
            for windows, plat in ((True, "win32"), (False, "darwin")):
                for sandbox in (False, True):
                    want = [str(p) for p in wnc.claude_candidates(env, home, plat, sandbox)]
                    got = [str(p) for p in P.claude_install_candidates(env, home, windows, sandbox)]
                    self.assertEqual(got, want, (plat, sandbox))
                    self.assertGreaterEqual(len(got), 4, (plat, sandbox))
            # newest bundle first, and the explicit $CLAUDE_CLI before PATH (the order itself is part of the parity)
            win = [str(p) for p in P.claude_install_candidates(env, home, True, False)]
            self.assertEqual(win[0], str(Path(d) / "own" / "my-claude.exe"))
            bundles = [x for x in win if "claude-code" in x]
            self.assertEqual(len(bundles), 3)
            self.assertIn("2.11.0", bundles[0])
            self.assertIn("2.10.1", bundles[1])
            sb = [str(p) for p in P.claude_install_candidates(env, home, True, True)]
            self.assertEqual(sb[0], str(Path(d) / "own" / "stand-in.exe"))
            self.assertNotIn(str(Path(d) / "own" / "my-claude.exe"), sb)       # a sandbox never follows $CLAUDE_CLI
            self.assertFalse(any(x.startswith(str(Path(d) / "pathbin")) for x in sb))

    def test_parity_with_the_installer_command_resolution(self):
        self._wnc_claude()
        base = importlib.import_module("wnc_installer.base")
        for p in ("C:/x/claude.exe", "/usr/local/bin/claude", "/t/stand-in.py", "/t/stand-in.SH"):
            self.assertEqual(P.claude_command(p), base.stand_in_command(p), p)

    def test_find_claude_code_prefers_the_exe_over_the_cmd_shim(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            home = d / "home"
            cmd = touch(home / "AppData" / "Roaming" / "npm" / "claude.cmd")
            exe = touch(home / ".local" / "bin" / "claude.exe")
            env = {"PATH": str(cmd.parent), "APPDATA": str(home / "AppData" / "Roaming")}
            self.assertEqual(_correct_module.find_claude_code(env, home, True), str(exe))
            exe.unlink()
            self.assertEqual(os.path.normcase(_correct_module.find_claude_code(env, home, True)),   # the only one: found
                             os.path.normcase(str(cmd)))                                            # (PATH says claude.CMD)
            cmd.unlink()
            self.assertIsNone(_correct_module.find_claude_code(env, home, True))

    def test_find_claude_code_skips_a_file_windows_cannot_start(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            home = d / "home"
            plain = touch(Path(d) / "pathbin" / "claude")                           # no extension: not a program on Windows
            env = {"PATH": "", "CLAUDE_CLI": str(plain), "APPDATA": str(home / "AppData" / "Roaming")}
            self.assertEqual(P.claude_install_candidates(env, home, True, False), [plain])     # found as a candidate ...
            with mock.patch("os.access", return_value=True):
                self.assertIsNone(_correct_module.find_claude_code(env, home, True))

    def test_find_claude_code_in_the_test_sandbox_ignores_path_and_claude_cli(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            home = d / "home"
            real = touch(d / "bin" / "claude.exe")
            env = {"PATH": str(real.parent), "CLAUDE_CLI": str(real), "WHYNOT_TEST_SANDBOX": "1"}
            self.assertIsNone(_correct_module.find_claude_code(env, home, True))
            env["WNC_CLAUDE_CLI"] = str(real)
            self.assertEqual(_correct_module.find_claude_code(env, home, True), str(real))

    def test_find_claude_code_without_arguments_never_leaves_the_sandbox(self):
        self.assertTrue(os.environ.get("WHYNOT_TEST_SANDBOX"))
        with mock.patch.dict(os.environ):
            os.environ.pop("WNC_CLAUDE_CLI", None)
            self.assertIsNone(_correct_module.find_claude_code())


class TestCmdShim(unittest.TestCase):
    """A `.cmd` CLI is never run through cmd.exe with the caption JSON on argv (BatBadBut)."""

    def _shim(self, d: Path, cli_js: bool = False, native: bool = False, node: bool = False) -> Path:
        shim = touch(d / "npm" / "claude.cmd")
        pkg = d / "npm" / "node_modules" / "@anthropic-ai" / "claude-code"
        if cli_js:
            touch(pkg / "cli.js")
        if native:
            touch(pkg / "bin" / "claude.exe")
        if node:
            touch(d / "npm" / "node.exe")
        return shim

    def test_cmd_resolves_to_node_cli_js(self):
        with tempfile.TemporaryDirectory() as d:
            shim = self._shim(Path(d), cli_js=True, node=True)
            cmd = P.claude_command(shim, {})
            self.assertEqual(cmd, [str(Path(d) / "npm" / "node.exe"),
                                   str(Path(d) / "npm" / "node_modules" / "@anthropic-ai" / "claude-code" / "cli.js")])
            self.assertFalse(P.is_batch(cmd[0]))

    def test_cmd_resolves_to_the_native_exe_when_the_package_ships_one(self):
        with tempfile.TemporaryDirectory() as d:
            shim = self._shim(Path(d), native=True, cli_js=True)
            cmd = P.claude_command(shim, {})
            self.assertEqual(len(cmd), 1)
            self.assertTrue(cmd[0].endswith("claude.exe") and "node_modules" in cmd[0])

    def test_cmd_without_a_program_next_to_it_is_refused_with_a_how(self):
        with tempfile.TemporaryDirectory() as d:
            shim = self._shim(Path(d))
            with self.assertRaises(RuntimeError) as cm:
                P.claude_command(shim, {"PATH": ""})
            self.assertIn("cmd.exe", str(cm.exception))
            self.assertIn("native installer", str(cm.exception))
            shim2 = self._shim(Path(d) / "b", cli_js=True)               # cli.js but no node anywhere
            with self.assertRaises(RuntimeError):
                P.claude_command(shim2, {"PATH": ""})

    def test_client_with_an_unresolvable_cmd_never_starts_a_process_and_keeps_the_source(self):
        with tempfile.TemporaryDirectory() as d:
            shim = self._shim(Path(d))
            calls = []
            client = ClaudeCodeClient(str(shim), runner=lambda *a: calls.append(a) or (0, "{}"), auth_runner=OK_AUTH)
            out, stats = correct(SRC, "rules", {}, "", client=client)
        self.assertEqual(calls, [])
        self.assertEqual(out, SRC)
        self.assertEqual(stats["error"], "cmd_shim_refused")
        self.assertIn("cmd.exe", stats["how"])

    def test_client_runs_the_resolved_program_not_the_shim_with_json_off_argv(self):
        seen = {}

        def runner(args, stdin, cwd):
            seen.update(args=args, stdin=stdin)
            return 0, json.dumps({"is_error": False, "structured_output": {"lines": FIXED}})

        with tempfile.TemporaryDirectory() as d:
            shim = self._shim(Path(d), native=True)
            out, stats = correct(SRC, "rules", {}, "", client=ClaudeCodeClient(str(shim), runner=runner, auth_runner=OK_AUTH))
        self.assertEqual(out, FIXED)
        self.assertFalse(P.is_batch(seen["args"][0]))
        self.assertNotIn("claude.cmd", " ".join(seen["args"]))
        self.assertEqual(json.loads(seen["stdin"])["lines"], SRC)

    def test_default_runner_refuses_a_batch_file_before_spawning(self):
        with mock.patch.object(subprocess, "Popen") as popen:
            with self.assertRaises(RuntimeError):
                _run_cli(["C:/x/claude.cmd", "-p"], "{}", ".")
            with self.assertRaises(RuntimeError):
                _run_cli(["C:/x/RUN.BAT"], "{}", ".")
        popen.assert_not_called()

    def test_py_and_sh_stand_ins_run_on_this_interpreter_or_bash(self):
        seen = []

        def runner(args, stdin, cwd):
            seen.append(args)
            return 0, json.dumps({"is_error": False, "structured_output": {"lines": FIXED}})

        correct(SRC, "rules", {}, "", client=ClaudeCodeClient("/t/fake-claude.py", runner=runner, auth_runner=OK_AUTH))
        self.assertEqual(seen[0][:3], [sys.executable, "-B", "/t/fake-claude.py"])


class TestTempFolderAndCancel(unittest.TestCase):
    def test_temp_folder_prefix_and_cleanup(self):
        seen = {}

        def runner(args, stdin, cwd):
            seen["cwd"] = cwd
            seen["exists"] = os.path.isdir(cwd)
            return 0, json.dumps({"is_error": False, "structured_output": {"lines": FIXED}})

        correct(SRC, "rules", {}, "", client=ClaudeCodeClient("/x/claude", runner=runner, auth_runner=OK_AUTH))
        self.assertTrue(os.path.basename(seen["cwd"]).startswith("wnc-kalam-cc-"))
        self.assertTrue(seen["exists"])
        self.assertFalse(os.path.exists(seen["cwd"]))

    def _sleeper(self, pidfile=None):
        code = "import time; time.sleep(120)"
        if pidfile:
            code = ("import subprocess, sys, time\n"
                    "g = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(120)'])\n"
                    "open(%r, 'w').write(str(g.pid))\n"
                    "time.sleep(120)\n" % str(pidfile))
        return [sys.executable, "-c", code]

    def _alive(self, pid: int) -> bool:
        if sys.platform == "win32":
            out = subprocess.run(["tasklist", "/FI", "PID eq %d" % pid, "/NH"], capture_output=True, text=True, timeout=30).stdout
            return str(pid) in out
        try:
            os.kill(pid, 0)
        except OSError:
            return False
        return True

    def test_timeout_kills_the_cli(self):
        procs, realc = [], subprocess.Popen.communicate

        def communicate(self, *a, **k):
            procs.append(self)
            return realc(self, *a, **k)

        with mock.patch.object(_correct_module, "CLI_TIMEOUT", 1), \
                mock.patch.object(subprocess.Popen, "communicate", communicate), \
                mock.patch.object(_correct_module, "kill_tree", wraps=_correct_module.kill_tree) as kt:
            with self.assertRaises(subprocess.TimeoutExpired):
                _run_cli(self._sleeper(), "", ".")
        kt.assert_called_once()
        self.assertIsNotNone(procs[0].wait(timeout=30))                  # procs[0] is the CLI (the first communicate)

    def test_cancel_kills_the_process_tree(self):
        procs, realc = [], subprocess.Popen.communicate
        with tempfile.TemporaryDirectory() as d:
            pidfile, state = Path(d) / "grandchild.pid", {"n": 0}

            def communicate(self, *a, **k):
                state["n"] += 1
                if state["n"] == 1:                       # the user cancels once the CLI has started its own child
                    procs.append(self)
                    deadline = time.time() + 60
                    while not pidfile.exists() and time.time() < deadline:
                        time.sleep(0.1)
                    time.sleep(0.2)
                    raise KeyboardInterrupt
                return realc(self, *a, **k)

            with mock.patch.object(subprocess.Popen, "communicate", communicate):
                with self.assertRaises(KeyboardInterrupt):
                    _run_cli(self._sleeper(pidfile), "", d)
            self.assertIsNotNone(procs[0].poll())
            grandchild = int(pidfile.read_text(encoding="utf-8"))
            # Windows: kill_tree walks the tree with taskkill /T; POSIX: the CLI's process group is killed (_kill_cli)
            deadline = time.time() + 30
            while self._alive(grandchild) and time.time() < deadline:
                time.sleep(0.2)
            gone = not self._alive(grandchild)
            if not gone:
                os.kill(grandchild, 9)                    # never leave it behind, then fail
            self.assertTrue(gone, "the CLI's child survived the cancel")

    def test_a_cancelled_parallel_run_kills_the_tracked_cli(self):
        import contextvars
        import threading
        from lib import parallel
        run = parallel._Run()
        token = parallel._RUN.set(run)
        try:
            ctx = contextvars.copy_context()
        finally:
            parallel._RUN.reset(token)
        result = []
        t = threading.Thread(target=lambda: result.append(ctx.run(_run_cli, self._sleeper(), "", ".")))
        t.start()
        deadline = time.time() + 60
        while not run.procs and time.time() < deadline:
            time.sleep(0.05)
        self.assertTrue(run.procs, "the CLI was not registered with the parallel run")
        proc = next(iter(run.procs))
        run.cancel()                                      # what an interrupted parallel_map does
        t.join(timeout=60)
        self.assertFalse(t.is_alive())
        self.assertIsNotNone(proc.poll())
        self.assertNotEqual(result[0][0], 0)
        self.assertFalse(run.procs, "the finished CLI is untracked")


class TestLazyAnthropic(unittest.TestCase):
    def test_module_imports_without_anthropic(self):
        pkg = sys.modules["lib.kalam"]
        with mock.patch.dict(sys.modules, {"anthropic": None}):         # None in sys.modules: `import anthropic` raises
            sys.modules.pop("lib.kalam.correct", None)
            try:
                mod = importlib.import_module("lib.kalam.correct")
                self.assertIsNot(mod, _correct_module)                   # a fresh import really ran
                self.assertFalse(hasattr(mod, "anthropic"))
                self.assertEqual(mod._api_errors(), ())
            finally:
                sys.modules["lib.kalam.correct"] = _correct_module     # keep the module the other tests hold
                pkg.correct = _correct_module

    def test_api_backend_without_the_package_says_so_and_keeps_the_source(self):
        with mock.patch.dict(sys.modules, {"anthropic": None}):
            out, stats = correct(SRC, "rules", {}, "sk-test-key")
        self.assertEqual(out, SRC)
        self.assertEqual(stats["error"], "anthropic_missing")
        self.assertEqual(stats["kept_source"], [0, 1, 2])
        self.assertIn("subscription", stats["how"])
        self.assertIn("anthropic", stats["how"])

    def test_api_backend_with_the_package_builds_the_client_lazily(self):
        with fake_api_modules() as (anthropic, _httpx2):
            out, stats = correct(SRC, "rules", {}, "sk-test-key")
            made = list(anthropic.Anthropic.made)
        self.assertEqual(out, FIXED)
        self.assertEqual(made, [{"api_key": "sk-test-key", "max_retries": 3}])

    def test_api_errors_are_caught_only_when_the_package_exists(self):
        with fake_api_modules() as (anthropic, _httpx2):
            self.assertEqual(_correct_module._api_errors(), (anthropic.APIError,))
            out, stats = correct(SRC, "rules", {}, "k", client=FakeClient(anthropic.APIError("boom")))
        self.assertEqual(out, SRC)
        self.assertEqual(stats["error"], "APIError")


class TestCwdRelativeIsNeverTrusted(unittest.TestCase):
    """Task 10 review I1: shutil.which looks in the current folder first on Windows (unless the process has
    NoDefaultCurrentDirectoryInExePath). A claude.exe / node.exe planted in a project folder must never be started."""

    @contextlib.contextmanager
    def _cwd(self, path):
        old = os.getcwd()
        os.chdir(path)
        try:
            yield
        finally:
            os.chdir(old)

    def test_absolute_only_keeps_absolute_paths(self):
        absolute = str(Path(tempfile.gettempdir()) / "claude.exe")
        self.assertEqual(P.absolute_only([absolute, "claude.exe", ".\\claude.EXE", "bin/claude", "", None]), [absolute])
        self.assertEqual(P.absolute_only([Path(absolute), Path("claude.exe")]), [Path(absolute)])

    def test_find_claude_code_ignores_relative_and_empty_path_entries_everywhere(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            planted = touch(d / "cwd" / "claude.exe")
            touch(d / "cwd" / "sub" / "claude.exe")
            home = d / "home"
            for path in ("", ".", os.pathsep.join(["", "."]), "sub", os.pathsep.join([".", "sub"])):
                env = {"PATH": path, "APPDATA": str(home / "AppData" / "Roaming")}
                with self._cwd(planted.parent):
                    self.assertIsNone(_correct_module.find_claude_code(env, home, True), path)

    def test_find_claude_code_still_finds_the_real_install_next_to_a_planted_one(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            touch(d / "cwd" / "claude.exe")
            home = d / "home"
            real = touch(home / ".local" / "bin" / "claude.exe")
            env = {"PATH": ".", "APPDATA": str(home / "AppData" / "Roaming")}
            with self._cwd(d / "cwd"):
                self.assertEqual(_correct_module.find_claude_code(env, home, True), str(real))

    def test_node_must_be_absolute_and_not_a_batch_file(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            shim = touch(d / "npm" / "claude.cmd")
            touch(d / "npm" / "node_modules" / "@anthropic-ai" / "claude-code" / "cli.js")
            planted = touch(d / "cwd" / "node.exe")
            for path in ("", ".", "cwd", os.pathsep.join(["", ".", "cwd"])):          # relative / empty PATH entries only
                with self._cwd(d):
                    with self.assertRaises(P.CmdShimRefused, msg=path):
                        P.claude_command(shim, {"PATH": path}, windows=True)
            touch(d / "bin" / "node.cmd")                                           # a batch node is never used
            with self.assertRaises(P.CmdShimRefused):
                P.claude_command(shim, {"PATH": str(d / "bin")}, windows=True)
            real = touch(d / "bin2" / "node.exe")
            self.assertEqual(os.path.normcase(P.claude_command(shim, {"PATH": str(d / "bin2")}, windows=True)[0]),
                             os.path.normcase(str(real)))
            self.assertTrue(planted.is_file())

    @unittest.skipUnless(sys.platform == "win32", "shutil.which searches the current folder on Windows only")
    def test_windows_planted_claude_exe_and_node_exe_in_the_cwd_are_not_used(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            planted_claude = touch(d / "cwd" / "claude.exe", "")
            touch(d / "cwd" / "node.exe", "")
            (d / "emptybin").mkdir()
            home = d / "home"
            shim = touch(d / "npm" / "claude.cmd")
            touch(d / "npm" / "node_modules" / "@anthropic-ai" / "claude-code" / "cli.js")
            env = {"PATH": str(d / "emptybin"), "APPDATA": str(home / "AppData" / "Roaming")}
            with mock.patch.dict(os.environ):
                os.environ.pop("NoDefaultCurrentDirectoryInExePath", None)      # a panel- or launcher-started engine
                with self._cwd(d / "cwd"):
                    self.assertTrue(P.shutil.which("claude", path=env["PATH"]), "the premise: which() does see the cwd")
                    self.assertIsNone(_correct_module.find_claude_code(env, home, True))
                    with self.assertRaises(P.CmdShimRefused):
                        P.claude_command(shim, env)
            self.assertTrue(planted_claude.is_file())


class TestShimRefusalIsACodeWithAHow(unittest.TestCase):
    """Task 10 review M2: stats["error"] is a short code, the help text is stats["how"]; make_client surfaces it."""

    def _shim(self, d, cli_js=False):
        shim = touch(Path(d) / "npm" / "claude.cmd")
        if cli_js:
            touch(Path(d) / "npm" / "node_modules" / "@anthropic-ai" / "claude-code" / "cli.js")
        return shim

    def test_refused_shim_gives_a_code_and_a_how(self):
        with tempfile.TemporaryDirectory() as d:
            client = ClaudeCodeClient(str(self._shim(d)), runner=lambda *a: (0, "{}"), auth_runner=OK_AUTH)
            out, stats = correct(SRC, "rules", {}, "", client=client)
        self.assertEqual(out, SRC)
        self.assertEqual(stats["error"], "cmd_shim_refused")
        self.assertIn("cmd.exe", stats["how"])
        self.assertEqual(stats["kept_source"], [0, 1, 2])

    def test_make_client_surfaces_the_refusal(self):
        with tempfile.TemporaryDirectory() as d:
            c, notice = make_client({}, finder=lambda: str(self._shim(d)))
        self.assertIsNone(c)
        self.assertEqual(notice, "cmd_shim_refused")
        self.assertIn("cmd.exe", _correct_module.notice_how(notice))
        self.assertIsNone(_correct_module.notice_how("claude_code_missing"))

    def test_make_client_still_returns_a_client_for_a_resolvable_shim(self):
        with tempfile.TemporaryDirectory() as d:
            shim = self._shim(d)
            touch(Path(d) / "npm" / "node_modules" / "@anthropic-ai" / "claude-code" / "bin" / "claude.exe")
            c, notice = make_client({}, finder=lambda: str(shim))
        self.assertTrue(isinstance(c, ClaudeCodeClient) and notice is None)

    def test_a_node_cmd_gets_a_message_about_node_not_about_the_cli(self):
        with tempfile.TemporaryDirectory() as d:
            shim = self._shim(d, cli_js=True)
            node_cmd = touch(Path(d) / "bin" / "node.cmd")
            with mock.patch.dict(os.environ, {"PATH": str(node_cmd.parent)}):
                with self.assertRaises(P.CmdShimRefused) as cm:
                    P.claude_command(shim, {"PATH": str(node_cmd.parent)})
                client = ClaudeCodeClient(str(shim), runner=lambda *a: (0, "{}"), auth_runner=OK_AUTH)
                out, stats = correct(SRC, "rules", {}, "", client=client)
            how = str(cm.exception)
        self.assertIn("Node.js", how)
        self.assertNotIn("was not found next to it", how)
        self.assertEqual(stats["error"], "cmd_shim_refused")
        self.assertIn("Node.js", stats["how"])


class TestProcessGroupKill(unittest.TestCase):
    """Task 10 review M3: on POSIX the CLI leads its own process group and a cancel kills the group (fake-backed here,
    a real one on a POSIX machine); on Windows the tree is killed by taskkill /T through lib/parallel.kill_tree."""

    def test_spawn_kwargs(self):
        self.assertEqual(_correct_module._spawn_kwargs(posix=True), {"start_new_session": True})
        self.assertEqual(_correct_module._spawn_kwargs(posix=False), {})

    def test_kill_cli_kills_the_group_first_then_the_process_on_posix(self):
        proc = types.SimpleNamespace(pid=4242)
        order = []
        with mock.patch.object(os, "killpg", lambda pgid, sig: order.append(("killpg", pgid, sig)), create=True), \
                mock.patch.object(_correct_module, "kill_tree", lambda p: order.append(("kill_tree", p.pid))):
            _correct_module._kill_cli(proc, posix=True)
        self.assertEqual([o[0] for o in order], ["killpg", "kill_tree"])
        self.assertEqual(order[0][1], 4242)
        self.assertEqual(order[0][2], getattr(__import__("signal"), "SIGKILL", 9))

    def test_kill_cli_ignores_a_group_that_is_already_gone(self):
        def gone(pgid, sig):
            raise ProcessLookupError

        with mock.patch.object(os, "killpg", gone, create=True), \
                mock.patch.object(_correct_module, "kill_tree") as kt:
            _correct_module._kill_cli(types.SimpleNamespace(pid=1), posix=True)
        kt.assert_called_once()

    def test_kill_cli_on_windows_is_kill_tree_only(self):
        with mock.patch.object(os, "killpg", create=True) as kp, mock.patch.object(_correct_module, "kill_tree") as kt:
            _correct_module._kill_cli(types.SimpleNamespace(pid=7), posix=False)
        kp.assert_not_called()
        kt.assert_called_once()

    @unittest.skipUnless(os.name == "posix", "a real process group needs POSIX")
    def test_posix_cancel_kills_the_clis_own_child(self):
        helper = TestTempFolderAndCancel()
        with tempfile.TemporaryDirectory() as d:
            pidfile = Path(d) / "grandchild.pid"
            realc = subprocess.Popen.communicate
            state = {"n": 0}

            def communicate(self, *a, **k):
                state["n"] += 1
                if state["n"] == 1:
                    deadline = time.time() + 60
                    while not pidfile.exists() and time.time() < deadline:
                        time.sleep(0.1)
                    time.sleep(0.2)
                    raise KeyboardInterrupt
                return realc(self, *a, **k)

            with mock.patch.object(subprocess.Popen, "communicate", communicate):
                with self.assertRaises(KeyboardInterrupt):
                    _run_cli(helper._sleeper(pidfile), "", d)
            grandchild = int(pidfile.read_text(encoding="utf-8"))
            deadline = time.time() + 15
            while helper._alive(grandchild) and time.time() < deadline:
                time.sleep(0.2)
            self.assertFalse(helper._alive(grandchild))


class TestCancelStopsCorrection(unittest.TestCase):
    """Task 10 review M5: after a cancel no new batch starts and the result says "cancelled", not "exit 1"."""

    def _run(self):
        from lib import parallel
        run = parallel._Run()
        token = parallel._RUN.set(run)
        return run, lambda: parallel._RUN.reset(token)

    def test_no_new_batch_starts_after_the_run_was_cancelled(self):
        src = ["كلمة %d هنا" % i for i in range(130)]
        run, done = self._run()

        class CancellingClient(FakeClient):
            def create(self, **kw):
                resp = FakeClient.create(self, **kw)
                run.cancel()                               # the editor pressed cancel while batch 1 was answering
                return resp

        c = CancellingClient(src[0:60], src[60:120], src[120:130])
        try:
            out, stats = correct(src, "rules", {}, "key", client=c)
        finally:
            done()
        self.assertEqual(len(c.requests), 1)
        self.assertEqual(stats["error"], "cancelled")
        self.assertEqual(out, src)
        self.assertEqual(stats["kept_source"], list(range(60, 130)))
        self.assertEqual(stats["fallback"], 70)

    def test_a_cli_killed_by_the_cancel_reports_cancelled_not_exit_1(self):
        run, done = self._run()

        def runner(args, stdin, cwd):
            run.cancel()
            return 1, ""                                   # what a killed `claude -p` leaves behind

        try:
            out, stats = correct(SRC, "rules", {}, "", client=ClaudeCodeClient("/x/claude", runner=runner, auth_runner=OK_AUTH))
        finally:
            done()
        self.assertEqual(out, SRC)
        self.assertEqual(stats["error"], "cancelled")

    def test_without_a_cancel_nothing_changes(self):
        c = FakeClient(FIXED)
        out, stats = correct(SRC, "rules", {}, "key", client=c)
        self.assertTrue(out == FIXED and stats["error"] is None)


class TestSubscriptionNeverInheritsApiKeys(unittest.TestCase):
    """Task 10 review M4 (executor ruling): the subscription backend runs `claude -p` with an explicit environment that has
    neither ANTHROPIC_API_KEY nor ANTHROPIC_AUTH_TOKEN, so it can never fall into API billing silently (nothing paid)."""

    # the API keys and the provider switches (Bedrock / Vertex / a proxy base URL): any of them can send the call to a paid
    # provider, so none may reach the subscription child (executor ruling, Task 10 M4 + follow-up)
    KEYS = {"ANTHROPIC_API_KEY": "sk-test-parent-key", "ANTHROPIC_AUTH_TOKEN": "tok-test-parent-token",
            "CLAUDE_CODE_USE_BEDROCK": "1", "CLAUDE_CODE_USE_VERTEX": "1",
            "ANTHROPIC_BASE_URL": "https://proxy.example.invalid/v1"}

    def test_the_child_env_handed_to_popen_lacks_both_keys_while_the_parent_has_them(self):
        seen = {}

        class StubPopen:
            def __init__(self, args, **kw):
                seen.update(kw)
                self.pid, self.returncode = 4242, 0

            def communicate(self, *a, **k):
                return "{}", ""

            def poll(self):
                return 0

        with mock.patch.dict(os.environ, dict(self.KEYS, KEEP_ME="1")), \
                mock.patch.object(subprocess, "Popen", StubPopen):
            code, out = _run_cli(["/x/claude", "-p"], "{}", ".")
            self.assertEqual((code, out), (0, "{}"))
            env = seen.get("env")
            self.assertIsInstance(env, dict, "the child gets an explicit environment")
            for key in self.KEYS:
                self.assertNotIn(key, env)
            self.assertEqual(env.get("KEEP_ME"), "1")                      # everything else is inherited
            self.assertEqual({k: os.environ.get(k) for k in self.KEYS}, self.KEYS)   # the parent is untouched

    def test_a_real_child_process_does_not_see_the_keys(self):
        names = list(self.KEYS)
        code = "import os; print(' '.join(str(os.environ.get(k)) for k in %r + ['KEEP_ME']))" % (names,)
        with mock.patch.dict(os.environ, dict(self.KEYS, KEEP_ME="1")):
            rc, out = _run_cli([sys.executable, "-c", code], "", ".")
            self.assertEqual(out.strip(), " ".join(["None"] * len(names) + ["1"]))
            self.assertEqual({k: os.environ.get(k) for k in self.KEYS}, self.KEYS)
        self.assertEqual(rc, 0)

    def test_client_default_runner_path_uses_it(self):
        """the REAL default runner (no runner= given), driven through the Popen seam: the env it hands over lacks the keys"""
        seen = {}

        class StubPopen:
            def __init__(self, args, **kw):
                seen.setdefault("calls", []).append((args, kw))
                self.args = args
                self.pid, self.returncode = 4242, 0

            def communicate(self, *a, **k):
                if "auth" in self.args:
                    return auth_json(), ""
                return json.dumps({"is_error": False, "structured_output": {"lines": FIXED}}), ""

            def poll(self):
                return 0

        client = ClaudeCodeClient("/x/claude")
        self.assertIs(client.runner, _run_cli)
        with mock.patch.dict(os.environ, dict(self.KEYS, KEEP_ME="1")), mock.patch.object(subprocess, "Popen", StubPopen):
            out, stats = correct(SRC, "rules", {}, "", client=client)
            self.assertEqual({k: os.environ.get(k) for k in self.KEYS}, self.KEYS)
        self.assertTrue(out == FIXED and stats["error"] is None)
        self.assertEqual(len(seen["calls"]), 2)                       # the auth preflight, then the -p call
        for args, kw in seen["calls"]:
            env = kw.get("env")
            self.assertIsInstance(env, dict)
            self.assertTrue(all(k not in env for k in self.KEYS))
            self.assertEqual(env.get("KEEP_ME"), "1")

    def test_child_env_matching_is_case_insensitive_on_windows_only(self):
        base = {"anthropic_api_key": "a", "Anthropic_Auth_Token": "b", "ANTHROPIC_API_KEY": "c", "PATH": "p",
                "claude_code_use_bedrock": "1", "Claude_Code_Use_Vertex": "1", "anthropic_base_url": "u"}
        self.assertEqual(_correct_module._child_env(base, windows=True), {"PATH": "p"})
        self.assertEqual(_correct_module._child_env(base, windows=False),
                         {"anthropic_api_key": "a", "Anthropic_Auth_Token": "b", "PATH": "p",
                          "claude_code_use_bedrock": "1", "Claude_Code_Use_Vertex": "1", "anthropic_base_url": "u"})
        self.assertEqual(_correct_module._child_env({"CLAUDE_CODE_USE_BEDROCK": "1", "ANTHROPIC_BASE_URL": "u", "X": "1"},
                                                    windows=False), {"X": "1"})
        self.assertEqual(base["ANTHROPIC_API_KEY"], "c")                     # the input mapping is not modified

    def test_the_api_backend_keeps_its_key_and_never_builds_a_child_env(self):
        with fake_api_modules() as (anthropic, _httpx2), \
                mock.patch.object(_correct_module, "_child_env", wraps=_correct_module._child_env) as ce, \
                mock.patch.object(subprocess, "Popen") as popen, mock.patch.dict(os.environ, self.KEYS):
            out, stats = correct(SRC, "rules", {}, "sk-test-api-key")
            made = list(anthropic.Anthropic.made)
            self.assertEqual({k: os.environ.get(k) for k in self.KEYS}, self.KEYS)
        self.assertEqual(out, FIXED)
        self.assertEqual(made, [{"api_key": "sk-test-api-key", "max_retries": 3}])
        ce.assert_not_called()
        popen.assert_not_called()


class TestCancelReachesTheProcessGroup(unittest.TestCase):
    """Task 10 re-review M3a: a cancel goes through lib/parallel (kill_tree = the CLI only off Windows). A grandchild that
    holds the pipes would keep communicate() waiting for CLI_TIMEOUT, so what is tracked is a handle whose kill() also
    kills the process group."""

    def _stub(self, dead):
        class StubPopen:
            made = []

            def __init__(self, args, **kw):
                self.args, self.kw, self.pid, self.returncode = args, kw, 987654, None
                StubPopen.made.append(self)

            def communicate(self, *a, **k):
                dead.wait(30)                        # blocked on the pipes until the CLI is killed
                self.returncode = -9
                return "", ""

            def poll(self):
                return -9 if dead.is_set() else None

            def kill(self):
                dead.set()

        return StubPopen

    def test_a_cancelled_run_kills_the_group_through_the_tracked_handle(self):
        import contextvars
        import threading
        from lib import parallel
        dead, killed = threading.Event(), []
        stub = self._stub(dead)
        run = parallel._Run()
        token = parallel._RUN.set(run)
        try:
            ctx = contextvars.copy_context()
        finally:
            parallel._RUN.reset(token)

        def off_windows_kill_tree(proc):             # what lib/parallel.kill_tree does off Windows: the process itself
            if proc.poll() is None:
                proc.kill()

        with mock.patch.object(_correct_module, "_is_posix", lambda: True), \
                mock.patch.object(os, "killpg", lambda pgid, sig: killed.append((pgid, sig)), create=True), \
                mock.patch.object(subprocess, "Popen", stub), \
                mock.patch.object(parallel, "kill_tree", off_windows_kill_tree):
            result = []
            t = threading.Thread(target=lambda: result.append(ctx.run(_run_cli, ["/x/claude", "-p"], "{}", ".")))
            t.start()
            deadline = time.time() + 30
            while not run.procs and time.time() < deadline:
                time.sleep(0.02)
            self.assertTrue(run.procs, "the CLI was not registered with the parallel run")
            run.cancel()
            t.join(timeout=30)
        self.assertFalse(t.is_alive(), "communicate() was still waiting after the cancel")
        self.assertTrue(dead.is_set())
        self.assertTrue(killed, "the cancel never reached killpg")
        self.assertEqual({pgid for pgid, _sig in killed}, {987654})
        self.assertTrue(stub.made[0].kw.get("start_new_session"))
        self.assertFalse(run.procs)

    def test_is_posix_follows_the_os(self):
        self.assertEqual(_correct_module._is_posix(), os.name == "posix")


class TestPathSearchSkipsPlantedFiles(unittest.TestCase):
    """Task 10 re-review R1-N1: a planted claude.exe in the cwd must not hide the real CLI further down PATH. The port
    searches each ABSOLUTE PATH folder itself (PATHEXT order on Windows); relative and empty entries are skipped."""

    def test_find_on_path_walks_absolute_folders_in_pathext_order_and_skips_the_rest(self):
        nc = os.path.normcase
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            first, second = d / "first", d / "second"
            touch(first / "claude.cmd")
            touch(second / "claude.exe")
            touch(d / "cwd" / "claude.exe")
            path = os.pathsep.join(["", ".", "cwd", str(first), '"%s"' % second])
            old = os.getcwd()
            os.chdir(d)
            try:
                got = P.find_on_path("claude", path, windows=True, env={})
                every = [nc(x) for x in P.iter_on_path("claude", path, windows=True, env={})]
                only_exe = P.find_on_path("claude", path, windows=True, env={"PATHEXT": ".EXE"})
                nothing = P.find_on_path("claude", os.pathsep.join(["", ".", "cwd"]), windows=True, env={})
            finally:
                os.chdir(old)
        self.assertEqual(nc(got), nc(str(first / "claude.cmd")))                 # folder by folder, then PATHEXT
        self.assertEqual(every, [nc(str(first / "claude.cmd")), nc(str(second / "claude.exe"))])
        self.assertEqual(nc(only_exe), nc(str(second / "claude.exe")))
        self.assertIsNone(nothing)

    def test_find_claude_code_finds_the_real_cli_behind_a_planted_one(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            touch(d / "cwd" / "claude.exe")
            real = touch(d / "realbin" / "claude.exe")
            home = d / "home"
            env = {"PATH": os.pathsep.join(["", ".", str(d / "realbin")]), "APPDATA": str(home / "AppData" / "Roaming")}
            old = os.getcwd()
            os.chdir(d / "cwd")
            try:
                got = _correct_module.find_claude_code(env, home, True)
            finally:
                os.chdir(old)
            self.assertEqual(os.path.normcase(got), os.path.normcase(str(real)))

    @unittest.skipUnless(sys.platform == "win32", "shutil.which searches the current folder on Windows only")
    def test_windows_real_which_would_have_hidden_it(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            touch(d / "cwd" / "claude.exe", "")
            real = touch(d / "realbin" / "claude.exe", "")
            home = d / "home"
            env = {"PATH": str(d / "realbin"), "APPDATA": str(home / "AppData" / "Roaming")}
            with mock.patch.dict(os.environ):
                os.environ.pop("NoDefaultCurrentDirectoryInExePath", None)
                old = os.getcwd()
                os.chdir(d / "cwd")
                try:
                    self.assertFalse(os.path.isabs(str(P.shutil.which("claude", path=env["PATH"]))),
                                     "the premise: which() returns the planted, relative file")
                    self.assertEqual(os.path.normcase(_correct_module.find_claude_code(env, home, True)),
                                     os.path.normcase(str(real)))
                finally:
                    os.chdir(old)

    def test_node_behind_a_planted_or_batch_node_is_found(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            shim = touch(d / "npm" / "claude.cmd")
            touch(d / "npm" / "node_modules" / "@anthropic-ai" / "claude-code" / "cli.js")
            touch(d / "cwd" / "node.exe")
            touch(d / "nvm" / "node.cmd")
            real = touch(d / "real" / "node.exe")
            env = {"PATH": os.pathsep.join(["", ".", str(d / "nvm"), str(d / "real")])}
            old = os.getcwd()
            os.chdir(d / "cwd")
            try:
                cmd = P.claude_command(shim, env, windows=True)
            finally:
                os.chdir(old)
            self.assertEqual(os.path.normcase(cmd[0]), os.path.normcase(str(real)))

    @unittest.skipUnless(sys.platform == "win32", "compares with the Windows behaviour of shutil.which")
    def test_the_walk_agrees_with_shutil_which_when_every_entry_is_absolute(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            touch(d / "a" / "claude.com")
            touch(d / "b" / "claude.exe")
            touch(d / "c" / "claude.cmd")
            path = os.pathsep.join(str(d / x) for x in "abc")
            with mock.patch.dict(os.environ, {"PATHEXT": ".COM;.EXE;.BAT;.CMD", "NoDefaultCurrentDirectoryInExePath": "1"}):
                want = P.shutil.which("claude", path=path)
            got = P.find_on_path("claude", path, windows=True, env={})
            self.assertEqual(os.path.normcase(got), os.path.normcase(want))

    def test_a_relative_claude_cli_variable_is_dropped_and_the_real_one_found(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            touch(d / "cwd" / "claude.exe")
            real = touch(d / "realbin" / "claude.exe")
            home = d / "home"
            env = {"CLAUDE_CLI": "claude.exe", "PATH": str(d / "realbin"), "APPDATA": str(home / "AppData" / "Roaming")}
            old_cwd = os.getcwd()
            os.chdir(d / "cwd")
            try:
                got = _correct_module.find_claude_code(env, home, True)
            finally:
                os.chdir(old_cwd)
            self.assertEqual(os.path.normcase(got), os.path.normcase(str(real)))

    def test_claude_install_candidates_takes_an_injected_which_and_keeps_the_rest(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            home = d / "home"
            real = touch(d / "realbin" / "claude.exe")
            local = touch(home / ".local" / "bin" / "claude.exe")
            env = {"PATH": "", "APPDATA": str(home / "AppData" / "Roaming")}
            got = P.claude_install_candidates(env, home, True, False, which=lambda name, path=None: str(real))
            self.assertEqual(got, [real, local])                   # which() is 2nd after $CLAUDE_CLI, then the fixed paths


class TestPathWalkOnPosixRules(unittest.TestCase):
    """Task 10 re-review 2 R3-N1: macOS / Linux discovery goes through iter_on_path(windows=False); the Windows-flavoured
    tests above never reach that branch (the name is searched as given: no PATHEXT, execute bit decides)."""

    def test_windows_false_walks_absolute_folders_in_order_and_skips_the_rest(self):
        nc = os.path.normcase
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            a, b = touch(d / "a" / "claude"), touch(d / "b" / "claude")
            for f in (a, b, touch(d / "e" / "claude.exe")):
                os.chmod(f, 0o755)
            (d / "c" / "claude").mkdir(parents=True)                  # a FOLDER named claude is not a program
            touch(d / "cwd" / "claude")
            os.chmod(d / "cwd" / "claude", 0o755)
            path = os.pathsep.join(["", ".", "cwd", str(d / "c"), str(a.parent), '"%s"' % b.parent, str(d / "e")])
            old = os.getcwd()
            os.chdir(d)
            try:
                every = [nc(x) for x in P.iter_on_path("claude", path, windows=False, env={})]
                first = P.find_on_path("claude", path, windows=False, env={})
                none = P.find_on_path("claude", os.pathsep.join(["", ".", "cwd"]), windows=False, env={})
                only_exe_dir = P.find_on_path("claude", str(d / "e"), windows=False, env={})
            finally:
                os.chdir(old)
        self.assertEqual(every, [nc(str(a)), nc(str(b))])               # folder order; no PATHEXT lookup (claude.exe is not "claude")
        self.assertEqual(nc(first), nc(str(a)))
        self.assertIsNone(none)
        self.assertIsNone(only_exe_dir)

    @unittest.skipIf(os.name == "nt", "the execute bit only means something on POSIX")
    def test_posix_the_execute_bit_decides(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            plain = touch(d / "first" / "claude")
            os.chmod(plain, 0o644)
            runnable = touch(d / "second" / "claude")
            os.chmod(runnable, 0o755)
            path = os.pathsep.join([str(plain.parent), str(runnable.parent)])
            self.assertEqual(P.find_on_path("claude", path, windows=False, env={}), str(runnable))
            self.assertEqual(list(P.iter_on_path("claude", str(plain.parent), windows=False, env={})), [])

    def test_find_claude_code_uses_the_posix_walk_for_a_mac_layout(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            real = touch(d / "bin" / "claude")
            os.chmod(real, 0o755)
            home = d / "home"
            env = {"PATH": os.pathsep.join([".", str(d / "bin")])}
            old = os.getcwd()
            os.chdir(d)
            try:
                got = _correct_module.find_claude_code(env, home, False)
            finally:
                os.chdir(old)
            self.assertEqual(os.path.normcase(got), os.path.normcase(str(real)))


class TestCancelBetweenRetries(unittest.TestCase):
    """Task 10 re-review M5 nit: a cancel between the two attempts of one batch starts no second request or process."""

    def test_no_second_request_after_a_cancel(self):
        from lib import parallel
        run = parallel._Run()
        token = parallel._RUN.set(run)

        class CancellingClient(FakeClient):
            def create(self, **kw):
                resp = FakeClient.create(self, **kw)
                run.cancel()
                return resp

        c = CancellingClient(FIXED[:2], FIXED)           # a wrong count: the retry would normally run
        try:
            out, stats = correct(SRC, "rules", {}, "key", client=c)
        finally:
            parallel._RUN.reset(token)
        self.assertEqual(len(c.requests), 1)
        self.assertEqual(out, SRC)
        self.assertEqual(stats["error"], "cancelled")
        self.assertEqual(stats["kept_source"], [0, 1, 2])

    def test_no_second_cli_process_after_a_cancel(self):
        from lib import parallel
        run = parallel._Run()
        token = parallel._RUN.set(run)
        calls = []

        def runner(args, stdin, cwd):
            calls.append(1)
            run.cancel()
            return 0, json.dumps({"is_error": False, "structured_output": {"lines": FIXED[:2]}})   # wrong count

        try:
            out, stats = correct(SRC, "rules", {}, "", client=ClaudeCodeClient("/x/claude", runner=runner, auth_runner=OK_AUTH))
        finally:
            parallel._RUN.reset(token)
        self.assertEqual(len(calls), 1)
        self.assertEqual(stats["error"], "cancelled")

    def test_without_a_cancel_the_retry_still_runs(self):
        c = FakeClient(FIXED[:2], FIXED)
        out, stats = correct(SRC, "rules", {}, "key", client=c)
        self.assertEqual((out, len(c.requests)), (FIXED, 2))


class TestSubscriptionAuthPreflight(unittest.TestCase):
    """Executor ruling (TOOLS-NOTE-claude-p-auth-sources): `claude -p` can bill an API key from settings env / apiKeyHelper
    even with a clean child env, and the subscription login comes last in its auth precedence. So once per job,
    `claude --safe-mode auth status` runs with the same env and a neutral cwd; unless authMethod == "claude.ai" the
    subscription backend does not start `claude -p` (error "subscription_not_active", or "auth_status_unavailable" when
    the check itself fails) and the captions keep their source text. Only authMethod / loggedIn are ever used or shown."""

    METHODS = {"api_key": "ANTHROPIC_API_KEY", "api_key_helper": "apiKeyHelper", "oauth_token": "CLAUDE_CODE_OAUTH_TOKEN",
               "third_party": "cloud provider", "none": "/login"}

    def _pair(self, auth, calls=None, lines=None):
        def runner(args, stdin, cwd):
            if calls is not None:
                calls.append(("p", args))
            return 0, json.dumps({"is_error": False, "structured_output": {"lines": lines or FIXED}})

        def auth_runner(args, cwd):
            if calls is not None:
                calls.append(("auth", args, cwd, os.path.isdir(cwd)))
            if isinstance(auth, Exception):
                raise auth
            return auth

        return ClaudeCodeClient("/x/claude", runner=runner, auth_runner=auth_runner)

    def test_claude_ai_runs_the_correction_and_the_check_ran_once_for_the_whole_job(self):
        src = ["كلمة %d هنا" % i for i in range(130)]            # 3 batches: 3 `-p` calls, one auth check
        calls = []
        client = self._pair((0, auth_json()), calls, lines=None)

        def runner(args, stdin, cwd):
            calls.append(("p", args))
            return 0, json.dumps({"is_error": False, "structured_output": {"lines": json.loads(stdin)["lines"]}})

        client.runner = runner
        out, stats = correct(src, "rules", {}, "", client=client)
        self.assertEqual(out, src)
        self.assertIsNone(stats["error"])
        self.assertEqual([c[0] for c in calls], ["auth", "p", "p", "p"])
        kind, args, cwd, existed = calls[0]
        self.assertEqual(args, ["/x/claude", "--safe-mode", "auth", "status"])       # no prompt text, no -p flags
        self.assertTrue(os.path.basename(cwd).startswith("wnc-kalam-cc-") and existed)
        self.assertFalse(os.path.exists(cwd))

    def test_every_other_auth_method_refuses_without_starting_claude_p(self):
        for method, source in self.METHODS.items():
            calls = []
            client = self._pair((0 if method != "none" else 1, auth_json(method, logged_in=method != "none")), calls)
            out, stats = correct(SRC, "rules", {}, "", client=client)
            self.assertEqual([c[0] for c in calls], ["auth"], method)               # `claude -p` never started
            self.assertEqual(out, SRC, method)
            self.assertEqual(stats["error"], "subscription_not_active", method)
            self.assertEqual(stats["kept_source"], [0, 1, 2], method)
            how = stats["how"]
            self.assertIn(source, how, method)
            self.assertIn("subscription", how.lower(), method)
            self.assertTrue(re.search("[\u0600-\u06FF]", how), "the how text has Arabic as well: %s" % method)
            if method != "none":
                self.assertIn(method, how)                                          # the method found is named

    def test_the_how_text_says_what_to_change(self):
        client = self._pair((0, auth_json("api_key")))
        _out, stats = correct(SRC, "rules", {}, "", client=client)
        self.assertIn("WhyNot Kalam only uses your Claude subscription", stats["how"])
        self.assertIn("remove", stats["how"])
        self.assertIn("turn Kalam correction off", stats["how"])

    def test_logged_in_false_even_with_claude_ai_is_a_refusal(self):
        client = self._pair((1, auth_json("claude.ai", logged_in=False)))
        _out, stats = correct(SRC, "rules", {}, "", client=client)
        self.assertEqual(stats["error"], "subscription_not_active")
        self.assertIn("/login", stats["how"])

    def test_a_check_that_cannot_be_trusted_refuses_as_unavailable(self):
        cases = {"missing": OSError("no such file"), "timeout": subprocess.TimeoutExpired("claude", 60),
                 "not json": (1, "error: unknown command"), "empty": (0, ""), "list": (0, "[]"),
                 "no method": (0, json.dumps({"loggedIn": True})), "method not text": (0, json.dumps({"authMethod": 5}))}
        for name, auth in cases.items():
            calls = []
            out, stats = correct(SRC, "rules", {}, "", client=self._pair(auth, calls))
            self.assertEqual([c[0] for c in calls], ["auth"], name)
            self.assertEqual(out, SRC, name)
            self.assertEqual(stats["error"], "auth_status_unavailable", name)
            self.assertIn("subscription", stats["how"].lower(), name)

    def test_an_unexpected_auth_method_value_is_not_echoed(self):
        client = self._pair((0, auth_json("weird method with spaces and ev1l <script>")))
        _out, stats = correct(SRC, "rules", {}, "", client=client)
        self.assertEqual(stats["error"], "subscription_not_active")
        self.assertNotIn("<script>", stats["how"])
        self.assertIn("unknown", stats["how"])

    def test_the_answer_is_cached_for_the_job_including_a_refusal(self):
        calls = []
        client = self._pair((0, auth_json("api_key")), calls)
        correct(SRC, "rules", {}, "", client=client)
        correct(SRC, "rules", {}, "", client=client)
        self.assertEqual([c[0] for c in calls], ["auth"])

    def test_no_identity_value_reaches_stats_the_how_text_or_the_exception(self):
        secrets = [FAKE_IDENTITY["email"], FAKE_IDENTITY["orgId"], FAKE_IDENTITY["orgName"], FAKE_IDENTITY["token"]]
        auth = (0, auth_json("api_key", token=FAKE_IDENTITY["token"]))
        for method_auth in (auth, (0, auth_json("claude.ai", token=FAKE_IDENTITY["token"])),
                            (1, "Not logged in as %s (%s)" % (FAKE_IDENTITY["email"], FAKE_IDENTITY["orgName"]))):
            client = self._pair(method_auth)
            out, stats = correct(SRC, "rules", {}, "", client=client)
            blob = json.dumps([out, stats], ensure_ascii=False)
            for secret in secrets:
                self.assertNotIn(secret, blob)
        with self.assertRaises(_correct_module.SubscriptionRefused) as cm:
            _correct_module.check_subscription("/x/claude", auth_runner=lambda args, cwd: auth)
        for secret in secrets:
            self.assertNotIn(secret, str(cm.exception))
            self.assertNotIn(secret, repr(cm.exception))

    def test_check_subscription_returns_the_method_only(self):
        self.assertEqual(_correct_module.check_subscription("/x/claude", auth_runner=OK_AUTH), "claude.ai")

    def test_correction_line_for_the_doctor(self):
        ok = _correct_module.correction_line("/x/claude", auth_runner=OK_AUTH)
        self.assertEqual(ok["ok"], True)
        self.assertEqual(ok["authMethod"], "claude.ai")
        self.assertIn("subscription (claude.ai)", ok["line"])
        bad = _correct_module.correction_line("/x/claude", auth_runner=lambda a, c: (0, auth_json("api_key_helper")))
        self.assertEqual((bad["ok"], bad["code"]), (False, "subscription_not_active"))
        self.assertIn("apiKeyHelper", bad["line"])
        none = _correct_module.correction_line(None)
        self.assertEqual((none["ok"], none["code"]), (False, "claude_code_missing"))
        blob = json.dumps([ok, bad, none], ensure_ascii=False)
        for secret in FAKE_IDENTITY.values():
            self.assertNotIn(secret, blob)

    def test_a_real_process_end_to_end_with_a_stand_in_cli(self):
        """the real default runners (Popen, stripped env, neutral cwd) against a stand-in `claude` script"""
        script = (
            "import json, os, sys\n"
            "log = os.environ.get('FAKE_CLAUDE_LOG')\n"
            "names = ['ANTHROPIC_API_KEY', 'ANTHROPIC_AUTH_TOKEN', 'CLAUDE_CODE_USE_BEDROCK', 'CLAUDE_CODE_USE_VERTEX',\n"
            "         'ANTHROPIC_BASE_URL']\n"
            "with open(log, 'a', encoding='utf-8') as f:\n"
            "    f.write(json.dumps({'argv': sys.argv[1:], 'leaked': [n for n in names if n in os.environ],\n"
            "                        'cwd': os.path.basename(os.getcwd())}) + '\\n')\n"
            "if 'auth' in sys.argv:\n"
            "    print(json.dumps({'loggedIn': True, 'authMethod': os.environ.get('FAKE_METHOD', 'claude.ai'),\n"
            "                      'email': 'ali.example@example.invalid'}))\n"
            "    sys.exit(0)\n"
            "lines = json.loads(sys.stdin.read())['lines']\n"
            "print(json.dumps({'is_error': False, 'structured_output': {'lines': lines}}))\n")
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            fake = touch(d / "fake-claude.py", script)
            log = d / "calls.jsonl"
            env = dict(FAKE_CLAUDE_LOG=str(log), ANTHROPIC_API_KEY="sk-test-parent-key", CLAUDE_CODE_USE_BEDROCK="1",
                       ANTHROPIC_BASE_URL="https://proxy.example.invalid")
            with mock.patch.dict(os.environ, env):
                out, stats = correct(SRC, "rules", {}, "", client=ClaudeCodeClient(str(fake)))
                self.assertEqual((out, stats["error"]), (SRC, None))
                with mock.patch.dict(os.environ, {"FAKE_METHOD": "api_key"}):
                    out2, stats2 = correct(SRC, "rules", {}, "", client=ClaudeCodeClient(str(fake)))
            calls = [json.loads(x) for x in log.read_text(encoding="utf-8").splitlines()]
            self.assertEqual(stats2["error"], "subscription_not_active")
            self.assertEqual(out2, SRC)
            self.assertEqual(len(calls), 3)                                   # auth + -p, then auth only (refused)
            self.assertEqual(calls[0]["argv"][-3:], ["--safe-mode", "auth", "status"])
            self.assertIn("-p", calls[1]["argv"])
            for c in calls:
                self.assertEqual(c["leaked"], [])
                self.assertTrue(c["cwd"].startswith("wnc-kalam-cc-"))
            self.assertNotIn("example.invalid", json.dumps([stats, stats2]))


class TestCorrectProvenance(unittest.TestCase):
    def test_headers(self):
        pkg = HERE.parent / "engine" / "reel" / "lib" / "kalam"
        for name in ("correct", "platform"):
            head = (pkg / (name + ".py")).read_text(encoding="utf-8").splitlines()[:3]
            self.assertEqual(head[0], "# SPDX-License-Identifier: GPL-3.0-or-later")
            self.assertEqual(head[1], "# © 2026 The Why Not AI (thewhynot.ai)")
            self.assertTrue(head[2].startswith("# Ported from the owner's Kalam engine (kalam/%s.py);" % name), head[2])

    def test_contract_schema_and_constants_are_the_owners(self):
        upstream = HERE.parents[1] / "adobe" / "tools" / "kalam" / "_upstream" / "engine" / "kalam" / "correct.py"
        if not upstream.is_file():
            self.skipTest("adobe/tools is not part of the plugin zip")
        up = upstream.read_text(encoding="utf-8")
        mine = (HERE.parent / "engine" / "reel" / "lib" / "kalam" / "correct.py").read_text(encoding="utf-8")
        start, end = up.index("CONTRACT = "), up.index("class _Text")
        self.assertEqual(mine[mine.index("CONTRACT = "):mine.index("class _Text")], up[start:end])      # CONTRACT + SCHEMA
        faith = lambda s: s[s.index("# ---- faithfulness"):s.index("def correct(")]            # noqa: E731
        self.assertEqual(faith(mine), faith(up))
        for const in ('MODEL = "claude-opus-5-5"', "BATCH = 60", "CONTEXT = 3", "MIN_KEEP = 0.6"):
            self.assertIn(const, mine)
            self.assertIn(const, up)


if __name__ == "__main__":
    unittest.main()
