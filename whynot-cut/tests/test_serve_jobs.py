"""`reel serve` job journal (3.0 Addendum G2, hardening H1): CEP jobs outlive the session that sent them, a repeated
request id attaches or replays (the host runs it once), the daemon reconciles the journal with the queue files at start,
and the journal is confined, atomic, size-capped and pruned. Run:
    bash tools/test.sh -p test_serve_jobs.py
Every App runs on a temp engine home; the CEP queue is never reached (lib.ppro_bridge.submit is patched, and the queue
files a test needs are written by the test into that temp home). No token, no real ~/.whynot-cut, no Adobe app.
"""
import sys as _sys
_sys.dont_write_bytecode = True  # keep the plugin folder free of __pycache__
import _isolation  # noqa: F401,E402  G79: sandbox the engine home before anything else (see tests/_isolation.py)
import asyncio
import json
import os
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
from serve import app as serve_app, jobs, messages, router, security  # noqa: E402
from test_serve_app import AppCase, PING_READBACK, T, cep_ok, command  # noqa: E402


async def until(cond, timeout=T, step=0.02):
    t0 = time.monotonic()
    while not cond():
        if time.monotonic() - t0 > timeout:
            raise AssertionError("condition not met in time")
        await asyncio.sleep(step)


def ping_result_file(queue: Path, jid: str):
    queue.mkdir(parents=True, exist_ok=True)
    inner = {"ok": True, "action": CEP_NAME["ping"], "result": PING_READBACK}
    (queue / f"{jid}.result.json").write_text(json.dumps({"ok": True, "result": inner, "at": 1}), encoding="utf-8")


def heartbeat(queue: Path):
    queue.mkdir(parents=True, exist_ok=True)
    from lib import cep_bundle
    from lib.ppro_bridge import BRIDGE_VERSION
    (queue / "bridge.heartbeat").write_text(json.dumps({
        "at": time.time() * 1000, "busy": True, "role": "daemon", "host": "PPRO", "version": BRIDGE_VERSION,
        "bundle": BRIDGE_VERSION, "protocol": cep_bundle.PROTOCOL, "current": None}), encoding="utf-8")


class GatedSubmit:
    """lib.ppro_bridge.submit that blocks until released, counting its calls."""

    def __init__(self, result=None):
        self.calls = 0
        self.entered = threading.Event()
        self.release = threading.Event()
        self.result = result or cep_ok("ping", PING_READBACK)

    def __call__(self, action, data=None, timeout=600):
        self.calls += 1
        self.entered.set()
        self.release.wait(T)
        return self.result


