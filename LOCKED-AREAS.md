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
  safe zones, look recommender):
  - `docs/superpowers/specs/addendum-h/source-r-specs/**`
  - `whynot-cut/templates/after_effects/wnc_motion_lib.jsx`, `whynot-cut/engine/reel/lib/motion_library.py`
  - `whynot-cut/engine/reel/lib/looks*.py`, `whynot-cut/engine/reel/lib/cut_proposals*.py`,
    `whynot-cut/engine/reel/lib/safe_zones*.py`
  - `whynot-cut/config/defaults/looks/**`, `whynot-cut/config/defaults/safe-zones.json`
  - `whynot-cut/skills/motion-craft/references/motion-scenes.md`
  - `tools/identity_scan.py`, `tools/identity_hashes.json`
  - `whynot-cut/tests/test_looks*.py`, `whynot-cut/tests/test_motion_library*.py`, `whynot-cut/tests/test_cut_proposals*.py`,
    `whynot-cut/tests/test_safe_zones*.py`, `whynot-cut/tests/test_identity_scan*.py`
