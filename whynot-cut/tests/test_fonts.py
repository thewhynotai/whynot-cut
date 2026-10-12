"""3.0 T2.10 — one font discovery (IM-12, G72, Adobe Fonts):
  * .ttc/.otc collections are indexed face by face (PostScript name -> file + face index), font folders recursively;
  * the macOS folders (/System/Library/Fonts/Supplemental, ~/Library/Fonts) and the Adobe Fonts (Creative Cloud
    livetype) folders are searched; livetype files have obfuscated names, so faces are found by the names inside them;
  * the index is cached in the engine home and rebuilt when a font folder changes;
  * a client without an Arabic font gets a system Arabic fallback at the right size (never Pillow's bitmap font) and a
    warning naming it (previews, `reel plan`, caption stills, thumbnails), or one saying Arabic cannot be drawn when the
    computer has no Arabic font either; Arabic support is read from the character map;
  * a face of a collection is measured with that face (face index carried from discovery to fit() and the animatic).
Every test builds its own synthetic fonts (fontTools FontBuilder) in a temp folder and injects the font folders: no
real system font folder is scanned (tests/_isolation.py points discovery at an empty folder).
Run: bash tools/test.sh -p test_fonts.py
"""
import sys as _sys
_sys.dont_write_bytecode = True  # keep the plugin folder free of __pycache__
import _isolation  # noqa: F401,E402  G79: sandbox the engine home first (tests/_isolation.py)
import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SK = Path(__file__).resolve().parents[1]
sys = _sys
sys.path.insert(0, str(SK / "engine" / "reel"))

from lib import common, fonts, plat  # noqa: E402

ARABIC_RANGE = 1 << 13          # OS/2 ulUnicodeRange1 bit 13: Arabic


ARABIC_GLYPHS = {0x0627: "alef", 0x0628: "beh", 0x0644: "lam", 0x0645: "meem", 0x0646: "noon"}


def make_font(family: str, style: str, ps: str, arabic: bool = False, weight: int = 400, advance: int = 500,
              os2_arabic: bool | None = None):
    """A tiny valid TrueType font (box glyphs, every glyph `advance` units wide) with the given names; Arabic letters
    in the cmap when `arabic`; the OS/2 Arabic range bit as `os2_arabic` says (default: same as `arabic`)."""
    from fontTools.fontBuilder import FontBuilder
    from fontTools.pens.ttGlyphPen import TTGlyphPen
    order = [".notdef", "space", "A", "a"] + (list(ARABIC_GLYPHS.values()) if arabic else [])
    cmap = {0x20: "space", 0x41: "A", 0x61: "a"}
    if arabic:
        cmap.update(ARABIC_GLYPHS)
    os2_arabic = arabic if os2_arabic is None else os2_arabic
    fb = FontBuilder(1000, isTTF=True)
    fb.setupGlyphOrder(order)
    fb.setupCharacterMap(cmap)
    pen = TTGlyphPen(None)
    pen.moveTo((50, 0))
    pen.lineTo((50, 600))
    pen.lineTo((450, 600))
    pen.lineTo((450, 0))
    pen.closePath()
    box = pen.glyph()
    fb.setupGlyf({g: (TTGlyphPen(None).glyph() if g == "space" else box) for g in order})
    fb.setupHorizontalMetrics({g: (advance, 50) for g in order})
    fb.setupHorizontalHeader(ascent=800, descent=-200)
    fb.setupNameTable({"familyName": family, "styleName": style, "psName": ps, "fullName": f"{family} {style}",
                       "uniqueFontIdentifier": ps})
    fb.setupOS2(usWeightClass=weight, ulUnicodeRange1=ARABIC_RANGE if os2_arabic else 0, sTypoAscender=800,
                sTypoDescender=-200, usWinAscent=800, usWinDescent=200)
    fb.setupPost()
    return fb.font


def save_font(path: Path, *args, **kw) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    make_font(*args, **kw).save(str(path))
    return path


def save_collection(path: Path, faces: list[tuple]) -> Path:
    """A .ttc / .otc holding one synthetic face per (family, style, ps, arabic, weight) tuple, in that order."""
    from fontTools.ttLib import TTCollection
    path.parent.mkdir(parents=True, exist_ok=True)
    coll = TTCollection()
    coll.fonts = [make_font(*f) for f in faces]
    coll.save(str(path))
    return path


class FontDirs(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="t210_"))
        fonts.clear_cache()

    def tearDown(self):
        fonts.clear_cache()
        shutil.rmtree(self.tmp, ignore_errors=True)


