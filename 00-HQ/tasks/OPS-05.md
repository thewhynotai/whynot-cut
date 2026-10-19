# OPS-05 — First observed cross-account cycle

- **Assigned:** see BOARD    **Status:** NOT READY (needs ENV-01)    **Tier:** LIGHT    **Milestone:** M0

## Goal
Observe, do not simulate: H1 delivers a DONE card → H2's loop writes a valid peer review → the hourly intake decides → MERGE-QUEUE → the executor merges → GitHub SHA. Record each artefact (report mtime, review file, verdict, merge sha, remote sha) in this card.

## Acceptance
1. Every step has a file or SHA as evidence.
2. If a step fails, the failure and the fix are recorded; the cycle is repeated until it passes once end to end.

## Evidence
(filled at close)
