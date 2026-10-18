"""After Effects `-r` and script paths (found live 2026-10-17, docs/adobe/photoshop-route.md section 4).

With After Effects running, `AfterFX.exe -r <jsx>` silently did nothing when the .jsx path had a space (the launcher
exited 0); the same file from a path without spaces ran in 1-2 s. ae-build, mogrt-build and `motion-build --run-script`
write their scripts into the client folder, which often has spaces (or Arabic letters, or symbols). adobe_run now hands
AE a copy with a hex name, in this order: <engine home>/tmp/ae-run; %ProgramData%/WhyNotCut/tmp/ae-run (only when no
part of it is a link or owned by another account); the 8.3 short form of the engine-home copy; else it refuses (never
runs silently). The copy is never removed under a running After Effects: it carries a deadline (its mtime) - 60 s
after a confirmed run, the build lock's own deadline otherwise - and a later run sweeps it.
Not verified live (risk R-L3): that the `~` of an 8.3 short path survives -r's re-parsing, like the non-ASCII
assumption. That doubt is the only reason the shared %ProgramData% folder is tried before the user's own 8.3 path.
Nothing here launches After Effects or calls the real kernel: Popen of the AE exe, the app lookup, the folder-owner
check and ctypes.windll.kernel32.GetShortPathNameW are stubbed in every test (the real owner check has its own
read-only smoke test, tests/test_ae_render_trust.py). Cases that need a safe engine home (a test folder whose path -r
accepts) skip, by name, on a PC whose temp folder has a space or non-ASCII letters; the others run everywhere.
Run:  bash tools/test.sh -p test_adobe_run_paths.py
"""
import sys as _sys
_sys.dont_write_bytecode = True  # keep the plugin folder free of __pycache__
import _isolation  # noqa: F401,E402  G79: sandbox the engine home first (tests/_isolation.py)
import ctypes
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import types
import unittest
from pathlib import Path
from unittest import mock

SK = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SK / "engine" / "reel"))

from lib import adobe_run, ae_render, common, plat  # noqa: E402
from lib.common import Paths, write_json  # noqa: E402
from lib.errors import exit_code  # noqa: E402

FAKE_AE = {"name": "AE", "exe": "AfterFX.exe"}
_REAL_POPEN = subprocess.Popen
JSX = "// AUTO-GENERATED test script\nvar x = 'عميل';\n"
R_SAFE = re.compile(r"[A-Za-z0-9._\-\\/:~]+")             # what `-r` may receive (the test's own copy of the rule)
COPY_NAME = re.compile(r"[0-9a-f]{16}-\d+-[0-9a-f]{12}\.jsx")
GRACE = 300                                               # run_after_effects' build lock: hold_s = timeout + 300
CONFIRMED_KEEP = 60                                       # a confirmed run's copy: kept 60 s more, never deleted
TZ = r"[+-]\d\d:\d\d$"


def r_safe(s: str) -> bool:
    return bool(R_SAFE.fullmatch(s)) and not s.startswith(("\\\\", "//"))


class FakeKernel32:
    """ctypes.windll.kernel32 with GetShortPathNameW faked: `table` maps a long path to its 8.3 form; a path not in
    it comes back unchanged (8.3 names off on the volume); `fail` returns 0 (the call failed). `seen` records, per
    call, whether the long path existed at that moment."""

    def __init__(self, fail=True):
        self.table, self.fail, self.calls, self.seen = {}, fail, [], []
        self.rewrite = None                                   # callable(long) -> short, instead of the table

    def GetShortPathNameW(self, path, buf, n):  # noqa: N802
        self.calls.append(path)
        self.seen.append(Path(path).is_file())
        if self.fail:
            return 0
        short = self.rewrite(path) if self.rewrite else self.table.get(path, path)
        buf.value = short
        return len(short)


