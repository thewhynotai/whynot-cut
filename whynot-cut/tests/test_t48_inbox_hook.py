# SPDX-License-Identifier: GPL-3.0-or-later
# © 2026 The Why Not AI (thewhynot.ai)
"""3.0 Phase 4 T4.8 hooks — the intake warnings reach the editor: `reel inbox` returns `warnings[]` and writes
output/discovery/intake-warnings.json (lib/onboard.py), the SessionStart context says them from that file only
(hooks/session_context.py), and the start / new-client skills tell Claude to say them in the editor's language.
Goes with hooks/T4.8/patch.diff (lib/intake_warnings.py has its own tests: test_t48_intake_warnings.py).
Run:  bash tools/test.sh -p test_t48_inbox_hook.py
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

sys = _sys
SK = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SK / "engine" / "reel"))

from lib import common  # noqa: E402
from lib.common import write_json  # noqa: E402

LONG = {"duration_s": 61 * 60, "video": {"display_width": 1920, "display_height": 1080}}


class TestInboxHook(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="t48h-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        from lib.onboard import scaffold
        self.root = self.tmp / "Dr Test"
        scaffold(self.root, "Dr Test")                       # the marker: the session hook sees a client folder
        write_json(self.root / common.CLIENT_PROFILE_REL / "podcast.json", {"raw_episode_hint_min": 60})
        (self.root / "data/Raw/full episode.mp4").write_bytes(b"v" * 64)
        (self.root / "data/Raw/script.pdf").write_bytes(b"%PDF-1.4\n%%EOF\n")

    def inbox(self):
        from lib import media, onboard
        with mock.patch.object(media, "probe", lambda p: LONG):
            return onboard.inbox(self.root)

    def test_h1_inbox_returns_the_warnings_and_writes_the_file(self):
        res = self.inbox()
        ids = [w["id"] for w in res["warnings"]]
        self.assertIn("episode_in_raw:data/Raw/full episode.mp4", ids)
        self.assertIn("document_in_data:data/Raw/script.pdf", ids)
        self.assertIn("logo:assets/Logo", ids)
        self.assertNotIn("warnings_unread", res)
        saved = json.loads((self.root / "output/discovery/intake-warnings.json").read_text(encoding="utf-8"))
        self.assertEqual(saved["warnings"], res["warnings"])
        for key in ("episode_hints", "missing_material", "discovery_warnings", "clips"):     # nothing removed
            self.assertIn(key, res)

    def test_h1b_every_warning_kind_goes_through_the_real_inbox(self):
        """Review fca6d25 P2-3: each kind the module makes reaches the inbox JSON once (no_footage on an empty client)."""
        from lib import intake_warnings as IW
        from lib.episode_sheet import render
        from test_t48_intake_warnings import pdf_with_text
        r = self.root
        files = {"data/Raw/00001.MTS": b"m", "data/Music/bed.ogg": b"o", "data/References/deck.pptx": b"p",
                 "data/References/Brand Guidelines.pdf": pdf_with_text("Brand"), "data/Raw/reference cut.mp4": b"v",
                 "data/Broll/city.mp4": b"v", "assets/Brand/brief.md": "Friendly, blue", "assets/Brand/client brief 2.md": "x",
                 "data/Episodes/EP1.mp4": b"v", "data/Episodes/EP2.mp4": b"v", "data/Episodes/EP2.docx": b"d",
                 "data/Episodes/EP3.mp4": b"v", "data/Episodes/EP3.md": render("EP3", "data/Episodes/EP3.mp4", "data/Episodes/"),
                 "data/Episodes/EP4.mp4": b"v", "data/Episodes/EP4.md": "---\nshow: S\nguest: G\n"}
        for rel, data in files.items():
            (r / rel).parent.mkdir(parents=True, exist_ok=True)
            (r / rel).write_bytes(data.encode("utf-8") if isinstance(data, str) else data)
        write_json(r / "output/projects/X1/01_analysis/burned-in-captions.json", {"verdict": "yes"})
        known = tuple(k for k in IW._KNOWN if not k.startswith("No SFX library"))     # one note passed through
        with mock.patch.object(IW, "_KNOWN", known):
            res = self.inbox()
        empty = self.tmp / "Empty"
        from lib.onboard import scaffold
        scaffold(empty, "Empty")
        from lib import media, onboard
        with mock.patch.object(media, "probe", lambda p: LONG):
            res_empty = onboard.inbox(empty)
        got = {w["kind"] for w in res["warnings"]} | {w["kind"] for w in res_empty["warnings"]}
        self.assertEqual(got, set(IW.SESSION_LABELS), sorted(set(IW.SESSION_LABELS) ^ got))
        self.assertNotIn("warnings_unread", res)
        saved = json.loads((r / "output/discovery/intake-warnings.json").read_text(encoding="utf-8"))
        self.assertEqual(saved["warnings"], res["warnings"])

    def test_h5_a_failing_build_never_stops_the_inbox(self):
        """Review fca6d25 P3-1: build() raising (and even the module failing to load) is named; inbox returns."""
        from lib import intake_warnings as IW
        with mock.patch.object(IW, "build", side_effect=RuntimeError("boom")):
            res = self.inbox()
        self.assertEqual(res["warnings"], [])
        self.assertEqual(res["warnings_unread"], [{"source": "intake_warnings", "why": "not built: RuntimeError"}])
        self.assertIn("clips", res)
        with mock.patch.object(IW, "refresh", side_effect=ImportError("half-installed")):
            res = self.inbox()
        self.assertEqual(res["warnings_unread"], [{"source": "intake_warnings", "why": "not built: ImportError"}])

    def test_h2_a_rerun_is_the_same_list(self):
        self.assertEqual(self.inbox()["warnings"], self.inbox()["warnings"])

    def test_h3_the_session_context_says_them_from_the_file_only(self):
        from test_plugin import CTX, hook
        self.inbox()
        cache = self.root / "output/discovery/discovery-cache.json"
        before = cache.stat().st_mtime_ns
        code, out, _ = hook(CTX, {"cwd": str(self.root)})
        self.assertEqual(code, 0)
        ctx = json.loads(out)["hookSpecificOutput"]["additionalContext"]
        self.assertIn("Intake warnings from the last `reel inbox` (", ctx)
        self.assertIn("episode-length clip in data/Raw", ctx)
        self.assertNotIn("full episode.mp4", ctx)                           # counts, never file names
        self.assertEqual(cache.stat().st_mtime_ns, before)                  # no discovery at session start
        (self.root / "output/discovery/intake-warnings.json").unlink()
        code, out, _ = hook(CTX, {"cwd": str(self.root)})
        self.assertNotIn("Intake warnings", json.loads(out)["hookSpecificOutput"]["additionalContext"])
        self.assertFalse((self.root / "output/discovery/intake-warnings.json").exists())
        (self.root / "output/discovery/intake-warnings.json").write_text("{damaged", encoding="utf-8")
        code, out, _ = hook(CTX, {"cwd": str(self.root)})                  # review fca6d25 P3-3: said, not silent
        self.assertEqual(code, 0)
        self.assertIn("can't be read; run `reel inbox` again",
                      json.loads(out)["hookSpecificOutput"]["additionalContext"])

    def test_h4_the_skills_and_the_intake_inspector_say_the_warnings(self):
        for doc in ("skills/start/SKILL.md", "skills/new-client/SKILL.md", "agents/intake-inspector.md"):
            text = (SK / doc).read_text(encoding="utf-8")
            self.assertIn("warnings[]", text, doc)
            self.assertIn("text_ar", text, doc)


if __name__ == "__main__":
    unittest.main()
