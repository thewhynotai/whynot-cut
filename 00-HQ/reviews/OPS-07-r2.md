reviewer: fresh Opus subagent (Command Center delta review)
suite: Ran 6 tests in 0.002s OK (test_stale_suites); read-only `scan-tag local_f2d2f435-…` → "0 suite(s) tagged" with 3 live untagged suites on the PC (none matched)
verdict: FAIL (no P1; 3 P2s, all small prose/one-line fixes)

## r1 findings
| r1 | Status | Evidence |
|---|---|---|
| P1-1 CPU heuristic kills live suites | **FIXED** | CPU logic removed. `tagged()` (stale_suites.py:18-23) selects only `env.exe` whose command line carries exactly `WNC_RUN=<id>`. Live check 2026-10-20: executor `t29`, `h1-setup4` and `peer-BL-16` are untagged and are not selected. |
| P1-2 `--before` no-op | **FIXED** | Ownership is now the tag in MASTER-INTAKE:103. Simulation `sim_ops07.txt`: the tagged tree was ended (children included) and the untagged twin stayed alive. Test line 16-22 covers other ids, untagged runs, non-env processes and a prefix id. |
| P1-3 missing session = stale | **FIXED** | `list_task_runs` is dropped. `get_session` is used, and an unknown state is respected (`lock_stale(..., None)` → False, test line 49). |
| P2-1 prose ≠ function | **FIXED** | MASTER-INTAKE:20-23 and `lock_stale` now state the same three rules. No self-run ambiguity remains, since `get_session` is called on the lock's id. (No `lock-check` CLI: the routine still applies the prose. Acceptable, because the prose and the function now agree.) |
| P2-2 unreadable lock | **FIXED** (different choice) | `parse_lock` → (None, None) → stale (tests 38-40, 48). r1 suggested "stale only if no other run is running". The author chose unconditional stale instead. That is acceptable: an unreadable lock names no session, so nothing gets killed. The worst case is a parallel intake. |
| P3-1 null CPU, P3-2 culture | **FIXED** (code removed) | n/a |
| P3-3 `end` checks nothing | **FIXED** | `end-tag` scans again before each kill (line 58). A reused pid would not carry the tag. |
| Acceptance 3: runbook | **NOT FIXED** | `AUTOMATION_RUNBOOK.md:65-67` still only records the incident ("Permanent fix → card OPS-07"). There is no recovery procedure: the tag, `end-tag`, and what to do by hand. → P2-4 |
| Goal 2: helper `peer-*` orphans | **NOT ADDRESSED** | Helper peer suites carry no tag, so `h1-bl02-final`-type orphans (00:48→03:52) remain. → P3-1 (write it as a known limit) |

## Checks done on the questions asked
- **`taskkill /T` reaches the python child.** It does. Live tree observed: env.exe 10320 → venv launcher python.exe 28284 → real python.exe 61344 (ParentProcessId chain intact below env.exe; the chain is broken only ABOVE env.exe). `/T` follows ParentProcessId down, so killing env.exe takes the launcher, the interpreter and any test subprocesses. The simulation shows children killed ("child process of PID 62036"). Caveat: the simulation started env.exe from PowerShell, not through heavy.sh, so slot release was not shown. See P3-2.
- **Can a live run carry a dead id?** Not via reuse: ids are `local_<uuid>`. `get_session "self"` from a subagent returns the PARENT session's id (checked here), so the reviewer subagent tags with the intake run's id, which is correct. The regex boundary blocks prefix matches. A quoted `"WNC_RUN=…"` would fail to match. That is fail-safe (it skips the suite, never wrongly kills one), but it is not tested (P3-3). Auto-resume (`whynot-cut-auto-resume`) targets only listed sessions and never intake runs, so a "dead" intake run is not resurrected by the watchdog.
- **Reviewer forgets the tag.** The orphan is then not cleaned: the pre-OPS-07 behaviour, where the suite runs to the end and then frees the slot. That is degraded but not dangerous, so it is acceptable as a known limit. If the placeholder is pasted literally, `WNC_RUN=<this …>` is a bash redirection error and the suite fails loudly, so it cannot run mis-tagged.
- **`isRunning` reliability.**
  - The dead incident run 2d542916 shows `isRunning:false`, which is correct.
  - But `list_sessions` right now shows two sessions with `isRunning:true` whose transcripts end in a bare tool call hours ago: 2474be8e at 23:01Z and ea7e31f2 at 00:52Z. So `isRunning` can stay true for a dead session. That is fail-safe, because the lock is held until `until`. It does feed P2-1, though.
  - The opposite direction (false while still working) is unverified. See P2-3.

