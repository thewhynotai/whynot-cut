# SPDX-License-Identifier: GPL-3.0-or-later
# © 2026 The Why Not AI (thewhynot.ai)
"""Addendum M M2-T4 (looks track hook): the caption font chain takes the M2 font pair first.
  * the client's own pairing (typography.json `pairing`) leads both chains; its Latin face carries latin_scale and the
    Typesetter draws it at size x scale;
  * a superfamily or a table pair fills in after the client's own faces, before the look fallback and the house faces;
  * a table pair whose faces are not installed here (or are variable instances) is skipped: the chain is exactly the
    pre-M2 chain, and so it is with `pairing=False`.
Fonts: the committed OFL fonts in guide-ar/fonts. Run: bash tools/test.sh -p test_looks_pairing.py
"""
import sys as _sys
_sys.dont_write_bytecode = True  # keep the plugin folder free of __pycache__
import _isolation  # noqa: F401,E402  G79: sandbox the engine home first (tests/_isolation.py)
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys = _sys
SK = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SK / "engine" / "reel"))

from lib import font_pairing, fonts  # noqa: E402
from lib import looks_type as LT  # noqa: E402

FONTS = SK.parent / "guide-ar" / "fonts"
PLEX = FONTS / "ibmplexsansarabic" / "IBMPlexSansArabic-Regular.ttf"
PLEX_SB = FONTS / "ibmplexsansarabic" / "IBMPlexSansArabic-SemiBold.ttf"
INTER = FONTS / "inter" / "Inter-Regular.ttf"
INTER_B = FONTS / "inter" / "Inter-Bold.ttf"
SYNE = FONTS / "syne" / "Syne-Bold.ttf"
ALEX = FONTS / "alexandria" / "Alexandria-Bold.ttf"


def face(path: Path, ps: str, family: str, style: str = "Bold", weight: int = 700) -> dict:
    return {"file": str(path), "index": 0, "ps": ps, "family": family, "style": style, "weight": weight}


HOUSE = {"arabic": [face(PLEX_SB, "IBMPlexSansArabic-SemiBold", "House Arabic", "SemiBold", 600)],
         "latin": [face(INTER, "Inter-Regular", "House Latin", "Regular", 400)]}


def typography(*rows, roles=None, pairing=None) -> dict:
    fams = {fam: {"weights": [{"style": s, "file": str(f), "postscript_name": ps, "weight_class": w}
                              for s, f, ps, w in weights]} for fam, weights in rows}
    out = {"families": fams, "roles": roles or {}}
    if pairing is not None:
        out["pairing"] = pairing
    return out


def tiny_font(path: Path, family: str, ps_name: str, drop: str = "") -> Path:
    """A rectangle TrueType font drawing the Arabic and Latin gate strings (lam-alef as an rlig ligature), x-height and
    Arabic body both 500/1000, minus the characters in `drop`."""
    from fontTools.fontBuilder import FontBuilder
    from fontTools.pens.ttGlyphPen import TTGlyphPen
    chars = [c for c in dict.fromkeys(font_pairing.LATIN_TEST + font_pairing.ARABIC_TEST + "لا") if c not in drop]

    def rect(x0, y0, x1, y1):
        pen = TTGlyphPen(None)
        for x, y in ((x0, y0), (x0, y1), (x1, y1), (x1, y0)):
            (pen.moveTo if (x, y) == (x0, y0) else pen.lineTo)((x, y))
        pen.closePath()
        return pen.glyph()
    glyphs = {f"u{ord(c):04X}": rect(50, 0, 550, 750 if c in "Aا" else 500) for c in chars}
    glyphs["lam_alef"], glyphs[".notdef"] = rect(50, 0, 550, 500), rect(50, 0, 450, 700)
    order = [".notdef", "space"] + [g for g in glyphs if g != ".notdef"]
    glyphs["space"] = TTGlyphPen(None).glyph()
    fb = FontBuilder(1000, isTTF=True)
    fb.setupGlyphOrder(order)
    cmap = {ord(c): f"u{ord(c):04X}" for c in chars}
    cmap[0x20] = "space"
    fb.setupCharacterMap(cmap)
    fb.setupGlyf({g: glyphs[g] for g in order})
    fb.setupHorizontalMetrics({g: (250 if g == "space" else 600, 50) for g in order})
    fb.setupHorizontalHeader(ascent=900, descent=-300)
    fb.setupNameTable({"familyName": family, "styleName": "Bold", "psName": ps_name})
    fb.setupOS2(usWeightClass=700)
    fb.setupPost()
    fb.addOpenTypeFeatures("languagesystem arab dflt;\nfeature rlig { sub u0644 u0627 by lam_alef; } rlig;\n")
    path.parent.mkdir(parents=True, exist_ok=True)
    fb.font.save(str(path))
    return path


