# WhyNot Cut 2.2: Motion from audio (episode window → animated After Effects video)

Date: 2026-10-11 · Status: designed by Claude under the user's standing "decide and continue" instruction (spec and
plan review gates waived for podcast-mode work); every decision below says why, so it can be overridden ·
Plugin: `whynot-cut` 2.1.0 → 2.2.0 · Phase 3 of podcast mode (phase 1 spec:
`2026-10-11-podcast-mode-design.md`, which deferred "full motion/animation videos" to this spec)

## ملخص بالعربي
نفس البلاجن، مود جديد اسمه **motion**. المونتير في Gate 0 بيختار ريل (أو موضوع من خريطة المواضيع) ويقول
`--as motion`، فبيتعمل مشروع جديد `EP12_R03_MO` مبني على **صوت** الجزء ده بس (الكلام + فهم Claude للسياق)، من غير
ولا لقطة كاميرا، فبيشتغل كمان مع البودكاست الصوتي بس. الصوت بيتنضف وبتتشال الوقفات بنفس الـ audio-clean. وكيل جديد
`motion-director` بيكتب `motion-script.json`: الحلقة بتتقسم beats حسب نوع المحتوى (حكاية، دراما، قصة نجاح…) وكل beat
بيبقى مشهد من 12 نوع ثابت (كلام متحرك متزامن مع الصوت كلمة بكلمة، عنوان، رقم بيعد، أيقونة + فكرة، خطوات، مقارنة،
تايم لاين، اقتباس، كارت سياق، كارت ضيف، رسمة مرخصة، خاتمة). الكود بيراجع كل كلمة على الشاشة إنها من كلام المتحدث
نفسه أو معلّمة إنها سطر تحريري، وكل رقم إنه اتقال، وكل اسم إنه من الـ sheet. قبل After Effects بيطلع animatic
(فيديو تقريبي بالصوت) للموافقة في Gate 1. بعدها Claude بيبني مشروع **After Effects أصلي** بنفسه: بيانات + مكتبة
ExtendScript بتتشغل جوه AE عن طريق نفس **WhyNot Cut Bridge** (بقى بيشتغل في Premiere و AE) وبيقرا المشروع تاني
(النصوص، الخطوط، اتجاه RTL، أماكن النصوص). الأيقونات من Lucide (رخصة ISC) بتتحول لـ shape layers أصلية، والرسومات
بس من مكتبة مرخصة فيها ملف رخصة. الـ render بـ aerender، والـ QC من فريمات AE نفسه. والتسليم: ملف .aep قابل
للتعديل + فيديو MP4 + كابشنز النشر. ممنوع نكتب أي إعدادات Adobe، و `assets/` و `data/` قراءة بس.

## 1. Goal and success criteria
An agency editor picks a window of a podcast episode at Gate 0 and asks for it "as motion". They get, with the usual two
human decisions (Gate 0: which windows; Gate 1: approve the motion plan):
1. an **animated video built from the audio only**: cleaned dialogue, pauses removed with proof, and a sequence of
   animated scenes driven by what is said — Arabic-first right-to-left kinetic typography synced word by word, icons,
   stat counters, steps, comparisons, timelines, quote and person cards, licensed illustrations, brand backgrounds,
   optional captions and a speaker badge — paced and styled by the window's **content-type recipe**;
2. a **native, editable After Effects project** that Claude builds itself (one comp per scene, brand colour controls,
   live text, native shape-layer icons, the audio laid in), plus a rendered master and an H.264 MP4 with audio;
3. **evidence-based QC**: AE's own read-back of the built project (text, fonts, direction, layout boxes) and frames
   rendered by AE, inspected against the plan; and the reel's captions in the existing **publish package**.

Success means:
- The test suite is green, with the existing tests unchanged, and new tests cover every engine rule below.
- An **Arabic capability probe** runs on this PC (Windows 11, After Effects 2026) through the bridge and its rendered
  frames show joined Arabic, right-to-left word order and a word-synced reveal that starts with the first spoken word.
- A live run on this PC takes the `whynot-test/PODCAST-TEST` episode through Gate 0 `--as motion`, motion script,
  plan, animatic, Gate 1, AE build through the bridge, read-back, render, frames viewed, `qc` pass, and `publish-check`
  pass with the motion reel's captions.

