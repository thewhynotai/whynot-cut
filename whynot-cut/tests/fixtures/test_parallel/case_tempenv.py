"""OPS-09 fixture for tests/test_test_parallel.py (copied in as test_<name>.py; never discovered here)."""
import json
import os
import tempfile
import unittest


class TempEnv(unittest.TestCase):
    def test_records_the_temp_variables(self):
        seen = {k: os.environ.get(k) for k in ("TEMP", "TMP", "TMPDIR")}
        seen["gettempdir"] = tempfile.gettempdir()
        with open(os.path.join(os.environ["WNC_PARALLEL_FIXTURE_STATE"], "tempenv.json"), "w", encoding="utf-8") as f:
            json.dump(seen, f)
