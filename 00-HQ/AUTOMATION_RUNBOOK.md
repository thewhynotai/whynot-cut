# AUTOMATION RUNBOOK — what runs by itself, how to check it, pause it, stop it and recover

Owner: Command Center (master). Words used here: **configured** (exists) · **scheduled** (has a trigger) ·
**running** (a process/session is live now) · **delivered** (the recipient can see it) · **verified** (evidence below).

## 0. Routine set since 2026-10-20 11:50 (Command Center, Yunus: «احلها بدون اي ابروف مني»)
- `whynot-cut-primary-report-2` (09/13/17/21, **Bypass mode**, notifies the Command Center) — `roles/PRIMARY-REPORT.md`.
- `whynot-cut-auto-resume-2` (:13/:43, **Bypass mode**) — `roles/WATCHDOG.md`: stops stuck routine runs, resumes the
  executor, the Command Center (`local_a36b6974…`) and Builder A, including when their transcripts are too big to read.
- `whynot-cut-hq-intake` (:37, Bypass) — `roles/MASTER-INTAKE.md`.
- Retired (disabled, kept for history): `whynot-cut-auto-resume` v1 (no Command Center target, blind to huge
  transcripts), `whynot-cut-lane-watch`, `whynot-cut-owner-update`; `whynot-cut-primary-report` v1 deleted (it ran in
  default mode and hung on permission prompts).

## 1. Routine inventory (audit 2026-10-20 01:15 Cairo, after the 00:45 reboot)

| Routine | Kind | What it does | State found | Decision | Evidence |
|---|---|---|---|---|---|
| Helper AUTO loop h1 | Windows: `helper_loop.py` (pythonw), keepalive-started | One headless `claude -p` per BOARD card on Mayar's seat; sleeps through limits | **RUNNING** (pid 21616, run 1 on BL-02 since 00:46) | IN_USE / HEALTHY | `D:\ClaudeData\accounts\h1\auto\status.json`, `auto.log` |
| Helper AUTO loop h2 | same, marketing@ seat | same | **STOPPED** by STOP file 2026-10-19 20:55 (AUTO-ON removed) | IN_USE — restart (owner 21:25: «اوعى توقفهم») | `h2\auto\status.json` |
| Windows task "WhyNot Cut helpers keepalive" | Task Scheduler, 30 min + logon | Restarts a loop whose `AUTO-ON` exists | Ran at 00:46 after the reboot (restarted h1) | IN_USE / HEALTHY | `D:\ClaudeData\accounts\keepalive.log` |
| Windows task "WhyNot Cut API lanes keepalive" + Startup | Task Scheduler | Starts lane supervisors, reaper, board | Lanes all STOP/HOLD → nothing starts | IN_USE (idle by design) | `claude-api-lane\STOP`, lane folders |
| `lane_reaper.py` monthly guard | Python process | Budget guard; on a new month removes STOPs that start with "budget guard" | Lane 1/5 STOPs converted to **HOLD by owner** 2026-10-20 | IN_USE — can no longer release the API | `00-HQ/BUDGET-API.md` |
| `wnc-queue` / `heavy.sh` | Windows task + bash | Shared heavy-job queue (2 slots, RAM gate) | Present | IN_USE | `D:\ClaudeData\jobs` |
| Claude task `whynot-cut-hq-intake` | Claude app, hourly :37 | Receives helper reports, independent review, verdicts, MERGE-QUEUE | **DISABLED** (last run 10-19 20:37; cause unknown — seen twice before) | IN_USE → re-enable | `list_scheduled_tasks` |
| Claude task `whynot-cut-auto-resume` | Claude app, :13/:43 | Nudges limit-stopped Gate 4 sessions (2 per run, staggered) | **DISABLED** (last run 10-19 20:22) | IN_USE → re-enable | same |
| Claude task `whynot-cut-lane-watch` | Claude app, hourly | Lane health, guard, builder idle nudges, release-preview refresh | **DISABLED** | RETIRED 2026-10-20: lanes are all held; builder nudges contradict "BLD-A/B finish and END"; its release-preview check (step 0f) now runs in every PRIMARY report (`hq_status.py` → `refresh.py --check`, queues one rebuild through wnc-queue when behind; OPS-03). Stays off | same |
| Claude task `whynot-cut-owner-update` | Claude app, 10:00/21:00 | Asks the plan session to message Yunus | **DISABLED** | DUPLICATE of the PRIMARY reports (D-005). Stays off | same |
| 7 one-shot `whynot-cut-resume-*` | Claude app | Past one-shot resumes | disabled, fired | HISTORICAL | same |
| Claude task `whynot-cut-primary-report` | Claude app, 09/13/17/21 | Runs `hq_status.py`, delivers the Arabic report into Yunus's app | NEW (OPS-02) | — | OPS-02 card |

