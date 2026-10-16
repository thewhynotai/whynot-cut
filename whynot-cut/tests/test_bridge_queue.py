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
import contextlib
import contextvars
import datetime as dt
import io
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

from lib import cep_bundle, cep_queue, common, errors, ppro_bridge  # noqa: E402
from test_round4_intake import slate_gradient_left  # noqa: E402  (a function only: no test class is imported)

CEP = SK.parent / "adobe" / "cep-bridge"
FROZEN_311 = SK / "tests" / "fixtures" / "cep-bridge-3.1.1"


def _iso(t: float) -> str:
    return dt.datetime.fromtimestamp(t, dt.timezone.utc).isoformat(timespec="milliseconds")   # what the engine writes


# Every wait in this file polls a condition up to WAIT_S, then fails saying what it waited for. A passing run never
# comes near it: it only bounds a broken or starved run (a loaded machine stretches every step, never the outcome).
WAIT_S = 60.0


def wait_until(cond, what: str, timeout: float = WAIT_S, poll: float = 0.05, proc=None, detail=None) -> None:
    """Poll `cond()` until it holds; AssertionError after `timeout` s (or as soon as `proc` exited) naming `what`."""
    deadline = time.monotonic() + timeout
    while not cond():
        if proc is not None and proc.poll() is not None:
            raise AssertionError(f"{what}: the node child exited (code {proc.returncode}) before it happened"
                                 + (f"\n{detail()}" if detail else ""))
        if time.monotonic() > deadline:
            raise AssertionError(f"{what}: not within {timeout:g}s" + (f"\n{detail()}" if detail else ""))
        time.sleep(poll)


class FakeBridge:
    """Plays the bridge daemon on `queue`: heartbeat, claim by rename, an expired job answered {ok:false,
    error:"expired"} without running, `<id>.claimed`, a result written atomically. Family-aware (3.0 T6.3 Task 4):
    "bundle" beats {..., bundle, version, protocol 4, build, libs (default: this engine's)}; "legacy" beats the 3.1.1
    shape {at, busy, version 3.1.1, host, role, current}. `protocol` / `libs` / `version` override the beat.
    `delays[action]` = seconds the host 'works'; `until[action]` = a condition the host works until (WAIT_S at most):
    a test states what must have happened meanwhile instead of guessing a duration; `mute` = never claims;
    `ran` = (job id, action, start, end); `first_seen[id]` = when a job file was first seen (also while the host works);
    `loops` = finished polling rounds."""

    def __init__(self, queue: Path, host="PPRO", version=None, mute=False, delays=None, beat=True, family="bundle",
                 protocol=..., libs=..., until=None):
        self.q, self.host, self.mute, self.delays, self.do_beat = Path(queue), host, mute, dict(delays or {}), beat
        self.until = dict(until or {})
        self.family = family
        legacy = family == "legacy"
        self.version = version or (cep_bundle.LEGACY_VERSION if legacy else ppro_bridge.BRIDGE_VERSION)
        self.protocol = (None if legacy else cep_bundle.PROTOCOL) if protocol is ... else protocol
        self.libs = (None if legacy else cep_bundle.expected_libs()) if libs is ... else libs
        self.busy, self.current = False, None
        self.ran, self.claimed, self.first_seen = [], [], {}
        self.loops = 0
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
        self.t.join(WAIT_S)

    def beat(self):
        tmp = self.q / "bridge.heartbeat.fake.tmp"
        hb = {"at": time.time() * 1000, "busy": self.busy, "version": self.version, "host": self.host,
              "role": "daemon", "current": self.current}
        if self.protocol is not None:
            hb.update(protocol=self.protocol, bundle=self.version, hostVersion="26.5.2", build="f" * 16, libs=self.libs)
        tmp.write_text(json.dumps(hb), encoding="utf-8")
        try:
            tmp.replace(self.q / "bridge.heartbeat")
        except PermissionError:          # Windows: the reader has the file open this instant; next beat wins
            pass

    def see(self):
        jobs = sorted(self.q.glob("*.job.json"))
        for jf in jobs:
            self.first_seen.setdefault(jf.name[:-len(".job.json")], time.time())
        return jobs

    def loop(self):
        while not self.stop.is_set():
            if self.do_beat:
                self.beat()
            jobs = self.see()
            if jobs and not self.mute:
                self.run(jobs[0])
            self.loops += 1
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
        until = self.until.get(data["action"], lambda: True)
        bound = time.monotonic() + WAIT_S
        while (time.time() < end or not until()) and not self.stop.is_set() and time.monotonic() < bound:
            self.beat()
            self.see()
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
        self.script = self.home / "ppro-scripts" / "wnc_ppro_lib.jsx"
        self.script.parent.mkdir(parents=True)
        self.script.write_text("// x", encoding="utf-8")

    def tearDown(self):
        self._ctx.__exit__(None, None, None)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def leftovers(self):
        return sorted(f.name for f in self.q.iterdir() if not f.name.startswith("bridge.heartbeat"))   # + a fake's tmp


