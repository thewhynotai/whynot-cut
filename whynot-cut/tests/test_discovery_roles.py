import _isolation  # noqa: F401  G79: sandbox the engine home first (tests/_isolation.py)
"""3.0 T2.5 (engine IM-8): discovery decides a file's role by its folder first (data/Raw = source, data/References =
references, data/Broll = B-roll, ...), and uses filename hints only outside the known folders, on word boundaries.
Raw clips named "Refractive...", "Reflux...", "Preface..." or "Stock market..." stay source clips (they used to turn
into reference edits / B-roll and silently drop out of `reel inbox` and autopilot).
"""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SK = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SK / "engine" / "reel"))

from lib.common import Paths  # noqa: E402
from lib.discover import classify, discover  # noqa: E402

CTX = SK / "hooks/session_context.py"
TRAPS = ["Refractive surgery talk.mp4", "Reflux explained.mp4", "Preface.mp4", "Stock market tips.mp4",
         "Referral.mp4", "Strawberry.mp4", "Drawing.mp4", "Brawl.mp4"]
NO_WORD = [n for n in TRAPS if not n.startswith("Stock")]       # "Stock market" has the real word "stock" in it


def role_of(root: Path, rel: str) -> str:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    if not p.exists():
        p.write_bytes(b"x")
    return classify(p, rel)["role"]


def make_client(tmp) -> Path:
    root = Path(tmp) / "Dr Test"
    for d in ("assets/Brand", "data/Raw"):
        (root / d).mkdir(parents=True)
    (root / ".whynot-client").write_text("{}", encoding="utf-8")
    return root


class TestFolderFirst(unittest.TestCase):
    def setUp(self):
        self._t = tempfile.TemporaryDirectory()
        self.addCleanup(self._t.cleanup)
        self.root = make_client(self._t.name)

    def test_raw_folder_clips_with_hint_lookalike_names_stay_source(self):
        for n in TRAPS:
            self.assertEqual(role_of(self.root, f"data/Raw/{n}"), "source_footage", n)

    def test_nested_raw_folders_stay_source(self):
        self.assertEqual(role_of(self.root, "data/Raw/2026/April/Refractive.mp4"), "source_footage")
        self.assertEqual(role_of(self.root, "data/raw/Preface.MOV"), "source_footage")      # folder case is irrelevant

    def test_references_folder_is_references(self):
        self.assertEqual(role_of(self.root, "data/References/Style one.mp4"), "editing_reference_video")
        self.assertEqual(role_of(self.root, "data/References/notes.md"), "editing_reference_doc")
        self.assertEqual(role_of(self.root, "data/references/sub/clip.mov"), "editing_reference_video")

    def test_broll_folder_is_broll(self):
        self.assertEqual(role_of(self.root, "data/Broll/city.mp4"), "broll_video")
        self.assertEqual(role_of(self.root, "data/B-roll/city.mp4"), "broll_video")
        self.assertEqual(role_of(self.root, "data/Broll/SOURCES.md"), "broll_license")

    def test_music_and_sfx_folders(self):
        self.assertEqual(role_of(self.root, "data/Music/theme.mp3"), "music")
        self.assertEqual(role_of(self.root, "data/SFX/whoosh.wav"), "sfx")

    def test_episodes_folder_is_unchanged(self):
        self.assertEqual(role_of(self.root, "data/Episodes/EP1.mp4"), "episode")
        self.assertEqual(role_of(self.root, "data/Episodes/EP1.md"), "episode_sheet")

    def test_folder_beats_a_contradicting_filename(self):
        self.assertEqual(role_of(self.root, "data/Raw/Reference style.mp4"), "source_footage")
        self.assertEqual(role_of(self.root, "data/Broll/raw take.mp4"), "broll_video")
        self.assertEqual(role_of(self.root, "data/References/Raw clip.mp4"), "editing_reference_video")


class TestHintsOutsideKnownFolders(unittest.TestCase):
    def setUp(self):
        self._t = tempfile.TemporaryDirectory()
        self.addCleanup(self._t.cleanup)
        self.root = make_client(self._t.name)

    def test_hint_words_still_work_outside_known_folders(self):
        r = self.root
        self.assertEqual(role_of(r, "data/Style ref 1.mp4"), "editing_reference_video")
        self.assertEqual(role_of(r, "data/REF_02.mp4"), "editing_reference_video")
        self.assertEqual(role_of(r, "data/Client Raw/a.mp4"), "source_footage")
        self.assertEqual(role_of(r, "data/Stock clips/a.mp4"), "broll_video")
        self.assertEqual(role_of(r, "data/b_roll/a.mp4"), "broll_video")
        self.assertEqual(role_of(r, "data/Reference edit.md"), "editing_reference_doc")

    def test_lookalike_words_are_not_hints_outside_known_folders_either(self):
        r = self.root
        for n in NO_WORD:
            self.assertEqual(role_of(r, f"data/Loose/{n}"), "source_footage", n)    # a video in data/ is source
        self.assertEqual(role_of(r, "data/Preface.pdf"), "unclassified")             # not a reference document
        self.assertEqual(role_of(r, "data/Refractive notes.md"), "unclassified")

    def test_camel_case_and_digits_are_word_boundaries(self):
        r = self.root
        self.assertEqual(role_of(r, "assets/Brand/ClientBrief.docx"), "client_brief")
        self.assertEqual(role_of(r, "assets/Brand/BrandColors.txt"), "brand_colors")
        self.assertEqual(role_of(r, "assets/Logo/logo2.png"), "logo")
        self.assertEqual(role_of(r, "assets/Logo/Logos.png"), "logo")

    def test_asset_lookalikes_are_not_hints(self):
        r = self.root
        self.assertEqual(role_of(r, "assets/Misc/Colombia trip.jpg"), "client_image")
        self.assertEqual(role_of(r, "assets/Photos/Biology.jpg"), "client_photo")      # "photo" is in the folder name
        self.assertEqual(role_of(r, "assets/Brand/Season promo S.jpg"), "brand_image")

    def test_existing_asset_roles_are_unchanged(self):
        r = self.root
        self.assertEqual(role_of(r, "assets/Photos/Profile.jpg"), "client_photo")
        self.assertEqual(role_of(r, "assets/Brand/brief.md"), "client_brief")
        self.assertEqual(role_of(r, "assets/Fonts/Brand.ttf"), "brand_font")
        self.assertEqual(role_of(r, "assets/Brand/colors.txt"), "brand_colors")


