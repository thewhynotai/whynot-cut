"""Portability edges (3.0 T2.15; engine review MI-14..MI-18, §10): one test per item.

Non-ASCII Windows engine home and OpenCV's face model in doctor, --footage through native_path, UNC pathurl,
ffmpeg timeouts, the bundled ffmpeg before PATH (override + filter self-test), the AppleScript argv form, DELIVERED,
the capped status history, the writer lease's stable host id, `reel gpu-enable` through the pinned uv, and the plan's
default main_footage stored relative. (The bridge-queue items are in test_bridge_queue.py.) Run:
    <runtime python> -m unittest discover -s <plugin>/tests -p test_portability.py -v
"""
import sys as _sys
_sys.dont_write_bytecode = True
import _isolation  # noqa: F401,E402  G79: sandbox the engine home first (tests/_isolation.py)
import contextlib
import importlib.util
import io
import json
import os
import subprocess
import sys
import tempfile
import types
import unittest
from pathlib import Path, PureWindowsPath
from unittest import mock

SK = Path(__file__).resolve().parents[1]
if str(SK / "engine" / "reel") not in sys.path:
    sys.path.insert(0, str(SK / "engine" / "reel"))

from lib import common, media_util, plat, portability, writer_lock  # noqa: E402
from lib.common import Paths  # noqa: E402

CLI = SK / "engine" / "reel" / "cli.py"
IS_WIN = os.name == "nt"


def cli_module():
    spec = importlib.util.spec_from_file_location("reel_cli_t215", CLI)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


class _Tmp(unittest.TestCase):
    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.tmp = Path(self._td.name)
        self.addCleanup(self._td.cleanup)


def _done(rc=0, out="", err=""):
    return subprocess.CompletedProcess([], rc, out, err)


# ------------------------------------------------------------------------------------------- MI-14 doctor
class TestDoctorPortability(_Tmp):
    def test_a_non_ascii_windows_engine_home_is_a_fix_naming_whynot_home(self):
        f = portability.home_path_fix(PureWindowsPath("C:/Users/يونس/.whynot-cut"), is_win=True)
        self.assertIsNotNone(f)
        self.assertIn("non-ASCII", f["item"])
        self.assertIn(r"WHYNOT_HOME C:\whynot", f["fix"])
        self.assertIsNone(portability.home_path_fix(PureWindowsPath("C:/Users/yunus/.whynot-cut"), is_win=True))
        self.assertIsNone(portability.home_path_fix("/Users/يونس/.whynot-cut", is_win=False))   # macOS: not affected

    def test_an_empty_face_cascade_is_reported(self):
        def fake_cv2(empty):
            cc = mock.Mock()
            cc.return_value.empty.return_value = empty
            return types.SimpleNamespace(data=types.SimpleNamespace(haarcascades="C:/rt/cv2/data/"),
                                         CascadeClassifier=cc)
        bad = portability.face_model_check(fake_cv2(True))
        self.assertIs(bad["ok"], False)
        self.assertTrue(bad["path"].endswith("haarcascade_frontalface_default.xml"))
        fix = portability.face_model_fix(bad, "C:/Users/x/.whynot-cut")
        self.assertIn("face detection is off", fix["item"])
        self.assertIs(portability.face_model_check(fake_cv2(False))["ok"], True)
        self.assertIsNone(portability.face_model_fix({"ok": True}, "C:/h"))

    def test_doctor_carries_the_portability_report_and_its_fixes(self):
        from lib import onboard
        fix = {"item": "PORTABILITY-PROBE", "who": "editor", "fix": "x"}
        with mock.patch.object(portability, "doctor_checks", return_value=({"probe": 1}, [fix])) as dc:
            rep = onboard.doctor()
        dc.assert_called_once()
        self.assertEqual(rep["portability"], {"probe": 1})
        self.assertIn(fix, rep["fixes"])


