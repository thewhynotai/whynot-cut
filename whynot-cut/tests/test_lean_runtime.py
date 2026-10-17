# SPDX-License-Identifier: GPL-3.0-or-later
# © 2026 The Why Not AI (thewhynot.ai)
"""3.0 Phase 4 T4.11 (G13-RUN, engine part): background `reel` work at BelowNormal (a product setting, on by
default), GPU batches that fit the free VRAM (room left for Premiere), and Whisper released after every job.

No test lowers the test runner's own priority: every priority call here gets a fake setter, and the one real check
runs in a child python (tearDownModule asserts the runner's priority is unchanged). The suite runs with
WHYNOT_PRIORITY=normal (tests/_isolation.py) and WHYNOT_ACCEL=off, so no test reaches the GPU.
Case list: the lane's work/t411/cases.md (A-H).
Run:  bash tools/test.sh -p test_lean_runtime.py
"""
import sys as _sys
_sys.dont_write_bytecode = True  # keep the plugin folder free of __pycache__
import _isolation  # noqa: F401,E402  G79: sandbox the engine home first (tests/_isolation.py)
import contextlib
import gc
import io
import os
import subprocess
import sys
import tempfile
import textwrap
import unittest
import weakref
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import numpy as np

SK = Path(__file__).resolve().parents[1]
ENGINE = SK / "engine" / "reel"
if str(ENGINE) not in sys.path:
    sys.path.insert(0, str(ENGINE))

from lib import priority  # noqa: E402
from lib import settings as S  # noqa: E402
from lib import whisper_backends as WB  # noqa: E402


def _runner_priority():
    """The test runner's own priority class (Windows) or niceness (POSIX), read only."""
    if os.name == "nt":
        import ctypes
        k = ctypes.windll.kernel32
        k.GetCurrentProcess.restype = ctypes.c_void_p
        k.GetPriorityClass.argtypes = [ctypes.c_void_p]
        return k.GetPriorityClass(k.GetCurrentProcess())
    return os.nice(0)


_AT_IMPORT = _runner_priority()


def tearDownModule():  # noqa: N802  A16: nothing in this file lowered the runner itself
    now = _runner_priority()
    if now != _AT_IMPORT:
        raise AssertionError(f"the test runner's priority changed: {_AT_IMPORT} -> {now}")


@contextlib.contextmanager
def quiet():
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        yield


