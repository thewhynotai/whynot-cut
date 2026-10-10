# WhyNot Cut 2.1: Podcast mode (episode → reels plan → reels, plus a publish package)

Date: 2026-10-11 · Status: approved in conversation (the user waived the separate spec and plan review gates and asked
for end-to-end execution) · Plugin: `whynot-cut` 2.0.0 → 2.1.0

## ملخص بالعربي
بلاجن واحدة. الحلقة المتمنتجة (16:9) بتتحط في `data/Episodes/`، وجنبها اختياري episode sheet. الحلقة بتتفرّغ مرة
واحدة على أجزاء فيها checkpoints. الـ `episode-analyst` بيطلّع خريطة المواضيع والأدوار ومرشحين للريلز بالـ timecode
والنوع والدرجة، والـ engine بيراجعهم بالكود. المونتير بيختار في Gate 0، وكل ريل بيبقى مشروع عادي بيشاور على جزء من
الحلقة (source window)، وبيكمّل الـ pipeline الحالي بوصفة نوع المحتوى بتاعه، وبـ reframe لكل لقطة، وبـ build في Premiere،
وبـ QC. باكدج النشر (يوتيوب + سوشيال + ثمبنيل) ملفات بس، ومتراجعة بالكود. مفيش رفع على أي منصة.

## 1. Goal and success criteria
An agency editor drops a finished podcast episode into a client folder and gets, with two human decisions (Gate 0: which
reels; Gate 1: approve the reel plans):
1. a validated **reels plan**: 8–15 candidates per hour, each with exact in/out timecodes snapped to sentence
   boundaries, a content type, a hook, a score with reasons, a "needs context" flag and risks, plus a quick 9:16 preview
   per candidate;
2. for every selected reel, the existing WhyNot Cut result: cleaned dialogue with pauses removed (with proof), brand
   graphics and captions, a preview MP4, a native Premiere project and evidence-based QC. The reel's edit follows a
   **content-type recipe**, and a **per-shot 9:16 reframe** follows the speaker;
3. a **publish package**: YouTube titles, description, chapters, tags and an SRT for the episode; captions and hashtags
   for Instagram, TikTok and Shorts for each reel; thumbnail frame candidates plus three rendered thumbnail designs. Every
   item is checked by code against platform limits and the episode's own facts.

Success means:
- The test suite is green, with the existing tests unchanged, and new tests cover every engine rule below.
- A live run on this PC (Windows 11, Premiere 26.5) takes a real 16:9 podcast excerpt through the whole chain:
  transcript, plan, selection, reel build, QC pass, then `publish-check` pass.

## 2. Decisions taken
| Topic | Decision | Why |
|---|---|---|
| One plugin or two | One plugin with a podcast mode (`/whynot-cut:podcast`) | After Gate 0 a reel *is* a clip. A fork would duplicate the engine, the Premiere bridge (two CEP panels on one queue) and every fix |
| Brain vs Adobe panel | Claude Code is the brain and builds Premiere projects through the existing bridge | Works today; an in-Adobe UI panel is a later project |
| Input | The finished, edited episode as one 16:9 file in `data/Episodes/`; optional sheet `<stem>.md` | Most common agency input; raw multi-cam is out of scope |
| Reel ↔ episode | Approach A: a reel is a *source window* `[in, out)` of the original episode file; every project clock starts at 0 = the reel's in-point | Premiere links to the original media with handles; the editor can adjust the crop and in/out; no re-encode |
| Who picks reels | The editor, at Gate 0 (`reels-select --by editor`; `--by delegated` only when the editor said so in chat) | User's choice |
| Content type | Changes pacing, camera, captions, graphics, SFX, music mood and copy tone through `recipes.json` | User chose all four effects |
| Speakers | Turn-level roles inferred by the analyst (marked `inferred`); no pyannote in 2.1 | Avoids torch (~2 GB) and a HF token |
| Two-shot framing | Follow the speaker (crop on whoever talks, minimum hold 1.5 s); unknown speaker → whole frame over blurred fill | Single layer, editable; split-screen needs a bridge feature not yet verified |
| Publish | Files only; checked by code; no upload | Upload needs OAuth and is outward-facing |
| Thumbnail PSD | PNG designs always; layered PSD is not part of 2.1 (Photoshop stays an opt-in extra) | Keeps Photoshop opt-in; PNGs cover the need |
| Platform limits | `config/defaults/platform-limits.json` | Platforms change rules often |

