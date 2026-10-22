# RECOVERY PROCEDURE (AI-infra restart Phase 8)

Status: **current** (promoted by the master 2026-10-22 ~19:00 from `setup/RECOVERY_PROCEDURE.draft.md`, checked against
the files cited; R6 updated for the per-card attempt limit live since 18:35). Components C1–C13:
`AUTOMATION_OPERATIONS.md` §1. Test evidence: `AUTOMATION_TEST_REPORT.md`.

Paths used below:
- `HQ` = `D:\0 Work\0 Pegasus IMC Agency\00 TWN\0 TWN AI\Editing Plugin\00-HQ`
- `REPO` = `D:\0 Work\0 Pegasus IMC Agency\00 TWN\0 TWN AI\Editing Plugin\WhyNotCut`
- `HEAVY` = `C:/Users/LOQ/AppData/Roaming/Claude/side-session-notes/local_263cabbf-75e3-42a1-b384-1753a7bd4dad/heavy.sh`
- `LOCKS` = `D:\ClaudeData\Temp\wnc-locks` · `ACC` = `D:\ClaudeData\accounts`

Who: **Owner** = Yunus by hand. **Master** = an attended Command Center session on the main seat. Claude never starts
helper loops (`Start-Helper.cmd:21-28` refuses inside a Claude session; D-012), never pushes `release/3.0`, never
kills another session's process without the owner's yes.

General rules for every procedure:
- Read before you act; every step has a check. A step whose check fails stops the procedure; write what you saw.
- Never delete a `HOLD by …` STOP file, a client file, or anything inside a helper worktree.
- A process ended with `taskkill /F` through the msys wrapper is logged `rc=0` in `LOCKS\heavy-log.tsv`. **That rc is
  false.** Mark it in the job's own log (precedent: `D:\ClaudeData\setup-phase6\FROZEN_SUITES_CHECKPOINT.md` §4).
- Times: use `python -X utf8 "HQ\tools\stale_suites.py" age <ISO time>` (prints whole minutes). Never compute UTC vs
  Cairo by hand (the shell clock is Cairo labelled "EDT"; `AUTOMATION_RUNBOOK.md` §6, 10-20 11:40).

---

## R1. After a Claude desktop app restart (or a Windows reboot)

1. **Owner:** log in to Windows. Check: within 30 min `ACC\keepalive.log` gets "keepalive: starting auto for hN" for
   each helper whose `ACC\hN\auto\AUTO-ON` exists (verified pattern: 2026-10-20 00:46).
2. **Owner:** open the Claude app (routines live only there).
3. **Master:** list routines (Claude app → Routines, or `list_scheduled_tasks`). Expected enabled set after Phase 8:
   `whynot-cut-hq-intake`, `whynot-cut-primary-report-2`, `whynot-cut-auto-resume-2` (and `whynot-infra-resume-watch`
   only until Phase 8 is DONE). Routines were found **disabled** after restarts on 10-14 and 10-20
   (`AUTOMATION_RUNBOOK.md` §5). Switch any that are off back on (Owner, or Master in an attended session). Check: each
   shows a `nextRunAt`.
4. **Master:** `list_task_runs` (limit 1) for each of the three. A run still `running` from before the restart blocks
   every later run of that routine: if `stale_suites.py age <started_at>` > 60 (report, watchdog) or > 420 (intake),
   stop it with `stop_session <its session id>` (`PRIMARY-REPORT.md:13-19`). Check: the next scheduled run starts.
5. **Anyone:** `python -X utf8 "ACC\helper_loop.py" h1 --alive` and `… h2 --alive` → exit 0 = loop running
   (it checks `auto\loop.lock`: PID is a python and the lock is newer than the last boot). Exit 1 with `AUTO-ON`
   present after 30 min → R3.
6. **Anyone:** Windows tasks: `schtasks /query /tn "WhyNot Cut helpers keepalive"` = Ready; `WNC-Queue` = Ready
   after Phase 8 (Disabled during the D1 stop). Check: `Next Run Time` is not N/A.
