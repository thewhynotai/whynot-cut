---
name: preview
description: "Render a watchable MP4 of the planned edit, no Premiere needed: \"show me the edit\", \"make a preview video\", \"quick MP4\", «ورّيني الفيديو», «عايز أشوف المونتاج»."
argument-hint: "[clip id] [--width 540|720|1080]"
allowed-tools: Bash(reel *), PowerShell(reel *)
---

# Preview video

```bash
reel preview-video --root "<CLIENT>" --video-id <ID> [--width 720]
```
It needs a compiled plan and the stills (`reel plan`, `reel previews`). It writes
`<CLIENT>/output/projects/<ID>/08_quality_control/preview/<ID>_preview.mp4` (540×960 H.264 by default) plus
`preview-result.json`. Failure comes back as `ok: false` with `error` and exit code 1, so read the JSON.

What is in it, mirroring the Premiere build: the footage pieces after pause removal with the zoom change at every jump
cut and the punch-ins (scale and position per piece), every graphic and caption layer with its Premiere animation
preset (bar sweep, text pop, slide, push, card, flash), the cleaned dialogue (or the camera audio if cleanup hasn't run,
which the result says) and the SFX. A small "preview" label keeps anyone from mistaking it for the final render.

After rendering:
- Give the path, length and render time. Offer to open it: `open "<mp4>"` on macOS; `explorer.exe "<mp4 with
  backslashes>"` on Windows.
- The video can't be watched from here, so tell the editor what to look and listen for: the hook, each graphic's timing,
  the cut points (`cut-verification.json` lists spots to listen to), caption collisions.
- For a visual check, extract a few frames with the engine's own ffmpeg (path from `reel doctor` → `ffmpeg`; never
  install another) and view them:
  `"<ffmpeg>" -ss <t> -i "<mp4>" -frames:v 1 "<CLIENT>/output/projects/<ID>/08_quality_control/preview/frame_<t>.png"`.
  For a full check use `/whynot-cut:status`.
- It is a proxy: not the deliverable, not proof of the Premiere build (QC uses Premiere's own frames).

If it fails with "graphics stills missing", run `reel previews`; "timeline-spec.json missing", run `reel plan`.
