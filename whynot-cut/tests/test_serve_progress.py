"""`reel serve` CEP progress you can see in 2 s (3.0 Addendum G2, hardening H2 / budget S3): the FileQueueAdapter sends
synthetic v4 progress with a `phase` and `elapsed_s` (queued at submit, claimed when the bridge's claim marker appears,
an elapsed event every 2 s until the result), moves the journal received -> queued -> claimed from the same watch, and
answers ok:false at once when the bridge left its `<id>.error` marker (it could not write the result) or the job
vanished with no result. Run:
    bash tools/test.sh -p test_serve_progress.py
The queue folder is a temp one under a temp engine home (the CEP queue is never reached: lib.ppro_bridge.submit is
patched), the clock of the tracker is a fake one, no Adobe app, no token, no real ~/.whynot-cut.
"""
import sys as _sys
_sys.dont_write_bytecode = True  # keep the plugin folder free of __pycache__
import _isolation  # noqa: F401,E402  G79: sandbox the engine home before anything else (see tests/_isolation.py)
import asyncio
import json
import shutil
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

SK = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SK / "engine" / "reel"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import contract  # noqa: E402
from contract.cep import CEP_NAME  # noqa: E402
from lib import common  # noqa: E402
from serve import adapters, jobs, messages  # noqa: E402
from test_serve_app import AppCase, PING_READBACK, T, cep_ok, command, request  # noqa: E402

PING = CEP_NAME["ping"]


class FakeClock:
    def __init__(self, now=1000.0):
        self.now = now

    def __call__(self):
        return self.now

    def advance(self, s):
        self.now += s


def queue_job(queue: Path, jid: str, data=None, *, name=PING):
    """The two files cep_queue.submit writes: <jid>.data.json ({...data, action, job_id, submitted}) and <jid>.job.json."""
    queue.mkdir(parents=True, exist_ok=True)
    (queue / f"{jid}.data.json").write_text(json.dumps(dict(data or {}, action=name, job_id=jid, submitted="x")),
                                            encoding="ascii")
    (queue / f"{jid}.job.json").write_text("{}", encoding="utf-8")


def claim(queue: Path, jid: str, how="running"):
    """What the bridge does: rename the job (the atomic claim) and/or write <jid>.claimed."""
    if how == "running":
        (queue / f"{jid}.job.json").rename(queue / f"{jid}.running")
    else:
        (queue / f"{jid}.job.json").unlink()
        (queue / f"{jid}.claimed").write_text(json.dumps({"at": 1, "by": "daemon"}), encoding="utf-8")


class TrackerCase(unittest.TestCase):
    def setUp(self):
        self.home = Path(tempfile.mkdtemp(prefix="wnc-prog-"))
        self.addCleanup(shutil.rmtree, self.home, True)
        self.queue = self.home / "ppro-queue"
        self.clock = FakeClock()
        self.journal = jobs.Journal(self.home)
        self.journal.start("r-1", action="ping", session_kind="cli", route="cep", lane="premiere", data={})
        sha = jobs.data_sha({})
        self.tracker = adapters.QueueTracker(
            "r-1", "ping", self.queue, lambda: jobs.find_job(self.queue, PING, sha, 0.0), journal=self.journal,
            clock=self.clock)

    def tick(self, s=0.5):
        """One poll after `s` seconds of the fake clock; the events and the verdict."""
        self.clock.advance(s)
        return self.tracker.poll()

    def run_for(self, seconds, step=0.5):
        out = []
        for _ in range(int(round(seconds / step))):
            events, verdict = self.tick(step)
            out += events
            self.assertIsNone(verdict)
        return out


