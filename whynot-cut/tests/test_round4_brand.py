"""Round 4 brand gaps (field test round 4, a podcast episode; fictional example-clinic here). Run:
    ~/.whynot-cut/venv/bin/python -m unittest discover -s <plugin>/tests -p test_round4_brand.py -v

G62  a graphic's font weight comes from typography.json `roles`, then brand.json font_roles_fallback.weights, then the
     NEAREST available weight - never "the first font file".
G68  a highlight colour drawn over a frame (publish-thumbnail, preview stills) is measured against the pixels behind it
     and falls back to white/paper, with a warning, when it is unreadable (brand primary was a brown on a warm set).
"""
import sys as _sys
_sys.dont_write_bytecode = True  # keep the plugin folder free of __pycache__
import _isolation  # noqa: F401,E402  G79: sandbox the engine home first (tests/_isolation.py)
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

BROWN = "#7F6040"                       # a brown primary like the one measured in field test round 4
BROWN_RGB = tuple(int(BROWN[i:i + 2], 16) for i in (1, 3, 5))


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


# --------------------------------------------------------------------------- G68
class TestLegibility(unittest.TestCase):
    """G68: the contrast check itself (WCAG relative luminance; thresholds are the engine's motion.json constants)."""
    WHITE, PAPER = ("white", (255, 255, 255)), ("paper", (244, 241, 234))

    def test_brown_on_a_warm_region_falls_back_to_white(self):
        from lib.legibility import legible
        r = legible(BROWN_RGB, [(143, 107, 69)], 104, [self.PAPER, self.WHITE])
        self.assertTrue(r["fallback"])
        self.assertEqual(r["rgb"], (255, 255, 255))                      # the better of white / paper
        self.assertLess(r["original_ratio"], 1.6)                        # the field test measured 1.1-1.5
        self.assertGreaterEqual(r["ratio"], r["need"])

    def test_good_contrast_keeps_the_brand_colour(self):
        from lib.legibility import legible
        r = legible((32, 172, 175), [(10, 10, 10)], 104, [self.WHITE, self.PAPER])
        self.assertFalse(r["fallback"])
        self.assertEqual(r["rgb"], (32, 172, 175))
        self.assertEqual(r["ratio"], r["original_ratio"])

    def test_threshold_depends_on_text_size(self):
        from lib.legibility import legible, needed
        self.assertEqual(needed(104), 3.0)                               # large text
        self.assertEqual(needed(40), 4.5)
        grey = (99, 99, 99)                                              # ~3.5:1 on black
        self.assertFalse(legible(grey, [(0, 0, 0)], 104, [self.WHITE])["fallback"])
        self.assertTrue(legible(grey, [(0, 0, 0)], 40, [self.WHITE])["fallback"])

    def test_the_worst_region_decides(self):
        from lib.legibility import legible
        r = legible((32, 172, 175), [(10, 10, 10), (32, 172, 175)], 104, [self.WHITE])
        self.assertTrue(r["fallback"])                                   # one word sits on a teal patch

    def test_no_better_fallback_keeps_the_colour(self):
        from lib.legibility import legible
        r = legible((200, 200, 200), [(255, 255, 255)], 104, [self.WHITE, self.PAPER])
        self.assertFalse(r["fallback"])                                  # nothing is more readable than what we have
        self.assertLess(r["ratio"], r["need"])                           # ... but the caller still sees it is too low

    def test_region_mean(self):
        from PIL import Image
        from lib.legibility import region_mean
        im = Image.new("RGBA", (100, 100), (0, 0, 0, 255))
        im.paste((200, 100, 50, 255), (0, 0, 50, 100))
        self.assertEqual(region_mean(im, (0, 0, 50, 100)), (200, 100, 50))
        self.assertEqual(region_mean(im, (0, 0, 100, 100)), (100, 50, 25))
        self.assertEqual(region_mean(im, (80, 80, 400, 400)), (0, 0, 0))   # clamped to the image