# ===================================================================================================== IM-4
class TestExpiryCancelCleanup(_Home):
    def test_the_job_carries_expires_at_and_resolved_paths(self):
        with FakeBridge(self.q) as fb:
            t0 = time.time()
            r = cep_queue.submit(self.q, self.script, "ping", {"echo": 1}, timeout=WAIT_S, claim_timeout=30)
            t1 = time.time()
        self.assertTrue(r["ok"], r)
        job = fb.claimed[0]
        exp = dt.datetime.fromisoformat(job["expires_at"]).timestamp()
        # the claim timeout from the moment of submitting (somewhere in [t0, t1]; the ISO text keeps milliseconds)
        self.assertTrue(t0 + 30 - 0.002 <= exp <= t1 + 30, (t0, t1, job["expires_at"]))
        self.assertRegex(job["expires_at"], r"T\d\d:\d\d:\d\d\.\d{3}\+00:00$")    # milliseconds, not whole seconds
        self.assertEqual(job["script"], str(self.script.resolve()))
        self.assertEqual(job["data_file"], str(Path(job["data_file"]).resolve()))

    def test_an_unclaimed_job_is_cancelled_on_timeout_and_never_runs(self):
        main, naps, real_sleep = threading.current_thread(), [], time.sleep

        def sleep(s):                               # the engine's poll naps (this thread only; the fake has its own)
            if threading.current_thread() is main:
                naps.append(s)
            real_sleep(s)
        with FakeBridge(self.q, mute=True) as fb:
            with mock.patch("time.sleep", sleep):
                r = cep_queue.submit(self.q, self.script, "build_project", timeout=1, poll_s=0.5)
            # it gave up at its 1 s claim timeout, not later: the naps before the last look at the clock add up to
            # less than the timeout plus one poll (counted, not timed: a slow machine only means fewer naps)
            self.assertLess(sum(naps), 1 + 0.5 + 0.25, naps)
            fb.mute = False                         # Premiere frees up later: the job must not run then
            seen = fb.loops
            wait_until(lambda: fb.loops >= seen + 5, "the fake bridge polling five more rounds after it freed up")
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
            wait_until((self.q / "old.result.json").exists, "the fake bridge answering the expired job")
        self.assertEqual(fb.ran, [])
        self.assertEqual(json.loads((self.q / "old.result.json").read_text(encoding="utf-8"))["error"], "expired")

    def test_the_engine_reports_an_expired_answer_as_a_timeout(self):
        def expired_job_queued():                   # Premiere frees up only once the queued job is past its expiry
            for jf in self.q.glob("*.job.json"):
                try:
                    exp = dt.datetime.fromisoformat(json.loads(jf.read_text(encoding="utf-8"))["expires_at"])
                except (OSError, ValueError, KeyError):
                    continue
                if time.time() > exp.timestamp():
                    return True
            return False

        def unmute():
            try:
                wait_until(expired_job_queued, "the queued job expiring")
            finally:
                fb.mute = False
        with FakeBridge(self.q, mute=True) as fb:
            with mock.patch.object(cep_queue, "_cancel", return_value=False):     # the claim races the cancel
                t = threading.Thread(target=unmute, daemon=True)
                t.start()
                r = cep_queue.submit(self.q, self.script, "ping", timeout=WAIT_S, claim_timeout=0.2)
                t.join(WAIT_S)
        self.assertFalse(r["ok"])
        self.assertTrue(r.get("expired") and r["error"].startswith("timeout"), r)
        self.assertEqual(fb.ran, [])

    def test_the_result_timeout_starts_at_the_claim(self):
        """Queue wait behind another job does not count against the caller's timeout (IM-5)."""
        def ping_waited_past_its_timeout():         # the host finishes "slow" only after "ping" queued > 1.2 s
            return any(jid != fb.current and time.time() - t > 1.2 for jid, t in fb.first_seen.items())
        with FakeBridge(self.q, until={"slow": ping_waited_past_its_timeout}) as fb:
            other = threading.Thread(target=contextvars.copy_context().run,
                                     args=(cep_queue.submit, self.q, self.script, "slow"), kwargs={"timeout": WAIT_S})
            other.start()
            wait_until(lambda: fb.current is not None, "the bridge claiming the slow job")     # ping queues behind it
            r = cep_queue.submit(self.q, self.script, "ping", {"echo": 2}, timeout=1.0, claim_timeout=WAIT_S)
            other.join(WAIT_S)
            self.assertFalse(other.is_alive(), "the slow job's submit never returned")
        self.assertTrue(r["ok"], r)
        self.assertGreater(r["elapsed_s"], 1.0)                       # it waited longer than its own timeout
        self.assertEqual([a for _, a, *_ in fb.ran], ["slow", "ping"])

    def test_ctrl_c_before_the_claim_cancels_and_says_so(self):
        """The exception carries `wnc_claimed`: False = the job was taken back and never runs (ppro_build relies on it)."""
        self.q.mkdir(parents=True)
        with mock.patch.object(cep_queue, "_wait", side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt) as cm:
                cep_queue.submit(self.q, self.script, "build_project", timeout=5, st={"alive": True})
        self.assertIs(cm.exception.wnc_claimed, False)
        self.assertEqual(self.leftovers(), [])
        with mock.patch.object(cep_queue, "_wait", side_effect=KeyboardInterrupt), \
                mock.patch.object(cep_queue, "_cancel", return_value=False):          # the bridge had claimed it
            with self.assertRaises(KeyboardInterrupt) as cm:
                cep_queue.submit(self.q, self.script, "build_project", timeout=5, st={"alive": True})
        self.assertIs(cm.exception.wnc_claimed, True)

    def _interrupt_submit(self, patches):
        self.q.mkdir(parents=True, exist_ok=True)
        with contextlib.ExitStack() as st:
            for p in patches:
                st.enter_context(p)
            with self.assertRaises(KeyboardInterrupt) as cm:
                cep_queue.submit(self.q, self.script, "build_project", timeout=5, st={"alive": True})
        return cm.exception

    def test_ctrl_c_right_after_the_job_file_appears_cancels_it(self):
        """The job file is visible one statement before `_wait`: a Ctrl-C there must still take it back (Minor 2)."""
        real = Path.rename

        def rename(path, target):
            real(path, target)
            if path.suffix == ".tmp":
                raise KeyboardInterrupt           # the job is published, nobody waits for it yet
        e = self._interrupt_submit([mock.patch.object(Path, "rename", rename)])
        self.assertIs(e.wnc_claimed, False)
        self.assertEqual(self.leftovers(), [])                            # cancelled: it never runs

    def test_ctrl_c_before_the_job_file_appears_leaves_nothing_and_is_not_claimed(self):
        real = Path.rename

        def rename(path, target):
            if path.suffix == ".tmp":
                raise KeyboardInterrupt
            return real(path, target)
        e = self._interrupt_submit([mock.patch.object(Path, "rename", rename)])
        self.assertIs(e.wnc_claimed, False)
        self.assertEqual(self.leftovers(), [])

    def test_a_write_error_before_the_job_exists_is_not_claimed(self):
        self.q.mkdir(parents=True, exist_ok=True)
        with mock.patch.object(Path, "write_text", side_effect=OSError("disk full")):
            with self.assertRaises(OSError) as cm:
                cep_queue.submit(self.q, self.script, "build_project", timeout=5, st={"alive": True})
        self.assertIs(cm.exception.wnc_claimed, False)

    def test_the_cancel_retries_a_locked_job_file(self):
        """T2.15: Windows answers a rename of a file the antivirus or the panel has open with a sharing violation for a
        moment; the cancel tries again (5 x 0.1 s) before it gives up and reports the job as claimed."""
        self.q.mkdir(parents=True, exist_ok=True)
        job = self.q / "J1.job.json"
        job.write_text("{}", encoding="utf-8")
        real, tries = Path.rename, []

        def rename(path, target):
            tries.append(path.name)
            if len(tries) < 3:
                raise PermissionError(32, "being used by another process")
            return real(path, target)
        with mock.patch.object(Path, "rename", rename), mock.patch.object(cep_queue.time, "sleep") as sleep:
            self.assertTrue(cep_queue._cancel(self.q, "J1"))
        self.assertEqual(len(tries), 3)
        self.assertEqual(sleep.call_count, 2)
        self.assertFalse(job.exists())
        with mock.patch.object(cep_queue.time, "sleep") as sleep:
            self.assertFalse(cep_queue._cancel(self.q, "J1"))               # claimed / gone: no retry
        sleep.assert_not_called()
        job.write_text("{}", encoding="utf-8")
        with mock.patch.object(Path, "rename", side_effect=PermissionError(32, "locked")), \
                mock.patch.object(cep_queue.time, "sleep"):
            self.assertFalse(cep_queue._cancel(self.q, "J1"))               # still locked after 5 tries

    def test_a_job_with_a_result_is_done_not_claimed(self):
        """T2.15: result.json already written = the bridge finished; nothing more will happen to the project."""
        self.q.mkdir(parents=True, exist_ok=True)
        (self.q / "J2.result.json").write_text('{"ok": false}', encoding="utf-8")
        (self.q / "J2.claimed").write_text("", encoding="utf-8")
        self.assertIs(cep_queue._bridge_has_job(self.q, "J2"), False)
        (self.q / "J2.result.json").unlink()
        self.assertIs(cep_queue._bridge_has_job(self.q, "J2"), True)

    def test_a_second_ctrl_c_inside_the_cancel_counts_as_claimed(self):
        """The job may still run when the cancel itself is interrupted: the host must not put the old project back."""
        calls = []

        def cancel(queue, jid):
            calls.append(jid)
            raise KeyboardInterrupt               # the second Ctrl-C
        e = self._interrupt_submit([mock.patch.object(cep_queue, "_wait", side_effect=KeyboardInterrupt),
                                    mock.patch.object(cep_queue, "_cancel", cancel)])
        self.assertEqual(len(calls), 1)
        self.assertIs(e.wnc_claimed, True)
        e = self._interrupt_submit([mock.patch.object(cep_queue, "_wait", side_effect=KeyboardInterrupt),
                                    mock.patch.object(cep_queue, "_cancel", return_value=False),
                                    mock.patch.object(cep_queue, "_bridge_has_job", side_effect=KeyboardInterrupt)])
        self.assertIs(e.wnc_claimed, True)

    def test_data_result_and_claim_files_are_removed_after_reading(self):
        with FakeBridge(self.q):
            r = cep_queue.submit(self.q, self.script, "ping", {"echo": "عربي"}, timeout=WAIT_S)
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
            self.assertTrue(cep_queue.submit(self.q, self.script, "ping", timeout=WAIT_S)["ok"])
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
        with FakeBridge(self.q, family="legacy", version="3.1.0") as fb:
            r = ppro_bridge.submit("ping", timeout=5)
        self.assertFalse(r["ok"])
        self.assertIn("3.1.0", r["error"])
        self.assertIn(ppro_bridge.BRIDGE_VERSION, r["error"])
        self.assertIn(f"Restart Premiere to load WhyNot Cut {ppro_bridge.BRIDGE_VERSION}", r["how"])
        self.assertEqual(errors.exit_code(r), 2)
        self.assertEqual(fb.claimed, [])
        self.assertEqual(self.leftovers(), [])                     # nothing was queued

    def test_an_older_bridge_of_ours_is_refused_until_it_is_updated(self):
        """T6.3 Task 6: an unsigned bridge of ours before 3.1.1 is replaced by the install without --force; until then
        the queue refuses it (compatibility stays exactly 3.1.1, decision 15) and says to update it."""
        for have in ("3.1.0", "3.0.0", "2.2.1"):
            with self.subTest(have=have), FakeBridge(self.q, family="legacy", version=have) as fb:
                r = ppro_bridge.submit("ping", timeout=5)
                self.assertFalse(r["ok"])
                self.assertEqual(errors.exit_code(r), 2)
                self.assertEqual(fb.claimed, [])
                self.assertIn(f"is the older {have}: update it", r["error"])
                self.assertIn("Update the WhyNot Cut extension", r["how"])
                self.assertIn(f"`reel ppro-install` (it replaces {have})", r["how"])
                self.assertNotIn("--force", r["how"])
                self.assertNotIn("Bridge", r["error"] + r["how"])
        self.assertEqual(self.leftovers(), [])
        self.assertIsNone(cep_queue.version_refusal({"bridge_version": "3.1.1"}, "3.0.0", "Premiere"))
        later = cep_queue.version_refusal({"bridge_version": "3.1.2"}, "3.0.0", "Premiere")   # not ours to judge
        self.assertNotIn("update it", later["error"])

    def test_a_newer_running_bridge_asks_to_update_the_plugin(self):
        """`reel ppro-install` skips a newer installed bundle, so telling the editor to run it would loop (Minor 5)."""
        for st in ({"bridge_version": "3.2.0", "protocol": 4}, {"bridge_version": "3.0.0", "protocol": 5}):
            r = cep_queue.version_refusal(st, "3.0.0", "Premiere")
            self.assertIn("newer", r["how"])
            self.assertIn("update", r["how"].lower())
            self.assertIn("reel ppro-install --force", r["how"])
        # a legacy number above the bundle's (3.1.0 > 3.0.0) is still older: restart / reinstall, never --force
        old = cep_queue.version_refusal({"bridge_version": "3.1.0"}, "3.0.0", "Premiere")
        self.assertIn("`reel ppro-install`", old["how"])
        self.assertNotIn("--force", old["how"])
        self.assertTrue(old["blocked"] and old["ok"] is False)

    def test_the_two_families_are_accepted_and_everything_else_refused(self):
        libs = cep_bundle.expected_libs()
        ok = [{"bridge_version": "3.1.1"},                                             # legacy: no protocol
              {"bridge_version": "3.0.0", "protocol": 4, "libs": libs}]                # the bundle
        for st in ok:
            self.assertIsNone(cep_queue.version_refusal(st, "3.0.0", "Premiere"), st)
        bad = [{"bridge_version": "3.1.0"}, {"bridge_version": "3.0.0"},              # old legacy (3.0.0 = pre-bundle)
               {"bridge_version": "3.1.1", "protocol": 4, "libs": libs},              # 3.1.1 is never protocol 4
               {"bridge_version": "3.0.0", "protocol": 5, "libs": libs},              # protocol 5
               {"bridge_version": "3.0.0", "protocol": 3, "libs": libs},
               {"bridge_version": "3.0.1", "protocol": 4, "libs": libs}, {"bridge_version": None}]
        for st in bad:
            r = cep_queue.version_refusal(st, "3.0.0", "Premiere")
            self.assertTrue(r and r["blocked"] and r["ok"] is False, st)
            self.assertEqual(errors.exit_code(r), 2)
            self.assertNotIn("Window > Extensions", r["error"] + r["how"])
            self.assertNotIn("Bridge", r["error"] + r["how"])
        self.assertIn("protocol 5", cep_queue.version_refusal(bad[3], "3.0.0", "Premiere")["error"])

    def test_the_heartbeat_fields_reach_the_status(self):
        with FakeBridge(self.q, mute=True):
            st = ppro_bridge.status()
        self.assertTrue(st["alive"], st)
        self.assertEqual((st["bridge_version"], st["protocol"], st["bundle"], st["build"], st["host_version"]),
                         ("3.0.0", 4, "3.0.0", "f" * 16, "26.5.2"))
        self.assertEqual(st["libs"], cep_bundle.expected_libs())
        with FakeBridge(self.q, family="legacy", mute=True):
            st = ppro_bridge.status()
        self.assertEqual((st["bridge_version"], st["protocol"], st["libs"]), ("3.1.1", None, None))

    def test_no_heartbeat_names_no_bridge_menu(self):
        st = cep_queue.status(self.q, app="Premiere")
        self.assertFalse(st["alive"])
        self.assertNotIn("Window > Extensions", st["detail"])
        self.assertNotIn("Bridge", st["detail"])

    def test_ppro_build_refuses_a_version_mismatch_with_a_failing_exit(self):
        from lib import errors, ppro_build
        p = _reel(self.tmp)
        with mock.patch("lib.ppro_bridge.status", return_value={"alive": True, "bridge_version": "3.1.0"}), \
                mock.patch("lib.ppro_bridge.submit") as sub:
            r = ppro_build.build(p)
        self.assertEqual(r["status"], "BRIDGE_VERSION_MISMATCH")
        self.assertIs(r["ok"], False)
        self.assertIn("3.1.0", r["blocked"])
        self.assertIn("Restart Premiere", r["how"])
        self.assertNotEqual(errors.exit_code(r), 0)
        sub.assert_not_called()

    def test_motion_build_refuses_a_version_mismatch_as_blocked(self):
        from lib import errors, motion_build
        p = _reel(self.tmp)
        with mock.patch("lib.plat.newest_app", return_value={"version": "26"}), \
                mock.patch("lib.motion_plan.fingerprint", return_value="fp"), \
                mock.patch("lib.ae_bridge.status", return_value={"alive": True, "bridge_version": "3.0.0"}), \
                mock.patch("lib.ae_bridge.submit") as sub:
            r = motion_build.build(p, lock_wait_s=0)
        self.assertEqual(r["status"], "REFUSED")
        self.assertIn("3.0.0", r["blocked"])
        self.assertIn("Restart After Effects", r["how"])
        self.assertEqual(errors.exit_code(r), 2)
        sub.assert_not_called()

    def test_the_matching_bridge_runs_the_job(self):
        with FakeBridge(self.q):
            r = ppro_bridge.submit("ping", timeout=WAIT_S)
        self.assertTrue(r["ok"], r)

    def test_after_effects_checks_the_same_bundle_version(self):
        from lib import ae_bridge
        with FakeBridge(ae_bridge.queue_dir(), host="AEFT", family="legacy", version="3.0.0") as fb:   # pre-bundle 3.0.0
            r = ae_bridge.submit("ping", timeout=5)
        self.assertFalse(r["ok"])
        self.assertIn("Restart After Effects", r["how"])
        self.assertEqual(fb.claimed, [])

    def test_the_bundle_version_is_300_everywhere(self):
        import re
        js = (CEP / "js/bridge.js").read_text(encoding="utf-8")
        self.assertEqual(ppro_bridge.BRIDGE_VERSION, "3.0.0")
        self.assertIn("var BUNDLE = '3.0.0', PROTOCOL = 4;", js)
        self.assertRegex((CEP / "CSXS/manifest.xml").read_text(encoding="utf-8"), re.escape('ExtensionBundleVersion="3.0.0"'))
        self.assertEqual((cep_bundle.PRODUCT, cep_bundle.PROTOCOL, cep_bundle.LEGACY_VERSION), ("3.0.0", 4, "3.1.1"))

    def test_submit_signatures_are_stable(self):
        """reel serve's FileQueueAdapter calls these: positional parameters never change (keyword-only may be added)."""
        import inspect
        from lib import ae_bridge
        self.assertEqual(list(inspect.signature(ppro_bridge.submit).parameters)[:4], ["action", "data", "timeout", "script"])
        self.assertEqual(list(inspect.signature(ae_bridge.submit).parameters)[:3], ["action", "data", "timeout"])


