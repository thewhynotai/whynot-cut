# WhyNot Cut → a real Premiere Pro / After Effects plugin: technical assessment (October 2026)

Scope: turn the WhyNot Cut Adobe integration (CEP "WhyNot Cut Bridge" 3.1.0 + ExtendScript libraries + Python engine,
driven by the Claude Code plugin `whynot-cut` 2.2.0) into a branded, installable plugin for Premiere Pro and After
Effects on macOS and Windows. Part A reads the code as it is on `main` (read-only). Part B is web research with URLs.
The recommendation is at the end.

---

## Part A — The current implementation (code read on 2026-10-11)

### A.1 Components

| Layer | Files | Role |
|---|---|---|
| CEP bundle "WhyNot Cut Bridge" 3.1.0 | `templates/premiere/cep_bridge/CSXS/manifest.xml`, `index.html`, `js/bridge.js`, `jsx/host.jsx` | One bundle `ai.thewhynot.cut.bridge` with two extensions: a visible **panel** (`…bridge.panel`, Window › Extensions › WhyNot Cut Bridge, 360×260) and a hidden **daemon** (`…bridge.daemon`, `AutoVisible=false`, `StartOn` `com.adobe.csxs.events.ApplicationActivate` + `applicationActivate`, 1×1 `Custom` window). Hosts `PPRO [22.0,99.9]` and `AEFT [24.0,99.9]`; `ExtensionManifest Version="7.0"`, `RequiredRuntime CSXS 11.0`; CEF flags `--enable-nodejs --mixed-context`. `host.jsx` only defines `nhBridgeAlive()`. |
| Premiere ExtendScript | `templates/premiere/nh_ppro_lib.jsx` (`NHPP`) | All Premiere work: actions `ping`, `probe`, `new_project_import`, `import_xml_count`, `reference_export`, `build_project`, `export_frames`, `probe_frame_export`, `probe_frame_paths`, `clip_components`, `test_crop`, `close_project_path`, `close_project`. |
| After Effects ExtendScript | `templates/after_effects/nh_ae_bridge.jsx` (`NHAE`, entry), `nh_ae_lib.jsx` (`NH`, graphics/captions/MOGRT authoring), `nh_motion_lib.jsx` (`NHM`, motion mode) | Bridge actions `ping`, `fonts`, `probe_text`, `build_motion`, `readback`. `NH.build`/`NH.buildMogrts` are used by the opt-in extras through `AfterFX -r`/AppleScript, not the bridge. |
| Photoshop ExtendScript | `templates/photoshop/nh_ps_lib.jsx` (`NHPS`) | Layered PSDs; run by COM (`Photoshop.Application.DoJavaScriptFile`) on Windows or `osascript … do javascript` on macOS (`adobe_run.run_photoshop`). Not part of the bridge. |
| Engine (Python) | `engine/reel/lib/ppro_bridge.py`, `cep_queue.py`, `ae_bridge.py`, `ppro_build.py`, `premiere_xml.py`, `ae_builder.py`, `ae_probe.py`, `ae_render.py`, `motion_build.py`, `motion_readback.py`, `adobe_run.py`, `plat.py`; CLI `engine/reel/cli.py` | Install, status, job submission, build data, read-back checks, aerender, fallbacks, OS/app discovery. |
| Claude side | `skills/premiere-craft`, `skills/setup`, `skills/start`, `skills/motion-craft`, `skills/adobe-extras`; agents `premiere-builder`, `ae-builder`, `setup-doctor`, `qc-reviewer` + `frame-inspector`; `hooks/guard.py` | Agents only call `reel …` through Bash; the guard hook blocks Claude from writing Adobe CSXS preferences. |

### A.2 How a job flows (Premiere `reel ppro-build`)

```
Claude (premiere-builder agent, Bash)
  └─ reel ppro-build --root <CLIENT> --video-id <ID> [--force [--replace-edited]]
       cli.cmd_ppro_build → refuse_stale_window → require_plan_approval (Gate 1)
       ppro_build.build()
         1 ppro_bridge.status(): read <engine home>/ppro-queue/bridge.heartbeat; alive if < 5 s old
         2 existing .prproj? → submit("close_project_path") (Premiere saves + closes it), rename to *_prev_<ts>.prproj;
           EDITOR_CHANGES_PRESENT if the editor saved after the last build (content signature), unless --replace-edited
         3 job_data(): premiere_xml.build_xml() writes the base FCP7 XML (footage pieces, punch-ins, cleaned dialogue
           as L/R mono pairs on A1/A2, SFX, muted camera audio, empty named graphic lanes); graphics list (PNG still,
           lane, animation preset, start/end s); markers; sequence settings; track names; blur/sharpen targets;
           stage_stills() copies the PNGs to 07_premiere/media/stills-<ts> (Windows locks imported stills)
         4 ppro_bridge.submit("build_project", data, timeout=900)
             sync_scripts(): sha256-compare templates/premiere/nh_ppro_lib.jsx with <engine home>/ppro-scripts/ and copy
             cep_queue.submit(): write <jid>.data.json (ASCII-escaped JSON) → write <jid>.tmp → rename to <jid>.job.json
             (atomic) → poll <jid>.result.json every 0.5 s until timeout
CEP daemon or panel inside Premiere (js/bridge.js, setInterval 1 s)
  tick(): write bridge.heartbeat {at, busy, version, host, who}; if idle take the first sorted *.job.json
  runJob(): rename job → <jid>.running (atomic claim: panel and daemon both poll), realpath(job.script) must start with
            <engine home>/ppro-scripts/ (else error result), then
            __adobe_cep__.evalScript('$.evalFile(new File(script)); NHPP.run(data_file);', callback)
  ExtendScript NHPP.run(): eval() the data file, dispatch on data.action, return JSON string {ok, action, result}
  callback: write <jid>.result.json {ok: res !== 'EvalScript error.', result: res, at}; delete .running
            (a job with no reply in 20 min is failed and the queue released; a late reply is ignored)
Engine read-back
  cep_queue parses result → ok = bridge ok AND inner.ok; ppro_build computes 11 checks from Premiere's own read-back
  (prproj saved this run, previewCodec "apcs", 1080×1920, fps, linear colour on, max bit depth off, max render quality off,
  all graphics placed, V1 sharpened, caption track, dialogue clips on A1/A2) → 07_premiere/ppro-build-result.json
  (status PRPROJ_BUILT | PRPROJ_BUILT_WITH_ISSUES | FAILED, content signature for later edit detection)
QC
  reel ppro-frames → submit("export_frames") → PNGs of Premiere's own timeline in a fresh
  08_quality_control/premiere_frames/run-<ts>/ + labelled _sheet.jpg → qc-reviewer fans out frame-inspectors (Claude
  looks at the frames) → reel verify --record
```

After Effects uses the same protocol with `<engine home>/ae-queue`, whitelisted `<engine home>/ae-scripts` (three files
synced: `nh_ae_bridge.jsx`, `nh_ae_lib.jsx`, `nh_motion_lib.jsx`) and entry `NHAE.run`. `ae_bridge.status()` also
requires the heartbeat's `host` to be `AEFT`. `reel motion-build` runs: preconditions (Gate 1 approval + plan
fingerprint, bridge alive and idle, `ping`, an ok `ae-probe` verdict for this AE version, AE project not dirty, `fonts`
installed) → `build_motion` → `readback` → `motion_readback.compare()` (texts, fonts, Universal composer, RTL direction,
in/out frames, safe-area boxes, overlaps, cue hashes) → `04_after_effects/motion-build-result.json`. Rendering never goes
through the bridge: `aerender -project … -comp … -RStemplate … -OMtemplate … -output …` runs on the saved `.aep` in its
own process; ffmpeg pulls frames.

Other Adobe paths that bypass the bridge:
- `reel premiere`: standalone FCP7 XML (`07_premiere/interchange/…xml`) for manual File › Import; no keyframes, no
  preview codec, no track names, no captions.
