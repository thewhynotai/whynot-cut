# WhyNot Control Center

One place to see and talk to the three Claude accounts on this PC. Open it with the desktop shortcut
**WhyNot - Control Center**. That gives you:

- the **dashboard** as its own app window (Edge app mode with its own profile in `D:\ClaudeData\control-center\app-window`,
  so it never mixes with your browsing; `http://127.0.0.1:8765`, this PC only), in **English or Arabic** (button top right),
  styled like thewhynot.ai;
- one **Windows Terminal** window ("WhyNotCC") with exactly three tabs: **Main**, **Helper 1**, **Helper 2**.

Running the shortcut again opens nothing twice. It starts only what is missing. The older shortcuts (Helper 1/2,
AUTO, STOP, Agency LIVE) are in the desktop folder **WhyNot - Old tools**, and they still work.

## 0. Buttons (they never stop running work)

| Where | Button | What it does |
|---|---|---|
| Helper card | **What are you doing?** | Sends the helper a short question. It answers in its feed at its next step. Uses that helper's tokens only when you click. |
| Helper card | **Compact** (highlighted when its context passes 70%) | Asks it to finish its step, commit, write a PARTIAL report and end the run, so the next run starts fresh. A running headless session cannot take `/compact`, so this is the safe equivalent. Nothing is lost or stopped. |
| Helper card | **Start AUTO** (only shown when its loop is NOT running) | Runs `Start-Helper.cmd hN --auto`, the same as its old AUTO shortcut. It asks first. |
| Helper card | **Open terminal** | Opens the missing terminal tabs (never a second one). |
| Main session row | **Compact** | Copies `/compact` and shows 3 steps: open that session in the Claude app, paste, Enter. Nothing is sent automatically. |

Every button needs the page key, a local origin and a per-run anti-forgery token. The same button for the same
account is refused for 30 s, and every click is written to History.

## 0b. New things show up by themselves
- **New tasks** on BOARD.md appear at once, with a **New** badge for 48 h (`new_badge_hours`).
- **Projects & trackers:** every markdown tracker listed in `config.json` → `trackers` becomes a panel (its first
  table). Today that's the AI-infra restart phases (`00-HQ/setup/SETUP_PHASE_TRACKER.md`). For a new tracker, add one
  line there; no code changes.
- **How it works** (on the page) shows the road every task takes, who does what, and what each status word means.

The audit that led to this design is in `AUDIT.md`.

## 1. Architecture

```
 00-HQ (BOARD, cards, reports, reviews, intake) ─┐
 helper status.json + run-*.jsonl logs ──────────┤                   ┌─► dashboard (browser, live push)
 desktop-app sessions + transcripts ─────────────┼─► app/collect.py ─► app/server.py ─┤
 plan-usage-history, heavy.sh status, git, procs ┘   (snapshot)         │            └─► <state>\snapshot.json ─► terminals + status line
                                                                        └─► <state>\history.jsonl (state changes only)
 Helper tab: type a message ─► <state>\mailbox\hN\pending ─► hook in hN's profile ─► the running helper session
```

- **Source of truth stays where it was.** BOARD.md and the cards own the tasks. `helper_loop.py` owns the helper runs.
  The desktop app owns the main sessions. The control center only reads them. The one exception is the mailbox:
  it writes a message there when you send one.
- **Zero LLM tokens for monitoring.** Every value comes from files, the process list, git and `heavy.sh status`.
  Only the messages you send and the chats you open use an account.

## 2. Folders

