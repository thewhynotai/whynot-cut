# Fixture for test_skip_audit.py: temporary skips as found on release/3.0 (words kept), each with a condition that looks
# like a machine/tool check (.exists(), .is_file(), a tool name). None may be classed platform/tool. Only parsed.
import shutil
import unittest

NODE = shutil.which("node")


class TestTemporary(unittest.TestCase):
    def test_brief(self):                       # tests/test_brief.py
        cb = SK / "engine/reel/lib/client_brief.py"
        if not cb.exists():
            self.skipTest("lib/client_brief.py (Task 59, M5-T4) is not built yet")

    def test_identity(self):                    # tests/test_identity_scan.py
        f = ROOT / "tools" / "identity_hashes.json"
        if not f.exists():
            self.skipTest("tools/identity_hashes.json not generated yet")

    def test_tls(self):                         # tests/test_runtime_locks.py
        if not (cert.is_file() and key.is_file()):          # the J-T1 loopback fixture lands with Addendum J's commit
            self.skipTest("tests/fixtures/brand_web/tls is not committed yet (J-T1)")

    def test_tool(self):
        if not NODE:
            self.skipTest("the bridge is not available yet")
