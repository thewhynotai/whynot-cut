# SPDX-License-Identifier: GPL-3.0-or-later
# © 2026 The Why Not AI (thewhynot.ai)
"""Task 26 conform wiring, engine half (hooks/t26/CONTRACT.md): after a preflight the engine makes the evenly timed /
SDR copy of each main-footage file whose `normalise.decision.actions` is not empty, and records it in
`00_inputs/preflight.json` -> `files[i].normalise.conform` exactly as the contract says (ready | pending | failed |
not_needed, client-root-relative POSIX paths, parts with source-clock ms, cfr_fps, source_tag, source_size, reason, lines,
at). A stale source never keeps `ready`; an old preflight.json without the key is never touched; intake never fails
because the copy failed. `reel conform [--wait]` re-runs it for one item.
The suite runs with WHYNOT_ACCEL=off (tests/_isolation.py): every encode here is the CPU lane.
Run:  bash tools/test.sh -p test_t26_conform_wiring.py
"""
import sys as _sys
_sys.dont_write_bytecode = True  # keep the plugin folder free of __pycache__
import _isolation  # noqa: F401,E402  G79: sandbox the engine home first (tests/_isolation.py)
import contextlib
import hashlib
import importlib.util
import io
import json
import os
import re
import shutil
import subprocess
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

SK = Path(__file__).resolve().parents[1]
if str(SK / "engine" / "reel") not in _sys.path:
    _sys.path.insert(0, str(SK / "engine" / "reel"))

from lib import media, media_normalise as MN  # noqa: E402
from lib.common import Paths, ffmpeg_exe, read_json, write_json  # noqa: E402

FX = SK / "tests" / "fixtures" / "media_normalise"
CLI = SK / "engine" / "reel" / "cli.py"
KEYS = {"state", "path", "parts", "cfr_fps", "source_tag", "source_size", "reason", "lines", "at"}
ARABIC = re.compile("[؀-ۿ]")


@contextlib.contextmanager
def quiet():
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        yield


def ff(*args):
    subprocess.run([ffmpeg_exe(), "-v", "error", "-y", *args], check=True, capture_output=True)


def make_vfr(out: Path, seconds: int = 3):
    """A phone-style VFR clip with audio: 30 fps for `seconds`, then 15 fps for `seconds`, vertical 180x320."""
    out.parent.mkdir(parents=True, exist_ok=True)
    ff("-f", "lavfi", "-i", f"testsrc2=s=180x320:r=30:d={seconds}", "-f", "lavfi", "-i", f"testsrc2=s=180x320:r=15:d={seconds}",
       "-f", "lavfi", "-i", f"sine=frequency=440:sample_rate=48000:duration={2 * seconds}",
       "-filter_complex", "[0:v][1:v]concat=n=2:v=1[v]", "-map", "[v]", "-map", "2:a", "-fps_mode", "vfr",
       "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", "-c:a", "aac", str(out))
    return out


def reel(root: Path, *argv, video_id=None, env=None):
    cmd = [_sys.executable, "-B", str(CLI), "--root", str(root)] + (["--video-id", video_id] if video_id else []) + list(argv)
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", env=dict(os.environ, **(env or {})),
                       timeout=600)
    doc = None
    try:
        doc = json.loads(r.stdout)
    except ValueError:
        pass
    return r.returncode, doc, r.stdout + r.stderr


def frame_times(path):
    import av
    with av.open(str(path)) as c:
        s = c.streams.video[0]
        return sorted(float(p.pts * s.time_base) for p in c.demux(s) if p.pts is not None)


def stream_rates(path):
    import av
    with av.open(str(path)) as c:
        s = c.streams.video[0]
        return float(s.average_rate), float(s.base_rate)


