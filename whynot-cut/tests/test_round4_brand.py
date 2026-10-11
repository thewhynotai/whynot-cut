"""Round 4 brand gaps (field test, Dr Sherin EP02). Run:
    ~/.whynot-cut/venv/bin/python -m unittest discover -s <plugin>/tests -p test_round4_brand.py -v

G62  a graphic's font weight comes from typography.json `roles`, then brand.json font_roles_fallback.weights, then the
     NEAREST available weight - never "the first font file".
"""
import sys as _sys
_sys.dont_write_bytecode = True  # keep the plugin folder free of __pycache__
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SK = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SK / "engine" / "reel"))
sys.path.insert(0, str(SK / "tests"))

from lib import common  # noqa: E402
from lib.common import CLIENT_PROFILE_REL, read_json, write_json  # noqa: E402
from test_motion import good_script, motion_plan_fixture, test_font  # noqa: E402
from test_podcast import ff  # noqa: E402


def brand_db(root: Path, weights: dict, roles: dict | None = None, primary: str | None = None, same_file: bool = False):
    """output/client_database with one family. `weights` maps style -> PostScript name. Every style gets its OWN copy of
    the test font (named after the style) so the file a graphic used says which weight it got."""
    font = test_font()
    db = root / "output/client_database"
    fdir = root / "fonts"
    fdir.mkdir(parents=True, exist_ok=True)
    rows = []
    for style, ps in weights.items():
        f = fdir / (font.name if same_file else f"Brand-{style.replace(' ', '')}.ttf")
        if not f.exists():
            shutil.copy(font, f)
        rows.append({"style": style, "file": str(f), "postscript_name": ps, "installed": True})
    typ = {"families": {"Brand": {"weights": rows}}}
    if roles is not None:
        typ["roles"] = roles
    write_json(db / "branding/typography.json", typ)
    if primary:
        write_json(db / "branding/brand-tokens.json", {"roles": {"primary": {"hex": primary}}})
    return db


def picked(brand, role: str) -> str:
    """File name (stem) of the font file the role resolves to."""
    return Path(brand.face(role)["file"]).stem


class RoleFontCase(unittest.TestCase):
    def setUp(self):
        if test_font() is None:
            self.skipTest("no test font")
        self.tmp = Path(tempfile.mkdtemp())
        self.root = self.tmp / "CLIENT"
        self.root.mkdir()
        common.set_context(self.root)
        self.addCleanup(common.set_context, None)
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

    def profile(self, name: str, data: dict):
        write_json(self.root / CLIENT_PROFILE_REL / name, data)