class Base(unittest.TestCase):
    NEEDS_SAFE_HOME = True          # every case of the class needs a test folder whose path -r accepts

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="aerun_"))          # inside the test sandbox (tests/_isolation.py)
        self.addCleanup(shutil.rmtree, self.tmp, True)
        if self.NEEDS_SAFE_HOME:
            self.need_safe()
        self.launched = []      # (argv, the -r file's text at launch or None, the copies in the engine home at launch)
        self.popen_error = None
        self.on_launch = None

        def popen(argv, *a, **kw):      # catch ONLY the After Effects launch (the build lock may run real tools)
            if isinstance(argv, (list, tuple)) and argv and os.path.basename(str(argv[0])) == FAKE_AE["exe"]:
                if self.popen_error:
                    raise self.popen_error
                p = Path(argv[2])
                self.launched.append((list(argv), p.read_text(encoding="utf-8") if p.is_file() else None,
                                      self.copies()))
                if self.on_launch:
                    self.on_launch()
                return None
            return _REAL_POPEN(argv, *a, **kw)

        self.k = FakeKernel32()                                   # no test ever reaches the real kernel call
        self.owner_ok = lambda p: True                            # the folder-owner check (GetNamedSecurityInfoW)
        self.is_link = lambda p: False                            # the reparse-point check
        # never the machine's %ProgramData%: Windows keys are case-insensitive (os.environ holds PROGRAMDATA)
        env = {k: v for k, v in os.environ.items() if k.upper() not in ("PROGRAMDATA", "SYSTEMDRIVE")}
        env["SystemDrive"] = str(self.tmp / "sysdrive")           # never used: a root folder's ACL is not ours
        for p in (mock.patch.object(plat, "newest_app", lambda key: FAKE_AE),
                  mock.patch.object(plat, "sandbox_refusal", lambda what, *t: None),
                  mock.patch.object(plat, "IS_MAC", False),
                  mock.patch.object(adobe_run.subprocess, "Popen", popen),
                  mock.patch.object(adobe_run.time, "sleep", lambda s: None),
                  mock.patch.object(ctypes, "windll", types.SimpleNamespace(kernel32=self.k), create=True),
                  mock.patch.object(ae_render, "_owner_trusted", lambda p: self.owner_ok(p), create=True),
                  mock.patch.object(ae_render, "_is_reparse", lambda p: self.is_link(p), create=True),
                  mock.patch.dict(os.environ, env, clear=True)):
            p.start()
            self.addCleanup(p.stop)
        self.use_home(self.tmp / "enginehome")
        real_stage_dirs = adobe_run.stage_dirs

        def guarded_stage_dirs():
            dirs = real_stage_dirs()
            outside = [d for d, _shared in dirs if not str(os.path.abspath(d)).startswith(str(self.tmp))]
            if outside:
                raise AssertionError(f"a test would write outside its temp folder: {outside}")
            return dirs
        p = mock.patch.object(adobe_run, "stage_dirs", guarded_stage_dirs)
        p.start()
        self.addCleanup(p.stop)

    def need_safe(self):
        """Skip THIS case on a PC whose temp folder -r would not take (a space, non-ASCII letters)."""
        if not r_safe(os.path.abspath(self.tmp)):
            self.skipTest(f"needs a test folder whose path -r accepts; this PC's is {self.tmp}")

    def use_home(self, home: Path):
        os.environ["WHYNOT_HOME"] = str(home)
        self.run_dir = Path(os.path.abspath(home)) / "tmp" / "ae-run"

    def use_program_data(self, folder: Path) -> Path:
        os.environ["ProgramData"] = str(folder)
        return folder / "WhyNotCut" / "tmp" / "ae-run"

    def client_jsx(self, folder: str, name: str = "build_V1_graphics.jsx") -> Path:
        d = self.tmp / "clients" / folder / "04_after_effects" / "scripts"
        d.mkdir(parents=True, exist_ok=True)
        f = d / name
        f.write_text(JSX, encoding="utf-8")
        return f

    def copies(self, folder: Path | None = None) -> list:
        folder = folder or self.run_dir
        return sorted(folder.glob("*.jsx")) if folder.is_dir() else []

    def assert_staged_run(self, jsx: Path, res: dict, folder: Path | None = None, confirmed: bool = True):
        folder = folder or self.run_dir
        self.assertEqual(len(self.launched), 1, res)
        argv, text, _ = self.launched[0]
        self.assertEqual(argv[:2], [FAKE_AE["exe"], "-r"])
        self.assertTrue(r_safe(argv[2]), argv)                       # never an unsafe character in -r
        self.assertEqual(text, JSX)                                  # the copy existed, same bytes, at launch
        self.assertEqual(Path(argv[2]).parent, folder)               # never beside the client files
        self.assertRegex(Path(argv[2]).name, COPY_NAME)
        self.assertEqual(sorted(p.name for p in jsx.parent.iterdir()), [jsx.name])
        self.assertEqual(res.get("script_copy_used"), argv[2])
        self.assertRegex(res.get("script_copy_kept_until") or "", TZ)  # an ISO time with its zone offset
        if confirmed:
            [copy] = self.copies(folder)                              # never deleted under a running AE: a late -r
            self.assertEqual(str(copy), argv[2])                      # of the same file finds it
            self.assertAlmostEqual(copy.stat().st_mtime, time.time() + CONFIRMED_KEEP, delta=5)


