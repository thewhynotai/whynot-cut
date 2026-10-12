# Addendum A — Kalam, Hush, Tidy: portability audit and port plan (Windows + macOS)

| | |
|---|---|
| Date | 2026-10-12 |
| Request | Yunus: «خلي الكود دا يشتغل ماك و ويندوز» (make this code work on macOS and Windows) |
| Stage | 1 of the port: upstream imported unchanged, Windows baseline recorded, audit + plan. No logic ported yet |
| Upstream | `adobe/tools/{kalam,hush,tidy}/_upstream/` (commit 2d87b5f, 88 files, `adobe/tools/UPSTREAM-SHA256.txt`) |
| Binding | Addendum A §A0 (every FR, §8 rule, §11 test kept), §A2 layers, §A3 #1, §A5 tests, §A6b names + gates |

## للمالك (ملخص بالمصري)

جبنا كود الأدوات التلاتة (كلام، هَش، تايدي) زي ما هو بالظبط جوه WhyNot Cut كمرجع للقراية بس، وكل ملف متأكدين إنه
نفس النسخة الأصلية حرف بحرف (88 ملف). شغّلنا الاختبارات الأصلية على الويندوز ده: منطق كلام نفسه (التقسيم،
القواعد، التنضيف، الكابشن) شغال على ويندوز من غير أي تعديل — 71 اختبار من 101 نجحوا، والباقي وقف عشان مكتبات
مش متسطبة لسه (torch، soundfile، anthropic) أو ملفات صوت تجربة موجودة على الماك بتاع المطوّر بس. اختبارات
الجافاسكريبت بتاعة كلام وتايدي كلها نجحت على ويندوز (145 من 145). هَش ملوش اختبارات خالص، فأول خطوة هنكتب له
اختبارات على الكود الأصلي زي ما هو، وبعدين ننقله، ونفس الاختبارات لازم تنجح.
أكبر حاجات بتمنع الشغل على ويندوز: هَش وتايدي بيحطوا ملفاتهم في مسار ماك (`~/Library/Application Support`)
وبيفتحوا الفولدرات بأمر `open` بتاع الماك، هَش بيدوّر على preset تصدير الصوت في مسارات ماك بس فالتصدير هيفشل على
ويندوز، وويسبر بتاع هَش شغال بـ MLX (أبل بس). كل ده عندنا حله جاهز في WhyNot Cut (فولدر المحرك، faster-whisper
بالكارت NVIDIA أو المعالج، `reel serve`). الخطة: نبدأ دلوقتي بالحاجات اللي مش محتاجة بريمير (محرك كلام بالبايثون،
ويسبر هَش، المنطق الصافي بتاع التلاتة باختبارات بتشتغل على الماك والويندوز)، وبعد ما توصيل UXP↔CEP يخلص (T6.7)
ننقل عمليات بريمير واللوحات. كل الأسامي هتبقى WhyNot Kalam / Hush / Tidy ومفيش "Hoka" في المنتج.

---

## 1. Import record

- **Commit 2d87b5f** `chore(3.0): Addendum A — owner's Kalam/Hush/Tidy source imported unchanged as _upstream
  reference`: `adobe/tools/{kalam,hush,tidy}/_upstream/**` (kalam 54, hush 12, tidy 22 = 88 files), plus
  `adobe/tools/README.md` (read-only rule, ported code lives elsewhere), `UPSTREAM-SHA256.txt`, and
  `adobe/tools/.gitattributes` (`*/_upstream/** -text`, so `* text=auto eol=lf` at the root never rewrites them; every
  text file is already LF, `tests/panel/fixtures/tiny.mogrt` is a stored zip with a CR byte).
- **sha256:** the listing of the source (`new plugin code/`, excluding `._*`, `.DS_Store`, `__pycache__`,
  `.pytest_cache`: 155 junk files left out) equals the listing of the copy, file for file.
- **Not picked up anywhere:** `unittest discover -s whynot-cut/tests` (outside `whynot-cut/`); `tools/jsx_lint.py`
  (reads only `wnc_*.jsx`; run after the import: "no wnc_*.jsx files found"); the `adobe/` npm workspaces
  (`panel-ui` / `premiere-uxp` `tsconfig` include only their own `src`/`test`; tests are `test/*.test.ts`); the
  no-real-client-names test (`test_contract.py::test_no_real_client_name_and_no_machine_user_in_any_fixture`) scans
  only `whynot-cut/tests` fixtures.
- **Packaging gap (pre-existing, executor-owned):** `package.py` zips `ROOT.rglob("*")` minus
  `SKIP_DIRS = {__pycache__, .git, .pytest_cache, docs, .superpowers, tools}`. `adobe/` is not skipped, so the 2.x
  marketplace zip would carry `adobe/tools/**/_upstream` (and `adobe/node_modules`, already today). Fix before any
  `package.py` release: add `adobe` (or at least `_upstream` and `node_modules`) to `SKIP_DIRS`, with a test.
  `tools/release.py` only globs `<plugin>/adobe/*.zxp|*.ccx` and is not affected.
