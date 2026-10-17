# SPDX-License-Identifier: GPL-3.0-or-later
# © 2026 The Why Not AI (thewhynot.ai)
"""Phase 4 Task 48 (L-T10): the long fuzz profile's gate (tools/security/fuzz_long.py) and the example-count rules of
tests/security/fuzz/_hyp.py.

The ruling: every target runs 10,000 examples; only a target whose single example is 100 KB or more may run 1,500 (a HEAVY
waiver listed in the report with its size). fuzz_long.py must FAIL (non-zero exit) when any target ran fewer. Nothing here
starts the long profile: the runs are faked.
Run:  tools/test.sh -p test_security_fuzz_long.py
"""
import sys as _sys
_sys.dont_write_bytecode = True
import _isolation  # noqa: F401,E402
import contextlib
import io
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
_sys.path.insert(0, str(ROOT / "tools" / "security"))
_sys.path.insert(0, str(HERE / "security" / "fuzz"))

import _hyp  # noqa: E402
import fuzz_long as fl  # noqa: E402


def line(test, n, cap=10000, space=None, heavy=None):
    return "FUZZ-COUNT %s %d cap %s space %s heavy %s" % (test, n, cap, space, heavy)


def parsed(*lines):
    return fl.parse_counts("\n".join(lines))


class CheckCounts(unittest.TestCase):
    def test_parse_reads_every_field(self):
        c = parsed(line("m.C.t", 9999, cap=10000, space=None, heavy=None), line("m.C.h", 1500, cap=1500, heavy=300000),
                   line("m.C.s", 25, cap=10000, space=25), "noise", "FUZZ-COUNT broken")
        self.assertEqual([x["test"] for x in c], ["m.C.t", "m.C.h", "m.C.s"])
        self.assertEqual((c[0]["count"], c[0]["space"], c[0]["heavy"]), (9999, None, None))
        self.assertEqual((c[1]["cap"], c[1]["heavy"]), (1500, 300000))
        self.assertEqual(c[2]["space"], 25)

    def test_full_counts_pass(self):
        c = parsed(line("a.t", 10000), line("a.u", 12345), line("a.h", 1500, cap=1500, heavy=300000), line("a.s", 25, space=25))
        self.assertEqual(fl.check_counts(c), [])

    def test_a_light_target_at_9999_fails(self):
        problems = fl.check_counts(parsed(line("a.t", 9999), line("a.u", 10000)))
        self.assertEqual([p["test"] for p in problems], ["a.t"])
        self.assertEqual(problems[0]["want"], 10000)
        self.assertIn("9999", problems[0]["why"])

    def test_a_lowered_cap_fails_even_when_the_target_ran_its_cap(self):
        problems = fl.check_counts(parsed(line("a.deep", 1500, cap=1500)))     # the old 'lowered max_examples means heavy' rule
        self.assertEqual([p["test"] for p in problems], ["a.deep"])
        self.assertIn("cap lowered", problems[0]["why"])

    def test_a_heavy_target_needs_1500_and_100_kb(self):
        self.assertEqual(fl.check_counts(parsed(line("a.h", 1499, cap=1500, heavy=100000)))[0]["want"], 1500)
        self.assertEqual(fl.check_counts(parsed(line("a.h", 1500, cap=1500, heavy=100000))), [])
        small = fl.check_counts(parsed(line("a.h", 1500, cap=1500, heavy=99999)))
        self.assertEqual([p["test"] for p in small], ["a.h"])
        self.assertIn("99999", small[0]["why"])

    def test_space_counts_only_when_smaller_than_the_requirement(self):
        self.assertEqual(fl.check_counts(parsed(line("a.s", 24, space=25))) [0]["want"], 25)      # exhausted too early
        self.assertEqual(fl.check_counts(parsed(line("a.s", 10000, space=10000)))[0]["test"], "a.s")  # space is not smaller
        self.assertEqual(fl.check_counts(parsed(line("a.s", 8115, space=8115))), [])

    def test_waivers_list_name_and_size(self):
        w = fl.waivers(parsed(line("a.t", 10000), line("a.h", 1500, cap=1500, heavy=300000)))
        self.assertEqual(w, [{"test": "a.h", "bytes": 300000, "required": 1500, "ran": 1500}])

    def test_report_lists_the_waived_targets_with_sizes_and_the_failures(self):
        res = [{"file": "f", "rc": 0, "seconds": 1, "tests": 2, "log": "x",
                "counts": parsed(line("a.t", 9999), line("a.h", 1500, cap=1500, heavy=300000))}]
        res[0]["below_target"] = fl.check_counts(res[0]["counts"])
        text = fl.report(res, "2026-01-01")
        self.assertIn("| a.h | 300000 | 1500 | 1500 |", text)
        self.assertIn("BELOW TARGET a.t", text)


class GateExitCode(unittest.TestCase):
    def _main(self, counts, rc=0):
        def fake(bash, name, env, log):
            return {"file": name, "rc": rc, "seconds": 0, "tests": 1, "counts": counts, "log": str(log)}
        with tempfile.TemporaryDirectory(prefix="wncfl-") as out, mock.patch.object(fl, "run_file", fake), \
                mock.patch.object(fl, "which_safe", lambda n: "bash"), mock.patch.object(fl.sys, "stderr", mock.MagicMock()), contextlib.redirect_stdout(io.StringIO()):
            return fl.main(["--only", "test_fuzz_serve", "--out", out])

    def test_exit_is_zero_when_every_target_ran_its_count(self):
        self.assertEqual(self._main(parsed(line("a.t", 10000), line("a.h", 1500, cap=1500, heavy=300000))), 0)

    def test_a_target_at_9999_makes_the_run_fail(self):
        self.assertEqual(self._main(parsed(line("a.t", 9999))), 1)

    def test_no_count_lines_at_all_fails(self):
        self.assertEqual(self._main([]), 1)

    def test_a_failing_test_run_fails_even_with_full_counts(self):
        self.assertEqual(self._main(parsed(line("a.t", 10000)), rc=1), 1)


