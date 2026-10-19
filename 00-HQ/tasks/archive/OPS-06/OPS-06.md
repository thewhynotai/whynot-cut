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

## Closure (2026-10-20 02:12) — DONE_ARCHIVED
- Change: `D:\ClaudeData\accounts\helper_loop.py` (+ `effort_for_run`, `review_effort`, `--effort` on every run, next-effort cleared on IDLE, prompt line); backup before the change: `helper_loop.py.bak-ops06`. PLAYBOOK §4 line "Effort follows the tier".
- Tests: `test_helper_loop.py` 9 new OPS-06 checks (red first each round) → **30/30 PASS** ("FAILED: none").
- Review: `reviews/OPS-06-r1.md` PASS-WITH-MINORS → P2-1 (stale medium after IDLE) and P2-2 (PLAYBOOK path) fixed with tests; P3-1 prompt wording fixed.
- Rollout: live loops load it between runs through `RELOAD-h1` (H1) and at the next start (H2); no running run was stopped.
- Known limit (P3-3): the effort is chosen at the end of the previous run, so a FIX round posted after that runs at the guessed effort (HIGH cards are still reviewed at high).
