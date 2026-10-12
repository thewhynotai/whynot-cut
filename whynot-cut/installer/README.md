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

### One line (future: needs hosting, H3)

```powershell
irm https://thewhynot.ai/install.ps1 | iex
```
```bash
curl -fsSL https://thewhynot.ai/install.sh | bash
```

In this mode the script has no folder of its own. It fetches the release named by the release index (`release.index_url`,
which the release tool fills in). Until that index is hosted, the script prints this line in English and Arabic and
exits with code 2:

> hosting is not ready yet (H3): download the zip, extract it, run `installer\install.ps1`

You can point a one-liner at a specific release zip, either a file or an https URL, together with its sha256:

```powershell
& ([scriptblock]::Create((irm https://thewhynot.ai/install.ps1))) -Source https://.../WhyNotCut-3.0.0.zip -SourceSha256 <64 hex>
```
```bash
curl -fsSL https://thewhynot.ai/install.sh | bash -s -- --source https://.../WhyNotCut-3.0.0.zip --source-sha256 <64 hex>
```

The installer copies or downloads the zip into `~/.whynot-cut/downloads/release-<first 8 of the sha256>/` and checks it
against the sha256. A mismatch deletes the file and exits with code 3. It then extracts the zip into `x/` next to it,
and `x/whynot-cut-marketplace/whynot-cut` becomes the plugin folder.

## Options

| Windows (`install.ps1`) | macOS (`install.sh`) | Meaning |
|---|---|---|
| `-Home <dir>` | `--home <dir>` | Sandbox or test mode. Everything goes under `<dir>` (see below). |
| `-DryRun` | `--dry-run` | Says what would happen and writes nothing: no log, no folder. |
| `-Yes` | `--yes` | Asks no questions and takes the defaults. |
| `-ClientsFolder <dir>` | `--clients-folder <dir>` | The folder that holds the client folders. The folder itself is never created. |
| `-Language ar\|en` | `--language ar\|en` | Language of the answers (default `ar`). |
| `-Channel stable\|beta` | `--channel stable\|beta` | Release channel (default: the one in `components.json`). |
| `-Components <file>` | `--components <file>` | Use another `components.json` (tests, release checks). |
| `-Skip a,b` | `--skip a,b` | Skip core steps by name: `preflight questions runtime ffmpeg gitbash gpu claude adobe fonts settings model state doctor launch`. |
| `-Uninstall` | `--uninstall` | Remove WhyNot Cut for this user. |
| `-RemoveEngine` | `--remove-engine` | With uninstall: also delete `~/.whynot-cut` (runtimes, ffmpeg, ...). |
| `-RemoveModels` | `--remove-models` | With uninstall: also delete the Whisper models (about 3 GB each). |
| `-Source <zip\|url>` | `--source <zip\|url>` | One-line mode: the release zip to install from. |
| `-SourceSha256 <hex>` | `--source-sha256 <hex>` | The sha256 of that zip. It is required with `-Source`. |

Exit codes:

| Code | Meaning |
|---|---|
| 0 | Done. Some rows may be amber or skipped; the checklist says why. |
| 1 | At least one step failed (red). |
| 2 | Cannot start, for one of these reasons: wrong OS or CPU, Git Bash on Windows, no hosting yet, a bad option, an unreadable `components.json`, or too little free space. |
| 3 | A download or a bootstrap step failed: uv, Python, or a sha256 mismatch. The message names the file and the log. |

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
   - preflight, then the two questions (clients folder and language);
   - the runtime (from `setup/locks/`), ffmpeg, Git Bash (Windows), GPU libraries (NVIDIA);
   - the Claude Code plugin and settings, the Adobe panel, fonts, preferences;
   - the Whisper model download, which keeps going in the background;
   - `state.json`, `reel doctor`, and the checklist;
   - opening Claude with `/whynot-cut:start`.

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
On Windows, `~` is `%USERPROFILE%`.

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
| `engine` | Only with `-RemoveEngine` / `--remove-engine`: everything in `~/.whynot-cut` except `models/`, plus `%LOCALAPPDATA%\WhyNotCut\git` and then its Git Bash entry in `settings.json`. It refuses a folder that holds none of `state.json`, `current` or `bin/uv(.exe)`. If the `adobe` or `fonts` step could not remove something (a running Premiere Pro, a font in use), a small `state.json` keeps that record, so running uninstall again finishes it. With `-RemoveModels` / `--remove-models` the models go too. `-RemoveModels` on its own deletes only `models/`. |

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
`~/.whynot-cut` itself, only once it is empty); any other line is refused and reported.
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

The installer's own tests are in `tests/test_installer.py` (run with `bash tools/test.sh -p test_installer.py`). They
run both front ends end to end against a fixture plugin, served from a local `http.server`, with a home folder whose
name has a space and Arabic letters.

Optional checks in the same file, skipped when their tool or switch is missing:

| Variable | Check |
|---|---|
| `WNC_PSSA_PATH` | Path to `PSScriptAnalyzer.psd1` (otherwise the PowerShell module path is used): no `Error` finding in the `.ps1` files. |
| `WNC_SHELLCHECK` | Path to `shellcheck` (otherwise `PATH`): `shellcheck` exits 0 on the `.sh` files. |
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
  from macOS, and questions asked through `/dev/tty`.
- Real per-user font registration on Windows (`HKCU\...\Fonts` values and the font-change broadcast). The tests use a
  fake `LOCALAPPDATA` and a JSON stand-in for the registry.
- Adobe's plugin installer (UPIA) installing or removing the UXP panel.
- Installing the plugin with the real Claude Code CLI (`claude plugin marketplace add` / `plugin install`). The tests
  use a stand-in CLI.
- Signed ZXP and `.ccx` panels: they arrive with Phase 6. Until then the `adobe` step is skipped.
- A clean standard-user Windows account with no Python and no Git (Gate 7, H10).
- Windows Smart App Control (SAC) switched on.
