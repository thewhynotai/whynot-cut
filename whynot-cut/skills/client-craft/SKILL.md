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
- Write the semantic layer listed in `${CLAUDE_PLUGIN_ROOT}/skills/client-craft/references/client-intelligence.md`:
  - the profile docs
  - `asset-classification.json` (after viewing)
  - `brand-roles.json`
  - `typography-roles.json`

  Then run `client-db` again so the roles merge.
- **Reference style is written once per client**, not per video: `output/client_database/reference_style/`
  `editing-style-analysis.md`, `editing-style.json` and `editing-rules.json`, with measured and inferred items clearly
  marked (see `${CLAUDE_PLUGIN_ROOT}/skills/client-craft/references/editing-reference-analysis.md`). Then `reel ref-style --record`: it stores the fingerprint of
  the reference set (every reference file's path, size and modification time).
  - `reel ref-style` says **current**: don't re-author. Each video reuses it (`reel ref-style --apply --video-id <ID>`;
    `ref-analyze` with a video id does it automatically). What only one video needs goes in that video's
    `01_analysis/editing-style-overrides.json`.
  - **stale** (a reference was added, removed or edited since the record; `reel next` and the session start say so):
    refresh the three files from the changed references, refresh `reel-profile/style.json` and `notes.md` where the
    standing style changed (keep the client-rules block in `notes.md` and the knobs a client rule wrote, which
    `reel rules --list` names: a rule changes only through `reel rules`), then `--record` again. `--record` warns when the profile files were not touched.
  - No reference edits at all: write the three files from the profile's `style.json`/`notes.md` and the editor's own
    words, marked "no reference edits", and record them.
  - **Old videos with their own style** (2.x authored `01_analysis/editing-style.json` per video): seed or extend the
    client style from one with `reel ref-style --adopt <ID>`. It prints the diff first (added keys, rules, and
    conflicts where the client value is kept); report it to the lead, who shows it to the editor and, only with their
    OK, runs `--adopt <ID> --yes` (subagents may not: the guard blocks it).
    Conflicts land in `editing-rules.json` `conflicts` for you and the editor to settle; then review the three files
    against the current references and `--record`. It never changes the video's own files.
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
    `camera.ease_ms` (smooth zoom on the story punch-ins, default 250, 0 = hard punches, when the references show
    hard or slower zooms; a slow_push always pushes across its whole piece); `fades` {video_in_ms, video_out_ms,
    audio_in_ms, audio_out_ms} (default 0 = off; under one frame counts as off) when the client's reels fade to/from
    black at the start/end. The picture fade is one black layer over everything; sound effects never fade;
    `export` {name pattern with {episode} {video_id} {name} {version}, video, audio, folder} from the client's
    delivery spec, which the handoff turns into the exact file name
  - `style.json`, the four caption and hook knobs that `reel plan` reads (set one only when the references or the
    editor say so; leave it out to keep today's look):
    - `caption_size_px`: how big the captions are, a whole number of px on a 1080 px wide frame (32-140; e.g. 52
      for a series with small captions, 72 for bigger ones). Not set = the caption template's size. Bigger captions
      get shorter lines so they stay in the frame; the plan warns when a caption is still wider than the safe area.
      A chosen caption size rebuilds the captions from the transcript words, so fix caption wording in the
      transcript, not by hand in `captions-short.srt` (the plan warns when hand edits there would be lost).
    - `captions_during_hook`: `"show"` keeps the captions on screen while the hook title is up (as many Arabic
      channels do); `"hide"` (default) hides them so the hook is not read twice. After Effects captions follow it
      now; Premiere captions follow it after the next WhyNot Cut update (until then they stay hidden under the hook).
    - `hook_title_sfx`: `false` = no click or pop when the hook title appears; `true` (default) = its usual sound.
    - `highlight_colour`: the box behind the keyword caption: `"brand"` (default), `"accent"`, `"ink"` or a code such
      as `"#81613D"`. The plan checks it against the caption text; a colour too faint to read is swapped for the most
      readable brand colour and the plan warns, so pick a darker one if the warning shows. It colours the Premiere
      captions; After Effects captions use the brand colour for now.

    Builds follow the compiled plan: after changing a knob, run `reel plan` again. One reel may differ (the story editor sets `global.caption_size_px`, `global.hook_title_sfx` or
    `global.highlight_colour` in its edit-decisions); a reel that must hide captions under its hook while the client
    shows them lists `hook_title` in that reel's `global.captions_hidden_during`. These keys stay at the top level of
    `style.json`, never inside its `captions` block (that block is the caption-look choice).
  - **Caption look, on a new client's first clip:** first `reel looks recommend --root "<CLIENT>" --video-id <ID>
    --kind caption`: the one look that suits this clip, one reason line and the top three with their stills (it
    changes nothing). Lead with that suggestion; the editor still picks. Then offer the gallery, `reel caption-looks --root
    "<CLIENT>" --video-id <ID>`. It draws every caption look on two frames of that clip and one sheet in
    `08_quality_control/previews/caption-looks/` (view the sheet, then show it). The editor picks by sight;
    `reel caption-looks --root "<CLIENT>" --video-id <ID> --pick <look>` prints the diff against `style.json`. Report
    it to the lead, who runs it again with `--yes` only with the editor's OK: that saves the look in the `captions`
    block. No pick keeps today's captions.
  - `brand.json`: only if the client supplied HEX codes the extraction missed
- Every statement cites a source file. Missing facts stay "unavailable". A missing font is reported, never substituted.
  Brand files outrank references, and references outrank generic templates.
