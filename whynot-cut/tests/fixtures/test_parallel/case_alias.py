"""OPS-09 fixture for tests/test_test_parallel.py (copied in as test_<name>.py; never discovered here).

Loads its test class under another module name, as test_wnc_queue.py does with wnc_queue_tool_tests (fix round 4):
the test ids start with `alias_inner.`, not with this module's name.
"""
import types

_SRC = '''
import os, unittest


def event(name):
    with open(os.path.join(os.environ["WNC_PARALLEL_FIXTURE_STATE"], "events.txt"), "a", encoding="utf-8") as f:
        f.write(name + "\\n")


class Inner(unittest.TestCase):
    def test_timed(self):
        event("alias-timed")

    def test_plain(self):
        event("alias-plain")
'''
_mod = types.ModuleType("alias_inner")
exec(_SRC, _mod.__dict__)
Inner = _mod.Inner
