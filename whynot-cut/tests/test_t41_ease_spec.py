"""3.0 T4.1 smooth zoom and fades: keyframe generation (lib/camera_ease.py, pure).

The case list is T41-CASES.md (side-session notes): C1-C16, C21, C33. What is eased: a story camera move (punch_in,
punch_out, slow_push, reframe by the story editor) on V01 pieces of the compiled timeline spec. Never the automatic
pieces (jump-cut masks, source cutaways, the 4:5 window, shot framing). The ease sits on a boundary only when the
neighbour piece is contiguous in source (no pause or word cut between); at a cut the punch stays hard. A run of pieces
of one decision is one punch-in (ease in on its first piece, ease out on its last); the ease of a boundary between two
story moves belongs to the later one. Keys carry the segment values (scale_factor, offset_x, offset_y) so the Premiere
build and the preview renderer read the same data.
Run:  bash tools/test.sh -p test_t41_ease_spec.py
"""
import sys as _sys
_sys.dont_write_bytecode = True  # keep the plugin folder free of __pycache__
import _isolation  # noqa: F401,E402  G79: sandbox the engine home first (tests/_isolation.py)
import copy  # noqa: E402
import json  # noqa: E402
import math  # noqa: E402
import unittest  # noqa: E402
from pathlib import Path  # noqa: E402

sys = _sys
SK = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SK / "engine" / "reel"))

FPS = 24
E24 = 6          # 250 ms at 24 fps


def ce():
    from lib import camera_ease
    return camera_ease


def seg(a, b, camera="hold", sf=1.0, did=None, src_in=None, ox=0.0, oy=0.0, keep=None, window=None, **extra):
    """A compiled V01 piece. Source times are contiguous with the sequence unless `src_in` says otherwise."""
    s_in = a * 1000 / FPS if src_in is None else src_in
    d = {"start_frame": a, "end_frame": b, "camera": camera, "scale_factor": sf, "offset_x": ox, "offset_y": oy,
         "decision_id": did, "src_in_ms": s_in, "src_out_ms": s_in + (b - a) * 1000 / FPS}
    if keep is not None:
        d["keep_index"] = keep
    if window:
        d["window"] = window
    d.update(extra)                      # e.g. shot_offset_x (only ever set at ease time, never in a spec)
    return d


def keys(segments, ease_ms=250, fps=FPS):
    return ce().ease_keys(segments, fps, ease_ms)


def boundaries(runs):
    """Every (piece, side) that carries an ease."""
    out = []
    for r in runs:
        if r.get("ease_in"):
            out.append(("in", r["ease_in"]["piece"]))
        if r.get("ease_out"):
            out.append(("out", r["ease_out"]["piece"]))
    return out


class TestEaseSettings(unittest.TestCase):
    """C11: camera.ease_ms validation (warnings, never a crash)."""

    def check(self, style, want_ms, warns):
        ms, w = ce().ease_settings(style)
        self.assertEqual(ms, want_ms, (style, w))
        self.assertIsInstance(ms, int)
        if warns:
            self.assertTrue(w and all("camera.ease_ms" in x for x in w), w)
        else:
            self.assertEqual(w, [])

    def test_missing_is_the_250_default(self):
        self.assertEqual(ce().DEFAULT_EASE_MS, 250)
        self.check({}, 250, False)
        self.check({"camera": {}}, 250, False)
        self.check({"camera": {"ease_ms": None}}, 250, False)

    def test_zero_is_off(self):
        self.check({"camera": {"ease_ms": 0}}, 0, False)

    def test_plain_values(self):
        self.check({"camera": {"ease_ms": 300}}, 300, False)
        self.check({"camera": {"ease_ms": 250.6}}, 251, False)

    def test_bad_values_warn_and_use_the_default(self):
        for bad in (-50, "fast", True, False, float("nan"), float("inf"), [250], {"ms": 1}):
            with self.subTest(bad=bad):
                self.check({"camera": {"ease_ms": bad}}, 250, True)

    def test_camera_not_an_object(self):
        self.check({"camera": "smooth"}, 250, True)

    def test_a_number_in_a_string_is_taken_with_a_warning(self):
        self.check({"camera": {"ease_ms": "300"}}, 300, True)

    def test_absurd_is_clamped(self):
        self.assertEqual(ce().MAX_EASE_MS, 2000)
        self.check({"camera": {"ease_ms": 99999}}, 2000, True)


class TestEaseFrames(unittest.TestCase):
    """C12: 250 ms in frames, half up, at the sequence rate."""

    def test_rates(self):
        f = ce().ease_frames
        self.assertEqual(f(250, 24), 6)
        self.assertEqual(f(250, 25), 6)
        self.assertEqual(f(250, 30000 / 1001), 7)
        self.assertEqual(f(250, 30), 8)          # 7.5 -> 8 (half up, not banker's)
        self.assertEqual(f(0, 25), 0)


class TestFadeSettings(unittest.TestCase):
    """C15, C16, C21."""

    def test_missing_or_zero_is_off(self):
        self.assertEqual(ce().fade_settings({}, 10000), (None, []))
        zero = {"fades": {"video_in_ms": 0, "video_out_ms": 0, "audio_in_ms": 0, "audio_out_ms": 0}}
        self.assertEqual(ce().fade_settings(zero, 10000), (None, []))

    def test_values_are_kept(self):
        f, w = ce().fade_settings({"fades": {"video_in_ms": 500, "audio_out_ms": 1200}}, 10000)
        self.assertEqual(w, [])
        self.assertEqual(f, {"video_in_ms": 500, "video_out_ms": 0, "audio_in_ms": 0, "audio_out_ms": 1200})

    def test_bad_values_warn_and_are_off(self):
        f, w = ce().fade_settings({"fades": {"video_in_ms": -5, "audio_out_ms": "x"}}, 10000)
        self.assertIsNone(f)
        self.assertEqual(len(w), 2, w)
        self.assertTrue(all("fades." in x for x in w), w)

    def test_mg_a_fade_shorter_than_a_frame_is_off(self):
        """Review 2 M-g: under one frame at the sequence rate a fade does nothing visible: off, with a warning."""
        f, w = ce().fade_settings({"fades": {"video_in_ms": 20, "audio_out_ms": 500}}, 10000, fps=24)
        self.assertEqual(f["video_in_ms"], 0)
        self.assertEqual(f["audio_out_ms"], 500)
        self.assertTrue(any("fades.video_in_ms" in x and "frame" in x for x in w), w)
        f, w = ce().fade_settings({"fades": {"video_in_ms": 20}}, 10000, fps=24)
        self.assertIsNone(f)
        self.assertTrue(w)

    def test_fades_not_an_object(self):
        f, w = ce().fade_settings({"fades": True}, 10000)
        self.assertIsNone(f)
        self.assertTrue(w)

    def test_longer_than_the_reel_is_clamped(self):
        f, w = ce().fade_settings({"fades": {"video_in_ms": 5000}}, 3000)
        self.assertEqual(f["video_in_ms"], 3000)
        self.assertTrue(any("fades" in x for x in w), w)

    def test_in_plus_out_never_exceeds_the_reel(self):
        f, w = ce().fade_settings({"fades": {"video_in_ms": 2500, "video_out_ms": 2500,
                                             "audio_in_ms": 1000, "audio_out_ms": 1000}}, 3000)
        self.assertLessEqual(f["video_in_ms"] + f["video_out_ms"], 3000)
        self.assertEqual((f["audio_in_ms"], f["audio_out_ms"]), (1000, 1000))     # fits: untouched
        self.assertTrue(w)


