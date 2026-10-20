"""Task 29 (R-4.7): emphasis candidates through the REAL plan compile (HEAD plan.py, T4.1 eases), no patch needed.

The story-editor copies a candidate's `decision` into edit-decisions.json; `reel plan` must then compile exactly the
scale and offsets emphasis.py measured (single camera and the podcast shot layer), ease it as T4.1 says, and keep the
head inside the frame on every frame of every ease. Cases: lane4\\work\\task29\\cases.md F57-F63 (+ E52 parity).
Run:  bash tools/test.sh -p test_emphasis_plan.py
"""
import sys as _sys
_sys.dont_write_bytecode = True  # keep the plugin folder free of __pycache__
import _isolation  # noqa: F401,E402  G79: sandbox the engine home first (tests/_isolation.py)
import inspect  # noqa: E402
import json  # noqa: E402
import shutil  # noqa: E402
import tempfile  # noqa: E402
import unittest  # noqa: E402
from pathlib import Path  # noqa: E402

sys = _sys
SK = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SK / "engine" / "reel"))

from lib import common  # noqa: E402
from lib.common import write_json, read_json  # noqa: E402
import test_pipeline as tp  # noqa: E402  (module import: its TestCases are not collected again here)
import test_podcast as tpod  # noqa: E402
from test_emphasis import head, samples_doc  # noqa: E402

FACE = [0.5, 0.42, 0.3, 0.2]


def E():
    from lib import emphasis
    return emphasis


class Base(unittest.TestCase):
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
        for f in ("06_audio/dialogue/pauses.json", "01_analysis/emphasis.json"):
            if self.p.p(f).exists():
                self.p.p(f).unlink()
        write_json(self.p.p(E().FACES_FILE), dict(samples_doc(lambda t: [FACE], t1=12000, w=216, h=384),
                                                  footage="data/Raw/CLIP1.mov"))
        self.ed({})

    def ed(self, g, decisions=()):
        write_json(self.p.p("01_analysis/edit-decisions.json"),
                   {"video_id": "CLIP1", "global": dict({"main_footage": "data/Raw/CLIP1.mov"}, **g),
                    "decisions": list(decisions)})

    def emphasis(self):
        with common.use_context(common.Context(root=self.root)) as _:
            return E().run(self.p, common.Context(root=self.root), audio=False)

    def compile(self, g, decisions):
        from lib.plan import compile_plan
        self.ed(g, decisions)
        with common.use_context(common.Context(root=self.root)):
            r = compile_plan(self.p)
        self.assertTrue(r["ok"], r["errors"])
        return r, read_json(self.p.p("01_analysis/timeline-spec.json"))


