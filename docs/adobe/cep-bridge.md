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
- **Only the live extension folder is ever in `<CEP extensions>`.** CEP loads every folder there by its manifest, so a
  second copy of the bundle (a staged new one, a kept previous one) would load beside it. Those live in
  `<CEP root>/.wnc-staging/{new,prev}` instead: `%APPDATA%\Adobe\CEP\.wnc-staging` on Windows and
  `~/Library/Application Support/Adobe/CEP/.wnc-staging` on macOS (`cep_bundle.staging_dir()`, the parent of the
  extensions folder: the same volume, so the swap is two atomic renames).
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
 "engine_start": {"at": 1760000000000, "outcome": "<outcome>", "reason": "<reason>" | null} | null,
 "engine_retry": "slow" | null}
```
- `version` equals `bundle`. It is what engines before protocol 4 read.
- `libs` is hashed from `<extension>/jsx/` when the daemon starts.
- `engine_start` is section 5's last decision. `outcome` is one of:

| Outcome | Meaning |
|---|---|
| `running` | `engine.json` names a live pid. |
| `no_launcher` | There is no `config.json`, or its `launcher` is null. |
| `refused` | The launcher failed the allowlist. `reason` says which check (table below). |
| `spawned` | An attempt was made. The next check, 30 s later, decides whether it worked. |
| `spawn_error` | The spawn threw or emitted `error`. |
| `failed` | The launcher exited non-zero, or the engine was still down at the next check. |
| `gave_up` | 5 failures in a row. The daemon keeps trying, one attempt every 5 minutes (H2); `engine_retry` is `"slow"`. `reason` is `gave_up`. |

- **`reason`** is a fixed code, never a path or any text read from disk (`null` for the other outcomes):

| Reason | The check that failed (section 5.2) |
|---|---|
| `not_absolute` | `launcher` is not an absolute path. |
| `metachar_in_path` | The launcher, its realpath or `engine_home` holds one of `" % ^ & \| < > !`. |
| `not_found` | The launcher does not exist. |
| `not_a_file` | It is not a regular file. |
| `unresolvable` | Its realpath or `engine_home`'s cannot be resolved. |
| `not_the_launcher` | Its realpath is not `realpath(engine_home)/bin/wnc-engine(.cmd)`. |
| `outside_profile` | Windows: its realpath is outside `%USERPROFILE%`. |
| `not_owner` | POSIX: it is not owned by this user. |
| `writable_by_others` | POSIX: it is group- or world-writable. |
| `gave_up` | Outcome `gave_up` (5 failed attempts). |

- `engine_retry` is `"slow"` once 5 attempts in a row have failed and `null` otherwise (an engine that comes up ends it).
- **Doctor:** with the daemon alive, `refused` and `gave_up` become one plain fix sentence for the editor
  (`onboard.ENGINE_START_FIXES`): no code, no path.

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
- **Orphans (H2):** when the daemon starts, every `<id>.running` a previous run left is answered
  `{ok: false, error: "interrupted", reason: "bridge restarted", at}` and removed. It is never run again. A `.running` whose
  result already exists only loses the stale file. The visible panel never does this.
- **A result that cannot be written (H2):** the daemon keeps the job claimed (`<id>.running`) and tries again 1 s, 2 s and 4 s
  later (3 retries, on later ticks, so the queue keeps moving). After the last failure it writes the minimal marker
  `<id>.error` = `{ok: false, error: "result write failed", at}` and removes the job file. `reel serve` reads a marker, or a
  job seen in the queue that vanished with no result, as a failed job at once (`serve/jobs.py`, `serve/adapters.py`
  QueueTracker). `cep_queue._wait` does not read the marker yet (executor hunk, H5): it times out as before.
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
4. **On Windows:** its realpath is inside `%USERPROFILE%` (the installer puts the engine home there; a launcher
   anywhere else is refused, `outside_profile`).
5. **On POSIX:** it is owned by the user (`uid === process.getuid()`) and not group- or world-writable (`mode & 0o022`
   is 0).

