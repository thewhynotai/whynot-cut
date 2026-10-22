# SETUP-P6-H1 — seat check + handoff test (AI-infra restart Phase 6)

- **Assigned:** H1    **Model:** Sonnet 5.5 (effort medium)    **Size:** S    **Status:** READY
- **Tier:** LIGHT (read-only seat check; no product code)
- **Stage / gate:** AI-infra restart Phase 6 (`00-HQ/setup/SETUP_PHASE_TRACKER.md`)    **Depends on:** none

## Goal
Prove that a card handed out by the master (main account) reaches your seat, that you can read the shared project
records, and report the true state of your environment, so `00-HQ/ACCOUNT_STATUS.md` holds verified facts.

## Fence (the ONLY paths this task may change)
- your report file `00-HQ/inbox/h1/2026-10-22-SETUP-P6-H1.md`. Nothing in the repo, no commit, no branch, no push.

## Steps (read-only; one Bash call per item, no suites, no heavy jobs)
1. `echo %WHYNOT_HELPER%` (or `$WHYNOT_HELPER`), `git -C D:\WNC-work\h1 rev-parse --abbrev-ref HEAD` and `git -C D:\WNC-work\h1 rev-parse --short HEAD`, `git -C D:\WNC-work\h1 status --short | wc -l`.
2. The release branch you would start from: `git -C D:\WNC-work\h1 rev-parse --short release/3.0`.
3. Which tools your session sees: do you have any skill named `gstack-*` or `oh-my-claudecode:*`? (List what your session lists; do not install anything.)
4. `bash C:/Users/LOQ/AppData/Roaming/Claude/side-session-notes/local_263cabbf-75e3-42a1-b384-1753a7bd4dad/heavy.sh status` (first 15 lines).
5. Read `00-HQ/AGENT_ROUTING_RULES.md` and quote, in one line, which system owns task status.
6. Write the report (template `00-HQ/templates/UPDATE-REPORT.md`) with status **DONE**, the outputs above verbatim,
   and the time. Do NOT write anything else. Then, per your loop rules, there is no other card for you: write IDLE.

## Acceptance
- [ ] report exists with all 5 outputs, the run time, and status DONE
- [ ] no file changed anywhere else (`git status` of your worktree unchanged)

## Pre-mortem
- Will it work: yes, read-only. Risk: the loop picks another card first → all other H1 cards are PARKED for Phase 6.
- Holes: none known.

## Live checks needed
- none