class TestRules(Base):
    """Rules that hold on any PC (no safe test folder needed)."""
    NEEDS_SAFE_HOME = False

    def test_the_machine_folders_are_out_of_reach(self):
        self.assertIsNone(os.environ.get("ProgramData"))
        self.assertEqual(adobe_run.stage_dirs(), [(self.run_dir, False)])

    def test_under_the_test_sandbox_program_data_outside_it_is_never_used(self):
        """G79: an unsafe engine home in some other test (a temp folder with a space on that machine) must not
        reach the machine's %ProgramData%. Only computed here: nothing is written."""
        self.assertTrue(os.environ.get(plat.SANDBOX_ENV))
        os.environ["ProgramData"] = os.path.dirname(os.path.abspath(os.environ[plat.SANDBOX_ENV]))
        self.assertEqual(adobe_run.stage_dirs(), [(self.run_dir, False)])
        inside = self.use_program_data(self.tmp / "pd")
        self.assertEqual(adobe_run.stage_dirs(), [(self.run_dir, False), (inside, True)])

    def test_r_safe_is_an_allowlist(self):
        ok = [r"D:\Clients\DrNahla\build.jsx", "C:/x/y.jsx", r"C:\Users\D3C0~1\.whynot-cut\tmp\a-b_c.jsx"]
        bad = [r"D:\Dr Nahla\b.jsx", r"D:\عميل\b.jsx", r"\\?\D:\Clients\b.jsx", r"\\server\share\b.jsx",
               "//server/share/b.jsx", r"\\.\D:\b.jsx", "D:\\a\tb.jsx", ""] + [f"D:\\a{c}b\\x.jsx" for c in "'&(),;%![]"]
        for s in ok:
            self.assertTrue(adobe_run.r_safe(s), s)
        for s in bad:
            self.assertFalse(adobe_run.r_safe(s), s)

    def test_every_staging_folder_is_absolute(self):
        """A saved engine-home option is not made absolute by plat.engine_home(), and %ProgramData% is the
        environment's: either could be relative, and AE would resolve the -r path in its own folder."""
        cwd = os.getcwd()
        os.chdir(self.tmp)
        self.addCleanup(os.chdir, cwd)
        os.environ["ProgramData"] = "pd-rel"
        with mock.patch.object(plat, "engine_home", lambda: Path("home-rel")):
            dirs = adobe_run.stage_dirs()
        self.assertEqual(dirs, [(self.tmp / "home-rel" / "tmp" / "ae-run", False),
                                (self.tmp / "pd-rel" / "WhyNotCut" / "tmp" / "ae-run", True)])

    def test_the_8_3_and_program_data_doubt_is_written_down(self):
        """R-L3: the 8.3 route is not verified live; the module says so, and why %ProgramData% comes first."""
        doc = Path(adobe_run.__file__).read_text(encoding="utf-8")
        self.assertIn("not verified live", doc.lower())
        self.assertIn("R-L3", doc)
        self.assertIn("%ProgramData% folder is tried before the user's own 8.3", doc)


class TestUnsafeScriptPaths(Base):
    def test_a_path_with_a_space_is_run_from_an_engine_home_copy(self):
        jsx = self.client_jsx("Dr Nahla Clinic")
        res = adobe_run.run_after_effects(jsx, 5, done=lambda: True)
        self.assert_staged_run(jsx, res)
        self.assertNotIn("status", res)                              # a normal run result, not a refusal

    def test_an_arabic_path_is_run_from_an_engine_home_copy(self):
        """Assumed broken like the space (unverified live): AE's command-line tools read the ANSI code page (aerender
        turns Arabic into '???', lib/ae_render.stage_ascii), so non-ASCII never goes to -r."""
        jsx = self.client_jsx("عميل")
        self.assert_staged_run(jsx, adobe_run.run_after_effects(jsx, 5, done=lambda: True))

    def test_the_copy_name_is_hex_whatever_the_script_is_called(self):
        jsx = self.client_jsx("Clients", "بناء الرسوم.jsx")
        self.assert_staged_run(jsx, adobe_run.run_after_effects(jsx, 5, done=lambda: True))

    def test_symbols_in_the_path_are_copied_too(self):
        """An allowlist, not a blocklist: what else -r's re-parsing breaks on is unknown, so any character outside
        letters, digits and . _ - \\ / : ~ sends the script through a copy."""
        for ch in "'&(),;%![]":
            with self.subTest(ch=ch):
                self.launched.clear()
                shutil.rmtree(self.run_dir, ignore_errors=True)     # the previous case's kept copy
                jsx = self.client_jsx(f"Client{ch}A")
                self.assert_staged_run(jsx, adobe_run.run_after_effects(jsx, 5, done=lambda: True))

    def test_a_safe_path_goes_as_it_is(self):
        jsx = self.client_jsx("DrNahla")
        res = adobe_run.run_after_effects(jsx, 5, done=lambda: True)
        self.assertEqual([x[:2] for x in self.launched], [([FAKE_AE["exe"], "-r", str(jsx)], JSX)], res)
        self.assertEqual(self.copies(), [])
        self.assertNotIn("script_copy_used", res)

    def test_a_relative_path_is_made_absolute_first(self):
        """AE runs the script in ITS working folder, not ours: a relative path would point elsewhere."""
        jsx = self.client_jsx("DrNahla")
        cwd = os.getcwd()
        os.chdir(jsx.parent)
        self.addCleanup(os.chdir, cwd)
        adobe_run.run_after_effects(Path(jsx.name), 5, done=lambda: True)
        self.assertEqual(self.launched[0][0][2], os.path.abspath(jsx.name))
        self.assertTrue(Path(self.launched[0][0][2]).is_absolute())

    def test_the_trust_check_keys_on_shared_not_on_position(self):
        """A shared folder is checked wherever it sits in the list (a reorder must never skip the check)."""
        pd = self.use_program_data(self.tmp / "ProgramData")
        pd.mkdir(parents=True)
        self.owner_ok = lambda p: os.path.abspath(p) != str(pd.parent.parent)      # WhyNotCut: someone else's
        jsx = self.client_jsx("Client A")
        with mock.patch.object(adobe_run, "stage_dirs", lambda: [(pd, True), (self.run_dir, False)]):
            res = adobe_run.run_after_effects(jsx, 5, done=lambda: True)
        self.assertEqual(Path(self.launched[0][0][2]).parent, self.run_dir, res)
        self.assertEqual(self.copies(pd), [])


