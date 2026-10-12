"""3.0 T1.10 version and release hygiene (structure 1.1-1.4):
  * one plugin version everywhere (plugin.json, both marketplace.json fields, the newest CHANGELOG heading)
  * the bridge has its own version, identical in its three places (ppro_bridge.py, CEP manifest, bridge.js)
  * `reel --version` names the plugin version and root; `reel --help` lists every subcommand, generated from the
    command table (core + podcast + motion), so a new command cannot be forgotten
  * 3.0 T2.17 (engine MI-9): a ResourceWarning (unclosed file, pipe or process) anywhere in the suite fails the run
Run:  ~/.whynot-cut/venv/Scripts/python.exe -B -m unittest discover -s whynot-cut/tests -p test_release_hygiene.py -v
"""
import sys as _sys
_sys.dont_write_bytecode = True  # keep the plugin folder free of __pycache__
import _isolation  # noqa: F401,E402  G79: sandbox the engine home first (tests/_isolation.py)
import atexit
import gc
import importlib.util
import json
import os
import re
import subprocess
import sys
import unittest
import warnings
from pathlib import Path

SK = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SK / "engine" / "reel"))

CLI = SK / "engine/reel/cli.py"
SEMVER = r"\d+\.\d+\.\d+"


# --------------------------------------------------------------------------- ResourceWarning = error, suite-wide
# Installed when unittest discovery imports this module, i.e. before any test of any module runs. A leak is reported
# two ways: tools/test.sh runs Python with -W error::ResourceWarning, so a leak in a destructor (an unclosed file,
# pipe or Popen) reaches sys.unraisablehook; without -W (a plain `python -m unittest`) it reaches
# warnings.showwarning. Either way it is recorded, and at exit the run fails with the list (exit status 1).
LEAKS: list = []
QUIET = [False]                    # True only while TestResourceWarningIsAnError leaks on purpose (output stays clean)


def _hook(u, _prev=sys.unraisablehook):
    if isinstance(u.exc_value, ResourceWarning):
        LEAKS.append(f"{u.exc_value} (in {u.object!r})"[:400])
        if QUIET[0]:
            return
    _prev(u)


def _show(message, category, filename, lineno, file=None, line=None, _prev=warnings.showwarning):
    if issubclass(category, ResourceWarning):
        LEAKS.append(f"{message} ({filename}:{lineno})"[:400])
        if QUIET[0]:
            return
    _prev(message, category, filename, lineno, file, line)


def _fail_on_leaks():
    gc.collect()
    if LEAKS:
        sys.stderr.write(f"\nFAILED (ResourceWarning x{len(LEAKS)}; every file, pipe and process must be closed — "
                         "T2.17 / MI-9):\n" + "\n".join(f"  - {x}" for x in LEAKS) + "\n")
        sys.stderr.flush()
        os._exit(1)


if not getattr(sys, "_whynot_leak_watch", False):
    sys._whynot_leak_watch = True
    sys.unraisablehook, warnings.showwarning = _hook, _show
    atexit.register(_fail_on_leaks)


class TestResourceWarningIsAnError(unittest.TestCase):
    def test_watch_is_installed_and_catches_a_leak(self):
        self.assertIs(sys.unraisablehook, _hook)
        saved = list(LEAKS)
        QUIET[0] = True
        try:
            # "error" (tools/test.sh: the leak reaches sys.unraisablehook) and "always" (a plain `python -m unittest`
            # shows warnings: the leak reaches warnings.showwarning)
            for action in ("error", "always"):
                n = len(LEAKS)
                with warnings.catch_warnings():
                    warnings.simplefilter(action, ResourceWarning)
                    f = open(__file__, "rb")                 # noqa: SIM115 — the leak under test
                    del f
                    gc.collect()
                self.assertEqual(len(LEAKS), n + 1, f"an unclosed file must be recorded ({action})")
        finally:
            QUIET[0] = False
            LEAKS[:] = saved                           # this deliberate leak does not fail the run

    def test_test_runner_turns_resource_warnings_into_errors(self):
        self.assertIn("-W error::ResourceWarning", (SK.parent / "tools/test.sh").read_text(encoding="utf-8"))


def changelog_version() -> str:
    """The first `## x.y.z` heading; `## 3.0.0 (unreleased)` counts as 3.0.0."""
    for line in (SK / "CHANGELOG.md").read_text(encoding="utf-8").splitlines():
        m = re.match(rf"##\s+({SEMVER})\b", line)
        if m:
            return m.group(1)
    raise AssertionError("CHANGELOG.md has no '## x.y.z' heading")


def cli_module():
    spec = importlib.util.spec_from_file_location("reel_cli_t110", CLI)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def norm(text: str) -> str:
    """Whitespace-normalised help text: argparse re-wraps the lines (also after a hyphen)."""
    return re.sub(r"-\s+", "-", " ".join(text.split()))


def reel(*args):
    return subprocess.run([sys.executable, "-B", str(CLI), *args], capture_output=True, text=True, encoding="utf-8")


