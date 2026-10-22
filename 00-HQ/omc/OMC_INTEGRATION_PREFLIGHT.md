# OMC Integration — Phase 0 Preflight & Compatibility Audit

- Date: 2026-10-22 03:30 (Cairo) · Auditor: Claude Code session on the master seat (info@), Opus 5.5
- Scope: read-only audit + one config backup. **Nothing installed, nothing enabled, no hook touched, no session restarted,
  roadmap and `PROJECT_PLAN_AR.md` not edited.** No paid API used (GitHub reads via `gh api` / WebFetch only).
- Verdict: **PHASE 0 PASSED WITH CONDITIONS** — OMC can be installed safely only under the decisions in §11.
  Two items in §12 are owner decisions; neither blocks a master-only, project-scope install.

Status words: VERIFIED (seen on disk / live process / git) · FILE-EVIDENCE (seen in config, not live-tested) ·
UNVERIFIED · NOT INSTALLED.

---

## 1. System inventory

| Item | Value | State |
|---|---|---|
| Project root | `D:\0 Work\0 Pegasus IMC Agency\00 TWN\0 TWN AI\Editing Plugin` (**not** a git repo) | VERIFIED |
| Git repo | `Editing Plugin\WhyNotCut` → `origin https://github.com/thewhynotai/whynot-cut.git` | VERIFIED |
| Active branch | `release/3.0` @ `c963132` | VERIFIED |
| Ahead/behind origin | **114 ahead, 0 behind** (`origin/release/3.0` last moved 2026-10-18) — push belongs to the Executor at the Gate 4 tag | VERIFIED · RISK R7 |
| Working tree | **dirty**: 19 modified + 11 untracked (brand_web, emphasis, ppro_build, …) — other sessions' open work | VERIFIED · do not touch |
| Worktrees | `D:\WNC-work\{h1 [h1/BL-17], h2 [h2/BL-04], ops [ops/hq], ops-check, review, review-h1, review-h2}`, `D:\ClaudeData\Temp\{bl24-f3, fix3-wt, t26r6-wt}` | VERIFIED |
| Orchestration (Master Orchestrator) | `00-HQ/` (outside git until the Gate 4 tag): README, PLAYBOOK, `roles/MASTER.md`, `BOARD.md` (only task list), `TASK_QUEUE.yaml` (generated), `DECISIONS.md`, `AUTOMATION_RUNBOOK.md`, `inbox/{h1,h2,lane,mac}`, `tools/hq_status.py` (+ GitHub mirror `ops/hq`) | VERIFIED |
| Owner dashboard | `PROJECT_PLAN_AR.md` (top block auto-refreshed by `hq_status.py`, last 2026-10-22 03:26) | VERIFIED |
| Roadmap / spec | `WhyNotCut/docs/superpowers/plans/2026-10-18-master-roadmap-v1.md`, `…/specs/2026-10-18-v1-premiere-panel-design.md` | not opened (no change) |
| Claude Code | desktop app `Claude_3.1623.1.0`, bundled Claude Code **2.1.304**; no `claude` on PATH | VERIFIED |
| Toolchain | git 2.56.0 · node **26.7.0** · npm 11.19.0 · python 3.13.2 · gh 2.102.0 · bun 1.3.4 (**only the copy bundled inside the Jan app**, not a real install) · tmux/psmux **missing** · `wsl.exe` present (distros not checked) | VERIFIED |
| Machine load at audit | RAM 55 % | VERIFIED |

## 2. Installed plugins (versions)

### Master seat (`~/.claude` → junction `D:\Claude\dot-claude`)
| Plugin | Scope | Version / sha | Enabled |
|---|---|---|---|
| superpowers@superpowers-marketplace | user (+ project El-Modeeer S4) | 6.4.2 / 8ca22dba | yes |
| whynot-cut@thewhynot-ai | user | **3.0.0** (cache also holds 2.1.1, 2.2.1) | yes |
| whynot-cut@thewhynot-ai-live | project `D:\ClaudeData\wnc-live\try` | 3.0.0 | try folder only |
| plugin-dev@claude-plugins-official | project (Editing Plugin) | d1adba47 | yes |
| andrej-karpathy-skills@karpathy-skills | user | 1.0.0 / 2c606141 | yes |
| cloudflare@cloudflare | user | 1.0.2 | yes |
| experiment-coach@growth-marketing-os | user | c7852dee | yes |
| windsor-ai@synced | — | — | **disabled** in project |
| reel-editor 1.0.6/1.0.7 | cache only | — | not registered |