def first_latin(ch: dict) -> tuple:
    f = ch["latin"][0]
    return f["ps"], round(float(f.get("scale") or 1.0), 4)


def ps(fs):
    return [f["ps"] for f in fs]


class TestChainTakesThePair(unittest.TestCase):
    def setUp(self):
        font_pairing.clear_cache()

    def test_client_pairing_leads_both_chains_with_latin_scale(self):
        typ = typography(("Alexandria", [("Bold", ALEX, "Alexandria-Bold", 700)]),
                         ("Syne", [("Bold", SYNE, "Syne-Bold", 700)]),
                         roles={"caption": "Alexandria-Bold"},
                         pairing={"caption": {"arabic": "Alexandria", "latin": "Syne", "source": "client",
                                              "latin_scale": 0.95}})
        ch = LT.font_chain(typ, "caption", house=HOUSE)
        self.assertEqual(ps(ch["arabic"]), ["Alexandria-Bold", "IBMPlexSansArabic-SemiBold"])
        self.assertEqual(ps(ch["latin"])[:2], ["Syne-Bold", "Alexandria-Bold"])
        self.assertEqual(ch["latin"][0]["scale"], 0.95)
        self.assertEqual((ch["pair"]["source"], ch["pair"]["latin_scale"]), ("client", 0.95))

    def test_no_pair_keeps_the_pre_m2_chain(self):
        typ = typography(("Syne", [("Bold", SYNE, "Syne-Bold", 700)]), roles={"caption": "Syne-Bold"})
        ch = LT.font_chain(typ, "caption", house=HOUSE)          # sandbox: no table face is installed
        self.assertIsNone(ch["pair"])
        self.assertEqual(ps(ch["latin"]), ["Syne-Bold", "Inter-Regular"])
        self.assertEqual(ps(ch["arabic"]), ["IBMPlexSansArabic-SemiBold"])
        off = LT.font_chain(typ, "caption", house=HOUSE, pairing=False)
        self.assertEqual((ps(off["arabic"]), ps(off["latin"]), off["pair"]), (ps(ch["arabic"]), ps(ch["latin"]), None))

    def test_the_clients_role_face_keeps_its_place_and_the_pair_is_measured_against_it(self):
        # captions in Inter, body in Alexandria: the chain draws Alexandria + Inter, so that is the pair, at its scale
        typ = typography(("Inter", [("Bold", INTER_B, "Inter-Bold", 700)]),
                         ("Alexandria", [("Bold", ALEX, "Alexandria-Bold", 700)]),
                         roles={"caption": "Inter-Bold", "body": "Alexandria-Bold"})
        ch = LT.font_chain(typ, "caption", house=HOUSE)
        want = font_pairing.measure_pair({"file": str(ALEX)}, {"file": str(INTER_B)}, 700)["latin_scale"]
        self.assertEqual((ch["pair"]["arabic"], ch["pair"]["latin"], ch["pair"]["source"]),
                         ("Alexandria", "Inter", "client-fonts"))
        self.assertEqual(ps(ch["arabic"])[0], "Alexandria-Bold")
        self.assertEqual(first_latin(ch), ("Inter-Bold", round(want, 4)))
        self.assertEqual(ch["pair"]["latin_scale"], want)

    def test_a_client_arabic_brand_face_never_gets_another_familys_latin(self):
        typ = typography(("Plex", [("SemiBold", PLEX_SB, "IBMPlexSansArabic-SemiBold", 600)]),
                         roles={"caption": "IBMPlexSansArabic-SemiBold"})
        installed = {"Alexandria-Bold": str(ALEX), "Inter-Bold": str(INTER_B), "Syne-Bold": str(SYNE)}
        with mock.patch.object(fonts, "find", side_effect=lambda n, dirs=None: (
                {"file": installed[n], "ps": n, "index": 0} if n in installed else None)):
            ch = LT.font_chain(typ, "caption", house=HOUSE)
        self.assertEqual(ch["pair"]["source"], "superfamily")     # its own family draws both scripts
        self.assertEqual((ch["pair"]["arabic"], ch["pair"]["latin"]), ("Plex", "Plex"))

    def test_an_installed_table_pair_fills_the_missing_latin(self):
        installed = {"Alexandria-Bold": str(ALEX), "Inter-Bold": str(INTER_B), "Syne-Bold": str(SYNE),
                     "IBMPlexSansArabic-SemiBold": str(PLEX_SB), "IBMPlexSansArabic-Regular": str(PLEX)}
        with mock.patch.object(fonts, "find", side_effect=lambda n, dirs=None: (
                {"file": installed[n], "ps": n, "index": 0} if n in installed else None)):
            ch = LT.font_chain(typography(), "caption", house=HOUSE)
        self.assertEqual(ch["pair"]["source"], "table")
        self.assertIn(ch["pair"]["band"], ("auto", "shown"))
        self.assertTrue(all(f.get("scale") for f in ch["latin"][:1]))
        self.assertNotEqual(ps(ch["latin"])[0], "Inter-Regular")   # the pair's Latin face, before the house face
        row_fams = {(r["arabic"]["family"], r["latin"]["family"]) for r in font_pairing.load_table()["rows"]}
        self.assertIn((ch["pair"]["arabic"], ch["pair"]["latin"]), row_fams)

    def test_variable_instances_are_not_used_yet(self):
        self.assertIsNone(LT_locate({"family": "X", "file": str(ALEX), "ps": "Alexandria-Bold", "instance": 700}))
        self.assertEqual(LT_locate({"family": "X", "file": str(ALEX), "ps": "Alexandria-Bold", "instance": None}),
                         str(ALEX))