class _Client(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="whynot-t26w-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.root = self.tmp / "Client One"
        (self.root / "assets").mkdir(parents=True)
        (self.root / "data" / "Raw").mkdir(parents=True)
        env = mock.patch.dict(os.environ, {"WHYNOT_CONFORM": "off"})     # each test starts the job itself
        env.start()
        self.addCleanup(env.stop)

    def clip(self, name, vid="V1", fname=None):
        f = self.root / "data" / "Raw" / (fname or f"{name}.mp4")
        shutil.copyfile(FX / f"{name}.mp4", f)
        p = Paths(self.root, vid)
        p.ensure_project()
        return p, f

    def preflight(self, p, f):
        with quiet():
            return media.preflight(p, [f])

    def job(self, p, **kw):
        with quiet():
            return media.run_conform_job(p, **kw)

    def doc(self, p):
        return read_json(p.p("00_inputs/preflight.json"))

    def rec(self, p, i=0):
        return self.doc(p)["files"][i]["normalise"]["conform"]

    def assertContract(self, r):
        self.assertEqual(set(r), KEYS, r)
        self.assertIn(r["state"], ("ready", "pending", "failed", "not_needed"))
        self.assertRegex(r["source_tag"], r"^[0-9a-f]{10}$")
        self.assertIsInstance(r["source_size"], int)
        self.assertEqual(set(r["lines"]), {"ar", "en"})
        self.assertRegex(r["at"], r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d")
        for part in r["parts"]:
            self.assertEqual(set(part), {"path", "from_ms", "to_ms"}, part)
            self.assertIsInstance(part["from_ms"], int)
            self.assertIsInstance(part["to_ms"], int)

    def assertInsideOutput(self, rel):
        self.assertIsInstance(rel, str)
        self.assertNotIn("\\", rel)
        self.assertFalse(rel.startswith("/") or re.match(r"^[A-Za-z]:", rel), rel)
        self.assertNotIn("..", rel.split("/"))
        self.assertTrue(rel.startswith("output/"), rel)
        full = (self.root / rel).resolve()
        self.assertTrue(full.is_file(), full)
        full.relative_to((self.root / "output").resolve())             # raises when outside output/


# --------------------------------------------------------------------------- the four states
class TestRecordStates(_Client):
    def test_not_needed(self):
        p, f = self.clip("cfr30")
        rep = self.preflight(p, f)
        self.assertTrue(rep["ok"])
        r = self.rec(p)
        self.assertContract(r)
        self.assertEqual(r["state"], "not_needed")
        self.assertEqual((r["path"], r["parts"], r["cfr_fps"]), (None, [], None))
        self.assertEqual(r["source_tag"], MN._source_tag(f, p.root))
        self.assertEqual(r["source_size"], f.stat().st_size)
        res = self.job(p)
        self.assertEqual(res["state"], "not_needed")
        self.assertFalse(p.p("00_inputs/intermediates").exists())        # nothing to make, nothing written

    def test_pending_after_preflight(self):
        p, f = self.clip("tag60_real30")
        self.preflight(p, f)
        r = self.rec(p)
        self.assertContract(r)
        self.assertEqual(r["state"], "pending")
        self.assertEqual((r["path"], r["parts"], r["cfr_fps"]), (None, [], 30.0))
        self.assertTrue(r["lines"]["ar"] and ARABIC.search(r["lines"]["ar"][0]), r)
        self.assertTrue(r["lines"]["en"] and not ARABIC.search(r["lines"]["en"][0]), r)
        self.assertFalse(list(p.project.rglob("*.conform*.mp4")))         # preflight itself encodes nothing

    def test_ready_after_the_job(self):
        p, f = self.clip("tag60_real30")
        before = hashlib.sha256(f.read_bytes()).hexdigest()
        self.preflight(p, f)
        res = self.job(p)
        self.assertEqual(res["state"], "ready", res)
        r = self.rec(p)
        self.assertContract(r)
        self.assertEqual(r["state"], "ready")
        self.assertEqual(r["parts"], [])
        self.assertInsideOutput(r["path"])
        self.assertTrue(r["path"].startswith("output/projects/V1/00_inputs/intermediates/"), r["path"])
        self.assertTrue(r["path"].endswith(".conform.mp4"), r["path"])
        self.assertIn(r["source_tag"], r["path"])
        self.assertEqual(r["cfr_fps"], 30.0)
        self.assertEqual(r["source_size"], f.stat().st_size)
        self.assertEqual(hashlib.sha256(f.read_bytes()).hexdigest(), before)      # the original is never changed
        av_, base = stream_rates(self.root / r["path"])
        self.assertAlmostEqual(base, 30.0, places=2)

    def test_failed_has_a_reason_and_both_lines(self):
        p, f = self.clip("tag60_real30")
        rep = self.preflight(p, f)
        self.assertTrue(rep["ok"])
        with mock.patch.object(MN, "_engine_ffmpeg", lambda: None):
            res = self.job(p)
        self.assertEqual(res["state"], "failed")
        r = self.rec(p)
        self.assertContract(r)
        self.assertEqual(r["state"], "failed")
        self.assertEqual((r["path"], r["parts"]), (None, []))
        self.assertIn("ffmpeg", r["reason"])
        self.assertTrue(ARABIC.search(r["lines"]["ar"][0]))
        self.assertIn("FFmpeg", r["lines"]["en"][0])
        self.assertTrue(self.doc(p)["ok"])                                # the preflight result stays as it was

    def test_the_summary_lists_every_file(self):
        p, f = self.clip("tag60_real30")
        g = self.root / "data" / "Raw" / "cfr30.mp4"
        shutil.copyfile(FX / "cfr30.mp4", g)
        with quiet():
            media.preflight(p, [f, g])
        res = self.job(p)
        self.assertEqual([x["state"] for x in res["files"]], ["ready", "not_needed"])
        self.assertEqual(res["state"], "ready")
        self.assertEqual([x["file"] for x in res["files"]], ["data/Raw/tag60_real30.mp4", "data/Raw/cfr30.mp4"])


class TestPaths(_Client):
    def test_a_linked_output_folder_still_gives_a_root_relative_path(self):
        far = self.tmp / "other drive" / "client output"
        far.mkdir(parents=True)
        try:
            if os.name == "nt":
                subprocess.run(["cmd", "/c", "mklink", "/J", str(self.root / "output"), str(far)], check=True,
                               capture_output=True)
            else:
                os.symlink(far, self.root / "output", target_is_directory=True)
        except (OSError, subprocess.CalledProcessError) as e:
            self.skipTest(f"no link: {e}")
        self.addCleanup(lambda: os.rmdir(self.root / "output") if os.name == "nt" else os.unlink(self.root / "output"))
        p, f = self.clip("tag60_real30")
        self.preflight(p, f)
        self.assertEqual(self.job(p)["state"], "ready")
        r = self.rec(p)
        self.assertTrue(r["path"].startswith("output/projects/V1/00_inputs/intermediates/"), r["path"])
        self.assertTrue((self.root / r["path"]).is_file())

    def test_a_copy_outside_output_is_never_ready(self):
        p, f = self.clip("tag60_real30")
        self.preflight(p, f)
        outside = self.tmp / "elsewhere.conform.mp4"
        shutil.copyfile(FX / "cfr30.mp4", outside)
        fake = {"ok": True, "path": str(outside), "parts": [], "sidecar": None, "lane": "cpu", "reused": False,
                "skipped": None, "reason": None, "fps": 30.0, "lines": {"en": [], "ar": []}}
        with mock.patch.object(MN, "conform", lambda *a, **k: dict(fake)):
            res = self.job(p)
        self.assertEqual(res["state"], "failed")
        self.assertIn("written outside the client's output/ folder", self.rec(p)["reason"])

    def test_a_copy_that_does_not_open_is_never_ready(self):
        p, f = self.clip("tag60_real30")
        self.preflight(p, f)
        bad = p.p("00_inputs/intermediates/tag60_real30.0123456789.conform.mp4")
        bad.parent.mkdir(parents=True, exist_ok=True)
        bad.write_bytes(b"not a video at all" * 64)
        fake = {"ok": True, "path": str(bad), "parts": [], "sidecar": None, "lane": "cpu", "reused": False,
                "skipped": None, "reason": None, "fps": 30.0, "lines": {"en": [], "ar": []}}
        with mock.patch.object(MN, "conform", lambda *a, **k: dict(fake)):
            res = self.job(p)
        self.assertEqual(res["state"], "failed")
        self.assertIn("could not be verified", self.rec(p)["reason"])
        self.assertTrue(ARABIC.search(self.rec(p)["lines"]["ar"][0]))


# --------------------------------------------------------------------------- stale sources
class TestStale(_Client):
    def ready(self):
        p, f = self.clip("tag60_real30")
        self.preflight(p, f)
        self.assertEqual(self.job(p)["state"], "ready")
        return p, f

    def test_a_changed_size_turns_ready_into_pending_and_reconforms(self):
        p, f = self.ready()
        old = self.rec(p)
        with open(f, "ab") as h:
            h.write(b"\0" * 64)                                           # the editor replaced the file
        self.assertIn("size", media.conform_current(p, f, old))
        with quiet():
            res = media.start_conform(p, mode="off")
        self.assertEqual(res["state"], "pending")
        self.assertEqual(self.rec(p)["state"], "pending")
        res = self.job(p)
        self.assertEqual(res["state"], "ready")
        self.assertEqual(self.rec(p)["source_size"], f.stat().st_size)

    def test_a_changed_tag_turns_ready_into_pending(self):
        p, f = self.ready()
        doc = self.doc(p)
        doc["files"][0]["normalise"]["conform"]["source_tag"] = "0" * 10
        write_json(p.p("00_inputs/preflight.json"), doc)
        with quiet():
            self.assertEqual(media.start_conform(p, mode="off")["state"], "pending")

    def test_a_source_newer_than_its_copy_is_stale(self):
        p, f = self.ready()
        r = self.rec(p)
        t = (self.root / r["path"]).stat().st_mtime + 60
        os.utime(f, (t, t))
        self.assertIn("newer", media.conform_current(p, f, r))

    def test_a_missing_copy_is_stale(self):
        p, f = self.ready()
        r = self.rec(p)
        (self.root / r["path"]).unlink()
        self.assertIsNotNone(media.conform_current(p, f, r))
        with quiet():
            self.assertEqual(media.start_conform(p, mode="off")["state"], "pending")

    def test_a_preflight_rerun_keeps_a_current_copy_and_drops_a_stale_one(self):
        p, f = self.ready()
        self.preflight(p, f)
        self.assertEqual(self.rec(p)["state"], "ready")                   # unchanged source: still ready, no job
        with quiet():
            self.assertIsNone(media.start_conform(p, mode="inline")["job"])
        with open(f, "ab") as h:
            h.write(b"\0" * 64)
        self.preflight(p, f)
        self.assertEqual(self.rec(p)["state"], "pending")                 # never a stale ready

    def test_a_source_changed_during_the_encode_is_not_ready(self):
        p, f = self.clip("tag60_real30")
        self.preflight(p, f)
        real = MN.conform

        def changing(src, *a, **k):
            res = real(src, *a, **k)
            if not getattr(changing, "done", False):
                changing.done = True
                with open(src, "ab") as h:
                    h.write(b"\0" * 64)
            return res
        with mock.patch.object(MN, "conform", changing):
            res = self.job(p)
        self.assertEqual(res["state"], "ready")                           # made again for the new bytes
        self.assertEqual(self.rec(p)["source_size"], f.stat().st_size)


# --------------------------------------------------------------------------- a real VFR clip
class TestRealVfr(_Client):
    def test_vfr_clip_gets_a_constant_rate_copy(self):
        f = make_vfr(self.root / "data" / "Raw" / "phone vfr.mp4")
        self.assertTrue(media.probe(f)["video"]["vfr"])
        p = Paths(self.root, "PHONE")
        p.ensure_project()
        rep = self.preflight(p, f)
        self.assertTrue(rep["ok"], rep["issues"])
        vfr = [i for i in rep["issues"] if "variable frame rate (average" in i["msg"]]
        self.assertEqual(len(vfr), 1, rep["issues"])
        self.assertIn("made automatically", vfr[0]["msg"])
        self.assertNotIn("Ask for a constant-frame-rate export", vfr[0]["msg"])
        self.assertEqual(vfr[0]["severity"], "info")
        self.assertEqual(self.rec(p)["state"], "pending")
        res = self.job(p)
        self.assertEqual(res["state"], "ready", res)
        r = self.rec(p)
        self.assertContract(r)
        out = self.root / r["path"]
        avg, base = stream_rates(out)
        self.assertAlmostEqual(avg, base, places=3)                        # constant frame rate
        self.assertAlmostEqual(base, r["cfr_fps"], places=2)
        t = frame_times(out)
        d = [b - a for a, b in zip(t, t[1:])]
        self.assertLess(max(d) - min(d), 1e-3, "frame intervals are not constant")
        self.assertAlmostEqual(t[-1] + d[0], media.probe(f)["duration_s"], delta=0.15)
        err = subprocess.run([ffmpeg_exe(), "-hide_banner", "-i", str(out)], capture_output=True, text=True,
                             errors="replace").stderr
        self.assertRegex(err, rf"\b{int(r['cfr_fps'])} fps\b")             # what ffprobe would print
        self.assertFalse(media.probe(out)["video"]["vfr"])


class TestReelConformVerb(_Client):
    def test_conform_wait_on_a_vfr_clip(self):
        make_vfr(self.root / "data" / "Raw" / "phone.mp4")
        code, doc, log = reel(self.root, "preflight", "--footage", "data/Raw/phone.mp4", video_id="PHONE")
        self.assertEqual(code, 0, log)
        self.assertEqual(doc["conform"]["state"], "pending", doc)          # WHYNOT_CONFORM=off: queued, not made
        code, doc, log = reel(self.root, "conform", "--wait", video_id="PHONE")
        self.assertEqual(code, 0, log)
        self.assertEqual(doc["state"], "ready", doc)
        self.assertEqual(doc["files"][0]["state"], "ready")
        rec = read_json(self.root / "output/projects/PHONE/00_inputs/preflight.json")["files"][0]["normalise"]["conform"]
        self.assertEqual(rec["state"], "ready")
        self.assertTrue((self.root / rec["path"]).is_file())
        code, doc, log = reel(self.root, "conform", video_id="PHONE")      # without --wait: the state, nothing to do
        self.assertEqual(code, 0, log)
        self.assertEqual(doc["state"], "ready")
        self.assertIsNone(doc["job"])

    def test_preflight_starts_a_background_job_and_wait_waits_for_it(self):
        make_vfr(self.root / "data" / "Raw" / "phone.mp4")
        code, doc, log = reel(self.root, "preflight", "--footage", "data/Raw/phone.mp4", video_id="BG",
                              env={"WHYNOT_CONFORM": "background"})
        self.assertEqual(code, 0, log)
        self.assertEqual(doc["conform"]["job"], "started", doc)
        pid = doc["conform"]["pid"]
        self.assertIsInstance(pid, int)
        code, doc, log = reel(self.root, "conform", "--wait", video_id="BG")
        self.assertEqual(code, 0, log)
        self.assertEqual(doc["state"], "ready", doc)
        from lib.writer_lock import pid_alive
        t0 = time.monotonic()
        while pid_alive(pid) and time.monotonic() - t0 < 120:
            time.sleep(0.2)
        self.assertFalse(pid_alive(pid), "the background job never ended")
        self.assertTrue((self.root / "output/projects/BG/logs/conform-job.log").is_file())

    def test_the_verb_is_registered(self):
        spec = importlib.util.spec_from_file_location("reel_cli_t26w", CLI)
        cli = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cli)
        self.assertIn("conform", cli.CORE_COMMANDS)
        self.assertIn("conform", cli.CORE_WRITES)
        from lib import lead_steps
        self.assertNotIn("conform", [s for s, _ in lead_steps.LEAD_STEPS])
        r = subprocess.run([_sys.executable, "-B", str(CLI), "conform", "--help"], capture_output=True, text=True,
                           encoding="utf-8")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("--wait", r.stdout)
        self.assertIn("ready", r.stdout)


# --------------------------------------------------------------------------- episodes: Gate 0 windows -> parts
class TestEpisodeWindows(_Client):
    def setUp(self):
        super().setUp()
        self.ep = make_vfr(self.root / "data" / "Episodes" / "EP1.mp4", seconds=12)

    def reel_item(self, rid, in_ms, out_ms):
        p = Paths(self.root, f"EP1_{rid}")
        p.ensure_project()
        write_json(p.p("00_inputs/source.json"), {"footage": "data/Episodes/EP1.mp4", "in_ms": in_ms, "out_ms": out_ms,
                                                  "duration_ms": out_ms - in_ms, "offset_ms": in_ms,
                                                  "kind": "episode_reel", "episode_id": "EP1", "reel_id": rid})
        return p

    def test_two_reels_of_one_episode_get_their_own_parts(self):
        recs = {}
        for rid, a, b in (("R01", 3000, 8000), ("R02", 14000, 19000)):
            p = self.reel_item(rid, a, b)
            self.assertEqual(media.conform_windows(p, self.ep), [(a / 1000, b / 1000)])
            self.preflight(p, self.ep)
            self.assertEqual(self.job(p)["state"], "ready")
            recs[rid] = self.rec(p)
        for rid, (a, b) in (("R01", (1000, 10000)), ("R02", (12000, 21000))):
            r = recs[rid]
            self.assertContract(r)
            self.assertIsNone(r["path"])
            self.assertEqual([(x["from_ms"], x["to_ms"]) for x in r["parts"]], [(a, b)])      # 2 s handles
            self.assertInsideOutput(r["parts"][0]["path"])
            self.assertIn(f".conform.r{a}-{b}.mp4", r["parts"][0]["path"])
        self.assertNotEqual(recs["R01"]["parts"][0]["path"], recs["R02"]["parts"][0]["path"])

    def test_two_windows_in_one_item_give_two_parts(self):
        p = self.reel_item("R01", 3000, 8000)
        self.preflight(p, self.ep)
        with mock.patch.object(media, "conform_windows", lambda paths, src: [(3.0, 5.0), (15.0, 18.0)]):
            self.assertEqual(self.job(p)["state"], "ready")
        r = self.rec(p)
        self.assertIsNone(r["path"])
        self.assertEqual([(x["from_ms"], x["to_ms"]) for x in r["parts"]], [(1000, 7000), (13000, 20000)])
        for part in r["parts"]:
            self.assertInsideOutput(part["path"])
            n = frame_times(self.root / part["path"])
            self.assertAlmostEqual(n[-1], (part["to_ms"] - part["from_ms"]) / 1000, delta=0.2)
        # a ready ranged record is current only while it still covers this item's windows
        self.assertIsNotNone(media.conform_current(p, self.ep, r, windows=[(9.0, 11.0)]))
        self.assertIsNone(media.conform_current(p, self.ep, r, windows=[(3.0, 5.0)]))

    def test_a_clip_has_no_windows(self):
        p, f = self.clip("tag60_real30")
        self.assertIsNone(media.conform_windows(p, f))


# --------------------------------------------------------------------------- old files, failures, the hook
class TestCompatibility(_Client):
    def test_an_old_preflight_json_without_the_key_is_untouched(self):
        p, f = self.clip("tag60_real30")
        old = {"generated": "2026-09-01T10:00:00+02:00", "sequence": {"w": 1080, "h": 1920, "fps": 24.0, "audio_hz": 48000},
               "files": [{"path": str(f), "name": f.name, "size_bytes": f.stat().st_size, "video": {"fps": 60.0},
                          "audio": [], "errors": []}],
               "valid": [str(f)], "issues": [], "conversions": [], "ok": True}
        pf = p.p("00_inputs/preflight.json")
        write_json(pf, old)
        before = pf.read_bytes()
        with quiet():
            for mode in ("off", "inline", "background"):
                with mock.patch.object(media, "_spawn_job", side_effect=AssertionError("no job for an old file")):
                    self.assertEqual(media.start_conform(p, mode=mode)["state"], "none")
            self.assertEqual(media.run_conform_job(p)["state"], "none")
        code, doc, log = reel(self.root, "conform", "--wait", video_id="V1")
        self.assertEqual(code, 0, log)
        self.assertEqual(doc["state"], "none")
        self.assertEqual(pf.read_bytes(), before)
        self.assertFalse(p.p("00_inputs/intermediates").exists())
        self.assertFalse(p.p("00_inputs/conform-job.lock").exists())      # nothing at all is written for an old item

    def test_no_preflight_yet(self):
        p = Paths(self.root, "V9")
        p.ensure_project()
        with quiet():
            self.assertEqual(media.start_conform(p, mode="inline")["state"], "none")

    def test_the_write_keeps_everything_else_and_uses_the_file_lock(self):
        p, f = self.clip("tag60_real30")
        self.preflight(p, f)
        doc = self.doc(p)
        doc["extra"] = {"kept": True}
        write_json(p.p("00_inputs/preflight.json"), doc)
        seen, held, writes = [], [0], []
        real, real_write = media.file_locked, media.write_json

        @contextlib.contextmanager
        def spy(path, *a, **k):
            seen.append(Path(path).name)
            with real(path, *a, **k) as x:
                if Path(path).name == "preflight.json":
                    held[0] += 1
                try:
                    yield x
                finally:
                    if Path(path).name == "preflight.json":
                        held[0] -= 1

        def write(path, data):
            if Path(path).name == "preflight.json":
                writes.append(held[0] > 0)                                # every write inside the file's lock
            return real_write(path, data)
        with mock.patch.object(media, "file_locked", spy), mock.patch.object(media, "write_json", write):
            self.job(p)
            self.preflight(p, f)
        self.assertIn("preflight.json", seen)
        self.assertTrue(writes and all(writes), writes)
        self.job(p)
        doc = self.doc(p)
        doc["extra"] = {"kept": True}
        write_json(p.p("00_inputs/preflight.json"), doc)
        with open(f, "ab") as h:
            h.write(b"\0" * 64)
        self.job(p)
        after = self.doc(p)
        self.assertEqual(after["extra"], {"kept": True})
        self.assertEqual({k: v for k, v in after["files"][0].items() if k != "normalise"},
                         {k: v for k, v in doc["files"][0].items() if k != "normalise"})


class TestIntakeNeverFails(_Client):
    def test_a_conform_that_raises_is_a_failed_record(self):
        p, f = self.clip("tag60_real30")
        self.preflight(p, f)
        with mock.patch.object(MN, "conform", side_effect=RuntimeError("boom")):
            res = self.job(p)
        self.assertEqual(res["state"], "failed")
        r = self.rec(p)
        self.assertIn("boom", r["reason"])
        self.assertTrue(r["lines"]["ar"] and r["lines"]["en"])

    def test_the_preflight_verb_survives_a_broken_conform_step(self):
        make_vfr(self.root / "data" / "Raw" / "phone.mp4")
        spec = importlib.util.spec_from_file_location("reel_cli_t26w_b", CLI)
        cli = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cli)
        buf = io.StringIO()
        with mock.patch.object(media, "start_conform", side_effect=RuntimeError("no job today")), \
                mock.patch.object(cli.priority, "apply", lambda: None), contextlib.redirect_stdout(buf), \
                contextlib.redirect_stderr(io.StringIO()):
            try:
                cli.main(["--root", str(self.root), "--video-id", "PHONE", "preflight", "--footage",
                          "data/Raw/phone.mp4"])
                code = 0
            except SystemExit as e:
                code = e.code or 0
        self.assertEqual(code, 0, buf.getvalue())
        doc = json.loads(buf.getvalue())
        self.assertTrue(doc["ok"])
        self.assertEqual(doc["conform"]["state"], "failed")
        self.assertIn("no job today", doc["conform"]["reason"])

    def test_a_measurement_that_raises_never_stops_the_preflight(self):
        p, f = self.clip("tag60_real30")
        with mock.patch.object(MN, "measure", side_effect=RuntimeError("bad file")):
            rep = self.preflight(p, f)
        self.assertTrue(rep["ok"])
        self.assertNotIn("normalise", rep["files"][0])
        with quiet():
            self.assertEqual(media.start_conform(p, mode="inline")["state"], "none")


