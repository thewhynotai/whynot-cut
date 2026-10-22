import os, sys, tempfile, time, unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "app"))
import tasks as T  # noqa: E402

BOARD = """# BOARD
| ID | Title | Assigned | Status | Card | Next |
|---|---|---|---|---|---|
| BL-17 | Second install must not overwrite pointer files (Gate 5) | H1 | READY | `tasks/BL-17.md` | — |
| S6b | Gate 4 eval cases (LIGHT) | H1 | FIX (round 1, 2026-10-21 17:55) | `tasks/S6b.md` | — |
| BL-04 | run-state.json + resume (Gate 4) | H2 | IN PROGRESS · fallback | `tasks/BL-04.md` | — |
| BL-03 | Notice templates (Gate 4) | H2 | ACCEPTED (2026-10-21 22:40) | `tasks/BL-03.md` | — |
| BL-16 | Safe engine home | H1 | MERGED (890b144) | `tasks/BL-16.md` | — |
| BL-20 | Skip audit | H2 | BLOCKED | `tasks/BL-20.md` | — |
| (lane 1) | API lane 1 | — | STOPPED | — | — |
| OPS-04 | Move 00-HQ into the repo | EXECUTOR | NOT READY (after the tag) | `tasks/OPS-04.md` | — |
| SETUP-H1 | First login | H1 | ACCEPTED — closed, no code (nothing to merge) | `tasks/SETUP-H1.md` | — |
| OPS-01 | Status generator | MASTER | DONE_ARCHIVED (02:00) | `tasks/OPS-01.md` | — |
| API-500 | Paid job | LANE | PLANNED_NOT_AUTHORIZED (waits) | `BUDGET-API.md` | — |
| S7 | Fixed already | H1 | FIX (round 1) | `tasks/S7.md` | — |
"""

CARD = """# {id} — {title}

- **Assigned:** H1    **Model:** Opus    **Size:** M    **Status:** READY
- **Tier:** LIGHT (dev files)
- **Stage / gate:** Gate 5 (value medium)    **Depends on:** BL-16 merged

## Goal
Each install keeps its own pointer files, so a second install never breaks the first.

## Extra acceptance
- [x] two installs test
- [ ] upgrade test
"""


def write(p, text, mtime=None):
    p = Path(p)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")
    if mtime:
        os.utime(p, (mtime, mtime))
    return p


class ParseCard(unittest.TestCase):
    def test_fields(self):
        d = tempfile.mkdtemp()
        p = write(Path(d, "BL-17.md"), CARD.format(id="BL-17", title="Pointers"))
        c = T.parse_card(p)
        self.assertEqual(c["tier"], "LIGHT")
        self.assertEqual(c["stage"], "Gate 5")
        self.assertEqual(c["depends"], "BL-16 merged")
        self.assertEqual(c["summary"], "Each install keeps its own pointer files, so a second install never breaks the first.")
        self.assertEqual(c["acceptance"], (1, 2))
        self.assertIsNone(c["fix_at"])

    def test_fix_round_time_and_spec_fallback(self):
        d = tempfile.mkdtemp()
        write(Path(d, "S6b-spec.md"), "### S6b\n\nEval cases for every Phase 4 skill, graded by rubric.\n")
        p = write(Path(d, "S6b.md"), "# S6b — Evals\n\n- **Status:** FIX\n\n## Spec (binding)\n`tasks/S6b-spec.md`\n\n"
                                     "## FIX round 1 (2026-10-21 17:55)\n- P2 fix grader\n## FIX round 2 (2026-10-22 01:10)\n")
        c = T.parse_card(p)
        self.assertEqual(c["fix_at"], "2026-10-22 01:10")
        self.assertEqual(c["fix_round"], 2)
        self.assertEqual(c["summary"], "Eval cases for every Phase 4 skill, graded by rubric.")

    def test_spec_heading_is_the_objective_when_no_prose(self):
        d = tempfile.mkdtemp()
        write(Path(d, "BL-02-spec.md"), "<!-- copy -->\n### BL-02 [Gate 4]: Task 18 (part 1) licence files + notices "
                                        "generator  [Gate 4 value: high]  Model: opus\n- Depends on: none\n")
        p = write(Path(d, "BL-02.md"), "# BL-02 — t\n\n## Spec (binding)\n`tasks/BL-02-spec.md`, a copy.\n")
        self.assertEqual(T.parse_card(p)["summary"], "Task 18 (part 1) licence files + notices generator")

    def test_spec_heading_ignores_plain_headings(self):
        for text in ("## Objective\n", "## Goal\n- do x\n", "# Title\n\n## Scope\n- a\n"):
            self.assertEqual(T._spec_heading(text), "", text)

    def test_missing_card(self):
        self.assertEqual(T.parse_card(Path(tempfile.mkdtemp(), "x.md"))["summary"], "")


