"""T2.8 (3.0, IM-16): the frame size comes from the client's sequence-settings.json everywhere (stills, preview video,
verify sheet, handoff, the Premiere settings and the read-back check), never from a hard-coded 1080x1920.

Run one file: <engine runtime python> -s -B -m unittest discover -s whynot-cut/tests -p test_frame_size.py
"""
import sys as _sys
_sys.dont_write_bytecode = True
import _isolation  # noqa: F401,E402  G79: sandbox the engine home first (tests/_isolation.py)
import contextlib
import io
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SK = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SK / "engine" / "reel"))
sys.path.insert(0, str(SK / "tests"))

from lib import common  # noqa: E402
from lib.common import Context, Paths, read_json, write_json  # noqa: E402

SIZES = [(1080, 1350), (1920, 1080)]          # a 4:5 feed profile and a 16:9 landscape profile


def size_of(path) -> tuple:
    from PIL import Image
    with Image.open(path) as im:
        return im.size


def profile_with(root: Path, w, h) -> None:
    write_json(root / common.CLIENT_PROFILE_REL / "sequence-settings.json", {"general": {"frame_width": w, "frame_height": h}})


class TestFrameSizeHelper(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.root = self.tmp / "C"
        (self.root / "assets").mkdir(parents=True)
        (self.root / "data").mkdir()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_the_shipped_default_is_1080x1920(self):
        self.assertEqual(common.frame_size(ctx=Context(self.root)), (1080, 1920))

    def test_a_profile_sets_the_size(self):
        for w, h in SIZES:
            profile_with(self.root, w, h)
            self.assertEqual(common.frame_size(ctx=Context(self.root)), (w, h))

    def test_paths_name_the_client_even_when_another_context_is_current(self):
        profile_with(self.root, 1080, 1350)
        other = self.tmp / "OTHER"
        (other / "assets").mkdir(parents=True)
        (other / "data").mkdir()
        profile_with(other, 1920, 1080)
        with common.use_context(Context(other)):
            self.assertEqual(common.frame_size(Paths(self.root, "V1")), (1080, 1350))
            self.assertEqual(common.frame_size(), (1920, 1080))            # no paths: the current context

    def test_a_size_missing_from_the_settings_falls_back_to_the_default(self):
        class Bare:
            def config(self, name):
                return {"general": {}}
        self.assertEqual(common.frame_size(ctx=Bare()), common.DEFAULT_FRAME_SIZE)
        self.assertEqual(common.DEFAULT_FRAME_SIZE, (1080, 1920))

    def test_a_size_given_as_whole_numbers_in_text_is_accepted(self):
        profile_with(self.root, "1080", 1350.0)
        self.assertEqual(common.frame_size(ctx=Context(self.root)), (1080, 1350))

    def test_an_invalid_size_is_a_clear_error_naming_the_file_and_key(self):
        from lib.errors import Guidance
        for bad in ("wide", 0, -1080, 1080.5, True, None, [1080], 100000):
            with self.subTest(frame_height=bad):
                profile_with(self.root, 1080, bad)
                with self.assertRaises(Guidance) as cm:
                    common.frame_size(ctx=Context(self.root))
                self.assertIn("sequence-settings.json", cm.exception.error)
                self.assertIn("frame_height", cm.exception.error)
                self.assertTrue(cm.exception.how)


def _stub_edit(p: Paths, hook_text="هل في حاجات معينة") -> None:
    for f in ("main-topic.md", "medical-content-review.md"):
        (p.p("01_analysis") / f).write_text("# stub\n", encoding="utf-8")
    for f in ("narrative-segments.json", "transcript-semantic-analysis.json", "editing-style.json"):
        write_json(p.p("01_analysis") / f, {"stub": True})
    write_json(p.p("01_analysis/edit-decisions.json"), {
        "video_id": "CLIP1", "global": {"main_footage": "data/Raw/CLIP1.mov"},
        "caption_highlights": [{"text": "التشخيص الصحيح", "at": "00:00:08.600"}],
        "decisions": [{"decision_id": "EDIT_001", "segment_id": "SEG_001", "evidence": "هل في حاجات معينة",
                       "start": "00:00:00.200", "end": "00:00:04.000", "semantic_intent": "hook",
                       "visual_treatment": "hook", "confidence": "high",
                       "graphics": [{"id": "GFX_001", "template": "hook_title", "start": "00:00:00.200",
                                     "end": "00:00:03.500", "text": hook_text}]}]})


def ready_response(data: dict, prproj: Path, size=None) -> dict:
    """What Premiere answers to build_project when everything worked: the sequence has the size the profile says."""
    w, h = size or (data["settings"]["previewFrameWidth"], data["settings"]["previewFrameHeight"])
    n = len(data["graphics"])
    prproj.parent.mkdir(parents=True, exist_ok=True)
    prproj.write_text("built", encoding="utf-8")
    res = {"settings_after": {"previewCodec": "apcs", "videoFrameWidth": w, "videoFrameHeight": h,
                              "videoFrameRate": {"seconds": 1 / 24}, "compositeLinearColor": True,
                              "maximumBitDepth": False, "maximumRenderQuality": False},
           "placed": [{"id": g["id"], "ok": True} for g in data["graphics"]][:n],
           "sharpened": [{"ok": True}] if data.get("sharpen_v1") else [], "captionTrack": True,
           "tracks": {"audio": [{"clips": 1}, {"clips": 1}], "video": []}}
    return {"ok": True, "response": {"ok": True, "result": res}}


class TestFrameSizeEverywhere(unittest.TestCase):
    """One synthetic reel per profile size, planned, previewed, verified and built (mocked bridge) end to end."""

    @classmethod
    def setUpClass(cls):
        import test_pipeline as T
        from lib.client_db import build as build_db
        from lib.discover import run_discovery
        from lib.media import preflight
        from lib.plan import compile_plan
        from lib.previews import render_all
        cls.tmp = Path(tempfile.mkdtemp())
        cls.proj = {}
        for w, h in SIZES:
            root, p, _words = T.make_project(cls.tmp / f"{w}x{h}")
            profile_with(root, w, h)
            with common.use_context(Context(root, home=cls.tmp / "home")):
                build_db(p, run_discovery(p)["inventory"])
                preflight(p, [root / "data/Raw/CLIP1.mov"])
                _stub_edit(p)
                plan = compile_plan(p)
                assert plan["ok"], plan.get("errors")
                render_all(p, composite_preview=True)
            cls.proj[(w, h)] = (root, p)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def ctx(self, w, h):
        root, p = self.proj[(w, h)]
        return common.use_context(Context(root, home=self.tmp / "home")), p

    def test_stills_are_the_profile_size(self):
        from PIL import Image
        for w, h in SIZES:
            with self.subTest(size=f"{w}x{h}"):
                c, p = self.ctx(w, h)
                with c:
                    d = p.p("03_broll/educational-graphics")
                    pngs = sorted(d.glob("GFX_001*.png")) or sorted(p.p("03_broll").rglob("GFX_001*.png"))
                    self.assertTrue(pngs, "no stills rendered")
                    for png in pngs:
                        self.assertEqual(size_of(png), (w, h), png.name)
                    comp = next(p.p("08_quality_control/previews").glob("GFX_001_*.jpg"))
                    self.assertEqual(size_of(comp), (540, round(540 * h / w)))

    def test_caption_stills_are_the_profile_size(self):
        from PIL import Image
        from lib.ppro_build import job_data
        for w, h in SIZES:
            with self.subTest(size=f"{w}x{h}"):
                c, p = self.ctx(w, h)
                with c:
                    job_data(p)
                    caps = sorted(p.p("03_broll/captions").glob("CAP_*_fg.png"))
                    self.assertTrue(caps, "no caption stills")
                    self.assertEqual(size_of(caps[0]), (w, h))

    def test_premiere_settings_carry_the_profile_size(self):
        from lib import ppro_build
        from lib.ppro_build import job_data
        for w, h in SIZES:
            with self.subTest(size=f"{w}x{h}"):
                c, p = self.ctx(w, h)
                with c:
                    s = job_data(p)["settings"]
                    self.assertEqual((s["previewFrameWidth"], s["previewFrameHeight"]), (w, h))
                    self.assertEqual(s["previewCodec"], "apcs")
        self.assertNotIn("previewFrameWidth", ppro_build.SETTINGS)            # no frame size baked into the constant

    def test_the_mocked_build_reads_the_size_back_without_issues(self):
        from lib import ppro_build
        for w, h in SIZES:
            with self.subTest(size=f"{w}x{h}"):
                c, p = self.ctx(w, h)
                with c:
                    prproj = p.p(f"07_premiere/project/{p.video_id}_{common.project_prefix()}_EDIT.prproj")
                    prproj.unlink(missing_ok=True)
                    sent = []

                    def submit(action, data=None, timeout=0, **kw):
                        sent.append((action, data))
                        return ready_response(data, prproj)
                    with mock.patch("lib.ppro_bridge.status", return_value={"alive": True}), \
                            mock.patch("lib.ppro_bridge.submit", side_effect=submit):
                        r = ppro_build.build(p)
                self.assertEqual(r["status"], "PRPROJ_BUILT", r["checks"])
                self.assertIn(f"frame_{w}x{h}", r["checks"])
                self.assertTrue(r["checks"][f"frame_{w}x{h}"])
                self.assertEqual([k for k in r["checks"] if k.startswith("frame_")], [f"frame_{w}x{h}"])
                self.assertEqual((sent[0][1]["settings"]["previewFrameWidth"], sent[0][1]["settings"]["previewFrameHeight"]), (w, h))

    def test_a_sequence_of_the_wrong_size_is_flagged_by_the_size_check(self):
        from lib import ppro_build
        c, p = self.ctx(1080, 1350)
        with c:
            prproj = p.p(f"07_premiere/project/{p.video_id}_{common.project_prefix()}_EDIT.prproj")
            prproj.unlink(missing_ok=True)

            def submit(action, data=None, timeout=0, **kw):
                return ready_response(data, prproj, size=(1080, 1920))        # Premiere kept its default size
            with mock.patch("lib.ppro_bridge.status", return_value={"alive": True}), \
                    mock.patch("lib.ppro_bridge.submit", side_effect=submit):
                r = ppro_build.build(p)
        self.assertEqual(r["status"], "PRPROJ_BUILT_WITH_ISSUES")
        self.assertFalse(r["checks"]["frame_1080x1350"])

    def test_preview_video_has_the_profile_aspect(self):
        from lib.media import probe
        from lib.preview_video import render
        want = {(1080, 1350): (270, 338), (1920, 1080): (270, 152)}
        for w, h in SIZES:
            with self.subTest(size=f"{w}x{h}"):
                c, p = self.ctx(w, h)
                with c:
                    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                        r = render(p, width=270, label=False)           # logs its path; keep the run output clean
                    self.assertTrue(r["ok"], r)
                    self.assertEqual(r["size"], "%dx%d" % want[(w, h)])
                    pr = probe(Path(r["video"]))
                    self.assertEqual((pr["video"]["display_width"], pr["video"]["display_height"]), want[(w, h)])

    def test_verify_sheet_scales_to_the_profile_size(self):
        from PIL import Image
        from lib import verify
        for w, h in SIZES:
            with self.subTest(size=f"{w}x{h}"):
                c, p = self.ctx(w, h)
                with c:
                    mov = p.p("04_after_effects/compositions/GFX_001.mov")
                    mov.parent.mkdir(parents=True, exist_ok=True)
                    mov.write_bytes(b"x")
                    cmds = []
                    with mock.patch.object(verify, "run", side_effect=lambda cmd, **kw: cmds.append(cmd)):
                        verify.build(p)
                    mov.unlink()
                    flt = [c_[c_.index("-filter_complex") + 1] for c_ in cmds if "-filter_complex" in c_]
                    self.assertTrue(flt, cmds)
                    th = round(360 * h / w)
                    self.assertIn(f"scale={w}:{h}[b]", flt[0])
                    self.assertIn(f"scale=360:{th}", flt[0])
                    if (w, h) != (1080, 1920):
                        self.assertNotIn("1080:1920", flt[0])
                    verify.build(p)                                              # the preview-only branch: a still tile
                    tile = p.p("08_quality_control/verify/GFX_001.jpg")
                    self.assertEqual(size_of(tile), (360, th))

    def test_the_safe_area_follows_the_frame(self):
        from lib import verify
        self.assertEqual(verify.safe_area(1080, 1920), {"x0": 60, "x1": 1020, "y0": 150, "y1": 1720})   # unchanged for 9:16
        self.assertEqual(verify.safe_area(1920, 1080), {"x0": 60, "x1": 1860, "y0": 150, "y1": 880})
        self.assertEqual(verify.safe_area(1080, 1350), {"x0": 60, "x1": 1020, "y0": 150, "y1": 1150})

    def test_the_export_name_carries_the_aspect(self):
        from lib.handoff import aspect_label
        self.assertEqual([aspect_label(w, h) for w, h in [(1080, 1920), (1080, 1350), (1920, 1080), (1080, 1080), (1000, 1500)]],
                         ["9x16", "4x5", "16x9", "1x1", "2x3"])
        self.assertEqual(aspect_label(1234, 4321), "1234x4321")

    def test_the_handoff_names_the_profile_size(self):
        from lib.handoff import build as handoff
        for w, h in SIZES:
            with self.subTest(size=f"{w}x{h}"):
                c, p = self.ctx(w, h)
                with c:
                    handoff(p)                                    # after the (mocked) native build: names the export size
                    native = p.p("09_handoff/README.md").read_text(encoding="utf-8")
                    p.p("07_premiere/ppro-build-result.json").unlink(missing_ok=True)
                    handoff(p)                                    # the XML fallback lists the sequence settings to check
                    xml = p.p("09_handoff/README.md").read_text(encoding="utf-8")
                self.assertIn(f"{w}x{h} at", native)
                self.assertIn(f"Preview **{w} × {h}**", xml)
                self.assertIn(f"{w}×{h}, 24.00 fps", xml)
                if (w, h) != (1080, 1920):
                    for text in (native, xml):
                        self.assertNotIn("1080x1920", text)
                        self.assertNotIn("1080 × 1920", text)
                        self.assertNotIn("1080×1920", text)
                        self.assertNotIn("9x16", text)

    def test_grab_frame_asks_for_the_profile_size(self):
        from lib import previews
        for w, h in SIZES:
            with self.subTest(size=f"{w}x{h}"):
                c, p = self.ctx(w, h)
                with c, mock.patch("lib.media_util.grab_frame", return_value=None) as g:
                    previews.grab_frame(Path("x.mp4"), 1000)
                self.assertEqual(g.call_args.args[2:4], (w, h))


class TestFramingWindowFollowsTheSequence(unittest.TestCase):
    """T2.8 review: the framing window is placed inside the sequence's own frame, not a 1080x1920 one."""

    def window(self, sw, sh, framing="4:5"):
        from types import SimpleNamespace
        from lib.plan import apply_framing
        inp = SimpleNamespace(ctx=Context(Path(tempfile.gettempdir())), base={"framing": framing}, style={}, pre_all={},
                              main_file=None, main_v={"display_width": 1080, "display_height": 1920}, dur_ms=2000,
                              fps=25.0, seq_cfg={"general": {"frame_width": sw, "frame_height": sh}})
        cam = {"camera": [], "main_v": inp.main_v, "bsp": 100.0, "box": 0.0, "framing": ""}
        out, errors, _warnings = apply_framing(inp, cam)
        self.assertEqual(errors, [])
        return out["merged"][0]["window"]

    def test_a_4x5_window_in_a_1080x1350_sequence_fills_it(self):
        self.assertEqual(self.window(1080, 1350), {"w": 1080, "h": 1350, "y": 0, "mode": "4:5"})

    def test_a_4x5_window_in_the_default_sequence_is_centred(self):
        self.assertEqual(self.window(1080, 1920), {"w": 1080, "h": 1350, "y": 285, "mode": "4:5"})


if __name__ == "__main__":
    unittest.main()
