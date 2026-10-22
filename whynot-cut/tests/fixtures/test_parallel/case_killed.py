"""OPS-09 fixture for tests/test_test_parallel.py (copied in as test_<name>.py; never discovered here)."""
import os
import unittest


def event(name):
    with open(os.path.join(os.environ["WNC_PARALLEL_FIXTURE_STATE"], "events.txt"), "a", encoding="utf-8") as f:
        f.write(name + "\n")


import signal


class Killed(unittest.TestCase):
    def test_kills_its_own_process(self):
        event("killed")
        os.kill(os.getpid(), signal.SIGTERM)
