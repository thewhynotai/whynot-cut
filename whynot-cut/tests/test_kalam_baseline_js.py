# SPDX-License-Identifier: GPL-3.0-or-later
# © 2026 The Why Not AI (thewhynot.ai)
"""3.0 tools track, N2/N3-kalam - the owner's WhyNot Kalam panel jsc test suites, run under node.

adobe/tools/kalam/_upstream/tests/panel/test_{html,mogrt,platform,range}.js were written for macOS `jsc` (globals `print`,
`readFile`, `load`, top-level `this` as `window`, paths relative to the tool root). adobe/tools/_harness/jsc_shim.js
supplies those globals; each suite is one test method here and must exit 0, end with `ALL PASS`, print no `FAIL ` line
and print exactly the recorded number of `PASS ` lines (35 in all upstream), so a silently skipped check is caught.

* `KalamUpstreamJsMixin.ROOT` is the tool root (cwd of the run: tests read `js/...`, `index.html`, the .mogrt fixture).
  `TestKalamPortJs` (N3-kalam) subclasses it with ROOT = adobe/tools/kalam/src, VERIFY_SHA = False, TEST_ROOT = the
  upstream root (the owner's test files are run, not copied), its own SUITES / COUNTS / TOTAL.
* On the port: test_range and test_mogrt are the owner's files unchanged (same PASS counts). test_mogrt reads the upstream
  fixture tests/panel/fixtures/tiny.mogrt, which the port does not carry: the run happens in a temporary copy of the port
  root plus that one fixture (EXTRA_FILES), never copied into the repo. test_platform is the R3 copy
  src/tests/panel/test_platform.js (its header lists every difference). test_html stays upstream-only (the UI is rebuilt
  by the Adobe track).
* `test_upstream_files_unchanged` pins the upstream files these suites run to adobe/tools/UPSTREAM-SHA256.txt (for the
  upstream root also the js/index.html they load and the exact file list), so a green run is a run of the owner's bytes.
  After every run the set of files under the run root must be unchanged (the shim writes nothing).
Run:  bash tools/test.sh -p test_kalam_baseline_js.py
"""
import sys as _sys
_sys.dont_write_bytecode = True  # keep the plugin folder free of __pycache__
import _isolation  # noqa: F401,E402  G79: sandbox the engine home first (tests/_isolation.py)
import hashlib  # noqa: E402
import os  # noqa: E402
import shutil  # noqa: E402
import subprocess  # noqa: E402
import tempfile  # noqa: E402
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
UPSTREAM = ADOBE_TOOLS / "kalam" / "_upstream"


def run_suite(root, test_file):
    """Run one jsc test file through jsc_shim.js with cwd = root; return (rc, stdout lines, stderr).
    Lines are split on LF only (str.splitlines also splits on VT, FF, U+2028 ... inside a message)."""
    p = subprocess.run([NODE, str(SHIM), str(root), test_file], capture_output=True, text=True, encoding="utf-8",
                       timeout=120, cwd=str(root))
    lines = p.stdout.split("\n")
    if lines and lines[-1] == "":
        lines.pop()
    return p.returncode, lines, p.stderr


def tree(root):
    """Every file under root, as sorted posix paths relative to it."""
    out = []
    for d, _dirs, files in os.walk(str(root)):
        for f in files:
            out.append(Path(d, f).relative_to(root).as_posix())
    return sorted(out)


def sha_listing():
    """UPSTREAM-SHA256.txt as {path relative to adobe/tools: sha256}."""
    want = {}
    for line in SHA_FILE.read_text(encoding="utf-8").splitlines():
        if line.strip():
            digest, rel = line.split(None, 1)
            want[rel.strip()] = digest
    return want