class ReportNames(unittest.TestCase):
    def test_both_name_styles(self):
        self.assertEqual(T.report_task("2026-10-21-2356-BL-04.md"), "BL-04")
        self.assertEqual(T.report_task("2026-10-22-S6b-r3.md"), "S6b")
        self.assertEqual(T.report_task("2026-10-19-SETUP-H1.md"), "SETUP-H1")
        self.assertIsNone(T.report_task("OPS-03-r1.md"))


class Build(unittest.TestCase):
    def setUp(self):
        self.hq = Path(tempfile.mkdtemp())
        write(self.hq / "BOARD.md", BOARD)
        now = time.time()
        self.now = now
        for cid, title in (("BL-17", "Pointers"), ("BL-04", "Resume"), ("BL-03", "Notices"), ("BL-16", "Home"),
                           ("BL-20", "Skips"), ("OPS-04", "Move")):
            write(self.hq / "tasks" / f"{cid}.md", CARD.format(id=cid, title=title))
        write(self.hq / "tasks" / "S6b.md", "# S6b — Evals\n\n- **Status:** FIX\n\n## Goal\nEvals.\n\n"
                                            "## FIX round 1 (2026-10-21 17:55)\n")
        # S6b: DONE report BEFORE the fix round (17:55) -> fixing; BL-04: DONE + peer PASS -> awaiting decision
        write(self.hq / "inbox/h1/2026-10-21-S6b.md", "# Update — S6b — h1 — 2026-10-21 12:00 (Cairo)\n\n"
                                                      "**Status:** DONE first round.\n",
              mtime=time.mktime((2026, 10, 21, 12, 0, 0, 0, 0, -1)))
        rep = write(self.hq / "inbox/h2/2026-10-22-0316-BL-04.md",
                    "# Update — BL-04 — h2 — 2026-10-22 03:16 (Cairo)\n\n**Status:** DONE (4 patches, full suite OK).\n")
        mt = int(rep.stat().st_mtime)
        write(self.hq / "reviews" / "BL-04-peer-h1-20261022-0400.md",
              f"report-mtime: {mt}\nreviewer: h1 (peer)\nsha: abc\nsuite: OK 9000 run\nverdict: PASS\n")
        write(self.hq / "inbox/h2/2026-10-22-BL-20.md", "# Update — BL-20 — h2 — 2026-10-22 02:00 (Cairo)\n\n"
                                                        "**Status:** BLOCKED needs the executor's skip list.\n")
        write(self.hq / "tasks" / "S7.md", "# S7 — t\n\n## FIX round 1 (2026-10-21 17:55)\n")
        write(self.hq / "inbox/h1/2026-10-22-S7-r2.md", "# Update — S7 — h1 — 2026-10-22 02:58 (Cairo)\n\n"
                                                       "**Status:** DONE fixed.\n")
        write(self.hq / "intake/state.json",
              '{"inbox/h2/2026-10-22-0316-BL-04.md": {"verdict": "awaiting-peer", "at": "2026-10-22 03:39"}}')
        self.tasks = {t["id"]: t for t in T.build_tasks(self.hq, branches={"h1/BL-17": "2026-10-22T03:00:00+02:00"},
                                                         queue={"running": {"h2-BL-04": 12}, "waiting": {}})}

    def step(self, cid, key):
        return next(s for s in self.tasks[cid]["steps"] if s["key"] == key)

    def test_skips_lane_rows_and_maps_owner(self):
        self.assertNotIn("(lane 1)", self.tasks)
        self.assertEqual(self.tasks["BL-17"]["owner"], "h1")
        self.assertEqual(self.tasks["OPS-04"]["owner"], "main")

    def test_title_summary_parent(self):
        t = self.tasks["BL-17"]
        self.assertEqual(t["title"], "Second install must not overwrite pointer files")
        self.assertEqual(t["summary"], "Each install keeps its own pointer files, so a second install never breaks the first.")
        self.assertEqual(t["parent"], "Gate 5")

    def test_started_from_branch(self):
        t = self.tasks["BL-17"]
        self.assertEqual(self.step("BL-17", "started")["state"], "done")
        self.assertIn("h1/BL-17", self.step("BL-17", "started")["evidence"])
        self.assertEqual(t["display"], "In progress")

    def test_fix_after_done_reopens_delivery(self):
        self.assertEqual(self.tasks["S6b"]["display"], "Fixing (round 1)")
        self.assertEqual(self.step("S6b", "delivered")["state"], "current")

    def test_delivered_and_peer_passed_awaits_decision(self):
        t = self.tasks["BL-04"]
        self.assertEqual(self.step("BL-04", "delivered")["state"], "done")
        self.assertEqual(self.step("BL-04", "peer")["state"], "done")
        self.assertIn("PASS", self.step("BL-04", "peer")["evidence"])
        self.assertEqual(self.step("BL-04", "decision")["state"], "current")
        self.assertEqual(t["display"], "Peer review passed, waiting for the master's decision")
        self.assertEqual(t["verification"], "Peer h1: PASS · suite: OK 9000 run")
        self.assertEqual(t["jobs"], ["h2-BL-04 running 12 min"])
        self.assertEqual(t["progress"], {"done": 4, "total": 6})

    def test_accepted_and_merged(self):
        self.assertEqual(self.tasks["BL-03"]["display"], "Accepted, waiting for merge")
        self.assertEqual(self.tasks["BL-16"]["display"], "Merged")
        self.assertEqual(self.step("BL-16", "merged")["state"], "done")

    def test_no_peer_review_is_skipped_not_verified(self):
        self.assertEqual(self.step("BL-16", "peer")["state"], "skipped")
        self.assertEqual(self.tasks["BL-16"]["progress"], {"done": 5, "total": 5})

    def test_blocked_has_blocker_text(self):
        t = self.tasks["BL-20"]
        self.assertEqual(t["display"], "Blocked")
        self.assertIn("skip list", t["blocker"])
        self.assertEqual(self.step("BL-20", "delivered")["state"], "failed")

    def test_depends(self):
        self.assertEqual(self.tasks["BL-17"]["depends"], "BL-16 merged")

    def test_closed_without_code(self):
        self.assertEqual(self.tasks["SETUP-H1"]["display"], "Accepted (nothing to merge)")
        self.assertEqual(self.step("SETUP-H1", "merged")["state"], "skipped")

    def test_archived_is_done_not_merged(self):
        self.assertEqual(self.tasks["OPS-01"]["display"], "Done (archived)")

    def test_unknown_status_is_shown_as_written(self):
        self.assertEqual(self.tasks["API-500"]["display"], "Planned, not authorized")

    def test_board_fix_but_newer_done_report_is_delivered(self):
        t = self.tasks["S7"]
        self.assertEqual(self.step("S7", "delivered")["state"], "done")
        self.assertEqual(t["display"], "Delivered, waiting for peer review")

    def test_spec_html_comment_is_not_the_summary(self):
        d = tempfile.mkdtemp()
        write(Path(d, "X-spec.md"), "<!-- Verbatim copy of BACKLOG.md -->\n### X\n\nThe real goal.\n")
        p = write(Path(d, "X.md"), "# X — t\n\n## Spec (binding)\n`tasks/X-spec.md`\n")
        self.assertEqual(T.parse_card(p)["summary"], "The real goal.")

    def test_not_ready(self):
        self.assertEqual(self.tasks["OPS-04"]["display"], "Not ready yet")


if __name__ == "__main__":
    unittest.main()
