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
            "r-1", "ping", self.queue, lambda exclude=(): jobs.find_job(self.queue, PING, sha, 0.0, exclude), journal=self.journal,
            clock=self.clock)
        self.addCleanup(self.tracker.close)

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
        t = adapters.QueueTracker("none-1", "ping", self.queue, lambda exclude=(): "j9", journal=self.journal, clock=self.clock)
        self.addCleanup(t.close)
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


def beat(queue: Path, current):
    queue.mkdir(parents=True, exist_ok=True)
    (queue / "bridge.heartbeat").write_text(json.dumps({"at": 1, "current": current}), encoding="utf-8")


class VanishRules(TrackerCase):
    """Review 1: a job is missing only when none of its files is left AND the bridge's heartbeat no longer holds it,
    never after its result was seen, and a safe build (several queue jobs in a row) is never called vanished."""

    def seen_claimed(self, jid="jv"):
        self.tracker.begin()
        queue_job(self.queue, jid)
        claim(self.queue, jid)
        self.tick()

    def test_a_job_the_heartbeat_still_holds_is_not_vanished(self):
        self.seen_claimed()
        (self.queue / "jv.running").unlink()
        beat(self.queue, "jv")
        for _ in range(10):
            self.assertIsNone(self.tick()[1])
        beat(self.queue, None)
        self.assertIsNone(self.tick()[1])
        self.assertIsNone(self.tick()[1])
        self.assertEqual(self.tick()[1]["ok"], False)

    def test_a_job_whose_result_was_seen_is_never_called_vanished(self):
        self.seen_claimed()
        (self.queue / "jv.result.json").write_text("{}", encoding="utf-8")
        self.assertIsNone(self.tick()[1])                                  # done is seen
        for f in list(self.queue.glob("jv.*")):
            f.unlink()                                                     # the caller read it and cleaned up
        for _ in range(10):
            self.assertIsNone(self.tick()[1])

    def test_a_safe_build_never_vanishes(self):
        t = adapters.QueueTracker("r-1", "ping", self.queue, lambda exclude=(): "jv", journal=self.journal,
                                  clock=self.clock, vanish=False)
        self.addCleanup(t.close)
        t.begin()
        queue_job(self.queue, "jv")
        claim(self.queue, "jv")
        self.clock.advance(0.5)
        t.poll()
        for f in list(self.queue.glob("jv.*")):
            f.unlink()
        for _ in range(10):
            self.clock.advance(0.5)
            self.assertIsNone(t.poll()[1])

    def test_the_poll_slows_to_2_seconds_once_the_job_is_claimed(self):
        self.assertEqual(self.tracker.poll_s, adapters.TRACK_POLL_S)
        self.assertEqual(adapters.TRACK_POLL_S, 0.5)
        self.assertEqual(adapters.TRACK_POLL_CLAIMED_S, 2.0)
        self.tracker.begin()
        queue_job(self.queue, "jp")
        self.tick()
        self.assertEqual(self.tracker.poll_s, adapters.TRACK_POLL_S)        # queued: still fast (the claim is the news)
        claim(self.queue, "jp")
        self.tick()
        self.assertEqual(self.tracker.poll_s, adapters.TRACK_POLL_CLAIMED_S)


class TakenJobs(unittest.TestCase):
    """Review 2: two identical requests never share a queue job: a tracker takes its job id in a process-wide set, the
    other's locate skips it, and the id is released when the tracker closes."""

    def setUp(self):
        self.home = Path(tempfile.mkdtemp(prefix="wnc-prog-"))
        self.addCleanup(shutil.rmtree, self.home, True)
        self.queue = self.home / "ppro-queue"
        self.sha = jobs.data_sha({})
        self.clock = FakeClock()
        self.addCleanup(lambda: self.assertEqual(adapters._TAKEN, set()))

    def tracker(self, rid):
        t = adapters.QueueTracker(rid, "ping", self.queue,
                                  lambda exclude=(): jobs.find_job(self.queue, PING, self.sha, 0.0, exclude),
                                  journal=None, clock=self.clock)
        self.addCleanup(t.close)
        return t

    def test_the_second_tracker_gets_its_own_job(self):
        queue_job(self.queue, "ja")
        time.sleep(0.02)
        queue_job(self.queue, "jb")                                         # identical data, written later
        import os
        os.utime(self.queue / "ja.data.json", (1000, 1000))                 # ja is the older one
        a, b = self.tracker("r-a"), self.tracker("r-b")
        a.poll()
        b.poll()
        self.assertEqual((a.jid, b.jid), ("ja", "jb"))

    def test_a_taken_job_is_released_when_its_tracker_closes(self):
        queue_job(self.queue, "ja")
        a, b = self.tracker("r-a"), self.tracker("r-b")
        a.poll()
        b.poll()
        self.assertEqual((a.jid, b.jid), ("ja", None))
        a.close()
        b.poll()
        self.assertEqual(b.jid, "ja")

    def test_find_job_skips_the_excluded_ids(self):
        queue_job(self.queue, "ja")
        self.assertEqual(jobs.find_job(self.queue, PING, self.sha, 0.0), "ja")
        self.assertIsNone(jobs.find_job(self.queue, PING, self.sha, 0.0, exclude={"ja"}))


