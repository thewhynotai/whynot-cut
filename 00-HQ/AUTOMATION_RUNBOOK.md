# AUTOMATION RUNBOOK — what runs by itself, how to check it, pause it, stop it and recover

Owner: Command Center (master). Words used here: **configured** (exists) · **scheduled** (has a trigger) ·
**running** (a process/session is live now) · **delivered** (the recipient can see it) · **verified** (evidence below).

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

- Helpers live view: desktop shortcut **WhyNot - Helpers LIVE**, or `python -X utf8 D:\ClaudeData\accounts\helper_peek.py h1`.
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
4. Open **Helpers LIVE** and check both show `AUTO ON  loop running`.

## 6. Incidents
- 2026-10-19 ~20:40: all four recurring Claude tasks found disabled (cause unknown). 21:30: the whole account hit its
  usage limit. 00:45 reboot. Recovered by the Command Center 2026-10-20.
- 2026-10-19: helper suites failed 563 tests: the engine packages existed only in Claude's sandboxed AppData. Fixed by
  ENV-01 (D-009).
