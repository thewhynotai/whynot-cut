# PHASE 8 GAPS (DRAFT) — brief item → mechanism → evidence → test for AUTOMATION_TEST_REPORT

Written 2026-10-22 ~17:35 Cairo. "Verified" only where evidence was seen on disk or in the app's run list (cited).
Constraints on every test: no paid API, no rate-limit bypass, Claude starts no helper loop, localhost only, D: drive,
no full product suite just for a test (reuse a run the work already needs), nothing destructive without the owner's yes.
Components C1–C13: `setup/AUTOMATION_OPERATIONS.draft.md` §1. Procedures R1–R9: `setup/RECOVERY_PROCEDURE.draft.md`.

## A. Execution requirements

| # | Brief item | Current mechanism | Verified? (evidence) | Test needed | Who |
|---|---|---|---|---|---|
| 1 | Review automation | SETUP_AUDIT §9/§11 + Ops draft §1 | Yes: `schtasks` query, process list, `list_scheduled_tasks` (all 2026-10-22 17:1x) | none | — |
| 2 | Simplest Windows architecture | routines + 2 python loops + keepalive + heavy.sh | Yes (design; running since 10-19, `AUTOMATION_RUNBOOK.md` §6) | none beyond B1–B9 | — |
| 3 | OMC persistence / recovery | **not used** (D-011 deny list; psmux absent) | Deny verified Phase 4 (`AI_TOOLING_ARCHITECTURE.md` §5 test 4) | none; state "not met by owner decision" in the final doc | Claude |
| 4 | No competing loops | one set; lane-watch/owner-update off | Partly: lane processes `lane_board.py` (pid 16656) + `lane_reaper.py` (18684) still run, Startup `WhyNot Cut API lanes.cmd` present (17:1x) | owner parks the Startup file and ends the 2 processes (D1 open item), or records them as accepted dormant; then re-list processes | Owner |
| 5 | Durable checkpoints | branches, inbox reports, card FIX headers, `intake\state.json`, `status.json`, `heavy-log.tsv` | Yes for files existing (`h2\auto\status.json`, `intake\state.json`) | covered by B3/B4 | — |
| 6 | Validate before resume | helper prompt rules; watchdog message; intake 3-signal lock | Intake: unit-tested (`stale_suites.py`, OPS-07) + live 10-21 18:37 (`AUTOMATION_RUNBOOK.md` §6). Helper/watchdog: prompt only, **unverified** | B3 + B4 | Claude |
| 7 | Dependency-aware | `Depends on:` + master's NOT READY | **Unverified** (no code reads it) | dry check: `hq_status.py` (no flags) lists no READY card whose `Depends on:` names an unmerged card; write the result | Claude |
| 8 | Next READY after verified completion | helper takes next card / IDLE; intake → MERGE-QUEUE → executor | Helper IDLE→wake verified live (`h1\auto\auto.log` 14:28→16:53, 17:05); intake→merge verified earlier (OPS-05, BL-16 merged 890b144) | B2 | Claude + executor |
| 9 | Exclusive ownership, safe git | BOARD owner, claim files, `loop.lock`, worktrees, pre-push hook, executor-only merges | `loop.lock` takeover tested (`test_helper_loop.py:158`); claim `claims\BL-20.claim` exists; pre-push hook **not re-checked** | B6 | Claude |
| 10 | Isolated concurrency | worktrees `D:\WNC-work\{h1,h2,review,review-h1,review-h2,ops,…}`, heavy slots | Yes (`git -C D:\WNC-work\h1/h2 rev-parse`: `h1/BL-17`, `h2/BL-20`) | none | — |
| 11 | Bounded retries / escalation | STALLED after 3 quick fails; 5 h 10 / 8 h kill; peer review ≤ 2; FIX-round limits | Unit tests (`test_helper_loop.py:151-152,176`); live kill `h2\auto\auto.log:63` (10-21 00:16). **Gap:** no per-card attempt limit | B5; plus a card (LIGHT) "per-card attempt counter in helper_loop.py" — owner-routed (shared tool) | Claude (card), master |
| 12 | No infinite / destructive repeats | as 11 + watchdog nudge caps + end-tag only on `failed` | Watchdog caps: prompt rules only. **Gap:** same per-card hole; false `rc=0` after taskkill (`FROZEN_SUITES_CHECKPOINT.md` §4) | B5; document the rc=0 trap (done in R-draft) | Claude |
| 13 | Monitor CPU/RAM/GPU/health/perf | `heavy.sh status/stats`, `heavy-log.tsv`, Control Center, report §5 | RAM per job yes (`heavy-log.tsv`); CPU/GPU only on demand (`heavy.sh:95-101`). **Gap:** no history, no alert outside dashboard | one `heavy.sh status` + `stats` snapshot pasted into the report; compare with Task Manager once | Claude (read-only) |
| 14 | Use fully, don't destabilise | RAM brakes 75/85, VRAM ≥ 1,500 MB, gate, FREEZE | Brakes work for new starts (log: `ops09-parallel2` waited for slots); **gap:** peaks 88 % today (`heavy-log.tsv` 14:24–16:18); no Premiere check | record peaks for the test window from `heavy-log.tsv`; any Premiere run only with the owner present | Claude / Owner |
| 15 | Rate-limit recovery | helper sleep to reset + 3 min; routines fail fast; watchdog one-shot | Main side yes (Runs pane: report runs 10-21 06:03Z/14:03Z/18:03Z failed "session limit", next runs succeeded). Helper side **unit test only** (`test_helper_loop.py:38-43,128`); 0 limit lines in `h1|h2\auto\auto.log` since 10-19 | observe-only: when a seat next hits its limit, copy the `waiting until … (usage limit)` and resume lines from `auto.log`; never force a limit | Claude (observe) |
| 16 | Helper persistence / restart | keepalive task (30 min + logon) | Yes: `keepalive.log` 10-20 00:46 (reboot), 10-21 23:43; task Last Result 0 at 17:07 | B3 | Owner (kill/start) + Claude (verify) |

