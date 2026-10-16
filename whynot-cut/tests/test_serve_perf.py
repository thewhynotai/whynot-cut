"""`reel serve` perf hooks and a faster first state (3.0 Addendum G2 hardening H3; budgets S1 / S2 / S3):
    * serve/perf.py appends local JSON lines {t, mark, ms?, rid?} to <home>/logs/perf.jsonl, size-capped with one
      rotated file, and never writes a token, a path or a name (marks from a fixed allowlist, every other key dropped);
    * the panel's `perf` message (session.schema.json) carries a bounded batch of panel marks; serve appends it, from a
      panel session only, rate-limited per session;
    * serve/perf_report.py computes the p95 of each budget and exits 1 on a miss;
    * the FIRST snapshot of a session waits at most FIRST_FIELDS_TIMEOUT (1 s) for the engine-state read: past it the
      last good state is served marked `stale: true`, and a panel session gets the fresh one as soon as the read
      answers;
    * serve pushes a state to the connected panel sessions when the engine state changes (serve/push.py StatePusher:
      the PanelFields cache generation, debounced), the panel's poll stays as the fallback.
Run:
    bash tools/test.sh -k test_serve_perf
Deterministic: the pusher runs on a fake clock and a fake sleep; a stuck engine-state read is a threading.Event, never a
sleep; no assertion holds a wall-clock budget.
"""
import sys as _sys
_sys.dont_write_bytecode = True  # keep the plugin folder free of __pycache__
import _isolation  # noqa: F401,E402  G79: sandbox the engine home before anything else (see tests/_isolation.py)
import asyncio
import io
import json
import shutil
import sys
import tempfile
import threading
import unittest
from pathlib import Path

SK = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SK / "engine" / "reel"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from serve import app as serve_app, messages, perf, perf_report, push  # noqa: E402
from test_serve_app import PING_READBACK, AppCase, T, command  # noqa: E402

TOKEN_LIKE = "ab" * 32
GOOD = {"client": "Dr Nour", "item": "C0239", "pipeline": [], "approval": None, "qc": []}
BLANK = {"client": "", "item": "", "pipeline": [], "approval": None, "qc": []}


def lines(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]


class Clock:
    def __init__(self, t=1_760_000_000.0):
        self.t = t

    def __call__(self):
        return self.t