# --------------------------------------------------------------------------- A. priority.apply
class TestApply(unittest.TestCase):
    def test_windows_default_is_below_normal(self):
        calls = []
        self.assertEqual(priority.apply(None, os_name="nt", setter=calls.append, env={}), "below_normal")
        self.assertEqual(calls, [0x4000])

    def test_posix_nice_10(self):
        calls = []
        self.assertEqual(priority.apply(None, os_name="posix", setter=calls.append, env={}), "below_normal")
        self.assertEqual(calls, [10])

    def test_posix_is_idempotent_and_never_raises_priority(self):
        for cur, want in ((0, [10]), (4, [6]), (10, []), (19, [])):
            calls = []
            r = priority.apply(None, os_name="posix", setter=calls.append, getter=lambda c=cur: c, env={})
            self.assertEqual((r, calls), ("below_normal", want), cur)

    def test_windows_already_lower_is_left_alone(self):
        for cur in (0x40, 0x4000):                 # IDLE / BELOW_NORMAL inherited from a parent
            calls = []
            r = priority.apply(None, os_name="nt", setter=calls.append, getter=lambda c=cur: c, env={})
            self.assertEqual((r, calls), ("below_normal", []), hex(cur))
        calls = []
        priority.apply(None, os_name="nt", setter=calls.append, getter=lambda: 0x20, env={})       # NORMAL
        self.assertEqual(calls, [0x4000])

    def test_setting_normal_and_env_override(self):
        calls = []
        self.assertEqual(priority.apply("normal", os_name="nt", setter=calls.append, env={}), "normal")
        self.assertEqual(priority.apply("below_normal", os_name="nt", setter=calls.append,
                                        env={"WHYNOT_PRIORITY": "normal"}), "normal")
        self.assertEqual(calls, [])
        self.assertEqual(priority.apply("normal", os_name="nt", setter=calls.append,
                                        env={"WHYNOT_PRIORITY": " Below_Normal "}), "below_normal")
        self.assertEqual(calls, [0x4000])

    def test_invalid_values_fall_back_to_the_default_never_raise_priority(self):
        for env in ({"WHYNOT_PRIORITY": "high"}, {"WHYNOT_PRIORITY": ""}, {"WHYNOT_PRIORITY": "realtime"}):
            calls = []
            self.assertEqual(priority.apply("below_normal", os_name="nt", setter=calls.append, env=env), "below_normal")
            self.assertEqual(calls, [0x4000])
        for bad in ("idle", 3, True, "", "HIGH"):
            calls = []
            self.assertEqual(priority.apply(bad, os_name="posix", setter=calls.append, env={}), "below_normal", bad)
            self.assertEqual(calls, [10])

    def test_setting_read_from_preferences_when_not_given(self):
        calls = []
        with mock.patch.object(S, "load", return_value=dict(S.DEFAULTS, background_priority="normal")):
            self.assertEqual(priority.apply(None, os_name="nt", setter=calls.append, env={}), "normal")
        with mock.patch.object(S, "load", side_effect=ValueError("corrupt")):
            self.assertEqual(priority.apply(None, os_name="nt", setter=calls.append, env={}), "below_normal")
        self.assertEqual(calls, [0x4000])

    def test_refusal_is_silent(self):
        def boom(_v):
            raise OSError("refused")
        for err in (OSError("x"), PermissionError("x"), AttributeError("no os.nice")):
            def setter(_v, e=err):
                raise e
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                self.assertEqual(priority.apply(None, os_name="posix", setter=setter, env={}), "unsupported")
                self.assertEqual(priority.apply(None, os_name="nt", setter=boom, env={}), "unsupported")
            self.assertEqual(out.getvalue(), "")                 # stdout is the CLI's JSON

    def test_unknown_os_is_unsupported(self):
        calls = []
        for osn in ("java", "riscos"):
            self.assertEqual(priority.apply(None, os_name=osn, setter=calls.append, env={}), "unsupported")
        self.assertEqual(calls, [])

    def test_windows_real_setter_call_shape_and_refusal(self):
        seen = []

        class K32:
            def GetCurrentProcess(self):  # noqa: N802
                return -1

            def SetPriorityClass(self, h, cls):  # noqa: N802
                seen.append((h, cls))
                return self.ret
        k = K32()
        k.ret = 1
        priority._win_set(0x4000, kernel32=k)
        self.assertEqual(seen, [(-1, 0x4000)])
        k.ret = 0
        with self.assertRaises(OSError):                        # a 0 return is a refusal -> apply() says unsupported
            priority._win_set(0x4000, kernel32=k)

    def test_the_suite_runs_at_normal(self):
        self.assertEqual(os.environ.get("WHYNOT_PRIORITY"), "normal")
        calls = []
        self.assertEqual(priority.apply(None, os_name="nt", setter=calls.append), "normal")   # real os.environ
        self.assertEqual(calls, [])

    def test_children_inherit_the_lowered_priority(self):
        """A15, real OS: a child python lowers itself (the product default, no WHYNOT_PRIORITY), then starts a
        grandchild that reports its own priority. The runner is never touched."""
        code = textwrap.dedent(f"""
            import os, subprocess, sys
            sys.path.insert(0, {str(ENGINE)!r})
            from lib import priority
            print(priority.apply("below_normal"))
            probe = ("import os, ctypes; k = ctypes.windll.kernel32; k.GetCurrentProcess.restype = ctypes.c_void_p; "
                     "k.GetPriorityClass.argtypes = [ctypes.c_void_p]; print(k.GetPriorityClass(k.GetCurrentProcess()))"
                     if os.name == "nt" else "import os; print(os.nice(0))")
            print(subprocess.run([sys.executable, "-c", probe], capture_output=True, text=True).stdout.strip())
        """)
        env = {k: v for k, v in os.environ.items() if k != "WHYNOT_PRIORITY"}
        r = subprocess.run([sys.executable, "-I", "-c", code], capture_output=True, text=True, env=env, timeout=60)
        self.assertEqual(r.returncode, 0, r.stderr)
        state, child = r.stdout.split()
        self.assertEqual(state, "below_normal")
        self.assertEqual(int(child), 0x4000 if os.name == "nt" else 10)


# --------------------------------------------------------------------------- C. the setting
class TestSetting(unittest.TestCase):
    def test_default_and_choices(self):
        self.assertEqual(S.DEFAULTS["background_priority"], "below_normal")
        self.assertEqual(S.CHOICES["background_priority"], {"below_normal", "normal"})

    def test_settings_rejects_other_values(self):
        self.assertEqual(S.check("background_priority", "normal"), ("normal", None))
        v, why = S.check("background_priority", "fast")
        self.assertIsNone(v)
        self.assertIn("is not one of", why)

    def test_file_layer_and_round_trip(self):
        d = Path(tempfile.mkdtemp())
        f = S.save(d / ".claude" / S.FILE, {"background_priority": "normal"})
        self.assertIn("background_priority", f.read_text(encoding="utf-8"))
        got = S.load(d)
        self.assertEqual(got["background_priority"], "normal")
        self.assertEqual(got["_sources"]["background_priority"], "client")


# --------------------------------------------------------------------------- D. vram_free_mb
def _proc(stdout="", rc=0):
    return subprocess.CompletedProcess([], rc, stdout=stdout, stderr="")


