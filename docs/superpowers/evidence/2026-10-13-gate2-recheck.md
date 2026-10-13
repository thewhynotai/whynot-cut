# Gate 2 live recheck after the G1 fix round: 2026-10-13, Windows PC (LOQ)

Engine: `./whynot-cut/bin/reel` from the repo root (branch release/3.0, plugin 3.0.0, runtime r-6e4a68a292b4, working
tree as found, with uncommitted changes). Test data only: `Editing Plugin/whynot-test/عميل-تجربة-٣`, video-id `CLIP_6EB37C`.
Nothing in `D:\WhyNot Clients` was written. `reel plan` was **not** run. The approval from 12-Oct (delegated,
fingerprint b05ad19462908eef, format 3) was still valid, and no build said "not approved".
Times are local (+03:00). Elapsed times are wall clock around each command; "bridge" is the bridge job's `elapsed_s`.

## 1. Premiere start: Verified
- At 02:07 Premiere and After Effects were not running: there was no process, and `ppro-status` and `ae-status`
  showed heartbeats about 14,340 s old.
- The exe came from `reel doctor` adobe_found: `C:\Program Files\Adobe\Adobe Premiere Pro 2026\Adobe Premiere Pro.exe`.
- I started it with `Start-Process` at 02:08:20 (pid 49240).
- `reel ppro-status` showed **alive** at 02:08:42 (22 s): bridge_version **3.1.1**, role **daemon**, Premiere 26.5.2
  build 5, projects_open 0.

## 2. B2: two `ppro-build --force` in a row, nothing touched in Premiere: **FAILED**
| # | when | command | status | exit | wall | bridge | closed_previous | `_prev_` created |
|---|---|---|---|---|---|---|---|---|
| 1 | 02:09:06 | `ppro-build --force` | **PRPROJ_BUILT**, 11/11 checks true | 0 | 36.1 s | 31.0 s (job 20261013-020911-a6725c) | closed false, "not open" | `CLIP_6EB37C_RE_EDIT_prev_20261013-020911-25620500.prproj` (the 12-Oct build) |
| 2 | 02:09:53, right after #1 | `ppro-build --force` | **EDITOR_CHANGES_PRESENT** (false refusal) | 2 | 2.5 s | n/a | closed **true** | none |

Build #1's checks were all true: prproj_saved_this_run, preview_codec_prores_422_lt, frame_1080x1920, fps_24,
linear_color_on, max_bit_depth_off, max_render_quality_off, all_graphics_placed (9 placed), v1_sharpened,
caption_track_ok, dialogue_on_A1_A2. Its settings_after: previewCodec apcs, 1080×1920, videoFrameRate ticks 10584000000
(24 fps), compositeLinearColor true. It was a newProject.

Build #1 updated ppro-build-result.json:
- before: mtime 12-Oct 21:50:40, sha1 ac8676e9…
- after: mtime 02:09:42, sha1 cd154ceb…, content_signature `2ae5fe2d917e…`, prproj_mtime 1791846581.709

Build #2's refusal said: "the project open in Premiere had changes that are not the pipeline's". Its detail.content was
"changed (saved by Premiere when the build closed the open project)".
- After the refusal, ppro-build-result.json was not rewritten. That is correct: the record keeps the pipeline's signature.
- Premiere's close save made the .prproj grow from 21108 to 21140 bytes (02:09:55) and wrote a `.prin` file.
- `prproj_signature` of the closed file is `fa65bb5e…`, not the recorded `2ae5fe2d…`.
- **Nothing was touched in Premiere between #1 and #2.** I made no clicks, and the only commands were `ls`, `stat` and
  `sha1sum`.

### Diagnosis (extra runs, test project only)
I ran these to find what changed. There was no editor work to lose: this Premiere session started with no project open.

