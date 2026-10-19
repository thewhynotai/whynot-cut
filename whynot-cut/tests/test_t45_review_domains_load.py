# SPDX-License-Identifier: GPL-3.0-or-later
# © 2026 The Why Not AI (thewhynot.ai)
"""3.0 Phase 4 T4.5 (part B): review_domains reads the asset manifest through `client_db.load` (one door for the
database's stored paths). Goes with hooks/BL-14/review_domains.patch.
A display copy stored as an absolute path of the folder the client was copied from is found here again (load resolves
it under this client), so an AI-generated image still asks for its disclosure; read directly, it would point at the old
folder and the image would pass unflagged.
Run:  bash tools/test.sh -p test_t45_review_domains_load.py
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

from lib import review_domains  # noqa: E402
from lib.common import Paths, write_json  # noqa: E402

DERIV = "output/client_database/assets/derivatives/gen_alpha.png"


class TestAiFilesThroughLoad(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.root = self.tmp / "Now here عميل"
        for rel in ("assets/Images/gen.png", DERIV):
            f = self.root / rel
            f.parent.mkdir(parents=True, exist_ok=True)
            f.write_bytes(b"png")
        (self.root / "data").mkdir()
        self.old = self.tmp / "Was there"           # the folder it was copied from: gone

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def manifest(self, deriv: str):
        write_json(self.root / "output/client_database/asset-manifest.json", {"assets": [
            {"rel": "assets/Images/gen.png", "file": "assets/Images/gen.png", "category": "image",
             "ai_generated": True, "display_derivative": deriv}]})

    def test_a_display_copy_stored_under_the_old_folder_is_found_here(self):
        self.manifest(str(self.old.joinpath(*DERIV.split("/"))))
        got = review_domains._ai_files(Paths(self.root, "R01"), {"g1": {"params": {"image": DERIV}}})
        self.assertEqual(got, {"g1": [DERIV]})

    def test_a_relative_display_copy_still_matches(self):
        self.manifest(DERIV)
        got = review_domains._ai_files(Paths(self.root, "R01"), {"g1": {"params": {"image": DERIV}},
                                                                 "g2": {"params": {"image": "assets/Images/gen.png"}},
                                                                 "g3": {"params": {"image": "assets/Images/x.png"}}})
        self.assertEqual(got, {"g1": [DERIV], "g2": ["assets/Images/gen.png"]})


if __name__ == "__main__":
    unittest.main()