class TestEases(Base):
    def test_f57_f58_a_kept_candidate_is_an_eased_story_punch(self):
        from lib.camera_ease import _is_story, ease_frames
        doc = self.emphasis()
        self.assertEqual(len(doc["candidates"]), 1, doc["dropped"])
        c = doc["candidates"][0]
        self.assertEqual(c["ease"], {"in": "eased", "out": "eased"})
        r, spec = self.compile({}, [c["decision"]])
        pieces = [s for s in spec["main_segments"] if s.get("decision_id") == c["decision"]["decision_id"]]
        self.assertTrue(pieces and all(_is_story(s) for s in pieces))
        self.assertEqual({s["scale_factor"] for s in pieces}, {c["scale"]})
        self.assertEqual({(s["offset_x"], s["offset_y"]) for s in pieces}, {(c["offset_x"], c["offset_y"])})
        runs = [x for x in spec["camera_ease"]["runs"] if x["decision_id"] == c["decision"]["decision_id"]]
        self.assertEqual(len(runs), 1)
        self.assertEqual(runs[0]["ease_in"]["frames"], ease_frames(250, spec["fps"]))
        self.assertEqual(runs[0]["ease_out"]["frames"], ease_frames(250, spec["fps"]))
        self.assertEqual([ease_frames(250, f) for f in (24, 30000 / 1001, 30)], [6, 7, 8])
        self.assertFalse(any("recipe" in w for w in r["warnings"]))

    def test_f59_a_punch_at_a_pause_cut_is_hard_on_that_side(self):
        write_json(self.p.p("06_audio/dialogue/pauses.json"), {"keep_ms": [[0, 7000], [7200, 12000]],
                                                              "cuts_ms": [[7000, 7200]]})
        self.ed({"remove_pauses": True})
        doc = self.emphasis()
        c = doc["candidates"][0]
        self.assertEqual(c["start_ms"], 7200)
        self.assertTrue(c["ease"]["in"].startswith("hard"), c["ease"])
        self.assertEqual(c["ease"]["out"], "eased")
        self.assertIn("حاد", c["reason"])
        self.assertNotIn("smooth", c["reason_en"].lower().split("hard")[0] if "hard" in c["reason_en"] else "")
        _, spec = self.compile({"remove_pauses": True}, [c["decision"]])
        run = next(x for x in spec["camera_ease"]["runs"] if x["decision_id"] == c["decision"]["decision_id"])
        self.assertIsNone(run["ease_in"])
        self.assertIsNotNone(run["ease_out"])

    def test_f60_the_head_stays_inside_on_every_frame_of_every_ease(self):
        from lib.camera_ease import value_at
        doc = self.emphasis()
        c = doc["candidates"][0]
        _, spec = self.compile({}, [c["decision"]])
        S = float(spec["base_scale_percent"] or 500.0) / 100
        hb = head(FACE)
        n_frames = 0
        for run in spec["camera_ease"]["runs"]:
            for side in ("ease_in", "ease_out"):
                e = run[side]
                if not e:
                    continue
                piece = e["piece"]
                seg = spec["main_segments"][piece]
                n = seg["end_frame"] - seg["start_frame"]
                frames = range(0, e["frames"] + 1) if side == "ease_in" else range(n - e["frames"], n + 1)
                for f in frames:
                    v = value_at(spec, piece, f)
                    P = S * v["scale_factor"]
                    cx = 540 + spec["base_offset_x"] + v["offset_x"]
                    cy = 960 + spec["base_offset_y"] + v["offset_y"]
                    x0, y0 = cx + (hb[0] - 0.5) * 216 * P, cy + (hb[1] - 0.5) * 384 * P
                    x1, y1 = cx + (hb[2] - 0.5) * 216 * P, cy + (hb[3] - 0.5) * 384 * P
                    self.assertTrue(0 <= x0 and x1 <= 1080 and 0 <= y0 and y1 <= 1920, (run, f, v))
                    self.assertLessEqual(cx - 216 * P / 2, 1e-6)          # no black edge mid-ease either
                    self.assertGreaterEqual(cy + 384 * P / 2, 1920 - 1e-6)
                    n_frames += 1
        self.assertGreater(n_frames, 10)

    def test_f61_the_4_5_window_stays_hard(self):
        self.ed({"framing": "4:5"})
        doc = self.emphasis()
        c = doc["candidates"][0]
        self.assertEqual(c["ease"], {"in": "hard: 4:5 window", "out": "hard: 4:5 window"})
        self.assertIn("في شباك 4:5 الزوم حاد", c["reason"])
        _, spec = self.compile({"framing": "4:5"}, [c["decision"]])
        self.assertEqual(spec["camera_ease"]["runs"], [])

    def test_f62_ease_off_still_proposes_hard_punches(self):
        self.style_f.parent.mkdir(parents=True, exist_ok=True)
        write_json(self.style_f, {"camera": {"ease_ms": 0}})
        doc = self.emphasis()
        c = doc["candidates"][0]
        self.assertEqual(c["ease"], {"in": "hard: smooth zoom off", "out": "hard: smooth zoom off"})
        self.assertIn("الزوم الناعم مقفول", c["reason"])

    def test_f63_t41_contract_pin(self):
        from lib import camera_ease as ce
        self.assertEqual(list(inspect.signature(ce.ease_settings).parameters), ["style"])
        self.assertEqual(list(inspect.signature(ce.ease_frames).parameters), ["ms", "fps"])
        self.assertEqual(list(inspect.signature(ce.with_shots).parameters), ["segments", "camera", "fps"])
        self.assertEqual(list(inspect.signature(ce.ease_keys).parameters), ["segments", "fps", "ease_ms"])
        self.assertEqual(list(inspect.signature(ce.value_at).parameters), ["spec", "piece", "frame_in_piece"])
        self.assertEqual(list(inspect.signature(ce.spec_fields).parameters),
                         ["segments", "style", "fps", "duration_ms", "camera", "verse"])
        self.assertEqual(ce.STORY_MOVES, {"punch_in", "slow_push"})
        self.assertEqual(ce.ease_settings({"camera": {"ease_ms": 0}}), (0, []))


