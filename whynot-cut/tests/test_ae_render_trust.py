"""The folder-trust checks of lib/ae_render (shared with lib/adobe_run): a staging folder under a place every account
may write (%ProgramData%) is used only when it is no link and is owned by this account, SYSTEM or the Administrators.

  * TestRealOwnerCheck: a read-only smoke test of the REAL Windows call (GetNamedSecurityInfoW + the token user SID).
    The check fails closed, so a broken ctypes call would silently switch the %ProgramData% routes off while every
    mocked test stays green. Windows only; it reads owners, it changes nothing.
  * the rest: the NULL-owner case, the aerender roots (never a folder at the root of the system drive: one made there
    inherits Authenticated Users: Modify, which no owner check can see), the engine home's own tmp left unchecked (as
    adobe_run does), and stage_ascii checking again after it made the folder.
Run:  bash tools/test.sh -p test_ae_render_trust.py
"""
import sys as _sys
_sys.dont_write_bytecode = True  # keep the plugin folder free of __pycache__
import _isolation  # noqa: F401,E402  G79: sandbox the engine home first (tests/_isolation.py)
import ctypes
import os
import shutil
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

SK = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SK / "engine" / "reel"))

from lib import adobe_run, ae_render, plat  # noqa: E402

ARABIC_TEMP = r"C:\Users\يونس\AppData\Local\Temp"


class Tmp(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="trust_"))          # inside the test sandbox
        self.addCleanup(shutil.rmtree, self.tmp, True)


@unittest.skipUnless(plat.IS_WIN, "the owner check calls the Windows security API")
class TestRealOwnerCheck(Tmp):
    """Read-only: owners are read, nothing is changed."""

    def test_a_folder_this_account_made_is_trusted(self):
        d = self.tmp / "mine"
        d.mkdir()
        self.assertIs(ae_render._owner_trusted(d), True)
        self.assertIsNone(ae_render.folder_trust_problem([d]))

    def test_system32_is_not(self):
        """Owned by TrustedInstaller: not this user, not SYSTEM, not the Administrators."""
        system32 = Path(os.environ.get("SystemRoot") or r"C:\Windows") / "System32"
        self.assertIs(ae_render._owner_trusted(system32), False)
        self.assertIn("owned by another account", ae_render.folder_trust_problem([system32]))

    def test_a_missing_path_is_not(self):
        self.assertIs(ae_render._owner_trusted(self.tmp / "not-there"), False)

    def test_adobe_run_uses_the_same_real_check(self):
        """adobe_run has no owner check of its own: its %ProgramData% route goes through ae_render's."""
        self.assertIs(adobe_run.ae_render, ae_render)
        d = self.tmp / "mine"
        d.mkdir()
        self.assertIsNone(adobe_run.ae_render.folder_trust_problem([d, d / "not-made-yet"]))

    def test_stage_script_uses_a_shared_folder_this_account_owns(self):
        """The whole shared route with the REAL owner check: WhyNotCut, tmp and ae-run made by this account pass, so
        the copy lands there (the engine home here is unsafe, so it can only be the shared folder)."""
        if not adobe_run.r_safe(os.path.abspath(self.tmp)):
            self.skipTest(f"needs a test folder whose path -r accepts; this PC's is {self.tmp}")
        pd = self.tmp / "PD" / "WhyNotCut" / "tmp" / "ae-run"
        eng = self.tmp / "eng home" / "tmp" / "ae-run"                    # a space: never usable as it is
        src = self.tmp / "Client A" / "x.jsx"
        src.parent.mkdir()
        src.write_text("// x\n", encoding="utf-8")
        with mock.patch.object(adobe_run, "stage_dirs", lambda: [(pd, True), (eng, False)]):
            copy, arg = adobe_run.stage_script(src, time.time() + 60)
        self.assertEqual((copy.parent, arg), (pd, str(copy)))
        self.assertEqual(copy.read_text(encoding="utf-8"), "// x\n")


class FakeFn:
    """A Win32 function stand-in: accepts argtypes/restype, records calls, runs `impl`."""

    def __init__(self, name, calls, impl):
        self.name, self.calls, self.impl = name, calls, impl

    def __call__(self, *a):
        self.calls.append(self.name)
        return self.impl(*a)


