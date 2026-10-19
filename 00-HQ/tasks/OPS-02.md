# OPS-02 — Schedule the four daily PRIMARY reports and prove delivery

- **Assigned:** see BOARD    **Status:** NOT READY (needs OPS-01)    **Tier:** LIGHT    **Milestone:** M0

## Goal
Create the Claude-app scheduled task `whynot-cut-primary-report` (cron 0 9,13,17,21 * * *, Cairo). Each run: runs `hq_status.py --write --sync`, checks the routines are enabled (list_scheduled_tasks), and ends with the Arabic report as its final reply (that session in Yunus's app is the delivery). 09:00 and 21:00 are the full-plan refreshes.

## Acceptance
1. Task exists, enabled, next run shown.
2. One manual run (`run_scheduled_task`) succeeds: report file + inbox row + ops/hq SYNCED + the run's session id recorded in the inbox as SENT.
3. Two scheduled runs observed (list_task_runs) before the task is DONE.
4. ACKNOWLEDGED only after Yunus replies to one report.

## Evidence
(filled at close)
