# SPDX-License-Identifier: GPL-3.0-or-later
# © 2026 The Why Not AI (thewhynot.ai)
"""Platform safe-zone profiles (Phase 4 Task 27, R-4.5): loader, scaling, violations, caption width.
Spec: docs/superpowers/specs/addendum-h/source-r-specs/R-4.5-safe-zone-profiles.md. Case list: C01-C41.
Run:  tools/test.sh -p test_safe_zones.py
"""
import sys as _sys
_sys.dont_write_bytecode = True  # keep the plugin folder free of __pycache__
import _isolation  # noqa: F401,E402  G79: sandbox the engine home before anything else (see tests/_isolation.py)
import json
import re
import tempfile
import unittest
from pathlib import Path

SK = Path(__file__).resolve().parents[1]
if str(SK / "engine" / "reel") not in _sys.path:
    _sys.path.insert(0, str(SK / "engine" / "reel"))

from lib import safe_zones as SZ  # noqa: E402

FILE = SK / "config" / "defaults" / "safe-zones.json"
NAMES = ["ig_reels_organic", "ig_reels_ads", "ig_reels_ads_disclaimer", "tiktok", "yt_shorts", "feed_4x5"]
FRAMES = [(1080, 1920), (720, 1280), (2160, 3840), (1080, 1350)]
BASES = {"official", "template", "screenshot", "community"}
DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def raw():
    return json.loads(FILE.read_text(encoding="utf-8"))


def write(d, text=None, name="safe-zones.json", sub="x"):
    tmp = Path(tempfile.mkdtemp()) / sub
    tmp.mkdir(parents=True, exist_ok=True)
    p = tmp / name
    if text is not None:
        p.write_bytes(text if isinstance(text, bytes) else text.encode("utf-8"))
    else:
        p.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
    return p


def inter(a, b):
    return min(a[2], b[2]) > max(a[0], b[0]) and min(a[3], b[3]) > max(a[1], b[1])


class Shipped(unittest.TestCase):
    def test_c01_all_profiles_load_and_default(self):
        for n in NAMES:
            p = SZ.load(n)
            self.assertEqual(p.name, n)
            self.assertFalse(p.fallback, n)
            self.assertTrue(p.zones, n)
        self.assertEqual(SZ.load().name, "ig_reels_organic")

    def test_c02_every_number_has_source_date_basis(self):
        d = raw()
        self.assertEqual(set(d["profiles"]), set(NAMES))
        for n, pr in d["profiles"].items():
            for z in pr["zones"]:
                for k in ("basis", "source", "retrieved"):
                    self.assertTrue(z.get(k), f"{n}/{z['name']} {k}")
                self.assertIn(z["basis"], BASES)
                self.assertTrue(z["source"].startswith("https://"))
                self.assertRegex(z["retrieved"], DATE)
            e = pr.get("encode")
            if e:
                self.assertIn(e["basis"], BASES)
                self.assertTrue(e["source"].startswith("https://"))
                self.assertRegex(e["retrieved"], DATE)

    def test_c02b_encode_blocks_where_the_platform_publishes(self):
        for n in ("ig_reels_organic", "ig_reels_ads", "ig_reels_ads_disclaimer", "tiktok"):
            self.assertTrue(SZ.load(n).encode, n)
        # never a guessed number: nothing the platforms do not publish
        for n in NAMES:
            e = SZ.load(n).encode or {}
            for k in ("loudness_lufs", "true_peak_dbtp", "gop_s", "level_max", "profile"):
                self.assertNotIn(k, e, f"{n} {k} is not published by the platform")

    def test_c11_community_flagged(self):
        self.assertTrue(SZ.load("yt_shorts").flags)
        self.assertFalse(SZ.load("ig_reels_ads").flags)

    def test_c24_meta_percentages(self):
        p = SZ.load("ig_reels_ads")
        z = {x.name: x.rect for x in p.zones}
        self.assertEqual(z["top_ui"][3], 269)
        self.assertEqual(z["bottom_ui"][1], 1248)
        self.assertEqual(z["left_margin"][2], 65)
        self.assertEqual(z["right_margin"][0], 1015)
        q = SZ.load("ig_reels_ads", frame=(1440, 2560))
        z = {x.name: x.rect for x in q.zones}
        self.assertEqual((z["top_ui"][3], z["bottom_ui"][1], z["left_margin"][2]), (359, 1664, 87))
        self.assertEqual(SZ.load("ig_reels_ads_disclaimer").zones[1].rect[1], 1152)