class TestCollections(FontDirs):
    def test_geezapro_bold_resolves_from_a_ttc(self):
        sysf = self.tmp / "System/Library/Fonts"
        ttc = save_collection(sysf / "GeezaPro.ttc", [("Geeza Pro", "Regular", "GeezaPro", True, 400),
                                                      ("Geeza Pro", "Bold", "GeezaPro-Bold", True, 700)])
        hit = fonts.find("GeezaPro-Bold", dirs=[sysf])
        self.assertEqual((hit["file"], hit["index"], hit["style"], hit["arabic"]), (str(ttc), 1, "Bold", True))
        self.assertEqual(fonts.find("GeezaPro", dirs=[sysf])["index"], 0)
        self.assertEqual(fonts.find_file("GeezaPro-Bold", dirs=[sysf]), str(ttc))
        self.assertIsNone(fonts.find("NoSuchFont-Bold", dirs=[sysf]))

    def test_otc_and_nested_folders_are_scanned(self):
        root = self.tmp / "fonts"
        save_collection(root / "a/b/Brand.otc", [("Brand Sans", "Regular", "BrandSans-Regular", False, 400),
                                                 ("Brand Sans", "Black", "BrandSans-Black", False, 900)])
        save_font(root / "deep/er/Other.TTF", "Other", "Regular", "Other-Regular")
        (root / "deep/readme.txt").write_text("not a font", encoding="utf-8")
        names = fonts.postscript_names(dirs=[root])
        self.assertEqual(set(names), {"BrandSans-Regular", "BrandSans-Black", "Other-Regular"})
        self.assertEqual(fonts.find("BrandSans-Black", dirs=[root])["index"], 1)

    def test_a_folder_listed_twice_or_nested_gives_each_face_once(self):
        sysf = self.tmp / "System/Library/Fonts"
        save_font(sysf / "Supplemental/Arial.ttf", "Arial", "Regular", "ArialMT", arabic=True)
        faces = fonts.faces(dirs=[sysf, sysf / "Supplemental", sysf])
        self.assertEqual([f["ps"] for f in faces], ["ArialMT"])

    def test_hb_text_renders_a_face_of_a_collection(self):
        from lib import hb_text
        if not hb_text.AVAILABLE:
            self.skipTest("HarfBuzz/FreeType not in this runtime")
        ttc = save_collection(self.tmp / "G.ttc", [("Geeza Pro", "Regular", "GeezaPro", True, 400),
                                                   ("Geeza Pro", "Bold", "GeezaPro-Bold", True, 700)])
        self.assertEqual(hb_text.HBFontSpec(str(ttc), 40, index=1).resolved, "GeezaPro-Bold")
        self.assertEqual(hb_text.HBFontSpec(str(ttc), 40).resolved, "GeezaPro")


class TestPlatformFolders(FontDirs):
    def test_macos_folders(self):
        home = self.tmp / "home"
        got = [str(d) for d in plat.font_dirs(system="darwin", home=home)]
        for want in (home / "Library/Fonts", Path("/Library/Fonts"), Path("/System/Library/Fonts"),
                     Path("/System/Library/Fonts/Supplemental"),
                     home / "Library/Application Support/Adobe/CoreSync/plugins/livetype"):
            self.assertIn(str(want), got)

    def test_windows_folders(self):
        env = {"WINDIR": str(self.tmp / "Windows"), "LOCALAPPDATA": str(self.tmp / "Local"),
               "APPDATA": str(self.tmp / "Roaming")}
        got = [str(d) for d in plat.font_dirs(system="windows", env=env)]
        self.assertEqual(got, [str(self.tmp / "Windows/Fonts"), str(self.tmp / "Local/Microsoft/Windows/Fonts"),
                               str(self.tmp / "Roaming/Adobe/CoreSync/plugins/livetype")])

    def test_macos_layout_resolves_through_injected_folders(self):
        """The macOS folders, re-rooted in a temp folder: Geeza Pro (.ttc in /System/Library/Fonts) and Arial (only in
        Supplemental) are both found, and the Arabic fallback picks Geeza Pro."""
        home, root = self.tmp / "home", self.tmp / "root"
        dirs = [d if str(d).startswith(str(home)) else root / d.relative_to(d.anchor)
                for d in plat.font_dirs(system="darwin", home=home)]
        save_collection(root / "System/Library/Fonts/GeezaPro.ttc",
                        [("Geeza Pro", "Regular", "GeezaPro", True, 400), ("Geeza Pro", "Bold", "GeezaPro-Bold", True, 700)])
        save_font(root / "System/Library/Fonts/Supplemental/Arial.ttf", "Arial", "Regular", "ArialMT", arabic=True)
        save_font(home / "Library/Fonts/Brand-Bold.otf", "Brand", "Bold", "Brand-Bold", weight=700)
        self.assertEqual(fonts.find("GeezaPro-Bold", dirs=dirs)["index"], 1)
        self.assertTrue(fonts.find("ArialMT", dirs=dirs)["file"].endswith("Arial.ttf"))
        self.assertIsNotNone(fonts.find("Brand-Bold", dirs=dirs))
        fb = fonts.arabic_fallback(dirs=dirs, bold=True, system="darwin")
        self.assertEqual((fb["ps"], fb["index"]), ("GeezaPro-Bold", 1))


