"""Tests for agency_live.py (the read-only AGENCY LIVE screen). Run: python -X utf8 -m unittest test_agency_live"""
import datetime as dt, json, sys, unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import agency_live as al  # noqa: E402

NOW = dt.datetime(2026, 10, 21, 22, 55)


class Words(unittest.TestCase):
    def test_model_name(self):
        self.assertEqual(al.model_name("claude-opus-5-5"), "Opus 5.5")
        self.assertEqual(al.model_name("opus"), "Opus")
        self.assertEqual(al.model_name("claude-sonnet-5-5"), "Sonnet 5.5")
        self.assertEqual(al.model_name(None), "?")

    def test_ago(self):
        self.assertEqual(al.ago(0.5), "now")
        self.assertEqual(al.ago(12), "12 min")
        self.assertEqual(al.ago(85), "1 h 25 min")

    def test_latin_drops_arabic_and_cuts(self):
        self.assertEqual(al.latin("تمام، هكمّل وأبلّغك أول ما ريفيو round 3 يطلع"), "")
        self.assertEqual(al.latin("BL-03  accepted\nnext"), "BL-03 accepted next")
        self.assertEqual(len(al.latin("x" * 300, 50)), 50)


class Limits(unittest.TestCase):
    def test_reset_same_evening_and_next_day(self):
        at = dt.datetime(2026, 10, 21, 21, 54)
        self.assertEqual(al.limit_reset("You've hit your session limit · resets 10:20pm (Africa/Cairo)", at),
                         dt.datetime(2026, 10, 21, 22, 20))
        late = dt.datetime(2026, 10, 21, 23, 40)
        self.assertEqual(al.limit_reset("limit · resets 2:20am (Africa/Cairo)", late), dt.datetime(2026, 10, 22, 2, 20))
        self.assertEqual(al.limit_reset("limit · resets 12pm", dt.datetime(2026, 10, 21, 9, 0)),
                         dt.datetime(2026, 10, 21, 12, 0))
        self.assertIsNone(al.limit_reset("API error 500", at))

    def test_account_state(self):
        err = "You've hit your session limit · resets 10:20pm (Africa/Cairo)"
        at = dt.datetime(2026, 10, 21, 21, 54)
        self.assertEqual(al.account_state([(err, at)], dt.datetime(2026, 10, 21, 22, 0)),
                         ("LIMITED", dt.datetime(2026, 10, 21, 22, 20)))
        self.assertEqual(al.account_state([(err, at)], NOW), ("OK", (at, dt.datetime(2026, 10, 21, 22, 20))))
        self.assertEqual(al.account_state([("network error", at)], NOW), ("OK", None))
        old = ("limit · resets 5:20pm", dt.datetime(2026, 10, 21, 16, 10))
        self.assertEqual(al.account_state([(err, at), old], dt.datetime(2026, 10, 21, 22, 0))[0], "LIMITED")  # newest wins
        weekly = ("You've hit your weekly limit · resets Oct 24, 9am", dt.datetime(2026, 10, 21, 22, 0))
        self.assertEqual(al.account_state([(err, at), weekly], dt.datetime(2026, 10, 21, 22, 30)), ("LIMITED", None))
        self.assertEqual(al.account_state([weekly], dt.datetime(2026, 10, 22, 4, 0)), ("OK", None))  # 6 h on: unknown


class Schedule(unittest.TestCase):
    def test_next_run(self):
        self.assertEqual(al.next_run([37], None, NOW), dt.datetime(2026, 10, 21, 23, 37))
        self.assertEqual(al.next_run([0], [9, 13, 17, 21], NOW), dt.datetime(2026, 10, 22, 9, 0))
        self.assertEqual(al.next_run([13, 43], None, dt.datetime(2026, 10, 21, 23, 13)), dt.datetime(2026, 10, 21, 23, 43))