## 2. Decisions taken
| Topic | Decision | Why |
|---|---|---|
| One plugin or two | Still one plugin; motion is a mode of podcast mode (`/whynot-cut:motion`) | Shares the episode transcript, Gate 0, recipes, audio cleanup, brand DB, bridge, QC and publish |
| Input unit | A **window** of the episode chosen at Gate 0: an analyst reel candidate (`R03`) or a topic from the topic map (`T02`), 15–180 s; `reels-select --as motion` | Reuses snapped windows, transcript slicing and fingerprints. Animating a whole episode is a different product (hundreds of scenes, hours of render) — deferred |
| Picture source | None. Only the window's audio, its words, the speaker turns, the episode sheet and the client's brand | The user's brief ("audio only"); also makes audio-only podcasts usable |
| Audio-only episodes | `.mp3 .wav .m4a .aac .flac` in `data/Episodes/` become episodes; they can only be picked `--as motion` | Phase 1 told such clients "suggests motion mode"; now it exists |
| Output formats | `9x16` (1080×1920, default) and `16x9` (1920×1080) | Reels and YouTube; each format needs layout presets for every scene type, so 4:5 and 1:1 wait |
| Frame rate | The client's sequence rate (`seq_fps()`), as for every other deliverable | One clock everywhere (TimeMap, captions, QC) |
| Who authors | New `motion-director` agent (opus) writes `motion-script.json`; the engine validates and compiles it | Claude is the brain; the engine checks facts and does all timing and layout math |
| Story beats → scenes | Each content-type recipe gains a `motion` block: beat grammar, preferred/avoided scene types, scene lengths, reveal mode, easing, transition, theme, captions, SFX | The user decided content type drives pacing, graphics, music/SFX and copy tone |
| Visual vocabulary | A closed set of 12 parametric scene types plus 5 persistent layers, implemented once in an ES3 library | Testable and consistent; Claude composes scenes from data instead of writing free JSX per video |
| Text truth | Speech text = an in-order subsequence of the words spoken in the scene (fillers may be dropped, nothing added); editorial lines are allowed only in marked fields and shown at Gate 1; numbers must be spoken; names come only from the sheet | Same non-negotiables as phase 1 |
| Assets | Client brand DB (colours, fonts, logo, photos) + shipped **Lucide** icons (ISC) converted to native shape layers + optional licensed illustration packs from an agency motion library with a license manifest. Nothing generated, nothing fetched at run time | Licensed only; `assets/` and `data/` stay read-only |
| AE build path | Generated data + ES3 scene library, executed inside AE through the **WhyNot Cut Bridge** (one CEP bundle, now host-aware: Premiere and AE, separate queues); `AfterFX.exe -r` / AppleScript only as a files-only fallback | Return channel and read-back evidence, no modal-dialog dead ends, same proven design as Premiere (§5.1) |
| Arabic in AE | Universal composer + RTL per layer, `fontObject` from `app.fonts`, word animation by expression selectors; an on-machine probe records capabilities and picks the fallbacks | Known quirks (the `direction` persist bug reported on AE 25.2, word-index order for RTL) must be measured, not assumed |
| Preview before AE | An **animatic** (storyboard stills + MP4 with the audio) for Gate 1 | Approve the story before spending AE build and render time; mirrors `preview-video` |
| QC | Bridge read-back + `aerender` master + frames at planned moments + frame-inspectors + engine checks | Evidence from AE itself, as Premiere QC uses Premiere's frames |
| Deliverable | `.aep` + ProRes master + H.264 MP4 + handoff; the editor finishes in AE | The motion video is born in AE; Premiere wrapping (Dynamic Link) is not needed |
| Extras gate | Motion commands do not need `--extras`: picking `--as motion` at Gate 0 is the editor's explicit request for AE. The old `ae-*` graphics extras keep their gate | The guard stays meaningful without blocking the mode the editor chose |
| UXP | CEP now | UXP for After Effects is still in beta; CEP works in AE 2026 |
| Adobe preferences | Never written (PlayerDebugMode, the AE Type text-engine preference, scripting security). Claude gives the editor the step | Standing constraint |

Out of scope: whole-episode or > 180 s animation, 4:5 and 1:1, generated images or illustrations, character
animation or lip sync, 3D, stock footage, Lottie export, Premiere wrapping of the motion render, UXP, upload.

## 3. Folder layout and data formats

### 3.1 Episode side
- `discover`: audio files under `data/Episodes/` get role `episode` (with `media: "audio"`); video episodes get
  `media: "video"`.
- `episode-prep` for an audio episode: probe, no aspect warning, no intake frames, `episode.json["media"] = "audio"`.
  The intake-inspector is skipped.
- `reels-preview` for an audio episode: a 540×960 card (label + the window's waveform) with the window's audio.
- `reels-plan.json` candidates may carry `"motion_fit": true` and `"motion_why": "…"` (optional, the analyst's view
  that the moment works as animation: abstract ideas, numbers, steps, or no usable picture). `reels-plan.md` shows a
  "motion" flag. `topics.json` topics may carry an optional `type` (a recipe type).

### 3.2 Gate 0 for motion
`reel reels-select --episode EP12 --pick R03,T02 --as motion [--format 9x16|16x9] [--type advice] --by editor|delegated …`
- `--as video|motion` (default `video`) applies to every pick in the call. A video pick from an audio episode is
  refused ("no picture: use --as motion").
- `T\d+` ids are accepted only with `--as motion`. Their edges come from `topics.json`, snapped with
  `snap_in`/`snap_out`, then checked against the hard duration limits (15–180 s). Longer topics are refused with
  "split it: pick a reel candidate inside it or move the edges with --adjust".
- Content type: an `R` pick keeps its candidate type; a `T` pick uses the topic's `type`, else `--type`, else it is
  refused with the list of types.
- The project id is `f"{EP}_{ID}_MO"` (e.g. `EP12_R03_MO`), so a video reel and a motion version of the same
  candidate can coexist. `selection.json` history entries record `as` and `format`.
- Everything else is unchanged: `--adjust`, `--force`, `--resync`, `--confirm-avoid`, the guard (subagents blocked),
  and the no-op for an unchanged window.

### 3.3 Motion project `output/projects/<EP>_<ID>_MO/`
An ordinary clip project (`Paths`) with:
```
00_inputs/source.json                 kind "motion_reel" (fields below)
00_inputs/speakers.json               turns on the reel clock + people (as for reels)
02_transcription/*                    sliced from the episode (as for reels)
06_audio/dialogue/*                   audio-clean output (existing layout, pauses.json, cut proof)
06_audio/sfx/*                        synthesised SFX (existing sfx.py kinds)
01_analysis/motion-script.json        AUTHORED by motion-director
01_analysis/motion-plan.json          compiled by the engine (frames, cues, layout, assets, audio)
01_analysis/motion-plan.md            human-readable plan for Gate 1
01_analysis/motion-validation.json    errors, warnings, approvals, editorial lines
01_analysis/plan-approval.json        Gate 1 (approve-plan, fingerprint of motion-plan.json)
08_quality_control/animatic/          S01.png …, _storyboard.jpg, <ID>_animatic.mp4
04_after_effects/data/motion-job.json the bridge data file (ASCII JSON)
04_after_effects/scripts/build_<ID>_motion.jsx   self-contained fallback script (SCRIPT_ONLY / -r)
04_after_effects/project/<ID>_<PREFIX>_MOTION.aep
04_after_effects/project/backups/     editor-changed .aep copies kept before a forced rebuild
04_after_effects/motion-build-result.json   build + read-back report
04_after_effects/render/<ID>_MAIN.mov, <ID>_motion.mp4, <ID>_cover.jpg, pieces/<ID>_S03.mov
08_quality_control/ae_frames/run-<stamp>/   F001_S01_hero.png …, frames.json, _sheet.jpg
08_quality_control/visual-verification.json, qc-results.json
09_handoff/README.md
```

**source.json** (motion): the episode-reel fields (`footage`, `in_ms`, `out_ms`, `duration_ms`, `offset_ms`,
`episode_id`, `fingerprint`, `content_type`, `secondary_type`, `recipe` with its `motion` block, `context_line`,
`selected_by`, `selected_at`, `note`) plus `"kind": "motion_reel"`, `"source_id": "R03"|"T02"`, `"format": "9x16"`,
`"media": "video"|"audio"`, `"language"` and `"direction": "rtl"|"ltr"` (from the sheet `language`, else the
transcript language; Arabic and other RTL scripts → `rtl`), and `candidate` or `topic`. `source_range()` already
reads it, so `audio-clean` works unchanged (it maps only the first audio stream).

### 3.4 `motion-script.json` (authored)
```json
{"reel_id": "EP12_R03_MO", "theme": "dark", "captions": "subtitles",
 "beats": [{"id": "B1", "role": "hook", "summary": "…"}],
 "scenes": [
  {"id": "S01", "beat": "B1", "type": "kinetic_quote", "at": "@start",
   "text": "<speaker words>", "emphasis": ["<word>"]},
  {"id": "S02", "beat": "B2", "type": "stat_counter", "at": "<first 2–12 words spoken when it starts, verbatim>",
   "value": "3", "unit": "مليون", "label": "<label>", "evidence": "<the spoken words with the number, verbatim>"},
  {"id": "S09", "type": "outro", "at": "@end", "cta": "<editorial line>"}],
 "music": {"file": "data/Music/warm_curious.wav", "level_db": -24},
 "notes": "…"}
```
Common scene fields: `id` (`S\d+`), `type`, `beat` (a beat id), `at` (`@start` for the first scene, `@end` for an
outro after the speech, otherwise verbatim words), optional `transition_in`, `sfx` (synthesisable kinds), `theme`,
`captions` (`on|off`), `recipe_note` (why it deviates from the recipe). The top-level `theme` and `captions` override
the recipe for the whole video; a scene's own value overrides both for that scene. `music` is optional (no fitting
licensed track → the music stays for the editor, as in phase 1).

