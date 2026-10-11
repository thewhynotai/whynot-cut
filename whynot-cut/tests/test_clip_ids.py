"""3.0 T1.3 (engine CR-1): one stable clip id per raw clip, for names with spaces, Arabic, Arabic-Indic digits and
duplicate stems. Every id `reel inbox` hands out is accepted by the per-clip commands (`--video-id`), two clips never
share a project folder, and an id never changes once it is in output/discovery/clip-ids.json.
Run:  <engine venv python> -m unittest discover -s <plugin>/tests -v
"""
import sys as _sys
_sys.dont_write_bytecode = True  # keep the plugin folder free of __pycache__
import hashlib
import importlib.util
import json
import os
import re
import subprocess
import sys
import tempfile
import unicodedata
import unittest
from pathlib import Path

SK = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SK / "engine" / "reel"))

from lib.common import Paths, read_json, write_json  # noqa: E402

CLI = SK / "engine/reel/cli.py"
CTX = SK / "hooks/session_context.py"
SAFE = re.compile(r"[A-Z0-9_]+")              # an id is a folder name on every OS and a plain CLI argument

ARABIC_1 = "مقابلة ١.mp4"                     # Arabic-Indic digits: slug() used to drop the whole name -> VIDEO
ARABIC_2 = "مقابلة ٢.mp4"
ARABIC_3 = "مقابلة 3.mp4"                     # ASCII digit: slug() used to give just "3"
RAW = ["C0239.MP4", "C0239.mov", "Dr Sherif intro.mp4", "Dr Sherif outro.mp4", ARABIC_1, ARABIC_2]


def h6(text: str) -> str:
    return hashlib.sha1(unicodedata.normalize("NFC", text).encode("utf-8")).hexdigest()[:6].upper()


def make_client(tmp, names=RAW) -> Path:
    root = Path(tmp) / "Dr Test"
    for d in ("assets/Brand", "data/Raw"):
        (root / d).mkdir(parents=True)
    for i, n in enumerate(names):
        (root / "data/Raw" / n).write_bytes(b"raw clip %d" % i)
    return root


def cli_module():
    spec = importlib.util.spec_from_file_location("reel_cli_t13", CLI)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def reel(root: Path, *argv, video_id=None):
    cmd = [sys.executable, "-B", str(CLI), "--root", str(root)] + (["--video-id", video_id] if video_id else []) + list(argv)
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")
    return r.returncode, (json.loads(r.stdout) if r.stdout.strip().startswith("{") else r.stdout), r.stderr