class States(unittest.TestCase):
    def test_person(self):
        lim = "You've hit your session limit · resets 10:20pm"
        at = dt.datetime(2026, 10, 21, 22, 0)
        self.assertEqual(al.person_status(lim, at, at - dt.timedelta(minutes=1), 900, dt.datetime(2026, 10, 21, 22, 5)),
                         ("STOPPED: usage limit until 22:20", "red"))
        self.assertEqual(al.person_status(lim, at, at, 900, NOW)[1], "yellow")           # limit over, not resumed yet
        self.assertEqual(al.person_status(lim, at, NOW, 30, NOW), ("WORKING now", "green"))  # resumed after the error
        self.assertEqual(al.person_status(None, None, NOW - dt.timedelta(minutes=8), 480, NOW)[0], "QUIET 8 min")
        self.assertEqual(al.person_status(None, None, NOW - dt.timedelta(hours=3), None, NOW), ("IDLE 3 h 00 min", "gray"))

    def test_helper(self):
        self.assertEqual(al.helper_status("running", None, 5, "", None), al.CHECKING)  # before the first check
        self.assertEqual(al.helper_status("running", False, 5, "", None), ("LOOP NOT RUNNING", "red"))
        self.assertEqual(al.helper_status("running", True, 5, "", None), ("WORKING now", "green"))
        self.assertEqual(al.helper_status("running", True, 5, "", None, waiting_sec=5400)[0], "WAITING 1 h 30 min")
        self.assertEqual(al.helper_status("running", True, 5, "", None, 5400, ("RUNNING TESTS 91 min", "green")),
                         ("RUNNING TESTS 91 min", "green"))
        self.assertEqual(al.helper_status("running", True, 900, "", None)[0], "QUIET 15 min")
        self.assertEqual(al.helper_status("yielding", True, 999, "x", None)[1], "yellow")
        self.assertEqual(al.helper_status("idle", True, None, "", None), ("IDLE: no card for it", "gray"))
        self.assertEqual(al.helper_status("waiting", True, None, "", "2026-10-21 23:40")[0], "WAITING: limit until 23:40")
        self.assertEqual(al.helper_status("stalled", True, None, "3 quick failures", None), ("STALLED: 3 quick failures", "red"))


def _tool(cmd):
    return json.dumps({"type": "assistant", "message": {"content": [{"type": "tool_use", "input": {"command": cmd}}]}})


class HelperRun(unittest.TestCase):
    IDS = ["BL-02", "BL-04", "S6b", "S1-R51", "BL-03"]

    def test_card_from_branch_or_queue_label_not_from_board_reads(self):
        board_read = json.dumps({"type": "user", "message": {"content": "| BL-02 | tasks/BL-02.md | S6b |"}})
        log = [board_read, _tool("git switch -C h2/BL-04 && git status"), _tool("git diff h2/BL-04-base074b85b HEAD")]
        self.assertEqual(al.helper_card("h2", log, [], self.IDS), "card BL-04")
        self.assertEqual(al.helper_card("h1", [_tool("bash heavy.sh suite h1-S6b-r1 -- env X=1 bash tools/test.sh")], [],
                                        self.IDS), "card S6b")
        self.assertEqual(al.helper_card("h1", [board_read], [], self.IDS), "")

    def test_peer_review_from_auto_log(self):
        tail = ["[2026-10-21 16:27:37] peer review of h2's BL-03 (report mtime 1792559882) before my next card",
                "[2026-10-21 16:27:37] run 4 started on opus (effort medium), log x.jsonl"]
        self.assertEqual(al.helper_card("h1", [], tail, self.IDS), "peer review of BL-03 (H2)")
        self.assertEqual(al.helper_card("h1", [], ["[..] run 5 started on opus"], self.IDS), "")

    def test_doing_and_waiting(self):
        said = json.dumps({"type": "assistant", "message": {"content": [{"type": "text", "text": "Queue check, then the suite."}]}})
        beat = json.dumps({"type": "tool_progress", "heartbeat": True, "elapsed_time_seconds": 5400})
        self.assertEqual(al.helper_doing([said, beat]), ("Queue check, then the suite.", 5400))
        self.assertEqual(al.helper_doing([beat, said]), ("Queue check, then the suite.", 0))  # spoke after the wait
        self.assertEqual(al.helper_doing(["not json"]), ("", 0))


