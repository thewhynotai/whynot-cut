"""`reel serve` engine state (3.0 Addendum C2.3 / C2.4): <engine home>/state/active.json -> PanelState (client, item,
pipeline, approval, qc), read from the item's own evidence files and never written; and the panel build stamp checked
against <plugin>/adobe/expected.json. Run:
    bash tools/test.sh -p test_serve_engine_state.py
Every test builds a fixture client tree under a temp folder (Arabic names included) and a temp engine home.
"""
import sys as _sys
_sys.dont_write_bytecode = True  # keep the plugin folder free of __pycache__
import _isolation  # noqa: F401,E402  G79: sandbox the engine home before anything else (see tests/_isolation.py)
import hashlib
import json
import os
import shutil
import sys
import tempfile
import time
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

SK = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SK / "engine" / "reel"))

from contract import validate  # noqa: E402
from lib import common  # noqa: E402
from lib.plan import APPROVAL_FORMAT, plan_fingerprint  # noqa: E402
from serve import engine_state as ES, messages  # noqa: E402

NOW = datetime(2026, 10, 13, 12, 0, 0, tzinfo=timezone.utc)
SPEC = {"fps": 30, "duration_frames": 900, "events": [], "main_segments": [], "generated": "2026-10-13T11:00:00+00:00"}
STEPS = ["transcript", "plan", "approve", "build", "frames", "qc", "handoff"]


def iso(dt):
    return dt.isoformat()


def write(path: Path, data) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(data, (dict, list)):
        path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    elif isinstance(data, bytes):
        path.write_bytes(data)
    else:
        path.write_text(data, encoding="utf-8")
    return path


def tree(root: Path) -> dict:
    """{relative path: (size, mtime_ns, sha1)} of every file under root: proves a read changed nothing."""
    out = {}
    for p in sorted(root.rglob("*")):
        if p.is_file():
            st = p.stat()
            out[str(p.relative_to(root))] = (st.st_size, st.st_mtime_ns, hashlib.sha1(p.read_bytes()).hexdigest())
    return out


class Base(unittest.TestCase):
    client_name = "Dr Nour"
    item = "C0239"

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="wnc-es-"))
        self.home = self.tmp / "home"
        self.home.mkdir()
        self.root = self.tmp / "clients" / self.client_name
        for d in ("assets", "data"):
            (self.root / d).mkdir(parents=True)
        self.project = self.root / "output" / "projects" / self.item
        self.project.mkdir(parents=True)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def p(self, rel) -> Path:
        return self.project / rel

    def activate(self, **over):
        rec = {"client_root": str(self.root), "item": self.item, "stage": "plan", "session_id": "sess-1",
               "claude_pid": 4242, "at": iso(NOW - timedelta(minutes=5))}
        rec.update(over)
        return write(self.home / "state" / "active.json", rec)

    def fields(self, now=NOW):
        return ES.panel_fields(self.home, now=now)

    def steps(self, f):
        return {s["id"]: s["state"] for s in f["pipeline"]}

    def assert_valid_state(self, f):
        st = messages.state("offline", None, "s-1", f)
        self.assertEqual(validate(st, "session#/$defs/state"), [], st)
        return st

    def compiled_plan(self, spec=None):
        write(self.p("01_analysis/timeline-spec.json"), spec or SPEC)
        write(self.p("01_analysis/edit-plan.md"), "# Edit plan — C0239\n\nHook: «الصحة أولاً»\n")

    def fingerprint(self):
        return plan_fingerprint(common.Paths(self.root, self.item))

    def approve(self, fp=None):
        write(self.p("01_analysis/plan-approval.json"),
              {"approved": True, "by": "editor", "note": "", "at": iso(NOW), "plan_fingerprint": fp or self.fingerprint(),
               "format": APPROVAL_FORMAT})