class TestCleanup(Base):
    def test_kept_60_s_after_success_and_present_while_done_is_polled(self):
        """Confirmed is not deleted: an earlier kept copy's late run can satisfy done() before AE has read THIS copy,
        so the file stays 60 s more (its mtime) and a later run sweeps it."""
        jsx = self.client_jsx("Client A")
        seen = []
        res = adobe_run.run_after_effects(jsx, 5, done=lambda: seen.append(len(self.copies())) or len(seen) >= 3)
        self.assertEqual(seen, [1, 1, 1], "the copy stays while After Effects may still be reading it")
        self.assert_staged_run(jsx, res)

    def assert_kept_until_the_lock_deadline(self, res: dict, t0: float, timeout: int):
        [copy] = self.copies()
        deadline = copy.stat().st_mtime
        self.assertAlmostEqual(deadline, t0 + timeout + GRACE, delta=5)
        self.assertIn("script_copy_kept_until", res)
        return copy

    def test_a_timeout_keeps_the_copy_until_the_lock_deadline(self):
        """After Effects may still be starting or behind a dialog: removing the file then would make that late run
        fail (or alert). The copy lives exactly as long as the build lock that guards it (hold_s = timeout + 300)."""
        jsx = self.client_jsx("Client A")
        t0, polls = time.time(), [0]
        ticks = iter(t0 + 0.5 * i for i in range(10_000))            # a counter clock: 0.5 s per reading

        def not_yet():
            polls[0] += 1
            return False
        # adobe_run's own clock only: the build lock (cep_queue) keeps reading the real time.time
        with mock.patch.object(adobe_run, "_now", lambda: next(ticks)):
            res = adobe_run.run_after_effects(jsx, 10, done=not_yet)
        self.assertGreater(polls[0], 3)
        self.assertLess(polls[0], 30)                                # a timeout, not a spin
        self.assertEqual(res["elapsed_s"], round(next(ticks) - t0 - 0.5, 1))   # every reading was adobe_run's
        self.assert_staged_run(jsx, res, confirmed=False)
        copy = self.assert_kept_until_the_lock_deadline(res, t0, 10)
        self.assertEqual(str(copy), res["script_copy_used"])

    def test_a_failed_done_check_keeps_the_copy_until_the_lock_deadline(self):
        jsx = self.client_jsx("Client A")

        def boom():
            raise RuntimeError("done() broke")
        t0 = time.time()
        with self.assertRaises(RuntimeError):
            adobe_run.run_after_effects(jsx, 7, done=boom)
        self.assertEqual(len(self.launched), 1)
        [copy] = self.copies()
        self.assertAlmostEqual(copy.stat().st_mtime, t0 + 7 + GRACE, delta=5)

    def test_without_a_done_check_the_copy_stays_until_the_lock_deadline(self):
        jsx = self.client_jsx("Client A")
        t0 = time.time()
        res = adobe_run.run_after_effects(jsx, 9)
        self.assert_kept_until_the_lock_deadline(res, t0, 9)

    def test_removed_at_once_when_the_launch_fails(self):
        jsx = self.client_jsx("Client A")
        self.popen_error = OSError("AfterFX.exe vanished")
        with self.assertRaises(OSError):
            adobe_run.run_after_effects(jsx, 5, done=lambda: True)
        self.assertEqual(self.copies(), [])

    def test_the_sweep_removes_only_expired_copies(self):
        self.run_dir.mkdir(parents=True)
        now = time.time()
        names = {"expired": ("0123456789abcdef-11-0123456789ab.jsx", now - 120),
                 "deadline_ahead": ("0123456789abcdef-12-0123456789ab.jsx", now + 3600),   # another run's, live
                 "just_written": ("0123456789abcdef-13-0123456789ab.jsx", now - 5),        # before its utime
                 "not_ours": ("notes.jsx", now - 999_999)}
        for name, t in names.values():
            f = self.run_dir / name
            f.write_text("x", encoding="utf-8")
            os.utime(f, (t, t))
        res = adobe_run.run_after_effects(self.client_jsx("Client A"), 5, done=lambda: True)
        left = sorted(p.name for p in self.run_dir.iterdir() if str(p) != res["script_copy_used"])
        self.assertEqual(left, sorted(n for k, (n, _) in names.items() if k != "expired"))

    def test_a_missing_script_is_a_stage_failure_and_launches_nothing(self):
        jsx = self.tmp / "clients" / "Client A" / "missing.jsx"
        res = adobe_run.run_after_effects(jsx, 5, done=lambda: True)
        self.assertEqual((res.get("status"), res.get("ok")), ("SCRIPT_STAGE_FAILED", False), res)
        self.assertEqual(res["msg"].count("missing.jsx"), 1, res["msg"])  # the path once, then the OS reason
        self.assertIn("could not be read", res["msg"])
        # the script itself is unreadable: running it by hand cannot help, and the copy folder is not the problem
        self.assertEqual(res["how"], "run the command again so the script is made again")
        self.assertEqual(exit_code(res), 1)
        self.assertEqual((self.launched, self.copies()), ([], []))

    def test_a_copy_folder_that_cannot_be_written_names_it_in_the_how(self):
        jsx = self.client_jsx("Client A")
        self.run_dir.parent.mkdir(parents=True)
        self.run_dir.write_text("a file where the copy folder must go", encoding="utf-8")
        res = adobe_run.run_after_effects(jsx, 5, done=lambda: True)
        self.assertEqual(res.get("status"), "SCRIPT_STAGE_FAILED", res)
        self.assertIn(f"free space or fix the permissions on {self.run_dir}", res["how"])
        self.assertEqual(self.launched, [])

    def test_a_failed_write_leaves_no_partial_copy(self):
        """Disk full in the middle of the copy: the half-written file (no deadline yet) is removed, not left for 60 s."""
        jsx = self.client_jsx("Client A")
        real_open = open

        class Half:
            def __init__(self, fh):
                self.fh = fh

            def __enter__(self):
                return self

            def __exit__(self, *exc):
                self.fh.close()

            def write(self, data):
                self.fh.write(data[:5])
                raise OSError(28, "No space left on device")

        def fake_open(path, mode="r", *a, **kw):
            fh = real_open(path, mode, *a, **kw)
            return Half(fh) if mode == "xb" else fh
        with mock.patch.object(adobe_run, "open", fake_open, create=True):
            res = adobe_run.run_after_effects(jsx, 5, done=lambda: True)
        self.assertEqual(res.get("status"), "SCRIPT_STAGE_FAILED", res)
        self.assertIn("No space left", res["msg"])
        self.assertEqual((self.launched, list(self.run_dir.iterdir())), ([], []))

    def test_macos_passes_the_path_as_it_is(self):
        jsx = self.client_jsx("Client A")
        done = subprocess.CompletedProcess([], 0, "", "")
        with mock.patch.object(plat, "IS_MAC", True), mock.patch.object(adobe_run, "run", return_value=done) as run:
            adobe_run.run_after_effects(jsx, 5, done=lambda: True)
        self.assertEqual(run.call_args[0][0][-1], str(jsx))
        self.assertEqual((self.launched, self.copies()), ([], []))


