# SPDX-License-Identifier: GPL-3.0-or-later
# © 2026 The Why Not AI (thewhynot.ai)
"""3.0 Phase 4 T4.5 (part B): ae_builder reads the typography and the asset manifest through `client_db.load` (their
paths are stored root-relative since BL-14). Goes with hooks/BL-14/ae_builder.patch (for the Adobe track), which also
deletes PENDING_SWAP in test_t45_guard.py: from then on the guard holds ae_builder to the rule like every other reader.
Run:  bash tools/test.sh -p test_t45_ae_builder_load.py
"""
import sys as _sys
_sys.dont_write_bytecode = True  # keep the plugin folder free of __pycache__
import _isolation  # noqa: F401,E402  G79: sandbox the engine home first (tests/_isolation.py)
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys = _sys
SK = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SK / "engine" / "reel"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from lib import ae_builder, client_db  # noqa: E402
from lib.common import write_json  # noqa: E402
import test_t45_guard as G  # noqa: E402


class TestAeBuilderThroughLoad(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.db = self.tmp / "Client عميل" / "output" / "client_database"
        (self.db / "branding").mkdir(parents=True)
        write_json(self.db / "branding/typography.json", {"families": {"B": {"weights": [
            {"file": "assets/Fonts/B.ttf", "ps": "B-Regular", "style": "Regular"}]}},
            "roles": {"headline": {"postscript_name": "B-Bold"}}, "missing_or_uninstalled": []})

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_fonts_map_reads_the_typography_through_load(self):
        seen = []
        real = client_db.load

        def spy(paths, rel, default=None):
            seen.append(rel)
            return real(paths, rel, default)
        with mock.patch.object(client_db, "load", spy):
            d = ae_builder.fonts_map(self.db)
        self.assertIn("branding/typography.json", seen)
        self.assertEqual(d["headline"], "B-Bold")

    def test_no_direct_read_of_a_path_file_is_left_in_ae_builder(self):
        left = [f"{n}: {name}" for f, n, name in G.direct_reads() if f == "lib/ae_builder.py"
                and (name == "?" or client_db.path_fields(name))]
        left += [f"{n}: {name}" for f, n, name in G.named_paths() if f == "lib/ae_builder.py"]
        self.assertEqual(left, [])
        self.assertFalse(hasattr(G, "PENDING_SWAP"), "delete PENDING_SWAP in test_t45_guard.py with this patch")


if __name__ == "__main__":
    unittest.main()
