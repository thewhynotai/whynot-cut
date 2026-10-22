# SETUP AUDIT — Phase 0 of the AI-infrastructure restart

- Date: 2026-10-22, 03:50–04:05 Cairo (system clock = Cairo, UTC+3). Seat: main account (info@), Claude desktop app.
- Method: read-only inventory (directory listings, `git` read commands, process list, Task Scheduler, Claude routines,
  session list, config files). Nothing was installed, reinstalled, stopped, started or deleted. The only writes are
  this folder (`00-HQ/setup/`) and the backup folder in `SETUP_BASELINE.md`.
- Secrets: credential files were checked for **presence and date only**, never opened. MCP servers are listed by name.
- Companion files: `SETUP_BASELINE.md` (the recovery checkpoint) and `SETUP_PHASE_TRACKER.md` (Phases 0–9).

Labels: **VERIFIED** = seen directly in this audit · **REPORTED** = taken from an existing doc, not re-checked ·
**NOT INSPECTED** = not accessible or out of scope (said so explicitly).

---

## 0. Headline findings

| # | Severity | Finding | Evidence |
|---|---|---|---|
| F1 | **CRITICAL** | **Execution is NOT stopped.** The brief says all execution was stopped; at 03:53 the whole system was live: 3 main-account sessions running, both helper AUTO loops running headless `claude -p` jobs, 6+ test suites and 2 mutation runs, the API-lane supervisor and reaper, 3 enabled Claude routines (one of them resumes stopped sessions every 30 min), 3 Windows scheduled tasks (one restarts helper loops every 30 min) and a Startup script. 00-HQ files were still being edited (BOARD.md, AUTOMATION_RUNBOOK.md at 03:55). | §9, §12 |
| F2 | **HIGH** | **Three setup/orchestration threads exist at once.** (a) the Command Center = master (`local_a36b6974`, running), owner of 00-HQ; (b) "Multi-account Claude control center" (`local_15b89011`, running) is building `00-HQ/control-center/` right now (files written 03:37–03:52); (c) the OMC preflight/installation sessions (`local_10ffbedc`, `local_77ee42a8`) that wrote `00-HQ/omc/` and `omc-lab/`. This session is a fourth. Risk: competing orchestrators and conflicting charters. | §9, §10 |
| F3 | **HIGH** | **Work exists only on this PC.** `release/3.0` is **114 commits ahead** of GitHub (local c963132, origin 322d8a5). The newest off-PC copy is `ops/backup-release-3.0-20261020` = 4c1e59c (2 days old). Helper branches (`h1/*`, `h2/*`) are local only. The main checkout has 42 uncommitted files; 5 other worktrees are dirty. One disk failure would lose 2 days of work. | §3 |
| F4 | MEDIUM | **OMC is installed in two places, one undocumented.** `oh-my-claudecode@omc 5.7.6` has project scope in `D:\ClaudeData\omc-pilot` (in the installation report) **and** in `Editing Plugin\omc-lab` (created 03:48, after the report; not in it). `omc-lab/README.md` points to `00-HQ/AGENT_COORDINATION.md`, which does not exist (D-001 maps that name to `PLAYBOOK.md`). | §7 |
| F5 | MEDIUM | **Docs disagree with the machine.** (a) `PROJECT_PLAN_AR.md` §5 and memory say the installed plugin is 2.2.1; installed is **whynot-cut 3.0.0** (user scope, plus a 3.0.0 "live" copy for `D:\ClaudeData\wnc-live\try`). (b) OMC preflight says `wsl.exe` present; WSL is **not installed**. | §4, §6 |
| F6 | MEDIUM | **Bun is not a real install.** The only `bun` (1.3.4) is bundled in the Jan app and is on PATH from Jan's folder, together with Jan's `uv` 0.9.16. Any tool that calls `bun` or `uv` gets Jan's copies. gstack needs bun ≥ 1.3.3 (tested 1.4.2). | §4 |
| F7 | INFO | **gstack is not installed** (no trace in `~/.claude`, `D:\Claude`, `D:\ClaudeData`). The OMC report records the owner dropping it on 2026-10-22. | §7 |
| F8 | LOW | `claude` CLI and `ffmpeg` are not on PATH. The CLI exists only inside the desktop app (`AppData\Roaming\Claude\claude-code\2.1.304`). The engine uses its own runtimes. | §4 |

---

## 1. Hardware and Windows — VERIFIED

