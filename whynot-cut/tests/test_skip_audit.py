# SPDX-License-Identifier: GPL-3.0-or-later
# © 2026 The Why Not AI (thewhynot.ai)
"""BL-20, tools/skip_audit.py: the Gate 4 check "ZERO temporary dated skips". It finds every skip site in
whynot-cut/tests (AST), classes each one dated / platform/tool / unknown, and exits 0 clean, 1 a FAIL, 2 "could not run".
The fixtures are case_*.py under tests/fixtures/skip_audit/ (never test_*.py, so discovery never runs them).
Run:  bash tools/test.sh -p test_skip_audit.py
"""
import sys as _sys
_sys.dont_write_bytecode = True  # keep the plugin folder free of __pycache__
import _isolation  # noqa: F401,E402  G79: sandbox the engine home first (tests/_isolation.py)
import contextlib
import io
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SK = Path(__file__).resolve().parents[1]
REPO = SK.parent
FIX = SK / "tests" / "fixtures" / "skip_audit"
sys.path.insert(0, str(REPO / "tools"))

import skip_audit as SA  # noqa: E402


def _rm(tmp):
    def onerr(fn, path, _exc):  # git objects are read-only on Windows
        os.chmod(path, stat.S_IWRITE)
        fn(path)
    shutil.rmtree(tmp, onerror=onerr)


def audit_text(text, rel="whynot-cut/tests/test_x.py"):
    return SA.audit_source(rel, text)


def run_main(*argv):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = SA.main(list(argv))
    return code, out.getvalue(), err.getvalue()


def git(root, *args):
    return subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t.t", *args], cwd=str(root), check=True,
                          capture_output=True, text=True, encoding="utf-8").stdout


class Repo:
    """A temp git repo with whynot-cut/tests/."""
    def __init__(self, case):
        self.root = Path(tempfile.mkdtemp(prefix="skau_"))
        case.addCleanup(_rm, self.root)
        (self.root / "whynot-cut" / "tests").mkdir(parents=True)
        git(self.root, "init", "-q")

    def write(self, name, text):
        p = self.root / "whynot-cut" / "tests" / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")

    def commit(self, msg="c"):
        git(self.root, "add", "-A")
        git(self.root, "commit", "-q", "-m", msg)


UNKNOWN_SKIP = 'import unittest\n\n@unittest.skipIf(FLAG, "later")\ndef test_a():\n    pass\n'
DATED_SKIP = 'import unittest\n\n@unittest.skip("a dated skip, until the patch lands")\ndef test_b():\n    pass\n'
PLAIN = "import unittest\n\n\ndef test_ok():\n    pass\n"


class TestForms(unittest.TestCase):
    def test_every_form_is_found(self):
        sites = SA.audit_source("x.py", (FIX / "case_forms.py").read_text(encoding="utf-8"))
        reasons = sorted(s.reason for s in sites)
        self.assertEqual(len(sites), 12, [(s.line, s.kind) for s in sites])
        for want in ("form: skip", "form: skipIf", "form: skipUnless", "form: skipTest", "form: raise unittest.SkipTest",
                     "form: raise SkipTest", "form: pytest skip", "form: pytest skipif", "form: pytest xfail",
                     "the thing is not ready"):
            self.assertIn(want, reasons)
        kinds = {s.kind for s in sites}
        self.assertTrue({"expectedFailure", "SkipTest"} <= kinds, kinds)
        self.assertEqual({s.cls for s in sites}, {"unknown"})

    def test_a_decorator_name_is_not_a_second_site(self):
        text = "import unittest\nr = unittest.skipUnless(X, 'no')\n\n@r\ndef test_a():\n    pass\n\n@r\ndef test_b():\n    pass\n"
        self.assertEqual(len(audit_text(text)), 1)

    def test_a_plain_file_has_no_sites(self):
        self.assertEqual(audit_text(PLAIN), [])
        self.assertEqual(audit_text("import unittest\n\n\nclass T(unittest.TestCase):\n    def test_x(self):\n"
                                    "        try:\n            pass\n        except unittest.SkipTest:\n            pass\n"), [])


