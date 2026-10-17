# SPDX-License-Identifier: GPL-3.0-or-later
# © 2026 The Why Not AI (thewhynot.ai)
"""3.0 Phase 4 T4.10 (G-GPU): NVENC/NVDEC and VideoToolbox for intermediates, the engine GPU lock, CPU fallback.

No test here touches a GPU or runs a GPU encode: the ffmpeg probes are fake runners, a "GPU" ffmpeg is either a fake
process that prints an NVENC error or its CPU twin (the -hwaccel pair dropped, the NVENC arguments swapped for
libx264), and the suite itself runs with WHYNOT_ACCEL=off (tests/_isolation.py), so every other test file stays on
the CPU path with today's exact ffmpeg arguments.
Run:  bash tools/test.sh -p test_gpu_accel.py
"""
import sys as _sys
_sys.dont_write_bytecode = True  # keep the plugin folder free of __pycache__
import _isolation  # noqa: F401,E402  G79: sandbox the engine home first (tests/_isolation.py)
import contextlib
import importlib.util
import inspect
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import numpy as np

SK = Path(__file__).resolve().parents[1]
ENGINE = SK / "engine" / "reel"
sys.path.insert(0, str(ENGINE))
sys.path.insert(0, str(SK / "tests"))

from lib import common  # noqa: E402
from lib import accel, gpu_lock  # noqa: E402
from lib.common import Context, Paths, use_context, write_json  # noqa: E402

GPU_NAME = "NVIDIA GeForce RTX 4060 Laptop GPU"
CUDA = {"kind": "cuda", "h264": "h264_nvenc", "hevc": "hevc_nvenc", "decode": ["-hwaccel", "cuda"], "name": GPU_NAME,
        "why": None}
VT = {"kind": "videotoolbox", "h264": "h264_videotoolbox", "hevc": "hevc_videotoolbox",
      "decode": ["-hwaccel", "videotoolbox"], "name": "Apple VideoToolbox", "why": None}
CPU_OFF = {"kind": "cpu", "h264": "libx264", "hevc": None, "decode": [], "name": None,
           "why": "turned off (WHYNOT_ACCEL=off)"}
AR_DIR = "عميل تجربة ٣"                      # Arabic and spaces: must reach ffmpeg unchanged in both lanes
NVENC_ERR = "[h264_nvenc @ 0000021f] OpenEncodeSessionEx failed: out of memory (10): (no details)"
# ffmpeg 7.1 with -loglevel error, as it really prints a GPU encoder failure: the reason comes first, and the last
# three lines (all a 3-line tail sees) are generic task / thread / muxer lines that never name the GPU.
_FF7_TAIL = ["[vf#0:0 @ 0000020f8a3b0b00] Error sending frames to consumers: Generic error in an external library",
             "[vf#0:0 @ 0000020f8a3b0b00] Task finished with error code: -542398533 (Generic error in an external library)",
             "[vf#0:0 @ 0000020f8a3b0b00] Terminating thread with return code -542398533 (Generic error in an external "
             "library)",
             "[out#0/mp4 @ 0000020f8a3c4f00] Nothing was written into output file, because at least one of its streams "
             "received no packets."]


def ff7(first: str, enc: str = "h264_nvenc") -> str:
    return "\n".join([f"[{enc} @ 0000020f8a3c5c40] {first}",
                      f"[vost#0:0/{enc} @ 0000020f8a3a1e00] Error while opening encoder - maybe incorrect parameters "
                      "such as bit_rate, rate, width or height.", *_FF7_TAIL]) + "\n"


FF7_OPEN = ff7("OpenEncodeSessionEx failed: unsupported device (2): (no details)")
FF7_OOM = ff7("OpenEncodeSessionEx failed: out of memory (10): (no details)")
FF7_SESSIONS = ff7("OpenEncodeSessionEx failed: incompatible client key (21): (no details)")      # session limit
FF7_VT = ff7("Error: cannot create compression session: -12908", enc="h264_videotoolbox")
# an empty window (a range past the end of the source): the NVENC prefix with nothing about the GPU in it
FF7_EMPTY = "\n".join(["[vost#0:0/h264_nvenc @ 0000020f8a3a1e00] Could not open encoder before EOF",
                       "[vost#0:0/h264_nvenc @ 0000020f8a3a1e00] Task finished with error code: -22 (Invalid argument)",
                       "[vost#0:0/h264_nvenc @ 0000020f8a3a1e00] Terminating thread with return code -22 "
                       "(Invalid argument)", _FF7_TAIL[-1]]) + "\n"
CPU_X264 = ["-c:v", "libx264", "-preset", "veryfast", "-crf", "23"]
NVENC_23 = ["-c:v", "h264_nvenc", "-preset", "p4", "-rc", "vbr", "-cq", "23", "-b:v", "0"]


def cp(cmd, rc=0, out="", err=""):
    return subprocess.CompletedProcess(cmd, rc, out, err)


def fake(encoders="", probe_rc=0, probe_err="", name=GPU_NAME, driver="581.57"):
    """A runner that plays ffmpeg -encoders, the 0.1 s lavfi test encode and nvidia-smi (name, driver version)."""
    calls = []

    def run(cmd, *a, **kw):
        calls.append([str(c) for c in cmd])
        if "-encoders" in cmd:
            body = "".join(f" V....D {e:<22} fake {e} encoder\n" for e in encoders.split())
            return cp(cmd, 0, "Encoders:\n V..... = Video\n ------\n" + body)
        if "lavfi" in cmd:
            return cp(cmd, probe_rc, "", probe_err)
        if "nvidia-smi" in Path(str(cmd[0])).name:
            return cp(cmd, 0, (driver if "--query-gpu=driver_version" in cmd else name) + "\n")
        raise AssertionError(f"unexpected command {cmd}")
    run.calls = calls
    return run


def fake_seq(*results):
    """A runner answering (returncode, stderr) pairs in order."""
    calls, it = [], iter(results)

    def run(cmd, *a, **kw):
        calls.append([str(c) for c in cmd])
        rc, err = next(it)
        return cp(cmd, rc, "", err)
    run.calls = calls
    return run


def has_seq(argv, seq) -> bool:
    argv = [str(a) for a in argv]
    return any(argv[i:i + len(seq)] == list(seq) for i in range(len(argv) - len(seq) + 1))


def after(argv, flag) -> str:
    argv = [str(a) for a in argv]
    return argv[argv.index(flag) + 1]


def detect_as(d):
    return mock.patch.object(accel, "detect", return_value=dict(d))


@contextlib.contextmanager
def quiet():
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        yield


