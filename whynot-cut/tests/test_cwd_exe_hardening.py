"""3.0 hygiene: no program is ever started from the CURRENT folder by a bare name (tools track Task 10 review I1).

On Windows `shutil.which()` and CreateProcess look in the current folder first unless the process has
`NoDefaultCurrentDirectoryInExePath` (Claude Code's own shell sets it; a launcher, a panel or a user terminal does not).
A `claude.exe` or `taskkill.exe` planted in a folder the engine runs in (a client delivery folder) would then run with
the user's rights.
  * tools/find_claude.py keeps only absolute `which()` results;
  * lib/parallel.kill_tree starts taskkill by its full System32 path.
Run:  tools/test.sh -p test_cwd_exe_hardening.py
"""
import sys as _sys
_sys.dont_write_bytecode = True  # keep the plugin folder free of __pycache__
import _isolation  # noqa: F401,E402  G79: sandbox the engine home before anything else (see tests/_isolation.py)
import importlib.util
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SK = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SK / "engine" / "reel"))

from lib import parallel  # noqa: E402

FIND_CLAUDE = SK.parent / "tools" / "find_claude.py"


def find_claude_module():
    spec = importlib.util.spec_from_file_location("wnc_test_find_claude_cwd", FIND_CLAUDE)
    fc = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(fc)
    return fc