class TestEaseKeys(unittest.TestCase):
    def test_c1_punch_at_frame_0_has_no_ease_in(self):
        runs = keys([seg(0, 48, "punch_in", 1.1, "EDIT_001"), seg(48, 120)])
        self.assertEqual(len(runs), 1)
        r = runs[0]
        self.assertEqual(r["decision_id"], "EDIT_001")
        self.assertIsNone(r["ease_in"])
        self.assertEqual(r["ease_out"]["piece"], 0)
        self.assertEqual(r["ease_out"]["frames"], E24)
        self.assertEqual(r["ease_out"]["value"]["scale_factor"], 1.1)
        self.assertEqual(r["ease_out"]["to"]["scale_factor"], 1.0)
        self.assertEqual(r["interpolation"], "bezier")

    def test_c2_punch_to_the_last_frame_has_no_ease_out(self):
        runs = keys([seg(0, 48), seg(48, 120, "punch_in", 1.1, "EDIT_001")])
        r = runs[0]
        self.assertIsNone(r["ease_out"])
        self.assertEqual((r["ease_in"]["piece"], r["ease_in"]["frames"]), (1, E24))
        self.assertEqual(r["ease_in"]["from"], {"scale_factor": 1.0, "offset_x": 0.0, "offset_y": 0.0})
        self.assertEqual(r["ease_in"]["value"]["scale_factor"], 1.1)

    def test_a_middle_punch_eases_both_ways(self):
        runs = keys([seg(0, 24), seg(24, 72, "punch_in", 1.1, "EDIT_001", oy=-40.0), seg(72, 120)])
        r = runs[0]
        self.assertEqual(r["pieces"], [1, 1])
        self.assertEqual((r["ease_in"]["frames"], r["ease_out"]["frames"]), (E24, E24))
        self.assertEqual(r["ease_in"]["value"]["offset_y"], -40.0)
        self.assertEqual(r["ease_out"]["to"]["offset_y"], 0.0)

    def test_c3_short_punch_shares_its_frames(self):
        """Review I1: the two eases of one piece never meet (the middle keys would merge into one): the ease out is
        one frame shorter when they would."""
        for n, ms, want in ((8, 250, (4, 3)), (3, 250, (1, 1)), (12, 250, (6, 5)), (11, 250, (5, 5)),
                            (13, 250, (6, 6)), (100, 2084, (50, 49))):
            with self.subTest(n=n, ms=ms):
                r = keys([seg(0, 24), seg(24, 24 + n, "punch_in", 1.1, "E"), seg(24 + n, 200)], ease_ms=ms)[0]
                self.assertEqual((r["ease_in"]["frames"], r["ease_out"]["frames"]), want)
                self.assertLess(r["ease_in"]["frames"] + r["ease_out"]["frames"], n)

    def test_c3_two_frames_keep_one_ease(self):
        r = keys([seg(0, 24), seg(24, 26, "punch_in", 1.1, "E"), seg(26, 60)])[0]
        self.assertEqual(r["ease_in"]["frames"], 1)
        self.assertIsNone(r["ease_out"])

    def test_c3_a_one_frame_punch_has_no_keys(self):
        self.assertEqual(keys([seg(0, 24), seg(24, 25, "punch_in", 1.1, "E"), seg(25, 60)]), [])

    def test_m3_a_one_frame_piece_has_no_keys_with_one_side_either(self):
        self.assertEqual(keys([seg(0, 24), seg(24, 25, "punch_in", 1.1, "E")]), [])          # last piece: ease in only
        self.assertEqual(keys([seg(0, 1, "punch_in", 1.1, "E"), seg(1, 60)]), [])            # first piece: ease out only
        segs = [seg(0, 24), seg(24, 25, "punch_in", 1.1, "E", keep=0, src_in=1000),
                seg(25, 60, "punch_in", 1.1, "E", keep=1, src_in=3000), seg(60, 90, keep=1, src_in=4458.33)]
        r = keys(segs)[0]                                     # a run whose first piece is one frame: no ease in there
        self.assertIsNone(r["ease_in"])
        self.assertIsNotNone(r["ease_out"])

    def test_c4_back_to_back_the_later_move_owns_the_boundary(self):
        runs = keys([seg(0, 24), seg(24, 72, "punch_in", 1.1, "A"), seg(72, 120, "punch_in", 1.2, "B"), seg(120, 160)])
        a = next(r for r in runs if r["decision_id"] == "A")
        b = next(r for r in runs if r["decision_id"] == "B")
        self.assertIsNotNone(a["ease_in"])
        self.assertIsNone(a["ease_out"])
        self.assertEqual(b["ease_in"]["from"]["scale_factor"], 1.1)
        self.assertEqual(b["ease_out"]["to"]["scale_factor"], 1.0)

    def test_c5_overlapping_moves_get_one_ease_per_boundary(self):
        segs = [seg(0, 24), seg(24, 48, "punch_in", 1.1, "A"), seg(48, 72, "punch_in", 1.25, "B"),
                seg(72, 96, "punch_in", 1.1, "A"), seg(96, 130)]
        runs = keys(segs)
        b = boundaries(runs)
        self.assertEqual(len(b), 4, runs)              # 4 changes of picture, one ease each
        self.assertEqual(len({p for _, p in b if _ == "in"}), len([1 for s, _ in b if s == "in"]))
        a2 = next(r for r in runs if r["pieces"] == [3, 3])
        self.assertEqual(a2["ease_in"]["from"]["scale_factor"], 1.25)
        self.assertEqual(a2["ease_out"]["to"]["scale_factor"], 1.0)

    def test_c6_a_punch_split_by_a_cut_is_one_run(self):
        segs = [seg(0, 24, keep=0, src_in=0), seg(24, 48, "punch_in", 1.1, "P", keep=0, src_in=1000),
                seg(48, 72, "punch_in", 1.16, "P", keep=1, src_in=4000), seg(72, 100, keep=1, src_in=5000)]
        runs = keys(segs)
        self.assertEqual(len(runs), 1, runs)
        r = runs[0]
        self.assertEqual(r["pieces"], [1, 2])
        self.assertEqual(r["ease_in"]["piece"], 1)
        self.assertEqual(r["ease_out"]["piece"], 2)
        self.assertEqual(r["ease_out"]["value"]["scale_factor"], 1.16)     # the mask step inside stays hard

    def test_c7_a_punch_at_a_cut_stays_hard(self):
        segs = [seg(0, 24, keep=0, src_in=0), seg(24, 72, "punch_in", 1.1, "P", keep=1, src_in=2000),
                seg(72, 100, keep=2, src_in=6000)]
        self.assertEqual(keys(segs), [])

    def test_c7_cut_on_one_side_only(self):
        segs = [seg(0, 24, keep=0, src_in=0), seg(24, 72, "punch_in", 1.1, "P", keep=1, src_in=2000),
                seg(72, 100, keep=1, src_in=4000)]
        r = keys(segs)[0]
        self.assertIsNone(r["ease_in"])
        self.assertIsNotNone(r["ease_out"])

    def test_c9_automatic_pieces_are_never_eased(self):
        for s in (seg(24, 72, "jumpcut_mask", 1.06, None), seg(24, 72, "reframe", 0.6, "AUTO_CUTAWAY"),
                  seg(24, 72, "window", 0.8, "AUTO_WINDOW"), seg(24, 72, "reframe", 1.3, "AUTO_SHOT")):
            with self.subTest(piece=s["camera"] + str(s["decision_id"])):
                self.assertEqual(keys([seg(0, 24), s, seg(72, 100)]), [])

    def test_c9_no_ease_into_or_out_of_a_source_cutaway(self):
        segs = [seg(0, 24, "reframe", 0.6, "AUTO_CUTAWAY"), seg(24, 72, "punch_in", 1.1, "P"),
                seg(72, 100, "reframe", 0.6, "AUTO_CUTAWAY")]
        self.assertEqual(keys(segs), [])

    def test_c9_a_punch_inside_the_4_5_window_stays_hard(self):
        """Review C2 (ruling: 4:5 window framing stays hard): the windowed speaker is its own clip on the cutaway
        track, V1 under it is the blurred cover copy, so V1 keys would zoom the blur, not the speaker."""
        win = {"x": 0, "y": 285, "w": 1080, "h": 1350, "mode": "4:5"}
        segs = [seg(0, 24, "window", 0.8, "AUTO_WINDOW", window=win), seg(24, 72, "punch_in", 0.88, "P", window=win),
                seg(72, 100, "window", 0.8, "AUTO_WINDOW", window=win)]
        self.assertEqual(keys(segs), [])
        segs2 = [seg(0, 24), seg(24, 72, "punch_in", 1.1, "P", window=win), seg(72, 100)]
        self.assertEqual(keys(segs2), [])

    def test_c10_only_punch_in_and_slow_push_are_eased(self):
        """Review 2 M-c (ruling): reframe and punch_out stay hard; punch_in eases, slow_push pushes."""
        for cam, sf in (("punch_in", 1.1), ("slow_push", 1.08)):
            with self.subTest(cam=cam):
                r = keys([seg(0, 24), seg(24, 72, cam, sf, "EDIT_009"), seg(72, 100)])[0]
                self.assertEqual(r["camera"], cam)
                self.assertEqual(r["ease_in"]["value"]["scale_factor"], sf)
        for cam, sf in (("punch_out", 0.9), ("reframe", 1.2)):
            with self.subTest(cam=cam):
                self.assertEqual(keys([seg(0, 24), seg(24, 72, cam, sf, "EDIT_009"), seg(72, 100)]), [])

    def test_imp1_never_across_a_shot_boundary(self):
        """Review 2 IMP-1: an automatic shot piece next to a punch-in is another framing (another shot): hard."""
        segs = [seg(0, 24, "reframe", 1.3, "AUTO_SHOT", ox=200.0), seg(24, 72, "punch_in", 1.43, "P", ox=220.0),
                seg(72, 100, "reframe", 1.3, "AUTO_SHOT", ox=-250.0)]
        self.assertEqual(keys(segs), [])
        segs[1]["shot_offset_x"] = 200.0                 # composed over the shot left of it, not the one right of it
        r = keys(segs)[0]
        self.assertIsNotNone(r["ease_in"])
        self.assertIsNone(r["ease_out"])

    def test_imp1_the_same_shot_on_both_sides_eases(self):
        segs = [seg(0, 24, "reframe", 1.3, "AUTO_SHOT", ox=200.0), seg(24, 72, "punch_in", 1.43, "P", ox=220.0),
                seg(72, 100, "reframe", 1.3, "AUTO_SHOT", ox=200.0)]
        segs[1]["shot_offset_x"] = 200.0
        r = keys(segs)[0]
        self.assertEqual(r["ease_in"]["from"]["offset_x"], 200.0)
        self.assertEqual(r["ease_out"]["to"]["offset_x"], 200.0)

    # ---- round 4 I-1: never across a speaker change between two story pieces
    def podcast(self, *story):
        return ([seg(0, 24, "reframe", 1.0, "AUTO_SHOT", ox=200.0)] + list(story)
                + [seg(120, 160, "reframe", 1.0, "AUTO_SHOT", ox=-250.0)])

    def test_r4_i1_back_to_back_punch_ins_over_different_shots(self):
        segs = self.podcast(seg(24, 72, "punch_in", 1.1, "A", ox=220.0, shot_offset_x=200.0),
                            seg(72, 120, "punch_in", 1.1, "B", ox=-275.0, shot_offset_x=-250.0))
        runs = {r["decision_id"]: r for r in keys(segs)}
        self.assertIsNotNone(runs["A"]["ease_in"])             # from its own shot
        self.assertIsNone(runs["A"]["ease_out"])
        self.assertIsNone(runs["B"]["ease_in"])               # the speaker changes at frame 72: hard
        self.assertIsNotNone(runs["B"]["ease_out"])            # back to its own shot

    def test_r4_i1_the_same_shot_back_to_back_still_eases(self):
        segs = self.podcast(seg(24, 72, "punch_in", 1.1, "A", ox=220.0, shot_offset_x=200.0),
                            seg(72, 120, "punch_in", 1.2, "B", ox=240.0, shot_offset_x=200.0))
        segs[-1]["offset_x"] = 200.0
        runs = {r["decision_id"]: r for r in keys(segs)}
        self.assertEqual(runs["B"]["ease_in"]["from"]["scale_factor"], 1.1)

    def test_r4_i1_a_story_reframe_on_one_shot_then_a_punch_in_on_another(self):
        segs = [seg(0, 72, "reframe", 1.0, "E1", ox=200.0, shot_offset_x=200.0),
                seg(72, 120, "punch_in", 1.1, "B", ox=-275.0, shot_offset_x=-250.0),
                seg(120, 160, "reframe", 1.0, "AUTO_SHOT", ox=-250.0)]
        r = keys(segs)[0]
        self.assertIsNone(r["ease_in"])
        self.assertIsNotNone(r["ease_out"])
        segs[1]["shot_offset_x"] = 200.0                       # the same shot: the punch eases in from the reframe
        segs[1]["offset_x"] = 220.0
        segs[2]["offset_x"] = 200.0
        self.assertIsNotNone(keys(segs)[0]["ease_in"])

    def test_r4_i1_a_slow_push_on_another_shot_starts_from_its_own_shot(self):
        segs = [seg(0, 72, "reframe", 1.0, "E1", ox=200.0, shot_offset_x=200.0),
                seg(72, 120, "slow_push", 1.1, "S", ox=-275.0, shot_offset_x=-250.0)]
        r = keys(segs)[0]
        self.assertEqual(r["ease_in"]["from"], {"scale_factor": 1.0, "offset_x": -250.0, "offset_y": 0.0})
        segs[1]["shot_offset_x"] = 200.0                       # the same shot: from the picture before it
        self.assertEqual(keys(segs)[0]["ease_in"]["from"]["offset_x"], 200.0)

    # ---- round 5 IMP-1: the shot is matched in FRAMES (as apply_framing cuts the pieces), and with shot ids in the
    # camera layer a story piece with no resolved shot is another shot (hard), never "the same"
    @staticmethod
    def pair_at(at_b, fps, src_in_b=None, keep=None):
        """Two punch-ins back to back on two speakers, the speaker change (and the move) at `at_b` ms."""
        from lib.common import ms_to_frame
        fb, f5, f_end = ms_to_frame(at_b, fps), ms_to_frame(5000, fps), ms_to_frame(6400, fps)
        f1 = ms_to_frame(1000, fps)
        cam = [{"decision_id": "AUTO_SHOT", "at_ms": 0, "until_ms": 1000, "offset_x": 200.0},
               {"decision_id": "A", "type": "punch_in", "at_ms": 1000, "until_ms": at_b, "offset_x": 220.0,
                "shot_offset_x": 200.0},
               {"decision_id": "B", "type": "punch_in", "at_ms": at_b, "until_ms": 5000, "offset_x": -275.0,
                "shot_offset_x": -250.0},
               {"decision_id": "AUTO_SHOT", "at_ms": 5000, "until_ms": 6400, "offset_x": -250.0}]

        def sg(a, b, camera, sf, did, ox, src_in=None):
            s_in = a * 1000 / fps if src_in is None else src_in
            d = {"start_frame": a, "end_frame": b, "camera": camera, "scale_factor": sf, "offset_x": ox,
                 "offset_y": 0.0, "decision_id": did, "src_in_ms": s_in, "src_out_ms": s_in + (b - a) * 1000 / fps}
            if keep is not None:
                d["keep_index"] = keep
            return d
        segs = [sg(0, f1, "reframe", 1.0, "AUTO_SHOT", 200.0), sg(f1, fb, "punch_in", 1.1, "A", 220.0),
                sg(fb, f5, "punch_in", 1.1, "B", -275.0, src_in=src_in_b),
                sg(f5, f_end, "reframe", 1.0, "AUTO_SHOT", -250.0)]
        return segs, cam

    def test_r5_imp1_identity_path_at_3010_ms_25_fps(self):
        segs, cam = self.pair_at(3010, 25)                       # piece B starts at frame 75 = 3000 ms < 3010
        ws = ce().with_shots(segs, cam, 25)
        self.assertEqual(ws[2]["shot_offset_x"], -250.0)
        runs = {r["decision_id"]: r for r in ce().ease_keys(ws, 25, 250)}
        self.assertIsNone(runs["B"]["ease_in"])                  # no pan across the speaker change
        self.assertIsNotNone(runs["B"]["ease_out"])             # back to its own shot
        self.assertIsNone(runs["A"]["ease_out"])

    def test_r5_imp1_non_aligned_at_29_97(self):
        fps = 30000 / 1001
        segs, cam = self.pair_at(3010, fps)          # 90.2 frames: frame 90 starts at 3003 ms
        runs = {r["decision_id"]: r for r in ce().ease_keys(ce().with_shots(segs, cam, fps), fps, 250)}
        self.assertIsNone(runs["B"]["ease_in"])
        self.assertIsNotNone(runs["B"]["ease_out"])

    def test_r5_imp1_time_map_path(self):
        """After pause removal a piece keeps its exact source in-point (TimeMap): matched in frames all the same."""
        for fps, at_b in ((25, 3010), (30000 / 1001, 3010)):
            with self.subTest(fps=fps):
                segs, cam = self.pair_at(at_b, fps, src_in_b=float(at_b), keep=0)
                runs = {r["decision_id"]: r for r in ce().ease_keys(ce().with_shots(segs, cam, fps), fps, 250)}
                self.assertIsNone(runs["B"]["ease_in"])
                self.assertIsNotNone(runs["B"]["ease_out"])

    def test_r5_imp1_a_slow_push_on_the_new_shot_starts_on_the_speaker(self):
        from lib.common import ms_to_frame
        for fps, at_b in ((25, 3010), (30000 / 1001, 3010)):
            with self.subTest(fps=fps):
                fb, f5 = ms_to_frame(at_b, fps), ms_to_frame(5000, fps)
                cam = [{"decision_id": "AUTO_SHOT", "at_ms": 0, "until_ms": at_b, "offset_x": 200.0},
                       {"decision_id": "S", "type": "slow_push", "at_ms": at_b, "until_ms": 5000, "offset_x": 682.7,
                        "shot_offset_x": 682.7}]
                segs = [seg(0, fb, "reframe", 1.0, "AUTO_SHOT", ox=200.0), seg(fb, f5, "slow_push", 1.1, "S", ox=682.7)]
                for s_ in segs:
                    s_["src_in_ms"] = s_["start_frame"] * 1000 / fps
                r = ce().ease_keys(ce().with_shots(segs, cam, fps), fps, 250)
                self.assertEqual(r[0]["ease_in"]["from"], {"scale_factor": 1.0, "offset_x": 682.7, "offset_y": 0.0})

    def test_r5_imp1_the_same_shot_pair_still_eases(self):
        segs, cam = self.pair_at(3010, 25)
        cam[2]["shot_offset_x"] = 200.0
        segs[2]["offset_x"] = 230.0
        segs[3]["offset_x"] = 200.0
        runs = {r["decision_id"]: r for r in ce().ease_keys(ce().with_shots(segs, cam, 25), 25, 250)}
        self.assertIsNotNone(runs["B"]["ease_in"])
        self.assertIsNotNone(runs["B"]["ease_out"])

    def test_r5_imp1_an_unresolved_story_piece_in_a_multicam_plan_is_hard(self):
        segs, cam = self.pair_at(3010, 25)
        cam[2]["decision_id"] = "OTHER"                          # B's shot cannot be found in the layer
        ws = ce().with_shots(segs, cam, 25)
        self.assertIsNone(ws[2].get("shot_offset_x"))
        runs = {r["decision_id"]: r for r in ce().ease_keys(ws, 25, 250)}
        self.assertIsNone(runs.get("B", {}).get("ease_in"))
        self.assertIsNone(runs["A"]["ease_out"])

    def test_r5_imp1_single_cam_without_shot_ids_is_as_before(self):
        segs = [seg(0, 24), seg(24, 72, "punch_in", 1.1, "A"), seg(72, 120, "punch_in", 1.2, "B"), seg(120, 160)]
        runs = {r["decision_id"]: r for r in ce().ease_keys(ce().with_shots(segs, [], 24), 24, 250)}
        self.assertIsNotNone(runs["B"]["ease_in"])

    # ---- round 6 (executor): no ease may START inside a manual_verse span; the move stays hard there, with a warning
    def test_r6_no_ease_starts_inside_a_recited_verse(self):
        segs = [seg(0, 24), seg(24, 72, "punch_in", 1.1, "P"), seg(72, 120)]
        verse = [{"id": "V1", "start_frame": 20, "end_frame": 30}]                 # covers the ease-in start (24)
        f, w = ce().spec_fields(segs, {}, FPS, 5000, verse=verse)
        r = f["camera_ease"]["runs"][0]
        self.assertIsNone(r["ease_in"])
        self.assertIsNotNone(r["ease_out"])
        self.assertTrue(any("verse" in x and "P" in x for x in w), w)
        verse = [{"id": "V2", "start_frame": 60, "end_frame": 80}]                 # covers the ease-out start (66)
        r = ce().spec_fields(segs, {}, FPS, 5000, verse=verse)[0]["camera_ease"]["runs"][0]
        self.assertIsNotNone(r["ease_in"])
        self.assertIsNone(r["ease_out"])
        verse = [{"id": "V3", "start_frame": 31, "end_frame": 60}]                 # inside the hold (after the last ease-in key)
        r = ce().spec_fields(segs, {}, FPS, 5000, verse=verse)[0]["camera_ease"]["runs"][0]
        self.assertIsNotNone(r["ease_in"])
        self.assertIsNotNone(r["ease_out"])

    def test_r6_a_slow_push_starting_inside_a_verse_stays_hard(self):
        segs = [seg(0, 24), seg(24, 72, "slow_push", 1.1, "S"), seg(72, 120)]
        f, w = ce().spec_fields(segs, {}, FPS, 5000, verse=[{"id": "V1", "start_frame": 10, "end_frame": 40}])
        self.assertEqual(f["camera_ease"]["runs"], [])
        self.assertTrue(w)

    # ---- round 7 (P3-2 ruling): no camera motion during a recited verse: an ease whose window OVERLAPS a span is
    # dropped (that side stays hard); a slow_push whose piece overlaps one is not pushed. Half-open frame spans.
    def verse_runs(self, verse, segs=None):
        segs = segs or [seg(0, 24), seg(24, 72, "punch_in", 1.1, "P"), seg(72, 120)]
        f, w = ce().spec_fields(segs, {}, FPS, 5000, verse=verse)
        return f["camera_ease"], w

    def test_r7_an_ease_that_starts_before_a_verse_and_runs_into_it_is_dropped(self):
        ce_, w = self.verse_runs([{"id": "V1", "start_frame": 27, "end_frame": 40}])      # ease in = frames 24-29
        r = ce_["runs"][0]
        self.assertIsNone(r["ease_in"])
        self.assertIsNotNone(r["ease_out"])
        self.assertNotIn("dropped", r)                       # round 8 P2-1: the runs stay schema-clean
        self.assertEqual(ce_["verse_dropped"], [{"decision_id": "P", "camera": "punch_in", "side": "in",
                                                 "start_ms": 1000}])
        ce_, _ = self.verse_runs([{"id": "V2", "start_frame": 60, "end_frame": 67}])      # ease out = frames 66-71
        self.assertEqual([(d["side"], d["start_ms"]) for d in ce_["verse_dropped"]], [("out", 2750)])
        self.assertIsNone(ce_["runs"][0]["ease_out"])

    def test_r7_half_open_edges_do_not_touch(self):
        ce_, w = self.verse_runs([{"id": "V1", "start_frame": 10, "end_frame": 24},          # ends where the ease starts
                                  {"id": "V2", "start_frame": 31, "end_frame": 66},          # between the two eases
                                  {"id": "V3", "start_frame": 72, "end_frame": 90}])         # starts where the move ends
        r = ce_["runs"][0]
        self.assertIsNotNone(r["ease_in"])
        self.assertIsNotNone(r["ease_out"])
        self.assertNotIn("dropped", r)
        self.assertNotIn("verse_dropped", ce_)               # a verse touching no ease leaves camera_ease as it was
        self.assertNotIn("verse_hard", ce_)
        self.assertEqual(w, [])

    # ---- round 8
    def test_r8_p3_1_a_verse_on_the_last_ease_in_key_frame_drops_it(self):
        """The last ease-in key sits AT frame start + frames (JSX tSelf, value_at): a verse starting there drops it."""
        from lib.common import ms_to_frame
        for fps in (24, 25, 30000 / 1001):
            with self.subTest(fps=fps):
                e = ce().ease_frames(250, fps)
                a = 24
                segs = [seg(0, a), seg(a, a + 48, "punch_in", 1.1, "P"), seg(a + 48, a + 96)]
                ce_, _ = ce().spec_fields(segs, {}, fps, 10000, verse=[{"start_frame": a + e, "end_frame": a + e + 4}])
                self.assertIsNone(ce_["camera_ease"]["runs"][0]["ease_in"])
                ce_, _ = ce().spec_fields(segs, {}, fps, 10000,
                                          verse=[{"start_frame": a + e + 1, "end_frame": a + e + 4}])
                self.assertIsNotNone(ce_["camera_ease"]["runs"][0]["ease_in"])      # the frame after: kept
                self.assertGreater(ms_to_frame(250, fps), 0)

    def test_r8_p3_2_a_verse_strictly_inside_the_ease_out_window(self):
        ce_, w = self.verse_runs([{"id": "V1", "start_frame": 68, "end_frame": 70}])      # ease out = 66-71
        self.assertIsNone(ce_["runs"][0]["ease_out"])
        self.assertIsNotNone(ce_["runs"][0]["ease_in"])
        self.assertEqual([d["side"] for d in ce_["verse_dropped"]], ["out"])

    def test_r8_p3_4_the_warning_names_the_time_of_the_dropped_side(self):
        ce_, w = self.verse_runs([{"id": "V1", "start_frame": 68, "end_frame": 70}])      # ease out starts 66 = 2.75 s
        self.assertEqual(len(w), 1)
        self.assertIn("00:03", w[0])
        self.assertNotIn("00:01", w[0])                       # not the punch's start
        from lib.common import ms_to_frame
        for fps in (25, 29.97):                               # round 8 review P3-2 (M15): the time uses the clip's fps
            with self.subTest(fps=fps):
                f, w = ce().spec_fields([seg(0, 24), seg(24, 72, "punch_in", 1.1, "P"), seg(72, 120)], {}, fps, 5000,
                                        verse=[{"id": "V1", "start_frame": 68, "end_frame": 70}])
                t = int(round((72 - ms_to_frame(250, fps)) / fps))
                self.assertEqual(len(w), 1, w)
                self.assertIn(f"00:{t:02d}", w[0])
        self.assertEqual(int(round((72 - ms_to_frame(250, 29.97)) / 29.97)), 2)     # 29.97 differs from 24 fps

    def test_r7_a_slow_push_across_a_verse_is_not_pushed(self):
        segs = [seg(0, 24), seg(24, 72, "slow_push", 1.1, "S"), seg(72, 120)]
        ce_, w = self.verse_runs([{"id": "V1", "start_frame": 40, "end_frame": 50}], segs)
        self.assertEqual(ce_["runs"], [])
        self.assertEqual([h["decision_id"] for h in ce_["verse_hard"]], ["S"])
        self.assertEqual(len(w), 1)

    def test_r7_both_sides_dropped_keeps_a_record_and_one_warning(self):
        ce_, w = self.verse_runs([{"id": "V1", "start_frame": 20, "end_frame": 80}])
        self.assertEqual(ce_["runs"], [])
        self.assertEqual(ce_["verse_hard"], [{"decision_id": "P", "camera": "punch_in", "sides": ["in", "out"],
                                              "start_ms": 1000}])
        self.assertEqual(len(w), 1, w)                            # P3-1: one line per move
        self.assertIn("00:01", w[0])                               # the move's time, mm:ss
        self.assertIn("P", w[0])
        self.assertTrue(any("\u0621" <= ch <= "\u064a" for ch in w[0]), w[0])     # and Egyptian Arabic

    def test_r7_malformed_verse_entries_are_skipped(self):
        bad = [None, "x", 7, {}, {"start_frame": 20}, {"start_frame": "a", "end_frame": 30},
               {"start_frame": True, "end_frame": 30}, {"start_frame": [1], "end_frame": {}},
               {"start_frame": 20, "end_frame": 20}]                               # zero length (review P3-2, M16)
        ce_, w = self.verse_runs(bad)
        r = ce_["runs"][0]
        self.assertIsNotNone(r["ease_in"])
        self.assertIsNotNone(r["ease_out"])
        self.assertEqual(w, [])
        ce_, _ = self.verse_runs(bad + [{"start_frame": "20", "end_frame": 30.0}])         # numbers as text / float
        self.assertIsNone(ce_["runs"][0]["ease_in"])

    def test_r7_a_head_shaped_manual_verse_record_blocks(self):
        """Executor (round 7): spec["manual_verse"] is the source of truth, keyed on its frames; the full record shape
        of 91cd197 (apply_manual_verse) is read as is."""
        rec = {"id": "MV01", "src_start_ms": 900, "src_end_ms": 1400, "start_ms": 900, "end_ms": 1400,
               "start_frame": 22, "end_frame": 34, "start_tc": "00:00:00:22", "end_tc": "00:00:01:10", "cue": "editor",
               "cue_ar": "x", "cue_en": "x", "end": "editor", "guessed_end": False, "source": "editor"}
        ce_, w = self.verse_runs([rec])
        self.assertIsNone(ce_["runs"][0]["ease_in"])
        self.assertEqual(len(w), 1)

    # ---- round 9 P2-2: the piece each window is read on, and the last frame before the out point (M1-M4)
    def split_punch(self):
        """A punch-in split into 2 contiguous pieces (one run, pieces [1, 2]): ease in on 24-30, ease out on 90-95."""
        return [seg(0, 24), seg(24, 48, "punch_in", 1.1, "P"), seg(48, 96, "punch_in", 1.1, "P"), seg(96, 140)]

    def test_r9_m1_the_ease_out_window_is_on_the_runs_last_piece(self):
        ce_, _ = self.verse_runs([{"start_frame": 90, "end_frame": 91}], self.split_punch())
        self.assertEqual(ce_["runs"][0]["pieces"], [1, 2])
        self.assertIsNone(ce_["runs"][0]["ease_out"])
        self.assertIsNotNone(ce_["runs"][0]["ease_in"])
        ce_, w = self.verse_runs([{"start_frame": 44, "end_frame": 45}], self.split_punch())   # the first piece's end
        self.assertIsNotNone(ce_["runs"][0]["ease_out"])
        self.assertEqual(w, [])

    def test_r9_m2_the_ease_in_window_is_on_the_runs_first_piece(self):
        ce_, _ = self.verse_runs([{"start_frame": 26, "end_frame": 27}], self.split_punch())
        self.assertIsNone(ce_["runs"][0]["ease_in"])
        self.assertIsNotNone(ce_["runs"][0]["ease_out"])
        ce_, w = self.verse_runs([{"start_frame": 50, "end_frame": 51}], self.split_punch())   # the last piece's start
        self.assertIsNotNone(ce_["runs"][0]["ease_in"])
        self.assertEqual(w, [])

    def test_r9_m4_a_verse_on_the_frame_before_the_out_point_drops_the_ease_out(self):
        ce_, _ = self.verse_runs([{"start_frame": 71, "end_frame": 80}])          # punch 24-72, ease out 66-71
        self.assertIsNone(ce_["runs"][0]["ease_out"])
        self.assertEqual([d["side"] for d in ce_["verse_dropped"]], ["out"])

    def test_r9_m3_a_verse_on_a_slow_pushs_last_frame_makes_it_hard(self):
        segs = [seg(0, 24), seg(24, 72, "slow_push", 1.1, "S"), seg(72, 120)]
        ce_, _ = self.verse_runs([{"start_frame": 71, "end_frame": 80}], segs)
        self.assertEqual(ce_["runs"], [])
        self.assertEqual([h["decision_id"] for h in ce_["verse_hard"]], ["S"])

    # ---- round 9 P2-1 (executor: the round-7 P3-4 ruling): a caption run held after a span ("the verse may go on",
    # spec verse_hold, not released, not cut away) blocks camera motion like a verse; its words say "may go on"
    def held_runs(self, held, verse=None, segs=None):
        """plan.apply_ease's shape: the manual_verse records, then the held runs marked `held: True`."""
        segs = segs or [seg(0, 24), seg(24, 72, "punch_in", 1.1, "P"), seg(72, 120)]
        f, w = ce().spec_fields(segs, {}, FPS, 5000, verse=(verse or []) + [dict(h, held=True) for h in held or []])
        return f["camera_ease"], w

    def test_r9_only_a_true_held_mark_softens_the_wording(self):
        for mark in ("yes", 1, None, False):                  # anything but True is a recited verse (fail safe)
            with self.subTest(mark=mark):
                ce_, w = self.held_runs(None, verse=[{"start_frame": 27, "end_frame": 40, "held": mark}])
                self.assertEqual(ce_["verse_dropped"][0].get("held"), None)
                self.assertIn("is recited", w[0])

    def test_r9_a_held_run_blocks_an_ease(self):
        ce_, w = self.held_runs([{"id": "MV01H", "start_frame": 27, "end_frame": 40}])     # ease in = frames 24-30
        self.assertIsNone(ce_["runs"][0]["ease_in"])
        self.assertIsNotNone(ce_["runs"][0]["ease_out"])
        self.assertEqual(ce_["verse_dropped"], [{"decision_id": "P", "camera": "punch_in", "side": "in",
                                                 "start_ms": 1000, "held": True}])
        self.assertEqual(len(w), 1, w)
        self.assertIn("may go on", w[0])
        self.assertIn("ممكن الآية تكون مكمّلة", w[0])
        self.assertNotIn("is recited", w[0])                    # never claims a verse for sure
        self.assertNotIn("وقت الآية", w[0])
        self.assertIn("00:01", w[0])

    def test_r9_a_held_run_over_both_eases_makes_the_move_hard(self):
        ce_, w = self.held_runs([{"start_frame": 20, "end_frame": 80}])
        self.assertEqual(ce_["runs"], [])
        self.assertEqual(ce_["verse_hard"], [{"decision_id": "P", "camera": "punch_in", "sides": ["in", "out"],
                                              "start_ms": 1000, "held": True}])
        self.assertEqual(len(w), 1, w)
        segs = [seg(0, 24), seg(24, 72, "slow_push", 1.1, "S"), seg(72, 120)]
        ce_, _ = self.held_runs([{"start_frame": 71, "end_frame": 72}], segs=segs)        # a push's last frame
        self.assertEqual([(h["decision_id"], h.get("held")) for h in ce_["verse_hard"]], [("S", True)])

    def test_r9_a_verse_wins_over_a_held_run(self):
        ce_, w = self.held_runs([{"start_frame": 68, "end_frame": 70}], verse=[{"start_frame": 26, "end_frame": 27}])
        self.assertEqual(ce_["verse_hard"], [{"decision_id": "P", "camera": "punch_in", "sides": ["in", "out"],
                                              "start_ms": 1000}])                  # a recited verse: no "held"
        self.assertEqual(len(w), 1, w)
        self.assertIn("is recited", w[0])
        self.assertIn("00:01", w[0])
        ce_, w = self.held_runs([{"start_frame": 26, "end_frame": 27}], verse=[{"start_frame": 68, "end_frame": 70}])
        self.assertEqual(len(w), 1, w)
        self.assertIn("is recited", w[0])
        self.assertIn("00:03", w[0])                              # at the verse's side (ease out, 2.75 s)
        segs = [seg(0, 24), seg(24, 72, "slow_push", 1.1, "S"), seg(72, 120)]       # one window over both
        ce_, w = self.held_runs([{"start_frame": 40, "end_frame": 50}], verse=[{"start_frame": 30, "end_frame": 32}],
                                segs=segs)
        self.assertEqual(ce_["verse_hard"], [{"decision_id": "S", "camera": "slow_push", "sides": ["in"],
                                              "start_ms": 1000}])
        self.assertIn("is recited", w[0])

    def test_r9_a_held_run_touching_no_ease_changes_nothing(self):
        ce_, w = self.held_runs([{"start_frame": 31, "end_frame": 66}, {"start_frame": 72, "end_frame": 90},
                                 {"start_frame": 10, "end_frame": 24}])
        self.assertEqual(set(ce_), {"ease_ms", "curve", "runs"})
        self.assertIsNotNone(ce_["runs"][0]["ease_in"])
        self.assertIsNotNone(ce_["runs"][0]["ease_out"])
        self.assertEqual(w, [])
        plain, _ = self.held_runs(None)
        self.assertEqual(ce_, plain)

    def test_r9_held_edges_are_half_open(self):
        ce_, _ = self.held_runs([{"start_frame": 30, "end_frame": 31}])                    # the last ease-in key frame
        self.assertIsNone(ce_["runs"][0]["ease_in"])
        ce_, _ = self.held_runs([{"start_frame": 23, "end_frame": 24}])                    # ends where the ease starts
        self.assertIsNotNone(ce_["runs"][0]["ease_in"])
        ce_, _ = self.held_runs([{"start_frame": 10, "end_frame": 25}])                    # ends on its first frame
        self.assertIsNone(ce_["runs"][0]["ease_in"])
        ce_, _ = self.held_runs([{"start_frame": 71, "end_frame": 72}])                    # the frame before the out point
        self.assertIsNone(ce_["runs"][0]["ease_out"])
        ce_, _ = self.held_runs([{"start_frame": 72, "end_frame": 73}])                    # the out point itself
        self.assertIsNotNone(ce_["runs"][0]["ease_out"])

    # ---- round 9 P3-2 (executor): one warning per move, not per run
    def test_r9_a_move_split_by_a_cutaway_gets_one_warning(self):
        segs = [seg(0, 24), seg(24, 48, "punch_in", 1.1, "P"), seg(48, 72, did="AUTO_CUTAWAY"),
                seg(72, 96, "punch_in", 1.1, "P"), seg(96, 140)]
        runs = keys(segs)
        self.assertEqual([r["pieces"] for r in runs], [[1, 1], [3, 3]])                    # two runs of one move
        for verse, held in (([{"start_frame": 20, "end_frame": 100}], None),
                            (None, [{"start_frame": 20, "end_frame": 100}])):
            with self.subTest(held=bool(held)):
                ce_, w = self.held_runs(held, verse=verse, segs=segs)
                self.assertEqual(len(ce_["verse_hard"]), 2)
                self.assertEqual(len(w), 1, w)
                self.assertIn("00:01", w[0])                                               # the move's first side

    # ---- round 4 I-2: a punch_in never eases out into another story decision
    def test_r4_i2_no_ease_out_into_a_story_reframe_or_punch_out(self):
        for cam, sf, ox in (("reframe", 1.0, 300.0), ("punch_out", 0.9, 0.0)):
            with self.subTest(cam=cam):
                r = keys([seg(0, 24), seg(24, 72, "punch_in", 1.1, "A"), seg(72, 120, cam, sf, "B", ox=ox),
                          seg(120, 160)])[0]
                self.assertIsNotNone(r["ease_in"])
                self.assertIsNone(r["ease_out"])

    # ---- round 4 I-3 (option B): the shot identity is derived at ease time, never stored in the spec
    def test_r4_i3_shot_identity_comes_from_the_camera_layer(self):
        cam = [{"decision_id": "AUTO_SHOT", "type": "reframe", "at_ms": 0, "until_ms": 1000, "offset_x": 200.0},
               {"decision_id": "A", "type": "punch_in", "at_ms": 1000, "until_ms": 3000, "offset_x": 220.0,
                "shot_offset_x": 200.0},
               {"decision_id": "B", "type": "punch_in", "at_ms": 3000, "until_ms": 5000, "offset_x": -275.0,
                "shot_offset_x": -250.0},
               {"decision_id": "AUTO_SHOT", "type": "reframe", "at_ms": 5000, "until_ms": 6667, "offset_x": -250.0}]
        segs = self.podcast(seg(24, 72, "punch_in", 1.1, "A", ox=220.0), seg(72, 120, "punch_in", 1.1, "B", ox=-275.0))
        before = [dict(s) for s in segs]
        f, _ = ce().spec_fields(segs, {}, FPS, 160 * 1000 / FPS, camera=cam)
        runs = {r["decision_id"]: r for r in f["camera_ease"]["runs"]}
        self.assertIsNotNone(runs["A"]["ease_in"])
        self.assertIsNone(runs["B"]["ease_in"])                # different shots, known only from the camera layer
        self.assertEqual(segs, before)                         # the spec's pieces are never changed
        self.assertNotIn("shot_offset_x", json.dumps(f))

    # ---- round 3, item 1: a slow_push is a push across its own piece, not a 250 ms ease
    def test_r3_slow_push_spans_its_piece(self):
        r = keys([seg(0, 24), seg(24, 72, "slow_push", 1.08, "S"), seg(72, 100)])[0]
        self.assertEqual((r["ease_in"]["piece"], r["ease_in"]["frames"]), (1, 47))      # 48 frames: start to end - 1
        self.assertEqual(r["ease_in"]["from"]["scale_factor"], 1.0)
        self.assertEqual(r["ease_in"]["value"]["scale_factor"], 1.08)
        self.assertIsNone(r["ease_out"])                                                   # it ends on its value

    def test_r3_slow_push_does_not_depend_on_ease_ms(self):
        a = keys([seg(0, 24), seg(24, 72, "slow_push", 1.08, "S"), seg(72, 100)], ease_ms=250)
        b = keys([seg(0, 24), seg(24, 72, "slow_push", 1.08, "S"), seg(72, 100)], ease_ms=1500)
        self.assertEqual(a, b)

    def test_r3_slow_push_with_ease_off_still_pushes(self):
        """ease_ms 0 means hard punches; a slow_push is a push by definition (a static one would be a punch-in)."""
        r = keys([seg(0, 24), seg(24, 72, "slow_push", 1.08, "S"), seg(72, 100)], ease_ms=0)
        self.assertEqual(r[0]["ease_in"]["frames"], 47)

    def test_r3_slow_push_at_frame_0_and_after_a_cut_starts_from_the_unzoomed_picture(self):
        r = keys([seg(0, 48, "slow_push", 1.08, "S"), seg(48, 100)])[0]
        self.assertEqual(r["ease_in"]["from"], {"scale_factor": 1.0, "offset_x": 0.0, "offset_y": 0.0})
        self.assertEqual(r["ease_in"]["frames"], 47)
        segs = [seg(0, 24, keep=0, src_in=0), seg(24, 72, "slow_push", 1.2, "S", oy=-30.0, keep=1, src_in=2000),
                seg(72, 100, keep=1, src_in=4000)]
        r = keys(segs)[0]
        self.assertEqual(r["ease_in"]["from"], {"scale_factor": 1.0, "offset_x": 0.0, "offset_y": 0.0})
        self.assertIsNone(r["ease_out"])                                # the edges stay hard: no ease back out

    def test_r3_short_slow_push(self):
        r = keys([seg(0, 24), seg(24, 26, "slow_push", 1.08, "S"), seg(26, 60)])[0]
        self.assertEqual(r["ease_in"]["frames"], 1)
        self.assertEqual(keys([seg(0, 24), seg(24, 25, "slow_push", 1.08, "S"), seg(25, 60)]), [])

    def test_r3_slow_push_split_by_a_cut_pushes_on_its_first_piece(self):
        segs = [seg(0, 24, keep=0, src_in=0), seg(24, 48, "slow_push", 1.08, "S", keep=0, src_in=1000),
                seg(48, 72, "slow_push", 1.14, "S", keep=1, src_in=4000), seg(72, 100, keep=1, src_in=5000)]
        r = keys(segs)[0]
        self.assertEqual(r["pieces"], [1, 2])
        self.assertEqual((r["ease_in"]["piece"], r["ease_in"]["frames"]), (1, 23))
        self.assertIsNone(r["ease_out"])

    def test_c11_zero_ms_means_no_keys(self):
        self.assertEqual(keys([seg(0, 24), seg(24, 72, "punch_in", 1.1, "P"), seg(72, 100)], ease_ms=0), [])

    def test_c12_frames_follow_the_rate(self):
        r = keys([seg(0, 30), seg(30, 90, "punch_in", 1.1, "P"), seg(90, 120)], fps=30)[0]
        self.assertEqual(r["ease_in"]["frames"], 8)

    def test_c33_deterministic_and_pure(self):
        segs = [seg(0, 24), seg(24, 72, "punch_in", 1.1, "P"), seg(72, 100)]
        before = copy.deepcopy(segs)
        self.assertEqual(json.dumps(keys(segs), sort_keys=True), json.dumps(keys(segs), sort_keys=True))
        self.assertEqual(segs, before)

    def test_keys_are_json(self):
        r = keys([seg(0, 24), seg(24, 72, "punch_in", 1.1, "قص_١"), seg(72, 100)])
        self.assertEqual(json.loads(json.dumps(r, ensure_ascii=False))[0]["decision_id"], "قص_١")


