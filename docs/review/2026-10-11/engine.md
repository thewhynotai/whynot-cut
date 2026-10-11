# WhyNot Cut — Python engine review

Reviewer: Claude (read-only review; nothing in the repos was edited, committed, checked out or stashed).
Date: 2026-10-11. Platform used: Windows 11, engine venv Python 3.13.2 (`C:\Users\LOQ\.whynot-cut\venv`).

## 0. Snapshot, method, severity

**Main moved twice during the review.** I started on `39026fb` (v2.2.0). At 15:23:06 `fix/motion-minors` was
fast-forwarded into main (`920b9ff`, v2.2.1). At 15:30:50 `fix/r4-b` was fast-forwarded too (it contains r4-a), so main
is now **`cb0539f`** (v2.2.1 + round-4 G62/G63/G64/G67-docs/G68). **All file:line references below are for `cb0539f`.**
Everything I had read on 2.2.0 was re-checked against the 2.2.1 and r4-b diffs, and findings those merges fixed were dropped
or moved to "fixed" (for example the FreeType non-ASCII path in `hb_text._face` and the previews' first-font-file
fallback, G62).

**Method.** I read the whole engine: `cli.py` and the 40+ `lib/*.py` modules, `setup/`, `bin/`, the CEP bridge JS/manifest,
and `hooks/hooks.json`, `run_python.sh` and the top of `guard.py`. I ran the full test suite three times, ran small
in-memory experiments with the engine venv (they wrote no files: `python -I`, `slug()`/`main_footage()`, `discover.classify()`,
bidi runs), and inspected the venv layout. Two read-only sub-audits fed this report: CLI surface against docs and tests,
and gaps/branches/specs. I verified their key claims.

**Severity.**
- **Critical:** breaks a core flow or risks wrong deliverables for the target clients. Fix before the next field test.
- **Important:** real defect or risk with a plausible trigger. Fix soon.
- **Minor:** hygiene, consistency, or a low-probability edge.

### Top findings at a glance

| ID | Sev | Finding | Where |
|---|---|---|---|
| CR-1 | Critical | Clip IDs from `reel inbox` are rejected by every per-clip command when a client has ≥2 raw clips with spaces or punctuation in their names. Arabic-named clips all collapse to the same ID (`VIDEO`, or just their ASCII digits). | onboard.py:180, cli.py:74, cli.py:911, common.py:222-224 |
| CR-2 | Critical (macOS, needs a Mac to confirm) | `bin/reel` has never had the executable bit in git (`100644`), and no file in the repo is `100755`. A git-installed plugin on macOS cannot run `reel`. | `git ls-files -s whynot-cut/bin/reel` |
| IM-1 | Important | The engine venv on this machine is not self-contained. Most packages load from the Windows USER site-packages (the real root cause of G67). Version drift is not detected anywhere. | setup_env.py:53-55, 72-81; venv `pyvenv.cfg` |
| IM-2 | Important | `reel setup` never (re)installs packages, but `doctor` tells Claude to run it to "re-install the pinned packages". There is no update path after a requirements change. | cli.py:633-645, onboard.py:63, bin/reel:18-37, bin/reel.cmd:15-20 |
| IM-3 | Important | The Gate 1 approval fingerprint ignores everything before `"events"` in timeline-spec.json (camera moves, framing 9:16↔4:5, base scale, main_footage, duration). The plan can change after approval without re-approval. | plan.py:608-610 |
| IM-4 | Important | Bridge jobs that time out are never cancelled or expired. The panel runs them later (possibly hours later, on the next Premiere start). Data and result files are never cleaned up. | cep_queue.py:37-70, bridge.js:74-112 |
| IM-5 | Important | No build lock. Queue wait counts against the caller's timeout. The `busy` flag is unreliable because two CEP copies run. No runtime version handshake. | cep_queue.py, ppro_build.py:202-271, bridge.js:48-67 |
| IM-6 | Important | G69: "Media pending" frames count as exported frames. | ppro_build.py:274-329 |
| IM-7 | Important | Tracebacks instead of guidance for common authoring mistakes (missing `start`, a UTF-8 BOM in JSON, no discovery yet). Exit code is 0 for failed `plan`, `qc`, `ppro-build` and `preview-video`. | cli.py:784-915, common.py:177-182, plan.py:198,223 |
| IM-8 | Important | Discovery classifies by substring over the whole path. Raw clips named "Refractive…", "Reflux…" or "Preface…" become *reference edits*, and "Stock…" becomes *B-roll*. They silently drop out of inbox and autopilot. | discover.py:12-20, 37 |
| IM-9 | Important | The clip handoff README still describes the 1.x XML/After Effects workflow and ignores the native `ppro-build` result. | handoff.py:32-155 |
| IM-10 | Important | The client SFX library is never used: `06_audio/sfx-map.json` is documented but never read. Unknown sound kinds pass `plan` and then crash `reel sfx`. | cli.py:336-346, plan.py:283-288, sfx.py:36-38 |
| IM-11 | Important | Windows concurrency: a fixed `<name>.tmp` plus `os.replace`, with no locks. Parallel agents race on shared JSON (inventory, probe cache, status). | common.py:185-193, onboard.py:206-231 |
| IM-12 | Important (macOS) | The motion fallback font `GeezaPro-Bold` is in a `.ttc`, but lookups only scan `.ttf/.otf`. `_system_font()` misses macOS `Supplemental`. | motion_layout.py:157-158, motion_plan.py:27,38-45, client_db.py:36, motion.json:29 |
| IM-13 | Important | Whisper uses faster-whisper's default of **4 CPU threads** everywhere. There is no batched inference, and no Apple-Silicon (MLX/CoreML) path. | transcribe.py:54-78, episode.py:387-409 |
| IM-14 | Important | Long single clips (not podcast episodes) are transcribed in one pass, with no VAD and no checkpoints. Audio-clean, cut-proof and preview-video also scale badly past about 20 minutes. | transcribe.py:86-135, audio_clean.py:28-42, 311-409, preview_video.py:226-279 |
| IM-15 | Important | Adobe app discovery only looks in `C:\Program Files*\Adobe` and `/Applications`, with no override. | plat.py:99-140 |
| IM-16 | Important | The 1080×1920 frame size is hard-coded in the stills, verify, the preview and the Premiere settings and checks, while other code honours sequence-settings.json. | previews.py:19, verify.py:23, preview_video.py:171, ppro_build.py:16-20, 250 |
| IM-17 | Important | The client-source guard fails open: `run_python.sh` exits 0 when no Python is on PATH. Some role rules are prose only. | hooks/run_python.sh:5-11, guard.py:267-293 |

The Minor findings (MI-1 to MI-24) are in the sections below.

---

## 1. CLI surface

61 subcommands: 42 core (`cli.py`), 10 podcast (`lib/podcast_cli.py`), 9 motion (`lib/motion_cli.py`). Global options
`--root/--video-id/--profile/--episode` are accepted before or after the subcommand (cli.py:792-808). Gate sets:
`EXTRAS` (cli.py:626, duplicated in guard.py:27), `NO_ROOT` (627), `NO_ID` (629), `OPTIONAL_ID` (630). Two in-handler gates:
`refuse_stale_window` (cli.py:109) and `require_plan_approval` (cli.py:349).

### 1.1 Command table (name → handler/module → purpose → test status)

Test status: **CLI** = invoked as a subprocess in tests; **lib** = only the library function is tested; **none** = no test.

| Command | Module(s) | Purpose | Tests |
|---|---|---|---|
| discover | discover.run_discovery | Inventory and classify inputs, audit environment | lib |
| client-db | client_db.build | Brand tokens, typography, asset manifest | lib |
| preflight | media.preflight | Probe footage, reframe/shot analysis, issues | CLI (stale refusal only) |
| transcribe | transcribe.transcribe / reels.slice_transcript | Whisper to words/SRT; podcast reels re-slice the episode instead | CLI (reel path) |
| transcript-correct | transcribe.apply_corrections | Apply transcript-corrections.json | lib |
| transcript-verify | transcribe.words_fingerprint | Record that the editor verified by ear | CLI |
| transcript-relisten | transcribe.relisten | Re-decode flagged words 3 ways | **none** |
| range | cli.cmd_range, media.snap_range_points | Window of a longer raw file | lib (CLI time parsing untested) |
| ref-analyze | ref_analysis.analyze_all, ref_style | Measure reference edits (cached), apply the client style | lib |
| ref-style | ref_style | Show / `--record` / `--apply` the client style | CLI |
| plan | plan.compile_plan | Validate and compile edit-decisions into timeline-spec | CLI (missing-files path) + lib |
| previews | previews.render_all | Brand stills, QC composites, contact sheet | lib (+ stale refusal) |
| sfx | sfx.synth_needed | Synthesise needed SFX | lib |
| approve-plan | plan.plan_fingerprint / motion_plan.fingerprint | Gate 1 record | CLI |
| verify | verify / motion_qc.record_visual | Build the check sheet / record a verdict | CLI (motion) + lib |
| ppro-install | ppro_bridge.install | Install the CEP bundle (Premiere and After Effects) | lib |
| ppro-status | ppro_bridge.status + ping | Bridge heartbeat and ping | **none** |
| ppro-probe | ppro_bridge.submit("probe") | Dump open sequences' settings | **none**, undocumented |
| ppro-build | ppro_build.build | Native .prproj via the bridge | CLI (refusals) + lib with mocked bridge |
| ppro-frames | ppro_build.export_frames | Premiere-rendered frames + sheet | lib (mocked) |
| mogrt-build | mogrt_builder.build | .mogrt templates (extra) | **none** |
| audio-clean | audio_clean.clean/detect_pauses/verify_cuts | Denoise, pauses, cut proof | CLI (stale refusal); detect_pauses/verify_cuts **untested** |
| ae-script / ae-build / ae-render | ae_builder | Clip graphics in After Effects (extras) | lib / refusals / **none** (ae-render) |
| ps-script / ps-build | ps_builder | Layered PSDs (extra) | **none** / refusal only |
| premiere | premiere_xml.build_xml | FCP7 XML fallback (no approval gate) | CLI refusal + lib |
| qc | qc.run_qc / motion_qc.run | Mandatory checks → QC_PASSED/BLOCKED | lib |
| handoff | handoff.build / motion_readme | Editor package | lib |
| status | common.load_status | Raw status JSON | **none**, undocumented |
| next | cli.cmd_next / motion_qc.motion_next | Next step + stale list | CLI |
| setup | ppro_bridge.install + onboard.doctor | "Idempotent machine setup" (see IM-2) | **none** |
| profile / client-init | common / profile copy | Active profile / create reel-profile | CLI |
| doctor | onboard.doctor | Environment report | **none** |
| scaffold / inbox | onboard | New client skeleton / clip + episode states | lib |
| preview-video | preview_video.render | 540×960 proxy MP4 of the plan | lib (+ stale refusal) |
| settings | settings | Show / write preferences | CLI |
| model-download | faster_whisper.download_model | Fetch Whisper model | **none** |
| gpu-enable | plat.install_cuda_redist / pip | cuBLAS for CUDA Whisper | **none** |
| episodes / episode-prep | episode | List episodes / probe + intake sheet | CLI |
| episode-transcribe | episode.transcribe_episode | Chunked, resumable Whisper | lib (fake runner) |
| reels-plan / reels-preview | reels | Validate the reels plan / candidate MP4s | CLI (errors) / lib |
| reels-select | reels.select | Gate 0 → reel projects (video or motion) | lib only, so the `--resync` parse break is not caught |
| music | recipes.music_library | Licensed tracks + moods | lib |
| publish-check / publish-thumbnail | publish | Validate copy / thumbnails | lib |
| episode-next | episode.episode_next | Episode resumable state | lib |
| ae-status / ae-probe | ae_bridge / ae_probe | After Effects bridge state / Arabic capability probe | **none** / record only |
| motion-icons / motion-library | motion_icons / motion_library | Lucide search / illustration packs | lib |
| motion-plan / motion-animatic | motion_plan / motion_animatic | Compile the motion script / storyboard | lib |
| motion-build / motion-render / motion-frames | motion_build / motion_render | .aep via bridge + read-back / aerender / QC frames | lib with fake AE |

