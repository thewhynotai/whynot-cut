"""Gate 2 fix round G1 — Premiere rebuild safety and id/root validation.

B1  a failed rebuild that put the old project back keeps the record of what the PIPELINE saved, so the editor's changes
    are still seen by the next `--force`.
B2  closing the open project in Premiere saves it: the editor's unsaved work that this close wrote is never recorded as
    the pipeline's; the build refuses (EDITOR_CHANGES_PRESENT) unless --replace-edited.
B3  the bridge's own "no reply" timeout result counts as claimed (Premiere may still be writing).
B4  --video-id / --episode are one plain folder name (no separators, no `..`); writing commands refuse a --root without
    assets/ and data/.
Minors: `_prev_` names are unique below the second and their stem is glob-escaped; a relative WHYNOT_HOME is absolute.
Run:  bash tools/test.sh -p test_gate2_safety.py
"""
import sys as _sys
_sys.dont_write_bytecode = True
import _isolation  # noqa: F401,E402  G79: sandbox the engine home first (tests/_isolation.py)
import gzip  # noqa: E402
import json  # noqa: E402
import os  # noqa: E402
import shutil  # noqa: E402
import subprocess  # noqa: E402
import tempfile  # noqa: E402
import time  # noqa: E402
import unittest  # noqa: E402
from pathlib import Path  # noqa: E402
from unittest import mock  # noqa: E402

SK = Path(__file__).resolve().parents[1]
CLI = SK / "engine" / "reel" / "cli.py"
if str(SK / "engine" / "reel") not in _sys.path:
    _sys.path.insert(0, str(SK / "engine" / "reel"))

from lib import cep_queue, common, errors  # noqa: E402
from lib.common import Paths, read_json, write_json  # noqa: E402

DATA = {"_missing": [], "graphics": [], "native_caption_track": False, "sharpen_v1": None,
        "sequence_name": "V1", "track_names": {}}


def gz(path: Path, text: str, mtime: float | None = None):
    with gzip.open(path, "wb") as f:
        f.write(f"<Project><Sequence>{text}</Sequence></Project>".encode("utf-8"))
    if mtime is not None:
        os.utime(path, (mtime, mtime))


def ungz(path: Path) -> str:
    with gzip.open(path) as f:
        return f.read().decode("utf-8")