class TestAdobeFonts(FontDirs):
    def livetype(self) -> Path:
        lt = self.tmp / "Roaming/Adobe/CoreSync/plugins/livetype"
        save_font(lt / "r/62878", "IBM Plex Sans Arabic", "Regular", "IBMPlexSansArabic-Regular", arabic=True)
        save_font(lt / "r/62879", "IBM Plex Sans Arabic", "Bold", "IBMPlexSansArabic-Bold", arabic=True, weight=700)
        (lt / "e").mkdir(parents=True)
        (lt / "e/62878").write_bytes(b"\x5f\x9a\xda\x7e" + b"\x00" * 64)       # an encrypted copy: not a font
        (lt / "c").mkdir()
        (lt / "c/entitlements.xml").write_text("<typekitSyncState/>", encoding="utf-8")
        return lt

    def test_obfuscated_file_found_by_family_name(self):
        lt = self.livetype()
        hit = fonts.find("IBM Plex Sans Arabic", dirs=[lt])
        self.assertEqual((Path(hit["file"]).name, hit["ps"], hit["source"]), ("62878", "IBMPlexSansArabic-Regular",
                                                                               "adobe-fonts"))
        self.assertEqual(Path(fonts.find("IBMPlexSansArabic-Bold", dirs=[lt])["file"]).name, "62879")
        self.assertEqual(Path(fonts.find("ibm plex sans arabic bold", dirs=[lt])["file"]).name, "62879")
        self.assertEqual(len(fonts.faces(dirs=[lt])), 2)        # the encrypted copy and the XML are skipped

    def test_client_db_and_motion_layout_see_adobe_fonts(self):
        lt = self.livetype()
        from lib import client_db, motion_layout
        with mock.patch.object(plat, "font_dirs", lambda: [lt]):
            self.assertEqual(Path(motion_layout.find_font_file("IBMPlexSansArabic-Bold")).name, "62879")
            self.assertEqual(Path(client_db.installed_postscript_names()["IBMPlexSansArabic-Regular"]).name, "62878")


class TestCache(FontDirs):
    def test_index_is_cached_in_the_engine_home_and_follows_the_folders(self):
        d = self.tmp / "fonts"
        save_font(d / "One.ttf", "One", "Regular", "One-Regular")
        self.assertEqual([f["ps"] for f in fonts.faces(dirs=[d])], ["One-Regular"])
        cache = common.current_context().engine_home / "cache" / "font-index.json"
        self.assertTrue(cache.is_file())
        self.assertIn("One-Regular", json.dumps(json.loads(cache.read_text(encoding="utf-8"))))
        fonts.clear_cache(disk=False)                     # a new process: served from the disk cache, no file opened
        with mock.patch.object(fonts, "_read_faces", side_effect=AssertionError("rescanned")):
            self.assertEqual([f["ps"] for f in fonts.faces(dirs=[d])], ["One-Regular"])
        import os
        save_font(d / "sub/Two.ttf", "Two", "Regular", "Two-Regular")
        st = d.stat()
        os.utime(d, ns=(st.st_atime_ns, st.st_mtime_ns + 10_000_000_000))   # coarse file systems
        self.assertEqual(sorted(f["ps"] for f in fonts.faces(dirs=[d])), ["One-Regular", "Two-Regular"])

    def test_unreadable_cache_is_rebuilt(self):
        d = self.tmp / "fonts"
        save_font(d / "One.ttf", "One", "Regular", "One-Regular")
        cache = common.current_context().engine_home / "cache" / "font-index.json"
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_text("{broken", encoding="utf-8")
        self.assertEqual([f["ps"] for f in fonts.faces(dirs=[d])], ["One-Regular"])


