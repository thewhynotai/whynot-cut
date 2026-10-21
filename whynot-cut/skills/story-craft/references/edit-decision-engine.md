# Edit Decision Engine (Stage 6) — authoring `01_analysis/edit-decisions.json`

Combine **SRT meaning + editing-style/rules + client brand** (`01_analysis/editing-style.json` + `editing-rules.json` =
the client reference style copied for this video, with its overrides). One decision per meaningful segment that
needs treatment (talking-head-only segments need no decision unless a camera change happens).
`reel plan` validates and compiles; fix all errors it reports. Times: `"HH:MM:SS.mmm"` (or seconds).
Frames are computed by the compiler at the client's sequence rate (24 / 25 / 29.97 …, round-half-up from absolute ms —
no drift); don't hand-compute. Times are on the transcript's clock (0 = the reel's in-point for a range).

### Framing (`global.base_scale_percent`)
- `"auto"` (or absent): a 9:16 source is fitted; a WIDER source (e.g. a 16:9 episode) is reframed to fill the vertical
  frame, centred on the speaker's face (preflight measures it: `00_inputs/preflight.json` → `reframe`).
- A number (e.g. `50`) overrides it; `base_offset_x` / `base_offset_y` (sequence px) shift the frame.
- **Source cutaways** (graphic cards, B-roll or another camera burned into a finished episode, listed in preflight's
  `reframe.cutaways_ms`) are shown whole over a blurred copy of themselves, automatically: a 16:9 card cropped to
  9:16 loses its text. Graphics that would sit over the card end before it starts.
  Decide per cutaway: keep it, cover it with your own graphic carrying the same words (statement_highlight etc.), or
  choose a clip range that avoids it. Mention them in the plan summary.

```json
{
  "video_id": "C0238", "version": 1,
  "global": {
    "main_footage": "data/Raw/C0238.MP4",
    "base_scale_percent": "auto",
    "caption_style": "keywords | highlight_all",
    "captions_hidden_during": ["broll_card", "logo_outro"],
    "remove_pauses": {"min_pause_ms": 250, "pad_ms": 80, "mask_scales": [1.0, 1.06],
                      "protect": [["00:00:02.400", "00:00:33.160"]]},
    "cut_words": [{"word_ids": [52], "reason": "filler «يعني»"}],
    "framing": "9:16 | 4:5",
    "native_caption_track": false,
    "photoshop_jobs": [
      {"id": "PS_COVER", "image": "assets/Photos/4.jpg", "headline": "<the speaker's words>", "subline": "<exact approved name>",
       "band": [1100, 1920], "headline_y": 1450, "subline_y": 1600, "logo_y": 1790}
    ]
  },
  "caption_highlights": [{"text": "<exact phrase>", "at": "00:00:05.120"}],
  "music": {"status": "NO_MUSIC_SUPPLIED", "cue_points": [{"frame": 0, "label": "bed in", "note": "low bed -18 dB"}]},
  "decisions": [{
    "decision_id": "EDIT_001", "segment_id": "SEG_001",
    "evidence": "<exact transcript words — must exist verbatim (diacritics/punctuation-insensitive)>",
    "start": "00:00:00.000", "end": "00:00:03.900",
    "semantic_intent": "Hook: poses the core question", "visual_treatment": "hook title + punch-in",
    "camera": {"type": "punch_in", "at": "00:00:01.200", "until": "00:00:03.900", "scale_factor": 1.08, "offset_y": 40,
               "rationale": "emphasis on key word"},
    "graphics": [{
      "id": "GFX_001", "template": "hook_title", "start": "00:00:00.200", "end": "00:00:03.800",
      "text": "<the speaker's words, shortened only by removing filler>", "concept": "…",
      "items": [{"text": "…", "at": "00:00:10.400", "latin": false}],
      "image": "assets/Photos/2.png", "headline": "…", "name": "…", "lines": ["…"],
      "latin": false, "sfx": "pop | none", "approval_required": false
    }],
    "sound": [{"type": "whoosh", "at": "00:00:12.000", "gain_db": -16, "related_visual": "GFX_004", "note": "…"}],
    "approval_required": false, "confidence": "high|medium|low", "rationale": "why this helps understanding"
  }]
}
```

### Style knobs for this reel (`global`, optional)
The client's `reel-profile/style.json` sets the standing caption and hook style (see client-craft); set these in
`global` only when the editor wants this one reel different. `reel plan` records the result in the timeline-spec's
`style` block (nothing is written when everything is at the default).
- `caption_size_px`: this reel's caption size, a whole number of px (32-140 on a 1080 px wide frame), e.g. `72` for
  bigger captions; caption lines get shorter as it grows.
- `hook_title_sfx`: `false` = no sound when the hook title appears (`true` brings it back for this reel). A graphic's
  own `"sfx"` still wins.
- `highlight_colour`: the keyword caption box for this reel: `"brand"`, `"accent"`, `"ink"` or `"#RRGGBB"` (with the
  `#`). A colour too faint behind the caption text is replaced by a readable brand colour, and the plan warns (G68).
  It colours the Premiere captions; After Effects captions use the brand colour for now.
- Captions under the hook are a client setting (`captions_during_hook`). For one reel, write
  `captions_hidden_during` with or without `hook_title`: that list replaces the client's whole list (copy the other
  graphics you still want), and an empty `[]` falls back to the client's list.
