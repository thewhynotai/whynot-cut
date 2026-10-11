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


# ===================================================================================================== G66
PLUGIN_JSON = json.loads((SK / ".claude-plugin/plugin.json").read_text(encoding="utf-8"))
VERSION = PLUGIN_JSON["version"]
TAG = f"WhyNot Cut {VERSION}"


def fake_plugin(root: Path, name: str, version: str) -> Path:
    """A plugin folder with a bin/reel (and reel.cmd) and its manifest; returns its bin dir."""
    (root / "bin").mkdir(parents=True)
    (root / ".claude-plugin").mkdir()
    (root / ".claude-plugin/plugin.json").write_text(json.dumps({"name": name, "version": version}), encoding="utf-8")
    for n in ("reel", "reel.cmd"):
        f = root / "bin" / n
        f.write_text("#!/usr/bin/env bash\necho hi\n", encoding="utf-8")
        f.chmod(0o755)
    return root / "bin"


class TestG66ReelIdentity(unittest.TestCase):
    """A Claude session started before the install keeps the OLD plugin's bin/ on PATH: `reel` is the old reel-editor
    ("environment not installed") and subagents inherit it. WhyNot Cut names itself and finds the impostor."""

    def setUp(self):
        import os
        from lib import selfid
        self.os, self.selfid = os, selfid
        self.tmp = Path(tempfile.mkdtemp())
        self.own = Path(selfid.own_bin())

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def path(self, *dirs):
        return self.os.pathsep.join(str(d) for d in dirs)

    def test_tag_names_plugin_and_version_from_plugin_json(self):
        self.assertEqual(self.selfid.tag(), TAG)
        info = self.selfid.plugin_info()
        self.assertEqual((info["name"], info["version"]), ("whynot-cut", VERSION))

    def test_own_reel_first_is_ok(self):
        old = fake_plugin(self.tmp / "reel-editor", "reel-editor", "1.0.7")
        r = self.selfid.scan_path(self.path(self.own, old))
        self.assertTrue(r["ok"], r)
        self.assertEqual(r["state"], "ok")
        self.assertTrue(r["hits"][0]["is_this"])
        self.assertFalse(r["hits"][1]["is_this"])            # listed, but harmless behind ours

    def test_old_reel_editor_first_is_reported_with_the_fix(self):
        old = fake_plugin(self.tmp / "reel-editor" / "1.0.7", "reel-editor", "1.0.7")
        r = self.selfid.scan_path(self.path(old, self.own))
        self.assertFalse(r["ok"])
        self.assertEqual(r["state"], "foreign_first")
        first = r["first"]
        self.assertEqual((first["plugin"], first["version"]), ("reel-editor", "1.0.7"))
        self.assertFalse(first["is_this"])
        self.assertEqual(Path(first["path"]).parent.resolve(), old.resolve())
        self.assertIn("restart Claude Code", r["fix"])
        self.assertIn(str(self.own), r["fix"])                # the full path to call meanwhile
        self.assertIn("reel-editor", r["message"])
        self.assertIn("1.0.7", r["message"])

    def test_another_copy_of_whynot_cut_first_is_also_wrong(self):
        """A session opened before an UPDATE keeps the previous version's folder first."""
        older = fake_plugin(self.tmp / "whynot-cut" / "2.1.1", "whynot-cut", "2.1.1")
        r = self.selfid.scan_path(self.path(older, self.own))
        self.assertEqual(r["state"], "foreign_first")
        self.assertEqual((r["first"]["plugin"], r["first"]["version"]), ("whynot-cut", "2.1.1"))
        self.assertIn("2.1.1", r["message"])

    def test_unknown_reel_first_is_reported_without_a_manifest(self):
        d = self.tmp / "tools"
        d.mkdir()
        for n in ("reel", "reel.cmd"):
            (d / n).write_text("x", encoding="utf-8")
            (d / n).chmod(0o755)
        r = self.selfid.scan_path(self.path(d, self.own))
        self.assertEqual(r["state"], "foreign_first")
        self.assertIsNone(r["first"]["plugin"])

    def test_no_reel_on_path_is_not_ok_either(self):
        empty = self.tmp / "empty"
        empty.mkdir()
        r = self.selfid.scan_path(self.path(empty))
        self.assertFalse(r["ok"])
        self.assertEqual(r["state"], "not_on_path")
        self.assertIn(str(self.own), r["fix"])

    def test_doctor_reports_the_foreign_reel_and_the_fix(self):
        from unittest import mock
        from lib import onboard
        old = fake_plugin(self.tmp / "reel-editor" / "1.0.7", "reel-editor", "1.0.7")
        with mock.patch.dict(self.os.environ, {"PATH": self.path(old, self.own)}):
            rep = onboard.doctor()
        self.assertEqual(rep["plugin"]["version"], VERSION)
        self.assertEqual(rep["reel_command"]["state"], "foreign_first")
        fix = next(f for f in rep["fixes"] if "reel" in f["item"] and "PATH" in f["item"])
        self.assertIn("reel-editor", fix["item"])
        self.assertIn("restart Claude Code", fix["fix"])
        self.assertFalse(rep["ready"]["reel_command"])

    def test_doctor_is_quiet_when_reel_is_ours(self):
        from unittest import mock
        from lib import onboard
        with mock.patch.dict(self.os.environ, {"PATH": self.path(self.own)}):
            rep = onboard.doctor()
        self.assertEqual(rep["reel_command"]["state"], "ok")
        self.assertTrue(rep["ready"]["reel_command"])
        self.assertFalse([f for f in rep["fixes"] if "PATH" in f["item"]])


