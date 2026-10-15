# Live round-trip in Premiere Pro and After Effects (2026-10-14 / 15)

**Why:** Yunus asked us to prove that we can open Premiere and After Effects ourselves, do the work inside them, review
it and fix it («اتاكد انك بتعرف تفتح بريمير وافتر ايفكت وكل البرامج اللي انت محتاجها وتعمل كل حاجه جواهم وتراجع الشغل
وتظبط كل حاجه»). This page records what ran, how long each step took, which steps needed nobody, and what still needs
Yunus.

**Setup:**
- Engine: the release/3.0 checkout's `whynot-cut/bin/reel` (WhyNot Cut 3.0.0), venv in `~/.whynot-cut` (a junction to
  `D:\Claude\whynot-cut-home`). The installed marketplace `reel` is 2.2.1 and has no `serve`, so the 3.0 wrapper was used.
- Bridge: the installed legacy CEP bridge 3.1.1 in both apps (heartbeat `version: 3.1.1`, no `protocol`). The rebuilt
  signed 3.0.0 ZXP was **not** installed (Gate 6).
- Apps: Premiere Pro 26.5.2, After Effects 26.5x89, both under `C:\Program Files\Adobe\`.
- Test items only (whynot-test): Premiere `CLIENT/CLIP1`, After Effects `PODCAST-TEST/EP02TEST_R02_MO`.
- Every build, frame export and render ran through `heavy.sh gpu|job`. `FREEZE` was checked before each one and was
  never set.
- Times are local (+03:00). "Hands-free" means no click and no keystroke from anyone.

## 1. Premiere Pro, run 1 (2026-10-14)

| Step | Time | Hands-free | Note |
|---|---|---|---|
| `reel serve ensure` | 1.7 s | yes | daemon up on a new port; the UXP dev panel connected on its own (2 sessions) |
| Launch `Adobe Premiere Pro.exe` (no project) | 51 s to a fresh heartbeat (22:56:54 → 22:57:45) | yes | no dialog |
| First `build_project` through serve | 1 s | yes | **refused**: the plan approved under 2.x has another fingerprint under the 3.0 engine (Gate 1 works) |
| `reel plan` + `reel approve-plan --by delegated` | 0.7 s + 1.3 s | yes | official commands only; no gate file edited |
| Build 1 (serve `build_project` → `ppro_build.build_for_serve`) | 62 s (bridge 44.1 s, cold) + 18 s waiting for the GPU slot | yes | `PRPROJ_BUILT`, every check true, 11 graphics placed, 10 video + 6 audio tracks named |
| `reel ppro-frames` | 7 s | yes | 8 of 8 frames, Premiere's own render, no media-pending slate |
| Review of the frames | - | yes | text, Arabic shaping, bar sizes and timing as designed (the hook bar sits under the lower half of the text, as in the still) |
| The deliberate change | - | yes | `GFX_001` hook text «لازم أبقى عارفاها» → «لازم تعرفي الحاجات دي» in `01_analysis/edit-decisions.json` |
| `reel plan`, then a build before re-approval | 0.7 s + 1 s | yes | the build is **refused** again (plan changed after approval) |
| `reel previews` (re-renders the stills) | 2 s, after 2 min 12 s waiting for a heavy slot | yes | new `GFX_001*.png` |
| `reel approve-plan --by delegated` | 1.3 s | yes | new fingerprint `1dfa83e6031a20d1` |
| Build 2 | 6 s (bridge 4.5 s) | yes | the old project parked as `_prev_20261014-230738…` |
| `reel ppro-frames` | 5 s | yes | the new hook text is visible (evidence 02, 03); the other 7 frames are unchanged |
| Save and close through the host (`close_project_path`, `save: always`) | 1.4 s | yes | `saved: true` |
| Quit (`CloseMainWindow`, a WM_CLOSE) | 3 s | yes | no prompt; Premiere's `dynamiclinkmanager` ended on its own |

Wall time for the whole Premiere loop: about 12 minutes, of which about 3 minutes waited for machine slots.

## 2. The interruption

The session hit a usage limit right after run 1 (Premiere had already been saved and quit at 23:09). When it resumed
(2026-10-15 03:01) the controller reported that the heartbeat step had been cut off and the app was closed, and asked
for a restart of Premiere from the command line. The run-1 log above shows that the Premiere loop had in fact finished
before the break, so the restart was used as a second, cold check of the same loop after a break (run 2). The serve
daemon had died during the break (`state: stale`); `reel serve ensure` replaced it.

## 3. Premiere Pro, run 2 (after the break, 2026-10-15)

| Step | Time | Hands-free | Note |
|---|---|---|---|
| `reel serve ensure` | 2 s | yes | |
| Launch with the `.prproj` as an argument | heartbeat fresh by 03:04:00 (at most 139 s; the poll loop was slow) | **no** | modal **"Open Project: This file path does not exist on disk at this location"** for a file that does exist (evidence 04). Premiere's own command-line open does not take this path. Use no argument and let the engine open or build the project |
| Wait for Yunus to be idle 3 min | 9 min, longest idle 43 s | - | he was using the PC: no click was allowed |
| `reel ppro-probe` with the modal still up | 0.5 s | yes | ExtendScript still answers behind this modal |
| Build 3 (serve) with the modal still up | 59 s (bridge 38.4 s) | yes | `PRPROJ_BUILT` |
| `reel ppro-frames` | 14 s | yes | frame 2.512 s is pixel-identical to run 1 after the fix |
| Save and close through the host | 1.4 s | yes | `saved: true` |
| Quit | - | yes, after a message | `CloseMainWindow` returned false behind the modal. A posted `WM_CLOSE` to the modal closed it (this simple OK box accepts it, unlike the dialogs in uxp-parity.md). Then `CloseMainWindow` quit Premiere |

## 4. After Effects (2026-10-15)

| Step | Time | Hands-free | Note |
|---|---|---|---|
| Launch `AfterFX.exe` | 144 s to a fresh heartbeat (cold) | yes | |
| After Effects closed by itself about 5 s later | - | - | no crash record and no Application-log event; After Effects wrote its prefs at exit (a normal quit). Yunus was active (idle under 1 min), so a person most likely closed the window. Not confirmed |
| Wait for 3 min idle, then launch again | 9 min wait; 44 s to a fresh heartbeat | yes | no further interruption (idle 294 s at the check) |
| `reel motion-plan` | under 1 s | yes | ok; the 2026-10-11 approval was still valid |
| Build 1 (serve `ae_build_motion` → `motion_build.build_for_serve`) | 37 s | yes | 9 of 9 scenes, no fallback font, `.aep` saved |
| `reel motion-render --scenes S01` (aerender) | 61 s | yes | 90 frames (3.75 s) |
| `reel motion-frames` | 140 s | yes | 24 of 24 frames (S01 from the new piece, the rest from the main render); reviewed (evidence 05) |
| The deliberate change, try 1 | under 1 s | yes | S01 text cut to «عبد الطريق يعني رصف»: **rejected** by `motion-plan` ("text leaves out 50% of what is said … max 40%"), and serve refused the build. The guard for religious wording works |
| The deliberate change, try 2 | under 1 s | yes | S01 emphasis «رصف» → «الطريق» in `motion-script.json`; `motion-plan` ok; `reel approve-plan --by delegated` |
| Build 2 | 9 s | yes | the previous `.aep` kept in `backups/` |
| Render S01 again | 12 s | yes | |
| `reel motion-frames` | 13 s | yes | the highlight moved to «الطريق» (evidence 06) |
| Save and quit | 2 s | yes | the build saved the `.aep` (`saved` in the read-back; no dirty mark in the title); `CloseMainWindow`, no prompt |

## 5. Media Encoder

Not needed. Premiere's QC frames come from Premiere's own frame export (`ppro-frames`), and the motion video is rendered
by `aerender` (`motion-render`). Neither path queues to Media Encoder. Media Encoder has no headless mode, so showing it
"headless" would mean opening its window. That was skipped.

## 6. Dialogs and prompts met

| Dialog | When | How it was cleared |
|---|---|---|
| None | run 1, Premiere launch, two builds, save, quit | - |
| "Open Project: This file path does not exist on disk at this location" (OK) | Premiere launched with the `.prproj` argument | It did not block the bridge. Before the quit, a posted `WM_CLOSE` closed it: no click |
| (none) After Effects closed itself | 5 s after its first heartbeat | Waited for 3 min of user idle, then relaunched |

Floating panels seen in Premiere (not dialogs): the UXP dev panel ("Engine connected", "Premiere Pro 26.5.2"), the
spike panel 0.1.9 and the Bridge 3.1.1 panel (evidence 01).

## 7. What we cannot do without Yunus

1. **Click Adobe modals that ignore posted messages:** "Scratch Disk Error" (Yes/No), UXP "Request For Permission"
   (it needs a real foreground and a real click), and "Project Modified" (OK/Cancel). We may only click them after
   3 minutes of user idle. While he works at the PC, a build behind one of them waits.
2. **The UXP consent prompts** (`shell.openExternal` / `openPath`, «WhyNot Cut wants to open…»): he answers them once
   (whether "allow" is remembered is still unmeasured).
3. **Creative Cloud sign-in, licence and first-run screens** of any Adobe app, and Adobe app updates.
4. **Installing the signed 3.0.0 extension (Gate 6)**, plus any PlayerDebugMode decision. Not done here, by rule.
5. **Editor approval for real work:** this run used `approve-plan --by delegated` on test items only. Real clients need
   his or the editor's approval (Gate 1), and the medical or religious sign-off where the profile asks for it.
6. **Leaving the apps alone while a run is live:** After Effects was closed about 5 s after it started, most likely by
   hand while he was at the PC. Live Adobe runs are best when he is away, or after he has been told.
7. **A missing brand font:** a fallback font needs his OK (`--allow-fallback-font`, never available from serve). It was
   not needed this time.

## 8. Findings for the 3.0 track

- **Approvals go stale on the engine upgrade.** Plans approved under 2.x compute another fingerprint under 3.0. Every
  existing Premiere item needs `reel plan` plus a new approval before its first 3.0 build. That is safe, but the
  upgrade notes or doctor should say so. The motion approval stayed valid.
- **Premiere ignores a `.prproj` command-line argument with this path** and shows a modal. The engine should never
  launch Premiere with a project argument.
- **A simple Premiere OK box accepts a posted `WM_CLOSE`.** This is narrower than "Adobe modals ignore posted
  messages". Only this box was tried.
- **Stale stills (not tested live; read from code):** `ppro_build.job_data` checks only that each graphic still exists,
  not that it matches the current plan. A text change followed by `plan` → `approve-plan` → build, without
  `reel previews`, would probably place the old still. This run ran `previews` first. Follow-up: make the build refuse
  stills older than the compiled plan, or re-render them.
- `build_project` over serve needs the full request schema (`xml_path`, `settings`, …) although `build_for_serve` uses
  only `project_path` and `overwrite_existing`. Clients must send placeholders.
- The cold build in Premiere took 44 s on the bridge and the warm one 4.5 s. In After Effects the cold build took 37 s
  and the warm one 9 s. A scene render took 61 s cold and 12 s warm.

## 9. Evidence (`evidence/live-roundtrip-2026-10-14/`)

| File | What it shows |
|---|---|
| `01-ppro-panels-engine-connected.jpg` | Premiere's floating panels during run 1: the UXP panel connected to the engine, the spike panel and Bridge 3.1.1 |
| `02-ppro-hook-before-after.jpg` | Premiere's own frame at 2.512 s, before and after the hook text change |
| `03-ppro-frames-after-fix-sheet.jpg` | all 8 QC frames after the change |
| `04-ppro-open-project-modal.jpg` | the "Open Project" modal from the command-line project argument |
| `05-ae-24-frames-before-sheet.jpg` | the 24 motion QC frames reviewed before the change |
| `06-ae-s01-before-after.jpg` | S01 hero frame (89) from After Effects, before and after the emphasis change |

**End state:** no Premiere, After Effects, aerender or Media Encoder process is running. `reel serve` was stopped, and
Creative Cloud was not touched. The test items keep the changed hook text and S01 emphasis, both approved; the previous
`.prproj` and `.aep` are kept as `_prev_` and `backups/`.
