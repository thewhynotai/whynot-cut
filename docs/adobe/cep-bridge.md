# The WhyNot Cut CEP extension (bundle 3.0.0)

**Audience:** the installer track, the engine and anyone reviewing the extension. This page describes what is on disk,
every file shape the extension reads or writes, the install rule, the engine-start allowlist and the legacy family.
Sources: `adobe/cep-bridge/**` (the shell), `whynot-cut/engine/reel/lib/cep_bundle.py` (assembly, install rule,
`config.json`, the signed install), `whynot-cut/engine/reel/lib/cep_queue.py` (the queue protocol), `tools/sign_zxp.py`
(signing) and the plan
`docs/superpowers/plans/2026-10-13-3.0-phase-6-t63-bridge.md` (3.0 T6.3).

## 1. Ids and names
- **Bundle id:** `ai.thewhynot.cut.bridge`. **Extensions:** `ai.thewhynot.cut.bridge.panel` and
  `ai.thewhynot.cut.bridge.daemon`.
  - These ids are the same as in 3.1.1. A new id would leave 3.1.1 loaded beside the new bundle.
- **Visible name:** "WhyNot Cut" (`ExtensionBundleName` and the After Effects menu). "Bridge" is an internal word and
  never appears on screen.
- **Hosts:** the bundle lists Premiere Pro (`PPRO [22.0,99.9]`) and After Effects (`AEFT [24.0,99.9]`).
  - The hidden **daemon** runs in both.
  - The visible **panel** is After Effects only. Premiere has the UXP panel.

## 2. Layout of an installed bundle
```
<CEP extensions>/ai.thewhynot.cut.bridge/
  CSXS/manifest.xml        bundle 3.0.0, the panel (AEFT, ./ui/index.html, 340x640, min 280x320) and the daemon
                           (./daemon.html, AutoVisible false, starts with the app)
  daemon.html              loads js/bridge.js (the daemon role: the queue, the heartbeat, the engine start)
  ui/index.html            the After Effects panel; loads ../js/bridge.js (panel role: read-only) and ui/js/panel.js
  ui/js/panel.js           one sentence per state, plus Copy diagnostics
  ui/tokens.css            brand/tokens.css copied as-is (the one brand token source)
  js/bridge.js             the CEP side: roles, queue, heartbeat, engine start
  jsx/wnc_host.jsx         the host script (WNC_HOST.alive)
  jsx/wnc_ppro_lib.jsx     the libraries, copied from whynot-cut/templates/** (their single source)
  jsx/wnc_ae_bridge.jsx
  jsx/wnc_ae_lib.jsx
  jsx/wnc_motion_lib.jsx
  build.json               see section 3.2
  META-INF/signatures.xml  present only in a signed install (the ZXP, section 10)
  mimetype                 present only in a signed install (ZXPSignCmd adds it)
```
- `<CEP extensions>` is `%APPDATA%\Adobe\CEP\extensions` on Windows and `~/Library/Application Support/Adobe/CEP/extensions`
  on macOS.
- `cep_bundle.assemble(dst)` builds exactly this layout from the repo. The copies of `ui/tokens.css` and `jsx/wnc_*.jsx`
  are build artefacts, never a second source.
- Nothing inside the extension is ever written after install. In particular there is no `bridge-config.json` (the
  3.1.x engine wrote one; 3.0 never writes or reads it).

## 3. Shapes

### 3.1 `~/.whynot-cut/bridge/config.json` (installer and engine write it; the daemon reads it)
```json
{"schema": 1, "engine_home": "<absolute>", "launcher": "<absolute>" | null, "written_by": "installer" | "engine",
 "at": "<ISO 8601>"}
```
- **Location:** always under the user's home, never inside the extension, never under `WHYNOT_HOME`. The daemon cannot
  see environment variables set for Claude.
- **Rights:** user-only (the folder 0700 and the file 0600 on POSIX). It holds no secret.
- **Atomic write:** a temp file, then a rename (`cep_bundle.write_config`).
- **`engine_home`:** the resolved engine home. The daemon uses it only when it is an absolute path to an existing folder.
  Otherwise it falls back to the first of `~/.whynot-cut`, `~/.reel-editor` and `~/.dr-nahla-editor` that holds an
  engine (a `current` file or a `venv`), else `~/.whynot-cut`.
