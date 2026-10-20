# SPDX-License-Identifier: GPL-3.0-or-later
# © 2026 The Why Not AI (thewhynot.ai)
"""3.0 Phase 4 Task 64 (K-T4) call sites, committed by the executor with the cli.py / qc.py hunks: `reel
safezone-check` exits 0 / 1 / 2 (clean / an element intrudes / could not check); `reel qc` adds a failing mandatory
item for an intrusion only with the K-T4 switch on (off: today's QC result).
Run:  bash tools/test.sh -p test_safety_safezone_gate_hooks.py
"""
import sys as _sys
_sys.dont_write_bytecode = True  # keep the plugin folder free of __pycache__
import _isolation  # noqa: F401,E402  G79: sandbox the engine home first (tests/_isolation.py)
import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

sys = _sys
SK = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SK / "engine" / "reel"))

from lib import common  # noqa: E402
from lib.common import write_json  # noqa: E402
from lib.safety import switches  # noqa: E402

CLI = SK / "engine/reel/cli.py"


def env():
    from test_plugin import isolated_env
    return isolated_env()


class TestHooks(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="kt4hook_"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.addCleanup(common.set_context, None)
        from test_long_lived import golden_project
        self.root, self.p = golden_project(self.tmp)
        from lib.plan import compile_plan
        common.set_context(self.root)
        compile_plan(self.p)

    def caption(self, rect):
        from PIL import Image, ImageDraw
        im = Image.new("RGBA", (1080, 1920), (0, 0, 0, 0))
        ImageDraw.Draw(im).rectangle(rect, fill=(255, 255, 255, 255))
        f = self.p.p("03_broll/captions/CAP_901_fg.png")
        f.parent.mkdir(parents=True, exist_ok=True)
        im.save(f)

    def reel(self, *argv):
        cmd = [sys.executable, "-B", str(CLI), "--root", str(self.root), "--video-id", self.p.video_id, *argv]
        r = subprocess.run(cmd, capture_output=True, env=env())
        return r.returncode, r.stdout.decode("utf-8"), r.stderr.decode("utf-8", "replace")

    def test_exit_codes(self):
        self.caption((200, 1500, 880, 1600))
        code, out, err = self.reel("safezone-check", "--platform", "ig_reels_organic")
        self.assertEqual(code, 1, err)
        self.assertIn("CAP_901", out)
        code, out, err = self.reel("safezone-check", "--platform", "no_such_platform")
        self.assertEqual(code, 2, err)
        self.caption((200, 1000, 880, 1100))
        code, out, err = self.reel("safezone-check", "--platform", "ig_reels_organic")
        self.assertEqual(code, 0, out + err)

    def test_qc_hard_fail_only_with_the_switch(self):
        from lib import qc
        self.caption((200, 1500, 880, 1600))
        write_json(self.p.p("01_analysis/edit-decisions.json"),
                   dict(json.loads(self.p.p("01_analysis/edit-decisions.json").read_text("utf-8")),
                        **{"global": {**json.loads(self.p.p("01_analysis/edit-decisions.json").read_text("utf-8"))
                           ["global"], "platforms": ["ig_reels_organic"]}}))

        def items():
            res = qc.run_qc(self.p)
            return [i for i in res["checks"] if "Platform safe zones" in str(i.get("check"))]
        self.assertEqual(items(), [])
        write_json(self.root / common.CLIENT_PROFILE_REL / "safety.json",
                   {"switches": {switches.QC_SAFEZONE_HARD_FAIL: True}})
        got = items()
        self.assertEqual(len(got), 1)
        self.assertEqual(got[0]["result"], "FAIL")
        self.assertTrue(got[0]["mandatory"])


if __name__ == "__main__":
    unittest.main()
