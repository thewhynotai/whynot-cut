# SPDX-License-Identifier: GPL-3.0-or-later
# © 2026 The Why Not AI (thewhynot.ai)
"""Addendum M M2-T4 (Task 56, Gate 4 part): the font-pairing module and the curated OFL table draft.
  * traits are MEASURED from the font file (fontTools outlines + a FreeType raster probe), never read from names: Latin
    x-height (ink of "x", else OS/2 sxHeight), the Arabic letter body (median tooth height of «س ب ن ي», dots dropped),
    stroke contrast, ink density, width and word-space rhythm, terminal shape; at the ROLE's weight (nearest static
    file, ties to the heavier; a variable font is instanced at that weight);
  * a coverage gate on fixed test strings (Arabic letters with ڤ, the lam-alef ligature, ٪ ، ؛ ؟, Arabic-Indic digits;
    Latin A-Z a-z 0-9 % & ®): a face missing any of them never enters a pair, the misses are named;
  * the 0-100 score = class 40 + weight 20 + height 15 + contrast 15 + width/rhythm 10; >= 70 automatic, 50-69
    shown with the reason from explain(), < 50 never picked; the client's pair always wins (score shown);
  * latin_scale aligns the scaled Latin x-height with the Arabic body within 3 % of the target ratio (1.00);
  * config/defaults/font-pairings.json: OFL licence proof per face (nameID 13/14, OFL.txt sha256, file sha256), rows
    re-measured by the module byte for byte, unmeasured candidates never picked.
Every test font is made here with fontTools (known glyph boxes); the committed OFL fonts in guide-ar/fonts are used for
the real-font checks and the table. Run: bash tools/test.sh -p test_font_pairing.py
"""
import sys as _sys
_sys.dont_write_bytecode = True  # keep the plugin folder free of __pycache__
import _isolation  # noqa: F401,E402  G79: sandbox the engine home first (tests/_isolation.py)
import json
import math
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys = _sys
SK = Path(__file__).resolve().parents[1]
REPO = SK.parent
sys.path.insert(0, str(SK / "engine" / "reel"))

from lib import font_pairing as FP  # noqa: E402

FONTS = REPO / "guide-ar" / "fonts"           # OFL fonts kept in the repo
TABLE = SK / "config" / "defaults" / "font-pairings.json"
OFL_TEXT = ("Copyright (c) test\n\nThis Font Software is licensed under the SIL Open Font License, Version 1.1.\n"
            "SIL OPEN FONT LICENSE Version 1.1 - 26 February 2007\n")
LATIN = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789%&®"
ARABIC = "ابتثجحخدذرزسشصضطظعغفقكلمنهويءآأؤإئةىڤ٪،؛؟٠١٢٣٤٥٦٧٨٩"


# --------------------------------------------------------------------------- tiny fonts with known boxes
def _rect(pen, x0, y0, x1, y1, ccw=False):
    pts = [(x0, y0), (x0, y1), (x1, y1), (x1, y0)]          # clockwise: a TrueType outer contour
    if ccw:
        pts.reverse()
    pen.moveTo(pts[0])
    for p in pts[1:]:
        pen.lineTo(p)
    pen.closePath()


def _name(ch: str) -> str:
    return f"u{ord(ch):04X}"


