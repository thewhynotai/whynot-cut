# Phase 6B reservations (Kalam, Hush, Tidy, WNC_AUDIO)

Round 4 of the 3.0 Adobe track (2026-10-12) reserves names now so that Phase 6B (T6.11 to T6.16, Addendum A §A4) fits
without rework. **Nothing here works yet.** A reserved action has a name, a schema and a `protocol.json` entry. The
engine daemon never routes it.

Sources:
- `docs/superpowers/specs/addendum-a/ADDENDUM-A-kalam-hush-tidy.md` (§A0 is binding, plus §A2 and §A3);
- the three PRDs in `docs/superpowers/specs/addendum-a/prd/`;
- since the follow-up round, the owner's real host code, which the schemas follow:
  - `adobe/tools/hush/_upstream/jsx/host.jsx`;
  - `adobe/tools/kalam/_upstream/jsx/host.jsx`;
  - `adobe/tools/tidy/_upstream/jsx/host.jsx`.

Every schema description cites the upstream implementation and its public entry as
`adobe/tools/<tool>/_upstream/jsx/host.jsx:<line> <FN> (entry <public> :<line>)`. A test checks that those lines really
hold those functions.

## What "reserved" means

- **`protocol.json`.** Every entry has `"status"`:
  - `"active"` (the 15 actions of rounds 1 to 3) means it is routed today.
  - `"reserved"` (the 20 below) means it is never routed.
  - The field is never absent, and `tests/test_contract.py` checks this.
- **`uxp`** is the planned target, as for active actions. It is `true` only where `docs/adobe/uxp-parity.md` is green
  for that exact operation. It is `false` for everything UXP cannot do: razor, QE `addTracks`, audio track add,
  `createCaptionTrack` and MOGRT text. It is also `false` for anything not measured yet, such as the selection, In/Out,
  bins, marker removal and the encoder.
- **Schemas.** Each `<action>.schema.json` description starts with
  `RESERVED for Phase 6B (T6.1x) — shape from <PRD> §…, FR-…; not routed yet. Upstream: <file>:<line> <FN> …`.
  - **Keys** are snake_case, like every v4 contract key (see the mapping below). camelCase is kept only for a value
    copied verbatim from a Premiere or After Effects API object. No reserved schema needs one; the test allow-list is
    empty.
  - **Values** copied verbatim from Premiere are kept as Premiere gives them. One example: a selected clip's `type` is
    `mediaType`, `"Video"` or `"Audio"`.
  - **`data`** is closed at the top level. Required versus optional follows upstream: what upstream reads with
    `|| []`, `|| 0`, `|| null` or as a truthy flag is optional, and the schema says so.
  - **`readback`** is always open, so keys the host adds are not rejected. Every field is typed from upstream.
- **Router** (`whynot-cut/engine/reel/serve/router.py`). A `command` for a reserved action is answered before data,
  expiry or any adapter is looked at:
  - It returns `ok:false` with the error `reserved for Phase 6B (<tool>), not available yet`.
  - The `how` names the 6B task that will build the action.
  - It is audited as `event: command, outcome: reserved`.
  - `Router.pick()` also returns no adapter for a reserved action, even when a panel claims it as a capability.
  - `FileQueueAdapter.run` refuses a reserved action itself (`ValueError`), as defence in depth.
  - `<tool>` is `WNC_AUDIO shared audio export`, `Hush`, `Tidy` or `Kalam`.
- **Panel** (`adobe/panel-ui/src/contract.ts`). It has `ACTIVE_ACTION_NAMES` and `RESERVED_ACTION_NAMES`, and
  `ACTION_NAMES` is their concatenation, equal to `protocol.json`. A test scans every file under `panel-ui/src/` for a
  reserved name in double quotes, single quotes or backticks, so the panel UI does not expose them.
- **Session schema.** `hello.client.capabilities.maxItems` follows the action count (35).

## Reserved host actions