# ------------------------------------------------------------------------------------------------------ active.json
class ActiveFile(Base):
    def test_missing_means_no_item(self):
        f = self.fields()
        self.assertEqual(f, {"client": "", "item": "", "pipeline": [], "approval": None, "qc": []})
        self.assert_valid_state(f)

    def test_a_fresh_valid_record_names_the_client_and_item(self):
        self.activate()
        f = self.fields()
        self.assertEqual((f["client"], f["item"]), ("Dr Nour", "C0239"))
        self.assertEqual([s["id"] for s in f["pipeline"]], STEPS)
        self.assertEqual(set(self.steps(f).values()), {"pending"})
        self.assertIsNone(f["approval"])
        self.assertEqual(f["qc"], [])
        self.assert_valid_state(f)

    def test_oversized_invalid_or_not_json_means_no_item(self):
        good = json.loads(self.activate().read_text(encoding="utf-8"))
        cases = [
            json.dumps(dict(good, stage="x" * 40)) + " " * (ES.ACTIVE_MAX + 1),        # valid JSON, over 64 KiB
            "{not json", "[]", "null", json.dumps(dict(good, extra=1)),
            json.dumps({k: v for k, v in good.items() if k != "at"}), json.dumps(dict(good, at="yesterday")),
            json.dumps(dict(good, claude_pid="1")), b"\xff\xfe\x00garbage",
        ]
        for raw in cases:
            write(self.home / "state" / "active.json", raw)
            self.assertEqual(self.fields()["item"], "", repr(raw)[:80])
        self.activate()
        self.assertEqual(self.fields()["item"], "C0239")

    def test_exactly_64_kib_is_still_read(self):
        rec = json.loads(self.activate().read_text(encoding="utf-8"))
        text = json.dumps(rec)
        write(self.home / "state" / "active.json", text + " " * (ES.ACTIVE_MAX - len(text.encode())))
        self.assertEqual((self.home / "state" / "active.json").stat().st_size, ES.ACTIVE_MAX)
        self.assertEqual(self.fields()["item"], "C0239")

    def test_stale_after_12_hours_and_a_future_time_beyond_the_skew(self):
        self.activate(at=iso(NOW - timedelta(hours=12, seconds=1)))
        self.assertEqual(self.fields()["item"], "")
        self.activate(at=iso(NOW - timedelta(hours=11, minutes=59)))
        self.assertEqual(self.fields()["item"], "C0239")
        self.activate(at=(NOW - timedelta(hours=2)).astimezone(timezone(timedelta(hours=3))).isoformat())   # +03:00
        self.assertEqual(self.fields()["item"], "C0239")
        self.activate(at=iso(NOW + timedelta(minutes=10)))
        self.assertEqual(self.fields()["item"], "")
        self.activate(at=iso(NOW + timedelta(minutes=1)))
        self.assertEqual(self.fields()["item"], "C0239")

    def test_the_default_clock_is_now(self):
        self.activate(at=iso(datetime.now(timezone.utc)))
        self.assertEqual(ES.panel_fields(self.home)["item"], "C0239")

    def test_path_traversal_in_item_is_refused(self):
        outside = self.root / "output" / "secret"
        outside.mkdir(parents=True)
        for item in ("..", ".", "../secret", "..\\secret", "a/b", "a\\b", "C:x", "C0239 ", " C0239", "C0239.", "x\x00y"):
            self.activate(item=item)
            self.assertEqual(self.fields()["item"], "", repr(item))

    def test_path_traversal_or_a_relative_client_root_is_refused(self):
        rel = os.path.relpath(self.root, Path.cwd()) if self.root.drive == Path.cwd().drive else "clients/Dr Nour"
        bad = [str(self.root / ".." / self.client_name), str(self.root) + "/../" + self.client_name, rel, "Dr Nour",
               str(self.tmp / "missing"), str(self.home / "state" / "active.json"), str(self.root) + "\x00"]
        for root in bad:
            self.activate(client_root=root)
            self.assertEqual(self.fields()["item"], "", repr(root))

    @unittest.skipIf(sys.platform == "win32", "creating a symlink needs a privilege on Windows")
    def test_an_item_folder_that_links_out_of_the_client_is_refused(self):
        elsewhere = self.tmp / "elsewhere"
        (elsewhere / "01_analysis").mkdir(parents=True)
        (self.root / "output" / "projects" / "LINK").symlink_to(elsewhere, target_is_directory=True)
        self.activate(item="LINK")
        self.assertEqual(self.fields()["item"], "")

    def test_a_directory_in_place_of_the_file_or_an_unreadable_home(self):
        (self.home / "state" / "active.json").mkdir(parents=True)
        self.assertEqual(self.fields()["item"], "")
        self.assertEqual(ES.panel_fields(self.tmp / "no-such-home", now=NOW)["item"], "")


class ArabicPaths(Base):
    client_name = "د. نور الهدى"
    item = "C0239"

    def test_arabic_client_folder_and_evidence(self):
        self.activate()
        self.compiled_plan()
        f = self.fields()
        self.assertEqual((f["client"], f["item"]), ("د. نور الهدى", "C0239"))
        self.assertIn("«الصحة أولاً»", f["approval"]["summary"])
        st = self.assert_valid_state(f)
        json.dumps(st, ensure_ascii=False).encode("utf-8")