class TestClasses(unittest.TestCase):
    def test_the_61feeb2_incident_is_dated(self):
        sites = SA.audit_source("x.py", (FIX / "case_incident_61feeb2.py").read_text(encoding="utf-8"))
        self.assertEqual([s.cls for s in sites], ["dated"], sites)
        self.assertEqual(sites[0].kind, "skipIf")

    def test_platform_and_tool_skips_are_never_dated(self):
        sites = SA.audit_source("x.py", (FIX / "case_platform.py").read_text(encoding="utf-8"))
        self.assertEqual(len(sites), 9, [(s.line, s.reason) for s in sites])
        bad = [(s.line, s.cls, s.reason) for s in sites if s.cls != "platform/tool"]
        self.assertEqual(bad, [])

    def test_each_dated_marker(self):
        for label, deco in (
            ("dated skip in the reason", '@unittest.skip("an explicit, DATED skip")'),
            ("waits for ... patch", '@unittest.skip("waits for the engine patch")'),
            ("until ... lands", '@unittest.skip("until the fixture lands")'),
            ("an ISO date in the reason", '@unittest.skip("review 2026-10-19")'),
            ("a comment above", '# dated skip, executor\n@unittest.skip("x")'),
            ("a comment on the line", '@unittest.skip("x")  # an explicit, dated skip'),
            ("a _PENDING name", '@unittest.skipIf(_PENDING, "x")'),
        ):
            with self.subTest(label):
                (s,) = audit_text("import unittest\n%s\ndef test_a():\n    pass\n" % deco)
                self.assertEqual(s.cls, "dated")

    def test_dated_beats_a_platform_look(self):
        text = ('import unittest\ntry:\n    from helper import X\n    _PENDING = None\nexcept ImportError:\n'
                '    _PENDING = "needs the tool"  # dated skip\n\n@unittest.skipIf(_PENDING, _PENDING or "")\ndef test_a():\n    pass\n')
        (s,) = audit_text(text)
        self.assertEqual(s.cls, "dated")

    def test_the_marker_in_the_except_block_is_followed_from_the_condition_name(self):
        text = ('import unittest\ntry:\n    from helper import X\n    GATE = None\n'
                'except ImportError:  # executor: dated skip\n    GATE = "later"\n\n'
                '@unittest.skipIf(GATE, "later")\ndef test_a():\n    pass\n')
        (s,) = audit_text(text)
        self.assertEqual(s.cls, "dated")

    def test_a_date_outside_the_reason_does_not_make_it_dated(self):
        (s,) = audit_text('import unittest\n# review 2026-10-19\n@unittest.skipUnless(sys.platform == "win32", "windows only")\ndef test_a():\n    pass\n')
        self.assertEqual(s.cls, "platform/tool")

    def test_unknown_is_the_rest(self):
        (s,) = audit_text(UNKNOWN_SKIP)
        self.assertEqual(s.cls, "unknown")

    def test_arabic_reasons_and_comments(self):
        text = '# -*- coding: utf-8 -*-\nimport unittest\n\n# مؤجل حتى الإصلاح\n@unittest.skip("غير جاهز بعد")\ndef test_a():\n    pass\n'
        (s,) = audit_text(text)
        self.assertEqual(s.reason, "غير جاهز بعد")
        code, out, _ = run_main("--root", self.tree(text), "--all")
        self.assertIn("غير جاهز بعد", out)

    def tree(self, text):
        r = Repo(self)
        r.write("test_ar.py", text)
        r.commit()
        return str(r.root)


