# WhyNot Cut installer (3.0)

Installs WhyNot Cut for the current user on Windows 10/11 x64 and macOS (Apple silicon and Intel). It needs no admin
rights, no Homebrew, no Xcode tools, and no Python on the machine.

| File | What it is |
|---|---|
| `install.ps1` | Windows front end (Windows PowerShell 5.1 or PowerShell 7). |
| `install.sh` | macOS front end (bash 3.2 or newer). |
| `core/bootstrap.ps1`, `core/bootstrap.sh` | These put uv and Python in place, then start the core. The front end runs them; you never run them yourself. |
| `core/wnc_install.py` + `core/wnc_installer/` | The installer core. It is plain Python (standard library only) and runs the 14 steps on both systems. |
| `licenses/` | Licence texts shipped with third-party binaries (ffmpeg: GPL-3.0). |

## Run it

### From the WhyNot Cut zip (today)

1. Extract the zip.
2. Open a terminal in the extracted folder (it holds `whynot-cut/`):

   - **Windows:** open PowerShell (Start › type "PowerShell" › Enter), then run:
     ```powershell
     powershell -ExecutionPolicy Bypass -File whynot-cut\installer\install.ps1
     ```
   - **macOS:** open Terminal (Spotlight › "Terminal"), then run:
     ```bash
     bash whynot-cut/installer/install.sh
     ```

The installer uses the plugin folder it sits in. That is the folder above `installer/` that holds
`setup/components.json`.

### No questions by default

The installer asks nothing unless you want to choose (Addendum D, D-T1). It starts with one line, in English and
Arabic:

> Installing everything WhyNot Cut needs (about N GB)

N is the runtime (about 0.5 GB), ffmpeg and the fonts (their sizes from `components.json`), the Whisper model
(`large-v3`, about 2.9 GB, or the one `-Model` names) and, on Windows, PortableGit unpacked (about 0.4 GB) when Git
Bash is missing and the NVIDIA CUDA libraries (about 1 GB) when an NVIDIA GPU is there; a step you skip with `-Skip`
is not counted, and N is rounded up to one decimal. When a person is at the terminal, a
10-second countdown follows on one line that updates in place:

> Press C to customise (10)... / اضغط C للتخصيص

- nobody presses a key, or any key other than C: everything installs with the strongest defaults, exactly as with
  `-Yes` (the same steps, the same `state.json`; `answers.mode` is `"default"`);
- **C**: the Customise path - the questions below, every answer preselected (Enter keeps it):
  the location of the engine (asked by the bootstrap before any download), then the Whisper model, the language and
  the clients folder (asked by the core). `answers.mode` in `state.json` is then `"customise"`.

`-Customise` / `--customise` goes straight to the Customise path, without the countdown. `-Yes` / `--yes` shows no
countdown and asks nothing; `-Yes` together with `-Customise` stops with exit code 2. Without a keyboard (input
redirected or piped, `-NonInteractive`, a CI run, the install from inside Claude, Setup.exe) the installer behaves
like `-Yes` and never waits for a key. On Windows the key is read from the console (`[Console]::KeyAvailable`); on
macOS from the terminal, or from `/dev/tty` under `curl | bash` when it can be opened and the output goes to a
terminal too, never from the piped script, and only when the installer runs in the foreground (without that: no
countdown). Keys typed before the countdown appears (the Enter after the command) are not taken as an answer; with
macOS's own bash 3.2 the first second of the countdown is spent clearing them. A saved engine home in the wrong place
(below) is refused before the countdown, so you never wait 10 seconds for an error.

### One line (future: needs hosting, H3)

```powershell
irm https://dl.thewhynot.ai/install.ps1 | iex
```
```bash
curl -fsSL https://dl.thewhynot.ai/install.sh | bash
```

In this mode the script has no folder of its own. It fetches the release named by the release index (`release.index_url`,
which the release tool fills in). Until that index is hosted, the script prints this line in English and Arabic and
exits with code 2:

> hosting is not ready yet (H3): download the zip, extract it, run `installer\install.ps1`

You can point a one-liner at a specific release zip, either a file or an https URL, together with its sha256:

```powershell
& ([scriptblock]::Create((irm https://dl.thewhynot.ai/install.ps1))) -Source https://.../WhyNotCut-3.0.0.zip -SourceSha256 <64 hex>
```
```bash
curl -fsSL https://dl.thewhynot.ai/install.sh | bash -s -- --source https://.../WhyNotCut-3.0.0.zip --source-sha256 <64 hex>
```

