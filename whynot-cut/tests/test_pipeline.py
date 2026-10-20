"""Unit + integration tests. Run:
    ~/.whynot-cut/venv/bin/python -m unittest discover -s <plugin>/tests -v
Set NH_INTEGRATION=1 to also run Whisper (uses macOS `say` to synthesize Arabic + English speech).
"""
import sys as _sys
_sys.dont_write_bytecode = True  # keep the plugin folder free of __pycache__
import _isolation  # noqa: F401,E402  G79: sandbox the engine home first (tests/_isolation.py)
import contextlib
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

SK = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SK / "engine" / "reel"))

from lib import common, srt as srtlib  # noqa: E402
from lib import lead_steps  # noqa: E402  BL-15: a lead-only step runs with the guard's token
from lib.common import Paths, ms_to_frame, parse_ts, fmt_ts, write_json  # noqa: E402

from lib.plat import font_dirs  # noqa: E402
FONT_DIR = next((d for d in font_dirs() if (d / "thmanyahserifdisplay-Bold.otf").exists()), font_dirs()[0])
HAS_FONT = (FONT_DIR / "thmanyahserifdisplay-Bold.otf").exists()


def words_from(text_words, start=0, step=400):
    return [{"id": i + 1, "segment_id": 1, "word": w, "start_ms": start + i * step,
             "end_ms": start + i * step + step - 40, "probability": 0.9} for i, w in enumerate(text_words)]


def make_project(tmp: Path, dur_ms=12000):
    """Synthetic client folder + transcribed project with a tiny 25 fps rotated-free video."""
    root = tmp / "CLIENT"
    (root / "assets/Font").mkdir(parents=True)
    (root / "assets/Photos").mkdir(parents=True)
    (root / "assets/Brief").mkdir(parents=True)
    (root / "data/Raw").mkdir(parents=True)
    (root / "data/Ref").mkdir(parents=True)
    (root / "assets/Brief/brief.md").write_text("# Brand\nPrimary #20ACAF and #FFFFFF\n", encoding="utf-8")
    (root / "assets/Photos/._junk.jpg").write_bytes(b"x")
    (root / "data/Ref/style.md").write_text("# Style\nFast captions.\n", encoding="utf-8")
    from PIL import Image
    Image.new("RGB", (400, 700), (200, 120, 120)).save(root / "assets/Photos/p1.jpg")
    Image.new("RGBA", (300, 300), (32, 172, 175, 0)).save(root / "assets/Photos/logo.png")
    if HAS_FONT:
        shutil.copy(FONT_DIR / "thmanyahserifdisplay-Bold.otf", root / "assets/Font/")
    ff = common.ffmpeg_exe()
    subprocess.run([ff, "-y", "-loglevel", "error", "-f", "lavfi", "-i", f"testsrc2=s=216x384:r=25:d={dur_ms/1000}",
                    "-f", "lavfi", "-i", f"sine=f=440:r=48000:d={dur_ms/1000}", "-ac", "2", "-c:v", "libx264", "-pix_fmt", "yuv420p",
                    "-c:a", "pcm_s16le", "-shortest", str(root / "data/Raw/CLIP1.mov")], check=True)
    p = Paths(root, "CLIP1")
    p.ensure_project()
    words = words_from("هل في حاجات معينة لازم أبقى عارفاها قبل الليزر ؟ أول حاجة التشخيص الصحيح Isotretinoin مهم".split(), 200, 700)
    segs = [{"id": 1, "start_ms": 200, "end_ms": words[-1]["end_ms"], "text": " ".join(w["word"] for w in words),
             "avg_logprob": -0.2, "no_speech_prob": 0.01, "compression_ratio": 1.2, "words": [w["id"] for w in words]}]
    meta = {"source_video": str(root / "data/Raw/CLIP1.mov"), "backend": "test", "model": "none", "language": "ar",
            "language_probability": 1.0, "duration_ms": dur_ms}
    from lib.transcribe import finalize
    finalize(p, meta, segs, words)
    return root, p, words


