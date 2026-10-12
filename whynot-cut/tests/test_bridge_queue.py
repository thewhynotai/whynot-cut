"""Bridge queue robustness (3.0 T2.9; engine review IM-4, IM-5, IM-6, MI-22).

A fake bridge (a thread playing the CEP daemon's side of the protocol on a temp queue folder) checks the engine side:
expiry, cancel on timeout, claim-based timeouts, cleanup and the sweeper, the machine-wide build lock, the runtime
version handshake, the `_prev_` project restored on a failed build, and the wait for Premiere's media before frames are
exported. The real js/bridge.js is run in node with a stubbed CEP (`window.__adobe_cep__`) for the panel side. Run:
    <runtime python> -m unittest discover -s <plugin>/tests -p test_bridge_queue.py -v
"""
import sys as _sys
_sys.dont_write_bytecode = True
import _isolation  # noqa: F401,E402  G79: sandbox the engine home first (tests/_isolation.py)
import contextvars
import datetime as dt
import json
import os
import shutil
import subprocess
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

SK = Path(__file__).resolve().parents[1]
sys_path = str(SK / "engine" / "reel")
if sys_path not in _sys.path:
    _sys.path.insert(0, sys_path)

from lib import cep_queue, common, ppro_bridge  # noqa: E402
from test_round4_intake import slate_gradient_left  # noqa: E402  (a function only: no test class is imported)

CEP = SK / "templates" / "premiere" / "cep_bridge"


def _iso(t: float) -> str:
    return dt.datetime.fromtimestamp(t, dt.timezone.utc).isoformat(timespec="seconds")


class FakeBridge:
    """Plays the 3.1.1 bridge daemon on `queue`: heartbeat (version, role, busy, current), claim by rename, an expired
    job answered {ok:false, error:"expired"} without running, `<id>.claimed`, a result written atomically.
    `delays[action]` = seconds the host 'works'; `mute` = never claims; `ran` = (job id, action, start, end)."""

    def __init__(self, queue: Path, host="PPRO", version=None, mute=False, delays=None, beat=True):
        self.q, self.host, self.mute, self.delays, self.do_beat = Path(queue), host, mute, dict(delays or {}), beat
        self.version = version or ppro_bridge.BRIDGE_VERSION
        self.busy, self.current = False, None
        self.ran, self.claimed, self.first_seen = [], [], {}
        self.stop = threading.Event()
        self.t = threading.Thread(target=self.loop, daemon=True)

    def __enter__(self):
        self.q.mkdir(parents=True, exist_ok=True)
        if self.do_beat:
            self.beat()
        self.t.start()
        return self

    def __exit__(self, *a):
        self.stop.set()
        self.t.join(5)

    def beat(self):
        tmp = self.q / "bridge.heartbeat.fake.tmp"
        tmp.write_text(json.dumps({"at": time.time() * 1000, "busy": self.busy, "version": self.version,
                                   "host": self.host, "role": "daemon", "current": self.current}), encoding="utf-8")
        try:
            tmp.replace(self.q / "bridge.heartbeat")
        except PermissionError:          # Windows: the reader has the file open this instant; next beat wins
            pass

    def loop(self):
        while not self.stop.is_set():
            if self.do_beat:
                self.beat()
            jobs = sorted(self.q.glob("*.job.json"))
            for jf in jobs:
                self.first_seen.setdefault(jf.name[:-len(".job.json")], time.time())
            if jobs and not self.mute:
                self.run(jobs[0])
            time.sleep(0.03)

    def run(self, jf: Path):
        run = jf.with_name(jf.name.replace(".job.json", ".running"))
        try:
            jf.rename(run)
        except OSError:
            return
        job = json.loads(run.read_text(encoding="utf-8"))
        self.claimed.append(job)
        if time.time() > dt.datetime.fromisoformat(job["expires_at"]).timestamp():
            self.finish(job, run, {"ok": False, "error": "expired", "at": time.time() * 1000})
            return
        (self.q / f"{job['id']}.claimed").write_text(json.dumps({"at": time.time() * 1000, "by": "daemon"}),
                                                     encoding="utf-8")
        data = json.loads(Path(job["data_file"]).read_text(encoding="ascii"))
        self.busy, self.current = True, job["id"]
        start = time.time()
        end = start + self.delays.get(data["action"], 0)
        while time.time() < end and not self.stop.is_set():
            self.beat()
            time.sleep(0.05)
        self.ran.append((job["id"], data["action"], start, time.time()))
        self.finish(job, run, {"ok": True, "result": json.dumps({"ok": True, "action": data["action"],
                                                                  "result": {"echo": data.get("echo")}}),
                               "at": time.time() * 1000})
        self.busy, self.current = False, None

    def finish(self, job, run, payload):
        tmp = self.q / f"{job['id']}.result.fake.tmp"
        tmp.write_text(json.dumps(payload), encoding="utf-8")
        tmp.replace(self.q / f"{job['id']}.result.json")
        run.unlink()