class TestJobModes(_Home):
    """3.0 T6.3 Task 4: ppro_bridge.submit / ae_bridge.submit send what the running bridge needs: bundle 3.0.0 with this
    engine's libraries -> `lib`; legacy 3.1.1 -> the synced library as `script`; a bundle of another build -> refused
    (WHYNOT_BRIDGE_DEV=1: the synced library as `script`); anything else -> refused. Nothing is queued on a refusal."""
    ANOTHER_BUILD = ("the WhyNot Cut extension in Premiere is from another build: restart Premiere; if it persists, "
                     "reinstall WhyNot Cut")

    def setUp(self):
        super().setUp()
        p = mock.patch.dict(os.environ, {"WHYNOT_BRIDGE_DEV": ""})
        p.start()
        self.addCleanup(p.stop)

    def test_the_bundle_with_this_engines_libraries_runs_its_own_lib(self):
        before = self.script.read_text(encoding="utf-8")
        with FakeBridge(self.q) as fb:
            r = ppro_bridge.submit("ping", {"echo": "x"}, timeout=WAIT_S)
        self.assertTrue(r["ok"], r)
        (job,) = fb.claimed
        self.assertEqual(job["lib"], "wnc_ppro_lib.jsx")
        self.assertNotIn("script", job)
        self.assertEqual(self.script.read_text(encoding="utf-8"), before)             # nothing synced for the bundle

    def test_the_legacy_311_gets_the_synced_library_by_path(self):
        with FakeBridge(self.q, family="legacy") as fb:
            r = ppro_bridge.submit("ping", timeout=WAIT_S)
        self.assertTrue(r["ok"], r)
        (job,) = fb.claimed
        self.assertNotIn("lib", job)
        self.assertEqual(job["script"], str(ppro_bridge.lib_path().resolve()))
        self.assertEqual(ppro_bridge.lib_path().read_bytes(), ppro_bridge.LIB_SRC.read_bytes())

    def test_another_build_is_refused_and_nothing_is_queued(self):
        other = dict(cep_bundle.expected_libs(), **{"wnc_ppro_lib.jsx": "0" * 64})
        for libs in (other, None, {}):
            with self.subTest(libs=libs), FakeBridge(self.q, libs=libs) as fb:
                r = ppro_bridge.submit("ping", timeout=5)
                self.assertEqual((r["ok"], r["blocked"], r["error"]), (False, self.ANOTHER_BUILD, self.ANOTHER_BUILD))
                self.assertIn("Restart Premiere", r["how"])
                self.assertEqual(errors.exit_code(r), 2)
                self.assertEqual(fb.claimed, [])
                self.assertEqual(self.leftovers(), [])

    def test_the_dev_loop_sends_the_synced_library_for_another_build(self):
        with mock.patch.dict(os.environ, {"WHYNOT_BRIDGE_DEV": "1"}), FakeBridge(self.q, libs={}) as fb:
            r = ppro_bridge.submit("ping", timeout=WAIT_S)
        self.assertTrue(r["ok"], r)
        (job,) = fb.claimed
        self.assertEqual(job["script"], str(ppro_bridge.lib_path().resolve()))
        self.assertNotIn("lib", job)

    def test_protocol_5_and_old_legacy_versions_are_refused(self):
        for kw in ({"protocol": 5}, {"protocol": 3}, {"family": "legacy", "version": "3.1.0"},
                   {"family": "legacy", "version": "3.0.0"}, {"version": "3.0.1"}):
            with self.subTest(**kw), FakeBridge(self.q, **kw) as fb:
                r = ppro_bridge.submit("ping", timeout=5)
                self.assertFalse(r["ok"])
                self.assertEqual(errors.exit_code(r), 2)
                self.assertEqual(fb.claimed, [])
                if kw.get("protocol") == 5:
                    self.assertIn("protocol 5", r["error"])

    def test_after_effects_modes(self):
        from lib import ae_bridge
        q = ae_bridge.queue_dir()
        with FakeBridge(q, host="AEFT") as fb:
            r = ae_bridge.submit("ping", timeout=WAIT_S)
        self.assertTrue(r["ok"], r)
        self.assertEqual(fb.claimed[0]["lib"], "wnc_ae_bridge.jsx")
        self.assertFalse(ae_bridge.scripts_dir().exists())                             # nothing synced
        with FakeBridge(q, host="AEFT", family="legacy") as fb:
            r = ae_bridge.submit("ping", timeout=WAIT_S)
        self.assertTrue(r["ok"], r)
        self.assertEqual(fb.claimed[0]["script"], str(ae_bridge.entry_path().resolve()))
        self.assertEqual(sorted(p.name for p in ae_bridge.scripts_dir().iterdir()), sorted(ae_bridge.LIBS))
        with FakeBridge(q, host="AEFT", libs={}) as fb:
            r = ae_bridge.submit("ping", timeout=5)
        self.assertEqual(r["blocked"], self.ANOTHER_BUILD.replace("Premiere", "After Effects"))
        self.assertEqual(fb.claimed, [])

    def test_job_mode(self):
        libs = cep_bundle.expected_libs()
        self.assertEqual(cep_queue.job_mode({"bridge_version": "3.1.1"}, "3.0.0", "Premiere"), "script")
        self.assertEqual(cep_queue.job_mode({"bridge_version": "3.0.0", "protocol": 4, "libs": libs}, "3.0.0",
                                            "Premiere"), "lib")
        st = {"bridge_version": "3.0.0", "protocol": 4, "libs": dict(libs, extra="x")}       # extra names are fine
        self.assertEqual(cep_queue.job_mode(st, "3.0.0", "Premiere"), "lib")
        st = {"bridge_version": "3.0.0", "protocol": 4, "libs": {}}
        self.assertEqual(cep_queue.job_mode(st, "3.0.0", "Premiere")["blocked"], self.ANOTHER_BUILD)
        with mock.patch.dict(os.environ, {"WHYNOT_BRIDGE_DEV": "1"}):
            self.assertEqual(cep_queue.job_mode(st, "3.0.0", "Premiere"), "script")
        self.assertTrue(cep_queue.job_mode({"bridge_version": "3.0.0", "protocol": 5, "libs": libs}, "3.0.0",
                                           "Premiere")["blocked"])

    def test_the_build_gates_refuse_another_build_before_anything(self):
        """ppro_build / motion_build read version_refusal: a bundle of another build stops there (exit 2)."""
        from lib import motion_build, ppro_build
        p = _reel(self.tmp)
        st = {"alive": True, "bridge_version": "3.0.0", "protocol": 4, "libs": {}}
        with mock.patch("lib.ppro_bridge.status", return_value=st), mock.patch("lib.ppro_bridge.submit") as sub:
            r = ppro_build.build(p)
        self.assertEqual(r["blocked"], self.ANOTHER_BUILD)
        self.assertNotEqual(errors.exit_code(r), 0)
        sub.assert_not_called()
        with mock.patch("lib.plat.newest_app", return_value={"version": "26"}), \
                mock.patch("lib.motion_plan.fingerprint", return_value="fp"), \
                mock.patch("lib.ae_bridge.status", return_value=st), mock.patch("lib.ae_bridge.submit") as sub:
            r = motion_build.build(p, lock_wait_s=0)
        self.assertIn("from another build", r["blocked"])
        self.assertEqual(errors.exit_code(r), 2)
        sub.assert_not_called()

    def test_submit_needs_exactly_one_of_script_and_lib(self):
        st = {"alive": True}
        with self.assertRaises(ValueError):
            cep_queue.submit(self.q, None, "ping", st=st)
        with self.assertRaises(ValueError):
            cep_queue.submit(self.q, self.script, "ping", st=st, lib="wnc_ppro_lib.jsx")


