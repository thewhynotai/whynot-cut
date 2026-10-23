"""OPS-09 fixture for tests/test_test_parallel.py (copied in as test_<name>.py; never discovered here)."""
import atexit
import os
import unittest

atexit.register(os._exit, 3)  # the worker writes its record, then the interpreter ends with exit code 3


class ExitAfterRecord(unittest.TestCase):
    def test_passes(self):
        pass