# ---------------------------------------------------------------------------------------------------- the journal
class JournalFiles(unittest.TestCase):
    def setUp(self):
        self.home = Path(tempfile.mkdtemp(prefix="wnc-jobs-"))
        self.addCleanup(shutil.rmtree, self.home, True)
        self.j = jobs.Journal(self.home)

    def test_request_ids_are_checked_against_a_strict_charset(self):
        for ok in ("r-1", "cmd-abc123-7", "A.b_c-d", "x" * 64, "0"):
            self.assertTrue(jobs.valid_id(ok), ok)
        for bad in ("", ".", "..", ".hidden", "-x", "_x", "a..b", "a/b", "a\\b", "a b", "x" * 65, "CON", "nul",
                    "com1.json", "LPT9", "aux.x", None, 5, "é"):
            self.assertFalse(jobs.valid_id(bad), repr(bad))

    def test_entries_stay_inside_the_jobs_folder(self):
        p = self.j.path("r-1")
        self.assertEqual(p.parent, self.home / "serve" / "jobs")
        for bad in ("../x", "..", "a/../../b", "CON", ""):
            with self.assertRaises(ValueError):
                self.j.path(bad)
            self.assertIsNone(self.j.get(bad))
        with self.assertRaises(ValueError):
            self.j.start("../evil", action="ping", session_kind="cli", route="cep")
        self.assertEqual(list(self.home.rglob("evil*")), [])

    def test_a_write_is_atomic(self):
        self.j.start("r-1", action="ping", session_kind="cli", route="cep", lane="premiere", data={})
        before = self.j.path("r-1").read_bytes()
        with mock.patch("serve.jobs.os.replace", side_effect=OSError("disk gone")):
            with self.assertRaises(OSError):
                self.j.update("r-1", state="claimed", job_id="j1")
        self.assertEqual(self.j.path("r-1").read_bytes(), before)          # the old entry, whole
        self.assertEqual([p.name for p in self.j.dir.iterdir()], ["r-1.json"])   # no temp file left
        self.assertEqual(self.j.get("r-1")["state"], "received")

    def test_an_entry_is_size_capped(self):
        self.j.start("r-big", action="ping", session_kind="cli", route="cep")
        huge = {"ok": True, "action": "ping", "id": "r-big", "readback": {"version": "x" * (jobs.ENTRY_MAX + 10),
                                                                         "project": "", "projects_open": 0}}
        self.j.finish("r-big", huge)
        self.assertLessEqual(self.j.path("r-big").stat().st_size, jobs.ENTRY_MAX)
        e = self.j.get("r-big")
        self.assertEqual((e["state"], e["result_truncated"], e["result"]["ok"]), ("done", True, True))
        self.assertEqual(e["result"]["readback"], {})
        failed = {"ok": False, "action": "ping", "id": "r-f", "error": "e" * (jobs.ENTRY_MAX + 10), "how": "h"}
        self.j.start("r-f", action="ping", session_kind="cli", route="cep")
        self.j.finish("r-f", failed)
        e = self.j.get("r-f")
        self.assertEqual((e["state"], len(e["result"]["error"]), e["result"]["how"]), ("failed", jobs.TEXT_MAX, "h"))
        # an over-size file on disk (written by something else) is never read
        self.j.path("r-f").write_text("{" + " " * (jobs.ENTRY_MAX + 1) + "}", encoding="utf-8")
        self.assertIsNone(self.j.get("r-f"))

    def test_retention_keeps_the_last_200_and_7_days(self):
        now = time.time()
        with mock.patch.object(self.j, "prune"):                   # start() prunes too: not while the test builds
            for i in range(jobs.KEEP + 5):
                self.j.start(f"r-{i}", action="ping", session_kind="cli", route="uxp")
                self.j.update(f"r-{i}", _t=now - 1000 + i)
            self.j.start("r-old", action="ping", session_kind="cli", route="uxp")
            self.j.update("r-old", _t=now - jobs.KEEP_S - 60)
        stale_tmp = self.j.dir / ".deadbeef.tmp"
        stale_tmp.write_text("x", encoding="utf-8")
        os.utime(stale_tmp, (now - 2 * jobs.TMP_STALE_S, now - 2 * jobs.TMP_STALE_S))
        gone = self.j.prune(now)
        self.assertIn("r-old", gone)
        names = {p.name[:-5] for p in self.j.dir.glob("*.json")}
        self.assertEqual(len(names), jobs.KEEP)
        self.assertNotIn("r-0", names)                              # the oldest went first
        self.assertIn(f"r-{jobs.KEEP + 4}", names)
        self.assertFalse(stale_tmp.exists())
        fresh = jobs.Journal(self.home)                             # a new daemon indexes what is left
        self.assertEqual(len(fresh.summaries(10_000)), jobs.KEEP)

    def test_newest_first_is_a_total_order_even_when_timestamps_are_equal(self):
        """Gate 3: a loaded machine gives two entries the same clock reading. The order is the journal's own write
        sequence (seq), the same for the snapshot, entries() and retention, and it survives a daemon restart."""
        frozen = jobs._now()     # one real reading: start() prunes on the real clock, so a fixed date ages out
        frozen = (frozen[0], float(int(frozen[1])))
        with mock.patch.object(jobs, "_now", return_value=frozen):
            for rid in ("r-a", "r-b", "r-c", "r-d"):
                self.j.start(rid, action="ping", session_kind="cli", route="uxp")
            self.j.finish("r-a", {"ok": True, "action": "ping", "id": "r-a", "readback": {}})   # no reordering
        order = ["r-d", "r-c", "r-b", "r-a"]
        self.assertEqual([s["request_id"] for s in self.j.summaries()], order)
        self.assertEqual([e["request_id"] for e in self.j.entries()], order)
        fresh = jobs.Journal(self.home)                                 # a restarted daemon: same order
        self.assertEqual([s["request_id"] for s in fresh.summaries()], order)
        with mock.patch.object(jobs, "_now", return_value=frozen):
            fresh.start("r-e", action="ping", session_kind="cli", route="uxp")   # continues after the max seq
        self.assertEqual([s["request_id"] for s in fresh.summaries()][:2], ["r-e", "r-d"])
        with mock.patch.object(jobs, "KEEP", 3):                        # retention drops the oldest by that order
            gone = fresh.prune(frozen[1])
        self.assertEqual(sorted(gone), ["r-a", "r-b"])
        self.assertEqual([s["request_id"] for s in fresh.summaries()], ["r-e", "r-d", "r-c"])

    def test_entries_without_a_sequence_sort_after_the_others_deterministically(self):
        """Backward compatible: an entry written before `seq` existed sorts after every entry that has one, newest
        `_t` first, then by request id."""
        self.j.start("r-new", action="ping", session_kind="cli", route="uxp")
        for rid, t in (("r-old-b", 100.0), ("r-old-a", 100.0), ("r-old-c", 50.0)):
            doc = {"request_id": rid, "action": "ping", "session_kind": "cli", "route": "uxp", "state": "received",
                   "submitted_at": "2026-10-01T00:00:00+00:00", "updated_at": "2026-10-01T00:00:00+00:00", "_t": t}
            self.j.path(rid).write_text(json.dumps(doc), encoding="utf-8")
        for j in (jobs.Journal(self.home), jobs.Journal(self.home)):
            self.assertEqual([s["request_id"] for s in j.summaries()], ["r-new", "r-old-b", "r-old-a", "r-old-c"])
        j = jobs.Journal(self.home)
        j.start("r-next", action="ping", session_kind="cli", route="uxp")
        self.assertEqual([s["request_id"] for s in j.summaries()][:2], ["r-next", "r-new"])

    def test_summaries_follow_the_session_schema_and_carry_no_host_text(self):
        self.j.start("r-a", action="build_project", session_kind="panel", route="cep", lane="premiere",
                     data={"project_path": "D:/secret/C0239.prproj"})
        self.j.start("r-b", action="ping", session_kind="cli", route="cep")
        self.j.finish("r-b", {"ok": False, "action": "ping", "id": "r-b", "error": "D:/secret/x failed", "how": "h"})
        self.j.start("r-c", action="ping", session_kind="cli", route="uxp")
        self.j.finish("r-c", jobs.interrupted_result("ping", "r-c", "why", "how"), "interrupted")
        rows = self.j.summaries()
        self.assertEqual([r["request_id"] for r in rows], ["r-c", "r-b", "r-a"])          # newest first
        self.assertEqual(rows[0]["result"], {"ok": False, "code": "interrupted"})
        self.assertEqual(rows[1]["result"], {"ok": False})
        self.assertNotIn("result", rows[2])
        self.assertNotIn("secret", json.dumps(rows))
        st = messages.state("offline", jobs=rows)
        self.assertIsNone(messages.validate_message(st))
        for r in rows:
            self.assertEqual(contract.validate(r, "session#/$defs/job_summary"), [], r)