class Tasks(unittest.TestCase):
    def test_groups(self):
        rows = [
            {"id": "S6b", "owner": "H1", "status": "FIX", "status_note": "FIX (round 1)", "card": "tasks/S6b.md"},
            {"id": "BL-02", "owner": "H1", "status": "READY", "status_note": "READY", "card": "tasks/BL-02.md"},
            {"id": "BL-03", "owner": "H2", "status": "ACCEPTED", "status_note": "ACCEPTED (22:40)", "card": "x"},
            {"id": "SETUP-H1", "owner": "H1 (Mayar)", "status": "ACCEPTED", "status_note": "ACCEPTED — closed, no code",
             "card": "x"},
            {"id": "BL-17", "owner": "H1", "status": "READY", "status_note": "READY", "card": "x"},
            {"id": "BL-16", "owner": "H1", "status": "MERGED", "status_note": "MERGED (890b144)", "card": "today"},
            {"id": "OPS-01", "owner": "MASTER", "status": "DONE_ARCHIVED", "status_note": "", "card": "old"},
            {"id": "(lane 1)", "owner": "—", "status": "STOPPED", "status_note": "", "card": ""},
            {"id": "BL-09", "owner": "H2", "status": "BLOCKED", "status_note": "", "card": ""},
        ]
        reports = {"BL-02": {"who": "h1", "file": "inbox/h1/2026-10-20-BL-02-r2.md", "status": "DONE"},
                   "1350-BL-03": {"who": "h2", "file": "inbox/h2/a.md", "status": "DONE"}}
        verdicts = {"inbox/h1/2026-10-20-BL-02-r2.md": {"verdict": "processing"}, "inbox/h2/a.md": {"verdict": "FIX r1"}}
        today = NOW.date()
        g = al.task_groups(rows, reports, verdicts, today, lambda c: today if c == "today" else dt.date(2026, 10, 1))
        self.assertEqual(g["Working on"], ["S6b (H1, fix)"])
        self.assertEqual(g["Waiting for review"], ["BL-02 (H1)"])
        self.assertEqual(g["Waiting for merge"], ["BL-03 (H2)"])
        self.assertEqual(g["Next up"], ["BL-17 (H1)"])
        self.assertEqual(g["Blocked"], ["BL-09 (H2)"])
        self.assertEqual(g["Finished today"], ["BL-16"])


class Queue(unittest.TestCase):
    TEXT = ("RAM 79% (24.9 of 31.7 GB)  CPU 26%  heavy slots: 2 of 4 allowed\nRunning:\n"
            "  heavy-1  suite h2-BL-04                              91 min  owner alive\n"
            "  suite-1  suite h2-BL-04                              91 min  owner alive\n"
            "  heavy-2  job   rv6d74-mutA                          13 min  owner alive\n"
            "Waiting (first come first served per kind):\n"
            "  suite h1-S6b-r1                            39 min  2 suites already running\n"
            "  suite peer-BL-03                            5 min  queued\n"
            "Last finished:\n"
            "  2026-10-21T16:22  suite bl20r3-all   rc=0   wait  9343s  ran   1572s\n")

    def test_parse_and_helper_tests(self):
        q = al.parse_queue(self.TEXT)
        self.assertEqual(q["running"], {"h2-BL-04": 91, "rv6d74-mutA": 13})
        self.assertEqual(q["waiting"], {"h1-S6b-r1": 39, "peer-BL-03": 5})
        self.assertEqual(al.helper_tests("h2", "card BL-04", q), ("RUNNING TESTS 1 h 31 min", "green"))
        self.assertEqual(al.helper_tests("h1", "card S6b", q), ("IN TEST QUEUE 39 min", "yellow"))
        self.assertEqual(al.helper_tests("h1", "peer review of BL-03 (H2)", q), ("IN TEST QUEUE 39 min", "yellow"))
        self.assertIsNone(al.helper_tests("h1", "", al.parse_queue("RAM 50%\nRunning:\n")))
        self.assertEqual(al.queue_summary(q), "RAM 79% · test queue: 2 running, 2 waiting (oldest 39 min)")

    def test_summary(self):
        text = ("RAM 79% (24.9 of 31.7 GB)  CPU 26%  heavy slots: 2 of 4 allowed\nRunning:\n"
                "  heavy-1  suite h1-S6b-r1                            28 min  owner alive\n"
                "  suite-1  suite h1-S6b-r1                            28 min  owner alive\n"
                "  heavy-2  job   rv6d74-mutA                          13 min  owner alive\n"
                "Waiting (first come first served per kind):\n"
                "  job   rv6d74-mutC                          79 min  RAM 69%: 4 of 4 heavy slots in use\n"
                "  suite review-BL-02                         74 min  2 suites already running\n")
        self.assertEqual(al.queue_summary(al.parse_queue(text)),
                         "RAM 79% · test queue: 2 running, 2 waiting (oldest 1 h 19 min)")
        self.assertEqual(al.queue_summary(al.parse_queue("RAM 50%\nRunning:\nWaiting (x):\n  (nobody)\n")),
                         "RAM 50% · test queue: 0 running, 0 waiting")
        self.assertEqual(al.queue_summary(al.parse_queue("")), "RAM ? · test queue: 0 running, 0 waiting")


