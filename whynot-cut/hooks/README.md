# WhyNot Cut hooks (reference)

`hooks.json` wires these; every Python hook starts through `run_python.sh` (the engine runtime, else a cached or PATH
Python; no Python = fail open, said loudly at the next session start). Hooks never fail a session: an error is a silent
exit 0, except the guard, which blocks a guarded call it cannot check.

| Event | Script | What it does |
|---|---|---|
| PreToolUse `Bash\|PowerShell` | `guard.py` | Client sources read-only, Premiere-first, role limits (rules in the guard's docstring). Also hands Claude a waiting CwdChanged context (see below). |
| PreToolUse `Write\|Edit\|NotebookEdit` | `guard.py`, behind `if` | One handler per tool and path pattern (`session_context.FILE_IF_PATTERNS`): `assets/` and `data/` at any depth and any case, `*.whynot-*` (marker, writer lock), After Effects preferences, the lead-step tokens (`run/lead-tokens`, also by its 8.3 short name) and Claude Code's session transcripts (`projects/**/*.jsonl`, BL-15). Any other write starts **no process** (measured: the guard costs ~260 ms per call on Windows). |
| PreToolUse `MultiEdit` | `guard.py` | Always (older CLIs; no `if`, so never unguarded). |
| SessionStart `startup\|resume\|clear\|compact\|fork` | `session_context.py` | The context for a client folder / the clients folder; panel approvals and change requests; pending updates; busy clients (writer leases; the clients folder's busy and panel lists share one ~1 s budget, then say "(scan cut short …)"); after `/clear` or `/resume`, re-keys the lease its own Claude Code process still holds (`writer_lock.rekey`: the only takeover of a live lease); the first-run nudge once; writes `~/.whynot-cut/plugin-root.json`; starts the panel link (`serve --ensure`, detached). |
| PostToolUse `Read`, behind `if` (`Read(//**/[Oo][Uu][Tt][Pp][Uu][Tt]/**)`) | `read_once.py` | The read-once reminder (BL-01, M5-T6): a second FULL read (no `offset`, `limit` or `pages`) of the same unchanged file of 20 KB or more by the same session and agent adds one line of context (use what you read, or a ranged read / grep / `reel brief`). Never blocks. State: one file per session and agent under `<engine home>/run/read-once/`, updated under a short lock file (written through `lib/linksafe`, never through a link; files older than 2 days are swept; no lock within 3 s means no reminder). A read outside a client's `output/` starts no process. A missing engine home means silence. |
| SessionStart `compact` | `read_once.py` | Clears the lead's read-once records (the lead's compaction drops what it had read). Subagents' records are untouched. |
| SessionEnd | `read_once.py` | Removes every read-once state file of the ending session. |
| CwdChanged | `session_context.py` | The same context for the new folder, once per place. CwdChanged output reaches Claude only as `systemMessage` (a note to the editor), so the context waits in `${CLAUDE_PLUGIN_DATA}/pending-context/<session>` and the guard adds it to Claude's next Bash/PowerShell call. Leaving for an unrelated folder drops a context still waiting; the evidence-gate flag follows the new folder. |
| Stop | `stop_gate.sh` → `stop_gate.py` | Evidence gate, **off by default**. On with the preference `evidence_gate: true` (not with `approval: auto`): a turn that ran `reel` commands and says ready/done without `reel qc`/`reel verify` is sent back once. Off: one bash start per turn end, builtins only. |
| SessionEnd | `session_end.py` | Releases the ending session's own writer lease; removes its files in `${CLAUDE_PLUGIN_DATA}`. |
| (settings.json) `subagentStatusLine` | `subagent_status.py` | Not a hook: the plugin's `settings.json` names it as the subagent status line. One row per `whynot-cut:*` subagent in the agent panel: `agent \| stage \| clip \| state \| time`. Claude Code reads only `agent` and `subagentStatusLine` from a plugin `settings.json` and does not expand `${CLAUDE_PLUGIN_ROOT}` there, so the command reads the root from `~/.whynot-cut/plugin-root.json` when the variable is empty. Stdlib only; any error prints nothing. **Labels stay plain ASCII English with `language: ar` too (decision, G3 review M4):** a terminal row has no right-to-left support, so Arabic labels between the Latin agent name, the clip id and the time would show reversed or with broken letter joins in Windows Terminal and macOS Terminal; the editor gets the Arabic words in the chat and the board (`reel board`). |

## `if` filter rules (checked live, CLI 2.1.295, Windows)

- The rule's tool name must be the call's tool: `Edit(...)` never matches a `Write` call, so each tool has its own handlers.
- `//` = absolute path; a relative `**/data/**` matches only below the session's working folder (a write to a client
  elsewhere would skip the guard), hence `//**/…`.
- Matching is case-insensitive on Windows; the patterns spell `[Aa]` classes so macOS matches any case too.
- `X/**` also matches a file named `X`.
- Handlers with the same command run once per matching `if` (no merging before the filter).
- Other drives and UNC (fix round 1, probed live with sessions on D: and on C:, see
  `docs/superpowers/evidence/2026-10-13-t3.4-if-filter-probes.md`): the `//**/…` patterns match a write to a client on
  another drive, on `\host\share\…`, through a subst drive or junction naming the client folder, through an 8.3
  alias, and with forward slashes (Claude Code turns `/` into `\` before matching). No `*`-prefixed pattern is needed:
  those match the raw path case-sensitively, and `*\assets\*` / `*/assets/*` matched nothing.
- Known misses (a mistake guard, not a sandbox): a write through a junction, symlink or subst drive that points
  **straight at** `assets/` or `data/` (or inside them), e.g. `V:\x.txt` after `subst V: <client>\data`, names no
  source folder, so the filter skips the guard (before T3.4 the guard resolved such aliases itself). An alias of the
  client folder or a folder above it is matched. The guard's Bash/PowerShell checks are unchanged.

## Per-session files (`${CLAUDE_PLUGIN_DATA}`)

`scope/<session>` (where the session was last told it is), `pending-context/<session>`, `evidence-gate/<session>`,
`first-run-done`, `last-session-start`, `guard-ok`, `hooks-ok`, `python`. SessionEnd removes the per-session ones.

## TODO

- TODO (T6.2b): add the plugin monitor `monitors/monitors.json` running `reel watch --panel` (`when: "always"`) once
  `reel watch` exists, so panel approvals reach a running session live. Not before: the command does not exist yet.