class TestBuildLock(_Home):
    def test_two_concurrent_builds_run_one_after_the_other(self):
        """Two sessions build at once: the second job is queued only after the first finished, and its own 900 s clock
        never runs while it waits."""
        out = {}

        def build(name):
            with ppro_bridge.build_lock(f"ppro-build {name}", wait_s=WAIT_S, poll_s=0.05):
                out[name] = ppro_bridge.submit("build_project", {"echo": name}, timeout=WAIT_S)

        with FakeBridge(self.q, delays={"build_project": 0.8}) as fb:     # (B reads the lock while A releases it:
            # the release copes with that, test_the_release_retries_while_a_reader_has_the_lock_open)
            # each session's thread runs in a copy of this test's context (the bound engine home)
            ts = [threading.Thread(target=contextvars.copy_context().run, args=(build, n)) for n in ("A", "B")]
            for t in ts:
                t.start()
            for t in ts:
                t.join(2 * WAIT_S)
            self.assertFalse(any(t.is_alive() for t in ts), "a build thread never finished")
        self.assertTrue(out["A"]["ok"] and out["B"]["ok"], out)
        (j1, _, s1, e1), (j2, _, s2, e2) = fb.ran
        self.assertGreaterEqual(fb.first_seen[j2], e1 - 0.05)       # queued only after the first build ended
        self.assertFalse((self.q / cep_queue.LOCK_NAME).exists())

    # The release meets a reader (a waiter inside read_lock): Windows refuses to delete an open file (PermissionError
    # 13, measured). A lock left by this live process is never stale, so the next build here must not wait it out.
    def lock_files(self):
        return sorted(p.name for p in self.q.iterdir() if p.name.startswith(cep_queue.LOCK_NAME))

    def assert_next_build_goes_ahead(self):
        with ppro_bridge.build_lock("ppro-build next", wait_s=0) as rec:      # wait_s=0: busy would raise at once
            self.assertEqual(cep_queue.read_lock(self.q), rec)
        self.assertNotIn(cep_queue.LOCK_NAME, self.lock_files())

    def open_reader(self):
        f = open(self.q / cep_queue.LOCK_NAME, encoding="utf-8")          # what read_lock holds for a moment
        self.addCleanup(f.close)
        return f

    @unittest.skipUnless(os.name == "nt", "Windows refuses to delete an open file; POSIX deletes it")
    def test_the_release_retries_while_a_reader_has_the_lock_open(self):
        readers = []
        with mock.patch.object(cep_queue.time, "sleep", side_effect=lambda s: readers[0].close()) as nap, \
                contextlib.redirect_stderr(io.StringIO()):
            with ppro_bridge.build_lock("ppro-build A"):
                readers.append(self.open_reader())                         # the reader finishes during the backoff
        self.assertEqual(nap.call_count, 1)
        self.assertEqual(self.lock_files(), [])
        self.assert_next_build_goes_ahead()

    @unittest.skipUnless(os.name == "nt", "Windows refuses to delete or move an open file")
    def test_a_reader_holding_the_lock_through_every_retry_leaves_it_marked_released(self):
        err = io.StringIO()
        with mock.patch.object(cep_queue.time, "sleep") as nap, contextlib.redirect_stderr(err):
            with ppro_bridge.build_lock("ppro-build A") as rec:
                reader = self.open_reader()
        self.assertEqual(nap.call_count, cep_queue.CANCEL_TRIES - 1)
        self.assertEqual(json.loads((self.q / cep_queue.RELEASED_NAME).read_text(encoding="utf-8")), rec)
        self.assertIn("marked free", err.getvalue())
        reader.close()
        self.assert_next_build_goes_ahead()
        self.assertEqual(self.lock_files(), [])                            # the marker went with the takeover

    def failing(self, *names):
        """Path.unlink / Path.rename raising PermissionError(13) for the lock and its tombstones."""
        def ours(p):
            return p.name == cep_queue.LOCK_NAME or p.name.startswith(cep_queue.LOCK_NAME + ".released-")
        real = {n: getattr(Path, n) for n in names}

        def make(n):
            def f(p, *a, **k):
                if ours(p):
                    raise PermissionError(13, "The process cannot access the file because it is being used")
                return real[n](p, *a, **k)
            return f
        return [mock.patch.object(Path, n, make(n)) for n in names]

    def test_a_lock_that_cannot_be_deleted_is_moved_aside(self):
        err = io.StringIO()
        with contextlib.ExitStack() as st:
            for p in self.failing("unlink"):
                st.enter_context(p)
            nap = st.enter_context(mock.patch.object(cep_queue.time, "sleep"))
            st.enter_context(contextlib.redirect_stderr(err))
            with ppro_bridge.build_lock("ppro-build A"):
                pass
        self.assertEqual(nap.call_count, cep_queue.CANCEL_TRIES - 1)      # retried first, with the backoff
        (tomb,) = self.lock_files()
        self.assertRegex(tomb, rf"^\.build\.lock\.released-{os.getpid()}-\d+$")
        self.assertIn(tomb, err.getvalue())
        self.assert_next_build_goes_ahead()

    def test_a_lock_that_can_be_neither_deleted_nor_moved_is_marked_released(self):
        err = io.StringIO()
        with contextlib.ExitStack() as st:
            for p in self.failing("unlink", "rename"):
                st.enter_context(p)
            st.enter_context(mock.patch.object(cep_queue.time, "sleep"))
            st.enter_context(contextlib.redirect_stderr(err))
            with ppro_bridge.build_lock("ppro-build A") as rec:
                pass
        self.assertEqual(self.lock_files(), [cep_queue.LOCK_NAME, cep_queue.RELEASED_NAME])
        self.assertEqual(cep_queue.read_lock(self.q), rec)               # still on disk, held by this live process
        self.assertIn("marked free", err.getvalue())
        marker = (self.q / cep_queue.RELEASED_NAME).read_text(encoding="utf-8")
        self.assert_next_build_goes_ahead()
        self.assertEqual(self.lock_files(), [])
        # the marker frees only the lock it names: a live holder's newer lock is still waited for
        (self.q / cep_queue.RELEASED_NAME).write_text(marker, encoding="utf-8")
        with ppro_bridge.build_lock("ppro-build live"):
            with self.assertRaises(cep_queue.BuildLockBusy):
                with ppro_bridge.build_lock("ppro-build B", wait_s=0):
                    pass

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

    def test_a_live_holder_on_this_computer_is_never_stale_even_past_its_expiry(self):
        """The holder does not renew its lock: a build that runs past `hold_s` must not be taken over (Minor 3)."""
        import socket
        from lib.writer_lock import process_created
        rec = {"pid": os.getpid(), "pid_created": process_created(os.getpid()), "host": socket.gethostname(),
               "what": "long build", "expires_at": time.time() - 60}
        self.assertFalse(cep_queue.lock_stale(self.q, rec))
        self.assertTrue(cep_queue.lock_stale(self.q, dict(rec, host="another-pc")))        # elsewhere: expiry rules

    def test_a_hung_holder_on_this_computer_gets_stop_or_delete_guidance(self):
        """A same-host holder past its expiry is never taken over (a long build must not be): the refusal tells the
        user which process to stop and which file to delete (Minor 3)."""
        import socket
        from lib.writer_lock import process_created
        started = (dt.datetime.now().astimezone() - dt.timedelta(hours=3)).isoformat(timespec="seconds")
        h = {"pid": 4242, "pid_created": process_created(os.getpid()), "host": socket.gethostname(),
             "what": "ppro-build V1", "started_at": started, "expires_at": time.time() - 60}
        r = cep_queue.lock_busy_result(cep_queue.BuildLockBusy(h, 1200, self.q), "Premiere")
        self.assertIn("4242", r["how"])
        self.assertIn("180 min", r["how"])
        self.assertIn("stop", r["how"])
        self.assertIn(str(self.q / cep_queue.LOCK_NAME), r["how"])
        self.assertIn("Let it finish", r["how"])
        # creation time unknown (a reused pid cannot be ruled out), not yet expired: same guidance
        r = cep_queue.lock_busy_result(cep_queue.BuildLockBusy(dict(h, pid_created=None, expires_at=time.time() + 600),
                                                               1200, self.q), "Premiere")
        self.assertIn(str(self.q / cep_queue.LOCK_NAME), r["how"])
        # a healthy holder, or one on another computer: just wait
        for ok in (dict(h, expires_at=time.time() + 600), dict(h, host="another-pc")):
            r = cep_queue.lock_busy_result(cep_queue.BuildLockBusy(ok, 1200, self.q), "Premiere")
            self.assertNotIn(cep_queue.LOCK_NAME, r["how"])

    def test_a_real_expired_live_lock_refuses_with_the_guidance(self):
        with ppro_bridge.build_lock("ppro-build hung", hold_s=-5):
            with self.assertRaises(cep_queue.BuildLockBusy) as cm:
                with ppro_bridge.build_lock("ppro-build B", wait_s=0.2, poll_s=0.05):
                    pass
        r = cep_queue.lock_busy_result(cm.exception, "Premiere")
        self.assertIn(f"process {os.getpid()}", r["how"])
        self.assertIn(cep_queue.LOCK_NAME, r["how"])

    def test_an_unreadable_lock_replaced_by_a_live_one_is_put_back(self):
        """Waiter A read the lock while it was unreadable; before A renamed it, waiter B took over and wrote a fresh
        record. A must put B's lock back, not delete it (Minor 2)."""
        import socket
        from lib.writer_lock import process_created
        self.q.mkdir(parents=True, exist_ok=True)
        lock = self.q / cep_queue.LOCK_NAME
        live = {"pid": os.getpid(), "pid_created": process_created(os.getpid()), "host": socket.gethostname(),
                "what": "ppro-build B", "started_at": "now", "expires_at": time.time() + 999}
        lock.write_text(json.dumps(live), encoding="utf-8")
        os.utime(lock, (time.time() - 120,) * 2)        # A saw an old, unreadable file: stale by its age
        real, calls = cep_queue.read_lock, []

        def read_lock(q):
            calls.append(1)
            return {} if len(calls) == 1 else real(q)
        with mock.patch.object(cep_queue, "read_lock", side_effect=read_lock):
            with self.assertRaises(cep_queue.BuildLockBusy):
                with ppro_bridge.build_lock("ppro-build A", wait_s=0.2, poll_s=0.05):
                    pass
        self.assertEqual(json.loads(lock.read_text(encoding="utf-8")), live)

    def test_ppro_build_waits_for_the_lock_and_reports_busy(self):
        from lib import ppro_build
        p = _reel(self.tmp)
        with mock.patch("lib.ppro_bridge.status", return_value={"alive": True}), \
                mock.patch("lib.ppro_bridge.submit") as sub, ppro_bridge.build_lock("ppro-frames other"):
            r = ppro_build.build(p, lock_wait_s=0.1)
        self.assertEqual(r["status"], "BRIDGE_BUSY", r)
        self.assertIn("ppro-frames other", r["blocked"])
        sub.assert_not_called()

    def test_an_editor_save_during_the_lock_wait_is_caught(self):
        """EXISTS / EDITOR_CHANGES_PRESENT are decided once the lock is held: the editor may save while the build
        waits behind another one (Important 2)."""
        from lib import ppro_build
        p = _reel(self.tmp)
        prj = p.p(f"07_premiere/project/{p.video_id}_{common.project_prefix()}_EDIT.prproj")
        prj.parent.mkdir(parents=True, exist_ok=True)
        prj.write_text("BUILT", encoding="utf-8")
        edited, waiting, released = threading.Event(), threading.Event(), threading.Event()
        out = {}
        real_read_lock = cep_queue.read_lock

        def read_lock(q):
            rec = real_read_lock(q)
            if threading.current_thread() is t and not waiting.is_set():
                waiting.set()                         # the build thread read the held lock: it waits on it now
                released.wait(WAIT_S)                 # (and stays off the file until the holder has let go)
            return rec
        t = threading.Thread(target=contextvars.copy_context().run,
                             args=(lambda: out.update(r=ppro_build.build(p, overwrite=True, lock_wait_s=WAIT_S)),))
        with mock.patch("lib.ppro_bridge.status", return_value={"alive": True}), \
                mock.patch("lib.ppro_bridge.submit") as sub, \
                mock.patch.object(cep_queue, "read_lock", side_effect=read_lock), \
                mock.patch("lib.verify.editor_modified",
                           side_effect=lambda _p: {"project": str(prj)} if edited.is_set() else None):
            try:
                with ppro_bridge.build_lock("ppro-build other"):
                    t.start()
                    self.assertTrue(waiting.wait(WAIT_S), "the build never waited on the lock")
                    edited.set()                      # ... and the editor saves their work in Premiere meanwhile
            finally:
                released.set()
            t.join(WAIT_S)
            self.assertFalse(t.is_alive(), "the build never finished")
        self.assertEqual(out["r"]["status"], "EDITOR_CHANGES_PRESENT", out)
        from lib import errors
        self.assertEqual(errors.exit_code(out["r"]), 2)                    # a stop for a decision, never read as success
        sub.assert_not_called()
        self.assertEqual(prj.read_text(encoding="utf-8"), "BUILT")

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

    def run_build(self, answer, old=True, overwrite=True):
        from lib import ppro_build
        p = _reel(self.tmp)
        prj = p.p(f"07_premiere/project/{p.video_id}_{common.project_prefix()}_EDIT.prproj")
        prj.parent.mkdir(parents=True, exist_ok=True)
        if old:
            prj.write_text("OLD", encoding="utf-8")

        def submit(action, data=None, timeout=0, **kw):
            if action == "close_project_path":
                return {"ok": True, "response": {"ok": True, "result": {"closed": True}}}
            return answer(prj)

        with mock.patch("lib.ppro_bridge.status", return_value={"alive": True}), \
                mock.patch("lib.ppro_bridge.submit", side_effect=submit), \
                mock.patch.object(ppro_build, "job_data", return_value=dict(self.DATA)), \
                mock.patch("lib.verify.editor_modified", return_value=None):
            r = ppro_build.build(p, overwrite=overwrite)
        return r, prj

    def project_dir(self) -> Path:
        return next(self.tmp.glob("C/**/07_premiere/project"))

    def test_ctrl_c_or_an_error_while_queueing_puts_the_previous_project_back(self):
        for exc in (KeyboardInterrupt(), OSError("disk full")):
            with self.subTest(exc=type(exc).__name__):
                def boom(prj, exc=exc):
                    exc.wnc_claimed = False           # cep_queue's verdict: nothing was queued, or it was taken back
                    raise exc
                with self.assertRaises(type(exc)):
                    self.run_build(boom)
                d = self.project_dir()
                self.assertEqual((d / f"V1_{common.project_prefix()}_EDIT.prproj").read_text(encoding="utf-8"), "OLD")
                self.assertEqual(list(d.glob("*_prev_*")), [])
                shutil.rmtree(self.tmp / "C")

    def test_an_error_after_a_claimed_submit_never_downgrades_claimed(self):
        """The stat race in `saved_now` (or any later error in the try) must not make the finally restore over a
        project Premiere is still writing (Minor 1)."""
        state = {"after": False, "n": 0}
        real_exists = Path.exists

        def exists(self, *a, **k):
            if state["after"] and not state["n"] and self.suffix == ".prproj" and "_prev_" not in self.name:
                state["n"] += 1
                raise OSError("stat race")           # the first look at the project after the submit
            return real_exists(self, *a, **k)

        def answer(prj):
            state["after"] = True
            return {"ok": False, "error": "timeout after 900s", "claimed": True}
        with mock.patch.object(Path, "exists", exists), self.assertRaises(OSError):
            self.run_build(answer)
        d = self.project_dir()
        self.assertEqual(len(list(d.glob("*_prev_*"))), 1)
        self.assertEqual([f.name for f in d.glob("*.prproj") if "_prev_" not in f.name], [])

    def test_an_exception_without_a_verdict_while_submitting_keeps_the_backup_aside(self):
        """T2.15: a second Ctrl-C inside cep_queue's own cleanup reaches ppro_build without `wnc_claimed`; the job may
        be queued, so the old project is parked, never restored over a project Premiere may still save."""
        def boom(prj):
            raise KeyboardInterrupt()
        with self.assertRaises(KeyboardInterrupt):
            self.run_build(boom)
        d = self.project_dir()
        self.assertEqual(len(list(d.glob("*_prev_*"))), 1)
        self.assertEqual([f.name for f in d.glob("*.prproj") if "_prev_" not in f.name], [])

    def test_a_failure_before_anything_is_queued_says_not_claimed(self):
        """T2.15: ppro_bridge.submit (status, script sync) and cep_queue.submit (queue folder, sweep) flag their own
        early failures `wnc_claimed = False`, so the previous project still goes back."""
        with mock.patch.object(ppro_bridge, "status", return_value={"alive": True, "bridge_version": "3.1.1"}), \
                mock.patch.object(ppro_bridge, "sync_scripts", side_effect=OSError("disk full")):   # legacy: syncs
            with self.assertRaises(OSError) as cm:
                ppro_bridge.submit("build_project", {})
        self.assertIs(cm.exception.wnc_claimed, False)
        with mock.patch.object(cep_queue, "sweep", side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt) as cm:
                cep_queue.submit(self.tmp / "q", self.tmp / "s.jsx", "build_project", st={"alive": True})
        self.assertIs(cm.exception.wnc_claimed, False)

    def test_ctrl_c_after_the_claim_keeps_the_backup_aside(self):
        def boom(prj):
            e = KeyboardInterrupt()
            e.wnc_claimed = True                      # Premiere took the job: it may still save the new project
            raise e
        with self.assertRaises(KeyboardInterrupt):
            self.run_build(boom)
        d = self.project_dir()
        self.assertEqual(len(list(d.glob("*_prev_*"))), 1)
        self.assertEqual([f.name for f in d.glob("*.prproj") if "_prev_" not in f.name], [])

    def test_a_lone_prev_is_reported_with_how_to_restore(self):
        """A hard kill between the rename and the restore leaves only `_prev_`: the next ppro-build says so."""
        from lib import errors, ppro_build
        p = _reel(self.tmp)
        d = p.p("07_premiere/project")
        d.mkdir(parents=True, exist_ok=True)
        prj = d / f"{p.video_id}_{common.project_prefix()}_EDIT.prproj"
        parked = d / f"{prj.stem}_prev_20261012-101010.prproj"
        parked.write_text("EDITOR'S", encoding="utf-8")
        with mock.patch("lib.ppro_bridge.status", return_value={"alive": True}), \
                mock.patch("lib.ppro_bridge.submit") as sub:
            r = ppro_build.build(p)
        self.assertEqual(r["status"], "PREVIOUS_PARKED", r)
        self.assertEqual(r["parked_previous"]["file"], str(parked))
        self.assertIn(parked.name, r["how"])
        self.assertIn(prj.name, r["how"])
        self.assertIn("--force", r["how"])
        self.assertIn("no project is at the expected path", r["how"])
        self.assertNotIn("stopped before", r["how"])                        # a deleted project looks the same: no blame
        self.assertEqual(errors.exit_code(r), 2)
        self.assertTrue(r["blocked"])
        sub.assert_not_called()
        self.assertEqual(ppro_build.parked_previous(p)["file"], str(parked))
        self.assertTrue(parked.exists())                                   # report only: nothing is moved

    def test_force_builds_anyway_and_still_names_the_parked_file(self):
        def built(prj):
            prj.write_text("NEW", encoding="utf-8")
            return {"ok": True, "response": {"ok": True, "result": {}}}
        p = _reel(self.tmp)
        d = p.p("07_premiere/project")
        d.mkdir(parents=True, exist_ok=True)
        (d / f"V1_{common.project_prefix()}_EDIT_prev_20261012-101010.prproj").write_text("EDITOR'S", encoding="utf-8")
        r, prj = self.run_build(built, old=False)
        self.assertEqual(prj.read_text(encoding="utf-8"), "NEW")
        self.assertIn("_prev_20261012-101010", r["parked_previous"]["file"])

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


