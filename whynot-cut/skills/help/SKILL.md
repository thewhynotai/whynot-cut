---
name: help
description: "What WhyNot Cut can do and which command to use: \"WhyNot Cut help\", \"what can it do\", \"which command edits a video\", «ايه أوامر WhyNot Cut». First time: /whynot-cut:start."
allowed-tools: Bash(reel *), PowerShell(reel *)
---

# WhyNot Cut cheat sheet

Run `reel doctor` (fast, read-only) and, inside a client folder, `reel inbox` so the answer fits the user's situation.
If `reel doctor` returns `blocked: engine not installed`, highlight only `/whynot-cut:start`. Otherwise show this
table, highlighting the one or two rows that fit right now:

| Say / run (قول أو شغّل) | What happens (اللي بيحصل) |
|---|---|
| `/whynot-cut:start` | first-time setup, step by step, until "drop your footage here" |
| "edit the new videos" · `/whynot-cut:autopilot` | edits every new clip in the client folder(s) |
| `/whynot-cut:edit C0239` | full edit of one clip: transcript → audio → story → graphics → preview → approval → Premiere → QC |
| "make reels from this episode" · `/whynot-cut:podcast` | podcast episode -> reels plan with timecodes and content types -> you pick -> reels in Premiere, plus YouTube/social copy and thumbnails |
| "make a motion video from this part" · `/whynot-cut:motion` | an episode window's audio → an animated After Effects video: plan, animatic, you approve, After Effects build, render, QC |
| `/whynot-cut:preview` | watchable MP4 of the planned edit (no Premiere needed) |
| `/whynot-cut:revise "1- … 2- …"` | applies editor comments, rebuilds, re-verifies, reports per comment |
| `/whynot-cut:status` | "is it ready?", with fresh evidence |
| `/whynot-cut:fix-audio` | dialogue cleanup and pause removal only |
| `/whynot-cut:new-client` | builds a new client's profile from their brand files and reference edits |
| `/whynot-cut:handoff` | handoff package for the editor or another computer |
| `/whynot-cut:preferences` | approval mode, language, transcription speed, clients folder |
| `/whynot-cut:setup` | install or repair the engine and the Premiere bridge |
| `/whynot-cut:adobe-extras` | After Effects / Photoshop graphics for a clip edit, only on request |

Where things go: brand files in `assets/`, raw clips in `data/Raw/`, reference edits in `data/References/`; results in
`output/projects/<clip>/` (Premiere project in `07_premiere/project/`, preview in `08_quality_control/preview/`, handoff
in `09_handoff/`). WhyNot Cut never changes `assets/` or `data/`.

The three things you do: **drop files** into the client folder, **say what you want** ("edit the new videos"),
and **approve the plan** before anything is built. Clip edits are built in Premiere; motion videos in After Effects.

Made by The Why Not AI · info@thewhynot.ai