### 3.5 Scene types (the visual vocabulary)
| Type | Fields (required · optional) | Text source | Typical beats |
|---|---|---|---|
| `kinetic_quote` | `text` · `emphasis[]`, `reveal` (word/line), manual `\n` breaks | speech | hook, statement, peak, punchline |
| `title_card` | `title`, `title_source` · `eyebrow`, `subtitle` | speech or editorial | hook, chapter |
| `stat_counter` | `value`, `evidence` · `prefix`, `suffix`, `unit`, `label`, `icon`, `count_up` | number spoken; label speech or editorial | milestone, result |
| `icon_point` | `icon`, `text`, `text_source` · `draw_on` | speech or editorial | idea, reason |
| `list_steps` | `items[{text, at}]` (2–5) · `title`, `numbered`, item `icon` | speech (items) | steps, tips |
| `comparison` | `first{label, points[≤3]}`, `second{…}` · `icon`s, `verdict` | speech or editorial | before/after, myth/fact |
| `timeline` | `points[{label, when, at}]` (2–5) | speech | journey, milestones |
| `quote_card` | `text`, `attribution` (`host`/`guest`) | speech; name from the sheet | emotional peak, drama |
| `context_card` | `text` | editorial | context for a cold viewer |
| `person_card` | `who` (`host`/`guest`) · `photo` (an `asset-manifest` image) | name and role from the sheet | introduction |
| `illustration_scene` | `illustration` (`pack/item`) · `text`, `text_source` | speech or editorial | scene-setting |
| `outro` | `cta` · `show_logo`, `show_name` | editorial; show name from the sheet | end |

Persistent layers (in the MAIN comp, recipe-controlled, overridable in the script):
- `background`: theme colours with a slow gradient drift and light grain.
- `captions`: sequence-clock subtitle cues from `captions-short`, hidden while a scene shows the spoken words
  (`kinetic_quote`, `quote_card`, `list_steps` items, `timeline` labels with speech source).
- `speaker_badge`: a small pill with the current speaker's name (sheet) from the turns; hidden for a single speaker.
- `progress`: a thin bar that fills in the reading direction.
- `voice_pulse`: a ring or bars driven by the dialogue's per-frame loudness (useful for audio-only shows).

**Direction.** Everything that means "next" or "more" moves or grows toward the reading end: in RTL, timelines draw
right → left, progress fills right → left, list numbers sit on the right, `comparison.first` is the right panel, and a
push transition brings the next scene in from the left (the mirrored phone-UI convention). Scene code never hardcodes a
side; it reads `dir` (−1 for RTL, +1 for LTR) from the plan. Directional icons (configured list: arrows, chevrons,
trending, send, reply, undo/redo…) are mirrored in RTL unless the scene sets `"mirror": false`.

### 3.6 Recipe `motion` blocks (`recipes.json`, profile-overridable)
Each type gains: `beats` (grammar, ordered roles), `scene_s {min, target, max}`, `prefer[]`, `avoid[]`,
`reveal` (word | line), `ease` (smooth | snappy | bouncy | gentle), `transition` (cut | push | wipe | scale | fade),
`theme` (dark | light | brand), `captions` (off | subtitles), `speaker_badge`, `progress`, `voice_pulse`,
`max_words_on_screen`, `emphasis_per_scene`, `sfx_on_transition`. Defaults:

