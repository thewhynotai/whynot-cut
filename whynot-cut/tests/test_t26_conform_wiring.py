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
KEYS = {"state", "path", "parts", "cfr_fps", "source_tag", "source_size", "source_mtime", "source_fp", "copy_files",
        "reason", "lines", "at"}
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

    def test_a_source_with_a_new_time_is_stale(self):
        p, f = self.ready()
        r = self.rec(p)
        t = (self.root / r["path"]).stat().st_mtime + 60
        os.utime(f, (t, t))
        self.assertIn("modified time", media.conform_current(p, f, r))

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
        # review 99f6357 R03: a window the part only overlaps (1.0-7.0 s against a widened 3.0-9.0 s) is not covered
        self.assertIn("no part covers", media.conform_current(p, self.ep, r, windows=[(3.0, 9.0)]))

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
            # review 99f6357 P2-1: DETACHED_PROCESS makes Windows ignore CREATE_NO_WINDOW (a visible console that kills
            # the job when it is closed): a hidden console of its own, its own group, out of the caller's job
            fl = seen["creationflags"]
            self.assertFalse(fl & subprocess.DETACHED_PROCESS)
            for bit in (subprocess.CREATE_NO_WINDOW, subprocess.CREATE_NEW_PROCESS_GROUP,
                        subprocess.CREATE_BREAKAWAY_FROM_JOB):
                self.assertTrue(fl & bit, hex(bit))
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


# --------------------------------------------------------------------------- fix round 2 (review 99f6357)
CLAIM = "00_inputs/conform-job.claim"       # the job's own claim: {pid, pid_created, host, host_id, started_at}
PENDING_AR = "النسخة الثابتة لسه بتتعمل: البناء ده من الملف الأصلي. ابنِ تاني بعد ما تخلص."      # CONTRACT.md, step 3
PROBE = """import ctypes, json, subprocess, sys
REPORT = ("import ctypes, json; k = ctypes.windll.kernel32; u = ctypes.windll.user32; h = k.GetConsoleWindow(); "
          "print(json.dumps({'hwnd': h, 'visible': bool(h and u.IsWindowVisible(h))}))")
h = ctypes.windll.kernel32.GetConsoleWindow()
me = {"hwnd": h, "visible": bool(h and ctypes.windll.user32.IsWindowVisible(h))}
tool = json.loads(subprocess.run([sys.executable, "-c", REPORT], capture_output=True, text=True).stdout)
open(sys.argv[1], "w").write(json.dumps({"job": me, "tool": tool}))
"""


class TestR2NoWindow(_Client):
    """P2-1: the background job (and every ffmpeg it starts, the way common.run does: no creation flags) has no
    visible console window, so there is no odd window for the editor to close (closing it killed the job)."""

    @unittest.skipUnless(os.name == "nt", "Windows console windows")
    def test_the_job_and_the_tools_it_starts_have_no_visible_window(self):
        p, f = self.clip("tag60_real30")
        self.preflight(p, f)
        seen = []

        class P:
            pid = 4242

        def popen(cmd, **kw):
            seen.append(kw["creationflags"])
            return P()
        with mock.patch.object(media, "_popen", popen), quiet():
            media.start_conform(p, mode="background")
        probe, out = self.tmp / "probe.py", self.tmp / "probe.json"
        probe.write_text(PROBE, encoding="utf-8")
        cmd = [_sys.executable, "-s", "-B", str(probe), str(out)]
        kw = dict(stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, close_fds=True)
        try:                                           # the job's exact flags, with the job's own fallback
            proc = subprocess.Popen(cmd, creationflags=seen[0], **kw)
        except OSError:
            proc = subprocess.Popen(cmd, creationflags=seen[0] & ~subprocess.CREATE_BREAKAWAY_FROM_JOB, **kw)
        proc.wait(60)
        rep = json.loads(out.read_text(encoding="utf-8"))
        self.assertFalse(rep["job"]["visible"], rep)
        self.assertFalse(rep["tool"]["visible"], rep)


class _R2(_Client):
    def no_os_locks(self):
        """The volume refuses OS file locks (macOS SMB/AFP, a cloud-drive folder): file_lock goes on in process only."""
        import errno
        from lib import file_lock
        m = mock.patch.object(file_lock, "_try_lock", side_effect=file_lock._Unsupported(
            OSError(errno.EINVAL, "this volume cannot lock")))
        m.start()
        self.addCleanup(m.stop)

    def process(self, code):
        proc = subprocess.Popen([_sys.executable, "-c", code], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                stderr=subprocess.DEVNULL)
        self.addCleanup(lambda: (proc.kill(), proc.wait(30)) if proc.poll() is None else None)
        return proc

    def sleeper(self) -> int:
        return self.process("import time; time.sleep(120)").pid

    def dead_pid(self) -> int:
        proc = self.process("pass")
        proc.wait(60)
        return proc.pid

    def write_claim(self, p, pid, **kw):
        from lib import writer_lock as WL
        import socket
        rec = dict({"pid": pid, "pid_created": WL.process_created(pid), "host": socket.gethostname(),
                    "host_id": WL.host_id(), "started_at": "2026-10-20T10:00:00+03:00"}, **kw)
        p.p(CLAIM).write_text(json.dumps(rec), encoding="utf-8")
        return p.p(CLAIM)

    def started(self):
        class P:
            pid = 4242
        return mock.patch.object(media, "_popen", lambda cmd, **kw: P())

    def no_second_job(self):
        return mock.patch.object(media, "_spawn_job", side_effect=AssertionError("a second job"))


