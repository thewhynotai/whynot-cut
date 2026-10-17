# SPDX-License-Identifier: GPL-3.0-or-later
# © 2026 The Why Not AI (thewhynot.ai)
"""Addendum J13.3 / Phase 4 Task 15 / Addendum L-T8: `lib/linksafe.py`, the shared link-safe remover and write
confinement (COORDINATION rule 15, the 2026-10-14 junction incident).

Every link in these tests is made in the test's own temp folder: `_winapi.CreateJunction` on Windows, `os.symlink`
elsewhere (a test is skipped only when the OS refuses to make the link). A sentinel file outside the tree proves a
target was never touched. Run:
    <engine python> -m unittest discover -s whynot-cut/tests -p test_j5_linksafe.py -v
"""
import sys as _sys
_sys.dont_write_bytecode = True
import _isolation  # noqa: F401,E402  G79: sandbox the engine home first (tests/_isolation.py)
import os
import stat
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from test_j0_support import NetGuardCase  # noqa: E402

from lib import errors, linksafe  # noqa: E402


def dir_link(link: Path, target: Path):
    """A directory link: a junction on Windows, a symlink elsewhere."""
    if sys.platform == "win32":
        import _winapi
        _winapi.CreateJunction(str(target), str(link))
    else:
        os.symlink(target, link, target_is_directory=True)


def file_link(test, link: Path, target: Path):
    try:
        os.symlink(target, link)
    except (OSError, NotImplementedError) as e:
        test.skipTest(f"the OS refused a file symlink here: {e}")


class Tmp(NetGuardCase):
    def setUp(self):
        super().setUp()
        d = tempfile.TemporaryDirectory()
        self.addCleanup(d.cleanup)
        self.tmp = Path(d.name)
        self.root = self.tmp / "client عميل"
        self.root.mkdir()
        self.outside = self.tmp / "outside"
        self.outside.mkdir()
        self.sentinel = self.outside / "sentinel.txt"
        self.sentinel.write_text("keep me", encoding="utf-8")

    def tree(self) -> Path:
        t = self.root / "output" / "from_website" / "run1"
        (t / "logos" / "deep").mkdir(parents=True)
        (t / "logos" / "a.png").write_bytes(b"x" * 100)
        (t / "logos" / "deep" / "شعار.png").write_bytes(b"y" * 50)
        ro = t / "readonly.txt"
        ro.write_bytes(b"z" * 7)
        os.chmod(ro, stat.S_IREAD)
        return t


class TestIsLink(Tmp):
    def test_junction_or_symlink_is_a_link_plain_dir_is_not(self):
        dir_link(self.root / "j", self.outside)
        self.assertTrue(linksafe.is_link(self.root / "j"))
        self.assertFalse(linksafe.is_link(self.outside))
        self.assertFalse(linksafe.is_link(self.root / "missing"))

    def test_windows_cloud_placeholder_is_not_a_link(self):
        fake = mock.Mock(st_mode=stat.S_IFREG, st_file_attributes=0x400, st_reparse_tag=0x9000001A)
        with mock.patch.object(linksafe.os, "lstat", return_value=fake):
            self.assertFalse(linksafe.is_link(self.root / "x"))
        fake2 = mock.Mock(st_mode=stat.S_IFDIR, st_file_attributes=0x400, st_reparse_tag=0xA0000003)
        with mock.patch.object(linksafe.os, "lstat", return_value=fake2):
            self.assertTrue(linksafe.is_link(self.root / "x"))

    def test_posix_symlink_through_lstat_mode(self):
        fake = mock.Mock(st_mode=stat.S_IFLNK | 0o755, spec=["st_mode"])          # no Windows attributes at all
        with mock.patch.object(linksafe.os, "lstat", return_value=fake):
            self.assertTrue(linksafe.is_link(self.root / "x"))

    def test_lstat_errors_fail_closed(self):
        for exc in (PermissionError("denied"), OSError(5, "io"), ValueError("nul")):
            with self.subTest(exc=exc), mock.patch.object(linksafe.os, "lstat", side_effect=exc):
                with self.assertRaises(errors.Guidance):
                    linksafe.is_link(self.root / "x")
        for exc in (FileNotFoundError(), NotADirectoryError()):
            with self.subTest(exc=exc), mock.patch.object(linksafe.os, "lstat", side_effect=exc):
                self.assertFalse(linksafe.is_link(self.root / "x"))


