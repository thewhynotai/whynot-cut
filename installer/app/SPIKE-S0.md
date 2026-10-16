# SPIKE S0 (ET1-16): can this PC build a Tauri 2 app with a per-user toolchain?

Date: 2026-10-16. Machine: Lenovo LOQ 15IRX9, Windows 11 Pro 10.0.26300, a normal (non-admin) user, Kaspersky active.
Everything was installed per user on drive D. No admin, no UAC prompt, no licence acceptance, no PATH or registry change.

## Verdict

**Local per-user build WORKS** with `x86_64-pc-windows-gnullvm` + llvm-mingw (route 2a). Routes 2b and 2c were not needed and were not tried.

- Result: a Tauri 2.12.4 window app built from a hand-written `Cargo.toml` + `tauri.conf.json` + static `index.html`.
  No npm, no `create-tauri-app`, no Visual Studio Build Tools.
- It starts, opens a window titled `WNC Spike S0` (class `Tauri Window`) in about 0.2 s and renders the page through WebView2.
  It closes cleanly (`CloseMainWindow`), and it leaves no WebView2 process behind.
- **Recommendation: use the local per-user route for development and tests on this PC. Keep CI `windows-latest` (MSVC) as the reference and release build.**
  Nothing is needed from Yunus for the toolchain. VS Build Tools (UAC plus the Microsoft licence) stay OUT.
- Two caveats (details below) decide what the local build is good for:
  1. the gnullvm exe is not standalone: it needs `libunwind.dll` and `WebView2Loader.dll` next to it;
  2. the "fully static" variant (`+crt-static`) was removed from disk after it was read, which looks like antivirus. Do not rely on it.

## What already existed (read-only probe)

| Item | Result |
|---|---|
| rustc / cargo / rustup | none on PATH, no `%USERPROFILE%\.cargo`, nothing under `D:\ClaudeData\rust` |
| MSVC | `vswhere` exists but lists no installation; no `link.exe`, no `cl.exe` |
| Windows SDK | none (`C:\Program Files (x86)\Windows Kits\10\Lib` absent) |
| WebView2 Evergreen runtime | 155.0.4283.45 (HKLM, WOW6432Node `EdgeUpdate\Clients\{F3017226-...}`) |
| Node / npm | v26.7.0 / 11.19.0 (not used) |
| gcc / clang / 7z / curl on PATH | none (git-bash `curl` and Windows `tar` exist) |
| User rights | not administrator |
| Free space | C 201 GB, D 291 GB |

## What was installed (all per user, pinned)

| Component | Version | Source | sha256 |
|---|---|---|---|
| rustup-init.exe (msvc-built installer, needs no linker) | rustup 1.29.1 | `https://static.rust-lang.org/rustup/dist/x86_64-pc-windows-msvc/rustup-init.exe` | `6f4bef66261261fcb43131be8720bab817d403a09edec7455c371974b90bdb7e` (matches the `.sha256` file published beside it) |
| Rust toolchain | **1.99.1** (58cf8f9c3, 2026-10-13), host `x86_64-pc-windows-gnullvm`, profile minimal | static.rust-lang.org through rustup | verified by rustup against the channel manifest `channel-rust-stable.toml` (dated 2026-10-15) |
| llvm-mingw | **20261006**, `ucrt-x86_64` (clang/LLVM 23.1.1) | `https://github.com/mstorsjo/llvm-mingw/releases/download/20261006/llvm-mingw-20261006-ucrt-x86_64.zip` (190,836,485 bytes) | `317492c456aa27ee607a5919f1d2d38dcdc1112516a24d0bf4b00d078f52d17a` (matches the digest GitHub shows for the release asset) |
| crates | `tauri =2.12.4`, `tauri-build =2.7.3` (408 crates in `Cargo.lock`; 2.12.x needs Rust >= 1.90) | crates.io through cargo | cargo checksums in `Cargo.lock` |

