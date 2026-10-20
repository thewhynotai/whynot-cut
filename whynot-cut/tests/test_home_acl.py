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
# read on the company PC: the C:\ root. C_SUBFOLDER is DERIVED from it by the inheritance rules (what a C:\whynot
# made there gets), not read from a real folder: no test or probe creates anything at the root of C:\
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
        self.assertEqual(home_acl.acl_problems(f"O:{ME}D:P(A;;FA;;)", ME), ["an access entry this check cannot read"])

    def test_creator_owner_and_the_builtin_administrator_are_not_flagged(self):
        self.assertEqual(home_acl.acl_problems(f"O:{ME}D:P(A;OICIIO;GA;;;CO)(A;OICI;FA;;;{ME})", ME), [])
        admin = "S-1-5-21-309784801-1742820768-791828555-500"
        self.assertEqual(home_acl.acl_problems("O:LAD:P(A;OICI;FA;;;LA)", admin), [])
        self.assertEqual(home_acl.acl_problems("O:LAD:P(A;OICI;FA;;;LA)", ME), ["LA", "LA (owner)"])

    def test_a_null_dacl_and_another_owner_are_flagged(self):
        self.assertEqual(home_acl.acl_problems(f"O:{ME}D:NO_ACCESS_CONTROL", ME), ["Everyone (no access list)"])
        self.assertEqual(home_acl.acl_problems(f"O:{ME}", ME), ["Everyone (no access list)"])
        self.assertEqual(home_acl.acl_problems(f"O:{OTHER}D:PAI(A;OICI;FA;;;{ME})", ME), [f"{OTHER} (owner)"])
        for owner in ("SY", "BA", ME):
            self.assertEqual(home_acl.acl_problems(f"O:{owner}D:PAI(A;OICI;FA;;;{ME})", ME), [])

    def test_the_fixed_aliases_read_as_their_sids(self):
        """Fix r1 P3: OWNER RIGHTS is S-1-3-4, and a built-in alias (e.g. Remote Desktop Users) is a real SID, so the
        fix command can remove its explicit grant."""
        for alias, sid in (("OW", "S-1-3-4"), ("RD", "S-1-5-32-555"), ("RU", "S-1-5-32-554"),
                           ("BO", "S-1-5-32-551"), ("WR", "S-1-5-33")):
            with self.subTest(alias=alias):
                self.assertEqual(home_acl.acl_problems(f"O:{ME}D:P(A;;FA;;;{alias})", ME), [sid])

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

    def test_explicit_grants_of_the_flagged_sids_are_removed_too(self):
        argv = home_acl.lock_argv("H", ME, environ={}, remove=["S-1-5-32-545", OTHER])
        self.assertEqual(argv[1:6], ["H", "/inheritance:r", "/remove:g", "*S-1-5-32-545", "/remove:g"])
        self.assertEqual(argv[6:8], [f"*{OTHER}", "/grant:r"])
        self.assertIn('/remove:g "*S-1-5-32-545"', home_acl.lock_command("H", ME, ["S-1-5-32-545"]))

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


