---
name: fix-audio
description: "This skill should be used when the request is only about the dialogue audio — \"clean the audio\", \"clean her/his audio\", \"remove the noise/hum\", \"remove all pauses\", \"tighten the gaps\", \"audio sounds bad\", \"الصوت فيه دوشة\", \"شيل السكتات\". Runs the measured cleanup and pause removal with before/after evidence."
argument-hint: "[clip id] [--min-pause ms] [--pad ms]"
allowed-tools: Bash(reel *), PowerShell(reel *)
---

# Fix dialogue audio

Delegate to `audio-engineer` (`subagent_type: "whynot-cut:audio-engineer"`) with the client folder, video id, and any
editor numbers (minimum pause, breath pad). It runs `reel audio-clean` and reports:
- the channel plan (which mic per segment)
- speech-to-noise before and after, and integrated loudness
- spectrogram paths
- pauses removed (count and seconds) and the new duration
- `cut-verification.json`: missing words must be 0

Then:
- If pauses are to be removed from the edit, `global.remove_pauses` must be set in `edit-decisions.json`
  (story-editor, or you for this one key). Then run `reel plan`, then previews, then Gate 1, then the Premiere rebuild (see `/whynot-cut:revise`).
- Look at both spectrograms yourself before claiming an improvement.
- **You can't hear the audio.** Tell the editor to listen. Offer a gentler setting if it sounds processed:
  lower `nr` (24 → 16), or keep more pause (`--min-pause 400`).

Reference: `${CLAUDE_PLUGIN_ROOT}/skills/audio-craft/references/sound-design.md`.
