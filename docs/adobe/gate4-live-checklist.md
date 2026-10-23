# Gate 4 live checklist: WhyNot Cut 3.0 on a PODCAST-TEST copy

**Purpose.** This is the "live PODCAST-TEST check" on the Gate 4 exit list (PROGRESS "Gate 4 exit" and "exit prep";
roadmap Stage 1). It covers every Gate 4 item that only a live Premiere or After Effects run can show. Nothing in it is
claimed as verified until the Result and Evidence cells are filled in.

**Setup (all of it, before row 1).**
- **Copy:**
  - run `robocopy "<Editing Plugin>\whynot-test\PODCAST-TEST" "D:\ClaudeData\wnc-live\g4\PODCAST-TEST" /E /XJ`;
  - confirm `dir /AL /S` finds no links in the copy;
  - below, `C` = that copy. Items: `EP02TEST_R02` (Premiere reel) and `EP02TEST_R02_MO` (motion);
  - never write into the original or into `D:\WhyNot Clients`.
- **Engine:** the 3.0 dev engine (`WhyNotCut/whynot-cut/bin/reel`, release/3.0) with the usual `WHYNOT_HOME`
  (`~/.whynot-cut` → `D:\Claude\whynot-cut-home`). Before the run and after each group, take a listing of
  `~/.whynot-cut` and diff it against the baseline.
- **Bridge:** the INSTALLED CEP bundle PREVIEW 3.0.0, protocol 4, from build `322d8a5` (the real installer, 21 Oct).
  Checked on 23 Oct in `%APPDATA%\Adobe\CEP\extensions\ai.thewhynot.cut.bridge\build.json`; `…bridge.prev` is 3.0.0
  too. Its bundled libraries are 322d8a5's, and the dev tree's differ (`wnc_ppro_lib.jsx` sha256 2b1167… installed vs
  129ef7… at HEAD abdece5). So without the dev loop the engine refuses every job ("from another build").
  - Run every `reel` command of this checklist with `WHYNOT_BRIDGE_DEV=1` set for the engine process only
    (cep_queue `job_mode`: a bundle of another build gets the synced library by path). The engine then syncs its
    libraries to `ppro-scripts/` (`ae-scripts/` for AE) and sends them as `script=`.
  - Pass check: the first job's result runs the dev library, not 322d8a5's bundled one. A refusal naming "another
    build" means the variable is missing.
  - No installs. No `cep_bundle` re-bundle. Do not change PlayerDebugMode or any Adobe preference.
  - Do not start `reel serve`: its discovery pointer is a write to the engine home.
- **UXP baseline:** two UXP plugins sit in `%APPDATA%\Adobe\UXP\Plugins\External`: spike 0.1.9 (left over
  from 13 Oct) and dev 3.0.0 (the PREVIEW 3.0.0 panel, 322d8a5, installed 21 Oct). They load in Premiere and write `~/.whynot-cut/uxp-spike/lifecycle.json`. That write is baseline, not a
  leak. Do not use them as a check tool.