class TestPreviewHighlightContrast(RoleFontCase):
    """G68: preview stills. A colour that reaches the footage directly (text without a box) is checked against the frame
    behind it; the default white text and the boxed texts are never touched."""
    WARM, DARK = (*BROWN_RGB, 255), (10, 10, 10, 255)

    def render(self, probe_colour, text_role="primary", notes=None, probe_callable=False, layer="fg", size=86):
        from PIL import Image
        from lib import previews
        db = brand_db(self.root, {"Regular": "Brand-Regular", "Bold": "Brand-Bold"}, primary=BROWN)
        b = previews.Brand(db)
        out = self.tmp / "hook.png"
        img = Image.new("RGBA", common.frame_size(), probe_colour) if probe_colour else None
        probe = (lambda: img) if (probe_callable and img is not None) else img
        t = {"size": size, "y": 1080, "bar_style": "underline", "text_role": text_role}
        previews.render_event({"template": "hook_title", "event_id": "GFX_001", "params": {"text": "Big win today"}},
                              t, b, {}, None, out, layer=layer, probe=probe, notes=notes)
        return out

    @staticmethod
    def glyphs(png: Path, rgb: tuple) -> int:
        from PIL import Image
        with Image.open(png) as im:
            return sum(1 for p in im.convert("RGBA").getdata()
                       if p[3] >= 250 and all(abs(p[i] - rgb[i]) <= 12 for i in range(3)))

    def test_brown_text_on_a_warm_frame_turns_white_with_a_warning(self):
        notes = []
        png = self.render(self.WARM, notes=notes)
        self.assertGreater(self.glyphs(png, (255, 255, 255)), 300)
        self.assertEqual(self.glyphs(png, BROWN_RGB), 0)
        self.assertEqual(len(notes), 1, notes)
        self.assertIn("GFX_001", notes[0])
        self.assertIn("contrast", notes[0])

    def test_brown_text_on_a_dark_frame_is_kept(self):
        notes = []
        png = self.render(self.DARK, notes=notes)
        self.assertGreater(self.glyphs(png, BROWN_RGB), 300)
        self.assertEqual(notes, [])

    def test_lazy_probe_is_used_too(self):
        notes = []
        png = self.render(self.WARM, notes=notes, probe_callable=True)
        self.assertEqual(self.glyphs(png, BROWN_RGB), 0)
        self.assertEqual(len(notes), 1)

    def test_nothing_changes_without_a_frame_or_with_the_default_white(self):
        png = self.render(None)                                          # production still: no frame, colour as configured
        self.assertGreater(self.glyphs(png, BROWN_RGB), 300)
        notes = []
        png = self.render(self.WARM, text_role="neutral_light", notes=notes)    # the default style: white text
        self.assertGreater(self.glyphs(png, (255, 255, 255)), 300)
        self.assertEqual(notes, [])

    def test_boxed_text_is_not_measured_against_the_frame(self):
        from PIL import Image
        from lib import previews
        db = brand_db(self.root, {"Regular": "Brand-Regular", "Bold": "Brand-Bold"}, primary=BROWN)
        b = previews.Brand(db)
        notes = []
        # statement text sits on its own box: what is behind it is the box, not the frame
        previews.render_event({"template": "statement_highlight", "event_id": "GFX_002", "params": {"text": "Big win"}},
                              {"size": 70, "y": 900, "box_role": "ink", "text_role": "primary"}, b, {}, None,
                              self.tmp / "st.png", layer="fg", probe=Image.new("RGBA", common.frame_size(), self.WARM),
                              notes=notes)
        self.assertEqual(notes, [])

    def test_render_all_reports_the_warning(self):
        import subprocess
        from lib.previews import render_all
        root = self.root
        (root / "assets").mkdir()
        (root / "data").mkdir()
        p = common.Paths(root, "V1")
        p.ensure_project()
        brand_db(root, {"Regular": "Brand-Regular", "Bold": "Brand-Bold"}, primary=BROWN)
        self.profile("graphics-templates.json", {"templates": {"hook_title": {"text_role": "primary"}}})
        clip = root / "data/Raw/warm.mp4"
        clip.parent.mkdir(parents=True)
        subprocess.run([common.ffmpeg_exe(), "-y", "-loglevel", "error", "-f", "lavfi", "-i",
                        "color=c=0x7F6040:s=360x640:r=25:d=4", "-pix_fmt", "yuv420p", str(clip)], check=True)
        write_json(p.p("01_analysis/timeline-spec.json"), {"main_footage": str(clip), "events": [
            {"event_id": "GFX_001", "template": "hook_title", "start_ms": 500, "end_ms": 2500,
             "params": {"text": "Big win today"}}]})
        for composite in (False, True):
            r = render_all(p, composite_preview=composite)
            self.assertTrue(any("GFX_001" in w and "contrast" in w for w in r["warnings"]), (composite, r.get("warnings")))
            png = p.p("03_broll/typography/GFX_001_fg.png")
            self.assertGreater(self.glyphs(png, (255, 255, 255)), 300)
            self.assertEqual(self.glyphs(png, BROWN_RGB), 0)


