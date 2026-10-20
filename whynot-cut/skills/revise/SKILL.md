---
name: revise
description: "Editor feedback on an edit or motion video: a list of 2+ comments, or any non-audio one: \"make it punchier\", \"move the name card\", «ملاحظات على الفيديو», «عدّل ده». Rebuilds, re-verifies."
argument-hint: "\"<editor feedback>\" [clip id]"
allowed-tools: Bash(reel *), PowerShell(reel *)
---

# Revise from editor feedback

**Which skill:** this one for a list of two or more comments, or any comment about graphics, wording, timing, cuts or
scenes. A single request that is only about the dialogue audio ("clean the audio", "remove all pauses") is
`/whynot-cut:fix-audio`. A project whose id ends in `_MO` is a motion video: follow **Motion videos** below, not
**Clip videos (Premiere)**.

Every `reel` command for a project takes `--root "<CLIENT_FOLDER>" --video-id <ID>` (never a bare clip id), e.g.
`reel plan --root "<CLIENT_FOLDER>" --video-id C0238`. Other options come from `reel <command> --help` or the owning
agent: never guess an option name.

**Read `reel brief`, not the JSON files.** `reel brief --root "<CLIENT>" --video-id <ID>` prints the item's state, key
numbers, open items and next step in at most 1,500 tokens. Read it instead of opening `project-status.json`,
`qc-results.json`, `review-flags.json` or the timeline spec; open a file only when the brief points at it. Agents
(story-editor, reviewers, proofreaders) read the compact transcript for the words (context, review, claims):
`02_transcription/transcript.compact.md` (segment ids, start, words), not `transcript.json`; word ids and exact times
still come from `words.json` (proofreader chunks, story-editor timings, `cut_words`). `reel transcript-compact`
refreshes it when the brief says it is stale or missing.

## Clip videos (Premiere)
1. **Restate each comment** as a concrete, checkable change. "Remove all pauses" becomes `global.remove_pauses` (min 250 ms, pad 80 ms) plus re-verification that no words are lost.
   If a comment is a question ("did you make the text like the ref?"), answer it honestly first, with evidence, before changing anything.
   Only ask the editor when two readings would produce different edits.
