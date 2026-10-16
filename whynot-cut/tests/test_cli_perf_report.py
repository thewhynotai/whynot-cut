"""3.0 G2 H3 (Adobe track, serve/perf_report.py) — `reel perf-report` is a `reel` command.

* cli.py registers `perf-report` (machine level: no client folder, no writer lock) and passes `--since` and the hidden
  `--home` through to serve.perf_report.main(argv) unchanged; its exit code is reel's exit code (0 every budget met or
  no data, 1 a miss, 2 a usage error, 3 an internal error).
* Other commands never import serve.perf_report.
Nothing here starts a daemon: the report reads <home>/logs/perf.jsonl of a temp engine home.
Run:  bash tools/test.sh -p test_cli_perf_report.py
"""
import sys as _sys
_sys.dont_write_bytecode = True  # keep the plugin folder free of __pycache__
import _isolation  # noqa: F401,E402  G79: sandbox the engine home first (tests/_isolation.py)
import contextlib
import io
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys = _sys
SK = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SK / "engine" / "reel"))

import cli  # noqa: E402


def run_main(argv):
    """cli.main in-process -> (exit code, stdout, stderr)."""
    o, e = io.StringIO(), io.StringIO()
    code = 0
    with contextlib.redirect_stdout(o), contextlib.redirect_stderr(e):
        try:
            cli.main(list(argv))
        except SystemExit as x:
            code = x.code if isinstance(x.code, int) else (0 if x.code is None else 1)
    return code, o.getvalue(), e.getvalue()


class TestPerfReportIsACommand(unittest.TestCase):
    def test_in_the_table_and_classified_as_a_machine_level_read(self):
        self.assertIn("perf-report", cli.command_table())
        self.assertIn("perf-report", cli.registered_commands())
        self.assertIn("perf-report", cli.NO_ROOT)
        self.assertIn("perf-report", cli.NO_ID)
        self.assertIn("perf-report", cli.CORE_READS)
        self.assertNotIn("perf-report", cli.CORE_WRITES)
        self.assertNotIn("perf-report", cli.WRITES_IF)
        self.assertTrue(callable(getattr(cli, "cmd_perf_report", None)))

    def test_reel_help_lists_it(self):
        code, out, _ = run_main(["--help"])
        self.assertEqual(code, 0)
        self.assertRegex(out, r"(?m)^\s+perf-report\s")

    def test_its_help_names_since_and_hides_home(self):
        code, out, _ = run_main(["perf-report", "--help"])
        self.assertEqual(code, 0)
        self.assertIn("--since", out)
        self.assertNotIn("--home", out)

    def test_args_are_passed_through_and_the_exit_code_is_reels(self):
        from serve import perf_report
        for rc in (0, 1, 2, 3):
            with mock.patch.object(perf_report, "main", return_value=rc) as m:
                code, _, _ = run_main(["perf-report", "--since", "2026-10-16T09:00:00Z", "--home", "H"])
            self.assertEqual(code, rc)
            argv = list(m.call_args.args[0])
            self.assertEqual(argv, ["--since", "2026-10-16T09:00:00Z", "--home", "H"])
        with mock.patch.object(perf_report, "main", return_value=0) as m:
            run_main(["perf-report"])
        self.assertEqual(list(m.call_args.args[0]), [])

    def test_an_internal_error_is_3_never_a_budget_miss(self):
        """Review b2e820b P2: an exception escaped to reel's fail() and exited 1, which means "budget missed"."""
        from serve import perf_report
        for boom in (RuntimeError("boom"), OSError("no engine home")):
            with mock.patch.object(perf_report, "main", side_effect=boom):
                code, out, err = run_main(["perf-report"])
            self.assertEqual(code, 3, out + err)
            self.assertIn(str(boom), out + err)

    def test_a_real_run_on_an_empty_home_is_0_and_a_bad_since_is_2(self):
        with tempfile.TemporaryDirectory() as td:
            code, out, _ = run_main(["perf-report", "--home", td])
            self.assertEqual(code, 0, out)
            code, out, _ = run_main(["perf-report", "--home", td, "--since", "yesterday-ish"])
            self.assertEqual(code, 2, out)
            self.assertIn("--since", out)

    def test_needs_no_client_folder_and_takes_no_lock(self):
        import argparse
        self.assertFalse(cli.writes(argparse.Namespace(cmd="perf-report")))
        with tempfile.TemporaryDirectory() as td, tempfile.TemporaryDirectory() as cwd, \
                mock.patch.object(cli.Path, "cwd", return_value=Path(cwd)):
            code, out, _ = run_main(["perf-report", "--home", td])      # an empty folder: no assets/, no data/
        self.assertEqual(code, 0, out)

    def test_other_commands_do_not_import_perf_report(self):
        """Commands run for real (in this run's sandbox engine home), not stopped at parse_args (review b2e820b)."""
        code = ("import sys; sys.path.insert(0, %r); import cli\n"
                "for argv in (['settings'], ['lock', '--status', '--root', %r], ['--help']):\n"
                "    try: cli.main(argv)\n"
                "    except SystemExit: pass\n"
                "print('serve.perf_report' in sys.modules)\n") % (str(SK / "engine" / "reel"), tempfile.gettempdir())
        r = subprocess.run([sys.executable, "-B", "-c", code], capture_output=True, text=True, encoding="utf-8",
                           timeout=120)
        self.assertEqual(r.stdout.strip().splitlines()[-1:], ["False"], r.stderr)


if __name__ == "__main__":
    unittest.main()
