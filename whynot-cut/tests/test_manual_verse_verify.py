# SPDX-License-Identifier: GPL-3.0-or-later
# © 2026 The Why Not AI (thewhynot.ai)
"""Manual verse, the QC verification sheet (patch verify-caption-source.patch, executor): the After Effects caption
picks take their expected text from the spec's caption_source (the captions the build drew), so a recited verse's
words never reach 08_quality_control/verify/ as "expected text".
Run:  bash tools/test.sh -p test_manual_verse_verify.py
"""
import sys as _sys
_sys.dont_write_bytecode = True  # keep the plugin folder free of __pycache__
import _isolation  # noqa: F401,E402  G79: sandbox the engine home first (tests/_isolation.py)
import unittest
from pathlib import Path
from unittest import mock

sys = _sys
SK = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SK / "engine" / "reel"))
sys.path.insert(0, str(SK / "tests"))

from test_manual_verse import SC, Base, build_words, has_verse, verse_project  # noqa: E402


class TestVerifyCaptions(Base):
    def test_expected_text_has_no_verse(self):
        _root, p = verse_project(self.tmp, build_words(SC["recited"]))
        self.compile(p)
        cap = p.p("04_after_effects/compositions/CAPTIONS.mov")
        cap.parent.mkdir(parents=True, exist_ok=True)
        cap.write_bytes(b"\0")
        from lib import verify
        with mock.patch.object(verify, "run", return_value=None):
            verify.build(p)
        out = [f for f in p.p("08_quality_control").rglob("*") if f.is_file() and f.suffix in (".json", ".md")]
        self.assertTrue(out)
        rows = "\n".join(f.read_text(encoding="utf-8") for f in out)
        self.assertIn("highlight_caption", rows)
        self.assertEqual(has_verse(rows), [])


if __name__ == "__main__":
    unittest.main()
