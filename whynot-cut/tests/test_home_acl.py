"""BL-16: the engine home outside the user profile is locked on creation and checked by doctor (lib/home_acl.py).

The ACL is read as SDDL (GetNamedSecurityInfoW): SIDs and the fixed SDDL aliases (SY, BA, AU, BU, WD), never account
names, so a localized Windows reads the same as an English one. The fixtures are SDDL strings read on the company
PC (Windows 11, 2026-10-19). One real run locks a scratch folder under the temp folder; nothing touches a drive root.
    <runtime python> -m unittest discover -s <plugin>/tests -p test_home_acl.py -v
"""
import sys as _sys
_sys.dont_write_bytecode = True
import _isolation  # noqa: F401,E402  G79: sandbox the engine home first (tests/_isolation.py)
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SK = Path(__file__).resolve().parents[1]
if str(SK / "engine" / "reel") not in sys.path:
    sys.path.insert(0, str(SK / "engine" / "reel"))

from lib import home_acl  # noqa: E402

IS_WIN = os.name == "nt"
ME = "S-1-5-21-309784801-1742820768-791828555-1001"
OTHER = "S-1-5-21-309784801-1742820768-791828555-1002"

# read on the company PC: a folder made in D:\ (D:\ClaudeData\Temp), inheriting the drive root's ACL
D_SUBFOLDER = ("O:S-1-5-21-309784801-1742820768-791828555-1001D:(A;ID;FA;;;BA)(A;OICIIOID;GA;;;BA)(A;ID;FA;;;SY)"
               "(A;OICIIOID;GA;;;SY)(A;ID;0x1301bf;;;AU)(A;OICIIOID;SDGXGWGR;;;AU)(A;ID;0x1200a9;;;BU)"
               "(A;OICIIOID;GXGR;;;BU)")
# read on the company PC: the C:\ root; a folder made there (C:\whynot) inherits its AU entry as below
C_ROOT = ("O:S-1-5-80-956008885-3418522649-1831038044-1853292631-2271478464D:PAI(A;OICI;FA;;;BA)(A;OICI;FA;;;SY)"
          "(A;OICI;0x1200a9;;;BU)(A;OICIIO;SDGXGWGR;;;AU)(A;;LC;;;AU)(A;;0x1000a1;;;S-1-15-3-65536-1888954469-"
          "739942743-1668119174-2468466756-4239452838-1296943325-355587736-700089176)")
C_SUBFOLDER = (f"O:{ME}D:AI(A;OICIID;FA;;;BA)(A;OICIID;FA;;;SY)(A;OICIID;0x1200a9;;;BU)(A;ID;0x1301bf;;;AU)"
               "(A;OICIIOID;SDGXGWGR;;;AU)")
# read on the company PC: the default engine home under the profile, and the profile itself (a read-only capability)
PROFILE_HOME = f"O:{ME}D:(A;OICIID;FA;;;SY)(A;OICIID;FA;;;BA)(A;OICIID;FA;;;{ME})"
PROFILE = (f"O:SYD:P(A;OICI;FA;;;SY)(A;OICI;FA;;;BA)(A;OICI;FA;;;{ME})(A;;0x100020;;;S-1-15-3-65536-599108337-"
           "2355189375-1353122160-3480128286-3345335107-485756383-4087318168-230526575)")
# what the lock leaves (icacls /inheritance:r /grant:r <me> SY BA, each (OI)(CI)F)
LOCKED = f"O:{ME}D:PAI(A;OICI;FA;;;{ME})(A;OICI;FA;;;SY)(A;OICI;FA;;;BA)"