class TestRemove(Tmp):
    def test_tree_with_links_removed_targets_untouched_bytes_counted(self):
        t = self.tree()
        dir_link(t / "logos" / "to_outside", self.outside)
        freed = linksafe.remove(t, self.root)
        self.assertFalse(os.path.lexists(t))
        self.assertTrue(self.sentinel.exists())
        self.assertEqual(self.sentinel.read_text(encoding="utf-8"), "keep me")
        self.assertEqual(freed, 157)

    def test_file_symlink_inside_removed_target_kept(self):
        t = self.tree()
        file_link(self, t / "link.txt", self.sentinel)
        linksafe.remove(t, self.root)
        self.assertTrue(self.sentinel.exists())

    def test_path_itself_a_link_removes_only_the_link(self):
        link = self.root / "output" / "j"
        link.parent.mkdir(parents=True)
        dir_link(link, self.outside)
        self.assertEqual(linksafe.remove(link, self.root), 0)
        self.assertFalse(os.path.lexists(link))
        self.assertTrue(self.sentinel.exists())

    def test_outside_root_refused_nothing_removed(self):
        for p in (self.outside, self.root / ".." / "outside", self.tmp, self.root):
            with self.subTest(p=p), self.assertRaises(errors.Guidance):
                linksafe.remove(p, self.root)
        self.assertTrue(self.sentinel.exists())
        self.assertTrue(self.root.exists())

    def test_sibling_with_root_as_prefix_refused(self):
        sib = self.tmp / (self.root.name + "2")
        sib.mkdir()
        (sib / "f").write_text("x")
        with self.assertRaises(errors.Guidance):
            linksafe.remove(sib / "f", self.root)
        self.assertTrue((sib / "f").exists())

    def test_link_on_the_way_down_refused(self):
        (self.root / "output").mkdir()
        dir_link(self.root / "output" / "j", self.outside)
        with self.assertRaises(errors.Guidance):
            linksafe.remove(self.root / "output" / "j" / "sentinel.txt", self.root)
        self.assertTrue(self.sentinel.exists())

    def test_root_reached_through_a_link_is_fine(self):
        t = self.tree()
        via = self.tmp / "via"
        dir_link(via, self.root)
        freed = linksafe.remove(via / "output" / "from_website" / "run1", via)
        self.assertEqual(freed, 157)
        self.assertFalse(t.exists())

    def test_missing_path_is_zero(self):
        self.assertEqual(linksafe.remove(self.root / "output" / "nothing", self.root), 0)

    def test_single_file(self):
        f = self.root / "a.txt"
        f.write_bytes(b"1234")
        self.assertEqual(linksafe.remove(f, self.root), 4)
        self.assertFalse(f.exists())

    def test_hard_link_removed_other_name_kept(self):
        src = self.outside / "hard.bin"
        src.write_bytes(b"data")
        dst = self.root / "hard.bin"
        os.link(src, dst)
        linksafe.remove(dst, self.root)
        self.assertEqual(src.read_bytes(), b"data")


