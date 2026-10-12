"""3.0 T2.17 — long-lived-process readiness (engine MI-6, MI-7, MI-8, MI-9; required by `reel serve`, T6.2):
  * no location is computed at import: an engine home changed after import is honoured;
  * an explicit Context per request (client root, profile layers, engine home, request caches);
  * caches of installed fonts follow the font folders;
  * compile_plan is a chain of pure steps;
  * lib/media_util.py: one frame grab, one contact-sheet builder (G73), one time parser.
Run: bash tools/test.sh -k test_long_lived
"""
import sys as _sys
_sys.dont_write_bytecode = True  # keep the plugin folder free of __pycache__
import _isolation  # noqa: F401,E402  G79: sandbox the engine home first (tests/_isolation.py)
import json
import os
import shutil
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

SK = Path(__file__).resolve().parents[1]
sys = _sys
sys.path.insert(0, str(SK / "engine" / "reel"))

from lib import common  # noqa: E402


class TempDir(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="t217_"))
        self.addCleanup(shutil.rmtree, self.tmp, True)


class TestEngineHomeAfterImport(TempDir):
    """MI-8: ENV_DIR / QUEUE / SCRIPTS / EXT_DIR were computed at import, so a home set later was ignored."""

    def test_env_change_after_import_is_honoured(self):
        from lib import ae_bridge, ae_probe, motion_library, ppro_bridge
        for name in ("one", "two"):                      # the second change must be seen too (nothing cached)
            home = self.tmp / name
            with mock.patch.dict(os.environ, {"WHYNOT_HOME": str(home)}):
                self.assertEqual(common.engine_home(), home)
                self.assertEqual(common.models_dir(), home / "models")
                self.assertEqual(common.current_context().engine_home, home)
                self.assertEqual(ppro_bridge.queue_dir(), home / "ppro-queue")
                self.assertEqual(ppro_bridge.scripts_dir(), home / "ppro-scripts")
                self.assertEqual(ppro_bridge.lib_path(), home / "ppro-scripts" / "nh_ppro_lib.jsx")
                self.assertEqual(ae_bridge.queue_dir(), home / "ae-queue")
                self.assertEqual(ae_bridge.entry_path(), home / "ae-scripts" / ae_bridge.ENTRY_NAME)
                self.assertEqual(ae_probe.caps_file(), home / "ae-capabilities.json")
                if not motion_library.motion_cfg().get("library_dir"):
                    self.assertEqual(motion_library.library_dir(), home / "library" / "motion")
                # one-release back-compat attributes resolve live as well
                self.assertEqual(common.ENV_DIR, home)
                self.assertEqual(ppro_bridge.QUEUE, home / "ppro-queue")
                self.assertEqual(ae_bridge.SCRIPTS, home / "ae-scripts")

    def test_bridge_sync_goes_to_the_current_home(self):
        from lib import ae_bridge, ppro_bridge
        with mock.patch.dict(os.environ, {"WHYNOT_HOME": str(self.tmp / "h")}):
            r = ppro_bridge.sync_scripts()
            self.assertEqual(r["scripts_dir"], str(self.tmp / "h" / "ppro-scripts"))
            self.assertTrue((self.tmp / "h" / "ppro-scripts" / "nh_ppro_lib.jsx").is_file())
            self.assertEqual(ae_bridge.sync_scripts()["scripts_dir"], str(self.tmp / "h" / "ae-scripts"))

    def test_no_module_level_home_constants(self):
        """Guard: no engine module computes an engine-home path at import again."""
        import re
        bad = []
        for f in sorted((SK / "engine/reel").rglob("*.py")):
            for n, line in enumerate(f.read_text(encoding="utf-8").splitlines(), 1):
                if re.match(r"^[A-Z_][A-Z0-9_]*\s*(:[^=]+)?=.*((?<![\w\x22])ENV_DIR|engine_home\(\)|cep_extensions_dir\(\)|font_dirs\(\))",
                            line):
                    bad.append(f"{f.name}:{n}: {line.strip()}")
        self.assertEqual(bad, [])


def _client(root: Path, timebase: int, prefix: str = "AA") -> Path:
    prof = root / common.CLIENT_PROFILE_REL
    prof.mkdir(parents=True, exist_ok=True)
    common.write_json(prof / "sequence-settings.json", {"general": {"timebase": timebase, "ntsc": False}})
    common.write_json(prof / "profile.json", {"prefix": prefix})
    (root / "assets").mkdir(exist_ok=True)
    (root / "data").mkdir(exist_ok=True)
    return root


