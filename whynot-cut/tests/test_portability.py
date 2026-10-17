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

    # ---- fix round 1 (review I-1, m-1, m-2)
    def test_the_duration_probe_has_its_own_timeout(self):
        import threading
        import time
        clip = self.tmp / "on-a-stalled-share.mp4"
        clip.write_bytes(b"x")
        release = threading.Event()
        self.addCleanup(release.set)                      # the stuck probe thread ends with the test

        def stuck(*a):
            release.wait(30)
            return 99.0
        t0 = time.monotonic()
        with mock.patch.object(media_util, "_duration_cached", side_effect=stuck), \
                mock.patch.object(media_util, "FF_PROBE_TIMEOUT_S", 0.3):
            self.assertEqual(media_util.ff_timeout(["ffmpeg", "-i", str(clip), "-f", "null", "-"]),
                             media_util.FF_TIMEOUT_UNKNOWN_S)
        self.assertLess(time.monotonic() - t0, 5)

    def test_the_scale_variable_multiplies_every_timeout(self):
        cmd = ["ffmpeg", "-t", "2", "-i", "x.wav", "-f", "null", "-"]                # 10 + 3 x 2 = 16
        for v, want in (("2.5", 40), ("1", 16), ("0.5", 16), ("abc", 16), ("nan", 16), ("", 16)):
            with self.subTest(scale=v), mock.patch.dict(os.environ, {media_util.FF_TIMEOUT_SCALE_ENV: v}):
                self.assertEqual(media_util.ff_timeout(cmd), want)
        with mock.patch.dict(os.environ, {media_util.FF_TIMEOUT_SCALE_ENV: "2"}):
            self.assertEqual(media_util.ff_timeout(["ffmpeg", "-f", "lavfi", "-i", "sine"]),
                             2 * media_util.FF_TIMEOUT_UNKNOWN_S)

    def test_the_timeout_guidance_names_the_variable_not_a_missing_flag(self):
        from lib import errors
        ff = errors.describe(subprocess.TimeoutExpired(["C:/x/ffmpeg.exe", "-i", "a.mov"], 70))
        self.assertIn("WHYNOT_FFMPEG_TIMEOUT_SCALE", ff["how"])
        self.assertNotIn("--timeout", ff["how"])
        ae = errors.describe(subprocess.TimeoutExpired(["aerender"], 70))
        self.assertNotIn("--timeout", ae["how"])
        self.assertIn("dialog", ae["how"])


class _Hang:
    """A stand-in ffmpeg that hangs: subprocess.Popen runs a Python child that sleeps (reads nothing, writes nothing)
    whatever argv the engine built; ff_timeout is shortened so the watchdog fires within a second."""
    HANG = [sys.executable, "-c", "import time; time.sleep(60)"]

    def hang(self, timeout=0.5):
        real = subprocess.Popen
        argvs = []

        def popen(cmd, *a, **kw):
            argvs.append(list(map(str, cmd)))
            return real(self.HANG, *a, **kw)
        st = contextlib.ExitStack()
        st.enter_context(mock.patch.object(media_util.subprocess, "Popen", side_effect=popen))
        st.enter_context(mock.patch.object(media_util, "ff_timeout", return_value=timeout))
        return st, argvs