class TestDiscoverWarnings(unittest.TestCase):
    def setUp(self):
        self._t = tempfile.TemporaryDirectory()
        self.addCleanup(self._t.cleanup)
        self.root = make_client(self._t.name)

    def test_inventory_keeps_misnamed_raw_clips_as_source(self):
        for n in TRAPS:
            (self.root / "data/Raw" / n).write_bytes(b"x")
        inv = discover(Paths(self.root), read_docs=False)["inventory"]
        self.assertEqual(sorted(inv["by_role"]["source_footage"]), sorted(f"data/Raw/{n}" for n in TRAPS))
        self.assertNotIn("editing_reference_video", inv["by_role"])
        self.assertNotIn("broll_video", inv["by_role"])
        w = " ".join(x for x in inv["warnings"] if "disagree" in x)           # only the real word "stock" is a hint
        self.assertIn("Stock market tips.mp4", w)
        for n in NO_WORD:
            self.assertNotIn(n, w)

    def test_folder_and_hint_disagreement_is_warned(self):
        for rel in ("data/Raw/Reference style.mp4", "data/Broll/raw take.mp4", "data/Raw/ok.mp4"):
            (self.root / rel).parent.mkdir(parents=True, exist_ok=True)
            (self.root / rel).write_bytes(b"x")
        inv = discover(Paths(self.root), read_docs=False)["inventory"]
        w = " ".join(x for x in inv["warnings"] if "disagree" in x)
        self.assertIn("data/Raw/Reference style.mp4", w)
        self.assertIn("data/Broll/raw take.mp4", w)
        self.assertNotIn("ok.mp4", w)
        self.assertEqual(sorted(inv["by_role"]["source_footage"]), ["data/Raw/Reference style.mp4", "data/Raw/ok.mp4"])
        self.assertEqual(inv["by_role"]["broll_video"], ["data/Broll/raw take.mp4"])

    def test_loose_document_warning_ignores_lookalike_words(self):
        (self.root / "data/Preface.md").write_text("x", encoding="utf-8")
        inv = discover(Paths(self.root), read_docs=False)["inventory"]
        self.assertTrue(any("Preface.md" in w for w in inv["warnings"]), inv["warnings"])


class TestSessionContext(unittest.TestCase):
    def _new_line(self, root: Path) -> str:
        r = subprocess.run([sys.executable, "-B", str(CTX)], input=json.dumps({"cwd": str(root)}),
                           capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(r.returncode, 0, r.stderr)
        ctx = json.loads(r.stdout)["hookSpecificOutput"]["additionalContext"]
        return ctx.split("New clips not started yet: ", 1)[1].split(". ", 1)[0]

    def test_referral_in_raw_is_reported_new(self):
        with tempfile.TemporaryDirectory() as t:
            root = make_client(t)
            (root / "data/References").mkdir()
            (root / "data/Raw/Referral.mp4").write_bytes(b"x")
            (root / "data/Raw/Stock market.mp4").write_bytes(b"x")
            (root / "data/References/style.mp4").write_bytes(b"x")
            line = self._new_line(root)
            self.assertIn("REFERRAL", line)
            self.assertIn("STOCK_MARKET", line)
            self.assertNotIn("STYLE", line)

    def test_fallback_matches_path_segments_not_substrings(self):
        """When the engine cannot be imported the hook falls back to its own scan: same rule."""
        sys.path.insert(0, str(SK / "hooks"))
        import importlib
        sc = importlib.import_module("session_context")
        with tempfile.TemporaryDirectory() as t:
            root = make_client(t)
            (root / "data/References").mkdir()
            (root / "data/Raw/Referral.mp4").write_bytes(b"x")
            (root / "data/References/style.mp4").write_bytes(b"x")
            (root / "data/Episodes").mkdir()
            (root / "data/Episodes/EP1.mp4").write_bytes(b"x")
            with mock.patch("lib.discover.classify", side_effect=RuntimeError("engine unavailable")):
                got = sc.new_clips(root)                          # the engine classifier fails -> fallback scan
            self.assertEqual(got, ["REFERRAL"])


if __name__ == "__main__":
    unittest.main()
