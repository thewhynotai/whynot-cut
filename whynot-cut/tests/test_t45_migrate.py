# SPDX-License-Identifier: GPL-3.0-or-later
# © 2026 The Why Not AI (thewhynot.ai)
"""3.0 Phase 4 T4.5 (part B) — `client_db.migrate`: an existing database with absolute paths is rewritten in the
stored (root-relative) form only under the client's writer lock held by this session, atomically and never through a
link, with each file's modification time kept; a reader never writes. Case list: BL-14 cases.md M1–M7.
Run:  bash tools/test.sh -p test_t45_migrate.py
"""
import sys as _sys
_sys.dont_write_bytecode = True  # keep the plugin folder free of __pycache__
import _isolation  # noqa: F401,E402  G79: sandbox the engine home first (tests/_isolation.py)
import json
import os
import shutil
import tempfile
import time
import unittest
from pathlib import Path

sys = _sys
SK = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SK / "engine" / "reel"))

from lib import client_db as CDB, writer_lock  # noqa: E402
from lib.common import Paths, read_json, write_json  # noqa: E402
from lib.errors import Guidance  # noqa: E402

IS_WIN = os.name == "nt"
OLD_T = time.time() - 86400


def link_dir(target, at):
    if IS_WIN:
        import _winapi
        _winapi.CreateJunction(str(target), str(at))
    else:
        os.symlink(str(target), str(at), target_is_directory=True)


def unlink_links(top: Path):
    for d, dirs, files in os.walk(top):
        for n in dirs + files:
            p = os.path.join(d, n)
            if os.path.islink(p) or (IS_WIN and os.path.isjunction(p)):
                os.rmdir(p) if IS_WIN and os.path.isdir(p) else os.unlink(p)


def state(f: Path):
    st = os.stat(f)
    return f.read_bytes(), st.st_mtime_ns


class Base(unittest.TestCase):
    NAME = "عميل جديد Client"

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.root = self.tmp / self.NAME
        for d in ("assets/Brand", "assets/Fonts", "data/References", "output/client_database/assets/derivatives",
                  "output/client_database/branding", "output/client_database/reference_analysis/ref/cuts"):
            (self.root / d).mkdir(parents=True)
        for rel in ("assets/Brand/logo.png", "assets/Fonts/B.ttf", "data/References/ref.mp4",
                    "output/client_database/assets/derivatives/logo_alpha.png",
                    "output/client_database/reference_analysis/ref/sheet_00.jpg"):
            (self.root / rel).write_bytes(b"x")
        self.db = self.root / "output/client_database"
        self.env = os.environ.get(writer_lock.ENV)

    def tearDown(self):
        if self.env is None:
            os.environ.pop(writer_lock.ENV, None)
        else:
            os.environ[writer_lock.ENV] = self.env
        unlink_links(self.tmp)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def a(self, rel, base=None):
        return str((base or self.root).joinpath(*rel.split("/")))

    def absolute_db(self, base=None):
        """A 2.x / pre-T4.5 database: every path absolute (of `base`, the folder it was written in)."""
        a = lambda r: self.a(r, base)
        man = {"assets": [{"rel": "assets/Brand/logo.png", "file": a("assets/Brand/logo.png"), "category": "logo",
                           "display_derivative": a("output/client_database/assets/derivatives/logo_alpha.png")}],
               "policy": ["keep"]}
        write_json(self.db / "asset-manifest.json", man)
        write_json(self.db / "assets/asset-manifest.json", man)
        write_json(self.db / "branding/typography.json", {"families": {"B": {"weights": [
            {"file": a("assets/Fonts/B.ttf"), "postscript_name": "B-Bold"}]}},
            "missing_or_uninstalled": [a("assets/Fonts/B.ttf")], "roles": {"caption": "B-Bold"}})
        entry = {"video": a("data/References/ref.mp4"), "duration_s": 2.0,
                 "contact_sheets": [a("output/client_database/reference_analysis/ref/sheet_00.jpg")],
                 "cut_frames": [a("output/client_database/reference_analysis/ref/cuts/t0001.00.jpg")]}
        write_json(self.db / "reference_analysis/cache.json", {f"{a('data/References/ref.mp4')}|1|2": entry})
        write_json(self.db / "reference_analysis/reference-measurements.json",
                   {"references": [{k: entry[k] for k in ("video", "duration_s", "contact_sheets")}], "aggregate": {}})
        write_json(self.db / "reference_analysis/ref/measurements.json", dict(entry, note="n"))
        write_json(self.db / "branding/brand-tokens.json", {"roles": {}})
        for f in self.db.rglob("*.json"):
            os.utime(f, (OLD_T, OLD_T))

    def hold(self, root=None):
        lk = writer_lock.acquire(root or self.root, "reel client-move")
        self.addCleanup(lambda: (lk.release(), writer_lock.release_own(root or self.root, writer_lock.session_id())))
        return lk


