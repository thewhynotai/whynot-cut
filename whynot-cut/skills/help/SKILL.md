---
name: help
description: "What WhyNot Cut can do and which command to use: \"WhyNot Cut help\", \"what can it do\", \"which command edits a video\", «ايه أوامر WhyNot Cut». First time: /whynot-cut:start."
allowed-tools: Bash(reel *), PowerShell(reel *)
---

# WhyNot Cut help (fits where the editor is)

Answer in the editor's language. First find where they are, read-only:
1. `reel doctor`. If it returns `blocked: engine not installed` (or `reel` is not found), say only: run
   `/whynot-cut:start` (it sets everything up, step by step). Stop there.
2. `reel board --json` (every client in the clients folder, each video's state and next step; inside a client folder
   add `--root "<CLIENT_FOLDER>"`). No clients folder set (`ok: false`) → point to `/whynot-cut:start`.
3. For the video that waits for them (state `waiting_for_you`, else the newest `working` one) read its next step:
   ```bash
   reel next --root "<CLIENT_FOLDER>" --video-id <ID>
   ```
   (an episode: `reel episode-next --root "<CLIENT_FOLDER>" --episode <EP>`).

Then answer in this order, short:
- **Right now:** one or two lines from what you just read, in the editor's words, e.g. "C0239 waits for you to approve
  the plan", "2 new clips in Dr Karim: say 'edit the new videos'", "EP01: pick the reels". Use the item's `next_step`;
  never show the internal step names (AUTHOR, PLAYBACK, stage numbers, "Gate 0/1/2") to the editor.
- **The three things you do:** **drop files** into the client folder · **say what you want** ("edit the new videos")
  · **approve the plan** before anything is built. «حط الملفات · قول عايز إيه · وافق على الخطة».
- **The WhyNot Cut panel in Premiere** (Window › UXP Plugins › WhyNot Cut) shows the same videos and their state;
  the editor never types commands into it. Approving from the panel is coming in a next update: for now they approve
  here in the chat («وافق هنا في الشات»).
- Then this table, the one or two rows that fit right now marked:

| Say / run (قول أو شغّل) | What happens (اللي بيحصل) |
|---|---|
| `/whynot-cut:start` | first-time setup, step by step, until "drop your footage here" |
| "edit the new videos" · `/whynot-cut:autopilot` | edits every new clip in the client folder(s) |
| `/whynot-cut:edit C0239` | full edit of one clip: transcript → audio → story → graphics → preview → you approve the plan → Premiere → proof check |
| "make reels from this episode" · `/whynot-cut:podcast` | podcast episode → reels plan with timecodes and content types → you pick the reels → reels in Premiere, plus YouTube/social copy and thumbnails |
| "make a motion video from this part" · `/whynot-cut:motion` | an episode window's audio → an animated After Effects video: plan, animatic, you approve, After Effects build, render, proof check |
| `/whynot-cut:preview` | watchable MP4 of the planned edit (no Premiere needed) |
| `/whynot-cut:revise "1- … 2- …"` | applies editor comments, rebuilds, re-verifies, reports per comment |
| "is it ready?" · `/whynot-cut:status` | one clip: is it ready, with fresh evidence; no clip named: every client's videos in one table |
| `/whynot-cut:fix-audio` | dialogue cleanup and pause removal only |
| `/whynot-cut:new-client` | builds a new client's profile from their brand files and reference edits |
| `/whynot-cut:handoff` | handoff package for the editor or another computer |
| `/whynot-cut:preferences` | approval mode, language, transcription speed, clients folder |
| `/whynot-cut:setup` | install or repair the engine and the Premiere bridge |
| `/whynot-cut:adobe-extras` | After Effects / Photoshop graphics for a clip edit, only on request |

Where things go: brand files in `assets/`, raw clips in `data/Raw/`, reference edits in `data/References/`; results in
`output/projects/<clip>/` (Premiere project in `07_premiere/project/`, preview in `08_quality_control/preview/`, handoff
in `09_handoff/`). WhyNot Cut never changes `assets/` or `data/`. Clip edits are built in Premiere (graphics and
captions animated with Premiere keyframes; After Effects / Photoshop only on request); motion videos in After Effects.

Made by The Why Not AI · info@thewhynot.ai