class TestPlanCheck(Base):
    """H77-H80, H84 and the Q10 / Q15 rulings: emphasis.plan_check on HEAD's own plan steps (read_inputs ->
    validate_decisions -> build_camera -> apply_framing -> apply_timemap), the composed camera the plan builds."""

    def check(self, g, decisions):
        from lib import plan
        self.ed(g, decisions)
        ctx = common.Context(root=self.root)
        with common.use_context(ctx):
            inp = plan.read_inputs(self.p, ctx)
            inp.emphasis = E().plan_inputs(self.p, ctx, inp.main_file, inp.rng, inp.pre_all)
            vd, e0, _ = plan.validate_decisions(inp)
            self.assertEqual(e0, [])
            cam, _, _ = plan.build_camera(inp, vd["camera"], vd["events"])
            fr, _, _ = plan.apply_framing(inp, cam)
            tm, _, _ = plan.apply_timemap(inp, fr["camera"], fr["merged"], vd["events"], vd["broll"], vd["cues"],
                                          cam["box"])
            return E().plan_check(inp, cam, fr, tm)

    def candidate(self):
        doc = self.emphasis()
        self.assertEqual(len(doc["candidates"]), 1, doc["dropped"])
        return json.loads(json.dumps(doc["candidates"][0]["decision"]))

    def test_h77_a_kept_candidate_passes_and_a_raised_scale_is_refused(self):
        d = self.candidate()
        e, w, info = self.check({}, [d])
        self.assertEqual(e, [])
        self.assertEqual(info, {"kept": 1, "review": []})                 # nothing moved or cut: no "changed"
        d["camera"]["scale_factor"] = 2.0
        e, w, info = self.check({}, [d])
        self.assertEqual(len(e), 1, e)
        self.assertIn("crops the head", e[0])
        self.assertIn("scale_factor <= 1.", e[0])

    def test_h78_a_moved_punch_is_measured_again_and_no_samples_means_review(self):
        write_json(self.p.p(E().FACES_FILE), dict(samples_doc(lambda t: [FACE] if t < 9000 else [], t1=12000, w=216,
                                                              h=384), footage="data/Raw/CLIP1.mov"))
        d = self.candidate()
        d["camera"]["at"], d["camera"]["until"] = "00:00:09.100", "00:00:10.300"
        d["start"], d["end"] = "00:00:09.100", "00:00:10.300"
        e, w, info = self.check({}, [d])
        self.assertEqual(e, [])
        self.assertTrue(any("moved from its candidate" in x for x in w), w)
        self.assertEqual([(c["decision_id"], c["what"]) for c in info["changed"]], [(d["decision_id"], "moved")])
        self.assertEqual(len(info["review"]), 1)
        self.assertEqual(info["review"][0]["reason"], "مفيش وش متقاس هنا، راجعها بنفسك")

    def test_h79_plain_punch_crop_is_a_warning_and_offset_y_black_edge_too(self):
        plain = tp_decision("EDIT_001", "00:00:07.200", "00:00:09.900", "أول حاجة التشخيص الصحيح",
                            camera={"type": "punch_in", "at": "00:00:07.200", "until": "00:00:09.900",
                                    "scale_factor": 2.0})
        e, w, info = self.check({}, [plain])
        self.assertEqual(e, [])
        self.assertIsNone(info)
        self.assertTrue(any("crops the head" in x for x in w), w)
        edge = tp_decision("EDIT_001", "00:00:07.200", "00:00:09.900", "أول حاجة التشخيص الصحيح",
                           camera={"type": "slow_push", "at": "00:00:07.200", "until": "00:00:09.900",
                                   "scale_factor": 1.1, "offset_y": 900})
        e, w, info = self.check({}, [edge])
        self.assertEqual(e, [])
        self.assertTrue(any("black edge" in x and "offset_y between -96 and 96" in x for x in w), w)

    def test_h80_stale_candidates_one_warning(self):
        d = self.candidate()
        d["camera"]["emphasis"]["inputs_sha1"] = "0" * 40
        _, w, _ = self.check({}, [d])
        self.assertEqual(sum("made from other inputs" in x for x in w), 1)

    def test_h84_cut_words_inside_a_kept_punch(self):
        d = self.candidate()
        _, w, info = self.check({"cut_words": [12]}, [d])
        self.assertTrue(any("crosses a cut" in x for x in w), w)
        self.assertEqual([(c["decision_id"], c["what"]) for c in info["changed"]], [(d["decision_id"], "cut")])
        self.assertTrue(any("made from other inputs" in x for x in w), w)

    def test_q10_no_face_candidates_are_unticked_and_listed_for_review(self):
        self.p.p(E().FACES_FILE).unlink()
        doc = self.emphasis()
        c = doc["candidates"][0]
        self.assertEqual((c["needs_review"], c["default_keep"], c["scale"]), (True, False, 1.05))
        e, w, info = self.check({}, [c["decision"]])
        self.assertEqual(e, [])
        self.assertEqual([r["decision_id"] for r in info["review"]], [c["decision"]["decision_id"]])
        self.assertEqual(info["review"][0]["reason"], "مفيش عينات للوش: شغّل reel emphasis --faces")