class TestJobAndLane(_Client):
    def capture(self):
        calls = []

        def fake(src, out_dir, d, **kw):
            calls.append(dict(kw, src=src, out_dir=out_dir, d=d))
            return {"ok": False, "path": None, "parts": [], "sidecar": None, "lane": kw.get("lane"), "reused": False,
                    "skipped": "no ffmpeg", "reason": "stub", "fps": None, "lines": {"en": ["x"], "ar": ["س"]}}
        return calls, fake

    def test_the_lane_comes_from_the_gpu_slot_and_a_clip_has_no_ranges(self):
        p, f = self.clip("tag60_real30")
        self.preflight(p, f)
        calls, fake = self.capture()
        sites = []

        @contextlib.contextmanager
        def slot(site, **kw):
            sites.append(site)
            yield "cuda"
        with mock.patch.object(MN, "conform", fake), mock.patch("lib.gpu_lock.site_slot", slot):
            self.job(p)
        self.assertEqual(sites, ["conform"])
        self.assertEqual(len(calls), 1)
        c = calls[0]
        self.assertEqual(c["lane"], "cuda")
        self.assertIsNone(c["ranges"])
        self.assertEqual(Path(c["out_dir"]), p.p("00_inputs/intermediates"))
        self.assertEqual(Path(c["client_root"]), p.root)
        self.assertEqual(Path(c["src"]), f)
        self.assertEqual(c["d"]["actions"], ["cfr"])
        self.assertTrue(c["d"]["has_audio"])                              # the full decision, not the record's subset

    def test_an_episode_reel_passes_its_window(self):
        ep = make_vfr(self.root / "data" / "Episodes" / "EP2.mp4", seconds=6)
        p = Paths(self.root, "EP2_R01")
        p.ensure_project()
        write_json(p.p("00_inputs/source.json"), {"footage": "data/Episodes/EP2.mp4", "in_ms": 2000, "out_ms": 7000,
                                                  "kind": "episode_reel", "episode_id": "EP2", "reel_id": "R01"})
        self.preflight(p, ep)
        calls, fake = self.capture()
        with mock.patch.object(MN, "conform", fake):
            self.job(p)
        self.assertEqual(calls[0]["ranges"], [(2.0, 7.0)])

    def test_a_running_job_is_not_started_twice(self):
        p, f = self.clip("tag60_real30")
        self.preflight(p, f)
        held, release = threading.Event(), threading.Event()

        def hold():
            with media.file_locked(p.p(media.JOB_REL), 5):
                held.set()
                release.wait(30)
        t = threading.Thread(target=hold)
        t.start()
        self.addCleanup(t.join)
        self.addCleanup(release.set)
        held.wait(10)
        with mock.patch.object(media, "_spawn_job", side_effect=AssertionError("spawned twice")), quiet():
            res = media.start_conform(p, mode="background")
            self.assertEqual(res["job"], "running")
            self.assertEqual(media.run_conform_job(p, wait_s=0)["job"], "running")
        self.assertEqual(self.rec(p)["state"], "pending")

    def test_the_background_job_command(self):
        p, f = self.clip("tag60_real30")
        self.preflight(p, f)
        seen = {}

        class P:
            pid = 4242

        def popen(cmd, **kw):
            seen.update(cmd=cmd, **kw)
            return P()
        with mock.patch.object(media, "_popen", popen), quiet():
            res = media.start_conform(p, mode="background")
        self.assertEqual((res["job"], res["pid"]), ("started", 4242))
        cmd = seen["cmd"]
        self.assertEqual(cmd[0], _sys.executable)
        self.assertEqual(Path(cmd[cmd.index("--root") + 1]), p.root)
        self.assertEqual(cmd[cmd.index("--video-id") + 1], "V1")
        self.assertEqual(cmd[-2:], ["conform", "--wait"])
        self.assertEqual(Path(next(c for c in cmd if c.endswith("cli.py"))).resolve(), CLI.resolve())
        self.assertEqual(seen["env"]["WHYNOT_CONFORM"], "inline")          # the job itself never spawns again
        if os.name == "nt":
            self.assertTrue(seen["creationflags"] & subprocess.DETACHED_PROCESS)
        else:
            self.assertTrue(seen["start_new_session"])

    def test_the_test_sandbox_runs_the_job_inline_by_default(self):
        p, f = self.clip("tag60_real30")
        self.preflight(p, f)
        with mock.patch.dict(os.environ, {"WHYNOT_CONFORM": ""}), mock.patch.object(
                media, "_spawn_job", side_effect=AssertionError("no background process inside the test sandbox")):
            with quiet():
                res = media.start_conform(p)
        self.assertEqual((res["job"], res["state"]), ("inline", "ready"))