# ------------------------------------------------------------------------------------------------------ perf.py
class PerfLogTests(unittest.TestCase):
    def setUp(self):
        self.home = Path(tempfile.mkdtemp(prefix="wnc-perf-"))
        self.clock = Clock()
        self.log = perf.PerfLog(self.home, clock=self.clock)

    def tearDown(self):
        shutil.rmtree(self.home, ignore_errors=True)

    def test_a_mark_is_one_json_line_in_logs_perf_jsonl(self):
        self.assertEqual(self.log.path, self.home / "logs" / "perf.jsonl")
        self.assertTrue(self.log.mark("cmd.received", rid="cmd-abc-1"))
        self.assertTrue(self.log.mark("cmd.first_progress", ms=12.345, rid="cmd-abc-1"))
        rows = lines(self.log.path)
        self.assertEqual(rows, [{"t": 1_760_000_000_000, "mark": "cmd.received", "rid": "cmd-abc-1"},
                                {"t": 1_760_000_000_000, "mark": "cmd.first_progress", "ms": 12.3, "rid": "cmd-abc-1"}])

    def test_the_serve_marks_and_the_panel_marks_are_fixed_lists(self):
        self.assertEqual(perf.SERVE_MARKS, ("cmd.received", "cmd.queued", "cmd.claimed", "cmd.first_progress",
                                            "cmd.result", "link.welcome_sent"))
        self.assertEqual(perf.PANEL_MARKS, ("panel.boot", "panel.first_paint", "link.welcome", "link.first_state",
                                            "panel.usable", "ui.click", "ui.paint"))
        from contract.validator import load
        self.assertEqual(list(perf.PANEL_MARKS), load("session")["$defs"]["perf_mark"]["properties"]["mark"]["enum"])

    def test_an_unknown_mark_is_refused_and_nothing_is_written(self):
        for bad in ("cmd.hacked", "", None, 3, "C:/Users/x", "panel.boot\n"):
            self.assertFalse(self.log.mark(bad), repr(bad))
        self.assertEqual(lines(self.log.path), [])

    def test_a_rid_that_could_hold_a_token_a_path_or_a_name_is_dropped_and_the_mark_kept(self):
        for bad in (TOKEN_LIKE, "C:/clients/Dr Nour", "..\\x", "a b", "د.نور", "x" * 49, "", ".hidden"):
            self.log.mark("cmd.received", rid=bad)
        rows = lines(self.log.path)
        self.assertEqual(len(rows), 8)
        self.assertTrue(all("rid" not in r for r in rows), rows)

    def test_a_bad_ms_is_dropped(self):
        for bad in (-1, float("nan"), float("inf"), "12", True, perf.MS_MAX + 1):
            self.log.mark("cmd.result", ms=bad)
        self.assertTrue(all("ms" not in r for r in lines(self.log.path)))

    def test_a_panel_batch_keeps_only_t_mark_ms_rid_of_the_panel_marks(self):
        n = self.log.extend([
            {"mark": "panel.usable", "t": 1_760_000_000_500, "ms": 812, "path": "D:/clients/Dr Nour",
             "client": "Dr Nour"},
            {"mark": "ui.paint", "t": 1_760_000_000_900, "ms": 7.25, "rid": "c-3", "token": TOKEN_LIKE},
            {"mark": "cmd.received", "t": 1_760_000_000_000},                 # a serve mark: not the panel's to send
            {"mark": "panel.boot", "t": "yesterday"},                         # no usable time
            {"mark": "panel.boot"},
            "panel.boot",
        ])
        self.assertEqual(n, 2)
        self.assertEqual(lines(self.log.path), [{"t": 1_760_000_000_500, "mark": "panel.usable", "ms": 812},
                                                {"t": 1_760_000_000_900, "mark": "ui.paint", "ms": 7.2, "rid": "c-3"}])
        text = self.log.path.read_text(encoding="utf-8")
        for secret in (TOKEN_LIKE, "Dr Nour", "D:/", "clients", "path", "token"):
            self.assertNotIn(secret, text)

    def test_a_batch_is_capped(self):
        many = [{"mark": "ui.click", "t": 1_760_000_000_000 + i, "rid": f"c-{i}"} for i in range(perf.BATCH_MAX + 20)]
        self.assertEqual(self.log.extend(many), perf.BATCH_MAX)

    def test_the_file_rotates_at_its_cap_and_keeps_one_older_file(self):
        log = perf.PerfLog(self.home, clock=self.clock, max_bytes=600)
        for i in range(200):
            log.mark("cmd.received", rid=f"cmd-{i}")
        old = log.path.with_name("perf.jsonl.1")
        self.assertTrue(old.exists())
        self.assertLessEqual(log.path.stat().st_size, 600)
        self.assertLessEqual(old.stat().st_size, 600)
        self.assertEqual(sorted(p.name for p in log.path.parent.iterdir()), ["perf.jsonl", "perf.jsonl.1"])
        rows = perf.read(self.home)                                       # the older file first, then the current
        self.assertEqual(rows[-1]["rid"], "cmd-199")
        rids = [int(r["rid"].split("-")[1]) for r in rows]
        self.assertEqual(rids, sorted(rids))

    def test_read_since_and_bad_lines(self):
        self.log.mark("cmd.received", rid="a")
        self.clock.t += 10
        self.log.mark("cmd.result", rid="a", ms=10)
        with open(self.log.path, "a", encoding="utf-8") as fh:
            fh.write("{broken\n[1]\n{\"t\": 1, \"mark\": \"evil\"}\n")
        self.assertEqual([r["mark"] for r in perf.read(self.home)], ["cmd.received", "cmd.result"])
        self.assertEqual([r["mark"] for r in perf.read(self.home, since_ms=1_760_000_005_000)], ["cmd.result"])

    def test_a_write_that_fails_never_raises(self):
        (self.home / "logs").write_text("a file where the folder should be", encoding="utf-8")
        with self.assertLogs("serve.perf", "WARNING") as logs:
            self.assertFalse(self.log.mark("cmd.received"))
            self.assertFalse(self.log.mark("cmd.result"))
        self.assertEqual(len(logs.output), 1, "a failing disk is logged once")