class Scaling(unittest.TestCase):
    def test_c20_every_profile_every_frame(self):
        for n in NAMES:
            for fr in FRAMES:
                p = SZ.load(n, frame=fr)
                self.assertEqual(tuple(p.frame), fr)
                W, H = fr
                for z in p.zones:
                    x0, y0, x1, y1 = z.rect
                    self.assertTrue(0 <= x0 <= x1 <= W and 0 <= y0 <= y1 <= H, (n, fr, z.name, z.rect))
                    self.assertFalse(inter(z.rect, p.safe_text), (n, fr, z.name))
                sx0, sy0, sx1, sy1 = p.safe_text
                self.assertTrue(0 <= sx0 < sx1 <= W and 0 <= sy0 < sy1 <= H)
                cb = p.caption_band
                self.assertTrue(sx0 <= cb[0] and cb[2] <= sx1 and sy0 <= cb[1] and cb[3] <= sy1, (n, fr))

    def test_c21_identity(self):
        d = raw()["profiles"]
        for n in NAMES:
            p = SZ.load(n, frame=tuple(d[n]["frame"]))
            self.assertEqual([list(z.rect) for z in p.zones], [z["rect"] for z in d[n]["zones"]])
            self.assertEqual(list(p.safe_text), d[n]["safe_text"])

    def test_c22_exact_double_and_round_toward_safety(self):
        a, b = SZ.load("tiktok"), SZ.load("tiktok", frame=(2160, 3840))
        for za, zb in zip(a.zones, b.zones):
            self.assertEqual(tuple(2 * v for v in za.rect), zb.rect)
        # 65 px at 1080 -> 43.33 at 720: the zone edge rounds up and the safe text edge rounds up too (both toward safety)
        p = SZ.load("ig_reels_ads", frame=(720, 1280))
        z = {x.name: x.rect for x in p.zones}
        self.assertEqual(z["left_margin"][2], 44)
        self.assertEqual(p.safe_text[0], 44)
        self.assertEqual(z["right_margin"][0], 676)       # 1015*2/3 = 676.67 -> floor 676
        self.assertEqual(p.safe_text[2], 676)

    def test_c23_aspect_mismatch_and_bad_frames(self):
        self.assertTrue(SZ.load("ig_reels_ads", frame=(1080, 1350)).aspect_mismatch)
        self.assertFalse(SZ.load("ig_reels_ads", frame=(720, 1280)).aspect_mismatch)
        for bad in [(0, 0), (-1, 100), (float("nan"), 10), ("a", "b"), None, (1,), (1080, 1920, 3)]:
            p = SZ.load("tiktok", frame=bad)
            self.assertEqual(tuple(p.frame), (1080, 1920), bad)   # ignored, never raises


