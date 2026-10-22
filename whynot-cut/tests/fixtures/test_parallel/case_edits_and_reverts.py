"""OPS-09 fixture for tests/test_test_parallel.py (copied in as test_<name>.py; never discovered here)."""
import time
import unittest


class EditsAndReverts(unittest.TestCase):
    def test_edits_a_tracked_file_then_restores_its_exact_bytes(self):
        with open("tools/x.txt", "rb") as f:  # cwd = the repo root
            before = f.read()
        with open("tools/x.txt", "wb") as f:
            f.write(b"edited during the run\n")
        time.sleep(0.2)
        with open("tools/x.txt", "wb") as f:
            f.write(before)
