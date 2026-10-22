# Review r1 — Phase 8 report fields (`00-HQ/tools/hq_status.py`) — 2026-10-22 ~18:30

Reviewer: fresh `oh-my-claudecode:code-reviewer` subagent (read-only), LIGHT tier. Saved here by the master from the
reviewer's returned text (shortened, every finding kept). Reviewer ran the 32 tests (OK) and the no-flag dry run only.

**Verdict: PASS-WITH-MINORS.** No P1. Checked: milestone regex vs the real plan (M0 `[x]`, M1–M10 `[ ]`), the
"since" time is taken before `inbox_reports()` and compared with `>=` on the minute (no missed handoff), naive local
time vs `st_mtime` on one PC, older snapshots without `time` (ValueError caught), sort keys unique.

## P2
1. Helper lines do not name the account (brief: "current account assignments"). Fix: `H1 (mayar@)`, `H2 (marketing@)`.
2. No same-minute boundary test (`>=` vs `>` would pass); no test of a `prev` without `time`.

## P3
1. Existing bug: H2 file names keep HHMM in the task name (`0316-BL-04`), also in §5 and TASK_QUEUE.
2. "Newest per task" can hide one of two same-window reports for one task (rare; intended for revisions).
3. mtime = last edit, so an edited report is listed again (repeat over miss).
4. A `prev` with no/bad `time` silently drops the handoff line.
5. `current_milestone` catches only `OSError` (non-UTF-8 plan kills the run); `"time": null` raises `TypeError`.
6. Regex `M\d+` is not limited to §3 (fine today). (Reviewer also said `M11` would not match; it does: `\d+`.)
7. The PRIMARY line is a fixed role, not live activity.

## Master disposition (fix round 1, ~18:33)
- P2-1 fixed (`SEATS`, test). P2-2 fixed (17:00:30 vs "17:00" listed; `prev` without/null `time` → "مش معروفة").
- P3-1 fixed (regex `(?:\d{4}-)?`, test): TASK_QUEUE `latest_report` for H2 cards is now filled too.
- P3-4 fixed (explicit "not known" line). P3-5 fixed (`(OSError, ValueError)` / `(ValueError, TypeError)`).
- P3-2, P3-3, P3-6, P3-7: known limits. P3-6's `M11` remark is wrong (checked).
- Result: `test_hq_status.py` + `test_agency_live.py` **53/53 OK**; dry run `D:\ClaudeData\setup-phase8\hq_status-dryrun2.txt`
  shows `H1 (mayar@)`, milestone `M1 — Gate 4 → v3.0.0-p4`, BL-04 under its real id. Backups:
  `D:\ClaudeData\setup-phase8\hq_status.py.bak`, `test_hq_status.py.bak`. No round 2 (LIGHT).