class TestRoleStyles(RoleFontCase):
    """G62: the weight a role gets."""

    def test_typography_roles_by_postscript_name(self):
        from lib.previews import Brand
        # what the researcher writes (typography-roles.json -> typography.json): headline = the Bold face
        db = brand_db(self.root, {"Light": "Brand-Light", "Medium": "Brand-Medium", "Bold": "Brand-Bold",
                                  "Black": "Brand-Black"},
                      roles={"headline": {"postscript_name": "Brand-Bold"}, "small": {"postscript_name": "Brand-Medium"}})
        b = Brand(db)
        self.assertEqual(picked(b, "headline"), "Brand-Bold")            # not the hard-coded Black
        self.assertEqual(picked(b, "small"), "Brand-Medium")             # not the hard-coded Regular
        self.assertEqual(picked(b, "body"), "Brand-Medium")              # roles left out keep the house default

    def test_typography_roles_by_style(self):
        from lib.previews import Brand
        for key in ("style", "weight"):
            db = brand_db(self.root, {"Medium": "Brand-Medium", "Bold": "Brand-Bold", "Black": "Brand-Black"},
                          roles={"headline": {key: "Bold"}, "caption": "Medium"})
            b = Brand(db)
            self.assertEqual(picked(b, "headline"), "Brand-Bold", key)
            self.assertEqual(picked(b, "caption"), "Brand-Medium", key)         # a bare string is a style too

    def test_role_style_reflects_the_roles(self):
        from lib.previews import Brand
        db = brand_db(self.root, {"Medium": "Brand-Medium", "Bold": "Brand-Bold", "Black": "Brand-Black"},
                      roles={"headline": {"postscript_name": "Brand-Bold"}})
        self.assertEqual(Brand(db).role_style["headline"], "bold")

    def test_brand_json_when_roles_are_silent(self):
        from lib.previews import Brand
        self.profile("brand.json", {"font_roles_fallback": {"weights": {"headline": "bold", "small": "medium"}}})
        db = brand_db(self.root, {"Light": "Brand-Light", "Medium": "Brand-Medium", "Bold": "Brand-Bold",
                                  "Black": "Brand-Black", "Regular": "Brand-Regular"}, roles={})
        b = Brand(db)
        self.assertEqual(picked(b, "headline"), "Brand-Bold")
        self.assertEqual(picked(b, "small"), "Brand-Medium")

    def test_typography_roles_beat_brand_json(self):
        from lib.previews import Brand
        self.profile("brand.json", {"font_roles_fallback": {"weights": {"headline": "medium", "term": "light"}}})
        db = brand_db(self.root, {"Light": "Brand-Light", "Medium": "Brand-Medium", "Bold": "Brand-Bold",
                                  "Black": "Brand-Black"}, roles={"headline": {"postscript_name": "Brand-Bold"}})
        b = Brand(db)
        self.assertEqual(picked(b, "headline"), "Brand-Bold")            # roles win
        self.assertEqual(picked(b, "term"), "Brand-Light")               # brand.json fills the role typography skipped

    def test_nearest_weight_never_the_first_file(self):
        from lib.previews import Brand
        # no Black, no Regular; the FIRST file in the family is the lightest (the field test's Medium was first)
        db = brand_db(self.root, {"Light": "Brand-Light", "Medium": "Brand-Medium", "Bold": "Brand-Bold"})
        b = Brand(db)
        self.assertEqual(picked(b, "headline"), "Brand-Bold")            # black -> extrabold -> bold
        self.assertEqual(picked(b, "caption"), "Brand-Bold")
        self.assertEqual(picked(b, "term"), "Brand-Bold")
        self.assertEqual(picked(b, "small"), "Brand-Medium")             # regular -> book -> medium -> light
        self.assertEqual(picked(b, "body"), "Brand-Medium")

    def test_nearest_to_a_weight_the_family_lacks(self):
        from lib.previews import Brand
        db = brand_db(self.root, {"Regular": "Brand-Regular", "Medium": "Brand-Medium", "Bold": "Brand-Bold"},
                      roles={"headline": {"style": "Black"}, "small": {"style": "SemiBold"}})
        b = Brand(db)
        self.assertEqual(picked(b, "headline"), "Brand-Bold")            # Black asked, Bold is the nearest
        self.assertEqual(picked(b, "small"), "Brand-Medium")             # SemiBold asked: Medium / Bold tie, lists say medium

    def test_style_spellings(self):
        from lib.previews import Brand
        db = brand_db(self.root, {"Light": "B-Light", "Semi Bold": "B-SemiBold", "Extra Bold": "B-ExtraBold",
                                  "Regular": "B-Regular"})
        b = Brand(db)
        self.assertEqual(picked(b, "headline"), "Brand-ExtraBold")       # black -> "Extra Bold" (spaced spelling)
        self.assertEqual(picked(b, "caption"), "Brand-SemiBold")         # bold -> Semi Bold / Extra Bold tie: the list says semibold
        self.assertEqual(picked(b, "small"), "Brand-Regular")
        self.assertEqual(b.face("headline")["ps"], "B-ExtraBold")

    def test_empty_database_still_works(self):
        from lib.previews import Brand
        b = Brand(self.root / "output/client_database")                  # no typography.json at all
        self.assertIsNone(b.face("headline")["file"])
        self.assertIsNotNone(b.font("headline", 40))                     # Pillow default, no crash