class TestG66ReelNamesItself(unittest.TestCase):
    CLI = SK / "engine/reel/cli.py"

    def cli(self, *args, cwd=None):
        return subprocess.run([sys.executable, "-B", str(self.CLI), *args], capture_output=True, text=True,
                              encoding="utf-8", cwd=cwd)

    def test_version_flag_prints_plugin_name_and_version(self):
        r = self.cli("--version")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout.strip().splitlines()[0], TAG)      # line 2 is the plugin root (T1.10)

    def test_errors_start_with_the_plugin_name_and_version(self):
        with tempfile.TemporaryDirectory() as t:
            r = self.cli("next", cwd=t)                       # no --root, not inside a client folder
        self.assertNotEqual(r.returncode, 0)
        self.assertTrue(r.stderr.strip().startswith(f"{TAG}: "), r.stderr)
        self.assertIn("--root required", r.stderr)

    def test_usage_errors_name_it_too(self):
        r = self.cli("no-such-command")
        self.assertEqual(r.returncode, 2)
        self.assertIn(TAG, r.stderr)

    def test_bash_wrapper_blocked_message_names_the_plugin(self):
        import os
        bash = next((b for b in (os.environ.get("GIT_BASH"), r"C:\Program Files\Git\bin\bash.exe", shutil.which("bash"))
                     if b and Path(b).exists() and "system32" not in b.lower()), None)
        if not bash:
            self.skipTest("no bash")
        with tempfile.TemporaryDirectory() as t:
            r = subprocess.run([bash, str(SK / "bin/reel"), "doctor"], capture_output=True, text=True, encoding="utf-8",
                               env={**os.environ, "WHYNOT_HOME": t})
        self.assertEqual(r.returncode, 2, r.stderr)
        blocked = json.loads(r.stdout.strip().splitlines()[-1])
        self.assertIn(TAG, blocked["blocked"])
        self.assertIn("engine not installed", blocked["blocked"])

    @unittest.skipUnless(sys.platform == "win32", "reel.cmd is the Windows wrapper")
    def test_cmd_wrapper_blocked_message_names_the_plugin(self):
        import os
        with tempfile.TemporaryDirectory() as t:
            r = subprocess.run(["cmd", "/c", str(SK / "bin/reel.cmd"), "doctor"], capture_output=True, text=True,
                               encoding="utf-8", env={**os.environ, "WHYNOT_HOME": t})
        self.assertEqual(r.returncode, 2, r.stderr)
        blocked = json.loads(r.stdout.strip().splitlines()[-1])
        self.assertIn(TAG, blocked["blocked"])
        self.assertIn("engine not installed", blocked["blocked"])


class TestG66SkillsTellTheStory(unittest.TestCase):
    def test_start_and_setup_skills_cover_the_wrong_reel(self):
        for rel in ("skills/start/SKILL.md", "skills/setup/SKILL.md"):
            text = (SK / rel).read_text(encoding="utf-8")
            for needle in ("reel --version", "restart Claude Code", "full path", "reel-editor"):
                self.assertIn(needle, text, f"{rel} lacks {needle!r}")


# ===================================================================================================== G69
FIX = Path(__file__).resolve().parent / "fixtures"
REAL_SLATE = FIX / "media_pending_1080x1920.png"      # a real Premiere 26.5 "Media pending" frame (EP02TEST_R02, run 1)
REAL_CLEAN = sorted(FIX.glob("clean_*_270x480.jpg"))    # real clean frames exported by the same Premiere


