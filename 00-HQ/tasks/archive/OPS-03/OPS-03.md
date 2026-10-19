# OPS-03 — Release-preview refresh check without lane-watch

- **Assigned:** see BOARD    **Status:** READY    **Tier:** LIGHT    **Milestone:** M0

## Goal
lane-watch (disabled, outdated) also checked whether «خد دا كوبي» folders are behind origin/release/3.0 and queued `D:\ClaudeData\release-preview\refresh.py`. Add that zero-token check (`refresh.py --check`, exit 10 = behind) to the report run and list it in the report; keep lane-watch disabled and mark it retired in AUTOMATION_RUNBOOK.

## Acceptance
1. Report shows preview folder label/sha vs origin.
2. No build runs inside the report run; a refresh is only queued through wnc-queue.
3. Runbook updated.

## Evidence
(filled at close)

## Closure (2026-10-20 02:20) — DONE_ARCHIVED
- Change: `00-HQ/tools/hq_status.py` (`preview_label`, `should_queue_refresh`, `refresh_failure`, `preview_state`, `preview_line`; the report's §3 shows the preview folders, §5 a FAILED refresh); runbook marks lane-watch RETIRED.
- Tests: `Preview` class 3 tests (red first, each round) → full file **28/28 OK**. Dry run shows `PREVIEW-3.0.0-p4 @ 322d8a5d — up to date`.
- Review: `reviews/OPS-03-r1.md` PASS-WITH-MINORS → P2-1 (waiting job missed: now `wnc-queue list --json`), P2-2 (FAILED refresh.log line), P2-3 (add without try), P2-4 (status failure read as empty) fixed.
- Known limits (P3): origin sha not printed; only the Windows folder's LABEL is read; bare `bash` on PATH; a lock older than 4 h blocks queuing.
