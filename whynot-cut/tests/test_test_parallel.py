"""OPS-09: tools/test_parallel.py, the parallel full suite behind `tools/test.sh --parallel N`.

Every run here points the tool at a small temp git repo whose tests folder is made of fixtures
(tests/fixtures/test_parallel/case_*.py, copied in as test_*.py), a temp cache folder (WHYNOT_SUITE_CACHE) and,
where it matters, a simulated RAM reading (WHYNOT_PARALLEL_FAKE_RAM_FILE). The real suite is never run.
Run:  bash tools/test.sh -p test_test_parallel.py
"""
import sys as _sys
_sys.dont_write_bytecode = True  # keep the plugin folder free of __pycache__
import _isolation  # noqa: F401,E402  G79: sandbox the engine home first (tests/_isolation.py)
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

SK = Path(__file__).resolve().parents[1]
REPO = SK.parent
TOOL = REPO / "tools" / "test_parallel.py"
FIX = Path(__file__).resolve().parent / "fixtures" / "test_parallel"
STATE_ENV = "WNC_PARALLEL_FIXTURE_STATE"


def load_tool():
    spec = importlib.util.spec_from_file_location("_wnc_test_parallel", TOOL)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def git(repo, *args):
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@example.invalid", "-c", "core.autocrlf=false",
                    *args], cwd=str(repo), check=True, capture_output=True)