class TestThumbnailHighlightContrast(unittest.TestCase):
    """G68: publish-thumbnail draws the design's highlight word in the brand colour over the frame."""

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

    def render(self, frame_ms: int, primary: str, text="Big loss today", highlight="loss"):
        from lib import previews
        from lib.publish import render_thumbnails
        brand_db(self.root, {"Black": "Brand-Black"}, primary=primary)      # the episode's client_database
        write_json(self.ep.p("publish/publish.json"), {"thumbnail": {"designs": [
            {"frame_ms": frame_ms, "text": text, "highlight": highlight}]}})
        fills = []
        real = previews._text_block

        def spy(d, t, font, cx, cy, fill, *a, **kw):
            fills.append(tuple(fill)[:3])
            return real(d, t, font, cx, cy, fill, *a, **kw)
        with mock.patch.object(previews, "_text_block", spy):
            r = render_thumbnails(self.ep)
        self.assertTrue(r["ok"], r)
        return r, fills

    def test_brown_highlight_on_the_warm_set_falls_back(self):
        r, fills = self.render(5000, BROWN)
        brown = BROWN_RGB
        self.assertNotIn(brown, fills)                                   # the word is never drawn in brown
        ws = [w for w in r["warnings"] if "highlight" in w and "contrast" in w]
        self.assertEqual(len(ws), 1, r["warnings"])
        self.assertIn("design 1", ws[0])
        self.assertIn("#7F6040", ws[0])                                  # which colour failed ...
        self.assertRegex(ws[0], r"\d\.\d:1")                             # ... by how much
        h = r["highlights"][0]
        self.assertTrue(h["fallback"])
        self.assertIn(h["color"], ("#FFFFFF", "#E6EEF8", "#F4F1EA"))     # white or the brand's light colour
        self.assertGreaterEqual(h["contrast"], 3.0)
        self.assertLess(h["brand_contrast"], 3.0)

    def test_readable_highlight_keeps_the_brand_colour(self):
        r, fills = self.render(15000, "#20ACAF")
        self.assertIn((32, 172, 175), fills)                             # the dark set: teal reads fine
        self.assertFalse([w for w in r["warnings"] if "contrast" in w], r["warnings"])
        h = r["highlights"][0]
        self.assertFalse(h["fallback"])
        self.assertEqual(h["color"], "#20ACAF")

    def test_plain_design_has_nothing_to_check(self):
        r, _ = self.render(5000, BROWN, highlight="")
        self.assertEqual(r.get("highlights", []), [])
        self.assertFalse([w for w in r["warnings"] if "contrast" in w])

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
