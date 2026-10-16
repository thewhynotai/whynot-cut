"""`reel serve` perf hooks and a faster first state (3.0 Addendum G2 hardening H3; budgets S1 / S2 / S3):
    * serve/perf.py appends local JSON lines {t, mark, ms?, rid?, s?} to <home>/logs/perf.jsonl from one background
      writer thread (bounded queue, drop on overflow), size-capped with one rotated file, and never writes a token, a
      path or a name: marks from a fixed allowlist, every other key dropped, a rid only as a salted per-run hash;
    * the panel's `perf` message (session.schema.json) carries a bounded batch of panel marks; serve appends it with the
      session's tag, from a panel session only, rate-limited per session;
    * serve/perf_report.py computes the p95 of each budget (pairs within one session, never a negative sample) and
      exits 1 on a miss, 3 on an internal error;
    * the FIRST snapshot of a session waits at most FIRST_FIELDS_TIMEOUT (1 s) for the engine-state read: past it the
      last good state is served marked `stale: true`, and a panel session gets the fresh one as soon as the read
      answers;
    * serve pushes a state to every welcomed panel session whose last state differs from the current one (serve/push.py
      StatePusher: the PanelFields cache generation, the host, the jobs and `stale`, debounced); the panel's poll stays
      as the fallback.
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
import re
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

from serve import app as serve_app, messages, perf, perf_report, push  # noqa: E402
from test_serve_app import PING_READBACK, AppCase, T, command  # noqa: E402

TOKEN_LIKE = "ab" * 32
GOOD = {"client": "Dr Nour", "item": "C0239", "pipeline": [], "approval": None, "qc": []}
BLANK = {"client": "", "item": "", "pipeline": [], "approval": None, "qc": []}
HASH_RE = re.compile(r"[0-9a-f]{12}")


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
        self.log = self.make()

    def make(self, **kw):
        log = perf.PerfLog(self.home, clock=self.clock, **kw)
        self.addCleanup(log.close, 2.0)
        return log

    def tearDown(self):
        self.log.close(2.0)
        shutil.rmtree(self.home, ignore_errors=True)

    def rows(self, log=None):
        log = log or self.log
        self.assertTrue(log.flush(T), "the writer flushed")
        return lines(log.path)

    def test_a_mark_is_one_json_line_in_logs_perf_jsonl(self):
        self.assertEqual(self.log.path, self.home / "logs" / "perf.jsonl")
        self.assertTrue(self.log.mark("cmd.received", rid="cmd-abc-1"))
        self.assertTrue(self.log.mark("cmd.first_progress", ms=12.345, rid="cmd-abc-1"))
        h = self.log.rid("cmd-abc-1")
        self.assertRegex(h, HASH_RE)
        self.assertEqual(self.rows(), [{"t": 1_760_000_000_000, "mark": "cmd.received", "rid": h},
                                       {"t": 1_760_000_000_000, "mark": "cmd.first_progress", "ms": 12.3, "rid": h}])

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
        self.assertEqual(self.rows(), [])

    def test_a_rid_that_could_hold_a_token_a_path_or_a_name_is_dropped_and_the_mark_kept(self):
        for bad in ("C:/clients/Dr Nour", "..\\x", "a b", "د.نور", "x" * 65, "", ".hidden"):
            self.log.mark("cmd.received", rid=bad)
        rows = self.rows()
        self.assertEqual(len(rows), 7)
        self.assertTrue(all("rid" not in r for r in rows), rows)

    def test_a_rid_is_written_only_as_a_salted_hash_of_this_run(self):
        """Review P2-7: a CLI id such as DrNour-reel3, or the first 48 characters of the token, is an id in shape; the
        file never holds it, only a 12-hex HMAC under a salt made for this daemon run (pairing still works in a run)."""
        for raw in ("DrNour-reel3", TOKEN_LIKE[:48], TOKEN_LIKE):
            self.log.mark("cmd.received", rid=raw)
        rows = self.rows()
        text = self.log.path.read_text(encoding="utf-8")
        for raw in ("DrNour", "reel3", TOKEN_LIKE[:12]):
            self.assertNotIn(raw, text)
        self.assertTrue(all(HASH_RE.fullmatch(r["rid"]) for r in rows), rows)
        self.assertEqual(rows[0]["rid"], self.log.rid("DrNour-reel3"))
        other = self.make()
        self.assertNotEqual(other.rid("DrNour-reel3"), self.log.rid("DrNour-reel3"), "a new run, a new salt")

    def test_a_bad_ms_is_dropped(self):
        for bad in (-1, float("nan"), float("inf"), "12", True, perf.MS_MAX + 1, 10 ** 400):
            self.log.mark("cmd.result", ms=bad)
        self.assertTrue(all("ms" not in r for r in self.rows()))

    def test_a_huge_number_is_dropped_never_an_overflow(self):
        """Review P2-4: math.isfinite(10 ** 400) raises OverflowError; such a t or ms is just not usable."""
        self.assertIsNone(perf.clean({"mark": "panel.boot", "t": 10 ** 400}))
        self.assertEqual(perf.clean({"mark": "panel.boot", "t": 5, "ms": 10 ** 400}), {"t": 5, "mark": "panel.boot"})
        self.assertEqual(self.log.extend([{"mark": "panel.boot", "t": 10 ** 400}]), 0)
        self.log.path.parent.mkdir(parents=True, exist_ok=True)
        self.log.path.write_text('{"t": %s, "mark": "panel.boot"}\n{"t": 7, "mark": "panel.boot"}\n' % ("9" * 400),
                                 encoding="utf-8")
        self.assertEqual(perf.read(self.home), [{"t": 7, "mark": "panel.boot"}])

    def test_a_panel_batch_keeps_only_t_mark_ms_rid_and_the_session_tag(self):
        tag = self.log.new_session()
        self.assertRegex(tag, r"^[0-9a-f]{6}-[0-9]+$")
        self.assertNotEqual(tag, self.log.new_session())
        n = self.log.extend([
            {"mark": "panel.usable", "t": 1_760_000_000_500, "ms": 812, "path": "D:/clients/Dr Nour",
             "client": "Dr Nour"},
            {"mark": "ui.paint", "t": 1_760_000_000_900, "ms": 7.25, "rid": "c-3", "token": TOKEN_LIKE},
            {"mark": "cmd.received", "t": 1_760_000_000_000},                 # a serve mark: not the panel's to send
            {"mark": "panel.boot", "t": "yesterday"},                         # no usable time
            {"mark": "panel.boot"},
            "panel.boot",
        ], session=tag)
        self.assertEqual(n, 2)
        self.assertEqual(self.rows(), [
            {"t": 1_760_000_000_500, "mark": "panel.usable", "ms": 812, "s": tag},
            {"t": 1_760_000_000_900, "mark": "ui.paint", "ms": 7.2, "rid": self.log.rid("c-3"), "s": tag}])
        text = self.log.path.read_text(encoding="utf-8")
        for secret in (TOKEN_LIKE, "Dr Nour", "D:/", "clients", "path", "token"):
            self.assertNotIn(secret, text)

    def test_a_batch_is_capped(self):
        many = [{"mark": "ui.click", "t": 1_760_000_000_000 + i, "rid": f"c-{i}"} for i in range(perf.BATCH_MAX + 20)]
        self.assertEqual(self.log.extend(many), perf.BATCH_MAX)

    def test_writes_happen_on_the_writer_thread_never_the_caller(self):
        """Review P2-5: a mark from the event loop never touches the disk on the loop's thread."""
        threads = []
        real = perf.PerfLog._append

        def spy(this, raw):
            threads.append(threading.current_thread().name)
            return real(this, raw)
        with mock.patch.object(perf.PerfLog, "_append", spy):
            self.log.mark("cmd.received")
            self.log.extend([{"mark": "panel.boot", "t": 5}])
            self.assertTrue(self.log.flush(T))
        self.assertTrue(threads)
        self.assertNotIn(threading.current_thread().name, threads)
        self.assertTrue(all(n == "reel-serve-perf" for n in threads), threads)

    def test_the_queue_is_bounded_and_drops_on_overflow(self):
        gate = threading.Event()
        real = perf.PerfLog._append

        def slow(this, raw):
            gate.wait(T)
            return real(this, raw)
        log = self.make(queue_max=3)
        with mock.patch.object(perf.PerfLog, "_append", slow):
            results = [log.mark("cmd.received", rid=f"r{i}") for i in range(12)]
            self.assertIn(False, results, "a full queue drops, never blocks")
            self.assertEqual(log.dropped, results.count(False))
            gate.set()
            self.assertTrue(log.flush(T))
        self.assertEqual(len(lines(log.path)), results.count(True))

    def test_close_writes_what_is_queued(self):
        for i in range(20):
            self.log.mark("cmd.received", rid=f"r{i}")
        self.log.close(T)
        self.assertEqual(len(lines(self.log.path)), 20)
        self.assertFalse(self.log.mark("cmd.result"), "a closed log takes nothing")

    def test_the_file_rotates_at_its_cap_and_keeps_one_older_file(self):
        log = self.make(max_bytes=600)
        for i in range(200):
            log.mark("cmd.received", rid=f"cmd-{i}")
        self.assertTrue(log.flush(T))
        old = log.path.with_name("perf.jsonl.1")
        self.assertTrue(old.exists())
        self.assertLessEqual(log.path.stat().st_size, 600)
        self.assertLessEqual(old.stat().st_size, 600)
        self.assertEqual(sorted(p.name for p in log.path.parent.iterdir()), ["perf.jsonl", "perf.jsonl.1"])
        order = {log.rid(f"cmd-{i}"): i for i in range(200)}
        rows = perf.read(self.home)                                       # the older file first, then the current
        self.assertEqual(order[rows[-1]["rid"]], 199)
        seq = [order[r["rid"]] for r in rows]
        self.assertEqual(seq, sorted(seq))

    def test_a_rotation_refused_by_windows_still_appends_up_to_twice_the_cap(self):
        """Review P2-6: os.replace fails with WinError 32 while a reader or the antivirus holds the file. The append
        goes on until the file is twice the cap; a failure is logged once per failing episode (a good write ends it)."""
        mono = Clock(100.0)
        log = self.make(max_bytes=600, mono=mono)
        with mock.patch.object(perf.os, "replace", side_effect=PermissionError(32, "in use")) as refused, \
                self.assertLogs("serve.perf", "WARNING") as logs:
            for i in range(60):
                log.mark("cmd.received", rid=f"r{i}")
            self.assertTrue(log.flush(T))
        size = log.path.stat().st_size
        self.assertGreater(size, 600, "appended past the cap while the rotation was refused")
        self.assertLessEqual(size, 1200)
        self.assertFalse(log.path.with_name("perf.jsonl.1").exists())
        self.assertEqual(len(logs.output), 1, logs.output)
        self.assertEqual(refused.call_count, 1, "re-review 3: one rename attempt per back-off window, not per line")
        log.mark("cmd.result")                                            # within the window: not tried again
        self.assertTrue(log.flush(T))
        self.assertFalse(log.path.with_name("perf.jsonl.1").exists())
        mono.t += perf.RENAME_RETRY_S                                     # the window is over: the rotation works
        log.mark("cmd.result")
        self.assertTrue(log.flush(T))
        self.assertTrue(log.path.with_name("perf.jsonl.1").exists())
        with mock.patch.object(perf.os, "replace", side_effect=PermissionError(32, "in use")), \
                self.assertLogs("serve.perf", "WARNING") as again:
            for i in range(60):
                log.mark("cmd.received", rid=f"q{i}")
            self.assertTrue(log.flush(T))
        self.assertEqual(len(again.output), 1, "a new failing episode is logged again")

    def test_close_keeps_to_one_deadline(self):
        """Re-review 2: close(timeout) spends at most `timeout` in all: the wait to queue the stop and the join share
        one deadline (it was the full timeout for each)."""
        mono = Clock(0.0)
        log = self.make(mono=mono)
        log.mark("cmd.received")                                          # the writer thread is running
        self.assertTrue(log.flush(T))
        puts, joins = [], []

        def slow_put(item, block=True, timeout=None):
            puts.append(timeout)
            mono.t += 0.15                                                # the queue was full for 0.15 s
        try:
            with mock.patch.object(log._q, "put", slow_put), \
                    mock.patch.object(log._thread, "join", lambda timeout=None: joins.append(timeout)):
                log.close(0.2)
            self.assertEqual((len(puts), len(joins)), (1, 1))
            self.assertAlmostEqual(puts[0], 0.2)
            self.assertLessEqual(joins[0], 0.05 + 1e-9, "the join gets what is left of the one deadline")
        finally:
            log._q.put_nowait(perf._STOP)

    def test_read_since_and_bad_lines(self):
        self.log.mark("cmd.received", rid="a")
        self.clock.t += 10
        self.log.mark("cmd.result", rid="a", ms=10)
        self.assertTrue(self.log.flush(T))
        with open(self.log.path, "a", encoding="utf-8") as fh:
            fh.write("{broken\n[1]\n{\"t\": 1, \"mark\": \"evil\"}\n")
        self.assertEqual([r["mark"] for r in perf.read(self.home)], ["cmd.received", "cmd.result"])
        self.assertEqual([r["mark"] for r in perf.read(self.home, since_ms=1_760_000_005_000)], ["cmd.result"])

    def test_a_write_that_fails_never_raises(self):
        (self.home / "logs").write_text("a file where the folder should be", encoding="utf-8")
        with self.assertLogs("serve.perf", "WARNING") as logs:
            self.log.mark("cmd.received")
            self.log.mark("cmd.result")
            self.assertTrue(self.log.flush(T))
        self.assertEqual(len(logs.output), 1, "a failing disk is logged once")


