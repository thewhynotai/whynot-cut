# Locked areas (two-machine rule)

The Windows side is changing these paths in the current phase. The Mac side (branch `mac/dev`) **never edits,
moves, renames, deletes or reformats** anything that matches a pattern below, not even a one-line fix.

If a Mac bug lives in a locked path:
1. Don't touch the file.
2. Write a `MAC-INBOX.md` entry with the repro, the evidence and the proposed fix (as a diff in a fenced block).
3. Set the entry's Status to `needs Windows fix`.

The Windows side applies the fix and marks the entry done.

The Windows executor updates this list at every phase boundary. `tools/release.py handoff` copies it into the Mac
`START-HERE.md`. Patterns are git pathspec globs, relative to the repo root (`**` = any depth).

## Locked now

Phase 4 (from 2026-10-16, after Gate 3 / v3.0.0-p3.1):

- `whynot-cut/engine/reel/**`: executor, engine core (Phase 4); except the track-owned paths below
- `whynot-cut/hooks/**`: executor
- `whynot-cut/skills/**`: executor; except the track-owned skills below
- `whynot-cut/evals/**`: executor; except the track-owned evals below
- `whynot-cut/config/defaults/**`: executor
- `adobe/**`: Adobe track; except `adobe/tools/**`
- `whynot-cut/engine/reel/serve/**`: Adobe track
- `whynot-cut/installer/**`: installer track
- `installer/app/**`: installer track (E-T1, Tauri app + UI bundle)
- `guide-ar/**`: guide track
- tools track (Kalam, Hush, Tidy, G-ALIGN):
  - `adobe/tools/**`
  - `whynot-cut/engine/reel/lib/kalam*.py`, `whynot-cut/engine/reel/lib/hush*.py`, `whynot-cut/engine/reel/lib/tidy*.py`,
    `whynot-cut/engine/reel/lib/align_w2v*.py`
  - packages: `whynot-cut/engine/reel/lib/kalam*/**`, `whynot-cut/engine/reel/lib/hush*/**`,
    `whynot-cut/engine/reel/lib/tidy*/**`, `whynot-cut/engine/reel/lib/align_w2v*/**`
  - `whynot-cut/skills/kalam/**`, `whynot-cut/skills/hush/**`, `whynot-cut/skills/tidy/**`
  - `whynot-cut/evals/kalam-*/**`, `whynot-cut/evals/hush-*/**`, `whynot-cut/evals/tidy-*/**`
  - `whynot-cut/tests/test_kalam*.py`, `whynot-cut/tests/test_hush*.py`, `whynot-cut/tests/test_tidy*.py`,
    `whynot-cut/tests/test_align_w2v*.py`
- looks & motion track (Addendum H rebuild: R-T1 specs, R-T6 identity scan, caption looks, AE scenes, cut proposals,
  look recommender; safe zones moved to the API-credit lane 2026-10-17, see below):
  - `docs/superpowers/specs/addendum-h/source-r-specs/**`
  - `whynot-cut/templates/after_effects/wnc_motion_lib.jsx`, `whynot-cut/engine/reel/lib/motion_library.py`
  - `whynot-cut/engine/reel/lib/looks*.py` (cut_proposals moved to API-credit lane 2 on 2026-10-17, see below)
  - `whynot-cut/config/defaults/looks/**`
  - `whynot-cut/skills/motion-craft/references/motion-scenes.md`
  - `tools/identity_scan.py`, `tools/identity_hashes.json`
  - `whynot-cut/tests/test_looks*.py`, `whynot-cut/tests/test_motion_library*.py`, `whynot-cut/tests/test_identity_scan*.py`
  - `tools/identity_scan.py`: the release-gate modes (`--git`, `--archives`) are executor hunks (2026-10-17)
