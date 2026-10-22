# AUTOMATION OPERATIONS (AI-infra restart Phase 8)

Status: **current** (promoted by the master 2026-10-22 ~20:30 from `setup/AUTOMATION_OPERATIONS.draft.md`, written
~17:20 from files on disk, a read-only `schtasks` query, a read-only process list and the Claude app's routine list).
Changes since the draft are marked **(P8)**: the per-card attempt limit, the three new report fields, and the routine
states after the Phase 8 restore (§1 "State" column = 17:15 snapshot unless marked). Recovery steps:
`RECOVERY_PROCEDURE.md`. Test evidence: `AUTOMATION_TEST_REPORT.md`.

Words used: **configured** (exists) · **enabled** (has a live trigger) · **running** (a process/session is live now) ·
**verified** (evidence cited) · **unverified** (no evidence seen by this draft). "Brief" = the owner's Phase 8 brief
(`D:\ClaudeData\setup-phase6\phase8-brief.txt:436-514`).

`HQ` = `D:\0 Work\0 Pegasus IMC Agency\00 TWN\0 TWN AI\Editing Plugin\00-HQ`.
`HEAVY` = `C:\Users\LOQ\AppData\Roaming\Claude\side-session-notes\local_263cabbf-75e3-42a1-b384-1753a7bd4dad\heavy.sh`.

---

## 1. Components (what really runs)

| # | Component | Runtime | Trigger | Owner / who starts it | State file | Log | State 2026-10-22 ~17:15 |
|---|---|---|---|---|---|---|---|
| C1 | `whynot-cut-hq-intake` (master intake) | Claude desktop app routine, Bypass mode (`AUTOMATION_RUNBOOK.md:6-7`), fresh session per run, follows `HQ\roles\MASTER-INTAKE.md` | cron `37 * * * *`, jitter 1 s | master (Command Center) | `HQ\intake\intake.lock`, `HQ\intake\state.json`, cards, BOARD, `HQ\MERGE-QUEUE.md` | routine Runs pane; `D:\ClaudeData\claude-api-lane\SUBSCRIPTION-LEDGER.md`; `HQ\reviews\` | **disabled** since the D1 stop (last run 2026-10-22 00:37Z, succeeded) |
| C2 | `whynot-cut-primary-report-2` (Arabic report) | Claude app routine, Bypass, follows `HQ\roles\PRIMARY-REPORT.md` | cron `0 9,13,17,21 * * *`, jitter 163 s | master | `HQ\PRIMARY_ACCOUNT_INBOX.md` (FILED/SENT rows), `HQ\reports\.last-snapshot.json` | `HQ\reports\<stamp>.md`; routine Runs pane | **disabled** at 17:15; **(P8) re-enabled ~19:00**, first scheduled run 21:00 (see `AUTOMATION_TEST_REPORT.md` B1/B8) |
| C3 | `whynot-cut-auto-resume-2` (watchdog) | Claude app routine, Bypass, follows `HQ\roles\WATCHDOG.md` | cron `13,43 * * * *`, jitter 660 s | master | `HQ\intake\watchdog-nudges.json` | routine Runs pane | **disabled** (last run 2026-10-22 00:54Z) |
| C4 | `whynot-infra-resume-watch` (restart-only watchdog) | Claude app routine | cron `5,35 * * * *` | master (temporary) | reads `HQ\setup\SETUP_PHASE_TRACKER.md` | Runs pane | **enabled**; disables itself when the Phase 8 row says DONE (`SKILL.md:12`) |
| C5 | `whynot-cut-owner-update`, `whynot-cut-lane-watch`, 9 one-shot `whynot-cut-resume-*` / `whynot-infra-resume-0830` / `whynot-cut-usage-remeasure-1000` | Claude app routines | — | — | — | — | **disabled, retired** (owner-update = duplicate of C2 per D-005; lane-watch retired by OPS-03) |
| C6 | Helper AUTO loop **h1** (mayar@) | `pythonw.exe helper_loop.py h1`, one headless `claude -p` per card, cwd `D:\WNC-work\h1` | started by the owner (desktop «WhyNot - Helper 1 AUTO» / Control Center "Start AUTO") or by C8 | owner | `D:\ClaudeData\accounts\h1\auto\{AUTO-ON,STOP,IDLE,loop.lock,status.json,next-model.txt,next-effort.txt,peer-attempts.json}` | `h1\auto\auto.log`, `h1\auto\run-<stamp>.jsonl` | **running** (pid 19828 since 04:40), `idle` since 17:06 (all other H1 cards parked) |
| C7 | Helper AUTO loop **h2** (marketing@) | same, `helper_loop.py h2`, cwd `D:\WNC-work\h2` | same | owner | `D:\ClaudeData\accounts\h2\auto\…` | `h2\auto\auto.log` | **running** (pid 41332 since 04:40), run 2 on BL-20 since 14:23; its suite `h2-BL-20b` holds `suite-1` + `heavy-1`. **(P8)** reloaded itself onto the per-card-limit code at 19:33 (pid 73888) |
| C8 | Windows task **"WhyNot Cut helpers keepalive"** | Task Scheduler → `D:\ClaudeData\accounts\Helper-Keepalive.cmd` | every 30 min + at logon | owner-approved 2026-10-19 | uses `hN\auto\AUTO-ON` + `helper_loop.py hN --alive` | `D:\ClaudeData\accounts\keepalive.log` | **Ready** (last run 17:07:43, result 0; next 17:37:42) |
| C9 | Heavy-job admission queue `heavy.sh` (v2) | Git Bash, runs in the caller's shell; kinds `job`, `suite`, `psuite`, `gpu`, `gate` | called by every session/helper for suites, renders, GPU work | shared (plan session's notes folder) | slots `D:\ClaudeData\Temp\wnc-locks\{heavy-1..4,suite-1,suite-2,gpu,gate}.d\owner`, tickets `wnc-locks\wait\*.t`, `FREEZE` file | `wnc-locks\heavy-log.tsv` (1,143 finished jobs) | in use: `h2-BL-20b` running, `ops09-parallel2` (psuite) waiting |
| C10 | Windows task **"WNC-Queue"** (`wnc-queue.py run`) | `C:\Python313\pythonw.exe -B …\WhyNotCut\tools\wnc-queue.py run --home D:\ClaudeData\jobs` | every 10 min + logon (`D:\ClaudeData\jobs\task.xml`) | executor's dev tool | `D:\ClaudeData\jobs\{queue,running,done}\`, `runner.json` | `D:\ClaudeData\jobs\logs\` | **Disabled** (D1); `runner.json` state `exited` 04:10; queue empty |
| C11 | Windows task **"WhyNot Cut API lanes keepalive"** + Startup `WhyNot Cut API lanes.cmd` + processes `lane_board.py` (pid 16656), `lane_reaper.py` (pid 18684) | Task Scheduler + Startup folder + python | 30 min / logon | old API-lane system | `D:\ClaudeData\claude-api-lane\STOP` files (HOLD) | lane folders | task **Disabled**; Startup file **still present**; both processes **still running** (lanes held → spend 0, `BUDGET-API.md`) |
| C12 | Control Center | `python server.py` (pid 28036) on `http://127.0.0.1:8765`, read-only collector + 3 terminals | owner's desktop shortcut | owner | `<state>\snapshot.json`, `history.jsonl` | — | running |
| C13 | Status generator `HQ\tools\hq_status.py` | python, no AI tokens | called by C2 (and by hand) | master | writes `HQ\TASK_QUEUE.yaml`, `HQ\reports\<stamp>.md`, an inbox row, the AUTO block of `Editing Plugin\PROJECT_PLAN_AR.md`; `--sync` mirrors 00-HQ to GitHub `ops/hq` | stdout | tool, not a process |

Evidence for the states: Claude app `list_scheduled_tasks` (read 17:15); `schtasks /query /v` (17:1x); process list
(`Get-CimInstance Win32_Process`, 17:1x); `h1|h2\auto\status.json` + `auto.log`; `wnc-locks\*.d\owner`.

## 2. The one execution architecture

```
Owner (Yunus) ── starts/stops helper loops, enables routines, approves pushes/money/security
   │
   ├─ Claude app (main seat info@) ── routines C1 intake · C2 report · C3 watchdog  (= the Master Orchestrator's hands)
   │        reads/writes 00-HQ files only; intake reviews in D:\WNC-work\review; never merges
   │
   ├─ Windows Task Scheduler ── C8 keepalive (restarts a helper loop whose AUTO-ON exists)
   │                            C10 WNC-Queue (non-AI jobs; disabled now)
   │
   ├─ helper loops C6/C7 (h1 = mayar@, h2 = marketing@) ── one fresh `claude -p` per BOARD card, own worktree + branch
   │
   └─ heavy.sh C9 ── every suite / render / GPU job from any of the above waits here for a slot (RAM brake)

Source of truth for tasks: HQ\BOARD.md + HQ\tasks\<ID>.md (only the master edits them). Merges: executor only.
```

**Why this is the simplest reliable Windows option.** Every piece is already installed, owner-approved and has run
for days (`AUTOMATION_RUNBOOK.md` §1, §6). It uses only two schedulers that exist on this PC anyway: the Claude app's
routines (for anything that needs the main seat's AI) and Windows Task Scheduler (for the two python processes that
must survive reboots and crashes). The loops are plain python with file flags (`AUTO-ON`, `STOP`, `IDLE`), so their
state survives any restart and can be read by a person. State lives in files and git, never in a session's memory.
No new service, daemon, container or paid component is added.

**Why OMC persistent modes are excluded.** Owner decision D-011 (`HQ\DECISIONS.md:79-90`) and
`HQ\AGENT_ROUTING_RULES.md` §4 (lines 63-71): only the helper loops, intake, report and watchdogs may pick up work by
themselves; OMC `autopilot`, `ralph`, `ultragoal`, `team`, `ralplan` etc. are on the enforced `Skill(...)` deny list
(`AI_TOOLING_ARCHITECTURE.md` §5 test 4). A second loop would compete with BOARD for task selection and with the
watchdog for resumes. Also, OMC's own rate-limit detection and team mode need `psmux`, which is not installed
(`SETUP_PHASE_TRACKER.md` row 3). OMC is used only **inside** one card (plan, executor/test-engineer/debugger/verifier
agents). This answers brief item 3: OMC persistence is **not supported in this setup by owner decision**, and session
recovery is done by C3/C4 and the helper loop instead.

## 3. The 16 execution requirements

| # | Brief requirement | How it is met today | Met? / gap |
|---|---|---|---|
| 1 | Review existing automation, schedulers, agent processes | `setup/SETUP_AUDIT.md` §9, §11; `AUTOMATION_RUNBOOK.md` §1; §1 of this file (re-checked 17:15) | **Met** |
| 2 | Simplest reliable Windows architecture | §2 above | **Met** (design). Limits: routines run only while the Claude app is open; keepalive needs a logged-in Windows user |
| 3 | OMC persistent execution / session recovery where supported and verified | Not used (D-011, deny list); recovery = C3 watchdog + C4 + helper-loop limit sleep | **Not met by OMC, by owner decision.** Stated plainly in the final doc |
| 4 | Integrate existing scheduling, no competing loops | One set: C1–C3 + C6–C8 + C9; owner-update and lane-watch retired; OMC/gstack start nothing | **Mostly met.** Gaps: (a) C11 lane processes still run and the Startup script still exists (D1 record: Claude's safety check refused moving it; owner step); lanes are HOLD so they spend nothing but they are a dormant third path; (b) C10 WNC-Queue and C9 heavy.sh are two job runners sharing the same slots (wnc-queue refreshes its own slots, `heavy.sh` header) — not an orchestration loop, but C10 is disabled, so anything queued through wnc-queue (e.g. the report's release-preview rebuild, `AUTOMATION_RUNBOOK.md` §1 lane-watch row) will not run until it is re-enabled; (c) C4 must retire at Phase 8 DONE (self-disables, `whynot-infra-resume-watch\SKILL.md:12`) |
| 5 | Durable execution checkpoints | Card-level: commits on `<who>/<ID>` branches, inbox reports (`DONE`/`PARTIAL`/`BLOCKED`), card `## FIX round n (time)` headers, `intake\state.json`, `hN\auto\status.json`, run transcripts `run-*.jsonl`, `heavy-log.tsv`, suite-log reuse `reviews/suites/review-<ID>-<sha8>.log` (`AUTOMATION_RUNBOOK.md` §6, 10-21 22:30) | **Met at card level.** A run cut mid-card resumes from the branch + newest PARTIAL report; uncommitted edits stay in the worktree. A unittest run cannot resume mid-run (re-run = checkpoint, see `FROZEN_SUITES_CHECKPOINT.md` §3) |
| 6 | Resume only after validating latest state | Helper prompt rules 1–4 compare FIX/Answer times with report times and reuse the existing branch (`helper_loop.py:390-419`); watchdog message says "check git status and your ledger first" (`WATCHDOG.md:56-60`); intake lock judged by 3 signals (`MASTER-INTAKE.md:17-43`) | **Partly met.** The intake check is code-backed (`stale_suites.py run_alive/lock_stale`, tested). The helper and watchdog checks are prompt instructions to the agent, not code. Unverified in this restart |
| 7 | Dependency-aware scheduling | Card field `**Depends on:**` (`templates/TASK-CARD.md:5`); master keeps a card `NOT READY` while it depends on an unmerged card (`MASTER-INTAKE.md:170-173`); helper skips `NOT READY` | **Partly met.** Dependencies are enforced by the master's status words, not parsed by any code; a wrong status word = wrong order |
| 8 | Move to the next READY task after verified completion | Helper: after its DONE report it takes the next card in BOARD order or writes `IDLE` and wakes on a BOARD/card change (`helper_loop.py` `main()`, `board_stamp()`); verification is asynchronous (peer review of the other helper, then intake verdict → MERGE-QUEUE → executor merge → MERGED) | **Met with a deviation:** a helper does not wait for verification before its next card (PLAYBOOK §3c, by design). Verified completion → MERGED needs C1 (disabled now) and the executor |
| 9 | Exclusive ownership + safe Git | One `assigned:` per BOARD row; claim file `D:\ClaudeData\claude-api-lane\claims\<ID>.claim` (text, written by the master); `auto\loop.lock` per helper (atomic `O_EXCL`, PID + boot-time check, `helper_loop.py:157-184`); one worktree per helper (`D:\WNC-work\h1` on `h1/BL-17`, `h2` on `h2/BL-20`); helper pre-push hook allows only `refs/heads/<helper>/*` (PLAYBOOK §3b, unverified by this draft); intake never commits (`MASTER-INTAKE.md:206-211`); executor merges with the private-index rule + `revert_audit.py` | **Met by rule; claims are not machine-enforced** (a claim file is a note, not a lock). Push hook not re-checked here |
| 10 | Concurrency only when isolated | Separate seats, separate worktrees (`h1`, `h2`, `review`, `review-h1`, `review-h2`, `ops`), heavy.sh slots and RAM brake, intake "never two reviews at once" | **Met** |
| 11 | Bounded retries, failure detection, escalation | Helper: 3 quick failures (< 120 s) → `STALLED`, `AUTO-ON` removed (`main()`; tested `test_helper_loop.py:151-152`); kill after 5 h 10 min silent or 8 h (`helper_loop.py:52-53`; live: `h2\auto\auto.log:63` "run 1 killed: over 8 h", 2026-10-21 00:16); peer review tried at most twice (`note_peer_attempt`, tested `:176`). Intake: HIGH → PARKED after 3 FIX rounds, LIGHT → ACCEPTED with known limits after 2 (`MASTER-INTAKE.md:165-168`) | **Met (P8).** Per-card attempt limit live since 18:35 (`helper_loop.py` `note_card_run`, counts in `hN\auto\card-attempts.json`): key = card + number of `## FIX round n` / `## Answer` headers, so a master reopen starts a fresh count; 6 runs whose report is PARTIAL (or has no status word) on the same key → the loop itself writes `inbox\hN\<date>-<HHMM>-<ID>-loop.md` `**Status:** BLOCKED`; one more run on it → `STALLED`, `AUTO-ON` removed; 3 runs in a row with no report at all → `STALLED`; an unconfirmed yield waits 15 min; only DONE resets. Tests 53/53, review `reviews/P8-helper-loop-r1.md`. Remaining: STALLED is shown in the report/dashboard only; nobody is notified outside the app |
| 12 | No infinite retry loops, no repeated destructive actions | As 11, plus: watchdog max 2 nudges per run and 90 min per target (`WATCHDOG.md:53-55`); lost report re-run once, only ≤ 180 min old (`WATCHDOG.md:22-28`); `end-tag` only on a `failed` run, never on time alone (`MASTER-INTAKE.md:34-38`); heavy.sh never re-runs a job | **Met (P8)** with the per-card limit of 11. Known trap: a forced end through the msys wrapper is logged `rc=0` in `heavy-log.tsv` (`FROZEN_SUITES_CHECKPOINT.md` §4) — an `rc=0` after a taskkill is not a pass |
| 13 | Monitor CPU, RAM, GPU, process health, real performance | `heavy.sh status` (RAM, CPU via Get-Counter, GPU + VRAM via `nvidia-smi`, `heavy.sh:95-101,224`); `heavy-log.tsv` per job: wait, run time, RAM start/peak/end; `heavy.sh stats`; Control Center top line (RAM, test queue, alerts, stale banner); `agency_live.py` lists the biggest RAM users at ≥ 85 %; report §5 flags RAM ≥ 85 %; report §2 marks a helper heartbeat older than 330 min `STALE` (`hq_status.py:405`) | **Partly met.** No continuous CPU/GPU history (only on-demand snapshots; heavy-log keeps RAM only). No alert leaves the PC/dashboard |
| 14 | Use the machine fully without destabilising Windows or Premiere | Normal priority; brakes RAM < 75 % → 4 heavy jobs, 75–85 % → 2, ≥ 85 % → none new; second suite / psuite only < 75 %; GPU jobs need ≥ 1,500 MB free VRAM; `gate` kind runs alone; `FREEZE` file holds all starts (`heavy.sh:17-30`) | **Partly met.** The brake gates **new** starts only: today's log shows peaks of 88 % (`heavy-log.tsv`: `ops09-serial` and `h2-BL-20`, 14:24–16:18). Nothing checks whether Premiere is open before a heavy start |
| 15 | Rate-limit recovery while respecting provider limits | Helper: reads "resets <time>" from the run's result, sleeps until reset + 3 min (30 min if no time), never retries early (`reset_time()`, `sleep_until()`; tested `test_helper_loop.py:38-43,128`). Routines fail fast at a limit and the next slot runs (Runs pane: report runs 06:03Z, 14:03Z, 18:03Z on 10-21 "failed … session limit"); watchdog re-runs a lost report once and creates a one-shot resume at reset + 3 min (`WATCHDOG.md:22-28,65-67`). No paid API (`BUDGET-API.md` HOLD) | **Met by design; helper side unverified live:** `h1|h2\auto\auto.log` (kept since 2026-10-19 15:01) contain no limit sleep — only the fake-claude test proves it. Main side verified by the incidents in `AUTOMATION_RUNBOOK.md` §6 |
| 16 | Helper process persistence and restart | C8 keepalive every 30 min + logon restarts a loop whose `AUTO-ON` exists and whose lock is not alive (`Helper-Keepalive.cmd`); live evidence `keepalive.log` (10-20 00:46 after the reboot; 10-21 23:43 both); loops alive now (pids 19828, 41332). Claude may not start loops (`Start-Helper.cmd:21-28` refuses inside a Claude session; D-012) | **Met for crash/reboot.** Gaps: a STALLED loop stays off by design until the owner fixes the cause; a logged-out seat is not detected before a run (it shows up as quick failures → STALLED; inferred from the code, unverified live); the 04:40 restart today was by the owner, not the keepalive |

## 4. Reporting: brief vs what really happens

| Item | Brief | Actual | Note |
|---|---|---|---|
| Schedule | 09:00 / 12:00 / 16:00 / 21:00 (proposed) | **09:00 / 13:00 / 17:00 / 21:00 Cairo** (C2, D-005, approved 2026-10-20) | The existing approved schedule takes precedence, as the brief allows. Windows zone = `Egypt Standard Time` (`tzutil /g`), routines use local time; jitter up to 163 s |
| `PROJECT_PLAN_AR.md` twice daily | 09:00 + 21:00 | the AUTO block (lines 3–37) is rewritten by **every** report run (4×/day); D-005 names 09/21 as the "full refresh" | **Gap:** the hand-written sections §1–§16 are refreshed only by an attended master session (file last modified 08:31 today); no routine does the 09/21 plan update |
| Content | 10 fields | `hq_status.py:408-470`: §1 changes since last report, §2 helpers + active cards, §3 tag / "NO NEW VERIFIED BUILD", §4 git local vs GitHub + ops/hq mirror, §5 errors/blocks + reports waiting for intake + RAM, §6 requests for PRIMARY, §7 next READY cards, §8 API | **(P8) All 10 covered:** completed (as changes), active, blocked, latest git sync, problems, next actions, verified version (pointer to `PROJECT_PLAN_AR.md` §5), plus the three added in Phase 8 (`reviews/P8-hq-status-r1.md`, 53/53): §3 current milestone (first open `M…` line of `PROJECT_PLAN_AR.md`), §2 a PRIMARY line + `H1 (mayar@)` / `H2 (marketing@)` seat accounts, §1 new handoffs (inbox reports newer than the last snapshot) |
| "Delivered to the main account" | distinguish delivered vs saved | **Delivered** = the routine run's final reply is the report, visible in Yunus's Claude app (Routines → run session), and step 3 marks the inbox row `SENT (session <id>)` (`PRIMARY-REPORT.md:20-23`, `hq_status.py:299-306`). **Saved only** = rows left `FILED` (manual runs, or a run that died before step 3) | 8 rows are SENT (last `R-2026-10-21-2227`); the 6 newest rows (10-21 23:57 → 10-22 03:59) are FILED only. No push notification or e-mail is sent; Yunus sees a report only when he opens the app. ACKNOWLEDGED only when he answers (D-005) |
| Lost report | — | a run that hits a limit fails fast; C3 re-runs it once if ≤ 180 min old, else the next slot covers it | C3 is disabled now, so a lost slot is simply lost |

## 5. Resource monitoring (how to look)

- One look: `bash "<HEAVY>" status` (RAM / CPU / GPU / VRAM, running and waiting jobs with reasons); history:
  `bash "<HEAVY>" stats` and `wnc-locks\heavy-log.tsv`.
- Dashboard: Control Center `http://127.0.0.1:8765` (localhost only).
- Helpers: `python -X utf8 D:\ClaudeData\accounts\helper_peek.py h1|h2`; `hN\auto\status.json`.
- Main-seat usage: `python -X utf8 HQ\tools\usage_by_session.py 5`; oversized sub-agents: `HQ\tools\big_agents.py`
  (OPS-08, run by C3 step 1c).

## 6. Rate limits

Three seats, three limits (PLAYBOOK §3c). The system only ever **waits**: helpers sleep to the printed reset, routines
fail fast and the next trigger tries again, the watchdog resumes at most 2 sessions per run. Nothing switches account,
rotates logins, or calls the paid API (lanes HOLD, `BUDGET-API.md` PLANNED_NOT_AUTHORIZED). The reserved $500 is
untouched by any component listed here.

## 7. Concurrency, isolation and git safety

- One card → one owner → one branch `<who>/<ID>` → one worktree. Helpers work only in `D:\WNC-work\h1|h2`; reviewers in
  `review`, `review-h1`, `review-h2`; the master tree `Editing Plugin\WhyNotCut` is read-only for routines.
- Only the executor merges into `release/3.0` and pushes it, from `MERGE-QUEUE.md`, with "HEAD before/after, file list,
  revert audit" (`MASTER-INTAKE.md:180-190`).
- Private-index commits: pin `H=$(git rev-parse HEAD)` before `read-tree`, abort if HEAD moved, then check
  `HEAD~1 == H` and that `git diff --stat HEAD~1 HEAD` lists only your files; `revert_audit.py` (plan-session notes
  folder) before every push (incident 7cadf05 vs 264d16f, 2026-10-19).
- Worktree identity only with `git config --worktree` (incident 2026-10-20 01:35, `AUTOMATION_RUNBOOK.md` §6).
- Pushes to GitHub of `release/3.0` (115 local commits, `ACCOUNT_STATUS.md`) wait for the owner (D4).

## 8. Remaining limitations

1. The three AI routines (C1–C3) are **disabled** since 04:15 (D1). Until they are back, nothing is reviewed,
   accepted, merged, reported or resumed automatically. Re-enabling is an owner (or attended master) step.
2. Claude-app routines run only while the Claude desktop app is open and the main seat is under its limit; a run that
   hangs blocks every later run of the same routine (`AUTOMATION_RUNBOOK.md` §6, 10-20 03:52); detection depends on
   C2/C3 themselves.
3. Claude may not start helper loops (safety classifier, D-012); after a STALLED loop or a seat logout the owner must act.
4. ~~No per-card retry limit inside the helper loop~~ — **closed (P8)**, see §3 items 11–12.
5. RAM brake gates new starts only; peaks of 88 % happen; no Premiere-aware brake.
6. CPU/GPU are monitored on demand only; no alert reaches Yunus outside the dashboard and the 4 reports.
7. Report delivery = visible in the app, no push notification. (The missing "current milestone" field was added in P8.)
8. `PROJECT_PLAN_AR.md` hand-written sections are not refreshed by any routine.
9. Old API-lane processes and Startup script still present (held, zero spend) — owner step to park them.
10. WNC-Queue (C10) disabled: jobs queued through `wnc-queue` wait until it is re-enabled.
11. Helper-side live rate-limit recovery is unverified (only unit-tested).
12. Unattended routines run in Bypass mode (`AUTOMATION_RUNBOOK.md` §0), while `AGENT_ROUTING_RULES.md` §5 forbids
    bypass for headless runs; the routine prompts are the only fence. Record as a known limit or align in a card.
