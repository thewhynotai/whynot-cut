"""OPS-09 fixture for tests/test_test_parallel.py (copied in as test_<name>.py; never discovered here)."""
import unittest


class XPass(unittest.TestCase):
    @unittest.expectedFailure
    def test_marked_to_fail_but_passes(self):
        pass