| Where | What |
|---|---|
| `00-HQ\control-center\app\` | `collect.py` (snapshot), `runlog.py` (log parsing, context), `status.py` (states), `tasks.py` (task lifecycle), `server.py` (dashboard server), `console.py` (terminals), `ownermsg.py` (mailbox + hook), `statusline.py`, `history.py`, `launch.py`, `install.py` |
| `00-HQ\control-center\web\` | The dashboard page (no external requests) |
| `00-HQ\control-center\tests\` | 116 tests: `python -X utf8 -m unittest discover -s tests` |
| `00-HQ\control-center\config.json` | Accounts, session names, routines, goal, thresholds, refresh times, port. **Edit names and thresholds here.** |
| `D:\ClaudeData\control-center\` (state) | `snapshot.json`, `history.jsonl`, `mailbox\`, `consoles\*.lock`, `model_windows.json`, `server.json` (port + page key), `server.log`, `backups\` |

Helpers cannot write either folder: `install.py` adds Edit/Write deny rules for both, plus `Bash(*control-center*)`,
to their profiles. Without them, a helper could post a message "from Yunus" to the other helper, or change code that
runs as another account's hook. The state folder also stays out of git when 00-HQ moves into the repo.

## 3. Start, stop, recover

- **Start:** double-click **WhyNot - Control Center**.
- **Close the terminals:** close the Windows Terminal window. Nothing else stops: the helpers keep working, and so do
  the routines and the desktop app.
- **Stop the dashboard server:** end the `pythonw.exe` whose PID is in `D:\ClaudeData\control-center\server.json`.
  The shortcut starts it again.
- **After a Windows restart:** double-click the shortcut. The helper loops come back by themselves (keepalive), as before.
- **Undo the whole install:** `python -X utf8 app\install.py --undo`. It removes the hooks and the status line from
  the helper profiles and restores the Agency LIVE shortcut. A backup is taken first; every earlier backup is in
  `state\backups\<time>\`.

## 4. The three terminals

**Main (blue tab).** It shows the main account's state, then opens a real **Claude Code chat on info@** in the Editing Plugin
folder. The status line at the bottom shows the account, model, this chat's context and the helpers' state. It is a
separate conversation from the desktop app sessions, which keep coordinating exactly as before. After `/exit`:
Enter = new chat, `c` = continue the last one, `q` = close the tab.

**Helper 1 (green) / Helper 2 (purple).**
- **Header (updates in place):** account and sign-in check, status and why, model and effort, session and run, the
  task with its title and verified steps, what it is doing now, context, plan usage and waiting messages.
- **Feed:** only new events of the run, never repeated. The helper's words are white, its actions gray, errors red.
- **Typing:**

| You type | What happens |
|---|---|
| any text + Enter | A message to this helper. It reaches the running session at its next step, usually within a minute. An idle helper wakes up for it. The feed confirms delivery ("✓ delivered to session …"), and the helper answers in its next words. |
| `/task` | The current task with every lifecycle step and its evidence |
| `/status` | Status, reason, sign-in, loop, file paths |
| `/msgs` | Your recent messages and when each was delivered |
| `/chat` | A full chat on this seat. Only when AUTO is off: two Claude sessions must not share one worktree. |
| `/continue` | Reopen the newest conversation in its worktree (usually its last AUTO run) |
| `/start` | Turn AUTO on |
| `/stop` | Turn AUTO off. It asks first, because it ends the current run within about a minute. |
| `/log` | Where the full logs are |
| `/clear` | Clear the feed |
| `/quit` | Close the tab |

## 5. Reading the dashboard

- **Top line:** live dot, last sync time, RAM and test queue, the release goal. A red **stale** banner appears if no
  update arrived for 35 minutes.
- **Needs attention:** red = error, stalled, disconnected or wrong account; amber = waiting for you, context nearly
  full, a blocked task, high RAM, a failed routine, an open request. "Nothing needs you right now" when all is well.
  **Enable alerts** turns on desktop notifications for new items.
- **Account cards:** status and its reason, connection (Main: app running and signed in as info@; helpers: signed in
  as their own seat, AUTO loop running), model and effort, session, start time and duration, last activity, the
  **context bar**, the current task with its steps, "Doing now" and "Last said", a short activity feed (helpers) or the
  list of active sessions (Main). **Plan usage** sits on its own line and is never mixed with context.
- **Tasks:** search by ID, title, account, project or status; filter by account and group. Click a row to see its
  objective, owner, current step, start, last activity, dependencies, blocker, result, verification, branch, test jobs
  and every lifecycle step with its evidence.
- **Sub-agents**, **Routines**, **History** (every real state change, searchable) and **How this screen knows**.

### Status words

| Status | Meaning (evidence) |
|---|---|
| Working | Its run log or transcript was written in the last 3 min |
| Running tests / Waiting in the test queue | Its job label (`h1-…`, `peer-…`) is in `heavy.sh status` |
| Waiting on a long command | A tool has been running at least 15 min (heartbeats) |
| Quiet | Alive, nothing written for 20–60 min |
| Stalled | Alive, nothing written for 60 min or more. Check before acting; the loop itself kills a run only after 5 h 10 min. |
| Waiting on another task | The loop yields to Gate 4 jobs (`YIELD.txt`) |
| Waiting: usage limit | A limit was hit; resumes at the time shown |
| Waiting for you | Its newest report is BLOCKED, or a desktop session asked you something |
| Idle | No card left for it |
| Stopped | AUTO is off |
| Disconnected | AUTO is on but the loop is not running (the keepalive restarts it within 30 min), or the desktop app is closed |
| Error | The loop switched itself off after 3 quick failures, the last run failed and is backing off, or a session error |

The dashboard never stops, kills or restarts anything.

## 6. How tasks are tracked

Each BOARD id is joined with its card (title, goal, tier, stage, depends-on, FIX rounds), the helpers' reports in
`inbox\hN`, the peer reviews in `reviews\`, the intake verdicts in `intake\state.json`, the git branch `hN/<ID>` and
its heavy-queue jobs. Progress counts six verified steps: card ready → work started → delivered → peer review →
master's decision → merged. Each step shows its evidence. A FIX round reopens "delivered" until a newer report
arrives. The task a helper is on comes from its run (branch and queue labels in its commands, or the peer review the
loop started).

## 7. How context and model are measured

- **Model:** the model named in the newest reply of the session or run (`message.model`), else the run's start line.
- **Context in use:** `input + cache_read + cache_creation` tokens of the newest main-thread reply. Sub-agent lines
  are excluded. It is "as of" that reply, and the time is shown.
- **Window size:** only what Claude Code itself reported (`modelUsage.<model>.contextWindow` in a finished run),
  remembered per model in `model_windows.json` with where and when it was seen. Until one is seen, the card says
  "window unknown" and shows no percentage. The desktop app never reports a window, so Main's sessions use the window
  reported for the same model by a helper run. It is marked **≈ (estimated)** everywhere it appears.
- **Plan usage:** helpers from `rate_limit_event` in their logs (5-hour window); Main from the app's
  `plan-usage-history.json`. Shown separately.

## 8. Synchronisation

- Every 5 s the server only **stats** the files it reads (BOARD, cards, inbox, reviews, intake, helper status and
  logs, mailbox, the desktop session files). A change triggers a rebuild.
- Every 60 s it also refreshes the slow sources: heavy queue, git, loop liveness, sub-agents, process list.
- At least every 30 minutes it does a full rebuild (`config.json` → `refresh`).
- Pages get a push only when the snapshot really changed, plus a heartbeat every 20 s that updates "last sync".
- Transitions (status, task, new run, a new red alert) are appended once to `history.jsonl`.

## 9. Troubleshooting

| You see | Do |
|---|---|
| Browser says "Open the dashboard from the … shortcut" | Use the shortcut: it carries the page key |
| Red "stale" banner, or "monitor offline" in a terminal | Double-click the shortcut (it starts the server); then read `D:\ClaudeData\control-center\server.log` |
| Helper "Disconnected" | Wait for the keepalive (30 min), or type `/start` in its tab |
| Helper "Error: switched itself off" | Read `D:\ClaudeData\accounts\hN\auto\auto.log`, fix the cause, then `/start` |
| "Account check failed" | That profile is signed in to the wrong seat: open its tab, `/stop`, `/chat`, `/logout`, `/login` with its own e-mail |
| A message stays "waiting" | AUTO is off (`/start`) or the loop is waiting on a limit. It is read at the next run. |
| A terminal tab says "already open" | That account's tab is open in the WhyNotCC window; use that one |
| Main tab: claude.exe not found | The Claude desktop app is missing or updating; press Enter to retry |

## 10. Known limits

- A running headless helper cannot be typed into directly. Messages arrive through the hook at its next step. A long
  single command (a 1-hour suite) delays delivery until it ends.
- The Main terminal is its own conversation. Desktop app sessions are not resumed in the terminal, because two
  programs writing one transcript is unsafe.
- Context is measured at the newest reply. During a long tool call the value is from before it.
- A main-account sub-agent's context is shown only when `agency_live.scan_agents` reports it.
- When 00-HQ moves into the repo (OPS-04), the hook and status-line paths in the helper profiles move too: run
  `app\install.py` again from the new place.
- **The Bash deny rule can be bypassed.** A helper could chain commands that are each allowed, such as
  `cd /d/ClaudeData && cp x cont*/mailbox/h2/pending/y.json`, without ever typing "control-center", and so forge an
  "owner" message to the other helper. The Edit/Write denies hold; this shell route stays open. Accepted for an
  internal tool (light tier, owner decision 2026-10-19). The paid edition would sign messages.
- A `RELOAD-hN` flag is read only when a run ends. A loop that is idle or yielding picks up new `helper_loop.py`
  code after its next run. To apply it at once, stop the loop and start it again.
- The page key is stored in `server.json` (local, this PC). Anyone signed in to this Windows account can read it,
  which is the same trust level as the Claude logins themselves.