def tp_decision(did, a, b, evidence, **kw):
    d = {"decision_id": did, "segment_id": "S1", "evidence": evidence, "start": a, "end": b, "semantic_intent": "x",
         "visual_treatment": "x", "confidence": "high"}
    d.update(kw)
    return d


class TestEndingsPlanCheck(Base):
    def check(self, prof, g, decisions):
        from lib import plan, endings
        prof_f = self.root / common.CLIENT_PROFILE_REL / "profile.json"
        prof_f.parent.mkdir(parents=True, exist_ok=True)
        write_json(prof_f, prof)
        self.addCleanup(prof_f.unlink)
        self.ed(g, decisions)
        ctx = common.Context(root=self.root)
        with common.use_context(ctx):
            inp = plan.read_inputs(self.p, ctx)
            vd, _, _ = plan.validate_decisions(inp)
            cam, _, _ = plan.build_camera(inp, vd["camera"], vd["events"])
            fr, _, _ = plan.apply_framing(inp, cam)
            tm, _, _ = plan.apply_timemap(inp, fr["camera"], fr["merged"], vd["events"], vd["broll"], vd["cues"],
                                          cam["box"])
            au, _, _ = plan.build_audio(inp, tm["cues"], tm["tmap"], tm["dur_f"])
            return endings.plan_check(inp, tm, au["music"])

    def test_g69_g71_on_a_real_plan(self):
        prof = {"endings": {"cta": {"on": True, "keyword_ar": "التشخيص"}, "follow": {"on": True, "handle": "@dr.x"},
                            "sign_off": {"on": True, "phrase": "Isotretinoin مهم"}}}
        cta = tp_decision("EDIT_001", "00:00:07.200", "00:00:09.900", "أول حاجة التشخيص الصحيح",
                          graphics=[{"id": "GFX_C", "template": "cta", "text": "اكتب التشخيص", "start": "00:00:07.200",
                                     "end": "00:00:09.000"},
                                    {"id": "GFX_F", "template": "cta", "text": "@dr.x", "ending": "follow",
                                     "start": "00:00:09.000", "end": "00:00:10.300"}])
        e, w, info = self.check(prof, {}, [cta])
        self.assertEqual(info["span"]["source"], "phrase")
        self.assertEqual(info["span"]["start_ms"], 200 + 14 * 700)
        self.assertTrue(any("GFX_F" in x and "covers the protected sign-off" in x for x in e), e)
        self.assertTrue(any("GFX_F" in x and "1.5" in x for x in e), e)
        self.assertTrue(any("not measured" in x for x in w), w)          # no font in the test sandbox: said, not passed

    def test_endings_off_is_silent(self):
        e, w, info = self.check({}, {}, [])
        self.assertEqual((e, w, info["span"], info["parts"]), ([], [], None, []))


