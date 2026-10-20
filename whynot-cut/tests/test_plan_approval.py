"""3.0 T1.4 (engine IM-3): the Gate 1 approval fingerprint covers the whole timeline spec, not just the bytes after
"events". A camera move, the framing or the duration changed after approval blocks `ppro-build`; a re-compile that only
changes `generated` stays approved.
Run:  <engine venv python> -m unittest discover -s <plugin>/tests -v
"""
import sys as _sys
_sys.dont_write_bytecode = True  # keep the plugin folder free of __pycache__
import _isolation  # noqa: F401,E402  G79: sandbox the engine home first (tests/_isolation.py)
import copy
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SK = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SK / "engine" / "reel"))

from lib.common import Paths, read_json, write_json  # noqa: E402
from lib import lead_steps  # noqa: E402  BL-15: a lead-only step runs with the guard's token
from lib.plan import plan_fingerprint  # noqa: E402

CLI = SK / "engine/reel/cli.py"
OLDER_EN = "This plan was approved with an older WhyNot Cut. Have one more look and approve it again."
OLDER_AR = "الخطة دي اتوافق عليها بنسخة أقدم من WhyNot Cut. بص عليها بصّة كمان ووافق عليها تاني."


def base_spec() -> dict:
    return {
        "generated": "2026-10-11T10:00:00", "video_id": "CLIP1", "fps": 24, "source_in_ms": 0, "source_range": None,
        "duration_ms": 12000, "duration_frames": 288, "main_footage": "data/Raw/CLIP1.mp4",
        "base_scale_percent": 100.0, "base_offset_x": 0.0, "base_offset_y": 0.0,
        "framing": {"aspect": "9:16", "mode": "center"},
        "main_segments": [
            {"decision_id": "EDIT_001", "start_frame": 0, "end_frame": 144, "src_in_ms": 0, "scale": 100, "move": None},
            {"decision_id": "EDIT_002", "start_frame": 144, "end_frame": 288, "src_in_ms": 6000, "scale": 100, "move": None}],
        "events": [{"event_id": "GFX_001", "template": "statement_bar", "track": 3, "start_frame": 10, "end_frame": 80,
                    "params": {"text": "x"}}],
        "caption_source": "02_transcription/captions-short.srt", "caption_highlights": [], "time_map": None,
        "music": None, "recipe": None}


def cli(root: Path, *args):
    lead_steps.issue_for(["--root", str(root), "--video-id", "CLIP1", *args])     # BL-15: the lead's token
    return subprocess.run([sys.executable, "-B", str(CLI), "--root", str(root), "--video-id", "CLIP1", *args],
                          capture_output=True, text=True)


class ApprovalFixture(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name) / "CLIENT"
        (self.root / "assets").mkdir(parents=True)
        (self.root / "data/Raw").mkdir(parents=True)
        (self.root / "data/Raw/CLIP1.mp4").write_bytes(b"x")
        self.p = Paths(self.root, "CLIP1")
        self.p.ensure_project()
        self.spec = base_spec()
        self.save(self.spec)

    def save(self, spec: dict):
        write_json(self.p.p("01_analysis/timeline-spec.json"), spec)

    def approve(self):
        r = cli(self.root, "approve-plan", "--by", "editor")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def assert_blocked(self):
        r = cli(self.root, "ppro-build")
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn("not approved", r.stdout)

    def mutated(self, fn) -> dict:
        s = copy.deepcopy(self.spec)
        fn(s)
        return s