class ArabicItem(Base):
    client_name = "عيادة"
    item = "حلقة 3"

    def test_a_clip_named_in_arabic_is_a_valid_item(self):
        self.activate()
        write(self.p("02_transcription/transcript.json"), {"segments": []})
        f = self.fields()
        self.assertEqual(f["item"], "حلقة 3")
        self.assertEqual(self.steps(f)["transcript"], "done")


# ------------------------------------------------------------------------------------------------------ evidence
class Pipeline(Base):
    def setUp(self):
        super().setUp()
        self.activate()

    def test_each_step_from_its_evidence_file(self):
        write(self.p("02_transcription/transcript.json"), {"segments": []})
        self.assertEqual(self.steps(self.fields())["transcript"], "done")
        self.compiled_plan()
        s = self.steps(self.fields())
        self.assertEqual((s["plan"], s["approve"]), ("done", "waiting"))
        self.approve()
        s = self.steps(self.fields())
        self.assertEqual(s["approve"], "done")
        for status, want in (("PRPROJ_BUILT", "done"), ("PRPROJ_BUILT_WITH_ISSUES", "done"), ("FAILED", "failed"),
                             ("SOMETHING_NEW", "pending")):
            write(self.p("07_premiere/ppro-build-result.json"), {"status": status, "project": "x.prproj", "at": iso(NOW)})
            self.assertEqual(self.steps(self.fields())["build"], want, status)
        for verdict, want in (("pass", "done"), ("fail", "failed")):
            write(self.p("08_quality_control/visual-verification.json"), {"verdict": verdict, "notes": "", "by": "claude"})
            self.assertEqual(self.steps(self.fields())["frames"], want, verdict)
        for ok, want in ((True, "done"), (False, "failed")):
            write(self.p("08_quality_control/qc-results.json"), {"ok": ok, "checks": [], "failed": []})
            self.assertEqual(self.steps(self.fields())["qc"], want, ok)
        write(self.p("09_handoff/README.md"), "# Handoff\n")
        f = self.fields()
        self.assertEqual(self.steps(f)["handoff"], "done")
        self.assert_valid_state(f)

    def test_broken_evidence_files_read_as_not_done(self):
        for rel in ("07_premiere/ppro-build-result.json", "08_quality_control/visual-verification.json",
                    "08_quality_control/qc-results.json"):
            write(self.p(rel), "{broken")
        s = self.steps(self.fields())
        self.assertEqual((s["build"], s["frames"], s["qc"]), ("pending", "pending", "pending"))
        write(self.p("08_quality_control/qc-results.json"), b"{" + b" " * (ES.EVIDENCE_MAX + 1) + b"}")
        self.assertEqual(self.steps(self.fields())["qc"], "pending")


class Approval(Base):
    def setUp(self):
        super().setUp()
        self.activate()

    def test_no_compiled_plan_no_card(self):
        f = self.fields()
        self.assertIsNone(f["approval"])
        self.assertEqual(self.steps(f)["approve"], "pending")

    def test_card_carries_the_current_plan_fingerprint_summary_and_preview(self):
        self.compiled_plan()
        f = self.fields()
        a = f["approval"]
        self.assertEqual(a["fingerprint"], self.fingerprint())
        self.assertTrue(a["summary"].startswith("# Edit plan — C0239"))
        self.assertIsNone(a["preview_mp4"])
        self.assertEqual(a["flagged"], [])
        pv = write(self.p("08_quality_control/preview/C0239_preview.mp4"), b"\x00\x00")
        self.assertEqual(Path(self.fields()["approval"]["preview_mp4"]), pv)
        self.assert_valid_state(f)

    def test_a_current_approval_clears_the_card_and_a_changed_plan_brings_it_back(self):
        self.compiled_plan()
        self.approve()
        f = self.fields()
        self.assertIsNone(f["approval"])
        self.assertEqual(self.steps(f)["approve"], "done")
        self.compiled_plan(dict(SPEC, duration_frames=901))           # re-plan: the approval is for another plan
        f = self.fields()
        self.assertEqual(self.steps(f)["approve"], "waiting")
        self.assertEqual(f["approval"]["fingerprint"], self.fingerprint())
        self.assertNotEqual(f["approval"]["fingerprint"],
                            json.loads(self.p("01_analysis/plan-approval.json").read_text(encoding="utf-8"))["plan_fingerprint"])

    def test_a_long_summary_is_clipped_and_a_huge_spec_is_not_read(self):
        self.compiled_plan()
        write(self.p("01_analysis/edit-plan.md"), "x" * 30000)
        self.assertLessEqual(len(self.fields()["approval"]["summary"]), 20000)
        write(self.p("01_analysis/timeline-spec.json"), b"{" + b" " * (ES.EVIDENCE_MAX + 1) + b"}")
        f = self.fields()
        self.assertIsNone(f["approval"])
        self.assertNotEqual(self.steps(f)["approve"], "done")


