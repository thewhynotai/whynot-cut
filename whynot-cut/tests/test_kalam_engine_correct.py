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
  * The upstream test_every_user_approved_demo_correction_passes reads demo/sherif_raw_model.srt and the user-approved
    twin demo/sherif_corrected.srt (28 captions); those files were never supplied and name a real person. They are
    replaced by a fictional Egyptian-Arabic pair written for this test, same structure (28 SRT blocks each, the model's
    raw lines with Arabic-script spellings of English terms and spelling slips, and the corrected lines with the Latin
    terms and fixed spelling, every pair must pass the faithfulness gate): tests/test_kalam_fixtures/
    example_raw_model.srt and example_corrected.srt (a home-bakery talk, no real names).
  * Fixture scan: the two upstream files hold no real name or machine path other than the demo file names above.

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

        out, stats = correct(SRC, "rules", {}, "", client=ClaudeCodeClient("/x/claude", runner=runner))
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
        out, stats = correct(SRC, "rules", {}, "", client=ClaudeCodeClient("/x/claude", runner=runner))
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
            client = ClaudeCodeClient(str(shim), runner=lambda *a: calls.append(a) or (0, "{}"))
            out, stats = correct(SRC, "rules", {}, "", client=client)
        self.assertEqual(calls, [])
        self.assertEqual(out, SRC)
        self.assertIn("cmd.exe", stats["error"])

    def test_client_runs_the_resolved_program_not_the_shim_with_json_off_argv(self):
        seen = {}

        def runner(args, stdin, cwd):
            seen.update(args=args, stdin=stdin)
            return 0, json.dumps({"is_error": False, "structured_output": {"lines": FIXED}})

        with tempfile.TemporaryDirectory() as d:
            shim = self._shim(Path(d), native=True)
            out, stats = correct(SRC, "rules", {}, "", client=ClaudeCodeClient(str(shim), runner=runner))
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

        correct(SRC, "rules", {}, "", client=ClaudeCodeClient("/t/fake-claude.py", runner=runner))
        self.assertEqual(seen[0][:3], [sys.executable, "-B", "/t/fake-claude.py"])


class TestTempFolderAndCancel(unittest.TestCase):
    def test_temp_folder_prefix_and_cleanup(self):
        seen = {}

        def runner(args, stdin, cwd):
            seen["cwd"] = cwd
            seen["exists"] = os.path.isdir(cwd)
            return 0, json.dumps({"is_error": False, "structured_output": {"lines": FIXED}})

        correct(SRC, "rules", {}, "", client=ClaudeCodeClient("/x/claude", runner=runner))
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

        with mock.patch.object(_correct_module, "CLI_TIMEOUT", 1),                 mock.patch.object(subprocess.Popen, "communicate", communicate),                 mock.patch.object(_correct_module, "kill_tree", wraps=_correct_module.kill_tree) as kt:
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
            if sys.platform == "win32":                   # kill_tree walks the tree with taskkill /T on Windows only
                deadline = time.time() + 30
                while self._alive(grandchild) and time.time() < deadline:
                    time.sleep(0.2)
                self.assertFalse(self._alive(grandchild), "the CLI's child survived the cancel")
            elif self._alive(grandchild):                 # POSIX: only the CLI itself is killed (lib/parallel.kill_tree)
                os.kill(grandchild, 9)

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
