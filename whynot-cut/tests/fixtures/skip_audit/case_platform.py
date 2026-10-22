# Fixture for test_skip_audit.py: the platform/tool skip shapes found on release/3.0, pinned here so the test does not
# depend on those files staying as they are. Every site must be classed platform/tool. Never run; only parsed.
import os
import shutil
import sys
import unittest
from pathlib import Path

import hb_text

NODE = shutil.which("node")
PLEX = Path(__file__).parent / "ibmplexsansarabic" / "IBMPlexSansArabic-Regular.ttf"
AVAILABLE = _find_hypothesis()
INSTALL_HINT = "hypothesis is not installed (run tools/security/setup_fuzz.py)"

# tests/security/fuzz/_hyp.py: a module-level skip decorator assigned to a name
requires_hypothesis = unittest.skipUnless(AVAILABLE, INSTALL_HINT)


def free_ram(mb):
    free = available_ram_mb()
    return unittest.skipIf(free is not None and free < mb, "needs about %d MB free RAM, %s MB free" % (mb, free))


# test_cep_bridge.py
@unittest.skipUnless(NODE, "needs node to run js/bridge.js with a stubbed CEP")
class TestBridge(unittest.TestCase):
    @unittest.skipUnless(os.name == "nt", "a Windows junction")
    def test_junction(self):
        pass

    @unittest.skipIf(sys.platform == "darwin", "macOS has no such thing")
    def test_not_mac(self):
        pass

    def test_symlink(self):
        try:
            os.symlink("a", "b")
        except OSError as e:
            self.skipTest(f"no symlinks here: {e}")


# test_bidi_lines_hosts.py
@unittest.skipUnless(hb_text.AVAILABLE, "HarfBuzz/FreeType missing (run with the engine runtime)")
class TestShape(unittest.TestCase):
    @unittest.skipUnless(PLEX.is_file(), "the panel font is only in a repo checkout")
    def test_plex(self):
        pass


# test_audio_long.py: an explicit opt-in env var
class TestLong(unittest.TestCase):
    @unittest.skipUnless(os.environ.get("WHYNOT_SLOW_TESTS"), "slow: set WHYNOT_SLOW_TESTS=1")
    def test_sixty_minutes(self):
        pass
