# Premiere UXP parity record (T6.4) - live spike on Premiere Pro 26.5.2

What the UXP plugin can and cannot do compared with today's CEP/ExtendScript bridge
(`whynot-cut/templates/premiere/nh_ppro_lib.jsx`), measured live. Every green below has evidence from a results file;
nothing is green from reading code or `premierepro.d.ts` alone. **Spike 0.1.2 is the current verdict**; the 0.1.0 and
0.1.1 runs are kept as history (each row says what 0.1.1 showed when it differs).

| | |
|---|---|
| Date | 2026-10-12. Spike 0.1.0 / 0.1.1 runs 00:26 - 00:42 local (UTC+3), spike 0.1.2 runs 01:38 and 01:40 local, spike 0.1.3 run 21:19 local (18:19Z); the `at` fields in the JSON are UTC |
| Machine | Windows 11 Pro (build 10.0.26300; UXP `os.release()` reports the compat string `6.2.9200`), x64 |
| Premiere Pro | 26.5.2 (`uxp.host.version`; `ppro.Application.version` returns undefined, see P2) |
| UXP | `uxp-9.3.0-local` (results key `uxp`; `host_info` key `uxp_version`) |
| Spike | `ai.thewhynot.cut.spike` **0.1.3** (current verdict; it adds the engine-daemon connection and the host calls), 0.1.2 (source commits `18db177` and `1181eaa`), 0.1.1 and 0.1.0 before it |
| Types | `@adobe/premierepro` 26.5.0 (`adobe/node_modules/@adobe/premierepro/src/premierepro.d.ts`) |
| Install method | **UPIA `/install` of `dist/uxp/WhyNotCut-Spike.ccx`**, no Developer Mode, no PlayerDebugMode, no UDT. Confirmed working with 0.1.1: the UPIA list output reads "Enabled WhyNot Cut Spike 0.1.1"; the panel appears under Window > UXP Plugins and runs. Premiere was restarted once after the install. This is the install path the installer can use. 0.1.2 (commits `18db177` and `1181eaa`) was installed by the controller the same way: UPIA `/install` exit 0, `/list` shows "Enabled WhyNot Cut Spike 0.1.2", with Premiere closed; the product panel 3.0.0 likewise ("Enabled WhyNot Cut 3.0.0"). `host_info` reports `plugin_version: 0.1.2`. |
| Manifest | v5, `host {app: premierepro, minVersion: 26.5.0}`, `localFileSystem: fullAccess`, `clipboard: readAndWrite`, `network.domains: [ws://127.0.0.1, http://127.0.0.1]`. **These entries do not match a URL with a port, so UXP blocked the 0.1.3 connection** (W1). Ruling: `network.domains: "all"` in the product and spike manifests (spec fallback rule); another implementer is changing it |
| Test data | only under `Editing Plugin/whynot-test/` (fictional PODCAST-TEST: one base FCP7 XML + one PNG still); nothing in `D:\WhyNot Clients` |