### Helper seats
| Seat | Plugins | Note |
|---|---|---|
| H1 (`D:\ClaudeData\accounts\h1`) | superpowers **7.0.0** | version drift vs master 6.4.2 |
| H2 (`D:\ClaudeData\accounts\h2`) | `enabledPlugins` says superpowers, but `installed_plugins.json` is **empty** and the cache holds only a stuck `temp_git_*` clone | **H2 runs without superpowers** (finding F1) |

`00-HQ/PLUGIN_CAPABILITY_MATRIX.md` (2026-10-20) is stale: it lists whynot-cut 2.2.1 user-wide (now 3.0.0) and does
not show the H1/H2 superpowers drift (finding F2).

## 3. Current configuration

| File | Content that matters for OMC |
|---|---|
| `~/.claude/settings.json` | 5 allow rules, 5 enabled plugins, 5 extra marketplaces, `crossSessionInbound: accept`. **No `hooks`, no `statusLine`, no `env`** |
| `~/.claude/CLAUDE.md` | Owner's global rules (Egyptian Arabic, decide-and-continue, D drive, security, junction-safe moves) — **must never be overwritten** |
| `~/.claude.json` | MCP: `magnific` (user). Project MCP: none |
| `Editing Plugin/.claude/settings.json` | official marketplace, plugin-dev on, windsor off, **deny** `mcp__magnific` + 2 connector MCPs |
| `Editing Plugin/.claude/settings.local.json` | 4 one-off allow rules |
| `Editing Plugin/CLAUDE.md` | owner rules §0, quality tiers, Karpathy guidelines |
| `WhyNotCut/` | no `CLAUDE.md`, no `.claude/`; `.gitignore` ignores only `.claude/*.local.*` (no `.omc/`) |
| Helper `settings.json` (h1/h2) | model `sonnet`, 62 allow / 68 deny (fences: no edits to master tree, no push to release/main, no `npm -g`, no `schtasks`, no reading other seat), no hooks |
| User skills | brand-identity-pipeline, el-modeeer-story-board, framer(+code-components), llm-council, reels-editing-pipeline; project skill `skill-finder` |
| User agents | brand-systems-designer, marketing-short-video-editing-coach |

### Hooks in force today (all from plugins; none in settings files)
| Source | Events |
|---|---|
| superpowers 6.4.2 | SessionStart (startup/clear/compact) — injects `using-superpowers` |
| whynot-cut 3.0.0 | PreToolUse Bash/PowerShell (guard), PreToolUse Write/Edit/NotebookEdit on client-source paths, MultiEdit; SessionStart; CwdChanged; **Stop** (`stop_gate.sh`, evidence gate, off unless enabled); SessionEnd |

### Routines (scheduled tasks, enabled)
`whynot-cut-hq-intake` (hourly :37), `whynot-cut-primary-report-2` (09/13/17/21), `whynot-cut-auto-resume-2`
(:13/:43). 11 older ones disabled.

## 4. gstack health

**NOT INSTALLED** on this PC (searched `~/.claude/skills`, `D:\Claude`, `D:\ClaudeData`, `D:\WNC-work`, the project
tree, `~/.gstack`: no trace; no project doc mentions it). Health cannot be "verified" — there is nothing to check.

Upstream facts (github.com/garrytan/gstack, `VERSION` = **1.91.176.0**, main `514fbfd` 2026-10-21):
- Install = `git clone … ~/.claude/skills/gstack && ./setup`; needs **bun ≥ 1.3.3 (tested 1.4.2)** + Node on Windows;
  `/cso` needs VS 2022 Build Tools.
- Writes **hooks into `~/.claude/settings.json`** (SessionStart auto-update, AskUserQuestion Pre/Post, default-on
  Stop `gstack-timeline-stop`), asks Claude to add a `## gstack` section to CLAUDE.md, keeps state in `~/.gstack` (C:).
- **Outside reviews ON by default** (sends code/diffs to Codex) and `$D` design tool needs an OpenAI key → paid /
  data-egress risk unless `gstack-config set codex_reviews disabled`.
- Overlaps heavily with superpowers and OMC (plan/review/ship/qa/investigate).

## 5. OMC installation status

**NOT INSTALLED** (no plugin, no `omc` binary, no npm package, no `~/.omc`, no `.omc/`, no `~/.config/claude-omc`).