# ------------------------------------------------------------------------------------------- the session drops
class SessionDropKeepsTheCepJob(AppCase):
    async def test_a_dropped_session_does_not_cancel_the_cep_job_and_a_reconnect_sees_done(self):
        gate = GatedSubmit()
        with mock.patch("lib.ppro_bridge.submit", gate):
            c = await self.cli()
            msg = command("ping", id="drop-1")
            await c.send(msg)
            await asyncio.to_thread(gate.entered.wait, T)
            self.assertEqual(self.app.router.journal.get("drop-1")["state"], "received")
            await c.aclose()                                         # the panel's session drops mid-job
            await until(lambda: not self.app.sessions)
            gate.release.set()                                       # ... and Premiere finishes it anyway
            await until(lambda: (self.app.router.journal.get("drop-1") or {}).get("state") == "done")
            c2 = await self.cli()                                    # the reconnect
            await c2.send({"type": "snapshot", "id": "snap-1"})
            st = await c2.recv_type("state")
            row = next(j for j in st["state"]["jobs"] if j["request_id"] == "drop-1")
            self.assertEqual((row["state"], row["result"]), ("done", {"ok": True}))
            await c2.send(msg)                                       # reattach by request id: the stored result
            res = await c2.recv_type("result")
        self.assertEqual(res["result"], {"ok": True, "action": "ping", "id": "drop-1", "readback": PING_READBACK})
        self.assertEqual(gate.calls, 1)                              # the host ran it once
        self.assertIn("replayed", [r["outcome"] for r in self.events("command")])
        text = self.app.router.journal.path("drop-1").read_text(encoding="utf-8")
        self.assertNotIn(self.token, text)
        self.assertNotIn(self.token, security.audit_log_path(self.home).read_text(encoding="utf-8"))

    async def test_a_uxp_job_stays_tied_to_its_session(self):
        p = await self.panel(caps=("ping",))
        c = await self.cli()
        await c.send(command("ping", id="uxp-1"))
        self.assertEqual((await p.recv())["type"], "command")
        await c.aclose()
        self.assertEqual(await asyncio.wait_for(p.recv(), T), {"type": "cancel", "id": "uxp-1"})
        await until(lambda: (self.app.router.journal.get("uxp-1") or {}).get("state") == "interrupted")
        res = self.app.router.journal.get("uxp-1")["result"]
        self.assertEqual((res["ok"], res["id"]), (False, "uxp-1"))
        self.assertEqual(contract.validate_result(res), [])


