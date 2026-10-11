---
name: status
description: "Where a video stands, with evidence and no changes: \"is it done?\", \"what's left before I send it?\", \"can I render now?\", «جاهز؟», «خلاص جاهز؟»."
argument-hint: "[clip id] [client folder]"
allowed-tools: Bash(reel *), PowerShell(reel *)
---

# Status check (read-only)

1. Run, in this message, so the evidence is fresh:
   ```bash
   reel next --root "<CLIENT_FOLDER>" --video-id <ID>
   reel qc   --root "<CLIENT_FOLDER>" --video-id <ID>
   ```
   `next` lists `stale` steps: anything whose inputs changed after it ran (e.g. audio re-cleaned after the plan).
   A stale step means the earlier "done" no longer holds.
2. Read these and compare their timestamps (a verdict older than the latest build is stale):
   - `08_quality_control/qc-results.json` and `validation-report.md`
   - `08_quality_control/visual-verification.json` (verdict and date)
   - `07_premiere/ppro-build-result.json` (read-back checks)
   - `01_analysis/plan-approval.json` (still matches the current plan?)
   - `02_transcription/subtitle-review.md` (unconfirmed words)
   - `01_analysis/medical-content-review.md` (approvals pending)
   - `06_audio/dialogue/dialogue-clean-report.json` and `cut-verification.json`
   - `08_quality_control/preview/preview-result.json` (a preview newer than the plan, for the editor to watch)
   - Podcast episode: `reel episode-next --root "<CLIENT>" --episode <EP>` (episode steps, stale steps, its reels'
     status) and `publish/publish-validation.json` (publish package checked?).
3. Answer in the report format:
   - **Verified**: only what the commands you just ran or the files you just read prove. Name the evidence.
   - **Not verified**: anything stale or unchecked, and why.
   - **Needs you**:
     - words to confirm by ear
     - medical approvals
     - music
     - final mix and render

Say "ready to send" only if `qc` passed just now **and** nothing in "Needs you" blocks it. Don't fix anything here. If something is
broken, say what and offer `/whynot-cut:revise` or `/whynot-cut:edit`.
In your own messages, tables and file names, «الدكتور/الدكتورة» and he/she come only from people[] (reel-profile
`profile.json`). Until a person's gender is known write «د.» or the name.

## Motion mode (2.2)
For `<EP>_<ID>_MO` projects: `reel next` (motion steps and stale steps), the build result's read-back comparison, the
render result, the newest frames sheet and its recorded verdict, and `reel qc` run now. A build without read-back
(`--script-only`/`--run-script`) is Not verified.
