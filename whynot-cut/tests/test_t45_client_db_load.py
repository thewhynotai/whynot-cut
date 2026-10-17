# SPDX-License-Identifier: GPL-3.0-or-later
# © 2026 The Why Not AI (thewhynot.ai)
"""3.0 Phase 4 T4.5 (part A) — `client_db.load`: every reader of a client-database file that carries paths gets
paths it can open, whether the file stores them relative to the client root (3.0) or absolute (2.x and older 3.0,
possibly from the folder the client was copied from). A reader never writes. Case list: the wnc-queue track's notes.
Run:  bash tools/test.sh -p test_t45_client_db_load.py
"""
import sys as _sys
_sys.dont_write_bytecode = True  # keep the plugin folder free of __pycache__
import _isolation  # noqa: F401,E402  G79: sandbox the engine home first (tests/_isolation.py)
import os
import shutil
import tempfile
import unittest
from pathlib import Path, PurePosixPath, PureWindowsPath
from unittest import mock

sys = _sys
SK = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SK / "engine" / "reel"))

from lib import client_db as CDB  # noqa: E402
from lib.common import Paths, write_json  # noqa: E402

REL_LOGO = "output/client_database/assets/derivatives/logo_display.jpg"


def make_client(parent: Path, name: str) -> Path:
    root = parent / name
    for d in ("assets/Brand", "data/Raw", "output/client_database/assets/derivatives", "output/client_database/branding"):
        (root / d).mkdir(parents=True)
    (root / "assets/Brand/logo.png").write_bytes(b"png")
    (root / REL_LOGO).write_bytes(b"jpg")
    (root / "assets/Brand/Brand-Bold.ttf").write_bytes(b"ttf")
    return root


class Base(unittest.TestCase):
    NAME = "Dr Test د. تجربة"                                # Arabic with spaces

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.root = make_client(self.tmp, self.NAME)
        self.paths = Paths(self.root)
        self.db = self.paths.client_db

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def manifest(self, file, disp, raw=None):
        a = {"file": file, "display_derivative": disp, "rel": "assets/Brand/logo.png", "category": "logo"}
        if raw is not None:
            a["raw_derivative"] = raw
        write_json(self.db / "asset-manifest.json", {"assets": [a], "count": 1})


