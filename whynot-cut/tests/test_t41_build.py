"""3.0 T4.1 smooth zoom and fades through the real `reel plan` -> `ppro_build.build` path (only the bridge is mocked:
its status and submit), plus the captions the build sends with them.

* review I5: an eased plan really sends `camera_keys` (the spec's runs) and `fades` to Premiere (no mocked job_data);
* review C2: a 4:5 window reel sends no camera keys (its speaker is the windowed clip, V1 the blurred cover copy);
* executor hunk (T4.2): the native caption track and the animated captions follow the compiled spec's
  `style.captions_during_hook` ("show" keeps captions under the hook title; no style block hides them, the safe default);
* review M4: the native caption track (a caption track cannot fade) keeps out of the picture fade windows, so no
  caption sits over black at the reel's start or end. The animated captions are video items and fade with the picture.
Run:  bash tools/test.sh -p test_t41_build.py
"""
import sys as _sys
_sys.dont_write_bytecode = True  # keep the plugin folder free of __pycache__
import _isolation  # noqa: F401,E402  G79: sandbox the engine home first (tests/_isolation.py)
import gzip  # noqa: E402
import json  # noqa: E402
import shutil  # noqa: E402
import tempfile  # noqa: E402
import unittest  # noqa: E402
from pathlib import Path  # noqa: E402
from unittest import mock  # noqa: E402

sys = _sys
SK = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SK / "engine" / "reel"))

from lib import common  # noqa: E402
from lib import srt as srtlib  # noqa: E402
from lib.common import Paths, write_json  # noqa: E402
import test_pipeline as tp  # noqa: E402  (module import: its TestCases are not collected again here)
from test_t41_plan import decisions  # noqa: E402


