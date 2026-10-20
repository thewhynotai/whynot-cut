"""`reel serve` engine state (3.0 Addendum C2.3 / C2.4): <engine home>/state/active.json -> PanelState (client, item,
pipeline, approval, qc), read from the item's own evidence files and never written; and the panel build stamp checked
against <plugin>/adobe/expected.json. Run:
    bash tools/test.sh -p test_serve_engine_state.py
Every test builds a fixture client tree under a temp folder (Arabic names included) and a temp engine home.
"""
import sys as _sys
_sys.dont_write_bytecode = True  # keep the plugin folder free of __pycache__
import _isolation  # noqa: F401,E402  G79: sandbox the engine home before anything else (see tests/_isolation.py)
import contextlib
import hashlib
import json
import math
import os
import re
import shutil
import sys
import tempfile
import time
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

SK = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SK / "engine" / "reel"))

from contract import validate  # noqa: E402
from lib import common  # noqa: E402
from lib.plan import APPROVAL_FORMAT, plan_fingerprint  # noqa: E402
from serve import engine_state as ES, messages  # noqa: E402
import cli as reel_cli  # noqa: E402

# `reel` + one of its registered subcommands, or `reel` + a flag: a command the editor must never see
REEL_COMMAND = re.compile(r"(?<![\w-])reel\s+(?:-|(?:%s)(?![\w-]))" % "|".join(
    re.escape(c) for c in sorted(reel_cli.registered_commands(), key=len, reverse=True)), re.I)

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
        self.assertTrue(a["summary"].startswith("Edit plan — C0239"), a["summary"])   # markdown collapsed
        self.assertIsNone(a["preview_mp4"])
        self.assertEqual(a["flagged"], [])
        pv = write(self.p("08_quality_control/preview/C0239_preview.mp4"), b"\x00\x00")
        # engine_state hands out the RESOLVED path (_check: resolve(strict=True), base resolved too); a temp root behind
        # a link (macOS /var -> /private/var) differs only by that, so both sides are resolved (macOS CI, v3.0.0-p3)
        self.assertEqual(Path(self.fields()["approval"]["preview_mp4"]).resolve(), pv.resolve())
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
        """visual-verification.json as verify.py writes it: its `sheet` comes from common.Paths, so it is resolved (a
        temp root behind a link, macOS /var -> /private/var, would otherwise never match the run's sheet)."""
        rec = {"verdict": verdict, "notes": "", "by": "claude", "at": iso(NOW), "recorded_epoch": time.time(),
               "sheet": str(sheet.resolve()), "sheet_mtime": sheet.stat().st_mtime}
        rec.update(over)
        write(self.p("08_quality_control/visual-verification.json"), rec)

    def test_tiles_come_from_the_newest_run_pending_until_its_sheet_is_verified(self):
        f = self.fields()
        self.assertEqual([(q["t_s"], q["verdict"]) for q in f["qc"]], [(2.5, "pending"), (15.0, "pending")])
        self.assertEqual(Path(f["qc"][0]["file"]).resolve(),                 # the resolved path: see Approval
                         (self.run2 / "frame_002500.png").resolve())
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

    def episode_reel(self, guest="Sara — CEO"):
        """BL-20: a motion reel of episode EP02 whose sheet names the guest, compiled and approved."""
        write(self.p("00_inputs/source.json"), {"kind": "motion_reel", "episode_id": "EP02"})
        self.episode = self.root / "output/episodes/EP02/00_inputs/episode.json"
        write(self.episode, {"episode_id": "EP02", "sheet": {"guest": guest, "avoid": []}})
        write(self.p("00_inputs/speakers.json"), {"people": {"guest": {"name": "Sara"}}, "turns": []})
        write(self.p("01_analysis/motion-script.json"), {"scenes": []})
        write(self.p("01_analysis/motion-plan.json"), {"fps": 25, "scenes": []})
        fp = self.motion_fp()
        write(self.p("01_analysis/motion-validation.json"), {"ok": True, "errors": [], "fingerprint": fp})
        write(self.p("01_analysis/plan-approval.json"), {"approved": True, "by": "editor", "at": iso(NOW),
                                                          "plan_fingerprint": fp, "kind": "motion", "format": APPROVAL_FORMAT})

    def test_a_renamed_guest_in_the_episode_sheet_is_seen_by_the_cached_panel(self):
        """BL-20: the episode.json the motion fingerprint reads is watched: a guest renamed by `reel episode-prep`
        turns the cached approval from done to waiting again, with no file of the item touched."""
        self.episode_reel()
        cache = ES.PanelFields()
        self.assertEqual(self.steps(cache(self.home, now=NOW))["approve"], "done")
        write(self.episode, {"episode_id": "EP02", "sheet": {"guest": "Mona — CEO", "avoid": []}})
        self.assertNotEqual(self.steps(cache(self.home, now=NOW))["approve"], "done")

    def test_caption_words_are_watched_and_checked(self):
        """BL-21: captions-short.srt (read by the motion fingerprint when the plan shows captions) is watched, so a
        caption word fixed by hand turns the cached approval back to waiting, and checked first: an oversized one is
        never handed to the fingerprint."""
        srt = write(self.p("02_transcription/captions-short.srt"), "1\n00:00:00,000 --> 00:00:01,000\nكلمة\n")
        self.episode_reel()
        write(self.p("01_analysis/motion-script.json"), {"captions": "subtitles", "scenes": [{"id": "S01"}]})
        fp = self.motion_fp()
        write(self.p("01_analysis/motion-validation.json"), {"ok": True, "errors": [], "fingerprint": fp})
        write(self.p("01_analysis/plan-approval.json"), {"approved": True, "by": "editor", "at": iso(NOW),
                                                          "plan_fingerprint": fp, "kind": "motion", "format": APPROVAL_FORMAT})
        cache = ES.PanelFields()
        self.assertEqual(self.steps(cache(self.home, now=NOW))["approve"], "done")
        write(srt, "1\n00:00:00,000 --> 00:00:01,000\nغير\n")
        self.assertNotEqual(self.steps(cache(self.home, now=NOW))["approve"], "done")
        write(srt, b" " * (ES.EVIDENCE_MAX + 1))
        with mock.patch("lib.motion_plan.fingerprint", side_effect=AssertionError("called")) as called:
            self.assertNotEqual(self.steps(self.fields())["approve"], "done")
        self.assertEqual(called.call_count, 0)

    def test_an_oversized_episode_json_or_speakers_json_skips_the_motion_fingerprint(self):
        """BL-20: the helper reads them with no cap, so they are checked first like every other input (the control:
        with both fine the helper is called and the approval holds)."""
        import lib.motion_plan as mp
        self.episode_reel()
        with mock.patch("lib.motion_plan.fingerprint", side_effect=mp.fingerprint) as fp:
            self.assertEqual(self.steps(self.fields())["approve"], "done")
        self.assertGreater(fp.call_count, 0)
        for f in (self.episode, self.p("00_inputs/speakers.json")):
            keep = f.read_bytes()
            write(f, b" " * (ES.EVIDENCE_MAX + 1))
            with mock.patch("lib.motion_plan.fingerprint", side_effect=AssertionError("called")) as fp:
                self.assertNotEqual(self.steps(self.fields())["approve"], "done", f.name)
            self.assertEqual(fp.call_count, 0, f.name)
            write(f, keep)
        other = write(self.tmp / "elsewhere.json", self.episode.read_bytes())   # a hard link: another file's text
        self.episode.unlink()
        os.link(other, self.episode)
        with mock.patch("lib.motion_plan.fingerprint", side_effect=AssertionError("called")) as fp:
            self.assertNotEqual(self.steps(self.fields())["approve"], "done")
        self.assertEqual(fp.call_count, 0, "hard-linked episode.json")


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


