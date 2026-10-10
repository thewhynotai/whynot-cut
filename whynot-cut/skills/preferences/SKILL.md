---
name: preferences
description: "This skill should be used when the user wants to see or change how WhyNot Cut behaves for them — \"change my settings\", \"stop asking me to approve\", \"always ask before building\", \"use the faster transcription\", \"talk to me in Arabic\", \"where are my clients\", \"WhyNot Cut preferences\", \"إعدادات WhyNot Cut\", \"متسألنيش قبل ما تبني\", \"كلمني بالعربي\". It reads and writes the .claude/whynot-cut.local.md preferences file."
argument-hint: "[key=value ...]"
allowed-tools: Bash(reel *), PowerShell(reel *)
---

# Preferences

Preferences live in `.claude/whynot-cut.local.md` (YAML frontmatter + free notes). The first file found wins: the
`--root` folder (or the current folder) and its parents, then the folder in the `clients_root` plugin option /
`WHYNOT_CLIENTS_ROOT`, then `~/.claude/whynot-cut.local.md`. The `clients_root` value *inside* a file does not make that
file findable, which is why `/whynot-cut:start` writes the machine-wide file in `~`. Show the values in effect:
```bash
reel settings --root "<CLIENT>"        # or `reel settings` outside a client folder
```
`_file` says which file is in effect (null = defaults); `_problems` lists invalid values that fell back to defaults.

| Key | Values | Effect |
|---|---|---|
| `editor_name` | text | how to address the editor (empty = don't use a name) |
| `language` | `en` · `ar` | language for talking to the editor (on-screen text always follows the speaker) |
| `approval` | `ask` · `auto` | `ask` stops at Gate 1 for every plan; `auto` shows the plan + preview, then builds (recorded as delegated approval citing this file) |
| `whisper_model` | `large-v3` · `large-v3-turbo` · `medium` · `small` | accuracy vs. speed; `medium`/`small` are noticeably weaker on Arabic medical terms |
| `preview_video` | `true` · `false` | render the preview MP4 before approval |
| `clients_root` | folder | used by `reel doctor`, the session-start message and bare `--root "<name>"` |
| `notify_done` | `true` · `false` | start the final report of long runs with a clear "Finished" line |

Change values (keeps the others and the notes; unknown keys and invalid values are refused):
```bash
reel settings --init "<FOLDER>" --set approval=auto --set language=ar --force
```
`<FOLDER>` holds the `.claude/` of the file to change: take it from `_file` (drop `/.claude/whynot-cut.local.md`) so a
nearer file doesn't shadow the change. Create a new file only for a client-specific override (one client folder) or a
machine-wide default (`~`).

- Confirm by running `reel settings --root "<CLIENT>"` again and quoting the new values; `_problems` must be empty.
- When the user says "stop asking" / "just go", ask once whether they mean this clip only (delegated approval for this
  plan, no file change) or from now on (`approval=auto`).
- `approval: auto` is a standing delegation. Say so when switching it on, and that medical approvals are never
  automatic: graphics needing the doctor's sign-off always stay under "Needs you".
- Engine commands see changes immediately; the session hook reads them at the next session start.
- The file is personal (`.local.md`). In a git repo, suggest adding `.claude/*.local.md` to `.gitignore`.
- Only the lead conversation changes preferences (a hook blocks subagents from `reel settings --init`).
