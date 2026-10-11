# WhyNot Cut: one-click installer and update path (macOS + Windows)

Research report, 2026-10-11. Scope: the `whynot-cut` Claude Code plugin 2.2.0 (`whynot-cut-marketplace/`), its Python
engine (`~/.whynot-cut`), the WhyNot Cut Bridge (CEP bundle 3.1.0 for Premiere Pro + After Effects) and a planned UXP
plugin for Premiere. Target user: a video editor who is not technical, on macOS (Apple Silicon and Intel) or
Windows 10/11.

Method: the repository and this PC's install were read without changes (read-only); public docs were fetched on
2026-10-11. In this report, **verified** means read in the code, measured on this PC, or quoted from an official page.
**(est.)** marks my own estimate. The sibling report `review/adobe.md` covers the Premiere/AE panel architecture. This
report only covers how that panel gets **installed and updated**.

---

## 0. Executive summary

* Today a new user goes through **12–15 manual steps** before a first edit: get a zip, extract it to a permanent
  folder, register a local marketplace, install the plugin, restart, install Python, let pip download ~400 MB from
  PyPI, run 4 `reg add`/`defaults write` commands for Adobe's PlayerDebugMode, restart Premiere, install fonts by
  hand, download a 2.9 GB model, and (on NVIDIA) download cuBLAS. They see at least 3 restarts, and the Windows Python
  install may bring up a UAC prompt. Updates are manual: re-extract the zip and run 2 CLI commands that desktop-app
  users don't have on PATH.
* The code review found real defects in this flow. On a PC without Python or Git Bash, the read-only **guard hook
  silently does not run** (F1). G67 has a confirmed root cause (F2). The engine runtime isn't versioned against the
  plugin (F9). The bridge writes a file into its own extension folder, which rules out a signed ZXP (F7).
* **Recommendation:** use one per-user **bootstrap core** with no admin rights and no system Python. It has two front
  ends:
  1. **Now, no certificates needed:** a one-line command the editor pastes once, `irm …/install.ps1 | iex` on Windows
     or `curl … | bash` on macOS. Files fetched this way get no Mark-of-the-Web or quarantine flag, so SmartScreen and
     Gatekeeper don't block them.
  2. **Later, with certificates:** a signed Windows Inno Setup `.exe` (per-user) and a notarized macOS installer app in
     a `.dmg`. Both wrap the same core.

  The core does this:
  * installs `uv` and python-build-standalone 3.12 into `~/.whynot-cut`, then syncs a **hash-locked** runtime per
    platform;
  * installs a pinned ffmpeg build;
  * installs the plugin from a **hosted `marketplace.json` URL with an `archive` (zip + sha256) source**, so no git is
    needed, and turns `autoUpdate` on in the user's settings;
  * copies a **signed ZXP** (a self-signed certificate is enough for CEP) into the per-user CEP folder, so
    **PlayerDebugMode is no longer needed**, and installs the UXP `.ccx` via UPIA for Premiere 25.6+;
  * installs the bundled OFL Arabic fonts per user;
  * downloads the Whisper model in the background;
  * opens Claude on `/whynot-cut:start`.
* **Transcription:** keep faster-whisper/CTranslate2 on CUDA for Windows with NVIDIA (measured ~10× real time on an RTX
  4060, about 6 min for a 60-min episode; batched mode is 3–4× faster). Use CPU int8 large-v3-turbo on other Windows
  PCs. Add an **MLX backend for Apple Silicon** (large-v3 or turbo; est. 3–12 min for 60 min). Intel Macs use CPU
  turbo.
* **Certificates:**
  * Apple Developer Program, $99/yr, for a notarized macOS installer.
  * A Windows OV code-signing certificate, about $150–300/yr with a hardware token or cloud HSM. **Azure Artifact
    Signing isn't available to an Egyptian organization or individual.**
  * Adobe signing is free (a self-signed ZXP; independent `.ccx` needs no review).
  * Without certificates, ship the one-liner. It also stays as the fallback.
* **Updates:** the plugin auto-updates through Claude Code. Inside the plugin, a `components.json` pins the runtime
  lock, ffmpeg, bridge protocol and model revisions. A SessionStart hook compares it with `~/.whynot-cut/state.json`
  and asks the editor before running `reel update`. Every component carries a version **and** a protocol number, so a
  mismatch blocks with a clear message instead of failing halfway.

---

## Part A — The current setup flow (read from the code)

### A.1 Components and where they live today

| Component | Where | How it gets there | Size (verified unless est.) |
|---|---|---|---|
| Marketplace + plugin source | `~/.whynot-cut/marketplace` on this PC (`known_marketplaces.json`: `"source": "directory"`) | Editor extracts `whynot-cut-<ver>.zip` (built by `package.py`; top folder `whynot-cut-marketplace/`) | 2.2.0 zip = 1.73 MB (2,321 files) |
| Installed plugin (Claude) | `~/.claude/plugins/cache/thewhynot-ai/whynot-cut/<ver>` (this PC: `2.1.1`, user scope, `installed_plugins.json`) | `claude plugin marketplace add <dir>` + `claude plugin install whynot-cut@thewhynot-ai` | — |
| `reel` CLI | plugin `bin/reel` (bash), `bin/reel.cmd` (cmd/PowerShell) | Claude Code puts the plugin `bin/` on PATH while the plugin is enabled, **for sessions started after install** | — |
| Engine code | plugin `engine/reel/` (inside the versioned cache dir) | Updates together with the plugin | — |
| Engine runtime | `~/.whynot-cut/venv` | `setup/setup_env.py` with **any system Python ≥3.9** → `python -m venv` → `pip install -r setup/requirements.txt` (version **ranges**, not a lock) | "~400 MB"; this PC: venv 24 MB **plus ~500 MB in the system Python's user site** (see F2) |
| ffmpeg | the `imageio-ffmpeg` wheel; macOS symlink `~/.whynot-cut/ffmpeg` | pip | Windows binary 87.6 MB (gyan.dev 7.1 "essentials", `--enable-gpl --enable-version3 --enable-libx264/x265`, verified with `-version`) |
| Whisper model | `~/.whynot-cut/models/models--Systran--faster-whisper-large-v3` | Hugging Face on first transcription or `reel model-download` | 2.9 GB (measured) |
| CUDA cuBLAS (Windows NVIDIA) | `~/.whynot-cut/cuda/bin` | `reel gpu-enable` from NVIDIA's redistributable CDN (sha256-checked; pip fallback ~550 MB) | download ~520 MB; 736 MB on disk (measured) |
| WhyNot Cut Bridge (CEP) | `%APPDATA%\Adobe\CEP\extensions\ai.thewhynot.cut.bridge` / `~/Library/Application Support/Adobe/CEP/extensions/…` | `reel setup` / `reel ppro-install` copies `templates/premiere/cep_bridge` and writes `bridge-config.json` **into** it | manifest: PPRO `[22.0,99.9]`, AEFT `[24.0,99.9]`, CSXS 11.0 |
| PlayerDebugMode | HKCU `Software\Adobe\CSXS.<n>` / `com.adobe.CSXS.<n>` | **The editor** runs 4 commands (CSXS 11–14). `hooks/guard.py` blocks Claude from writing them | this PC: only `CSXS.12` exists (Premiere Pro 2026, v26.5.2) |
| Bridge job scripts | `~/.whynot-cut/ppro-scripts`, `ae-scripts`, queues `ppro-queue`, `ae-queue` | `sync_scripts()` before every job (sha256 compare) | — |
| Preferences | `~/.claude/whynot-cut.local.md` (or nearer) | `/whynot-cut:start` → `reel settings --init` | — |
| Hooks | `hooks/hooks.json` → `bash "${CLAUDE_PLUGIN_ROOT}/hooks/run_python.sh" …guard.py / session_context.py` | Load with the plugin. `run_python.sh` uses **the first system `python3/python/py`**, and if none is found it prints a warning and **exits 0** | — |
| Brand fonts | client `assets/Fonts` | The editor installs them by hand (double-click / right-click → Install) | — |

### A.2 How the plugin is installed today