**12 commands have no test:** transcript-relisten, ppro-status, ppro-probe, mogrt-build, ae-render, ps-script, status,
setup, doctor, model-download, gpu-enable, ae-status. The `bin/reel` and `bin/reel.cmd` wrappers and
`setup/setup_env.py` are never tested either.

### 1.2 Docs ↔ CLI mismatches

**No doc names a command that doesn't exist.** But these documented or engine-printed forms fail:

- **MI-1 (Minor): `reels-select --resync` without `--by`** exits 2 (`--by` is `required=True`, podcast_cli.py:23). The
  engine's own refusal hint prints exactly that form (cli.py:193). It also appears in agents/transcript-editor.md:43,
  skills/transcript-craft/SKILL.md:77 and skills/podcast/SKILL.md:73.
  *Fix:* make `--by` required only when `--pick` is given, or add `--by editor` to every hint, and add a CLI-level test.
- **MI-2 (Minor): `reel verify --record pass|fail --notes …`** (motion_cli.py:160) is wrong. `--record` is a flag, so the
  correct form is `--record --verdict pass`. *Fix the hint text.*
- **MI-3 (Minor): `reel setup --system-site-packages`** (skills/setup/references/platform-setup.md:29, added by r4-b)
  does not exist. Only `setup_env.py` has that flag. *Fix the doc,* and see IM-1: that flag should not be recommended at
  all.
- **MI-4 (Minor): `music --list`** is used in 6 docs, but `cmd_music` never reads the flag (podcast_cli.py:130-136).
- **Undocumented commands:** `ppro-probe` and `status`.
- **Stale docstring:** the module docstring of cli.py:2-24 omits about 30 commands.

### 1.3 Naming inconsistencies (Minor, MI-5)

- `ae-*` mixes opt-in extras (`ae-build/ae-render`, which need `--extras`) with core motion commands (`ae-status/ae-probe`).
- `ppro-install` installs the After Effects side too, and there is no `ae-install`.
- `next` vs `episode-next`. Four different "preview" commands (`previews`, `preview-video`, `reels-preview`,
  `motion-animatic`).
- `--note` (approve-plan, transcript-verify, reels-select) vs `--notes` (verify, ae-probe).
- `verify --record --verdict pass|fail` vs `ae-probe --record ok|fail`.
- `--by` is validated on approve-plan and reels-select, and free text on transcript-verify, ref-style and verify.
- List options are sometimes comma lists (`--pick`, `--ids`, `--words`, `--scenes`) and sometimes repeatable
  (`--adjust`, `--confirm-avoid`, `--set`). **`--confirm-avoid R05,R06` silently matches nothing** (whole-string
  membership in reels.select).
- `--force` has 7 meanings across commands.

*Fix:* a small CLI style guide (verb-noun, `--note` everywhere with `--notes` as an alias, comma lists parsed
everywhere), and alias the old forms for one release.

---

## 2. Architecture and code health

### 2.1 Module boundaries

The layering is sensible:
- `cli.py`, `podcast_cli.py` and `motion_cli.py` handle argument parsing and dispatch.
- `lib/*` holds the stages.
- `common.py` holds paths, time, JSON, status and profile layering.
- `plat.py` holds every OS difference, stdlib only, so hooks can import it.

Imports are lazy inside handlers, which keeps `reel doctor` fast and lets machines without the ML stack run onboarding.
The machine-state/plugin split (engine home outside the plugin folder) is right for an auto-updated plugin.

**Files doing too much (Minor, MI-6):**
- `plan.compile_plan` (plan.py:162-605) is one ~440-line function. It does validation, camera timeline, auto-reframe,
  cutaways, per-shot framing (shots.py), 4:5 windows, pause and word-cut TimeMap, caption rebuild, music, recipe checks,
  flag enforcement and the writes. It is hard to test piecewise and is where IM-3 and IM-7 live. *Split it into*
  `validate_decisions → build_camera → apply_framing → apply_timemap → build_audio → write_outputs`, each pure and
  returning (data, errors, warnings).
- `cli.py` contains orchestration logic, not just dispatch. Examples: `cmd_next` dependency/stale logic (cli.py:558-623),
  `cmd_range` (144-178), `main_footage` (58-78). Three different "next" engines exist: `cli.cmd_next`,
  `episode.episode_next` and `motion_qc.motion_next`. *Extract* a declarative step graph (step → outputs → inputs) and
  generate `next`/stale for all three modes from it.
- `previews.render_event` (previews.py:254-426) is a long per-template `if/elif`. A template registry
  (`{template: renderer}`) would let templates be added without touching the dispatcher.

**Duplicated logic (Minor, MI-7):**
- Caption hidden-range computation (source→sequence mapping of `captions_hidden_ranges`, hide-during templates) appears
  three times: ppro_build.py:27-52, ppro_build.py:121-128 and ae_builder.py:103-135.
- Contact-sheet assembly appears seven times: verify.build, ppro_build.export_frames, reels.render_candidates,
  episode.intake_frames, publish.thumbnail_candidates, motion_render.frames, previews.render_all.
- Single-frame ffmpeg grab appears four times: previews.grab_frame, publish.frame_at, ae_render.extract_frames,
  ref_analysis.frames_at.
- Face detection appears twice: previews._face_center_* and shots._boxes_*.
- Time parsing appears four times: cli._parse_time_ms, plan.to_ms, publish.parse_time, common.parse_ts.
- The Whisper segment loop appears twice: transcribe._run_whisper and episode._decode.
- *Fix:* `lib/media_util.py` (frame grab, sheet builder) and one `parse_time`. This also fixes MI-9 (leaks) in one
  place.

**Global state (Minor, MI-8).** `ENV_DIR`, `QUEUE`, `EXT_DIR` and `SCRIPTS` are computed at import time
(common.py:36, ppro_bridge.py:21-26, ae_bridge.py:16-21), so an env change after import is ignored. There is also a
mutable context `_CTX` + `_RATE_CACHE` (common.py:70, 315-322), plus caches `_INSTALLED_PS`, `_FACES` and `_FONT_FILES`.
This is fine for a one-shot CLI, but tests must set env before import, and a long-lived process (a future daemon or
MCP server) would serve stale profile data. *Fix:* functions (`engine_home()`) instead of module constants, and an
explicit `Context` object passed down.

**Status machine.** `cmd_next` tests for `"DELIVERED"` (cli.py:618), which is not in `STATUSES` (common.py:103-108), and
`set_status` asserts membership. `project-status.json` history grows without bound (Minor).

### 2.2 Error handling (IM-7, Important)

The style is mostly good. Refusals are plain-English `SystemExit` strings or JSON `{"blocked": ..., "how": ...}` that
say what to do next, for example `require_plan_approval` (cli.py:349-359) and `refuse_stale_window`. But:

1. **No top-level exception handler** (cli.py:784-915). Any unexpected exception prints a Python traceback to a
   non-technical editor or agent. Reproducible triggers:
   - A decision without `start`, or with an empty `start`. plan.py:187-189 records "missing 'start'", but then
     plan.py:198 `to_ms(d["start"])` raises `KeyError`/`ValueError` before the error list is returned. The same happens
     with `g.get("start", d["start"])` at plan.py:223.
   - **A JSON file saved with a UTF-8 BOM** (PowerShell 5.1 `Out-File`/`Set-Content -Encoding utf8` writes one).
     `read_json` uses `encoding="utf-8"` (common.py:181-182), so `json.load` raises "Unexpected UTF-8 BOM". `srt.read_srt`
     already uses `utf-8-sig`, so the handling is inconsistent.
   - `reel ref-analyze` before `discover`: `inv["files"]` on `None` (cli.py:247-248) raises `TypeError`.
   - `_loudness` does `re.findall(...)[-1]` (audio_clean.py:134), which raises `IndexError` on silent or unreadable audio.
   - `subprocess.TimeoutExpired` from `run(..., timeout=)` in ae_builder.render and ae_render.
   - `sfx.synth` raises `KeyError` for unknown kinds (sfx.py:36-38, see IM-10).
