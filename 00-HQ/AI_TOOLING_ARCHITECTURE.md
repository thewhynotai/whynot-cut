# AI TOOLING ARCHITECTURE — how the engineering system fits together

Adopted 2026-10-22 (AI-infra restart Phase 4, D-011). Rules of use: `AGENT_ROUTING_RULES.md`. Install details:
`setup/GSTACK_INSTALLATION_REPORT.md`, `omc/OMC_INSTALLATION_REPORT.md`, `setup/ENVIRONMENT_VERIFICATION.md`.

## 1. Layers

```
 Yunus (owner)  ──decisions──►  MASTER ORCHESTRATOR = Command Center + 00-HQ   (one source of truth)
                                 BOARD · cards · DECISIONS · PLAYBOOK · PROJECT_PLAN_AR · reports · intake
                                        │  hands out ONE card to ONE owner (branch/worktree)
                                        ▼
            ┌──────────── Builder session (master seat now; H1/H2 seats after Phase 6) ────────────┐
            │  superpowers (method: TDD, debugging, verification)   Karpathy (principles, always)   │
            │  OMC = execution layer for that card: /plan → executor / test-engineer / debugger /   │
            │        verifier agents → trace                                                        │
            │  gstack = specialist checks on demand: review · investigate · qa · browse · careful   │
            │  whynot-cut = the product's own skills, agents and guard hooks                        │
            └───────────────────────────────────────────────────────────────────────────────────────┘
                                        │  evidence + report into the card / inbox
                                        ▼
                 Master intake: fresh independent reviewer → verdict → executor merges → git/GitHub
```

## 2. What is installed where (main seat, this PC)

| Component | Version | Scope | Location | Config |
|---|---|---|---|---|
| gstack | 1.91.176.0 (`514fbfd`) | **global** (all main-seat sessions) | `~/.claude/skills/gstack` + 58 `gstack-*` skill folders | `~/.gstack/config.yaml` (→ `D:\ClaudeData\gstack`): telemetry off, codex_reviews disabled, skill_prefix true, artifacts sync off, auto_upgrade false, proactive false, timeline hook no |
| OMC | 5.7.6 (`07c115c`) | **project** = `Editing Plugin` folder (production) + `D:\ClaudeData\omc-pilot` (test bed) | `~/.claude/plugins/cache/omc/oh-my-claudecode/5.7.6` | `Editing Plugin\.claude\settings.json` (`enabledPlugins`, pinned marketplace `v5.7.6`, env profile, MCP `t` denied, **`Skill(...)` deny list for the never-use skills of both plugins**) + `.claude\omc.jsonc` (keywords off) + `~/.claude/.omc-config.json` (`claudeMdEnabled: false`) |
| superpowers | 6.4.2 | user | plugin cache | unchanged |
| Karpathy guidelines | 1.0.0 skill + text | user + project `CLAUDE.md` | — | unchanged |
| whynot-cut | 3.0.0 | user (+ 3.0.0 "live" in `D:\ClaudeData\wnc-live\try`) | plugin cache | unchanged; its guard hooks run beside OMC's and gstack's |
| Runtime | Bun 1.4.2 (D), Node 26.7.0, Git for Windows 2.56, Claude Code 2.1.304 (app bundle) | — | `D:\ClaudeData\bun\bin` first on user PATH | Phase 1 |

The production product repo is `WhyNotCut/` (GitHub `thewhynotai/whynot-cut`, branch `release/3.0`). It has no
`.claude/` folder of its own. Sessions open in the parent `Editing Plugin` folder, so the project settings and
project `CLAUDE.md` there are the integration point. No tool config was added inside the product repo.

## 3. Hook stack in a main-seat session (Editing Plugin folder)

| Event | whynot-cut | OMC (env-trimmed) | gstack |
|---|---|---|---|
| SessionStart | session context | 7 (state, memory, wiki; update check pointed at 127.0.0.1) | — |
| PreToolUse | **guard** (client sources read-only, Bash/PowerShell/file tools) | 2: pre-tool advisory + `git-guardrails` (dormant unless `OMC_GIT_GUARDRAILS=1` or an unattended mode) | only while `careful`/`guard`/`freeze`/`investigate`/`autoplan`/`plan-ceo-review` run |
| PermissionRequest | — | `permission-handler`: **auto-approves** read-only `ls`, `git status`, `gh pr/issue view`, `cat`/`sed`/`rg` on repo paths (known limit: headless runs get these without `--allowedTools`) | — |
| PostToolUse / Stop / PreCompact / SessionEnd | stop gate (off), session end | bookkeeping; Stop: `context-guard-stop` (94 %, max 2 blocks), `budget-guard`, `code-simplifier` (opt-in, off) | none (timeline hook off) |