1. The zip comes from a shared drive or chat. The editor extracts it to a folder that must stay put. On this PC it is
   `~/.whynot-cut/marketplace` (per the user's memory notes, this folder "is the update source, keep it").
2. Register the marketplace: `/plugin marketplace add "<path>"` in a terminal session, or
   `claude plugin marketplace add <path>` from a shell. The `README` also says "In the desktop app: + › Plugins › Add
   plugin with the same folder". But the desktop **Add plugin** browser "shows available plugins from your configured
   marketplaces" ([desktop docs](https://code.claude.com/docs/en/desktop)). On this PC an older upload sits in a
   separate `local-desktop-app-uploads` marketplace (`reel-editor 1.0.7`, "Locally uploaded plugins via Claude Desktop
   app"), and that path can't receive updates.
3. Install: `claude plugin install whynot-cut@thewhynot-ai` (user scope). In the **desktop app the `claude` CLI isn't
   on PATH**. This PC's CLI is the desktop-bundled
   `%APPDATA%\Claude\claude-code\2.1.295\d2e29494ec83\claude.exe` (verified), and there is no `~/.local/bin/claude`.
4. Update: extract the new zip over the folder, then run `claude plugin marketplace update thewhynot-ai` and
   `claude plugin update whynot-cut@thewhynot-ai`. Third-party and local marketplaces **don't auto-update by default**
   ([plugins/install](https://code.claude.com/docs/en/plugins/install)). A local-directory marketplace also skips the
   pre-install refresh ([plugins/loading](https://code.claude.com/docs/en/plugins/loading)).
5. Start a **new** session, because the plugin `bin/` is added to PATH at session start. G66: a session started before
   the install keeps an old `reel` on PATH, and subagents inherit it.

### A.3 Windows 10/11: from nothing to the first edit, today

| # | Step (who) | Prompts / admin | Download | Where it fails |
|---|---|---|---|---|
| 0 | Claude subscription (Pro/Max/Team), install the **Claude desktop app** (per-user) or the CLI (`irm https://claude.ai/install.ps1 \| iex`). Sign in | none (CLI install "does not need Administrator", [setup](https://code.claude.com/docs/en/setup)) | ~100–200 MB (est.) | Unsupported region / free plan |
| 1 | (Optional, but WhyNot Cut needs it, see F1) **Git for Windows**, which provides Git Bash for the Bash tool and `bash` hooks | standard installer = **UAC** | ~60–70 MB (est.) | Usually skipped; the docs call it optional |
| 2 | Get the zip, then extract it to a **permanent** folder (editor) | Explorer adds Mark-of-the-Web to extracted files (harmless for .md/.py) | 1.7 MB | Extracted into Downloads/OneDrive and later deleted or moved; nested-folder confusion (`whynot-cut-marketplace/whynot-cut/…`) |
| 3 | Register the marketplace + install the plugin (editor types `/plugin marketplace add "<path>"` then `/plugin install whynot-cut@thewhynot-ai`, picks **user** scope) | — | — | The desktop app has no `claude` on PATH; a path with spaces needs quotes; in a session the `--marketplace` form can't contain spaces |
| 4 | **Quit and reopen Claude** (editor) | — | — | G66 (old `reel` first on PATH) |
| 5 | `/whynot-cut:start` → `reel doctor` → "engine missing" → `reel setup` (Claude, after asking) | — | — | `reel.cmd` uses `py -3`, else `python`. The Store `python.exe` alias stub is skipped |
| 6 | **No Python:** the editor runs `winget install Python.Python.3.12` (or the python.org installer, ticking "Add python.exe to PATH"), then **quits and reopens Claude** | python.org per-user install needs no admin, but the py launcher "for all users" can show **UAC** (est.) | ~25–30 MB | No winget (LTSC/older Win10). The desktop app inherits env vars **at launch only**, so a running app doesn't see the new PATH ([desktop](https://code.claude.com/docs/en/desktop)). Python 3.13/3.14 may lack wheels (warned in code) |
| 7 | `setup_env.py`: `python -m venv` + `pip install` | none | "up to ~400 MB" from PyPI | **PyPI was measured at ~40 KB/s on this network** (user memory), which means hours. No lock file and no resume. Antivirus scanning. Corporate proxy. The VC++ runtime is needed by CTranslate2 ([CTranslate2 install](https://opennmt.net/CTranslate2/installation.html)) |
| 8 | `reel setup` copies the CEP bridge into `%APPDATA%\Adobe\CEP\extensions` (Claude; Premiere must be **closed**, because Windows locks the folder) | none | — | Premiere open during install → stale/locked folder |
| 9 | **PlayerDebugMode**: the editor pastes 4 × `reg add "HKCU\Software\Adobe\CSXS.N" /v PlayerDebugMode /t REG_SZ /d 1 /f` into **PowerShell** (not Git Bash, which mangles `/v /d /f`) | none (HKCU) | — | Wrong shell; scary "security downgrade" wording; the guard blocks Claude from doing it |
| 10 | Restart Premiere (+ After Effects), open Window › Extensions › WhyNot Cut Bridge, `reel ppro-status` → `alive` | — | — | Heartbeat stale when a modal dialog is open (documented) |
| 11 | NVIDIA only: `reel gpu-enable` (after asking) | none | ~520 MB (NVIDIA CDN) | No NVIDIA driver with CUDA 12 → silent CPU fallback (5–10× slower) |
| 12 | Whisper large-v3: `reel model-download` in the background, or it downloads at the first transcription | none | **2.9 GB** | HF throttling. An interrupted download is detected as `partial` (good) |
| 13 | Preferences (4 questions), `reel scaffold` first client folder, the editor installs brand fonts by hand (right-click → Install, per-user; "Install for all users" = **UAC**), restarts Premiere/AE | possibly UAC | — | Fonts not seen by Adobe until restart; OneDrive-synced client folders (online-only files) |
| 14 | Drop clips into `data/Raw` → "edit the new videos" | — | — | — |

The editor sees 3–4 app restarts (Claude ×2, Premiere/AE ×1–2), 0–2 UAC prompts, and ~3.5–4 GB of downloads (est.).

### A.4 macOS (Apple Silicon / Intel): from nothing to the first edit, today

| # | Step | Prompts / admin | Download | Where it fails |
|---|---|---|---|---|
| 0 | Claude desktop app (`.dmg`, universal) or CLI (`curl -fsSL https://claude.ai/install.sh \| bash`); sign in | Dragging to /Applications needs admin on a standard account | ~200 MB (est.) | — |
| 1 | Zip downloaded with a browser → **quarantine** xattr; Archive Utility carries it to the extracted files | none for scripts (`bin/reel` is a bash script run by `bash`) | 1.7 MB | Exec bits lost if the zip was re-zipped on Windows (`package.py` sets 0755, so the original zip is fine) |
| 2–4 | Same marketplace/install/restart steps as Windows | — | — | Same as Windows |
| 5 | `reel setup` needs Python ≥3.9. A fresh Mac has only the `/usr/bin/python3` **stub**, which opens the **Xcode Command Line Tools** installer | CLT install dialog (admin password on standard accounts, est.) | CLT ~0.7–1.5 GB (est.) | CLT Python is 3.9.x → `requirements.txt` falls to `numpy==2.0.2`; older pyobjc wheels |
| 6 | pip install (pyobjc 11.1 ×5, Pillow, CTranslate2 CPU, PyAV, …) | none | ~300–400 MB (est.) | Same network issues |
| 7 | CEP bridge → `~/Library/Application Support/Adobe/CEP/extensions`; ffmpeg symlink into the engine home | none | — | — |
| 8 | PlayerDebugMode: `defaults write com.adobe.CSXS.N PlayerDebugMode 1` ×4 in Terminal. Adobe notes the plist cache may need `killall cfprefsd` or a log-out ([CEP 12 cookbook](https://github.com/Adobe-CEP/CEP-Resources/blob/master/CEP_12.x/Documentation/CEP%2012%20HTML%20Extension%20Cookbook.md)) | none | — | The panel still doesn't load because of the preference cache |
| 9 | Restart Premiere/AE; `reel ppro-status` | — | — | — |
| 10 | **TCC prompts** when Claude/Terminal first touches `~/Documents`, Desktop or external drives (the start skill says to click Allow) | Allow dialogs | — | "Don't Allow" clicked by mistake → silent file errors |
| 11 | Model 2.9 GB. **Whisper runs on CPU on every Mac** (`plat.gpu_info()` → `"macOS: Whisper runs on the CPU"`) | — | 2.9 GB | Slow: large-v3 on CPU ≈ 0.5–2× real time (est.), so a 60-min episode takes ~30 min to 2 h |
| 12 | Fonts: double-click → Font Book → Install (per-user `~/Library/Fonts`) | none | — | — |

### A.5 Findings from the code review (installer-relevant)

* **F1 — Guard and context hooks depend on `bash` and a system Python.**
  * `hooks.json` runs `bash "${CLAUDE_PLUGIN_ROOT}/hooks/run_python.sh" …`.
  * On Windows, Claude Code runs a hook through Git Bash, "or PowerShell when Git Bash isn't installed"
    ([hooks](https://code.claude.com/docs/en/hooks)). So with no Git for Windows the command is `bash …` inside
    PowerShell. It either fails, or it reaches WSL's `bash.exe` if WSL is installed, which is wrong too.
  * `run_python.sh` also needs a system Python 3.8+. On a fresh PC or Mac it prints
    `no Python 3.8+ found on PATH; hook skipped` and **exits 0**.
  * Result: **the read-only protection of client `assets/`/`data/` and the PlayerDebugMode block are OFF exactly on
    new machines**, and nobody is told.
* **F2 — G67 root cause confirmed on this PC.**
  * `~/.whynot-cut/venv/pyvenv.cfg` has `include-system-site-packages = true` (home `C:\Python313`).
  * PIL, av, ctranslate2, faster_whisper and numpy actually live in the **user site**
    `%APPDATA%\Python\Python313\site-packages`. The venv itself holds only arabic_reshaper, bidi, freetype, pypdf and
    uharfbuzz.
  * `python -I` implies `-s` (no user site), so the heavy packages disappear.
  * A self-contained runtime with no `--system-site-packages` removes this whole class of bug.
* **F3 — The runtime isn't reproducible.**
  * `requirements.txt` uses ranges (`ctranslate2>=4.6,<5`, `av>=14,<21`, `numpy>=2.1,<3`, …) with no hashes.
  * Two editors installing a week apart can get different engines, and pip resolution happens on the user's machine.
* **F4 — Update skew between the plugin and the venv.**
  * Engine code updates with the plugin, but the venv is only repaired when an import fails
    (`check_modules` checks importability, not versions).
  * A plugin update that needs `ctranslate2>=4.7` would run against 4.6 without warning.
* **F5 — Bridge version skew.**
  * `BRIDGE_VERSION = "3.1.0"` is a constant in `ppro_bridge.py`. An older plugin's `reel setup` would downgrade a
    newer bridge (fixed by the downgrade guard).
  * There is no **protocol** number. The engine can't tell whether a bridge speaks the job format it sends.
* **F6 — PATH timing (G66).**
  * PATH is fixed when a session starts, and the desktop app reads environment variables when it launches.
  * Any install step that changes PATH (Python, Git) needs an app restart. The current flow has two.
* **F7 — `bridge-config.json` is written into the extension folder.** That prevents signing: a signed CEP extension
  must stay byte-identical to what was signed (see B.5). Move the config to the engine home, where the panel can find
  it via Node `os.homedir()`.
* **F8 — PlayerDebugMode scope.**
  * The code loops over CSXS 11–14. Premiere/AE 25+ use CEP 12 (cookbook table), and this PC only has `CSXS.12`.
  * Setting the flag turns on **every** unsigned extension for that CSXS version. It is a real security downgrade,
    and the docs rightly say so.
* **F9 — No component manifest.** Plugin 2.2.0, bridge 3.1.0, venv (unversioned) and models (unpinned HF revision) have
  no shared compatibility record. `reel doctor` can't say "your engine is too old for this plugin".
* **F10 — ffmpeg licence.** The Windows `imageio-ffmpeg` binary is a **GPLv3** build with libx264/x265. Today the user
  downloads it from PyPI themselves. Once an installer *ships* ffmpeg, The Why Not AI becomes the distributor (B.3).
  The engine really uses `libx264` (`preview_video.py`, `reels.py`, `motion_render.py`, `motion_animatic.py`).
* **F11 — Org distribution blocker.** claude.ai/Cowork and organization sync "don't install a plugin that has a
  top-level `bin/` directory" ([components](https://code.claude.com/docs/en/plugins/components)). Fine for Claude Code
  marketplaces. It matters only if the owner later wants claude.ai org distribution.
* **F12 — Proprietary licence.** `LICENSE` says "All rights reserved". A **public** GitHub marketplace isn't an option.
  A private one needs git credentials that a non-technical editor doesn't have (B.1).
* **F13 — Windows Smart App Control (SAC).** On Windows 11 machines with SAC on, unsigned `python.exe`, `.pyd`
  and `.dll` files can be blocked even when they weren't downloaded by a browser. SAC "evaluates trust and signatures
  of all code loaded", and a KiCad user saw `_ctypes.pyd` blocked
  ([textslashplain](https://textslashplain.com/2026/04/28/smart-app-control/),
  [KiCad forum](https://forum.kicad.info/t/windows-11-smart-app-control-sac-incompatibility/39473)). This risk also
  applies to the current pip venv. The doctor must detect it.
* **Good already:**
  * the idempotent `setup`/`doctor` split with `fixes[].who`;
  * sha256-checked cuBLAS from NVIDIA's CDN;
  * resumable model download with `partial` detection;
  * the bridge downgrade guard;
  * per-user CEP install (no admin);
  * legacy-home reuse (`.reel-editor`);
  * a stable engine home outside the versioned plugin dir.

---

## Part B — Research

### B.1 Installing and updating a Claude Code plugin without interaction

**Commands** ([plugins/install](https://code.claude.com/docs/en/plugins/install),
[cli-reference](https://code.claude.com/docs/en/plugins/cli-reference)):

* `claude plugin marketplace add <source>` takes:
  * GitHub `owner/repo[#ref]`;
  * any git URL (`https://…git#ref`, `git@host:path`);
  * a local directory or `marketplace.json` file;
  * an `https://…/marketplace.json` URL.

  It writes the marketplace into **user settings** (`extraKnownMarketplaces`).
* `claude plugin install <name>@<marketplace> [--scope user|project|local] [--config KEY=VALUE]… [--json] [-y]`.
  User scope is the default.
  * `--config` sets the plugin's `userConfig` options (WhyNot Cut declares `clients_root` and `engine_home`). The
    shell command never prompts for them.
  * `--json` prints one result object on the last line.
* One-step add + install: `claude plugin install whynot-cut --marketplace <source>` (shell, **v2.1.292+**; this PC's
  bundled CLI is 2.1.295). In a session: `/plugin install whynot-cut --marketplace <source>` (v2.1.275+, the source
  can't contain spaces).
* `claude plugin update <plugin>@<mkt>`, `claude plugin list --json`, `claude plugin configure <p> --values-stdin`,
  `claude plugin validate --strict`.
* Plugins installed from the shell "load the next time you start Claude Code, or when you run `/reload-plugins`".

**Sources that need no git account.** This matters because the editor has no GitHub credentials and the code is
proprietary ([host-marketplace](https://code.claude.com/docs/en/plugins/host-marketplace),
[marketplace-reference](https://code.claude.com/docs/en/plugins/marketplace-reference)):

* **Hosted `marketplace.json` URL** plus plugin entries with an **`archive` source** (`{"source":"archive","url":"https://…zip","sha256":"…"}`, v2.1.224+):
  * "Users need neither `git` nor an account, only network access to the URL".
  * Limits: zip ≤ 256 MiB, ≤ 1 GiB unpacked, 120 s server response, ≤ 5 HTTPS redirects.
  * A URL marketplace can't use relative-path entries.
  * `headers` (or a `headersHelper` command) on the marketplace `url` source are sent with archive downloads from the
    same origin. That gives a per-customer token without git.
* Private GitHub works only with the user's own stored git credentials (no prompts; SSH key in agent, or `gh auth
  setup-git`). Background updates fail quietly without them.

**Auto-update** ([plugins/loading](https://code.claude.com/docs/en/plugins/loading)):

* Off by default for third-party marketplaces, and "`marketplace.json` has no field to turn it on".
* Precedence:
  1. `autoUpdate` on the `extraKnownMarketplaces` entry in **a settings file**;
  2. the `/plugin` › Marketplaces toggle;
  3. the default.

  So an installer can write `"autoUpdate": true` into `~/.claude/settings.json`.
* It runs after the first message, after a random delay of up to 10 minutes. The running session keeps the old
  version (`Plugin updated … Run /reload-plugins`).
* A new copy is installed only when the **computed version changes**: `plugin.json` `version` wins, else the entry
  `version`, else the git SHA or archive sha256.
* Disabled by `DISABLE_UPDATES`, `DISABLE_AUTOUPDATER` or `CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC`, unless
  `FORCE_AUTOUPDATE_PLUGINS=1`.
* Old version dirs are cleaned after 14 days. `${CLAUDE_PLUGIN_ROOT}` changes on every version, and durable data
  belongs in `${CLAUDE_PLUGIN_DATA}` (`~/.claude/plugins/data/<id>/`). That folder is **deleted on uninstall unless
  `--keep-data` is passed**, so it isn't a good home for a 3 GB model cache.

**Install without the CLI (settings only)**
([plugins/loading](https://code.claude.com/docs/en/plugins/loading)):

* If settings declare a marketplace that `known_marketplaces.json` lacks, Claude Code fetches it in the background
  after session start, "then reloads plugins and downloads enabled plugins that aren't cached yet".
* External-source plugins are fetched only when **user settings**, `.claude/settings.local.json`, `--settings` or
  managed settings set them `true`.
* So merging `extraKnownMarketplaces` and `enabledPlugins` into `~/.claude/settings.json` installs the plugin on the
  next Claude start, even for desktop-only users. The first session may need `/reload-plugins`.

**Team / org distribution** ([plugins/org](https://code.claude.com/docs/en/plugins/org)):

* Managed settings use `extraKnownMarketplaces` + `enabledPlugins` (+ `autoUpdate`), delivered as server-managed
  (claude.ai admin, Team/Enterprise Owner), an MDM plist / registry string, or a `managed-settings.json` file.
* Allow/block lists: `strictKnownMarketplaces` / `blockedMarketplaces`.
* `CLAUDE_CODE_PLUGIN_SEED_DIR` gives an offline, read-only seed with auto-update forced off.
* Repo-level `.claude/settings.json` marketplaces apply only after the folder-trust dialog. A clients folder could
  carry them, but per-user install is simpler.

**Desktop app** ([desktop](https://code.claude.com/docs/en/desktop)):

* The Code tab's local sessions read the **same settings files** as the CLI. A user-scope install in any surface is
  visible in the others.
* **+ › Plugins › Add plugin** lists plugins from configured marketplaces; Manage plugins enables or disables them.
  There are no plugins in cloud or WSL sessions.
* On Windows the app inherits user/system env vars and doesn't read PowerShell profiles. On macOS it extracts `PATH`
  from the shell profile when launched from the Dock.
* Deep links:
  * Desktop handles `claude://code/new?…&q=<prompt>`. The prefill is documented with the SSH form.
  * The CLI handler `claude-cli://open?cwd=<abs path>&q=<prompt>` is registered only after the first interactive
    prompt ([deep-links](https://code.claude.com/docs/en/deep-links)).
  * Prompts are prefilled, **never auto-sent**. That's fine: the installer can open Claude with `/whynot-cut:start`
    typed in.

**Windows shells** ([setup](https://code.claude.com/docs/en/setup)):

* Git for Windows is "optional". Without it, Claude Code uses the PowerShell tool, and hooks run in PowerShell.
* `CLAUDE_CODE_GIT_BASH_PATH` in settings `env` points Claude Code to a Git Bash that isn't in the default place.
  PortableGit can be extracted per user with no admin
  ([gitforwindows.org](https://gitforwindows.org/zip-archives-extracting-the-released-archives.html)).
* Hook handlers accept `"shell": "bash" | "powershell"` or exec form (`command` + `args`). Exec form on Windows needs
  a real `.exe`, not `.cmd` ([hooks](https://code.claude.com/docs/en/hooks)).

### B.2 Shipping a Python runtime, and the transcription backend per platform

**Option 1: uv + python-build-standalone (recommended).**

* uv installs CPython builds from Astral's python-build-standalone ("self-contained and portable")
  ([uv python versions](https://docs.astral.sh/uv/concepts/python-versions/)).
* `UV_PYTHON_INSTALL_DIR` moves them into the engine home. `--managed-python` / `only-managed` ignores system Pythons,
  which avoids F2.
* The standalone uv installer honours `UV_INSTALL_DIR`, `UV_NO_MODIFY_PATH` and `UV_UNMANAGED_INSTALL` (no profile
  edits, no self-update) ([uv installer](https://docs.astral.sh/uv/reference/installer/),
  [installation](https://docs.astral.sh/uv/getting-started/installation/)). It goes into the user's folders, so no
  admin is needed (inferred from the default per-user locations).
* Plan: `uv pip compile --universal --generate-hashes` → a per-platform lock (win-x64, mac-arm64, mac-x64) →
  `uv pip sync --require-hashes`.
* Updates are incremental: only changed wheels download, from uv's cache. A private wheel mirror (`--index-url` /
  `--find-links` to the owner's CDN) fixes the slow-PyPI problem seen here.
* Size: Python ~30–45 MB and uv ~20 MB (est.). Wheels ≈ 200–250 MB compressed, about 500 MB installed (measured on
  this PC: ctranslate2 60 MB, av+libs 69 MB, cv2 111 MB, onnxruntime 46 MB, imageio_ffmpeg 84 MB, numpy 55 MB, …).
* Caveats:
  * python-build-standalone has documented portability "quirks". Test tkinter-free use, SSL certs, and locale.
  * On Windows 11 with SAC on, its unsigned binaries may be blocked (F13). The same holds for any pip venv.

**Option 2: PyInstaller or Nuitka frozen engine.**

* Pros: no interpreter at all, one folder.
* Cons for this product:
  * per-platform bundles of 0.6–2.5 GB with CUDA (est.), re-downloaded on every engine update;
  * PyInstaller's shared bootloader is a well-known antivirus false-positive trigger
    ([discuss.python.org](https://discuss.python.org/t/pyinstaller-false-positive/43171));
  * on macOS **every** Mach-O must be signed (hardened runtime) and notarized;
  * the engine code would split from the plugin. Today it updates with the plugin for free; frozen, it gets a second
    update channel;
  * `setup_env.py` and the hooks run `python -c …` snippets.
* Verdict: not worth it. Revisit only for a stripped-down UXP-only helper.

**Transcription backends.** faster-whisper README benchmarks
([SYSTRAN/faster-whisper](https://github.com/SYSTRAN/faster-whisper)), 13 min audio:
* large-v2 on an RTX 3070 Ti: fp16 63 s; `batch_size=8` 17 s; int8 batched 16 s.
* small model on an i7-12700K CPU: int8 1 m 42 s; batched 51 s.
* Needs cuBLAS 12 + cuDNN 9; the Windows CTranslate2 wheel needs the VC++ runtime
  ([CTranslate2](https://opennmt.net/CTranslate2/installation.html)).

Other backends:
* MLX Whisper: `pip install mlx-whisper`, word-level timestamps supported, needs ffmpeg
  ([mlx-examples/whisper](https://github.com/ml-explore/mlx-examples/tree/main/whisper)). Community tests put it about
  30–40% faster than whisper.cpp on Apple Silicon for the same model
  ([Simon Willison](https://simonwillison.net/2024/Aug/13/mlx-whisper/)).
* whisper.cpp: Metal on Apple Silicon "fully on the GPU"; a Core ML encoder ">3× faster" than CPU; CUDA; **Vulkan**
  (cross-vendor GPUs); word timestamps via `-ml 1`; MIT licence ([whisper.cpp](https://github.com/ggml-org/whisper.cpp)).

| Platform | Recommended backend | Default model | 60 min of audio |
|---|---|---|---|
| Windows + NVIDIA (≥6 GB VRAM, driver supporting CUDA 12) | faster-whisper / CTranslate2 CUDA fp16 (current engine) + `BatchedInferencePipeline` for episodes | large-v3 | **~6 min measured** (RTX 4060 ≈ 10× RT, sequential); ~2–3 min batched (est., README ratio 63 s → 17 s) |
| Windows, no NVIDIA | faster-whisper CPU int8 (current); later optional whisper.cpp Vulkan for Intel/AMD GPUs | large-v3-turbo (the `start` skill already recommends it) | large-v3 ≈ 40–90 min, turbo ≈ 15–30 min (est., scaled from the README's CPU row by parameter count) |
| macOS Apple Silicon | **new MLX backend** (`mlx-whisper`, word timestamps). Keep CTranslate2 CPU as the verified fallback | large-v3 (M-Pro/Max) or turbo (base M1/M2) | MLX large-v3 ≈ 5–12 min, turbo ≈ 3–6 min (est.); CTranslate2 CPU ≈ 20–60 min (est.) |
| macOS Intel | faster-whisper CPU int8 | large-v3-turbo | turbo ≈ 30–60 min, large-v3 ≈ 1.5–3 h (est.) |

The estimates must be confirmed with a `reel bench` (5-minute Arabic sample, report RT factor) on each test machine.
An MLX backend needs a parity test against the verified CTranslate2 output on Arabic medical vocabulary: same weights,
glossary `initial_prompt`, word timings and hallucination filter. Ship it behind `transcription.json` `backend: auto`.

### B.3 ffmpeg distribution and licence

* FFmpeg is LGPL 2.1+, but "if those parts [GPL] get used the GPL applies to all of FFmpeg". libx264/x265 builds are
  GPL ([ffmpeg.org/legal](https://ffmpeg.org/legal.html)). The page's LGPL checklist (dynamic linking, source next to
  the binary, credits) is about linking. It doesn't cover shipping a separate GPL executable. GPL "mere aggregation"
  is the usual basis for shipping `ffmpeg(.exe)` next to proprietary software, as long as GPL terms are met for that
  binary: licence text plus the exact source or a written offer.
* Builds:
  * Windows: **BtbN FFmpeg-Builds** in `gpl`/`lgpl` and static/shared variants (daily, version-pinned names), or
    gyan.dev (what imageio-ffmpeg uses) ([BtbN](https://github.com/BtbN/FFmpeg-Builds)).
  * macOS: **Martin Riedl's build server** has Apple Silicon and Intel static builds with checksums, says its binaries
    are signed and installers notarized (2022 statement, re-verify), and plans to drop Intel
    ([ffmpeg.martin-riedl.de](https://ffmpeg.martin-riedl.de/)). evermeet.cx is Intel-only, with "no plan" for arm64
    ([evermeet](https://evermeet.cx/ffmpeg/apple-silicon-arm)).
* System ffmpeg via winget or Homebrew is wrong for this user: it needs Homebrew (admin and CLT) or winget, versions
  drift, and Homebrew's ffmpeg changes underneath you.
* **Recommendation:**
  * Ship a **pinned GPL static build per OS/arch** from the owner's own CDN (mirror plus sha256), with `LICENSE.GPL`
    and a link to the exact source tarball (the GPL obligation).
  * Keep PyAV's own LGPL libs for probing.
  * Alternative to avoid GPL: an LGPL build plus platform H.264 encoders (`h264_videotoolbox` on Mac,
    `h264_mf`/`h264_nvenc` on Windows). That costs an engine change and quality tuning. Not worth it now.

### B.4 Installer technology, signing, SmartScreen and Gatekeeper, per-user installs

**macOS**

* Gatekeeper requires Developer ID signing **and** notarization by default since Catalina.
* For unsigned or un-notarized apps the user must go to System Settings › Privacy & Security › **Open Anyway**
  ([Apple support 102445](https://support.apple.com/en-us/102445)).
* macOS 15 removed the old Control-click › Open bypass
  ([Wikipedia: Gatekeeper](https://en.wikipedia.org/wiki/Gatekeeper_(macOS)),
  [Macworld](https://www.macworld.com/article/2457844/what-to-do-when-you-cant-open-an-app-you-just-installed-in-macos-sequoia.html)).
  For a non-technical editor an unsigned `.pkg`/`.app` is effectively a dead end.
* Files fetched by `curl` in Terminal aren't quarantined. That's why `curl … | bash` installers (Claude Code's own,
  Homebrew, uv) avoid Gatekeeper.
* Signing pipeline:
  * apps/binaries: "Developer ID Application" (`codesign --options runtime --timestamp`);
  * `.pkg`: "Developer ID Installer" (`productsign`);
  * then `xcrun notarytool submit --wait` and `xcrun stapler staple` (`.pkg`/`.dmg`/`.app`; a zip can't be stapled)
    ([notarization](https://developer.apple.com/documentation/security/notarizing-macos-software-before-distribution)).
  * Every Mach-O inside a notarized package must itself be signed. Keep downloaded runtimes (Python, ffmpeg) **out**
    of the package and fetch them at install time.
* `.pkg` per-user installs (`<domains enable_currentUserHome="true">`) are documented
  ([Distribution XML ref](https://developer.apple.com/library/mac/documentation/DeveloperTools/Reference/DistributionDefinitionRef/Chapters/Distribution_XML_Ref.html)).
  But developers report the Installer still asking for an admin password or installing into `/Library`
  ([Apple forums](https://developer.apple.com/forums/thread/133850)). `.pkg` scripts also run as **root**, which would
  leave root-owned files in `~`.
  * **Use a signed and notarized "Install WhyNot Cut.app" inside a `.dmg` instead.** It runs as the user with no admin
    and needs only the Developer ID **Application** certificate.
* Apple Developer Program: **$99/year**, individual or organization, in 220+ countries
  ([Apple](https://developer.apple.com/programs/whats-included/)). Organizations need a D-U-N-S number (free, up to 5
  business days) ([Apple D-U-N-S](https://developer.apple.com/support/D-U-N-S/)).

**Windows**

* SmartScreen:
  * Unsigned: "Windows protected your PC" → More info → Run anyway.
  * OV/EV-signed: the publisher name shows, but there's still a warning until reputation builds.
  * **EV no longer bypasses SmartScreen (2024).** Reputation comes per file hash and per certificate. It "can take
    several weeks and hundreds of clean installs".
  * The Microsoft Store (MSIX) is the only warning-free route
    ([SmartScreen reputation](https://learn.microsoft.com/en-us/windows/apps/package-and-deploy/smartscreen-reputation)).
* Signing options ([code-signing options](https://learn.microsoft.com/en-us/windows/apps/package-and-deploy/code-signing-options)):
  * **Azure Artifact Signing** (formerly Trusted Signing): ~$9.99/month, but only for **organizations in the USA,
    Canada, EU, UK and individuals in the USA/Canada**. Not Egypt.
  * **OV certificate** from a CA: $150–300/yr, worldwide, private key on an **HSM/hardware token since June 2023**.
  * EV: $400+/yr, no SmartScreen advantage any more.
  * Self-signed: blocked.
* **Smart App Control** (Windows 11) can block unsigned executables and DLLs regardless of download source (F13).
* Installer tools:
  * **Inno Setup**: `PrivilegesRequired=lowest` means "Setup will not request to be run with administrative
    privileges" ([Inno](https://jrsoftware.org/ishelp/topic_setup_privilegesrequired.htm)). It has built-in
    sha256-checked downloads with a progress page (`DownloadTemporaryFile`, `CreateDownloadPage`)
    ([Inno download page](https://jrsoftware.org/ishelp/topic_isxfunc_createdownloadpage.htm)). This is the best fit.
  * **WiX/MSI**: per-user MSI is possible but heavy to author. No benefit here.
  * **MSIX**: AppData writes are virtualized into a private per-app location, the package folder is read-only, and
    install-time scripts aren't supported ([Advanced Installer](https://www.advancedinstaller.com/msix-limitations.html)).
    It can't write `%APPDATA%\Adobe\CEP\extensions`, `~/.claude/settings.json` or fonts the way we need. Unsuitable,
    even though it would avoid SmartScreen through the Store.
* `irm https://…/install.ps1 | iex` (Claude Code's own pattern) runs as the user with no MOTW and no SmartScreen.
  Downloaded binaries can still hit SAC.

### B.5 Installing the Adobe parts

* **UXP (Premiere 25.6+).** UXP left beta in Premiere **25.6**
  ([Adobe blog](https://blog.developer.adobe.com/en/publish/2025/12/uxp-arrives-in-premiere-a-new-era-for-plugin-development),
  [changelog](https://developer.adobe.com/premiere-pro/uxp/changelog)).
  * Packaged as `.ccx`; each `.ccx` targets one host (`minVersion` e.g. `25.6.0`). Independent distribution needs no
    review, but users see a "only install plugins from trusted sources" warning
    ([independent distribution](https://developer.adobe.com/premiere-pro/uxp/plugins/distribution/independent-distribution)).
  * Install by double-click (Creative Cloud desktop) or **UPIA**
    ([install](https://developer.adobe.com/premiere-pro/uxp/plugins/distribution/install)):
    * Windows: `"C:\Program Files\Common Files\Adobe\Adobe Desktop Common\RemoteComponents\UPI\UnifiedPluginInstallerAgent\UnifiedPluginInstallerAgent.exe" /install <file.ccx>` (also `/remove`, `/list all`).
      Verified present on this PC.
    * macOS: `"/Library/Application Support/Adobe/Adobe Desktop Common/RemoteComponents/UPI/UnifiedPluginInstallerAgent/UnifiedPluginInstallerAgent.app/Contents/macOS/UnifiedPluginInstallerAgent" --install <file.ccx>`.
    * Adobe: "admin privileges may be required". Logs: `%APPDATA%\Adobe\UPI\Log\` and
      `~/Library/Application Support/Adobe/UPI/Log/`
      ([Adobe blog 2021](https://blog.developer.adobe.com/en/publish/2021/06/new-command-line-tool-for-plugin-installation-replaces-exmancmd)).
  * The plugin may ask the user to grant permissions (network / local file system).
  * After Effects has no production UXP, so **the CEP bridge stays for AE and for Premiere 22–25.5**.
* **CEP.** Per-user extension folders: `%APPDATA%\Adobe\CEP\extensions` and
  `~/Library/Application Support/Adobe/CEP/extensions`. System folders need admin.
  * Adobe's validation rules: no signature → doesn't run; invalid signature → doesn't run; **valid signature → runs**;
    expired certificate with a valid timestamp → runs. **`ZXPSignCmd -selfSignedCert …`** then
    `ZXPSignCmd -sign <folder> <out.zxp> <cert.p12> <pw> -tsa <timestamp url>` is Adobe's documented flow
    ([Adobe-CEP Getting Started: Package/Distribute/Install](https://github.com/Adobe-CEP/Getting-Started-guides/tree/master/Package%20Distribute%20Install)).
  * A signed bundle (the ZXP is a zip with `META-INF/signatures.xml`) can be extracted into the per-user folder and
    loads with PlayerDebugMode off. The bundle must stay byte-identical, so F7 must be fixed first. **Test this on
    Premiere 26 and AE 26 before relying on it**: community reports confirm self-signed ZXPs loading with debug mode
    off on 2024/2025 when installed via a ZXP installer, but manual extraction wasn't confirmed in an official source.
  * ExManCmd is deprecated. UPIA replaced it for CEP installs from CC 2022 on (same Adobe blog). UPIA installs into
    the Adobe-managed location and may need admin, so per-user extraction is simpler and admin-free.
* **PlayerDebugMode** (fallback only):
  * Windows: `HKCU\Software\Adobe\CSXS.<n>` string `PlayerDebugMode` = `1`.
  * macOS: `defaults write com.adobe.CSXS.<n> PlayerDebugMode 1`, then `killall cfprefsd` or log out
    ([CEP 12 cookbook](https://github.com/Adobe-CEP/CEP-Resources/blob/master/CEP_12.x/Documentation/CEP%2012%20HTML%20Extension%20Cookbook.md)).
  * Premiere Pro and After Effects 25.0+ = CEP 12. Earlier CC 2021–2024 hosts read CSXS.11. Write 11, 12 and 13
    only if signing isn't available, and only with the user's explicit tick in the installer.
* **Detecting installed hosts:**
  * Windows: glob `%ProgramFiles%\Adobe\Adobe Premiere Pro 20xx\Adobe Premiere Pro.exe` and
    `…\Adobe After Effects 20xx\Support Files\AfterFX.exe` (what `plat.find_adobe_apps()` does; this PC: "Adobe
    Premiere Pro 2026", "Adobe After Effects 2026"). Read the exact version from the exe's version resource
    (`(Get-Item $exe).VersionInfo.ProductVersion`). Detect running instances by process name before touching the CEP
    folder.
  * macOS: glob `/Applications/Adobe Premiere Pro 20xx/*.app` and read `Contents/Info.plist`
    `CFBundleShortVersionString` with `plistlib`. Use `pgrep -f "Adobe Premiere Pro"` for running instances.
  * Map: version < 25 → CSXS.11, ≥ 25 → CSXS.12; version ≥ 25.6 → UXP is available.

### B.6 Fonts (OFL Arabic, e.g. IBM Plex Sans Arabic)

* The OFL lets fonts be bundled and redistributed with software, with the licence text included and no sale of the
  fonts on their own. Ship `OFL.txt` with them.
* **Windows per-user, no admin (Windows 10 1809+):**
  1. Copy to `%LOCALAPPDATA%\Microsoft\Windows\Fonts\`.
  2. Add a value under `HKCU\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Fonts` holding the full path.
  3. `AddFontResource` + broadcast `WM_FONTCHANGE`.

  The PSWinGlue `Install-Font.ps1 -Scope User` script implements this
  ([PowerShell Gallery](https://www.powershellgallery.com/packages/PSWinGlue/0.6.11/Content/Scripts/Install-Font.ps1)).
  Adobe apps **must be restarted**. Adobe forum threads report per-user fonts sometimes not showing in Premiere/AE
  ([Adobe community](https://community.adobe.com/t5/after-effects-discussions/user-installed-fonts-not-showing-up-in-after-effects-and-premiere/m-p/9913370)).
  The doctor should verify through the host (`reel ae-status`/bridge `app.fonts` query, or a Premiere title test) and
  fall back to "Install for all users" (UAC) only when the host can't see the font.
* **macOS per-user:** copy to `~/Library/Fonts/`. No admin. Adobe apps pick the fonts up after a restart.
* Client brand fonts stay the client's (licence unknown), so the installer only installs **our** bundled OFL fonts.
  `reel inbox` can offer a per-user install for a client's fonts, after the editor confirms they're licensed.

### B.7 Doctor and self-repair; error reports without telemetry

* Model it on `claude doctor` ("read-only installation and settings diagnostics … with suggested fixes",
  [setup](https://code.claude.com/docs/en/setup)) and the existing `reel doctor` (`fixes[].who`).
* Levels:
  1. `reel doctor`: read-only;
  2. `reel doctor --fix`: only safe, reversible, automatic repairs;
  3. `reel doctor --bundle`: a diagnostic zip.
* Full check list: §R.5. Diagnostic bundle: §R.6.

### B.8 Auto-update strategy, all components

* The **Claude plugin** is the update carrier: hosted marketplace + archive + `autoUpdate: true` in user settings.
* Everything else is pinned **inside** the plugin (`components.json`) and applied by `reel update`, which the
  SessionStart hook proposes and Claude runs after the editor agrees.
* The Adobe UXP plugin, outside the Adobe Marketplace, doesn't self-update, so `reel update` re-installs the `.ccx`
  through UPIA.
* Models change rarely and are pinned by HF revision and sha256.
* Details in §R.4.

---

## Recommendation

### R.1 Architecture: one bootstrap core, two front ends per OS

```
                       ┌──────────── dl.thewhynot.ai (CDN: Cloudflare R2 / S3) ─────────────┐
                       │ claude/marketplace.json  (url marketplace; plugin entry = archive)  │
                       │ releases/whynot-cut-<ver>.zip (+sha256)                             │
                       │ components/<ver>.json   runtime locks   wheelhouse mirror           │
                       │ ffmpeg/<ver>/<os-arch>/ (+GPL source link)   bridge/*.zxp  *.ccx      │
                       │ fonts/ofl-arabic.zip    models mirror (optional)                     │
                       └───────────────▲───────────────────────────▲─────────────────────────┘
                                       │ HTTPS + sha256             │ HTTPS + sha256
 Front ends                            │                            │
  Windows: install.ps1 (irm|iex)  ─┐   │                            │
           WhyNotCut-Setup.exe ────┼─► BOOTSTRAP CORE (per-user, no admin, idempotent, resumable, logged)
  macOS:   install.sh (curl|bash) ─┤      1 preflight  2 components.json  3 uv  4 python 3.12  5 runtime lock
           Install WhyNot Cut.app ─┘      6 ffmpeg  7 GPU libs  8 Claude plugin  9 Adobe bridge/UXP
                                          10 fonts  11 model (bg)  12 state.json + doctor + open Claude
 After install: Claude plugin auto-updates → SessionStart hook compares components.json ↔ state.json
                → "reel update" (asks) → runtime/ffmpeg/bridge/models brought in line
```

**Engine home layout.** Keep `~/.whynot-cut` (Windows `%USERPROFILE%\.whynot-cut`) for compatibility with existing
installs, the 2.9 GB of models, and `bridge-config`. It stays independent of the Claude plugin lifecycle; don't use
`${CLAUDE_PLUGIN_DATA}`, which is deleted on uninstall.

```
~/.whynot-cut/
  bin/uv(.exe)                      pinned uv release (sha256)
  python/                           UV_PYTHON_INSTALL_DIR (python-build-standalone 3.12.x)
  runtimes/<lock-id>/               venv built from runtime-<platform>.lock (no system site, no user site)
  current                           text file holding <lock-id> (atomic switch; previous kept for rollback)
  ffmpeg/<ver>/ffmpeg(.exe)
  cuda/bin/                         Windows NVIDIA only (existing install_cuda_redist)
  models/                           HF cache layout (existing)
  bridge/config.json                moved out of the CEP folder (F7)
  ppro-queue/ ppro-scripts/ ae-queue/ ae-scripts/   (existing)
  state.json                        installed component versions (§R.4)
  logs/install-*.log  logs/update-*.log
  cache/uv/                         UV_CACHE_DIR
```

**Code changes the installer depends on** (small, mostly in `bin/reel*`, `hooks/run_python.sh`, `setup/`,
`ppro_bridge.py`, the CEP `index.html`):

1. `bin/reel` and `reel.cmd` pick the runtime in this order: `$WHYNOT_HOME/runtimes/$(cat current)/…python` → legacy
   `venv/` → (setup only) bootstrap. Never fall back to system Python for the engine.
2. `hooks/run_python.sh` uses the **engine Python first** (`$HOME/.whynot-cut/python/…`), then the system one. It must
   **fail loudly** in the SessionStart context when no interpreter exists ("WhyNot Cut protection is OFF until setup
   finishes"), not silently.
3. Windows hooks. Phase 1: the installer guarantees Git Bash. If `bash.exe` is missing, extract PortableGit per user to
   `%LOCALAPPDATA%\WhyNotCut\git` and set `env.CLAUDE_CODE_GIT_BASH_PATH` in `~/.claude/settings.json`. Phase 2: test
   exec-form hooks (`command` = engine `python.exe` via a userConfig value) to drop the bash dependency.
4. `setup/bootstrap.ps1` and `setup/bootstrap.sh` replace "find a system Python" with "download uv → `uv python install`
   → `uv venv` → `uv pip sync --require-hashes runtime-<platform>.lock`". `setup_env.py` stays as the in-runtime
   repair tool.
5. Bridge:
   * the panel reads `~/.whynot-cut/bridge/config.json` (Node `os.homedir()`);
   * the bundle ships as a **signed ZXP** (self-signed + timestamp);
   * `install()` extracts the ZXP instead of copying loose files, and verifies `META-INF/signatures.xml` and file
     hashes;
   * the heartbeat reports `{bundle, protocol, host, hostVersion}`.
6. `reel update`, `reel doctor --fix`, `reel doctor --bundle`, `reel bench`, `reel --version` (prints plugin version and
   root, which fixes G66 diagnosis).

### R.2 The installer per OS

**Windows 10/11 (x64; ARM64 later)**

* **Now (no certificate):** `install.ps1`, published at `https://thewhynot.ai/install.ps1`. The editor opens PowerShell
  (Start › type "PowerShell" › Enter) and pastes `irm https://thewhynot.ai/install.ps1 | iex`. No admin, no
  SmartScreen.
* **With an OV certificate:** `WhyNotCut-Setup.exe`, ~5–10 MB (est.). Inno Setup with `PrivilegesRequired=lowest`,
  install dir `{localappdata}\WhyNotCut\installer`. It embeds `install.ps1` + uv and runs the core with a progress page
  (CreateDownloadPage) and a checklist UI. Signed with the OV certificate and RFC 3161 timestamp. It registers an
  uninstaller (HKCU) that removes the plugin (`claude plugin uninstall`), the CEP/UXP panel, the per-user fonts and
  (optionally) `~/.whynot-cut`.
* What the core does on Windows, beyond the common steps:
  * if no Git Bash: PortableGit plus `CLAUDE_CODE_GIT_BASH_PATH` (~60 MB, est.);
  * NVIDIA detection via `nvidia-smi` → cuBLAS (existing code, ~520 MB) with a default-yes tick;
  * a SAC check: `HKLM\SYSTEM\CurrentControlSet\Control\CI\Policy` `VerifiedAndReputablePolicyState`, read-only. If SAC
    is on, warn and run a 5-second `python -c "import ctranslate2, av"` smoke test right away so a block shows during
    install, not during the first edit;
  * per-user fonts;
  * the CEP bridge (signed ZXP) into `%APPDATA%\Adobe\CEP\extensions`;
  * for Premiere ≥ 25.6, the UXP `.ccx` through UPIA `/install`. If UPIA needs elevation, fall back to opening the
    `.ccx` (Creative Cloud desktop handles it, with Adobe's warning dialog).

**macOS (Apple Silicon + Intel)**

* **Now (no Apple account):** `install.sh`. The editor opens Terminal (Spotlight › "Terminal") and pastes
  `curl -fsSL https://thewhynot.ai/install.sh | bash`. No quarantine and no Gatekeeper. No admin, no Xcode CLT, no
  Homebrew.
* **With the Apple Developer Program:** `WhyNotCut.dmg` containing **"Install WhyNot Cut.app"**. A tiny SwiftUI or
  AppleScript app runs the same `install.sh` as the user and shows a checklist. It's signed with Developer ID
  Application + hardened runtime, notarized and stapled. **No `.pkg`**: postinstall scripts run as root, and
  home-domain `.pkg` installs are unreliable (B.4).
* What the core does on macOS, beyond the common steps:
  * arch detection (`uname -m`), so arm64 gets the MLX extra in the lock;
  * ffmpeg arm64/x64 (from the owner's mirror of Martin Riedl's builds, signature checked with `codesign -v`);
  * fonts → `~/Library/Fonts`;
  * CEP signed ZXP → `~/Library/Application Support/Adobe/CEP/extensions`;
  * UXP via UPIA `--install`;
  * a note that the first file access from Claude to Documents or external drives brings a macOS "Allow" dialog.

**Common core steps (both OSs)**

1. **Preflight** (read-only):
   * OS version and arch; free space (≥ 6 GB without the model, ≥ 9 GB with large-v3);
   * a non-ASCII or space-containing home path (test path, warn), OneDrive/iCloud redirection of Documents;
   * Claude present (CLI on PATH, desktop-bundled CLI, or just `~/.claude`) and a signed-in plan (can't check: say
     so);
   * Adobe apps and versions, and whether they're running;
   * NVIDIA GPU;
   * an existing install (`~/.whynot-cut`, legacy `~/.reel-editor`, `thewhynot-ai` directory marketplace).
2. Fetch `components.json` for the channel (stable/beta). The installer embeds the sha256 of the signing public key, or
   at minimum pins the URL over HTTPS.
3. uv → Python 3.12 → runtime lock sync (PyPI first, own wheelhouse mirror as fallback, `--require-hashes`).
4. ffmpeg (pinned, sha256).
5. GPU libraries (Windows NVIDIA cuBLAS; Apple Silicon: MLX is in the lock).
6. **Claude plugin:**
   * (a) if a `claude` CLI is found (PATH, `%APPDATA%\Claude\claude-code\*\*\claude.exe`, macOS app bundle path):
     `claude plugin install whynot-cut --marketplace https://dl.thewhynot.ai/claude/marketplace.json --scope user --config engine_home=<path> --json`;
   * (b) **always** merge into `~/.claude/settings.json`, after a timestamped backup:
     ```json
     { "extraKnownMarketplaces": { "thewhynot-ai": {
           "source": { "source": "url", "url": "https://dl.thewhynot.ai/claude/marketplace.json" },
           "autoUpdate": true } },
       "enabledPlugins": { "whynot-cut@thewhynot-ai": true } }
     ```
   * (c) **migration**: if `thewhynot-ai` is still a `directory` marketplace, run `claude plugin marketplace remove
     thewhynot-ai` first. That uninstalls the plugin, which is safe because the engine lives outside it. Then re-add it
     from the URL.
7. **Adobe:**
   * if a host is running, ask the editor to close it (Windows locks the folder);
   * extract the signed ZXP per user, write `~/.whynot-cut/bridge/config.json`;
   * UXP `.ccx` for Premiere ≥ 25.6;
   * **only if the ZXP is unsigned** (an emergency build): offer a checkbox "Allow unsigned Adobe panels
     (PlayerDebugMode)" and set CSXS.11/12 for the user;
   * remember that all hosts need a restart.
8. Fonts (bundled OFL Arabic set) per user.
9. Ask two questions in the installer:
   * clients folder (the default from the `start` skill: `D:\WhyNot Clients` if D: exists, else
     `Documents\WhyNot Clients`; macOS `~/Documents/WhyNot Clients`);
   * Arabic or English.

   Write `~/.claude/whynot-cut.local.md` via `reel settings --init "~" …`.
10. Model: "Download the transcription model now (2.9 GB)?" Default **yes, in the background**. Pick the model by
    hardware: NVIDIA → large-v3; Apple Silicon → large-v3 (MLX); otherwise turbo. Resume with the existing logic.
11. Write `state.json`, run `reel doctor --json`, and show green, amber or red rows.
12. **Open Claude:**
    * Desktop: `claude://code/new?q=%2Fwhynot-cut%3Astart` (confirm a local-folder parameter in Desktop; else open the
      app and show "type /whynot-cut:start").
    * CLI users: `claude-cli://open?cwd=<clients folder>&q=/whynot-cut:start`.

    The prompt is prefilled; the editor presses Enter.

### R.3 The editor's journey (≤ 6 steps)

| # | Windows | macOS | Time |
|---|---|---|---|
| 1 | Install the Claude desktop app and sign in (Pro/Max/Team) | same | 3 min |
| 2 | **Signed later:** double-click `WhyNotCut-Setup.exe`. **Now:** open PowerShell and paste `irm https://thewhynot.ai/install.ps1 \| iex` | **Signed later:** open `WhyNotCut.dmg` and double-click "Install WhyNot Cut". **Now:** open Terminal and paste `curl -fsSL https://thewhynot.ai/install.sh \| bash` | 1 min |
| 3 | Answer 2 questions (clients folder, language), tick "download model now"; the checklist turns green (engine, Premiere/AE panel, fonts, GPU, Claude plugin); the model keeps downloading in the background | same | 5–15 min, network-bound |
| 4 | If Premiere/After Effects were open: close them when asked, reopen when done | same | 1 min |
| 5 | Claude opens with `/whynot-cut:start` typed in. Press Enter: the wizard checks everything (`reel doctor`), creates the first client folder and opens it | same; click **Allow** if macOS asks about Documents | 3 min |
| 6 | Drop logo, fonts, photos and raw clips into the folders shown, then say **"edit the new videos"** | same | — |

**No admin prompt and no `reg add`/`defaults write` on the normal path.** Downloads: ~0.4 GB plus the model (2.9 GB),
plus ~0.5 GB cuBLAS on NVIDIA PCs.

**Updates:** nothing to do. Claude updates the plugin in the background. When a new version needs an engine or panel
update, Claude says so at the start of a session ("WhyNot Cut 2.4 needs a 120 MB engine update and a Premiere panel
update. Do it now?"). On yes it runs `reel update`, and asks the editor to restart Premiere when the panel changed.
**Repair:** run the installer again, or say "fix WhyNot Cut" (`reel doctor --fix`).

### R.4 Component and version-handshake design

**1. `components.json`** (shipped **inside** the plugin, so it updates atomically with the engine code, and also
published on the CDN for the installer):

```json
{
  "schema": 1,
  "plugin": "2.4.0",
  "channel": "stable",
  "claude_code": { "min": "2.1.224" },
  "runtime": {
    "python": "3.12.11",
    "locks": {
      "win-x64":   { "file": "setup/locks/runtime-win-x64.lock",   "id": "r-7f3a9c21d0e4" },
      "mac-arm64": { "file": "setup/locks/runtime-mac-arm64.lock", "id": "r-19bb04e8a6c2" },
      "mac-x64":   { "file": "setup/locks/runtime-mac-x64.lock",   "id": "r-c0de55aa1f90" }
    }
  },
  "uv": { "version": "x.y.z", "sha256": { "win-x64": "…", "mac-arm64": "…", "mac-x64": "…" } },
  "ffmpeg": { "version": "7.1.x", "license": "GPL-3.0", "source": "https://dl.thewhynot.ai/ffmpeg/7.1.x/src.tar.xz",
              "sha256": { "win-x64": "…", "mac-arm64": "…", "mac-x64": "…" } },
  "bridge": {
    "protocol": 4, "min_protocol": 4,
    "cep": { "bundle": "3.2.0", "zxp": "bridge/whynot-cut-bridge-3.2.0.zxp", "sha256": "…",
             "hosts": { "PPRO": "[22.0,99.9]", "AEFT": "[24.0,99.9]" } },
    "uxp": { "version": "1.0.0", "ccx": "bridge/whynot-cut-premiere-1.0.0.ccx", "sha256": "…", "min_host": "25.6.0" }
  },
  "models": {
    "large-v3":       { "backend": "ct2", "repo": "Systran/faster-whisper-large-v3", "revision": "<hf sha>", "bytes": 3087000000 },
    "large-v3-turbo": { "backend": "ct2", "repo": "…", "revision": "…" },
    "large-v3-mlx":   { "backend": "mlx", "repo": "mlx-community/whisper-large-v3-mlx", "revision": "…" }
  },
  "fonts": { "pack": "fonts/ofl-arabic-1.0.zip", "sha256": "…" }
}
```

**2. `~/.whynot-cut/state.json`** is written only by the installer and `reel update`. It records what is **actually
installed**: plugin version that last ran the update, runtime `id` (also stamped as
`runtimes/<id>/WHYNOT_RUNTIME`), uv/python/ffmpeg versions and sha256, bridge bundle, protocol and per-host install
path, UXP version, fonts pack, model revisions, last doctor result and time.

**3. Compatibility rules** (enforced in code, not only in docs):

| Check | Where | On mismatch |
|---|---|---|
| Claude Code ≥ `claude_code.min` | installer; SessionStart hook (`CLAUDE_CODE_VERSION` if exposed, else `claude --version`) | Tell the editor to update Claude; archive sources need ≥ 2.1.224 |
| runtime `id` == `current` | `bin/reel` wrapper (cheap file compare) before every command | Commands that don't need new packages run with a warning; any import failure → `{"blocked": "engine update needed", "how": "reel update"}` |
| bridge `protocol` within `[min_protocol, protocol]` | engine `submit()` reads the heartbeat `{bundle, protocol}` | Refuse the job: "Premiere panel 3.1 is older than this WhyNot Cut (needs 3.2). Run reel update, then restart Premiere." Never send a job in an unknown format. The panel refuses an engine whose protocol it doesn't know. |
| bundle downgrade | `ppro_bridge.install()` (exists: version compare) | Keep the newer bundle unless `--force` |
| model revision | doctor / transcribe | Old revision still works (warn); a missing or corrupt model → re-download (ask: GB) |
| ffmpeg sha256 | doctor | Re-fetch |

**4. Update flows:**

* **Plugin:** `autoUpdate: true` (user settings) → Claude Code downloads the new archive. It takes effect at the next
  session start or `/reload-plugins`.
* **SessionStart hook** (≤ 10 s; reads two JSON files, no network): if `components.json` ≠ `state.json`, it adds
  context: "Pending WhyNot Cut updates: runtime (≈120 MB), Premiere panel (restart needed). Ask the editor, then run
  `reel update` in the background."
* **`reel update`** (idempotent, resumable, logged):
  * the runtime is built **side by side** (`runtimes/<new-id>`) and `current` switches only after an import smoke
    test passes; the previous runtime is kept until the next successful update;
  * ffmpeg goes to a new versioned folder;
  * bridge: if Premiere/AE are running, stop and ask (Windows locks) → extract the new signed ZXP into a temp folder,
    then swap; UXP via UPIA;
  * then `state.json` and `reel doctor`.
* **Models:** only when `models.<name>.revision` changes and the editor agrees. The engine keeps working with the old
  revision meanwhile.
* **Rollback:**
  * the plugin: publish the previous archive under a new patch version (`2.4.1` = the 2.3.x content), because one
    marketplace serves one version;
  * the runtime: `reel update --rollback` switches `current` back;
  * the bridge: keep the previous `.zxp` in `~/.whynot-cut/bridge/`.
* **Release channels:** two marketplace URLs (`…/stable/marketplace.json`, `…/beta/marketplace.json`) with different
  marketplace `name`s, chosen by the installer flag `--channel beta`
  ([host-marketplace: release channels](https://code.claude.com/docs/en/plugins/host-marketplace)).

**5. Release pipeline** (CI on the owner's machine or GitHub Actions in a private repo):

1. tests;
2. `claude plugin validate --strict`;
3. `uv pip compile --universal --generate-hashes` → 3 locks (and a CI install of each lock on a clean
   Windows/macOS-arm64/macOS-x64 runner);
4. build and **sign** the ZXP (`ZXPSignCmd -sign … -tsa`);
5. package the `.ccx` (UDT);
6. `package.py` → plugin zip;
7. upload all artifacts to versioned CDN paths;
8. render `components.json` and `marketplace.json` (archive url + sha256);
9. **upload `marketplace.json` last** (atomic publish);
10. smoke-install on clean VMs.

### R.5 Doctor: what it verifies and repairs

| Area | Verify (read-only) | Auto-fix (`--fix`) | Needs the editor |
|---|---|---|---|
| Platform | OS/arch/build; free space on engine and clients drives; home path non-ASCII/spaces; OneDrive/iCloud "online-only" files in clients folder; Windows LongPathsEnabled; SAC state | — | Free space; make folders "always keep on this device" |
| Claude | plugin installed, enabled, version and scope (`claude plugin list --json` if a CLI exists, else `installed_plugins.json`); marketplace source = URL and `autoUpdate` true; **this session's `reel` = this plugin** (`reel --version` root vs `CLAUDE_PLUGIN_ROOT`, G66); Git Bash present (Windows); hooks heartbeat (SessionStart writes `~/.whynot-cut/logs/hook-heartbeat.json`) | Re-merge settings keys; PortableGit + `CLAUDE_CODE_GIT_BASH_PATH` | Restart Claude (new session) |
| Runtime | uv/python versions; `current` id == lock id; every module imports; `importlib.metadata` versions == lock; **no user site and no system site** (`sys.flags.no_user_site`, `pyvenv.cfg`) (F2/G67) | Rebuild side by side; switch `current` | — |
| ffmpeg | path, version, sha256; 1-s libx264 encode test | Re-fetch | — |
| GPU / backend | NVIDIA driver + `ctranslate2.get_cuda_device_count()`; cuBLAS loadable; a 2-s inference on the chosen device; Apple: `mlx` import + Metal device; RT factor from `reel bench` cache | Install cuBLAS (ask, ~520 MB) | Update the NVIDIA driver |
| Models | complete vs partial; size/sha256; revision pin | Resume or re-download (ask) | Approve GBs |
| Adobe | hosts and versions; running state; CEP bundle version, **signature intact** (manifest present, no extra files, file hashes vs `signatures.xml`); PlayerDebugMode only reported; UXP installed (`UPIA /list all`); heartbeat alive + `protocol`; recent CEP log errors (`CEPHtmlEngine*-PPRO/AEFT-*.log`), UPIA logs | Reinstall the bundle when the host is closed; re-sync scripts | Close/reopen Premiere or AE; dismiss modal dialogs |
| Fonts | bundled fonts installed (file + registry/`~/Library/Fonts`) and **seen by the host** (bridge font query); client brand fonts | Re-register per-user fonts | Restart Adobe apps; "install for all users" (UAC) as a last resort |
| Network (only with `--fix`) | reach CDN, PyPI, HF, NVIDIA; proxy env | Switch to the mirror | Corporate proxy settings |
| Preferences | file found, values valid, `clients_root` exists | — | — |

Output stays the current JSON (`verdict`, `ready`, `fixes[{item, who, fix}]`) plus `components` (expected vs
installed). Every fix must be idempotent and logged to `~/.whynot-cut/logs/doctor-*.log`.

### R.6 Error reports without telemetry

* `reel doctor --bundle` writes `WhyNotCut-diagnostics-<date>.zip` to the Desktop and prints its path. Contents:
  * `doctor.json`, `state.json`, `components.json`;
  * the last 3 install/update logs and hook heartbeat;
  * the last 500 lines of the newest `pipeline.log`;
  * CEP and UPIA logs from the last 7 days;
  * `claude plugin list --json` (if a CLI exists);
  * Python/package versions; a PATH entry list.
* Redaction: replace the username and home path with `<HOME>`, client folder names with `client-1…n`; strip API keys
  by regex.
* **No media, transcripts, or client files**, unless the editor ticks "include transcript of clip X".
* A `MANIFEST.txt` lists every included file so the editor can see what is being shared. The editor sends it to
  support by email or WhatsApp themselves. Nothing is uploaded automatically, and there is no telemetry.
* The installer's failure screen offers "Save diagnostics" for the same thing, before the engine even exists: the
  PowerShell/bash core collects its own log, OS info and preflight result.

### R.7 Certificates: what costs money, and what to do without it

| Need | Pays for | Cost | Without it |
|---|---|---|---|
| macOS double-click installer with no Gatekeeper wall | **Apple Developer Program** (Developer ID Application cert + notarization). The Installer cert is needed only if a `.pkg` is ever shipped | $99/yr ([Apple](https://developer.apple.com/programs/whats-included/)); organization enrollment needs a D-U-N-S number (free, ≤5 business days) | `curl -fsSL https://thewhynot.ai/install.sh \| bash` (no quarantine). **Don't ship an unsigned `.app`/`.pkg`**: on macOS 15+ it needs the System Settings › Open Anyway detour |
| Windows double-click installer with a publisher name | **OV code-signing certificate** from a CA (DigiCert, Sectigo, GlobalSign, Certum, SSL.com …) on an HSM token or cloud HSM. **Azure Artifact Signing isn't available for Egypt** (organizations only in US/CA/EU/UK; individuals only in US/CA) unless the agency has a legal entity there | $150–300/yr ([Microsoft](https://learn.microsoft.com/en-us/windows/apps/package-and-deploy/code-signing-options)) | `irm https://thewhynot.ai/install.ps1 \| iex`. An unsigned `.exe` works but shows "Windows protected your PC" → More info → Run anyway, and reputation never builds for unsigned files |
| SmartScreen with no warning at all | Only the Microsoft Store (MSIX), which doesn't fit (B.4); or weeks of signed-download reputation | — | Tell early users to expect one SmartScreen prompt, even when signed |
| CEP panel without PlayerDebugMode | Nothing. **A self-signed ZXP certificate is valid** (+ free timestamp TSA) | $0 | — |
| UXP `.ccx` | Nothing for independent distribution (Adobe's warning dialog stays). The Adobe Marketplace is optional (review; 10% fee only on paid sales) | $0 | — |
| ffmpeg, fonts | Nothing: GPL/OFL compliance (licence files + source link) | $0 | — |

**Plan if the owner has no certificates yet:**

1. Ship the one-liner front ends and the URL marketplace now.
2. Sign the ZXP with a self-signed certificate now. This removes PlayerDebugMode, the biggest scary step.
3. Enroll in the Apple Developer Program and order an OV certificate in parallel; the identity checks take days to
   weeks.
4. Add the signed `.exe` and notarized `.dmg` front ends when they arrive. They wrap the same core, with no rework.

### R.8 Test matrix (before calling it "one-click")

* **Windows:**
  * Windows 10 22H2 and Windows 11 24H2/25H2;
  * a **standard (non-admin) user**; no Python, no Git;
  * a username with a space **and** one with Arabic letters;
  * OneDrive-redirected Documents; SAC on;
  * NVIDIA and no-NVIDIA laptops; proxy/slow link (throttle to 1 Mbit/s).
* **macOS:**
  * 14, 15 and 26 on Apple Silicon (base M1/M2, an M-Pro); 13–15 on Intel;
  * a standard user; no CLT; FileVault on.
* **Adobe:** Premiere 2024 (CSXS.11), 2025 (CSXS.12), 2026 (CSXS.12 + UXP); AE 2025/2026; Premiere open during install.
* **Upgrades:** 2.1.1/2.2.0 directory-marketplace install → URL marketplace; legacy `~/.reel-editor`; interrupted
  model download; runtime rollback; bridge protocol mismatch.

### R.9 Open questions and risks

* Self-signed ZXP **extracted** (not ExMan/UPIA-installed) loading with PlayerDebugMode off on CEP 12 / Premiere 26 and
  AE 26 must be verified on this PC. It's the linchpin of removing PlayerDebugMode.
* Desktop `claude://code/new` with a **local folder** parameter isn't documented on the page read (only the SSH form +
  `q`). The fallback is a plain "type /whynot-cut:start" instruction.
* SAC on Windows 11 can block unsigned Python/PyAV/CTranslate2 binaries. No installer choice fixes this short of
  signing third-party binaries, which isn't allowed. Detect it and explain clearly. SAC is off on most upgraded PCs.
* MLX backend parity for Arabic word timestamps and the glossary prompt; numbers in B.2 are estimates until
  `reel bench` runs.
* GPL ffmpeg distribution: keep the source-tarball mirror next to the binaries for as long as they're distributed.
* Writing `~/.claude/settings.json`: the installer must merge, not overwrite (backup + JSON merge), and never touch
  managed settings.

---

## Sources (fetched 2026-10-11)

Claude Code: [Install and manage plugins](https://code.claude.com/docs/en/plugins/install) ·
[Create a marketplace](https://code.claude.com/docs/en/plugin-marketplaces) ·
[Host and maintain a marketplace](https://code.claude.com/docs/en/plugins/host-marketplace) ·
[Marketplace reference](https://code.claude.com/docs/en/plugins/marketplace-reference) ·
[Plugin loading reference](https://code.claude.com/docs/en/plugins/loading) ·
[Manage plugins for your organization](https://code.claude.com/docs/en/plugins/org) ·
[Publish and distribute](https://code.claude.com/docs/en/plugins/publish) ·
[Plugin components](https://code.claude.com/docs/en/plugins/components) ·
[Plugin CLI reference](https://code.claude.com/docs/en/plugins/cli-reference) ·
[Hooks](https://code.claude.com/docs/en/hooks) · [Advanced setup](https://code.claude.com/docs/en/setup) ·
[Desktop](https://code.claude.com/docs/en/desktop) · [Deep links](https://code.claude.com/docs/en/deep-links)

Python/ML: [uv installation](https://docs.astral.sh/uv/getting-started/installation/) ·
[uv installer reference](https://docs.astral.sh/uv/reference/installer/) ·
[uv Python versions](https://docs.astral.sh/uv/concepts/python-versions/) ·
[uv install Python](https://docs.astral.sh/uv/guides/install-python/) ·
[faster-whisper](https://github.com/SYSTRAN/faster-whisper) ·
[CTranslate2 installation](https://opennmt.net/CTranslate2/installation.html) ·
[mlx-examples/whisper](https://github.com/ml-explore/mlx-examples/tree/main/whisper) ·
[Simon Willison on mlx-whisper](https://simonwillison.net/2024/Aug/13/mlx-whisper/) ·
[whisper.cpp](https://github.com/ggml-org/whisper.cpp) ·
[PyInstaller false positives (discuss.python.org)](https://discuss.python.org/t/pyinstaller-false-positive/43171)

ffmpeg: [FFmpeg legal](https://ffmpeg.org/legal.html) · [BtbN FFmpeg-Builds](https://github.com/BtbN/FFmpeg-Builds) ·
[Martin Riedl builds](https://ffmpeg.martin-riedl.de/) · [evermeet.cx arm64 note](https://evermeet.cx/ffmpeg/apple-silicon-arm) ·
[imageio-ffmpeg](https://pypi.org/project/imageio-ffmpeg/)

Apple: [Safely open apps (102445)](https://support.apple.com/en-us/102445) ·
[Notarizing macOS software](https://developer.apple.com/documentation/security/notarizing-macos-software-before-distribution) ·
[Apple Developer Program](https://developer.apple.com/programs/whats-included/) ·
[D-U-N-S](https://developer.apple.com/support/D-U-N-S/) ·
[Distribution XML reference](https://developer.apple.com/library/mac/documentation/DeveloperTools/Reference/DistributionDefinitionRef/Chapters/Distribution_XML_Ref.html) ·
[Apple forum: home-domain pkg asks for admin](https://developer.apple.com/forums/thread/133850) ·
[Gatekeeper (Wikipedia)](https://en.wikipedia.org/wiki/Gatekeeper_(macOS)) ·
[Macworld on Sequoia](https://www.macworld.com/article/2457844/what-to-do-when-you-cant-open-an-app-you-just-installed-in-macos-sequoia.html)

Microsoft/Windows: [Code signing options](https://learn.microsoft.com/en-us/windows/apps/package-and-deploy/code-signing-options) ·
[SmartScreen reputation](https://learn.microsoft.com/en-us/windows/apps/package-and-deploy/smartscreen-reputation) ·
[Artifact Signing quickstart](https://learn.microsoft.com/azure/trusted-signing/quickstart) ·
[Artifact Signing pricing](https://azure.microsoft.com/pricing/details/artifact-signing/) ·
[Smart App Control (textslashplain)](https://textslashplain.com/2026/04/28/smart-app-control/) ·
[KiCad SAC thread](https://forum.kicad.info/t/windows-11-smart-app-control-sac-incompatibility/39473) ·
[Inno Setup PrivilegesRequired](https://jrsoftware.org/ishelp/topic_setup_privilegesrequired.htm) ·
[Inno CreateDownloadPage](https://jrsoftware.org/ishelp/topic_isxfunc_createdownloadpage.htm) ·
[Inno DownloadTemporaryFile](https://jrsoftware.org/ishelp/topic_isxfunc_downloadtemporaryfile.htm) ·
[MSIX limitations (Advanced Installer)](https://www.advancedinstaller.com/msix-limitations.html) ·
[Git for Windows archives](https://gitforwindows.org/zip-archives-extracting-the-released-archives.html) ·
[PSWinGlue Install-Font.ps1](https://www.powershellgallery.com/packages/PSWinGlue/0.6.11/Content/Scripts/Install-Font.ps1)

Adobe: [Install a UXP plugin (Premiere)](https://developer.adobe.com/premiere-pro/uxp/plugins/distribution/install) ·
[Independent distribution](https://developer.adobe.com/premiere-pro/uxp/plugins/distribution/independent-distribution) ·
[Package a UXP plugin](https://developer.adobe.com/premiere-pro/uxp/plugins/distribution/package) ·
[Premiere UXP changelog](https://developer.adobe.com/premiere-pro/uxp/changelog) ·
[UXP arrives in Premiere (Dec 2025)](https://blog.developer.adobe.com/en/publish/2025/12/uxp-arrives-in-premiere-a-new-era-for-plugin-development) ·
[UPIA replaces ExManCmd](https://blog.developer.adobe.com/en/publish/2021/06/new-command-line-tool-for-plugin-installation-replaces-exmancmd) ·
[CEP 12 Cookbook](https://github.com/Adobe-CEP/CEP-Resources/blob/master/CEP_12.x/Documentation/CEP%2012%20HTML%20Extension%20Cookbook.md) ·
[CEP Package/Distribute/Install guide](https://github.com/Adobe-CEP/Getting-Started-guides/tree/master/Package%20Distribute%20Install) ·
[Adobe community: user-installed fonts](https://community.adobe.com/t5/after-effects-discussions/user-installed-fonts-not-showing-up-in-after-effects-and-premiere/m-p/9913370)

Local evidence (read-only): `package.py`, `README.md`, `.claude-plugin/marketplace.json`, `whynot-cut/.claude-plugin/plugin.json`,
`setup/setup_env.py|.sh`, `setup/requirements.txt`, `bin/reel`, `bin/reel.cmd`, `hooks/hooks.json`, `hooks/run_python.sh`,
`hooks/session_context.py`, `engine/reel/lib/{plat,settings,ppro_bridge,onboard,common,transcribe}.py`, `engine/reel/cli.py`,
`templates/premiere/cep_bridge/CSXS/manifest.xml`, skills `start`, `setup` (+ `references/platform-setup.md`), `preferences`,
agent `setup-doctor`, `CHANGELOG.md`, `THIRD_PARTY_NOTICES.md`, `LICENSE`, `Editing Plugin/round4-gaps.md` (G66, G67);
this PC: `~/.claude/plugins/known_marketplaces.json`, `installed_plugins.json`, `~/.whynot-cut/venv/pyvenv.cfg`, site-packages
sizes, model folder size, cuBLAS size, `%APPDATA%\Claude\claude-code\…\claude.exe`, `C:\Program Files\Adobe\*`, UPIA present,
`HKCU\Software\Adobe\CSXS.12`, imageio-ffmpeg `-version` build flags.