class TestContext(TempDir):
    def setUp(self):
        super().setUp()
        self.addCleanup(common.set_context, None)

    def test_set_context_returns_the_process_context(self):
        a = _client(self.tmp / "A", 25, "AA")
        ctx = common.set_context(a)
        self.assertIs(common.current_context(), ctx)
        self.assertEqual(ctx.root, a.resolve())
        self.assertEqual(common.seq_rate(), (25, False))
        self.assertEqual(common.project_prefix(), "AA")
        self.assertEqual(common.load_config("profile.json", ctx)["prefix"], "AA")

    def test_a_new_request_sees_an_edited_profile(self):
        """A daemon builds a Context per request: the sequence rate cached for one request is not served to the next."""
        a = _client(self.tmp / "A", 25)
        with common.use_context(common.Context(a)):
            self.assertEqual(common.seq_fps(), 25.0)
            common.write_json(a / common.CLIENT_PROFILE_REL / "sequence-settings.json",
                              {"general": {"timebase": 30, "ntsc": True}})
            self.assertEqual(common.seq_fps(), 25.0)                  # same request: stable
        with common.use_context(common.Context(a)):
            self.assertAlmostEqual(common.seq_fps(), 30000 / 1001)    # next request: the edit is seen

    def test_use_context_is_scoped_and_per_thread(self):
        a, b = _client(self.tmp / "A", 25, "AA"), _client(self.tmp / "B", 50, "BB")
        common.set_context(a)
        seen = {}

        def worker(root, key):
            with common.use_context(common.Context(root)):
                seen[key] = (common.seq_rate()[0], common.project_prefix())

        with common.use_context(common.Context(b)):
            self.assertEqual(common.project_prefix(), "BB")
            t = threading.Thread(target=worker, args=(a, "a"))
            t.start()
            t.join()
            self.assertEqual(common.project_prefix(), "BB")           # the other thread's binding never leaks here
        self.assertEqual(seen["a"], (25, "AA"))
        self.assertEqual(common.project_prefix(), "AA")                # back to the process context

    def test_explicit_home_on_a_context(self):
        ctx = common.Context(None, home=self.tmp / "custom")
        self.assertEqual(ctx.engine_home, self.tmp / "custom")


class TestFontCachesFollowTheFolders(TempDir):
    """_INSTALLED_PS / _FONT_FILES were filled once per process: a font installed while `reel serve` runs was never
    found. They now follow plat.font_dirs_stamp."""

    def font(self) -> Path | None:
        from lib.plat import font_dirs
        for d in font_dirs():
            for name in ("arial.ttf", "Arial.ttf", "DejaVuSans.ttf"):
                for f in (d / name, *d.glob(f"**/{name}")):
                    if f.is_file():
                        return f
        return None

    def test_font_installed_later_is_found(self):
        src = self.font()
        if not src:
            self.skipTest("no system font to copy")
        from lib import client_db, motion_layout, plat
        fonts = self.tmp / "fonts"
        fonts.mkdir()
        from fontTools.ttLib import TTFont
        with TTFont(str(src), lazy=True) as tt:
            ps = str(tt["name"].getName(6, 3, 1, 0x409))
        with mock.patch.object(plat, "font_dirs", lambda: [fonts]):
            self.assertIsNone(motion_layout.find_font_file(ps))
            self.assertNotIn(ps, client_db.installed_postscript_names())
            shutil.copy(src, fonts / "late.ttf")
            st = (fonts / "late.ttf").stat()
            os.utime(fonts, ns=(st.st_atime_ns, st.st_mtime_ns + 10_000_000_000))   # some file systems are coarse
            self.assertEqual(motion_layout.find_font_file(ps), str(fonts / "late.ttf"))
            self.assertEqual(client_db.installed_postscript_names().get(ps), str(fonts / "late.ttf"))

    def test_hb_face_cache_sees_a_replaced_file(self):
        from lib import hb_text
        if not hb_text.AVAILABLE:
            self.skipTest("HarfBuzz not installed")
        src = self.font()
        if not src:
            self.skipTest("no system font to copy")
        f = self.tmp / "brand.ttf"
        shutil.copy(src, f)
        a = hb_text._face(str(f))
        self.assertIs(hb_text._face(str(f)), a)
        st = f.stat()
        os.utime(f, ns=(st.st_atime_ns, st.st_mtime_ns + 10_000_000_000))
        self.assertIsNot(hb_text._face(str(f)), a)
        self.assertLessEqual(len(hb_text._FACES), hb_text._FACES_MAX)