class _Home(unittest.TestCase):
    """A temp engine home bound for the test (the queue and scripts resolve from the bound Context)."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.home = self.tmp / "home"
        self.home.mkdir()
        self._ctx = common.use_context(common.Context(home=self.home))
        self._ctx.__enter__()
        self.q = ppro_bridge.queue_dir()
        self.script = self.home / "ppro-scripts" / "nh_ppro_lib.jsx"
        self.script.parent.mkdir(parents=True)
        self.script.write_text("// x", encoding="utf-8")

    def tearDown(self):
        self._ctx.__exit__(None, None, None)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def leftovers(self):
        return sorted(f.name for f in self.q.iterdir() if f.name != "bridge.heartbeat")


# ===================================================================================================== IM-4
class TestExpiryCancelCleanup(_Home):
    def test_the_job_carries_expires_at_and_resolved_paths(self):
        with FakeBridge(self.q) as fb:
            t0 = time.time()
            r = cep_queue.submit(self.q, self.script, "ping", {"echo": 1}, timeout=10, claim_timeout=30)
        self.assertTrue(r["ok"], r)
        job = fb.claimed[0]
        exp = dt.datetime.fromisoformat(job["expires_at"]).timestamp()
        self.assertTrue(t0 + 29 <= exp <= t0 + 32, (t0, job["expires_at"]))
        self.assertEqual(job["script"], str(self.script.resolve()))
        self.assertEqual(job["data_file"], str(Path(job["data_file"]).resolve()))

    def test_an_unclaimed_job_is_cancelled_on_timeout_and_never_runs(self):
        with FakeBridge(self.q, mute=True) as fb:
            t0 = time.time()
            r = cep_queue.submit(self.q, self.script, "build_project", timeout=1)
            self.assertLess(time.time() - t0, 4)
            fb.mute = False                         # Premiere frees up later: the job must not run then
            time.sleep(0.4)
        self.assertFalse(r["ok"])
        self.assertTrue(r["error"].startswith("timeout"), r)
        self.assertTrue(r.get("cancelled"), r)
        self.assertIn("how", r)
        self.assertEqual(fb.ran, [])
        self.assertEqual(self.leftovers(), [])      # job, data and cancelled marker are gone

    def test_an_expired_job_is_answered_expired_and_not_run(self):
        """A job left behind by a CLI that died (no cancel): the bridge sees it hours later."""
        self.q.mkdir(parents=True)
        data = self.q / "old.data.json"
        data.write_text(json.dumps({"action": "build_project"}), encoding="ascii")
        (self.q / "old.job.json").write_text(json.dumps({
            "id": "old", "action": "build_project", "script": str(self.script), "data_file": str(data),
            "expires_at": _iso(time.time() - 3600)}), encoding="utf-8")
        with FakeBridge(self.q) as fb:
            deadline = time.time() + 5
            while not (self.q / "old.result.json").exists() and time.time() < deadline:
                time.sleep(0.05)
        self.assertEqual(fb.ran, [])
        self.assertEqual(json.loads((self.q / "old.result.json").read_text(encoding="utf-8"))["error"], "expired")

    def test_the_engine_reports_an_expired_answer_as_a_timeout(self):
        with FakeBridge(self.q, mute=True) as fb:
            with mock.patch.object(cep_queue, "_cancel", return_value=False):     # the claim races the cancel
                threading.Timer(0.6, lambda: setattr(fb, "mute", False)).start()
                r = cep_queue.submit(self.q, self.script, "ping", timeout=5, claim_timeout=0.2)
        self.assertFalse(r["ok"])
        self.assertTrue(r.get("expired") and r["error"].startswith("timeout"), r)
        self.assertEqual(fb.ran, [])

    def test_the_result_timeout_starts_at_the_claim(self):
        """Queue wait behind another job does not count against the caller's timeout (IM-5)."""
        with FakeBridge(self.q, delays={"slow": 1.5}) as fb:
            other = threading.Thread(target=cep_queue.submit, args=(self.q, self.script, "slow"), kwargs={"timeout": 10})
            other.start()
            time.sleep(0.2)
            r = cep_queue.submit(self.q, self.script, "ping", {"echo": 2}, timeout=1.0, claim_timeout=10)
            other.join()
        self.assertTrue(r["ok"], r)
        self.assertGreater(r["elapsed_s"], 1.0)                       # it waited longer than its own timeout
        self.assertEqual([a for _, a, *_ in fb.ran], ["slow", "ping"])

    def test_data_result_and_claim_files_are_removed_after_reading(self):
        with FakeBridge(self.q):
            r = cep_queue.submit(self.q, self.script, "ping", {"echo": "عربي"}, timeout=10)
        self.assertTrue(r["ok"], r)
        self.assertEqual(r["response"]["result"]["echo"], "عربي")
        self.assertEqual(self.leftovers(), [])

    def test_a_bridge_that_stops_before_the_claim_cancels_the_wait(self):
        with FakeBridge(self.q, mute=True) as fb:
            with mock.patch.object(cep_queue, "CLAIM_CHECK_S", 0.2), \
                    mock.patch.object(cep_queue, "status", side_effect=[{"alive": False, "detail": "gone"}]):
                r = cep_queue.submit(self.q, self.script, "ping", timeout=30, st={"alive": True})
        self.assertFalse(r["ok"])
        self.assertTrue(r.get("cancelled"), r)
        self.assertEqual(fb.ran, [])

    def test_the_sweeper_removes_day_old_files_only(self):
        self.q.mkdir(parents=True)
        old = time.time() - 2 * 86400
        names = ["a.data.json", "a.result.json", "a.job.json", "a.running", "a.claimed", "a.job.cancelled", "a.tmp"]
        for n in names + [f"fresh-{n}" for n in names] + ["bridge.heartbeat", ".build.lock"]:
            (self.q / n).write_text("{}", encoding="utf-8")
        for n in names + ["bridge.heartbeat", ".build.lock"]:
            os.utime(self.q / n, (old, old))
        gone = cep_queue.sweep(self.q)
        self.assertEqual(sorted(gone), sorted(names))
        self.assertEqual(sorted(f.name for f in self.q.iterdir()),
                         sorted([f"fresh-{n}" for n in names] + ["bridge.heartbeat", ".build.lock"]))

    def test_submit_sweeps_first(self):
        self.q.mkdir(parents=True)
        stale = self.q / "x.result.json"
        stale.write_text("{}", encoding="utf-8")
        os.utime(stale, (time.time() - 2 * 86400,) * 2)
        with FakeBridge(self.q):
            self.assertTrue(cep_queue.submit(self.q, self.script, "ping", timeout=10)["ok"])
        self.assertFalse(stale.exists())

    def test_status_tolerates_a_heartbeat_without_at(self):
        self.q.mkdir(parents=True)
        (self.q / "bridge.heartbeat").write_text(json.dumps({"busy": False, "version": "3.1.1"}), encoding="utf-8")
        st = cep_queue.status(self.q)
        self.assertFalse(st["alive"])
        self.assertIn("no time", st["detail"])

    def test_status_reports_orphaned_running_jobs(self):
        with FakeBridge(self.q, mute=True):
            orphan = self.q / "dead.running"
            orphan.write_text("{}", encoding="utf-8")
            os.utime(orphan, (time.time() - 3600,) * 2)
            (self.q / "fresh.running").write_text("{}", encoding="utf-8")
            st = ppro_bridge.status()
        self.assertEqual(st.get("orphans"), ["dead"])
        self.assertEqual(st["role"], "daemon")