# ===================================================================================================== G2 H5
class TestH5ErrorMarkerAndRestart(_Home):
    """bridge.js (H2): a result it cannot write leaves `<id>.error` (the job file removed, no result); a restarted
    bridge answers each leftover `<id>.running` {ok:false, error:"interrupted", reason:"bridge restarted"} (soon also
    `claimed: true`). The engine's wait ends at once on the marker, and both count as claimed: the host ran the job and
    may still be saving, so ppro_build keeps the previous project parked."""

    TIMEOUT = 30.0          # the wait's own timeout; every answer below must come far sooner

    def setUp(self):
        super().setUp()
        self.q.mkdir(parents=True, exist_ok=True)

    def claimed_job(self, jid, error=None, result=None):
        """A job the bridge claimed (its `.claimed`, the data file), then the files it leaves behind."""
        (self.q / f"{jid}.data.json").write_text("{}", encoding="ascii")
        (self.q / f"{jid}.claimed").write_text(json.dumps({"at": time.time() * 1000, "by": "daemon"}), encoding="utf-8")
        if error is not None:
            (self.q / f"{jid}.error").write_bytes(error)
        if result is not None:
            (self.q / f"{jid}.result.json").write_text(json.dumps(result), encoding="utf-8")

    def wait(self, jid):
        t = time.monotonic()
        r = cep_queue._wait(self.q, jid, time.time(), self.TIMEOUT, self.TIMEOUT, 0.01, "Premiere")
        return r, time.monotonic() - t

    def test_the_error_marker_alone_fails_at_once_and_counts_as_claimed(self):
        marker = json.dumps({"ok": False, "error": "result write failed", "at": 1}).encode()
        self.claimed_job("J1", error=marker)
        r, took = self.wait("J1")
        self.assertLess(took, 5.0, r)
        self.assertIs(r["ok"], False)
        self.assertEqual(r["error"], "result write failed")
        self.assertIs(r["claimed"], True)
        self.assertEqual(r["job"], "J1")
        self.assertIn("check the project", r["how"].lower())
        self.assertEqual(self.leftovers(), [])                          # the marker goes with the other files

    def test_an_empty_or_garbage_marker_still_fails(self):
        for i, raw in enumerate([b"", b"{not json", b"\xff\xfe\x00", b"[1, 2]", b'"text"', b'{"ok": true}']):
            with self.subTest(raw=raw):
                jid = f"G{i}"
                self.claimed_job(jid, error=raw)
                r, took = self.wait(jid)
                self.assertLess(took, 5.0, r)
                self.assertIs(r["ok"], False)
                self.assertEqual(r["error"], "result write failed")
                self.assertIs(r["claimed"], True)
                self.assertTrue(r["how"])
                self.assertFalse((self.q / f"{jid}.error").exists())

    def test_a_marker_that_appears_during_the_wait_ends_it(self):
        self.claimed_job("J2")
        (self.q / "J2.running").write_text("{}", encoding="utf-8")

        def give_up():               # bridge.js giveUpResult: the marker first, then the job file goes
            time.sleep(0.3)
            (self.q / "J2.error").write_text(json.dumps({"ok": False, "error": "result write failed", "at": 1}),
                                             encoding="utf-8")
            (self.q / "J2.running").unlink()
        th = threading.Thread(target=give_up)
        th.start()
        r, took = self.wait("J2")
        th.join()
        self.assertLess(took, 5.0, r)
        self.assertIs(r["ok"], False)
        self.assertIs(r["claimed"], True)

    def test_a_real_result_wins_over_the_marker(self):
        ok = {"ok": True, "result": json.dumps({"ok": True, "result": {"saved": True}}), "at": 1}
        self.claimed_job("J3", error=b'{"ok": false, "error": "result write failed"}', result=ok)
        r, _ = self.wait("J3")
        self.assertIs(r["ok"], True, r)
        self.assertNotIn("claimed", r)
        self.assertEqual(r["response"], {"ok": True, "result": {"saved": True}})

    def test_an_interrupted_result_counts_as_claimed_with_or_without_the_flag(self):
        shapes = {"today": {"ok": False, "error": "interrupted", "reason": "bridge restarted", "at": 1},
                  "follow-up": {"ok": False, "error": "interrupted", "reason": "bridge restarted", "claimed": True,
                                "at": 1}}
        for name, doc in shapes.items():
            with self.subTest(shape=name):
                jid = f"I-{name}"
                self.claimed_job(jid, result=doc)
                r, took = self.wait(jid)
                self.assertLess(took, 5.0, r)
                self.assertIs(r["ok"], False)
                self.assertIs(r["claimed"], True, r)
                self.assertIn("restarted", r["how"])
                self.assertEqual(self.leftovers(), [])

    def test_any_result_flagged_claimed_counts_as_claimed(self):
        self.claimed_job("C1", result={"ok": False, "error": "something else", "claimed": True, "at": 1})
        self.assertIs(self.wait("C1")[0]["claimed"], True)

    def test_other_failures_are_still_not_claimed(self):
        for i, doc in enumerate([{"ok": False, "error": "interrupted", "at": 1},          # not the restart reason
                                 {"ok": False, "error": "script not whitelisted", "at": 1},
                                 {"ok": False, "error": "x", "claimed": "yes", "at": 1}]):   # only a real True
            with self.subTest(doc=doc):
                self.claimed_job(f"N{i}", result=doc)
                self.assertNotIn("claimed", self.wait(f"N{i}")[0])

    def test_a_ctrl_c_cleanup_sees_both_as_claimed(self):
        """submit's Ctrl-C path (`_bridge_has_job`) agrees: the host may still act on either job."""
        self.claimed_job("K1", result={"ok": False, "error": "interrupted", "reason": "bridge restarted", "at": 1})
        self.assertIs(cep_queue._bridge_has_job(self.q, "K1"), True)
        (self.q / "K2.error").write_text("", encoding="utf-8")         # only the marker is left
        self.assertIs(cep_queue._bridge_has_job(self.q, "K2"), True)

    def test_the_sweeper_takes_a_day_old_marker(self):
        old = time.time() - 2 * 86400
        for n in ("a.error", "fresh.error"):
            (self.q / n).write_text("{}", encoding="utf-8")
        os.utime(self.q / "a.error", (old, old))
        self.assertEqual(cep_queue.sweep(self.q), ["a.error"])
        self.assertTrue((self.q / "fresh.error").exists())


