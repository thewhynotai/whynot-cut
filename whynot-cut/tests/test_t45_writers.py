# SPDX-License-Identifier: GPL-3.0-or-later
# © 2026 The Why Not AI (thewhynot.ai)
"""3.0 Phase 4 T4.5 (part B) — the writers of the client database store paths relative to the client root (POSIX):
`client_db.build` (both asset manifests, typography) and `ref_analysis` (the cache, its keys, every measurements file);
`load` turns them back into paths this computer opens. Case list: work notes BL-14 cases.md W1–W7.
Run:  bash tools/test.sh -p test_t45_writers.py
"""
import sys as _sys
_sys.dont_write_bytecode = True  # keep the plugin folder free of __pycache__
import _isolation  # noqa: F401,E402  G79: sandbox the engine home first (tests/_isolation.py)
import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys = _sys
SK = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SK / "engine" / "reel"))
sys.path.insert(0, str(SK / "tests"))

from lib import client_db as CDB, ref_analysis as RA  # noqa: E402
from lib.common import Paths, read_json, write_json  # noqa: E402

IS_WIN = os.name == "nt"


def link_dir(target, at):
    if IS_WIN:
        import _winapi
        _winapi.CreateJunction(str(target), str(at))
    else:
        os.symlink(str(target), str(at), target_is_directory=True)


def make_client(parent: Path, name: str) -> Path:
    root = parent / name
    for d in ("assets/Brand", "assets/Fonts", "data/References", "output"):
        (root / d).mkdir(parents=True)
    from PIL import Image
    Image.new("RGBA", (64, 32), (10, 20, 30, 0)).save(root / "assets/Brand/logo.png")
    Image.new("RGB", (40, 80), (200, 20, 30)).save(root / "assets/Brand/poster.jpg")
    from test_font_pairing import make_font
    make_font(family="Brand", style="Bold", weight=700).save(str(root / "assets/Fonts/Brand-Bold.ttf"))
    return root


def inventory(root: Path) -> dict:
    files = []
    for rel, kind, role in (("assets/Brand/logo.png", "image", "logo"), ("assets/Brand/poster.jpg", "image", "brand_image"),
                            ("assets/Fonts/Brand-Bold.ttf", "font", "font")):
        files.append({"rel": rel, "path": str(root / rel), "kind": kind, "role": role})
    return {"files": files}


class Base(unittest.TestCase):
    NAME = "Dr Test د. تجربة"                                     # Arabic with spaces

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.root = make_client(self.tmp, self.NAME)
        self.paths = Paths(self.root)
        self.db = self.paths.client_db
        for p in (mock.patch.object(CDB, "installed_postscript_names", return_value={}),
                  mock.patch.object(CDB.plat, "font_dirs", return_value=[])):
            p.start()
            self.addCleanup(p.stop)

    def tearDown(self):
        for c in self.tmp.iterdir():
            if os.path.islink(c) or (IS_WIN and os.path.isjunction(c)):
                os.rmdir(c) if IS_WIN else os.unlink(c)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def build(self, paths=None):
        paths = paths or self.paths
        return CDB.build(paths, inventory(paths.root))