class TestSpecFields(unittest.TestCase):
    """What compile adds to the timeline spec: nothing when off (C13), the runs and the fades when on."""

    def test_r3_the_plan_records_the_ease_even_with_nothing_to_ease(self):
        """Round 3, item 2: a plan written with T4.1 records camera.ease_ms (old plans keep their old value: none)."""
        f, w = ce().spec_fields([seg(0, 100)], {}, FPS, 100 * 1000 / FPS)
        self.assertEqual((f, w), ({"camera_ease": {"ease_ms": 250, "curve": "bezier", "runs": []}}, []))

    def test_ease_off_is_recorded_with_no_runs(self):
        f, _ = ce().spec_fields([seg(0, 24), seg(24, 72, "punch_in", 1.1, "P"), seg(72, 100)],
                                {"camera": {"ease_ms": 0}}, FPS, 4200)
        self.assertEqual(f["camera_ease"], {"ease_ms": 0, "curve": "bezier", "runs": []})

    def test_on(self):
        f, w = ce().spec_fields([seg(0, 24), seg(24, 72, "punch_in", 1.1, "P"), seg(72, 100)],
                                {"fades": {"video_in_ms": 500}}, FPS, 4200)
        self.assertEqual(f["camera_ease"]["ease_ms"], 250)
        self.assertEqual(len(f["camera_ease"]["runs"]), 1)
        self.assertEqual(f["fades"]["video_in_ms"], 500)
        self.assertEqual(w, [])

    def test_warnings_come_back(self):
        _, w = ce().spec_fields([seg(0, 100)], {"camera": {"ease_ms": "fast"}, "fades": {"audio_in_ms": -1}}, FPS, 4200)
        self.assertEqual(len(w), 2, w)


