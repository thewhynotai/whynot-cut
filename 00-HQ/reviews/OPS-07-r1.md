reviewer: fresh Opus subagent (Command Center review)
suite: Ran 7 tests in 0.002s OK (test_stale_suites); live `stale_suites.py scan` at 06:06 → "0 frozen suite(s)"
verdict: FAIL

## Acceptance
1. Tests: a failed session's lock is taken over, a running one is respected: **OK as a function**, with a gap. `lock_stale`
   is tested, but the unattended routine never calls it. It reads the prose in MASTER-INTAKE 0.1, and the prose and
   the function disagree (P2-1).
2. A simulated cut run leaves no slot held longer than one intake period: **NOT OK**. There is no simulation test, and
   the scan as written would end LIVE suites (P1-1, P1-2). Goal 2's helper side (orphaned `peer-*` suites after a
   helper hits its limit) is not addressed.
3. MASTER-INTAKE.md and the runbook are updated: **PARTLY**. MASTER-INTAKE has step 0.1. AUTOMATION_RUNBOOK.md:65-67
   only records the incident and does not describe the new recovery procedure.

## Findings
**P1-1 `stale_suites.py:54-56,22`: the scan lists the venv launcher stub of every live suite.**
- On Windows, a venv `Scripts\python.exe` is a launcher. It spawns the real interpreter as a child and keeps 0 CPU
  forever.
- Measured live:
  - executor `t29-suite`: launcher pid 46660 at cpu 0→0, while its child 36608 had 731 s of CPU;
  - `h1-setup4`: launcher 28284 at 0.0156→0.0156.
- With `frozen(procs, now+15min, before=09:38)` on the real samples, the result is `[46660]`. From 06:17 today, the
  scan would list the executor's live suite. Then `end` runs `taskkill /T /F` on that launcher and kills its whole
  tree.
- The suite heavy log shows normal suites take 45–60 min, and some take up to 241 min. So FROZEN_MIN_AGE=60 gives no
  protection.
- Even the real interpreter showed only 0.06 s of CPU in 20 s while a test waited on a subprocess. A test's child
  processes are not counted.
- Fix:
  - group the processes by tree and sum the CPU of all descendants;
  - drop any process whose child is a matched python;
  - sample over at least 3 minutes, not 20 s.

**P1-2 MASTER-INTAKE.md:25: `--before "<the stale lock's until>"` is effectively a no-op.**
- `until` is start+30 min or start+6 h. In the incident it was 09:38 while the time was 06:05, so every suite on the
  PC qualifies: the executor's, the builders' and the helpers' `peer-*` suites.
- `--before` needs the dead run's start and end time, and even those are not ownership.
- Ownership is knowable. WMI cannot see a process's working directory, and the parent chain is broken after
  heavy.sh's `exec`: env.exe's parent was already gone. But env.exe's command line IS visible.
- Fix:
  - add `WNC_RUN=<session id>` to the intake's `env ...` suite command (MASTER-INTAKE:104);
  - have `scan --session <id>` list only suites whose ancestor env.exe command line contains that id;
  - alternatively, read `wnc-locks/*.d/owner` for `label=review-*` and use `/proc/<cpid>/winpid`.
- Keep the CPU test only as a second guard.

**P1-3 MASTER-INTAKE.md:20-23 and `stale_suites.py:49`: a lock whose session is missing from the runs list counts as
stale.**
- The step asks for `list_task_runs` with limit 5, and the task fires hourly (`totalRuns` grows while a run is live).
- A live 6-hour review run drops out of the newest 5 runs after about 5 h. `runs.get(sid)` then returns None, so the
  lock counts as stale. The result is a parallel intake, which breaks "never two reviews", and then the P1-1 kill.
- Fix:
  - only `failed` or `succeeded` makes a lock stale; a session that is missing counts as alive;
  - check that session with `get_session(sid)`, or use limit 50;
  - add a test for this case.

**P2-1 `stale_suites.py:50` versus MASTER-INTAKE.md:22: two rules for old locks.**
- The prose says "no intake run *other than this one*" is running.
- The function checks for any `running` run. With the real `list_task_runs` output, which includes the current run,
  an old-format lock is never taken over before it expires.
- Fix: add a `self_id` parameter and exclude it, and test it with the current run included. Better still, have the
  routine call `stale_suites.py lock-check <lockfile>` instead of re-deriving the rule from prose.

**P2-2 `parse_lock`: unreadable locks are not handled.**
- An empty or garbled lock raises IndexError or ValueError.
- `until … session` with no id is silently read as old format.
- MASTER-INTAKE says nothing about an unreadable lock, so the bypass-mode routine is left to improvise.
- Fix:
  - return `(None, None)` for an unreadable lock;
  - treat it as stale only when no other run is `running`;
  - write that into step 0.1.

**P3-1 `stale_suites.py:67`: a missing CPU value counts as frozen.**
- `cpu or 0` turns an unreadable CPU (Get-Process failed, or the process exited) into 0, which reads as frozen.
- Fix: skip any process with a null CPU.

**P3-2 `stale_suites.py:56`: the date format depends on the culture.**
- `ToString('yyyy-MM-dd HH:mm:ss')` uses the current culture, and a culture with a non-Gregorian calendar breaks it.
- Fix: pass `[cultureinfo]::InvariantCulture`.

**P3-3 `stale_suites.py:80`: `end <pid>` checks nothing before it kills.**
- Fix: before the kill, check that the pid still has the same CreationDate and still matches `unittest discover`, so a
  reused pid is never killed.