# --------------------------------------------------------------------------- mutation-pass additions
class TestMutationGaps(_Client):
    def test_a_source_that_keeps_changing_is_never_left_ready(self):
        p, f = self.clip("tag60_real30")
        self.preflight(p, f)
        real = MN.conform

        def changing(src, *a, **k):
            res = real(src, *a, **k)
            with open(src, "ab") as h:
                h.write(b"\0" * 64)
            return res
        with mock.patch.object(MN, "conform", changing), mock.patch.object(media, "STALE_PASSES", 0):
            res = self.job(p)
        r = self.rec(p)
        self.assertEqual((res["state"], r["state"]), ("pending", "pending"))       # no pass left: never a stale ready
        self.assertIn("changed while its copy was made", r["reason"])

    def test_a_broken_step_is_a_failed_record_never_an_error(self):
        p, f = self.clip("tag60_real30")
        self.preflight(p, f)
        calls = []
        real = media._refresh

        def broken(*a, **k):
            calls.append(1)
            if len(calls) == 1:
                raise OSError("the folder went away")
            return real(*a, **k)
        with mock.patch.object(media, "_refresh", broken), quiet():
            res = media.start_conform(p, mode="inline")
        self.assertEqual(res["state"], "failed")
        self.assertIn("the folder went away", res["reason"])
        r = self.rec(p)
        self.assertEqual(r["state"], "failed")
        self.assertIn("the folder went away", r["reason"])

    def test_a_failed_copy_is_tried_again(self):
        p, f = self.clip("tag60_real30")
        self.preflight(p, f)
        with mock.patch.object(MN, "_engine_ffmpeg", lambda: None):
            self.assertEqual(self.job(p)["state"], "failed")
        self.assertEqual(self.job(p)["state"], "failed")                          # the job alone never retries it
        with quiet():
            self.assertEqual(media.start_conform(p, mode="off")["state"], "pending")   # the step (and the verb) does
        self.assertEqual(self.job(p)["state"], "ready")

    def test_the_summary_says_failed_over_ready(self):
        p, f = self.clip("tag60_real30")
        g = self.root / "data" / "Raw" / "second.mp4"
        shutil.copyfile(FX / "tag60_real30.mp4", g)
        with quiet():
            media.preflight(p, [f, g])
        real = MN.conform

        def second_fails(src, *a, **k):
            if Path(src).name == "second.mp4":
                raise RuntimeError("no luck")
            return real(src, *a, **k)
        with mock.patch.object(MN, "conform", second_fails):
            res = self.job(p)
        self.assertEqual([x["state"] for x in res["files"]], ["ready", "failed"])
        self.assertEqual(res["state"], "failed")
        doc = self.doc(p)
        doc["files"][1]["normalise"]["conform"]["state"] = "pending"
        write_json(p.p("00_inputs/preflight.json"), doc)
        self.assertEqual(media.conform_summary(p)["state"], "pending")

    def test_conform_wait_waits_for_the_running_job(self):
        p, f = self.clip("tag60_real30")
        self.preflight(p, f)
        held, done = threading.Event(), threading.Event()

        def job_elsewhere():
            with media.file_locked(p.p(media.JOB_REL), 5):
                held.set()
                time.sleep(2.0)                                                   # another process's job running
            done.set()
        t = threading.Thread(target=job_elsewhere)
        t.start()
        self.addCleanup(t.join)
        held.wait(10)
        spec = importlib.util.spec_from_file_location("reel_cli_t26w_w", CLI)
        cli = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cli)
        buf = io.StringIO()
        with mock.patch.object(cli.priority, "apply", lambda: None), contextlib.redirect_stdout(buf), \
                contextlib.redirect_stderr(io.StringIO()):
            try:
                cli.main(["--root", str(self.root), "--video-id", "V1", "conform", "--wait"])
            except SystemExit:
                pass
        doc = json.loads(buf.getvalue())
        self.assertTrue(done.is_set(), "returned before the running job ended")
        self.assertEqual((doc["state"], doc["job"]), ("ready", "done"))