class TestCompilePlanSteps(TempDir):
    """MI-6: compile_plan = read_inputs -> pure steps -> write_outputs. The steps never read or write files and never
    mutate their inputs; the outputs are byte-identical to the one-function version (golden run in the T2.17 report)."""

    def setUp(self):
        super().setUp()
        from test_pipeline import make_project
        self.root, self.p, self.words = make_project(self.tmp)
        common.write_json(self.p.p("01_analysis/edit-decisions.json"), {
            "video_id": "CLIP1", "global": {"main_footage": "data/Raw/CLIP1.mov", "cut_words": [{"word_ids": [3],
                                                                                                   "reason": "filler"}]},
            "music": {"status": "NO_MUSIC_SUPPLIED", "cue_points": [{"label": "drop", "at": "00:00:06.000"}]},
            "decisions": [{"decision_id": "EDIT_001", "segment_id": "SEG_001", "evidence": "هل في حاجات معينة",
                           "start": "00:00:00.200", "end": "00:00:04.000", "semantic_intent": "hook",
                           "visual_treatment": "hook", "confidence": "high",
                           "camera": {"type": "punch_in", "at": "00:00:01.000", "until": "00:00:03.000",
                                      "scale_factor": 1.1},
                           "graphics": [{"id": "GFX_001", "template": "checklist", "start": "00:00:05.000",
                                         "end": "00:00:09.000", "title": "خطوات",
                                         "items": [{"text": "التشخيص", "at": "00:00:06.000"},
                                                   {"text": "Isotretinoin", "at": "00:00:07.500"}]}]}]})

    def files(self):
        return {str(f): f.stat().st_mtime_ns for f in self.p.project.rglob("*") if f.is_file()}

    def test_steps_are_pure_and_compose_to_compile_plan(self):
        import copy
        from lib import plan
        inp = plan.read_inputs(self.p)
        ed0, before = copy.deepcopy(inp.ed), self.files()
        vd = plan.validate_decisions(inp)
        self.assertEqual(len(vd), 3)                                   # (data, errors, warnings)
        built = plan.build_plan(inp)
        self.assertEqual(inp.ed, ed0)                                  # inputs untouched
        self.assertEqual(self.files(), before)                         # nothing read-then-written by the steps
        self.assertTrue(built["ok"], built["errors"])
        self.assertTrue(built["spec"]["time_map"]["words_cut"])        # the word cut went through apply_timemap
        self.assertEqual(set(built["seq_srts"]), {"subtitles", "captions-short"})
        items = built["spec"]["events"][0]["params"]["items"]
        self.assertTrue(all("src_frame" in it for it in items))
        self.assertFalse(any("src_frame" in it for g in ed0["decisions"][0]["graphics"] for it in g["items"]))
        res = plan.write_outputs(self.p, built)
        spec1 = common.read_json(self.p.p("01_analysis/timeline-spec.json"))
        res2 = plan.compile_plan(self.p, common.Context(self.root))
        spec2 = common.read_json(self.p.p("01_analysis/timeline-spec.json"))
        self.assertEqual(res, res2)
        spec1.pop("generated"), spec2.pop("generated")
        self.assertEqual(spec1, spec2)


def no_resource_warnings(test: unittest.TestCase, fn):
    """Run fn; fail on any ResourceWarning it causes (also those raised in __del__, which reach sys.unraisablehook)."""
    import gc
    import warnings
    caught, prev = [], sys.unraisablehook
    sys.unraisablehook = lambda u: caught.append(repr(u.exc_value))
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", ResourceWarning)
            out = fn()
            gc.collect()
    finally:
        sys.unraisablehook = prev
    test.assertEqual(caught, [])
    return out


def _video(path: Path, seconds: float = 2.0, size: str = "320x240") -> Path:
    import subprocess
    subprocess.run([common.ffmpeg_exe(), "-y", "-loglevel", "error", "-f", "lavfi", "-i",
                    f"testsrc2=s={size}:r=25:d={seconds}", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(path)],
                   check=True)
    return path