class Cadence(TrackerCase):
    def test_queued_is_the_first_event_and_comes_at_submit(self):
        (first,) = self.tracker.begin()
        self.assertEqual(first, {"event": "progress", "id": "r-1", "action": "ping", "step": "queued",
                                 "phase": "queued", "elapsed_s": 0.0})
        self.assertEqual(contract.validate(first, "progress"), [])

    def test_an_elapsed_event_every_2_seconds_and_nothing_between(self):
        self.tracker.begin()
        events = self.run_for(7.0)
        self.assertEqual([e["elapsed_s"] for e in events], [2.0, 4.0, 6.0])
        for e in events:
            self.assertEqual((e["event"], e["id"], e["action"], e["step"], e["phase"]),
                             ("progress", "r-1", "ping", "elapsed", "elapsed"))
            self.assertEqual(contract.validate(e, "progress"), [])

    def test_a_stalled_poller_never_bursts(self):
        self.tracker.begin()
        events, _ = self.tick(9.0)                       # the loop was starved for 9 s: one tick, not four
        self.assertEqual([e["elapsed_s"] for e in events], [9.0])
        events, _ = self.tick(0.5)                       # the next tick is the next multiple of 2 s
        self.assertEqual(events, [])
        events, _ = self.tick(0.5)
        self.assertEqual([e["elapsed_s"] for e in events], [10.0])
        events, _ = self.tick(1.0)
        self.assertEqual(events, [])

    def test_the_tick_is_the_module_constant(self):
        self.assertEqual(adapters.PROGRESS_TICK_S, 2.0)
        self.assertLessEqual(adapters.TRACK_POLL_S, 0.5)


class ClaimDetection(TrackerCase):
    def test_the_claim_by_rename_is_one_claimed_event_then_elapsed_continues(self):
        self.tracker.begin()
        queue_job(self.queue, "j1")
        self.assertEqual(self.tick()[0], [])
        self.assertEqual((self.journal.get("r-1")["state"], self.journal.get("r-1")["job_id"]), ("queued", "j1"))
        claim(self.queue, "j1", "running")
        events, _ = self.tick()
        self.assertEqual([(e["phase"], e["step"], e["elapsed_s"]) for e in events], [("claimed", "claimed", 1.0)])
        self.assertEqual(contract.validate(events[0], "progress"), [])
        self.assertEqual(self.journal.get("r-1")["state"], "claimed")
        later = self.run_for(4.0)
        self.assertEqual([(e["phase"], e["elapsed_s"]) for e in later], [("elapsed", 2.0), ("elapsed", 4.0)])
        self.assertNotIn("claimed", [e["phase"] for e in later])          # said once

    def test_the_claim_marker_file_counts_too(self):
        self.tracker.begin()
        queue_job(self.queue, "j2")
        self.tick()
        claim(self.queue, "j2", "marker")
        events, _ = self.tick()
        self.assertEqual([e["phase"] for e in events], ["claimed"])
        self.assertEqual(self.journal.get("r-1")["state"], "claimed")

    def test_a_job_claimed_before_it_was_found_is_queued_then_claimed_in_one_poll(self):
        self.tracker.begin()
        queue_job(self.queue, "j3")
        claim(self.queue, "j3")
        events, _ = self.tick()
        self.assertEqual([e["phase"] for e in events], ["claimed"])
        self.assertEqual((self.journal.get("r-1")["state"], self.journal.get("r-1")["job_id"]), ("claimed", "j3"))

    def test_the_journal_never_goes_back_from_claimed(self):
        self.tracker.begin()
        queue_job(self.queue, "j4")
        claim(self.queue, "j4")
        self.tick()
        (self.queue / "j4.running").unlink()
        (self.queue / "j4.job.json").write_text("{}", encoding="utf-8")   # a stray file of the same id
        self.tick()
        self.assertEqual(self.journal.get("r-1")["state"], "claimed")

    def test_another_commands_job_is_never_adopted(self):
        self.tracker.begin()
        queue_job(self.queue, "other", {"path": "x.prproj"})              # same action, other data: not this request
        self.tick()
        self.assertNotIn("job_id", self.journal.get("r-1"))
        self.assertEqual(self.journal.get("r-1")["state"], "received")

    def test_a_request_with_no_journal_entry_still_reports_progress(self):
        t = adapters.QueueTracker("none-1", "ping", self.queue, lambda: "j9", journal=self.journal, clock=self.clock)
        t.begin()
        queue_job(self.queue, "j9")
        claim(self.queue, "j9")
        events, verdict = t.poll()
        self.assertEqual(([e["phase"] for e in events], verdict), (["claimed"], None))
        self.assertIsNone(self.journal.get("none-1"))                      # nothing was invented