class SameIdTwice(AppCase):
    async def test_the_same_request_id_twice_runs_the_host_once(self):
        gate = GatedSubmit()
        with mock.patch("lib.ppro_bridge.submit", gate):
            a, b = await self.cli(), await self.cli()
            msg = command("ping", id="twice-1")
            await a.send(msg)
            await asyncio.to_thread(gate.entered.wait, T)
            await b.send(msg)                                        # in flight: b attaches
            await until(lambda: "attached" in [r["outcome"] for r in self.events("command")])
            gate.release.set()
            ra, rb = await a.recv_type("result"), await b.recv_type("result")
            await a.send(msg)                                        # settled: replayed
            rc = await a.recv_type("result")
        self.assertEqual(gate.calls, 1)
        for r in (ra, rb, rc):
            self.assertEqual(r["result"], {"ok": True, "action": "ping", "id": "twice-1", "readback": PING_READBACK})

    async def test_an_id_reused_for_another_action_is_refused(self):
        with mock.patch("lib.ppro_bridge.submit", return_value=cep_ok("ping", PING_READBACK)):
            c = await self.cli()
            await c.send(command("ping", id="reuse-1"))
            self.assertTrue((await c.recv_type("result"))["result"]["ok"])
            await c.send(command("status", id="reuse-1"))
            err = await c.recv()
        self.assertEqual((err["type"], err["code"], err["id"]), ("error", "schema", "reuse-1"))

    async def test_an_id_that_cannot_name_a_journal_file_is_refused(self):
        c = await self.cli()
        with mock.patch("lib.ppro_bridge.submit", side_effect=AssertionError("queued")):
            for rid in ("..", "-x", "CON", "a..b"):
                await c.send(command("ping", id=rid))
                err = await c.recv()
                self.assertEqual((err["type"], err["code"]), ("error", "schema"), rid)
        folder = self.home / "serve" / "jobs"
        self.assertEqual(list(folder.iterdir()) if folder.exists() else [], [])        # nothing was journaled


class QueueWatch(AppCase):
    async def test_a_running_cep_job_journals_its_queue_job_id_and_claim(self):
        seen = []

        def fake_submit(action, data=None, timeout=600):
            from lib import ppro_bridge
            q = ppro_bridge.queue_dir()
            q.mkdir(parents=True, exist_ok=True)
            (q / "jw1.data.json").write_text(json.dumps(dict(data or {}, action=action, job_id="jw1", submitted="x")),
                                             encoding="ascii")
            (q / "jw1.job.json").write_text("{}", encoding="utf-8")
            time.sleep(3 * router.WATCH_S)
            (q / "jw1.job.json").rename(q / "jw1.running")
            time.sleep(3 * router.WATCH_S)
            seen.append(self.app.router.journal.get("watch-1"))
            return cep_ok("ping", PING_READBACK)

        with mock.patch("lib.ppro_bridge.submit", fake_submit):
            c = await self.cli()
            await c.send(command("ping", id="watch-1"))
            res = await c.recv_type("result")
        self.assertTrue(res["result"]["ok"])
        self.assertEqual((seen[0]["job_id"], seen[0]["state"]), ("jw1", "claimed"))
        e = self.app.router.journal.get("watch-1")
        self.assertEqual((e["state"], e["job_id"], e["route"], e["session_kind"]), ("done", "jw1", "cep", "cli"))


