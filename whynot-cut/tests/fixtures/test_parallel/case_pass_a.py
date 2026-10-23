"""OPS-09 fixture for tests/test_test_parallel.py (copied in as test_<name>.py; never discovered here)."""
import os
import unittest


def event(name):
    with open(os.path.join(os.environ["WNC_PARALLEL_FIXTURE_STATE"], "events.txt"), "a", encoding="utf-8") as f:
        f.write(name + "\n")


class A(unittest.TestCase):
    def test_ok(self):
        event("a")

    def test_skipped(self):
        event("a")
        self.skipTest("not here")