class TestRun(unittest.TestCase):
    def repo(self, **files):
        r = Repo(self)
        for name, text in files.items():
            r.write(name, text)
        r.commit()
        return r

    def test_clean_exits_0_and_says_how_many(self):
        r = self.repo(**{"test_a.py": PLAIN, "test_b.py": UNKNOWN_SKIP})
        code, out, _ = run_main("--root", str(r.root))
        self.assertEqual(code, 0, out)
        self.assertIn("unknown", out)
        self.assertIn("2 test files", out)

    def test_dated_fails_with_file_and_line(self):
        r = self.repo(**{"security/test_d.py": DATED_SKIP})
        code, out, _ = run_main("--root", str(r.root))
        self.assertEqual(code, 1, out)
        self.assertIn("whynot-cut/tests/security/test_d.py:3", out)
        self.assertIn("dated", out)

    def test_the_incident_copy_fails_the_run(self):
        r = self.repo(**{"test_mvh.py": (FIX / "case_incident_61feeb2.py").read_text(encoding="utf-8")})
        code, out, _ = run_main("--root", str(r.root))
        self.assertEqual(code, 1, out)
        self.assertIn("test_mvh.py:", out)

    def test_the_fixtures_folder_is_excluded(self):
        r = self.repo(**{"test_a.py": PLAIN, "fixtures/skip_audit/case_d.py": DATED_SKIP})
        code, out, _ = run_main("--root", str(r.root))
        self.assertEqual(code, 0, out)

    def test_default_lists_only_dated_and_all_lists_everything(self):
        r = self.repo(**{"test_u.py": UNKNOWN_SKIP, "test_d.py": DATED_SKIP})
        _, out, _ = run_main("--root", str(r.root))
        self.assertIn("test_d.py:3", out)
        self.assertNotIn("test_u.py:3", out)
        _, out, _ = run_main("--root", str(r.root), "--all")
        self.assertIn("test_u.py:3", out)

    def test_json_report(self):
        r = self.repo(**{"test_u.py": UNKNOWN_SKIP, "test_d.py": DATED_SKIP})
        code, out, _ = run_main("--root", str(r.root), "--json")
        self.assertEqual(code, 1)
        rep = json.loads(out)
        self.assertEqual(rep["exit"], 1)
        self.assertEqual(rep["counts"], {"dated": 1, "platform/tool": 0, "unknown": 1})
        self.assertEqual([f["file"] for f in rep["fail"]], ["whynot-cut/tests/test_d.py"])
        self.assertEqual({s["file"] for s in rep["sites"]}, {"whynot-cut/tests/test_d.py", "whynot-cut/tests/test_u.py"})


class TestSince(unittest.TestCase):
    def test_new_unknown_after_the_tag_fails_old_one_does_not(self):
        r = Repo(self)
        r.write("test_old.py", UNKNOWN_SKIP)
        r.commit("one")
        git(r.root, "tag", "t0")
        code, out, _ = run_main("--root", str(r.root), "--since", "t0")
        self.assertEqual(code, 0, out)                      # the same skip, before the tag
        r.write("test_new.py", UNKNOWN_SKIP)
        r.commit("two")
        code, out, _ = run_main("--root", str(r.root), "--since", "t0")
        self.assertEqual(code, 1, out)
        self.assertIn("test_new.py:3", out)
        self.assertNotIn("test_old.py:3", out)
        code, _, _ = run_main("--root", str(r.root))        # no --since: unknown is only listed
        self.assertEqual(code, 0)

    def test_a_skip_added_to_an_old_file_counts_by_its_line(self):
        r = Repo(self)
        r.write("test_a.py", UNKNOWN_SKIP)
        r.commit("one")
        git(r.root, "tag", "t0")
        r.write("test_a.py", UNKNOWN_SKIP + "\n\n@unittest.skip('later')\ndef test_c():\n    pass\n")
        r.commit("two")
        code, out, _ = run_main("--root", str(r.root), "--since", "t0")
        self.assertEqual(code, 1, out)
        self.assertIn("test_a.py:8", out)
        self.assertNotIn("test_a.py:3", out)

    def test_dated_fails_before_the_tag_too(self):
        r = Repo(self)
        r.write("test_d.py", DATED_SKIP)
        r.commit("one")
        git(r.root, "tag", "t0")
        r.write("test_other.py", PLAIN)
        r.commit("two")
        code, out, _ = run_main("--root", str(r.root), "--since", "t0")
        self.assertEqual(code, 1, out)
        self.assertIn("test_d.py:3", out)