2. **The exit code does not reflect failure.** These print a failure and exit 0:
   - `plan` (`ok:false`, cli.py:296-324)
   - `qc` (`failed`, cli.py:509-526)
   - `ppro-build` (`FAILED` / `BRIDGE_NOT_RUNNING`, cli.py:425-433)
   - `preview-video` (`ok:false`)
   - `motion-build` REFUSED

   Meanwhile stale/approval refusals exit 2. Agents parse JSON, but autopilot loops, shell scripts and any future CI
   cannot rely on `$?`.

*Fix:* wrap `main()`. Map `SystemExit` as-is. Map known exceptions (`json.JSONDecodeError`, `KeyError`, `ValueError`,
`FileNotFoundError`, `PermissionError`, `TimeoutExpired`) to `{"ok": false, "error": ..., "where": file, "how": ...}` and
exit 1, and append the traceback to `logs/pipeline.log`. In `out()`, exit 1 when the payload has `ok is False` or a
`status` in a FAILED/REFUSED set. Make `read_json` use `utf-8-sig` and re-raise decode errors with the file name and line.
Validate required fields **before** using them in `compile_plan`.

### 2.3 Logging (Minor, MI-10)

`log()` (common.py:300-307) writes timestamped lines to stderr and to `<project>/logs/pipeline.log`. stdout is reserved
for one JSON document, which is a good contract.
- There are no levels, no run or command id, and no rotation.
- Long single-clip operations are silent for minutes: `transcribe` consumes the faster-whisper generator without
  progress, and preview-video renders frame by frame silently. Only the episode transcription logs per-chunk ETA
  (episode.py:466-470).

*Fix:* add a `--progress` stderr line every N seconds for Whisper (segment end time / duration) and preview-video
(frame/total). Prefix log lines with the subcommand.

### 2.4 Artefact schemas and validation (Minor, MI-11)

There is no JSON Schema and no `schema_version` in any artefact. Authored files (edit-decisions.json, reels-plan.json,
motion-script.json, publish.json, transcript-corrections.json) are validated ad hoc inside the compilers:
- plan.py:182-289
- reels.py:compile_reels_plan
- motion_script.check_fields
- publish.check

Compiled files (timeline-spec.json, motion-plan.json, reels-plan-validated.json) carry no engine version, so a plan
compiled by 2.1 and built by 2.2 is not detectable.
*Fix:*
- Ship `schemas/*.schema.json`, generated or hand-written, with `"schema_version"`.
- Add a `reel validate <file>` that checks the schema first, so the compilers can assume shape (this removes the
  KeyError class of IM-7).
- Stamp `engine_version` into every compiled artefact and refuse or warn on mismatch.

### 2.5 Idempotency and resume

Mostly strong:
- `transcribe` skips unless `--force`.
- Episode chunk checkpoints are validated by file fingerprint, chunk bounds and language (episode.py:431-455).
- `save_still` writes only changed pixels.
- Reference analysis is cached by path, size and mtime (ref_analysis.py:109-135).
- The inbox probe cache is keyed by stat.
- `ppro-build` refuses an existing project without `--force` and detects editor edits by content signature
  (verify.py:66-97).
- Motion audio is content-addressed (motion_audio.py:28-52).
- `next` computes staleness from mtimes.

Gaps:
- IM-3 (approval fingerprint).
- MI-12: episode chunk checkpoints don't record model or prompt (episode.py:451). Changing `whisper_model` and re-running
  without `--force` silently mixes models.