class TestAclProblems(unittest.TestCase):
    def test_the_default_drive_subfolder_acl_is_flagged_by_sid(self):
        for sddl in (D_SUBFOLDER, C_SUBFOLDER):
            with self.subTest(sddl=sddl[:40]):
                self.assertEqual(home_acl.acl_problems(sddl, ME), ["Authenticated Users (S-1-5-11)"])
        self.assertIn("Authenticated Users (S-1-5-11)", home_acl.acl_problems(C_ROOT, ME))    # (and its owner)

    def test_a_profile_home_and_a_locked_home_pass(self):
        for sddl in (PROFILE_HOME, PROFILE, LOCKED):
            with self.subTest(sddl=sddl[:40]):
                self.assertEqual(home_acl.acl_problems(sddl, ME), [])

    def test_each_kind_of_write_right_for_another_sid_is_flagged(self):
        for rights in ("FA", "FW", "GA", "GW", "WD", "WO", "SD", "DC", "LC", "DT", "0x2", "0x4", "0x40",
                       "0x10000", "0x1301bf", "0x10000000", "0x40000000"):
            with self.subTest(rights=rights):
                self.assertEqual(home_acl.acl_problems(f"O:{ME}D:P(A;;{rights};;;WD)", ME), ["Everyone (S-1-1-0)"])

    def test_read_only_rights_deny_entries_and_audit_are_not_flagged(self):
        for ace in ("(A;OICI;0x1200a9;;;BU)", "(A;;FR;;;WD)", "(A;;FX;;;AU)", "(A;;GRGX;;;AU)", f"(D;OICI;FA;;;{OTHER})"):
            with self.subTest(ace=ace):
                self.assertEqual(home_acl.acl_problems(f"O:{ME}D:P{ace}", ME), [])

    def test_an_unknown_right_or_ace_shape_fails_closed(self):
        self.assertEqual(home_acl.acl_problems(f"O:{ME}D:P(A;;ZZ;;;{OTHER})", ME), [OTHER])
        self.assertEqual(home_acl.acl_problems(f"O:{ME}D:P(OA;;FA;guid;;{OTHER})", ME), [OTHER])
        cond = f"O:{ME}D:P(A;;FA;;;{ME})(XA;;FA;;;WD;(@User.x == 1))(A;;FA;;;SY)"       # its own brackets
        self.assertIn("an access entry this check cannot read", home_acl.acl_problems(cond, ME))

    def test_a_null_dacl_and_another_owner_are_flagged(self):
        self.assertEqual(home_acl.acl_problems(f"O:{ME}D:NO_ACCESS_CONTROL", ME), ["Everyone (no access list)"])
        self.assertEqual(home_acl.acl_problems(f"O:{ME}", ME), ["Everyone (no access list)"])
        self.assertEqual(home_acl.acl_problems(f"O:{OTHER}D:PAI(A;OICI;FA;;;{ME})", ME), [f"{OTHER} (owner)"])
        for owner in ("SY", "BA", ME):
            self.assertEqual(home_acl.acl_problems(f"O:{owner}D:PAI(A;OICI;FA;;;{ME})", ME), [])

    def test_one_line_per_sid(self):
        sddl = f"O:{ME}D:(A;;FA;;;{OTHER})(A;OICIIO;GA;;;{OTHER})(A;;FW;;;BU)"
        self.assertEqual(home_acl.acl_problems(sddl, ME), [OTHER, "Users (S-1-5-32-545)"])


class TestLockCommand(unittest.TestCase):
    def test_the_argv_uses_system32_and_sids(self):
        env = {"SystemRoot": r"C:\Windows"}
        argv = home_acl.lock_argv(r"D:\WhyNotCut", ME, environ=env)
        self.assertEqual(argv, [os.path.join(r"C:\Windows", "System32", "icacls.exe"), r"D:\WhyNotCut",
                                "/inheritance:r", "/grant:r", f"*{ME}:(OI)(CI)F", "*S-1-5-18:(OI)(CI)F",
                                "*S-1-5-32-544:(OI)(CI)F"])

    def test_the_printed_command_quotes_every_argument_for_powershell(self):
        cmd = home_acl.lock_command(r"D:\Why Not Cut", ME)
        self.assertEqual(cmd, f'icacls "D:\\Why Not Cut" /inheritance:r /grant:r "*{ME}:(OI)(CI)F" '
                              '"*S-1-5-18:(OI)(CI)F" "*S-1-5-32-544:(OI)(CI)F"')

    def test_the_user_sid_comes_from_system32_whoami(self):
        seen = []

        def runner(argv, **kw):
            seen.append(argv)
            return subprocess.CompletedProcess(argv, 0, f'"pc\\yunus","{ME}"\r\n'.encode(), b"")
        self.assertEqual(home_acl.current_user_sid(runner=runner, environ={"SystemRoot": r"C:\Windows"}), ME)
        self.assertEqual(seen[0], [os.path.join(r"C:\Windows", "System32", "whoami.exe"), "/user", "/fo", "csv",
                                   "/nh"])
        bad = lambda argv, **kw: subprocess.CompletedProcess(argv, 0, b"nonsense", b"")   # noqa: E731
        with self.assertRaises(OSError):
            home_acl.current_user_sid(runner=bad, environ={})