class TestParseTime(unittest.TestCase):
    """MI-7: four time parsers (cli._parse_time_ms, plan.to_ms, publish.parse_time, common.parse_ts) -> one."""

    def test_forms(self):
        from lib.media_util import parse_time
        for v, ms in [(40, 40000), (40.5, 40500), ("40", 40000), ("40.5", 40500), ("00:40", 40000),
                      ("1:02:03", 3723000), ("00:00:40.500", 40500), ("00:01:02,345", 62345), ("1:30.25", 90250),
                      ("0:00:01,5", 1500), (" 00:00:02.000 ", 2000), ("90:00", 5400000)]:
            with self.subTest(v=v):
                self.assertEqual(parse_time(v), ms)
        self.assertEqual(parse_time(1500, int_is_ms=True), 1500)
        self.assertEqual(parse_time(1.5, int_is_ms=True), 1500)          # a float is always seconds
        for bad in ("abc", "1:2:3:4", "", "1:", "-5", None, True):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                parse_time(bad)

    def test_old_names_agree(self):
        import cli
        from lib import common as c, plan, publish
        self.assertEqual(plan.to_ms(1500), 1500)                        # decisions: an int is milliseconds
        self.assertEqual(plan.to_ms("00:00:01,500"), 1500)
        self.assertEqual(plan.to_ms(2.5), 2500)
        self.assertEqual(publish.parse_time(40), 40000)                 # publishing copy: an int is seconds
        self.assertEqual(publish.parse_time("1:02:03"), 3723000)
        self.assertEqual(cli._parse_time_ms("90"), 90000)
        self.assertEqual(cli._parse_time_ms("1:30.5"), 90500)
        self.assertEqual(c.parse_ts("00:01:02,345"), 62345)
        with self.assertRaises(ValueError):
            c.parse_ts("01:02")                                         # SRT grammar stays strict


