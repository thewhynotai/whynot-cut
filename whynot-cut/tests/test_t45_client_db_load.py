# SPDX-License-Identifier: GPL-3.0-or-later
# © 2026 The Why Not AI (thewhynot.ai)
"""3.0 Phase 4 T4.5 (part A) — `client_db.load`: every reader of a client-database file that carries paths gets
paths it can open, whether the file stores them relative to the client root (3.0) or absolute (2.x and older 3.0,
possibly from the folder the client was copied from). A reader never writes. Case list: the wnc-queue track's notes.
Run:  bash tools/test.sh -p test_t45_client_db_load.py
"""
import sys as _sys
_sys.dont_write_bytecode = True  # keep the plugin folder free of __pycache__
import _isolation  # noqa: F401,E402  G79: sandbox the engine home first (tests/_isolation.py)
import os
import shutil
import tempfile
import unittest
from pathlib import Path, PurePosixPath, PureWindowsPath
from unittest import mock

sys = _sys
SK = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SK / "engine" / "reel"))

from lib import client_db as CDB  # noqa: E402
from lib.common import Paths, write_json  # noqa: E402

REL_LOGO = "output/client_database/assets/derivatives/logo_display.jpg"


def make_client(parent: Path, name: str) -> Path:
    root = parent / name
    for d in ("assets/Brand", "data/Raw", "output/client_database/assets/derivatives", "output/client_database/branding"):
        (root / d).mkdir(parents=True)
    (root / "assets/Brand/logo.png").write_bytes(b"png")
    (root / REL_LOGO).write_bytes(b"jpg")
    (root / "assets/Brand/Brand-Bold.ttf").write_bytes(b"ttf")
    return root


class Base(unittest.TestCase):
    NAME = "Dr Test د. تجربة"                                # Arabic with spaces

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.root = make_client(self.tmp, self.NAME)
        self.paths = Paths(self.root)
        self.db = self.paths.client_db

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def manifest(self, file, disp, raw=None):
        a = {"file": file, "display_derivative": disp, "rel": "assets/Brand/logo.png", "category": "logo"}
        if raw is not None:
            a["raw_derivative"] = raw
        write_json(self.db / "asset-manifest.json", {"assets": [a], "count": 1})