class TestRemoveHardening(Tmp):
    def test_narrow_scope_behind_a_planted_junction_is_refused(self):
        assets = self.root / "assets" / "Logo"
        assets.mkdir(parents=True)
        (assets / "logo.png").write_bytes(b"client")
        (self.root / "output").mkdir()
        dir_link(self.root / "output" / "from_website", self.root / "assets")
        w = "output/from_website"
        for fn in (lambda: linksafe.remove(self.root / w / "Logo", self.root, within=w),
                   lambda: linksafe.create_new(self.root / w / "run1" / "x.json", self.root, b"x", within=w),
                   lambda: linksafe.replace_atomic(self.root / w / "Logo" / "logo.png", self.root, b"P", within=w),
                   lambda: linksafe.makedirs(self.root / w / "run1", self.root, within=w)):
            with self.assertRaises(errors.Guidance):
                fn()
        self.assertEqual((assets / "logo.png").read_bytes(), b"client")
        self.assertFalse((self.root / "assets" / "run1").exists())

    def test_scope_itself_is_never_removed(self):
        fw = self.root / "output" / "from_website"
        fw.mkdir(parents=True)
        with self.assertRaises(errors.Guidance):
            linksafe.remove(fw, self.root, within="output/from_website")
        self.assertTrue(fw.exists())

    def test_trailing_dots_and_spaces_never_widen_a_removal(self):
        fw = self.root / "output" / "from_website"
        (fw / "run1").mkdir(parents=True)
        (fw / "current.json").write_text("{}")
        (self.root / "output" / "a").mkdir()
        for p in (str(fw) + os.sep + "...", str(self.root / "output" / "a") + " ", str(fw / "run1") + "."):
            with self.subTest(p=p), self.assertRaises(errors.Guidance):
                linksafe.remove(p, self.root)
        self.assertTrue((fw / "run1").exists() and (fw / "current.json").exists() and (self.root / "output" / "a").exists())

    def test_a_folder_swapped_for_a_junction_mid_walk_is_not_followed(self):
        t = self.tree()
        sub = t / "logos" / "deep"
        real_lstat = os.lstat
        calls = {"n": 0}

        def swapping_lstat(p, *a, **k):
            if os.fspath(p) == str(sub):
                calls["n"] += 1
                if calls["n"] == 2:                    # after the walk saw a folder, before it scans it
                    os.rename(sub, t / "moved_away")
                    dir_link(sub, self.outside)
            return real_lstat(p, *a, **k)
        with mock.patch.object(linksafe.os, "lstat", swapping_lstat):
            try:
                linksafe.remove(t, self.root)
            except errors.Guidance:
                pass
        if sys.platform == "win32":
            self.assertGreaterEqual(calls["n"], 2)    # the swap really happened between the two looks
        self.assertTrue(self.sentinel.exists())
        self.assertEqual(self.sentinel.read_text(encoding="utf-8"), "keep me")

    def test_read_only_hard_link_never_unlocks_the_file_outside(self):
        src = self.outside / "client_source.bin"
        src.write_bytes(b"source")
        os.chmod(src, stat.S_IREAD)
        self.addCleanup(os.chmod, src, stat.S_IWRITE | stat.S_IREAD)
        os.link(src, self.root / "copy.bin")
        try:
            linksafe.remove(self.root / "copy.bin", self.root)
        except linksafe.RemoveIncomplete:
            pass
        self.assertFalse(os.stat(src).st_mode & stat.S_IWRITE)
        self.assertEqual(src.read_bytes(), b"source")

    def test_hard_linked_files_free_no_bytes(self):
        src = self.outside / "big.bin"
        src.write_bytes(b"x" * 1000)
        d = self.root / "out"
        d.mkdir()
        os.link(src, d / "big.bin")
        (d / "own.bin").write_bytes(b"y" * 10)
        self.assertEqual(linksafe.remove(d, self.root), 10)

    @unittest.skipUnless(sys.platform == "win32", "a file held open blocks deletion on Windows")
    def test_locked_file_is_reported_the_rest_is_removed_and_counted(self):
        d = self.root / "run2"
        d.mkdir()
        (d / "big.bin").write_bytes(b"b" * 1000)
        locked = d / "locked.bin"
        locked.write_bytes(b"l")
        import _winapi
        h = _winapi.CreateFile(str(locked), _winapi.GENERIC_READ, 0, 0, _winapi.OPEN_EXISTING, 0, 0)
        try:
            with self.assertRaises(linksafe.RemoveIncomplete) as cm:
                linksafe.remove(d, self.root)
        finally:
            _winapi.CloseHandle(h)
        self.assertEqual(cm.exception.freed, 1000)
        self.assertEqual([os.path.basename(f) for f, _why in cm.exception.failures][:1], ["locked.bin"])
        self.assertFalse((d / "big.bin").exists())


