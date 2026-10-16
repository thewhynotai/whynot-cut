"""`reel serve` and Adobe's host_busy (3.0 Addendum G2 hardening H6, G13):
    * serve/host_busy.py reads the CEP bridge heartbeat's host_busy back, read only: per app ("offline" when no bridge
      beats there, "unknown" for a beat that stopped recently or a value it cannot vouch for) and overall, for the engine
      GPU lock (Phase 4) to call;
    * panel_state.connection.host.busy (session.schema.json) carries the Premiere value while the CEP bridge is the
      host; absent for a UXP host and offline;
    * the state pusher looks only while a panel is connected, and one look costs a fixed, counted number of reads.
Run:
    bash tools/test.sh -k test_serve_host_busy
Deterministic: heartbeats are files with a chosen `at` and the accessor takes `now`; costs are counted with wrappers,
never timed.
"""
import sys as _sys
_sys.dont_write_bytecode = True  # keep the plugin folder free of __pycache__
import _isolation  # noqa: F401,E402  G79: sandbox the engine home before anything else (see tests/_isolation.py)
import asyncio
import json
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

SK = Path(__file__).resolve().parents[1]
_sys.path.insert(0, str(SK / "engine" / "reel"))
_sys.path.insert(0, str(Path(__file__).resolve().parent))

from contract import validate  # noqa: E402
from lib import cep_queue, common, ppro_bridge  # noqa: E402
from serve import host_busy, messages  # noqa: E402
from test_serve_app import AppCase  # noqa: E402
from test_serve_perf import FakeFields  # noqa: E402

NOW = 1_760_000_000.0


def write_beat(queue: Path, *, age_s: float = 0.0, now: float = NOW, raw: str | None = None, **fields) -> Path:
    queue.mkdir(parents=True, exist_ok=True)
    hb = queue / "bridge.heartbeat"
    doc = dict({"at": int((now - age_s) * 1000), "busy": False, "role": "daemon", "host": "PPRO", "protocol": 4,
                "version": "3.0.0", "bundle": "3.0.0"}, **fields)
    hb.write_text(raw if raw is not None else json.dumps(doc), encoding="utf-8")
    return hb


def status_carries_host_busy() -> bool:
    """Does this engine's cep_queue.status already return host_busy (the executor's T4.10 hunk)? Asked once, on a
    fake heartbeat, so the cost test expects 0 extra reads with the hunk and 1 without it."""
    with tempfile.TemporaryDirectory() as t:
        write_beat(Path(t), now=time.time(), host_busy="idle")
        return "host_busy" in cep_queue.status(Path(t))


class AccessorTests(unittest.TestCase):
    def setUp(self):
        self._t = tempfile.TemporaryDirectory()
        self.home = Path(self._t.name)
        self.pq, self.aq = self.home / "ppro-queue", self.home / "ae-queue"

    def tearDown(self):
        self._t.cleanup()

    def test_a_lane_reads_the_heartbeat_value(self):
        for v in host_busy.HOST_BUSY:
            with self.subTest(v):
                write_beat(self.pq, host_busy=v)
                self.assertEqual(host_busy.lane(self.pq, now=NOW), v)

    def test_what_the_bridge_cannot_vouch_for_is_unknown(self):
        cases = {"an older bridge (no field)": {}, "a value outside the enum": {"host_busy": "busy"},
                 "not a string": {"host_busy": 1}}
        for name, fields in cases.items():
            with self.subTest(name):
                write_beat(self.pq, **fields)
                self.assertEqual(host_busy.lane(self.pq, now=NOW), "unknown")
        for name, raw in {"torn": '{"at": 17600', "no time": '{"host_busy": "idle"}', "not json": "x"}.items():
            with self.subTest(name):
                write_beat(self.pq, raw=raw)
                self.assertEqual(host_busy.lane(self.pq, now=NOW), "unknown")

    def test_age_no_file_is_offline_a_recent_stop_is_unknown_an_old_one_offline(self):
        self.assertEqual(host_busy.lane(self.pq, now=NOW), "offline")
        for age, want in ((4.9, "rendering"), (5.0, "unknown"), (119.0, "unknown"), (121.0, "offline")):
            with self.subTest(age):
                write_beat(self.pq, age_s=age, host_busy="rendering")
                self.assertEqual(host_busy.lane(self.pq, now=NOW), want)
        self.assertEqual(host_busy.lane_value(self.pq, now=NOW), "unknown")   # alive already known: never offline

    def test_a_torn_read_is_read_once_more(self):
        write_beat(self.pq, host_busy="exporting")
        good = (self.pq / "bridge.heartbeat").read_text(encoding="utf-8")
        reads = iter(['{"at": 17', good])
        with mock.patch.object(Path, "read_text", lambda self, encoding=None: next(reads)):
            self.assertEqual(host_busy.lane(self.pq, now=NOW), "exporting")
        reads = iter(['{"at": 17', '{"at"'])
        with mock.patch.object(Path, "read_text", lambda self, encoding=None: next(reads)):
            self.assertEqual(host_busy.lane(self.pq, now=NOW), "unknown")   # torn twice: no third read

    def test_fresh_is_the_engines_own_rule(self):
        import inspect
        self.assertEqual(host_busy.FRESH_S, inspect.signature(cep_queue.status).parameters["max_age_s"].default)

    def test_overall(self):
        table = [  # (premiere, after effects) -> overall; None = no heartbeat at all
            ((None, None), "idle"), (("idle", None), "idle"), (("idle", "idle"), "idle"),
            (("exporting", "unknown"), "exporting"), (("unknown", "rendering"), "rendering"),
            (("exporting", "rendering"), "exporting"), (("unknown", None), "unknown"), (("idle", "unknown"), "unknown")]
        for (pp, ae), want in table:
            with self.subTest(pp=pp, ae=ae):
                for q, v in ((self.pq, pp), (self.aq, ae)):
                    (q / "bridge.heartbeat").unlink(missing_ok=True)
                    if v is not None:
                        write_beat(q, host_busy=v)
                out = host_busy.host_busy(self.home, now=NOW)
                self.assertEqual(out, {"premiere": pp or "offline", "after_effects": ae or "offline", "overall": want})

    def test_the_default_home_is_the_bound_context_and_nothing_is_written(self):
        write_beat(self.aq, now=time.time(), host_busy="rendering")
        before = sorted(p.name for p in self.home.rglob("*"))
        with common.use_context(common.Context(home=self.home)):
            self.assertEqual(host_busy.host_busy()["after_effects"], "rendering")
        self.assertEqual(sorted(p.name for p in self.home.rglob("*")), before)