class TestFfmpegPipelinesNeverHang(_Tmp, _Hang):
    """Review I-1: every direct ffmpeg pipeline is bounded (preview_video.py: T2.14's fixer)."""

    def assert_killed(self, fn, argvs):
        import time
        t0 = time.monotonic()
        with self.assertRaises(subprocess.TimeoutExpired) as cm:
            fn()
        self.assertLess(time.monotonic() - t0, 20)
        self.assertEqual(cm.exception.timeout, 0.5)
        self.assertTrue(argvs and media_util.is_ff(argvs[0]), argvs)       # the engine's own ffmpeg argv
        return cm.exception

    def test_ff_popen_kills_a_hung_reader_and_passes_a_finished_one(self):
        st, _ = self.hang()
        with st, self.assertRaises(subprocess.TimeoutExpired):
            with media_util.ff_popen(["ffmpeg", "-i", "x"], stdout=subprocess.PIPE) as p:
                p.stdout.read()
        with mock.patch.object(media_util, "ff_timeout", return_value=30):
            with media_util.ff_popen([sys.executable, "-c", "print('ok')"], stdout=subprocess.PIPE) as p:
                self.assertEqual(p.stdout.read().strip(), b"ok")
        self.assertEqual(p.returncode, 0)

    def test_media_analyze_shots(self):
        from lib import media
        st, argvs = self.hang()
        with st:
            self.assert_killed(lambda: media.analyze_shots(self.tmp / "a.mp4", 30.0), argvs)

    def test_shots_analyze_window(self):
        from lib import shots
        st, argvs = self.hang()
        with st, mock.patch.object(shots, "detect_cuts", return_value=[]):
            self.assert_killed(lambda: shots.analyze_window(self.tmp / "a.mp4", 0, 30000, faces_fn=lambda im: []),
                               argvs)

    def test_motion_animatic_encoder(self):
        from PIL import Image
        from lib import media_util as mu, motion_animatic, motion_audio, previews, stamps
        plan = {"fps": 25, "duration_frames": 250, "scenes": [{"id": "S1", "type": "kinetic", "start_frame": 0}]}
        p = Paths(self.tmp / "C", "V1_MO")
        st, argvs = self.hang()
        with st, mock.patch.object(stamps, "read_compiled", return_value=plan), \
                mock.patch.object(previews, "Brand"), \
                mock.patch.object(motion_audio, "mix", return_value=self.tmp / "mix.wav"), \
                mock.patch.object(mu, "contact_sheet", return_value=self.tmp / "sheet.jpg"), \
                mock.patch.object(motion_animatic, "scene_still", return_value=Image.new("RGB", (540, 960))):
            self.assert_killed(lambda: motion_animatic.render(p), argvs)
        self.assertFalse(p.p("08_quality_control/animatic/_animatic_ffmpeg.log").exists())

    def run_timeout_of(self, fn):
        """subprocess.run as a hung ffmpeg would end: TimeoutExpired after the timeout the engine passed."""
        seen = []

        def run(cmd, *a, **kw):
            seen.append((list(map(str, cmd)), kw.get("timeout")))
            raise subprocess.TimeoutExpired(cmd, kw.get("timeout"))
        with mock.patch("subprocess.run", side_effect=run), self.assertRaises(subprocess.TimeoutExpired):
            fn()
        self.assertTrue(seen and media_util.is_ff(seen[0][0]), seen)
        return seen[0]

    def test_media_snap_range_points(self):
        from lib import media
        argv, timeout = self.run_timeout_of(lambda: media.snap_range_points(self.tmp / "a.mp4", 10000, 20000))
        self.assertEqual(timeout, media_util.ff_timeout(argv))
        self.assertIsNotNone(timeout)

    def test_reels_audio_card(self):
        from lib import episode, reels
        cand = {"id": "R1", "in_ms": 0, "out_ms": 4000, "total": 9, "type": "advice"}
        with mock.patch.object(episode, "episode_file", return_value=self.tmp / "ep.wav"):
            argv, timeout = self.run_timeout_of(lambda: reels.audio_card(None, cand, self.tmp / "R1.mp4"))
        self.assertEqual(timeout, 10 + 3 * 4)


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

    def test_an_override_may_name_the_folder_holding_ffmpeg(self):
        """Review m-4: like state.json `ffmpeg.path`, WHYNOT_FFMPEG may be the binary's folder."""
        folder = self.tmp / "ffmpeg-9"
        exe = folder / ("ffmpeg.exe" if IS_WIN else "ffmpeg")
        folder.mkdir()
        with self.env(WHYNOT_FFMPEG=str(folder)), mock.patch.dict(sys.modules, {"imageio_ffmpeg": None}):
            self.assertIsNotNone(common.ffmpeg_choice()["bad_override"])          # a folder without ffmpeg: bad
            exe.write_bytes(b"")
            ch = common.ffmpeg_choice()
            self.assertEqual((ch["path"], ch["source"], ch["bad_override"]),
                             (str(exe), "override WHYNOT_FFMPEG", None))

    def test_the_sandbox_drops_a_developers_ffmpeg_variables(self):
        self.assertIn("WHYNOT_FFMPEG", _isolation._DROP)
        self.assertIn("WHYNOT_FFMPEG_TIMEOUT_SCALE", _isolation._DROP)

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
                tell = [s for s in scripts if s.startswith('tell application "Adobe \\"Q\\" 2025"')]
                self.assertEqual(len(tell), 1, scripts)
                if key == "after_effects":                                          # unchanged form
                    self.assertTrue(tell[0].endswith("to DoScriptFile (item 1 of argv)"), tell)
                else:
                    # T2.15 review I-2: no `POSIX file` inside Photoshop's tell (it would be sent to Photoshop as an
                    # object specifier, -1728); the alias is made before the tell, by AppleScript (Mac run pending)
                    self.assertTrue(tell[0].endswith("to do javascript jsxFile"), tell)
                    self.assertNotIn("POSIX file", tell[0])
                    pre = scripts.index("set jsxFile to ((item 1 of argv) as POSIX file) as alias")
                    self.assertLess(pre, scripts.index(tell[0]))
                    self.assertLess(scripts.index("on run argv"), pre)


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

    def test_delivered_counts_as_done_on_the_board_and_in_the_stale_checks(self):
        """Review m-5: the client board and the motion-QC / `reel next` stale marks treat DELIVERED as finished."""
        import inspect
        from lib import motion_qc, onboard
        self.assertEqual(common.DONE_STATUSES, ("QC_PASSED", "READY_FOR_HUMAN_EDITOR", "DELIVERED"))
        self.assertIn("stale and status in DONE_STATUSES", inspect.getsource(motion_qc))    # motion `reel next`
        self.assertIn("stale and status in DONE_STATUSES", CLI.read_text(encoding="utf-8"))  # `reel next`
        root = self.tmp / "C"
        for d in ("assets", "data/Raw"):
            (root / d).mkdir(parents=True)
        (root / "data" / "Raw" / "a.mp4").write_bytes(b"")
        inv = {"files": [{"path": str(root / "data/Raw/a.mp4"), "rel": "data/Raw/a.mp4", "role": "source_footage",
                          "kind": "video", "size_bytes": 1}], "by_role": {}, "warnings": []}
        common.write_json(root / "output" / "discovery" / "input-inventory.json", inv)
        from lib.clip_ids import clip_ids, id_of
        pp = Paths(root, id_of(clip_ids(root, inv), "data/Raw/a.mp4"))
        pp.ensure_project()
        common.write_json(pp.p("02_transcription/transcript.json"), {})
        common.write_text(pp.p("09_handoff/README.md"), "x")
        common.set_status(pp, "DELIVERED", "sent")
        clip = onboard.inbox(root, refresh=False)["clips"][0]
        self.assertEqual((clip["status"], clip["state"]), ("DELIVERED", "done"), clip)

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
        import hashlib
        writer_lock.host_id.cache_clear()
        out = '  "IOPlatformUUID" = "1234-ABCD"\n'
        with mock.patch.object(writer_lock, "IS_MAC", True), \
                mock.patch.object(writer_lock.subprocess, "run", return_value=_done(out=out)):
            hid = writer_lock.host_id()
            # T2.15 review m-6: only a short hash of the hardware UUID goes into the (shared, synced) lease file
            self.assertEqual(hid, "mac:" + hashlib.sha256(b"1234-ABCD").hexdigest()[:16])
            self.assertNotIn("1234-ABCD", hid)
            self.assertTrue(writer_lock.same_host({"host_id": hid}))
            self.assertTrue(writer_lock.same_host({"host_id": "mac:1234-ABCD"}))      # a 3.0 beta lease, unhashed
            self.assertFalse(writer_lock.same_host({"host_id": "mac:5678-EFGH"}))

    def test_a_new_lease_never_holds_the_clear_uuid(self):
        writer_lock.host_id.cache_clear()
        root = self.tmp / "C"
        root.mkdir()
        out = '  "IOPlatformUUID" = "1234-ABCD"\n'
        with mock.patch.object(writer_lock, "IS_MAC", True), \
                mock.patch.object(writer_lock.subprocess, "run", return_value=_done(out=out)):
            hid = writer_lock.host_id()                      # looked up once per process (cached)
        with writer_lock.acquire(root, "plan", env={"WHYNOT_LOCK_SESSION": "t215b"}):
            text = writer_lock.lock_path(root).read_text(encoding="utf-8")
        self.assertNotIn("1234-ABCD", text)
        self.assertEqual(json.loads(text)["host_id"], hid)

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
    """gpu-enable's wheel fallback is the Windows path (cuBLAS pinned and hash-checked); macOS CI runs it as Windows."""
    def setUp(self):
        super().setUp()
        p = mock.patch.object(plat, "IS_WIN", True)
        p.start()
        self.addCleanup(p.stop)

    def run_gpu_enable(self, home: Path, pip_ok: bool, index_url=None):
        from lib import runtime
        cli = cli_module()
        calls = []
        comp = {"runtime": {"index_url": index_url}}

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
                mock.patch.object(runtime, "components", return_value=comp), \
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
        self.assertNotIn("--index-url", install[0])                       # components.json index_url: null
        env = next(kw["env"] for c, kw in calls if c[0] == str(uv))
        self.assertEqual(env["UV_NO_CONFIG"], "1")
        self.assertEqual(doc["via"], "uv pip")
        # T2.15 review m-7: pinned and hash-checked, like the rest of the runtime
        req = Path(install[0][install[0].index("-r") + 1])
        self.assertIn("--require-hashes", install[0])
        line = req.read_text(encoding="utf-8").strip()
        self.assertTrue(line.startswith("nvidia-cublas-cu12==12.9.1.4 --hash=sha256:"), line)
        self.assertEqual(line.count("--hash=sha256:"), 3)                  # win_amd64 + 2 manylinux wheels

    def test_the_runtime_index_url_is_used(self):
        home = self.tmp / "home"
        uv = home / "bin" / ("uv.exe" if plat.IS_WIN else "uv")
        uv.parent.mkdir(parents=True)
        uv.write_bytes(b"")
        calls, _, _ = self.run_gpu_enable(home, pip_ok=False, index_url="https://mirror.example/simple")
        argv = next(c for c, _ in calls if c[0] == str(uv))
        self.assertEqual(argv[argv.index("--index-url") + 1], "https://mirror.example/simple")

    def test_the_cublas_pin_matches_the_nvidia_redist_and_the_locked_ctranslate2(self):
        cli = cli_module()
        ver = cli.CUDA_WHEEL_PINS["nvidia-cublas-cu12"][0]
        self.assertEqual(plat.CUDA_REDIST_MANIFEST, f"redistrib_{'.'.join(ver.split('.')[:3])}.json")
        lock = (SK / "setup" / "locks" / "runtime-win-x64.lock").read_text(encoding="utf-8")
        self.assertIn("ctranslate2==4.", lock)                             # a CUDA 12 build: cuBLAS 12.x
        self.assertTrue(ver.startswith("12."))

    def test_pip_fallback_probe_has_a_timeout(self):
        home = self.tmp / "home"
        calls, doc, rt_py = self.run_gpu_enable(home, pip_ok=True)
        probe = next(kw for c, kw in calls if c[1:4] == ["-m", "pip", "--version"])
        self.assertEqual(probe.get("timeout"), 60)
        argv = next(c for c, _ in calls if c[1:4] == ["-m", "pip", "install"])
        self.assertIn("--require-hashes", argv)
        self.assertEqual(doc["via"], "pip")

    def test_no_uv_and_no_pip_is_guidance_not_a_crash(self):
        from lib.errors import Guidance
        with self.assertRaises(Guidance) as cm:
            self.run_gpu_enable(self.tmp / "home", pip_ok=False)
        self.assertIn("reel setup", cm.exception.how)

    def test_doctor_says_a_runtime_sync_removes_the_wheels(self):
        from lib import onboard
        gpu = {"cuda_devices": 1, "cuda_libs_missing": ["cublas64_12.dll"], "name": "RTX"}
        with mock.patch.object(plat, "gpu_info", return_value=gpu), \
                mock.patch.object(portability, "doctor_checks", return_value=({}, [])):
            rep = onboard.doctor()
        fix = next(f for f in rep["fixes"] if "GPU transcription" in f["item"])
        self.assertIn("reel gpu-enable again", fix["fix"])


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
                              video_id="NOT_A_CLIP", paths=Paths(root, "NOT_A_CLIP"), root=root)
        _, errors, warnings = plan.final_checks(inp, [])
        self.assertEqual(errors, [])
        w = next(x for x in warnings if "main_footage not set" in x)
        self.assertIn("data/Raw/a.mp4", w)
        self.assertIn("only raw clip", w)