| # | when | command | status | wall | bridge | closed | `_prev_` created |
|---|---|---|---|---|---|---|---|
| 3 | 02:10:23 | `ppro-build --force --replace-edited` (to get past #2's refusal) | PRPROJ_BUILT | 5.4 s | 3.5 s | false ("not open": #2's close had closed it) | `_prev_20261013-021025-71010700` |
| 4 | 02:10:36 | `ppro-build --force` | **PRPROJ_BUILT** | 7.0 s | 4.0 s | **true** | `_prev_20261013-021039-29398300` |
| | 02:11:08 | Premiere closed gracefully (`CloseMainWindow` on pid 49240, which I started; the project was whynot-test). The close did not save the .prproj | | | | | |
| | 02:11:13 | Premiere restarted (pid 96008), alive 02:11:19, 3.1.1, daemon, 0 projects | | | | | |
| 5 | 02:11:28 | `ppro-build --force` | PRPROJ_BUILT | 7.7 s | 5.0 s | false, "not open" | `_prev_20261013-021131-18992900` |
| 6 | 02:11:36, right after #5 | `ppro-build --force` | **PRPROJ_BUILT** | 6.2 s | 3.5 s | **true** | `_prev_20261013-021139-16217800` |

- The repeat pair (#5 then #6, the same scenario as #1 then #2 after a Premiere restart) **passed**. Pair #3 then #4
  also passed.
- In those passing pairs, the file the build saved and the file Premiere saved on close have identical signatures. The
  normalised XML diff between them is empty:
  - build #3 and its close: `aba1ea9c…` both times;
  - build #5 and its close: `4d3e0589…` both times.
- So the failure is **intermittent** and tied to build #1. That build was slow (31 s in the bridge, against 3.5–5 s for
  the others): it was the first build in a fresh Premiere and replaced the 12-Oct project.

I compared what Premiere saved on #2's close with what it saved on #6's close (a passing close). I applied the same
`_VOLATILE` normalisation, masked the GUIDs and the `stills-<timestamp>` paths, and diffed. The failing close-save has
these extra keys:
```
<HSL.TimelinePatchingAndTargeting.AudioPatchesG>[{"mNumber":0,"mState":2},{"mNumber":1,"mState":2}]</...>
<HSL.TimelinePatchingAndTargeting.VideoPatchesG>[{"mNumber":0,"mState":2},{"mNumber":-1,"mState":0},…]</...>
<MZ.SourceTrackState>2|0</MZ.SourceTrackState> + <MZ.SourceTrackNumber>0|1|-1</MZ.SourceTrackNumber>   (on all 10 tracks)
```
It also has a different element order for `CCLibrariesLocation0`, `CapsuleMediaLocation0` and `AutoSaveLocation0`, and
for the two `DVAMarker`s.

These keys are timeline UI state: source patching and track targeting. Premiere writes them when the sequence's
timeline panel initialises. In the cold session it did that after the build had already saved. They are not editor
content.

The pre-close bytes of build #1 were overwritten by the close save, so I could not diff them directly. This is a strong
inference, not a byte-level proof.

**Suggested fix:**
- Add these to `verify._VOLATILE`: `HSL.TimelinePatchingAndTargeting.*`, `MZ.SourceTrackState` and
  `MZ.SourceTrackNumber`.
- Consider order-insensitive handling of the `*Location0` and DVAMarker siblings.
- Or have the bridge save once more after the timeline is shown, before the signature is taken.

The scratchpad has the snapshots: after-close-b2, after-build3, b3-closed, after-build5 and b5-closed (.prproj and the
normalised .xml).

### `_prev_` files now in `07_premiere/project/`
`_prev_20261013-020911-25620500` (the 12-Oct build), `_prev_20261013-021025-71010700` (#2's close save),
`_prev_20261013-021039-29398300`, `_prev_20261013-021131-18992900`, `_prev_20261013-021139-16217800`.
- `ppro-build-result.json` now holds build #6: at 02:11:42, content_signature `9cfd46d5…`.
- `07_premiere/media/` now holds only the two newest folders, `stills-20261013-021131` and `-021139`, so the older
  stills folders are cleaned up.
- Writer-lock note: build #1 printed "took over the stale lock of session 0ceb43a2… (reel ppro-frames …, since
  2026-10-12T21:43:31): its process 17480 … is no longer running". This is the stale-lock takeover working.

## 3. `reel ppro-frames`: Verified
- 02:12:12: ok true, frames 6/6, media_pending [], pending_frames [], media_wait online after 1 poll, 4.6 s.
- Output: `run-20261013-021213`, with frames 002100, 002500, 002538, 007000, 007683 and 013500.
- I viewed the sheet. It is copied as `2026-10-13-gate2-recheck-frames.png`. It matches 12-Oct:
  - GFX_001 context_card «شرب الماء كل يوم» appears at 2:02, 2:12 and 2:13.
  - The caption "Today we talk" appears at 2:02–2:13.
  - GFX_002 statement_highlight «الماء يساعد جسمك» appears at 7:00 and 7:16.
  - 13:12 is clean.
  - Arabic is joined and right-to-left with no tofu, in Segoe UI (the documented fallback: this client has no Arabic
    font).
- **PASS**.

## 4. Unsaved change refused: Not verified live (unit-tested)
This needs a manual edit in Premiere's UI (clicks). I skipped it as the brief allows.

## 5. `reel doctor` (02:12, 2.4 s, exit 0)
- **guard_active: null ("can't tell")**, with the 2.x note: "the installed WhyNot Cut 2.2.1 guard writes no heartbeat
  (that check came with 3.0) … type /hooks". silent_guards: 2.2.1. That is the expected accurate answer while the 2.2.1
  plugin is the installed one, and the false "not confirmed running" alarm from 12-Oct is gone.
- adobe_found:
  - Premiere 26.5.2.5
  - After Effects 26.5.0.89
  - Media Encoder 26.5.2.2
  - Photoshop 27.11.0.26
- premiere_bridge: 3.1.1, alive, debug_mode_ok. Runtime up_to_date, problems []. ready.premiere_build true.
- Verdict: "READY — but plain `reel` does not run WhyNot Cut in this session".
- Fixes listed:
  - The 2.2.1 `reel` is first on PATH (restart Claude Code).
  - The guard cannot be checked (2.2.1).
  - `Dr Sherin Helmy` has no client marker. I did not run the fix: that is a real client.
- Before Premiere was started (02:07), doctor also listed "Premiere bridge not running". That item is gone now.

## 6. Premiere left running
Premiere pid 96008 is running with the test project open (`CLIP_6EB37C_RE_EDIT.prproj`, projects_open 1). It was
alive, idle and daemon at 02:13. After Effects was not started.

## 7. B2 fix loop 1 (02:14–02:31): root cause at byte level, fix 09cb376, live re-check
Same machine, test project only (`whynot-test/عميل-تجربة-٣`, CLIP_6EB37C). Premiere was restarted gracefully
(`CloseMainWindow` on pids this session started, test project open, nothing unsaved) four times. Nothing in
`D:\WhyNot Clients` was touched. Captures: scratchpad `b2fix/` (`<pair>-A-build.prproj` = the file right after build A,
`<pair>-B-closesave.prproj` = what Premiere wrote when build B closed it; `pdiff.py` diffs the gunzipped XML).

### Reproduced before the fix (old signature)
| pair | Premiere | B (untouched `--force`) | what the close save changed, beyond the old `_VOLATILE` keys |
|---|---|---|---|
| cold1 (02:16) | fresh start, first build | **EDITOR_CHANGES_PRESENT** | 9 stills: `<ContentCredentialsInfo>65536</…>` became `<CCFileModTime>1791…</…>` (the content-credentials scan finished after the build's save) |
| warm1, warm2 | warm | PRPROJ_BUILT | none |
| warm3 (02:18) | warm | **EDITOR_CHANGES_PRESENT** | the two `HSL.TimelinePatchingAndTargeting.{Audio,Video}Patches…` keys swapped order in the sequence's `<Properties>` bag |

Also seen: between builds, the build save itself sometimes has the patching keys (`HSL.TimelinePatchingAndTargeting.*`
and `MZ.SourceTrackState`/`MZ.SourceTrackNumber` on all 10 tracks) and sometimes not (warm2 build: none; warm3 build:
all). So the 02:09 failure (keys absent at the build's save, present in the close save) is the same race: Premiere's
timeline panel writes source patching/targeting when it initialises the newly opened sequence, before or after the save.
**Root cause:** Premiere finishes background work after the build has saved (content-credentials scan, timeline
patching/targeting init) and stores property bags as an unordered map. The old signature hashed the raw XML text, so
any of these made an untouched close save look like editor work.

### Fix (09cb376, verify.py + ppro_build.py)
- `prproj_signature` = `c2:` + sha1 of a canonical form (ElementTree). Left out: the old bookkeeping, the
  content-credentials keys, `HSL.TimelinePatchingAndTargeting.*`, `MZ.SourceTrack{State,Number}` and pure view state
  (timeline scroll/zoom, Program monitor zoom, bin expansion). Children with all-different names and no children of
  their own are sorted (property bags, param records: no information lost). Lists (repeated names) keep their order.
- Deny-list, not allow-list: the diff shows four families, and a missing allow-list entry would silently miss editor
  work (the loss B2 guards against). A missing deny-list entry only costs a refusal that names `--replace-edited`.
- `signature_matches` compares in the recorded format, so 2.2.1 / earlier 3.0 records (no prefix) still compare with
  the old algorithm. An unchanged close re-records the `c2:` signature.
- On the captured bytes: cold1 and warm3 differ under the old signature and are equal under the new one. warm1/2,
  build3/close and build5/close are equal under both. Two different builds still differ.

### Tests
`tests/test_gate2_safety.py` 22 OK (14 existing + 8 new, fictional real-shaped fixtures modelled on the captures).
test_bridge_queue 54 OK, test_plugin 105 OK (1 skip), test_pipeline 25 OK (3 skips),
test_crossplatform `untouched_save` OK.

### Live after the fix (engine at 09cb376's code)
Setup build `--force --replace-edited` (02:24, to replace warm3's refused close save). Then untouched pairs, each
`ppro-build --force` twice in a row with no clicks:

| pair | Premiere | A | B | drift in the close save |
|---|---|---|---|---|
| fixW1, fixW2 | warm | PRPROJ_BUILT | PRPROJ_BUILT | none |
| fixC1 (02:25:24) | **fresh start, first build** | PRPROJ_BUILT (closed false, not open) | PRPROJ_BUILT | none |
| fixC2 (02:25:49) | **fresh start, first build** | PRPROJ_BUILT | PRPROJ_BUILT | none |
| fixW3, fixW4 | warm | PRPROJ_BUILT | PRPROJ_BUILT | none |
| fixW5 (02:27:01) | warm | PRPROJ_BUILT | **PRPROJ_BUILT** | patching keys reordered: the old signature would have refused |
| fixW6–fixW9 | warm | PRPROJ_BUILT | PRPROJ_BUILT | none |
| fixC3 (02:28:58), fixC4 (02:29:38) | **fresh start, first build** | PRPROJ_BUILT | PRPROJ_BUILT | none |

Result: 13 untouched pairs, 26/26 PRPROJ_BUILT, 0 EDITOR_CHANGES_PRESENT. Four of them were the first build in a fresh
Premiere. One (fixW5) had live drift that the old signature refused. The content-credentials drift did not recur live
after the fix; it is covered by cold1's captured bytes and the unit test. The record now holds a `c2:` signature.

`reel ppro-frames` (02:29:57): ok, 6/6 frames, media online after 1 poll, 4 s, `run-20261013-022957`. I viewed the
sheet and it matches §3: GFX_001 «شرب الماء كل يوم» at 2:02–2:13, the caption "Today we talk", GFX_002 «الماء يساعد
جسمك» at 7:00/7:16, 13:12 clean, Arabic joined RTL. Copied as `2026-10-13-gate2-b2-fix-frames.jpg`.
Premiere is left running (pid 126216) with the test project open (projects_open 1, alive, 02:30).

## 8. Final live recheck at e37c712 (02:57–03:00)
Engine: working tree with `whynot-cut/engine` identical to HEAD e37c712 (`git diff HEAD -- whynot-cut/engine` empty).
Same machine, test project only (`whynot-test/عميل-تجربة-٣`, `--video-id CLIP_6EB37C`). Nothing in `D:\WhyNot Clients`
was touched. `reel plan` and approve-plan were not run, and no build said "not approved". Premiere was not restarted.
Commands from the repo root: `./whynot-cut/bin/reel ppro-build --root ../whynot-test/عميل-تجربة-٣ --video-id CLIP_6EB37C --force`.
Captures: scratchpad `final/` (`<run>.json`, `<run>-build.prproj`, `at0248-current.prproj`, `cdiff.py`).

### 8.1 `reel ppro-status` (02:57:33): Verified
alive, age 0.7 s, bridge_version **3.1.1**, role **daemon**, Premiere 26.5.2 build 5, projects_open 1 (the Adobe
track's `whynot-test/_uxp-spike/spike-20261013-024944.prproj`).

### 8.2 Starting state: a new drift family (finding, not part of the untouched pairs)
The first `ppro-build --force` (02:57:58) and a second one right after it returned **EDITOR_CHANGES_PRESENT** (exit 2):
built_at 02:29, edited_at 02:48, content "changed". The test project had been saved by Premiere at 02:48:50
(20962 bytes and a `.prin` file), between §7's last build (fixC4-B, 02:29:40) and the spike project being created at
02:49:44. That is when the Adobe track switched Premiere to its spike project. This session made no click.
- The record's `c2:f1778860…` equals the signature of the captured fixC4-B build bytes (`b2fix/fixC4-B-build.prproj`).
  The 02:48 save signs `c2:09919b13…`.
- Canonical diff (verify._canonical, both files), the only change: on one sequence's `VideoComponentChain`
  (ObjectID 139), the empty `<ComponentChain>` gained
  `<Node><Properties><MZ.ComponentChain.ActiveComponentID>1</…><MZ.ComponentChain.ActiveComponentParamIndex>4294967295</…></Properties></Node>`.
  That chain's sibling order also differs, but only because the chain now has children, so the property-bag sort no
  longer applies to that level.
- `ActiveComponentID` / `ActiveComponentParamIndex` record which effect is selected in Effect Controls, which is UI
  state and not editor content. It appears once a clip or the sequence is shown or selected in Effect Controls (by a
  UI click or by the UXP spike; I cannot tell which from here). The c2 deny-list does not cover it. Per the B2 design,
  the cost is a refusal that names `--replace-edited`, not a missed edit.
- **Suggested follow-up:** add `MZ\.ComponentChain\.Active.*` to `_VOLATILE_TAG`, and drop the `Node`/`Properties`
  wrapper that becomes empty, so that a chain holding only this state canonicalises like an empty `<ComponentChain>`.
  Add a unit test from these captured bytes.

To get a clean start I ran one setup build with `--force --replace-edited` (test project, the 02:48 file kept as
`_prev_20261013-025904-85298100`), as in §7.

### 8.3 Two untouched pairs: Verified
Each run was `ppro-build --force`, back-to-back, with no clicks or other commands between them.

| run | start | status | checks | exit | wall | bridge (job) | closed_previous | content_signature |
|---|---|---|---|---|---|---|---|---|
| setup (`--replace-edited`) | 02:59:02 | PRPROJ_BUILT | 11/11 | 0 | 5.4 s | 3.0 s (025904-65a1d8) | false, "not open" | `c2:0928b6c7…` |
| pair 1 A | 02:59:08 | **PRPROJ_BUILT** | 11/11 | 0 | 4.9 s | 2.5 s (025910-3c3817) | **true** | `c2:18ee6071…` |
| pair 1 B | 02:59:13 | **PRPROJ_BUILT** | 11/11 | 0 | 4.0 s | 2.5 s (025914-fd7193) | **true** | `c2:857af167…` |
| pair 2 A | 02:59:17 | **PRPROJ_BUILT** | 11/11 | 0 | 4.9 s | 2.5 s (025919-5e5bdf) | **true** | `c2:dbe2f832…` |
| pair 2 B | 02:59:22 | **PRPROJ_BUILT** | 11/11 | 0 | 3.8 s | 1.5 s (025924-3f7a71) | **true** | `c2:12897dbf…` |

- Result: 4/4 PRPROJ_BUILT and 0 EDITOR_CHANGES_PRESENT. Each A also closed the previous build's project
  untouched, so all 4 runs exercised the close-save comparison.
- The checks in every run were: prproj_saved_this_run, preview_codec_prores_422_lt, frame_1080x1920, fps_24,
  linear_color_on, max_bit_depth_off, max_render_quality_off, all_graphics_placed (9 placed: GFX_001,
  GFX_002_bar/_fg, CAP_001–005, CAP_008), v1_sharpened, caption_track_ok and dialogue_on_A1_A2. stderr was empty.
- After the last build, `ppro-build-result.json` (02:59:25, 7568 bytes) holds content_signature
  **`c2:12897dbfdbde5ca1117e0edd973589170c13237e`** (prefix `c2:`) and prproj_mtime 1791849565.577.
- `07_premiere/media/` holds `stills-20261013-025910`, `-025914`, `-025919` and `-025924`.

### 8.4 `reel ppro-frames` (02:59:42): Verified
- Result: ok true, frames 6/6, media_pending [], pending_frames [], media online after 1 poll, pending retries 0,
  exit 0, 3.4 s. Output in `run-20261013-025943`.
- I viewed the sheet. It is copied as `2026-10-13-gate2-final-frames.jpg`. It matches §3 and §7:
  - GFX_001 context_card «شرب الماء كل يوم» appears at 2:02, 2:12 and 2:13.
  - The caption "Today we talk" appears at 2:02–2:13.
  - GFX_002 statement_highlight «الماء يساعد جسمك» appears at 7:00 and 7:16.
  - 13:12 is clean.
  - Arabic is joined and right-to-left with no tofu.
- **PASS**.

### 8.5 Premiere left running
At 02:59:54, Premiere pid 89252 (not started by this session) was alive, idle, daemon and 3.1.1, with projects_open 2:
`CLIP_6EB37C_RE_EDIT.prproj` (active) and the Adobe track's spike project, both under whynot-test.

### Verdict
B2 at e37c712 is **verified live**: 2 untouched pairs out of 2 passed, the record is `c2:`, and the frames are
correct. There is one new false-refusal source, Effect Controls selection state (`MZ.ComponentChain.Active*`), seen
once on a save made outside the pipeline. It is not a data-loss risk, but it is worth a deny-list follow-up (§8.2).