## B. Brief verification items (to run and record in AUTOMATION_TEST_REPORT)

| # | Brief test | Mechanism | Verified now? | Concrete safe test | Who |
|---|---|---|---|---|---|
| B1 | Scheduled execution | C1–C3 routines, C8 task | C8 yes (17:07 run). C1–C3 **disabled** | after R8 step 4: next `:37` intake and next report slot each show `succeeded` in `list_task_runs`; the watchdog run's one-line reply | Owner/attended master enables; Claude verifies |
| B2 | Task completion transition | BL-20 pilot: H2 DONE → H1 peer review → intake → MERGE-QUEUE → executor → MERGED | In progress (h2 run 2 since 14:23; suite `h2-BL-20b` running) | record: `inbox\h2\…-BL-20.md` DONE, `reviews\BL-20-peer-h1-*.md` with `report-mtime`, `intake\state.json` verdict, MERGE-QUEUE line + merge sha, BOARD `MERGED`; h2 `auto.log` next run/IDLE | Claude observes; executor merges |
| B3 | Process interruption recovery | keepalive + `loop.lock` | partly (historic keepalive lines) | while h1 is **IDLE** (no card running): owner ends the h1 `pythonw helper_loop.py h1` process in Task Manager; within 30 min `keepalive.log` gets "starting auto for h1", `--alive` = 0, `auto.log` "auto loop started", no duplicate loop | Owner (end process); Claude verifies |
| B4 | Session state restoration | files only; watchdog resumes sessions | Yes once: Phase 6 fresh-session reconstruction (`D:\ClaudeData\setup-phase6\reconstruct.jsonl`) | re-run `reconstruct.sh` (read-only, Sonnet, `--allowedTools Read Grep Glob`) after Phase 8 edits; compare its 5 answers with BOARD/tracker | Claude |
| B5 | Failed-task handling | STALLED, FIX rounds, PARKED | unit tests only | run the helper-loop unit file with the fake claude (`python -X utf8 D:\ClaudeData\accounts\test_helper_loop.py`; no real seat, no product suite; isolated temp HQ/profile/claims in `D:\ClaudeData\Temp\claude\helper-loop-test`, `test_helper_loop.py:12-18`) and record the STALLED/peer-attempt checks; walk one FIX round on a real card if the pilot produces one | Claude |
| B6 | Git conflict prevention | private-index rule, revert audit, pre-push hook, executor-only merge | rule documented; incident history | in a throwaway clone under `D:\ClaudeData\Temp\p8-git`: pin H, land a second commit, show the "HEAD moved → abort" and `HEAD~1 == H` checks catch it; feed the helper pre-push hook a `refs/heads/release/3.0` line on stdin and confirm it refuses (no network push) | Claude |
| B7 | Report generation | `hq_status.py --write --sync` via C2 | Yes historically (47 files in `HQ\reports\`, latest `2026-10-22-0359.md`) | `hq_status.py` without flags (writes nothing) now; map its sections to the brief's 10 fields; record missing "current milestone" and partial fields | Claude |
| B8 | Report delivery | routine run session + `--mark-sent` → `SENT (session id)` | Yes historically: 8 SENT rows, last `R-2026-10-21-2227`; newest 6 rows FILED only | after re-enable: next slot row `SENT`; owner confirms he saw it in the app (that is the only delivery: no push/e-mail) | Owner confirms; Claude records |
| B9 | Agent status accuracy | `status.json`, report §2, Control Center | spot check 17:15 consistent: h2 `running` run 2 ↔ slot `h2-BL-20b`; h1 `idle` ↔ `IDLE` file; loop PIDs 19828/41332 ↔ `loop.lock` | at one moment compare `hq_status.py` §2, Control Center cards, `status.json`, process list and heavy slots; any mismatch = finding | Claude |

## C. Reporting

| Brief item | Current | Verified? | Test / action | Who |
|---|---|---|---|---|
| 4 reports/day | 09/13/17/21 (D-005 precedence over 09/12/16/21) | yes historically (Runs pane) | B1/B8 | — |
| `PROJECT_PLAN_AR.md` twice daily | AUTO block 4×/day; hand sections only when the master edits (last 08:31) | AUTO block yes | decide: either the 09/21 report also asks the master to refresh §5/§8/§12, or record as limit | Master |
| 10 report fields | 6 covered, 3 partial, "current milestone" missing (`hq_status.py:408-470`) | read from code | small LIGHT card: add a milestone line from `PROJECT_PLAN_AR.md` §3 + main-seat line + new handoffs | Master (card) |
| Delivered vs saved | `SENT (session)` vs `FILED` rows | yes | keep the distinction in the test report | Claude |

## D. Biggest gaps (one line each)

1. C1–C3 routines disabled → no review, merge, report or resume runs today until R8 step 4.
2. No per-card retry limit in `helper_loop.py` (a card can be re-run every ≤ 8 h forever).
3. Helper-side live rate-limit recovery never observed (unit test only).
4. Report lacks "current milestone"; delivery is app-only, no notification.
5. `PROJECT_PLAN_AR.md` hand sections not refreshed by any routine.
6. RAM brake gates new starts only (88 % peaks today); no Premiere-aware brake; no CPU/GPU history.
7. Old API-lane processes + Startup script still live (held, zero spend) — owner step.
8. WNC-Queue disabled; dependency order and claims rely on the master's words, not code.