# ------------------------------------------------------------------------------------------------------ perf_report.py
def m(mark, t, ms=None, rid=None):
    out = {"t": t, "mark": mark}
    if ms is not None:
        out["ms"] = ms
    if rid is not None:
        out["rid"] = rid
    return out


class ReportMathTests(unittest.TestCase):
    def test_p95_is_the_nearest_rank(self):
        self.assertIsNone(perf_report.p95([]))
        self.assertEqual(perf_report.p95([7]), 7)
        self.assertEqual(perf_report.p95(list(range(1, 101))), 95)
        self.assertEqual(perf_report.p95(list(range(100, 0, -1))), 95)
        self.assertEqual(perf_report.p95([1] * 19 + [500]), 1)             # rank ceil(0.95 * 20) = 19
        self.assertEqual(perf_report.p95([1] * 19 + [500] * 2), 500)       # rank ceil(0.95 * 21) = 20
        self.assertEqual(perf_report.p95(list(range(1, 21))), 19)

    def test_budgets(self):
        self.assertEqual(perf_report.BUDGETS, {"S1": 1500, "S2": 100, "S3": 2000})

    def test_samples_use_ms_and_pair_by_time_or_rid_when_ms_is_missing(self):
        marks = [
            m("panel.boot", 1000), m("panel.usable", 1900, ms=900),                # S1 from ms
            m("panel.boot", 5000), m("panel.usable", 6200),                        # S1 paired with the boot before it
            m("ui.click", 7000, rid="c-1"), m("ui.paint", 7040, ms=40, rid="c-1"),
            m("ui.click", 8000, rid="c-2"), m("ui.paint", 8090, rid="c-2"),       # S2 paired by rid
            m("cmd.received", 9000, rid="r1"), m("cmd.first_progress", 9300, ms=300, rid="r1"),
            m("cmd.received", 9100, rid="r2"), m("cmd.first_progress", 9600, rid="r2"),   # S3 paired by rid
            m("cmd.first_progress", 9900, rid="lonely"),                                 # no start: not a sample
        ]
        self.assertEqual(perf_report.samples(marks), {"S1": [900, 1200], "S2": [40, 90], "S3": [300, 500]})

    def test_s1_falls_back_to_the_first_state_when_no_usable_mark_exists(self):
        marks = [m("panel.boot", 0), m("link.first_state", 700, ms=700)]
        self.assertEqual(perf_report.samples(marks)["S1"], [700])
        marks.append(m("panel.usable", 800, ms=800))
        self.assertEqual(perf_report.samples(marks)["S1"], [800])

    def test_report_rows(self):
        marks = [m("panel.usable", 1, ms=v) for v in [100] * 19 + [1600]] + [m("ui.paint", 1, ms=20)]
        rows = {r["id"]: r for r in perf_report.report(marks)}
        self.assertEqual((rows["S1"]["n"], rows["S1"]["p95_ms"], rows["S1"]["ok"]), (20, 100, True))
        marks += [m("panel.usable", 2, ms=1600)]
        rows = {r["id"]: r for r in perf_report.report(marks)}
        self.assertEqual((rows["S1"]["p95_ms"], rows["S1"]["ok"]), (1600, False))
        self.assertEqual((rows["S2"]["ok"], rows["S3"]["n"], rows["S3"]["ok"]), (True, 0, None))


