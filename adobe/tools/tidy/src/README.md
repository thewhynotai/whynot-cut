# WhyNot Tidy: pure JS port (`adobe/tools/tidy/src`)

The project clean-up logic of WhyNot Tidy, ported from the owner's panel (`../_upstream/js/`). Pure JavaScript, no DOM,
no Node-only API: the Adobe panel (UXP) loads these files as plain scripts (and ExtendScript tests load them too, so
they stay ES3: no arrow functions, no `const`, every nested `?:` parenthesised); tests and the engine twin load them
with `node` / `require`.

| file | what | vs upstream |
|---|---|---|
| `js/media.js` | what a media file is from its own bytes: camera original or render, which camera, image size, icon (`TidyMedia`) | unchanged logic |
| `js/classify.js` | which bin an item belongs in, category, camera numbers (`TidyClassify`) | unchanged logic |
| `js/plan.js` | project scan to clean-up plan: removals, moves, colours, duplicates, offline, empty bins, nest names (`TidyPlan`) | the four changes below |
| `js/sync.js` | sync recordings of one shoot by sound: FFT cross-correlation, confidence guard (`TidySync`) | unchanged logic |

`../_upstream/js/{engine,cep,i18n,main}.js`, `jsx/` and the CEP panel are not ported here: the engine side (reading bytes,
WAV power, project files) goes to the engine, the Premiere side to `wnc_tidy.jsx` (B3), the UI to the WhyNot Cut tab.

## What changed vs upstream (and nothing else, A0)

1. Every file starts with the licence header (`SPDX-License-Identifier: GPL-3.0-or-later`, `© 2026 The Why Not AI`) and a
   one-line provenance comment.
2. UMD tail: besides `root.TidyX = X` each module sets `module.exports = X` when CommonJS is present (`require()` returns
   the same object as the global). `plan.js` finds `TidyClassify` on the global object, else `require('./classify.js')`.
3. `plan.js`, path key (audit 3.3): `P.pathKey(path, platform)` is the path itself unless `platform === 'win32'`; then
   backslashes become `/` and it is lower-cased. `P.build(scan, opts)` groups duplicate files by
   `P.pathKey(it.path, opts.platform)`, so `C:\M\Clip.MP4` and `c:/m/clip.mp4` are one duplicate group on Windows and two
   files elsewhere. `duplicates[].path` is the first item's original path. With `opts.platform` absent or `'darwin'` the
   output is identical to upstream (`whynot-cut/tests/test_tidy_port.py` compares the two on the same scans).
4. `plan.js`, backup names (A6b): `P.BACKUP` is `/\((?:WhyNot )?Hush (?:backup|cut) /`: the legacy `(Hush backup ...)` /
   `(Hush cut ...)` and the new `(WhyNot Hush backup ...)` / `(WhyNot Hush cut ...)` are all backups.
5. `plan.js`, pure name helpers for A3 #7 (used later by the Tidy tab and the host): `P.syncedName(projectName,
   existingNames)` is `<name without .prproj> - Synced`, else `... - Synced 2`, `... - Synced 3` (first free number; an
   empty name is `Podcast`, as upstream's `main.js`); `P.TEMP_SYNC = /^(?:WhyNot )?Tidy sync temp$/` (the temporary
   sequence the sync makes, old and new name); `P.TIDY_BACKUP = /\((?:WhyNot )?Tidy backup /` (the project backup file
   name). The names the port writes are `WhyNot Tidy sync temp` and `(WhyNot Tidy backup <stamp>).prproj`.

Not changed on purpose: `sync.js` only sees 1 ms power arrays, so the 44.1 kHz drift guard lives in the engine's WAV power
reader (Task 8), not here.

`../_upstream/` stays the parity baseline and is never edited (`../../UPSTREAM-SHA256.txt`). Tests:
`whynot-cut/tests/test_tidy_baseline_js.py` (the owner's jsc suites, on upstream and on this port; `test_lint.js` runs on
the port as a copy whose only change is the file list, because the port has no `jsx/host.jsx`) and
`whynot-cut/tests/test_tidy_port.py` (the changes above, identical results on both roots, module shape).
Run `bash tools/test.sh -p test_tidy_baseline_js.py` and `-p test_tidy_port.py`.
