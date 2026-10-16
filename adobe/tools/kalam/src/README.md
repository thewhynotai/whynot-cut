# WhyNot Kalam: panel pure JS port (`adobe/tools/kalam/src`)

The panel-side logic of WhyNot Kalam that needs no DOM and no Node, ported from the owner's panel (`../_upstream/js/`).
Pure JavaScript: the Adobe panel (UXP) loads these files as plain scripts, tests and the engine twin load them with
`node` / `require`.

| file | what | vs upstream |
|---|---|---|
| `js/range.js` | which part of the sequence to caption, SRT times in sequence time (`KalamRange`) | unchanged logic |
| `js/mogrt.js` | the Motion Graphics Templates gallery: zip central directory, definition info, folder, filter (`KalamMogrt`) | pure functions unchanged; `G.scan` removed |
| `js/platform.js` | what differs between macOS and Windows on the panel side (`KalamPlatform`) | `paths`, `safeName` changed, `fileUrl` added |
| `tests/panel/test_platform.js` | R3 copy of the owner's `test_platform.js` | its header lists every difference |

Not ported here: `cep.js` (the bridge replaces it), `engine.js`, `i18n.js`, `main.js`, `index.html`, `css/`, `jsx/` and the
Python engine under `../_upstream/engine/` (separate tasks of the track: engine package, panel UI, Premiere host).

## What changed vs upstream (and nothing else, A0)

1. Every file starts with the licence header (`SPDX-License-Identifier: GPL-3.0-or-later`, `© 2026 The Why Not AI`) and a
   one-line provenance comment.
2. UMD tail: `platform.js` and `mogrt.js` ended with `})(window);` (they needed `window` to exist); they now end with
   `})(typeof window !== 'undefined' ? window : this);` like `range.js`, and every module sets `module.exports = X` when
   CommonJS is present (`require()` returns the same object as the global).
3. `mogrt.js`: `G.scan(base, cacheDir)` (walks Premiere's Local Templates folder with Node `fs`, `zlib` and `crypto`, and
   caches thumbnails) is removed: a UXP panel cannot run it. A comment names the replacement, an engine service (Task 11)
   that returns `[{path, name, folder, textFields, thumb}]`. `zipEntries`, `dataStart`, `definitionInfo`, `folderOf`,
   `filter` and `topFolders` are unchanged.
4. `platform.js`, A6b + audit 3.1:
   - `P.paths(platform, engineHome, sep)` returns `{home, logs, cache, models, hf}` under `<engineHome>/tools/kalam` on
     both OS (upstream: `%LOCALAPPDATA%\Kalam` and `~/Library/Application Support/Kalam`, and a `py` path). There is no
     `py`: the engine runtime runs Kalam and a UXP panel cannot spawn it. `engineHome` is given without a trailing separator.
   - `P.safeName(s)`: the upstream replacement of `\ / : * ? " < > |` by `-` first, then trailing dots and spaces are
     stripped, then a Windows device name (CON, PRN, AUX, NUL, COM1-COM9, LPT1-LPT9, case-insensitive, also before an
     extension: `nul.srt`) gets `_` appended to its base name (`nul_.srt`), and an empty result is `_`.
   - `P.fileUrl(p)` (the panel's `fileUrl` from `main.js`, fixed for drives): `file:///C:/...` for a drive path,
     `file:///...` for POSIX, `file://server/share/...` for a UNC path; the encoding is the owner's (`encodeURI`, then
     `#` to `%23` and `?` to `%3F`). Upstream gave `file://C:/...` for a drive path.
   - `childEnv`, `revealCmd`, `openCmd` and `templatesDir` are unchanged.

`../_upstream/` stays the parity baseline and is never edited (`../../UPSTREAM-SHA256.txt`). Tests:
`whynot-cut/tests/test_kalam_baseline_js.py` (the owner's jsc suites on upstream and on this port: `test_range` and
`test_mogrt` unchanged, `test_platform` as the R3 copy, `test_html` upstream only; `test_mogrt` runs in a temporary copy of
this folder plus the upstream fixture `tests/panel/fixtures/tiny.mogrt`, which is not copied here) and
`whynot-cut/tests/test_kalam_port.py` (the changes above, identical results on both roots, module shape).
Run `bash tools/test.sh -p test_kalam_baseline_js.py` and `-p test_kalam_port.py`.
