# Phase 6B reservations (Kalam, Hush, Tidy, WNC_AUDIO)

Round 4 of the 3.0 Adobe track (2026-10-12) reserves names now so that Phase 6B (T6.11 to T6.16, Addendum A §A4) fits
without rework. **Nothing here works yet.** A reserved action has a name, a schema and a `protocol.json` entry. The
engine daemon never routes it.

Sources: `docs/superpowers/specs/addendum-a/ADDENDUM-A-kalam-hush-tidy.md` (§A0 is binding, plus §A2 and §A3) and the three
PRDs in `docs/superpowers/specs/addendum-a/prd/`. Every shape below comes from a PRD host function table: Hush §7.1,
Kalam §7.1 and Tidy §7.

## What "reserved" means

- **`protocol.json`.** Every entry has `"status"`:
  - `"active"` (the 15 actions of rounds 1 to 3) means it is routed today.
  - `"reserved"` (the 20 below) means it is never routed.
  - The field is never absent, and `tests/test_contract.py` checks this.
- **`uxp`** is the planned target, as for active actions. It is `true` only where `docs/adobe/uxp-parity.md` is green
  for that exact operation. It is `false` for everything UXP cannot do: razor, QE `addTracks`, audio track add,
  `createCaptionTrack` and MOGRT text. It is also `false` for anything not measured yet, such as the
  selection, In/Out, bins, marker removal and the encoder.
- **Schemas.** Each `<action>.schema.json` description starts with
  `RESERVED for Phase 6B (T6.1x) — shape from <PRD> §…, FR-…; not routed yet.`
  - **Field names** are the PRDs' own: camelCase, exactly as the host tables write them. The 6B host code can then port
    the upstream `host.jsx` functions without renaming anything.
  - **`data`** is closed at the top level, because each PRD lists the arguments.
  - **`readback`** is always open: keys the host adds are not rejected.
  - **Types.** Where a PRD names a key but not its type, the property has no `type`, and its description says "its type
    is not stated in the PRD, left open". Nothing was invented.
- **Router** (`whynot-cut/engine/reel/serve/router.py`). A `command` for a reserved action is answered before data,
  expiry or any adapter is looked at:
  - It returns `ok:false` with the error `reserved for Phase 6B (<tool>), not available yet`.
  - The `how` names the 6B task that will build the action.
  - It is audited as `event: command, outcome: reserved`.
  - `Router.pick()` also returns no adapter for a reserved action, even when a panel claims it as a capability.
  - `<tool>` is `WNC_AUDIO shared audio export`, `Hush`, `Tidy` or `Kalam`.
- **Panel** (`adobe/panel-ui/src/contract.ts`). It has `ACTIVE_ACTION_NAMES` and `RESERVED_ACTION_NAMES`, and
  `ACTION_NAMES` is their concatenation, equal to `protocol.json`. A test checks that no other panel source names a
  reserved action, so the panel UI does not expose them.
- **Session schema.** `hello.client.capabilities.maxItems` follows the action count (35).

## Reserved host actions

