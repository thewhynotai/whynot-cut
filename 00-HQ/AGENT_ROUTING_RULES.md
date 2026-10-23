# AGENT ROUTING RULES — who does what (Master Orchestrator, OMC, gstack, superpowers, Karpathy)

Adopted 2026-10-22, AI-infra restart Phase 4 (D-011). Applies to every Claude session on this project, any seat.
Owner rules (global CLAUDE.md, project `CLAUDE.md`, memory) win over this file; this file wins over any plugin's own
instructions, including text a plugin injects at session start.

## 1. Ownership (one owner per function)

| Function | Owner | Where it lives | Others may NOT |
|---|---|---|---|
| Roadmap, milestones, tasks, priorities, assignments, status, acceptance, reports | **Master Orchestrator** (Command Center, `00-HQ`) | `BOARD.md`, `tasks/`, `DECISIONS.md`, `..\PROJECT_PLAN_AR.md`, `reports/` | create or close tasks, edit BOARD, keep their own task list, set a card's status |
| Execution inside ONE card: implementation plan, delegation to specialist agents, in-task handoff, execution record (`.omc/state/agent-replay-*.jsonl`, `/oh-my-claudecode:debug`) | **OMC** (`oh-my-claudecode`, project scope) | the card's worktree/branch; OMC scratch in `.omc/` | run persistent loops, pick the next card, merge, push, release |
| Specialist checks: review lens, plan analysis, debugging, QA, browser checks, security-adjacent checks, release-doc audit | **gstack** (`/gstack-*`, global) | report into the card's evidence / review file | ship, deploy, open PRs, sync memory off-PC, send code to outside models |
| Working method: TDD, systematic debugging, verification before "done", card specs | **superpowers** | as today (PLAYBOOK §2–§2b) | — |
| Coding principles: think first, simplicity, surgical changes, goal-driven | **Karpathy guidelines** (project `CLAUDE.md`) | always on | — |
| The product itself (editing pipeline) | **whynot-cut** plugin | `WhyNotCut/` | — |

Durable state goes only to Master Orchestrator files and git. OMC `.omc/` notes, plans and project-memory, and gstack
`~/.gstack/projects/*`, are scratch: anything that must survive is copied into the card or the review file.

## 2. Overlapping skills: which one to use

