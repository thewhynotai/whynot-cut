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
        self.assertEqual(hs.charter_status("FIX"), "IN_PROGRESS")
        self.assertEqual(hs.charter_status("weird"), "UNKNOWN")

    def test_board_words_map_to_the_restart_lifecycle(self):
        # AI-infra restart Phase 5: BACKLOG → READY → IN_PROGRESS → IN_REVIEW → IN_TESTING → DONE → ARCHIVED
        # (+ BLOCKED). BOARD keeps its words because the helper loops read them.
        want = {"NOT READY": "BACKLOG", "READY": "READY", "IN PROGRESS": "IN_PROGRESS", "FIX": "IN_PROGRESS",
                "DONE": "IN_REVIEW", "ACCEPTED": "IN_TESTING", "MERGED": "DONE", "DONE_ARCHIVED": "ARCHIVED",
                "ARCHIVED": "ARCHIVED", "IN_TESTING": "IN_TESTING", "BLOCKED": "BLOCKED", "PARKED": "BLOCKED"}
        for word, state in want.items():
            self.assertEqual(hs.charter_status(word), state, word)
        self.assertEqual(hs.LIFECYCLE, ("BACKLOG", "READY", "IN_PROGRESS", "IN_REVIEW", "IN_TESTING", "DONE",
                                        "ARCHIVED"))


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


class FixRound1(unittest.TestCase):
    """Review OPS-01-r1 findings."""

    def test_verdict_belongs_to_the_newest_report_file(self):
        with tempfile.TemporaryDirectory() as d:
            hq = Path(d)
            (hq / "inbox" / "h1").mkdir(parents=True)
            (hq / "intake").mkdir()
            old = hq / "inbox/h1/2026-10-19-SETUP-H1.md"
            new = hq / "inbox/h1/2026-10-19-SETUP-H1-r2.md"
            old.write_text("**Status:** PARTIAL", encoding="utf-8")
            new.write_text("**Status:** BLOCKED", encoding="utf-8")
            os.utime(old, (1, 1))
            (hq / "intake/state.json").write_text(json.dumps(
                {"inbox/h1/2026-10-19-SETUP-H1.md": {"verdict": "noted"}}), encoding="utf-8")
            rep = hs.inbox_reports(hq)["SETUP-H1"]
            self.assertEqual(rep["file"], "inbox/h1/2026-10-19-SETUP-H1-r2.md")
            self.assertEqual(hs.report_verdict(hq, rep), "")      # r2 has no verdict yet; r1's "noted" is not r2's

    def test_unfetched_remote_tip_is_not_given_a_count(self):
        self.assertEqual(hs.sync_label("a", "b", None, None), "REMOTE_MOVED (not fetched here)")

    def test_remote_tip_survives_one_failed_lookup(self):
        calls = []
        saved = hs._git
        try:
            hs._git = lambda *a, **k: calls.append(a) or (None if len(calls) == 1 else "abc123\trefs/heads/x")
            self.assertEqual(hs._remote_tip(".", "x", pause=0), "abc123")
            self.assertEqual(len(calls), 2)
            calls.clear()
            hs._git = lambda *a, **k: calls.append(a) and None
            self.assertIsNone(hs._remote_tip(".", "x", pause=0))  # two misses = really unreachable
            self.assertEqual(len(calls), 2)
        finally:
            hs._git = saved

    def test_newlines_are_kept(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d, "plan.md")
            p.write_bytes(b"a\n<!-- AUTO:STATUS START -->\nx\n<!-- AUTO:STATUS END -->\nb\n")
            hs.write_block(p, "y")
            self.assertNotIn(b"\r\n", p.read_bytes())
            inbox = Path(d, "inbox.md")
            inbox.write_bytes(b"# i\n| a |\n")
            hs.append_inbox(inbox, "R-1", "s", "l")
            self.assertNotIn(b"\r\n", inbox.read_bytes())

    def test_parser_tolerates_bold_dash_and_empty_owner(self):
        rows = hs.parse_board("| ID | T | A | S | C |\n|---|---|---|---|---|\n| X-1 | t |  | **ACCEPTED** | — |\n"
                              "| X-2 | t | H1 | READY — note | `tasks/X-2.md` |\n")
        self.assertEqual([r["status"] for r in rows], ["ACCEPTED", "READY"])
        hs.render_queue_yaml(rows, {}, "now")                  # no IndexError on the empty owner

    def test_removed_tasks_and_first_report_are_reported(self):
        self.assertEqual(hs.status_changes({"tasks": {"A": "READY"}}, {"tasks": {}}), [("A", "READY", None)])
        s = {"time": "t", "rows": [], "tasks": {}, "verdicts": {}, "reports": {}, "helpers": [], "api": "X",
             "api_month": {}, "ram": 10, "requests": [], "git": {"branch": "b", "local": "1", "remote": "1",
                                                             "label": "SYNCED", "dirty_files": 0}}
        self.assertIn("أول تقرير", hs.render_report(s, None, "t"))

    def test_open_owner_requests_are_listed(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d, "PRIMARY_ACCOUNT_INBOX.md")
            p.write_text("| Q-001 | 2026-10-19 | T4.14 transcript | his | OPEN |\n| Q-009 | x | done one | his | CLOSED |\n",
                         encoding="utf-8")
            self.assertEqual(hs.open_requests(p), ["Q-001 — T4.14 transcript"])

    def test_sync_refuses_a_worktree_on_another_branch(self):
        with tempfile.TemporaryDirectory() as d:
            wt = Path(d, "wt")
            git(d, "init", str(wt))
            git(wt, "checkout", "-b", "release/3.0")
            src = Path(d, "a.md")
            src.write_text("x", encoding="utf-8")
            r = hs.sync_mirror(wt, {"hq/a.md": src}, "m", branch="ops/hq")
            self.assertEqual(r["state"], "WRONG_BRANCH")
            self.assertFalse((wt / "hq" / "a.md").exists())

    def test_mark_sent_updates_only_that_row(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d, "inbox.md")
            p.write_text("# i\n", encoding="utf-8")
            hs.append_inbox(p, "R-1", "s", "l")
            hs.append_inbox(p, "R-2", "s", "l")
            self.assertTrue(hs.mark_sent(p, "R-1", "local_abc"))
            t = p.read_text(encoding="utf-8")
            self.assertIn("| R-1 |", t)
            self.assertIn("SENT (session local_abc)", t)
            self.assertEqual(t.count("SENT"), 1)
            self.assertFalse(hs.mark_sent(p, "R-9", "x"))