class TestBuildWritesRelative(Base):
    def test_manifests_and_typography_store_root_relative_posix(self):
        self.build()
        for rel in ("asset-manifest.json", "assets/asset-manifest.json"):
            man = read_json(self.db / rel)
            files = {a["rel"]: a for a in man["assets"]}
            self.assertEqual(set(files), {"assets/Brand/logo.png", "assets/Brand/poster.jpg"})
            logo = files["assets/Brand/logo.png"]
            self.assertEqual(logo["file"], "assets/Brand/logo.png")
            self.assertEqual(logo["display_derivative"], "output/client_database/assets/derivatives/logo_alpha.png")
            self.assertTrue(CDB.is_relative(files["assets/Brand/poster.jpg"]["display_derivative"]))
        typ = read_json(self.db / "branding/typography.json")
        w = [w for fam in typ["families"].values() for w in fam["weights"]]
        self.assertEqual([x["file"] for x in w], ["assets/Fonts/Brand-Bold.ttf"])
        self.assertEqual(typ["missing_or_uninstalled"], ["assets/Fonts/Brand-Bold.ttf"])
        self.assertNotIn(str(self.tmp), json.dumps(read_json(self.db / "asset-manifest.json"), ensure_ascii=False))

    def test_load_gives_back_paths_that_open(self):
        self.build()
        man = CDB.load(self.paths, "asset-manifest.json")
        for a in man["assets"]:
            self.assertTrue(Path(a["file"]).is_file(), a["file"])
            self.assertTrue(Path(a["display_derivative"]).is_file(), a["display_derivative"])
        typ = CDB.load(self.paths, "branding/typography.json")
        f = next(iter(typ["families"].values()))["weights"][0]["file"]
        self.assertTrue(Path(f).is_file())

    def test_a_root_reached_through_a_junction_still_writes_relative(self):
        alias = self.tmp / "alias"
        link_dir(self.root, alias)
        self.build(Paths(alias))
        man = read_json(self.db / "asset-manifest.json")
        self.assertEqual(sorted(a["file"] for a in man["assets"]), ["assets/Brand/logo.png", "assets/Brand/poster.jpg"])

    def test_raw_derivative_is_relative_too(self):
        (self.root / "assets/Brand/shot.cr2").write_bytes(b"raw")
        jpg = self.db / "assets/derivatives/shot_from_raw.jpg"
        jpg.parent.mkdir(parents=True, exist_ok=True)
        from PIL import Image
        Image.new("RGB", (30, 30)).save(jpg)                     # the RAW render made earlier (cached)
        inv = inventory(self.root)
        inv["files"].append({"rel": "assets/Brand/shot.cr2", "path": str(self.root / "assets/Brand/shot.cr2"),
                             "kind": "raw_image", "role": "brand_image"})
        CDB.build(self.paths, inv)
        a = next(a for a in read_json(self.db / "asset-manifest.json")["assets"] if a["rel"].endswith(".cr2"))
        self.assertEqual(a["raw_derivative"], "output/client_database/assets/derivatives/shot_from_raw.jpg")


class TestToStored(unittest.TestCase):
    def test_forms(self):
        root = str(Path(tempfile.gettempdir()) / "C l" / "عميل")
        inside = os.path.join(root, "assets", "a b.png")
        self.assertEqual(CDB.to_stored(root, inside), "assets/a b.png")
        self.assertEqual(CDB.to_stored(root, "assets\\x\\y.png"), "assets/x/y.png")
        self.assertEqual(CDB.to_stored(root, "./assets//y.png"), "assets/y.png")
        outside = str(Path(tempfile.gettempdir()) / "Fonts" / "f.ttf")
        self.assertEqual(CDB.to_stored(root, outside), outside)                  # kept, never invented
        for v in ("", None, 3, "../x.png", ["a"]):
            self.assertEqual(CDB.to_stored(root, v), v)
        self.assertEqual(CDB.to_stored(root, root), root)                        # the root itself: not a file path

    def test_case_is_folded_where_the_file_system_folds_it(self):
        with mock.patch("lib.client_move_paths.FOLD_CASE", True):
            self.assertEqual(CDB.rel_under("/Clients/ACME/Assets/a.png", "/clients/acme"), "Assets/a.png")
        with mock.patch("lib.client_move_paths.FOLD_CASE", False), \
                mock.patch("lib.client_move_paths.real", side_effect=lambda p: str(p)):
            self.assertIsNone(CDB.rel_under("/Clients/ACME/Assets/a.png", "/clients/acme"))

    def test_darwin_var_alias_is_compared_on_real_paths(self):
        real = {"/var/folders/x/C": "/private/var/folders/x/C"}
        fake = lambda p: real.get(str(p), str(p).replace("/var/", "/private/var/", 1) if str(p).startswith("/var/")
                                  else str(p))
        with mock.patch("lib.client_move_paths.real", side_effect=fake), \
                mock.patch("lib.client_move_paths.FOLD_CASE", True):
            self.assertEqual(CDB.rel_under("/private/var/folders/x/C/assets/a.png", "/var/folders/x/C"),
                             "assets/a.png")

    def test_extended_length_and_unc_prefixes(self):
        self.assertEqual(CDB._plain("\\\\?\\C:\\x"), "C:\\x")
        self.assertEqual(CDB._plain("\\\\?\\UNC\\srv\\share\\x"), "\\\\srv\\share\\x")
        with mock.patch("lib.client_move_paths.real", side_effect=lambda p: str(p)), \
                mock.patch("lib.client_move_paths.FOLD_CASE", True):
            self.assertEqual(CDB.rel_under("\\\\?\\D:\\Clients\\A\\assets\\a.png", "D:\\Clients\\A"), "assets/a.png")
            self.assertEqual(CDB.rel_under("\\\\srv\\share\\A\\data\\x.mp4", "\\\\SRV\\share\\A"), "data/x.mp4")

    def test_old_root_wins_over_the_anchor_rule(self):
        with tempfile.TemporaryDirectory() as t:
            root = Path(t) / "new"
            (root / "data" / "C" / "assets").mkdir(parents=True)     # a decoy the anchor rule would pick first
            (root / "assets").mkdir()
            (root / "assets" / "a.png").write_bytes(b"x")
            (root / "data" / "C" / "assets" / "a.png").write_bytes(b"x")
            old = str(Path(t) / "data" / "C")
            v = os.path.join(old, "assets", "a.png")
            self.assertEqual(CDB.to_stored(root, v), "data/C/assets/a.png")         # anchors: earliest wins
            self.assertEqual(CDB.to_stored(root, v, old_roots=[old]), "assets/a.png")


