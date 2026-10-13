---
name: client-craft
description: "Reference for the client-researcher agent (preloaded). Not for direct use."
user-invocable: false
---

# Client craft

```bash
reel discover    --root "<CLIENT>"                 # inventory + roles (assets/ = brand, data/ = footage + references)
reel client-db   --root "<CLIENT>"                 # colours from documents, fonts (fontTools), images → client_database/
reel ref-analyze --root "<CLIENT>"                 # reference cuts, contact sheets, loudness (cached per client)
reel ref-style   --root "<CLIENT>"                 # client reference style: missing | unrecorded | stale | current
reel ref-style   --root "<CLIENT>" --record --by client-researcher   # after writing reference_style/ (below)
```
- **View** every image contact sheet and every reference contact sheet (Read the JPGs). Many facts are only visible this way.
- Write the semantic layer listed in `${CLAUDE_SKILL_DIR}/references/client-intelligence.md`:
  - the profile docs
  - `asset-classification.json` (after viewing)
  - `brand-roles.json`
  - `typography-roles.json`

  Then run `client-db` again so the roles merge.
- **Reference style is written once per client**, not per video: `output/client_database/reference_style/`
  `editing-style-analysis.md`, `editing-style.json` and `editing-rules.json`, with measured and inferred items clearly
  marked (see `${CLAUDE_SKILL_DIR}/references/editing-reference-analysis.md`). Then `reel ref-style --record`: it stores the fingerprint of
  the reference set (every reference file's path, size and modification time).
  - `reel ref-style` says **current**: don't re-author. Each video reuses it (`reel ref-style --apply --video-id <ID>`;
    `ref-analyze` with a video id does it automatically). What only one video needs goes in that video's
    `01_analysis/editing-style-overrides.json`.
  - **stale** (a reference was added, removed or edited since the record; `reel next` and the session start say so):
    refresh the three files from the changed references, refresh `reel-profile/style.json` and `notes.md` where the
    standing style changed, then `--record` again. `--record` warns when the profile files were not touched.
  - No reference edits at all: write the three files from the profile's `style.json`/`notes.md` and the editor's own
    words, marked "no reference edits", and record them.
- **Client reel-profile** (`output/client_database/reel-profile/`, created by `reel client-init`):
  - `profile.json`: id, display name, prefix, languages, specialty, and `people[]`:
    `{"name": "Dr. Name / د. الاسم", "role": "client", "gender": "male" | "female" | "unknown",
    "honorific_ar": "الدكتور", "honorific_en": "Dr.", "pronouns": "he/him"}` per person who appears or is named
    (client, co-host, regular guest). Gender and honorifics come only from the client's material (brief, name card,
    bio, a reference edit's title, the editor's words), cited in `notes.md`. Never infer gender from a name; not stated
    → `unknown` and ask the editor. `reel plan` / `reel publish-check` then flag «الدكتورة <name>» for a man (error)
    and any gendered honorific for an `unknown` person (warning).
  - `transcription.json`: `initial_prompt` with the name and specialty exactly as spelled in the brief
  - `medical-glossary.json`: domain terms that trigger review
  - `style.json` + `notes.md`: standing style seen in the references or stated by the editor
  - `sequence-settings.json`: the frame rate of the client's delivered reels (probe a reference video), e.g.
    `{"general": {"timebase": 30, "ntsc": true}}` for 29.97 fps
  - `graphics-templates.json`: positions and colour roles measured from the reference reels (keep top graphics under
    the 250 px safe line even when a reference places them higher). `highlight_caption`: `box_all` (captions on a
    translucent box, as many Arabic channels use), `strip_punctuation` (e.g. "،,.;؛:" when the client wants no commas
    in burned captions), `lead_in_ms` (e.g. 200: a line appears just before the words), `size`
  - `style.json`, beyond pacing and music: `reframe_sharpen` {amount, grain_percent} when the client sharpens the
    upscaled 9:16 crop; `framing` "9:16" or "4:5" (the speaker in a 1080×1350 window over a blurred fill);
    `export` {name pattern with {episode} {video_id} {name} {version}, video, audio, folder} from the client's
    delivery spec, which the handoff turns into the exact file name
  - `brand.json`: only if the client supplied HEX codes the extraction missed
- Every statement cites a source file. Missing facts stay "unavailable". A missing font is reported, never substituted.
  Brand files outrank references, and references outrank generic templates.