class _Client(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.home = self.tmp / "home"
        self.home.mkdir()
        ctx = common.use_context(common.Context(home=self.home))
        ctx.__enter__()
        self.addCleanup(ctx.__exit__, None, None, None)
        root = self.tmp / "C"
        (root / "assets").mkdir(parents=True)
        (root / "data").mkdir()
        self.p = Paths(root, "V1")
        self.p.ensure_project()
        write_json(self.p.p("01_analysis/timeline-spec.json"), {"events": [], "duration_frames": 240, "main_segments": []})
        self.prj = self.p.p(f"07_premiere/project/V1_{common.project_prefix()}_EDIT.prproj")
        self.prj.parent.mkdir(parents=True, exist_ok=True)
        self.rec_p = self.p.p("07_premiere/ppro-build-result.json")

    def pipeline_built(self, text="BUILT", age_s=3600):
        """The project as the pipeline saved it `age_s` ago, and its build record."""
        from lib.verify import prproj_signature
        bt = time.time() - age_s
        gz(self.prj, text, bt)
        write_json(self.rec_p, {"status": "PRPROJ_BUILT", "project": str(self.prj), "prproj_mtime": bt,
                                "content_signature": prproj_signature(self.prj), "checks": {}})
        return bt

    def build(self, answer, close=None, **kw):
        """ppro_build.build with a fake bridge: `close(prj)` plays Premiere's save-and-close, `answer(prj)` the build."""
        from lib import ppro_build
        sent = []

        def submit(action, data=None, timeout=0, **k):
            sent.append(action)
            if action == "close_project_path":
                if close:
                    close(self.prj)
                return {"ok": True, "response": {"ok": True, "result": {"closed": True}}}
            return answer(self.prj)

        with mock.patch("lib.ppro_bridge.status", return_value={"alive": True}), \
                mock.patch("lib.ppro_bridge.submit", side_effect=submit), \
                mock.patch.object(ppro_build, "job_data", return_value=dict(DATA)):
            r = ppro_build.build(self.p, **kw)
        return r, sent


def failed(prj):
    return {"ok": False, "error": "Premiere reported an error"}


class TestB1FailedRebuildKeepsTheEditorCheck(_Client):
    def test_editor_change_survives_a_failed_replace_edited_rebuild(self):
        bt = self.pipeline_built()
        gz(self.prj, "EDITED BY THE EDITOR", bt + 1800)                  # the editor saved real work in Premiere
        r, sent = self.build(failed, overwrite=True)
        self.assertEqual(r["status"], "EDITOR_CHANGES_PRESENT", r)
        self.assertEqual(sent, [])
        r, sent = self.build(failed, overwrite=True, replace_edited=True)
        self.assertEqual(r["status"], "FAILED", r)
        self.assertTrue(r["previous_restored"])
        self.assertIn("EDITED BY THE EDITOR", ungz(self.prj))
        r, sent = self.build(failed, overwrite=True)                    # the next plain --force
        self.assertEqual(r["status"], "EDITOR_CHANGES_PRESENT", r)
        self.assertEqual(errors.exit_code(r), 2)
        self.assertNotIn("build_project", sent)

    def test_the_failure_is_still_recorded(self):
        self.pipeline_built()
        r, _ = self.build(failed, overwrite=True)
        self.assertEqual(r["status"], "FAILED")
        rec = read_json(self.rec_p)
        self.assertEqual(rec["status"], "FAILED")
        self.assertTrue(rec["previous_restored"])


class TestB2CloseSaveIsNotThePipelines(_Client):
    def test_unsaved_editor_work_written_by_the_close_is_refused(self):
        self.pipeline_built()
        sig0 = read_json(self.rec_p)["content_signature"]
        r, sent = self.build(failed, close=lambda prj: gz(prj, "UNSAVED EDITOR WORK"), overwrite=True)
        self.assertEqual(r["status"], "EDITOR_CHANGES_PRESENT", r)
        self.assertTrue(r["blocked"])
        self.assertEqual(errors.exit_code(r), 2)
        self.assertEqual(sent, ["close_project_path"])                  # nothing was built over it
        self.assertEqual(read_json(self.rec_p)["content_signature"], sig0)   # never recorded as the pipeline's
        self.assertIn("UNSAVED EDITOR WORK", ungz(self.prj))
        r, sent = self.build(failed, overwrite=True)                    # and the next --force still sees it
        self.assertEqual(r["status"], "EDITOR_CHANGES_PRESENT", r)

    def test_replace_edited_goes_ahead(self):
        self.pipeline_built()
        r, sent = self.build(failed, close=lambda prj: gz(prj, "UNSAVED EDITOR WORK"), overwrite=True,
                             replace_edited=True)
        self.assertIn("build_project", sent)
        self.assertEqual(r["status"], "FAILED")

    def test_a_save_without_changes_is_the_pipelines(self):
        self.pipeline_built()
        r, sent = self.build(failed, close=lambda prj: gz(prj, "BUILT"), overwrite=True)    # same timeline, new time
        self.assertIn("build_project", sent)
        rec = read_json(self.rec_p)
        self.assertGreater(rec["prproj_mtime"], time.time() - 120)


class TestB3NoReplyCountsAsClaimed(unittest.TestCase):
    def test_the_bridges_own_timeout_keeps_the_job_claimed(self):
        q = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, q, True)
        (q / "J1.result.json").write_text(json.dumps({"ok": False, "error": "no reply from PPRO within 20 min"}),
                                          encoding="utf-8")
        r = cep_queue._wait(q, "J1", time.time(), 5, 5, 0.01, "Premiere")
        self.assertIs(r["claimed"], True, r)
        self.assertFalse(r["ok"])
        (q / "J2.result.json").write_text(json.dumps({"ok": False, "error": "script not whitelisted"}), encoding="utf-8")
        self.assertNotIn("claimed", cep_queue._wait(q, "J2", time.time(), 5, 5, 0.01, "Premiere"))


