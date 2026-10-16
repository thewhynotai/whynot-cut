# SPDX-License-Identifier: GPL-3.0-or-later
# © 2026 The Why Not AI (thewhynot.ai)
"""3.0 tools track, N2 - the owner's upstream WhyNot Tidy jsc test suites, run unchanged under node.

adobe/tools/tidy/_upstream/tests/test_{classify,lint,media,plan,sync}.js were written for macOS `jsc` (globals `print`,
`readFile`, `load`, top-level `this` as `window`, paths relative to the tool root). adobe/tools/_harness/jsc_shim.js
supplies those globals; each upstream file is one test method here and must exit 0, end with `ALL PASS`, print no
`FAIL ` line and print exactly the recorded number of `PASS ` lines (110 in all), so a silently skipped check is caught.

* `TidyUpstreamJsMixin.ROOT` is the tool root (cwd of the run: tests read `js/...`, `jsx/host.jsx`). The port's test
  class (Task 4) subclasses the mixin with ROOT = adobe/tools/tidy/src, VERIFY_SHA = False and, where a renamed
  expectation needs it, its own COUNTS; nothing below hard-codes the upstream path inside a test method.
* `test_upstream_files_unchanged` pins the upstream files these suites run (test files, the js/jsx they load or read)
  to adobe/tools/UPSTREAM-SHA256.txt, so a green run is a run of the owner's bytes.
Run:  bash tools/test.sh -p test_tidy_baseline_js.py
"""
import sys as _sys
_sys.dont_write_bytecode = True  # keep the plugin folder free of __pycache__
import _isolation  # noqa: F401,E402  G79: sandbox the engine home first (tests/_isolation.py)
import hashlib  # noqa: E402
import shutil  # noqa: E402
import subprocess  # noqa: E402
import unittest  # noqa: E402
from pathlib import Path  # noqa: E402

SK = Path(__file__).resolve().parents[1]
REPO = SK.parent
ADOBE_TOOLS = REPO / "adobe" / "tools"
SHIM = ADOBE_TOOLS / "_harness" / "jsc_shim.js"
SHA_FILE = ADOBE_TOOLS / "UPSTREAM-SHA256.txt"
NODE = shutil.which("node")
HAVE_TOOLS = ADOBE_TOOLS.is_dir()   # the shipped plugin zip has no repo-root adobe/: these suites then skip, not error
SKIP_REASON = "node is not installed" if not NODE else "adobe/tools is not part of this layout (the plugin zip ships without the repo-root adobe/)"


def run_suite(tc, root, test_file):
    """Run one jsc test file through jsc_shim.js with cwd = root; return (rc, stdout lines, stderr)."""
    p = subprocess.run([NODE, str(SHIM), str(root), test_file], capture_output=True, text=True, encoding="utf-8",
                       timeout=120, cwd=str(root))
    return p.returncode, p.stdout.splitlines(), p.stderr


@unittest.skipUnless(NODE and HAVE_TOOLS, SKIP_REASON)
class TidyUpstreamJsMixin:
    ROOT = ADOBE_TOOLS / "tidy" / "_upstream"
    VERIFY_SHA = True
    # test file (relative to ROOT) -> exact number of `PASS ` lines of a green run
    COUNTS = {
        "tests/test_classify.js": 25,
        "tests/test_lint.js": 4,
        "tests/test_media.js": 33,
        "tests/test_plan.js": 32,
        "tests/test_sync.js": 16,
    }
    # files (relative to ROOT) the suites load or read besides the test files; hashed when VERIFY_SHA
    DEPENDS = ["js/classify.js", "js/media.js", "js/plan.js", "js/sync.js", "jsx/host.jsx"]

    def check(self, test_file):
        rc, lines, err = run_suite(self, self.ROOT, test_file)
        fails = [ln for ln in lines if ln.startswith("FAIL ")]
        self.assertEqual(fails, [], "failing checks in %s:\n%s\n%s" % (test_file, "\n".join(fails), err))
        self.assertEqual(rc, 0, "exit %s for %s\n%s\n%s" % (rc, test_file, "\n".join(lines[-5:]), err))
        self.assertTrue(lines, "%s printed nothing: %s" % (test_file, err))
        self.assertEqual(lines[-1], "ALL PASS", "%s last line: %r" % (test_file, lines[-1]))
        passed = [ln for ln in lines if ln.startswith("PASS ")]
        self.assertEqual(len(passed), self.COUNTS[test_file], "PASS count of %s" % test_file)

    def test_classify(self):
        self.check("tests/test_classify.js")

    def test_lint(self):
        self.check("tests/test_lint.js")

    def test_media(self):
        self.check("tests/test_media.js")

    def test_plan(self):
        self.check("tests/test_plan.js")

    def test_sync(self):
        self.check("tests/test_sync.js")

    def test_counts_sum_to_the_audited_total(self):
        # portability audit 2.2: Tidy 5 files, 110 checks
        self.assertEqual(sorted(self.COUNTS), ["tests/test_%s.js" % n for n in ("classify", "lint", "media", "plan", "sync")])
        self.assertEqual(sum(self.COUNTS.values()), 110)

    def test_upstream_files_unchanged(self):
        if not self.VERIFY_SHA:
            self.skipTest("not an upstream root")
        want = {}
        for line in SHA_FILE.read_text(encoding="utf-8").splitlines():
            if line.strip():
                digest, rel = line.split(None, 1)
                want[rel.strip()] = digest
        base = self.ROOT.relative_to(ADOBE_TOOLS).as_posix()
        for rel in list(self.COUNTS) + self.DEPENDS:
            key = base + "/" + rel
            self.assertIn(key, want, key + " is not listed in UPSTREAM-SHA256.txt")
            got = hashlib.sha256((self.ROOT / rel).read_bytes()).hexdigest()
            self.assertEqual(got, want[key], key + " differs from UPSTREAM-SHA256.txt")


class TestTidyUpstreamJs(TidyUpstreamJsMixin, unittest.TestCase):
    pass


if __name__ == "__main__":
    unittest.main()