class TestReviewRound2Linksafe(Tmp):
    def test_file_directly_inside_within_can_be_written(self):
        fw = self.root / "output" / "from_website"
        fw.mkdir(parents=True)
        w = "output/from_website"
        linksafe.create_new(fw / "current.json", self.root, b"{}", within=w)
        linksafe.replace_atomic(fw / "current.json", self.root, b'{"run":1}', within=w)
        self.assertEqual((fw / "current.json").read_bytes(), b'{"run":1}')
        linksafe.makedirs(fw, self.root, within=w)                  # the scope folder itself may be made

    def test_swap_after_the_scan_is_not_followed(self):
        t = self.tree()
        sub = t / "logos"
        (self.outside / "a.png").write_bytes(b"outside")
        real_scandir = os.scandir
        state = {"done": False}
        outside = self.outside

        class SwapAfter:
            def __init__(self, it, path):
                self.it, self.path = it, path

            def __enter__(self):
                return self

            def __exit__(self, *a):
                self.it.close()
                if os.fspath(self.path) == str(sub) and not state["done"]:
                    state["done"] = True                  # the scan is done: now swap the folder for a junction
                    os.rename(sub, t / "moved_away")
                    dir_link(sub, outside)

            def __iter__(self):
                return iter(self.it)

        def scandir(p):
            return SwapAfter(real_scandir(p), p)
        with mock.patch.object(linksafe.os, "scandir", scandir):
            try:
                linksafe.remove(t, self.root)
            except errors.Guidance:
                pass
        if sys.platform == "win32":
            self.assertTrue(state["done"])
        self.assertEqual((self.outside / "a.png").read_bytes(), b"outside")
        self.assertTrue(self.sentinel.exists())

    @unittest.skipUnless(sys.platform == "win32", "rooted paths and alternate data streams are Windows")
    def test_rooted_path_without_drive_still_name_checked(self):
        (self.root / "output" / "from_website" / "run1").mkdir(parents=True)
        (self.root / "output" / "v.mp4").write_bytes(b"video")
        rooted = os.path.splitdrive(str(self.root))[1]
        for fn in (lambda: linksafe.remove(rooted + "\\output\\from_website\\...", self.root, within="output"),
                   lambda: linksafe.create_new(rooted + "\\output\\v.mp4:evil", self.root, b"ads"),
                   lambda: linksafe.create_new(rooted + "\\output\\CON", self.root, b"x")):
            with self.assertRaises(errors.Guidance):
                fn()
        self.assertTrue((self.root / "output" / "from_website" / "run1").exists())
        self.assertFalse(os.path.exists(str(self.root / "output" / "CON")) and
                         "CON" in os.listdir(self.root / "output"))

    def test_makedirs_rechecks_a_folder_that_turns_into_a_link(self):
        real_mkdir = os.mkdir

        def evil_mkdir(p, *a, **k):
            if os.fspath(p).endswith("Logo"):
                dir_link(Path(p), self.outside)           # someone made a junction in its place
                return
            return real_mkdir(p, *a, **k)
        (self.root / "assets").mkdir()
        with mock.patch.object(linksafe.os, "mkdir", evil_mkdir):
            with self.assertRaises(errors.Guidance):
                linksafe.makedirs(self.root / "assets" / "Logo" / "from-website", self.root)
        self.assertFalse((self.outside / "from-website").exists())

    def test_makedirs_rolls_back_what_it_made(self):
        real_mkdir = os.mkdir
        calls = {"n": 0}

        def flaky(p, *a, **k):
            calls["n"] += 1
            if calls["n"] == 2:
                raise PermissionError(13, "denied", str(p))
            return real_mkdir(p, *a, **k)
        with mock.patch.object(linksafe.os, "mkdir", flaky):
            with self.assertRaises(errors.Guidance):
                linksafe.makedirs(self.root / "n1" / "n2" / "n3", self.root)
        self.assertFalse((self.root / "n1").exists())

    def test_leftover_error_types_are_guidance(self):
        (self.root / "dir").mkdir()
        with self.assertRaises(errors.Guidance):
            linksafe.replace_atomic(self.root / "dir", self.root, b"x")
        with self.assertRaises(errors.Guidance):
            linksafe.create_new(self.tmp / "no-such-root" / "x", self.tmp / "no-such-root", b"x")


