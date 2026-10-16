# Photoshop hands-free route, and the access check of 2026-10-16

**Why:** Yunus allowed Claude to open, use and close Premiere Pro 2026, After Effects 2026 and Photoshop 2026 without
asking. This page records the route chosen for Photoshop (new), and the access check that proved all three apps end
to end on this PC (Lenovo LOQ, Windows 11, 32 GB).

**Setup:**
- Engine: the release/3.0 checkout's `whynot-cut/bin/reel.cmd`, engine home `~/.whynot-cut` (a junction to
  `D:\Claude\whynot-cut-home`).
- Bridge: the installed legacy CEP bridge 3.1.1 in Premiere and After Effects (heartbeat `version: 3.1.1`, no
  `protocol`). Nothing was installed or changed, and no preference or debug flag was touched.
- Apps:
  - Premiere Pro 26.5.2 (build 5);
  - After Effects 26.5x89;
  - Photoshop 27.11.0. COM `Photoshop.Application` → `Photoshop.Application.200`, LocalServer32
    `Photoshop.exe /Automation`.
- Test files: only under `whynot-test/access-check-2026-10-16/` (`ppro/`, `ae/`, `ps/`), next to this repo. These are
  the "evidence paths" below.
- Times are local (+03:00). The run started 2026-10-16 21:52 and was cut by a usage limit. It resumed on 2026-10-17 at
  02:01, so the After Effects and Photoshop steps ran on 10-17.
- "Hands-free" means no click and no keystroke from anyone.

## 1. The route: COM `DoJavaScriptFile` from PowerShell (route a)

This is what the engine already does in `lib/adobe_run.run_photoshop` (Windows branch). This run is its first live
proof.

```powershell
powershell -NoProfile -NonInteractive -Command "$ErrorActionPreference='Stop'; $app = New-Object -ComObject Photoshop.Application; $r = $app.DoJavaScriptFile('<absolute path to .jsx>'); Write-Output $r"
```

- **One line does it all.** When Photoshop is closed, `New-Object -ComObject` starts it (`Photoshop.exe /Automation
  -Embedding`) and returns once it can take calls. When Photoshop is open, it attaches to that instance.
- **The result:** `DoJavaScriptFile` returns the script's last expression as a string. The access-check script ends
  with `res.toSource()` and also writes the same text to a file.
  - Photoshop's ExtendScript has no `JSON` object. Return `toSource()` text, or write the result file yourself.
- **Errors:** a JS error comes back as a `COMException` with Photoshop's error number, message and line, for example:
  ```
  General Photoshop error occurred. ... - Error 54: Uncaught JavaScript exception: wnc deliberate error.Line: 1->
  ```
  Syntax errors come back the same way (`Error 23: ; does not have a value.`). PowerShell's `try/catch`, or
  `$ErrorActionPreference='Stop'` (a non-zero exit), catches them.
- **No warning dialog:** COM runs the script directly, with no "run script?" prompt.
- **Quit:** check `$app.Documents.Count` is 0, release the COM object, then `CloseMainWindow()` on the Photoshop
  process (a normal WM_CLOSE). Photoshop quit in 2.4 s (launched from the command line) and in 5.5 s (started by
  COM), with no prompt.
- **Inside the script:**
  - `app.displayDialogs = DialogModes.NO` for the run, put back after;
  - sizes as explicit `UnitValue`s (`new UnitValue(1080, "px")`), so `app.preferences.rulerUnits` / `typeUnits` are
    never touched;
  - close without saving: `doc.close(SaveOptions.DONOTSAVECHANGES)`.