def _lines(draw, x0, y0, n, line_h, width, colour=(255, 255, 255), seed=3):
    """Stand-in for text: n lines of 'words' made of thin strokes (like the slate's multi-language block)."""
    rng = np.random.default_rng(seed)
    stroke = max(2, int(line_h * 0.12))
    for i in range(n):
        x, y = x0, y0 + i * int(line_h * 1.6)
        while x < x0 + width * (0.55 + 0.45 * rng.random()):
            for _ in range(int(rng.integers(3, 8))):                  # one letter-ish: a few thin bars
                draw.rectangle([x, y, x + stroke, y + int(line_h * 0.7)], fill=colour)
                x += stroke * 3
            x += int(line_h * 0.5)                                   # word gap


def slate_gradient_left(w=1080, h=1920):
    """Like the real one: vertical yellow -> olive gradient, a left-aligned multi-line white block."""
    from PIL import Image, ImageDraw
    top, bot = np.array([212, 197, 71.0]), np.array([107, 94, 40.0])
    col = (top[None, :] * (1 - np.linspace(0, 1, h)[:, None]) + bot[None, :] * np.linspace(0, 1, h)[:, None])
    im = Image.fromarray(np.repeat(col[:, None, :], w, axis=1).astype(np.uint8))
    _lines(ImageDraw.Draw(im), int(w * 0.26), int(h * 0.2), 9, int(h * 0.03), int(w * 0.5))
    return im


def slate_dark_centre(w=1080, h=1920):
    """The other slate people remember: near-uniform dark grey, one small centred text line."""
    from PIL import Image, ImageDraw
    im = Image.new("RGB", (w, h), (38, 38, 38))
    _lines(ImageDraw.Draw(im), int(w * 0.36), int(h * 0.49), 1, int(h * 0.022), int(w * 0.28), colour=(235, 235, 235))
    return im


def slate_landscape(w=1920, h=1080):
    from PIL import Image, ImageDraw
    im = Image.new("RGB", (w, h), (60, 66, 72))
    _lines(ImageDraw.Draw(im), int(w * 0.38), int(h * 0.44), 2, int(h * 0.035), int(w * 0.24), colour=(240, 240, 240))
    return im


def not_a_slate_images():
    """Frames that must never be taken for the slate."""
    from PIL import Image, ImageDraw
    rng = np.random.default_rng(1)
    out = {}
    out["black"] = Image.new("RGB", (1080, 1920), (0, 0, 0))
    out["flat grey, no text"] = Image.new("RGB", (1080, 1920), (60, 60, 60))
    out["noise"] = Image.fromarray(rng.integers(0, 255, (480, 270, 3), dtype=np.uint8)).resize((1080, 1920))
    wall = Image.new("RGB", (1080, 1920), (240, 240, 238))        # a speaker on a white backdrop
    d = ImageDraw.Draw(wall)
    d.ellipse([400, 450, 680, 800], fill=(190, 150, 125))
    d.rectangle([270, 800, 810, 1920], fill=(30, 30, 45))
    out["person on white wall"] = wall
    card = slate_gradient_left()                                    # same background, but a big photo in the middle
    ImageDraw.Draw(card).rectangle([180, 300, 900, 1500], fill=(90, 120, 160))
    out["gradient with a big picture"] = card
    split = Image.new("RGB", (1080, 1920), (20, 20, 20))            # left half dark, right half bright: not a slate
    ImageDraw.Draw(split).rectangle([540, 0, 1080, 1920], fill=(200, 200, 200))
    out["split screen"] = split
    return out