class TestVramFree(unittest.TestCase):
    def setUp(self):
        p = mock.patch.dict(os.environ, {"WHYNOT_ACCEL": "auto"})      # the suite's "off" queries nothing (below)
        p.start()
        self.addCleanup(p.stop)

    def test_acceleration_off_queries_nothing(self):
        started = []
        with mock.patch.dict(os.environ, {"WHYNOT_ACCEL": "off"}), \
                mock.patch("lib.accel._nvidia_smi", return_value=r"C:\Windows\System32\nvidia-smi.exe"):
            self.assertIsNone(WB.vram_free_mb(runner=lambda *a, **k: started.append(a) or _proc("6000")))
        self.assertEqual(started, [])

    def test_parse(self):
        seen = []

        def run(argv, **kw):
            seen.append((argv, kw))
            return _proc(self.out)
        with mock.patch("lib.accel._nvidia_smi", return_value=r"C:\Windows\System32\nvidia-smi.exe"):
            for out, want in (("6123\n", 6123), ("6123\n512\n", 6123), (" 812 \r\n", 812), ("[N/A]\n", None),
                              ("[Not Supported]", None), ("", None), ("garbage", None), ("-5", None), ("1234.5", 1234)):
                self.out = out
                self.assertEqual(WB.vram_free_mb(runner=run), want, out)
        argv, kw = seen[0]
        self.assertEqual(argv, [r"C:\Windows\System32\nvidia-smi.exe", "--query-gpu=memory.free",
                                "--format=csv,noheader,nounits"])
        self.assertEqual(kw.get("timeout"), 10)

    def test_failures_are_none(self):
        def raises(e):
            def run(argv, **kw):
                raise e
            return run
        with mock.patch("lib.accel._nvidia_smi", return_value="/usr/bin/nvidia-smi"):
            self.assertIsNone(WB.vram_free_mb(runner=lambda a, **k: _proc("6000", rc=9)))
            for e in (FileNotFoundError(), PermissionError(), subprocess.TimeoutExpired("x", 10), OSError()):
                self.assertIsNone(WB.vram_free_mb(runner=raises(e)))

    def test_no_nvidia_smi_starts_nothing(self):
        started = []
        with mock.patch("lib.accel._nvidia_smi", return_value=None), \
                mock.patch.object(subprocess, "run", side_effect=lambda *a, **k: started.append(a)):
            self.assertIsNone(WB.vram_free_mb())
        self.assertEqual(started, [])


# --------------------------------------------------------------------------- E. fit_batch
class TestFitBatch(unittest.TestCase):
    def setUp(self):
        p = [mock.patch.object(WB, "MODEL_VRAM_MB", {("m", "float16"): 1000, ("large-v3", "float16"): 1000}),
             mock.patch.object(WB, "PER_BATCH_MB", 100), mock.patch.object(WB, "HEADROOM_MB", 500)]
        for x in p:
            x.start()
            self.addCleanup(x.stop)

    def test_fit_batch(self):
        self.assertEqual(WB.fit_batch("m", "float16", 4, 2000), (4, "cuda"))
        self.assertEqual(WB.fit_batch("m", "float16", 4, 1700), (2, "cuda"))
        self.assertEqual(WB.fit_batch("m", "float16", 4, 1600), (0, "cuda"))
        self.assertEqual(WB.fit_batch("m", "float16", 4, 1500), (0, "cpu"))
        self.assertEqual(WB.fit_batch("m", "float16", 4, None), (4, "cuda"))

    def test_exactly_enough_and_one_short(self):
        self.assertEqual(WB.fit_batch("m", "float16", 3, 1800), (3, "cuda"))      # need(3) = 1800: fits
        self.assertEqual(WB.fit_batch("m", "float16", 3, 1799), (2, "cuda"))

    def test_zero_negative_and_sequential(self):
        self.assertEqual(WB.fit_batch("m", "float16", 4, 0), (0, "cpu"))
        self.assertEqual(WB.fit_batch("m", "float16", 4, -50), (0, "cpu"))
        for conf in (0, 1, -3, None):
            self.assertEqual(WB.fit_batch("m", "float16", conf, 1600), (0, "cuda"), conf)
            self.assertEqual(WB.fit_batch("m", "float16", conf, 1599), (0, "cpu"), conf)
            self.assertEqual(WB.fit_batch("m", "float16", conf, None), (0, "cuda"), conf)

    def test_never_above_configured(self):
        self.assertEqual(WB.fit_batch("m", "float16", 2, 99999), (2, "cuda"))
        self.assertEqual(WB.fit_batch("m", "float16", 16, 99999), (16, "cuda"))

    def test_unknown_model_or_type_is_the_conservative_row(self):
        for model, ct in (("medium", "float16"), ("m", "int8"), ("/snap/x", "bfloat16")):
            self.assertEqual(WB.fit_batch(model, ct, 4, 1700), (2, "cuda"), (model, ct))

    def test_shipped_constants(self):
        with mock.patch.object(WB, "MODEL_VRAM_MB", WB._MODEL_VRAM_MB_START), \
                mock.patch.object(WB, "PER_BATCH_MB", 700), mock.patch.object(WB, "HEADROOM_MB", 1536):
            self.assertEqual(WB.MODEL_VRAM_MB[("large-v3", "float16")], 3300)
            self.assertEqual(WB.MODEL_VRAM_MB[("large-v3-turbo", "int8_float16")], 1100)
            # an 8 GB laptop card with nothing else on it (~7.5 GB free): batch 3 of 4 fits for large-v3 fp16
            self.assertEqual(WB.fit_batch("large-v3", "float16", 4, 7600), (3, "cuda"))