The installer copies or downloads the zip into `downloads/release-<first 8 of the sha256>/` of the engine home (normally
`~/.whynot-cut`; see [Where the engine home is](#where-the-engine-home-is)) and checks it
against the sha256. A mismatch deletes the file and exits with code 3. It then extracts the zip into `x/` next to it,
and `x/whynot-cut-marketplace/whynot-cut` becomes the plugin folder.

## Options

| Windows (`install.ps1`) | macOS (`install.sh`) | Meaning |
|---|---|---|
| `-Home <dir>` | `--home <dir>` | Sandbox or test mode. Everything goes under `<dir>` (see below). |
| `-DryRun` | `--dry-run` | Says what would happen and writes nothing: no log, no folder. |
| `-Yes` | `--yes` | Asks no questions and takes the defaults (the strongest choice everywhere), without the 10-second countdown. Without `-Yes` the installer asks nothing either; it only counts down 10 seconds so you can press C (see [No questions by default](#no-questions-by-default)). |
| `-Customise` | `--customise` | The Customise path: asks the location, the Whisper model, the language and the clients folder, every answer preselected. Also reached by pressing C during the countdown. Not together with `-Yes`. (`-Customize` / `--customize` work too.) |
| `-EngineHome <dir>` | `--engine-home <dir>` | Where the engine goes (uv, Python, runtimes, ffmpeg, the Whisper model, logs, `state.json`): answers the location question. Default: the folder found as described in [Where the engine home is](#where-the-engine-home-is), normally `~/.whynot-cut`. With `-Uninstall`: the engine home to remove. |
| `-Model <name>` | `--model <name>` | The Whisper model to install: `large-v3` (about 2.9 GB, the default: best accuracy), `large-v3-turbo` (about 1.6 GB: faster, a little less accurate), `medium` (about 1.5 GB) or `small` (about 0.5 GB). Answers the model question. |
| `-ClientsFolder <dir>` | `--clients-folder <dir>` | The folder that holds the client folders. The folder itself is never created. |
| `-Language ar\|en` | `--language ar\|en` | Language of the answers (default `ar`). |
| `-Channel stable\|beta` | `--channel stable\|beta` | Release channel (default: the one in `components.json`). |
| `-Components <file>` | `--components <file>` | Use another `components.json` (tests, release checks). |
| `-Skip a,b` | `--skip a,b` | Skip core steps by name: `preflight questions runtime ffmpeg gitbash gpu claude adobe fonts settings model state doctor launch`. |
| `-Uninstall` | `--uninstall` | Remove WhyNot Cut for this user. |
| `-RemoveEngine` | `--remove-engine` | With uninstall: also delete the engine home (runtimes, ffmpeg, ...). `models/` stays unless you add `-RemoveModels`; `library/` (your licensed motion and illustration packs) always stays. |
| `-RemoveModels` | `--remove-models` | With uninstall: also delete the Whisper models (0.5 to 2.9 GB each). |
| `-Source <zip\|url>` | `--source <zip\|url>` | One-line mode: the release zip to install from. |
| `-SourceSha256 <hex>` | `--source-sha256 <hex>` | The sha256 of that zip. It is required with `-Source`. |

Exit codes:

| Code | Meaning |
|---|---|
| 0 | Done. Some rows may be amber or skipped; the checklist says why. |
| 1 | At least one step failed (red). |
| 2 | Cannot start, for one of these reasons: wrong OS or CPU, Git Bash on Windows, no hosting yet, a bad option (or `-Yes` with `-Customise`), an unreadable `components.json`, too little free space, or an engine home that cannot be used (see the location question, and [A saved engine home in the wrong place](#a-saved-engine-home-in-the-wrong-place)). Nothing was downloaded. |
| 3 | A download or a bootstrap step failed: uv, Python, or a sha256 mismatch. The message names the file and the log. |

## Where the engine home is

The engine home is the folder written `~/.whynot-cut` in this README. Outside a sandbox, the installer finds it exactly
the way the engine does (`engine/reel/lib/plat.py`), in this order:

1. the first of these variables that is set: `WHYNOT_HOME`, `CLAUDE_PLUGIN_OPTION_ENGINE_HOME`, `REEL_HOME`,
   `CLAUDE_PLUGIN_OPTION_REEL_HOME`, `NH_ENV_DIR`;
2. the plugin option `engine_home` saved in `~/.whynot-cut/plugin-options.json` (the file the plugin's SessionStart hook
   writes; `WHYNOT_OPTIONS_FILE` moves it), when that file is a JSON object with an `engine_home` text (`""` means
   "not set" and ends the search);
3. otherwise the same option in Claude Code's `settings.json` (`~/.claude`, or `CLAUDE_CONFIG_DIR`), under
   `pluginConfigs["whynot-cut@thewhynot-ai"].options`, else the first other `whynot-cut@...` entry with `options`;
4. otherwise `~/.whynot-cut`.

`~` in a saved value is your user folder; on Windows a Git Bash path such as `/d/WhyNot` means `D:/WhyNot`. The
engine's old fallback to an earlier `~/.reel-editor` home is not used: after the install the engine finds the new
`current` file and uses this folder too.

### The location question

The bootstrap works this folder out before it downloads anything and offers it as the default of its first question
(in English and Arabic):

> Where should WhyNot Cut keep its engine (Python, ffmpeg, the Whisper model)? It needs about 6 GB, 9 GB with the
> model. Enter keeps the folder in brackets.

The question is asked only on the Customise path (`-Customise`, or C during the countdown); otherwise the default
is used, as with `-Yes`. `-EngineHome <dir>` / `--engine-home <dir>` answers it; `-Yes` / `--yes` takes the default;
without a terminal the default is used. On macOS the answer is read from the terminal, or from `/dev/tty` under `curl | bash` (never from
the piped script). When WhyNot Cut is already installed there, the question says so: Enter keeps it.

The folder is checked before anything is downloaded (the same rules in both bootstraps and the core):

- refused: not a full path; a drive root or a mounted volume (`D:\`, `/Volumes/<name>`, any mount point) or a link;
  anything inside the plugin folder (it is replaced on every update);
- refused, unless WhyNot Cut is already installed there: a folder that holds the plugin folder (except in its own
  `downloads/`, where the one-line mode caches the release); one that is, holds or lies inside your clients folder
  (`clients_root` in your preferences or in `plugin-options.json`); one inside a folder marked `.whynot-client`, or
  holding one (three levels down);
- **moved into its own `WhyNotCut` subfolder** - only for a folder you choose (`-EngineHome` or a typed answer)
  that is not the folder WhyNot Cut already uses: the resolved engine home (`~/.whynot-cut`, or the one saved in
  `plugin-options.json` / `settings.json` / a variable) is always used as it is, so a 2.x install there is upgraded
  in place with its models. Moved: your user folder, Desktop, Documents and Downloads themselves, and any
  existing folder with anything in it that is not already a WhyNot Cut engine home. Names are never trusted: a
  folder holding your own `fonts`, `logs`, `downloads` or `Bin` counts as yours. Only the installer's own write test,
  the one-line mode's `downloads/release-*` cache and, in `~/.whynot-cut`, the plugin's `plugin-options.json` do not
  count. A folder is a WhyNot Cut engine home only by what WhyNot Cut wrote there: a `state.json` that is a JSON object
  with `schema` 1 and a `plugin` key, or a `current` naming a runtime whose `runtimes/<id>/WHYNOT_RUNTIME` stamp has
  that same id (a file merely named `state.json`, `current` or `bin/uv` is not enough). The installer writes that
  `state.json` as soon as it has chosen a folder, before any download, so running it again after a failed download
  uses the same folder. Choosing `D:\Work` or `Documents` therefore installs into `D:\Work\WhyNotCut` or `Documents\WhyNotCut`, and the
  installer says so in English and Arabic. Uninstall can then never empty a folder of your own files. A `WhyNotCut`
  subfolder that itself holds other files is refused;
- then: not Claude's folder; in a sandbox, inside the sandbox; 6 GB free on the drive, 9 GB with the Whisper model
  (6 GB with `-Skip model`), unless WhyNot Cut is already installed there; the folder can be created and written in.

A refused folder is explained and asked again; with `-Yes` the installer stops with exit code 2 and downloads nothing.

On Windows, a path with non-English (non-ASCII) letters gets a warning in English and Arabic, because some tools can
fail on such a path; it suggests `C:\WhyNotCut` and asks again (Enter takes the suggestion; typing the same folder
again keeps it). With `-Yes` the folder is kept and the warning stays on the screen. A folder WhyNot Cut is already
installed in is never questioned again: on a re-install, Enter keeps the engine where it is (a one-line note mentions
the letters). When you choose a folder other than the one WhyNot Cut is already installed in, the installer says (in
English and Arabic) that the old install stays where it is, unused, and names the folder, so you can delete it
yourself.

uv, Python, the log and every step then land in that one folder, and `state.json` lives there. The bootstrap hands the
folder to the core as `--engine-home`. When you chose it (the flag or an answer) it also passes
`--engine-home-chosen`, and the core uses the folder as it is, after the same checks. Otherwise the core works the
folder out again and stops with exit code 2 if the two disagree; the message says how to fix it yourself: run the
installer again with `-EngineHome <folder>` (`--engine-home <folder>`). Preflight shows the folder and where it came
from.

### Where the choice is saved

Only through the engine's own two places, so the engine, the `reel` wrappers and Claude Code all find it:

- Claude Code's `settings.json`: `pluginConfigs["whynot-cut@thewhynot-ai"].options.engine_home`. Claude Code hands it
  to the plugin's hooks, and the SessionStart hook rewrites `~/.whynot-cut/plugin-options.json` from it at the start of
  every session. It is merged like every other settings change: other keys and their order are kept, the original
  bytes are backed up first, and a `settings.json` that is not valid JSON is left untouched (the step turns amber and
  shows the JSON to add by hand).
- the pointer `~/.whynot-cut/plugin-options.json`, in the hook's own format (`clients_root`, `engine_home`, `updated`,
  one per line, UTF-8), so `reel` finds the folder before the first Claude session. A `clients_root` already in it is
  kept, and so is any other key in it.

They are written at the very end, after `state.json`, and only when no step failed (red): an install whose runtime
(or any other step) failed leaves the saved location as it was, so the previous engine home stays the active one; the
checklist's `location` line says so. Both are written only when the folder is not `~/.whynot-cut`, or when one of them
already names another folder
(choosing `~/.whynot-cut` again then sets both back to `""`, which means "the default"). A default install leaves both
files as they are. `~/.whynot-cut` then holds only the pointer. No `WHYNOT_HOME` user variable is set and no shell
profile is changed: a variable would beat the plugin option, so a later change in `/plugin` would be silently
ignored. If `WHYNOT_HOME` (or another engine-home variable) is already set to another folder, the `location` line of
the checklist turns amber and says to remove it.

In the one-line mode (`-Source`), the release zip is cached in `downloads/` of the engine home found the same way
(with `-EngineHome`, after the same `WhyNotCut` subfolder rule), not always in `~/.whynot-cut`.

A sandbox (`--home`) finds its engine home the same way, but only from its own `<dir>/.whynot-cut/plugin-options.json`
and `<dir>/.claude/settings.json`, never from the variables of the machine running it, and a chosen folder must be
inside `<dir>`.

### A saved engine home in the wrong place

An engine home that was not chosen in this run but found as described above (a variable, `plugin-options.json` or
`settings.json` names it) is used as it is - except `~/.whynot-cut` itself - unless it is:

- a link itself (a junction, symlink, or a drive mounted into a folder): name the real folder;
- a network share or device path (`\\server\share\...`, `\\localhost\C$\...`, `\\.\...`; the long-path form
  `\\?\C:\...` counts as `C:\...`);
- a drive root or a mount point (`D:\`, `/Volumes/<name>`);
- your user folder itself, or Desktop, Documents or Downloads themselves (a folder inside them is fine); on Windows
  also where Windows keeps them (OneDrive Known Folder Move, a moved Documents);
- a folder holding client data: your saved clients folder (`clients_root` in your preferences or in
  `plugin-options.json`), or a folder that holds it, or a folder with a `.whynot-client` marker in it or up to three
  levels below;
- a folder too big to check for that: more than 5000 files and folders within three levels (a footage folder).

Every comparison is made both as the folder is written and with every link on the way resolved (a link to Documents
is Documents), and without regard to upper / lower case on Windows and macOS. `-EngineHome` / `--engine-home` naming
that same saved folder is checked the same way (it is that folder, used as it is), also before any download.

`~/.whynot-cut` itself is never refused by these rules, and it may be a link (a junction or symlink) to a folder on
another drive, for example `D:\ClaudeData\whynot-cut-home` (Addendum F): the installer uses it through the link, and
`-Uninstall -RemoveEngine` deletes only WhyNot Cut's own entries inside it; the link and the folder it points to
always stay, with anything else in them. Where such a link points is checked with all the rules above (a link to
Documents, your user folder, a drive root or a client folder is refused at install and at uninstall, before anything
is downloaded or deleted): remove the link, or point it at a folder of its own. Because the link's name is
WhyNot Cut's, its target is also placed like a folder you choose: it must not hold your user folder, lie inside a
client folder or your clients folder, or already hold other files unless it is a WhyNot Cut engine folder (an empty
folder, or your old WhyNot Cut folder, is fine). A link whose folder is missing (an unplugged drive) is refused with
"reconnect the drive or remove the link". If the refused folder is your old WhyNot Cut folder with files of your own
in it, move those files out and run the installer again.

What `-Uninstall -RemoveEngine` keeps by default - a folder holding only `models/` with the Whisper model in WhyNot
Cut's own store (`models/models--<repo>`, one per `models.*.repo` in `components.json`) - still counts as a WhyNot Cut
engine folder, so installing into it again works (through the link too) and reuses the model. A `models` folder
of your own (anything else inside it) does not count: the name alone is never trusted.

Uninstall checks the engine home the same way before it writes anything (its log, uv, Python), also when
`-EngineHome` / `--engine-home` names that same folder (the linked `~/.whynot-cut` is then that home, used through
the link as above); a WhyNot Cut engine folder is not refused for client folders inside it, because uninstall deletes
only WhyNot Cut's own entries. `-Uninstall -EngineHome <folder>` naming any other folder needs that folder to exist,
not be a link, pass the same placement rules, and be a WhyNot Cut engine folder (or what an uninstall left of one).
When it is not, but its `WhyNotCut` subfolder is - the folder an install with `-EngineHome <folder>` made inside your
user folder, Desktop, Documents, Downloads or a folder holding your files - the uninstall uses that subfolder and
says so (English and Arabic). Anything else stops with exit code 2 and "Nothing was changed", before any log,
download or delete. Every path is read in its plain form first: a saved `~/.whynot-cut/`, `~/.whynot-cut/.` or
`<home>/x/../.whynot-cut` is `~/.whynot-cut`. Right before python/ and bin/ are deleted after the uninstall, a linked
`~/.whynot-cut` is resolved again; if it points somewhere else than when the uninstall started, nothing is deleted
and the uninstall says so. (A program that changes the link in the instant between that check and the delete is
not covered; nothing on a normal PC does that.)

Then the install stops with exit code 2 before anything is downloaded, both bootstraps and the core alike, and says
how to fix it (in English and Arabic): **run the installer again with -EngineHome <folder> / --engine-home <folder>**,
naming a folder of its own (for example `C:\WhyNotCut` or `~/WhyNotCut`); that folder is then saved in place of the
old one. A genuine 2.x or 3.0 engine home anywhere else is upgraded in place, with its models. Uninstall stops the
same way, with nothing changed, except for client folders inside a WhyNot Cut engine folder (see above).

## What happens

1. **uv.** The pinned uv from `components.json` (`uv.assets.<platform>`) is downloaded into `~/.whynot-cut/downloads/`,
   checked against its sha256, and unpacked to `~/.whynot-cut/bin/uv(.exe)`. If uv is already there at the pinned
   version, nothing is downloaded.
2. **Python.** The bootstrap runs `uv python install <runtime.python> --no-bin --no-registry` into
   `~/.whynot-cut/python`. This adds no `~/.local/bin` shim and no registry key. It uses `UV_PYTHON_INSTALL_DIR`,
   `UV_CACHE_DIR`, `UV_NO_CONFIG=1`, `UV_PYTHON_PREFERENCE=only-managed` and `UV_NO_MODIFY_PATH=1`. Then
   `uv python find` names the interpreter.
3. **The core.** The bootstrap runs `<python> -I -B -X utf8 installer/core/wnc_install.py install ...`, which runs
   these steps:
   - preflight, then the questions, only on the Customise path (`--customise`; see [No questions by
     default](#no-questions-by-default)): the Whisper (transcription) model, the language and the clients folder,
     each preselected; without Customise the answers below are taken as they are. The suggested
     clients folder is `D:\WhyNot Clients` when a `D:` drive exists, else `Documents/WhyNot Clients`; when Documents
     is synced to OneDrive or iCloud Drive it is `~/WhyNot Clients` instead (raw footage should not go to the cloud),
     and the question says why. A folder you saved in your preferences, or `--clients-folder`, always wins. The model
     question lists the four models with their download size, in English and Arabic:

     | Model | About | |
     |---|---|---|
     | `large-v3` | 2.9 GB | best accuracy (the default, on every computer) |
     | `large-v3-turbo` | 1.6 GB | faster, a little less accurate |
     | `medium` | 1.5 GB | smaller, less accurate |
     | `small` | 0.5 GB | smallest, least accurate |

     Answer with the number or the name; Enter keeps the model in brackets. That is the model saved in your
     preferences when there is one (a re-install keeps your choice), else `large-v3`. `-Model` / `--model` answers
     it, and `-Yes` takes the default. Every choice defaults to the strongest option: `large-v3`, the GPU libraries
     whenever an NVIDIA GPU is there, and the full font set. The chosen model is written into your preferences
     (`reel settings --set whisper_model=...`);
   - the runtime (from `setup/locks/`), ffmpeg, Git Bash (Windows), GPU libraries (NVIDIA);
   - the Claude Code plugin and settings, the Adobe panel, fonts, preferences;
   - the download of the chosen Whisper model, which keeps going in the background;
   - `state.json`, `reel doctor`, and the checklist; only now, when no step failed, is a chosen engine home saved
     (the checklist's `location` line, see above);
   - opening Claude with `/whynot-cut:start`. On macOS the end of the install also says (in English and Arabic): the
     first time Claude opens files in Documents or on an external drive, macOS asks for permission; click **Allow**.

The runtime is built in place under the lock file `runtimes/.<id>.building`, which `reel setup` uses too. Both write
their process id first. A lock whose process is no longer running (for example, the installer window was closed
during `pip sync`) is taken over at once; a lock older than 2 hours is taken over too. Otherwise the step is amber
and names the lock file and its age.

Downloads use the system `curl` first. When curl cannot reach the server (exit 5, 6 or 7: proxy or host not found, no
connection), that try is repeated with Python's own downloader, which reads the system proxy settings.

## What the installer never does

- It never asks for admin rights or a UAC prompt. It never writes to HKLM or Program Files. The only registry values
  it writes are per-user font entries under `HKCU\...\Fonts`.
- It never switches on Adobe's debug mode for unsigned panels. An unsigned panel is reported, not installed.
- It never creates, moves or deletes client folders. Uninstall leaves anything marked `.whynot-client` alone, and it
  never follows a link or junction.
- It never overwrites `~/.claude/settings.json`. The installer merges into it, and makes a timestamped backup first
  whenever something changes. If the file is not valid JSON, the installer leaves it untouched and shows the lines to
  paste in by hand.
- It never uses a download that is not pinned to an exact URL and sha256. A placeholder pin (`"<release>"`) is skipped
  and the reason is given; the installer never guesses one.

## Logs

Every run that is not a dry run writes one log, which the bootstrap and the core share:
`~/.whynot-cut/logs/install-YYYYmmdd-HHMMSS.log` (or `uninstall-...` for an uninstall). The checklist is also saved as
`~/.whynot-cut/logs/install-checklist.json`. The background model download logs to `logs/model-download-<time>.log`.
On Windows, `~` is `%USERPROFILE%`. With an engine home in another folder, `logs/` (and `state.json`) are in that
folder.

## Uninstall

```powershell
powershell -ExecutionPolicy Bypass -File whynot-cut\installer\install.ps1 -Uninstall [-RemoveEngine] [-RemoveModels]
```
```bash
bash whynot-cut/installer/install.sh --uninstall [--remove-engine] [--remove-models]
```

Uninstall runs on the Python that is already in `~/.whynot-cut/python`, so it downloads nothing. It downloads uv and
Python only when that Python is gone. It runs these steps in order:

| Step | What it removes |
|---|---|
| `plugin` | It checks `~/.claude/settings.json` first and backs up the original bytes. Then it runs `claude plugin uninstall whynot-cut@thewhynot-ai --scope user` and `claude plugin marketplace remove thewhynot-ai`. Last, it removes our entries from `settings.json`. The Git Bash entry (`CLAUDE_CODE_GIT_BASH_PATH`) stays as long as the Git folder WhyNot Cut installed stays; both go together, with `-RemoveEngine`. A plugin the install switched off (`reel-editor@*`) is switched back on. If `settings.json` is not valid JSON, nothing is changed and the Claude Code CLI does not run; the step shows what to remove by hand. |
| `adobe` | The CEP panel folder the install recorded, and the UXP panel through Adobe's plugin installer (`/remove <id>`). If Premiere Pro or After Effects is running, nothing is removed; close them and run uninstall again. |
| `fonts` | Only the font files the install recorded, and only their own registry values. A font you had before stays. |
| `marketplace` | `~/.whynot-cut/marketplace` (and its `.new` / `.prev` copies). |
| `engine` | Only with `-RemoveEngine` / `--remove-engine`, in every engine home (`~/.whynot-cut` too): **only what WhyNot Cut puts there** - `bin`, `python`, `runtimes`, `current`, `ffmpeg`, `cuda`, `bridge`, `state.json`, `logs`, `cache`, `downloads`, `fonts`, `marketplace` (and `.new` / `.prev`), `.delete-after-exit`, the engine's `venv`, `ppro-queue`, `ppro-scripts`, `ae-queue`, `ae-scripts`, `ae-probe`, `ae-capabilities.json`, `bench`, `tmp`, and their set-aside leftovers. Anything else in the folder is yours: it is kept and listed in the summary, and the folder itself is removed only when it is then empty. `models/` stays unless you add `-RemoveModels`; `library/` (your licensed motion and illustration packs) always stays; `plugin-options.json` follows the pointer rules below. Plus `%LOCALAPPDATA%\WhyNotCut\git` and then its Git Bash entry in `settings.json`. It refuses a folder that is not a WhyNot Cut engine home by content (see the location rules above). Names are compared exactly: your `Bin` or `Models` is not `bin/` or `models/` and stays, also on Windows and macOS disks that ignore case; the install script's final delete of `python/` and `bin/` refuses an entry whose name differs in case. If the `adobe` or `fonts` step could not remove something (a running Premiere Pro, a font in use), a small `state.json` keeps that record, so running uninstall again finishes it. With `-RemoveModels` / `--remove-models` the models go too. `-RemoveModels` on its own deletes only `models/`. If files are locked while the background Whisper model download is still running, the step says so and names its log. |

**An engine home in another folder.** Uninstall asks nothing: it finds the engine home exactly as the install does
(the variables, then `plugin-options.json`, then `settings.json` `pluginConfigs`), or takes `-EngineHome <dir>` /
`--engine-home <dir>`. `-RemoveEngine` removes WhyNot Cut's own entries from that folder with the same rules as
above (anything else stays and is listed; `models/` and `library/` stay unless asked; a client folder is never
touched). Once nothing is left to retry, it also removes the saved choice, for every engine home (`~/.whynot-cut`
included): `engine_home` from our `pluginConfigs` options in `settings.json` (with a backup), and from the pointer
`~/.whynot-cut/plugin-options.json` - the whole file when it holds nothing else; when it still holds a
`clients_root` (or another key) the file stays with `engine_home` set to `""` - then `~/.whynot-cut` itself, but only
when it is then empty. Both are removed only while they still name that folder (or `""`). If `models/` or
`library/` stayed in the folder, the summary says how to use it again: install with `-EngineHome <that folder>`. If
something could not be deleted, the saved choice stays, so the next uninstall finds the same folder.

Uninstall never touches:

- your clients folder (`clients_root` in your preferences) or any folder that holds a `.whynot-client` file, even
  inside `~/.whynot-cut`;
- your preferences file `~/.claude/whynot-cut.local.md`. It is kept and named in the summary, so a later install
  uses it again;
- fonts, registry values or Adobe folders the install did not record;
- the target of a link or junction inside `~/.whynot-cut`. The link itself is removed, never followed.

With `-RemoveEngine`, the Python that runs the uninstall cannot delete itself, because Windows locks a running
`python.exe`. So the core lists `python/` and `bin/` in `~/.whynot-cut/.delete-after-exit`, and the install script
deletes them once the core has finished. The script accepts only `python/` and `bin/` from that list (and
the engine home itself, only once it is then empty: the core lists it only when nothing else is left); any other
line is refused and reported.
The uninstall log is in `logs/`, so it is deleted with the engine home; the summary stays on the screen.

## Sandbox and test mode

`-Home <dir>` / `--home <dir>` turns the run into a sandbox. Before anything is downloaded, the bootstrap points
`HOME`, `USERPROFILE`, `APPDATA`, `LOCALAPPDATA`, `CLAUDE_CONFIG_DIR` and `WHYNOT_HOME` into `<dir>`. It then passes
`--home <dir>` to the core. So uv, Python, the engine home, `.claude/settings.json`, fonts and the Adobe folders all
land under `<dir>`. A sandbox never reads or writes the registry, never opens Claude or Adobe's installer, only runs
a Claude Code CLI named by `WNC_CLAUDE_CLI`, and never looks at `D:\`. Combined with `-DryRun`, it leaves `<dir>` empty.

Test hooks, honoured only together with `--home`:

| Variable | Effect |
|---|---|
| `WNC_TEST_UV` | A uv stand-in, such as `tests/fixtures/installer/fake_uv.cmd`, `.sh` or `.py`. It is used for `uv python install/find` and by the core. The real uv archive is still downloaded and verified first. |
| `WNC_TEST_PLATFORM` | `win-x64`, `mac-arm64` or `mac-x64`. It lets Git Bash run the macOS path in tests; without it, `install.sh` on Git Bash says "use install.ps1" and exits 2. |
| `WNC_CLAUDE_CLI` | A Claude Code CLI stand-in (`tests/fixtures/installer/fake_claude.*`). |
| `WNC_TEST_ANSWERS` | A text file with one answer per line, read instead of the keyboard: first the bootstrap's location question, then (from the line after the bootstrap's last one, which the bootstrap passes on as `WNC_TEST_ANSWERS_AT`) the core's Customise questions. |
| `WNC_TEST_KEYS` | Stands in for the keyboard during the countdown, as if a person were at the console: `C` (Customise), another key (go on at once), or `none` (nobody presses). |
| `WNC_TEST_COUNTDOWN_S` | With `WNC_TEST_KEYS`: the seconds the countdown waits in all (`0` = none). |
| `WNC_TEST_MOUNTS` | Folders (separated by `;`) that the bootstraps' engine-home check treats as mount points, like a USB drive. |
| `WNC_TEST_FREE_GB` | The free space (GB) the bootstrap's location check sees. |

The installer's own tests are in `tests/test_installer.py` (run with `bash tools/test.sh -p test_installer.py`). They
run both front ends end to end against a fixture plugin, served from a local `http.server`, with a home folder whose
name has a space and Arabic letters.

Optional checks in the same file, skipped when their tool or switch is missing. The two lint variables are not named
`WNC_*` on purpose: other suites check that no `WNC_*` variable reaches the engine, so exporting them for a full run
is safe.

| Variable | Check |
|---|---|
| `WHYNOTCUT_PSSA_PATH` | Path to `PSScriptAnalyzer.psd1` (otherwise the PowerShell module path is used): no `Error` finding in the `.ps1` files. |
| `WHYNOTCUT_SHELLCHECK` | Path to `shellcheck` (otherwise `PATH`): `shellcheck` exits 0 on the `.sh` files. |
| `WNC_INSTALLER_LIVE=1` | The live smoke, with real network: the pinned uv download, then `uv python install --no-bin --no-registry`, `uv venv` and `uv pip sync --require-hashes` of `tests/fixtures/installer/live_lock.txt` (six), all through the runtime step in a temp home. |

The PowerShell parser (`[System.Management.Automation.Language.Parser]::ParseFile`) and `bash -n` always run when
the shell is there.

## Release tool (stub)

`python tools/release.py components --check` lists every placeholder (`"<release>"` or `null`) left in
`setup/components.json`. `python tools/release.py components --fill-artefacts` pins the panel files found in
`whynot-cut/adobe/`: `*.zxp` goes into `bridge.cep.zxp` + `bridge.cep.sha256`, and `*.ccx` into `bridge.uxp.ccx` +
`bridge.uxp.sha256`. Everything else stays as it is. The full release pipeline (T7.6) is not part of the installer
track. The docstring of `tools/release.py` describes the release index that the one-line mode reads.

## Verified / Not verified

### Verified

- **uv and Python, live.** The pinned uv 0.13.0 (URL and sha256 from `components.json`) was downloaded for real.
  `uv python install 3.12.15 --no-bin --no-registry` installed the pinned Python into a temp home. A runtime was
  built from a hashed lock (`uv pip sync --require-hashes`) and imported its package. Afterwards the real profile had
  no `~/.local/bin/python3.12.exe` and there was no `HKCU\Software\Python\Astral` key: no side effects (the
  `WNC_INSTALLER_LIVE=1` test, and earlier checks by the controller).
- **Git for Windows.** The real PortableGit 7z self-extractor unpacks into paths with spaces and Arabic letters. Under
  a very long base path it fails (Windows MAX_PATH) after a partial extraction. The `gitbash` step then cleans up
  its staging folder and turns amber with the download link, so a broken Git is never set.
- **Windows front end.** `install.ps1` and `bootstrap.ps1` under Windows PowerShell 5.1, end to end in a sandbox home
  (uv download and sha256, the core, one log, the real `~/.claude` and `~/.whynot-cut` untouched), plus the one-line
  modes, uninstall and `-RemoveEngine`.
- **macOS script, on Windows.** `install.sh` and `bootstrap.sh` were run under Git Bash with
  `WNC_TEST_PLATFORM=mac-arm64`, end to end the same way.
- **Static checks.** The PowerShell parser and PSScriptAnalyzer 1.25.0 found no errors in the `.ps1` files.
  `bash -n` and shellcheck 0.11.0 are clean on the `.sh` files.

### Not verified

- A real Mac run. Not yet checked there: reading JSON through JXA (`osascript -l JavaScript`), `shasum` and `tar`
  from macOS, and questions asked through `/dev/tty`, including the countdown's `read -t 1 -n 1` (and its install
  size, computed with JXA).
- The countdown with a real keyboard: the tests drive it through `WNC_TEST_KEYS`; `[Console]::KeyAvailable` in a
  real PowerShell console window (and in hosts such as ISE or VS Code) was not pressed by hand.
- Real per-user font registration on Windows (`HKCU\...\Fonts` values and the font-change broadcast). The tests use a
  fake `LOCALAPPDATA` and a JSON stand-in for the registry.
- Adobe's plugin installer (UPIA) installing or removing the UXP panel.
- Installing the plugin with the real Claude Code CLI (`claude plugin marketplace add` / `plugin install`). The tests
  use a stand-in CLI.
- Signed ZXP and `.ccx` panels: they arrive with Phase 6. Until then the `adobe` step is skipped.
- A clean standard-user Windows account with no Python and no Git (Gate 7, H10).
- Windows Smart App Control (SAC) switched on.