class QcTiles(Base):
    def setUp(self):
        super().setUp()
        self.activate()
        self.run1 = self.p("08_quality_control/premiere_frames/run-20261013-100000")
        self.run2 = self.p("08_quality_control/premiere_frames/run-20261013-110000")
        for run in (self.run1, self.run2):
            for ms in (2500, 15000):
                write(run / f"frame_{ms:06d}.png", b"\x89PNG")
            write(run / "_sheet.jpg", b"\xff\xd8")
        write(self.run2 / "._frame_002500.png", b"")                    # macOS metadata twin: never a frame
        write(self.run2 / "notes.png", b"")                              # no milliseconds in the name: skipped

    def record(self, sheet, verdict="pass", **over):
        rec = {"verdict": verdict, "notes": "", "by": "claude", "at": iso(NOW), "recorded_epoch": time.time(),
               "sheet": str(sheet), "sheet_mtime": sheet.stat().st_mtime}
        rec.update(over)
        write(self.p("08_quality_control/visual-verification.json"), rec)

    def test_tiles_come_from_the_newest_run_pending_until_its_sheet_is_verified(self):
        f = self.fields()
        self.assertEqual([(q["t_s"], q["verdict"]) for q in f["qc"]], [(2.5, "pending"), (15.0, "pending")])
        self.assertEqual(Path(f["qc"][0]["file"]), self.run2 / "frame_002500.png")
        self.assertEqual(f["qc"][0]["label"], "")                       # the engine stores no per-frame label
        self.assertRegex(f["qc"][0]["tc"], r"^[0-9]{2}:[0-9]{2}:[0-9]{2}:[0-9]{2}$")
        self.assert_valid_state(f)
        self.record(self.run1 / "_sheet.jpg")                            # an older run's sheet: not these frames
        self.assertEqual({q["verdict"] for q in self.fields()["qc"]}, {"pending"})
        self.record(self.run2 / "_sheet.jpg", "fail")
        self.assertEqual({q["verdict"] for q in self.fields()["qc"]}, {"fail"})
        self.record(self.run2 / "_sheet.jpg", "pass")
        self.assertEqual({q["verdict"] for q in self.fields()["qc"]}, {"pass"})
        self.record(self.run2 / "_sheet.jpg", "pass", sheet_mtime=1.0)  # the sheet was rebuilt after the verdict
        self.assertEqual({q["verdict"] for q in self.fields()["qc"]}, {"pending"})

    def test_the_timecode_follows_the_sequence_rate(self):
        with common.use_context(common.Context(root=self.root, home=self.home)):
            want = common.frame_to_tc(round(15.0 * common.seq_fps()))
        self.assertEqual(self.fields()["qc"][1]["tc"], want)

    def test_at_most_500_tiles(self):
        for ms in range(0, 600):
            write(self.run2 / f"frame_{100000 + ms:06d}.png", b"")
        self.assertEqual(len(self.fields()["qc"]), 500)