class FinalEntriesStayFinal(unittest.TestCase):
    """Review 3: a poll thread that outlives the result must not move a finished entry back to claimed."""

    def setUp(self):
        self.home = Path(tempfile.mkdtemp(prefix="wnc-prog-"))
        self.addCleanup(shutil.rmtree, self.home, True)
        self.journal = jobs.Journal(self.home)
        self.journal.start("r-1", action="ping", session_kind="cli", route="cep", lane="premiere", data={})

    def test_update_ignores_a_state_on_a_final_entry(self):
        res = {"ok": True, "action": "ping", "id": "r-1", "readback": PING_READBACK}
        self.journal.finish("r-1", res)
        out = self.journal.update("r-1", state="claimed", job_id="j1")
        e = self.journal.get("r-1")
        self.assertEqual((e["state"], e["job_id"], e["result"]["ok"]), ("done", "j1", True))
        self.assertEqual(out["state"], "done")
        self.assertEqual(self.journal.summaries()[0]["state"], "done")

    def test_a_poll_that_lands_after_the_result_leaves_the_entry_done(self):
        q = self.home / "ppro-queue"
        t = adapters.QueueTracker("r-1", "ping", q, lambda exclude=(): "j1", journal=self.journal)
        self.addCleanup(t.close)
        t.begin()
        queue_job(q, "j1")
        claim(q, "j1")
        self.journal.finish("r-1", {"ok": True, "action": "ping", "id": "r-1", "readback": PING_READBACK})
        t.poll()                                                            # the thread that outlived watch.cancel()
        self.assertEqual(self.journal.get("r-1")["state"], "done")

    def test_finish_can_still_settle_an_active_entry_in_any_final_state(self):
        self.journal.finish("r-1", {"ok": False, "action": "ping", "id": "r-1", "error": "x"}, "interrupted")
        self.assertEqual(self.journal.get("r-1")["state"], "interrupted")


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
        for name, val in (("PROGRESS_TICK_S", 0.2), ("TRACK_POLL_S", 0.04), ("TRACK_POLL_CLAIMED_S", 0.04)):
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
        """cep_queue reads the result and removes the job's files, then returns: for that moment the tracker sees a job
        it saw, with no file and no result, which is what a vanished job looks like. Within the grace (fewer than
        VANISHED_POLLS such polls in a row) the queue's own answer must be the answer.
        Ordered by events, never by the wall clock (macOS CI v3.0.0-p3: a 0.05 s sleep against a 3 x 0.04 s grace lost
        the race on a slower runner): the files go only after the tracker has seen the job claimed; the result is
        returned only after the tracker has counted VANISHED_POLLS - 1 polls with no file of it; and the tracker's
        next look (the one that would call it vanished) waits until the command has answered."""
        jid, grace = "jd1", adapters.VANISHED_POLLS - 1
        claimed_seen, misses_seen, answered = threading.Event(), threading.Event(), threading.Event()
        self.addCleanup(answered.set)
        real_state, looks = jobs.job_state, []                               # what the tracker saw of jd1, in order

        def job_state(queue, j):
            st = real_state(queue, j)
            if j == jid and (st is not None or claimed_seen.is_set()):
                if st == "claimed":
                    claimed_seen.set()
                if st is None and looks.count(None) >= grace:
                    answered.wait(T)                                          # the look past the grace: after the answer
                looks.append(st)
                if looks.count(None) >= grace and claimed_seen.is_set() and st is None:
                    misses_seen.set()
            return st

        def submit(action, data=None, timeout=600):
            queue_job(self.queue, jid, data)
            claim(self.queue, jid)
            if not claimed_seen.wait(T):
                raise AssertionError("the tracker never saw the job claimed")
            (self.queue / f"{jid}.running").unlink()                          # cep_queue read the result, removed the files
            if grace and not misses_seen.wait(T):
                raise AssertionError(f"the tracker never counted {grace} polls with no file: {looks}")
            return cep_ok("ping", PING_READBACK)

        with mock.patch.object(jobs, "job_state", job_state):
            res, _ = await self.run_adapter(request("ping", id="d-1"), submit)
            missed = looks.count(None)
            answered.set()
        self.assertTrue(res["ok"], res)
        self.assertEqual(res["id"], "d-1")
        self.assertIn("claimed", looks)
        self.assertEqual(missed, grace, looks)                               # it did see the files gone, and waited

    async def test_a_safe_build_with_several_queue_jobs_is_not_called_vanished(self):
        """Review 1: motion_build runs a build job, cleans it up, then a readback job (up to 300 s): the gap between
        them has no queue file of the first job, and the build is still running."""
        name = CEP_NAME["build_project"]

        def fake_build(action, data):
            queue_job(self.queue, "jb-1", {"x": 1}, name=name)
            time.sleep(0.1)
            claim(self.queue, "jb-1")
            time.sleep(0.1)
            for f in list(self.queue.glob("jb-1.*")):
                f.unlink()                                                  # the build job is read and cleaned up
            time.sleep(0.6)                                                 # (> VANISHED_POLLS polls)
            queue_job(self.queue, "jb-2", {"y": 2}, name="readback")        # the readback job
            claim(self.queue, "jb-2")
            time.sleep(0.2)
            for f in list(self.queue.glob("jb-2.*")):
                f.unlink()
            return {"ok": True, "readback": {"project": "p"}}

        req = request("build_project", {"x": 1}, id="sb-1")
        self.journal.start("sb-1", action="build_project", session_kind="cli", route="cep", lane="premiere", data={})
        with common.use_context(self.ctx), mock.patch.object(adapters, "_safe_build", fake_build):
            res = await adapters.FileQueueAdapter(journal=self.journal).run(req)
        self.assertEqual((res["ok"], res["id"]), (True, "sb-1"), res)

    async def test_two_identical_requests_each_follow_their_own_queue_job(self):
        """Review 2: the second waits for the lane, so its tracker must not adopt the first's job (and its journal
        must not get the first's job id)."""
        order, seen = [], {}

        def submit(action, data=None, timeout=600):
            jid = f"jx{len(order) + 1}"
            order.append(jid)
            queue_job(self.queue, jid, data)
            time.sleep(0.15)
            claim(self.queue, jid)
            time.sleep(0.45)
            if jid == "jx1":
                seen["b_while_a_runs"] = self.journal.get("b-1")
            for f in list(self.queue.glob(f"{jid}.*")):
                f.unlink()
            return cep_ok("ping", PING_READBACK)

        reqs = [request("ping", id="a-1"), request("ping", id="b-1")]
        for r in reqs:
            self.journal.start(r["id"], action="ping", session_kind="cli", route="cep", lane="premiere", data={})
        with common.use_context(self.ctx), mock.patch("lib.ppro_bridge.submit", submit):
            adapter = adapters.FileQueueAdapter(journal=self.journal)
            ra, rb = await asyncio.gather(adapter.run(reqs[0]), adapter.run(reqs[1]))
        self.assertTrue(ra["ok"] and rb["ok"], (ra, rb))
        self.assertNotIn("job_id", seen["b_while_a_runs"])                    # B did not take A's job
        self.assertEqual(self.journal.get("a-1")["job_id"], "jx1")
        self.assertEqual(self.journal.get("b-1")["job_id"], "jx2")
        self.assertEqual(adapters._TAKEN, set())                              # all released

    async def test_the_bridges_error_marker_flag_from_the_queue_is_the_marker_result(self):
        out = {"ok": False, "error_marker": True, "job": "jm"}                # what cep_queue._wait will return
        res, _ = await self.run_adapter(request("ping", id="m-1"), lambda action, data=None, timeout=600: out)
        self.assertEqual(res, jobs.error_marker_result("ping", "m-1", "Premiere"))

    async def test_an_interrupted_job_tells_the_editor_to_check_the_project(self):
        """The host may still have run it (the bridge's result says claimed): the how says to check the project."""
        out = {"ok": False, "error": "interrupted", "claimed": True, "job": "ji"}
        res, _ = await self.run_adapter(request("ping", id="i-1"),
                                        lambda action, data=None, timeout=600: out)
        self.assertEqual(res, jobs.bridge_restart_result("ping", "i-1", "Premiere"))
        self.assertIn("check the project", res["how"])

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
        for name, val in (("PROGRESS_TICK_S", 0.2), ("TRACK_POLL_S", 0.04), ("TRACK_POLL_CLAIMED_S", 0.04)):
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