class TestNullOwner(unittest.TestCase):
    def setUp(self):
        try:
            from ctypes import wintypes  # noqa: F401
        except Exception as e:  # noqa: BLE001  (some non-Windows Pythons cannot load it)
            self.skipTest(f"ctypes.wintypes unavailable here: {e}")

    def test_a_descriptor_without_an_owner_is_not_trusted(self):
        """FAT/exFAT, or a security descriptor without an owner: the call succeeds with a NULL owner. That is not
        trusted, the SID functions never see the NULL, and the descriptor is still freed. No real kernel call."""
        calls = []

        def dll(name, **kw):
            impls = {"GetNamedSecurityInfoW": lambda *a: 0,                         # success, owner left NULL
                     "LocalFree": lambda *a: None, "GetCurrentProcess": lambda: -1, "CloseHandle": lambda *a: 1}
            fns = {n: FakeFn(n, calls, f) for n, f in impls.items()}
            for n in ("IsWellKnownSid", "EqualSid", "OpenProcessToken", "GetTokenInformation"):
                fns[n] = FakeFn(n, calls, lambda *a, n=n: (_ for _ in ()).throw(AssertionError(f"{n} called")))
            return type("Dll", (), fns)()
        with mock.patch.object(plat, "IS_WIN", True), mock.patch.object(ctypes, "WinDLL", dll, create=True):
            self.assertIs(ae_render._owner_trusted(r"E:\exfat\WhyNotCut"), False)
        self.assertEqual(calls, ["GetNamedSecurityInfoW", "LocalFree"])


class TestAerenderRoots(Tmp):
    def setUp(self):
        super().setUp()
        if not str(self.tmp).isascii():
            self.skipTest(f"aerender roots are ASCII only; this PC's test folder is {self.tmp}")

    def roots(self, **env):
        e = {"ProgramData": str(self.tmp / "PD"), "SystemDrive": str(self.tmp / "sysdrive")}
        e.update(env)
        return ae_render.ascii_stage_roots(temp=ARABIC_TEMP, home=self.tmp / "eng", environ=e,
                                           short_path=lambda p: r"C:\Users\D3C0~1\AppData\Local\Temp")

    def test_never_a_root_folder_of_the_system_drive(self):
        with mock.patch.object(ae_render, "_owner_trusted", lambda p: False):     # even with %ProgramData% skipped
            (self.tmp / "PD" / "WhyNotCut").mkdir(parents=True)
            for roots in (self.roots(), self.roots(ProgramData="")):
                self.assertFalse([r for r in roots if str(r).startswith(str(self.tmp / "sysdrive"))], roots)
                self.assertFalse([r for r in roots if "WhyNotCut-tmp" in str(r)], roots)

    def test_the_order(self):
        """Engine home, %ProgramData% (when trusted), the 8.3 form of %TEMP%; then stage_ascii refuses with a how."""
        self.assertEqual([str(r) for r in self.roots()],
                         [str(self.tmp / "eng" / "tmp"), str(self.tmp / "PD" / "WhyNotCut" / "tmp"),
                          r"C:\Users\D3C0~1\AppData\Local\Temp"])

    def test_the_engine_home_tmp_is_not_owner_checked(self):
        """The user's own folder (as in adobe_run): a tmp restored from a backup (an orphaned owner SID) or one made
        a link stays usable for aerender."""
        (self.tmp / "eng" / "tmp").mkdir(parents=True)
        with mock.patch.object(ae_render, "_owner_trusted", lambda p: False), \
                mock.patch.object(ae_render, "_is_reparse", lambda p: True):
            self.assertIn(self.tmp / "eng" / "tmp", self.roots())

    def test_stage_ascii_checks_again_after_making_the_folder(self):
        """Another account could create %ProgramData%\\WhyNotCut between the listing and mkdir: the check runs again
        after mkdir, before the stage is made, and the next root is used."""
        aep = self.tmp / "مشروع.aep"
        aep.write_bytes(b"AEP")
        pd_root = self.tmp / "PD" / "WhyNotCut" / "tmp"
        good = self.tmp / "ok-root"
        seen = []

        def owner(p):
            seen.append(os.path.abspath(p))
            return os.path.abspath(p) != str(self.tmp / "PD" / "WhyNotCut")
        with mock.patch.object(ae_render.plat, "IS_WIN", True), \
                mock.patch.dict(os.environ, {"ProgramData": str(self.tmp / "PD")}), \
                mock.patch.object(ae_render, "ascii_stage_roots", return_value=[pd_root, good]), \
                mock.patch.object(ae_render, "_owner_trusted", owner):
            stage, r_aep, _ = ae_render.stage_ascii(aep)
        self.addCleanup(shutil.rmtree, stage, True)
        self.assertEqual(stage.parent, good)
        self.assertIn(str(self.tmp / "PD" / "WhyNotCut"), seen)
        self.assertEqual(list(pd_root.iterdir()), [], "no stage under the foreign-owned folder")


if __name__ == "__main__":
    unittest.main()