class TestRoleFontFiles(RoleFontCase):
    """G62: every renderer asks the same resolver (preview stills, caption stills, motion plan, After Effects names)."""

    def hb_paths(self, fn):
        from lib import hb_text
        if not hb_text.AVAILABLE:
            self.skipTest("uharfbuzz/freetype not installed")
        with mock.patch.object(hb_text, "HBFontSpec", wraps=hb_text.HBFontSpec) as spy:
            fn()
        return [Path(c.args[0]).stem for c in spy.call_args_list]

    def test_font_uses_the_resolved_file(self):
        from lib import ct_text
        from lib.previews import Brand
        if ct_text.AVAILABLE:
            self.skipTest("CoreText draws installed fonts by PostScript name")
        db = brand_db(self.root, {"Medium": "Brand-Medium", "Bold": "Brand-Bold", "Black": "Brand-Black"},
                      roles={"headline": {"postscript_name": "Brand-Bold"}})
        b = Brand(db)
        self.assertEqual(self.hb_paths(lambda: b.font("headline", 60))[0], "Brand-Bold")

    def test_preview_stills_follow_the_roles(self):
        from lib import ct_text, previews
        if ct_text.AVAILABLE:
            self.skipTest("CoreText draws installed fonts by PostScript name")
        db = brand_db(self.root, {"Medium": "Brand-Medium", "Bold": "Brand-Bold"})        # no Black, no Regular
        b = previews.Brand(db)
        out = self.tmp / "hook.png"
        paths = self.hb_paths(lambda: previews.render_event(
            {"template": "hook_title", "params": {"text": "Big win"}}, {"size": 86, "y": 1080}, b, {}, None, out))
        self.assertTrue(paths)
        self.assertEqual(set(paths), {"Brand-Bold"})                      # hook title = headline = nearest to Black
        out2 = self.tmp / "card.png"
        paths = self.hb_paths(lambda: previews.render_event(
            {"template": "name_card", "params": {"name": "Dr Sara", "lines": ["Dermatology"]}},
            {"y": 700, "w": 800, "name_size": 60, "line_size": 36}, b, {}, None, out2))
        self.assertEqual(set(paths), {"Brand-Bold", "Brand-Medium"})      # headline name + small lines (regular -> medium)

    def test_motion_plan_follows_the_roles(self):
        tmp = Path(tempfile.mkdtemp())
        try:
            root, ep, reel = motion_plan_fixture(tmp)
            f = str(test_font())
            write_json(reel.client_db / "branding/typography.json", {"families": {"Brand": {"weights": [
                {"style": "Medium", "file": f, "postscript_name": "Brand-Medium"},
                {"style": "Bold", "file": f, "postscript_name": "Brand-Bold"},
                {"style": "Black", "file": f, "postscript_name": "Brand-Black"}]}},
                "roles": {"headline": {"postscript_name": "Brand-Bold"}}})
            from lib.motion_plan import compile_motion
            write_json(reel.p("01_analysis/motion-script.json"), good_script())
            r = compile_motion(reel)
            self.assertTrue(r["ok"], r["errors"])
            plan = read_json(reel.p("01_analysis/motion-plan.json"))
            self.assertEqual(plan["fonts"]["title"]["ps"], "Brand-Bold")       # roles say Bold: not the default Black
            self.assertEqual(plan["fonts"]["quote"]["ps"], "Brand-Bold")
        finally:
            common.set_context(None)
            shutil.rmtree(tmp, ignore_errors=True)

    def test_after_effects_font_names_follow_the_roles(self):
        from lib.ae_builder import fonts_map
        # roles give the style only (no PostScript name): After Effects must still get a real font name
        db = brand_db(self.root, {"Light": "Brand-Light", "Medium": "Brand-Medium", "Bold": "Brand-Bold"},
                      roles={"headline": {"style": "Bold"}})
        fm = fonts_map(db)
        self.assertEqual(fm["headline"], "Brand-Bold")
        self.assertEqual(fm["small"], "Brand-Medium")                      # nearest to Regular, never the first (Light)
        self.assertEqual(fm["caption"], "Brand-Bold")
        # an explicit PostScript name in the roles still wins, as before
        db = brand_db(self.root, {"Medium": "Brand-Medium", "Bold": "Brand-Bold"},
                      roles={"headline": {"postscript_name": "Brand-Medium"}})
        self.assertEqual(fonts_map(db)["headline"], "Brand-Medium")


# --------------------------------------------------------------------------- thumbnails
class TestThumbnailFont(unittest.TestCase):
    """G62: publish-thumbnail draws the headline in the role's weight."""

    @classmethod
    def setUpClass(cls):
        from lib.episode import EpisodePaths, prep
        cls.tmp = Path(tempfile.mkdtemp())
        root = cls.root = cls.tmp / "TC"
        for d in ("assets/Brand", "data/Episodes"):
            (root / d).mkdir(parents=True)
        # 20 s: a warm brown set for 10 s, then a near-black one
        ff("-f", "lavfi", "-i", "color=c=0x8F6B45:s=640x360:r=5:d=10", "-f", "lavfi", "-i", "color=c=0x0A0A0A:s=640x360:r=5:d=10",
           "-f", "lavfi", "-i", "sine=f=300:r=48000:d=20", "-filter_complex", "[0:v][1:v]concat=n=2:v=1:a=0[v]",
           "-map", "[v]", "-map", "2:a", "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", "-c:a", "aac",
           "-shortest", str(root / "data/Episodes/EP9.mp4"))
        common.set_context(root)
        cls.ep = EpisodePaths(root, "EP9")
        prep(cls.ep)

    @classmethod
    def tearDownClass(cls):
        common.set_context(None)
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def setUp(self):
        if test_font() is None:
            self.skipTest("no test font")
        for rel in ("branding/brand-tokens.json", "branding/typography.json"):
            self.addCleanup((self.ep.client_db / rel).unlink, missing_ok=True)

    def test_headline_font_follows_the_roles(self):
        from lib import ct_text, hb_text
        if ct_text.AVAILABLE or not hb_text.AVAILABLE or test_font() is None:
            self.skipTest("needs HarfBuzz and a test font (no CoreText)")
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        db = brand_db(tmp, {"Medium": "Brand-Medium", "Bold": "Brand-Bold", "Black": "Brand-Black"},
                      roles={"headline": {"postscript_name": "Brand-Bold"}})
        write_json(self.ep.client_db / "branding/typography.json", read_json(db / "branding/typography.json"))
        from lib.publish import render_thumbnails
        write_json(self.ep.p("publish/publish.json"), {"thumbnail": {"designs": [{"frame_ms": 15000, "text": "Big win"}]}})
        with mock.patch.object(hb_text, "HBFontSpec", wraps=hb_text.HBFontSpec) as spy:
            r = render_thumbnails(self.ep)
        self.assertTrue(r["ok"], r)
        self.assertEqual({Path(c.args[0]).stem for c in spy.call_args_list}, {"Brand-Bold"})


if __name__ == "__main__":
    unittest.main()