class TestResolve(Base):
    def test_relative_values_resolve_against_the_root(self):
        self.manifest("assets/Brand/logo.png", REL_LOGO)
        a = CDB.load(self.paths, "asset-manifest.json")["assets"][0]
        self.assertEqual(Path(a["file"]), self.root / "assets/Brand/logo.png")
        self.assertEqual(Path(a["display_derivative"]), self.root / REL_LOGO)
        self.assertTrue(Path(a["display_derivative"]).is_file())
        self.assertEqual(a["rel"], "assets/Brand/logo.png")             # not a path field: untouched

    def test_an_object_with_only_client_db_uses_the_root_above_it(self):
        self.manifest("assets/Brand/logo.png", REL_LOGO)

        class Ep:                                                         # e.g. a test's stand-in for EpisodePaths
            client_db = self.db
        for given in (Ep(), self.db, str(self.db)):
            a = CDB.load(given, "asset-manifest.json")["assets"][0]
            self.assertEqual(Path(a["display_derivative"]), self.root / REL_LOGO, given)

    def test_absolute_inside_the_root_is_kept(self):
        self.manifest(str(self.root / "assets/Brand/logo.png"), str(self.root / REL_LOGO))
        a = CDB.load(self.paths, "asset-manifest.json")["assets"][0]
        self.assertEqual(Path(a["file"]), self.root / "assets/Brand/logo.png")
        self.assertEqual(Path(a["display_derivative"]), self.root / REL_LOGO)

    def test_absolute_from_an_old_root_is_rebased_when_the_file_is_here(self):
        old = self.tmp / "data" / "old drive" / "عميل قديم"                # the OLD place has a "data" folder above it
        self.manifest(str(old / "assets/Brand/logo.png"), str(old / REL_LOGO), raw=str(old / "assets/gone.cr2"))
        a = CDB.load(self.paths, "asset-manifest.json")["assets"][0]
        self.assertEqual(Path(a["file"]), self.root / "assets/Brand/logo.png")
        self.assertEqual(Path(a["display_derivative"]), self.root / REL_LOGO)
        self.assertEqual(a["raw_derivative"], str(old / "assets/gone.cr2"))   # not here: kept, never invented

    def test_both_forms_in_one_file_and_typography(self):
        write_json(self.db / "branding/typography.json", {"families": {"Brand": {"weights": [
            {"style": "Bold", "file": "assets/Brand/Brand-Bold.ttf"},
            {"style": "Regular", "file": str(self.root / "assets/Brand/Brand-Bold.ttf")},
            {"style": "Thin", "file": None}]}},
            "missing_or_uninstalled": ["assets/Brand/Brand-Bold.ttf"], "roles": {"title": "assets/x.ttf"}})
        t = CDB.load(self.paths, "branding/typography.json")
        ws = t["families"]["Brand"]["weights"]
        self.assertEqual(Path(ws[0]["file"]), self.root / "assets/Brand/Brand-Bold.ttf")
        self.assertEqual(Path(ws[1]["file"]), self.root / "assets/Brand/Brand-Bold.ttf")
        self.assertIsNone(ws[2]["file"])
        self.assertEqual(Path(t["missing_or_uninstalled"][0]), self.root / "assets/Brand/Brand-Bold.ttf")
        self.assertEqual(t["roles"], {"title": "assets/x.ttf"})            # roles are names/specs, not path fields

    def test_reference_analysis_files(self):
        old = self.tmp / "elsewhere" / "C"
        (self.root / "data/References").mkdir()
        (self.root / "data/References/ref.mp4").write_bytes(b"v")
        sheet = "output/client_database/reference_analysis/ref/sheet_00.jpg"
        (self.root / sheet).parent.mkdir(parents=True)
        (self.root / sheet).write_bytes(b"j")
        write_json(self.db / "reference_analysis/ref/measurements.json",
                   {"video": str(old / "data/References/ref.mp4"), "contact_sheets": [sheet], "cut_frames": []})
        m = CDB.load(self.paths, "reference_analysis/ref/measurements.json")
        self.assertEqual(Path(m["video"]), self.root / "data/References/ref.mp4")
        self.assertEqual(Path(m["contact_sheets"][0]), self.root / sheet)
        write_json(self.db / "reference_analysis/reference-measurements.json",
                   {"references": [{"video": "data/References/ref.mp4", "contact_sheets": [sheet]}]})
        r = CDB.load(self.paths, "reference_analysis/reference-measurements.json")["references"][0]
        self.assertEqual(Path(r["video"]), self.root / "data/References/ref.mp4")

    def test_missing_gives_the_default_damaged_is_named_like_read_json(self):
        self.assertEqual(CDB.load(self.paths, "asset-manifest.json", {"assets": []}), {"assets": []})
        (self.db / "asset-manifest.json").write_text("{broken", encoding="utf-8")
        from lib.errors import FileFormatError
        with self.assertRaises(FileFormatError):                     # the readers' behaviour is unchanged
            CDB.load(self.paths, "asset-manifest.json", {"assets": []})
        write_json(self.db / "asset-manifest.json", {"assets": [{"file": 5}, "x", None]})
        self.assertEqual(CDB.load(self.paths, "asset-manifest.json")["assets"], [{"file": 5}, "x", None])

    def test_a_file_without_path_fields_is_read_as_is(self):
        write_json(self.db / "branding/brand-tokens.json", {"official_colors": [{"hex": "#112233"}]})
        self.assertEqual(CDB.load(self.paths, "branding/brand-tokens.json"),
                         {"official_colors": [{"hex": "#112233"}]})

    def test_a_reader_never_writes(self):
        self.manifest(str(self.root / "assets/Brand/logo.png"), "assets/Brand/logo.png")
        f = self.db / "asset-manifest.json"
        before = (f.read_bytes(), f.stat().st_mtime_ns)
        CDB.load(self.paths, "asset-manifest.json")
        self.assertEqual((f.read_bytes(), f.stat().st_mtime_ns), before)

    def test_the_default_is_never_shared(self):
        d = {"assets": []}
        got = CDB.load(self.paths, "asset-manifest.json", d)
        got["assets"].append(1)
        self.assertEqual(d, {"assets": []})