# ------------------------------------------------------------------------------------------------------ review round 1
# The approval footers exactly as the engine writes them (lib/plan.py write_edit_plan, lib/motion_plan.py
# write_motion_md); EngineSummary checks they are still in those files, so a changed footer re-runs this review.
EDIT_FOOTER = "**To approve:** reply 'approved' (or list changes). Adobe builds wait for `reel approve-plan`."
MOTION_ANIMATIC = "not rendered yet (`reel motion-animatic`)"
MOTION_FOOTER = "**To approve:** the editor says so; the lead records `reel approve-plan --by editor`."
EDIT_MD = "\n".join([
    "# Edit Plan — C0239 (for editor approval)", "",
    "Runtime 00:00:30:00 at 30 fps · 3 graphics · 1 camera moves (+0 automatic jump-cut zooms) · 2 SFX cues",
    "", "Times are on the reel's timeline (after pause removal and word cuts).", "",
    "## Decisions", "", "| # | Time | Treatment | On-screen text | Why (speaker's words) | Approval |",
    "|---|---|---|---|---|---|", "| D1 | 00:00:01:00 | statement_bar | «الصحة أولاً» | health first | YES |", "",
    "Run `reel plan --root X` again after changes.", "Claude Code records the approval.",
    "", "Music: PLACED — bed.mp3 at -24 dB, 2 s fade-out", "", EDIT_FOOTER, ""])
MOTION_MD = "\n".join([
    "# Motion plan — EP02_R03_MO (approve the plan before After Effects)", "", "story · 9x16 · RTL · 30.0 s · 4 scenes",
    "", "## Editorial lines (Claude's words, not the speaker's)", "", "- s1 headline: الخلاصة", "",
    f"Animatic: {MOTION_ANIMATIC}", "", MOTION_FOOTER, ""])