OMC hooks also fire in sub-folders, e.g. the product repo: they write `.omc/state/` there. `WhyNotCut/.git/info/exclude`
lists `.omc/` (local, no commit) so it never reaches a commit.

Hooks fail open except the whynot-cut guard (fails closed for guarded calls).

## 4. Accounts

Main seat: everything above. Helper seats H1/H2: superpowers + Karpathy text + their profile rules; gstack and OMC
**not** enabled until Phase 6 tests them per seat (their own `CLAUDE_CONFIG_DIR` means global main-seat skills do not
reach them).

## 5. Phase 4 verification evidence (`D:\ClaudeData\setup-phase4\`, all real headless Claude Code 2.1.304 sessions in this folder)

| # | Test | Result |
|---|---|---|
| 1 | New session loads the integrated tools (`A-load.jsonl`) | init: superpowers + whynot-cut + oh-my-claudecode, **58 gstack + 48 OMC** skills (pilot showed 49); it answered from the new CLAUDE.md section correctly (master owns tasks; OMC autopilot not allowed; `browse stop` after gstack browse) |
| 2 | whynot-cut guard deny path with OMC + gstack loaded (`B-guards.jsonl`, fixture client in Temp) | Write to `CLIENT-T/assets/test.txt` **blocked**: "WhyNot Cut guard: the client's source folder (CLIENT-T/assets) is read-only" |
| 3 | gstack careful hook in a session (`careful-r2.jsonl`) | `git reset --hard HEAD` **blocked** by `[careful] Destructive…`. Gap: running the check script by hand on `git -C <dir> reset --hard HEAD~1` returns `{}` (no match), and in `B-guards.jsonl` that form ran unchecked in a throwaway repo |
| 4 | Enforced deny list (`deny-test.jsonl`) | `gstack-ship`, `oh-my-claudecode:autopilot` → "Skill execution blocked by permission rules"; `gstack-careful` allowed (2 of now 42 entries exercised) |
| 5 | OMC workflow on the product repo, read-only (`C-omc-explore.jsonl`) | `oh-my-claudecode:explore` agent located `reel` CLI parsing (`cli.py:1916-1966`, dispatch `2201-2219`); nothing edited |
| 6 | gstack workflow (`D-gstack-eng-review.jsonl`) | `/gstack-plan-eng-review` reviewed `AGENT_ROUTING_RULES.md`; its top finding (rules not enforced) led to test 4 |
| 7 | Hook latency (`latency.txt`, haiku, 1 turn) | Editing Plugin 7.6 s / 8.1 s vs empty folder 6.5 s / 6.4 s → **≈ +1.4 s per session start**, nothing per tool call measured as noticeable |
| 8 | Product repo untouched (`repo-head-before/after.txt`) | HEAD `3aa6167` before = after, dirty count 43 = 43 (the executor's own WIP); `plugin validate --strict` ✔ ×2; repo `pre-push` hook present and unchanged |

## 6. Rollback (integration only; install rollbacks are in the two install reports)

1. **Clean way:** restore `Editing Plugin\.claude\settings.json` and `CLAUDE.md` from
   `D:\ClaudeData\backups\setup-phase4-20261022-0454\` (`project-settings.json`, `project-CLAUDE.md`), delete
   `.claude\omc.jsonc`, then `claude plugin uninstall oh-my-claudecode@omc --scope project` from the `Editing Plugin`
   folder. (Uninstall alone leaves the env, deny list and marketplace entries in settings.json.) Also restore
   `PROJECT_PLAN_AR.md`, `PLUGIN_CAPABILITY_MATRIX.md`, `DECISIONS.md` from the same backup if wanted, and remove the
   `.omc/` line from `WhyNotCut/.git/info/exclude`.
2. Delete `~/.claude/.omc-config.json` (it only holds `claudeMdEnabled: false`).
3. gstack: `gstack-config set proactive true` restores the upstream default; nothing else of gstack was changed by Phase 4.
4. The routing docs (`AGENT_ROUTING_RULES.md`, this file) can stay; D-011 records the decision.
