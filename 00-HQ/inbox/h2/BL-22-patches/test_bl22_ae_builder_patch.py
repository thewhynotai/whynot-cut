# SPDX-License-Identifier: GPL-3.0-or-later
# © 2026 The Why Not AI (thewhynot.ai)
"""BL-22 patch for the executor (lib/ae_builder.py): generate() writes 04_after_effects/ae-assets.json.

New file whynot-cut/tests/test_bl22_ae_builder_patch.py (copy it there when applying ae_builder.patch). Red without
the patch, green with it. A missing logo or image gives one row in the file (client-relative ref); with the file back
the next build writes an empty list; the existing EN/AR warnings stay as they are.
Run:  bash tools/test.sh -p test_bl22_ae_builder_patch.py
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

from lib import ae_builder, common  # noqa: E402
from lib.common import Paths, read_json, write_json  # noqa: E402

LOGO_D = "output/client_database/derivatives/logo.png"
PHOTO_D = "output/client_database/derivatives/photo.png"


class TestGenerateWritesAssets(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="bl22ae_"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.root = self.tmp / "Client عميل"
        for d in ("assets", "data"):
            (self.root / d).mkdir(parents=True)
        write_json(self.root / common.CLIENT_PROFILE_REL / "sequence-settings.json",
                   {"general": {"timebase": 30, "ntsc": True}})
        self.p = Paths(self.root, "V1")
        self.p.ensure_project()
        self.root = self.p.root
        write_json(self.p.client_db / "asset-manifest.json", {"assets": [
            {"rel": "assets/Logo.png", "category": "logo", "file": "assets/Logo.png", "display_derivative": LOGO_D},
            {"rel": "assets/photo.jpg", "category": "photo", "file": "assets/photo.jpg", "display_derivative": PHOTO_D}]})
        write_json(self.p.p("01_analysis/timeline-spec.json"), {
            "fps": 30000 / 1001, "duration_frames": 240, "main_segments": [],
            "events": [{"event_id": "GFX_001", "template": "glass_card", "start_frame": 0, "end_frame": 48,
                        "params": {"image": "assets/photo.jpg"}}]})
        self.file = self.p.p("04_after_effects/ae-assets.json")

    def put(self, *rels):
        for rel in rels:
            f = self.root / rel
            f.parent.mkdir(parents=True, exist_ok=True)
            f.write_bytes(b"\x89PNG")

    def generate(self):
        with common.use_context(common.Context(self.p.root)):
            return ae_builder.generate(self.p)

    def test_a_missing_logo_is_one_row_and_the_warnings_stay(self):
        self.put(PHOTO_D)
        res = self.generate()
        rows = read_json(self.file)["needs_you"]
        self.assertEqual([(r["kind"], r["ref"]) for r in rows], [("assets", LOGO_D)])
        self.assertEqual(len(res["warnings"]), 2)                    # the d991323 EN + AR lines, unchanged

    def test_a_missing_image_and_logo_are_two_rows(self):
        rows = (self.generate() and read_json(self.file))["needs_you"]
        self.assertEqual(sorted(r["ref"] for r in rows), sorted([LOGO_D, PHOTO_D]))

    def test_with_the_files_back_the_next_build_writes_an_empty_list(self):
        self.generate()
        self.put(LOGO_D, PHOTO_D)
        res = self.generate()
        self.assertEqual(read_json(self.file), {"schema_version": 1, "needs_you": []})
        self.assertEqual(res["warnings"], [])


if __name__ == "__main__":
    unittest.main()