7. **Master:** then follow R2 steps 1–5 (stale locks, slots, tickets) before anything resumes work.
8. Resume order (PLAYBOOK §4): master first, then one work session at a time. The watchdog (C3) does this by itself
   once enabled (max 2 per run).

## R2. After a usage-limit cut on the main seat

What resumes it by itself (when the routines are enabled): the next `:37` intake, the next report slot, and the
watchdog at `:13/:43` (resumes executor, Command Center, Builder A; re-runs a report lost ≤ 180 min ago once;
`WATCHDOG.md`). Helpers keep working on their own seats and sleep to their own resets (`helper_loop.py reset_time()`).

Check first, in this order (Master; read-only until a step says otherwise):

1. **Intake lock.** Read `HQ\intake\intake.lock` (`until <time> session <id>`). Judge it only with the three signals in
   `roles\MASTER-INTAKE.md:17-43`: `get_session <id>` isRunning, its status in `list_task_runs`, and
   `stale_suites.py scan-tag <id>` (tagged suites). Stale → rename to `intake.lock.stale-<HHMM>`; only a run listed
   `failed` may have its tagged suites ended with `stale_suites.py end-tag <id>`; never `end-tag` on time alone.
   Check: no `intake.lock`, or one naming a live run.
   *Seen now (17:15):* `intake.lock` = `until 2026-10-22 09:38 session local_b10e116d…`; that run is listed
   `succeeded` (ended 01:34Z). With 0 tagged suites it is stale; the first intake after re-enable renames it.
2. **Heavy-queue slots.** For each `LOCKS\<slot>.d\owner` read `pid`, `winpid`, `label`, `start`.
   `bash "<HEAVY>" status` shows `owner alive` or `STALE (owner gone; the next asker frees it)`. A STALE slot needs no
   action (heavy.sh takes it over: owner dead, or heartbeat silent ≥ 600 s, or ≥ 24 h; `heavy.sh:133-141`). An
   `owner alive` slot whose job is frozen → R4. Check: every slot's label belongs to a job someone owns.
3. **Waiting tickets.** `LOCKS\wait\*.t`: dead tickets (winpid gone) are removed by heavy.sh itself (`scan_tickets`);
   the helper loop ignores dead ones (`helper_loop.py yield_to()` checks `pid_alive`). A live ticket for a session that
   was cut by the limit will start its job when a slot frees; its caller may be gone, so its owner session must read
   the job log after resume. Check: `heavy.sh status` "waiting" list matches sessions that still exist.
4. **Untagged suites of dead sessions** (helper peer-review and executor suites are not tagged, `AUTOMATION_RUNBOOK.md`
   §5b). Find the CHILD python of the suite (the venv launcher `python.exe` always shows 0 CPU) and sample its CPU twice,
   60 s apart (`Get-Process -Id <pid> | Select CPU`). Unchanged CPU and no log growth = frozen → R4/R5 (owner yes needed
   to end it).
5. **Kill records.** Any `taskkill` in this recovery: re-check with `tasklist /FI "PID eq <pid>"` that it is gone; never
   take the `rc=0` in `heavy-log.tsv` or the word "SUCCESS" as a test pass.
6. **Resume.** With 1–5 clean, the routines continue on their own triggers. If the routines are disabled: Master
   follows R1 step 3. Check: next intake reply in the Runs pane, next report row `SENT` in `HQ\PRIMARY_ACCOUNT_INBOX.md`.

## R3. A helper loop died, stalled, or its seat is logged out (Owner steps)

Detect (anyone, read-only):
- `ACC\hN\auto\status.json` `state`: `running` / `idle` / `yielding` / `waiting` (limit) are healthy; `stalled` = 3
  quick failures (AUTO-ON was removed, keepalive will **not** restart it); `stopped` = STOP file.
- `helper_loop.py hN --alive` exit 1 while `AUTO-ON` exists → died; the keepalive restarts it within 30 min.
- Report §2 marks a `running` heartbeat older than 330 min `STALE`.
- `ACC\hN\auto\auto.log` last lines; the run's `run-<stamp>.jsonl` for the error text.

