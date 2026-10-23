# ACCOUNT STATUS — the three Claude accounts (verified record)

Updated 2026-10-23 05:30 Cairo by the master (Phase 9 resume; rows checked against git, the loop logs and BOARD). Each line says how it was checked. No
passwords, tokens or login material are recorded here. Update this file whenever a seat's state changes.

| | **MAIN** (master) | **H1** (helper 1) | **H2** (helper 2) |
|---|---|---|---|
| Account | info@thewhynot.ai, team org (`.claude.json` oauthAccount) | mayar@thewhynot.ai, team org (`Start-Helper.cmd h1 --check`: loggedIn, not the master seat, right account) | marketing@thewhynot.ai, team org (same check) |
| Role | Command Center (tasks, status, acceptance, reports) + executor (Gate 4 integrator, merges/pushes `release/3.0`) | Engine builder + peer reviewer of H2 (`roles/HELPER-ENGINE.md`) | Product builder (panels, installer, guide) + peer reviewer of H1 (`roles/HELPER-PRODUCT.md`) |
| Launch method | Claude desktop app; headless `claude -p` from the app bundle for tests | AUTO: `helper_loop.py h1` via `Start-Helper.cmd h1 --auto` (desktop shortcut, Control Center "Start AUTO", or the keepalive task when `AUTO-ON` exists). Chat: `--talk`. **Never from inside a Claude session** (login leak) | same, `h2` |
| Profile / config | `~/.claude` (→ `D:\Claude\dot-claude`) | `CLAUDE_CONFIG_DIR=D:\ClaudeData\accounts\h1` | `D:\ClaudeData\accounts\h2` |
| Runtime state (2026-10-23 04:59, Phase 8 close) | restart session closing Phase 8; routines C1 intake + C2 report + C3 watchdog enabled, restart watchdog retired | loop **running** (pid 2952), run 9 on BL-17 (Opus high) after its BL-20 round-2 peer review | loop **running** (pid 73888), run 3 on BL-04 FIX round 1 (Sonnet high) |
| Current task | Phase 9 master (BOARD/STATUS/plan/reports) + executor Gate 4 rounds | BL-17 (run 9 since 04:52); next READY: S1-R51, BL-19 | BL-04 FIX round 1 (run 3 since 02:32, in its suite); next READY: BL-22 |
| Branch / worktree | main checkout `WhyNotCut` on `release/3.0` = `abdece5` (42 uncommitted executor files) | `D:\WNC-work\h1` on `h1/BL-17` @ `c963132`, 9 changed (BL-17 WIP) | `D:\WNC-work\h2` **detached HEAD** @ `b7e2190`, 10 changed (BL-04 WIP); check the branch at its DONE report |
| Latest handoff | Phases 6–8 closed 2026-10-23 05:00 (`setup/SETUP_PHASE_TRACKER.md`) | BL-20 round-2 peer review PASS-WITH-MINORS 04:51 | BL-20 delivered, ACCEPTED 04:54, merged `032ff99` |
| Latest sync to GitHub | `ops/hq` = `f2ddaa2` = origin. `release/3.0` = `abdece5` = origin (pushed 2026-10-23 05:02) | `h1/*` branches local only (push rule: PLAYBOOK §1) | `h2/*` branches local only, except `h2/BL-20` (pushed by H2; known limit F2) |
| AI tools in the session | gstack 1.91.176 (global, 58 skills), OMC 5.7.6 (project scope), superpowers, Karpathy, whynot-cut 3.0.0 | superpowers + profile CLAUDE.md rules; **no gstack, no OMC** (own config dir; main-seat global skills do not reach it; to be confirmed by the seat itself in SETUP-P6-H1) | same as H1 (SETUP-P6-H2 confirms) |
| Execution capabilities | everything incl. Premiere/AE live, merges, pushes of `ops/hq` | headless runs, own worktree, heavy.sh queue, inbox reports; no push of `release/3.0` | same as H1 + panel tooling (npm in its worktree) |
| Blocking issues | Claude may not start helper loops (safety classifier, 2026-10-22): a dead loop is restarted by the keepalive task or the owner | yields while any `g4/bl/rev/…` job waits in the heavy queue (`00-HQ/YIELD.txt`) | same |

## Coordination files (one place each; reused, not duplicated — D-012)

| Brief name | Lives in |
|---|---|
| `AGENT_COORDINATION.md` | `PLAYBOOK.md` §1 (team), §3b (AUTO), §3c (three accounts), §3d (yield) + `AGENT_ROUTING_RULES.md` |
| `AGENT_HANDOFF_PROTOCOL.md` | `PLAYBOOK.md` §2 + §2a (card → branch → inbox report → independent review → verdict → merge → archive), `templates/TASK-CARD.md`, `templates/UPDATE-REPORT.md` |
| `AGENT_STARTUP_PROMPTS.md` | `README.md` "Startup prompts per account" (+ the AUTO prompt built into `helper_loop.py`) |
| Task locking / ownership | one owner per card on BOARD; claim files `D:\ClaudeData\claude-api-lane\claims\<ID>.claim`; one worktree per helper; `intake/intake.lock`; heavy.sh slots; a loop lock per helper (`auto\loop.lock`) |