class TestArabicFallback(FontDirs):
    def setUp(self):
        super().setUp()
        from lib import ct_text             # macOS: CoreText would draw the REAL installed Tahoma-Bold by name
        p = mock.patch.object(ct_text, "AVAILABLE", False)
        p.start()
        self.addCleanup(p.stop)

    def system_dir(self) -> Path:
        d = self.tmp / "Windows/Fonts"
        save_font(d / "latin.ttf", "Latin Only", "Regular", "LatinOnly-Regular")
        save_font(d / "tahoma.ttf", "Tahoma", "Regular", "Tahoma", arabic=True)
        save_font(d / "tahomabd.ttf", "Tahoma", "Bold", "Tahoma-Bold", arabic=True, weight=700)
        save_font(d / "segoeui.ttf", "Segoe UI", "Regular", "SegoeUI", arabic=True)
        return d

    def test_windows_order_and_weight(self):
        d = self.system_dir()
        self.assertEqual(fonts.arabic_fallback(dirs=[d], system="windows")["ps"], "SegoeUI")
        self.assertEqual(fonts.arabic_fallback(dirs=[d], bold=True, system="windows")["ps"], "Tahoma-Bold")

    def test_any_arabic_face_when_no_known_fallback(self):
        d = self.tmp / "fonts"
        save_font(d / "x.ttf", "Latin Only", "Regular", "LatinOnly-Regular")
        self.assertIsNone(fonts.arabic_fallback(dirs=[d], system="windows"))
        save_font(d / "y.ttf", "Some Arabic", "Regular", "SomeArabic-Regular", arabic=True)
        fonts.clear_cache()
        self.assertEqual(fonts.arabic_fallback(dirs=[d], system="windows")["ps"], "SomeArabic-Regular")

    def brand(self, families: dict):
        from lib.previews import Brand
        db = self.tmp / "db"
        (db / "branding").mkdir(parents=True)
        (db / "branding/typography.json").write_text(json.dumps({"families": families}), encoding="utf-8")
        return Brand(db)

    def test_client_without_arabic_font_uses_the_system_fallback(self):
        from lib import hb_text
        if not hb_text.AVAILABLE:
            self.skipTest("HarfBuzz/FreeType not in this runtime")
        d = self.system_dir()
        latin = save_font(self.tmp / "client/Brand-Bold.ttf", "Brand", "Bold", "Brand-Bold", weight=700)
        with mock.patch.object(plat, "font_dirs", lambda: [d]):
            b = self.brand({"Brand": {"supports_arabic": False, "weights": [
                {"style": "Bold", "postscript_name": "Brand-Bold", "weight_class": 700, "file": str(latin)}]}})
            f = b.font("headline", 64)
            ar, en = f.for_text("مرحبا بكم"), f.for_text("Hello")
            self.assertEqual((Path(ar.path).name, ar.size), ("tahomabd.ttf", 64.0))
            self.assertEqual(Path(en.path).name, "Brand-Bold.ttf")
            warn = b.font_warnings()
            self.assertEqual(len(warn), 1)
            self.assertIn("client has no Arabic font — using Tahoma Bold", warn[0])
            # the text block draws the Arabic line with the fallback (real pixels, not Pillow's bitmap font)
            from PIL import Image, ImageDraw
            from lib.previews import _text_block
            im = Image.new("RGBA", (600, 200), (0, 0, 0, 0))
            boxes = _text_block(ImageDraw.Draw(im), "مرحبا", f, 300, 100, (255, 255, 255))
            self.assertGreater(boxes[0][3] - boxes[0][1], 40)
            self.assertIsNotNone(im.getbbox())

    def test_client_with_no_font_at_all_never_gets_the_bitmap_font(self):
        from lib import hb_text
        if not hb_text.AVAILABLE:
            self.skipTest("HarfBuzz/FreeType not in this runtime")
        d = self.system_dir()
        with mock.patch.object(plat, "font_dirs", lambda: [d]):
            b = self.brand({})
            f = b.font("body", 50)
            self.assertEqual((Path(f.for_text("نص").path).name, f.for_text("نص").size), ("segoeui.ttf", 50.0))
            self.assertIn("client has no Arabic font — using Segoe UI", b.font_warnings()[0])

    def test_client_with_an_arabic_font_has_no_warning(self):
        from lib import hb_text
        if not hb_text.AVAILABLE:
            self.skipTest("HarfBuzz/FreeType not in this runtime")
        d = self.system_dir()
        own = save_font(self.tmp / "client/Brand-Ar.ttf", "BrandAr", "Bold", "BrandAr-Bold", arabic=True, weight=700)
        with mock.patch.object(plat, "font_dirs", lambda: [d]):
            b = self.brand({"BrandAr": {"weights": [
                {"style": "Bold", "postscript_name": "BrandAr-Bold", "weight_class": 700, "file": str(own)}]}})
            f = b.font("headline", 64)
            self.assertEqual(Path(getattr(f, "for_text", lambda t: f)("مرحبا").path).name, "Brand-Ar.ttf")
            self.assertEqual(b.font_warnings(), [])

    def test_no_arabic_font_anywhere_is_named(self):
        """G72: the client's font is Latin-only and the computer has no Arabic font: the brand font draws, and the
        warning says Arabic text cannot be drawn (not the "using <fallback>" one)."""
        from lib import hb_text
        if not hb_text.AVAILABLE:
            self.skipTest("HarfBuzz/FreeType not in this runtime")
        d = self.tmp / "fonts"
        save_font(d / "latin.ttf", "Latin Only", "Regular", "LatinOnly-Regular")
        latin = save_font(self.tmp / "client/Brand-Bold.ttf", "Brand", "Bold", "Brand-Bold", weight=700)
        with mock.patch.object(plat, "font_dirs", lambda: [d]):
            b = self.brand({"Brand": {"supports_arabic": False, "weights": [
                {"style": "Bold", "postscript_name": "Brand-Bold", "weight_class": 700, "file": str(latin)}]}})
            f = b.font("headline", 64)
            self.assertEqual(Path(f.for_text("Hello").path).name, "Brand-Bold.ttf")
            self.assertEqual(b.font_warnings(), [])                 # nothing Arabic drawn yet
            self.assertEqual(Path(f.for_text("مرحبا").path).name, "Brand-Bold.ttf")
            warn = b.font_warnings()
            self.assertEqual(len(warn), 1)
            self.assertIn("Arabic text cannot be drawn", warn[0])
            self.assertEqual(b.arabic_warnings(), warn)              # what `reel plan` says before drawing

    def test_plan_warning_only_when_there_is_arabic_text(self):
        from lib.previews import arabic_font_warnings
        d = self.system_dir()
        latin = save_font(self.tmp / "client/Brand-Bold.ttf", "Brand", "Bold", "Brand-Bold", weight=700)
        self.brand({"Brand": {"weights": [
            {"style": "Bold", "postscript_name": "Brand-Bold", "weight_class": 700, "file": str(latin)}]}})
        with mock.patch.object(plat, "font_dirs", lambda: [d]):
            self.assertEqual(arabic_font_warnings(self.tmp / "db", ["Hello", None]), [])
            warn = arabic_font_warnings(self.tmp / "db", ["Hello", "نص عربي"])
        self.assertTrue(warn and all(w.startswith("client has no Arabic font — using ") for w in warn), warn)