- **`launcher`:**
  - It is `<engine_home>/bin/wnc-engine.cmd` on Windows and `<engine_home>/bin/wnc-engine` on macOS: the installer's shim
    (installer track, step 7b).
  - `write_config` fills it only when that file exists, and writes `null` otherwise.
  - **Installer rule:** write the shim first, then `config.json`. The daemon re-reads `config.json` every 30 s, so a
    later write is picked up without restarting the app.
- **The daemon's rule for reading it:**
  - it must be a regular file (`lstat`; a link is ignored);
  - `schema` must be 1.

### 3.2 `<extension>/build.json` (written by `assemble`)
```json
{"product": "3.0.0", "build": "<16 hex>", "sha": "<git commit>" | null, "protocol": 4,
 "libs": {"wnc_ppro_lib.jsx": "<sha256>", "wnc_ae_bridge.jsx": "<sha256>", "wnc_ae_lib.jsx": "<sha256>",
          "wnc_motion_lib.jsx": "<sha256>"}}
```
- **`build`:** the first 16 hex of the sha256 over the sorted `(posix path, sha256)` pairs of every other file in the
  bundle. The same sources always give the same build.
- **`libs`:** these must equal `cep_bundle.expected_libs()` of the engine that drives the bundle. Otherwise jobs are
  refused with "the WhyNot Cut extension in <app> is from another build".

### 3.3 The heartbeat: `<engine_home>/{ppro,ae}-queue/bridge.heartbeat` (only the daemon writes it, every second)
```json
{"at": 1760000000000, "busy": false, "role": "daemon", "host": "PPRO" | "AEFT", "hostVersion": "26.5.2",
 "bundle": "3.0.0", "version": "3.0.0", "protocol": 4, "build": "<16 hex>", "libs": {"<name>": "<sha256>"},
 "current": "<job id>" | null, "action": "<action>" | null,
 "engine_start": {"at": 1760000000000, "outcome": "<outcome>"} | null}
```
- `version` equals `bundle`. It is what engines before protocol 4 read.
- `libs` is hashed from `<extension>/jsx/` when the daemon starts.
- `engine_start` is section 5's last decision. `outcome` is one of:

| Outcome | Meaning |
|---|---|
| `running` | `engine.json` names a live pid. |
| `no_launcher` | There is no `config.json`, or its `launcher` is null. |
| `refused` | The launcher failed the allowlist. The reason is in the daemon's log only. |
| `spawned` | An attempt was made. The next check, 30 s later, decides whether it worked. |
| `spawn_error` | The spawn threw or emitted `error`. |
| `failed` | The launcher exited non-zero, or the engine was still down at the next check. |
| `gave_up` | 5 failures in a row. There are no more attempts until the app restarts. |

### 3.4 Jobs and results (protocol 4; `cep_queue.py` documents every queue file)
- **`<id>.data.json`:** the job's data, as ASCII JSON.
- **`<id>.job.json`:** `{id, action, lib | script, data_file, submitted, expires_at}`.
  - **`lib`:** a bundled library of this host (`wnc_ppro_lib.jsx` in Premiere, `wnc_ae_bridge.jsx` in After Effects),
    resolved inside `<extension>/jsx/` and realpath-confined.
  - **`script`:** the compatibility path. It is accepted only directly inside `<engine_home>/{ppro,ae}-scripts/`, with
    the allowlisted file name.
  - **Anything else:** answered `{ok: false, error: "script not allowed"}`.
- **The job id is the job file's name.** Every `.result.json` and `.claimed` path is built from that name, never from
  JSON.
  - A JSON `id` that differs from the file name is answered `{ok: false, error: "bad job id"}` inside the queue and never
    run.
  - So is a file name outside `^[\w.-]+$`.
- **`<id>.running`:** the atomic claim (a rename).
- **`<id>.claimed`:** `{at, by}`. The caller's result timeout starts here.
- **`<id>.result.json`:** `{ok, result | error, at}`, written atomically.
- **Expired jobs:** a job past `expires_at` is answered `{ok: false, error: "expired"}` and never run.

## 4. Install rule (`cep_bundle.installed` + `decide_install`)