class TestBuildSendsTheKeys(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp())
        cls.root, cls.p, _ = tp.make_project(cls.tmp)
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
        prj = self.p.p("07_premiere/project")
        if prj.exists():
            shutil.rmtree(prj)

    def compile(self, style=None, ed=None):
        from lib.plan import compile_plan
        if style is not None:
            self.style_f.parent.mkdir(parents=True, exist_ok=True)
            write_json(self.style_f, style)
        write_json(self.p.p("01_analysis/edit-decisions.json"), ed or decisions())
        with common.use_context(common.Context(root=self.root)):
            r = compile_plan(self.p)
        self.assertTrue(r["ok"], r["errors"])
        return json.loads(self.p.p("01_analysis/timeline-spec.json").read_text(encoding="utf-8"))

    def build(self):
        from lib import ppro_build
        sent = []
        prj = self.p.p(f"07_premiere/project/CLIP1_{common.project_prefix()}_EDIT.prproj")

        def submit(action, d=None, timeout=0, **k):
            sent.append((action, d))
            prj.parent.mkdir(parents=True, exist_ok=True)
            with gzip.open(prj, "wb") as f:
                f.write(b"<Project><Sequence>BUILT</Sequence></Project>")
            return {"ok": True, "claimed": True, "response": {"ok": True, "result": {}}}

        with common.use_context(common.Context(root=self.root)), \
                mock.patch("lib.ppro_bridge.status", return_value={"alive": True}), \
                mock.patch("lib.ppro_bridge.submit", side_effect=submit):
            r = ppro_build.build(self.p, overwrite=True)
        jobs = [d for a, d in sent if a == "build_project"]
        self.assertEqual(len(jobs), 1, r)
        return jobs[0], r

    def test_i5_an_eased_plan_sends_its_keys(self):
        spec = self.compile({"fades": {"video_in_ms": 300, "audio_out_ms": 500}})
        job, r = self.build()
        self.assertEqual(len(spec["camera_ease"]["runs"]), 1)
        self.assertEqual(job["camera_keys"], spec["camera_ease"]["runs"])
        self.assertAlmostEqual(job["fades"]["video_in_s"], 0.3)
        self.assertAlmostEqual(job["fades"]["audio_out_s"], 0.5)
        self.assertAlmostEqual(job["fades"]["end_s"], spec["duration_frames"] / spec["fps"])
        self.assertIn("punch_ins_eased", r["checks"])
        self.assertFalse(r["checks"]["punch_ins_eased"])         # the mocked Premiere read nothing back

    def test_c2_a_4_5_window_reel_sends_no_camera_keys(self):
        spec = self.compile({"framing": "4:5"})
        self.assertTrue(any(m.get("window") and m.get("decision_id") == "EDIT_001" for m in spec["main_segments"]),
                        spec["main_segments"])
        self.assertEqual(spec["camera_ease"]["runs"], [])
        job, r = self.build()
        self.assertNotIn("camera_keys", job)                       # nothing eased: nothing sent (review 2 M-f)
        self.assertNotIn("punch_ins_eased", r["checks"])

    def hidden_with(self, style_block):
        """The hidden caption ranges job_data hands the animated captions, for a spec with a hook title 0.2-2.0 s."""
        from lib.ppro_build import job_data
        from lib.stamps import stamp
        spec = self.compile()
        spec["events"] = [{"event_id": "GFX_H", "decision_id": "EDIT_001", "template": "hook_title", "track": "V04",
                           "start_frame": 5, "end_frame": 48, "start_ms": 200, "end_ms": 2000, "params": {"text": "x"},
                           "approval_required": False}]
        if style_block is not None:
            spec["style"] = style_block
        write_json(self.p.p("01_analysis/timeline-spec.json"), stamp(spec))
        seen = {}

        def caps(paths, hidden, **kw):
            seen["hidden"] = list(hidden)
            return []
        with common.use_context(common.Context(root=self.root)), \
                mock.patch("lib.previews.render_captions", side_effect=caps):
            job_data(self.p)
        return seen["hidden"]

    def test_captions_under_the_hook_follow_the_spec(self):
        self.assertIn((200, 2000), self.hidden_with(None))                               # the safe default: hidden
        self.assertNotIn((200, 2000), self.hidden_with({"captions_during_hook": "show"}))
        self.assertIn((200, 2000), self.hidden_with({"captions_during_hook": "hide"}))


    # ---- round 3, item 2: an approved plan written before T4.1 is not touched by the update
    B61_JOB_KEYS = {"project_path", "overwrite_existing", "xml_path", "sequence_name", "settings", "graphics", "srt_path",
                    "native_caption_track", "markers", "track_names", "_missing", "blur_v1_clips", "sharpen_v1",
                    "_lanes", "_warnings", "_stills_redrawn", "duration_s"}       # ppro_build.job_data at b61f808

    def test_r3_an_approved_pre_t41_plan_builds_as_before(self):
        from lib.plan import APPROVAL_FORMAT, approval_state, plan_fingerprint
        from lib.ppro_build import approval_refusal
        from lib.stamps import stamp
        spec = self.compile()
        frozen = {k: v for k, v in spec.items() if k != "camera_ease"}         # the plan as a pre-T4.1 engine wrote it
        write_json(self.p.p("01_analysis/timeline-spec.json"), stamp(frozen))
        with common.use_context(common.Context(root=self.root)):
            write_json(self.p.p("01_analysis/plan-approval.json"),
                       {"approved": True, "by": "editor", "format": APPROVAL_FORMAT, "plan_fingerprint": plan_fingerprint(self.p)})
            self.assertEqual(approval_state(self.p)["state"], "current")
            self.assertIsNone(approval_refusal(self.p))
        cli = tp.subprocess.run([sys.executable, "-B", str(SK / "engine/reel/cli.py"), "--root", str(self.root),
                                 "--video-id", "CLIP1", "ppro-build"], capture_output=True, text=True)
        self.assertNotIn("not approved", cli.stdout + cli.stderr)
        job, r = self.build()
        # the job of b61f808 exactly (the private "_" keys never reach the bridge); hard punches, no new check
        self.assertEqual(set(job), {k for k in self.B61_JOB_KEYS if not k.startswith("_")})
        self.assertNotIn("punch_ins_eased", r["checks"])
        self.assertNotIn("fades_applied", r["checks"])
        self.assertNotIn("qc_frames", r)

    # ---- round 3, item 3: the hook SFX at frame 0 is never faded
    def test_r3_sfx_tracks_are_left_out_of_the_sound_fade(self):
        from lib import sfx
        ed = decisions()
        ed["decisions"][0]["sound"] = [{"type": "pop", "at": "00:00:00.000"}]
        spec = self.compile({"fades": {"audio_in_ms": 1000, "video_in_ms": 500}}, ed=ed)
        cues = json.loads(self.p.p("06_audio/audio-cue-sheet.json").read_text(encoding="utf-8"))["cues"]
        self.assertTrue(any(c["start_frame"] == 0 for c in cues), cues)
        sfx.synth_needed({c["kind"] for c in cues}, self.p.p("06_audio/sfx"))
        job, _ = self.build()
        names = job["track_names"]["audio"]
        sfx_idx = {i + 1 for i, n in enumerate(names) if "Sound Effects" in n}
        self.assertTrue(sfx_idx, names)
        self.assertTrue(job["fades"]["audio_tracks"])
        self.assertFalse(set(job["fades"]["audio_tracks"]) & sfx_idx, (job["fades"], names))
        self.assertTrue({1, 2} <= set(job["fades"]["audio_tracks"]))          # the dialogue fades

    # ---- round 3, item 4: the mid-ease frames, written for QC and exported by ppro-frames
    def test_r3_the_build_result_names_the_mid_ease_frames(self):
        from lib.ppro_build import ease_qc_frames
        spec = self.compile()
        job, r = self.build()
        q = r["qc_frames"]
        self.assertEqual(q, ease_qc_frames(spec))
        self.assertEqual([x["why"] for x in q], ["mid ease-in", "mid ease-out"])
        self.assertEqual(q[0]["frame"], 24 + 3)
        self.assertAlmostEqual(q[0]["t_s"], 27.5 / 24, places=3)                # the frame's centre
        self.assertIn(f"{q[0]['t_s']:.3f}", r["qc_frames_note"])
        rec = json.loads(self.p.p("07_premiere/ppro-build-result.json").read_text(encoding="utf-8"))
        self.assertEqual(rec["qc_frames"], q)

    # ---- review 2 IMP-2: one black matte over the whole picture, on its own top track
    def test_imp2_the_picture_fade_is_a_matte_on_a_top_track(self):
        from PIL import Image
        self.compile({"fades": {"video_in_ms": 300, "video_out_ms": 500}})
        job, _ = self.build()
        m = job["fades"]["matte"]
        self.assertTrue(Path(m["png"]).is_file())
        im = Image.open(m["png"])
        self.assertEqual(im.size, (1080, 1920))
        self.assertEqual(im.convert("RGB").getextrema(), ((0, 0), (0, 0), (0, 0)))
        self.assertEqual(m["track_index"], len(job["track_names"]["video"]) - 1)        # the topmost track
        self.assertIn("Fade to black", job["track_names"]["video"][-1])
        self.assertFalse(any(g["track_index"] == m["track_index"] for g in job["graphics"]))

    def test_imp2_no_picture_fade_no_matte_track(self):
        self.compile({"fades": {"audio_out_ms": 500}})
        job, _ = self.build()
        self.assertNotIn("matte", job["fades"])
        self.assertFalse(any("Fade to black" in n for n in job["track_names"]["video"]))

    # ---- round 4 M-2: a picture fade + the native caption track sends the trimmed SRT copy
    def test_r4_m2_job_srt_path_with_and_without_a_picture_fade(self):
        ed = decisions()
        ed["global"]["native_caption_track"] = True
        seq_srt = self.p.p("02_transcription/subtitles-seq.srt")
        keep = seq_srt.read_bytes() if seq_srt.exists() else None
        if keep is None:
            self.addCleanup(lambda: seq_srt.unlink(missing_ok=True))
        else:
            self.addCleanup(seq_srt.write_bytes, keep)
        self.compile({"fades": {"video_in_ms": 1000}}, ed=ed)
        srtlib.write_srt(seq_srt, [{"start_ms": 0, "end_ms": 1500, "text": "اول"},
                                   {"start_ms": 3000, "end_ms": 4000, "text": "وسط"}])
        job, r = self.build()
        self.assertEqual(Path(job["srt_path"]), self.p.p("07_premiere/media/captions-faded.srt"))
        self.assertTrue(any("caption" in w for w in r.get("warnings", [])), r.get("warnings"))
        self.compile({"fades": {"audio_in_ms": 1000}}, ed=ed)
        srtlib.write_srt(seq_srt, [{"start_ms": 0, "end_ms": 1500, "text": "اول"}])
        job, _ = self.build()
        self.assertEqual(Path(job["srt_path"]), seq_srt)

    # ---- review 2 M-e: the XML fallback says the smooth zoom and fades are not in it
    def test_me_the_xml_fallback_warns(self):
        self.compile({"fades": {"video_in_ms": 300}})
        cli = tp.subprocess.run([sys.executable, "-B", str(SK / "engine/reel/cli.py"), "--root", str(self.root),
                                 "--video-id", "CLIP1", "premiere"], capture_output=True, text=True)
        self.assertIn("smooth zoom and fades are not in the XML", cli.stdout, cli.stdout + cli.stderr)
        self.assertNotIn("ppro-build", cli.stdout)                       # round 4 M-1: plain words, no command
        out = json.loads(cli.stdout)
        self.assertTrue(any("\u0621" <= ch <= "\u064a" for w in out.get("warnings", []) for ch in w), out)

    def test_r3_ppro_frames_exports_the_mid_ease_frames(self):
        import contextlib
        from lib import ppro_build
        from lib.ppro_build import ease_qc_frames
        spec = self.compile()
        asked = []

        def submit(action, d=None, timeout=0, **k):
            asked.append((action, d))
            return {"ok": True, "response": {"ok": True, "result": {"frames": []}}}
        with common.use_context(common.Context(root=self.root)),                 mock.patch("lib.ppro_bridge.submit", side_effect=submit),                 mock.patch("lib.ppro_bridge.build_lock", return_value=contextlib.nullcontext()):
            ppro_build.export_frames(self.p, retries=0, media_wait_s=0)
        times = next(d["times"] for a, d in asked if a == "export_frames")
        for q in ease_qc_frames(spec):
            self.assertIn(q["t_s"], times)


