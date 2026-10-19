# OPS-01 — Status generator, Arabic reports and GitHub mirror for 00-HQ

- **Assigned:** COMMAND CENTER (master)    **Model:** Opus 5.5    **Size:** M    **Status:** DONE_ARCHIVED (2026-10-20 02:00)
- **Tier:** LIGHT (internal tooling: tests first, ONE independent review, no mutation run, ≤ 2 fix rounds)
- **Milestone:** M0 Operations bootstrap. **Depends on:** nothing. **Unblocks:** OPS-02 (scheduled delivery).

## Goal
One deterministic command (no AI tokens) that reads the real state (BOARD, cards, intake state, helper loops, git,
API budget, RAM) and writes: `00-HQ/TASK_QUEUE.yaml`, a dated Arabic report in `00-HQ/reports/`, an entry in
`00-HQ/PRIMARY_ACCOUNT_INBOX.md`, the auto block of `PROJECT_PLAN_AR.md`; and, with `--sync`, mirrors 00-HQ to the
branch `ops/hq` and verifies the remote SHA.

## Why
The charter needs a live dashboard, four reports a day and a Git-backed copy of the management state, without
manufactured progress and without spending AI usage on bookkeeping.

## Fence (only these paths)
`00-HQ/tools/hq_status.py`, `00-HQ/tools/test_hq_status.py`, outputs listed above, `D:\WNC-work\ops` (ops/hq worktree).
Never the master tree's working files; git there is read-only (`rev-parse`, `rev-list`, `ls-remote`).

## Acceptance
1. BOARD table rows parse into queue items (id, title, owner, status, card) — tested.
2. Helper heartbeat from `status.json`; AUTO-ON/STOP flags shown — tested.
3. Git: local vs remote SHA → `SYNCED` / `LOCAL_AHEAD n` / `REMOTE_AHEAD n` / `DIVERGED` / `REMOTE_UNREACHABLE` — tested.
4. API state read from `BUDGET-API.md` (never invented) — tested.
5. Plan auto block replaced only between the markers; text outside unchanged; missing markers = error, file untouched — tested.
6. Inbox append is idempotent per message id; status `FILED` — tested.
7. "Done since last report" comes from a status diff against the previous snapshot, not from claims — tested.
8. `--sync`: no change → no commit; change → commit + push + remote SHA equals local, else `PUSH_FAILED` recorded — tested
   against a temporary bare remote.
9. Real run on this PC produces all outputs; the ops/hq branch shows on GitHub with the same SHA.

## Required tests
`python -X utf8 -m unittest 00-HQ/tools/test_hq_status.py` all pass; one real run; one independent fresh review.

## Closure evidence (2026-10-20 02:00)
- **Tests:** red first (11 errors) → green 11/11; fix round 1: 8 new tests red → 19/19; fix round 2: 6 new tests (4 red) → **25/25 OK** (`python -X utf8 -m unittest test_hq_status`, run from `00-HQ/tools`).
- **Reviews (independent, fresh Opus):** `reviews/OPS-01-r1.md` PASS-WITH-MINORS (5 P2) → all fixed; `reviews/OPS-01-r2.md` delta: the 5 P2 FIXED, 1 new P2 (non-ASCII names in `git ls-files`) → fixed in round 2 with a test. LIGHT tier: closed after the 2nd fix round.
- **Real runs:** reports `reports/2026-10-20-0136.md`, `-0150.md`, `-0159.md`; ops/hq local = remote at each run; last 450fbe05 (git ls-remote).
- **Acceptance 1-9:** met (r1/r2 tables); line 3 has unit coverage on the label only (git_state itself checked by real runs).
- **Known limits (accepted, LIGHT):** a pipe inside backticks in a BOARD cell breaks that row; STALE only after 330 min silence; the mirror filters by type and 1 MB size but has no name deny-list (fine while the repo is private: it holds staff e-mails and executor patches); the `report_verdict` helper is tested but production reads the same map inline.
- **Archive:** this packet → `tasks/archive/OPS-01/`; the code stays live in `00-HQ/tools/`.
