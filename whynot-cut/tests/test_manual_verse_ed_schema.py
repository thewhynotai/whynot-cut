# SPDX-License-Identifier: GPL-3.0-or-later
# © 2026 The Why Not AI (thewhynot.ai)
"""Manual verse, the edit-decisions schema (patch edit-decisions-schema-verse.patch, executor): `manual_verse` and
`manual_verse_off` at the top level are documented and checked by `reel validate` (start_ms and end_ms are times).
Run:  bash tools/test.sh -p test_manual_verse_ed_schema.py
"""
import sys as _sys
_sys.dont_write_bytecode = True  # keep the plugin folder free of __pycache__
import _isolation  # noqa: F401,E402  G79: sandbox the engine home first (tests/_isolation.py)
import unittest
from pathlib import Path

sys = _sys
SK = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SK / "engine" / "reel"))

from lib import schemas  # noqa: E402

BASE = {"video_id": "CLIP1", "global": {"main_footage": "data/Raw/CLIP1.mov"}, "decisions": []}


class TestEditDecisionsSchema(unittest.TestCase):
    def test_overrides_validate(self):
        ed = dict(BASE, manual_verse=[{"start_ms": 1200, "end_ms": "00:00:04.500", "note": "سمعتها"}],
                  manual_verse_off=[{"start_ms": 8000, "end_ms": 9000}])
        self.assertEqual(schemas.validate(ed, "edit-decisions"), [])

    def test_bad_overrides(self):
        for bad in ({"manual_verse": [{"start_ms": 1}]}, {"manual_verse": "x"},
                    {"manual_verse_off": [{"start_ms": "soon", "end_ms": 2}]}):
            self.assertNotEqual(schemas.validate(dict(BASE, **bad), "edit-decisions"), [], bad)


if __name__ == "__main__":
    unittest.main()
