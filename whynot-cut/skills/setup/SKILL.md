---
name: setup
description: "Install or repair WhyNot Cut on a Mac or PC: \"install the engine\", \"reel: command not found\", \"Premiere bridge not responding\", «المحرك مش متثبت», «نقلت على جهاز جديد». New user: /whynot-cut:start."
allowed-tools: Bash(reel *), PowerShell(reel *)
---

# Machine setup and repair (macOS and Windows)

1. **`reel: command not found` / "not recognized":** the plugin's `bin/` isn't on PATH. Check the plugin is enabled
   (`/plugin`), then fully restart Claude Code; meanwhile use `"${CLAUDE_PLUGIN_ROOT}/bin/reel"`.
   **`reel` answers as something else** (`reel --version` is not `WhyNot Cut <version>`, or the error says
   `reel-editor environment not installed`): the session started before the install and another plugin's `bin/` (the
   old reel-editor, or the previous WhyNot Cut) is first on PATH; subagents inherit it. Restart Claude Code; until
   then call `"${CLAUDE_PLUGIN_ROOT}/bin/reel"` by its full path everywhere, subagent prompts included.
2. Check first, change second:
   ```bash
   reel --version
   reel doctor
   ```
   It is read-only and returns `verdict`, `ready`, and a `fixes` list (each fix says who does it: claude / editor).
   `reel_command` lists every `reel` on PATH; if the first is not this plugin's, a fix says so.
3. `reel setup` repairs everything WhyNot Cut owns. It's idempotent:
   - the engine runtime `~/.whynot-cut/runtimes/<id>` (Windows: `%USERPROFILE%\.whynot-cut\runtimes\<id>`), built or
     re-synced from the hash lock, with the one-line `current` file naming it; ffmpeg. `reel doctor` → `isolated:
     true` when every engine module loads from it. Engine-side scripts run with `reel py`
   - the WhyNot Cut Bridge panel in Premiere's CEP folder (replacing the old "Reel Editor Bridge" if present)
   - a fresh doctor report

   If the engine is missing, say it's about 400 MB and a few minutes and confirm first, unless the person just asked to
   install. Ask them to quit Premiere before running it (the panel folder is replaced; Windows locks it while Premiere
   runs). With no engine yet, the `reel` wrapper builds it via `setup/setup_env.py` on
   Python 3.12 (installed by WhyNot Cut). An existing `~/.reel-editor` install from reel-editor 1.x is reused automatically, models included.
   No Python: the person installs it (Windows `winget install Python.Python.3.12`; macOS `xcode-select --install`).
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
     It's the editor's setting (a hook blocks Claude from writing it). Give the commands from the doctor's `fixes` in one
     fenced block for their OS: macOS Terminal `defaults write …`; Windows **PowerShell** `reg add …` (not Git Bash,
     which mangles the `/v /d /f` switches).
   - `reel ppro-status` must show `alive: true` and a ping result before claiming the bridge works.
6. **Fonts:** each client's fonts come from their `assets/` folder. The editor installs them (macOS: double-click →
   Install Font; Windows: right-click → Install). `reel inbox --root "<CLIENT>"` then `reel client-db --root "<CLIENT>"`
   report any that are missing.
7. Report what is ready and what needs the editor. If something fails twice, spawn `whynot-cut:setup-doctor` with the
   exact output instead of trying variations.

Platform details and fixes: `references/platform-setup.md`. Pipeline failures: `${CLAUDE_PLUGIN_ROOT}/skills/edit/references/troubleshooting.md`.

## Motion mode (2.2)
`reel ppro-install` installs one bundle for Premiere and After Effects (bridge 3.1.1). Check After Effects with
`reel ae-status`; then `reel ae-probe` once per After Effects version (the lead views the frames and records the
verdict). The plugin never changes After Effects preferences. If the installed bridge is newer than this plugin's,
`ppro-install`/`setup` keep it and report `skipped`; replace it only on the editor's word (`reel ppro-install --force`).