class TestParallel(Base):
    def test_two_parallel_stagings_of_the_same_script_never_collide(self):
        jsx = self.client_jsx("Client A")
        gate, out, errors = threading.Barrier(2), [], []

        def stage():
            try:
                gate.wait(5)
                out.append(adobe_run.stage_script(jsx, time.time() + 60))
            except Exception as e:  # noqa: BLE001
                errors.append(e)
        ts = [threading.Thread(target=stage) for _ in range(2)]
        for t in ts:
            t.start()
        for t in ts:
            t.join(10)
        self.assertEqual(errors, [])
        copies = [c for c, _arg in out]
        self.assertEqual(len(set(copies)), 2, copies)                # same content, two different files
        self.assertTrue(all(c.read_text(encoding="utf-8") == JSX for c in copies))

    def test_same_content_and_pid_still_differ(self):
        jsx = self.client_jsx("Client A")
        a, b = adobe_run.stage_script(jsx, time.time() + 60), adobe_run.stage_script(jsx, time.time() + 60)
        self.assertNotEqual(a[0], b[0])
        self.assertEqual(a[0].name.split("-")[0], b[0].name.split("-")[0])   # the content hash part matches
        self.assertIn(f"-{os.getpid()}-", a[0].name)

    def test_an_existing_name_is_never_overwritten(self):
        jsx = self.client_jsx("Client A")
        self.run_dir.mkdir(parents=True)
        taken = self.run_dir / "taken.jsx"
        taken.write_text("another run", encoding="utf-8")
        names = iter(["taken.jsx", "free.jsx"])
        with mock.patch.object(adobe_run, "_copy_name", lambda data: next(names)):
            copy, arg = adobe_run.stage_script(jsx, time.time() + 60)
        self.assertEqual((copy.name, taken.read_text(encoding="utf-8")), ("free.jsx", "another run"))