| type | beats | scene s (min/target/max) | prefer | reveal · ease · transition | theme | sfx on transition |
|---|---|---|---|---|---|---|
| storytelling | hook, setup, turn, payoff | 2.5/5/9 | title_card, kinetic_quote, timeline, icon_point, context_card | word · smooth · push | light | whoosh_soft |
| drama | hook, tension, peak, aftermath | 2/4/8 | kinetic_quote, quote_card | word · snappy · cut | dark | hit_soft (peak only) |
| success_story | result, before, struggle, milestone, lesson | 2/4/7 | stat_counter, timeline, title_card | word · snappy · push | brand | riser_soft before a stat, shimmer after |
| advice | hook, problem, steps, takeaway | 2/3.5/6 | list_steps, icon_point, comparison | word · snappy · wipe | light | tick per item |
| bold_opinion | claim, reasons, claim_again | 2/3.5/6 | kinetic_quote, title_card | word · snappy · scale | dark | hit_soft |
| emotional | moment, reflection | 3.5/6/12 | quote_card, kinetic_quote | line · gentle · fade | dark | none |
| comedy | setup, beat, punchline, tag | 1.5/3/6 | kinetic_quote, icon_point | word · bouncy · scale | brand | pop |

Captions default `subtitles` except drama and emotional (`off`); `speaker_badge` on when the window has two speakers;
`progress` off; `voice_pulse` on for audio episodes only; `max_words_on_screen` 12 (emotional 18);
`emphasis_per_scene` 2 (bold_opinion 3, emotional 1). The existing `music.mood` and `copy` blocks are reused as they are.