class ErrorMarker(TrackerCase):
    def test_the_error_marker_with_no_result_is_failed_at_once(self):
        self.tracker.begin()
        queue_job(self.queue, "j5")
        claim(self.queue, "j5")
        self.tick()
        (self.queue / "j5.running").unlink()                               # the bridge removes the job ...
        (self.queue / "j5.error").write_text(json.dumps({"ok": False, "error": "result write failed", "at": 1}),
                                             encoding="utf-8")             # ... and leaves its marker
        events, verdict = self.tick()
        self.assertEqual(events, [])
        self.assertEqual(verdict["ok"], False)
        self.assertEqual((verdict["action"], verdict["id"]), ("ping", "r-1"))
        self.assertIn("could not save", verdict["error"])
        self.assertTrue(verdict["how"])
        self.assertEqual(contract.validate_result(verdict), [])
        self.assertNotIn("result write failed", json.dumps(verdict))        # fixed sentences, never the file's text

    def test_a_result_beats_a_marker(self):
        self.tracker.begin()
        queue_job(self.queue, "j6")
        claim(self.queue, "j6")
        self.tick()
        (self.queue / "j6.result.json").write_text("{}", encoding="utf-8")
        (self.queue / "j6.error").write_text("{}", encoding="utf-8")
        events, verdict = self.tick()
        self.assertIsNone(verdict)

    def test_the_marker_is_failed_for_the_journal_helpers_too(self):
        queue_job(self.queue, "j7")
        self.assertEqual(jobs.job_state(self.queue, "j7"), "queued")
        (self.queue / "j7.error").write_text("{}", encoding="utf-8")
        self.assertEqual(jobs.job_state(self.queue, "j7"), "failed")
        res = jobs.read_result(self.queue, "j7", "ping", "r-7")
        self.assertEqual((res["ok"], res["id"], res["action"]), (False, "r-7", "ping"))
        self.assertEqual(contract.validate_result(res), [])
        (self.queue / "j7.result.json").write_text(json.dumps({"ok": True, "result": {
            "ok": True, "action": PING, "result": PING_READBACK}}), encoding="utf-8")
        self.assertEqual(jobs.job_state(self.queue, "j7"), "done")           # a result wins

    def test_a_vanished_job_with_no_result_is_failed_after_three_polls(self):
        self.tracker.begin()
        queue_job(self.queue, "j8")
        claim(self.queue, "j8")
        self.tick()
        (self.queue / "j8.running").unlink()                                # gone, no result, no marker
        self.assertEqual(self.tick()[1], None)                              # a result just read and deleted by the
        self.assertEqual(self.tick()[1], None)                              # caller looks the same: it gets a grace
        events, verdict = self.tick()
        self.assertEqual((verdict["ok"], verdict["id"]), (False, "r-1"))
        self.assertEqual(contract.validate_result(verdict), [])

    def test_a_job_never_seen_in_the_queue_is_not_called_vanished(self):
        self.tracker.begin()
        for _ in range(10):
            self.assertIsNone(self.tick()[1])


class JournalAlongTheWay(unittest.TestCase):
    def test_reconcile_finishes_a_marked_job_as_failed(self):
        home = Path(tempfile.mkdtemp(prefix="wnc-prog-"))
        self.addCleanup(shutil.rmtree, home, True)
        q = home / "ppro-queue"
        j = jobs.Journal(home)
        j.start("r-m", action="ping", session_kind="panel", route="cep", lane="premiere", data={})
        j.update("r-m", job_id="jm", state="claimed")
        q.mkdir(parents=True)
        (q / "jm.error").write_text("{}", encoding="utf-8")
        live = jobs.reconcile(j, lambda lane: q, lambda lane: True, lambda a: PING)
        self.assertEqual(live, [])
        e = j.get("r-m")
        self.assertEqual((e["state"], e["result"]["ok"]), ("failed", False))
        self.assertIn("could not save", e["result"]["error"])