class Loader(unittest.TestCase):
    def mutate(self, fn):
        d = raw()
        fn(d)
        return write(d)

    def refused(self, fn, word=None):
        p = self.mutate(fn)
        with self.assertRaises(SZ.SafeZoneError) as cm:
            SZ.read_profiles(p, strict=True)
        if word:
            self.assertIn(word, str(cm.exception))

    def test_c03_no_source_refused(self):
        self.refused(lambda d: d["profiles"]["tiktok"]["zones"][0].pop("source"), "tiktok")
        self.refused(lambda d: d["profiles"]["tiktok"]["zones"][1].update(source=""), "left_margin")
        self.refused(lambda d: d["profiles"]["tiktok"]["zones"][0].update(source="trust me"))

    def test_c04_basis_and_date(self):
        self.refused(lambda d: d["profiles"]["yt_shorts"]["zones"][0].pop("basis"))
        self.refused(lambda d: d["profiles"]["yt_shorts"]["zones"][0].update(basis="guess"))
        self.refused(lambda d: d["profiles"]["yt_shorts"]["zones"][0].update(retrieved="2026-13-40"))
        self.refused(lambda d: d["profiles"]["yt_shorts"]["zones"][0].update(retrieved="17/10/2026"))
        self.refused(lambda d: d["profiles"]["yt_shorts"]["zones"][0].update(retrieved="2999-01-01"))

    def test_c05_bad_rects(self):
        for bad in ([0, 0, 10], ["a", 0, 1, 1], [10, 0, 5, 5], [0, 0, 5000, 5], [True, 0, 5, 5], [0, 0, float("nan"), 5]):
            self.refused(lambda d, b=bad: d["profiles"]["tiktok"]["zones"][0].update(rect=b))
        self.refused(lambda d: d["profiles"]["tiktok"].update(safe_text=[0, 0, 10]))
        self.refused(lambda d: d["profiles"]["tiktok"].update(frame=[0, 10]))

    def test_c06_encode_block_rules(self):
        self.refused(lambda d: d["profiles"]["tiktok"]["encode"].pop("source"))
        self.refused(lambda d: d["profiles"]["tiktok"]["encode"].pop("retrieved"))
        self.refused(lambda d: d["profiles"]["tiktok"]["encode"].update(made_up_key=1))

    def test_c07_damaged_files_fall_back(self):
        cases = {"missing": None, "empty": b"", "notjson": b"{{{", "array": b"[1,2]", "truncated": FILE.read_bytes()[:500],
                 "nul": b"\x00\x00\x00", "null": b"null"}
        for k, v in cases.items():
            p = Path(tempfile.mkdtemp()) / "safe-zones.json" if v is None else write(None, v)
            pr = SZ.load("tiktok", path=p)
            self.assertTrue(pr.fallback, k)
            self.assertTrue(pr.fallback_reason, k)
            self.assertEqual(pr.safe_text, (90, 250, 990, 1500), k)    # today's subtitle-style safe_area, 1080x1920

    def test_c07b_bom_and_crlf_load(self):
        text = "\ufeff" + FILE.read_text(encoding="utf-8").replace("\n", "\r\n")
        pr = SZ.load("tiktok", path=write(None, text.encode("utf-8")))
        self.assertFalse(pr.fallback)

    def test_c08_partial_file(self):
        def brk(d):
            d["profiles"]["tiktok"]["zones"][0].pop("source")
        p = self.mutate(brk)
        profs, default, reasons = SZ.read_profiles(p, strict=False)
        self.assertNotIn("tiktok", profs)
        self.assertIn("yt_shorts", profs)
        self.assertTrue(any("tiktok" in r for r in reasons))
        pr = SZ.load("tiktok", path=p)                 # the broken one asked for: default profile, with the reason
        self.assertEqual(pr.name, "ig_reels_organic")
        self.assertTrue(pr.fallback_reason)
        self.assertEqual(SZ.load("yt_shorts", path=p).name, "yt_shorts")

        def baddef(d):
            d["default"] = "nope"
        pr = SZ.load(path=self.mutate(baddef))
        self.assertTrue(pr.name in NAMES and pr.fallback_reason)

    def test_c09_unknown_platform_names(self):
        for n in ["", "Instagram", "tiktok_", "../x", "ig reels", None, 5, "x" * 500]:
            pr = SZ.load(n) if n is not None else SZ.load()
            self.assertEqual(pr.name, "ig_reels_organic", n)
        self.assertTrue(SZ.load("Instagram").fallback_reason)
        self.assertEqual(SZ.load("TikTok").name, "tiktok")
        self.assertEqual(SZ.load(" YT_SHORTS ").name, "yt_shorts")

    def test_c10_selection_order(self):
        self.assertEqual(SZ.load("tiktok", client_default="yt_shorts").name, "tiktok")
        self.assertEqual(SZ.load(None, client_default="yt_shorts").name, "yt_shorts")
        self.assertEqual(SZ.load("nonsense", client_default="yt_shorts").name, "yt_shorts")
        self.assertEqual(SZ.load("nonsense", client_default="also-nonsense").name, "ig_reels_organic")

    def test_c12_paths(self):
        for sub in ["مجلد عربي", "with space", "a b\u00e9"]:
            p = write(None, FILE.read_bytes(), sub=sub)
            self.assertFalse(SZ.load("tiktok", path=p).fallback)
            self.assertFalse(SZ.load("tiktok", path=str(p)).fallback)
        for s in ["/Users/x/Library/Application Support/WhyNot Cut/safe-zones.json", "C:\\nope\\safe-zones.json",
                  "~/x.json"]:      # no network share here: a UNC read can stall for seconds on a dead server
            self.assertTrue(SZ.load("tiktok", path=s).fallback, s)


