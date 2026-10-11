# <Client name> — client notes

Fill this from the client's own documents and the editor's feedback only. Never invent facts.

## Brand
- Colours: (measured by `reel client-db` from `assets/`; HEX codes only if the client supplied them)
- Fonts: (file names in `assets/`; install them before building)
- Logo:
- Approved name-card wording (exact):

## People (`profile.json` → `people`)
- One entry per person who appears or is named in the videos (the client, a co-host, a regular guest):
  `{"name", "role", "gender": "male" | "female" | "unknown", "honorific_ar", "honorific_en", "pronouns"}`.
  Put the Arabic and Latin spellings in `name` (e.g. "Dr. Name / د. الاسم").
- Fill gender and honorifics **only from the client's own material** (brief, name card, bio, the editor's words).
  Never infer gender from a name: «الدكتور» vs «الدكتورة» is a fact to look up, not a guess. Not stated → `unknown`,
  and ask the editor.
- `reel plan` and `reel publish-check` flag an honorific of the wrong gender next to the person's name (error) and a
  gendered honorific for someone whose gender is `unknown` (warning).

## Editor's standing style
- Pauses: removed? min pause / pad?
- Captions: style, when hidden
- Statements / graphics: which templates, any "only at the end" rules
- Animation: (Premiere keyframe presets: bar_sweep, text_pop, slide, push, card, flash)

## Audio facts
- Mics / channels:
- Noise characteristics:

## Domain / medical
- Specialty:
- Claims that always need approval:

## Worked examples
- <clip id>: what was done, what is still open