Owner steps:
1. If `stalled`: open the newest `run-*.jsonl`, read the final `result` text. If it says "not logged in", "auth" or
   "401": go to step 2. Otherwise send the text to the master (it may be a broken card or tool; master files a card).
2. Seat logged out: double-click desktop **WhyNot - Helper N** (chat; since 2026-10-22 the old shortcuts are in the
   desktop folder **WhyNot - Old tools**, `control-center\README.md`). Type `/login`, finish the login in the browser
   with that seat's own account (mayar@ for H1, marketing@ for H2). Type `/exit`.
3. Check the seat: run `D:\ClaudeData\accounts\Start-Helper.cmd hN --check` from a normal Windows terminal (not from inside Claude: the login status shown there is not trustworthy). Expect
   "loggedIn", the right e-mail, not the master seat.
4. Start auto: double-click **WhyNot - Helper N AUTO** (or Control Center → helper card → **Start AUTO**). This deletes
   a leftover `STOP`/`IDLE` and writes `AUTO-ON` (`Start-Helper.cmd:114-132`).
5. Verify (anyone): `auto.log` shows "auto loop started for hN (pid …)"; `--alive` exit 0; `status.json` changes
   within ~1 min; at the next keepalive tick no second loop starts (`loop.lock` refuses it: "another auto loop … exits").
6. If the loop died without stalling and the keepalive did not restart it after 30 min: check the task
   (`schtasks /query /tn "WhyNot Cut helpers keepalive" /v`: Last Result 0, Next Run set) and `keepalive.log`; then
   step 4.

Never: close a helper window while its suite runs (orphans the suite, 10-19 incident); start a loop from inside a
Claude session; delete `loop.lock` of a live loop.

## R4. A stuck heavy-queue slot

1. Identify: `LOCKS\<slot>.d\owner` → `pid` (msys), `winpid`, `cpid`, `label`, `kind`, `start`. `heavy.sh status`
   says `owner alive` (else see R2 step 2: nothing to do).
2. Is it really stuck? Find the job's log (by label: helper suites in `hN\auto\` or the worktree, intake suites in
   `HQ\reviews\suites\`, others per the owning session). Sample the child python's CPU twice 60 s apart; check the log's
   last write time. Running and writing = not stuck, however long (suites take ~1 h + queue wait).
3. Find the owner: label prefix `h1-`/`h2-` = helper; `review-`/`peer-` = intake/peer; `g4`, `bl…`, `exec`, `adobe`,
   `ops09` = executor / plan / master sessions.
4. Ask the owning session to end it, or, if that session is gone, get the **owner's yes** in chat to end it. Then end
   the process tree from the top shell down (`taskkill /T /F /PID <winpid of the heavy wrapper>`), record the PIDs.
5. Verify: `tasklist /FI "PID eq <pid>"` = no task; the slot directory is gone or `STALE` and freed on the next ask;
   the waiting job starts (`heavy.sh status`). Append "ended by hand at <time>, rc=0 in heavy-log is false" to the
   job's own log. Record the job as **not run**; it must be re-run (R5).
6. Do not `rmdir` a slot directory by hand while its owner process lives; do not create `FREEZE` unless the owner asks
   for a maintenance window (it holds every new start).

## R5. A frozen or ended suite (re-run, not resume)

A unittest run cannot continue mid-run; "resume" = re-run the unfinished steps on the same snapshot with the same
command (`D:\ClaudeData\setup-phase6\FROZEN_SUITES_CHECKPOINT.md` §3).

1. Read the checkpoint row: snapshot path (kept), command, which steps finished validly. Partial results of a frozen
   run are **not evidence**.
2. Check RAM < 70 % (`heavy.sh status`) — the 10-22 freeze happened with both suites at 83–84 % RAM.
3. Queue ONE at a time: `bash D:/ClaudeData/setup-phase6/resume-frozen-suites.sh verse`, wait for its rc line, then
   `… religious`. (No arg = both in sequence.) Labels: `verse-fix3-resume`, `religious-ok-r4b-resume`.
4. Verify: new files with the `-resume` suffix next to the old ones
   (`D:\ClaudeData\claude-api-lane\work\manual-verse\fix3\suite-c963132-resume.log`;
   `D:\ClaudeData\claude-api-lane\hooks\religious-ok\r4\{full-resume.txt,mutants-resume.txt}`,
   `D:\ClaudeData\Temp\religious-ok\r4\job-resume.log`); a matching row in `heavy-log.tsv`; the owning card/session
   reads the result (these are HIGH-tier religious/verse checks: the owning session decides, not the queue).
5. For any other frozen suite, write the same kind of checkpoint row first (snapshot, command, finished steps), then
   queue the re-run with a `-resume` label.

## R6. A failed card

Bounded paths that already exist:
1. **Run-level (helper loop):** a run that fails in < 120 s three times in a row → `STALLED`, `AUTO-ON` removed → R3.
   A run silent 5 h 10 min or over 8 h is killed and logged (`h2\auto\auto.log:63`, 2026-10-21 00:16); the loop goes on.
   A run that hits a limit sleeps to the reset.
2. **Card-level (intake, `MASTER-INTAKE.md:161-168`):** each review that fails → `## FIX round <n> (YYYY-MM-DD HH:MM)`
   in the card, same builder. HIGH tier: after the 3rd FIX round → `PARKED` + a "Needs Yunus" line. LIGHT tier: after
   the 2nd → ACCEPTED with the open findings under "Known limits" (security basics must still be fixed).