Result files are on this PC in `C:\Users\LOQ\.whynot-cut\uxp-spike\` (`results-20261012-HHMMSS.json`), plus
`whynot-test\_uxp-spike\filters-*.json` (the 108 video filters) and `...\_uxp-spike\frames\` (the exported PNGs of the
0.1.2 runs: `exp_20261012-013838_*` and `exp_20261012-014010_*`). Screenshots are committed under
`docs/adobe/evidence/`.

## Runs

| File (`results-20261012-...`) | Spike | Mode | Outcome |
|---|---|---|---|
| `002655`, `002846`, `002903`, `002912` | 0.1.0 | `002655` and `002846` kept open (`kept_project_open: true`), `002903` and `002912` normal | The safety guard compared the raw `project.path`, which Windows reports as `\\?\D:/...`, and refused it: `create_project` created the file but every later probe was skipped ("no scratch project"). Safe by design, no data. `host_info` also failed (`Clipboard access not supported for 3P plugins with manifest version upto 4`: it needs a v5 manifest with the `clipboard` permission). The only useful number: `create_project` took 32 955 / 2 583 / 2 624 / 1 970 ms. |
| `004022` | 0.1.1 | **Run, keep project open** (`kept_project_open: true`) | 10 probes ran; `save_close_open` skipped on purpose. Cold run: `import_fcp7_xml` took 7 572 ms. |
| `004058`, `004108`, `004145` | 0.1.1 | Run spike (`kept_project_open: false`) | Full run including save / close / reopen. Identical outcome per step in all three runs. The reopen failed in all three (`Failed to open the project`); position, crop, Gaussian Blur, preview codec and frame export were red. |
| **`013838`** | **0.1.2** | **Run spike** (full, `kept_project_open: false`) | **18 probes: 14 pass, 2 fail, 2 n/a** (counted from the file: `effects_by_match_name` fails only on the Repeat Edge Pixels lookup; `save_close_open` fails because open attempts 1 - 3 failed although attempt 4 succeeded; `ws_loopback` and `encoder_export` are n/a). All of save / close / reopen / save-as ran. 26 PNGs in `frames/` per 0.1.2 run (52 with the next run). |
| **`014010`** | **0.1.2** | **Run, keep project open** (`kept_project_open: true`), stops after `undo_transaction` | 15 probes: 13 pass, 1 fail (the same effects step), 1 n/a (`ws_loopback`). This is the run the panel shows ("Done: 13 pass, 1 fail, 1 n/a"; screenshot below) and the project the History screenshot belongs to. All the measurements of 013838 repeat here (same PNG checksums for the time-basis frames). |
| `204411`, `204511` | 0.1.2 | normal runs at 17:44Z and 17:45Z (between the 0.1.2 and 0.1.3 runs) | Both failed early and are not used as evidence: `204411` (1 pass, 13 fail, 1 n/a) stopped at `create_project` ("createProject returned nothing" after 15 050 ms, so every later probe was refused); `204511` (5 pass, 11 fail, 2 n/a) created the project but `import_fcp7_xml` found no new sequence after 22 823 ms ("importFiles returned true but it created no new sequence"). Cause not recorded; createProject and the XML import can fail in a bad state, so the adapter needs a verify-and-retry. |
| **`211920`** | **0.1.3** | **Run spike** (full, `kept_project_open: false`; Premiere 26.5.2) | **19 probes: 15 pass, 3 fail, 1 n/a** (counted from the file; the spike panel in the screenshot reads "Done: 15 pass, 3 fail, 1 n/a"). The 3 fails: `ws_loopback` (new in 0.1.3: **UXP refused the connection**, W1), `effects_by_match_name` (**same single reason as 0.1.2**: only the "Repeat Edge Pixels" lookup by name, Blurriness 90 reads back; Sharpen, Noise, Lumetri ok) and `save_close_open` (**same as 0.1.2**: open attempts 1 - 3 failed in 1 376 / 2 / 755 ms, attempt 4 with the backslash path opened in 957 ms and persistence verified; save 2 634 ms, close 396 ms). n/a: `encoder_export` (off). New probe `host_calls` ok (H1 - H3). Everything else of 0.1.2 repeats: the time-basis and frame-export PNGs have the same checksums as in `013838`; the winning export form is again `name + dir\`. `create_project` took 14 717 ms, `import_fcp7_xml` 1 023 ms, `export_frame` 13 679 ms. 26 more PNGs in `frames/` (`exp_20261012-211920_*`). Screenshot: `docs/adobe/evidence/2026-10-12-premiere-run4-panel-blocked.webp`. |

Status legend: 🟢 works, verified live. 🔴 did not work (the cause column says API gap or spike defect). 🟡 partly works
or works with a condition. ⚪ pending: not probed, or blocked. Decision rule: green -> UXP adapter; red -> CEP compat
op through the engine daemon, or the documented fallback of `docs/review/2026-10-11/adobe.md` ("Fallback plan if a UXP
API is missing"). **Partial (🟡) and pending (⚪) rows stay on the CEP path until a re-measure turns them green**; a 🟡
row's Decision column says what the UXP adapter will do once it is green, not that it may ship now.

## The matrix

Evidence notation: `R/<run>` = `results-20261012-<run>.json`; `ops[x]` = the entry with `op == x`; `steps[y]` = the
sub-step named `y` in `detail.steps`. Times are ms unless marked s. "0.1.1:" in a row is what the earlier spike showed.

### A. Host and projects

| ID | WhyNot Cut operation | Status | UXP API used | Evidence | Cause / condition | Decision |
|---|---|---|---|---|---|---|
| P1 | Read host, OS, fs, globals | 🟢 | `require("uxp").host`, `require("os")`, `require("fs")` | R/013838 `ops[host_info]` (all 10 steps ok): `steps[uxp_host]` name `premierepro`, version `26.5.2`, `uxp_version` `uxp-9.3.0-local`, `plugin_version` `0.1.2`. 0.1.1 (R/004145): fs has readFile / writeFile / mkdir / lstat / readdir / readFileSync / writeFileSync / lstatSync; `mkdirSync`, `existsSync`, `TextDecoder` undefined; `WebSocket` and `fetch` are functions | `uxp.versions` has no enumerable keys; read `uxp.versions.uxp` | UXP adapter. Do not use `TextDecoder`, `mkdirSync`, `existsSync` |
| P2 | Read the Premiere version | 🔴 | `ppro.Application.version` (typed `Promise<string>`) | R/013838 `steps[premiere_version (informational)]`: raw and awaited value are both `undefined`; `source: "uxp.host.version"`, value `26.5.2` | API quirk on 26.5.2, not a spike defect | UXP adapter reads `uxp.host.version` instead (green, P1) |
| P3 | Active project name and path | 🟢 | `Project.getActiveProject()` | R/013838 `ops[create_project].detail`: `name` `spike-20261012-013838.prproj`, `path` `\\?\D:/...`, `is_active: true`; `ops[project_views]` lists that project as the one view (`host_info`'s `active_project` step is `null` in that run) | path carries the `\\?\` prefix, see Fact 1 | UXP adapter |
| P4 | List all open projects (for `activateProject`) | 🟢 | `ProjectUtils.getProjectViewIds`, `getProjectFromViewId` | R/013838 `ops[project_views]`: `count: 1`, the one view is the scratch project | only one project was open, so a multi-project listing is untested; the probe deliberately records nothing about other projects | UXP adapter |
| O1 | New project | 🟡 | `Project.createProject(path)` (path given with forward slashes) | R/014010 `ops[create_project]`: ok in 2 611 ms, file 5 324 bytes; R/013838: ok in **35 137 ms** (0.1.1 and 0.1.0 showed 1.97 - 4.7 s and 19.3 / 33.0 s). New projects start with every scratch disk set to `MyDocuments` (SD1) | works 4 of 4 times in 0.1.1 and 2 of 2 in 0.1.2, but the time is bimodal (2 - 5 s vs 19 - 35 s) and whether the **Scratch Disk Error** dialog of 0.1.1 still appeared in the 0.1.2 runs is not established (Yunus's note names only Project Modified) | partial: stays on the CEP compat op (`build_project` unattended) until a run with the dialogs observed turns it green; target is the UXP adapter with a 180 s timeout |
| SD1 | Read and set project scratch disks | 🟢 | `ProjectSettings.getScratchDiskSettings(project)`, `ScratchDiskSettings.setScratchDiskPath(type, ScratchDiskFolder.SAME_AS_PROJECT)`, `ProjectSettings.createSetScratchDiskSettingsAction` in a transaction | R/013838 `ops[scratch_disk]`: before, all six types (`CAPTURE`, `AUDIO_PREVIEW`, `VIDEO_PREVIEW`, `AUTO_SAVE`, `CCL_LIBRARIES`, `CAPSULE_MEDIA`) read `"MyDocuments"`; after, all six setters returned true, the transaction returned true and every path reads back `"SameAsProject"` | - | UXP adapter: set SAME_AS_PROJECT right after `createProject` |
| O2 | Open an existing project | 🟢 | `Project.open(path)` with **a native backslash path** (`D:\0 Work\...\spike-...prproj`), no options | R/013838 `ops[save_close_open]`: attempt 4 (backslash path, no options) ok in 3 051 ms. Attempts 1 (cleaned forward-slash path, no options), 2 (the raw `\\?\D:/...` path as Premiere reports it) and 3 (forward-slash path + the four suppression options, the 0.1.1 call) all failed with `Failed to open the project` (2 294 / 1 / 1 598 ms). 0.1.1: the forward-slash call failed 3 of 3. **Caveat: the results record the path string only for the failed attempts; attempt 4's string is not stored.** That it was a backslash path rests on the step label ("backslash path, no options") and on `path_before_json` of `save_as` (Premiere's path in backslash form after the reopen) | the 0.1.1 red was a **spike defect: wrong path form**. Open needs backslashes on Windows | UXP adapter; always pass `Project.open` a backslash path |
| O3 | Save | 🟢 | `project.save()` | R/013838 `steps[save (explicit)]`: ok in 3 621 ms, `bytes_before 5152`, `bytes_after 36763` (0.1.1: 1 319 - 7 659 ms, 31 KB) | the Project Modified dialog of this run was reported at about 22:39:17Z, before the save started (22:39:35.9Z), so it is **not** from `save()` (see "Dialogs") | UXP adapter |
| O4 | Close | 🟢 | `project.close(new CloseProjectOptions().setPromptIfDirty(false).setSaveWorkspace(false).setShowCancelButton(false))` after an explicit save | R/013838 `steps[close ...]`: `closed: true` in 1 024 ms (0.1.1: 65 - 152 ms) | - | UXP adapter |
| O5 | Save as | 🟢 | `project.saveAs(path)` | R/013838 `ops[save_as]`: ok in 193 ms, target `...spike-20261012-013838-copy.prproj`, 36 913 bytes, `project_object_now_points_to_copy: true` | the project object follows the copy | UXP adapter |
| D1 | Changes persist after save + close + reopen | 🟢 | the O2 reopen, then reads | R/013838 `steps[verify persisted]`: 1 sequence `EP02TEST_R02_RE_EDIT`, V1 name `WNC Undo Test` (set by the undo probe), V2 name `WNC Spike V2` (track_rename), 6 markers (the 5 earlier plus `WNC undo marker`) | - | UXP adapter |

### B. Import and sequence

| ID | Operation | Status | UXP API used | Evidence | Cause / condition | Decision |
|---|---|---|---|---|---|---|
| I1 | Import a still (PNG) | 🟢 | `project.importFiles([path], true)`, then find the item with `ClipProjectItem.cast(item).getMediaFilePath()` | R/013838 `ops[keyframes_motion_opacity_crop].steps[place_still_or_pick_clip]`: `source: "placed still"` (GFX_002.png) | - | UXP adapter |
| I2 | **Import the FCP7 XML as the base timeline** (adobe.md: "first thing to test") | 🟢 | `project.importFiles([xmlPath], true)`, poll `project.getSequences()`, `project.setActiveSequence(seq)` | R/013838 `ops[import_fcp7_xml]`: ok, `detail.import_ms` 4 180 (all figures are `detail.import_ms`: R/014010 633; 0.1.1 R/004145 345; cold R/004022 7 572); one new sequence `EP02TEST_R02_RE_EDIT`; **9 video tracks (V1: 11 clips, V2: 3, V3-V9: 0) and 8 audio tracks (A1: 11, A2: 11, A3-A6: 1 each, A7: 11, A8: 11)**; 1080x1920, end 30.0833 s; XML markers GFX_001..003 with their Arabic comments came through | - | **UXP adapter; the engine keeps writing the FCP7 XML for the base timeline** |
| S1 | Read sequence settings | 🟢 | `seq.getSettings()` then the getters | R/013838 `ops[sequence_settings].steps[read_all]`: preview codec `"Animation"`, preview file format `"QuickTime"`, composite in linear colour `true`, max bit depth `false`, max render quality `false`, editing mode `"Custom"`, frame rect and preview rect 1080x1920, PAR `"1:1"`, field type 0, frame rate 24, audio channel type 1, count 2 | - | UXP adapter |
| S2 | Set linear colour / max bit depth / max render quality | 🟢 | `setCompositeInLinearColor`, `setMaximumBitDepth`, `setMaxRenderQuality` + `seq.createSetSettingsAction(s)` in one transaction | R/013838 `steps[toggle_each_bool_and_back]`: each of the three flipped and restored, read-back correct both times | the engine's targets equal the imported defaults, so only the toggle proves settability | UXP adapter (replaces CEP `compositeLinearColor`, `maximumBitDepth`, `maximumRenderQuality`) |
| S3 | Set the preview codec to ProRes 422 LT | 🟢 | `s.setPreviewCodec("Apple ProRes 422 LT")` + `createSetSettingsAction` | R/013838 and R/014010 `steps[preview_codec: discover, round trip, try display names]`: `accepted_candidate: "Apple ProRes 422 LT"`, read back after the transaction; `Animation` -> `Apple ProRes 422 LT` -> restore `Animation` all read back. 0.1.1: `"apcs"` was ignored (read back `Animation`) | 0.1.1 red was a **spike defect: the setter takes the display name, not the FourCC**. Side effect: `setPreviewFileFormat("QuickTime")` alone changed the read codec to `Apple ProRes 422 LT`. The d.ts has no codec list; only this one name was confirmed | UXP adapter (replaces CEP `previewCodec: "apcs"`) |
| S4 | Other settings setters (frame rect, frame rate, audio sample rate, pixel aspect, field type) | 🟡 | `setPreviewFrameRect`, `setVideoFrameRect`, `setVideoFrameRate`, `setAudioSampleRate`, ... | only `setPreviewFrameRect(1080x1920)` ran (`steps[preview_frame_rect=video_frame_rect]` ok). **It set the rect to its current value, so it proves little** | never set to a *different* value; the engine gets frame size and rate from the XML anyway | not needed for 3.0; stays CEP-or-XML |
| S5 | Create a sequence with explicit settings (no XML) | ⚪ | `createSequence`, `createSequenceFromMedia`, `createSequenceWithPresetPath` | not probed (the engine uses the XML) | - | keep the XML |
| T1 | Place a still on a track at a time | 🟢 | `SequenceEditor.getEditor(seq).createOverwriteItemAction(item, time, videoTrackIndex, 0)` | R/013838 `steps[place_still_or_pick_clip]`: placed at 30.0833 s on video track index 8, ends 35.0833 s (default 5 s); the fresh still of the time-basis probe was placed the same way at 36.083 s on a new track | a placed still reports `in_point_s 3599.9583` (Fact 6) | UXP adapter |
| T2 | Set clip end / start / move / out point, rename, disable | 🟢 | `clip.createSetEndAction`, `createSetStartAction`, `createMoveAction(offset)`, `createSetOutPointAction`, `createSetNameAction`, `createSetDisabledAction` | R/013838 `ops[clip_edits_transitions_tracks]` on the placed still (start 30.083, end 35.083): end - 2 s -> 33.083; start + 0.5 s -> 30.583 (in-point moved with it, 3599.958 -> 3600.458); move +1 s -> 31.583 / 34.083; out - 0.5 s -> end 33.583 (out 3602.458); rename `GFX_002.png` -> `WNC placed still`; disabled true then false | `createMoveAction` takes an **offset** ("shifting by a number of seconds"), not a target time | UXP adapter |
| T2b | Set clip in-point | 🟡 | `clip.createSetInPointAction(time)` | R/013838 same op: the transaction returned true, but in-point read 3600.458 before and after | **spike defect**: the probe asked for `target.in_s + 0.5` using the in-point from before the earlier start edit, which equals the value it already had, so nothing could change | partial: stays CEP until re-measured (workaround: `createSetStartAction`, which also advances the in-point) |
| T3a | Add a video track | 🟢 | `createOverwriteItemAction(item, time, trackIndex = track count, 0)` (d.ts: "a new track will be created") | R/013838 `steps[add a video track by overwriting ...]`: `video_tracks_before 10`, `after 11`, `track_added: true`; the time-basis probe's fresh still created track index 9 the same way | video track only; audio track and track *type* not probed | UXP adapter (for extra graphic tracks) |
| T3b | Add audio tracks of a chosen type; audio mono pairs / channel mapping | 🔴 | none exists | static evidence, not a live probe: `premierepro` exposes 71 members (R/004145 `steps[ppro_members]`) and none is a channel-mapping API; the 26.5.0 d.ts has no `AudioChannelMapping` | API gap (as predicted in adobe.md) | **the base FCP7 XML supplies all tracks and the pairs** (verified in I2: 9 V + 8 A created by the import); any channel-mapping change goes to the CEP compat op |
| T4 | Remove a clip | 🟢 | `TrackItemSelection` + `createRemoveItemsAction` | R/013838 `steps[remove the clip placed on the new track ...]`: `clips_before 1`, `clips_after 0` | - | UXP adapter |

### C. Keyframes and effects

| ID | Operation | Status | UXP API used | Evidence | Cause / condition | Decision |
|---|---|---|---|---|---|---|
| K0 | Components by match name | 🟢 | `clip.getComponentChain()`, `getComponentAtIndex`, `getMatchName()`, `getDisplayName()`, `getParam(i).displayName` | R/013838 `steps[dump_component_chain]` for the placed still: index 0 `AE.ADBE Opacity` (params Opacity, Blend Mode, Blend Mode), index 1 `AE.ADBE Motion` (Position, Scale, Scale Width, `" "`, Rotation, Anchor Point, Anti-flicker Filter, **Crop Left, Crop Top, Crop Right, Crop Bottom**); every param `keyframes: true` (the probe's field for `areKeyframesSupported()`) | **Opacity comes before Motion**, so never index by position; params may share names or be blank | UXP adapter finds components by match name and params by display name |
| K1 | Motion Scale keyframes | 🟢 | `param.createSetTimeVaryingAction(true)`, `param.createKeyframe(n)`, `kf.position = TickTime`, `createAddKeyframeAction` | R/013838 `steps[motion.scale 100->110]`: times `[0, 1]`, value 100 / 110, mid 105 | times are **media-time**: key at `clip.getInPoint() + local seconds` (K7); create + read-back only: the probe's keys at 0 / 1 s fall outside the media window, per K7 | UXP adapter |
| K2 | Motion Rotation keyframes | 🟢 | same | `steps[motion.rotation 0->5]`: `[0, 1]`, 0 / 5, mid 2.5 | same time rule (K7); create + read-back only: the probe's keys at 0 / 1 s fall outside the media window, per K7 | UXP adapter |
| K3 | Opacity keyframes (fade) | 🟢 | same, on `AE.ADBE Opacity` | `steps[opacity 100->0]`: `[0, 1]`, 100 / 0, mid 50; **the rendered fade is visible in the exported frames** (K7, a different probe with in-point-based keys) | same time rule (K7); create + read-back only: the probe's keys at 0 / 1 s fall outside the media window, per K7 | UXP adapter |
| K4 | Motion Position keyframes (the `slide` animation) | 🟢 | `param.createKeyframe(new ppro.PointF(x, y))`; read with `getStartValue()` / `getValueAtTime()` which return **arrays** | R/013838 `steps[position: ...]`: start value `{value: [0.5, 0.5]}` (normalised units, frame 1080x1920), `getValueAtTime` also `{value: [0.5, 0.5]}`; `createKeyframe` accepted `new PointF(x, y)`, `PointF(x, y)` without `new`, `new PointF()` then `.x/.y` and a pixel-valued PointF (540, 960); it rejected a plain `{x, y}`, an array `[x, y]` and the start-value object (`Illegal Parameter type`); two keys added, read back `[0, 1]` with value 1 s = `[0.55, 0.5]` | the 0.1.1 red was a **spike defect**: it built the keyframe from `start.x`/`start.y` of an *array*, so `x`/`y` were undefined; create + read-back only: the probe's keys at 0 / 1 s fall outside the media window, per K7 | UXP adapter: read an array, write a `PointF` |
| K5 | Crop (the `bar_sweep` animation keys Motion "Crop Left") | 🟢 | Motion params `Crop Left / Top / Right / Bottom`; the crop effect `AE.ADBE AECrop` | R/013838: `steps[crop: Motion Crop Left 0->100]` times `[0, 1]`, values 0 / 100, mid 50; `Crop Right 0->10` ok; `steps[crop effect AE.ADBE AECrop ...]`: chain 2 -> 3, params `Left, Top, Right, Bottom, " ", Edge Feather`, `Left 0->10` keyed and read back | 0.1.1 red was a **spike defect** (the regex `/ADBE Crop/` does not match `AE.ADBE AECrop`); create + read-back only: the probe's keys at 0 / 1 s fall outside the media window, per K7 | UXP adapter via Motion `Crop Left` (as the CEP engine does) |
| K6 | Keyframe interpolation | 🟢 | `param.createSetInterpolationAtKeyframeAction(time, ppro.Keyframe.INTERPOLATION_MODE_BEZIER)`, `getKeyframePtr(time).getTemporalInterpolationMode()` | `steps[motion.scale interpolation -> bezier at 1s]`: mode read back 5, wanted 5 | create + read-back only: the probe's keys at 0 / 1 s fall outside the media window, per K7 | UXP adapter |
| K7 | **Keyframe time basis** | 🟢 | `kf.position = TickTime.createWithSeconds(t)` | **Decided from rendered frames: keyframe times are media time (clip in-point + seconds into the clip).** R/013838 `ops[keyframe_time_basis]` on a fresh still placed on its own track (in-point 3599.958 s, start 36.083 s, windows pairwise disjoint), Opacity 100 -> 0 over 1 s, one basis at a time, frames exported at sequence 36.333 / 36.583 / 36.833 s (the 25 / 50 / 75 % points of the first second); I looked at them: **B (in-point + 0 and +1 s) shows the blue Arabic bar fading, about 75 % opaque at 0.25, clearly fainter at 0.75**; **A (0 and 1 s) and C (36.083 and 37.083 s) show no bar at all** and their frames are byte-identical (same checksums) to each other; the baseline (no keys) shows the bar fully opaque. R/014010 repeats it (same checksums). `getValueAtTime` and the read-back times mirror whatever was keyed, so they cannot decide | the second variant (an XML clip moved past the sequence end) was **not decisive**: all 12 of its frames are byte-identical (even across the 3 times and the baseline) and show a still image of the speaker, so the keyed clip was not what was rendered there; the decision rests on the fresh-still variant | UXP adapter keys at `clip.getInPoint() + t` (this is the basis the CEP engine already uses, `base = it.inPoint.seconds`); for a still the in-point is about 3600 s. Re-confirm on an XML clip in a later run |
| K8 | Set a static param value (no keyframes) | 🟢 | `param.createKeyframe(v)` + `param.createSetValueAction(kf)` | R/013838 `ops[effects_by_match_name]`: Blurriness 90 read back `{value: 90}` and start value 90; Sharpen Amount 50 read back 50; Noise Intensity 30 read back 30 | - | UXP adapter |
| E1 | List all video filters | 🟢 | `VideoFilterFactory.getMatchNames()`, `getDisplayNames()` | R/013838 `steps[list_filters]`: 108 and 108 (parallel arrays), file `filters-20261012-013838.json` (4 804 bytes, identical in all six runs that wrote it) | - | UXP adapter reads this list at start-up |
| E2 | Add Sharpen | 🟢 | `VideoFilterFactory.createComponent("AE.ADBE Sharpen")` + `chain.createAppendComponentAction(comp)` | `steps[sharpen ...]`: chain 4 -> 5, param `Sharpen Amount` set 50 and read back | - | UXP adapter (replaces QE `addVideoEffect("Sharpen")`) |
| E3 | Add Noise (grain) | 🟢 | `createComponent("AE.ADBE_Noise_FX")` | `steps[noise ...]`: chain 5 -> 6, params include Seed, **Intensity** (set 30, read back 30), Shadows, Midtones, Highlights, Uniform Intensity, Saturation, Blend Mode, Master, Preserve Alpha (plus junk entries) | match name has an underscore; the legacy one is `AE.ADBE Noise2` | UXP adapter |
| E4 | Add Gaussian Blur (Blurriness 90, Repeat Edge Pixels) | 🟡 | `createComponent("AE.ADBE Gaussian Blur 2")` + append | R/013838 and R/014010 `steps[gaussian_blur_legacy ...]`: chain 3 -> 4, display `Gaussian Blur (Legacy)`, params `Blurriness`, `Blur Dimensions`, `" "` (blank); **Blurriness 90 set and read back**; the only failure is the lookup of "Repeat Edge Pixels" by name (`no param matching /repeat edge pixels/i`), which is why `effects_by_match_name` is the one failing probe. The new effect `AE.Impact_Blur_FX` (display "Gaussian Blur") was appended separately: params Angle, Amount, Thickness, Uniform Blur, Chromatic Aberration, Edge Behavior | the third param has a blank name; it is probably Repeat Edge Pixels (third param of AE's Gaussian Blur) but was not set and read back | partial: stays on CEP until the blank-name param is verified; target is the UXP adapter with `AE.ADBE Gaussian Blur 2`, Blurriness by name, edge pixels by index 2 |
| E5 | Add Lumetri | 🟢 | `createComponent("AE.ADBE Lumetri")` + append | R/013838 `steps[lumetri ...]`: chain 6 -> 7, display `Lumetri Color`, 130 params listed (Basic Correction, Temperature, Tint, Exposure, Contrast, Look, Curves, ...); no value was set | creation and append only | UXP adapter |
| V1 | Video transitions | 🟢 | `TransitionFactory.createVideoTransition`, `createAddVideoTransitionAction` | R/013838 `steps[video transition ...]`: 118 transitions listed (e.g. `ADBE Additive Dissolve`, `ADBE Cross Zoom`), used `AE.ADBE Cross Dissolve New`, transition items on the track 0 -> 1, transaction true | the rendered result was not looked at | UXP adapter |

### D. Captions, MOGRT, markers, names, frames, export, undo, network

| ID | Operation | Status | UXP API used | Evidence | Cause / condition | Decision |
|---|---|---|---|---|---|---|
| C1 | Native caption track from SRT (`createCaptionTrack`) | 🔴 | none exists | static evidence, not live-probed: the 26.5.0 d.ts has no `createCaptionTrack` (0 hits); `ppro` has a `CaptionTrack` member but no create call | API gap (as in adobe.md) | animated caption stills stay the default; CEP compat `create_caption_track` if ever requested; SRT for manual import |
| M1 | MOGRT insert and text | ⚪ | `SequenceEditor.insertMogrtFromPath` is in the d.ts | not probed; text parameters are not available before 27.0 (`MogrtText`) per adobe.md | - | not blocking: WhyNot Cut uses PNG stills |
| N1 | Rename video and audio tracks | 🟢 | `track.createSetNameAction(name)` | R/013838 `ops[track_rename]`: V2 `Video 2` -> `WNC Spike V2`, A2 `Audio 2` -> `WNC Spike A2`, both read back; the names survive save + reopen (D1) | - | UXP adapter |
| MK1 | Markers: read, add with name / comment / duration, set colour | 🟢 | `Markers.getMarkers(seq)`, `createAddMarkerAction(name, type, start, duration, comments)`, `createSetColorByIndexAction` | R/013838 `ops[markers]`: 3 XML markers read (names, type `Comment`, Arabic comments); 2 added (starts 2 and 3 s, durations 0 and 1 s); colour index 1 (RED) read back; the markers survive save + reopen (D1) | - | UXP adapter (replaces `seq.markers.createMarker`) |
| Q1 | Single-frame export (QE `exportFramePNG` today) | 🟢 | `Exporter.exportSequenceFrame(seq, TickTime, "<bare file name>.png", "<native backslash folder>\\", 1080, 1920)` | R/013838 `ops[export_frame]`: winner `work:name + dir\ (backslashes):png`: `returned: true`, call 49 ms, file `exp_20261012-013838_f1_4.png` found 54 ms after the call, PNG 1080x1920 (1 610 035 bytes final); a second frame at 12.033 s with the same form returned true (R/014010 the same). **I viewed the exported PNGs** (the programme frames of the time-basis probe: speaker video with the blue Arabic bar). The forms with forward-slash folders returned `false` without an exception, **including the d.ts example form** (full path + `dir/`), the no-trailing-slash form and the bare-name form with `dir/` | **the file shows up before it is complete**: the first poll saw 114 967 bytes of what ended as 1 610 035 bytes, so wait until the size stops changing. Trying the wrong forms first costs about 13 s (1.5 s polls, plus 10 s for the d.ts form), so use the winning form directly | UXP adapter (replaces QE `exportFramePNG`; no timecode string needed). 0.1.1 red was a **spike defect: forward-slash paths** |
| X1 | Export / render through Premiere's encoder or AME | ⚪ | `EncoderManager.exportSequence` | `ops[encoder_export]`: off by default (`"encoder_export": true` in config.json would run it), not run | - | later; Q1 is green, so it is no longer the frame-export fallback |
| R1 | Timeline read-back (tracks, clips, start / end / in / out, settings, markers, chain) | 🟢 | `seq.getVideoTrackCount/getVideoTrack`, `track.getTrackItems(CLIP, false)`, `clip.getStartTime/getEndTime/getInPoint`, `seq.getFrameSize/getTimebase/getEndTime`, `getSettings` | I2, S1, K0, T2 (`before` / `after` windows), MK1 | the track-item to project-item (source path) link was not probed | UXP adapter |
| U1 | Mutation pattern (every write undoable in one step) | 🟢 | `project.lockedAccess(() => project.executeTransaction(ca => ca.addAction(a), label))` | every write in R/013838 returned `true` through this pattern | - | UXP adapter |
| U2 | Transaction label shows as a named undo step | 🟢 | `executeTransaction(build, "WhyNot Cut build")` | **History panel screenshots.** 0.1.2 (`docs/adobe/evidence/2026-10-12-premiere-run3-panel-history.png`, project `spike-20261012-014010` kept open): the History panel lists per-probe entries `WNC spike: clip_edits_transitions...` (x3), `WNC spike: track_rename` (x2), `WNC spike: markers` (x2) and, **last, `WhyNot Cut build`**; footer "32 Undos" (it reads the same in both screenshots, so it may be Premiere's history cap; do not read it as a step count). 0.1.1 (`docs/adobe/evidence/2026-10-12-history-undo-label.png`, kept-open project, per the controller's reading of Yunus's screenshot about 8 entries labelled "WhyNot Cut build"): the footer reads "32 Undos" too, and after one Ctrl+Z the last "WhyNot Cut build" entry is greyed out, i.e. exactly one step was undone. The Edit menu only shows "Undo", so the label is visible only in Window > History | **several transactions give several history steps**: wrap a whole build in ONE `executeTransaction` if the editor should undo it in one step | UXP adapter: one `lockedAccess` + one `executeTransaction("WhyNot Cut build")` per build |
| U3 | One Ctrl+Z reverts all three mutations of the `undo_transaction` probe (V1 name + A1 name + marker) | ⚪ | - | R/013838 and R/014010 `steps[one_transaction_three_actions]` record `state_before` (V1 `Video 1`, A1 `Audio 1`, no `WNC undo marker`) and `state_after` (V1 `WNC Undo Test`, A1 `WNC Undo Test A1`, `WNC undo marker` present). The 0.1.2 screenshot was taken **before** pressing Ctrl+Z (the last entry is not greyed), so the revert is still unchecked | - | press Ctrl+Z once on the kept-open project and compare against `state_before` |
| W1 | WebSocket client to the engine daemon (`ws://127.0.0.1:<port>/session`) | 🔴 | `new WebSocket(url)` | R/211920 `ops[ws_loopback]` (3 steps): `steps[engine.json ...]` read `~/.whynot-cut/bridge/engine.json` (keys port, token, pid, version, protocol, pid_created, started_at; port 53672, pid 83576, version `3.0.0`, protocol 4, token 64 characters, shape ok); `steps[connect ...]` failed after 0 ms with **"Permission denied to the url ws://127.0.0.1:53672/session. Manifest entry not found."** | **UXP permission rule, not a daemon problem**: the manifest `network.domains` entries `ws://127.0.0.1` and `http://127.0.0.1` do not match a URL that has a port, so the request never left Premiere | **`network.domains: "all"` in the product and spike manifests** (ruling, spec fallback rule; another implementer is changing it); re-measure after that |
| W2 | HTTP `fetch` to the daemon (`http://127.0.0.1:<port>/status`, bearer token) | 🔴 | `fetch(url, {headers})` | R/211920 `steps[http: fetch /status ...]`: refused in 12 ms with **"Permission denied to the url http://127.0.0.1:53672/status. Manifest entry not found."** | same cause as W1 | same fix as W1 |
| W3 | Origin header and keepalive of the daemon connection | ⚪ | - | **Unmeasured.** The request never left Premiere, so the daemon has no `origin` row in `~/.whynot-cut/logs/serve-audit.log` for the run and there was no connection to keep alive | blocked by W1 / W2 | re-measure with the `"all"` manifest; see "Origin header" |
| H1 | Open a file in the Source Monitor | 🟡 | `SourceMonitor.openFilePath(<native backslash path>)` | R/211920 `ops[host_calls]`: `steps[SourceMonitor.openFilePath ...]` returned `true` in 44 ms for a scratch copy of the preview mp4 (2 485 388 bytes); **but** project items stayed 6 -> 6, `getProjectItem` gave no name and `getPosition` read `-400000` s straight after, so the effect on the monitor was not confirmed; `closeClip` returned `true`; the later screenshot shows "Source: (no clips)" | the call accepts a native path and returns true; whether the clip really loaded is unverified | partial: stays as is (panel use only) until a run reads the monitor state or Yunus confirms it on screen |
| H2 | Move the playhead | 🟢 | `Sequence.setPlayerPosition(TickTime)`, read with `Sequence.getPlayerPosition()` | R/211920 `steps[Sequence.setPlayerPosition (TickTime) read back]`: scratch sequence end 41.0833 s; set 10.271 / 20.542 / 30.813 s (25 / 50 / 75 %): each returned `true` and read back **exactly** (delta 0); `steps[setPlayerPosition beyond the end / negative]`: **beyond the end (51.083 s) is accepted and read back as 51.083**; **a negative time (-1) returned `true` but is ignored** (the position stayed at 51.083; that call took 415 ms) | clamp negatives and the end yourself | UXP adapter (`set_player_position`) |
| H3 | Open a folder or file with the system | 🟡 | `uxp.shell.openPath(path, developerText)` with native backslash paths | R/211920 `steps[shell.openPath ...]`: the three calls completed and returned the empty string `""`: folder `work_dir` in **4 650 ms**, the mp4 in **1 808 ms**, the folder again in **32 102 ms**; all three carry `consent_dialog_suspected: true` (the probe infers it from the time; it cannot see a dialog) and Premiere's own text "WhyNot Cut spike 0.1.3 is measuring whether it may open this location on your computer."; the controller reports that the folder and the mp4 did open (relayed, not in the file) | **a consent dialog is probably shown**; the third call took 32 s, so the consent was apparently **not remembered** (or the person was slow: the results do not say whether anyone answered) | partial: the adapter may use it only as a user-visible, long-timeout action (about 2 - 35 s); the product manifest grants `launchProcess` |

