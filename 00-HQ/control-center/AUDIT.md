# Control Center audit (2026-10-22, before any change)

## DONE 2026-10-22 04:50 (resumed after the restart on Yunus's «كمل»)

- Review round 2 (fresh Opus): **PASS-WITH-MINORS**. All 12 round-1 fixes were confirmed and no new P1 was found. The
  minors are fixed with tests:
  - a failed delivery mark puts the message back;
  - a slow page keeps the newest snapshot;
  - no `/chat` while AUTO-ON exists;
  - backup folders never collide;
  - undo finds the rules by their shape.
- After the restart I also fixed: a helper between runs now shows its last run (model, session, words); the page
  has no sideways scroll even at 264 px with every panel open.
- Tests: **102** (control center) + **35/35** (`test_helper_loop.py`, which no longer deletes a real RELOAD flag).
- Live on real data after the restart:
  - the server answers `/whoami`; the key is kept across restarts;
  - Main is WORKING, with ≈ estimated context;
  - h1 and h2 show "Waiting on another task", which is the truth: both loops were restarted at 04:40 (AUTO-ON
    written by Start-Helper, not by this build) and are yielding to Gate 4 job `bl14r9-full`.
- Known limits: README §10 (the Bash-deny bypass and RELOAD only after a run are new).
- Still only the owner can check these, from outside Claude:
  - the desktop shortcut opens the 3 tabs;
  - the Main tab chat works;
  - `/chat` and `/continue` work.
- A BOARD card / DECISIONS entry is still the master's call (SETUP_AUDIT F2). The restart's Phase 6 should reuse
  this tool.

## CHECKPOINT 2026-10-22 04:25 (builder session "Multi-account Claude control center")

Paused here for the owner's AI-infra restart (D1, see `00-HQ/setup/SETUP_PHASE_TRACKER.md`). Nothing of D1 was
touched or re-enabled: no AUTO-ON, no RELOAD flag, no routine. My test server is stopped.

- **Done and verified:** the collector, dashboard, three terminals, launcher and installer are built; **94 tests**
  pass (`tests\`), and `D:\ClaudeData\accounts\test_helper_loop.py` passes 35/35. Checked on real data:
  - the dashboard in a browser, desktop and phone widths;
  - a Helper 1 terminal in a real console;
  - message delivery through the hook in real Claude runs (PostToolUse, UserPromptSubmit, sub-agent calls skipped);
  - `install.py` applied: hooks, status line and the new deny rules in h1/h2 `settings.json`; desktop shortcut;
    Agency LIVE shortcut moved to `D:\ClaudeData\control-center\backups\`.
- **Review round 1 (fresh Opus): FAIL → all P1 and P2 findings fixed with tests:**
  - helpers can no longer write the control-center code or state (deny rules);
  - a failed build never refreshes the snapshot (freshness comes from `generated_at`);
  - stable alert keys (no notification or history spam);
  - the hook skips sub-agent calls and puts a message back when delivery fails;
  - "no log yet" ≠ Working;
  - a broken hook cannot cause run after run;
  - Main's window is marked "≈ estimated";
  - desktop-app detection by image path;
  - Main's status rolls up only recent sessions;
  - the terminal lock is atomic.
- **Open (next session):**
  1. Review round 2 (LIGHT tier allows one more).
  2. P3s from round 1: the peer step shows "skipped" when there was no peer review; record heavy-queue command
     errors; `hmac.compare_digest` for the key; `running_url` should check the server's identity.
  3. Owner-side checks that cannot run from inside Claude: the shortcut opening the three tabs; the Main tab's
     interactive chat; `/chat` and `/continue` (`Start-Helper.cmd --talk`).
  4. A BOARD card / DECISIONS entry for the control center (SETUP_AUDIT F2), to be decided by the master.

### Paused 2026-10-22 04:30 (D1 stop order, received from the AI-infra restart session)
No server, background job or test is running from this session. Nothing re-enabled.

Files touched outside this folder:
- `D:\ClaudeData\accounts\helper_loop.py` (`owner_message_waiting`, `note_owner_wake`; backup `.bak-cc01`)
- `test_helper_loop.py` (backup `.bak-cc01`)
- `Start-Helper.cmd` (`--talk`; backup `.bak-cc01`)
- `h1\settings.json` and `h2\settings.json`: hooks, status line and deny rules (backups in
  `D:\ClaudeData\control-center\backups\`)
- Desktop shortcuts: added "WhyNot - Control Center"; moved "WhyNot - Agency LIVE" to the backups folder
- `00-HQ\README.md` and `AUTOMATION_RUNBOOK.md` §3: one pointer each
- Memory: `control-center.md`

**Resume condition (Yunus, 2026-10-22 ~05:05):** wait until the restart's Phase 2 says go
(`00-HQ/setup/SETUP_PHASE_TRACKER.md`). Checked at 05:05: Phases 0–1 DONE, Phase 2 (gstack) READY, not started.
Note: the tracker's Phase 6 (three-account orchestration) overlaps this build, so it should reuse this tool rather
than start a second one.

Runtime state: `D:\ClaudeData\control-center\`. Undo everything: `python -X utf8 app\install.py --undo`, then restore
the three `.bak-cc01` files.

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
