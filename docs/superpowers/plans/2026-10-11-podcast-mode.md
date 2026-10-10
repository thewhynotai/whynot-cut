# WhyNot Cut 2.1 Podcast Mode — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A finished 16:9 podcast episode becomes a validated reels plan; editor-picked reels flow through the existing
WhyNot Cut pipeline (per-shot reframe, content-type recipe); and a checked YouTube/social publish package comes out.

**Architecture:** New engine modules: `episode.py` (episode project, sheet, chunked Whisper), `reels.py` (plan
validation, previews, Gate 0 slicing), `source.py` (source window used by every media read), `shots.py` (shot/face
analysis and framing), `recipes.py` and `publish.py`. Reels are ordinary clip projects whose `00_inputs/source.json`
points at a window of the episode file. Plugin agents and skills drive it; hooks guard Gate 0.

**Tech Stack:** Python 3.10–3.13 in the engine venv (PyAV, numpy, Pillow, OpenCV, faster-whisper, uharfbuzz/freetype),
ffmpeg, the stdlib unittest runner, Markdown agents/skills, Premiere bridge (CEP, ExtendScript) unchanged.

**Spec:** `docs/superpowers/specs/2026-10-11-podcast-mode-design.md`

## Global Constraints
- Run tests with `PY="C:/Users/LOQ/.whynot-cut/venv/Scripts/python.exe"`, then from `whynot-cut-marketplace/`:
  `"$PY" -B -m unittest discover -s whynot-cut/tests` → all OK, the existing 77 tests unchanged.
- Engine files live in `whynot-cut/engine/reel/lib/`. Config defaults go in `whynot-cut/config/defaults/` and are
  read only through `load_config(name)` (profile-overridable).
- Time unit is integer ms. Sequence frames: `ms_to_frame()` at 24 fps. Premiere ticks: `TPS = 254016000000`.
- `assets/` and `data/` are never written. Outputs go under `<client>/output/`.
- Reel id: `f"{EP}_{RID}"` (e.g. `EP12_R03`). Episode project: `output/episodes/<EP>/`.
- Content types: `storytelling, drama, success_story, advice, bold_opinion, emotional, comedy`.
- Reel duration: soft 30–90 s (warning), hard 15–180 s (error). Snap: lead-in 120 ms, tail 250 ms, search ±1500 ms,
  evidence tolerance ±3000 ms. Speaker minimum hold: 1500 ms. Overlap warning above 0.5 of the shorter candidate.
  Candidates per hour: 8–15.
- YouTube: title ≤ 100 (warning > 70), description ≤ 5000, tags total ≤ 500, hashtags ≤ 15, chapters start `00:00`,
  ≥ 3, each ≥ 10 s, no `<` `>`.
- Instagram caption ≤ 2200 with ≤ 30 hashtags; TikTok caption ≤ 2200; Shorts title ≤ 100; thumbnail 1280×720 ≤ 2 MB.
- No new pip dependencies.
- Clips without `source.json` and without `preflight["shots"]` must behave exactly as in 2.0.0.
- Commit after each task: `git commit -m "<type>: <what>"` ending with
  `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.

## Review Focus
1. **Arabic or symbol-only episode file names** (`حلقة 12.mp4`, `الحلقة.mov`): `slug()` drops them to `VIDEO` or
   digits, so two episodes could collide. Expected: distinct, stable ids (`EP_<6 hex of name>` fallback). Test in
   Task 1.
2. **Arabic spelling variants in evidence and quotes** (أ/ا/إ, ة/ه, ى/ي, tashkeel, Whisper punctuation): matching
   must go through `plan.norm()`. Tests in Tasks 3 and 10.
3. **Candidates at the episode edges** (start 00:00:00.5, end at the last word): snapping must clamp to
   `[0, duration]` and never return `in >= out`. Test in Task 3.
4. **Non-24 fps episodes with large offsets** (29.97/25 fps, reel at 45:00): XML in-points must be frame-exact from
   ticks with no drift, and audio extraction sample-exact. Tests in Task 6.
5. **Links in the sheet vs the copy** (trailing punctuation `https://x.com/a.`, `www.` vs `https://www.`, trailing
   slash): normalise before comparing; an invented URL still fails. Test in Task 10.

---

### Task 1: Episode intake (`episode.py`, discovery roles, CLI `--episode`, `episodes`, `episode-prep`)

**Files:**
- Create: `whynot-cut/engine/reel/lib/episode.py`, `whynot-cut/config/defaults/podcast.json`,
  `whynot-cut/tests/test_podcast.py`
- Modify: `lib/discover.py` (`classify`), `lib/onboard.py` (`FOLDERS`, `start_here`, `inbox`), `engine/reel/cli.py`
  (global `--episode`, `P()`, `NO_ID`, new commands)