### 3.7 `config/defaults/motion.json` (profile-overridable)
Formats with size and safe area (9x16: top 250, bottom 420, sides 90 px; 16x9: top 90, bottom 120, sides 160 px),
text-box widths and font-size ranges per scene type, `scene_lead_ms` 150 (a scene starts this long before its first
word), `word_reveal_ms` 180, `transition_ms` per transition type, `outro_ms` 2500, `min_contrast` 4.5 (3.0 for text
≥ 64 px), `max_drop_ratio` 0.4 (the share of spoken words a speech text may leave out), `rtl_mirror_icons`, `themes`
(dark = ink background, white text, primary accent; light = paper background, ink text, primary accent; brand =
primary background, white text, ink accent), `render {rs_template: "Best Settings", om_template: "High Quality"}`,
`library_dir` (default `<engine home>/library/motion`), and `fallback_fonts` (used only with the editor's OK).

## 4. Engine

### 4.1 Motion plan compiler (`lib/motion_plan.py`)
`compile_motion(paths) → dict` reads `motion-script.json`, the sliced words, `pauses.json` (TimeMap), the recipe,
`motion.json`, the sheet facts (`source.json` → episode), the brand DB and the asset manifest. Pure helpers are unit
tested one by one.
- **Scene anchors:** `at` evidence is matched (normalised with `plan.norm`) in order, each search starting after the
  previous scene's anchor. Scene start = first word start − `scene_lead_ms`, clamped to 0; scene end = next scene start;
  the first scene starts at 0; the outro starts at the end of the last word and lasts `outro_ms`. Missing or out-of-order
  anchors are errors.
- **Speech text:** tokens of a speech field must be an in-order subsequence of the words spoken inside the scene
  (± 1.5 s at its edges), with at most `max_drop_ratio` of those words left out and no token added. Each shown token
  keeps its word id and time.
- **Editorial text:** allowed only in the fields the table marks editorial. It may not contain quotation marks or
  digits absent from the window's words. People and the show are written as `{host}`, `{guest}` and `{show}`, which
  the engine fills from the sheet (a placeholder the sheet cannot fill is an error); code cannot recognise other names
  in free Arabic text, so the agent rule and Gate 1 cover them. Every editorial line goes to
  `motion-validation.json["editorial_lines"]` and the Gate 1 summary.
- **Numbers:** `stat_counter.evidence` must be found inside the scene. The digit string of `value` (separators
  removed, Arabic-Indic digits mapped to Western) must appear in the evidence's digit string mapped the same way;
  otherwise the scene goes to `approval_required` ("number written from the spoken words «…»: confirm"). The same check
  applies to digits in `timeline.when`.
- **Names:** `quote_card.attribution` and `person_card.who` resolve to the sheet's host/guest; a missing name is an
  error. `person_card.photo` must be an image in the asset manifest.
- **Recipe checks** (warnings unless noted): scene durations against `scene_s`, types in `avoid`, beat roles outside
  the grammar, the first scene not a hook role, emphasis count, words on screen over `max_words_on_screen` (error at
  1.5×). `recipe_note` silences one warning and is listed in the plan.
- **Timing:** source ms → sequence ms through `TimeMap` (pause removal) → frames at `seq_fps()`. Each shown token gets
  a cue frame (its word start); list items, timeline points and stat counts get theirs from `at`/`evidence`. Each scene
  gets `hero_frame = min(last cue + word_reveal_ms + 6 frames, end_frame − next transition frames − 1)`, the moment
  every element is on screen; a scene whose hero frame would fall before its last cue is an error ("too short for its
  content"). A scene's layer in MAIN runs from its start to its end plus the next scene's transition length; the next
  scene's `transition_in` plays over that overlap. MAIN lasts until the outro ends (or the dialogue ends when there is
  no outro).
- **Layout fitting:** every text element is wrapped with the balanced wrapper (`ae_builder.wrap_lines`, extended to
  never split a Latin term, a number with its unit, or "ال" + a Latin term), then measured with HarfBuzz using the
  brand font **file** at the largest size of the scene's range that fits the format's text box; below the minimum size
  it is an error ("too long: split the scene"). Positions come from per-type layout presets in `motion.json`.
- **Contrast:** text and accent colours against the theme background (WCAG ratio). Below the threshold the compiler
  switches text to ink or white; if neither reaches it, error.
- **Captions:** cues from `captions-short-seq.srt` (or the sequence clock), minus the ranges where the scene shows the
  same words.
- **Assets:** icons resolve in the icon index; illustrations in a licensed pack (§4.3); photos in the asset manifest.
  Each used asset is listed with its license in `motion-plan.json["assets"]`; CC-BY assets add an attribution line.
- **Audio:** the cleaned dialogue (sequence clock), music (`data/Music` only, recipe level, 2 s fade-out), SFX cues
  (transition and scene SFX from the recipe, synthesised with `sfx.synth`), the per-frame dialogue loudness for
  `voice_pulse`.
- **Output:** `motion-plan.json` (everything the AE library needs, in frames and pixels), `motion-plan.md` (per scene:
  time, beat, type, on-screen text with speech/editorial marked, icon or illustration, number with its evidence,
  transition and SFX; then music, deviations, approvals, the animatic path) and `motion-validation.json`. A
  fingerprint over the script, words, pauses, recipe, `motion.json` and brand tokens is stored; `approve-plan`, the
  build and QC compare it.

### 4.2 Icons (`lib/motion_icons.py`, `templates/motion/icons/lucide/`)
- The Lucide SVG set is vendored at a pinned release with its `LICENSE` (ISC) and an `icons.json` index
  (name → tags, categories) by a dev-only script (`tools/vendor_lucide.py`, not shipped in the zip). About 0.7 MB.
- `svg_to_shapes(svg_text) → list[{"vertices", "inTangents", "outTangents", "closed"}]` parses `path`
  (`M L H V C S Q T A Z`, absolute and relative; arcs converted to cubic Béziers), `circle`, `ellipse`, `rect`
  (with `rx`), `line`, `polyline`, `polygon`, scaled from the 24×24 viewBox to the requested size. The AE library turns
  each subpath into a shape group with a brand-linked stroke (round caps and joins) and Trim Paths for the draw-on.
- `search(query) → [{"name", "tags", "score"}]` for `reel motion-icons --search "money, growth"`.
- `flatten(shapes, tol)` turns the same data into polylines for the animatic.

### 4.3 Licensed illustration library (`lib/motion_library.py`)
- Packs live in `motion.json["library_dir"]`, outside client folders and read-only for Claude. Each pack folder has a
  `pack.json`: `{"id", "name", "license", "source", "attribution", "proof", "items": [{"id", "file", "tags"}]}`.
- Allowed licenses: `CC0-1.0`, `MIT`, `ISC`, `Apache-2.0`, `CC-BY-4.0` (attribution required) and `commercial` (needs
  `proof`: an invoice or license id). Any other value, or a missing `pack.json`, makes the whole pack unusable.
- Items are PNG with alpha (imported as footage) or simple SVG (solid fills only, ≤ 300 subpaths), converted like the
  icons.
- `reel motion-library` lists packs, licenses and problems. No pack ships with the plugin.

### 4.4 Animatic (`lib/motion_animatic.py`, `reel motion-animatic`)
For each scene, a still of its hero state at 540 px wide (Pillow + HarfBuzz with the brand font files, flattened icons,
photos and illustrations, theme background, captions and badge), `_storyboard.jpg` (a grid with scene id, type and
times) and `<ID>_animatic.mp4`: each still held for its scene with 6-frame crossfades and a label strip, over the
mixed audio (dialogue + music + SFX, the same mixer as `preview_video.build_audio`). It is labelled "layout
approximation — AE frames are the truth".

### 4.5 After Effects bridge (`lib/cep_queue.py`, `lib/ae_bridge.py`, bundle 3.1.0)
- **One CEP bundle, two hosts.** `templates/premiere/cep_bridge/CSXS/manifest.xml` lists `PPRO [22.0,99.9]` and
  `AEFT [24.0,99.9]` for both the panel and the hidden daemon. `bridge.js` reads the host from
  `__adobe_cep__.getHostEnvironment()` and uses `{queue, scripts, entry}` = `ppro-queue, ppro-scripts, NHPP` in Premiere
  (exactly today's behaviour) and `ae-queue, ae-scripts, NHAE` in AE. The heartbeat records the host. Version 3.1.0.
- **Python.** `cep_queue.py` holds the generic queue client (`status(queue_dir)`, `submit(queue_dir, script, action,
  data, timeout)`), lifted from `ppro_bridge.py`, whose public functions keep their names and behaviour. `ae_bridge.py`
  adds `sync_scripts()` (copies `nh_ae_lib.jsx`, `nh_motion_lib.jsx` and `nh_ae_bridge.jsx` into `ae-scripts`,
  hash-checked before every job), `status()` and `submit()`. `reel ppro-install` installs the one bundle;
  `reel ae-status` reports the AE heartbeat. After an install, AE (like Premiere) needs a restart.
- **`nh_ae_bridge.jsx`** (`NHAE.run(dataFile)`): reads the ASCII JSON data file (reading needs no scripting-security
  preference), wraps every action in `app.beginSuppressDialogs()` / `app.endSuppressDialogs(false)` and returns JSON.
  Actions: `ping` (AE version, open project, `app.project.dirty`), `fonts` (per PostScript name:
  `app.fonts.getFontsByPostScriptName`, `isSubstitute`, plus `missingOrSubstitutedFonts`), `probe_text` (§4.6),
  `build_motion` (§4.7), `readback` (§4.8). ExtendScript never writes files; the panel's Node side writes results.
- **The editor's work is never discarded.** `build_motion` refuses when AE has a project with unsaved changes
  (`app.project.dirty`, undocumented but present since AE 17.5) that is not this reel's `.aep`, and when this reel's
  `.aep` is open with unsaved changes ("save or close it in AE first").
- **Fallback.** With the bridge down, `motion-build --script-only` writes `build_<ID>_motion.jsx` (data + libraries +
  `NHM.build()`), and `--run-script` hands it to AE with `adobe_run.run_after_effects`, judged by the `.aep` save time
  (as the extras do). Such a build has no read-back: QC reports "Not verified: read-back (bridge not running)" and
  cannot pass.

### 4.6 Arabic capability probe (`reel ae-probe`)
Before any scene work, and again after an AE update, `ae-probe` builds `<engine home>/ae-probe/probe.aep` through the
bridge with test comps, reads them back, renders frames with `aerender` and writes `<engine home>/ae-capabilities.json`.

| Probe | Measured | Fallback chosen when it fails |
|---|---|---|
| Arabic sentence, Universal composer | composer read back as UNIVERSAL | none: Needs you — AE Preferences › Type › Text Engine "South Asian and Middle Eastern", restart AE |
| `TextDocument.direction = RTL` | read back after `setValue` | set it through `paragraphRange(0)` (AE 24.3+); else `rtl_direction: false` (right-justified, rely on the composer's bidi) + warning |
| Word reveal, expression selector "Based On: Words" | which word is revealed first, judged from frames rendered at known cue times (AE scripting cannot report a selector's per-word value) | `word_index_logical: false` → per-line layers with line reveal; if lines also fail → one text layer per word, chained by `sourceRectAtTime` expressions (Arabic does not join across spaces) |
| Per-word fill emphasis (animator + expression selector) | colour at the emphasised word in the frame | emphasis by scale only |
| Mixed Arabic + Latin term + digits | frame view | none (a QC failure points to the term) |
| Brand font via `fontObject` | `getFontsByPostScriptName`, not substituted | Needs you: install the font (`font_install_hint()`) |
| Icon from SVG path data with Trim Paths | layer read-back + frame | none |
| Output-module templates | names available in this AE | the first ProRes/lossless template |

Claude views the probe frames (joined letters, word order, emphasis colour) and records the verdict with
`reel ae-probe --record ok|fail --word-order logical|visual --notes "…"` (the word order seen in the frames sets
`word_index_logical`). `motion-build` refuses while there is no `ok` verdict for this AE version.

### 4.7 Build (`lib/motion_build.py`, `templates/after_effects/nh_motion_lib.jsx`, `reel motion-build`)
- Preconditions: a fresh `motion-plan.json`, Gate 1 approval for its fingerprint, an `ok` probe verdict, all fonts
  present (`fonts` action), and AE idle.
- `motion-job.json` = the compiled plan + brand controls + fonts + capabilities + paths (ASCII JSON).
- **Project structure** (the library sets `NH.W`, `NH.H`, `NH.FPS` from the plan and reuses the `nh_ae_lib.jsx`
  helpers): `NH_BRAND/BRAND_CONTROLS` (colour controls; every fill, stroke and text colour links to them),
  `NH_SCENES/S01_kinetic_quote …` (one full-frame comp per scene), `NH_PERSISTENT` (background, captions, badge,
  progress, voice pulse), `NH_AUDIO` (dialogue, music, SFX footage), `NH_ASSETS` (photos, illustrations) and
  `MAIN_<ID>` (the scene comps at their frames with their transitions, the persistent layers and the audio layers).
- All keyframe times are `frame × comp.frameDuration`, so 29.97/23.976 profiles do not drift. Word reveals and
  emphasis are text animators with expression selectors whose cue arrays come from the plan (or the capability
  fallbacks). Counters drive Source Text by expression. Icons are shape layers built from the plan's vertex data.
- The library saves `<ID>_<PREFIX>_MOTION.aep` and returns a per-scene report (made / failed + error and line).
- **Rebuild protection:** after each save the engine records the file's SHA-1. If the `.aep` on disk differs at the
  next build (the editor worked in it), `motion-build` refuses unless `--replace-edited`, which first copies it to
  `project/backups/<name>.edited-<stamp>.aep`.

### 4.8 Read-back
Right after the build, `readback` inspects the project AE just saved (still open, nothing reopened) and returns, per
scene comp:
its in/out frames in MAIN, every layer (name, kind, in/out), every text layer's string, font PostScript name and
`isSubstitute`, composer, direction, and its box from `sourceRectAtTime(hero)` in comp pixels; each expression
selector's cue-array hash; and `missingOrSubstitutedFonts`. The engine compares it with the plan: same strings
(normalised), same fonts and no substitutes, UNIVERSAL composer for Arabic layers, direction as the capabilities say,
boxes inside the safe area and not overlapping each other or the caption band, and scene frames and cue hashes as
planned. The comparison goes into `motion-build-result.json`.

### 4.9 Render, MP4, cover (`reel motion-render`)
- `aerender -project <aep> -comp MAIN_<ID> -RStemplate <rs> -OMtemplate <om> -output render/<ID>_MAIN.mov` (a new AE
  instance reading the saved file; the editor's open AE is untouched). `--scenes S03,S05` renders only those frame
  ranges (`-s`/`-e`) into `render/pieces/` for quick fixes. Log in `logs/aerender.log`.
- The result is probed: size, fps and duration (= plan ±1 frame) and an audio stream. ffmpeg then writes
  `<ID>_motion.mp4` (H.264, AAC, `+faststart`, loudness checked against the existing −14 LUFS target) and
  `<ID>_cover.jpg` (the first scene's hero frame, for the Instagram cover).
- A render whose audio stream is missing gets the engine's mix muxed into the MP4, with a warning.

### 4.10 Frames and QC (`reel motion-frames`, `reel qc` for motion projects)
- **Frames:** taken from the newest render (pieces win for their ranges) at every scene's hero frame, the midpoint of
  each word/line reveal and list/timeline reveal, each transition midpoint and three caption samples. They go to a fresh
  `ae_frames/run-<stamp>/` with `frames.json` (per frame: scene, kind, expected lines, emphasised words, icon,
  revealed-token count) and a labelled `_sheet.jpg`. The qc-reviewer splits them across frame-inspectors.
- **Frame checklist:** Arabic letters joined (no isolated forms), words in right-to-left order, a mid-reveal frame shows
  the first spoken words (rightmost in RTL) and not the last, no missing-glyph boxes, no clipped or overflowing text,
  emphasis on the right words, the icon fits its meaning, mirrored arrows point the reading way, nothing inside the
  platform UI zones, readable contrast, brand colours.
- **`qc` checks** (each FAIL blocks `QC_PASSED`):
  1. the plan validated with no errors, and Gate 1 approval matches the built plan's fingerprint;
  2. the `.aep` was saved by this build (fresh save time, SHA-1 recorded);
  3. the read-back comparison passed (strings, fonts, composer, direction, boxes, frames, cue hashes); a fallback
     build without read-back fails here;
  4. the render exists, is newer than the `.aep`, and has the planned size, fps, duration and an audio stream;
  5. audio sync: the render's audio envelope against the cleaned dialogue (correlation ≥ 0.9, offset ≤ 1 frame);
  6. the cut proof from `audio-clean` exists and is ok;
  7. visual verification recorded by the lead (`verify --record`) for the newest frames run;
  8. every asset used has a license record; CC-BY attributions are present in the handoff;
  9. approvals (numbers from words, avoid topics) are listed for the editor (warning, not a failure).

### 4.11 Status, `next`, `episode-next`
- Statuses reuse the existing vocabulary (`common.STATUSES` is unchanged): `TRANSCRIBED` (sliced) → `ANALYZED`
  (`motion-plan` compiles with no errors) → `EDIT_PLAN_READY` (approved) → `PROJECT_ASSEMBLED` (built and read back,
  stage `motion_build`) → `QC_PASSED` → `READY_FOR_HUMAN_EDITOR` (handoff). The render is tracked by its files and the
  stage `motion_render`.
- `reel next --video-id EP12_R03_MO` follows the motion steps: audio-clean, AUTHOR motion-script, motion-plan,
  motion-animatic, PLAYBACK motion-plan.md + animatic → approve-plan, ae-probe (once per AE version), motion-build,
  motion-render, motion-frames + LOOK + verify --record, qc, handoff. Stale rules: plan older than the script or
  `pauses.json`; animatic older than the plan; build older than the approval or plan; render older than the build;
  frames older than the render; qc older than the frames or the verification.
- `episode-next` lists motion projects with their status next to the video reels.

### 4.12 Publish and handoff
- The publish-writer writes `publish/reels/<EP>_<ID>_MO.json` as for any reel; `publish-check` validates it unchanged,
  and for motion reels also requires every CC-BY attribution from `motion-plan.json` in the reel's captions.
  `publish-thumbnail` is unchanged; the motion cover is `render/<ID>_cover.jpg`.
- `handoff` for a motion project: where the `.aep` is, how the comps are organised, where to edit text and brand
  colours, the fonts it needs, the audio layers, the renders, the licenses and attributions, and the Needs-you list.

### 4.13 CLI
New: `motion-icons` (`--search`), `motion-library`, `motion-plan`, `motion-animatic`, `ae-status`, `ae-probe`
(`--record ok|fail --word-order logical|visual --notes`), `motion-build` (`--script-only`, `--run-script`, `--replace-edited`,
`--allow-fallback-font`), `motion-render` (`--scenes`), `motion-frames`. Changed:
`reels-select` (`--as`, `--format`, `--type`, `T` ids), `approve-plan`, `next`, `qc`, `verify --record` and `handoff`
dispatch on `source.json["kind"] == "motion_reel"`. `ppro-install` installs the two-host bundle.

## 5. Approaches considered

### 5.1 AE build path
| Approach | For | Against |
|---|---|---|
| **A. Generated ExtendScript, run with `AfterFX.exe -r` / AppleScript only** (today's `ae-*` extras) | Already exists and was verified (C0238, macOS); no install | No return value on Windows (only file times), so no read-back of text, fonts, direction or layout; an uncaught error or a first-run dialog blocks AE silently; each step is a blind launch |
| **B. The same generated library, executed through the WhyNot Cut Bridge in AE, `-r` as fallback** (chosen) | Synchronous JSON results; read-back of exactly what AE built (fonts substituted? direction kept? boxes in the safe area?); dialogs suppressed; heartbeat and queue already proven in Premiere; one bundle | Touches the verified Premiere bridge (host-aware `bridge.js`, a new manifest host); AE must be restarted once after install; PlayerDebugMode is the same editor-set preference Premiere already needs |
| **C. Designer-made `.aep` templates with data replacement** (or MOGRT Essential Properties) | Highest polish per template | Binary files that can't be generated, diffed or reviewed; every look needs a designer; layouts can't adapt to Arabic line counts; contradicts "Claude builds the projects itself" |
| D. UXP plugin | Adobe's future | Beta in After Effects today |

B keeps the content model of A (data + a code library, so every fix is a reviewed diff) and gains the evidence a CEP
panel gives. A designer-made "look pack" could later restyle the same scene types; it is not part of 2.2.

### 5.2 Input unit
A whole-episode segment (5–20 min) was rejected for 2.2: scene counts and render times grow linearly, and QC must be
proven on short windows first. Topics up to 180 s are allowed so an editor can animate a chapter-sized idea.

### 5.3 Assets
Generated illustrations were rejected (no approved provider; licensing unclear). Downloading icons at run time was
rejected (network, reproducibility). Vendored Lucide (ISC: commercial use and redistribution allowed with the notice)
covers concepts; licensed packs cover characters and scenes when an agency buys them.

## 6. Plugin layer
- **Agents (new):**
  - `motion-director` (opus; reads the sliced transcript, speakers, recipe, sheet facts and brand; writes
    `motion-script.json`; runs `motion-icons`, `motion-plan` until no errors, `motion-animatic`; views the storyboard)
  - `ae-builder` (sonnet; `ae-status`, `ae-probe`, `motion-build`, `motion-render`; reports the read-back comparison;
    never approves)
- **Agents (updated):**
  - `episode-analyst`: `motion_fit`/`motion_why`, topic `type`
  - `qc-reviewer` and `frame-inspector`: the motion frame checklist and `frames.json` expectations
  - `publish-writer`: motion reels, CC-BY attribution lines
  - `setup-doctor`: AE bridge diagnosis (heartbeat in `ae-queue`, CEP logs for AEFT)
- **Skills (new):** `motion` (lead playbook: Gate 0 `--as motion`, stages, Gate 1 with the animatic, build → render →
  frames → QC, report format) and `motion-craft` references `motion-scenes.md` (vocabulary and fields),
  `motion-beats.md` (recipes → beats → scenes, direction rules) and `ae-motion.md` (bridge, probe, build, read-back,
  render, fallbacks).
- **Skills (updated):** `podcast` (Gate 0 offers motion, audio episodes), `adobe-extras` (motion mode is not an
  extra), `help`, `status`, `start` and `setup` (AE bridge and restart), `qc-craft`, `episode-craft`, `publish-craft`.
- **Hooks:** `motion-*` and `ae-status|ae-probe` are not extras. Subagents may not run `reels-select`, `approve-plan`,
  `verify --record` or `ae-probe --record` (the existing role rules extended). `qc-reviewer` may not run `motion-plan`,
  `motion-build` or `motion-render`. Writing AE preference files (`Adobe After Effects * Prefs*.txt`) is blocked like
  PlayerDebugMode.
- **Session context:** mentions motion mode when a client has `data/Episodes`.
- **Evals (new):** `motion-from-audio` (stops at Gate 1 with the plan and animatic; no invented words, numbers or
  names; editorial lines marked) and `motion-qc-evidence` (never calls a motion reel done without read-back, frames
  viewed and `qc` passing in the same message).
- **Docs:** README (motion section, commands, EN + AR quick start), CHANGELOG 2.2.0, plugin and marketplace manifests,
  `THIRD_PARTY_NOTICES.md` (Lucide ISC). `package.py` ships `templates/motion/` and skips `tools/`.

## 7. Error handling
| Situation | Behaviour |
|---|---|
| AE not installed | `motion-build --script-only` delivers the JSX and the animatic; status stays `EDIT_PLAN_READY`; report says Needs you: After Effects |
| Bridge not loaded in AE | `ae-status` says why (no heartbeat; PlayerDebugMode off → the editor's command; AE not restarted); fallback `--run-script` builds without read-back; QC cannot pass |
| Probe not ok for this AE version | `motion-build` refuses and names the failed probe and its fix |
| Brand font not installed | `motion-build` refuses: Needs you — install `assets/Fonts/<file>` (per-user install is enough), restart AE. A fallback font only with the editor's OK (`--allow-fallback-font`, recorded) |
| Letters disconnected in frames | QC fail; the report gives the AE Type preference step (the editor changes it) |
| AE has unsaved work open | `motion-build` refuses: save or close it first |
| The editor changed the `.aep` | Rebuild refused; `--replace-edited` keeps a backup copy first |
| AE dialog or crash mid-job | The queue times out with a clear message; the job file stays for diagnosis |
| Text too long for the scene | Plan error with the measured width; the director splits the scene |
| Number not literally spoken as digits | Approval item, shown at Gate 1 |
| Icon name unknown | Plan error with the five closest names from the index |
| Unlicensed or unknown-license asset | Plan error; the pack is listed by `motion-library` with the problem |
| Window > 180 s | Refused at Gate 0 with the split advice |
| Episode file changed after selection | Existing fingerprint refusal (plan, build) |
| Render missing audio | MP4 gets the engine mix + warning |
| English episode | `direction: ltr`; every direction rule mirrors |

## 8. Testing
- **New `tests/test_motion.py`:**
  - Gate 0: `--as motion` ids, topic snapping and limits, `--type`, audio-only episodes (discover role, prep, preview
    card, video pick refused), selection history
  - recipe `motion` defaults load and profile overrides merge
  - anchors (in-order, missing, `@start`/`@end`), speech subsequence (drop ratio, added token, Arabic spelling
    variants through `plan.norm`), editorial rules (quotes, digits, names), numbers with Arabic-Indic digits
  - TimeMap mapping of cue frames after pause removal at 24/25/29.97/30 fps; hero frames; transition overlaps
  - wrapping rules and HarfBuzz fitting (skipped without the venv's uharfbuzz, as today)
  - contrast switching; caption hide ranges; SFX and music cues
  - `svg_to_shapes` on every element type (arcs included) against reference points; icon search; RTL mirroring
  - library license validation (allowed, CC-BY attribution, `commercial` without proof, missing `pack.json`)
  - animatic stills and MP4 (duration = plan, audio stream present)
  - the generated JSX and `nh_motion_lib.jsx` pass the JavaScript syntax check (`assert_js_syntax`)
  - the queue client against a fake panel thread (job claim, result, timeout, host-specific folders), and
    `ppro_bridge` behaviour unchanged
  - read-back comparison (good report passes; substituted font, wrong string, box outside the safe area, missing scene
    each fail); rebuild protection (SHA-1 changed → refused; `--replace-edited` writes the backup)
  - render probe checks and frame selection (`frames.json` expectations)
  - every motion `qc` rule; `next` and `episode-next` for motion projects; guard rules; publish CC-BY check
- **Regression:** all existing tests pass unchanged (the bridge refactor is covered by the existing Premiere tests).
- **Live on this PC:** the bridge in AE 2026 (and Premiere still answering after the bundle update), `ae-probe` frames
  viewed, then one motion reel from `whynot-test/PODCAST-TEST` through QC and `publish-check`.

## 9. Implementation order (each step testable)
1. Two-host bridge + `cep_queue` + `ae_bridge` + `ae-status` + `ae-probe` (live on this PC; **gate**: stop and report
   if AE cannot load the bridge or the Arabic probe fails without a fallback)
2. Audio episodes, Gate 0 `--as motion`, motion project, `source.json`, recipe `motion` blocks, `motion.json`
3. Icons (vendoring, SVG → shapes, search) and the licensed library
4. Motion plan compiler + `motion-plan.md` + `approve-plan` for motion
5. Animatic
6. ES3 motion library + job data + fallback script
7. Build through the bridge + read-back + rebuild protection; render, MP4, cover; frames
8. Motion QC, verify, `next`/`episode-next`, handoff, publish CC-BY check
9. Agents, skills, hooks, evals, docs, version 2.2.0, package
10. Live verification on this PC

Coordination: steps 1 and 8 touch shared engine files (`ppro_bridge.py`, the CEP bundle, `cli.py`, `qc.py`,
`verify.py`). Before each, the implementing session messages the "Reel editing plugin enhancement" session and agrees
file ownership; after step 1, Premiere is re-checked live (`ppro-status`, one `ppro-frames` on an existing reel).

Follow-ups noticed while designing (not part of 2.2): `nh_ae_lib.jsx` hardcodes 24 fps for the clip graphics extras;
the extras could also move onto the bridge for read-back.
