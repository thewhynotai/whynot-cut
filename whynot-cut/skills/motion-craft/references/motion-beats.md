# Recipes → beats → scenes

The window's content type (from Gate 0) sets `recipe.motion` in `00_inputs/source.json`. Follow it; explain any
deviation in the scene's `recipe_note`.

| type | beats (in order) | scene s (min/target/max) | prefer | reveal · ease · transition | theme | SFX |
|---|---|---|---|---|---|---|
| storytelling | hook, setup, turn, payoff | 2.5/5/9 | title_card, kinetic_quote, timeline, icon_point, context_card | word · smooth · push | light | whoosh_soft on transitions |
| drama | hook, tension, peak, aftermath | 2/4/8 | kinetic_quote, quote_card | word · snappy · cut | dark | hit_soft on the peak |
| success_story | result, before, struggle, milestone, lesson | 2/4/7 | stat_counter, timeline, title_card | word · snappy · push | brand | riser before a stat, shimmer when it lands |
| advice | hook, problem, steps, takeaway | 2/3.5/6 | list_steps, icon_point, comparison | word · snappy · wipe | light | tick per item |
| bold_opinion | claim, reasons, claim_again | 2/3.5/6 | kinetic_quote, title_card | word · snappy · scale | dark | hit_soft |
| emotional | moment, reflection | 3.5/6/12 | quote_card, kinetic_quote | line · gentle · fade | dark | none |
| comedy | setup, beat, punchline, tag | 1.5/3/6 | kinetic_quote, icon_point | word · bouncy · scale | brand | pop |

Avoided: drama/bold_opinion/comedy avoid `list_steps`; emotional avoids `list_steps`, `stat_counter`, `comparison`.
Captions are off for drama and emotional (the words are on screen or the moment is quiet).

## Picking scenes
- Hook first: the line that makes a viewer stay (a kinetic quote of the speaker's own hook, or a title card).
- A number the speaker says → `stat_counter`. Steps or tips → `list_steps` (each item appears when said).
- Before/after, myth/fact → `comparison`. A journey with dates/ages → `timeline`.
- A strong sentence to sit with → `quote_card` (line reveal). Cold open needs context → `context_card` first.
- One idea per scene; ≤ the recipe's words on screen; scenes change on phrase boundaries.

## Direction (RTL vs LTR)
Everything that means "next" or "more" moves toward the reading end. In Arabic (RTL): words appear right → left,
timelines draw right → left, progress fills right → left, list numbers sit on the right, `comparison.first` is the
right panel, a push brings the next scene in from the left. Directional icons (arrows, chevrons, trending, send…) are
mirrored automatically; set `"mirror": false` on a scene to keep an icon as drawn. Never hardcode a side.