**Interfaces:**
- Produces:
  - `parse_sheet(text: str) -> dict` (keys from frontmatter, lists for `[a, b]` or `- item`, plus `_notes`, `_text`)
  - `episode_id_for(path: Path) -> str`
  - `class EpisodePaths(Paths)` with `__init__(root, episode_id)`, `.project = output/episodes/<id>` and
    `ensure_project()` (dirs `00_inputs/intake, 01_analysis, 02_transcription/chunks, 03_candidates,
    publish/reels, publish/thumbnail/candidates, 08_quality_control, logs`)
  - `list_episodes(root: Path) -> list[dict]` (`episode_id, file, rel, sheet, state`)
  - `episode_file(ep: EpisodePaths) -> Path` (from the inventory, role `episode`)
  - `prep(ep: EpisodePaths) -> dict` (writes `00_inputs/episode.json` and intake frames; returns probe summary +
    `estimate_minutes {gpu, cpu}`)
  - `load_episode(ep) -> dict` (reads episode.json)
  - CLI `a.episode`; `P(a)` returns `EpisodePaths` when `--episode` is set and `--video-id` is not.
- `podcast.json` keys: `reel_duration_s {min:30,max:90,hard_min:15,hard_max:180}`,
  `candidates_per_hour {min:8,max:15}`, `snap {lead_in_ms:120, tail_ms:250, search_ms:1500, evidence_tol_ms:3000,
  gap_ms:300}`, `max_overlap_ratio:0.5`, `chunk_minutes:10`, `episode_vad:true`, `speaker_min_hold_ms:1500`,
  `shots {scene_threshold:0.3, samples_per_shot:3, min_shot_ms:400, face_min_ratio:0.3, group_fit:0.8}`,
  `raw_episode_hint_min:10`.

- [ ] **Step 1: Write failing tests** in `test_podcast.py`, class `TestEpisodeIntake`. Use a temp client with
  `data/Episodes/EP12.mp4` (ffmpeg testsrc2 1280×720 25 fps 20 s + sine), `EP12.md`, and `data/Raw/CLIP1.mov`.
  - `test_parse_sheet`: `parse_sheet("---\nguest: \"Sara — CEO\"\nlinks:\n  - https://a.com/x\navoid: [السياسة, دين]\n---\nnotes")`
    → `guest == "Sara — CEO"`, `links == ["https://a.com/x"]`, `avoid == ["السياسة","دين"]`, `"notes" in _notes`.
  - `test_discover_roles`: the inventory gives `data/Episodes/EP12.mp4` role `episode` and `EP12.md` role
    `episode_sheet`; `CLIP1.mov` stays `source_footage`.
  - `test_episode_ids_unique_for_arabic_names`: `episode_id_for(Path("حلقة 12.mp4")) != episode_id_for(Path("الحلقة.mov"))`.
    Both are stable across calls and match `^[A-Z0-9_]+$`. `episode_id_for(Path("EP12.mp4")) == "EP12"`.
  - `test_list_and_prep`: `list_episodes(root)[0]["state"] == "new"`. `prep(ep)` writes `00_inputs/episode.json` with
    `duration_ms ≈ 20000 (±100)`, `sheet.guest`, 6 files `00_inputs/intake/frame_0*.jpg` and `_intake_sheet.jpg`.
    `estimate_minutes["cpu"] > estimate_minutes["gpu"]`.
  - `test_inbox_lists_episodes`: `inbox(root)["episodes"][0]["episode_id"] == "EP12"`; `clips` excludes the episode.