class ContractTests(unittest.TestCase):
    def test_connection_host_busy_is_a_closed_optional_field(self):
        for v in host_busy.HOST_BUSY:
            st = messages.state("cep", None, "s1", host_busy=v)
            self.assertEqual(st["state"]["connection"]["host"], {"state": "cep", "busy": v})
            self.assertEqual(validate(st, "session#/$defs/state"), [])
        self.assertNotIn("busy", messages.state("offline")["state"]["connection"]["host"])
        self.assertEqual(messages.state("cep", host_busy="weird")["state"]["connection"]["host"]["busy"], "unknown")
        bad = messages.state("cep", host_busy="idle")
        bad["state"]["connection"]["host"]["busy"] = "exporting-ish"
        self.assertNotEqual(validate(bad, "session#/$defs/state"), [])
        self.assertEqual(messages.HOST_BUSY, host_busy.HOST_BUSY)

    def test_the_schema_enum_matches(self):
        schema = json.loads((SK / "engine" / "reel" / "contract" / "session.schema.json").read_text(encoding="utf-8"))
        busy = schema["$defs"]["connection"]["properties"]["host"]["properties"]["busy"]
        self.assertEqual(tuple(busy["enum"]), host_busy.HOST_BUSY)
        self.assertNotIn("busy", schema["$defs"]["connection"]["properties"]["host"]["required"])


