# WhyNot Hush: pure JS port (`adobe/tools/hush/src`)

The silence and filler-word logic of WhyNot Hush, ported from the owner's panel (`../_upstream/js/`). Pure JavaScript,
no DOM, no Node-only API: the Adobe panel (UXP) loads these files as plain scripts, tests and the engine twin load
them with `node` / `require`.

| file | what | vs upstream |
|---|---|---|
| `js/wav.js` | WAV header / decode / 10 ms level envelope (`HushWav`) | unchanged logic |
| `js/detect.js` | percentiles, intensity mapping, silences, cuts, combine, frame snap, plan (`HushDetect`) | unchanged logic, plus the `fmt` fix below |
| `js/fillers.js` | filler matching, Arabic normalisation, untranscribed sounds (`HushFillers`) | unchanged logic |
| `js/settings.js` | which settings are in force: `current`, `advFromSimple`, `readout` (`HushSettings`) | new file, extracted unchanged from the upstream `main.js:166-180` and `:198` so Tight (pads 0) can be tested |

## What changed vs upstream (and nothing else, A0)

1. Every file starts with the licence header (`SPDX-License-Identifier: GPL-3.0-or-later`, `© 2026 The Why Not AI`) and a
   one-line provenance comment.
2. UMD tail: besides `root.HushX = X` each module sets `module.exports = X` when CommonJS is present (`require()` returns
   the same object as the global). `settings.js` finds `HushDetect` on the global object, else `require('./detect.js')`.
3. `settings.js`: the panel's `currentSettings`, `syncAdvFromSimple` and the summary string, as pure functions of
   `cfg = {tab, intensity, tight, adv}` and the clip stats. `advFromSimple` returns `null` (upstream: does nothing)
   when there are no stats.
4. `HushDetect.fmt` display fix (controller ruling): the seconds are rounded to 0.1 s before they are split into minutes.
   Upstream printed `fmt(9.96)` as `0:010.0` and `fmt(59.96)` as `0:60.0`; the port prints `0:10.0` and `1:00.0`.
   Every other value is identical to upstream.

`../_upstream/` stays the parity baseline and is never edited (`../../UPSTREAM-SHA256.txt`). Tests:
`whynot-cut/tests/test_hush_characterization.py` (every behaviour, on upstream and on this port) and
`whynot-cut/tests/test_hush_port.py` (identical results on both roots, settings, module shape, runner contract).
Run `bash tools/test.sh -p test_hush_characterization.py` and `-p test_hush_port.py`.