@unittest.skipUnless(NODE and HAVE_TOOLS, SKIP_REASON)
class KalamUpstreamJsMixin:
    ROOT = UPSTREAM
    TEST_ROOT = None   # where the owner's test files live when not under ROOT (the port runs the upstream test files)
    OWN_TESTS = ()     # test files (keys of COUNTS) that live under ROOT itself (R3 copies), not under TEST_ROOT
    EXTRA_FILES = {}   # {path relative to the run root: source file}: a temporary copy of ROOT + these runs the suites
    VERIFY_SHA = True
    TOTAL = 35         # portability audit 2.2: Kalam panel 4 files, 35 checks
    SUITES = ("html", "mogrt", "platform", "range")
    # test file (relative to ROOT) -> exact number of `PASS ` lines of a green run
    COUNTS = {
        "tests/panel/test_html.js": 2,
        "tests/panel/test_mogrt.js": 7,
        "tests/panel/test_platform.js": 16,
        "tests/panel/test_range.js": 10,
    }
    # files (relative to ROOT) the suites load or read besides the test files; hashed when VERIFY_SHA
    DEPENDS = ["index.html", "js/main.js", "js/platform.js", "js/cep.js", "js/range.js", "js/mogrt.js",
               "tests/panel/fixtures/tiny.mogrt"]

    def check(self, test_file):
        base = self.ROOT if (not self.TEST_ROOT or test_file in self.OWN_TESTS) else self.TEST_ROOT
        tests = test_file if base == self.ROOT else str(base / test_file)
        with tempfile.TemporaryDirectory() as td:
            run_root = self.ROOT
            if self.EXTRA_FILES:
                run_root = Path(td) / "root"
                shutil.copytree(str(self.ROOT), str(run_root))
                for rel, src in self.EXTRA_FILES.items():
                    (run_root / rel).parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(str(src), str(run_root / rel))
            before = tree(run_root)
            rc, lines, err = run_suite(run_root, tests)
            self.assertEqual(tree(run_root), before, "the run added or removed files under the tool root")
        fails = [ln for ln in lines if ln.startswith("FAIL ")]
        self.assertEqual(fails, [], "failing checks in %s:\n%s\n%s" % (test_file, "\n".join(fails), err))
        self.assertEqual(rc, 0, "exit %s for %s\n%s\n%s" % (rc, test_file, "\n".join(lines[-5:]), err))
        self.assertTrue(lines, "%s printed nothing: %s" % (test_file, err))
        self.assertEqual(lines[-1], "ALL PASS", "%s last line: %r" % (test_file, lines[-1]))
        passed = [ln for ln in lines if ln.startswith("PASS ")]
        self.assertEqual(len(passed), self.COUNTS[test_file], "PASS count of %s" % test_file)

    def test_html(self):
        self.check("tests/panel/test_html.js")

    def test_mogrt(self):
        self.check("tests/panel/test_mogrt.js")

    def test_platform(self):
        self.check("tests/panel/test_platform.js")

    def test_range(self):
        self.check("tests/panel/test_range.js")

    def test_counts_sum_to_the_audited_total(self):
        self.assertEqual(sorted(self.COUNTS), ["tests/panel/test_%s.js" % n for n in self.SUITES])
        self.assertEqual(sum(self.COUNTS.values()), self.TOTAL)

    def test_upstream_files_unchanged(self):
        """The upstream files a green run depends on: the test files that are the owner's (under TEST_ROOT or ROOT) and
        the extra fixtures; for the upstream root also the js/index.html they load and the exact file list."""
        want = sha_listing()
        up_root = self.TEST_ROOT or self.ROOT
        base = up_root.relative_to(ADOBE_TOOLS).as_posix()
        pinned = [(up_root, rel) for rel in self.COUNTS if rel not in self.OWN_TESTS]
        pinned += [(UPSTREAM, str(src.relative_to(UPSTREAM).as_posix())) for src in self.EXTRA_FILES.values()]
        if self.VERIFY_SHA:
            listed = sorted(k[len(base) + 1:] for k in want if k.startswith(base + "/"))
            self.assertEqual(tree(self.ROOT), listed, "files under the upstream root differ from UPSTREAM-SHA256.txt")
            pinned += [(self.ROOT, rel) for rel in self.DEPENDS]
        for root, rel in pinned:
            key = root.relative_to(ADOBE_TOOLS).as_posix() + "/" + rel
            self.assertIn(key, want, key + " is not listed in UPSTREAM-SHA256.txt")
            got = hashlib.sha256((root / rel).read_bytes()).hexdigest()
            self.assertEqual(got, want[key], key + " differs from UPSTREAM-SHA256.txt")


class TestKalamUpstreamJs(KalamUpstreamJsMixin, unittest.TestCase):
    pass


class TestKalamPortJs(KalamUpstreamJsMixin, unittest.TestCase):
    """The same suites against the port (adobe/tools/kalam/src): range and mogrt unchanged, platform as R3 copy."""
    ROOT = ADOBE_TOOLS / "kalam" / "src"
    TEST_ROOT = UPSTREAM
    OWN_TESTS = ("tests/panel/test_platform.js",)
    EXTRA_FILES = {"tests/panel/fixtures/tiny.mogrt": UPSTREAM / "tests" / "panel" / "fixtures" / "tiny.mogrt"}
    VERIFY_SHA = False
    SUITES = ("mogrt", "platform", "range")
    TOTAL = 37     # 7 + 20 + 10 (the R3 copy has 20 checks: 16 upstream minus 3 cleanPath plus 7 new)
    COUNTS = {
        "tests/panel/test_mogrt.js": 7,
        "tests/panel/test_platform.js": 20,
        "tests/panel/test_range.js": 10,
    }

    def test_html(self):
        self.skipTest("test_html.js checks the owner's index.html and main.js: upstream only, the UI is rebuilt by the Adobe track")

    def test_port_has_the_three_modules_and_the_r3_copy(self):
        self.assertEqual(tree(self.ROOT), ["README.md", "js/mogrt.js", "js/platform.js", "js/range.js",
                                           "tests/panel/test_platform.js"])


if __name__ == "__main__":
    unittest.main()
