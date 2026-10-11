# WhyNot Cut 2.2 Motion from Audio — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** An editor picks an episode window at Gate 0 "as motion" and gets an animated video built from its audio only:
a validated motion plan and animatic for Gate 1, then a native After Effects project built by Claude through the
WhyNot Cut Bridge, read back, rendered, QC'd from AE's own frames, and captioned in the publish package.

**Architecture:** The podcast engine gains audio episodes and `reels-select --as motion`, which creates a clip-like
project `<EP>_<ID>_MO`. A `motion-director` agent writes `motion-script.json`; pure Python modules check truth
(`motion_script`), timing (`motion_timing`), layout (`motion_layout`) and compile `motion-plan.json` in frames and
pixels (`motion_plan`). An ES3 library (`nh_motion_lib.jsx`) renders that plan inside AE, sent through the existing CEP
bridge made host-aware (`cep_queue`, `ae_bridge`, `nh_ae_bridge.jsx`); `aerender` + ffmpeg make the master, MP4 and QC
frames; `motion_qc` decides from read-back, render, audio and recorded visual verification.

**Tech Stack:** Python 3.10–3.12 in the engine venv (numpy, Pillow, uharfbuzz/freetype, PyAV), ffmpeg, stdlib
unittest, ExtendScript (ES3) for After Effects 24+, CEP (CSXS 11+) panel JS, Markdown agents/skills, Lucide icons
(ISC, vendored SVG).

**Spec:** `docs/superpowers/specs/2026-10-11-motion-from-audio-design.md`

## Global Constraints
- Tests: `PY="C:/Users/LOQ/.whynot-cut/venv/Scripts/python.exe"`, from `whynot-cut-marketplace-motion/`:
  `"$PY" -B -m unittest discover -s whynot-cut/tests` → all OK. Baseline on the branch: 197 tests, 4 skipped; the
  existing tests stay unchanged. New tests go in `whynot-cut/tests/test_motion.py` (same header and `sys.path` setup as
  `test_podcast.py`; reuse its `ff`, `make_episode_client`, `synthetic_episode_transcript`, `validated_plan`,
  `run_guard` by importing `test_podcast`). Use the venv: system Python silently skips the HarfBuzz tests.
- Engine code in `whynot-cut/engine/reel/lib/`; config defaults in `whynot-cut/config/defaults/`, read only through
  `load_config(name)` (profile-overridable). Motion CLI commands live in `lib/motion_cli.py` (same `ARGS` /
  `add_args` / `dispatch` pattern as `podcast_cli.py`), registered in `cli.py`.
- Time: integer source ms → `TimeMap` (pause removal) → sequence frames at `seq_fps()`. In JSX every key time is
  `frame * comp.frameDuration`.
- Ids: motion project `f"{EP}_{ID}_MO"` (`EP12_R03_MO`, `EP12_T02_MO`); scenes `S\d+`; AE layer names
  `<scene id>_<kind>_<n>` (e.g. `S03_text_1`), scene comps `<scene id>_<type>`, main comp `MAIN_<reel id>`.
- Formats: `9x16` = 1080×1920, safe top 250 / bottom 420 / sides 90 px; `16x9` = 1920×1080, safe top 90 / bottom 120 /
  sides 160 px. Motion window hard limits 15–180 s.
- Timing values: `scene_lead_ms` 150, `word_reveal_ms` 180, `outro_ms` 2500, transitions cut 0 / push 400 / wipe 400 /
  scale 300 / fade 500 ms, speech-edge slack 1500 ms, `max_drop_ratio` 0.4, contrast ≥ 4.5 (≥ 3.0 at ≥ 64 px).
- Allowed asset licenses: `CC0-1.0, MIT, ISC, Apache-2.0, CC-BY-4.0` (attribution required), `commercial` (needs
  `proof`). Icons: Lucide, vendored with its ISC `LICENSE`.
- SFX kinds only from `sfx.RECIPES`; music only from `data/Music`.
- Never write Adobe preferences (PlayerDebugMode, AE Type text-engine preference, scripting security). ExtendScript
  never writes files (only `app.project.save`); the panel's Node side writes results. `assets/` and `data/` are never
  written. No new pip dependencies.
- Clips, video reels and every existing command behave exactly as in 2.1.0 unless a task says otherwise; the Premiere
  side of the bridge keeps its queue, scripts folder, entry point and Python API.
- Before Tasks 1, 3 and 17 (shared engine files: `ppro_bridge.py`, the CEP bundle, `cli.py`, `qc.py`, `verify.py`,
  `handoff.py`, `publish.py`), message the "Reel editing plugin enhancement" session (`SendMessage`; find it with
  `mcp__ccd_session_mgmt__list_sessions {"linked": true}`) and agree file ownership. Installing the bundle and using
  the Premiere bridge also need that agreement.