3. **BLOCKED report:** the helper writes `BLOCKED: <exact need>`; the master answers with `## Answer (time)` and READY,
   or parks it for the owner.
4. **Escalation to the owner:** "Needs Yunus" in the card → listed in the next report §5/§6 and in
   `HQ\PRIMARY_ACCOUNT_INBOX.md` as an OPEN request.

5. **Per-card attempt limit (helper loop, live 2026-10-22 18:35; `reviews/P8-helper-loop-r1.md`):** counts in
   `ACC\hN\auto\card-attempts.json`, key = card + number of `## FIX round n` / `## Answer` headers in its card.
   - 6 runs on one card ending PARTIAL in one FIX/Answer round → the loop writes `HQ\inbox\hN\<date>-<HHMM>-<ID>-loop.md`
     (`**Status:** BLOCKED`, "**Written by:** helper_loop.py") and the agent skips the card (prompt rule 4).
     Master: read that helper's PARTIAL reports, then answer (`## Answer (time)`), split, or PARK
     (`MASTER-INTAKE.md` §C). A new FIX round or Answer starts a fresh count; DONE resets it.
   - One more PARTIAL run on that card, or 3 own-card runs in a row with no report and no IDLE → `STALLED` (as 1).
   - A PARTIAL "yielded" run that the loop's own YIELD check cannot confirm → 15 min wait before the next run.
   - Rollback: `ACC\helper_loop.py.bak-p8` + `RELOAD-hN` (the loop re-execs after its current run).

## R7. Git conflict or private-index race