- mtime-based staleness can be fooled by copying a client folder between machines (tools that don't preserve mtimes),
  which is the "moving to another device" case. *Prefer content hashes* for the plan and spec inputs, as
  `motion_plan.fingerprint` already does.

### 2.6 IM-3 — approval fingerprint covers only part of the plan (Important)

`plan_fingerprint` hashes the bytes **after the first `"events"`** in timeline-spec.json (plan.py:608-610). The spec
dict is written in this key order (plan.py:558-567):

`generated, video_id, fps, source_in_ms, source_range, duration_ms, duration_frames, rounding_policy, main_footage,
base_scale_percent, base_offset_x/y, framing, main_segments, events, …`

Everything before `events` is outside the fingerprint:
- all camera moves and punch-ins (`main_segments`)
- the framing (a switch from 9:16 to a 4:5 window)
- base scale and offsets
- `main_footage`, the source range and the duration

A re-plan that changes only these keeps the approval valid, so `ppro-build` and `qc` accept it (qc.py:284-287,
cli.py:349-359). The docstring promises "A re-plan after approval invalidates it".
*Fix:* hash a canonical JSON of the spec without `generated`:
`sha1(json.dumps({k: v for k, v in spec.items() if k != "generated"}, sort_keys=True, ensure_ascii=False))`.
Add a test that changes a camera move after approval and expects a block. Note that this invalidates existing approvals
once: say so in the CHANGELOG.

### 2.7 IM-16 — frame size hard-coded in places (Important)

`sequence-settings.json` (frame_width/height) is honoured by `preflight`, `premiere_xml.build_xml`, `qc` and
`plan.window_rect`. But 1080×1920 is hard-coded in:
- `previews.py:19` (all stills)
- `verify.py:23`
- `preview_video.py:171` (16:9 ratio)
- `ppro_build.py:16-20` (`previewFrameWidth/Height`)
- the read-back check `frame_1080x1920` (ppro_build.py:250)

A profile with another size (for example 1080×1350, or 1920×1080 for YouTube cut-downs) gets stills at the wrong size
and a build that always reports `PRPROJ_BUILT_WITH_ISSUES`.
*Fix:* read W/H from `load_config("sequence-settings.json")` in one helper. Until then, reject non-1080×1920 profiles
explicitly in `preflight`.

---

## 3. Cross-platform (Windows and macOS)

All 2.x live verification was on Windows 11 (CHANGELOG L250, L265). macOS paths are reasoned from code and older 1.x
production use. The 2.2.0 and 2.2.1 CHANGELOG list "macOS: not verified live".

### 3.1 CR-2 — `bin/reel` is not executable in git (Critical on macOS, needs confirmation)

`git ls-files -s` shows `100644` for `whynot-cut/bin/reel`, `setup/setup_env.sh` and `hooks/run_python.sh`. It has
been `100644` in every commit that touched it, and **no file in the repo is `100755`** (`core.filemode=false` on this
Windows clone hides it). A plugin cloned from the marketplace on macOS gets `-rw-r--r--`. Bash on PATH then reports
"permission denied" for `reel`, and the skills' fallback `"${CLAUDE_PLUGIN_ROOT}/bin/reel"` fails the same way. Hooks are
unaffected because they run through `bash "<file>"`. Windows Git Bash treats a `#!` file as executable, which is why
nobody noticed.
*Fix:*
```
git update-index --chmod=+x whynot-cut/bin/reel whynot-cut/setup/setup_env.sh whynot-cut/hooks/run_python.sh
```
Add a test that runs `git ls-files -s` and asserts `100755` for those paths. Confirm on a Mac after a fresh plugin
install (`ls -l ~/.claude/plugins/**/bin/reel`). If the release zip is built on Windows, set the mode in the zip too.

### 3.2 Paths (spaces, Arabic, Git Bash)

- **CR-1 (Critical), clip identity.** Video IDs come from `slug(stem)` (common.py:222-224: `[^A-Za-z0-9]+ → _`, upper
  case, empty → `VIDEO`):
  - `reel inbox` hands out the slug (onboard.py:180), and `main()` auto-fills it (cli.py:911).
  - But `main_footage()` matches the **raw stem** (cli.py:74).

  Verified in memory with 4 raw clips:

  | Raw clip | ID handed out | Result |
  |---|---|---|
  | `Dr Sherif intro.mp4` | `DR_SHERIF_INTRO` | `SystemExit: no raw clip named 'DR_SHERIF_INTRO'` |
  | `Dr Sherif outro.mp4` | `DR_SHERIF_OUTRO` | `SystemExit` |
  | `مقابلة ١.mp4` | `VIDEO` | `SystemExit` |
  | `مقابلة ٢.mp4` | `VIDEO` | `SystemExit` (both collide) |

  `slug('مقابلة 1')` is `'1'`.

  Consequences:
  - Autopilot is blocked for normal file names.
  - If an agent works around it with `--footage`, two Arabic clips share `output/projects/VIDEO`. The second clip then
    *skips* transcription ("transcript exists") and is edited from the first clip's transcript.
  - If an agent uses the raw stem as `--video-id`, the work lands in a folder `inbox` never looks at, so the clip stays
    "new" forever and is re-edited on every "edit the new videos".

  Episodes already solved this: `episode_id_for` (episode.py:89-98) is an ASCII slug plus a short hash for non-ASCII
  names.

  *Fix:*
  - One `clip_id_for(path)` with the same rule as `episode_id_for`, plus a de-duplication suffix for `C0239.MP4` and
    `C0239.mov`.
  - Persist an `output/discovery/clip-ids.json` id→rel map.
  - Make `main_footage` resolve through the map (also accept the raw stem and the slug).
  - Make `inbox` and `cli.main` use it.
  - Add tests with spaces, Arabic, Arabic-Indic digits and duplicate stems.
- **Arabic folder names:**
  - FreeType and HarfBuzz font loading from non-ASCII paths was fixed in 2.2.1 (`hb_text._face` reads bytes;
    `motion_layout.find_font_file` falls back to memory).
  - aerender is staged through an ASCII temp copy on Windows (ae_render.py:44-73).
  - **MI-13:** the same staging is missing from the extras renderer `ae_builder.render` (ae_builder.py:197-214). That
    function also reports `RENDERED` when *any* `.mov` exists, including stale ones from a previous run.
- **Untested risk: non-ASCII Windows user name** (Minor, MI-14). The engine home, venv and models default to
  `%USERPROFILE%\.whynot-cut`. CTranslate2 (model.bin) and OpenCV (`cv2.CascadeClassifier(cv2.data.haarcascades …)`) open
  files through narrow paths on Windows. With an Arabic user name, Whisper may fail to load, and face detection silently
  returns nothing: the exceptions are swallowed in previews.py:155-179 and shots.py:83-107, so every reframe is centred.
  *Fix:* `doctor` warns when `ENV_DIR` is not ASCII on Windows and suggests `WHYNOT_HOME=C:\whynot`. It should also
  check that `cv2.CascadeClassifier(...).empty()` is False.
- **Git Bash paths.** `--root` and `settings --init` go through `native_path`, but `--footage` (cli.py:63, 152-153) does
  not. `/d/...` becomes `D:/d/...` and fails as "not found". This is MI-15 (Minor).
- **UNC paths** (`\\server\share`) in FCP7 `pathurl` become `file://localhost//server/share/...` (premiere_xml.py:26-32).
  This is untested, and NAS-based agencies will hit it (Minor, MI-16).
- **AppleScript strings** interpolate the JSX path inside quotes (adobe_run.py:33, 54). A client folder containing `"`
  breaks the command (see §10).

### 3.3 Subprocess usage

Every external call uses an argv list. There is no `shell=True` (grep of engine: none). ffmpeg filter strings contain
only numbers or fixed text, never paths. Timeouts are only set where Adobe is involved, so ffmpeg and ffprobe calls can
hang forever on a corrupt file or a network stall. This is MI-17 (Minor): add generous timeouts (for example
`10 + 3 × media_duration`).

### 3.4 ffmpeg / ffprobe discovery

`ffmpeg_exe()` (common.py:232-240) tries, in order: `NH_FFMPEG`, then **`shutil.which("ffmpeg")`**, then
`ENV_DIR/ffmpeg` (a symlink on macOS made by setup_env.py:90-94; it does not exist on Windows), then imageio-ffmpeg's
bundled binary.
- A system ffmpeg on PATH (old Chocolatey or Homebrew builds) wins over the pinned imageio-ffmpeg 0.6.0 (ffmpeg 7.x). The
  filters the engine relies on (`afftdn`, `alimiter`, `ebur128=peak=true`, `showspectrumpic`, `select=gt(scene)`) vary
  by version and build. This is MI-18 (Minor). *Fix:* prefer the bundled binary, allow an override, and have `doctor`
  print `ffmpeg -version` and test the filters.
- **ffprobe is not used.** Probing is done with PyAV (media.probe), plus one `ffmpeg -i` parse for rotation
  (media.py:14-20). `discover.audit_environment` still reports `which("ffprobe")` (discover.py:173), which is harmless
  noise.

### 3.5 Fonts discovery

`plat.font_dirs()` (plat.py:70-78):
- Windows: `%WINDIR%\Fonts` + `%LOCALAPPDATA%\Microsoft\Windows\Fonts`.
- macOS: `~/Library/Fonts`, `/Library/Fonts`, `/System/Library/Fonts`.

Not covered:
- **Adobe Fonts (Creative Cloud activated) folders** on both OSes. A client font activated through Adobe Fonts is
  reported "not installed" even though Premiere and After Effects can use it.
- Font managers.
- **IM-12 (Important, macOS):**
  - `find_font_file` (motion_layout.py:157-158) and `installed_postscript_names` (client_db.py:36) only read
    `.ttf/.otf`. The macOS motion fallback `GeezaPro-Bold` (config/defaults/motion.json:29) ships as
    `/System/Library/Fonts/GeezaPro.ttc`, so `motion-build --allow-fallback-font` should return "the fallback font … is
    not installed either" on a Mac (motion_build.py:213-216). This is from reading the code: confirm on a Mac.
  - `_system_font()` (motion_plan.py:38-45) globs only top-level `*.ttf` with Windows-style names. macOS keeps
    Arial/Tahoma in `/System/Library/Fonts/Supplemental`, so the "measure text with a system font" fallback raises
    `SystemExit` on a Mac without brand font files.

  *Fix:* scan `.ttc/.otc` with `fontNumber`/face index (FreeType `Face(path, index)`), recurse, and add macOS names
  (`GeezaPro.ttc`, `Supplemental/Arial.ttf`). Test with a fake `.ttc` collection.

### 3.6 GPU and Apple Silicon (IM-13, Important)

- **Windows and Linux.** CUDA via CTranslate2, with cuBLAS 12 from NVIDIA's redistributable, sha256-checked
  (plat.py:226-267). A GPU failure at first inference falls back to CPU (transcribe.py:103-113, episode.py:398-407).
  This is good.
- **macOS.** `gpu_info()` returns `cpu` (plat.py:313-314). There is **no MLX, CoreML or Metal path**. On Apple Silicon,
  faster-whisper runs CTranslate2 int8 on the CPU.
- **CPU threads.** `WhisperModel(...)` is never given `cpu_threads` (transcribe.py:75, 111; episode.py:405). In
  faster-whisper 1.2.1 that means **4 threads** (`cpu_threads: … (4 by default)`, transcribe.py:652 in the installed
  package). An M2/M3 Pro with 8-12 performance cores, or a 16-core Windows PC, is left mostly idle.
- The engine's own estimate is 1.2 min of CPU per minute of audio for large-v3 (episode.py:179-180), so a 90-minute
  episode takes about 1 h 48 min on CPU.

*Fix (in order of cost):*
1. `cpu_threads=os.cpu_count()` (or physical cores), configurable in transcription.json.
2. Make `large-v3-turbo` the macOS default.
3. An optional `mlx-whisper` backend for `darwin/arm64`, which supports word timestamps: `transcription.json`
   `"backend": "mlx"`, the same output schema, and install it on Apple Silicon only.
4. `BatchedInferencePipeline` (present in 1.2.1) for CUDA. See §9.

### 3.7 Adobe app and aerender discovery (IM-15, Important)

`find_adobe_apps` (plat.py:113-135) scans `ProgramW6432`/`ProgramFiles`/`ProgramFiles(x86)` `\Adobe\<prefix>*` on
Windows and `/Applications/<prefix>*` on macOS.
- Creative Cloud lets users install to another drive (`D:\Adobe\...`). Apps there are reported "not installed", so
  `reel setup` skips the bridge (cli.py:639-642) and motion-build refuses.
- `~/Applications` and beta builds (`(Beta)`, which get year 0) are also missed.
- aerender on macOS is `<AE folder>/aerender` and on Windows `Support Files\aerender.exe` (plat.py:143-148). Both are
  correct.

*Fix:*
- Windows: read `HKLM\SOFTWARE\Adobe\Premiere Pro\<ver>\InstallPath` (and the After Effects / Photoshop equivalents),
  or `App Paths`.
- macOS: `mdfind "kMDItemCFBundleIdentifier == 'com.adobe.PremierePro*'"`.
- Add overrides `WHYNOT_PREMIERE_APP`, `WHYNOT_AE_APP`, `WHYNOT_AERENDER`.

Related Minor (MI-19): `reel setup` installs the bridge only when *Premiere* is found (cli.py:639). A motion-only
machine with only After Effects gets no bridge.

### 3.8 Line endings, `python -I` (G67), wrappers

- **Line endings are handled.** The marketplace root `.gitattributes` has `* text=auto eol=lf`, `*.cmd eol=crlf`, `*.sh`
  and `bin/reel` `eol=lf`. `git ls-files --eol` confirms LF for bin/reel and the hooks and CRLF for reel.cmd.
- **G67 root cause (IM-1, see §4.2).** It is not a Windows `-I` quirk. Here is the measurement on this machine:

  | Fact | Value |
  |---|---|
  | venv/pyvenv.cfg | `include-system-site-packages = true` (made with `setup_env.py --system-site-packages`) |
  | Loaded from `%APPDATA%\Python\Python313\site-packages` (user site) | PIL 11.3.0, av 19.0.1, numpy 2.5.3, faster_whisper 1.2.1, ctranslate2 4.8.2, cv2 4.14.0, fontTools 4.66.1, imageio_ffmpeg 0.6.0 |
  | Installed in the venv itself | only uharfbuzz, freetype-py, pypdf, arabic-reshaper, python-bidi |

  `-I`, `-s` and `-E -s` disable the user site, so the imports fail. No flag, or `-E` alone, works. The r4-b
  "fix" (cb0539f) only documents "don't use -I".
- **Wrapper differences (Minor, MI-20):**
  - `reel.cmd` lacks the `.dr-nahla-editor` legacy home that `bin/reel` has (reel.cmd:9-12 vs bin/reel:10-12).
  - `reel.cmd` runs setup with `py -3 … || python …`, so a setup that *reports* failure (exit 1) is executed a second
    time with `python` (reel.cmd:18).
  - Batch `%*` expands `%` in arguments, so a client folder like `100% Natural` breaks.

### 3.9 Windows-only or macOS-untested places

| Area | Windows-only code / macOS-only code | macOS verified? |
|---|---|---|
| aerender ASCII staging | ae_render.py:44-73 (Windows only by design) | macOS "renders in place", not live-tested (CHANGELOG 2.2.1 L9-13) |
| Locked-file handling (save_still, `_clear`, prune) | previews.py:233-251, motion_render.py:37-44, motion_audio.py:55-77 | n/a |
| cuBLAS / gpu-enable | plat.py:199-308, cli.py:658-683 | n/a (no GPU path on Mac) |
| PlayerDebugMode via `winreg` vs `defaults` | plat.py:167-195 | `defaults` path untested in 2.x |
| After Effects run: `AfterFX.exe -r` vs AppleScript `DoScriptFile` | adobe_run.py:26-44 | AppleScript path only verified in 1.x |
| Photoshop COM via PowerShell vs AppleScript | adobe_run.py:47-62 | 1.x only |
| CoreText rendering + Vision faces (macOS) vs HarfBuzz + OpenCV (Windows) | ct_text.py, previews.py:127-179, shots.py:59-107 | CoreText test is skipped on Windows; Vision never tested in 2.x |
| `textutil`/`mdls`/`sips` document, PDF and RAW conversion | discover.py:75-90, client_db.py:161-176 | macOS-only tools, 1.x verified |
| Motion fallback font `.ttc` | IM-12 | broken on Mac (code reading) |
| bin/reel executable bit | CR-2 | breaks on Mac (code reading) |
| Whisper integration test | test_pipeline.py:372-378 uses macOS `say` | the only real-Whisper test cannot run on Windows |
| CEP bridge on macOS | the bridge.js extension-path fallbacks | not verified with bundle 3.1.0 |

---

## 4. Dependencies and setup

### 4.1 Pins and Python version

`setup/requirements.txt`:
- Pinned exactly: `faster-whisper==1.2.1`, `imageio-ffmpeg==0.6.0`, `arabic-reshaper==3.0.0`, and pyobjc `11.1`
  (darwin).
- Ranges with upper caps: `ctranslate2>=4.6,<5`, `av>=14,<21`, `numpy>=2.1,<3` (2.0.2 on <3.10), `pillow>=11.3,<13`,
  `fonttools`, `python-bidi`, `uharfbuzz`, `freetype-py`, `pypdf`, `opencv-python-headless` (non-darwin).

Python versions:
- `setup_env.py` requires 3.9 or newer and warns at 3.14 or newer (setup_env.py:60-66).
- The docs say "3.10–3.12 best" (some docs say 3.13). This machine runs **3.13**, and all tests pass.
- pyobjc 11.1 has no 3.14 wheels, so a python.org 3.14 Mac would try to compile pyobjc. *Cap pyobjc to the Python
  versions that have wheels, or move to 12.x for 3.14.*

There are no hashes and no lock file. A fresh install months later can pull a newer ctranslate2, av or numpy inside the
ranges. Every field-test regression so far (G17 PyAV `metadata_errors`) came from exactly this. This is MI-21 (Minor to
Important). *Fix:* commit a `requirements.lock` per platform (pip-tools `--generate-hashes`) and install it with
`--require-hashes`. Keep the ranges file for development.

### 4.2 What `setup_env.py` does, step by step

1. Resolves the engine home: `--home`, env vars, `~/.whynot-cut`, or a legacy home (plat.engine_home).
2. Refuses Python older than 3.9 and warns at 3.14 or newer.
3. Creates `home/models` and the venv (`python -m venv`, optionally `--system-site-packages`).
4. `check_modules()` imports the module list in the venv python.
5. Installs **only if** a module is missing (or `--upgrade` / `--system-site-packages`): `pip install --upgrade pip`, then
   `pip install -q -r requirements.txt`, capturing the last 3000 characters of the error.
6. Re-checks the modules.
7. Finds the imageio ffmpeg binary and, on macOS and Linux, symlinks `home/ffmpeg` to it.
8. Lists Adobe apps.
9. Prints a JSON report and exits 1 if any module is missing.

**Failure modes and gaps:**
- **IM-1 (Important): the venv is not isolated when `--system-site-packages` is used** (it was used on this machine).
  - pip treats packages in the user site as satisfying the requirements and installs nothing into the venv.
  - A later `pip install --user --upgrade numpy av` by any other tool silently changes or breaks WhyNot Cut.
  - `-I/-s` breaks (G67).
  - The tests on this machine ran against user-site packages, not the venv.

  *Fix:*
  - Remove the `--system-site-packages` option, or keep it but install with `pip install --ignore-installed`.
  - `doctor` should verify that every engine module's `__file__` is under `venv/` and that versions satisfy
    requirements (`importlib.metadata.version` + `packaging.specifiers`), and report "engine not isolated" with the fix.
  - Once the venv is clean, run the engine with `python -s` in `bin/reel` and `reel.cmd`, so user-site packages can
    never leak in.
- **IM-2 (Important): no repair or update path.**
  - `reel setup` (cli.py:633-645) only installs the bridge and runs `doctor`. It never runs `setup_env.py`.
  - The wrappers run `setup_env.py` only when the venv python does **not exist** (bin/reel:18-37, reel.cmd:15-20).
  - So a missing or broken package in an existing venv is never repaired, even though `doctor`'s fix says
    `reel setup (re-installs the pinned packages)` (onboard.py:63). The setup skill says the same
    (skills/setup/SKILL.md:18-21).
  - When a plugin update changes `requirements.txt` (a new package or a new minimum), nothing upgrades the venv,
    because `check_modules` only checks importability, not versions.

  *Fix:* `cmd_setup` should call `setup_env.main(["--home", ENV_DIR])` (or the same logic in-process) before the bridge.
  `setup_env` should compare installed versions against requirements and install when they differ. Store a hash of
  requirements.txt in `home/venv/.whynot-requirements.sha` and re-install when it changes.
- pip runs with no timeout (setup_env.py:77-80). A stalled download hangs `reel setup` forever. Add `--timeout 60` and
  `--retries 5`.
- `--check` mode still reports `next: reel setup`.
- There is no wheelhouse or offline mode (see 4.4).

### 4.3 Model downloads

- **Whisper:**
  - `large-v3` is `Systran/faster-whisper-large-v3` on Hugging Face, 2.9 GB on disk here.
  - `large-v3-turbo` is `mobiuslabsgmbh/faster-whisper-large-v3-turbo` (about 1.6 GB).
  - `medium` and `small` are also available.
  - Downloads go to `<home>/models` via faster-whisper `download_model` / `snapshot_download`.
  - Xet is disabled by default (cli.py:788-791, G2b).
  - `doctor` reports "complete" (model.bin over 50 MB) vs "partial" (onboard.py:28-37).
- **cuBLAS 12 (Windows, optional):** NVIDIA redistributable manifest `redistrib_12.9.1.json`, sha256-verified, with only
  two DLLs kept (plat.py:222-267). There is a pip fallback (`nvidia-cublas-cu12`, about 550 MB).
- **Icons:** Lucide is bundled (`templates/motion/icons`). There are no run-time downloads.

### 4.4 Offline behaviour

- **Transcription:** `WhisperModel(model_size, download_root=...)` is called with a **model name**, not a path
  (transcribe.py:75). huggingface_hub first tries the network, then falls back to the cached snapshot. Offline, that
  costs connection timeouts on every model load. If the cache's `refs/main` is missing (an interrupted first download),
  it fails.
  *Fix:* when `whisper_model_state()` says complete, pass the snapshot directory (`models--…/snapshots/<rev>`) to
  `WhisperModel`, or set `HF_HUB_OFFLINE=1`.
- Everything else (ffmpeg, rendering, Premiere bridge, publish) is offline by design. Nothing is uploaded
  (publish.py:6).

### 4.5 Update path

- The plugin folder is replaced on update. The engine home survives.
- Bridge JSX is re-synced by hash before every job (ppro_bridge.py:33-45, ae_bridge.py:28-44).
- The bridge bundle is reinstalled by `reel setup` / `ppro-install`, with a downgrade guard (ppro_bridge.py:67-73).
- **Python packages are never updated** (IM-2).
- The running CEP panel stays old until Premiere restarts, and nothing compares versions (IM-5).

---

## 5. Bridge and job-queue robustness (engine side)

### 5.1 How it works

Python side:
1. `cep_queue.submit` (cep_queue.py:37-70) writes `<id>.data.json` (ASCII JSON) and `<id>.tmp`, then renames it
   atomically to `<id>.job.json`.
2. It polls `<id>.result.json` every 0.5 s until the timeout. The defaults are ping 30 s, close 60 s, probe 120 s,
   build 900 s, frames 600 s, AE motion build 900 s, readback 300 s.

Panel side (bridge.js):
1. Every second it writes a heartbeat (non-atomic `writeFileSync`; Python retries a torn read 4 times, cep_queue.py:23-28).
2. It picks the alphabetically first `*.job.json`, claims it by renaming to `.running`, `realpath`-checks that the script
   is inside the whitelisted folder, and runs `$.evalFile(...)` + `NHPP.run(data_file)`.
3. It writes the result and releases jobs older than 20 minutes.

### 5.2 Findings

**IM-4 (Important): timeouts leave live jobs behind.**
- When the CLI times out, it returns `{"error": "timeout…"}` (cep_queue.py:70) but leaves `<id>.job.json` (if not yet
  claimed) or `.running` in the queue.
- The panel has **no expiry**: `tick()` runs any queued job however old (bridge.js:108-111).
- So a `build_project` that timed out while Premiere was busy (another build, or a modal dialog) still runs minutes or
  hours later, for example on the next Premiere start.
  - The CLI has already moved the old project to `*_prev_*` (ppro_build.py:237-239) and recorded FAILED.
  - The late build then writes a new .prproj that no result file describes. The next `ppro-build --force` reports
    `EDITOR_CHANGES_PRESENT` ("content unknown").
  - Or, if the editor retried, the build runs twice.
- `.data.json` and `.result.json` are **never deleted** by either side (no `unlink` of them anywhere in the engine), so
  the queue grows forever.
- `.running` files from a crash are never cleaned up.

*Fix:*
- Put `expires_at = submitted + timeout` in the job. The panel discards expired jobs and writes a
  `{ok:false, error:"expired"}` result.
- On timeout the CLI tries `rename(job.json → job.cancelled)`. If that succeeds, the job never runs.
- Python deletes data and result after reading. A sweeper removes queue files older than one day.
- Report `.running` orphans in `ppro-status`.

**IM-5 (Important): concurrency and version handshake.**
- There is **no machine-wide build lock**. Two Claude sessions (two clients), or autopilot running `ppro-build` for two
  reels, each submit jobs. The panel serialises them, but each CLI's timeout clock includes the queue wait. With build
  timeouts of 900 s, the second build can time out while it waits, and IM-4 then follows. The autopilot skill's
  "Premiere builds run one at a time" is prose only.
- The manifest declares a visible panel **and** a hidden daemon with the same JS (manifest.xml:5-6, 17-55). Each copy
  has its own `busy` flag and both write the same heartbeat file, so `busy` flips between the copies' views.
  `motion_build.preconditions` relies on `busy` (motion_build.py:156-157). Both copies can also claim different jobs
  at the same time; the host serialises them, but the 20-minute timeout clocks start at claim time.
- **There is no runtime version handshake.** The heartbeat carries `version` (bridge.js:65), and Python reads it into
  `bridge_version` (cep_queue.py:32), but nothing compares it with `BRIDGE_VERSION` (ppro_bridge.py:22). After a plugin
  update, a Premiere that was not restarted runs the old panel against new JSX libraries. Static version agreement is
  tested (test_motion.py:150-179), but runtime agreement is not.

*Fix:*
- Use an exclusive lock file `ppro-queue/.build.lock`, with PID and expiry, around ppro-build, ppro-frames and
  motion-build.
- Start each job's timeout when the panel **claims** it: the panel writes `<id>.claimed`, and Python waits up to N
  minutes for the claim, then up to the timeout for the result.
- Let only the daemon process jobs (the panel shows status only), or use a single-instance lock file in the queue.
- Warn or refuse when `heartbeat.version != BRIDGE_VERSION`: "restart Premiere to load bridge X".

**IM-6 (Important): G69 "Media pending".**
- `export_frames` (ppro_build.py:274-329) counts PNGs newer than t0 and compares the count with the number expected
  (lines 302 and 324-325).
- A frame Premiere rendered while media was still loading is the grey "Media pending" slate. It counts as success, and
  qc-reviewer has to catch it by eye (4 of 17 frames in the AE session).

*Fix (engine side):*
1. Before exporting, poll a cheap bridge action that reports offline or pending media (`projectItem.isOffline()`/media
   status) until clear, or for up to 30 s.
2. After export, detect the slate: low-variance grey frames, or a histogram match against a stored slate signature.
   Re-request just those times once or twice with a delay.
3. Return `pending_frames` and never `ok:true` while any remain.

Add a test with a synthetic slate PNG.

**Smaller items:**
- `cep_queue.status` raises `KeyError` on a heartbeat without `at` (cep_queue.py:31).
- `ppro_build.build` renames the existing project to `_prev_` *before* the submit, so a bridge failure leaves no
  project at the expected path (ppro_build.py:236-239). *Fix:* rename after a successful build, or restore on failure.
  Together these are MI-22 (Minor).
- **Whitelist path check (Minor).** The JS compares `realpathSync(job.script)` with `realpathSync(BASE)+scripts`
  (bridge.js:47, 81-85). Python sends an *unresolved* `ENV_DIR` path, while `bridge-config.json` stores
  `ENV_DIR.resolve()`. With a custom `WHYNOT_HOME` whose drive-letter case or symlinks differ, JS realpath may keep the
  given case and reject the script. *Fix:* send `str(SCRIPTS.resolve() / name)`.

---

## 6. Quality and correctness risks

Findings already covered elsewhere: CR-1, IM-3, IM-7, IM-16.

- **IM-8 (Important): substring role classification** (discover.py:12-20, 37).
  - `ROLE_HINTS` are matched as substrings of the *whole lower-cased path*, in list order, and `("ref",
    "editing_reference")` comes before `("raw", "source_footage")`.
  - Verified with `classify()`: `data/Raw/Refractive surgery Q&A.mp4`, `data/Raw/Reflux - episode 3.mp4` and
    `data/Raw/Preface.mov` all become `editing_reference_video`. `data/Raw/Stock market myths.mp4` becomes `broll_video`.
    The same applies to "brief" in "debrief".
  - Such clips silently disappear from `inbox`/autopilot, and they are analysed as style references. The trigger is
    likely for medical clients ("Refractive", "Reflux", "Reference ranges").

  *Fix:*
  - Decide the role by **folder first**: `data/Raw/**` is source footage, `data/References/**` is references,
    `data/Broll/**` is B-roll.
  - Use filename hints only for files outside known folders, and match them on word boundaries (`\bref(erence)?s?\b`).
  - Add a warning listing any video whose folder and filename hints disagree.
- **IM-9 (Important): handoff README for clip projects is stale** (handoff.py:57-117).
  - It always says "Premiere sequence: FCP7 XML interchange (automated) → you import + save as .prproj" (line 73).
  - It tells the editor to "File › Import … the XML" (81).
  - It says the captions are "already on the C02 track (AE render)" (88).
  - It reports After Effects and Photoshop as "SCRIPT ONLY — run the JSX" (70-72).
  - It never reads `07_premiere/ppro-build-result.json`.
  - On the default native path, where the .prproj is already built and captions are stills on the cap lanes, these
    instructions are wrong and would lead an editor to import a second sequence.

  *Fix:* branch on `ppro-build-result.json` status. Document the native project, its track map from `job_data`
  `track_names`, and the caption lanes. Show the XML steps only for the fallback, and hide the After Effects and
  Photoshop rows unless the extras were used.
- **IM-10 (Important): client SFX library and sound kinds.**
  - `06_audio/sfx-map.json` is promised by cli.py:343 and skills/audio-craft/references/sound-design.md:15, but no code
    reads it. The cue sheet always points to `06_audio/sfx/<kind>.wav` (plan.py:588-593).
  - `compile_plan` accepts any `sound[].type` (plan.py:283-288). `reel sfx` then raises `KeyError` (sfx.py:36-38), while
    `motion_plan` validates kinds (motion_plan.py:700-704).

  *Fix:* validate kinds against `sfx.RECIPES` ∪ map keys in `compile_plan`. Implement the map: copy or convert the
  mapped library file to `06_audio/sfx/<kind>.wav` with provenance, or drop the claim from the docs.
- **IM-11 (Important): Windows concurrency on shared JSON.**
  - `write_json` writes `<name>.tmp` and then `os.replace` (common.py:185-193). The temp name is fixed, so two processes
    writing the same file at once interleave or fail.
  - On Windows, `os.replace` onto a file another process has open for reading fails with `PermissionError` (Python opens
    without `FILE_SHARE_DELETE`).
  - Autopilot runs several per-clip agents in parallel. They all read `output/discovery/input-inventory.json`, and
    `discover` / `inbox --refresh` rewrite it. They also share `raw-probe-cache.json` (onboard.py:206-231) and
    `reference_analysis/cache.json`.
  - `set_status` is load-modify-write without a lock (common.py:284-297), so parallel stages on one clip lose history.

  *Fix:*
  - Unique temp names (`tempfile.NamedTemporaryFile(dir=parent, delete=False)`) plus a retry loop on
    `PermissionError` for `replace`.
  - A tiny cross-platform lock (`msvcrt.locking` / `fcntl.flock` on `<file>.lock`) in `write_json` and `set_status`.
  - Make discovery per-client and serialised (lock), and have per-clip commands never rewrite it.
- **MI-23 (Minor): `reels.select` is not atomic.** Picks are written one by one (reels.py:661-667). A later pick failing
  with `SystemExit` (duration, overwrite) leaves earlier reel projects created but not in `selection.json` history,
  which is appended only at the end (reels.py:670-673). So `episode-next` doesn't list them. *Fix:* validate all picks
  first, then write.
- **MI-9 (Minor): resource leaks that matter on Windows.**
  - `previews.grab_frame` creates a temp PNG with `mkstemp` and never closes the fd or deletes the file
    (previews.py:429-437). It is now called more often (the r4-a G68 probe), so `%TEMP%` fills with 2-4 MB PNGs.
  - `Image.open` without close: ppro_build.py:136, 312; previews.py contact sheet; motion_render.frames `im0`.
  - The motion animatic leaves a `Popen` stderr pipe unclosed. The test run prints `ResourceWarning: unclosed file` for
    test_motion.py:1143, 1156, 1589.
  - Open handles lock files on Windows.

  *Fix:* use `with` everywhere, `os.close(fd)` + `unlink` in `grab_frame` (or pipe rawvideo like `publish.frame_at`),
  and turn ResourceWarnings into errors in the hygiene test across all modules.
- **MI-24 (Minor): small correctness edges.**
  - `settings.parse` ignores a file starting with a BOM (settings.py:43), so preferences silently fall back to
    defaults. `episode._FM` already accepts a BOM.
  - `audio_clean` lists `highpass=f=90` twice (audio_clean.py:161). If the second is intentional (a 4-pole slope),
    document it.
  - The min-duration extension of the last SRT cue can run past the media end (srt.py:133-139).
  - `ppro_build.job_data` / `premiere_xml` give the cleaned-dialogue file element the full-source duration for range
    reels (premiere_xml.py:242).
  - `analyze_shots` keeps a 768-float histogram per sample in Python lists. A 90-minute raw clip at 2 fps holds about
    8 M floats, or 250+ MB (media.py:117-126).

---

## 7. Test coverage

### 7.1 Results (exact)

| Run | Code under test | Result | Time |
|---|---|---|---|
| 1 | discovered on `39026fb` (2.2.0); main fast-forwarded to 2.2.1 at 15:23, mid-run | `Ran 350 tests … OK (skipped=4)` | 359.5 s |
| 2 (`--durations`) | discovered on `920b9ff` (2.2.1); main moved to `cb0539f` at 15:30:50, mid-run | `Ran 376 tests … OK (skipped=4)` | 373.6 s |
| **3 (`--durations`), authoritative** | **`cb0539f` (current main; HEAD stable 15:31:36 → 15:39:50)** | **`Ran 435 tests in 492.582s` / `OK (skipped=4)`** | 492.6 s (machine shared with other sessions) |

Command: `C:\Users\LOQ\.whynot-cut\venv\Scripts\python.exe -m unittest discover -s .` from `whynot-cut\tests`. There were
no failures and no errors in any run. The suite is now 8 files (r4 added `test_round4_brand.py` and
`test_round4_reels.py`). Note that these packages come from the *user* site (IM-1): the suite does not
test the venv that `setup_env.py` would build on a clean machine.

**Skips (4):**
- `test_pipeline.TestDiscoveryAndClientDB.test_font_not_installed_is_reported`: 'brand font not installed'.
- `test_pipeline.TestWhisperIntegration.test_arabic` and `test_english`: need `NH_INTEGRATION=1`, and they synthesise
  speech with **macOS `say`** (test_pipeline.py:372-378), so the only real-Whisper test cannot run on Windows.
- `test_plugin.TestRTLLineDirection.test_latin_first_word_stays_rightmost`: 'CoreText not available' (macOS only).

Conditional skips that did *not* trigger here:
- `skipUnless win32` file-lock tests (test_motion.py:1599, 2655).
- The HarfBuzz/no-Arabic-font guards.
- The node-required JS tests.
- r4's inverse CoreText skips (test_round4_brand.py:170, 179).

### 7.2 Slow tests

There is no single outlier. The run time comes from many 3-9 s tests that spawn ffmpeg, renders or compiles. The
slowest (run 3):
- 9.5 s: `test_podcast.TestWindowMedia.test_qc_reel_checks`
- 9.4 s: `test_podcast.TestHygiene.test_tests_leave_no_resource_warnings_or_temp_files`
- 7.4 s: `test_xml_inpoints_offset`
- 7.1 s: `test_changed_episode_refused_by_build_commands`, `test_preview_video_seeks`
- 7.0 s: `test_motion.TestMotionQC.test_each_check_fails`
- 6.9 s: `test_qc_sync_offset_aware`
- 6.2 s: `test_audio_extract_sample_exact`
- 6.1 s: `test_wide_source_reframe_and_cutaway_letterbox`, `test_piece_render_after_rebuild_fails_render`
- Then a long tail of 3-6 s tests.

Run 2 showed the same set at 3.6-7.2 s.

*Fix:* share compiled fixtures per class (`setUpClass`). Run with `pytest -n auto` (pytest-xdist): the tests already use
temp dirs, and the 6-minute run would drop to about 1-2 minutes on 8 cores.

### 7.3 Untested areas (by risk)

1. **The identity and multi-clip flow** (CR-1). There is no test with ≥2 raw clips that have spaces, Arabic names or
   duplicate stems. The inbox test uses a single `C0001`.
2. **Wrappers and setup.** `bin/reel`, `reel.cmd`, `setup_env.py`, `reel setup`, `doctor`, `model-download` and
   `gpu-enable` have no test (IM-2, CR-2). There is no test of the git file mode.
3. **Bridge failure modes.** There are no tests for timeout, stale-job, cleanup, concurrent-submit or version mismatch
   (IM-4, IM-5). `ppro-status`, `ppro-probe` and `ae-status` have no tests. Media pending (IM-6) is untested.
4. **audio-clean core.** `detect_pauses` and `verify_cuts` have no test, and the real Whisper path is never exercised on
   Windows (integration tests are macOS-only).
5. **Authoring-error UX.** There are no tests for missing fields, BOM JSON or unknown SFX kinds (IM-7, IM-10). There
   is no test that the approval fingerprint covers camera and framing changes (IM-3).
6. **CLI-level parsing of podcast commands.** `reels-select` is only tested through the library, so the
   `--resync`/`--by` break is not caught. The `range` time parsing is untested.
7. **macOS.** CoreText, Vision, `osascript`, `textutil/mdls/sips`, the `.ttc` fallback and `defaults` PlayerDebugMode
   are never executed in 2.x CI. *Add a macOS CI job* (GitHub Actions `macos-14`, ffmpeg + venv, no Adobe) running the
   same suite.
8. **Non-9:16 profiles** (IM-16), **discovery role edge cases** (IM-8), and the **handoff text for native builds**
   (IM-9).
9. **Test hygiene.** Six CLI subprocess calls omit `-B` and may write `__pycache__` into the plugin (test_pipeline.py:290;
   test_plugin.py:132, 155, 181; test_crossplatform.py:257; test_ref_style.py:52). ResourceWarnings are printed in
   test_motion.

---

## 8. Gap status (G1–G69 + spec deferrals)

Status as of main `cb0539f`. Source: CHANGELOG (main), `round4-gaps.md`, `git log` of every branch.

| ID | Summary | Status |
|---|---|---|
| G1 | 16:9 → face-centred auto-reframe | fixed on main (2.0.0) |
| G2 | Partial Whisper downloads reported; `model-download` | fixed on main (2.0.0) |
| (G2b) | HF Xet died on Windows → plain HTTPS | workaround on main (2.0.0) |
| G3 | `Profile.jpg` classed as a brief → hints depend on file kind | fixed on main (2.0.0) |
| G4 | Sideways faces → OpenCV profile detector | fixed on main (2.0.0) |
| G5 | — | not found (number skipped) |
| G6 | No HEX → measured palettes | fixed on main (2.0.0) |
| G7 | Fonts-not-installed only advisory | fixed on main (2.0.0) |
| G8 | Cards burned into episode → cutaway detection | fixed on main (2.0.0) |
| G9 | Generic "the speaker" wording | fixed on main (2.0.0) |
| G10 | Card whole over blurred fill | fixed on main (2.0.0) |
| G11 | Licensed B-roll video clips | fixed on main (2.0.0) |
| G12 | Brand fonts in docs | fixed on main (2.0.0) |
| G13 | Religious review by profile domain | fixed on main (2.0.0) |
| G14 | Template colour roles | fixed on main (2.0.0) |
| G15 | One `still_category` | fixed on main (2.0.0) |
| G16 | Second audio stream reported | fixed on main (2.0.0) |
| G17 | PyAV `metadata_errors` → own decode | fixed on main (2.0.0) |
| G18 | Silent CPU fallback → doctor + gpu-enable | fixed on main (2.0.0; improved G54) |
| G19 | Arabic-normalised glossary | fixed on main (2.0.0) |
| G20 | Profile names spelled differently | fixed on main (2.0.0, reporting) |
| G21 | Uncertain words never on graphics; relisten | fixed on main (2.0.0) |
| G22 | — | not found |
| G23 | — | not found |
| G24 | Cut check ≤20 s chunks + 85 % match | fixed on main (2.0.0; superseded by G57) |
| G25 | Dual-mono → one channel | fixed on main (2.0.0) |
| G26 | Hum notches only where they stand out | fixed on main (2.0.0) |
| G27 | No denoise on clean master | fixed on main (2.0.0) |
| G28 | Document quotes vs transcript | fixed on main (2.0.0) |
| G29 | `cut_words` | fixed on main (2.0.0) |
| G30 | `reel range` | fixed on main (2.0.0) |
| G31 | `--video-id` picks its own clip or refuses | fixed on main (2.0.0). **But see CR-1: the id scheme it relies on is broken for non-slug names** |
| G32 | Client sequence rate (NTSC) | fixed on main (2.0.0) |
| G33 | FCP7 29.97 timebase | fixed on main (2.0.0) |
| G34 | Preflight never moves status back | fixed on main (2.0.0) |
| G35 | Editor's finished reel as human transcript | fixed on main (2.0.0) |
| G36 | Range snaps to pause | fixed on main (2.0.0) |
| G37 | Corrections re-anchor | fixed on main (2.0.0) |
| G38 | Pause settings from style | fixed on main (2.0.0) |
| G39 | edit-plan.md on reel timeline | fixed on main (2.0.0) |
| G40 | Preview background source time | fixed on main (2.0.0) |
| G41 | Captions on translucent box | fixed on main (2.0.0) |
| G42 | Captions move only on overlap | fixed on main (2.0.0) |
| G43 | Premiere frames include cutaways/camera | fixed on main (2.0.0) |
| G44 | QC failed every bridge build | fixed on main (2.0.0) |
| G45 | Handoff said 24 fps | fixed on main (2.0.0). **The handoff is still legacy otherwise (IM-9)** |
| G46 | Sharpen on ≥150 % upscale | fixed on main (2.1.0) |
| G47 | 4:5 framing | fixed on main (2.1.0). **Approval fingerprint blind to framing (IM-3)** |
| G48 | Strip caption punctuation | fixed on main (2.1.0) |
| G49 | Caption lead-in | fixed on main (2.1.0) |
| G50 | — | not found |
| G51 | Client export name/codec/loudness | fixed on main (2.1.0) |
| G52 | Per-video vocabulary | fixed on main (2.1.0) |
| G53 | Known hallucinations dropped | fixed on main (2.1.0) |
| G54 | cuBLAS from NVIDIA redist | fixed on main (2.1.0) |
| G55 | Host cut = another person | fixed on main (2.1.0; warning only, words not attributed) |
| G56 | Protected pauses not tested as cuts | fixed on main (2.1.0) |
| G57 | Deterministic two-reading cut proof | fixed on main (2.1.0) |
| G58 | Reference analysis cached per client | fixed on main (2.1.0) |
| G59 | Captions over card fill get the box | fixed on main (2.1.0) |
| G60 | Content signature for editor changes | fixed on main (2.1.0) |
| G61 | ppro-frames uses the reel's own project | fixed on main (2.1.0) |
| G62 | Previews ignored typography roles / first-file fallback | **fixed on main** (r4-a `a23c8d8`, merged via r4-b at 15:30) |
| G63 | `--adjust` snapped to sentence start | **fixed on main** (r4-b `3f04170`) |
| G64 | Evidence errors show corrected words | **fixed on main** (r4-b `bfeac5b`) |
| G65 | Intake missed name supers | fixed on branch **fix/r4-c** (`574881f`), not merged; branch based on old `39026fb` |
| G66 | Old `reel` first on PATH | fixed on branch **fix/r4-c** (`63d823a`), not merged |
| G67 | `python -I` loses packages | **workaround on main** (docs only, `cb0539f`). **Root cause open (IM-1)** |
| G68 | Highlight colour contrast | **fixed on main** (r4-a `9f782e3`) |
| G69 | ppro-frames "Media pending" | **open** (no code on any branch; see IM-6) |

**Counts (69 ids):**

| Status | Count |
|---|---|
| fixed on main | **61** |
| fixed on an unmerged branch (fix/r4-c: G65, G66) | **2** |
| workaround / docs-only on main (G67) | **1** |
| open (G69) | **1** |
| not found / skipped numbers (G5, G22, G23, G50) | **4** |

G2b is an extra workaround, and G55 is partial. None of G62–G69 is in a CHANGELOG yet. `round4-gaps.md` lines 30-31
are out of date: the downgrade guard is on main since 2.2.0.

**Spec / plan deferred items (docs/superpowers):**

| Source | Item | Status on main |
|---|---|---|
| podcast-mode spec:35 | In-Adobe UI panel | not implemented (CEP panel is status/log only) |
| podcast-mode spec:36 | Raw multi-cam | out of scope, not implemented |
| podcast-mode spec:40 | pyannote diarization | not implemented (speakers authored by the analyst) |
| podcast-mode spec:41 | Split-screen (bridge feature unverified) | not implemented |
| podcast-mode spec:42 | Upload to platforms | not implemented, by design |
| podcast-mode spec:43 | Layered thumbnail PSD | not implemented |
| podcast-mode spec:46 / shots.py:193 | Motion videos ("phase 3") | implemented in 2.2.0. shots.py note still says "phase 3" |
| motion spec:46, 422 | Whole-episode animation (>180 s) | deferred (`motion.json` hard_max 180) |
| motion spec:49 | 4:5 and 1:1 motion formats | not implemented (9x16, 16x9 only) |
| motion spec:62, 416 | UXP for After Effects | not implemented (CEP; Adobe is moving to UXP, which is a strategic risk) |
| motion spec:65-66 | Generated images, lip sync, 3D, stock, Lottie, Premiere wrapping, upload | out of scope |
| motion spec:274 | Illustration packs | none shipped: illustrations unusable until an agency adds packs |
| motion spec:419 | Designer "look pack" | not implemented |
| motion spec:519 | `nh_ae_lib.jsx` hard-codes 24 fps for the clip extras | **still open** (`NH.FPS = 24`; ae_builder and mogrt_builder never set it). Extras on a 25/29.97 profile get 24 fps comps |
| motion spec:520 | Move the extras onto the bridge for read-back | not implemented |
| motion plan:757 | `claude plugin validate --strict` | no record it was run |
| motion plan:762-777 | Audio-only motion **live run** (PODCAST-AUDIO-TEST) | **not run** (code present: `reels.audio_card`) |
| CHANGELOG 2.2.0 L90-93, 2.2.1 L43-46 "Not verified live" | ppro-build on bundle 3.1.0; macOS; brand-font AE build; LTR progress bar; fallback-script unsaved refusal | **unverified** |

---

## 9. Performance (60–90-minute episode)

| Stage | What happens | Cost for 90 min | Opportunity |
|---|---|---|---|
| episode-transcribe | 10-min chunks, sequential, VAD on, beam 5, **4 CPU threads**, no batching (episode.py:412-481, transcribe.py:54-78) | GPU about 7 min; CPU about 108 min by the engine's own estimate (episode.py:179-180). Apple Silicon is CPU-bound | `cpu_threads=os.cpu_count()`. `BatchedInferencePipeline(batch_size=8-16)` on CUDA (about 3× in faster-whisper's benchmarks). Two chunk workers on many-core CPUs (`num_workers=2` + thread pool). MLX backend on macOS. Offer `large-v3-turbo` for the first pass and large-v3 relisten on flagged words |
| finalize → `document_quotes` | For every quote in client docs, `SequenceMatcher` over every window of the full word list ×3 lengths (transcribe.py:304-347) | O(quotes × 13k words × 3): roughly 1 s per quote, so tens of seconds to minutes for a long reels-plan doc, repeated on every `transcript-correct` | Pre-filter windows by rare-token overlap, or index tokens → candidate positions |
| discovery / inbox | `sha1_head` reads 8 MB per file plus parses every PDF/DOCX on **every** `inbox` call (discover.py:191-210). It also imports faster_whisper to audit modules (discover.py:178) | Seconds per call, more on a NAS | Cache by (path, size, mtime) like the probe cache; skip the module audit in inbox |
| reels-preview | One ffmpeg encode per candidate, sequential (reels.py:335-393) | 30-40 candidates × 5-10 s = 3-6 min | ThreadPool of 3-4 ffmpeg jobs (thumbnail_candidates already does this, publish.py:181) |
| Long single clip (not episode) transcribe | One Whisper pass, no VAD, no checkpoints (transcribe.py:130-135) | As above, but a crash loses everything; hallucination risk on long silences | Reuse the episode chunk runner for any clip over 10 min |
| audio-clean on a long clip | Whole file in float32 arrays (raw 48k stereo ≈ 2 GB for 90 min, plus copies), `evidence()` re-reads raw; `verify_cuts` runs **Whisper twice** over the whole clip (audio_clean.py:311-409) | Multi-GB RAM; cut proof ≈ 2× transcription time | Stream in blocks (ffmpeg does the filtering already); for the cut proof, check only ±3 s around each cut, not whole chunks |
| preflight shot analysis (long raw 16:9) | Decode at 2 fps + Haar per sample + histograms in Python lists (media.py:105-155) | 10.8k samples: a few minutes, 250+ MB | NumPy arrays; detect faces only every Nth sample, using the histogram for the rest |
| preview-video | Python/PIL composite per output frame (preview_video.py:226-279) | Fine for reels (1-3 min); 90 min at 24-30 fps ≈ 130-160k frames ≈ 1-2 h | Render N segments in parallel processes and concat; or build an ffmpeg `overlay` graph with `enable='between(t,a,b)'` |
| Premiere build of long-form | Every caption cue is two PNGs placed one by one through ExtendScript | Thousands of clips for 60 min, which is slow in Premiere and clutters tracks | Use the native caption track (`native_caption_track`) for long-form |

