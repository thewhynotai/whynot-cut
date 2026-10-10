# B-roll & Graphics

Decide per statement (semantic-analysis.md): what needs visual explanation, why, best format, can a client
asset be reused, is typography enough, duration, timing, brand compliance.

| Type | Source | Implementation |
|---|---|---|
| A — Client assets | `client_database/asset-manifest.json` (photos, logo) | `photo_card`, `broll_card` image, `logo_outro`, PSD jobs |
| B — Typography | the speaker's words | `highlight_caption`, `hook_title`, `term_callout`, `glass_card`, `cta` |
| C — Educational | the speaker's enumerations/processes | `checklist` (+ future: process/comparison templates) |
| F — Licensed stock video | `data/Broll/` clips (role `broll_video`) with a SOURCES/licence file | `broll_video`: `video`, `in` (s), optional `crop_center`; full screen, muted, hard cut; captions stay on top. Use for a concrete image the speaker names (an object, a place, an action), 1–3 s, at most one per ~10 s; never for faces of real people other than the speaker; never download stock yourself |
| D — Motion | AE comps (all of the above are animated, editable) | `04_after_effects/` |
| E — Generated illustrative | **only** a configured, approved provider | not configured → `broll_card` with `"placeholder": true` + approval flag; never claim generated footage exists |

Outputs per graphic: AE comp (named = event id) → ProRes 4444 alpha `.mov` in `04_after_effects/compositions/`;
PNG preview in `03_broll/{typography|educational-graphics}/`; QC composite over the real frame in
`08_quality_control/previews/`. `03_broll/broll-manifest.json` tracks status
(PLANNED → PREVIEW_PNG_ONLY / AE_RENDERED / MISSING) and approval.

Source cutaways (graphic cards burned into a finished episode, see edit-decision-engine.md › Framing) are shown whole
over a blurred fill automatically; a `broll_video` or your own graphic can cover them instead.

Specs: 1080×1920, 9:16, 24 fps, the client's brand fonts only, brand colours only (+ documented derived tints), text in
safe area (x 90–990, y 250–1500), never cover the speaker's face, one primary graphic at a time.