# --------------------------------------------------------------------------------------------- the daemon restarts
class DaemonRestart(AppCase):
    """A daemon died with jobs in flight; the next one reconciles the journal with the queue files, then replays."""

    async def asyncSetUp(self):
        self.home_pre = Path(tempfile.mkdtemp(prefix="wnc-serve-"))
        j = jobs.Journal(self.home_pre)
        q = self.home_pre / "ppro-queue"
        j.start("r-done", action="ping", session_kind="panel", route="cep", lane="premiere", data={})
        j.update("r-done", job_id="j1", state="claimed")
        ping_result_file(q, "j1")
        j.start("r-lost", action="ping", session_kind="panel", route="cep", lane="premiere", data={})
        j.update("r-lost", job_id="j2", state="claimed")                  # no file of it left, no heartbeat
        j.start("r-uxp", action="ping", session_kind="cli", route="uxp")
        j.start("r-live", action="ping", session_kind="panel", route="cep", lane="premiere", data={})
        q.mkdir(parents=True, exist_ok=True)                              # in the queue, never matched yet
        (q / "j3.data.json").write_text(json.dumps({"action": CEP_NAME["ping"], "job_id": "j3",
                                                    "submitted": "s"}), encoding="ascii")
        (q / "j3.running").write_text("{}", encoding="utf-8")
        await super().asyncSetUp()

    async def asyncTearDown(self):
        await super().asyncTearDown()
        shutil.rmtree(self.home_pre, ignore_errors=True)

    async def start_app(self):
        await self.app.close()
        self.home, old = self.home_pre, self.home
        shutil.rmtree(old, ignore_errors=True)
        heartbeat(self.home / "ppro-queue")
        self.app = serve_app.App(home=self.home, token=self.token, version="3.0.0-test", hello_timeout=1.0)
        self.port = await self.app.start()

    async def beat(self):
        """Premiere stays open: its bridge heartbeat is kept fresh (a loaded machine must not make it look dead)."""
        while True:
            heartbeat(self.home / "ppro-queue")
            await asyncio.sleep(0.5)

    async def test_reconcile_then_replay(self):
        with mock.patch("lib.ppro_bridge.submit", side_effect=AssertionError("the host must not run it again")):
            await self.start_app()
            beating = asyncio.create_task(self.beat())
            self.addCleanup(beating.cancel)
            j = self.app.router.journal
            self.assertEqual(j.get("r-done")["state"], "done")
            self.assertEqual(j.get("r-lost")["state"], "interrupted")
            self.assertEqual(j.get("r-uxp")["state"], "interrupted")
            self.assertEqual((j.get("r-live")["state"], j.get("r-live")["job_id"]), ("claimed", "j3"))
            c = await self.cli()
            await c.send(command("ping", id="r-done"))
            self.assertEqual((await c.recv_type("result"))["result"],
                             {"ok": True, "action": "ping", "id": "r-done", "readback": PING_READBACK})
            await c.send(command("ping", id="r-lost"))
            lost = (await c.recv_type("result"))["result"]
            self.assertEqual((lost["ok"], lost["id"]), (False, "r-lost"))
            self.assertIn("stopped before it finished", lost["error"])
            self.assertEqual(contract.validate_result(lost), [])
            await c.send(command("ping", id="r-live"))           # still in Premiere: attach ...
            await until(lambda: "attached" in [r["outcome"] for r in self.events("command")])
            ping_result_file(self.home / "ppro-queue", "j3")              # ... it finishes
            live = (await c.recv_type("result"))["result"]
            self.assertEqual(live, {"ok": True, "action": "ping", "id": "r-live", "readback": PING_READBACK})
            self.assertEqual(j.get("r-live")["state"], "done")
            await c.send({"type": "snapshot", "id": "snap-2"})
            rows = {r["request_id"]: r for r in (await c.recv_type("state"))["state"]["jobs"]}
        self.assertEqual({k: rows[k]["state"] for k in ("r-done", "r-lost", "r-uxp", "r-live")},
                         {"r-done": "done", "r-lost": "interrupted", "r-uxp": "interrupted", "r-live": "done"})
        self.assertEqual(rows["r-lost"]["result"], {"ok": False, "code": "interrupted"})

    async def test_a_followed_job_whose_bridge_stops_is_interrupted(self):
        with mock.patch.object(router, "HOST_CHECK_S", 0.05), \
                mock.patch("lib.ppro_bridge.submit", side_effect=AssertionError("must not run")):
            await self.start_app()
            (self.home / "ppro-queue" / "bridge.heartbeat").unlink()       # Premiere quits
            await until(lambda: (self.app.router.journal.get("r-live") or {}).get("state") == "interrupted")


if __name__ == "__main__":
    unittest.main()