---

## 10. Security and safety

- **Client source protection.**
  - The engine never writes into `assets/` or `data/`. `scaffold` only creates empty folders, refuses if any file
    exists (onboard.py:145-165), and writes everything else to `output/`.
  - `hooks/guard.py` enforces read-only `assets/` and `data/` for Write/Edit/Bash/PowerShell, blocks deleting project
    folders, blocks Adobe preference writes (PlayerDebugMode, After Effects prefs), and enforces role rules.
  - **IM-17 (Important): the guard fails open.**
    - `hooks/run_python.sh` exits 0 with only a stderr note when no Python 3.8+ is on PATH (lines 5-11). On a machine
      where Python isn't on PATH, all protections are silently off. *Fix:* fall back to the engine venv python
      (`$WHYNOT_HOME/venv/...`) before giving up, and have `session_context` warn loudly when the guard cannot run.
    - Documented limit: writes from inside interpreters (`python -c`, scripts) are not inspected (guard.py:13-14).
    - Role holes found by the CLI audit:
      - `transcript-verify --by editor` is allowed for subagents.
      - qc-reviewer can run `ref-analyze`, which applies the client style (cli.py:254-258) and so gets around the
        `ref-style --apply` block.
      - setup-doctor's "never run `reel setup`" is prose only.
      - `cmd /c reg add …` or `powershell -Command "Set-ItemProperty …"` from Bash bypasses the PlayerDebugMode rule.