A wrong value here is a plan error naming the field; fix it and run `reel plan` again.

## Templates (see `config/defaults/graphics-templates.json (+ client profile overrides)`)
| template | required params | track |
|---|---|---|
| hook_title | text | V05 |
| term_callout | text, latin (bool) | V05 |
| glass_card | text | V04 (check the client's style.json: some clients reserve glass for the closing card) |
| statement_highlight | text (white text on brand boxes that sweep in RTL) | V04 |
| checklist | items[{text, at, latin}], title? | V09 |
| broll_card | headline, image? (else placeholder:true) | V07 (covers speaker) |
| photo_card | image, text? | V04 |
| name_card | name, lines[] | V04 |
| cta | text (only a CTA the speaker says) | V05 |
| logo_outro | — | V07 |
| flash_transition | — (8–10 f around full-screen cuts) | V12 |

## Camera
`type`: hold | punch_in | punch_out | slow_push | reframe. `scale_factor` multiplies base scale (1.05–1.12 typical);
`offset_y`/`offset_x` px in sequence space (positive y moves the image down to keep eyes in frame when scaling).
The compiler splits V01 at every camera change; timeline time always equals source time (sync safe).
A punch_in eases in and out over the client's `style.json` `camera.ease_ms` (default 250 ms, bezier); a slow_push
pushes in across its whole piece (from the picture before it to its scale_factor), so use slow_push for a slow zoom.
punch_out and reframe stay hard. A move that starts or ends on a pause/word cut, or next to another shot (podcast
framing), stays hard on that side; the automatic jump-cut zooms and 4:5 window framing stay hard on purpose. Don't
shorten a punch-in to fake a smooth zoom: one shorter than 2 x the ease shares its frames between the two eases.

## Quality rules
- Same-track graphics cannot overlap (compiler error). One primary graphic at a time.
- No random zooms, no graphics every sentence, no SFX on every word. Prefer fewer, meaningful events.
- On-screen wording = the speaker's words (filler removed) or exact client-approved strings (name card).
- `approval_required: true` for any medical diagram, claim card, dosage, lab values, before/after or likeness, and
  (religious domain) any hadith, ruling or line that echoes a verse. A verse itself never goes on screen: the editor
  adds it by hand (`reel plan` leaves a recited verse's captions empty and marks it, and holds the captions after a
  verse that ends on a pause; `manual_verse` / `manual_verse_off` at the top level of edit-decisions.json add or
  remove a span, `manual_verse_release` releases a held run once the editor has listened, see
  agents/story-editor.md).
- Client-approved strings (a hook written in the client's reels plan, the show's standing end card) may be used
  as on-screen text; say where they come from in `concept`.
- Images only from the client asset manifest (`client_database/asset-manifest.json`, by `rel` path).

## Global switches
- `remove_pauses`: needs `reel audio-clean` first (writes `06_audio/dialogue/pauses.json`). Decisions stay in SOURCE time;
  the compiler remaps every graphic/caption/SFX and alternates the zoom at cuts (`mask_scales`). Camera decisions win.
  `protect` (source-time ranges) keeps the pauses inside them, e.g. a joke's comedic timing.
- `framing`: "9:16" (default, the picture fills the frame) or "4:5" (the speaker in a 1080×1350 window over a blurred
  fill; punch-ins and jump-cut zooms stay inside the window; `framing_window_y` moves it). Follow the client's plan.
- `native_caption_track`: false = captions are animated graphics (reference style) + `subtitles-seq.srt` CC sidecar;
  true = also add Premiere's native caption track (would show twice if both are visible).
- Copy the client's standing choices from the profile's `style.json` (via `reel profile`) — don't re-decide them per video.