def make_font(*, family="Test", style="Regular", ps=None, weight=400, upm=1000, adv=600, space=250, xh=500,
              with_x=True, sx_height=0, cap=700, ink=80, stem=80, hair=80, latin=True, arabic=True, body=500,
              ar_stem=80, ar_bar=80, lam_alef=True, drop=(), extra_glyphs=0, ofl=True, split_beh=False):
    """A TrueType font made of rectangles. Latin lowercase: a stem `ink` wide and a base bar `ink` high, `xh` tall
    ("x" too unless `with_x` is False); "o" is a ring with sides `stem` and top/bottom `hair`. Arabic letters: a base
    bar `ar_bar` high and a tooth `ar_stem` wide, `body` tall; ب/ي carry dots below, ن a dot above (separate contours);
    alef is a stem `ar_stem` wide, 1.5 x body tall. `lam_alef` adds the rlig lam-alef ligature. `drop`: characters left
    out of the cmap. `extra_glyphs` unmapped glyphs make a large font. `split_beh`: ccmp draws ب as a dotless base
    glyph plus a separate dot glyph (as some Naskh fonts do)."""
    from fontTools.fontBuilder import FontBuilder
    from fontTools.pens.ttGlyphPen import TTGlyphPen
    ps = ps or f"{family}-{style}".replace(" ", "")
    chars = []
    if latin:
        chars += [c for c in LATIN if c not in drop]
    if arabic:
        chars += [c for c in ARABIC if c not in drop]
        for c in "لا":
            if c not in chars and c not in drop:
                chars.append(c)
    chars = list(dict.fromkeys(chars))
    glyphs = {}

    def draw(fn):
        pen = TTGlyphPen(None)
        fn(pen)
        return pen.glyph()

    def latin_generic(top):
        return lambda pen: (_rect(pen, 50, 0, 50 + ink, top), _rect(pen, 50 + ink, 0, adv - 50, ink))

    def arabic_generic(extra=None):
        def fn(pen):
            _rect(pen, 50, 0, adv - 50 - ar_stem, ar_bar)
            _rect(pen, adv - 50 - ar_stem, 0, adv - 50, body)
            if extra:
                extra(pen)
        return fn

    for c in chars:
        n = _name(c)
        if c == "o":
            def ring(pen):
                _rect(pen, 50, 0, adv - 50, xh)
                _rect(pen, 50 + stem, hair, adv - 50 - stem, xh - hair, ccw=True)
            glyphs[n] = draw(ring)
        elif c == "x" and not with_x:
            continue
        elif c in LATIN:
            glyphs[n] = draw(latin_generic(cap if (c.isupper() or c.isdigit() or c in "%&®") else xh))
        elif c == "ا":
            glyphs[n] = draw(lambda pen: _rect(pen, adv // 2 - ar_stem // 2, 0, adv // 2 - ar_stem // 2 + ar_stem,
                                               int(body * 1.5)))
        elif c in "بي":
            glyphs[n] = draw(arabic_generic(lambda pen: _rect(pen, adv // 2 - 30, -160, adv // 2 + 30, -100)))
        elif c == "ن":
            glyphs[n] = draw(arabic_generic(lambda pen: _rect(pen, adv // 2 - 30, body + 60, adv // 2 + 30,
                                                              body + 120)))
        else:
            glyphs[n] = draw(arabic_generic())
    cmap = {ord(c): _name(c) for c in chars if _name(c) in glyphs}
    fea = ""
    if arabic and lam_alef == "context" and "ل" in chars and "ا" in chars:
        # lam-alef from two contextual glyphs (as some Naskh fonts build it): lam before alef, alef after that lam
        glyphs["lam_ctx"], glyphs["alef_ctx"] = draw(arabic_generic()), draw(arabic_generic())
        lam, alef = _name("ل"), _name("ا")
        fea = (f"languagesystem arab dflt;\nfeature rlig {{ sub {lam}' {alef} by lam_ctx; "
               f"sub lam_ctx {alef}' by alef_ctx; }} rlig;\n")
    elif arabic and lam_alef and "ل" in chars and "ا" in chars:
        glyphs["lam_alef"] = draw(arabic_generic())
        fea = f"languagesystem arab dflt;\nfeature rlig {{ sub {_name('ل')} {_name('ا')} by lam_alef; }} rlig;\n"
    if arabic and split_beh and "ب" in chars:
        glyphs["behbase"] = draw(arabic_generic())
        glyphs["dotb"] = draw(lambda pen: _rect(pen, -330, -160, -270, -100))
        fea = (fea or "languagesystem arab dflt;\n") + f"feature ccmp {{ sub {_name('ب')} by behbase dotb; }} ccmp;\n"
    for i in range(extra_glyphs):
        glyphs[f"extra{i}"] = draw(lambda pen: _rect(pen, 0, 0, 10, 10))
    glyphs["space"] = TTGlyphPen(None).glyph()
    cmap[0x20] = "space"
    order = [".notdef", "space"] + [g for g in glyphs if g != "space"]
    glyphs[".notdef"] = draw(lambda pen: _rect(pen, 50, 0, 450, 700))
    fb = FontBuilder(upm, isTTF=True)
    fb.setupGlyphOrder(order)
    fb.setupCharacterMap(cmap)
    fb.setupGlyf({g: glyphs[g] for g in order})
    fb.setupHorizontalMetrics({g: ((space if g == "space" else 0 if g == "dotb" else adv), 50) for g in order})
    fb.setupHorizontalHeader(ascent=900, descent=-300)
    names = {"familyName": family, "styleName": style, "psName": ps, "fullName": f"{family} {style}",
             "uniqueFontIdentifier": ps}
    if ofl:
        names.update({"licenseDescription": "This Font Software is licensed under the SIL Open Font License, "
                                            "Version 1.1.",
                      "licenseInfoURL": "https://openfontlicense.org"})
    else:
        names.update({"licenseDescription": "All rights reserved. Commercial licence.",
                      "licenseInfoURL": "https://example.com/eula"})
    fb.setupNameTable(names)
    fb.setupOS2(version=4, usWeightClass=weight, sxHeight=sx_height, sCapHeight=cap, sTypoAscender=900,
                sTypoDescender=-300, usWinAscent=900, usWinDescent=300)
    fb.setupPost()
    if fea:
        fb.addOpenTypeFeatures(fea)
    return fb.font


def save(path: Path, ofl_txt: bool = True, **kw) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    make_font(**kw).save(str(path))
    if ofl_txt:
        (path.parent / "OFL.txt").write_bytes(OFL_TEXT.encode("utf-8"))
    return path


def save_variable(path: Path, light: dict, heavy: dict) -> Path:
    """A variable font with a wght axis 400..900 from two masters made by make_font (same glyphs, other thickness)."""
    from fontTools import varLib
    from fontTools.designspaceLib import AxisDescriptor, DesignSpaceDocument, SourceDescriptor
    ds = DesignSpaceDocument()
    ax = AxisDescriptor()
    ax.tag, ax.name, ax.minimum, ax.default, ax.maximum = "wght", "Weight", 400, 400, 900
    ds.addAxis(ax)
    for loc, kw in ((400, light), (900, heavy)):
        src = SourceDescriptor()
        src.font = make_font(**kw)
        src.location = {"Weight": loc}
        src.name = f"m{loc}"
        ds.addSource(src)
    vf = varLib.build(ds)[0]
    path.parent.mkdir(parents=True, exist_ok=True)
    vf.save(str(path))
    (path.parent / "OFL.txt").write_bytes(OFL_TEXT.encode("utf-8"))
    return path


class Tmp(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="t56_"))
        FP.clear_cache()

    def tearDown(self):
        FP.clear_cache()
        shutil.rmtree(self.tmp, ignore_errors=False)


def traits(**kw):
    """Plain trait dicts for score() tests: the same keys the module measures."""
    base = {"x_height": 0.5, "arabic_body": 0.5, "density_latin": 0.3, "density_arabic": 0.3, "contrast_latin": 0.1,
            "contrast_arabic": 0.1, "width_latin": 1.2, "width_arabic": 1.2, "space_latin": 0.5, "space_arabic": 0.5,
            "angularity_latin": 0.5, "angularity_arabic": 0.5}
    base.update(kw)
    return base


# --------------------------------------------------------------------------- A. traits
class TestTraits(Tmp):
    def test_x_height_is_the_ink_of_x_then_os2_then_null(self):
        t = FP.traits(save(self.tmp / "a" / "a.ttf", xh=500, sx_height=420))
        self.assertAlmostEqual(t["x_height"], 0.5, places=3)
        self.assertEqual(t["x_height_source"], "ink")
        t = FP.traits(save(self.tmp / "b" / "b.ttf", with_x=False, sx_height=420))
        self.assertAlmostEqual(t["x_height"], 0.42, places=3)
        self.assertEqual(t["x_height_source"], "os2")
        t = FP.traits(save(self.tmp / "c" / "c.ttf", with_x=False, sx_height=0))
        self.assertIsNone(t["x_height"])
        self.assertTrue(any("x-height" in r for r in t["reasons"]))
        s = FP.score(t, t)                                       # never a crash: the height part is 0 with a reason
        self.assertEqual(s["parts"]["height"], 0)
        self.assertTrue(any("height" in r for r in s["reasons"]))

    def test_x_height_is_per_upm(self):
        t = FP.traits(save(self.tmp / "u" / "u.ttf", upm=2048, xh=1024))
        self.assertAlmostEqual(t["x_height"], 0.5, places=3)

    def test_arabic_body_is_the_median_tooth_height_dots_dropped(self):
        t = FP.traits(save(self.tmp / "a" / "a.ttf", body=520))
        self.assertAlmostEqual(t["arabic_body"], 0.52, places=3)   # ن's dot above (body+120) does not count
        t = FP.traits(save(self.tmp / "b" / "b.ttf", body=520, drop=("س",)))
        self.assertAlmostEqual(t["arabic_body"], 0.52, places=3)   # measured from the rest
        t = FP.traits(save(self.tmp / "c" / "c.ttf", arabic=False))
        self.assertIsNone(t["arabic_body"])
        self.assertTrue(any("Arabic body" in r for r in t["reasons"]))

    def test_a_letter_drawn_as_base_plus_dot_glyphs_is_measured_whole(self):
        t = FP.traits(save(self.tmp / "s" / "s.ttf", body=540, split_beh=True, ar_stem=30, ar_bar=150))
        self.assertAlmostEqual(t["arabic_body"], 0.54, places=3)
        self.assertGreater(t["contrast_arabic"], 0.75)            # the dotless base glyph still gives the base stroke
        self.assertEqual(t["reasons"], [])

    def test_contrast_uniform_is_zero_and_thin_thick_is_high_bounded(self):
        flat = FP.traits(save(self.tmp / "a" / "a.ttf", stem=100, hair=100, ar_stem=90, ar_bar=90))
        self.assertLess(flat["contrast_latin"], 0.03)
        self.assertLess(flat["contrast_arabic"], 0.03)
        hi = FP.traits(save(self.tmp / "b" / "b.ttf", stem=150, hair=30, ar_stem=30, ar_bar=150))
        self.assertGreater(hi["contrast_latin"], 0.75)
        self.assertGreater(hi["contrast_arabic"], 0.75)
        for t in (flat, hi):
            for k in ("contrast_latin", "contrast_arabic"):
                self.assertTrue(0.0 <= t[k] <= 1.0)

    def test_ink_density_rises_with_the_committed_alexandria_weights(self):
        files = ["Alexandria-SemiBold.ttf", "Alexandria-Bold.ttf", "Alexandria-ExtraBold.ttf", "Alexandria-Black.ttf"]
        ar = [FP.traits(FONTS / "alexandria" / f)["density_arabic"] for f in files]
        la = [FP.traits(FONTS / "alexandria" / f)["density_latin"] for f in files]
        self.assertEqual(ar, sorted(ar))
        self.assertEqual(la, sorted(la))
        self.assertEqual(len(set(ar)), 4)

    def test_width_is_deterministic_and_cached_by_sha(self):
        p = save(self.tmp / "a" / "a.ttf", adv=600)
        t1 = FP.traits(p)
        hits = FP.cache_info()["hits"]
        t2 = FP.traits(p)
        self.assertEqual(t1, t2)
        self.assertEqual(FP.cache_info()["hits"], hits + 1)
        copy = self.tmp / "b" / "copy.ttf"                        # same bytes elsewhere: the same cache entry
        copy.parent.mkdir()
        shutil.copyfile(p, copy)
        FP.traits(copy)
        self.assertEqual(FP.cache_info()["hits"], hits + 2)
        self.assertAlmostEqual(t1["width_latin"], 600 / 500, places=2)
        self.assertEqual(t1["file_sha256"], FP.file_sha256(p))

    def test_variable_font_is_measured_at_the_role_weight_instance(self):
        p = save_variable(self.tmp / "v" / "V[wght].ttf", dict(ink=50, ar_bar=50, ar_stem=50, stem=50, hair=50),
                          dict(ink=150, ar_bar=150, ar_stem=150, stem=150, hair=150))
        lo, hi = FP.traits(p, weight=400), FP.traits(p, weight=900)
        self.assertTrue(lo["variable"])
        self.assertEqual((lo["weight"], hi["weight"]), (400, 900))
        self.assertGreater(hi["density_latin"], lo["density_latin"] * 1.5)
        self.assertGreater(hi["density_arabic"], lo["density_arabic"] * 1.5)
        default = FP.traits(p)                                    # no weight: the default instance
        self.assertEqual(default["density_latin"], lo["density_latin"])
        self.assertEqual(FP.traits(p, weight=2000)["weight"], 900)   # clamped to the axis

    def test_static_family_picks_the_nearest_weight_ties_heavier(self):
        fam = [{"file": "R.ttf", "weight_class": 400}, {"file": "S.ttf", "weight_class": 600},
               {"file": "B.ttf", "weight_class": 700}]
        self.assertEqual(FP.nearest_face(fam, 500)["file"], "S.ttf")
        self.assertEqual(FP.nearest_face(fam, 650)["file"], "B.ttf")   # 50 / 50: the heavier
        self.assertEqual(FP.nearest_face(fam, 300)["file"], "R.ttf")
        self.assertIsNone(FP.nearest_face([], 400))
        self.assertIsNone(FP.nearest_face(fam, 900, reach=150))        # Bold is 200 away: out of reach


# --------------------------------------------------------------------------- B. coverage gate
class TestCoverage(Tmp):
    def test_the_test_strings_are_the_owner_list(self):
        for ch in "ڤ٪،؛؟٠٩":
            self.assertIn(ch, FP.ARABIC_TEST)
        for ch in "AZaz09%&®":
            self.assertIn(ch, FP.LATIN_TEST)
        self.assertIn("لا", FP.ARABIC_LIGATURES)

    def test_a_face_missing_veh_is_refused_for_arabic_and_named(self):
        c = FP.coverage(save(self.tmp / "a" / "a.ttf", drop=("ڤ",)), "arabic")
        self.assertFalse(c["ok"])
        self.assertEqual(c["missing"], ["ڤ"])

    def test_lam_alef_must_form(self):
        c = FP.coverage(save(self.tmp / "a" / "a.ttf", lam_alef=False), "arabic")
        self.assertFalse(c["ok"])
        self.assertEqual(c["missing"], ["لا"])
        self.assertTrue(FP.coverage(save(self.tmp / "b" / "b.ttf"), "arabic")["ok"])

    def test_lam_alef_built_from_two_contextual_glyphs_passes(self):
        # four of the spec's Naskh/Ruqaa fonts draw lam-alef this way: refusing them would leave a formal or
        # handwritten client with no Arabic face from the table
        p = save(self.tmp / "c" / "ctx.ttf", lam_alef="context")
        face = FP._Face(p)
        got = [g[0] for g in face.shape("لا")]
        self.assertEqual(sorted(got), ["alef_ctx", "lam_ctx"])                # two glyphs, both contextual forms
        self.assertEqual(FP.coverage(p, "arabic"), {"ok": True, "missing": []})

    def test_missing_registered_sign_refuses_latin_only(self):
        p = save(self.tmp / "a" / "a.ttf", drop=("®",))
        self.assertEqual(FP.coverage(p, "latin"), {"ok": False, "missing": ["®"]})
        self.assertTrue(FP.coverage(p, "arabic")["ok"])

    def test_the_committed_fonts(self):
        self.assertTrue(FP.coverage(FONTS / "alexandria" / "Alexandria-Bold.ttf", "arabic")["ok"])
        self.assertTrue(FP.coverage(FONTS / "alexandria" / "Alexandria-Bold.ttf", "latin")["ok"])
        self.assertFalse(FP.coverage(FONTS / "inter" / "Inter-Bold.ttf", "arabic")["ok"])
        self.assertTrue(FP.coverage(FONTS / "inter" / "Inter-Bold.ttf", "latin")["ok"])


# --------------------------------------------------------------------------- C. score
class TestScore(unittest.TestCase):
    def test_weights_are_the_spec(self):
        self.assertEqual(FP.WEIGHTS, {"class": 40, "weight": 20, "height": 15, "contrast": 15, "width": 10})
        self.assertEqual(sum(FP.WEIGHTS.values()), 100)

    def test_identical_traits_same_class_is_100(self):
        s = FP.score(traits(), traits(), "geometric", "geometric")
        self.assertEqual(s["score"], 100)
        self.assertEqual(s["parts"], {"class": 40, "weight": 20, "height": 15, "contrast": 15, "width": 10})

    def test_each_part_moves_by_its_own_trait_and_stays_bounded(self):
        base = FP.score(traits(), traits(), "geometric", "geometric")["parts"]
        cases = {"weight": dict(density_latin=0.2), "height": dict(x_height=0.6), "contrast": dict(contrast_latin=0.35),
                 "width": dict(width_latin=1.6)}
        for part, kw in cases.items():
            with self.subTest(part=part):
                p = FP.score(traits(), traits(**kw), "geometric", "geometric")["parts"]
                self.assertLess(p[part], base[part])
                self.assertGreater(p[part], 0)
                self.assertEqual({k: v for k, v in p.items() if k != part},
                                 {k: v for k, v in base.items() if k != part})
        far = FP.score(traits(), traits(density_latin=5, x_height=5, contrast_latin=1, width_latin=50, space_latin=50),
                       "geometric", "handwritten")
        self.assertEqual(far["parts"], {"class": 0, "weight": 0, "height": 0, "contrast": 0, "width": 0})
        self.assertEqual(far["score"], 0)

    def test_pinned_values_catch_a_changed_constant(self):
        p = FP.score(traits(), traits(density_latin=0.24, x_height=0.55, contrast_latin=0.2, width_latin=1.5,
                                      space_latin=0.6), "geometric", "humanist")["parts"]
        # weight: |0.3-0.24|/0.3 = 0.2 of a 0.5 tolerance -> 20*(1-0.4) = 12
        self.assertAlmostEqual(p["weight"], 12.0, places=2)
        # height: r = 0.55/0.5 = 1.1, 15*(1 - ln1.1/ln1.6) = 11.96
        self.assertAlmostEqual(p["height"], round(15 * (1 - math.log(1.1) / math.log(1.6)), 2), places=2)
        # contrast: |0.1-0.2| of a 0.5 tolerance -> 15*0.8 = 12
        self.assertAlmostEqual(p["contrast"], 12.0, places=2)
        # width: 5*(1-ln(1.5/1.2)/ln2) + 5*(1-ln(0.6/0.5)/ln2)
        want = 5 * (1 - math.log(1.25) / math.log(2)) + 5 * (1 - math.log(1.2) / math.log(2))
        self.assertAlmostEqual(p["width"], round(want, 2), places=2)
        self.assertEqual(p["class"], 20)                           # geometric ~ humanist

    def test_class_matrix(self):
        self.assertEqual(FP.class_part("geometric", "handwritten"), (0, None))
        self.assertEqual(FP.class_part("formal", "formal")[0], 40)
        self.assertEqual(FP.class_part("humanist", "geometric"), FP.class_part("geometric", "humanist"))
        for a in FP.CLASSES:
            for b in FP.CLASSES:
                self.assertTrue(0 <= FP.class_part(a, b)[0] <= 40)

    def test_unknown_class_uses_terminal_shape_capped_below_full(self):
        same = FP.score(traits(), traits(), None, None)
        self.assertEqual(same["parts"]["class"], 30)
        self.assertTrue(any("class" in r for r in same["reasons"]))
        apart = FP.score(traits(angularity_arabic=0.9), traits(angularity_latin=0.2), None, "geometric")
        self.assertEqual(apart["parts"]["class"], 0)

    def test_bands(self):
        for s, b in ((100, "auto"), (70, "auto"), (69.99, "shown"), (50, "shown"), (49.99, "refused"), (0, "refused")):
            with self.subTest(score=s):
                self.assertEqual(FP.band(s), b)
        self.assertEqual([FP.band(s, True) for s in (100, 70, 50, 49.99)], ["shown", "shown", "shown", "refused"])

    def test_a_clamped_scale_is_never_automatic(self):
        s = FP.score(traits(), traits(x_height=0.2), "geometric", "geometric")
        self.assertTrue(s["scale_clamped"])
        self.assertGreaterEqual(s["score"], 70)
        self.assertEqual(s["band"], "shown")
        self.assertIn("clamped", FP.explain(s))
        row = dict(table_row(80), scale_clamped=True, band="shown")
        p = FP.pick("caption", typography({}), {"rows": [row]})["pair"]
        self.assertEqual(p["band"], "shown")
        self.assertTrue(p["reason"])

    def test_explain_lists_every_part_with_values_and_is_deterministic(self):
        s = FP.score(traits(), traits(x_height=0.55), "geometric", "humanist")
        text = FP.explain(s)
        self.assertEqual(text, FP.explain(FP.score(traits(), traits(x_height=0.55), "geometric", "humanist")))
        for word in ("class", "weight", "height", "contrast", "width", "geometric", "humanist", "latin_scale", "0.55"):
            self.assertIn(word, text)
        self.assertIn(f"{s['score']:.2f}", text)


# --------------------------------------------------------------------------- E. latin_scale
class TestLatinScale(unittest.TestCase):
    def test_scale_aligns_within_3_percent_and_4_percent_fails(self):
        for xh, body in ((500, 520), (430, 560), (560, 470), (1118 / 2048, 0.5)):
            with self.subTest(xh=xh, body=body):
                s = FP.latin_scale(xh, body)
                self.assertFalse(s["clamped"])
                self.assertTrue(FP.heights_aligned(xh, body, s["scale"]))
                self.assertTrue(abs(s["scale"] * xh / body - FP.TARGET_RATIO) <= 0.03 * FP.TARGET_RATIO)
                self.assertFalse(FP.heights_aligned(xh, body, s["scale"] * 1.04))
                self.assertFalse(FP.heights_aligned(xh, body, s["scale"] * 0.96))
        self.assertTrue(FP.heights_aligned(500, 500, 1.029))
        self.assertFalse(FP.heights_aligned(500, 500, 1.031))

    def test_target_ratio_and_tolerance_are_pinned(self):
        self.assertEqual((FP.TARGET_RATIO, FP.ALIGN_TOL, FP.SCALE_RANGE), (1.0, 0.03, (0.7, 1.4)))

    def test_clamped_and_reported_never_inf_or_nan(self):
        s = FP.latin_scale(200, 600)
        self.assertEqual((s["scale"], s["clamped"]), (1.4, True))
        self.assertTrue(s["reason"])
        self.assertEqual(FP.latin_scale(900, 300)["scale"], 0.7)
        near = FP.latin_scale(1000, 690)                         # needs 0.69: 0.7 still lands within 3 %
        self.assertEqual((near["scale"], near["clamped"]), (0.7, False))
        self.assertIn("within", near["reason"])
        self.assertTrue(FP.heights_aligned(1000, 690, near["scale"]))
        far = FP.latin_scale(1000, 670)                          # needs 0.67: 0.7 is 4.5 % off
        self.assertEqual((far["scale"], far["clamped"]), (0.7, True))
        self.assertFalse(FP.heights_aligned(1000, 670, far["scale"]))
        for xh, body in ((0, 500), (500, 0), (None, 500), (500, None), (float("nan"), 500), (float("inf"), 500)):
            with self.subTest(xh=xh, body=body):
                s = FP.latin_scale(xh, body)
                self.assertEqual(s["scale"], 1.0)
                self.assertTrue(math.isfinite(s["scale"]))
                self.assertTrue(s["reason"])

    def test_made_fonts_pair_within_3_percent(self):
        tmp = Path(tempfile.mkdtemp(prefix="t56s_"))
        try:
            ar = FP.traits(save(tmp / "a" / "ar.ttf", body=560, latin=False))
            la = FP.traits(save(tmp / "l" / "la.ttf", xh=470, arabic=False))
            r = FP.score(ar, la)
            self.assertTrue(FP.heights_aligned(la["x_height"], ar["arabic_body"], r["latin_scale"]))
            self.assertAlmostEqual(r["latin_scale"], 560 / 470, places=2)
        finally:
            FP.clear_cache()
            shutil.rmtree(tmp)


# --------------------------------------------------------------------------- D. pair resolution
def typography(rows: dict, pairing: dict | None = None) -> dict:
    fams = {fam: {"weights": [{"style": st, "file": str(f), "postscript_name": ps, "weight_class": w}
                              for st, f, ps, w in weights]} for fam, weights in rows.items()}
    out = {"families": fams, "roles": {}}
    if pairing is not None:
        out["pairing"] = pairing
    return out


def table_row(score, ar="Tab Arabic", la="Tab Latin", weight=700, status="measured"):
    return {"weights": [weight], "arabic": {"family": ar, "file": "a.ttf", "ps": ar.replace(" ", "") + "-Bold",
                                         "weight_class": weight},
            "latin": {"family": la, "file": "l.ttf", "ps": la.replace(" ", "") + "-Bold", "weight_class": weight},
            "kind": "pair", "class": {"arabic": "geometric", "latin": "geometric"}, "score": score,
            "band": FP.band(score), "latin_scale": 1.0, "status": status}


class TestPick(Tmp):
    def fonts(self):
        ar = save(self.tmp / "ar" / "Heavy Arabic.ttf", family="Heavy Arabic", style="Bold", weight=700, latin=False,
                  body=650, ar_stem=40, ar_bar=180, adv=900)
        la = save(self.tmp / "la" / "Thin Latin.ttf", family="Thin Latin", style="Bold", weight=700, arabic=False,
                  xh=380, ink=30, stem=30, hair=30, adv=420, space=120)
        return ar, la

    def test_client_pair_always_wins_even_low_with_its_score(self):
        ar, la = self.fonts()
        typ = typography({"Heavy Arabic": [("Bold", ar, "HeavyArabic-Bold", 700)],
                          "Thin Latin": [("Bold", la, "ThinLatin-Bold", 700)]},
                         {"caption": {"arabic": "Heavy Arabic", "latin": "Thin Latin", "source": "client"}})
        table = {"rows": [table_row(95)]}
        r = FP.pick("caption", typ, table)
        self.assertEqual(r["pair"]["source"], "client")
        self.assertLess(r["pair"]["score"], 50)                   # shown, never overridden by the 95 row
        self.assertEqual(r["pair"]["arabic"]["family"], "Heavy Arabic")
        self.assertEqual(r["pair"]["band"], "refused")
        self.assertTrue(r["pair"]["explain"])

    def test_client_latin_scale_is_kept(self):
        ar, la = self.fonts()
        typ = typography({"Heavy Arabic": [("Bold", ar, "HeavyArabic-Bold", 700)],
                          "Thin Latin": [("Bold", la, "ThinLatin-Bold", 700)]},
                         {"caption": {"arabic": "HeavyArabic-Bold", "latin": "ThinLatin-Bold", "latin_scale": 1.12,
                                      "source": "client"}})
        self.assertEqual(FP.pick("caption", typ, {"rows": []})["pair"]["latin_scale"], 1.12)

    def test_client_pair_with_a_coverage_miss_still_wins_with_a_finding(self):
        ar = save(self.tmp / "ar" / "ar.ttf", family="Ar", style="Bold", weight=700, latin=False)
        la = save(self.tmp / "la" / "la.ttf", family="La", style="Bold", weight=700, arabic=False, drop=("®", "&"))
        typ = typography({"Ar": [("Bold", ar, "Ar-Bold", 700)], "La": [("Bold", la, "La-Bold", 700)]},
                         {"caption": {"arabic": "Ar", "latin": "La", "source": "client"}})
        r = FP.pick("caption", typ, {"rows": [table_row(95)]})
        self.assertEqual(r["pair"]["source"], "client")
        f = " ".join(r["findings"])
        self.assertIn("®", f)
        self.assertIn("&", f)
        self.assertIn("La", f)

    def test_client_pair_with_a_corrupt_file_wins_unmeasured_with_a_finding(self):
        bad = self.tmp / "bad" / "bad.ttf"
        bad.parent.mkdir()
        bad.write_bytes(b"not a font at all" * 20)
        la = save(self.tmp / "la" / "la.ttf", family="La", style="Bold", weight=700, arabic=False)
        typ = typography({"Bad": [("Bold", bad, "Bad-Bold", 700)], "La": [("Bold", la, "La-Bold", 700)]},
                         {"caption": {"arabic": "Bad", "latin": "La", "source": "client"}})
        r = FP.pick("caption", typ, {"rows": [table_row(95)]})
        self.assertEqual(r["pair"]["source"], "client")
        self.assertIsNone(r["pair"]["score"])
        self.assertTrue(any("bad.ttf" in f for f in r["findings"]))

    def test_superfamily_is_recognised_and_scored(self):
        both = save(self.tmp / "sf" / "sf.ttf", family="Both", style="Bold", weight=700)
        typ = typography({"Both": [("Bold", both, "Both-Bold", 700)]})
        r = FP.pick("caption", typ, {"rows": [table_row(95)]})
        self.assertEqual(r["pair"]["source"], "superfamily")
        self.assertEqual(r["pair"]["arabic"]["family"], "Both")
        self.assertEqual(r["pair"]["latin"]["family"], "Both")
        self.assertGreaterEqual(r["pair"]["score"], 70)
        self.assertTrue(FP.is_superfamily([{"file": str(both), "weight_class": 700}], 700))
        # one family drawn for both scripts by design: the full class part, never the uncurated stand-in
        self.assertEqual(r["pair"]["parts"]["class"], FP.WEIGHTS["class"])
        self.assertNotIn("uncurated", r["pair"]["explain"])

    def test_a_superfamily_that_is_auto_is_not_demoted_to_shown(self):
        # 77.37 with the full class part; the uncurated stand-in (max 30) would make it 67.37 and send the client's own
        # bilingual brand family to the editor as a doubtful pair
        both = save(self.tmp / "sf2" / "sf2.ttf", family="Both2", style="Bold", weight=700, xh=430, body=520,
                    stem=100, hair=70)
        typ = typography({"Both2": [("Bold", both, "Both2-Bold", 700)]})
        p = FP.pick("caption", typ, {"rows": []})["pair"]
        self.assertEqual((p["source"], p["band"]), ("superfamily", "auto"))
        self.assertEqual(p["reason"], "")

    def test_latin_digits_only_is_not_a_superfamily(self):
        p = save(self.tmp / "d" / "d.ttf", family="Dig", style="Bold", weight=700,
                 drop=tuple(c for c in LATIN if not c.isdigit()))
        self.assertFalse(FP.is_superfamily([{"file": str(p), "weight_class": 700}], 700))
        typ = typography({"Dig": [("Bold", p, "Dig-Bold", 700)]})
        r = FP.pick("caption", typ, {"rows": [table_row(80, ar="Dig")]})
        self.assertEqual(r["pair"]["source"], "table")

    def test_table_prefers_the_clients_arabic_family_then_score(self):
        ar = save(self.tmp / "ar" / "ar.ttf", family="Client Ar", style="Bold", weight=700, latin=False)
        typ = typography({"Client Ar": [("Bold", ar, "ClientAr-Bold", 700)]})
        rows = [table_row(90, ar="Other", la="L1"), table_row(72, ar="Client Ar", la="L2"),
                table_row(99, ar="Client Ar", la="L3", status="candidate-unmeasured")]
        r = FP.pick("caption", typ, {"rows": rows})
        self.assertEqual((r["pair"]["source"], r["pair"]["latin"]["family"]), ("table", "L2"))
        r = FP.pick("caption", typography({}), {"rows": rows})
        self.assertEqual(r["pair"]["latin"]["family"], "L1")

    def test_unmeasured_and_low_rows_are_never_picked(self):
        rows = [table_row(99, status="candidate-unmeasured"), table_row(49.99), table_row(30)]
        r = FP.pick("caption", typography({}), {"rows": rows})
        self.assertIsNone(r["pair"])
        self.assertTrue(r["reason"])

    def test_shown_band_carries_the_reason(self):
        r = FP.pick("caption", typography({}), {"rows": [table_row(60)]})
        self.assertEqual(r["pair"]["band"], "shown")
        self.assertTrue(r["pair"]["reason"])

    def test_role_weight_selects_the_rows(self):
        rows = [table_row(80, la="Body", weight=500), table_row(75, la="Cap", weight=700)]
        self.assertEqual(FP.pick("caption", typography({}), {"rows": rows})["pair"]["latin"]["family"], "Cap")
        self.assertEqual(FP.pick("body", typography({}), {"rows": rows})["pair"]["latin"]["family"], "Body")
        self.assertEqual(FP.role_weight("headline"), 900)

    def test_with_no_client_font_the_highest_score_wins_across_classes(self):
        rows = [dict(table_row(60, ar="Disp", la="DispL"), **{"class": {"arabic": "display", "latin": "display"}}),
                table_row(90, ar="Geo", la="GeoL")]
        self.assertEqual(FP.pick("caption", typography({}), {"rows": rows})["pair"]["arabic"]["family"], "Geo")

    def test_a_client_arabic_font_gets_the_best_measured_table_latin(self):
        ar = save(self.tmp / "ar" / "ClientAr.ttf", family="Client Ar", style="Bold", weight=700, latin=False)
        good = save(self.tmp / "good" / "Good.ttf", family="Good L", style="Bold", weight=700, arabic=False)
        bad = save(self.tmp / "bad" / "Bad.ttf", family="Bad L", style="Bold", weight=700, arabic=False, xh=300,
                   ink=20, stem=150, hair=20, adv=350, space=90)
        typ = typography({"Client Ar": [("Bold", ar, "ClientAr-Bold", 700)]})
        rows = [table_row(95, ar="Other", la="Bad L"), table_row(60, ar="Other 2", la="Good L")]
        files = {"Bad L": bad, "Good L": good}
        r = FP.pick("caption", typ, {"rows": rows},
                    locate=lambda f: str(files[f["family"]]) if f.get("family") in files else None)
        p = r["pair"]
        self.assertEqual((p["source"], p["kind"], p["arabic"]["family"], p["latin"]["family"]),
                         ("table", "client-arabic", "Client Ar", "Good L"))
        self.assertGreaterEqual(p["score"], 50)
        self.assertEqual(FP.pick("caption", typ, {"rows": rows})["pair"]["latin"]["family"], "Bad L")  # no locate
        r = FP.pick("caption", typ, {"rows": [table_row(95, ar="Other", la="Bad L")]},
                    locate=lambda f: str(files[f["family"]]) if f.get("family") in files else None)
        self.assertIsNone(r["pair"])                              # Bad L measures < 50 against the client's face

    def test_locate_drops_rows_whose_faces_are_not_on_this_computer(self):
        rows = [table_row(90, la="Absent"), table_row(70, la="Here")]
        r = FP.pick("caption", typography({}), {"rows": rows},
                    locate=lambda face: "x.ttf" if face["family"] != "Absent" else None)
        self.assertEqual(r["pair"]["latin"]["family"], "Here")
        self.assertTrue(any("Absent" in f for f in r["findings"]))


# --------------------------------------------------------------------------- F. the table
class TestTable(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.raw = TABLE.read_bytes()
        cls.t = json.loads(cls.raw.decode("utf-8"))

    def test_structure_and_licence_proof(self):
        self.assertEqual(FP.check_table(self.t), [])
        measured = [r for r in self.t["rows"] if r["status"] == "measured"]
        self.assertGreaterEqual(len(measured), 6)
        for r in measured:
            for side in ("arabic", "latin"):
                lic = r["licence"][side]
                self.assertEqual(set(lic), {"name13", "name14", "ofl_sha256", "file_sha256"})
        broken = json.loads(self.raw)
        del broken["rows"][0]["licence"]["latin"]["ofl_sha256"]
        self.assertTrue(FP.check_table(broken))

    def test_every_spec_family_is_measured_or_a_candidate_with_its_reason(self):
        measured = {r[s]["family"] for r in self.t["rows"] for s in ("arabic", "latin")}
        cands = {c["family"]: c for c in self.t["candidates"]}
        for fam in ("Alexandria", "Cairo", "Tajawal", "Readex Pro", "IBM Plex Sans Arabic", "Noto Sans Arabic", "Amiri",
                    "Noto Naskh Arabic", "Markazi Text", "Aref Ruqaa", "Lalezar", "Rakkas", "IBM Plex Sans",
                    "Noto Sans"):
            with self.subTest(family=fam):
                self.assertTrue(fam in measured or fam in cands, fam)
                self.assertIn(fam, self.t["families"])
                self.assertIn(self.t["families"][fam]["class"], FP.CLASSES)
        for c in cands.values():
            self.assertEqual(c["status"], "candidate-unmeasured")
            self.assertTrue(c["reason"])
        for cls in FP.CLASSES:                                    # every class has a measured pair
            self.assertTrue(any(r["class"]["arabic"] == cls for r in self.t["rows"]), cls)

    def test_candidates_are_never_picked(self):
        poisoned = {"rows": [table_row(100, ar=c["family"], status="candidate-unmeasured")
                             for c in self.t["candidates"]] + [table_row(100, status="candidate-unmeasured")]}
        self.assertIsNone(FP.pick("caption", typography({}), poisoned)["pair"])

    def test_only_ofl_families_and_ofl_sha_matches(self):
        for fam, info in self.t["families"].items():
            if not info.get("source"):
                continue
            ofl = REPO / info["source"] / "OFL.txt"
            self.assertEqual(info["ofl_sha256"], FP.text_sha256(ofl), fam)
        for r in self.t["rows"]:
            for side in ("arabic", "latin"):
                self.assertTrue(FP.is_ofl(r["licence"][side]["name13"], r["licence"][side]["name14"]))

    def test_rebuilding_from_the_repo_fonts_is_byte_identical(self):
        tmp = Path(tempfile.mkdtemp(prefix="t56t_"))
        try:
            out = tmp / "font-pairings.json"
            FP.write_table(out, FP.build_table([FONTS], self.t, rel_root=REPO))
            self.assertEqual(out.read_bytes(), self.raw)
        finally:
            FP.clear_cache()
            shutil.rmtree(tmp)

    def test_rows_sorted_deterministically(self):
        rows = self.t["rows"]
        self.assertEqual(rows, sorted(rows, key=FP.row_key))

    def test_every_measured_row_aligns_heights_within_3_percent_unless_clamped(self):
        for r in self.t["rows"]:
            if r["status"] == "measured" and not r["scale_clamped"]:
                self.assertTrue(FP.heights_aligned(r["traits"]["x_height"], r["traits"]["arabic_body"],
                                                   r["latin_scale"]), r)

    def test_default_table_path_and_loader(self):
        self.assertEqual(FP.DEFAULT_TABLE, TABLE)
        self.assertEqual(FP.load_table(), self.t)


class TestBuilder(Tmp):
    def curation(self, **fams):
        return {"families": {k: {"class": v, "use": True, "note": ""} for k, v in fams.items()}, "candidates": []}

    def test_non_ofl_font_is_refused(self):
        save(self.tmp / "f" / "nonofl" / "N.ttf", family="NonOfl", style="Bold", weight=700, ofl=False, ofl_txt=False)
        with self.assertRaises(FP.PairingRefused) as cm:
            FP.build_table([self.tmp / "f"], self.curation(NonOfl="geometric"), rel_root=self.tmp)
        self.assertIn("NonOfl", str(cm.exception))
        lic = FP.licence(self.tmp / "f" / "nonofl" / "N.ttf")
        self.assertFalse(lic["ok"])

    def test_a_commercial_font_dropped_next_to_an_ofl_txt_is_refused(self):
        # the name table says "all rights reserved": an OFL.txt lying in the folder does not make it free to ship
        p = save(self.tmp / "f" / "eula" / "E.ttf", family="Eula", style="Bold", weight=700, ofl=False, ofl_txt=True)
        lic = FP.licence(p)
        self.assertFalse(lic["ok"])
        self.assertIn("name table", lic["reason"])
        with self.assertRaises(FP.PairingRefused) as cm:
            FP.build_table([self.tmp / "f"], self.curation(Eula="geometric"), rel_root=self.tmp)
        self.assertIn("Eula", str(cm.exception))

    def test_an_ofl_named_font_without_the_licence_text_is_refused(self):
        # OFL requires the licence to travel with the font: no OFL.txt (or a file that is not the OFL) -> refused
        p = save(self.tmp / "f" / "bare" / "B.ttf", family="Bare", style="Bold", weight=700, ofl_txt=False)
        self.assertFalse(FP.licence(p)["ok"])
        self.assertIn("OFL.txt", FP.licence(p)["reason"])
        (p.parent / "OFL.txt").write_bytes(b"Copyright (c) test. All rights reserved.\n")
        self.assertFalse(FP.licence(p)["ok"])
        with self.assertRaises(FP.PairingRefused) as cm:
            FP.build_table([self.tmp / "f"], self.curation(Bare="geometric"), rel_root=self.tmp)
        self.assertIn("Bare", str(cm.exception))

    def test_ofl_proof_ignores_the_checkouts_line_endings(self):
        a = save(self.tmp / "lf" / "A.ttf")
        b = save(self.tmp / "crlf" / "A.ttf")
        (b.parent / "OFL.txt").write_bytes(OFL_TEXT.replace("\n", "\r\n").encode("utf-8"))
        self.assertNotEqual(FP.file_sha256(a.parent / "OFL.txt"), FP.file_sha256(b.parent / "OFL.txt"))
        self.assertEqual(FP.licence(a)["ofl_sha256"], FP.licence(b)["ofl_sha256"])

    def test_refusal_writes_nothing(self):
        save(self.tmp / "f" / "good" / "G-Bold.ttf", family="Good", style="Bold", weight=700)
        bad = self.tmp / "f" / "good" / "Broken.ttf"
        bad.write_bytes(b"\x00\x01\x00\x00garbage" * 50)
        out = self.tmp / "out" / "font-pairings.json"
        with self.assertRaises(FP.PairingRefused) as cm:
            FP.write_table(out, FP.build_table([self.tmp / "f"], self.curation(Good="geometric"), rel_root=self.tmp))
        self.assertIn("Broken.ttf", str(cm.exception))
        self.assertFalse(out.exists())
        self.assertFalse(out.parent.exists())

    def test_a_downloaded_folder_adds_families_with_their_shas(self):
        ext = Path(tempfile.mkdtemp(prefix="t56ext_"))
        try:
            save(ext / "newar" / "NewAr-Bold.ttf", family="New Ar", style="Bold", weight=700, latin=False)
            save(self.tmp / "repo" / "f" / "lat" / "Lat-Bold.ttf", family="Lat", style="Bold", weight=700, arabic=False)
            cur = self.curation(**{"New Ar": "humanist", "Lat": "humanist"})
            t = FP.build_table([self.tmp / "repo" / "f", ext], cur,
                               rel_root=self.tmp / "repo")
            self.assertEqual(t["families"]["New Ar"]["source"], None)
            self.assertEqual(t["families"]["New Ar"]["origin"], "external")
            self.assertEqual(t["families"]["Lat"]["source"], "f/lat")
            self.assertEqual(t["families"]["New Ar"]["files"][0]["sha256"],
                             FP.file_sha256(ext / "newar" / "NewAr-Bold.ttf"))
            row = next(r for r in t["rows"] if r["arabic"]["family"] == "New Ar")
            self.assertEqual(row["latin"]["family"], "Lat")
            self.assertEqual(row["status"], "measured")
        finally:
            FP.clear_cache()
            shutil.rmtree(ext)

    def test_a_one_file_family_serves_every_role_weight(self):
        # display faces ship one heavy file labelled 400: a headline (900) must still find the display pair
        save(self.tmp / "f" / "disar" / "DisAr-Regular.ttf", family="Dis Ar", style="Regular", weight=400,
             latin=False, ar_bar=160, ar_stem=160)
        save(self.tmp / "f" / "dislat" / "DisLat-Regular.ttf", family="Dis Lat", style="Regular", weight=400,
             arabic=False, ink=160, stem=160, hair=160)
        t = FP.build_table([self.tmp / "f"], self.curation(**{"Dis Ar": "display", "Dis Lat": "display"}),
                           rel_root=self.tmp)
        row = next(r for r in t["rows"] if r["arabic"]["family"] == "Dis Ar")
        self.assertEqual(row["weights"], list(FP.ROW_WEIGHTS))
        self.assertEqual(FP.pick("headline", typography({}), t)["pair"]["latin"]["family"], "Dis Lat")
        # a family with several static files still keeps to WEIGHT_REACH (no Regular serving a headline)
        save(self.tmp / "g" / "multi" / "M-Regular.ttf", family="Multi", style="Regular", weight=400, arabic=False)
        save(self.tmp / "g" / "multi" / "M-Medium.ttf", family="Multi", style="Medium", weight=500, arabic=False)
        save(self.tmp / "g" / "ar" / "A-Regular.ttf", family="Ar G", style="Regular", weight=400, latin=False)
        t2 = FP.build_table([self.tmp / "g"], self.curation(**{"Multi": "geometric", "Ar G": "geometric"}),
                            rel_root=self.tmp)
        self.assertEqual(sorted(w for r in t2["rows"] if r["latin"]["family"] == "Multi" for w in r["weights"]),
                         [400, 500])

    def test_uncurated_family_is_a_finding_not_a_row(self):
        save(self.tmp / "f" / "x" / "X-Bold.ttf", family="Stray", style="Bold", weight=700)
        t = FP.build_table([self.tmp / "f"], self.curation(), rel_root=self.tmp)
        self.assertEqual(t["rows"], [])
        self.assertTrue(any("Stray" in f for f in t["findings"]))


# --------------------------------------------------------------------------- G. hostile input / platform
class TestHostile(Tmp):
    def test_corrupt_font_raises_a_probe_error_not_a_crash(self):
        bad = self.tmp / "bad.ttf"
        bad.write_bytes(b"\x00garbage" * 100)
        with self.assertRaises(FP.FontProbeError):
            FP.traits(bad)
        c = FP.coverage(bad, "latin")
        self.assertFalse(c["ok"])
        self.assertTrue(c["error"])

    def test_collection_face_index(self):
        from fontTools.ttLib import TTCollection
        coll = TTCollection()
        coll.fonts = [make_font(family="C0", xh=400), make_font(family="C1", xh=550)]
        p = self.tmp / "c.ttc"
        coll.save(str(p))
        self.assertAlmostEqual(FP.traits(p, index=0)["x_height"], 0.40, places=3)
        self.assertAlmostEqual(FP.traits(p, index=1)["x_height"], 0.55, places=3)

    def test_huge_glyph_count_and_arabic_path_with_spaces(self):
        p = save(self.tmp / "مجلد خطوط" / "خط تجريبي كبير.ttf", extra_glyphs=20000)
        t = FP.traits(p)
        self.assertAlmostEqual(t["x_height"], 0.5, places=3)
        self.assertTrue(FP.coverage(p, "arabic")["ok"])
        self.assertTrue(FP.licence(p)["ok"])

    def test_platform_branches_resolve_the_same(self):
        p = save(self.tmp / "ar" / "BrandAr-Bold.ttf", family="Brand Ar", style="Bold", weight=700, latin=False)
        la = save(self.tmp / "la" / "BrandLa-Bold.ttf", family="Brand La", style="Bold", weight=700, arabic=False)
        typ = typography({"Brand Ar": [("Bold", p, "BrandAr-Bold", 700)],
                          "Brand La": [("Bold", la, "BrandLa-Bold", 700)]},
                         {"caption": {"arabic": "brandar-bold.TTF", "latin": "BrandLa-Bold.ttf", "source": "client"}})
        got = {}
        for plat_name in ("win32", "darwin"):
            with mock.patch.object(FP.sys, "platform", plat_name):
                got[plat_name] = (FP.pick("caption", typ, {"rows": []})["pair"]["arabic"]["family"],
                                  FP.load_table()["rows"])
        self.assertEqual(got["win32"], got["darwin"])
        self.assertEqual(got["win32"][0], "Brand Ar")             # file names fold case on Windows and macOS
        with mock.patch.object(FP.sys, "platform", "linux"):
            r = FP.pick("caption", typ, {"rows": []})
        self.assertNotEqual((r["pair"] or {}).get("source"), "client")  # exact case elsewhere: no match
        self.assertTrue(any("brandar-bold.TTF" in f for f in r["findings"]))


class TestSpecimen(Tmp):
    def test_specimen_sheet_draws_every_repo_row(self):
        t = json.loads(TABLE.read_text(encoding="utf-8"))
        repo = {n for n, f in t["families"].items() if f.get("origin") == "repo"}
        t["rows"] = [r for r in t["rows"] if {r["arabic"]["family"], r["latin"]["family"]} <= repo]
        self.assertTrue(t["rows"])
        out = self.tmp / "sheet" / "specimen.png"
        info = FP.specimen_sheet(t, [FONTS], out)
        from PIL import Image
        with Image.open(out) as im:
            self.assertEqual(im.size, (1600, 140 * len(t["rows"])))
        self.assertEqual((info["rows"], info["missing"]), (len(t["rows"]), []))
        gone = FP.specimen_sheet({"rows": [dict(t["rows"][0], arabic=dict(t["rows"][0]["arabic"], file="nope.ttf"))]},
                                 [FONTS], self.tmp / "sheet" / "none.png")
        self.assertEqual((gone["rows"], len(gone["missing"])), (0, 1))


if __name__ == "__main__":
    unittest.main()