### Arabic in Photoshop 27.11 (from the script, no preference)
- Out of the box, a new text layer's paragraph already uses the World-Ready composer (`textComposerEngine:
  textOptycaComposer`, the Middle Eastern one). Its paragraph direction is `dirLeftToRight`.
- A pure Arabic line is already shaped and ordered right to left with those defaults (run 1, evidence
  `ps_frame_run1_dir-ltr.png`). Paragraph direction matters for mixed Arabic/Latin text, punctuation and alignment, so
  set it anyway.
- **Set RTL per layer through Action Manager**, with the text layer active:
  ```js
  var s = stringIDToTypeID, d = new ActionDescriptor(), r = new ActionReference(), p = new ActionDescriptor();
  r.putProperty(s("property"), s("paragraphStyle"));
  r.putEnumerated(s("textLayer"), s("ordinal"), s("targetEnum"));
  d.putReference(s("null"), r);
  p.putEnumerated(s("directionType"), s("directionType"), s("dirRightToLeft"));
  p.putEnumerated(s("textComposerEngine"), s("textComposerEngine"), s("textOptycaComposer"));
  d.putObject(s("to"), s("paragraphStyle"), p);
  executeAction(s("set"), d, DialogModes.NO);
  ```
  - Read back through `executeActionGet` → `textKey` → `paragraphStyleRange[0].paragraphStyle`. Run 2 read
    `dirRightToLeft`.
  - With the two `putProperty` arguments swapped, Photoshop answers "The command "Set" is not currently available"
    (run 1).
- The Type preference "Text Engine Options" (Middle Eastern) was not needed and was not touched.

## 2. Routes compared

| | (a) COM `DoJavaScriptFile` (chosen) | (b) `Photoshop.exe <file.jsx>` | (c) UXP plugin through UPIA |
|---|---|---|---|
| Tested | yes, 3 runs | yes, once, with a probe | assessed only |
| "Run script?" warning | none | **yes, every time**, a modal (below) | none once installed |
| Preferences needed | none | `WarnRunningScripts 0` in `PSUserConfig.txt` to suppress the warning: a settings file, so not allowed | none for a signed `.ccx`; an unsigned one needs Developer Mode (a debug setting, not allowed) |
| Photoshop already open | attaches (0.26 s) | handed to the running instance | the panel lives inside the app |
| Photoshop closed | starts it (6.5 s to a usable object) | starts it | the app must be started first |
| Result and errors | return string + COMException with line | none: the script must write a file, and there is no error channel | needs a file or socket queue, like the CEP bridge |
| Extra install | none (pywin32 not needed; PowerShell has COM) | none | a signed `.ccx` through UPIA, a manifest, and a queue protocol to build |

**Recommendation: (a).**
- It needs no preference and no install, and it shows no dialog.
- It works whether Photoshop is open or closed.
- It reports success and errors synchronously, with the line number.
- The engine already ships it.
- (b) is unusable hands-free because of the warning.
- (c) is worth it only if Photoshop gets a visible WhyNot Cut panel later (Addendum E style). For automation it adds a
  signing and install step and a queue, and gains nothing over COM.
- Python `win32com` would be the same COM route, but pywin32 is not in the engine runtime or the system Python
  3.13. It was not installed.

## 3. Measured (Photoshop)

| Step | Time | Note |
|---|---|---|
| Launch `Photoshop.exe` (no argument) to the main window "Adobe Photoshop 2026", responding | 19.1 s | 02:12:28.9; RAM 68% before; no dialog, no Home-screen block |
| `New-Object -ComObject Photoshop.Application` on the open instance | 0.26 s | version 27.11.0, 0 documents. A second `Photoshop.exe` (pid 9816, started at the moment of the call) appeared and was gone seconds later. Most likely the COM launcher handing off; not proven |
| Run 1 `DoJavaScriptFile` (first document of the session) | 5.19 s | document 1.8 s, text layers 1.0 s, PNG 2.1 s, close 0.1 s; RTL set failed (my argument order), PNG still shaped RTL |
| Run 2 `DoJavaScriptFile` | 1.32 s | document 0.36 s, text layers 0.66 s (RTL set and read back), PNG 0.17 s, close 0.09 s |
| Error reporting (`throw`, syntax error through `DoJavaScript`) | under 1 s | COMException with the error number, message and line |
| Route (b) `Photoshop.exe "<...>\probe_cmdline.jsx"` with Photoshop open | - | modal `PSDialogBox` "You are about to run the script contained in file "probe_cmdline.jsx". Are you sure you want to do this? To suppress this warning, add WarnRunningScripts 0 to the PSUserConfig.txt …" (Yes/No). A posted `WM_CLOSE` closed it as No: the script did not run and nothing changed |
| Quit (`CloseMainWindow`, 0 documents) | 2.4 s | no prompt; no Photoshop or dynamiclinkmanager left 5 s later |
| Cold route: `New-Object -ComObject` with Photoshop closed | 6.5 s | started `Photoshop.exe /Automation -Embedding` |
| Then `DoJavaScriptFile` (first document) | 5.9 s | ok, same PNG |
| Then quit (`CloseMainWindow`) | 5.5 s | no prompt. Whole cold loop 18.1 s |

The exported PNG is 1080x1920 and about 6 MB: `PNGSaveOptions` defaults to low compression. Set `compression` (0-9)
when size matters.

## 4. Gotchas met in this check (all three apps)

- **After Effects ignores `AfterFX.exe -r` when the script path has a space.**
  - With After Effects running, `-r "D:\0 Work\...\access_check_ae.jsx"` did nothing, twice (180 s and 90 s). Both a
    PowerShell `Start-Process` and the engine's own `subprocess.Popen([exe, "-r", jsx])` were tried, and the launcher
    exited 0.
  - The same file from a path without spaces (the scratchpad) ran in 1.1–1.8 s.
  - The script itself can write to paths with spaces.
  - **This affects `adobe_run.run_after_effects`** (ae-build, mogrt-build, `motion-build --run-script`) whenever the
    `.jsx` sits in a client folder with a space. Follow-up: copy the `.jsx` to a space-free temp path (or the engine
    home) before `-r`, or send it through the bridge.
- **After Effects closed itself about 7 s after its first heartbeat**, as on 2026-10-15.
  - The first launch reached a heartbeat at +65.6 s. The last heartbeat came at +72.7 s.
  - After Effects wrote its prefs and workspace at that moment (a normal quit). There was no crash dump and no
    Application-log event.
  - The cause is unknown: a person closing it is possible. `GetLastInputInfo` reads ~0 s idle all the time on this
    PC, so it cannot tell.
  - The relaunch 4 h later stayed up. If it recurs, watch the process for the first 15 s and relaunch once.
- **Premiere's first frame export can be the "Media pending" slate.**
  - The first `export_frames` (21.6 s, including opening the project) wrote the multilingual "Media pending" slate.
    Evidence: `frame_002512_try1_media-pending.png`.
  - A second export 10 s later (1.0 s) was the real frame. `reel ppro-frames` handles this with
    `_wait_for_media`. A one-off export must wait too.
- **Passing JSON through `reel.cmd py` breaks quotes.** cmd strips the double quotes from a JSON argument. Pass a file
  (`@file.json`).
- **A copied `.prproj` works:** the copy in `access-check-2026-10-16/ppro/` opened through the bridge
  (`app.openDocument`) with its media found, no dialog.
- The failed first After Effects script run (a bug in my `step()` helper, `TypeError` at line 9) had already added a
  comp and a solid. So the saved `AccessCheck_AE.aep` holds two `AccessCheck_2026-10-16` comps. This is harmless in a
  test file. A real build script must clean up after itself or start from a new project.

## 5. macOS (from documentation and the engine's code; **not verified on a Mac**)

- **AppleScript `do javascript`** is the macOS counterpart of COM. The engine already builds it (`adobe_run.osascript_argv`
  with `PS_ALIAS`):
  ```
  osascript -e 'on run argv' -e 'set jsxFile to ((item 1 of argv) as POSIX file) as alias' \
    -e 'with timeout of 600 seconds' -e 'tell application "Adobe Photoshop 2026" to do javascript jsxFile' \
    -e 'end timeout' -e 'end run' '/path/to/script.jsx'
  ```
  - It starts Photoshop if needed and returns the script's result.
  - JS errors come back as an AppleScript error, with a non-zero `osascript` exit and the message on stderr.
  - Like COM, it should show no "run script?" warning.
- **TCC (Automation permission):** the first time a process (Terminal, the Claude app or `osascript` under it) sends
  Apple Events to Photoshop, macOS asks: "“<app>” wants access to control “Adobe Photoshop 2026”".
  - That needs one click by the user. The answer is kept in System Settings → Privacy & Security → Automation.
  - Until it is allowed, `osascript` fails with error -1743 ("Not authorised to send Apple events").
  - It cannot be granted by a script. A managed Mac can pre-grant it with an MDM PPPC profile.
- **`open -a "Adobe Photoshop 2026" file.jsx`**, the counterpart of route (b), should show the same "run script?"
  warning. Do not use it.
- **UXP plugin through UPIA:** the same as on Windows, a signed `.ccx`; it has no TCC prompt of its own.
- `PS_ALIAS` (the alias made outside the `tell` block) was written for a known Photoshop AppleScript error (-1728). It
  has not yet run on a Mac.

## 6. Access check 2026-10-16 (all three apps)

Evidence paths are relative to `whynot-test/access-check-2026-10-16/`.

| App | Step | Result | Time | Evidence |
|---|---|---|---|---|
| Premiere | Launch `Adobe Premiere Pro.exe` (no argument), RAM 80.9% | ok, no dialog | 27.0 s to a fresh heartbeat (21:52:10) | - |
| Premiere | Ping through the bridge (`reel ppro-status`) | ok, 26.5.2, 0 projects | 1.0 s (job), 1.9 s wall | - |
| Premiere | Open the copied test project and export a frame (`export_frames`, QE `exportFramePNG`) | first try the "Media pending" slate, second try the real frame | 21.6 s, then 1.0 s | `ppro/frame_002512_try1_media-pending.png`, `ppro/frame_002512.png` (looked at: test pattern plus the hook «لازم تعرفي الحاجات دي», shaped, RTL) |
| Premiere | Save and close through the host (`close_project_path`, `save: always`) | `saved: true`, `closed: true` | 2.5 s | `ppro/AccessCheck_CLIP1.prproj` (mtime 21:54:22) |
| Premiere | Quit (`CloseMainWindow`) | no prompt; all helpers gone within 10 s | 2.1 s | - |
| After Effects | Launch 1 `AfterFX.exe`, RAM 73% | heartbeat at +65.6 s, then After Effects quit by itself at about +73 s (see 4) | - | - |
| After Effects | Launch 2 `AfterFX.exe`, RAM 61% | ok, no dialog | 43.7 s to a fresh heartbeat (02:02:16) | - |
| After Effects | Ping through the bridge | ok, 26.5x89, `libs_loaded: true` | 0.5 s | - |
| After Effects | `AfterFX.exe -r <script with spaces in path>` | did nothing (twice) | - | - |
| After Effects | `AfterFX.exe -r <same script, space-free path>`: comp 1080x1920, Arabic + English text, `saveFrameToPng`, save | ok: Arabic layer `UNIVERSAL` composer, `RTL`; PNG through `saveFrameToPng` (no render queue needed); saved, not dirty | 1.6 s wall (0.73 s in the script) | `ae/ae_result.json`, `ae/ae_frame_access_check.png` (looked at: «تجربة الوصول» joined, RTL), `ae/AccessCheck_AE.aep` |
| After Effects | Quit (`CloseMainWindow`, `dirty: false` checked through the bridge) | no prompt | 1.3 s | - |
| Photoshop | Launch `Photoshop.exe`, RAM 68% | ok, no dialog | 19.1 s to the main window | - |
| Photoshop | COM attach, `DoJavaScriptFile`: document, two text layers, RTL, PNG, close without saving | ok | 5.2 s (run 1), 1.3 s (run 2) | `ps/ps_result_run1.json`, `ps/ps_result_run2.json`, `ps/ps_frame_run2_rtl.png` (looked at: «تجربة الوصول» joined, RTL) |
| Photoshop | Route (b) probe | "run script?" modal, closed as No | - | `ps/probe_cmdline.jsx` (it never ran) |
| Photoshop | Quit (`CloseMainWindow`, 0 documents) | no prompt | 2.4 s | - |
| Photoshop | Cold COM loop (start, script, quit) | ok | 6.5 + 5.9 + 5.5 = 18.1 s | `ps/ps_frame_access_check.png`, `ps/ps_result.json` |

**End state:**
- No Premiere, After Effects, Photoshop, aerender or dynamiclinkmanager process is running.
- Creative Cloud was not touched.
- No preference, registry value or debug flag was changed. The run-script warning was closed as No.

## 7. What still needs Yunus

1. The After Effects self-close right after launch: if it was him, nothing is needed. If not, it is an open question
   (two cases now).
2. Every other step ran hands-free. The only dialog met was Photoshop's "run script?" box, and that belongs to route
   (b), which is not used.
3. On a Mac, the Automation (TCC) prompt needs one click the first time (section 5).