class ReportMainTests(unittest.TestCase):
    def setUp(self):
        self.home = Path(tempfile.mkdtemp(prefix="wnc-perfr-"))
        self.clock = Clock(1_760_000_000.0)                                # 2025-10-09T08:53:20Z
        self.log = perf.PerfLog(self.home, clock=self.clock)

    def tearDown(self):
        shutil.rmtree(self.home, ignore_errors=True)

    def run_main(self, *argv):
        out = io.StringIO()
        code = perf_report.main(["--home", str(self.home), *argv], out=out)
        return code, out.getvalue()

    def test_within_budget_exits_0_with_a_plain_table(self):
        self.log.extend([{"mark": "panel.usable", "t": 1_760_000_000_000, "ms": 900}])
        self.log.mark("cmd.first_progress", ms=150, rid="r1")
        code, text = self.run_main()
        self.assertEqual(code, 0, text)
        for word in ("S1", "S2", "S3", "1500", "100", "2000", "900", "150", "ok", "no data"):
            self.assertIn(word, text)

    def test_a_miss_exits_1_and_says_which(self):
        self.log.mark("cmd.first_progress", ms=2500, rid="r1")
        code, text = self.run_main()
        self.assertEqual(code, 1, text)
        self.assertIn("MISS", text)
        self.assertRegex(text, r"S3[^\n]*MISS")

    def test_since_leaves_older_marks_out(self):
        self.log.mark("cmd.first_progress", ms=2500, rid="old")
        self.clock.t += 3600
        self.log.mark("cmd.first_progress", ms=120, rid="new")
        self.assertEqual(self.run_main()[0], 1)
        code, text = self.run_main("--since", "2025-10-09T09:30:00Z")
        self.assertEqual(code, 0, text)
        self.assertEqual(self.run_main("--since", "2025-10-09T09:30:00+00:00")[0], 0)

    def test_no_data_is_not_a_miss_and_a_bad_since_is_a_usage_error(self):
        self.assertEqual(self.run_main()[0], 0)
        code, text = self.run_main("--since", "last tuesday")
        self.assertEqual(code, 2, text)


# ------------------------------------------------------------------------------------------------------ contract
def perf_msg(*marks):
    return {"type": "perf", "marks": list(marks) or [{"mark": "panel.boot", "t": 1_760_000_000_000}]}


class PerfContractTests(unittest.TestCase):
    def test_a_perf_batch_is_a_client_message(self):
        self.assertIn("perf", messages.TYPES)
        self.assertIn("perf", messages.CLIENT_TYPES)
        ok = perf_msg({"mark": "panel.usable", "t": 1_760_000_000_000, "ms": 812.5},
                      {"mark": "ui.paint", "t": 1_760_000_000_100, "ms": 6, "rid": "c-12"})
        self.assertIsNone(messages.validate_message(ok))
        full = perf_msg(*[{"mark": "ui.click", "t": 1_760_000_000_000 + i} for i in range(perf.BATCH_MAX)])
        self.assertIsNone(messages.validate_message(full))

    def test_bad_batches_are_schema_errors(self):
        good = {"mark": "panel.boot", "t": 1_760_000_000_000}
        bad = [
            {"type": "perf", "marks": []},
            {"type": "perf"},
            {"type": "perf", "marks": [good] * (perf.BATCH_MAX + 1)},
            perf_msg(dict(good, mark="cmd.received")),                       # a serve mark
            perf_msg(dict(good, mark="panel.hack")),
            perf_msg(dict(good, path="D:/x")),
            perf_msg(dict(good, rid="C:/clients/x")),
            perf_msg(dict(good, rid=TOKEN_LIKE)),
            perf_msg(dict(good, ms=-1)),
            perf_msg(dict(good, ms="5")),
            perf_msg(dict(good, t="2026-10-16T10:00:00Z")),
            perf_msg({"mark": "panel.boot"}),
            dict(perf_msg(), extra=1),
        ]
        for msg in bad:
            problem = messages.validate_message(msg)
            self.assertIsNotNone(problem, msg)
            self.assertEqual(problem[0], "schema", msg)

    def test_state_may_say_stale_and_welcome_names_its_features(self):
        st = messages.state("offline", None, "s-1", GOOD)
        self.assertIsNone(messages.validate_message(st))
        st["state"]["stale"] = True
        self.assertIsNone(messages.validate_message(st))
        st["state"]["stale"] = "yes"
        self.assertIsNotNone(messages.validate_message(st))
        w = messages.welcome("s-1", "3.0.0", "ok")
        self.assertEqual(w["features"], ["perf", "push"])
        self.assertIsNone(messages.validate_message(w))
        self.assertIsNotNone(messages.validate_message(dict(w, features=["teleport"])))


