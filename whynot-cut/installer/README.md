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

This removes the plugin, the Adobe panel, the fonts the installer added, and its settings entries. The installer
removes these by undoing its own `settings.json` merge, using the backup rules above. The Whisper models and the engine
home stay unless you ask for them to go.

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