class Case(unittest.TestCase):
    """A temp repo <tmp>/repo (git, one commit) with whynot-cut/tests/ holding the chosen fixtures."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="wnc-par-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.repo = self.tmp / "repo"
        self.tests = self.repo / "whynot-cut" / "tests"
        self.tests.mkdir(parents=True)
        (self.repo / "tools").mkdir()
        (self.repo / "tools" / "x.txt").write_bytes(b"x\n")
        self.cache = self.tmp / "cache"
        self.state = self.tmp / "state"
        self.state.mkdir()
        self.tool = TOOL

    def use(self, *cases, commit=True):
        for c in cases:
            shutil.copyfile(FIX / f"case_{c}.py", self.tests / f"test_{c}.py")
        if commit:
            git(self.repo, "init", "-q")
            git(self.repo, "add", "-A")
            git(self.repo, "commit", "-q", "-m", "fixture")

    def env(self, **extra):
        e = dict(os.environ, WHYNOT_SUITE_CACHE=str(self.cache), PYTHONUTF8="1", WHYNOT_PARALLEL_POLL="0.2")
        e[STATE_ENV] = str(self.state)
        e.pop("WHYNOT_PARALLEL_FAKE_RAM_FILE", None)
        e.update(extra)
        return e

    def argv(self, *extra, workers="2", lane=""):
        return [sys.executable, "-B", str(self.tool), "--workers", workers, "--repo", str(self.repo),
                "--tests-dir", str(self.tests), "--serial-lane", lane, *extra]

    def run_tool(self, *extra, lane="", env=None, workers="2"):
        r = subprocess.run(self.argv(*extra, workers=workers, lane=lane), capture_output=True,
                           env=env or self.env(), timeout=300)
        out = (r.stdout.decode("utf-8") + r.stderr.decode("utf-8")).replace("\r\n", "\n")   # Windows text mode
        return r.returncode, out

    def events(self):
        f = self.state / "events.txt"
        return f.read_text(encoding="utf-8").split() if f.exists() else []

    def run_serial(self, env=None):
        """The serial run exactly as tools/test.sh does it (cwd = repo root, -m unittest discover -s ...)."""
        r = subprocess.run([sys.executable, "-B", "-W", "error::ResourceWarning", "-m", "unittest", "discover",
                            "-s", "whynot-cut/tests"], cwd=str(self.repo), capture_output=True,
                           env=env or self.env(), timeout=300)
        return r.returncode, (r.stdout.decode("utf-8", "replace") + r.stderr.decode("utf-8", "replace")
                              ).replace("\r\n", "\n")

    def assert_last_line(self, out, prefix):
        self.assertTrue(out.rstrip("\n").splitlines()[-1].startswith(prefix), out)

    def cache_entries(self):
        return sorted(p.name for p in self.cache.glob("*.json") if p.name != "durations.json") \
            if self.cache.exists() else []


class Discovery(Case):
    def test_module_discovery_equals_unittest_discover(self):
        self.use("pass_a", "pass_b", "fail", "arabic", commit=False)
        (self.tests / "helper.py").write_bytes(b"X = 1\n")              # not test*.py: discover skips it
        (self.tests / "test-dash.py").write_bytes(b"import unittest\n")  # not an importable name: discover skips it
        (self.tests / "data").mkdir()
        shutil.copyfile(FIX / "case_pass_a.py", self.tests / "data" / "test_inner.py")   # no __init__: not a package
        tool = load_tool()
        got = tool.discover_modules(self.tests)
        suite = unittest.TestLoader().discover(str(self.tests))
        want = set()

        def walk(s):
            for t in s:
                if isinstance(t, unittest.TestSuite):
                    walk(t)
                else:
                    want.add(t.id().split(".")[0])
        try:
            walk(suite)
        finally:
            for m in list(sys.modules):
                if m in ("test_pass_a", "test_pass_b", "test_fail", "test_arabic"):
                    del sys.modules[m]
            while str(self.tests) in sys.path:
                sys.path.remove(str(self.tests))
        self.assertEqual(sorted(got), sorted(want))
        self.assertEqual(sorted(got), ["test_arabic", "test_fail", "test_pass_a", "test_pass_b"])

    def test_a_test_package_is_refused_with_exit_2(self):
        self.use("pass_a", commit=False)
        pkg = self.tests / "subpkg"
        pkg.mkdir()
        (pkg / "__init__.py").write_bytes(b"")
        shutil.copyfile(FIX / "case_pass_b.py", pkg / "test_inside.py")
        git(self.repo, "init", "-q")
        code, out = self.run_tool()
        self.assertEqual(code, 2, out)
        self.assertIn("subpkg", out)
        self.assertNotIn("\nOK", out)


class SameAsSerial(Case):
    """Review r1 P1-1 / P3-3: a worker imports and prints exactly like the serial `-m unittest discover` run.
    The tool runs from <repo>/tools/, as in the real repo, so its own folder is the one that must not leak in."""

    def setUp(self):
        super().setUp()
        self.tool = self.repo / "tools" / "test_parallel.py"
        shutil.copyfile(TOOL, self.tool)

    def test_sys_path_is_the_same_as_the_serial_run(self):
        self.use("syspath")
        code, out = self.run_serial()
        self.assertEqual(code, 0, out)
        serial = json.loads((self.state / "syspath.json").read_text(encoding="utf-8"))
        (self.state / "syspath.json").unlink()
        code, out = self.run_tool()
        self.assertEqual(code, 0, out)
        par = json.loads((self.state / "syspath.json").read_text(encoding="utf-8"))
        self.assertEqual(par, serial)                                     # same entries, same order
        self.assertNotIn(str(self.repo / "tools"), par)

    def test_a_module_only_in_tools_fails_to_import_in_both_modes(self):
        (self.repo / "tools" / "wnc_tools_only_helper.py").write_bytes(b"X = 1\n")
        self.use("tools_import", "pass_b", "surrogate")
        scode, sout = self.run_serial()
        self.assertEqual(scode, 1, sout)
        code, out = self.run_tool()
        self.assertEqual(code, 1, out)

        def problems(text):
            return sorted(x for x in text.splitlines() if x.startswith(("FAIL: ", "ERROR: ")))
        self.assertEqual(problems(out), problems(sout))
        self.assertEqual(len(problems(out)), 2, out)                      # the tools/ import + the lone surrogate
        self.assertIn("wnc_tools_only_helper", out)
        self.assertIn("FAILED (errors=2)", out)
        self.assertIn("FAILED (errors=2)", sout)

    def test_workers_keep_the_parent_temp_variables_unchanged(self):     # fix round 3: semgrep fails on a long TEMP
        self.use("tempenv")
        dirs = [self.tmp / n for n in ("parent-temp", "parent-tmp", "parent-tmpdir")]
        for d in dirs:
            d.mkdir()
        cases = (dict(TEMP=str(dirs[0]), TMP=str(dirs[1]), TMPDIR=str(dirs[2])),   # three different strings
                 dict(TEMP=str(dirs[0]), TMP=str(dirs[1])))                          # no TMPDIR: none in the worker
        seen = self.state / "tempenv.json"
        for parent in cases:
            with self.subTest(parent=sorted(parent)):
                env = self.env(**parent)
                if "TMPDIR" not in parent:
                    env.pop("TMPDIR", None)
                want = {"TEMP": parent["TEMP"], "TMP": parent["TMP"], "TMPDIR": parent.get("TMPDIR")}
                code, out = self.run_serial(env=env)
                self.assertEqual(code, 0, out)
                serial = json.loads(seen.read_text(encoding="utf-8"))
                seen.unlink()
                code, out = self.run_tool("--fresh", env=env)
                self.assertEqual(code, 0, out)
                par = json.loads(seen.read_text(encoding="utf-8"))
                seen.unlink()
                self.assertEqual({k: par[k] for k in want}, want)               # the same strings as the parent
                self.assertEqual(par, serial)                                     # and as the serial run


class Ordering(unittest.TestCase):
    def test_lpt_order_from_recorded_durations(self):
        tool = load_tool()
        mods = ["a", "b", "c", "d"]
        order = tool.order_modules(mods, {"a": 5.0, "b": 50.0, "c": 1.0, "d": 20.0}, {m: 100 for m in mods})
        self.assertEqual(order, ["b", "d", "a", "c"])

    def test_lpt_order_from_file_sizes_when_no_durations(self):
        tool = load_tool()
        order = tool.order_modules(["a", "b", "c"], {}, {"a": 10, "b": 3000, "c": 200})
        self.assertEqual(order, ["b", "c", "a"])

    def test_missing_duration_is_estimated_from_size(self):
        tool = load_tool()
        # a and b known (1 s per 100 bytes); c has no duration but 5000 bytes -> ~50 s: first
        order = tool.order_modules(["a", "b", "c"], {"a": 10.0, "b": 2.0}, {"a": 1000, "b": 200, "c": 5000})
        self.assertEqual(order, ["c", "a", "b"])

    def test_relabel_selector_strips_holders_and_subtest_params(self):   # review r1 P3-4
        tool = load_tool()
        self.assertEqual(tool._selector("setUpClass (test_m.C)"), "test_m.C")
        self.assertEqual(tool._selector("test_m.C.test_x (i=1)"), "test_m.C.test_x")
        self.assertEqual(tool._selector("test_m.C.test_x [msg] (i=1)"), "test_m.C.test_x")
        self.assertEqual(tool._selector("test_m.C.test_x"), "test_m.C.test_x")


class Results(Case):
    def test_green_run_prints_ran_and_ok_and_exits_0(self):
        self.use("pass_a", "pass_b")
        code, out = self.run_tool()
        self.assertEqual(code, 0, out)
        self.assertIn("Ran 4 tests in ", out)
        self.assertIn("\nOK (skipped=1)\n", out)
        self.assertIn("parallel: workers=2", out)

    def test_failing_fixture_counts_as_failure_exit_1(self):
        self.use("pass_a", "fail")
        code, out = self.run_tool()
        self.assertEqual(code, 1, out)
        self.assertIn("FAIL: test_always_fails (test_fail.Fails", out)
        self.assertIn("AssertionError", out)
        self.assertIn("ERROR: test_raises (test_fail.Fails", out)
        self.assertIn("Ran 5 tests in ", out)
        self.assertIn("FAILED (failures=1, errors=1, skipped=1)", out)
        self.assertIn("test_fail.Fails.test_always_fails: fails alone too", out)
        self.assertIn("test_fail.Fails.test_raises: fails alone too", out)
        # review r1 P3-1: the labels come before the verdict, so the last lines are always `Ran ...` / FAILED
        self.assertLess(out.rindex("parallel: label: "), out.rindex("\nRan 5 tests in "))
        self.assert_last_line(out, "FAILED (failures=1, errors=1, skipped=1)")

    def test_green_run_ends_with_the_ok_line(self):
        self.use("pass_a")
        code, out = self.run_tool()
        self.assertEqual(code, 0, out)
        self.assert_last_line(out, "OK (skipped=1)")
        self.assertLess(out.rindex("parallel: workers="), out.rindex("\nRan 2 tests in "))

    def test_an_unexpected_success_is_a_failure(self):                   # review r1 P2-3
        self.use("pass_b", "xpass")
        code, out = self.run_tool()
        self.assertEqual(code, 1, out)
        self.assertIn("FAILED (unexpected successes=1)", out)
        self.assertNotIn("\nOK", out)
        self.assertEqual(len(self.cache_entries()), 1)                   # complete, so stored, with its exit code 1
        self.assertEqual(self.run_tool()[0], 1)

    def test_load_sensitive_failure_is_labelled_and_still_fails(self):
        self.use("pass_a", "flaky")
        code, out = self.run_tool()
        self.assertEqual(code, 1, out)                                   # the strict rule: the label changes nothing
        self.assertIn("FAILED (failures=1, skipped=1)", out)
        self.assertIn("test_flaky.Flaky.test_fails_first_time: load-sensitive (passed alone)", out)
        self.assertEqual(self.events().count("flaky"), 2)                # first run + the labelling re-run

    def test_problem_and_incomplete_modules_keep_their_log_clean_ones_do_not(self):   # fix round 3
        self.use("pass_a", "fail", "xpass", "killed")
        ptemp = self.tmp / "ptemp"
        ptemp.mkdir()
        code, out = self.run_tool(env=self.env(TEMP=str(ptemp), TMP=str(ptemp), TMPDIR=str(ptemp)))
        self.assertEqual(code, 2, out)
        runs = list(ptemp.glob("wnc-par-*"))
        self.assertEqual(len(runs), 1, out)
        for tag in ("m-test_fail", "m-test_xpass", "m-test_killed"):      # failure/error, unexpected success, killed
            log = runs[0] / tag / "worker.log"
            self.assertTrue(log.is_file(), tag + "\n" + out)
            self.assertIn(f"parallel: log kept: {tag}: {log}\n", out)
        self.assertIn("boom", (runs[0] / "m-test_fail" / "worker.log").read_text(encoding="utf-8", errors="replace"))
        self.assertFalse((runs[0] / "m-test_pass_a").exists(), "a clean module's log is tidied away")
        self.assertNotIn("log kept: m-test_pass_a", out)
        self.assert_last_line(out, "FAILED (incomplete: m-test_killed: ")

    def test_arabic_test_names_and_messages_print_as_utf8(self):
        self.use("arabic")
        code, out = self.run_tool()
        self.assertEqual(code, 1, out)
        self.assertIn("test_عربي", out)
        self.assertIn("الجملة غلط: ٣ مش ٤", out)
        self.assertIn("رسالة الخطأ", out)


class Incomplete(Case):
    def assert_nothing_stored(self):
        stored = sorted(p.name for p in self.cache.glob("*")) if self.cache.exists() else []
        self.assertEqual(stored, [], "an incomplete run must store no cache entry and no durations")

    def test_killed_worker_exits_2_no_cache_no_durations(self):
        self.use("pass_a", "killed")
        code, out = self.run_tool()
        self.assertEqual(code, 2, out)
        self.assertIn("INCOMPLETE", out)
        self.assertIn("test_killed", out)
        self.assertNotIn("\nOK", out)
        self.assert_nothing_stored()
        self.assert_last_line(out, "FAILED (incomplete: m-test_killed: ")   # review r1 P3-2: greps fail closed

    def test_a_record_then_a_non_zero_exit_is_incomplete(self):          # review r1 P2-4
        self.use("pass_a", "exit_after_record")
        code, out = self.run_tool()
        self.assertEqual(code, 2, out)
        self.assertIn("test_exit_after_record", out)
        self.assertIn("did not exit by itself (exit code 3)", out)
        self.assertNotIn("\nOK", out)
        self.assert_nothing_stored()
        self.assert_last_line(out, "FAILED (incomplete: ")

    def test_a_crash_inside_the_tool_exits_2(self):                      # review r1 P3-5
        self.use("pass_a")
        code, out = self.run_tool(env=self.env(WHYNOT_PARALLEL_POLL="not-a-number"))
        self.assertEqual(code, 2, out)
        self.assertNotIn("\nOK", out)
        self.assert_last_line(out, "FAILED (incomplete: tool error: ")
        self.assert_nothing_stored()

    def test_missing_record_exits_2_even_with_rc_0(self):
        self.use("pass_a", "norecord")
        code, out = self.run_tool()
        self.assertEqual(code, 2, out)
        self.assertIn("test_norecord", out)
        self.assertIn("no result record", out)
        self.assertNotIn("\nOK", out)
        self.assert_nothing_stored()

    def test_bad_worker_count_exits_2(self):
        self.use("pass_a")
        code, out = self.run_tool(workers="1")
        self.assertEqual(code, 2, out)


class Cache(Case):
    def test_cache_hit_reuses_the_report_and_says_so(self):
        self.use("pass_a", "fail")
        code1, out1 = self.run_tool()
        self.assertEqual(code1, 1, out1)
        self.assertTrue((self.cache / "durations.json").is_file())
        ran = len(self.events())
        code2, out2 = self.run_tool()
        self.assertEqual(code2, 1, out2)                                  # the stored exit code
        self.assertTrue(out2.startswith("reused: "), out2)
        self.assertIn(" from ", out2.splitlines()[0])
        self.assertIn("FAILED (failures=1, errors=1, skipped=1)", out2)
        self.assertEqual(len(self.events()), ran, "a cache hit runs nothing")

    def test_a_dirty_tree_change_misses_the_cache(self):
        self.use("pass_a")
        self.assertEqual(self.run_tool()[0], 0)
        f = self.tests / "test_pass_a.py"
        f.write_bytes(f.read_bytes() + b"\n# edited\n")                   # tracked change: git diff HEAD
        code, out = self.run_tool()
        self.assertEqual(code, 0, out)
        self.assertFalse(out.startswith("reused: "), out)
        self.assertTrue(self.run_tool()[1].startswith("reused: "))
        (self.repo / "tools" / "new.txt").write_bytes(b"new\n")           # untracked, not ignored, under tools/
        self.assertFalse(self.run_tool()[1].startswith("reused: "))

    def test_a_line_ending_only_change_misses_the_cache(self):           # review r1 P2-1
        (self.repo / ".gitattributes").write_bytes(b"* text=auto eol=lf\n")   # this repo's own settings
        self.use("pass_a")
        git(self.repo, "config", "core.autocrlf", "true")
        self.assertEqual(self.run_tool()[0], 0)
        self.assertTrue(self.run_tool()[1].startswith("reused: "))
        f = self.tests / "test_pass_a.py"
        f.write_bytes(f.read_bytes().replace(b"\n", b"\r\n"))             # LF -> CRLF only
        code, out = self.run_tool()
        self.assertEqual(code, 0, out)
        self.assertFalse(out.startswith("reused: "), out)

    def test_an_untracked_file_anywhere_in_the_repo_misses_the_cache(self):   # review r1 P3-7
        self.use("pass_a")
        self.assertEqual(self.run_tool()[0], 0)
        self.assertTrue(self.run_tool()[1].startswith("reused: "))
        (self.repo / "notes.txt").write_bytes(b"untracked, not ignored, at the repo root\n")
        self.assertFalse(self.run_tool()[1].startswith("reused: "))

    def test_test_switch_env_vars_are_in_the_key(self):                  # review r1 P2-2
        self.use("pass_a")
        self.assertEqual(self.run_tool()[0], 0)
        for name in ("WHYNOT_SLOW_TESTS", "WNC_INSTALLER_LIVE", "NH_INTEGRATION", "WHYNOTCUT_SHELLCHECK"):
            out = self.run_tool(env=self.env(**{name: "wnc-key-probe"}))[1]
            self.assertFalse(out.startswith("reused: "), name + "\n" + out)
            self.assertTrue(self.run_tool(env=self.env(**{name: "wnc-key-probe"}))[1].startswith("reused: "), name)
        # the tool's own control vars are not part of the key
        self.assertTrue(self.run_tool(env=self.env(WHYNOT_PARALLEL_POLL="0.3"))[1].startswith("reused: "))

    def test_a_tree_changed_during_the_run_is_not_cached(self):          # review r1 P1-2
        self.use("pass_a", "edits_tree")
        code, out = self.run_tool()
        self.assertEqual(code, 0, out)
        self.assertIn("parallel: tree changed during the run; not cached", out)
        self.assertEqual(self.cache_entries(), [])
        git(self.repo, "checkout", "--", "tools/x.txt")                   # back to exactly the committed tree
        code, out = self.run_tool()
        self.assertFalse(out.startswith("reused: "), out)

    def test_a_tree_edited_and_reverted_during_the_run_is_not_cached(self):   # review r2 P1-1
        self.use("pass_a", "edits_and_reverts")
        before = (self.repo / "tools" / "x.txt").read_bytes()
        code, out = self.run_tool()
        self.assertEqual(code, 0, out)
        self.assertEqual((self.repo / "tools" / "x.txt").read_bytes(), before)   # same bytes at the end
        self.assertIn("parallel: tree touched during the run; not cached", out)
        self.assertEqual(self.cache_entries(), [])
        self.assertFalse((self.cache / "durations.json").exists(), "store nothing")
        code, out = self.run_tool()
        self.assertFalse(out.startswith("reused: "), out)

    def test_git_takes_no_optional_index_lock(self):                     # review r2 P3-1
        self.use("pass_a")
        x = self.repo / "tools" / "x.txt"
        time.sleep(0.05)
        x.write_bytes(x.read_bytes())                                     # same bytes, new mtime: a stale index entry
        index = self.repo / ".git" / "index"
        st = index.stat()
        self.assertEqual(self.run_tool()[0], 0)
        st2 = index.stat()
        self.assertEqual((st.st_mtime_ns, st.st_size), (st2.st_mtime_ns, st2.st_size),
                         "the tool rewrote .git/index (git status without --no-optional-locks)")
        src = TOOL.read_text(encoding="utf-8")
        self.assertIn('["git", "--no-optional-locks", *args]', src)
        self.assertEqual(src.count('["git"'), 1, "every git call goes through g()")

    def test_cache_and_durations_are_written_atomically(self):           # review r2 P3-2
        tool = load_tool()
        d = self.tmp / "w"
        d.mkdir()
        calls = []
        real = tool.os.replace

        def spy(src, dst):
            calls.append((Path(src), Path(dst)))
            return real(src, dst)
        tool.os.replace = spy
        try:
            tool.atomic_write(d / "entry.json", "عربي")
        finally:
            tool.os.replace = real
        self.assertEqual((d / "entry.json").read_text(encoding="utf-8"), "عربي")
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0][0].parent, d)                           # temp file in the same folder
        self.assertEqual(calls[0][1], d / "entry.json")
        self.assertEqual(sorted(p.name for p in d.iterdir()), ["entry.json"])   # no temp file left
        src = TOOL.read_text(encoding="utf-8")
        self.assertNotIn("dur_file.write_text", src)
        self.assertNotIn("entry.write_text", src)

    def test_fresh_ignores_the_cache(self):
        self.use("pass_a")
        self.assertEqual(self.run_tool()[0], 0)
        ran = len(self.events())
        code, out = self.run_tool("--fresh")
        self.assertEqual(code, 0, out)
        self.assertFalse(out.startswith("reused: "), out)
        self.assertGreater(len(self.events()), ran)


class SerialLane(Case):
    def test_lane_ids_run_alone_after_the_parallel_run_and_count(self):
        self.use("pass_a", "pass_b", "lane")
        code, out = self.run_tool(lane="test_lane.Heavy.test_alone,test_lane.WholeClass")
        self.assertEqual(code, 0, out)
        ev = self.events()
        self.assertEqual(ev.count("lane-alone"), 1)                       # not also run in the parallel phase
        self.assertEqual(ev.count("lane-class"), 2)
        last_parallel = max(i for i, e in enumerate(ev) if e in ("a", "b", "lane-other"))
        lane_idx = [i for i, e in enumerate(ev) if e.startswith("lane-") and e != "lane-other"]
        self.assertGreater(min(lane_idx), last_parallel)
        self.assertIn("Ran 8 tests in ", out)                            # 2 + 2 + 1 other + 1 alone + 2 class

    def test_a_lane_id_that_matches_no_test_exits_2(self):
        self.use("pass_a", "lane")
        code, out = self.run_tool(lane="test_lane.Heavy.test_renamed")
        self.assertEqual(code, 2, out)
        self.assertIn("test_lane.Heavy.test_renamed", out)

    def test_default_lane_names_real_tests(self):
        tool = load_tool()
        self.assertEqual(tool.DEFAULT_SERIAL_LANE, (
            "test_identity_scan.TestRealTree.test_full_repo_scan_is_fast",
            "test_serve_progress.AdapterRun", "test_serve_progress.ThroughTheDaemon"))
        tests = SK / "tests"
        self.assertIn("    def test_full_repo_scan_is_fast(self):",
                      (tests / "test_identity_scan.py").read_text(encoding="utf-8"))
        src = (tests / "test_serve_progress.py").read_text(encoding="utf-8")
        self.assertIn("\nclass AdapterRun(", src)
        self.assertIn("\nclass ThroughTheDaemon(", src)


class RamBrake(Case):
    def test_no_module_starts_while_ram_is_high_then_it_goes_on(self):
        self.use("pass_a")
        ram = self.tmp / "ram.txt"
        ram.write_bytes(b"92\n")
        p = subprocess.Popen(self.argv(), stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                             env=self.env(WHYNOT_PARALLEL_FAKE_RAM_FILE=str(ram)))
        try:
            time.sleep(3)
            self.assertIsNone(p.poll(), "the run must wait, not finish or give up")
            self.assertEqual(self.events(), [], "no module may start at RAM >= 85 %")
            ram.write_bytes(b"40\n")
            raw, _ = p.communicate(timeout=120)
        finally:
            if p.poll() is None:
                p.kill()
                p.communicate()
        out = raw.decode("utf-8").replace("\r\n", "\n")
        self.assertEqual(p.returncode, 0, out)
        self.assertIn("RAM brake", out)
        self.assertIn("Ran 2 tests in ", out)
        self.assertIn("ram_peak=92%", out)

    def test_unreadable_ram_is_said_once_and_the_run_goes_on(self):
        self.use("pass_a")
        code, out = self.run_tool(env=self.env(WHYNOT_PARALLEL_FAKE_RAM_FILE=str(self.tmp / "missing.txt")))
        self.assertEqual(code, 0, out)
        self.assertEqual(out.count("RAM cannot be read"), 1, out)


class ThroughTestSh(Case):
    def test_test_sh_parallel_dispatches_to_the_tool(self):
        from test_wrappers import git_bash
        bash = git_bash()
        if not bash:
            self.skipTest("no bash")
        self.use("pass_a")
        r = subprocess.run([bash, str(REPO / "tools" / "test.sh"), "--parallel", "2", "--repo", str(self.repo),
                            "--tests-dir", str(self.tests), "--serial-lane", ""], capture_output=True,
                           env=self.env(WHYNOT_HOME=str(_isolation.REAL_ENGINE_HOME)), timeout=300)  # read only
        out = r.stdout.decode("utf-8") + r.stderr.decode("utf-8")
        self.assertEqual(r.returncode, 0, out)
        self.assertIn("Ran 2 tests in ", out)
        self.assertIn("parallel: workers=2", out)


if __name__ == "__main__":
    unittest.main()