class TestPreviewValues(unittest.TestCase):
    """For the preview renderer (wired later, after T4.10): the eased value at a frame, and the fade gain."""

    def spec(self):
        segs = [seg(0, 24), seg(24, 72, "punch_in", 1.1, "P", oy=-40.0), seg(72, 100)]
        f, _ = ce().spec_fields(segs, {"fades": {"video_in_ms": 1000, "video_out_ms": 1000}}, FPS, 100 * 1000 / FPS)
        return dict(f, main_segments=segs, duration_frames=100, fps=FPS)

    def test_scale_runs_from_the_neighbour_to_the_punch(self):
        s = self.spec()
        v = ce().value_at
        self.assertAlmostEqual(v(s, 1, 0)["scale_factor"], 1.0)
        self.assertAlmostEqual(v(s, 1, E24)["scale_factor"], 1.1)
        mid = v(s, 1, 3)["scale_factor"]
        self.assertTrue(1.0 < mid < 1.1, mid)
        self.assertLess(v(s, 1, 1)["scale_factor"] - 1.0, 0.1 / E24)        # eased: a slow start, not linear
        self.assertAlmostEqual(v(s, 1, 48)["scale_factor"], 1.0)           # end of the ease out
        self.assertAlmostEqual(v(s, 1, 24)["offset_y"], -40.0)
        self.assertAlmostEqual(v(s, 0, 10)["scale_factor"], 1.0)            # a piece without keys: its own value

    def test_r3_slow_push_is_intermediate_across_its_piece(self):
        segs = [seg(0, 24), seg(24, 72, "slow_push", 1.2, "S"), seg(72, 100)]
        f, _ = ce().spec_fields(segs, {}, FPS, 100 * 1000 / FPS)
        s = dict(f, main_segments=segs, duration_frames=100, fps=FPS)
        v = ce().value_at
        self.assertAlmostEqual(v(s, 1, 0)["scale_factor"], 1.0)
        mid = v(s, 1, 24)["scale_factor"]
        self.assertTrue(1.05 < mid < 1.15, mid)
        self.assertAlmostEqual(v(s, 1, 47)["scale_factor"], 1.2)

    def test_fade_gain(self):
        s = self.spec()
        g = ce().fade_gain
        self.assertAlmostEqual(g(s, 0, "video"), 0.0)
        self.assertAlmostEqual(g(s, 24, "video"), 1.0)
        self.assertTrue(0 < g(s, 12, "video") < 1)
        self.assertAlmostEqual(g(s, 100, "video"), 0.0)
        self.assertAlmostEqual(g(s, 50, "audio"), 1.0)                      # no audio fade asked
        self.assertFalse(math.isnan(g(s, 50, "video")))