Locations: `RUSTUP_HOME=D:/ClaudeData/rust/rustup`, `CARGO_HOME=D:/ClaudeData/rust/cargo`, llvm-mingw in
`D:\ClaudeData\rust\llvm-mingw-20261006\llvm-mingw-20261006-ucrt-x86_64`. Temp and build output:
`D:/ClaudeData/Temp/wnc-tests/et1-16/` (scratch app in `app/`, `TEMP`/`TMP` pointed at `tmp/` there).
Nothing was written to the user PATH, to `HKCU\Environment`, or to the Uninstall keys (`--no-modify-path`; checked afterwards).

How to build again (per process only):

```
export RUSTUP_HOME=D:/ClaudeData/rust/rustup CARGO_HOME=D:/ClaudeData/rust/cargo
export PATH="/d/ClaudeData/rust/cargo/bin:/d/ClaudeData/rust/llvm-mingw-20261006/llvm-mingw-20261006-ucrt-x86_64/bin:$PATH"
export CARGO_TARGET_DIR=D:/ClaudeData/Temp/wnc-tests/et1-16/target
cd D:/ClaudeData/Temp/wnc-tests/et1-16/app && cargo build --release      # through heavy.sh: job <label> -- ...
```

llvm-mingw on PATH provides both the linker driver (`clang`) and `windres` (for the Windows version-info and manifest resource that `tauri-build` compiles).
Both were found and worked; the exe carries the product name "WNC Spike" in its version info.

## The scratch app

Hand-written, minimal (kept under `D:/ClaudeData/Temp/wnc-tests/et1-16/app`; ET1-17 will make the real one):

- `Cargo.toml`: `tauri =2.12.4` with default features (wry/WebView2), `tauri-build =2.7.3`, release profile `opt-level="s"`, `lto`, `codegen-units=1`, `panic="abort"`, `strip`.
- `build.rs`: `tauri_build::build()`. `src/main.rs`: `tauri::Builder::default().run(tauri::generate_context!())`, `windows_subsystem = "windows"`.
- `tauri.conf.json`: `frontendDist ./dist`, one window 760x540 (`resizable:false`), `csp: default-src 'self'`, `bundle.active:false`.
- `dist/index.html`: one static page. `icons/icon.ico` and `icon.png` (generated 32x32 placeholders; `tauri-build` needs `icons/icon.ico` on Windows).

## Measurements

| Measure | Value |
|---|---|
| rustup-init (download of 4 components + install) | 35 s |
| llvm-mingw download (190.8 MB) / extract (`Expand-Archive`) | 24 s / 139 s (extract is slow, most likely the on-access scan of the many files) |
| Cold `cargo build --release` (includes crate download, 408 crates) | **4 min 51 s** (293 s) |
| Cold rebuild with other RUSTFLAGS (crates already cached) | 4 min 08 s |
| Relink only (the app crate changed) | 70 s |
| Exe size (release, stripped, LTO) | **3,155,968 bytes = 3.01 MB**, sha256 `6020b2fd0c50802c05feb93ead1e026e91d1be60d2909b340b3f0c0baefee86e` |
| Side files needed next to the exe | `WebView2Loader.dll` 160,880 bytes (copied by the build into the output folder), `libunwind.dll` 183,808 bytes (from llvm-mingw `bin/`, sha256 `b0636a4281610124704adb2be2edf5642e830d86c68b7f27dbc9c8154705a780`) |
| Start to window visible | 245 ms and 178 ms (two runs); working set about 28 MB; 6 `msedgewebview2.exe` processes belong to it while it runs |
| Disk, persistent | rustup 690 MB + cargo 330 MB (registry 318 MB) + llvm-mingw 715 MB = about **1.7 GB** on D (plus the 191 MB zip, deletable) |
| Disk, per build tree | `target/` about 990 MB for the release build of this tiny app |
| RAM | started at 62 to 63 percent (the heavy.sh limit is 85); the build did not push it near the limit |

Network use in the whole spike: static.rust-lang.org, github.com (llvm-mingw release), crates.io and its index. Nothing else.

## Needs the WebView2 runtime?

