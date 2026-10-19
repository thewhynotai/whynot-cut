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