class TestArabicFromTheCharacterMap(FontDirs):
    """Arabic support is read from the cmap (alef, lam, meem, noon), never from the OS/2 Unicode range bits."""

    def test_arabic_glyphs_without_the_range_bit(self):
        d = self.tmp / "fonts"
        f = save_font(d / "a.ttf", "Sloppy Arabic", "Regular", "SloppyArabic-Regular", arabic=True, os2_arabic=False)
        self.assertTrue(fonts.find("SloppyArabic-Regular", dirs=[d])["arabic"])
        self.assertTrue(fonts.supports_arabic(str(f)))

    def test_range_bit_without_arabic_glyphs(self):
        d = self.tmp / "fonts"
        f = save_font(d / "b.ttf", "Liar Latin", "Regular", "LiarLatin-Regular", arabic=False, os2_arabic=True)
        self.assertFalse(fonts.find("LiarLatin-Regular", dirs=[d])["arabic"])
        self.assertFalse(fonts.supports_arabic(str(f)))

    def test_supports_arabic_reads_the_face_of_a_collection(self):
        ttc = save_collection(self.tmp / "Mixed.ttc", [("Latin", "Regular", "Latin-Regular", False, 400),
                                                       ("Arabic", "Regular", "Arabic-Regular", True, 400)])
        self.assertEqual((fonts.supports_arabic(str(ttc), 0), fonts.supports_arabic(str(ttc), 1)), (False, True))

    def test_previews_ask_with_the_face_index(self):
        from lib.previews import Brand
        ttc = save_collection(self.tmp / "Mixed.ttc", [("Latin", "Regular", "Latin-Regular", False, 400),
                                                       ("Arabic", "Regular", "Arabic-Regular", True, 400)])
        b = Brand(self.tmp / "no-db")
        self.assertFalse(b._has_arabic({"file": str(ttc), "index": 0}))
        self.assertTrue(b._has_arabic({"file": str(ttc), "index": 1}))


