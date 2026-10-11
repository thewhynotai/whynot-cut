---
name: revise
description: "Editor feedback on an existing edit, two or more comments or any non-audio comment: \"make it punchier\", \"move the name card\", a numbered list, «ملاحظات على الفيديو». Rebuilds, re-verifies."
argument-hint: "\"<editor feedback>\" [clip id]"
allowed-tools: Bash(reel *), PowerShell(reel *)
---

# Revise from editor feedback

1. **Restate each comment** as a concrete, checkable change. "Remove all pauses" becomes `global.remove_pauses` (min 250 ms, pad 80 ms) plus re-verification that no words are lost.
   If a comment is a question ("did you make the text like the ref?"), answer it honestly first, with evidence, before changing anything.
   Only ask the editor when two readings would produce different edits.
2. **Route** each change to the agent that owns it:

   | Comment is about | Agent | Typical change |
   |---|---|---|
   | noise, hum, loudness, pauses, breaths | `audio-engineer` | `reel audio-clean` options; evidence |
   | wording, which moments get graphics, timing, cuts, glass/statement style | `story-editor` | `edit-decisions.json` (+ client `reel-profile/style.json` if it is a standing rule) |
   | how graphics or captions look or animate | `motion-designer` | template params or profile `graphics-templates.json`; previews |
   | transcript words | `transcript-editor` | `transcript-corrections.json` → `transcript-correct` |
   | medical wording | `medical-reviewer` (read-only) | approval list |

   Independent changes go out in parallel in one message.
3. If the comment is a **standing preference** ("always glass only at the end"), record it in the client's
   `output/client_database/reel-profile/style.json` and `notes.md`, so the next video follows it.
4. `reel plan` must compile, then previews, then `reel preview-video` (preferences `preview_video`) so the editor can
   watch the change. Summarise the changed plan for the editor (Gate 1); with preferences `approval: auto`, record the
   delegated approval citing the preferences file.
   If they already said "just do it", record the approval with `approve-plan --by delegated --note "<their words>"`.
5. **Protect the editor's own work in Premiere.** If `reel qc` shows "Premiere project unchanged since the pipeline build" as WARN,
   or `ppro-build` returns `EDITOR_CHANGES_PRESENT`, the editor has edited the project by hand. A rebuild starts from the plan, so those
   manual edits would not carry over. The old file is kept as `*_prev_<time>.prproj`. Tell them exactly that and let them choose:
   - rebuild anyway: `--force --replace-edited`, only with their explicit OK
   - or apply your change by hand in their project (give precise timecodes and values)
   - or rebuild and they redo their tweaks

   Also ask them to save before any rebuild, because `--force` closes the open project.
6. `premiere-builder` runs `ppro-build --force`, then `qc-reviewer` checks the frames, then you record the verdict, run `qc` and update the handoff.
7. Report **per comment**: what changed, the evidence (numbers, frames), and caveats. Use the report format from `/whynot-cut:edit`.