class TestR2JobClaim(_R2):
    """P2-2: one conform job per item also where the volume has no OS file locks: the job holds an exclusive claim
    file (O_EXCL; pid + process start + computer), a dead holder's claim is taken over, the claim goes at the end."""

    def test_a_live_job_in_another_process_is_seen_without_os_locks(self):
        p, f = self.clip("tag60_real30")
        self.preflight(p, f)
        self.no_os_locks()
        cp = self.write_claim(p, self.sleeper())
        before = cp.read_bytes()
        with self.no_second_job(), quiet():
            self.assertEqual(media.start_conform(p, mode="background")["job"], "running")
            self.assertEqual(media.run_conform_job(p, wait_s=0)["job"], "running")
        self.assertEqual(self.rec(p)["state"], "pending")
        self.assertEqual(cp.read_bytes(), before)                                # never taken from a live job

    def test_a_dead_jobs_claim_is_taken_over_and_removed_at_the_end(self):
        p, f = self.clip("tag60_real30")
        self.preflight(p, f)
        self.no_os_locks()
        self.write_claim(p, self.dead_pid())
        self.assertEqual(self.job(p, wait_s=5)["state"], "ready")
        self.assertFalse(p.p(CLAIM).exists())

    def test_the_job_holds_its_claim_while_it_encodes(self):
        from lib import writer_lock as WL
        p, f = self.clip("tag60_real30")
        self.preflight(p, f)
        real, seen = MN.conform, []

        def spy(*a, **k):
            seen.append(json.loads(p.p(CLAIM).read_text(encoding="utf-8")))
            return real(*a, **k)
        with mock.patch.object(MN, "conform", spy):
            self.assertEqual(self.job(p)["state"], "ready")
        self.assertEqual(seen[0]["pid"], os.getpid())
        self.assertEqual(seen[0]["host_id"], WL.host_id())
        self.assertEqual(str(seen[0]["pid_created"]), str(WL.process_created(os.getpid())))
        self.assertFalse(p.p(CLAIM).exists())

    def test_a_claim_being_written_counts_for_a_moment_only(self):
        p, f = self.clip("tag60_real30")
        self.preflight(p, f)
        self.no_os_locks()
        cp = p.p(CLAIM)
        cp.write_text("{", encoding="utf-8")                                    # created, not yet written
        with self.no_second_job(), quiet():
            self.assertEqual(media.start_conform(p, mode="background")["job"], "running")
        old = time.time() - 600
        os.utime(cp, (old, old))
        with self.started(), quiet():
            self.assertEqual(media.start_conform(p, mode="background")["job"], "started")

    def test_another_computers_claim_counts_until_it_is_old(self):
        p, f = self.clip("tag60_real30")
        self.preflight(p, f)
        self.no_os_locks()
        cp = self.write_claim(p, 99999, pid_created=None, host="other-mac", host_id="mac:0000000000other")
        with self.no_second_job(), quiet():
            self.assertEqual(media.start_conform(p, mode="background")["job"], "running")
        old = time.time() - media.JOB_WAIT_S - 60
        os.utime(cp, (old, old))
        with self.started(), quiet():
            self.assertEqual(media.start_conform(p, mode="background")["job"], "started")

    def test_a_claim_left_by_this_process_is_never_waited_for(self):
        p, f = self.clip("tag60_real30")
        self.preflight(p, f)
        self.write_claim(p, os.getpid())
        self.assertEqual(self.job(p, wait_s=0)["state"], "ready")
        self.assertFalse(p.p(CLAIM).exists())

    def test_a_reused_pid_is_not_the_job(self):
        p, f = self.clip("tag60_real30")
        self.preflight(p, f)
        self.no_os_locks()
        self.write_claim(p, self.sleeper(), pid_created="1")                   # alive, but another process now
        self.assertEqual(self.job(p, wait_s=0)["state"], "ready")
        self.assertFalse(p.p(CLAIM).exists())

    def test_a_claim_that_is_no_longer_ours_is_never_removed(self):
        p, f = self.clip("tag60_real30")
        self.preflight(p, f)
        real = MN.conform

        def replaced(*a, **k):
            res = real(*a, **k)
            self.write_claim(p, os.getpid(), started_at="someone else's")
            return res
        with mock.patch.object(MN, "conform", replaced):
            self.job(p)
        self.assertEqual(json.loads(p.p(CLAIM).read_text(encoding="utf-8"))["started_at"], "someone else's")