- **Shell or code injection through file names.**
  - All subprocess calls use argv lists. There is no `shell=True`.
  - ExtendScript payloads are ASCII-escaped JSON (`ensure_ascii=True`; bridge `JSON.stringify` for the script path).
  - XML names are `escape()`d, and `pathurl` is percent-encoded.
  - PowerShell for Photoshop doubles single quotes (adobe_run.py:57-58).
  - **Remaining sink (Minor):** AppleScript `tell application "…" to DoScriptFile "{jsx}"` /
    `do javascript file (POSIX file "{jsx}")` (adobe_run.py:33, 54). A `"` in the client folder path ends the string,
    and `& do shell script "…"` would run. *Fix:* `osascript -e 'on run argv' -e 'tell application (item 1 of argv) to
    DoScriptFile (item 2 of argv)' -e 'end run' <app> <path>`.
- **Bridge trust boundary.**
  - The panel evaluates only scripts under `<engine home>/<app>-scripts` (realpath check, bridge.js:81-88). The queue
    and scripts folders are chmod 0700 on macOS; that is a no-op on Windows, but the profile ACLs are private.
  - Any process running as the user can queue a whitelisted action with arbitrary data (for example save a project
    anywhere). That is acceptable for a same-user threat model.
  - **PlayerDebugMode=1 lets every unsigned CEP extension load, for all of CSXS 11-14.** This is a global weakening of
    Adobe's extension signing. *Fix (Important for agencies):* ship a signed ZXP (ZXPSignCmd, self-signed certificate)
    so PlayerDebugMode is not needed, and say clearly what the setting does until then.
