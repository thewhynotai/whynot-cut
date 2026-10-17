# SPDX-License-Identifier: GPL-3.0-or-later
# © 2026 The Why Not AI (thewhynot.ai)
"""3.0 Phase 4 Task 65 (K-T5) call site, committed by the executor with the motion_qc.py hunk: motion QC lists
`arabic_integrity` only when it finds something (a clean plan's QC result is unchanged) and fails on a per-letter Arabic
animation with the scene id.
Run:  bash tools/test.sh -p test_safety_arabic_integrity_hooks.py
"""
import sys as _sys
_sys.dont_write_bytecode = True  # keep the plugin folder free of __pycache__
import _isolation  # noqa: F401,E402  G79: sandbox the engine home first (tests/_isolation.py)
import shutil
import tempfile
import unittest
from pathlib import Path

sys = _sys
SK = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SK / "engine" / "reel"))

from lib import common  # noqa: E402
from lib.common import Paths, read_json, write_json  # noqa: E402


def plan(reveal):
    text = "الضغط العالي خطر"
    return {"scenes": [{"id": "S03", "type": "kinetic_quote", "elements": [
        {"kind": "text", "name": "S03_text_1", "lines": [text], "text": text, "rtl": True, "reveal": reveal,
         "tokens": [{"text": t} for t in text.split()], "font_ps": ""}]}]}


class TestMotionQc(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="kt5hook_"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.addCleanup(common.set_context, None)
        self.root = self.tmp / "د. تجربة Dr Test"
        for d in ("assets", "data/Raw"):
            (self.root / d).mkdir(parents=True)
        (self.root / ".whynot-client").write_text("{}", encoding="utf-8")
        self.p = Paths(self.root, "C0001")
        common.set_context(self.root)

    def qc(self):
        from lib import motion_qc
        motion_qc.run(self.p)
        return read_json(self.p.p("08_quality_control/qc-results.json"))

    def names(self, res):
        return [c.get("name") or c.get("check") or c.get("id") for c in res.get("checks", [])]

    def test_clean_plan_has_no_new_line(self):
        write_json(self.p.p("01_analysis/motion-plan.json"), plan("word"))
        self.assertNotIn("arabic_integrity", self.names(self.qc()))

    def test_switch_off_changes_nothing(self):
        write_json(self.p.p("01_analysis/motion-plan.json"), plan("char"))
        self.assertNotIn("arabic_integrity", self.names(self.qc()))

    def test_per_letter_arabic_fails_with_the_scene(self):
        from lib.safety import switches
        write_json(self.root / common.CLIENT_PROFILE_REL / "safety.json",
                   {"switches": {switches.ARABIC_QC_IN_MOTION_QC: True}})
        write_json(self.p.p("01_analysis/motion-plan.json"), plan("char"))
        res = self.qc()
        check = [c for c in res.get("checks", []) if (c.get("name") or c.get("check") or c.get("id"))
                 == "arabic_integrity"][0]
        self.assertFalse(check.get("ok", check.get("pass")))
        self.assertIn("S03", str(check))


if __name__ == "__main__":
    unittest.main()