class _Home(unittest.TestCase):
    """A temp engine home bound for the test (the GPU lock, the accel cache and the bridge queues live there)."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="whynot-t410-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.home = self.tmp / "home"
        self.home.mkdir()
        stack = contextlib.ExitStack()
        self.addCleanup(stack.close)
        stack.enter_context(use_context(Context(None, home=self.home)))
        self.stack = stack

    def env(self, value):
        self.stack.enter_context(mock.patch.dict(os.environ, {"WHYNOT_ACCEL": value}))


# --------------------------------------------------------------------------- detection
class TestDetect(_Home):
    def setUp(self):
        super().setUp()
        self.env("auto")

    def test_the_suite_runs_with_acceleration_off(self):
        self.stack.close()                                   # the sandbox's own value, not this class's "auto"
        self.assertEqual(os.environ.get("WHYNOT_ACCEL"), "off")
        r = fake(encoders="h264_nvenc")
        self.assertEqual(accel.detect("ff", system="Windows", runner=r, refresh=True)["kind"], "cpu")
        self.assertEqual(r.calls, [])

    def test_nvenc_listed_and_probe_ok_is_cuda(self):
        r = fake(encoders="h264_nvenc hevc_nvenc")
        d = accel.detect("ff", system="Windows", runner=r, refresh=True)
        self.assertEqual((d["kind"], d["h264"], d["decode"]), ("cuda", "h264_nvenc", ["-hwaccel", "cuda"]))
        self.assertEqual((d["hevc"], d["name"], d["why"]), ("hevc_nvenc", GPU_NAME, None))
        probe = next(c for c in r.calls if "lavfi" in c)
        self.assertTrue(has_seq(probe, accel.h264_args("cuda", 23)), probe)   # the real argument shape (preset, rc)
        self.assertTrue(any("d=0.1" in c for c in probe), probe)          # a real 0.1 s encode, not just the list

    def test_intel_mac_without_qscale_is_cpu(self):
        """An Intel Mac's VideoToolbox refuses -q:v: the probe uses the engine's real arguments, so it says so now."""
        r = fake(encoders="h264_videotoolbox", probe_rc=1,
                 probe_err=ff7("qscale not available for encoder. Use -b:v bitrate instead.", enc="h264_videotoolbox"))
        d = accel.detect("ff", system="Darwin", runner=r, refresh=True)
        self.assertEqual(d["kind"], "cpu")
        self.assertIn("qscale not available", d["why"])
        self.assertTrue(has_seq(next(c for c in r.calls if "lavfi" in c), ["-c:v", "h264_videotoolbox", "-q:v", "65"]))

    def test_nvenc_listed_but_probe_fails_is_cpu_with_reason(self):      # Optimus laptop, old driver
        d = accel.detect("ff", system="Windows", runner=fake(encoders="h264_nvenc", probe_rc=1,
                         probe_err="[h264_nvenc @ 01] No capable devices found"), refresh=True)
        self.assertEqual(d["kind"], "cpu")
        self.assertIn("No capable devices", d["why"])
        self.assertEqual((d["h264"], d["hevc"], d["decode"]), ("libx264", None, []))

    def test_no_nvenc_in_this_ffmpeg_is_cpu_with_reason(self):
        r = fake(encoders="libx264 libx265")
        d = accel.detect("ff", system="Windows", runner=r, refresh=True)
        self.assertEqual(d["kind"], "cpu")
        self.assertIn("h264_nvenc", d["why"])
        self.assertFalse(any("lavfi" in c for c in r.calls))                # nothing to test-encode

    def test_mac_is_videotoolbox(self):
        r = fake(encoders="h264_videotoolbox hevc_videotoolbox")
        d = accel.detect("ff", system="Darwin", runner=r, refresh=True)
        self.assertEqual((d["kind"], d["h264"], d["decode"]),
                         ("videotoolbox", "h264_videotoolbox", ["-hwaccel", "videotoolbox"]))
        self.assertEqual((d["hevc"], d["name"], d["why"]), ("hevc_videotoolbox", "Apple VideoToolbox", None))
        self.assertIn("h264_videotoolbox", next(c for c in r.calls if "lavfi" in c))
        self.assertFalse(any("nvidia-smi" in c[0] for c in r.calls))

    def test_mac_without_videotoolbox_is_cpu(self):
        d = accel.detect("ff", system="Darwin", runner=fake(encoders="libx264"), refresh=True)
        self.assertEqual(d["kind"], "cpu")
        self.assertIn("h264_videotoolbox", d["why"])

    def test_no_ffmpeg_and_env_off_are_cpu(self):
        r = fake(encoders="h264_nvenc")
        with mock.patch.object(accel, "_ffmpeg", return_value=None):
            d = accel.detect(None, system="Windows", runner=r, refresh=True)
        self.assertEqual(d["kind"], "cpu")
        self.assertIn("ffmpeg", d["why"])
        self.env("off")
        self.assertEqual(accel.detect("ff", system="Windows", runner=r, refresh=True), CPU_OFF)
        self.assertEqual(r.calls, [])

    def test_a_runner_that_raises_is_cpu_never_an_error(self):
        for exc in (OSError(2, "not found"), subprocess.TimeoutExpired(["ff"], 30)):
            def boom(cmd, *a, _e=exc, **kw):
                raise _e
            with self.subTest(exc=type(exc).__name__):
                d = accel.detect("ff", system="Windows", runner=boom, refresh=True)
                self.assertEqual(d["kind"], "cpu")
                self.assertTrue(d["why"])

    def test_cache_keyed_by_ffmpeg_stat(self):
        ff = self.tmp / "ffmpeg.exe"
        ff.write_bytes(b"x")
        r = fake(encoders="h264_nvenc hevc_nvenc")
        first = accel.detect(str(ff), system="Windows", runner=r)
        n = len(r.calls)
        self.assertGreater(n, 0)
        self.assertTrue((self.home / "cache" / "accel.json").is_file())
        self.assertEqual(accel.detect(str(ff), system="Windows", runner=r), first)
        self.assertEqual(len(r.calls), n)                                   # 2nd call: 0 runner calls
        st = ff.stat()
        os.utime(ff, ns=(st.st_atime_ns, st.st_mtime_ns + 2_000_000_000))
        accel.detect(str(ff), system="Windows", runner=r)
        self.assertGreater(len(r.calls), n)                                 # another ffmpeg build: probed again
        m = len(r.calls)
        accel.detect(str(ff), system="Windows", runner=r, refresh=True)
        self.assertGreater(len(r.calls), m)

    def test_a_new_nvidia_driver_probes_again(self):
        """The key holds a cheap stat of the driver's files (Windows: System32 nvcuda.dll / nvml.dll, nvidia-smi):
        an update changes it, so the next detect probes again."""
        ff, dll = self.tmp / "ffmpeg.exe", self.tmp / "nvcuda.dll"
        ff.write_bytes(b"x")
        dll.write_bytes(b"driver 581")
        with mock.patch.object(accel, "_driver_files", return_value=[dll]):
            accel.detect(str(ff), system="Windows", runner=fake(encoders="h264_nvenc", probe_rc=1,
                                                                 probe_err="No capable devices found"))
            dll.write_bytes(b"driver 590.12")                              # the editor updated the driver
            r = fake(encoders="h264_nvenc")
            self.assertEqual(accel.detect(str(ff), system="Windows", runner=r)["kind"], "cuda")
        self.assertTrue(any("lavfi" in c for c in r.calls))
        key = json.loads((self.home / "cache" / "accel.json").read_text(encoding="utf-8"))["key"]
        self.assertEqual(key["driver"][0][1], len(b"driver 590.12"))

    def test_a_cache_hit_starts_no_process(self):
        """Every preflight, prep and animatic calls detect(): a hit costs a few stat calls, never nvidia-smi."""
        ff = self.tmp / "ffmpeg.exe"
        ff.write_bytes(b"x")
        first = accel.detect(str(ff), system="Windows", runner=fake(encoders="h264_nvenc"))
        r = fake(encoders="h264_nvenc")
        with mock.patch.object(subprocess, "Popen", side_effect=AssertionError("no process on a cache hit")), \
                mock.patch.object(subprocess, "run", side_effect=AssertionError("no process on a cache hit")):
            self.assertEqual(accel.detect(str(ff), system="Windows", runner=r), first)
            self.assertEqual(accel.detect(str(ff), system="Windows"), first)    # the default runner too
        self.assertEqual(r.calls, [])

    def test_a_gpu_fallback_drops_the_cache(self):
        ff = self.tmp / "ffmpeg.exe"
        ff.write_bytes(b"x")
        accel.detect(str(ff), system="Windows", runner=fake(encoders="h264_nvenc"))
        cache = self.home / "cache" / "accel.json"
        self.assertTrue(cache.is_file())
        with quiet():
            accel.run_ff(lambda ln: ["ffmpeg", *accel.h264_args(ln, 23), "o.mp4"], "cuda",
                         runner=fake_seq((1, FF7_OOM), (0, "")))
        self.assertFalse(cache.exists())                                 # the next job asks the card again

    def test_a_busy_gpu_at_probe_time_is_not_cached(self):
        """A GPU out of memory while Premiere exports is not "this machine has no GPU": the next job probes again."""
        ff = self.tmp / "ffmpeg.exe"
        ff.write_bytes(b"x")
        r = fake(encoders="h264_nvenc", probe_rc=1, probe_err=FF7_OOM)
        self.assertEqual(accel.detect(str(ff), system="Windows", runner=r)["kind"], "cpu")
        n = len(r.calls)
        accel.detect(str(ff), system="Windows", runner=r)
        self.assertGreater(len(r.calls), n)


# --------------------------------------------------------------------------- arguments and failures
class TestArgs(unittest.TestCase):
    def test_cpu_args_are_todays_exact_args(self):
        self.assertEqual(accel.h264_args("cpu", 23), ["-c:v", "libx264", "-preset", "veryfast", "-crf", "23"])
        self.assertEqual(accel.h264_args("cpu", 28), ["-c:v", "libx264", "-preset", "veryfast", "-crf", "28"])

    def test_gpu_args(self):
        self.assertEqual(accel.h264_args("cuda", 18),
                         ["-c:v", "h264_nvenc", "-preset", "p4", "-rc", "vbr", "-cq", "18", "-b:v", "0"])
        self.assertEqual(accel.VT_Q, {18: 75, 23: 65, 28: 55})
        for crf, q in ((18, "75"), (23, "65"), (28, "55"), (26, "59")):     # 26: the animatic, between 23 and 28
            self.assertEqual(accel.h264_args("videotoolbox", crf), ["-c:v", "h264_videotoolbox", "-q:v", q])

    def test_decode_args(self):
        self.assertEqual(accel.decode_args("cpu"), [])
        self.assertEqual(accel.decode_args("cuda"), ["-hwaccel", "cuda"])
        self.assertEqual(accel.decode_args("videotoolbox"), ["-hwaccel", "videotoolbox"])

    def test_site_lanes(self):
        self.assertEqual(set(accel.SITE_LANES),
                         {"preview_video", "reel_candidates", "animatic", "thumbs", "shots", "grab_frame"})
        self.assertTrue(set(accel.SITE_LANES.values()) <= {"gpu", "cpu"})
        self.assertEqual(accel.SITE_LANES["grab_frame"], "cpu")              # one frame pays the CUDA start-up
        self.assertEqual(accel.site_lane("grab_frame", "cuda"), "cpu")
        with mock.patch.dict(accel.SITE_LANES, {"thumbs": "gpu"}):
            self.assertEqual(accel.site_lane("thumbs", "cuda"), "cuda")
            self.assertEqual(accel.site_lane("thumbs", "cpu"), "cpu")

    def test_is_gpu_failure(self):
        for s in (NVENC_ERR, "No capable devices found", "CUDA_ERROR_OUT_OF_MEMORY", "cuda: out of memory",
                  "Cannot load nvcuda.dll", "Cannot load libnvidia-encode.so.1",
                  "[h264_videotoolbox @ 0x1] Error: cannot create compression session: VTCompressionSessionCreate",
                  "Driver does not support the required nvenc API version. Required: 12.1 Found: 11.0",
                  "[h264 @ 0x1] Failed setup for format cuda: hwaccel initialisation returned error",
                  b"Cannot load nvcuda.dll", FF7_OPEN, FF7_OOM, FF7_SESSIONS, FF7_VT,
                  "[vost#0:0/h264_nvenc @ 0000020f8a3a1e00] OpenEncodeSessionEx failed: out of memory (10)",
                  "[h264_videotoolbox @ 0x600] qscale not available for encoder"):
            with self.subTest(s=s):
                self.assertTrue(accel.is_gpu_failure(s))
        for s in ("D:/cuda clips/x.mp4: No such file or directory", "Invalid data found when processing input",
                  "", None, "Conversion failed!", "\n".join(_FF7_TAIL[-3:]),
                  "[vost#0:0/libx264 @ 0000] Error while opening encoder", FF7_EMPTY,
                  "[vost#0:0/h264_nvenc @ 0000020f8a3a1e00] Could not open encoder before EOF",
                  "[vost#0:0/hevc_videotoolbox @ 0x600] Task finished with error code: -22 (Invalid argument)"):
            with self.subTest(s=s):
                self.assertFalse(accel.is_gpu_failure(s))


class TestRunFF(unittest.TestCase):
    def setUp(self):
        self.src = str(Path(tempfile.gettempdir()) / AR_DIR / "حلقة 1.mp4")
        self.out = str(Path(tempfile.gettempdir()) / AR_DIR / "خرج 1.mp4")

    def build(self, lane):
        return ["ffmpeg", "-y", *accel.decode_args(lane), "-i", self.src, *accel.h264_args(lane, 23), self.out]

    def test_gpu_failure_reruns_once_on_cpu(self):
        r = fake_seq((1, FF7_OOM), (0, ""))
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            res, lane = accel.run_ff(self.build, "cuda", runner=r)
        self.assertEqual(lane, "cpu")
        self.assertEqual(len(r.calls), 2)
        self.assertIn("h264_nvenc", r.calls[0])
        self.assertIn("libx264", r.calls[1])
        self.assertNotIn("-hwaccel", r.calls[1])
        self.assertEqual(res.returncode, 0)
        self.assertIn(accel.GPU_FALLBACK_EN, err.getvalue())
        self.assertIn(accel.GPU_FALLBACK_AR, err.getvalue())
        self.assertIn("OpenEncodeSessionEx failed: out of memory", err.getvalue())    # the reason, not the tail
        for c in r.calls:                                       # the Arabic + space paths, unchanged, both lanes
            self.assertEqual((after(c, "-i"), c[-1]), (self.src, self.out))

    def test_other_failure_is_not_retried(self):
        r = fake_seq((1, f"{self.src}: No such file or directory"))
        res, lane = accel.run_ff(self.build, "cuda", runner=r)
        self.assertEqual((len(r.calls), lane, res.returncode), (1, "cuda", 1))

    def test_an_empty_window_is_the_usual_refusal(self):
        """P3: "Could not open encoder before EOF" (no frames: the window is empty) under an NVENC prefix is not the
        GPU's fault: no CPU re-run, and the machine's answer stays cached."""
        with tempfile.TemporaryDirectory() as t, use_context(Context(None, home=Path(t))), \
                mock.patch.dict(os.environ, {"WHYNOT_ACCEL": "auto"}):
            ff = Path(t) / "ffmpeg.exe"
            ff.write_bytes(b"x")
            accel.detect(str(ff), system="Windows", runner=fake(encoders="h264_nvenc"))
            r = fake_seq((1, FF7_EMPTY))
            res, lane = accel.run_ff(self.build, "cuda", runner=r)
            self.assertEqual((len(r.calls), lane, res.returncode), (1, "cuda", 1))
            self.assertTrue((Path(t) / "cache" / "accel.json").is_file())

    def test_cpu_lane_is_never_retried(self):
        r = fake_seq((1, "out of memory"))
        res, lane = accel.run_ff(self.build, "cpu", runner=r)
        self.assertEqual((len(r.calls), lane), (1, "cpu"))
        self.assertEqual(r.calls[0], ["ffmpeg", "-y", "-i", self.src, *CPU_X264, self.out])

    def test_bytes_stderr_and_a_second_failure(self):
        r = fake_seq((1, b"Cannot load nvcuda.dll"), (1, b"Conversion failed!"))
        with quiet():
            res, lane = accel.run_ff(self.build, "cuda", runner=r)
        self.assertEqual((len(r.calls), lane, res.returncode), (2, "cpu", 1))   # once, never a third time

    def test_messages(self):
        self.assertEqual(accel.GPU_FALLBACK_EN,
                         "The graphics card couldn't do this step (it may be busy or out of memory), so the processor "
                         "did it: slower, same result.")
        self.assertRegex(accel.GPU_FALLBACK_AR, "[\u0600-\u06ff]")


# --------------------------------------------------------------------------- the engine GPU lock
class TestGpuSlot(_Home):
    def setUp(self):
        super().setUp()
        self.q, self.aq = self.home / "ppro-queue", self.home / "ae-queue"
        self.info = self.home / "locks" / "gpu.json"

    def beat(self, q, age_s=0.0, **kw):
        q.mkdir(parents=True, exist_ok=True)
        write_json(q / "bridge.heartbeat", {"at": (time.time() - age_s) * 1000, "busy": False, "role": "daemon",
                                            "host": "PPRO" if q.name == "ppro-queue" else "AEFT", **kw})

    def test_cep_status_carries_host_busy(self):
        from lib import cep_queue
        self.beat(self.q, host_busy="exporting")
        self.assertEqual(cep_queue.status(self.q)["host_busy"], "exporting")
        self.beat(self.q)
        self.assertIsNone(cep_queue.status(self.q)["host_busy"])

    def test_cpu_machine_slot_is_cpu_without_lock(self):
        with detect_as(CPU_OFF), mock.patch.object(gpu_lock.file_lock, "locked",
                                                   side_effect=AssertionError("no lock on a CPU machine")):
            with gpu_lock.gpu_slot("preview_video", wait_s=5) as lane:
                self.assertEqual(lane, "cpu")
        self.assertFalse(self.info.exists())

    def test_free_gpu_yields_the_lane_and_records_the_holder(self):
        with detect_as(CUDA):
            with gpu_lock.gpu_slot("transcribe", wait_s=0) as lane:
                self.assertEqual(lane, "cuda")
                rec = json.loads(self.info.read_text(encoding="utf-8"))
                self.assertEqual((rec["pid"], rec["what"]), (os.getpid(), "transcribe"))
                self.assertIn("since", rec)
                self.assertEqual(gpu_lock.held()["what"], "transcribe")
            self.assertIsNone(gpu_lock.held())
        self.assertFalse(self.info.exists())

    def test_mac_slot_is_videotoolbox(self):
        with detect_as(VT), gpu_lock.gpu_slot("preview_video") as lane:
            self.assertEqual(lane, "videotoolbox")

    def test_second_holder_gets_cpu_after_wait(self):
        """Two sessions at once: the second waits wait_s, then takes the CPU path (one log line), never a crash."""
        code = ("import sys; sys.path.insert(0, sys.argv[1]); from lib import file_lock\n"
                "with file_lock.locked(sys.argv[2], wait_s=10):\n"
                "    print('ready', flush=True); sys.stdin.read()\n")
        with subprocess.Popen([sys.executable, "-B", "-c", code, str(ENGINE), str(self.home / "locks" / "gpu")],
                              stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True) as p:
            try:
                self.assertEqual(p.stdout.readline().strip(), "ready")
                err = io.StringIO()
                with detect_as(CUDA), contextlib.redirect_stderr(err):
                    t0 = time.monotonic()
                    with gpu_lock.gpu_slot("transcribe", wait_s=0.3) as lane:
                        waited = time.monotonic() - t0
                        self.assertEqual(lane, "cpu")
                    self.assertIsNotNone(gpu_lock.held())              # the other holder still has it
                self.assertGreaterEqual(waited, 0.25)
                self.assertLess(waited, 10)
                lines = [x for x in err.getvalue().splitlines() if x.strip()]
                self.assertEqual(len(lines), 2, lines)                 # "waiting for ...", then "... so the CPU"
                self.assertIn("waiting for the graphics card", lines[0])
                self.assertIn("GPU", lines[1])
                self.assertFalse(self.info.exists())                   # the waiter wrote no holder record
            finally:
                p.stdin.close()
                p.wait(timeout=30)
        with detect_as(CUDA), gpu_lock.gpu_slot("transcribe") as lane:  # the holder exited: free again
            self.assertEqual(lane, "cuda")

    @contextlib.contextmanager
    def hold(self, name, what=None):
        """Another process (another Claude session's engine) holds <home>/locks/<name> (and names itself `what`)."""
        code = ("import sys, os, json; sys.path.insert(0, sys.argv[1]); from lib import file_lock\n"
                "with file_lock.locked(sys.argv[2], wait_s=10):\n"
                "    if sys.argv[3]:\n"
                "        open(sys.argv[2] + '.json', 'w', encoding='utf-8').write(json.dumps("
                "{'pid': os.getpid(), 'what': sys.argv[3], 'since': 'x'}))\n"
                "    print('ready', flush=True); sys.stdin.read()\n")
        with subprocess.Popen([sys.executable, "-B", "-c", code, str(ENGINE), str(self.home / "locks" / name),
                               what or ""], stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True) as p:
            try:
                self.assertEqual(p.stdout.readline().strip(), "ready")
                yield
            finally:
                p.stdin.close()
                p.wait(timeout=30)

    def whisper(self, lane, **kw):
        with mock.patch.object(gpu_lock, "whisper_lane", return_value=lane), quiet(), \
                gpu_lock.whisper_slot("transcribe", wait_s=0, **kw) as got:
            return got

    def test_a_lock_folder_that_cannot_be_written_gives_cpu(self):
        """A read-only engine home: the file lock's Guidance / OSError is "use the CPU", one log line, never a crash."""
        from lib.errors import Guidance
        for exc in (Guidance("cannot create the lock file gpu.lock in X: Access is denied", "Check the folder", "X"),
                    PermissionError(13, "Access is denied")):
            with self.subTest(exc=type(exc).__name__):
                err = io.StringIO()
                with detect_as(CUDA), mock.patch.object(gpu_lock.file_lock, "locked", side_effect=exc), \
                        contextlib.redirect_stderr(err), gpu_lock.gpu_slot("preview_video") as lane:
                    self.assertEqual(lane, "cpu")
                lines = [x for x in err.getvalue().splitlines() if x.strip()]
                self.assertEqual(len(lines), 1, lines)
                self.assertIn("lock", lines[0])

    def test_windows_video_and_whisper_share_one_lock(self):
        """NVENC and CUDA Whisper share the card's VRAM: one lock on Windows."""
        with self.hold("gpu"):
            with detect_as(CUDA), quiet(), gpu_lock.gpu_slot("preview_video") as lane:
                self.assertEqual(lane, "cpu")
            self.assertEqual(self.whisper("cuda"), "cpu")
        self.assertEqual(self.whisper("cuda"), "cuda")

    def test_mac_videotoolbox_and_mlx_use_separate_locks(self):
        """macOS: VideoToolbox (the media engine) and MLX (the GPU cores) hardly contend: locks/gpu-media for video,
        locks/gpu for ML."""
        with self.hold("gpu"):                                   # an MLX transcription elsewhere
            with detect_as(VT), gpu_lock.gpu_slot("preview_video") as lane:
                self.assertEqual(lane, "videotoolbox")
                self.assertEqual(gpu_lock.held("gpu-media")["what"], "preview_video")
            self.assertEqual(self.whisper("mlx"), "cpu")
        with self.hold("gpu-media"):                             # a VideoToolbox job elsewhere
            with detect_as(VT), quiet(), gpu_lock.gpu_slot("preview_video") as lane:
                self.assertEqual(lane, "cpu")
            self.assertEqual(self.whisper("mlx"), "mlx")

    def test_whisper_lane(self):
        """Transcription locks by Whisper's own device (plat.gpu_info), not by ffmpeg's: an NVENC-less ffmpeg or a
        failed NVENC probe must not let two CUDA Whispers run unlocked."""
        from lib import plat
        from lib import whisper_backends as WB
        cuda = {"cuda_devices": 1, "whisper_device": "cuda"}
        with mock.patch.dict(os.environ, {"WHYNOT_ACCEL": "auto"}), \
                mock.patch.object(WB, "choose_backend", return_value=("ct2", None)):
            with mock.patch.object(plat, "gpu_info", return_value=cuda):
                self.assertEqual(gpu_lock.whisper_lane(), "cuda")
                with detect_as(dict(CPU_OFF, why="this ffmpeg has no h264_nvenc encoder")), quiet(), \
                        gpu_lock.whisper_slot("transcribe", wait_s=0) as lane:
                    self.assertEqual(lane, "cuda")                     # the real lock, though video is "cpu"
                    self.assertEqual(gpu_lock.held()["what"], "transcribe")
                self.beat(self.q, host_busy="exporting")
                with quiet(), gpu_lock.whisper_slot("transcribe", wait_s=0) as lane:
                    self.assertEqual(lane, "cpu")                      # and the host-busy wait
            with mock.patch.object(plat, "gpu_info", return_value={"cuda_devices": 0, "whisper_device": "cpu"}):
                self.assertEqual(gpu_lock.whisper_lane(), "cpu")
            with mock.patch.object(WB, "choose_backend", return_value=("mlx", None)):
                self.assertEqual(gpu_lock.whisper_lane(), "mlx")
        with mock.patch.object(plat, "gpu_info", side_effect=AssertionError("no CUDA query when off")):
            self.assertEqual(gpu_lock.whisper_lane(), "cpu")                # the suite: WHYNOT_ACCEL=off
        self.assertEqual((accel.whisper_device("cuda"), accel.whisper_device("mlx"), accel.whisper_device("cpu")),
                         (None, None, "cpu"))

    def test_host_exporting_gives_cpu(self):
        self.beat(self.q, host_busy="exporting")
        err = io.StringIO()
        with detect_as(CUDA), contextlib.redirect_stderr(err):
            with gpu_lock.gpu_slot("preview_video", wait_s=0) as lane:
                self.assertEqual(lane, "cpu")
        self.assertEqual(gpu_lock.host_busy(), "exporting")
        self.assertIn("exporting", err.getvalue())
        self.assertFalse(self.info.exists())

    def test_after_effects_rendering_gives_cpu(self):
        self.beat(self.aq, host_busy="rendering")
        self.assertEqual(gpu_lock.host_busy(), "rendering")
        self.assertEqual(gpu_lock.host_busy([self.aq]), "rendering")
        self.assertIsNone(gpu_lock.host_busy([self.q]))
        with detect_as(CUDA), quiet(), gpu_lock.gpu_slot("animatic") as lane:
            self.assertEqual(lane, "cpu")

    def test_host_busy_absent_unknown_or_stale_proceeds(self):
        for kw, age in (({}, 0), ({"host_busy": "unknown"}, 0), ({"host_busy": "idle"}, 0),
                        ({"host_busy": "something new"}, 0), ({"host_busy": "exporting"}, 30)):
            with self.subTest(kw=kw, age=age):
                self.beat(self.q, age, **kw)
                self.assertIsNone(gpu_lock.host_busy())
                with detect_as(CUDA), gpu_lock.gpu_slot("preview_video", wait_s=0) as lane:
                    self.assertEqual(lane, "cuda")
        (self.q / "bridge.heartbeat").write_text("{not json", encoding="utf-8")
        self.assertIsNone(gpu_lock.host_busy())
        (self.q / "bridge.heartbeat").unlink()
        self.assertIsNone(gpu_lock.host_busy())

    def test_a_lock_wait_says_so_and_reports_progress_in_the_clip_log(self):
        """P2: a wait of up to 600 s is never silent: one line when it starts (who has the card), a progress line
        about every PROGRESS_S, to stderr AND the clip's pipeline.log."""
        root = self.tmp / "C"
        clip = Paths(root, "C0001")
        clip.ensure_project()
        err = io.StringIO()
        with self.hold("gpu", what="transcribe"), mock.patch.object(gpu_lock, "PROGRESS_S", 0.3), \
                detect_as(CUDA), contextlib.redirect_stderr(err), \
                gpu_lock.gpu_slot("preview_video", wait_s=1.2, log_to=clip) as lane:
            self.assertEqual(lane, "cpu")
        lines = [x for x in err.getvalue().splitlines() if x.strip()]
        self.assertIn("waiting for the graphics card (another WhyNot Cut job: transcribe", lines[0])
        self.assertGreaterEqual(sum("still waiting" in x for x in lines), 2, lines)
        self.assertIn("so this step uses the processor", lines[-1])
        log = clip.p("logs/pipeline.log").read_text(encoding="utf-8")
        self.assertIn("waiting for the graphics card", log)
        self.assertIn("still waiting", log)

    def test_a_host_wait_says_so_and_reports_progress(self):
        self.beat(self.q, host_busy="exporting")
        now, err = [0.0], io.StringIO()

        def sleep(s):
            now[0] += s
            if now[0] >= 70:
                self.beat(self.q, host_busy="idle")
        with detect_as(CUDA), contextlib.redirect_stderr(err), \
                gpu_lock.gpu_slot("preview_video", wait_s=120, clock=lambda: now[0], sleep=sleep) as lane:
            self.assertEqual(lane, "cuda")
        lines = [x for x in err.getvalue().splitlines() if x.strip()]
        self.assertIn("waiting for Premiere or After Effects to finish exporting", lines[0])
        self.assertEqual(sum("still waiting" in x for x in lines), 2, lines)     # at 30 s and 60 s
        self.assertEqual(len(lines), 3, lines)

    def test_a_wait_of_zero_prints_no_waiting_line(self):
        err = io.StringIO()
        with self.hold("gpu", what="transcribe"), detect_as(CUDA), contextlib.redirect_stderr(err), \
                gpu_lock.gpu_slot("animatic") as lane:
            self.assertEqual(lane, "cpu")
        lines = [x for x in err.getvalue().splitlines() if x.strip()]
        self.assertEqual(len(lines), 1, lines)
        self.assertNotIn("waiting", lines[0])

    def test_a_held_poller_never_pushes_a_free_slot_onto_the_cpu(self):
        """P3: held() (T4.15's check) from another process must not make a wait-0 job lose a free GPU."""
        code = ("import sys, time; sys.path.insert(0, sys.argv[1]); from lib import gpu_lock\n"
                "print('ready', flush=True); t = time.monotonic()\n"
                "while time.monotonic() - t < 6: gpu_lock.held()\n")
        env = dict(os.environ, WHYNOT_HOME=str(self.home))
        got = []
        with subprocess.Popen([sys.executable, "-B", "-c", code, str(ENGINE)], stdout=subprocess.PIPE, text=True,
                              env=env) as p:
            try:
                self.assertEqual(p.stdout.readline().strip(), "ready")
                with detect_as(CUDA), quiet():
                    for _ in range(40):
                        with gpu_lock.gpu_slot("animatic") as lane:
                            got.append(lane)
                        time.sleep(0.02)
            finally:
                p.wait(timeout=30)
        self.assertEqual(got, ["cuda"] * 40)

    def test_a_busy_host_is_waited_for(self):
        self.beat(self.q, host_busy="exporting")
        now, polls = [0.0], []

        def sleep(s):
            polls.append(s)
            now[0] += s
            if len(polls) == 2:
                self.beat(self.q, host_busy="idle")                    # Premiere finished its export
        with detect_as(CUDA), gpu_lock.gpu_slot("preview_video", wait_s=120, poll_s=2.0, clock=lambda: now[0],
                                                sleep=sleep) as lane:
            self.assertEqual(lane, "cuda")
        self.assertEqual(polls, [2.0, 2.0])

    def test_a_host_still_busy_after_the_wait_gives_cpu(self):
        self.beat(self.q, host_busy="rendering")
        now, polls = [0.0], []

        def sleep(s):
            polls.append(s)
            now[0] += s
        with detect_as(CUDA), quiet(), gpu_lock.gpu_slot("transcribe", wait_s=5, poll_s=2.0, clock=lambda: now[0],
                                                          sleep=sleep) as lane:
            self.assertEqual(lane, "cpu")
        self.assertEqual(polls, [2.0, 2.0, 1.0])

    def test_site_slot_follows_site_lanes(self):
        with detect_as(CUDA):
            with gpu_lock.site_slot("grab_frame") as lane:                # "cpu" in SITE_LANES: no lock at all
                self.assertEqual(lane, "cpu")
                self.assertIsNone(gpu_lock.held())
            with mock.patch.dict(accel.SITE_LANES, {"thumbs": "gpu"}), gpu_lock.site_slot("thumbs") as lane:
                self.assertEqual(lane, "cuda")
                self.assertEqual(gpu_lock.held()["what"], "thumbs")
        self.assertEqual((gpu_lock.WAITS["transcribe"], gpu_lock.WAITS["preview_video"],
                          gpu_lock.WAITS["reel_candidates"]), (600.0, 120.0, 120.0))


# --------------------------------------------------------------------------- call sites
class TestFrameSites(_Home):
    def setUp(self):
        super().setUp()
        self.src = self.tmp / AR_DIR / "حلقة 1.mp4"

    def test_grab_frame_file_lanes(self):
        from lib import media_util as MU
        seen = []
        self.assertEqual(inspect.signature(MU.grab_frame_file).parameters["lane"].default, "cpu")
        with mock.patch.object(common, "run", side_effect=lambda cmd, **kw: seen.append(cmd) or cp(cmd, 1)), \
                mock.patch.object(MU, "_ffmpeg", return_value="ffmpeg"):
            MU.grab_frame_file(self.src, 1.5, self.tmp / "a.jpg")
            MU.grab_frame_file(self.src, 1.5, self.tmp / "b.jpg", lane="cuda")
        cpu, gpu = seen
        self.assertEqual(cpu, ["ffmpeg", "-y", "-loglevel", "error", "-ss", "1.500", "-i", str(self.src),
                               "-frames:v", "1", str(self.tmp / "a.jpg")])            # today's argv
        self.assertLess(gpu.index("-hwaccel"), gpu.index("-i"))
        self.assertEqual(after(gpu, "-hwaccel"), "cuda")
        self.assertEqual(after(gpu, "-i"), str(self.src))

    def test_grab_frame_lanes(self):
        from lib import media_util as MU
        seen = []
        self.assertEqual(inspect.signature(MU.grab_frame).parameters["lane"].default, "cpu")
        with mock.patch.object(MU.subprocess, "run", side_effect=lambda cmd, **kw: seen.append(cmd) or cp(cmd, 1, b"")), \
                mock.patch.object(MU, "_ffmpeg", return_value="ffmpeg"):
            self.assertIsNone(MU.grab_frame(self.src, 2.0, 64, 36))
            self.assertIsNone(MU.grab_frame(self.src, 2.0, 64, 36, lane="videotoolbox"))
        cpu, gpu = seen
        self.assertNotIn("-hwaccel", cpu)
        self.assertEqual(cpu[:8], ["ffmpeg", "-loglevel", "error", "-ss", "2.000", "-i", str(self.src), "-an"])
        self.assertEqual(after(gpu, "-hwaccel"), "videotoolbox")
        self.assertEqual(after(gpu, "-i"), str(self.src))

    def test_thumbs_gpu_failure_reruns_on_cpu(self):
        from lib import overlay_scan as OS
        seen = []
        answers = [cp(None, 1, b"", b"[h264 @ 1] Failed setup for format cuda: hwaccel initialisation returned error"),
                   cp(None, 0, bytes(OS.TH_W * OS.TH_H * 3 * 2), b"")]
        with mock.patch.object(OS.subprocess, "run", side_effect=lambda cmd, **kw: seen.append(cmd) or answers.pop(0)), \
                mock.patch.object(OS, "ffmpeg_exe", return_value="ffmpeg"), quiet():
            fr = OS.decode_thumbs(self.src, 0.0, 2.0, lane="cuda")
        self.assertEqual(fr.shape, (2, OS.TH_H, OS.TH_W, 3))
        self.assertEqual(len(seen), 2)
        self.assertEqual(after(seen[0], "-hwaccel"), "cuda")
        self.assertNotIn("-hwaccel", seen[1])
        for c in seen:
            self.assertEqual(after(c, "-i"), str(self.src))

    def test_thumbs_cpu_argv_unchanged(self):
        from lib import overlay_scan as OS
        seen = []
        with mock.patch.object(OS.subprocess, "run", side_effect=lambda cmd, **kw: seen.append(cmd) or cp(cmd, 0, b"")), \
                mock.patch.object(OS, "ffmpeg_exe", return_value="ffmpeg"):
            OS.decode_thumbs(self.src, 5.0, 2.0)
        self.assertEqual(seen, [["ffmpeg", "-nostdin", "-v", "error", "-ss", "5.000", "-i", str(self.src), "-t", "2.000",
                                 "-an", "-sn", "-vf", f"fps=1,scale={OS.TH_W}:{OS.TH_H}:flags=area,format=rgb24",
                                 "-f", "rawvideo", "-"]])

    def test_scan_video_takes_no_slot_and_passes_the_lane(self):
        """The verb (episode.prep) takes the slot once; the analysis helper only passes the lane down."""
        from lib import overlay_scan as OS
        lanes = []

        def dec(src, a, b, lane="cpu"):
            lanes.append(lane)
            return np.zeros((0, OS.TH_H, OS.TH_W, 3), np.uint8)
        self.assertEqual(inspect.signature(OS.scan_video).parameters["lane"].default, "cpu")
        with mock.patch.object(gpu_lock, "gpu_slot", side_effect=AssertionError("a helper takes no slot")), \
                mock.patch.object(gpu_lock, "site_slot", side_effect=AssertionError("a helper takes no slot")), \
                mock.patch.object(OS, "decode_thumbs", side_effect=dec):
            OS.scan_video(self.src, 700.0, lane="cuda")                  # three 5-minute chunks
            OS.scan_video(self.src, 10.0)
            OS.scan_video(self.src, 10.0, decode=lambda *a: np.zeros((0, OS.TH_H, OS.TH_W, 3), np.uint8))
        self.assertEqual(lanes, ["cuda"] * 3 + ["cpu"])

    def test_shots_decoder_lane_and_cpu_rerun(self):
        from lib import media_util as MU
        from lib import shots
        cmds = []

        @contextlib.contextmanager
        def fake_popen(cmd, **kw):
            cmds.append(list(cmd))
            gpu = "-hwaccel" in cmd
            if gpu and hasattr(kw.get("stderr"), "write"):
                kw["stderr"].write(b"[h264 @ 1] Failed setup for format cuda: hwaccel initialisation returned error\n")
                kw["stderr"].flush()
            yield SimpleNamespace(stdout=io.BytesIO(b"" if gpu else bytes(640 * 360 * 3)), kill=lambda: None)
        self.assertEqual(inspect.signature(shots.analyze_window).parameters["lane"].default, "cpu")
        with mock.patch.object(gpu_lock, "gpu_slot", side_effect=AssertionError("a helper takes no slot")), \
                mock.patch.object(shots, "detect_cuts", return_value=[]), \
                mock.patch.object(shots, "ffmpeg_exe", return_value="ffmpeg"), \
                mock.patch.object(MU, "ff_popen", fake_popen), quiet():
            rep = shots.analyze_window(self.src, 0, 2000, faces_fn=lambda im: [], lane="cuda")
        self.assertEqual(len(cmds), 2)
        self.assertEqual(after(cmds[0], "-hwaccel"), "cuda")
        self.assertNotIn("-hwaccel", cmds[1])
        for c in cmds:
            self.assertEqual(after(c, "-i"), str(self.src))
        self.assertTrue(rep["shots"])


class TestPreflightShots(unittest.TestCase):
    """media.preflight (the verb) takes the "shots" slot once and passes its lane to shots.analyze_window."""

    def test_preflight_shot_analysis_lane(self):
        from test_podcast import ff
        from lib import shots
        from lib.media import preflight
        tmp = Path(tempfile.mkdtemp()) / AR_DIR
        self.addCleanup(shutil.rmtree, tmp.parent, True)
        root = tmp / "PF"
        for d in ("assets/Brand", "data/Episodes"):
            (root / d).mkdir(parents=True)
        src = root / "data/Episodes/حلقة 1.mp4"
        ff("-f", "lavfi", "-i", "testsrc2=s=640x360:r=25:d=3", "-f", "lavfi", "-i", "sine=f=300:r=48000:d=3",
           "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(src))
        seen = []

        def window(path, offset_ms, duration_ms, faces_fn=None, lane="cpu"):
            seen.append((lane, gpu_lock.held(), str(path)))
            return {"window": {"offset_ms": offset_ms, "duration_ms": duration_ms}, "cuts_ms": [], "shots": [],
                    "method": "fake", "note": ""}
        with use_context(Context(root, home=tmp / "home")), quiet():
            reel = Paths(root, "E_R01")
            reel.ensure_project()
            write_json(reel.p("00_inputs/source.json"), {"footage": "data/Episodes/حلقة 1.mp4", "in_ms": 500,
                                                          "out_ms": 2500, "duration_ms": 2000, "kind": "episode_reel"})
            with mock.patch.object(shots, "analyze_window", side_effect=window):
                for d in (CUDA, CPU_OFF):
                    with detect_as(d):
                        preflight(reel, [src])
            self.assertIsNone(gpu_lock.held())
        (gpu_lane, gpu_held, p1), (cpu_lane, cpu_held, p2) = seen
        self.assertEqual((gpu_lane, gpu_held["what"]), ("cuda", "shots"))
        self.assertEqual((cpu_lane, cpu_held), ("cpu", None))
        self.assertEqual((p1, p2), (str(src), str(src)))                   # the Arabic + space path, unchanged


class TestAudioCard(_Home):
    def test_audio_card_lanes(self):
        from lib import episode, reels
        src = self.tmp / AR_DIR / "حلقة صوت.m4a"
        out = self.tmp / "cands" / "R01.mp4"
        out.parent.mkdir(parents=True)
        cand = {"id": "R01", "in_ms": 1000, "out_ms": 3000, "total": 7.0, "type": "advice"}
        seen = []

        def run(cmd, **kw):
            seen.append([str(c) for c in cmd])
            return cp(cmd, 1, "", FF7_OPEN) if "h264_nvenc" in cmd else cp(cmd, 0)
        with mock.patch.object(episode, "episode_file", return_value=src), \
                mock.patch.object(common, "run", side_effect=run), quiet():
            reels.audio_card(None, cand, out)
            reels.audio_card(None, cand, out, lane="cuda")
        cpu, gpu, rerun = seen
        self.assertTrue(has_seq(cpu, ["-c:v", "libx264", "-tune", "stillimage", "-preset", "veryfast",
                                      "-pix_fmt", "yuv420p"]), cpu)                     # today's argv
        self.assertIn("h264_nvenc", gpu)
        self.assertNotIn("-tune", gpu)                                    # an x264-only option
        self.assertEqual(rerun, cpu)                                      # the GPU failure: once more, on the CPU
        for c in seen:
            self.assertIn(str(src), c)


class TestReelCandidates(unittest.TestCase):
    """render_candidates on a client folder with an Arabic name and spaces: real ffmpeg on the CPU, the GPU encoder
    replaced by a fake that fails with an NVENC error."""

    @classmethod
    def setUpClass(cls):
        from test_podcast import make_episode_client
        from lib.episode import EpisodePaths, prep
        from lib.transcribe import finalize
        cls.tmp = Path(tempfile.mkdtemp()) / AR_DIR
        cls.tmp.mkdir(parents=True)
        cls.root = make_episode_client(cls.tmp, with_clip=False)
        cls.ep = EpisodePaths(cls.root, "EP12")
        with quiet():
            prep(cls.ep)
            ws = [{"id": i + 1, "segment_id": 1, "word": f"كلمه{i}", "start_ms": i * 500, "end_ms": i * 500 + 400,
                   "probability": 0.9} for i in range(38)]
            finalize(cls.ep, {"source_video": "x", "backend": "test", "model": "none", "language": "ar",
                              "language_probability": 1.0, "duration_ms": 20000},
                     [{"id": 1, "start_ms": 0, "end_ms": ws[-1]["end_ms"], "text": " ".join(w["word"] for w in ws),
                       "avg_logprob": -0.2, "no_speech_prob": 0.0, "compression_ratio": 1.1,
                       "words": [w["id"] for w in ws]}], ws)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp.parent, ignore_errors=True)

    def go(self, detect):
        from test_podcast import validated_plan
        from lib.episode import episode_file
        from lib.reels import render_candidates
        validated_plan(self.ep, [{"id": "R01", "in_ms": 2000, "out_ms": 6000, "duration_ms": 4000, "type": "advice",
                                  "type_label": "نصيحة", "total": 7.5, "title": "t", "score": {}}])
        real, seen, self.helds = common.run, [], {}

        def run(cmd, *a, **kw):
            seen.append([str(c) for c in cmd])
            self.helds[id(seen[-1])] = gpu_lock.held()
            if "h264_nvenc" in cmd:
                return cp(cmd, 1, "", FF7_SESSIONS)
            return real(cmd, *a, **kw)
        with mock.patch.object(common, "run", run), detect_as(detect), quiet():
            r = render_candidates(self.ep)
        enc = [c for c in seen if "-filter_complex" in c]
        return r, enc, str(episode_file(self.ep))

    def test_cpu_lane_argv_is_todays(self):
        r, enc, src = self.go(CPU_OFF)
        self.assertTrue(r["ok"], r)
        (c,) = enc
        d = self.ep.p("03_candidates")
        self.assertEqual(c[1:], ["-y", "-loglevel", "error", "-ss", "2.000", "-t", "4.000", "-i", src,
                                 "-i", str(d / "_R01_label.png"), "-filter_complex",
                                 "[0:v]scale=540:-2,pad=540:960:0:(oh-ih)/2:color=0x111111[v];[v][1:v]overlay=0:0[o]",
                                 "-map", "[o]", "-map", "0:a:0?", "-c:v", "libx264", "-preset", "veryfast", "-crf", "28",
                                 "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "96k", "-movflags", "+faststart",
                                 str(d / "R01.mp4")])

    def test_prep_takes_the_thumbs_slot_once_and_passes_the_lane(self):
        from lib import overlay_scan as OS
        from lib.episode import prep
        seen = []

        def scan(src, dur_s, **kw):
            seen.append((kw.get("lane"), gpu_lock.held()))
            return {"events": [], "scanned_s": dur_s, "duration_s": dur_s, "complete": True, "elapsed_s": 0.0,
                    "step_s": 1.0, "ref_s": 4, "budget_s": 300.0}
        with detect_as(CUDA), mock.patch.dict(accel.SITE_LANES, {"thumbs": "gpu"}), \
                mock.patch.object(OS, "scan_video", side_effect=scan), quiet():
            prep(self.ep)
        self.assertEqual(len(seen), 1)
        self.assertEqual(seen[0][0], "cuda")
        self.assertEqual(seen[0][1]["what"], "thumbs")
        self.assertIsNone(gpu_lock.held())

    def episode_transcribe(self, lane, inject):
        from lib import whisper_backends as WB
        from lib.episode import transcribe_episode
        seen = {}

        def fake(audio, start_ms, language, prompt):
            seen["held_slot"] = seen.get("slot")
            return {"language": "ar", "language_probability": 0.97,
                    "segments": [{"id": 1, "start_ms": 100, "end_ms": 900, "text": "كلام", "avg_logprob": -0.2,
                                  "no_speech_prob": 0.0, "compression_ratio": 1.1, "words": [1]}],
                    "words": [{"id": 1, "segment_id": 1, "word": "كلام", "start_ms": 100, "end_ms": 900,
                               "probability": 0.9}]}
        fake.backend = "ct2"

        def factory(model_size, vad, log_to=None, **k):
            seen["device"] = k.get("device", "not passed")
            return fake
        with mock.patch.object(gpu_lock, "whisper_slot", side_effect=whisper_slot_fake(seen, lane)), \
                mock.patch.object(WB, "make_runner", side_effect=factory), quiet():
            transcribe_episode(self.ep, "small", run_chunk=fake if inject else None, chunk_ms=8000, force=True)
        return seen

    def test_episode_transcription_takes_the_whisper_slot(self):
        """P1-2: a whole episode is the longest GPU job: it holds the Whisper slot for the runner and every chunk."""
        seen = self.episode_transcribe("cpu", inject=False)
        self.assertEqual((seen["slot"], seen["device"]), (("transcribe", 600), "cpu"))
        self.assertEqual(seen["held_slot"], ("transcribe", 600))          # the chunks ran inside the slot
        self.assertIsNone(self.episode_transcribe("cuda", inject=False)["device"])
        self.assertEqual(self.episode_transcribe("cpu", inject=True)["slot"], ("transcribe", 600))

    def test_cuda_lane_gpu_failure_renders_on_cpu(self):
        r, enc, src = self.go(CUDA)
        self.assertTrue(r["ok"], r)
        gpu, cpu = enc
        self.assertEqual(self.helds[id(gpu)]["what"], "reel_candidates")
        self.assertIsNone(self.helds[id(cpu)])                           # the CPU re-run left the GPU lock free
        self.assertEqual(after(gpu, "-hwaccel"), "cuda")
        self.assertTrue(has_seq(gpu, ["-c:v", "h264_nvenc", "-preset", "p4", "-rc", "vbr", "-cq", "28", "-b:v", "0"]))
        self.assertNotIn("-hwaccel", cpu)
        self.assertTrue(has_seq(cpu, ["-c:v", "libx264", "-preset", "veryfast", "-crf", "28", "-pix_fmt", "yuv420p"]))
        for c in enc:
            self.assertEqual(after(c, "-i"), src)
        self.assertIn(AR_DIR, src)
        self.assertTrue(self.ep.p("03_candidates/R01.mp4").stat().st_size > 1000)
        self.assertIsNone(gpu_lock.held())


def cpu_twin(cmd):
    """The CPU version of a GPU ffmpeg argv: no -hwaccel pair, libx264 instead of the NVENC arguments."""
    out, i = [], 0
    while i < len(cmd):
        if cmd[i] == "-hwaccel":
            i += 2
            continue
        if cmd[i] == "-c:v" and i + 1 < len(cmd) and cmd[i + 1] == "h264_nvenc":
            out += ["-c:v", "libx264", "-preset", "veryfast", "-crf", cmd[i + 7]]
            i += 10
            continue
        out.append(cmd[i])
        i += 1
    return out


class TestPreviewVideoLanes(unittest.TestCase):
    """preview-video in both lanes on a project in a folder with an Arabic name and spaces (test_perf's fixture)."""

    @classmethod
    def setUpClass(cls):
        from test_perf import build_preview_project
        cls.tmp = Path(tempfile.mkdtemp()) / AR_DIR
        cls.tmp.mkdir(parents=True)
        with quiet():
            cls.ctx, cls.p = build_preview_project(cls.tmp)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp.parent, ignore_errors=True)

    def render(self, detect=CPU_OFF, fail=None, err=FF7_OOM, helds=None, **kw):
        """Render; records every ffmpeg argv the render starts (and, in `helds`, the GPU lock's holder at that moment).
        A GPU argv runs as its CPU twin (there is no GPU in the suite); `fail(argv)` True -> that GPU encoder is a fake
        that prints `err` (ffmpeg 7.1's real multi-line stderr) and exits 1."""
        from lib import preview_video as PV
        real, rec, cats = subprocess.Popen, [], []
        realrun = PV.run

        def popen(cmd, *a, **k):
            if isinstance(cmd, list):
                rec.append([str(c) for c in cmd])
                if helds is not None:
                    helds.append(gpu_lock.held())
                if ("h264_nvenc" in cmd or "h264_videotoolbox" in cmd) and fail and fail(cmd):
                    cmd = [sys.executable, "-c", "import sys; sys.stdin.buffer.read(); "
                           f"sys.stderr.write({err!r}); sys.exit(1)"]
                else:
                    cmd = cpu_twin(cmd)
            return real(cmd, *a, **k)

        def run(cmd, *a, **k):
            if "concat" in cmd:
                cats.append(len(rec))
            return realrun(cmd, *a, **k)
        with use_context(self.ctx), detect_as(detect), mock.patch.object(PV.subprocess, "Popen", side_effect=popen), \
                mock.patch.object(PV, "run", side_effect=run), quiet():
            r = PV.render(self.p, width=270, **kw)
        return r, rec, cats

    @staticmethod
    def encoders(rec):
        return [c for c in rec if has_seq(c, ["-f", "rawvideo", "-pix_fmt", "rgb24", "-s"])]

    @staticmethod
    def decoders(rec):
        return [c for c in rec if c[-1] == "-" and "-s" not in c]

    def test_preview_video_cpu_lane_argv_unchanged(self):
        r, rec, _ = self.render(workers=1)
        self.assertTrue(r["ok"], r)
        self.assertEqual(r["lane"], "cpu")
        (enc,) = self.encoders(rec)
        out_dir = self.p.p("08_quality_control/preview")
        with use_context(self.ctx):
            fps = common.fps_arg()
        self.assertEqual(enc[1:], ["-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", r["size"],
                                   "-r", fps, "-i", "-", "-i", str(out_dir / "_preview_audio.wav"),
                                   "-c:v", "libx264", "-preset", "veryfast", "-crf", "23", "-pix_fmt", "yuv420p",
                                   "-c:a", "aac", "-b:a", "160k", "-shortest", "-movflags", "+faststart", r["video"]])
        self.assertFalse(any("-hwaccel" in c for c in rec))
        self.assertIn(AR_DIR, r["video"])

    def test_preview_video_cuda_lane_uses_nvenc_and_hwaccel(self):
        r, rec, _ = self.render(detect=CUDA, workers=1)
        self.assertTrue(r["ok"], r)
        self.assertEqual(r["lane"], "cuda")
        self.assertNotIn("gpu_fallback", r)
        (enc,) = self.encoders(rec)
        self.assertTrue(has_seq(enc, NVENC_23), enc)
        (dec,) = self.decoders(rec)
        self.assertLess(dec.index("-hwaccel"), dec.index("-i"))
        self.assertEqual(after(dec, "-hwaccel"), "cuda")
        self.assertIn(AR_DIR, after(dec, "-i"))
        self.assertTrue(Path(after(dec, "-i")).is_file())             # the source path, unchanged
        self.assertIsNone(gpu_lock.held())

    def test_preview_video_any_chunk_gpu_failure_rerenders_all_on_cpu(self):
        """The lossless concat needs one codec in every chunk: chunk 1's NVENC failure re-renders BOTH on the CPU."""
        helds = []
        r, rec, cats = self.render(detect=CUDA, fail=lambda c: c[-1].endswith("_preview_chunk_1.mp4"),
                                   workers=2, min_chunk_frames=8, helds=helds)
        self.assertTrue(r["ok"], r)
        self.assertEqual((r["lane"], r["chunks"]), ("cpu", 2))
        self.assertEqual(r["gpu_fallback"], accel.GPU_FALLBACK_EN)
        enc = self.encoders(rec)
        self.assertEqual(["h264_nvenc" in c for c in enc], [True, True, False, False])
        self.assertTrue(all(has_seq(c, CPU_X264) for c in enc[2:]))
        self.assertEqual(sorted(c[-1][-5] for c in enc[2:]), ["0", "1"])  # both chunks again
        self.assertEqual(len(cats), 1)                                   # one join, after the CPU chunks only
        self.assertIn("concat", rec[cats[0]])                            # (the join's own ffmpeg comes next)
        self.assertLess(max(i for i, c in enumerate(rec) if c in enc), cats[0])
        self.assertEqual(list(self.p.p("08_quality_control/preview").glob("_preview_chunk*")), [])
        by = {id(c): h for c, h in zip(rec, helds)}
        self.assertTrue(all(by[id(c)] and by[id(c)]["what"] == "preview_video" for c in enc[:2]))
        self.assertTrue(all(by[id(c)] is None for c in enc[2:]))       # the CPU re-render left the GPU lock free

    def test_preview_video_single_pass_gpu_failure_renders_on_cpu(self):
        for detect, err, enc_name in ((CUDA, FF7_OPEN, "h264_nvenc"), (CUDA, FF7_SESSIONS, "h264_nvenc"),
                                      (VT, FF7_VT, "h264_videotoolbox")):
            with self.subTest(err=err.splitlines()[0][:60]):
                r, rec, _ = self.render(detect=detect, fail=lambda c: True, err=err, workers=1)
                self.assertTrue(r["ok"], r)
                self.assertEqual(r["lane"], "cpu")
                self.assertEqual([enc_name in c for c in self.encoders(rec)], [True, False])

    def test_a_non_gpu_encoder_failure_is_still_an_error(self):
        """Only a GPU failure re-renders on the CPU; the generic ffmpeg 7 tail alone is the usual refusal."""
        from lib.errors import Guidance
        with self.assertRaises(Guidance) as cm:
            self.render(detect=CUDA, fail=lambda c: True, err="\n".join(_FF7_TAIL) + "\n", workers=1)
        self.assertIn("Nothing was written", cm.exception.error)          # the 3-line message stays short
        self.assertNotIn("Error sending frames", cm.exception.error)


