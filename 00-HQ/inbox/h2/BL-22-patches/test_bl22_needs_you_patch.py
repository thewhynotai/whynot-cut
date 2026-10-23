# SPDX-License-Identifier: GPL-3.0-or-later
# © 2026 The Why Not AI (thewhynot.ai)
"""BL-22 patch for the executor (lib/needs_you.py + schemas/needs-you.schema.json): the kind `assets`.

New file whynot-cut/tests/test_bl22_needs_you_patch.py (copy it there when applying needs_you.patch). Red without
the patch, green with it. End to end: a project whose 04_after_effects/ae-assets.json (written by
lib/ae_assets_needs.py) names one missing logo -> collect() has one `assets` item -> NEEDS-YOU.md shows it under its
own heading, Arabic first, then English -> the JSON twin passes the schema.
Run:  bash tools/test.sh -p test_bl22_needs_you_patch.py
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

from lib import ae_assets_needs, needs_you, schemas  # noqa: E402
from lib.common import Paths  # noqa: E402

VID = "C0001"
AR_HEAD, EN_HEAD = "## ملفات ناقصة في الأفتر إفكتس", "## Files missing from After Effects"


class TestAssetsKind(unittest.TestCase):
    def setUp(self):
        tmp = Path(tempfile.mkdtemp(prefix="bl22ny_"))
        self.addCleanup(shutil.rmtree, tmp, True)
        (tmp / "عميل أ" / "assets").mkdir(parents=True)
        self.root = (tmp / "عميل أ").resolve()
        self.paths = Paths(self.root, VID)

    def assets(self, doc):
        return [i for i in doc["items"] if i["kind"] == "assets"]

    def test_a_missing_logo_is_one_item_with_its_own_heading(self):
        ae_assets_needs.write(self.paths, [("logo", str(self.root / "assets" / "logo.png"))])
        doc = needs_you.collect(self.root)
        items = self.assets(doc)
        self.assertEqual(len(items), 1, doc)
        self.assertEqual(items[0]["ref"], "assets/logo.png")
        self.assertEqual(doc["skipped"], [])
        md = needs_you.render_md(doc)
        self.assertIn(AR_HEAD, md)
        self.assertIn(EN_HEAD, md)
        self.assertLess(md.index(AR_HEAD), md.index("# Needs you"))      # Arabic first
        self.assertGreater(md.index(EN_HEAD), md.index("# Needs you"))
        self.assertIn("assets/logo.png", md)

    def test_an_empty_list_shows_nothing(self):
        ae_assets_needs.write(self.paths, [("logo", str(self.root / "assets" / "logo.png"))])
        ae_assets_needs.write(self.paths, [])
        doc = needs_you.collect(self.root)
        self.assertEqual(self.assets(doc), [])
        self.assertNotIn(AR_HEAD, needs_you.render_md(doc))

    def test_the_kind_is_in_the_reader_and_in_the_schema(self):
        self.assertIn("assets", needs_you.KINDS)
        self.assertIn("assets", needs_you.HEAD)
        self.assertEqual(needs_you.KINDS.index("assets"), needs_you.KINDS.index("logo") + 1)
        ae_assets_needs.write(self.paths, [("image", "assets/e.png")])
        self.assertEqual(schemas.validate(needs_you.collect(self.root), "needs-you"), [])


if __name__ == "__main__":
    unittest.main()