- **Privacy scan of upstream fixtures** (REAL_CLIENT_TOKENS, machine user, names): no WhyNot Cut client token. Found,
  reference-only, must **not** be copied into WhyNot Cut fixtures or shipped:
  - developer machine path `/Users/macstoreeg/Metrial/shhh Hoka/...`: `kalam/tests/premiere/test_host.jsx:3`,
    `tidy/tests/premiere/test_host.jsx:3-6`, `tidy/tests/premiere/test_sync_host.jsx:3`,
    `kalam/engine/tests/test_verify_bundle.py:49` (as a negative fixture);
  - a demo speaker "Sherif" / "Dr Sherif" (likely a real doctor's clip): `kalam/tests/panel/stub.js:49`,
    `kalam/engine/tests/test_cli.py:11`, `test_pipeline_slow.py:11,21-38`; `kalam/tests/panel/captions.json` is a real
    medical transcript of that clip (157 lines);
  - project name "Rog 2" (a real project per the Tidy PRD): `tidy/tests/panel/stub.js:20,28`,
    `kalam/tests/panel/test_platform.js:36`; `/Volumes/Work/Clinic/clinic.prproj` in `kalam/tests/panel/stub.js:49`.
  The ported tests use fictional names (e.g. the existing `example-*` style) and H13 clips in `whynot-test/`.
- **Upstream files the PRDs reference but were not supplied** (record, ask once if needed): `install_kalam.sh`,
  `build_windows.sh`, `windows/` (install.bat/ps1), `install.sh`/`uninstall.sh` (Hush), `install_tidy.sh`,
  `run_premiere_test.sh`, the design specs `docs/superpowers/specs/2026-10-12-*.md`, Kalam `demo/sherif_*.srt`
  (needed by `test_correct.py:145-156`), Hush `presets/Hush_WAV48k16.epr` (`hush/jsx/host.jsx:93`), Hush test media
  (`~/Library/Application Support/Hush/bench/sherif.wav`, `.../Hush/test/speech.wav`). None blocks the port: the
  installers are replaced by WhyNot Cut's installer (A3 #2), the preset falls back to Premiere's own, the demo and
  media come from H13.
- **Owner facts (2026-10-12):** Tidy here is the latest release = PRD v2 (its `CSXS/manifest.xml:9` says 1.0.0:
  stale, `_upstream` left unchanged). Ownership confirmed (Yunus holds the rights).

## 2. Baseline on this Windows PC (read-only temp copy)

Copy: `C:\Users\LOQ\AppData\Local\Temp\claude\addA-baseline\src\`. Python = WhyNot Cut engine runtime
`r-6e4a68a292b4` (CPython 3.12.15; numpy 2.5.4, faster-whisper 1.2.1, ctranslate2 4.8.2, onnxruntime 1.31.0; **no**
pytest, torch, torchaudio, transformers, soundfile, anthropic, onnx-asr, mlx*). pytest 9.1.1 was installed into a
temp `--target` folder (`addA-baseline\pylib`) put on `PYTHONPATH`; nothing was installed into the runtime or
`~/.whynot-cut`. Env: `PYTHONUTF8=1 HF_HUB_OFFLINE=1 HF_HOME=<temp>`. Each file was run separately (a collection
error aborts a whole-suite run).

### 2.1 Kalam engine (pytest, 101 tests in 13 files)

| File | Tests | As-is result | Reason | Logic-only diagnostic (stubs) |
|---|---|---|---|---|
| test_align | 1 | 1 failed | `torch` missing (`align.py:86` imports it before the unromanizable-window branch) | pass |
| test_captions | 18 | 18 passed | | pass |
| test_clean | 9 | 9 passed | | pass |
| test_cli | 2 | 2 failed | child engine: `soundfile` missing; also needs `~/Library/Application Support/Hush/bench/sherif.wav` + Kalam models; child env is `PATH=/usr/bin:/bin` with no `SYSTEMROOT` (`test_cli.py:22-23`) | fail (child env drops PYTHONPATH; mac media) |
| test_correct | 17 | collection error | `anthropic`, `httpx2` missing | 16 pass, 1 fail: `demo/sherif_raw_model.srt` not supplied |
| test_doctor | 2 | collection error | `soundfile` missing (kalam_engine imports audio.py) | pass (portable backend, nvidia-smi probe ran) |
| test_pipeline_slow | 3 | collection error | `soundfile`; mac media paths (`test_pipeline_slow.py:10-14`), real models | 2 fail + 1 error: media at `C:\Users\LOQ\Library\Application Support\...` |
| test_platform | 5 | collection error | `anthropic` (via `kalam.correct`) | 4 pass, **1 fail = real Windows bug**: `claude_candidates(..., windows=False)` builds `str(Path("/Users/x")/...)` which renders `\Users\x\.local\bin\claude` on Windows (`platform.py:29`, `test_platform.py:17-19`) |
| test_portable | 12 | 12 passed | GPU→CPU fallbacks, chunk cuts, providers (all faked) | pass |
| test_rules | 12 | 12 passed | | pass |
| test_setup_models | 2 | 2 passed | | pass |
| test_units | 9 | 9 passed | | pass |
| test_verify_bundle | 9 | 9 passed | (objdump text is faked) | pass |
| **Total** | **101** | **71 passed, 3 failed, 27 not collected, 0 skipped** | | **94 passed, 6 failed, 1 error** |

The diagnostic pass put throwaway stubs first on `PYTHONPATH` (`anthropic` exception classes, `httpx2.Request`,
`soundfile.read` via stdlib `wave`, empty `torch`/`torchaudio`) only to separate "dependency missing" from "logic
breaks on Windows". It is not a result for the record; the as-is column is. Conclusion: Kalam's pure engine logic
(rules, captions DP, units, cleaning, correction contract + faithfulness gate, portable backends, doctor) already runs
unchanged on Windows; the only logic failure is the mac-candidate path string.

### 2.2 Panel / pure JS (jsc suites, run with node 26.7.0 + a 12-line jsc shim)

The upstream JS tests target macOS JavaScriptCore `jsc` (`print`, `readFile(path[, 'binary'])`, `load(path)`,
top-level `this` as `window`). They are plain ES5, so a shim (`print`→console.log, `readFile`→fs, `load`→
`vm.runInThisContext`, cwd = tool root) runs them unchanged on Windows.

| Suite | Files | Checks | Result |
|---|---|---|---|
| Kalam panel (`tests/panel/test_{html,mogrt,platform,range}.js`) | 4 | 35 | 35/35 PASS (incl. Windows paths, `file:///C:/` extension path, Arabic user dir, safe names) |
| Tidy pure (`tests/test_{classify,lint,media,plan,sync}.js`) | 5 | 110 | 110/110 PASS |
| Kalam/Tidy browser harness (`tests/panel/index.html` + `stub.js`) | 2 | — | not run (needs a served page in a browser; UI wiring tests) |
| Hush | 0 | — | **no upstream tests** (see §6.1: characterization first) |

### 2.3 Premiere host tests (need Premiere: listed, not run)

| Test | Checks | Needs | Windows blockers inside the test itself |
|---|---|---|---|
| `kalam/tests/premiere/test_host.jsx` | 13 | `KalamTest.prproj`, `hush_test.mp4` in `~/Library/Application Support/Kalam/test` | `$.evalFile('/Users/macstoreeg/...')` (l.3), `Folder('~/Library/...')` (l.5), project guard `indexOf('/Kalam/test/KalamTest.prproj')` (l.4/8) |
| `tidy/tests/premiere/test_host.jsx` | 11 | builds `TidyRun <ms>.prproj` in `~/Library/Application Support/Tidy/test` | l.3-7 same; guard `indexOf('/Tidy/test/')` (l.12) always aborts on Windows (backslash paths) — safe failure |
| `tidy/tests/premiere/test_sync_host.jsx` | 4 | 3 cams + 2 mics media | l.3-4, guard l.10 |
| `tidy/tests/premiere/make_podcast_media.py` | — | `av`, `soundfile`, numpy | portable (pathlib), deps missing in the core runtime |

Premiere 2026 is installed here; both Windows WAV presets exist:
`C:\Program Files\Adobe\Adobe Premiere Pro 2026\Settings\EncoderPresets\Wave48mono16.epr` and
`...\MediaIO\systempresets\3F3F3F3F_57415645\Waveform Audio 48kHz 16-bit.epr` (Kalam/Tidy already list them; Hush
does not, §3.2).

## 3. Portability audit (every file)

Legend: **B** = blocks Windows, **W** = wrong/fragile on Windows, **N** = neutral (runs on both as is). "Reuse" names
the WhyNot Cut module that already solves it. Every Node-service and host row also changes layer in the port (A2:
UXP has no Node and cannot spawn, so Node services move to `reel serve`, host ops to `WNC_*` CEP compat ops).

### 3.1 Kalam (54 files)

| File:line | Assumption | Sev | Windows equivalent / port | Reuse |
|---|---|---|---|---|
| `engine/kalam/platform.py:8-19` | backend: `mlx` only on darwin with mlx_whisper, else portable; `KALAM_BACKEND` override | N | keep; macOS also needs `mlx` only on Apple Silicon | `lib/whisper_backends.choose_backend` / `is_apple_silicon` / `mlx_available` |
| `engine/kalam/platform.py:22-29` | Claude CLI candidates; mac branch uses `str(Path(...))` (backslashes on Windows, test fails); misses LOCALAPPDATA `Programs\claude\claude.exe` and the desktop-bundled CLI | W | use the installer's order (exe first, `.cmd` last, bundled CLI newest first); POSIX strings via `PurePosixPath` | `installer/core/wnc_installer/claude.py:68 claude_candidates` (+ `tools/find_claude.py`) |
| `engine/kalam/correct.py:59-63` | `subprocess.run([exe, ...args])` | W | an npm `claude.cmd` runs through cmd.exe: `--tools ""` and the `--json-schema {...}` argument (quotes, braces) are re-parsed by cmd (BatBadBut class). Prefer `claude.exe`; for a `.cmd` resolve to `node <cli.js>` or refuse with a `how` | `wnc_installer/claude.py:105 claude_command` |
| `engine/kalam/correct.py:65-70` | `os.access(c, X_OK)` as "is executable" | W | on Windows X_OK is true for any existing file; check `is_file()` + suffix in PATHEXT | same |
| `engine/kalam/correct.py:60-61,85` | UTF-8 pipes, temp dir `kalam-cc-` | N | fine (explicit `encoding="utf-8"`); timeout 900 s, cancel must kill the CLI's tree | `lib/parallel.kill_tree` (taskkill /T) |
| `engine/kalam/device.py:6-18` | CTranslate2 CUDA count → cuda/fp16 else cpu/int8 | N | keep | `whisper_backends._device_tries`, `load_ct2` |
| `engine/kalam/device.py:24-39` | Windows: add `torch\lib` to the DLL path for cuBLAS/cuDNN | W | WhyNot Cut's core runtime has no torch; cuBLAS comes from the pinned NVIDIA redist. Kalam pack: torch lib dirs added after `enable_cuda_libs()` | `lib/plat.enable_cuda_libs`, `cuda_lib_dirs`, `cuda_libs_missing` |
| `engine/kalam/transcribe.py:23-67` | `_whisper` / `_parakeet_words` via `mlx_whisper` / `parakeet_mlx` (Metal) | mac-only by design | mac backend; Windows uses lines 180-256 | `whisper_backends._mlx_runner` (mlx not verified live yet, T9.3/H6) |
| `engine/kalam/transcribe.py:70-163` | portable: faster-whisper (CUDA→CPU once), onnx-asr Parakeet, 25 s chunks in the quietest 200 ms | N | keep as is (this is Kalam's Windows path, PRD §4.1) | model loading via `whisper_backends` snapshot rules; `lib/portability.py` (non-ASCII engine home breaks CTranslate2 narrow paths) |
| `engine/kalam/transcribe.py:166-178` | model folders under `models_dir` (`ct2-*`, `parakeet-*-onnx`) | N | models move under the engine home (pack) | `common.models_dir()`, `plat.engine_home()` |
| `engine/kalam/align.py:53-62` | MMS aligner from the HF cache (`snapshot_download(REPO)`), torch + transformers + torchaudio | B (deps) | Kalam pack runtime (A3 #9); HF cache = engine home models, offline | `whisper_backends._snapshot` / offline rules; pack lock (Phase 7) |
| `engine/kalam/align.py:22-50` | torch device cuda else cpu; no MPS | N | keep | — |
| `engine/kalam/audio.py:1-25` | `soundfile` (libsndfile) WAV read, naive resample | B (dep) | soundfile wheels ship libsndfile for Windows; or read PCM with stdlib `wave` (Premiere export is 16-bit PCM, like `hush_whisper.load_wav`). Must stay bit-identical in output | add `soundfile` to the pack lock, or stdlib reader with a parity test |
| `engine/kalam_engine.py:17-20` | `KMP_DUPLICATE_LIB_OK` on Windows (CT2 + torch OpenMP) | N | keep in the pack process | — |
| `engine/kalam_engine.py:37-40` | `DEFAULT_MODELS` = `%LOCALAPPDATA%\Kalam\models` / `~/Library/Application Support/Kalam/models` | W | `~/.whynot-cut/tools/kalam/models` (A6b) or the shared models dir | `plat.engine_home()` |
| `engine/kalam_engine.py:53-59` | `nvidia-smi` probe | N | fine (PATH on Windows); doctor reuses ours | `plat` GPU/doctor checks, `reel doctor` |
| `engine/kalam_engine.py:109-110,153-157` | stdout JSON lines `ensure_ascii=False`; `write_text` of SRT/JSON | W | Windows text mode writes CRLF (`Path.write_text` translates `\n`); stdout needs UTF-8. Write with `newline="\n"`; run with `PYTHONUTF8=1`/`PYTHONIOENCODING=utf-8` | `serve/daemon.py:315` env; `lib/srt.py` writer |
| `engine/kalam_engine.py:183` | settings file holds the API key; deleted by the panel at `loading` | security | port: engine deletes it itself on read; private file | `serve/security.private_file` / `open_private` (Windows DACL) |
| `engine/setup_models.py:20-40,65-72,90-106` | MLX conversion (`mlx.core`) mac-only; CT2 conversion needs torch+transformers | B (deps) | run conversions once at release time; ship converted packs (A3 #9, Phase 7) | `components.json` packs, installer |
| `engine/run_tests.sh:3` | `$HOME/Library/Application Support/Kalam/venv/bin/pytest` | B | replaced by `tools/test.sh -p test_kalam_*.py` (unittest, runtime python) | `tools/test.sh` |
| `engine/pytest.ini` | pytest config | N | tests become unittest under `whynot-cut/tests` with `import _isolation` | COORDINATION rule 7 |
| `engine/tools/verify_bundle.py:49,74,83` | `/usr/bin/objdump`; "no /Users/" check; Mac-built Windows bundle | mac-only tool | obsolete: WhyNot Cut builds the runtime on the target OS (installer runtime contract) | `lib/runtime.py`, installer |
| `engine/tools/compare_backends.py:15,22-23` | mac model/HF paths; pass bar 95 % / median 0.08 s | W | port into the parity job with engine-home paths; **use the PRD §11 bar (text ≥ 96 %, onsets within 15 ms)** | `whisper_backends.parity` |
| `engine/kalam/{captions,clean,phrases,rules,similar,units}.py`, `default_rules*.txt`, `__init__.py` | pure Python / text | N | port unchanged (baseline: their 48 tests pass on Windows as is) | — |
| `engine/tests/test_cli.py:10-12,22-23` | mac media + `PATH=/usr/bin:/bin` env without `SYSTEMROOT` | B (test) | media from `whynot-test/` (H13); env = runtime contract env | `_isolation`, H13 |
| `engine/tests/test_pipeline_slow.py:10-14` | mac media, macOS `say` clip | B (test) | H13 clips, skip when absent | — |
| `engine/tests/test_platform.py:17-19` | expects POSIX strings from `Path` | W (test exposes the bug above) | keep the assertion; fix the code | — |
| `engine/tests/test_correct.py:145-156` | `demo/sherif_*.srt` (not supplied) | B (fixture) | owner supplies the 28-line demo pair or an equivalent fictional pair (A0: the test is kept) | — |
| `engine/tests/{test_align,test_captions,test_clean,test_doctor,test_portable,test_rules,test_setup_models,test_units,test_verify_bundle}.py` | | N | port as unittest | — |
| `js/platform.js:9-19` | data dirs `%LOCALAPPDATA%\Kalam` / `~/Library/Application Support/Kalam`, `venv/bin/python` / `python\python.exe` | W | `~/.whynot-cut/tools/kalam/` (A6b); python = engine runtime | `plat.engine_home`, `plat.engine_runtime` / `venv_python` |
| `js/platform.js:22-28` | child env forces UTF-8 | N | keep (serve does it) | `serve/daemon.py:315` |
| `js/platform.js:30-35` | reveal/open: `explorer /select,` / `open -R` | N | done by the engine for UXP | engine reveal helper (new, tiny) |
| `js/platform.js:38` | `safeName` strips `\/:*?"<>|` | W | also reserved names (CON, NUL…), trailing dot/space, MAX_PATH | `common.slug` patterns; add a Windows-name test |
| `js/platform.js:41-46` | Local Templates `%APPDATA%\Adobe\Common\Motion Graphics Templates` / mac Library | N | keep | — |
| `js/engine.js:4-7` | `cep_node.require('fs','child_process')`, `process.platform` | B in UXP | all Node services move to `reel serve` | `serve/router.py`, contract v4 |
| `js/engine.js:31,70` | settings + job file `mode: 384` (0600) | W | chmod is a no-op on Windows; use a DACL | `serve/security.private_file` |
| `js/engine.js:74-75,100` | spawn engine python; `child.kill()` | W | engine-side process with tree kill; JSON-lines kept (PRD §13) | `lib/parallel.kill_tree` |
| `js/engine.js:81` | stdout split on `\n` | N | `JSON.parse` tolerates the trailing `\r` | — |
| `js/engine.js:112-133` | report on `~/Desktop` (OneDrive-redirected on many Windows PCs; fallback to HOME) | W | report into the engine home + diagnostics bundle (A3 #2), redacted; reveal it | `reel doctor` diagnostics (redaction rules of `serve/security.AuditLog`) |
| `js/cep.js:12-38` | `evalScript('kalam_<fn>(json)')`; `cleanPath` handles `file:///C:/` | N (CEP) | becomes a `WNC_KALAM.*` compat op via the bridge queue; UXP routes | `lib/cep_queue.py`, `serve/router.py`, contract `kalam_*.schema.json` (T6.1 reserved, e2492c1) |
| `js/mogrt.js:16-34,49-66` | pure zip/definition parsing, `folderOf` handles `\` | N | reuse as is (35/35 checks pass on Windows) | — |
| `js/mogrt.js:67-104` | Node `fs`/`zlib`/`crypto` gallery scan, thumbs cache | B in UXP | engine service (stdlib `zipfile`, `zlib`); same output shape | — |
| `js/main.js:88` | SRT next to the project in "Kalam Captions" | N | name change (A6b); path via engine | — |
| `js/main.js:210` | `window.cep.fs.showOpenDialogEx` | B in UXP | UXP `storage.localFileSystem.getFileForOpening` | UXP plugin (`adobe/premiere-uxp`) |
| `js/main.js:234` | `fileUrl` = `'file://' + 'C:/…'` (two slashes before a drive) | W | `file:///C:/…`; in UXP use a data/blob URL | — |
| `js/{range,i18n}.js`, `index.html`, `css/kalam.css` | pure / UI | N | UI is rebuilt as a UXP tab (A2), strings reused | `adobe/panel-ui` |
| `jsx/host.jsx:83-91` | WAV preset: mac `Contents/...` + Windows `Settings/EncoderPresets` candidates | N | moves to the shared `WNC_AUDIO` (one implementation) | contract `audio_export_range` |
| `jsx/host.jsx:5-212` | ExtendScript, ASCII, ES3, `KALAM` namespace; `$.os` only reported | N (both OS) | rename to `WNC_KALAM` (A6b), jsx lint | `tools/jsx_lint.py` |
| `CSXS/manifest.xml:3,9,25,31-33` | `com.hoka.kalam`, CEP 11 `--enable-nodejs --mixed-context`, PlayerDebugMode (unsigned) | B (install) | ops ship inside the signed WhyNot Cut Bridge; no separate CEP panel, no PlayerDebugMode (A3 #2) | `templates/premiere/cep_bridge`, T6.3 signing |
| `tests/panel/*` | jsc tests | N | run under node (shim) on both OS | §6.1 N2 |
| `tests/premiere/test_host.jsx:3-8` | mac paths, `/`-only guard | B (test) | `$.fileName`-relative includes; separator-neutral guard; test projects under `whynot-test/` | — |

### 3.2 Hush (12 files)

| File:line | Assumption | Sev | Windows equivalent / port | Reuse |
|---|---|---|---|---|
| `js/engine.js:8-12` | data dir `~/Library/Application Support/Hush`, `venv/bin/python`, `hf/` | **B** | `~/.whynot-cut/tools/hush/` (A6b); python = engine runtime; HF = engine models | `plat.engine_home`, `common.models_dir` |
| `js/engine.js:25` | `cp.spawn('open', [dir])` | **B** | `explorer <dir>` / `open`; done by the engine for UXP | Kalam `platform.js:33` logic |
| `js/engine.js:28-40` | export → read the whole WAV in Node → envelope in the panel | B in UXP | export via `WNC_AUDIO`; envelope in the engine (same maths as `wav.js`/`detect.js`, parity-tested) or in the panel from a file UXP may read | contract `audio_export_range` |
| `js/engine.js:43-48` | cache keeps last 3 scans | N | keep in `tools/hush/cache` | — |
| `js/engine.js:53-83` | spawn `hush_whisper.py` without UTF-8 env; `kill('SIGTERM')` | W | engine-side job, UTF-8 env, tree kill | `serve/daemon.py:315`, `parallel.kill_tree` |
| `js/cep.js:29-34` | `extensionPath` keeps `/C:/...` on Windows (no drive fix, unlike Kalam) | **W** | Kalam's `cleanPath`; moot once ops live in the bridge | Kalam `cep.js:30-35` |
| `py/hush_whisper.py:12,61-72` | `mlx-whisper` (Apple GPU only), model `mlx-community/whisper-large-v3-turbo` | **B** | faster-whisper large-v3-turbo (CUDA fp16 / CPU int8) with the same disfluency prompts (`PROMPTS`, l.15-19) as `initial_prompt`; mlx on Apple Silicon; `HUSH_WHISPER_MODEL` kept (PRD §7.2) | `whisper_backends.make_runner` (`initial_prompt` supported, `CT2_REPOS["large-v3-turbo"]`) |
| `py/hush_whisper.py:22-46` | stdlib `wave` reader, 16 kHz decimation | N | keep (no ffmpeg; PRD §9) | — |
| `py/hush_whisper.py:49-50,78-79` | JSON lines `ensure_ascii=False` | W | needs UTF-8 stdout on Windows | runtime env |
| `py/hush_whisper.py:78-80` | writes `{language, words, elapsed}` | note | PRD §7.2 says `{language, duration, words}`: the port adds `duration` (PRD wins, A0) and keeps `elapsed` | — |
| `js/{detect,fillers,wav}.js` | pure, UMD (`window` or `this`) | N | reuse as is; run under node | — |
| `js/main.js:166-180` | Simple/Tight settings computed inside the DOM code | N | extract unchanged into a pure `settings` function (needed by `reel hush plan` from chat) | — |
| `js/main.js:340` | `E.openFolder` | B | see engine.js:25 | — |
| `jsx/host.jsx:90-99` | WAV preset: `extDir/presets/Hush_WAV48k16.epr` (file not supplied) + **mac-only** `Contents/...` paths | **B** | add the Windows candidates (`Settings/EncoderPresets/Wave48mono16.epr`, `MediaIO/systempresets/...`) — i.e. use the shared `WNC_AUDIO` finder (Kalam/Tidy already have them) | contract `audio_export_range` |
| `jsx/host.jsx:145-327` | QE razor (`getFormatted` timecode), ripple in one pass, relink, markers, restore; ES3/ASCII | N (both OS) | `WNC_HUSH` compat ops; UXP has no razor | contract `hush_*.schema.json` (reserved) |
| `jsx/host.jsx:7,171,323` | marker prefix "Hush", "(Hush backup …)", "(Hush cut …)" | rename | A6b names (§4) | — |
| `CSXS/manifest.xml` | `com.hoka.hush`, CEP 11 + Node, PlayerDebugMode | B (install) | signed bridge | T6.3 |
| `index.html`, `css/hush.css`, `js/i18n.js` | UI | N | UXP tab | `adobe/panel-ui` |

### 3.3 Tidy (22 files)

| File:line | Assumption | Sev | Windows equivalent / port | Reuse |
|---|---|---|---|---|
| `js/engine.js:7-8` | data dir `~/Library/Application Support/Tidy` | **B** | `~/.whynot-cut/tools/tidy/` | `plat.engine_home` |
| `js/engine.js:111` | `cp.spawn('open', [p])` | **B** | `explorer` / `open` via the engine | — |
| `js/engine.js:20-32` | `fs.statSync` exists/size (PRD FR-3) | B in UXP | engine service (`os.stat`); same `{exists,size}` | — |
| `js/engine.js:37-68` | read first/last 2 MB (64 KB images) as latin1 text | B in UXP | engine reads the same bytes (`latin-1` decode) and feeds the same `TidyMedia.describe` rules (or a Python port with parity tests over the same fixture strings) | — |
| `js/engine.js:71-92` | 16-bit WAV mean power per 1 ms in 4 MB pieces | B in UXP | engine (numpy or stdlib) with a byte-for-byte parity test against `wavPower` on the same WAV | `lib/audio_clean.py` style readers |
| `js/engine.js:93` | temp WAVs in `~/Library/.../Tidy/sync` | B | `tools/tidy/sync` in the engine home; removed in `finally` | — |
| `js/engine.js:97-104` | backup copy next to the `.prproj`, `COPYFILE_EXCL`, colon-free stamp | N | keep (engine `shutil.copy2` + exclusive create); name per A6b | — |
| `js/cep.js:29-34` | no `/C:/` drive fix | W | as Hush | — |
| `js/media.js:85` | `dirOf` splits on `/` and `\` | N | — | — |
| `js/plan.js` (usage/duplicates by `path` string) | media paths compared as exact strings | W | Windows paths are case-insensitive and may differ in separator: compare a normalised key (case-fold + `\`→`/` on Windows only); new test, plan output otherwise unchanged | — |
| `js/plan.js:8`, `jsx/host.jsx:6` | backup regex `/\((Hush backup|Hush cut) /` | rename | accept legacy and new: `/\((?:WhyNot )?Hush (?:backup|cut) /` (A6b) | — |
| `js/sync.js:42-…` | WAV header parse, FFT xcorr; expects 48 kHz | N | keep; add the 44.1 kHz drift guard (A3 #7) | — |
| `js/{classify,media,plan,sync}.js` | pure; also loaded by ExtendScript tests (ES3) | N | reuse as is (110/110 on Windows) | — |
| `js/main.js:185` | synced name `<project> - Synced` | N | A3 #7 numbered name on a second sync | — |
| `js/main.js:208-209` | `E.openFolder` | B | as above | — |
| `jsx/host.jsx:211-218` | WAV preset incl. Windows candidates | N | → `WNC_AUDIO` | — |
| `jsx/host.jsx:221-237` | temp sequence "Tidy sync temp", deleted in `finally` | N | name per A6b; A3 #7 cleanup of leftovers | — |
| `jsx/host.jsx:241-251` | QE `addTracks`, re-read tracks | N (both OS) | `WNC_TIDY` compat | contract `tidy_build_synced` |
| `jsx/host.jsx:47-55,135-139` | project bin paths joined with `/` (project tree, not disk) | N | — | — |
| `jsx/host.jsx:300-304` | save / `openDocument(backup)` | N | — | contract `tidy_save` / `tidy_open` |
| `tests/premiere/*.jsx` | mac paths, `/`-only guards (§2.3) | B (test) | as Kalam | — |
| `tests/test_*.js` | jsc | N | node shim | — |
| `tests/premiere/make_podcast_media.py` | `av` + `soundfile` | dep | test-only, runs with the pack/test deps | — |
| `CSXS/manifest.xml` | `com.hoka.tidy` v1.0.0 (stale, = PRD v2), Node, PlayerDebugMode | B (install) | signed bridge | T6.3 |
| `index.html`, `css/tidy.css`, `js/i18n.js` | UI | N | UXP tab | — |

### 3.4 Cross-cutting

- **Encodings:** every Python child gets `PYTHONUTF8=1` + `PYTHONIOENCODING=utf-8` (daemon env); files are read and
  written with explicit `encoding="utf-8"` and `newline="\n"` for SRT/JSON so macOS and Windows outputs are
  byte-identical (needed for the A5 parity tests). ExtendScript stays ASCII (`C.ascii` escaping is kept).
- **Spaces / Arabic in paths:** spawn with argument lists only (no shell); non-ASCII engine home warning from
  `lib/portability.py` also covers Kalam's CTranslate2 models.
- **Process control:** cancel = `parallel.kill_tree` (Windows `taskkill /T`), never by name (COORDINATION rule 12).
- **Model caches:** never `~/.cache/huggingface`; HF cache = engine-home models, `HF_HUB_OFFLINE=1` at run time.
- **Temp:** engine-home tool folders (`tools/<tool>/cache|sync|jobs`), not `/tmp`; tests use the `_isolation`
  sandbox.
- **Case sensitivity:** Tidy path keys (above); Kalam MOGRT cache keys use `path|mtime` (fine).
- **Line endings in host code:** jsx files are LF in git; ExtendScript accepts both.

## 4. Rename map (A6b: no "Hoka" in the product; `_upstream` stays unchanged)

| What | Upstream (file:line) | Port |
|---|---|---|
| Panel/bundle ids | `kalam/CSXS/manifest.xml:3,9,25` `com.hoka.kalam(.panel)`; `hush/CSXS/manifest.xml:3,9,25`; `tidy/CSXS/manifest.xml:3,9,25` | no separate CEP bundles: ops in the signed bridge; UXP/tab ids `ai.thewhynot.cut.kalam|hush|tidy` |
| Panel menu names | `*/CSXS/manifest.xml:41` `Kalam` / `Hush` / `Tidy` | tabs "WhyNot Kalam" «كلام», "WhyNot Hush" «هَش», "WhyNot Tidy" «تايدي» |
| ExtendScript namespaces | `kalam/jsx/host.jsx` 62 lines `KALAM.` (l.5-205); `hush/jsx/host.jsx` 74 lines `HUSH.` (l.5-327); `tidy/jsx/host.jsx` 71 lines `TIDY.` (l.1-304) | `WNC_KALAM`, `WNC_HUSH`, `WNC_TIDY`; shared export → `WNC_AUDIO` |
| Public host functions | `kalam/jsx/host.jsx:206-212` `kalam_*` (7); `hush/jsx/host.jsx:330-337` `hush_*` (8); `tidy/jsx/host.jsx:308-313` `tidy_*` (6) | `WNC_<TOOL>.<fn>` via the bridge whitelist; contract actions `kalam_*`/`hush_*`/`tidy_*`/`audio_*` (already reserved, e2492c1) |
| evalScript callers | `kalam/js/cep.js:15,19`; `hush/js/cep.js:15,19`; `tidy/js/cep.js:15,19` ("Window > Extensions > X") | contract requests through `reel serve`; messages name the WhyNot Cut panel |
| Window globals | `KalamPlatform/KalamCEP/KalamEngine/KalamRange/KalamMogrt/KalamI18n`, `Hush{CEP,Engine,Wav,Detect,Fillers,I18n}`, `Tidy{CEP,Engine,Media,Classify,Plan,Sync,I18n}` | module exports under `adobe/panel-ui/tools/<tool>/` (no globals) |
| Data dirs | `kalam/js/platform.js:12,16`; `kalam/engine/kalam_engine.py:38,40`; `kalam/engine/tools/compare_backends.py:15,23`; `hush/js/engine.js:8`; `tidy/js/engine.js:7` | `~/.whynot-cut/tools/kalam|hush|tidy/` (engine home); models in the Kalam pack dir |
| Python path | `kalam/js/platform.js:13,17` (`python\python.exe`, `venv/bin/python`); `hush/js/engine.js:11` | engine runtime (core) / Kalam pack runtime |
| Log files | `kalam/js/engine.js:18,118` `kalam.log`; `hush/js/engine.js:17` `hush.log`; `tidy/js/engine.js:12` `tidy.log` | `tools/<tool>/logs/whynot-<tool>.log`, in the diagnostics bundle (redacted) |
| Developer report | `kalam/js/engine.js:122-123` `Kalam-report-<stamp>.txt`, "Kalam report" | WhyNot Cut diagnostics bundle section "WhyNot Kalam" |
| Sequence/backup suffixes | `hush/jsx/host.jsx:171` "(Hush backup HH:MM:SS)", `:323` "(Hush cut …)"; `tidy/js/engine.js:96,101` "(Tidy backup …).prproj" | "(WhyNot Hush backup …)", "(WhyNot Hush cut …)", "(WhyNot Tidy backup …)" |
| Legacy recognition | `tidy/js/plan.js:8`, `tidy/jsx/host.jsx:6` `/\((Hush backup|Hush cut) /`; `tidy/js/plan.js:21` comment | match both old and new names (A6b) + test |
| Markers | `hush/jsx/host.jsx:7,294,305` prefix "Hush" (+ "Remove all Hush markers", `hush/js/i18n.js:6,22,31`) | "WhyNot Hush"; clear-markers also removes legacy "Hush …" markers |
| Bins / clip names | `kalam/jsx/host.jsx:7` bin "Kalam Captions"; `:181,197` clip names "Kalam N"; `kalam/js/main.js:88` folder "Kalam Captions"; Tidy removes "Kalam Captions" bins (PRD §4.3) | "WhyNot Kalam Captions", clips "WhyNot Kalam N"; Tidy and Kalam undo recognise both |
| Temp sequence | `tidy/jsx/host.jsx:226` "Tidy sync temp" | "WhyNot Tidy sync temp" (A3 #7 cleanup matches both) |
| Version strings | `kalam/jsx/host.jsx:205` `panel: '1.1.0'`; manifests 1.1.0 / 1.0.0 / 1.0.0 | WhyNot Cut version |
| UI brand | `*/index.html:5,10` titles/brand marks; `kalam/js/i18n.js:1,6,26,31,51` ("Kalam folder", "Run install_kalam.sh"); `hush/js/i18n.js:1`; `tidy/js/i18n.js:1,6,11,25,30` ("Hush/Kalam backups") | WhyNot names, footer "Powered by thewhynot.ai", TWN tokens; setup message points to `reel setup` / the installer |
| Engine temp prefix | `kalam/engine/kalam/correct.py:85` `kalam-cc-` | `wnc-kalam-cc-` |
| Preset file | `hush/jsx/host.jsx:93` `presets/Hush_WAV48k16.epr` | dropped (shared `WNC_AUDIO` finder) |

## 5. Security review points (A6b gate 3, Phase 8 T8.2)

- **WhyNot Kalam:** only caption text leaves the machine (`correct.py:124-131` payload = phrases + 3 lines context;
  no times, no audio); API key only in a private settings file (`serve/security.private_file`, Windows DACL — the
  upstream 0600 chmod is a no-op on Windows) and a job file the engine deletes on read; never in argv
  (`kalam_engine.py` reads it from the file), logs, reports or the diagnostics bundle; `claude -p --safe-mode --tools ""
  --disallowedTools mcp__* --no-session-persistence --max-turns 3` with the system prompt in a temp file and phrases
  on stdin (`correct.py:85-92`); Windows: no `.cmd` through cmd.exe with JSON on argv (§3.1); faithfulness gate and
  `rules.enforce` run on every backend (A3 #10); MOGRT all-or-nothing.
- **WhyNot Hush:** backup-before-cut default on, original made active and verified before QE (`host.jsx:169-179`);
  locked ticked track aborts before any razor (`:184-186`); tracks re-read after every razor (`trackRef.t()`);
  one-pass ripple; untouched unticked/locked tracks and media; cut boundaries snapped inward (`detect.js:95-105`);
  restore by sequence id, never by name.
- **WhyNot Tidy:** project-only removals, media only read; host re-checks usage and refuses used items and non-backup
  sequences (FR-16); bins by nodeId and deleted only when empty; save + exclusive backup copy before apply; temp
  sequences deleted in `finally`; the 2 MB sniff keeps descriptions, never bytes.
- **All three:** guard rules (Phase 3: the tools may edit only the editor's own Premiere project, never `assets/` or
  `data/`, and only after the backup record exists); routing only through `reel serve` (token, Host and Origin checks,
  rate limit, audit log — `serve/app.py`, `serve/security.py`); every bridge script whitelisted and hash-checked
  (`ppro_bridge.sync_scripts`); process spawning with argument lists, bounded time, tree kill; host tests refuse to
  run unless only test projects are open (separator-neutral guards).

## 6. Port plan

Order inside every item: **characterize the upstream behaviour first (tests run against `_upstream` as is), then
port, and the same tests pass unchanged against the port on Windows and macOS.** Tests live in
`whynot-cut/tests/test_<tool>_*.py` (unittest, `import _isolation` first) and `adobe/panel-ui/test/tools-*.test.ts`
(`node --test`). Sizes: S ≤ ½ day, M ≈ 1 day, L ≈ 2 days.

### 6.1 Can start now (no T6.7 routing needed)

| # | Item | Task | Files | Tests that prove Windows + mac parity | PRD §11 covered | Size |
|---|---|---|---|---|---|---|
| N1 | **Hush characterization tests, FIRST** (no upstream tests exist) | T6.12 | `adobe/panel-ui/test/tools-hush-characterization.test.ts` loading `adobe/tools/hush/_upstream/js/{wav,detect,fillers}.js` by path (module path is a parameter, so the same file later runs against the port) | the list in §6.3, run on Windows now and on macOS CI/H6 | Hush pure (all) | M |
| N2 | jsc → node harness for the upstream JS suites | T6.11 | `adobe/panel-ui/test/jsc-shim.ts` + `tools-upstream-jsc.test.ts` (runs the 9 Kalam/Tidy jsc files, each must print `ALL PASS`) | 145/145 on Windows today; same on macOS | Kalam panel (jsc), Tidy jsc incl. lint | S |
| N3 | Pure JS made platform-neutral | T6.12/13/14 | `adobe/panel-ui/tools/{kalam,hush,tidy}/` from `range/platform/mogrt`, `detect/fillers/wav` + extracted `settings` (main.js:166-180), `media/classify/plan/sync`; Windows path key in `plan` (§3.3); backup regex legacy+new; `safeName` Windows reserved names | N1 + N2 suites re-pointed at the port, unchanged; new: path-key, legacy/new backup names, reserved names, `fileUrl` drive form | Hush pure; Kalam panel; Tidy media/classify/plan/sync/lint | M |
| N4 | Kalam engine package | T6.14 | `whynot-cut/engine/reel/kalam/` (captions, clean, phrases, rules, similar, units, correct, align, audio, transcribe, device, platform, engine CLI); Claude discovery via the installer's rules (exe first, safe `.cmd`), models/HF under the engine home, UTF-8 + `\n` writers, settings file deleted on read; `reel kalam run|doctor` shapes per `docs/adobe/phase-6b-reservations.md` (wiring `cli.py` is the executor's) | the 101 upstream tests ported to unittest and passing (deps faked as upstream does; slow ones skip without H13 media); new: mac-candidate strings on Windows, `.cmd` handling, CRLF-free outputs, byte-identical SRT for the same words on both OS, doctor on Windows (CUDA→CPU) | Kalam engine (rules, DP, units, cleaning, contract + gate, alignment fallbacks, CLI, doctor, platform, portable backends) | L |
| N5 | Kalam pack (runtime lock + models) | A-7 (Phase 7) prep | `setup/locks/kalam-<platform>.lock` (torch/torchaudio/transformers/soundfile/anthropic/onnx-asr; Windows CUDA 12.8 wheels; macOS adds mlx, mlx-whisper, parakeet-mlx), converted models (Egyptian CT2 fp16, Parakeet ONNX, MMS aligner, MLX Egyptian) built once at release, `components.json` pack entry (ticked, sizes shown) | doctor (non-quick) green on Windows GPU and CPU-only; `reel doctor` lists the pack; uninstall removes `tools/kalam/` | Kalam doctor; backend parity prerequisites | L |
| N6 | Hush Whisper on the engine | T6.12 | `whynot-cut/engine/reel/hush/words.py`: `whisper_backends` ct2 large-v3-turbo with Hush's prompts (`hush_whisper.py:15-19`), mlx on Apple Silicon, `HUSH_WHISPER_MODEL`, output `{language, duration, words[{w,s,e,p}]}`; later (T6.15) reuse Kalam's words for the same range (A3 #3) | unit tests with a fake runner (prompt per language passed, schema, offline); live on H13 clips; after N4, the A5 test "Hush using Kalam's words gives the same filler list as its own run on 3 clips" | Hush FR-7; A5 new filler parity | M |
| N7 | Tidy engine services | T6.13 | `whynot-cut/engine/reel/tidy/` disk info, 2 MB head/tail sniff, 1 ms WAV power (streamed), exclusive backup copy, temp dir; Python twins of `wavPower` and the sniff reader | parity: Python vs upstream `engine.js` functions (run in node on the same files) give identical `{exists,size}`, identical sniff text, `wavPower` arrays equal; tests on Windows and macOS | Tidy FR-3/4/20 (feeds jsc media/sync tests) | M |
| N8 | Hush/Kalam services: settings, presets, cache, logs, report → engine home | T6.12/14 | `engine/reel/{hush,kalam}/store.py` | private-file permissions on Windows (DACL) and POSIX (0600); report never contains settings/keys; cache keeps last 3 scans | Kalam FR-24 report rule; Hush FR-24 presets | S |
| N9 | Upstream test fixes kept in the port (not in `_upstream`) | all | separator-neutral host-test guards and `$.fileName`-relative includes (prepared, run later); `test_cli` env with `SYSTEMROOT`; fictional fixtures replacing "Sherif"/"Rog 2" | — | Kalam CLI/slow; host suites | S |

### 6.2 Needs T6.7 routing / the bridge (Phase 6B proper)

| # | Item | Task | Files | Tests | PRD §11 covered | Size |
|---|---|---|---|---|---|---|
| B1 | Shared `WNC_AUDIO.exportRange` / `exportClipAudio` (Windows + mac preset finder, mute/restore of unticked tracks, In/Out restore, temp sequence for clips) | T6.11 | bridge `wnc_audio.jsx`, contract `audio_export_range|clip` routes | host test on a Windows test project; **byte-identical WAV** vs the three old exports for the same range (A5 new); jsx lint | feeds all three | M |
| B2 | `WNC_HUSH` ops + Hush tab | T6.12 | `wnc_hush.jsx` (from `hush/jsx/host.jsx`), `adobe/panel-ui/tools/hush/` UI, routing | Hush host checks (§6.3) on Windows test projects; UXP↔CEP routing test per op | Hush Premiere tests | L |
| B3 | `WNC_TIDY` ops + sync + A3 #7 | T6.13 | `wnc_tidy.jsx`, Tidy tab | host 11/11, synced 3 cams + 2 mics 4/4 on Windows; 44.1 kHz drift guard, "- Synced 2", temp cleanup, skip reason; read-only dry run on a copy of a real project's files | Tidy Premiere + dry run | L |
| B4 | `WNC_KALAM` ops + Kalam tab + MOGRT gallery (engine scan) | T6.14 | `wnc_kalam.jsx`, Kalam tab; info/playhead via UXP where the parity matrix is green | 13 host checks on Windows; panel e2e (track / MOGRT / SRT); backend parity portable vs MLX on 3 H13 clips (text ≥ 96 %, onsets ≤ 15 ms; MLX side needs H6) | Kalam Premiere, parity | L |
| B5 | "Organise → Cut → Caption" + client-aware defaults | T6.15 | flow in the panel + `reel` | backups exist, undo in reverse order; client glossary applied and the gate still rejects rewrites | A5 new | M |
| B6 | Live acceptance + A6b gate 4 | T6.16 | evidence under `docs/adobe/evidence/` | every output/mode on Windows; macOS if H6 | all | M |

### 6.3 Hush: PRD §11 tests to derive (characterize upstream first, then the port)

Pure (N1, against `hush/_upstream/js/*.js`):
1. `wav.js`: header parse of 16-bit PCM, 24-bit, 32-bit float, `WAVE_FORMAT_EXTENSIBLE`, odd-length chunk padding,
   `data` length 0 / 0xFFFFFFFF (streamed), stereo → mono mix; `envelope` at 10 ms hops, floor −100 dB (FR-4/5).
2. `detect.percentile` / `stats`: floor = 10th percentile clamped at −70, speech = 90th (FR-6).
3. `fromIntensity`: threshold/minSilence/pads for 0, 25, 50, 80, 100 and the `span = max(6, speech − floor)` clamp
   (FR-10); Tight → pads 0 (FR-11, extracted settings).
4. `silences`: runs ≥ minSilence; a ≤ 30 ms blip inside a silence ignored, a 40 ms one splits it (FR-8).
5. `cutsFromSilences`: pads applied next to speech, none at range start/end, cuts < 80 ms dropped (FR-9).
6. `combine`: overlapping union; filler swallows a gap ≤ padBefore + padAfter + 50 ms, a silence–silence gap is not
   joined; labels merged (FR-16).
7. `snap`: inward to whole frames at 24/25/29.97/30/60 fps, never outward; pieces < 2 frames dropped (FR-16, §8).
8. `plan`: end-to-end numbers (before/after/removed) on a synthetic envelope.
9. `fillers.norm`: lower case, punctuation, Arabic diacritics/tatweel, alef forms, alef maqsura → yeh (FR-13).
10. `fillers.find`: strong vs soft (`on`), two-word phrases ("you know", "i mean") before single words, elongated
    hesitations (ummmm, hmmmm, aaah, اممممم, آآآه) always strong, custom lists parsed by `,` `،` newline (FR-13).
11. `fillers.untranscribed`: loud runs 0.15–1.2 s with no word within ±150 ms, unticked (FR-14).
Premiere (B2, test projects only): cut → removed count; **no gaps** after ripple; linked video/audio pieces; backup
sequence exists with the new name; restore swaps names (cut kept as "(WhyNot Hush cut …)"); markers added and
"remove markers" removes them (legacy "Hush" too); a locked ticked track aborts with nothing changed. These run
against upstream `host.jsx` first (renamed copy in a test project), then against `wnc_hush.jsx`, unchanged.

### 6.4 PRD vs code notes (A0: the PRD wins where they differ; recorded, not silently changed)

- Hush `hush_whisper.py` output lacks `duration` (PRD §7.2 lists it) → port adds it.
- Kalam `compare_backends.py` bar is 95 % / median 0.08 s; PRD §11 is ≥ 96 % / within 15 ms → port uses the PRD bar.
- Tidy manifest 1.0.0 vs PRD v2 → owner confirmed v2.
- Kalam `test_correct` needs `demo/sherif_*.srt` (28 approved lines) → ask Yunus for it or approve a fictional pair.

## 7. Top macOS-only blockers (Windows)

1. Hush Whisper is MLX-only (`hush/py/hush_whisper.py:61-72`) → N6.
2. Hush WAV export has no Windows preset path (`hush/jsx/host.jsx:90-99`) → B1 (`WNC_AUDIO`).
3. Hush/Tidy data dirs under `~/Library/Application Support` and `open` shell-outs (`hush/js/engine.js:8-12,25`,
   `tidy/js/engine.js:7,93,111`) → engine home + engine reveal (N7/N8).
4. Panels are CEP+Node (fs, child_process, `cep.fs` dialogs) with PlayerDebugMode; UXP can't spawn → `reel serve`
   services + signed bridge (A2, B2-B4).
5. Kalam heavy deps (torch, torchaudio, transformers, soundfile, anthropic, onnx-asr) missing from the core runtime →
   Kalam pack (N5).
6. Kalam Claude discovery/spawn on Windows (`platform.py:22-29`, `correct.py:59-70`) → installer rules (N4).
7. Test harnesses hard-code the developer's Mac paths and `/`-only guards (§2.3) → N9.