def _link_dir(target: Path, link: Path) -> None:
    if IS_WIN:
        import _winapi
        _winapi.CreateJunction(str(target), str(link))
    else:
        os.symlink(target, link)


class TestRangeFootageRelative(_Tmp):
    """Review m-8: `reel range` stores --footage by the plan's rule (realpath on both sides), not a bare
    is_relative_to against the resolved client root."""

    def test_footage_through_a_linked_client_folder_is_stored_relative(self):
        from lib import media
        real = self.tmp / "real" / "C"
        for d in ("assets", "data/Raw"):
            (real / d).mkdir(parents=True)
        (real / "data" / "Raw" / "ep.mp4").write_bytes(b"")
        link = self.tmp / "C-link"
        _link_dir(real, link)
        self.addCleanup(lambda: os.rmdir(link) if IS_WIN else os.unlink(link))
        cli = cli_module()
        a = types.SimpleNamespace(root=str(link), video_id="R1", episode=None, footage=str(link / "data/Raw/ep.mp4"),
                                  start="1", end="5", snap=False, label="")
        buf = io.StringIO()
        with mock.patch.object(media, "probe", return_value={"duration_s": 60.0}), \
                mock.patch.object(media, "snap_range_points", return_value={}), contextlib.redirect_stdout(buf):
            cli.cmd_range(a)
        self.assertEqual(json.loads(buf.getvalue())["footage"], "data/Raw/ep.mp4")
        self.assertEqual(common.read_json(Paths(link, "R1").p("00_inputs/source.json"))["footage"], "data/Raw/ep.mp4")


