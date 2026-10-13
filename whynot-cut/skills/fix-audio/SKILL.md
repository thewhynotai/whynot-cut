---
name: fix-audio
description: "One audio-only request, no other comments: \"clean the audio\", \"remove the noise\", \"remove all pauses\", «الصوت فيه دوشة», «شيل السكتات». Measured, with before/after proof."
argument-hint: "[clip id] [--min-pause ms] [--pad ms]"
allowed-tools: Bash(reel *), PowerShell(reel *)
---

# Fix dialogue audio

**Which skill:** this one when the editor's request is only about the dialogue audio (noise, hum, loudness, pauses,
breaths). A list of two or more comments, or any comment about graphics, wording, timing or cuts, goes to
`/whynot-cut:revise` (it sends the audio part to the same agent).

Delegate to `audio-engineer` (`subagent_type: "whynot-cut:audio-engineer"`) with the client folder, video id, and any
editor numbers (minimum pause, breath pad). It runs `reel audio-clean`; what that command does (channel choice, hum
notches, denoise or not, loudness, pause detection, the no-lost-words proof) is described once, in
`${CLAUDE_PLUGIN_ROOT}/skills/audio-craft/SKILL.md`. The agent reports:
- the `decisions` (channels, hum notches, denoise or why not)
- speech-to-noise before and after, and integrated loudness
- pauses removed (count and seconds), the old and new duration
- `cut-verification.json`: `ok`, coverage, missing words (must be 0)
- the spectrograms it viewed

Then:
- If pauses are to be removed from the edit, `global.remove_pauses` must be set in `edit-decisions.json`
  (story-editor, or you for this one key). Then run `reel plan`, then previews, then show the changed plan for the
  editor to approve, then the Premiere rebuild (see `/whynot-cut:revise`). Motion videos (`<EP>_<ID>_MO`): after
  `audio-clean`, the motion plan is compiled again (`reel motion-plan`), see the motion route in `/whynot-cut:revise`.
- Look at both spectrograms yourself before claiming an improvement.
- **You can't hear the audio.** Tell the editor to listen. Offer a gentler setting if it sounds processed:
  lower `--nr` (24 → 16), or keep more pause (`--min-pause 400`).

Reference: `${CLAUDE_PLUGIN_ROOT}/skills/audio-craft/references/sound-design.md`.