class Motion(Base):
    item = "EP02_R03_MO"

    def setUp(self):
        super().setUp()
        self.activate()
        write(self.p("00_inputs/source.json"), {"kind": "motion_reel"})

    def motion_fp(self):
        from lib.motion_plan import fingerprint
        with common.use_context(common.Context(root=self.root, home=self.home)):
            return fingerprint(common.Paths(self.root, self.item))

    def test_motion_plan_card_build_and_frames(self):
        write(self.p("01_analysis/motion-script.json"), {"scenes": []})
        write(self.p("01_analysis/motion-plan.json"), {"fps": 25, "scenes": []})
        write(self.p("01_analysis/motion-plan.md"), "# Motion plan — EP02_R03_MO\n")
        fp = self.motion_fp()
        write(self.p("01_analysis/motion-validation.json"), {"ok": True, "errors": [], "fingerprint": fp})
        write(self.p("08_quality_control/animatic/EP02_R03_MO_animatic.mp4"), b"\x00")
        f = self.fields()
        s = self.steps(f)
        self.assertEqual((s["plan"], s["approve"]), ("done", "waiting"))
        self.assertEqual(f["approval"]["fingerprint"], fp)
        self.assertTrue(f["approval"]["preview_mp4"].endswith("EP02_R03_MO_animatic.mp4"))
        write(self.p("01_analysis/plan-approval.json"), {"approved": True, "by": "editor", "at": iso(NOW),
                                                          "plan_fingerprint": fp, "kind": "motion", "format": APPROVAL_FORMAT})
        write(self.p("04_after_effects/motion-build-result.json"), {"status": "PROJECT_ASSEMBLED"})
        run = self.p("08_quality_control/ae_frames/run-20261013-120000")
        write(run / "F001_s1_hero.png", b"")
        write(run / "_sheet.jpg", b"")
        write(run / "frames.json", {"plan_fingerprint": fp, "frames": [
            {"frame": 50, "scene": "s1", "type": "kinetic_quote", "kind": "hero", "file": "F001_s1_hero.png"},
            {"frame": 10, "scene": "s1", "type": "kinetic_quote", "kind": "evil", "file": "../../outside.png"}]})
        f = self.fields()
        s = self.steps(f)
        self.assertEqual((s["approve"], s["build"]), ("done", "done"))
        self.assertIsNone(f["approval"])
        self.assertEqual([(q["t_s"], q["tc"], q["label"], q["verdict"]) for q in f["qc"]],
                         [(2.0, "00:00:02:00", "s1 hero", "pending")])
        self.assert_valid_state(f)

    def test_an_invalid_or_stale_motion_plan_has_no_card(self):
        write(self.p("01_analysis/motion-plan.json"), {"fps": 25})
        write(self.p("01_analysis/motion-validation.json"), {"ok": False, "errors": ["x"], "fingerprint": "f"})
        f = self.fields()
        self.assertEqual(self.steps(f)["plan"], "failed")
        self.assertIsNone(f["approval"])
        write(self.p("01_analysis/motion-validation.json"), {"ok": True, "errors": [], "fingerprint": "not-current"})
        f = self.fields()
        self.assertIsNone(f["approval"])
        self.assertEqual(self.steps(f)["approve"], "pending")


class ReadOnly(Base):
    def test_reading_writes_nothing_anywhere(self):
        self.activate()
        write(self.p("02_transcription/transcript.json"), {"segments": []})
        self.compiled_plan()
        write(self.p("07_premiere/ppro-build-result.json"), {"status": "PRPROJ_BUILT"})
        run = self.p("08_quality_control/premiere_frames/run-20261013-110000")
        write(run / "frame_002500.png", b"")
        before = (tree(self.tmp), sorted(str(p) for p in self.tmp.rglob("*")))
        for _ in range(3):
            self.fields()
        self.assertEqual((tree(self.tmp), sorted(str(p) for p in self.tmp.rglob("*"))), before)


# ------------------------------------------------------------------------------------------------------ build stamp
class BuildStamp(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="wnc-es-"))
        self.expected = self.tmp / "adobe" / "expected.json"

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_compare_builds(self):
        cases = [("142", "142", "ok"), ("3.0.0.142", "3.0.0.142", "ok"), ("141", "142", "stale"), ("143", "142", "newer"),
                 ("3.0.0.9", "3.0.0.10", "stale"), ("3.0.1", "3.0.0.99", "newer"), ("3.0", "3.0.0", "ok"),
                 ("abc1234 2026-10-13T10:00:00Z", "abc1234 2026-10-13T10:00:00Z", "ok"),   # same stamp: the same build
                 ("abc1234", "def5678", "unknown"), ("142", "abc", "unknown"), ("v142", "142", "unknown"),
                 (None, "142", "unknown"), ("142", None, "unknown"), ("", "", "unknown"), (142, 142, "unknown"),
                 ("1." * 10 + "1", "1", "unknown"), ("9" * 20, "1", "unknown")]
        for panel, expected, want in cases:
            self.assertEqual(messages.compare_builds(panel, expected), want, (panel, expected))

    def test_panel_update_reads_expected_json(self):
        self.assertEqual(ES.panel_update("142", self.expected), "unknown")                    # no expected.json
        write(self.expected, {"product": "3.0.0", "build": "142", "sha": "abc1234"})
        for build, want in (("142", "ok"), ("141", "stale"), ("143", "newer"), ("junk", "unknown"), (None, "unknown")):
            self.assertEqual(ES.panel_update(build, self.expected), want, build)
        for bad in ("{broken", "[]", json.dumps({"product": "3.0.0"}), json.dumps({"build": 142}),
                    json.dumps({"build": "142", "pad": "x" * ES.EXPECTED_MAX})):
            write(self.expected, bad)
            self.assertEqual(ES.panel_update("142", self.expected), "unknown", bad[:40])

    def test_the_default_location_is_the_plugin_adobe_folder(self):
        self.assertEqual(ES.expected_path(), common.PLUGIN_DIR / "adobe" / "expected.json")


if __name__ == "__main__":
    unittest.main()
