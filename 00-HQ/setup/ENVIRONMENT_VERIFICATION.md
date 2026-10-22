# ENVIRONMENT VERIFICATION — Phase 1 (Windows development environment & dependencies)

- Date: 2026-10-22, 04:20–05:00 Cairo. Seat: main (info@). Builds on `SETUP_AUDIT.md` / `SETUP_BASELINE.md` (Phase 0).
- Changed on this PC in Phase 1 (everything else was read-only):
  1. **Installed standalone Bun 1.4.2** (official GitHub release, SHA256 verified) to `D:\ClaudeData\bun\bin\bun.exe`.
  2. **User PATH:** prepended `D:\ClaudeData\bun\bin` (kept `REG_EXPAND_SZ` and every existing entry; Jan's folders untouched).
  3. **User env:** `BUN_INSTALL=D:\ClaudeData\bun` (so `bun upgrade` and global packages stay on D).
  Scripts and the saved old PATH: `D:\ClaudeData\setup-phase1\` (`install-bun.cmd`, `undo-bun.cmd`, `user-path-before.txt`).
- Not changed: gstack and OMC (not installed), product code, helper accounts, Windows security, execution policy,
  any other global tool. No paid API.

## 1. Official requirements (read from the upstream repos on 2026-10-22, not installed)

| Consumer | Mandatory | Optional |
|---|---|---|
| **gstack** (`garrytan/gstack` main, package 1.91.176; `README.md`, `setup`, `setup.ps1`, `bin/gstack-bun-version.sh`) | Claude Code · Git (Windows: Git for Windows + its Git Bash; `setup.ps1` refuses WSL's bash as launcher — gstack inside WSL is a separate supported install, not used here) · **Bun ≥ 1.3.3 floor, 1.4.2 tested (CI pin), 1.4.3 default** · Node.js (Windows only) | Aside browser (macOS only) · bundled Chromium via Playwright (setup downloads it; `--no-browser` defers it) · `/cso`: VS 2022 Build Tools (Desktop C++) + Docker images · Codex CLI (outside reviews; to stay disabled) |
| **OMC** (`Yeachan-Heo/oh-my-claudecode`, latest 5.7.7; 5.7.6 already in the pilot) | Claude Code CLI · Claude Pro/Max subscription or API key · Node `20.x–26.x` (package `engines`; hooks are node scripts) | **tmux / psmux** (`omc team` CLI workers and rate-limit detection) · Linux `flock` (named autopilot profiles: Linux only) · external CLIs: Codex, Gemini, Antigravity, Grok, Cursor (to stay off) · npm runtime `oh-my-claude-sisyphus` (not needed for the plugin) |
| **Claude Code on Windows** | Git for Windows (Git Bash is the shell its Bash tool uses) | `claude` on PATH (only for terminal use outside the app) |
| **WhyNot Cut product** | Python (engine runs its own CPython 3.12.15 runtime) · Node for `adobe/` · Premiere Pro / After Effects 2026 | — |

## 2. Installed tool versions and executable locations — VERIFIED

| Tool | Version | Location (first on PATH) | Requirement | Result |
|---|---|---|---|---|
| Git for Windows | 2.56.0.windows.2 | `C:\Program Files\Git\cmd\git.exe` (Git Bash: `/ucrt64/bin/git`) | gstack, Claude Code | **PASS** |
| Git Bash | GNU bash 5.3.15, `MINGW64_NT-10.0-26300` | `C:\Program Files\Git\bin\bash.exe` | gstack setup, Claude Code | **PASS** |
| Node.js | 26.7.0 | `C:\Program Files\nodejs\node.exe` | gstack (Win), OMC 20–26 | **PASS** (26 = top of OMC's range) |
| npm / npx | 11.19.0 | `C:\Program Files\nodejs\npm.cmd` (+ `.ps1` shim) | build | PASS (see §4 PowerShell note) |
| **Bun** | **1.4.2** (win32 x64) | **`D:\ClaudeData\bun\bin\bun.exe`** (new, first); Jan's 1.3.4 now second | gstack ≥ 1.3.3, tested 1.4.2 | **PASS** = gstack's tested version |
| Claude Code | 2.1.304 (also 2.1.299 bundle) | `%APPDATA%\Claude\claude-code\2.1.304\aed62990b91e\claude.exe` (desktop app bundle; **not on PATH**) | gstack, OMC | **PASS** for in-app use; see L3 |
| Python | 3.13.2 (system) · 3.12.15 (engine runtime) | `C:\Python313\python.exe` · `~\.whynot-cut\runtimes\r-6e4a68a292b4\Scripts\python.exe` | product | PASS |
| gh | 2.102.0 | `%LOCALAPPDATA%\Microsoft\WinGet\Links\gh.exe` | GitHub ops | PASS |
| curl / tar | Windows built-ins | `C:\WINDOWS\system32` | downloads, zips | PASS |
| uv | 0.9.16 | Jan's bundle only | not required | INFO |
| psmux / tmux | — | missing | OMC optional | **NOT INSTALLED** (optional) |
| WSL | stub only, no distro | `C:\WINDOWS\system32\wsl.exe` | optional | NOT INSTALLED (by choice, §5) |
| VS 2022 Build Tools | — (VS 2019 folders exist) | — | gstack `/cso` only | NOT INSTALLED (optional) |
| Docker | — | — | gstack `/cso` images only | NOT INSTALLED (optional) |
| ffmpeg | not on PATH | (engine/hosts ship their own; not re-verified) | product only | INFO |

## 3. PATH validation — VERIFIED

Fresh environment = Machine PATH + User PATH from the registry (what a newly started shell gets).

| Shell | `bun` resolves to | Version | Other tools |
|---|---|---|---|
| PowerShell (fresh env) | `D:\ClaudeData\bun\bin\bun.exe`, then Jan's | 1.4.2; `bun -e` → `win32 x64` | node, git, python OK |
| Git Bash (`bash -lc`, fresh env) | `/d/ClaudeData/bun/bin/bun`, then Jan's | 1.4.2 | node `/c/Program Files/nodejs/node`, git `/ucrt64/bin/git`, python `/c/Python313/python` |
| cmd (fresh env) | `D:\ClaudeData\bun\bin\bun.exe`, then Jan's | — | node, git OK |
| **Already-running processes** (the Claude app and every session it started, this one included; the Terminal panel shells) | **Jan's `bun.exe` 1.3.4** | — | they keep the PATH they started with |

Duplicates and conflicts:
- **bun**: two copies; ours wins in every new shell. Jan's stays (Jan app needs it; unrelated tooling is not touched).
- **python**: `C:\Python313` wins over the Microsoft Store alias stub in `WindowsApps` (harmless).
- **git**: one install (Git for Windows); `cmd\git.exe` outside Git Bash, `ucrt64\bin\git` inside it. Same build.
- **claude**: two bundles in the app folder (2.1.299, 2.1.304); none on PATH, so no conflict.
- User PATH cosmetic issues (left as is): `WindowsApps` listed twice (literal and `%USERPROFILE%`), a `\\?\`-prefixed Jan
  entry, LM Studio's bin.

## 4. Windows compatibility and permissions — VERIFIED

| Check | Value | Meaning |
|---|---|---|
| User | `LOQ`, **not elevated** | All Phase 1 work ran per-user, no admin needed |
| Developer Mode | **ON** (`AllowDevelopmentWithoutDevLicense=1`) | Non-admin native symlinks work |
| Symlink test (Git Bash, `MSYS=winsymlinks:nativestrict`) | file + dir symlinks created as `SymbolicLink`; test folder removed link-first | gstack's link helper will work |
| Long paths | **ON** (`LongPathsEnabled=1`) | deep `node_modules` / skill trees OK |
| PowerShell execution policy | all scopes Undefined → effective **Restricted** for interactive PowerShell 5.1 | `.ps1` files do not run there: use `npm.cmd`, and run gstack's **`./setup` from Git Bash** (its official path; `setup.ps1` just calls it). Policy left unchanged |
| Claude tool sandbox | Claude's Bash/PowerShell tools see a sandboxed `%APPDATA%\Roaming` (memory note, 10-13) | Global installs that write to AppData go through the **Terminal panel** (real shell), as done for Bun |
| Smart App Control (gstack README's known Windows blocker for its unsigned compiled binaries) | **OFF** (`HKLM\SYSTEM\CurrentControlSet\Control\CI\Policy VerifiedAndReputablePolicyState=0`) | gstack's compiled `browse`/`pdf` tools can run. Not changed |
| Antivirus | Kaspersky + Windows Defender registered | Bun's download, `bun build --compile` exe and its run were not blocked. Nothing disabled, no exclusions |
| Virtualisation | hypervisor present | WSL2 would be possible, but needs admin + reboot (not done) |
| `C:` home state | `~\.claude` → D (junction); `~\.gstack` and `%LOCALAPPDATA%\ms-playwright` do not exist yet | **Phase 2 must point gstack state and Chromium at D** (owner rule), see §8 |

## 5. Execution environment decision: **native Windows + Git Bash** (WSL2 not used)

- Premiere Pro, After Effects, the UXP panel, the CEP bridge and UPIA are Windows apps; WSL cannot drive them.
- Claude Code on Windows already runs its tools through Git Bash; gstack supports Windows only through Git Bash and
  explicitly refuses WSL's bash; OMC's hooks are node scripts that ran green on Windows in the pilot.
- The engine, its tests, the panel tests and the plugin validator all pass natively (§6).
- WSL2 would add a second filesystem, a second Node/Bun/Git, admin rights and a reboot, for one gain only: real tmux
  for `omc team`. The native Windows alternative for that is psmux (optional, not installed; decide in Phase 3).

## 6. Successful command tests — VERIFIED (clean export of `release/3.0` @ c963132 in `D:\ClaudeData\Temp\phase1-buildcheck`, no writes to the repo)

| # | Command | Result |
|---|---|---|
| 1 | `install-bun.cmd` (curl → SHA256 check → extract → PATH) | hash `ce4c1749…6405` matches `SHASUMS256.txt`; `bun --version` = 1.4.2 |
| 2 | `bun test` (tiny TS test) | 1 pass, 0 fail |
| 3 | `bun build --compile m.ts --no-compile-autoload-dotenv --no-compile-autoload-bunfig` then run the exe | `compiled-ok 5`; Bun 1.4.2 supports all four `--no-compile-autoload-*` flags gstack needs |
| 4 | `npm ci --ignore-scripts` in `adobe/` | 16 packages, 2 s |
| 5 | `npm test` in `adobe/panel-ui` | **296 / 296 pass**, 0 fail |
| 6 | `npm test` in `adobe/premiere-uxp` | **389 / 389 pass**, 0 fail |
| 7 | `tsc -p panel-ui/tsconfig.json --noEmit` · `tsc -p premiere-uxp/tsconfig.json --noEmit` | exit 0, no errors |
| 8 | `npm run build:plugin` (UXP plugin build) | built `premiere-uxp\build\plugin`, exit 0 |
| 9 | engine syntax check (`compileall` on `whynot-cut/engine`, engine Python 3.12.15) | exit 0 |
| 10 | `unittest discover -p 'test_emphasis*.py'` (engine runtime) | **135 tests OK** (20.6 s) |
| 11 | `claude plugin validate --strict .` and `… whynot-cut` (CLI 2.1.304) | marketplace ✔, plugin ✔ |
| 12 | Git Bash login shell, symlink creation | OK (§4) |
| 13 | Premiere / AE install check | Premiere Pro **26.5.2**, After Effects **26.5** present; CEP `PlayerDebugMode=1` (CSXS.12); bridge `ai.thewhynot.cut.bridge` (+ `.prev`) installed; UPIA present |

Full engine suite was **not** re-run: it is heavy (≈ 1 h) and the live system is already running suites through the
shared queue; the last full-suite result (8,899 OK, ENV-01) stays REPORTED.

## 7. Failed checks

| Check | Result | Impact |
|---|---|---|
| `tsc -p adobe/tsconfig.base.json` (my first, wrong invocation) | errors: missing `@types/node` for test files | **Not a project failure**: the base config is not a build entry; the per-package configs (test 7) are clean |
| `gh api` to api.github.com | 3 of ~8 calls timed out (`connectex … failed to respond`), retries succeeded | Flaky route to one GitHub IP: gstack's clone/upgrade and OMC marketplace calls need retries |
| Nothing else failed | | |

## 8. Remaining limitations (to carry into Phase 2+)

- **L1 — Running processes still see Jan's Bun 1.3.4.** The Claude desktop app and every session it started (this
  one, the executor, builders, routines, the Terminal panel) keep their old PATH until the **Claude app is fully
  restarted**. gstack hooks running inside those sessions would find 1.3.4: above setup's 1.3.3 hard floor, but **below** gstack's
  `engines.bun >=1.4.2` and the README's "v1.4.2+" — not acceptable for real use.
  A full app restart stops every running session; it is the owner's call (Phase 0 D1). Until then, Phase 2 commands
  can set PATH explicitly (`PATH=/d/ClaudeData/bun/bin:$PATH`) in the Terminal panel.
- **L2 — gstack state would land on C:.** `~/.gstack` and Playwright's Chromium (`%LOCALAPPDATA%\ms-playwright`) do not
  exist yet. Before `./setup`, Phase 2 should junction `~/.gstack` to `D:\ClaudeData\gstack` (as done for `~/.omc`)
  and set `PLAYWRIGHT_BROWSERS_PATH` to a D: folder, or run setup with `--no-browser` first.
- **L3 — `claude` is not on PATH.** Fine for slash commands inside the app (the brief's install route). Needed only for
  `omc team` CLI workers and terminal-launched sessions (helpers use `Start-Helper.cmd`, which finds the bundle). Not
  added, to avoid a second auto-updating Claude Code install; optional.
- **L4 — PowerShell scripts are blocked** (Restricted). Use `npm.cmd`, Git Bash `./setup`, `.cmd` wrappers. Not changed.
- **L5 — Optional, not installed:** psmux (OMC team/rate-limit detection), VS 2022 Build Tools + Docker (gstack `/cso`),
  WSL2, UXP Developer Tool app (the project installs `.ccx` through UPIA instead).
- **L6 — Live system.** All Phase 0 automation is still running (F1); installs that touch `~/.claude` (gstack in Phase 2,
  OMC scope in Phase 3) will be seen by every new session on the main seat.
- **L7 — Flaky GitHub API route** (see §7).

## 9. Resource constraints

32 GB RAM (58–64 % used during Phase 1 with the live system running) — new heavy jobs only below the 85 % brake.
RTX 4060 8 GB idle. Disk free: C: ≈ 201 GB, D: ≈ 235 GB (Bun ≈ 110 MB on D; gstack + Chromium expected ≈ 0.5–1 GB).
CPU i7-14700HX, 165+ bash processes from the live agents.

## 10. Environment recovery

- **Undo the Bun install:** run `D:\ClaudeData\setup-phase1\undo-bun.cmd` from a Terminal-panel or normal shell. It removes
  only the `D:\ClaudeData\bun\bin` entry from the current user PATH (keeps `REG_EXPAND_SZ` and any entry added later),
  removes `BUN_INSTALL`, and deletes `D:\ClaudeData\bun` only if the PATH step succeeded and the folder holds no links.
  The original PATH is kept in `user-path-before.txt` (never overwritten by a re-run) for a manual comparison.
- **Re-install / repair:** run `install-bun.cmd` again (it exits early if Bun is already there; delete the folder first
  to force). The pinned zip and `SHASUMS256.txt` stay in `D:\ClaudeData\downloads\bun-v1.4.2\`.
- **Upgrade later:** only to a version gstack lists in `GSTACK_BUN_VERIFIED`, by editing `VER` in the script.
- Everything else: `SETUP_BASELINE.md` §3.

## 11. Phase 2 readiness

**READY, with conditions.** All mandatory prerequisites for gstack (Claude Code, Git for Windows + Git Bash, Bun
1.4.2 = tested version, Node 26.7) and for OMC (Claude Code, Node within 20–26) are installed and verified on this PC; the
subscription on all three seats is REPORTED from Phase 0 (§8 of the audit), not re-checked here. Conditions before running gstack's `./setup`:
1. Run it from Git Bash in the Terminal panel with `D:\ClaudeData\bun\bin` first on PATH (L1), or after a full Claude app restart.
2. Point `~/.gstack` and the Chromium download at D: (L2).
3. Inspect `setup` before running it (brief), and keep Codex/telemetry off as the brief says.
Optional prerequisites (psmux, VS 2022 Build Tools, Docker, WSL2, `claude` on PATH) are documented in §2/§8 and are
not needed for Phase 2.