class TestPlanApprovalFingerprint(ApprovalFixture):
    def test_camera_move_after_approval_blocks_build(self):
        self.approve()
        self.save(self.mutated(lambda s: s["main_segments"][1].update(scale=125, move="push_in")))
        self.assert_blocked()

    def test_framing_after_approval_blocks_build(self):
        self.approve()
        self.save(self.mutated(lambda s: s.update(framing={"aspect": "4:5", "mode": "center"}, base_scale_percent=112.0)))
        self.assert_blocked()

    def test_duration_after_approval_blocks_build(self):
        self.approve()
        self.save(self.mutated(lambda s: s.update(duration_ms=11000, duration_frames=264)))
        self.assert_blocked()

    def test_main_footage_after_approval_blocks_build(self):
        self.approve()
        self.save(self.mutated(lambda s: s.update(main_footage="data/Raw/OTHER.mp4")))
        self.assert_blocked()

    def test_unchanged_recompile_stays_approved(self):
        self.approve()
        fp = plan_fingerprint(self.p)
        self.save(self.mutated(lambda s: s.update(generated="2026-10-12T09:30:00")))     # only the timestamp differs
        self.assertEqual(plan_fingerprint(self.p), fp)
        appr = read_json(self.p.p("01_analysis/plan-approval.json"))
        self.assertEqual(appr["plan_fingerprint"], fp)
        self.assertFalse(appr.get("stale"))
        # the approval gate passes: the build gets past "not approved" (it may then fail on the missing bridge)
        r = cli(self.root, "ppro-build")
        self.assertNotIn("not approved", r.stdout + r.stderr)

    def test_events_change_still_changes_fingerprint(self):
        fp = plan_fingerprint(self.p)
        self.save(self.mutated(lambda s: s["events"][0]["params"].update(text="y")))
        self.assertNotEqual(plan_fingerprint(self.p), fp)

    def test_fingerprint_format_is_16_hex(self):
        fp = plan_fingerprint(self.p)
        self.assertRegex(fp, r"^[0-9a-f]{16}$")

    def test_key_order_and_formatting_do_not_matter(self):
        fp = plan_fingerprint(self.p)
        reordered = dict(reversed(list(self.spec.items())))
        self.p.p("01_analysis/timeline-spec.json").write_text(json.dumps(reordered, indent=4, ensure_ascii=True),
                                                              encoding="utf-8")
        self.assertEqual(plan_fingerprint(self.p), fp)


class TestApprovalStaleness(ApprovalFixture):
    """3.0 T11 (E1, E2): a `reel range` re-run that only refreshes its timestamp keeps the approval; `reel next` and the
    handoff say when the approval no longer matches the plan."""

    def ranged(self, **kw) -> dict:
        rng = {"footage": "data/Raw/CLIP1.mp4", "in_ms": 1000, "out_ms": 13000, "duration_ms": 12000, "label": "",
               "set_at": "2026-10-11T10:00:00"}
        rng.update(kw)
        return self.mutated(lambda s: s.update(source_range=rng, source_in_ms=rng["in_ms"]))

    def next_out(self) -> dict:
        r = cli(self.root, "next")
        self.assertEqual(r.returncode, 0, r.stderr)
        return json.loads(r.stdout)

    def handoff_readme(self) -> str:
        from lib.handoff import build
        build(self.p)
        return self.p.p("09_handoff/README.md").read_text(encoding="utf-8")

    def test_e1_range_timestamp_does_not_change_the_fingerprint(self):
        self.save(self.ranged())
        self.approve()
        fp = plan_fingerprint(self.p)
        self.save(self.ranged(set_at="2026-10-12T09:00:00", selected_at="2026-10-12T09:00:01"))
        self.assertEqual(plan_fingerprint(self.p), fp)
        self.assertNotIn("not approved", cli(self.root, "ppro-build").stdout)
        self.save(self.ranged(in_ms=2000))                                  # a real range change still counts
        self.assertNotEqual(plan_fingerprint(self.p), fp)

    def test_e2_next_and_handoff_flag_a_stale_approval(self):
        self.approve()
        self.assertEqual(self.next_out()["stale"], [])
        self.assertIn("approved by editor", self.handoff_readme())
        self.save(self.mutated(lambda s: s.update(duration_ms=11000, duration_frames=264)))
        nx = self.next_out()
        self.assertIn("plan changed since approval — re-approve", " ".join(nx["stale"]))
        self.assertNotIn("approval format changed", " ".join(nx["stale"]))
        self.assertIn("approve-plan", nx["next"])
        readme = self.handoff_readme()
        self.assertNotIn("approved by editor", readme)
        self.assertIn("plan changed since approval — re-approve", readme)

    def test_e2_pre_3_0_approval_says_it_was_approved_with_an_older_whynot_cut(self):
        write_json(self.p.p("01_analysis/plan-approval.json"),          # 2.x record: old fingerprint, no format
                   {"approved": True, "by": "editor", "note": "", "at": "2026-09-01T10:00:00",
                    "plan_fingerprint": "0123456789abcdef"})
        stale = " ".join(self.next_out()["stale"])
        self.assertIn(OLDER_EN, stale)
        self.assertNotIn("plan changed since approval", stale)
        readme = self.handoff_readme()
        self.assertNotIn("approved by editor", readme)
        self.assertIn(OLDER_EN, readme)