| Action | Tool | CEP function | uxp | PRD source | FR / safety |
|---|---|---|---|---|---|
| `audio_export_range` | WNC_AUDIO (T6.11) | `WNC_AUDIO.exportRange` | false | Hush §7.1 `hush_exportAudio` + Kalam §7.1 `kalam_exportAudio` (one shared service, §A2) | Hush FR-3, FR-4; Kalam FR-3. The other tracks are muted and restored, In/Out restored. Encoder export (X1) not measured |
| `audio_export_clip` | WNC_AUDIO (T6.11) | `WNC_AUDIO.exportClipAudio` | false | Tidy §7 `tidy_exportClipAudio` | Tidy FR-19, FR-20; temp sequence deleted in `finally` (§8) |
| `hush_info` | Hush (T6.12) | `WNC_HUSH.info` | false | Hush §7.1 `hush_info` | FR-1, FR-2 (selection, In/Out and lock state not measured in UXP) |
| `hush_clip_sources` | Hush (T6.12) | `WNC_HUSH.clipSources` | false | Hush §7.1 `hush_clipSources` | FR-1, FR-7 (track item to source path not probed, R1 note) |
| `hush_cut` | Hush (T6.12) | `WNC_HUSH.cut` | false | Hush §7.1 `hush_cut` (razor, remove, ripple, link, clone-sequence backup) | FR-19, FR-20, FR-21, §8. UXP has no razor |
| `hush_markers` | Hush (T6.12) | `WNC_HUSH.markers` | true | Hush §7.1 `hush_markers` | FR-22. Adding named markers is green (MK1) |
| `hush_clear_markers` | Hush (T6.12) | `WNC_HUSH.clearMarkers` | false | Hush §7.1 `hush_clearMarkers` | FR-22 (marker removal not measured) |
| `hush_set_playhead` | Hush (T6.12) | `WNC_HUSH.setPlayhead` | true | Hush §7.1 `hush_setPlayhead` | FR-15, FR-17. `Sequence.setPlayerPosition` is green (H2, spike 0.1.3) |
| `hush_restore` | Hush (T6.12) | `WNC_HUSH.restore` | false | Hush §7.1 `hush_restore` | FR-23 |
| `tidy_scan` | Tidy (T6.13) | `WNC_TIDY.scan` | false | Tidy §7 `tidy_scan` (scan tree) | FR-1, FR-2, FR-9 (bins not measured in UXP) |
| `tidy_apply` | Tidy (T6.13) | `WNC_TIDY.apply` | false | Tidy §7 `tidy_apply` (moves, removals, bins, colours, nest renames) | FR-12, FR-16, FR-17, FR-18, §8 |
| `tidy_save` | Tidy (T6.13) | `WNC_TIDY.save` | true | Tidy §7 `tidy_save` | FR-15. Save (O3) and the project path (P3) are green |
| `tidy_open` | Tidy (T6.13) | `WNC_TIDY.open` | true | Tidy §7 `tidy_open` | FR-15 undo. Open with a backslash path (O2) is green |
| `tidy_build_synced` | Tidy (T6.13) | `WNC_TIDY.buildSynced` | false | Tidy §7 `tidy_buildSynced` (QE `addTracks`) | FR-22, FR-23, §8. UXP cannot add audio tracks (T3b red) |
| `kalam_info` | Kalam (T6.14) | `WNC_KALAM.info` | false | Kalam §7.1 `kalam_info` | FR-2, FR-3 |
| `kalam_captions_track` | Kalam (T6.14) | `WNC_KALAM.captionsTrack` | false | Kalam §7.1 `kalam_captionsTrack` (`createCaptionTrack`) | FR-17, FR-20, FR-22. No `createCaptionTrack` in UXP (C1 red) |
| `kalam_mogrt` | Kalam (T6.14) | `WNC_KALAM.mogrt` | false | Kalam §7.1 `kalam_mogrt` (`importMGT` + text) | FR-18, FR-19, §8 all-or-nothing. MOGRT text needs 27.0 (M1) |
| `kalam_remove_clips` | Kalam (T6.14) | `WNC_KALAM.removeClips` | true | Kalam §7.1 `kalam_removeClips` | FR-18 rollback, FR-22 undo. Read clips (R1) and remove a clip (T4) are green |
| `kalam_set_playhead` | Kalam (T6.14) | `WNC_KALAM.setPlayhead` | true | Kalam §7.1 `kalam_setPlayhead` | FR-22. `Sequence.setPlayerPosition` is green (H2, spike 0.1.3) |
| `kalam_version` | Kalam (T6.14) | `WNC_KALAM.version` | true | Kalam §7.1 `kalam_version` | FR-24. Host version and OS are green (P1) |

How the brief's operation list maps onto these actions:

| Operation in the brief | Action | Why |
|---|---|---|
| Hush razor, ripple, link and clone-sequence backup | `hush_cut` | The PRD's host contract does all four in one call: FR-19 razor, remove, one-pass ripple and relink; FR-20 backup clone first |
| Tidy moves, colours, bin removal and nest renames | `tidy_apply` | FR-17 fixes the order inside one host call and makes each step fail-safe |
| Tidy temporary sequences | `audio_export_clip` and `tidy_build_synced` | FR-20 (temporary export sequence, deleted in `finally`) and §8 |
| Tidy QE `addTracks` | `tidy_build_synced` | FR-23 |
| Kalam export WAV, Hush `exportAudio`, Tidy `exportClipAudio` | `audio_export_range` and `audio_export_clip` | Addendum A2: one shared host service |

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
| Remove placed clips | `kalam_remove_clips` | – | – | UXP (R1, T4), CEP fallback |
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

## Open questions for Phase 6B

The PRD names these keys but does not say their types. They stay open in the schemas, and 6B decides them from the
upstream code (H12) or by asking Yunus once (§A1).

1. **Hush.**
   - `hush_cut` readback: are `cuts` and `linked` counts, lists or flags?
   - `hush_restore`: is `restored` a boolean?
2. **Sequence info.**
   - `hush_info` and `kalam_info`: how is an unset In or Out reported?
   - `hush_info`: is a track's `clips` a count?
   - `kalam_info`: what is the track item shape (the PRD writes `[…]`)?
   - Both: is the track index 0-based? The schemas assume Premiere's DOM numbering.
3. **Tidy.**
   - `tidy_apply` readback: are `moved`, `removed`, `skipped`, `binsRemoved`, `colored` and `renamed` counts or lists?
     What is the shape of a `problems` item?
   - `tidy_scan`: what types are `path`, `color`, `duration` and `project`?
   - `tidy_open`: what type is `opened`?
   - `tidy_build_synced` data: what is `first`? The PRD does not explain it. Its readback types are also not stated.
4. **Kalam.**
   - `kalam_captions_track`: what type is `item`?
   - `kalam_mogrt`: what type is `field`?
   - `kalam_version`: is `version` Premiere's or Kalam's? FR-24's report lists "Premiere/panel versions", so the
     schema only types it as a string.
5. **Shared WNC_AUDIO.** `audio_export_range` keeps Hush's `extDir` as an optional field. The signed bridge knows its
   own folder, so 6B may drop it.
6. **Playhead.** `hush_set_playhead` and `kalam_set_playhead` are the same host operation as the active
   `set_player_position`, which is UXP and needs `sequence_name`. `setPlayerPosition` is now green (H2), so 6B may
   merge them into one operation. They are reserved per tool here because each PRD names its own.