class TestAnimaticEncode(_Home):
    def frames(self):
        return (bytes([k * 20]) * (64 * 64 * 3) for k in range(10))

    def real_cmd(self, out):
        return [common.ffmpeg_exe(), "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", "64x64",
                "-r", "10", "-i", "-", "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p", str(out)]

    def test_cmd_lanes(self):
        from lib import motion_animatic as MA
        wav, mp4 = self.tmp / AR_DIR / "mix 1.wav", self.tmp / AR_DIR / "انيماتك 1.mp4"
        with mock.patch.object(MA, "ffmpeg_exe", return_value="ffmpeg"):
            cpu, gpu = MA._cmd(64, 64, wav, 2.0, mp4, "cpu"), MA._cmd(64, 64, wav, 2.0, mp4, "cuda")
        self.assertEqual(cpu, ["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", "64x64",
                               "-r", str(MA.ANIM_FPS), "-i", "-", "-i", str(wav), "-map", "0:v", "-map", "1:a",
                               "-c:v", "libx264", "-preset", "veryfast", "-crf", "26", "-pix_fmt", "yuv420p",
                               "-c:a", "aac", "-b:a", "128k", "-t", "2.000", "-movflags", "+faststart", str(mp4)])
        self.assertTrue(has_seq(gpu, ["-c:v", "h264_nvenc", "-preset", "p4", "-rc", "vbr", "-cq", "26", "-b:v", "0"]))
        self.assertEqual((gpu[gpu.index("-map") - 1], gpu[-1]), (str(wav), str(mp4)))

    def test_gpu_failure_reencodes_on_cpu(self):
        from lib import motion_animatic as MA
        for err in (FF7_OPEN, FF7_OOM, FF7_SESSIONS):
            with self.subTest(err=err.splitlines()[0][:60]):
                out, lanes = self.tmp / "a.mp4", []
                bad = [sys.executable, "-c",
                       f"import sys; sys.stdin.buffer.read(); sys.stderr.write({err!r}); sys.exit(1)"]

                def build(lane):
                    lanes.append(lane)
                    return bad if lane == "cuda" else self.real_cmd(out)
                with quiet():
                    rc, e, lane = MA._encode(build, "cuda", self.frames, self.tmp / "_err.log",
                                             release=lambda: lanes.append("released"))
                self.assertEqual((rc, lane, lanes), (0, "cpu", ["cuda", "released", "cpu"]))   # slot freed first
        self.assertTrue(out.stat().st_size > 0)

    def test_an_encoder_that_dies_early_is_reported(self):
        from lib import motion_animatic as MA
        die = [sys.executable, "-c", "import sys; sys.stderr.write('Conversion failed!'); sys.exit(1)"]
        rc, err, lane = MA._encode(lambda ln: die, "cpu", self.frames, self.tmp / "_err.log")
        self.assertEqual((rc, lane), (1, "cpu"))
        self.assertIn("Conversion failed", err)