class TestConfine(Tmp):
    def test_inside_relative_and_missing_parts_ok(self):
        p = linksafe.confine("output/from_website/run1/x.json", self.root)
        self.assertEqual(p, Path(os.path.realpath(self.root)) / "output" / "from_website" / "run1" / "x.json")

    def test_returns_the_real_path_through_a_link_above_the_root(self):
        via = self.tmp / "via"
        dir_link(via, self.root)
        p = linksafe.confine(via / "output" / "x", via)
        self.assertEqual(p, Path(os.path.realpath(self.root)) / "output" / "x")

    def test_final_real_path_check_holds_even_if_the_link_walk_failed_open(self):
        (self.root / "output").mkdir()
        dir_link(self.root / "output" / "j", self.outside)
        with mock.patch.object(linksafe, "is_link", return_value=False):      # simulate a walk that missed the link
            with self.assertRaises(errors.Guidance):
                linksafe.confine(self.root / "output" / "j" / "x", self.root)

    def test_within_scope_and_links_on_the_way_to_it(self):
        fw = self.root / "output" / "from_website"
        fw.mkdir(parents=True)
        self.assertEqual(linksafe.confine("output/from_website/run1/a", self.root, within="output/from_website"),
                         Path(os.path.realpath(fw)) / "run1" / "a")
        for bad in ("output/other/a", "output/from_website", "assets/x"):
            with self.subTest(bad=bad), self.assertRaises(errors.Guidance):
                linksafe.confine(bad, self.root, within="output/from_website")

    def test_bad_characters_refused_as_guidance(self):
        names = ["a\x00b", "a\x01b"] + (["a<b", "a>b", 'a"b', "a|b", "a?b", "a*b"] if sys.platform == "win32" else [])
        for name in names:
            with self.subTest(name=repr(name)), self.assertRaises(errors.Guidance):
                linksafe.confine(self.root / "output" / name, self.root)

    @unittest.skipUnless(sys.platform == "win32", "Windows path rules")
    def test_only_names_below_the_root_are_checked(self):
        odd = self.tmp / "con.clinic files"            # a legal folder name above the root on Windows 11
        try:
            odd.mkdir()
        except OSError:
            self.skipTest("this Windows refuses the name")
        r = odd / "client"
        r.mkdir()
        self.assertEqual(linksafe.confine(r / "output" / "x", r).name, "x")

    def test_outside_and_dotdot_refused(self):
        for p in (self.outside / "x", self.root / ".." / "outside" / "x", "../outside/x", self.root):
            with self.subTest(p=p), self.assertRaises(errors.Guidance):
                linksafe.confine(p, self.root)

    def test_link_from_root_down_refused_before_any_write(self):
        (self.root / "output").mkdir()
        dir_link(self.root / "output" / "from_website", self.outside)
        with self.assertRaises(errors.Guidance) as cm:
            linksafe.confine(self.root / "output" / "from_website" / "x.json", self.root)
        self.assertIn("link", cm.exception.error.lower())

    def test_link_above_root_allowed(self):
        via = self.tmp / "via"
        dir_link(via, self.tmp)
        p = linksafe.confine(via / self.root.name / "output" / "x", via / self.root.name)
        self.assertTrue(str(p).endswith(os.path.join("output", "x")))

    @unittest.skipUnless(sys.platform == "win32", "Windows path rules")
    def test_windows_oddities_refused(self):
        for name in ("a:stream", "CON", "nul.txt", "x.", "x ", "COM1.png"):
            with self.subTest(name=name), self.assertRaises(errors.Guidance):
                linksafe.confine(self.root / "output" / name, self.root)

    @unittest.skipUnless(sys.platform == "win32", "case-insensitive volume")
    def test_case_insensitive_containment_on_windows(self):
        p = linksafe.confine(str(self.root).upper() + "\\output\\x", self.root)
        self.assertTrue(str(p).lower().endswith("output\\x"))