Out of scope: full motion/animation videos (phase 3, own spec), YouTube upload, split-screen, pyannote, an Adobe UI
panel, raw multi-cam input, layered thumbnail PSD.

## 3. Folder layout and data formats

### 3.1 Client folder
```
data/Episodes/EP12.mp4     finished episode (16:9)
data/Episodes/EP12.md      optional episode sheet
```
`discover` classifies videos under `data/Episodes/` as role `episode` and documents there as `episode_sheet`. Episodes
are never `source_footage`, so clip-only flows (video-id auto-detection, `inbox` clips) ignore them. `scaffold` creates
`data/Episodes/` and START_HERE.md documents it in English and Arabic. `inbox` lists episodes with their state
(new / transcribed / planned / N reels selected) and warns when a `data/Raw` file is ≥ 10 min and 16:9 ("looks like an
episode: move it to data/Episodes").

### 3.2 Episode sheet (`<stem>.md`)
YAML-like frontmatter (flat keys, inline `[a, b]` lists or `- item` lists), then free notes:
```
---
show: اسم البرنامج
episode: 12
host: اسم المذيع
guest: "الاسم — الصفة"
links:
  - https://instagram.com/guest
sponsor: ""
avoid: [السياسة]
language: ar
---
notes…
```
The sheet text is the only source for names, links and the sponsor in published copy.

### 3.3 Episode project `output/episodes/<EP>/`
`<EP>` = `slug(file stem)`. An `EpisodePaths(Paths)` subclass reuses every `paths.p()` helper.
```
00_inputs/episode.json          probe summary, fingerprint, parsed sheet + raw sheet text, time estimate
00_inputs/intake/               6 evenly spaced frames + _intake_sheet.jpg (for intake-inspector)
00_inputs/intake.json           written by the lead from intake-inspector's report (burned subtitles/logo, layout)
02_transcription/               same files as a clip (transcript/words/srt/captions-short/review) + chunks/
01_analysis/topics.json         authored by episode-analyst
01_analysis/speakers.json       authored by episode-analyst
01_analysis/reels-plan.json     authored by episode-analyst
01_analysis/reels-plan-validated.json, reels-plan.md, reels-plan-validation.json   engine
01_analysis/selection.json      Gate 0 record (engine, lead only)
03_candidates/R01.mp4 R01.jpg _sheet.jpg   candidate previews (engine)
publish/publish.json            authored by publish-writer
publish/reels/<REEL>.json       authored by publish-writer (one per reel)
publish/youtube.md chapters.txt tags.txt <EP>.srt reels/<REEL>.md publish-validation.json   engine
publish/thumbnail/candidates/*.jpg _candidates.jpg thumb_1..3.png                         engine
08_quality_control/episode-status.json, logs/
```

**intake.json** (lead):
`{"burned_subtitles": false, "burned_logo": "top-right" | null, "lower_thirds": false, "layout": {"host": "left", "guest": "right"}, "clean_export_requested": false, "notes": ""}`

**topics.json**: `{"topics": [{"id": "T01", "start": "00:00:00.000", "end": "00:04:10.000", "title": "…", "summary": "…"}]}`

**speakers.json**: `{"method": "inferred from context and the episode sheet", "people": {"host": {"name": "…", "position": "left|right|center|unknown"}, "guest": {…}}, "turns": [{"start": "…", "end": "…", "speaker": "host"}]}`

**reels-plan.json**:
```json
{"episode_id": "EP12", "candidates": [{
  "id": "R03", "start": "00:12:01.240", "end": "00:13:05.880",
  "type": "success_story", "secondary_type": "emotional",
  "title": "…", "hook_quote": "<first spoken line, verbatim>", "hook_text": "<suggested on-screen hook>",
  "evidence": "<first 4–12 words, verbatim>", "end_evidence": "<last 4–12 words, verbatim>",
  "why": "…", "score": {"hook": 8, "standalone": 7, "payoff": 9, "ending": 8},
  "needs_context": false, "context_line": "", "speakers": ["guest"], "risks": []}]}
```

### 3.4 Reel project `output/projects/<EP>_<RID>/`
A normal clip project plus:
- `00_inputs/source.json`:
  `{"kind": "episode_reel", "episode_id", "reel_id", "path", "rel", "fingerprint", "in_ms", "out_ms", "offset_ms", "duration_ms", "content_type", "secondary_type", "recipe": {…resolved…}, "candidate": {…}, "intake": {…}, "selected_by", "selected_at"}`
- `00_inputs/speakers.json`: the turns inside the window on the reel clock, plus `people`.
- `02_transcription/*`: sliced from the episode transcript (word times minus `in_ms`, ids renumbered,
  `episode_word_id` kept, flags kept), plus a sliced `dialogue_16k_mono.wav`. If the episode transcript was verified,
  the reel gets its own `verification.json` ("by": "episode verification").

## 4. Engine

### 4.1 Source window (`lib/source.py`)
`window(paths) → {"path", "offset_ms", "duration_ms", "episode_id", "reel_id", "windowed": bool}`. A plain clip is
`offset 0`, its full duration, `windowed: False`. Every media read goes through it:

| Place | Change |
|---|---|
| `cli.main_footage` | windowed → the episode file |
| `media.preflight` | probe the file; record `window`; windowed → per-shot analysis inside the window (4.4) instead of the global reframe; `reframe[file]` = cover scale, offset 0, `mode: per-shot` |
| `audio_clean.clean` | extract with `-ss offset -t duration` (ffmpeg accurate seek, sample exact) |
| `preview_video` | decoder and camera-audio extraction seek to the window |
| `previews.render_all` | composite frames at `offset + source time` (also fixes sequence-vs-source time after pause removal) |
| `verify.build` | source frame grabs add the offset |
| `premiere_xml` | V1, cutaway and original-camera-audio in-points add the offset; the cleaned dialogue (reel clock) does not; the `<file>` duration stays the full episode (handles) |
| `qc` | sync check compares A1 against V1 minus the offset when A1 is the reel-clock clean file; new checks: first V1 in-point equals the reel in-point, window inside the episode |
| `cmd_transcribe` | windowed → refuses ("sliced from the episode; re-slice with `reels-select --resync`") |

### 4.2 Chunked episode transcription (`lib/episode.py`)
1. Extract a 16 kHz mono WAV once.
2. Plan chunks of about `chunk_minutes` (default 10). Each boundary goes at the quietest 50 ms window within ±20 s of
   the target (pure function `plan_chunks`).
3. Per chunk without a checkpoint, run Whisper on the slice, with `vad_filter` on for episodes (`podcast.json`
   `episode_vad`). Offset the times and write `chunks/chunk_NNN.json`. The language is detected on chunk 1 and reused.
4. Stitch: renumber words and segments, then `finalize()` writes the standard files; the machine copies are kept.
   `--force` clears the checkpoints.
5. GPU → CPU fallback as for clips. `episode-prep` prints a rough time estimate (GPU vs CPU, model).

### 4.3 Reels plan (`lib/reels.py`)
`compile_reels_plan(ep)` validates `reels-plan.json` against the episode transcript, `podcast.json`, `recipes.json`,
the sheet and the optional `speakers.json` and `topics.json`.
- **Ids:** unique, `R\d+`.
- **Times:** parse; must be inside the episode.
- **Type:** `type` must be in the recipe types; `secondary_type` is optional but must also be a type.
- **Evidence:** the `evidence` tokens must appear (normalised) in words starting within ±3 s of `start`;
  `end_evidence` within ±3 s of `end`. Errors otherwise.
- **Snap in:** the in-point snaps to the nearest sentence-like word start within ±1.5 s: a segment start, after a
  word ending in `. ? ! ؟ …`, or after a gap ≥ 300 ms. `in = word.start − lead_in_ms (120)`, never before the
  previous word's end + 20 ms.
- **Snap out:** the out-point snaps the same way to a word end. `out = word.end + tail_ms (250)`, never after the
  next word's start − 20 ms.
- **Duration:** warning outside 30–90 s; error outside 15–180 s (configurable).
- **Overlap:** warning when an overlap exceeds 50 % of the shorter candidate.
- **`avoid` terms:** any normalised hit in the window's text flags `avoid_hits`. Selecting such a candidate needs
  `--confirm-avoid <id>`.
- **Count:** warning when the count is outside 8–15 per hour, scaled to the episode length.
- **Score:** four integers 1–10; the engine computes `total` (mean, one decimal) and sorts by it.
- **Context:** `needs_context: true` without `context_line` → warning. Unknown speakers → warning.
- **Topics** (when present): sorted, non-overlapping, each ≥ 10 s, the first starting ≤ 5 s. Violations are warnings
  here and errors in `publish-check`.
- **Output:** `reels-plan-validated.json` (snapped `in_ms`/`out_ms`, `duration_ms`, excerpt, flags), `reels-plan.md`
  (table by score, with preview paths), `reels-plan-validation.json`.
- A fingerprint of the plan and the transcript words is stored; `reels-select` refuses a stale validation.

`reels-preview`: for each candidate, render a 540×960 H.264 that shows the whole 16:9 frame letterboxed over a dark
background with a Latin label (id · timecodes · type), using the episode audio for the range. Also writes a first-frame
JPG and `_sheet.jpg`.

### 4.4 Gate 0 and reel creation (`reels-select`)
`reel reels-select --episode EP12 --pick R01,R03 [--adjust R03:in=00:12:04.000] [--adjust R03:out=…] --by editor|delegated [--note] [--confirm-avoid R05] [--resync] [--force]`
1. Adjusted edges are re-snapped and re-checked against the duration limits.
2. Writes `selection.json` (history kept) and creates each reel project as in 3.4.
3. Status `TRANSCRIBED` ("sliced from EP12 R03").
4. Re-picking an unchanged window is a no-op. A changed window needs `--force`, which re-slices; downstream steps
   become stale through the existing fingerprints.
5. `--resync` re-slices the transcripts of all selected reels after episode corrections.
6. The guard blocks subagents from running it.

### 4.5 Per-shot reframe (`lib/shots.py`, `plan.py`, `timemap.py`)
- **`detect_cuts`:** ffmpeg scene score inside the window, threshold 0.3. Shots shorter than 400 ms merge into a
  neighbour.
- **`face_boxes(im)`:** every face (macOS Vision, else OpenCV frontal + profile), dropping faces smaller than 30 % of
  the largest.
- **`analyze_window`:** 3 samples per shot give each shot a face count and face x-centres. Stored as
  `preflight.json["shots"]`.
- **`frame_shots(shots, speakers, dims)`** (pure; called by `plan`). Cover scale fills the 9:16 height.

| Faces in the shot | Framing |
|---|---|
| 1 face, or a group whose span fits in 80 % of the crop width | `AUTO_SHOT`, centred on the face or group, clamped so the frame stays filled |
| 0 faces | `AUTO_CUTAWAY`: shown whole over a blurred fill (existing path) |
| ≥ 2 faces that don't fit | Follow the speaker: map positions (left = leftmost face, right = rightmost, center = nearest the middle), split the shot at turn boundaries, merge pieces shorter than 1.5 s into the previous one. An unknown speaker or layout → `AUTO_CUTAWAY` (whole) with the reason |

- **Composition** (`compose_camera`): story-editor camera moves layer over `AUTO_SHOT`:
  `scale = shot × story`, `offset_x = shot_offset × story_scale + story_offset`, clamped to the filled frame.
  `AUTO_CUTAWAY` keeps priority (existing behaviour). Clips without `preflight["shots"]` behave exactly as before.
- **TimeMap:** when a jump-cut mask steps the zoom of a piece that has an offset, the offset scales by the same factor.
- **edit-plan.md:** shows a framing summary; `AUTO_*` entries are not counted as punch-ins.

### 4.6 Recipes (`config/defaults/recipes.json`, profile-overridable)
Types: `storytelling`, `drama`, `success_story`, `advice`, `bold_opinion`, `emotional`, `comedy`. Each type has a label
(en/ar), `pacing {min_pause_ms, pad_ms}`, `camera {max_scale, punch_ins_per_30s, style}`,
`captions {style, highlights_per_30s}`, `graphics {prefer[], avoid[], max_per_30s}`, `sfx {palette[], density}`
(synthesised kinds only), `music {mood[], level_db}` and `copy {tone, hook_style, emoji}`. Default values:

| type | min_pause/pad ms | max_scale · punch-ins/30 s | graphics prefer (max/30 s) | sfx | music mood · dB |
|---|---|---|---|---|---|
| storytelling | 350/100 | 1.15 · 1 | context_card, hook_title (2) | whoosh_soft, riser_soft | warm, curious · −24 |
| drama | 600/160 | 1.20 · 1 | statement_highlight (1) | hit_soft, riser_soft | tense, dark · −26 |
| success_story | 300/90 | 1.15 · 2 | stat_card, hook_title (3) | riser_soft, shimmer | uplifting · −22 |
| advice | 250/80 | 1.12 · 2 | checklist, term_callout (3) | pop, click, tick | light, upbeat · −24 |
| bold_opinion | 250/80 | 1.18 · 2 | hook_title, statement_highlight (2) | hit_soft | minimal · −28 |
| emotional | 800/200 | 1.10 · 1 | — (1) | — | soft piano · −26 |
| comedy | 220/70 | 1.25 · 2 | hook_title (2) | pop | playful · −24 |
- **`audio-clean`:** for a reel, `--min-pause`/`--pad` default to the recipe (else 250/80).
- **`plan`:** non-fatal warnings when graphics per 30 s, camera scale or avoided templates exceed the recipe. A
  decision may carry `recipe_note` to explain a deviation; edit-plan.md lists recipe, deviations and notes.
- **Music:** `edit-decisions.music.file` (must be under `data/Music`) is placed on A06 from 0 to the end at the
  recipe/decision level, with a 2 s fade-out. Status `PLACED`. The preview video mixes it.
- **`reel music --list`:** library tracks with mood tags from `data/Music/music.json` or file-name tokens.

### 4.7 New templates
- `stat_card` (`value`, `label`): big brand-primary value over a glass card with a label. Card lane, `card` animation,
  SFX `shimmer`. Captions are hidden during it by default.
- `context_card` (`text`): a top-safe-area pill (brand primary, white text) that tells a cold viewer what came before.
  Card lane, captions stay on. It is an editorial line, so the Gate 1 summary marks it as such.
- Both render with the existing HarfBuzz path. `plan` requires their fields, and `value` and `label` join the on-screen
  text checks.

### 4.8 Publish (`lib/publish.py`)
- **`publish-check --episode EP12`** validates `publish.json` and `publish/reels/*.json` and renders the human files:
  - **Titles:** ≥ 3 options, each 1–100 characters, no `<` or `>`; warning above 70.
  - **Description:** the assembled description (hook, summary, guest, chapters, links, sponsor, CTA, hashtags) is
    ≤ 5000 characters with no angle brackets; hashtags ≤ 15, each `#` with no spaces.
  - **Chapters** (`youtube.chapters`, else `topics.json`): first `00:00`, ≥ 3, ascending, each ≥ 10 s, all inside the
    episode.
  - **Tags:** total ≤ 500 characters (tags with spaces count their quotes; commas count).
  - **Facts:** every URL must appear in the sheet text, the sheet's guest name must appear in the guest line (warning),
    and any quoted text («…», "…", “…”) must exist in the transcript (normalised).
  - **Approvals:** `approval_required` items are listed.
  - **Per reel:** Instagram caption ≤ 2200 and hashtags ≤ 30, TikTok caption ≤ 2200, Shorts title ≤ 100. All
    numbers come from `platform-limits.json`.
  - **SRT:** the episode SRT is copied and validated.
  - **Output:** writes `youtube.md`, `chapters.txt`, `tags.txt`, `<EP>.srt`, `reels/<REEL>.md` and
    `publish-validation.json`.
- **`publish-thumbnail --episode EP12 --candidates`:** samples about 150 frames at low resolution. Each frame is scored
  on face area, sharpness (Laplacian variance) and contrast. The top 12 with a face, at least 30 s apart, are kept at
  full resolution and labelled on `_candidates.jpg`.
- **`--render`:** draws `publish.json` `thumbnail.designs` (`frame_ms`, `text`, `highlight`) as 1280×720 PNGs:
  face-aware cover crop, a gradient on the text side, the brand headline font (HarfBuzz) with a brand-primary highlight
  bar, and the logo when available. Each PNG is ≤ 2 MB (JPEG fallback). Warning above 5 words.

### 4.9 Episode status
`reel episode-next --episode EP12` lists the remaining steps: prep, transcribe, verify transcript (optional), AUTHOR
topics/speakers/reels-plan, reels-plan, reels-preview, SELECT (Gate 0), the selected reels' own `next`, AUTHOR publish,
publish-check, thumbnail. Stale steps are reported from file times, as `next` does.

### 4.10 CLI
- A global `--episode` option.
- New commands: `episodes`, `episode-prep`, `episode-transcribe`, `reels-plan`, `reels-preview`, `reels-select`,
  `episode-next`, `publish-check`, `publish-thumbnail`, `music`.
- `transcript-correct|verify|relisten` accept `--episode`.
- Episode commands do not need `--video-id`. When `--episode` is missing and exactly one episode exists, that one is
  used.

## 5. Plugin layer
- **Agents (new):**
  - `episode-analyst` (opus; writes topics, speakers and reels-plan; fans out `moment-scout`)
  - `moment-scout` (sonnet, read-only; one ~10-min chunk → candidate moments as JSON in its report)
  - `publish-writer` (opus; writes publish.json and per-reel JSON, runs publish-check)
- **Agents (updated):**
  - `intake-inspector`: an episode checklist (burned subtitles/logo, lower thirds, wide-shot layout)
  - `transcript-editor`: episode chunks
  - `story-editor`: reads `source.json` recipe and context line; new templates
  - `qc-reviewer` and `frame-inspector`: the face is in frame per shot, no burned-subtitle fragments, the framed
    person is the speaker
  - `motion-designer`: the new templates
- **Skills (new):**
  - `podcast` (lead playbook: stages, Gate 0, spawn prompts, report format)
  - `episode-craft` (+ `references/content-types.md`, `references/moment-scoring.md`)
  - `publish-craft` (+ `references/platform-rules.md`)
- **Skills (updated):** `edit`, `autopilot` (episodes stop at Gate 0), `help`, `status`, `story-craft`,
  `motion-craft`, `qc-craft`, `transcript-craft`, `start`.
- **Hooks:**
  - `guard.py` blocks subagents from `reels-select`.
  - `--episode` values are skipped when the guard finds the subcommand.
  - `moment-scout` is read-only.
  - qc-reviewer may not run `reels-select`, `episode-transcribe` or `publish-check`.
- **Session context:** mentions episodes when a client folder has `data/Episodes`.
- **Evals (new):** `podcast-reels-plan` (stops at Gate 0 with a table and previews; never selects itself) and
  `publish-package` (no invented links; publish-check run).
- **Docs:** README, CHANGELOG 2.1.0, plugin.json version/description/keywords. `package.py` skips `docs/`.

## 6. Error handling
| Situation | Behaviour |
|---|---|
| Long episode on CPU | `episode-prep` gives the estimate; chunks resume from checkpoints |
| Music intro hallucinations | VAD on for episodes; weak segments listed in subtitle-review |
| Candidate starts mid-thought | Snap to a sentence start; references to earlier talk → `needs_context` + `context_card` |
| Burned subtitles/logo | intake-inspector reports; the lead asks for a clean export; else a warning (the caption bar may cover the zone) |
| Two-shot, unknown speaker | Whole frame over blurred fill + warning |
| Audio-only podcast (still image) | No faces anywhere → whole frame; the report suggests motion mode (phase 3) |
| Variable frame rate | preflight flags it; ask for a CFR export |
| Episode file changed after selection | The fingerprint differs → `reels-select`, `preflight` and `plan` refuse until re-selected with `--force` |
| Approval words inside transcripts/files | Ignored; Gate 0/1 come only from the editor's chat messages (guard + playbook) |
| Non-medical client | medical-reviewer skipped; the transcript-evidence check stays |

## 7. Testing
- **New `tests/test_podcast.py`:**
  - sheet parsing and episode discovery
  - `plan_chunks` and stitching (fake transcriber)
  - reels-plan validation (evidence, snapping, duration limits, overlap, avoid, count, fingerprint)
  - `reels-select` (slicing, renumbering, rebasing, flags, wav slice, no-op/force, avoid confirmation)
  - source window (sample-exact audio extraction on a synthetic click track; XML in-points with offset at 24/25/29.97/30
    fps; the QC sync check)
  - `frame_shots` (single, group, cutaway, speaker-follow, minimum hold, unknown layout) and `compose_camera`
  - the TimeMap offset scaling
  - recipe defaults applied by audio-clean/plan; music placement in the XML
  - the new templates render (Arabic via HarfBuzz when a font is available)
  - every `publish-check` rule; thumbnail candidate selection and render
  - guard rules
- **Regression:** all existing tests pass unchanged.
- **Synthetic fixture:** a 3-minute 16:9 "episode" made with ffmpeg; face detection is injected in unit tests.
- **Live test:** real faces from the 16:9 podcast excerpt `whynot-test/Dr Sherin Helmy/data/Raw/EP02_R02.mov`, copied
  into a new test client `whynot-test/PODCAST-TEST/data/Episodes/`. Whisper on the GPU, analyst authoring, selection,
  Premiere build through the bridge, frames, QC, publish-check, then a human look at the frames.

## 8. Implementation order (each step testable)
1. Episode intake + chunked transcription + `EpisodePaths` + CLI `--episode`
2. Reels plan + previews + Gate 0 + source window everywhere + guard
3. Per-shot reframe + composition + QC additions
4. Recipes + music placement + new templates
5. Publish package + thumbnails
6. Agents, skills, evals, docs, version 2.1.0, package
7. Live verification on this PC