class WhatTheGateCovers(unittest.TestCase):
    def test_the_files_come_from_the_disk_so_a_new_one_cannot_be_left_out(self):
        with tempfile.TemporaryDirectory(prefix="wncfl-") as d:
            for n in ("test_fuzz_a.py", "test_fuzz_new_family.py", "test_fuzz_regressions.py", "test_other.py"):
                (Path(d) / n).write_text("", encoding="utf-8")
            self.assertEqual(fl.discover_files(d), ["test_fuzz_a", "test_fuzz_new_family"])
        real = fl.discover_files()
        self.assertEqual(real, sorted(p.stem for p in HERE.glob("test_fuzz_*.py") if p.stem != "test_fuzz_regressions"))
        self.assertTrue({"test_fuzz_serve", "test_fuzz_files", "test_fuzz_xml", "test_fuzz_brandweb", "test_fuzz_media"} <= set(real))

    def test_the_only_file_without_a_fuzz_target_is_the_regression_replay(self):
        self.assertEqual(fl.NO_TARGETS, ("test_fuzz_regressions",))
        self.assertNotIn("fuzz(", (HERE / "test_fuzz_regressions.py").read_text(encoding="utf-8").replace("`fuzz()`", ""))

    def test_freeze_is_read_from_the_job_runners_lock_folder_only(self):
        with tempfile.TemporaryDirectory(prefix="wncfl-") as locks, tempfile.TemporaryDirectory(prefix="wncfl-") as out:
            (Path(locks) / "FREEZE").write_text("", encoding="utf-8")
            with mock.patch.dict(fl.os.environ, {"WNC_LOCKS_DIR": locks}), mock.patch.object(fl, "which_safe", lambda n: "bash"), \
                mock.patch.object(fl.sys, "stderr", mock.MagicMock()):
                self.assertEqual(fl.main(["--only", "test_fuzz_serve", "--out", out]), 75)
        self.assertNotIn("D:/", Path(fl.__file__).read_text(encoding="utf-8").split("def main")[1].split("out = Path")[0])

    def test_every_fuzz_decorator_is_paired_with_given_and_the_other_way_round(self):
        """`@fuzz()` without `@given` registers nothing (a plain test the gate never counts); `@given` without `@fuzz` runs with
        Hypothesis defaults and is never counted. Every test in a test_fuzz_*.py file has both or neither."""
        import ast
        for path in sorted(HERE.glob("test_fuzz_*.py")):
            for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
                if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    continue
                names = set()
                for d in node.decorator_list:
                    f = d.func if isinstance(d, ast.Call) else d
                    names.add(f.attr if isinstance(f, ast.Attribute) else getattr(f, "id", ""))
                self.assertEqual("fuzz" in names, "given" in names, "%s:%s has only one of @fuzz / @given" % (path.name, node.name))

    @unittest.skipUnless(_hyp.AVAILABLE, _hyp.INSTALL_HINT)
    def test_a_target_that_never_ran_is_printed_with_count_zero_and_fails_the_gate(self):
        """A registered fuzz target that did not run (skipped, or deselected) must not vanish from the FUZZ-COUNT lines."""
        code = ("import sys; sys.path.insert(0, %r); import _hyp\n"
                "class T:\n"
                "    @_hyp.fuzz()\n"
                "    @_hyp.given(_hyp.st.integers())\n"
                "    def test_never_called(self, n):\n"
                "        pass\n" % str(HERE / "security" / "fuzz"))
        env = dict(os.environ, WNC_FUZZ_PROFILE="long", PYTHONDONTWRITEBYTECODE="1")
        p = subprocess.run([_sys.executable, "-c", code], env=env, capture_output=True, text=True, timeout=60)
        counts = fl.parse_counts(p.stderr)
        self.assertEqual([(c["count"]) for c in counts], [0], p.stderr[-500:])
        self.assertEqual(len(fl.check_counts(counts)), 1)


class ExampleCountRules(unittest.TestCase):
    def test_max_examples_is_refused(self):
        with self.assertRaises(ValueError):
            _hyp._plan(None, None, None, {"max_examples": 30})
        with self.assertRaises(ValueError):
            _hyp.fuzz(max_examples=30)

    def test_heavy_needs_100_kb(self):
        with self.assertRaises(ValueError):
            _hyp.fuzz(heavy=99_999)
        _hyp.fuzz(heavy=100_000)

    def test_space_must_be_smaller_than_the_requirement(self):
        with self.assertRaises(ValueError):
            _hyp.fuzz(space=10_000)
        with self.assertRaises(ValueError):
            _hyp.fuzz(heavy=300_000, space=1_500)
        _hyp.fuzz(space=9_999)
        _hyp.fuzz(heavy=300_000, space=1_499)

    def test_unit_examples_lowers_only_the_unit_profile(self):
        n, required = _hyp._plan(None, None, 30, {})
        self.assertEqual(required, 10000)
        self.assertEqual(n, 30 if not _hyp.LONG else _hyp.EXAMPLES)


if __name__ == "__main__":
    unittest.main()