## Counts

55 rows: **39 green, 5 red, 6 partial, 5 pending** (spike 0.1.3). (After spike 0.1.2 the matrix had 50 rows: 38 / 3 / 4 / 5; after 0.1.1, 46 rows: 21 / 7 / 6 / 12.)

- Green (39): H2, P1, P3, P4, SD1, O2, O3, O4, O5, D1, I1, I2, S1, S2, S3, T1, T2, T3a, T4, K0, K1, K2, K3, K4, K5, K6, K7, K8, E1, E2, E3, E5, V1, N1, MK1, Q1, R1, U1, U2.
- Red (5): P2 (Application.version undefined, workaround green), T3b (audio channel mapping / audio track types, API gap, static evidence), C1 (native caption track, API gap, static evidence), **W1 and W2 (UXP refused the WebSocket and the fetch to `127.0.0.1:<port>`: manifest entry not found)**.
- Partial (6): O1 (createProject: dialog and cold-start time unresolved), S4 (other setters never set to a different value), T2b (in-point probe could not change anything), E4 (Gaussian Blur: Repeat Edge Pixels param), **H1 (SourceMonitor.openFilePath returned true, effect unverified), H3 (shell.openPath: consent dialog suspected)**.
- Pending (5): S5, M1, X1, U3, W3 (Origin header and keepalive).