class _Tmp(unittest.TestCase):
    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.tmp = Path(self._td.name)
        self.addCleanup(self._td.cleanup)


def _ok(argv, **kw):
    return subprocess.CompletedProcess(argv, 0, b"", b"")


class TestCreateHome(_Tmp):
    def create(self, home, *, runner=_ok, read=lambda p: LOCKED, profile=None, is_win=True):
        calls = []

        def run(argv, **kw):
            calls.append(argv)
            return runner(argv, **kw)
        env = {"USERPROFILE": str(profile or self.tmp / "profile"), "SystemRoot": r"C:\Windows"}
        made = home_acl.create_home(home, is_win=is_win, environ=env, runner=run, sid=ME, read=read)
        return made, calls

    def test_a_new_home_outside_the_profile_is_locked_and_read_back(self):
        home = self.tmp / "drive" / "WhyNotCut"
        made, calls = self.create(home)
        self.assertTrue(made)
        self.assertTrue(home.is_dir())
        self.assertEqual(calls, [home_acl.lock_argv(home, ME, environ={"SystemRoot": r"C:\Windows"})])

    def test_a_new_home_inside_the_profile_is_not_locked(self):
        profile = self.tmp / "Users" / "يونس"
        made, calls = self.create(profile / ".whynot-cut", profile=profile)
        self.assertTrue(made)
        self.assertEqual(calls, [])

    def test_an_existing_home_is_left_as_it_is(self):
        home = self.tmp / "WhyNotCut"
        home.mkdir()
        made, calls = self.create(home)
        self.assertFalse(made)
        self.assertEqual(calls, [])

    def test_macos_only_creates_the_folder(self):
        made, calls = self.create(self.tmp / "WhyNotCut", is_win=False)
        self.assertTrue(made)
        self.assertEqual(calls, [])

    def test_an_icacls_failure_stops_with_the_command_and_leaves_no_folder(self):
        home = self.tmp / "WhyNotCut"
        fail = lambda argv, **kw: subprocess.CompletedProcess(argv, 5, b"", b"Access is denied.")   # noqa: E731
        with self.assertRaises(home_acl.HomeAclError) as cm:
            self.create(home, runner=fail)
        self.assertFalse(home.exists())
        msg = str(cm.exception)
        self.assertFalse(msg[:1].isascii(), msg)                                      # Arabic first
        self.assertIn(str(home), msg)
        self.assertIn(home_acl.lock_command(home, ME), cm.exception.how)

    def test_a_lock_that_does_not_hold_stops_too(self):
        home = self.tmp / "WhyNotCut"
        with self.assertRaises(home_acl.HomeAclError) as cm:
            self.create(home, read=lambda p: D_SUBFOLDER)
        self.assertFalse(home.exists())
        self.assertIn("Authenticated Users", str(cm.exception))

    def test_no_user_sid_stops_too(self):
        home = self.tmp / "WhyNotCut"
        env = {"USERPROFILE": str(self.tmp / "profile")}
        with mock.patch.object(home_acl, "current_user_sid", side_effect=OSError("no SID")), \
                self.assertRaises(home_acl.HomeAclError):
            home_acl.create_home(home, is_win=True, environ=env, runner=_ok, read=lambda p: LOCKED)
        self.assertFalse(home.exists())

    @unittest.skipUnless(IS_WIN, "junctions: Windows")
    def test_a_home_under_a_linked_parent_is_refused(self):
        import _winapi
        real = self.tmp / "real"
        real.mkdir()
        link = self.tmp / "link"
        _winapi.CreateJunction(str(real), str(link))
        self.addCleanup(os.rmdir, link)                                   # the link as a link, never its target
        with self.assertRaises(home_acl.HomeAclError) as cm:
            self.create(link / "WhyNotCut")
        self.assertIn("link", str(cm.exception))
        self.assertEqual(list(real.iterdir()), [])