- `reel motion-build --script-only | --run-script`: a self-contained JSX (`SCRIPT_ONLY`) or handed to AE with
  `AfterFX.exe -r` (Windows) / `osascript … DoScriptFile` (macOS) → `BUILT_UNVERIFIED` (no read-back, QC cannot pass).
- Extras (`--extras`): `ae-build`/`ae-render`, `mogrt-build` (AE authors `.mogrt` via `exportAsMotionGraphicsTemplate`),
  `ps-build` (Photoshop COM/AppleScript). Success is judged by files written in this run, never by the return value.

### A.3 Installation today

- `reel setup` (or `reel ppro-install [--force]`) copies `templates/premiere/cep_bridge` to the **per-user** CEP folder:
  - macOS `~/Library/Application Support/Adobe/CEP/extensions/ai.thewhynot.cut.bridge`
  - Windows `%APPDATA%\Adobe\CEP\extensions\ai.thewhynot.cut.bridge`
- writes `bridge-config.json` `{base: <engine home>, version}` into the extension folder (the panel cannot see the
  engine's environment variables); removes the legacy `com.nh.bridge` only if its manifest says "Reel Editor Bridge";
  creates `ppro-queue` (chmod 700) and syncs the scripts; refuses to downgrade a newer installed bridge unless `--force`.
- reads `PlayerDebugMode` for CSXS 11–14 (Windows `HKCU\Software\Adobe\CSXS.<n>`, macOS `defaults read com.adobe.CSXS.<n>`)
  and, if none is `1`, returns `editor_must_run` commands (`reg add "HKCU\Software\Adobe\CSXS.<n>" /v PlayerDebugMode
  /t REG_SZ /d 1 /f` or `defaults write com.adobe.CSXS.<n> PlayerDebugMode 1`). `hooks/guard.py` blocks Claude from
  running them (`defaults write/delete com.adobe.csxs*`, `reg add/delete/import …adobe\csxs`, `Set-ItemProperty` etc.).
- The editor must quit Premiere/AE before install (Windows locks the folder) and restart afterwards (CEP scans at launch).
- No ZXP, no signature, no installer, no uninstaller. The bundle is copied as loose files.

### A.4 What the panel shows

`index.html` hard-codes a dark style (`#232323` background, teal `#4FB3B5` title): the title "WhyNot Cut Bridge", the line
"by The Why Not AI · keeps Premiere connected to Claude", one state line (`starting…`, `idle — watching queue`,
`running <job id> (<action>)`, `FAILED to start: …`) and a monospace log of the last ~4,000 characters. No buttons, no
icon, no host-theme sync, no progress, no approvals, no link back to Claude. It is a status window for a daemon,
not a product UI. Small bug: the heartbeat's `who` field is meant to tell the visible panel (`ui`) from the hidden
daemon (`bg`), but both extensions load the same `index.html`, so `#state` always exists and `who` is always `ui`.

### A.5 Operations performed inside the hosts

**Premiere (`nh_ppro_lib.jsx`, classic ExtendScript DOM + QE DOM):**

| Need | How it is done today | API family |
|---|---|---|
| New project / open / activate / save / close | `app.newProject(path)`, `app.openDocument`, `app.projects[i]`, `project.save()`, `closeDocument(save, prompt)` | DOM |
| Bins, tidy | `rootItem.createBin`, `projectItem.moveBin`, `getMediaPath()` | DOM |
| Sequence creation with settings | **Not created by API**: the sequence comes from importing the engine's FCP7 XML (`importFiles([xml])`, then polling `waitSeq` because it registers late); then `seq.getSettings()` → set `previewCodec`, `previewFrameWidth/Height`, `maximumBitDepth`, `maximumRenderQuality`, `compositeLinearColor` → `setSettings` → read back | DOM + XML interchange |
| Footage, punch-ins (Basic Motion scale/centre), jump-cut zoom masking, linked A/V | In the XML | XML |
| Audio: stereo as L/R mono pairs, track attributes, A1–A8 layout, muted camera audio | In the XML (`premiereTrackType="Stereo"`, exploded track indexes …); no audio API calls | XML |
| Graphics | **PNG stills**, not MOGRTs: `importFiles` into "02 Graphics", `track.overwriteClip(item, sec)`, find the item by start time, `item.end = Time` | DOM |
| Animation | Keyframes on `Motion` (`Scale`, `Position`, `Crop Left`) and `Opacity` found by **display name**: `setTimeVarying(true)`, `addKey(t)`, `setValueAtKey(t, v, true)`; presets `bar_sweep`, `text_pop`, `slide`, `push`, `card`, `flash`, `fade` (frame constant `NHPP.F = 1/24` is hard-coded) | DOM |
| Effects | `Gaussian Blur` (Blurriness 90, Repeat Edge Pixels), `Sharpen` (+ `Noise` as grain) added with **QE** `qe.project.getVideoEffectByName(name)` + `addVideoEffect`, parameters then set through the DOM by display name | QE + DOM |
| Captions | Optional native track: import SRT, `seq.createCaptionTrack(item, 0, Sequence.CAPTION_FORMAT_SUBTITLE)`; default is animated caption PNG stills | DOM |
| Track names | `videoTracks[i].name = …` | DOM |
| Markers | `seq.markers.createMarker(t)`, `name`, `comments` (one per edit decision, with evidence) | DOM |
| Frame export (QC) | `seq.setPlayerPosition(ticks)` then **QE** `qe.project.getActiveSequence().exportFramePNG(CTI.timecode, path)` (needs the timecode string; ticks silently export frame 0; Windows accepts only backslash paths) | QE (undocumented) |
| Reference XML | `seq.exportAsFinalCutProXML` | DOM |
| Read-back | `getSettings()` dump, track/clip counts, placed items, effect property values, `clip_components` dump | DOM |
| Export / AME | **Not used**: final render is the editor's | — |

**After Effects (`nh_ae_bridge.jsx` + `nh_motion_lib.jsx`, `nh_ae_lib.jsx`):** `app.newProject` (only when AE reports
the open project clean), `items.addComp` (one comp per scene + `MAIN_<reel>`), folders, `layers.addText`,
`addShape` (Lucide icons as native paths with Trim Paths draw-on), `addSolid`, `addNull`, brand colour controls
(`ADBE Color Control`) linked by expressions, `TextDocument` styling (`fontObject` via
`app.fonts.getFontsByPostScriptName`, `composerEngine = UNIVERSAL_TYPE_ENGINE`, `direction` RTL with a
`paragraphRange(0).direction` fallback because AE 25.2 drops it on `setValue`), text animators with Expressible
selectors (word reveal, emphasis), **one text layer per word** for RTL Arabic (AE 26.5 "Based On: Words" maps
`textIndex` inconsistently), anchor-point and opacity expressions, keyframes, transitions between scene layers, audio
layers with level keyframes, `renderQueue.items.add` + `outputModule(1).file`, `project.save`, fonts read-back
(`missingOrSubstitutedFonts`), `beginSuppressDialogs`/`endSuppressDialogs`, `sourceRectAtTime` boxes for safe-area
checks. Opt-in extras also author MOGRTs (`addToMotionGraphicsTemplateAs`, protected regions,
`exportAsMotionGraphicsTemplate`). Rendering: `aerender` (separate process) + ffmpeg frames.

### A.6 Known fragilities

1. **Unsigned extension + PlayerDebugMode.** The bridge loads only when the editor sets `PlayerDebugMode=1` for the
   CSXS version their host uses. The code checks 11–14; `premiere-assembly.md` says 11–13, `setup` says 11–14 (small
   doc drift). It is a per-user, per-CSXS-version security downgrade that lets *any* unsigned extension load, and it is
   the step new editors most often get wrong (wrong window, Git Bash mangling `/v /d /f`, another user account).
2. **Restart and lock rules.** CEP only scans at launch; Windows locks the extension folder while the host runs.
3. **One evalScript at a time, on the host's main thread.** Premiere's UI is blocked while a build runs (≈7 s for a
   build; frames longer); any modal dialog stalls a job until the 600–900 s caller timeout (20 min in the panel).
4. **Undocumented QE DOM** for effects and frame export (`exportFramePNG` timecode-string and backslash quirks were
   found by probing 26.5.2). QE can change without notice.
5. **Localisation.** Components, properties and effects are found by English **display names** (`"Motion"`,
   `"Opacity"`, `"Scale"`, `"Crop Left"`, `"Gaussian Blur"`, `"Sharpen"`, `"Noise"` with an `Intensity` vs
   `Amount of Noise` fork). A Premiere running in Arabic, French or German would not find them. Match names exist and
   should be used.
6. **"Media pending" (G69, `round4-gaps.md`).** `ppro-frames` right after a project opens exported 4 of 17 frames as
   the "Media pending" slate; a second run was clean. Needs a wait-until-online step and QC treating such frames as
   a re-export.
7. **Heartbeat file** is rewritten every second non-atomically (the reader retries torn reads); the queue folder's
   `chmod 700` has no effect on Windows ACLs; the data file is `eval()`ed in ExtendScript (trusted only because of the
   folder permissions).
8. **Hard-coded 24 fps** in the Premiere animation presets (`NHPP.F`), while profiles can run 29.97 fps (timing in
   seconds stays right; frame counts of the presets drift slightly).
9. **AE-specific:** libraries must be `$.evalFile`d at top level; `app.newProject()` discards work, so dirty checks
   gate it; RTL quirks above are measured per AE version by `reel ae-probe` and recorded in
   `~/.whynot-cut/ae-capabilities.json`; AE keeps imported audio open on Windows (content-addressed copies).
10. **Versions tested live:** Windows 11 + Premiere Pro **26.5.2** (bridge 3.0.0 full build; bundle 3.1.0 only
    `ppro-frames`), After Effects **26.5x89** (bundle 3.1.0, full motion build/read-back/render). Audit notes in
    `skills/adobe-extras/references/automation-matrix.md` record an earlier macOS audit of the AE/PS script paths
    (AppleScript), not of the CEP bridge.
11. **macOS untested for the bridge 3.x:** the CEP folder, `defaults` checks, `osascript` fallbacks, CoreText and
    `~/Library/Logs/CSXS` paths exist in code but no 3.x bridge build, frame export or AE motion build has run on a Mac
    (CHANGELOG 2.2.0 "Not verified live: … macOS"). Also unverified: a Premiere `ppro-build` on bundle 3.1.0, an Arabic
    project-folder path through ExtendScript `File()`, a build in a client's brand font.

### A.7 What already works in WhyNot Cut's favour

- A clean separation: the engine decides every frame and pixel; the host scripts only execute and read back. This
  maps one-to-one onto a UXP command layer.
- A whitelist + atomic-claim job protocol, evidence-based read-back, edit-detection and backups: these rules survive
  any transport change.
- The XML interchange already carries the parts that UXP still handles least well (audio mono pairs, mixed-rate tick
  maths), so the migration does not have to re-implement them first.

---

## Part B — Research (web, checked 11 October 2026)

Facts marked *unverified* could not be confirmed from a primary source.

### B.1 Premiere Pro UXP

**Status and versions**
- UXP in Premiere went public beta in 25.2 (Dec 2024) and became **generally available in Premiere 25.6** ("Official
  release of UXP extensibility in Premiere Pro") — https://developer.adobe.com/premiere-pro/uxp/changelog/ ,
  https://blog.developer.adobe.com/en/publish/2025/12/uxp-arrives-in-premiere-a-new-era-for-plugin-development .
  Minimums on every recipe page: Premiere 25.6, UXP Developer Tool 2.2, **manifest v5**
  (https://developer.adobe.com/premiere-pro/uxp/plugins/concepts/manifest/). Plugins appear under **Window › UXP Plugins**.
- Shipping line is **26.5.x** (26.5 API notes 10 Sep 2026: https://forums.creativeclouddeveloper.com/t/premiere-26-5-api-updates/12159);
  **27.0 is in beta** (official types 27.0.0-beta.x: https://github.com/adobe/premierepro-types/blob/main/CHANGELOG.md).
  Premiere 26.2 ships UXP 9.2.1, 26.3 ships UXP 9.3.0 (https://blog.developer.adobe.com/en/publish/2026/07/uxp-changelog-and-support-matrix).
- 2026 API changes that matter here:
  - **26.2:** hybrid plugins; `SequenceSettings.setVideoFrameRate`.
  - **26.3:** `Project.createSequenceWithPresetPath`, `createSetNameAction` on tracks, `Marker.guid`, EncoderManager
    `launchEncoder`/`startBatchEncode`, `ProjectConverter.exportAAF`; **breaking:** every `create*Action` must run inside
    `project.lockedAccess(() => …)` (https://forums.creativeclouddeveloper.com/t/premiere-26-3-api-updates/12009).
  - **26.5:** `MediaManager`, `Transcript.transcribeClipProjectItem`, `host.getBackgroundColor()`, fixed
    `ClipProjectItem.createSetIn/OutPointAction`.
  - **27.0 beta (types only):** `MogrtText` (`getText`/`setText`, font, size) usable from `ComponentParam.createKeyframe`;
    breaking type changes to `ComponentParam`/`Keyframe`, `Application` class removed.
  The API is still moving release to release; pin `minVersion` and type-check against `premierepro-types`.

**Coverage against what WhyNot Cut does today** (signatures from
https://github.com/adobe/premierepro-types/blob/main/src/premierepro.d.ts and the class pages under
https://developer.adobe.com/premiere-pro/uxp/ppro-reference/classes/ ; mutations are Actions run in
`project.lockedAccess(() => project.executeTransaction(ca => ca.addAction(…)))`, which also gives one undo step):

| WhyNot Cut operation (today) | UXP | API / note |
|---|---|---|
| New project, open, save, save-as, close (`app.newProject`, `openDocument`, `closeDocument`) | Supported | `Project.createProject`, `Project.open`, `save`, `saveAs`, `close`. No list of all open projects (workaround `ProjectUtils.getProjectViewIds`) — matters for `activateProject` |
| Bins, move items | Supported | `FolderItem.createBinAction`, move/rename/remove actions |
| Import media / stills / the FCP7 XML | Supported for media | `Project.importFiles(paths, suppressUI, targetBin, asNumberedStills)`; importing an **FCP7 XML** through it is *unverified* — first thing to test |
| Sequence with explicit settings | Partial | `createSequence`, `createSequenceFromMedia`, `createSequenceWithPresetPath` (26.3); `SequenceSettings.setVideoFrameRect`, `setVideoFrameRate`, `setAudioSampleRate` + `Sequence.createSetSettingsAction`. Audio channel type/count read-only. Whether preview codec (ProRes 422 LT), max bit depth, max render quality and linear colour are settable is *unverified* → a `.sqpreset` can carry them |
| Place stills on a track at a time, set end | Supported | `SequenceEditor.createOverwriteItemAction(item, time, vIdx, aIdx)`, `createInsertProjectItemAction`, track item `createSetEndAction`/`createSetStartAction`/`createMoveAction` |
| In/out, trim | Supported | track item and clip in/out actions (fixed in 26.5). **No razor/split** |
| Add tracks of a chosen type, audio mono pairs / channel mapping | Not supported | Inserting past the last track creates one, type not selectable; no `AudioChannelMapping` (open request, Jul 2026: https://forums.creativeclouddeveloper.com/t/missing-getaudiochannelmapping/12010) → keep the XML |
| Keyframes on Motion Scale/Position/Crop, Opacity | Supported | `getComponentChain` → `ComponentParam.createSetTimeVaryingAction`, `createKeyframe`, `createAddKeyframeAction`, `createSetValueAction`, interpolation; find components by **match name**, not display name |
| Add effects (Gaussian Blur, Sharpen, Noise; Lumetri) | Supported | `VideoFilterFactory.createComponent(matchName)` + `VideoComponentChain.createAppendComponentAction` — replaces QE `addVideoEffect` and removes the localisation fragility. Lumetri by match name *unverified* |
| Video transitions | Supported (video only) | `TransitionFactory.createVideoTransition` + `createAddVideoTransitionAction` |
| Native caption track from SRT (`createCaptionTrack`) | Not supported | read-only caption track access; Adobe: captions/text items "not yet supported via UXP" (https://forums.creativeclouddeveloper.com/t/uxp-full-control-over-premiere-timeline-when/11768) |
| MOGRT | Insert yes, text params not yet | `SequenceEditor.insertMogrtFromPath`; text only via 27.0-beta `MogrtText`; Adobe staff "work… is underway" (https://forums.creativeclouddeveloper.com/t/mogrt-parameters-in-uxp-availabilty/11408?page=2). WhyNot Cut uses PNG stills, so this is not blocking |
| Track names | Supported (26.3) | `createSetNameAction` |
| Markers with name/comment | Supported | `Markers.getMarkers(seq).createAddMarkerAction(name, type, start, duration, comments)` |
| Single-frame export (QE `exportFramePNG`) | Supported | `Exporter.exportSequenceFrame(sequence, time, filename, filepath, width, height)` → `Promise<boolean>`, since 25.6, png/jpg/tif/exr… (https://developer.adobe.com/premiere-pro/uxp/ppro-reference/classes/exporter/) — no QE, no timecode-string or backslash quirks |
| Export via encoder / AME | Supported (new capability) | `EncoderManager.exportSequence(seq, IMMEDIATELY | QUEUE_TO_AME, out, preset)`, `encodeProjectItem`, `isAMEInstalled`, render events; `ProjectConverter.exportAsFinalCutProXML`, `exportAsOpenTimelineIO` |
| Read-back of the timeline | Supported | tracks → `getTrackItems` → start/end/in/out/duration/project item/component chain; `getSettings`, `getFrameSize` |
| QE DOM | Not available | "in UXP, there is no such thing as QE DOM… the plan is to expose some (but definitely not ALL) QE DOM functions" (https://community.adobe.com/t5/premiere-pro-discussions/extendscript-unsupported-undoc-commands-are-hidden-behind-40-is-there-a-way-to-get-them-for-free/m-p/15129503) |

Community gap list: https://forums.creativeclouddeveloper.com/t/premierepro-migrating-from-cep-to-uxp-community-api-gap-issue-summary/11373 .
There is no Premiere-specific CEP→UXP guide; the generic one is https://developer.adobe.com/uxp/migration-center/uxp-for-cep-devs/technical-migration-guide/ .

**Network, processes, files** (https://developer.adobe.com/premiere-pro/uxp/plugins/concepts/manifest/)
- `requiredPermissions`: `network.domains` (list or `"all"`), `localFileSystem` (`plugin` | `request` | `fullAccess`),
  `launchProcess` (`schemes`, `extensions`), `clipboard`, `webview`, `ipc`, `enableAddon`.
- `fetch`, XHR and **WebSocket clients** work; a plugin **cannot listen** for connections; unlisted domains fail;
  "macOS restricts `http://`" (https://developer.adobe.com/premiere-pro/uxp/resources/recipes/network). Adobe's own
  Premiere OAuth sample talks to `http://localhost:8000` with `"domains": "all"`
  (https://github.com/AdobeDocs/uxp-premiere-pro-samples/tree/main/sample-panels/oauth-workflow-sample). Exact
  loopback/port domain entries are *unverified* (forum reports of failures). Self-signed certs cannot be used for
  `wss://` on macOS (migration guide above).
- Processes: only `shell.openPath` / `shell.openExternal`, behind `launchProcess` and a **user consent dialog**; "not
  possible to pass any parameters, nor to capture the output"
  (https://developer.adobe.com/premiere-pro/uxp/resources/recipes/external-process). The panel cannot start `reel serve`
  with arguments; the engine must already be running (or be started by a launcher file the user approves).
- Files: `fullAccess` gives `require("fs")` with absolute paths; the plugin folder is read-only
  (https://developer.adobe.com/premiere-pro/uxp/resources/recipes/filesystem-operations). So the panel can read the
  engine's config/token file and could even speak today's file queue.

**Hybrid plugins:** officially supported since Premiere 26.2 (UDT 2.2, CC Desktop 5.10); `.uxpaddon` for mac arm64,
mac x64, win x64; macOS binaries "must be signed and notarized with a valid Apple Developer ID certificate"; install
asks for admin credentials; docs disagree on manifest v5 vs "v6 or above"
(https://developer.adobe.com/premiere-pro/uxp/plugins/hybrid-plugins/ ,
https://developer.adobe.com/premiere-pro/uxp/plugins/hybrid-plugins/build). Not needed for WhyNot Cut (the engine
is already an out-of-process native component).

**ExtendScript from UXP:** not possible and not planned — "UXP doesn't use ExtendScript - and it won't ever"
(https://community.adobe.com/questions-734/uxp-error-in-premiere-pro-beta-25-2-evalscript-fails-311854); "we have no plans
to create any bridges to ExtendScript" (forum, Jun 2026, link above). ExtendScript itself is not being removed
(https://ppro-scripting.docsforadobe.dev/), but CEP — its only in-app host for a panel — is.

**CEP retirement (Adobe, Sep 2026,** https://blog.developer.adobe.com/en/publish/2026/09/investing-in-the-future-of-creative-cloud-extensibility-uxp-comes-to-our-flagship-applications **):**

| App | UXP | No new CEP Marketplace submissions | CEP off by default | CEP removed |
|---|---|---|---|---|
| Premiere | GA (25.6) | Dec 2027 | Dec 2028 | Dec 2029 |
| After Effects | public beta "by November 2026" | Dec 2028 | Dec 2028 | Dec 2029 |
| Media Encoder | public beta live | Dec 2028 | Dec 2028 | Dec 2029 |

"ExtendScripts are not affected by this transition"; every app gets "a guaranteed minimum of two years from its UXP
public beta".

### B.2 After Effects UXP

- **Not usable in production today.** The docs are published and labelled beta
  (https://developer.adobe.com/after-effects/uxp/); Adobe targets a **public beta by November 2026** (blog above); an AE
  category opened on the developer forum on 5 Oct 2026 (https://forums.creativeclouddeveloper.com/t/about-the-after-effects-category/12271).
  Every class page lists **Min Version 27.0** (https://developer.adobe.com/after-effects/uxp/after-effects-api/application),
  while the shipping line is 26.x — so nothing runs on AE 26.5. The manifest host id for AE is *unverified*.
- **Coverage looks right for motion mode once it ships** (43 classes, `require("aftereffects")`,
  https://developer.adobe.com/after-effects/uxp/after-effects-api/): `LayerCollection.addText/addBoxText/addShape/addSolid/addNull/add/precompose`;
  `TextDocument.direction = DIRECTION_RIGHT_TO_LEFT`, `composerEngine` (Universal by default), `digitSet`
  `ARABIC_DIGITS_RTL`, character/paragraph ranges (https://developer.adobe.com/after-effects/uxp/after-effects-api/textdocument);
  `Property.expression`, `setValueAtTime`, `setValuesAtTimes`, `addKey`, `KeyframeEase`
  (https://developer.adobe.com/after-effects/uxp/after-effects-api/property); `RenderQueue.render/renderAsync/queueInAME`
  (https://developer.adobe.com/after-effects/uxp/after-effects-api/renderqueue). Building shape *contents* groups is
  *unverified*; early forum bugs (no Keyframe class, `Application.effects` TypeError).
- **CEP + ExtendScript remain the supported route for AE 26.x.** AE 25.0+ runs CEP 12 (host `AEFT`)
  (https://github.com/Adobe-CEP/CEP-Resources/blob/master/CEP_12.x/Documentation/CEP%2012%20HTML%20Extension%20Cookbook.md).
  A July 2026 user report says AE 26.3 renamed the menu to **Window › Extensions (Legacy)** and that some new ZXP
  installs fail with "Unsupported Manifest version" (unconfirmed, no Adobe reply:
  https://community.adobe.com/bug-reports-528/in-recent-versions-of-after-effects-i-m-unable-to-install-or-sign-new-zxp-files-1632227);
  WhyNot Cut's own bridge 3.1.0 loaded fine in AE 26.5x89.
- `aerender` is still documented (https://helpx.adobe.com/after-effects/using/automated-rendering-network-rendering.html);
  no deprecation found.
- **Best path for AE:** keep the CEP/ExtendScript bridge for After Effects through 2027, **signed as a ZXP** so
  PlayerDebugMode is no longer needed; port `NHM` to AE UXP after the public beta, gated by the same
  `ae-probe` Arabic verdict, and finish before CEP is disabled by default (Dec 2028).

### B.3 Packaging and installation

**UXP `.ccx`**
- A `.ccx` is a zip; build it in the UXP Developer Tool (••• › Package) → `<id>_<host>.ccx`; **no signature or
  timestamp is required** (https://developer.adobe.com/premiere-pro/uxp/plugins/distribution/package). Premiere needs
  UDT 2.2+ (https://developer.adobe.com/premiere-pro/uxp/introduction/essentials/dev-tools).
- **One host per `.ccx`.** `host` must be a single object in production; an array is development-only and UDT packages
  only the first host (package page above). Premiere and (later) After Effects need separate packages.
- CLI packaging: `@adobe/uxp-devtools-cli` 1.5.1 exists but is barely maintained
  (https://forums.creativeclouddeveloper.com/t/status-of-uxp-devtools-cli/7672, https://github.com/adobe-uxp/devtools-cli/releases);
  since a `.ccx` is a zip of the plugin folder with a valid manifest, a CI script can zip it, but verify the result by
  installing it with UPIA on both OSes (*inference*).
- **Install with UPIA** (https://developer.adobe.com/premiere-pro/uxp/plugins/distribution/install):

  Windows (Command Prompt, may need admin):
  ```
  "C:\Program Files\Common Files\Adobe\Adobe Desktop Common\RemoteComponents\UPI\UnifiedPluginInstallerAgent\UnifiedPluginInstallerAgent.exe" /install "C:\path\ai.thewhynot.cut_premierepro.ccx"
  UnifiedPluginInstallerAgent.exe /list all
  UnifiedPluginInstallerAgent.exe /remove "WhyNot Cut"
  UnifiedPluginInstallerAgent.exe /help     (also /version)
  ```
  macOS (Terminal):
  ```
  "/Library/Application Support/Adobe/Adobe Desktop Common/RemoteComponents/UPI/UnifiedPluginInstallerAgent/UnifiedPluginInstallerAgent.app/Contents/MacOS/UnifiedPluginInstallerAgent" --install "/path/ai.thewhynot.cut_premierepro.ccx"
  … --list all   … --remove "WhyNot Cut"   … --help   … --version
  ```
  `--remove` takes the plugin name; a newer version replaces an older one
  (https://learn.fotoware.com/Fotoware_SaaS/Using_the_Fotoware_plugins/02-01_Enabling_the_Fotoware_plugins_for_Adobe_Creative_Cloud_on_your_computer/Command-line_installation__of_a_Fotoware_plugin_for_an_Adobe_product).
  `/enable` / `/disable` are *unverified* (check `--help`). Run the host app once first. UPIA ships with Creative Cloud
  desktop (5.5+, 5.7+ for `.ccx`); it installs into `%APPDATA%\Adobe\UXP\Plugins` / `~/Library/Application Support/Adobe/UXP/Plugins`
  and updates a database, so **copying files there by hand does not work**
  (https://blog.developer.adobe.com/en/publish/2022/03/how-to-install-uxp-plugins-using-command-line-tools). Adobe's help
  says the commands work only in user mode and while signed in to CC desktop (search snippet of
  https://helpx.adobe.com/creative-cloud/help/working-from-the-command-line.html, page not fetchable). A macOS `.pkg`
  postinstall runs as root, so it must call UPIA as the console user.
- **Double-click** a `.ccx`: CC desktop opens, shows an extra warning for non-Marketplace plugins, installs (install page
  above). Developers report double-click failing for ~15–20 % of users (file association, "No compatible app", macOS
  Tahoe), fixed by CC Repair or by UPIA
  (https://forums.creativeclouddeveloper.com/t/whats-your-experience-when-distributing-installing-ccx-files-it-looks-to-me-like-the-normal-flow-sometimes-does-not-work/11465).
  Installed `.ccx` plugins do not need Developer Mode (only loading unpackaged plugins does) — *inference* from
  the dev-tools page.
- **Distribution:**
  - Marketplace via the Developer Distribution portal: the portal issues the plugin ID that must match the manifest;
    upload the `.ccx`; review "within 10 business days"; listing icons 48/96/192 px, screenshot 1360×800
    (https://developer.adobe.com/uxp/guides/how-to/distribution/listing/,
    https://developer.adobe.com/photoshop/uxp/2021/distribution/submission-checklist). Private/unlisted listings and
    whether Adobe re-signs the package are *unverified*.
  - **Independent distribution:** host the `.ccx` yourself; no signing needed; CC warns users
    (https://developer.adobe.com/uxp/guides/how-to/distribution/independent-distribution/).
  - Enterprise: Admin Console packages with UPIA (https://developer.adobe.com/uxp/guides/how-to/distribution/enterprise-distribution/).
    Without CC desktop (Feature Restricted Licensing) UXP plugins "should work" via UPIA
    (https://developer.adobe.com/developer-distribution/creative-cloud/docs/guides/faq).

**CEP ZXP (for After Effects, and a Premiere compatibility bundle)**
- Sign (https://github.com/Adobe-CEP/Getting-Started-guides/tree/master/Package%20Distribute%20Install):
  ```
  ZXPSignCmd -selfSignedCert EG Cairo "The Why Not AI" "WhyNot Cut" <password> whynotcut.p12 -validityDays 3650
  ZXPSignCmd -sign build/cep_bridge dist/ai.thewhynot.cut.bridge.zxp whynotcut.p12 <password> -tsa http://time.certum.pl/
  ZXPSignCmd -verify dist/ai.thewhynot.cut.bridge.zxp -certinfo
  ```
  With a timestamp the extension keeps running after the certificate expires. A 2025 `-tsa` bug on Windows and a macOS
  segfault were reported, with a Windows fix shipped
  (https://community.adobe.com/t5/premiere-pro-bugs/zxpsigncmd-sign-process-is-broken-segmentation-fault/m-p/15280790).
- Install: **UPIA installs `.zxp`** too (since 1.2); **ExManCmd is deprecated** and unsupported by CC 2022+
  (https://blog.developer.adobe.com/en/publish/2021/06/new-command-line-tool-for-plugin-installation-replaces-exmancmd).
  Third-party: Anastasiy's Extension Manager, aescripts ZXP/UXP Installer (uses UPIA,
  https://aescripts.com/knowledgebase/index/view/faq/zxp-installer-faq). A signed extension can also be copied into a CEP
  folder: system `C:\Program Files (x86)\Common Files\Adobe\CEP\extensions` (and `C:\Program Files\Common Files\…`),
  `/Library/Application Support/Adobe/CEP/extensions`; user `%APPDATA%\Adobe\CEP\extensions`,
  `~/Library/Application Support/Adobe/CEP/extensions` (CEP 12 Cookbook above).
- **PlayerDebugMode** exists to "bypass the check for extension signatures" (CEP 12 Cookbook): `HKCU\Software\Adobe\CSXS.12`
  string `PlayerDebugMode=1`, or `defaults write com.adobe.CSXS.12 PlayerDebugMode 1` (+ restart Finder / cfprefsd)
  (https://community.adobe.com/questions-734/cep-panel-developers-update-necessary-to-load-unsigned-panels-in-25-0-beta-313915).
  A correctly signed ZXP does not need it (*inference from the cookbook wording*; to be confirmed on both OSes).
  Premiere and AE 25.0+ use **CEP 12** (Chromium 99, Node 17.7.1); Premiere 26.x on CEP 12 is *unverified*; there is no
  CEP 13 in Adobe's resources repo (https://github.com/Adobe-CEP/CEP-Resources).
- **Signing pitfall specific to WhyNot Cut:** today `ppro_bridge.install()` writes `bridge-config.json` *into* the
  extension folder after copying it. In a signed extension any added or changed file fails signature verification
  (an invalid or missing signature means the extension does not run:
  https://github.com/Adobe-CEP/Getting-Started-guides/tree/master/Package%20Distribute%20Install). The engine-home pointer must move to a
  fixed per-user path outside the extension (and the UXP plugin folder is read-only anyway).

### B.4 Branding and UX in the panel

**Platform facts**
- Built-in Spectrum widgets in UXP (`sp-button`, `sp-checkbox`, `sp-textfield`, `sp-picker`,
  `sp-progressbar`, `sp-meter`, `sp-dialog`, `sp-popover`, `sp-menu`, `sp-switch`, `sp-tooltip`, `sp-link`, `sp-icon`,
  `sp-divider`, `sp-heading`, `sp-body`, `sp-detail`…) follow the host's light/dark theme automatically
  (https://developer.adobe.com/uxp/guides/explanation/fundamentals/user-interfaces/,
  https://developer.adobe.com/premiere-pro/uxp/uxp-api/reference-spectrum/spectrum-to-swc-mapping/).
- Spectrum Web Components: since UXP 7.0, locked to **0.37.0** since UXP 8.0, via `@swc-uxp-wrappers/<name>` and
  `featureFlags.enableSWCSupport: true`; **the RTL `dir` setting does not work with `sp-theme`** — relevant for an Arabic
  UI (https://developer.adobe.com/premiere-pro/uxp/uxp-api/reference-spectrum/swc).
- Theme matching: `prefers-color-scheme` (lightest/light/dark/darkest; Adobe's table lists PS/XD only), `--uxp-host-*`
  variables (forum-documented), and **`uxp.host.getBackgroundColor()` since Premiere 26.5**
  (https://developer.adobe.com/premiere-pro/uxp/uxp-api/reference-css/media-queries/prefers-color-scheme ,
  https://forums.creativeclouddeveloper.com/t/help-with-uxp-host-theme/7959 , changelog above). Premiere has Darkest,
  Dark and Light themes since the Spectrum UI (https://helpx.adobe.com/premiere-pro/using/whats-new.html).
- Manifest icons: `width`, `height`, `path`, `scale` ([1,2] → `@2x`), `theme` (all/lightest/light/medium/dark/darkest),
  `species` (generic/toolbar/pluginList); toolbar 23/46 px, plugin list 24/48 px. Panel size: `minimumSize`,
  `maximumSize`, `preferredDockedSize`, `preferredFloatingSize` — "Premiere may not honor" them; keyboard shortcuts are
  ignored in Premiere (manifest page above). Marketplace icons 48/96/192 px.
- Naming: the Agent SDK branding rules allow "<YourAgentName> Powered by Claude" and forbid "Claude Code" naming or look-alike
  visuals (https://code.claude.com/docs/en/agent-sdk/overview). "WhyNot Cut · Powered by Claude" is safe.

**What a good editor-facing panel should show** (design recommendation)
1. **Header:** WhyNot Cut mark (theme-specific monochrome icon), client + reel (`Dr Sherin · EP02_R05`), and three status
   pills: *Engine* (connected / not running), *Claude* (session active / idle — from the engine's last activity), *Host*
   (Premiere 26.5.2 · UXP ok / CEP compat).
2. **Pipeline strip:** the gates the skills already enforce, as steps — Transcript › Plan › **Gate 1 approval** › Build ›
   Frames › QC › Handoff — with the current step's `sp-progressbar`, elapsed time and Cancel. Progress events come from
   the daemon (UXP build actions report per step: import, settings, graphics placed n/47, markers, save).
3. **Approvals inbox:** plan summary, the preview MP4 (open in the Source Monitor), flagged medical/religious statements,
   and **Approve / Request changes** buttons with a text field. An approval clicked in Premiere is a real editor
   approval recorded as `plan-approval.json --by editor` with the editor name — stronger evidence than "delegated".
4. **QC frames grid:** Premiere's own frames as tiles with the expected text/template and pass/fail; clicking a tile
   moves the playhead there (`sequence.setPlayerPosition`) so the editor sees it in context; "Re-export this frame" for
   Media-pending tiles.
5. **One-click actions:** Open project · Import/Rebuild build (with the edited-project warning and backup name) · Export
   frames · Render review MP4 (EncoderManager) · Reveal folder · Copy diagnostics.
6. **Collapsed log drawer** for support, never the main view.
7. **Bilingual EN/AR UI** following the editor's `whynot-cut.local.md` language; RTL via CSS `direction: rtl` on
   containers (not `sp-theme dir`), tested with Arabic client names and paths.
8. **Sizes:** docked ~340×640 px preferred, minimum ~280×320; everything must work in a narrow docked column.
9. **No free-form chat box in the panel** in v1: the conversation, permissions and gates stay in the editor's Claude Code
   session; the panel shows state and answers gates.

### B.5 Connecting the panel to Claude Code

**What exists in October 2026**
- **Adobe has no developer agent API or MCP server for desktop Premiere/AE.** Adobe's own AI Assistant entered public
  beta in Premiere on 18 June 2026 (bins, batch rename, interview questions, markers, a starting assembly; AE private
  beta) with no API, MCP or UXP hook mentioned (https://news.adobe.com/news/2026/06/adobe-unveils-major-expansion); the AE
  assistant reached public beta at IBC, again with no extensibility
  (https://blog.adobe.com/en/publish/2026/09/08/generate-create-directly-in-your-timeline-with-new-ai-powered-innovations-in-premiere-after-effects).
  The "Adobe for creativity" Claude connector (28 Apr 2026) works on cloud services, not a local Premiere timeline
  (https://blog.adobe.com/en/publish/2026/04/28/adobe-for-creativity-connector, https://developer.adobe.com/adobe-for-creativity/).
  An official Premiere MCP server is still a community feature request
  (https://community.adobe.com/feature-requests-730/official-model-context-protocol-mcp-server-for-premiere-pro-1644303).
  Adobe's assistant now competes for "assemble a first cut"; WhyNot Cut's moat is the client brand system, Arabic
  motion, the approval gates and evidence-based QC.
- **Community MCP servers** (all MIT, none endorsed by Adobe):

| Project | Path into the host | Maturity |
|---|---|---|
| mikechambers/adb-mcp (https://github.com/mikechambers/adb-mcp) | Python MCP → Node Socket.IO proxy :3001 → **UXP** plugin in Premiere (manifest v5, `premierepro` minVersion 25.6.0, `network.domains: "all"`, `localFileSystem: "fullAccess"`); AE and Illustrator via **CEP** | Proof of concept; Premiere "more limited", one sequence; ~22 commands incl. overwrite, in/out, effects, keyframes, markers, export frame, EncoderManager (https://raw.githubusercontent.com/mikechambers/adb-mcp/main/uxp/pr/commands/core.js). Socket.IO **polling on Windows, websocket on macOS**; proxy listens on all interfaces without auth (do not copy) |
| hetpatel-11/Adobe_Premiere_Pro_MCP (https://github.com/hetpatel-11/Adobe_Premiere_Pro_MCP) | Node MCP writes ExtendScript to a temp folder; CEP panel polls and `evalScript`s — WhyNot Cut's current pattern | ~280 tools; UXP "experimental"; telemetry on by default |
| leancoderkavy/premiere-pro-mcp (https://github.com/leancoderkavy/premiere-pro-mcp) | CEP file IPC; UXP preview (25.6+) over `ws://127.0.0.1:7777` with a token on the upgrade | Large; UXP path "needs live-host validation" |
| Dakkshin/after-effects-mcp (https://github.com/Dakkshin/after-effects-mcp), a-y-ibrahim fork (https://github.com/a-y-ibrahim/after-effects-mcp) | ScriptUI panel polling JSON command files | Early; the fork has Arabic/RTL text detection and background aerender |
| shotbyx-dev/premiere-mcp-server (https://github.com/shotbyx-dev/premiere-mcp-server) | Streamable HTTP MCP on `127.0.0.1:8787` + bearer token; file queue to CEP/ScriptUI | Tiny, early |

  Nothing mature, signed and cross-platform exists; every AE integration still uses ExtendScript. adb-mcp is a good
  reference for UXP Premiere calls and proves UXP → localhost works.
- **UXP localhost quirks:** `localhost` may resolve to `::1` and fail where `127.0.0.1` works; specific loopback/port
  domain entries have failed while `"all"` works
  (https://forums.creativeclouddeveloper.com/t/websocket-connection-not-working-in-manifestversion-5/6322,
  https://forums.creativeclouddeveloper.com/t/allowing-network-access-to-a-specific-port/11509,
  https://forums.creativeclouddeveloper.com/t/uxp-devtools-cli-websocket-error-object-object/7528). The Origin header a UXP
  WebSocket sends is undocumented: log it in the spike before writing the check.
- **Claude Code facts:** headless `claude -p` with `--output-format stream-json`, `--allowedTools`, `--permission-mode`
  (`dontAsk`), `--max-turns`, `--max-budget-usd`, `--resume` (https://code.claude.com/docs/en/headless,
  https://code.claude.com/docs/en/cli-reference). Agent SDK: "Anthropic does not allow third party developers to offer
  claude.ai login or rate limits for their products, including agents built on the Claude Agent SDK" without approval
  (https://code.claude.com/docs/en/agent-sdk/overview). Plugins can bundle MCP servers (`.mcp.json` / `mcpServers`,
  `${CLAUDE_PLUGIN_ROOT}`, `${CLAUDE_PLUGIN_DATA}`, `userConfig` with `sensitive: true` in the keychain)
  (https://code.claude.com/docs/en/plugins-reference, https://code.claude.com/docs/en/mcp). **Channels** (research preview)
  let a plugin's stdio MCP server push events into the running session (`capabilities.experimental['claude/channel']`,
  `notifications/claude/channel`) and relay permission prompts (`claude/channel/permission`) — exactly "editor clicks
  Approve in Premiere → Claude continues" — but custom channels register only with
  `--dangerously-load-development-channels` or an org allowlist until Anthropic lists them
  (https://code.claude.com/docs/en/channels, https://code.claude.com/docs/en/channels-reference).
- **Security baseline:** MCP Streamable HTTP servers MUST validate `Origin`, SHOULD bind to 127.0.0.1 and authenticate
  (https://modelcontextprotocol.io/specification/2025-11-25/basic/transports); local servers should prefer stdio or a token;
  DNS rebinding is a named attack (https://modelcontextprotocol.io/specification/2025-11-25/basic/security_best_practices);
  the MCP Inspector RCE (CVE-2025-49596) came from an unauthenticated localhost proxy
  (https://www.tenable.com/blog/how-tenable-research-discovered-a-critical-remote-code-execution-vulnerability-on-anthropic);
  OWASP: exact Origin allowlist, token not in the URL, message size caps, rate limits
  (https://cheatsheetseries.owasp.org/cheatsheets/WebSocket_Security_Cheat_Sheet.html).

**The four options**

| | (a) Engine daemon on 127.0.0.1 (WebSocket + token) | (b) File queue (today) | (c) MCP server in the engine | (d) Panel launches `claude -p` |
|---|---|---|---|---|
| Works from UXP | Yes, panel connects out as client | Yes (`fullAccess` + `fs`), polling only | Needs (a) or (b) underneath (UXP cannot host) | Only via `shell.openPath` with no arguments + consent dialog: impractical |
| Latency / live progress | Push, ms; live progress | ~1 s poll; no push to panel | as (a) | seconds to start |
| Panel → Claude | Engine records approvals/requests as evidence files; channels later | files only | Claude → host only; host → Claude needs channels | a second, separate agent |
| Security | One surface: token, Host + Origin checks, loopback bind, schema-validated commands | folder permissions (no effect on Windows ACLs) | stdio between Claude and engine is safest | riskiest: spawns an agent with tool rights from a panel; login/branding rules |
| Robustness | must handle daemon down, reconnects, IPv4/IPv6 | very robust, easy to debug | long jobs need async/progress | many moving parts |

**Verdict:** (a) as the primary transport, (b) kept as the fallback transport, (c) as a thin stdio layer for Claude,
(d) rejected.

---

## Recommendation

### Target architecture

```
 Claude Code (editor's session)                     Adobe hosts
 ┌──────────────────────────────┐        ┌─────────────────────────────────────────────┐
 │ whynot-cut plugin            │        │ Premiere 26.5+                               │
 │  skills / agents / hooks     │        │  "WhyNot Cut" UXP plugin (.ccx, manifest v5) │
 │  reel CLI ───────────┐       │        │   panel UI (Spectrum) + command adapter      │
 │  stdio MCP (optional)┤       │        │   (premierepro DOM, lockedAccess+transaction)│
 └──────────────────────┼───────┘        └──────────────▲──────────────────────────────┘
                        │ local API                      │ ws://127.0.0.1:<port> (client→engine)
                 ┌──────▼──────────────────────────────┐ │ token from per-user config file
                 │ WhyNot Cut engine ("reel serve")     ├─┘
                 │  127.0.0.1 only · bearer token ·     │   ┌──────────────────────────────────┐
                 │  Host/Origin checks · job router ·   ├──►│ After Effects 25+ (and old Premiere)│
                 │  evidence files · file-queue fallback│   │  "WhyNot Cut Bridge" CEP 12, SIGNED │
                 │  (later: Claude channel server)      │   │  ZXP, ExtendScript NHAE/NHM (+NHPP │
                 └──────────────────────────────────────┘   │  compat ops)                        │
                                                            └──────────────────────────────────┘
```

**Components**
1. **WhyNot Cut for Premiere (UXP, new).** `.ccx`, plugin ID from Adobe Developer Distribution, `host: {app:
   "premierepro", minVersion: "26.5.0"}`, permissions `localFileSystem: "fullAccess"` and
   `network.domains: ["ws://127.0.0.1", "http://127.0.0.1"]` (fall back to `"all"` only if the spike shows the
   explicit entries fail). A panel (B.4) plus a command adapter implementing the same actions as `NHPP`, in TypeScript
   against `premierepro-types`, finding components/effects by match name, every mutation inside
   `lockedAccess`+`executeTransaction` (one undo step: "WhyNot Cut build").
2. **WhyNot Cut Bridge (CEP, kept, signed).** The 3.x bundle becomes a signed, timestamped ZXP for After Effects (motion
   mode, extras) and a Premiere compatibility adapter for the few ops UXP lacks (native caption track; anything that
   fails the parity matrix). JSX libraries ship *inside* the signed bundle with a version handshake; engine-home
   discovery moves out of the extension folder.
3. **Engine daemon `reel serve` (new, Python).** Loopback-only WebSocket/HTTP, 256-bit token in a per-user config file
   (`~/Library/Application Support/WhyNot Cut/engine.json`, `%APPDATA%\WhyNot Cut\engine.json`, user-only permissions)
   that the UXP panel reads with `fs`; rejects any `Host` other than `127.0.0.1:<port>`/`localhost:<port>` and any
   browser `Origin`; no "run arbitrary script" endpoint; schema-validated commands; per-command routing to the UXP or
   CEP adapter; progress events; writes the same evidence files as today. File queue stays as the fallback transport.
   Started by the Claude plugin's SessionStart hook (`reel serve --ensure`) and optionally by a login item
   (LaunchAgent / HKCU Run) the installer offers.
4. **Claude Code plugin (unchanged contract).** Skills/agents keep calling `reel …`; `reel` talks to the daemon when it
   runs, else the file queue. Optional bundled stdio MCP server exposing typed tools (`premiere_build`,
   `premiere_export_frames`, `ae_build_motion`, `bridge_status`) that call the same engine code. Later: the same server
   declares `claude/channel` so panel approvals and requests arrive in the session once custom channels are allowed.
5. **Installers.** "WhyNot Cut Setup": macOS notarized `.pkg`; Windows signed `.exe`/MSI (Microsoft Artifact Signing,
   formerly Trusted Signing: https://azure.microsoft.com/en-us/products/artifact-signing; Apple notarization:
   https://developer.apple.com/documentation/security/notarizing-macos-software-before-distribution). They install the
   engine bootstrap, run UPIA for the `.ccx` and the `.zxp`, write `engine.json`, and point to the Claude marketplace
   install. `reel setup` keeps working for developer installs.
6. **Later: WhyNot Cut for After Effects (UXP)** once AE 27.x UXP is public and the Arabic probe passes on it.

### Minimum host versions
- **Premiere UXP plugin: 26.5.0** (26.3 locking model, `createSequenceWithPresetPath`, track rename; 26.5 in/out fix and
  `getBackgroundColor`); validated on 26.5.2. Revisit for 27.0 (breaking type changes, `MogrtText`).
- **CEP bundle:** Premiere 25.0+ and After Effects 25.0+ (CEP 12) as the tested floor (today's manifest allows PPRO 22 /
  AEFT 24 untested). Premiere 25.0–26.4 users run the CEP path; below 25.0 → XML fallback only.
- **After Effects UXP:** 27.0+ (not before 2027).

### Packaging and install per OS
- **Windows:** signed installer → `UnifiedPluginInstallerAgent.exe /install "…\ai.thewhynot.cut_premierepro.ccx"` and
  `/install "…\ai.thewhynot.cut.bridge.zxp"` as the logged-in user; verify with `/list all`; uninstall with
  `/remove "WhyNot Cut"` / `/remove "WhyNot Cut Bridge"`. Fallbacks: double-click the `.ccx`; aescripts ZXP/UXP Installer.
- **macOS:** notarized `.pkg` → postinstall runs `…/UnifiedPluginInstallerAgent.app/Contents/MacOS/UnifiedPluginInstallerAgent --install <ccx|zxp>`
  **as the console user** (not root), with CC desktop signed in and each host launched once; verify with `--list all`.
- **No PlayerDebugMode** for end users once the ZXP is signed; keep the doctor's PlayerDebugMode advice only for
  developer builds. Hooks keep blocking Claude from changing it.
- **Distribution:** start with independent distribution (own site, signed installers); Marketplace listing later for
  discovery (10-business-day review, ID must match).

### Migration steps from CEP 3.1.0
| Phase | Work | Exit criterion |
|---|---|---|
| 0 · Harden CEP (now) | G69 wait-until-online + re-export of Media-pending frames; match names instead of display names; fix the `who` field; move `bridge-config.json` to `engine.json` outside the extension; ship JSX inside the bundle with a version handshake; sign + timestamp the ZXP; install via UPIA; update docs for AE "Window › Extensions (Legacy)" | Signed bridge loads with PlayerDebugMode **off** on Premiere 26.5.2 + AE 26.5, Windows **and macOS**; ppro-build 11/11 on bundle 3.2 |
| 1 · Contract + daemon | Versioned JSON-Schema command contract from the `NHPP`/`NHAE` actions and their read-back shapes; `reel serve` with token/Host/Origin checks and adapter router; `reel` uses it, falls back to the file queue | Existing CEP path passes the suite through the daemon; golden read-back fixtures |
| 2 · UXP spike (1–2 weeks) | Minimal manifest-v5 plugin on both OSes: loopback WS (record the Origin header), `importFiles` of the base FCP7 XML, `SequenceSettings` coverage (preview codec, linear colour, bit depth, render quality), `exportSequenceFrame` incl. Media pending, Motion/Opacity/Crop keyframes by match name, Gaussian Blur/Sharpen/Noise via `VideoFilterFactory`, track rename, markers, open/save/close | A green/red parity matrix per operation |
| 3 · UXP adapter + panel | Port `build_project`, `export_frames`, `close_project_path`, `probe`, `clip_components`; panel per B.4; setting `bridge: auto|uxp|cep` | PODCAST-TEST and a real client reel: identical checks and frame sheets via UXP and CEP |
| 4 · Ship | `.ccx` + signed ZXP + installers; independent distribution; optional Marketplace | Clean install on fresh Windows and macOS machines with CC desktop only |
| 5 · After Effects | Track AE UXP public beta; port `NHM` + probe to UXP on 27.x | ae-probe verdict ok on UXP; motion build/read-back parity; done before Dec 2028 |
| 6 · Retire Premiere CEP | Remove the Premiere compat ops once UXP covers them for two releases | Before Dec 2028 (CEP off by default) |

### Risks
- **UXP API churn and gaps:** 26.3 made every action need `lockedAccess`; 27.0 changes types and removes `Application`;
  no caption-track creation, no audio channel mapping, no razor, no track-type control, MOGRT text only in 27.0 beta.
  Mitigate: pinned `minVersion`, typed build, a smoke test per Premiere update, per-op routing to CEP.
- **Localhost from UXP:** IPv6 resolution, domain-entry matching, Windows WebSocket reliability (adb-mcp uses polling
  on Windows). Mitigate: `127.0.0.1` literals, HTTP long-poll fallback, file-queue fallback.
- **Installer dependencies:** UPIA needs CC desktop and a signed-in user; double-click `.ccx` fails for a minority;
  macOS postinstall must run UPIA as the user.
- **CEP sunset:** Premiere no new CEP submissions Dec 2027; CEP off by default Dec 2028 (Premiere and AE); removed Dec
  2029. AE migration must happen in 2027–2028 on a platform still in beta.
- **Signing:** any post-install write into a signed extension breaks it; ZXPSignCmd `-tsa` bugs; native helpers need
  notarization on macOS.
- **macOS never tested for bridge 3.x:** paths and `defaults` code exist but nothing ran live; the test matrix must
  include Apple Silicon before "macOS" is claimed.
- **New attack surface:** a local daemon that can drive Premiere and read client folders. Token, loopback bind,
  Host/Origin checks, no arbitrary-script endpoint, size limits, audit log.
- **Policy/branding:** no Claude login inside the panel or an SDK-based app without approval; "Powered by Claude", never
  "Claude Code".
- **Competition:** Adobe's Premiere AI Assistant (public beta) covers bins, markers and rough assembly natively.

### Fallback plan if a UXP API is missing
| Missing in UXP | Fallback, in order |
|---|---|
| Audio mono pairs / channel mapping / track types | Keep the engine's FCP7 XML for the base timeline (if `importFiles(xml)` works in UXP) → `.sqpreset` with the track layout + `createSequenceWithPresetPath` → CEP compat op |
| Preview codec, linear colour, bit depth, render quality | Read-back after `createSetSettingsAction` → `.sqpreset` → CEP compat `apply_settings` → report as an editor step (as the XML fallback already does) |
| Native caption track | Animated caption stills (already the default) → CEP compat `create_caption_track` → SRT for manual import |
| MOGRT text parameters | PNG stills (current design) → MOGRT path behind a flag once `MogrtText` ships (27.0) |
| Single-frame export misbehaves | `exportSequenceFrame` retry with a Media-pending check → EncoderManager export of a short range + ffmpeg frames → CEP QE `exportFramePNG` |
| An effect cannot be added by match name | Engine pre-renders the look into the still/fill → CEP QE `addVideoEffect` |
| Anything else | Route that one command to the signed CEP adapter (works until Dec 2028, removable Dec 2029); long term a hybrid `.uxpaddon` (26.2+, notarized) or a documented editor step in the handoff |
