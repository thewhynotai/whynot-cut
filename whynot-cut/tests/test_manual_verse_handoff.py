# SPDX-License-Identifier: GPL-3.0-or-later
# © 2026 The Why Not AI (thewhynot.ai)
"""Manual verse, the handoff README (lib/handoff.py): with a recited verse it names the SRT the plan wrote without it
(subtitles-seq.srt), never the transcript's subtitles.srt, and lists each verse to add by hand (id and time, never
its words). A plain clip: as before. Self-contained (fix round 1, review c2c23e6 P2-3): its own real-clip fixture.
Run:  bash tools/test.sh -p test_manual_verse_handoff.py
"""
import sys as _sys
_sys.dont_write_bytecode = True  # keep the plugin folder free of __pycache__
import _isolation  # noqa: F401,E402  G79: sandbox the engine home first (tests/_isolation.py)
import shutil
import tempfile
import unittest
from pathlib import Path

sys = _sys
SK = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SK / "engine" / "reel"))
sys.path.insert(0, str(SK / "tests"))

from lib import common  # noqa: E402
from lib.common import write_json  # noqa: E402
from test_manual_verse import SC, build_words, has_verse  # noqa: E402

NAME = "آية: يضيفها المونتير يدويًا"


def video_project(tmp: Path, scenario: str, domain="religious"):
    """test_pipeline.make_project's real 12 s clip with this scenario's words, preflighted and planned."""
    from lib.media import preflight
    from lib.plan import compile_plan
    from lib.transcribe import finalize
    from test_pipeline import make_project
    root, p, _w = make_project(tmp)
    if domain:
        write_json(root / common.CLIENT_PROFILE_REL / "profile.json", {"domain": domain})
    common.set_context(root)
    w = build_words(SC[scenario])
    segs = [{"id": 1, "start_ms": w[0]["start_ms"], "end_ms": w[-1]["end_ms"], "text": " ".join(x["word"] for x in w),
             "avg_logprob": -0.2, "no_speech_prob": 0.01, "compression_ratio": 1.2, "words": [x["id"] for x in w]}]
    finalize(p, {"source_video": str(root / "data/Raw/CLIP1.mov"), "backend": "test", "model": "none", "language": "ar",
                 "language_probability": 1.0, "duration_ms": 12000}, segs, [dict(x) for x in w])
    preflight(p, [root / "data/Raw/CLIP1.mov"])
    write_json(p.p("01_analysis/edit-decisions.json"), {"video_id": "CLIP1",
                                                        "global": {"main_footage": "data/Raw/CLIP1.mov"},
                                                        "decisions": []})
    res = compile_plan(p)
    assert res["ok"], res["errors"]
    return root, p


class TestHandoff(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="mvh_"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.addCleanup(common.set_context, None)

    def readme(self, scenario, domain="religious"):
        _root, p = video_project(self.tmp, scenario, domain)
        from lib.premiere_xml import build_xml
        from lib import handoff
        build_xml(p)
        handoff.build(p)
        return p.p("09_handoff/README.md").read_text(encoding="utf-8")

    def test_verse_readme(self):
        readme = self.readme("recited")
        self.assertIn("subtitles-seq.srt", readme)
        self.assertNotIn("`02_transcription/subtitles.srt`", readme)
        self.assertIn(NAME, readme)
        self.assertIn("MV01", readme)
        self.assertEqual(has_verse(readme), [])

    def test_plain_readme(self):
        readme = self.readme("plain", None)
        self.assertIn("`02_transcription/subtitles.srt`", readme)
        self.assertNotIn(NAME, readme)


if __name__ == "__main__":
    unittest.main()