# ------------------------------------------------------------------------------------------------------ app: perf
class AppPerfTests(AppCase):
    async def panel_session(self):
        c = await self.hello(kind="panel")
        w = await c.recv()
        self.assertEqual(w["type"], "welcome", w)
        return c, w

    async def sync(self, c, sid="sync"):
        """A snapshot round trip: every message sent before it has been dispatched."""
        await c.send({"type": "snapshot", "id": sid})
        return await c.recv_type("state")

    async def test_welcome_advertises_perf_and_push(self):
        _, w = await self.panel_session()
        self.assertEqual(w["features"], ["perf", "push"])

    async def test_a_panel_batch_is_appended(self):
        c, _ = await self.panel_session()
        await c.send(perf_msg({"mark": "panel.boot", "t": 1_760_000_000_000},
                              {"mark": "panel.usable", "t": 1_760_000_000_800, "ms": 800}))
        await self.sync(c)
        rows = [r for r in lines(perf.perf_path(self.home)) if r["mark"].startswith("panel.")]
        self.assertEqual(rows, [{"t": 1_760_000_000_000, "mark": "panel.boot"},
                                {"t": 1_760_000_000_800, "mark": "panel.usable", "ms": 800}])

    async def test_perf_from_a_session_that_is_not_the_panel_is_refused(self):
        c = await self.cli()
        await c.send(perf_msg())
        err = await c.recv()
        self.assertEqual((err["type"], err["code"]), ("error", "schema"), err)
        self.assertIn("panel", err["message"])
        self.assertFalse([r for r in lines(perf.perf_path(self.home)) if r["mark"].startswith("panel.")])

    async def test_perf_batches_are_rate_limited_per_session_and_dropped_silently(self):
        rate, burst = serve_app.PERF_RATE
        c, _ = await self.panel_session()
        for i in range(burst + 5):
            await c.send(perf_msg({"mark": "ui.click", "t": 1_760_000_000_000 + i, "rid": f"c-{i}"}))
        st = await self.sync(c)                         # the next message is the snapshot's answer: no error was sent
        self.assertEqual(st.get("id"), "sync")
        clicks = [r for r in lines(perf.perf_path(self.home)) if r["mark"] == "ui.click"]
        self.assertGreaterEqual(len(clicks), burst)
        self.assertLess(len(clicks), burst + 5)
        self.assertEqual(len([r for r in self.events("rate") if r.get("action") == "perf"]), 1, "audited once")

    async def test_serve_marks_a_command_and_the_welcome(self):
        p = await self.panel(caps=("ping",))
        c = await self.cli()
        msg = command("ping", id="cmd-perf-1")
        await c.send(msg)
        await p.recv()
        await p.send({"type": "progress", "progress": {"event": "progress", "id": "cmd-perf-1", "action": "ping",
                                                        "step": "looking", "n": 1, "of": 2}})
        await p.send({"type": "progress", "progress": {"event": "progress", "id": "cmd-perf-1", "action": "ping",
                                                        "step": "looking", "n": 2, "of": 2}})
        await p.send({"type": "result", "result": {"ok": True, "action": "ping", "id": "cmd-perf-1",
                                                   "readback": PING_READBACK}})
        self.assertEqual((await c.recv_type("result"))["type"], "result")
        rows = lines(perf.perf_path(self.home))
        cmd = [r for r in rows if r.get("rid") == "cmd-perf-1"]
        self.assertEqual([r["mark"] for r in cmd], ["cmd.received", "cmd.first_progress", "cmd.result"])
        self.assertTrue(all(isinstance(r.get("ms", 0), (int, float)) for r in cmd))
        self.assertIn("ms", cmd[1])
        self.assertIn("ms", cmd[2])
        self.assertEqual(len([r for r in rows if r["mark"] == "link.welcome_sent"]), 2)
        text = perf.perf_path(self.home).read_text(encoding="utf-8")
        self.assertNotIn(self.token, text)
        self.assertNotIn(str(self.home), text)


