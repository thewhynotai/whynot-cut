"""3.0 T4.1 smooth zoom and fades: what `reel plan` writes into the timeline spec, and the Gate 1 wording.

Cases (T41-CASES.md): C7, C8, C11, C13, C16, C33 through a real compile of a synthetic client (ffmpeg testsrc, as in
test_pipeline), plus the executor's ruling: a re-plan whose fingerprint changed ONLY because of the new ease keys says
so in editor words ("smooth zoom added to the punch-ins"), in English and Arabic.
Run:  bash tools/test.sh -p test_t41_plan.py
"""
import sys as _sys
_sys.dont_write_bytecode = True  # keep the plugin folder free of __pycache__
import _isolation  # noqa: F401,E402  G79: sandbox the engine home first (tests/_isolation.py)
import copy  # noqa: E402
import json  # noqa: E402
import shutil  # noqa: E402
import tempfile  # noqa: E402
import unittest  # noqa: E402
from pathlib import Path  # noqa: E402

sys = _sys
SK = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SK / "engine" / "reel"))

from lib import common  # noqa: E402
from lib.common import Paths, write_json  # noqa: E402
import test_pipeline as tp  # noqa: E402  (module import: its TestCases are not collected again here)
import test_plan_approval as tpa  # noqa: E402
import test_podcast as tpod  # noqa: E402  (module import: its TestCases are not collected again here)


def decisions(camera=True, cut_words=None):
    d = {"decision_id": "EDIT_001", "segment_id": "SEG_001", "evidence": "هل في حاجات معينة", "start": "00:00:00.200",
         "end": "00:00:04.000", "semantic_intent": "hook", "visual_treatment": "hook", "confidence": "high"}
    if camera:
        d["camera"] = {"type": "punch_in", "at": "00:00:01.000", "until": "00:00:03.000", "scale_factor": 1.1}
    g = {"main_footage": "data/Raw/CLIP1.mov"}
    if cut_words:
        g["cut_words"] = cut_words
    return {"video_id": "CLIP1", "global": g, "decisions": [d]}


