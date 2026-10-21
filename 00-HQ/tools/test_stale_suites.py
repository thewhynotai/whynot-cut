"""Tests for stale_suites.py (OPS-07, round 2 after review OPS-07-r1). Run: python -X utf8 -m unittest test_stale_suites"""
import datetime as dt, sys, unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import stale_suites as ss  # noqa: E402

NOW = dt.datetime(2026, 10, 20, 6, 5)
DEAD = "local_f2d2f435-b1b2-4c37-8fb5-60cd4ebf3673"
ENV = '"C:\\Program Files\\Git\\usr\\bin\\env.exe" WNC_RUN={} PYTHONDONTWRITEBYTECODE=1 PYTHONUTF8=1 python.exe -B -m unittest discover'


class Tagged(unittest.TestCase):
    def test_only_the_dead_runs_tagged_env_processes_are_selected(self):
        procs = [
            {"pid": 10, "name": "env.exe", "cmd": ENV.format(DEAD)},                         # the dead run's suite
            {"pid": 11, "name": "env.exe", "cmd": ENV.format("local_other")},                # another live run
            {"pid": 12, "name": "env.exe", "cmd": ENV.replace("WNC_RUN={} ", "")},           # executor: untagged
            {"pid": 13, "name": "python.exe", "cmd": f"python.exe -c 'WNC_RUN={DEAD}'"},     # not an env.exe launcher
            {"pid": 14, "name": "env.exe", "cmd": ENV.format(DEAD + "x")},                    # prefix of another id
            {"pid": 15, "name": "bash.exe", "cmd": "bash heavy.sh suite review-BL-16 -- " + ENV.format(DEAD)},  # still queued (r2 P2-2)
        ]
        self.assertEqual(ss.tagged(procs, DEAD), [10, 15])

    def test_an_empty_or_bad_session_id_selects_nothing(self):
        procs = [{"pid": 10, "name": "env.exe", "cmd": ENV.format("")}]
        self.assertEqual(ss.tagged(procs, ""), [])
        self.assertEqual(ss.tagged(procs, "x; rm -rf"), [])


class Lock(unittest.TestCase):
    def test_lock_line_round_trip(self):
        line = ss.lock_line(NOW + dt.timedelta(minutes=30), DEAD)
        self.assertEqual(ss.parse_lock(line), (NOW + dt.timedelta(minutes=30), DEAD))

    def test_old_format_lock_has_no_session(self):
        self.assertEqual(ss.parse_lock("until 2026-10-20 09:38"), (dt.datetime(2026, 10, 20, 9, 38), None))

    def test_garbled_lock_parses_to_nothing(self):
        self.assertEqual(ss.parse_lock(""), (None, None))
        self.assertEqual(ss.parse_lock("until soon"), (None, None))

    def test_staleness(self):
        later = NOW + dt.timedelta(hours=3)
        self.assertFalse(ss.lock_stale(later, DEAD, True, NOW))          # its run still runs: respect it
        self.assertTrue(ss.lock_stale(later, DEAD, False, NOW))          # its run was cut: stale
        self.assertFalse(ss.lock_stale(later, None, None, NOW))          # old lock: time only
        self.assertFalse(ss.lock_stale(NOW - dt.timedelta(minutes=1), DEAD, True, NOW))  # expired but its run is live: respect (r2 P2-1)
        self.assertTrue(ss.lock_stale(NOW - dt.timedelta(minutes=1), DEAD, None, NOW))   # expired, state unknown
        self.assertTrue(ss.lock_stale(NOW - dt.timedelta(minutes=1), None, None, NOW))   # expired old lock
        self.assertTrue(ss.lock_stale(None, None, None, NOW))            # unreadable lock
        self.assertFalse(ss.lock_stale(later, DEAD, None, NOW))          # session state unknown: respect it


class RunAlive(unittest.TestCase):
    """2026-10-21 08:38 + 13:38 incidents: a live intake waiting on its review read `isRunning: false`, the next intake
    took its lock, and two intakes ran at once. The routine's own run status is the second, authoritative signal."""

    def test_either_signal_alive_means_alive(self):
        self.assertTrue(ss.run_alive(True, None))
        self.assertTrue(ss.run_alive(False, "running"))   # the incident: idle-looking session, run still running
        self.assertTrue(ss.run_alive(None, "running"))

    def test_finished_run_is_dead(self):
        self.assertFalse(ss.run_alive(False, "failed"))   # cut by a usage limit
        self.assertFalse(ss.run_alive(False, "succeeded"))
        self.assertFalse(ss.run_alive(None, "failed"))

    def test_not_in_the_run_list_is_unknown(self):
        # hand-started or older than the list: isRunning false alone is the incident's bad signal (review r1 P1)
        self.assertIsNone(ss.run_alive(False, None))
        self.assertIsNone(ss.run_alive(None, None))
        later = NOW + dt.timedelta(hours=3)
        self.assertFalse(ss.lock_stale(later, DEAD, ss.run_alive(False, None), NOW))                      # until respected
        self.assertTrue(ss.lock_stale(NOW - dt.timedelta(minutes=1), DEAD, ss.run_alive(False, None), NOW))  # expired

    def test_succeeded_turn_with_live_tagged_suites_is_alive(self):
        # 2026-10-21 17:43: the intake's turn ended ("succeeded", isRunning false) while 3 of its WNC_RUN-tagged
        # review suites waited in heavy.sh; their finish wakes it again. Killing them would repeat the incident.
        self.assertTrue(ss.run_alive(False, "succeeded", 3))
        self.assertFalse(ss.run_alive(False, "succeeded", 0))   # truly finished, only the lock was left behind
        self.assertFalse(ss.run_alive(False, "failed", 2))      # cut by a usage limit: its suites are orphans (OPS-07)

    def test_feeds_lock_stale(self):
        later = NOW + dt.timedelta(hours=3)
        self.assertFalse(ss.lock_stale(later, DEAD, ss.run_alive(False, "running"), NOW))
        self.assertTrue(ss.lock_stale(later, DEAD, ss.run_alive(False, "failed"), NOW))


class Age(unittest.TestCase):
    """2026-10-20 11:40 incident: the watchdog read UTC run times against a Cairo clock and stopped 3-minute-old runs."""

    def test_utc_z_timestamps(self):
        now = dt.datetime(2026, 10, 20, 8, 43, tzinfo=dt.timezone.utc)
        self.assertEqual(ss.age_minutes("2026-10-20T08:40:16.320Z", now), 2)
        self.assertEqual(ss.age_minutes("2026-10-20T01:40:16Z", now), 422)

    def test_offset_timestamps_and_garbage(self):
        now = dt.datetime(2026, 10, 20, 8, 43, tzinfo=dt.timezone.utc)
        self.assertEqual(ss.age_minutes("2026-10-20T11:40:00+03:00", now), 3)
        self.assertIsNone(ss.age_minutes("yesterday", now))
        self.assertIsNone(ss.age_minutes("2026-10-20 11:40", now))   # no zone: refuse to guess


if __name__ == "__main__":
    unittest.main()
