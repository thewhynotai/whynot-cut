---
name: status
description: "Where a video stands, with evidence and no changes: \"is it done?\", \"what's left before I send it?\", \"can I render now?\", «جاهز؟», «خلاص جاهز؟»."
argument-hint: "[clip id] [client folder]"
allowed-tools: Bash(reel *), PowerShell(reel *)
---

# Status check (read-only)

Answer in the editor's language. The editor only ever does three things: **drop files**, **say what you want** and
**approve the plan**; say which of them (if any) each video waits for. Never name internal engine steps or "Gate 0/1/2" to them.
A one-clip answer always uses the three headings **Verified** · **Not verified** · **Needs you** (in Arabic «اتأكدت منه» ·
«ما اتأكدتش منه» · «محتاج منك», as in the output style), even when the engine could not run: the editor reads every status the same way.

## No clip named: every client at once
With no clip id (no arguments, or "what's waiting?" / «إيه اللي مستنيني؟»): run `reel board` in this message and
show its table as it is (one row per video: client, video, state, next step; Arabic client names stay as they are).
**Pass `--lang` for the language the editor is writing in** (`ar` when they write Arabic, `en` when they write
English), so the table and your words agree; without it the table follows settings `language` (Arabic unless set).
Finished videos are folded into one "+N done" row per client (`reel board --all` lists them one by one).
```bash
reel board --lang <ar|en>
```
Lead with the rows in state "waiting for you" (approve the plan, pick the reels, or say "continue <id>": nothing runs
until they do), then "blocked", then the new ones ("say 'edit the new videos'"). "In progress" means a session is
working in that client right now. For one client only add `--root "<CLIENT_FOLDER>"`. `reel board --json` gives the same
data as a document (`board: 1`, fields in the engine's `lib/board.py`), the same data the WhyNot Cut panel in Premiere
shows; use it when you need a field the table leaves out. Exit 1 with `ok: false` means no clients folder is set (or it
cannot be reached): say so and offer `/whynot-cut:start` or `/whynot-cut:preferences`. `truncated: true` means the scan
was cut short (very many clients or a slow drive): offer the board of one client. Stop here unless they ask about one
video.

## One clip: is it ready?
1. Run, in this message, so the evidence is fresh:
   ```bash
   reel next --root "<CLIENT_FOLDER>" --video-id <ID>
   reel qc   --root "<CLIENT_FOLDER>" --video-id <ID>
   ```
   `next` lists `stale` steps: anything whose inputs changed after it ran (e.g. audio re-cleaned after the plan).
   A stale step means the earlier "done" no longer holds. `reel status --root "<CLIENT>" --video-id <ID>` prints the
   project's status record itself (status, history, blockers). Both name a `parked_previous` Premiere project (a
   build stopped between parking the old `.prproj` and saving the new one; its `how` says how to rename it back) and
   `version_warnings` (a plan compiled by another engine version: re-run `reel plan`).
2. Read these and compare their timestamps (a verdict older than the latest build is stale). They are all under
   `<CLIENT_FOLDER>/output/projects/<ID>/`: list that folder (most file names don't contain the clip id, so a search
   by name finds only the raw clip). If the engine can't run, these files are your only evidence; say so.
   - `08_quality_control/qc-results.json` and `validation-report.md`
   - `08_quality_control/visual-verification.json` (verdict and date)
   - `07_premiere/ppro-build-result.json` (read-back checks)
   - `01_analysis/plan-approval.json` (still matches the current plan? `via: panel` = approved from the panel, once it offers that)
   - `02_transcription/subtitle-review.md` (unconfirmed words)
   - `01_analysis/medical-content-review.md` (approvals pending)
   - `06_audio/dialogue/dialogue-clean-report.json` and `cut-verification.json`
   - `08_quality_control/preview/preview-result.json` (a preview newer than the plan, for the editor to watch)
   - Podcast episode: `reel episode-next --root "<CLIENT>" --episode <EP>` (episode steps, stale steps, its reels'
     status) and `publish/publish-validation.json` (publish package checked?).
   - Motion video (`<EP>_<ID>_MO`): `reel next` lists the motion steps and stale steps; read the build result's
     read-back comparison, the render result, and the newest After Effects frames sheet with its recorded verdict.
     A build without read-back (`--script-only`/`--run-script`) is Not verified.
3. Answer in the report format:
   - **Verified**: only what the commands you just ran or the files you just read prove. Name the evidence.
   - **Not verified**: anything stale or unchecked, and why.
   - **Needs you**:
     - approve the plan / pick the reels, when that is the next step
     - words to confirm by ear (the editor records the check with `reel transcript-verify --by editor --note "…"`;
       until then those words stay off graphics)
     - medical approvals
     - music
     - final mix and render

Say "ready to send" only if `qc` passed just now **and** nothing in "Needs you" blocks it. Don't fix anything here. If something is
broken, say what and offer `/whynot-cut:revise` or `/whynot-cut:edit`.
In your own messages, tables and file names, «الدكتور/الدكتورة» and he/she come only from people[] (reel-profile
`profile.json`). Until a person's gender is known write «د.» or the name.