# ------------------------------------------------------------------------------------------------------ first snapshot
class FirstSnapshotTests(AppCase):
    def test_the_first_snapshot_waits_1_s_not_3(self):
        self.assertEqual(serve_app.FIRST_FIELDS_TIMEOUT, 1.0)
        self.assertEqual(serve_app.FIELDS_TIMEOUT, 3.0)
        self.assertLess(serve_app.FIRST_FIELDS_TIMEOUT, perf_report.BUDGETS["S1"] / 1000)

    async def stuck_app(self, first_timeout=0.05):
        """The app with a read that answers only when `release` is set (a dead share, then a recovered one)."""
        self.app.fields_timeout = 3.0
        self.app.first_fields_timeout = first_timeout
        self.app._last_fields = dict(GOOD, item="C0001")                 # the last good read
        release, started = threading.Event(), threading.Event()

        def stuck(home):
            started.set()
            release.wait(T)
            return dict(GOOD)
        self.app._fields = stuck
        return release, started

    async def test_a_stuck_read_serves_the_last_good_state_at_once_marked_stale_then_the_fresh_one(self):
        release, started = await self.stuck_app()
        try:
            c = await self.hello(kind="panel")
            self.assertEqual((await c.recv())["type"], "welcome")
            await c.send({"type": "snapshot", "id": "first"})
            st = await c.recv()
            self.assertEqual((st["type"], st.get("id")), ("state", "first"), st)
            self.assertTrue(started.is_set())
            self.assertFalse(release.is_set(), "answered while the read was still stuck")
            self.assertIs(st["state"]["stale"], True)
            self.assertEqual(st["state"]["item"], "C0001", "the last good item")
            release.set()                                                 # the read answers: the fresh state follows
            fresh = await c.recv()
            self.assertEqual(fresh["type"], "state", fresh)
            self.assertNotIn("id", fresh)
            self.assertNotIn("stale", fresh["state"])
            self.assertEqual(fresh["state"]["item"], "C0239")
        finally:
            release.set()

    async def test_without_a_last_good_read_the_stale_state_has_no_item(self):
        release, _ = await self.stuck_app()
        self.app._last_fields = None
        try:
            c = await self.cli()
            await c.send({"type": "snapshot", "id": "first"})
            st = (await c.recv())["state"]
            self.assertEqual((st["item"], st["stale"]), ("", True))
        finally:
            release.set()

    async def test_only_a_panel_gets_the_fresh_follow_up(self):
        release, _ = await self.stuck_app()
        try:
            c = await self.cli()
            await c.send({"type": "snapshot", "id": "first"})
            self.assertIs((await c.recv())["state"]["stale"], True)
            release.set()
            for _ in range(200):                                          # until the read answered
                if self.app._fields_running is not None and self.app._fields_running.done():
                    break
                await asyncio.sleep(0.01)
            await c.send({"type": "snapshot", "id": "second"})
            st = await c.recv()
            self.assertEqual(st.get("id"), "second", "no unsolicited state for the CLI")
            self.assertNotIn("stale", st["state"])
        finally:
            release.set()

    async def test_a_later_snapshot_keeps_the_3_s_read_and_a_fast_first_read_is_not_stale(self):
        self.app.first_fields_timeout = 1.0
        self.app._fields = lambda home: dict(GOOD)
        c = await self.cli()
        await c.send({"type": "snapshot", "id": "a"})
        st = (await c.recv())["state"]
        self.assertEqual(st["item"], "C0239")
        self.assertNotIn("stale", st)