class Decisions(unittest.TestCase):
    def test_recent(self):
        state = {"inbox/h1/2026-10-19-BL-16.md": {"verdict": "FIX r1", "at": "2026-10-20 08:24"},
                 "inbox/h1/2026-10-21-BL-16.md": {"verdict": "ACCEPTED", "at": "2026-10-21 03:39"},
                 "inbox\\h2\\2026-10-21-0817-BL-03.md": {"verdict": "ACCEPTED", "at": "2026-10-21 22:40"},
                 "inbox/h1/2026-10-20-BL-02-r2.md": {"verdict": "processing", "at": "2026-10-21 12:39"},
                 "inbox/h2/2026-10-21-1902-BL-04.md": {"verdict": "noted", "at": "2026-10-21 22:40"}}
        self.assertEqual(al.recent_decisions(state, NOW.date(), 2), ["22:40 BL-03 ACCEPTED", "03:39 BL-16 ACCEPTED"])
        self.assertEqual(al.recent_decisions(state, NOW.date())[-1], "10-20 08:24 BL-16 FIX r1")  # older day: date shown


class Usage(unittest.TestCase):
    def test_newest_account_and_stale_weekly(self):
        ms = lambda d: int(d.timestamp() * 1000)  # noqa: E731
        samples = [
            {"t": ms(dt.datetime(2026, 10, 20, 16, 16)), "org": "old", "u": {"fh": 46, "sd": 17}},
            {"t": ms(dt.datetime(2026, 10, 21, 21, 52)), "org": "main", "u": {"fh": 100}},
            {"t": ms(dt.datetime(2026, 10, 21, 22, 20)), "org": "main", "u": {"fh": 0}},
        ]
        self.assertEqual(al.usage_line(samples, NOW), "used 0% of the 5-hour limit (at 22:20)")
        samples.append({"t": ms(dt.datetime(2026, 10, 21, 22, 30)), "org": "main", "u": {"fh": 12, "sd": 40}})
        self.assertEqual(al.usage_line(samples, NOW), "used 12% of the 5-hour limit (at 22:30) · weekly 40%")
        self.assertEqual(al.usage_line([], NOW), "")
        self.assertEqual(al.usage_line(samples, NOW + dt.timedelta(hours=6)), "weekly 40%")  # 5-hour % too old


class SubAgents(unittest.TestCase):
    def test_state(self):
        done = {"type": "assistant", "message": {"stop_reason": "end_turn", "content": [{"type": "text"}]}}
        tool = {"type": "user", "message": {"content": [{"type": "tool_result"}]}}
        self.assertIsNone(al.subagent_state({"finished": True}, tool, 10))
        self.assertIsNone(al.subagent_state({}, done, 10))
        self.assertEqual(al.subagent_state({}, tool, 30), ("WORKING now", "green"))
        self.assertEqual(al.subagent_state({}, tool, 600), ("QUIET 10 min", "yellow"))
        self.assertEqual(al.subagent_state({}, tool, 600, parent_limited=True), ("STOPPED: usage limit", "red"))
        self.assertEqual(al.subagent_state({}, tool, 3600), ("STOPPED? quiet 1 h 00 min", "gray"))

    def test_context_label(self):
        self.assertEqual(al.context_label(0), ("", ""))
        self.assertEqual(al.context_label(120_400), ("120k ctx", "gray"))
        self.assertEqual(al.context_label(250_000), ("250k ctx", "gray"))
        self.assertEqual(al.context_label(947_100), ("947k TOO BIG", "red"))


class Render(unittest.TestCase):
    def test_continuation_parts_and_width(self):
        out = al.render([("Name      ", ""), ("\0WORKING", "green"), ("\0 doing a long thing", "")], 20, colour=False)
        self.assertEqual(out, "Name      WORKING d")  # width - 1: the last column would wrap the console line
        coloured = al.render([("A", ""), ("\0B", "red")], 80)
        self.assertIn("\x1b[31mB\x1b[0m", coloured)


if __name__ == "__main__":
    unittest.main()