class TestH5PreviousProjectStaysParked(_Home):
    """ppro_build through the real `_wait`: an error marker or a bridge-restart result leaves the previous project as
    `_prev_` (Premiere may still save the new one at that path), never restored over it."""

    DATA = TestPreviousProjectKept.DATA
    run_build = TestPreviousProjectKept.run_build

    def through_wait(self, files: dict):
        def answer(prj):
            q = self.q
            q.mkdir(parents=True, exist_ok=True)
            (q / "B1.claimed").write_text("{}", encoding="utf-8")
            for name, body in files.items():
                (q / name).write_text(body, encoding="utf-8")
            return cep_queue._wait(q, "B1", time.time(), 30, 30, 0.01, "Premiere")
        return answer

    def assert_parked(self, r, prj):
        self.assertEqual(r["status"], "FAILED", r)
        self.assertFalse(prj.exists())
        prev = list(prj.parent.glob("*_prev_*"))
        self.assertEqual([x.read_text(encoding="utf-8") for x in prev], ["OLD"])
        self.assertFalse(r["previous_restored"])
        self.assertEqual(r["previous_version_backup"], str(prev[0]))
        self.assertTrue(r.get("how"), r)

    def test_an_error_marker_keeps_the_backup_parked(self):
        self.assert_parked(*self.run_build(self.through_wait(
            {"B1.error": json.dumps({"ok": False, "error": "result write failed", "at": 1})})))

    def test_a_bridge_restart_keeps_the_backup_parked(self):
        for doc in ({"ok": False, "error": "interrupted", "reason": "bridge restarted", "at": 1},
                    {"ok": False, "error": "interrupted", "reason": "bridge restarted", "claimed": True, "at": 1}):
            with self.subTest(doc=doc):
                self.assert_parked(*self.run_build(self.through_wait({"B1.result.json": json.dumps(doc)})))
                shutil.rmtree(self.tmp / "C")


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
# The bridge runs on its own clock (its setIntervals, 50 ms each here; its setTimeouts 1/20 of their delay), and the
# run ends on that clock, never on wall
# time: a loaded machine stretches every tick, so a fixed lifetime ended the bridge before it had done its work (jobs
# left unanswered, a claimed job never finished, an engine submit finding the bridge already gone). The test closes
# this process's stdin to ask for the end (once the outcome it waits for is on disk, or at once); the harness then
# lets the bridge tick until it has ticked `minTicks` times in all and SETTLE times since the request with no
# evalScript in flight (a result written, then a heartbeat after it), writes what it saw and exits. A bridge that
# starts no clock (the bundle's panel) has nothing left to do: it ends at the request. A test process that dies
# closes the pipe too, so the child never outlives it. fs.watch is the real one (H6: bundle 3.0.0 watches its queue).
# An evalScript that is not a job (H6: the After Effects render-queue probe, the Premiere encoder-event bind) is
# answered at once ("idle" / "unavailable") and recorded in hostEvals, never in evals.
HARNESS = r"""
const vm = require('vm'), fs = require('fs');
const [bridgeJs, extDir, role, minTicks, outFile, host] = process.argv.slice(2);
const SETTLE = 2;
const evals = [], hostEvals = [], state = { textContent: '' }, logEl = { textContent: '' };
let clocks = 0, ticks = 0, inFlight = 0, stopAsked = false, settled = 0, ended = false;
function end() {
  if (ended) { return; }
  ended = true;
  const b = ctx.window.WNC_BRIDGE;
  fs.writeFileSync(outFile, JSON.stringify({ evals, hostEvals, ticks, state: state.textContent, log: logEl.textContent,
    panel: b ? { role: b.role, host: b.host, bundle: b.bundle, queue: b.queue, beat: b.readBeat() } : null }));
  process.exit(0);
}
function maybeEnd() {
  if (stopAsked && (clocks === 0 || (inFlight === 0 && ticks >= +minTicks && settled >= SETTLE))) { end(); }
}
const cep = {
  getExtensionId: () => 'ai.thewhynot.cut.bridge.' + role,
  getHostEnvironment: () => JSON.stringify({ appName: host, appVersion: '26.5.2' }),
  getSystemPath: () => 'file:///' + extDir.replace(/\\/g, '/'),
  evalScript: (code, cb) => {
    const m = /^\$\.evalFile\(new File\(("(?:[^"\\]|\\.)*")\)\); (\w+)\.run\(("(?:[^"\\]|\\.)*")\);$/.exec(code);
    if (!m) { hostEvals.push(code); return cb(/renderQueue/.test(code) ? 'idle' : 'unavailable'); }
    const data = JSON.parse(fs.readFileSync(JSON.parse(m[3]), 'ascii'));
    evals.push({ action: data.action, file: JSON.parse(m[1]), entry: m[2] });
    inFlight += 1;
    setTimeout(() => {
      inFlight -= 1; settled = 0;
      cb(JSON.stringify({ ok: true, action: data.action, result: { echo: data.echo } }));
    }, 30);
  }
};
const ctx = { window: { __adobe_cep__: cep, cep_node: { require } }, document: { getElementById: (id) => id === 'state' ? state : logEl },
              setInterval: (f) => { clocks += 1; return setInterval(() => {
                f(); ticks += 1;
                if (stopAsked && inFlight === 0) { settled += 1; }
                maybeEnd();
              }, 50); },
              clearInterval, setTimeout: (f, ms) => setTimeout(f, Math.ceil((+ms || 0) / 20)), clearTimeout,
              process, console };
vm.runInNewContext(fs.readFileSync(bridgeJs, 'utf8'), ctx);
const stop = () => { stopAsked = true; maybeEnd(); };
process.stdin.on('end', stop);
process.stdin.on('error', stop);
process.stdin.resume();
"""


