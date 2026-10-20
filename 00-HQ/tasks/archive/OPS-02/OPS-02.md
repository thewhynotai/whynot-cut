# OPS-02 — Schedule the four daily PRIMARY reports and prove delivery

- **Assigned:** see BOARD    **Status:** DONE_ARCHIVED (2026-10-20 17:10)    **Tier:** LIGHT    **Milestone:** M0

## Goal
Create the Claude-app scheduled task `whynot-cut-primary-report` (cron 0 9,13,17,21 * * *, Cairo). Each run: runs `hq_status.py --write --sync`, checks the routines are enabled (list_scheduled_tasks), and ends with the Arabic report as its final reply (that session in Yunus's app is the delivery). 09:00 and 21:00 are the full-plan refreshes.

## Acceptance
1. Task exists, enabled, next run shown.
2. One manual run (`run_scheduled_task`) succeeds: report file + inbox row + ops/hq SYNCED + the run's session id recorded in the inbox as SENT.
3. Two scheduled runs observed (list_task_runs) before the task is DONE.
4. ACKNOWLEDGED only after Yunus replies to one report.

## Evidence
- 2026-10-20 02:01 first manual run waited on a permission prompt (Q-005).
- 2026-10-20 02:46 run `local_6b4431c0`: report R-2026-10-20-0247 written, marked **SENT (session local_6b4431c0…)**, ops/hq SYNCED. Delivery channel verified.
- 11:39 the routine was re-created as `whynot-cut-primary-report-2` in bypass mode (no permission prompts); 11:43 run `local_bc75882a` delivered R-2026-10-20-1143 unattended, SENT.
- **Scheduled run 1:** 13:03 `local_0fea5398` succeeded unattended.
- 13:54–16:20 account usage limit: routine runs during the limit fail fast (status failed, not stuck), so later runs are not blocked.
- **Scheduled run 2:** 17:03 `local_9a91a749` succeeded unattended: R-2026-10-20-1704 SENT with its session id, ops/hq
  commit 4484496. Acceptance 1–3 met.
- Closed 2026-10-20 17:10 (LIGHT tier). **Known limit:** acceptance 4 (ACKNOWLEDGED) needs Yunus to answer one report;
  he is away, so it moves to the inbox as Q-006 and is recorded there when it happens.