2. **Route** each change to the agent that owns it:

   | Comment is about | Agent | Typical change |
   |---|---|---|
   | noise, hum, loudness, pauses, breaths | `whynot-cut:audio-engineer` | `reel audio-clean` options; evidence |
   | wording, which moments get graphics, timing, cuts, glass/statement style | `whynot-cut:story-editor`, then `whynot-cut:medical-reviewer` for any wording change (below) | `edit-decisions.json` (+ client `reel-profile/style.json` if it is a standing rule) |
   | how graphics or captions look or animate | `whynot-cut:motion-designer` | template params or profile `graphics-templates.json`; previews |
   | transcript words | `whynot-cut:transcript-editor` | `transcript-corrections.json` → `transcript-correct` |
   | medical or religious wording | `whynot-cut:medical-reviewer` (read-only) | approval list |

   Independent changes go out in parallel in one message.
   **Any change to on-screen wording** (the story-editor's edits to graphics, captions or statements, whatever the
   topic) gets a `whynot-cut:medical-reviewer` re-review of the changed items (it re-reads the changed elements of
   `01_analysis/timeline-spec.json` against the transcript) after `reel plan` compiles and **before** step 4 shows the
   changed plan for approval; it re-reviews the changed items only. Its approval list goes into what you show the editor.
   Then record its new rows: `reel review-flags --root "<CLIENT>" --video-id <ID> --from -` with only the rows it reviewed this
   time as JSON on standard input, with only the flags the client's domain checks (`medical`; a religious client:
   `religious` and `medical`; a graphic with no words on screen is left out). The engine does the bookkeeping: a graphic
   reviewed before with the same id and the same words stays covered by itself, and its earlier flag carries over. It
   refuses, and writes nothing, until every graphic with words on screen is covered; when an earlier flag left its
   graphic (its words changed, or its id was reused or removed), until every new or changed graphic is reviewed for
   that same flag; and while a flag stays on its graphic, until every new graphic with an exact copy of its words is. It
   names what is missing ("G5, G6 have not been reviewed"; "G6 is new or changed since G2's medical flag: review G6 for
   medical"), so an edited, renumbered, split or merged graphic can never show clean: send those rows back to the
   reviewer, then run the command again. Tell the story-editor to **keep graphic ids stable**: an edited graphic keeps its id, a new one gets the
   next unused id, nothing is renumbered. A graphic that is truly gone is reported by the command as `dropped`, and an
   earlier flag now passed as ok on the same words as `cleared`: mention both to the editor.
3. If the comment is a **standing preference** ("always glass only at the end"), record it in the client's
   `output/client_database/reel-profile/style.json` and `notes.md`, so the next video follows it. Four of them are
   knobs `reel plan` applies by itself (client-craft lists them):
   - "bigger captions" «الكابشن أكبر» → `caption_size_px`;
   - "keep the captions during the hook" «سيب الكابشن على الهوك» → `captions_during_hook: "show"` (a client
     setting only: for one clip, the story-editor edits that clip's `captions_hidden_during` list). After Effects
     captions follow it now; Premiere captions follow it after the next WhyNot Cut update, so tell the editor that
     until then the Premiere captions stay hidden under the hook;
   - "no click on the title" «من غير صوت على العنوان» → `hook_title_sfx: false`;
   - "the highlight colour" «لون التمييز» → `highlight_colour`.

   For one clip only, the story-editor sets the size, sound or colour knob in that clip's edit-decisions `global`
   instead. Then run `reel plan` again: builds follow the compiled plan, not the live `style.json`.
4. `reel plan` must compile, then previews, then `reel preview-video` (preferences `preview_video`) so the editor can
   watch the change. Summarise the changed plan for the editor to approve; with preferences `approval: auto`, record
   the delegated approval citing `_where.approval` from `reel settings`.
   If they already said "just do it", record the approval with `reel approve-plan --by delegated --note "<their words>"`.
5. **Protect the editor's own work in Premiere.** If `reel qc` shows "Premiere project unchanged since the pipeline build" as WARN,
   or `ppro-build` returns `EDITOR_CHANGES_PRESENT`, the editor has edited the project by hand. A rebuild starts from the plan, so those
   manual edits would not carry over. The old file is kept as `*_prev_<time>.prproj`. Tell them exactly that and let them choose:
   - rebuild anyway: `reel ppro-build --force --replace-edited`, only with their explicit OK
   - or apply your change by hand in their project (give precise timecodes and values)
   - or rebuild and they redo their tweaks

   Also ask them to save before any rebuild, because `--force` closes the open project.
6. `whynot-cut:premiere-builder` runs `reel ppro-build --force` (the previous project is kept as
   `*_prev_<time>.prproj`; tell the editor), then `whynot-cut:qc-reviewer` checks the frames, then you view the frame
   sheet, record the verdict, run `reel qc` and update the handoff.
7. Report **per comment**: what changed, the evidence (numbers, frames), and caveats. Use the report format from `/whynot-cut:edit`.

## Motion videos (`<EP>_<ID>_MO`)
A motion video is built in After Effects from the motion plan, never with `ppro-build`. Route its comments like this
(the full playbook is `/whynot-cut:motion`). First read `01_analysis/motion-script.json` yourself and map each comment
to the scene it means (e.g. "the second scene" = `S02`, with its current timing and style), so every routed change names
a scene id.

| Comment is about | Who | Commands |
|---|---|---|
| on-screen words, scenes, beats, timing, icons, illustrations, music | `whynot-cut:motion-director` | revise `01_analysis/motion-script.json`, then `reel motion-plan` until no errors, then `reel motion-animatic` |
| noise, hum, pauses | `whynot-cut:audio-engineer`, then `whynot-cut:motion-director` | `reel audio-clean`, then `reel motion-plan` again (the scenes follow the new timing) and `reel motion-animatic` |
| how a scene looks or moves (layout, style, colours, animation) | `whynot-cut:motion-director` | change the scene choices and style in `01_analysis/motion-script.json` (a standing rule: the client's `output/client_database/reel-profile/motion.json`), then `reel motion-plan` and `reel motion-animatic`; a rebuild of the unchanged plan gives the same look |
| the `.aep` is missing, broken or older than the approved plan | `whynot-cut:ae-builder` | rebuild from the same approved plan (step 4) |
| any change above that re-plans | `whynot-cut:medical-reviewer` (read-only) | reviews the new `01_analysis/motion-plan.md`: health claims; verses, hadith, attributed stories and rulings for a religious client |

1. After every re-plan, `whynot-cut:medical-reviewer` reviews the new `motion-plan.md`, reading the `On-screen text (full)` section (every motion video, whatever
   the client's `domain`; the religious checks when the profile `domain` is `religious`). Approval waits for its review;
   its approval list goes into what you show the editor. Record its table with `reel review-flags --root "<CLIENT>" --video-id <EP>_<ID>_MO --from -`
   (keyed by scene id; send only the changed scenes: a scene reviewed before with the same id and the same words stays
   covered by itself and keeps its earlier flag, and the command refuses, naming them, any scene whose words changed or
   that was renumbered, split or merged until the table lists it; when an earlier flag left its scene, until every new or
   changed scene is reviewed for that same flag, and while it stays on its scene, every new scene with an exact copy of
   its words, for example "S3 is new or changed since S2's medical flag: review S3 for medical"). Tell the
   motion-director to **keep scene ids stable** on a revision; a scene that is truly gone is reported as `dropped`.
2. VIEW the new `_storyboard.jpg` yourself; then show the editor the changed scenes (time, words, editorial lines
   marked as such) and the animatic path, for them to approve. Record `reel approve-plan --by editor` only with their
   words (a standing `approval: auto` or a "just do it" in chat → `--by delegated --note "…"`, as in step 4 of
   **Clip videos (Premiere)** above).
3. Ask the editor to save in After Effects first: `motion-build` refuses while After Effects holds unsaved work.
4. `whynot-cut:ae-builder` runs `reel motion-build`. If the editor changed the `.aep` in After Effects, the build refuses: tell
   them their changes would not carry over, and only with their explicit OK run `reel motion-build --replace-edited`
   (it keeps a backup of their file in `backups/`).
5. `whynot-cut:ae-builder` runs `reel motion-render`, then `reel motion-frames`.
6. `whynot-cut:qc-reviewer` checks the frames sheet (fan-out of frame-inspectors). You VIEW the sheet, record
   `reel verify --record --verdict pass|fail --notes "<what you checked>"`, run `reel qc` in the same message, and
   update the handoff and the reel's publish captions (`whynot-cut:publish-writer`) if the on-screen words changed.
7. Report per comment, as above. A build without read-back (`--script-only`) is Not verified.

- In your own messages, tables and file names, «الدكتور/الدكتورة» and he/she come only from people[] (reel-profile
  `profile.json`). Until a person's gender is known write «د.» or the name.