# ===================================================================================================== IM-5
class TestVersionHandshake(_Home):
    def test_an_old_running_bridge_is_refused_with_a_restart_hint(self):
        with FakeBridge(self.q, version="3.1.0") as fb:
            r = ppro_bridge.submit("ping", timeout=5)
        self.assertFalse(r["ok"])
        self.assertIn("3.1.0", r["error"])
        self.assertIn(ppro_bridge.BRIDGE_VERSION, r["error"])
        self.assertIn(f"Restart Premiere to load bridge {ppro_bridge.BRIDGE_VERSION}", r["how"])
        self.assertEqual(fb.claimed, [])
        self.assertEqual(self.leftovers(), [])                     # nothing was queued

    def test_the_matching_bridge_runs_the_job(self):
        with FakeBridge(self.q):
            r = ppro_bridge.submit("ping", timeout=10)
        self.assertTrue(r["ok"], r)

    def test_after_effects_checks_the_same_bundle_version(self):
        from lib import ae_bridge
        with FakeBridge(ae_bridge.queue_dir(), host="AEFT", version="3.0.0") as fb:
            r = ae_bridge.submit("ping", timeout=5)
        self.assertFalse(r["ok"])
        self.assertIn("Restart After Effects", r["how"])
        self.assertEqual(fb.claimed, [])

    def test_the_bridge_version_is_311_everywhere(self):
        import re
        js = (CEP / "js/bridge.js").read_text(encoding="utf-8")
        self.assertEqual(ppro_bridge.BRIDGE_VERSION, "3.1.1")
        self.assertIn("var VERSION = '3.1.1'", js)
        self.assertRegex((CEP / "CSXS/manifest.xml").read_text(encoding="utf-8"), re.escape('ExtensionBundleVersion="3.1.1"'))

    def test_submit_signatures_are_stable(self):
        """reel serve's FileQueueAdapter calls these: positional parameters never change (keyword-only may be added)."""
        import inspect
        from lib import ae_bridge
        self.assertEqual(list(inspect.signature(ppro_bridge.submit).parameters)[:4], ["action", "data", "timeout", "script"])
        self.assertEqual(list(inspect.signature(ae_bridge.submit).parameters)[:3], ["action", "data", "timeout"])