# ------------------------------------------------------------------------------------------- MI-15 --footage
class TestFootageNativePath(_Tmp):
    @unittest.skipUnless(IS_WIN, "Git Bash paths exist on Windows only")
    def test_a_git_bash_footage_path_becomes_a_windows_path(self):
        cli = cli_module()
        p = Paths(self.tmp)
        with mock.patch.object(plat, "IS_WIN", True):
            self.assertEqual(cli.main_footage(p, "/d/Work/raw/a b.mp4"), [Path("D:/Work/raw/a b.mp4")])
            self.assertEqual(cli.footage_path(p, "data/Raw/a.mp4"), p.root / "data/Raw/a.mp4")


# ------------------------------------------------------------------------------------------- MI-16 UNC pathurl
class TestUncPathurl(unittest.TestCase):
    def test_a_share_is_file_server_share(self):
        from lib.premiere_xml import path_from_url, pathurl
        for p in ("\\\\nas\\clients\\Dr X\\a b.mov", "//nas/clients/Dr X/a b.mov"):
            self.assertEqual(pathurl(p), "file://nas/clients/Dr%20X/a%20b.mov")
        back = path_from_url("file://nas/clients/Dr%20X/a%20b.mov")
        self.assertEqual(str(back).replace("\\", "/"), "//nas/clients/Dr X/a b.mov")
        self.assertTrue(pathurl(Path(__file__)).startswith("file://localhost/"))       # a local file is unchanged


# ------------------------------------------------------------------------------------------- MI-17 timeouts
class TestFfmpegTimeouts(_Tmp):
    def test_ffmpeg_gets_ten_plus_three_times_the_media_duration(self):
        clip = self.tmp / "a.mp4"
        clip.write_bytes(b"x")
        with mock.patch.object(media_util, "_duration_cached", return_value=20.0):
            self.assertEqual(media_util.ff_timeout(["C:/ff/ffmpeg.exe", "-i", str(clip), "-f", "null", "-"]), 70)
        self.assertEqual(media_util.ff_timeout(["ffmpeg", "-ss", "3", "-t", "4.5", "-i", "nope.mp4", "o.wav"]), 23.5)
        self.assertEqual(media_util.ff_timeout(["/x/ffmpeg-win-x86_64-v7.1.exe", "-f", "lavfi", "-i", "sine"]),
                         media_util.FF_TIMEOUT_UNKNOWN_S)
        self.assertIsNone(media_util.ff_timeout(["git", "status"]))

    def test_common_run_passes_the_timeout_to_subprocess(self):
        with mock.patch.object(common.subprocess, "run", return_value=_done()) as run:
            common.run(["ffmpeg", "-t", "2", "-i", "x.wav", "-f", "null", "-"], check=False)
            self.assertEqual(run.call_args.kwargs["timeout"], 16)
            common.run(["git", "status"], check=False)
            self.assertIsNone(run.call_args.kwargs["timeout"])
            common.run(["ffmpeg", "-i", "x"], check=False, timeout=5)                    # an explicit one wins
            self.assertEqual(run.call_args.kwargs["timeout"], 5)