class TestFindClaudeIgnoresTheCurrentFolder(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.cwd, self.empty, self.home = self.tmp / "delivery", self.tmp / "empty path", self.tmp / "home"
        for d in (self.cwd, self.empty, self.home):
            d.mkdir()
        old = os.getcwd()
        os.chdir(self.cwd)
        self.addCleanup(os.chdir, old)

    def norm(self, paths) -> list:
        return [os.path.normcase(os.path.abspath(p)) for p in paths]

    def test_relative_path_entries_are_never_searched(self):
        """Every OS: "", "." and "bin" on PATH would resolve in the current folder; only absolute folders count."""
        planted = self.cwd / "claude.exe"
        planted.write_bytes(b"")
        (self.cwd / "bin").mkdir()
        (self.cwd / "bin" / "claude.exe").write_bytes(b"")
        fc = find_claude_module()
        env = {"PATH": os.pathsep.join(["", ".", "bin", str(self.empty)])}
        got = self.norm(fc.candidates(env, self.home, "win32"))
        self.assertNotIn(os.path.normcase(str(planted)), got)
        self.assertNotIn(os.path.normcase(str(self.cwd / "bin" / "claude.exe")), got)

    def test_shutil_which_is_not_used(self):
        """Filtering which() afterwards is not enough: a planted file it answers first hides the real CLI."""
        code = [ln for ln in FIND_CLAUDE.read_text(encoding="utf-8").splitlines() if not ln.lstrip().startswith("#")]
        self.assertFalse([ln for ln in code if "shutil.which(" in ln and '"""' not in ln and "Not shutil" not in ln])

    def test_a_planted_file_does_not_hide_the_real_cli(self):
        (self.cwd / "claude.exe").write_bytes(b"")
        real = self.tmp / "bin" / "claude.exe"
        real.parent.mkdir()
        real.write_bytes(b"")
        fc = find_claude_module()
        got = fc.candidates({"PATH": os.pathsep.join([".", str(real.parent)])}, self.home, "win32")
        self.assertEqual(got[0], real)

    def test_an_absolute_path_folder_is_searched(self):
        real = self.tmp / "bin" / "claude.exe"
        real.parent.mkdir()
        real.write_bytes(b"")
        fc = find_claude_module()
        self.assertIn(real, fc.candidates({"PATH": str(real.parent)}, self.home, "win32"))

    def test_a_relative_claude_cli_is_dropped(self):
        (self.cwd / "claude.exe").write_bytes(b"")
        fc = find_claude_module()
        got = self.norm(fc.candidates({"PATH": str(self.empty), "CLAUDE_CLI": "claude.exe"}, self.home, "win32"))
        self.assertNotIn(os.path.normcase(str(self.cwd / "claude.exe")), got)

    @unittest.skipUnless(sys.platform == "win32", "drive-less rooted paths are a Windows form")
    def test_a_drive_less_rooted_path_entry_is_not_absolute(self):
        r"""`\dir` is relative to the current DRIVE; os.path.isabs says True, Path.is_absolute says False."""
        fc = find_claude_module()
        rooted = "\\" + str(self.cwd)[3:]                       # D:\...\delivery -> \...\delivery
        (self.cwd / "claude.exe").write_bytes(b"")
        got = self.norm(fc.candidates({"PATH": rooted, "CLAUDE_CLI": rooted + "\\claude.exe"}, self.home, "win32"))
        self.assertNotIn(os.path.normcase(str(self.cwd / "claude.exe")), got)

    @unittest.skipUnless(sys.platform == "win32", "the current-folder search is Windows behaviour")
    def test_windows_planted_claude_exe_in_the_cwd_is_not_found(self):
        """The real repro: no mock, `NoDefaultCurrentDirectoryInExePath` removed, PATH = an empty folder."""
        planted = self.cwd / "claude.exe"
        planted.write_bytes(b"")
        fc = find_claude_module()
        env = {k: v for k, v in os.environ.items() if k.upper() != "NODEFAULTCURRENTDIRECTORYINEXEPATH"}
        env["PATH"] = str(self.empty)
        with mock.patch.dict(os.environ, env, clear=True):
            got = [os.path.normcase(os.path.abspath(p)) for p in fc.candidates(env, self.home, "win32")]
        self.assertNotIn(os.path.normcase(str(planted)), got)


class _Proc:
    pid = 4242

    def __init__(self):
        self.killed = False

    def poll(self):
        return None

    def kill(self):
        self.killed = True


class TestKillTreeUsesTheSystemTaskkill(unittest.TestCase):
    def test_taskkill_by_full_system32_path(self):
        calls = []
        with mock.patch.object(parallel.sys, "platform", "win32"), \
                mock.patch.dict(os.environ, {"SystemRoot": r"C:\Windows"}), \
                mock.patch.object(parallel.subprocess, "run", side_effect=lambda argv, **kw: calls.append(argv)):
            proc = _Proc()
            parallel.kill_tree(proc)
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0][0].lower(), r"c:\windows\system32\taskkill.exe")
        self.assertEqual(calls[0][1:], ["/F", "/T", "/PID", "4242"])
        self.assertTrue(proc.killed)                       # the direct kill still follows

    def test_no_systemroot_falls_back_to_the_windows_default(self):
        calls = []
        env = {k: v for k, v in os.environ.items() if k.upper() not in ("SYSTEMROOT", "WINDIR")}
        with mock.patch.object(parallel.sys, "platform", "win32"), mock.patch.dict(os.environ, env, clear=True), \
                mock.patch.object(parallel.subprocess, "run", side_effect=lambda argv, **kw: calls.append(argv)):
            parallel.kill_tree(_Proc())
        self.assertEqual(calls[0][0].lower(), r"c:\windows\system32\taskkill.exe")

    def test_taskkill_failure_still_kills_the_process(self):
        def boom(argv, **kw):
            raise OSError("cannot start")
        with mock.patch.object(parallel.sys, "platform", "win32"), \
                mock.patch.object(parallel.subprocess, "run", side_effect=boom):
            proc = _Proc()
            parallel.kill_tree(proc)
        self.assertTrue(proc.killed)

    def test_no_bare_taskkill_left_in_the_engine(self):
        """No engine file starts taskkill by a bare name."""
        hits = []
        for p in (SK / "engine" / "reel").rglob("*.py"):
            for n, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
                if '["taskkill"' in line or "['taskkill'" in line:
                    hits.append(f"{p.relative_to(SK)}:{n}")
        self.assertEqual(hits, [])


if __name__ == "__main__":
    unittest.main()
