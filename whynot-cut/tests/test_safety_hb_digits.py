# SPDX-License-Identifier: GPL-3.0-or-later
# © 2026 The Why Not AI (thewhynot.ai)
"""K-T5 (Phase 4 Task 65) finding, committed by the executor with the hb_text.py hunk: Arabic-Indic digits and the
Arabic decimal separator keep their order inside right-to-left text. Before the fix «٥٠٠» was drawn «٠٠٥» and
«٣٫٥ مجم» as «٥٫٣ مجم» on the graphics stills (HarfBuzz path: Windows, Linux, and macOS without CoreText).
Run:  bash tools/test.sh -p test_safety_hb_digits.py
"""
import sys as _sys
_sys.dont_write_bytecode = True  # keep the plugin folder free of __pycache__
import _isolation  # noqa: F401,E402  G79: sandbox the engine home first (tests/_isolation.py)
import unittest
from pathlib import Path

sys = _sys
SK = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SK / "engine" / "reel"))

from lib import hb_text  # noqa: E402


class TestDigitRuns(unittest.TestCase):
    def test_arabic_indic_digits_are_one_left_to_right_run(self):
        self.assertEqual(hb_text.runs("خد ٥٠٠ مجم"), (True, [("R", "خد "), ("L", "٥٠٠"), ("R", " مجم")]))
        self.assertEqual(hb_text.runs("٣٫٥ مجم"), (True, [("L", "٣٫٥"), ("R", " مجم")]))
        self.assertEqual(hb_text.runs("۱۲۰/۸۰")[1], [("L", "۱۲۰/۸۰")])            # Persian digits too
        self.assertEqual(hb_text.runs("٧٠٪ من الناس")[1][0], ("L", "٧٠٪"))           # the Arabic percent sign

    def test_western_digits_and_plain_arabic_unchanged(self):
        self.assertEqual(hb_text.runs("خد 500 مجم"), (True, [("R", "خد "), ("L", "500"), ("R", " مجم")]))
        self.assertEqual(hb_text.runs("مرحبا"), (True, [("R", "مرحبا")]))


if __name__ == "__main__":
    unittest.main()
