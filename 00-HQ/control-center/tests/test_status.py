import datetime as dt, sys, unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "app"))
import status as S  # noqa: E402

TH = {"working_seconds": 180, "quiet_warn_minutes": 20, "stalled_minutes": 60, "tool_wait_warn_minutes": 15}
NOW = dt.datetime(2026, 10, 22, 4, 0)


def helper(**kw):
    base = dict(loop_alive=True, auto_on=True, stop_file=False, state="running", reason="", until="",
                log_age_sec=30, tool_wait_sec=0, tests=None, report_blocked=False, action="Reading x")
    base.update(kw)
    return S.helper_status(base, TH)


class HelperStatus(unittest.TestCase):
    def test_not_checked_yet(self):
        self.assertEqual(helper(loop_alive=None)["code"], "CHECKING")

    def test_working(self):
        self.assertEqual(helper()["code"], "WORKING")

    def test_alive_but_silent_is_stalled_not_working(self):
        s = helper(log_age_sec=61 * 60)
        self.assertEqual(s["code"], "STALLED")
        self.assertIn("1 h 01 min", s["reason"])

    def test_quiet_between(self):
        self.assertEqual(helper(log_age_sec=25 * 60)["code"], "QUIET")

    def test_long_tool_is_waiting_on_a_command(self):
        s = helper(tool_wait_sec=20 * 60, action="Shell: sleep")
        self.assertEqual(s["code"], "WAITING_TOOL")
        self.assertIn("Shell: sleep", s["reason"])

    def test_tests_running_and_queued(self):
        self.assertEqual(helper(tests=("running", 12))["code"], "RUNNING_TESTS")
        self.assertEqual(helper(tests=("waiting", 40))["code"], "WAITING_QUEUE")

    def test_limit(self):
        s = helper(state="waiting", reason="usage limit", until="2026-10-22 06:03")
        self.assertEqual(s["code"], "WAITING_LIMIT")
        self.assertIn("06:03", s["label"])

    def test_back_off_after_failures_is_error(self):
        self.assertEqual(helper(state="waiting", reason="quick failure back-off", until="2026-10-22 04:10")["code"], "ERROR")

    def test_yielding_is_waiting_on_dependency(self):
        self.assertEqual(helper(state="yielding", reason="Gate 4 job 'g4-x' waits")["code"], "WAITING_DEP")

    def test_idle_and_blocked(self):
        self.assertEqual(helper(state="idle")["code"], "IDLE")
        self.assertEqual(helper(state="idle", report_blocked=True)["code"], "WAITING_INPUT")

    def test_loop_dead(self):
        self.assertEqual(helper(loop_alive=False)["code"], "DISCONNECTED")
        self.assertEqual(helper(loop_alive=False, stop_file=True, state="stopped")["code"], "STOPPED")
        self.assertEqual(helper(loop_alive=False, auto_on=False, state="stopped")["code"], "STOPPED")
        self.assertEqual(helper(loop_alive=False, auto_on=False, state="stalled")["code"], "ERROR")


def sess(**kw):
    base = dict(error=None, error_at=None, last_activity=NOW - dt.timedelta(minutes=5), transcript_age_sec=30,
                awaiting_person=False)
    base.update(kw)
    return S.session_status(base, TH, NOW)


class SessionStatus(unittest.TestCase):
    def test_working(self):
        self.assertEqual(sess()["code"], "WORKING")

    def test_limit_newer_than_activity(self):
        s = sess(error="You've hit your limit · resets 6am (Africa/Cairo)", error_at=NOW - dt.timedelta(minutes=1),
                 transcript_age_sec=600)
        self.assertEqual(s["code"], "WAITING_LIMIT")
        self.assertIn("06:00", s["label"])

    def test_old_limit_is_ignored_after_new_activity(self):
        s = sess(error="hit your limit · resets 1am", error_at=NOW - dt.timedelta(hours=3))
        self.assertEqual(s["code"], "WORKING")

    def test_other_error(self):
        s = sess(error="API Error: 500", error_at=NOW - dt.timedelta(minutes=1), transcript_age_sec=600)
        self.assertEqual(s["code"], "ERROR")

    def test_waiting_for_person(self):
        self.assertEqual(sess(awaiting_person=True, transcript_age_sec=600)["code"], "WAITING_INPUT")

    def test_idle_after_90_min(self):
        s = sess(last_activity=NOW - dt.timedelta(minutes=100), transcript_age_sec=6000)
        self.assertEqual(s["code"], "IDLE")

    def test_quiet(self):
        s = sess(last_activity=NOW - dt.timedelta(minutes=10), transcript_age_sec=600)
        self.assertEqual(s["code"], "QUIET")


class Rollup(unittest.TestCase):
    def test_most_important_wins(self):
        self.assertEqual(S.rollup(["IDLE", "WORKING", "QUIET"]), "WORKING")
        self.assertEqual(S.rollup(["IDLE", "WAITING_INPUT", "WORKING"]), "WAITING_INPUT")
        self.assertEqual(S.rollup(["IDLE", "ERROR"]), "ERROR")
        self.assertEqual(S.rollup([]), "IDLE")


class Context(unittest.TestCase):
    def test_levels(self):
        ctx = S.context_view(72000, {"size": 200000, "source": "h1 run"}, "2026-10-22T01:00:00Z", 70, 85)
        self.assertEqual(ctx["percent"], 36)
        self.assertEqual(ctx["remaining"], 128000)
        self.assertEqual(ctx["level"], "ok")
        self.assertEqual(S.context_view(150000, {"size": 200000}, None, 70, 85)["level"], "warn")
        self.assertEqual(S.context_view(190000, {"size": 200000}, None, 70, 85)["level"], "danger")

    def test_unknown_window_is_labelled_not_guessed(self):
        ctx = S.context_view(72000, None, None, 70, 85)
        self.assertIsNone(ctx["percent"])
        self.assertEqual(ctx["level"], "unknown")

    def test_no_measurement(self):
        self.assertEqual(S.context_view(None, {"size": 1}, None, 70, 85)["level"], "none")


if __name__ == "__main__":
    unittest.main()