class TestTiming(unittest.TestCase):
    def test_examples(self):
        self.assertEqual(ms_to_frame(1000), 24)
        self.assertEqual(ms_to_frame(2500), 60)
        self.assertEqual(ms_to_frame(5000), 120)
        self.assertEqual(ms_to_frame(10000), 240)

    def test_no_drift(self):
        self.assertEqual(ms_to_frame(3_600_000), 86400)
        # absolute conversion: sum of rounded durations may drift, absolute never does
        self.assertEqual(ms_to_frame(41 * 1000 + 666), round(41.666 * 24))

    def test_rounding_half_up(self):
        self.assertEqual(ms_to_frame(1021), 25)  # 24.504 -> 25
        self.assertEqual(ms_to_frame(1020), 24)  # 24.48 -> 24

    def test_source_rate(self):
        self.assertEqual(ms_to_frame(1000, 25), 25)

    def test_ts_roundtrip(self):
        for s in ("00:00:01,000", "01:02:03,456"):
            self.assertEqual(fmt_ts(parse_ts(s)), s)
        self.assertEqual(parse_ts("00:00:02.5"), 2500)


class TestSRT(unittest.TestCase):
    def test_roundtrip_and_rtl_order(self):
        cues = [{"start_ms": 0, "end_ms": 1000, "text": "هل في حاجات"}, {"start_ms": 1000, "end_ms": 2200, "text": "الـ Isotretinoin دواء"}]
        with tempfile.TemporaryDirectory() as t:
            p = Path(t) / "a.srt"
            srtlib.write_srt(p, cues)
            back = srtlib.read_srt(p)
        self.assertEqual([c["text"] for c in back], [c["text"] for c in cues])  # logical order preserved
        self.assertEqual(srtlib.validate_cues(back, 3000), [])

    def test_overlap_detected(self):
        cues = [{"index": 1, "start_ms": 0, "end_ms": 1500, "text": "a"}, {"index": 2, "start_ms": 1000, "end_ms": 2000, "text": "b"}]
        self.assertTrue(any("overlap" in e for e in srtlib.validate_cues(cues)))

    def test_build_cues_breaks(self):
        w = words_from("هل في حاجات معينة لازم أبقى عارفاها ؟ أول حاجة".split())
        cues = srtlib.build_cues_from_words(w, max_chars=18, max_lines=1, max_words=4)
        self.assertTrue(all(len(c["text"]) <= 18 + 6 or " " not in c["text"] for c in cues))  # +orphan slack
        self.assertTrue(cues[1]["text"].endswith("؟") or any(c["text"].endswith("؟") for c in cues))
        self.assertEqual(srtlib.validate_cues(cues), [])
        for c in cues:
            self.assertEqual(c["start_frame"], ms_to_frame(c["start_ms"]))

    def test_orphan_merge(self):
        w = words_from("مبدئياً، يعني إيه Scar كريم؟ أصدق إيه؟".split())
        cues = srtlib.build_cues_from_words(w, max_chars=18, max_lines=1, max_words=4)
        self.assertFalse(any(len(c["word_ids"]) == 1 and c["text"] == "كريم؟" for c in cues))

    def test_segment_boundary_breaks(self):
        w = words_from("مش هيسيب سكار إلا لو طبيعتك".split())
        for x in w[3:]:
            x["segment_id"] = 2
        cues = srtlib.build_cues_from_words(w, max_chars=40, max_lines=2)
        self.assertEqual([c["text"] for c in cues], ["مش هيسيب سكار", "إلا لو طبيعتك"])

    def test_english_cues(self):
        w = words_from("Laser is not permanent hair removal. It is reduction.".split())
        cues = srtlib.build_cues_from_words(w)
        self.assertTrue(cues[0]["text"].replace("\n", " ").endswith("removal."))


