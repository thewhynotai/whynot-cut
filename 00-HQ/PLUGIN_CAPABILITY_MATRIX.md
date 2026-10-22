# PLUGIN_CAPABILITY_MATRIX — Claude Code plugins and skills for this project (audit 2026-10-20)

Runtime: Claude Code (desktop app, Windows 11) on three seats: Yunus (info@, user-scope plugins), H1 and H2 (own
`CLAUDE_CONFIG_DIR` profiles under `D:\ClaudeData\accounts\h1|h2`). Sources: `~\.claude\plugins\installed_plugins.json`,
`settings.json` of each profile, the plugin caches, and GitHub (WebFetch). "Activated" = enabled for that seat.

| Capability | Source & version | Installed | Activated | Role / task | Test evidence | State |
|---|---|---|---|---|---|---|
| `karpathy-guidelines` skill (4 principles) | `andrej-karpathy-skills@karpathy-skills` 1.0.0, git sha 2c606141, repo multica-ai/andrej-karpathy-skills (forrestchang URL = same repo), MIT | YES (user scope, 2026-10-19) | Yunus: YES · H1/H2: NO (text only, by design D-008) | Every coding card and review | Session local_dc725f2c invoked it in a fresh CLI and got the 4 sections; listed as `andrej-karpathy-skills:karpathy-guidelines` here | VERIFIED installed + loadable |
| Same 4 principles as text | `Editing Plugin\CLAUDE.md` "Coding guidelines" (identical to SKILL.md but one blank line) + both helper profile `CLAUDE.md` | n/a | Always loaded | Same | Text compared 2026-10-20 | VERIFIED |
| Behaviour change from the principles | — | — | — | — | Controlled task: OPS-01 here (tests first, minimal surface, fence, surgical edits); reviewer checks it | UNVERIFIED until the OPS-01 review is recorded |
| Karpathy Cursor rule `.cursor/rules/karpathy-guidelines.mdc`, `CURSOR.md` | same repo | in cache only | — | Cursor is not used here | — | NOT_APPLICABLE |
| Karpathy upstream `CLAUDE.md` curl install | same repo | — | — | Would duplicate the text already present | — | NOT_APPLICABLE (deliberately not used) |
| superpowers (TDD, systematic debugging, writing/executing plans, requesting/receiving code review, verification-before-completion, worktrees) | `superpowers-marketplace` 6.4.2, sha 8ca22dba | YES (user) | Yunus + H1 + H2 | Builders (TDD), reviewers, master (plans, verification) | Skills listed in sessions; TDD flow used in OPS-01 (red 11 errors → green 11/11) | VERIFIED for TDD here; others UNVERIFIED |
| plugin-dev (plugin structure, hooks, skills, agents, validator, skill-reviewer) | `claude-plugins-official` sha a0b04d9d | YES (project scope, Editing Plugin) | Yunus in this folder | Builders of `whynot-cut/` manifests, agents, skills, hooks | Listed in sessions | UNVERIFIED (no run recorded today) |
| code-review, security-review, simplify | built-in session skills | built-in | YES | Reviews (master intake uses fresh Opus subagents instead) | — | UNVERIFIED |
| whynot-cut 2.2.1 (the product, Claude Code plugin) | marketplace `thewhynot-ai`, cache `…\thewhynot-ai\whynot-cut\2.2.1` | YES (user) | YES | Production use by editors on this PC | Live-verified 2026-10-11 (memory) | VERIFIED (2.2.1) |
| whynot-cut 3.0.0 (preview) | marketplace `thewhynot-ai-live`, project scope `D:\ClaudeData\wnc-live\try` | YES (project) | try folder only | Owner tries of the preview | Version match only | UNVERIFIED |
| cloudflare, windsor-ai, marketing, rampstack-seo, adobe/magnific connectors | various | YES | YES | Not used by this product | — | NOT_APPLICABLE |
| reel-editor 1.0.6/1.0.7 | cache only | NO (not registered) | NO | Old predecessor | — | NOT_APPLICABLE |