class Violations(unittest.TestCase):
    def box(self, rect, kind="text", id_="b", label="العنوان"):
        return {"id": id_, "kind": kind, "rect": list(rect), "label": label}

    def test_c30_seeded_box_in_every_zone(self):
        for n in NAMES:
            p = SZ.load(n)
            for z in p.zones:
                x0, y0, x1, y1 = z.rect
                cx, cy = (x0 + x1) // 2, (y0 + y1) // 2
                v = SZ.violations([self.box((cx - 2, cy - 2, cx + 2, cy + 2))], p)
                self.assertTrue(any(f["zone"] == z.name and f["severity"] == "P1" for f in v), (n, z.name))
                self.assertTrue(all(f["overlap_px"] > 0 for f in v))
            sx0, sy0, sx1, sy1 = p.safe_text
            ok = self.box((sx0, sy0, sx0 + 40, sy0 + 40))
            self.assertEqual(SZ.violations([ok], p), [], n)

    def test_c31_off_by_one_all_four_sides(self):
        p = SZ.load("ig_reels_ads")
        # top band ends at y=269 (exclusive): a box starting at y=269 is clean, y=268 overlaps by 1 px
        self.assertEqual(SZ.violations([self.box((300, 269, 400, 400))], p), [])
        v = SZ.violations([self.box((300, 268, 400, 400))], p)
        self.assertEqual((len(v), v[0]["overlap_h"], v[0]["zone"]), (1, 1, "top_ui"))
        # bottom band starts at y=1248: a box ending at y=1248 is clean, 1249 overlaps by 1
        self.assertEqual(SZ.violations([self.box((300, 1000, 400, 1248))], p), [])
        v = SZ.violations([self.box((300, 1000, 400, 1249))], p)
        self.assertEqual((len(v), v[0]["overlap_h"]), (1, 1))
        # left margin ends at x=65, right margin starts at x=1015
        self.assertEqual(SZ.violations([self.box((65, 400, 200, 500))], p), [])
        self.assertEqual(SZ.violations([self.box((64, 400, 200, 500))], p)[0]["overlap_w"], 1)
        self.assertEqual(SZ.violations([self.box((900, 400, 1015, 500))], p), [])
        self.assertEqual(SZ.violations([self.box((900, 400, 1016, 500))], p)[0]["overlap_w"], 1)

    def test_c32_severity(self):
        p = SZ.load("ig_reels_ads")
        # decorative 100x100 box, 10 px into the top band = 10% -> P2; text with the same overlap -> P1
        shape = self.box((300, 259, 400, 359), kind="shape")
        text = self.box((300, 259, 400, 359), kind="text")
        self.assertEqual(SZ.violations([shape], p)[0]["severity"], "P2")
        self.assertEqual(SZ.violations([text], p)[0]["severity"], "P1")
        big = self.box((300, 169, 400, 369), kind="shape")      # 100 of 200 px tall inside = 50%
        self.assertEqual(SZ.violations([big], p)[0]["severity"], "P1")
        edge = self.box((300, 249, 400, 349), kind="shape")     # 20 px of 100 = 20% -> P1 (only under 20% is P2)
        self.assertEqual(SZ.violations([edge], p)[0]["severity"], "P1")

    def test_c33_rtl_caption_vs_rail(self):
        p = SZ.load("tiktok")
        right = self.box((860, 800, 950, 880), label="الترجمة")
        left = self.box((140, 800, 300, 880), label="الترجمة")
        v = SZ.violations([right], p)
        self.assertEqual(v[0]["zone"], "right_rail")
        self.assertIn("على اليمين", v[0]["text"])
        self.assertIn("تيك توك", v[0]["text"])
        self.assertEqual(SZ.violations([left], p), [])
        r = SZ.load("tiktok", rtl=True)
        self.assertEqual(SZ.violations([right], r), [])
        v = SZ.violations([self.box((10, 800, 100, 880), label="الترجمة")], r)
        self.assertEqual(v[0]["zone"], "right_rail")
        self.assertIn("على اليسار", v[0]["text"])
        self.assertEqual(r.safe_text, (240, 252, 960, 906))
        self.assertEqual(r.mirrored().zones, p.zones)          # mirrored twice is the original

    def test_c34_face_envelope(self):
        p = SZ.load("tiktok")
        face = (400, 500, 600, 700)
        b = self.box((450, 600, 700, 650))
        v = SZ.violations([b], p, face=face)
        self.assertEqual([f["kind"] for f in v], ["face"])
        self.assertIn("الوجه", v[0]["text"])
        self.assertEqual(SZ.violations([b], p), [])
        for bad in [(0, 0, 0, 0), (5, 5, 1, 1), None, "x", (1, 2, 3)]:
            self.assertEqual(SZ.violations([b], p, face=bad), [])
        self.assertEqual(SZ.violations([self.box((200, 300, 350, 400))], p, face=face), [])

    def test_c35_bad_boxes_never_raise(self):
        p = SZ.load("tiktok")
        junk = [None, 5, {}, {"rect": None}, {"rect": [1, 2, 3]}, {"rect": ["a", 0, 1, 1]}, {"rect": [0, 0, 0, 0]},
                {"rect": [100, 100, 10, 10]}, {"rect": [-500, -500, -400, -400]}, {"rect": [0, 0, 10 ** 9, 10 ** 9]},
                {"rect": [float("nan")] * 4}, {"id": "ok", "kind": "text", "rect": [140, 800, 300, 880]}]
        v = SZ.violations(junk, p)
        self.assertTrue(v)                               # the huge box still hits zones
        self.assertEqual({f["box"] for f in v}, {"box-9"})   # unnamed boxes get "box-<index>"; every bad one is skipped
        self.assertEqual(SZ.violations(None, p), [])
        self.assertEqual(SZ.violations([], p), [])
        self.assertEqual(SZ.violations([self.box((0, 0, 10, 10))], None), [])

    def test_c36_union(self):
        u = SZ.union(["ig_reels_ads", "tiktok"])
        self.assertEqual({z.platform for z in u.zones}, {"ig_reels_ads", "tiktok"})
        a = SZ.load("ig_reels_ads")
        self.assertEqual(u.safe_text, (120, 269, 840, 906))
        box = self.box((850, 800, 1000, 850))   # clean for the ads profile, in the tiktok rail
        self.assertEqual(SZ.violations([box], a), [])
        v = SZ.violations([box], u)
        self.assertEqual({f["platform"] for f in v}, {"tiktok"})
        self.assertEqual(SZ.union([]).name, "ig_reels_organic")
        self.assertEqual(SZ.union(["nonsense"]).name, "ig_reels_organic")

    def test_c37_plain_words(self):
        for n in NAMES:
            p = SZ.load(n)
            x0, y0, x1, y1 = p.zones[0].rect
            fs = SZ.violations([self.box((x0, y0, x0 + 5, y0 + 5))], p)
            self.assertTrue(fs, n)
            for f in fs:
                self.assertRegex(f["text"], r"[\u0600-\u06FF]")
                for bad in ("rect", "basis", "profile", "zone", "None", "{", "_"):
                    self.assertNotIn(bad, f["text"], n)

    def test_c11b_community_in_text(self):
        p = SZ.load("yt_shorts")
        f = SZ.violations([self.box((10, 10, 20, 20))], p)[0]
        self.assertTrue(f["community"])
        self.assertIn("تقدير", f["text"])
        self.assertFalse(SZ.violations([self.box((10, 10, 20, 20))], SZ.load("ig_reels_ads"))[0]["community"])

    def test_c38_deterministic_order(self):
        p = SZ.load("tiktok")
        bs = [self.box((850, 800, 900, 850), id_="b2"), self.box((0, 0, 20, 20), id_="b1")]
        v1, v2 = SZ.violations(bs, p), SZ.violations(bs, p)
        self.assertEqual(v1, v2)
        self.assertEqual(v1[0]["box"], "b2")