# ------------------------------------------------------------------------------------------- MI-18 ffmpeg choice
class TestBundledFfmpegFirst(_Tmp):
    def env(self, **kw):
        e = {k: v for k, v in os.environ.items() if k not in common.FFMPEG_OVERRIDES}
        e.update(WHYNOT_HOME=str(self.tmp / "home"), **kw)
        return mock.patch.dict(os.environ, e, clear=True)

    def test_the_runtime_ffmpeg_beats_path_and_an_override_beats_both(self):
        bundled = self.tmp / "imageio" / "ffmpeg-win-x86_64-v7.1.exe"
        mine = self.tmp / "mine" / "ffmpeg.exe"
        for f in (bundled, mine):
            f.parent.mkdir(parents=True)
            f.write_bytes(b"")
        fake = types.SimpleNamespace(get_ffmpeg_exe=lambda: str(bundled))
        with self.env(), mock.patch.dict(sys.modules, {"imageio_ffmpeg": fake}), \
                mock.patch.object(common.shutil, "which", return_value="C:/choco/bin/ffmpeg.exe"):
            ch = common.ffmpeg_choice()
            self.assertEqual((ch["path"], ch["source"]), (str(bundled), "engine runtime (imageio-ffmpeg)"))
            self.assertEqual(common.ffmpeg_exe(), str(bundled))
        with self.env(WHYNOT_FFMPEG=str(mine)), mock.patch.dict(sys.modules, {"imageio_ffmpeg": fake}):
            self.assertEqual(common.ffmpeg_choice()["source"], "override WHYNOT_FFMPEG")
        with self.env(WHYNOT_FFMPEG=str(self.tmp / "gone.exe")), mock.patch.dict(sys.modules, {"imageio_ffmpeg": fake}):
            ch = common.ffmpeg_choice()
            self.assertEqual(ch["path"], str(bundled))
            self.assertIn("WHYNOT_FFMPEG=", ch["bad_override"])
            self.assertTrue(any("WHYNOT_FFMPEG" in f["item"] for f in portability.ffmpeg_fix({}, ch["bad_override"])))

    def test_doctor_self_test_names_a_missing_filter(self):
        def runner(argv, **kw):
            if "-version" in argv:
                return _done(out="ffmpeg version 4.2 Copyright\n")
            if "-filters" in argv:
                return _done(out=" ... alimiter          A->A       Audio lookahead limiter.\n"
                                 " T.C ebur128          A->N       EBU R128 scanner.\n")
            return _done(rc=1, err="Option 'peak' not found\n")
        rep = portability.ffmpeg_report("C:/choco/ffmpeg.exe", "PATH", runner=runner)
        self.assertEqual(rep["version"], "ffmpeg version 4.2 Copyright")
        self.assertIn("afftdn", rep["filters_missing"])
        self.assertNotIn("alimiter", rep["filters_missing"])
        self.assertIs(rep["selftest_ok"], False)
        fixes = portability.ffmpeg_fix(rep)
        self.assertIn("afftdn", fixes[0]["item"])
        self.assertIn("WHYNOT_FFMPEG", fixes[0]["fix"])

    def test_the_engine_ffmpeg_passes_its_own_self_test(self):
        ff = common.ffmpeg_exe()
        if not ff:
            self.skipTest("no ffmpeg on this machine")
        rep = portability.ffmpeg_report(ff, "test")
        self.assertEqual(rep["filters_missing"], [], rep)
        self.assertIs(rep["selftest_ok"], True, rep)


# ------------------------------------------------------------------------------------------- §10 AppleScript
class TestAppleScriptArgv(unittest.TestCase):
    def test_the_script_path_travels_as_an_argument(self):
        from lib import adobe_run
        jsx = Path('/Users/x/Dr "Q" & do shell script "touch pwned"/run.jsx')
        for key, fn in (("after_effects", adobe_run.run_after_effects), ("photoshop", adobe_run.run_photoshop)):
            with self.subTest(app=key), mock.patch.object(plat, "IS_MAC", True), \
                    mock.patch.object(plat, "newest_app", return_value={"name": 'Adobe "Q" 2025', "exe": "/A"}), \
                    mock.patch.object(plat, "sandbox_refusal", return_value=None), \
                    mock.patch.object(adobe_run, "run", return_value=_done()) as run:
                fn(jsx, 60)
                argv = run.call_args.args[0]
                self.assertEqual(argv[:3], ["osascript", "-e", "on run argv"])
                self.assertEqual(argv[-1], str(jsx))
                scripts = [argv[i + 1] for i, a in enumerate(argv[:-1]) if a == "-e"]
                self.assertIn("end run", scripts)
                self.assertFalse(any("pwned" in s for s in scripts))                 # never inside the source
                self.assertTrue(any('tell application "Adobe \\"Q\\" 2025"' in s and "item 1 of argv" in s
                                    for s in scripts), scripts)