# --------------------------------------------------------------------------- F. the runner loads where it fits
class FakeModel:
    def transcribe(self, audio, **kw):
        return iter([]), SimpleNamespace(language="ar", language_probability=0.9)


class TestRunnerFit(unittest.TestCase):
    def go(self, free, tries=(("cuda", "float16"),), batch=4, vad=True, device=None):
        loads, queries, logs = [], [], []

        def load(model, compute_type="int8", device=None):
            loads.append(device)
            return FakeModel(), ("cpu" if device == "cpu" else "cuda"), ("int8" if device == "cpu" else "float16")

        def query(runner=None):
            queries.append(1)
            return free
        with mock.patch.object(WB, "load_ct2", side_effect=load), \
                mock.patch.object(WB, "_device_tries", lambda cfg, d, ct: [("cpu", ct)] if d == "cpu" else list(tries)), \
                mock.patch.object(WB, "vram_free_mb", side_effect=query), \
                mock.patch.object(WB, "log", side_effect=lambda to, msg: logs.append(msg)), \
                mock.patch("faster_whisper.BatchedInferencePipeline", lambda m: ("pipeline", m), create=True):
            run = WB.make_runner("large-v3", vad=vad, backend="ct2", batch_size=batch, device=device)
            self.assertEqual(queries, [])                  # H02: nothing is queried until the job runs (inside its slot)
            run.load()
        return run, loads, queries, logs

    def setUp(self):
        import importlib.util
        if importlib.util.find_spec("faster_whisper") is None:
            sys.modules.setdefault("faster_whisper", SimpleNamespace(BatchedInferencePipeline=lambda m: ("pipeline", m)))

    def test_fits_on_the_gpu(self):
        run, loads, queries, _ = self.go(99999)
        self.assertEqual((loads, queries), ([None], [1]))
        self.assertEqual((run.state["device"], run.state["batch_size"]), ("cuda", 4))

    def test_smaller_batch_when_vram_is_tight(self):
        with mock.patch.object(WB, "MODEL_VRAM_MB", {("large-v3", "float16"): 1000}), \
                mock.patch.object(WB, "PER_BATCH_MB", 100), mock.patch.object(WB, "HEADROOM_MB", 500):
            run, loads, _, _ = self.go(1700)
        self.assertEqual((run.state["device"], run.state["batch_size"]), ("cuda", 2))

    def test_busy_gpu_goes_cpu_with_message(self):
        run, loads, queries, logs = self.go(800)
        self.assertEqual(loads, ["cpu"])                   # CUDA never tried: no OOM loop
        self.assertEqual(queries, [1])
        self.assertEqual(run.state["device"], "cpu")
        self.assertEqual(run.state["fallback_from"]["device"], "cuda")
        self.assertTrue(any("The graphics card is busy (0.8 GB free): transcribing on the processor" in m for m in logs),
                        logs)

    def test_unknown_free_vram_keeps_todays_batch(self):
        run, loads, queries, _ = self.go(None)
        self.assertEqual((loads, run.state["batch_size"]), ([None], 4))

    def test_cpu_device_never_queries(self):
        run, loads, queries, _ = self.go(99999, device="cpu")
        self.assertEqual((loads, queries), (["cpu"], []))
        run, loads, queries, _ = self.go(99999, tries=(("cpu", "int8"),))
        self.assertEqual(queries, [])

    def test_sequential_short_clip_on_a_busy_gpu_goes_cpu(self):
        run, loads, _, _ = self.go(800, vad=False)
        self.assertEqual(loads, ["cpu"])

    def test_degrade_to_cpu_does_not_query_again(self):
        run, loads, queries, _ = self.go(99999)
        with mock.patch.object(WB, "load_ct2", return_value=(FakeModel(), "cpu", "int8")), \
                mock.patch.object(WB, "vram_free_mb", side_effect=AssertionError("queried again")), quiet():
            run.state["batch_size"] = 0
            run.state["pipeline"] = None
            WB_log = []
            with mock.patch.object(WB, "log", side_effect=lambda to, m: WB_log.append(m)):
                # a non-OOM GPU failure: straight to the CPU
                st = run.state
                st["model"] = SimpleNamespace(transcribe=mock.Mock(side_effect=RuntimeError("cuda failure")))
                r = run([0.0] * 1600, 0, "ar", None)
        self.assertEqual(run.state["device"], "cpu")
        self.assertEqual(r["language"], "ar")


# --------------------------------------------------------------------------- G. release
class Big(FakeModel):
    """A stand-in model: weakref-able, decodes nothing."""