class TestCompile(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp())
        cls.root, cls.p, cls.words = tp.make_project(cls.tmp)
        from lib.discover import run_discovery
        from lib.client_db import build
        from lib.media import preflight
        with common.use_context(common.Context(root=cls.root)):
            build(cls.p, run_discovery(cls.p)["inventory"])
            preflight(cls.p, [cls.root / "data/Raw/CLIP1.mov"])

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def setUp(self):
        self.style_f = self.root / common.CLIENT_PROFILE_REL / "style.json"
        if self.style_f.exists():
            self.style_f.unlink()

    def style(self, st: dict):
        self.style_f.parent.mkdir(parents=True, exist_ok=True)
        write_json(self.style_f, st)

    def compile(self, ed):
        from lib.plan import compile_plan, plan_fingerprint
        write_json(self.p.p("01_analysis/edit-decisions.json"), ed)
        with common.use_context(common.Context(root=self.root)):
            r = compile_plan(self.p)
            self.assertTrue(r["ok"], r["errors"])
            spec = json.loads(self.p.p("01_analysis/timeline-spec.json").read_text(encoding="utf-8"))
            return r, spec, plan_fingerprint(self.p)

    def run_of(self, spec):
        runs = spec["camera_ease"]["runs"]
        self.assertEqual(len(runs), 1, runs)
        return runs[0]

    def test_punch_in_gets_eased_keys_by_default(self):
        r, spec, _ = self.compile(decisions())
        self.assertEqual(spec["camera_ease"]["ease_ms"], 250)
        run = self.run_of(spec)
        self.assertEqual(run["decision_id"], "EDIT_001")
        seg = spec["main_segments"][run["ease_in"]["piece"]]
        self.assertEqual((seg["start_frame"], seg["decision_id"]), (24, "EDIT_001"))
        self.assertEqual((run["ease_in"]["frames"], run["ease_out"]["frames"]), (6, 6))
        self.assertNotIn("fades", spec)                                       # fades default to off

    def test_m2_edit_plan_says_smooth_zoom_in_editor_words(self):
        self.compile(decisions())
        md = self.p.p("01_analysis/edit-plan.md").read_text(encoding="utf-8")
        line = next((x for x in md.splitlines() if "smooth zoom" in x.lower()), None)
        self.assertIsNotNone(line, md)
        self.assertIn("250 ms", line)
        self.assertNotIn("ease_ms", line)
        self.assertIn("1 punch-in eases in and out", line)              # round 4 M-7: counted per kind
        self.assertIn("زوم ناعم", md)                                    # and in Arabic

    def edit_plan_with(self, runs):
        from lib.plan import write_edit_plan
        from lib.stamps import stamp
        _, spec, _ = self.compile(decisions())
        spec["camera_ease"]["runs"] = runs(spec["camera_ease"]["runs"][0])
        write_json(self.p.p("01_analysis/timeline-spec.json"), stamp(spec))
        with common.use_context(common.Context(root=self.root)):
            md = write_edit_plan(self.p).read_text(encoding="utf-8")
        return next(x for x in md.splitlines() if "smooth zoom" in x.lower()), md

    def test_r5_min1_arabic_plural_and_wording(self):
        line, md = self.edit_plan_with(lambda r: [r, dict(r, decision_id="EDIT_002", pieces=[5, 5]),
                                                  dict(r, decision_id="EDIT_003", camera="slow_push", ease_out=None,
                                                       pieces=[7, 7])])
        ar = next(x for x in md.splitlines() if "زوم ناعم" in x)
        self.assertIn("2 punch-in بيدخلوا ويخرجوا بنعومة", ar)
        self.assertIn("طول اللقطة كلها", ar)
        self.assertNotIn("على طول", ar)
        line1, md1 = self.edit_plan_with(lambda r: [r])
        self.assertIn("1 punch-in بيدخل ويخرج بنعومة", next(x for x in md1.splitlines() if "زوم ناعم" in x))

    def test_r5_min2_no_ms_when_only_slow_pushes(self):
        line, md = self.edit_plan_with(lambda r: [dict(r, camera="slow_push", ease_out=None)])
        ar = next(x for x in md.splitlines() if "زوم ناعم" in x)
        self.assertNotIn("ms", line)
        self.assertNotIn("ms", ar)
        self.assertIn("1 slow push", line)

    def test_r4_m7_slow_pushes_and_one_sided_eases_are_counted(self):
        line, _ = self.edit_plan_with(lambda r: [dict(r, camera="slow_push", ease_out=None),
                                                 dict(r, decision_id="EDIT_002", ease_in=None, pieces=[5, 5])])
        self.assertIn("1 slow push", line)
        self.assertIn("1 punch-in eases on one side only", line)
        self.assertNotIn("in and out", line)

    def test_mh_a_punch_in_split_by_a_cutaway_counts_once(self):
        from lib.plan import write_edit_plan
        from lib.stamps import stamp
        _, spec, _ = self.compile(decisions())
        run = spec["camera_ease"]["runs"][0]
        spec["camera_ease"]["runs"] = [dict(run, ease_out=None), dict(run, ease_in=None, pieces=[9, 9])]
        write_json(self.p.p("01_analysis/timeline-spec.json"), stamp(spec))
        with common.use_context(common.Context(root=self.root)):
            md = write_edit_plan(self.p).read_text(encoding="utf-8")
        line = next(x for x in md.splitlines() if "smooth zoom" in x.lower())
        self.assertIn("1 punch-in eases in and out", line)                # one move, both sides over its pieces

    def test_m2_no_line_when_nothing_is_eased(self):
        self.compile(decisions(camera=False))
        md = self.p.p("01_analysis/edit-plan.md").read_text(encoding="utf-8")
        self.assertNotIn("smooth zoom", md.lower())

    def test_r6_a_recited_verse_and_the_smooth_zoom_compose(self):
        """Round 6 (c2c23e6 manual verse slot): a verse span blanks captions / graphics / SFX and adds a marker; it
        never touches the V01 pieces, so a punch-in over or next to it eases as before, and the fades stay on."""
        self.style({"fades": {"video_in_ms": 300, "audio_in_ms": 300}})
        ed = decisions()
        ed["manual_verse"] = [{"start_ms": "00:00:01.500", "end_ms": "00:00:02.500"}]
        r, spec, _ = self.compile(ed)
        self.assertTrue(spec.get("manual_verse"), spec.keys())               # the span is there
        run = self.run_of(spec)                                                # and the punch-in still eases
        self.assertEqual((run["ease_in"]["frames"], run["ease_out"]["frames"]), (6, 6))
        self.assertEqual(spec["fades"]["video_in_ms"], 300)
        md = self.p.p("01_analysis/edit-plan.md").read_text(encoding="utf-8")
        self.assertIn("Smooth zoom", md)
        _, plain, _ = self.compile(decisions())                               # same pieces with and without a verse
        self.assertEqual(spec["main_segments"], plain["main_segments"])
        self.assertEqual(spec["camera_ease"], plain["camera_ease"])

    def test_r6_a_punch_in_starting_inside_a_verse_is_hard(self):
        """Round 6 (executor): no ease may start inside a manual_verse span (the punch-in starts at 1.0 s, inside the
        verse 0.9-1.5 s): its ease in is dropped with a plan warning, its ease out (2.75 s) stays."""
        ed = decisions()
        ed["manual_verse"] = [{"start_ms": "00:00:00.900", "end_ms": "00:00:01.500"}]
        r, spec, _ = self.compile(ed)
        run = self.run_of(spec)
        self.assertIsNone(run["ease_in"])
        self.assertIsNotNone(run["ease_out"])
        self.assertTrue(any("verse" in w and "EDIT_001" in w for w in r["warnings"]), r["warnings"])
        # round 7 P2-1: edit-plan.md gives the true reason, in both languages
        md = self.p.p("01_analysis/edit-plan.md").read_text(encoding="utf-8")
        en = next(x for x in md.splitlines() if x.startswith("Smooth zoom"))
        ar = next(x for x in md.splitlines() if "زوم ناعم" in x)
        self.assertIn("inside a recited verse", en)
        self.assertNotIn("on a cut or another shot", en)
        self.assertIn("جوه آية", ar)
        self.assertNotIn("على قطع", ar)

    def test_r7_a_verse_cut_away_whole_does_not_block(self):
        """Executor (round 7): a span cut out whole (`verse_cut`) and the word mask (`verse_mask`) have no timeline
        range: they never block an ease; only spec["manual_verse"] does."""
        ed = decisions(cut_words=[1])                                       # word 1 (0.20-0.86 s) is cut
        ed["manual_verse"] = [{"start_ms": "00:00:00.300", "end_ms": "00:00:00.800"}]
        r, spec, _ = self.compile(ed)
        self.assertTrue(spec.get("verse_cut"), spec.keys())
        self.assertFalse(spec.get("manual_verse"))
        run = self.run_of(spec)
        self.assertIsNotNone(run["ease_in"])
        self.assertIsNotNone(run["ease_out"])
        self.assertNotIn("verse_hard", spec["camera_ease"])

    def test_r8_p3_5_arabic_plural_of_moves_kept_hard(self):
        from lib.plan import write_edit_plan
        from lib.stamps import stamp
        _, spec, _ = self.compile(decisions())
        for n, want in ((1, "1 حركة فضلت"), (2, "حركتين فضلوا"), (3, "3 حركات فضلوا"), (10, "10 حركات فضلوا"),
                        (11, "11 حركة فضلوا")):
            with self.subTest(n=n):
                spec["camera_ease"]["runs"] = []
                spec["camera_ease"]["verse_hard"] = [{"decision_id": f"D{i}", "camera": "punch_in", "sides": ["in"],
                                                      "start_ms": 1000} for i in range(n)]
                write_json(self.p.p("01_analysis/timeline-spec.json"), stamp(spec))
                with common.use_context(common.Context(root=self.root)):
                    md = write_edit_plan(self.p).read_text(encoding="utf-8")
                ar = next(x for x in md.splitlines() if "زوم ناعم" in x)
                self.assertIn(want, ar)

    def test_r8_p2_1_a_verse_dropped_job_fits_the_build_contract(self):
        """Round 8 P2-1: the runs sent to the bridge stay schema-clean; the verse drop lives in camera_ease.verse_dropped."""
        from contract import validator as V
        from lib.ppro_build import ease_job_fields
        ed = decisions()
        ed["manual_verse"] = [{"start_ms": "00:00:01.100", "end_ms": "00:00:01.200"}]       # inside the ease in
        _, spec, _ = self.compile(ed)
        self.assertEqual([d["side"] for d in spec["camera_ease"]["verse_dropped"]], ["in"])
        job = ease_job_fields(spec)
        self.assertTrue(job["camera_keys"])
        for run_ in job["camera_keys"]:
            self.assertEqual(V.validate(run_, "build_project#/$defs/ease_run"), [])

    def test_r7_a_move_kept_hard_in_a_verse_is_named_in_the_edit_plan(self):
        ed = decisions()
        ed["manual_verse"] = [{"start_ms": "00:00:00.900", "end_ms": "00:00:03.000"}]     # both eases fall inside it
        r, spec, _ = self.compile(ed)
        self.assertEqual(spec["camera_ease"]["runs"], [])
        self.assertEqual([h["decision_id"] for h in spec["camera_ease"]["verse_hard"]], ["EDIT_001"])
        md = self.p.p("01_analysis/edit-plan.md").read_text(encoding="utf-8")
        en = next(x for x in md.splitlines() if x.startswith("Smooth zoom"))
        self.assertIn("1 move stays hard inside a recited verse", en)
        self.assertIn("جوه آية", next(x for x in md.splitlines() if "زوم ناعم" in x))
        self.assertEqual(sum(1 for w in r["warnings"] if "EDIT_001" in w and "verse" in w), 1)

    # ---- round 9: the edit plan names a side lost to a held run ("the verse may go on") without claiming a verse
    def edit_plan_lines(self, ce):
        from lib.plan import write_edit_plan
        from lib.stamps import stamp
        _, spec, _ = self.compile(decisions())
        spec["camera_ease"] = ce(spec["camera_ease"]["runs"][0])
        write_json(self.p.p("01_analysis/timeline-spec.json"), stamp(spec))
        with common.use_context(common.Context(root=self.root)):
            md = write_edit_plan(self.p).read_text(encoding="utf-8")
        return (next(x for x in md.splitlines() if x.startswith("Smooth zoom")),
                next(x for x in md.splitlines() if "زوم ناعم" in x))

    def test_r9_p3_4_the_ms_suffix_when_the_only_one_sided_moves_are_verse_ones(self):
        """Round 8 review P3-4 (M8): a punch-in eased on one side only because of a verse still names ease_ms."""
        ed = decisions()
        ed["manual_verse"] = [{"start_ms": "00:00:00.900", "end_ms": "00:00:01.500"}]
        self.compile(ed)
        md = self.p.p("01_analysis/edit-plan.md").read_text(encoding="utf-8")
        en = next(x for x in md.splitlines() if x.startswith("Smooth zoom"))
        self.assertTrue(en.startswith("Smooth zoom (250 ms): 1 punch-in eases on one side only (the other side is "
                                      "inside a recited verse)"), en)
        self.assertIn("زوم ناعم (250 ms):", next(x for x in md.splitlines() if "زوم ناعم" in x))

    def test_r9_a_side_lost_to_a_held_run_says_the_verse_may_go_on(self):
        en, ar = self.edit_plan_lines(lambda r: {"ease_ms": 250, "curve": "bezier", "runs": [dict(r, ease_in=None)],
                                                 "verse_dropped": [{"decision_id": "EDIT_001", "camera": "punch_in",
                                                                    "side": "in", "start_ms": 1000, "held": True}]})
        self.assertIn("Smooth zoom (250 ms): 1 punch-in eases on one side only (the other side is where the verse may "
                      "go on)", en)
        self.assertNotIn("recited", en)
        self.assertNotIn("on a cut or another shot", en)
        self.assertIn("زوم ناعم (250 ms): 1 punch-in بنعومة من ناحية واحدة بس (الناحية التانية في وقت ممكن الآية تكون "
                      "مكمّلة)", ar)
        self.assertNotIn("جوه آية", ar)
        self.assertNotIn("على قطع", ar)

    def test_r9_a_move_kept_hard_by_a_held_run_says_the_verse_may_go_on(self):
        hard = {"decision_id": "EDIT_001", "camera": "punch_in", "sides": ["in", "out"], "start_ms": 1000, "held": True}
        en, ar = self.edit_plan_lines(lambda r: {"ease_ms": 250, "curve": "bezier", "runs": [], "verse_hard": [hard]})
        self.assertEqual(en, "Smooth zoom: 1 move stays hard where the verse may go on.")
        self.assertEqual(ar, "زوم ناعم: 1 حركة فضلت من غير زوم ناعم في وقت ممكن الآية تكون مكمّلة.")
        two = [dict(hard, decision_id="A"), dict(hard, decision_id="B")]
        en, ar = self.edit_plan_lines(lambda r: {"ease_ms": 250, "curve": "bezier", "runs": [], "verse_hard": two})
        self.assertIn("2 moves stay hard where the verse may go on", en)
        self.assertIn("حركتين فضلوا من غير زوم ناعم في وقت ممكن الآية تكون مكمّلة", ar)

    def test_r9_a_move_hit_by_a_verse_and_a_held_run_names_the_verse(self):
        held = {"decision_id": "EDIT_001", "camera": "punch_in", "sides": ["in"], "start_ms": 1000, "held": True}
        verse = dict(held, sides=["out"], start_ms=2750)
        verse.pop("held")
        en, ar = self.edit_plan_lines(lambda r: {"ease_ms": 250, "curve": "bezier", "runs": [],
                                                 "verse_hard": [held, verse]})
        self.assertEqual(en, "Smooth zoom: 1 move stays hard inside a recited verse.")
        self.assertIn("جوه آية", ar)
        en, _ = self.edit_plan_lines(lambda r: {"ease_ms": 250, "curve": "bezier", "runs": [dict(r, ease_in=None)],
                                                "verse_dropped": [dict(held, side="in"), dict(verse, side="out")]})
        self.assertIn("(the other side is inside a recited verse)", en)
        self.assertNotIn("may go on", en)

    def test_c11_ease_zero_is_recorded_with_hard_punches(self):
        self.style({"camera": {"ease_ms": 0}})
        _, spec, _ = self.compile(decisions())
        self.assertEqual(spec["camera_ease"], {"ease_ms": 0, "curve": "bezier", "runs": []})

    def test_c11_a_bad_value_is_a_plan_warning(self):
        self.style({"camera": {"ease_ms": "fast"}})
        r, spec, _ = self.compile(decisions())
        self.assertTrue(any("camera.ease_ms" in w for w in r["warnings"]), r["warnings"])
        self.assertEqual(spec["camera_ease"]["ease_ms"], 250)

    def test_c13_no_move_no_fades_keeps_the_fingerprint(self):
        """Round 3, item 2: the plan records camera.ease_ms, but a record with nothing eased does not change the Gate 1
        fingerprint: a reel without punch-ins re-planned after the update stays approved."""
        from lib.plan import spec_fingerprint
        _, spec, fp = self.compile(decisions(camera=False))
        self.assertEqual(spec["camera_ease"], {"ease_ms": 250, "curve": "bezier", "runs": []})
        self.assertNotIn("fades", spec)
        pre = {k: v for k, v in spec.items() if k != "camera_ease"}          # what a pre-T4.1 engine wrote
        self.assertEqual(fp, spec_fingerprint(pre))
        self.style({"camera": {"ease_ms": 0}})
        _, _, fp0 = self.compile(decisions(camera=False))
        self.assertEqual(fp, fp0)

    def test_r3_a_punch_in_re_plan_records_250_and_changes_the_fingerprint(self):
        from lib.plan import spec_fingerprint
        _, spec, fp = self.compile(decisions())
        pre = {k: v for k, v in spec.items() if k != "camera_ease"}
        self.assertNotEqual(fp, spec_fingerprint(pre))

    def test_c16_fade_longer_than_the_reel_is_clamped_with_a_warning(self):
        self.style({"fades": {"video_in_ms": 99999, "audio_out_ms": 400}})
        r, spec, _ = self.compile(decisions())
        self.assertLessEqual(spec["fades"]["video_in_ms"], spec["duration_ms"])
        self.assertEqual(spec["fades"]["audio_out_ms"], 400)
        self.assertTrue(any("fades" in w for w in r["warnings"]), r["warnings"])

    def test_c8_a_word_cut_moves_the_keys(self):
        _, s0, _ = self.compile(decisions())
        _, s1, _ = self.compile(decisions(cut_words=[1]))          # the first word goes: everything moves earlier
        r0, r1 = self.run_of(s0), self.run_of(s1)
        a0 = s0["main_segments"][r0["ease_in"]["piece"]]["start_frame"]
        a1 = s1["main_segments"][r1["ease_in"]["piece"]]["start_frame"]
        self.assertLess(a1, a0)
        self.assertIsNotNone(r1["ease_out"])

    def test_c7_a_cut_at_the_punch_start_keeps_it_hard(self):
        _, spec, _ = self.compile(decisions(cut_words=[2]))           # word 2 spans the punch's start (1.0 s)
        run = self.run_of(spec)
        self.assertIsNone(run["ease_in"])
        self.assertIsNotNone(run["ease_out"])

    def test_c33_replan_is_idempotent(self):
        _, s0, fp0 = self.compile(decisions())
        _, s1, fp1 = self.compile(decisions())
        self.assertEqual(fp0, fp1)
        self.assertEqual(s0["camera_ease"], s1["camera_ease"])


