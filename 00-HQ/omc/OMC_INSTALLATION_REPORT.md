# OMC Installation Report — Phase 1

- Date: 2026-10-22 03:30–03:50 (Cairo) · Seat: master (info@) · Claude Code 2.1.304 (desktop app bundle) · Windows 11
- Builds on: `OMC_INTEGRATION_PREFLIGHT.md` (Phase 0) in this folder
- Raw evidence: `D:\ClaudeData\omc-pilot-evidence\` (`run1-probe.jsonl` … `run5-review.jsonl`, `before.sha256`, C: listings)
- **Verdict:** OMC **loads and passes its diagnostics in an isolated pilot**, under a conservative profile. It is **not**
  "fully operational": several features are disabled on purpose or untested (§6). gstack was dropped by the owner
  (2026-10-22), so there is no gstack to keep working.

## 1. Installed version
| Item | Value |
|---|---|
| Plugin | `oh-my-claudecode@omc` **5.7.6** |
| Git commit | `07c115c797f9ec14724a74534b558cc8d1cc8b17` (annotated tag `v5.7.6`, 2026-10-21 19:36 +0900) |
| Why not 5.7.7 | released < 24 h before install; 5.7.6 is the previous tag and the exact code that was audited |
| npm runtime (`oh-my-claude-sisyphus`, `omc` CLI) | **not installed** (no feature in scope needs it) |

## 2. Installation method
The official marketplace workflow, run non-interactively through the bundled CLI so every result was captured (the
`/plugin …` slash commands are the same operations):
```
cd D:\ClaudeData\omc-pilot
claude plugin marketplace add "https://github.com/Yeachan-Heo/oh-my-claudecode.git#v5.7.6" --scope project
claude plugin install oh-my-claudecode@omc --scope project
claude -p "/oh-my-claudecode:omc-setup --local"
```
Both CLI steps returned `outcome: ok`. `/omc-setup` ran **with `--local` only**. The default and `--global` setup would
overwrite `~/.claude/CLAUDE.md` and write a global `statusLine`, which owner rules forbid.

**Scope = one pilot folder, not the project folder.** `Editing Plugin\.claude\settings.json` is shared by every master
session (Executor, Adobe, K+M builder, intake and report routines, auto-resume). Enabling OMC there would load 25 new
hooks into all of them on their next start. The pilot keeps OMC away from them until Phase 2 decides otherwise.

## 3. Installation paths
| Path | What |
|---|---|
| `D:\ClaudeData\omc-pilot\` | pilot git repo (throwaway; `README.md`, `calc.py`) |
| `…\omc-pilot\.claude\settings.json` | marketplace pin, `enabledPlugins`, conservative `env` (§7), deny for MCP server `t` |
| `…\omc-pilot\.claude\settings.local.json` | `ask` rules that neutralise OMC's auto-approve |
| `…\omc-pilot\.claude\omc.jsonc` | `keywordDetector.disabled` (all keywords) |
| `…\omc-pilot\.claude\CLAUDE.md` | written by `omc-setup --local` (OMC:START..OMC:END, 73 lines) |
| `…\omc-pilot\.claude\skills\wiki\` | installed by `omc-setup --local` |
| `…\omc-pilot\.omc\` | OMC state (project-memory, sessions); git-excluded by setup via `.git/info/exclude` |
| `C:\Users\LOQ\.claude\plugins\cache\omc\oh-my-claudecode\5.7.6` (= `D:\Claude\dot-claude\…` by junction) | plugin code |
| `C:\Users\LOQ\.claude\plugins\marketplaces\omc` | marketplace clone |
| `D:\Claude\dot-claude\.omc\` | update-check cache, cache-occupancy |
| `D:\Claude\dot-claude\.session-stats.json`, `projects\D--ClaudeData-omc-pilot\` | per-session stats / transcripts |
| `C:\Users\LOQ\.omc` → `D:\ClaudeData\omc` | junction made in Phase 1 step 1 (OMC global root) |
| `C:\Users\LOQ\.config\claude-omc` → `D:\ClaudeData\claude-omc` | junction; **not used on Windows** (OMC reads `%APPDATA%\claude-omc`, which does not exist) — harmless, can be removed |
| `D:\ClaudeData\omc-src\v5.7.6` | read-only audit clone |

## 4. Verified commands and checks
| # | Requirement | Result | Evidence |
|---|---|---|---|
| 1 | Installation + version | **PASS**: 5.7.6, sha 07c115c, scope project, `projectPath D:\ClaudeData\omc-pilot` | `installed_plugins.json`, `claude plugin details` |
| 2 | Skills recognised | **PASS**: 49 `oh-my-claudecode:*` slash skills, 19 `oh-my-claudecode:*` agents in the session init | `run1-probe.jsonl` |
| 3 | `/omc-doctor` | **PASS: "HEALTHY with small warnings".** Warnings: latest-version check blocked (on purpose), config-dir write test skipped (read-only run), HUD not set up (on purpose) | `run3-doctor.jsonl` |
| 4 | Generated settings and hooks | **PASS**: no hooks written to any settings file. OMC hooks come only from the plugin's `hooks/hooks.json` (11 events). `omc-setup --local` wrote only pilot files | doctor checks 2–3, file diff |
| 5 | gstack still works | **N/A**: gstack is not installed and was dropped by the owner | Phase 0 §4 |
| 6 | Native team requirements | Documented, **not enabled**: `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1`, tmux (Windows: `psmux` via winget) for `omc team` CLI workers and `omc wait` | README |
| 7 | Windows compatibility | **Hooks run on Windows**: 7 SessionStart + 2 UserPromptSubmit + 6 Stop + Pre/PostToolUse all returned `success`; probe session 13 s | `run1`, `run5` |
| 8 | Linux/WSL, external CLIs, paid APIs | Listed in §6 | audit |
| 9 | HUD / statusline | **Works standalone** (rendered branch, model, 5-hour usage bar, context bar). **Not enabled**: see finding H1 | standalone run, not kept |
| 10 | Skill naming conflicts, global config | §8 | |
| 11 | Harmless skill invocation | **PASS**: `/oh-my-claudecode:review calc.py` (read-only) returned a correct "no findings" review. A Bash probe passed through **both** the whynot-cut guard and OMC's PreToolUse hooks | `run5-review.jsonl` |
| — | Keyword safety | **PASS**: a prompt with "autopilot … end to end" created **no** mode state (`.omc/state` has only `session-started` files) | `run4-keyword.jsonl` |
| — | Network | update check **neutralised** (`update-check.json` source=marketplace, claude:unknown); no notification or Jev variables set | `.omc/update-*.json` |
| — | MCP server `t` | connects, but **0 tools exposed** (deny rule works) | `run1` tools list |
| — | Existing environment | **PASS**: SHA256 of global `CLAUDE.md` + `settings.json`, project `CLAUDE.md` + `.claude/settings*.json`, h1/h2 `settings.json` + `CLAUDE.md` **unchanged** after every run; no new entries in `C:\Users\LOQ` | `before.sha256`, `c-*.txt` |

Usage: 5 short headless runs on the master subscription (Sonnet). No API key, no Console credit.

## 5. Working capabilities (in the pilot profile)
- All 49 skills invocable by explicit slash command; 19 agents available for delegation.
- `/omc-doctor`, `/omc-setup --local`, `/oh-my-claudecode:review`.
- Project memory (`.omc/project-memory.json`), session tracking, PreCompact/SessionEnd bookkeeping.
- `git-guardrails` (inactive without a mode; only blocks push / reset --hard / clean -f / branch -D / checkout .).
- `context-guard-stop` (threshold raised to 94 %, at most 2 blocks per session).

## 6. Failed, disabled or unavailable capabilities
| Capability | State | Why |
|---|---|---|
| Keyword auto-activation (autopilot, ralph, ultragoal, ralplan, …) | **DISABLED** | "autopilot" anywhere in a sentence, an Arabic question, or `/whynot-cut:autopilot` starts a mode that blocks Stop up to 20× |
| Persistent modes (ralph / autopilot / ultragoal) | **DISABLED** (`persistent-mode` skipped) + not to be started (owner restriction) | conflicts with auto-resume and the helper loops |
| `workflow-drift-guard` | **DISABLED** | forces AskUserQuestion; breaks headless runs |
| `skill-injector` | DISABLED | not needed (no learned skills) |
| Read budget (deny full reads > 45 KB) | **OFF** | would block transcripts and large JSON in WhyNot Cut work |
| Team mode / `omc team` / CLI workers | NOT AVAILABLE | no tmux/psmux; experimental flag off; the H1/H2 seats already cover it |
| `/ask`, Codex/Gemini/Grok/Antigravity providers | NOT INSTALLED / not used | external CLIs, possible cost, data leaves the PC |
| Notifications (Telegram, Discord, Slack, webhook, OpenClaw) | OFF (`OMC_NOTIFY=0`) | external services |
| Jev (`api.typesafe.ai`) | OFF | sends prompt excerpts to a third party |
| Named autopilot workflow profiles | UNAVAILABLE on Windows | need Linux `flock` |
| MCP server `t` (OMC tools) | DENIED | 1.2 MB bundle not reviewed |
| HUD statusline | **NOT ENABLED** (finding H1) | |
| `better-sqlite3` | ABSENT | hooks fall back to file locks (no failure seen) |
| Live latest-version check | BLOCKED on purpose | pinned version |
| whynot-cut guard **deny** path inside a pilot session | NOT RE-TESTED | needs a real client folder (off-limits); the guard ran on every Bash call next to OMC's hooks |
| Latency under the real master workload | NOT MEASURED | only small probes |

**H1. The HUD handles the login token.** `dist/hud/usage-api.js` reads the Claude OAuth token from
`~/.claude/.credentials.json`, calls `api.anthropic.com/api/oauth/usage`, and can **refresh the token and rewrite
`.credentials.json`** (lines 589, 742–765, 1127–1143). That could race Claude Code's own refresh and log the master seat
out. The standalone test read the token and made one usage call to Anthropic (first-party, free); `.credentials.json`
was not rewritten (mtime 03:32 is from Claude Code's own refresh, before the test). Decision: no HUD. A global
`statusLine` would also change every session on this seat.

## 7. Windows compatibility findings
- The hooks are node-only and fail open; all of them ran green on node 26.7 / Git Bash. A timed-out hook is reaped with `taskkill /T /F`.
- OMC's user config is `%APPDATA%\claude-omc` on Windows (not `~/.config`); global state is `~/.omc` (junctioned to D).
- SessionStart replaces old plugin versions with **junctions** in the plugin cache and deletes old folders
  (`rmSync`). Watch this on upgrades (owner rule: never delete through junctions). Nothing to delete today (one version).
- tmux/psmux are missing → no Team mode. WSL exists but was not needed.
- The CLI refused `${VAR:-…}` and quoted compound commands in headless mode ("can't be checked before it runs"); the
  setup skill retried with plain paths and succeeded.
- `setup-claude-md.sh` printed a false "Plugin NOT found" line although the plugin was installed and the coordinator succeeded.

## 8. Configuration changes and conflicts
**Global (outside the pilot), all expected:**
- `plugins\known_marketplaces.json`: + `omc` (git, ref v5.7.6). `plugins\installed_plugins.json`: + `oh-my-claudecode@omc` (project scope).
- `D:\Claude\dot-claude\.omc\`, `.session-stats.json`, `projects\D--ClaudeData-omc-pilot\` (written by pilot sessions only).
- Two junctions in `C:\Users\LOQ` (logged in `D:\ClaudeData\backups\omc-preflight-20261022-0326\junctions.log`).
- Not by us: plugin-dev auto-updated to `af59ee3a` at 03:26 (before the install); `C:\Users\LOQ\.claude.json` is rewritten by Claude Code on every session.
- **Unchanged (checksums):** `~/.claude/CLAUDE.md`, `~/.claude/settings.json`, project `CLAUDE.md`, project `.claude/settings*.json`, helper profiles.

**Pilot profile (`D:\ClaudeData\omc-pilot\.claude\settings.json` `env`):**
```
OMC_SKIP_HOOKS=keyword-detector,skill-injector,persistent-mode,workflow-drift-guard
OMC_READ_BUDGET=off
OMC_UPDATE_REGISTRY_BASE=http://127.0.0.1:9
OMC_NOTIFY=0
OMC_JEV=off
OMC_BUDGET_ENFORCE=off
OMC_CONTEXT_GUARD_THRESHOLD=94
permissions.deny: mcp__plugin_oh-my-claudecode_t
```
Hooks that cannot be switched off: session-start (now offline), context-guard-stop (94 %), permission-handler
(auto-allows read-only `ls`/`git status`/`cat`/`head`/`sed -n`/`rg` → neutralised by the `ask` rules in
`settings.local.json`), session-end, pre-compact, wiki, project-memory.

**Skill names:** every OMC skill is namespaced `oh-my-claudecode:*`, so there are no hard clashes. Same bare names as
ours (risk only of the model picking the wrong one from a description): `autopilot` (whynot-cut), `review`
(built-in code-review), `tdd` (superpowers test-driven-development), `plan`, `debug`, `verify`, `release`, `team`,
`diagram`, `research`, `remember`. A second instruction authority appears at SessionStart: superpowers' "use skills
first" plus OMC's CLAUDE.md block. Phase 2 must set one routing rule.

## 9. Rollback (copy-safe, no junction walking)
1. `claude plugin uninstall oh-my-claudecode@omc --scope project` (cwd `D:\ClaudeData\omc-pilot`), then
   `claude plugin marketplace remove omc`.
2. Delete the pilot: `D:\ClaudeData\omc-pilot` holds no links. Check with `dir /AL /S` first, then `rmdir /s /q`.
3. `rmdir "C:\Users\LOQ\.omc"` and `rmdir "C:\Users\LOQ\.config\claude-omc"` (links only, never `/s`), then
   `rmdir "C:\Users\LOQ\.config"` if empty. Their targets `D:\ClaudeData\omc`, `D:\ClaudeData\claude-omc` can then go.
4. Remove `D:\Claude\dot-claude\.omc`, `.session-stats.json`, `projects\D--ClaudeData-omc-pilot` (after a `dir /AL` check).
5. Compare with `D:\ClaudeData\backups\omc-preflight-20261022-0326\SHA256SUMS`; restore from there with `RESTORE.md` if anything differs.
6. Optional: delete `D:\ClaudeData\omc-src` (audit clone).

## 10. Phase 2 readiness decision
**READY for Phase 2 (design and docs), with conditions:**
- Keep the pilot profile (§8) as the only allowed OMC profile. Any wider scope (the `Editing Plugin` folder, helper
  seats) is a Phase 2 decision with its own smoke test.
- No HUD, no Team mode, no persistent modes, no external providers, no unattended OMC runs.
- Before any production use: measure hook latency on a real master task, and re-test the whynot-cut guard deny path
  in a fixture client folder (`whynot-test/`).