# ------------------------------------------------------------------------------------------- statuses
class TestStatus(_Tmp):
    def project(self):
        p = Paths(self.tmp / "C", "V1")
        p.ensure_project()
        return p

    def test_delivered_is_a_status(self):
        p = self.project()
        self.assertIn("DELIVERED", common.STATUSES)
        self.assertEqual(common.set_status(p, "DELIVERED", "sent to the client")["status"], "DELIVERED")

    def test_history_keeps_the_last_200_and_is_trimmed_inside_the_lock(self):
        p = self.project()
        common.write_json(common.status_path(p), {"video_id": "V1", "status": "TRANSCRIBED", "stages": {}, "blockers": [],
                                                  "history": [{"status": "TRANSCRIBED", "at": str(i), "note": str(i)}
                                                              for i in range(250)]})
        held, seen = [False], []
        real_lock, real_write = common.file_locked, common.write_json

        @contextlib.contextmanager
        def lock(path, *a, **k):
            with real_lock(path, *a, **k):
                held[0] = True
                try:
                    yield
                finally:
                    held[0] = False

        def write(path, data, *a, **k):
            seen.append((held[0], len(data.get("history", []))))
            return real_write(path, data, *a, **k)
        with mock.patch.object(common, "file_locked", lock), mock.patch.object(common, "write_json", write):
            st = common.set_status(p, "ANALYZED", "new")
        self.assertEqual(seen, [(True, 200)])
        self.assertEqual(len(st["history"]), common.STATUS_HISTORY_MAX)
        self.assertEqual(st["history"][-1]["note"], "new")
        self.assertEqual(st["history"][0]["note"], "51")                 # the oldest 51 dropped


# ------------------------------------------------------------------------------------------- writer lease host id
class TestStableHostId(_Tmp):
    def tearDown(self):
        writer_lock.host_id.cache_clear()

    def test_mac_uses_the_hardware_uuid_not_the_hostname(self):
        writer_lock.host_id.cache_clear()
        out = '  "IOPlatformUUID" = "1234-ABCD"\n'
        with mock.patch.object(writer_lock, "IS_MAC", True), \
                mock.patch.object(writer_lock.subprocess, "run", return_value=_done(out=out)):
            self.assertEqual(writer_lock.host_id(), "mac:1234-ABCD")

    def test_a_dead_holder_is_taken_over_after_the_hostname_changed(self):
        root = self.tmp / "C"
        (root / "output").mkdir(parents=True)
        rec = {"session_id": "s1", "pid": 999999, "pid_created": None, "host": "Yunus-MacBook.local",
               "host_id": "mac:1234-ABCD", "started_at": "x", "updated_at": "x", "command": "plan"}
        writer_lock.lock_path(root).write_text(json.dumps(rec), encoding="utf-8")
        with mock.patch.object(writer_lock, "host_id", return_value="mac:1234-ABCD"), \
                mock.patch.object(writer_lock.socket, "gethostname", return_value="yunus-mbp.lan"), \
                mock.patch.object(writer_lock, "pid_alive", return_value=False):
            self.assertIn("no longer running", writer_lock.stale_reason(root, rec))
        with mock.patch.object(writer_lock, "host_id", return_value="mac:OTHER"), \
                mock.patch.object(writer_lock, "pid_alive", return_value=False):
            self.assertIsNone(writer_lock.stale_reason(root, rec))      # another computer: only the 2 h rule
        old = {k: v for k, v in rec.items() if k != "host_id"}         # a lease written before 3.0: by name
        with mock.patch.object(writer_lock.socket, "gethostname", return_value="Yunus-MacBook.local"), \
                mock.patch.object(writer_lock, "pid_alive", return_value=False):
            self.assertIsNotNone(writer_lock.stale_reason(root, old))

    def test_a_new_lease_records_the_host_id(self):
        root = self.tmp / "C"
        root.mkdir()
        with mock.patch.object(writer_lock, "host_id", return_value="mac:1234-ABCD"), \
                mock.patch.dict(os.environ, {}), writer_lock.acquire(root, "plan", env={"WHYNOT_LOCK_SESSION": "t215"}):
            self.assertEqual(writer_lock.read(root)["host_id"], "mac:1234-ABCD")