class TestG69PendingDetector(unittest.TestCase):
    def setUp(self):
        from lib import media_pending
        self.mp = media_pending

    def test_the_real_premiere_slate_is_detected(self):
        self.assertTrue(REAL_SLATE.exists(), "fixture missing")
        self.assertTrue(self.mp.is_media_pending(REAL_SLATE), self.mp.pending_metrics(REAL_SLATE))

    def test_real_clean_premiere_frames_are_not(self):
        self.assertGreaterEqual(len(REAL_CLEAN), 3)
        for f in REAL_CLEAN:
            self.assertFalse(self.mp.is_media_pending(f), (f.name, self.mp.pending_metrics(f)))

    def test_synthetic_slates_are_detected(self):
        for name, im in (("gradient+left block", slate_gradient_left()), ("dark+centre line", slate_dark_centre()),
                         ("landscape", slate_landscape()), ("small 540x960", slate_gradient_left(540, 960))):
            self.assertTrue(self.mp.is_media_pending(im), (name, self.mp.pending_metrics(im)))

    def test_a_jpeg_compressed_slate_is_still_detected(self):
        import io
        from PIL import Image
        buf = io.BytesIO()
        slate_gradient_left().save(buf, "JPEG", quality=60)
        self.assertTrue(self.mp.is_media_pending(Image.open(io.BytesIO(buf.getvalue()))))

    def test_ordinary_frames_are_not_slates(self):
        for name, im in not_a_slate_images().items():
            self.assertFalse(self.mp.is_media_pending(im), (name, self.mp.pending_metrics(im)))

    def test_metrics_explain_the_decision(self):
        m = self.mp.pending_metrics(REAL_SLATE)
        for k in ("pending", "row_constancy", "smoothness", "text_fraction", "fill"):
            self.assertIn(k, m)
        self.assertTrue(m["pending"])


class FakeBridge:
    """Stands in for ppro_bridge.submit: writes one PNG per requested time; `pending_for[ms]` = how many exports of that
    frame still come out as the Media pending slate (media loading)."""

    def __init__(self, pending_for=None, fail_after=None):
        self.calls, self.pending_for = [], dict(pending_for or {})

    def __call__(self, action, payload, timeout=0, **kw):
        from PIL import Image
        self.calls.append(list(payload["times"]))
        frames = []
        for t in payload["times"]:
            ms = round(t * 1000)
            out = Path(payload["out_dir"]) / ("frame_%06d.png" % ms)
            n = self.pending_for.get(ms, 0)
            if n > 0:
                self.pending_for[ms] = n - 1
                shutil.copyfile(REAL_SLATE, out)
            else:
                rng = np.random.default_rng(ms)
                Image.fromarray(rng.integers(0, 255, (240, 135, 3), dtype=np.uint8)).save(out)
            frames.append({"t": t, "file": str(out), "called": True})
        return {"ok": True, "elapsed_s": 0.1, "response": {"ok": True, "result": {"frames": frames}}}