class TestWrap(unittest.TestCase):
    def test_balanced_no_orphan(self):
        from lib.ae_builder import wrap_lines
        out = wrap_lines("وكل ما كان بدري كل ما كان أحسن", 26).split("\r")
        self.assertEqual(len(out), 2)
        self.assertTrue(all(len(l.split()) >= 3 for l in out), out)

    def test_latin_term_not_split(self):
        from lib.ae_builder import wrap_lines
        self.assertIn("Hypertrophic", wrap_lines("إلا لو طبيعتك بقى Hypertrophic Scar", 14).split("\r")[-1] + " " +
                      " ".join(wrap_lines("إلا لو طبيعتك بقى Hypertrophic Scar", 14).split("\r")))


class TestDiscoveryAndClientDB(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp())
        cls.root, cls.p, cls.words = make_project(cls.tmp)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_discovery(self):
        from lib.discover import run_discovery
        r = run_discovery(self.p)
        roles = r["inventory"]["by_role"]
        self.assertIn("source_footage", roles)
        self.assertIn("editing_reference_doc", roles)
        self.assertFalse(any("._junk" in f["rel"] for f in r["inventory"]["files"]))
        self.assertTrue((self.root / "assets/Photos/._junk.jpg").exists())  # source untouched

    def test_client_db_colors_and_missing_font(self):
        from lib.discover import run_discovery
        from lib.client_db import build
        inv = run_discovery(self.p)["inventory"]
        st = build(self.p, inv)
        tok = json.loads((self.p.client_db / "branding/brand-tokens.json").read_text(encoding="utf-8"))
        self.assertEqual([c["hex"] for c in tok["official_colors"]], ["#20ACAF", "#FFFFFF"])
        typ = json.loads((self.p.client_db / "branding/typography.json").read_text(encoding="utf-8"))
        if HAS_FONT:
            fam = next(iter(typ["families"].values()))
            self.assertTrue(fam["supports_arabic"])
        man = json.loads((self.p.client_db / "asset-manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(len(man["assets"]), 2)

    def test_font_not_installed_is_reported(self):
        from lib.client_db import font_info
        if not HAS_FONT:
            self.skipTest("brand font not installed")
        tmpf = self.tmp / "renamed-font.otf"
        shutil.copy(FONT_DIR / "thmanyahserifdisplay-Bold.otf", tmpf)
        self.assertFalse(font_info(tmpf)["installed"])

    def test_media_probe_and_preflight(self):
        from lib.media import preflight
        rep = preflight(self.p, [self.root / "data/Raw/CLIP1.mov", self.root / "data/Raw/missing.mov"])
        self.assertFalse(rep["ok"])  # missing file -> error
        v = rep["files"][0]["video"]
        self.assertEqual(round(v["fps"]), 25)
        self.assertTrue(any("25" in i["msg"] for i in rep["issues"]))


class TestPlanToXML(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp())
        cls.root, cls.p, cls.words = make_project(cls.tmp)
        from lib.discover import run_discovery
        from lib.client_db import build
        from lib.media import preflight
        build(cls.p, run_discovery(cls.p)["inventory"])
        preflight(cls.p, [cls.root / "data/Raw/CLIP1.mov"])

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def decisions(self, evidence="هل في حاجات معينة", overlap=False):
        g2s = "00:00:02.000" if overlap else "00:00:05.000"
        return {"video_id": "CLIP1", "global": {"main_footage": "data/Raw/CLIP1.mov"},
                "caption_highlights": [{"text": "التشخيص الصحيح", "at": "00:00:08.600"}],
                "decisions": [
                    {"decision_id": "EDIT_001", "segment_id": "SEG_001", "evidence": evidence, "start": "00:00:00.200",
                     "end": "00:00:04.000", "semantic_intent": "hook", "visual_treatment": "hook", "confidence": "high",
                     "camera": {"type": "punch_in", "at": "00:00:01.000", "until": "00:00:03.000", "scale_factor": 1.1},
                     "graphics": [{"id": "GFX_001", "template": "hook_title", "start": "00:00:00.200", "end": "00:00:03.500",
                                   "text": "هل في حاجات معينة"}]},
                    {"decision_id": "EDIT_002", "segment_id": "SEG_002", "evidence": "أول حاجة التشخيص الصحيح", "start": "00:00:05.000",
                     "end": "00:00:10.000", "semantic_intent": "point", "visual_treatment": "list", "confidence": "high",
                     "graphics": [{"id": "GFX_002", "template": "hook_title" if overlap else "checklist", "start": g2s,
                                   "end": "00:00:09.000", "text": "x", "title": "خطوات",
                                   "items": [{"text": "التشخيص", "at": "00:00:06.000"}, {"text": "Isotretinoin", "at": "00:00:07.500", "latin": True}]},
                                  {"id": "GFX_003", "template": "name_card", "start": "00:00:09.000", "end": "00:00:11.500",
                                   "name": "د/ نهلة هنتر", "lines": ["كلية طب القصر العيني"]}]}]}

    def _semantic_stub(self):
        for f in ("main-topic.md", "medical-content-review.md"):
            (self.p.p("01_analysis") / f).write_text("# stub\n", encoding="utf-8")
        for f in ("narrative-segments.json", "transcript-semantic-analysis.json", "editing-style.json"):
            write_json(self.p.p("01_analysis") / f, {"stub": True})

    def test_1_bad_evidence_rejected(self):
        from lib.plan import compile_plan
        write_json(self.p.p("01_analysis/edit-decisions.json"), self.decisions(evidence="كلام غير موجود"))
        r = compile_plan(self.p)
        self.assertFalse(r["ok"])
        self.assertTrue(any("evidence not found" in e for e in r["errors"]))

    def test_2_overlap_rejected(self):
        from lib.plan import compile_plan
        write_json(self.p.p("01_analysis/edit-decisions.json"), self.decisions(overlap=True))
        r = compile_plan(self.p)
        self.assertTrue(any("overlaps" in e for e in r["errors"]))

    def test_3_full_chain(self):
        from lib.plan import compile_plan
        from lib.previews import render_all
        from lib.sfx import synth_needed
        from lib.premiere_xml import build_xml, TPS
        from lib.qc import run_qc
        from lib.handoff import build as handoff
        from lib.ae_builder import generate as ae_gen
        self._semantic_stub()
        write_json(self.p.p("01_analysis/edit-decisions.json"), self.decisions())
        r = compile_plan(self.p)
        self.assertTrue(r["ok"], r["errors"])
        spec = json.loads(self.p.p("01_analysis/timeline-spec.json").read_text(encoding="utf-8"))
        g1 = next(e for e in spec["events"] if e["event_id"] == "GFX_001")
        self.assertEqual((g1["start_frame"], g1["end_frame"]), (5, 84))
        cl = next(e for e in spec["events"] if e["template"] == "checklist")
        self.assertEqual([i["frame"] for i in cl["params"]["items"]], [144, 180])
        self.assertEqual([s["start_frame"] for s in spec["main_segments"]][:3], [0, 24, 72])
        # B-roll manifest + cue sheet
        bm = json.loads(self.p.p("03_broll/broll-manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(len(bm["assets"]), 3)
        cues = json.loads(self.p.p("06_audio/audio-cue-sheet.json").read_text(encoding="utf-8"))["cues"]
        self.assertTrue(all(c["start_frame"] == ms_to_frame(c["at_ms"]) for c in cues))
        # assets
        render_all(self.p, composite_preview=True)
        synth_needed({c["kind"] for c in cues}, self.p.p("06_audio/sfx"))
        self.assertTrue(self.p.p("03_broll/educational-graphics/GFX_002.png").exists())
        # AE script syntax (JavaScriptCore parse; ExtendScript directives stripped)
        jsx = Path(ae_gen(self.p)["jsx"])
        assert_js_syntax(self, jsx)
        # XML
        tm = build_xml(self.p)
        root = ET.parse(tm["xml"]).getroot()
        sc = root.find("./sequence/media/video/format/samplecharacteristics")
        self.assertEqual((sc.findtext("width"), sc.findtext("height")), ("1080", "1920"))
        self.assertEqual(root.findtext("./sequence/rate/timebase"), "24")
        v1 = root.find("./sequence/media/video/track")
        first = v1.find("clipitem")
        self.assertEqual(int(first.findtext("pproTicksOut")), int(first.findtext("end")) * TPS // 24)
        self.assertEqual(tm["missing_events"], [])
        # evidence gates: QC must fail until plan approved + visual verification recorded
        q0 = run_qc(self.p)
        self.assertFalse(q0["ok"])
        self.assertTrue(any("Visual verification" in f["check"] for f in q0["failed"]))
        nh = [sys.executable, str(SK / "engine/reel/cli.py"), "--root", str(self.root), "--video-id", "CLIP1"]
        extras = subprocess.run(nh + ["ae-build"], capture_output=True, text=True)
        self.assertEqual(extras.returncode, 2, extras.stdout + extras.stderr)  # AE is an opt-in extra
        self.assertIn("optional After Effects", extras.stdout)
        blocked = subprocess.run(nh + ["ppro-build"], capture_output=True, text=True)
        self.assertEqual(blocked.returncode, 2, blocked.stdout + blocked.stderr)  # approval gate blocks the build
        self.assertIn("not approved", blocked.stdout)
        blocked_ae = subprocess.run(nh + ["ae-build", "--extras"], capture_output=True, text=True)
        self.assertIn("not approved", blocked_ae.stdout)
        lead_steps.issue_for(nh[2:] + ["approve-plan", "--by", "editor"])      # BL-15: the lead's token
        subprocess.run(nh + ["approve-plan", "--by", "editor"], check=True, capture_output=True)
        from lib import verify
        vb = verify.build(self.p)
        self.assertTrue(Path(vb["sheet"]).exists())
        self.assertIn("GFX_001", (self.p.p("08_quality_control/verify/verify-checklist.md")).read_text(encoding="utf-8"))
        verify.record(self.p, "pass", "unit test")
        q = run_qc(self.p)
        self.assertTrue(q["ok"], q["failed"])
        rs = next(c for c in q["checks"] if c["check"].startswith("Client reference style current"))
        self.assertEqual((rs["mandatory"], rs["result"]), (False, "WARN"))    # data/Ref/style.md, no client style yet
        self.assertTrue(self.p.p("01_analysis/edit-plan.md").exists())
        # re-plan with a change -> approval goes stale -> QC fails again
        ed = self.decisions()
        ed["decisions"][0]["graphics"][0]["text"] = "هل في حاجات"
        write_json(self.p.p("01_analysis/edit-decisions.json"), ed)
        self.assertTrue(compile_plan(self.p)["ok"])
        self.assertTrue(any("approved" in f["check"] for f in run_qc(self.p)["failed"]))
        write_json(self.p.p("01_analysis/edit-decisions.json"), self.decisions())
        compile_plan(self.p)
        lead_steps.issue_for(nh[2:] + ["approve-plan", "--by", "delegated", "--note", "test"])
        subprocess.run(nh + ["approve-plan", "--by", "delegated", "--note", "test"], check=True, capture_output=True)
        self.assertTrue(run_qc(self.p)["ok"])
        # watchable preview of the plan: same layers as the Premiere build, real H.264 + AAC of the sequence length
        from lib.preview_video import render as preview
        from lib.media import probe
        with contextlib.redirect_stderr(io.StringIO()):       # its `[time] preview video: ...` log line (T2.16 review)
            pv = preview(self.p, width=270)
        self.assertTrue(pv["ok"], pv)
        pr = probe(Path(pv["video"]))
        self.assertAlmostEqual(pr["duration_s"], spec["duration_frames"] / 24, delta=0.25)
        self.assertEqual((pr["video"]["display_width"], pr["video"]["display_height"]), (270, 480))
        self.assertTrue(pr["audio"], "preview has no audio")
        handoff(self.p)
        self.assertIn("Sequence Settings", self.p.p("09_handoff/README.md").read_text(encoding="utf-8"))
        # missing media path -> QC failure
        os.remove(self.p.p("03_broll/educational-graphics/GFX_002.png"))
        q2 = run_qc(self.p)
        self.assertFalse(q2["ok"])


def assert_js_syntax(tc, jsx: Path):
    src = "\n".join(l for l in jsx.read_text(encoding="utf-8").splitlines() if not l.startswith("#"))
    if shutil.which("osascript"):
        wrapped = "new Function(" + json.dumps(src) + "); 'SYNTAX_OK'"
        r = subprocess.run(["osascript", "-l", "JavaScript", "-e", wrapped], capture_output=True, text=True)
    elif shutil.which("node"):   # Windows/Linux: same check, source on stdin (too long for a command line)
        code = "let s='';process.stdin.on('data',d=>s+=d).on('end',()=>{new Function(s);console.log('SYNTAX_OK')})"
        r = subprocess.run(["node", "-e", code], input=src, capture_output=True, text=True, encoding="utf-8")
    else:
        tc.skipTest("needs osascript (macOS) or node for the JavaScript syntax check")
    tc.assertIn("SYNTAX_OK", r.stdout, r.stderr[:500])


class TestTemplatesSyntax(unittest.TestCase):
    def test_ae_lib(self):
        assert_js_syntax(self, SK / "templates/after_effects/wnc_ae_lib.jsx")

    def test_ps_lib(self):
        assert_js_syntax(self, SK / "templates/photoshop/wnc_ps_lib.jsx")


class TestSFX(unittest.TestCase):
    def test_all_recipes(self):
        from lib.sfx import RECIPES, synth_needed
        import av
        from lib.premiere_xml import audio_duration
        with tempfile.TemporaryDirectory() as t:
            r = synth_needed(set(RECIPES), Path(t))
            for k, v in r.items():
                with av.open(v["file"]) as c:
                    a = c.streams.audio[0].codec_context
                    self.assertEqual((a.sample_rate, a.channels, a.name), (48000, 2, "pcm_s24le"))
                self.assertAlmostEqual(audio_duration(Path(v["file"])), RECIPES[k][1], delta=0.02)


@unittest.skipUnless(os.environ.get("NH_INTEGRATION") == "1", "set NH_INTEGRATION=1 for Whisper tests")
class TestWhisperIntegration(unittest.TestCase):
    def _run(self, voice, text, lang_expect):
        from lib.transcribe import transcribe
        tmp = Path(tempfile.mkdtemp())
        aiff = tmp / "s.aiff"
        subprocess.run(["say", "-v", voice, "-o", str(aiff), text], check=True)
        mov = tmp / "CLIENT/data/Raw/S.mov"
        mov.parent.mkdir(parents=True)
        (tmp / "CLIENT/assets").mkdir()
        subprocess.run([common.ffmpeg_exe(), "-y", "-loglevel", "error", "-f", "lavfi", "-i", "color=c=black:s=216x384:r=24",
                        "-i", str(aiff), "-shortest", "-c:v", "libx264", "-c:a", "aac", str(mov)], check=True)
        p = Paths(tmp / "CLIENT", "S")
        p.ensure_project()
        r = transcribe(p, mov, model_size=os.environ.get("NH_TEST_MODEL", "large-v3"))
        self.assertEqual(r["meta"]["language"], lang_expect)
        self.assertGreater(r["words"], 2)
        cues = srtlib.read_srt(p.p("02_transcription/subtitles.srt"))
        self.assertEqual(srtlib.validate_cues(cues), [])
        shutil.rmtree(tmp, ignore_errors=True)
        return r

    def test_arabic(self):
        self._run("Majed", "البشرة الصحية تبدأ بفهم بشرتك والتشخيص الصحيح", "ar")

    def test_english(self):
        self._run("Samantha", "Healthy skin starts with understanding your skin.", "en")


if __name__ == "__main__":
    unittest.main()
