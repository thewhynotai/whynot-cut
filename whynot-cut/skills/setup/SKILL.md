---
name: setup
description: "Install/repair WhyNot Cut, free up space (Mac/PC): \"reel: command not found\", \"Premiere bridge not responding\", «المحرك مش متثبت», «نقلت على جهاز جديد», «فضّي مساحة». New user: /whynot-cut:start."
allowed-tools: Bash(reel *), PowerShell(reel *)
---

# Machine setup and repair (macOS and Windows)

1. **`reel: command not found` / "not recognized":** the plugin's `bin/` isn't on PATH. Check the plugin is enabled
   (`/plugin`), then fully restart Claude Code; meanwhile call it by its full path, in the shell you are using:
   ```bash
   "${CLAUDE_PLUGIN_ROOT}/bin/reel" doctor
   ```
   ```powershell
   & "${CLAUDE_PLUGIN_ROOT}/bin/reel.cmd" doctor
   ```
   **`reel` answers as something else** (`reel --version` is not `WhyNot Cut <version>`, or the error says
   `reel-editor environment not installed`): the session started before the install and another plugin's `bin/` (the
   old reel-editor, or the previous WhyNot Cut) is first on PATH; subagents inherit it. Restart Claude Code; until
   then call it by its full path everywhere, subagent prompts included: `"${CLAUDE_PLUGIN_ROOT}/bin/reel"` (bash) or
   `& "${CLAUDE_PLUGIN_ROOT}/bin/reel.cmd"` (PowerShell).
2. Check first, change second:
   ```bash
   reel --version
   reel doctor
   ```
   It is read-only and returns `verdict`, `ready`, and a `fixes` list (each fix says who does it: claude / editor).
   `reel_command` lists every `reel` on PATH; if the first is not this plugin's, a fix says so.
   **`guard_active: false` is a stop item:** say "WhyNot Cut protection is OFF" (the guard hook that keeps client
   `assets/` and `data/` read-only and the approvals the editor's own is not running), give `guard_heartbeat.fix`
   (Windows: Git for Windows, then restart Claude Code), and don't start any edit until `reel doctor` shows
   `guard_active: true`. `null` = an older guard that writes no heartbeat: ask them to check `/hooks`.
3. `reel setup` repairs everything WhyNot Cut owns. It's idempotent:
   - the engine runtime `~/.whynot-cut/runtimes/<id>` (Windows: `%USERPROFILE%\.whynot-cut\runtimes\<id>`), built or
     re-synced from the hash lock, with the one-line `current` file naming it; ffmpeg. `reel doctor` → `isolated:
     true` when every engine module loads from it. Engine-side scripts run with `reel py`
   - the WhyNot Cut Bridge panel in Premiere's CEP folder (replacing the old "Reel Editor Bridge" if present); the same
     bundle loads in After Effects for motion videos (`reel ppro-install`)
   - a fresh doctor report

   If the engine is missing, say it's about 400 MB and a few minutes and confirm first, unless the person just asked to
   install. Ask them to quit Premiere before running it (the panel folder is replaced; Windows locks it while Premiere
   runs). With no engine yet and a usable Python 3.9+ on the machine, the `reel` wrapper starts `setup/setup_env.py`,
   which builds the runtime on Python 3.12 (installed by WhyNot Cut). An existing `~/.reel-editor` install from
   reel-editor 1.x is reused automatically, models included.
   No Python (`no Python 3.9+ found`, e.g. a new Mac without Xcode tools): run the installer that ships with the plugin
   as `${CLAUDE_PLUGIN_ROOT}/skills/start/references/install-from-claude.md` says; it brings its own Python. Never send
   the person to Xcode tools, Homebrew, winget or python.org.
4. **Whisper large-v3 (about 3 GB)** downloads on the first `transcribe`, or deliberately (ask first) with
   `reel model-download --model large-v3` in the background. `reel doctor` → `whisper_partial_downloads` lists an
   interrupted download; the same command resumes it. With an NVIDIA
   GPU (Windows/Linux), transcription runs on CUDA when NVIDIA's cuBLAS can load. The doctor names the GPU and the
   missing library; with the editor's OK, `reel gpu-enable` installs it (about 520 MB, sha256-checked, from NVIDIA's own
   download server on Windows, much faster than PyPI; Whisper then runs about 8× faster).
   Without it everything works on the CPU, just slower.
5. **Premiere bridge:**
   - Premiere must be restarted after the first install, because CEP finds panels only at launch.
   - `PlayerDebugMode` must be 1 (CSXS 11–14). It lets Premiere load extensions not signed by Adobe; say so plainly.
     It's the editor's setting (a hook blocks Claude from writing it). Give each command from the doctor's `fixes` for
     their OS in its own fenced block (one command per block): macOS Terminal `defaults write …`; Windows
     **PowerShell** `reg add …` (not Git Bash, which mangles the `/v /d /f` switches).
   - macOS: when macOS asks whether Premiere Pro (or the app Claude runs in) may access files in Documents, Desktop or
     an external drive, the editor clicks Allow. Refused earlier: the editor turns that folder on for the app in
     System Settings › Privacy & Security › Files and Folders, then restarts the app. It is their setting; Claude never
     changes privacy settings and never suggests sudo or turning off macOS security.
   - `reel ppro-status` must show `alive: true` and a ping result before claiming the bridge works.
   - If the installed bridge is newer than this plugin's, `ppro-install`/`setup` keep it and report `skipped`; replace
     it only on the editor's word (`reel ppro-install --force`).
6. **After Effects (motion videos only):** after `reel ppro-install`, the editor restarts After Effects once;
   `reel ae-status` must show `host: AEFT`. Then `reel ae-probe` once per After Effects version (the lead views the
   frames and records the verdict). The plugin never changes After Effects preferences.
7. **Fonts:** each client's fonts come from their `assets/` folder. The editor installs them (macOS: double-click →
   Install Font; Windows: right-click → Install). `reel inbox --root "<CLIENT>"` then `reel client-db --root "<CLIENT>"`
   report any that are missing. After Effects needs the brand fonts installed too.
8. **Free up space** («فضّي مساحة», "the disk is full", the panel's "Free up space"): run `reel clean` (a dry
   run: nothing is removed). Tell the editor what a yes frees (`removable_bytes`, never the kept items' sizes) and
   each item's size and why. Only after the editor says yes, run `reel clean --apply` yourself (a subagent may not;
   it may run the dry run). Unused Whisper models go only with `reel clean --apply --models` and their own yes (each one is
   about 1.5-3 GB to download again). uv's downloaded packages go only with `reel clean --apply --uv-cache` and
   their own yes: say «التثبيت الجاي هيحمّل تاني» (the next setup downloads them again) with the size the dry run
   shows. Client folders, the model in use and anything outside the engine home are
   never touched. An item that could not be removed (a file another program holds) shows an `error` line: close
   that program, then run it again.
9. Report what is ready and what needs the editor. If something fails twice, spawn `whynot-cut:setup-doctor` with the
   exact output instead of trying variations.

Platform details and fixes: `${CLAUDE_SKILL_DIR}/references/platform-setup.md`. Pipeline failures: `${CLAUDE_PLUGIN_ROOT}/skills/edit/references/troubleshooting.md`.
