# Motion scenes (motion-script.json)

```json
{"reel_id": "EP12_R03_MO", "theme": "dark", "captions": "subtitles",
 "beats": [{"id": "B1", "role": "hook", "summary": "…"}],
 "scenes": [
  {"id": "S01", "beat": "B1", "type": "kinetic_quote", "at": "@start", "text": "<speaker words>", "emphasis": ["<word>"]},
  {"id": "S02", "type": "stat_counter", "at": "<first words spoken when it starts>", "value": "3", "unit": "مليون",
   "label": "<label>", "label_source": "editorial", "evidence": "<spoken words with the number>"},
  {"id": "S09", "type": "outro", "at": "@end", "cta": "تابع {show}"}],
 "music": {"file": "data/Music/<licensed>.wav", "level_db": -24}}
```
Every scene: `id` (S01…), `type`, `beat`, `at` (`@start` first; `@end` only for a last outro; otherwise 2–12 words
copied from the transcript), optional `transition_in`, `sfx` (synth kinds), `theme`, `captions` (`on|off`),
`recipe_note` (why it deviates from the recipe). Top-level `theme`/`captions` override the recipe for the video.

| Type | Fields (required · optional) | Text source |
|---|---|---|
| `kinetic_quote` | `text` · `emphasis[]`, `reveal` (word/line) | speech, word by word as spoken; ≤ recipe max words |
| `title_card` | `title` (+ `title_source`) · `eyebrow`, `subtitle` | title speech or editorial; eyebrow/subtitle editorial |
| `stat_counter` | `value`, `evidence` · `prefix`, `suffix`, `unit`, `label` (+ `label_source`), `icon` | the number as said |
| `icon_point` | `icon`, `text` (+ `text_source`) · `mirror` | speech or editorial |
| `list_steps` | `items[{text, at}]` (2–5) · `title` | items speech (each appears at its `at`); title editorial |
| `comparison` | `first{label, points[≤3]}`, `second{…}` · `verdict`, `text_source` | speech or editorial (one source) |
| `timeline` | `points[{label, when, at}]` (2–5) | labels speech; `when` editorial (digits must be said) |
| `quote_card` | `text`, `attribution` (`host`/`guest`) | speech, revealed line by line; name from the sheet |
| `context_card` | `text` | editorial (tells a cold viewer what came before) |
| `person_card` | `who` (`host`/`guest`) · `photo` (asset-manifest rel) | name and role from the sheet |
| `illustration_scene` | `illustration` (`pack/item`) · `text` (+ `text_source`) | licensed pack only |
| `outro` | `cta` · `show_logo`, `show_name` | editorial; show from the sheet |

Persistent layers (recipe-controlled): background (theme, slow gradient, grain), captions (hidden while a scene shows
the spoken words), speaker badge (two speakers), progress bar, voice pulse (audio-only episodes).

## Truth rules the engine enforces (`reel motion-plan`)
- Speech text = the speaker's words in order; fillers may be dropped; nothing added. Kinetic/quote text may leave out
  at most 40 % of what is said in its scene.
- Editorial text: no quotation marks, no digits that were not said, people/show only via `{host}` `{guest}` `{show}`.
- Numbers: the value's digits must be in the evidence's digits; otherwise the editor must confirm (approval).
- Icons from the Lucide index (`reel motion-icons --search`), illustrations from ok packs (`reel motion-library`).
- Text must fit its box at the recipe/format sizes (HarfBuzz with the brand font); otherwise "too long: split".