| Action | Tool | CEP function | uxp | PRD source | Upstream (implementation, entry) | FR / notes |
|---|---|---|---|---|---|---|
| `audio_export_range` | WNC_AUDIO (T6.11) | `WNC_AUDIO.exportRange` | false | Hush §7.1 `hush_exportAudio` + Kalam §7.1 `kalam_exportAudio` | hush `host.jsx:101 HUSH.exportAudio` (:331), kalam `host.jsx:92 KALAM.exportAudio` (:208) | Hush FR-3, FR-4; Kalam FR-3. Unlisted tracks are muted and restored, In/Out restored. Hush's `extDir` is dropped (the host finds the preset), `preset` is optional in the readback |
| `audio_export_clip` | WNC_AUDIO (T6.11) | `WNC_AUDIO.exportClipAudio` | false | Tidy §7 `tidy_exportClipAudio` | tidy `host.jsx:221 TIDY.exportClipAudio` (:312) | FR-19, FR-20; the temporary sequence is deleted in `finally` (§8) |
| `hush_info` | Hush (T6.12) | `WNC_HUSH.info` | false | Hush §7.1 `hush_info` | hush `host.jsx:71 HUSH.info` (:330) | FR-1, FR-2. Also returns `project_path`, track `muted` and selection `nest` (not in the PRD) |
| `hush_clip_sources` | Hush (T6.12) | `WNC_HUSH.clipSources` | false | Hush §7.1 `hush_clipSources` | hush `host.jsx:133 HUSH.clipSources` (:332) | FR-1, FR-7 |
| `hush_cut` | Hush (T6.12) | `WNC_HUSH.cut` | false | Hush §7.1 `hush_cut` | hush `host.jsx:165 HUSH.cut` (:333), relink `:254` | FR-19, FR-20, FR-21, §8. An empty cut list gives `{removed:0, cuts:0}` only. `linked` is `{groups, already_linked}` \| `{groups:0, note}` \| null. No razor in UXP |
| `hush_markers` | Hush (T6.12) | `WNC_HUSH.markers` | true | Hush §7.1 `hush_markers` | hush `host.jsx:288 HUSH.markers` (:334) | FR-22. Named markers are green (MK1); `label` is optional |
| `hush_clear_markers` | Hush (T6.12) | `WNC_HUSH.clearMarkers` | false | Hush §7.1 `hush_clearMarkers` | hush `host.jsx:301 HUSH.clearMarkers` (:335) | FR-22 (marker removal not measured) |
| `hush_set_playhead` | Hush (T6.12) | `WNC_HUSH.setPlayhead` | true | Hush §7.1 `hush_setPlayhead` | hush `host.jsx:311 HUSH.setPlayhead` (:336) | FR-15, FR-17. `setPlayerPosition` is green (H2) |
| `hush_restore` | Hush (T6.12) | `WNC_HUSH.restore` | false | Hush §7.1 `hush_restore` | hush `host.jsx:314 HUSH.restore` (:337) | FR-23. `restored` is the restored sequence's name (a string) |
| `tidy_scan` | Tidy (T6.13) | `WNC_TIDY.scan` | false | Tidy §7 `tidy_scan` | tidy `host.jsx:111 TIDY.scan` (:308) | FR-1, FR-2, FR-9. `color` is an int (-1 unknown), `path` is '' for sequences |
| `tidy_apply` | Tidy (T6.13) | `WNC_TIDY.apply` | false | Tidy §7 `tidy_apply` | tidy `host.jsx:152 TIDY.apply` (:309) | FR-12, FR-16, FR-17, FR-18, §8. Every list is optional; counts are ints, `problems` are strings |
| `tidy_save` | Tidy (T6.13) | `WNC_TIDY.save` | true | Tidy §7 `tidy_save` | tidy `host.jsx:300 TIDY.save` (:310) | FR-15. Save (O3) and the path (P3) are green; UXP's path carries `\\?\`, which the adapter strips |
| `tidy_open` | Tidy (T6.13) | `WNC_TIDY.open` | true | Tidy §7 `tidy_open` | tidy `host.jsx:301 TIDY.open` (:311) | FR-15 undo. O2 is green with a native backslash path; `opened` is the path (a string) |
| `tidy_build_synced` | Tidy (T6.13) | `WNC_TIDY.buildSynced` | false | Tidy §7 `tidy_buildSynced` | tidy `host.jsx:251 TIDY.buildSynced` (:313), addTracks `:240` | FR-22, FR-23, §8. `first` and `bin` are optional (defaults at :254 and :256), `mic_track` is 1-based (:293). T3b is red |
| `kalam_info` | Kalam (T6.14) | `WNC_KALAM.info` | false | Kalam §7.1 `kalam_info` | kalam `host.jsx:63 KALAM.info` (:207) | FR-2, FR-3. Tracks have the same chip shape as Hush |
| `kalam_captions_track` | Kalam (T6.14) | `WNC_KALAM.captionsTrack` | false | Kalam §7.1 `kalam_captionsTrack` | kalam `host.jsx:135 KALAM.captionsTrack` (:209) | FR-17, FR-20, FR-22. `start` and `name` are optional. C1 is red |
| `kalam_mogrt` | Kalam (T6.14) | `WNC_KALAM.mogrt` | false | Kalam §7.1 `kalam_mogrt` | kalam `host.jsx:166 KALAM.mogrt` (:210) | FR-18, FR-19, §8 all-or-nothing. `start` and `text_param` are optional; `field` is string \| null. M1 (text from 27.0) |
| `kalam_remove_clips` | Kalam (T6.14) | `WNC_KALAM.removeClips` | true | Kalam §7.1 `kalam_removeClips` | kalam `host.jsx:192 KALAM.removeClips` (:211) | FR-18, FR-22. Removes only clips named `Kalam …`. R1 and T4 are green, but reading a track item's name is not measured yet |
| `kalam_set_playhead` | Kalam (T6.14) | `WNC_KALAM.setPlayhead` | true | Kalam §7.1 `kalam_setPlayhead` | kalam `host.jsx:202 KALAM.setPlayhead` (:212) | FR-22. H2 is green |
| `kalam_version` | Kalam (T6.14) | `WNC_KALAM.version` | true | Kalam §7.1 `kalam_version` | kalam `host.jsx:205 KALAM.version` (:206) | FR-24. P1 is green; `version` is Premiere's `app.version` |