class TestPodcastFingerprint(unittest.TestCase):
    """Round 4 I-3: a podcast reel (per-shot framing) re-planned after the update keeps its approval unless easing
    really changed something: the shot identity a story move sits on is derived at ease time (from the camera layer),
    never stored in the spec."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.addCleanup(common.set_context, None)
        self.reel = tpod.TestShots.shot_reel(None, self.tmp)       # shots: 0-3 s face at 0.70, 3-8 s face at 0.30

    def compile(self, camera_decisions):
        from lib.plan import compile_plan
        ds = [tpod.decision(f"EDIT_00{i + 1}", a, b, ev, camera=cam) for i, (a, b, ev, cam) in enumerate(camera_decisions)]
        write_json(self.reel.p("01_analysis/edit-decisions.json"), {"video_id": "E_R01", "global": {}, "decisions": ds})
        r = compile_plan(self.reel)
        self.assertTrue(r["ok"], r["errors"])
        return json.loads(self.reel.p("01_analysis/timeline-spec.json").read_text(encoding="utf-8"))

    def approve_as_before_t41(self, spec):
        """The plan as a pre-T4.1 engine wrote it (no camera_ease), approved by the editor."""
        from lib.plan import APPROVAL_FORMAT, plan_fingerprint
        from lib.stamps import stamp
        write_json(self.reel.p("01_analysis/timeline-spec.json"), stamp({k: v for k, v in spec.items() if k != "camera_ease"}))
        write_json(self.reel.p("01_analysis/plan-approval.json"),
                   {"approved": True, "by": "editor", "format": APPROVAL_FORMAT, "plan_fingerprint": plan_fingerprint(self.reel)})

    def test_r4_i3_story_moves_without_easing_stay_approved(self):
        from lib.plan import approval_state
        moves = [("00:00:00.500", "00:00:01.500", "كلمه1 كلمه2",
                  {"type": "reframe", "at": "00:00:00.500", "until": "00:00:01.500", "scale_factor": 1.05}),
                 ("00:00:03.500", "00:00:05.000", "كلمه7 كلمه8",
                  {"type": "punch_out", "at": "00:00:03.500", "until": "00:00:05.000", "scale_factor": 0.95})]
        spec = self.compile(moves)
        self.assertEqual(spec["camera_ease"]["runs"], [])
        self.assertFalse(any("shot_offset_x" in m for m in spec["main_segments"]), spec["main_segments"])
        self.approve_as_before_t41(spec)
        self.compile(moves)                                         # the re-plan after the update
        self.assertEqual(approval_state(self.reel)["state"], "current")

    def test_r4_i3_easing_alone_gives_the_smooth_zoom_message(self):
        from lib.plan import approval_state
        moves = [("00:00:00.500", "00:00:02.000", "كلمه1 كلمه2",
                  {"type": "punch_in", "at": "00:00:01.000", "until": "00:00:02.000", "scale_factor": 1.1})]
        spec = self.compile(moves)
        self.assertTrue(spec["camera_ease"]["runs"], spec["main_segments"])   # same shot both sides: eased
        self.assertFalse(any("shot_offset_x" in m for m in spec["main_segments"]))
        self.approve_as_before_t41(spec)
        self.compile(moves)
        st = approval_state(self.reel)
        self.assertEqual(st["state"], "stale")
        self.assertIn("smooth zoom added to the punch-ins", st["message"])


class TestPodcastShotsInFrames(unittest.TestCase):
    """Round 5 IMP-1 on a real compile: the speaker change at 3.01 s is not on a frame boundary (24 fps: frame 72 is
    3.000 s); two punch-ins back to back on the two speakers meet hard, also after pause removal (word cut)."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.addCleanup(common.set_context, None)
        self.reel = tpod.TestShots.shot_reel(None, self.tmp)
        from lib.common import read_json
        pre = read_json(self.reel.p("00_inputs/preflight.json"))
        pre["shots"]["shots"] = [tpod.shot(0, 3010, 0.70), tpod.shot(3010, 8000, 0.30)]
        write_json(self.reel.p("00_inputs/preflight.json"), pre)

    def pair(self, cut_words=None):
        from lib.plan import compile_plan
        ds = [tpod.decision("EDIT_001", "00:00:01.000", "00:00:03.000", "كلمه2 كلمه3",
                            camera={"type": "punch_in", "at": "00:00:01.000", "until": "00:00:03.010", "scale_factor": 1.1}),
              tpod.decision("EDIT_002", "00:00:03.010", "00:00:05.000", "كلمه6 كلمه7",
                            camera={"type": "punch_in", "at": "00:00:03.010", "until": "00:00:05.000", "scale_factor": 1.1})]
        g = {"cut_words": cut_words} if cut_words else {}
        write_json(self.reel.p("01_analysis/edit-decisions.json"), {"video_id": "E_R01", "global": g, "decisions": ds})
        r = compile_plan(self.reel)
        self.assertTrue(r["ok"], r["errors"])
        spec = json.loads(self.reel.p("01_analysis/timeline-spec.json").read_text(encoding="utf-8"))
        return spec, {x["decision_id"]: x for x in spec["camera_ease"]["runs"]}

    def test_r5_imp1_real_compile_identity_path(self):
        spec, runs = self.pair()
        self.assertIn("EDIT_002", runs, spec["main_segments"])
        self.assertIsNone(runs["EDIT_002"]["ease_in"])            # no pan across the speakers
        self.assertIsNotNone(runs["EDIT_002"]["ease_out"])
        self.assertIsNone(runs["EDIT_001"]["ease_out"])
        self.assertIsNotNone(runs["EDIT_001"]["ease_in"])

    def test_r5_imp1_real_compile_time_map_path(self):
        spec, runs = self.pair(cut_words=[1])
        self.assertTrue(spec.get("time_map"))
        self.assertIsNone(runs["EDIT_002"]["ease_in"])
        self.assertIsNotNone(runs["EDIT_002"]["ease_out"])


