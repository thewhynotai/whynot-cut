---
name: client-craft
description: "This skill should be used when building a whynot-cut client database or profile — discovering client assets, extracting brand colours/fonts, classifying photos, analysing reference edits, writing the client's reel-profile. Knowledge for the client-researcher agent."
user-invocable: false
---

# Client craft

```bash
reel discover    --root "<CLIENT>"                 # inventory + roles (assets/ = brand, data/ = footage + references)
reel client-db   --root "<CLIENT>"                 # colours from documents, fonts (fontTools), images → client_database/
reel ref-analyze --root "<CLIENT>" --video-id <ID> # reference cuts, contact sheets, loudness
```
- **View** every image contact sheet and every reference contact sheet (Read the JPGs). Many facts are only visible this way.
- Write the semantic layer listed in `references/client-intelligence.md`:
  - the profile docs
  - `asset-classification.json` (after viewing)
  - `brand-roles.json`
  - `typography-roles.json`

  Then run `client-db` again so the roles merge.
- Reference style goes in `01_analysis/editing-style-analysis.md`, `editing-style.json` and `editing-rules.json`, with measured and
  inferred items clearly marked (see `references/editing-reference-analysis.md`).
- **Client reel-profile** (`output/client_database/reel-profile/`, created by `reel client-init`):
  - `profile.json`: id, display name, prefix, languages, specialty
  - `transcription.json`: `initial_prompt` with the name and specialty exactly as spelled in the brief
  - `medical-glossary.json`: domain terms that trigger review
  - `style.json` + `notes.md`: standing style seen in the references or stated by the editor
  - `sequence-settings.json`: the frame rate of the client's delivered reels (probe a reference video), e.g.
    `{"general": {"timebase": 30, "ntsc": true}}` for 29.97 fps
  - `graphics-templates.json`: positions and colour roles measured from the reference reels (keep top graphics under
    the 250 px safe line even when a reference places them higher; `highlight_caption.box_all` for captions on a
    translucent box, as many Arabic channels use)
  - `brand.json`: only if the client supplied HEX codes the extraction missed
- Every statement cites a source file. Missing facts stay "unavailable". A missing font is reported, never substituted.
  Brand files outrank references, and references outrank generic templates.