class TestEngineHomeNotSafe(Base):
    """The fallback chain when <engine home>/tmp/ae-run is not safe: %ProgramData%/WhyNotCut/tmp/ae-run, then the 8.3
    short form of the engine-home copy, then a refusal. Never a root folder of the system drive."""
    NEEDS_SAFE_HOME = False         # the refusal cases run anywhere; the others ask need_safe()

    def setUp(self):
        super().setUp()
        self.use_home(self.tmp / "engine home")

    def shorten(self, *pairs):
        """8.3 on: each (long folder name, short name) pair is replaced in the long path."""
        def rewrite(long):
            for a, b in pairs:
                long = long.replace(a, b)
            return long
        self.k.fail, self.k.rewrite = False, rewrite

    def test_program_data_comes_before_the_short_path(self):
        self.need_safe()
        pd = self.use_program_data(self.tmp / "ProgramData")
        jsx = self.client_jsx("Client A")
        self.shorten(("engine home", "ENGINE~1"))
        res = adobe_run.run_after_effects(jsx, 5, done=lambda: True)
        self.assert_staged_run(jsx, res, folder=pd)
        self.assertEqual(self.k.calls, [])

    def test_an_unusable_program_data_falls_through_to_the_short_path(self):
        self.need_safe()
        for name, prep in (("Program Data", None), ("pd-blocked", "file")):
            with self.subTest(program_data=name):
                self.launched.clear()
                self.k.calls.clear()
                self.k.seen.clear()
                shutil.rmtree(self.run_dir, ignore_errors=True)     # the previous case's kept copy
                folder = self.tmp / name
                pd = self.use_program_data(folder)
                if prep == "file":                                   # a file where the folder must go: cannot mkdir
                    folder.mkdir()
                    (folder / "WhyNotCut").write_text("x", encoding="utf-8")
                jsx = self.client_jsx("Client A")
                self.shorten(("engine home", "ENGINE~1"))
                res = adobe_run.run_after_effects(jsx, 5, done=lambda: True)
                self.assertEqual(len(self.launched), 1, res)
                argv, _text, at_launch = self.launched[0]
                self.assertTrue(r_safe(argv[2]), argv)
                self.assertIn("ENGINE~1", argv[2])
                self.assertEqual(len(at_launch), 1, "the long-name copy existed when After Effects was launched")
                self.assertEqual(Path(argv[2].replace("ENGINE~1", "engine home")), at_launch[0])
                self.assertEqual(self.k.seen, [True], "GetShortPathNameW got an existing file")
                self.assertEqual(self.copies(), at_launch, "the copy keeps its long name, with its deadline")
                self.assertEqual(self.copies(pd), [])

    def program_data_with(self, *parts) -> Path:
        """%ProgramData% in the test folder, with WhyNotCut/tmp/ae-run already there (made by 'someone')."""
        base = self.tmp / "ProgramData"
        (base / "WhyNotCut" / "tmp" / "ae-run").mkdir(parents=True)
        return self.use_program_data(base)

    def test_program_data_owned_by_another_account_is_skipped(self):
        """Another local user may create C:\\ProgramData\\WhyNotCut\\tmp\\ae-run first; as its owner they could swap
        the copy before After Effects runs it as YOU. Each of the three folders must be ours, SYSTEM's or the
        Administrators' (GetNamedSecurityInfoW owner), else the folder is not used."""
        self.need_safe()
        for part in ("WhyNotCut", "tmp", "ae-run"):
            with self.subTest(owned_by_someone_else=part):
                self.launched.clear()
                shutil.rmtree(self.tmp / "ProgramData", ignore_errors=True)
                pd = self.program_data_with()
                bad = {"WhyNotCut": pd.parent.parent, "tmp": pd.parent, "ae-run": pd}[part]
                self.owner_ok = lambda p, bad=bad: os.path.abspath(p) != str(bad)
                res = adobe_run.run_after_effects(self.client_jsx("Client A"), 5, done=lambda: True)
                self.assert_refused(res)                              # 8.3 is off here: nothing else is left
                self.assertIn(f"{bad} is owned by another account", res["msg"])
                self.assertEqual(self.copies(pd), [])

    def test_program_data_through_a_link_is_skipped(self):
        self.need_safe()
        for part in ("WhyNotCut", "tmp", "ae-run"):
            with self.subTest(link=part):
                self.launched.clear()
                shutil.rmtree(self.tmp / "ProgramData", ignore_errors=True)
                pd = self.program_data_with()
                bad = {"WhyNotCut": pd.parent.parent, "tmp": pd.parent, "ae-run": pd}[part]
                self.is_link = lambda p, bad=bad: os.path.abspath(p) == str(bad)
                self.shorten(("engine home", "ENGINE~1"))             # 8.3 on: the next route is used instead
                res = adobe_run.run_after_effects(self.client_jsx("Client A"), 5, done=lambda: True)
                self.assertIn("ENGINE~1", self.launched[0][0][2], res)
                self.assertEqual(self.copies(pd), [])
                shutil.rmtree(self.run_dir, ignore_errors=True)

    def test_a_trusted_program_data_folder_made_earlier_is_used(self):
        self.need_safe()
        pd = self.program_data_with()
        jsx = self.client_jsx("Client A")
        res = adobe_run.run_after_effects(jsx, 5, done=lambda: True)
        self.assert_staged_run(jsx, res, folder=pd)

    def test_the_refusal_lists_every_other_folder_tried_whatever_the_order(self):
        """'also tried' names each folder that is not the engine home's, with its reason, wherever it sat."""
        pd = self.tmp / "pd blocked" / "WhyNotCut" / "tmp" / "ae-run"            # unsafe: a space
        with mock.patch.object(adobe_run, "stage_dirs", lambda: [(pd, True), (self.run_dir, False)]):
            res = adobe_run.run_after_effects(self.client_jsx("Client A"), 5, done=lambda: True)
        self.assert_refused(res)
        tried = res["msg"].split("also tried: ", 1)[1]
        self.assertIn(f"{pd} is not a path -r takes", tried)
        self.assertNotIn(str(self.run_dir), tried)                             # the home has its own sentence

    def test_8_3_names_off_refuses_clearly(self):
        self.k.fail = False                                           # comes back unchanged: still has the space
        res = adobe_run.run_after_effects(self.client_jsx("Client A"), 5, done=lambda: True)
        self.assert_refused(res)
        self.assertIn("no 8.3 short name for it (short names are off on that drive, or the folder was made before "
                      "they were turned on)", res["msg"])

    def test_a_failed_short_path_call_refuses_clearly(self):
        self.assert_refused(adobe_run.run_after_effects(self.client_jsx("Client A"), 5, done=lambda: True))

    def test_a_partly_shortened_path_refuses_and_names_the_short_form(self):
        self.use_home(self.tmp / "engine home" / "sub dir")
        self.shorten(("engine home", "ENGINE~1"))                   # one folder has no 8.3 name: still a space
        res = adobe_run.run_after_effects(self.client_jsx("Client A"), 5, done=lambda: True)
        self.assert_refused(res)
        self.assertIn(str(self.tmp / "ENGINE~1" / "sub dir" / "tmp" / "ae-run"), res["msg"])

    def test_arabic_user_name_with_a_cp720_short_name_refuses(self):
        """An Arabic Windows user name: the profile folder's 8.3 name is made in the OEM code page (cp720), so it can
        keep Arabic letters - still not a path -r takes."""
        self.use_home(self.tmp / "Users" / "يونس عبده" / ".whynot-cut")
        self.shorten(("يونس عبده", "يونسع~1"))
        res = adobe_run.run_after_effects(self.client_jsx("Client A"), 5, done=lambda: True)
        self.assert_refused(res)
        self.assertIn("يونسع~1", res["msg"])

    def test_a_safe_jsx_path_never_needs_the_engine_home(self):
        self.need_safe()
        jsx = self.client_jsx("ClientA")
        res = adobe_run.run_after_effects(jsx, 5, done=lambda: True)
        self.assertEqual([x[:2] for x in self.launched], [([FAKE_AE["exe"], "-r", str(jsx)], JSX)], res)

    def assert_refused(self, res: dict):
        self.assertEqual(self.launched, [], "never run silently from a path -r ignores")
        self.assertEqual((res.get("status"), res.get("ok"), res.get("refused")), ("REFUSED", False, "ae-script-path"))
        self.assertEqual(exit_code(res), 2)
        self.assertIn("space", res["msg"])
        self.assertIn("WHYNOT_HOME", res["how"])
        self.assertIn("Run Script File", res["how"])
        self.assertNotIn("C:\\whynot", res["how"])                  # a C:\ root folder: Authenticated Users may write
        self.assertEqual(self.copies(), [], "a refused run leaves no copy behind")
        self.assertFalse((self.tmp / "sysdrive").exists(), "never a root folder of the system drive")


