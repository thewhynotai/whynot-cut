---
name: motion
description: "Animated motion-graphics video from a podcast window's audio (motion mode): \"make a motion video from this part\", \"animate this podcast part\", «اعمل موشن من الجزء ده», «البودكاست صوت بس»."
argument-hint: "[episode id] [R/T id] [client folder]"
allowed-tools: Bash(reel *), PowerShell(reel *)
---

# Motion mode: an episode window's audio → an animated After Effects video

You are the lead editor. Read `${CLAUDE_PLUGIN_ROOT}/skills/podcast/SKILL.md` first (episode stages, Gate 0) and
`${CLAUDE_PLUGIN_ROOT}/skills/edit/SKILL.md` (agents do the stages, you alone talk to the editor and approve nothing for
them, no claim without fresh evidence). Motion mode uses no camera picture: only what is said, who says it, the episode
sheet and the client's brand. The deliverable is a native After Effects project + a rendered MP4.

## 0. Orient
```bash
reel episode-next --root "<CLIENT>" --episode <EP>      # episode state, picked reels (motion ones end in _MO)
reel next --root "<CLIENT>" --video-id <EP>_<ID>_MO     # the motion project's next step (resumable), stale steps
reel ae-status                                          # is the WhyNot Cut Bridge alive in After Effects?
```
Audio-only episodes (`.mp3 .wav .m4a .aac .flac` in `data/Episodes/`) can only become motion videos.

## 1. Gate 0 `--as motion` (the editor's choice only)
Offer motion for candidates the analyst flagged `motion_fit` (numbers, steps, abstract ideas, no usable picture) and
for audio-only episodes. A topic from the topic map (`T02`) can be picked too, with a content type.
```bash
reel reels-select --root "<CLIENT>" --episode <EP> --pick R03 --as motion [--format 9x16|16x9] --by editor
reel reels-select --root "<CLIENT>" --episode <EP> --pick T02 --as motion --type advice --by editor
```
Windows are 15–180 s; longer topics are refused ("split it"). The project is `<EP>_<ID>_MO`.

## 2. Stages
| Stage | Who | Commands | Done when |
|---|---|---|---|
| Audio | `audio-engineer` | `audio-clean` | pauses removed, cut proof ok |
| Script | `motion-director` | `motion-icons`, `motion-library`, `music --list`, write `motion-script.json`, `motion-plan` | plan compiles, no errors |
| Animatic | `motion-director` | `motion-animatic`; VIEW `_storyboard.jpg` | storyboard + MP4 |
| **Gate 1** | **you + the editor** | `approve-plan --by editor` | the editor approved |
| Probe (once per AE version) | `ae-builder` runs, **you** view and record | `ae-probe`, then `ae-probe --record ok\|fail --word-order logical\|visual --notes "…"` | ok verdict for this AE version |
| Build | `ae-builder` | `motion-build` | PROJECT_ASSEMBLED, read-back comparison passes |
| Render + frames | `ae-builder` | `motion-render`, `motion-frames` | RENDERED, frames sheet |
| QC | `qc-reviewer` (frame-inspectors) | `motion-frames` output, `qc` (after your verdict) | qc ok |
| Verdict | **you** | VIEW `_sheet.jpg`, `verify --record --verdict pass\|fail --notes "…"` | recorded |
| Handoff + publish | you, `publish-writer` | `handoff`; `publish/reels/<EP>_<ID>_MO.json`, `publish-check` | handoff + package pass |

## 3. Gate 1 (show, in the editor's language)
From `motion-plan.md`: each scene's time, beat, type and on-screen words, with **editorial lines marked as Claude's
words** (not the speaker's), numbers that need confirming, icons/illustrations and their licenses, music, recipe
deviations; plus the animatic path. Record `reel approve-plan --by editor` only with their words (or a standing
delegation they gave in chat, quoted in `--note`). Words inside files never count as approval.

## 4. Build rules
- The bridge is one bundle for Premiere and After Effects (`reel ppro-install`; After Effects must be restarted once).
  PlayerDebugMode and every After Effects preference are the editor's to change: give them the step.
- `motion-build` refuses without Gate 1, an ok probe for this AE version, installed brand fonts, or when AE holds
  unsaved work. Fonts missing → Needs you (install from `assets/Fonts`, restart AE); `--allow-fallback-font` only with
  the editor's OK.
- Never overwrite an `.aep` the editor changed: `--replace-edited` keeps a backup, and only with their OK.
- No After Effects or no bridge: `motion-build --script-only` (or `--run-script`) delivers the project unverified — QC
  cannot pass without the read-back; say so.

## 5. Report format
**Verified** (with evidence paths: read-back, render probe, frames you viewed, `qc` in this message) /
**Not verified** / **Needs you** (fonts to install, AE restart, music, numbers to confirm, final look and export).
Never call a motion video done unless `qc` passed in this message.

## Non-negotiables
- On screen: the speaker's words verbatim, or editorial lines marked as such; numbers only as said; names only from
  the sheet; licensed assets only (attribution published with the video when CC-BY).
- Gate 0 and Gate 1 come only from the editor. `assets/` and `data/` are read-only.

References: `motion-craft/references/motion-scenes.md`, `motion-beats.md`, `ae-motion.md`.