- Commit after each task: `git commit -m "<type>(motion): <what>"` ending with
  `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.

## Review Focus
1. **Paths with spaces and Arabic** (`D:/0 Work/…/Dr Sherin Helmy`, `data/Episodes/حلقة 12.m4a`) through the JSON job
   file, JSX `File()` paths and `aerender`/ffmpeg command lines: they must arrive unchanged (ASCII-escaped JSON, list
   arguments, never a shell string). Tests in Tasks 2 and 13.
2. **Fractional frame rates** (29.97, 23.976) with pauses removed: cue frames must not drift over a 180 s window, and
   the JSX must place keys by `frameDuration`, not `frame / fps`. Tests in Tasks 9 and 13.
3. **Fast talkers / dense windows**: a scene too short for its cues, or more words than the recipe allows, must fail
   at `motion-plan` with a message naming the scene, never reach AE as unreadable frames. Tests in Tasks 9 and 11.
4. **The editor's own AE session**: an unsaved project open in AE, or edits the editor made in our `.aep`, are never
   discarded by a build. Tests in Task 15.
5. **One speaker or no speaker turns** (audio-only episodes often have no `speakers.json`): the badge is simply off,
   captions still work, no error. Test in Task 11.

---

### Task 1: Host-aware bridge (Premiere + After Effects)

**Files:**
- Create: `lib/cep_queue.py`, `lib/ae_bridge.py`, `lib/motion_cli.py`, `templates/after_effects/nh_ae_bridge.jsx`,
  `templates/after_effects/nh_motion_lib.jsx` (header + `var NHM = NHM || {};` only), `tests/test_motion.py`
- Modify: `lib/ppro_bridge.py` (status/submit delegate to `cep_queue`; `BRIDGE_VERSION = "3.1.0"`),
  `templates/premiere/cep_bridge/js/bridge.js`, `templates/premiere/cep_bridge/CSXS/manifest.xml`,
  `engine/reel/cli.py` (register `motion_cli` after `podcast_cli`; `NO_ROOT` gains `ae-status`, `ae-probe`)

**Interfaces:**
- Produces:
  - `cep_queue.status(queue: Path, max_age_s: float = 5.0) -> dict` — keys `alive, age_s, busy, bridge_version, host,
    detail` (today's `ppro_bridge.status` logic, plus `host` from the heartbeat)
  - `cep_queue.submit(queue: Path, script: Path, action: str, data: dict | None = None, timeout: float = 600,
    poll_s: float = 0.5) -> dict` — today's `ppro_bridge.submit` protocol (ASCII data file, atomic `.tmp` → `.job.json`,
    wait for `.result.json`): `{ok, bridge_ok, response, elapsed_s, job}` or `{ok: False, error, status|job}`
  - `ae_bridge.QUEUE = ENV_DIR / "ae-queue"`, `ae_bridge.SCRIPTS = ENV_DIR / "ae-scripts"`,
    `ae_bridge.LIBS = ("nh_ae_lib.jsx", "nh_motion_lib.jsx", "nh_ae_bridge.jsx")` (from `templates/after_effects/`),
    `ae_bridge.ENTRY = SCRIPTS / "nh_ae_bridge.jsx"`
  - `ae_bridge.sync_scripts() -> {"scripts_dir": str, "synced": list[str], "sha256": dict[str, str]}` (copies only
    changed files, atomic replace)
  - `ae_bridge.status() -> dict` (`cep_queue.status(QUEUE)`; a heartbeat whose `host != "AEFT"` → `alive: False`)
  - `ae_bridge.submit(action: str, data: dict | None = None, timeout: float = 900) -> dict` (syncs, then
    `cep_queue.submit(QUEUE, ENTRY, …)`)
  - JSX `NHAE.run(dataPath) -> String` (JSON `{ok, action, result}` or `{ok: false, action, error, line}`); tiny JSON
    helpers `NHAE.q/str/read` as in `NHPP`; every action runs between `app.beginSuppressDialogs()` and
    `app.endSuppressDialogs(false)` (in `finally`). `nh_ae_bridge.jsx` loads the other two libraries with
    `$.evalFile(File($.fileName).parent.fsName + "/<lib>")`.
  - Actions: `ping` → `{ae_version: app.version, project: name|null, project_path: fsName|null, dirty: bool|null}`;
    `fonts` (`data.postscript_names: [..]`) → `{fonts: {ps: {found, substitute, family, style}},
    missing_or_substituted: [ps]}` via `app.fonts.getFontsByPostScriptName` and `app.fonts.missingOrSubstitutedFonts`.
  - `motion_cli.ARGS: dict`, `motion_cli.NO_ID: set`, `add_args(name, sp)`, `dispatch(a) -> bool`; `reel ae-status`
    prints `{"bridge": ae_bridge.status(), "debug_mode_ok": plat.debug_mode_ok(), "next": …}`.
- bridge.js: `var HOSTS = { PPRO: { queue: 'ppro-queue', scripts: 'ppro-scripts', entry: 'NHPP' }, AEFT: { queue:
  'ae-queue', scripts: 'ae-scripts', entry: 'NHAE' } };` host = `JSON.parse(window.__adobe_cep__.getHostEnvironment())
  .appName`, default `PPRO`; heartbeat gains `host`; eval code uses the host's entry; `VERSION = '3.1.0'`.
- manifest: `<Host Name="PPRO" Version="[22.0,99.9]"/>` and `<Host Name="AEFT" Version="[24.0,99.9]"/>`,
  `ExtensionBundleVersion="3.1.0"`.

- [ ] **Step 1: Message the other session** about `ppro_bridge.py` and the CEP bundle (Global Constraints); wait for
  agreement.
- [ ] **Step 2: Write failing tests** in `test_motion.py`, class `TestBridge` (temp queue dirs; a helper thread
  `fake_panel(queue, host)` writes a heartbeat `{"at": now_ms, "busy": false, "version": "3.1.0", "host": host}` every
  0.2 s, claims `*.job.json` by renaming to `.running`, and writes `<id>.result.json`
  `{"ok": true, "result": "{\"ok\": true, \"echo\": <data.action>}"}`):
  - `test_queue_roundtrip`: `cep_queue.submit(q, script, "ping", {"a": 1}, timeout=10)` → `ok` True,
    `response["echo"] == "ping"`, the data file was pure ASCII.
  - `test_queue_timeout`: heartbeat only, nobody answers, `timeout=1` → `ok` False and `"timeout" in error`.
  - `test_queue_dead_heartbeat`: heartbeat 30 s old → `ok` False, `error == "bridge not running"`.
  - `test_ppro_api_unchanged`: `list(inspect.signature(ppro_bridge.submit).parameters) == ["action", "data",
    "timeout", "script"]`, `ppro_bridge.QUEUE.name == "ppro-queue"`, `ppro_bridge.BRIDGE_VERSION == "3.1.0"`.
  - `test_ae_status_needs_aeft`: a `PPRO` heartbeat in the AE queue → `ae_bridge.status()["alive"]` False.
  - `test_bridge_js_hosts`: bridge.js contains both `HOSTS` entries above and `getHostEnvironment`; passes
    `assert_js_syntax` (import from `test_pipeline`).
  - `test_manifest_hosts`: parsed manifest hosts == `{"PPRO": "[22.0,99.9]", "AEFT": "[24.0,99.9]"}`, bundle 3.1.0.
  - `test_ae_sync_scripts`: with `ae_bridge.SCRIPTS` patched to a temp dir, the first sync copies the 3 files (same
    SHA-256 as the templates), the second returns `synced == []`.
  - `test_ae_bridge_jsx_syntax`: `nh_ae_bridge.jsx` and `nh_motion_lib.jsx` pass `assert_js_syntax`.
- [ ] **Step 3: Run** `"$PY" -B -m unittest discover -s whynot-cut/tests -p test_motion.py` → FAIL (modules missing).
- [ ] **Step 4: Implement** the interfaces above; `ppro_bridge.status/submit` become one-line calls into `cep_queue`.
- [ ] **Step 5: Run** the motion tests, then the full suite → all PASS (existing Premiere bridge tests unchanged).
- [ ] **Step 6: Commit** `feat(motion): host-aware WhyNot Cut Bridge for After Effects (3.1.0)`.

### Task 2: Arabic capability probe and the aerender helper

**Files:**
- Create: `lib/ae_probe.py`, `lib/ae_render.py`
- Modify: `templates/after_effects/nh_ae_bridge.jsx` (action `probe_text`), `lib/motion_cli.py` (`ae-probe`)

**Interfaces:**
- Consumes: `ae_bridge.submit` (Task 1).
- Produces:
  - `ae_render.aerender_cmd(aerender: str, aep: Path, comp: str, out: Path, rs: str, om: str,
    start_frame: int | None = None, end_frame: int | None = None) -> list[str]`
  - `ae_render.render(aep: Path, comp: str, out: Path, rs: str, om: str, start_frame=None, end_frame=None,
    timeout: int = 3600, log: Path | None = None) -> dict` — `{status: RENDERED|FAILED|SKIPPED, returncode, output,
    elapsed_s, log}`; RENDERED only when `out` exists and is newer than the call start; `aerender` from
    `plat.aerender_path()`
  - `ae_render.extract_frames(video: Path, frames: list[int], fps: float, out_dir: Path,
    names: list[str] | None = None) -> list[Path]` (one ffmpeg call per frame, input seek to `(frame + 0.5) / fps`)
  - `ae_probe.PROBE_DIR = ENV_DIR / "ae-probe"`, `ae_probe.CAPS = ENV_DIR / "ae-capabilities.json"`
  - `ae_probe.probe_job(fonts: dict[str, str]) -> dict` — comps (each 1080×1920, 30 fps, 3 s): `arabic_rtl`,
    `word_reveal` (text `"واحد اتنين تلاتة اربعة"`, cue frames `[15, 30, 45, 60]`), `emphasis` (word 3 in red),
    `mixed` (`"الـ Isotretinoin ٣ مرات 25%"`), `brand_font`, `icon` (hand-written check-mark subpath with Trim Paths);
    plus `aep_path = PROBE_DIR / "probe.aep"`
  - `ae_probe.capabilities_from(readback: dict, om_pref: str) -> dict` — keys `composer_universal: bool`,
    `rtl_direction: "textdocument" | "paragraph_range" | False`, `fontobject: bool`, `emphasis_animator: bool`,
    `om_template: str`, `templates: list[str]`
  - `ae_probe.run_probe(fonts: dict | None = None, timeout: int = 600) -> dict` — submits `probe_text`, renders frames
    (`word_reveal` at frames 20 and 65; every other comp at frame 75) into `PROBE_DIR/frames/`, writes `CAPS`
    (`{ae_version, measured, frames, word_index_logical: None, verdict: None}`)
  - `ae_probe.record(verdict: str, notes: str, word_order: str) -> dict` (`"ok"|"fail"`, `"logical"|"visual"`; sets
    `word_index_logical`, `verdict`, `recorded_at`)
  - `ae_probe.verdict_ok(ae_version: str) -> bool` (an `ok` verdict recorded for that exact version)
  - JSX `probe_text` builds and saves the probe project and returns per comp `{name, composer, direction_textdocument,
    direction_paragraph_range, font_ps, substitute, rect}` plus `om_templates` (output-module template names).
  - CLI: `reel ae-probe` (run) and `reel ae-probe --record ok|fail --word-order logical|visual --notes "…"`.

- [ ] **Step 1: Write failing tests**, class `TestProbe`:
  - `test_probe_job_shape`: comp names as above; `word_reveal` cue frames `[15, 30, 45, 60]`; the Arabic strings start
    with `"و"` (logical order, not reversed); `json.dumps(job, ensure_ascii=True)` round-trips.
  - `test_capabilities_from_readback`: direction kept on the TextDocument → `"textdocument"`; only via paragraph range →
    `"paragraph_range"`; neither → `False`; composer `"UNIVERSAL"` → `composer_universal`; `om_template` is the
    preferred name when listed, else the first name containing `ProRes` or `Lossless`.
  - `test_record_and_verdict`: with `CAPS` patched to a temp file, `record("ok", "n", "logical")` →
    `verdict_ok(<that version>)` True, `verdict_ok("99.0")` False, `word_index_logical` True.
  - `test_aerender_cmd_paths`: for `aep = Path("D:/0 Work/عميل/x y.aep")` the list contains `-project`, that path as
    ONE item, `-comp`, `MAIN_X`, `-s`, `"10"`, `-e`, `"20"`, `-RStemplate`, `-OMtemplate`, `-output`.
  - `test_extract_frames`: from an ffmpeg testsrc 30 fps 2 s clip, frames `[0, 30, 59]` → 3 PNGs.
- [ ] **Step 2: Run** the motion tests → FAIL.
- [ ] **Step 3: Implement.** `probe_text` sets text with `fontObject` when `app.fonts` exists, composer
  `ComposerEngine.UNIVERSAL_TYPE_ENGINE`, direction on the TextDocument, then reads it back after `setValue`; if lost,
  sets it through `textDocument.paragraphRange(0)` and reads again. Word reveal = text animator (opacity 0) with an
  expression selector, Based On Words: `var T=[…seconds…]; var t=T[textIndex-1]; ease(time, t, t+0.18, 100, 0)`.
- [ ] **Step 4: Run** the motion tests and the full suite → PASS.
- [ ] **Step 5: Commit** `feat(motion): AE Arabic capability probe and aerender helper`.

### Task 3: Live gate — bridge in AE, probe verdict, Premiere still answers

**Files:** none in the repo unless a fix is needed (capabilities live in the engine home).

- [ ] **Step 1:** Agree with the other session before reinstalling the bundle (it replaces the Premiere bridge).
- [ ] **Step 2:** `reel ppro-install` → JSON with `debug_mode_ok: true`. Ask the user to restart After Effects and
  Premiere (the plugin never restarts their apps).
- [ ] **Step 3:** `reel ae-status` → `alive: true`, `host: "AEFT"`; `reel ppro-status` → alive (Premiere).
- [ ] **Step 4:** `reel ae-probe` → frames in `~/.whynot-cut/ae-probe/frames/`. VIEW every frame: letters joined,
  words right-to-left, at frame 20 only `واحد` (rightmost) is visible, emphasis on the 3rd word, mixed line correct,
  brand font, icon drawn.
- [ ] **Step 5:** `reel ae-probe --record ok|fail --word-order logical|visual --notes "<what the frames showed>"`.
- [ ] **Step 6:** Premiere re-check: `reel ppro-frames --root "<PODCAST-TEST>" --video-id <an existing reel>` → frames
  exported.
- [ ] **Step 7: Gate.** If AE cannot load the bridge, or the Arabic frames fail with no fallback in the spec's probe
  table, STOP: report the evidence to the user and the parent session, and propose the spec change. Otherwise note
  the capabilities (version, direction mode, word order) in the task report and continue.

### Task 4: Audio-only episodes

**Files:**
- Modify: `lib/discover.py` (classify), `lib/episode.py` (`prep`, `list_episodes`), `lib/reels.py`
  (`render_candidates`)
- Test: `tests/test_motion.py`

**Interfaces:**
- Produces: inventory records for episodes carry `"media": "audio" | "video"`; `list_episodes()` rows carry `media`;
  `episode.json["media"]`; `reels.audio_card(ep, cand: dict, out: Path) -> Path` (540×960 H.264 + the window's audio:
  a dark card with the Latin label `id · in–out · type` and the window's waveform drawn with Pillow).

- [ ] **Step 1: Write failing tests**, class `TestAudioEpisodes` (client from `make_episode_client` plus
  `data/Episodes/POD3.m4a`, 20 s sine, and `POD3.md` = `SHEET`):
  - `test_audio_episode_discovered`: inventory role `episode`, `media == "audio"`; `EP12.mp4` has `media == "video"`.
  - `test_prep_audio`: `prep()` → `episode.json["media"] == "audio"`, `intake_sheet is None`, no warning containing
    `"16:9"`, `abs(duration_ms - 20000) <= 100`.
  - `test_preview_audio_card`: with a validated plan (`validated_plan`) for `POD3`, `render_candidates` writes
    `03_candidates/R01.mp4` with a 540×960 video stream and an audio stream, duration = window ±0.1 s.
- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement**: audio under `data/Episodes/` → role `episode`; `prep` skips the aspect check and intake
  frames when there is no video stream; `render_candidates` uses `audio_card` for audio episodes.
- [ ] **Step 4: Run** motion tests + full suite → PASS.
- [ ] **Step 5: Commit** `feat(motion): audio-only podcast episodes`.

### Task 5: Recipe motion blocks, `motion.json`, Gate 0 `--as motion`

**Files:**
- Create: `config/defaults/motion.json`, `lib/motion_config.py`
- Modify: `config/defaults/recipes.json` (a `motion` block per type), `lib/reels.py` (`select`), `lib/podcast_cli.py`
  (`--as`, `--format`, `--type`), `lib/episode.py` (`episode_next` lists motion projects)

**Interfaces:**
- Produces:
  - `motion_config.motion_cfg() -> dict`; `format_spec(fmt: str) -> dict` (`w, h, safe{top,bottom,side}, text_box_w,
    sizes{title, quote, body, label, stat, caption}` as `[max, min]` px; unknown → `SystemExit`);
    `direction_for(lang: str | None) -> "rtl" | "ltr"` (`ar, fa, ur, he` → rtl); `is_motion(paths) -> bool`
    (`source.json["kind"] == "motion_reel"`); `recipe_motion(paths) -> dict` (the reel's `recipe["motion"]`)
  - `reels.motion_id(episode_id: str, src_id: str) -> str` → `f"{episode_id}_{src_id}_MO"`
  - `reels.select(ep, picks, adjust, by, note="", confirm_avoid=(), force=False, resync=False, as_: str = "video",
    fmt: str = "9x16", type_: str | None = None) -> dict`
  - motion `source.json`: the episode-reel keys plus `kind: "motion_reel"`, `source_id`, `format`, `media`,
    `language`, `direction`, and `candidate` or `topic` (spec §3.3)
  - `selection.json` history entries gain `as` and `format`
- `motion.json` keys and values: `formats` (sizes 9x16: title [120,72], quote [96,56], body [64,44], label [52,36],
  stat [260,160], caption [54,54], `text_box_w` 900; 16x9: title [110,64], quote [84,52], body [56,40], label [44,32],
  stat [220,140], caption [48,48], `text_box_w` 1500; safe areas per Global Constraints), `duration_s {hard_min: 15,
  hard_max: 180}`, `scene_lead_ms`, `word_reveal_ms`, `transition_ms`, `outro_ms`, `edge_slack_ms`, `max_drop_ratio`,
  `min_contrast`, `min_contrast_large`, `large_px: 64`, `rtl_mirror_icons` (arrow-right, arrow-left, arrow-up-right,
  chevron-right, chevron-left, chevrons-right, chevrons-left, trending-up, trending-down, move-right, move-left,
  send, reply, forward, undo, redo, log-in, log-out), `themes` (dark/light/brand per spec §3.7),
  `render {rs_template: "Best Settings", om_template: "High Quality"}`, `library_dir: null`,
  `fallback_fonts {windows: "SegoeUI-Bold", mac: "GeezaPro-Bold"}`, `licenses_allowed`.
- Recipe `motion` blocks: exactly the spec §3.6 table and the defaults paragraph under it.

- [ ] **Step 1: Write failing tests**, class `TestMotionGate0` (fixture: the `TestReelsSelect.setUp` client, built by a
  helper `motion_episode_fixture(tmp)` in `test_motion.py`, plus `topics.json` with `T01` 2–9 s and no type):
  - `test_recipes_have_motion_blocks`: every type has the 15 keys; drama `reveal == "word"`, `transition == "cut"`,
    `theme == "dark"`, `captions == "off"`; emotional `reveal == "line"`, `ease == "gentle"`, `transition == "fade"`,
    `max_words_on_screen == 18`, `emphasis_per_scene == 1`; every `sfx_on_transition` is `None` or in `sfx.RECIPES`.
  - `test_profile_override_motion`: a client profile `recipes.json` with `types.advice.motion.theme = "dark"` →
    `recipes.resolve("advice")["motion"]["theme"] == "dark"` and `["transition"] == "wipe"`.
  - `test_select_as_motion`: `select(ep, ["R01"], [], "editor", as_="motion")` → `EP12_R01_MO/00_inputs/source.json`
    has `kind == "motion_reel"`, `source_id == "R01"`, `format == "9x16"`, `direction == "rtl"`, `media == "video"`,
    `"motion" in recipe`; `02_transcription/words.json` exists; the last history entry has `as == "motion"`.
  - `test_video_and_motion_coexist`: picking `R01` as video, then as motion → both project folders exist.
  - `test_topic_rules`: `["T01"]` with `as_="video"` → `SystemExit` containing `"--as motion"`; motion without type →
    `SystemExit` listing `advice`; with `type_="advice"` → recipe type `advice`, `0 <= in_ms < out_ms`.
  - `test_topic_too_long`: profile `motion.json` `duration_s.hard_max = 5` → `SystemExit` containing `"split it"`.
  - `test_audio_episode_video_refused`: the `POD3` audio episode, `as_="video"` → `SystemExit` containing
    `"no picture"`.
  - `test_episode_next_lists_motion`: after the motion pick, `episode_next(ep)["reels"]` has key `EP12_R01_MO`.
  - `test_cli_args`: `podcast_cli.ARGS["reels-select"]` defines `--as` (choices video/motion), `--format`
    (choices 9x16/16x9), `--type`.
- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement.** Topic edges: `snap_in`/`snap_out` on the episode words, then the motion hard limits. The
  language comes from the sheet `language`, else `transcript.json["meta"]["language"]`.
- [ ] **Step 4: Run** motion tests + full suite → PASS (all existing `reels-select` tests unchanged).
- [ ] **Step 5: Commit** `feat(motion): recipe motion blocks, motion.json, Gate 0 --as motion`.

### Task 6: Icons — vendored Lucide, SVG → AE shapes, search

**Files:**
- Create: `tools/vendor_lucide.py` (dev-only), `templates/motion/icons/lucide/{*.svg, LICENSE, icons.json}`,
  `lib/motion_icons.py`
- Modify: `lib/motion_cli.py` (`motion-icons --search`)

**Interfaces:**
- Produces:
  - `motion_icons.ICON_DIR`; `load_index() -> dict[str, dict]` (`name → {"tags": [...], "categories": [...]}`)
  - `svg_to_shapes(svg_text: str, size: float = 24.0) -> list[dict]` — each subpath `{"vertices": [[x, y]],
    "inTangents": [[dx, dy]], "outTangents": [[dx, dy]], "closed": bool}`, tangents relative to their vertex (AE
    convention), coordinates centred on the viewBox centre and scaled by `size / viewBox width`
  - `icon_shapes(name: str, size: float, mirror: bool = False) -> list[dict]` (mirror negates x)
  - `search(query: str, limit: int = 10) -> list[dict]` (`name, tags, score`; a query token in the name scores 2, in a
    tag 1); `closest(name: str, n: int = 5) -> list[str]` (difflib)
  - `should_mirror(name: str, direction: str) -> bool` (rtl and the name is in `rtl_mirror_icons`)
  - `flatten(shapes: list[dict], tol: float = 0.5) -> list[list[tuple[float, float]]]`

- [ ] **Step 1: Vendor the icons.** Ask the user before downloading: `lucide-static@<pinned version, released ≥ 2
  weeks ago>` tarball from `registry.npmjs.org` (about 2–4 MB). `tools/vendor_lucide.py <version>` checks the
  registry's `dist.integrity` (sha512), extracts `icons/*.svg` and `LICENSE`, and writes `icons.json` from the
  package's tag data (if the tarball has none, tags = the name's tokens). Commit the vendored folder on its own:
  `chore(motion): vendor Lucide icons <version> (ISC)`.
- [ ] **Step 2: Write failing tests**, class `TestIcons`:
  - `test_lines_and_relative`: `M2 2 L22 2 L22 22 Z` → one closed subpath, vertices `[[-10,-10],[10,-10],[10,10]]`,
    zero tangents; `m2 2 l20 0 v20 z` gives the same; `H`/`V` covered by a third path.
  - `test_cubic_and_smooth`: `M0 12 C0 0 24 0 24 12 S24 24 12 24` → 3 vertices; vertex 0 `outTangent == [0, -12]`;
    the `S` control point is the reflection (`inTangent` of vertex 1 `== [0, -12]`, `outTangent == [0, 12]`).
  - `test_arc`: `M2 12 A10 10 0 0 1 22 12` → endpoints `[-10, 0]` and `[10, 0]`; every flattened point is
    10 ± 0.2 from the centre.
  - `test_elements`: `circle r=10` → closed, 4 vertices at distance 10; `rect rx=2` → closed, 8 vertices; `line` →
    open, 2 vertices; `polyline` open, `polygon` closed.
  - `test_vendored_index`: ≥ 1000 names including `trending-up` and `check`; `LICENSE` contains `ISC`; every indexed
    name has an SVG that `svg_to_shapes` parses without error.
  - `test_search_closest_mirror`: `search("trending up")[0]["name"] == "trending-up"`; `"trending-up" in
    closest("trendingup")`; `should_mirror("arrow-right", "rtl")` True, `("arrow-right", "ltr")` False,
    `("heart", "rtl")` False; `icon_shapes(n, 24, mirror=True)` x values are the negatives of the unmirrored ones.
- [ ] **Step 3: Run** → FAIL. **Step 4: Implement** (arcs: endpoint → centre parameterisation, split into ≤ 90°
  segments, each a cubic). **Step 5: Run** motion tests + full suite → PASS.
- [ ] **Step 6: Commit** `feat(motion): SVG to AE shape conversion, icon index and search`.

### Task 7: Licensed illustration library

**Files:** Create `lib/motion_library.py`; Modify `lib/motion_cli.py` (`motion-library`)

**Interfaces:**
- Produces:
  - `motion_library.ALLOWED: set[str]` (from `motion.json` `licenses_allowed`)
  - `library_dir() -> Path` (`motion.json` `library_dir`, else `ENV_DIR / "library/motion"`)
  - `load_packs(base: Path | None = None) -> list[dict]` — `{id, name, license, attribution, ok, problems: [...],
    items: {item_id: {"path": Path, "kind": "png" | "svg", "tags": [...]}}}`
  - `resolve(ref: str) -> dict` (`"pack/item"` → `{path, kind, license, attribution, pack}`; `ValueError` with the
    reason for unknown/unusable)
  - `svg_ok(svg_text: str) -> tuple[bool, str]` (solid fills only — no `linearGradient`, `radialGradient`, `pattern`,
    `mask`, `filter`, `clipPath`, `image`, `text`; ≤ 300 subpaths)

- [ ] **Step 1: Write failing tests**, class `TestLibrary` (temp library with packs): `CC0-1.0` pack ok; `CC-BY-4.0`
  with empty `attribution` → not ok, problem mentions attribution; `commercial` without `proof` → not ok; license
  `"free"` → not ok; a folder without `pack.json` → listed with a problem; `resolve` into a bad pack → `ValueError`;
  an SVG with `<linearGradient>` → `svg_ok` False; 301 subpaths → False; a PNG item has `kind == "png"`.
- [ ] **Step 2: Run** → FAIL. **Step 3: Implement.** **Step 4: Run** → PASS.
- [ ] **Step 5: Commit** `feat(motion): licensed illustration packs with license manifest`.

### Task 8: Motion script truth checks (`motion_script.py`)

**Files:** Create `lib/motion_script.py`

**Interfaces:**
- Produces:
  - `SCENE_TYPES: dict[str, dict]` — per type `required`, `speech`, `editorial`, `either` field lists (spec §3.5;
    `either` fields take a sibling `<field>_source` of `"speech" | "editorial"`)
  - `load_script(paths) -> dict` (`SystemExit` with the authoring hint when missing)
  - `check_fields(script: dict) -> list[str]` — errors: ids unique and `S\d+`, known type, required fields, `at` on
    every scene, the first `at == "@start"`, `@end` only on a last `outro`, list sizes 2–5 (`list_steps.items`,
    `timeline.points`), comparison points ≤ 3, beats referenced exist
  - `match_subsequence(shown: str, spoken: list[str], max_drop: float) -> dict` — `{ok, idx: list[int],
    dropped_ratio: float, added: list[str]}`, tokens compared after `plan.norm`
  - `digits_of(s: str) -> str` (Arabic-Indic → Western, digits only); `check_number(value: str, evidence: str) -> bool`
  - `check_editorial(text: str, window_digits: set[str]) -> list[str]` (quotes `« » " “ ”`, digit runs absent from the
    window)
  - `fill_placeholders(text: str, sheet: dict) -> tuple[str, list[str]]` (`{host}`, `{guest}` = name before ` — `,
    `{show}`; returns missing placeholders)

- [ ] **Step 1: Write failing tests**, class `TestMotionTruth`, with spoken tokens of
  `"انا قلت ان الشركه دي هتنجح"`:
  - `test_subsequence`: `"قلت ان الشركه دي هتنجح"` ok (`dropped_ratio == 1/6`); `"قلت الشركه هتنجح"` not ok at 0.4
    (0.5 dropped); `"قلت الشركه هتنجح جدا"` not ok, `added == ["جدا"]`; swapped order not ok; `"إن الشركة"` and
    `"قُلْت"` match (norm).
  - `test_fields`: a duplicate id, an unknown type, `kinetic_quote` without `text`, `list_steps` with 1 and with 6
    items, a first scene without `@start`, `@end` on a non-last scene → one error each, naming the scene.
  - `test_editorial`: `«كلام»` rejected; `"3 خطوات"` with window digits `{"5"}` rejected, with `{"3"}` ok;
    `fill_placeholders("مع {guest}", {"guest": "Sara — CEO"}) == ("مع Sara", [])`; `{host}` with no host → missing.
  - `test_numbers`: `check_number("٣", "عندنا 3 فروع")` True; `("1,000,000", "مليون عميل")` False;
    `("70%", "٧٠ في المية")` True.
- [ ] **Step 2: Run** → FAIL. **Step 3: Implement.** **Step 4: Run** → PASS.
- [ ] **Step 5: Commit** `feat(motion): motion script truth checks`.

### Task 9: Scene timing (`motion_timing.py`)

**Files:** Create `lib/motion_timing.py`

**Interfaces:**
- Consumes: `TimeMap(keep_ms)` (`timemap.py`), `seq_fps()`.
- Produces:
  - `anchor_scenes(scenes: list[dict], words: list[dict], cfg: dict) -> tuple[list[dict], list[str]]` — each
    `{id, start_ms, end_ms, word_idx}` in source ms; `at` tokens matched contiguously (norm) at or after the previous
    anchor; start = word start − `scene_lead_ms` (≥ 0); end = next start; `@start` → 0; an `@end` outro starts at the
    last word's end and lasts `outro_ms`
  - `scene_word_indexes(words, start_ms, end_ms, slack_ms) -> list[int]`
  - `cue_frames(word_idx: list[int], words: list[dict], tmap: TimeMap | None, fps: float) -> list[int]`
  - `hero_frame(last_cue: int, end_frame: int, next_transition: int, fps: float, reveal_ms: int) -> int` —
    `min(last_cue + ceil(reveal_ms·fps/1000) + 6, end_frame − next_transition − 1)`
  - `frame_scenes(anchored: list[dict], tmap: TimeMap | None, fps: float, cfg: dict,
    transitions: list[int]) -> tuple[list[dict], list[str]]` (adds `start_frame, end_frame`; error
    `"<id>: too short for its content"` when the hero frame would precede the last cue)

- [ ] **Step 1: Write failing tests**, class `TestMotionTiming` (words every 400 ms from `synthetic_episode_transcript`
  shapes; fps set through the client profile `sequence-settings.json` as `TestWindowMedia` does):
  - `test_anchors`: anchors at words 0 (`@start`), 10, 25 → starts `0, 4000−150, 10000−150`; ends chain; an `@end`
    outro starts at the last word's end and ends 2500 ms later.
  - `test_anchor_errors`: a missing phrase → error naming `S02`; `S03` anchored before `S02` → out-of-order error.
  - `test_cues_with_pauses`: `keep_ms [[0, 4000], [5000, 12000]]`, a word at 6000 ms → cue frame
    `== round(5.0 * fps)` for fps 24, 25, 29.97, 30.
  - `test_no_drift_long_window`: no pauses, 29.97 fps, a word at 179 600 ms → `round(179.6 * 29.97)` exactly; same at
    23.976.
  - `test_hero_and_too_short`: `hero_frame(100, 160, 12, 30, 180) == 111`; last cue 150 with end 155 → the
    too-short error.
- [ ] **Step 2: Run** → FAIL. **Step 3: Implement.** **Step 4: Run** → PASS.
- [ ] **Step 5: Commit** `feat(motion): scene anchors, cue frames and hero frames`.

### Task 10: Layout, fitting and contrast (`motion_layout.py`)

**Files:** Create `lib/motion_layout.py`; Modify `lib/ae_builder.py` only if `wrap_lines` gains a `glue` hook (keep its
behaviour for existing callers)

**Interfaces:**
- Produces:
  - `wrap(text: str, max_chars: int, max_lines: int) -> list[str]` — balanced lines; never splits a Latin run, a number
    and its unit (`% ٪ مليون الف ألف سنة سنين يوم ساعة دقيقة جنيه دولار k m`), or `ال`/`الـ` + a Latin token (glue
    with U+00A0, balance, restore)
  - `fit(text: str, font_file: str, box_w: int, size_range: tuple[int, int], max_lines: int) -> dict` — `{ok, size,
    lines, widths}`; sizes from max down to min in 4 px steps, measured with `hb_text.HBFontSpec` + `hb_text.measure`
  - `contrast(fg: tuple, bg: tuple) -> float` (WCAG relative luminance ratio)
  - `pick_text_color(bg: tuple, candidates: list[tuple[str, tuple]], size_px: int, cfg: dict) -> tuple[str, float]`
    (`ValueError` when none reaches the threshold)
  - `theme_colors(theme: str, brand) -> dict` (`{"bg", "text", "accent"}` RGB tuples from a `previews.Brand`)
  - `PRESETS: dict[str, dict]` — per scene type, per element `{"y": fraction of the safe height, "x": "center" |
    "start" | "end", "role": size key}`; `place(scene_type: str, element: str, fmt: dict, direction: str) -> tuple[int,
    int]` (`start` = the reading-start side: right in RTL)

- [ ] **Step 1: Write failing tests**, class `TestMotionLayout` (font: the `test_hb_font_sizes_independent` search;
  skip fit tests when none or `hb_text.AVAILABLE` is False):
  - `test_wrap_glue`: `wrap("الـ Isotretinoin مهم جدا", 10, 3)` keeps `الـ Isotretinoin` on one line;
    `"عندنا 3 مليون عميل"` keeps `3 مليون`; `"Vitamin D3 مهم"` keeps `Vitamin D3`; a 2-line result has no 1-word
    line when a 2/2 split exists.
  - `test_fit`: a longer text never gets a larger size than a shorter one; a 400-character text → `ok` False.
  - `test_contrast`: white on black `== 21.0`; `pick_text_color` on `#20ACAF` picks ink over white;
    `#DDDDDD` and `#666666` on `#A0A0A0` → `ValueError`.
  - `test_place_direction`: `place("list_steps", "number", fmt, "rtl")[0] > fmt["w"] / 2` and `< fmt["w"] / 2` in ltr.
- [ ] **Step 2: Run** → FAIL. **Step 3: Implement.** **Step 4: Run** → PASS.
- [ ] **Step 5: Commit** `feat(motion): text wrapping, HarfBuzz fitting, contrast, layout presets`.

### Task 11: Motion plan compiler, `motion-plan`, Gate 1

**Files:**
- Create: `lib/motion_plan.py`, `lib/motion_audio.py`
- Modify: `lib/motion_cli.py` (`motion-plan`), `engine/reel/cli.py` (`cmd_approve_plan`: motion projects require
  `motion-plan.json` and record `motion_plan.fingerprint(paths)`)

**Interfaces:**
- Consumes: Tasks 5–10 (`motion_config`, `motion_icons`, `motion_library`, `motion_script`, `motion_timing`,
  `motion_layout`), `sfx.synth`, `previews.Brand`, `ae_builder.brand_controls`/`fonts_map`.
- Produces:
  - `motion_plan.compile_motion(paths) -> dict` — `{ok, errors, warnings, approvals, editorial_lines, plan, md,
    fingerprint}`; writes `motion-plan.json`, `motion-plan.md`, `motion-validation.json`; status `ANALYZED` when ok
  - `motion_plan.fingerprint(paths) -> str` (sha1 over the script, `words.json`, `pauses.json`, the recipe,
    `motion.json` and `brand-tokens.json`)
  - `motion_audio.envelope(wav: Path, fps: float, n_frames: int) -> list[float]` (RMS per frame, 0–1)
  - `motion_audio.sfx_files(kinds: set[str], out_dir: Path) -> dict[str, Path]`
  - `motion-plan.json` top level: `reel_id, format, w, h, fps, dir (-1|1), direction, duration_frames, theme {bg,
    text, accent} (0–1 floats), fonts {role: {ps, file}}, brand (brand_controls), scenes [...], persistent {background,
    captions {cues [{text, start_frame, end_frame}]} | null, speaker_badge {segments [{name, start_frame, end_frame}]}
    | null, progress: bool, voice_pulse {values [...]} | null}, audio {dialogue, music {file, level_db,
    fade_out_frames} | null, sfx [{kind, file, frame}]}, assets [{ref, license, attribution}], editorial_lines,
    approvals, fingerprint`
  - scene: `{id, type, beat, start_frame, end_frame, hero_frame, transition_in {type, frames}, theme, elements [...]}`;
    element kinds `text {name, role, lines, size, color, x, y, rtl, reveal: word|line|none, tokens [{text,
    cue_frame}], emphasis [token index], cue_hash}`, `icon {name, shapes, size, x, y, mirror, draw_on_frame}`,
    `image {path, x, y, w, h}`, `counter {name, value, prefix, suffix, digits: western|arabic_indic, from_frame,
    to_frame}`; `cue_hash = sha1(json(cue frames))[:12]`

- [ ] **Step 1: Write failing tests**, class `TestMotionPlan` (fixture: the Task 5 motion project; `pauses.json` with
  `keep_ms`; brand tokens + `typography.json` pointing at the test font; skip when no font):
  - `test_compile_ok`: a 4-scene script (`kinetic_quote @start`, `stat_counter`, `list_steps`, `outro @end`) → `ok`;
    scenes contiguous (`end_frame` of one = `start_frame` of the next); `duration_frames` = outro end; every speech
    token has a `cue_frame`; `motion-plan.md` lists each scene with its time and marks the outro CTA as editorial;
    status `ANALYZED`.
  - `test_truth_errors_block`: an added word in `kinetic_quote.text`, an unknown icon (error lists 5 closest names), a
    `{guest}` placeholder with no guest in the sheet, an illustration from a pack whose license is `"free"`, and a
    200-character `title_card.title` (error contains `"too long"` and the scene id) → `ok` False with one error each.
  - `test_episode_changed_refused`: after selection, change the episode file's first bytes in a copy-based fixture
    (`source.json` fingerprint no longer matches) → `compile_motion` raises `SystemExit` with the
    `reels.window_stale` message.
  - `test_number_approval`: `stat_counter` value `"1000000"` with evidence `"مليون"` → `ok` True and one approval.
  - `test_dense_scene`: a `kinetic_quote` of 20 words under drama (`max_words_on_screen` 12) → error at > 18
    (1.5×), warning at 13–18 (second script with 14 words).
  - `test_recipe_warnings`: a `checklist`-like `list_steps` in `emotional` (avoided) → warning; with `recipe_note` →
    no warning and the note appears in the md.
  - `test_single_speaker_no_turns`: `00_inputs/speakers.json` absent → `speaker_badge is None`, captions present,
    `ok` True.
  - `test_ltr_mirror`: an English window (`direction: ltr`) → `dir == 1`, `list_steps` numbers left of centre;
    the same in rtl → right of centre; `arrow-right` icon mirrored only in rtl.
  - `test_cc_by_asset_listed`: an illustration from a CC-BY pack → `assets` entry with its attribution.
  - `test_approve_plan_motion`: `reel approve-plan --by editor` on the motion project writes `plan-approval.json` with
    `plan_fingerprint == fingerprint(paths)`; editing the script changes the fingerprint.
- [ ] **Step 2: Run** → FAIL. **Step 3: Implement** `compile_motion` as the spec §4.1 pipeline: `window_stale` check →
  load → `check_fields`
  → anchors → speech/editorial/number/name checks → recipe checks → frames → layout and contrast → captions (from
  `02_transcription/captions-short-seq.srt` when pauses are removed, else `captions-short.srt`, minus ranges of
  scenes that show speech) → assets → audio (music only under `data/Music`) → outputs. **Step 4: Run** → PASS.
- [ ] **Step 5: Commit** `feat(motion): motion plan compiler, motion-plan.md, Gate 1 for motion`.

### Task 12: Animatic

**Files:** Create `lib/motion_animatic.py`; Modify `lib/motion_audio.py` (`mix`), `lib/motion_cli.py`
(`motion-animatic`)

**Interfaces:**
- Produces:
  - `motion_audio.mix(plan: dict, root: Path, out: Path) -> Path` (dialogue + music at `level_db` with its fade-out +
    each SFX delayed to its frame; 48 kHz WAV)
  - `motion_animatic.scene_still(scene: dict, plan: dict, brand, width: int = 540) -> PIL.Image.Image` (hero state:
    theme background, texts via `Brand.font`, flattened icons, images, badge and caption band)
  - `motion_animatic.render(paths, width: int = 540) -> dict` — `{stills, sheet, mp4, duration_s}`; files in
    `08_quality_control/animatic/` (`S01.png`…, `_storyboard.jpg`, `<ID>_animatic.mp4` with 6-frame crossfades and a
    label strip "layout approximation — AE frames are the truth")

- [ ] **Step 1: Write failing tests**, class `TestAnimatic` (the Task 11 fixture, compiled): one still per scene;
  `_storyboard.jpg` exists; the MP4 duration = `duration_frames / fps` ± 1 frame and it has an audio stream; the
  kinetic scene's still has text pixels (non-background pixels in the text box > 1 %).
- [ ] **Step 2: Run** → FAIL. **Step 3: Implement.** **Step 4: Run** → PASS.
- [ ] **Step 5: Commit** `feat(motion): storyboard and animatic for Gate 1`.

### Task 13: ES3 motion library core, job data, fallback script

**Files:**
- Modify: `templates/after_effects/nh_motion_lib.jsx`, `templates/after_effects/nh_ae_bridge.jsx` (action
  `build_motion`)
- Create: `lib/motion_build.py` (job and script generation only in this task)

**Interfaces:**
- Consumes: `motion-plan.json` (Task 11), `ae-capabilities.json` (Task 2).
- Produces:
  - `motion_build.aep_path(paths) -> Path` (`04_after_effects/project/<ID>_<PREFIX>_MOTION.aep`)
  - `motion_build.job_data(paths, fallback_font: str | None = None) -> dict` (`plan`, `caps`, `aep_path`,
    `audio_paths`, `generated`)
  - `motion_build.write_job(paths, **kw) -> Path` (`04_after_effects/data/motion-job.json`, `ensure_ascii=True`)
  - `motion_build.write_fallback_script(paths, **kw) -> Path` (`04_after_effects/scripts/build_<ID>_motion.jsx`:
    `var NH_JOB = <json>;` + `nh_ae_lib.jsx` + `nh_motion_lib.jsx` + `NHM.build(NH_JOB);`)
  - JSX: `NHM.build(job) -> report` — sets `NH.W/H/FPS` from the plan; creates `NH_BRAND/BRAND_CONTROLS`,
    `NH_SCENES`, `NH_PERSISTENT`, `NH_AUDIO`, `NH_ASSETS`, `MAIN_<ID>`; places scene comps at their frames with
    `transition_in`; adds persistent layers and audio; saves `job.aep_path`; returns `{made: [...], failed: [{scene,
    error, line}], saved: path}`
  - JSX helpers: `NHM.t(comp, frame)` (= `frame * comp.frameDuration`), `NHM.textEl(comp, el, caps)` (point text,
    lines joined by `"\r"`, `fontObject` when `caps.fontobject`, composer UNIVERSAL, direction per
    `caps.rtl_direction`, reveal animator + expression selector per caps — logical word order, else per-line layers,
    else per-word layers chained by `sourceRectAtTime`; emphasis animator; stores `el.cue_hash` in the layer comment),
    `NHM.transition(layer, spec, dir)`, `NHM.S.kinetic_quote`, `NHM.S.title_card`, `NHM.P.background`,
    `NHM.P.captions`, `NHM.P.speaker_badge`, `NHM.P.progress`, `NHM.P.voice_pulse` (Slider keys via
    `setValuesAtTimes`)
  - Bridge action `build_motion` (`data.job`): refuses `{ok: false, reason: "dirty"}` when `app.project.dirty` and
    the open project path is not `job.aep_path`, or is that path with unsaved changes; else `app.newProject()`,
    `NHM.build(job)`.

- [ ] **Step 1: Write failing tests**, class `TestMotionJSX`:
  - `test_lib_syntax`: `nh_motion_lib.jsx` and `nh_ae_bridge.jsx` pass `assert_js_syntax`.
  - `test_fallback_script`: generated from the Task 11 fixture → passes `assert_js_syntax`, contains `NHM.build(`.
  - `test_job_ascii_paths`: with the dialogue at `D:/0 Work/عميل/حلقة 1.wav`, the job file is pure ASCII and
    `json.loads` returns that path unchanged.
  - `test_lib_uses_frame_duration`: the `NHM` code contains `frameDuration` and no `/ NH.FPS` or `/NH.FPS`.
  - `test_lib_defines_core`: the source defines `NHM.S.kinetic_quote`, `NHM.S.title_card` and the five `NHM.P.*`.
- [ ] **Step 2: Run** → FAIL. **Step 3: Implement.** **Step 4: Run** → PASS.
- [ ] **Step 5: Commit** `feat(motion): AE motion library core, job data and fallback script`.

### Task 14: ES3 scene types (the other ten)

**Files:** Modify `templates/after_effects/nh_motion_lib.jsx`

**Interfaces:**
- Produces: `NHM.S.stat_counter` (Source Text expression counting `from_frame → to_frame`, digit mapping per
  `digits`), `NHM.S.icon_point` (shape groups from `shapes`, brand-linked stroke, round caps/joins, Trim Paths 0 → 100
  from `draw_on_frame`), `NHM.S.list_steps`, `NHM.S.comparison`, `NHM.S.timeline` (line drawn in `job.plan.dir`),
  `NHM.S.quote_card` (line reveal), `NHM.S.context_card`, `NHM.S.person_card`, `NHM.S.illustration_scene`,
  `NHM.S.outro`. Every side/direction comes from `plan.dir`; element positions come from the plan.

- [ ] **Step 1: Write failing tests**, class `TestMotionScenesJSX`: every key of `motion_script.SCENE_TYPES` has
  `NHM.S.<type> = function` in the source; the source contains `"ADBE Vector Filter - Trim"` and
  `"ADBE Vector Stroke Line Cap"`; the counter code sets `sourceText.expression`; the timeline and list code read
  `plan.dir` (regex); the file passes `assert_js_syntax`.
- [ ] **Step 2: Run** → FAIL. **Step 3: Implement.** **Step 4: Run** → PASS.
- [ ] **Step 5: Commit** `feat(motion): AE scene types — counters, icons, steps, comparison, timeline, cards, outro`.

### Task 15: Build through the bridge, read-back, protection

**Files:**
- Create: `lib/motion_readback.py`
- Modify: `lib/motion_build.py` (`preconditions`, `build`, `script_only`, `run_script`, `editor_changed`),
  `templates/after_effects/nh_ae_bridge.jsx` (action `readback`), `lib/motion_cli.py` (`motion-build`)

**Interfaces:**
- Consumes: `ae_bridge.submit` (Task 1), `ae_probe.verdict_ok` (Task 2), `motion_plan.fingerprint` (Task 11),
  `write_job`/`write_fallback_script` (Task 13), `adobe_run.run_after_effects`.
- Produces:
  - `motion_build.preconditions(paths, allow_fallback_font: bool = False) -> tuple[list[str], dict]` — problems and
    context (`ping`, `fonts`): After Effects installed (`plat.newest_app("after_effects")`, else "use --script-only"),
    fresh `motion-plan.json`, approval fingerprint == current, `verdict_ok(ae_version)`, every planned PostScript name
    found and not substituted (unless `allow_fallback_font`), bridge alive and not busy
  - `motion_build.editor_changed(paths) -> bool` (SHA-1 of the `.aep` ≠ `motion-build-result.json["aep_sha1"]`)
  - `motion_build.build(paths, replace_edited: bool = False, allow_fallback_font: bool = False,
    timeout: int = 900) -> dict` — `{status: PROJECT_ASSEMBLED | REFUSED | FAILED, reasons, report, readback,
    comparison, aep, aep_sha1}`; writes `motion-build-result.json`; status `PROJECT_ASSEMBLED` only when the save time
    is fresh and the comparison passed; `--replace-edited` first copies the `.aep` to
    `project/backups/<name>.edited-<YYYYmmdd-HHMMSS>.aep`
  - `motion_build.script_only(paths) -> dict` (`status: SCRIPT_ONLY`); `run_script(paths, timeout: int = 900) ->
    dict` (`status: BUILT_UNVERIFIED | FAILED`, `readback: None`)
  - `motion_readback.compare(plan: dict, rb: dict, fmt: dict, caps: dict) -> dict` — `{ok, failures, warnings}`:
    every scene comp present with planned frames; text strings equal after `plan.norm`; font PostScript names as
    planned and not substitutes; composer UNIVERSAL on rtl text; direction as `caps.rtl_direction`; every text box
    inside the safe area and not overlapping another text box of its scene or the caption band; cue hashes equal;
    `missing_or_substituted` empty
  - Bridge `readback` → per scene comp `{name, in_frame, out_frame, layers: [{name, kind, in, out, text, font_ps,
    substitute, composer, direction, rect [l, t, w, h] at the hero frame, comment}]}` + `missing_or_substituted`
  - CLI `motion-build [--replace-edited] [--allow-fallback-font] [--script-only] [--run-script]`

- [ ] **Step 1: Write failing tests**, class `TestMotionBuild` (`ae_bridge.submit` patched with canned responses; a
  fake save writes bytes to the `.aep` path):
  - `test_refusals`: no approval; stale approval (script edited after approving); no probe verdict; a missing font →
    each `REFUSED` with a reason naming it; with `allow_fallback_font` the job uses `fallback_fonts` and the result
    records `fallback_font`.
  - `test_dirty_session`: `ping` → `dirty: true` with another project path → `REFUSED` (reason mentions saving or
    closing in AE); `dirty: false` → proceeds.
  - `test_rebuild_protection`: after a successful fake build, change the `.aep` bytes → `REFUSED` ("editor changed");
    with `replace_edited` → a file in `project/backups/` with the old bytes, then `PROJECT_ASSEMBLED`.
  - `test_compare`: a read-back built from the plan passes; then one failure each for a substituted font, a changed
    string, a box with `top < safe.top`, a missing scene comp, a cue-hash mismatch, a non-empty
    `missing_or_substituted`.
  - `test_script_only`: `script_only` → `SCRIPT_ONLY` and a script passing `assert_js_syntax`; the project status is
    not `PROJECT_ASSEMBLED`.
- [ ] **Step 2: Run** → FAIL. **Step 3: Implement.** **Step 4: Run** → PASS.
- [ ] **Step 5: Commit** `feat(motion): AE build through the bridge with read-back and rebuild protection`.

### Task 16: Render, MP4, cover, QC frames

**Files:** Create `lib/motion_render.py`; Modify `lib/motion_cli.py` (`motion-render --scenes`, `motion-frames`)

**Interfaces:**
- Consumes: `ae_render.render`/`extract_frames` (Task 2), `motion_audio.mix` (Task 12), `media.probe`.
- Produces:
  - `motion_render.render(paths, scenes: list[str] | None = None, timeout: int = 3600) -> dict` — `{status: RENDERED |
    FAILED, main, pieces, mp4, cover, probe, warnings}`; MAIN → `render/<ID>_MAIN.mov`; `--scenes` → frame ranges into
    `render/pieces/<ID>_<scene>.mov`; MP4 via ffmpeg `-c:v libx264 -crf 18 -pix_fmt yuv420p -c:a aac -b:a 192k
    -movflags +faststart`; cover = the first scene's hero frame as JPG; a render without audio gets `mix()` muxed and
    a warning; checks size, fps, duration (plan ± 1 frame) and loudness (−14 LUFS ± 1 → warning otherwise)
  - `motion_render.frame_points(plan: dict) -> list[dict]` — `{frame, scene, kind: hero | reveal_mid | transition_mid
    | caption, expect: {lines, emphasis, icon, revealed_tokens}}`
  - `motion_render.frames(paths) -> dict` — newest render (pieces win for their ranges) → `ae_frames/run-<stamp>/`
    `F###_<scene>_<kind>.png`, `frames.json`, labelled `_sheet.jpg`

- [ ] **Step 1: Write failing tests**, class `TestMotionRender` (compiled Task 11 fixture; a fake MAIN made with ffmpeg
  testsrc at the plan's size/fps/duration with audio; `ae_render.render` patched to "render" that file):
  - `test_frame_points`: one `hero` per scene; one `reveal_mid` per kinetic/list/timeline scene with
    `revealed_tokens` = cues ≤ that frame; `transition_mid` only where `transition_in.frames > 0`; 3 `caption` points
    when captions exist.
  - `test_render_ok`: `RENDERED`, MP4 and cover exist, probe matches.
  - `test_render_duration_mismatch`: fake MAIN 1 s short → `FAILED` with a duration reason.
  - `test_render_no_audio`: fake MAIN without audio → MP4 has an audio stream and a warning.
  - `test_frames`: PNG count == `len(frame_points)`, `_sheet.jpg` exists, `frames.json` carries the expectations.
- [ ] **Step 2: Run** → FAIL. **Step 3: Implement.** **Step 4: Run** → PASS.
- [ ] **Step 5: Commit** `feat(motion): aerender master, MP4, cover and QC frames`.

### Task 17: Motion QC, verify, `next`, handoff, publish attribution

**Files:**
- Create: `lib/motion_qc.py`
- Modify: `engine/reel/cli.py` (`cmd_qc`, `cmd_verify --record`, `cmd_next`, `cmd_handoff` dispatch on
  `is_motion`), `lib/handoff.py` (`motion_readme(paths) -> Path`), `lib/publish.py` (CC-BY check for motion reels)

**Interfaces:**
- Consumes: everything above.
- Produces:
  - `motion_qc.run(paths) -> dict` — `{ok, checks: [{id, result: PASS|FAIL|WARN, detail}], failed: [ids]}` with ids
    `plan_valid, approval_current, aep_fresh, readback, render, audio_sync, cut_proof, visual_verified, licenses`
    (FAIL blocks) and `approvals_listed` (WARN); writes `08_quality_control/qc-results.json`; status `QC_PASSED` /
    `BLOCKED` as `cmd_qc` does today
  - `motion_qc.audio_sync(render: Path, dialogue: Path, fps: float) -> dict` (`corr`, `offset_frames`; pass when
    `corr ≥ 0.9` and `|offset| ≤ 1`)
  - `motion_qc.motion_next(paths) -> dict` (same shape as `cmd_next`: `status, next, remaining, stale`; steps and
    stale rules from spec §4.11)
  - `verify --record` for motion: the sheet is the newest `ae_frames/run-*/_sheet.jpg`; refused when older than the
    newest file in `04_after_effects/render/`
  - `publish.check`: a reel id ending in `_MO` whose `motion-plan.json` lists CC-BY assets needs each attribution
    string in its Instagram caption, TikTok caption or Shorts description (error otherwise)

- [ ] **Step 1: Message the other session** about `cli.py`, `qc.py`, `verify.py`, `handoff.py`, `publish.py`.
- [ ] **Step 2: Write failing tests**, class `TestMotionQC` (a complete fake motion project: plan, approval, build
  result with fresh `aep_sha1` and passing comparison, render files, cut proof, a recorded verification, frames run):
  - `test_complete_passes`: `ok` True, every FAIL-class check PASS.
  - `test_each_check_fails`: remove/stale one piece of evidence at a time (approval fingerprint, `.aep` touched after
    the build, comparison failed, fallback build without read-back, render older than the `.aep`, audio offset of
    3 frames, missing cut proof, verification older than the frames, an asset with license `"free"`) → that id FAILs.
  - `test_next_order_and_stale`: an empty motion project → `next == "audio-clean"`; with every file present and the
    script newer than the plan → `stale` starts with `motion-plan`.
  - `test_verify_record_motion`: `reel verify --record pass --notes x` uses the frames sheet; with a newer render it
    is refused.
  - `test_handoff_motion`: README mentions the `.aep` path, `MAIN_`, the fonts and any attribution.
  - `test_publish_cc_by`: a motion reel JSON without the attribution → error naming it; with it → ok.
- [ ] **Step 3: Run** → FAIL. **Step 4: Implement.** **Step 5: Run** motion tests + full suite → PASS.
- [ ] **Step 6: Commit** `feat(motion): motion QC, verify, next, handoff and publish attribution`.

### Task 18: Plugin layer — agents, skills, hooks, evals

**Files:**
- Create: `agents/motion-director.md`, `agents/ae-builder.md`, `skills/motion/SKILL.md`,
  `skills/motion-craft/references/{motion-scenes.md, motion-beats.md, ae-motion.md}`,
  `evals/motion-from-audio/{prompt.md, graders/criteria.md}`, `evals/motion-qc-evidence/{prompt.md,
  graders/criteria.md}`
- Modify: agents `episode-analyst.md` (`motion_fit`, `motion_why`, topic `type`), `qc-reviewer.md`,
  `frame-inspector.md` (motion checklist + `frames.json`), `publish-writer.md` (motion reels, attributions),
  `setup-doctor.md` (AE bridge); skills `podcast`, `adobe-extras`, `help`, `status`, `start`, `setup`, `qc-craft`,
  `episode-craft`, `publish-craft`, `motion-craft/SKILL.md`; `hooks/guard.py`; `hooks/session_context.py`;
  `lib/reels.py` (`reels-plan.md` shows a `motion` flag for `motion_fit`)

**Interfaces:**
- guard: `QC_FORBIDDEN` gains `motion-plan`, `motion-build`, `motion-render`, `motion-animatic`; subagents are blocked
  from `ae-probe --record`; `protected()` treats AE preference files (`Adobe After Effects * Prefs*.txt`, any path
  under `Adobe/After Effects/<version>/`) as unwritable for every tool; `motion-*`, `ae-status` and `ae-probe` are not
  in `EXTRAS`.
- `motion-director`: model `opus`, tools `Read, Write, Edit, Grep, Bash`; `ae-builder`: model `sonnet`, tools
  `Read, Bash`.

- [ ] **Step 1: Write failing tests**, class `TestMotionPluginLayer`:
  - the two new agents have `name`, `description`, `tools`, `model` (`motion-director` → `opus`); `ae-builder` has no
    `Write`/`Edit`.
  - `skills/motion/SKILL.md` mentions `--as motion`, `Gate 1`, `animatic`, `ae-probe` and `verify --record`.
  - guard: `run_guard("reel ae-probe --record ok --word-order logical", agent="ae-builder") == 2`;
    `run_guard("reel motion-build --video-id X", agent="qc-reviewer") == 2`; `run_guard("reel motion-build --video-id
    X") == 0` (no `--extras`); a `Write` tool payload to `C:/Users/x/AppData/Roaming/Adobe/After Effects/26.0/Adobe
    After Effects 26.0 Prefs.txt` → 2.
  - session context for a client with `data/Episodes` mentions `motion`.
  - `reels-plan.md` shows `motion` for a candidate with `motion_fit: true`.
- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Write the Markdown** in the existing style (report format, when to invoke, non-negotiables). The
  motion playbook: Gate 0 `--as motion` → audio-clean → motion-director (script → `motion-plan` until no errors →
  animatic, views the storyboard) → **Gate 1** with `motion-plan.md` + the animatic (editorial lines and approvals
  called out) → `ae-status`/`ae-probe` → ae-builder `motion-build` → `motion-render` → `motion-frames` → qc-reviewer
  (frame-inspectors) → lead views the sheet, `verify --record` → `qc` → handoff → publish-writer captions →
  `publish-check`. Implement the guard and session-context changes.
- [ ] **Step 4: Run** motion tests + full suite (incl. `test_plugin.py` frontmatter checks) → PASS.
- [ ] **Step 5: Commit** `feat(motion): agents, skills, guard rules and evals for motion mode`.

### Task 19: Docs, version 2.2.0, package

**Files:** Modify `whynot-cut/README.md`, `whynot-cut/CHANGELOG.md`, `whynot-cut/.claude-plugin/plugin.json` (version
`2.2.0`; description adds motion videos from episode audio as After Effects projects; keywords `motion`,
`after-effects`, `animation`), `.claude-plugin/marketplace.json` (version), `package.py` (ship `templates/motion/`, skip
`tools/`); Create `whynot-cut/THIRD_PARTY_NOTICES.md` (Lucide, ISC, version, copyright lines from its LICENSE)

- [ ] **Step 1:** Edit the docs: a "Motion mode" section (what it makes, Gate 0 `--as motion`, the stages, outputs
  tree, the AE needs: bridge + restart, fonts installed, the Type preference note), the new commands table, an Arabic
  quick-start paragraph, CHANGELOG 2.2.0.
- [ ] **Step 2:** `"$PY" package.py` → JSON with `corrupt_member: null`, `has_manifest: true`; the zip contains
  `templates/motion/icons/lucide/LICENSE` and `THIRD_PARTY_NOTICES.md` and no `tools/` or `docs/`.
- [ ] **Step 3:** Full suite → PASS; `claude plugin validate whynot-cut --strict` → no errors (if the CLI is available).
- [ ] **Step 4: Commit** `docs(motion): WhyNot Cut 2.2.0 motion mode`.

### Task 20: Live verification on this PC

**Files:** test client `whynot-test/PODCAST-TEST/` (existing; copies only), plus an audio-only copy of its episode
made by a Python fixture script into a new test client `whynot-test/PODCAST-AUDIO-TEST/`.

- [ ] **Step 1:** `reel reels-select --episode <EP> --pick R01 --as motion --by delegated --note "<the user's own
  delegation words>"` → `<EP>_R01_MO`.
- [ ] **Step 2:** `audio-clean` (cut proof ok) → author `motion-script.json` as the motion-director would (≥ 6 scenes,
  ≥ 4 scene types, one `stat_counter` or `list_steps`) → `motion-plan` until `ok` → `motion-animatic` → VIEW the
  storyboard and watch the animatic.
- [ ] **Step 3:** Gate 1: show `motion-plan.md` + the animatic to the user; record `approve-plan` only with their
  words (or a standing delegation they gave in chat, quoted in `--note`).
- [ ] **Step 4:** `ae-status` → `motion-build` → `PROJECT_ASSEMBLED` with a passing comparison → `motion-render` →
  `motion-frames` → VIEW every frame (Arabic joined, RTL order, mid-reveal frames show the first words, no clipping)
  → `verify --record pass|fail` → `qc` → ok → `handoff`.
- [ ] **Step 5:** Publish: author `publish/reels/<EP>_R01_MO.json` → `publish-check` ok.
- [ ] **Step 6:** Audio-only: in `PODCAST-AUDIO-TEST`, `episode-prep` → `reels-preview` (audio card) → `reels-select
  --as motion` → `motion-plan` + animatic (AE build optional).
- [ ] **Step 7:** Report Verified / Not verified / Needs you with the evidence paths; update the memory file
  `whynot-cut-plugin.md` (motion mode, probe capabilities, live results); leave a hand-over note in the shared notes
  folder.
