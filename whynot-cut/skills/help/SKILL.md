---
name: help
description: "This skill should be used when the user asks what WhyNot Cut can do or which WhyNot Cut command to use — \"WhyNot Cut help\", \"what can WhyNot Cut do\", \"list the WhyNot Cut commands\", \"how does this plugin work\", \"which command edits a video\", \"ايه أوامر WhyNot Cut\", \"مساعدة في المونتاج\". It gives a short cheat sheet tailored to where the user is. For first-time setup, /whynot-cut:start applies."
allowed-tools: Bash(reel *), PowerShell(reel *)
---

# WhyNot Cut cheat sheet

Run `reel doctor` (fast, read-only) and, inside a client folder, `reel inbox` so the answer fits the user's situation.
If `reel doctor` returns `blocked: engine not installed`, highlight only `/whynot-cut:start`. Otherwise show this
table, highlighting the one or two rows that fit right now:

| Say / run | What happens |
|---|---|
| `/whynot-cut:start` | first-time setup, step by step, until "drop your footage here" |
| "edit the new videos" · `/whynot-cut:autopilot` | edits every new clip in the client folder(s) |
| `/whynot-cut:edit C0239` | full edit of one clip: transcript → audio → story → graphics → preview → approval → Premiere → QC |
| "make reels from this episode" · `/whynot-cut:podcast` | podcast episode -> reels plan with timecodes and content types -> you pick -> reels in Premiere, plus YouTube/social copy and thumbnails |
| `/whynot-cut:preview` | watchable MP4 of the planned edit (no Premiere needed) |
| `/whynot-cut:revise "1- … 2- …"` | applies editor comments, rebuilds, re-verifies, reports per comment |
| `/whynot-cut:status` | "is it ready?", with fresh evidence |
| `/whynot-cut:fix-audio` | dialogue cleanup and pause removal only |
| `/whynot-cut:new-client` | builds a new client's profile from their brand files and reference edits |
| `/whynot-cut:handoff` | handoff package for the editor or another computer |
| `/whynot-cut:preferences` | approval mode, language, transcription speed, clients folder |
| `/whynot-cut:setup` | install or repair the engine and the Premiere bridge |
| `/whynot-cut:adobe-extras` | After Effects / Photoshop output, only on request |

Where things go: brand files in `assets/`, raw clips in `data/Raw/`, reference edits in `data/References/`; results in
`output/projects/<clip>/` (Premiere project in `07_premiere/project/`, preview in `08_quality_control/preview/`, handoff
in `09_handoff/`). WhyNot Cut never changes `assets/` or `data/`.

Made by The Why Not AI · info@thewhynot.ai

## Motion mode (2.2)
`/whynot-cut:motion` — an episode window's audio → animated After Effects video: `reels-select --as motion`,
`motion-plan`, `motion-animatic`, Gate 1, `ae-status`/`ae-probe`, `motion-build`, `motion-render`, `motion-frames`,
`qc`. Icons: `motion-icons --search`; licensed illustration packs: `motion-library`.
