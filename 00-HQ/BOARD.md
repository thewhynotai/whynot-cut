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
| SETUP-H1 | First login (mayar@) + full suite baseline | H1 (Mayar) | ACCEPTED — closed, no code (nothing to merge) | `tasks/SETUP-H1.md` | r3 2026-10-20 08:26: 8226 run, 51 env/timing; ENV-01 gaps routed |
| BL-16 | Safe ASCII engine home for a non-ASCII Windows user (Gate 4, high) | H1 | FIX (round 1, 2026-10-20 08:24) | `tasks/BL-16.md` | H1 fixes P1 patch + 2×P2 |
| BL-02 | Licence files, notices generator, SPDX tool (tool only) (Gate 4, high) | H1 | READY | `tasks/BL-02.md` | — |
| BL-17 | Second install must not overwrite the first install's pointer files (Gate 5) | H1 | READY | `tasks/BL-17.md` | — |
| BL-19 | Root-normalised fingerprints, so a client move keeps its approvals (Stage 2) | H1 | READY | `tasks/BL-19.md` | — |
| SETUP-H2 | First login (marketing@) + full suite baseline | H2 (marketing@) | ACCEPTED — closed, no code (nothing to merge) | `tasks/SETUP-H2.md` | r1 2026-10-20 11:40: 8753 run, 77 env/timing (ENV-01 classes); npm ci + 296 panel tests + 1 render OK |
| BL-03 | GPL-compliance + trademark notice templates (AR + EN) (Gate 4) | H2 | READY | `tasks/BL-03.md` | answered 2026-10-20 08:26: run full suite via queue, then DONE |
| BL-04 | run-state.json + resume, preflight-first in `reel next` (Gate 4) | H2 | READY · fallback executor 25 Oct | `tasks/BL-04.md` | BLOCKED answered 2026-10-20 09:40: queue via wnc-locks/wait; next_doc ruling + fixture patch accepted; full suite with 3 patches, then DONE |
| BL-20 | Gate check: no temporary dated skips in the suite (`tools/skip_audit.py`) (Gate 4 exit, LIGHT, S) | H2 | READY · fallback executor 25 Oct | `tasks/BL-20.md` | — |
| BL-18 | Two wrong fix lines in installer/onboarding (Gate 4) | EXECUTOR (done) | MERGED (f2ca516 on release/3.0, 2026-10-20) | `tasks/BL-18.md` | H2 does NOT take it |
| BL-14 | Portable client copy | EXECUTOR | MERGED (API-200 closed it: 5 commits + executor hooks 7f0c00a; `tracks\API-200-BL-14-HANDOVER.md`) | — | not a card |
| (lane 1) | API lane 1 | — | STOPPED (owner budget ruling 10-19 10:03); BL-16 and BL-04 moved to cards above | — | — |
| S6b | Gate 4 eval cases for the Phase 4 skills | H1 | NOT READY (ask the executor which skills are frozen) | — | master writes the card |
| STAGE3-DRAFTS | Stage 3 task specs (F1, F10, F11 skeleton) as drafts | MASTER | NOT READY (after the Gate 4 tag / 1 Nov) | — | becomes H1/H2/LANE cards |
| ENV-01 | Engine runtime for unsandboxed processes (helper suites: 563 env errors) | MASTER | DONE_ARCHIVED (16:23; helper full suite 8899 OK, 0 fail) | `tasks/archive/ENV-01/ENV-01.md` | — |
| OPS-01 | Status generator, Arabic reports, ops/hq GitHub mirror (pilot task) | MASTER | DONE_ARCHIVED (02:00, 25/25 tests, 2 reviews) | `tasks/archive/OPS-01/OPS-01.md` | OPS-02 |
| OPS-02 | Schedule the 4 daily PRIMARY reports + delivery receipt test | MASTER | IN PROGRESS | `tasks/OPS-02.md` | — |
| OPS-03 | Fold the release-preview refresh check into the report run; retire lane-watch | MASTER | DONE_ARCHIVED (02:20, 28/28, review r1) | `tasks/archive/OPS-03/OPS-03.md` | — |
| OPS-04 | After the tag: move 00-HQ into the repo; fix 3 repo references to archived docs | EXECUTOR | NOT READY (after the v3.0.0-p4 tag) | `tasks/OPS-04.md` | — |
| OPS-05 | First observed cross-account cycle: H1 DONE → H2 peer review → intake verdict | MASTER (observe) | IN PROGRESS (steps 1-4 seen on BL-16; merge pending) | `tasks/OPS-05.md` | — |
| OPS-06 | Effort per tier in helper runs (HIGH → high, LIGHT/setup → medium); owner rule 10-19 21:00 | MASTER | DONE_ARCHIVED (02:12, 30/30, review r1) | `tasks/archive/OPS-06/OPS-06.md` | — |
| OPS-07 | A usage-limit cut must not freeze the intake lock or the heavy queue (incident 10-20 03:54) | MASTER | DONE_ARCHIVED (06:15, 6/6 + sim, reviews r1/r2) | `tasks/archive/OPS-07/OPS-07.md` | — |
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
