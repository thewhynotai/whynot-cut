# Control Center audit (2026-10-22, before any change)

Scope: the three-account setup on this PC. Main = info@ (Yunus, Claude desktop app), Helper 1 = mayar@ (profile `D:\ClaudeData\accounts\h1`), Helper 2 = marketing@ (profile `...\h2`).

## 1. What exists and what it does

| Component | Where | Purpose | Verdict |
|---|---|---|---|
| BOARD + task cards + inbox reports + intake verdicts + reviews | `00-HQ\BOARD.md`, `tasks\`, `inbox\h1|h2\`, `intake\state.json`, `reviews\` | The single source of truth for tasks: who owns what, status, delivery, decision | **Keep.** It stays the source of truth. The control center only reads it |
| `TASK_QUEUE.yaml` | 00-HQ | Generated machine view of the above | Keep (other routines use it) |
| Helper AUTO loop | `D:\ClaudeData\accounts\helper_loop.py` (pythonw, hidden) | Runs one headless `claude -p` per card on the helper's own seat, sleeps through limits, writes `auto\status.json` + one `run-*.jsonl` stream log per run | **Keep.** It works (21 tests). Small extension: wake an idle loop when the owner sends a message |
| Helper launcher | `Start-Helper.cmd h1|h2 [--auto|--check]` + 6 desktop shortcuts | Opens the helper's profile in its worktree, checks it is the right account, refuses Yunus's login, refuses to run from inside Claude | **Keep.** Add a `--talk` mode (open a chat without the auto kickoff, or continue the last one) |
| Keepalive | Windows task "WhyNot Cut helpers keepalive" + `Helper-Keepalive.cmd` | Restarts a loop whose `AUTO-ON` exists | Keep, untouched |
| Agency LIVE | `00-HQ\tools\agency_live.py` (desktop shortcut) | Console screen, redraws every 5 s: sessions, helpers, agents, routines, tasks, needs-you | **Replace as the main view; reuse its parsing.** Its pure functions are imported by the new collector. Kept as a text fallback (`--once`) |
| helpers_live.py / helper_peek.py | `D:\ClaudeData\accounts` | Older helpers-only screen; raw step dump of one run | helpers_live: already superseded, left in place (not used by anything). helper_peek: kept |
| hq_status.py | `00-HQ\tools` | Status generator, Arabic reports, BOARD parser, RAM | Keep; its readers are reused |
| Routines (intake, report, watchdog) | Claude app scheduled tasks, prompts in `roles\` | Intake reviews, 4 reports a day, resumes stopped sessions | Keep, untouched. Shown on the dashboard |
| Heavy job queue | `heavy.sh` (`D:\ClaudeData\jobs`) | Shared test queue, 2 slots, RAM gate | Keep. Its jobs are linked to tasks by their label (`h1-BL-17`) |

## 2. Problems found (root causes)

1. **No terminal per account.** Helpers run headless with no window, so there is nothing to type into. Their only "screen" is the Agency LIVE console, which is read-only. The only way to talk to a helper is to stop its AUTO mode and open the other shortcut. The main account has no terminal; it lives in the desktop app.
2. **Unclear, noisy screen.** Agency LIVE redraws a whole console every 5 s and shows card IDs ("card S6b") without titles. It also mixes 3 main-account chats, 2 helpers and up to 12 agents in one table. Arabic is dropped because the console cannot shape it.
3. **Context window not shown anywhere.** The data exists: each assistant line carries `usage`, and the stream logs carry `modelUsage.contextWindow`. Nothing read it.
4. **Task identity is lost at the action level.** The helper's current command (a suite in the heavy queue, a peer review) is not linked to its task title, its lifecycle or its blockers.
5. **"Process alive" is treated as "working".** A run that is alive but silent is only "QUIET n min". There is no stalled threshold and no explanation.
6. **No history.** Status changes are not recorded, so nobody can see later who did what and when.
7. **Hard-coded lists** (`PEOPLE`, `ROUTINES`, `GOAL`) in the code went stale whenever sessions changed.

## 3. Facts the design relies on (verified on this PC)

- Context in use = `input_tokens + cache_read_input_tokens + cache_creation_input_tokens` of the newest assistant line. It is in both the desktop app transcripts (`~/.claude/projects/*/<id>.jsonl`) and the helper stream logs. Now: Command Center 488K, H1 run 251K.
- Context window size: the CLI reports `modelUsage.<model>.contextWindow` in every run's final `result` line (Opus 5.5 = 1,000,000; Haiku 5.5 = 1,000,000). This is learned from real runs, never assumed.
- Helper usage limits: the stream logs carry `rate_limit_event` (5-hour utilisation and reset). For the main account, the app writes `plan-usage-history.json`.
- **Owner messages can reach a helper's running headless session without stopping it.** A `PostToolUse` hook that returns `additionalContext` is read by the running session at its next tool call. Tested 2026-10-22 03:4x with a one-off Haiku run (USD 0.008): the session quoted the message back.

## 4. Limits (not fixable from outside)

- A headless `claude -p` run cannot be typed into directly. The terminal sends messages through the hook (delivered at the next tool call). It offers a full chat only when AUTO mode is off, because two Claude processes must not work in one worktree.
- The main account's work runs in the desktop app. Its main terminal is a real Claude Code CLI on the same login, a separate conversation. Resuming a desktop session in the CLI while the app has it open would let two processes write the same transcript, so it is not offered.
- A context window measurement is as fresh as the session's last model reply. A session that is thinking or running a long tool shows the value from its last reply, with its time.

## 5. Target architecture

```
          read-only, zero LLM calls                                   one localhost page
 BOARD / tasks / inbox / intake / reviews ─┐
 helper status.json + run-*.jsonl ─────────┤   app/collect.py   ──►  app/server.py  ──SSE──►  web/ (dashboard)
 desktop sessions + transcripts ───────────┤   (snapshot JSON)        stat-watch 5 s, full rebuild ≤ 30 min,
 plan-usage-history.json, heavy.sh, git ───┘        │                 history.jsonl on transitions
                                                    ▼
 Terminal 1 MAIN  = app/console.py main → interactive Claude Code (info@)           + status line
 Terminal 2 H1    = app/console.py h1   → live run feed + message box → mailbox ─hook─► running helper
 Terminal 3 H2    = app/console.py h2   → same                          (or a full chat when AUTO is off)
```

- Code, config, docs and tests: `00-HQ\control-center\`. Runtime state (mailbox, history, token, caches, logs): `D:\ClaudeData\control-center\`. That folder lies outside every helper's writable folders, so a helper cannot write messages "from Yunus" to itself or to the other helper. It also stays out of git when 00-HQ moves into the repo.
- No new orchestration. BOARD and the loops keep ownership of tasks. The control center reads them. It writes only the mailbox, at Yunus's request, and its own state.
- Python standard library only (Python 3.13 is already installed). Windows Terminal is already installed, so no new dependencies.