# --------------------------------------------------------------------------- finals stay libx264
class TestFinalsUntouched(_Home):
    def test_motion_render_final_is_always_libx264(self):
        from lib import ae_render, audio_clean, motion_build, stamps
        from lib import motion_render as MR
        root = self.tmp / AR_DIR
        paths = Paths(root, "EP1_R01_MO")
        paths.ensure_project()
        aep = paths.p("04_after_effects/x.aep")
        aep.parent.mkdir(parents=True, exist_ok=True)
        aep.write_bytes(b"aep")
        plan = {"reel_id": "R01", "fps": 25, "duration_frames": 50, "w": 1080, "h": 1920, "scenes": [{"hero_frame": 10}]}
        seen = []

        def run(cmd, **kw):
            seen.append([str(c) for c in cmd])
            Path(cmd[-1]).parent.mkdir(parents=True, exist_ok=True)
            Path(cmd[-1]).write_bytes(b"mp4")
            return cp(cmd, 0)
        with detect_as(CUDA), use_context(Context(root, home=self.home)), \
                mock.patch.object(stamps, "read_compiled", return_value=plan), \
                mock.patch.object(motion_build, "aep_path", return_value=aep), \
                mock.patch.object(motion_build, "render_path", return_value=paths.p("04_after_effects/render/m.mov")), \
                mock.patch.object(MR, "_templates", return_value=("Best Settings", "High Quality")), \
                mock.patch.object(ae_render, "render", return_value={"status": "RENDERED"}), \
                mock.patch.object(MR, "_probe", return_value={"w": 1080, "h": 1920, "fps": 25, "duration_s": 2.0,
                                                              "audio": True}), \
                mock.patch.object(MR, "run", side_effect=run), \
                mock.patch.object(audio_clean, "_lufs", return_value=-14.0), \
                mock.patch.object(ae_render, "extract_frames", return_value=[]), \
                mock.patch.object(common, "set_status"), mock.patch.object(common, "load_status", return_value={}):
            res = MR.render(paths)
        self.assertEqual(res["status"], "RENDERED", res)
        (final,) = seen
        self.assertTrue(has_seq(final, ["-c:v", "libx264", "-crf", "18", "-pix_fmt", "yuv420p"]), final)
        self.assertFalse({"-hwaccel", "h264_nvenc", "h264_videotoolbox"} & set(final))
        src = (ENGINE / "lib" / "motion_render.py").read_text(encoding="utf-8")
        self.assertNotIn("accel", src)
        self.assertNotIn("gpu_", src)