class _BridgeJs(_Home):
    """Runs a real bridge.js in node with a stubbed CEP. HOME and USERPROFILE of the node process are a temp folder,
    so the bridge never reads or writes the real ~/.whynot-cut. Subclasses name the file and build the extension."""
    BRIDGE: Path
    FAMILY: str
    REFUSED: str                            # the bridge's answer to a script outside the allowed folder

    def setUp(self):
        super().setUp()
        self.user = self.tmp / "user"
        self.user.mkdir()
        self.ext = self.make_ext()
        self.harness = self.tmp / "harness.js"
        self.harness.write_text(HARNESS, encoding="utf-8")
        self.q.mkdir(parents=True)

    def make_ext(self) -> Path:
        raise NotImplementedError

    def run_bridge(self, role="daemon", host="PPRO", *, until=None, what="", during=None, ticks=3):
        """Run the bridge in node until `until()` holds (the outcome the test needs is on disk) or `during(p)` returned,
        then ask it to end (stdin closed): it ends after `ticks` ticks in all and a settled tick or two (HARNESS).
        Every wait is bounded (WAIT_S); the child is always waited for, killed if it is still there, and its output
        goes to a file (no pipe to fill)."""
        out = self.tmp / f"out-{role}-{host}.json"
        with contextlib.suppress(FileNotFoundError):
            out.unlink()                                      # a test may run the bridge more than once
        log = self.tmp / f"node-{role}-{host}.log"
        env = dict(os.environ, HOME=str(self.user), USERPROFILE=str(self.user))
        with open(log, "wb") as logf:
            p = subprocess.Popen([NODE, str(self.harness), str(self.BRIDGE), str(self.ext), role, str(ticks), str(out),
                                  host], stdin=subprocess.PIPE, stdout=logf, stderr=subprocess.STDOUT, env=env)
            try:
                if during:
                    during(p)
                if until:
                    self.wait_for(until, what or "the bridge's outcome", p)
                p.stdin.close()
                try:
                    p.wait(timeout=WAIT_S)
                except subprocess.TimeoutExpired:
                    self.fail(f"the bridge did not end within {WAIT_S:g}s of the stop request\n{self.state(log)}")
            finally:
                if p.poll() is None:
                    p.kill()
                    p.wait(timeout=WAIT_S)
                p.stdin.close()
        self.assertEqual(p.returncode, 0, self.state(log))
        return json.loads(out.read_text(encoding="utf-8"))

    def state(self, log: Path | None = None) -> str:
        """What a failed wait reports: the queue folders and the node output."""
        qs = sorted({self.q, self.home / "ae-queue"})
        text = "; ".join(f"{q.name}: {sorted(f.name for f in q.iterdir()) if q.is_dir() else 'missing'}" for q in qs)
        if log is None:
            log = next(iter(sorted(self.tmp.glob("node-*.log"))), None)
        if log is not None and log.exists():
            text += "\nnode: " + log.read_text(encoding="utf-8", errors="replace")[-2000:]
        return text

    def wait_for(self, cond, what: str, p=None):
        wait_until(cond, what, proc=p, detail=self.state)

    def results(self, *jids, q=None):
        """until= for run_bridge: every one of these jobs has its result file."""
        return lambda: all(((q or self.q) / f"{j}.result.json").exists() for j in jids)

    def job(self, jid, action, expires_in, **ref):
        """A job file; `ref` = lib=... or script=... (default: what this family's engine sends)."""
        data = self.q / f"{jid}.data.json"
        data.write_text(json.dumps({"action": action, "echo": jid}), encoding="ascii")
        if not ref:
            ref = {"lib": "wnc_ppro_lib.jsx"} if self.FAMILY == "bundle" else {"script": str(self.script.resolve())}
        (self.q / f"{jid}.job.json").write_text(json.dumps(dict({
            "id": jid, "action": action, "data_file": str(data.resolve()),
            "expires_at": _iso(time.time() + expires_in)}, **ref)), encoding="utf-8")

    def result(self, jid):
        return json.loads((self.q / f"{jid}.result.json").read_text(encoding="utf-8"))

    def beat(self, q=None):
        return json.loads(((q or self.q) / "bridge.heartbeat").read_text(encoding="utf-8"))

    def wait_beat(self, q, p):
        self.wait_for((q / "bridge.heartbeat").exists, "the bridge's first heartbeat", p)


class _SharedBridgeJsTests:
    """The same suite against bundle 3.0.0 (adobe/cep-bridge/js/bridge.js) and the frozen legacy 3.1.1."""

    def test_the_daemon_runs_a_live_job_and_discards_an_expired_one(self):
        self.job("a-old", "build_project", -60)
        self.job("b-new", "ping", 60)
        out = self.run_bridge(until=self.results("a-old", "b-new"), what="both jobs answered")
        self.assertEqual([e["action"] for e in out["evals"]], ["ping"])       # the expired build never reached the host
        self.assertEqual(self.result("a-old")["error"], "expired")
        self.assertFalse(self.result("a-old")["ok"])
        self.assertTrue(self.result("b-new")["ok"])
        self.assertEqual(json.loads(self.result("b-new")["result"])["result"]["echo"], "b-new")
        self.assertEqual(json.loads((self.q / "b-new.claimed").read_text(encoding="utf-8"))["by"], "daemon")
        self.assertEqual(sorted(f.name for f in self.q.glob("*.running")) + sorted(f.name for f in self.q.glob("*.tmp")), [])
        hb = self.beat()
        self.assertEqual((hb["role"], hb["host"], hb["busy"]), ("daemon", "PPRO", False))

    def test_the_engine_and_the_real_bridge_agree(self):
        """ppro_bridge.submit against the real bridge.js: the mode this family needs, claim, result, cleanup."""
        def during(p):
            self.wait_beat(self.q, p)
            self.r = ppro_bridge.submit("ping", {"echo": "x"}, timeout=WAIT_S)
        out = self.run_bridge(during=during)
        self.assertTrue(self.r["ok"], self.r)
        self.assertEqual(self.r["response"]["result"]["echo"], "x")
        self.assertEqual(self.leftovers(), [])
        (ev,) = out["evals"]
        self.assertEqual((ev["action"], ev["entry"]), ("ping", self.ENTRY["PPRO"]))
        self.assertEqual(norm(ev["file"]), norm(self.ran_from("PPRO")))

    def test_after_effects_runs_its_entry(self):
        from lib import ae_bridge
        q = ae_bridge.queue_dir()

        def during(p):
            self.wait_beat(q, p)
            self.r = ae_bridge.submit("ping", {"echo": "ae"}, timeout=WAIT_S)
        out = self.run_bridge(during=during, host="AEFT")
        self.assertTrue(self.r["ok"], self.r)
        (ev,) = out["evals"]
        self.assertEqual((ev["action"], ev["entry"]), ("ping", self.ENTRY["AEFT"]))
        self.assertEqual(norm(ev["file"]), norm(self.ran_from("AEFT")))
        self.assertEqual(self.beat(q)["host"], "AEFT")

    def test_a_script_outside_the_scripts_folder_is_refused(self):
        evil = self.tmp / "evil" / "wnc_ppro_lib.jsx"
        evil.parent.mkdir()
        evil.write_text("// evil", encoding="utf-8")
        self.job("e", "ping", 60, script=str(evil.resolve()))
        out = self.run_bridge(until=self.results("e"), what="the job answered")
        self.assertEqual(out["evals"], [])
        r = self.result("e")
        self.assertFalse(r["ok"])
        self.assertEqual(r["error"], self.REFUSED)

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
            out = self.run_bridge(role="panel", ticks=24)     # every tick a chance to take the job
        finally:
            stop.set()
            t.join(2)
        self.assertEqual(out["evals"], [])
        self.assertTrue((self.q / "c.job.json").exists())

    def test_the_panel_waits_longer_than_the_engine_heartbeat_window(self):
        """The panel must not count the daemon gone while the engine still counts it alive (cep_queue.status)."""
        import inspect
        import re
        ms = int(re.search(r"var DAEMON_STALE_MS = (\d+);", self.BRIDGE.read_text(encoding="utf-8")).group(1))
        engine_s = inspect.signature(cep_queue.status).parameters["max_age_s"].default
        self.assertGreaterEqual(ms, 6000)
        self.assertGreater(ms, engine_s * 1000)


