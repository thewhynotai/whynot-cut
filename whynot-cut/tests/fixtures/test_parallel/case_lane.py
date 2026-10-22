"""OPS-09 fixture for tests/test_test_parallel.py (copied in as test_<name>.py; never discovered here)."""
import os
import unittest


def event(name):
    with open(os.path.join(os.environ["WNC_PARALLEL_FIXTURE_STATE"], "events.txt"), "a", encoding="utf-8") as f:
        f.write(name + "\n")


class Heavy(unittest.TestCase):
    def test_alone(self):
        event("lane-alone")

    def test_other(self):
        event("lane-other")


class WholeClass(unittest.TestCase):
    def test_one(self):
        event("lane-class")

    def test_two(self):
        event("lane-class")
