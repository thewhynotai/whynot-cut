"""3.0 T2.18 - the After Effects extras (clip graphics, MOGRTs) take their frame rate from the profile, and a render
counts only when this run wrote it (spec: nh_ae_lib.jsx hard-coded NH.FPS = 24; MI-13).
Run:  bash tools/test.sh -p test_ae_extras.py
"""
import sys as _sys
_sys.dont_write_bytecode = True  # keep the plugin folder free of __pycache__
import _isolation  # noqa: F401,E402  G79: sandbox the engine home first (tests/_isolation.py)
import argparse
import importlib.util
import io
import json
import os
import shutil
import subprocess
import contextlib
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

    def test_the_rate_is_exact_not_rounded(self):
        """30000/1001, not 29.97: After Effects gets the unrounded double (the Premiere sequence rate, frame for frame)."""
        from lib import ae_builder
        for tb, ntsc in ((30, True), (24, True), (60, True), (25, False)):
            p = self.paths(tb, ntsc)
            with common.use_context(common.Context(p.root)):
                want = common.seq_fps()
                res = ae_builder.generate(p)
            self.assertEqual(nh_data(Path(res["jsx"]))["fps"], want, (tb, ntsc))
        with common.use_context(common.Context(self.paths(30, True).root)):
            self.assertAlmostEqual(ae_builder.comp_fps(), 30000 / 1001, places=12)

    def test_mogrt_length_is_four_seconds_at_any_rate(self):
        from lib import mogrt_builder
        for tb, ntsc, frames in ((24, False, 96), (30, False, 120), (30, True, 120), (60, False, 240), (25, False, 100)):
            p = self.paths(tb, ntsc)
            with common.use_context(common.Context(p.root)):
                jsx = mogrt_builder.generate(p)
            data = nh_data(jsx)
            self.assertEqual(data["mogrt_frames"], frames, (tb, ntsc))
            self.assertAlmostEqual(data["mogrt_frames"] / data["fps"], 4.0, delta=0.02, msg=(tb, ntsc))
        self.assertIn("Math.round(4 * NH.FPS)", LIB_JSX.read_text(encoding="utf-8"))   # the library's own default

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


class TestExtrasFrameSize(TempDir):
    """Gate 2 A1: the After Effects extras use the profile's frame size (a 4:5 client gets 1080x1350 comps)."""

    def paths(self, size=None) -> Paths:
        root = client(self.tmp, 25, False, f"S{size[1] if size else 0}")
        if size:
            write_json(root / common.CLIENT_PROFILE_REL / "sequence-settings.json",
                       {"general": {"timebase": 25, "ntsc": False, "frame_width": size[0], "frame_height": size[1]}})
        p = Paths(root, "V1")
        p.ensure_project()
        write_json(p.p("01_analysis/timeline-spec.json"),
                   {"fps": 25.0, "duration_frames": 240, "events": [], "main_segments": []})
        return p

    def test_clip_graphics_and_mogrt_scripts_carry_the_profile_size(self):
        from lib import ae_builder, mogrt_builder
        for size, want in (((1080, 1350), [1080, 1350]), ((1920, 1080), [1920, 1080]), (None, [1080, 1920])):
            p = self.paths(size)
            with common.use_context(common.Context(p.root)):
                res = ae_builder.generate(p)
                jsx = mogrt_builder.generate(p)
            for d in (nh_data(Path(res["jsx"])), nh_data(jsx)):
                self.assertEqual([d["w"], d["h"]], want, size)

    def test_library_sets_the_size_from_the_data_before_building(self):
        text = LIB_JSX.read_text(encoding="utf-8")
        for fn in ("NH.build = function", "NH.buildMogrts = function"):
            body = text[text.index(fn):]
            self.assertIn("NH.applyFrameSize();", body[:body.index("app.beginUndoGroup") + 80], fn)

    @unittest.skipUnless(shutil.which("node"), "needs node to run the library's plain-JS part")
    def test_apply_frame_size_runs(self):
        lib = LIB_JSX.read_text(encoding="utf-8")
        for data, want in (({"w": 1080, "h": 1350}, [1080, 1350]), ({"w": 1920, "h": 1080}, [1920, 1080]),
                           ({}, [1080, 1920]), ({"w": 0, "h": -5}, [1080, 1920])):
            js = self.tmp / "t.js"
            js.write_text(f"var NH_DATA = {json.dumps(data)};\n{lib}\nNH.applyFrameSize();\n"
                          "console.log(JSON.stringify([NH.W, NH.H]));", encoding="utf-8")
            r = subprocess.run(["node", str(js)], capture_output=True, text=True, encoding="utf-8")
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertEqual(json.loads(r.stdout), want, data)