# ------------------------------------------------------------------------------------------- bridge "no reply"
class TestBridgeNoReplyIsNotFinished(_Tmp):
    """Review m-3: the bridge writes result.json for its own 20-min "no reply" timeout while the host may still run
    the script: that job still counts as claimed (the old project is not restored under a running save)."""

    def test_result_kinds(self):
        from lib import cep_queue
        q = self.tmp / "q"
        q.mkdir()
        res = q / "J1.result.json"
        for body, claimed in ((json.dumps({"ok": True, "result": "{}"}), False),
                              (json.dumps({"ok": False, "error": "expired"}), False),
                              (json.dumps({"ok": False, "error": "no reply from PPRO within 20 min"}), True),
                              ('{"ok": tr', True)):                                   # still being written
            with self.subTest(body=body):
                res.write_text(body, encoding="utf-8")
                self.assertIs(cep_queue._bridge_has_job(q, "J1"), claimed)



# ------------------------------------------------------------------------------------------- Gate 2 G1 (review D)
class TestAsciiAeStage(_Tmp):
    """D1: an Arabic Windows user name makes %TEMP% non-ASCII too: the aerender stage then goes to the engine home
    (when ASCII), %ProgramData%/WhyNotCut/tmp, %SystemDrive%/WhyNotCut-tmp, or the 8.3 short form of %TEMP%."""

    ARABIC_TEMP = r"C:\Users\يونس\AppData\Local\Temp"

    def env(self, **kw):
        d = {"ProgramData": str(self.tmp / "ProgramData"), "SystemDrive": str(self.tmp / "sysdrive")}
        d.update(kw)
        return d

    def test_engine_home_first_when_ascii(self):
        from lib import ae_render
        roots = ae_render.ascii_stage_roots(temp=self.ARABIC_TEMP, home=self.tmp / "eng", environ=self.env(),
                                            short_path=lambda p: None)
        self.assertEqual(roots[0], self.tmp / "eng" / "tmp")
        self.assertEqual(roots[1], self.tmp / "ProgramData" / "WhyNotCut" / "tmp")
        self.assertEqual(roots[2], self.tmp / "sysdrive" / "WhyNotCut-tmp")

    def test_non_ascii_home_skipped_short_path_last(self):
        from lib import ae_render
        roots = ae_render.ascii_stage_roots(temp=self.ARABIC_TEMP, home=r"C:\Users\يونس\.whynot-cut",
                                            environ=self.env(), short_path=lambda p: r"C:\Users\D3C0~1\AppData\Local\Temp")
        self.assertTrue(all(str(r).isascii() for r in roots), roots)
        self.assertEqual(roots[0], self.tmp / "ProgramData" / "WhyNotCut" / "tmp")
        self.assertEqual(str(roots[-1]), r"C:\Users\D3C0~1\AppData\Local\Temp")

    def test_ascii_temp_is_used_as_before(self):
        from lib import ae_render
        self.assertEqual(ae_render.ascii_stage_roots(temp=str(self.tmp), home="x", environ={}), [self.tmp])

    def test_stage_made_under_the_first_root_that_works(self):
        from lib import ae_render
        aep = self.tmp / "مشروع.aep"
        aep.write_bytes(b"AEP")
        blocked = self.tmp / "blocked"
        blocked.write_text("a file, not a folder", encoding="utf-8")       # mkdir fails here -> next root
        good = self.tmp / "ok-root"
        with mock.patch.object(ae_render.plat, "IS_WIN", True), \
                mock.patch.object(ae_render, "ascii_stage_roots", return_value=[blocked / "tmp", good]):
            stage, r_aep, r_out = ae_render.stage_ascii(aep, self.tmp / "out" / "ريل.mov")
        try:
            self.assertEqual(stage.parent, good)
            self.assertEqual(r_aep.read_bytes(), b"AEP")
            self.assertEqual(r_out, stage / "render.mov")
        finally:
            import shutil
            shutil.rmtree(stage, ignore_errors=True)

    def test_no_root_gives_a_precise_how(self):
        from lib import ae_render
        aep = self.tmp / "مشروع.aep"
        aep.write_bytes(b"AEP")
        with mock.patch.object(ae_render.plat, "IS_WIN", True), \
                mock.patch.object(ae_render.tempfile, "gettempdir", return_value=self.ARABIC_TEMP), \
                mock.patch.object(ae_render, "ascii_stage_roots", return_value=[]):
            with self.assertRaises(ae_render.StageError) as cm:
                ae_render.stage_ascii(aep)
        msg = str(cm.exception)
        self.assertIn("setx WHYNOT_HOME", msg)
        self.assertIn("TEMP", msg)