class TestMakedirsAndWrites(Tmp):
    def test_makedirs_creates_only_missing_folders(self):
        (self.root / "assets").mkdir()
        (self.root / "assets" / "keep.txt").write_text("k")
        made = linksafe.makedirs(self.root / "assets" / "Logo" / "from-website", self.root)
        self.assertEqual([p.name for p in made], ["Logo", "from-website"])
        self.assertEqual((self.root / "assets" / "keep.txt").read_text(), "k")
        self.assertEqual(linksafe.makedirs(self.root / "assets" / "Logo", self.root), [])

    def test_makedirs_refuses_through_a_link(self):
        dir_link(self.root / "assets", self.outside)
        with self.assertRaises(errors.Guidance):
            linksafe.makedirs(self.root / "assets" / "Logo", self.root)
        self.assertFalse((self.outside / "Logo").exists())

    def test_create_new_is_exclusive_and_never_writes_through(self):
        f = linksafe.create_new(self.root / "out" / "a.bin", self.root, b"abc")
        self.assertEqual(f.read_bytes(), b"abc")
        with self.assertRaises(FileExistsError):
            linksafe.create_new(self.root / "out" / "a.bin", self.root, b"zzz")
        self.assertEqual(f.read_bytes(), b"abc")
        os.link(self.sentinel, self.root / "out" / "hard.txt")
        with self.assertRaises(FileExistsError):
            linksafe.create_new(self.root / "out" / "hard.txt", self.root, b"overwrite")
        self.assertEqual(self.sentinel.read_text(encoding="utf-8"), "keep me")

    def test_replace_atomic_replaces_a_hard_link_not_its_target(self):
        (self.root / "out").mkdir()
        os.link(self.sentinel, self.root / "out" / "current.json")
        linksafe.replace_atomic(self.root / "out" / "current.json", self.root, b"{}")
        self.assertEqual((self.root / "out" / "current.json").read_bytes(), b"{}")
        self.assertEqual(self.sentinel.read_text(encoding="utf-8"), "keep me")
        self.assertEqual(sorted(p.name for p in (self.root / "out").iterdir()), ["current.json"])

    def test_makedirs_with_a_file_in_the_way_is_guidance_and_cleans_up(self):
        (self.root / "a").mkdir()
        (self.root / "a" / "file").write_text("x")
        with self.assertRaises(errors.Guidance):
            linksafe.makedirs(self.root / "a" / "file" / "sub", self.root)
        with self.assertRaises(errors.Guidance):
            linksafe.create_new(self.root / "a" / "file" / "x.bin", self.root, b"1")
        self.assertEqual((self.root / "a" / "file").read_text(), "x")

    def test_create_new_on_a_folder_name_is_file_exists(self):
        (self.root / "taken").mkdir()
        with self.assertRaises(FileExistsError):
            linksafe.create_new(self.root / "taken", self.root, b"1")

    def test_create_new_failure_removes_the_folders_it_made(self):
        with mock.patch.object(linksafe.os, "open", side_effect=OSError(28, "No space left")):
            with self.assertRaises((errors.Guidance, OSError)):
                linksafe.create_new(self.root / "n1" / "n2" / "x.bin", self.root, b"1")
        self.assertFalse((self.root / "n1").exists())

    def test_replace_atomic_from_two_threads(self):
        import threading
        (self.root / "out").mkdir()
        errs = []

        def w(data):
            try:
                for _ in range(20):
                    linksafe.replace_atomic(self.root / "out" / "current.json", self.root, data)
            except Exception as e:                    # noqa: BLE001 — collected for the assertion
                errs.append(e)
        ts = [threading.Thread(target=w, args=(b"A" * 100,)), threading.Thread(target=w, args=(b"B" * 100,))]
        [t.start() for t in ts]
        [t.join() for t in ts]
        self.assertEqual(errs, [])                    # Windows' momentary "access denied" is retried inside
        self.assertIn((self.root / "out" / "current.json").read_bytes(), (b"A" * 100, b"B" * 100))
        self.assertEqual(sorted(p.name for p in (self.root / "out").iterdir()), ["current.json"])

    @unittest.skipIf(sys.platform == "win32", "O_NOFOLLOW is POSIX")
    def test_o_nofollow_even_if_confine_missed_a_final_link(self):
        (self.root / "out").mkdir()
        os.symlink(self.sentinel, self.root / "out" / "x")
        with mock.patch.object(linksafe, "confine", side_effect=lambda p, r, within=None: Path(p)):
            with self.assertRaises((errors.Guidance, OSError)):
                linksafe.create_new(self.root / "out" / "x", self.root, b"over")
        self.assertEqual(self.sentinel.read_text(encoding="utf-8"), "keep me")

    @unittest.skipIf(sys.platform == "win32", "mount points are POSIX")
    def test_posix_walk_never_crosses_a_device(self):
        t = self.tree()
        real = os.stat

        def fake_stat(p, *a, **k):
            st = real(p, *a, **k)
            if os.fsdecode(p).endswith("deep"):
                return os.stat_result((st.st_mode, st.st_ino, st.st_dev + 1) + tuple(st)[3:])
            return st
        with mock.patch.object(linksafe.os, "stat", fake_stat):
            with self.assertRaises(linksafe.RemoveIncomplete):
                linksafe.remove(t, self.root)
        self.assertTrue((t / "logos" / "deep" / "شعار.png").exists())

    def test_makedirs_rechecks_each_part_it_creates(self):
        (self.root / "assets").mkdir()
        dir_link(self.root / "assets" / "Logo", self.outside)
        with mock.patch.object(linksafe, "confine", side_effect=lambda p, r, within=None: Path(os.path.abspath(p))):
            with self.assertRaises(errors.Guidance):
                linksafe.makedirs(self.root / "assets" / "Logo" / "from-website", self.root)
        self.assertFalse((self.outside / "from-website").exists())

    def test_writes_refused_through_a_link(self):
        dir_link(self.root / "out", self.outside)
        for fn in (lambda: linksafe.create_new(self.root / "out" / "x", self.root, b"1"),
                   lambda: linksafe.replace_atomic(self.root / "out" / "sentinel.txt", self.root, b"1")):
            with self.assertRaises(errors.Guidance):
                fn()
        self.assertEqual(self.sentinel.read_text(encoding="utf-8"), "keep me")
        self.assertFalse((self.outside / "x").exists())


if __name__ == "__main__":
    unittest.main()
