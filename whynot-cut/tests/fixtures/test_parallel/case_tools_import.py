"""OPS-09 fixture for tests/test_test_parallel.py (copied in as test_<name>.py; never discovered here)."""
import unittest

import wnc_tools_only_helper  # lives only in <repo>/tools/: an ImportError serially, so it must be one in parallel


class ToolsImport(unittest.TestCase):
    def test_uses_the_helper(self):
        self.assertEqual(wnc_tools_only_helper.X, 1)