class TestBuildLock(_Home):
    def test_two_concurrent_builds_run_one_after_the_other(self):
        """Two sessions build at once: the second job is queued only after the first finished, and its own 900 s clock
        never runs while it waits."""
        out = {}

        def build(name):
            with ppro_bridge.build_lock(f"ppro-build {name}", wait_s=20, poll_s=0.05):
                out[name] = ppro_bridge.submit("build_project", {"echo": name}, timeout=5)

        with FakeBridge(self.q, delays={"build_project": 0.8}) as fb:
            # each session's thread runs in a copy of this test's context (the bound engine home)
            ts = [threading.Thread(target=contextvars.copy_context().run, args=(build, n)) for n in ("A", "B")]
            for t in ts:
                t.start()
                time.sleep(0.05)
            for t in ts:
                t.join(30)
        self.assertTrue(out["A"]["ok"] and out["B"]["ok"], out)
        (j1, _, s1, e1), (j2, _, s2, e2) = fb.ran
        self.assertGreaterEqual(fb.first_seen[j2], e1 - 0.05)       # queued only after the first build ended
        self.assertFalse((self.q / cep_queue.LOCK_NAME).exists())

    def test_a_held_lock_refuses_after_the_wait(self):
        with ppro_bridge.build_lock("ppro-build A"):
            with self.assertRaises(cep_queue.BuildLockBusy) as cm:
                with ppro_bridge.build_lock("ppro-build B", wait_s=0.2, poll_s=0.05):
                    pass
        self.assertIn("ppro-build A", str(cm.exception))
        r = cep_queue.lock_busy_result(cm.exception, "Premiere")
        self.assertIn("ppro-build A", r["blocked"])
        self.assertIn("how", r)

    def test_a_dead_or_expired_holder_is_taken_over(self):
        import socket
        self.q.mkdir(parents=True, exist_ok=True)
        lock = self.q / cep_queue.LOCK_NAME
        for rec in ({"pid": 999999, "host": socket.gethostname(), "what": "crashed", "expires_at": time.time() + 999},
                    {"pid": os.getpid(), "host": "another-pc", "what": "expired", "expires_at": time.time() - 1}):
            lock.write_text(json.dumps(rec), encoding="utf-8")
            with mock.patch("lib.writer_lock.pid_alive", lambda pid, created=None: pid != 999999):
                with ppro_bridge.build_lock("ppro-build new", wait_s=0) as mine:
                    self.assertEqual(cep_queue.read_lock(self.q), mine)
            self.assertFalse(lock.exists())

    def test_ppro_build_waits_for_the_lock_and_reports_busy(self):
        from lib import ppro_build
        p = _reel(self.tmp)
        with mock.patch("lib.ppro_bridge.status", return_value={"alive": True}), \
                mock.patch("lib.ppro_bridge.submit") as sub, ppro_bridge.build_lock("ppro-frames other"):
            r = ppro_build.build(p, lock_wait_s=0.1)
        self.assertEqual(r["status"], "BRIDGE_BUSY", r)
        self.assertIn("ppro-frames other", r["blocked"])
        sub.assert_not_called()

    def test_ppro_frames_and_motion_build_take_the_lock(self):
        from lib import ae_bridge, motion_build, ppro_build
        p = _reel(self.tmp)
        with ppro_bridge.build_lock("ppro-build other"), mock.patch("lib.ppro_bridge.submit") as sub:
            r = ppro_build.export_frames(p, times=[1.0], lock_wait_s=0.1)
        self.assertFalse(r["ok"])
        self.assertIn("ppro-build other", r["blocked"])
        sub.assert_not_called()
        with ae_bridge.build_lock("motion-build other"), mock.patch.object(motion_build, "preconditions") as pre:
            r = motion_build.build(p, lock_wait_s=0.1)
        self.assertEqual(r["status"], "REFUSED")
        self.assertIn("motion-build other", r["blocked"])
        pre.assert_not_called()