- **Credentials and secrets.**
  - None are used. Hugging Face downloads are anonymous. The NVIDIA download is HTTPS and sha256-verified against
    NVIDIA's manifest. pip uses PyPI without hashes (supply-chain risk, MI-21).
  - The preferences file is written 0600 (settings.py:106-109). No tokens are logged.
  - The user's email is not used anywhere in the engine.
- **Content safety.**
  - Gate 1 approval, the transcript-verified gate for flagged words on graphics (plan.py:568-580), document-quote checks,
    publish link/quote verification (publish.py:400-407) and CC-BY attribution checks all exist and are enforced in code.
  - The weak point is IM-3: approval does not cover camera and framing changes.

---

## Appendix — suggested fix order

1. CR-1 clip identity (+ tests), CR-2 executable bits (+ mode test), IM-3 approval fingerprint (+ test).
2. IM-1/IM-2 self-contained venv + `reel setup` that actually repairs (+ doctor version/origin check).
3. IM-7 top-level error handler, BOM-safe `read_json`, exit codes, field validation before use; IM-10 SFX kinds.
4. IM-4/IM-5/IM-6 bridge: job expiry/cancel, cleanup, claim-based timeouts, a build lock, version warning, media-pending
   retry.
5. IM-8 folder-first discovery, IM-9 native-build handoff, IM-11 locking writes.
6. IM-12/IM-15 macOS fonts and Adobe discovery overrides; add a macOS CI job (§7.3 item 7).
7. IM-13/IM-14 performance (threads, batching, chunked long-clip transcription, MLX on Apple Silicon).
8. The Minor items, in passing.
