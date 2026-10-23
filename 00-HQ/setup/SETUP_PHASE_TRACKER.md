# SETUP PHASE TRACKER — AI-infrastructure restart (Phases 0–9)

Updated: 2026-10-22 05:00 Cairo. One phase at a time; a phase closes only with evidence and passes its QC gate.
This tracker lives under the existing Master Orchestrator (00-HQ) and does not replace `BOARD.md`: when a phase
creates work for H1/H2/executor, it becomes a BOARD card. Status words: DONE · READY · BLOCKED · NOT STARTED.

Phase scopes now follow the owner's briefs received 2026-10-22 (Phases 1–8). Phase 9 has no brief yet.

| # | Phase (owner brief) | Status | Verification evidence | Blockers | Next action |
|---|---|---|---|---|---|
| 0 | Complete system audit & safe baseline | **DONE** (04:05) | `SETUP_AUDIT.md` (§0–§12, F1–F8); `SETUP_BASELINE.md`; backup `D:\ClaudeData\backups\setup-phase0-20261022-0357` (bundle verify okay, SHA256SUMS 238 files); review PASS-WITH-MINORS (22 claims, 20 match, 2 changed by the live system), P2 ×3 fixed | — | — |
| 1 | Windows development environment & dependencies | **DONE** (05:00) | `ENVIRONMENT_VERIFICATION.md`: Bun 1.4.2 standalone on D (SHA256 ok), resolution in PowerShell / Git Bash / cmd, 13 command tests (panel 296 + uxp 389 pass, UXP build, 135 engine tests, `plugin validate --strict` ✔), symlinks/long paths/dev mode/Smart App Control off OK; independent review PASS-WITH-MINORS (18 claims all match, upstream requirements confirmed), 2 P2 + 4 P3 fixed (undo script now surgical) | L1: running sessions keep Jan's Bun until a full Claude app restart (owner call) | Owner starts Phase 2 |
| 2 | gstack installation, privacy & verification | **DONE** (05:00) | `GSTACK_INSTALLATION_REPORT.md`: gstack 1.91.176.0 global, prefix mode, telemetry off, codex_reviews disabled, artifacts sync off, proactive off, settings.json unchanged; doctor 0 fail; `/gstack-browse` + `/gstack-review` ran in real headless Claude Code sessions; review PASS-WITH-MINORS (P1 left-over browse server stopped) | L1 prefix-mode broken link (upstream), `/cso` needs VS 2022 | — |
| 3 | OMC installation & validation | **DONE** (05:15) | `00-HQ/omc/OMC_INSTALLATION_REPORT.md` Part A: 5.7.6 reused (official marketplace install), loads 49 skills / 19 agents beside 58 gstack skills; omc-doctor no critical; plan, executor (real edit + verify + revert), trace, gstack-in-OMC all ran in real sessions; outbound integrations off (exception: doctor's `npm view` lookup); HUD/team/persistent modes off; review PASS-WITH-MINORS, fixed | rate-limit detection + team need psmux (absent); `omc-lab` duplicate → Phase 4 | — |
| 4 | Unified engineering system integration | **DONE** (05:40) | `AI_TOOLING_ARCHITECTURE.md` §5 (8 real-session tests), `AGENT_ROUTING_RULES.md`, `PLUGIN_CAPABILITY_MATRIX.md` (= compatibility matrix), D-011, project `CLAUDE.md` section, `PROJECT_PLAN_AR.md` §7; OMC at project scope with enforced deny list (42 `Skill()` entries); `omc-lab` de-registered; `.omc/` excluded in the product repo; review PASS-WITH-MINORS, all fixed. **Commit:** `ops/hq` **bdff83f** (pushed, remote verified; config snapshot `setup/PHASE4_CONFIG_SNAPSHOT.md`). Note: the mirror snapshots all of 00-HQ, so it also carried the control-center session's own WIP, which this review did not cover. **Rollback:** `AI_TOOLING_ARCHITECTURE.md` §6 + backup `D:\ClaudeData\backups\setup-phase4-20261022-0454` | careful misses `git -C … reset --hard`; deny list bypassable via router/Read (known limits) | — |
| 5 | Project reorganization, archiving & roadmap | **DONE** (09:15; review PASS-WITH-MINORS, 3 P2 + 5 P3 fixed: hold list, TRACKS.md pointer, M4–M11 full fields; line endings of 5 files restored to LF) | `setup/PROJECT_INVENTORY.md` (+ RAW: 374 items with references), DOC-MAP top table (one authoritative file per function), archive batch `2026-10-22-b2` (2 files, self-tested apply/undo, manifest), lifecycle BACKLOG→…→ARCHIVED in PLAYBOOK §2a + `hq_status.py` (tests 29/29), `PROJECT_PLAN_AR.md` rebuilt (16 sections, milestones with all 9 fields) | `T4.14` folder + `omc-lab` deletion = owner | independent review → commit |
| 6 | Three-account orchestration | **DONE** (2026-10-23 05:00): three seats ran together unattended (H2 built BL-20, H1 peer-reviewed it twice by itself, each loop then took its next card by itself); OPS-09 ACCEPTED 03:00 (parallel suite = serial, 28 min); H1's 5 parked cards restored 03:02; fresh-session rebuild re-run at close (B4). History: (10:20) owner paused `YIELD.txt` (now `YIELD.txt.paused.txt`) → both loops left yield at 10:05 and first ran the peer reviews owed from before the stop (h1 reviews h2's BL-04, h2 reviews h1's S6b-r3: built-in loop behaviour, review files only). Owner approved ending the two frozen suites: done 10:19, checkpoint + resume script `D:\ClaudeData\setup-phase6\FROZEN_SUITES_CHECKPOINT.md` (heavy.sh logged a false `rc=0` for both; marked in their logs). **~11:50 owner approved (chat): Phase 6 + 7 run as ONE pilot on the real card BL-20** (H2 builds, H1 peer-reviews, master accepts); BL-20 un-parked to READY, SETUP-P6-H1/H2 ARCHIVED unrun; every other parked card stays PARKED. **14:22–14:26** owed peer reviews done: h2 → S6b (`reviews/S6b-r3-peer-h2-20261022-1005.md`, PASS-WITH-MINORS; h2 could not write into 00-HQ/reviews, master copied it), h1 → BL-04 (`reviews/BL-04-peer-h1-20261022-1005.md`, FAIL; card stays parked, master verdict in Phase 8). **14:23 H2 took BL-20** (branch `h2/BL-20`, claim written) = pilot started | `ACCOUNT_STATUS.md`, D-012, README prompts | test cards SETUP-P6-H1/H2 on BOARD; 8 real helper cards parked (`setup/PHASE6_PARKED.json`); `Start-Helper --check` both seats signed in (team org); state-reconstruction test by a fresh session passed (`D:\ClaudeData\setup-phase6\reconstruct.jsonl`) | none (owner steps listed in the finished message) | — |
| 7 | End-to-end execution pilot | **DONE** (2026-10-23 05:00): BL-20 ACCEPTED 04:54 after H1's round-2 peer review PASS-WITH-MINORS (04:51), MERGE-QUEUE line written; executor merge is the normal next step. Record `EXECUTION_PILOT_REPORT.md`. History: (run as ONE pilot with Phase 6 on BL-20, owner-approved ~11:50; live record `EXECUTION_PILOT_REPORT.md`: H2 DONE 18:30 → H1 peer FAIL 20:53 (real P2) → master FIX round 1 20:56 → H2 took it by itself 20:59, fix suite `h2-BL-20c` queued 22:29 → H1 round-2 review → master verdict → MERGE-QUEUE) | — | 4–6 | — |
| 8 | Continuous execution, recovery & reporting | **DONE** (2026-10-23 05:00): C1 intake back 03:03 (accepted S6b, reviewing BL-02), C2 reports back since 21:00, C3 watchdog back at close (last), restart watchdog C4 retired; tests B1 (C1+C2+C3), B2, B5–B9 PASS, B3 PASS (historic), B4 re-run at close; `hq_status.py` F5 fix reviewed (`reviews/P8-hq-status-r2.md`, 55/55). Frozen suites: religious-ok-r4b-resume rc=0 (21:22); verse-fix3-resume not run on purpose, superseded by the executor's newer `vf3r2-fix3-suite` (23:21). History: NOT STARTED (prep 17:25: read-only drafts `setup/AUTOMATION_OPERATIONS.draft.md`, `RECOVERY_PROCEDURE.draft.md`, `PHASE8_GAPS.draft.md`; biggest gaps: routines still disabled since D1, `helper_loop.py` has no per-card attempt limit (brief items 11–12), report fields "current milestone" missing, hand-written plan sections not refreshed, routines run in Bypass vs AGENT_ROUTING_RULES §5). **18:20–18:45 (while suites ran): IN PROGRESS** — (a) per-card attempt limit in `helper_loop.py` (6 PARTIAL runs per FIX/Answer round → loop BLOCKED report, then STALLED; 3 no-report runs → STALLED; unconfirmed yield → 15 min wait): TDD, review `reviews/P8-helper-loop-r1.md` PASS-WITH-MINORS, fix round 1, 53/53, live since 18:35 (backup `.bak-p8`, sha-identical, `RELOAD-h1/h2` = loads after each loop's current run); MASTER-INTAKE §C "reopen = `## Answer`". (b) report fields milestone / seat accounts / new handoffs + H2 task-id bug in `hq_status.py`: review `reviews/P8-hq-status-r1.md` PASS-WITH-MINORS, fix round 1, 53/53. (c) B6 git test 8/8 (`D:\ClaudeData\setup-phase8\b6-git-test.log`). **19:00–21:12:** `AUTOMATION_OPERATIONS.md` + `RECOVERY_PROCEDURE.md` promoted; both loops on the new code (h2 19:33, h1 20:54); 21:03 report fired by schedule with all 10 fields, row SENT (B1 C2 + B8 PASS); `hq_status.py` "FIX r1 = decided" fix (TDD, 54/54); BL-20 peer FAIL → master FIX round 1 20:56, h2 took it by itself 20:59; BL-04 master verdict FIX round 1 21:07 (peer FAIL confirmed), BL-22 READY; `YIELD.txt` restored 21:08; C3 watchdog re-enabled + Run now PASS 21:11 → it woke the executor/Builder A, queue ~15 jobs, RAM 85 % → **owner 21:35: C3 off again until Phase 8 is done** (disabled by the infra-audit session; executor + Builder A told to finish only the step in flight; `AUTOMATION_RUNBOOK.md` §6). OPS-09 run 3 (21:21): Ran 9546 but 1 extra failure + 1 extra skip → not accepted, probe queued (card). **Held on purpose:** H1's 5 cards + C1 intake until H1 starts the BL-20 round-2 peer review (else a long H1 card delays it by hours) | existing routines (Phase 0 §11) | D1, D2 | — (Phase 8 closed) |
| 9 | (no brief yet) | NOT STARTED | — | — | — |