### 4.1 How `installed(ext)` classifies an installed extension
| Family | Condition |
|---|---|
| `bundle` | It carries a readable `build.json`. |
| `unknown` | It is **signed** (`META-INF/signatures.xml`) but has no readable `build.json`. Signed is checked before legacy. |
| `legacy` | It is **unsigned**, has no `build.json`, and is ours: the id `ai.thewhynot.cut.bridge` at a version up to and including 3.1.1 (3.1.1, 3.1.0, 3.0.0 before the bundle, 2.x), or the reel-editor `com.nh.bridge`. |
| `unknown` | Anything else (for example an unsigned 3.1.2, or another id). |

- **`legacy` here is the install rule's word: "ours and older, replace it without `--force`".** The queue is stricter:
  it still drives exactly 3.1.1 (section 7, decision 15). An unsigned 3.1.0 is therefore replaced by the next install,
  and until then the queue refuses it and says to update it.

### 4.2 What `decide_install` does with the new build
| Case | Action |
|---|---|
| Nothing is installed | install |
| `force` | replace |
| `legacy` | replace |
| `unknown` | keep |
| The same `build` | skip |
| The same `build`, unsigned, and this build is signed | replace (the ZXP replaces the dev copy of the same sources: the `build` id does not cover `META-INF/`) |
| The installed `product` is newer | keep |
| A signed install, and this build is unsigned | keep |
| Otherwise | replace |

- **Keep** means the extension is left as it is. The answer says that `--force` replaces it.
- **Installer:** compare the installed `build.json` with yours. Never write into the extension. Write `config.json`
  (section 3.1) in step 7b.

## 5. Engine start: the spawn allowlist (`js/bridge.js`, daemon role only)

### 5.1 When it checks
- At start, then every 30 s.
- It acts only when `~/.whynot-cut/bridge/engine.json` is missing, or its pid is dead (`process.kill(pid, 0)`; `EPERM`
  counts as alive).
- **The token:** `engine.json` is parsed with a reviver that keeps only `pid`. The token in it is never kept, logged or
  written. A parse error's text is never logged either, because it can quote the file.

### 5.2 What it may start
It may start only `config.json` `launcher`, and only when **all** of these hold:
1. It is an absolute path to a regular file (`stat`).
2. `realpath(launcher)` equals `realpath(engine_home)/bin/wnc-engine.cmd` on Windows (compared without case), or
   `.../bin/wnc-engine` on macOS. A link that resolves elsewhere, another name, or another folder is refused.
3. Neither the launcher, its realpath nor `engine_home` contains any of `" % ^ & | < > !`. cmd.exe acts on these even
   inside quotes.
4. **On POSIX:** it is owned by the user (`uid === process.getuid()`) and not group- or world-writable (`mode & 0o022`
   is 0).

### 5.3 How it starts it
There are no arguments, and nothing comes from the queue, the network or the job files.
- **Windows:**
  ```js
  spawn(ComSpec, ["/d", "/s", "/c", '""' + launcher + '""'],
        {detached: true, windowsHide: true, stdio: "ignore", cwd: engine_home, windowsVerbatimArguments: true}).unref()
  ```
  - `ComSpec` is used only when it is an absolute path to a file named `cmd.exe`. Otherwise
    `C:\Windows\System32\cmd.exe` is used.
  - **The quoting is node's own `shell: true` form, and it differs from the plan.** `/s` strips one pair of outer quotes,
    so the quoted path is quoted once more, and `windowsVerbatimArguments` stops node from escaping those quotes.
  - Measured on Windows 11 with the launcher in a folder with a space:
    - the plan's single pair (`'"' + launcher + '"'`) exits 1, with or without verbatim;
    - the double pair runs the launcher.
  - `test_cep_bridge.py` checks this with the real cmd.exe.
- **macOS:** `spawn(launcher, [], {detached: true, windowsHide: true, stdio: "ignore", cwd: engine_home}).unref()`.

### 5.4 Limits
- At most one attempt per 30 s.
- After 5 failed attempts in a row it stops (`gave_up`). A successful start resets the count.
- The panel role never spawns, never claims a job and never writes a heartbeat.

## 6. The After Effects panel (minimal until the designed panel of Addendum E)
- **Content:** one sentence per state, the brand tokens (`ui/tokens.css`), and no command text. A test runs every `ui/**`
  string through `adobe/panel-ui/src/commands.ts`, the detector the panel kit uses.

