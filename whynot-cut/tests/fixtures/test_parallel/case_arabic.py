"""OPS-09 fixture for tests/test_test_parallel.py (copied in as test_<name>.py; never discovered here)."""
import os
import unittest


def event(name):
    with open(os.path.join(os.environ["WNC_PARALLEL_FIXTURE_STATE"], "events.txt"), "a", encoding="utf-8") as f:
        f.write(name + "\n")


class عربي(unittest.TestCase):
    def test_عربي(self):
        event("arabic")
        self.assertEqual(3, 4, "الجملة غلط: ٣ مش ٤")

    def test_error(self):
        event("arabic")
        raise ValueError("رسالة الخطأ")