class TestClipIdRule(unittest.TestCase):
    def test_ascii_names_keep_their_slug(self):
        from lib.clip_ids import clip_id_for
        self.assertEqual(clip_id_for("data/Raw/C0239.MP4"), "C0239")
        self.assertEqual(clip_id_for("data/Raw/Dr Sherif intro.mp4"), "DR_SHERIF_INTRO")
        self.assertEqual(clip_id_for("data/Raw/dr_sherif_intro.mp4"), "DR_SHERIF_INTRO")

    def test_arabic_names_get_a_short_stable_hash(self):
        from lib.clip_ids import clip_id_for
        a, b = clip_id_for("data/Raw/" + ARABIC_1), clip_id_for("data/Raw/" + ARABIC_2)
        self.assertNotEqual(a, b)                                    # both used to be VIDEO
        self.assertEqual(a, "CLIP_" + h6("مقابلة ١"))
        self.assertEqual(clip_id_for("data/Raw/" + ARABIC_3), "CLIP_3_" + h6("مقابلة 3"))
        self.assertEqual(a, clip_id_for("data/Raw/" + ARABIC_1))     # stable
        for i in (a, b):
            self.assertTrue(SAFE.fullmatch(i), i)

    def test_nfd_names_from_macos_get_the_same_id(self):
        from lib.clip_ids import clip_id_for
        self.assertEqual(clip_id_for(unicodedata.normalize("NFD", "data/Raw/Café intro.mov")),
                         clip_id_for(unicodedata.normalize("NFC", "data/Raw/Café intro.mov")))

    def test_same_stem_other_extension_gets_a_dedup_suffix(self):
        from lib.clip_ids import clip_id_for
        taken = {"C0239": "data/Raw/C0239.MP4"}
        self.assertEqual(clip_id_for("data/Raw/C0239.mov", taken), "C0239_MOV")
        ar = clip_id_for("data/Raw/" + ARABIC_1)
        self.assertEqual(clip_id_for("data/Raw/مقابلة ١.mov", {ar: "data/Raw/" + ARABIC_1}), ar + "_MOV")

    def test_colliding_ascii_names_get_a_hash(self):
        from lib.clip_ids import clip_id_for
        taken = {"DR_SHERIF_INTRO": "data/Raw/Dr Sherif intro.mp4"}
        self.assertEqual(clip_id_for("data/Raw/dr-sherif-intro.mp4", taken), "DR_SHERIF_INTRO_" + h6("dr-sherif-intro"))

    def test_never_returns_a_taken_id(self):
        from lib.clip_ids import clip_id_for
        taken = {}
        for rel in ["data/Raw/C0239.MP4", "data/Raw/C0239.mov", "data/Raw/day2/C0239.MP4", "data/Raw/day3/C0239.MP4",
                    "data/Raw/c0239.MP4"]:
            i = clip_id_for(rel, taken)
            self.assertNotIn(i.upper(), {k.upper() for k in taken}, rel)
            taken[i] = rel
        self.assertEqual(len(taken), 5)

    def test_episode_ids_unchanged_by_the_shared_helper(self):
        from lib.episode import episode_id_for
        self.assertEqual(episode_id_for(Path("EP12.mp4")), "EP12")
        self.assertEqual(episode_id_for(Path("حلقة 12.mp4")), "EP_12_" + h6("حلقة 12"))
        self.assertEqual(episode_id_for(Path("الحلقة.mov")), "EP_" + h6("الحلقة"))
        self.assertEqual(episode_id_for(Path("###.mp4")), "EP_" + h6("###"))


