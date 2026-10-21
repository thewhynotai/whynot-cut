---
name: story-craft
description: "Reference for the story-editor agent (preloaded). Not for direct use."
user-invocable: false
---

# Story craft

The transcript decides the edit. Read **all** of `02_transcription/transcript.txt` first, then use `words.json` for exact times.
Work from complete statements in context, never from isolated keywords.

**Write, in order** (formats in the references):
1. `01_analysis/main-topic.md`
2. `01_analysis/narrative-segments.json`, segments that tile the speech, on word boundaries
3. `01_analysis/transcript-semantic-analysis.json`, statement-level, including the B-roll options you rejected
4. `01_analysis/edit-decisions.json`, see `${CLAUDE_SKILL_DIR}/references/edit-decision-engine.md` and the schema

`01_analysis/editing-style.json` + `editing-rules.json` are this video's copy of the client reference style (written once per
client by client-researcher in `output/client_database/reference_style/`, copied by `reel ref-style --apply`). Read them and
the client's `editing-style-analysis.md`; never edit the copies. What only this video does differently goes in
`01_analysis/editing-style-overrides.json` (`reason`, `style` deep-merged, `rules` appended), then `reel ref-style --apply`.
`medical-content-review.md` comes from you together with medical-reviewer.
Then run `reel plan` and fix **every** error it reports (evidence not verbatim, overlaps, unknown assets). Repeat until it compiles.

**Rules:**
- Take the client's standing style from the profile (`reel profile`, then `style.json` and `notes.md`). Examples: pause removal, which statement
  template to use, glass only on the closing card, when captions hide. Copy those choices; don't re-decide them per video.
- Choose by **communication value**, not a quota. One primary graphic at a time, no graphic on every sentence, no SFX on every word.
- On-screen wording is the speaker's words with filler removed, or exact client-approved strings. Keep hedges ("يمكن", "ممكن") and warnings.
- Honorifics and gendered words about a person (name card, context card, hook) come from the profile `people[]`
  (`gender`, `honorific_ar`, `honorific_en`): «الدكتور» for a man, «الدكتورة» for a woman, never guessed from the name.
  `gender: unknown` → «د.» or the name alone until the editor says. `reel plan` errors on «الدكتورة <name>» for a man
  (and الأستاذ/ة, الشيخ/ة, المهندس/ة), and warns on a gendered honorific for an `unknown` person.
- Any claim the profile's `domain` makes sensitive gets `approval_required: true`: a medical claim; for a religious
  client a hadith, a ruling, or the speaker's words that echo a verse. A verse itself is never on screen: the editor
  adds it by hand, and `reel plan` empties a recited verse's captions and marks it. `reel plan` refuses words flagged as
  uncertain on any graphic.
- Fillers the editor or the client's plan asks to cut (a repeated «يعني», "um", a false start) go in
  `global.cut_words` (word ids + reason): picture, sound and captions lose them together; edit-plan.md lists them.
  Cut only fillers: a word that carries meaning («يعني» = "i.e." in an explanation) stays.
- A sentence said more than once: `reel takes` numbers the sentences and groups the repeats with the better take
  proposed («٤ و ٥ نفس الجملة: الأفضل ٥ — كاملة ومن غير تلعثم»). Show the editor those lines; the lead records the
  editor's choice with `reel takes --drop 4 --keep 5` (`--undo` goes back one step), then `reel plan` and a new
  approval. Nothing is cut before that, and the numbers are re-listed if the transcript changes. When the takes differ
  in meaning (a number or dose, a negation, a timing) no take is proposed: the line names the difference and the
  editor listens and chooses; never pick one for them.
- `reel cut-proposals` lists what could go (pauses, retakes with the better take kept, false starts, fillers, a
  doubled word) in `01_analysis/cut-proposals.json` with a plain reason, Arabic first, and the "Proposed cuts" table
  in edit-plan.md. Show the editor the numbered list; only the ids the editor picks are added, by the lead, with
  `reel cut-proposals --accept CP-003,CP-007`, then `reel plan` and a new approval. Nothing is cut before that. Bare
  «اه» (yes), «إيه», «آية», «امم» (unstretched), laughter, the sign-off, quotes and drug names are never proposed; a
  take holding a number or a dose, and two takes that differ in a negation, a number or a timing word («مش», «الصبح»
  / «بالليل»), are left unticked with the differing words named: play both to the editor. The plan side (the table,
  the markers, a take cut whole) waits for the `task25_plan_proposals` switch in safety.json.
- Images come only from the client asset manifest (by `rel` path); stock VIDEO only from the licensed `data/Broll/` folder
  (`broll_video`). Never download or generate footage. No AI likeness, and no retouching of the client.
- Decisions stay in **source time**. With `remove_pauses`, the compiler remaps everything.

**Podcast reels:** `00_inputs/source.json` holds the reel's content type and recipe. Follow it (pause thresholds are
applied by the engine; graphics per 30 s, zoom limits and avoided templates are checked by `reel plan`). Explain a
deliberate deviation in that decision's `recipe_note`. Templates for podcasts: `stat_card` (`value`, `label`) for a
number the speaker says, `context_card` (`text`) at the start of a reel that needs context (editorial, so keep it
short and factual). Music only from `reel music --list` (licensed tracks with moods) via `music.file`; keep chosen
pauses with `global.remove_pauses.protect: [[start, end]]`.

**References:**
- `${CLAUDE_SKILL_DIR}/references/semantic-analysis.md`
- `${CLAUDE_SKILL_DIR}/references/edit-decision-engine.md`
- `${CLAUDE_SKILL_DIR}/references/broll-and-graphics.md`
- `${CLAUDE_PLUGIN_ROOT}/schemas/edit-decisions.schema.json` (check a draft with `reel validate 01_analysis/edit-decisions.json`)