- Phase 4 fan-out (2026-10-16, executor rules and commits stay with each track):
  - Adobe track, T4.1 smooth zoom/fades + T4.6 motion music:
    - `whynot-cut/engine/reel/lib/ppro_build.py`, `whynot-cut/engine/reel/lib/motion_audio.py`,
      `whynot-cut/engine/reel/lib/motion_build.py`
    - `whynot-cut/tests/test_t41*.py`, `whynot-cut/tests/test_t46*.py`
  - wnc-queue track, T4.4 episode sheet + T4.5 portable client database + T4.9 adopt old styles:
    - `whynot-cut/engine/reel/lib/episode_sheet*.py`, `whynot-cut/engine/reel/lib/client_db.py`,
      `whynot-cut/engine/reel/lib/client_move*.py`, `whynot-cut/engine/reel/lib/ref_style.py`
    - `whynot-cut/tests/test_t44*.py`, `whynot-cut/tests/test_t45*.py`, `whynot-cut/tests/test_t49*.py`
  - `whynot-cut/engine/reel/cli.py` stays the executor's; each track commits only its own subcommand hunks
  - Adobe track, extra grants (2026-10-17): T4.1 `lib/camera_ease.py` (new), `templates/premiere/wnc_ppro_lib.jsx`,
    `contract/build_project.schema.json`, premiere-craft skill text; after the T4.2 commit also `lib/plan.py`,
    `config/defaults/style.json` + the profile style schema, client-craft SKILL.md, story-craft edit-decision-engine.md
    (hunks only). T4.6 `lib/motion_plan.py`, `templates/after_effects/wnc_ae_bridge.jsx`, `lib/motion_readback.py`,
    `schemas/motion-script.schema.json`, `lib/recipes.py`, `lib/podcast_cli.py` (cmd_music), `lib/handoff.py` (music
    line), the motion skill/agent text (hunks only); `wnc_motion_lib.jsx` WNCM.audio hunk only, agreed with looks first.
  - Addendum J track (2026-10-17), J-T1…J-T5 (Tasks 31–35): `whynot-cut/engine/reel/lib/brand_web/**`,
    `whynot-cut/engine/reel/lib/linksafe.py` (shared later with L-T8 / Task 15), `tools/build_open_fonts_index.py`,
    the open-fonts index data file, `schemas/brand-candidates*.json`, `whynot-cut/tests/test_j*.py`,
    `whynot-cut/tests/fixtures/brand_web/**`; cli.py `brand-fetch` + `scaffold --fill-missing` hunks only.
    J-T6…J-T8 paths are granted when Tasks 7 + 8 land. `requirements.txt` / locks stay the executor's (Task 12).
  - API-credit lane (2026-10-17, moved from the looks track; brief + ASSIGNMENT.md in `D:\ClaudeData\claude-api-lane\`),
    Task 27 R-4.5 safe-zone profiles: `whynot-cut/engine/reel/lib/safe_zones*.py`,
    `whynot-cut/config/defaults/safe-zones.json`, `whynot-cut/tests/test_safe_zones*.py`,
    `whynot-cut/tests/fixtures/safe_zones/**`, `docs/superpowers/evidence/2026-10-17-safe-zones-sources.md`.
    Hooks in qc.py / motion_readback.py / previews.py / cli.py arrive as patches; the executor applies and pushes.
  - API-credit lane 1, assignment 2 (2026-10-17): T4.11 lean runtime + T4.14 transcription precision + Task 24 R-4.2
    burned-in captions, in that order, after the T4.10 commit: new `lib/priority.py`, `lib/wer.py`,
    `lib/burned_captions.py`; hunks in `lib/settings.py`, `lib/whisper_backends.py`, `lib/transcribe.py`,
    `config/defaults/transcription.json` (gpu_compute_types), `tests/_isolation.py` (WHYNOT_PRIORITY line);
    `tests/test_lean_runtime.py`, `tests/test_transcribe_precision.py`, `tests/test_burned_captions.py`,
    `tests/fixtures/burned_captions/**`; the G13 evidence file. cli.py / plan.py / ppro_build.py / previews.py /
    intake hooks arrive as patches.
  - Addendum M (2026-10-17, M6): `whynot-cut/engine/reel/lib/bidi_lines.py` and `lib/client_brief.py` executor;
    `lib/looks_pairing.py` looks & motion track (covered by `looks*.py`); the `typography.pairing` field in
    `lib/client_db.py` wnc-queue (hunk only).
  - Safety track = API-credit lane 2 (2026-10-17, Addendum K1, Tasks 61–68): `whynot-cut/engine/reel/lib/safety/**`,
    `whynot-cut/tests/test_safety*.py`, `whynot-cut/tests/fixtures/safety/**`. `config/defaults/safety.json` (the K1
    switches) is executor-owned; cli.py / plan / reels-plan / qc call sites, skills, agents and hooks arrive as patches;
    K-T3's ppro_build fade goes to the Adobe track; K-T4's Task 27 delta goes as a patch to lane 1's `safe_zones*`.
  - API-credit lane 3 (2026-10-17, Addendum L Tasks 39, 40, 41, 48 = L-T1 scan kit, L-T2 secrets sweep, L-T3 security
    CI, L-T10 fuzzing Python part): `tools/security/**`, `.semgrep/**`, `.gitleaks.toml`,
    `.github/workflows/security.yml`, `docs/security/scan-*.md` + `docs/security/baseline*.json`,
    `whynot-cut/tests/security/fuzz/**`, `whynot-cut/tests/test_security_scan*.py`, `whynot-cut/tests/test_fuzz*.py`.
    `adobe/` devDependencies (ESLint security plugins) go to the Adobe track as a patch; `docs/ci.md` minutes table and
    any fix in another owner's file arrive as patches.
  - API-credit lane 2 also owns Phase 4 Task 25 R-4.3 cut proposals (2026-10-17, from the looks track; K-T7 builds on
    it): `whynot-cut/engine/reel/lib/cut_proposals*.py`, `whynot-cut/tests/test_cut_proposals*.py`,
    `whynot-cut/tests/fixtures/cut_proposals/**`; plan.py / ppro_build.py hooks arrive as patches.
  - API-credit lane queues (2026-10-17, owner strategy: lanes do the long heavy implementation until the Console credit
    is used up; the sessions keep design, ordering, acceptance and gates). Each lane commits only its own files,
    unpushed; the executor accepts and pushes; other owners' hunks arrive as patches.
    - Lane 1 adds, after Task 24: T4.10 Step 8 A/B (`SITE_LANES`/`VT_Q` values in `lib/accel.py` + their assertions,
      the G-GPU evidence file); Task 26 (`lib/media_normalise.py`, `tests/test_media_normalise*.py`,
      `tests/fixtures/media_normalise/**`); T4.12 (`setup/requirements-torch.in`, `setup/locks/runtime-*.txt`,
      `setup/requirements.txt` requested lines, `lib/runtime.py`, `setup/setup_env.py`, `lib/plat.py` cuda_lib_dirs,
      `tests/test_runtime_locks.py`); T4.15 after `lib/linksafe.py` lands (`lib/housekeeping.py`,
      `tests/test_housekeeping.py`).
    - Lane 2 adds, after K1: Task 30 (`lib/publish_rules.py`, `tests/test_publish_rules*.py`,
      `tests/fixtures/publish_rules/**`); T4.3 after T4.2 (`lib/rules_loop.py`, `tests/test_t43_rules*.py`); Task 29
      after T4.1 (`lib/emphasis.py`, `lib/endings.py`, `tests/test_emphasis*.py`).
    - Lane 3 adds, after L-T1/2/3/10: L-T16 (`tests/security/files/**`, `tests/test_security_files*.py`); L-T6 v1
      (`tests/security/injection/**`, `tests/test_security_injection*.py`, `evals/security/**`); L-T4 audit
      (`tests/test_security_bare_exe.py`, `docs/security/scan-bare-exe.md`); L-T17 read-only record
      (`docs/security/scan-acl-thispc.md`).
    - Lane 4 (new) = Addendum M Gate 4 list, Tasks 50–60: `lib/review_domains*.py`, `lib/review_flags.py` (handed over
      for M1-T2), `lib/bidi_lines.py`, `lib/font_pairing.py`, `lib/client_brief.py`, `lib/brief.py`,
      `lib/transcript_compact.py`, `config/review-domains/**`, `tests/test_review_domains*.py`, `tests/test_review_flags.py`,
      `tests/test_bidi_lines*.py`, `tests/test_font_pairing*.py`, `tests/test_brief.py`, `tests/test_client_brief.py`,
      `tests/test_transcript_compact*.py`, fixtures `tests/fixtures/{review_domains,bidi,brief}/**`,
      `evals/review-domains/**`, `evals/model-tier/**`, the M2/M5 evidence files.