def fake_analyze(calls):
    def run(video, out_dir, duration_s, root=None):
        calls.append(str(video))
        sd = Path(out_dir) / Path(video).stem
        sd.mkdir(parents=True, exist_ok=True)
        (sd / "sheet_00.jpg").write_bytes(b"jpg")
        res = {"video": str(video), "duration_s": duration_s, "cut_count": 1, "cuts_per_minute": 30.0,
               "shot_durations_s": [1.0, 1.0], "shot_stats": {}, "first_cut_s": 1.0,
               "contact_sheets": [str(sd / "sheet_00.jpg")], "cut_frames": [str(sd / "cuts" / "t0001.08.jpg")]}
        if root is not None:
            CDB.stored(root, "reference_analysis/x/measurements.json", res)
        write_json(sd / "measurements.json", res)
        return res
    return run


class TestRefAnalysis(Base):
    def setUp(self):
        super().setUp()
        self.ref = self.root / "data/References/مرجع 1.mp4"
        self.ref.write_bytes(b"video")
        self.calls = []
        p = mock.patch.object(RA, "analyze_reference", side_effect=fake_analyze(self.calls))
        p.start()
        self.addCleanup(p.stop)
        q = mock.patch.object(RA, "log")
        q.start()
        self.addCleanup(q.stop)
        self.ra = self.db / "reference_analysis"

    def run_all(self, root=None, vid=None):
        root = root or self.root
        ref = root / self.ref.relative_to(self.root)
        return RA.analyze_all(Paths(root, vid), [ref], {str(ref): 2.0})

    def test_cache_key_and_values_are_relative_and_the_return_opens(self):
        res = self.run_all(vid="R01")
        st = self.ref.stat()
        idx = read_json(self.ra / "cache.json")
        self.assertEqual(list(idx), [f"data/References/مرجع 1.mp4|{st.st_size}|{int(st.st_mtime)}"])
        e = next(iter(idx.values()))
        self.assertEqual(e["video"], "data/References/مرجع 1.mp4")
        self.assertEqual(e["contact_sheets"], ["output/client_database/reference_analysis/مرجع 1/sheet_00.jpg"])
        self.assertTrue(all(CDB.is_relative(x) for x in e["cut_frames"]))
        for f in (self.ra / "reference-measurements.json",
                  Paths(self.root, "R01").p("01_analysis/reference_analysis") / "reference-measurements.json"):
            doc = read_json(f)
            self.assertEqual(doc["references"][0]["video"], "data/References/مرجع 1.mp4", f)
            self.assertTrue(CDB.is_relative(doc["references"][0]["contact_sheets"][0]))
        m = read_json(self.ra / "مرجع 1" / "measurements.json")
        self.assertEqual(m["video"], "data/References/مرجع 1.mp4")
        self.assertTrue(Path(res["references"][0]["contact_sheets"][0]).is_file())    # the caller can open it
        self.assertTrue(Path(res["references"][0]["video"]).is_file())

    def test_a_moved_client_hits_its_cache(self):
        self.run_all()
        new = self.tmp / "moved"
        shutil.copytree(self.root, new, copy_function=shutil.copy2)
        self.calls.clear()
        res = self.run_all(new)
        self.assertEqual(self.calls, [])
        self.assertTrue(Path(res["references"][0]["contact_sheets"][0]).is_relative_to(new))

    def test_a_legacy_absolute_key_of_this_file_is_reused_and_stored_relative(self):
        st = self.ref.stat()
        sd = self.ra / "مرجع 1"
        sd.mkdir(parents=True)
        (sd / "sheet_00.jpg").write_bytes(b"jpg")
        old_key = f"{self.ref.resolve()}|{st.st_size}|{int(st.st_mtime)}"
        legacy = {"video": str(self.ref), "duration_s": 2.0, "cut_count": 0, "cuts_per_minute": 0, "shot_durations_s": [2.0],
                  "shot_stats": {}, "first_cut_s": None, "contact_sheets": [str(sd / "sheet_00.jpg")], "cut_frames": []}
        write_json(self.ra / "cache.json", {old_key: legacy})
        self.run_all()
        self.assertEqual(self.calls, [])                                      # no re-analysis after the upgrade
        idx = read_json(self.ra / "cache.json")
        new_key = f"data/References/مرجع 1.mp4|{st.st_size}|{int(st.st_mtime)}"
        self.assertEqual(idx[new_key]["contact_sheets"], ["output/client_database/reference_analysis/مرجع 1/sheet_00.jpg"])
        self.assertEqual(idx[old_key]["video"], str(self.ref))                # the old entry is left as it was

    def test_an_old_roots_key_or_a_damaged_entry_is_analysed_again_never_a_crash(self):
        st = self.ref.stat()
        tail = f"|{st.st_size}|{int(st.st_mtime)}"
        for bad in ({"/elsewhere/C/data/References/مرجع 1.mp4" + tail: {"contact_sheets": ["/elsewhere/x.jpg"]}},
                    {"data/References/مرجع 1.mp4" + tail: {"contact_sheets": "nope"}},
                    {"data/References/مرجع 1.mp4" + tail: {"contact_sheets": [], "shot_durations_s": [1]}},
                    ["not", "a", "dict"]):
            self.calls.clear()
            write_json(self.ra / "cache.json", bad) if self.ra.exists() else (self.ra.mkdir(parents=True),
                                                                               write_json(self.ra / "cache.json", bad))
            self.run_all()
            self.assertEqual(len(self.calls), 1, bad)