## Key mapping: upstream key to contract key

The T6.11+ port translates these keys at the CEP host boundary, in the `WNC_*` functions. The engine and the UXP adapter
only ever see the contract keys. Keys not listed are already the same, for example `start`, `end`, `path`, `cuts`, `t`,
`s`, `e`, `name` and `removed`.

| Upstream key | Contract key | Where |
|---|---|---|
| `outPath` | `out_path` | audio_export_range, audio_export_clip (data) |
| `audioTracks` | `audio_tracks` | audio_export_range (data) |
| `extDir` | dropped | Hush's exportAudio: the shared host finds the preset itself |
| `nodeId` | `node_id` | audio_export_clip, tidy_* lists and items, kalam_captions_track (readback) |
| `inPoint` | `in_point` | hush_info, kalam_info, hush_clip_sources |
| `outPoint` | `out_point` | hush_info, kalam_info |
| `projectPath` | `project_path` | hush_info, kalam_info |
| `sequenceId` | `sequence_id` | hush_cut (readback) |
| `alreadyLinked` | `already_linked` | hush_cut `linked` |
| `backupId` | `backup_id` | hush_restore (data) |
| `cutId` | `cut_id` | hush_restore (data) |
| `originalName` | `original_name` | hush_restore (data) |
| `isSequence` | `is_sequence` | tidy_scan items |
| `emptyBins` | `empty_bins` | tidy_apply (data) |
| `binsRemoved` | `bins_removed` | tidy_apply (readback) |
| `videoTracks` | `video_tracks` | tidy_build_synced (readback) |
| `audioTracks` | `audio_tracks` | tidy_build_synced (readback) |
| `micTrack` | `mic_track` | tidy_build_synced (readback), still 1-based |
| `srtPath` | `srt_path` | kalam_captions_track (data) |
| `mogrtPath` | `mogrt_path` | kalam_mogrt (data) |
| `videoTrack` | `video_track` | kalam_mogrt, kalam_remove_clips (data) |
| `textParam` | `text_param` | kalam_mogrt (data) |

