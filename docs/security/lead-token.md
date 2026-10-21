# Lead-only steps: the approval token (BL-15, Addendum L L-G13)

Some engine steps belong to the lead editor only. The main conversation runs them after the editor says so. Today they
are:
- `approve-plan` and `auto-approve`;
- `reels-select`;
- `lock --release`;
- `settings --init`;
- `handoff --delivered`;
- `verify --record` and `ae-probe --record`;
- `ref-style --adopt … --yes`;
- `caption-looks --pick … --yes`;
- `rules --add`, `rules --remove`, `rules --record` and `rules --dismiss`;
- `clean --apply` (the engine-home clean-up, which removes files);
- `cut-proposals --accept` (the editor's chosen cuts go into the plan's cut list);
- `takes --drop`, `takes --keep` and `takes --undo` (which takes stay);
- `transcript-verify` as the editor.

The table of these steps lives in `whynot-cut/engine/reel/lib/lead_steps.py` (`LEAD_STEPS`). `hooks/guard.py` keeps a
copy of it, so that every guarded call does not pay the module's import. A test pins the two as equal.

## Two walls
1. **The guard** (`hooks/guard.py`, PreToolUse) refuses these steps for every subagent, by its engine rules and by its
   text backstop. It reads shell text, so a deliberately unusual spelling can get past it.
2. **The engine** runs these steps only with an approval token for exactly that call. The guard writes the token,
   `<engine home>/run/lead-tokens/<key>.<nonce>.tok`, when ALL of these are true:
   - the guard allowed the call;
   - the call is a lead-only step;
   - it is a **plain** call (below);
   - the hook input names no subagent (`agent_type`) and no teammate (`agent_id`);
   - the session's own main transcript holds this exact tool call, by its `tool_use_id`, with the same tool and command,
     and not as a sidechain. Claude Code writes the transcript asynchronously, so the guard waits up to 2 s for the
     call to land.

   A token lasts 120 s, names the Claude Code session, and is used once. One tool call gets at most one token.

   `cli.main` consumes a matching token before the step runs. Without one, it refuses with exit 2 and a `blocked`
   text that starts «الخطوة دي للمحرر بس…». A token that has expired gets its own text: «… خلص وقتها … run the same
   command again», which typically happens when the permission prompt took longer than 2 minutes.

The refusal also names its cause, in Arabic first, so a broken hook never blocks the editor silently. The causes are:
- the guard hook is missing from `hooks/hooks.json`;
- the guard hook is not running (no heartbeat);
- the guard did not see this call as one plain call from the main conversation;
- the last call it saw was not plain;
- the guard could not confirm the call in the transcript;
- the guard approved a different call;
- the approval was already used;
- the approval belongs to another Claude Code session;
- the approval expired.

Each refusal points to `reel doctor`. That command checks that the guard hook is registered and that a token round
trip works in the engine home. When either fails, it gives the editor one line to fix it.

## Why there is no terminal escape
The first design let the editor run these steps from their own terminal with `WHYNOT_LEAD_TTY=1`, honoured only with a
real TTY and no Claude Code variables. It was **removed on purpose** (executor, 2026-10-18), because Claude Code itself
could satisfy it in three ways:
1. Windows reports the NUL device as a TTY, so `env -i … WHYNOT_LEAD_TTY=1 python … < /dev/null` passed.
2. `Start-Process -UseNewEnvironment` gives a real console without Claude variables.
3. `script` on macOS gives a real pty.

A hole the agent can satisfy is worse than no escape. Nothing outside Claude runs a lead-only step: the installer, the
panel and the tools were checked. So the editor runs these steps through the lead (Claude). From Phase 6 the panel
runs them too: its daemon issues its own token with `lead_steps.issue_for(argv, env, cwd)`, marked
`"issuer": "panel"`. No environment variable opens the engine wall.

## What a plain call is
- One engine call: `reel …`, or `python …/engine/reel/cli.py …`.
- Literal words after it. Not allowed:
  - variables or `$( )`;
  - globs or `~`;
  - `cd … &&`, or anything else chained before or after it (`;`, `&&`, `||`);
  - redirects or environment prefixes.
- It may end with `2>&1` and one pipe into a read-only text tool (`| tail -5`, `| Select-Object -Last 5`).

## The key
The key binds the whole call:
- every argument, in Unicode NFC;
- `--opt=value` read as `--opt value`;
- Git Bash's `/d/…` and `name=/d/…` read as `D:/…` on Windows;
- the real path of `--root`, with links and junctions resolved and case folded on Windows;
- the real current folder when there is no `--root`.

## The token folder
- Nobody writes there by hand, the lead included.
- The guard judges every write target by its **real path**: a path whose resolved form lies in a `run/lead-tokens`
  folder is refused, also through a link, a junction, an 8.3 name or another case. This covers Write, Edit,
  NotebookEdit, MultiEdit, shell redirects and copies, and the PowerShell content writers.
- `hooks/hooks.json` routes Write/Edit/NotebookEdit to the guard for `lead-tokens` paths and their 8.3 form.
- A subagent's shell command that names the folder (also with the spelling stripped, or through a glob with 6 or more
  literal characters that matches its name) is refused.
