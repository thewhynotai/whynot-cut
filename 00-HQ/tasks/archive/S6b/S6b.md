# S6b — Gate 4 eval cases for the Phase 4 skills

**Archived:** DONE_ARCHIVED 2026-10-23 05:50 (master). Merged on release/3.0 as f3995f9; origin = abdece5 (verified ls-remote).

- **Assigned:** H1    **Model:** Opus 5.5 high    **Size:** M    **Status:** ACCEPTED (2026-10-23 03:05; peer h2 PASS-WITH-MINORS on d6f9a3b, no P1/P2; → MERGE-QUEUE)
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

## FIX round 1 (2026-10-21 17:55)
Master intake decision from the valid peer review `reviews/S6b-peer-h2-20261021-1224.md` (h2, sha 6a76a75, report-mtime
1792557329, verdict PASS-WITH-MINORS). Fence re-checked by the master: all 77 paths under `whynot-cut/evals/` or
`whynot-cut/tests/test_evals.py`; all 3 commits "Mayar (WhyNot Helper 1)". The peer suite's 4 failures are outside the
diff (not counted against you). A P2 blocks ACCEPTED, so:
1. **P2-1 (must fix):** `whynot-cut/evals/autopilot-approval-auto/graders/auto-approve-command.md:7` fails the
   skill-faithful answer (no fixture sets `approval: auto`; default is `ask`, so the right move is
   `reel approve-plan --by delegated …` or asking "this clip only, or from now on?"). Fix inside the fence: let the
   grader also accept the delegated path (e.g. `reel(?:\.cmd)?\s+(?:auto-approve|approve-plan[^\n]*--by[ =]delegated)`),
   or drop this grader and rely on `sensitive-never-auto` + `stops-at-qc`. No `_fixtures` change (outside the fence).
2. **P3s (fix if cheap, else list under "Known limits" in your report):** P3-1 map each case to its expected
   positive/negative tag in `test_evals.py:199-200`; P3-2 reword product finding 1 (motion/SKILL.md:111-112 already names
   the needs_you music item; what is missing is the licence-file rule and "check data/Music first"); P3-3 say the music
   cases measure the lead's own text only (no Agent tool); P3-4 split two-claim llm graders or record it as accepted;
   P3-5 make `episode-sheet-before-episode`'s Skill grader record-only, or hand the description gap to the executor.
Then: focused `test_evals.py`, the full suite through the queue, a new report with the new sha and the suite line.
LIGHT tier: this is round 1 of at most 2.

## Accepted (2026-10-23 03:05)
Master intake decision from the valid peer review `reviews/S6b-r3-peer-h2-20261022-1005.md` (h2, sha d6f9a3b = branch tip, report-mtime 1792626934,
verdict PASS-WITH-MINORS, no P1/P2). The file name carries `S6b-r3` (the dispatch's name) instead of `S6b`: the helper
id h2 matches the reviewer line and the reviewer is not the author, so it counts. Fence re-checked by the master: every
path under `whynot-cut/evals/` or `whynot-cut/tests/test_evals.py`; all 4 commits "Mayar (WhyNot Helper 1)". Peer suite:
Ran 9117, 5 F (ae_builder junction, identity_scan speed, isolation s1_reachable, media_normalise A/V sync, serve_jobs
total order fixed on release/3.0 in dd52ae8): known env/timing classes, none in the diff, no worse than the baseline.

## Accepted minors
- P3-1: this round's graders (auto-approve-command, not-a-rule, tells-the-editor, scan-before-reviewer, hands-the-lines,
  episode-sheet skill-fired min 0) were never run on the real judge: the Gate 4 eval run is their first measurement.
- P3-2 (Known limit): no T4.4 case scores whether the podcast skill fires (`min: 0` in both episode-sheet cases); root
  cause `podcast/SKILL.md:3` is the executor's. When the description widens, drop `min: 0` + the matching assert.
- P3-3: `auto-approve-command.md:7` regex can pass a mention and miss `--by "delegated"` / a wrapped line (house style).
- Note: `tests/test_evals.py:155` regex_issues is order-dependent (swap the alternation and it reports a false
  `auto-approve --by`); for whoever next touches it.