Prevention (every commit to `release/3.0` made with `GIT_INDEX_FILE`, executor only):
1. `H=$(git -C "<REPO>" rev-parse HEAD)` **before** `git read-tree "$H"`.
2. Before committing: `git rev-parse HEAD` still equals `$H`, else abort and start over.
3. After the commit: `git rev-parse HEAD~1` equals `$H`.
4. `git diff --stat HEAD~1 HEAD` lists **only** your files.
5. Before every push: `revert_audit.py` (in the plan session's notes folder
   `C:\Users\LOQ\AppData\Roaming\Claude\side-session-notes\local_263cabbf-75e3-42a1-b384-1753a7bd4dad\`).
   Rule text: `PRIVATE-INDEX-COMMIT-RULE.md` in the same folder.

If a race happened (check 3 or 4 fails, or the audit flags a silent revert):
1. Do **not** fix it with another blind commit. Stop committing on that branch.
2. Tell the executor (only it merges/pushes `release/3.0`). Record the bad commit and the commit it reverted.
3. Executor restores the reverted files from the correct commit in one explicit-path commit, re-runs checks 3–4 and the
   revert audit (precedent: 7cadf05 reverted 264d16f, restored in 4e5ced9, 2026-10-19).
4. Verify: `git diff <good commit> HEAD -- <files>` shows only intended changes; the full suite through heavy.sh.

Merge conflicts on a helper branch: the helper never rebases a shared branch; it reports `BLOCKED: conflict with
<sha>` and the master decides (new FIX round, or the executor applies the patch). Identity: always
`git config --worktree`; read `git config --show-origin --get-all user.name` before any change (`AUTOMATION_RUNBOOK.md`
§6, 10-20 01:35).

## R8. Planned restart of the automation (closing Phase 8)

Order matters: queue and inputs first, then the AI routines.
1. **Owner/Master:** restore the yield list: rename `HQ\YIELD.txt.paused.txt` → `HQ\YIELD.txt` (only if Gate 4 work
   is still running; PLAYBOOK §3d). Check: a waiting `g4…` ticket makes helpers show `yielding`.
2. **Master:** restore parked cards from `HQ\setup\PHASE6_PARKED.json` (each card's original status word) on BOARD and
   in the cards, unless the owner keeps some parked. Check: `hq_status.py` (no flags) lists them READY/FIX.
3. **Owner:** `D:\ClaudeData\setup-phase1\start-automation.cmd` (re-enables `WNC-Queue` and the API-lanes keepalive,
   restores the lanes Startup file). Note: lanes stay HOLD; if the owner wants the lane tasks to stay off, run only
   `schtasks /Change /TN "WNC-Queue" /ENABLE`. Check: `schtasks /query /tn "WNC-Queue"` = Ready.
4. **Owner or attended Master:** switch on `whynot-cut-hq-intake`, `whynot-cut-primary-report-2`,
   `whynot-cut-auto-resume-2`. Leave `owner-update` and `lane-watch` off. Check: `nextRunAt` set for all three; then R2
   step 1 happens at the first intake.
5. **Master:** re-queue the two ended suites (R5), one at a time.
6. Verify the whole: next report row `SENT (session …)`; next intake reply in its Runs pane; both helpers `--alive`.

## R9. Rollback of the restart (back to the D1 stop state)

1. **Owner or attended Master:** Claude app → Routines → switch off `whynot-cut-hq-intake`,
   `whynot-cut-primary-report-2`, `whynot-cut-auto-resume-2`. Check: `enabled: false` in `list_scheduled_tasks`.
2. **Owner:** helpers: desktop **WhyNot - Helper 1 STOP auto** and **Helper 2 STOP auto** (= `ACC\Stop-Helper-Auto.cmd
   hN`: writes `auto\STOP`, removes `AUTO-ON`; the running card is killed within ~1 min, committed work kept). Check:
   `auto.log` "auto loop stopped"; `--alive` exit 1; keepalive leaves them (no `AUTO-ON`).
3. **Master:** pause the yield list again: rename `HQ\YIELD.txt` → `HQ\YIELD.txt.paused.txt`.
4. **Master:** re-park the cards that were un-parked (status word `PARKED (restart hold; was: <old>)`, as on BOARD today);
   update `PHASE6_PARKED.json` if the set changed.
5. **Owner:** `schtasks /Change /TN "WNC-Queue" /DISABLE` and `schtasks /Change /TN "WhyNot Cut API lanes keepalive"
   /DISABLE` (the D1 record in `SETUP_PHASE_TRACKER.md`). Running suites are left to finish (D1 rule).
6. Verify: `hq_status.py` (no flags) shows both helpers `stopped`, no READY cards except those the owner keeps; the
   tracker "D1 stop record" table matches; nothing new appears in `LOCKS\wait\` from routines or helpers.