# ------------------------------------------------------------------------------------------- gpu-enable via uv
class TestGpuEnableUv(_Tmp):
    def run_gpu_enable(self, home: Path, pip_ok: bool):
        cli = cli_module()
        calls = []

        def run(argv, *a, **kw):
            calls.append((list(map(str, argv)), kw))
            if argv[1:4] == ["-m", "pip", "--version"]:
                return _done(rc=0 if pip_ok else 1)
            return _done()
        rt_py = home / "runtimes" / "r-x" / ("Scripts/python.exe" if plat.IS_WIN else "bin/python")
        gpu = {"cuda_devices": 1, "cuda_libs_missing": ["cublas64_12.dll"]}
        buf = io.StringIO()
        with mock.patch.dict(os.environ, {"WHYNOT_HOME": str(home)}), \
                mock.patch.object(plat, "IS_MAC", False), \
                mock.patch.object(plat, "gpu_info", return_value=gpu), \
                mock.patch.object(plat, "install_cuda_redist", side_effect=OSError("CDN down")), \
                mock.patch.object(plat, "engine_runtime", return_value={"kind": "runtime", "python": rt_py}), \
                mock.patch("subprocess.run", side_effect=run), contextlib.redirect_stdout(buf), \
                contextlib.redirect_stderr(io.StringIO()):
            cli.cmd_gpu_enable(types.SimpleNamespace())
        return calls, json.loads(buf.getvalue()), rt_py

    def test_the_pinned_uv_installs_into_the_runtime_python(self):
        home = self.tmp / "home"
        uv = home / "bin" / ("uv.exe" if plat.IS_WIN else "uv")
        uv.parent.mkdir(parents=True)
        uv.write_bytes(b"")
        calls, doc, rt_py = self.run_gpu_enable(home, pip_ok=False)
        install = [c for c, _ in calls if c[0] == str(uv)]
        self.assertEqual(len(install), 1, calls)
        self.assertEqual(install[0][1:5], ["pip", "install", "--python", str(rt_py)])
        self.assertIn("nvidia-cublas-cu12", install[0])
        env = next(kw["env"] for c, kw in calls if c[0] == str(uv))
        self.assertEqual(env["UV_NO_CONFIG"], "1")
        self.assertEqual(doc["via"], "uv pip")

    def test_no_uv_and_no_pip_is_guidance_not_a_crash(self):
        from lib.errors import Guidance
        with self.assertRaises(Guidance) as cm:
            self.run_gpu_enable(self.tmp / "home", pip_ok=False)
        self.assertIn("reel setup", cm.exception.how)


# ------------------------------------------------------------------------------------------- plan main_footage
class TestDefaultFootageRelative(_Tmp):
    def client(self, raw_dir: Path):
        root = self.tmp / "C"
        (root / "assets").mkdir(parents=True)
        (root / "data").mkdir()
        raw_dir.mkdir(parents=True)
        (raw_dir / "a.mp4").write_bytes(b"")
        link = root / "data" / "Raw"
        if IS_WIN:
            import _winapi
            _winapi.CreateJunction(str(raw_dir), str(link))
        else:
            os.symlink(raw_dir, link)
        self.addCleanup(lambda: os.rmdir(link) if IS_WIN else os.unlink(link))
        inv = {"files": [{"path": str(link / "a.mp4"), "rel": "data/Raw/a.mp4", "role": "source_footage"}]}
        common.write_json(root / "output" / "discovery" / "input-inventory.json", inv)
        return root

    def test_a_raw_folder_linked_elsewhere_is_stored_relative_and_the_warning_names_it(self):
        from lib import plan
        root = self.client(self.tmp / "elsewhere" / "Footage")
        rel, why = plan._default_footage(Paths(root, "NOT_A_CLIP"))
        self.assertEqual(rel, "data/Raw/a.mp4")                  # never the junction's target outside the client
        self.assertIn("only raw clip", why)
        self.assertIn("NOT_A_CLIP", why)
        inp = plan.PlanInputs(ctx=common.current_context(), base={}, rng={}, main_file=rel, main_default=rel,
                              main_default_why=why, exists=lambda r: True, flagged=[], profile={},
                              video_id="NOT_A_CLIP")
        _, errors, warnings = plan.final_checks(inp, [])
        self.assertEqual(errors, [])
        w = next(x for x in warnings if "main_footage not set" in x)
        self.assertIn("data/Raw/a.mp4", w)
        self.assertIn("only raw clip", w)


if __name__ == "__main__":
    unittest.main()