def _reel(tmp: Path):
    from lib.common import Paths, write_json
    root = tmp / "C"
    (root / "assets").mkdir(parents=True, exist_ok=True)
    (root / "data").mkdir(exist_ok=True)
    p = Paths(root, "V1")
    p.ensure_project()
    write_json(p.p("01_analysis/timeline-spec.json"), {"events": [], "duration_frames": 240, "main_segments": []})
    return p


# ===================================================================================================== MI-22
class TestPreviousProjectKept(_Home):
    """The old project becomes `_prev_` only when the new one was built; a failed build puts it back."""

    DATA = {"_missing": [], "graphics": [], "native_caption_track": False, "sharpen_v1": None,
            "sequence_name": "V1", "track_names": {}}

    def run_build(self, answer):
        from lib import ppro_build
        p = _reel(self.tmp)
        prj = p.p(f"07_premiere/project/{p.video_id}_{common.project_prefix()}_EDIT.prproj")
        prj.parent.mkdir(parents=True, exist_ok=True)
        prj.write_text("OLD", encoding="utf-8")

        def submit(action, data=None, timeout=0, **kw):
            if action == "close_project_path":
                return {"ok": True, "response": {"ok": True, "result": {"closed": True}}}
            return answer(prj)

        with mock.patch("lib.ppro_bridge.status", return_value={"alive": True}), \
                mock.patch("lib.ppro_bridge.submit", side_effect=submit), \
                mock.patch.object(ppro_build, "job_data", return_value=dict(self.DATA)), \
                mock.patch("lib.verify.editor_modified", return_value=None):
            r = ppro_build.build(p, overwrite=True)
        return r, prj

    def test_a_failed_build_restores_the_previous_project(self):
        r, prj = self.run_build(lambda prj: {"ok": False, "error": "bridge not running"})
        self.assertEqual(r["status"], "FAILED")
        self.assertEqual(prj.read_text(encoding="utf-8"), "OLD")
        self.assertEqual(list(prj.parent.glob("*_prev_*")), [])
        self.assertTrue(r["previous_restored"])
        self.assertIsNone(r["previous_version_backup"])

    def test_a_successful_build_keeps_the_previous_one_as_prev(self):
        def built(prj):
            prj.write_text("NEW", encoding="utf-8")
            return {"ok": True, "response": {"ok": True, "result": {}}}
        r, prj = self.run_build(built)
        self.assertNotEqual(r["status"], "FAILED")
        self.assertEqual(prj.read_text(encoding="utf-8"), "NEW")
        prev = list(prj.parent.glob("*_prev_*"))
        self.assertEqual([x.read_text(encoding="utf-8") for x in prev], ["OLD"])
        self.assertEqual(r["previous_version_backup"], str(prev[0]))

    def test_a_build_still_running_in_premiere_keeps_the_backup_aside(self):
        """Timed out after the claim: Premiere may still save the new project at that path, so nothing is put back."""
        r, prj = self.run_build(lambda prj: {"ok": False, "error": "timeout after 900s", "claimed": True})
        self.assertEqual(r["status"], "FAILED")
        self.assertFalse(prj.exists())
        self.assertEqual(len(list(prj.parent.glob("*_prev_*"))), 1)
        self.assertFalse(r["previous_restored"])