class TestR2Import(_R2):
    """P3-2 + P3-3: media.conform_import is ppro_build's one call before it imports a copy: the copy only while it is
    still current, else the original with the one build warning; a pending record whose job died becomes failed."""

    def imp(self, p, src):
        with quiet():
            return media.conform_import(p, src)

    def age(self, p, seconds):
        import datetime as dt
        doc = self.doc(p)
        doc["files"][0]["normalise"]["conform"]["at"] = (dt.datetime.now().astimezone() - dt.timedelta(
            seconds=seconds)).isoformat(timespec="seconds")
        write_json(p.p("00_inputs/preflight.json"), doc)

    def assertOriginal(self, res, state):
        self.assertEqual((res["use"], res["state"], res["path"], res["parts"]), ("original", state, None, []), res)

    def ready(self):
        p, f = self.clip("tag60_real30")
        self.preflight(p, f)
        self.assertEqual(self.job(p)["state"], "ready")
        return p, f

    def test_a_current_copy_is_imported(self):
        p, f = self.ready()
        r = self.rec(p)
        for src in (f, str(f), "data/Raw/tag60_real30.mp4"):
            res = self.imp(p, src)
            self.assertEqual((res["use"], res["state"], res["path"], res["parts"]), ("copy", "ready", r["path"], []))
            self.assertEqual(res["lines"], {"ar": [], "en": []})

    def test_a_stale_copy_is_never_imported(self):
        p, f = self.ready()
        with open(f, "ab") as h:
            h.write(b"\0" * 64)                                                 # the editor replaced the footage
        res = self.imp(p, f)
        self.assertOriginal(res, "ready")
        self.assertIn("size", res["reason"])
        self.assertIn("reel conform --wait", res["lines"]["en"][0])
        self.assertTrue(ARABIC.search(res["lines"]["ar"][0]))
        self.assertIn("reel conform --wait", res["lines"]["ar"][0])

    def test_an_emptied_copy_is_never_imported(self):
        p, f = self.ready()
        copy = self.root / self.rec(p)["path"]
        os.truncate(copy, 0)                                                    # review 99f6357 R14
        self.assertIn("empty", media.conform_current(p, f, self.rec(p)))
        res = self.imp(p, f)
        self.assertOriginal(res, "ready")
        self.assertIn("empty", res["reason"])

    def test_pending_gives_the_contract_line(self):
        p, f = self.clip("tag60_real30")
        self.preflight(p, f)
        res = self.imp(p, f)
        self.assertOriginal(res, "pending")
        self.assertIn(PENDING_AR, res["lines"]["ar"])
        self.assertTrue(res["lines"]["en"] and not ARABIC.search(res["lines"]["en"][0]))
        self.assertEqual(self.rec(p)["state"], "pending")

    def test_a_pending_copy_whose_job_died_is_failed_and_recorded(self):
        p, f = self.clip("tag60_real30")
        self.preflight(p, f)
        self.age(p, 600)                                                        # queued 10 min ago, no job alive
        res = self.imp(p, f)
        self.assertOriginal(res, "failed")
        self.assertIn("reel conform --wait", res["reason"])
        r = self.rec(p)
        self.assertContract(r)
        self.assertEqual(r["state"], "failed")
        self.assertEqual(res["lines"], r["lines"])
        self.assertTrue(ARABIC.search(r["lines"]["ar"][0]))
        with quiet():                                                           # and `reel conform --wait` recovers
            media.start_conform(p, mode="off")
        self.assertEqual(self.job(p, wait_s=5)["state"], "ready")
        self.assertEqual(self.imp(p, f)["use"], "copy")

    def test_a_dead_jobs_claim_does_not_count_as_a_live_job(self):
        p, f = self.clip("tag60_real30")
        self.preflight(p, f)
        self.age(p, 600)
        self.write_claim(p, self.dead_pid())
        self.assertOriginal(self.imp(p, f), "failed")

    def test_a_pending_copy_with_a_live_job_stays_pending(self):
        p, f = self.clip("tag60_real30")
        self.preflight(p, f)
        self.age(p, 600)
        for live in ("thread", "claim"):
            with self.subTest(live):
                held, release = threading.Event(), threading.Event()
                if live == "thread":
                    def hold():
                        with media.file_locked(p.p(media.JOB_REL), 5):
                            held.set()
                            release.wait(30)
                    t = threading.Thread(target=hold)
                    t.start()
                    held.wait(10)
                else:
                    self.no_os_locks()
                    self.write_claim(p, self.sleeper())
                try:
                    self.assertOriginal(self.imp(p, f), "pending")
                    self.assertEqual(self.rec(p)["state"], "pending")
                finally:
                    release.set()
                    if live == "thread":
                        t.join()

    def test_failed_passes_the_engines_lines(self):
        p, f = self.clip("tag60_real30")
        self.preflight(p, f)
        with mock.patch.object(MN, "_engine_ffmpeg", lambda: None):
            self.assertEqual(self.job(p)["state"], "failed")
        res = self.imp(p, f)
        self.assertOriginal(res, "failed")
        self.assertEqual((res["reason"], res["lines"]), (self.rec(p)["reason"], self.rec(p)["lines"]))

    def test_not_needed_and_old_files_use_the_original_silently(self):
        p, f = self.clip("cfr30")
        self.preflight(p, f)
        res = self.imp(p, f)
        self.assertOriginal(res, "not_needed")
        self.assertEqual(res["lines"], {"ar": [], "en": []})
        pf = p.p("00_inputs/preflight.json")
        write_json(pf, {"files": [{"path": str(f), "name": f.name, "video": {"fps": 30.0}}], "ok": True})
        before = pf.read_bytes()
        res = self.imp(p, f)
        self.assertOriginal(res, "none")
        self.assertEqual(res["lines"], {"ar": [], "en": []})
        self.assertEqual(pf.read_bytes(), before)
        self.assertOriginal(self.imp(Paths(self.root, "NOPE"), f), "none")     # no preflight at all

    def test_another_cameras_file_of_the_same_name_is_never_matched(self):
        cam_a = self.root / "data" / "CamA" / "C0001.mp4"
        cam_a.parent.mkdir(parents=True)
        shutil.copyfile(FX / "tag60_real30.mp4", cam_a)
        p = Paths(self.root, "CAM")
        p.ensure_project()
        self.preflight(p, cam_a)
        self.assertEqual(self.job(p)["state"], "ready")
        self.assertOriginal(self.imp(p, self.root / "data" / "CamB" / "C0001.mp4"), "none")
        self.assertEqual(self.imp(p, "C0001.mp4")["use"], "copy")              # a bare name: the only file so named

    def test_the_parts_of_a_reel_cut_from_an_episode(self):
        ep = make_vfr(self.root / "data" / "Episodes" / "EP3.mp4", seconds=4)
        p = Paths(self.root, "EP3_R01")
        p.ensure_project()
        write_json(p.p("00_inputs/source.json"), {"footage": "data/Episodes/EP3.mp4", "in_ms": 2500, "out_ms": 5000,
                                                  "kind": "episode_reel", "episode_id": "EP3", "reel_id": "R01"})
        self.preflight(p, ep)
        self.assertEqual(self.job(p)["state"], "ready")
        res = self.imp(p, ep)
        self.assertEqual((res["use"], res["path"]), ("copy", None))
        self.assertEqual(res["parts"], self.rec(p)["parts"])
        self.assertEqual([(x["from_ms"], x["to_ms"]) for x in res["parts"]], [(500, 7000)])


class TestR2Advice(_Client):
    """P3-4: when the copy fails, the old advice to ask for a constant-frame-rate export comes back (AR + EN)."""

    def test_a_failed_copy_keeps_the_constant_frame_rate_advice(self):
        p, f = self.clip("tag60_real30")
        self.preflight(p, f)
        with mock.patch.object(MN, "_engine_ffmpeg", lambda: None):
            self.assertEqual(self.job(p)["state"], "failed")
        r = self.rec(p)
        self.assertIn("FFmpeg", r["lines"]["en"][0])                            # the failure's own line stays first
        self.assertIn("constant-frame-rate export", " ".join(r["lines"]["en"]))
        self.assertIn("بمعدل فريمات ثابت", " ".join(r["lines"]["ar"]))
        self.assertEqual(len(r["lines"]["ar"]), len(r["lines"]["en"]))

    def test_a_record_that_preflight_could_not_build_keeps_the_advice_too(self):
        p, f = self.clip("tag60_real30")
        with mock.patch.object(media, "_pending", side_effect=RuntimeError("no record today")):
            self.preflight(p, f)
        r = self.rec(p)
        self.assertEqual(r["state"], "failed")
        self.assertIn("constant-frame-rate export", " ".join(r["lines"]["en"]))

    def test_a_ready_copy_has_no_advice(self):
        p, f = self.clip("tag60_real30")
        self.preflight(p, f)
        self.assertEqual(self.job(p)["state"], "ready")
        self.assertNotIn("constant-frame-rate export", " ".join(self.rec(p)["lines"]["en"]))


class TestR2Windows(_Client):
    """P3-5: a range's footage is matched by its client-relative path, never by the file name alone."""

    def test_two_cameras_files_of_one_name_are_told_apart(self):
        p = Paths(self.root, "CAM_R01")
        p.ensure_project()
        write_json(p.p("00_inputs/source.json"), {"footage": "data/CamA/C0001.MP4", "in_ms": 2000, "out_ms": 5000})
        self.assertEqual(media.conform_windows(p, self.root / "data" / "CamA" / "C0001.MP4"), [(2.0, 5.0)])
        self.assertIsNone(media.conform_windows(p, self.root / "data" / "CamB" / "C0001.MP4"))


