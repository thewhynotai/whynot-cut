"""Phase 4 Task 19 release side (Addendum H R-T6): `tools/release.py handoff` runs the keyed identity scan over the Mac
clone and the plugin zip's files before anything is zipped.
  * identity: HARD. A finding, a scan error, or (on a real release, not a PREVIEW) a missing key stops the hand-off and
    nothing is swapped in. A PREVIEW without a key is logged as skipped.
  * secrets: REPORT-ONLY until the committed tree's real home paths are fixed or allowlisted.
Fictional tokens only (test key and hashes made in a temp folder; they name nobody).
Run:  tools/test.sh -p test_release_identity_gate.py
"""
import sys as _sys
_sys.dont_write_bytecode = True  # keep the plugin folder free of __pycache__
import _isolation  # noqa: F401,E402  G79: sandbox the engine home first (tests/_isolation.py)
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import test_release_handoff as trh  # noqa: E402  (the shared fake repo + release module loader)

rel = trh.rel
ROOT = trh.REPO
sys.path.insert(0, str(ROOT / "tools"))
import identity_scan as ids  # noqa: E402

PLAIN = "# fictional test list\nZorblax Quentaro\nVexilor\n"
NO_KEY_ENV = {k: v for k, v in os.environ.items() if k not in (ids.KEY_ENV, ids.KEY_HEX_ENV)}


class GateFixture(unittest.TestCase):
    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.addCleanup(self._td.cleanup)
        tmp = Path(self._td.name)
        secret = tmp / "secret"
        secret.mkdir()
        (secret / "plain.txt").write_text(PLAIN, encoding="utf-8")
        self.key = secret / "test.key"
        ids.make_key(self.key, repo_root=ROOT)
        self.hashes = tmp / "hashes.json"
        ids.make_hashes(secret / "plain.txt", self.key, self.hashes, repo_root=ROOT)
        self.tree = tmp / "tree"
        (self.tree / "docs").mkdir(parents=True)
        (self.tree / "docs" / "ok.md").write_text("A clean page about captions.\n", encoding="utf-8")
        self.lines = []

    def with_key(self):
        return mock.patch.dict(os.environ, {**NO_KEY_ENV, ids.KEY_ENV: str(self.key)}, clear=True)

    def without_key(self):
        return mock.patch.dict(os.environ, NO_KEY_ENV, clear=True)

    def gate(self, require_key):
        return rel.identity_gate(self.tree, require_key=require_key, log=self.lines.append, hashes=self.hashes)


class TestIdentityGate(GateFixture):
    def test_a_planted_token_stops_the_handoff(self):
        (self.tree / "docs" / "leak.md").write_text("Made like Vexilor does it.\n", encoding="utf-8")
        with self.with_key(), self.assertRaises(rel.HandoffError) as cm:
            self.gate(require_key=True)
        msg = str(cm.exception)
        self.assertIn("identity scan (tree): exit 1", msg)
        self.assertIn("docs/leak.md", msg)
        self.assertNotIn("Vexilor", msg)                              # the scan's output is redacted
        with self.with_key(), self.assertRaises(rel.HandoffError):    # a PREVIEW with a key is just as hard
            self.gate(require_key=False)

    def test_a_planted_token_in_a_file_name_stops_it(self):
        (self.tree / "docs" / "vexilor-notes.md").write_text("nothing here\n", encoding="utf-8")
        with self.with_key(), self.assertRaises(rel.HandoffError):
            self.gate(require_key=True)

    def test_a_clean_tree_passes_and_says_so(self):
        with self.with_key():
            line = self.gate(require_key=True)
        self.assertIn("identity scan (tree): 0 findings in", line)
        self.assertEqual(self.lines, [line])

    def test_a_release_without_a_key_is_refused(self):
        with self.without_key(), self.assertRaises(rel.HandoffError) as cm:
            self.gate(require_key=True)
        self.assertIn("exit 2", str(cm.exception))
        self.assertIn("no key", str(cm.exception))

    def test_a_preview_without_a_key_is_logged_as_skipped(self):
        (self.tree / "docs" / "leak.md").write_text("Vexilor\n", encoding="utf-8")
        with self.without_key():
            line = self.gate(require_key=False)
        self.assertIn("skipped, no key", line)

    def test_unreadable_scan_output_is_an_error_not_a_pass(self):
        fake = [sys.executable, "-c", "print('not json')"]
        with self.assertRaises(rel.HandoffError) as cm:
            rel.identity_gate(self.tree, require_key=False, log=self.lines.append, cmd=fake)
        self.assertIn("unreadable output", str(cm.exception))


class TestSecretReport(GateFixture):
    def test_findings_are_counted_never_raised(self):
        (self.tree / "notes.md").write_text("see C:\\Users\\someone\\Desktop\\x.txt\n", encoding="utf-8")
        with self.without_key():
            n = rel.secret_report(self.tree, log=self.lines.append)
        self.assertGreaterEqual(n, 1)
        self.assertIn("report-only", self.lines[-1])

    def test_a_broken_scan_is_reported_not_raised(self):
        n = rel.secret_report(self.tree, log=self.lines.append, cmd=[sys.executable, "-c", "import sys; sys.exit(3)"])
        self.assertEqual(n, -1)
        self.assertIn("could not run", self.lines[-1])


@unittest.skipUnless(trh.GIT, "git not on PATH")
class TestHandoffRunsTheGate(trh.HandoffCase):
    def test_a_gate_failure_swaps_nothing_in(self):
        repo = trh.make_repo(self.tmp / "src")
        with mock.patch.object(rel, "identity_gate", side_effect=rel.HandoffError("identity scan (repo): exit 1: x")), \
                self.assertRaises(rel.HandoffError):
            self.run_handoff(repo)
        self.assertFalse(self.out.exists())
        self.assertFalse(self.out.with_name(self.out.name + ".new").exists())

    def test_both_trees_are_scanned_and_a_release_needs_the_key(self):
        repo = trh.make_repo(self.tmp / "src")
        seen = []
        with mock.patch.object(rel, "identity_gate", side_effect=lambda root, require_key, log=None: seen.append(
                (Path(root).name, require_key)) or "ok"), mock.patch.object(rel, "secret_report", return_value=0):
            summary = self.run_handoff(repo)
        self.assertEqual(seen, [("repo", False), (".stage", False)])  # a PREVIEW: key used if set, else skipped
        self.assertEqual(summary["secret_findings"], {"repo": 0, ".stage": 0})


if __name__ == "__main__":
    unittest.main()