## Findings
**P2-1 MASTER-INTAKE.md:23-26: an EXPIRED lock triggers `end-tag` even when its session is still running.**
- Step 0.1 runs `end-tag` on *any* stale lock that names a session, including one that is stale only by time. The 6 h `until` is written once, before the review, and is never refreshed.
- heavy-log shows wait+run totals for suites of up to 5.5 h:
  - builderA-t59-suite: 5199 s wait + 14475 s run;
  - h1-setup2: 3.8 h.
- Add setup, focused tests and mutants, or a gate holding the machine for up to 6 h, and a live review passes 6 h. The next intake then kills its live suite.
- The killed run also later "deletes the lock whatever happens" (line 29). That deletes the NEW run's lock, so a third intake can start. Result: two or more intakes at once.
- Fix:
  - run `end-tag` only when `get_session` says `isRunning:false`;
  - on expiry with `isRunning:true`, take over the lock but do not kill, and log a STATUS risk;
  - at the end, delete the lock only if it still names this run's session;
  - add a test, e.g. a `should_end_tag(until, sid, running, now)` helper, or note the rule beside `lock_stale`.

**P2-2 `stale_suites.py:23`: a dead run's suite that is still WAITING in the heavy queue is missed and later runs as an orphan.**
- `end-tag` matches only `env.exe`, and env.exe exists only after admission.
- Live right now: 2 heavy.sh suites are present and only 1 env.exe, so waiting is common.
- The dead run's waiting heavy.sh keeps its ticket, which blocks the new intake's suite under first come, first served. It then starts the full orphan suite: 45–240 min, holding a slot.
- The dead id is forgotten once the lock is replaced, so no later run cleans it. This breaks acceptance 2 in that case.
- heavy.sh's bash.exe command line DOES carry the full argv. Verified: `bash.exe …/heavy.sh suite h1-setup4 -- env PYTHON…`.
- Fix:
  - also select `bash.exe` whose command line contains `heavy.sh` and the exact `WNC_RUN=<id>` token;
  - `taskkill /T` that waiting bash. Its EXIT trap does not run under /F, but the ticket and slot go stale anyway (alive_k=1);
  - add a test row for it.

**P2-3 MASTER-INTAKE.md:96: the reviewer subagent may run in the background, so `isRunning` may read false while the review is live.**
- Subagents run in the background by default. If the unattended main turn ends while the reviewer works, waiting for the notification, `get_session` can report `isRunning:false`. The next :37 run then kills a LIVE suite, which is the r1 failure class.
- This is unverified either way.
- Fix: in step 1B, write "spawn it with `run_in_background: false` and wait in the same turn". Optionally, in step 0.1, treat `isRunning:false` with `lastActivityAt` under 15 min as running.

**P2-4 AUTOMATION_RUNBOOK.md:65-67: acceptance 3 is not met.**
- Add a short "Run cut by a limit" procedure:
  - the lock format with `session`;
  - `scan-tag` and then `end-tag <id>` (read the `.stale-HHMM` file for the id);
  - untagged and helper suites are never ended by the tool.

**P3-1** Write Goal 2 (helper `peer-*` / `h1-*` orphans, not tagged) into the card as a known limit, or add `WNC_RUN` to the helper loop's suite command too.

**P3-2** The real-environment simulation bypasses heavy.sh, so it does not prove that the dead run's heavy.sh notices the TerminateProcess'd env.exe and frees its slots. heavy.sh's `alive_k` keeps a slot while its bash pid lives. The 06:05 hand-fix ("both waiting suites started") suggests that it works. One more simulation through `heavy.sh suite` with `HEAVY_LOCKS=<temp>` would close this.

**P3-3** `tagged()` gives a quoted `"WNC_RUN=<id>"` token a silent miss. That is fail-safe, but add a test row so the behaviour is intentional. There is also no test of `main()`'s end-tag path (re-scan before kill) with a mocked `_env_procs`/`subprocess.run`.

**P3-4** Step 0.1 does not say what to do when `get_session` errors or the session is not found (archived or deleted). An unattended model may read that as "dead". State: error/not found → judge by time only (matches `lock_stale(..., None)`). Also, `rename to intake.lock.stale-<HHMM>` can collide with an existing name: add "-<n> if taken".
