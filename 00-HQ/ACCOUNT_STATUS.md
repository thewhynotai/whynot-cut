# ACCOUNT STATUS — the three Claude accounts (verified record)

Updated 2026-10-22 09:30 Cairo by the master (AI-infra restart Phase 6). Each line says how it was checked. No
passwords, tokens or login material are recorded here. Update this file whenever a seat's state changes.

| | **MAIN** (master) | **H1** (helper 1) | **H2** (helper 2) |
|---|---|---|---|
| Account | info@thewhynot.ai, team org (`.claude.json` oauthAccount) | mayar@thewhynot.ai, team org (`Start-Helper.cmd h1 --check`: loggedIn, not the master seat, right account) | marketing@thewhynot.ai, team org (same check) |
| Role | Command Center (tasks, status, acceptance, reports) + executor (Gate 4 integrator, merges/pushes `release/3.0`) | Engine builder + peer reviewer of H2 (`roles/HELPER-ENGINE.md`) | Product builder (panels, installer, guide) + peer reviewer of H1 (`roles/HELPER-PRODUCT.md`) |
| Launch method | Claude desktop app; headless `claude -p` from the app bundle for tests | AUTO: `helper_loop.py h1` via `Start-Helper.cmd h1 --auto` (desktop shortcut, Control Center "Start AUTO", or the keepalive task when `AUTO-ON` exists). Chat: `--talk`. **Never from inside a Claude session** (login leak) | same, `h2` |
| Profile / config | `~/.claude` (→ `D:\Claude\dot-claude`) | `CLAUDE_CONFIG_DIR=D:\ClaudeData\accounts\h1` | `D:\ClaudeData\accounts\h2` |
| Runtime state (09:30) | this session working (restart Phases 5–8); other main sessions idle; routines off except the two restart resume tasks | loop **running** (pid 19828, since 04:40:15), status `yielding` to Gate 4 job `bl14r9-full` in the heavy queue | loop **running** (pid 41332, since 04:40:17), `yielding` (same job) |
| Current task | AI-infra restart Phase 6 | SETUP-P6-H1 (READY, first in BOARD order; all other H1 cards PARKED) | SETUP-P6-H2 (NOT READY until H1 is DONE; all other H2 cards PARKED) |
| Branch / worktree | main checkout `WhyNotCut` on `release/3.0` = `3aa6167` (43 uncommitted executor files) | `D:\WNC-work\h1` on `h1/BL-17` @ `c963132`, 9 changed + 1 untracked (BL-17 WIP, parked) | `D:\WNC-work\h2` on `h2/BL-04` @ `fab930b`, clean |
| Latest handoff | Phase 6 cards issued 09:20 | `inbox/h1/2026-10-22-S6b-r3.md` (before the stop) | `inbox/h2/2026-10-22-0316-BL-04.md` (before the stop) |
| Latest sync to GitHub | `ops/hq` = `aeee8eb` SYNCED (remote verified 09:15). `release/3.0`: **115 commits local only** (D4 waits for the owner) | `h1/*` branches local only (push rule: PLAYBOOK §1) | `h2/*` branches local only |
| AI tools in the session | gstack 1.91.176 (global, 58 skills), OMC 5.7.6 (project scope), superpowers, Karpathy, whynot-cut 3.0.0 | superpowers + profile CLAUDE.md rules; **no gstack, no OMC** (own config dir; main-seat global skills do not reach it; to be confirmed by the seat itself in SETUP-P6-H1) | same as H1 (SETUP-P6-H2 confirms) |
| Execution capabilities | everything incl. Premiere/AE live, merges, pushes of `ops/hq` | headless runs, own worktree, heavy.sh queue, inbox reports; no push of `release/3.0` | same as H1 + panel tooling (npm in its worktree) |
| Blocking issues | Claude may not start helper loops (safety classifier, 2026-10-22); D4 backup push needs the owner | yields while any `g4/bl/rev/…` job waits in the heavy queue (`00-HQ/YIELD.txt`) | same |

## Coordination files (one place each; reused, not duplicated — D-012)

| Brief name | Lives in |
|---|---|
| `AGENT_COORDINATION.md` | `PLAYBOOK.md` §1 (team), §3b (AUTO), §3c (three accounts), §3d (yield) + `AGENT_ROUTING_RULES.md` |
| `AGENT_HANDOFF_PROTOCOL.md` | `PLAYBOOK.md` §2 + §2a (card → branch → inbox report → independent review → verdict → merge → archive), `templates/TASK-CARD.md`, `templates/UPDATE-REPORT.md` |
| `AGENT_STARTUP_PROMPTS.md` | `README.md` "Startup prompts per account" (+ the AUTO prompt built into `helper_loop.py`) |
| Task locking / ownership | one owner per card on BOARD; claim files `D:\ClaudeData\claude-api-lane\claims\<ID>.claim`; one worktree per helper; `intake/intake.lock`; heavy.sh slots; a loop lock per helper (`auto\loop.lock`) |