- [ ] **Step 2: Run** `"$PY" -B -m unittest discover -s whynot-cut/tests -p test_podcast.py` → FAIL (module missing).
- [ ] **Step 3: Implement.**
  - `classify`: a video under `data/Episodes/` → `episode`; a document there → `episode_sheet`.
  - `episode_id_for`: `slug(stem)`. When the stem has no ASCII alphanumerics, or slug gives `VIDEO`, use
    `"EP_" + sha1(stem)[:6].upper()`.
  - `prep`: probe via `media.probe`, frames via ffmpeg `-ss`, a 3×2 contact sheet with Pillow. Estimate:
    `gpu = dur_min*0.08`, `cpu = dur_min*(1.2 if model=='large-v3' else 0.5)` with the model from settings.
  - `inbox`: add `episodes` (from `list_episodes`) and a warning for Raw videos ≥ `raw_episode_hint_min` min and 16:9.
  - `FOLDERS` gains `data/Episodes` (EN text: "finished podcast episodes (16:9) to cut into reels, plus an optional
    <name>.md episode sheet"); the Arabic paragraph mentions `data/Episodes/`.
  - CLI: `episodes` (prints `list_episodes`) and `episode-prep`. When `--episode` is missing and one episode exists,
    use it.
- [ ] **Step 4: Run** the podcast tests and then the full suite → all PASS.
- [ ] **Step 5: Commit** `feat(podcast): episode intake, sheet parser, episode-prep`.

### Task 2: Chunked, resumable episode transcription

**Files:**
- Modify: `lib/episode.py`, `lib/transcribe.py` (`_run_whisper` gains `vad: bool = False`), `cli.py`
  (`episode-transcribe`; `transcript-correct|verify|relisten` work with `--episode` through `P(a)`)
- Test: `tests/test_podcast.py` class `TestChunkedTranscription`

**Interfaces:**
- Consumes: `EpisodePaths`, `episode_file`.
- Produces:
  - `plan_chunks(db: list[float], hop_ms: int, total_ms: int, chunk_ms: int, search_ms: int = 20000) -> list[tuple[int, int]]`
  - `stitch(chunks: list[dict]) -> tuple[list, list]`
  - `transcribe_episode(ep, model_size, language=None, force=False, run_chunk=None) -> dict`
  - `run_chunk(audio_f32, start_ms, language, initial_prompt) -> (segs, words, info_language)` is injectable.
    Default: Whisper with `vad=podcast.episode_vad`.
  - Checkpoints: `02_transcription/chunks/chunk_NNN.json` with `{start_ms, end_ms, language, segments, words}` (times
    already absolute).

- [ ] **Step 1: Write failing tests.**
  - `test_plan_chunks_cuts_in_silence`: `db` = −20 everywhere except −80 at 590–592 s and 1210 s (hop 50 ms),
    `total_ms = 1_500_000`, `chunk_ms = 600_000` → boundaries are within 1 s of 591000 and 1210000; chunks are
    contiguous from 0 to total.
  - `test_plan_chunks_short_audio`: total 300000 → `[(0, 300000)]`.
  - `test_stitch_renumbers`: two chunks of 2 words each → word ids 1..4, segment ids 1..2, each word's `segment_id`
    matches, times unchanged.
  - `test_resume_skips_done_chunks`: use a fake `run_chunk` that records calls. Pre-write `chunk_000.json`, run
    `transcribe_episode(ep, "small", run_chunk=fake)` on the 20 s fixture with `chunk_ms` patched to 8000 → the fake is
    not called for chunk 0. `transcript.json` exists with `meta.chunks == 3`, `meta.vad is True`. `force=True` re-calls
    all.
- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement.** Extract the 16 kHz mono WAV once (`transcribe.extract_audio`). `db` comes from 50 ms RMS
  windows. Each boundary is at the minimum-energy window within ±search of `k*chunk_ms`. The model loads lazily once
  (`whisper_model`, with the GPU→CPU retry pattern from `transcribe.transcribe`). Log per-chunk progress and ETA. Meta
  matches the clip transcript meta plus `chunks`, `vad`, `episode_id`. Call `finalize()`, then write the `.machine.json`
  copies.
- [ ] **Step 4: Run** the tests → PASS; the full suite → PASS.
- [ ] **Step 5: Commit** `feat(podcast): chunked resumable episode transcription`.

### Task 3: Reels plan validation and `recipes.json`

**Files:**
- Create: `lib/reels.py`, `config/defaults/recipes.json` (7 types, values from spec §4.6 table, labels en/ar,
  `copy.tone`)
- Modify: `cli.py` (`reels-plan`)
- Test: `TestReelsPlan`

**Interfaces:**
- Consumes: `EpisodePaths`, `load_episode`, `plan.norm`, `plan.to_ms`.
- Produces:
  - `content_types() -> list[str]`
  - `boundary_words(words: list) -> (set[int] starts_ok, set[int] ends_ok)` (indices)
  - `snap_in(words, t_ms, cfg) -> int`
  - `snap_out(words, t_ms, cfg, total_ms) -> int`
  - `find_evidence(words, text, near_ms, tol_ms) -> bool`
  - `compile_reels_plan(ep) -> dict` (`{ok, errors, warnings, candidates}`); writes
    `01_analysis/reels-plan-validated.json` (each candidate + `in_ms, out_ms, duration_ms, total, excerpt_start,
    excerpt_end, avoid_hits, warnings`), `reels-plan.md` and `reels-plan-validation.json`
  - `reels_plan_fingerprint(ep) -> str` (sha1 of reels-plan.json bytes + words.json bytes, 16 hex)

- [ ] **Step 1: Write failing tests.** Fixture: an episode project with a synthetic transcript of 3 segments. Words
  every 400 ms; a 600 ms gap before word 40; word 39 ends with `؟`; total 120 s.
  - `test_valid_candidate_snaps_to_sentence`: start 1.1 s before word 40's start → `in_ms == words[39].start − 120`.
    End near a segment end → `out_ms == word.end + 250`, capped at next word start − 20.
  - `test_evidence_variants_match`: evidence written `"أنا قلت إن الشركة"` matches transcript `"انا قلت ان الشركه"`.
  - `test_evidence_missing_is_error`: an error mentioning `evidence`.
  - `test_edges_clamped`: start `00:00:00.000` → `in_ms == 0`; end at the last word → `out_ms <= total` and
    `in_ms < out_ms`.
  - `test_duration_limits`: 20 s → warning; 10 s → error.
  - `test_unknown_type_error`, `test_overlap_warning`, `test_avoid_hit_flagged` (the sheet `avoid: [السياسه]` with
    transcript `السياسة` → `avoid_hits == ["السياسه"]`).
  - `test_total_and_sort`: score `{8,7,9,8}` → `total == 8.0`; `reels-plan.md` lists candidates by total, descending.
  - `test_fingerprint_changes_with_words`.
- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement.** A sentence-like start is a segment's first word, the word after one ending in
  `.?!؟…`, or a word after a gap ≥ `gap_ms`. Ends mirror this. Snap to the nearest qualifying boundary within ±search,
  else the nearest word. The count warning scales `candidates_per_hour` to the duration. Topics and speakers are
  validated as in spec §4.3 (warnings).
- [ ] **Step 4: Run** → PASS; full suite PASS.
- [ ] **Step 5: Commit** `feat(podcast): reels plan validation with sentence snapping`.

### Task 4: Candidate previews (`reels-preview`)

**Files:** Modify `lib/reels.py`, `cli.py`. Test: `TestReelsPreview`.

**Interfaces:**
- Produces: `render_candidates(ep, ids: list[str] | None = None) -> dict` (`{ok, previews: [{id, mp4, jpg}], sheet}`)
  → `03_candidates/<id>.mp4` (540×960 H.264 CRF 28, whole 16:9 frame letterboxed on `#111`, Latin label PNG
  overlaid, AAC), `<id>.jpg`, `_sheet.jpg`. Updates `reels-plan.md` with the preview paths.

- [ ] **Step 1: Failing test** `test_previews_rendered`: one validated candidate 2.0–6.0 s on the 20 s fixture → the
  mp4 exists, probe gives 540×960, duration 4.0–4.6 s, has audio; `_sheet.jpg` exists.
- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement** with ffmpeg `-ss in -t dur -i episode -i label.png -filter_complex
  "[0:v]scale=540:-2,pad=540:960:0:(oh-ih)/2:color=0x111111[v];[v][1:v]overlay=0:0"`. Requires a fresh validated plan
  (fingerprint).
- [ ] **Step 4: Run** → PASS.
- [ ] **Step 5: Commit** `feat(podcast): candidate preview videos`.

### Task 5: Source window, Gate 0 (`reels-select`) and guard

**Files:**
- Create: `lib/source.py`
- Modify: `lib/reels.py`, `cli.py` (`reels-select`, `main_footage`, `cmd_transcribe` refusal),
  `hooks/guard.py` (block `reels-select` for agents; skip `--episode` values; `moment-scout` read-only;
  qc-reviewer forbidden list + `reels-select`, `episode-transcribe`, `publish-check`)
- Test: `TestReelsSelect`, plus guard tests in `test_podcast.py` that run `guard.py` with JSON stdin (mirror
  `test_plugin.py`'s pattern)

**Interfaces:**
- Produces:
  - `source.window(paths) -> dict` (`path, offset_ms, duration_ms, episode_id, reel_id, windowed`)
  - `source.write(paths, rec: dict) -> Path`
  - `reels.select(ep, picks: list[str], adjust: list[str], by: str, note: str = "", confirm_avoid=(), force=False, resync=False) -> dict`
  - `reels.slice_transcript(ep, reel: Paths, in_ms, out_ms) -> dict`
  - `reels.slice_wav(src: Path, dst: Path, in_ms: int, out_ms: int) -> Path`
  - `recipes.resolve(type_id) -> dict` lives in `lib/recipes.py` (created here as a thin loader, extended in Task 8)

- [ ] **Step 1: Failing tests.**
  - `test_select_creates_reel_project`: pick R01 (in 2000, out 9000) → `output/projects/EP12_R01/00_inputs/source.json`
    has `offset_ms 2000`, `duration_ms 7000`, `content_type`, `recipe.pacing.min_pause_ms`.
    `02_transcription/words.json` word 1 has `start_ms == orig − 2000`, ids start at 1, `episode_word_id` is set.
    `transcript.json.meta.duration_ms == 7000`. The 16 kHz wav has 7000 ms ± 1 sample of frames. Status
    `TRANSCRIBED`.
  - `test_flags_and_verification_carry`: a flagged episode word stays flagged; a verified episode gives a reel
    `verification.json` whose `words_sha1` matches the reel.
  - `test_reselect_noop_and_force`: the same pick returns `unchanged`. `--adjust R01:in=00:00:03.000` without force →
    error; with force → re-sliced, offset ≈ 2880 (snapped).
  - `test_avoid_requires_confirm`, `test_stale_plan_refused` (editing reels-plan.json after validation → error).
  - `test_window_plain_clip`: `window(Paths(root,"CLIP1"))["windowed"] is False` with `offset_ms == 0`.
  - `test_changed_episode_refused`: a changed `fingerprint` in source.json → `window()` returns `stale: True`;
    `cmd_preflight` and `compile_plan` report an error naming `reels-select --force`.
  - `test_guard_blocks_subagent_select`: agent `episode-analyst` running `reel reels-select --episode EP12 --pick R01
    --by editor` → exit 2. With no agent → exit 0. `reel --root X --episode EP12 reels-select …` from an agent → also
    exit 2.
- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement.**
  - **Slicing:** take words with `start_ms ≥ in−50` and `end_ms ≤ out+50`. Rebuild segments from the contained words
    and run `finalize()`.
  - **WAV slice:** the stdlib `wave` module with sample indices.
  - **Selection record:** `selection.json` appends `{picked, adjust, by, note, at, plan_fingerprint}`.
  - **Speakers:** clip and rebase to `00_inputs/speakers.json`; copy `intake.json` into `source.json`.
  - **CLI:** `main_footage()` returns the window path when windowed. `cmd_transcribe` on a windowed project prints the
    refusal (re-slice with `reels-select --resync`) unless the transcript is missing, in which case it re-slices.
- [ ] **Step 4: Run** → PASS; full suite PASS.
- [ ] **Step 5: Commit** `feat(podcast): source window, Gate 0 reel selection, guard`.

### Task 6: Every media read through the window

**Files:**
- Modify: `lib/audio_clean.py` (`clean`), `lib/media.py` (`preflight`), `lib/preview_video.py`, `lib/previews.py`
  (`render_all`), `lib/verify.py` (`build`), `lib/premiere_xml.py` (`build_xml`), `lib/qc.py` (sync + reel checks)
- Test: `TestWindowMedia`

**Interfaces:**
- Consumes: `source.window`.
- Produces: `premiere_xml.build_xml` manifest key `source_offset_ms`; `qc` checks named
  `"Reel starts at its episode in-point"` and `"Reel window inside the episode"`.

- [ ] **Step 1: Failing tests.** Fixture: an episode of 120 s at 29.97 fps (testsrc2 640×360) with a stereo audio track
  that is silent except a 10 ms 1 kHz click at exactly 61.000 s. Reel window 60.000–70.000 s.
  - `test_audio_extract_sample_exact`: `clean()` raw WAV → click onset at 1.000 s ± 1 ms (48 kHz).
  - `test_xml_inpoints_offset`: a minimal plan without pause removal → the first V1 `pproTicksIn ==
    round(60000*TPS/1000)` and `<in> == round(60*24)`; the A1 clean-dialogue ticks start at 0; the `<file>` duration
    covers the full 120 s. The same at offset 2,700,000 ms for a 25 fps 46-min synthetic stub (probe dict injected) →
    ticks exact, no drift.
  - `test_qc_sync_offset_aware`: `run_qc` passes "Dialogue sync preserved" and the two reel checks; tampering an A1
    tick fails it.
  - `test_preview_video_seeks`: `preview_video.render` on the reel finishes in < 30 s and the frame at 0.5 s differs
    from the episode's frame at 0.5 s (mean abs diff > 5).
  - `test_plain_clip_unchanged`: the existing `TestPlanToXML` still passes (run the suite).
  - `test_vfr_flagged`: a probe dict whose `r_frame_rate` differs from `avg_frame_rate` by > 0.5 % → a preflight
    warning containing `variable frame rate`. `probe()` gains `fps_real` from `base_rate`.
- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement.**
  - **Seeking:** add `-ss`/`-t` before `-i` for window reads (accurate seek); frame grabs add `offset`.
  - **XML in-points:** `tin = round((offset+sin_ms)*TPS/1000)` and `fin = round((offset+sin_ms)*fps/1000)` for V1,
    VCUT, A7 and camera-audio A1. The clean A1 uses `sin_ms`.
  - **QC sync:** compares A1 ticks + offset ticks to V1 when A1 is the clean file.
  - **Preflight:** records `window`.
- [ ] **Step 4: Run** → PASS; full suite PASS.
- [ ] **Step 5: Commit** `feat(podcast): window-aware audio, preview, XML and QC`.

### Task 7: Per-shot reframe and camera composition

**Files:**
- Create: `lib/shots.py`
- Modify: `lib/media.py` (preflight: windowed → `report["shots"] = analyze_window(...)` and
  `reframe[file] = {base_scale_percent: cover*100, offset_x: 0, offset_y: 0, cutaways_ms: [], mode: "per-shot"}`),
  `lib/plan.py` (shot layer + `compose_camera`, framing summary, punch-in count excludes `AUTO_*`),
  `lib/timemap.py` (offset scales with mask step)
- Test: `TestShots`

**Interfaces:**
- Produces:
  - `detect_cuts(path, offset_ms, duration_ms, threshold=0.3) -> list[int]`
  - `shots_from_cuts(cuts, duration_ms, min_shot_ms=400) -> list[tuple[int, int]]`
  - `face_boxes(im) -> list[tuple[float, float, float, float]]` (normalised x, y, w, h)
  - `analyze_window(path, offset_ms, duration_ms, faces_fn=face_boxes) -> dict` (`{shots: [{start_ms, end_ms,
    faces: [[cx, cy, w, h]...], n_faces}], method}`)
  - `frame_shots(shots, speakers: dict | None, src_w, src_h, seq_w=1080, seq_h=1920, min_hold_ms=1500, group_fit=0.8) -> list[dict]`
    (camera entries: `decision_id` `AUTO_SHOT`|`AUTO_CUTAWAY`, `type "reframe"`, `at_ms`, `until_ms`,
    `scale_factor`, `offset_x`, `offset_y 0`, `rationale`, `target`)
  - `compose_camera(story: list, layer: list, src_w, src_h, seq_w, seq_h) -> list[dict]` (non-overlapping;
    `AUTO_CUTAWAY` entries pass through untouched)

- [ ] **Step 1: Failing tests** (pure functions; faces injected). 1920×1080 source, cover = 1920/1080.
  - `test_single_face_centred`: face cx 0.70 → `offset_x == clamp(-(0.70-0.5)*1920*cover)` = −682.7 ± 0.5, within
    ±`(1920*cover-1080)/2`.
  - `test_group_fits_uses_group_centre`: faces 0.45 and 0.55 → one `AUTO_SHOT` centred on 0.5.
  - `test_no_face_is_cutaway`: `decision_id == "AUTO_CUTAWAY"`, `scale_factor == round(fit/cover, 5)` with
    fit = min(1080/1920, 1920/1080).
  - `test_two_shot_follows_speaker`: faces 0.25 and 0.75; people host=left, guest=right; turns host 0–4000, guest
    4000–9000 → two entries split at 4000, offsets for 0.25 then 0.75.
  - `test_min_hold_merges_short_turns`: a 900 ms guest turn inside host speech → no separate entry.
  - `test_unknown_layout_whole`: no speakers → `AUTO_CUTAWAY` with a rationale mentioning `speaker`.
  - `test_no_faces_anywhere_note`: `analyze_window` with `faces_fn` always empty → `note` mentions `motion` (an
    audio-only podcast: suggest motion mode).
  - `test_compose_punch_in_over_shot`: shot offset −300 at scale 1.0 plus story punch-in 1.15 offset 0 → composed
    `scale_factor 1.15`, `offset_x −345`, story id kept.
  - `test_timemap_scales_offset_on_mask_step`: a piece with cam offset −300 stepped to 1.06 → offset −318.
  - `test_plan_uses_shot_layer`: `compile_plan` on a windowed reel fixture with `preflight["shots"]` (2 shots) →
    `main_segments` include a boundary at the shot cut and `framing` starts with `per-shot`.
- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement.**
  - **Cuts:** `detect_cuts` follows `ref_analysis.detect_cuts` with `-ss/-t`.
  - **Faces:** `face_boxes` uses Vision when available, else the OpenCV cascades from `previews._face_center_opencv`,
    returning every box ≥ `face_min_ratio` of the largest.
  - **Plan:** the shot layer replaces the old `rf`/cutaway path only when `preflight["shots"]` exists for the main
    footage.
- [ ] **Step 4: Run** → PASS; full suite PASS.
- [ ] **Step 5: Commit** `feat(podcast): per-shot 9:16 reframe with speaker follow`.

### Task 8: Recipes applied, music placement, `reel music`

**Files:**
- Modify: `lib/recipes.py` (`resolve`, `for_paths`), `cli.py` (`audio-clean` `--min-pause/--pad` default None →
  recipe or 250/80; new `music --list`), `lib/plan.py` (recipe warnings + `recipe` and deviations in the spec and
  edit-plan.md; `music.file` validation), `lib/premiere_xml.py` (music clip on A06), `lib/preview_video.py` (mix
  music), `lib/qc.py` (the existing "Music placed" check works unchanged)
- Test: `TestRecipes`

**Interfaces:**
- Produces:
  - `recipes.for_paths(paths) -> dict | None` (recipe from source.json, else None)
  - `music_library(root) -> list[dict]` (`rel, moods, license`) in `lib/recipes.py`
  - `spec["recipe"] = {"type", "deviations": [...]}`
  - `spec["music"]` gains `file, level_db, status "PLACED"`

- [ ] **Step 1: Failing tests.**
  - `test_audio_clean_defaults_from_recipe`: a drama reel → the CLI resolves `min_pause 600`, `pad 160`. A clip →
    250/80. An explicit `--min-pause 300` wins.
  - `test_plan_warns_on_recipe_excess`: an emotional reel with 2 graphics in 10 s → a warning containing
    `recipe emotional`; `recipe_note` is shown in edit-plan.md.
  - `test_music_placed_in_xml`: `music.file = "data/Music/warm_track.wav"` (a fixture file) → the XML has a clipitem
    named `MUSIC` on the A06 pair, level `10**(-24/20)`, ending at the sequence end; `spec.music.status == "PLACED"`;
    a file outside `data/Music` → plan error.
  - `test_music_library_tags`: `data/Music/music.json` moods win over file-name tokens.
- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement** music as a looped-free single clip (trimmed to the duration; a 2 s fade-out via an
  audio-levels keyframe pair), on its own A06 L/R pair added to `aorder`.
- [ ] **Step 4: Run** → PASS; full suite PASS.
- [ ] **Step 5: Commit** `feat(podcast): content-type recipes and licensed music placement`.

### Task 9: `stat_card` and `context_card` templates

**Files:** Modify `config/defaults/graphics-templates.json`, `lib/previews.py` (`render_event`), `lib/plan.py`
(required fields; `value` and `label` in `ONSCREEN_KEYS`), `lib/common.py` (`CAPTION_HIDE_SAFE` + `stat_card`),
`lib/ppro_build.py` (`stat_card` in the caption-avoid list). Test: `TestNewTemplates`.

**Interfaces:**
- Produces:
  - template `stat_card`: track V04, category typography, `in_frames 8`, `out_frames 5`, `sfx shimmer`, `value_size 150`,
    `label_size 52`, `y 1050`, `w 760`, `radius 36`
  - template `context_card`: track V05, category typography, `in_frames 6`, `out_frames 5`, `sfx null`, `size 44`,
    `y 330`, `max_chars 34`

- [ ] **Step 1: Failing tests.**
  - `test_stat_card_requires_value`: a plan error without `value`.
  - `test_render_new_templates`: `render_all` → both PNGs are non-empty and the alpha bbox lies inside the safe area
    (context_card's top ≥ 250 px); the job_data lane is `card`.
  - `test_flagged_word_blocks_stat_value`: a flagged word in `value` → a plan error.
- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement** the renderers with `_text_block`, `_round_rect` and brand colours (value in primary on a
  glass card; context pill in primary with white text).
- [ ] **Step 4: Run** → PASS.
- [ ] **Step 5: Commit** `feat(podcast): stat_card and context_card templates`.

### Task 10: Publish package check (`publish-check`)

**Files:** Create `lib/publish.py`, `config/defaults/platform-limits.json`. Modify `cli.py`. Test: `TestPublish`.

**Interfaces:**
- Produces:
  - `check(ep) -> dict` (`{ok, errors, warnings, files, approvals}`)
  - `norm_url(u: str) -> str` (lower-case host, strip scheme, `www.`, trailing `/.,)»"`)
  - `count_tags_chars(tags) -> int`
  - `chapters(ep, pub) -> list[tuple[int, str]]`
  - Writes `publish/youtube.md`, `chapters.txt`, `tags.txt`, `<EP>.srt`, `reels/<REEL>.md` and
    `publish-validation.json`.

- [ ] **Step 1: Failing tests** (a fixture `publish.json` that passes, then mutated per test).
  - `test_valid_package_renders_files`: ok; `chapters.txt` first line starts `00:00 `; youtube.md contains all 3
    titles and the sheet link.
  - `test_title_limits`, `test_angle_brackets_rejected`, `test_description_5000`, `test_tags_500` (a tag with spaces
    counts +2), `test_hashtags_15`.
  - `test_chapter_rules`: first not 0 → error; 2 chapters → error; a 5 s chapter → error.
  - `test_invented_link_rejected`; `test_link_normalisation` (sheet `https://www.x.com/a.` vs copy `x.com/a/` → OK).
  - `test_quote_must_exist`: `«انا قلت ان الشركه»` OK against transcript `أنا قلت إن الشركة`; an invented quote →
    error.
  - `test_reel_caption_limits`: Instagram 2300 characters → error; 31 hashtags → error.
- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement** per spec §4.8 with the limits from `platform-limits.json`.
- [ ] **Step 4: Run** → PASS.
- [ ] **Step 5: Commit** `feat(podcast): publish package validation and rendering`.

### Task 11: Thumbnails (`publish-thumbnail`)

**Files:** Modify `lib/publish.py`, `cli.py`. Test: `TestThumbnails`.

**Interfaces:**
- Produces:
  - `thumbnail_candidates(ep, n=12, faces_fn=None) -> dict` (`publish/thumbnail/candidates/T01_<ms>.jpg`,
    `_candidates.jpg`, `candidates.json`)
  - `render_thumbnails(ep) -> dict` (`thumb_1..3.png` or `.jpg`, each ≤ 2 MB, 1280×720)

- [ ] **Step 1: Failing tests.**
  - `test_candidates_spaced_and_faced`: inject `faces_fn` returning a face only for frames whose mean brightness
    > 100 (fixture alternates bright/dark every 10 s on a 120 s video, `n = 3`) → 3 candidates, all bright, pairwise
    ≥ 30 s apart.
  - `test_render_design`: one design → a 1280×720 file of size ≤ 2,000,000 bytes; warning for a 7-word text.
- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement.**
  - **Sampling:** ffmpeg `fps=1/X,scale=640:-2` raw frames, `X = max(10, dur/150)`.
  - **Scoring:** sharpness is the variance of a numpy Laplacian.
  - **Render:** the text uses `Brand(paths.client_db).font("headline", 110)` through `_text_block`; the highlight
    bar is in brand primary.
- [ ] **Step 4: Run** → PASS.
- [ ] **Step 5: Commit** `feat(podcast): thumbnail candidates and designs`.

### Task 12: `episode-next`

**Files:** Modify `lib/episode.py`, `cli.py`. Test: `TestEpisodeNext`.

**Interfaces:**
- Produces: `episode_next(ep) -> dict` (`{next, remaining, stale, reels: {id: next}}`). Steps in order: `episode-prep`,
  `episode-transcribe`, `AUTHOR 01_analysis/topics.json`, `AUTHOR 01_analysis/speakers.json`,
  `AUTHOR 01_analysis/reels-plan.json`, `reels-plan`, `reels-preview`, `SELECT reels (Gate 0: editor)`,
  `AUTHOR publish/publish.json`, `publish-check`, `publish-thumbnail --candidates`.

- [ ] **Step 1: Failing test** `test_next_progression`: a fresh episode → `next == "episode-prep"`. After prep and a
  fake transcript → `AUTHOR 01_analysis/topics.json`. Touching reels-plan.json after validation → `stale` contains
  `reels-plan`.
- [ ] **Step 2–4:** implement, run → PASS.
- [ ] **Step 5: Commit** `feat(podcast): episode-next resumable status`.

### Task 13: Plugin layer — agents, skills, hooks context, evals

**Files:**
- Create: `agents/episode-analyst.md`, `agents/moment-scout.md`, `agents/publish-writer.md`,
  `skills/podcast/SKILL.md`, `skills/episode-craft/SKILL.md` (+ `references/content-types.md`,
  `references/moment-scoring.md`), `skills/publish-craft/SKILL.md` (+ `references/platform-rules.md`),
  `evals/podcast-reels-plan/{prompt.md,graders/criteria.md}`, `evals/publish-package/{prompt.md,graders/criteria.md}`
- Modify:
  - agents: `intake-inspector.md`, `transcript-editor.md`, `story-editor.md`, `qc-reviewer.md`, `frame-inspector.md`,
    `motion-designer.md`
  - skills: `edit`, `autopilot`, `help`, `status`, `story-craft`, `motion-craft`, `qc-craft`, `transcript-craft`,
    `start`
  - hooks: `hooks/session_context.py` (mention episodes)
- Test: extend `test_plugin.py` checks automatically (frontmatter, skill names); add `test_podcast.py::TestPluginLayer`:
  - every new agent has `name`, `description`, `tools` and `model`
  - `moment-scout` tools are `Read` only
  - the podcast skill mentions `reels-select --by editor` and "Gate 0"
  - the session context for a client with `data/Episodes` mentions `podcast`

- [ ] **Step 1:** Write the TestPluginLayer tests → run → FAIL.
- [ ] **Step 2:** Write the Markdown in the existing style: report format, "When to invoke", non-negotiables. The
  podcast playbook stages are: prep → intake-inspector ∥ transcribe → (verify) → episode-analyst (fan-out
  moment-scouts) → reels-plan → reels-preview → **Gate 0** → per reel: the existing edit pipeline with the recipe,
  publish-writer for the episode in parallel → combined Gate 1 → build → QC → publish-check/thumbnails → report.
- [ ] **Step 3:** Run the full suite → PASS.
- [ ] **Step 4: Commit** `feat(podcast): agents, skills, evals for podcast mode`.

### Task 14: Docs, version 2.1.0, package

**Files:** Modify `README.md`, `CHANGELOG.md`, `.claude-plugin/plugin.json` (version `2.1.0`; the description adds
podcast episodes → reels plan → reels + publish package; keywords `podcast`, `youtube`, `shorts`), `package.py`
(`SKIP_DIRS` + `docs`), `.claude-plugin/marketplace.json` version if present.

- [ ] **Step 1:** Edit the docs: a commands table with the new commands, a podcast quick start in EN and AR, and the
  output tree.
- [ ] **Step 2:** `"$PY" package.py` → JSON with `corrupt_member: null` and `has_manifest: true`; the zip has no
  `docs/`.
- [ ] **Step 3:** Run the full suite → PASS.
- [ ] **Step 4: Commit** `docs: WhyNot Cut 2.1.0 podcast mode`.

### Task 15: Live verification on this PC

**Files:** Test client `whynot-test/PODCAST-TEST/` (scaffolded; the episode copied from
`whynot-test/Dr Sherin Helmy/data/Raw/EP02_R02.mov` by a Python setup script as fixture creation; brand assets copied
from the Dr Sherin Helmy folder).

- [ ] **Step 1:** `reel episode-prep`, `episode-transcribe` (GPU) → transcript exists; view the intake sheet.
- [ ] **Step 2:** Author topics/speakers/reels-plan (≥ 2 candidates) as the episode-analyst would, then `reels-plan` →
  ok; `reels-preview` → view the sheet.
- [ ] **Step 3:** `reels-select --by editor --note "live test authorised by the user's 'continue to the end'"` for 1
  reel, then run the reel through audio-clean → plan → previews → preview-video → approve → ppro-build (bridge) →
  ppro-frames → view the frames → verify --record → qc.
- [ ] **Step 4:** Author publish.json → `publish-check` ok → thumbnails → view.
- [ ] **Step 5:** Record evidence and limits in the final report; update the memory file `whynot-cut-plugin.md`.