class TestPathRules(unittest.TestCase):
    """The pure rules, Windows and POSIX forms, without touching a disk."""

    def test_inside_folds_case_on_windows_and_mac(self):
        root = r"D:\Clients\Dr Test د. تجربة"
        self.assertTrue(CDB.inside_root(r"d:\clients\DR TEST د. تجربة\assets\x.png", root, fold=True, sep="\\"))
        self.assertFalse(CDB.inside_root(r"d:\clients\DR TEST د. تجربة\assets\x.png", root, fold=False, sep="\\"))
        self.assertFalse(CDB.inside_root(r"D:\Clients\Dr Test د. تجربة 2\x.png", root, fold=True, sep="\\"))

    def test_relative_values_are_posix_and_never_climb_out(self):
        self.assertTrue(CDB.is_relative("assets/Brand/logo.png"))
        self.assertTrue(CDB.is_relative("assets\\Brand\\logo.png"))
        for v in ("/Users/x/C/assets/a.png", "D:\\C\\a.png", "D:/C/a.png", "\\\\server\\share\\a.png", "../x.png",
                  "assets/../../x.png", ""):
            self.assertFalse(CDB.is_relative(v), v)

    def test_anchor_tail(self):
        self.assertEqual(CDB.anchor_tails(PureWindowsPath(r"D:\data\old\C\assets\Brand\logo.png")),
                         ["data/old/C/assets/Brand/logo.png", "assets/Brand/logo.png"])
        self.assertEqual(CDB.anchor_tails(PurePosixPath("/Volumes/X/C/output/client_database/assets/d.jpg")),
                         ["output/client_database/assets/d.jpg", "assets/d.jpg"])
        self.assertEqual(CDB.anchor_tails(PurePosixPath("/tmp/nothing/here.png")), [])


@unittest.skipUnless(sys.platform == "darwin" or os.name == "nt", "the /private/var case needs a real-path alias")
class TestRealPathAlias(Base):
    def test_a_root_reached_through_an_alias_still_counts_as_inside(self):
        """macOS: /var/folders/... is /private/var/folders/...; Windows: a junction to the client folder."""
        alias = self.tmp / "alias"
        if os.name == "nt":
            import _winapi
            _winapi.CreateJunction(str(self.root), str(alias))
        else:
            os.symlink(self.root, alias)
        try:
            self.manifest(str(alias / "assets/Brand/logo.png"), str(alias / REL_LOGO))
            a = CDB.load(self.paths, "asset-manifest.json")["assets"][0]
            self.assertTrue(Path(a["file"]).is_file())
            self.assertTrue(CDB.inside_root(str(alias / "assets/Brand/logo.png"), str(self.root)) or
                            Path(a["file"]) == self.root / "assets/Brand/logo.png")
        finally:
            os.rmdir(alias) if os.name == "nt" else alias.unlink()


class TestDarwinPrivateVar(unittest.TestCase):
    def test_private_var_is_the_same_root(self):
        real = {"/var/folders/a/C": "/private/var/folders/a/C",
                "/private/var/folders/a/C/assets/x.png": "/private/var/folders/a/C/assets/x.png"}
        from lib import client_move_paths as CMP
        with mock.patch.object(CMP, "real", side_effect=lambda p: real.get(str(p), str(p))):
            self.assertTrue(CDB.inside_root("/private/var/folders/a/C/assets/x.png", "/var/folders/a/C",
                                            fold=True, sep="/"))


class TestReaders(Base):
    """The readers swapped to client_db.load find the files of a client whose database stores relative paths."""

    def test_publish_logo(self):
        self.manifest("assets/Brand/logo.png", REL_LOGO)
        from lib import publish
        src = Path(publish.__file__).read_text(encoding="utf-8")
        self.assertIn('client_db.load(', src)
        self.assertNotIn('read_json(ep.client_db / "asset-manifest.json"', src)

    def test_ps_builder_and_qc_use_load(self):
        for mod in ("ps_builder", "qc"):
            src = (SK / "engine/reel/lib" / f"{mod}.py").read_text(encoding="utf-8")
            self.assertIn("client_db.load(", src, mod)
            self.assertNotRegex(src, r'read_json\(paths\.client_db / "(asset-manifest|branding/typography)\.json"', mod)


if __name__ == "__main__":
    unittest.main()
