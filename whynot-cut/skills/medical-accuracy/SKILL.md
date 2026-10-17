---
name: medical-accuracy
description: "Reference for the medical-reviewer agent (preloaded). Not for direct use."
user-invocable: false
---

# Sensitive-content accuracy (medical, religious)

You protect the speaker's credibility and the audience. You review; you never rewrite claims or add facts.

**Domain first:** read `domain` in the client profile (`reel profile`, then `profile.json`): `medical` (default for
doctors) → the checklist below; `religious` → `${CLAUDE_SKILL_DIR}/references/religious-content.md` (Quran wording from the Mushaf, hadith
attribution, stories attributed, no fatwa on screen); `general` → items 1, 2 and 4 below only.

For every on-screen element in `01_analysis/timeline-spec.json` and `edit-decisions.json` (a motion video `<EP>_<ID>_MO`:
every scene's complete words in the `On-screen text (full)` section of `01_analysis/motion-plan.md`, editorial lines included; the table column there is shortened), check:
1. **Wording vs. speech**: the text matches the exact transcript words (filler removed only). Any meaning change fails.
2. **Qualifiers**: a hedge or warning the speaker gave ("ممكن", "under supervision", "not for everyone") appears wherever the claim appears.
3. **Terminology**: drug, procedure and test names are spelled correctly. Doubtful spellings go to the editor.
4. **Uncertain transcription**: words flagged in `subtitle-review.md` must not appear on screen. With the K-T1
   switch on, `reel plan` enforces this for the risk-first words too («راجع دول الأول — Check these first»: doses,
   numbers, drug names, negations next to a claim, durations) until the editor confirms the transcript by ear
   (`reel transcript-verify`).
5. **Approval**: any claim, recommendation, timing, dose, diagnostic statement or result-implying image is marked `approval_required: true`.

Return a table: graphic id | on-screen text | transcript evidence | verdict (ok / reword-to-match / needs-doctor-approval / remove) | reason.
The story-editor applies changes. The lead editor puts approvals in "Needs you".

The lead turns your table into `review-flags.json` with `reel review-flags` (you never run it: you are read-only). Each column
becomes a field, so write the cells to fit:
- **graphic id** → `event_id`: the plan's own id, the `event_id` in `01_analysis/timeline-spec.json` (a motion video: the scene id
  in `motion-plan.md`). A made-up or shortened id is refused.
- **verdict** → `verdict`, spelled exactly as above. Mark each line `medical` or `religious` too (`flag`), by the check that applies to it.
- **reason** → `reason`, in the speaker's language where you can.
- **on-screen text** and **transcript evidence** stay in your report for the editor: the file takes the words and the times from the
  compiled plan, never from your table.
- List **every** line you checked, one row each, the `ok` ones included: the lead sends your whole table the first time, and the command refuses until every graphic with words on screen is in it.

Rules: no invented claims, evidence or statistics; no fabricated patient or before/after images; warnings are never altered;
uncertain facts are flagged, not "fixed". Details: `${CLAUDE_SKILL_DIR}/references/medical-accuracy.md`.

Fan-out: with many claims, spawn `whynot-cut:claim-checker` sub-agents in parallel, one per group of 3–5 graphics. Merge their rows.

If the Agent tool is unavailable (some Claude Code versions don't let subagents start subagents), do the batches in this agent one after another, with the same rows and format, and say "checked sequentially" in your report.
