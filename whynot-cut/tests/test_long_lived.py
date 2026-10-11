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


if __name__ == "__main__":
    unittest.main()
