---
name: qc-craft
description: "Reference for the qc-reviewer agent (preloaded). Not for direct use."
user-invocable: false
---

# QC craft

You are the independent check. Assume nothing that you haven't seen.

```bash
reel ppro-frames --root "<CLIENT>" --video-id <ID>    # Premiere renders frames of its own timeline
reel qc          --root "<CLIENT>" --video-id <ID>    # structural checks + evidence gates
```
1. Build the expectation list from `01_analysis/timeline-spec.json`. For each event: id, template, timecode, the exact
   expected text (items and lines included), and whether captions should be hidden.
   `ppro-frames` prints the run folder and its `_sheet.jpg`. Use only that folder.
   **"Media pending" frames:** right after a project opens Premiere may export its placeholder for media that is still
   loading (a smooth colour field with "Media pending" in nine languages) instead of the picture. `ppro-frames`
   detects them, waits and re-exports them (`--pending-retries N`, `--pending-wait S`), and lists any that are still
   the slate under `media_pending` with `ok: false` (they are left out of the sheet and the `frames` count). Such a
   frame is neither a pass nor a fail: re-export (run `reel ppro-frames` again once Premiere has finished loading),
   never judge it, and report its rows as unchecked until a clean frame exists.
2. Fan out `whynot-cut:frame-inspector` sub-agents in parallel, 6–8 frames each. Give each its PNG paths with the matching expectation rows.
   Each frame passes only if all of these hold:
   - the text matches word for word, in RTL order (the first word on the right)
   - Arabic letters are joined
   - the face and eyes are clear
   - nothing is doubled (caption plus card)
   - it's inside the safe area
   - the colours are brand colours
   - the animation state makes sense (mid-sweep is fine at 70 % only if the bar is partly drawn on the right)
   - the style follows the profile (e.g. no glass except the closing card)
3. Also check:
   - the audio evidence: `dialogue-clean-report.json` shows speech-to-noise up, and `cut-verification.json` shows missing = 0
   - the pause cuts: the zoom changes at every jump cut, also inside a punch-in (`qc` checks the spec: "Every jump cut changes the zoom")
   - the build read-back checks are all true
4. Return a verdict table (frame | event | pass/fail/unsure | reason) and an overall recommendation, with the frame sheet path.
   **Don't record the verdict yourself.** The lead editor views the evidence and records it. A hook enforces this.

Red flags and the claim → evidence table: `${CLAUDE_SKILL_DIR}/references/verification.md`.

If the Agent tool is unavailable (some Claude Code versions don't let subagents start subagents), do the batches in this agent one after another, with the same rows and format, and say "checked sequentially" in your report.

Podcast reels: `qc` also checks that the first V1 clip starts at the reel's in-point in the episode and that the window lies inside the episode. In the frames, check each shot's face is in the picture and that wide shots frame the person speaking (`00_inputs/speakers.json`).

Motion videos (`<EP>_<ID>_MO`, built in After Effects): the frames come from `reel motion-frames` (the newest After
Effects frames sheet), not `ppro-frames`. `reel qc` on a motion project checks plan_valid, approval_current,
aep_fresh, readback, render, audio_sync (correlation ≥ 0.9, offset ≤ 1 frame), cut_proof, visual_verified (pass on
the newest frames sheet) and licenses; pending approvals are a warning. The lead records the verdict
(`reel verify --record --verdict pass|fail --notes "…"`) only after viewing the sheet.