class TestResolve(Base):
    def test_relative_values_resolve_against_the_root(self):
        self.manifest("assets/Brand/logo.png", REL_LOGO)
        a = CDB.load(self.paths, "asset-manifest.json")["assets"][0]
        self.assertEqual(Path(a["file"]), self.root / "assets/Brand/logo.png")
        self.assertEqual(Path(a["display_derivative"]), self.root / REL_LOGO)
        self.assertTrue(Path(a["display_derivative"]).is_file())
        self.assertEqual(a["rel"], "assets/Brand/logo.png")             # not a path field: untouched

    def test_an_object_with_only_client_db_uses_the_root_above_it(self):
        self.manifest("assets/Brand/logo.png", REL_LOGO)

        class Ep:                                                         # e.g. a test's stand-in for EpisodePaths
            client_db = self.db
        for given in (Ep(), self.db, str(self.db)):
            a = CDB.load(given, "asset-manifest.json")["assets"][0]
            self.assertEqual(Path(a["display_derivative"]), self.root / REL_LOGO, given)

    def test_absolute_inside_the_root_is_kept(self):
        self.manifest(str(self.root / "assets/Brand/logo.png"), str(self.root / REL_LOGO))
        a = CDB.load(self.paths, "asset-manifest.json")["assets"][0]
        self.assertEqual(Path(a["file"]), self.root / "assets/Brand/logo.png")
        self.assertEqual(Path(a["display_derivative"]), self.root / REL_LOGO)

    def test_absolute_from_an_old_root_is_rebased_when_the_file_is_here(self):
        old = self.tmp / "data" / "old drive" / "عميل قديم"                # the OLD place has a "data" folder above it
        self.manifest(str(old / "assets/Brand/logo.png"), str(old / REL_LOGO), raw=str(old / "assets/gone.cr2"))
        a = CDB.load(self.paths, "asset-manifest.json")["assets"][0]
        self.assertEqual(Path(a["file"]), self.root / "assets/Brand/logo.png")
        self.assertEqual(Path(a["display_derivative"]), self.root / REL_LOGO)
        self.assertEqual(a["raw_derivative"], str(old / "assets/gone.cr2"))   # not here: kept, never invented

    def test_both_forms_in_one_file_and_typography(self):
        write_json(self.db / "branding/typography.json", {"families": {"Brand": {"weights": [
            {"style": "Bold", "file": "assets/Brand/Brand-Bold.ttf"},
            {"style": "Regular", "file": str(self.root / "assets/Brand/Brand-Bold.ttf")},
            {"style": "Thin", "file": None}]}},
            "missing_or_uninstalled": ["assets/Brand/Brand-Bold.ttf"], "roles": {"title": "assets/x.ttf"}})
        t = CDB.load(self.paths, "branding/typography.json")
        ws = t["families"]["Brand"]["weights"]
        self.assertEqual(Path(ws[0]["file"]), self.root / "assets/Brand/Brand-Bold.ttf")
        self.assertEqual(Path(ws[1]["file"]), self.root / "assets/Brand/Brand-Bold.ttf")
        self.assertIsNone(ws[2]["file"])
        self.assertEqual(Path(t["missing_or_uninstalled"][0]), self.root / "assets/Brand/Brand-Bold.ttf")
        self.assertEqual(t["roles"], {"title": str(self.root / "assets" / "x.ttf")})   # review d224a9a P3-1: a role
        # given as a file is read like the families' files (a style or a PostScript name is left as it is)

    def test_reference_analysis_files(self):
        old = self.tmp / "elsewhere" / "C"
        (self.root / "data/References").mkdir()
        (self.root / "data/References/ref.mp4").write_bytes(b"v")
        sheet = "output/client_database/reference_analysis/ref/sheet_00.jpg"
        (self.root / sheet).parent.mkdir(parents=True)
        (self.root / sheet).write_bytes(b"j")
        write_json(self.db / "reference_analysis/ref/measurements.json",
                   {"video": str(old / "data/References/ref.mp4"), "contact_sheets": [sheet], "cut_frames": []})
        m = CDB.load(self.paths, "reference_analysis/ref/measurements.json")
        self.assertEqual(Path(m["video"]), self.root / "data/References/ref.mp4")
        self.assertEqual(Path(m["contact_sheets"][0]), self.root / sheet)
        write_json(self.db / "reference_analysis/reference-measurements.json",
                   {"references": [{"video": "data/References/ref.mp4", "contact_sheets": [sheet]}]})
        r = CDB.load(self.paths, "reference_analysis/reference-measurements.json")["references"][0]
        self.assertEqual(Path(r["video"]), self.root / "data/References/ref.mp4")

    def test_missing_gives_the_default_damaged_is_named_like_read_json(self):
        self.assertEqual(CDB.load(self.paths, "asset-manifest.json", {"assets": []}), {"assets": []})
        (self.db / "asset-manifest.json").write_text("{broken", encoding="utf-8")
        from lib.errors import FileFormatError
        with self.assertRaises(FileFormatError):                     # the readers' behaviour is unchanged
            CDB.load(self.paths, "asset-manifest.json", {"assets": []})
        write_json(self.db / "asset-manifest.json", {"assets": [{"file": 5}, "x", None]})
        self.assertEqual(CDB.load(self.paths, "asset-manifest.json")["assets"], [{"file": 5}, "x", None])

    def test_a_file_without_path_fields_is_read_as_is(self):
        write_json(self.db / "branding/brand-tokens.json", {"official_colors": [{"hex": "#112233"}]})
        self.assertEqual(CDB.load(self.paths, "branding/brand-tokens.json"),
                         {"official_colors": [{"hex": "#112233"}]})

    def test_a_reader_never_writes(self):
        self.manifest(str(self.root / "assets/Brand/logo.png"), "assets/Brand/logo.png")
        f = self.db / "asset-manifest.json"
        before = (f.read_bytes(), f.stat().st_mtime_ns)
        CDB.load(self.paths, "asset-manifest.json")
        self.assertEqual((f.read_bytes(), f.stat().st_mtime_ns), before)

    def test_the_default_is_never_shared(self):
        d = {"assets": []}
        got = CDB.load(self.paths, "asset-manifest.json", d)
        got["assets"].append(1)
        self.assertEqual(d, {"assets": []})