class TestFaceIndexIsMeasured(FontDirs):
    """I1: the fallback face at index 1 of a .ttc (GeezaPro-Bold in GeezaPro.ttc) is measured with face 1, not face 0:
    find_font_face / _system_font / the motion plan's fonts / fit() / the animatic all carry the index."""

    def collection(self) -> Path:
        # face 0 narrow (500 units), face 1 wide (900 units): measuring with the wrong face shows in the widths
        return save_collection(self.tmp / "fonts/SegoeUI.ttc",
                               [("Narrow", "Regular", "Narrow-Regular", True, 400, 500),
                                ("Segoe UI", "Regular", "SegoeUI", True, 400, 900)])

    def test_fallback_at_index_1_is_measured_with_face_1(self):
        from lib import hb_text, motion_animatic, motion_layout, motion_plan
        if not hb_text.AVAILABLE:
            self.skipTest("HarfBuzz/FreeType not in this runtime")
        ttc = self.collection()
        with mock.patch.object(plat, "font_dirs", lambda: [ttc.parent]), \
                mock.patch.object(fonts, "_system", lambda system: "windows"):
            self.assertEqual(motion_layout.find_font_face("SegoeUI"), {"file": str(ttc), "index": 1})
            self.assertEqual(motion_layout.find_font_file("SegoeUI"), str(ttc))
            self.assertEqual(motion_plan._system_font(), {"file": str(ttc), "index": 1})
            # the motion plan's fonts when the brand font files are missing: the fallback's file AND face
            brand = mock.Mock()
            brand.face.return_value = {"file": None, "ps": "Brand-Bold", "index": 0}
            comp = mock.Mock(font_override=None, brand=brand, paths=mock.Mock(client_db=self.tmp / "no-db"),
                             warnings=[])
            got = motion_plan._Compiler._fonts(comp)
        self.assertEqual({(v["ps"], v["file"], v["index"]) for v in got.values()}, {("Brand-Bold", str(ttc), 1)})
        # fit() measures with face 1: 3 glyphs x 900 units at 100 px = 270 px (face 0 would give 150 px)
        wide = motion_layout.fit("aaa", got["title"]["file"], 2000, (100, 100), 1, index=got["title"]["index"])
        narrow = motion_layout.fit("aaa", str(ttc), 2000, (100, 100), 1)
        self.assertEqual((wide["widths"], narrow["widths"]), ([270.0], [150.0]))
        # an approved fallback (motion-build --allow-fallback-font) passes the index through font_override
        over = motion_plan._Compiler._fonts(mock.Mock(font_override={"ps": "SegoeUI", "file": str(ttc), "index": 1}))
        self.assertEqual({v["index"] for v in over.values()}, {1})
        old = motion_plan._Compiler._fonts(mock.Mock(font_override={"ps": "SegoeUI", "file": str(ttc)}))
        self.assertEqual({v["index"] for v in old.values()}, {0})
        # the animatic draws the same face; a plan written before the index existed still loads (face 0)
        self.assertEqual(motion_animatic._font(str(ttc), 40, 1).resolved, "SegoeUI")
        self.assertEqual(motion_animatic._font(str(ttc), 40).resolved, "Narrow-Regular")


class TestSandbox(unittest.TestCase):
    def test_discovery_reads_the_sandbox_folder_unless_a_test_injects_folders(self):
        import os
        sandbox = os.environ.get(plat.FONT_DIRS_ENV)
        self.assertTrue(sandbox, "tests/_isolation.py sets WHYNOT_FONT_DIRS")
        self.assertEqual(plat.font_search_dirs(), [Path(sandbox)])
        self.assertNotIn(Path(sandbox), plat.font_dirs())               # font_dirs() still names the real folders
        with mock.patch.object(plat, "font_dirs", lambda: [Path("injected")]):
            self.assertEqual(plat.font_search_dirs(), [Path("injected")])


if __name__ == "__main__":
    unittest.main()