# --------------------------------------------------------------------------- transcription
class TestWhisperDevice(_Home):
    def test_make_runner_device_cpu_loads_on_the_cpu(self):
        from lib import whisper_backends as WB
        got = []

        def load(model, compute_type="int8", device=None):
            got.append(device)
            return object(), "cpu", "int8"
        real_tries = WB._device_tries

        def tries(cfg, device, compute_type):      # no CUDA query in the suite: "auto" is a CPU machine here
            self.assertIn(device, (None, "cpu"))
            return real_tries(cfg, device, compute_type) if device else [("cpu", compute_type)]
        with mock.patch.object(WB, "load_ct2", side_effect=load), mock.patch.object(WB, "_device_tries", tries), \
                quiet():
            run = WB.make_runner("large-v3", vad=True, backend="ct2", batch_size=4, device="cpu")
            self.assertEqual(run.signature(), {"device": "cpu", "batch_size": 0, "vad": True})
            run.load()
            WB.make_runner("large-v3", vad=True, backend="ct2", batch_size=4).load()
        self.assertEqual(got, ["cpu", None])                              # no device: Whisper's own choice, as before

    def test_mlx_with_device_cpu_uses_faster_whisper_on_the_cpu(self):
        from lib import whisper_backends as WB
        with mock.patch.object(WB, "choose_backend", return_value=("mlx", None)), quiet():
            self.assertEqual(WB.make_runner("large-v3", vad=True).backend, "mlx")
            run = WB.make_runner("large-v3", vad=True, device="cpu")
        self.assertEqual(run.backend, "ct2")
        self.assertEqual(run.signature()["device"], "cpu")


