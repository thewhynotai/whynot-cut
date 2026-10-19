# OPS-06 — Effort per tier in helper runs

- **Assigned:** see BOARD    **Status:** READY    **Tier:** LIGHT    **Milestone:** M0

## Goal
Owner rule (Yunus via the plan session 2026-10-19 ~21:00): HIGH-tier work runs at effort high; LIGHT tier, coordination, monitoring and setup at medium; independent reviews of HIGH items stay high. Apply it in `D:\ClaudeDataccounts\helper_loop.py` (pass the effort for the card's tier) and add one line to PLAYBOOK §4. The 00-HQ chat could not do it (usage limit).

## Acceptance
1. Unit test in test_helper_loop.py: HIGH card → high, LIGHT/SETUP → medium, peer review of HIGH → high.
2. test_helper_loop.py all pass.
3. Change applied only between helper runs (never kill a running run).

## Evidence
(filled at close)