class TestB4Ids(unittest.TestCase):
    def test_real_ids_stay_valid(self):
        from lib.episode import EpisodePaths
        root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, root, True)
        for vid in ("C0239", "CLIP_6EB37C", "EP02TEST_R02_MO", "EP12_R01", "C0239_MOV", "DR_SHERIF_INTRO_1A2B3C",
                    "Dr Sherif intro", "V1", "clip.v2", "Interview... part 2", "x..y"):
            self.assertEqual(Paths(root, vid).project.name, vid)
        for eid in ("EP12", "EP_1A2B3C", "POD3", "EP02TEST"):
            self.assertEqual(EpisodePaths(root, eid).project.name, eid)

    def test_traversal_and_separators_are_refused(self):
        from lib.episode import EpisodePaths
        root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, root, True)
        for bad in ("../../assets/X", "..", ".", "a/b", "a\\b", "C:X", "a/../b", "...", " V1", "V1.", "a\x00b"):
            with self.subTest(bad=bad), self.assertRaises(errors.Guidance):
                Paths(root, bad)
        for bad in ("../x", "EP 1", "a/b", "..", "EP1/../../data"):
            with self.subTest(bad=bad), self.assertRaises(errors.Guidance):
                EpisodePaths(root, bad)


def reel(*argv):
    r = subprocess.run([_sys.executable, "-B", str(CLI), *argv], capture_output=True, text=True, encoding="utf-8")
    try:
        doc = json.loads(r.stdout)
    except ValueError:
        doc = None
    return r.returncode, doc, r.stderr


class TestB4Cli(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.root = self.tmp / "Client"
        (self.root / "assets" / "Logos").mkdir(parents=True)
        (self.root / "data" / "Raw").mkdir(parents=True)

    def snapshot(self, d: Path):
        return sorted(x.relative_to(d).as_posix() for x in d.rglob("*"))

    def test_a_video_id_that_climbs_out_is_refused(self):
        before = self.snapshot(self.root / "assets") + self.snapshot(self.root / "data")
        code, doc, err = reel("--root", str(self.root), "preflight", "--video-id", "../../assets/X")
        self.assertEqual(code, 1, (doc, err))
        self.assertIs(doc["ok"], False)
        self.assertIn("video id", doc["error"])
        self.assertEqual(self.snapshot(self.root / "assets") + self.snapshot(self.root / "data"), before)
        self.assertFalse((self.tmp / "assets").exists())

    def test_an_episode_that_climbs_out_is_refused(self):
        code, doc, err = reel("--root", str(self.root), "episode-prep", "--episode", "../../data/X")
        self.assertEqual(code, 1, (doc, err))
        self.assertIn("episode id", doc["error"])
        self.assertEqual(self.snapshot(self.root / "data"), ["Raw"])

    def test_writing_commands_refuse_a_root_that_is_not_a_client(self):
        for root in (self.tmp / "Downloads", self.root / "assets", self.root / "data" / "Raw"):
            root.mkdir(exist_ok=True)
            before = self.snapshot(root)
            with self.subTest(root=root.name):
                code, doc, err = reel("--root", str(root), "preflight", "--video-id", "C1")
                self.assertEqual(code, 1, (doc, err))
                self.assertIn("assets/ and data/", doc["error"])
                self.assertEqual(self.snapshot(root), before)

    def test_read_only_status_stays_lenient(self):
        wrong = self.tmp / "Downloads"
        wrong.mkdir()
        code, doc, err = reel("--root", str(wrong), "lock")
        self.assertNotIn("assets/ and data/", json.dumps(doc) if doc else err)


class TestMinors(unittest.TestCase):
    def test_relative_whynot_home_is_absolute(self):
        from lib import plat
        with mock.patch.dict(os.environ, {"WHYNOT_HOME": "rel-home"}):
            h = plat.engine_home()
        self.assertTrue(h.is_absolute(), h)
        self.assertEqual(h, Path(os.path.abspath("rel-home")))

    def test_prev_names_are_unique_and_glob_safe(self):
        from lib import ppro_build
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp, True)
        prj = tmp / "X[1]_RE_EDIT.prproj"
        a, b = ppro_build.prev_name(prj), ppro_build.prev_name(prj)
        self.assertNotEqual(a, b)
        self.assertTrue(a.name.startswith("X[1]_RE_EDIT_prev_"))
        a.write_text("x", encoding="utf-8")
        with mock.patch.object(ppro_build, "project_prefix", return_value="RE"):
            p = Paths(tmp / "C", "X[1]")
            p.project = tmp / "proj"
            (p.project / "07_premiere/project").mkdir(parents=True)
            parked = p.project / "07_premiere/project" / a.name
            a.rename(parked)
            self.assertEqual(ppro_build.parked_previous(p)["file"], str(parked))


if __name__ == "__main__":
    unittest.main()