class TestR2MutantGaps(_Client):
    """P3-7: the reviewer's surviving mutants R06, R11, R12 (R03 in TestEpisodeWindows, R14 in TestR2Import)."""

    def test_a_not_needed_file_replaced_by_one_that_needs_a_copy(self):
        p, f = self.clip("cfr30", fname="clip.mp4")
        self.preflight(p, f)
        self.assertEqual(self.rec(p)["state"], "not_needed")
        self.assertNotEqual((FX / "tag60_real30.mp4").stat().st_size, f.stat().st_size)
        shutil.copyfile(FX / "tag60_real30.mp4", f)                             # R06
        with quiet():
            self.assertEqual(media.start_conform(p, mode="off")["state"], "pending")
        self.assertEqual(self.job(p)["state"], "ready")

    def test_a_copy_without_a_duration_is_never_ready(self):
        p, f = self.clip("tag60_real30")
        self.preflight(p, f)
        good = p.p("00_inputs/intermediates/tag60_real30.0123456789.conform.mp4")
        good.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(FX / "cfr30.mp4", good)
        fake = {"ok": True, "path": str(good), "parts": [], "sidecar": None, "lane": "cpu", "reused": False,
                "skipped": None, "reason": None, "fps": 30.0, "lines": {"en": [], "ar": []}}
        real_probe = media.probe

        def no_duration(path):                                                  # R11
            r = real_probe(path)
            return dict(r, duration_s=None) if Path(path).name == good.name else r
        with mock.patch.object(MN, "conform", lambda *a, **k: dict(fake)), \
                mock.patch.object(media, "probe", no_duration):
            self.assertEqual(self.job(p)["state"], "failed")
        self.assertIn("could not be verified", self.rec(p)["reason"])
        with quiet():
            media.start_conform(p, mode="off")
        with mock.patch.object(MN, "conform", lambda *a, **k: dict(fake)):     # the control: with a duration, ready
            self.assertEqual(self.job(p)["state"], "ready")

    def test_a_same_size_replace_during_the_encode_is_seen(self):
        p, f = self.clip("tag60_real30")
        self.preflight(p, f)
        real = MN.conform

        def touched(src, *a, **k):                                              # R12: new bytes, same size
            res = real(src, *a, **k)
            t = time.time() + 120
            os.utime(src, (t, t))
            return res
        with mock.patch.object(MN, "conform", touched), mock.patch.object(media, "STALE_PASSES", 0):
            res = self.job(p)
        self.assertEqual((res["state"], self.rec(p)["state"]), ("pending", "pending"))
        self.assertIn("changed while its copy was made", self.rec(p)["reason"])


class TestR2JobNeverCrashes(_Client):
    """P3-8: a record write that fails inside the job's own error handler never crashes the job."""

    def test_a_record_that_cannot_be_written_never_crashes_the_job(self):
        from lib.file_lock import LockTimeout
        p, f = self.clip("tag60_real30")
        self.preflight(p, f)

        @contextlib.contextmanager
        def no_slot(site, **kw):
            raise RuntimeError("no slot today")
            yield
        with mock.patch("lib.gpu_lock.site_slot", no_slot), \
                mock.patch.object(media, "_store", side_effect=LockTimeout(p.p("00_inputs/preflight.json"), 120)):
            res = self.job(p)
        self.assertEqual(res["job"], "done")
        self.assertEqual(self.rec(p)["state"], "pending")                       # `reel conform --wait` makes it


class TestR2EditSkill(unittest.TestCase):
    """P3-9: the edit skill's conform line names the client folder like the rest of the file and says the wait may
    outlast a default Bash timeout."""

    def test_the_conform_line(self):
        t = (SK / "skills" / "edit" / "SKILL.md").read_text(encoding="utf-8")
        para = t[t.index("**Evenly timed copy**"):]
        para = para[:para.index("\n- ")]
        self.assertIn('reel conform --root "<CLIENT_FOLDER>" --video-id <ID> --wait', para)
        self.assertIn("timeout", para)


# --------------------------------------------------------------------------- fix round 3 (review 01ea9ae)
class _R3(_R2):
    def imp(self, p, src):
        with quiet():
            return media.conform_import(p, src)

    def assertOriginal(self, res, state):
        self.assertEqual((res["use"], res["state"], res["path"], res["parts"]), ("original", state, None, []), res)

    def ready(self, vid="V1", fname=None):
        p, f = self.clip("tag60_real30", vid=vid, fname=fname)
        self.preflight(p, f)
        self.assertEqual(self.job(p)["state"], "ready")
        return p, f

    def wait(self, p):
        """What `reel conform --wait` runs (cli.cmd_conform)."""
        with quiet():
            media.start_conform(p, mode="off")
        return self.job(p, wait_s=5)

    def age(self, p, seconds):
        import datetime as dt
        doc = self.doc(p)
        doc["files"][0]["normalise"]["conform"]["at"] = (dt.datetime.now().astimezone() - dt.timedelta(
            seconds=seconds)).isoformat(timespec="seconds")
        write_json(p.p("00_inputs/preflight.json"), doc)

    def foreign_claim(self, p, age_s=3600, **kw):
        cp = self.write_claim(p, 99999, pid_created=None, host="other-mac", host_id="mac:0000000000other", **kw)
        old = time.time() - age_s
        os.utime(cp, (old, old))
        return cp

    def edit(self, f, offset, data=b"\xab" * 4096):
        st = f.stat()
        with open(f, "r+b") as h:
            h.seek(offset)
            h.write(data)
        os.utime(f, ns=(st.st_atime_ns, st.st_mtime_ns))
        self.assertEqual((f.stat().st_size, f.stat().st_mtime_ns), (st.st_size, st.st_mtime_ns))

    def link_dir(self, link: Path, target: Path):
        """A directory junction (Windows) or symlink, removed at the end as a link only (never its target's files)."""
        try:
            if os.name == "nt":
                subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(target)], check=True, capture_output=True)
            else:
                os.symlink(target, link, target_is_directory=True)
        except (OSError, subprocess.CalledProcessError) as e:
            self.skipTest(f"no link: {e}")
        self.addCleanup(lambda: os.rmdir(link) if os.name == "nt" else os.unlink(link))