class FixRound2(unittest.TestCase):
    """Review OPS-01-r2 findings."""

    def _repo(self, d):
        remote = Path(d, "remote.git")
        git(d, "init", "--bare", str(remote))
        wt = Path(d, "wt")
        git(d, "init", str(wt))
        git(wt, "config", "user.email", "t@t")
        git(wt, "config", "user.name", "t")
        git(wt, "checkout", "-b", "ops/hq")
        git(wt, "remote", "add", "origin", str(remote))
        return wt

    def test_arabic_file_names_sync_twice(self):
        with tempfile.TemporaryDirectory() as d:
            wt = self._repo(d)
            src = Path(d, "كارت.md")
            src.write_text("x", encoding="utf-8")
            files = {"00-HQ/كارت-جرّب.md": src}
            self.assertEqual(hs.sync_mirror(wt, files, "m")["state"], "SYNCED")
            r = hs.sync_mirror(wt, files, "m")
            self.assertEqual(r["state"], "SYNCED", r["error"])
            self.assertFalse(r["committed"])

    def test_a_removed_source_is_removed_from_the_mirror(self):
        with tempfile.TemporaryDirectory() as d:
            wt = self._repo(d)
            a, b = Path(d, "a.md"), Path(d, "b.md")
            a.write_text("a", encoding="utf-8")
            b.write_text("b", encoding="utf-8")
            hs.sync_mirror(wt, {"x/a.md": a, "x/b.md": b}, "m")
            r = hs.sync_mirror(wt, {"x/a.md": a}, "m")
            self.assertEqual(r["state"], "SYNCED", r["error"])
            self.assertFalse((wt / "x" / "b.md").exists())

    def test_failures_carry_gits_own_message(self):
        with tempfile.TemporaryDirectory() as d:
            wt = self._repo(d)
            a = Path(d, "a.md")
            a.write_text("a", encoding="utf-8")
            git(wt, "remote", "set-url", "origin", str(Path(d, "nowhere.git")))
            r = hs.sync_mirror(wt, {"x/a.md": a}, "m")
            self.assertEqual(r["state"], "PUSH_FAILED")
            self.assertTrue(r["error"])

    def test_no_new_tag_claim_without_a_previous_tag(self):
        s = {"time": "t", "rows": [], "tasks": {}, "verdicts": {}, "reports": {}, "helpers": [], "api": "X",
             "api_month": {}, "ram": 10, "requests": [], "tag": "v1", "git": {"branch": "b", "local": "1",
                                                                              "remote": "1", "label": "SYNCED", "dirty_files": 0}}
        self.assertIn("NO NEW VERIFIED BUILD", hs.render_report(s, {"tasks": {}}, "t"))
        self.assertIn("tag جديد", hs.render_report(s, {"tasks": {}, "tag": "v0"}, "t"))

    def test_planned_api_row_is_not_an_unknown_status(self):
        self.assertEqual(hs.charter_status("PLANNED_NOT_AUTHORIZED"), "BACKLOG")

    def test_git_timeout_is_not_a_crash(self):
        self.assertIsNone(hs._git(".", "rev-parse", "HEAD", timeout=0.000001))