class TestPrepareHome(_Tmp):
    def create(self, home, *, runner=_ok, read=lambda p: LOCKED, profile=None, is_win=True):
        calls = []

        def run(argv, **kw):
            calls.append(argv)
            return runner(argv, **kw)
        env = {"USERPROFILE": str(profile or self.tmp / "profile"), "SystemRoot": r"C:\Windows"}
        made = home_acl.prepare_home(home, is_win=is_win, environ=env, runner=run, sid=ME, read=read)
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

    def test_an_existing_locked_home_is_left_as_it_is(self):
        home = self.tmp / "WhyNotCut"
        home.mkdir()
        made, calls = self.create(home)
        self.assertFalse(made)
        self.assertEqual(calls, [])

    def test_an_existing_home_others_may_write_in_stops_setup_and_is_kept(self):
        """Review finding 1: setup never continues on a writable-by-others home (e.g. one the installer or uv's
        download made, or a C:\\whynot made by hand); the editor gets the exact command, nothing is changed."""
        home = self.tmp / "WhyNotCut"
        (home / "bin").mkdir(parents=True)
        with self.assertRaises(home_acl.HomeAclError) as cm:
            self.create(home, read=lambda p: D_SUBFOLDER)
        self.assertTrue((home / "bin").is_dir())
        self.assertFalse(str(cm.exception)[:1].isascii())
        self.assertIn("Authenticated Users (S-1-5-11)", str(cm.exception))
        self.assertIn(home_acl.lock_command(home, ME, ["S-1-5-11"]), cm.exception.how)

    def test_an_existing_open_home_inside_the_profile_is_not_checked(self):
        profile = self.tmp / "Users" / "x"
        (profile / ".whynot-cut").mkdir(parents=True)
        made, calls = self.create(profile / ".whynot-cut", profile=profile, read=lambda p: D_SUBFOLDER)
        self.assertEqual((made, calls), (False, []))

    def test_an_existing_home_with_items_owned_by_another_account_stops_setup(self):
        """Fix r1 P2 (master r1): a locked home can still hold what another account made there while it was open."""
        home = self.tmp / "WhyNotCut"
        (home / "runtimes").mkdir(parents=True)
        read = lambda p: f"O:{OTHER}D:PAI(A;OICI;FA;;;{ME})" if str(p).endswith("runtimes") else LOCKED   # noqa: E731
        with self.assertRaises(home_acl.HomeAclError) as cm:
            self.create(home, read=read)
        self.assertFalse(str(cm.exception)[:1].isascii())
        self.assertIn("runtimes", str(cm.exception))
        self.assertIn("new empty folder", cm.exception.how)
        self.assertTrue((home / "runtimes").is_dir())

    def test_a_folder_that_cannot_be_made_is_arabic_first_guidance(self):
        """Fix r1 P3 (peer P3-2): e.g. a drive root where this account may not make folders."""
        home = self.tmp / "WhyNotCut"
        with mock.patch.object(home_acl.os, "mkdir", side_effect=PermissionError(13, "Access is denied")), \
                self.assertRaises(home_acl.HomeAclError) as cm:
            self.create(home)
        self.assertFalse(str(cm.exception)[:1].isascii())
        self.assertIn(str(home), str(cm.exception))
        self.assertIn("WHYNOT_HOME", cm.exception.how)

    def test_a_file_in_the_way_is_guidance(self):
        home = self.tmp / "WhyNotCut"
        home.write_text("x", encoding="utf-8")
        with self.assertRaises(home_acl.HomeAclError):
            self.create(home)
        self.assertTrue(home.is_file())

    def test_an_item_made_before_the_lock_stops_setup(self):
        """Review finding 2: whatever another account put into the new folder before the lock stays theirs."""
        home = self.tmp / "WhyNotCut"

        def planted(argv, **kw):
            (home / "sitecustomize.py").write_text("x", encoding="utf-8")
            return _ok(argv)
        with self.assertRaises(home_acl.HomeAclError) as cm:
            self.create(home, runner=planted)
        self.assertIn("before it was locked", str(cm.exception))
        self.assertTrue(home.is_dir())                                    # not empty: never removed by us

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
            home_acl.prepare_home(home, is_win=True, environ=env, runner=_ok, read=lambda p: LOCKED)
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

    @unittest.skipUnless(IS_WIN, "junctions: Windows")
    def test_an_existing_linked_home_is_refused(self):
        """Fix r1 P2 (peer P2-1, spec: a linked home is refused): an existing junction home, or an existing home under
        a linked parent, stops setup too; nothing is written through the link."""
        import _winapi
        real = self.tmp / "real"
        (real / "WhyNotCut").mkdir(parents=True)
        link = self.tmp / "home"
        _winapi.CreateJunction(str(real), str(link))
        self.addCleanup(os.rmdir, link)
        for home in (link, link / "WhyNotCut"):
            with self.subTest(home=home.name), self.assertRaises(home_acl.HomeAclError) as cm:
                self.create(home)
            self.assertIn("link", str(cm.exception))
        self.assertEqual(list(real.iterdir()), [real / "WhyNotCut"])
        self.assertEqual(list((real / "WhyNotCut").iterdir()), [])

    @unittest.skipUnless(IS_WIN, "junctions: Windows")
    def test_a_profile_reached_through_a_link_is_compared_on_real_paths(self):
        """Fix r1 P3 (r1 P3-1): a folder in the profile that is a junction to another drive is not the profile."""
        import _winapi
        profile, outside = self.tmp / "Users" / "x", self.tmp / "open"
        profile.mkdir(parents=True)
        outside.mkdir()
        _winapi.CreateJunction(str(outside), str(profile / "data"))
        self.addCleanup(os.rmdir, profile / "data")
        env = {"USERPROFILE": str(profile)}
        self.assertFalse(home_acl.under_profile(profile / "data" / "a" / "WhyNotCut", env))
        self.assertTrue(home_acl.under_profile(profile / ".whynot-cut", env))