class TestScriptDriverLock(TempDir):
    """Gate 2 minor: ae-build, mogrt-build and `motion-build --run-script` (adobe_run.run_after_effects) start a new
    After Effects project too, so they take the bridge's build lock like `motion-build`."""

    def setUp(self):
        super().setUp()
        from lib import adobe_run
        self.adobe_run = adobe_run
        self.launched = []
        patches = [mock.patch.object(plat, "newest_app", lambda key: {"name": "AE", "exe": "AfterFX.exe"}),
                   mock.patch.object(plat, "sandbox_refusal", lambda what, *t: None),
                   mock.patch.object(plat, "IS_MAC", False),
                   mock.patch.object(adobe_run.subprocess, "Popen", lambda argv, **kw: self.launched.append(argv))]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)

    def test_the_script_runs_under_the_lock(self):
        from lib import ae_bridge, cep_queue
        seen = []
        res = self.adobe_run.run_after_effects(self.tmp / "x.jsx", 5,
                                               done=lambda: seen.append(cep_queue.read_lock(ae_bridge.queue_dir())) or True)
        self.assertEqual(len(self.launched), 1, res)
        self.assertTrue(seen and seen[0] and "x.jsx" in seen[0]["what"], seen)
        self.assertIsNone(cep_queue.read_lock(ae_bridge.queue_dir()))           # released after the run

    def test_a_held_lock_refuses_with_blocked(self):
        from lib import ae_bridge
        from lib.errors import exit_code
        with ae_bridge.build_lock("motion-build other"):
            res = self.adobe_run.run_after_effects(self.tmp / "x.jsx", 5, lock_wait_s=0.2)
        self.assertEqual(res["status"], "REFUSED", res)
        self.assertIn("another build", res["blocked"])
        self.assertEqual((self.launched, exit_code(res)), ([], 2))

    def test_mogrt_partial_is_a_failure(self):
        """Gate 2 minor: some templates missing (PARTIAL) exited 0."""
        from lib import mogrt_builder
        from lib.errors import exit_code
        p = Paths(client(self.tmp, 25, False), "V1")
        d = mogrt_builder.mogrt_dir(p)

        def fake_ae(jsx, timeout, done=None):
            import zipfile
            with zipfile.ZipFile(d / "NH_hook_title.mogrt", "w") as z:
                z.writestr("definition.json", "{}")
            return {"returncode": None}
        with mock.patch.object(self.adobe_run, "run_after_effects", fake_ae), common.use_context(common.Context(p.root)):
            res = mogrt_builder.build(p)
        self.assertEqual(res["status"], "PARTIAL", res)
        self.assertIs(res["ok"], False)
        self.assertEqual(exit_code(res), 1)


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

    def render(self, writes=(), returncode: int = 0, **kw):
        """Render with a fake aerender that writes `writes` ((name, bytes[, age_s]) tuples) into compositions/; age_s
        sets that file's mtime that many seconds into the past (a copy, or a file server whose clock runs behind)."""
        from lib import ae_builder
        self.calls = []

        def run(cmd, check=True, timeout=None, **_):
            proj = Path(cmd[cmd.index("-project") + 1])
            self.calls.append({"cmd": list(cmd), "project": str(proj),
                               "project_bytes": proj.read_bytes() if proj.exists() else None})
            for name, data, *age in writes:
                (self.comps / name).write_bytes(data)
                if age:
                    t = time.time() - age[0]
                    os.utime(self.comps / name, (t, t))
            return subprocess.CompletedProcess(cmd, returncode, "", "")
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

    def test_a_stale_output_is_a_failed_result(self):
        """T2.2: nothing rendered this run must not exit 0 (MI-13)."""
        self.mov("GFX_001.mov", age_s=3600)
        self.assertIs(self.render()["ok"], False)
        self.assertIs(self.render([("GFX_009.mov", b"")])["ok"], False)

    def test_a_clock_that_runs_behind_does_not_hide_a_changed_file(self):
        """A file that existed before and was rewritten is fresh on the snapshot alone, whatever its mtime says."""
        self.mov("GFX_001.mov", b"OLD", age_s=3600)
        r = self.render([("GFX_001.mov", b"NEWER", 600)])        # server clock 10 minutes behind
        self.assertEqual(r["status"], "RENDERED", r)
        self.assertEqual([Path(x).name for x in r["outputs"]], ["GFX_001.mov"])

    def test_a_new_file_within_the_clock_slack_counts(self):
        r = self.render([("GFX_002.mov", b"x", 2)])               # 2 s behind: FAT granularity, NAS skew
        self.assertEqual(r["status"], "RENDERED", r)

    def test_a_new_file_with_an_old_mtime_is_a_copy_not_a_render(self):
        r = self.render([("GFX_002.mov", b"x", 3600)])
        self.assertEqual(r["status"], "STALE_OUTPUT_NOT_RENDERED", r)
        self.assertEqual(r["outputs"], [])

    def test_a_complete_render_is_not_partial(self):
        r = self.render([("GFX_001.mov", b"x"), ("GFX_002.mov", b"y")])
        self.assertEqual(r["status"], "RENDERED", r)
        self.assertNotIn("partial", r)
        self.assertNotIn("warnings", r)

    def test_stale_siblings_make_it_partial(self):
        self.mov("GFX_001.mov", age_s=3600)
        r = self.render([("GFX_002.mov", b"new")])
        self.assertEqual(r["status"], "RENDERED", r)
        self.assertIs(r["partial"], True)
        self.assertTrue(any("GFX_001.mov" in w for w in r["warnings"]), r["warnings"])

    def test_a_nonzero_aerender_code_is_reflected(self):
        r = self.render([("GFX_001.mov", b"x")], returncode=3)
        self.assertEqual(r["status"], "RENDERED", r)
        self.assertEqual(r["returncode"], 3)
        self.assertIs(r["partial"], True)
        self.assertTrue(any("code 3" in w for w in r["warnings"]), r["warnings"])
        saved = json.loads(self.paths.p("04_after_effects/ae-render-result.json").read_text(encoding="utf-8"))
        self.assertIn("warnings", saved)

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