class TestPluginVersionConsistency(unittest.TestCase):
    def test_plugin_marketplace_changelog_agree(self):
        pj = json.loads((SK / ".claude-plugin/plugin.json").read_text(encoding="utf-8"))
        mj = json.loads((SK.parent / ".claude-plugin/marketplace.json").read_text(encoding="utf-8"))
        v = pj["version"]
        self.assertRegex(v, rf"^{SEMVER}$")
        self.assertEqual(mj["metadata"]["version"], v, "marketplace.json metadata.version")
        self.assertEqual(len(mj["plugins"]), 1)
        self.assertEqual(mj["plugins"][0]["version"], v, "marketplace.json plugins[0].version")
        self.assertEqual(changelog_version(), v, "newest CHANGELOG heading")

    def test_this_release_is_3_0_0(self):
        """Pinned on purpose: bumping the version is a release decision, so this test must be edited with it (the
        consistency test above only proves the four places agree, not that they say the intended release)."""
        pj = json.loads((SK / ".claude-plugin/plugin.json").read_text(encoding="utf-8"))
        self.assertEqual(pj["version"], "3.0.0")


class TestBridgeVersionTriple(unittest.TestCase):
    def test_python_manifest_and_js_agree(self):
        from lib import ppro_bridge
        manifest = (SK / "templates/premiere/cep_bridge/CSXS/manifest.xml").read_text(encoding="utf-8")
        m = re.search(rf'ExtensionBundleVersion="({SEMVER})"', manifest)
        self.assertIsNotNone(m, "manifest.xml has no ExtensionBundleVersion")
        js = (SK / "templates/premiere/cep_bridge/js/bridge.js").read_text(encoding="utf-8")
        j = re.search(rf"var VERSION = '({SEMVER})'", js)
        self.assertIsNotNone(j, "bridge.js has no `var VERSION = 'x.y.z'`")
        self.assertRegex(ppro_bridge.BRIDGE_VERSION, rf"^{SEMVER}$")
        self.assertEqual(m.group(1), ppro_bridge.BRIDGE_VERSION, "CSXS ExtensionBundleVersion")
        self.assertEqual(j.group(1), ppro_bridge.BRIDGE_VERSION, "bridge.js VERSION")

    def test_bridge_version_is_independent_of_the_plugin_version(self):
        """The bridge only changes when the CEP panel changes (Phase 6); it stays 3.1.0 until then. Pinned on purpose,
        like the plugin version: a bridge bump forces an update of the installed panel, so it must be a decision."""
        from lib import ppro_bridge
        self.assertEqual(ppro_bridge.BRIDGE_VERSION, "3.1.0")


class TestReelVersionFlag(unittest.TestCase):
    def test_prints_plugin_version_and_root(self):
        pj = json.loads((SK / ".claude-plugin/plugin.json").read_text(encoding="utf-8"))
        r = reel("--version")
        self.assertEqual(r.returncode, 0, r.stderr)
        lines = r.stdout.strip().splitlines()
        self.assertEqual(lines[0], f"WhyNot Cut {pj['version']}")
        self.assertEqual(len(lines), 2, r.stdout)
        self.assertTrue(lines[1].startswith("plugin root: "), lines[1])
        self.assertEqual(Path(lines[1][len("plugin root: "):]).resolve(), SK.resolve())


class TestReelHelpFromTheCommandTable(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cli = cli_module()
        cls.table = cls.cli.command_table()
        r = reel("--help")
        assert r.returncode == 0, r.stderr
        cls.help = r.stdout

    def test_every_table_command_is_in_help_with_its_line(self):
        from lib import motion_cli, podcast_cli
        self.assertGreater(len(self.table), 60)
        for name in list(podcast_cli.ARGS) + list(motion_cli.ARGS):
            self.assertIn(name, self.table, f"{name} (podcast/motion) missing from the command table")
        for name, line in self.table.items():
            self.assertTrue(line.strip(), f"{name} has no one-line help")
            self.assertRegex(self.help, rf"(?m)^\s+{re.escape(name)}\s", f"`reel --help` does not list {name}")
            self.assertIn(norm(f"{name} {line}"), norm(self.help), f"`reel --help` lacks the full help line of {name}")

    def test_every_table_command_has_a_handler(self):
        """The other way round: a command in the table that nothing runs would only fail when someone calls it."""
        from lib import motion_cli, podcast_cli
        for name in self.table:
            fn = "cmd_" + name.replace("-", "_")
            self.assertTrue(any(callable(getattr(m, fn, None)) for m in (self.cli, podcast_cli, motion_cli)),
                            f"`{name}` is in the command table but no {fn} exists in cli/podcast_cli/motion_cli")

    def test_help_has_no_command_beyond_the_table(self):
        """Every registered subparser is in the table and the other way round (no stale or missing entries)."""
        names = set(self.cli.registered_commands())
        self.assertEqual(names, set(self.table))

    def test_every_cmd_handler_is_a_command(self):
        for n in dir(self.cli):
            if n.startswith("cmd_"):
                self.assertIn(n[4:].replace("_", "-"), self.table, f"{n} has no command-table entry")

    def test_docstring_no_longer_carries_a_command_list(self):
        doc = self.cli.__doc__
        for name in self.table:
            if "-" in name:                      # a stale hand-written list would name the hyphenated commands
                self.assertNotIn(name, doc, f"the module docstring names `{name}`: --help generates the list")

    def test_subcommand_help_still_works(self):
        r = reel("transcribe", "--help")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("--model", r.stdout)


if __name__ == "__main__":
    unittest.main()