class TestR3TouchedSource(_R3):
    """P2-1: a source whose time changed but not its bytes (touch, a cloud or NAS re-sync, a copy tool that does not
    keep times). `reel conform --wait` checks it again (the sidecar's full sha256), reuses the copy and records the new
    time, so the next build imports the copy: the loop «run --wait» -> ready -> «run --wait» is gone."""

    def test_wait_after_a_time_only_change_gives_the_copy_again(self):
        for i, shift in enumerate((60, 30 * 86400, -86400)):    # a touch; a clock a month ahead; a restore a day back
            with self.subTest(shift=shift):
                p, f = self.ready(vid=f"T{i}", fname=f"touched {i}.mp4")
                r = self.rec(p)
                copy = self.root / r["path"]
                made = copy.stat().st_mtime_ns
                t = f.stat().st_mtime + shift
                os.utime(f, (t, t))
                res = self.imp(p, f)
                self.assertOriginal(res, "ready")                               # until it is checked again
                self.assertIn("modified time", res["reason"])
                self.assertIn("reel conform --wait", res["lines"]["en"][0])
                self.assertEqual(self.wait(p)["state"], "ready")
                for _ in range(2):                                              # and it stays so
                    res = self.imp(p, f)
                    self.assertEqual((res["use"], res["path"]), ("copy", r["path"]), res)
                self.assertEqual(copy.stat().st_mtime_ns, made)                 # reused, never encoded again
                self.assertEqual(self.rec(p)["source_mtime"], f.stat().st_mtime)

    def test_the_cli_wait_ends_the_loop(self):
        p, f = self.ready()
        t = f.stat().st_mtime + 60
        os.utime(f, (t, t))
        self.assertEqual(self.imp(p, f)["use"], "original")
        rc, doc, out = reel(self.root, "conform", "--wait", video_id="V1")
        self.assertEqual((rc, doc and doc.get("state")), (0, "ready"), out)
        self.assertEqual(self.imp(p, f)["use"], "copy")

    def test_a_ready_record_from_before_this_check_is_made_again(self):
        p, f = self.ready()
        doc = self.doc(p)
        for k in ("source_mtime", "source_fp"):
            doc["files"][0]["normalise"]["conform"].pop(k, None)               # written by the round-2 engine
        write_json(p.p("00_inputs/preflight.json"), doc)
        self.assertIsNotNone(media.conform_current(p, f, self.rec(p)))
        self.assertOriginal(self.imp(p, f), "ready")
        self.assertEqual(self.wait(p)["state"], "ready")
        self.assertEqual(self.imp(p, f)["use"], "copy")