# ===================================================================================================== IM-6
class SlateBridge:
    """export_frames stand-in: the first `pending_exports` exports come out as the Media pending slate."""

    def __init__(self, pending_exports=0):
        self.calls, self.left = [], pending_exports

    def __call__(self, action, payload, timeout=0, **kw):
        from PIL import Image
        import numpy as np
        self.calls.append((Path(payload["out_dir"]).name, list(payload["times"])))
        slate = self.left > 0
        self.left -= 1
        for t in payload["times"]:
            out = Path(payload["out_dir"]) / ("frame_%06d.png" % round(t * 1000))
            if slate:
                slate_gradient_left(270, 480).save(out)
            else:
                rng = np.random.default_rng(round(t * 1000))
                Image.fromarray(rng.integers(0, 255, (240, 135, 3), dtype=np.uint8)).save(out)
        return {"ok": True, "response": {"ok": True, "result": {"frames": [{"t": t} for t in payload["times"]]}}}


class TestWaitForMedia(_Home):
    TIMES = [1.0, 2.0, 3.0]

    def export(self, bridge, **kw):
        from lib import ppro_build
        p = _reel(self.tmp)
        with mock.patch("lib.ppro_bridge.submit", bridge), mock.patch("time.sleep") as sleep:
            r = ppro_build.export_frames(p, times=list(self.TIMES), **kw)
        return r, sleep

    def test_it_polls_one_frame_until_the_media_is_online_then_exports(self):
        b = SlateBridge(pending_exports=2)
        r, sleep = self.export(b, retries=0)
        self.assertTrue(r["ok"], r)
        self.assertEqual(r["pending_frames"], [])
        self.assertEqual(r["media_wait"]["online"], True)
        self.assertEqual(r["media_wait"]["polls"], 3)
        self.assertEqual([len(ts) for _, ts in b.calls], [1, 1, 1, 3])        # 3 one-frame polls, then the export
        self.assertEqual(sleep.call_count, 2)
        self.assertFalse((Path(r["dir"]) / "_media_check").exists())        # the probe frames are not evidence
        self.assertEqual(r["frames"], 3)

    def test_it_never_reports_ok_while_a_slate_remains(self):
        b = SlateBridge(pending_exports=999)                                 # the media never comes online
        r, _ = self.export(b, retries=1, media_wait_s=6, media_poll_s=3)
        self.assertFalse(r["ok"])
        self.assertEqual(r["media_wait"], {"online": False, "polls": 2, "limit_s": 6})
        self.assertEqual(r["pending_frames"], self.TIMES)
        self.assertEqual(r["frames"], 0)
        self.assertIn("Media pending", r["error"])

    def test_no_wait_when_disabled(self):
        b = SlateBridge()
        r, sleep = self.export(b, media_wait_s=0)
        self.assertTrue(r["ok"], r)
        self.assertEqual(len(b.calls), 1)
        self.assertIsNone(r["media_wait"]["online"])
        sleep.assert_not_called()