| State | Sentence |
|---|---|
| running | "WhyNot Cut is running in After Effects." |
| busy | "WhyNot Cut is working in After Effects." |
| starting (the panel loaded under 10 s ago, or the daemon's `engine_start` is `spawned`) | "Starting WhyNot Cut…" |
| the daemon is not loaded | "WhyNot Cut isn't running in After Effects: restart After Effects" |

- **Copy diagnostics** copies JSON with these fields:
  - `product`, `bundle`, `build`, `host`, `hostVersion`, `panel_loaded_at`, `now`, `state` and `queue`;
  - the daemon's last heartbeat (it holds no secret).

## 7. The legacy family (exactly 3.1.1; removed in 3.1)
- **Frozen copy:** `whynot-cut/tests/fixtures/cep-bridge-3.1.1/` (bridge.js and manifest, byte-identical to the live
  install).
- **How 3.1.1 differs:**
  - its heartbeat has no `protocol`;
  - it reads its engine home from the `bridge-config.json` the 3.1.x engine wrote into the extension;
  - its visible panel works the queue when no daemon beats.
- **How the engine drives it:**
  - it syncs the renamed libraries into `<engine_home>/{ppro,ae}-scripts/`;
  - it sends `script:` jobs;
  - the libraries keep `var NHPP = WNCPP;` and `var NHAE = WNCAE;` for its eval tail.
- **Refusals:** every other version without `protocol`, and every protocol other than 4.
  - **An older bridge of ours** (no `protocol`, a version below 3.1.1, such as 3.1.0): "the WhyNot Cut extension
    running in <app> is the older 3.1.0: update it (this engine needs WhyNot Cut 3.0.0)". The `how` says to run
    `reel ppro-install` (it replaces it without `--force`) or the installer, then restart the app. Nothing is queued.
- **Doctor:**
  - shows a legacy 3.1.1 install as an amber, optional fix (it still works in 3.0; the update replaces it);
  - shows an older one of ours (such as 3.1.0) as a fix that is not optional: "update it (the update replaces it)";
  - flags an unsigned bundle in a plugin build without the source (a dev build over a signed install) in amber.

## 8. Doctor (`onboard.bridge_info`)
- **Reads:**
  - the installed extension through `cep_bundle.installed` (`family`, `product`/`version`, `build`, `signed`);
  - `config.json` (`config`, `queue_base` = `engine_home`, `launcher`);
  - the Premiere heartbeat's `engine_start`.
- **PlayerDebugMode:** `debug_mode_needed` is true only for an unsigned install. A signed one loads without it.
  `loads` = installed and (signed or PlayerDebugMode on).
- **When the extension is missing, the fix depends on the plugin build:**
  - with the source in this checkout, it is `reel setup`;
  - otherwise, "install WhyNot Cut with its installer (the signed extension comes with it)".

## 9. Known notes (accepted, review of Tasks 1–4)
- **The `config.json` lstat/read race.** The daemon checks `lstat(config.json).isFile()` and then reads the file. A
  process that swaps the file for a link between the two calls would be read once.
  - Accepted: `~/.whynot-cut/bridge/` is a user-only folder, and anyone who can write there already runs as the user.
  - The engine-start allowlist re-checks the launcher itself (realpath, owner, mode), so a swapped `config.json` cannot
    widen what is started.
- **The daemon creates the engine home.** When the resolved engine home does not exist, the daemon role creates it
  (`mkdirSync(BASE, {recursive: true})`) so the queue and heartbeat have a place.
  - With a stale `config.json` this can create an empty folder at the old path. It holds only the queue folders, with
    no engine; `engine_home` must already exist for `config.json` to be used at all, so this happens only through the
    fallback `~/.whynot-cut`.
  - Accepted for 3.0. The installer writes `config.json` after the engine home exists.

## 10. The signed extension (Task 6)

### 10.1 Signing: `tools/sign_zxp.py` (stdlib only; run by hand, never by tests or the engine)
- **`setup`** (once per machine; everything lives in `~/.whynot-cut/signing/`, never in the repo):
  - **ZXPSignCmd** from `Adobe-CEP/CEP-Resources` at commit `8897cfaf9801b0ad5321951199dd831a82964583`, path
    `ZXPSignCMD/4.1.3/x64/ZXPSignCmd.exe` (Windows x64), 4542464 bytes, sha256
    `ffc2223167225ce61d024eb463fc5ad1a1be16133f99ef334a646f7311916c98`. The exe is not Authenticode-signed: the size and
    sha256 are the check, before the copy and before every use.
  - `setup --from <file>` copies a file that is already downloaded, after the same check. Without `--from` the pinned
    `raw.githubusercontent.com` URL is fetched into a temp folder and checked the same way. A mismatch is refused and
    nothing is written.
  - **macOS:** the pin is not set yet (`ZXPSignCMD/4.1.3/macOS` at the same commit, decision 10). `setup` and `build`
    refuse with "macOS pin not set".
  - **The certificate** is self-signed and made once: `EG Cairo "The Why Not AI" "WhyNot Cut"`, valid 3650 days, in
    `whynot-cut.p12`. An existing certificate is never replaced.
  - **Its password** is `secrets.token_urlsafe(32)` (never starting with `-`). It lives only in the OS credential store,
    target `WhyNotCut/zxp-signing`: the Windows Credential Manager (`CredWriteW`/`CredReadW` through ctypes) or the macOS
    keychain (`security`).
- **`build`:**
  1. assembles the bundle (section 2) in a temp staging folder;
  2. refuses the staging tree when it holds any symlink, junction, `.DS_Store` or `__MACOSX` (Adobe's KnownIssue2024: a
     ZXP that holds links fails its signature check after a UPIA install);
  3. `ZXPSignCmd -sign <staging> <zxp> <p12> <password> -tsa <url>`. `-tsa` is always passed (default
     `http://timestamp.digicert.com`), and a failed timestamp fails the build (decision 11);
  4. `ZXPSignCmd -verify <zxp> -certinfo` must report a verified signature and a valid timestamp. The archive must hold
     `META-INF/signatures.xml` and exactly the staged files with the same CRC; only `META-INF/*` and `mimetype` may be
     added;
  5. an atomic rename to `whynot-cut/adobe/WhyNotCut-Bridge-3.0.0.zxp`, then every other `*.zxp` there is removed:
     exactly one is left (`tools/release.py --fill-artefacts` refuses two). A failed build leaves the folder as it was.
- **`verify`** repeats step 4 on the built ZXP.
- **The password is never printed, logged or put in an error.** Every command shown has it as `***`, and the tool's
  output is scrubbed of it. ZXPSignCmd itself takes it as an argument, so it is visible to the user's own processes
  while signing runs.
- The ZXP is a build artefact: `whynot-cut/adobe/.gitignore` has `*.zxp`, and `package.py` ships it with the plugin.

### 10.2 Installing: `cep_bundle.install_zxp` and `ppro_bridge.install`
- **`ppro_bridge.install()` (`reel ppro-install`, `reel setup`) picks its source in this order:**
  1. the signed ZXP the plugin carries (`cep_bundle.zxp_path()`);
  2. the unsigned dev build from `adobe/cep-bridge`, only with `WHYNOT_BRIDGE_DEV=1` (decision 9);
  3. otherwise `ok: false`. A checkout with the source says to sign it (`python tools/sign_zxp.py build`) or to set
     `WHYNOT_BRIDGE_DEV=1`; a plugin without either says "install WhyNot Cut with its installer".
  - A signed install needs no PlayerDebugMode, so `editor_must_run` is empty for it.
- **`install_zxp(zxp, ext)`:**
  - **Signed only:** a ZXP without `META-INF/signatures.xml` is never installed.
  - **Every entry is checked before anything is written.** An absolute path, a drive, a backslash, an empty, `.` or
    `..` part, a link entry or a duplicate refuses the whole archive.
  - The files are extracted into `<ext>.new`, each one checked against its CRC-32 and size. The manifest must name
    `ai.thewhynot.cut.bridge`.
  - The install rule (section 4) decides. To install, `ext` becomes `<ext>.prev` (one previous copy is kept; the next
    install replaces it) and `<ext>.new` becomes `ext`. A failed swap puts the previous copy back.
  - A refused ZXP leaves `ext` untouched and no `.new` behind. An `ext` that is a link (a development checkout) is left
    alone.
- **Gate 6 check:** CEP must not load `<ext>.prev` beside `ext` (both hold the same bundle id). The installer track
  keeps `.prev` the same way.
