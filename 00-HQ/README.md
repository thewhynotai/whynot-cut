# 00-HQ — WhyNot Cut control centre (START HERE)

Status: **IN FORCE for new work since 2026-10-19 00:30** (Yunus approved the one-PC design). The chats that were
already running keep their old charters (TRACKS.md, LOCKED-AREAS.md, PROGRESS.md) until they END; their leftovers
come to `BOARD.md`. The HQ folder moves into the repo at the Gate 4 tag; until then it lives here, outside git.

Every Claude session on this project, on any machine and any account, reads **only**:
1. this file;
2. `PLAYBOOK.md` (the rules for everyone);
3. its own role file in `roles/`;
4. the live board `BOARD.md` (and the task card it points to).

Helpers start from the desktop shortcuts «WhyNot - Helper 1/2» (`D:\ClaudeData\accounts\Start-Helper.cmd`), which
open their own profile in their own worktree and send the kickoff line by themselves.

It does not read the old plan files unless a task card points at one. `DOC-MAP.md` says which old file is current.

| File | For whom | What |
|---|---|---|
| `..\PROJECT_PLAN_AR.md` | Yunus | **The owner dashboard** (Arabic): status, full roadmap, ordered checklist, accounts, versions, API. Top block auto-refreshed 4×/day |
| `PRIMARY_ACCOUNT_INBOX.md` | Yunus / master | Reports and requests for Yunus, with delivery state |
| `TASK_QUEUE.yaml` | machines | Generated, read-only view of BOARD + cards + intake + inbox |
| `DECISIONS.md` | everyone | How the project is run (ADR-lite); product decisions stay in PROGRESS/spec |
| `AUTOMATION_RUNBOOK.md` | master | Every routine, its state, pause/stop/restart steps, incidents |
| `PLUGIN_CAPABILITY_MATRIX.md` | everyone | Plugins and skills: installed, active, tested (= the plugin compatibility matrix, D-011) |
| `AGENT_ROUTING_RULES.md` | every session | Who does what: Master Orchestrator vs OMC vs gstack vs superpowers; the enforced never-use list (2026-10-22) |
| `AI_TOOLING_ARCHITECTURE.md` | everyone | Where each AI tool is installed, its config, hooks, test evidence and rollback |
| `setup/` | Yunus / master | AI-infra restart Phases 0–9: tracker, audit, baseline, environment, gstack report (OMC report: `omc/`) |
| `ARCHIVE_MANIFEST.md` | everyone | What was archived where, and the hold list |
| `reports/` · `tasks/archive/<ID>/` | everyone | Dated reports (immutable) · closed task packets |
| `control-center/` | Yunus | **WhyNot Control Center** (2026-10-22): live dashboard + one terminal per account (desktop shortcut "WhyNot - Control Center"); replaces the Agency LIVE screen. `control-center/README.md` |
| `tools/hq_status.py` | master | Status generator + GitHub mirror (`ops/hq`); `tools/archive_docs.py` safe archiving |
| `PLAYBOOK.md` | every session | Rules: roles, the task life-cycle, models and usage, safety, Windows + Mac |
| `roles/MASTER.md` | Yunus's account (master) | Integrator: receives, reviews, merges, plans. Does not build |
| `roles/HELPER-ENGINE.md` | Helper 1's account | Builder: engine, features, tests |
| `roles/HELPER-PRODUCT.md` | Helper 2's account | Builder: panels/UI, installer, guide |
| `roles/API-LANES.md` | headless API lanes | Mechanical tasks + first-pass reviews on the Console credit |
| `roles/MAC-TESTER.md` | Claude on the agency Mac | Final Mac test and report |
| `BUDGET-API.md` | master + lanes | The API plan: API-500 = PLANNED_NOT_AUTHORIZED (HOLD until the owner says «نفذ خطة الـ API») |
| `DOC-MAP.md` | everyone | Every old .md file: current, partly stale or superseded, plus the 15 contradictions and how they are settled |
| `templates/TASK-CARD.md` | master | How a task is handed out |
| `templates/UPDATE-REPORT.md` | builders | How work is handed back |

Kickoff line for any new session (paste as the first message):

> Read `00-HQ/README.md`, then `00-HQ/PLAYBOOK.md`, then `00-HQ/roles/<ROLE>.md`, and do what the role file says
> for the start of a session.

## Startup prompts per account (SESSION_BOOTSTRAP, charter §23.3; adopted 2026-10-20)

Paste the one for the seat you open. Each points at the canonical files; none needs an old chat.

- **PRIMARY / Command Center (Yunus's account, Claude app):**
  > You are the WhyNot Cut Command Center (master). Read `00-HQ/README.md`, `00-HQ/PLAYBOOK.md`, `00-HQ/roles/MASTER.md`,
  > `00-HQ/DECISIONS.md`, then `..\PROJECT_PLAN_AR.md`. Run `python -X utf8 00-HQ/tools/hq_status.py` for the live state.
  > Reconcile git (fetch, local vs origin, dirty files) and the routines (enabled?), then take the first READY card
  > assigned to MASTER on `BOARD.md`. Reply to Yunus in Egyptian Arabic.
- **ASSISTANT_A = H1 (Mayar) and ASSISTANT_B = H2 (marketing@):** started by their desktop shortcuts (AUTO mode sends
  its own kickoff). For an interactive chat on that seat:
  > Read `00-HQ/README.md`, then `00-HQ/PLAYBOOK.md`, then `00-HQ/roles/HELPER-ENGINE.md` (H1) or
  > `00-HQ/roles/HELPER-PRODUCT.md` (H2), then `00-HQ/BOARD.md`. Work only on cards assigned to you, in your own
  > worktree, and hand back through `00-HQ/inbox/<h>/`.
- **Executor / Gate 4 tracks (until the tag):** keep their existing charters (`D:\ClaudeData\claude-api-lane\TRACKS.md`).

Old chat histories are not needed: every decision is in DECISIONS.md, PROGRESS.md, the spec/roadmap and the cards.