class TestG69ExportRetry(unittest.TestCase):
    TIMES = [1.0, 2.5, 3.75, 5.0, 6.5, 8.0]

    def setUp(self):
        from lib.common import Paths, write_json
        self.tmp = Path(tempfile.mkdtemp())
        root = self.tmp / "C"
        (root / "assets").mkdir(parents=True)
        (root / "data").mkdir()
        self.p = Paths(root, "V1")
        self.p.ensure_project()
        write_json(self.p.p("01_analysis/timeline-spec.json"), {"events": [], "duration_frames": 240})

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def export(self, bridge, times=None, **kw):
        from unittest import mock
        from lib import ppro_build
        with mock.patch("lib.ppro_bridge.submit", bridge), mock.patch("time.sleep") as sleep:
            r = ppro_build.export_frames(self.p, times=times or self.TIMES, **kw)
        return r, sleep

    def test_clean_export_is_one_bridge_call_and_no_wait(self):
        b = FakeBridge()
        r, sleep = self.export(b)
        self.assertTrue(r["ok"], r)
        self.assertEqual((r["frames"], r["expected"], r["media_pending"]), (6, 6, []))
        self.assertEqual(len(b.calls), 1)
        sleep.assert_not_called()

    def test_pending_frames_are_re_exported_after_a_wait(self):
        """Seen live: 4 of 17 frames were the slate right after the project opened; a second run was clean."""
        b = FakeBridge({2500: 1, 5000: 1})
        r, sleep = self.export(b, wait_s=4.0)
        self.assertTrue(r["ok"], r)
        self.assertEqual((r["frames"], r["media_pending"]), (6, []))
        self.assertEqual(len(b.calls), 2)
        self.assertEqual(sorted(b.calls[1]), [2.5, 5.0])             # only the slate frames are exported again
        sleep.assert_called_once()
        self.assertGreaterEqual(sleep.call_args[0][0], 4.0)
        rec = r["pending_retries"]
        self.assertEqual(rec["attempts"], 1)
        self.assertEqual(sorted(rec["recovered"]), [2.5, 5.0])
        from lib.media_pending import is_media_pending
        self.assertFalse(any(is_media_pending(f) for f in Path(r["dir"]).glob("frame_*.png")))

    def test_it_waits_longer_each_time_and_gives_up_after_n_retries(self):
        b = FakeBridge({3750: 99})                                    # media never comes online
        r, sleep = self.export(b, retries=2, wait_s=3.0)
        self.assertFalse(r["ok"])
        self.assertEqual(len(b.calls), 3)                             # first export + 2 re-exports
        self.assertEqual([c[0][0] for c in sleep.call_args_list], [3.0, 6.0])
        self.assertEqual((r["frames"], r["expected"]), (5, 6))        # the slate frame is not a normal frame
        self.assertEqual([m["t"] for m in r["media_pending"]], [3.75])
        self.assertTrue(r["media_pending"][0]["file"].endswith("frame_003750.png"))
        self.assertEqual(r["media_pending"][0]["retries"], 2)
        self.assertIn("Media pending", r["error"])
        self.assertIn("1 of 6", r["error"])
        self.assertIn("neither a pass nor a fail", r["next"].lower())

    def test_retries_zero_only_reports(self):
        b = FakeBridge({1000: 5})
        r, sleep = self.export(b, retries=0)
        self.assertEqual(len(b.calls), 1)
        sleep.assert_not_called()
        self.assertEqual([m["t"] for m in r["media_pending"]], [1.0])
        self.assertFalse(r["ok"])

    def test_the_sheet_leaves_slate_frames_out(self):
        from PIL import Image
        b = FakeBridge({1000: 99})
        r, _ = self.export(b, times=[1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0], retries=1)
        self.assertTrue(r["sheet"])
        with Image.open(r["sheet"]) as sheet:
            self.assertEqual(sheet.size[1] // (480 + 18), 1)         # 6 clean frames = one row of 6 (7 would be two)

    def test_a_re_export_that_writes_nothing_leaves_the_frame_reported_as_pending(self):
        """The old slate must never turn into a 'normal frame' because the second export failed."""
        class Dying(FakeBridge):
            def __call__(self, action, payload, timeout=0, **kw):
                if len(self.calls) >= 1:                              # the re-export writes nothing
                    self.calls.append(list(payload["times"]))
                    return {"ok": True, "response": {"ok": True, "result": {"frames": []}}}
                return super().__call__(action, payload, timeout, **kw)
        r, _ = self.export(Dying({2500: 9}), retries=1)
        self.assertFalse(r["ok"])
        self.assertEqual(r["frames"], 5)
        self.assertEqual([m["t"] for m in r["media_pending"]], [2.5])
        self.assertTrue(Path(r["media_pending"][0]["file"]).exists())             # the slate is put back, not lost
        self.assertEqual(list(Path(r["dir"]).glob("*.slate")), [])

    def test_a_re_export_never_has_to_overwrite_the_slate(self):
        """Premiere's exportFramePNG might refuse to overwrite: the slate is parked before the re-export."""
        class Strict(FakeBridge):
            def __call__(self, action, payload, timeout=0, **kw):
                if self.calls:                                         # re-export: refuse to overwrite a file
                    for t in payload["times"]:
                        if (Path(payload["out_dir"]) / ("frame_%06d.png" % round(t * 1000))).exists():
                            self.calls.append(list(payload["times"]))
                            return {"ok": True, "response": {"ok": True, "result": {"frames": [
                                {"t": t, "error": "file exists"}]}}}
                return super().__call__(action, payload, timeout, **kw)
        r, _ = self.export(Strict({2500: 1}), retries=1)
        self.assertTrue(r["ok"], r)
        self.assertEqual((r["frames"], r["media_pending"]), (6, []))

    def test_cli_has_the_retry_options(self):
        r = subprocess.run([sys.executable, "-B", str(SK / "engine/reel/cli.py"), "ppro-frames", "--help"],
                           capture_output=True, text=True, encoding="utf-8")
        self.assertIn("--pending-retries", r.stdout)
        self.assertIn("--pending-wait", r.stdout)


class TestG69QcDocs(unittest.TestCase):
    def test_reviewers_treat_media_pending_as_re_export_not_a_verdict(self):
        for rel in ("agents/qc-reviewer.md", "agents/frame-inspector.md", "skills/qc-craft/SKILL.md"):
            text = (SK / rel).read_text(encoding="utf-8")
            self.assertIn("Media pending", text, rel)
            self.assertIn("re-export", text, rel)
        for rel in ("agents/qc-reviewer.md", "skills/qc-craft/SKILL.md"):         # the ones that read the JSON
            self.assertIn("media_pending", (SK / rel).read_text(encoding="utf-8"), rel)


if __name__ == "__main__":
    unittest.main()