# ------------------------------------------------------------------------------------------------------ push
class FakeSleep:
    """asyncio.sleep stand-in: advances the fake clock and runs `on_sleep` (the outside world changing meanwhile)."""

    def __init__(self, clock: Clock, on_sleep=None):
        self.clock, self.on_sleep, self.calls = clock, on_sleep, []

    async def __call__(self, s):
        self.calls.append(s)
        self.clock.t += s
        if self.on_sleep is not None:
            self.on_sleep()
        await asyncio.sleep(0)


class PusherTests(unittest.IsolatedAsyncioTestCase):
    def make(self, states, **kw):
        """A pusher whose probe returns the next of `states` on each call (the last one repeats)."""
        self.clock = Clock(0.0)
        self.sleep = FakeSleep(self.clock)
        self.probes, self.published = 0, []
        seq = list(states)

        async def probe():
            self.probes += 1
            v = seq.pop(0) if len(seq) > 1 else seq[0]
            return v, {"value": v}

        async def publish(fp, payload):
            self.published.append((fp, payload["value"]))
        opts = {"interval": 1.0, "debounce": 0.25, "debounce_max": 1.0, "sleep": self.sleep, "clock": self.clock, **kw}
        return push.StatePusher(probe, publish, **opts)

    async def test_the_first_look_is_the_baseline_and_an_unchanged_state_is_not_pushed(self):
        p = self.make(["a", "a", "a"])
        self.assertFalse(await p.tick())
        self.assertFalse(await p.tick())
        self.assertEqual(self.published, [])

    async def test_a_change_is_pushed_once(self):
        p = self.make(["a", "b", "b", "b"])
        self.assertFalse(await p.tick())
        self.assertTrue(await p.tick())                  # b, then one debounce look: still b
        self.assertFalse(await p.tick())
        self.assertEqual(self.published, [("b", "b")])
        self.assertEqual(self.sleep.calls, [0.25])

    async def test_a_burst_of_changes_is_one_push_of_the_last_state(self):
        p = self.make(["a", "b", "c", "d", "d", "d"])
        await p.tick()
        self.assertTrue(await p.tick())
        self.assertEqual(self.published, [("d", "d")])
        self.assertEqual(self.sleep.calls, [0.25, 0.25, 0.25])

    async def test_a_state_that_never_settles_is_pushed_after_debounce_max(self):
        p = self.make([str(i) for i in range(50)])
        await p.tick()
        self.assertTrue(await p.tick())
        self.assertEqual(len(self.published), 1)
        self.assertLessEqual(sum(self.sleep.calls), 1.0)
        self.assertEqual(len(self.sleep.calls), 4)

    async def test_run_looks_every_interval_while_active(self):
        p = self.make(["a", "a", "b", "b", "b"], debounce=0.0)
        n = {"left": 10}

        def active():
            n["left"] -= 1
            return n["left"] >= 0
        await p.run(active)
        self.assertEqual(self.published, [("b", "b")])
        self.assertIn(1.0, self.sleep.calls)

    async def test_a_failing_probe_or_publish_does_not_end_the_loop(self):
        p = self.make(["a"])
        calls = {"n": 0}

        async def bad_probe():
            calls["n"] += 1
            raise OSError("share gone")
        p.probe = bad_probe
        with self.assertLogs("serve.push", "WARNING") as logs:
            self.assertFalse(await p.tick())
            self.assertFalse(await p.tick())
        self.assertEqual(len(logs.output), 1, "logged once")