class TestAerenderRootsTrust(Base):
    """ae_render.ascii_stage_roots (aerender's ASCII stage) skips a root with a link or a foreign owner too."""

    ARABIC_TEMP = r"C:\Users\يونس\AppData\Local\Temp"
    NEEDS_SAFE_HOME = False

    def setUp(self):
        super().setUp()
        if not str(self.tmp).isascii():
            self.skipTest(f"aerender roots are ASCII only; this PC's test folder is {self.tmp}")

    def roots(self, env):
        return ae_render.ascii_stage_roots(temp=self.ARABIC_TEMP, home=self.tmp / "eng", environ=env,
                                           short_path=lambda p: None)

    def test_a_foreign_or_linked_program_data_root_is_skipped(self):
        pd = self.tmp / "PD"
        (pd / "WhyNotCut" / "tmp").mkdir(parents=True)
        env = {"ProgramData": str(pd), "SystemDrive": str(self.tmp / "sys")}
        self.assertIn(pd / "WhyNotCut" / "tmp", self.roots(env))
        for check in ("owner", "link"):
            with self.subTest(check=check):
                bad = str(pd / "WhyNotCut")
                if check == "owner":
                    self.owner_ok, self.is_link = (lambda p: os.path.abspath(p) != bad), (lambda p: False)
                else:
                    self.owner_ok, self.is_link = (lambda p: True), (lambda p: os.path.abspath(p) == bad)
                roots = self.roots(env)
                self.assertNotIn(pd / "WhyNotCut" / "tmp", roots)
                self.assertIn(self.tmp / "eng" / "tmp", roots)        # the others stay

    def test_roots_not_made_yet_are_kept(self):
        """A folder that does not exist yet is made by this account on use (stage_ascii), so nothing to check."""
        env = {"ProgramData": str(self.tmp / "nothing-here"), "SystemDrive": str(self.tmp / "sys")}
        self.owner_ok = lambda p: False
        self.assertIn(self.tmp / "nothing-here" / "WhyNotCut" / "tmp", self.roots(env))


