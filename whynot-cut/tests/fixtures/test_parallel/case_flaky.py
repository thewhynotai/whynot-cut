"""OPS-09 fixture for tests/test_test_parallel.py (copied in as test_<name>.py; never discovered here)."""
import os
import unittest


def event(name):
    with open(os.path.join(os.environ["WNC_PARALLEL_FIXTURE_STATE"], "events.txt"), "a", encoding="utf-8") as f:
        f.write(name + "\n")


class Flaky(unittest.TestCase):
    def test_fails_first_time(self):
        """Stands in for a test that fails only under load: fails on its first run, passes when re-run alone."""
        event("flaky")
        seen = os.path.join(os.environ["WNC_PARALLEL_FIXTURE_STATE"], "flaky.seen")
        if not os.path.exists(seen):
            open(seen, "w").close()
            self.fail("timed out under load")