| Item | Value |
|---|---|
| Machine | Lenovo LOQ 15IRX9 (model 83DV), Intel i7-14700HX |
| RAM | 31.7 GB; 64 % used at 03:53 (11.3 GB free). Below the 85 % brake |
| GPU | NVIDIA RTX 4060 Laptop 8 GB (driver 617.42, idle 0 %) + Intel UHD |
| OS | Windows 11 Pro 10.0.26300; last boot 2026-10-21 23:42 |
| Disks | C: 286 GB used / **201 GB free** · D: 231 GB used / **235 GB free** |
| TEMP | `D:\ClaudeData\Temp` (on D, as required) |
| Junctions (C → D) | `~\.claude` → `D:\Claude\dot-claude` · `~\.whynot-cut` → `D:\Claude\whynot-cut-home` · `~\.omc` → `D:\ClaudeData\omc` · `~\.config\claude-omc` → `D:\ClaudeData\claude-omc` (unused on Windows) |
| Adobe | Premiere Pro 2026, After Effects 2026, Media Encoder, Photoshop, Illustrator, Bridge, Acrobat installed. None open at audit time (only Acrobat's notification client) |

## 2. Project directories — VERIFIED

Root: `D:\0 Work\0 Pegasus IMC Agency\00 TWN\0 TWN AI\Editing Plugin` (not a git repo itself).

| Folder / file | What it is | Notes |
|---|---|---|
| `WhyNotCut/` | **The product repo** (git) | see §3 |
| `00-HQ/` | **The existing Master Orchestrator** ("Command Center"): BOARD, PLAYBOOK, roles, tasks, inbox, intake, reviews, reports, tools, routines' prompts | Outside git; mirrored to GitHub branch `ops/hq` by the report routine (D-004). Moves into the repo at the Gate 4 tag (OPS-04) |
| `00-HQ/control-center/` | New localhost dashboard + per-account consoles, **being built now** by `local_15b89011` | F2. Has its own AUDIT.md; no BOARD card or DECISIONS entry found for it |
| `00-HQ/omc/` | OMC Phase 0 preflight + Phase 1 installation report | REPORTED content, §7 |
| `omc-lab/` | Second OMC pilot (git repo, 1 commit) | F4 |
| `PROJECT_PLAN_AR.md` | Owner dashboard (Arabic), auto-refreshed | Authoritative; §5 stale on installed version |
| `CLAUDE.md`, `.claude/` | Project rules; project settings (plugin-dev on, 3 MCP servers denied) | |
| `WhyNot-Cut-3.0-Addendum/` | Addenda A–M (plans, research) | Planning, read-only here |
| `_archive/` | Old zips 1.0.7 → 2.2.1, archived plans (with manifest) | |
| `new plugin code/` | Kalam / Hush / Tidy source drops (+ macOS `._*` files) | Not inspected in depth |
| `whynot-test/` | Test client folders and spikes (fixtures) | Not inspected in depth |
| `خد دا كوبي للويندوز` / `للماك` | 3.0 preview packages (PREVIEW-3.0.0-p4, commit 322d8a5) | REPORTED: 50+ commits behind |
| `_private-profiles/`, `_private-evidence/` | Client profile and a frame screenshot | **Client data: not opened** |
| `T4.14-راجع-التفريغ/` | Transcript-review handoff | Not opened |
| Other docs | API-PAUSE-AR, COMPETITORS-AR, PARKED-SESSIONS, VALIDATION-PLAN-AR, SAVED-LATER…, card | Preserved, not changed |

No `AGENTS.md` exists anywhere in the project (depth 3).

## 3. Git — VERIFIED

Repo `WhyNotCut/`, remote `origin` = `https://github.com/thewhynotai/whynot-cut.git`. `.git` = 99 MB. No stash.

| Branch | Local | GitHub | State |
|---|---|---|---|
| `release/3.0` (checked out) | c963132 (2026-10-21 22:30) | 322d8a5 | **local ahead 114, behind 0** |
| `main` | 4831de5 (= v2.2.1) | 4831de5 | in sync |
| `ops/hq` | 1b1c836 | 1b1c836 | in sync |
| `ops/backup-release-3.0-20261020` | — | 4c1e59c | remote-only backup |
| `h1/BL-02, BL-16, BL-17, S6b, SETUP-H1` · `h2/BL-03, BL-04 (+2 base copies), SETUP-H2` | local | none | local only |

Tags: v2.1.0 … v2.2.1, v3.0.0-p0 … **v3.0.0-p3.1** (latest). `v3.0.0-p4` does not exist yet.

Worktrees (12): main checkout (42 dirty: 19 modified, 23 untracked — brand_web J3/J4 modules, manual-verse tests, a
stray `whynot-cut/p.out`); `D:\WNC-work\h1` (9 dirty, `h1/BL-17`), `h2` (clean, `h2/BL-04`), `ops`, `ops-check`,
`review`, `review-h1`, `review-h2` (clean); four detached temp worktrees in `D:\ClaudeData\Temp`
(`bl24-f3` 8, `bl24-mut3` 14, `fix3-wt` 10, `t26r6-wt` 4 dirty) used by live mutation/fix runs.

**Risks:** F3 (unpushed), uncommitted work that belongs to running sessions (must not be touched by setup work), temp
worktrees under TEMP (a TEMP clean-up would break them), the shared-index commit race already recorded in memory.

## 4. Toolchain — VERIFIED

| Tool | Version | Source / note |
|---|---|---|
| git | 2.56.0.windows.2 | Git for Windows (ucrt64) |
| node / npm / npx | 26.7.0 / 11.19.0 | `C:\Program Files\nodejs` |
| python | 3.13.2 | `C:\Python313` (+ `py` launcher). Engine uses its own CPython 3.12.15 in `~\.whynot-cut` |
| **bun** | **1.3.4** | **Jan app bundle** (`AppData\Local\Programs\Jan\bun.exe`), not standalone (F6) |
| uv | 0.9.16 | also Jan's bundle |
| gh | 2.102.0 | winget |
| winget | 1.29.380 | |
| cf (Cloudflare CLI) | 1.0.0-beta.14 | npm global |
| claude CLI | 2.1.304 | only inside the desktop app; **not on PATH** |
| ffmpeg | — | not on PATH (engine/hosts ship their own; not re-verified) |
| WSL | **not installed** | F5 |
| tmux / psmux | missing | OMC Team mode unavailable |
| pnpm / yarn / deno / wrangler | missing | not needed today |

## 5. Product source, builds and tests — VERIFIED (counts) / REPORTED (results)

- 4,379 tracked files: 2,115 SVG (templates), 657 MD, 510 Python, 349 JSON, 130 TS, 88 HTML, 85 JS, 62 sh.
- Parts: `whynot-cut/` (Claude plugin: 47 skills files, 19 agents, `engine/` Python `reel` engine, `templates/`,
  `evals/` 520 files, `tests/` 210 Python test modules); `adobe/` (`panel-ui`, `premiere-uxp` — TypeScript, `node --test`,
  53 test files; `cep-bridge`; `tools`); `installer/`; `guide-ar/`; `docs/` (specs, plans, Adobe evidence); `tools/security`.
- Plugin manifest: whynot-cut **3.0.0**; marketplace `thewhynot-ai` 3.0.0. Packaging: `package.py`.
- CI: `.github/workflows/macos.yml`, `security.yml`, `security-watch.yml`, `security-watch-paths.yml`.
- Premiere integration: REPORTED working — chat → bridge builds a Premiere sequence, exports and checks frames
  (live 2026-10-14/15, Premiere 26.5.2, bridge 3.1.1). **Not working yet:** the UXP panel inside Premiere (= V1).
- Suites: REPORTED 8,899 OK on helper seat (ENV-01, 10-20); Gate 3 Windows 3,374 OK + macOS CI. **Not re-run in this
  audit** (suites were already running; Phase 0 is read-only).
- Gate status: Stage 1 = Gate 4 (`v3.0.0-p4`) ≈ 55 % per BOARD; open items in `WhyNotCut/PROGRESS.md`.

## 6. Claude configuration — VERIFIED

**Main seat (`~/.claude` = `D:\Claude\dot-claude`):**
- `CLAUDE.md` (global rules, 3.8 KB, 2026-10-14). `agents/`: brand-systems-designer, marketing-short-video-editing-coach.
- `settings.json`: 5 allow rules; no hooks in the file; enabled plugins: superpowers, whynot-cut, cloudflare,
  andrej-karpathy-skills, experiment-coach. `crossSessionInbound: accept`.
- Installed plugins: superpowers 6.4.2 (user + one other project), whynot-cut 3.0.0 (user), whynot-cut-live 3.0.0
  (project `D:\ClaudeData\wnc-live\try`), cloudflare 1.0.2, andrej-karpathy-skills 1.0.0, experiment-coach,
  plugin-dev af59ee3a (project = Editing Plugin; auto-updated 10-22 03:26), **oh-my-claudecode 5.7.6 ×2** (F4).
- Marketplaces: superpowers-marketplace, local-desktop-app-uploads, claude-plugins-official, thewhynot-ai,
  cloudflare, thewhynot-ai-live, karpathy-skills, growth-marketing-os, omc.
- User skills: brand-identity-pipeline (+workspace), el-modeeer-story-board, framer, framer-code-components,
  llm-council, reels-editing-pipeline, synced.
- MCP (user): `magnific` only (denied in this project). Connectors from the app (Google, Adobe, Gmail, etc.) exist
  but are app-level; several need auth. Hooks come only from plugins (superpowers, whynot-cut guard; OMC only in pilot folders).

**Project (`Editing Plugin/.claude`):** settings.json enables plugin-dev, disables windsor-ai, denies `mcp__magnific`
and two app MCP servers; settings.local.json = 1 permission list; skill `skill-finder`.

**Helper seats:** `D:\ClaudeData\accounts\h1`, `h2` = `CLAUDE_CONFIG_DIR` profiles with own settings.json and CLAUDE.md
(copy of `00-HQ/profile/CLAUDE.md`), own plugins folder.

## 7. OMC and gstack

- **OMC — VERIFIED present, REPORTED behaviour.** 5.7.6 (sha 07c115c), project scope, conservative profile
  (keyword detector, persistent modes, drift guard, skill injector off; no HUD; no notifications; update check
  pointed at 127.0.0.1:9; MCP server `t` denied). npm runtime / `omc` CLI not installed. Pilot repos:
  `D:\ClaudeData\omc-pilot` (1 commit, `.claude/` untracked) and `Editing Plugin\omc-lab` (1 commit, same profile,
  `.omc/state` shows one session at 03:48–03:49). Audit clone `D:\ClaudeData\omc-src\v5.7.6`. Rollback steps exist
  in `00-HQ/omc/OMC_INSTALLATION_REPORT.md` §9 and a preflight backup in `D:\ClaudeData\backups\omc-preflight-20261022-0326`.
  Known open points from that report: HUD token-refresh risk (not enabled), hook latency on real work not measured,
  whynot-cut guard deny path not re-tested with OMC, skill-name overlaps (autopilot, review, tdd, plan…), a second
  instruction authority at SessionStart (superpowers + OMC) needs one routing rule.
- **gstack — VERIFIED absent.** Upstream needs bun ≥ 1.3.3, writes global hooks and a CLAUDE.md section, keeps state
  in `~/.gstack` (C:), and sends code to Codex by default (REPORTED from preflight). Owner dropped it 2026-10-22 (REPORTED).

## 8. Helper accounts — VERIFIED (identity + activity), NOT INSPECTED (interactive login)

| Seat | Identity (`oauthAccount`) | Profile | Credentials file | Activity |
|---|---|---|---|---|
| Main | info@thewhynot.ai, org thewhynot.ai, subscription | `~/.claude` | (app-managed) | this app |
| H1 | mayar@thewhynot.ai, same org, subscription | `D:\ClaudeData\accounts\h1` | present, refreshed 10-22 00:31 | loop `running`, run 5 since 02:56 (opus, medium), worktree `D:\WNC-work\h1` |
| H2 | marketing@thewhynot.ai, same org, subscription | `D:\ClaudeData\accounts\h2` | present, refreshed 10-21 21:59 | loop `running`, run 4 since 03:17 (opus, high) — peer review of S6b |

Both helpers are reachable and authenticated (their headless runs are working now). I did not open an interactive
session on either seat.

## 9. Live processes at 03:53 — VERIFIED

- Claude desktop app + **8 Claude Code sessions** (stream-json) on the main account, incl. the running sessions
  Command Center `local_a36b6974`, K+M builder `local_b32f950e`, control-center builder `local_15b89011`.
- Helpers: `helper_loop.py h1` (pid 9756), `helper_loop.py h2` (pid 21664), headless `claude -p` for h1 (pid 51304)
  and for h2's peer review (pid 56052).
- Tests: 3 full `unittest discover` suites, `test_bridge_queue`, `test_t25_r2`, manual-verse tests; mutation runs
  `BL-24/mutate.py` and `K-T7/r2/mutate_r2.py`.
- Lanes: `lane_board.py`, `lane_reaper.py` (lanes on HOLD by design). Engine server `reel serve` (×2 python), a
  `server.py` (likely control-center), `agency_live.py`, a Codex artifact host daemon (node).
- 165 bash, 43 python, 10 powershell processes in total. RAM 64 %.

## 10. Master Orchestrator and its files — VERIFIED present

`00-HQ/README.md` (start here) · `PLAYBOOK.md` (rules; = AGENT_COORDINATION) · `roles/` (MASTER, MASTER-INTAKE,
HELPER-ENGINE, HELPER-PRODUCT, API-LANES, MAC-TESTER, PRIMARY-REPORT, WATCHDOG) · `BOARD.md` (only task list) ·
`TASK_QUEUE.yaml` (generated) · `tasks/` (14 live cards + archive) · `inbox/h1,h2,lane,mac` · `intake/` (lock, state,
13 stale locks) · `reviews/` · `reports/` (47 dated reports + 2026-10-20 audit) · `DECISIONS.md` (D-001…) ·
`AUTOMATION_RUNBOOK.md` · `BUDGET-API.md` (API-500 PLANNED_NOT_AUTHORIZED, spend 0) · `ARCHIVE_MANIFEST.md` ·
`DOC-MAP.md` · `PLUGIN_CAPABILITY_MATRIX.md` · `PRIMARY_ACCOUNT_INBOX.md` · `tools/` (hq_status, agency_live,
stale_suites, big_agents, usage_by_session + tests). Old-system charters: `D:\ClaudeData\claude-api-lane\TRACKS.md`,
`WhyNotCut/LOCKED-AREAS.md`, `WhyNotCut/PROGRESS.md`.

**Conclusion:** a Master Orchestrator already exists and is in force (owner-approved 2026-10-19, charter adopted
2026-10-20, D-001). This setup restart must work **through** it, not beside it.

## 11. Automation — VERIFIED

| Mechanism | State at audit | Effect if left on |
|---|---|---|
| Claude routine `whynot-cut-hq-intake` (:37 hourly, Bypass) | **enabled** | reviews helper deliveries, writes verdicts, refills queues |
| Claude routine `whynot-cut-auto-resume-2` (:13/:43, Bypass) | **enabled** | **resumes the executor, Command Center and Builder A** after any stop |
| Claude routine `whynot-cut-primary-report-2` (09/13/17/21) | **enabled** | report + pushes 00-HQ to GitHub `ops/hq` |
| Claude one-time `whynot-cut-usage-remeasure-1000` (10-22 10:00) | **enabled** | one measurement run |
| 9 older Claude tasks (lane-watch, owner-update, 7 one-shot resumes) | disabled | none |
| Windows task "WhyNot Cut helpers keepalive" (30 min + logon) | Ready, last ok 03:37 | **restarts any helper loop with `AUTO-ON`** |
| Windows task "WhyNot Cut API lanes keepalive" (30 min) | Ready, last ok 03:30 | starts lane supervisors (lanes on HOLD) |
| Windows task "WNC-Queue" (heavy job queue) | Ready, last ok 03:50 | runs queued suites |
| Startup folder `WhyNot Cut API lanes.cmd` | present | starts lanes at logon |
| Helper `AUTO-ON` files (h1, h2) | present | loops keep taking BOARD cards |

**So a real stop needs all of these:** helper STOP shortcuts (or remove `AUTO-ON`), switch off the 3 routines + the
one-time task, and (optionally) disable the 3 Windows tasks — otherwise the watchdog and keepalive restart the work
within 30 minutes. This audit changed none of them (Phase 0 rule: no restarts, no stops without the owner).

## 12. Not inspected (and why)

- Contents of credential files, `.credentials.json`, Windows Credential Manager — security rule.
- Client folders (`_private-profiles`, `whynot-test` client data, real client footage) — owner rule.
- Transcripts of other sessions — not needed; only titles/state from the app's session list.
- Whether each running session is doing useful work vs. idle — needs their transcripts; out of Phase 0 scope.
- Test results today — not re-run (suites already running; read-only phase).
- GitHub settings (branch protection, Actions results), Anthropic Console — not checked.
- The Mac and its Claude seat — not reachable from this PC.