class TestContactSheet(TempDir):
    """G73: the previews sheet was half empty (3 tiles in a 6-column sheet) and its count disagreed with the stills.
    The shared builder lays out exactly the tiles it is given."""

    def tiles(self, n):
        from PIL import Image
        cols = [(200, 30, 30), (30, 200, 30), (30, 30, 200), (200, 200, 30), (30, 200, 200), (200, 30, 200),
                (120, 120, 120), (250, 250, 250)]
        out = []
        for i in range(n):
            f = self.tmp / f"t{i}.png"
            Image.new("RGB", (54, 96), cols[i]).save(f)
            out.append((f, f"T{i}"))
        return out, cols

    def test_lays_out_exactly_the_tiles_given(self):
        from PIL import Image
        from lib.media_util import contact_sheet
        for n, size in [(1, (270, 480)), (3, (810, 480)), (6, (1620, 480)), (7, (1620, 960))]:
            with self.subTest(n=n):
                tiles, cols = self.tiles(n)
                out = contact_sheet(tiles, self.tmp / f"s{n}.png", cols=6, tile_w=270, tile_h=480)
                with Image.open(out) as im:
                    self.assertEqual(im.size, size)
                    for i in range(n):                                     # every tile is where it should be
                        x, y = (i % min(6, n)) * 270 + 135, (i // min(6, n)) * 480 + 240
                        self.assertEqual(im.getpixel((x, y)), cols[i])
        self.assertIsNone(contact_sheet([], self.tmp / "none.jpg", cols=6, tile_w=10, tile_h=10))
        self.assertFalse((self.tmp / "none.jpg").exists())

    def test_labels_fits_and_closed_files(self):
        from PIL import Image
        from lib.media_util import contact_sheet
        tiles, _ = self.tiles(3)
        tiles[1] = (Image.new("RGB", (100, 50), "white"), [("line one", "yellow"), ("line two", "white")])
        for fit in ("stretch", "contain", "bottom"):
            out = no_resource_warnings(self, lambda: contact_sheet(tiles, self.tmp / f"{fit}.jpg", cols=2, tile_w=64,
                                                                   tile_h=40, label_h=18, fit=fit, label_box=(30, 12)))
            with Image.open(out) as im:
                self.assertEqual(im.size, (128, 2 * 58))
        for f, _ in (tiles[0], tiles[2]):
            f.unlink()                                                     # nothing holds the files (Windows)


class TestFrameGrab(TempDir):
    def test_grab_frame_pipes_no_temp_file(self):
        from lib import media_util
        v = _video(self.tmp / "v.mp4")
        with mock.patch("tempfile.mkstemp", side_effect=AssertionError("no temp files")):
            im = no_resource_warnings(self, lambda: media_util.grab_frame(v, 1.0, 90, 160, fit="crop", mode="RGBA"))
            self.assertEqual((im.size, im.mode), ((90, 160), "RGBA"))
            self.assertEqual(media_util.grab_frame(v, 1.0, 160, 90).size, (160, 90))
            self.assertIsNone(media_util.grab_frame(v, 50.0, 160, 90))      # past the end

    def test_grab_frame_file_and_previews_grab(self):
        from lib import media_util, previews
        v = _video(self.tmp / "v.mp4")
        out = media_util.grab_frame_file(v, 0.5, self.tmp / "f.jpg", vf="scale=64:-2", quality=3)
        self.assertEqual(out, self.tmp / "f.jpg")
        self.assertIsNone(media_util.grab_frame_file(v, 50.0, self.tmp / "none.jpg"))
        # MI-9: previews.grab_frame left a mkstemp PNG (and its fd) behind on every call
        with mock.patch("tempfile.mkstemp", side_effect=AssertionError("no temp files")):
            im = no_resource_warnings(self, lambda: previews.grab_frame(v, 1000))
        self.assertEqual((im.size, im.mode), (common.frame_size(), "RGBA"))

    def test_grab_frame_file_never_returns_a_stale_file(self):
        from lib import media_util
        v = _video(self.tmp / "v.mp4")
        old = self.tmp / "old.jpg"
        old.write_bytes(b"an earlier frame")
        self.assertIsNone(media_util.grab_frame_file(v, 50.0, old))    # past the end: nothing new, so no frame
        self.assertFalse(old.exists())


# --------------------------------------------------------------------------- the plan steps and their Context
def golden_project(tmp: Path):
    """A 25 fps client (profile sequence-settings), a 12 s clip with preflight, removed pauses (one protected), a cut
    word, a 4:5 window, a punch-in, three graphics, a sound and a music cue point: every compile step has work."""
    from lib.media import preflight
    from test_pipeline import make_project
    root, p, _words = make_project(tmp)
    prof = root / common.CLIENT_PROFILE_REL
    prof.mkdir(parents=True, exist_ok=True)
    common.write_json(prof / "sequence-settings.json", {"general": {"timebase": 25, "ntsc": False}})
    common.set_context(root)
    try:
        preflight(p, [root / "data/Raw/CLIP1.mov"])
    finally:
        common.set_context(None)
    common.write_json(p.p("06_audio/dialogue/pauses.json"), {"keep_ms": [[0, 4100], [4700, 8000], [8600, 12000]],
                                                             "cuts_ms": [[4100, 4700], [8000, 8600]]})
    common.write_json(p.p("01_analysis/edit-decisions.json"), {
        "video_id": "CLIP1",
        "global": {"main_footage": "data/Raw/CLIP1.mov", "framing": "4:5",
                   "remove_pauses": {"protect": [["00:00:08.000", "00:00:08.600"]]},
                   "cut_words": [{"word_ids": [3], "reason": "filler"}]},
        "music": {"status": "NO_MUSIC_SUPPLIED", "cue_points": [{"label": "drop", "at": "00:00:06.000"}]},
        "caption_highlights": [{"text": "التشخيص الصحيح", "at": "00:00:08.600"}],
        "decisions": [
            {"decision_id": "EDIT_001", "segment_id": "SEG_001", "evidence": "هل في حاجات معينة", "start": "00:00:00.200",
             "end": "00:00:04.000", "semantic_intent": "hook", "visual_treatment": "hook", "confidence": "high",
             "camera": {"type": "punch_in", "at": "00:00:01.000", "until": "00:00:03.000", "scale_factor": 1.1},
             "graphics": [{"id": "GFX_001", "template": "hook_title", "start": "00:00:00.200", "end": "00:00:03.500",
                           "text": "هل في حاجات معينة"}],
             "sound": [{"type": "pop", "at": "00:00:02.000"}]},
            {"decision_id": "EDIT_002", "segment_id": "SEG_002", "evidence": "أول حاجة التشخيص الصحيح",
             "start": "00:00:05.000", "end": "00:00:10.000", "semantic_intent": "point", "visual_treatment": "list",
             "confidence": "high",
             "graphics": [{"id": "GFX_002", "template": "checklist", "start": "00:00:05.000", "end": "00:00:09.000",
                           "title": "خطوات", "items": [{"text": "التشخيص", "at": "00:00:06.000"},
                                                      {"text": "Isotretinoin", "at": "00:00:07.500", "latin": True}]},
                          {"id": "GFX_003", "template": "name_card", "start": "00:00:09.000", "end": "00:00:11.500",
                           "name": "د/ نهلة", "lines": ["كلية الطب"]}]}]})
    return root, p


class TestPlanStepsBindTheirContext(TempDir):
    """Review I1: a step called on its own (no compile_plan around it) used whatever Context was bound for its frame
    maths. A 25 fps client read with its Context, built under the default 24 fps process context, must still get 25 fps
    frames (start 0.2 s = frame 5, 12 s = 300 frames before cuts), identical to compile_plan's."""

    def test_unbound_build_plan_uses_the_inputs_rate(self):
        from lib import plan
        root, p = golden_project(self.tmp)
        common.set_context(None)                                       # the default process context (24 fps)
        self.addCleanup(common.set_context, None)
        self.assertEqual(common.seq_fps(), 24.0)
        ctx = common.Context(root)
        inp = plan.read_inputs(p, ctx)
        self.assertEqual(inp.fps, 25.0)
        vd, _e, _w = plan.validate_decisions(inp)                      # one step alone
        self.assertEqual(vd["events"][0]["start_frame"], 5)            # 0.2 s at 25 fps (24 fps would give 5 too)
        self.assertEqual(vd["events"][1]["end_frame"], 225)            # 9.0 s at 25 fps (24 fps: 216)
        fr, _e, _w = plan.apply_framing(inp, plan.build_camera(inp, vd["camera"], vd["events"])[0])
        self.assertEqual(fr["merged"][-1]["end_frame"], 300)           # 12 s at 25 fps (24 fps: 288)
        built = plan.build_plan(inp)
        self.assertTrue(built["ok"], built["errors"])
        self.assertEqual(common.seq_fps(), 24.0)                       # nothing leaked into the process context
        plan.write_outputs(p, built)
        unbound = common.read_json(p.p("01_analysis/timeline-spec.json"))
        md_unbound = p.p("01_analysis/edit-plan.md").read_text(encoding="utf-8")
        plan.compile_plan(p, ctx)
        bound = common.read_json(p.p("01_analysis/timeline-spec.json"))
        unbound.pop("generated"), bound.pop("generated")
        self.assertEqual(unbound, bound)
        self.assertEqual(md_unbound, p.p("01_analysis/edit-plan.md").read_text(encoding="utf-8"))
        self.assertEqual(bound["fps"], 25.0)


GOLDEN = SK / "tests/fixtures/golden_plan"
GOLDEN_FILES = ("01_analysis/timeline-spec.json", "01_analysis/plan-validation.json", "01_analysis/edit-plan.md",
                "03_broll/broll-manifest.json", "06_audio/audio-cue-sheet.json",
                "02_transcription/subtitles-seq.srt", "02_transcription/captions-short-seq.srt")


def _golden_text(rel: str, text: str, root: Path) -> str:
    """Stable form of one compiled file: timestamps (`generated`, `engine_version`) dropped, the temp root replaced."""
    for form in {str(root), str(root).replace("\\", "/"), json.dumps(str(root))[1:-1]}:
        text = text.replace(form, "<ROOT>")
    if rel.endswith(".json"):
        def strip(o):
            if isinstance(o, dict):
                return {k: strip(v) for k, v in o.items() if k not in ("generated", "engine_version")}
            return [strip(x) for x in o] if isinstance(o, list) else o
        text = json.dumps(strip(json.loads(text)), ensure_ascii=False, indent=1, sort_keys=True) + "\n"
    return text


class TestGoldenPlan(TempDir):
    """Review M9: `reel plan` output locked byte for byte. The expected files in tests/fixtures/golden_plan/ were
    written by the pre-refactor engine (fb56caa, the one-function compile_plan) with WHYNOT_REGEN_GOLDEN=1; any change
    to what a plan compiles to fails here. Regenerate only for an intended output change, and say so in the commit."""

    def test_compiled_outputs_match_the_golden_files(self):
        from lib.plan import compile_plan
        root, p = golden_project(self.tmp)
        common.set_context(root)
        self.addCleanup(common.set_context, None)
        res = compile_plan(p)
        self.assertTrue(res["ok"], res["errors"])
        regen = os.environ.get("WHYNOT_REGEN_GOLDEN") == "1"
        for rel in GOLDEN_FILES:
            got = _golden_text(rel, p.p(rel).read_text(encoding="utf-8"), root)
            exp = GOLDEN / rel.replace("/", "__")
            if regen:
                exp.parent.mkdir(parents=True, exist_ok=True)
                exp.write_text(got, encoding="utf-8", newline="\n")
                continue
            with self.subTest(file=rel):
                self.assertEqual(got, exp.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
