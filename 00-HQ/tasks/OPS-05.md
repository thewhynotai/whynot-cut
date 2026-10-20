# OPS-05 — First observed cross-account cycle

- **Assigned:** see BOARD    **Status:** IN_PROGRESS    **Tier:** LIGHT    **Milestone:** M0

## Goal
Observe, do not simulate: H1 delivers a DONE card → H2's loop writes a valid peer review → the hourly intake decides → MERGE-QUEUE → the executor merges → GitHub SHA. Record each artefact (report mtime, review file, verdict, merge sha, remote sha) in this card.

## Acceptance
1. Every step has a file or SHA as evidence.
2. If a step fails, the failure and the fix are recorded; the cycle is repeated until it passes once end to end.

## Evidence (observed, not simulated; 2026-10-20 12:58)
1. H1 (mayar@ seat) DONE report `inbox/h1/2026-10-19-BL-16.md` 23:29, branch `h1/BL-16` @ 3f3b9bb (author "Mayar (WhyNot Helper 1)").
2. H2 (marketing@ seat) peer review from its own AUTO loop: `reviews/BL-16-peer-h2-20261020-0522.md` (report-mtime matches, reviewer h2, sha 3f3b9bb, full suite line, verdict FAIL with findings).
3. Master intake (info@ seat, routine run): own Opus review `reviews/BL-16-r1.md` 08:23 → card `## FIX round 1 (2026-10-20 08:24)`; state.json verdict `FIX r1`.
4. H1 picked the FIX up (BOARD row BL-16 = FIX; H1 AUTO running).
Still open to close: FIX delivery → valid review → ACCEPTED → MERGE-QUEUE → executor merge sha on release/3.0 → remote SHA after the executor's push.