class InterruptedByTheBridge(unittest.IsolatedAsyncioTestCase):
    """A restarted bridge answers the jobs it left running with {ok: false, error: "interrupted", reason: "bridge
    restarted"} (bridge.js, H2): serve says it in plain words, never the bare code, live and after a daemon restart."""

    PLAIN = "stopped before it finished"

    def test_a_stored_interrupted_result_is_a_plain_failure(self):
        home = Path(tempfile.mkdtemp(prefix="wnc-prog-"))
        self.addCleanup(shutil.rmtree, home, True)
        q = home / "ppro-queue"
        q.mkdir()
        (q / "ji.result.json").write_text(json.dumps({"ok": False, "error": "interrupted", "reason": "bridge restarted",
                                                      "at": 1}), encoding="utf-8")
        res = jobs.read_result(q, "ji", "ping", "r-i")
        self.assertEqual((res["ok"], res["id"], res["action"]), (False, "r-i", "ping"))
        self.assertIn(self.PLAIN, res["error"])
        self.assertNotIn("interrupted", res["error"].lower().replace("stopped before it finished", ""))
        self.assertTrue(res["how"])
        self.assertEqual(contract.validate_result(res), [])

    async def test_a_live_interrupted_answer_is_a_plain_failure(self):
        home = Path(tempfile.mkdtemp(prefix="wnc-prog-"))
        self.addCleanup(shutil.rmtree, home, True)
        out = {"ok": False, "error": "interrupted", "job": "ji"}               # what cep_queue._wait returns
        with common.use_context(common.Context(home=home)), mock.patch("lib.ppro_bridge.submit", return_value=out):
            res = await adapters.FileQueueAdapter().run(request("ping", id="r-i2"))
        self.assertEqual((res["ok"], res["id"]), (False, "r-i2"))
        self.assertIn(self.PLAIN, res["error"])
        self.assertTrue(res["how"])
        self.assertEqual(contract.validate_result(res), [])


