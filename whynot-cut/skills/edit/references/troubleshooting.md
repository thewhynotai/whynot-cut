# Troubleshooting: root cause first

Process (adapted from *systematic-debugging* in obra/superpowers, MIT):
1. **Reproduce and read.** Re-run the failing command and read the full output, `logs/pipeline.log`, `logs/aerender.log`,
   `04_after_effects/ae-*-result.json`, `05_photoshop/ps-build-result.json`, `08_quality_control/qc-results.json`.
2. **Locate the layer.** Is the data wrong (transcript, edit-decisions, timeline-spec), the generator (JSX/XML/preview code),
   or the app/environment (AE prefs, fonts, permissions, file system)? Check each boundary's output before guessing.
3. **Check the catalog below.** Most failures here have happened before.
4. **One hypothesis, one change**, then re-check the **original symptom** (re-render and look, or re-run the exact command).
5. **Three failed fixes → stop.** Report what you tried, what you learned and your best hypothesis to the editor.
   Repeated new failures in different places usually mean a wrong assumption, not bad luck.
6. If you change plugin code, add a test in the plugin's `tests/` that fails without the fix.

## Known symptom → cause → fix

| Symptom | Root cause | Fix |
|---|---|---|
| `AppleEvent timed out (-1712)` on first `ae-build` / `ps-build` | App still launching or a startup dialog is open | Runners use `with timeout`. Launch the app, poll `DoScript "\"V=\"+app.version"` until it returns `V=…`, then retry. Ask the editor to dismiss any dialog |
| AE DoScript output is always `0` (macOS) / AfterFX.exe returns at once (Windows) | Neither returns the script's value | Judge by files produced (`.aep`, renders), never stdout |
| A "ready" check passes while the app isn't ready | The check matched an error message (e.g. `74:96: execution error` starts with a digit) | Match an explicit sentinel such as `V=` |
| Arabic in previews has missing or isolated letters | Fallback renderer (arabic-reshaper) needs presentation-form glyphs; Thmanyah has only 89 | Use the CoreText renderer (`ct_text.py`, needs pyobjc); `setup_env.sh` installs it |
| PSD Arabic + Latin line reads in the wrong order | Photoshop DOM has no paragraph-direction API | `NHPS.setRTL()` sets RTL + World-Ready composer via ActionManager; check `ps-build` stdout for "RTL not set" |
| White box behind the logo in a PSD | Image was flattened on placement (destroys alpha) | Library merges visible layers instead of flattening |
| Photo card shows chest, not face | Centre crop of a portrait photo | AE `roundMask` focus point (default 32 % from top); override with `focus_y` on the graphic |
| Checklist/caption overlaps the speaker's face or neck | Template `y` too high for this framing | Adjust `y` in the graphic params (or the template config), re-render, re-verify |
| Captions appear twice | Burned-in CAPTIONS.mov on C02 plus an imported SRT caption track | Keep the SRT track hidden (CC export only) |
| Caption runs across two sentences | Whisper segment ends lack punctuation | Cue builder breaks on segment change; rebuild with `transcript-correct` |
| `wave.Error: unknown format: 65534` | 24-bit WAVs use WAVE_FORMAT_EXTENSIBLE | Durations come from PyAV (`audio_duration`) |
| Media path "not in preflight" / StopIteration | `/var` vs `/private/var` (symlinked paths) | Compare `Path.resolve()` |
| Extra `._*.mov` / `._*.psd` files counted or probed | exFAT drives store macOS metadata as `._` files | Every output glob filters `._` |
| A command prints `ok: false` with `error`, `where`, `how` and `log` (exit 1) | An input or step problem the engine caught (exit 1 = error or failed result, 2 = refusal) | Do what `how` says; the full traceback is in the `log` file (`logs/pipeline.log`), never in the chat |
| `ae-build` / `ps-build` exits 2 "not approved" | Plan gate: current plan unapproved or changed after approval | Play back `edit-plan.md`, then `approve-plan` |
| `verify --record` refused: sheet older than renders | You rendered after building the sheet | `reel verify` again, look again, then record |
| Planner: "evidence not found verbatim" | Evidence paraphrased, or the transcript was corrected later | Quote the corrected transcript exactly; use `…` to join fragments |
| Premiere asks to "Link Media" on import | A referenced file is missing (moved/deleted render, SFX or source) | `qc` lists unresolved paths; regenerate the missing asset (`sfx`, `ae-render`…) then `premiere` |
| "WhyNot Cut Bridge" missing from Window › Extensions / `ppro-status` says no heartbeat | Premiere was running when the bridge was installed (CEP scans at launch) | Quit Premiere normally (it asks to save), reopen; check the CEP log exists (macOS `~/Library/Logs/CSXS/`, Windows `%TEMP%`, `CEPHtmlEngine*-PPRO-*`) |
| XML imports video but **no audio** | Audio tracks lacked Premiere's track attributes / stereo declared instead of mono pairs | Fixed in `premiere_xml.py` (verified by bisecting against `exportAsFinalCutProXML`). Re-run `premiere`/`ppro-build` |
| Frame review shows a graphic that was already removed | Frames from an earlier build in the same folder | `ppro-frames` now writes `premiere_frames/run-<time>/`; judge only the folder it printed |
| All `ppro-frames` images identical | `exportFramePNG` given ticks exports frame 0 | Use CTI timecode string (fixed) |
| Some `ppro-frames` images say "Media pending" in many languages (right after a project opened) | Premiere was still loading the project's media | `ppro-frames` now detects the slate, waits and re-exports; frames still pending are listed under `media_pending` (`ok: false`, not in the sheet). Wait for Premiere to finish loading and run it again; never judge a slate frame |
| `*_CREATED` but output older than the run | Tool didn't actually write (blocked by a dialog) | Status checks now require mtime ≥ run start |
| AE `exportAsMotionGraphicsTemplate` made folders / truncated names | It writes `<template name>.mogrt` into the given FOLDER; multi-space names fail | Folder target + space-free names (AE path is opt-in only) |
| `/c/Users/...` paths not protected / not found (Windows) | Git Bash path form | Engine and guard translate `/d/...` to `D:/...`; quote paths with spaces |
| Premiere "Link Media" for every clip after XML import (Windows, reel-editor 1.x) | `pathurl` encoded `C:\` as `C%3A%5C` | Fixed in 2.0: `file://localhost/C:/...`; rebuild with `ppro-build --force` or `premiere` |
| `ModuleNotFoundError: No module named 'PIL'` / `av` / `numpy` from your own script while `reel` works | The script ran with another python (system Python, or a 2.x `--system-site-packages` venv under `-I` / `-s`) instead of the engine runtime | Run engine-side Python with `reel py <script.py>` (`-m <module>`, `-c <code>`); `reel setup` moves a 2.x machine to the isolated runtime (`~/.whynot-cut/runtimes/<id>`); see `skills/setup/references/platform-setup.md` |
| `UnicodeEncodeError` printing Arabic (Windows) | Console/pipe code page cp1252 | Fixed in 2.0: the CLI writes UTF-8 |
| `ppro-frames`: 0 frames, "Unknown error exception" per frame (Windows) | QE `exportFramePNG` accepts only native backslash paths on Windows; any `/` fails | Fixed in 2.0 (`NHPP.outPath`); a run with missing frames now returns `ok: false` with the per-frame errors |
| Rebuild fails: "<still>.png is locked" / Permission denied (Windows) | Premiere keeps imported stills locked until it quits, even after the project closes | Fixed in 2.0: Premiere gets per-build copies (`07_premiere/media/stills-*`) and unchanged stills are never rewritten. A project built by 1.x may still hold locks: quit Premiere once |
| `EDITOR_CHANGES_PRESENT` right after a failed rebuild | The pipeline's own save-and-close looked like an editor save | Fixed in 2.0: the pipeline records its own save. For an older case, check `ppro-queue` for a `close_project_path` job at that time before using `--replace-edited` |
| `clip id X was data/Raw/<old name>, which is no longer in data/` after the editor renamed a raw file | A clip renamed after its first edit keeps its old id (ids never change once in `output/discovery/clip-ids.json`) | Pass `--footage <new file>` with the old id, or ask the editor before editing `clip-ids.json` by hand |
| A step says it "used the CPU because the GPU was busy", or "The graphics card couldn't do this step … so the processor did it" | Premiere or After Effects was exporting or rendering, another WhyNot Cut job (a transcription, a preview) had the graphics card, or the card ran out of memory | Nothing to fix: the processor made the same result, only slower. To get the speed back, run heavy steps when Premiere is not exporting. If it happens on every step, run `reel doctor` and read `accelerator.line`; a broken graphics driver can be switched off with `WHYNOT_ACCEL=off` (the editor's setting) |
| Bridge never starts although PlayerDebugMode was "set" | The value went to another account or never ran (pasted into the wrong window) | `reg query "HKCU\Software\Adobe\CSXS.12" /v PlayerDebugMode` in the editor's own session must show `REG_SZ 1`; then restart Premiere |