class TestRelease(unittest.TestCase):
    def runner(self):
        with mock.patch.object(WB, "load_ct2", side_effect=lambda *a, **k: (Big(), "cpu", "int8")), \
                mock.patch.object(WB, "_device_tries", lambda cfg, d, ct: [("cpu", ct)]), quiet():
            run = WB.make_runner("large-v3", vad=False, backend="ct2", batch_size=0)
            run.load()
        return run

    def test_release_drops_the_model(self):
        run = self.runner()
        ref = weakref.ref(run.state["model"])
        run.state["pipeline"] = Big()
        pref = weakref.ref(run.state["pipeline"])
        run.release()
        self.assertIsNone(ref())
        self.assertIsNone(pref())
        for k in ("device", "compute_type", "batch_size", "redecoded"):
            self.assertIn(k, run.state)                 # transcribe() reads them after the decode
        self.assertNotIn("model", run.state)

    def test_release_is_idempotent_and_reload_works(self):
        run = self.runner()
        run.release()
        run.release()
        with mock.patch.object(WB, "load_ct2", side_effect=lambda *a, **k: (FakeModel(), "cpu", "int8")), quiet():
            r = run([0.0] * 1600, 0, "ar", None)
        self.assertIn("model", run.state)
        self.assertEqual(r["language"], "ar")
        with quiet():
            fresh = WB.make_runner("large-v3", vad=False, backend="ct2", batch_size=0)
        fresh.release()                                  # before any load: no error

    def test_mlx_release(self):
        holder = SimpleNamespace(model=Big(), model_path="x")
        fake_mlx = SimpleNamespace(transcribe=lambda *a, **k: {}, transcribe_module=None)
        cleared = []
        with mock.patch.object(WB, "mlx_model_source", return_value="src"), quiet():
            run = WB._mlx_runner("large-v3", False, None)
            run.state["mlx"] = fake_mlx
        ref = weakref.ref(holder.model)
        with mock.patch.object(WB, "_mlx_holders", return_value=[holder]), \
                mock.patch.object(WB, "_mlx_clear_cache", side_effect=lambda: cleared.append(1)):
            run.release()
            run.release()
        self.assertNotIn("mlx", run.state)
        self.assertIsNone(holder.model)
        self.assertIsNone(ref())
        self.assertTrue(cleared)

    def test_bench_releases_after_measuring(self):
        home = Path(tempfile.mkdtemp(prefix="whynot-t411-home-"))
        env = mock.patch.dict(os.environ, {"WHYNOT_HOME": str(home)})      # the bench cache goes to a temp home
        env.start()
        self.addCleanup(env.stop)
        made = []
        real = WB.make_runner

        def factory(*a, **k):
            with mock.patch.object(WB, "make_runner", real):
                run = self.runner()
            made.append(weakref.ref(run.state["model"]))
            return run
        with mock.patch.object(WB, "make_runner", side_effect=factory), \
                mock.patch.object(WB, "load_ct2", side_effect=lambda *a, **k: (FakeModel(), "cpu", "int8")), quiet():
            WB.bench([0.0] * 16000, model="large-v3", backend="ct2")
        gc.collect()
        self.assertIsNone(made[0]())


# --------------------------------------------------------------------------- G/H. transcribe() and relisten()
class _Proj(unittest.TestCase):
    def setUp(self):
        from lib.common import Paths
        self.tmp = Path(tempfile.mkdtemp(prefix="whynot-t411-"))
        root = self.tmp / "client"
        (root / "assets").mkdir(parents=True)
        (root / "data").mkdir()
        self.p = Paths(root, "V1")
        self.p.p("02_transcription").mkdir(parents=True, exist_ok=True)


class TestTranscribeReleases(_Proj):
    def fake_runner(self, events, fail=None):
        def run(audio, start_ms, language, prompt):
            events.append("decode")
            if fail:
                raise fail
            return {"segments": [], "words": [], "language": "ar", "language_probability": 0.9}
        run.backend, run.state = "ct2", {"device": "cpu", "compute_type": "int8", "batch_size": 0}
        run.release = lambda: events.append("release")
        return run

    def go(self, events, fail=None):
        from lib import gpu_lock
        from lib import transcribe as T

        @contextlib.contextmanager
        def slot(what="transcribe", **kw):
            events.append("slot-in")
            try:
                yield "cpu"
            finally:
                events.append("slot-out")
        runs = []

        def factory(*a, **k):
            r = self.fake_runner(events, fail)
            runs.append(r)
            return r
        with mock.patch.object(T, "extract_audio", side_effect=lambda src, dst, rng=None: dst), \
                mock.patch.object(T, "whisper_audio", return_value=[0.0] * 16000), \
                mock.patch.object(T, "finalize", return_value={"ok": True}), \
                mock.patch.object(gpu_lock, "whisper_slot", side_effect=slot), \
                mock.patch.object(WB, "make_runner", side_effect=factory), quiet():
            for name in ("transcript", "words"):
                (self.p.p("02_transcription") / f"{name}.json").write_text("{}", encoding="utf-8")
            return T.transcribe(self.p, self.tmp / "clip.mov", "large-v3")

    def test_release_on_success_inside_the_slot(self):
        ev = []
        self.go(ev)
        self.assertEqual(ev, ["slot-in", "decode", "release", "slot-out"])

    def test_transcribe_releases_on_error_too(self):
        for err in (RuntimeError("decode failed"), KeyboardInterrupt()):
            ev = []
            with self.assertRaises(type(err)):
                self.go(ev, fail=err)
            self.assertEqual(ev, ["slot-in", "decode", "release", "slot-out"], type(err).__name__)

    def test_two_jobs_two_loads_first_released_before_the_second(self):
        ev = []
        self.go(ev)
        self.go(ev)
        self.assertEqual(ev, ["slot-in", "decode", "release", "slot-out"] * 2)

    def test_a_runner_without_release_still_works(self):
        from lib import gpu_lock
        from lib import transcribe as T

        def run(audio, start_ms, language, prompt):
            return {"segments": [], "words": [], "language": "ar", "language_probability": 0.9}
        run.backend = "ct2"
        with mock.patch.object(T, "extract_audio", side_effect=lambda src, dst, rng=None: dst), \
                mock.patch.object(T, "whisper_audio", return_value=[0.0] * 16000), \
                mock.patch.object(T, "finalize", return_value={"ok": True}), \
                mock.patch.object(gpu_lock, "whisper_slot", side_effect=lambda *a, **k: contextlib.nullcontext("cpu")), \
                mock.patch.object(WB, "make_runner", return_value=run), quiet():
            for name in ("transcript", "words"):
                (self.p.p("02_transcription") / f"{name}.json").write_text("{}", encoding="utf-8")
            self.assertEqual(T.transcribe(self.p, self.tmp / "clip.mov", "large-v3")["ok"], True)