Sessions (Yunus's account) at audit time: none running. Executor, BLD-A, BLD-B and the 00-HQ chat stopped on the
usage limit 2026-10-19 ~21:30 ("resets 12:50am"). UI-P4 and REL-PREVIEW are ENDed/archived. The plan session is idle.

## 2. How the system keeps going without Yunus

1. **Helpers:** each loop takes the next READY card on BOARD for its seat, sleeps through usage limits, and is
   restarted by the keepalive after a crash or reboot. Peer review crosses accounts (H2 reviews H1's DONE code).
2. **Intake (hourly):** turns DONE/BLOCKED reports into verdicts and refills the queues.
3. **Executor + Gate 4 builders:** the auto-resume watchdog nudges them after a limit (max 2 per run).
4. **Reports:** `whynot-cut-primary-report` 4 times a day.
5. **Limits of this:** the Claude-app tasks run only while the Claude app is open (a run missed while it is closed
   fires on the next launch). Windows login is needed after a reboot (the keepalive runs at logon). AI work stops
   during each account's usage limit and resumes by itself after the reset. No paid API runs at all until
   `BUDGET-API.md` says AUTHORIZED.

## 3. Checks (copy-paste)

- **Since 2026-10-22: WhyNot Control Center** (desktop shortcut **WhyNot - Control Center**, `00-HQ\control-center\`):
  browser dashboard (all 3 accounts, context, tasks with lifecycle, alerts, history; zero LLM tokens) + one terminal per
  account; typing in a helper's tab reaches its running session through the profile hook (`ownermsg.py`), and an idle
  loop wakes for it (`helper_loop.owner_message_waiting`). The Agency LIVE shortcut was retired (backup in
  `D:\ClaudeData\control-center\backups\`); `agency_live.py` stays as the text view and as a library the control center
  imports. Undo: `python -X utf8 00-HQ\control-center\app\install.py --undo`.

- Live view of the whole agency (2026-10-21): desktop shortcut **WhyNot - Agency LIVE** = `00-HQ\tools\agency_live.py`
  (read-only: each session and helper with model, level, status and what it does; the main-account limit; routines;
  tasks; what needs Yunus). One helper's raw steps: `python -X utf8 D:\ClaudeData\accounts\helper_peek.py h1`. The old
  helpers-only `helpers_live.py` is kept; the old shortcut's backup is in `D:\ClaudeData\backups\shortcuts`.
- Routines: in the Claude app, sidebar **Routines** (or ask the Command Center "routines status").
- Status now: `python -X utf8 "D:\0 Work\0 Pegasus IMC Agency\00 TWN\0 TWN AI\Editing Plugin\00-HQ\tools\hq_status.py"`.
- Heavy queue: `bash C:/Users/LOQ/AppData/Roaming/Claude/side-session-notes/local_263cabbf-75e3-42a1-b384-1753a7bd4dad/heavy.sh status`.

## 4. Pause, resume, safe stop

| Want | Do |
|---|---|
| Pause one helper | Desktop **WhyNot - Helper N STOP auto** (finishes within ~1 min, committed work kept) |
| Resume one helper | Desktop **WhyNot - Helper N AUTO** |
| Pause all AI routines | Claude app → Routines → switch off `hq-intake`, `auto-resume`, `primary-report` |
| Emergency stop everything | Both helper STOP shortcuts + switch off the 3 routines. The API lanes are already held |
| Never | Close a helper's window while its test runs (orphans the suite, 10-19 incident); delete a `HOLD by …` STOP |

## 5. After a Windows restart

1. Log in to Windows. The keepalive restarts helpers whose `AUTO-ON` exists (verified 2026-10-20 00:46 for h1).
2. Open the Claude app (the routines live there).
3. Check the routines are **enabled** (they were found disabled after restarts on 10-14 and 10-20; a person must switch
   them back on — the Command Center does it in an attended session).
4. Open **Agency LIVE** and check neither helper shows `LOOP NOT RUNNING`.

## 5b. After a usage-limit cut (OPS-07)
- The intake recovers by itself (MASTER-INTAKE step 0.1): a lock whose run is dead (`get_session` isRunning false)
  is renamed `intake.lock.stale-<HHMM>`, and `00-HQ/tools/stale_suites.py end-tag <dead session id>` ends only the
  processes tagged `WNC_RUN=<that id>` (its review suites, running or queued). A live run is never touched.
- By hand (any session): `python -X utf8 00-HQ\tools\stale_suites.py scan-tag <session id>` lists, `end-tag` ends.
- Not covered (known limits): helper peer-review and executor suites are not tagged, so a frozen one is still ended by
  hand after checking its CPU on the CHILD python (the venv `python.exe` launcher always shows 0 CPU).

## 5c. Unattended runs and the OMC hooks (from 2026-10-22, D-011)
Every routine or headless run opened in the `Editing Plugin` folder (resume watchdogs now; intake and report when they
return in restart Phase 8) loads OMC's hooks: `context-guard-stop` can block a Stop up to 2 times at 94 % context
(extra turns), and OMC's permission-handler auto-approves read-only `ls`/`git status`/`cat`/`sed`/`rg`. Session start
is ≈ 1.4 s slower. Keep routine prompts narrow. If a routine misbehaves, open it in a folder without OMC instead
(e.g. `D:\ClaudeData\routines`) and file a card.

## 6. Incidents
- 2026-10-23 06:20: the report routine `whynot-cut-primary-report-2` was found `enabled: false` (last run 10-22
  18:03Z), so the 09:00 report would not have fired. The restart handoff lists it ON, and nobody recorded turning it
  off. The master re-enabled it. It also disabled `whynot-infra-resume-watch` (C4): Phase 8 is DONE and the handoff
  lists C4 as retired. **Rule:** at each master nudge, check `list_scheduled_tasks` against the expected set
  (C1 intake, C2 report, C3 watchdog = enabled).
- 2026-10-22 21:09–21:35: **watchdog re-enabled too early in the restart, then off again (owner).** The Phase 8 master
  (Command Center, Phases 2–8 session) re-enabled `whynot-cut-auto-resume-2` at 21:09 + Run now 21:11 as
  RECOVERY_PROCEDURE R8 step 4 (recorded in the tracker row 8; `primary-report-2` had been re-enabled ~18:48, its
  21:03 run = test B1/B8). The watchdog nudged the executor and Command Center (21:11) and Builder A (21:24 scheduled
  run); their Gate 4 work filled the heavy queue (~15 jobs, RAM 83–85 %). **Owner decision 21:35** (relayed by the
  infra-audit session, quoted: "switch whynot-cut-auto-resume-2 off again until Phase 8 is done … let the Gate 4
  sessions finish only the step they're in"): that session disabled the routine; the master told the executor and
  Builder A (21:4x) to finish only the step in flight, checkpoint, start no new heavy job and drop their other queued
  jobs. **Lesson:** R8 step 4 re-enables the watchdog only as the LAST step of Phase 8 (it wakes every Gate 4 track
  at once), with the queue and RAM checked first. `whynot-cut-hq-intake` stays off until then too.
- 2026-10-22 04:15: **planned full stop (owner, AI-infra restart D1).** Routines auto-resume-2, hq-intake,
  primary-report-2 and the 10:00 one-time remeasure disabled; both helpers STOP + AUTO-ON removed; Windows tasks
  WNC-Queue and API-lanes keepalive disabled; running suites left to finish; Yunus restarts the Claude app. Record and
  undo: `00-HQ/setup/SETUP_PHASE_TRACKER.md` "D1 stop record". **Do not re-enable anything until the restart's Phase 2+ says so.**
- 2026-10-22 04:00: **limit drain measured (OPS-08).** 24 h main-account use: executor sub-agents 59%, Builder A's
  Task 29 sub-agent 15%, Adobe 5%, Command Center 4%, intake 5.6%, watchdog 1.3%, report 0.2%. Cause: fix agents
  continued for 1-2 days at 0.4-0.95M context; each pause over 5 min re-wrote it (65-76% of their cost). Rule:
  PLAYBOOK §4 "Sub-agents stay small" (fresh agent per round, never continue one over 250k, handoff to the card).
  Measure with `python tools/usage_by_session.py 24` (or 5 for the current window). Enforced automatically from
  05:10: `tools/big_agents.py` finds unfinished sub-agents over 250k still being written; the watchdog (step 1c)
  messages the owning work session once per agent per 2 h; Agency LIVE shows each agent's context, red over 250k.
  LIGHT tier closed after 2 review rounds (r1 FAIL: file-time age, control chars in WATCHDOG.md, write order;
  r2 FAIL: a fork's copied agent; all fixed, 70 tests). Known limits: helper seats are not scanned (own limits,
  fresh runs); Agency LIVE may still list a fork's copied agents (screen only, no messages).
- 2026-10-22 ~00:10 → 03:20: eighth limit, run as prepared. Helpers kept going on their own seats: H1 re-delivered S6b, H2 delivered BL-04, H1 started BL-17, H2 peer-reviews S6b-r3. Watchdog 03:24 woke the executor + Command Center; the Command Center woke Builder A (quiet 1 h 18 min). The intake lock of run 657302a5 (failed at the limit) is cleared by the 03:37 intake (OPS-07, listed failed).
- 2026-10-21 ~23:20 → 23:45: RAM 97-99% (Acrobat 8.5 GB, Yunus closed it on request; RAM back to 43%). Both helper loops restarted by the keepalive at 23:43 (run counters reset); their earlier suites kept running in heavy.sh. Helper runs 23:43-23:55 ended in 2-5 min: they yielded to the Gate 4 jobs waiting under the RAM wall (the logged "permission denials" are the profile's standing deny rules, not new). 23:58 before the main account's limit (92% of the 5-hour window used): routines enabled, AC sleep never, D: 236 GB free, helpers AUTO-ON with READY cards (H1 BL-17/BL-19/S1-R51, H2 BL-20/BL-22) and peer reviews; the watchdog resumes the main sessions after the reset.
- 2026-10-21 23:10: Yunus found the old helpers-only live window unclear. New `tools/agency_live.py` (desktop shortcut renamed **WhyNot - Agency LIVE**): all sessions + helpers with model, level, status (WORKING / QUIET / RUNNING TESTS / IN TEST QUEUE / STOPPED by limit), what each does, routines, tasks, latest decisions, needs-you. 16 tests; review r1 PASS-WITH-MINORS (10 fixed) → r2 PASS. Known limits: an unreadable limit reset shows LIMITED up to 5 h; the WHO list and GOAL are constants in the file. Also found: the watchdog cannot run `run_scheduled_task` unattended → WATCHDOG 1b now asks the Command Center to re-run a lost report. 23:30 added (Yunus: "agents and the main account"): an AGENTS section (unfinished sub-agents of every main-account session and both helpers: parent, model, level, status, task), main-account usage % from the app's plan-usage-history.json, and the biggest RAM users when RAM >= 85%. Review PASS-WITH-MINORS, minors fixed; 20 tests. Found then: RAM 99% with Acrobat at 8.5 GB (Yunus's app: asked him to close it).
- 2026-10-21 ~21:08 → 22:20: seventh limit. Found at 22:30: BL-02's intake review queued the full suite 6 times today (each ~1 h + 1-2 h queue wait) and every run was cut by a limit before its verdict; the results lived only in the dead session. Fix: MASTER-INTAKE 1B keeps the suite log in `reviews/suites/review-<ID>-<sha8>.log` and the next run reuses a finished log for the same sha. (Helper/review worktrees fail ~40-80 env tests on the base too; the rule stays "no worse than the baseline".) Review PASS-WITH-MINORS, all minors applied (Bash only, full POSIX path, reuse check command, 24 h age, known limit: a suite ended by OPS-07 mid-run leaves only `.part`).
- 2026-10-21 ~14:10 → 17:20: sixth limit. The 17:00 report was lost → re-run by the Command Center 17:30. Found while checking: at 08:38 and 13:38 an intake took over the lock of a LIVE intake (b3a342d2 ran to 08:46, 06764fdd to 17:10) because a run waiting on its review reads `isRunning: false`; two intakes ran at once. Fix: MASTER-INTAKE 0.1 now also reads the run's status in `list_task_runs` (`stale_suites.run_alive`, tests RunAlive); a run listed `running` is alive. Not listed → `until` only. Review: r1 FAIL (P1: not-listed was judged dead) → r2 PASS. 17:43 found live: an intake's turn ends `succeeded` while its tagged suites still wait, so `succeeded` + 1+ tagged suites = alive (scan-tag is the third signal); end-tag only on `failed`; a woken run re-reads the lock and stops if taken over. Review r3 PASS-WITH-MINORS. Verified live 18:37: run 2dbec8c7 saw 432e75c7 `succeeded` + 6 tagged suites → "intake already running", lock and suites untouched. Known limit: an intake waiting on untagged background work (not via heavy.sh with WNC_RUN) can still be judged dead → a second intake runs beside it (nothing is killed). Known limit: an app crash that leaves a run stuck at `running` holds the lock until it drops out of the last 10 runs (~10 h).
- 2026-10-21 ~08:38 → 12:20: fifth limit. The 08:37 intake died holding the lock (to 14:40); the 09:37-11:37 intakes and the 09:00 report failed fast (13:00 report covers it; past step 1b's 180 min). 12:28 Command Center: H2's untagged `review-BL-02` suite frozen since 08:26 (wrapper gone, child python 0 CPU over 60 s) → ended by hand per §5b; heavy.sh marked the slot STALE and frees it on the next ask.
- 2026-10-21 ~05:44 → 07:20: fourth limit. The 03:37 intake (lock valid to 09:40) died at 05:44; the 04:37-06:37 intakes failed fast. Watchdog 07:24 resumed the executor + Command Center; the Command Center resumed Builder A (idle since 04:19). BL-16 stayed ACCEPTED in MERGE-QUEUE; helpers kept going. The 07:37 intake clears the lock (OPS-07).
- 2026-10-20 23:31 → 2026-10-21 02:20: third limit. The 21:37 intake run died holding `intake.lock` (no tagged suites
  left; the 02:37 intake clears it per OPS-07). Watchdog 02:24 resumed the executor + Command Center; the Command
  Center resumed Builder A (its Task 29 subagent stopped on the limit). Helpers kept going (BL-16 fix delivered 01:xx).
- 2026-10-20 ~18:30 → 21:20: second usage limit of the day. Routine runs failed fast (nothing blocked), but the 21:00
  report was lost. Helpers kept working on their own seats. 21:56 the Command Center (nudged by the watchdog) re-ran
  the report (R-2026-10-20-2156 SENT). Prevention: WATCHDOG step 1b re-runs a report that failed on a limit (≤ 180 min old).
- 2026-10-20 11:20–11:45 (Yunus: «ليه مرجعتش تشتغل لوحدها… احلها بدون اي ابروف»). Found and fixed:
  1. The Command Center session was never a watchdog target → added (`local_a36b6974…`, the parent Command Center; first set to the btw fork by mistake, corrected 11:55).
  2. The v1 watchdog could not read huge transcripts ("(no messages)") → never resumed the executor (idle 05:15) or
     Builder A (07:06). Both nudged by hand 11:38; v2 judges unreadable work tracks by last activity.
  3. Routine runs in default mode hung on permission prompts, and a hung run blocks every later run of its routine
     (no 09:00 report). Report + watchdog recreated in **Bypass mode** (as the intake already was); stuck runs stopped.
  4. The first v2 watchdog run stopped two healthy 3-minute-old runs: it compared UTC `started_at` with the shell clock
     (Cairo time labelled "EDT"). Fixed: all ages come from `stale_suites.py age` (tested: UTC Z, offsets, no zone =
     unknown). The intake run it stopped left a session-named lock that the next intake clears by itself (OPS-07).
  5. Heavy queue held 219 min by H1's stray A/B script (H1 asked to free it) → its tree ended; queue flowing.
  Verified after: report run 11:43 delivered unattended (row R-2026-10-20-1143 SENT with its session id).
- 2026-10-20 03:52 → 11:23: a routine run that never finishes (the 02:01 report run waiting on a permission prompt;
  the 03:52 auto-resume run cut by the usage limit) blocks EVERY later run of that routine (the app starts no new run
  while one is "in progress"). Effect: no 09:00 report; no watchdog after the 06:00 reset, so the executor (stopped
  05:15) was never resumed. 11:23 Command Center stopped both stuck runs and ran both routines by hand. Detection now
  in every report (PRIMARY-REPORT step 2: a routine whose newest run is `running` for > 60 min = STUCK).
  Prevention (11:40, on the plan session's evidence that all 4 watchdog hangs were on its step-1 PowerShell call):
  the auto-resume prompt is now shell-free (tag check by Glob/Grep on `.git`), time-boxed (any step > 2 min or a
  permission prompt → end the run), treats an idle work track with an unreadable (empty) transcript as STOPPED
  after 60 min, and tells resumed tracks to re-queue heavy jobs lost at a limit and to use `tools/test.sh`.
- 2026-10-20 03:54 → 06:00: Yunus's account hit its usage limit (reset 06:00). The intake run of 03:37 died holding
  `intake.lock` until 09:38 and its suite `review-BL-16` frozen in a heavy slot (140 min), blocking `h1-setup4` and
  `peer-BL-16`. 06:05 Command Center: lock renamed `intake.lock.stale-0338-limit`, orphan suite ended; both waiting
  suites started. Permanent fix → card OPS-07. Helpers kept working on their own seats through the limit (05:20 runs).
- 2026-10-19 ~20:40: all four recurring Claude tasks found disabled (cause unknown). 21:30: the whole account hit its
  usage limit. 00:45 reboot. Recovered by the Command Center 2026-10-20.
- 2026-10-20 01:35 (Command Center's own mistake): while creating the `ops` worktree, a plain `git config user.name`
  overwrote the SHARED `.git/config` [user] ("The Why Not AI <info@thewhynot.ai>"), and the "revert" then unset it,
  wrongly assuming nothing was there before. The executor's `git commit` in the main checkout then failed ("Author
  identity unknown"). The plan session set a main-worktree identity (`.git/config.worktree`, 10-20 ~03:00); the
  Command Center restored the shared [user] to its original value at 03:15 (verified: shared, main, h1, h2, ops,
  review). No commit was made with a wrong author (log checked). **Rule:** in this repo, always
  `git config --worktree` for a worktree identity; read `git config --show-origin --get-all` BEFORE any change.
- 2026-10-19: helper suites failed 563 tests: the engine packages existed only in Claude's sandboxed AppData. Fixed by
  ENV-01 (D-009).
