"""3.0 T2.18 - the After Effects extras (clip graphics, MOGRTs) take their frame rate from the profile, and a render
counts only when this run wrote it (spec: nh_ae_lib.jsx hard-coded NH.FPS = 24; MI-13).
Run:  bash tools/test.sh -p test_ae_extras.py
"""
import sys as _sys
_sys.dont_write_bytecode = True  # keep the plugin folder free of __pycache__
import _isolation  # noqa: F401,E402  G79: sandbox the engine home first (tests/_isolation.py)
import json
import os
import shutil
import subprocess
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

sys = _sys
SK = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SK / "engine" / "reel"))

from lib import common, plat  # noqa: E402
from lib.common import Paths, write_json  # noqa: E402

LIB_JSX = SK / "templates/after_effects/nh_ae_lib.jsx"
ARABIC = "عميل"          # a client folder named in Arabic


def client(tmp: Path, timebase: int, ntsc: bool, name: str = "Client") -> Path:
    root = tmp / name
    for d in ("assets", "data"):
        (root / d).mkdir(parents=True, exist_ok=True)
    write_json(root / common.CLIENT_PROFILE_REL / "sequence-settings.json",
               {"general": {"timebase": timebase, "ntsc": ntsc}})
    return root


def nh_data(jsx: Path) -> dict:
    """The NH_DATA object a generated build script defines."""
    text = jsx.read_text(encoding="utf-8")
    start = text.index("var NH_DATA = ") + len("var NH_DATA = ")
    return json.JSONDecoder().raw_decode(text[start:])[0]


class TempDir(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="t218_"))
        self.addCleanup(shutil.rmtree, self.tmp, True)


class TestExtrasFps(TempDir):
    RATES = [(24, False, 24.0), (25, False, 25.0), (30, True, 29.97), (24, True, 23.976), (60, True, 59.94)]

    def paths(self, timebase, ntsc) -> Paths:
        p = Paths(client(self.tmp, timebase, ntsc, f"C{timebase}{int(ntsc)}"), "V1")
        p.ensure_project()
        write_json(p.p("01_analysis/timeline-spec.json"),
                   {"fps": common.seq_fps(common.Context(p.root)), "duration_frames": 240, "events": [],
                    "main_segments": []})
        return p

    def test_clip_graphics_script_carries_the_profile_rate(self):
        from lib import ae_builder
        for tb, ntsc, want in self.RATES:
            p = self.paths(tb, ntsc)
            with common.use_context(common.Context(p.root)):
                res = ae_builder.generate(p)
            self.assertAlmostEqual(nh_data(Path(res["jsx"]))["fps"], want, places=3, msg=(tb, ntsc))
            self.assertAlmostEqual(res["fps"], want, places=3)

    def test_mogrt_script_carries_the_profile_rate(self):
        from lib import mogrt_builder
        for tb, ntsc, want in self.RATES:
            p = self.paths(tb, ntsc)
            with common.use_context(common.Context(p.root)):
                jsx = mogrt_builder.generate(p)
            self.assertAlmostEqual(nh_data(jsx)["fps"], want, places=3, msg=(tb, ntsc))

    def test_a_plan_made_at_another_rate_is_flagged(self):
        from lib import ae_builder
        p = self.paths(25, False)
        spec = json.loads(p.p("01_analysis/timeline-spec.json").read_text(encoding="utf-8"))
        spec["fps"] = 24.0
        write_json(p.p("01_analysis/timeline-spec.json"), spec)
        with common.use_context(common.Context(p.root)):
            res = ae_builder.generate(p)
        self.assertEqual(nh_data(Path(res["jsx"]))["fps"], 25.0)           # the profile decides
        self.assertTrue(any("24" in w and "25" in w for w in res["warnings"]), res.get("warnings"))

    def test_a_plan_at_the_profile_rate_has_no_warning(self):
        from lib import ae_builder
        p = self.paths(30, True)
        with common.use_context(common.Context(p.root)):
            res = ae_builder.generate(p)
        self.assertEqual(res["warnings"], [])

    def test_library_sets_the_rate_from_the_data_before_building(self):
        text = LIB_JSX.read_text(encoding="utf-8")
        self.assertIn("NH.applyFps = function", text)
        for fn in ("NH.build = function", "NH.buildMogrts = function"):
            body = text[text.index(fn):]
            self.assertIn("NH.applyFps();", body[:body.index("app.beginUndoGroup") + 80], fn)

    @unittest.skipUnless(shutil.which("node"), "needs node to run the library's plain-JS part")
    def test_apply_fps_runs(self):
        lib = LIB_JSX.read_text(encoding="utf-8")
        for data, want in (({"fps": 29.97}, [29.97, 24]), ({"fps": 25}, [25, 24]), ({"fps": 0}, [24, 24]),
                           ({}, [24, 24])):
            js = self.tmp / "t.js"
            js.write_text(f"var NH_DATA = {json.dumps(data)};\n{lib}\nNH.applyFps(); var a = NH.FPS; "
                          "NH_DATA = {}; NH.FPS = 1; NH.applyFps();\n"
                          "console.log(JSON.stringify([a, NH.FPS]));", encoding="utf-8")
            r = subprocess.run(["node", str(js)], capture_output=True, text=True, encoding="utf-8")
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertEqual(json.loads(r.stdout), want, data)