# ------------------------------------------------------------------------------------------------------ perf_report.py
def m(mark, t, ms=None, rid=None, s=None):
    out = {"t": t, "mark": mark}
    if ms is not None:
        out["ms"] = ms
    if rid is not None:
        out["rid"] = rid
    if s is not None:
        out["s"] = s
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

    def test_samples_use_ms_and_pair_within_one_session_or_rid_when_ms_is_missing(self):
        marks = [
            m("panel.boot", 1000, s="a-1"), m("panel.usable", 1900, ms=900, s="a-1"),   # S1 from ms
            m("panel.boot", 5000, s="a-2"), m("panel.usable", 6200, s="a-2"),           # paired with its own boot
            m("ui.click", 7000, rid="c1", s="a-2"), m("ui.paint", 7040, ms=40, rid="c1", s="a-2"),
            m("ui.click", 8000, rid="c2", s="a-2"), m("ui.paint", 8090, rid="c2", s="a-2"),   # S2 by rid
            m("cmd.received", 9000, rid="r1"), m("cmd.first_progress", 9300, ms=300, rid="r1"),
            m("cmd.received", 9100, rid="r2"), m("cmd.first_progress", 9600, rid="r2"),     # S3 by rid
            m("cmd.first_progress", 9900, rid="lonely"),                                     # no start: not a sample
        ]
        self.assertEqual(perf_report.samples(marks), {"S1": [900, 1200], "S2": [40, 90], "S3": [300, 500]})

    def test_two_panels_are_never_mixed_and_a_negative_sample_is_dropped(self):
        """Review P2-8: a boot of one panel never closes another's usable mark; a pairing that comes out negative (a
        clock step) is no sample."""
        marks = [
            m("panel.boot", 1000, s="a-1"), m("panel.boot", 5000, s="a-2"),
            m("panel.usable", 5500, s="a-1"),                       # a-1's own boot: 4500, never 500 from a-2
            m("panel.usable", 6000),                                # no session, no ms: no pairing at all
            m("ui.click", 9000, rid="c1", s="a-2"), m("ui.paint", 8000, rid="c1", s="a-2"),   # negative
            m("ui.click", 7000, rid="c9", s="a-1"), m("ui.paint", 7020, rid="c9", s="a-2"),   # another panel's c9
            m("ui.paint", 1, ms=-5, rid="c3", s="a-1"),
        ]
        self.assertEqual(perf_report.samples(marks), {"S1": [4500], "S2": [], "S3": []})

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
        self.log.close(2.0)
        shutil.rmtree(self.home, ignore_errors=True)

    def run_main(self, *argv):
        self.assertTrue(self.log.flush(T))
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

    def test_an_internal_error_is_exit_3_never_a_miss(self):
        """Review P2-4: a crash must not read as a budget miss (1)."""
        with mock.patch.object(perf_report.perf, "read", side_effect=RuntimeError("boom")):
            code, text = self.run_main()
        self.assertEqual(code, 3, text)
        self.assertIn("internal error", text)
        self.log.path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.log.path, "a", encoding="utf-8") as fh:            # a 400-digit time: skipped, not a crash
            fh.write('{"t": %s, "mark": "cmd.first_progress", "ms": 5}\n' % ("9" * 400))
        self.assertEqual(self.run_main()[0], 0)

    def test_an_engine_home_that_cannot_be_found_is_exit_3_not_a_traceback(self):
        """Executor review P2: with no --home, an OSError while finding the engine home is an internal error (3)."""
        from lib import plat
        out = io.StringIO()
        with mock.patch.object(plat, "engine_home", side_effect=OSError("no home")):
            code = perf_report.main([], out=out)
        self.assertEqual(code, 3, out.getvalue())
        self.assertIn("internal error", out.getvalue())


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
            perf_msg(dict(good, s="a-1")),                                   # the daemon tags sessions, not the panel
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
        """A snapshot round trip: every message sent before it has been dispatched; then the writer is flushed."""
        await c.send({"type": "snapshot", "id": sid})
        st = await c.recv_type("state")
        self.assertTrue(self.app.perf.flush(T))
        return st

    async def test_welcome_advertises_perf_and_push(self):
        _, w = await self.panel_session()
        self.assertEqual(w["features"], ["perf", "push"])

    async def test_a_panel_batch_is_appended_with_its_session_tag(self):
        c, _ = await self.panel_session()
        c2, _ = await self.panel_session()
        await c.send(perf_msg({"mark": "panel.boot", "t": 1_760_000_000_000},
                              {"mark": "panel.usable", "t": 1_760_000_000_800, "ms": 800}))
        await c2.send(perf_msg({"mark": "panel.boot", "t": 1_760_000_000_100}))
        await self.sync(c)
        await self.sync(c2)
        rows = [r for r in lines(perf.perf_path(self.home)) if r["mark"].startswith("panel.")]
        self.assertEqual([{k: v for k, v in r.items() if k != "s"} for r in rows],
                         [{"t": 1_760_000_000_000, "mark": "panel.boot"},
                          {"t": 1_760_000_000_800, "mark": "panel.usable", "ms": 800},
                          {"t": 1_760_000_000_100, "mark": "panel.boot"}])
        self.assertEqual(rows[0]["s"], rows[1]["s"])
        self.assertNotEqual(rows[0]["s"], rows[2]["s"], "each session its own tag")

    async def test_perf_from_a_session_that_is_not_the_panel_is_refused(self):
        c = await self.cli()
        await c.send(perf_msg())
        err = await c.recv()
        self.assertEqual((err["type"], err["code"]), ("error", "schema"), err)
        self.assertIn("panel", err["message"])
        self.assertTrue(self.app.perf.flush(T))
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
        self.assertTrue(self.app.perf.flush(T))
        rows = lines(perf.perf_path(self.home))
        cmd = [r for r in rows if r.get("rid") == self.app.perf.rid("cmd-perf-1")]
        self.assertEqual([r["mark"] for r in cmd], ["cmd.received", "cmd.first_progress", "cmd.result"])
        self.assertIn("ms", cmd[1])
        self.assertIn("ms", cmd[2])
        self.assertEqual(len([r for r in rows if r["mark"] == "link.welcome_sent"]), 2)
        text = perf.perf_path(self.home).read_text(encoding="utf-8")
        for secret in (self.token, str(self.home), "cmd-perf-1"):
            self.assertNotIn(secret, text)

    async def test_close_flushes_the_perf_writer(self):
        c, _ = await self.panel_session()
        await c.send(perf_msg({"mark": "panel.boot", "t": 1_760_000_000_000}))
        await c.send({"type": "snapshot", "id": "x"})
        await c.recv_type("state")
        await self.app.close()
        self.assertIn("panel.boot", [r["mark"] for r in lines(perf.perf_path(self.home))])
        self.assertFalse(self.app.perf.mark("cmd.result"), "closed with the app")


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
    """asyncio.sleep stand-in: advances the fake clock."""

    def __init__(self, clock: Clock):
        self.clock, self.calls = clock, []

    async def __call__(self, s):
        self.calls.append(s)
        self.clock.t += s
        await asyncio.sleep(0)


