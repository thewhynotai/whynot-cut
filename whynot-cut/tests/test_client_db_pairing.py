# SPDX-License-Identifier: GPL-3.0-or-later
# © 2026 The Why Not AI (thewhynot.ai)
"""Addendum M M2-T4 (wnc-queue part): typography.json gains `pairing` per role
{arabic, latin, latin_scale, source: "client" | "table", score}, and `reel client-db` re-runs (client_db.build) never
wipe it: the pair already in typography.json stays, branding/typography-roles.json `pairing` wins per role, an unusable
entry is left out and named in the database status. lib/font_pairing then reads it (the client's pair always wins).
Run: bash tools/test.sh -p test_client_db_pairing.py
"""
import sys as _sys
_sys.dont_write_bytecode = True  # keep the plugin folder free of __pycache__
import _isolation  # noqa: F401,E402  G79: sandbox the engine home first (tests/_isolation.py)
import json
import shutil
import tempfile
import unittest
from pathlib import Path

sys = _sys
SK = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SK / "engine" / "reel"))

from lib import client_db as CDB  # noqa: E402
from lib import font_pairing  # noqa: E402
from lib.common import Paths, write_json  # noqa: E402

FONTS = SK.parent / "guide-ar" / "fonts"


class TestPairingField(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="t56db_"))
        self.root = self.tmp / "عميل تجربة"
        brand = self.root / "assets" / "Brand"
        brand.mkdir(parents=True)
        (self.root / "data").mkdir()
        self.fonts = []
        for src in (FONTS / "ibmplexsansarabic" / "IBMPlexSansArabic-SemiBold.ttf", FONTS / "inter" / "Inter-Bold.ttf"):
            dst = brand / src.name
            shutil.copyfile(src, dst)
            self.fonts.append(dst)
        self.paths = Paths(self.root)
        self.db = self.paths.client_db
        font_pairing.clear_cache()

    def tearDown(self):
        _isolation.rmtree_retry(self.tmp)                  # Windows: retries a briefly locked folder (WinError 145)

    def build(self) -> dict:
        inv = {"files": [{"kind": "font", "path": str(f), "rel": f.relative_to(self.root).as_posix(), "role": "font"}
                         for f in self.fonts]}
        CDB.build(self.paths, inv)
        return json.loads((self.db / "branding" / "typography.json").read_text(encoding="utf-8"))

    def status(self) -> dict:
        return json.loads((self.db / "client-database-status.json").read_text(encoding="utf-8"))

    def test_no_pairing_keeps_todays_shape(self):
        self.assertNotIn("pairing", self.build())

    def test_an_editor_set_pair_survives_a_rebuild(self):
        typ = self.build()
        typ["pairing"] = {"caption": {"arabic": "IBM Plex Sans Arabic", "latin": "Inter", "latin_scale": 0.84,
                                      "source": "client", "score": 83.1}}
        write_json(self.db / "branding" / "typography.json", typ)
        again = self.build()
        self.assertEqual(again["pairing"], typ["pairing"])
        self.assertEqual(self.build()["pairing"], typ["pairing"])          # and the next re-run too

    def test_typography_roles_pairing_wins_per_role(self):
        typ = self.build()
        typ["pairing"] = {"caption": {"arabic": "IBM Plex Sans Arabic", "latin": "Inter", "source": "table",
                                      "score": 83.1},
                          "headline": {"arabic": "IBM Plex Sans Arabic", "latin": "Inter", "source": "client"}}
        write_json(self.db / "branding" / "typography.json", typ)
        write_json(self.db / "branding" / "typography-roles.json",
                   {"pairing": {"caption": {"arabic": "IBMPlexSansArabic-SemiBold", "latin": "Inter-Bold",
                                            "source": "client", "class": "humanist", "latin_class": "humanist"}}})
        p = self.build()["pairing"]
        self.assertEqual(p["caption"], {"arabic": "IBMPlexSansArabic-SemiBold", "latin": "Inter-Bold",
                                        "source": "client", "class": "humanist", "latin_class": "humanist"})
        self.assertEqual(p["headline"]["source"], "client")

    def test_unusable_entries_are_left_out_and_named(self):
        self.build()
        write_json(self.db / "branding" / "typography-roles.json",
                   {"pairing": {"caption": {"arabic": "IBM Plex Sans Arabic"},
                                "body": {"arabic": "A", "latin": "B", "source": "guess"},
                                "term": {"arabic": "IBM Plex Sans Arabic", "latin": "Inter", "latin_scale": 9}}})
        typ = self.build()
        self.assertEqual(sorted(typ["pairing"]), ["term"])
        self.assertNotIn("latin_scale", typ["pairing"]["term"])
        issues = " ".join(self.status()["issues"])
        for word in ("pairing.caption", "pairing.body", "pairing.term"):
            self.assertIn(word, issues)

    def test_font_pairing_reads_the_built_pair_and_the_client_wins(self):
        write_json(self.db / "branding" / "typography-roles.json",
                   {"pairing": {"caption": {"arabic": "IBM Plex Sans Arabic", "latin": "Inter", "source": "client"}}})
        self.build()
        typ = CDB.load(self.paths, "branding/typography.json")
        r = font_pairing.pick("caption", typ)
        self.assertEqual((r["pair"]["source"], r["pair"]["arabic"]["family"], r["pair"]["latin"]["family"]),
                         ("client", "IBM Plex Sans Arabic", "Inter"))
        self.assertIsNotNone(r["pair"]["score"])


if __name__ == "__main__":
    unittest.main()
