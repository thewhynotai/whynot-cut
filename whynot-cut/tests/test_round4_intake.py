"""Round 4 field-test gaps (Dr Sherin EP02, podcast mode):
  G65  the intake sheet missed the name supers (lower thirds) at 01:27 / 16:55 -> an overlay scan nominates them
  G66  a session started before the install keeps the old plugin's `reel` first on PATH -> WhyNot Cut names itself
  G69  `ppro-frames` right after a project opens exported Premiere's "Media pending" slate -> detect and re-export
Run:
    ~/.whynot-cut/venv/bin/python -m unittest discover -s <plugin>/tests -p test_round4_intake.py -v
"""
import sys as _sys
_sys.dont_write_bytecode = True  # keep the plugin folder free of __pycache__
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np

SK = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SK / "engine" / "reel"))

from lib import common  # noqa: E402
from lib.common import read_json  # noqa: E402

H, W = 180, 320          # the overlay scan works on 320x180 thumbnails (one per second)


# ----------------------------------------------------------------------------------------------- synthetic episode
def make_shot(seed: int, h: int = H, w: int = W) -> np.ndarray:
    """A static 'camera shot': blocky random colours (plenty of edges, like a studio) as float32 (h, w, 3)."""
    rng = np.random.default_rng(seed)
    small = rng.integers(70, 225, size=(9, 16, 3)).astype(np.float32)
    return np.kron(small, np.ones((h // 9, w // 16, 1), dtype=np.float32))


def add_person(img: np.ndarray, t: float) -> None:
    """A dark torso that sways a little (a talking head: small, slow movement)."""
    h, w = img.shape[:2]
    x0 = int(w * 0.38 + 3 * np.sin(t / 2.0))
    img[int(h * 0.30):, x0:x0 + int(w * 0.24)] = (25, 30, 45)


def add_hand(img: np.ndarray, t: float) -> None:
    """A hand-sized blob that wanders across the lower part of the frame."""
    h, w = img.shape[:2]
    x0 = int((t * 23) % (w - 50))
    img[int(h * 0.72):int(h * 0.72) + 28, x0:x0 + 40] = (200, 150, 120)


def add_super(img: np.ndarray, seed: int = 5) -> None:
    """A name super: gold bar anchored left (rows 83-91 %, cols 0-41 %) with white 'text' strokes on it."""
    h, w = img.shape[:2]
    r0, r1, c1 = int(h * 0.83), int(h * 0.91), int(w * 0.41)
    img[r0:r1, :c1] = (205, 170, 85)
    rng = np.random.default_rng(seed)
    for _ in range(26):
        x = int(rng.integers(int(w * 0.03), c1 - 12))
        img[r0 + 2:r1 - 2, x:x + int(rng.integers(2, 8))] = (250, 250, 250)


def make_frames(n: int, cuts: dict[int, int], supers=(), hands=False, seed: int = 0, h: int = H, w: int = W):
    """n one-per-second frames. `cuts` maps start second -> shot seed (the shot runs until the next cut)."""
    rng = np.random.default_rng(seed)
    starts = sorted(cuts)
    out = []
    for t in range(n):
        s = max(x for x in starts if x <= t)
        img = make_shot(cuts[s], h, w).copy()
        add_person(img, t)
        if hands:
            add_hand(img, t)
        if any(a <= t < b for a, b in supers):
            add_super(img)
        img += rng.normal(0, 2.0, img.shape)
        out.append(np.clip(img, 0, 255).astype(np.uint8))
    return np.stack(out)


class TestG65DenseSampling(unittest.TestCase):
    def test_dense_times_cover_the_first_three_minutes(self):
        from lib.overlay_scan import dense_times
        t = dense_times(3600.0)
        self.assertEqual(t, sorted(set(t)))
        self.assertGreaterEqual(len(t), 17)
        self.assertLessEqual(max(t), 180.0)
        gaps = [b - a for a, b in zip(t, t[1:])]
        self.assertLessEqual(max(gaps), 10.0 + 1e-6)

    def test_dense_times_never_pass_the_end_of_a_short_file(self):
        from lib.overlay_scan import dense_times
        t = dense_times(25.0)
        self.assertTrue(t and max(t) < 25.0, t)
        self.assertEqual(dense_times(0.0), [])


class TestG65OverlayDetector(unittest.TestCase):
    """The scan finds a transient, bar-shaped overlay in the lower part of the frame, also when it appears right
    at a camera cut (both real supers of the field test did), and does not call a static shot an overlay."""

    def test_super_at_a_cut_is_found(self):
        from lib.overlay_scan import detect_events
        fr = make_frames(60, {0: 1, 20: 2}, supers=[(20, 23)], hands=True)
        ev = detect_events(fr)
        self.assertTrue(ev, "the name super at 20-23 s was not nominated")
        top = ev[0]
        self.assertTrue(18 <= top["t_s"] <= 28 and (top["start_s"] <= 22 <= top["end_s"] + 1), top)
        x0, y0, x1, y1 = top["box"]
        self.assertGreater(y0, 0.7)                       # lower part of the frame
        self.assertLess(x0, 0.2)                          # anchored left
        self.assertGreater(x1 - x0, 0.30)                 # a wide bar, not a speck
        self.assertGreaterEqual(top["support"], 2)

    def test_super_in_the_middle_of_a_shot_is_found(self):
        from lib.overlay_scan import detect_events
        fr = make_frames(80, {0: 3}, supers=[(40, 44)])
        ev = detect_events(fr)
        self.assertTrue(any(38 <= e["start_s"] <= 44 for e in ev), ev)

    def test_two_supers_are_two_events(self):
        from lib.overlay_scan import detect_events
        fr = make_frames(120, {0: 1, 30: 2, 90: 3}, supers=[(30, 33), (90, 93)], hands=True)
        ev = detect_events(fr)
        starts = sorted(e["start_s"] for e in ev if e["score"] >= 0.5)
        self.assertTrue(any(26 <= s <= 34 for s in starts), starts)
        self.assertTrue(any(86 <= s <= 94 for s in starts), starts)

    def test_nothing_is_nominated_in_a_plain_talking_shot(self):
        from lib.overlay_scan import detect_events
        fr = make_frames(90, {0: 1, 30: 2, 60: 1}, hands=True)       # cuts, a swaying person, wandering hands
        self.assertEqual(detect_events(fr), [])

    def test_a_static_burned_in_overlay_is_not_a_transient_event(self):
        """A logo/bar that never leaves the picture is the 6-frame sheet's job, not a transient candidate."""
        from lib.overlay_scan import detect_events
        fr = make_frames(60, {0: 1}, supers=[(0, 60)])
        self.assertEqual(detect_events(fr), [])

    def test_full_frame_card_changes_are_not_lower_thirds(self):
        from lib.overlay_scan import detect_events
        fr = make_frames(60, {0: 1, 20: 7, 40: 1})                    # whole picture changes at 20 and 40
        self.assertEqual(detect_events(fr), [])


class TestG65ScanBudget(unittest.TestCase):
    def test_scan_reports_what_it_covered_and_stops_at_the_budget(self):
        from lib import overlay_scan
        fr = make_frames(600, {0: 1}, supers=[(30, 33)])
        calls = []

        def decode(src, start_s, length_s):
            calls.append((start_s, length_s))
            a = max(0, int(start_s))
            return fr[a:a + int(length_s)]

        class Clock:                       # every call to the clock advances 100 s
            t = 0.0

            def __call__(self):
                self.t += 100.0
                return self.t
        r = overlay_scan.scan_video("x.mp4", 600.0, decode=decode, clock=Clock(), budget_s=250.0, chunk_s=120.0)
        self.assertFalse(r["complete"])
        self.assertGreater(r["scanned_s"], 0)
        self.assertLess(r["scanned_s"], 600)
        self.assertLess(len(calls), 5)

    def test_scan_walks_the_whole_file_in_chunks(self):
        from lib import overlay_scan
        fr = make_frames(400, {0: 1, 150: 2}, supers=[(150, 153), (330, 333)])

        def decode(src, start_s, length_s):
            a = max(0, int(round(start_s)))
            return fr[a:a + int(round(length_s))]
        r = overlay_scan.scan_video("x.mp4", 400.0, decode=decode, chunk_s=100.0, budget_s=1e9)
        self.assertTrue(r["complete"])
        self.assertAlmostEqual(r["scanned_s"], 400.0, delta=1.0)
        starts = [e["start_s"] for e in r["events"]]
        self.assertTrue(any(146 <= s <= 154 for s in starts), starts)       # inside a chunk, right after a cut
        self.assertTrue(any(326 <= s <= 334 for s in starts), starts)       # in the last chunk
        # chunk borders never split an event into two
        self.assertEqual(len([s for s in starts if 146 <= s <= 160]), 1, starts)


def _ffmpeg(*args):
    subprocess.run([common.ffmpeg_exe(), "-y", "-loglevel", "error", *args], check=True)


def write_episode_with_supers(path: Path, n: int = 150, supers=((87, 90),), h: int = 360, w: int = 640):
    """A 1 fps 16:9 'episode' (+ audio): two shots, a cut at the first super, hands moving about."""
    fr = make_frames(n, {0: 1, supers[0][0]: 2}, supers=list(supers), hands=True, h=h, w=w)
    raw = path.with_suffix(".raw")
    raw.write_bytes(fr.tobytes())
    try:
        _ffmpeg("-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{w}x{h}", "-r", "1", "-i", str(raw),
                "-f", "lavfi", "-i", f"sine=f=440:r=48000:d={n}", "-ac", "2", "-c:v", "libx264", "-preset", "veryfast",
                "-crf", "18", "-pix_fmt", "yuv420p", "-g", "10", "-c:a", "aac", "-shortest", str(path))
    finally:
        raw.unlink(missing_ok=True)


class TestG65EpisodePrep(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp())
        root = cls.tmp / "PODCLIENT"
        for d in ("assets/Brand", "data/Episodes", "data/Raw"):
            (root / d).mkdir(parents=True, exist_ok=True)
        write_episode_with_supers(root / "data/Episodes/EP77.mp4", n=150, supers=((87, 90),))
        cls.root = root

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_prep_nominates_the_super_and_builds_the_extra_sheets(self):
        from lib.episode import EpisodePaths, prep
        ep = EpisodePaths(self.root, "EP77")
        r = prep(ep)
        info = read_json(ep.p("00_inputs/episode.json"))
        scan = info["overlay_scan"]
        self.assertTrue(scan["complete"])
        self.assertTrue(scan["events"], "no overlay candidate recorded")
        best = scan["events"][0]
        self.assertTrue(84 <= best["t_s"] <= 94, best)
        self.assertRegex(best["tc"], r"^\d\d:\d\d")
        self.assertTrue(info["lower_thirds_hint"])
        self.assertTrue(Path(info["supers_sheet"]).exists())
        self.assertTrue(Path(info["head_sheet"]).exists())
        self.assertTrue(any("lower third" in w.lower() or "super" in w.lower() for w in info["warnings"]), info["warnings"])
        self.assertEqual(r["supers_sheet"], info["supers_sheet"])
        # the 6-frame overview sheet is unchanged
        self.assertEqual(len(sorted(ep.p("00_inputs/intake").glob("frame_0*.jpg"))), 6)
        self.assertTrue(ep.p("00_inputs/intake/_intake_sheet.jpg").exists())

    def test_prep_of_an_episode_without_supers_says_so(self):
        from lib.episode import EpisodePaths, prep
        root = self.tmp / "CLEAN"
        for d in ("assets/Brand", "data/Episodes"):
            (root / d).mkdir(parents=True, exist_ok=True)
        write_episode_with_supers(root / "data/Episodes/EP78.mp4", n=70, supers=((0, 0),))
        ep = EpisodePaths(root, "EP78")
        prep(ep)
        info = read_json(ep.p("00_inputs/episode.json"))
        self.assertEqual(info["overlay_scan"]["events"], [])
        self.assertFalse(info["lower_thirds_hint"])
        self.assertIsNone(info["supers_sheet"])
        self.assertTrue(Path(info["head_sheet"]).exists())


if __name__ == "__main__":
    unittest.main()