## Use by role
- **Builders (H1/H2):** superpowers TDD + verification; Karpathy text; plugin-dev when touching `whynot-cut/` plugin parts.
- **Reviewers (peer + master intake):** fresh Opus subagent with the card, full suite, mutants for HIGH tier only.
- **Master / Command Center:** writing-plans, verification-before-completion; Karpathy skill on demand.

## Duplication / conflicts
- Karpathy text loads once per seat (Yunus also has the skill, which loads only when invoked). No duplicate added.
- Owner rule "decide and continue" overrides the guideline "if uncertain, ask" (project `CLAUDE.md` §0).
- Two whynot-cut sources (2.2.1 user-wide, 3.0.0 project-scoped in the try folder) can collide in a session that sees
  both: keep 3.0 testing in the try folder or an isolated `--plugin-dir` (PLAYBOOK §7 live-smoke isolation).

## Minimal toolchain (recommended, no installs needed)
superpowers + plugin-dev + the Karpathy text + the built-in review skills. Nothing else to install.

## Update 2026-10-22 — AI-infra restart Phase 4 (this file is also the PLUGIN_COMPATIBILITY_MATRIX)

The restart brief asked for `PLUGIN_COMPATIBILITY_MATRIX.md`; this existing file is that matrix (no duplicate made,
D-011). Rows above are the 2026-10-20 audit; the rows below supersede them where they differ (e.g. whynot-cut is now
**3.0.0** user scope, not 2.2.1).

| Capability | Version / scope | Installed | Activated | Role | Test evidence | State |
|---|---|---|---|---|---|---|
| **gstack** | 1.91.176.0, global, prefix `gstack-*`, proactive off | YES (main seat) | main seat, every folder | specialist checks (`AGENT_ROUTING_RULES.md` §2) | doctor 0 fail; `/gstack-browse`, `/gstack-review` in real sessions (`setup/GSTACK_INSTALLATION_REPORT.md` §5) | VERIFIED |
| **OMC** | 5.7.6, project scope `Editing Plugin` (+ test bed `D:\ClaudeData\omc-pilot`) | YES | main seat in this folder | execution layer inside a card | omc-doctor no critical; plan / executor edit+verify / trace in real sessions (`omc/OMC_INSTALLATION_REPORT.md` Part A); Phase 4 load + guard tests (below) | VERIFIED (pilot), Phase 4 tests below |
| whynot-cut | 3.0.0 user; 3.0.0 live (try folder) | YES | YES | the product | `plugin validate --strict` ✔ (Phase 1) | VERIFIED (validate) |
| superpowers / Karpathy / plugin-dev | unchanged | YES | unchanged | method / principles / plugin building | — | unchanged |

### Compatibility (pairwise)

| Pair | Overlap / risk | Resolution | Status |
|---|---|---|---|
| OMC ↔ gstack | review, plan, qa, debug, release, browse names | gstack prefixed `gstack-*`; OMC namespaced `oh-my-claudecode:*`; routing table decides which one | no name clash; both load together (58 + 49 skills, hooks all `success`) |
| OMC ↔ superpowers | two "use skills first" instruction sources; `tdd`, `plan`, `verify` | superpowers = method, OMC = delegation; OMC `tdd` skill not used | resolved by D-011 rules |
| OMC ↔ whynot-cut | `autopilot` name; both add PreToolUse hooks | OMC autopilot never used; OMC keyword detector off; guard interplay tested in Phase 4 | see Phase 4 test |
| gstack ↔ whynot-cut | gstack `careful`/`guard` hooks + whynot-cut guard on Bash | both may run; strictest wins | see Phase 4 test |
| gstack ↔ Claude in Chrome / app browser | gstack wants "browse only" | not merged; app browser default, gstack browse for dev checks | rule §2 |
| OMC HUD ↔ Claude login | HUD can refresh/rewrite `.credentials.json` | HUD not enabled | blocked |
| Any ↔ outside providers | Codex, Gemini, Jev, gbrain, ngrok | all off / not installed | blocked |