Upstream facts (github.com/Yeachan-Heo/oh-my-claudecode):
- Latest **v5.7.7, published 2026-10-21 21:02 UTC** (< 1 day old); previous tags v5.7.6, v5.7.5. MIT.
- Install: `/plugin marketplace add https://github.com/Yeachan-Heo/oh-my-claudecode` → `/plugin install oh-my-claudecode`
  (marketplace name `omc`); or npm `oh-my-claude-sisyphus` (not needed, and `npm -g` from Claude is sandboxed here).
- `engines.node`: 20–26 → node 26.7 OK. Native dep `better-sqlite3` (prebuild on node 26/Windows **UNVERIFIED**).
- Plugin ships 48 skills, commands, agents and one MCP server (`t`, local node bridge).
- **Hooks it registers (plugin `hooks/hooks.json`):** UserPromptSubmit ×2 (keyword-detector, skill-injector),
  SessionStart ×5 (+init, maintenance), PreToolUse `*` + Bash (git-guardrails), **PermissionRequest Bash
  (permission-handler)**, PostToolUse `*` ×2 + Read/Write/Edit ×2, PostToolUseFailure, SubagentStart, SubagentStop ×2,
  PreCompact ×3, **Stop ×5**, SessionEnd ×2.
- **`/omc-setup --global` "explicitly overwrites `~/.claude/CLAUDE.md`" by default** (preserve mode writes
  `CLAUDE-omc.md` instead); `--local` writes `.claude/CLAUDE.md` in the project; Phase 2 sets up the HUD statusLine.
- State: `.omc/` in a git project, otherwise **`~/.omc/` (= C: drive)**; config `~/.config/claude-omc/` (C:).
- Team mode needs tmux (Windows: `psmux` via winget) and `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1`.
- External models (Codex/Gemini/Grok) only when invoked; Jev off by default; no telemetry section documented.
- No uninstall section in the README → uninstall = `/plugin uninstall` + remove `.omc*`, `~/.omc`, config, statusLine.

## 6. Compatibility matrix

