# After Effects build for motion videos

## Bridge
- One CEP bundle (`reel ppro-install`) serves Premiere (ppro-queue, `NHPP`) and After Effects (ae-queue, `NHAE`).
  After an install, restart After Effects once. `reel ae-status` shows the heartbeat (`host: AEFT`).
- The panel runs only scripts in `<engine home>/ae-scripts` (`nh_ae_bridge.jsx` loads `nh_ae_lib.jsx` and
  `nh_motion_lib.jsx` at top level). ExtendScript never writes files; the panel's Node side writes results, so AE's
  "Allow Scripts to Write Files and Access Network" is never needed.
- Every action runs with dialogs suppressed; a build refuses when AE holds unsaved work.

## Arabic capability probe (`reel ae-probe`, once per AE version)
Builds probe comps, reads them back, renders frames to view. Verified on After Effects 26.5 (Windows):
- Universal composer and RTL paragraph direction persist on the TextDocument; `fontObject` from `app.fonts` works.
- An expression selector "Based On: Words" maps `textIndex` inconsistently for RTL Arabic (diagnostic comps
  `index_map`, `reveal_step`), so motion videos reveal words with **one text layer per word**, chained right-to-left by
  `sourceRectAtTime` expressions (Arabic does not join across spaces, so shaping is unchanged). A guide layer (not
  rendered) keeps the whole line for editing and read-back. `word_layers_20/35/50/65` must show 1/2/3/4 words from the
  right, the 3rd emphasised.
- Record: `reel ae-probe --record ok|fail --word-order logical|visual --notes "<what the frames showed>"` (lead only).
- Letters disconnected in frames → the editor sets Preferences › Type › Text Engine "South Asian and Middle Eastern"
  and restarts AE (never changed by the plugin).

## Project structure
`NH_BRAND/BRAND_CONTROLS` (colours; matching layers follow them) · `NH_SCENES/<S##>_<type>` (one comp per scene) ·
`NH_PERSISTENT` (CAPTIONS, SPEAKER_BADGE) · `NH_ASSETS` · `MAIN_<id>` (background, scene layers with transitions,
persistent layers, DIALOGUE/MUSIC/SFX audio). All keys at `frame × comp.frameDuration` (no drift at 29.97/23.976).

## Read-back (after every build)
Per scene: frames in MAIN, every text layer's string, font (not substituted), composer, direction, box at the hero
frame inside the safe area and not overlapping, cue hash; plus `missingOrSubstitutedFonts`. Anything off → FAILED with
the exact reason; PROJECT_ASSEMBLED only when everything matches.

## Render and frames
`reel motion-render` (aerender on the saved .aep, "Best Settings" + the probe's output module, default "High Quality")
→ `render/<id>_MAIN.mov`, `<id>_motion.mp4`, `<id>_cover.jpg`; `--scenes S03,S05` re-renders pieces.
`reel motion-frames` → `08_quality_control/ae_frames/run-*/` with `frames.json` (what each frame should show) and
`_sheet.jpg`. Frame checklist: joined Arabic, right-to-left order, mid-reveal frames show the first words (rightmost),
no boxes or clipping, emphasis on the right word, icon fits the idea, mirrored arrows point the reading way, nothing in
the platform UI zones, readable contrast, brand colours.

## Without the bridge
`reel motion-build --script-only` writes a self-contained JSX (File › Scripts › Run Script File…);
`--run-script` hands it to AE with `AfterFX -r`. Both are unverified (no read-back): QC cannot pass. Like the bridge,
the script refuses (an alert in AE) while the open project has unsaved changes: the editor saves or closes it first.
`--run-script` checks first and returns REFUSED at once, naming the project; tell the editor, do not retry.
