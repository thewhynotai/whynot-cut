# SPDX-License-Identifier: GPL-3.0-or-later
# © 2026 The Why Not AI (thewhynot.ai)
"""3.0 Phase 4 T4.5 (part B) — `lib/client_move.py`: `reel client-move` (the whole client to another place, times
kept, checked, database rewritten; the old folder left in place), `reel client-clone` (a new independent client from
the brand database, no media) and the rewrite-only "already moved" mode. Links are recorded and recreated, never
followed; every run is a dry run until apply; a failed copy is removed again; projects naming the old folder are
listed with their fix. Case list: BL-14 cases.md V1–V12, C1–C3, A1–A2.
Run:  bash tools/test.sh -p test_t45_client_move.py
"""
import sys as _sys
_sys.dont_write_bytecode = True  # keep the plugin folder free of __pycache__
import _isolation  # noqa: F401,E402  G79: sandbox the engine home first (tests/_isolation.py)
import gzip
import hashlib
import json
import os
import shutil
import stat
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

sys = _sys
SK = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SK / "engine" / "reel"))

from lib import client_db as CDB, client_move as CM, writer_lock  # noqa: E402
from lib.common import Paths, read_json, write_json  # noqa: E402
from lib.errors import Guidance  # noqa: E402

IS_WIN = os.name == "nt"
T0 = time.time() - 7 * 86400


def link_dir(target, at):
    if IS_WIN:
        import _winapi
        _winapi.CreateJunction(str(target), str(at))
    else:
        os.symlink(str(target), str(at), target_is_directory=True)


def can_symlink() -> bool:
    d = tempfile.mkdtemp()
    try:
        os.symlink("x", os.path.join(d, "l"))
        return True
    except (OSError, NotImplementedError):
        return False
    finally:
        shutil.rmtree(d, ignore_errors=True)


def is_link(p) -> bool:
    return os.path.islink(p) or (IS_WIN and os.path.isjunction(p))


def unlink_links(top: Path):
    for d, dirs, files in os.walk(top):
        for n in dirs + files:
            p = os.path.join(d, n)
            if is_link(p):
                os.rmdir(p) if IS_WIN and os.path.isdir(p) else os.unlink(p)


def tree(top: Path) -> dict:
    """rel -> (kind, sha1 or link target, mtime_ns), never following a link."""
    out = {}
    for d, dirs, files in os.walk(top):
        for n in list(dirs) + files:
            p = os.path.join(d, n)
            rel = os.path.relpath(p, top).replace("\\", "/")
            if is_link(p):
                out[rel] = ("link", os.readlink(p), None)
                if n in dirs:
                    dirs.remove(n)
            elif os.path.isdir(p):
                out[rel] = ("dir", None, None)
            else:
                out[rel] = ("file", hashlib.sha1(Path(p).read_bytes()).hexdigest(), os.stat(p).st_mtime_ns)
    for rel, v in list(out.items()):
        if v[0] == "dir":
            out[rel] = ("dir", None, os.stat(top / rel).st_mtime_ns)
    return out


def make_client(parent: Path, name: str, steps: bool = True) -> Path:
    """A client the pipeline worked on: database with ABSOLUTE paths (as written before T4.5), a clip whose steps all
    ran in order (times one minute apart), a Premiere project naming the folder, the lease and lock files."""
    root = parent / name
    files = {
        "assets/Brand/logo.png": b"png", "assets/Fonts/B.ttf": b"ttf", "data/Raw/clip 1.mp4": b"m" * 5000,
        "data/References/ref.mp4": b"r" * 300, "data/notes.lock": b"editor's own file",
        "output/client_database/assets/derivatives/logo_alpha.png": b"d",
        "output/client_database/branding/brand-tokens.json": b'{"roles": {"primary": {"hex": "#112233"}}}',
        "output/client_database/profile/client-profile.md": "# ملف العميل\n".encode("utf-8"),
        "output/client_database/reference_style/editing-style.json": b"{}",
        "output/client_database/reel-profile/profile.json": b'{"id": "acme"}',
        "output/client_database/reference_analysis/ref/sheet_00.jpg": b"j",
        "output/.whynot-lock": b'{"session_id": "x"}', "output/projects/R01/project-status.json.lock": b"",
        ".whynot-client": b'{"whynot_client": 1, "created": "2026-01-01T00:00:00+0000", "prefix": "ACME"}\n',
        ".claude/whynot-cut.local.md": b"---\nmagnific_api_key: secret\n---\n",
    }
    for rel, data in files.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)
    a = lambda r: str(root.joinpath(*r.split("/")))
    db = root / "output/client_database"
    man = {"assets": [{"rel": "assets/Brand/logo.png", "file": a("assets/Brand/logo.png"), "category": "logo",
                       "display_derivative": a("output/client_database/assets/derivatives/logo_alpha.png")}]}
    write_json(db / "asset-manifest.json", man)
    write_json(db / "assets/asset-manifest.json", man)
    write_json(db / "branding/typography.json", {"families": {"B": {"weights": [{"file": a("assets/Fonts/B.ttf")}]}},
                                                 "missing_or_uninstalled": []})
    write_json(db / "client-database-status.json",                   # 2.x/3.0 messages embed a list's repr
               {"issues": [f"Fonts not installed (hint): {[a('assets/Fonts/B.ttf')]}"]})
    write_json(db / "reference_analysis/cache.json", {f"{a('data/References/ref.mp4')}|300|5": {
        "video": a("data/References/ref.mp4"), "contact_sheets": [a("output/client_database/reference_analysis/ref/sheet_00.jpg")]}})
    write_json(root / "output/discovery/input-inventory.json", {"files": [
        {"rel": "data/Raw/clip 1.mp4", "path": a("data/Raw/clip 1.mp4"), "kind": "video", "role": "raw"}]})
    t = T0
    for f in sorted(root.rglob("*")):
        if f.is_file():
            os.utime(f, (t, t))
    if steps:
        p = Paths(root, "R01")
        order = ["00_inputs/preflight.json", "02_transcription/transcript.json", "06_audio/dialogue/pauses.json",
                 "01_analysis/edit-decisions.json", "01_analysis/timeline-spec.json",
                 "08_quality_control/previews/_contact_sheet.jpg", "08_quality_control/preview/R01_preview.mp4",
                 "07_premiere/project/R01_EDIT.prproj", "08_quality_control/visual-verification.json",
                 "08_quality_control/qc-results.json", "09_handoff/README.md"]
        for i, rel in enumerate(order):
            f = p.p(rel)
            f.parent.mkdir(parents=True, exist_ok=True)
            if rel.endswith(".prproj"):
                f.write_bytes(gzip.compress(f'<Project><Media path="{a("data/Raw/clip 1.mp4")}"/></Project>'.encode()))
            else:
                f.write_text(json.dumps({"media": a("data/Raw/clip 1.mp4")}) if rel.endswith(".json") else "x",
                             encoding="utf-8")
            os.utime(f, (T0 + 60 * (i + 1), T0 + 60 * (i + 1)))
        from urllib.parse import quote
        url = "file://localhost" + quote("/" + a("data/Raw/clip 1.mp4").replace("\\", "/").lstrip("/"), safe="/:")
        extra = {"07_premiere/R01_interchange.xml": f"<pathurl>{url}</pathurl>",
                 "08_quality_control/qc-report.md": f"Clip: `{a('data/Raw/clip 1.mp4')}`\nSibling: {root}2\\x.mp4\n",
                 "logs/pipeline.log": f"[t] ran preflight on {a('data/Raw/clip 1.mp4')}\n",
                 "09_handoff/delivery.json": json.dumps({"sent": a("data/Raw/clip 1.mp4")})}
        for rel, text in extra.items():
            f = p.p(rel)
            f.parent.mkdir(parents=True, exist_ok=True)
            f.write_text(text, encoding="utf-8")
            os.utime(f, (T0 + 900, T0 + 900))
    return root


class Base(unittest.TestCase):
    SRC = "Acme عميل"
    DST = "Moved نقل"

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.src = make_client(self.tmp, self.SRC)
        self.dest = self.tmp / "E drive" / self.DST
        self.dest.parent.mkdir()
        self.env = os.environ.get(writer_lock.ENV)

    def tearDown(self):
        if self.env is None:
            os.environ.pop(writer_lock.ENV, None)
        else:
            os.environ[writer_lock.ENV] = self.env
        unlink_links(self.tmp)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def hold(self, root=None):
        root = root or self.src
        (root / "output/.whynot-lock").unlink(missing_ok=True)       # the fixture's stale record
        lk = writer_lock.acquire(root, "reel client-move --apply")
        self.addCleanup(lambda: (lk.release(), writer_lock.release_own(root, writer_lock.session_id())))
        return lk

    def src_tree(self):
        t = tree(self.src)
        t.pop("output/.whynot-lock", None)
        t.pop("output/logs/pipeline.log", None)
        for d in ("output", "output/logs"):                  # the test's own lease comes and goes there
            if d in t:
                t[d] = ("dir", None, None)
        return t