- On POSIX the folder is 0700 and each token 0600. On Windows the folder inherits the engine home's ACL (L-G16; on a
  shared PC see HL7).

## Limits (read this)
- **Not a security boundary.** This is a guard against agent mistakes and prompt injection. It is not a wall against a
  process running as the same user. Such a process can:
  - write a token file through a path Claude Code does not route to the guard (for example, a link it made itself);
  - call `issue()`;
  - edit the transcript.
- **What counts as Claude Code's transcript:** the engine reads a transcript only at exactly
  `<claude config>/projects/<project folder>/<session id>.jsonl`, case folded on Windows and macOS. That is where
  Claude Code writes a session's main transcript. The file and its project folder must not be links (a symlink or a
  junction is refused, not followed). The same name anywhere else (deeper, or in a subagent's folder) is never read.
  `<claude config>` is taken from the hook process's own environment (`CLAUDE_CONFIG_DIR`, else the home folder), so
  whoever runs the hook by hand chooses it: see "What still mints a token" below.
- **What the guard judges in that store** (for the lead and subagents alike), and nothing more. This is a speed bump:
  many writers are not parsed (for example `tar -C"…"` or `--directory=`, `7z -o`, `robocopy`, `xcopy`, `mklink /J`,
  `fsutil hardlink`, `Copy-Item -Recurse` or `Expand-Archive` with a positional destination, `cd <store> && tar -xf`,
  and NTFS streams written with `Set-Content -Stream`). What it does judge:
  - the Write, Edit and NotebookEdit tools on a `projects/**/*.jsonl` path (`hooks/hooks.json` routes them to the
    guard), and MultiEdit (always routed): refused when the real target lies inside the store. A Write of another
    name there is not routed; the engine never reads it;
  - the write targets the guard parses from a shell command (redirects, `cp`/`mv`/`tee` and the other file writers,
    the PowerShell content writers): refused when the real target lies inside the store;
  - a writing or archive-extracting command (`tar`, `unzip`, `7z`, `Expand-Archive`…) run with the store as its
    working folder: refused.

  The one exception is Claude Code's own `<project>/memory/` folder, and only for files that are not `.jsonl`. A
  target the guard cannot parse (a path built inside code, or from a variable set by an earlier command) is not
  judged; see the next point.
- **What still mints a token (the real residual).** A forged transcript line becomes a token only when a hook run
  with a hand-made payload confirms it. A subagent's shell command that names the hook script (`guard.py`, in any
  spelling the guard reads) is refused. That check is a speed bump, not a wall: a path split into pieces or encoded
  (built inside code, or from variables) gets past it, and so does a glob with fewer than 6 literal characters
  (`hooks/g*.py`). The hand-run check is the ONLY barrier against a forged transcript, and it is only a speed bump.
  Known ways past it (review 1d218f8, accepted as known limits under the LIGHT tier, owner decision 2026-10-19):
  - a forged transcript written OUTSIDE the real store (the Write tool, anywhere), then one shell line that runs the
    hook by a short glob with `CLAUDE_CONFIG_DIR` pointing at the forged folder: no code needed;
  - on Windows, an NTFS stream on the memory folder (`<project>/memory:<sid>.jsonl`, written with
    `Set-Content -Stream`) is read as a depth-2 transcript;
  - code a subagent writes and then runs: it can write the transcript line and call `lead_steps.hook_issue` or the
    hook script itself, from a path the guard does not see (a name built inside the code);
  - a path built from a shell variable set in an earlier command (`d=…; echo x > "$d/…"`);
  - the lead (the main conversation) running the hook by hand. The lead is the party the token stands for.

  In one sentence: a subagent that sets out to mint a token can do it: this is a guard against agent mistakes and
  prompt injection, not a boundary against a determined agent or code running as the same user. Hardening against
  Claude bypassing its own lead-only steps waits for the paid edition (owner decision 2026-10-19). What stays
  mandatory is unchanged by this: the guard keeps a client's source folder read-only for every writer, and
  `clean --apply` (which removes files) is a lead step, run after the editor's yes.
- **Out of scope here:** code that imports the engine's library functions directly (not `cli.main`). That is the engine
  write gate's job (L-T8).
- **Cost:** an ordinary guarded call does not load the token module. The lead's call of a lead-only step loads it,
  together with the engine-home rules (`plat`). On this PC under load that costs about 15–30 ms, and the token work
  itself is under 20 ms (p95). Lead-only steps run a few times per video.
- **One engine home.** The hook and the engine must use the same engine home (`WHYNOT_HOME`, else the default). An
  engine started with a different `WHYNOT_HOME` than the Claude Code session that called it finds no token. It refuses
  with "not seen", and `reel doctor` (run with that engine's environment) shows the hook's heartbeat is missing there.
- **Session, not role:** the session check binds Claude Code sessions, not roles. Subagents share the lead's session id.
  The "lead's call" check is the transcript and `agent_type`.
- **A refused call can leave a token.** If a call is allowed by the guard but then refused, its token stays usable for
  at most 120 s, and only for the identical call in the same folder and session. The call might be refused at the
  permission prompt, by another plugin's hook, or by the guard's own deadline.
