# OPS-07 — A run cut by a usage limit must not freeze the intake or the heavy queue

- **Assigned:** MASTER (Command Center)    **Status:** READY    **Tier:** LIGHT    **Milestone:** M0

## Why (incident 2026-10-20)
The 03:37 intake run took the lock "until 09:38" (6 h, own Opus review) and queued `review-BL-16`; the account hit its
usage limit at 03:54. The run died, but (1) the lock kept every later intake run out until 09:38, and (2) the review
suite stayed in a heavy slot for 140 min with frozen CPU, blocking `h1-setup4` (ENV-01) and `peer-BL-16` (OPS-05).
Fixed by hand at 06:05 (stale lock renamed `intake.lock.stale-0338-limit`, orphan suite PID 68456 ended).
The same pattern hit H1's `h1-bl02-final` (00:48 → ended 03:52).

## Goal
1. The intake lock records the run's session id; a new run treats the lock as stale when that session is no longer
   running (`get_session` / `list_task_runs` status failed/succeeded), not only when the time passes.
2. Heavy jobs whose owner session died are released: `heavy.sh` already marks STALE when the owner pid is gone; make
   the intake (and the helper loop's peer review) end its own job when the run is cut, or record the job label in the
   lock so the next run can end the orphan before re-reviewing.

## Acceptance
1. Tests: a lock whose session is failed → taken over; a lock whose session is running → respected.
2. A simulated cut run leaves no slot held for more than one intake period.
3. MASTER-INTAKE.md and the runbook updated.

## Closure (2026-10-20 06:15) — DONE_ARCHIVED
- Change: `00-HQ/tools/stale_suites.py` (tag-based orphan ending + tested lock rules), `roles/MASTER-INTAKE.md`
  step 0.1 (lock with session id; stale rule; `end-tag` only for a run known dead; delete only your own lock) and
  step 1B (`env WNC_RUN=<session id>` on the review suite; reviewer in the foreground); runbook §5b.
- Tests: `test_stale_suites` red first each round → 6/6 OK; `test_hq_status` 28/28 still OK.
- Real-environment simulation (unsandboxed terminal): tagged env.exe tree ended, untagged twin alive
  (`scratchpad\sim_ops07.txt`).
- Reviews: `reviews/OPS-07-r1.md` FAIL (P1: CPU heuristic would kill live suites — the design was replaced, nothing was
  ever killed with it) → `OPS-07-r2.md` FAIL (no P1; 3 P2 + runbook) → all fixed in round 3 (LIGHT tier: closed after
  the 2nd fix round with known limits).
- Known limits: slot release through heavy.sh itself not simulated (the kill ends heavy.sh's child, heavy.sh then
  frees the slot as for any finished job); helper peer-review / executor suites are not tagged (runbook §5b);
  `isRunning` for a run paused on a permission prompt counts as alive (safe side).
