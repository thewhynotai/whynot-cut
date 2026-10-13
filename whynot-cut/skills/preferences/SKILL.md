---
name: preferences
description: "See or change WhyNot Cut settings: \"change my settings\", \"stop asking me to approve\", \"where are my clients\", «إعدادات WhyNot Cut», «كلمني بالعربي»."
argument-hint: "[key=value ...]"
allowed-tools: Bash(reel *), PowerShell(reel *)
---

# Preferences

Four layers, **highest wins, key by key** (a layer that does not set a key lets the next one decide):

1. **The client's file**: `.claude/whynot-cut.local.md` in the `--root` folder (or the current folder) and its parents,
   nearest first.
2. **The machine's file**: the one in the clients folder (`clients_root` plugin option / `WHYNOT_CLIENTS_ROOT`), then
   `~/.claude/whynot-cut.local.md`. The `clients_root` value *inside* a file does not make that file findable, which is
   why `/whynot-cut:start` writes the machine-wide file in `~`.
3. **The plugin options** (Claude Code asks for them when the plugin is enabled; `/plugin` changes them): `language`,
   `approval`, `whisper_model`, `magnific_budget_credits`. The engine reads them from the `CLAUDE_PLUGIN_OPTION_*`
   variables, else the pointer file `~/.whynot-cut/plugin-options.json` (written at session start), else
   `settings.json` `pluginConfigs`.
4. **The defaults** (`language` ar, `approval` ask, `whisper_model` large-v3, `magnific_budget_credits` 300).

A file holds only the keys someone set, so the plugin options keep applying to everything it leaves out. An invalid
value is ignored with a warning (the next layer, in the end the default, applies). `clients_root` is the exception: the
plugin option wins over a file value. The Magnific API key (`magnific_api_key`) is a plugin option only: Claude Code keeps
it in the system keychain; it is never in a preferences file, the pointer file or any report (`reel settings` shows
only `magnific_api_key_set: true|false`). Show the values in effect:
```bash
reel settings --root "<CLIENT>"        # or `reel settings` outside a client folder
```
`_sources` says which layer each value comes from (`client` · `machine` · `userConfig` · `default`), `_where` the file or
"plugin option", `_file` the strongest file (null = none), `_problems` the ignored values.

| Key | Values | Effect |
|---|---|---|
| `editor_name` | text | how to address the editor (empty = don't use a name) |
| `language` | `en` · `ar` | language for talking to the editor (on-screen text always follows the speaker) |
| `approval` | `ask` · `auto` | `ask` stops for the editor to approve every plan; `auto` shows the plan + preview, then builds (recorded as delegated approval citing this file) |
| `whisper_model` | `large-v3` · `large-v3-turbo` · `medium` · `small` | accuracy vs. speed; `medium`/`small` are noticeably weaker on Arabic medical terms |
| `preview_video` | `true` · `false` | render the preview MP4 before approval |
| `clients_root` | folder | used by `reel doctor`, the session-start message and bare `--root "<name>"` |
| `notify_done` | `true` · `false` | start the final report of long runs with a clear "Finished" line |
| `panel_link` | `true` · `false` | start the engine the Premiere panel talks to (`reel serve`) in the background at session start; `false` leaves the panel offline until `reel serve ensure` |
| `magnific_budget_credits` | number, 0 or more | the most Magnific credits one edit may spend (0 = never use Magnific; default 300) |

`language`, `approval`, `whisper_model` and `magnific_budget_credits` are also plugin options (layer 3).

Change values (keeps the others and the notes; unknown keys and invalid values are refused):
```bash
reel settings --init "<FOLDER>" --set approval=auto --set language=ar --force
```
`<FOLDER>` holds the `.claude/` of the file to change: take it from `_where` for that key (drop
`/.claude/whynot-cut.local.md`) so a nearer file doesn't shadow the change. Create a new file only for a
client-specific override (one client folder) or a machine-wide default (`~`). When a value should follow the plugin
option (e.g. everyone's `approval`), change the plugin option in `/plugin` instead of writing a file; only the keys you
`--set` are written, so nothing else is pinned.

- Confirm by running `reel settings --root "<CLIENT>"` again and quoting the new values; `_problems` must be empty.
- When the user says "stop asking" / "just go", ask once whether they mean this clip only (delegated approval for this
  plan, no file change) or from now on (`approval=auto`).
- `approval: auto` is a standing delegation. Say so when switching it on, and that medical approvals are never
  automatic: graphics needing the doctor's sign-off always stay under "Needs you".
- Engine commands see changes immediately; the session hook reads them at the next session start.
- The file is personal (`.local.md`). In a git repo, suggest adding `.claude/*.local.md` to `.gitignore`.
- Only the lead conversation changes preferences (a hook blocks subagents from `reel settings --init`).