How the brief's operation list maps onto actions:

| Operation in the brief | Action | Why |
|---|---|---|
| Hush razor, ripple, link and clone-sequence backup | `hush_cut` | One host call (`HUSH.cut`, relink in `HUSH.relink`), as FR-19 and FR-20 describe |
| Tidy moves, colours, bin removal and nest renames | `tidy_apply` | FR-17 fixes the order inside one call (`TIDY.apply`) |
| Tidy temporary sequences | `audio_export_clip`, `tidy_build_synced` | 'Tidy sync temp' is deleted in `finally`; the synced sequence is made from the first clip |
| Tidy QE `addTracks` | `tidy_build_synced` | `TIDY.addTracks`, host.jsx:240 |
| Kalam export WAV, Hush `exportAudio`, Tidy `exportClipAudio` | `audio_export_range`, `audio_export_clip` | Addendum A2: one shared host service |

## Engine-side tool runs (reserved here only, not in `cli.py`)

These shapes come from Addendum A2. The executor adds them in 6B. This round changes no `cli.py`, schema or daemon code
for them.

| Command | What it does | PRD |
|---|---|---|
| `reel kalam run --range in-out\|sequence\|playhead\|selection --mode ar\|en\|other --output track\|mogrt\|srt …` | Export the range, run the Kalam engine (its own process, JSON-lines stages), correct the text, build the captions, then place them through the host actions | Kalam §7.2, FR-1 to FR-23 |
| `reel kalam doctor` | Kalam's doctor (`{python,platform,backend,device,gpu,devices,models,claude,ok}`) | Kalam §7.2, FR-24 |
| `reel hush scan` | Export the range, compute the envelope and statistics, run Whisper words (or reuse Kalam's, §A3.3) | Hush FR-3 to FR-7 |
| `reel hush plan` | Silence and filler plan, previewed (pure `detect.js` / `fillers.js` logic) | Hush FR-8 to FR-18 |
| `reel hush apply --mode cut\|markers\|undo\|clear-markers` | `hush_cut` / `hush_markers` / `hush_restore` / `hush_clear_markers` | Hush FR-19 to FR-23 |
| `reel tidy scan` | `tidy_scan`, plus disk info and media sniffing (engine) | Tidy FR-1 to FR-4 |
| `reel tidy plan` | Classify and plan (pure `classify.js` / `plan.js`), previewed | Tidy FR-5 to FR-14 |
| `reel tidy apply` | `tidy_save`, then the backup copy (engine), then `tidy_apply`, then a rescan | Tidy FR-15 to FR-18 |
| `reel tidy undo` | `tidy_open` on the backup copy | Tidy FR-15 |
| `reel tidy sync` | `audio_export_clip` per clip, WAV power streaming and matching (engine), then `tidy_build_synced` | Tidy FR-19 to FR-23 |

### Panel-tab intents (names reserved, no schema this round)

The tabs send session intents next to `approve`, `request_changes` and `rebuild`. The 6B schema adds these to
`session.schema.json` and to the `reply.intent` enum:

- **`tool_run`** has the shape `{id, tool: "kalam"|"hush"|"tidy", step, options}`.
  - `step` mirrors the CLI verbs: `run`/`doctor` for Kalam, `scan`/`plan`/`apply` for Hush, and
    `scan`/`plan`/`apply`/`undo`/`sync` for Tidy.
  - The engine runs the same code as the CLI, and the report is the same (§A3.6).
- **`flow_run`** is "Organise → Cut → Caption" (§A3.4).
  - It runs Tidy, then Hush, then Kalam.
  - Each step still shows its own preview and needs its own confirm.

## Routing per operation (6B target)

The table uses these labels:
- **UXP** is the UXP plugin's adapter. Only operations whose parity row is green get it.
- **CEP** is the signed WhyNot Cut Bridge (`WNC_<TOOL>` ExtendScript, file queue).
- **engine** is `reel serve` / Python.

Today every row with UXP or CEP answers "reserved".

| Operation | Kalam | Hush | Tidy | Route |
|---|---|---|---|---|
| Sequence info (target, chips, selection, In/Out) | `kalam_info` | `hush_info` | – | CEP (UXP once the selection and In/Out are measured) |
| Clip sources | – | `hush_clip_sources` | – | CEP |
| Export a range to WAV | `audio_export_range` | `audio_export_range` | – | CEP |
| Export one clip to WAV | – | – | `audio_export_clip` | CEP |
| Razor, ripple, link and backup clone | – | `hush_cut` | – | CEP (QE razor; no UXP razor) |
| Add markers | – | `hush_markers` | – | UXP (MK1), CEP fallback |
| Remove Hush markers | – | `hush_clear_markers` | – | CEP |
| Restore the backup | – | `hush_restore` | – | CEP |
| Move the playhead | `kalam_set_playhead` | `hush_set_playhead` | – | UXP (H2), CEP fallback (the same operation as the active `set_player_position`) |
| Captions track from SRT | `kalam_captions_track` | – | – | CEP (C1 red) |
| MOGRT placement and text | `kalam_mogrt` | – | – | CEP (M1, text from 27.0) |
| Remove placed clips | `kalam_remove_clips` | – | – | UXP (R1, T4; the clip-name read still to be measured), CEP fallback |
| Versions for the report | `kalam_version` | – | – | UXP (P1), CEP fallback |
| Project scan | – | – | `tidy_scan` | CEP |
| Apply the plan | – | – | `tidy_apply` | CEP |
| Save, open | – | – | `tidy_save`, `tidy_open` | UXP (O3, P3, O2), CEP fallback |
| Synced sequence (QE `addTracks`) | – | – | `tidy_build_synced` | CEP (T3b red) |
| Transcribe, align, correct, captions | Kalam engine process | – | – | engine (separate process, JSON lines, Kalam §13) |
| Whisper words for fillers | – | reuse Kalam's words or faster-whisper | – | engine (§A3.3: one transcription per range) |
| Envelope, silences, fillers, plan | – | pure JS (`detect.js`, `fillers.js`, `wav.js`) | – | panel (pure logic, §A2) |
| Settings, presets, cache, logs, report | engine | engine | engine | engine (UXP cannot spawn) |
| Disk info, byte sniffing, WAV power streaming, backup `.prproj` copy | – | – | engine | engine |
| Classify, plan, sync maths | – | – | pure JS (`media.js`, `classify.js`, `plan.js`, `sync.js`) | panel (pure logic) |

## Remaining open points for Phase 6B

Upstream settled the earlier type questions:
- `hush_cut.cuts` and `linked`;
- `hush_restore.restored` and `tidy_open.opened`;
- the `tidy_apply` counts and `problems`;
- `tidy_scan` `color`, `path`, `duration` and `project`;
- `tidy_build_synced.first` and `bin`;
- `kalam_captions_track.item`, `kalam_mogrt.field` and `kalam_version.version`;
- the In/Out numbers and track `clips`.

What is still open:

1. **Unset In/Out.** Upstream reports an unset In or Out exactly as `getInPointAsTime` / `getOutPointAsTime` return it,
   with no flag. The panel logic decides "no In/Out" (Kalam FR-2).
2. **Playhead operation.** `hush_set_playhead` and `kalam_set_playhead` are the same host operation as the active
   `set_player_position`. 6B may merge them now that H2 is green.
3. **`kalam_remove_clips` on UXP.** It filters clips by name (`Kalam …`). Reading a track item's name in UXP is not
   measured yet, so the UXP adapter must measure it first.
4. **Panel version.** `kalam_version.panel` is hard-coded to `'1.1.0'` upstream. 6B should report the WhyNot Cut panel
   version instead.
