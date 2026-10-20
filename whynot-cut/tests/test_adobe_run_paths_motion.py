"""`motion-build --run-script` keeps adobe_run's SCRIPT_STAGE_FAILED (the .jsx could not be copied to a path
`AfterFX.exe -r` accepts): the reason reaches the editor, never the false "After Effects may be showing why" text.
Companion of test_adobe_run_paths.py (kept apart: motion_build.py changes on its own schedule).
TestMotionRealStage runs the REAL adobe_run.stage_script under motion_build.run_script (review 219e110 P3-4): only the
AE launch (Popen), the app lookup, the AE window check, the kernel's 8.3 call and macOS's osascript are stubbed, and
every folder it writes (engine home, staged copies, the result record) is inside the test's own temp folder.
Nothing here launches After Effects.
Run:  bash tools/test.sh -p test_adobe_run_paths_motion.py
"""
import sys as _sys
_sys.dont_write_bytecode = True  # keep the plugin folder free of __pycache__
import _isolation  # noqa: F401,E402  G79: sandbox the engine home first (tests/_isolation.py)
import ctypes
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import types
import unittest
from pathlib import Path
from unittest import mock

SK = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SK / "engine" / "reel"))

from lib import adobe_run, motion_build, plat  # noqa: E402
from lib.errors import exit_code  # noqa: E402

FAKE_AE = {"name": "AE", "exe": "AfterFX.exe"}
_REAL_POPEN = subprocess.Popen
JSX = "// motion\nvar x = 'عميل';\n"
R_SAFE = re.compile(r"[A-Za-z0-9._\-\\/:~]+")             # what `-r` may receive (the test's own copy of the rule)
COPY_NAME = re.compile(r"[0-9a-f]{16}-\d+-[0-9a-f]{12}\.jsx")
OLD_RESULT = {"status": "BUILT_UNVERIFIED", "ok": False, "at": "2026-10-18T10:00:00+03:00"}


def r_safe(s: str) -> bool:
    return bool(R_SAFE.fullmatch(s)) and not s.startswith(("\\\\", "//"))


