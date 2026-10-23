# PROJECT INVENTORY — Phase 5 classification (2026-10-22)

- Source: `D:\ClaudeData\setup-phase5\scan_inventory.py` (read-only walk; junctions/symlinks never followed; client
  folders listed, not opened). Full rows (374 items, with bytes, dates and **who references each file**: helper loop,
  HQ tools, control center, roles, README/PLAYBOOK, CLAUDE.md files, scheduled-task prompts):
  `setup/PROJECT_INVENTORY_RAW.txt` (TSV).
- Classes: **AUTH** = the one authoritative file for a function (`DOC-MAP.md` top table) · **ACTIVE** = in use ·
  **GENERATED** = written by a tool · **HISTORICAL** · **DUPLICATE** · **OBSOLETE** · **CLIENT** (not opened) · **UNKNOWN**.

## By area

| Area | Items | Class | Decision |
|---|---|---|---|
| `00-HQ/` top files (README, PLAYBOOK, BOARD, DECISIONS, RUNBOOK, BUDGET, MATRIX, ROUTING, ARCHITECTURE, DOC-MAP, ARCHIVE_MANIFEST, PRIMARY_ACCOUNT_INBOX, MERGE-QUEUE) | 17 | AUTH / ACTIVE | KEEP (all read by tools, roles or routines) |
| `00-HQ/STATUS.md` | 1 | ACTIVE (master's English notes, last 10-21) | KEEP: read by MASTER and MASTER-INTAKE roles; the owner view is PROJECT_PLAN_AR |
| `00-HQ/TASK_QUEUE.yaml`, `reports/` (48), `intake/` (lock, state, 13 stale locks), `reviews/` (15) | 77 | GENERATED / records | KEEP (records; the stale locks are history of OPS-07 recoveries) |
| `00-HQ/tasks/` 15 live cards + specs, `tasks/archive/` | 31 | ACTIVE + archived packets | KEEP; lifecycle now in PLAYBOOK §2a |
| `00-HQ/inbox/` h1/h2 reports | 24 | ACTIVE records | KEEP |
| `00-HQ/roles/`, `templates/`, `profile/`, `tools/` | 21 | ACTIVE (routine prompts point at roles) | KEEP |
| `00-HQ/setup/`, `00-HQ/omc/` | 8 | AUTH for the AI-infra restart | KEEP |
| `00-HQ/control-center/` | 28 | ACTIVE (another session's dashboard build) | KEEP, untouched |
| Root: `PROJECT_PLAN_AR.md`, `CLAUDE.md` | 2 | AUTH | KEEP |
| Root: `COMPETITORS-AR.md`, `VALIDATION-PLAN-AR.md`, `SAVED-LATER-licensing-updates-AR.md` | 3 | ACTIVE (owner's business docs; roadmap Stage 11 cites SAVED-LATER) | KEEP at root |
| Root: `كارت-جرّب-3.0.md` | 1 | ACTIVE but stale (try copy at `447ea2a`) | KEEP; refreshed by the release track |
| Root: `Start-Claude-API-lane.cmd` | 1 | ACTIVE-dormant (API lanes HOLD; may back a shortcut) | KEEP |
| Root: `PARKED-SESSIONS.md`, `API-PAUSE-AR.md` | 2 | HISTORICAL | **ARCHIVED** (batch 2026-10-22-b2) |
| `WhyNot-Cut-3.0-Addendum/` A–M + prd + evidence + K research | 24 | ACTIVE reference (the V1 spec cites them) | KEEP |
| `WhyNotCut/` repo: 134 tracked .md (PROGRESS, LOCKED-AREAS, MAC-INBOX, README, docs/) + code (8,990 files) | 135 | AUTH (spec, roadmap, PROGRESS) / ACTIVE | KEEP. `MAC-INBOX.md` is OBSOLETE (DOC-MAP) but inside the executor's tree → card OPS-04 after the tag |
| `_archive/` (zips 1.0.7→2.2.1, plans-2026-10, 3.0 plan, _source) | 329 files | HISTORICAL | KEEP (now also holds b2) |
| `new plugin code/` (Kalam/Hush/Tidy source drop of 10-12, macOS `._*` files) | 217 files | HISTORICAL source (ported into `engine/reel/lib`) | KEEP (source is preserved; moving gains little) |
| `خد دا كوبي للويندوز` / `للماك` | 2 folders | ACTIVE-stale (preview `322d8a5`) | KEEP (release track) |
| `whynot-test/` | 2,596 files, 6.2 GB | ACTIVE test fixtures (client copies) | KEEP; not opened |
| `T4.14-راجع-التفريغ/` | 3 files, 46 MB | DECIDED (owner 2026-10-22, D6: the task is finished) | **Stays in place**; nothing to move |
| `omc-lab/` | 5 files + `.git` | OBSOLETE (retired in Phase 4, de-registered) | **Archived** in batch b3 (2026-10-22, owner's word) to `_archive/tools-2026-10/omc-lab`, hash-verified |
| `.claude/`, `.gstack/` (gstack browse audit log) | 4 | ACTIVE config / runtime state | KEEP |
| `_private-profiles`, `_private-evidence` | 2 | CLIENT | not opened |

Nothing was deleted. Nothing referenced by a live tool, role, routine or the helper loop was moved.

## Contradictions found (and where they are settled)

| # | Contradiction | Settled |
|---|---|---|
| 1 | PROJECT_PLAN_AR §5 and the 10-20 matrix said whynot-cut **2.2.1** is installed; installed is **3.0.0** | PROJECT_PLAN §7 + matrix update (Phase 4) |
| 2 | PROJECT_PLAN AUTO block says "RUNNING" and `release/3.0` ahead 114 (03:59); the system is stopped (D1) and `release/3.0` is now `3aa6167` | the block regenerates at the next `hq_status.py --write`; §1 text updated in Phase 5 |
| 3 | `00-HQ/README.md` says BUDGET-API holds "October USD 200 / November 450"; BUDGET-API says API-500 PLANNED_NOT_AUTHORIZED (HOLD) | BUDGET-API wins (DOC-MAP top table) |
| 4 | DOC-MAP 10-19 listed `API-PAUSE-AR.md`, `PARKED-SESSIONS.md` as current | archived b2; DOC-MAP top table |
| 5 | `omc-lab/README.md` pointed to a missing `AGENT_COORDINATION.md` | README rewritten (Phase 4); the name maps to PLAYBOOK (D-001) |
| 6 | OMC report Part B "WSL exists" vs no distro | annotated (Phase 3) |
| 7 | BOARD header "Updated 2026-10-20 02:00" while rows changed on 10-21/22 | cosmetic; the BOARD's rows are current |
| 8 | Task status words: BOARD (NOT READY…MERGED) vs the restart's 7-state lifecycle | mapping in PLAYBOOK §2a + `hq_status.py` (tests 29/29) |