## Phase 1 checklist (brief "Required Actions")
- [x] 1 Phase 0 inventory and backup reviewed (backup re-verified, review fixes applied).
- [x] 2 Git, Git Bash, Node, npm, Bun, Claude Code, Python verified (§2).
- [x] 3 Versions checked against current official requirements (§1: gstack setup/README/bun pin, OMC README/package engines).
- [x] 4–5 Missing prerequisite installed officially: Bun 1.4.2 standalone (not Jan's); nothing else mandatory was missing.
- [x] 6 Resolution from PowerShell, Git Bash, cmd (§3); running Claude sessions documented as stale (L1).
- [x] 7 PATH conflicts and duplicates (§3).
- [x] 8 Windows permissions (§4).
- [x] 9 Native Windows + Git Bash chosen over WSL2 (§5).
- [x] 10 Premiere 26.5.2 / AE 26.5 / CEP debug / bridge / UPIA checked (§6 #13).
- [x] 11 Build commands run (§6).
- [x] 12 Constraints, prerequisites, recovery (§8–§10).
- [x] Restrictions kept: no gstack/OMC install, no product code change, no paid API, no security change, no helper change.

## Owner decisions still open (from Phase 0)

| ID | Decision | Recommendation |
|---|---|---|
| D1 | Stop the running system? | **Answered 2026-10-22 ~04:15: STOP, then Yunus restarts the Claude app himself.** Done 04:15–04:20 (see "D1 stop record" below). |
| D2 | Which session is the one Master Orchestrator? | Command Center + 00-HQ (D-001); this restart and the control-center build report into it. |
| D3 | gstack | **Answered by the Phase 2 brief: install it.** Bun prerequisite done in Phase 1. |
| D4 | Push an off-PC backup of `release/3.0` (114 local-only commits)? | **Answered + done 2026-10-22 ~13:30:** pushed `release/3.0` → `ops/backup-release-3.0-20261022` (private repo); remote verified = local `3aa6167`. |
| D5 | One OMC pilot only (`omc-pilot` vs undocumented `omc-lab`)? | **Done:** `omc-lab` de-registered (Phase 4) and archived to `_archive/tools-2026-10/omc-lab` on owner's word (batch b3, hash-verified). |
| D6 | `T4.14-راجع-التفريغ` folder | **Owner: task already finished.** Folder stays. |
| D7 | 3 `run.*` test folders next to heavy.sh | **Deleted on owner's word** (checked first: no links, only heavy-test output, 4–6 KB each). |

## Owner run rule (2026-10-22, chat + relayed 11:33)
Run Phases 6 → 7 → 8 without stopping between them; stop only for what is truly the owner's (push/publish, money,
security, live Premiere with him present, anything Claude's safety check refuses). When Phase 8 closes: ONE message
"finished", then start nothing. Speed-ups that split slow work are approved system-wide when no gate drops
(OPS-09 opened under this, owner-confirmed in chat). Other parked product work stays parked.
**OPS-09 ACCEPTED 2026-10-23 03:00:** equivalence run 4 on 302df0d matches serial exactly (Ran 9546, same 4 env
failures, skipped 48, 28.1 min). In MERGE-QUEUE; the suite-command switch waits for the executor's merge (report
`inbox/master/2026-10-22-OPS-09.md`).

## Proposals received during the restart (carded only after Phase 8; owner said: nothing else starts before then)

| From | Proposal | Master's note |
|---|---|---|
| audit session `local_eab80a9e`, 2026-10-22 ~11:45 | Parallel suite `tools/test.sh --parallel N`: per-module shards balanced by recorded duration, result cached by sha and reused by intake/peer/executor; heavy.sh treats it as one job holding both suite slots. Measured on a clean c963132 export: 9,459 tests, 5 of 6 shards 12–25 min (≈22–25 min balanced vs 68 min serial + 51 min wait), RAM peak 76 %, CPU 12 % → ~40 %. Script `…\eab80a9e…\scratchpad\shard_suite.py`, logs `D:\ClaudeData\Temp\shard-test-6` | Good: same tests, ~4× faster. **One change before it is a card:** "a failure that passes when re-run alone does not count" hides real load bugs. Count every first-run failure as a failure; the alone-rerun only *labels* it `load-sensitive` in the log for the reviewer. The 3 known timing tests go in a serial lane, named in the card. Card = LIGHT, shared runner, so TDD + 1 fresh review; it changes `tools/test.sh` + heavy.sh (both shared) → owner-routed. |

## D1 stop record (2026-10-22, owner order)

| Item | Action | State after |
|---|---|---|
| Routines `whynot-cut-auto-resume-2`, `whynot-cut-hq-intake`, `whynot-cut-primary-report-2`, one-time `whynot-cut-usage-remeasure-1000` | `enabled: false` (Claude scheduled tasks) | **disabled** (verified by tool result) |
| Helper AUTO loops h1, h2 | `auto\STOP` written, `auto\AUTO-ON` removed (same as `Stop-Helper-Auto.cmd`) | h2 **stopped** 04:16:57 (its run 5 killed by the STOP file, by design); h1: see below |
| Windows task "WNC-Queue" | `schtasks /Change /DISABLE` | **Disabled** (running suites keep going; queued ones will not start) |
| Windows task "WhyNot Cut API lanes keepalive" | `schtasks /Change /DISABLE` | **Disabled** |
| Windows task "WhyNot Cut helpers keepalive" | left Ready | harmless: no `AUTO-ON` file left |
| Running session "Multi-account Claude control center" (`local_15b89011`) | message queued: checkpoint into `control-center/AUDIT.md` and end the turn | queued |
| Idle sessions (Command Center, executor, K+M, Adobe, plan) | not messaged, so they are not woken | idle |
| Running test suites and mutation runs (executor/builders') | **not killed** (D1: let them finish) | running; they end with the app restart if they belong to an app session |
| Startup `WhyNot Cut API lanes.cmd` + `lane_board.py` / `lane_reaper.py` processes | **NOT done**: Claude's safety check refused the script that moves the Startup file and ends those two processes | owner steps in the Phase 1 report (lanes are on HOLD, so they spend nothing) |

**Undo / restart later:** `D:\ClaudeData\setup-phase1\start-automation.cmd` (re-enables the 2 Windows tasks, restores the
Startup script if parked); helpers via desktop «WhyNot - Helper N AUTO»; routines in Claude app → Routines.
