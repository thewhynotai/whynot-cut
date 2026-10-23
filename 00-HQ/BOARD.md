# BOARD — the only task list (edited by the MASTER only)

Updated 2026-10-20 02:00 (Cairo, Command Center: ENV/OPS/API rows). Stage 1 = Gate 4 (≈ 55%).
Machine view (generated, read-only): `TASK_QUEUE.yaml`. Owner view: `..\PROJECT_PLAN_AR.md`.

**Transition rule.** The chats already running on Yunus's account keep their charters until they END (TRACKS.md).
New work goes to H1, H2 or LANE through this board. No new track chat opens on Yunus's account. While the old
system still runs, every item a helper takes also gets a claim file `D:\ClaudeData\claude-api-lane\claims\<ID>.claim`,
so the old builders and lanes see the fence.

Status words: NOT READY · READY · IN PROGRESS · FIX · ACCEPTED · MERGED · BLOCKED · PARKED · RUNNING (old-system track).

## Helpers and lanes (new system)
**Queue rule:** every helper always holds 3 READY cards that don't depend on each other. A helper works through
them one after another until its own limit, and never waits for a review. Reviews are peer reviews (H1 reviews
H2's code and the other way round, PLAYBOOK §3c). The master intake decides each one and refills the queue.

| ID | Title | Assigned | Status | Card | Next |
|---|---|---|---|---|---|
| SETUP-P6-H1 | Seat check + handoff test (AI-infra restart Phase 6, LIGHT, read-only) | H1 | ARCHIVED (not run; superseded by the BL-20 pilot) | `tasks/SETUP-P6-H1.md` | — |
| SETUP-P6-H2 | Independent check of H1's seat report (Phase 6, LIGHT, read-only) | H2 | ARCHIVED (not run; superseded by the BL-20 pilot) | `tasks/SETUP-P6-H2.md` | — |
| SETUP-H1 | First login (mayar@) + full suite baseline | H1 (Mayar) | ACCEPTED — closed, no code (nothing to merge) | `tasks/SETUP-H1.md` | r3 2026-10-20 08:26: 8226 run, 51 env/timing; ENV-01 gaps routed |
| BL-16 | Safe ASCII engine home for a non-ASCII Windows user (Gate 4, high) | H1 | MERGED (890b144 + patch 1 7db98a5, 2026-10-21 12:25; patch 2 at ADOBE-G4) | `tasks/BL-16.md` | merged by executor |
| BL-02 | Licence files, notices generator, SPDX tool (tool only) (Gate 4, high) | H1 | FIX (round 1, 2026-10-23 06:21; master r2 PASS-WITH-MINORS, 2 P2: verify P35–P47 licence rows; §7 cuBLAS → Yunus) | `tasks/BL-02.md` | review `reviews/BL-02-r2.md`; suite 8830, no new failure |
| S6b | Gate 4 eval cases for the Phase 4 skills (LIGHT) | H1 | DONE_ARCHIVED (2026-10-23 05:50; merged f3995f9, on origin; macOS CI green on abdece5, run 39887611913) — was: ACCEPTED (2026-10-23 03:05) | `tasks/archive/S6b/S6b.md` | peer h2 PASS-WITH-MINORS (no P1/P2) on d6f9a3b → MERGE-QUEUE |
| BL-17 | Second install must not overwrite the first install's pointer files (Gate 5) | H1 | READY (restored 2026-10-23 03:02 after the restart hold) | `tasks/BL-17.md` | — |
| BL-19 | Root-normalised fingerprints, so a client move keeps its approvals (Stage 2) | H1 | READY (restored 2026-10-23 03:02 after the restart hold) | `tasks/BL-19.md` | — |
| S1-R51 | Installer r5_1: the engine-home drift test says which list to edit (Gate 4 exit prep, LIGHT) | H1 | READY (restored 2026-10-23 03:02 after the restart hold) · fallback executor 28 Oct | `tasks/S1-R51.md` | new card 2026-10-21 (intake top-up) |
| SETUP-H2 | First login (marketing@) + full suite baseline | H2 (marketing@) | ACCEPTED — closed, no code (nothing to merge) | `tasks/SETUP-H2.md` | r1 2026-10-20 11:40: 8753 run, 77 env/timing (ENV-01 classes); npm ci + 296 panel tests + 1 render OK |
| BL-03 | GPL-compliance + trademark notice templates (AR + EN) (Gate 4) | H2 | DONE_ARCHIVED (2026-10-23 05:50; merged abdece5, on origin; macOS CI green on abdece5, run 39887611913) — was: ACCEPTED (2026-10-21 22:40) | `tasks/archive/BL-03/BL-03.md` | peer h1 PASS (none) on ca8c783 → MERGE-QUEUE |
| BL-04 | run-state.json + resume, preflight-first in `reel next` (Gate 4) | H2 | FIX (round 1, 2026-10-22 21:07; peer h1 FAIL: 2 P2, mutation 6/6) · fallback executor 25 Oct | `tasks/BL-04.md` | DONE 2026-10-22 03:16 (fab930b + 4 patches) → peer FAIL → FIX round 1 |
| BL-20 | Gate check: no temporary dated skips in the suite (`tools/skip_audit.py`) (Gate 4 exit, LIGHT, S) | H2 | DONE_ARCHIVED (2026-10-23 05:50; merged 032ff99, on origin; macOS CI green on abdece5, run 39887611913) — was: ACCEPTED (2026-10-23 04:54; FIX round 1 → peer h1 round 2 PASS-WITH-MINORS on 71a1a65, 0 P1/P2; Phase 6 + 7 pilot) | `tasks/archive/BL-20/BL-20.md` | peer h1 PASS-WITH-MINORS (P3-1..3, gate text decided) on 71a1a65 → MERGE-QUEUE |
| BL-27 | Gate 4 skip register: a written reason for each of the 202 "unknown" skips (Gate 4 exit, LIGHT, M, read-only) | EXECUTOR | REVIEW (executor DONE 23:07: register 200 rows at abdece5 + 5 NEW at 5c2d7b3c; master fresh review started 23:35) | `tasks/BL-27.md` | report + register in `inbox/executor/`; one fresh review (LIGHT) |
| BL-22 | AE build warnings reach NEEDS-YOU: a missing logo or image becomes a checklist line (Stage 2, LIGHT) | H2 | READY (restored 2026-10-22 21:07 after the restart hold) · fallback executor 28 Oct | `tasks/BL-22.md` | — |
| BL-29 | The motion animatic refuses a stale plan too (new `lib/motion_stale.py` + motion_animatic patch) (Gate 4, LIGHT, S) | H2 | READY (2026-10-23 22:50, intake top-up) · fallback executor 30 Oct | `tasks/BL-29.md` | new card 2026-10-23 (intake top-up) |
| S1-SA2 | skip_audit: in-body machine skips class as platform/tool, not unknown (Gate 4 exit tooling, LIGHT, S/M) | H2 | READY (2026-10-23 22:50, intake top-up) · fallback executor 30 Oct | `tasks/S1-SA2.md` | new card 2026-10-23 (intake top-up) |
| BL-18 | Two wrong fix lines in installer/onboarding (Gate 4) | EXECUTOR (done) | MERGED (f2ca516 on release/3.0, 2026-10-20) | `tasks/BL-18.md` | H2 does NOT take it |
| BL-14 | Portable client copy | EXECUTOR | MERGED (API-200 closed it: 5 commits + executor hooks 7f0c00a; `tracks\API-200-BL-14-HANDOVER.md`) | — | not a card |
| (lane 1) | API lane 1 | — | STOPPED (owner budget ruling 10-19 10:03); BL-16 and BL-04 moved to cards above | — | — |
| STAGE3-DRAFTS | Stage 3 task specs (F1, F10, F11 skeleton) as drafts | MASTER | NOT READY (after the Gate 4 tag / 1 Nov) | — | becomes H1/H2/LANE cards |
| ENV-01 | Engine runtime for unsandboxed processes (helper suites: 563 env errors) | MASTER | DONE_ARCHIVED (16:23; helper full suite 8899 OK, 0 fail) | `tasks/archive/ENV-01/ENV-01.md` | — |
| OPS-01 | Status generator, Arabic reports, ops/hq GitHub mirror (pilot task) | MASTER | DONE_ARCHIVED (02:00, 25/25 tests, 2 reviews) | `tasks/archive/OPS-01/OPS-01.md` | OPS-02 |
| OPS-02 | Schedule the 4 daily PRIMARY reports + delivery receipt test | MASTER | DONE_ARCHIVED (17:10; runs 13:03 + 17:03 SENT unattended; ACK → Q-006) | `tasks/archive/OPS-02/OPS-02.md` | — |
| OPS-03 | Fold the release-preview refresh check into the report run; retire lane-watch | MASTER | DONE_ARCHIVED (02:20, 28/28, review r1) | `tasks/archive/OPS-03/OPS-03.md` | — |
| OPS-04 | After the tag: move 00-HQ into the repo; fix 3 repo references to archived docs; confirm BL-16 merge 890b144 is on remote release/3.0 (OPS-05) | EXECUTOR | NOT READY (after the v3.0.0-p4 tag) | `tasks/OPS-04.md` | — |
| OPS-05 | First observed cross-account cycle: H1 DONE → H2 peer review → intake verdict | MASTER (observe) | DONE_ARCHIVED (13:05; BL-16 merged 890b144 + 7db98a5; remote SHA → OPS-04) | `tasks/archive/OPS-05/OPS-05.md` | — |
| OPS-06 | Effort per tier in helper runs (HIGH → high, LIGHT/setup → medium); owner rule 10-19 21:00 | MASTER | DONE_ARCHIVED (02:12, 30/30, review r1) | `tasks/archive/OPS-06/OPS-06.md` | — |
| OPS-07 | A usage-limit cut must not freeze the intake lock or the heavy queue (incident 10-20 03:54) | MASTER | DONE_ARCHIVED (06:15, 6/6 + sim, reviews r1/r2) | `tasks/archive/OPS-07/OPS-07.md` | — |
| OPS-08 | Main-account limit drain: long-lived sub-agents at 0.4-0.95M context (75% of 24 h use) | MASTER | DONE (2026-10-22 21:15 re-measure `reports/usage-2026-10-22-2115.md`: executor 61.6% -> 0.7%, no sub-agent over 250k continued) — was: IN PROGRESS (04:10: rule in PLAYBOOK §4; executor + Builder A told; executor adopted it, 5 big agents handed off to `D:\ClaudeData\claude-api-lane\handoffs\`) | `PLAYBOOK.md` §4; guard `tools/big_agents.py` (watchdog step 1c every 30 min; Agency LIVE shows `NNNk TOO BIG` in red) | owner 04:45: keep everything running; one-time task `whynot-cut-usage-remeasure-1000` re-measures at 10:00 -> `reports/usage-2026-10-22-1000.md`; close when no sub-agent over 250k is continued |
| OPS-09 | Parallel full suite `tools/test.sh --parallel N` (strict: every first-run failure counts), per-commit cache, heavy.sh `psuite`; then used everywhere | MASTER | DONE_ARCHIVED (2026-10-23 05:50; merged b81baaa, on origin; macOS CI green on abdece5, run 39887611913) — was: ACCEPTED (2026-10-23 03:00; equivalence run 4 on 302df0d = serial: Ran 9546, same 4 env failures, skipped 48, 28.1 min; Mac CI open until the push) | `tasks/archive/OPS-09/OPS-09.md` | → MERGE-QUEUE; suite-command switch after the merge |
| OPS-10 | heavy.sh: a psuite blocked only by RAM runs as a serial suite (queue blocked 4 h on 10-23) | MASTER | READY (start only with the heavy queue quiet) | `tasks/OPS-10.md` | stopgap rule in PLAYBOOK §2 since 09:55 |
| API-500 | The single paid API job (Stage 3 mechanical part) | LANE | PLANNED_NOT_AUTHORIZED (waits for «نفذ خطة الـ API») | `BUDGET-API.md` | — |

## Old-system tracks still running on Yunus's account (no change until their END)
| Track | Chat | Holds | Expected END |
|---|---|---|---|
| EXEC-G4 | Executor local_22b44953 | Tasks 25/26, T4.8, T4.15, manual verse slot, S1 reachability, gate review, push of the 25 commits, tag `v3.0.0-p4` | Gate 4 tag (~1–3 Nov) |
| BLD-A | K+M local_b32f950e | Tasks 50, 52–60, 53 non-verse, Task 29 | Gate 4 |
| BLD-B | L local_913e8afa | BL-15 r4, T4.3 final round, BL-01 | soon |
| ADOBE-G4 | Adobe local_f9018851 | T4.1, T4.6, .ccx rebuild, live checklist | Gate 4 |
| UI-P4 | UI local_4c3a07e5 | Phase 4 screen batch | ~70% done |
| REL-PREVIEW | Release local_0004e483 | try card + update-try test | nearly done |
| API-200 | local_53f2edec | October API plan (lanes 1 + 5) | guard stop (25 USD left) |

When a track ENDs, its leftovers come to this board as cards for H1/H2/LANE, not to a new chat.

## Lanes 2, 3, 4
On HOLD (2026-10-19 00:30, `BUDGET-API.md` pre-flight item 1). They restart only from LANE cards on this board, on
1 Nov or later.
