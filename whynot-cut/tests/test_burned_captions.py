# SPDX-License-Identifier: GPL-3.0-or-later
# © 2026 The Why Not AI (thewhynot.ai)
"""Phase 4 Task 24, R-4.2: burned-in caption detection (lib/burned_captions.py).
Spec: docs/superpowers/specs/addendum-h/source-r-specs/R-4.2-burned-in-captions.md. Case list: the lane's
work/t24/cases.md (A-F). Fixtures: tests/fixtures/burned_captions/ (synthetic, made by make_fixtures.py; no client
footage), decoded at 1 fps with the engine's ffmpeg on the CPU (the suite runs with WHYNOT_ACCEL=off).
Measured on the fixtures (the starting thresholds' basis): captions coverage 0.75, Pearson 0.67-0.81 at lag +1 s,
0 s in pauses; the lower-third changes once and holds still 5 s (still share 1.0); the ticker is on screen in every
pause second; the logo never changes; the watermark's contrast is too low to be a band in most frames.
Run:  bash tools/test.sh -p test_burned_captions.py
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

import numpy as np

SK = Path(__file__).resolve().parents[1]
if str(SK / "engine" / "reel") not in _sys.path:
    _sys.path.insert(0, str(SK / "engine" / "reel"))

from lib import burned_captions as BC  # noqa: E402

FX = SK / "tests" / "fixtures" / "burned_captions"
DUR = {"short_2s": 2.0, "cont_bottom": 20.0, "karaoke": 20.0, "long_cues": 20.0, "small_vertical": 20.0,
       "lt_swaps": 20.0, "ticker_cont": 20.0, "short_cont": 8.0}
_CACHE = {}


def words_of(name):
    return json.loads((FX / f"{name}.words.json").read_text(encoding="utf-8"))["words"]


def frames_of(name, thumbs=False):
    """The clip decoder's frames (640x360), or the episode scan's 320x180 thumbnails (thumbs=True)."""
    key = (name, thumbs)
    if key not in _CACHE:
        if thumbs:
            from lib.overlay_scan import decode_thumbs
            _CACHE[key] = decode_thumbs(FX / f"{name}.mp4", 0, DUR.get(name, 12.0))
        else:
            _CACHE[key] = BC.decode_frames(FX / f"{name}.mp4", 0, DUR.get(name, 12.0))
    return _CACHE[key]


def text_frame(y0=150, y1=162, x0=100, x1=220, h=180, w=320, light=True, seed=0):
    """A synthetic frame: a soft gradient with one 'text line' of strokes (short vertical bars with a dark rim)."""
    rnd = np.random.default_rng(seed)
    img = np.zeros((h, w, 3), np.uint8)
    img[...] = np.linspace(60, 120, w, dtype=np.uint8)[None, :, None]
    if y1 > y0:
        img[y0:y1, x0:x1] = 30 if light else 230
        for x in range(x0 + 2, x1 - 2, 4):
            if rnd.random() < 0.85:
                img[y0 + 2:y1 - 2, x:x + 2] = 245 if light else 15
    return img


# --------------------------------------------------------------------------- A. per-frame bands
class TestBands(unittest.TestCase):
    def test_a01_bottom_caption_line(self):
        b = BC.frame_bands(text_frame())
        self.assertEqual(len(b), 1)
        self.assertEqual(b[0]["region"], "bottom")
        self.assertLessEqual(abs(b[0]["y0"] - 150), 2)
        self.assertLessEqual(abs(b[0]["y1"] - 162), 2)

    def test_a02_top_found_middle_not_searched(self):
        self.assertEqual([x["region"] for x in BC.frame_bands(text_frame(10, 22))], ["top"])
        self.assertEqual(BC.frame_bands(text_frame(80, 92)), [])             # 44-51 %: outside both regions (spec)

    def test_a03_two_lines_merge(self):
        img = text_frame(140, 152)
        img[153:165] = text_frame(153, 165, seed=1)[153:165]
        b = BC.frame_bands(img)
        self.assertEqual(len(b), 1)
        self.assertGreaterEqual(b[0]["y1"] - b[0]["y0"], 22)

    def test_a04_dark_text_on_a_light_plate(self):
        self.assertEqual(len(BC.frame_bands(text_frame(light=False))), 1)

    def test_a06_long_edges_and_a07_texture_and_a08_flat_are_not_text(self):
        img = text_frame(0, 0)
        img[120:] = 200                                     # a horizon: one long horizontal edge
        img[:, 160:162] = 10                                # a pole: one vertical edge through every row
        self.assertEqual(BC.frame_bands(img), [])
        noise = np.random.default_rng(5).integers(0, 255, (180, 320, 3), dtype=np.uint8)
        self.assertEqual(BC.frame_bands(noise), [])         # dense everywhere: not a band
        for v in (0, 128, 255):
            self.assertEqual(BC.frame_bands(np.full((180, 320, 3), v, np.uint8)), [])

    def test_a09_too_thin_or_too_thick(self):
        self.assertEqual(BC.frame_bands(text_frame(150, 153)), [])          # 1.7 % of the height
        self.assertEqual(BC.frame_bands(text_frame(105, 175)), [])          # 39 %

    def test_bad_frames_never_raise(self):
        for bad in (None, np.zeros((5, 5, 3), np.uint8), np.zeros((180, 320), np.uint8), "x"):
            self.assertEqual(BC.frame_bands(bad), [])


# --------------------------------------------------------------------------- A05/B/C/D on the fixtures
class TestFixtures(unittest.TestCase):
    def verdict(self, name):
        return BC.detect(frames_of(name), words_of(name))

    def test_acceptance_with_and_without_burned_text(self):
        for name, want in (("en_bottom", "yes"), ("ar_bottom", "yes"), ("en_top", "yes"), ("lower_third", "no"),
                           ("logo", "no"), ("watermark", "no"), ("ticker", "no"), ("clean", "no"), ("black", "no"),
                           ("vfr", "yes")):
            r = self.verdict(name)
            self.assertEqual(r["verdict"], want, (name, r["coverage"], r["regions"]))
            json.dumps(r, allow_nan=False)                                   # C08

    def test_b_why_the_overlays_fail(self):
        lt = self.verdict("lower_third")["regions"]["bottom"]
        self.assertFalse(lt["passes"])
        self.assertLess(lt["changes"], BC.MIN_CHANGES)                         # appears once and holds: no caption
        tk = self.verdict("ticker")["regions"]["bottom"]
        self.assertFalse(tk["passes"])
        self.assertEqual(tk["pause_present"], 1.0)                            # on screen through the pause
        lg = self.verdict("logo")["regions"]["top"]
        self.assertFalse(lg["passes"])
        self.assertIsNone(lg["r"])                                            # never changes: no correlation
        cap = self.verdict("en_bottom")["regions"]["bottom"]
        self.assertTrue(cap["passes"])
        self.assertGreaterEqual(cap["r"], BC.MIN_R)
        self.assertEqual(cap["pause_present"], 0.0)

    def test_c07_output_shape(self):
        r = self.verdict("en_bottom")
        for k in ("verdict", "coverage", "bands", "complete", "sheet"):
            self.assertIn(k, r)
        b = r["bands"][0]
        self.assertTrue(0.75 <= b["y0"] < b["y1"] <= 0.95, b)                 # frame fractions
        self.assertLess(b["from_ms"], b["to_ms"])
        self.assertEqual(self.verdict("en_top")["bands"][0]["y0"] < 0.2, True)

    def test_c05_short_clip(self):
        r = self.verdict("short_2s")
        self.assertEqual(r["verdict"], "maybe")
        self.assertEqual(BC.detect(frames_of("clean")[:2], words_of("short_2s"))["verdict"], "no")

    def test_c06_no_speech(self):
        r = BC.detect(frames_of("en_bottom"), [])
        self.assertEqual((r["verdict"], r["reason"]), ("no", "no speech"))

    def test_d03_gpu_and_cpu_lanes_give_the_same_verdict(self):
        """The decode lane only changes ffmpeg's -hwaccel arguments; fake GPU frames (the CPU frames with decoder
        noise of +-3 levels) give the same verdict. The real NVDEC-vs-CPU comparison is a live check (REPORT)."""
        noisy = np.clip(frames_of("en_bottom").astype(int) + np.random.default_rng(2).integers(-3, 4, frames_of("en_bottom").shape),
                        0, 255).astype(np.uint8)
        self.assertEqual(BC.detect(noisy, words_of("en_bottom"))["verdict"], "yes")
        noisy = np.clip(frames_of("lower_third").astype(int) + np.random.default_rng(3).integers(-3, 4, frames_of("lower_third").shape),
                        0, 255).astype(np.uint8)
        self.assertEqual(BC.detect(noisy, words_of("lower_third"))["verdict"], "no")


# --------------------------------------------------------------------------- B/C units
class TestRhythmAndVerdict(unittest.TestCase):
    def test_b08_pearson_of_a_constant_is_none(self):
        self.assertIsNone(BC.pearson([1, 1, 1, 1], [0, 1, 0, 1]))
        self.assertIsNone(BC.pearson([0, 1], [0, 1]))
        self.assertAlmostEqual(BC.pearson([0, 1, 0, 1], [0, 1, 0, 1]), 1.0)

    def test_c03_thresholds_are_inclusive(self):
        speech = [{"start_ms": k * 1000, "end_ms": k * 1000 + 900} for k in range(20)]
        frames = np.zeros((20, 180, 320, 3), np.uint8)
        for cov, want in ((0.60, "yes"), (0.25, "maybe"), (0.20, "no")):
            ok = {"passes": True, "evidence_pauses": True, "evidence_rhythm": False}
            pres = np.zeros(20, bool)
            pres[:int(round(cov * 20))] = True
            z = np.zeros(20, bool)
            with mock.patch.object(BC, "_region", side_effect=lambda tr, region, p=pres: (
                    p if region == "bottom" else z, z, z, [(150, 162)] * 20, np.full(20, 0.5), 180, z)), \
                    mock.patch.object(BC, "rhythm", side_effect=lambda *a, **k: dict(ok)):
                self.assertEqual(BC.detect(frames, speech)["verdict"], want, cov)

    def test_c04_unfinished_scan_is_maybe(self):
        r = BC.detect(frames_of("clean"), words_of("clean"), complete=False)
        self.assertEqual((r["verdict"], r["complete"]), ("maybe", False))
        r = BC.detect(frames_of("en_bottom"), words_of("en_bottom"), complete=False)
        self.assertEqual(r["verdict"], "maybe")                                # spec: unfinished -> maybe, never a hide

    def test_d05_no_frames(self):
        r = BC.detect(np.zeros((0, 180, 320, 3), np.uint8), words_of("en_bottom"))
        self.assertEqual((r["verdict"], r["complete"], r["reason"]), ("no", False, "no frames"))
        self.assertEqual(BC.detect(None, None)["verdict"], "no")


# --------------------------------------------------------------------------- D. the clip pass
class TestScanClip(unittest.TestCase):
    def test_d01_budget_ends_the_scan_without_an_error(self):
        clock = iter([0.0, 30.0, 31.0, 32.0, 33.0])
        calls = []

        def decode(src, a, b):
            calls.append((a, b))
            return frames_of("clean")[:int(b)]
        r, fr = BC.scan_clip("x.mp4", 180.0, words_of("clean"), decode=decode, clock=lambda: next(clock), chunk_s=60)
        self.assertEqual(calls, [(0.0, 60.0)])
        self.assertFalse(r["complete"])
        self.assertEqual(r["verdict"], "maybe")

    def test_d06_lane_is_passed_never_a_slot_taken(self):
        from lib import gpu_lock
        seen = []
        with mock.patch.object(BC, "decode_frames", side_effect=lambda s, a, b, lane="cpu": seen.append(lane)
                               or frames_of("clean")[:int(b)]), \
                mock.patch.object(gpu_lock, "gpu_slot", side_effect=AssertionError("took a slot")):
            BC.scan_clip("x.mp4", 12.0, words_of("clean"), lane="cuda")
        self.assertEqual(set(seen), {"cuda"})


# --------------------------------------------------------------------------- E. effects
class _Proj(unittest.TestCase):
    def setUp(self):
        from lib.common import Paths
        self.tmp = Path(tempfile.mkdtemp(prefix="whynot-t24-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        (self.tmp / "c" / "assets").mkdir(parents=True)
        (self.tmp / "c" / "data").mkdir()
        self.p = Paths(self.tmp / "c", "V1")
        out = self.p.p("02_transcription")
        out.mkdir(parents=True)
        self.words = words_of("en_bottom")
        (out / "words.json").write_text(json.dumps({"words": self.words}), encoding="utf-8")
        (out / "transcript.json").write_text(json.dumps({"segments": []}), encoding="utf-8")
        (out / "captions-short.srt").write_text("1\n00:00:00,500 --> 00:00:01,000\ntoday\n", encoding="utf-8")


class TestEffects(_Proj):
    def test_e01_e02_policy(self):
        yes, maybe, no = {"verdict": "yes"}, {"verdict": "maybe"}, {"verdict": "no"}
        self.assertEqual(BC.policy(yes), {"hide": True, "notice": BC.NOTICE["ar"]})
        self.assertEqual(BC.policy(yes, language="en")["notice"], BC.NOTICE["en"])
        self.assertEqual(BC.policy(yes, plan_compiled=True), {"hide": False, "notice": BC.ASK["ar"]})   # late result
        self.assertEqual(BC.policy(maybe), {"hide": False, "notice": BC.ASK["ar"]})
        for r in (no, {"verdict": "unknown"}, None, "x"):
            self.assertEqual(BC.policy(r), {"hide": False, "notice": None})

    def test_e06_notice_is_one_line_in_the_spec_words(self):
        self.assertEqual(BC.NOTICE["ar"], "الفيديو فيه ترجمة محروقة في الصورة، فخبّينا الكابشن بتاعنا عشان ميبقاش فيه اتنين. "
                                          "الكلام لسه موجود للقص.")
        for t in list(BC.NOTICE.values()) + list(BC.ASK.values()):
            self.assertNotIn("\n", t)

    def test_e03_running_never_touches_the_words(self):
        out = self.p.p("02_transcription")
        before = {f.name: f.read_bytes() for f in out.iterdir()}
        r = BC.run(self.p, FX / "en_bottom.mp4", 12.0)
        self.assertEqual(r["verdict"], "yes")
        self.assertEqual({f.name: f.read_bytes() for f in out.iterdir()}, before)
        saved = json.loads(self.p.p("01_analysis/burned-in-captions.json").read_text(encoding="utf-8"))
        self.assertEqual(saved["verdict"], "yes")
        self.assertNotIn("_strong", saved)

    def test_e05_contact_sheet(self):
        r = BC.run(self.p, FX / "en_bottom.mp4", 12.0)
        sheet = Path(r["sheet"])
        self.assertTrue(sheet.is_file())
        self.assertEqual(sheet.parent, self.p.p("08_quality_control"))
        from PIL import Image
        with Image.open(sheet) as im:
            self.assertEqual(im.size, (960, 360))                               # 6 tiles, 3 x 2
        clean = BC.run(self.p, FX / "clean.mp4", 12.0, words=words_of("clean"))
        self.assertIsNone(clean["sheet"])

    def test_e04_avoid_zones(self):
        z = BC.avoid_zones(BC.detect(frames_of("en_bottom"), words_of("en_bottom")))
        self.assertTrue(z)
        self.assertEqual((z[0]["rect"][0], z[0]["rect"][2]), (0.0, 1.0))
        self.assertEqual(BC.avoid_zones({"bands": [{"y0": "x"}]}), [])
        self.assertEqual(BC.avoid_zones(None), [])

    def test_e07_never_raises(self):
        r = BC.run(self.p, self.tmp / "missing.mp4", 12.0, decode=lambda *a: (_ for _ in ()).throw(OSError("unreadable")))
        self.assertEqual(r["verdict"], "unknown")
        self.assertIn("OSError", r["error"])
        self.assertEqual(BC.policy(r), {"hide": False, "notice": None})


class TestWiringHelpers(_Proj):
    """The producers the hook patches call (ppro_build hides our caption track; the intake line; the editor's switch)."""

    def spec_compiled(self, delay=0.0):
        import os
        import time
        f = self.p.p("01_analysis/timeline-spec.json")
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text("{}", encoding="utf-8")
        t = time.time() + delay
        os.utime(f, (t, t))

    def test_hidden_only_when_the_verdict_came_before_the_plan(self):
        self.assertFalse(BC.captions_hidden(self.p))                             # nothing detected
        BC.run(self.p, FX / "en_bottom.mp4", 12.0)
        self.assertTrue(BC.captions_hidden(self.p))                              # no plan yet: applies at compile
        self.spec_compiled(delay=+60)
        self.assertTrue(BC.captions_hidden(self.p))                              # compiled after the verdict
        self.spec_compiled(delay=-3600)
        self.assertFalse(BC.captions_hidden(self.p))                             # late verdict: never silently

    def test_the_editors_switch_wins(self):
        BC.run(self.p, FX / "en_bottom.mp4", 12.0)
        BC.set_captions(self.p, "on")
        self.assertFalse(BC.captions_hidden(self.p))
        BC.set_captions(self.p, "off")
        self.assertTrue(BC.captions_hidden(self.p))
        BC.run(self.p, FX / "clean.mp4", 12.0, words=words_of("clean"))
        self.assertTrue(BC.captions_hidden(self.p))                              # "off" holds whatever the footage
        BC.set_captions(self.p, "auto")
        self.assertFalse(BC.captions_hidden(self.p))
        ed = json.loads(self.p.p("01_analysis/edit-decisions.json").read_text(encoding="utf-8"))
        self.assertNotIn("visible", ed.get("captions", {}))
        with self.assertRaises(ValueError):
            BC.set_captions(self.p, "maybe")

    def test_switch_keeps_the_rest_of_edit_decisions(self):
        f = self.p.p("01_analysis/edit-decisions.json")
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(json.dumps({"global": {"x": 1}, "captions": {"look": "bold"}}), encoding="utf-8")
        BC.set_captions(self.p, "off")
        ed = json.loads(f.read_text(encoding="utf-8"))
        self.assertEqual((ed["global"], ed["captions"]["look"], ed["captions"]["visible"]), ({"x": 1}, "bold", False))

    def test_unreadable_files_never_raise(self):
        f = self.p.p("01_analysis/burned-in-captions.json")
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text("{{{", encoding="utf-8")
        self.assertFalse(BC.captions_hidden(self.p))
        self.p.p("01_analysis/edit-decisions.json").write_text("[1]", encoding="utf-8")
        self.assertFalse(BC.captions_hidden(self.p))

    def test_intake_line(self):
        self.assertEqual(BC.intake_line({"verdict": "yes"}), BC.NOTICE["ar"])
        self.assertEqual(BC.intake_line({"verdict": "maybe"}, "en"), BC.ASK["en"])
        self.assertIsNone(BC.intake_line({"verdict": "no"}))
        self.assertIsNone(BC.intake_line({"verdict": "unknown", "error": "x"}))


# --------------------------------------------------------------------------- independent review round 1
class TestReview1Hard(unittest.TestCase):
    """Continuous speech, other tools' groupings, long cues, small vertical text, swapping supers, a ticker over
    continuous speech, a short clip without a pause (fixtures from make_fixtures.hard)."""

    def test_harder_fixtures(self):
        for name, want in (("cont_bottom", "maybe"), ("karaoke", "maybe"), ("long_cues", "yes"), ("small_vertical", "yes"),
                           ("lt_swaps", "no"), ("ticker_cont", "no"), ("short_cont", "maybe")):
            r = BC.detect(frames_of(name), words_of(name))
            self.assertEqual(r["verdict"], want, (name, r["coverage"], r["regions"]))

    def test_episode_thumbnails_still_find_ordinary_captions(self):
        for name, want in (("en_bottom", "yes"), ("lower_third", "no"), ("ticker", "no"), ("logo", "no")):
            self.assertEqual(BC.detect(frames_of(name, thumbs=True), words_of(name))["verdict"], want, name)

    def test_why_the_new_overlays_fail(self):
        lt = BC.detect(frames_of("lt_swaps"), words_of("lt_swaps"))["regions"]["bottom"]
        self.assertFalse(lt["passes"])
        self.assertGreater(lt["center_offset"], BC.CENTER_MAX)                  # a super sits to one side
        tk = BC.detect(frames_of("ticker_cont"), words_of("ticker_cont"))["regions"]["bottom"]
        self.assertFalse(tk["passes"])
        self.assertGreater(tk["scroll_share"], BC.SCROLL_SHARE_MAX)            # the text slides, it is not replaced

    def test_no_pause_needs_enough_speech_to_hide(self):
        r = BC.detect(frames_of("short_cont"), words_of("short_cont"))
        self.assertTrue(r["regions"]["bottom"]["passes"])
        self.assertFalse(r["evidence"])                                         # caption-like, too little to act on
        self.assertTrue(BC.detect(frames_of("long_cues"), words_of("long_cues"))["evidence"])

    def test_min_changes_alone_fails_a_track(self):
        n = 20
        present = np.ones(n, bool)
        change = np.zeros(n, bool)
        change[[3, 9]] = True
        speech = np.ones(n, bool)
        rh = BC.rhythm(present, change, np.zeros(n, bool), [], np.zeros(n, bool), speech, np.full(n, 0.5))
        self.assertEqual(rh["changes"], 2)
        self.assertFalse(rh["passes"])


class TestReview1Scan(unittest.TestCase):
    def test_budget_is_checked_every_short_chunk(self):
        t = iter([0.0, 5.0, 12.0, 25.0, 26.0, 27.0, 28.0])
        calls = []

        def decode(src, a, b):
            calls.append(a)
            return frames_of("clean")[:int(round(b))]
        r, _ = BC.scan_clip("x.mp4", 60.0, words_of("clean"), decode=decode, clock=lambda: next(t))
        self.assertEqual(calls, [0.0, 10.0, 20.0])                              # 10 s chunks; stopped after 20 s
        self.assertFalse(r["complete"])

    def test_short_chunks_are_padded_and_an_empty_one_stops(self):
        def short(src, a, b):
            return frames_of("en_bottom")[:int(b) - 1] if a == 0 else frames_of("en_bottom")[:0]
        r, fr = BC.scan_clip("x.mp4", 20.0, words_of("en_bottom"), decode=short)
        self.assertEqual(len(fr), 10)                                           # 9 frames padded to 10 (1 per s)
        self.assertFalse(r["complete"])                                         # the next chunk gave nothing

    def test_episode_track_persists_and_a_window_matches(self):
        fr = frames_of("en_bottom", thumbs=True)
        track = BC.band_track(fr)
        json.dumps(track, allow_nan=False)
        self.assertEqual(BC.detect_track(track, words_of("en_bottom"))["verdict"], "yes")
        # an episode window: frames 0-12 placed at 100 s in a longer episode, words shifted the same way
        pad = np.zeros((100, *fr.shape[1:]), np.uint8)
        long = BC.band_track(np.concatenate([pad, fr, pad[:30]]))
        shifted = [dict(w, start_ms=w["start_ms"] + 100000, end_ms=w["end_ms"] + 100000) for w in words_of("en_bottom")]
        win = BC.detect_track(long, shifted, start_s=100.0, end_s=112.0)
        self.assertEqual(win["verdict"], "yes")
        self.assertGreaterEqual(win["bands"][0]["from_ms"], 100000)


class TestReview1Effects(_Proj):
    def test_a_changed_source_makes_the_verdict_stale(self):
        src = self.tmp / "clip.mp4"
        shutil.copyfile(FX / "en_bottom.mp4", src)
        BC.run(self.p, src, 12.0)
        self.assertTrue(BC.captions_hidden(self.p))
        src.write_bytes(src.read_bytes() + b"\0")                               # the footage changed
        self.assertFalse(BC.captions_hidden(self.p))
        src.unlink()
        self.assertFalse(BC.captions_hidden(self.p))

    def test_set_captions_never_overwrites_an_unreadable_file(self):
        f = self.p.p("01_analysis/edit-decisions.json")
        f.parent.mkdir(parents=True, exist_ok=True)
        for raw in ("{{{ broken", "[1, 2]"):
            f.write_text(raw, encoding="utf-8")
            with self.assertRaises(ValueError):
                BC.set_captions(self.p, "off")
            self.assertEqual(f.read_text(encoding="utf-8"), raw)

    def test_contact_sheet_tiles_are_distinct_cues(self):
        r = BC.detect(frames_of("en_bottom"), words_of("en_bottom"))
        keys = r["_strong"]
        segs = r["_segments"]
        self.assertTrue(keys)
        self.assertEqual(len({segs[k] for k in keys}), len(keys))               # one tile per caption cue


# --------------------------------------------------------------------------- independent review round 2
def _plate_frame(text_x0, text_x1, y0=290, y1=318, seed=0, logo=False):
    """640x360: a soft gradient, one 'text line' (light strokes on a dark plate) in x text_x0-text_x1; each seed is a
    different line (its own length around the same centre, its own strokes), as a new caption cue is."""
    c, half = (text_x0 + text_x1) // 2, (text_x1 - text_x0) // 2
    half = max(40, half - (seed * 37) % max(1, half - 40))
    f = text_frame(y0, y1, c - half, c + half, h=360, w=640, seed=seed)
    if logo:                                   # a small logo in the same rows, at the right edge
        f[y0:y1, 600:636] = 20
        f[y0 + 4:y1 - 4, 604:632:3] = 250
    return f


def _clip(segments, n, plate=(220, 420), logo=False):
    """n frames; segments = [(from, to, seed)]: the band shows text `seed` in [from, to); else no band."""
    out = []
    for k in range(n):
        seg = next((s for s in segments if s[0] <= k < s[1]), None)
        out.append(_plate_frame(*plate, seed=seg[2], logo=logo) if seg else text_frame(0, 0, h=360, w=640))
    return np.stack(out)


def _continuous_words(n_s, pause=None):
    ws, t, i = [], 0.3, 1
    while t < n_s - 0.3:
        if not (pause and pause[0] <= t < pause[1]):
            ws.append({"id": i, "word": "w", "start_ms": int(t * 1000), "end_ms": int(t * 1000) + 350})
            i += 1
        t += 0.4
    return ws


class TestReview2(unittest.TestCase):
    def test_centred_supers_that_come_and_go_are_not_captions(self):
        # a centred super every 5 s, 3 s on screen each, continuous speech: appear/disappear are not replacements
        fr = _clip([(1, 4, 1), (6, 9, 2), (11, 14, 3), (16, 19, 4)], 20)
        r = BC.detect(fr, _continuous_words(20))
        self.assertEqual(r["regions"]["bottom"]["replacements"], 0)
        self.assertEqual(r["verdict"], "no")
        # two centred supers and a pause they are absent in: still no
        fr = _clip([(1, 5, 1), (12, 17, 2)], 20)
        self.assertEqual(BC.detect(fr, _continuous_words(20, pause=(7.0, 10.0)))["verdict"], "no")

    def test_without_pauses_or_cue_rhythm_it_only_asks(self):
        # caption-like (replaced every 2 s, centred) over continuous speech: no speech-linked evidence -> maybe, never
        # a silent hide
        fr = _clip([(k, k + 2, k) for k in range(0, 20, 2)], 20)
        r = BC.detect(fr, _continuous_words(20))
        self.assertTrue(r["regions"]["bottom"]["passes"])
        if not r["regions"]["bottom"]["evidence_rhythm"]:
            self.assertEqual(r["verdict"], "maybe")
            self.assertFalse(r["evidence"])
        for name in ("cont_bottom", "karaoke"):                                 # the fixtures without a pause
            v = BC.detect(frames_of(name), words_of(name))
            self.assertIn(v["verdict"], ("yes", "maybe"), name)
            self.assertEqual(v["verdict"] == "yes", v["evidence"], name)

    def test_with_a_pause_the_same_captions_are_yes(self):
        segs = [(k, k + 2, k) for k in range(0, 8, 2)] + [(11, 13, 11), (13, 15, 13), (15, 17, 15), (17, 19, 17)]
        r = BC.detect(_clip(segs, 20), _continuous_words(20, pause=(8.2, 11.0)))
        self.assertEqual(r["verdict"], "yes")
        self.assertTrue(r["regions"]["bottom"]["evidence_pauses"])

    def test_centre_is_the_stroke_mass_not_the_extent(self):
        # a centred caption with a logo in the same rows at the right edge stays centred
        segs = [(k, k + 2, k) for k in range(0, 8, 2)] + [(11, 13, 11), (13, 15, 13), (15, 17, 15), (17, 19, 17)]
        r = BC.detect(_clip(segs, 20, logo=True), _continuous_words(20, pause=(8.2, 11.0)))
        self.assertLessEqual(r["regions"]["bottom"]["center_offset"], 0.05)
        self.assertEqual(r["verdict"], "yes")

    def test_known_residual_rotating_centred_text_cleared_in_pauses(self):
        """KNOWN LIMIT (documented, review round 3): centred text replaced back to back and absent in a long pause
        looks like captions to a 1 fps detector and gives "yes". Pinned so a change in this behaviour is seen."""
        segs = [(0, 4, 1), (4, 8, 2), (12, 16, 3), (16, 20, 4)]
        r = BC.detect(_clip(segs, 20), _continuous_words(20, pause=(8.2, 11.8)))
        self.assertEqual(r["verdict"], "yes")


if __name__ == "__main__":
    unittest.main()
