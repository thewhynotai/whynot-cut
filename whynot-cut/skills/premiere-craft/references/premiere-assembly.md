# Premiere Pro assembly (verified on Premiere 26.5.2)

## The bridge
Premiere can't be scripted from outside (macOS AppleScript exposes only capture/editoriginal; Windows has no COM API). The
**WhyNot Cut Bridge** is a CEP extension made of a visible panel plus a hidden daemon that auto-starts with Premiere.
- `reel setup` (or `reel ppro-install`) copies `templates/premiere/cep_bridge` into
  `~/Library/Application Support/Adobe/CEP/extensions/ai.thewhynot.cut.bridge` (macOS) or
  `%APPDATA%\Adobe\CEP\extensions\ai.thewhynot.cut.bridge` (Windows), plus `bridge-config.json` naming the engine home.
- Install needs `PlayerDebugMode=1` for CSXS 11–13. Setup only reports it. Never change Adobe security preferences yourself; the editor does that.
- **Restart Premiere after installing.** CEP scans for panels only at launch.
- Queue: `~/.whynot-cut/ppro-queue` (mode 700). Jobs are claimed atomically, and the heartbeat comes every second.
- Whitelist: only scripts in `~/.whynot-cut/ppro-scripts/` run. `sync_scripts()` copies the plugin's `nh_ppro_lib.jsx` there
  (hash-checked before every job). The plugin's own folder changes on every update, which is why the bridge needs this fixed path.

## `reel ppro-build` (about 7 s inside Premiere)
The build runs these steps:
1. Close any open copy, move the previous file aside as `<ID>_<PREFIX>_EDIT_prev_<ts>.prproj` (put back if the build saves
   no new project, also on Ctrl-C), and create a new project. If a hard kill left only the `_prev_` file, the next
   `ppro-build` stops with `PREVIOUS_PARKED` and says how to rename it back (`--force` builds anew and keeps it).
2. Import the base XML (`*_base.xml`). It holds the footage pieces (pause-tightened, jump cuts masked with alternating zoom), the cleaned dialogue on A1/A2 linked to V1, SFX on A3–A6, the original camera audio muted on A7/A8, and empty named graphic tracks.
3. `setSettings`: preview codec "apcs" (ProRes 422 LT) 1080×1920, max bit depth OFF, max render quality OFF, composite in linear colour ON. Every value is read back.
4. Place the brand stills on lanes and animate them with Premiere keyframes. The lanes are: B-roll, Graphic bars, Cards, Graphic text, one lane per checklist item, Caption bars, Caption text, Transitions.
5. Rename the tracks, tidy the bins, add markers (one per event, with its evidence), then save.
6. Read back into `07_premiere/ppro-build-result.json` and check:
   - the project was saved this run
   - the codec, frame size and fps
   - linear colour, bit depth and render quality
   - all graphics placed
   - dialogue on A1/A2

**Animation presets** (`NHPP.placeStill`, in `templates/premiere/nh_ppro_lib.jsx`, at 24 fps):

| preset | Premiere keyframes | used for |
|---|---|---|
| `bar_sweep` | Motion › Crop Left 100 → 0 over `sweep_f` (default 6 f) after `delay_f` (default 1 f), so the reveal runs right-to-left | brand boxes behind statements, hooks, terms, keyword captions |
| `text_pop` | Opacity 0 → 100 in 2 f, Scale 90 → 100 in 4 f | text layers |
| `slide` | Position +60 px → 0 in 5 f, Opacity 0 → 100 in 4 f | checklist items, each starting at its spoken word |
| `push` | Opacity 0 → 100 in 6 f, Scale 100 → 103 across the clip | full-screen B-roll card |
| `card` | Opacity 0 → 100 over `fade_in_s`, Scale 96 → 100 | closing name card (glass) |
| `flash` | Opacity 0 → peak (90) → 0 | flash transition |
| other / `fade` | Opacity 0 → 100 in 5 f | logo outro |

All presets except `flash` add an Opacity fade-out over `fade_out_s` (at most ⅓ of the clip). Keyframe API: `setTimeVarying(true)`, then
`addKey(t)` and `setValueAtKey(t, v, true)`. Times are relative to the clip's **inPoint**.

## Verified API facts
- Stereo media is two mono channels. The XML must use mono clip pairs **and** Premiere's track attributes
  (`TL.SQTrack…`, `Panner…`, `premiereTrackType="Stereo"`, `currentExplodedTrackIndex`, `totalExplodedTrackCount`).
  Without them every audio clip is dropped silently. Link `trackindex` values are absolute.
- `qe…exportFramePNG` needs the CTI **timecode string**. Given ticks, it silently exports frame 0.
- An imported XML sequence registers a moment later, so poll for it (`waitSeq`).
- `track.name = …` works. Motion has keyframable Crop Left/Top/Right/Bottom.
- Premiere ticks = 254016000000 per second. Sequence frame = round-half-up of absolute ms × 24 / 1000, so timing never drifts.

## `reel ppro-frames`
Exports PNGs of Premiere's own render of the timeline (about 70 % into every event, plus spot times) into a **fresh folder for each
run**, `08_quality_control/premiere_frames/run-<time>/`, together with a labelled `_sheet.jpg` (timecode + event + template).
Only judge frames from the run you just made. Older run folders are history: a stale frame once showed a glass card that had already been removed.
Right after a project opens, Premiere may still be loading media and export its "Media pending" slate instead of the
picture (4 of 17 frames in a field test). `ppro-frames` detects those frames (`lib/media_pending.py`), waits and exports
them again (`--pending-retries`, default 3; `--pending-wait`, default 5 s, doubling), and lists any that are still the
slate under `media_pending` / `pending_frames` with `ok: false`. They are left out of the sheet: a slate is neither a pass
nor a fail. Before the export it first polls one frame into a scratch folder until it shows the picture (up to 30 s,
`media_wait` in the result).

Bridge 3.1.1 queue rules: a job carries `expires_at` (the bridge never starts it later), a job not started in time is
cancelled, the result timeout starts when the bridge claims the job, one build or frame export runs at a time
(`ppro-queue/.build.lock`), and a running bridge of another version is refused ("restart Premiere to load bridge
3.1.1"). Only the hidden background copy works the queue; the visible panel shows its state.

## Not scriptable: the editor does these
- Final mix, licensed music, render or export.
- Optional: frosted backdrop blur under the closing glass card (Adjustment Layer + Gaussian Blur masked to the card).

## Fallback: standalone XML
If the bridge can't run, `reel premiere` writes `07_premiere/interchange/<ID>_<PREFIX>_EDIT.xml` with the graphics as clips.
The editor uses File › Import, and the preview settings must then be set by hand (Sequence › Sequence Settings). This XML has no keyframe animation.
