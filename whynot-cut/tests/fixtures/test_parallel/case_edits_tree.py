"""OPS-09 fixture for tests/test_test_parallel.py (copied in as test_<name>.py; never discovered here)."""
import unittest


class EditsTree(unittest.TestCase):
    def test_edits_a_tracked_file_while_the_suite_runs(self):
        with open("tools/x.txt", "ab") as f:  # cwd = the repo root
            f.write(b"edited during the run\n")