class AppHostBusyTests(AppCase):
    app_options = {"push_interval": 0.01, "push_debounce": 0.0}

    async def asyncSetUp(self):
        await super().asyncSetUp()
        self.fields = FakeFields()
        self.app._fields = self.fields

    def beat(self, **fields):
        write_beat(self.home / "ppro-queue", now=time.time(), **fields)

    async def host_of(self, c, sid):
        await c.send({"type": "snapshot", "id": sid})
        st = await c.recv_type("state")
        while st.get("id") != sid:
            st = await c.recv_type("state")
        return st["state"]["connection"]["host"]

    async def until(self, cond):
        for _ in range(500):
            if cond():
                return
            await asyncio.sleep(0.01)
        self.fail("condition not met")

    async def test_a_snapshot_carries_the_cep_hosts_busy_value(self):
        c = await self.cli()
        self.beat(host_busy="exporting")
        self.assertEqual(await self.host_of(c, "a"), {"state": "cep", "busy": "exporting"})
        self.beat()                                                          # an older bridge: no field
        self.assertEqual(await self.host_of(c, "b"), {"state": "cep", "busy": "unknown"})
        (self.home / "ppro-queue" / "bridge.heartbeat").unlink()
        self.assertEqual(await self.host_of(c, "c"), {"state": "offline"})
        self.beat(host_busy="idle")
        p = await self.panel(caps=("ping",))                                 # a UXP host does not report it
        self.assertEqual(await self.host_of(c, "d"), {"state": "uxp", "detail": "Premiere Pro 26.0"})
        await p.aclose()

    async def test_a_status_that_carries_host_busy_needs_no_second_read(self):
        """Once cep_queue.status returns host_busy (the executor's hunk), serve takes it from there."""
        c = await self.cli()
        with mock.patch("lib.ppro_bridge.status", return_value={"alive": True, "host_busy": "rendering"}), \
                mock.patch.object(host_busy, "lane", wraps=host_busy.lane) as lane:
            self.assertEqual(await self.host_of(c, "a"), {"state": "cep", "busy": "rendering"})
        self.assertEqual(lane.call_count, 0)

    async def test_a_host_busy_change_is_pushed(self):
        self.beat(host_busy="idle")
        c = await self.hello(kind="panel")
        self.assertEqual((await c.recv())["type"], "welcome")
        self.assertEqual((await self.host_of(c, "first"))["busy"], "idle")
        self.beat(host_busy="exporting")
        for _ in range(50):
            st = await c.recv_type("state")
            if st["state"]["connection"]["host"].get("busy") == "exporting":
                break
        else:
            self.fail("the change was never pushed")
        self.assertNotIn("id", st)

    async def test_read_host_busy_is_the_accessor_for_this_home(self):
        self.beat(host_busy="exporting")
        self.assertEqual(self.app.read_host_busy(), {"premiere": "exporting", "after_effects": "offline",
                                                     "overall": "exporting"})

    async def test_one_push_look_costs_one_fields_read_one_status_and_at_most_one_heartbeat_read(self):
        """The cost of the 1 s push look (push.py), counted: no wall clock. The host_busy heartbeat read happens only
        while cep_queue.status does not carry host_busy (the executor's T4.10 hunk): 1 per look before it, 0 after."""
        self.beat(host_busy="idle")
        looks = 25
        with mock.patch("lib.ppro_bridge.status", wraps=ppro_bridge.status) as status, \
                mock.patch.object(host_busy, "lane", wraps=host_busy.lane) as lane, \
                mock.patch.object(self.app.router.journal, "summaries", wraps=self.app.router.journal.summaries) as jobs:
            calls = self.fields.calls
            fps = set()
            for _ in range(looks):
                fp, payload, stale = await self.app._push_probe()
                fps.add(fp)
            self.assertEqual(self.fields.calls - calls, looks)               # one engine-state read (a cache hit)
            self.assertEqual(status.call_count, looks)                        # one bridge status
            extra = 0 if status_carries_host_busy() else 1
            self.assertEqual(lane.call_count, looks * extra)                  # the host_busy heartbeat read, if any
            self.assertEqual(jobs.call_count, looks)                          # the journal: in memory, no file
        self.assertEqual(len(fps), 1, "nothing changed: one fingerprint, so no push")
        self.assertIsNone(self.app._pusher_task, "no panel: the test drove the looks itself")

    async def test_a_snapshot_restarts_a_pusher_that_stopped(self):
        """Review P2: a pusher task that ended (a crash, a cancel) starts again on the panel's next snapshot."""
        c = await self.hello(kind="panel")
        self.assertEqual((await c.recv())["type"], "welcome")
        await self.host_of(c, "first")
        await self.until(lambda: self.app._pusher_task is not None)
        old = self.app._pusher_task
        old.cancel()
        await self.until(lambda: old.done())
        await self.host_of(c, "again")
        self.assertIsNot(self.app._pusher_task, old)
        self.assertFalse(self.app._pusher_task.done())

    async def test_no_panel_no_look_and_the_looks_stop_with_the_last_panel(self):
        c = await self.cli()
        p = await self.panel(caps=("ping",))
        calls = self.fields.calls
        await asyncio.sleep(0.2)                                             # ~20 push intervals with no panel
        self.assertIsNone(self.app._pusher_task)
        self.assertEqual(self.fields.calls, calls, "nobody asked: no engine-state read")
        panel = await self.hello(kind="panel")
        self.assertEqual((await panel.recv())["type"], "welcome")
        await self.until(lambda: self.fields.calls >= calls + 3)             # the pusher looks while it is there
        task = self.app._pusher_task
        await panel.aclose()
        await self.until(lambda: task.done())
        calls = self.fields.calls
        await asyncio.sleep(0.2)
        self.assertEqual(self.fields.calls, calls, "the last panel left: no more looks")
        await c.aclose()
        await p.aclose()


if __name__ == "__main__":
    unittest.main()
