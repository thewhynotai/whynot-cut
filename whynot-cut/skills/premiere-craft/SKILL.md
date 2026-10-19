---
name: premiere-craft
description: "Reference for the premiere-builder agent (preloaded). Not for direct use."
user-invocable: false
---

# Premiere craft

```bash
reel ppro-status --root "<CLIENT>"                        # alive + ping. If not alive: Premiere running? restarted since install?
reel ppro-probe  --root "<CLIENT>"                        # what the bridge's host reports back (version, project, API); for diagnosis
reel serve status                                         # the engine the Premiere panel talks to (session start runs it; `reel serve ensure` starts it)
reel status      --root "<CLIENT>" --video-id <ID>        # the project's status record (status, history, blockers, parked_previous)
reel ppro-build  --root "<CLIENT>" --video-id <ID> [--force]   # needs the CURRENT plan approved by the editor
reel premiere    --root "<CLIENT>" --video-id <ID>        # fallback standalone XML when the bridge can't run
```
- `--force` closes the open project in Premiere and keeps the previous file as `*_prev_<time>.prproj`. Make sure the editor
  has no unsaved work in it, and ask if unsure. Never delete the backups.
- **Success** means status `PRPROJ_BUILT` and every check in `07_premiere/ppro-build-result.json` is true:
  - the project was saved this run
  - codec ProRes 422 LT, 1080×1920, 24 fps
  - linear colour ON, max bit depth OFF, max render quality OFF
  - all graphics placed
  - dialogue on A1/A2
  - only when the plan asked for them: `punch_ins_eased` (every eased move has its smooth-zoom keys on Motion Scale
    and Position) and `fades_applied` (the black matte sits over each picture fade window with its keys; the sound
    fade keyed the dialogue)

  `PRPROJ_BUILT_WITH_ISSUES` is not success. Report exactly which checks failed.
- **Smooth zoom and fades** (T4.1) come from the client's `reel-profile/style.json`. `reel plan` writes them into the
  timeline spec, and the build only applies what the approved plan holds.
  - `camera.ease_ms`: the ease in/out of each story-editor punch_in. Default 250. Set `0` for hard punches. A
    slow_push always pushes across its whole piece.
  - `fades: {video_in_ms, video_out_ms, audio_in_ms, audio_out_ms}`: fades at the reel's start and end. Default 0 = off.
    The picture fades as one black layer over everything; the sound fade moves the dialogue and music, never the SFX.

  punch_out, reframe, jump-cut zoom masks, punches that land on a cut or next to another shot, and punches in 4:5
  window framing stay hard on purpose. A plan written before this update keeps its hard punches until it is planned
  again. If the editor wants a different feel,
  change `style.json`, then `reel plan` and get the plan approved again. Never hand-edit the keys in the spec.
  The build result names `qc_frames` (the middle of every ease); `reel ppro-frames` exports them, so look at those.
  The read-back says "bezier (set, not read back)": the bezier was SET on every key. Premiere's scripting cannot
  read the interpolation back, so the curve itself is checked live, not claimed as verified. The native caption
  track sits above the black matte, so its cues are trimmed where the picture is past half way to black (the result's
  warnings say how many). The XML fallback (`reel premiere`) has no smooth zoom and no fades, and says so.
- The sequence settings are the editor's house spec (`config/defaults/sequence-settings.json`). Don't change them.
- `EDITOR_CHANGES_PRESENT` means the editor saved changes in Premiere after the last build. Stop and report it to the lead.
  `--replace-edited` is only for when the editor explicitly agrees that their manual edits won't carry over.
- Nothing built is never exit 0: `EXISTS` (the project is already there; `--force` rebuilds) and
  `EDITOR_CHANGES_PRESENT` / `PREVIOUS_PARKED` are refusals (exit 2, with `how`); `MISSING_GRAPHICS` is a failure
  (exit 1, `ok: false`).
- If `ppro-build` returns `MISSING_GRAPHICS`, run previews. If it returns `BRIDGE_NOT_RUNNING`, the editor must start Premiere.
  Don't try to start or quit Premiere yourself unless the editor asked. It may hold their unsaved work.

Full details, verified API facts and animation presets: `${CLAUDE_SKILL_DIR}/references/premiere-assembly.md`.
Known failures: `${CLAUDE_PLUGIN_ROOT}/skills/edit/references/troubleshooting.md`.
