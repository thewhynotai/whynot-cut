# SPDX-License-Identifier: GPL-3.0-or-later
# © 2026 The Why Not AI (thewhynot.ai)
"""Manual verse, the handoff README (patch handoff-verse.patch, executor): with a recited verse it names the SRT the
plan wrote without it (subtitles-seq.srt), never the transcript's subtitles.srt, and lists each verse to add by hand
(id and time, never its words). A plain clip: as before.
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
from test_manual_verse import has_verse  # noqa: E402
try:  # the fixture lives with the premiere_xml-verse patch (ADOBE-G4); until it lands this test cannot run
    from test_manual_verse_premiere_xml import NAME, video_project  # noqa: E402
    _PENDING = None
except ImportError:  # executor 2026-10-19 (review c2c23e6 P2-3): an explicit, dated skip, removed by the fix round
    _PENDING = "waits for ADOBE-G4's premiere_xml-verse patch (test_manual_verse_premiere_xml)"


@unittest.skipIf(_PENDING, _PENDING or "")
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
