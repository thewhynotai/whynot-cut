"""3.0 T1.9: plugin options reach `reel` on every shell; both wrappers pass arguments and odd paths intact.

  * bin/reel.cmd (Windows, run as `cmd /c`) and bin/reel (bash; Git Bash on Windows) hand the engine its arguments
    unchanged: Arabic, `$`, `)`, `%` (`100% Natural`), `!`, `^`, and an engine home with a space and parentheses.
  * The SessionStart hook writes the plugin options to CLAUDE_ENV_FILE with shell quoting (Arabic survives) and to the
    pointer file ~/.whynot-cut/plugin-options.json, which PowerShell commands need (they never receive path-valued
    variables from the env file). plat.engine_home(), plat.clients_root_setting() and both wrappers read it, then
    Claude Code's own record (~/.claude/settings.json pluginConfigs), then the default and legacy homes.
The engine echo used here is env-gated (WHYNOT_DEBUG_ARGV=1: cli.py prints its argv and WHYNOT_HOME, then exits).
Never touches the real ~/.whynot-cut or ~/.claude: HOME / USERPROFILE / CLAUDE_CONFIG_DIR point to temp folders.
Run:
    ~/.whynot-cut/venv/Scripts/python.exe -B -m unittest discover -s <plugin>/tests -p test_wrappers.py -v
"""
import sys as _sys
_sys.dont_write_bytecode = True  # keep the plugin folder free of __pycache__
import json
import os
import shlex
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SK = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SK / "engine" / "reel"))

from lib import plat, settings  # noqa: E402

IS_WIN = os.name == "nt"
CMD = SK / "bin" / "reel.cmd"
BASH_WRAPPER = SK / "bin" / "reel"
CTX = SK / "hooks" / "session_context.py"
PLUGIN_ID = "whynot-cut@thewhynot-ai"
OPTION_KEYS = ("WHYNOT_HOME", "CLAUDE_PLUGIN_OPTION_ENGINE_HOME", "REEL_HOME", "CLAUDE_PLUGIN_OPTION_REEL_HOME",
               "NH_ENV_DIR", "WHYNOT_OPTIONS_FILE", "CLAUDE_CONFIG_DIR", "WHYNOT_CLIENTS_ROOT",
               "CLAUDE_PLUGIN_OPTION_CLIENTS_ROOT", "REEL_CLIENTS_ROOT", "CLAUDE_PLUGIN_DATA", "CLAUDE_ENV_FILE",
               "WHYNOT_DEBUG_ARGV")
ARABIC = "عيادة د. نهلة"
ARGS = ["status", "--root", f"D:/{ARABIC}/100% Natural", "a$b", "$(echo pwned)", "x)y", "(p)", ARABIC, "100%",
        "50%%", "%1", "%~1", "%*", "a%b%c", "a^b c", "!bang!"]


def git_bash():
    for b in (os.environ.get("GIT_BASH"), r"C:\Program Files\Git\bin\bash.exe", shutil.which("bash")):
        if b and Path(b).exists() and "system32" not in b.lower():
            return b
    return None


def clean_env(user_home: Path, **extra) -> dict:
    """No plugin option or engine home from the real machine; the user's home is a temp folder."""
    env = {k: v for k, v in os.environ.items() if k not in OPTION_KEYS}
    env.update(HOME=str(user_home), USERPROFILE=str(user_home), WHYNOT_DEBUG_ARGV="1", PYTHONUTF8="1",
               CLAUDE_CONFIG_DIR=str(user_home / ".claude"))
    env.update({k: str(v) for k, v in extra.items()})
    return env


def make_engine(home: Path) -> Path:
    """A real (tiny) venv at <home>/venv, enough for the engine's stdlib-only argv echo."""
    import venv
    venv.EnvBuilder(with_pip=False, symlinks=not IS_WIN).create(str(home / "venv"))
    return home


def norm(p: str) -> str:
    return os.path.normcase(os.path.normpath(plat.native_path(p)))


