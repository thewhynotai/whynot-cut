---
name: start
description: "First steps after installing WhyNot Cut, from empty machine to ready: \"get started\", \"set me up\", \"I just installed the plugin\", «أول مرة أستخدمه», «إزاي أبدأ»."
argument-hint: "[folder for client folders]"
allowed-tools: Bash(reel *), PowerShell(reel *)
---

# WhyNot Cut: guided start

WhyNot Cut (by The Why Not AI) turns raw talking-head footage into a native Premiere Pro project: transcript, cleaned
dialogue with pauses removed, story-driven animated graphics and captions in the client's brand, a watchable preview,
and evidence-based QC. This wizard gets a new user to the point where they only drop files into a folder.

Talk to the person in their language (Arabic if they write Arabic). Put every command and path on its own line or in a
code block (mixed right-to-left text garbles paths). One step per message: what was checked, what happens next.
Show progress as a checklist (✅ done · ⚠️ needs them · ⏳ running). If an argument was given, use it as the clients
folder and skip that question in Step 3.

Installing from inside Claude (the plugin, the engine and the Adobe parts in one go): when
`${CLAUDE_SKILL_DIR}/references/install-from-claude.md` is present, read it and follow it for Steps 1–2; if it is
not there, the steps below cover the install.

## Step 1: Check the machine
```bash
reel --version
reel doctor
```
`reel --version` must print `WhyNot Cut <version>`; every WhyNot Cut message starts with that name and version.
- **`reel: command not found` / "not recognized":** the plugin's `bin/` is on PATH only in sessions started after the
  install. Ask the person to fully quit and reopen Claude Code, then retry. Until then call it by full path, in the
  shell you are using:
  ```bash
  "${CLAUDE_PLUGIN_ROOT}/bin/reel" doctor
  ```
  ```powershell
  & "${CLAUDE_PLUGIN_ROOT}/bin/reel.cmd" doctor
  ```
- **`reel` answers, but not as WhyNot Cut** (`reel --version` fails or prints something else, or an error says
  `reel-editor environment not installed`): a session started before the install keeps the OLD plugin's `bin/` first
  on PATH, so `reel` is the old reel-editor (or a previous WhyNot Cut). Subagents inherit that PATH. Say so, ask the
  person to restart Claude Code, and until then use the full path in every command and in every subagent prompt:
  `"${CLAUDE_PLUGIN_ROOT}/bin/reel"` (bash) or `& "${CLAUDE_PLUGIN_ROOT}/bin/reel.cmd"` (PowerShell). Its `doctor`
  lists every `reel` on PATH (`reel_command`) and says which plugin each belongs to. Never run the old plugin's
  `reel setup`.
- **`guard_active: false` — stop here.** Say "WhyNot Cut protection is OFF": the guard hook that keeps the client's
  `assets/` and `data/` read-only and keeps approvals the editor's own is not running. Give `guard_heartbeat.fix` from
  the report (Windows: install Git for Windows, then restart Claude Code; then `/hooks` should list WhyNot Cut).
  Don't go on to editing until `reel doctor` shows `guard_active: true`. `null` means an older guard that writes no
  heartbeat: ask them to check `/hooks`.
- **Engine missing** (`blocked: engine not installed`): explain it is a private Python environment in `~/.whynot-cut`
  (about 400 MB, a few minutes, nothing else on the computer changes) and ask once. On yes, run `reel setup` in the
  background and ask the Step 3 questions while it runs; write preferences and re-run `reel doctor` after it finishes.
- **No Python 3.9+** (`reel setup` says so): installing software is the person's job. Give the command for their OS,
  then ask them to quit and reopen Claude Code:
  - Windows (PowerShell): `winget install Python.Python.3.12` (no winget: the python.org installer, tick
    "Add python.exe to PATH")
  - macOS: `xcode-select --install` (an Apple dialog opens; click Install and wait)
- Anything else failing: spawn `whynot-cut:setup-doctor` with the exact output and relay its fix list. Never guess.
- Report `verdict`, the GPU line (an NVIDIA GPU makes transcription several times faster) and the Adobe apps found.

## Step 2: Connect Premiere Pro
Read `adobe_apps.premiere` and `premiere_bridge` from the doctor report.
- **No Premiere:** say so plainly. WhyNot Cut still produces an importable XML project and a preview MP4; the native
  build starts working once Premiere Pro 2022+ is installed. Continue.
- **Bridge not installed:** ask them to quit Premiere first (Windows locks the panel folder while it runs), then
  `reel setup` installs the WhyNot Cut Bridge panel.
- **`debug_mode_ok` false:** Premiere loads the panel only when Adobe's `PlayerDebugMode` is 1, which lets Premiere load
  extensions that aren't signed by Adobe. Say that plainly; they may skip it and import the XML by hand instead. This
  setting is theirs to change (a hook blocks Claude from changing it). Show the commands from the doctor's `fixes` in one
  code block for their OS. On Windows they run them in **PowerShell** (Git Bash mangles the `/v /d /f` switches).