class TestClipIdMap(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = make_client(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def ids(self):
        return read_json(self.root / "output/discovery/clip-ids.json")

    def test_inbox_hands_out_unique_safe_ids_and_persists_them(self):
        from lib.onboard import inbox
        ib = inbox(self.root)
        got = {c["file"]: c["video_id"] for c in ib["clips"]}
        self.assertEqual(len(got), len(RAW))
        self.assertEqual(len(set(got.values())), len(RAW))            # two clips never share a project folder
        self.assertEqual(got["data/Raw/C0239.MP4"], "C0239")
        self.assertEqual(got["data/Raw/C0239.mov"], "C0239_MOV")
        self.assertEqual(got["data/Raw/Dr Sherif intro.mp4"], "DR_SHERIF_INTRO")
        self.assertEqual(got["data/Raw/" + ARABIC_1], "CLIP_" + h6("مقابلة ١"))
        self.assertEqual(got["data/Raw/" + ARABIC_2], "CLIP_" + h6("مقابلة ٢"))
        for i in got.values():
            self.assertTrue(SAFE.fullmatch(i), i)
        self.assertEqual(self.ids(), {v: k for k, v in got.items()})  # {id: relative path}
        self.assertEqual(sorted(ib["new"]), sorted(got.values()))

    def test_ids_never_change_once_assigned(self):
        from lib.onboard import inbox
        first = {c["file"]: c["video_id"] for c in inbox(self.root)["clips"]}
        self.assertEqual({c["file"]: c["video_id"] for c in inbox(self.root)["clips"]}, first)   # re-run: same
        (self.root / "data/Raw" / ARABIC_1).unlink()                 # a clip goes away: its id stays reserved
        (self.root / "data/Raw/مقابلة ١.mov").write_bytes(b"same name, other container")
        (self.root / "data/Raw/day2").mkdir()
        (self.root / "data/Raw/day2/C0239.MP4").write_bytes(b"same stem, other folder")
        again = {c["file"]: c["video_id"] for c in inbox(self.root)["clips"]}
        for rel, i in first.items():
            if rel != "data/Raw/" + ARABIC_1:
                self.assertEqual(again[rel], i, rel)
        m = self.ids()
        self.assertEqual(m[first["data/Raw/" + ARABIC_1]], "data/Raw/" + ARABIC_1)
        self.assertEqual(again["data/Raw/مقابلة ١.mov"], first["data/Raw/" + ARABIC_1] + "_MOV")
        self.assertNotIn(again["data/Raw/day2/C0239.MP4"], first.values())
        self.assertEqual(len(m), len(set(m)), m)
        self.assertEqual(len(m), len(RAW) + 2)

    def test_every_inbox_id_resolves_to_its_own_clip(self):
        from lib.onboard import inbox
        cli = cli_module()
        for c in inbox(self.root)["clips"]:
            f = cli.main_footage(Paths(self.root, c["video_id"]), None)
            self.assertEqual([x.name for x in f], [Path(c["file"]).name], c)
            low = cli.main_footage(Paths(self.root, c["video_id"].lower()), None)    # ids are case-insensitive
            self.assertEqual([x.name for x in low], [Path(c["file"]).name], c)

    def test_raw_stem_and_old_slug_still_resolve(self):
        from lib.onboard import inbox
        (self.root / "data/Raw" / ARABIC_3).write_bytes(b"third interview")
        inbox(self.root)
        cli = cli_module()
        one = lambda vid: [x.name for x in cli.main_footage(Paths(self.root, vid), None)]   # noqa: E731
        self.assertEqual(one("Dr Sherif intro"), ["Dr Sherif intro.mp4"])           # raw stem
        self.assertEqual(one("مقابلة ٢"), [ARABIC_2])                                 # raw Arabic stem
        self.assertEqual(one("3"), [ARABIC_3])                                        # the old slug, unique
        with self.assertRaises(SystemExit) as e:
            one("VIDEO")                                     # old slug shared by two Arabic clips: never guess
        self.assertIn("CLIP_", str(e.exception.code))                                  # names the real ids

    def test_every_inbox_id_is_accepted_by_a_per_clip_command(self):
        from lib.onboard import inbox
        for c in inbox(self.root)["clips"]:
            code, out, err = reel(self.root, "preflight", video_id=c["video_id"])
            self.assertEqual(code, 0, (c, err))
            self.assertTrue(out["issues"], out)                       # dummy bytes: "open failed" for THIS file
            self.assertEqual(Path(out["issues"][0]["file"]).name, Path(c["file"]).name, c)
            self.assertTrue((self.root / "output/projects" / c["video_id"]).is_dir())

    def test_session_context_lists_the_inbox_ids(self):
        from lib.onboard import inbox
        ids = [c["video_id"] for c in inbox(self.root)["clips"]]
        r = subprocess.run([sys.executable, "-B", str(CTX)], input=json.dumps({"cwd": str(self.root)}),
                           capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(r.returncode, 0, r.stderr)
        ctx = json.loads(r.stdout)["hookSpecificOutput"]["additionalContext"]
        line = next(x for x in ctx.split(". ") if "New clips not started yet" in x) if "New clips" in ctx else ctx
        for i in ids:
            self.assertIn(i, ctx)
        self.assertNotIn("مقابلة", line)


class TestClipIdCompat(unittest.TestCase):
    def test_single_arabic_clip_auto_fill_uses_its_id(self):
        with tempfile.TemporaryDirectory() as t:
            root = make_client(t, [ARABIC_1])
            reel(root, "discover")
            code, out, err = reel(root, "preflight")                  # no --video-id: the only clip
            self.assertEqual(code, 0, err)
            self.assertTrue((root / "output/projects" / ("CLIP_" + h6("مقابلة ١"))).is_dir())
            self.assertFalse((root / "output/projects/VIDEO").exists())

    def test_existing_ascii_projects_keep_their_ids(self):
        from lib.onboard import inbox
        with tempfile.TemporaryDirectory() as t:
            root = make_client(t, ["C0239.MP4", "Dr Sherif intro.mp4"])
            Paths(root, "C0239").ensure_project()
            Paths(root, "DR_SHERIF_INTRO").ensure_project()
            self.assertEqual(sorted(inbox(root)["new"]), ["C0239", "DR_SHERIF_INTRO"])

    def test_old_project_of_a_lone_arabic_clip_is_adopted(self):
        """2.x auto-filled VIDEO for a client's only Arabic clip and that worked: keep that project."""
        from lib.onboard import inbox
        with tempfile.TemporaryDirectory() as t:
            root = make_client(t, [ARABIC_1, "C0001.MP4"])
            p = Paths(root, "VIDEO")
            p.ensure_project()
            write_json(p.p("02_transcription/transcript.json"), {"words": []})
            ib = inbox(root)
            self.assertEqual({c["file"]: c["video_id"] for c in ib["clips"]}["data/Raw/" + ARABIC_1], "VIDEO")
            self.assertEqual(ib["in_progress"], ["VIDEO"])

    def test_old_shared_project_is_never_adopted_by_two_arabic_clips(self):
        from lib.onboard import inbox
        with tempfile.TemporaryDirectory() as t:
            root = make_client(t, [ARABIC_1, ARABIC_2])
            Paths(root, "VIDEO").ensure_project()
            got = [c["video_id"] for c in inbox(root)["clips"]]
            self.assertNotIn("VIDEO", got)
            self.assertEqual(len(set(got)), 2)

    def test_podcast_reel_ids_are_not_raw_clips(self):
        """`<EP>_<ID>` reels resolve through their range, never through the clip map."""
        from lib.onboard import inbox
        with tempfile.TemporaryDirectory() as t:
            root = make_client(t, ["C0001.MP4", "C0002.MP4"])
            inbox(root)
            p = Paths(root, "EPW_R01")
            p.ensure_project()
            write_json(p.p("00_inputs/source.json"), {"footage": "data/Episodes/EPW.mp4", "in_ms": 0, "out_ms": 1000,
                                                      "episode_id": "EPW"})
            f = cli_module().main_footage(p, None)
            self.assertEqual([x.name for x in f], ["EPW.mp4"])
            self.assertNotIn("EPW_R01", read_json(root / "output/discovery/clip-ids.json"))


def hook_new_clips(root: Path) -> list:
    r = subprocess.run([sys.executable, "-B", str(CTX)], input=json.dumps({"cwd": str(root)}),
                       capture_output=True, text=True, encoding="utf-8")
    ctx = json.loads(r.stdout)["hookSpecificOutput"]["additionalContext"]
    line = ctx.split("New clips not started yet: ", 1)[1].split(". ", 1)[0]
    return [] if line == "none" else line.split(", ")


class TestClipIdReviewFixes(unittest.TestCase):
    """Review round 1: a raw stem as --video-id never lands work outside the inbox project; a gone clip is refused,
    never swapped for its sibling; rels compare case-insensitively; the hook shows the inbox ids."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = make_client(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def projects(self):
        return sorted(os.listdir(self.root / "output/projects"))

    def test_raw_stem_video_id_is_rewritten_to_the_inbox_id(self):
        from lib.onboard import inbox
        ids = {c["file"]: c["video_id"] for c in inbox(self.root)["clips"]}
        spaced, arabic = ids["data/Raw/Dr Sherif intro.mp4"], ids["data/Raw/" + ARABIC_1]
        outro = ids["data/Raw/Dr Sherif outro.mp4"]
        for given, want in (("Dr Sherif intro", spaced), ("مقابلة ١", arabic), (outro.lower(), outro)):
            code, out, err = reel(self.root, "preflight", video_id=given)
            self.assertEqual(code, 0, err)
            self.assertIn(want, err)                                   # one note says which id was used
        self.assertEqual(self.projects(), sorted([spaced, arabic, outro]))    # no spaced/Arabic/lower-case folder
        for vid in (spaced, arabic):
            write_json(Paths(self.root, vid).p("02_transcription/transcript.json"), {"words": []})
        ib = inbox(self.root)
        self.assertIn(spaced, ib["in_progress"])
        self.assertIn(arabic, ib["in_progress"])

    def test_given_folder_that_already_exists_is_kept(self):
        from lib.onboard import inbox
        inbox(self.root)
        Paths(self.root, "Dr Sherif intro").ensure_project()          # made by hand after the ids were assigned
        code, out, err = reel(self.root, "preflight", video_id="Dr Sherif intro")
        self.assertEqual(code, 0, err)
        self.assertEqual(self.projects(), ["Dr Sherif intro"])

    def test_2x_raw_stem_project_is_adopted(self):
        from lib.onboard import inbox
        with tempfile.TemporaryDirectory() as t:
            root = make_client(t, ["Dr Sherif intro.mp4", ARABIC_1, "C0001.MP4", "Dr X.mp4", "Dr X.mov"])
            for given in ("Dr Sherif intro", "مقابلة ١", "Dr X"):
                write_json(Paths(root, given).p("02_transcription/transcript.json"), {"words": []})
            ib = inbox(root)
            got = {c["file"]: c["video_id"] for c in ib["clips"]}
            self.assertEqual(got["data/Raw/Dr Sherif intro.mp4"], "Dr Sherif intro")
            self.assertEqual(got["data/Raw/" + ARABIC_1], "مقابلة ١")
            self.assertEqual(sorted(ib["in_progress"]), sorted(["Dr Sherif intro", "مقابلة ١"]))
            # "Dr X" is ambiguous (two extensions): never adopted; ".mov" sorts before ".mp4"
            self.assertEqual({got["data/Raw/Dr X.mp4"], got["data/Raw/Dr X.mov"]}, {"DR_X", "DR_X_MP4"})

    def test_gone_clip_is_refused_not_swapped_for_its_sibling(self):
        from lib.onboard import inbox
        inbox(self.root)
        (self.root / "data/Raw/C0239.MP4").unlink()
        inbox(self.root)
        with self.assertRaises(SystemExit) as e:
            cli_module().main_footage(Paths(self.root, "C0239"), None)
        msg = str(e.exception.code)
        self.assertIn("clip id C0239 was data/Raw/C0239.MP4, which is no longer in data/", msg)
        self.assertIn("--footage", msg)

    def test_rel_case_change_keeps_the_id(self):
        from lib.onboard import inbox
        before = {c["file"]: c["video_id"] for c in inbox(self.root)["clips"]}
        (self.root / "data/Raw/C0239.MP4").rename(self.root / "data/Raw/C0239.mp4")
        after = {c["file"]: c["video_id"] for c in inbox(self.root)["clips"]}
        self.assertEqual(after["data/Raw/C0239.mp4"], before["data/Raw/C0239.MP4"])
        self.assertEqual(len(read_json(self.root / "output/discovery/clip-ids.json")), len(RAW))

    def test_ambiguous_raw_stem_is_refused(self):
        from lib.onboard import inbox
        with tempfile.TemporaryDirectory() as t:
            root = make_client(t, ["Dr X.mp4", "Dr X.mov"])
            inbox(root)
            with self.assertRaises(SystemExit):
                cli_module().main_footage(Paths(root, "Dr X"), None)

    def test_hook_shows_the_inbox_ids_before_the_first_inbox(self):
        from lib.onboard import inbox
        (self.root / "data/Broll").mkdir()
        (self.root / "data/Broll/C0239.mp4").write_bytes(b"b-roll with a raw clip's name")   # sorts before data/Raw
        shown = hook_new_clips(self.root)                             # no clip-ids.json yet
        self.assertFalse((self.root / "output/discovery/clip-ids.json").exists())            # the hook writes nothing
        self.assertEqual(sorted(shown), sorted(inbox(self.root)["new"]))


if __name__ == "__main__":
    unittest.main()
