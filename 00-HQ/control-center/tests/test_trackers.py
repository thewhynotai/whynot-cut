import datetime as dt, json, os, sys, tempfile, unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "app"))
import trackers  # noqa: E402

MD = """# SETUP PHASE TRACKER

Updated: 2026-10-22 05:00 Cairo. One phase at a time.

| # | Phase (owner brief) | Status | Verification evidence | Blockers | Next action |
|---|---|---|---|---|---|
| 0 | Complete system audit | **DONE** (04:05) | `SETUP_AUDIT.md` | — | — |
| 2 | gstack installation | READY | — | L1, L2 | Inspect `setup` |

## Other table
| a | b |
|---|---|
| x | y |
"""


class Parse(unittest.TestCase):
    def test_first_table_cleaned(self):
        d = tempfile.mkdtemp()
        Path(d, "T.md").write_text(MD, encoding="utf-8")
        t = trackers.read({"id": "r", "title": "Restart", "title_ar": "إعادة", "file": "T.md"}, d)
        self.assertEqual(t["headers"], ["#", "Phase (owner brief)", "Status", "Verification evidence", "Blockers",
                                        "Next action"])
        self.assertEqual(t["rows"][0][2], "DONE (04:05)")
        self.assertEqual(t["rows"][1][5], "Inspect setup")
        self.assertEqual(len(t["rows"]), 2)
        self.assertEqual(t["updated"], "2026-10-22 05:00 Cairo")
        self.assertEqual(t["status_col"], 2)

    def test_missing_file_is_reported_not_crashing(self):
        t = trackers.read({"id": "r", "title": "R", "file": "nope.md"}, tempfile.mkdtemp())
        self.assertEqual(t["rows"], [])
        self.assertTrue(t["error"])


class NewBadge(unittest.TestCase):
    def test_first_run_marks_nothing_new_then_new_ids_are_new(self):
        p = os.path.join(tempfile.mkdtemp(), "seen.json")
        now = dt.datetime(2026, 10, 22, 5, 0)
        self.assertEqual(trackers.mark_new(p, ["A", "B"], now, 48), set())
        self.assertEqual(trackers.mark_new(p, ["A", "B", "C"], now, 48), {"C"})
        later = now + dt.timedelta(hours=49)
        self.assertEqual(trackers.mark_new(p, ["A", "B", "C"], later, 48), set())


if __name__ == "__main__":
    unittest.main()
