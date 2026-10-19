# DECISIONS — operations and project-management decisions (ADR-lite)

Product and engineering decisions stay where they already live: owner decisions in `WhyNotCut/PROGRESS.md`, the V1
spec and the master roadmap. This file holds only decisions about how the project is run. Newest last. Statuses:
ACCEPTED · SUPERSEDED · PROPOSED.

## D-001 · 2026-10-20 · The master charter is adopted on top of 00-HQ, not beside it
- **Context:** Yunus gave `Master_Prompt_Latest.md` (permanent charter). 00-HQ (owner-approved 2026-10-19) already has
  a board, cards, inbox, hourly intake, helper AUTO loops, peer review and a budget file.
- **Options:** (a) build the charter's file set as a second system; (b) extend 00-HQ with only what the charter adds.
- **Chosen:** (b). New files: `PROJECT_PLAN_AR.md` (owner dashboard), `PRIMARY_ACCOUNT_INBOX.md`, `TASK_QUEUE.yaml`
  (generated), `AUTOMATION_RUNBOOK.md`, `PLUGIN_CAPABILITY_MATRIX.md`, `ARCHIVE_MANIFEST.md`, this file,
  `reports/`, `tasks/archive/`. Mapping of charter names: AGENT_COORDINATION = `PLAYBOOK.md`; TASK_BACKLOG =
  `BOARD.md`; PROJECT_STATE = `STATUS.md` + `PROJECT_PLAN_AR.md` §1; PRODUCT_ROADMAP / ARCHITECTURE = the repo roadmap
  and spec; CHANGELOG / RELEASES = repo `CHANGELOG` + `PROJECT_PLAN_AR.md` §5; TEST_REPORT = PROGRESS + reviews;
  API_BUDGET = `BUDGET-API.md`.
- **Trade-off:** charter file names are not all literal; one canonical place per subject instead.

## D-002 · 2026-10-20 · Account mapping
- PRIMARY = Yunus's Claude account (info@thewhynot.ai, Claude desktop app). The charter says "ChatGPT"; no ChatGPT
  account is connected to this project or reachable from here (ACCESS_UNAVAILABLE). If Yunus wants a ChatGPT lane, it
  needs its own connector or exported transcripts.
- ASSISTANT_A = H1 (mayar@thewhynot.ai, engine builder). ASSISTANT_B = H2 (marketing@thewhynot.ai, product builder,
  peer reviewer of H1). Both are Team seats on this PC (CLAUDE_CONFIG_DIR profiles + own worktrees).
- This chat is the **Command Center** (master role, charter §1). The older plan session (local_263cabbf) keeps its
  Gate 4 coordination charter until the v3.0.0-p4 tag, then ENDs; its owner-update task is replaced by D-005.

## D-003 · 2026-10-20 · Remote backup without touching release/3.0
- `release/3.0` had 50 unpushed commits; its push belongs to the executor (after a full suite on HEAD). A copy of its
  HEAD was pushed as `ops/backup-release-3.0-20261020` (4c1e59c, remote SHA verified). No CI runs for it (macOS CI
  triggers only on release/3.0 and mac/dev; the security watch skips owner pushes).
- Local baseline: `D:\ClaudeData\backups\2026-10-20-baseline\` (69 planning files with SHA256SUMS, a verified git
  bundle of release/3.0, the patch of 68 uncommitted tracked changes and the 62 untracked files).

## D-004 · 2026-10-20 · 00-HQ is mirrored to GitHub on branch `ops/hq`
- 00-HQ stays outside the repo until the Gate 4 tag (helper loops and the intake read its current paths). Each report
  run copies 00-HQ + `PROJECT_PLAN_AR.md` + `CLAUDE.md` into the worktree `D:\WNC-work\ops` (orphan branch `ops/hq`),
  commits when something changed, pushes, and verifies the remote SHA. The live files stay the canonical copy; the
  branch is their versioned history and off-PC backup.

## D-005 · 2026-10-20 · Reports: one deterministic generator, one scheduled delivery
- `00-HQ/tools/hq_status.py` builds the status from files and git (no AI tokens): `TASK_QUEUE.yaml`, the dated report,
  the inbox entry and the auto block of `PROJECT_PLAN_AR.md`.
- Delivery to PRIMARY = the scheduled task "whynot-cut-primary-report" (09:00, 13:00, 17:00, 21:00 Cairo) in Yunus's
  Claude app. Each run is a session in his app (observable), so the message state is SENT after a run; ACKNOWLEDGED only
  when Yunus answers. The 09:00 and 21:00 runs are also the twice-daily full refresh. The old "owner-update" task
  (twice a day via the plan session) stays disabled as a duplicate.

## D-006 · 2026-10-20 · Paid API: prepared, held, never calendar-activated
- See `BUDGET-API.md`. Plan B (450 USD from 1 Nov) is superseded. Lanes 1 and 5 now hold an owner HOLD STOP that the
  monthly guard cannot release.

## D-007 · 2026-10-20 · Resource targets
- Charter target: RAM up to 90 %, CPU/GPU up to 100 %. Owner rule: no NEW heavy job at ≥ 85 % RAM. Both hold: 85 % is
  the start gate, so running jobs peak below about 90 % (measured peak 94 % on 10-18 with 3 heavy jobs; the queue now
  allows 2). Every heavy job goes through `heavy.sh`; no change to the queue.

## D-008 · 2026-10-20 · Karpathy guidelines: one text, plugin kept optional
- The project `CLAUDE.md` text is identical to the plugin's `SKILL.md` (andrej-karpathy-skills 1.0.0, sha 2c606141,
  installed user-scope 2026-10-19). Helpers get the same text in their profile `CLAUDE.md`, without the plugin, so it
  never loads twice there. On Yunus's account the skill loads only when invoked; no duplicate is added anywhere.

## D-009 · 2026-10-20 · ENV-01: engine runtime for unsandboxed processes
- Root cause of the helpers' 563 suite errors: the 47 engine packages live only in the Claude sandbox's virtual
  AppData user-site; the real user-site is empty, so helper loops (unsandboxed) lack numpy/PIL/av/imageio-ffmpeg.
- Fix: install the same 47 pinned versions (frozen from the sandbox view) into the real user-site, PyPI only, from the
  Terminal (`D:\ClaudeData\accounts\env-fix\`). The sandboxed sessions keep their own copy, so the executor's runtime
  does not change.