# ===================================================================================================== bridge.js
NODE = shutil.which("node")
HARNESS = r"""
const vm = require('vm'), fs = require('fs'), path = require('path');
const [bridgeJs, extDir, role, runMs, outFile] = process.argv.slice(2);
const evals = [], state = { textContent: '' }, logEl = { textContent: '' };
const cep = {
  getExtensionId: () => 'ai.thewhynot.cut.bridge.' + role,
  getHostEnvironment: () => JSON.stringify({ appName: 'PPRO' }),
  getSystemPath: () => 'file:///' + extDir.replace(/\\/g, '/'),
  evalScript: (code, cb) => {
    const m = /\.run\(("(?:[^"\\]|\\.)*")\);$/.exec(code);
    const data = JSON.parse(fs.readFileSync(JSON.parse(m[1]), 'ascii'));
    evals.push(data.action);
    setTimeout(() => cb(JSON.stringify({ ok: true, action: data.action, result: { echo: data.echo } })), 30);
  }
};
const ctx = { window: { __adobe_cep__: cep, cep_node: { require } }, document: { getElementById: (id) => id === 'state' ? state : logEl },
              setInterval: (f) => setInterval(f, 50), process, console };
vm.runInNewContext(fs.readFileSync(bridgeJs, 'utf8'), ctx);
setTimeout(() => { fs.writeFileSync(outFile, JSON.stringify({ evals, state: state.textContent, log: logEl.textContent })); process.exit(0); }, +runMs);
"""