class TestDoctorFixes(_Tmp):
    def fixes(self, home, *, read=lambda p: LOCKED, is_win=True):
        return home_acl.doctor_fixes(home, is_win=is_win, read=read, sid=ME)

    def test_a_writable_by_others_home_is_an_editor_fix_with_the_exact_command(self):
        home = self.tmp / "whynot"
        home.mkdir()
        (fix,) = self.fixes(home, read=lambda p: C_SUBFOLDER)
        self.assertEqual(fix["who"], "editor")
        self.assertIn("Authenticated Users (S-1-5-11)", fix["item"])
        self.assertIn(home_acl.lock_command(home, ME, ["S-1-5-11"]), fix["fix"])
        # fix r1 P3 (peer P3-4): Git Bash may rewrite the /switches of a native command, so the shell is named
        self.assertIn("PowerShell or Command Prompt", fix["fix"])

    def test_an_alias_grant_is_removed_by_the_command(self):
        home = self.tmp / "whynot"
        home.mkdir()
        (fix,) = self.fixes(home, read=lambda p: f"O:{ME}D:P(A;OICI;FA;;;{ME})(A;OICI;0x1301bf;;;RD)")
        self.assertIn('/remove:g "*S-1-5-32-555"', fix["fix"])

    def test_a_top_level_item_owned_by_another_account_is_a_fix(self):
        """Review finding 4: the folder's own list does not cover what another account already owns inside."""
        home = self.tmp / "h"
        (home / "runtimes").mkdir(parents=True)
        (home / "models").mkdir()
        read = lambda p: f"O:{OTHER}D:PAI(A;OICI;FA;;;{ME})" if str(p).endswith("runtimes") else LOCKED   # noqa: E731
        (fix,) = self.fixes(home, read=read)
        self.assertIn("(runtimes)", fix["item"])
        self.assertIn("new empty folder", fix["fix"])

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

    def test_posix_a_dangling_link_home_is_a_fix_not_a_crash(self):
        """Fix r1 P3 (r1 P3-3): reel doctor on macOS with a home that is a symlink to nothing."""
        home = self.tmp / "h"
        try:
            os.symlink(self.tmp / "gone", home)
        except (OSError, NotImplementedError):
            self.skipTest("this account may not make symlinks")
        self.addCleanup(os.unlink, home)                                  # the link as a link
        (fix,) = self.fixes(home, is_win=False)
        self.assertIn("could not be read", fix["item"])


@unittest.skipUnless(IS_WIN, "the real lock: Windows")
class TestRealLock(_Tmp):
    """One real run: create, lock, read the ACL back, remove the folder as a folder. The scratch folder is in the temp
    folder (D:\\ClaudeData\\Temp on the company PC, a non-system drive); USERPROFILE points elsewhere so it is
    treated as outside the profile."""

    def test_create_lock_read_back_remove(self):
        home = self.tmp / "Why Not Cut"                                   # fix r1 P3: a path with spaces, for real
        env = dict(os.environ, USERPROFILE=str(self.tmp / "profile"))
        try:
            self.assertTrue(home_acl.prepare_home(home, is_win=True, environ=env))
            sddl = home_acl.read_sddl(home)
            sid = home_acl.current_user_sid()
            self.assertEqual(home_acl.acl_problems(sddl, sid), [], sddl)
            self.assertIn("D:P", sddl)                                         # protected: nothing inherited
            self.assertEqual(home_acl.doctor_fixes(home, is_win=True), [])
            self.assertFalse(home_acl.prepare_home(home, is_win=True, environ=env))     # a second setup: as it is
            # review finding 3: an explicit grant (Users: modify) is flagged, and the doctor's command removes it
            icacls = home_acl.system32("icacls.exe")
            r = subprocess.run([icacls, str(home), "/grant", "*S-1-5-32-545:(OI)(CI)M"], capture_output=True,
                               timeout=60)
            self.assertEqual(r.returncode, 0, r.stderr)
            (fix,) = home_acl.doctor_fixes(home, is_win=True)
            self.assertIn("Users (S-1-5-32-545)", fix["item"])
            r = subprocess.run(home_acl.lock_argv(home, sid, remove=["S-1-5-32-545"]), capture_output=True,
                               timeout=60)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertEqual(home_acl.doctor_fixes(home, is_win=True), [], home_acl.read_sddl(home))
        finally:
            if home.exists():
                os.rmdir(home)                                                 # empty folder, never a tree walk


if __name__ == "__main__":
    unittest.main()