| Pair / area | Result | Why |
|---|---|---|
| OMC ↔ Claude Code 2.1.304 | LIKELY OK | uses standard plugin hooks; `PermissionRequest`, `SubagentStart`, `PostToolUseFailure` events must exist in 2.1.304 — **verify in Phase 1 smoke** |
| OMC ↔ Node 26.7 / Windows | OK with caveat | engines allow 26; `better-sqlite3` native build is the risk |
| OMC ↔ whynot-cut 3.0.0 hooks | CONFLICT RISK | both run PreToolUse on every Bash, both have Stop hooks (OMC ×5 + `stop_gate.sh`), both SessionStart/SessionEnd → latency + two "authorities" at turn end |
| OMC ↔ superpowers | INSTRUCTION CONFLICT | both inject a "use me first" process at SessionStart; superpowers says invoke brainstorming/TDD before anything, OMC routes by keywords |
| OMC keyword-detector ↔ our vocabulary | CONFLICT RISK | prompts with "autopilot", "team", "ralph", "ultrawork"… trigger OMC modes; whynot-cut has its own `autopilot` skill; the owner says "autopilot" in Arabic chats |
| OMC persistent modes (ralph/autopilot Stop-block) ↔ auto-resume routine + helper_loop | CONFLICT RISK | three loop authorities; a Stop hook that keeps a session alive burns the subscription and fights `whynot-cut-auto-resume-2` |
| OMC PermissionRequest handler ↔ sandbox rule / permission mode | SECURITY REVIEW NEEDED | must confirm it never auto-approves Bash outside our rules (owner rule: only review-runner runs unsandboxed) |
| OMC `omc-setup --global` ↔ `~/.claude/CLAUDE.md` | **BLOCKING if run** | default overwrite of the owner's global rules |
| OMC state `~/.omc`, `~/.config/claude-omc` ↔ "D drive for everything" | CONFLICT | lands on C: |
| OMC `.omc/` ↔ `WhyNotCut` repo | MINOR | not in `.gitignore`; dirty tree already — use `.git/info/exclude`, not a tracked edit |
| OMC Team mode ↔ H1/H2 helper system | REDUNDANT | we already have seats + worktrees + BOARD; tmux/psmux missing |
| OMC HUD statusLine ↔ existing config | OK | no statusLine today |
| OMC ↔ helper seats (h1/h2 profiles) | NOT AFFECTED if master/project scope | helpers use their own `CLAUDE_CONFIG_DIR`; their deny list blocks `npm -g` and settings edits |
| gstack ↔ this PC | NOT READY | no proper bun (Jan's 1.3.4 < tested 1.4.2), hooks go into global settings, Codex reviews on by default |
| gstack ↔ OMC ↔ superpowers | HEAVY OVERLAP | three review/plan/ship stacks |
| Karpathy guidelines | NO HARMFUL DUPLICATE | text in `Editing Plugin/CLAUDE.md` (1×) + `00-HQ/profile/CLAUDE.md` → copied into h1/h2 `CLAUDE.md` (by design D-008) + on-demand skill (master only). OMC adds `minimal-code-discipline` — same idea, do not enable as always-on |

## 7. Identified conflicts & findings

| ID | Finding | Severity | Owner of fix |
|---|---|---|---|
| C1 | `omc-setup --global` overwrites `~/.claude/CLAUDE.md` | HIGH | Phase 1 rule: never run it; `--local`/preserve only |
| C2 | OMC Stop ×5 + PreToolUse `*` + UserPromptSubmit on every prompt in every session of the scope | MED | install **project scope** only, measure latency |
| C3 | Keyword modes vs our words ("autopilot", "team") | MED | Phase 1 test; disable keyword-detector or avoid magic words |
| C4 | Loop authorities (ralph/autopilot, auto-resume routine, helper_loop) | MED | do not use persistent OMC modes on master |
| C5 | PermissionRequest Bash handler | MED | read `scripts/permission-handler.mjs` before enabling |
| C6 | OMC/gstack state on C: | LOW-MED | junction `~/.omc` → `D:\ClaudeData\omc` (and config dir) before first run |
| C7 | superpowers vs OMC process authority | LOW-MED | rule: superpowers = TDD/verification; OMC = explicit slash commands only |
| F1 | **H2 has no superpowers** (failed install, stuck temp clone) | MED | separate fix (not OMC) |
| F2 | Capability matrix stale; H1 superpowers 7.0.0 vs master 6.4.2 | LOW | master doc update |
| F3 | Memory index has duplicate entries (3× private-index race, 2× pre-mortem) | LOW | `consolidate-memory` later |
| R7 | `release/3.0` 114 commits not on GitHub | MED (loss risk) | Executor (push at tag) — flag only |

## 8. Account connectivity

| Seat | Identity | How it runs | Evidence | State |
|---|---|---|---|---|
| Master / Command Center | info@thewhynot.ai (Claude app) | desktop app; ~7 Claude Code sessions loaded (Executor, Adobe, K+M builder, intake, auto-resume, report, this one) | live processes + `list_sessions` | VERIFIED |
| H1 "Mayar" | mayar@thewhynot.ai, Team seat (stripe subscription) | **separate OAuth login** in its own `CLAUDE_CONFIG_DIR=D:\ClaudeData\accounts\h1`, same Windows user `LOQ`; headless `claude -p` runs driven by `helper_loop.py h1` (pythonw); now run 5 (opus, medium) on worktree `D:\WNC-work\h1` | `.claude.json` oauthAccount + live process + `auto/auto.log` | FILE-EVIDENCE + live process |
| H2 marketing@ | marketing@thewhynot.ai, Team seat | same design, `accounts\h2`; now run 4 = peer review of H1's S6b-r3 (opus, high) | same | FILE-EVIDENCE + live process |
| API lanes | Console (paid) | `lane_board.py`, `lane_reaper.py` running; paid work **HELD** by owner | processes + BUDGET-API.md | VERIFIED (idle by policy) |

Answer to Q7: the two helpers are **separate authenticated Claude seats** (separate logins in separate config
folders), **not** separate Windows profiles, and they work as **unattended agent processes** (headless runs), not
interactive chats. A live `claude auth status` per seat was **not** run: `Start-Helper.cmd` forbids starting a helper
from inside a Claude session because the parent login leaks into the child (incident 2026-10-19). I have no access to
their accounts and did not use them.

Coordination today: `BOARD.md` (master-only edits) → task cards → helper worktree branches → `00-HQ/inbox/<h>/`
report → hourly intake routine (fresh Opus review) → `MERGE-QUEUE.md` → Executor merges. Peer review H1↔H2.
Fences: per-seat deny lists, `claims/*.claim`, `LOCKED-AREAS.md`, shared heavy-job queue (`heavy.sh`).

## 9. Backup reference

`D:\ClaudeData\backups\omc-preflight-20261022-0326\` — copies (not moves) of: global `settings.json`, `CLAUDE.md`,
`whynot-cut.local.md`, `installed_plugins.json`, `known_marketplaces.json`; project `CLAUDE.md`, `.claude\settings*.json`,
`00-HQ\profile\CLAUDE.md`; h1/h2 `settings.json`, `CLAUDE.md`, `installed_plugins.json`; `git-state.txt` (all refs,
worktrees, dirty list). `SHA256SUMS` verified OK. `RESTORE.md` = copy-back steps. Secrets **not** copied
(`.credentials.json`, `.claude.json`); their SHA256 is in `NOT-COPIED.txt`.

## 10. Windows prerequisites

| Need | Have | For |
|---|---|---|
| Node 20–26 | 26.7.0 ✔ | OMC hooks/MCP |
| git, bash (Git Bash) | ✔ | OMC `setup-claude-md.sh`, hooks |
| Native build for `better-sqlite3` (if no prebuild) | VS Build Tools: unknown | OMC — check in smoke |
| tmux / psmux | ✘ | only OMC Team mode + `omc wait` (not needed) |
| bun ≥ 1.3.3 (1.4.2 tested), official per-user | ✘ (only Jan's bundled 1.3.4) | gstack only |
| VS 2022 C++ Build Tools | unknown | gstack `/cso` only |
| `~/.omc`, `~/.config/claude-omc` on D | ✘ | owner D-drive rule |

## 11. Recommended integration decisions (for Phase 1)

1. **Master seat only, project scope** (`Editing Plugin`), not user scope. Helpers, El-Modeeer and other projects stay
   untouched. Helpers only after a soak and an owner yes.
2. **Pin a tag**: `v5.7.6` (soaked) — not the 1-day-old v5.7.7 — via the marketplace source ref; no auto-update.
3. **Never run `/omc-setup --global`.** Skip the CLAUDE.md phase, or `--local` only after reading OMC's canonical
   `docs/CLAUDE.md`; root `Editing Plugin/CLAUDE.md` and `~/.claude/CLAUDE.md` stay byte-identical (checksum before/after).
4. Before first run: junction `C:\Users\LOQ\.omc` → `D:\ClaudeData\omc` and `C:\Users\LOQ\.config\claude-omc` →
   `D:\ClaudeData\claude-omc` (empty targets, recorded in the move log); add `.omc/` to `WhyNotCut/.git/info/exclude`.
5. **Read before enabling**: `permission-handler.mjs`, `keyword-detector.mjs`, the 5 Stop hooks and
   `pre-tool-enforcer.mjs`. If any auto-approves, blocks stop, or calls the network → disable that hook.
6. No Team mode, no `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS`, no ralph/autopilot persistence, no external providers
   (Codex/Gemini), no notification callbacks. Use OMC only through explicit slash commands.
7. Smoke test in a **fresh** master session (existing sessions keep their state; nothing is restarted): hook latency,
   whynot-cut guard still blocks a client-source write, Stop gate still works, keyword false-positive test, CLAUDE.md
   checksums unchanged, nothing written to C:.
8. **gstack: do not install now.** It is not present, needs a proper bun, writes global hooks and sends code to Codex by
   default, and duplicates OMC + superpowers. If the owner still wants it later: separate phase, selected skills only
   (e.g. `/browse`, `/qa`), `codex_reviews disabled`, telemetry off, update_check off.
9. Separate small fixes (not OMC): reinstall superpowers on H2 (F1), refresh the capability matrix (F2).

## 12. Remaining blockers

| # | Blocker | Type | Blocks |
|---|---|---|---|
| B1 | Owner's brief assumes gstack is installed — it is not. Install it, or drop it from the plan? | **Owner decision** | gstack part only |
| B2 | OMC on helper seats (H1/H2) now or after a master-only soak? (recommended: after) | **Owner decision** | helper rollout only |
| B3 | `better-sqlite3` / new hook events on CC 2.1.304 unproven | Technical, Phase 1 smoke | OMC enable |
| B4 | Helpers are mid-run (H1 run 5, H2 run 4, two test suites) — project-scope install does not touch them, but do not restart or change their profiles | Timing | none for master-only |

**Gate result:** current state verified; a master-only, project-scope, pinned OMC install with the §11 rules does not
put existing work at risk. Phase 0 = **DONE**.

**Exact next action (Phase 1, step 1):** in a fresh master session, create the two D-drive junctions for `~/.omc` and
`~/.config/claude-omc`, then add the OMC marketplace pinned to `v5.7.6` at **project scope** and read the four hook
scripts in §11.5 before enabling the plugin.
