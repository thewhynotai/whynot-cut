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
| 6 | Three-account orchestration | NOT STARTED | identities + live loops verified (Phase 0 §8) | D1 | Account status records, handoff tests |
| 7 | End-to-end execution pilot | NOT STARTED | — | 4–6 | — |
| 8 | Continuous execution, recovery & reporting | NOT STARTED | existing routines (Phase 0 §11) | D1, D2 | Reconcile with the existing 09/13/17/21 reports |
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
| D4 | Push an off-PC backup of `release/3.0` (114 local-only commits)? | Yes, as `ops/backup-release-3.0-20261022`. |
| D5 | One OMC pilot only (`omc-pilot` vs undocumented `omc-lab`)? | Keep `omc-pilot`; settle in Phase 3. |

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