class PusherTests(unittest.IsolatedAsyncioTestCase):
    """StatePusher alone: `probe` gives the next look (fingerprint, payload, stale), `has` is what each panel was last
    sent; publish sends to every panel whose last state differs and says how many got it."""

    def make(self, looks, panels=("p",), **kw):
        self.clock = Clock(0.0)
        self.sleep = FakeSleep(self.clock)
        self.published = []
        self.has = {p: "a" for p in panels}                    # each panel was last sent "a"
        self.fail_sends = False
        seq = [x if isinstance(x, tuple) else (x, False) for x in looks]

        async def probe():
            fp, stale = seq.pop(0) if len(seq) > 1 else seq[0]
            return fp, {"value": fp}, stale

        async def publish(fp, payload, stale):
            sent = 0
            for p, last in self.has.items():
                if last != fp and not self.fail_sends:
                    self.has[p] = fp
                    sent += 1
            if sent:
                self.published.append(payload["value"])
            return sent

        def behind(fp):
            return any(last != fp for last in self.has.values())
        opts = {"interval": 1.0, "debounce": 0.25, "debounce_max": 1.0, "sleep": self.sleep, "clock": self.clock, **kw}
        return push.StatePusher(probe, publish, behind, **opts)

    async def test_nothing_is_sent_while_every_panel_has_the_state(self):
        p = self.make(["a", "a", "a"])
        self.assertFalse(await p.tick())
        self.assertFalse(await p.tick())
        self.assertEqual((self.published, self.sleep.calls), ([], []))

    async def test_a_change_is_pushed_once_after_it_settles(self):
        p = self.make(["a", "b", "b", "b"])
        self.assertFalse(await p.tick())
        self.assertTrue(await p.tick())                  # b, then one debounce look: still b
        self.assertFalse(await p.tick())
        self.assertEqual(self.published, ["b"])
        self.assertEqual(self.sleep.calls, [0.25])

    async def test_a_panel_that_fell_behind_is_caught_up_without_any_change(self):
        """Review P1-1: one server-wide `last` never re-sent a state a panel missed (a failed send, a stale first
        snapshot that outlived the read, an answer sent after a newer push)."""
        p = self.make(["b", "b", "b", "b"])
        self.has["p"] = "b"
        self.assertFalse(await p.tick())                 # everyone has b
        self.has["late"] = "a"                           # a panel that missed it
        self.assertTrue(await p.tick())
        self.assertEqual((self.has["late"], self.published), ("b", ["b"]))
        self.assertEqual(self.sleep.calls, [], "no change: no debounce wait")

    async def test_a_failed_send_is_tried_again_on_the_next_look(self):
        p = self.make(["b"])
        self.fail_sends = True
        self.assertFalse(await p.tick(), "nobody got it: not reported as pushed")
        self.fail_sends = False
        self.assertTrue(await p.tick())
        self.assertEqual(self.has["p"], "b")

    async def test_a_burst_of_changes_is_one_push_of_the_last_state(self):
        p = self.make(["a", "b", "c", "d", "d", "d"])
        await p.tick()
        self.assertTrue(await p.tick())
        self.assertEqual(self.published, ["d"])
        self.assertEqual(self.sleep.calls, [0.25, 0.25, 0.25])

    async def test_a_state_that_never_settles_is_pushed_after_debounce_max(self):
        p = self.make(["a"] + [str(i) for i in range(50)])
        await p.tick()
        self.assertTrue(await p.tick())
        self.assertEqual(len(self.published), 1)
        self.assertLessEqual(sum(self.sleep.calls), 1.0)
        self.assertEqual(len(self.sleep.calls), 4)

    async def test_a_stale_look_during_the_debounce_never_takes_the_fresh_change_back(self):
        """Review P2-9: the fresh change goes out in this look, not one tick late as the old stale state."""
        p = self.make(["a", "b", ("a", True), ("a", True)])
        await p.tick()
        self.assertTrue(await p.tick())
        self.assertEqual(self.published, ["b"])

    async def test_run_looks_every_interval_while_active(self):
        p = self.make(["a", "a", "b", "b", "b"], debounce=0.0)
        n = {"left": 10}

        def active():
            n["left"] -= 1
            return n["left"] >= 0
        await p.run(active)
        self.assertEqual(self.published, ["b"])
        self.assertIn(1.0, self.sleep.calls)

    async def test_a_failing_probe_does_not_end_the_loop(self):
        p = self.make(["a"])

        async def bad_probe():
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
        self.gate: threading.Event | None = None             # set: every read waits on it (a stuck share)
        self.fail = False                                    # True: every read raises (a share that errors)

    def __call__(self, home):
        return self.with_generation(home)[0]

    def with_generation(self, home):
        gate = self.gate
        if gate is not None:
            gate.wait(T)
        with self.lock:
            self.calls += 1
            if self.fail:
                raise OSError("the share answers with an error")
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

    async def asyncTearDown(self):
        if self.fields.gate is not None:
            self.fields.gate.set()
        await super().asyncTearDown()

    async def panel_session(self, snapshot=True):
        """A panel that has its first state (the pusher keeps a panel up to date once it has one)."""
        c = await self.hello(kind="panel")
        self.assertEqual((await c.recv())["type"], "welcome")
        if snapshot:
            await c.send({"type": "snapshot", "id": "first"})
            self.assertEqual((await c.recv()).get("id"), "first")
        return c

    def session_of(self, kind="panel"):
        return [s for s in self.app.sessions.values() if s.kind == kind]

    async def until(self, cond):
        for _ in range(500):
            if cond():
                return
            await asyncio.sleep(0.01)
        self.fail("condition not met")

    async def test_a_changed_engine_state_reaches_the_panel_without_a_snapshot(self):
        c = await self.panel_session()
        cli = await self.cli()
        self.fields.set(client="Dr Nour", item="C0239")
        st = await c.recv()
        self.assertEqual(st["type"], "state", st)
        self.assertNotIn("id", st)
        self.assertEqual((st["state"]["client"], st["state"]["item"]), ("Dr Nour", "C0239"))
        await cli.send({"type": "snapshot", "id": "cli-1"})
        self.assertEqual((await cli.recv()).get("id"), "cli-1", "the CLI gets no push")

    async def test_one_push_per_change_and_none_for_a_state_the_panel_already_has(self):
        c = await self.panel_session()
        self.fields.set(item="C0239")
        self.assertEqual((await c.recv())["state"]["item"], "C0239")
        calls = self.fields.calls
        await self.until(lambda: self.fields.calls >= calls + 5)            # several more looks: nothing changed
        await c.send({"type": "snapshot", "id": "s1"})
        self.assertEqual((await c.recv()).get("id"), "s1", "no second push of the same state")
        self.fields.set(item="C0240")
        st = await c.recv()
        self.assertEqual((st.get("id"), st["state"]["item"]), (None, "C0240"))

    async def test_a_panel_left_behind_is_caught_up_on_the_next_look(self):
        """Review P1-1: a panel whose last state is not the current one (a failed send, an answer that went out after a
        newer push) gets the current state, although nothing changed on the engine side."""
        c = await self.panel_session()
        self.session_of()[0].state_fp = ("an", "older", "state")
        st = await c.recv()
        self.assertEqual((st["type"], st.get("id")), ("state", None))

    async def test_a_host_change_is_pushed_while_the_item_read_is_stuck(self):
        """Review P1-1: a stuck item read still lets host and job changes through (marked stale, with the last good
        item), and the fresh state follows when the read answers."""
        self.fields.set(client="Dr Nour", item="C0239")
        c = await self.panel_session()
        self.app.fields_timeout = 0.05
        self.fields.gate = threading.Event()                              # the share hangs from now on
        p = await self.panel(caps=("ping",))                              # a UXP Premiere panel: the host changes
        for _ in range(20):
            st = await c.recv_type("state")
            if st["state"]["connection"]["host"]["state"] == "uxp":
                break
        else:
            self.fail("the host change was never pushed")
        self.assertIs(st["state"].get("stale"), True)
        self.assertEqual(st["state"]["item"], "C0239", "the last good item")
        self.fields.gate.set()                                            # the share answers again
        for _ in range(20):
            st = await c.recv_type("state")
            if "stale" not in st["state"]:
                break
        else:
            self.fail("the fresh state never followed")
        self.assertEqual(st["state"]["connection"]["host"]["state"], "uxp")
        await p.aclose()

    async def test_no_push_reaches_a_panel_before_its_welcome(self):
        """Review P1-2: a session is registered before panel_update answers and its welcome is sent; a push in that
        window would reach the panel before the welcome (the panel calls it malformed and never sees that state)."""
        a = await self.panel_session()
        gate, entered = threading.Event(), threading.Event()

        def slow_update(build, path):
            entered.set()
            gate.wait(T)
            return "unknown"
        try:
            with mock.patch.object(serve_app.engine_state, "panel_update", slow_update):
                b = await self.hello(kind="panel")                        # its welcome waits on panel_update
                await self.until(entered.is_set)
                self.fields.set(item="C0239")
                self.assertEqual((await a.recv())["state"]["item"], "C0239")
                calls = self.fields.calls
                await self.until(lambda: self.fields.calls >= calls + 3)
                gate.set()
                first = await b.recv()
            self.assertEqual(first["type"], "welcome", first)
        finally:
            gate.set()

    async def test_a_read_that_keeps_failing_gives_no_push_per_poll(self):
        """Re-review 1: the snapshot answer and the pusher must build the same state from a failed read (the last
        good item, stale); else each poll's answer differs from the pusher's and every poll costs one more push."""
        self.fields.set(client="Dr Nour", item="C0239")
        c = await self.panel_session()
        self.fields.fail = True
        with self.assertLogs("serve.app", "WARNING"):
            st = await c.recv()                                       # the one push: the state became stale
            self.assertEqual((st.get("id"), st["state"]["item"], st["state"].get("stale")), (None, "C0239", True))
            for i in range(5):
                calls = self.fields.calls
                await self.until(lambda: self.fields.calls >= calls + 3)        # the pusher looked meanwhile
                await c.send({"type": "snapshot", "id": f"poll-{i}"})
                st = await c.recv()
                self.assertEqual(st.get("id"), f"poll-{i}", f"poll {i}: a push came first ({st})")
                self.assertEqual((st["state"]["item"], st["state"].get("stale")), ("C0239", True))

    async def test_close_keeps_its_budget_with_a_perf_writer_stuck_on_the_disk(self):
        """Re-review 2: App.close waits for the perf writer only within CLOSE_BUDGET (a dead disk costs no more)."""
        gate = threading.Event()

        def stuck_close(timeout=0.5):
            gate.wait(T)
        c = await self.panel_session()
        try:
            with mock.patch.object(self.app.perf, "close", stuck_close):
                t0 = time.monotonic()
                await self.app.close()
                self.assertLess(time.monotonic() - t0, serve_app.CLOSE_BUDGET + 0.5)
        finally:
            gate.set()
        await c.aclose()

    async def test_a_panel_without_a_state_yet_is_not_pushed(self):
        c = await self.panel_session(snapshot=False)
        self.fields.set(item="C0239")
        calls = self.fields.calls
        await self.until(lambda: self.fields.calls >= calls + 3)
        await c.send({"type": "snapshot", "id": "s1"})
        self.assertEqual((await c.recv()).get("id"), "s1", "its own snapshot answer comes first")

    async def test_a_job_change_is_pushed_too(self):
        c = await self.panel_session()
        p = await self.panel(caps=("ping",))
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
