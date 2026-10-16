# SPDX-License-Identifier: GPL-3.0-or-later
# © 2026 The Why Not AI (thewhynot.ai)
"""3.0 tools track, Task 9: the guard against silently dropped Kalam engine tests.

The owner's Kalam engine suite (adobe/tools/kalam/_upstream/engine/tests/test_*.py, pytest style) is ported file by
file into whynot-cut/tests/test_kalam_*.py as unittest methods that keep the upstream function name. This test parses
(by AST) every `def test_*` of every upstream file and requires that each one is
  * a test method of the port file named in MAPPING, or
  * listed in NOT_PORTED with the reason, or
  * (its whole file) listed in PENDING with the task that ports it.
Tasks 10 and 11 move files from PENDING into MAPPING (and extend the package); Task 11 must leave PENDING empty.

The upstream side exists only in the repository (adobe/ is not in the plugin zip), so those checks skip with a reason
without adobe/tools; the checks of the maps themselves (the port files exist, the maps do not overlap) always run.
"""
import sys as _sys
_sys.dont_write_bytecode = True
import _isolation  # noqa: F401,E402  G79: sandbox the engine home first (tests/_isolation.py)
import ast
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
UPSTREAM_TESTS = HERE.parents[1] / "adobe" / "tools" / "kalam" / "_upstream" / "engine" / "tests"

# upstream test file -> the port test file (in whynot-cut/tests/) that carries its tests
MAPPING = {
    "test_rules.py": "test_kalam_engine_pure.py",
    "test_captions.py": "test_kalam_engine_pure.py",
    "test_clean.py": "test_kalam_engine_pure.py",
    "test_units.py": "test_kalam_engine_pure.py",
    "test_correct.py": "test_kalam_engine_correct.py",      # Task 10
    "test_platform.py": "test_kalam_engine_correct.py",
}

# upstream test file -> the task that ports it (not mapped yet). Task 11 must empty this.
PENDING = {
    "test_align.py": "Task 11",
    "test_doctor.py": "Task 11",
    "test_portable.py": "Task 11",
    "test_setup_models.py": "Task 11",
    "test_cli.py": "Task 11",
    "test_pipeline_slow.py": "Task 11",
}

# upstream test function name -> why it has no port (the verify_bundle tool checked a pre-built macOS bundle on a Mac)
_OBSOLETE = "obsolete: the runtime is built on the target OS (portability audit §3.1)"
NOT_PORTED = {
    "test_clean_bundle_has_no_problems": _OBSOLETE,
    "test_mac_binary_is_reported": _OBSOLETE,
    "test_mac_path_in_panel_is_reported": _OBSOLETE,
    "test_missing_cuda_dll_and_package_reported": _OBSOLETE,
    "test_single_file_module_counts_as_present": _OBSOLETE,
    "test_python_stdlib_text_is_not_scanned": _OBSOLETE,
    "test_soundfile_needs_its_windows_dll": _OBSOLETE,
    "test_dll_imports_are_read_from_objdump": _OBSOLETE,
    "test_missing_dlls_ignores_windows_and_driver_and_finds_the_rest": _OBSOLETE,
}
# upstream files whose every test is in NOT_PORTED (the file as a whole is not ported)
NOT_PORTED_FILES = ("test_verify_bundle.py",)


def test_names(path: Path) -> list:
    """every `def test_*` (module level or in a class) of a Python file, in source order, by AST"""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    return [n.name for n in ast.walk(tree)
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name.startswith("test_")]


def _is_testcase(c: ast.ClassDef) -> bool:
    """a class that derives from unittest.TestCase (`TestCase` or `unittest.TestCase`): only those run as tests"""
    return any((isinstance(b, ast.Name) and b.id == "TestCase") or (isinstance(b, ast.Attribute) and b.attr == "TestCase")
               for b in c.bases)


def port_methods(name: str) -> list:
    """the test methods of the unittest.TestCase classes of a port test file (a same-named method in any other
    class never runs, so it must not hide a dropped test)"""
    return _testcase_methods((HERE / name).read_text(encoding="utf-8"), name)


def _testcase_methods(source: str, filename: str) -> list:
    tree = ast.parse(source, filename=filename)
    return [f.name for c in ast.walk(tree) if isinstance(c, ast.ClassDef) and _is_testcase(c) for f in c.body
            if isinstance(f, ast.FunctionDef) and f.name.startswith("test_")]


