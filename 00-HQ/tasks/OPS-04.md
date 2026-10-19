# OPS-04 — Move 00-HQ into the repo and fix references to archived docs

- **Assigned:** see BOARD    **Status:** NOT READY (after the v3.0.0-p4 tag)    **Tier:** LIGHT    **Milestone:** M0

## Goal
Planned since 10-19: at the Gate 4 tag 00-HQ moves into the repo. Update helper_loop.py, the intake task and Start-Helper paths in the same change; fix the 3 references in the master roadmap (lines 29, 73) and V1 spec (lines 8, 10) to `_archive/plans-2026-10/…`; retire the ops/hq mirror or keep it as history.

## Acceptance
1. Helpers and intake read the new paths (one dry run each).
2. No dangling reference (grep).
3. ops/hq decision recorded in DECISIONS.md.

## Evidence
(filled at close)