class TestR3SameSizeEdit(_R3):
    """P3-5: a same-size edit with the time put back (a metadata tool editing in place with «keep the date»): the
    record keeps a cheap content check (sha256 of the size and the first and last FP_BYTES), compared at every build."""

    def test_a_same_size_edit_with_its_time_put_back_is_never_imported(self):
        p, f = self.ready()
        orig = f.read_bytes()
        st = f.stat()
        for where, offset in (("head", 0), ("tail", len(orig) - 4096)):
            with self.subTest(where):
                self.edit(f, offset)
                self.assertIn("content", media.conform_current(p, f, self.rec(p)))
                res = self.imp(p, f)
                self.assertOriginal(res, "ready")
                self.assertIn("reel conform --wait", res["lines"]["en"][0])
                self.edit(f, 0, orig)                                           # the control: the bytes back
                os.utime(f, ns=(st.st_atime_ns, st.st_mtime_ns))
                self.assertIsNone(media.conform_current(p, f, self.rec(p)))
                self.assertEqual(self.imp(p, f)["use"], "copy")

    def test_the_check_reads_the_first_and_last_part_only(self):
        with mock.patch.object(media, "FP_BYTES", 4096, create=True):
            p, f = self.ready()
            size = f.stat().st_size
            self.assertGreater(size, 4 * 4096)
            orig = f.read_bytes()
            for where, offset, seen in (("head", 100, True), ("tail", size - 200, True),
                                        ("middle", size // 2, False)):          # the middle: the stated limit
                with self.subTest(where):
                    self.edit(f, offset, b"\xcd" * 64)
                    why = media.conform_current(p, f, self.rec(p))
                    self.assertEqual(why is not None, seen, why)
                    self.edit(f, 0, orig)


class TestR3PathSpellings(_R3):
    """P3-4: one file under two spellings (a junction inside the client, an 8.3 short name) is one file: a reel never
    conforms the whole episode, and the build never silently uses the original."""

    def episode(self, footage_dir: Path, rel_footage: str):
        ep = make_vfr(footage_dir / "EP3.mp4", seconds=4)
        p = Paths(self.root, "EP3_R01")
        p.ensure_project()
        write_json(p.p("00_inputs/source.json"), {"footage": rel_footage, "in_ms": 2500, "out_ms": 5000,
                                                  "kind": "episode_reel", "episode_id": "EP3", "reel_id": "R01"})
        return p, ep

    def test_a_reel_whose_footage_is_reached_through_a_junction(self):
        real = self.root / "data" / "Episodes"
        p, ep = self.episode(real, "data/Episodes/EP3.mp4")    # plan._client_rel: the real path
        link = self.root / "data" / "EpLink"
        self.link_dir(link, real)
        via = link / "EP3.mp4"                                  # the editor's spelling
        self.assertEqual(media.conform_windows(p, via), [(2.5, 5.0)])
        self.preflight(p, via)
        self.assertEqual(self.job(p)["state"], "ready")
        r = self.rec(p)
        self.assertIsNone(r["path"])                            # parts, never the whole episode
        self.assertEqual([(x["from_ms"], x["to_ms"]) for x in r["parts"]], [(500, 7000)])
        for src in (ep, "data/Episodes/EP3.mp4", via):
            with self.subTest(src=str(src)):
                res = self.imp(p, src)
                self.assertEqual((res["use"], res["parts"]), ("copy", r["parts"]), res)

    def test_an_eight_dot_three_short_name(self):
        if os.name != "nt":
            self.skipTest("8.3 names are Windows only")
        import ctypes
        p, f = self.ready()
        buf = ctypes.create_unicode_buffer(1024)
        n = ctypes.windll.kernel32.GetShortPathNameW(str(f), buf, 1024)
        if not n or buf.value.lower() == str(f).lower():
            self.skipTest("this volume makes no 8.3 names")
        short = Path(buf.value)
        self.assertEqual(self.imp(p, short)["use"], "copy")
        self.assertTrue(media._same_file(short, f))


class TestR3ClaimCannotBeMade(_R3):
    """P3-2: a claim file that can't be created (a folder ACL; a name a virus scanner still holds after the last job
    removed it) never crashes `reel conform --wait`: retried for a moment, then a failed record with a plain line in
    both languages, the original used, the job's lock released."""

    def test_a_claim_that_cannot_be_created_is_a_failed_record_never_a_crash(self):
        from lib import writer_lock as WL
        p, f = self.clip("tag60_real30")
        self.preflight(p, f)
        with mock.patch.object(WL, "_create", side_effect=PermissionError(13, "Access is denied")), \
                mock.patch.object(media, "CLAIM_CREATE_S", 0.3, create=True):
            res = self.job(p, wait_s=5)
        self.assertEqual(res["state"], "failed")
        r = self.rec(p)
        self.assertContract(r)
        self.assertEqual(r["state"], "failed")
        self.assertIn("conform-job.claim", r["reason"])
        self.assertIn("reel conform --wait", r["lines"]["en"][0])
        self.assertTrue(ARABIC.search(r["lines"]["ar"][0]))
        self.assertIn("reel conform --wait", r["lines"]["ar"][0])
        res = self.imp(p, f)
        self.assertOriginal(res, "failed")
        self.assertEqual(res["lines"], r["lines"])
        got = []

        def take():
            with media.file_locked(p.p(media.JOB_REL), 0):
                got.append(True)
        t = threading.Thread(target=take)
        t.start()
        t.join(30)
        self.assertEqual(got, [True])                           # the job's own lock was released
        self.assertEqual(self.wait(p)["state"], "ready")        # and `--wait` makes it once the folder can be written

    def test_a_claim_held_for_a_moment_is_retried(self):
        from lib import writer_lock as WL
        p, f = self.clip("tag60_real30")
        self.preflight(p, f)
        real, calls = WL._create, []

        def flaky(path, rec):
            calls.append(1)
            if len(calls) <= 2:
                raise PermissionError(13, "delete pending")
            return real(path, rec)
        with mock.patch.object(WL, "_create", flaky):
            self.assertEqual(self.job(p, wait_s=0)["state"], "ready")
        self.assertGreaterEqual(len(calls), 3)


class TestR4Heartbeat(_R3):
    """Review 17729fc P3-1: the job rewrites its claim (`beat_at`) every HEARTBEAT_S while it runs. Another computer's
    claim counts while its file time is younger than CLAIM_STALE_S, whatever locks either side has: in a OneDrive or
    Dropbox folder each PC locks its own replica for real, and only the claim file is synced. A silent claim (a
    crashed or sleeping computer) is gone after that bound, not after 12 h."""

    def fast(self):
        for name, v in (("HEARTBEAT_S", 0.2), ("CLAIM_STALE_S", 1.5)):
            m = mock.patch.object(media, name, v, create=True)
            m.start()
            self.addCleanup(m.stop)

    def slow_job(self, p):
        """Machine A: the job in a thread, its encode held until `release` is set."""
        started, release, out = threading.Event(), threading.Event(), {}
        real = MN.conform

        def slow(*a, **k):
            started.set()
            release.wait(60)
            return real(*a, **k)
        m = mock.patch.object(MN, "conform", slow)
        m.start()
        self.addCleanup(m.stop)
        t = threading.Thread(target=lambda: out.update(res=media.run_conform_job(p)))
        t.start()
        self.addCleanup(lambda: (release.set(), t.join(60)))
        self.assertTrue(started.wait(60))
        return release, t, out

    def test_two_computers_a_running_jobs_claim_stays_live_on_the_other(self):
        from lib import writer_lock as WL
        self.fast()
        p, f = self.clip("tag60_real30")
        self.preflight(p, f)
        release, t, out = self.slow_job(p)
        cp, beats = p.p(CLAIM), set()
        with mock.patch.object(WL, "same_host", lambda rec: False):          # machine B: the claim is from another PC
            t0 = time.monotonic()
            while time.monotonic() - t0 < 3 * media.CLAIM_STALE_S:
                self.assertTrue(media._claim_live(cp), "a running job's claim was judged gone")
                rec = media._read_claim(cp)
                if rec:
                    beats.add(rec.get("beat_at"))
                time.sleep(0.1)
        release.set()
        t.join(60)
        self.assertEqual(out["res"]["state"], "ready")
        self.assertGreaterEqual(len(beats - {None}), 3)                        # it kept beating
        self.assertFalse(cp.exists())

    def test_a_silent_claim_from_another_computer_is_gone_after_the_bound(self):
        p, f = self.clip("tag60_real30")
        self.preflight(p, f)
        cp = self.foreign_claim(p, age_s=media.CLAIM_STALE_S + 60)              # a Mac asleep mid-job, 10+ min
        self.assertLess(media.CLAIM_STALE_S, 3600)
        self.assertFalse(media._job_running(p))
        self.assertEqual(self.job(p, wait_s=5)["state"], "ready")
        self.assertFalse(cp.exists())

    def test_a_pending_record_behind_a_silent_claim_is_reaped(self):
        p, f = self.clip("tag60_real30")
        self.preflight(p, f)
        self.age(p, 1800)
        self.foreign_claim(p, age_s=media.CLAIM_STALE_S + 60)
        self.assertOriginal(self.imp(p, f), "failed")

    def test_a_beating_claim_from_another_computer_counts_whatever_its_locks(self):
        for i, kw in enumerate(({"os_lock": True}, {"os_lock": False}, {}, {"os_lock": True})):
            with self.subTest(kw=kw, os_locks_here=i < 3):
                p, f = self.clip("tag60_real30", vid=f"B{i}")
                self.preflight(p, f)
                if i == 3:
                    self.no_os_locks()                                          # last: it stays on
                cp = self.foreign_claim(p, age_s=5, **kw)                       # a synced folder: a live job there
                before = cp.read_bytes()
                self.assertTrue(media._job_running(p))
                self.assertEqual(self.job(p, wait_s=0)["job"], "running")
                self.assertEqual(cp.read_bytes(), before)

    def test_the_heartbeat_never_writes_over_another_jobs_claim(self):
        self.fast()
        p, f = self.clip("tag60_real30")
        self.preflight(p, f)
        release, t, out = self.slow_job(p)
        cp = p.p(CLAIM)
        other = json.loads(cp.read_text(encoding="utf-8"))
        tmp = cp.with_name("other.tmp")
        tmp.write_text(json.dumps(dict(other, started_at="someone else's")), encoding="utf-8")
        for _ in range(100):                                                    # a takeover's new file (Windows
            try:                                                                # refuses while a beat has it open)
                os.replace(tmp, cp)
                break
            except PermissionError:
                time.sleep(0.01)
        time.sleep(1.0)                                                         # five beats
        self.assertEqual(json.loads(p.p(CLAIM).read_text(encoding="utf-8"))["started_at"], "someone else's")
        release.set()
        t.join(60)
        self.assertEqual(json.loads(p.p(CLAIM).read_text(encoding="utf-8"))["started_at"], "someone else's")


class TestR3Takeover(_R3):
    """P3-3 (known limit, CLOSEOUT) and the survivors N02 / N03: the takeover of a dead claim compares the claim it
    moved aside with the one it judged, and the put-back never replaces a claim made meanwhile."""

    def test_a_fresh_claim_made_while_a_dead_one_is_judged_is_put_back(self):     # N02
        p, f = self.clip("tag60_real30")
        self.preflight(p, f)
        self.no_os_locks()
        cp = self.write_claim(p, self.dead_pid())
        live, real_live, state = self.sleeper(), media._claim_live, {"raced": False}

        def racing(path, rec=None, **kw):
            if not state["raced"]:
                state["raced"] = True
                self.write_claim(p, live, started_at="the new job")             # a new job's claim lands meanwhile
                return False                                                    # the old one was judged dead
            return real_live(path, rec, **kw)
        with mock.patch.object(media, "_claim_live", racing):
            self.assertEqual(self.job(p, wait_s=1)["job"], "running")
        self.assertEqual(json.loads(cp.read_text(encoding="utf-8"))["started_at"], "the new job")
        self.assertFalse(list(cp.parent.glob(cp.name + ".stale-*")))

    def test_the_put_back_never_replaces_a_third_jobs_claim(self):               # N03
        p, f = self.clip("tag60_real30")
        self.preflight(p, f)
        self.no_os_locks()
        cp = self.write_claim(p, self.dead_pid())
        a_pid, c_pid = self.sleeper(), self.sleeper()
        real_live, real_read, state = media._claim_live, media._read_claim, {"n": 0}

        def racing_live(path, rec=None, **kw):
            if state["n"] == 0:
                state["n"] = 1
                self.write_claim(p, a_pid, started_at="job A")                  # A's fresh claim
                return False
            return real_live(path, rec, **kw)

        def racing_read(path):
            r = real_read(path)
            if Path(path).name.startswith(cp.name + ".stale-") and state["n"] == 1:
                state["n"] = 2
                self.write_claim(p, c_pid, started_at="job C")                  # C's claim, in the gap
            return r
        with mock.patch.object(media, "_claim_live", racing_live), mock.patch.object(media, "_read_claim", racing_read):
            self.assertEqual(self.job(p, wait_s=1)["job"], "running")
        self.assertEqual(json.loads(cp.read_text(encoding="utf-8"))["started_at"], "job C")
        aside = list(cp.parent.glob(cp.name + ".stale-*"))
        self.assertEqual([json.loads(x.read_text(encoding="utf-8"))["started_at"] for x in aside], ["job A"])


class TestR3MutantGaps(_R3):
    """The review's other survivors: N09 (the claim never waited for), N13 (a shared bare name), N15 (the frame-rate
    advice on a tone-map-only failure)."""

    def test_wait_waits_for_a_live_claim_without_os_locks(self):                 # N09
        p, f = self.clip("tag60_real30")
        self.preflight(p, f)
        self.no_os_locks()
        cp = self.write_claim(p, self.sleeper())
        timer = threading.Timer(1.5, cp.unlink)                                 # that job ends
        timer.start()
        self.addCleanup(timer.cancel)
        t0 = time.monotonic()
        res = self.job(p, wait_s=30)
        self.assertEqual((res["job"], res["state"]), ("done", "ready"))
        self.assertGreaterEqual(time.monotonic() - t0, 1.0)

    def test_a_bare_name_two_measured_files_share_is_never_guessed(self):        # N13
        cams = [self.root / "data" / c / "C0001.mp4" for c in ("CamA", "CamB")]
        for c in cams:
            c.parent.mkdir(parents=True)
            shutil.copyfile(FX / "tag60_real30.mp4", c)
        p = Paths(self.root, "CAM")
        p.ensure_project()
        with quiet():
            media.preflight(p, cams)
        self.assertEqual(self.job(p)["state"], "ready")
        self.assertOriginal(self.imp(p, "C0001.mp4"), "none")
        a, b = self.imp(p, cams[0]), self.imp(p, cams[1])
        self.assertEqual((a["use"], b["use"]), ("copy", "copy"))
        self.assertNotEqual(a["path"], b["path"])

    def test_a_tone_map_only_failure_has_no_frame_rate_advice(self):             # N15
        p, f = self.clip("tag60_real30")
        self.preflight(p, f)
        real = MN.decide

        def tone_map_only(m, *a, **k):
            return dict(real(m, *a, **k), actions=["tonemap"], cfr_fps=None, tonemap="pq")
        with mock.patch.object(MN, "decide", tone_map_only), mock.patch.object(MN, "_engine_ffmpeg", lambda: None):
            self.assertEqual(self.job(p)["state"], "failed")
        r = self.rec(p)
        self.assertIsNone(r["cfr_fps"])
        self.assertIn("FFmpeg", r["lines"]["en"][0])
        self.assertNotIn("constant-frame-rate export", " ".join(r["lines"]["en"]))
        self.assertNotIn("بمعدل فريمات ثابت", " ".join(r["lines"]["ar"]))


# --------------------------------------------------------------------------- fix round 4 (review 17729fc)
class TestR4StatedLimit(_R3):
    """P3-2: the limit as CONTRACT now states it. A same-size edit in the middle of a file (outside the first and last
    FP_BYTES) with its time put back is never caught: not at build time, not by `--wait` (a record that looks current
    is never hashed again), not by a new preflight."""

    def test_a_middle_edit_with_its_time_put_back_is_never_caught(self):
        with mock.patch.object(media, "FP_BYTES", 4096):
            p, f = self.ready()
            self.edit(f, f.stat().st_size // 2, b"\xcd" * 64)
            self.preflight(p, f)
            self.assertEqual(self.wait(p)["state"], "ready")
            self.assertEqual(self.imp(p, f)["use"], "copy")
            side = next(Path(self.root / self.rec(p)["path"]).parent.glob("*.conform.json"))
            self.assertNotEqual(json.loads(side.read_text(encoding="utf-8"))["source_sha256"],
                                hashlib.sha256(f.read_bytes()).hexdigest())     # no full hash ran


class TestR4CopyReplaced(_R3):
    """P3-3: the record keeps each copy file's size and time (copy_files), so a copy replaced under its name (a
    restore or a sync of that one file) is never imported, and `--wait` makes it again (the sidecar keeps them too)."""

    def test_a_copy_replaced_under_its_name_is_never_imported(self):
        for i, case in enumerate(("another video", "the same bytes, an older time")):
            with self.subTest(case):
                p, f = self.ready(vid=f"C{i}", fname=f"copy case {i}.mp4")
                copy = self.root / self.rec(p)["path"]
                self.assertEqual(self.rec(p)["copy_files"], [{"path": self.rec(p)["path"],
                                                              "size": copy.stat().st_size,
                                                              "mtime": copy.stat().st_mtime}])
                if i == 0:
                    shutil.copyfile(FX / "cfr30.mp4", copy)
                    planted = copy.read_bytes()
                else:
                    copy.write_bytes(copy.read_bytes())
                    old = time.time() - 86400
                    os.utime(copy, (old, old))
                planted_ns = copy.stat().st_mtime_ns
                res = self.imp(p, f)
                self.assertOriginal(res, "ready")
                self.assertIn("copy", res["reason"])
                self.assertEqual(self.wait(p)["state"], "ready")
                self.assertNotEqual(copy.stat().st_mtime_ns, planted_ns)        # made again, never reused
                if i == 0:
                    self.assertNotEqual(copy.read_bytes(), planted)
                self.assertEqual(self.imp(p, f)["use"], "copy")

    def test_a_ready_record_without_copy_files_is_made_again(self):
        p, f = self.ready()
        doc = self.doc(p)
        doc["files"][0]["normalise"]["conform"].pop("copy_files")                # written by the round-3 engine
        write_json(p.p("00_inputs/preflight.json"), doc)
        self.assertEqual(media.conform_current(p, f, self.rec(p)), media._WHY["old_record"][0])
        self.assertEqual(self.wait(p)["state"], "ready")
        self.assertEqual(self.imp(p, f)["use"], "copy")

    def test_the_parts_of_a_reel_are_each_checked(self):
        ep = make_vfr(self.root / "data" / "Episodes" / "EP3.mp4", seconds=4)
        p = Paths(self.root, "EP3_R01")
        p.ensure_project()
        write_json(p.p("00_inputs/source.json"), {"footage": "data/Episodes/EP3.mp4", "in_ms": 2500, "out_ms": 5000,
                                                  "kind": "episode_reel", "episode_id": "EP3", "reel_id": "R01"})
        self.preflight(p, ep)
        self.assertEqual(self.job(p)["state"], "ready")
        r = self.rec(p)
        self.assertEqual([x["path"] for x in r["copy_files"]], [x["path"] for x in r["parts"]])
        part = self.root / r["parts"][0]["path"]
        old = time.time() - 86400
        os.utime(part, (old, old))
        self.assertOriginal(self.imp(p, ep), "ready")


class TestR4ReasonLines(_R3):
    """P3-4: every reason the build line can carry has an Arabic twin; the Arabic line never carries English."""

    def test_every_reason_code_has_both_languages(self):
        self.assertGreaterEqual(len(media._WHY), 15)
        for code, (en, ar) in media._WHY.items():
            with self.subTest(code):
                self.assertTrue(en and ar)
                self.assertFalse(ARABIC.search(en), en)
                self.assertTrue(ARABIC.search(ar), ar)
                self.assertEqual(set(re.findall(r"{(\w+)}", en)), set(re.findall(r"{(\w+)}", ar)))

    def test_the_checks_give_coded_reasons_only(self):
        import inspect
        for fn in (media.conform_current, media._copy_problem):
            with self.subTest(fn.__name__):
                self.assertEqual(re.findall(r"return\s+f?[\"']", inspect.getsource(fn)), [])

    def test_the_arabic_build_line_has_an_arabic_reason(self):
        p, f = self.ready()
        t = f.stat().st_mtime + 60
        os.utime(f, (t, t))
        res = self.imp(p, f)
        self.assertEqual(res["reason"], media._WHY["source_mtime"][0])
        self.assertIn(media._WHY["source_mtime"][1], res["lines"]["ar"][0])
        self.assertNotIn(res["reason"], res["lines"]["ar"][0])
        self.assertIn(res["reason"], res["lines"]["en"][0])


class TestR4MutantGaps(_R3):
    """P3-5: the review's survivors R07 (a source that can't be read at build time) and R21 (the end of a file
    between FP_BYTES and 2 x FP_BYTES long)."""

    def test_a_source_that_cannot_be_read_at_build_time_is_never_imported(self):       # R07
        p, f = self.ready()
        with mock.patch.object(media, "_fingerprint", lambda src: None):
            res = self.imp(p, f)
        self.assertOriginal(res, "ready")
        self.assertEqual(res["reason"], media._WHY["source_unreadable"][0])
        self.assertEqual(self.imp(p, f)["use"], "copy")                          # the control

    def test_the_end_of_a_file_between_one_and_two_windows_is_read(self):              # R21
        g = self.tmp / "short phone clip.bin"
        g.write_bytes(bytes(range(256)) * 24)                                    # 6144 bytes
        with mock.patch.object(media, "FP_BYTES", 4096):
            a = media._fingerprint(g)
            for offset in (6000, 100):
                with self.subTest(offset=offset):
                    data = bytearray(g.read_bytes())
                    data[offset] ^= 0xFF
                    h = self.tmp / f"edited {offset}.bin"
                    h.write_bytes(bytes(data))
                    self.assertNotEqual(media._fingerprint(h), a)


class TestR4FolderCannotBeWritten(_R3):
    """P3-6: when the item's folder can't be written (preflight.json can't be saved either), `--wait` and the build
    each give ONE plain line in both languages: the folder can't be written and the original is used."""

    def assertNoWrite(self, lines):
        self.assertEqual((len(lines["en"]), len(lines["ar"])), (1, 1), lines)
        self.assertEqual(lines, {"en": [media._NO_WRITE[0]], "ar": [media._NO_WRITE[1]]})
        self.assertIn("can't be written", lines["en"][0])
        self.assertIn("original", lines["en"][0])
        self.assertTrue(ARABIC.search(lines["ar"][0]))

    def deny_create(self, folder: Path):
        """A real deny-create ACE (Everyone: write data / add file, append / add folder) on `folder` only."""
        if os.name != "nt":
            self.skipTest("Windows ACLs")
        r = subprocess.run(["icacls", str(folder), "/deny", "*S-1-1-0:(WD,AD)"], capture_output=True, text=True)
        if r.returncode:
            self.skipTest(f"icacls: {r.stdout} {r.stderr}")
        undo = lambda: subprocess.run(["icacls", str(folder), "/remove:d", "*S-1-1-0"], capture_output=True)  # noqa
        self.addCleanup(undo)
        try:
            (folder / "probe.tmp").write_bytes(b"")
        except PermissionError:
            return undo
        self.skipTest("the deny ACE does not stop this user")

    def test_a_folder_that_cannot_be_written(self):
        p, f = self.clip("tag60_real30")
        self.preflight(p, f)
        self.age(p, 600)
        undo = self.deny_create(p.p("00_inputs"))
        with mock.patch.object(media, "CLAIM_CREATE_S", 0.3):
            res = self.job(p, wait_s=5)
        self.assertEqual((res["job"], res["state"]), ("failed", "failed"))
        self.assertNoWrite(res["lines"])
        res = self.imp(p, f)
        self.assertEqual(res["use"], "original")
        self.assertNoWrite(res["lines"])
        undo()
        self.assertEqual(self.wait(p)["state"], "ready")

    def test_the_same_with_the_writes_refused_in_process(self):
        from lib import writer_lock as WL
        p, f = self.clip("tag60_real30")
        self.preflight(p, f)
        self.age(p, 600)
        denied = PermissionError(13, "Access is denied")
        with mock.patch.object(WL, "_create", side_effect=denied), mock.patch.object(media, "CLAIM_CREATE_S", 0.3), \
                mock.patch.object(media, "write_json", side_effect=denied):
            res = self.job(p, wait_s=5)
            self.assertEqual((res["job"], res["state"]), ("failed", "failed"))
            self.assertNoWrite(res["lines"])
            res = self.imp(p, f)
            self.assertEqual(res["use"], "original")
            self.assertNoWrite(res["lines"])


if __name__ == "__main__":
    unittest.main()