class TestMotionRunScript(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="aerun_mo_"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.launched = []
        scripts = self.tmp / "Client A" / "04_after_effects" / "scripts"
        scripts.mkdir(parents=True)
        self.jsx = scripts / "build_V1_motion.jsx"
        self.jsx.write_text("// motion\n", encoding="utf-8")
        self.aep = self.tmp / "Client A" / "04_after_effects" / "project" / "V1_MO.aep"

        def popen(argv, *a, **kw):
            if isinstance(argv, (list, tuple)) and argv and os.path.basename(str(argv[0])) == FAKE_AE["exe"]:
                self.launched.append(list(argv))
                return None
            return _REAL_POPEN(argv, *a, **kw)
        for p in (mock.patch.object(plat, "newest_app", lambda key: FAKE_AE),
                  mock.patch.object(plat, "sandbox_refusal", lambda what, *t: None),
                  mock.patch.object(plat, "IS_MAC", False),
                  mock.patch.object(adobe_run.subprocess, "Popen", popen),
                  mock.patch.object(adobe_run, "stage_script", side_effect=OSError("disk full")),
                  mock.patch.object(motion_build, "_ae_titles", lambda: [], create=True),
                  mock.patch.object(motion_build, "write_fallback_script", lambda paths, **kw: self.jsx),
                  mock.patch.object(motion_build, "_route_refused", lambda paths: None),   # BL-21: approved
                  mock.patch.object(motion_build, "aep_path", lambda paths: self.aep),
                  mock.patch.object(motion_build, "_record", lambda paths, res: res)):
            p.start()
            self.addCleanup(p.stop)

    def test_run_script_keeps_the_stage_failure(self):
        res = motion_build.run_script(object(), timeout=1)
        self.assertEqual((res["status"], res["ok"]), ("SCRIPT_STAGE_FAILED", False), res)
        self.assertIn("disk full", res["msg"])
        self.assertEqual(res["jsx"], str(self.jsx))
        self.assertNotIn("showing why", str(res))
        self.assertIn("Run Script File", res["how"])
        self.assertEqual(exit_code(res), 1)
        self.assertEqual(self.launched, [])

    def test_run_script_result_names_the_copy_it_used(self):
        """The -r argument and the copy's deadline reach the motion result, as they reach ae-build-result.json."""
        ran = {"returncode": None, "stdout": "", "script_copy_used": r"C:\eng\tmp\ae-run\0123456789abcdef-1-ab.jsx",
               "script_copy_kept_until": "2026-10-17T12:00:00+03:00"}
        with mock.patch.object(adobe_run, "run_after_effects", lambda jsx, timeout, done=None: dict(ran)):
            res = motion_build.run_script(object(), timeout=1)
        self.assertEqual(res["status"], "FAILED", res)                   # nothing saved: the stub wrote no .aep
        self.assertEqual(res["script_copy_used"], ran["script_copy_used"])
        self.assertEqual(res["script_copy_kept_until"], ran["script_copy_kept_until"])


class TestMotionRealStage(unittest.TestCase):
    """motion_build.run_script -> adobe_run.run_after_effects -> the real stage_script (review 219e110 P3-4)."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="aerun_mo_real_"))       # inside the test sandbox (_isolation.py)
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.launched, self.ran = [], []
        self.client = self.jsx = self.aep = None
        self.clock = [time.time()]

        def popen(argv, *a, **kw):      # catch ONLY the After Effects launch
            if isinstance(argv, (list, tuple)) and argv and os.path.basename(str(argv[0])) == FAKE_AE["exe"]:
                p = Path(argv[2])
                self.launched.append((list(argv), p.read_bytes() if p.is_file() else None))
                return None
            return _REAL_POPEN(argv, *a, **kw)

        def osascript(argv, **kw):
            self.ran.append(list(argv))
            return subprocess.CompletedProcess(argv, 0, "", "")

        def sleep(s):                   # the wait for the .aep advances the run's own clock, never the real one
            self.clock[0] += s

        kernel = types.SimpleNamespace(GetShortPathNameW=lambda path, buf, n: 0)   # no 8.3 name, never the real call
        # never the machine's %ProgramData%: Windows keys are case-insensitive (os.environ holds PROGRAMDATA)
        env = {k: v for k, v in os.environ.items() if k.upper() not in ("PROGRAMDATA", "SYSTEMDRIVE")}
        env["SystemDrive"] = str(self.tmp / "sysdrive")
        env["WHYNOT_HOME"] = str(self.tmp / "enginehome")
        real_stage_dirs = adobe_run.stage_dirs

        def guarded_stage_dirs():
            dirs = real_stage_dirs()
            outside = [d for d, _shared in dirs if not str(os.path.abspath(d)).startswith(str(self.tmp))]
            if outside:
                raise AssertionError(f"a test would write outside its temp folder: {outside}")
            return dirs
        for p in (mock.patch.object(plat, "newest_app", lambda key: FAKE_AE),
                  mock.patch.object(plat, "sandbox_refusal", lambda what, *t: None),
                  mock.patch.object(plat, "IS_MAC", False),
                  mock.patch.object(adobe_run.subprocess, "Popen", popen),
                  mock.patch.object(adobe_run, "run", osascript),
                  mock.patch.object(adobe_run, "_now", lambda: self.clock[0]),
                  mock.patch.object(adobe_run.time, "sleep", sleep),
                  mock.patch.object(ctypes, "windll", types.SimpleNamespace(kernel32=kernel), create=True),
                  mock.patch.object(adobe_run, "stage_dirs", guarded_stage_dirs),
                  mock.patch.dict(os.environ, env, clear=True),
                  mock.patch.object(motion_build, "_ae_titles", lambda: []),
                  mock.patch.object(motion_build, "write_fallback_script", lambda paths, **kw: self.jsx),
                  mock.patch.object(motion_build, "_route_refused", lambda paths: None),   # BL-21: approved
                  mock.patch.object(motion_build, "aep_path", lambda paths: self.aep)):
            p.start()
            self.addCleanup(p.stop)

    def use_client(self, folder: str):
        self.client = self.tmp / "clients" / folder
        scripts = self.client / "04_after_effects" / "scripts"
        scripts.mkdir(parents=True)
        self.jsx = scripts / "build_V1_motion.jsx"
        self.jsx.write_text(JSX, encoding="utf-8")
        self.aep = self.client / "04_after_effects" / "project" / "V1_MO.aep"
        return types.SimpleNamespace(p=lambda rel: self.client / rel)       # all _record needs of `paths`

    def run_dir(self) -> Path:
        return Path(os.path.abspath(plat.engine_home())) / "tmp" / "ae-run"

    def copies(self) -> list:
        d = self.run_dir()
        return sorted(d.glob("*.jsx")) if d.is_dir() else []

    def need_safe(self):
        """Skip THIS case on a PC whose temp folder -r would not take (a space, non-ASCII letters)."""
        if not r_safe(os.path.abspath(self.tmp)):
            self.skipTest(f"needs a test folder whose path -r accepts; this PC's is {self.tmp}")

    def old_record(self, paths) -> Path:
        rec = paths.p(motion_build.RESULT)
        rec.parent.mkdir(parents=True, exist_ok=True)
        rec.write_text(json.dumps(OLD_RESULT), encoding="utf-8")
        os.utime(rec, (1_700_000_000, 1_700_000_000))
        return rec

    def assert_untouched(self, rec: Path):
        self.assertEqual(json.loads(rec.read_text(encoding="utf-8")), OLD_RESULT)
        self.assertEqual(rec.stat().st_mtime, 1_700_000_000)
        self.assertEqual([p.name for p in rec.parent.iterdir() if p.name.startswith(rec.name)], [rec.name])  # no tmp

    def test_a_spaced_or_arabic_client_folder_runs_from_a_staged_copy(self):
        self.need_safe()
        for folder in ("Client A", "عميل مصر"):
            with self.subTest(folder=folder):
                self.launched.clear()
                paths = self.use_client(folder)
                res = motion_build.run_script(paths, timeout=1)
                self.assertEqual(len(self.launched), 1, res)
                argv, data = self.launched[0]
                self.assertEqual(argv[:2], [FAKE_AE["exe"], "-r"])
                copy = argv[2]
                self.assertTrue(r_safe(copy) and adobe_run.r_safe(copy), copy)
                self.assertEqual(Path(copy).parent, self.run_dir())                 # never beside the client files
                self.assertRegex(Path(copy).name, COPY_NAME)
                self.assertEqual(data, self.jsx.read_bytes())                      # the jsx's bytes, at launch
                self.assertTrue(Path(copy).is_file())                              # kept after return: swept later
                self.assertEqual(res["script_copy_used"], copy)
                self.assertRegex(res["script_copy_kept_until"], r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d[+-]\d\d:\d\d$")
                self.assertEqual(res["jsx"], str(self.jsx))                        # the original path, not the copy
                self.assertEqual((res["status"], res["ok"], exit_code(res)), ("FAILED", False, 1), res)
                rec = json.loads(paths.p(motion_build.RESULT).read_text(encoding="utf-8"))
                self.assertEqual(rec["script_copy_used"], copy)
                json.dumps(res, ensure_ascii=False)                                # serialisable as it is

    def test_a_stage_failure_leaves_the_last_motion_result_untouched(self):
        """Review 219e110 P3-2 (ruling: keep the early return): nothing ran in AE and the .aep is unchanged, so an
        earlier motion-build-result.json keeps its status. A real ScriptReadError: the script vanished."""
        paths = self.use_client("Client B")
        rec = self.old_record(paths)
        self.jsx.unlink()
        res = motion_build.run_script(paths, timeout=1)
        self.assertEqual((res["status"], res["ok"], exit_code(res)), ("SCRIPT_STAGE_FAILED", False, 1), res)
        self.assertIn("could not be read", res["msg"])
        self.assertNotIn("showing why", str(res))
        self.assertEqual(self.launched, [])
        self.assert_untouched(rec)

    def test_no_safe_path_is_refused_with_nothing_launched(self):
        """A real ScriptPathError: the engine home has a space and Windows gives no 8.3 name -> REFUSED, exit 2."""
        os.environ["WHYNOT_HOME"] = str(self.tmp / "eng home")
        paths = self.use_client("Client D")
        rec = self.old_record(paths)
        res = motion_build.run_script(paths, timeout=1)
        self.assertEqual((res["status"], res.get("refused"), res["ok"], exit_code(res)),
                         ("REFUSED", "ae-script-path", False, 2), res)
        self.assertIn("AfterFX.exe -r", res["msg"])
        self.assertIn("WHYNOT_HOME", res["how"])
        self.assertEqual(res["jsx"], str(self.jsx))
        self.assertEqual(self.launched, [])
        self.assertEqual(self.copies(), [])                   # the unusable copy was removed again
        self.assertNotIn("script_copy_used", res)
        self.assert_untouched(rec)

    def test_macos_hands_osascript_the_original_path(self):
        paths = self.use_client("Client M")
        with mock.patch.object(plat, "IS_MAC", True):
            res = motion_build.run_script(paths, timeout=1)
        self.assertEqual(len(self.ran), 1, self.ran)
        self.assertEqual(self.ran[0][0], "osascript")
        self.assertEqual(self.ran[0][-1], str(self.jsx))     # the spaced path as an argv item, no copy
        self.assertNotIn("-r", self.ran[0])
        self.assertEqual(self.launched, [])
        self.assertEqual(self.copies(), [])
        self.assertFalse({"script_copy_used", "script_copy_kept_until"} & set(res), res)
        self.assertEqual((res["status"], exit_code(res)), ("FAILED", 1), res)


if __name__ == "__main__":
    unittest.main()