Changes in 0.1.3: W1 went from pending to **red** (a permission refusal), W2 and W3 were split out of it, and H1 - H3 are new rows (the host calls the panel uses, never measured before). Nothing that was green in 0.1.2 changed: the time-basis and frame-export PNGs, the reopen with a backslash path, the effects and every settings value repeat.

Rows that turned from red or partial in 0.1.1 to green in 0.1.2 and why: O2 (backslash path), S3 (display name), K4 (PointF built from an array), K5 (the right param / match name), K7 (frames rendered), Q1 (backslash folder), K8, E5, O3, O4, O5, D1, P4, V1, T2, T3a, T4, SD1 (probes that did not exist in 0.1.1).

## Measured facts the adapter must encode

1. **`project.path` carries the Windows extended-length prefix and mixed slashes**: the string is `\\?\D:/0 Work/.../spike-...prproj` (raw JSON `"\\\\?\\D:/..."`). Compare paths only after stripping the prefix and normalising (`\\?\UNC\` -> `//`). **Path forms by call**: `createProject`, `saveAs`, `importFiles`, `fs` and the plugin's own paths work with forward slashes; **`Project.open` needs native backslashes** (`D:\...`; forward-slash and the raw `\\?\` form fail with "Failed to open the project"); **`Exporter.exportSequenceFrame` needs a bare file name plus a native backslash folder with a trailing backslash** (forward-slash folders return `false`).
2. **Timing**: `createProject` 2.2 - 4.7 s normally, 19.3 s, 33.0 s and 35.1 s on cold calls (modal not established); first `importFiles(xml)` 4 - 7.6 s cold, 0.2 - 0.6 s warm; `project.save()` 1.3 - 7.7 s (3.6 s in 0.1.2); `close` 0.07 - 1.0 s; `Project.open` 3.1 s; `saveAs` 0.2 s; a frame export call about 50 ms plus the time to finish writing; most other calls under 10 ms, effect appends up to about 100 ms (Noise 99 ms, Impact Blur 61 ms). Use 180 s timeouts for create, import, save, open.
3. **Settings** (UXP getters, values after the XML import): `getPreviewCodec` "Animation", `getPreviewFileFormat` "QuickTime", `getCompositeInLinearColor` true, `getMaximumBitDepth` false, `getMaxRenderQuality` false, `getEditingMode` "Custom", frame and preview rect 1080x1920, PAR "1:1", field type 0, frame rate 24, audio channel type 1, count 2. **Settable and verified**: linear colour, max bit depth, max render quality, and the **preview codec by display name `"Apple ProRes 422 LT"`**. CEP name map: `compositeLinearColor` -> `CompositeInLinearColor`, `maximumRenderQuality` -> `MaxRenderQuality`, `maximumBitDepth` -> `MaximumBitDepth`, `previewCodec` -> `PreviewCodec` (value: display name, not `apcs`). Writes go through `seq.createSetSettingsAction(settings)` in a transaction; read back with a *fresh* `getSettings()`. `setPreviewFileFormat("QuickTime")` alone resets the codec to `Apple ProRes 422 LT`.
4. **Match names (verified live)**: `AE.ADBE Opacity`, `AE.ADBE Motion` (order on a placed still: Opacity first, Motion second), `AE.ADBE Sharpen` (param "Sharpen Amount"), `AE.ADBE_Noise_FX` (param "Intensity"; legacy `AE.ADBE Noise2`), `AE.ADBE Gaussian Blur 2` (display "Gaussian Blur (Legacy)": Blurriness, Blur Dimensions, blank), `AE.ADBE AECrop` (display "Crop": Left, Top, Right, Bottom, blank, Edge Feather), `AE.ADBE Lumetri` ("Lumetri Color"), `AE.Impact_Blur_FX` (display "Gaussian Blur": Angle, Amount, Thickness, Uniform Blur, Chromatic Aberration, Edge Behavior). Transition match name used: `AE.ADBE Cross Dissolve New`. **Display names are not unique across generations** ("Gaussian Blur" -> `AE.Impact_Blur_FX`; "Noise" -> `AE.ADBE_Noise_FX`; "Mosaic" vs "Mosaic (Legacy)"), so the adapter resolves effects by match name only.
5. **The 108 filter list**: `whynot-test/_uxp-spike/filters-20261012-013838.json` (4 804 bytes; keys `matchNames`, `displayNames`, parallel arrays; identical in every run that wrote it). Almost all are `AE.` names; six are `PR.ADBE ...` (Color Replace, Gamma Correction, Extract, Color Pass, Lens Distortion, Levels). Copy it to a fixture when the adapter tests are written.
6. **Keyframe time basis = media time**: key at `clip.getInPoint().seconds + seconds_into_clip` (K7, decided from frames). A placed still reports `getInPoint() = 3599.9583 s` (3600 s minus one 24 fps frame), so a still's keys are at about 3600 s; a clip from the XML has its own in-point (23.83 s for the one probed). `createSetStartAction` moves the in-point with the start. Time is `TickTime` (`ppro.TickTime.createWithSeconds(s)`, `.seconds` to read). Keys outside the clip's media window are accepted and stored verbatim but hold their end value.
7. **Parameter values**: scalar params read and write numbers (`{value: n}` from `getValueAtTime` / `getStartValue`). **Position is normalised (0.5, 0.5 = centre) and is read as an array `[x, y]` but must be written with `new ppro.PointF(x, y)`**; a plain object, an array or the returned start-value object is rejected with "Illegal Parameter type". `Scale` interpolates linearly by default; `ppro.Keyframe.INTERPOLATION_MODE_BEZIER` = 5.
8. **Effects append to the end of the chain** (`createAppendComponentAction`); the chain grows by exactly one. Effects expose junk params ("Error occurred", "Controls", blank names, `_ Overlay ...`, `_ Sequence Width`); find the useful param by display name; a few real params have **blank names** (Gaussian Blur (Legacy) third param) and need an index.
9. **XML import**: `importFiles([xml], true)` returns `true` and the sequence is found on the first poll; empty tracks are kept (9 V, 8 A); markers with comments (Arabic included) survive; `setActiveSequence` works.
10. **Markers**: `getMarkers()` returns them sorted by start; type string `"Comment"`; `ppro.Constants.MarkerColor.RED` = 1.
11. **Runtime**: `Application.version` is undefined (use `uxp.host.version`); `uxp.versions.uxp` = `uxp-9.3.0-local`; `navigator.clipboard` throws without the manifest `clipboard` permission; no `TextDecoder`; `require("premierepro")` exposes 71 members, among them `Exporter`, `EncoderManager`, `MediaManager`, `ProjectConverter`, `ScratchDiskSettings`, `ProjectSettings`, `Transcript`, `TransitionFactory`, `CaptionTrack`; **no QE member**, no `AudioChannelMapping`; no undo-history API is exposed (`history_step_count: "not exposed by the API"`).
12. **New projects**: scratch disks default to `MyDocuments` for all six folder types; set them to `SameAsProject` (SD1). A project written by `saveAs` becomes the open project.
13. **Frame export**: the PNG file appears before it is fully written; poll the size until stable.
14. **Install**: UPIA `/install` of the `.ccx` is enough (no Developer Mode, no PlayerDebugMode, no UDT); one Premiere restart; listed as "Enabled WhyNot Cut Spike 0.1.1" (0.1.2 replaces it).
15. **Network permission**: a UXP manifest `network.domains` entry such as `ws://127.0.0.1` or `http://127.0.0.1` does **not** cover `127.0.0.1:<port>`; both `new WebSocket(...)` and `fetch(...)` throw "Permission denied to the url ... Manifest entry not found." before anything is sent (R/211920). Ruling: `"all"` for the product and the spike. A refused request leaves nothing in the daemon's audit log.
16. **Host calls**: `Sequence.setPlayerPosition(TickTime)` reads back exactly (also past the end of the sequence; negative times are ignored); `SourceMonitor.openFilePath(<native backslash path>)` returns `true`, but `getPosition()` then reads `-400000` s and `getProjectItem()` has no name (a sentinel, not a time); `uxp.shell.openPath` returns `""` and is slow (1.8 - 32 s per call, consent dialog suspected, not remembered).
17. **Failed starts**: twice (runs `204411`, `204511`) `createProject` returned nothing, or `importFiles(xml)` returned `true` without a new sequence; the spike refused to go on. Treat both as retriable failures.

## UXP adapter checklist (contract <-> UXP differences)

The v4 contract (`whynot-cut/engine/reel/contract/`) is the CEP-shaped wire form; the UXP adapter converts at its edge.
Each line is a difference the adapter owns, with where the contract says it.

- **Preview codec: FourCC on the wire, display name in UXP** (final review C1). `settings.previewCodec` and
  `settings_after.previewCodec` carry the FourCC (`"apcs"`; the engine check is `lib/ppro_build.py:249`). UXP's setter
  and getter use display names. The adapter owns the table (measured: `apcs` <-> `"Apple ProRes 422 LT"`, fact 3). A
  codec it does not know passes through as the display name on read-back, so the engine check fails correctly instead
  of the adapter guessing.
- **`exportSequenceFrame`** (C4; facts 1 and 13): a **bare file name** plus a **backslash folder with a trailing
  backslash**; a `false` return is not a throw (map it to the `{t, error}` frame form; `called` means "the export call
  reported success"); the PNG appears before it is fully written, so wait for a stable size. UXP takes a `TickTime`, so
  the frame entry has no `tc` (optional in the contract).
- **Strip `\\?\` from every path Premiere reports** (C3, U1; fact 1): `project.path`, sequence and clip media paths and
  everything else in a readback is a native OS path (adapters strip the Windows long-path prefix; `\\?\UNC\` becomes
  `\`). Going the other way, `Project.open` and `exportSequenceFrame` need native backslash paths; the panel host
  (`premiere-uxp/src/uxp-host.ts` `nativePath`) does the same for `SourceMonitor.openFilePath` and `shell.openPath`.
- **`Application.version` is empty**: ping and status take the version from `uxp.host.version` (C5; fact 11). UXP has no
  source for a build number, so `build` is optional in the Premiere ping.
- **Keyframe times are media time** (K7): key at `clip.getInPoint().seconds + seconds_into_clip`, not at the sequence
  time. A placed still reports an in-point near 3600 s.
- **One `executeTransaction` per build** (U1/U2): `project.lockedAccess(() => project.executeTransaction(build, "WhyNot
  Cut build"))`, so the whole build is one undo step with one label. Reads and the playhead stay outside it.
- **Host calls, measured in 0.1.3** (rows H1 - H3): `Sequence.setPlayerPosition` is green (exact read-back, negatives
  ignored, beyond the end accepted); `SourceMonitor.openFilePath` returns `true` but its effect is unverified (partial);
  `shell.openPath` completes with `""` but takes 1.8 - 32 s and a consent dialog is suspected on every call (partial), so the
  host calls it asynchronously with a long timeout.
- **Network permission** (W1, W2): the product and spike manifests must use `network.domains: "all"`. The entries
  `ws://127.0.0.1` / `http://127.0.0.1` do not match a URL with a port, so UXP refused the WebSocket and the `fetch` to
  `127.0.0.1:<port>` ("Manifest entry not found") before they left Premiere. Until that manifest change lands and is
  re-measured, the panel shows its "blocked" diagnosis (see "Product panel").
- **The product manifest now grants `clipboard: readAndWrite` and `launchProcess`** (owner decision, 2026-10-12): `launchProcess {schemes: ["file"], extensions: [".mp4", ".mov", ".prproj", ""]}` (the `""` is what Adobe's external-process recipe says allows folders; dotted vs undotted extensions is documented inconsistently). The panel host tries `navigator.clipboard.writeText` / `shell.openPath` first ("Copied." / "Opened.") and falls back to the copyable box. `openPath` behaviour (consent dialog, folder via `""`, dot form of the extensions, whether `file` is needed in `schemes`) is unmeasured -> spike 0.1.3.
- **`set_player_position` needs `sequence_name`, but `PanelHost.setPlayerPosition(t_s)` cannot pass it yet**: the host
  moves the playhead of the active sequence. T6.5 widens the host method to take the sequence name.
- **Failures are `ok:false` with an `error`** (C6): the result envelope is one shape per outcome (`ok:true` has a
  `readback` and no `error`; `ok:false` has an `error`); the UXP adapter never answers `ok:true` with a lone error.

## Dialogs (modal dialogs block automation)

What is known. Both dialogs appeared during the 0.1.1 runs; **the step that raised them was not logged**. Yunus reports
answering **Yes** (Scratch Disk Error) and **OK** (Project Modified); in the 0.1.1 runs the reopen failed (all three).
For the 0.1.2 run `013838` the only relayed dialog is a **Project Modified** one, answered OK, seen **at about 22:39:17Z**
(1-second resolution). In the step log that second holds the end of `sequence_settings` (22:39:17.922Z, which includes its
`createSetSettingsAction` transactions) and the start of `export_frame` (prepare began 22:39:17.933Z). Nothing relayed says
whether Scratch Disk Error appeared in the 0.1.2 runs.
For the 0.1.3 run `211920` Yunus reported **no dialog times** (none relayed), so nothing new is attributed. Every step carries
its `at` stamp (e.g. `sequence_settings` 18:19:36.101 - .118Z, `export_frame` prepare 18:19:36.127Z, 333 ms; save 2 634 ms,
close 396 ms, open attempts 1 376 / 2 / 755 / 957 ms) and none shows a stall, which fits a run without a modal wait.

| Dialog | Text (relayed from Yunus's screenshots) | What the 0.1.2 data shows | Hypothesis (not measured) |
|---|---|---|---|
| Project Modified | "The project file has been modified since last save. Do you wish to continue?" (OK / Cancel) | **Not from `project.save()`**: the dialog was seen at about 22:39:17Z, but `save` started at 22:39:35.9Z (the earlier hypothesis that the 1.3 - 7.7 s saves of 0.1.1 hid it is not supported). It landed **between the end of `sequence_settings` (its settings transactions) and the first calls of `export_frame`** ("prepare: activate sequence, size, media state": `openSequence`, `setActiveSequence`, `isOffline` reads, 1 315 ms; 695 ms in run 014010); **these are indistinguishable at 1 s resolution**. No step shows a stall (`export_frame` took 14 895 ms in 013838 and 14 047 ms in 014010; its 13 s of forward-slash attempts is the same in both) | the settings edits (`createSetSettingsAction`) leave the project dirty and a following call (`openSequence` / `setActiveSequence` / the export) checks the file on disk; to confirm, stamp every call in `sequence_settings` and `export_frame` |
| Scratch Disk Error | "The scratch disks are write protected or unavailable. To open this project, the scratch disks will be set to your My Documents folder." (Yes / No) | New projects start with all six scratch types on `MyDocuments` (SD1) and were set to `SameAsProject` right after creation in 0.1.2. Whether the dialog still appeared in the 0.1.2 runs is not established (Yunus's note names only Project Modified). The reopen now works with a backslash path | the dialog was tied to the `MyDocuments` defaults of a project made by `createProject` and to the `Project.open` call; the 0.1.2 order (scratch set before save / open) may have avoided it. Needs a run where Yunus notes every dialog with its time |

Consequence: a modal appeared during a settings / export step, so until it is attributed to a call and avoided, `build_project` through UXP cannot be
assumed unattended. The daemon must treat any project-level call as possibly blocked by a modal (long timeouts, a dialog
alert to the user, and the CEP compat op as the fallback). Next run: a `Date.now()` stamp before and after each call
inside `sequence_settings` (and its transaction) and `export_frame`'s `prepare` step, and Yunus noting each dialog with the clock time.

## Spike 0.1.6 live run `024944` (2026-10-13, full mode; Addendum C2.7 probes)

The panel and spike were installed with `npm run dev-install`. It removes by name, installs, then verifies the build:
the panel is "WhyNot Cut (dev)" 3.0.0, build 20261012T234905Z; the spike is "WhyNot Cut Spike" 0.1.6. UPIA accepted
both the explicit `network.domains` list and the `whynotcut` `launchProcess` scheme.

The evidence is in `docs/adobe/evidence/spike-016/`: the results, lifecycle and run-done files, and two dialog captures.
The results files contain no token; this was checked against the live `engine.json`.

| Probe | Measured | Consequence |
|---|---|---|
| Loopback `network.domains` | `ws://localhost:*` and `http://localhost:*` are **allowed**. The connections opened, and `/status` answered 401 without a token. `ws://127.0.0.1:*` and `http://127.0.0.1:*` are **denied** ("Manifest entry not found"). Each localhost connect took about 2.0 s, against 3 ms for a denied one: Windows resolves `localhost` to `::1` first, and the daemon binds only 127.0.0.1 | The product can drop `"all"`. Use `ws://localhost:*` + `http://localhost:*`; DaemonSource connects to `localhost`; the daemon also binds `::1` (otherwise every connect pays the ~2 s fallback). This closes the open security item from the plan session |
| `shell.openExternal("whynotcut://engine/start")` | UXP shows a modal **"Request For Permission"**: "The plugin WhyNot Cut Spike wants to open: whynotcut://engine/start", followed by the manifest's developer text (`consent-whynotcut-link.png`). Dismissed with Escape → rejected "User denied." after 177 s (the probe was blocked behind it) | The "Start engine" button through `whynotcut://` needs the editor's consent once. Keep the developer text short and in plain words. Whether "allow" is remembered is not measured; it needs a run that clicks Allow with a handler registered (T7.1 step 7b) |
| Quit / restart API | No quit, exit, restart or relaunch member exists on `premierepro` (72 names), `premierepro.Application(.prototype)` or `uxp.host`. The only matches are `CloseProjectOptions` and `ProjectClosedEvent`. Nothing was read or called | The panel cannot restart Premiere. A "Restart Premiere" card is text plus the editor's own action (Addendum C §3.4) |
| Hide / show lifecycle | Only `script.loaded` was recorded, with `entrypoints.setup` called. No `panel.create` or `panel.show` came, because the spike panel was not open in this workspace (the plugin ran headless) | The hide/show order is still unmeasured. It needs the panel opened from Window ▸ UXP Plugins |
| UI probes (fonts, svg, box-shadow, gradient, kit-code) | Every box measured **0 × 0**, because the panel was not shown. Computed styles did resolve: box-shadow `#9D6BFF 0px 0px 0px 2px` (token = literal); gradient `linear-gradient(90deg,#D95C9B,#5400FB)`; `kit-code` `display:inline`, background `#1E1E1E`, font "IBM Plex Mono"; svg color `#3DD68C` | `var()` resolves in UXP computed styles. Font loading and the svg paint are still unmeasured; the next run needs the panel visible (`style_guide` mode) |
| Premiere ops (create_project … save_close_open) | `create_project` timed out after 180 s and the rest were skipped (no scratch project) | Not a regression: a modal blocked it (next row). The ops were green in 0.1.3–0.1.5 and are unchanged |
| **Scratch Disk Error** (attributed) | Appeared **during `createProject`** on this PC (`scratch-disk-error.png`), while the permission dialog was stacked on top of it. Answering Yes created and opened the scratch project | `createProject` itself can raise this modal. Any engine path that creates a project must expect it: a long timeout plus a "Premiere is waiting for you" card |

Automation note: Adobe's dialogs ignore posted keyboard and mouse messages. Answering one needs a brief real foreground
with a real click or key, at the coordinates of the process's DPI-virtualised window rect.

## Product panel in real UXP

The WhyNot Cut product panel was loaded in Premiere as real UXP (screenshot
`docs/adobe/evidence/2026-10-12-premiere-run3-panel-history.png`, floating panels beside the CEP "WhyNot Cut Bridge"
3.1.0 panel and the spike panel v0.1.2). It **rendered**: the header with the monogram, the "WhyNot Cut" title,
the status chips ("Engine not running", "Claude unknown", "Host Premiere Pro 26..."), the red notice "The WhyNot Cut
engine is not running. In your Claude session run reel doctor", the Pipeline step pills (Transcript, Plan, Approve,
Build, Frames, QC, Handoff) and "Nothing is running." Observed problems: the **header is crowded at the floating width**
(the title wraps onto two lines next to the "No item selected" label and the chips; the Host chip is cut off), and the
**fonts appear to be system fallbacks** (Syne and the other brand fonts are not available in UXP). The CEP Bridge panel and the
UXP panels coexist in one Premiere.

**Run 4 (spike 0.1.3), screenshot `docs/adobe/evidence/2026-10-12-premiere-run4-panel-blocked.webp`.** The product panel showed the new
"blocked" diagnosis correctly: the chips read "Engine not running" (red), "Claude unknown" and "Host Premiere Pro 26.5.2"
(green), and the notice reads "The panel could not reach the engine on its port. In your Claude session run: reel serve
--status. The panel tries again by itself." The header is one line at this width (no wrapping). The spike panel (v0.1.3)
shows "Done: 15 pass, 3 fail, 1 n/a", the Source monitor reads "Source: (no clips)", the History panel "0 Undos" for the
reopened copy `spike-20261012-211920-copy`.

## Origin header

**Measured: UXP's `WebSocket` sends exactly `Origin: file://`** (Windows 11, Premiere Pro 26.5.2, UXP 9.3.0). Run
`211920` (spike 0.1.3) was still blocked inside Premiere by the manifest (W1, W2: "Permission denied to the url ...
Manifest entry not found"). Once the network permission let the request out, the WhyNot Cut panel 3.0.0 and spike 0.1.4
reached the daemon (port 53672), and every `/session` upgrade carried that exact value: `~/.whynot-cut/logs/serve-audit.log`
holds 205 rows `{"event":"origin","action":"/session","outcome":"rejected","reason":"file://"}` from 18:28:58Z to
18:52:26Z on 2026-10-12 (daemon pid 83576), each followed by `{"event":"http",...,"reason":"origin-browser-scheme"}`.
No other Origin value appears. There is no `/status` row, so whether UXP's `fetch` sends an Origin is still not
observed. The provisional policy refused `file` as a browser scheme, so the panel could never connect.

After the fix (`304cc06`) the daemon was restarted at 18:52:36Z (pid 159548, port 56549). Within 5 s two `/session` upgrades were logged with `"outcome":"allowed","reason":"file://"`, and both authenticated (`auth` `ok`):
- the spike (`uxp premiere ping,status,...`) at 18:52:40.656Z;
- the panel at 18:52:41.310Z.

**Policy (controller ruling, T6.2; `serve/security.py` `ALLOWED_ORIGINS_EXACT`).** The daemon allows the exact value
`file://` and nothing else new. The compare is case-sensitive and exact, so these stay refused:
- `FILE://`;
- `file:///...` with any path;
- `file://host`;
- `file:`;
- whitespace or a control character inside the value;
- `null`;
- every other browser scheme (http, https, ws, wss, extension schemes).

The request parser strips the optional whitespace around a header value before the check, as RFC 9110 §5.5 says it is not part of the value.

`file://` passes only the Origin gate. The client still needs the token (in the WebSocket `hello`, or as `Authorization: Bearer` for HTTP), a Host of `127.0.0.1:<port>` or `localhost:<port>`, and the loopback-only bind. Every Origin seen is audit-logged with its raw value and the outcome, allowed or rejected.

The `uxp://` / `plugin:` prefixes of the provisional policy are kept, but they are unmeasured. macOS UXP has not been measured, and `test_serve_app` pins `uxp://`. Remove them once the macOS measurement shows what macOS sends.

**Threat model.** Senders of `file://`:
- **UXP (measured)** sends it.
- **Chromium-family browsers** send `null` from a file page by default, and that is refused. They send `file://` when file-URL access is enabled. The T6.2 security review measured Chrome 154 started with `--allow-file-access-from-files` sending `Origin: file://` on both the WebSocket and `fetch`.
- **Embedders with the equivalent setting** send it too: Electron `allowFileAccessFromFileUrls` or `webSecurity: false`, and Android WebView.
- **CEP panels.** A CEP panel runs in CEF, so the future CEP adapter connection is likely to send `file://` as well. The same rule covers it; measure it when that adapter is built.
- **Everything else** is still refused: web and extension pages send their own http(s) or *-extension origin.

A client that passes the Origin gate this way still gets nothing without the token:
- Those contexts reach only the pre-auth surface: a WebSocket upgrade with 3 s (`hello_timeout`) to send a valid `hello` while it holds one of the 32 connection slots (`MAX_CONNECTIONS`), or a 401 from the HTTP routes.
- The token lives only in `<engine home>/bridge/engine.json`. That file is user-only (POSIX 0600, or a Windows DACL for the user's SID alone), and no web page can read it.
- The Host check stops DNS rebinding.
- The 127.0.0.1-only bind keeps everything off the machine out.

A process that runs as the user and can read engine.json is already past every one of these defences, the same trust as the user's own shell.

Allowing `file://` therefore adds pre-auth WebSocket surface to those contexts only, and nothing gets past `hello` without the token.

**Residual risk.** A file page that has file-URL access can also read the user's local files, `engine.json` included, so for that page the token is no barrier. That attack needs both of these:
- the user runs such a browser or embedder;
- the user opens a hostile local HTML file.

Such a page already holds the user's files. Before T6.2 the Origin gate refused it.

**Still to record:** whether UXP's `fetch` sends an Origin, the round trip of a protocol-4 `ping`, how long an idle socket stays open, and the macOS Origin.

**Follow-up (tracked, T6.2):** once macOS UXP is measured, replace the `uxp://` / `plugin:` prefixes (`ALLOWED_ORIGIN_PREFIXES`) with the exact values measured on macOS in `ALLOWED_ORIGINS_EXACT`, or drop them if macOS also sends `file://`. Update `test_serve_app.py::test_uxp_origin_is_allowed_and_audited` with them.

## Spike defects: status after 0.1.2

The 12 defects listed after 0.1.1, and where they stand.

| # | 0.1.1 defect | Outcome in 0.1.2 |
|---|---|---|
| 1 | Gaussian Blur picked `AE.Impact_Blur_FX` | Fixed: `AE.ADBE Gaussian Blur 2` appended, Blurriness 90 read back. Left: its Repeat Edge Pixels param has a blank name (E4) |
| 2 | Crop regex missed `AE.ADBE AECrop` | Fixed (K5 green) |
| 3 | Position keyframe not isolated | Fixed: the cause was building a keyframe from an array; `new PointF` works (K4 green) |
| 4 | Time basis undecidable | Fixed for a still: media time (K7 green); the XML-clip variant frames were byte-identical and not decisive |
| 5 | Preview codec sent the FourCC | Fixed: display name `Apple ProRes 422 LT` (S3 green) |
| 6 | Frame export tried too few forms | Fixed: native backslash folder (Q1 green) |
| 7 | save / close / reopen gave no attribution | Partly fixed: timestamps on every step, scratch set, reopen works with a backslash path (O2 green); the Project Modified dialog landed between the end of `sequence_settings` and the first calls of `export_frame` (indistinguishable at 1 s), not in save; the Scratch Disk dialog is still unattributed |
| 8 | `Application.version` counted as a failure | Fixed (informational step, `uxp.host.version`) |
| 9 | Static values never set | Fixed (K8 green) |
| 10 | Undo check pointed at the wrong menu | Fixed: per-probe labels, one `WhyNot Cut build` entry last; the Ctrl+Z revert still has to be pressed and checked (U3) |
| 11 | Missing probes | Mostly added (0.1.3 added `host_calls` and `ws_loopback` against the real daemon): save-as, project views, set end / start / move / out, transition, add track, remove clip, Lumetri. Still missing: MOGRT, `createSequence*`, audio track add, encoder export (off), `ws_loopback` |
| 12 | Report cleanliness | Fixed (`uxp_version`, `plugin_version`) |

For a spike 0.1.3 (small): (a) the in-point probe must read the clip's current in-point before computing the target (T2b);
(b) find and set the blank-name Gaussian Blur param by index (E4); (c) add `Date.now()` stamps around every call in
`sequence_settings` (including each `createSetSettingsAction` transaction) and `export_frame`'s `prepare`, to attribute Project Modified; (d) re-run the time-basis check on an XML clip whose frames
actually change (the 0.1.2 XML variant rendered a frozen picture); (e) wait for the exported file to stop growing before
recording its size; (f) the temp-folder export forms were never needed (the work-folder backslash form won first), so
that remains untested; (g) press Ctrl+Z once and check the three mutations (U3);
(h) measure the three host calls the panel host uses and the spike never ran: `SourceMonitor.openFilePath` (native path), `Sequence.setPlayerPosition(TickTime)` and `uxp.shell.openPath` **(done in 0.1.3, rows H1 - H3; left: confirm the source monitor really loaded the clip, and whether the `shell.openPath` consent is remembered)**. **0.1.3 itself added the daemon connection (W1 - W3); it failed on the manifest permission. Of items (a) - (g) the 0.1.3 run repeated the 0.1.2 results for (b) (Repeat Edge Pixels lookup still fails), and the Project Modified attribution (c) got no new data.**

## Decisions summary

- **UXP adapter now** (green): project create (see the O1 condition), save, close, open with a backslash path, save-as, scratch-disk set, persistence, active project, project views, still import, FCP7 XML import, sequence read-back, the four settings that were probed including the preview codec by display name, still placement, clip end / start / move / out / rename / disable, add a video track, remove a clip, Scale / Rotation / Opacity / Position / Crop keyframes with bezier interpolation **keyed in media time (`clip.getInPoint() + t`)**, static param values, the filter list, Sharpen, Noise, Lumetri, transitions, track rename, markers, single-frame export (backslash form), the `lockedAccess` + `executeTransaction` pattern with its "WhyNot Cut build" History label (one transaction per build if the editor should undo the build in one step).
- **Partial rows stay on CEP until re-measured** (decision rule above): `createProject` unattended (O1: Scratch Disk dialog and cold-start time), clip in-point action (T2b), Gaussian Blur Repeat Edge Pixels (E4), other settings setters (S4).
- **CEP compat op through the daemon permanently**: audio channel mapping and audio track types (the base FCP7 XML carries them), native caption track.
- **UXP network permission**: `network.domains: "all"` in the product and spike manifests (W1, W2); until it is in and re-measured, the daemon link is red and the panel stays on its "blocked" diagnosis.
- **Host calls**: `Sequence.setPlayerPosition` goes to the adapter (H2); `SourceMonitor.openFilePath` and `shell.openPath` are partial (H1, H3): asynchronous, long timeouts, a possible consent dialog.
- **Pending**: Ctrl+Z revert of the three-mutation transaction (U3), MOGRT, `createSequence*`, encoder export, and the Origin header and keepalive (W3, blocked by the network permission).
- **Open question for the controller**: which call raises Project Modified (it appeared between the end of `sequence_settings` and the first calls of `export_frame`, indistinguishable at 1 s resolution), and whether Scratch Disk Error still appears. A modal appeared during a settings / export step, so an unattended UXP build run is not assumed safe until this is answered.
