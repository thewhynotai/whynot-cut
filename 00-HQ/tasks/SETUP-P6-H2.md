# SETUP-P6-H2 — independent check of H1's seat report (AI-infra restart Phase 6)

- **Assigned:** H2    **Model:** Sonnet 5.5 (effort medium)    **Size:** S    **Status:** NOT READY (the master sets READY when SETUP-P6-H1 is DONE)
- **Tier:** LIGHT (read-only verification; no product code)
- **Stage / gate:** AI-infra restart Phase 6    **Depends on:** SETUP-P6-H1 (its DONE report in `00-HQ/inbox/h1/`)

## Goal
Independently verify, from your own seat, the facts H1 reported in `00-HQ/inbox/h1/2026-10-22-SETUP-P6-H1.md`, and
report your own seat's state the same way. This is the H1 → H2 verification leg of the handoff test.

## Fence
- your report file `00-HQ/inbox/h2/2026-10-22-SETUP-P6-H2.md` only. No commit, no branch, no push.

## Steps (read-only; no suites, no heavy jobs)
1. If H1's report does not exist yet: write a report with status **BLOCKED**: "waiting for SETUP-P6-H1 DONE" and stop.
2. Re-run, from your seat, H1's checks that you can see: `git -C D:\WNC-work\h1 rev-parse --abbrev-ref HEAD`,
   `git -C D:\WNC-work\h1 rev-parse --short HEAD`, `git -C D:\WNC-work\h1 rev-parse --short release/3.0`. Compare with
   H1's report: MATCH / MISMATCH per line.
3. Your own seat: `$WHYNOT_HELPER`, `git -C D:\WNC-work\h2 rev-parse --abbrev-ref HEAD`, `--short HEAD`,
   `status --short | wc -l`; which `gstack-*` / `oh-my-claudecode:*` skills your session lists (install nothing).
4. Read `00-HQ/AGENT_ROUTING_RULES.md` §1 and quote which system owns task status.
5. Write the report with status **DONE**, the comparison table and your outputs verbatim, and the time. Then IDLE.

## Acceptance
- [ ] report exists, every H1 claim marked MATCH / MISMATCH with the evidence line
- [ ] no other file changed

## Pre-mortem
- If H2 runs before H1 finishes: step 1 (BLOCKED, then the master re-marks READY). Other H2 cards are PARKED for Phase 6.

## Live checks needed
- none
