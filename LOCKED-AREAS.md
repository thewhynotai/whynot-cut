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
  - `whynot-cut/engine/reel/lib/looks*.py`, `whynot-cut/engine/reel/lib/cut_proposals*.py`
  - `whynot-cut/config/defaults/looks/**`
  - `whynot-cut/skills/motion-craft/references/motion-scenes.md`
  - `tools/identity_scan.py`, `tools/identity_hashes.json`
  - `whynot-cut/tests/test_looks*.py`, `whynot-cut/tests/test_motion_library*.py`, `whynot-cut/tests/test_cut_proposals*.py`,
    `whynot-cut/tests/test_identity_scan*.py`
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
