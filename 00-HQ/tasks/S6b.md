# S6b — Gate 4 eval cases for the Phase 4 skills

- **Assigned:** H1    **Model:** Opus 5.5 high    **Size:** M    **Status:** READY (2026-10-20 22:20, executor answer below)
- **Tier:** LIGHT (eval cases: dev workflow; they test the product, they don't change it)
- **Stage / gate:** Gate 4 (`WhyNotCut/PROGRESS.md` line "Evals": "Add cases for the Phase 4 skills (rules/T4.3,
  episode sheet, autopilot, music NEEDS-YOU): S6 work for a free builder")    **Depends on:** the executor naming
  which of those skills' texts are frozen

## Goal
New `claude plugin eval` cases under `whynot-cut/evals/` for the Phase 4 behaviours the p3 baseline does not cover, so
the Gate 4 eval run (at the end, after code freeze, `-j 2` through heavy.sh) measures them.

## Spec (filled from the executor's answer before READY)
- One folder per case, same shape as `evals/autopilot-new-clips/`: `case.yaml` (schema 1.1, `runs: 3`), `prompt.md`
  (Arabic editor wording where the skill is Arabic-facing), `graders/*.md`, `scaffold.sh` using the shared
  `evals/_fixtures` functions only.
- Per behaviour: at least 1 positive case; and 1 negative case where a wrong trigger is plausible.
- Graders: one claim each, measured on the real judge (strict one-word one-sample, as in the p3 baseline note).
- Cases list (confirmed, see ## Answer): rules/T4.3 · episode sheet/T4.4 · autopilot/T4.7 · music NEEDS-YOU/T4.6 ·
  review-scan before the medical-reviewer (edit skill stage 7). **No cases** for client-move/clone, verse/religious
  lines, or cut proposals/takes (still in rounds).

## Fence
`whynot-cut/evals/<new case folders>/` only, plus the expected-case list in `whynot-cut/tests/test_evals.py` if that
test enumerates cases. No skill text edits: a skill fault an eval finds goes into the report as a finding for the executor.

## Acceptance
1. `bash tools/test.sh -p test_evals.py` green (every case well formed).
2. Each new case run once by `claude plugin eval` on the subscription CLI **if** the bundled CLI is logged in (H11);
   if `auth_failed`, say so: that is no result, not a fail. No paid API.
3. Full suite through the queue (`bash <heavy.sh> suite h1-S6b -- env PYTHONDONTWRITEBYTECODE=1 PYTHONUTF8=1 bash tools/test.sh`).
4. One fresh independent review (LIGHT tier), at most 2 fix rounds.

## Delivery
Branch `h1/S6b`, report `00-HQ/inbox/h1/<date>-S6b.md` (PLAYBOOK §2).

## Answer
Executor, 2026-10-20 (HEAD 17729fc):
- **Frozen; write cases now:**
  - rules / T4.3: client-craft and edit text, verb landed fcb7884;
  - episode sheet / T4.4: podcast skill's episode-sheet steps;
  - autopilot / T4.7: the autopilot skill;
  - music NEEDS-YOU / T4.6: closed 7d0e9c0.
- **Add one:** review-scan before the medical-reviewer, in the edit skill stage 7 (1cb5eab).
- **NOT frozen; no cases yet:**
  - client-move / clone (handoff skill), because BL-14 is still in review rounds;
  - verse / religious lines (medical-accuracy, motion, podcast and agent texts), because verse fix r2 is building;
  - cut proposals / takes (edit skill), because the K-T7 port has not landed.
- **The fence is right:** evals + test_evals.py only.
