# SPDX-License-Identifier: GPL-3.0-or-later
# © 2026 The Why Not AI (thewhynot.ai)
"""3.0 Phase 4 Task 64 (Addendum K1, K-T4) — `reel safezone-check`: Task 27's platform safe zones over the graphic and
caption stills, the intruding element ids printed, and an exit code (0 clean, 1 an intrusion, 2 could not check);
`reel qc` treats an intrusion as a hard failure only behind its switch. Task 27's own detection tests are reused, not
copied: this file tests the wrapper.
Run:  bash tools/test.sh -p test_safety_safezone_gate.py
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

from lib import common  # noqa: E402
from lib import safe_zones  # noqa: E402
from lib.common import Paths, write_json  # noqa: E402
from lib.safety import safezone_gate as G, switches  # noqa: E402


class Project(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="kt4_"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.addCleanup(common.set_context, None)
        self.root = self.tmp / "د. تجربة Dr Test"
        for d in ("assets", "data/Raw"):
            (self.root / d).mkdir(parents=True)
        (self.root / ".whynot-client").write_text("{}", encoding="utf-8")
        self.p = Paths(self.root, "C0001")
        common.set_context(self.root)
        write_json(self.p.p("01_analysis/timeline-spec.json"), {"events": [
            {"event_id": "G1", "template": "glass_card", "start_frame": 0, "end_frame": 50, "params": {"text": "x"}}]})

    def still(self, rel, rect, size=(1080, 1920)):
        from PIL import Image, ImageDraw
        im = Image.new("RGBA", size, (0, 0, 0, 0))
        ImageDraw.Draw(im).rectangle([rect[0], rect[1], rect[2] - 1, rect[3] - 1], fill=(255, 255, 255, 255))
        f = self.p.p(rel)
        f.parent.mkdir(parents=True, exist_ok=True)
        im.save(f)
        return f

    def caption(self, rect, size=(1080, 1920), cid="CAP_001"):
        return self.still(f"03_broll/captions/{cid}_fg.png", rect, size)

    def snapshot(self):
        return {str(f.relative_to(self.root)): f.read_bytes() for f in self.root.rglob("*") if f.is_file()}


class TestSpec(Project):
    def test_intrusion_exits_1_with_ids(self):
        self.caption((200, 1500, 880, 1600))                      # inside IG's bottom UI (1248-1920)
        res = G.check(self.p, ["ig_reels_organic"])
        self.assertEqual(res["exit_code"], G.EXIT_FOUND)
        self.assertEqual(res["ids"], ["CAP_001"])
        self.assertTrue(res["message"].startswith("فيه عناصر"))

    def test_clean_exits_0(self):
        self.caption((200, 1000, 880, 1100))                      # the same caption moved up
        res = G.check(self.p, ["ig_reels_organic"])
        self.assertEqual((res["exit_code"], res["ids"]), (G.EXIT_OK, []))

    def test_profile_per_aspect(self):
        """Every profile on a 9:16 and a 4:5 reel: a profile of the reel's shape is checked (middle clear, the very
        bottom found where the profile has a bottom zone); a profile of another shape is "could not check" (2)."""
        names = list(safe_zones.read_profiles()[0])
        for size in ((1080, 1920), (1080, 1350)):
            self.seq(size)
            for name in names:
                with self.subTest(platform=name, size=size):
                    shutil.rmtree(self.p.p("03_broll"), ignore_errors=True)
                    w, h = size
                    prof = safe_zones.load(name, frame=size)
                    sa = safe_zones.safe_area_for(name, size)
                    cx, cy = (sa["left"] + w - sa["right"]) // 2, (sa["top"] + h - sa["bottom"]) // 2
                    self.caption((cx - 30, cy - 20, cx + 30, cy + 20), size)
                    res = G.check(self.p, [name])
                    if prof.aspect_mismatch:
                        self.assertEqual(res["exit_code"], G.EXIT_ERROR)
                        continue
                    self.assertEqual(res["exit_code"], G.EXIT_OK)
                    self.caption((w // 2 - 100, h - 60, w // 2 + 100, h), size, cid="CAP_002")
                    if any(z.rect[3] >= h and z.rect[1] > 0 for z in prof.zones):
                        self.assertEqual(G.check(self.p, [name])["exit_code"], G.EXIT_FOUND)
        shutil.rmtree(self.p.p("03_broll"), ignore_errors=True)
        self.caption((300, 600, 780, 700), (1080, 1350))
        self.assertEqual(G.check(self.p)["platforms"], ["feed_4x5"])     # a 4:5 reel with no platform chosen

    def seq(self, size):
        write_json(self.root / common.CLIENT_PROFILE_REL / "sequence-settings.json",
                   {"general": {"frame_width": size[0], "frame_height": size[1]}})

    def test_qc_hard_fail_only_when_switch_on(self):
        self.caption((200, 1500, 880, 1600))
        write_json(self.p.p("01_analysis/edit-decisions.json"), {"global": {"platforms": ["ig_reels_organic"]}})
        self.assertIsNone(G.qc_item(self.p))
        write_json(self.root / common.CLIENT_PROFILE_REL / "safety.json",
                   {"switches": {switches.QC_SAFEZONE_HARD_FAIL: True}})
        item = G.qc_item(self.p)
        self.assertFalse(item["ok"])
        self.assertTrue(item["mandatory"])
        self.assertIn("CAP_001", item["detail"])
        self.caption((200, 1000, 880, 1100))
        self.assertTrue(G.qc_item(self.p)["ok"])


class TestEdges(Project):
    def test_edge_exact_box_is_clear(self):
        self.caption((200, 1148, 880, 1248))                      # ends exactly where IG's bottom UI starts
        self.assertEqual(G.check(self.p, ["ig_reels_organic"])["exit_code"], G.EXIT_OK)
        self.caption((200, 1149, 880, 1249))                      # one pixel in
        self.assertEqual(G.check(self.p, ["ig_reels_organic"])["exit_code"], G.EXIT_FOUND)

    def test_rtl_caption_against_the_right_rail(self):
        self.caption((130, 500, 240, 600))                        # clear in TikTok's left-to-right layout ...
        self.assertEqual(G.check(self.p, ["tiktok"], rtl=False)["exit_code"], G.EXIT_OK)
        res = G.check(self.p, ["tiktok"], rtl=True)               # ... under the rail in its Arabic layout
        self.assertEqual((res["exit_code"], res["ids"]), (G.EXIT_FOUND, ["CAP_001"]))

    def test_rtl_follows_the_transcript(self):
        self.caption((130, 500, 240, 600))
        write_json(self.p.p("02_transcription/words.json"),
                   {"meta": {"scripts": {"rtl_primary": True, "arabic_ratio": 0.9}}, "words": []})
        self.assertEqual(G.check(self.p, ["tiktok"])["exit_code"], G.EXIT_FOUND)

    def test_exit_codes_are_distinct(self):
        res = G.check(self.p, ["ig_reels_organic"])               # nothing to check
        self.assertEqual(res["exit_code"], G.EXIT_ERROR)
        self.assertTrue(res["message"].startswith("مفيش"))
        self.caption((200, 1000, 880, 1100))
        self.assertEqual(G.check(self.p, ["no_such_platform"])["exit_code"], G.EXIT_ERROR)
        self.p.p("03_broll/captions/CAP_002_fg.png").write_bytes(b"not a png")
        self.assertEqual(G.check(self.p, ["ig_reels_organic"])["exit_code"], G.EXIT_ERROR)
        self.assertEqual(len({G.EXIT_OK, G.EXIT_FOUND, G.EXIT_ERROR}), 3)

    def test_graphic_stills_and_full_screen_templates(self):
        self.still(f"03_broll/{common.still_category('glass_card')}/G1.png", (200, 1500, 880, 1600))
        self.assertEqual(G.check(self.p, ["ig_reels_organic"])["ids"], ["G1"])

    def test_writes_nothing_reruns_and_macos(self):
        self.caption((200, 1500, 880, 1600))
        before = self.snapshot()
        a = G.check(self.p, ["ig_reels_organic"])
        with mock.patch.object(sys, "platform", "darwin"):
            b = G.check(self.p, ["ig_reels_organic"])
        self.assertEqual(a, b)
        self.assertEqual(self.snapshot(), before)


# --- review round 1 (independent reviewer, 2026-10-17): I1–I5, M6–M8, M10 --------------------------------------------
class TestReviewRound1(Project):
    def test_i1_any_failure_inside_is_exit_2(self):
        self.caption((200, 1000, 880, 1100))
        with mock.patch.object(G, "_check", side_effect=RuntimeError("boom")):
            res = G.check(self.p, ["ig_reels_organic"])
        self.assertEqual(res["exit_code"], G.EXIT_ERROR)

    def test_i2_damaged_plan_or_box_list_is_exit_2(self):
        self.caption((200, 1000, 880, 1100))
        self.p.p("01_analysis/timeline-spec.json").write_text("{x", encoding="utf-8")
        self.assertEqual(G.check(self.p, ["ig_reels_organic"])["exit_code"], G.EXIT_ERROR)
        self.p.p("01_analysis/timeline-spec.json").unlink()
        self.still(f"03_broll/{common.still_category('glass_card')}/G1.png", (200, 1000, 880, 1100))
        self.assertEqual(G.check(self.p, ["ig_reels_organic"])["exit_code"], G.EXIT_ERROR)   # stills nobody can name
        write_json(self.p.p("01_analysis/timeline-spec.json"), {"events": []})
        f = self.p.p("08_quality_control/frames/boxes.json")
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text("{x", encoding="utf-8")
        self.assertEqual(G.check(self.p, ["ig_reels_organic"])["exit_code"], G.EXIT_ERROR)

    def test_i3_caption_plate_is_checked(self):
        self.caption((300, 600, 700, 700))
        self.still("03_broll/captions/CAP_001_bar.png", (130, 590, 900, 710))   # the plate reaches TikTok's RTL rail
        res = G.check(self.p, ["tiktok"], rtl=True)
        self.assertEqual((res["exit_code"], res["ids"]), (G.EXIT_FOUND, ["CAP_001"]))

    def test_i4_stills_are_scaled_to_the_reel_and_another_shape_is_exit_2(self):
        self.caption((100, 750, 440, 800), (540, 960))                  # a half-size still: y 1500-1600 on the reel
        res = G.check(self.p, ["ig_reels_organic"])
        self.assertEqual((res["exit_code"], res["ids"]), (G.EXIT_FOUND, ["CAP_001"]))
        self.caption((100, 100, 440, 200), (1080, 1080), cid="CAP_009")  # a square still on a 9:16 reel
        self.assertEqual(G.check(self.p, ["ig_reels_organic"])["exit_code"], G.EXIT_ERROR)

    def test_i5_qc_passes_with_nothing_to_check_and_needs_a_chosen_platform(self):
        write_json(self.root / common.CLIENT_PROFILE_REL / "safety.json",
                   {"switches": {switches.QC_SAFEZONE_HARD_FAIL: True}})
        self.assertIsNone(G.qc_item(self.p))                            # no platform chosen: like Task 27, no line
        write_json(self.p.p("01_analysis/edit-decisions.json"), {"global": {"platforms": ["ig_reels_organic"]}})
        item = G.qc_item(self.p)                                        # a talking head with no stills
        self.assertTrue(item["ok"])
        self.assertTrue(item["detail"].startswith("مفيش"))

    def test_m7_one_unknown_platform_among_several_still_reports_the_intrusion(self):
        self.caption((200, 1500, 880, 1600))
        res = G.check(self.p, ["ig_reels_organic", "no_such_platform"])
        self.assertEqual(res["exit_code"], G.EXIT_FOUND)
        self.assertIn("no_such_platform", res["message"])

    def test_m8_rtl_needs_arabic_in_the_transcript(self):
        self.caption((130, 500, 240, 600))
        write_json(self.p.p("02_transcription/words.json"),
                   {"meta": {"scripts": {"rtl_primary": True, "arabic_ratio": 0}}, "words": []})
        self.assertEqual(G.check(self.p, ["tiktok"])["exit_code"], G.EXIT_OK)

    def test_m10_a_wrongly_typed_platform_setting_is_exit_2(self):
        self.caption((200, 1000, 880, 1100))
        write_json(self.p.p("01_analysis/edit-decisions.json"), {"global": {"platforms": {"tiktok": True}}})
        self.assertEqual(G.check(self.p)["exit_code"], G.EXIT_ERROR)


if __name__ == "__main__":
    unittest.main()