class TestDryRun(Base):
    def test_default_is_a_dry_run_that_creates_nothing(self):
        before = self.src_tree()
        doc = CM.move(self.src, self.dest)
        self.assertFalse(doc["applied"])
        self.assertNotIn("refused", doc)
        self.assertFalse(self.dest.exists())
        self.assertEqual(self.src_tree(), before)
        self.assertGreater(doc["files"], 20)
        self.assertIn("output/.whynot-lock", doc["excluded"])
        self.assertIn("output/projects/R01/project-status.json.lock", doc["excluded"])
        self.assertEqual([p["file"] for p in doc["outside_database"]["projects"]],
                         ["output/projects/R01/07_premiere/project/R01_EDIT.prproj"])
        self.assertIn("output/discovery/input-inventory.json", [r["file"] for r in doc["outside_database"]["rewritten"]])
        self.assertIn("dry run", doc["next"])

    def test_apply_needs_this_sessions_lock(self):
        with self.assertRaises(Guidance):
            CM.move(self.src, self.dest, apply=True)
        self.assertFalse(self.dest.exists())


class TestMove(Base):
    def moved(self):
        before = self.src_tree()
        self.hold()
        doc = CM.move(self.src, self.dest, apply=True)
        self.assertTrue(doc.get("applied"), doc)
        self.assertEqual(self.src_tree(), before)                              # the old folder: untouched
        return doc

    def test_copy_keeps_times_and_rewrites_the_database(self):
        doc = self.moved()
        src_t, dst_t = self.src_tree(), tree(self.dest)
        self.assertEqual(doc["mtime_rounded"], [])
        changed = {r["file"] for r in doc["outside_database"]["rewritten"]} | \
            {"output/client_database/" + c["file"] for c in doc["database"]["changed"]}
        self.assertIn("output/client_database/asset-manifest.json", changed)
        for rel, (kind, digest, mns) in src_t.items():
            if rel == "output/projects/R01/project-status.json.lock":
                continue
            self.assertIn(rel, dst_t)
            self.assertEqual(dst_t[rel][0], kind, rel)
            if rel not in changed:
                self.assertEqual(dst_t[rel][1], digest, rel)
            if kind in ("file", "dir") and mns is not None:
                self.assertEqual(dst_t[rel][2], mns, rel)                     # rewritten files keep their time too
        self.assertNotIn("output/.whynot-lock", dst_t)                       # no lease carried, none left behind
        self.assertNotIn("output/projects/R01/project-status.json.lock", dst_t)
        self.assertIn("data/notes.lock", dst_t)                               # the editor's own file IS copied
        self.assertIn(".whynot-client", dst_t)                                # a move keeps the client's identity
        self.assertNotIn(CM.INCOMPLETE, dst_t)
        man = read_json(self.dest / "output/client_database/asset-manifest.json")["assets"][0]
        self.assertEqual(man["file"], "assets/Brand/logo.png")
        idx = read_json(self.dest / "output/client_database/reference_analysis/cache.json")
        self.assertEqual(list(idx), ["data/References/ref.mp4|300|5"])
        self.assertIn("left in place", doc["old_folder"])
        self.assertEqual(int(os.stat(self.dest / "output/client_database/asset-manifest.json").st_mtime), int(T0))

    def test_reel_next_at_the_new_place_shows_no_stale_flags(self):
        import cli
        from lib import ref_style
        old = cli.next_doc(Paths(self.src, "R01"))
        self.moved()
        new = cli.next_doc(Paths(self.dest, "R01"))
        self.assertEqual(old["stale"], [])
        self.assertEqual(new["stale"], [])
        self.assertEqual(new["next"], old["next"])
        self.assertEqual(new["remaining"], old["remaining"])
        self.assertEqual(ref_style.state(self.dest)["fingerprint"], ref_style.state(self.src)["fingerprint"])

    def test_nothing_under_the_copy_points_at_the_old_folder(self):
        """REL-PREVIEW acceptance: no path in a JSON, MD or XML under the copy points outside it, except the files an
        approval or sign-off is bound to (kept, listed with why: the executor's question in BL-14); logs and projects
        are listed with what happens to them."""
        doc = self.moved()
        out = doc["outside_database"]
        kept = {k["file"]: k["why"] for k in out["kept"]}
        self.assertEqual(sorted(k for k, w in kept.items() if "approval" in w),
                         ["output/projects/R01/01_analysis/timeline-spec.json",
                          "output/projects/R01/06_audio/dialogue/pauses.json"])
        self.assertEqual(sorted(k for k, w in kept.items() if "approval" not in w),
                         ["output/projects/R01/09_handoff/delivery.json", "output/projects/R01/logs/pipeline.log"])
        self.assertIn("not on the list", kept["output/projects/R01/09_handoff/delivery.json"])
        olds = {str(self.src), str(self.src).replace("\\", "/"), json.dumps(str(self.src))[1:-1],
                json.dumps(str(self.src), ensure_ascii=False)[1:-1]}
        from urllib.parse import quote
        olds.add(quote("/" + str(self.src).replace("\\", "/").lstrip("/"), safe="/:"))
        import re
        checked = 0
        for f in (self.dest / "output").rglob("*"):
            if f.suffix in (".json", ".md", ".xml") and f.relative_to(self.dest).as_posix() not in kept:
                text, checked = f.read_text(encoding="utf-8"), checked + 1
                for o in olds:
                    self.assertIsNone(re.search(re.escape(o) + CM._END, text, re.IGNORECASE), (f, o))
        self.assertGreater(checked, 15)
        inv = read_json(self.dest / "output/discovery/input-inventory.json")["files"][0]["path"]
        self.assertTrue(Path(inv).is_file())
        self.assertTrue(Path(inv).is_relative_to(self.dest))
        md = (self.dest / "output/projects/R01/08_quality_control/qc-report.md").read_text(encoding="utf-8")
        self.assertIn(str(self.dest / "data/Raw/clip 1.mp4"), md)
        self.assertIn(f"{self.src}2\\x.mp4", md)                              # a sibling folder: never touched
        xml = (self.dest / "output/projects/R01/07_premiere/R01_interchange.xml").read_text(encoding="utf-8")
        self.assertIn(quote(str(self.dest).replace("\\", "/").lstrip("/"), safe="/:"), xml)
        self.assertIn("kept as written", kept["output/projects/R01/logs/pipeline.log"])
        self.assertEqual([p["file"] for p in out["projects"]], ["output/projects/R01/07_premiere/project/R01_EDIT.prproj"])
        self.assertIn("Link Media", out["projects"][0]["fix"])
        self.assertIn("reel ppro-build --force --video-id R01", out["projects"][0]["fix"])
        self.assertIn("still name the old folder", doc["next"])
        status = read_json(self.dest / "output/client_database/client-database-status.json")["issues"][0]
        self.assertIn("['assets\\\\Fonts\\\\B.ttf']" if IS_WIN else "['assets/Fonts/B.ttf']", status)  # relative in the db
        self.assertIsNone(CM.unmigrated(self.dest))

    def test_an_approved_plan_naming_the_old_folder_stays_approved(self):
        from lib import plan as PL
        p = Paths(self.src, "R01")
        write_json(p.p("01_analysis/plan-approval.json"), {"approved": True, "by": "editor", "format": PL.APPROVAL_FORMAT,
                                                            "plan_fingerprint": PL.plan_fingerprint(p)})
        spec = p.p("01_analysis/timeline-spec.json").read_bytes()
        self.moved()
        self.assertEqual((self.dest / "output/projects/R01/01_analysis/timeline-spec.json").read_bytes(), spec)
        self.assertEqual(PL.approval_state(Paths(self.dest, "R01"))["state"], "current")

    def test_a_value_from_the_other_systems_spelling_gets_this_computers_separators(self):
        old = "/Volumes/Drive/Acme" if IS_WIN else "D:\\C\\Acme"
        sep = "/" if IS_WIN else "\\"
        new = Path("E:/New/Acme") if IS_WIN else Path("/Users/ed/Acme")
        doc = {"path": old + sep + sep.join(("data", "Raw", "c.mov")), "note": f"see {old}{sep}x"}
        with mock.patch("lib.client_move_paths.FOLD_CASE", True):
            got = CM._rebase_doc(doc, ([old], new, CM._pairs([old], new, False), False, {}), [0])
        self.assertEqual(got["path"], str(new.joinpath("data", "Raw", "c.mov")))
        self.assertNotIn(old, got["note"])

    def test_moving_a_copy_nobody_migrated_is_refused(self):
        hand = self.tmp / "hand copy"
        shutil.copytree(self.src, hand, copy_function=shutil.copy2)
        doc = CM.move(hand, self.dest)
        self.assertIn("is a copy of", doc["refused"])
        self.assertRegex(doc["refused"], r"^فولدر العميل ده نسخة من .+ / this client folder is a copy of .+; nothing was "
                                         r"written$")
        self.assertIn("--already-moved", doc["how"])
        self.assertFalse(self.dest.exists())

    def test_an_approved_plan_without_paths_stays_approved(self):
        from lib import plan as PL
        p = Paths(self.src, "R01")
        p.p("01_analysis/timeline-spec.json").write_text(json.dumps({"events": [], "fps": 25}), encoding="utf-8")
        os.utime(p.p("01_analysis/timeline-spec.json"), (T0 + 300, T0 + 300))
        write_json(p.p("01_analysis/plan-approval.json"), {"approved": True, "by": "editor", "format": PL.APPROVAL_FORMAT,
                                                            "plan_fingerprint": PL.plan_fingerprint(p)})
        self.assertEqual(PL.approval_state(p)["state"], "current")
        self.moved()
        self.assertEqual(PL.approval_state(Paths(self.dest, "R01"))["state"], "current")

    def test_a_copy_nobody_migrated_is_refused_before_any_read(self):
        hand = self.tmp / "hand copy"
        shutil.copytree(self.src, hand, copy_function=shutil.copy2)
        r = CM.unmigrated(hand)
        self.assertIn("is a copy of", r["refused"])
        self.assertTrue(r["refused"].startswith(f"فولدر العميل ده نسخة من {self.src} "), r["refused"])   # Arabic first
        self.assertEqual(r["copied_from"], str(self.src))
        self.assertIn("--already-moved", r["how"])
        self.assertIsNone(CM.unmigrated(self.src))
        self.assertIsNone(CM.unmigrated(self.tmp))                          # not a client: not its business

    def test_an_outside_path_whose_file_is_not_here_is_not_a_copy(self):
        inv = read_json(self.src / "output/discovery/input-inventory.json")
        inv["files"].append({"rel": "x", "path": str(self.tmp / "store" / "data" / "elsewhere.mp4"), "kind": "video"})
        write_json(self.src / "output/discovery/input-inventory.json", inv)
        self.assertIsNone(CM.unmigrated(self.src))

    def test_moved_twice_names_only_the_last_place(self):
        self.moved()
        third = self.tmp / "Third Place"
        self.hold(self.dest)
        doc = CM.move(self.dest, third, apply=True)
        self.assertTrue(doc.get("applied"), doc)
        inv = read_json(third / "output/discovery/input-inventory.json")["files"][0]["path"]
        self.assertTrue(Path(inv).is_relative_to(third), inv)
        self.assertIsNone(CM.unmigrated(third))

    def test_an_after_effects_project_in_utf16_is_found(self):
        aep = self.src / "output/projects/R01/10_ae/R01.aep"
        aep.parent.mkdir(parents=True)
        aep.write_bytes(b"RIFX\x00" + str(self.src / "data/Raw/clip 1.mp4").encode("utf-16-be") + b"\x00")
        doc = self.moved()
        aeps = [p for p in doc["outside_database"]["projects"] if p["app"] == "after_effects"]
        self.assertEqual([p["file"] for p in aeps], ["output/projects/R01/10_ae/R01.aep"])
        self.assertIn("reel ae-build --force --video-id R01", aeps[0]["fix"])

    def test_links_are_recreated_never_followed(self):
        outside = self.tmp / "outside store"
        (outside / "big").mkdir(parents=True)
        (outside / "big/footage.mp4").write_bytes(b"F" * 1000)
        link_dir(outside / "big", self.src / "data/Mirror")                     # points outside: kept as is
        link_dir(self.src / "output/client_database", self.src / "output/db-alias")   # inside: moved along
        outside_before = tree(outside)
        doc = self.moved()
        self.assertTrue(is_link(self.dest / "data/Mirror"))
        self.assertEqual(os.path.realpath(self.dest / "data/Mirror"), os.path.realpath(outside / "big"))
        self.assertTrue(is_link(self.dest / "output/db-alias"))
        self.assertEqual(os.path.realpath(self.dest / "output/db-alias"),
                         os.path.realpath(self.dest / "output/client_database"))
        self.assertFalse(any(r.startswith("data/Mirror/") for r in tree(self.dest)))  # its content not copied
        self.assertEqual(tree(outside), outside_before)
        self.assertEqual(sorted(x["link"] for x in doc["links"]), ["data/Mirror", "output/db-alias"])

    @unittest.skipUnless(can_symlink(), "this OS account may not create symlinks (Windows without Developer Mode)")
    def test_relative_file_symlinks_stay_relative_and_ones_climbing_out_become_absolute(self):
        os.symlink("../assets/Brand/logo.png", self.src / "data/logo-link.png")
        (self.tmp / "shared.txt").write_text("s", encoding="utf-8")
        os.symlink("../../shared.txt", self.src / "data/shared-link.txt")
        self.moved()
        self.assertEqual(os.readlink(self.dest / "data/logo-link.png").replace("\\", "/"), "../assets/Brand/logo.png")
        self.assertEqual(os.path.realpath(self.dest / "data/shared-link.txt"), os.path.realpath(self.tmp / "shared.txt"))
        self.assertTrue(os.path.isabs(os.readlink(self.dest / "data/shared-link.txt")))

    def test_a_drive_that_rounds_times_is_warned_about(self):
        real_copystat = shutil.copystat

        def rounding(s, d, follow_symlinks=True):
            real_copystat(s, d, follow_symlinks=follow_symlinks)
            st = os.stat(d)
            if os.path.isfile(d):
                os.utime(d, ns=(st.st_atime_ns, (st.st_mtime_ns // 2_000_000_000) * 2_000_000_000 + 2_000_000_000))
        with mock.patch.object(CM.shutil, "copystat", side_effect=rounding):
            doc = self.moved()
        self.assertTrue(doc["mtime_rounded"])
        self.assertIn("FAT/exFAT", doc["warnings"][0])

    def test_failure_mid_copy_removes_the_copy_and_leaves_the_client(self):
        real = shutil.copyfile
        n = [0]

        def flaky(s, d, follow_symlinks=True):
            n[0] += 1
            if n[0] == 7:
                raise OSError(28, "No space left on device")
            return real(s, d, follow_symlinks=follow_symlinks)
        self.dest.mkdir()                                                      # an empty folder the editor made
        before = self.src_tree()
        self.hold()
        with mock.patch.object(CM.shutil, "copyfile", side_effect=flaky):
            doc = CM.move(self.src, self.dest, apply=True)
        self.assertIn("removed again", doc["refused"])
        self.assertIn("No space left", doc["refused"])
        self.assertEqual(list(self.dest.iterdir()), [])                         # back to the empty folder it was
        self.assertEqual(self.src_tree(), before)

    def test_an_interrupted_copy_of_this_client_is_redone(self):
        self.dest.mkdir()
        for d in ("assets/Brand", "data", "output/client_database"):         # a real partial copy: looks like a client
            (self.dest / d).mkdir(parents=True)
        shutil.copy2(self.src / ".whynot-client", self.dest / ".whynot-client")
        (self.dest / "data/Raw").mkdir()
        (self.dest / "data/Raw/clip 1.mp4").write_bytes(b"m" * 1200)          # stopped while copying it
        (self.dest / CM.INCOMPLETE).write_text(json.dumps({"from": str(self.src), "mode": "move", "started_ns": time.time_ns()}), encoding="utf-8")
        dry = CM.move(self.src, self.dest)
        self.assertNotIn("refused", dry)
        self.assertTrue(dry["resumes_interrupted_copy"])
        self.moved()
        self.assertEqual((self.dest / "data/Raw/clip 1.mp4").stat().st_size, 5000)
        self.assertFalse((self.dest / CM.INCOMPLETE).exists())

    def test_a_partial_copy_of_this_clients_files_with_another_marker_is_refused(self):
        self.dest.mkdir()
        (self.dest / "data/Raw").mkdir(parents=True)
        shutil.copy2(self.src / "data/Raw/clip 1.mp4", self.dest / "data/Raw/clip 1.mp4")   # only the client's files
        for mark in ({"from": str(self.tmp / "Other"), "mode": "move"}, {"from": str(self.src), "mode": "clone"},
                     {"from": str(self.src), "mode": "move"}, {"from": str(self.src), "mode": "move", "started_ns": "x"}):
            (self.dest / CM.INCOMPLETE).write_text(json.dumps(mark), encoding="utf-8")
            self.assertIn("not empty", CM.move(self.src, self.dest)["refused"], mark)
        self.assertTrue((self.dest / "data/Raw/clip 1.mp4").is_file())

    def test_a_resume_rechecks_the_free_space_after_removing_its_partial_copy(self):
        self.dest.mkdir()
        (self.dest / CM.INCOMPLETE).write_text(json.dumps({"from": str(self.src), "mode": "move", "started_ns": time.time_ns()}), encoding="utf-8")
        self.hold()
        with mock.patch.object(CM.shutil, "disk_usage", return_value=mock.Mock(free=1000)):
            doc = CM.move(self.src, self.dest, apply=True)
        self.assertIn("free space", doc["refused"])
        self.assertEqual(list(self.dest.iterdir()), [])

    def test_a_partial_copy_with_a_file_newer_than_the_run_is_never_removed(self):
        self.dest.mkdir()
        (self.dest / CM.INCOMPLETE).write_text(json.dumps({"from": str(self.src), "mode": "move",
                                                           "started_ns": time.time_ns() - 10 ** 9}), encoding="utf-8")
        (self.dest / "output/projects/R01/01_analysis").mkdir(parents=True)
        plan = self.dest / "output/projects/R01/01_analysis/edit-decisions.json"
        plan.write_text('{"the editor": "re-planned here"}', encoding="utf-8")      # a name the client has, but newer
        self.hold()
        self.assertIn("not empty", CM.move(self.src, self.dest, apply=True)["refused"])
        self.assertTrue(plan.exists())

    def test_an_interrupted_copy_someone_worked_in_is_never_removed(self):
        self.dest.mkdir()
        (self.dest / "data").mkdir()
        (self.dest / "data/new edit.mp4").write_bytes(b"the editor's work")    # not the client's: someone worked here
        (self.dest / CM.INCOMPLETE).write_text(json.dumps({"from": str(self.src), "mode": "move", "started_ns": time.time_ns()}), encoding="utf-8")
        self.hold()
        self.assertIn("not empty", CM.move(self.src, self.dest, apply=True)["refused"])
        self.assertEqual((self.dest / "data/new edit.mp4").read_bytes(), b"the editor's work")
        (self.dest / "data/new edit.mp4").unlink()
        big = self.dest / "data/Raw/clip 1.mp4"
        big.parent.mkdir()
        big.write_bytes(b"m" * 9000)                                          # larger than the client's: changed
        self.assertIn("not empty", CM.move(self.src, self.dest, apply=True)["refused"])
        self.assertTrue(big.exists())

    def test_a_partial_copy_inside_another_client_is_still_refused(self):
        other = make_client(self.tmp, "Other Client", steps=False)
        dest = other / "output/partial"
        (dest / "data").mkdir(parents=True)
        (dest / CM.INCOMPLETE).write_text(json.dumps({"from": str(self.src), "mode": "move", "started_ns": time.time_ns()}), encoding="utf-8")
        self.assertIn("another client", CM.move(self.src, dest)["refused"])

    def test_an_interrupted_copy_of_another_client_is_refused(self):
        self.dest.mkdir()
        (self.dest / "theirs.bin").write_bytes(b"keep")
        for mark in ({"from": str(self.tmp / "Other"), "mode": "move"}, {"from": str(self.src), "mode": "clone"},
                     {"mode": "move"}, {"from": "", "mode": "move"}):
            (self.dest / CM.INCOMPLETE).write_text(json.dumps(mark), encoding="utf-8")
            self.assertIn("not empty", CM.move(self.src, self.dest)["refused"], mark)
        self.assertEqual((self.dest / "theirs.bin").read_bytes(), b"keep")

    def test_folder_times_are_kept_too(self):
        d = self.src / "data/Raw"
        os.utime(d, (T0 - 500, T0 - 500))
        self.moved()
        self.assertEqual(os.stat(self.dest / "data/Raw").st_mtime_ns, os.stat(d).st_mtime_ns)

    def test_a_copy_that_does_not_match_is_removed_again(self):
        real = shutil.copyfile

        def corrupt(s, d, follow_symlinks=True):
            r = real(s, d, follow_symlinks=follow_symlinks)
            if d.replace("\\", "/").endswith("branding/brand-tokens.json"):
                data = bytearray(Path(d).read_bytes())
                data[0] ^= 1
                Path(d).write_bytes(bytes(data))                              # same size, other content
            return r
        self.hold()
        with mock.patch.object(CM.shutil, "copyfile", side_effect=corrupt):
            doc = CM.move(self.src, self.dest, apply=True)
        self.assertIn("content differs: output/client_database/branding/brand-tokens.json", doc["refused"])
        self.assertFalse(self.dest.exists())

    def test_a_destination_that_changes_after_the_check_is_refused(self):
        self.dest.mkdir()
        real_check = CM.check

        def then_someone_writes(*a, **k):
            r = real_check(*a, **k)
            (self.dest / "theirs.txt").write_text("x", encoding="utf-8")     # between the check and the copy
            return r
        self.hold()
        with mock.patch.object(CM, "check", side_effect=then_someone_writes):
            doc = CM.move(self.src, self.dest, apply=True)
        self.assertIn("changed while", doc["refused"])
        self.assertEqual(sorted(p.name for p in self.dest.iterdir()), ["theirs.txt"])

    def test_output_turning_into_a_link_after_the_check_is_caught_before_the_rewrite(self):
        outside = self.tmp / "elsewhere"
        outside.mkdir()
        real_verify = CM._verify

        def then_swap(src, dest, sc):
            res = real_verify(src, dest, sc)
            shutil.move(str(dest / "output"), str(outside / "output"))     # swapped for a junction after the check
            link_dir(outside / "output", dest / "output")
            return res
        self.hold()
        with mock.patch.object(CM, "_verify", side_effect=then_swap):
            doc = CM.move(self.src, self.dest, apply=True)
        self.assertIn("removed again", doc["refused"])
        self.assertFalse((outside / "output/.whynot-lock").exists())          # no lease written through the link
        self.assertTrue((outside / "output/client_database/asset-manifest.json").is_file())   # never entered
        self.assertFalse(self.dest.exists())

    def test_a_read_only_database_file_is_still_rewritten_in_the_copy(self):
        f = self.src / "output/client_database/asset-manifest.json"
        os.chmod(f, stat.S_IREAD)
        self.addCleanup(os.chmod, f, stat.S_IREAD | stat.S_IWRITE)
        doc = self.moved()
        self.assertEqual(read_json(self.dest / "output/client_database/asset-manifest.json")["assets"][0]["file"],
                         "assets/Brand/logo.png")
        self.assertIn("asset-manifest.json", [c["file"] for c in doc["database"]["changed"]])

    def test_a_link_to_the_client_folder_itself_points_at_the_new_one(self):
        link_dir(self.src, self.src / "output/whole-client")
        self.moved()
        self.assertEqual(os.path.realpath(self.dest / "output/whole-client"), os.path.realpath(self.dest))

    def test_names_are_never_written_through_a_destination_link(self):
        real_dest = self.tmp / "real dest"
        real_dest.mkdir()
        link_dir(real_dest, self.dest)
        self.assertIn("link", CM.move(self.src, self.dest)["refused"])
        self.assertEqual(list(real_dest.iterdir()), [])


class TestRefusals(Base):
    def refused(self, dest, src=None, mode="move"):
        before = self.src_tree()
        doc = (CM.move if mode == "move" else CM.clone)(src or self.src, dest)
        self.assertIn("refused", doc, dest)
        self.assertEqual(self.src_tree(), before)
        return doc

    def test_inside_each_other_or_the_same_folder(self):
        self.refused(self.src / "output/copy")
        self.refused(self.src)
        self.refused(self.tmp)                                               # the client would be inside the copy
        alias = self.tmp / "alias"
        link_dir(self.src, alias)
        self.refused(alias / "sub")
        self.refused(self.src / "data/x", mode="clone")

    def test_a_folder_holding_the_client_is_refused_even_with_our_marker(self):
        (self.tmp / CM.INCOMPLETE).write_text(json.dumps({"from": str(self.src), "mode": "move", "started_ns": time.time_ns()}), encoding="utf-8")
        self.assertIn("contain each other", self.refused(self.tmp)["refused"])
        self.hold()
        self.assertIn("contain each other", CM.move(self.src, self.tmp, apply=True)["refused"])
        self.assertTrue((self.src / "data/Raw/clip 1.mp4").is_file())

    def test_inside_another_client(self):
        other = make_client(self.tmp, "Other Client", steps=False)
        self.assertIn("another client", self.refused(other / "output/x")["refused"])
        self.assertIn("another client", self.refused(other / "data/x")["refused"])

    def test_a_folder_that_is_not_empty_or_a_file(self):
        self.dest.mkdir()
        (self.dest / "x.txt").write_text("x", encoding="utf-8")
        self.assertIn("not empty", self.refused(self.dest)["refused"])
        f = self.tmp / "E drive" / "file"
        f.write_text("x", encoding="utf-8")
        self.assertIn("not a folder", self.refused(f)["refused"])

    def test_not_a_client_and_a_missing_parent(self):
        (self.tmp / "plain").mkdir()
        self.assertIn("not a client", self.refused(self.dest, src=self.tmp / "plain")["refused"])
        self.assertIn("doesn't exist", self.refused(self.tmp / "nope" / "x")["refused"])

    def test_not_enough_free_space(self):
        with mock.patch.object(CM.shutil, "disk_usage", return_value=mock.Mock(free=1000)):
            self.assertIn("free space", self.refused(self.dest)["refused"])
        self.assertFalse(self.dest.exists())

    def test_darwin_var_alias_is_the_same_folder(self):
        priv = lambda p: str(p).replace(str(self.tmp), str(self.tmp) + "-private")
        with mock.patch.object(CM, "real", side_effect=priv):
            self.refused(Path(str(self.src) + "/output/x"))


class TestClone(Base):
    def cloned(self):
        self.hold()
        doc = CM.clone(self.src, self.dest, apply=True)
        self.assertTrue(doc.get("applied"), doc)
        return doc

    def test_brand_database_only_fresh_identity(self):
        before = self.src_tree()
        doc = self.cloned()
        got = set(tree(self.dest))
        self.assertEqual(self.src_tree(), before)
        for want in ("assets", "data", ".whynot-client", "output/client_database/branding/brand-tokens.json",
                     "output/client_database/branding/typography.json", "output/client_database/profile/client-profile.md",
                     "output/client_database/reference_style/editing-style.json",
                     "output/client_database/reel-profile/profile.json"):
            self.assertIn(want, got)
        for never in ("assets/Brand/logo.png", "data/Raw/clip 1.mp4", "output/client_database/assets",
                      "output/client_database/asset-manifest.json", "output/client_database/reference_analysis",
                      "output/projects", "output/discovery", "output/.whynot-lock", "output/logs", ".claude",
                      ".claude/whynot-cut.local.md", CM.INCOMPLETE):
            self.assertNotIn(never, got)
        self.assertEqual(list((self.dest / "assets").iterdir()) + list((self.dest / "data").iterdir()), [])
        marker = json.loads((self.dest / ".whynot-client").read_text(encoding="utf-8"))
        self.assertNotIn("prefix", marker)
        self.assertNotEqual(marker["created"], "2026-01-01T00:00:00+0000")
        typ = read_json(self.dest / "output/client_database/branding/typography.json")
        self.assertEqual(typ["families"]["B"]["weights"][0]["file"], "assets/Fonts/B.ttf")
        from lib.client_marker import is_client
        self.assertTrue(is_client(self.dest, None))
        self.assertIn("no media", doc["next"])
        self.assertNotIn("projects", doc)

    def test_the_clone_is_independent(self):
        self.cloned()
        a = self.src / "output/client_database/branding/brand-tokens.json"
        b = self.dest / "output/client_database/branding/brand-tokens.json"
        self.assertEqual(os.stat(b).st_nlink, 1)
        self.assertNotEqual(os.stat(a).st_ino, os.stat(b).st_ino)
        b.write_text('{"roles": {}}', encoding="utf-8")
        self.assertIn("112233", a.read_text(encoding="utf-8"))

    def test_a_link_in_the_database_or_a_linked_output_is_refused(self):
        link_dir(self.src / "assets", self.src / "output/client_database/branding/assets-link")
        self.hold()
        for fn in (CM.clone, CM.move):
            doc = fn(self.src, self.dest, apply=True)
            self.assertIn("holds links (branding/assets-link)", doc["refused"])
            self.assertFalse(self.dest.exists())
        os.rmdir(self.src / "output/client_database/branding/assets-link") if IS_WIN else \
            os.unlink(self.src / "output/client_database/branding/assets-link")
        lease = (self.src / "output/.whynot-lock").read_bytes()
        store = self.tmp / "big disk output"
        shutil.move(str(self.src / "output"), str(store))
        link_dir(store, self.src / "output")
        for fn in (CM.clone, CM.move):
            doc = fn(self.src, self.dest, apply=True)
            self.assertIn("is a link", doc["refused"])
        self.assertEqual((store / ".whynot-lock").read_bytes(), lease)          # the live lease: never touched
        self.assertFalse(self.dest.exists())


class TestAlreadyMoved(Base):
    def test_a_folder_moved_by_hand_is_rewritten_in_place(self):
        moved = self.tmp / "By Hand يدوي"
        shutil.copytree(self.src, moved, copy_function=shutil.copy2)
        old = str(self.src)
        dry = CM.already_moved(moved)
        self.assertEqual(dry["old_root"], old)
        self.assertFalse(dry["applied"])
        self.assertEqual(len(dry["database"]["changed"]), 4)
        self.assertNotIn("output/client_database/asset-manifest.json",
                         [r["file"] for r in dry["outside_database"]["rewritten"]])     # counted once, by migrate
        self.assertEqual(read_json(moved / "output/client_database/asset-manifest.json")["assets"][0]["file"],
                         str(self.src / "assets/Brand/logo.png"))                # the dry run wrote nothing
        self.hold(moved)
        doc = CM.already_moved(moved, apply=True)
        self.assertEqual(read_json(moved / "output/client_database/asset-manifest.json")["assets"][0]["file"],
                         "assets/Brand/logo.png")
        self.assertEqual([p["file"] for p in doc["outside_database"]["projects"]],
                         ["output/projects/R01/07_premiere/project/R01_EDIT.prproj"])
        self.assertIn("works from where it is now", doc["next"])
        self.assertIsNone(CM.unmigrated(moved))
        again = CM.already_moved(moved, apply=True)
        self.assertIn("already portable", again["next"])

    def test_errors_are_reported_as_a_failure(self):
        moved = self.tmp / "M"
        shutil.copytree(self.src, moved, copy_function=shutil.copy2)
        (moved / "output/client_database/branding/typography.json").write_text("{bad", encoding="utf-8")
        self.hold(moved)
        doc = CM.already_moved(moved, apply=True)
        self.assertIs(doc["ok"], False)
        self.assertIn("branding/typography.json", doc["error"])

    def test_explicit_from_wins_and_is_checked(self):
        moved = self.tmp / "M"
        shutil.copytree(self.src, moved, copy_function=shutil.copy2)
        spelled = str(self.src).replace("\\", "/")
        self.assertEqual(CM.already_moved(moved, old=spelled)["old_root"], spelled)
        before = tree(moved)
        for bad, why in ((Path(self.src.anchor), "drive"), (Path.home(), "home"), (self.tmp, "above it"),
                         (moved, "this client folder"), (self.tmp / "unrelated", "nothing in this client")):
            doc = CM.already_moved(moved, old=bad, apply=False)
            self.assertIn(why, doc["refused"], bad)
        self.assertEqual(tree(moved), before)

    def test_apply_needs_the_lock(self):
        moved = self.tmp / "M"
        shutil.copytree(self.src, moved, copy_function=shutil.copy2)
        (moved / "output/.whynot-lock").unlink()
        with self.assertRaises(Guidance):
            CM.already_moved(moved, apply=True)


class TestExcludeRule(unittest.TestCase):
    def test_rule(self):
        for rel, mode, want in (("output/.whynot-lock", "move", True), ("output/a/b.json.lock", "move", True),
                                ("data/x.lock", "move", False), (CM.INCOMPLETE, "move", True),
                                ("assets", "clone", True), ("output", "clone", False),
                                ("output/client_database", "clone", False), ("output/logs", "clone", True),
                                ("output/client_database/assets/derivatives", "clone", True),
                                ("output/client_database/branding/x.json", "clone", False),
                                (".whynot-client", "clone", True), (".whynot-client", "move", False)):
            self.assertEqual(CM._excluded(rel, mode), want, (rel, mode))


@unittest.skipUnless(IS_WIN, "the \\\\?\\ form is Windows only")
class TestLongPaths(Base):
    def test_a_path_past_260_characters_is_copied(self):
        deep = self.src / "output/projects/R01" / ("ف" * 60) / ("x" * 80) / ("y" * 80)
        os.makedirs(CM._x(deep))
        with open(CM._x(deep / "z.json"), "w", encoding="utf-8") as f:
            f.write("{}")
        self.assertGreater(len(str(deep / "z.json")), 260)
        self.hold()
        doc = CM.move(self.src, self.dest, apply=True)
        self.assertTrue(doc.get("applied"), doc)
        self.assertTrue(os.path.exists(CM._x(self.dest / (deep / "z.json").relative_to(self.src))))
        os.remove(CM._x(deep / "z.json"))                                   # tearDown's rmtree can't reach it
        os.remove(CM._x(self.dest / (deep / "z.json").relative_to(self.src)))
        for top in (self.src, self.dest):
            d = top / "output/projects/R01" / ("ف" * 60)
            for sub in (d / ("x" * 80) / ("y" * 80), d / ("x" * 80), d):
                os.rmdir(CM._x(sub))


class TestBoundDatabaseFiles(Base):
    """Review 02df75f r1 P2-1 (+ P3-1 R13): inside the client database a move rewrites only its own path files and
    client-database-status.json; a file whose bytes something checks, or that the editor / Claude wrote, is kept and
    listed (cases.md F1-F4)."""
    def moved(self, root=None):
        self.hold(root)
        doc = CM.move(root or self.src, self.dest, apply=True)
        self.assertTrue(doc.get("applied"), doc)
        return doc

    def kept(self, doc) -> dict:
        return {k["file"]: k["why"] for k in doc["outside_database"]["kept"]}

    def test_the_reference_style_is_kept_and_every_video_stays_current(self):
        from lib import ref_style
        sd = self.src / "output/client_database/reference_style"
        ref = str(self.src / "data/References/ref.mp4")
        write_json(sd / "editing-style.json", {"pace": 20, "cited": ref})
        write_json(sd / "editing-rules.json", {"mandatory": [f"match the cuts of {ref}"]})
        (sd / "editing-style-analysis.md").write_text(f"From `{ref}`\n", encoding="utf-8")
        p = Paths(self.src, "R01")
        write_json(p.p(ref_style.VIDEO_STYLE), {"_reference_style": {"style_sha1": ref_style.style_sha1(self.src),
                                                                     "overrides_sha1": ref_style._overrides(p)[1]}})
        self.assertEqual(ref_style.video_state(p)["state"], "current")
        before = {f.name: f.read_bytes() for f in sd.iterdir()}
        doc = self.moved()
        dd = self.dest / "output/client_database/reference_style"
        self.assertEqual({f.name: f.read_bytes() for f in dd.iterdir()}, before)
        self.assertEqual(ref_style.video_state(Paths(self.dest, "R01"))["state"], "current")
        kept = self.kept(doc)
        for name in before:
            self.assertIn("reel ref-style", kept["output/client_database/reference_style/" + name])
        cli = __import__("cli")
        self.assertEqual(cli.next_doc(Paths(self.dest, "R01"))["stale"], [])

    def test_the_sealed_rules_file_is_kept_and_still_reads(self):
        from lib import rules_loop
        prof = self.src / "output/client_database/reel-profile"
        rules = [{"id": "R-1", "status": "active", "text": "logo from " + str(self.src / "assets" / "Brand" / "logo.png"),
                  "from": ["N-1"]}]
        f = prof / rules_loop.RULES_FILE
        f.write_bytes(rules_loop._registry_bytes({"schema": rules_loop.SCHEMA, "rules": rules}))
        self.assertEqual(rules_loop._State(self.src).registry()["rules"][0]["id"], "R-1")
        raw = f.read_bytes()
        hand = self.tmp / "by hand"
        shutil.copytree(self.src, hand, copy_function=shutil.copy2)
        doc = self.moved()
        g = self.dest / "output/client_database/reel-profile" / rules_loop.RULES_FILE
        self.assertEqual(g.read_bytes(), raw)
        self.assertEqual(rules_loop._State(self.dest).registry()["rules"][0]["id"], "R-1")
        self.assertIn("sealed by `reel rules`", self.kept(doc)["output/client_database/reel-profile/rules.json"])
        self.hold(hand)                                                         # moved by hand, then repaired
        am = CM.already_moved(hand, apply=True)
        self.assertNotIn("error", am)
        self.assertEqual((hand / "output/client_database/reel-profile" / rules_loop.RULES_FILE).read_bytes(), raw)
        self.assertEqual(rules_loop._State(hand).registry()["rules"][0]["id"], "R-1")
        self.assertIn("output/client_database/reel-profile/rules.json", self.kept(am))

    def test_the_editors_own_writing_is_kept_and_the_status_file_is_still_rewritten(self):
        prof = self.src / "output/client_database/profile/client-profile.md"
        prof.write_text(f"# ملف العميل\nBrand book: {self.src / 'assets' / 'Brand' / 'book.pdf'}\n", encoding="utf-8")
        notes = self.src / "output/client_database/reel-profile/notes.md"
        notes.write_text(f"logo at {self.src / 'assets' / 'Brand' / 'logo.png'}\n", encoding="utf-8")
        raw = {f: f.read_bytes() for f in (prof, notes)}
        doc = self.moved()
        kept = self.kept(doc)
        for f, data in raw.items():
            rel = f.relative_to(self.src).as_posix()
            self.assertEqual((self.dest / rel).read_bytes(), data)
            self.assertIn("written by the editor or Claude", kept[rel])
        self.assertIn("output/client_database/client-database-status.json",
                      [r["file"] for r in doc["outside_database"]["rewritten"]])
        self.assertNotIn(str(self.src), (self.dest / "output/client_database/client-database-status.json")
                         .read_text(encoding="utf-8").replace("\\\\", "\\"))

    def test_brand_tokens_naming_a_path_are_kept_as_signed(self):
        bt = self.src / "output/client_database/branding/brand-tokens.json"
        write_json(bt, {"roles": {"primary": {"hex": "#112233"}}, "source": str(self.src / "assets/Brand/guide.pdf")})
        raw = bt.read_bytes()
        doc = self.moved()
        self.assertEqual((self.dest / "output/client_database/branding/brand-tokens.json").read_bytes(), raw)
        self.assertIn("approval", self.kept(doc)["output/client_database/branding/brand-tokens.json"])


class TestInterruptedCopyRule(Base):
    """Review 02df75f r1 P3-5 + P3-1 (M29, M30, R1): an interrupted copy is removed and made again only when every
    file in it is the client's own copy (its size and time), except the one file the copy stopped in, whose bytes are
    the start of the client's (cases.md F5, F6)."""
    def partial(self, files: dict):
        self.dest.mkdir(exist_ok=True)
        for rel, (data, mtime_ns) in files.items():
            f = self.dest / rel
            f.parent.mkdir(parents=True, exist_ok=True)
            f.write_bytes(data)
            if mtime_ns is not None:
                os.utime(f, ns=(mtime_ns, mtime_ns))
        (self.dest / CM.INCOMPLETE).write_text(json.dumps({"from": str(self.src), "mode": "move",
                                                           "started_ns": time.time_ns()}), encoding="utf-8")

    def src_ns(self, rel):
        return os.stat(self.src / rel).st_mtime_ns

    def test_an_older_smaller_file_with_other_content_is_never_removed(self):
        self.partial({"data/Raw/clip 1.mp4": (b"EDITOR-OWN" * 10, int(T0 * 1e9))})     # camera card, shoot time
        self.hold()
        self.assertIn("not empty", CM.move(self.src, self.dest, apply=True)["refused"])
        self.assertEqual((self.dest / "data/Raw/clip 1.mp4").read_bytes(), b"EDITOR-OWN" * 10)

    def test_only_one_file_may_be_cut_short(self):
        self.partial({"data/Raw/clip 1.mp4": (b"m" * 1200, None), "data/References/ref.mp4": (b"r" * 100, None)})
        self.assertIn("not empty", CM.check(self.src, self.dest)["refused"])
        (self.dest / "data/References/ref.mp4").unlink()
        self.assertTrue(CM.check(self.src, self.dest)["partial"])

    def test_a_copy_on_a_drive_that_keeps_coarse_times_is_redone(self):
        self.dest.mkdir()
        for rel, _size, _m in CM.scan(self.src, "move")["files"]:
            d = self.dest / rel
            d.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(self.src / rel, d)
            t = os.stat(d).st_mtime_ns
            os.utime(d, ns=(t, t - t % 2_000_000_000))                       # FAT: times kept to 2 s
        (self.dest / CM.INCOMPLETE).write_text(json.dumps({"from": str(self.src), "mode": "move",
                                                           "started_ns": time.time_ns()}), encoding="utf-8")
        self.assertTrue(CM.check(self.src, self.dest)["partial"])
        for rel in ("data/Raw/clip 1.mp4", "data/References/ref.mp4"):           # 3 s off: not what a drive rounds
            t = os.stat(self.src / rel).st_mtime_ns + 3_000_000_000
            os.utime(self.dest / rel, ns=(t, t))
        doc = CM.check(self.src, self.dest)
        self.assertIn("an interrupted copy of this client that changed", doc["refused"])     # ours, but changed:
        self.assertIn("remove only the link", doc["how"])                                     # said so, never removed
        self.assertTrue((self.dest / "data/Raw/clip 1.mp4").is_file())
        (self.dest / CM.INCOMPLETE).write_text(json.dumps({"from": str(self.tmp / "Other"), "mode": "move",
                                                           "started_ns": time.time_ns()}), encoding="utf-8")
        self.assertNotIn("interrupted copy", CM.check(self.src, self.dest)["refused"])
        (self.dest / CM.INCOMPLETE).write_text(json.dumps({"from": str(self.src), "mode": "move", "started_ns": "x"}),
                                               encoding="utf-8")                          # not a marker we wrote
        self.assertNotIn("interrupted copy", CM.check(self.src, self.dest)["refused"])

    def test_one_whole_file_with_a_new_time_is_taken_as_the_one_being_copied(self):
        self.partial({"data/notes.lock": (b"editor's own file", None)})            # same bytes, written later
        self.assertTrue(CM.check(self.src, self.dest)["partial"])                  # = the one file being copied
        self.partial({"data/Raw/clip 1.mp4": (b"m" * 5000, None)})
        self.assertIn("not empty", CM.check(self.src, self.dest)["refused"])       # a second one: not a copy we made

    def test_a_copy_stopped_during_the_rewrite_is_redone(self):
        inv = "output/discovery/input-inventory.json"
        rewritten = json.dumps({"files": [{"rel": "data/Raw/clip 1.mp4", "path": str(self.dest / "data/Raw/clip 1.mp4")}]})
        self.partial({inv: (rewritten.encode("utf-8"), self.src_ns(inv)),
                      "data/Raw/clip 1.mp4": ((self.src / "data/Raw/clip 1.mp4").read_bytes(),
                                              self.src_ns("data/Raw/clip 1.mp4"))})
        self.assertTrue(CM.check(self.src, self.dest)["partial"])
        self.partial({"data/References/ref.mp4": (b"r" * 300, self.src_ns("data/References/ref.mp4") + 10 ** 9)})
        self.partial({"data/notes.lock": (b"x" * 3, self.src_ns("data/notes.lock"))})     # client's time, other size
        self.assertIn("not empty", CM.check(self.src, self.dest)["refused"])

    def test_a_valid_marker_of_another_client_or_mode_is_refused(self):
        self.dest.mkdir()
        (self.dest / "data/Raw").mkdir(parents=True)
        shutil.copy2(self.src / "data/Raw/clip 1.mp4", self.dest / "data/Raw/clip 1.mp4")
        now = time.time_ns()
        (self.dest / CM.INCOMPLETE).write_text(json.dumps({"from": str(self.src), "mode": "move", "started_ns": now}),
                                               encoding="utf-8")
        self.assertTrue(CM.check(self.src, self.dest)["partial"])                  # the control: ours
        for mark in ({"from": str(self.tmp / "Other"), "mode": "move", "started_ns": now},
                     {"from": str(self.src), "mode": "clone", "started_ns": now}):
            (self.dest / CM.INCOMPLETE).write_text(json.dumps(mark), encoding="utf-8")
            self.assertIn("not empty", CM.check(self.src, self.dest)["refused"], mark)


class TestReviewR1Copy(Base):
    """Review 02df75f r1 P3-1 R4, P3-4, P3-6, P3-7 (cases.md F7, F9-F11)."""
    def test_a_media_file_cut_short_in_the_copy_is_caught(self):
        real = shutil.copyfile

        def short(s, d, follow_symlinks=True):
            r = real(s, d, follow_symlinks=follow_symlinks)
            if d.replace("\\", "/").endswith("data/Raw/clip 1.mp4"):
                with open(d, "r+b") as f:
                    f.truncate(100)
            return r
        self.hold()
        with mock.patch.object(CM.shutil, "copyfile", side_effect=short):
            doc = CM.move(self.src, self.dest, apply=True)
        self.assertIn("size differs: data/Raw/clip 1.mp4", doc["refused"])
        self.assertFalse(self.dest.exists())

    def test_a_data_junction_to_a_store_is_not_a_copy(self):
        store = self.tmp / "store" / "ClientX"
        (store / "data/References").mkdir(parents=True)
        (store / "data/References/ref.mp4").write_bytes(b"r" * 10)
        c = self.tmp / "clients" / "ClientX"
        (c / "assets").mkdir(parents=True)
        (c / "output/client_database/reference_analysis").mkdir(parents=True)
        link_dir(store / "data", c / "data")
        key = str((c / "data/References/ref.mp4").resolve())                       # how older caches keyed it
        self.assertTrue(key.casefold().startswith(os.path.realpath(store).casefold()))
        write_json(c / "output/client_database/reference_analysis/cache.json", {key + "|10|5": {"video": key}})
        self.assertIsNone(CM.unmigrated(c))
        hand = self.tmp / "hand" / "ClientX"                                       # a real copy of it is still caught
        shutil.copytree(c, hand)
        self.assertFalse(is_link(hand / "data"))
        self.assertIn("is a copy of", CM.unmigrated(hand)["refused"])

    def test_a_link_that_cannot_be_recreated_rolls_the_move_back(self):
        outside = self.tmp / "outside store"
        (outside / "big").mkdir(parents=True)
        (outside / "big/footage.mp4").write_bytes(b"F" * 1000)
        link_dir(outside / "big", self.src / "data/Mirror")
        before = tree(outside)
        self.hold()
        with mock.patch.object(CM, "_make_link", side_effect=OSError(1, "not allowed")):
            doc = CM.move(self.src, self.dest, apply=True)
        self.assertIn("removed again", doc["refused"])
        self.assertIn("data/Mirror", doc["refused"])
        self.assertIn("not allowed", doc["refused"])
        self.assertFalse(self.dest.exists())
        self.assertEqual(tree(outside), before)

    def test_a_store_reached_through_another_alias_is_not_a_copy(self):
        store = self.tmp / "store"
        (store / "ClientX/data/References").mkdir(parents=True)
        (store / "ClientX/data/References/ref.mp4").write_bytes(b"r" * 10)
        link_dir(store, self.tmp / "alias")                                       # e.g. a mapped drive vs the share
        c = self.tmp / "clients" / "ClientX"
        (c / "assets").mkdir(parents=True)
        (c / "output/client_database/reference_analysis").mkdir(parents=True)
        link_dir(store / "ClientX/data", c / "data")
        key = str(self.tmp / "alias" / "ClientX" / "data" / "References" / "ref.mp4")
        write_json(c / "output/client_database/reference_analysis/cache.json", {key + "|10|5": {"video": key}})
        self.assertIsNone(CM.unmigrated(c))

    def test_edit_decisions_with_a_takes_history_say_undo_stops_at_the_move(self):
        p = Paths(self.src, "R01")
        write_json(p.p("01_analysis/takes-history.json"), {"schema": 1, "steps": [{"before": "e30=", "after_sha1": "x"}]})
        self.hold()
        doc = CM.move(self.src, self.dest, apply=True)
        kept = {k["file"]: k["why"] for k in doc["outside_database"]["kept"]}
        self.assertIn("output/projects/R01/01_analysis/edit-decisions.json",
                      [r["file"] for r in doc["outside_database"]["rewritten"]])     # its media paths: the new folder
        self.assertIn("reel takes --undo", kept["output/projects/R01/01_analysis/takes-history.json"])
        plain = make_client(self.tmp, "Plain")                                    # every step undone: nothing to say
        write_json(Paths(plain, "R01").p("01_analysis/takes-history.json"), {"schema": 1, "steps": []})
        self.hold(plain)
        doc2 = CM.move(plain, self.tmp / "E drive" / "Plain2", apply=True)
        self.assertNotIn("takes-history", json.dumps(doc2["outside_database"]["kept"]))

    def test_the_report_says_close_premiere_first_and_when_to_delete_the_old_folder(self):
        dry = CM.move(self.src, self.dest)
        self.assertIn(f"Close the Premiere and After Effects projects you have open at {self.src} first", dry["next"])
        self.assertNotIn("Close the Premiere", CM.clone(self.src, self.tmp / "E drive" / "Sister")["next"])
        self.hold()
        doc = CM.move(self.src, self.dest, apply=True)
        self.assertIn(f"close the Premiere and After Effects projects you have open at {self.src} first", doc["next"])
        self.assertIn("keep it until", doc["old_folder"])                          # the fixture's plan is kept
        self.assertNotIn("delete the old one yourself", doc["old_folder"])
        plain = make_client(self.tmp, "Plain", steps=False)
        self.hold(plain)
        doc2 = CM.move(plain, self.tmp / "E drive" / "Plain2", apply=True)
        self.assertTrue(doc2.get("applied"), doc2)
        self.assertIn("delete the old one yourself", doc2["old_folder"])
        self.assertNotIn("keep it until", doc2["old_folder"])


class TestFileUrls(unittest.TestCase):
    """Review 02df75f r1 P3-3: an interchange XML's pathurl is read back and written again by the build's own
    pathurl, so a NAS share stays file://server/share/... and a drive file://localhost/... (cases.md F8)."""
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.root = self.tmp / "client"
        (self.root / "output/projects/R01/07_premiere").mkdir(parents=True)
        self.xml = self.root / "output/projects/R01/07_premiere/R01_interchange.xml"

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def rebased(self, old, new, url):
        self.xml.write_text(f"<pathurl>{url}</pathurl>\n<name>{old}</name>", encoding="utf-8")
        rep = CM.rebase(self.root, [old], new=new)
        self.assertEqual(rep["errors"], [])
        return self.xml.read_text(encoding="utf-8").split("</pathurl>")[0][len("<pathurl>"):]

    def test_nas_to_a_drive_and_back(self):
        from lib.premiere_xml import path_from_url, pathurl
        nas = "\\\\srv\\share\\C\\Acme" if IS_WIN else "//srv/share/C/Acme"
        local = self.tmp / "New Acme & Co"
        got = self.rebased(nas, local, "file://srv/share/C/Acme/data/Raw/clip%201.mp4")
        self.assertEqual(got, pathurl(local / "data/Raw/clip 1.mp4"))
        self.assertEqual(Path(path_from_url(got)), Path(os.path.realpath(local)) / "data/Raw/clip 1.mp4")
        back = self.rebased(str(local), Path(nas), pathurl(local / "data/Raw/clip 1.mp4"))
        self.assertEqual(back, "file://srv/share/C/Acme/data/Raw/clip%201.mp4")
        self.assertIn(f"<name>{nas}</name>", self.xml.read_text(encoding="utf-8"))   # the plain text: by spelling

    def report(self, old, new, text):
        md = self.root / "output/projects/R01/08_quality_control/qc-report.md"
        md.parent.mkdir(parents=True, exist_ok=True)
        md.write_text(text, encoding="utf-8")
        rep = CM.rebase(self.root, [old], new=new)
        self.assertEqual(rep["errors"], [])
        return md.read_text(encoding="utf-8"), {k["file"]: k["why"] for k in rep["kept"]}

    def test_urls_in_a_report_keep_their_punctuation_query_and_fragment(self):
        from lib.premiere_xml import pathurl
        old = Path("D:/C/Acme") if IS_WIN else Path("/C/Acme")
        new = self.tmp / "New"
        u = pathurl(old / "x.mov")
        text, kept = self.report(str(old), new, f"[clip]({u}). See {u}#t=10, and {u}?v=2.\nAlso {u}, done: {u}.\n"
                                                f"Root: {pathurl(old)}\n")
        n = pathurl(new / "x.mov")
        self.assertEqual(text, f"[clip]({n}). See {n}#t=10, and {n}?v=2.\nAlso {n}, done: {n}.\nRoot: {pathurl(new)}\n")
        self.assertEqual(kept, {})

    def test_a_hand_typed_url_with_a_space_is_listed(self):
        old = "D:\\C\\My Acme" if IS_WIN else "/C/My Acme"
        url = "file://localhost/" + old.replace("\\", "/").lstrip("/") + "/x.mov"
        _text, kept = self.report(old, self.tmp / "New", f"<a href=\"{url}\">clip</a>\n")
        self.assertIn("check it yourself", kept["output/projects/R01/08_quality_control/qc-report.md"])

    def test_a_url_in_a_json_value_is_rebuilt_too(self):
        from lib.premiere_xml import pathurl
        nas = "\\\\srv\\share\\C\\Acme" if IS_WIN else "//srv/share/C/Acme"
        local = self.tmp / "New Acme"
        f = self.root / "output/projects/R01/07_premiere/ppro-build-result.json"
        write_json(f, {"url": "file://srv/share/C/Acme/data/x.mov", "note": "built from file://srv/share/C/Acme/data/x.mov"})
        CM.rebase(self.root, [nas], new=local)
        doc = read_json(f)
        self.assertEqual(doc["url"], pathurl(local / "data/x.mov"))
        self.assertEqual(doc["note"], "built from " + pathurl(local / "data/x.mov"))

    def test_a_url_on_another_drive_or_server_is_never_looked_up(self):
        from lib.premiere_xml import pathurl
        old = self.tmp / "Old Acme"
        seen = []
        real = CM.client_db.__dict__.get("rel_under")

        def spy(v, base, *rest):
            seen.append(v)
            return None if "offline" in str(v) else real(v, base, *rest)   # (the red run must not stall either)
        with mock.patch.object(CM.client_db, "rel_under", side_effect=spy):
            text, _kept = self.report(str(old), self.tmp / "New",
                                      "music: file://offline/share/x.mp3 and " + pathurl(old / "x.mov") + "\n")
        self.assertIn(pathurl(self.tmp / "New" / "x.mov"), text)
        self.assertIn("file://offline/share/x.mp3", text)
        self.assertFalse([v for v in seen if "offline" in str(v)], seen)

    def test_a_share_url_of_an_old_root_given_as_a_mapped_drive_is_rebuilt(self):
        """--already-moved --from Z:\\Clients\\Acme where Z: is \\\\nas\\work: the build wrote the share's URL."""
        from lib.premiere_xml import pathurl
        z = "Z:\\Clients\\Acme" if IS_WIN else "/Volumes/Z/Clients/Acme"
        zhead, nas = ("Z:\\", "\\\\nas\\work\\") if IS_WIN else ("/Volumes/Z/", "//nas/work/")
        real = os.path.realpath

        def fake_real(p):
            s = str(p)
            if s.startswith(zhead):
                return nas + s[len(zhead):]
            return s if s[:2] in ("\\\\", "//") else real(s)                          # never a network lookup
        local = self.tmp / "New Acme"
        with mock.patch("lib.client_move.real", side_effect=fake_real), \
                mock.patch("lib.client_move_paths.real", side_effect=fake_real):
            got = self.rebased(z, local, "file://nas/work/Clients/Acme/data/x.mov")
        self.assertEqual(got, pathurl(local / "data/x.mov"))

    def test_a_drive_alias_url_of_the_old_root_is_rebuilt(self):
        """A URL on another drive letter that IS the old folder (subst / a junction drive): only shares are skipped."""
        from lib.premiere_xml import pathurl
        old = self.tmp / "Old Acme"
        alias = "Y:\\" if IS_WIN else "/aliasdrive/"
        real = os.path.realpath

        def fake_real(p):
            s = str(p)
            return str(self.tmp) + os.sep + s[len(alias):] if s.startswith(alias) else real(s)
        local = self.tmp / "New Acme"
        url = "file://localhost/" + (alias.replace("\\", "/") + "Old%20Acme/x.mov").lstrip("/")
        with mock.patch("lib.client_move.real", side_effect=fake_real), \
                mock.patch("lib.client_move_paths.real", side_effect=fake_real):
            got = self.rebased(str(old), local, url)
        self.assertEqual(got, pathurl(local / "x.mov"))

    def test_an_offline_old_share_is_looked_up_once_per_move(self):
        """--already-moved --from a NAS that is off now: every lookup of it stalls, so it is looked up once."""
        from lib.premiere_xml import pathurl
        nas = "\\\\nas\\gone\\Acme" if IS_WIN else "//nas/gone/Acme"
        real = os.path.realpath
        calls = []

        def fake_real(p):
            s = str(p)
            if s[:2] in ("\\\\", "//"):
                calls.append(s)
                return s
            return real(s)
        local = self.tmp / "New Acme"
        urls = [f"file://nas/gone/Acme/data/x{i}.mov" for i in range(3)]
        music = [pathurl(self.tmp / "Music" / f"m{i}.mp3") for i in range(3)]          # local stock: not under it
        self.xml.write_text("".join(f"<pathurl>{u}</pathurl>\n" for u in urls + music), encoding="utf-8")
        write_json(self.root / "output/projects/R01/07_premiere/ppro-build-result.json",
                   {"clips": [f"built from {u}" for u in urls]})
        with mock.patch("lib.client_move.real", side_effect=fake_real), \
                mock.patch("lib.client_move_paths.real", side_effect=fake_real):
            rep = CM.rebase(self.root, [nas], new=local)
        self.assertEqual(len(rep["rewritten"]), 2)
        self.assertIn(pathurl(local / "data/x2.mov"), self.xml.read_text(encoding="utf-8"))
        self.assertEqual(len(calls), 1, calls)
        self.assertIn(music[2], self.xml.read_text(encoding="utf-8"))

    def test_a_url_outside_the_old_root_is_left_alone(self):
        url = "file://localhost/D:/C/Acme2/x.mov"
        self.assertEqual(self.rebased("D:\\C\\Acme" if IS_WIN else "/C/Acme", self.tmp / "N", url), url)


if __name__ == "__main__":
    unittest.main()


class TestForeignFormValues(unittest.TestCase):
    """macOS/Linux reading a database written on Windows: a `D:\\...` value is never glued onto the working folder."""
    def test_a_windows_value_on_posix(self):
        root = "/Users/ed/Clients/A"
        glued = lambda p: str(p) if str(p).startswith("/") else root + "/" + str(p)      # realpath from cwd = root
        with mock.patch("sys.platform", "darwin"), mock.patch("lib.client_move_paths.real", side_effect=glued), \
                mock.patch("lib.client_move_paths.FOLD_CASE", True):
            v = "D:\\Clients\\A\\assets\\x.png"
            self.assertFalse(CDB.native_abs(v))
            self.assertIsNone(CDB.rel_under(v, root))
            self.assertFalse(CDB.inside_root(v, root))
            self.assertEqual(CDB.to_stored(root, v, old_roots=["D:\\Clients\\A"]), "assets/x.png")
            self.assertTrue(CDB.native_abs("/Users/ed/x.png"))


class TestRebaseBoundaries(unittest.TestCase):
    def test_a_root_is_replaced_only_where_it_ends(self):
        pairs = CM._pairs(["D:\\C\\Acme"], Path("E:/New"), True)
        for s, want in (("D:\\C\\Acme\\data\\x.mp4", 1), ("D:\\C\\Acme2\\x.mp4", 0), ("D:\\C\\Acme b\\x", 0),
                        ("D:/C/Acme/x", 1), ('"D:\\\\C\\\\Acme\\\\x"', 1),
                        ("file://localhost/D:/C/Acme/x.mov", 0),   # a URL is rebuilt whole (_rebased_url), not spelled
                        ("D:\\C\\Acme", 1)):
            self.assertEqual(CM._sub(s, pairs)[1], want, s)

    def test_a_root_is_replaced_only_where_it_starts(self):
        pairs = CM._pairs(["/Users/ed/Acme"], Path("/Users/ed/New"), True)
        for s, want in (("/Volumes/Backup/Users/ed/Acme/x.mov", 0), ("see /Users/ed/Acme/x.mov", 1),
                        ('"/Users/ed/Acme/x"', 1), ("[/Users/ed/Acme]", 1), ("--root=/Users/ed/Acme", 1)):
            self.assertEqual(CM._sub(s, pairs)[1], want, s)
        win = CM._pairs(["D:\\C\\Acme"], Path("E:/New"), True)
        self.assertEqual(CM._sub("XD:\\C\\Acme\\x", win)[1], 0)
        self.assertEqual(CM._sub("Clip: `D:\\C\\Acme\\x`", win)[1], 1)
        self.assertEqual(CM._sub("error:\\nD:\\C\\Acme\\x", win)[1], 1)                  # an escaped newline before it
        self.assertEqual(CM._sub("\\\\?\\D:\\C\\Acme\\x", win)[1], 1)                    # the long-path prefix

    def test_an_xml_escaped_root_is_found(self):
        pairs = CM._pairs(["D:\\C\\Pegasus & Co"], Path("E:/New"), True)
        self.assertEqual(CM._sub("<pathurl>file://localhost/D:/C/Pegasus%20&amp;%20Co/x.mov</pathurl>", pairs)[1], 0)
        self.assertEqual(CM._sub("<path>D:/C/Pegasus &amp; Co/x.mov</path>", pairs)[1], 1)
