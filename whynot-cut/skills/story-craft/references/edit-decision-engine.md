# Edit Decision Engine (Stage 7) — authoring `01_analysis/edit-decisions.json`

Combine **SRT meaning + editing-style/rules + client brand**. One decision per meaningful segment that
needs treatment (talking-head-only segments need no decision unless a camera change happens).
`reel plan` validates and compiles; fix all errors it reports. Times: `"HH:MM:SS.mmm"` (or seconds).
Frames are computed by the compiler (24 fps, round-half-up from absolute ms — no drift); don't hand-compute.

### Framing (`global.base_scale_percent`)
- `"auto"` (or absent): a 9:16 source is fitted; a WIDER source (e.g. a 16:9 episode) is reframed to fill the vertical
  frame, centred on the speaker's face (preflight measures it: `00_inputs/preflight.json` → `reframe`).
- A number (e.g. `50`) overrides it; `base_offset_x` / `base_offset_y` (sequence px) shift the frame.
- **Source cutaways** (graphic cards, B-roll or another camera burned into a finished episode, listed in preflight's
  `reframe.cutaways_ms`) are shown whole, letterboxed, automatically: a 16:9 card cropped to 9:16 loses its text.
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
    "remove_pauses": {"min_pause_ms": 250, "pad_ms": 80, "mask_scales": [1.0, 1.06]},
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

## Quality rules
- Same-track graphics cannot overlap (compiler error). One primary graphic at a time.
- No random zooms, no graphics every sentence, no SFX on every word. Prefer fewer, meaningful events.
- On-screen wording = the speaker's words (filler removed) or exact client-approved strings (name card).
- `approval_required: true` for any medical diagram, claim card, dosage, lab values, before/after or likeness.
- Images only from the client asset manifest (`client_database/asset-manifest.json`, by `rel` path).

## Global switches
- `remove_pauses`: needs `reel audio-clean` first (writes `06_audio/dialogue/pauses.json`). Decisions stay in SOURCE time;
  the compiler remaps every graphic/caption/SFX and alternates the zoom at cuts (`mask_scales`). Camera decisions win.
- `native_caption_track`: false = captions are animated graphics (reference style) + `subtitles-seq.srt` CC sidecar;
  true = also add Premiere's native caption track (would show twice if both are visible).
- Copy the client's standing choices from the profile's `style.json` (via `reel profile`) — don't re-decide them per video.