class TestRunDecodesLeniently(unittest.TestCase):
    """D minor 5: tool output that is not valid UTF-8 (a localised Windows tool, a file name in the ANSI code page)
    never raises UnicodeDecodeError in common.run."""

    def test_invalid_bytes_are_replaced(self):
        p = common.run([sys.executable, "-c", "import sys; sys.stdout.buffer.write(bytes([0x81, 0x8d]) + b' ok')"], timeout=60)
        self.assertIn("ok", p.stdout)
        self.assertIn("\ufffd", p.stdout)


class TestFootageNameMatching(unittest.TestCase):
    """D minor 7: the plan finds THIS video's preflight entry when the names differ only in Unicode form (macOS
    writes NFD) or, on Windows, in case."""

    def test_nfd_and_nfc_names_match(self):
        import unicodedata
        from lib import plan
        nfd = unicodedata.normalize("NFD", "data/Raw/café مقابلة.mp4")
        nfc = unicodedata.normalize("NFC", "data/Raw/café مقابلة.mp4")
        self.assertNotEqual(nfd, nfc)
        pre = {"files": [{"path": "data/Raw/other.mp4", "video": {"w": 1}}, {"path": nfd, "video": {"w": 2}}]}
        self.assertEqual(plan.main_video(pre, nfc), {"w": 2})
        self.assertTrue(plan.same_footage_name(nfd, nfc))
        self.assertFalse(plan.same_footage_name("data/Raw/a.mp4", "data/Raw/b.mp4"))

    @unittest.skipUnless(IS_WIN, "case-insensitive names: Windows")
    def test_case_differs_on_windows(self):
        from lib import plan
        pre = {"files": [{"path": "data/Raw/C0239.MP4", "video": {"w": 3}}]}
        self.assertEqual(plan.main_video(pre, "data/Raw/c0239.mp4"), {"w": 3})