class TestDoctorFixes(_Tmp):
    def fixes(self, home, *, read=lambda p: LOCKED, is_win=True):
        return home_acl.doctor_fixes(home, is_win=is_win, read=read, sid=ME)

    def test_a_writable_by_others_home_is_an_editor_fix_with_the_exact_command(self):
        home = self.tmp / "whynot"
        home.mkdir()
        (fix,) = self.fixes(home, read=lambda p: C_SUBFOLDER)
        self.assertEqual(fix["who"], "editor")
        self.assertIn("Authenticated Users (S-1-5-11)", fix["item"])
        self.assertIn(home_acl.lock_command(home, ME), fix["fix"])

    def test_a_locked_or_profile_home_has_no_fix(self):
        home = self.tmp / "h"
        home.mkdir()
        for sddl in (LOCKED, PROFILE_HOME):
            self.assertEqual(self.fixes(home, read=lambda p, s=sddl: s), [])

    def test_a_missing_home_has_no_fix(self):
        self.assertEqual(self.fixes(self.tmp / "none", read=lambda p: C_SUBFOLDER), [])

    def test_an_unreadable_acl_is_a_fix(self):
        home = self.tmp / "h"
        home.mkdir()

        def boom(p):
            raise OSError("denied")
        (fix,) = self.fixes(home, read=boom)
        self.assertIn("could not be read", fix["item"])

    @unittest.skipUnless(IS_WIN, "junctions: Windows")
    def test_a_linked_home_is_a_fix(self):
        import _winapi
        real = self.tmp / "real"
        real.mkdir()
        link = self.tmp / "home"
        _winapi.CreateJunction(str(real), str(link))
        self.addCleanup(os.rmdir, link)
        fixes = self.fixes(link)
        self.assertEqual(len(fixes), 1, fixes)
        self.assertIn("link", fixes[0]["item"])

    @unittest.skipIf(IS_WIN, "POSIX modes")
    def test_posix_group_or_other_write_is_a_fix(self):
        home = self.tmp / "h"
        home.mkdir()
        os.chmod(home, 0o775)
        (fix,) = self.fixes(home, is_win=False)
        self.assertIn(f'chmod go-w "{home}"', fix["fix"])
        os.chmod(home, 0o755)
        self.assertEqual(self.fixes(home, is_win=False), [])


@unittest.skipUnless(IS_WIN, "the real lock: Windows")
class TestRealLock(_Tmp):
    """One real run: create, lock, read the ACL back, remove the folder as a folder. The scratch folder is in the temp
    folder (D:\\ClaudeData\\Temp on the company PC, a non-system drive); USERPROFILE points elsewhere so it is
    treated as outside the profile."""

    def test_create_lock_read_back_remove(self):
        home = self.tmp / "WhyNotCut"
        env = dict(os.environ, USERPROFILE=str(self.tmp / "profile"))
        try:
            self.assertTrue(home_acl.create_home(home, is_win=True, environ=env))
            sddl = home_acl.read_sddl(home)
            sid = home_acl.current_user_sid()
            self.assertEqual(home_acl.acl_problems(sddl, sid), [], sddl)
            self.assertIn("D:P", sddl)                                         # protected: nothing inherited
            self.assertEqual(home_acl.doctor_fixes(home, is_win=True), [])
        finally:
            if home.exists():
                os.rmdir(home)                                                 # empty folder, never a tree walk


if __name__ == "__main__":
    unittest.main()