class TestPathRules(unittest.TestCase):
    """The pure rules, Windows and POSIX forms, without touching a disk."""

    def test_inside_folds_case_on_windows_and_mac(self):
        root = r"D:\Clients\Dr Test د. تجربة"
        self.assertTrue(CDB.inside_root(r"d:\clients\DR TEST د. تجربة\assets\x.png", root, fold=True, sep="\\"))
        self.assertFalse(CDB.inside_root(r"d:\clients\DR TEST د. تجربة\assets\x.png", root, fold=False, sep="\\"))
        self.assertFalse(CDB.inside_root(r"D:\Clients\Dr Test د. تجربة 2\x.png", root, fold=True, sep="\\"))

    def test_relative_values_are_posix_and_never_climb_out(self):
        self.assertTrue(CDB.is_relative("assets/Brand/logo.png"))
        self.assertTrue(CDB.is_relative("assets\\Brand\\logo.png"))
        for v in ("/Users/x/C/assets/a.png", "D:\\C\\a.png", "D:/C/a.png", "\\\\server\\share\\a.png", "../x.png",
                  "assets/../../x.png", ""):
            self.assertFalse(CDB.is_relative(v), v)

    def test_anchor_tail(self):
        self.assertEqual(CDB.anchor_tails(PureWindowsPath(r"D:\data\old\C\assets\Brand\logo.png")),
                         ["data/old/C/assets/Brand/logo.png", "assets/Brand/logo.png"])
        self.assertEqual(CDB.anchor_tails(PurePosixPath("/Volumes/X/C/output/client_database/assets/d.jpg")),
                         ["output/client_database/assets/d.jpg", "assets/d.jpg"])
        self.assertEqual(CDB.anchor_tails(PurePosixPath("/tmp/nothing/here.png")), [])


@unittest.skipUnless(sys.platform == "darwin" or os.name == "nt", "the /private/var case needs a real-path alias")
class TestRealPathAlias(Base):
    def test_a_root_reached_through_an_alias_still_counts_as_inside(self):
        """macOS: /var/folders/... is /private/var/folders/...; Windows: a junction to the client folder."""
        alias = self.tmp / "alias"
        if os.name == "nt":
            import _winapi
            _winapi.CreateJunction(str(self.root), str(alias))
        else:
            os.symlink(self.root, alias)
        try:
            self.manifest(str(alias / "assets/Brand/logo.png"), str(alias / REL_LOGO))
            a = CDB.load(self.paths, "asset-manifest.json")["assets"][0]
            self.assertTrue(Path(a["file"]).is_file())
            self.assertTrue(CDB.inside_root(str(alias / "assets/Brand/logo.png"), str(self.root)) or
                            Path(a["file"]) == self.root / "assets/Brand/logo.png")
        finally:
            os.rmdir(alias) if os.name == "nt" else alias.unlink()


class TestDarwinPrivateVar(unittest.TestCase):
    def test_private_var_is_the_same_root(self):
        real = {"/var/folders/a/C": "/private/var/folders/a/C",
                "/private/var/folders/a/C/assets/x.png": "/private/var/folders/a/C/assets/x.png"}
        from lib import client_move_paths as CMP
        with mock.patch.object(CMP, "real", side_effect=lambda p: real.get(str(p), str(p))):
            self.assertTrue(CDB.inside_root("/private/var/folders/a/C/assets/x.png", "/var/folders/a/C",
                                            fold=True, sep="/"))


def json_copy(doc):
    import json
    return json.loads(json.dumps(doc))


