---
name: story-craft
description: "This skill should be used when analysing what a speaker means and authoring edit decisions for a whynot-cut project — main topic, narrative segments, statement analysis, which moments get graphics/B-roll/punch-ins, edit-decisions.json. Knowledge for the story-editor agent."
user-invocable: false
---

# Story craft

The transcript decides the edit. Read **all** of `02_transcription/transcript.txt` first, then use `words.json` for exact times.
Work from complete statements in context, never from isolated keywords.

**Write, in order** (formats in the references):
1. `01_analysis/main-topic.md`
2. `01_analysis/narrative-segments.json`, segments that tile the speech, on word boundaries
3. `01_analysis/transcript-semantic-analysis.json`, statement-level, including the B-roll options you rejected
4. `01_analysis/edit-decisions.json`, see `references/edit-decision-engine.md` and the schema

`editing-style.json` comes from client-researcher, and `medical-content-review.md` from you together with medical-reviewer.
Then run `reel plan` and fix **every** error it reports (evidence not verbatim, overlaps, unknown assets). Repeat until it compiles.

**Rules:**
- Take the client's standing style from the profile (`reel profile`, then `style.json` and `notes.md`). Examples: pause removal, which statement
  template to use, glass only on the closing card, when captions hide. Copy those choices; don't re-decide them per video.
- Choose by **communication value**, not a quota. One primary graphic at a time, no graphic on every sentence, no SFX on every word.
- On-screen wording is the speaker's words with filler removed, or exact client-approved strings. Keep hedges ("يمكن", "ممكن") and warnings.
- Any medical claim on screen gets `approval_required: true`. Don't use words flagged as uncertain.
- Images come only from the client asset manifest (by `rel` path); stock VIDEO only from the licensed `data/Broll/` folder
  (`broll_video`). Never download or generate footage. No AI likeness, and no retouching of the client.
- Decisions stay in **source time**. With `remove_pauses`, the compiler remaps everything.

**References:**
- `references/semantic-analysis.md`
- `references/edit-decision-engine.md`
- `references/broll-and-graphics.md`
- `references/edit-decisions.schema.json`