# ---------------------------------------------------------------------------------------- through the adapter
class AdapterRun(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.home = Path(tempfile.mkdtemp(prefix="wnc-prog-"))
        self.addCleanup(shutil.rmtree, self.home, True)
        self.ctx = common.Context(home=self.home)
        self.queue = self.home / "ppro-queue"
        self.journal = jobs.Journal(self.home)
        for name, val in (("PROGRESS_TICK_S", 0.2), ("TRACK_POLL_S", 0.04)):
            p = mock.patch.object(adapters, name, val)
            p.start()
            self.addCleanup(p.stop)

    async def run_adapter(self, req, submit):
        got = []

        async def on_progress(p):
            got.append(p)

        self.journal.start(req["id"], action=req["action"], session_kind="cli", route="cep", lane="premiere",
                           data=req["data"])
        with common.use_context(self.ctx), mock.patch("lib.ppro_bridge.submit", submit):
            res = await adapters.FileQueueAdapter(journal=self.journal).run(req, on_progress=on_progress)
        return res, got

    async def test_queued_claimed_elapsed_then_the_result(self):
        seen = []

        def submit(action, data=None, timeout=600):
            queue_job(self.queue, "ja1", data)
            time.sleep(0.3)
            claim(self.queue, "ja1")
            time.sleep(0.6)
            seen.append(self.journal.get("a-1"))
            return cep_ok("ping", PING_READBACK)

        res, got = await self.run_adapter(request("ping", id="a-1"), submit)
        self.assertTrue(res["ok"])
        phases = [p["phase"] for p in got]
        self.assertEqual(phases[0], "queued")
        self.assertEqual(got[0]["elapsed_s"], 0.0)
        self.assertIn("claimed", phases)
        self.assertEqual(phases.count("claimed"), 1)
        self.assertLess(phases.index("claimed"), len(phases) - 1)             # elapsed ticks follow the claim
        self.assertEqual(phases[-1], "elapsed")
        self.assertGreaterEqual(phases.count("elapsed"), 2)
        for p in got:
            self.assertEqual(contract.validate(p, "progress"), [], p)
            self.assertEqual((p["id"], p["action"]), ("a-1", "ping"))
        e = [p["elapsed_s"] for p in got]
        self.assertEqual(e, sorted(e))                                        # elapsed never goes back
        self.assertEqual((seen[0]["state"], seen[0]["job_id"]), ("claimed", "ja1"))

    async def test_the_error_marker_fails_the_command_before_the_timeout(self):
        gate = threading.Event()
        self.addCleanup(gate.set)

        def submit(action, data=None, timeout=600):
            queue_job(self.queue, "jb1", data)
            time.sleep(0.15)
            claim(self.queue, "jb1")
            time.sleep(0.15)
            (self.queue / "jb1.running").unlink()
            (self.queue / "jb1.error").write_text("{}", encoding="utf-8")
            gate.wait(T)                                                      # cep_queue._wait knows no marker
            return cep_ok("ping", PING_READBACK)

        t0 = time.monotonic()
        res, got = await self.run_adapter(request("ping", id="b-1"), submit)
        self.assertLess(time.monotonic() - t0, T - 1)                         # not at the gate's timeout
        self.assertEqual((res["ok"], res["id"], res["action"]), (False, "b-1", "ping"))
        self.assertIn("could not save", res["error"])
        self.assertEqual(contract.validate_result(res), [])
        self.assertEqual(got[0]["phase"], "queued")

    async def test_a_vanished_job_fails_the_command(self):
        gate = threading.Event()
        self.addCleanup(gate.set)

        def submit(action, data=None, timeout=600):
            queue_job(self.queue, "jc1", data)
            time.sleep(0.15)
            claim(self.queue, "jc1")
            time.sleep(0.15)
            (self.queue / "jc1.running").unlink()                             # no result, no marker
            gate.wait(T)
            return cep_ok("ping", PING_READBACK)

        res, _ = await self.run_adapter(request("ping", id="c-1"), submit)
        self.assertEqual((res["ok"], res["id"]), (False, "c-1"))
        self.assertEqual(contract.validate_result(res), [])

    async def test_a_result_that_lands_while_the_job_files_go_away_is_still_the_result(self):
        def submit(action, data=None, timeout=600):
            queue_job(self.queue, "jd1", data)
            time.sleep(0.15)
            claim(self.queue, "jd1")
            time.sleep(0.15)
            (self.queue / "jd1.running").unlink()                             # cep_queue reads and removes the files
            time.sleep(0.05)
            return cep_ok("ping", PING_READBACK)

        res, _ = await self.run_adapter(request("ping", id="d-1"), submit)
        self.assertTrue(res["ok"])

    async def test_no_requester_listening_still_tracks_the_journal(self):
        def submit(action, data=None, timeout=600):
            queue_job(self.queue, "je1", data)
            time.sleep(0.1)
            claim(self.queue, "je1")
            time.sleep(0.25)
            return cep_ok("ping", PING_READBACK)

        req = request("ping", id="e-1")
        self.journal.start("e-1", action="ping", session_kind="cli", route="cep", lane="premiere", data={})
        with common.use_context(self.ctx), mock.patch("lib.ppro_bridge.submit", submit):
            res = await adapters.FileQueueAdapter(journal=self.journal).run(req)
        self.assertTrue(res["ok"])
        self.assertEqual(self.journal.get("e-1")["state"], "claimed")


# ---------------------------------------------------------------------------------------- through the daemon
class ThroughTheDaemon(AppCase):
    async def asyncSetUp(self):
        for name, val in (("PROGRESS_TICK_S", 0.2), ("TRACK_POLL_S", 0.04)):
            p = mock.patch.object(adapters, name, val)
            p.start()
            self.addCleanup(p.stop)
        await super().asyncSetUp()

    async def test_the_requester_sees_queued_first_then_claimed_with_elapsed(self):
        def submit(action, data=None, timeout=600):
            from lib import ppro_bridge
            q = ppro_bridge.queue_dir()
            queue_job(q, "jt1", data)
            time.sleep(0.2)
            claim(q, "jt1")
            time.sleep(0.5)
            return cep_ok("ping", PING_READBACK)

        with mock.patch("lib.ppro_bridge.submit", submit):
            c = await self.cli()
            await c.send(command("ping", id="thru-1"))
            progress = []
            while True:
                m = await c.recv()
                self.assertEqual(messages.validate_message(m), None, m)
                if m["type"] == "result":
                    break
                self.assertEqual(m["type"], "progress")
                progress.append(m["progress"])
        self.assertTrue(m["result"]["ok"])
        self.assertEqual(progress[0]["phase"], "queued")
        self.assertEqual(progress[0]["elapsed_s"], 0.0)
        self.assertIn("claimed", [p["phase"] for p in progress])
        self.assertIn("elapsed", [p["phase"] for p in progress])
        e = self.app.router.journal.get("thru-1")
        self.assertEqual((e["state"], e["job_id"]), ("done", "jt1"))

    async def test_the_snapshot_shows_the_claim_while_the_job_runs(self):
        seen = []

        def submit(action, data=None, timeout=600):
            from lib import ppro_bridge
            q = ppro_bridge.queue_dir()
            queue_job(q, "jt2", data)
            claim(q, "jt2")
            time.sleep(0.4)
            seen.append([j["state"] for j in self.app.router.journal.summaries() if j["request_id"] == "thru-2"])
            return cep_ok("ping", PING_READBACK)

        with mock.patch("lib.ppro_bridge.submit", submit):
            c = await self.cli()
            await c.send(command("ping", id="thru-2"))
            await c.recv_type("result")
        self.assertEqual(seen, [["claimed"]])


if __name__ == "__main__":
    unittest.main()
