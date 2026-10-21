# OPS-05 — First observed cross-account cycle

- **Assigned:** see BOARD    **Status:** DONE_ARCHIVED (2026-10-21 13:05)    **Tier:** LIGHT    **Milestone:** M0

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
5. H1 FIX delivery `inbox/h1/2026-10-21-BL-16.md` 00:52, branch `h1/BL-16` @ 37cc841.
6. H2 peer review from its own loop: `reviews/BL-16-peer-h2-20261021-0122.md` (03:31), verdict PASS-WITH-MINORS.
7. Intake verdict ACCEPTED 2026-10-21 03:39 (`intake/state.json`, key `inbox/h1/2026-10-21-BL-16.md`) → MERGE-QUEUE line written.
8. Executor merge on release/3.0: `890b144` (merge of 37cc841) + patch 1 `7db98a5` (366 focused OK), 2026-10-21 12:25;
   MERGE-QUEUE line ticked `[x]`; BOARD BL-16 = MERGED. Patch 2 goes to ADOBE-G4 (its own sha later).

## Result (2026-10-21 13:05)
The full cross-account cycle ran end to end with no human step, including one FAIL → FIX → re-review round, and it
survived three usage limits on the master seat. **Known limit:** the remote SHA is not on GitHub yet: the executor
pushes `release/3.0` only at the `v3.0.0-p4` tag (GitHub is at 322d8a5, local is 104 commits ahead). That check moves
to OPS-04 (after the tag): confirm `890b144` is reachable from the remote `release/3.0`.
