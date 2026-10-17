# SPDX-License-Identifier: GPL-3.0-or-later
# © 2026 The Why Not AI (thewhynot.ai)
"""3.0 Phase 4 Task 61 (K-T1) call sites, committed by the executor with the plan.py / transcribe.py / needs_you.py
hunks: with the K-T1 switch off `reel plan` compiles today's output byte for byte (the golden plan, test_long_lived);
with it on, a graphic showing an unconfirmed high-risk word is refused, and subtitle-review.md opens with the
risk-first block.
Run:  bash tools/test.sh -p test_safety_plan_hook.py
"""
import sys as _sys
_sys.dont_write_bytecode = True  # keep the plugin folder free of __pycache__
import _isolation  # noqa: F401,E402  G79: sandbox the engine home first (tests/_isolation.py)
import hashlib
import shutil
import tempfile
import unittest
from pathlib import Path

sys = _sys
SK = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SK / "engine" / "reel"))

from lib import common  # noqa: E402
from lib.common import read_json, write_json  # noqa: E402
from lib.safety import switches  # noqa: E402


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="kt1hook_"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.addCleanup(common.set_context, None)
        from test_long_lived import golden_project
        self.root, self.p = golden_project(self.tmp)
        self.prof = self.root / common.CLIENT_PROFILE_REL

    def switch(self, on):
        write_json(self.prof / "safety.json", {"switches": {switches.PLAN_BLOCK: on}})

    def unsure(self, word="Isotretinoin", p=0.5):
        f = self.p.p("02_transcription/words.json")
        doc = read_json(f)
        for w in doc["words"]:
            if w["word"] == word:
                w["probability"] = p
        write_json(f, doc)

    def compile(self):
        from lib.plan import compile_plan
        common.set_context(self.root)
        return compile_plan(self.p)


class TestPlanHook(Base):
    def test_switch_off_compiles_like_today(self):
        """The golden files themselves are compared in test_long_lived; here: off = no new error, same outputs as a
        run without any safety.json."""
        self.unsure()
        from test_long_lived import GOLDEN_FILES
        res0 = self.compile()
        out0 = {rel: self.p.p(rel).read_bytes() for rel in GOLDEN_FILES}
        self.switch(False)
        res1 = self.compile()
        self.assertEqual(res0["ok"], res1["ok"])
        self.assertEqual(res0["errors"], res1["errors"])
        strip = {"generated", "engine_version"}
        for rel in GOLDEN_FILES:
            if rel.endswith(".json"):
                a, b = read_json(self.p.p(rel)), None
                b = __import__("json").loads(out0[rel])
                self.assertEqual({k: v for k, v in a.items() if k not in strip},
                                 {k: v for k, v in b.items() if k not in strip}, rel)
            else:
                self.assertEqual(self.p.p(rel).read_bytes(), out0[rel], rel)

    def test_switch_on_refuses_unconfirmed_drug_name_on_a_graphic(self):
        self.prof.mkdir(parents=True, exist_ok=True)
        write_json(self.prof / "profile.json", {"domain": "medical"})
        self.switch(True)
        self.assertTrue(self.compile()["ok"])                  # sure of every word: nothing new
        self.unsure()
        res = self.compile()
        self.assertFalse(res["ok"])
        err = [e for e in res["errors"] if "«Isotretinoin»" in e]
        self.assertEqual(len(err), 1, res["errors"])
        self.assertIn("اسم دوا", err[0])
        data = self.p.p("02_transcription/words.json").read_bytes()
        write_json(self.p.p("02_transcription/verification.json"),
                   {"verified": True, "by": "editor", "words_sha1": hashlib.sha1(data).hexdigest()})
        self.assertTrue(self.compile()["ok"])                  # confirmed by ear: unblocked


class TestReviewHook(Base):
    def test_review_block_only_with_switch_on(self):
        from lib.transcribe import finalize
        tj = read_json(self.p.p("02_transcription/transcript.json"))
        wj = read_json(self.p.p("02_transcription/words.json"))
        for w in wj["words"]:
            if w["word"] == "Isotretinoin":
                w["probability"] = 0.5
        common.set_context(self.root)
        finalize(self.p, tj["meta"], tj["segments"], wj["words"])
        off = self.p.p("02_transcription/subtitle-review.md").read_text(encoding="utf-8")
        self.assertNotIn("راجع دول الأول", off)
        self.switch(True)
        finalize(self.p, tj["meta"], tj["segments"], wj["words"])
        on = self.p.p("02_transcription/subtitle-review.md").read_text(encoding="utf-8")
        self.assertIn("## راجع دول الأول", on)
        self.assertLess(on.index("راجع دول الأول"), on.index("## Low-confidence words"))
        self.assertEqual(on.replace(on[on.index("## راجع دول الأول"):on.index("## Low-confidence words")], ""), off)


if __name__ == "__main__":
    unittest.main()
