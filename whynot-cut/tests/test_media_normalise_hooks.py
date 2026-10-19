# SPDX-License-Identifier: GPL-3.0-or-later
# © 2026 The Why Not AI (thewhynot.ai)
"""Task 26 hook (R-4.4, hooks/t26/media.py.patch): media.preflight reports the real motion rate / VFR / HDR lines and
keeps the measurement in the file's record; it never changes the file. Red without the patch.
Run:  bash tools/test.sh -p test_media_normalise_hooks.py
"""
import sys as _sys
_sys.dont_write_bytecode = True  # keep the plugin folder free of __pycache__
import _isolation  # noqa: F401,E402  G79: sandbox the engine home first (tests/_isolation.py)
import hashlib
import shutil
import tempfile
import unittest
from pathlib import Path

SK = Path(__file__).resolve().parents[1]
if str(SK / "engine" / "reel") not in _sys.path:
    _sys.path.insert(0, str(SK / "engine" / "reel"))

FX = SK / "tests" / "fixtures" / "media_normalise"


class PreflightReports(unittest.TestCase):
    def setUp(self):
        from lib.common import Paths
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)
        (self.tmp / "c" / "assets").mkdir(parents=True)
        (self.tmp / "c" / "data" / "Raw").mkdir(parents=True)
        self.p = Paths(self.tmp / "c", "V1")
        self.p.ensure_project()

    def run_preflight(self, name):
        from lib.media import preflight
        f = self.tmp / "c" / "data" / "Raw" / f"{name}.mp4"
        shutil.copyfile(FX / f"{name}.mp4", f)
        before = hashlib.sha256(f.read_bytes()).hexdigest()
        rep = preflight(self.p, [f])
        self.assertEqual(hashlib.sha256(f.read_bytes()).hexdigest(), before)
        return rep

    def test_tag_real_mismatch_is_reported(self):
        rep = self.run_preflight("tag60_real30")
        self.assertTrue(any("really moves at 30" in i["msg"] for i in rep["issues"]), rep["issues"])
        self.assertEqual(rep["files"][0]["normalise"]["decision"]["actions"], ["cfr"])

    def test_lines_are_arabic_first_then_english(self):
        rep = self.run_preflight("tag60_real30")
        info = [i for i in rep["issues"] if "msg_ar" in i]
        self.assertTrue(info, rep["issues"])
        for i in info:
            first, second = i["msg"].split(chr(10))
            self.assertRegex(first[:12], "[؀-ۿ]")                  # the Arabic line comes first
            self.assertEqual((first, second), (i["msg_ar"], i["msg_en"]))
            self.assertNotRegex(second, "[؀-ۿ]")

    def test_report_markdown_keeps_both_lines_in_one_item(self):
        rep = self.run_preflight("tag60_real30")
        i = next(i for i in rep["issues"] if "msg_ar" in i)
        md = self.p.p("00_inputs/preflight-report.md").read_text(encoding="utf-8")
        self.assertIn(i["msg_ar"] + "\n  " + i["msg_en"], md)            # the English line indented under the Arabic

    def test_clean_clip_adds_nothing(self):
        rep = self.run_preflight("cfr30")
        self.assertEqual(rep["files"][0]["normalise"]["decision"]["actions"], [])


if __name__ == "__main__":
    unittest.main()