def strings(obj):
    """Every string inside a JSON value (keys too)."""
    if isinstance(obj, str):
        yield obj
    elif isinstance(obj, dict):
        for k, v in obj.items():
            yield k
            yield from strings(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from strings(v)


class EngineSummary(Base):
    """C1.4 / C2.2: the approval card is for the editor. No `reel ` command, no backtick, no "Claude Code", no
    "reply 'approved'" chat instruction reaches any PanelState string."""

    def setUp(self):
        super().setUp()
        self.activate()

    def assert_editor_safe(self, f):
        """No `reel <subcommand>` / `reel --flag`, no backtick, no "Claude Code", no footer in any PanelState string
        (ordinary words such as "reel", "reply" and "Claude" are the editor's content and stay)."""
        st = self.assert_valid_state(f)
        for s in strings(st["state"]):
            self.assertIsNone(REEL_COMMAND.search(s), s)
            self.assertNotIn("`", s, s)
            self.assertNotRegex(s.lower(), r"claude\s*code", s)
            self.assertNotIn("To approve:", s, s)
            self.assertNotIn("Animatic:", s, s)

    def test_the_footers_are_the_engines_own(self):
        lib = SK / "engine" / "reel" / "lib"
        self.assertIn(EDIT_FOOTER, (lib / "plan.py").read_text(encoding="utf-8"))
        motion = (lib / "motion_plan.py").read_text(encoding="utf-8")
        self.assertIn(MOTION_FOOTER, motion)
        self.assertIn(MOTION_ANIMATIC, motion)

    def test_edit_plan_summary_has_no_commands_and_no_markdown(self):
        self.compiled_plan()
        write(self.p("01_analysis/edit-plan.md"), EDIT_MD)
        f = self.fields()
        summary = f["approval"]["summary"]
        self.assertTrue(summary.startswith("Edit Plan — C0239 (for editor approval)"), summary)
        self.assertIn("«الصحة أولاً»", summary)
        self.assertIn("Times are on the reel's timeline", summary)    # "reel's" is a word, not a command
        self.assertIn("Music: PLACED", summary)
        self.assertIn("D1 · 00:00:01:00 · statement_bar", summary)     # a table row reads as one line
        self.assertNotIn("#", summary)
        self.assertNotIn("**", summary)
        self.assertNotIn("|", summary)
        self.assertNotIn("\n\n\n", summary)
        self.assertIn("Run again after changes.", summary)            # the command token goes, the sentence stays
        self.assertIn("Claude records the approval.", summary)
        self.assert_editor_safe(f)

    def test_motion_plan_summary_has_no_commands(self):
        self.item = "EP02_R03_MO"
        self.project = self.root / "output" / "projects" / self.item
        self.activate(item=self.item)
        write(self.p("00_inputs/source.json"), {"kind": "motion_reel"})
        write(self.p("01_analysis/motion-script.json"), {"scenes": []})
        write(self.p("01_analysis/motion-plan.json"), {"fps": 25, "scenes": []})
        write(self.p("01_analysis/motion-plan.md"), MOTION_MD)
        from lib.motion_plan import fingerprint
        with common.use_context(common.Context(root=self.root, home=self.home)):
            fp = fingerprint(common.Paths(self.root, self.item))
        write(self.p("01_analysis/motion-validation.json"), {"ok": True, "errors": [], "fingerprint": fp})
        f = self.fields()
        summary = f["approval"]["summary"]
        self.assertTrue(summary.startswith("Motion plan — EP02_R03_MO"), summary)
        self.assertIn("Claude's words", summary)                     # an engine heading, not the product name
        self.assertNotIn("Animatic", summary)
        self.assert_editor_safe(f)

    def test_the_editor_summary_function(self):
        self.assertEqual(ES.editor_summary(EDIT_FOOTER), "")
        self.assertEqual(ES.editor_summary("A\n\n\n\nB\n**To approve:** reply 'approved'\nstill footer\n\nC"), "A\n\nB\n\nC")
        self.assertEqual(ES.editor_summary("## To approve\nreply here\n## Next\nD"),     # not the engine's footer
                         "To approve\nreply here\nNext\nD")
        self.assertEqual(ES.editor_summary("| a | b |\n|:--|--:|\n| **c** | [d](http://x) |"), "a · b\nc · d")
        self.assertEqual(ES.editor_summary("Use claude to ask\nkeep"), "Use claude to ask\nkeep")
        self.assertEqual(ES.editor_summary("\r\n\r\nA\r\n"), "A")
        self.assertLessEqual(len(ES.editor_summary("x" * 30000)), ES.SUMMARY_MAX)


class HelperInputs(Base):
    """The engine helpers (approval_state, plan_fingerprint, motion_plan.fingerprint, seq_fps) read files with no cap:
    every file they would read is checked first (a regular file under the cap, inside its folder, one link); any other
    means the helper is not called at all."""

    def setUp(self):
        super().setUp()
        self.activate()

    @contextlib.contextmanager
    def never(self, *targets):
        """Patch the helpers; none may be called (a raise inside would be swallowed as "unreadable", so count)."""
        with contextlib.ExitStack() as stack:
            mocks = [stack.enter_context(mock.patch(t, side_effect=AssertionError(t))) for t in targets]
            yield
        for t, m in zip(targets, mocks):
            self.assertEqual(m.call_count, 0, f"{t} was called over a refused input")

    def test_the_helpers_are_called_when_their_inputs_are_fine(self):
        """The control for the tests below: the patch targets are the ones engine_state really calls."""
        import lib.plan as plan
        self.compiled_plan()
        self.approve()
        write(self.p("08_quality_control/premiere_frames/run-20261013-110000/frame_001000.png"), b"")
        with mock.patch("lib.plan.approval_state", side_effect=plan.approval_state) as a,                 mock.patch("lib.common.seq_fps", side_effect=common.seq_fps) as fps:
            self.assertEqual(self.steps(self.fields())["approve"], "done")
        self.assertGreater(a.call_count, 0)
        self.assertGreater(fps.call_count, 0)

    def test_an_oversized_approval_record_is_not_handed_to_approval_state(self):
        self.compiled_plan()
        write(self.p("01_analysis/plan-approval.json"), b"{" + b" " * (ES.EVIDENCE_MAX + 1) + b"}")
        with self.never("lib.plan.approval_state"):
            f = self.fields()
        self.assertNotEqual(self.steps(f)["approve"], "done")

    def test_a_folder_in_place_of_a_motion_fingerprint_input_skips_the_helper(self):
        write(self.p("00_inputs/source.json"), {"kind": "motion_reel"})
        write(self.p("01_analysis/motion-plan.json"), {"fps": 25, "scenes": []})
        write(self.p("01_analysis/motion-validation.json"), {"ok": True, "errors": [], "fingerprint": "f"})
        self.p("02_transcription/words.json").mkdir(parents=True)
        with self.never("lib.motion_plan.fingerprint", "lib.plan.approval_state"):
            f = self.fields()
        self.assertIsNone(f["approval"])
        self.assertEqual(self.steps(f)["approve"], "pending")

    def test_an_oversized_brand_token_file_skips_the_motion_fingerprint(self):
        write(self.p("00_inputs/source.json"), {"kind": "motion_reel"})
        write(self.p("01_analysis/motion-plan.json"), {"fps": 25, "scenes": []})
        write(self.p("01_analysis/motion-validation.json"), {"ok": True, "errors": [], "fingerprint": "f"})
        write(self.root / "output/client_database/branding/brand-tokens.json", b" " * (ES.EVIDENCE_MAX + 1))
        with self.never("lib.motion_plan.fingerprint"):
            self.assertIsNone(self.fields()["approval"])

    def test_a_refused_sequence_config_falls_back_to_the_default_rate_without_seq_fps(self):
        run = self.p("08_quality_control/premiere_frames/run-20261013-110000")
        write(run / "frame_015000.png", b"")
        (self.root / common.CLIENT_PROFILE_REL / "sequence-settings.json").mkdir(parents=True)
        with self.never("lib.common.seq_fps"):
            qc = self.fields()["qc"]
        self.assertEqual([(q["t_s"], q["tc"]) for q in qc],
                         [(15.0, common.frame_to_tc(15 * common.SEQ_FPS, common.SEQ_FPS))])

    def test_a_profile_id_that_is_a_path_is_refused(self):
        write(self.root / common.CLIENT_PROFILE_REL / "profile.json", {"id": "../../../elsewhere"})
        run = self.p("08_quality_control/premiere_frames/run-20261013-110000")
        write(run / "frame_001000.png", b"")
        with self.never("lib.common.seq_fps"):
            self.assertEqual(len(self.fields()["qc"]), 1)

    @unittest.skipUnless(hasattr(os, "mkfifo"), "FIFOs are POSIX")
    def test_a_fifo_is_never_opened(self):
        self.compiled_plan()
        os.unlink(self.p("01_analysis/edit-plan.md"))
        os.mkfifo(self.p("01_analysis/edit-plan.md"))
        os.mkfifo(self.p("01_analysis/plan-approval.json"))
        t0 = time.monotonic()
        f = self.fields()
        self.assertLess(time.monotonic() - t0, 2.0)
        self.assertNotEqual(self.steps(f)["approve"], "done")
        self.assertEqual((f["approval"] or {}).get("summary", ""), "")


class Confinement(Base):
    """Every evidence file must resolve inside the item folder and have one link (a hard link on Windows needs no
    privilege and would show another file's text or verdict)."""

    def setUp(self):
        super().setUp()
        self.activate()
        self.outside = write(self.tmp / "secret" / "notes.md", "SECRET TEXT\n")

    def test_a_hard_linked_evidence_file_is_refused(self):
        self.compiled_plan()
        os.unlink(self.p("01_analysis/edit-plan.md"))
        os.link(self.outside, self.p("01_analysis/edit-plan.md"))
        self.assertEqual(self.fields()["approval"]["summary"], "")
        ok = write(self.tmp / "secret" / "qc.json", {"ok": True})
        self.p("08_quality_control").mkdir(parents=True, exist_ok=True)
        os.link(ok, self.p("08_quality_control/qc-results.json"))
        self.assertEqual(self.steps(self.fields())["qc"], "pending")

    def test_a_symlinked_evidence_file_that_leaves_the_item_is_refused(self):
        self.compiled_plan()
        os.unlink(self.p("01_analysis/edit-plan.md"))
        try:
            os.symlink(self.outside, self.p("01_analysis/edit-plan.md"))
        except OSError:
            self.skipTest("creating a symlink needs a privilege here")
        self.assertEqual(self.fields()["approval"]["summary"], "")

    def test_a_symlinked_run_folder_that_leaves_the_item_gives_no_tiles(self):
        elsewhere = self.tmp / "elsewhere-run"
        write(elsewhere / "frame_001000.png", b"")
        self.p("08_quality_control/premiere_frames").mkdir(parents=True)
        try:
            os.symlink(elsewhere, self.p("08_quality_control/premiere_frames/run-20261013-110000"),
                       target_is_directory=True)
        except OSError:
            self.skipTest("creating a symlink needs a privilege here")
        self.assertEqual(self.fields()["qc"], [])


class Numbers(Base):
    def setUp(self):
        super().setUp()
        self.activate()

    def test_ms_tokens_are_ascii_digits_only(self):
        run = self.p("08_quality_control/premiere_frames/run-20261013-110000")
        write(run / "frame_٢٥٠٠.png", b"")                              # Arabic-Indic digits: int() would take them
        write(run / "frame_²5.png", b"")                                 # isdigit() but int() raises
        write(run / "frame_001000.png", b"")
        self.assertEqual([q["t_s"] for q in self.fields()["qc"]], [1.0])
        self.assertIsNone(ES._ms_of("frame_٢٥٠٠.png"))
        self.assertIsNone(ES._ms_of("frame_²5.png"))
        self.assertEqual(ES._ms_of("frame_002500.png"), 2500)

    def test_a_huge_frame_name_is_dropped_and_finite(self):
        run = self.p("08_quality_control/premiere_frames/run-20261013-110000")
        write(run / ("frame_" + "9" * 200 + ".png"), b"")
        write(run / "frame_001000.png", b"")
        f = self.fields()
        self.assertEqual([q["t_s"] for q in f["qc"]], [1.0])           # a timecode over TC_MAX: dropped, never cut
        self.assertIsNone(ES._tile(1.0, "1" * (ES.TC_MAX + 1), "f.png", "", "pending"))
        self.assertEqual(ES._tile(1.0, "1" * ES.TC_MAX, "f.png", "", "pending")["tc"], "1" * ES.TC_MAX)
        for q in f["qc"]:
            self.assertLessEqual(len(q["tc"]), 32)
            self.assertTrue(math.isfinite(q["t_s"]))
        json.dumps(self.assert_valid_state(f), allow_nan=False)

    def test_non_finite_motion_numbers_are_dropped(self):
        write(self.p("00_inputs/source.json"), {"kind": "motion_reel"})
        run = self.p("08_quality_control/ae_frames/run-20261013-120000")
        write(run / "a.png", b"")
        write(run / "b.png", b"")
        write(run / "frames.json", '{"frames": [{"frame": 50, "scene": "s1", "kind": "hero", "file": "a.png"},'
                                   ' {"frame": 1' + "0" * 400 + ', "scene": "s2", "kind": "x", "file": "b.png"}]}')
        for fps in ("Infinity", "NaN", "-Infinity", "1e400"):
            write(self.p("01_analysis/motion-plan.json"), '{"fps": %s, "scenes": []}' % fps)
            self.assertEqual(self.fields()["qc"], [], fps)
        write(self.p("01_analysis/motion-plan.json"), {"fps": 25, "scenes": []})
        f = self.fields()
        self.assertEqual([(q["t_s"], q["label"]) for q in f["qc"]], [(2.0, "s1 hero")])
        json.dumps(self.assert_valid_state(f), allow_nan=False)


class Cache(Base):
    """The panel polls a snapshot every 2 s: an unchanged item must not be re-hashed."""

    def setUp(self):
        super().setUp()
        self.activate()
        self.compiled_plan()
        self.cache = ES.PanelFields()

    def test_unchanged_files_are_not_read_again(self):
        import lib.plan as plan
        with mock.patch("lib.plan.plan_fingerprint", side_effect=plan.plan_fingerprint) as fp:
            a = self.cache(self.home, now=NOW)
            n = fp.call_count
            self.assertGreater(n, 0)
            b = self.cache(self.home, now=NOW)
            self.assertEqual(fp.call_count, n)
        self.assertEqual(a, b)
        b["pipeline"].clear()                                          # a caller cannot spoil the cached value
        self.assertEqual(self.cache(self.home, now=NOW), a)

    def test_a_changed_evidence_file_or_active_json_is_read_again(self):
        first = self.cache(self.home, now=NOW)
        self.approve()
        self.assertEqual(self.steps(self.cache(self.home, now=NOW))["approve"], "done")
        write(self.p("09_handoff/README.md"), "# Handoff\n")
        self.assertEqual(self.steps(self.cache(self.home, now=NOW))["handoff"], "done")
        run = self.p("08_quality_control/premiere_frames/run-20261013-110000")
        write(run / "frame_001000.png", b"")
        self.assertEqual(len(self.cache(self.home, now=NOW)["qc"]), 1)
        write(run / "frame_002000.png", b"")
        self.assertEqual(len(self.cache(self.home, now=NOW)["qc"]), 2)
        self.activate(item="../x")
        self.assertEqual(self.cache(self.home, now=NOW)["item"], "")
        self.activate()
        self.assertEqual(self.cache(self.home, now=NOW)["item"], "C0239")
        self.assertNotEqual(first, self.cache(self.home, now=NOW))

    def test_a_frame_added_or_removed_within_one_folder_clock_tick_is_seen(self):
        """Why the test above failed about 1 run in 5 on Windows: NTFS stamps a folder's mtime from a clock that moves
        in ticks (about 1-16 ms), so a frame written into a run folder in the same tick as the folder's last change
        leaves the folder's whole stat key (mtime, size 0, links, file id, creation time) as it was. The frames are
        listed, not watched one by one, so a key built from the folder's stat alone served the old tile list. Here the
        folder's mtime is put back with os.utime (what one tick does on NTFS); POSIX also moves the folder's ctime, so
        there the folder's stat key is held as it was."""
        run = self.p("08_quality_control/premiere_frames/run-20261013-110000")
        write(run / "frame_001000.png", b"")
        self.assertEqual(len(self.cache(self.home, now=NOW)["qc"]), 1)
        st, key, real = os.stat(run), ES._stat_key(run), ES._stat_key

        def one_tick():                                                 # the folder looks as it did at the last call
            os.utime(run, ns=(st.st_atime_ns, st.st_mtime_ns))
            if os.name == "nt":
                self.assertEqual(ES._stat_key(run), key, "NTFS: the folder's stat key did not change")
        with mock.patch.object(ES, "_stat_key", side_effect=lambda p: key if Path(p) == run else real(p)):
            write(run / "frame_002000.png", b"")
            one_tick()
            self.assertEqual(len(self.cache(self.home, now=NOW)["qc"]), 2, "a frame added in one tick")
            (run / "frame_002000.png").unlink()
            one_tick()
            self.assertEqual(len(self.cache(self.home, now=NOW)["qc"]), 1, "a frame removed in one tick")

    def test_staleness_is_checked_on_every_call(self):
        self.assertEqual(self.cache(self.home, now=NOW)["item"], "C0239")
        self.assertEqual(self.cache(self.home, now=NOW + timedelta(hours=13))["item"], "")


class NetworkClientRoot(Base):
    """A UNC client_root (a NAS) is accepted, but one whose existence check takes longer than UNC_PROBE_S is skipped
    (no item) and not touched again for UNC_RETRY_S."""

    def tearDown(self):
        ES._SLOW_ROOTS.clear()
        super().tearDown()

    def test_a_slow_network_root_is_skipped_then_left_alone(self):
        self.activate()
        calls = []

        def slow(p):
            calls.append(p)
            time.sleep(0.2)
            return p.resolve(strict=True)
        with mock.patch.object(ES, "_is_unc", return_value=True), mock.patch.object(ES, "UNC_PROBE_S", 0.05), \
                mock.patch.object(ES, "_probe_root", side_effect=slow):
            self.assertEqual(self.fields()["item"], "")
            self.assertEqual(self.fields()["item"], "")
        self.assertEqual(len(calls), 1, "a slow root is not probed again within UNC_RETRY_S")

    def test_a_quick_network_root_is_accepted(self):
        self.activate()
        with mock.patch.object(ES, "_is_unc", return_value=True):
            self.assertEqual(self.fields()["item"], "C0239")

    def test_unc_detection(self):
        for raw in ("\\\\nas\\clients\\Dr Nour", "//nas/clients/Dr Nour"):
            self.assertTrue(ES._is_unc(raw), raw)
        for raw in ("C:\\clients\\Dr Nour", "/Users/x/clients"):
            self.assertFalse(ES._is_unc(raw), raw)


# ------------------------------------------------------------------------------------------------------ review round 2
# A realistic edit plan whose decision rows hold the words "reel", "reply" and "Claude" and backticked words: the editor
# approves these rows, so every one of them must reach the card; only the command tokens and the footer go.
ROWS = [
    ("| D1 | 00:00:01:00 | statement_bar | Watch this reel till the end | the reel starts here | YES |",
     "D1 · 00:00:01:00 · statement_bar · Watch this reel till the end · the reel starts here · YES"),
    ("| D2 | 00:00:04:12 | +8% punch-in; statement_bar | Reply to the doctor | reply in the comments |  |",
     "D2 · 00:00:04:12 · +8% punch-in; statement_bar · Reply to the doctor · reply in the comments"),
    ("| D3 | 00:00:07:00 | lower_third | Ask Claude, not Google | the word `insulin` twice |  |",
     "D3 · 00:00:07:00 · lower_third · Ask Claude, not Google · the word insulin twice"),
    ("| D4 | 00:00:09:00 | camera only | — | fixed with `reel plan --root X` today |  |",
     "D4 · 00:00:09:00 · camera only · — · fixed with today"),
    ("| D5 | 00:00:12:00 | broll_card | My_reel__v2 | reel approve-plan was run | YES |",
     "D5 · 00:00:12:00 · broll_card · My_reel__v2 · was run · YES"),
    ("| D6 | 00:00:15:00 | statement_bar | `Claude Code` and `npx tsc` | `python3 x.py` / `py` / `reel` |  |",
     "D6 · 00:00:15:00 · statement_bar · and · / /"),
    ("| D7 | 00:00:18:00 | statement_bar | reel reel status works | the `pyramid` of reel --version |  |",
     "D7 · 00:00:18:00 · statement_bar · reel works · the pyramid of"),
]
ROWS_MD = "\n".join([
    "# Edit Plan — C0239 (for editor approval)", "",
    "Runtime 00:00:30:00 at 30 fps · 7 graphics · 1 camera moves (+0 automatic jump-cut zooms) · 0 SFX cues", "",
    "## Decisions", "", "| # | Time | Treatment | On-screen text | Why (speaker's words) | Approval |",
    "|---|---|---|---|---|---|", *[raw for raw, _ in ROWS], "",
    "## Words cut (1): picture, sound and captions", "", "- 00:00:03.200 «reply» (word 12)", "",
    "## Not included (and why)", "", "- the reel intro: Claude suggested it, the editor said no", "",
    "Music: PLACED — My_reel__v2.mp3 at -24 dB, 2 s fade-out", "", EDIT_FOOTER, ""])


class EditorSummaryRows(Base):
    """Round 2: the summary redacts commands token by token; it never drops a line or a row the editor approves."""

    def setUp(self):
        super().setUp()
        self.activate()

    def test_every_decision_row_is_kept_and_every_command_is_gone(self):
        self.compiled_plan()
        write(self.p("01_analysis/edit-plan.md"), ROWS_MD)
        f = self.fields()
        lines = f["approval"]["summary"].split("\n")
        for _, want in ROWS:
            self.assertIn(want, lines)
        self.assertIn("Decisions", lines)                                  # headings keep their rows under them
        self.assertIn("- 00:00:03.200 «reply» (word 12)", lines)
        self.assertIn("- the reel intro: Claude suggested it, the editor said no", lines)
        self.assertIn("Music: PLACED — My_reel__v2.mp3 at -24 dB, 2 s fade-out", lines)
        self.assertEqual(lines[-1], "Music: PLACED — My_reel__v2.mp3 at -24 dB, 2 s fade-out")   # the footer is gone
        EngineSummary.assert_editor_safe(self, f)

    def test_the_real_footers_are_removed(self):
        self.assertEqual(ES.editor_summary("Body\n\n" + EDIT_FOOTER + "\n"), "Body")
        anim = str(self.p("08_quality_control/animatic/EP02_R03_MO_animatic.mp4"))
        for animatic in (anim, MOTION_ANIMATIC):
            md = f"Body\n\n## Warnings\n\n- none\n\nAnimatic: {animatic}\n\n{MOTION_FOOTER}\n"
            self.assertEqual(ES.editor_summary(md), "Body\n\nWarnings\n\n- none", animatic)

    def test_a_double_underscore_name_and_plain_words_survive(self):
        self.assertEqual(ES.editor_summary("File My_reel__v2.mp4 and __init__"), "File My_reel__v2.mp4 and __init__")
        self.assertEqual(ES.editor_summary("Reply to the doctor\nWatch this reel\nAsk Claude"),
                         "Reply to the doctor\nWatch this reel\nAsk Claude")
        self.assertEqual(ES.editor_summary("Use claude --resume to go on"), "Use to go on")
        self.assertEqual(ES.editor_summary("Made in Claude Code."), "Made in Claude.")

    def test_backtick_spans(self):
        cases = [("say `insulin` now", "say insulin now"), ("`reel` alone", "alone"), ("`reel-x`", ""),
                 ("`reel_v2` stays", "reel_v2 stays"), ("``code``", "code"), ("a ` stray", "a stray"),
                 ("`npm` `npx` `python` `python3.12` `py` `py.exe` `claude`", ""), ("`pyramid`", "pyramid"),
                 ("run (`reel motion-animatic`) now", "run now"), ("`two words`", ""), ("` `", "")]
        for md, want in cases:
            self.assertEqual(ES.editor_summary(md), want, md)


class CacheGeneration(Base):
    """G2 H3: serve pushes a state when the engine state changes. The change test is the cache's own: `generation`
    moves only when the fields served differ from the ones served before (a cache hit never compares anything)."""

    def setUp(self):
        super().setUp()
        self.activate()
        self.compiled_plan()
        self.cache = ES.PanelFields()

    def test_generation_moves_only_when_the_fields_change(self):
        g0 = self.cache.generation
        first = self.cache(self.home, now=NOW)
        g1 = self.cache.generation
        self.assertEqual(g1, g0 + 1, "the first read is a change")
        self.assertEqual(self.cache(self.home, now=NOW), first)
        self.assertEqual(self.cache.generation, g1, "a cache hit is no change")
        st = self.p("01_analysis/edit-plan.md").stat()
        os.utime(self.p("01_analysis/edit-plan.md"), ns=(st.st_atime_ns, st.st_mtime_ns + 5_000_000_000))
        self.assertEqual(self.cache(self.home, now=NOW), first)          # a new key, the same fields
        self.assertEqual(self.cache.generation, g1, "a touched file with the same content is no change")
        self.approve()
        self.assertEqual(self.steps(self.cache(self.home, now=NOW))["approve"], "done")
        self.assertEqual(self.cache.generation, g1 + 1)
        (self.home / "state" / "active.json").unlink()
        self.assertEqual(self.cache(self.home, now=NOW)["item"], "")
        self.assertEqual(self.cache.generation, g1 + 2, "no item any more is a change")
        self.cache(self.home, now=NOW)
        self.assertEqual(self.cache.generation, g1 + 2)


class CacheRound2(Base):
    """Round 2: the cache key has the inode and ctime of every watched path and a content hash of the small gate files;
    a read that failed for any reason other than "not found" is never cached."""

    def setUp(self):
        super().setUp()
        self.activate()
        self.cache = ES.PanelFields()

    def rewrite_same_size_keep_mtime(self, path: Path, data: bytes):
        st = path.stat()
        self.assertEqual(len(data), st.st_size)
        with open(path, "r+b") as fh:                                   # in place: the same inode / creation time
            fh.write(data)
        os.utime(path, ns=(st.st_atime_ns, st.st_mtime_ns))
        self.assertEqual((path.stat().st_size, path.stat().st_mtime_ns), (st.st_size, st.st_mtime_ns))

    def test_a_same_size_change_with_the_mtime_kept_is_seen(self):
        qc = write(self.p("08_quality_control/qc-results.json"), b'{"ok": true}')
        self.assertEqual(self.steps(self.cache(self.home, now=NOW))["qc"], "done")
        self.rewrite_same_size_keep_mtime(qc, b'{"ok":false}')
        self.assertEqual(self.steps(self.cache(self.home, now=NOW))["qc"], "failed")

    def test_a_same_size_approval_change_with_the_mtime_kept_is_seen(self):
        self.compiled_plan()
        self.approve()
        p = self.p("01_analysis/plan-approval.json")
        self.assertEqual(self.steps(self.cache(self.home, now=NOW))["approve"], "done")
        raw = p.read_bytes()
        self.assertIn(b'"approved": true,', raw)
        self.rewrite_same_size_keep_mtime(p, raw.replace(b'"approved": true,', b'"approved":false,'))
        f = self.cache(self.home, now=NOW)
        self.assertEqual(self.steps(f)["approve"], "waiting")
        self.assertIsNotNone(f["approval"])

    def test_the_key_has_the_inode_and_ctime(self):
        st = os.stat(self.home)
        key = ES._stat_key(self.home)
        self.assertIn(st.st_ino, key)
        self.assertIn(st.st_ctime_ns, key)

    def test_a_transient_read_failure_is_not_cached(self):
        write(self.p("08_quality_control/qc-results.json"), {"ok": True})
        real_open = os.open
        locked = {"on": True}                                            # another process holds the file for a moment

        def flaky(path, *a, **kw):
            if str(path).endswith("qc-results.json") and locked["on"]:
                raise PermissionError(13, "sharing violation", str(path))
            return real_open(path, *a, **kw)
        with mock.patch.object(ES.os, "open", side_effect=flaky):
            self.assertEqual(self.steps(self.cache(self.home, now=NOW))["qc"], "pending")    # this read failed
            locked["on"] = False                                         # nothing on disk changed
            self.assertEqual(self.steps(self.cache(self.home, now=NOW))["qc"], "done")       # not cached: read again

    def test_a_not_found_read_is_still_cached(self):
        import lib.plan as plan
        self.compiled_plan()
        with mock.patch("lib.plan.plan_fingerprint", side_effect=plan.plan_fingerprint) as fp:
            self.cache(self.home, now=NOW)
            n = fp.call_count
            self.cache(self.home, now=NOW)
            self.assertEqual(fp.call_count, n)


class ApprovalInputsByKind(Base):
    """Round 2: an edit item's approval does not depend on the motion fingerprint's inputs."""

    def setUp(self):
        super().setUp()
        self.activate()

    def test_an_edit_item_ignores_a_refused_motion_input(self):
        self.compiled_plan()
        self.approve()
        write(self.root / "output/client_database/branding/brand-tokens.json", b" " * (ES.EVIDENCE_MAX + 1))
        self.p("02_transcription/words.json").mkdir(parents=True)
        self.assertEqual(self.steps(self.fields())["approve"], "done")

    def test_a_motion_record_still_checks_the_motion_inputs(self):
        self.compiled_plan()
        write(self.p("01_analysis/plan-approval.json"), {"approved": True, "by": "editor", "at": iso(NOW),
                                                          "plan_fingerprint": "f", "kind": "motion",
                                                          "format": APPROVAL_FORMAT})
        self.p("02_transcription/words.json").mkdir(parents=True)
        with mock.patch("lib.plan.approval_state", side_effect=AssertionError("called")) as a:
            self.fields()
        self.assertEqual(a.call_count, 0)


# ------------------------------------------------------------------------------------------------------ build stamp
class BuildStamp(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="wnc-es-"))
        self.expected = self.tmp / "adobe" / "expected.json"

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_compare_builds(self):
        """C1.8: the panel's __WNC_BUILD__ and build.json `build` are one UTC id, YYYYMMDDTHHMMSSZ (package-ccx.mjs
        buildId). Two ids compare as text (= time order). Two present values of any other, differing shape: stale
        (expected.json is the authority, so an old-format panel is told to restart Premiere). Missing or malformed
        (not a string, empty, over 64 characters, a control character): unknown."""
        a, b = "20261013T142530Z", "20261013T142531Z"
        cases = [(a, a, "ok"), (a, b, "stale"), (b, a, "newer"),
                 ("20261012T235959Z", "20261013T000000Z", "stale"), ("20271231T000000Z", "20261231T235959Z", "newer"),
                 ("abc1234", "def5678", "stale"),                       # was "unknown": stale had to be reachable
                 ("abc1234 2026-10-13T10:00Z", a, "stale"),            # a panel from before the shared id
                 (a, "142", "stale"), ("142", a, "stale"), ("143", "142", "stale"), ("v142", "142", "stale"),
                 ("٢٠٢٦١٠١٣T142530Z", a, "stale"),                     # not ASCII digits: not an id
                 ("abc1234 2026-10-13T10:00Z", "abc1234 2026-10-13T10:00Z", "ok"),   # the same text: the same build
                 (None, a, "unknown"), (a, None, "unknown"), ("", a, "unknown"), (a, "", "unknown"), ("", "", "unknown"),
                 (142, 142, "unknown"), ("x" * 65, a, "unknown"), (a, "x" * 65, "unknown"), ("2026\n", a, "unknown"),
                 (a, "a\x00b", "unknown")]
        for panel, expected, want in cases:
            self.assertEqual(messages.compare_builds(panel, expected), want, (panel, expected))

    def test_panel_update_reads_expected_json(self):
        a = "20261013T142530Z"
        self.assertEqual(ES.panel_update(a, self.expected), "unknown")                       # no expected.json
        write(self.expected, {"product": "3.0.0", "build": a, "sha": "abc1234"})
        for build, want in ((a, "ok"), ("20261013T142529Z", "stale"), ("20261013T142531Z", "newer"),
                            ("abc1234 2026-10-13T10:00Z", "stale"), (None, "unknown"), ("", "unknown")):
            self.assertEqual(ES.panel_update(build, self.expected), want, build)
        for bad in ("{broken", "[]", json.dumps({"product": "3.0.0"}), json.dumps({"build": 142}),
                    json.dumps({"build": a, "pad": "x" * ES.EXPECTED_MAX})):
            write(self.expected, bad)
            self.assertEqual(ES.panel_update(a, self.expected), "unknown", bad[:40])

    def test_the_schema_documents_the_build_id(self):
        from contract.validator import load
        s = load("session")["$defs"]
        for text in (s["hello"]["properties"]["client"]["properties"]["build"]["description"],
                     s["welcome"]["description"]):
            self.assertIn("YYYYMMDDTHHMMSSZ", text)
            self.assertIn("build.json", text)

    def test_the_default_location_is_the_plugin_adobe_folder(self):
        self.assertEqual(ES.expected_path(), common.PLUGIN_DIR / "adobe" / "expected.json")


if __name__ == "__main__":
    unittest.main()