class TestResolveConfinement(Base):
    """Review 0d84730 (After Effects loads what `resolve` gives): a value that names a place in the client never lands
    outside it, by `..` or through a link (P2-1, P3-2); a value that names no place we can place counts as missing
    (P3-3); a font role given as a file keeps its weight once the family's file is resolved (P3-1)."""

    def outside(self) -> Path:
        out = self.tmp / "outside"
        out.mkdir(exist_ok=True)
        (out / "x.ttf").write_bytes(b"ttf outside")
        return out

    def junction(self, at: Path, target: Path) -> None:
        """mklink /J at -> target; removed as a link only (os.rmdir), before tearDown's rmtree, target checked."""
        import subprocess
        r = subprocess.run(["cmd", "/c", "mklink", "/J", str(at), str(target)], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

        def unlink():                                         # called by the test itself (tearDown's rmtree is after)
            os.rmdir(at)                                      # the link only, never what it points to
            self.assertTrue((target / "x.ttf").is_file())
        self._unlink = unlink

    def test_an_anchor_tail_with_dotdot_never_leaves_the_client(self):        # P2-1
        out = self.outside()                                  # <root>\assets\..\..\outside\x.ttf exists: next to it
        self.assertTrue((self.root / "assets" / ".." / ".." / "outside" / "x.ttf").is_file())
        for v in (r"Z:\g\assets\..\..\outside\x.ttf", "/g/assets/../../outside/x.ttf"):
            got = CDB.resolve(self.root, v)
            if os.name == "nt":                               # review c84f652: its real path is not what it spells
                self.assertIsNone(got, v)
                continue
            self.assertEqual(got, v, v)                                   # never re-anchored: kept, names nothing here
            self.assertNotEqual(os.path.realpath(got), os.path.realpath(out / "x.ttf"), v)
        self.assertEqual(Path(CDB.resolve(self.root, r"Z:\Old\C\assets\Brand\logo.png")),   # a tail without `..`:
                         self.root / "assets/Brand/logo.png")                                 # re-anchored as before
        v = r"Z:\g\assets\x\..\Brand\logo.png"                         # a tail with `..` is never re-anchored, even
        self.assertEqual(CDB.resolve(self.root, v), None if os.name == "nt" else v)   # one that would stay inside
        self.assertEqual(Path(CDB.resolve(self.root, r"Z:\g\assets\..\x\assets\Brand\logo.png")),   # review d224a9a
                         self.root / "assets/Brand/logo.png")          # P3-4: a later clean tail still re-anchors

    def test_the_client_root_itself_is_no_file(self):                         # review d224a9a P3-4
        for v in (".", "./", "./.", ".\\"):
            self.assertIsNone(CDB.resolve(self.root, v), v)

    def subst(self, target: Path) -> str:
        """A free drive letter mapped to `target` with `subst`, removed again (`subst X: /d`) at cleanup."""
        import subprocess
        letter = next((c for c in "QRSTUVWXYP" if not os.path.exists(f"{c}:\\")), None)
        if letter is None:
            self.skipTest("no free drive letter for subst")
        r = subprocess.run(["subst", f"{letter}:", str(target)], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.addCleanup(lambda: subprocess.run(["subst", f"{letter}:", "/d"], capture_output=True))
        return f"{letter}:"

    @unittest.skipUnless(os.name == "nt", "device paths, admin shares, subst and a junction are Windows")
    def test_every_alias_of_a_path_follows_one_rule(self):                  # review c84f652 P2, P3-3
        """Inside or not is decided on the final real path (links, subst drives, this computer's shares, device
        prefixes and `..` followed), never on a list of spellings: an alias of a client file opens that file, one that
        really lands outside is missing, and nothing outside the client is ever a client file (inside_file)."""
        import socket
        out = self.outside()
        junc = self.root / "assets" / "junc"
        self.junction(junc, out)
        try:
            drive = os.path.splitdrive(str(self.root))[0]
            q = self.subst(self.root)
            inside = self.root / "assets" / "Brand" / "Brand-Bold.ttf"
            share = lambda host: (lambda x: f"\\\\{host}\\{drive[0]}$" + str(x)[len(drive):])
            forms = {"device ?": lambda x: "\\\\?\\" + str(x), "device .": lambda x: "\\\\.\\" + str(x),
                     "slashes //?/": lambda x: "//?/" + str(x).replace("\\", "/"),
                     "UNC device": lambda x: "\\\\?\\UNC\\localhost\\" + f"{drive[0]}$" + str(x)[len(drive):],
                     "localhost": share("localhost"), "LOCALHOST d$": lambda x: share("LOCALHOST")(x).replace(
                         f"{drive[0]}$", f"{drive[0].lower()}$"), "127.0.0.1": share("127.0.0.1"),
                     "this PC's name": share(socket.gethostname()),
                     "subst": lambda x: q + str(x)[len(str(self.root)):] if str(x).startswith(str(self.root)) else None}
            if not os.path.exists(share("localhost")(inside)):
                self.skipTest("this computer's admin share is not reachable here")
            for name, form in forms.items():
                with self.subTest(form=name):
                    got = CDB.resolve(self.root, form(inside))
                    self.assertEqual(Path(got), inside)                                   # the client's own file
                    self.assertEqual(Path(CDB.inside_file(self.root, got)), inside)
                    for bad in (junc / "x.ttf", self.root / "assets" / ".." / ".." / "outside" / "x.ttf"):
                        v = form(bad)
                        if v is None or name == "subst" and ".." in v:       # `..` can't climb above a drive root
                            continue
                        if bad == junc / "x.ttf":
                            self.assertTrue(os.path.exists(v), v)                # it really opens the outside file
                        self.assertIsNone(CDB.resolve(self.root, v), v)           # through a link or `..`: missing
                    v = form(out / "x.ttf")
                    if v is not None:                                       # plainly elsewhere: never a client file
                        self.assertIsNone(CDB.inside_file(self.root, CDB.resolve(self.root, v)), v)
                    if v is not None and name.startswith(("device", "slashes")):
                        self.assertEqual(CDB.resolve(self.root, v), v)    # a device prefix is no alias: kept as is
            self.assertIsNone(CDB.resolve(self.root, "/outside/x.ttf"))       # POSIX-rooted: this drive's \\outside
            self.assertEqual(Path(CDB.resolve(self.root, "/Volumes/Old/C/assets/Brand/logo.png")),
                             self.root / "assets/Brand/logo.png")                # ...unless it re-anchors here
            self.assertEqual(CDB.resolve(self.root, r"C:\Windows\Fonts\arial.ttf"), r"C:\Windows\Fonts\arial.ttf")
            self.assertIsNone(CDB.inside_file(self.root, r"C:\Windows\Fonts\arial.ttf"))   # kept, but no client file
        finally:
            self._unlink()

    def test_an_unreachable_share_counts_as_missing(self):                     # review c84f652 P3-5
        from lib import client_move_paths as CMP
        real = CMP.real

        def offline(p):
            if str(p).replace("/", "\\").startswith("\\\\127.0.0.2"):
                raise OSError(1231, "The network location cannot be reached")
            return real(p)
        v = "\\\\127.0.0.2\\D$\\Clients\\C\\x.png"
        with mock.patch.object(CMP, "real", side_effect=offline):
            self.assertIsNone(CDB.resolve(self.root, v))
            self.assertIsNone(CDB.inside_file(self.root, v))
            self.assertFalse(CDB.inside(self.root, v))

    def test_inside_file_is_an_existing_file_really_in_the_client(self):       # review c84f652 P2
        own = self.root / "assets" / "Brand" / "logo.png"
        self.assertEqual(CDB.inside_file(self.root, str(own)), str(own))
        self.assertIsNone(CDB.inside_file(self.root, str(self.root / "assets" / "Brand")))     # a folder
        self.assertIsNone(CDB.inside_file(self.root, str(self.root / "assets" / "gone.png")))  # missing
        out = self.outside()
        self.assertIsNone(CDB.inside_file(self.root, str(out / "x.ttf")))                      # another folder
        twin = Path(str(self.root) + " 2") / "assets" / "logo.png"                              # a name that only
        twin.parent.mkdir(parents=True)                                                         # starts like it
        twin.write_bytes(b"png")
        self.assertIsNone(CDB.inside_file(self.root, str(twin)))
        self.assertTrue(CDB.inside(self.root, str(self.root / "assets" / "gone.png")))         # inside, not there
        self.assertFalse(CDB.inside(self.root, str(out / "x.ttf")))
        for v in (None, "", 3):
            self.assertIsNone(CDB.inside_file(self.root, v))

    def test_dotdot_and_drive_relative_values_count_as_missing(self):        # P3-3
        for v in ("../../x.ttf", "..\\..\\outside\\x.ttf", "assets/../../outside/x.ttf", "C:x.ttf", "\\x.ttf"):
            self.assertIsNone(CDB.resolve(self.root, v), v)
        self.manifest("assets/Brand/logo.png", "../../logo_display.jpg")
        a = CDB.load(self.paths, "asset-manifest.json")["assets"][0]
        self.assertIsNone(a["display_derivative"])
        self.assertEqual(Path(a["file"]), self.root / "assets/Brand/logo.png")
        self.assertEqual(CDB.to_stored(self.root, "../../x.ttf"), "../../x.ttf")     # a writer keeps it as it is
        for v in ("", None, 3):
            self.assertEqual(CDB.resolve(self.root, v), v)

    @unittest.skipUnless(os.name == "nt", "a junction (mklink /J) is Windows")
    def test_a_value_through_a_junction_out_of_the_client_is_refused(self):  # P3-2
        out = self.outside()
        junc = self.root / "assets" / "junc"
        self.junction(junc, out)
        try:
            self.assertTrue((junc / "x.ttf").is_file())                      # the link really reaches outside
            self.assertIsNone(CDB.resolve(self.root, "assets/junc/x.ttf"))
            self.assertIsNone(CDB.resolve(self.root, str(junc / "x.ttf")))   # the absolute form inside by name
            self.assertEqual(CDB.resolve(self.root, r"Z:\Old\C\assets\junc\x.ttf"), r"Z:\Old\C\assets\junc\x.ttf")
            self.assertEqual(Path(CDB.resolve(self.root, "assets/Brand/Brand-Bold.ttf")),
                             self.root / "assets/Brand/Brand-Bold.ttf")      # a real file inside: as before
            write_json(self.db / "branding/typography.json", {"families": {"B": {"weights": [
                {"style": "Bold", "file": "assets/junc/x.ttf", "postscript_name": "B-Bold"}]}}})
            self.assertIsNone(CDB.load(self.paths, "branding/typography.json")["families"]["B"]["weights"][0]["file"])
        finally:
            self._unlink()
        self.assertTrue((out / "x.ttf").is_file())

    def typography(self, file_of, role_file, first=None, as_string=False):
        fonts = self.root / "assets" / "Fonts"
        fonts.mkdir(exist_ok=True)
        for n in ("B-Regular", "B-Bold"):
            (fonts / f"{n}.ttf").write_bytes(b"ttf")
        fams = dict(first or {})
        fams["B"] = {"weights": [{"style": "Regular", "file": file_of("B-Regular"), "postscript_name": "B-Regular"},
                                 {"style": "Bold", "file": file_of("B-Bold"), "postscript_name": "B-Bold"}]}
        write_json(self.db / "branding/typography.json", {"families": fams, "roles": {
            "body": role_file if as_string else {"file": role_file}}})
        from lib import font_roles
        return font_roles.resolve(CDB.load(self.paths, "branding/typography.json"), "body")

    def test_a_role_given_as_a_file_keeps_its_weight(self):                  # P3-1
        rel = lambda n: f"assets/Fonts/{n}.ttf"
        old = lambda n: rf"Z:\Old\Dr Test\assets\Fonts\{n}.ttf"           # a 2.x value from the folder it was copied from
        for file_of, role in ((rel, "assets/Fonts/B-Bold.ttf"), (old, old("B-Bold")), (rel, old("B-Bold")),
                              (old, "assets\\Fonts\\B-Bold.ttf"), (rel, "B-Bold.ttf"),
                              (rel, "ASSETS/FONTS/B-BOLD.TTF")):                  # names compare case folded
            with self.subTest(role=role):
                face = self.typography(file_of, role)
                self.assertEqual(face["ps"], "B-Bold")
                self.assertEqual(face["source"], "typography.json roles")
                shutil.rmtree(self.root / "assets" / "Fonts")
        face = self.typography(rel, "assets/Other/B-Bold.ttf")             # another folder's file of that name: no
        self.assertEqual(face["ps"], "B-Regular")
        self.assertEqual(face["source"], "default")

    def test_a_role_is_a_file_only_with_a_folder_and_a_font_extension(self):  # review c84f652 P3-2
        rel = lambda n: f"assets/Fonts/{n}.ttf"
        face = self.typography(rel, "Bold/Italic", as_string=True)          # a style with a slash: still a style
        self.assertEqual(face["ps"], "B-Bold")
        shutil.rmtree(self.root / "assets" / "Fonts")
        t = CDB.load(self.paths, "branding/typography.json")
        self.assertEqual(t["roles"]["body"], "Bold/Italic")
        for role in ("assets/Fonts", "assets/Fonts/B-Bold"):                  # no font extension: left as written
            write_json(self.db / "branding/typography.json", {"families": {}, "roles": {"body": {"file": role}}})
            self.assertEqual(CDB.load(self.paths, "branding/typography.json")["roles"]["body"]["file"], role)
        write_json(self.db / "branding/typography.json", {"families": {}, "roles": {"body": {"file": "B-Bold.TTF"}}})
        self.assertEqual(CDB.load(self.paths, "branding/typography.json")["roles"]["body"]["file"], "B-Bold.TTF")
        write_json(self.db / "branding/typography.json", {"families": {}, "roles": {"body": "assets\\Fonts\\B.OTF"}})
        self.assertEqual(Path(CDB.load(self.paths, "branding/typography.json")["roles"]["body"]),
                         self.root / "assets" / "Fonts" / "B.OTF")

    def test_a_bare_font_name_in_two_folders_names_no_face(self):              # review c84f652 P3-5
        rel = lambda n: f"assets/Fonts/{n}.ttf"
        (self.root / "assets" / "Old").mkdir(parents=True)
        (self.root / "assets" / "Old" / "B-Bold.ttf").write_bytes(b"ttf")
        old = {"Old": {"weights": [{"style": "Black", "file": "assets/Old/B-Bold.ttf", "postscript_name": "Old-Black"}]}}
        face = self.typography(rel, "B-Bold.ttf", first=old)                 # which B-Bold.ttf? ambiguous: none
        self.assertEqual((face["ps"], face["source"]), ("B-Regular", "default"))
        shutil.rmtree(self.root / "assets" / "Fonts")
        same = {"Copy": {"weights": [{"style": "Bold", "file": "assets/Fonts/B-Bold.ttf", "postscript_name": "B-Bold"}]}}
        face = self.typography(rel, "B-Bold.ttf", first=same)                # one file listed twice: that file
        self.assertEqual((face["ps"], face["source"]), ("B-Bold", "typography.json roles"))
        shutil.rmtree(self.root / "assets" / "Fonts")
        face = self.typography(rel, "assets/Old/B-Bold.ttf", first=old)      # a path is exact
        self.assertEqual(face["ps"], "Old-Black")

    def test_migrate_rewrites_a_role_file_like_saving_does(self):             # review c84f652 P3-4
        fonts = self.root / "assets" / "Fonts"
        fonts.mkdir()
        (fonts / "B-Bold.ttf").write_bytes(b"ttf")
        old = r"Z:\Old\C"
        write_json(self.db / "branding/typography.json", {"families": {"B": {"weights": [
            {"style": "Bold", "file": "assets/Fonts/B-Bold.ttf", "postscript_name": "B-Bold"}]}},
            "roles": {"body": {"file": old + r"\assets\Fonts\B-Bold.ttf"}, "small": "Regular"}})
        rep = CDB.migrate(self.paths, old_roots=[old], dry_run=True)
        self.assertEqual(rep["changed"], [{"file": "branding/typography.json", "values": 1}], rep)
        self.assertEqual(rep["kept_absolute"], [])
        stored = CDB.stored(self.root, "branding/typography.json", CDB.load(self.paths, "branding/typography.json"))
        self.assertEqual(stored["roles"], {"body": {"file": "assets/Fonts/B-Bold.ttf"}, "small": "Regular"})

    def test_the_brief_says_nothing_about_roles_written_as_files(self):        # review c84f652 P3-1
        from lib import client_brief
        roles = {"body": {"file": "assets/Fonts/B-Bold.ttf"}, "headline": "Black", "caption": "assets/Fonts/B.otf"}
        write_json(self.db / "branding/typography-roles.json", {"roles": roles})
        write_json(self.db / "branding/typography.json", {"families": {}, "roles": CDB.stored(
            self.root, "branding/typography.json", {"roles": json_copy(roles)})["roles"]})   # as `reel client-db` does
        self.assertFalse([n for n in client_brief._notes(self.paths) if "typography-roles.json" in n])
        write_json(self.db / "branding/typography-roles.json",
                   {"roles": dict(roles, body={"file": str(self.root / "assets" / "Fonts" / "B-Bold.ttf")})})
        self.assertFalse([n for n in client_brief._notes(self.paths) if "typography-roles.json" in n])   # same file
        write_json(self.db / "branding/typography-roles.json", {"roles": dict(roles, body={"file": "assets/x.ttf"})})
        self.assertTrue([n for n in client_brief._notes(self.paths) if "typography-roles.json" in n])  # really new

    def test_a_role_file_names_exactly_one_face(self):                        # review d224a9a P3-1
        rel = lambda n: f"assets/Fonts/{n}.ttf"
        copy = {"Copy": {"weights": [{"style": "Black", "file": "output/client_database/assets/Fonts/B-Bold.ttf",
                                      "postscript_name": "Copy-Black"}]}}    # same tail, listed first
        (self.db / "assets" / "Fonts").mkdir(parents=True)
        (self.db / "assets" / "Fonts" / "B-Bold.ttf").write_bytes(b"ttf")
        face = self.typography(rel, "assets/Fonts/B-Bold.ttf", first=copy)
        self.assertEqual(face["ps"], "B-Bold")
        shutil.rmtree(self.root / "assets" / "Fonts")
        face = self.typography(rel, "output/client_database/assets/Fonts/B-Bold.ttf", first=copy)
        self.assertEqual(face["ps"], "Copy-Black")                        # that very file: the copy's face
        shutil.rmtree(self.root / "assets" / "Fonts")
        for role in ("assets/Old/assets/Fonts/B-Bold.ttf", "data/x/assets/Fonts/B-Bold.ttf",
                     "output/client_database/assets/Fonts/B-Bold.ttf"):  # nested anchors: never the root file
            with self.subTest(role=role):
                face = self.typography(rel, role)
                self.assertEqual(face["ps"], "B-Regular")
                self.assertEqual(face["source"], "default")
                shutil.rmtree(self.root / "assets" / "Fonts")
        face = self.typography(rel, "assets/Fonts/B-Bold.ttf", as_string=True)   # a role given as a path string
        self.assertEqual(face["ps"], "B-Bold")
        stored = CDB.stored(self.root, "branding/typography.json", CDB.load(self.paths, "branding/typography.json"))
        self.assertEqual(stored["roles"]["body"], "assets/Fonts/B-Bold.ttf")   # what a writer / a hash sees: as stored
        self.assertEqual(stored["families"]["B"]["weights"][1]["file"], "assets/Fonts/B-Bold.ttf")


    def test_a_cached_reference_with_a_sheet_we_cannot_place_is_analysed_again(self):
        """`resolve` may now give None (P3-3): the reference cache's own check treats that sheet as missing."""
        from lib import ref_analysis
        ref = self.root / "data" / "References" / "ref.mp4"
        ref.parent.mkdir(parents=True)
        ref.write_bytes(b"r" * 64)
        st = ref.stat()
        key = CDB.to_stored(self.root, str(ref.resolve())) + f"|{st.st_size}|{int(st.st_mtime)}"
        entry = {"video": "data/References/ref.mp4", "duration_s": 1.0, "cut_count": 0, "cuts_per_minute": 0.0,
                 "shot_stats": {}, "first_cut_s": None, "contact_sheets": ["../../sheet_00.jpg"],
                 "shot_durations_s": [1.0]}
        write_json(self.db / "reference_analysis" / "cache.json", {key: entry})
        fresh = dict(entry, contact_sheets=[])
        with mock.patch.object(ref_analysis, "analyze_reference", return_value=fresh) as again, \
                mock.patch.object(ref_analysis, "log"):
            ref_analysis.analyze_all(self.paths, [ref], {})
        self.assertEqual(again.call_count, 1)


class TestReaders(Base):
    """The readers swapped to client_db.load find the files of a client whose database stores relative paths."""

    def test_publish_logo(self):
        self.manifest("assets/Brand/logo.png", REL_LOGO)
        from lib import publish
        src = Path(publish.__file__).read_text(encoding="utf-8")
        self.assertIn('client_db.load(', src)
        self.assertNotIn('read_json(ep.client_db / "asset-manifest.json"', src)

    def test_ps_builder_and_qc_use_load(self):
        for mod in ("ps_builder", "qc"):
            src = (SK / "engine/reel/lib" / f"{mod}.py").read_text(encoding="utf-8")
            self.assertIn("client_db.load(", src, mod)
            self.assertNotRegex(src, r'read_json\(paths\.client_db / "(asset-manifest|branding/typography)\.json"', mod)


if __name__ == "__main__":
    unittest.main()