class TestCutawaySplitVerse(unittest.TestCase):
    """Round 8 P3-3 (real compile): a punch-in split by a source card shown whole (AUTO_CUTAWAY) is two runs of one
    move; when the verse removes the second run's only ease, the edit plan still names the verse, not "a cut"."""

    def setUp(self):
        from lib.common import read_json
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.addCleanup(common.set_context, None)
        self.root, self.reel, _ = tpod.reel_fixture(self.tmp, "storytelling", music=False)
        pre = read_json(self.reel.p("00_inputs/preflight.json"))
        pre["shots"] = {"window": {"offset_ms": 1000, "duration_ms": 10000}, "method": "test",
                        "shots": [tpod.shot(0, 3000, 0.5), tpod.shot(3000, 8000), tpod.shot(8000, 10000, 0.5)]}
        write_json(self.reel.p("00_inputs/preflight.json"), pre)

    def test_r8_p3_3_the_edit_plan_names_the_verse(self):
        from lib.plan import compile_plan
        ed = {"global": {}, "decisions": [tpod.decision(
            "EDIT_001", "00:00:01.000", "00:00:09.500", "كلمه2 كلمه3",
            camera={"type": "punch_in", "at": "00:00:01.000", "until": "00:00:09.500", "scale_factor": 1.1})],
            "manual_verse": [{"start_ms": "00:00:09.300", "end_ms": "00:00:09.500"}]}
        write_json(self.reel.p("01_analysis/edit-decisions.json"), ed)
        r = compile_plan(self.reel)
        self.assertTrue(r["ok"], r["errors"])
        spec = json.loads(self.reel.p("01_analysis/timeline-spec.json").read_text(encoding="utf-8"))
        self.assertTrue(any(m.get("decision_id") == "AUTO_CUTAWAY" for m in spec["main_segments"]),
                        spec["main_segments"])
        ce_ = spec["camera_ease"]
        self.assertTrue(ce_.get("verse_hard") or ce_.get("verse_dropped"), ce_)
        md = self.reel.p("01_analysis/edit-plan.md").read_text(encoding="utf-8")
        en = next(x for x in md.splitlines() if x.startswith("Smooth zoom"))
        ar = next(x for x in md.splitlines() if "زوم ناعم" in x)
        self.assertIn("inside a recited verse", en)
        self.assertNotIn("on a cut or another shot", en)
        self.assertNotIn("على قطع", ar)
        self.assertNotIn("stays hard", en)                  # round 8 review P3-2 (M9): a move with an ease left is
        self.assertNotIn("فضل", ar)                         # never also counted hard