class TestTheScaleIsDrawn(unittest.TestCase):
    """Review ca5f2cb P1-2: the first Latin face of the chain carries the pair's latin_scale, whatever the source."""

    def setUp(self):
        font_pairing.clear_cache()
        self.tmp = Path(tempfile.mkdtemp(prefix="t56lk_"))

    def tearDown(self):
        _isolation.rmtree_retry(self.tmp)

    def check(self, typ, want_ps, arabic_file, latin_file, source):
        ch = LT.font_chain(typ, "caption", house=HOUSE)
        want = font_pairing.measure_pair({"file": str(arabic_file)}, {"file": str(latin_file)}, 700,
                                         superfamily=arabic_file == latin_file)["latin_scale"]
        self.assertEqual(ch["pair"]["source"], source)
        self.assertEqual(first_latin(ch), (want_ps, round(want, 4)))
        self.assertEqual((ch["pair"]["latin_scale"], ch["pair"]["latin_drawn"]), (want, ch["latin"][0]["family"]))
        return want

    def test_the_house_arabic_face_as_a_superfamily(self):
        typ = typography(("IBM Plex Sans Arabic", [("SemiBold", PLEX_SB, "IBMPlexSansArabic-SemiBold", 600)]))
        want = self.check(typ, "IBMPlexSansArabic-SemiBold", PLEX_SB, PLEX_SB, "superfamily")
        self.assertAlmostEqual(want, 0.7682, places=4)               # what the table and the specimen report

    def test_alexandria_as_a_superfamily(self):
        typ = typography(("Alexandria", [("Bold", ALEX, "Alexandria-Bold", 700)]))
        self.check(typ, "Alexandria-Bold", ALEX, ALEX, "superfamily")

    def test_a_latin_brand_face_for_captions(self):
        typ = typography(("Inter", [("Bold", INTER_B, "Inter-Bold", 700)]),
                         ("Alexandria", [("Bold", ALEX, "Alexandria-Bold", 700)]),
                         roles={"caption": "Inter-Bold", "body": "Alexandria-Bold"})
        self.check(typ, "Inter-Bold", ALEX, INTER_B, "client-fonts")

    def test_a_face_that_draws_both_but_misses_a_gate_is_drawn_at_its_own_scale(self):
        # like Tajawal for an Arabic-Indic client: its own Latin is what the chain draws, so it is the pair
        f = tiny_font(self.tmp / "gap" / "Gap-Bold.ttf", "Gap", "Gap-Bold", drop="®")
        typ = typography(("Gap", [("Bold", f, "Gap-Bold", 700)]))
        self.check(typ, "Gap-Bold", f, f, "client-fonts")

    def test_with_emphasis_the_stepped_face_keeps_the_scale_and_a_note_says_so(self):
        typ = typography(("IBM Plex Sans Arabic", [("Regular", PLEX, "IBMPlexSansArabic-Regular", 400),
                                                   ("SemiBold", PLEX_SB, "IBMPlexSansArabic-SemiBold", 600)]),
                         roles={"caption": "IBMPlexSansArabic-Regular"})
        ch = LT.font_chain(typ, "caption", house=HOUSE, weight_step=200)
        self.assertEqual(ch["latin"][0]["ps"], "IBMPlexSansArabic-SemiBold")
        self.assertEqual(round(ch["latin"][0]["scale"], 4), round(ch["pair"]["latin_scale"], 4))
        self.assertTrue(any("emphasis face keeps its latin_scale" in n for n in ch["notes"]))

    def test_a_stored_table_pair_for_another_arabic_is_not_drawn_with_its_scale(self):
        # review ca5f2cb P1-1 (a) through the chain: the caption face is the client's Arabic brand face
        brand = tiny_font(self.tmp / "brand" / "BrandAr-Bold.ttf", "Brand Ar", "BrandAr-Bold",
                          drop=font_pairing.LATIN_TEST)
        typ = typography(("Brand Ar", [("Bold", brand, "BrandAr-Bold", 700)]),
                         ("Alexandria", [("Bold", ALEX, "Alexandria-Bold", 700)]),
                         ("Inter", [("Bold", INTER_B, "Inter-Bold", 700)]),
                         roles={"caption": "BrandAr-Bold"},
                         pairing={"caption": {"arabic": "Alexandria", "latin": "Inter", "source": "table"}})
        ch = LT.font_chain(typ, "caption", house=HOUSE)
        self.assertEqual(ps(ch["arabic"])[0], "BrandAr-Bold")
        self.assertNotEqual((ch["pair"] or {}).get("arabic"), "Alexandria")
        if ch["pair"] is not None:                                 # a Latin measured against Brand Ar, at its scale
            want = font_pairing.measure_pair({"file": str(brand)}, {"file": ch["latin"][0]["file"]}, 700)["latin_scale"]
            self.assertEqual(first_latin(ch)[1], round(want, 4))


def LT_locate(face):
    """The hook's locate function, wherever the looks track keeps it (looks_type or looks_pairing)."""
    mod = LT
    if not hasattr(LT, "_pair_locate"):
        from lib import looks_pairing as mod  # noqa: N813
    return mod._pair_locate(face)


class TestTypesetterScale(unittest.TestCase):
    def test_a_scaled_latin_face_is_drawn_at_size_times_scale(self):
        plain = face(INTER, "Inter-Regular", "Inter", "Regular", 400)
        chain = {"arabic": HOUSE["arabic"], "latin": [plain]}
        scaled = {"arabic": HOUSE["arabic"], "latin": [dict(plain, scale=0.8)]}
        w1 = LT.Typesetter(chain, 60).word("insulin")["w"]
        w2 = LT.Typesetter(scaled, 60).word("insulin")["w"]
        self.assertAlmostEqual(w2 / w1, 0.8, places=2)
        a1 = LT.Typesetter(chain, 60).word("عندي")["w"]
        a2 = LT.Typesetter(scaled, 60).word("عندي")["w"]
        self.assertEqual(a1, a2)                                   # Arabic runs keep their size


if __name__ == "__main__":
    unittest.main()
