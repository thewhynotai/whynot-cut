# SPDX-License-Identifier: GPL-3.0-or-later
# © 2026 The Why Not AI (thewhynot.ai)
"""Phase 4 Task 48 (L-T10): the Hypothesis install for the fuzz tests (`install_tools.py --fuzz`, `fuzz.lock`).

Hypothesis is a dev tool (L-G37): hash-pinned in its own lock, installed beside the engine runtime's Python version,
never in the runtime locks. Run:  tools/test.sh -p test_security_scan_fuzz_install.py
"""
import sys as _sys
_sys.dont_write_bytecode = True
import _isolation  # noqa: F401,E402
import hashlib
import json
import os
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SEC = ROOT / "tools" / "security"
_sys.path.insert(0, str(SEC))

import install_tools as it  # noqa: E402

V = json.loads((SEC / "versions.json").read_text(encoding="utf-8"))
RUNTIME_LOCKS = sorted((ROOT / "whynot-cut" / "setup" / "locks").glob("runtime-*.lock"))


class FuzzLock(unittest.TestCase):
    def test_lock_matches_its_recorded_sha256_and_every_requirement_is_hashed(self):
        lock = ROOT / V["python_tools"]["fuzz_lock"]
        self.assertEqual(hashlib.sha256(lock.read_bytes()).hexdigest(), V["python_tools"]["fuzz_lock_sha256"])
        self.assertEqual(it.lock_lines_without_hash(lock.read_text(encoding="utf-8")), [])

    def test_hypothesis_pin_matches_versions_json(self):
        text = (ROOT / V["python_tools"]["fuzz_lock"]).read_text(encoding="utf-8").lower()
        self.assertRegex(text, r"(?m)^hypothesis==%s\b" % re.escape(V["python_tools"]["packages"]["hypothesis"]["version"]))

    def test_the_fuzz_tools_never_enter_the_runtime_locks(self):
        self.assertTrue(RUNTIME_LOCKS)
        for lock in RUNTIME_LOCKS:
            text = lock.read_text(encoding="utf-8").lower()
            for name in ("hypothesis", "semgrep", "bandit", "pip-audit", "sortedcontainers"):
                self.assertNotRegex(text, r"(?m)^%s==" % name, "%s in %s" % (name, lock.name))

    def test_fuzz_dir_is_named_for_the_runtime_python(self):
        self.assertEqual(it.fuzz_dir("/h", "3.12").name, "fuzz-py312")
        self.assertEqual(it.fuzz_dir("/h", "3.13").name, "fuzz-py313")

    def test_tampered_fuzz_lock_is_refused_before_anything_is_installed(self):
        import tempfile
        from unittest import mock
        v = dict(V, python_tools=dict(V["python_tools"], fuzz_lock_sha256="0" * 64))  # the recorded hash no longer matches the lock
        with tempfile.TemporaryDirectory() as d, mock.patch.object(it, "versions", return_value=v):
            with self.assertRaises(it.InstallError):
                it.install_fuzz(Path(d))
            self.assertFalse((Path(d) / "fuzz-py312").exists())


class HypothesisIsFound(unittest.TestCase):
    def test_hyp_module_finds_hypothesis_or_says_how_to_install_it(self):
        _sys.path.insert(0, str(ROOT / "whynot-cut" / "tests" / "security" / "fuzz"))
        import _hyp
        if not _hyp.AVAILABLE:
            if os.environ.get("WNC_REQUIRE_SCANNERS") == "1":
                self.fail("WNC_REQUIRE_SCANNERS=1 but Hypothesis is not installed: %s (the whole fuzz layer would be skipped)" % _hyp.INSTALL_HINT)
            self.skipTest(_hyp.INSTALL_HINT)
        import hypothesis
        self.assertEqual(hypothesis.__version__, V["python_tools"]["packages"]["hypothesis"]["version"])
        self.assertTrue(Path(hypothesis.__file__).resolve().is_relative_to(Path(it.tools_home()).resolve()),
                        "Hypothesis must be the pinned copy under the tools home, not another one on sys.path: %s" % hypothesis.__file__)


class LongProfileRunner(unittest.TestCase):
    """tools/security/fuzz_long.py: a test below its target is listed, never hidden."""

    def test_count_lines_parse_and_a_short_count_is_below_target_unless_the_space_is_exhausted(self):
        import fuzz_long as fl
        m = fl.COUNT_RE.match("FUZZ-COUNT test_x.A.test_y 2302 cap 1500 space None heavy 250000")
        self.assertEqual(m.groups(), ("test_x.A.test_y", "2302", "1500", "None", "250000"))
        self.assertEqual(fl.parse_counts("noise\nFUZZ-COUNT t 25 cap 10000 space 25 heavy None\n"),
                         [{"test": "t", "count": 25, "cap": 10000, "space": 25, "heavy": None}])
        counts = [{"test": "a", "count": 10000, "cap": 10000, "space": None, "heavy": None},    # reached
                  {"test": "b", "count": 9000, "cap": 10000, "space": None, "heavy": None},     # short: listed
                  {"test": "c", "count": 25, "cap": 10000, "space": 25, "heavy": None},         # tiny space, exhausted: fine
                  {"test": "d", "count": 1500, "cap": 1500, "space": None, "heavy": 250000},    # heavy target at its own floor
                  {"test": "e", "count": 1500, "cap": 1500, "space": None, "heavy": 900}]       # heavy waiver for a tiny example
        self.assertEqual([c["test"] for c in fl.check_counts(counts)], ["b", "e"])

    def test_the_runner_lists_every_fuzz_test_file_of_the_suite(self):
        import fuzz_long as fl
        on_disk = {p.stem for p in (ROOT / "whynot-cut" / "tests").glob("test_fuzz_*.py") if p.stem != "test_fuzz_regressions"}
        self.assertEqual(set(fl.FILES), on_disk)


if __name__ == "__main__":
    unittest.main()