def cli_module():
    spec = importlib.util.spec_from_file_location("reel_cli_t218", SK / "engine/reel/cli.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def run_cmd(fn, args):
    """A cmd_* function in this process: (exit code, the JSON document it printed)."""
    so, code = io.StringIO(), 0
    with contextlib.redirect_stdout(so), contextlib.redirect_stderr(io.StringIO()):
        try:
            fn(args)
        except SystemExit as e:
            code = e.code if isinstance(e.code, int) else 1
    return code, json.loads(so.getvalue())


class TestExitCodes(AerenderCase):
    """3.0 T2.2: `reel ae-render` / `reel ae-build` exit 1 when nothing was rendered or saved this run."""

    def setUp(self):
        super().setUp()
        self.cli = cli_module()
        self.args = argparse.Namespace(root=str(self.paths.root), video_id="V1", episode=None)
        patcher = mock.patch.object(self.cli, "P", return_value=self.paths)
        patcher.start()
        self.addCleanup(patcher.stop)

    def render_cmd(self, writes=(), returncode=0):
        from lib import ae_builder

        def run(cmd, **_):
            for n, d in writes:
                (self.comps / n).write_bytes(d)
            return subprocess.CompletedProcess(cmd, returncode, "", "")
        with mock.patch.object(ae_builder, "run", run):
            return run_cmd(self.cli.cmd_ae_render, self.args)

    def test_ae_render_exits_1_when_only_stale_outputs_exist(self):
        self.mov("GFX_001.mov", age_s=3600)
        code, doc = self.render_cmd()
        self.assertEqual(doc["status"], "STALE_OUTPUT_NOT_RENDERED")
        self.assertEqual(code, 1)

    def test_ae_render_exits_1_when_nothing_rendered(self):
        code, doc = self.render_cmd()
        self.assertEqual((doc["status"], code), ("FAILED", 1))

    def test_ae_render_exits_0_when_rendered(self):
        code, doc = self.render_cmd([("GFX_001.mov", b"x")])
        self.assertEqual((doc["status"], code), ("RENDERED", 0))

    def test_ae_render_partial_exits_0_but_says_so(self):
        self.mov("GFX_001.mov", age_s=3600)
        code, doc = self.render_cmd([("GFX_002.mov", b"x")])
        self.assertEqual((code, doc["partial"]), (0, True))

    def build_cmd(self, aep_age_s=None, rebuilds=False, plan_fps=None):
        """cmd_ae_build with After Effects replaced: the .aep is `aep_age_s` old (None: absent), and `rebuilds` saves it."""
        from lib import adobe_run
        spec = {"fps": plan_fps or common.seq_fps(common.Context(self.paths.root)), "duration_frames": 240,
                "events": [], "main_segments": []}
        write_json(self.paths.p("01_analysis/timeline-spec.json"), spec)
        self.aep.unlink()
        if aep_age_s is not None:
            self.aep.write_bytes(b"AEP")
            t = time.time() - aep_age_s
            os.utime(self.aep, (t, t))

        def fake_ae(jsx, timeout, done=None):
            if rebuilds:
                self.aep.write_bytes(b"NEW")
            return {"status": "DONE"}
        with mock.patch.object(self.cli, "refuse_stale_window"), mock.patch.object(self.cli, "require_plan_approval"), \
                mock.patch.object(adobe_run, "run_after_effects", fake_ae), \
                common.use_context(common.Context(self.paths.root)):
            return run_cmd(self.cli.cmd_ae_build, self.args)

    def test_ae_build_exits_1_when_the_project_was_not_rebuilt(self):
        code, doc = self.build_cmd(aep_age_s=3600)
        self.assertEqual(doc["execute"]["status"], "STALE_AEP_NOT_REBUILT")
        self.assertEqual((code, doc["ok"], doc["status"]), (1, False, "STALE_AEP_NOT_REBUILT"))

    def test_ae_build_exits_1_when_no_project_exists(self):
        code, doc = self.build_cmd()
        self.assertEqual((doc["execute"]["status"], code), ("FAILED", 1))

    def test_ae_build_exits_0_when_the_project_was_saved(self):
        code, doc = self.build_cmd(rebuilds=True)
        self.assertEqual((doc["execute"]["status"], code), ("AEP_CREATED", 0))
        self.assertNotIn("ok", doc)

    def test_ae_build_with_a_busy_build_lock_exits_2(self):
        """Gate 2 tail: the refusal's `blocked` reaches the top-level document, so the exit code is 2, not 1."""
        from lib import adobe_run, ae_bridge, cep_queue
        self.build_cmd(rebuilds=False)          # lays out the plan and the paths
        with mock.patch.object(self.cli, "refuse_stale_window"), mock.patch.object(self.cli, "require_plan_approval"),                 mock.patch.object(plat, "newest_app", lambda key: {"name": "AE", "exe": "AfterFX.exe"}),                 mock.patch.object(plat, "sandbox_refusal", lambda what, *t: None),                 mock.patch.object(adobe_run.subprocess, "Popen", side_effect=AssertionError("must not launch")),                 mock.patch.object(cep_queue, "LOCK_WAIT_S", 0.2),                 common.use_context(common.Context(self.paths.root)),                 ae_bridge.build_lock("motion-build other"):
            code, doc = run_cmd(self.cli.cmd_ae_build, self.args)
        self.assertEqual(code, 2, doc)
        self.assertIn("another build", doc["blocked"])
        self.assertEqual((doc["ok"], doc["status"]), (False, "REFUSED"))

    def test_a_plan_rate_mismatch_is_in_the_build_result_warnings(self):
        code, doc = self.build_cmd(rebuilds=True, plan_fps=30.0)
        self.assertEqual(code, 0)                                   # a warning, never a block
        self.assertTrue(any("30" in w and "24" in w for w in doc["warnings"]), doc["warnings"])
        code, doc = self.build_cmd(rebuilds=True)
        self.assertEqual(doc["warnings"], [])


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
        from lib import ae_builder, ae_render
        self.use_client(ARABIC)
        plat.IS_WIN = True
        with mock.patch.object(tempfile, "gettempdir", return_value=str(self.tmp / ARABIC)), \
                mock.patch.object(ae_render, "ascii_stage_roots", return_value=[]), \
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