- **Machine:**
  - RAM below 85% before each heavy step;
  - builds, frames and renders run through `bash "$HEAVY" gpu|job <label> -- …` (the phase-4 plan's path);
  - `FREEZE` must be absent;
  - book the ppro-queue slot with the release track (one queue writer at a time).
- **Apps:**
  - before each launch, check whether Premiere or AE is already running. If it is and this run did not start it
    (Yunus may be working in 2.2.1 or the 3.0 try folder), do not touch it: message the plan session and wait
    for its go. Never close or drive an app session that Yunus started;
  - launch Premiere and AE with NO project argument (live-roundtrip §8);
  - never choose Reset Preferences or Safe Mode at an AE modal (R-L1);
  - save and close only the test projects, through the host;
  - approvals on the copy are `reel approve-plan --by delegated --note "Gate 4 live"` (test items only).
- **Order:** setup → A (Premiere) → save, close and quit Premiere → B (AE) → quit AE → C → final diff of
  `~/.whynot-cut` → clean up the copy (only after the link check).

| # | Item | Source | Command / action | Expected result | How checked | Result | Evidence path |
|---|---|---|---|---|---|---|---|
| **A** | **Premiere podcast reel build** (`--root C --video-id EP02TEST_R02`) | | | | | | |
| A1 | Re-plan with the ease on; ease-only re-approval | T41 I3/I4/M2, live-roundtrip §8 | `reel plan`, `reel previews`, then `reel approve-plan --by delegated` | `edit-plan.md` has the "Smooth zoom" line (and "Fades" when set); the re-approval reason is in plain words; a new fingerprint | read-back JSON, plus reading edit-plan.md | | |
| A2 | Build with eases and fades | R-L6; T41 #2, #3; PROGRESS "eased frames and fades" | `reel ppro-build --force` | `PRPROJ_BUILT`, not `…WITH_ISSUES`; `punch_ins_eased` and `fades_applied` both true; interpolation reads "bezier (set, not read back)" | `07_premiere/ppro-build-result.json` | | |
| A3 | Mid-ease frames | R-L6; T41 #11; PROGRESS | `reel ppro-frames` (it exports the `qc_frames`), plus `reel preview-video` at the same times | every mid-ease frame shows a scale between the start and end values; it matches the preview's 0.33/0.67 bezier | Premiere's own exported frames, side by side with the preview | | |
| A4 | Bezier really applied | T41 #1 | in Premiere, Effect Controls → Scale/Position → graph | a curved (bezier) ease, not a straight line | screenshot of Premiere (CEP has no getter) | | |
| A5 | getValue and Position units | R-L6 items 3–4; T41 #3, #4 | the frames at both key ends of a framed punch-in (face reframe with offset_y) | the eased ends line up with the hard punch's framing; no jump to 0 or to a stale value | exported frames | | |
| A6 | Hard boundaries | R-L6 r4; T41 #9, #15; T41 round-5 add | find punch-ins at a shot or speaker change (also one off a frame boundary), back-to-back story moves, and a punch-in split by a pause cut | they meet hard (no whip-pan); a punch-in never eases out into a reframe or punch_out; a split punch-in eases in on its first piece and out on its last, and the mask step stays hard | exported frames, plus `eased[]` in the read-back | | |
| A7 | Ease-out end and slow push | R-L6 r4; T41 #12, #13 | frames at the out point of an eased clip and across a slow_push | the zoom-out lands with no jump into the next clip; the slow push moves smoothly across its whole piece | exported frames | | |
| A8 | Picture fades: 4:5 with B-roll | R-L6; T41 #5, #8, #10 | set `fades` (in/out 500 ms) in the copy's reel-profile style.json (path: confirm) and a 4:5 framing with B-roll (how: confirm); then plan, approve, build | at the 50% fade there is no ghosting (one black matte on the top track); the hook pop is multiplied, not replaced; in the 4:5 window punch-ins stay hard and nothing moves on V1 | the frame at the fade's half point, plus the read-back `faded` | | |
| A9 | 29.97 timing | R-L6 r4; T41 #13 | needs a 29.97 source; EP02TEST's fps: confirm (else use the A15 clip) | the matte clips start and end on the fade windows; the `qc_frames` (frame centres) give the intended frame | exported frames vs. the times in the spec | | |
| A10 | Sound fades | R-L6; T41 #6, #12 | play the sequence in Premiere at the fade-in, at the fade-out and at frame 0 | a smooth fade, not a late drop; the music bed's own fade-out keys are kept; the hook SFX keeps its level; a cue under the fade-out is kept to the 0.5 point and the build warns | listening in Premiere (check method to confirm: no CLI audio export) | | |
| A11 | Captions inside the fade windows | T41 #7, M4 | frames inside the fade windows | the native caption track is trimmed out of the windows; the animated captions fade with the picture | exported frames | | |
| A12 | Emphasis punch-ins and endings (Task 29: no builder yet, executor raising an owner; confirm) | phase-4 Task 29; PROGRESS | plan and build after Task 29 lands | the punch-ins keep the face in frame, keep the minimum spacing and follow the endings order | exported frames | | |
| A13 | Cut markers (Task 25; verb `cut-proposals` lands with lane2 hooks\K-T7, sha to follow, confirm; run LAST in A) | PROGRESS "cut markers"; phase-4 Task 25 | build after the proposals are written (`01_analysis/cut-proposals.json`) | one marker per proposal, coloured by kind, named kind + reason; a pause removed whole has no marker; nothing is cut without approval | MANUAL (executor-accepted for Gate 4): Markers panel screenshot + each marker's name and time written in the row | | |
| A14 | Manual verse marker | executor (manual verse slot); PROGRESS | add `manual_verse: [{start_ms, end_ms}]` to the copy's edit-decisions.json (the story-editor override; no Quran text); plan, approve, build; confirm the ppro_build marker hunk has landed | marker «آية: يضيفها المونتير يدويًا» (red, comment = timecodes + cue); no caption text over the span; one NEEDS-YOU line (`reel needs-you`) | MANUAL (executor-accepted): Markers panel screenshot with name and time, plus the exported frame at the span. Pass = the marker sits at the span and no caption or graphic text is over it | | |
| A15 | Task 26: VFR clip conformed to CFR | executor; CONTRACT.md (`hooks\t26`) | put a VFR phone clip (a real phone clip, else `tests/fixtures/media_normalise/vfr.mp4`) in the copy, after the Task 26 engine commit and my ppro_build hunk (shas to follow); `reel preflight` (it starts the conform in the background; the engine half is 99f6357), then `reel conform --root C --video-id <id> --wait` (before any preflight it returns "none"); plan, approve, build | `output/<item>/00_inputs/preflight.json` → `files[i].normalise.conform.state` = "ready", with a relative path under output/; the Premiere project item's media path is that conform path; the sidecar names the copy | read-back JSON, the Premiere item's media path, and exported frames at 3 word times in sync with the transcript | | |
| **B** | **AE motion build with a licensed track** (`--video-id EP02TEST_R02_MO`) | | | | | | |
| B1 | Pick a licensed track | T46 §5 steps 2–4; PROGRESS "AE music" | make the 45 s synthetic bed `C/data/Music/Live/tense_dark_bed.wav` (pinned ffmpeg, lavfi); add `licence.json` (`"license":"client"`, `"files":"*"`); `reel motion-plan`; `reel motion-animatic` | `audio.music.rel` = that file; keyframes present; `needs_you` = []; the bed dips under each phrase and rises in long pauses | read-back JSON, plus listening to the animatic | | |
| B2 | Build and read-back | T46 §5 step 6; R-L5 | `reel approve-plan --by delegated`, then `reel motion-build` | `PROJECT_ASSEMBLED`; `readback.audio` has one DIALOGUE, one MUSIC (out_frame = end_frame, keys equal to the plan's within 0.01 dB on both channels) and one SFX_* per cue; `comparison.ok` | `04_after_effects/motion-build-result.json` | | |
| B3 | −60 dB floor and linear keys | R-L5; T46 §5 steps 7, 9 | in AE: MAIN → MUSIC → Audio Levels | the fade keys read −60, not clamped to −48 (compare the values exactly: the read-back accepts ≤ −48); the keys are linear | read-back values, plus a screenshot of AE | | |
| B4 | Render and listen | R-L5; PROGRESS | `reel motion-render`, `reel motion-frames` | a clean render; at a dip the music sits under the speech; the 24 frames are as planned | render listen, plus AE's own frames | | |
| B5 | Rebuild, then remove the licence | T46 §5 step 8 | `reel motion-build` again; delete `licence.json`; `reel motion-build`; `reel motion-plan` | still one MUSIC layer; the build refuses as stale; the plan has no music, one NEEDS-YOU music item and a draft under `06_audio/licence-drafts/Live/` | read-back JSON | | |
| B6 | Arabic track name and a short track | T46 §5 step 9 | a second licensed bed with an Arabic name, shorter than the video | the name round-trips through `File.decode`; the track ends cleanly at its own end (end_frame < duration) | read-back JSON, plus render listen | | |
| B7 | AE crash modal | R-L1; PROGRESS (CEP queue H6) | 3 launches through explorer and 3 through the engine launcher (`adobe_run`; how to trigger: confirm), each after a clean quit; count the `#32770` modals | modals counted; none answered with Reset or Safe Mode; the no-heartbeat message names the on-screen dialog (Adobe track builds this message after T4.6; if it has not landed by the gate, this row becomes an owner-visible risk line in the gate record, never a silent skip) | log, plus screenshots | | |
| B8 | `-r` with a space in the path | R-L3 | a second /XJ copy at a path with spaces; `reel motion-build --run-script` (confirm this is the right route) | the script is staged without spaces and runs; or `SCRIPT_STAGE_FAILED`, never silence | log, plus the `.aep` written | | |
| **C** | **The rest** | | | | | | |
| C1 | Look recommender (Task 28) | PROGRESS; phase-4 Task 28 | `reel looks recommend --kind caption`; `reel caption-looks --pick <NAME> --yes` (copy only); recommend again | one plain-words reason line; top three with stills under `08_quality_control/previews/caption-looks/`; the profile is unchanged until `--yes`; after the pick, the recent-use penalty shows | read-back JSON, the stills viewed, and a hash of the profile before and after | | |
| C2 | M-list business fixture, stage 7 | PROGRESS; Addendum M QC (M6); T4.13; BLD-A spec `D:\ClaudeData\claude-api-lane\pause-builders\A-prep\C2-business-fixture.md` | a fresh /XJ copy of `whynot-test\CLIENT` CLIP1 with `A-prep\C2-edit-decisions.json` as its edit-decisions; `reel plan`, then `reel review-scan` (lands with lane4 hooks\task50, sha to follow, confirm; run LAST in C), then `reel review-flags --from` | a business flag on GFX_010 only (2.3–4.0 s, «الكشف عندنا ٣٠٠ جنيه وخصم ٢٠٪ على أول جلسة»); the other 3 lines carry no business flag (negative control); no flag on on-screen wording vanishes | `review-flags.json` read-back, plus the review table | | |
| C3 | `reel clean` (verb lands with hooks\T4.15 r2, sha to follow, confirm; run LAST in C) | PROGRESS; phase-4 Task 15 step 4 | `reel clean` dry-run on the real engine home | sizes listed (`cache_uv`, `cuda_redist` …); nothing deleted; the home listing is unchanged | `~/.whynot-cut` diff, plus JSON | | |
| C4 | K1 switches-on live plan (executor flips the accepted switches) | PROGRESS "K1 switches" | one `reel plan` with the switches on, on the copy | the plan compiles; K-T3's cut fades compose with T4.1's multiplied fades | read-back JSON; plan: `docs/superpowers/evidence/k1-switches-dryrun.md` (executor, before the tag) | | |
| C5 | Latin terms by ear (Task 55; **who: the editor or Yunus**, about 15 min, any audio player, not run by the Adobe track) | Addendum M M2-T3; Task 55 ruling Q55-1; evidence `docs/superpowers/evidence/2026-10-19-m2-latin-terms.md` | play EP02 (`whynot-test\Dr Sherin Helmy\data\Raw\EP02.mp4`, read only) at the 24 labelled-English and 17 uncertain times listed in `D:\ClaudeData\claude-api-lane\lane4\work\task55\podcast-test-item.md`; mark each E (said in English), A (Arabic word or loanword) or N (not said) | every row has E, A or N; if an English row is A or N, or an uncertain row is E, BLD-A recomputes the Task 55 numbers (`analyse.py`, labels.json) and updates the evidence | the editor's ear; BLD-A recomputes | | `lane4\work\task55\labels.json` + the editor's E/A/N list |

**Stop rules.**
1. Any change in `~/.whynot-cut` outside the expected paths → stop.
   - Expected for group A: `ppro-queue/`, `ppro-scripts/` and `logs/`.
   - Expected for group B: `ae-queue/`, `ae-scripts/` and `tmp/ae-run/`. These are the engine's normal AE paths; the
     Adobe track rules this, not a plan-session question.
   - Always allowed: the baseline `uxp-spike/lifecycle.json`.
2. Any item that would need a bridge or UXP panel build newer than the installed PREVIEW 3.0.0 (322d8a5), that is a
   re-install → mark it NEEDS-INSTALL, do not run it, and report it to the plan session.
3. A client project is open → do not touch it.
4. Also stop if `FREEZE` is set, if RAM is at 85% or more (wait), or at an AE modal you may not answer (leave it for
   Yunus).
5. A refusal or a "stale" result is a finding to record. Never edit a gate file to get past it.

**Not run here.**
- **R-L2** (AE quits on its own after launch): **Gate 6, not run here.** It needs the first launch after a reboot on
  the clean machine, with `aemon.ps1` running.
- **R-L4** (QE `remove()`): **Gate 6, not run here.**
- **R-L6 r4 / T41 #14** (Volume Level found by match name): needs a Premiere in another language, which means a
  language install or preference change. Gate 6 or Mac.
- **T41 #1, interpolation read through the UXP adapter (K6): not run, NEEDS-INSTALL.** The 3.0 UXP panel is
  installed now (PREVIEW 322d8a5). Its adapter has no interpolation read, though; only the spike's probe has one
  (`adobe/premiere-uxp/spike/src/probes.ts`). So it needs a newer panel build. A4 uses the Effect Controls graph
  instead (executor-accepted).
- **The re-bundled bridge (PROGRESS: "re-bundled (`cep_bundle`)"): partly live now.**
  - The installed bundle is a `cep_bundle` 3.0.0 build (322d8a5, protocol 4), so its daemon, queue, heartbeat and
    version check run live in this checklist.
  - Its `lib` mode, with this build's own libraries, is still NEEDS-INSTALL: the bundled libraries are 322d8a5's, so
    this run uses the dev loop (`WHYNOT_BRIDGE_DEV=1`, synced libraries as `script=`; see Setup).
- **The signed 3.0.0 ZXP, and M1-T4/T6 through the panel:** Gate 6.
- **Live Mac checks:** Phase 12 (H18).
- **T4.14 CPU 60 s:** a separate overnight gate item. It also needs Yunus's verified 60 s transcript.

**Follow-ups (not Gate 4).**
- Automated marker read-back in the JSX, so A13 and A14 need no manual check: a Stage 3 ticket.