class FakeFields:
    """PanelFields' interface: called with the home; with_generation hands the fields and their cache generation over
    together (taken under one lock, like PanelFields)."""

    def __init__(self):
        self.value, self.generation, self.calls = dict(BLANK), 0, 0
        self.lock = threading.Lock()

    def __call__(self, home):
        return self.with_generation(home)[0]

    def with_generation(self, home):
        with self.lock:
            self.calls += 1
            return dict(self.value), self.generation

    def set(self, **kw):
        with self.lock:
            self.value = dict(self.value, **kw)
            self.generation += 1


class AppPushTests(AppCase):
    app_options = {"push_interval": 0.01, "push_debounce": 0.0}

    async def asyncSetUp(self):
        await super().asyncSetUp()
        self.fields = FakeFields()
        self.app._fields = self.fields

    async def panel_session(self):
        c = await self.hello(kind="panel")
        self.assertEqual((await c.recv())["type"], "welcome")
        return c

    async def until(self, cond):
        for _ in range(500):
            if cond():
                return
            await asyncio.sleep(0.01)
        self.fail("condition not met")

    async def test_a_changed_engine_state_reaches_the_panel_without_a_snapshot(self):
        c = await self.panel_session()
        cli = await self.cli()
        await self.until(lambda: self.fields.calls >= 2)                   # the pusher has its baseline
        self.fields.set(client="Dr Nour", item="C0239")
        st = await c.recv()
        self.assertEqual(st["type"], "state", st)
        self.assertNotIn("id", st)
        self.assertEqual((st["state"]["client"], st["state"]["item"]), ("Dr Nour", "C0239"))
        await cli.send({"type": "snapshot", "id": "cli-1"})
        self.assertEqual((await cli.recv()).get("id"), "cli-1", "the CLI gets no push")

    async def test_one_push_per_change_and_none_for_a_state_the_panel_already_has(self):
        c = await self.panel_session()
        await self.until(lambda: self.fields.calls >= 2)
        self.fields.set(item="C0239")
        self.assertEqual((await c.recv())["state"]["item"], "C0239")
        calls = self.fields.calls
        await self.until(lambda: self.fields.calls >= calls + 5)            # several more looks: nothing changed
        await c.send({"type": "snapshot", "id": "s1"})
        self.assertEqual((await c.recv()).get("id"), "s1", "no second push of the same state")
        self.fields.set(item="C0240")
        st = await c.recv()
        self.assertEqual((st.get("id"), st["state"]["item"]), (None, "C0240"))

    async def test_a_job_change_is_pushed_too(self):
        c = await self.panel_session()
        p = await self.panel(caps=("ping",))
        await self.until(lambda: self.fields.calls >= 2)
        cli = await self.cli()
        await cli.send(command("ping", id="cmd-push-1"))
        await p.recv()
        for _ in range(20):                                               # (p connecting is a host change too)
            st = await c.recv_type("state")
            if "cmd-push-1" in [j["request_id"] for j in st["state"].get("jobs", [])]:
                break
        else:
            self.fail("the new job was never pushed")
        self.assertNotIn("id", st)
        await p.send({"type": "result", "result": {"ok": True, "action": "ping", "id": "cmd-push-1",
                                                   "readback": PING_READBACK}})
        await cli.recv_type("result")

    async def test_the_pusher_stops_with_the_last_panel_and_on_close(self):
        c = await self.panel_session()
        await self.until(lambda: self.app._pusher_task is not None)
        task = self.app._pusher_task
        await c.aclose()
        await self.until(lambda: task.done())
        c2 = await self.panel_session()
        await self.until(lambda: self.app._pusher_task is not None and not self.app._pusher_task.done())
        await self.app.close()
        self.assertTrue(self.app._pusher_task is None or self.app._pusher_task.done())
        await c2.aclose()


class NoPushTests(AppCase):
    app_options = {"push_interval": None}

    async def test_push_can_be_switched_off(self):
        c = await self.hello(kind="panel")
        self.assertEqual((await c.recv())["type"], "welcome")
        self.assertIsNone(self.app._pusher_task)


if __name__ == "__main__":
    unittest.main()