class TestRelistenReleases(_Proj):
    def go(self, holder, fail_after=False):
        import json
        from lib import transcribe as T
        out = self.p.p("02_transcription")
        (out / "words.json").write_text(json.dumps({"words": [{"id": 1, "word": "x", "start_ms": 1000, "end_ms": 1400,
                                                               "flagged": True}]}), encoding="utf-8")
        (out / "transcript.json").write_text(json.dumps({"meta": {"language": "ar"}}), encoding="utf-8")
        boom = mock.patch.object(T, "write_json", side_effect=OSError("disk full")) if fail_after else contextlib.nullcontext()
        with mock.patch.object(T, "whisper_audio", return_value=[0.0] * 16000 * 5),                 mock.patch.object(T, "whisper_model", side_effect=lambda *a, **k: (holder.pop(), "cpu", "int8")),                 boom, quiet():
            return T.relisten(self.p)

    class M(Big):
        def transcribe(self, clip, **kw):
            return [SimpleNamespace(text="x")], None

    def test_model_dropped_on_success(self):
        holder = [self.M()]
        ref = weakref.ref(holder[0])
        self.go(holder)
        gc.collect()
        self.assertIsNone(ref())

    def test_model_dropped_on_error_even_while_the_traceback_lives(self):
        holder = [self.M()]
        ref = weakref.ref(holder[0])
        try:
            self.go(holder, fail_after=True)
        except OSError:
            gc.collect()
            self.assertIsNone(ref())                   # relisten's frame (in the traceback) no longer holds the model
        else:
            self.fail("no error")

