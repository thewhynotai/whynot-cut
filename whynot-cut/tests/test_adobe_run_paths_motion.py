"""`motion-build --run-script` keeps adobe_run's SCRIPT_STAGE_FAILED (the .jsx could not be copied to a path
`AfterFX.exe -r` accepts): the reason reaches the editor, never the false "After Effects may be showing why" text.
Companion of test_adobe_run_paths.py (kept apart: motion_build.py changes on its own schedule).
Nothing here launches After Effects: the app lookup and the AE launch are stubbed.
Run:  bash tools/test.sh -p test_adobe_run_paths_motion.py
"""
import sys as _sys
_sys.dont_write_bytecode = True  # keep the plugin folder free of __pycache__
import _isolation  # noqa: F401,E402  G79: sandbox the engine home first (tests/_isolation.py)
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

from lib import adobe_run, motion_build, plat  # noqa: E402
from lib.errors import exit_code  # noqa: E402

FAKE_AE = {"name": "AE", "exe": "AfterFX.exe"}
_REAL_POPEN = subprocess.Popen


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


if __name__ == "__main__":
    unittest.main()