def cmd_line(args, delayed=False, wrapper=CMD) -> str:
    """What PowerShell / cmd hand to cmd.exe: the wrapper and every argument in double quotes."""
    return (f'cmd /d {"/v:on " if delayed else ""}/s /c ""{wrapper}" ' + " ".join(f'"{a}"' for a in args) + '"')


def run_cmd(args, env, delayed=False, wrapper=CMD):
    r = subprocess.run(cmd_line(args, delayed, wrapper), capture_output=True, env=env, timeout=120)
    return r.returncode, r.stdout.decode("utf-8", "replace"), r.stderr.decode("utf-8", "replace")


def run_bash(args, env):
    r = subprocess.run([git_bash(), str(BASH_WRAPPER), *args], capture_output=True, env=env, timeout=120)
    return r.returncode, r.stdout.decode("utf-8", "replace"), r.stderr.decode("utf-8", "replace")


def echo_of(rc, out, err) -> dict:
    assert rc == 0, (rc, out, err)
    return json.loads(out.strip().splitlines()[-1])


def write_pointer(user_home: Path, engine_home="", clients_root="") -> Path:
    f = user_home / ".whynot-cut" / "plugin-options.json"
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps({"clients_root": clients_root, "engine_home": engine_home, "updated": "test"},
                            ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return f


def write_claude_settings(user_home: Path, options: dict, plugin_id=PLUGIN_ID) -> Path:
    f = user_home / ".claude" / "settings.json"
    f.parent.mkdir(parents=True, exist_ok=True)
    data = {"enabledPlugins": {"other@x": True, plugin_id: True},
            "pluginConfigs": {"other@x": {"options": {"engine_home": "C:/not-this-one"}},
                              plugin_id: {"options": options}},
            "theme": "dark"}
    f.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return f


class WrapperCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.t = Path(self.tmp.name)
        self.user = self.t / "user home"
        self.user.mkdir()

    def tearDown(self):
        self.tmp.cleanup()

    def shells(self):
        """(name, runner) for every wrapper this machine can run."""
        out = []
        if IS_WIN:
            out.append(("reel.cmd", run_cmd))
        if git_bash():
            out.append(("bin/reel", run_bash))
        if not out:
            self.skipTest("no shell for either wrapper")
        return out


# ===================================================================================================== arguments
class TestArgumentsSurvive(WrapperCase):
    @unittest.skipUnless(IS_WIN, "reel.cmd is the Windows wrapper")
    def test_cmd_passes_arguments_and_odd_home_intact(self):
        home = make_engine(self.t / "eng home (1)")
        got = echo_of(*run_cmd(ARGS, clean_env(self.user, WHYNOT_HOME=home)))
        self.assertEqual(got["argv"], ARGS)
        self.assertEqual(norm(got["whynot_home"]), norm(str(home)))

    @unittest.skipUnless(IS_WIN, "reel.cmd is the Windows wrapper")
    def test_cmd_survives_delayed_expansion(self):
        """DelayedExpansion on (registry default or cmd /v:on) must not eat `!` in arguments."""
        home = make_engine(self.t / "eng home")
        args = ["status", "hi! there!", "100% Natural", f"{ARABIC}!"]
        got = echo_of(*run_cmd(args, clean_env(self.user, WHYNOT_HOME=home), delayed=True))
        self.assertEqual(got["argv"], args)

    @unittest.skipUnless(IS_WIN, "reel.cmd is the Windows wrapper")
    def test_cmd_blocked_message_with_odd_home(self):
        """No engine yet, home with a space, `)`, `&` and `%`: still the one-line JSON refusal, nothing else."""
        rc, out, err = run_cmd(["status"], clean_env(self.user, WHYNOT_HOME=self.t / "R&D (x) 100% home"))
        self.assertEqual(rc, 2, (out, err))
        blocked = json.loads(out.strip().splitlines()[-1])
        self.assertIn("engine not installed", blocked["blocked"])
        self.assertNotIn("3.10", blocked["how"])
        self.assertIn("reel setup", blocked["how"])
        self.assertNotIn("unexpected", err)
        self.assertNotIn("is not recognized", err)

    def test_bash_passes_arguments_and_odd_home_intact(self):
        if not git_bash():
            self.skipTest("no bash")
        home = make_engine(self.t / "eng home (1)")
        got = echo_of(*run_bash(ARGS, clean_env(self.user, WHYNOT_HOME=home)))
        self.assertEqual(got["argv"], ARGS)
        self.assertEqual(norm(got["whynot_home"]), norm(str(home)))

    def test_debug_echo_is_env_gated(self):
        """Without WHYNOT_DEBUG_ARGV the engine runs normally (here: --version)."""
        env = clean_env(self.user, WHYNOT_HOME=self.t / "x")
        env.pop("WHYNOT_DEBUG_ARGV")
        r = subprocess.run([sys.executable, "-B", str(SK / "engine/reel/cli.py"), "--version"], capture_output=True,
                           text=True, encoding="utf-8", env=env)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertNotIn('"argv"', r.stdout)
        self.assertIn("WhyNot Cut", r.stdout)


# ===================================================================================================== engine home
class TestWrappersFindTheEngineHome(WrapperCase):
    def check(self, expected: Path, **extra):
        for name, run in self.shells():
            with self.subTest(wrapper=name):
                got = echo_of(*run(["status"], clean_env(self.user, **extra)))
                self.assertEqual(norm(got["whynot_home"]), norm(str(expected)))

    def test_pointer_file_engine_home(self):
        """PowerShell gets no path-valued env-file variables: the pointer the SessionStart hook wrote is the source."""
        home = make_engine(self.t / f"{ARABIC} (2) & co" / "engine")
        write_pointer(self.user, engine_home=str(home))
        self.check(home)

    def test_pointer_engine_home_with_tilde(self):
        home = make_engine(self.user / "my engine")
        write_pointer(self.user, engine_home="~/my engine")
        self.check(home)

    def test_env_beats_pointer(self):
        home = make_engine(self.t / "from env")
        write_pointer(self.user, engine_home=str(make_engine(self.t / "from pointer")))
        self.check(home, WHYNOT_HOME=home)

    def test_claude_settings_when_no_pointer(self):
        home = make_engine(self.t / "from settings")
        write_claude_settings(self.user, {"engine_home": str(home), "clients_root": "D:/x"})
        self.check(home)

    def test_pointer_is_authoritative_over_claude_settings(self):
        make_engine(self.user / ".whynot-cut")
        write_pointer(self.user, engine_home="")
        write_claude_settings(self.user, {"engine_home": str(make_engine(self.t / "stale"))})
        self.check(self.user / ".whynot-cut")

    def test_legacy_dr_nahla_home_in_both_wrappers(self):
        legacy = make_engine(self.user / ".dr-nahla-editor")
        self.check(legacy)

    def test_legacy_home_when_default_holds_only_the_pointer(self):
        """The hook's pointer creates ~/.whynot-cut; that must not hide a legacy engine (3 GB of models)."""
        legacy = make_engine(self.user / ".reel-editor")
        write_pointer(self.user)
        self.check(legacy)


# ===================================================================================================== plat
class TestPlatReadsSavedOptions(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.user = Path(self.tmp.name) / "user"
        self.user.mkdir()
        env = {k: v for k, v in os.environ.items() if k not in OPTION_KEYS}
        env.update(HOME=str(self.user), USERPROFILE=str(self.user), CLAUDE_CONFIG_DIR=str(self.user / ".claude"))
        self.env = mock.patch.dict(os.environ, env, clear=True)
        self.env.start()

    def tearDown(self):
        self.env.stop()
        self.tmp.cleanup()

    def test_pointer_values(self):
        write_pointer(self.user, engine_home=f"D:/{ARABIC}/eng", clients_root=f"D:/{ARABIC}/clients")
        self.assertEqual(plat.engine_home(), Path(f"D:/{ARABIC}/eng"))
        self.assertEqual(plat.clients_root_setting(), Path(f"D:/{ARABIC}/clients"))

    def test_pointer_tilde(self):
        write_pointer(self.user, engine_home="~/eng", clients_root="~/Clients")
        self.assertEqual(plat.engine_home(), self.user / "eng")
        self.assertEqual(plat.clients_root_setting(), self.user / "Clients")

    def test_env_wins(self):
        write_pointer(self.user, engine_home="D:/p", clients_root="D:/c")
        with mock.patch.dict(os.environ, {"WHYNOT_HOME": "D:/e", "WHYNOT_CLIENTS_ROOT": "D:/r"}):
            self.assertEqual(plat.engine_home(), Path("D:/e"))
            self.assertEqual(plat.clients_root_setting(), Path("D:/r"))

    def test_empty_pointer_means_unset(self):
        write_pointer(self.user)
        write_claude_settings(self.user, {"engine_home": "D:/stale", "clients_root": "D:/stale"})
        self.assertEqual(plat.engine_home(), self.user / ".whynot-cut")
        self.assertIsNone(plat.clients_root_setting())

    def test_claude_settings_fallback(self):
        write_claude_settings(self.user, {"engine_home": "D:/s/eng", "clients_root": "D:/s/clients"})
        self.assertEqual(plat.engine_home(), Path("D:/s/eng"))
        self.assertEqual(plat.clients_root_setting(), Path("D:/s/clients"))

    def test_claude_settings_other_marketplace_name(self):
        write_claude_settings(self.user, {"clients_root": "D:/dev/clients"}, plugin_id="whynot-cut@local-dev")
        self.assertEqual(plat.clients_root_setting(), Path("D:/dev/clients"))

    def test_corrupt_pointer_falls_back(self):
        f = write_pointer(self.user)
        f.write_text("{not json", encoding="utf-8")
        write_claude_settings(self.user, {"clients_root": "D:/s/clients"})
        self.assertEqual(plat.clients_root_setting(), Path("D:/s/clients"))

    def test_nothing_saved(self):
        self.assertEqual(plat.engine_home(), self.user / ".whynot-cut")
        self.assertIsNone(plat.clients_root_setting())

    def test_legacy_home_when_default_holds_only_the_pointer(self):
        (self.user / ".dr-nahla-editor" / "venv").mkdir(parents=True)
        write_pointer(self.user)
        self.assertEqual(plat.engine_home(), self.user / ".dr-nahla-editor")
        (self.user / ".whynot-cut" / "venv").mkdir()
        self.assertEqual(plat.engine_home(), self.user / ".whynot-cut")

    def test_preferences_found_under_pointer_clients_root(self):
        base = self.user / "Clients"
        (base / ".claude").mkdir(parents=True)
        prefs = base / ".claude" / settings.FILE
        prefs.write_text("---\nlanguage: ar\n---\n", encoding="utf-8")
        write_pointer(self.user, clients_root=str(base))
        anchor = Path(Path(self.tmp.name).anchor)      # no parent of the temp folder may hold a preferences file
        if (anchor / ".claude" / settings.FILE).exists():
            self.skipTest("a preferences file at the drive root")
        self.assertEqual(settings.find(anchor), prefs)


# ===================================================================================================== SessionStart
class TestSessionStartOptions(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.t = Path(self.tmp.name)
        self.user = self.t / "user"
        self.user.mkdir()
        self.pointer = self.user / ".whynot-cut" / "plugin-options.json"

    def tearDown(self):
        self.tmp.cleanup()

    def hook(self, data=True, env_file=True, **opts):
        env = {k: v for k, v in os.environ.items() if k not in OPTION_KEYS}
        env.update(HOME=str(self.user), USERPROFILE=str(self.user), CLAUDE_CONFIG_DIR=str(self.user / ".claude"),
                   CLAUDE_PLUGIN_ROOT=str(SK))
        if env_file:
            env["CLAUDE_ENV_FILE"] = str(self.t / "env.sh")
        if data:
            env["CLAUDE_PLUGIN_DATA"] = str(self.t / "data")
        env.update({f"CLAUDE_PLUGIN_OPTION_{k.upper()}": v for k, v in opts.items()})
        r = subprocess.run([sys.executable, "-B", str(CTX)], input=json.dumps({"cwd": str(self.t)}),
                           capture_output=True, text=True, encoding="utf-8", env=env)
        self.assertEqual(r.returncode, 0, r.stderr)
        return r

    def test_env_file_quotes_arabic_paths_for_the_shell(self):
        eng = f"D:/{ARABIC}/محرك $HOME `x` 'q'"
        self.hook(engine_home=eng, clients_root=f"D:/{ARABIC}")
        text = (self.t / "env.sh").read_text(encoding="utf-8")
        self.assertIn(f"export WHYNOT_HOME={shlex.quote(eng)}\n", text)
        self.assertIn(f"export WHYNOT_CLIENTS_ROOT={shlex.quote(f'D:/{ARABIC}')}\n", text)
        self.assertNotIn("\\u", text)
        bash = git_bash()
        if bash:
            r = subprocess.run([bash, "-c", 'source "$1"; printf "%s|%s" "$WHYNOT_HOME" "$WHYNOT_CLIENTS_ROOT"', "_",
                                (self.t / "env.sh").as_posix()], capture_output=True)
            self.assertEqual(r.stdout.decode("utf-8"), f"{eng}|D:/{ARABIC}")

    def test_pointer_written_and_kept_current(self):
        self.hook(engine_home=f"D:/{ARABIC}/eng", clients_root="D:/Clients")
        d = json.loads(self.pointer.read_text(encoding="utf-8"))
        self.assertEqual((d["engine_home"], d["clients_root"]), (f"D:/{ARABIC}/eng", "D:/Clients"))
        self.assertTrue(d["updated"])
        self.assertIn(ARABIC, self.pointer.read_text(encoding="utf-8"))          # literal UTF-8, one key per line
        first = self.pointer.read_text(encoding="utf-8")
        self.hook(engine_home=f"D:/{ARABIC}/eng", clients_root="D:/Clients")
        self.assertEqual(self.pointer.read_text(encoding="utf-8"), first)        # unchanged options: not rewritten
        self.hook(clients_root="D:/Clients")                                       # engine_home cleared
        d = json.loads(self.pointer.read_text(encoding="utf-8"))
        self.assertEqual((d["engine_home"], d["clients_root"]), ("", "D:/Clients"))

    def test_pointer_written_even_with_no_options(self):
        self.hook()
        d = json.loads(self.pointer.read_text(encoding="utf-8"))
        self.assertEqual((d["engine_home"], d["clients_root"]), ("", ""))

    def test_no_pointer_outside_a_real_session_start(self):
        """A bare run of the script (tests, by hand) lacks CLAUDE_PLUGIN_DATA or CLAUDE_ENV_FILE and never writes
        ~/.whynot-cut."""
        self.hook(data=False, engine_home="D:/eng")
        self.hook(env_file=False, engine_home="D:/eng")
        self.assertFalse(self.pointer.exists())
        self.assertFalse((self.user / ".whynot-cut").exists())


# ===================================================================================================== reel.cmd setup
@unittest.skipUnless(IS_WIN, "reel.cmd is the Windows wrapper")
class TestCmdSetupPython(WrapperCase):
    """`reel setup` with no engine: `py -3` when the launcher exists (once, never again with `python`), else the
    first `python` on PATH that is not a Windows Store stub."""

    def setUp(self):
        super().setUp()
        self.plug = self.t / "plug"
        (self.plug / "bin").mkdir(parents=True)
        shutil.copy2(CMD, self.plug / "bin" / "reel.cmd")
        (self.plug / ".claude-plugin").mkdir()
        shutil.copy2(SK / ".claude-plugin/plugin.json", self.plug / ".claude-plugin/plugin.json")
        (self.plug / "setup").mkdir()
        self.record = self.t / "setup-runs.txt"
        (self.plug / "setup" / "setup_env.py").write_text(
            "import os, sys\n"
            "with open(os.environ['SETUP_RECORD'], 'a', encoding='utf-8') as f:\n"
            "    f.write(sys.executable + '\\n')\n"
            "sys.exit(1)\n", encoding="utf-8")
        self.sys32 = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32"
        self.real_py = make_engine(self.t / "sys python") / "venv" / "Scripts"

    def run_setup(self, path_dirs):
        env = clean_env(self.user, WHYNOT_HOME=self.t / "new home", SETUP_RECORD=self.record,
                        PATH=os.pathsep.join(str(d) for d in path_dirs))
        rc, out, err = run_cmd(["setup"], env, wrapper=self.plug / "bin" / "reel.cmd")
        runs = self.record.read_text(encoding="utf-8").splitlines() if self.record.exists() else []
        return rc, out, err, runs

    def fake_exe(self, folder: Path, name: str) -> Path:
        """An executable that fails with any Python-style arguments (a copy of where.exe)."""
        folder.mkdir(parents=True, exist_ok=True)
        shutil.copy2(self.sys32 / "where.exe", folder / name)
        return folder

    def test_failed_py_setup_is_not_run_again_with_python(self):
        fake = self.fake_exe(self.t / "launcher", "py.exe")
        rc, out, err, runs = self.run_setup([fake, self.real_py, self.sys32])
        self.assertEqual(rc, 2, (out, err))
        self.assertEqual(runs, [], "setup ran a second time with python after py -3 failed")

    def test_store_stub_skipped(self):
        stub = self.fake_exe(self.t / "Microsoft" / "WindowsApps", "python.exe")
        rc, out, err, runs = self.run_setup([stub, self.real_py, self.sys32])
        self.assertEqual(rc, 2, (out, err))
        self.assertEqual(len(runs), 1, (out, err))


# ===================================================================================================== hook runner
class TestRunPythonLegacyHome(unittest.TestCase):
    def test_legacy_engine_when_default_holds_only_the_pointer(self):
        bash = git_bash()
        if not bash:
            self.skipTest("no bash")
        with tempfile.TemporaryDirectory() as t:
            user = Path(t) / "user"
            write_pointer(user)
            for rel in ("venv/Scripts/python.exe", "venv/bin/python"):
                f = user / ".reel-editor" / rel
                f.parent.mkdir(parents=True, exist_ok=True)
                f.write_text('#!/bin/sh\necho LEGACY "$@"\n', encoding="utf-8", newline="\n")
                f.chmod(0o755)
            env = {k: v for k, v in os.environ.items() if k not in OPTION_KEYS}
            env.update(HOME=str(user), USERPROFILE=str(user))
            r = subprocess.run([bash, str(SK / "hooks/run_python.sh"), "x.py"], capture_output=True, text=True,
                               encoding="utf-8", env=env)
        self.assertTrue(r.stdout.startswith("LEGACY"), (r.stdout, r.stderr))


# ===================================================================================================== docs
class TestOnePythonPhrase(unittest.TestCase):
    PHRASE = "Python 3.12 (installed by WhyNot Cut)"

    def user_facing(self):
        files = [SK / "README.md", SK / "bin" / "reel.cmd", *(SK / "skills").rglob("*.md"), *(SK / "agents").glob("*.md")]
        return {f: f.read_text(encoding="utf-8") for f in files}

    def test_no_competing_version_advice(self):
        for f, text in self.user_facing().items():
            for old in ("3.10–3.12", "3.10-3.12", "3.10 - 3.12", "is best)"):
                self.assertFalse(old in text, f"{f.relative_to(SK)} still says {old!r}")

    def test_the_phrase_is_used(self):
        for rel in ("README.md", "skills/setup/SKILL.md", "skills/setup/references/platform-setup.md",
                    "agents/setup-doctor.md"):
            self.assertIn(self.PHRASE, (SK / rel).read_text(encoding="utf-8"), rel)


if __name__ == "__main__":
    unittest.main()