@unittest.skipUnless(NODE, "needs node to run js/bridge.js with a stubbed CEP")
class TestBridgeJs(_Home):
    def setUp(self):
        super().setUp()
        self.ext = self.tmp / "ext"
        self.ext.mkdir()
        (self.ext / "bridge-config.json").write_text(json.dumps({"base": str(self.home)}), encoding="utf-8")
        self.harness = self.tmp / "harness.js"
        self.harness.write_text(HARNESS, encoding="utf-8")
        self.q.mkdir(parents=True)

    def run_bridge(self, role="daemon", ms=1500, during=None):
        out = self.tmp / f"out-{role}.json"
        p = subprocess.Popen([NODE, str(self.harness), str(CEP / "js/bridge.js"), str(self.ext), role, str(ms), str(out)],
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8")
        if during:
            during(p)
        so, se = p.communicate(timeout=60)
        self.assertEqual(p.returncode, 0, se)
        return json.loads(out.read_text(encoding="utf-8"))

    def job(self, jid, action, expires_in):
        data = self.q / f"{jid}.data.json"
        data.write_text(json.dumps({"action": action, "echo": jid}), encoding="ascii")
        (self.q / f"{jid}.job.json").write_text(json.dumps({
            "id": jid, "action": action, "script": str(self.script.resolve()), "data_file": str(data.resolve()),
            "expires_at": _iso(time.time() + expires_in)}), encoding="utf-8")

    def result(self, jid):
        return json.loads((self.q / f"{jid}.result.json").read_text(encoding="utf-8"))

    def test_the_daemon_runs_a_live_job_and_discards_an_expired_one(self):
        self.job("a-old", "build_project", -60)
        self.job("b-new", "ping", 60)
        out = self.run_bridge()
        self.assertEqual(out["evals"], ["ping"])                          # the expired build never reached the host
        self.assertEqual(self.result("a-old")["error"], "expired")
        self.assertFalse(self.result("a-old")["ok"])
        self.assertTrue(self.result("b-new")["ok"])
        self.assertEqual(json.loads(self.result("b-new")["result"])["result"]["echo"], "b-new")
        self.assertEqual(json.loads((self.q / "b-new.claimed").read_text(encoding="utf-8"))["by"], "daemon")
        self.assertEqual(sorted(f.name for f in self.q.glob("*.running")) + sorted(f.name for f in self.q.glob("*.tmp")), [])
        hb = json.loads((self.q / "bridge.heartbeat").read_text(encoding="utf-8"))
        self.assertEqual((hb["version"], hb["role"], hb["host"], hb["busy"]), ("3.1.1", "daemon", "PPRO", False))

    def test_the_engine_and_the_real_bridge_agree(self):
        """cep_queue.submit against js/bridge.js: claim, result, cleanup."""
        def during(_p):
            deadline = time.time() + 10
            while not (self.q / "bridge.heartbeat").exists() and time.time() < deadline:
                time.sleep(0.05)
            self.r = cep_queue.submit(self.q, self.script, "ping", {"echo": "x"}, timeout=10,
                                      expect_version=ppro_bridge.BRIDGE_VERSION)
        self.run_bridge(ms=2500, during=during)
        self.assertTrue(self.r["ok"], self.r)
        self.assertEqual(self.r["response"]["result"]["echo"], "x")
        self.assertEqual(self.leftovers(), [])

    def test_the_panel_leaves_the_queue_to_a_live_daemon(self):
        self.job("c", "ping", 60)
        stop = threading.Event()

        def daemon_beats():
            while not stop.is_set():
                (self.q / "bridge.heartbeat").write_text(json.dumps({"at": time.time() * 1000, "role": "daemon",
                                                                     "busy": False, "version": "3.1.1"}), encoding="utf-8")
                time.sleep(0.1)
        t = threading.Thread(target=daemon_beats, daemon=True)
        t.start()
        try:
            out = self.run_bridge(role="panel", ms=1200)
        finally:
            stop.set()
            t.join(2)
        self.assertEqual(out["evals"], [])
        self.assertTrue((self.q / "c.job.json").exists())
        self.assertIn("background bridge", out["state"])

    def test_the_panel_works_the_queue_when_no_daemon_beats(self):
        self.job("d", "ping", 60)
        out = self.run_bridge(role="panel", ms=4500)
        self.assertEqual(out["evals"], ["ping"])
        self.assertIn("this panel works the queue", out["log"])
        self.assertEqual(json.loads((self.q / "bridge.heartbeat").read_text(encoding="utf-8"))["role"], "panel")


if __name__ == "__main__":
    unittest.main()