class TestEmptyFaceClassifier(unittest.TestCase):
    """D minor 8: OpenCV's face model not loading (a non-ASCII path) gives no faces and a note, never a crash."""

    def fake_cv2(self):
        class Err(Exception):
            pass

        class Cascade:
            def __init__(self, path):
                self.path = path

            def empty(self):
                return True

            def detectMultiScale(self, *a, **k):
                raise Err("(-215:Assertion failed) !empty() in function 'detectMultiScale'")
        return types.SimpleNamespace(CascadeClassifier=Cascade, error=Err,
                                     data=types.SimpleNamespace(haarcascades="C:/يونس/cv2/data/"),
                                     resize=lambda g, size: g, flip=lambda g, k: g)

    def test_returns_no_faces_and_a_note(self):
        try:
            from PIL import Image
            import numpy  # noqa: F401
        except ImportError:
            self.skipTest("PIL / numpy not in this interpreter")
        from lib import shots
        notes = set()
        with mock.patch.dict(sys.modules, {"cv2": self.fake_cv2()}):
            self.assertEqual(shots._boxes_opencv(Image.new("RGB", (64, 64)), notes), [])
            self.assertEqual(shots._boxes_opencv(Image.new("RGB", (64, 64))), [])
        self.assertEqual(len(notes), 1)
        self.assertIn("face model", next(iter(notes)))


if __name__ == "__main__":
    unittest.main()