# --------------------------------------------------------------------------- independent review round 1
class TestReview1(unittest.TestCase):
    """What the first independent review found missing."""

    def fit_runner(self, free, configured=4):
        with mock.patch.object(WB, "MODEL_VRAM_MB", {("large-v3", "float16"): 1000}), \
                mock.patch.object(WB, "PER_BATCH_MB", 100), mock.patch.object(WB, "HEADROOM_MB", 500), \
                mock.patch.object(WB, "load_ct2", side_effect=lambda *a, **k: (FakeModel(), "cuda", "float16")), \
                mock.patch.object(WB, "_device_tries", lambda cfg, d, ct: [("cpu", ct)] if d == "cpu" else [("cuda", "float16")]), \
                mock.patch.object(WB, "vram_free_mb", return_value=free), \
                mock.patch("faster_whisper.BatchedInferencePipeline", lambda m: ("pipeline", m), create=True), quiet():
            run = WB.make_runner("large-v3", vad=True, backend="ct2", batch_size=configured)
            want = run.signature()
            run.load()
        return run, want

    def test_p1_a_smaller_fitted_batch_marks_the_wanted_decoder(self):
        run, want = self.fit_runner(1800)                              # fits 3 of 4
        self.assertEqual(run.state["batch_size"], 3)
        self.assertEqual(want, {"device": "cuda", "batch_size": 4, "vad": True})
        self.assertEqual(run.state["fallback_from"], want)            # resumed chunks match the run that wanted 4
        run, want = self.fit_runner(99999)                             # the full batch fits: no fallback mark
        self.assertNotIn("fallback_from", run.state)

    def test_p1_resume_after_a_different_fit_reuses_the_checkpoints(self):
        from lib.episode import _decoder_matches
        first, want = self.fit_runner(1800)                            # session 1: 3 of 4 (Premiere open)
        rec = {"model": "large-v3", "prompt": None, "backend": "ct2", "decoder": first.signature(),
               "fallback_from": first.state.get("fallback_from")}
        second, want2 = self.fit_runner(1700)                          # session 2: 2 of 4
        self.assertEqual(want, want2)
        self.assertTrue(_decoder_matches(rec, "large-v3", None, "ct2", want2))

    def test_p2_the_test_runner_is_never_lowered_by_a_real_call(self):
        # in a process that imported tests/_isolation, a real (not injected) priority call is a no-op, even with the
        # environment cleared (mock.patch.dict(os.environ, clear=True) + cli.main in other test files)
        with mock.patch.dict(os.environ, {}, clear=True), \
                mock.patch.object(priority, "_win_set", side_effect=AssertionError("would lower the runner")), \
                mock.patch.object(os, "nice", side_effect=AssertionError("would lower the runner"), create=True):
            self.assertEqual(priority.apply("below_normal"), "normal")

    def test_p3_chunked_long_clip_keeps_its_meta(self):
        from lib import gpu_lock
        from lib import transcribe as T
        from lib.common import Paths
        tmp = Path(tempfile.mkdtemp(prefix="whynot-t411c-"))
        (tmp / "c" / "assets").mkdir(parents=True)
        (tmp / "c" / "data").mkdir()
        p = Paths(tmp / "c", "V1")
        out = p.p("02_transcription")
        out.mkdir(parents=True)
        for n in ("transcript", "words"):
            (out / f"{n}.json").write_text("{}", encoding="utf-8")
        ev, metas = [], []

        def run(audio, start_ms, language, prompt):
            raise AssertionError("the chunk runner decodes, not a single pass")
        run.backend, run.state = "ct2", {"device": "cuda", "compute_type": "float16", "batch_size": 4, "vad": True}
        run.release = lambda: ev.append("release")
        done = {"results": [{"x": 1}], "language": "ar", "language_probability": 0.8, "ran": 2,
                "decoders": ["cuda/batch4/vad"], "redecoded": 1}
        with mock.patch.object(T, "extract_audio", side_effect=lambda src, dst, rng=None: dst), \
                mock.patch.object(T, "whisper_audio", return_value=np.zeros(16000 * 700, np.float32)), \
                mock.patch.object(T, "finalize", side_effect=lambda paths, meta, segs, words: metas.append(meta) or {"ok": True}), \
                mock.patch.object(gpu_lock, "whisper_slot", side_effect=lambda *a, **k: contextlib.nullcontext("cuda")), \
                mock.patch.object(WB, "make_runner", return_value=run), \
                mock.patch("lib.common.sha1_head", return_value="h"), \
                mock.patch("lib.episode.chunk_plan", return_value={"chunks": [(0, 1), (1, 2)]}), \
                mock.patch("lib.episode.run_chunks", side_effect=lambda *a, **k: ev.append("chunks") or done), \
                mock.patch("lib.episode.stitch", return_value=(["s"], ["w"])), quiet():
            r = T.transcribe(p, tmp / "clip.mov", "large-v3")
        self.assertEqual(ev, ["chunks", "release"])
        m = metas[0]
        self.assertEqual((r["chunks"], r["chunks_run"]), (2, 2))
        self.assertEqual((m["chunks"], m["vad"], m["decoders"], m["mixed_decoders"], m["redecoded_segments"]),
                         (2, True, ["cuda/batch4/vad"], False, 1))
        self.assertEqual((m["language"], m["language_probability"], m["device"], m["batch_size"]), ("ar", 0.8, "cuda", 4))
        self.assertIn("gpu_wait_s", m)

    def test_p3_degrade_to_cpu_after_a_gpu_failure_does_not_query_again(self):
        loads, queries = [], []

        class GpuFails(FakeModel):
            def transcribe(self, audio, **kw):
                raise RuntimeError("CUBLAS_STATUS_EXECUTION_FAILED")

        def load(model, compute_type="int8", device=None):
            loads.append(device)
            return (FakeModel(), "cpu", "int8") if device == "cpu" else (GpuFails(), "cuda", "float16")
        with mock.patch.object(WB, "load_ct2", side_effect=load), \
                mock.patch.object(WB, "_device_tries", lambda cfg, d, ct: [("cpu", ct)] if d == "cpu" else [("cuda", "float16")]), \
                mock.patch.object(WB, "vram_free_mb", side_effect=lambda *a, **k: queries.append(1) or 99999), quiet():
            run = WB.make_runner("large-v3", vad=False, backend="ct2", batch_size=0)
            r = run(np.zeros(1600, np.float32), 0, "ar", None)
        self.assertEqual((loads, queries), ([None, "cpu"], [1]))
        self.assertEqual(run.state["device"], "cpu")
        self.assertEqual(r["language"], "ar")

    def test_p3_relisten_drops_a_generator_holding_the_model(self):
        import json
        from lib import transcribe as T
        from lib.common import Paths
        tmp = Path(tempfile.mkdtemp(prefix="whynot-t411r-"))
        (tmp / "c" / "assets").mkdir(parents=True)
        (tmp / "c" / "data").mkdir()
        p = Paths(tmp / "c", "V1")
        out = p.p("02_transcription")
        out.mkdir(parents=True)
        (out / "words.json").write_text(json.dumps({"words": [{"id": 1, "word": "x", "start_ms": 1000, "end_ms": 1400,
                                                               "flagged": True}]}), encoding="utf-8")
        (out / "transcript.json").write_text(json.dumps({"meta": {"language": "ar"}}), encoding="utf-8")

        class GenModel(Big):
            def transcribe(self, clip, **kw):
                def gen(model=self):              # like faster-whisper: the lazy generator holds the model
                    yield SimpleNamespace(text="x")
                    raise RuntimeError("decode failed mid-stream")
                return gen(), None
        holder = [GenModel()]
        ref = weakref.ref(holder[0])
        with mock.patch.object(T, "whisper_audio", return_value=[0.0] * 16000 * 5), \
                mock.patch.object(T, "whisper_model", side_effect=lambda *a, **k: (holder.pop(), "cpu", "int8")), quiet():
            err = None
            try:
                T.relisten(p)
            except RuntimeError as e:      # (assertRaises would drop the traceback this test inspects)
                err = e
        self.assertIsNotNone(err)
        # while the error is alive, relisten's own frame (in the traceback) no longer holds the model, the segment
        # generator or the clip; the generator's frame still does (an error raised inside it), and nothing else does
        tb, frame = err.__traceback__, None
        while tb is not None:
            if tb.tb_frame.f_code.co_name == "relisten":
                frame = tb.tb_frame
            tb = tb.tb_next
        self.assertIsNotNone(frame)
        self.assertEqual([frame.f_locals.get(k) for k in ("model", "segs", "clip")], [None, None, None])
        del err, tb, frame
        gc.collect()
        self.assertIsNone(ref())


