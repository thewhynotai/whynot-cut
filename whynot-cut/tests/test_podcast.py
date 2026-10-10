"""Podcast mode (2.1): episode intake, chunked transcription, reels plan, Gate 0, source window, per-shot reframe,
recipes, publish package. Run:
    ~/.whynot-cut/venv/bin/python -m unittest discover -s <plugin>/tests -p test_podcast.py -v
"""
import sys as _sys
_sys.dont_write_bytecode = True
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SK = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SK / "engine" / "reel"))

from lib import common  # noqa: E402
from lib.common import Paths, write_json, read_json  # noqa: E402

SHEET = """---
show: بودكاست التجربة
episode: 12
host: "Ahmed"
guest: "Sara — CEO"
links:
  - https://www.instagram.com/sara.ceo/
avoid: [السياسة, دين]
language: ar
---
Notes about the episode.
"""


def ff(*args):
    subprocess.run([common.ffmpeg_exe(), "-y", "-loglevel", "error", *args], check=True)


def make_episode_client(tmp: Path, dur_s: float = 20, fps: int = 25, size: str = "1280x720", name: str = "EP12.mp4",
                        with_clip: bool = True) -> Path:
    """Client folder with data/Episodes/<name> (16:9 testsrc2 + sine), its sheet and (optionally) a Raw clip."""
    root = tmp / "PODCLIENT"
    for d in ("assets/Brand", "assets/Logo", "data/Episodes", "data/Raw"):
        (root / d).mkdir(parents=True, exist_ok=True)
    (root / "assets/Brand/brief.md").write_text("# Brand\nPrimary #20ACAF and #FFFFFF\n", encoding="utf-8")
    ff("-f", "lavfi", "-i", f"testsrc2=s={size}:r={fps}:d={dur_s}", "-f", "lavfi", "-i", f"sine=f=440:r=48000:d={dur_s}",
       "-ac", "2", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(root / "data/Episodes" / name))
    (root / "data/Episodes" / (Path(name).stem + ".md")).write_text(SHEET, encoding="utf-8")
    if with_clip:
        ff("-f", "lavfi", "-i", "testsrc2=s=216x384:r=25:d=3", "-f", "lavfi", "-i", "sine=f=440:r=48000:d=3",
           "-ac", "2", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "pcm_s16le", "-shortest",
           str(root / "data/Raw/CLIP1.mov"))
    return root


class TestEpisodeIntake(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp())
        cls.root = make_episode_client(cls.tmp)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_parse_sheet(self):
        from lib.episode import parse_sheet
        s = parse_sheet("---\nguest: \"Sara — CEO\"\nlinks:\n  - https://a.com/x\navoid: [السياسة, دين]\n---\nnotes")
        self.assertEqual(s["guest"], "Sara — CEO")
        self.assertEqual(s["links"], ["https://a.com/x"])
        self.assertEqual(s["avoid"], ["السياسة", "دين"])
        self.assertIn("notes", s["_notes"])
        self.assertIn("https://a.com/x", s["_text"])

    def test_discover_roles(self):
        from lib.discover import run_discovery
        inv = run_discovery(Paths(self.root))["inventory"]
        roles = {f["rel"]: f["role"] for f in inv["files"]}
        self.assertEqual(roles["data/Episodes/EP12.mp4"], "episode")
        self.assertEqual(roles["data/Episodes/EP12.md"], "episode_sheet")
        self.assertEqual(roles["data/Raw/CLIP1.mov"], "source_footage")

    def test_episode_ids_unique_for_arabic_names(self):
        from lib.episode import episode_id_for
        a, b = episode_id_for(Path("حلقة 12.mp4")), episode_id_for(Path("الحلقة.mov"))
        self.assertNotEqual(a, b)
        self.assertEqual(a, episode_id_for(Path("حلقة 12.mp4")))
        for x in (a, b):
            self.assertRegex(x, r"^[A-Z0-9_]+$")
        self.assertEqual(episode_id_for(Path("EP12.mp4")), "EP12")

    def test_list_and_prep(self):
        from lib.episode import EpisodePaths, list_episodes, prep
        eps = list_episodes(self.root)
        self.assertEqual([e["episode_id"] for e in eps], ["EP12"])
        self.assertEqual(eps[0]["state"], "new")
        self.assertEqual(eps[0]["sheet"], "data/Episodes/EP12.md")
        ep = EpisodePaths(self.root, "EP12")
        r = prep(ep)
        info = read_json(ep.p("00_inputs/episode.json"))
        self.assertAlmostEqual(info["duration_ms"], 20000, delta=100)
        self.assertEqual(info["sheet"]["guest"], "Sara — CEO")
        frames = sorted(ep.p("00_inputs/intake").glob("frame_0*.jpg"))
        self.assertEqual(len(frames), 6)
        self.assertTrue(ep.p("00_inputs/intake/_intake_sheet.jpg").exists())
        self.assertGreater(r["estimate_minutes"]["cpu"], r["estimate_minutes"]["gpu"])
        self.assertEqual(list_episodes(self.root)[0]["state"], "prepared")

    def test_cli_episode_commands(self):
        cli = SK / "engine/reel/cli.py"
        own = make_episode_client(Path(tempfile.mkdtemp(dir=self.tmp)), dur_s=6, with_clip=False)   # isolated state
        r = subprocess.run([sys.executable, "-B", str(cli), "--root", str(own), "episode-prep"],
                           capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(r.returncode, 0, r.stderr[-800:])
        self.assertEqual(json.loads(r.stdout)["episode_id"], "EP12")      # the only episode is picked automatically
        r = subprocess.run([sys.executable, "-B", str(cli), "episodes", "--root", str(own)],
                           capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(json.loads(r.stdout)["episodes"][0]["state"], "prepared")

    def test_inbox_lists_episodes(self):
        from lib.onboard import inbox
        r = inbox(self.root)
        self.assertEqual(r["episodes"][0]["episode_id"], "EP12")
        self.assertEqual([c["video_id"] for c in r["clips"]], ["CLIP1"])


if __name__ == "__main__":
    unittest.main()