class AerenderCase(TempDir):
    """ae_builder.render with the aerender process replaced."""

    def setUp(self):
        super().setUp()
        self.exe = self.tmp / "aer_fake.exe"
        self.exe.write_bytes(b"")
        self.use_client("Client")
        self.addCleanup(setattr, plat, "IS_WIN", plat.IS_WIN)

    def use_client(self, folder: str):
        self.paths = Paths(client(self.tmp, 24, False, folder), "V1")
        self.paths.ensure_project()
        write_json(self.paths.output / "discovery/environment.json", {"aerender": str(self.exe)})
        self.aep = self.paths.p(f"04_after_effects/project/V1_{common.project_prefix()}_GFX.aep")
        self.aep.write_bytes(b"AEP")
        self.comps = self.paths.p("04_after_effects/compositions")

    def mov(self, name: str, data: bytes = b"MOV", age_s: float = 0) -> Path:
        f = self.comps / name
        f.write_bytes(data)
        if age_s:
            t = time.time() - age_s
            os.utime(f, (t, t))
        return f

    def render(self, writes=(), **kw):
        """Render with a fake aerender that writes `writes` ((name, bytes) pairs) into compositions/."""
        from lib import ae_builder
        self.calls = []

        def run(cmd, check=True, timeout=None, **_):
            proj = Path(cmd[cmd.index("-project") + 1])
            self.calls.append({"cmd": list(cmd), "project": str(proj),
                               "project_bytes": proj.read_bytes() if proj.exists() else None})
            for name, data in writes:
                (self.comps / name).write_bytes(data)
            return subprocess.CompletedProcess(cmd, 0, "", "")
        with mock.patch.object(ae_builder, "run", run):
            return ae_builder.render(self.paths, **kw)


class TestFreshRenderOnly(AerenderCase):
    def test_a_stale_output_is_not_rendered(self):
        self.mov("GFX_001.mov", age_s=3600)
        r = self.render()
        self.assertEqual(r["status"], "STALE_OUTPUT_NOT_RENDERED", r)
        self.assertEqual(r["outputs"], [])
        self.assertEqual([Path(x).name for x in r["stale_outputs"]], ["GFX_001.mov"])
        self.assertIn("GFX_001.mov", r["msg"])
        saved = json.loads(self.paths.p("04_after_effects/ae-render-result.json").read_text(encoding="utf-8"))
        self.assertEqual(saved["status"], "STALE_OUTPUT_NOT_RENDERED")

    def test_a_just_written_output_is_rendered_and_stale_ones_are_listed(self):
        self.mov("GFX_001.mov", age_s=3600)
        r = self.render([("GFX_002.mov", b"new")])
        self.assertEqual(r["status"], "RENDERED", r)
        self.assertEqual([Path(x).name for x in r["outputs"]], ["GFX_002.mov"])
        self.assertEqual([Path(x).name for x in r["stale_outputs"]], ["GFX_001.mov"])

    def test_a_rewrite_of_the_same_size_counts(self):
        self.mov("GFX_001.mov", b"OLD", age_s=3600)
        r = self.render([("GFX_001.mov", b"NEW")])
        self.assertEqual(r["status"], "RENDERED", r)
        self.assertEqual(r["stale_outputs"], [])

    def test_a_file_written_just_before_the_start_is_still_stale(self):
        """Inside the 1 s clock tolerance: the before/after snapshot, not only the clock, decides."""
        self.mov("GFX_001.mov", age_s=0.2)
        r = self.render()
        self.assertEqual(r["status"], "STALE_OUTPUT_NOT_RENDERED", r)

    def test_an_empty_output_is_not_a_render(self):
        r = self.render([("GFX_001.mov", b"")])
        self.assertEqual(r["status"], "FAILED", r)
        self.assertEqual(r["outputs"], [])

    def test_nothing_rendered_fails_with_a_message(self):
        r = self.render()
        self.assertEqual(r["status"], "FAILED", r)
        self.assertTrue(r["msg"])

    def test_apple_double_files_are_ignored(self):
        r = self.render([("._GFX_001.mov", b"junk")])
        self.assertEqual(r["status"], "FAILED", r)

    def test_missing_aep_is_skipped(self):
        self.aep.unlink()
        self.assertEqual(self.render()["status"], "SKIPPED")

    def test_the_test_sandbox_refuses_the_real_aerender(self):
        real = self.tmp / "aerender.exe"
        real.write_bytes(b"")
        write_json(self.paths.output / "discovery/environment.json", {"aerender": str(real)})
        r = self.render([("GFX_001.mov", b"x")])
        self.assertEqual(r["status"], "REFUSED", r)
        self.assertEqual(self.calls, [])


