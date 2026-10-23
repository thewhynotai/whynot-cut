"""OPS-09 fixture for tests/test_test_parallel.py (copied in as test_<name>.py; never discovered here)."""
import unittest


class Surrogate(unittest.TestCase):
    def test_prints_a_lone_surrogate(self):
        print("\ud800")  # serial stdout (PYTHONUTF8, surrogateescape) cannot encode it: an ERROR in both modes