class Caption(unittest.TestCase):
    def test_c40_safe_width(self):
        p = SZ.load("tiktok")
        self.assertEqual(SZ.safe_width(p, 0), 720)
        self.assertEqual(SZ.safe_width(p, 20), 680)
        self.assertEqual(SZ.safe_width(p, 10 ** 6), 0)
        self.assertEqual(SZ.safe_width(p, -5), 720)
        self.assertEqual(SZ.safe_width(p, "x"), 720)
        self.assertEqual(SZ.safe_width(SZ.load("tiktok", frame=(2160, 3840)), 0), 1440)

    def test_c41_legacy_defaults_untouched(self):
        self.assertEqual(SZ.legacy_safe_area(), {"left": 90, "right": 90, "top": 250, "bottom": 420})
        self.assertEqual(SZ.legacy_safe_top_px(), 220)
        self.assertEqual(SZ.legacy_safe_top_px(1280), 220 * 1280 / 1920)
        sub = json.loads((SK / "config" / "defaults" / "subtitle-style.json").read_text(encoding="utf-8"))["safe_area"]
        for k, v in SZ.legacy_safe_area().items():
            self.assertEqual(sub[k], v)


class Hooks(unittest.TestCase):
    """The helpers qc.py / previews.py call (the patches live in the executor's hand-over folder)."""

    def box(self, rect, kind="text", id_="g1"):
        return {"id": id_, "kind": kind, "rect": list(rect)}

    def test_c60_no_platform_chosen_adds_nothing(self):
        for none in (None, [], (), ""):
            self.assertEqual(SZ.qc_items([self.box((0, 0, 10, 10))], none, (1080, 1920)), [])

    def test_c60_seeded_graphic_in_each_profiles_zone(self):
        for n in NAMES:
            p = SZ.load(n)
            zone = next((z for z in p.zones if z.kind in ("bottom", "rail")), p.zones[0])   # feed_4x5: sides only (nothing else published)
            x0, y0, x1, y1 = zone.rect
            items = SZ.qc_items([self.box(((x0 + x1) // 2 - 5, (y0 + y1) // 2 - 5, (x0 + x1) // 2 + 5, (y0 + y1) // 2 + 5))], [n], p.frame)
            bad = [i for i in items if not i["ok"]]
            self.assertEqual(len(bad), 1, n)
            self.assertIn("P1", bad[0]["name"])
            self.assertIn("داخل", bad[0]["detail"])
            clean = SZ.qc_items([self.box(p.safe_text[:2] + (p.safe_text[0] + 30, p.safe_text[1] + 30))], [n], p.frame)
            self.assertTrue(clean and all(i["ok"] for i in clean), n)

    def test_c60_decorative_is_p2_and_union_checks_every_target(self):
        deco = self.box((300, 259, 400, 359), kind="shape")
        items = SZ.qc_items([deco], ["ig_reels_ads"], (1080, 1920))
        self.assertEqual([i["name"] for i in items if not i["ok"]], ["Graphics clear of platform app areas (P2: decorative)"])
        both = SZ.qc_items([self.box((850, 800, 1000, 850))], ["ig_reels_ads", "tiktok"], (1080, 1920))
        self.assertTrue(any(not i["ok"] and "تيك توك" in i["detail"] for i in both))
        self.assertTrue(SZ.qc_items([self.box((850, 800, 1000, 850))], ["ig_reels_ads"], (1080, 1920))[0]["ok"])

    def test_c60_other_frame_size_and_garbage(self):
        # 720x1280: a box inside the scaled tiktok rail is flagged, junk never raises
        p = SZ.load("tiktok", frame=(720, 1280))
        r = [z for z in p.zones if z.kind == "rail"][0].rect
        items = SZ.qc_items([self.box((r[0] + 5, r[1] + 5, r[0] + 40, r[1] + 40)), None, {"rect": "x"}], ["tiktok"], (720, 1280))
        self.assertEqual(len([i for i in items if not i["ok"]]), 1)
        self.assertIsInstance(SZ.qc_items("junk", ["tiktok"], (720, 1280)), list)
        self.assertIsInstance(SZ.qc_items([self.box((0, 0, 5, 5))], ["nonsense"], (720, 1280)), list)

    def test_c61_preview_helpers_default_is_todays_numbers(self):
        self.assertEqual(SZ.safe_area_for(None), {"left": 90, "right": 90, "top": 250, "bottom": 420})
        self.assertEqual(SZ.safe_top_px_for(None, (1080, 1920)), 220)
        self.assertEqual(SZ.safe_top_px_for("", (720, 1280)), 220)            # no profile chosen: previews.SAFE_TOP_PX unscaled
        self.assertEqual(SZ.safe_area_for("tiktok"), {"left": 120, "right": 240, "top": 252, "bottom": 1014})
        self.assertEqual(SZ.safe_top_px_for("tiktok", (1080, 1920)), 252)
        s = SZ.load("tiktok", frame=(720, 1280)).safe_text
        self.assertEqual(SZ.safe_area_for("tiktok", (720, 1280)), {"left": s[0], "right": 720 - s[2], "top": s[1], "bottom": 1280 - s[3]})
        bad = write(None, b"{{{")
        self.assertEqual(SZ.safe_top_px_for("tiktok", (1080, 1920), path=bad), 220)     # file unreadable: today's number
        self.assertEqual(SZ.safe_area_for("tiktok", path=bad), {"left": 90, "right": 90, "top": 250, "bottom": 420})
        self.assertEqual(SZ.safe_top_px_for("nonsense", (1080, 1920)), 220)             # unknown name: today's number, never a silent move


class Review1(unittest.TestCase):
    """Independent review round 1: what the first reviewer found missing."""

    def box(self, rect, kind="text", id_="b"):
        return {"id": id_, "kind": kind, "rect": list(rect), "label": "العنوان"}

    def test_yt_rail_rounds_toward_safety(self):
        z = {x.name: x.rect for x in SZ.load("yt_shorts").zones}
        self.assertEqual(z["right_rail"][0], 1080 - 193)           # 17.8% of 1080 = 192.24 -> 193 px
        self.assertEqual(SZ.load("yt_shorts").safe_text[2], 887)

    def test_unmeasured_rail_is_stated_not_silent(self):
        for n in ("ig_reels_organic", "ig_reels_ads", "ig_reels_ads_disclaimer"):
            p = SZ.load(n)
            self.assertTrue(any("غير" in g or "لم" in g or "لا يوجد" in g for g in p.gaps), n)
            items = SZ.qc_items([self.box((p.safe_text[0] + 5, p.safe_text[1] + 5, p.safe_text[0] + 40, p.safe_text[1] + 40))], [n], p.frame)
            self.assertTrue(items[0]["ok"])
            self.assertIn("لم تُقَس", items[0]["detail"])
        self.assertEqual(SZ.load("tiktok").gaps, ())

    def test_half_pixel_rounds_the_safe_way(self):
        d = {"format": 1, "default": "t", "profiles": {"t": {
            "frame": [2, 2], "safe_text": [1, 1, 2, 2], "caption_band": [1, 1, 2, 2],
            "zones": [{"name": "z", "kind": "side", "rect": [0, 0, 1, 1], "basis": "official", "source": "https://example.test/a",
                       "retrieved": "2026-10-17"}]}}}
        p = SZ.load("t", path=write(d), frame=(3, 3))
        self.assertEqual(p.zones[0].rect, (0, 0, 2, 2))           # 1.5 -> ceil: the zone grows
        self.assertEqual(p.safe_text, (2, 2, 3, 3))               # 1.5 -> ceil: the safe text shrinks (from 1.5 to 2)
        d["profiles"]["t"]["zones"][0]["rect"] = [1, 1, 2, 2]
        d["profiles"]["t"]["safe_text"] = [0, 0, 1, 1]
        d["profiles"]["t"]["caption_band"] = [0, 0, 1, 1]
        p = SZ.load("t", path=write(d), frame=(3, 3))
        self.assertEqual(p.zones[0].rect, (1, 1, 3, 3))           # x0 1.5 -> floor 1, x1 3.0
        self.assertEqual(p.safe_text, (0, 0, 1, 1))               # x1 1.5 -> floor 1

    def test_decorative_kind_and_box_level_severity(self):
        p = SZ.load("ig_reels_ads")
        self.assertEqual(SZ.violations([self.box((300, 259, 400, 359), kind="decorative")], p)[0]["severity"], "P2")
        # a shape in the top-left corner: 15% in the top band and 15% in the left margin (30% in total) is P1
        corner = self.box((55, 254, 155, 354), kind="shape")      # 100x100: top band 15 rows, left margin 10 cols
        v = SZ.violations([corner], p)
        self.assertEqual({f["zone"] for f in v}, {"top_ui", "left_margin"})
        self.assertEqual({f["severity"] for f in v}, {"P1"})       # 15*100 + 10*100 - overlap of the two = 24% -> P1
        small = self.box((60, 264, 160, 364), kind="shape")        # 5 rows + 5 cols = 9.75% -> P2
        self.assertEqual({f["severity"] for f in SZ.violations([small], p)}, {"P2"})

    def test_encode_value_types_are_refused(self):
        for key, bad in [("codec", 5), ("codec", []), ("container", 5), ("closed_gop", "yes"), ("bitrate_kbps_min", "x"),
                         ("bitrate_kbps_min", True), ("pix_fmt", 7), ("fps_max", float("nan"))]:
            def f(d, k=key, b=bad):
                d["profiles"]["tiktok"]["encode"][k] = b
            p = write(None, json.dumps(self.mut(f)))
            with self.assertRaises(SZ.SafeZoneError, msg=(key, bad)):
                SZ.read_profiles(p, strict=True)
            self.assertNotIn("tiktok", SZ.read_profiles(p)[0])

    def mut(self, fn):
        d = raw()
        fn(d)
        return d

    def test_deeply_nested_file_falls_back(self):
        pr = SZ.load("tiktok", path=write(None, b"[" * 200000))
        self.assertTrue(pr.fallback)

    def test_union_with_unknown_platform_says_so(self):
        u = SZ.union(["tiktok", "tiktoc"])
        self.assertEqual(u.name, "tiktok")
        self.assertIn("tiktoc", u.fallback_reason)
        items = SZ.qc_items([self.box((140, 800, 300, 880))], ["tiktoc"], (1080, 1920))
        self.assertTrue(any(not i["ok"] and "tiktoc" in i["detail"] for i in items))
        items = SZ.qc_items([self.box((140, 800, 300, 880))], ["tiktok", "tiktoc"], (1080, 1920))
        self.assertTrue(any(not i["ok"] and "tiktoc" in i["detail"] for i in items))

    def test_safe_area_for_a_list_is_the_union(self):
        a = SZ.safe_area_for(["ig_reels_ads", "tiktok"])
        self.assertEqual(a, {"left": 120, "right": 240, "top": 269, "bottom": 1014})

    def test_c37_every_zone_every_profile_plain_words(self):
        for n in NAMES:
            p = SZ.load(n)
            for z in p.zones:
                x0, y0, x1, y1 = z.rect
                for f in SZ.violations([self.box((x0, y0, min(x1, x0 + 6), min(y1, y0 + 6)))], p):
                    for bad in ("rect", "basis", "profile", "zone", "None", "{", "_", "community", "official"):
                        self.assertNotIn(bad, f["text"], (n, z.name))


class Review2(unittest.TestCase):
    def test_unhashable_default_falls_back(self):
        for bad in ([], {}, 5, None):
            d = raw()
            d["default"] = bad
            self.assertFalse(SZ.load(path=write(d)).fallback)

    def test_unknown_name_never_moves_margins_silently(self):
        self.assertEqual(SZ.safe_area_for("tiktoc"), SZ.legacy_safe_area())
        self.assertEqual(SZ.safe_area_for(["tiktoc"]), SZ.legacy_safe_area())
        self.assertEqual(SZ.safe_area_for(["tiktok", "tiktoc"])["top"], 252)       # one good name: the known ones are used
        self.assertEqual(SZ.safe_top_px_for("tiktoc", (1080, 1920)), 220)
        self.assertEqual(SZ.safe_area_for("tiktok")["top"], 252)

    def test_gaps_shown_on_findings_too(self):
        p = SZ.load("ig_reels_organic")
        items = SZ.qc_items([{"id": "a", "kind": "text", "rect": [10, 10, 50, 50]}], ["ig_reels_organic"], p.frame)
        bad = [i for i in items if not i["ok"]]
        self.assertTrue(bad and all("لم تُقَس" in i["detail"] for i in bad))


if __name__ == "__main__":
    unittest.main()
