# SPDX-License-Identifier: GPL-3.0-or-later
# © 2026 The Why Not AI (thewhynot.ai)
"""The one shared text normaliser (`engine/reel/lib/cut_proposals_norm.py`): used by the cut proposals (R-4.3) and
loaded from its file by the identity scan (`tools/identity_scan.py`, Task 19), so the two can never drift.
Spec: docs/superpowers/specs/addendum-h/source-r-specs/R-4.3-cut-proposals.md rule 1, R-9 (R-9.1 Normalisation).
Run:  tools/test.sh -p test_cut_proposals_norm.py
"""
import sys as _sys
_sys.dont_write_bytecode = True  # keep the plugin folder free of __pycache__
import _isolation  # noqa: F401,E402  G79: sandbox the engine home before anything else (see tests/_isolation.py)
import ast
import os
import sys
import unittest
from pathlib import Path

SK = Path(__file__).resolve().parents[1]
ROOT = SK.parent
sys.path.insert(0, str(SK / "engine" / "reel"))
sys.path.insert(0, str(ROOT / "tools"))

from lib import cut_proposals_norm as N  # noqa: E402
import identity_scan as ids  # noqa: E402


class TestNormaliser(unittest.TestCase):
    def test_words_casefold_nfkc_and_arabic_variants(self):
        self.assertEqual(N.normalize("ZORBLAX-Quentaro ｖｅｘ"), ["zorblax", "quentaro", "vex"])
        self.assertEqual(N.normalize("أَحْمَد إسلام آمن مدرسة على"), ["احمد", "اسلام", "امن", "مدرسه", "علي"])
        self.assertEqual(N.normalize("ک ی ۀ"), ["ك", "ي", "ه"])               # Persian letters unified

    def test_marks_tatweel_and_format_characters_removed_inside_words(self):
        self.assertEqual(N.normalize("كــتاب زو\u200fرب قلۡبي"), ["كتاب", "زورب", "قلبي"])

    def test_hard_punctuation_includes_arabic_marks(self):
        self.assertEqual(N.segments("واحد، اتنين؛ تلاتة؟ اربعة۔ خمسة"),
                         [["واحد"], ["اتنين"], ["تلاته"], ["اربعه"], ["خمسه"]])
        self.assertEqual(N.segments("v3.0 and a.b.c"), [["v3", "0", "and", "a", "b", "c"]])

    def test_prepare_keeps_line_breaks(self):
        text = "سطر أول\nline 2 \u200f\r\nكــتاب\n\nend"
        self.assertEqual(N.prepare(text).count("\n"), text.count("\n"))

    def test_glued_parts_and_arabic_proclitics(self):
        self.assertEqual(N.glued_parts("VexilorScene"), ["vexilor", "scene"])
        self.assertEqual(N.glued_parts("vexilor2"), ["vexilor", "2"])
        self.assertEqual(N.glued_parts("HTTPServer"), ["http", "server"])
        self.assertEqual(N.glued_parts("plain"), ["plain"])
        self.assertEqual(N.prefix_forms("والكتاب"), ["كتاب", "الكتاب"])     # the token may keep its own ال
        self.assertEqual(N.prefix_forms("بالكتاب"), ["كتاب", "الكتاب"])
        self.assertEqual(N.prefix_forms("للكتاب"), ["كتاب", "الكتاب"])
        self.assertEqual(N.prefix_forms("لكتاب"), ["كتاب"])
        self.assertEqual(N.prefix_forms("ولد"), [])                        # too short a remainder
        self.assertEqual(N.prefix_forms("وسام"), [])                       # at least 4 letters must remain
        self.assertEqual(N.prefix_forms("vexilor"), [])

    def test_fixed_input_output(self):
        """Pins the normaliser: any change here must bump NORM_VERSION (the identity hashes depend on it)."""
        self.assertEqual(N.NORM_VERSION, 2)
        text = "Zörb-LAX_v2.0, «أَحْمَدُ» كــتابٌ؟ مدرسة على ی ک ﻻ x\u200fy ｆｕｌｌ"
        self.assertEqual(N.segments(text),
                         [["zörb", "lax", "v2", "0"], ["احمد"], ["كتاب"], ["مدرسه", "علي", "ي", "ك", "لا", "xy", "full"]])

    def test_standard_library_only_no_relative_imports(self):
        """tools/identity_scan.py loads this file on its own: it must not import the engine package."""
        tree = ast.parse(Path(N.__file__).read_text(encoding="utf-8"))
        mods = {a.name.split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
        mods |= {n.module.split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) and n.module}
        rel = [n for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) and n.level]
        self.assertEqual(rel, [])
        self.assertLessEqual(mods, {"__future__", "re", "unicodedata"})

    def test_identity_scan_uses_this_very_file(self):
        self.assertEqual(os.path.realpath(ids.NORM_FILE), os.path.realpath(N.__file__))
        self.assertEqual(ids.normalize("ZorblaxQuentaro والكتاب"), N.normalize("ZorblaxQuentaro والكتاب"))


if __name__ == "__main__":
    unittest.main()