@unittest.skipUnless(NODE, "needs node to run js/bridge.js with a stubbed CEP")
class TestBridgeJs(_SharedBridgeJsTests, _BridgeJs):
    """Bundle 3.0.0: daemon-only worker, bundled libraries (`lib` jobs, confined), the protocol 4 heartbeat."""
    BRIDGE = CEP / "js" / "bridge.js"
    FAMILY = "bundle"
    REFUSED = "script not allowed"
    ENTRY = {"PPRO": "WNCPP", "AEFT": "WNCAE"}

    def make_ext(self) -> Path:
        ext = cep_bundle.assemble(self.tmp / "ext" / cep_bundle.EXT_ID)
        self.write_config(self.home)
        return ext

    def write_config(self, engine_home: Path):
        cfg = self.user / ".whynot-cut" / "bridge" / "config.json"
        cfg.parent.mkdir(parents=True, exist_ok=True)
        cfg.write_text(json.dumps({"schema": 1, "engine_home": str(engine_home), "launcher": None,
                                   "written_by": "engine", "at": "2026-10-13T00:00:00+00:00"}), encoding="utf-8")
        return cfg

    def ran_from(self, host):
        return self.ext / "jsx" / ("wnc_ppro_lib.jsx" if host == "PPRO" else "wnc_ae_bridge.jsx")

    def test_the_heartbeat_fields(self):
        self.run_bridge()
        hb = self.beat()
        self.assertEqual(sorted(hb), sorted(["at", "busy", "role", "host", "hostVersion", "bundle", "version", "protocol",
                                             "build", "libs", "current", "action", "engine_start", "engine_retry",
                                             "host_busy"]))
        self.assertIsNone(hb["engine_retry"])                                # H2: "slow" only after 5 failed engine starts
        self.assertEqual(hb["host_busy"], "unknown")                         # H6: no job yet, so no encoder bind
        self.assertEqual(hb["engine_start"]["outcome"], "no_launcher")       # config.json launcher null (Task 5)
        build = json.loads((self.ext / "build.json").read_text(encoding="utf-8"))
        self.assertEqual((hb["bundle"], hb["version"], hb["protocol"], hb["build"], hb["hostVersion"], hb["role"]),
                         ("3.0.0", "3.0.0", 4, build["build"], "26.5.2", "daemon"))
        self.assertEqual(hb["libs"], cep_bundle.expected_libs())
        self.assertEqual(hb["libs"], build["libs"])
        st = cep_queue.status(self.q, app="Premiere")
        self.assertEqual(cep_queue.job_mode(st, ppro_bridge.BRIDGE_VERSION, "Premiere"), "lib")

    def test_lib_jobs_run_from_the_bundle(self):
        self.job("l", "ping", 60, lib="wnc_ppro_lib.jsx")
        out = self.run_bridge(until=self.results("l"), what="the job answered")
        self.assertTrue(self.result("l")["ok"], self.result("l"))
        (ev,) = out["evals"]
        self.assertEqual(norm(ev["file"]), norm(self.ext / "jsx" / "wnc_ppro_lib.jsx"))
        self.assertEqual(ev["entry"], "WNCPP")

    def test_a_bad_lib_is_refused(self):
        bad = {"other-host": {"lib": "wnc_ae_bridge.jsx"}, "a-path": {"lib": "../js/bridge.js"},
               "host-script": {"lib": "wnc_host.jsx"}, "absolute": {"lib": str(self.ext / "jsx" / "wnc_ppro_lib.jsx")},
               "empty": {"lib": ""}, "number": {"lib": 5}, "nothing": {"data": 1}}
        for jid, ref in bad.items():
            self.job(jid, "ping", 60, **ref)
        out = self.run_bridge(until=self.results(*bad), what="every bad job answered")
        self.assertEqual(out["evals"], [])
        for jid in bad:
            r = self.result(jid)
            self.assertEqual((r["ok"], r["error"]), (False, "script not allowed"), jid)

    def test_a_lib_linked_out_of_the_bundle_is_refused(self):
        evil = self.tmp / "evil" / "wnc_ppro_lib.jsx"
        evil.parent.mkdir()
        evil.write_text("// evil", encoding="utf-8")
        lib = self.ext / "jsx" / "wnc_ppro_lib.jsx"
        lib.unlink()
        try:
            lib.symlink_to(evil)
        except OSError as e:                      # Windows without the symlink privilege
            self.skipTest(f"no symlinks here: {e}")
        self.job("s", "ping", 60, lib="wnc_ppro_lib.jsx")
        out = self.run_bridge(until=self.results("s"), what="the job answered")
        self.assertEqual(out["evals"], [])
        self.assertEqual(self.result("s")["error"], "script not allowed")

    def test_the_compatibility_script_runs_only_from_the_scripts_folder_with_an_allowlisted_name(self):
        other = self.script.with_name("other.jsx")
        other.write_text("// x", encoding="utf-8")
        self.job("a", "ping", 60, script=str(self.script.resolve()))                          # runs
        self.job("b", "ping", 60, script=str(other.resolve()))                                # not allowlisted
        self.job("c", "ping", 60, script=str(self.script.with_name("wnc_ae_bridge.jsx")))     # another host's
        self.job("d", "ping", 60, script=str(self.home / "ae-scripts" / "wnc_ppro_lib.jsx"))  # another folder
        out = self.run_bridge(until=self.results(*"abcd"), what="the four jobs answered")
        self.assertEqual([norm(e["file"]) for e in out["evals"]], [norm(self.script)])
        self.assertTrue(self.result("a")["ok"])
        for jid in "bcd":
            self.assertEqual(self.result(jid)["error"], "script not allowed", jid)

    def test_a_hostile_job_id_never_writes_outside_the_queue(self):
        """Review T6.3 1-4: the result and claim paths came from the JSON `id`, so "../../x" wrote outside the queue.
        The id is the job file's name; a JSON id that differs (or does not match ^[\\w.-]+$) is refused, in the queue."""
        for jid, hostile in (("h1", "../../escaped"), ("h2", "..\\..\\escaped2"), ("h3", "a b"), ("h4", "")):
            self.job(jid, "ping", 60)
            f = self.q / f"{jid}.job.json"
            f.write_text(json.dumps(dict(json.loads(f.read_text(encoding="utf-8")), id=hostile)), encoding="utf-8")
        out = self.run_bridge(until=self.results("h1", "h2", "h3", "h4"), what="the four jobs answered")
        self.assertEqual(out["evals"], [])
        for jid in ("h1", "h2", "h3", "h4"):
            r = self.result(jid)
            self.assertEqual((r["ok"], r["error"]), (False, "bad job id"), jid)
        for root in (self.tmp, self.home, self.q.parent.parent):
            self.assertEqual(sorted(p.name for p in root.rglob("escaped*")), [], root)
        self.assertEqual(sorted(p.name for p in self.q.glob("*.running")), [])

    def test_a_missing_library_is_not_found(self):
        (self.ext / "jsx" / "wnc_ppro_lib.jsx").unlink()
        self.script.unlink()
        self.job("m", "ping", 60)
        self.job("n", "ping", 60, script=str(self.script))
        self.run_bridge(until=self.results("m", "n"), what="both jobs answered")
        for jid in "mn":
            self.assertTrue(self.result(jid)["error"].startswith("script not found"), self.result(jid))

    def test_the_panel_never_claims(self):
        """Not even when no daemon beats (the 3.1.1 panel took over then): no claim, no heartbeat, no folder."""
        self.job("d", "ping", 60)
        out = self.run_bridge(role="panel", ticks=24)     # a panel that started a clock gets ticks to misbehave
        self.assertEqual(out["evals"], [])
        self.assertTrue((self.q / "d.job.json").exists())
        self.assertFalse((self.q / "d.claimed").exists())
        self.assertFalse((self.q / "bridge.heartbeat").exists())
        self.assertEqual(out["panel"]["role"], "panel")
        self.assertEqual(norm(out["panel"]["queue"]), norm(self.q))
        self.assertIsNone(out["panel"]["beat"])
        self.assertNotIn("WNC_BRIDGE", (CEP / "daemon.html").read_text(encoding="utf-8"))

    def test_the_panel_reads_the_daemons_beat(self):
        hb = {"at": time.time() * 1000, "role": "daemon", "busy": True, "current": "j", "version": "3.0.0"}
        (self.home / "ae-queue").mkdir()
        (self.home / "ae-queue" / "bridge.heartbeat").write_text(json.dumps(hb), encoding="utf-8")
        out = self.run_bridge(role="panel", host="AEFT")
        self.assertEqual((out["panel"]["host"], out["panel"]["bundle"]), ("AEFT", "3.0.0"))
        self.assertEqual(norm(out["panel"]["queue"]), norm(self.home / "ae-queue"))
        self.assertEqual(out["panel"]["beat"], hb)
        self.assertEqual(json.loads((self.home / "ae-queue" / "bridge.heartbeat").read_text(encoding="utf-8")), hb)

    def test_the_engine_home_comes_from_config_json_else_the_fallback(self):
        other = self.tmp / "other-home"
        other.mkdir()
        self.write_config(other)
        self.run_bridge()
        self.assertTrue((other / "ppro-queue" / "bridge.heartbeat").exists())
        cfg = self.user / ".whynot-cut" / "bridge" / "config.json"
        for bad in ({"schema": 2, "engine_home": str(other)}, {"schema": 1, "engine_home": "relative/home"},
                    {"schema": 1, "engine_home": str(self.tmp / "missing")}):
            shutil.rmtree(self.user / ".whynot-cut" / "ppro-queue", ignore_errors=True)
            cfg.write_text(json.dumps(bad), encoding="utf-8")
            self.run_bridge()
            self.assertTrue((self.user / ".whynot-cut" / "ppro-queue" / "bridge.heartbeat").exists(), bad)

    def test_a_linked_config_json_is_ignored(self):
        other = self.tmp / "other-home"
        other.mkdir()
        real = self.tmp / "elsewhere.json"
        real.write_text(json.dumps({"schema": 1, "engine_home": str(other)}), encoding="utf-8")
        cfg = self.user / ".whynot-cut" / "bridge" / "config.json"
        cfg.unlink()
        try:
            cfg.symlink_to(real)
        except OSError as e:
            self.skipTest(f"no symlinks here: {e}")
        self.run_bridge()
        self.assertFalse((other / "ppro-queue").exists())
        self.assertTrue((self.user / ".whynot-cut" / "ppro-queue" / "bridge.heartbeat").exists())


@unittest.skipUnless(NODE, "needs node to run js/bridge.js with a stubbed CEP")
class TestBridgeJsLegacy311(_SharedBridgeJsTests, _BridgeJs):
    """The frozen 3.1.1 (tests/fixtures/cep-bridge-3.1.1), live on the owner's PC until Gate 6: the engine still drives
    it (synced libraries, `script` jobs, the NHPP / NHAE aliases)."""
    BRIDGE = FROZEN_311 / "bridge.js"
    FAMILY = "legacy"
    REFUSED = "script not in whitelisted folder"
    ENTRY = {"PPRO": "NHPP", "AEFT": "NHAE"}

    def make_ext(self) -> Path:
        ext = self.tmp / "ext" / cep_bundle.EXT_ID
        ext.mkdir(parents=True)
        # what the 3.1.x engine wrote at install (3.1.1 reads its engine home from here)
        (ext / "bridge-config.json").write_text(json.dumps({"base": str(self.home)}), encoding="utf-8")
        return ext

    def ran_from(self, host):
        from lib import ae_bridge
        return ppro_bridge.lib_path() if host == "PPRO" else ae_bridge.entry_path()

    def test_the_heartbeat_is_the_311_shape(self):
        self.run_bridge()
        hb = self.beat()
        self.assertEqual((hb["version"], hb["role"], hb["host"]), ("3.1.1", "daemon", "PPRO"))
        self.assertNotIn("protocol", hb)
        st = cep_queue.status(self.q, app="Premiere")
        self.assertIsNone(cep_queue.version_refusal(st, ppro_bridge.BRIDGE_VERSION, "Premiere"))
        self.assertEqual(cep_queue.job_mode(st, ppro_bridge.BRIDGE_VERSION, "Premiere"), "script")

    def test_the_panel_works_the_queue_when_no_daemon_beats(self):
        self.job("d", "ping", 60)
        out = self.run_bridge(role="panel", until=self.results("d"),          # it waits DAEMON_STALE_MS first
                              what="the 3.1.1 panel taking the job once no daemon beats")
        self.assertEqual([e["action"] for e in out["evals"]], ["ping"])
        self.assertIn("this panel works the queue", out["log"])
        self.assertEqual(self.beat()["role"], "panel")


def norm(p) -> str:
    return os.path.normcase(os.path.realpath(str(p)))


if __name__ == "__main__":
    unittest.main()
