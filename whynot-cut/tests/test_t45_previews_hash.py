# SPDX-License-Identifier: GPL-3.0-or-later
# © 2026 The Why Not AI (thewhynot.ai)
"""3.0 Phase 4 T4.5 (part B), review 02df75f r1 P3-2: the stills' input hash (`previews._shared_inputs`) holds the
client database's paths in their stored, root-relative form, so a moved client redraws no still; the files themselves
are still read through `client_db.load` (an edited font or logo still redraws). Goes with hooks/BL-14/previews.patch.
Run:  bash tools/test.sh -p test_t45_previews_hash.py
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
sys.path.insert(0, str(Path(__file__).resolve().parent))

from lib import client_db as CDB, client_move as CM, previews, writer_lock  # noqa: E402
from lib.common import Paths  # noqa: E402
from test_t45_client_move import make_client, unlink_links  # noqa: E402

SPEC = {"main_footage": "data/Raw/clip 1.mp4", "source_in_ms": 0}


def shared(root: Path) -> dict:
    p = Paths(root, "R01")
    man = CDB.load(p, "asset-manifest.json", {"assets": []})
    return previews._shared_inputs(p, SPEC, man)


class TestStillsHashAfterAMove(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.src = make_client(self.tmp, "Acme عميل")
        self.dest = self.tmp / "E drive" / "Moved نقل"
        self.dest.parent.mkdir()

    def tearDown(self):
        unlink_links(self.tmp)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def move(self):
        (self.src / "output/.whynot-lock").unlink()
        lk = writer_lock.acquire(self.src, "reel client-move --apply")
        try:
            doc = CM.move(self.src, self.dest, apply=True)
        finally:
            lk.release()
            writer_lock.release_own(self.src, writer_lock.session_id())
        self.assertTrue(doc.get("applied"), doc)

    def test_a_moved_client_hashes_the_same(self):
        before = shared(self.src)
        self.assertEqual(before["fonts"], {"assets/Fonts/B.ttf": previews._file_sha(self.src / "assets/Fonts/B.ttf")})
        self.assertEqual(before["logo"][0], "output/client_database/assets/derivatives/logo_alpha.png")
        self.assertIsNotNone(before["logo"][1])                                  # the file itself was read
        self.move()
        self.assertEqual(shared(self.dest), before)

    def test_an_edited_font_still_changes_the_hash(self):
        before = shared(self.src)
        (self.src / "assets/Fonts/B.ttf").write_bytes(b"another font")
        self.assertNotEqual(shared(self.src)["fonts"], before["fonts"])


if __name__ == "__main__":
    unittest.main()
