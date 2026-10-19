"""Tests for hq_status.py (OPS-01). Run: python -X utf8 -m unittest 00-HQ/tools/test_hq_status.py"""
import json, os, subprocess, sys, tempfile, unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import hq_status as hs  # noqa: E402

BOARD = """# BOARD

Status words: READY ...

| ID | Title | Assigned | Status | Card | Next |
|---|---|---|---|---|---|
| BL-16 | Safe ASCII engine home (Gate 4, high) | H1 | READY · fallback executor 25 Oct | `tasks/BL-16.md` | — |
| BL-04 | run-state.json + resume | H2 | IN PROGRESS | `tasks/BL-04.md` | — |

## Old-system tracks
| Track | Chat | Holds | Expected END |
|---|---|---|---|
| EXEC-G4 | Executor local_x | Tasks 25/26 | Gate 4 tag |
"""


def git(cwd, *a):
    return subprocess.run(["git", *a], cwd=cwd, check=True, capture_output=True, text=True).stdout.strip()


class Board(unittest.TestCase):
    def test_rows_parse_from_the_task_table_only(self):
        rows = hs.parse_board(BOARD)
        self.assertEqual([r["id"] for r in rows], ["BL-16", "BL-04"])
        self.assertEqual(rows[0]["owner"], "H1")
        self.assertEqual(rows[0]["status"], "READY")          # the status word, without the note
        self.assertEqual(rows[0]["card"], "tasks/BL-16.md")
        self.assertEqual(rows[1]["status"], "IN PROGRESS")

    def test_status_words_map_to_charter_states(self):
        self.assertEqual(hs.charter_status("IN PROGRESS"), "IN_PROGRESS")
        self.assertEqual(hs.charter_status("MERGED"), "DONE_ARCHIVED")
        self.assertEqual(hs.charter_status("FIX"), "IN_PROGRESS")
        self.assertEqual(hs.charter_status("weird"), "UNKNOWN")


class Helpers(unittest.TestCase):
    def test_heartbeat_and_flags(self):
        with tempfile.TemporaryDirectory() as d:
            auto = Path(d, "h1", "auto")
            auto.mkdir(parents=True)
            (auto / "status.json").write_text(json.dumps({"state": "running", "at": "2026-10-20 00:46:11", "model": "opus"}))
            (auto / "AUTO-ON").write_text("")
            h = hs.helper_state(d, "h1")
            self.assertEqual((h["state"], h["at"], h["auto_on"], h["stop"]), ("running", "2026-10-20 00:46:11", True, False))
            self.assertEqual(hs.helper_state(d, "h2")["state"], "missing")


class Git(unittest.TestCase):
    def test_sync_labels(self):
        self.assertEqual(hs.sync_label("a", "a", 0, 0), "SYNCED")
        self.assertEqual(hs.sync_label("a", "b", 3, 0), "LOCAL_AHEAD 3")
        self.assertEqual(hs.sync_label("a", "b", 0, 2), "REMOTE_AHEAD 2")
        self.assertEqual(hs.sync_label("a", "b", 1, 1), "DIVERGED")
        self.assertEqual(hs.sync_label("a", None, 0, 0), "REMOTE_UNREACHABLE")


class Budget(unittest.TestCase):
    def test_api_state_is_read_not_invented(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d, "BUDGET-API.md")
            p.write_text("| **API-500 — single job below** | **PLANNED_NOT_AUTHORIZED** | 0 |\n", encoding="utf-8")
            self.assertEqual(hs.api_state(p), "PLANNED_NOT_AUTHORIZED")
            p.write_text("nothing here", encoding="utf-8")
            self.assertEqual(hs.api_state(p), "UNKNOWN")
            self.assertEqual(hs.api_state(Path(d, "missing.md")), "UNKNOWN")


class PlanBlock(unittest.TestCase):
    def test_only_the_block_changes(self):
        text = "head\n<!-- AUTO:STATUS START -->\nold\n<!-- AUTO:STATUS END -->\ntail\n"
        out = hs.replace_block(text, "new line")
        self.assertEqual(out, "head\n<!-- AUTO:STATUS START -->\nnew line\n<!-- AUTO:STATUS END -->\ntail\n")

    def test_missing_markers_raise(self):
        with self.assertRaises(ValueError):
            hs.replace_block("no markers", "x")


class Inbox(unittest.TestCase):
    def test_append_is_idempotent(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d, "PRIMARY_ACCOUNT_INBOX.md")
            p.write_text("# inbox\n", encoding="utf-8")
            self.assertTrue(hs.append_inbox(p, "R-20261020-0900", "summary", "reports/x.md"))
            self.assertFalse(hs.append_inbox(p, "R-20261020-0900", "summary", "reports/x.md"))
            t = p.read_text(encoding="utf-8")
            self.assertEqual(t.count("R-20261020-0900"), 1)
            self.assertIn("FILED", t)


class Diff(unittest.TestCase):
    def test_changes_since_last_snapshot(self):
        prev = {"tasks": {"BL-16": "READY", "BL-04": "IN PROGRESS"}}
        now = {"tasks": {"BL-16": "ACCEPTED", "BL-04": "IN PROGRESS", "BL-99": "READY"}}
        self.assertEqual(hs.status_changes(prev, now), [("BL-16", "READY", "ACCEPTED"), ("BL-99", None, "READY")])
        self.assertEqual(hs.status_changes(None, now), [])


class Queue(unittest.TestCase):
    def test_yaml_lists_every_task_with_required_fields(self):
        rows = hs.parse_board(BOARD)
        y = hs.render_queue_yaml(rows, {"BL-16": {"verdict": "awaiting-peer"}}, "2026-10-20 09:00")
        self.assertIn("task_id: \"BL-16\"", y)
        for key in ("owner:", "status:", "charter_status:", "card:", "intake_verdict:"):
            self.assertIn(key, y)
        self.assertIn("GENERATED", y.splitlines()[0])


class Sync(unittest.TestCase):
    def test_commit_push_verify_and_no_change_no_commit(self):
        with tempfile.TemporaryDirectory() as d:
            remote = Path(d, "remote.git")
            git(d, "init", "--bare", str(remote))
            wt = Path(d, "wt")
            git(d, "init", str(wt))
            git(wt, "config", "user.email", "t@t")
            git(wt, "config", "user.name", "t")
            git(wt, "checkout", "-b", "ops/hq")
            git(wt, "remote", "add", "origin", str(remote))
            src = Path(d, "src")
            src.mkdir()
            (src / "a.md").write_text("one", encoding="utf-8")
            r1 = hs.sync_mirror(wt, {"hq/a.md": src / "a.md"}, "ops: test", branch="ops/hq")
            self.assertEqual(r1["state"], "SYNCED")
            self.assertEqual(r1["local"], r1["remote"])
            r2 = hs.sync_mirror(wt, {"hq/a.md": src / "a.md"}, "ops: test", branch="ops/hq")
            self.assertEqual(r2["state"], "SYNCED")
            self.assertFalse(r2["committed"])
            (src / "a.md").write_text("two", encoding="utf-8")
            git(wt, "remote", "set-url", "origin", str(Path(d, "nowhere.git")))
            r3 = hs.sync_mirror(wt, {"hq/a.md": src / "a.md"}, "ops: test", branch="ops/hq")
            self.assertTrue(r3["committed"])
            self.assertEqual(r3["state"], "PUSH_FAILED")


if __name__ == "__main__":
    unittest.main()
