"""3.0 T1.4 (engine IM-3): the Gate 1 approval fingerprint covers the whole timeline spec, not just the bytes after
"events". A camera move, the framing or the duration changed after approval blocks `ppro-build`; a re-compile that only
changes `generated` stays approved.
Run:  <engine venv python> -m unittest discover -s <plugin>/tests -v
"""
import sys as _sys
_sys.dont_write_bytecode = True  # keep the plugin folder free of __pycache__
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
from lib.plan import plan_fingerprint  # noqa: E402

CLI = SK / "engine/reel/cli.py"


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

    def test_e2_pre_3_0_approval_names_the_format_change(self):
        write_json(self.p.p("01_analysis/plan-approval.json"),          # 2.x record: old fingerprint, no format
                   {"approved": True, "by": "editor", "note": "", "at": "2026-09-01T10:00:00",
                    "plan_fingerprint": "0123456789abcdef"})
        stale = " ".join(self.next_out()["stale"])
        self.assertIn("plan changed since approval — re-approve (approval format changed in 3.0)", stale)
        self.assertNotIn("approved by editor", self.handoff_readme())


if __name__ == "__main__":
    unittest.main()