class TestPodcastParity(unittest.TestCase):
    """E52: the scale and offsets emphasis.py measured on the composed shot layer are the ones `reel plan` compiles."""

    def setUp(self):
        from lib.transcribe import finalize
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.addCleanup(common.set_context, None)
        self.reel = tpod.TestShots.shot_reel(None, self.tmp)       # shots: 0-3 s face at 0.70, 3-8 s face at 0.30
        from test_emphasis import ws
        words = ws(["كلام جميل جدا"], t0=300) + ws(["٣ كيلو في الأسبوع"], t0=3500, id0=4)
        finalize(self.reel, {"source_video": "x", "backend": "test", "model": "none", "language": "ar",
                             "language_probability": 1.0, "duration_ms": 8000},
                 [{"id": 1, "start_ms": 300, "end_ms": words[-1]["end_ms"], "text": " ".join(w["word"] for w in words),
                   "avg_logprob": -0.2, "no_speech_prob": 0.0, "compression_ratio": 1.1,
                   "words": [w["id"] for w in words]}], words)
        write_json(self.reel.p(E().FACES_FILE), dict(samples_doc(lambda t: [[0.70 if t < 3000 else 0.30, 0.4, 0.05, 0.08]],
                                                                 t1=8000, w=640, h=360),
                                                     footage="data/Episodes/E.mp4", range={"in_ms": 1000, "out_ms": 9000},
                                                     video_id="E_R01"))
        write_json(self.reel.p("01_analysis/edit-decisions.json"), {"video_id": "E_R01", "global": {}, "decisions": []})

    def test_e52_the_compiled_values_are_the_measured_ones(self):
        from lib.plan import compile_plan
        ctx = common.set_context(self.reel.root)
        doc = E().run(self.reel, ctx, audio=False)
        self.assertEqual(len(doc["candidates"]), 1, doc["dropped"])
        c = doc["candidates"][0]
        write_json(self.reel.p("01_analysis/edit-decisions.json"),
                   {"video_id": "E_R01", "global": {}, "decisions": [c["decision"]]})
        r = compile_plan(self.reel)
        self.assertTrue(r["ok"], r["errors"])
        spec = read_json(self.reel.p("01_analysis/timeline-spec.json"))
        seg = next(s for s in spec["main_segments"] if s.get("decision_id") == c["decision"]["decision_id"])
        fr = E().geometry_from(read_json(self.reel.p("00_inputs/preflight.json")), "data/Episodes/E.mp4", {}, {},
                               (1080, 1920), {}, {})
        P, cx, cy = E().compose(fr, c["start_ms"], c["scale"], c["offset_x"], c["offset_y"])
        self.assertAlmostEqual(spec["base_scale_percent"] / 100 * seg["scale_factor"], P, places=4)
        self.assertAlmostEqual(540 + spec["base_offset_x"] + seg["offset_x"], cx, places=1)
        self.assertAlmostEqual(960 + spec["base_offset_y"] + seg["offset_y"], cy, places=1)


if __name__ == "__main__":
    unittest.main()