class TestNeedsTheLock(Base):
    def test_without_the_lock_nothing_is_written(self):
        self.absolute_db()
        before = {f: state(f) for f in self.db.rglob("*.json")}
        with self.assertRaises(Guidance) as cm:
            CDB.migrate(Paths(self.root))
        self.assertIn("writer lock", str(cm.exception))
        self.assertEqual({f: state(f) for f in self.db.rglob("*.json")}, before)

    def test_another_sessions_lock_refuses_too(self):
        self.absolute_db()
        (self.root / "output/.whynot-lock").write_text(json.dumps({"session_id": "someone-else", "pid": os.getpid()}),
                                                       encoding="utf-8")
        before = state(self.db / "asset-manifest.json")
        with self.assertRaises(Guidance):
            CDB.migrate(Paths(self.root))
        self.assertEqual(state(self.db / "asset-manifest.json"), before)

    def test_a_dry_run_needs_no_lock_and_writes_nothing(self):
        self.absolute_db()
        before = {f: state(f) for f in self.db.rglob("*.json")}
        rep = CDB.migrate(Paths(self.root), dry_run=True)
        self.assertEqual(len(rep["changed"]), 6)
        self.assertEqual({f: state(f) for f in self.db.rglob("*.json")}, before)


class TestMigrate(Base):
    def test_every_path_carrying_file_becomes_relative_and_keeps_its_time(self):
        self.absolute_db()
        self.hold()
        rep = CDB.migrate(Paths(self.root))
        self.assertEqual(rep["errors"], [])
        self.assertEqual(sorted(c["file"] for c in rep["changed"]),
                         sorted(["asset-manifest.json", "assets/asset-manifest.json", "branding/typography.json",
                                 "reference_analysis/cache.json", "reference_analysis/reference-measurements.json",
                                 "reference_analysis/ref/measurements.json"]))
        man = read_json(self.db / "asset-manifest.json")["assets"][0]
        self.assertEqual((man["file"], man["display_derivative"]),
                         ("assets/Brand/logo.png", "output/client_database/assets/derivatives/logo_alpha.png"))
        self.assertEqual(read_json(self.db / "asset-manifest.json")["policy"], ["keep"])        # other keys untouched
        typ = read_json(self.db / "branding/typography.json")
        self.assertEqual(typ["families"]["B"]["weights"][0], {"file": "assets/Fonts/B.ttf", "postscript_name": "B-Bold"})
        self.assertEqual(typ["missing_or_uninstalled"], ["assets/Fonts/B.ttf"])
        self.assertEqual(typ["roles"], {"caption": "B-Bold"})
        idx = read_json(self.db / "reference_analysis/cache.json")
        self.assertEqual(list(idx), ["data/References/ref.mp4|1|2"])
        e = idx["data/References/ref.mp4|1|2"]
        self.assertEqual(e["contact_sheets"], ["output/client_database/reference_analysis/ref/sheet_00.jpg"])
        self.assertEqual(e["cut_frames"], ["output/client_database/reference_analysis/ref/cuts/t0001.00.jpg"])
        self.assertEqual(read_json(self.db / "reference_analysis/ref/measurements.json")["note"], "n")
        for f in self.db.rglob("*.json"):
            self.assertEqual(int(f.stat().st_mtime), int(OLD_T), f)                # `reel next` compares times
        self.assertEqual(sorted(p.name for p in self.db.rglob("*.tmp")), [])

    def test_nothing_to_change_is_not_rewritten_and_a_second_run_is_a_no_op(self):
        self.absolute_db()
        self.hold()
        CDB.migrate(Paths(self.root))
        before = {f: (state(f), os.stat(f).st_ino) for f in self.db.rglob("*.json")}
        rep = CDB.migrate(Paths(self.root))
        self.assertEqual(rep["changed"], [])
        self.assertEqual(len(rep["unchanged"]), 6)
        self.assertEqual({f: (state(f), os.stat(f).st_ino) for f in self.db.rglob("*.json")}, before)

    def test_values_from_an_old_root_and_values_kept(self):
        old = self.tmp / "data" / "Old Name"                     # the old root itself under a folder named "data"
        self.absolute_db(base=old)
        fonts = str(self.tmp / "Windows" / "Fonts" / "B.ttf")
        typ = read_json(self.db / "branding/typography.json")
        typ["missing_or_uninstalled"].append(fonts)             # an OS font: outside every root, kept
        write_json(self.db / "branding/typography.json", typ)
        self.hold()
        rep = CDB.migrate(Paths(self.root), old_roots=[str(old)])
        self.assertEqual(rep["errors"], [])
        self.assertEqual(read_json(self.db / "asset-manifest.json")["assets"][0]["file"], "assets/Brand/logo.png")
        self.assertEqual(read_json(self.db / "branding/typography.json")["missing_or_uninstalled"],
                         ["assets/Fonts/B.ttf", fonts])
        self.assertEqual(rep["kept_absolute"], [{"file": "branding/typography.json", "value": fonts}])

    def test_a_link_is_never_written_through(self):
        self.absolute_db()
        outside = self.tmp / "outside"
        outside.mkdir()
        shutil.move(str(self.db / "branding"), str(outside / "branding"))
        link_dir(outside / "branding", self.db / "branding")
        before = state(outside / "branding/typography.json")
        self.hold()
        rep = CDB.migrate(Paths(self.root))
        self.assertEqual([e["file"] for e in rep["errors"]], ["branding/typography.json"])
        self.assertIn("link", rep["errors"][0]["why"])
        self.assertEqual(state(outside / "branding/typography.json"), before)
        self.assertEqual(read_json(self.db / "asset-manifest.json")["assets"][0]["file"], "assets/Brand/logo.png")

    def test_a_damaged_file_is_listed_and_left_alone(self):
        self.absolute_db()
        bad = self.db / "branding/typography.json"
        bad.write_text("{not json", encoding="utf-8")
        before = state(bad)
        self.hold()
        rep = CDB.migrate(Paths(self.root))
        self.assertEqual([e["file"] for e in rep["errors"]], ["branding/typography.json"])
        self.assertEqual(state(bad), before)
        self.assertEqual(len(rep["changed"]), 5)

    def test_load_never_writes(self):
        self.absolute_db()
        before = {f: state(f) for f in self.db.rglob("*.json")}
        for rel in CDB.path_files(self.db):
            CDB.load(Paths(self.root), rel)
        self.assertEqual({f: state(f) for f in self.db.rglob("*.json")}, before)

    def test_cache_key_collision_keeps_the_existing_relative_entry(self):
        self.absolute_db()
        idx = read_json(self.db / "reference_analysis/cache.json")
        idx["data/References/ref.mp4|1|2"] = {"video": "data/References/ref.mp4", "contact_sheets": [], "mine": 1}
        write_json(self.db / "reference_analysis/cache.json", idx)
        self.hold()
        CDB.migrate(Paths(self.root))
        self.assertEqual(read_json(self.db / "reference_analysis/cache.json"),
                         {"data/References/ref.mp4|1|2": {"video": "data/References/ref.mp4", "contact_sheets": [],
                                                          "mine": 1}})


if __name__ == "__main__":
    unittest.main()
