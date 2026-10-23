"""OPS-09 fixture for tests/test_test_parallel.py (copied in as test_<name>.py; never discovered here)."""
import json
import os
import sys
import unittest


class SysPath(unittest.TestCase):
    def test_records_sys_path(self):
        with open(os.path.join(os.environ["WNC_PARALLEL_FIXTURE_STATE"], "syspath.json"), "w", encoding="utf-8") as f:
            json.dump(sys.path, f)
