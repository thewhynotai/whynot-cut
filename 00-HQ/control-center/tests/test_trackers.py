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


class Clean(unittest.TestCase):
    def test_extra_cells_merge_into_the_last_column_and_status_gets_a_short_word(self):
        d = tempfile.mkdtemp()
        Path(d, "T.md").write_text(
            "| # | Phase | Status | Next action |\n|---|---|---|---|\n"
            "| 6 | Accounts | IN PROGRESS (10:20): owner paused | x | run the pilot |\n"
            "| 7 | Pilot | **DONE** (09:15; review PASS) | — |\n", encoding="utf-8")
        t = trackers.read({"id": "r", "title": "R", "file": "T.md"}, d)
        self.assertEqual(len(t["rows"][0]), 4)
        self.assertEqual(t["rows"][0][3], "x | run the pilot")
        self.assertEqual([i["status_short"] for i in t["items"]], ["IN PROGRESS", "DONE"])
        self.assertEqual(t["items"][0]["title"], "Accounts")
        self.assertEqual(t["items"][0]["next"], "x | run the pilot")
        self.assertEqual(t["done"], 1)
        self.assertTrue(t["file_changed"])


class NewBadgeSafety(unittest.TestCase):
    def test_unreadable_file_does_not_wipe_badges(self):
        d = tempfile.mkdtemp()
        p = os.path.join(d, "seen.json")
        now = dt.datetime(2026, 10, 22, 5, 0)
        trackers.mark_new(p, ["A"], now, 48)
        trackers.mark_new(p, ["A", "B"], now, 48)  # B is new
        open(p, "w").write("{broken")              # transient corruption
        self.assertEqual(trackers.mark_new(p, ["A", "B"], now, 48), set())
        self.assertEqual(open(p).read(), "{broken")  # not rewritten as a "first run"


if __name__ == "__main__":
    unittest.main()
