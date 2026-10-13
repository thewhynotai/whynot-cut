# WhyNot Cut hooks (reference)

`hooks.json` wires these; every Python hook starts through `run_python.sh` (the engine runtime, else a cached or PATH
Python; no Python = fail open, said loudly at the next session start). Hooks never fail a session: an error is a silent
exit 0, except the guard, which blocks a guarded call it cannot check.

| Event | Script | What it does |
|---|---|---|
| PreToolUse `Bash\|PowerShell` | `guard.py` | Client sources read-only, Premiere-first, role limits (rules in the guard's docstring). Also hands Claude a waiting CwdChanged context (see below). |
| PreToolUse `Write\|Edit\|NotebookEdit` | `guard.py`, behind `if` | One handler per tool and path pattern (`session_context.FILE_IF_PATTERNS`): `assets/` and `data/` at any depth and any case, `*.whynot-*` (marker, writer lock), After Effects preferences. Any other write starts **no process** (measured: the guard costs ~260 ms per call on Windows). |
| PreToolUse `MultiEdit` | `guard.py` | Always (older CLIs; no `if`, so never unguarded). |
| SessionStart `startup\|resume\|clear\|compact\|fork` | `session_context.py` | The context for a client folder / the clients folder; panel approvals and change requests; pending updates; busy clients (writer leases); the first-run nudge once; writes `~/.whynot-cut/plugin-root.json`; starts the panel link (`serve --ensure`, detached). |
| CwdChanged | `session_context.py` | The same context for the new folder, once per place. CwdChanged output reaches Claude only as `systemMessage` (a note to the editor), so the context waits in `${CLAUDE_PLUGIN_DATA}/pending-context/<session>` and the guard adds it to Claude's next Bash/PowerShell call. |
| Stop | `stop_gate.sh` → `stop_gate.py` | Evidence gate, **off by default**. On with the preference `evidence_gate: on` (not with `approval: auto`): a turn that ran `reel` commands and says ready/done without `reel qc`/`reel verify` is sent back once. Off: one bash start per turn end, builtins only. |
| SessionEnd | `session_end.py` | Releases the ending session's own writer lease; removes its files in `${CLAUDE_PLUGIN_DATA}`. |

## `if` filter rules (checked live, CLI 2.1.295, Windows)

- The rule's tool name must be the call's tool: `Edit(...)` never matches a `Write` call, so each tool has its own handlers.
- `//` = absolute path; a relative `**/data/**` matches only below the session's working folder (a write to a client
  elsewhere would skip the guard), hence `//**/…`.
- Matching is case-insensitive on Windows; the patterns spell `[Aa]` classes so macOS matches any case too.
- `X/**` also matches a file named `X`.
- Handlers with the same command run once per matching `if` (no merging before the filter).
- Known gap (as before for a mistake guard, not a sandbox): a path that reaches a client source only through a symlink
  or junction is not matched by the filter; the guard's own Bash/PowerShell checks are unchanged.

## Per-session files (`${CLAUDE_PLUGIN_DATA}`)

`scope/<session>` (where the session was last told it is), `pending-context/<session>`, `evidence-gate/<session>`,
`first-run-done`, `last-session-start`, `guard-ok`, `hooks-ok`, `python`. SessionEnd removes the per-session ones.

## TODO

- TODO (T6.2b): add the plugin monitor `monitors/monitors.json` running `reel watch --panel` (`when: "always"`) once
  `reel watch` exists, so panel approvals reach a running session live. Not before: the command does not exist yet.