# --------------------------------------------------------------------------- preflight's own lines (README hunk)
class TestPreflightLines(_Client):
    def test_the_sequence_rate_is_compared_with_the_copy_rate(self):
        p, f = self.clip("tag60_real30")
        rep = self.preflight(p, f)
        fps = [i["msg"] for i in rep["issues"] if "fps sequence" in i["msg"]]
        self.assertEqual(len(fps), 1, rep["issues"])                       # 24 fps default sequence
        self.assertIn('"timebase": 30', fps[0])                             # the real rate, never the 60 tag
        self.assertNotIn('"timebase": 60', fps[0])

    def test_a_vfr_clip_that_gets_no_copy_keeps_the_old_advice(self):
        f = make_vfr(self.root / "data" / "Raw" / "hdr phone.mp4")
        p = Paths(self.root, "HDR")
        p.ensure_project()
        real = MN.decide

        def no_copy(m, *a, **k):
            d = real(m, *a, **k)
            d["actions"], d["cfr_fps"] = [], None                         # e.g. HDR this FFmpeg cannot tone-map
            return d
        with mock.patch.object(MN, "decide", no_copy):
            rep = self.preflight(p, f)
        vfr = [i for i in rep["issues"] if "variable frame rate (average" in i["msg"]]
        self.assertEqual(len(vfr), 1)
        self.assertIn("constant-frame-rate export", vfr[0]["msg"])
        self.assertEqual(vfr[0]["severity"], "warning")


if __name__ == "__main__":
    unittest.main()