class TestEditorWording(unittest.TestCase):
    def test_i4_the_reapproval_line_has_no_developer_words(self):
        msg = ce().EASE_REAPPROVE
        self.assertIn("smooth zoom added to the punch-ins", msg["en"])
        self.assertTrue(msg["en"].endswith("."))                                      # review 2: the closing period
        self.assertEqual(msg["ar"], "اتضاف زوم ناعم على الـ punch-ins. بص على الخطة بصّة كمان ووافق عليها تاني.")
        self.assertTrue(msg["ar"].strip())
        for lang in ("en", "ar"):
            self.assertNotIn("ease_ms", msg[lang])
            self.assertNotIn("camera.", msg[lang])


class TestShippedDefaults(unittest.TestCase):
    def test_defaults_style_json_has_the_keys(self):
        st = json.loads((SK / "config" / "defaults" / "style.json").read_text(encoding="utf-8"))
        self.assertEqual(st.get("camera", {}).get("ease_ms"), 250)
        self.assertEqual(st.get("fades"), {"video_in_ms": 0, "video_out_ms": 0, "audio_in_ms": 0, "audio_out_ms": 0})


class TestReachableFromTheSkills(unittest.TestCase):
    """Global constraint: new behaviour reachable from the skills; the host calls listed for UXP parity."""

    def test_skills_name_the_knobs(self):
        text = "".join(p.read_text(encoding="utf-8") for p in (SK / "skills").rglob("*.md"))
        self.assertIn("camera.ease_ms", text)
        self.assertIn("fades", text)
        self.assertIn("video_in_ms", text)

    def test_uxp_parity_lists_the_keyframe_calls(self):
        doc = (SK.parent / "docs" / "adobe" / "uxp-parity.md").read_text(encoding="utf-8")
        self.assertIn("setInterpolationTypeAtKey", doc)
        self.assertIn("T4.1", doc)

    def test_r3_uxp_parity_names_what_the_uxp_port_needs(self):
        doc = (SK.parent / "docs" / "adobe" / "uxp-parity.md").read_text(encoding="utf-8")
        i = doc.index("## Pending ops")
        block = doc[i:doc.index("## Decisions summary", i)]
        for want in ("createSetInterpolationAtKeyframeAction", "getTemporalInterpolationMode", "createAddKeyframeAction",
                     "| P6 |", "matte", "caption", "not measured", "slow_push"):
            self.assertIn(want, block)


if __name__ == "__main__":
    unittest.main()
