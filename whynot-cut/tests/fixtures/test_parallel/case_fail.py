"""OPS-09 fixture for tests/test_test_parallel.py (copied in as test_<name>.py; never discovered here)."""
import os
import unittest


def event(name):
    with open(os.path.join(os.environ["WNC_PARALLEL_FIXTURE_STATE"], "events.txt"), "a", encoding="utf-8") as f:
        f.write(name + "\n")


class Fails(unittest.TestCase):
    def test_always_fails(self):
        event("fail")
        self.assertEqual(1, 2)

    def test_raises(self):
        event("fail")
        raise RuntimeError("boom")

    def test_ok(self):
        event("fail")