def whisper_slot_fake(seen, lane):
    @contextlib.contextmanager
    def slot(what="transcribe", *, wait_s=None, backend=None, **kw):
        seen["slot"] = (what, gpu_lock.WAITS["transcribe"] if wait_s is None else wait_s)
        yield lane
    return slot


class TestTranscribeLane(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="whynot-t410-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.root = self.tmp / AR_DIR
        for d in ("assets", "data/Raw", common.CLIENT_PROFILE_REL):
            (self.root / d).mkdir(parents=True)
        self.src = self.root / "data/Raw/C0001.mp4"
        self.src.write_bytes(b"not really a video" * 100)
        self.paths = Paths(self.root, "C0001")
        self.paths.ensure_project()

    def go(self, lane, detect=CUDA, env="off", slot=None, seen=None):
        """transcribe() with the Whisper slot yielding `lane` (or `slot`); the seen dict, or with `seen` given, the
        transcribe result."""
        from lib import transcribe as T
        from lib import whisper_backends as WB
        ret = seen
        seen = {} if seen is None else seen

        def fake(audio, start_ms, language, prompt):
            return {"language": "ar", "language_probability": 0.9,
                    "segments": [{"id": 1, "start_ms": 100, "end_ms": 900, "text": "كلام", "avg_logprob": -0.2,
                                  "no_speech_prob": 0.0, "compression_ratio": 1.1, "words": [1]}],
                    "words": [{"id": 1, "segment_id": 1, "word": "كلام", "start_ms": 100, "end_ms": 900,
                               "probability": 0.9}]}
        fake.backend = "ct2"

        slot = slot or whisper_slot_fake(seen, lane)

        def factory(model_size, vad, log_to=None, **k):
            seen["device"] = k.get("device", "not passed")
            return fake
        with use_context(Context(self.root)), mock.patch.dict(os.environ, {"WHYNOT_ACCEL": env}), detect_as(detect), \
                mock.patch.object(T, "extract_audio", side_effect=lambda src, dst, rng=None: dst), \
                mock.patch.object(T, "whisper_audio", return_value=np.zeros(16000 * 20, np.float32)), \
                mock.patch.object(WB, "make_runner", side_effect=factory), \
                mock.patch.object(gpu_lock, "gpu_slot", side_effect=AssertionError("transcription: whisper_slot")), \
                mock.patch.object(gpu_lock, "whisper_slot", side_effect=slot), quiet():
            res = T.transcribe(self.paths, self.src, model_size="large-v3")
        return seen if ret is None else res

    def test_transcribe_cpu_lane_forces_device_cpu(self):
        seen = self.go("cpu", env="auto")                                  # the GPU was busy: CPU this time
        self.assertEqual(seen, {"slot": ("transcribe", 600), "device": "cpu"})
        self.assertEqual(self.go("cpu", detect=CPU_OFF)["device"], "cpu")  # WHYNOT_ACCEL=off: the escape hatch

    def test_transcription_time_starts_after_the_slot(self):
        """P3: elapsed_s is the transcription; the time spent waiting for the GPU is its own field."""
        from lib import transcribe as T
        now = [1000.0]
        seen = {}

        @contextlib.contextmanager
        def slow_slot(what="transcribe", **kw):
            now[0] += 50.0                                                 # 50 s waiting for another job
            yield "cpu"
        fake = SimpleNamespace(time=lambda: now[0], strftime=time.strftime)
        with mock.patch.object(T, "time", fake):
            r = self.go("cpu", slot=slow_slot, seen=seen)
        self.assertEqual(r["meta"]["elapsed_s"], 0.0)
        self.assertEqual(r["meta"]["gpu_wait_s"], 50.0)

    def test_transcribe_gpu_lane_lets_whisper_choose(self):
        self.assertIsNone(self.go("cuda", env="auto")["device"])
        self.assertIsNone(self.go("mlx", detect=VT, env="auto")["device"])   # MLX / Metal stays as it was


# --------------------------------------------------------------------------- doctor
class TestDoctor(_Home):
    def test_doctor_names_the_accelerator(self):
        from lib import onboard, plat, portability
        self.env("auto")
        gpu = {"cuda_devices": 1, "whisper_device": "cuda", "name": GPU_NAME + ", 8188 MiB", "cuda_libs_missing": []}
        with detect_as(CUDA) as det, mock.patch.object(plat, "gpu_info", return_value=gpu), \
                mock.patch.object(portability, "doctor_checks", return_value=({}, [])):
            rep = onboard.doctor()
        self.assertTrue(all(c.kwargs.get("refresh") is True for c in det.call_args_list), det.call_args_list)
        self.assertEqual(rep["accelerator"]["line"],
                         "Video: NVIDIA GeForce RTX 4060 Laptop GPU (NVENC/NVDEC) · transcription: CUDA float16")
        self.assertEqual(rep["accelerator"]["video"], CUDA)
        self.assertEqual(rep["accelerator"]["transcription"], "cuda")

    def test_doctor_cpu_and_mac_lines(self):
        from lib import onboard
        self.env("auto")
        why = "h264_nvenc is listed but did not work: No capable devices found"
        cpu = onboard.accelerator(dict(CPU_OFF, why=why), {"whisper_device": "cpu"}, backend="ct2")
        self.assertEqual(cpu["line"], f"Video: CPU — {why} · transcription: CPU")
        with mock.patch.dict(os.environ, {"WHYNOT_ACCEL": "off"}):          # a CUDA PC, turned off
            off = onboard.accelerator(dict(CPU_OFF), {"whisper_device": "cuda"}, backend="ct2")
        self.assertEqual(off["line"], "Video: CPU — turned off (WHYNOT_ACCEL=off) · transcription: CPU")
        self.assertEqual(onboard.accelerator(VT, {"whisper_device": "cpu"}, backend="mlx")["line"],
                         "Video: Apple VideoToolbox · transcription: MLX")
        self.assertEqual(onboard.accelerator(VT, {"whisper_device": "cpu"}, backend="ct2")["line"],
                         "Video: Apple VideoToolbox · transcription: CPU")


# --------------------------------------------------------------------------- dev tools (not shipped)
def _tool(name):
    spec = importlib.util.spec_from_file_location(f"_wnc_tool_{name}", SK.parent / "tools" / f"{name}.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


class TestDevTools(unittest.TestCase):
    def test_footprint_summary_and_nvidia_smi(self):
        fp = _tool("footprint")
        s = fp.summarize([{"t": 0.0, "rss_mb": 100.0, "cpu_pct": 50.0, "gpu_pct": None, "vram_mb": None},
                          {"t": 0.5, "rss_mb": 300.0, "cpu_pct": 150.0, "gpu_pct": 40.0, "vram_mb": 1200.0}])
        self.assertEqual(s["samples"], 2)
        self.assertEqual(s["rss_mb"], {"peak": 300.0, "mean": 200.0})
        self.assertEqual(s["cpu_pct"], {"peak": 150.0, "mean": 100.0})
        self.assertEqual(s["gpu_pct"], {"peak": 40.0, "mean": 40.0})
        self.assertEqual(s["vram_mb"], {"peak": 1200.0, "mean": 1200.0})
        self.assertEqual(fp.summarize([])["rss_mb"], {"peak": None, "mean": None})
        self.assertEqual(fp.parse_nvidia_smi("37, 1234\n"), (37.0, 1234.0))
        self.assertEqual(fp.parse_nvidia_smi("[N/A], 512\n"), (None, 512.0))
        self.assertEqual(fp.parse_nvidia_smi(""), (None, None))
        self.assertEqual(fp.SAMPLE_S, 0.5)

    def test_bench_ssim_and_rules(self):
        bm = _tool("bench_media")
        self.assertEqual(bm.parse_ssim("[Parsed_ssim_0 @ 0000] SSIM Y:0.991 (20.4) U:0.99 (21) V:0.99 (21) "
                                       "All:0.987654 (19.1)\n"), 0.987654)
        self.assertIsNone(bm.parse_ssim("Conversion failed!"))
        self.assertEqual(bm.lane_rule(10.0, 8.5, 0.98), "gpu")             # 15 % faster, SSIM 0.98: keeps the GPU
        self.assertEqual(bm.lane_rule(10.0, 8.6, 0.999), "cpu")            # only 14 % faster
        self.assertEqual(bm.lane_rule(10.0, 5.0, 0.979), "cpu")            # fast but not the same picture
        self.assertEqual(bm.lane_rule(10.0, None, None), "cpu")            # the GPU run failed
        self.assertEqual(bm.final_rule(0.996)["switch"], False)            # finals never switch here (G10)
        self.assertTrue(bm.final_rule(0.996)["candidate"])
        self.assertFalse(bm.final_rule(0.994)["candidate"])

    def test_bench_site_commands(self):
        bm = _tool("bench_media")
        src, out = str(Path(tempfile.gettempdir()) / AR_DIR / "حلقة 1.mp4"), "out 1.mkv"
        for site in list(accel.SITE_LANES) + ["final"]:
            for lane in ("cpu", "cuda"):
                with self.subTest(site=site, lane=lane):
                    c = bm.site_cmd(site, lane, ff="ffmpeg", src=src, out=out)
                    self.assertEqual(after(c, "-i"), src)
                    self.assertEqual(c[-1], out)
                    self.assertEqual("-hwaccel" in c, lane == "cuda" and site != "final")
        self.assertTrue(has_seq(bm.site_cmd("preview_video", "cuda", ff="ffmpeg", src=src, out=out), NVENC_23))
        self.assertTrue(has_seq(bm.site_cmd("preview_video", "cpu", ff="ffmpeg", src=src, out=out), CPU_X264))
        self.assertTrue(has_seq(bm.site_cmd("final", "cpu", ff="ffmpeg", src=src, out=out),
                                ["-c:v", "libx264", "-crf", "18"]))
        self.assertTrue(has_seq(bm.site_cmd("final", "cuda", ff="ffmpeg", src=src, out=out),
                                ["-c:v", "h264_nvenc", "-preset", "p4", "-rc", "vbr", "-cq", "18", "-b:v", "0"]))
        self.assertEqual(bm.ssim_cmd("ffmpeg", "a 1.mkv", "ب 2.mkv"),
                         ["ffmpeg", "-hide_banner", "-nostdin", "-i", "a 1.mkv", "-i", "ب 2.mkv", "-lavfi", "ssim",
                          "-f", "null", "-"])


if __name__ == "__main__":
    unittest.main()