class TestAnalyzeReferenceWritesRelative(Base):
    def test_measurements_file_is_root_relative_and_the_record_too(self):
        ref = self.root / "data/References/r.mp4"
        ref.write_bytes(b"v")
        out = self.db / "reference_analysis"

        def sheet(video, o, **k):
            o.parent.mkdir(parents=True, exist_ok=True)
            o.write_bytes(b"j")
            return o
        with mock.patch.object(RA, "detect_cuts", return_value=[0.5]), \
                mock.patch.object(RA, "contact_sheet", side_effect=sheet), \
                mock.patch.object(RA, "frames_at", side_effect=lambda v, ts, d, **k: [d / "t0000.58.jpg"]), \
                mock.patch.object(RA, "loudness_envelope", return_value=[-20.0]):
            res = RA.analyze_reference(ref, out, 1.0, root=self.root)
        m = read_json(out / "r" / "measurements.json")
        self.assertEqual(m["video"], "data/References/r.mp4")
        self.assertEqual(m["contact_sheets"], ["output/client_database/reference_analysis/r/sheet_00.jpg"])
        self.assertEqual(m["cut_frames"], ["output/client_database/reference_analysis/r/cuts/t0000.58.jpg"])
        self.assertEqual(res["video"], "data/References/r.mp4")
        with mock.patch.object(RA, "detect_cuts", return_value=[]), \
                mock.patch.object(RA, "contact_sheet", side_effect=sheet), \
                mock.patch.object(RA, "frames_at", return_value=[]), \
                mock.patch.object(RA, "loudness_envelope", return_value=[]):
            res = RA.analyze_reference(ref, out, 1.0)                   # no root (another caller): as before
        self.assertEqual(res["video"], str(ref))


class TestCaptionFontsReadThroughLoad(Base):
    def test_relative_typography_gives_the_caption_chain_a_file_that_exists(self):
        from lib import looks_captions
        self.build()
        typ = read_json(self.db / "branding/typography.json")
        self.assertTrue(CDB.is_relative(next(iter(typ["families"].values()))["weights"][0]["file"]))
        seen = {}
        with mock.patch.object(looks_captions, "font_chain", side_effect=lambda t, *a, **k: seen.setdefault("t", t)):
            looks_captions._caption_fonts(self.paths, None)
        f = next(iter(seen["t"]["families"].values()))["weights"][0]["file"]
        self.assertTrue(Path(f).is_file(), f)


if __name__ == "__main__":
    unittest.main()
