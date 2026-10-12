# PRD: Tidy — project cleaner, organiser and podcast sync for Premiere Pro

| | |
|---|---|
| Status | Shipped v2, macOS, Premiere Pro 2024+ (tested on 26.5) |
| Owner | Hoka |
| Source | `tidy/`, `install_tidy.sh` |
| Panel id | `com.hoka.tidy` (CEP 11) |
| ExtendScript namespace | `TIDY`, public functions `tidy_*` |
| Design history | `docs/superpowers/specs/2026-10-12-tidy-project-cleaner-design.md`, `…-tidy-v2-design.md` |

## 1. Summary
Tidy cleans a Premiere project and organises it in one pass: it removes what no sequence uses (from the project
only, never from disk), sorts everything into fixed numbered bins by real type (camera footage is recognised from
the file's own metadata, not its name), names nests after what they hold, colours each type, and removes the
leftover bins. Everything is shown first with tick boxes; the project is saved and backed up before anything
changes. In Podcast mode it also splits footage per camera and builds a synced multi-camera sequence by matching
sound (what PluralEyes did).

## 2. Problem and goals
Real projects (e.g. "Rog 2": 193 items, 41 bins) fill up with unused renders, duplicates, old Hush/Kalam leftovers,
bins named after scripts, renamed camera files mixed with After Effects renders, and "Nested Sequence 07". Goals:
- G1. Remove unused items safely: never a used item, never a file on disk, never a non-backup sequence.
- G2. One fixed, flat bin layout an editor learns once.
- G3. Footage = only what came out of a camera, even after renaming.
- G4. Preview, untick, apply, undo.
- G5. Podcast: cameras apart, mics apart, one synced sequence.

Non-goals: relinking offline media, transcoding, deleting files on disk, editing existing sequences.

## 3. Users and use cases
U1 (Reels): "Clean and organise this project." U2: "Same, but keep the captions files." U3 (Podcast, before
editing): "Put each camera in its own bin and give me a synced sequence of all cameras and mics." U4: "Undo."

## 4. Functional requirements

### 4.1 Scan (read only)
- FR-1 Walk the project tree: items (nodeId, name, bin path, sequence?, media path, offline flag, colour, duration)
  and bins (nodeId, path). Usage = project items referenced by clips of each sequence (video + audio tracks).
- FR-2 Graphic text per sequence: the "Source Text" of graphic clips (top video track first, ≤ 3 per sequence).
- FR-3 Disk info per item (exists, size) — Premiere's `isOffline()` is unreliable, the file is checked.
- FR-4 Media sniffing (read only): first + last 2 MB of each video, first 64 KB of each image; only the description
  is kept in memory (kind, camera id, icon, size), never the bytes.

### 4.2 Classification
- FR-5 Video kind, in order: render tags (XMP CreatorTool, MainConcept, Lavf, HandBrake, CapCut, Media Encoder,
  DaVinci) → camera tags (DJI Osmo/Pocket/Action/…, `com.apple.quicktime.model`, Sony NonRealTimeMeta, GoPro,
  Insta360, Canon, Panasonic, Blackmagic, Fujifilm, Nikon, Android) → render words in the name (render, export,
  final, compose, edit) → camera file names (C0001, IMG_1234, DJI_0001, GX010001, MVI_, DSC_, A001C002, PXL_, VID_,
  AVCHD 00001.MTS) → otherwise render. RAW formats (r3d, braw, crm, ari, insv) are camera.
- FR-6 Camera identity = model from the metadata + folder on disk (identical cameras are kept in their own folders),
  else the folder.
- FR-7 Images: size from PNG/JPEG/GIF/WebP headers; icon = svg/ico/icns, a name with icon/logo/emoji, or longest
  side ≤ 512 px.
- FR-8 Audio: SFX words or ≤ 8 s → SFX; music words → Music; Podcast mode: recorder formats (wav/bwf/aif) ≥ 180 s →
  Mics (checked first, unless the name says music/bgm/song); else Voice. Videos named with whole SFX words
  ("BLADE WHOOSH SFX.mp4") → SFX.
- FR-9 Sequences used inside another kept sequence are nests; Hush backups ("(Hush backup …" / "(Hush cut …") are
  backups.

### 4.3 Bins (both modes)
`01 Footage` (Podcast: `01 Footage/Cam 1…n`, Cam 1 = most footage) · `02 Renders & Stock` · `03 Audio/Voice` ·
`03 Audio/Music` · `03 Audio/SFX` · `03 Audio/Mics` · `04 Images/PNG` · `04 Images/JPG` · `04 Images/Icons` ·
`04 Images/Other` · `05 Graphics` · `06 Sequences` · `07 Nests` · `08 Captions` · `09 Other`.
Fixed label colour per type (images share one). No "Assets" bin. Only bins something goes into are kept; every other
bin (Assets, script bins, Kalam Captions, Recovered Clips, same-name siblings) is removed once empty.

### 4.4 Plan (pure, previewed)
- FR-10 Removals: unused media (not referenced by any kept sequence, through nests; usage inside Hush backups does
  not count), unused duplicates of a used file (same media path), Hush backup sequences. Never other sequences.
- FR-11 Opt-in removals (listed unticked): caption files (Premiere cannot tell which captions track uses them);
  Podcast mode: camera footage, mics and any recording ≥ 180 s (raw material for the sync).
- FR-12 Moves into the bins above, colours, empty bins (deepest first), duplicates both used (report only),
  offline files (report).
- FR-13 Nest names: the nest's text, else the first image it holds, else its first clip, else a nested sequence's
  name; whitespace collapsed, ≤ 50 characters, repeats get " 2", " 3"; listed with ticks.
- FR-14 Stats: items, total media size, to remove (count/size), share of the project size unused, count per type.

### 4.5 Apply
- FR-15 Confirm → save the project → copy the .prproj next to itself as "<name> (Tidy backup YYYY-MM-DD HHMMSS)" →
  apply → rescan. Undo = open the backup.
- FR-16 Host re-checks usage live and refuses to remove a used item or a non-backup sequence even if asked.
- FR-17 Order: moves → removals (all into one temporary bin, then the bin is deleted — the only removal the API
  offers) → empty bins by nodeId, only if `children.numItems === 0`, index rebuilt after each delete → colours →
  nest renames. Each step is fail-safe: a failure is recorded in `problems` and the rest continues.
- FR-18 Options: remove ticked items / organise into bins (incl. nest names) / colour by type.

### 4.6 Podcast sync ("Sync the podcast by sound")
- FR-19 Inputs: every camera clip and mic recording (one copy per file).
- FR-20 Per clip: Premiere exports its sound to WAV (temporary sequence + Wave48mono16 preset, deleted after, the
  active sequence restored); the panel streams the WAV in 4 MB pieces into mean power per 1 ms (no full recording in
  memory). A clip that fails to export is left out with its name.
- FR-21 Matching: log-RMS envelopes at 100 Hz, FFT cross-correlation against the longest recording (offsets may be
  negative), confidence = best peak / best peak elsewhere (outside ±0.5 s); < 3 → left out and named; refine at
  1 kHz within ±0.5 s on up to 120 s of overlap (target ≤ 1 frame).
- FR-22 Layout: everything shifted so the earliest clip starts at 0; Cam n on video track n; a clip that would
  overlap another clip of its camera gets a new track (never overwrite an angle).
- FR-23 Sequence "<project> - Synced" in `06 Sequences`, settings from Cam 1's longest clip; tracks added via QE
  (`addTracks`) and re-read; camera sound where Premiere puts it; mics on the audio tracks after the last one the
  cameras use; every placement read back (within one frame) and mismatches reported. Existing sequences untouched.

## 5. UX
Dark panel, Arabic default (RTL) / English. Project card with Reels | Podcast switch and Scan → summary stats →
options + sections: to remove (grouped by reason, with sizes), to move (by target bin), nest names, old bins,
duplicates in use, offline → Clean & organise (confirm box) → report + "Open the pre-clean copy". Podcast mode adds
"Sync the podcast by sound" with per-clip progress and a report of skipped clips.

## 6. Architecture
| Layer | Files | Role |
|---|---|---|
| Pure modules (Chromium; media/classify/plan also run in ExtendScript tests) | `js/media.js`, `js/classify.js`, `js/plan.js`, `js/sync.js` | sniffing, categories/bins, plan, sync maths |
| Node services | `js/engine.js` | disk info, byte sniffing, backup copy, WAV power streaming, temp files, logs |
| Panel | `index.html`, `css/tidy.css`, `js/main.js`, `js/i18n.js` | UI and flow |
| Bridge | `js/cep.js` | `evalScript('tidy_<fn>(json)')` |
| ExtendScript host | `jsx/host.jsx` | scan, apply, save, open, clip audio export, synced sequence |
Data dir `~/Library/Application Support/Tidy/` (`settings.json`, `logs/tidy.log`, `sync/` temp WAVs).

## 7. Interfaces (host)
| Function | Args | Returns |
|---|---|---|
| `tidy_scan` | – | `{items:[{nodeId,name,bin,isSequence,path,offline,color,duration}],bins:[{nodeId,path,name}],usage:{seqNodeId:[nodeIds]},texts:{seqNodeId:[raw Source Text]},project,name}` |
| `tidy_apply` | `{removals:[{nodeId,name,checked}],moves:[{nodeId,to}],emptyBins:[{nodeId,path}],colors:[{nodeId,color}],renames:[{nodeId,to,checked}]}` | `{moved,removed,skipped,binsRemoved,colored,renamed,problems:[…]}` |
| `tidy_save` | – | `{path}` |
| `tidy_open` | `{path}` | `{opened}` |
| `tidy_exportClipAudio` | `{nodeId,outPath}` | `{path}` |
| `tidy_buildSynced` | `{name,bin,first,cams:[{nodeId,start,track}],mics:[{nodeId,start}]}` | `{placed,sequence,videoTracks,audioTracks,micTrack,problems}` |

Plan output (`TidyPlan.build(scan, {unchecked, checked, noRename, mode})`): `{removals, moves, colors, duplicates,
offline, emptyBins, renames, stats}`. Sync: `TidySync.fromPower(power1ms) → {env,hi,seconds}`, `plan(tracks) →
{ref, placed:[{id,offset,confidence}], skipped}`, `layout(plan, roles) → {cams, mics, skipped}`.

## 8. Safety rules (must survive any refactor)
- Remove from the project only; media files are only ever read.
- Never remove a used item or a non-backup sequence (plan and host both check).
- Never delete a bin that holds anything; find bins by nodeId (same-name sibling bins exist in real projects and
  crashed v1 when found by path).
- Save + backup copy before applying; undo opens the backup.
- Sync builds a new sequence only; temporary sequences are deleted in `finally`.
- ExtendScript evaluates `a ? x : b ? y : z` wrongly: all nested conditionals parenthesised; a lint test enforces it.

## 9. Dependencies and platform
macOS, Premiere Pro 2024+, CEP 11 with Node, PlayerDebugMode. No Python, no external binaries. Windows would need:
data dir, `open`→`explorer`, preset paths (Kalam already has these).

## 10. Performance
Scan of ~200 items with ~50 videos on an external disk: a few seconds (4 MB read per video). Sync: the per-clip audio
export by Premiere dominates (not yet measured on long podcasts); matching < 1 s per clip in tests; memory ~30 MB
per hour of audio per track.

## 11. Acceptance tests (in repo)
- jsc: media (camera vs render incl. renamed DJI, AE render carrying source tags, compose export, RAW, AVCHD,
  iPhone model, identical cameras, image sizes, icons, graphic text), classify (bins, Podcast cams/mics, SFX whole
  words), plan (backup usage, nests, duplicates, offline, captions/podcast opt-in, old bins incl. same-name,
  nest names), sync (offsets ±, refine ≤ 2 ms, stranger skipped, WAV header, layout incl. overlaps), lint.
- Premiere (test projects only): host test 11/11 (camera/render/sub-bins, old same-name bins gone, nest renamed,
  used item refused); synced sequence with 3 cameras + 2 mics 4/4 (tracks added, mics after camera sound, read-back).
- Real panel end-to-end (CEP remote debugging): Podcast scan + sync placed clips at 3.217/7.5/20.0 s and the mics
  at 0/10 s; a clip from another recording was left out.
- Read-only dry run on a real project's files: 15 DJI + 4 iPhone clips → camera (renamed ones too), 46 renders.

## 12. Known limitations
- Sync expects the 48 kHz export (no 44.1 kHz drift guard); very short clips against a long recording may be left
  out without a reason shown; running sync twice makes a second sequence with the same name; a crash mid-export can
  leave a "Tidy sync temp" sequence.
- Camera tags beyond the first/last 2 MB of very long recordings fall back to name rules.
- Multicam source sequence is not created (scripting API); the synced stacked sequence is the output.

## 13. Integration notes for the combined plugin
- `media.js` (camera vs render, image size) and `sync.js` (audio sync) are generic and dependency-free.
- Clip audio export duplicates Hush/Kalam's export — share one host service.
- A natural combined flow: Tidy (organise + sync) → edit → Hush (cut silences/fillers) → Kalam (captions).
- Keep the preview-then-apply pattern and the host-side safety re-checks; never trust a plan computed in the panel.
- ExtendScript rules: ASCII only, ES3, namespaced globals, parenthesised nested conditionals.