class TestCouldNotRun(unittest.TestCase):
    def assert_not_run(self, code, out, err, words):
        self.assertEqual(code, 2, (out, err))
        self.assertNotIn("clean", (out + err).lower().replace("not clean", ""))
        self.assertIn(words, out + err)

    def test_a_syntax_error(self):
        r = Repo(self)
        r.write("test_bad.py", "def (:\n")
        r.write("test_ok.py", PLAIN)
        r.commit()
        code, out, err = run_main("--root", str(r.root))
        self.assert_not_run(code, out, err, "test_bad.py")
        self.assertIn("NOT RUN", out + err)

    def test_a_missing_tag(self):
        r = Repo(self)
        r.write("test_ok.py", PLAIN)
        r.commit()
        code, out, err = run_main("--root", str(r.root), "--since", "no-such-tag")
        self.assert_not_run(code, out, err, "no-such-tag")

    def test_root_is_not_a_repo(self):
        d = Path(tempfile.mkdtemp(prefix="skau_"))
        self.addCleanup(_rm, d)
        (d / "whynot-cut" / "tests").mkdir(parents=True)
        code, out, err = run_main("--root", str(d))
        self.assert_not_run(code, out, err, "not a git repo")

    def test_root_inside_a_repo_but_not_its_top(self):
        r = Repo(self)
        r.write("test_ok.py", PLAIN)
        r.commit()
        code, out, err = run_main("--root", str(r.root / "whynot-cut"))
        self.assert_not_run(code, out, err, "not a git repo")

    def test_a_repo_without_the_tests_folder(self):
        d = Path(tempfile.mkdtemp(prefix="skau_"))
        self.addCleanup(_rm, d)
        git(d, "init", "-q")
        code, out, err = run_main("--root", str(d))
        self.assert_not_run(code, out, err, "whynot-cut/tests")

    def test_git_not_on_path(self):
        r = Repo(self)
        r.write("test_ok.py", PLAIN)
        r.commit()
        empty = Path(tempfile.mkdtemp(prefix="skau_"))
        self.addCleanup(_rm, empty)
        env = dict(os.environ, PATH=str(empty))
        p = subprocess.run([sys.executable, "-I", str(REPO / "tools" / "skip_audit.py"), "--root", str(r.root)],
                           env=env, capture_output=True, text=True, encoding="utf-8")
        self.assert_not_run(p.returncode, p.stdout, p.stderr, "git")


class TestReadOnly(unittest.TestCase):
    @staticmethod
    def listing(root):
        out = []
        for p in sorted(Path(root).rglob("*")):
            if p.is_file():
                st = p.stat()
                out.append((p.relative_to(root).as_posix(), st.st_size, st.st_mtime_ns))
        return out

    def test_nothing_changes(self):
        r = Repo(self)
        r.write("test_a.py", UNKNOWN_SKIP)
        r.commit("one")
        git(r.root, "tag", "t0")
        r.write("test_b.py", DATED_SKIP)
        r.commit("two")
        before = self.listing(r.root)           # the scanned tree and .git (index included)
        for argv in ([], ["--all"], ["--json"], ["--since", "t0"]):
            run_main("--root", str(r.root), *argv)
        self.assertEqual(self.listing(r.root), before)

    def test_files_are_opened_read_only(self):
        src = (REPO / "tools" / "skip_audit.py").read_text(encoding="utf-8")
        for bad in ('"w"', "'w'", '"a"', "'a'", '"wb"', "write_text", "write_bytes", "unlink(", "rmtree", "os.remove"):
            self.assertNotIn(bad, src)
        for cmd in ('"commit"', '"add"', '"checkout"', '"reset"', '"tag"', '"stash"'):
            self.assertNotIn(cmd, src)


class TestPaths(unittest.TestCase):
    def test_output_paths_are_repo_relative_with_forward_slashes(self):
        r = Repo(self)
        r.write("security/fuzz/test_d.py", DATED_SKIP)
        r.commit()
        code, out, _ = run_main("--root", str(r.root))
        self.assertEqual(code, 1)
        self.assertIn("whynot-cut/tests/security/fuzz/test_d.py:3", out)
        self.assertNotIn("\\", out.replace("\\n", ""))
        self.assertNotIn(str(r.root), out)


if __name__ == "__main__":
    unittest.main()
