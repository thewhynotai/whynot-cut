# Content types (podcast reels)

Each type has a recipe in `config/defaults/recipes.json` (a client profile may override it). The engine applies the
recipe's numbers (pause thresholds, zoom and graphics limits, music level); the story-editor and publish-writer
follow the rest. Pick the type by what the viewer feels at the end, not by the topic.

| type | id | the viewer feels | signals in speech | structure | hook |
|---|---|---|---|---|---|
| Storytelling — حكاية | `storytelling` | "what happened next?" | past tense narration, «مرة», «فاكر لما», names and places, "so then…" | setup → turn → ending | open question / the turn |
| Drama / confrontation — دراما/مواجهة | `drama` | tension | conflict, disagreement, a hard truth, «قلتله», raised stakes, silence | stakes → clash → aftermath | the conflict in one line |
| Success story — قصة نجاح | `success_story` | "I can too" | before → after, numbers, years, «بدأت من الصفر», milestones | low point → steps → result | the result or number first |
| Advice / insight — نصيحة/معلومة | `advice` | "useful" | «لازم», «أهم حاجة», "the mistake is", steps, lists | point → why → how | "N things" / the one mistake |
| Bold opinion — رأي جريء | `bold_opinion` | agreement or disagreement | «أنا شايف إن», "unpopular opinion", strong claims | claim → reason → stand | the opinion as said |
| Human / emotional — لحظة إنسانية | `emotional` | moved | vulnerability, loss, gratitude, pauses, voice changes | moment → meaning | a quiet line, no clickbait |
| Comedy — كوميدي | `comedy` | amused | laughter, irony, exaggeration, callbacks | setup → beat → punchline | the setup line |

Recipe highlights (defaults):
- Pauses removed from: storytelling 350 ms · drama 600 ms (dramatic silences stay) · success 300 · advice 250 ·
  bold opinion 250 · emotional 800 (pauses stay) · comedy 220 (keep the beat before the punchline with
  `remove_pauses.protect`).
- Graphics: success → `stat_card` for a number the speaker says; storytelling → `context_card` when needed; advice →
  `checklist`/`term_callout`; drama/bold → one `statement_highlight`/`hook_title`; emotional → almost none.
- SFX: drama hits/risers, success riser/shimmer, advice pops/clicks, emotional none, comedy pop.
- Music mood (licensed tracks only): warm/curious · tense/dark · uplifting · light/upbeat · minimal · soft piano · playful.

Two types? Keep the stronger as `type` and the other as `secondary_type` (it only changes the copy tone).
