"""OPS-09 fixture for tests/test_test_parallel.py (copied in as test_<name>.py; never discovered here)."""
import os
import unittest


def event(name):
    with open(os.path.join(os.environ["WNC_PARALLEL_FIXTURE_STATE"], "events.txt"), "a", encoding="utf-8") as f:
        f.write(name + "\n")


class NoRecord(unittest.TestCase):
    def test_exits_0_before_the_record(self):
        event("norecord")
        os._exit(0)
