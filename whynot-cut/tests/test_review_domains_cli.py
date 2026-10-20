# SPDX-License-Identifier: GPL-3.0-or-later
# © 2026 The Why Not AI (thewhynot.ai)
"""3.0 Phase 4 Task 50 = Addendum M1-T1: `reel review-scan` (the CLI verb; the scan itself is tested in
test_review_domains.py). Goes in with hooks/task50/cli.py.patch: whynot-cut/tests/test_review_domains_cli.py.
Run:  bash tools/test.sh -p test_review_domains_cli.py
"""
import sys as _sys
_sys.dont_write_bytecode = True  # keep the plugin folder free of __pycache__
import _isolation  # noqa: F401,E402  G79: sandbox the engine home first (tests/_isolation.py)
import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

sys = _sys
SK = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SK / "engine" / "reel"))
sys.path.insert(0, str(SK / "tests"))

from lib import common  # noqa: E402
from lib import review_domains as RD  # noqa: E402
from lib.common import Paths, write_json  # noqa: E402
from test_review_domains import event, make_client, spec, tree_digest  # noqa: E402

CLI = SK / "engine/reel/cli.py"
VID = "C0001"


def env():
    from test_plugin import isolated_env
    return isolated_env()


class TestReviewScanCli(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="m1t1c_"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.addCleanup(common.set_context, None)
        self.root = make_client(self.tmp)
        self.p = Paths(self.root, VID)
        write_json(self.root / common.CLIENT_PROFILE_REL / "profile.json", {"domain": "medical"})

    def reel(self, *argv):
        cmd = [sys.executable, "-B", str(CLI), "--root", str(self.root), "--video-id", VID, *argv]
        e = {k: v for k, v in env().items() if k not in ("PYTHONUTF8", "PYTHONIOENCODING")}
        r = subprocess.run(cmd, capture_output=True, env=e)
        return r.returncode, r.stdout.decode("utf-8"), r.stderr.decode("utf-8", "replace")

    def test_classified_read_only_and_listed(self):
        import importlib.util
        s = importlib.util.spec_from_file_location("reel_cli_m1t1", CLI)
        cli = importlib.util.module_from_spec(s)
        s.loader.exec_module(cli)
        self.assertIn("review-scan", cli.CORE_READS)
        self.assertIn("review-scan", cli.command_table())

    def test_prints_the_scan_as_one_json_document_and_writes_nothing(self):
        write_json(self.p.p("01_analysis/timeline-spec.json"),
                   spec(event("G1", 0, 2000, evidence="الكشف بـ ٥٠٠ جنيه", text="الكشف في العيادة")))
        before = tree_digest(self.root)
        code, so, se = self.reel("review-scan")
        self.assertEqual(code, 0, se)
        doc = json.loads(so)
        doc.pop("version_warnings", None)          # the CLI's own note: the fixture plan carries no version stamp
        common.set_context(self.root)
        self.assertEqual(doc, json.loads(json.dumps(RD.scan(self.p), ensure_ascii=False)))
        self.assertEqual(doc["lines"][0]["required"], ["ai", "business", "medical"])
        self.assertEqual(tree_digest(self.root), before)

    def test_refuses_without_a_plan(self):
        before = tree_digest(self.root)
        code, so, se = self.reel("review-scan")
        self.assertNotEqual(code, 0)
        self.assertIn("reel plan", so + se)
        self.assertIn("reel review-scan", so)
        log = self.root / "output" / "logs"          # every refusal goes to the engine's error log, as for any verb
        shutil.rmtree(log, True)
        if not any((self.root / "output").iterdir()):
            (self.root / "output").rmdir()
        self.assertEqual(tree_digest(self.root), before)

    def test_refuses_an_unknown_profile_domain_naming_it(self):
        write_json(self.p.p("01_analysis/timeline-spec.json"), spec(event("G1", 0, 2000, text="x")))
        write_json(self.root / common.CLIENT_PROFILE_REL / "profile.json", {"review_domains": ["crypto"]})
        code, so, se = self.reel("review-scan")
        self.assertNotEqual(code, 0)
        self.assertIn("crypto", so + se)


if __name__ == "__main__":
    unittest.main()
