# Platform setup reference (macOS and Windows)

## Where things live

| | macOS | Windows |
|---|---|---|
| Engine home (runtime, models, queue) | `~/.whynot-cut` | `%USERPROFILE%\.whynot-cut` |
| Engine runtime (3.0) | `~/.whynot-cut/runtimes/<id>/bin/python`, `<id>` named by the one-line file `~/.whynot-cut/current` | `%USERPROFILE%\.whynot-cut\runtimes\<id>\Scripts\python.exe`, `<id>` named by `%USERPROFILE%\.whynot-cut\current` |
| `reel` wrapper | `bin/reel` (bash) | `bin/reel` (Git Bash) and `bin/reel.cmd` (PowerShell/cmd) |
| Premiere bridge panel | `~/Library/Application Support/Adobe/CEP/extensions/ai.thewhynot.cut.bridge` | `%APPDATA%\Adobe\CEP\extensions\ai.thewhynot.cut.bridge` |
| Bridge logs | `~/Library/Logs/CSXS/CEPHtmlEngine*-PPRO-*.log` | `%TEMP%\CEPHtmlEngine*-PPRO-*.log` |
| PlayerDebugMode | `defaults read com.adobe.CSXS.12 PlayerDebugMode` | `reg query HKCU\Software\Adobe\CSXS.12 /v PlayerDebugMode` |
| Fonts checked | `~/Library/Fonts`, `/Library/Fonts`, `/System/Library/Fonts` | `C:\Windows\Fonts`, `%LOCALAPPDATA%\Microsoft\Windows\Fonts` |
| Adobe apps found in | `/Applications/Adobe <App> 20xx/` | `C:\Program Files\Adobe\Adobe <App> 20xx\` |
| Arabic text renderer for stills | CoreText (installed font), else HarfBuzz | HarfBuzz + FreeType from the client's font file |
| Face-aware photo crops | Vision framework | OpenCV face detector |
| AE / PS extras | AppleScript `DoScriptFile` | `AfterFX.exe -r`, Photoshop COM `DoJavaScriptFile` |
| Camera RAW photos | `sips` | `rawpy` if installed, else export JPEGs |

Set `WHYNOT_HOME` (or the plugin option `engine_home`) to move the engine home, e.g. to a bigger drive. The bridge
finds a moved home through `bridge-config.json`, which `reel setup` writes into the panel folder.

## Environment variables

All are optional; WhyNot Cut finds everything by itself when they are unset. Set one only to point at a
non-standard install or to move a folder. On Windows use `setx NAME value` (then open a new terminal and restart
Claude Code); on macOS export it in your shell profile (`~/.zshrc`).

| Variable | What it does | Default when unset |
|---|---|---|
| `WHYNOT_HOME` | The engine home: runtime, models, queue, logs. Same as the plugin option `engine_home`. Use an ASCII-only folder (e.g. `C:\whynot`) when your user name is not ASCII | `~/.whynot-cut` |
| `WHYNOT_CLIENTS_ROOT` | The folder that holds your client folders, so `--root` can be a bare client name. Same as the plugin option `clients_root` (the option wins over the preferences file) | `clients_root` from your preferences file; none if not set |
| `WHYNOT_OPTIONS_FILE` | Where the plugin options record is read from (the SessionStart hook writes it; the wrappers read it because PowerShell does not receive path variables) | `~/.whynot-cut/plugin-options.json` |
| `WHYNOT_PREMIERE_APP` | Premiere Pro to use: the `.app` / `.exe` or its folder. A wrong value is reported by `reel doctor` with this name | Newest release install found (registry / Spotlight / standard folders) |
| `WHYNOT_AE_APP` | After Effects to use: the `.app` / `.exe` or its folder | Newest release install found |
| `WHYNOT_AERENDER` | The `aerender` executable (`aerender.exe` on Windows, in the After Effects folder) | The one beside the newest After Effects that has one |
| `WHYNOT_FFMPEG` | The ffmpeg to run: the binary or the folder that holds it (needs ffmpeg 6 or newer) | The ffmpeg pinned in the engine home, then the runtime's bundled one, then `PATH` last |
| `WHYNOT_FFMPEG_TIMEOUT_SCALE` | A number from 1 to 100 that multiplies every ffmpeg time limit. Raise it (e.g. `3`) for a very long file or a slow network share when a step reports "ffmpeg timed out". Below 1 or not a number is ignored; above 100 counts as 100 | `1` |
| `WHYNOT_DEBUG` | `1` also prints the full Python traceback of an unexpected error on screen (it is always saved to the log). For developers and bug reports | off |
| `WHYNOT_HF_XET` | `1` turns Hugging Face "Xet" transfers back on for model downloads. They are off by default because they failed on some Windows machines; leave it unset unless a download is too slow | off |

## Running your own Python against the engine

Run engine-side Python with `reel py`: `reel py <script.py> [args]`, `reel py -m <module> [args]` or
`reel py -c "<code>"`. It runs the engine runtime's python (the runtime named by `current`, else a 2.x `venv/`),
with the engine's packages (PIL, av, numpy, cv2) and its `lib.*` importable, wherever the engine home is
(`WHYNOT_HOME` or the plugin option `engine_home` may move it). The script's output and exit code are its own.
Never hard-code a path to the engine's python.

- The 3.0 runtime is isolated: it is built from the platform's hash lock (`setup/locks/`) without
  `--system-site-packages`, and the wrappers run it with `-s`, so nothing from the user site-packages leaks in.
  `reel doctor` → `isolated: true` means every engine module loads from inside the runtime; `false` lists the
  module and the fix (`reel setup`, which repairs the runtime in place, or builds a new one side by side and
  switches `current`).
- Only a 2.x venv still on a machine was built with `--system-site-packages` (that flag belongs to
  `setup/setup_env.py` and is not a `reel setup` option); there `-I`, `-s` and `-E -s` switch the user site-packages
  off and `import PIL` fails with `ModuleNotFoundError` although `reel` works. `reel py` avoids it; `reel setup`
  replaces that venv with the runtime.
- Need isolation (a script that reads untrusted files)? Keep the script outside the folder it reads: the script's
  folder and the working directory are on `sys.path`.
- Check: `reel py -c "import PIL, av, numpy"` prints nothing when the environment is fine; `reel doctor` lists
  the modules.

## Symptom → cause → fix

| Symptom | Cause | Fix |
|---|---|---|
| `"blocked": "WhyNot Cut <version>: engine not installed"` | No engine runtime yet (no `current`, no 2.x `venv/`) | `reel setup` (ask first: ~400 MB) |
| `reel` says `reel-editor environment not installed` (or any message that does not start with `WhyNot Cut <version>`), `reel --version` is not `WhyNot Cut <version>` | The Claude Code session started before WhyNot Cut was installed or updated, so another plugin's `bin/` (the old reel-editor, or the previous WhyNot Cut) is first on PATH; subagents inherit it | Restart Claude Code. Until then call it by its full path (and tell subagents to): `"${CLAUDE_PLUGIN_ROOT}/bin/reel"` in bash, `& "${CLAUDE_PLUGIN_ROOT}/bin/reel.cmd"` in PowerShell; `<that path> doctor` → `reel_command` lists every `reel` on PATH |
| `no Python 3.9+ found` | Fresh machine (a new Mac has no Python without Xcode tools) | Run the installer that ships with the plugin (`/whynot-cut:start` does it: `skills/start/references/install-from-claude.md`); it brings its own Python 3.12 (installed by WhyNot Cut). No Xcode tools, Homebrew, winget or admin rights |
| Windows: `python3` opens the Microsoft Store | Store alias stub on PATH | The wrappers skip it; with no other Python, run the installer as above (or disable the alias in Settings › Apps › App execution aliases) |
| pip fails building `numpy`/`av` | Python too new for the pinned wheels | Use Python 3.12 (installed by WhyNot Cut) and run `reel setup` again |
| `ModuleNotFoundError: No module named 'PIL'` (or `av`, `numpy`) in your own script while `reel` works | The script ran with another python (system Python, or a 2.x `--system-site-packages` venv under `-I` / `-s`) | Run it with `reel py <script.py>`; `reel setup` moves a 2.x machine to the isolated runtime |
| Bridge missing in Window › Extensions | Premiere was open during install, or PlayerDebugMode off | Editor sets PlayerDebugMode, quits and reopens Premiere |
| `ppro-status` alive false with a stale heartbeat | Panel closed or Premiere busy with a dialog | Bring Premiere to the front, dismiss dialogs; reopen Window › Extensions › WhyNot Cut Bridge |
| Transcription very slow on Windows | CPU only | NVIDIA GPU with CUDA 12 runtime makes it automatic; else set preferences `whisper_model: large-v3-turbo` |
| `GPU transcription failed … retrying on CPU` in the log | cuDNN/cuBLAS DLLs missing | Harmless (CPU used). For GPU speed install NVIDIA's CUDA 12 + cuDNN 9 runtime |
| Arabic letters isolated in a still | Pillow fallback used (no HarfBuzz and no exact CoreText font) | `reel doctor` → `uharfbuzz`/`freetype` must be True; `reel setup` |
| Brief `.docx`/`.pdf` read as empty | Older engine | Engine 2.x reads `.docx`, `.rtf`, `.pdf` on both systems (`pypdf`) |
| `Fonts not installed` in client-db | Brand fonts only in `assets/Fonts` | Editor installs them; previews still render from the files, Premiere needs them installed |
| Arabic in output shows as `?` in a terminal | Console code page | Engine forces UTF-8 output; use the Bash or PowerShell tool output, not an old cmd window |