# --------------------------------------------------------------------------- executor acceptance review, batch A
class TestBatchAPriorityFlag(unittest.TestCase):
    """P3: "don't lower" comes from the explicit WHYNOT_PRIORITY=normal flag (tests/_isolation.py sets it), never from
    which modules happen to be imported."""

    def test_no_module_name_check(self):
        src = (ENGINE / "lib" / "priority.py").read_text(encoding="utf-8")
        self.assertNotIn("sys.modules", src)
        self.assertNotIn('"_isolation"', src)

    def test_the_flag_seen_at_start_survives_a_cleared_environment(self):
        with mock.patch.object(priority, "_START", "normal"), mock.patch.dict(os.environ, {}, clear=True), \
                mock.patch.object(priority, "_win_set", side_effect=AssertionError("would lower the runner")), \
                mock.patch.object(os, "nice", side_effect=AssertionError("would lower the runner"), create=True):
            self.assertEqual(priority.apply("below_normal", os_name="nt"), "normal")
            self.assertEqual(priority.wanted("below_normal"), "normal")

    def test_without_the_flag_an_isolated_process_is_lowered(self):
        # the old rule (a loaded module named _isolation) no longer decides: no flag at start or now -> lowered
        self.assertIn("_isolation", sys.modules)
        seen = []
        with mock.patch.object(priority, "_START", None), mock.patch.dict(os.environ, {}, clear=True), \
                mock.patch.object(priority, "_win_get", return_value=0x20), \
                mock.patch.object(priority, "_win_set", side_effect=seen.append):
            self.assertEqual(priority.apply("below_normal", os_name="nt"), "below_normal")
        self.assertEqual(seen, [0x4000])

    def test_an_explicit_env_argument_ignores_the_start_flag(self):
        calls = []
        with mock.patch.object(priority, "_START", "normal"):
            self.assertEqual(priority.apply(None, os_name="nt", setter=calls.append, env={}), "below_normal")
        self.assertEqual(calls, [0x4000])

    def test_a_child_started_with_the_flag_stays_normal_after_clearing_it(self):
        """Real OS, in a child: WHYNOT_PRIORITY=normal at start, os.environ cleared in-process, then apply()."""
        code = textwrap.dedent(f"""
            import os, sys
            sys.path.insert(0, {str(ENGINE)!r})
            from lib import priority
            os.environ.clear()
            print(priority.apply("below_normal"))
            if os.name == "nt":
                import ctypes
                k = ctypes.windll.kernel32
                k.GetCurrentProcess.restype = ctypes.c_void_p
                k.GetPriorityClass.argtypes = [ctypes.c_void_p]
                print(k.GetPriorityClass(k.GetCurrentProcess()))
            else:
                print(os.nice(0))
        """)
        env = dict(os.environ, WHYNOT_PRIORITY="normal")
        r = subprocess.run([sys.executable, "-I", "-c", code], capture_output=True, text=True, env=env, timeout=60)
        self.assertEqual(r.returncode, 0, r.stderr)
        state, cls = r.stdout.split()
        self.assertEqual(state, "normal")
        # the child inherits the runner's class; it must not have moved from it (read-only query of the runner)
        mine = priority._win_get() if os.name == "nt" else os.nice(0)
        self.assertEqual(int(cls), mine)


if __name__ == "__main__":
    unittest.main()