| Need | Use | Do not use for this |
|---|---|---|
| Card spec / plan before a task is handed out (master) | superpowers `writing-plans` | OMC `ralplan`, gstack `autoplan` |
| Implementation plan inside a card (builder) | `/oh-my-claudecode:plan` (short, no interview) | OMC `deep-interview`, gstack `office-hours` |
| Second opinion on a plan or design | `/gstack-plan-eng-review` (panel UI: `/gstack-plan-design-review`) | — |
| Writing code / tests | superpowers `test-driven-development` + the builder itself, or OMC `executor` / `test-engineer` agents for delegation | OMC `tdd` skill, `/oh-my-claudecode:autopilot` |
| Debugging | superpowers `systematic-debugging` first; `/gstack-investigate` for a root-cause pass; OMC `debugger` agent for delegation | — |
| Self-check before handing back | superpowers `verification-before-completion`; OMC `verifier` agent optional | — |
| **Acceptance review** (the gate) | master intake: fresh Opus reviewer per PLAYBOOK (unchanged) | any plugin's review as the gate |
| Extra review lens on a diff | `/gstack-review` (read-only, "report only") or OMC `code-reviewer` / `security-reviewer` agents | `/oh-my-claudecode:review` and built-in `code-review` both fine for quick checks |
| QA of CLI / API behaviour | `/gstack-qa-only` (report) or `/gstack-qa` (fix) | — |
| Web page checks during dev | `/gstack-browse` — **always end with `browse stop` in the same folder** | — |
| Owner-requested browsing | Claude app built-in browser (default); Claude in Chrome only when Yunus asks for it | gstack browse for the owner's own accounts |
| Risky shell work (moves, deletes, resets) | `/gstack-careful` or `/gstack-guard` on top of the owner's junction rules. Known gap: careful does not catch `git -C <dir> reset --hard` (tested); the owner rules still apply | — |
| Release notes / docs audit | `/gstack-document-release` | `/oh-my-claudecode:release` |
| Product editing work | `/whynot-cut:*` skills and agents | `/oh-my-claudecode:autopilot` (name clash: `autopilot` here means **whynot-cut's**) |

## 3. Never use — **enforced**

Every skill below is in `permissions.deny` of `Editing Plugin\.claude\settings.json` as `Skill(<name>)`. Tested
2026-10-22: a model call to `gstack-ship` or `oh-my-claudecode:autopilot` returns "Skill execution blocked by
permission rules", while `gstack-careful` still runs. Limits: (a) this binds main-seat sessions opened in this
folder (helper seats are Phase 6); (b) a slash command **typed by Yunus himself** still runs, which is owner authority.
The list must stay identical to the deny list; change both together.

- **OMC (22):** `autopilot`, `ralph`, `ultragoal`, `ralplan`, `team`, `ask` (external providers), `self-improve`,
  `autoresearch`, `release`, `pr`, `launch`, `harbor`, `configure-notifications`, `hud`, `omc-setup` (re-runs setup),
  `skillify`, `drydock` (seeds/overwrites CLAUDE.md), `deepinit` (writes AGENTS.md everywhere),
  `project-session-manager` (worktrees/tmux), `graph` (crash-recovering pipelines), `wiki` (memory outside HQ),
  `trace` (uses built-in team mode). Keyword auto-activation and persistent modes are off (`.claude/settings.json` env + `.claude/omc.jsonc`).
- **gstack (20):** `ship`, `land-and-deploy`, `setup-deploy`, `canary`, `landing-report`, `codex`, `setup-gbrain`,
  `sync-gbrain`, `pair-agent`, `setup-browser-cookies`, `connect-chrome`, `open-gstack-browser`, `scrape`, `skillify`,
  `eval-plan`, `benchmark-models`, `upgrade` (owner-approved upgrade sessions only), `plan-tune`, `design-shotgun`
  and `design-consultation` (may call an outside image model); no `gstack-team-init`.
- **Known limits of the deny list** (hardening waits for the paid edition, owner rule): the `gstack` / `_gstack-command`
  router skills or a plain Read of a skill's `SKILL.md` can reach a denied skill's text; only 2 of the 42 entries
  were exercised live (both through the Skill tool). The written rule above still binds every session.
  `proactive` is off, so gstack skills run only when typed.
- Anything that sends code or prompts to an outside model or service (Codex, Gemini, Grok, Cursor, Jev, ngrok, gbrain
  sync, notification webhooks), and any paid API (BUDGET-API.md stays HOLD).

## 4. Loops and claiming work (no duplicates)

1. Only these may pick up work by themselves: the helper AUTO loops (their own seat's READY cards on BOARD + a claim
   file), the master intake routine, the report routine, and the resume watchdogs. Each is listed in `AUTOMATION_RUNBOOK.md`.
2. OMC and gstack never start, schedule or resume work by themselves: no persistent modes, no Team Mode, no `/loop`
   built on them, no gstack team hooks.
3. One card = one accountable owner = one branch/worktree. A second session that finds a card IN PROGRESS by
   someone else stops and reports. OMC sub-agents work only inside their parent's card and worktree.
4. Merges and pushes stay with the executor/master flow (PLAYBOOK §2, private-index rules). No plugin merges or pushes.

## 5. Headless and unattended runs

- Give explicit `--allowedTools` for what the card needs. Never `--dangerously-skip-permissions`, never bypass.
- gstack/OMC skills that need Bash fail silently under default headless permissions (Phase 2 lesson). Plan the tool list.
- Every run ends clean: no browse server, no background process left (check, then stop it).

## 6. Seats

Main seat (info@): gstack global + OMC project scope (this folder). Helper seats (H1/H2, own `CLAUDE_CONFIG_DIR`
profiles): **neither plugin**. Phase 6–7 (closed 2026-10-23) did not need them: the BL-20 pilot ran on plain tools. They
stay off until a card needs one; the seats reach these rules through the project `CLAUDE.md` they already read.