class TestAsciiStaging(AerenderCase):
    """aerender on Windows reads its command line in the ANSI code page: ae_builder.render stages through ae_render."""

    def go(self, windows: bool) -> dict:
        plat.IS_WIN = windows
        r = self.render([("GFX_001.mov", b"x")])
        self.assertEqual(r["status"], "RENDERED", r)
        return self.calls[0]

    def test_arabic_folder_renders_an_ascii_copy_on_windows(self):
        self.use_client(ARABIC)
        call = self.go(True)
        self.assertTrue(call["project"].isascii(), call["project"])
        self.assertNotEqual(call["project"], str(self.aep))
        self.assertEqual(call["project_bytes"], b"AEP")                   # a copy of the real project
        self.assertFalse(Path(call["project"]).parent.exists())           # stage removed
        self.assertEqual(self.aep.read_bytes(), b"AEP")                   # the real project untouched

    def test_ascii_folder_and_macos_pass_the_project_as_it_is(self):
        self.assertEqual(self.go(True)["project"], str(self.aep))
        self.use_client(ARABIC)
        self.assertEqual(self.go(False)["project"], str(self.aep))

    def test_the_stage_is_removed_when_aerender_hangs(self):
        from lib import ae_builder
        self.use_client(ARABIC)
        plat.IS_WIN = True
        stages = []

        def run(cmd, check=True, timeout=None, **_):
            stages.append(Path(cmd[cmd.index("-project") + 1]).parent)
            raise subprocess.TimeoutExpired(cmd, 5)
        with mock.patch.object(ae_builder, "run", run):
            r = ae_builder.render(self.paths, timeout=5)
        self.assertEqual(r["status"], "FAILED")
        self.assertFalse(stages[0].exists())

    def test_a_non_ascii_temp_folder_is_named(self):
        from lib import ae_builder
        self.use_client(ARABIC)
        plat.IS_WIN = True
        with mock.patch.object(tempfile, "gettempdir", return_value=str(self.tmp / ARABIC)), \
                mock.patch.object(ae_builder, "run", side_effect=AssertionError("must not start")):
            r = ae_builder.render(self.paths)
        self.assertEqual(r["status"], "FAILED", r)
        self.assertIn("TEMP", r["msg"])

    def test_one_staging_helper(self):
        """No second copy of the staging code: ae_builder uses ae_render.stage_ascii."""
        from lib import ae_builder, ae_render
        self.use_client(ARABIC)
        plat.IS_WIN = True
        with mock.patch.object(ae_render, "stage_ascii", wraps=ae_render.stage_ascii) as spy, \
                mock.patch.object(ae_builder, "run", return_value=subprocess.CompletedProcess([], 0, "", "")):
            ae_builder.render(self.paths)
        self.assertEqual(spy.call_count, 1)
        self.assertNotIn("mkdtemp", Path(ae_builder.__file__).read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