class TestPre30Approval(ApprovalFixture):
    """3.0 F2: the plan fingerprint changed in 3.0, so a plan approved under 2.x needs one more approval. The refusal
    says so plainly (English and Arabic); a real re-plan after a 3.0 approval keeps the generic message."""

    def old_record(self, fingerprint="0123456789abcdef"):
        write_json(self.p.p("01_analysis/plan-approval.json"),          # what 2.x wrote: no "format"
                   {"approved": True, "by": "editor", "note": "", "at": "2026-09-01T10:00:00",
                    "plan_fingerprint": fingerprint})

    def test_ppro_build_says_the_plan_was_approved_with_an_older_whynot_cut(self):
        self.old_record()
        r = cli(self.root, "ppro-build")
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        doc = json.loads(r.stdout)
        self.assertEqual(doc["blocked"], OLDER_EN)
        self.assertEqual(doc["editor_message"], {"en": OLDER_EN, "ar": OLDER_AR})
        self.assertIn("approve-plan", doc["how"])

    def test_a_real_replan_after_a_3_0_approval_keeps_the_generic_message(self):
        self.approve()
        self.assertEqual(read_json(self.p.p("01_analysis/plan-approval.json"))["format"], 3)
        self.save(self.mutated(lambda s: s["events"][0]["params"].update(text="y")))
        r = cli(self.root, "ppro-build")
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn("not approved", r.stdout)
        self.assertNotIn("older WhyNot Cut", r.stdout)
        self.assertNotIn("editor_message", json.loads(r.stdout))
        from lib.ppro_build import approval_refusal
        ref = approval_refusal(self.p)
        self.assertNotIn("older WhyNot Cut", ref["error"])
        self.assertNotIn("editor_message", ref)
        from lib.plan import approval_state
        self.assertEqual(approval_state(self.p)["message"], "plan changed since approval — re-approve")

    def test_the_serve_build_refusal_says_it_too(self):
        from lib.ppro_build import approval_refusal
        self.old_record()
        ref = approval_refusal(self.p)
        self.assertEqual((ref["status"], ref["ok"]), ("REFUSED", False))
        self.assertTrue(ref["error"].startswith(OLDER_EN), ref["error"])
        self.assertEqual(ref["editor_message"], {"en": OLDER_EN, "ar": OLDER_AR})
        from lib.build_safety import serve_answer
        self.assertTrue(serve_answer(ref, "PRPROJ_BUILT", "result")["error"].startswith(OLDER_EN))

    def test_approval_state_names_it_in_both_languages(self):
        from lib.plan import approval_state
        self.old_record()
        st = approval_state(self.p)
        self.assertEqual((st["state"], st["message"]), ("stale", OLDER_EN))
        self.assertEqual(st["editor_message"], {"en": OLDER_EN, "ar": OLDER_AR})

    def test_a_2x_record_that_still_matches_the_plan_stays_approved(self):
        from lib.ppro_build import approval_refusal
        self.old_record(plan_fingerprint(self.p))
        self.assertIsNone(approval_refusal(self.p))
        self.assertNotIn("not approved", cli(self.root, "ppro-build").stdout)

    def test_approving_again_clears_it(self):
        self.old_record()
        self.approve()
        from lib.ppro_build import approval_refusal
        self.assertIsNone(approval_refusal(self.p))


class TestApproveReadsTheStamp(ApprovalFixture):
    """T2.3 review: approve-plan reads the compiled spec through stamps.read_compiled."""

    def test_a_2x_spec_without_a_stamp_is_approved_with_a_warning(self):
        r = cli(self.root, "approve-plan", "--by", "editor")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        out = json.loads(r.stdout)
        self.assertTrue(out["approved"])
        self.assertIn("no engine_version", " ".join(out["version_warnings"]))
        self.assertTrue(self.p.p("01_analysis/plan-approval.json").exists())

    def test_the_current_engine_version_is_silent(self):
        from lib.stamps import engine_version
        self.save(dict(self.spec, engine_version=engine_version()))
        r = cli(self.root, "approve-plan", "--by", "editor")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertNotIn("version_warnings", json.loads(r.stdout))

    def test_another_minor_version_warns_and_approves(self):
        from lib.stamps import engine_version
        major = engine_version().split(".")[0]
        self.save(dict(self.spec, engine_version=f"{major}.99.0"))
        r = cli(self.root, "approve-plan", "--by", "editor")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn(f"{major}.99.0", " ".join(json.loads(r.stdout)["version_warnings"]))

    def test_another_major_version_is_refused_with_a_rerun_hint(self):
        self.save(dict(self.spec, engine_version="9.0.0"))
        r = cli(self.root, "approve-plan", "--by", "editor")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("Re-run `reel plan`", r.stdout + r.stderr)
        self.assertFalse(self.p.p("01_analysis/plan-approval.json").exists())
        # the re-run itself must still be able to read the old spec's fingerprint (plan.py invalidates approvals)
        self.assertEqual(len(plan_fingerprint(self.p)), 16)


if __name__ == "__main__":
    unittest.main()