class TestHeldRunGuard(unittest.TestCase):
    """Round 9 P2-1 (executor: the round-7 P3-4 ruling, fail safe): the caption run held after a span that ends on a
    pause (spec verse_hold, marker «تحقق: الآية ممكن تكون مكمّلة») is possible recitation, so no camera motion there
    either until the editor releases it. The fixture verse is a placeholder (tests/fixtures/manual_verse)."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.addCleanup(common.set_context, None)

    def compile(self, ed_extra=None, glob=None, n=0):
        from lib.common import read_json
        from lib.plan import compile_plan
        from test_manual_verse import SC, build_words, verse_project
        d = {"decision_id": "EDIT_001", "segment_id": "S1", "evidence": "اهلا بيكم", "start": 200, "end": 10200,
             "semantic_intent": "hook", "visual_treatment": "hook", "confidence": "high",       # the held run is
             "camera": {"type": "punch_in", "at": 7000, "until": 9000, "scale_factor": 1.3}}   # 6.25-10.2 s
        _root, p = verse_project(self.tmp / str(n), build_words(SC["recited"]), decisions=[d], glob=glob,
                                 extra=ed_extra)
        r = compile_plan(p)
        self.assertTrue(r["ok"], r["errors"])
        md = p.p("01_analysis/edit-plan.md").read_text(encoding="utf-8")
        return r, read_json(p.p("01_analysis/timeline-spec.json")), md

    def test_a_punch_in_inside_a_held_run_stays_hard_until_released(self):
        r, spec, md = self.compile()
        hold = spec["verse_hold"][0]
        self.assertEqual((hold["src_start_ms"], hold["src_end_ms"], hold["released"]), (6250, 10200, False))
        self.assertFalse(spec.get("manual_verse") and any(m["src_end_ms"] > 6000 for m in spec["manual_verse"]))
        ce_ = spec["camera_ease"]
        self.assertEqual(ce_["runs"], [])
        self.assertEqual(ce_["verse_hard"], [{"decision_id": "EDIT_001", "camera": "punch_in", "sides": ["in", "out"],
                                              "start_ms": 7000, "held": True}])
        ws = [w for w in r["warnings"] if w.startswith("EDIT_001 at")]
        self.assertEqual(len(ws), 1, r["warnings"])
        self.assertIn("00:07", ws[0])
        self.assertIn("may go on", ws[0])
        self.assertNotIn("is recited", ws[0])
        en = next(x for x in md.splitlines() if x.startswith("Smooth zoom"))
        ar = next(x for x in md.splitlines() if "زوم ناعم" in x)
        self.assertIn("1 move stays hard where the verse may go on", en)
        self.assertNotIn("recited", en)
        self.assertIn("في وقت ممكن الآية تكون مكمّلة", ar)
        self.assertNotIn("جوه آية", ar)
        # the editor listened and released it: the punch-in eases again, nothing recorded
        _r, spec, _md = self.compile({"manual_verse_release": [{"start_ms": 6250, "end_ms": 10200}]}, n=1)
        self.assertEqual([x["released"] for x in spec["verse_hold"]], [True])
        self.assertEqual(set(spec["camera_ease"]), {"ease_ms", "curve", "runs"})
        self.assertEqual([(x["ease_in"]["frames"], x["ease_out"]["frames"]) for x in spec["camera_ease"]["runs"]],
                         [(6, 6)])

    def test_the_held_run_is_on_the_reels_frame_clock(self):
        """Pre-mortem risk 1: with a word cut before it (time map), the held run's frames are on the same clock as the
        main segments and as a manual_verse span over the same source time."""
        cut = {"cut_words": [{"word_ids": [2], "reason": "x"}]}
        _r, spec, _md = self.compile(glob=cut)
        hold = spec["verse_hold"][0]
        punch = next(m for m in spec["main_segments"] if m.get("decision_id") == "EDIT_001")
        self.assertLess(punch["start_frame"], 168)                                   # the cut moved it earlier
        fps = spec["fps"]
        self.assertEqual(hold["start_frame"], punch["start_frame"] - round((punch["src_in_ms"] - 6250) * fps / 1000))
        self.assertEqual([h["held"] for h in spec["camera_ease"]["verse_hard"]], [True])
        # the same source time as an editor's span (the hold released): same frames, same guard
        ed = {"manual_verse": [{"start_ms": 6250, "end_ms": 10200}],
              "manual_verse_release": [{"start_ms": 6250, "end_ms": 10200}]}
        _r, spec2, _md = self.compile(ed, glob=cut, n=1)
        mv = next(m for m in spec2["manual_verse"] if m["src_start_ms"] == 6250)
        self.assertEqual((mv["start_frame"], mv["end_frame"]), (hold["start_frame"], hold["end_frame"]))
        self.assertEqual(spec2["camera_ease"]["verse_hard"],
                         [{k: v for k, v in h.items() if k != "held"} for h in spec["camera_ease"]["verse_hard"]])


class TestApplyEaseSelection(unittest.TestCase):
    """Round 9 P2-1: which verse_hold records guard the eases, chosen as previews.render_captions chooses them: not
    released and not cut away (synthetic spec frames, so a cut-away record with a range still shows the rule)."""

    def apply(self, **spec_extra):
        from types import SimpleNamespace
        from lib.plan import apply_ease

        def sg(a, b, cam="hold", sf=1.0, did=None):
            return {"start_frame": a, "end_frame": b, "camera": cam, "scale_factor": sf, "offset_x": 0.0,
                    "offset_y": 0.0, "decision_id": did, "src_in_ms": a * 1000 / 24, "src_out_ms": b * 1000 / 24}
        spec = {"main_segments": [sg(0, 24), sg(24, 72, "punch_in", 1.1, "P"), sg(72, 120)], "duration_ms": 5000,
                **spec_extra}
        out, errs, warns = apply_ease(SimpleNamespace(ctx=None, style={}, fps=24), spec, [])
        self.assertEqual(errs, [])
        return out["camera_ease"], warns

    def test_an_unreleased_held_run_guards(self):
        ce_, w = self.apply(verse_hold=[{"id": "MV01H", "start_frame": 27, "end_frame": 40, "released": False}])
        self.assertEqual([(d["side"], d.get("held")) for d in ce_["verse_dropped"]], [("in", True)])
        self.assertEqual(len(w), 1)

    def test_released_or_cut_away_runs_do_not(self):
        for rec in ({"released": True}, {"released": False, "cut": True}, {"released": True, "cut": True}):
            with self.subTest(rec=rec):
                ce_, w = self.apply(verse_hold=[dict(rec, id="MV01H", start_frame=20, end_frame=80)])
                self.assertEqual(set(ce_), {"ease_ms", "curve", "runs"})
                self.assertEqual(w, [])

    def test_held_runs_and_verses_together_and_bad_entries(self):
        ce_, w = self.apply(manual_verse=[{"id": "MV01", "start_frame": 68, "end_frame": 70}],
                            verse_hold=["x", None, {"id": "MV01H", "start_frame": 26, "end_frame": 27}])
        self.assertEqual(ce_["verse_hard"], [{"decision_id": "P", "camera": "punch_in", "sides": ["in", "out"],
                                              "start_ms": 1000}])
        self.assertEqual(len(w), 1)

    def test_no_verse_and_no_hold_adds_nothing(self):
        ce_, w = self.apply()
        self.assertEqual(set(ce_), {"ease_ms", "curve", "runs"})
        self.assertEqual(w, [])


class TestReapprovalWording(tpa.ApprovalFixture):
    """Ruling 2026-10-17: a re-plan whose fingerprint changed only because the ease keys were added says why."""

    def approve_now(self):
        from lib.plan import plan_fingerprint
        write_json(self.p.p("01_analysis/plan-approval.json"),
                   {"approved": True, "by": "editor", "format": 3, "plan_fingerprint": plan_fingerprint(self.p)})

    def with_ease(self, spec):
        s = copy.deepcopy(spec)
        s["camera_ease"] = {"ease_ms": 250, "runs": [{"decision_id": "EDIT_001", "pieces": [0, 0], "ease_in": None,
                                                      "ease_out": {"piece": 0, "frames": 6, "value": {}, "to": {}},
                                                      "interpolation": "bezier"}]}
        return s

    def test_only_the_ease_keys_changed(self):
        from lib.plan import approval_state
        self.approve_now()
        self.save(self.with_ease(self.spec))
        st = approval_state(self.p)
        self.assertEqual(st["state"], "stale")
        self.assertIn("smooth zoom added to the punch-ins", st["message"])
        self.assertIn("ar", st.get("editor_message") or {})
        self.assertTrue(st["editor_message"]["ar"].strip())
        self.assertNotIn("ease_ms", st["message"] + st["editor_message"]["ar"])        # review I4: editor words only

    def test_i3_the_panel_build_refusal_says_why_too(self):
        """Review I3: `reel serve` / the panel go through ppro_build.approval_refusal, not the CLI."""
        from lib.ppro_build import approval_refusal
        self.approve_now()
        self.save(self.with_ease(self.spec))
        r = approval_refusal(self.p)
        self.assertIsNotNone(r)
        self.assertEqual((r["status"], r["ok"]), ("REFUSED", False))
        self.assertIn("smooth zoom added to the punch-ins", r["blocked"])
        self.assertTrue(r["editor_message"]["ar"].strip())
        self.assertIn("Nothing was built", r["error"])

    def test_i3_another_change_is_the_plain_panel_refusal(self):
        from lib.ppro_build import approval_refusal
        self.approve_now()
        s = self.with_ease(self.spec)
        s["duration_frames"] = 300
        self.save(s)
        r = approval_refusal(self.p)
        self.assertNotIn("smooth zoom", r["blocked"])
        self.assertNotIn("editor_message", r)

    def test_the_build_refusal_says_why_too(self):
        self.approve_now()
        self.save(self.with_ease(self.spec))
        r = tpa.cli(self.root, "ppro-build")
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn("not approved", r.stdout)                    # the wording every caller already looks for
        self.assertIn("smooth zoom added to the punch-ins", r.stdout)

    def test_r3_an_empty_ease_record_keeps_the_approval(self):
        from lib.plan import approval_state
        self.approve_now()
        s = copy.deepcopy(self.spec)
        s["camera_ease"] = {"ease_ms": 250, "curve": "bezier", "runs": []}
        self.save(s)
        self.assertEqual(approval_state(self.p)["state"], "current")

    def test_another_change_too_is_the_plain_message(self):
        from lib.plan import approval_state
        self.approve_now()
        s = self.with_ease(self.spec)
        s["duration_frames"] = 300
        self.save(s)
        st = approval_state(self.p)
        self.assertEqual(st["state"], "stale")
        self.assertNotIn("smooth zoom", st["message"])

    def test_ease_changed_after_an_eased_approval_is_the_plain_message(self):
        from lib.plan import approval_state
        self.save(self.with_ease(self.spec))
        self.approve_now()
        s = self.with_ease(self.spec)
        s["camera_ease"]["ease_ms"] = 400
        self.save(s)
        st = approval_state(self.p)
        self.assertEqual(st["state"], "stale")
        self.assertNotIn("smooth zoom added", st["message"])


if __name__ == "__main__":
    unittest.main()