- Ask them to open Premiere once, then run `reel ppro-status`. If `alive` is false, ask them to open
  Window › Extensions › WhyNot Cut Bridge and check once more; still false → spawn `whynot-cut:setup-doctor`.
  Don't loop, and don't claim the bridge works without `alive: true` and a `ping` result.

## Step 3: Preferences and the clients folder
Ask with AskUserQuestion (recommended option first):
1. **Where to keep client folders.** macOS: `~/Documents/WhyNot Clients`. Windows: `D:\WhyNot Clients` only if a D: drive
   exists, else `%USERPROFILE%\Documents\WhyNot Clients`. Avoid OneDrive/iCloud/Dropbox-synced folders: online-only files
   break transcription. Needs about 4 GB free for the engine and model, plus several GB per client.
2. **Approval:** `ask` (show the plan and preview, wait for their OK before building; recommended) or `auto` (show it,
   then build without waiting; they can still revise afterwards; medical approvals are never automatic).
3. **Transcription:** `large-v3` (most accurate; recommended with an NVIDIA GPU) or `large-v3-turbo` (much faster
   without one: every Mac and most laptops).
4. **How to address them** (optional; leave empty if they skip; never guess a name).

Write the preferences machine-wide so every session finds them:
```bash
reel settings --init "~" --set clients_root="<CLIENTS_FOLDER>" --set editor_name="<name or empty>" --set language=<en|ar> --set approval=<ask|auto> --set whisper_model=<model>
```
This writes `~/.claude/whynot-cut.local.md`; a client folder can still override it. If `reel doctor` already showed a
`settings_file`, show its values, change only what they ask, and add `--force` (other values are kept). Check that
`_problems` comes back empty.

## Step 4: The first client folder
Ask for the client's name (e.g. "Dr Sherif"). For the folder name drop characters Windows forbids
(`\ / : * ? " < > |`) and any trailing dot or space; keep the name as typed for `--name`.
```bash
reel scaffold --root "<CLIENTS_FOLDER>/<Client Name>" --name "<Client Name>"
```
- `status: EXISTS` means the folder already has material: go to Step 5.
- Show the table from `START_HERE.md`: logo → `assets/Logo`, fonts → `assets/Fonts`, photos → `assets/Photos`,
  brief + colour HEX codes → `assets/Brand`, raw clips → `data/Raw`, reference edits → `data/References`.
- Offer to open the folder: `open "<folder>"` on macOS; `explorer.exe "<folder with backslashes>"` on Windows (explorer
  ignores forward-slash paths and returns exit code 1 even when it works). If macOS asks whether the terminal may access
  Documents/Desktop/an external drive, they click Allow (or later: System Settings › Privacy & Security › Files and Folders).
- Remind them to install the client's fonts on the computer too (Premiere needs them installed).

- Podcast clients: finished episodes go in `data/Episodes/` (16:9), each with an optional `<name>.md` sheet (host,
  guest, links, sponsor, topics to avoid). Then "make reels from this episode" (`/whynot-cut:podcast`).

## Step 5: Check what they dropped
When they say the files are in (and any copy or cloud download has finished):
```bash
reel inbox --root "<CLIENT_FOLDER>"
```
For a closer look (formats, orientation, audio, misplaced files), spawn `whynot-cut:intake-inspector`. Report the clips
found and `missing_material`. A missing logo, fonts or colours is fine to start with, but say what will look generic
without them. Never invent brand facts to fill a gap.

## Step 6: Hand over to the pipeline
- `reel profile --root "<CLIENT_FOLDER>"` → `active` null: run the `/whynot-cut:new-client` flow (the client-researcher
  reads their brand and references).
- If `reel inbox` listed new clips, ask whether to start editing now; on yes, run `/whynot-cut:autopilot`. Tell them what
  to expect: transcription (the first run needs the Whisper model, about 3 GB for large-v3; ask, then
  `reel model-download --model <whisper_model>` in the background while the client profile is built),
  a plan and a preview video to approve, the Premiere build, QC.

Finish with two lines from `/whynot-cut:help` and their next step: "drop more clips into data/Raw any time, then say
'edit the new videos'".

## Rules
- One step at a time; verify each step with a command before calling it done.
- Never change Adobe preferences, the registry or system settings; give the person the command.
- Installers (Python, Xcode tools, fonts) are run by the person, never by Claude. `reel setup` covers the engine.
- Ask before large downloads (engine, Whisper model).
- `assets/` and `data/` belong to the client: scaffold only creates them for a new client, never edits them.
- In your own messages, tables and file names, «الدكتور/الدكتورة» and he/she come only from people[] (reel-profile
  `profile.json`). Until a person's gender is known write «د.» or the name.

Troubleshooting: `${CLAUDE_PLUGIN_ROOT}/skills/setup/references/platform-setup.md`.

Motion videos (animated, from a podcast's audio) are built in After Effects through the same WhyNot Cut Bridge: after
`reel ppro-install` the editor restarts After Effects once; `reel ae-status` must show `host: AEFT`. Brand fonts must
be installed for After Effects too. Set this up only when they want motion videos.