class TestNativeCaptions(unittest.TestCase):
    """ppro_build.premiere_captions: the native caption track's SRT."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)
        root = self.tmp / "عميل"
        (root / "assets").mkdir(parents=True)
        (root / "data").mkdir()
        self.root = root
        self.p = Paths(root, "V1")
        self.p.ensure_project()
        srtlib.write_srt(self.p.p("02_transcription/captions-short.srt"), [
            {"start_ms": 200, "end_ms": 1500, "text": "اول"}, {"start_ms": 300, "end_ms": 900, "text": "قصير"},
            {"start_ms": 4000, "end_ms": 5000, "text": "وسط"}, {"start_ms": 8500, "end_ms": 9800, "text": "آخر"}])

    def spec(self, **kw):
        return dict({"fps": 24, "duration_ms": 10000, "duration_frames": 240, "events": [], "main_segments": []}, **kw)

    def cues(self, spec):
        from lib.ppro_build import premiere_captions
        with common.use_context(common.Context(root=self.root)):
            return [(c["start_ms"], c["end_ms"], c["text"]) for c in srtlib.read_srt(premiere_captions(self.p, spec, {}))]

    def hook(self):
        return [{"event_id": "H", "template": "hook_title", "start_ms": 100, "end_ms": 2000, "start_frame": 2,
                 "end_frame": 48, "params": {}}]

    def test_hook_hides_captions_by_default(self):
        self.assertEqual([c[2] for c in self.cues(self.spec(events=self.hook()))], ["وسط", "آخر"])

    def test_hook_show_keeps_them(self):
        got = self.cues(self.spec(events=self.hook(), style={"captions_during_hook": "show"}))
        self.assertEqual([c[2] for c in got], ["اول", "قصير", "وسط", "آخر"])

    def faded(self, fades):
        from lib.ppro_build import fade_caption_srt
        warns = []
        spec = self.spec(fades=dict({"video_in_ms": 0, "video_out_ms": 0, "audio_in_ms": 0, "audio_out_ms": 0}, **fades))
        with common.use_context(common.Context(root=self.root)):
            out = fade_caption_srt(self.p, spec, self.p.p("02_transcription/captions-short.srt"), warns)
        return [(c["start_ms"], c["end_ms"], c["text"]) for c in srtlib.read_srt(out)], warns, out

    def test_imp3_native_captions_leave_only_the_dark_half_of_a_fade(self):
        """Review 2 IMP-3: native captions sit above every video track (the matte cannot cover them): they are
        trimmed only where the fade is past half way to black, with an editor line saying how many (EN and AR)."""
        srtlib.write_srt(self.p.p("02_transcription/captions-short.srt"), [
            {"start_ms": 200, "end_ms": 1500, "text": "اول"}, {"start_ms": 300, "end_ms": 400, "text": "قصير"},
            {"start_ms": 4000, "end_ms": 5000, "text": "وسط"}, {"start_ms": 8500, "end_ms": 10000, "text": "CTA"}])
        got, warns, out = self.faded({"video_in_ms": 1000, "video_out_ms": 1000})
        self.assertEqual(got, [(500, 1500, "اول"), (4000, 5000, "وسط"), (8500, 9500, "CTA")])
        self.assertEqual(len(warns), 2, warns)
        self.assertIn("3", warns[0])
        self.assertTrue(any("ء" <= ch <= "ي" for ch in warns[1]))           # Arabic letters
        self.assertIn("07_premiere", str(out))                         # a copy: the transcript files stay as they are

    def test_imp3_a_final_cta_keeps_until_the_half_point(self):
        srtlib.write_srt(self.p.p("02_transcription/captions-short.srt"), [
            {"start_ms": 8000, "end_ms": 10000, "text": "تابعنا"}])
        got, warns, _ = self.faded({"video_out_ms": 1000})
        self.assertEqual(got, [(8000, 9500, "تابعنا")])
        self.assertIn("1", warns[0])

    def test_imp3_no_picture_fade_changes_nothing(self):
        got, warns, out = self.faded({"audio_in_ms": 1000, "audio_out_ms": 1000})
        self.assertEqual(len(got), 4)
        self.assertEqual(warns, [])
        self.assertEqual(out, self.p.p("02_transcription/captions-short.srt"))


if __name__ == "__main__":
    unittest.main()