**What is spawned is the checked realpath** (and its `cwd` is `realpath(engine_home)`), never the configured string:
a link swapped after the checks cannot redirect the spawn.

### 5.3 How it starts it
There are no arguments, and nothing comes from the queue, the network or the job files.
- **Windows:**
  ```js
  spawn(ComSpec, ["/d", "/s", "/c", '""' + realpath(launcher) + '""'],
        {detached: true, windowsHide: true, stdio: "ignore", cwd: realpath(engine_home), windowsVerbatimArguments: true}).unref()
  ```
  - `ComSpec` is used only when it is an absolute path to a file named `cmd.exe`. Otherwise
    `C:\Windows\System32\cmd.exe` is used.
  - **The quoting is node's own `shell: true` form, and it differs from the plan.** `/s` strips one pair of outer quotes,
    so the quoted path is quoted once more, and `windowsVerbatimArguments` stops node from escaping those quotes.
  - Measured on Windows 11 with the launcher in a folder with a space:
    - the plan's single pair (`'"' + launcher + '"'`) exits 1, with or without verbatim;
    - the double pair runs the launcher.
  - `test_cep_bridge.py` checks this with the real cmd.exe.
- **macOS:** `spawn(realpath(launcher), [], {detached: true, windowsHide: true, stdio: "ignore", cwd: realpath(engine_home)}).unref()`.

### 5.4 Limits
- At most one attempt per 30 s.
- After 5 failed attempts in a row it does not stop: the outcome is `gave_up`, the heartbeat says `engine_retry: "slow"`, and
  it makes one attempt every 5 minutes (H2). A successful start resets the count and ends the slow retry.
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
- **When the extension is missing, the fix depends on what `reel setup` can install:**
  - the signed ZXP the plugin carries (`cep_bundle.zxp_path()`), or the dev source with `WHYNOT_BRIDGE_DEV=1`: it is
    `reel setup`;
  - otherwise (a plugin without either, or a checkout without a signed ZXP and without the variable), "install WhyNot
    Cut with its installer (the signed extension comes with it)".
- **Engine start:** with the daemon alive, a heartbeat `engine_start` of `refused` or `gave_up` is one plain fix
  sentence (section 3.3).

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
  - **macOS:** `ZXPSignCMD/4.1.3/macOS/ZXPSignCmd` at its own commit `fcee8de5537d2dd2ed3d91d5a495b7041155b280` (the
    macOS file came after the Windows one), 6391280 bytes, sha256
    `bc773fae0b97416fc7a462e7dadcc00270428a9913480c9b78b5606ff1cfb095`, git blob
    `38b958508c5a249d12418845dd07ad43e4f34a92`.
    - It is **Mach-O x86_64 only**: on Apple Silicon it runs through Rosetta 2 (`softwareupdate --install-rosetta`
      once; `setup` says so on arm64).
    - It is **not notarized**. `setup` fetches it with `urllib` (or copies `--from`), never through a browser, so it
      carries no quarantine attribute and Gatekeeper does not stop it. Never tell anyone to disable Gatekeeper.
    - After the pin check `setup` makes it `0755`.
    - It is a **build-time tool** on the signing machine only: it never ships with the plugin or the installer.
  - **The certificate** is self-signed and made once: `EG Cairo "The Why Not AI" "WhyNot Cut"`, valid 3650 days, in
    `whynot-cut.p12`. An existing certificate is never replaced.
  - **Its password** is `secrets.token_urlsafe(32)` (never starting with `-`). It lives only in the OS credential store,
    target `WhyNotCut/zxp-signing`: the Windows Credential Manager (`CredWriteW`/`CredReadW` through ctypes) or the macOS
    keychain. On macOS the password goes to `security -i` on **stdin** (never on an argv, which `ps` shows to every
    user), and is read back to check the write.