class TestMapsThemselves(unittest.TestCase):
    """Run everywhere, including the plugin zip (no adobe/ there)."""

    def test_every_mapped_port_file_exists_and_has_tests(self):
        for up, port in MAPPING.items():
            self.assertTrue((HERE / port).is_file(), "%s -> %s: port file missing" % (up, port))
            self.assertTrue(port_methods(port), "%s has no test methods" % port)

    def test_a_file_is_mapped_pending_or_not_ported_never_two_at_once(self):
        mapped, pending, dropped = set(MAPPING), set(PENDING), set(NOT_PORTED_FILES)
        self.assertEqual(mapped & pending, set())
        self.assertEqual(mapped & dropped, set())
        self.assertEqual(pending & dropped, set())

    def test_pending_names_a_task_for_every_file(self):
        for f, task in PENDING.items():
            self.assertTrue(f.startswith("test_") and f.endswith(".py"), f)
            self.assertEqual(task, "Task 11", f)

    def test_not_ported_gives_a_reason_for_every_name(self):
        for name, reason in NOT_PORTED.items():
            self.assertTrue(name.startswith("test_"), name)
            self.assertTrue(reason.startswith("obsolete:") or len(reason) > 20, (name, reason))

    def test_only_methods_of_testcase_classes_count(self):
        src = "\n".join([
            "import unittest",
            "class Helper:", "    def test_hidden(self): pass",
            "class A(unittest.TestCase):", "    def test_a(self): pass", "    def helper(self): pass",
            "class B(TestCase):", "    def test_b(self): pass",
            "def test_module_level(): pass"])
        self.assertEqual(sorted(_testcase_methods(src, "x.py")), ["test_a", "test_b"])

    def test_port_method_names_are_unique_per_port_file(self):
        for port in sorted(set(MAPPING.values())):
            names = port_methods(port)
            dup = sorted({n for n in names if names.count(n) > 1})
            self.assertEqual(dup, [], "%s: a duplicate method name hides a test" % port)


@unittest.skipUnless(UPSTREAM_TESTS.is_dir(), "adobe/tools is not part of the plugin zip")
class TestUpstreamIsAccountedFor(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.files = sorted(p.name for p in UPSTREAM_TESTS.glob("test_*.py"))
        cls.names = {f: test_names(UPSTREAM_TESTS / f) for f in cls.files}

    def test_every_upstream_test_file_is_in_exactly_one_list(self):
        known = set(MAPPING) | set(PENDING) | set(NOT_PORTED_FILES)
        self.assertEqual([f for f in self.files if f not in known], [], "an upstream test file nobody owns")
        self.assertEqual(sorted(known - set(self.files)), [], "a listed file that does not exist upstream")

    def test_every_upstream_test_has_a_same_named_method_in_its_port_file(self):
        for up, port in MAPPING.items():
            have = set(port_methods(port))
            missing = [n for n in self.names[up] if n not in have and n not in NOT_PORTED]
            self.assertEqual(missing, [], "%s: tests dropped in %s" % (up, port))

    def test_the_port_has_no_fewer_tests_than_upstream_per_file(self):
        for port in sorted(set(MAPPING.values())):
            ups = [n for up, p in MAPPING.items() if p == port for n in self.names[up]]
            self.assertEqual(len(ups), len(set(ups)), "upstream names collide inside one port file: %s" % port)
            self.assertTrue(set(ups) <= set(port_methods(port)))

    def test_not_ported_names_exist_upstream_and_are_not_ported_too(self):
        every = {n for f in self.files for n in self.names[f]}
        ported = {m for port in set(MAPPING.values()) for m in port_methods(port)}
        for name in NOT_PORTED:
            self.assertIn(name, every, "stale NOT_PORTED entry: %s" % name)
            self.assertNotIn(name, ported, "%s is both ported and listed NOT_PORTED" % name)

    def test_not_ported_files_have_every_test_listed(self):
        for f in NOT_PORTED_FILES:
            self.assertTrue(self.names[f], f)
            self.assertEqual([n for n in self.names[f] if n not in NOT_PORTED], [],
                             "%s: a test with no reason" % f)

    def test_pending_files_are_not_mapped_yet(self):
        """PENDING is a subset of the files not yet mapped: porting a file means moving it to MAPPING"""
        self.assertEqual(sorted(set(PENDING) & set(MAPPING)), [])
        for f in PENDING:
            self.assertIn(f, self.files)
            self.assertTrue(self.names[f], f)


if __name__ == "__main__":
    unittest.main()