class Preview(unittest.TestCase):
    """OPS-03: release-preview folders vs origin, without lane-watch."""

    def test_label_is_read(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d, "LABEL.txt")
            p.write_text("label: PREVIEW-3.0.0-p4\ncommit: 322d8a5de3c5\ndate: 2026-10-19 01:55 UTC\n", encoding="utf-8")
            self.assertEqual(hs.preview_label(p), {"label": "PREVIEW-3.0.0-p4", "commit": "322d8a5de3c5",
                                                   "date": "2026-10-19 01:55 UTC"})
            self.assertEqual(hs.preview_label(Path(d, "none.txt")), {})

    def test_queue_a_refresh_only_when_behind_and_not_already_queued(self):
        done = [{"state": "done", "title": "release preview refresh"}]          # `wnc-queue list --json` rows
        waiting = [{"state": "queued", "title": "release preview refresh"}]
        running = [{"state": "running", "title": "release preview refresh"}]
        self.assertTrue(hs.should_queue_refresh(10, False, done))
        self.assertTrue(hs.should_queue_refresh(10, False, []))
        self.assertFalse(hs.should_queue_refresh(0, False, done))      # up to date
        self.assertFalse(hs.should_queue_refresh(10, True, done))      # a refresh holds the lock
        self.assertFalse(hs.should_queue_refresh(10, False, waiting))  # already waiting in the queue
        self.assertFalse(hs.should_queue_refresh(10, False, running))  # already running
        self.assertFalse(hs.should_queue_refresh(10, False, None))     # queue state unknown: never guess
        self.assertFalse(hs.should_queue_refresh(None, False, done))   # check could not run

    def test_a_failed_refresh_is_reported(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d, "refresh.log")
            p.write_text("2026-10-19 04:55:50 DONE PREVIEW ok\n2026-10-20 03:00:00 FAILED clone fetch\n", encoding="utf-8")
            self.assertIn("FAILED clone fetch", hs.refresh_failure(p))
            p.write_text("2026-10-19 04:55:50 DONE PREVIEW ok\n", encoding="utf-8")
            self.assertEqual(hs.refresh_failure(p), "")
            self.assertEqual(hs.refresh_failure(Path(d, "none.log")), "")