- **`build`:**
  1. assembles the bundle (section 2) in a temp staging folder;
  2. refuses the staging tree when it holds any symlink, junction, `.DS_Store` or `__MACOSX` (Adobe's KnownIssue2024: a
     ZXP that holds links fails its signature check after a UPIA install);
  3. `ZXPSignCmd -sign <staging> <zxp> <p12> <password> -tsa <url>`. `-tsa` is always passed (default
     `http://timestamp.digicert.com`), and a failed timestamp fails the build (decision 11);
  4. `ZXPSignCmd -verify <zxp> -certinfo` (timeout `VERIFY_TIMEOUT` = 120 s; a timeout, exit 124, is retried once,
     any second failure fails the build and keeps no ZXP) must report a verified signature and a
     `Timestamp: Valid ...` line. ZXPSignCmd 4.1.3 prints
     `Timestamp: Valid and within certificate validity dates at time of signing` for a timestamped signature and
     `Timestamp: None` without `-tsa` (that fails; `tests/fixtures/zxpsigncmd/` holds the real output). The archive must hold
     `META-INF/signatures.xml` and exactly the staged files with the same CRC; only `META-INF/*` and `mimetype` may be
     added;
  5. an atomic rename to `whynot-cut/adobe/WhyNotCut-Bridge-3.0.0.zxp`, then every other `*.zxp` there is removed:
     exactly one is left (`tools/release.py --fill-artefacts` refuses two). A failed build leaves the folder as it was.
- **`verify`** repeats step 4 on the built ZXP.
- **ZXPSignCmd's output** goes to temp files, never pipes: a timeout kill on Windows cannot block on a pipe a child of
  the tool inherited. The files are read back and scrubbed of the password.
- **Every path handed to ZXPSignCmd is resolved first** (the tool, the certificate, the staged folder, the output and
  the verified ZXP; `sign_zxp.real`). ZXPSignCmd cannot open a `.p12` through a Windows junction: with `~/.whynot-cut`
  a junction to D:, it answered "Arguments are invalid" (exit 3), while the same file by its real path parsed. The pin
  is checked on the resolved tool.
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
  - **Signed only:** a ZXP without `META-INF/signatures.xml` is never installed. "Signed" here means that file is
    present: the engine does not check the signature itself. The real check is CEP's, when the app loads the
    extension with PlayerDebugMode off (0): an extension whose signature fails does not load.
  - **Size limits:** at most 2,000 entries and 64 MB uncompressed in total (the bundle is about 20 files and under
    1 MB); a file that holds more data than its entry declares is refused while it is written.
  - **Every entry is checked before anything is written.** An absolute path, a drive, a backslash, an empty, `.` or
    `..` part, a part ending in `.` or a space (Windows drops those, so `a.` and `a` are one file), a link entry or a
    duplicate refuses the whole archive.
  - The files are extracted into `<CEP root>/.wnc-staging/new` (section 2), each one checked against its CRC-32 and
    size. The manifest must name `ai.thewhynot.cut.bridge`.
  - The install rule (section 4) decides. To install, `ext` becomes `.wnc-staging/prev` (one previous copy is kept;
    the next install replaces it) and `.wnc-staging/new` becomes `ext`. Both renames are inside one `try`:
    - the first fails: "the installed one was left as it was";
    - the second fails: the previous copy is renamed back, "the previous one was put back";
    - that fails too: the message names `.wnc-staging/prev`, and the next install puts it back (below).
    - A staged `new` never survives a failure.
  - **Recovery (`cep_bundle.recover`) runs at the start of every install or update** (`install_zxp`,
    `install_source`): when `ext` is missing and `.wnc-staging/prev` exists (a crash between the two renames), the
    previous copy is put back first. It also migrates the Task 6 layout: an `<ext>.new` left in the extensions folder
    is removed, an `<ext>.prev` becomes `.wnc-staging/prev` (or `ext` itself, when `ext` is missing).
  - A refused ZXP leaves `ext` untouched and no staged `new` behind. An `ext` that is a link (a development checkout)
    is left alone.
- **Gate 6 check:** after an update the extensions folder holds only `ai.thewhynot.cut.bridge` (a test checks it).
  The installer track is asked to keep its previous copy outside the extensions folder too: `.wnc-staging/prev`, the
  same recovery at the start of install and update, and the uninstaller removes `.wnc-staging`.