Yes. The exe loads `WebView2Loader.dll`, which locates the installed Evergreen runtime (here 155.0.4283.45) and starts `msedgewebview2.exe` processes with it.
The app does not bundle the runtime. Windows 11 and updated Windows 10 have it. A PC without it is the "WebView2 missing" case, which was NOT tested here (the runtime was not removed from this PC).
ET1-20/21 must decide how to handle it: a check with a clear message, not a silent install. WebView2 also wrote its profile to
`C:\Users\LOQ\AppData\Local\ai.thewhynot.wnc-spike\EBWebView` (7.7 MB; deleted after the test). The real app should set `WEBVIEW2_USER_DATA_FOLDER` (or the Tauri data directory) deliberately.

## Antivirus (Kaspersky)

- No visible prompt, warning or message at any point: not for rustup-init, llvm-mingw, the compile, or the start of the dynamic exe.
  The `Kaspersky Event Log` holds 0 records, and the Defender operational log shows nothing.
- **One finding.** I built a second variant with `RUSTFLAGS="-C target-feature=+crt-static"` (static libunwind, so no `libunwind.dll`). It linked fine (3,191,808 bytes).
  Each time I read it (hash, objdump) the read failed first with "being used by another process" / "Permission denied", and the file, both in `release/` and in `deps/`, was gone about one to three minutes later. This happened three times.
  When I left the file completely untouched it survived (195 s). So the pattern is: read, then locked, then deleted. That looks like an on-access antivirus scan that removes the file, but **I saw no message and cannot read Kaspersky's quarantine from a normal user account, so the cause is inferred, not confirmed.**
  The dynamic exe (same source, no crt-static) survived all the same reads and runs.
  I did not add exclusions and did not try to get around it.
- Practical effect: do not use `+crt-static` on this PC. If a freshly built unsigned exe ever disappears, suspect Kaspersky first. (Optional check for Yunus: Kaspersky, Reports, Quarantine, look for `wnc-spike.exe`.)
- Related: a first run of the dynamic exe without `libunwind.dll` showed a Windows "System Error" dialog ("libunwind.dll was not found"). That was a missing file, not antivirus. I dismissed it.

## Blockers and limits

1. **The gnullvm exe is not standalone.** It needs `libunwind.dll` (llvm-mingw runtime) and `WebView2Loader.dll` beside it. On MSVC the loader is linked statically and there is no libunwind, so the MSVC build is one exe.
   So the local gnullvm build is for development, UI tests and toolchain checks. It is not what testers get.
2. **The release artifact should come from CI** (`windows-latest`, MSVC): one exe, the standard Tauri 2 Windows target, no extra DLLs.
3. **Not tested here:** `cargo tauri build` (the bundler, NSIS or portable, which is ET1-21; it needs `tauri-cli` and downloads NSIS at build time, so pin and check it then), the WebView2-missing case, code signing (phase 2), any macOS build.
4. gnullvm is a tier 2 Rust target and Tauri itself documents MSVC as its Windows target. Both are reasons to keep CI MSVC as the reference. If a gnullvm-only bug ever shows up, CI is the answer.
5. Two full test suites were running through heavy.sh while this ran. The timings above were measured under that normal load.

## Recommendation for the plan

- **Route: local per-user (llvm-mingw + gnullvm) for development, CI MSVC for release.** ET1-17 can scaffold and build locally. ET1-22 (the CI workflow file) still uses `windows-latest`.
- Pin: Rust **1.99.1** (`installer/app/rust-toolchain.toml`), `tauri =2.12.4`, `tauri-build =2.7.3`, llvm-mingw **20261006 ucrt x86_64** (sha256 above). Commit `Cargo.lock` in ET1-17.
- Keep `RUSTUP_HOME` and `CARGO_HOME` on D, set per process (the build wrapper sets them; nothing global).
- Local manual start: copy `libunwind.dll` next to the exe (or put llvm-mingw `bin` on PATH for that process).
- For Yunus: nothing needed. VS Build Tools are not required. The only optional item is the Kaspersky quarantine check above.