class Phase8Fields(unittest.TestCase):
    """AI-infra restart Phase 8: the brief's report fields 'current milestone', 'account assignments', 'new handoffs'."""

    S = {"time": "t", "rows": [], "tasks": {}, "verdicts": {}, "reports": {}, "helpers": [], "api": "X",
         "api_month": {}, "ram": 10, "requests": [], "git": {"branch": "b", "local": "1", "remote": "1",
                                                          "label": "SYNCED", "dirty_files": 0}}

    def test_current_milestone_is_the_first_open_one(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d, "PROJECT_PLAN_AR.md")
            p.write_text("## 3. Milestones\n\n- [x] **M0 — نظام الإدارة** · x\n- [ ] **M1 — Gate 4 → `v3.0.0-p4`** · y\n"
                         "- [ ] **M2 — خطة V1** · z\n", encoding="utf-8")
            self.assertEqual(hs.current_milestone(p), "M1 — Gate 4 → `v3.0.0-p4`")
            p.write_text("- [x] **M0 — done**\n", encoding="utf-8")
            self.assertEqual(hs.current_milestone(p), "")
            self.assertEqual(hs.current_milestone(Path(d, "none.md")), "")

    def test_report_names_milestone_and_main_seat(self):
        out = hs.render_report(dict(self.S, milestone="M1 — Gate 4"), None, "t")
        self.assertIn("M1 — Gate 4", out)
        self.assertIn("PRIMARY (info@)", out)
        self.assertIn("مش متحدد", hs.render_report(dict(self.S, milestone=""), None, "t"))

    def test_new_handoffs_since_the_last_report(self):
        reps = {"BL-20": {"who": "h2", "file": "inbox/h2/2026-10-22-1830-BL-20.md", "status": "DONE",
                          "mtime": hs.datetime.datetime(2026, 10, 22, 18, 30).timestamp()},
                "BL-04": {"who": "h2", "file": "inbox/h2/2026-10-22-0316-BL-04.md", "status": "DONE",
                          "mtime": hs.datetime.datetime(2026, 10, 22, 3, 16).timestamp()}}
        out = hs.render_report(dict(self.S, reports=reps), {"time": "2026-10-22 17:00", "tasks": {}}, "t")
        self.assertIn("inbox/h2/2026-10-22-1830-BL-20.md", out.split("## 2.")[0])
        self.assertNotIn("BL-04", out.split("## 2.")[0])
        self.assertIn("مفيش تسليم جديد", hs.render_report(dict(self.S, reports=reps),
                                                          {"time": "2026-10-22 19:00", "tasks": {}}, "t"))
        same_minute = {"BL-20": dict(reps["BL-20"], mtime=hs.datetime.datetime(2026, 10, 22, 17, 0, 30).timestamp())}
        self.assertIn("BL-20", hs.render_report(dict(self.S, reports=same_minute),
                                                {"time": "2026-10-22 17:00", "tasks": {}}, "t").split("## 2.")[0])
        for prev in ({"tasks": {}}, {"tasks": {}, "time": None}):
            self.assertIn("مش معروفة", hs.render_report(dict(self.S, reports=reps), prev, "t"))

    def test_helper_lines_name_the_account(self):
        h = {"who": "h2", "state": "idle", "auto_on": True, "stop": False, "at": "", "beat": "", "model": "", "reason": ""}
        self.assertIn("H2 (marketing@)", hs.render_report(dict(self.S, helpers=[h]), None, "t"))

    def test_h2_report_names_with_a_time_map_to_the_task(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "inbox" / "h2").mkdir(parents=True)
            Path(d, "inbox/h2/2026-10-22-0316-BL-04.md").write_text("**Status:** DONE", encoding="utf-8")
            self.assertEqual(list(hs.inbox_reports(Path(d))), ["BL-04"])

    def test_a_fix_round_verdict_is_not_waiting_for_intake(self):
        # the intake writes "FIX r1", "FIX r2": a decided report, not one still waiting
        reps = {"BL-20": {"who": "h2", "file": "inbox/h2/a-BL-20.md", "status": "DONE", "mtime": 0},
                "BL-04": {"who": "h2", "file": "inbox/h2/a-BL-04.md", "status": "DONE", "mtime": 0}}
        verdicts = {"inbox/h2/a-BL-20.md": {"verdict": "FIX r1"}, "inbox/h2/a-BL-04.md": {"verdict": "awaiting-peer"}}
        blocks = hs.render_report(dict(self.S, reports=reps, verdicts=verdicts), None, "t").split("## 5.")[1]
        self.assertNotIn("a-BL-20.md", blocks)
        self.assertIn("a-BL-04.md", blocks)

    def test_a_null_or_spaced_verdict_does_not_break_the_report(self):
        # state.json may hold "verdict": null; a leading space must not hide the FIX word
        reps = {"BL-20": {"who": "h2", "file": "inbox/h2/a-BL-20.md", "status": "DONE", "mtime": 0},
                "BL-04": {"who": "h2", "file": "inbox/h2/a-BL-04.md", "status": "DONE", "mtime": 0}}
        verdicts = {"inbox/h2/a-BL-20.md": {"verdict": " FIX r1"}, "inbox/h2/a-BL-04.md": {"verdict": None}}
        blocks = hs.render_report(dict(self.S, reports=reps, verdicts=verdicts), None, "t").split("## 5.")[1]
        self.assertNotIn("a-BL-20.md", blocks)
        self.assertIn("a-BL-04.md", blocks)


if __name__ == "__main__":
    unittest.main()