def _load_cli():
    import importlib.util
    spec = importlib.util.spec_from_file_location("reel_cli_aerun", SK / "engine/reel/cli.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def cli_doc(fn, args) -> dict:
    """A cmd_* function in this process: the JSON document it printed (it may exit with a code)."""
    import contextlib
    import io
    so = io.StringIO()
    with contextlib.redirect_stdout(so), contextlib.redirect_stderr(io.StringIO()):
        try:
            fn(args)
        except SystemExit:
            pass
    return json.loads(so.getvalue())


def client(tmp: Path, name: str) -> Paths:
    root = tmp / name
    for d in ("assets", "data"):
        (root / d).mkdir(parents=True, exist_ok=True)
    write_json(root / common.CLIENT_PROFILE_REL / "sequence-settings.json", {"general": {"timebase": 25, "ntsc": False}})
    p = Paths(root, "V1")
    p.ensure_project()
    write_json(p.p("01_analysis/timeline-spec.json"),
               {"fps": 25.0, "duration_frames": 100, "events": [], "main_segments": []})
    return p


class TestCallers(Base):
    """A copy that could not be made keeps its own status and reason up to the command (no 'AE may be showing why')."""

    def stage_fails(self):
        return mock.patch.object(adobe_run, "stage_script", side_effect=OSError("disk full"))

    def assert_kept(self, res: dict):
        self.assertEqual((res["status"], res["ok"]), ("SCRIPT_STAGE_FAILED", False), res)
        self.assertIn("disk full", res["msg"])
        self.assertIn("Run Script File", res["how"])
        self.assertNotIn("showing why", json.dumps(res, ensure_ascii=False))
        self.assertEqual(exit_code(res), 1)
        self.assertEqual(self.launched, [])

    def test_ae_build_keeps_the_stage_failure(self):
        from lib import ae_builder
        p = client(self.tmp, "Client A")
        with common.use_context(common.Context(p.root)):
            jsx = Path(ae_builder.generate(p)["jsx"])
            with self.stage_fails():
                res = ae_builder.execute(p, jsx)
        self.assert_kept(res)
        self.assertFalse(p.p("04_after_effects/ae-build-result.json").exists(), "nothing ran: no build result")

    def test_mogrt_build_keeps_the_stage_failure(self):
        from lib import mogrt_builder
        p = client(self.tmp, "Client A")
        with common.use_context(common.Context(p.root)), self.stage_fails():
            res = mogrt_builder.build(p)
        self.assert_kept(res)
        self.assertIn("jsx", res)

    def test_ae_build_result_names_the_copy_it_used(self):
        """ae-build-result.json: `script_copy_used` is the path -r received; the copy itself is gone after the run."""
        from lib import ae_builder
        p = client(self.tmp, "Client A")
        with common.use_context(common.Context(p.root)):
            jsx = Path(ae_builder.generate(p)["jsx"])
            aep = Path(ae_builder.generate(p)["aep"])
            self.on_launch = lambda: (aep.parent.mkdir(parents=True, exist_ok=True), aep.write_bytes(b"AEP"))
            res = ae_builder.execute(p, jsx, timeout=5)
        self.assertEqual(res["status"], "AEP_CREATED", res)
        doc = json.loads(p.p("04_after_effects/ae-build-result.json").read_text(encoding="utf-8"))
        self.assertEqual(doc["script_copy_used"], self.launched[0][0][2])
        self.assertRegex(doc["script_copy_kept_until"], TZ)
        self.assertEqual(self.copies(), [Path(doc["script_copy_used"])])

    def test_the_cli_carries_the_stage_failure_how(self):
        """cmd_ae_build lifts `how` to the top-level document (it already does for refusals)."""
        cli = _load_cli()
        p = client(self.tmp, "Client A")
        with common.use_context(common.Context(p.root)), self.stage_fails(), \
                mock.patch.object(cli, "refuse_stale_window"), mock.patch.object(cli, "require_plan_approval"), \
                mock.patch.object(cli, "P", lambda a: p):
            doc = cli_doc(cli.cmd_ae_build, types.SimpleNamespace())
        self.assertEqual(doc["status"], "SCRIPT_STAGE_FAILED", doc)
        self.assertIn("Run Script File", doc["how"])

    def test_mogrt_build_result_names_the_copy_it_used(self):
        import zipfile
        from lib import mogrt_builder
        p = client(self.tmp, "Client A")
        d = mogrt_builder.mogrt_dir(p)

        def write_all():
            d.mkdir(parents=True, exist_ok=True)
            for k in mogrt_builder.MOGRTS:
                with zipfile.ZipFile(d / f"NH_{k}.mogrt", "w") as z:
                    z.writestr("definition.json", "{}")
        self.on_launch = write_all
        with common.use_context(common.Context(p.root)):
            res = mogrt_builder.build(p, timeout=5)
        self.assertEqual(res["status"], "MOGRTS_CREATED", res)
        doc = json.loads((d / "mogrt-build-result.json").read_text(encoding="utf-8"))
        self.assertEqual(doc["script_copy_used"], self.launched[0][0][2])
        self.assertRegex(doc["script_copy_kept_until"], TZ)


if __name__ == "__main__":
    unittest.main()
