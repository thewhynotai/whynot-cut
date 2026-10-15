"""wnc-queue (tools/wnc_queue: the dev job runner, not the product) in the shared suite. The tests live with the tool,
in tools/wnc_queue/tests/test_wnc_queue.py (stdlib only, so they also run with the system Python); this file loads
them under the G79 sandbox. Run alone:
    bash tools/test.sh -p test_wnc_queue.py
"""
import sys as _sys
_sys.dont_write_bytecode = True
import _isolation  # noqa: F401,E402  G79: sandbox the engine home first (tests/_isolation.py)
import importlib.util  # noqa: E402
import unittest  # noqa: E402
from pathlib import Path  # noqa: E402

_SRC = Path(__file__).resolve().parents[2] / "tools" / "wnc_queue" / "tests" / "test_wnc_queue.py"
_spec = importlib.util.spec_from_file_location("wnc_queue_tool_tests", _SRC)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
globals().update({k: v for k, v in vars(_mod).items()
                  if isinstance(v, type) and issubclass(v, unittest.TestCase) and v.__module__ == _mod.__name__})

if __name__ == "__main__":
    unittest.main()
