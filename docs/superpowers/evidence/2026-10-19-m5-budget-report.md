<!-- SPDX-License-Identifier: GPL-3.0-or-later -->
<!-- © 2026 The Why Not AI (thewhynot.ai) -->

# M5 budget report from `tools/token_report.py --budget` (Addendum M, M5-T2, report-only at Gate 4)

> **PROVISIONAL, report-only.** No clean pipeline run of any mode exists yet, so every mode is **NOT MEASURED** and
> no verdict is binding (budgets bind from Gate 6). The rows below are the existing development sessions of the
> Task 57 baseline, shown per video as "provisional, n=<k>". They are an upper bound and are never judged.

## Which runs exist
| Mode | Clean runs | Why not | Provisional rows |
|---|---|---|---|
| Single clip | none | A token measurement needs an attended lead session running the edit skill with the production model mix, through the Premiere build and QC. A subagent cannot be that lead session (its own `reel` commands never move a stage, and nested `claude` sessions are refused here). Premiere was not started by this task. Engine-only stages cost 0 model tokens by construction, so running them alone measures nothing here. | 3 videos |
| Podcast reel | none | No Adobe (Premiere) slot (ruling Q60-1). | 3 videos |
| Motion | none | No Adobe (After Effects) slot (ruling Q60-1). | 1 video |

- **The single-clip fixture (Q60-1):** the T4.14 clip, the R02 window (125.15–179.45 s) of the `whynot-test` EP02 copy.
  Its transcript was read from a fresh `robocopy /XJ` copy (never the original): **0.905 speech minutes**
  (meta.duration_ms 54,300).
- **Provisional rows:** the two Task 57 project folders (the development folder and the repo folder), `--marked-only`,
  regenerated on 2026-10-20 with 1.3.0. Mode by video id: `*_MO` = motion; `EP…_<id>` = podcast reel; anything
  else = single clip. Episode-level ids (the episode share) are left out. A row is the usage attributed to that video
  plus the setup before the first `reel` command of its sessions, labelled item-filtered; the same setup can sit in
  more than one row (the development folder's setup is large: the biggest single-clip row grew from 78.9M with
  1.2.0, which dropped the setup, to 219.6M). A row is all the development work attributed to that video, so it is
  far above a clean run. No
  quality graders ran, and the commit is unknown (the sessions span many commits).
- **Podcast-reel episode share:** not included. M5.3 wants it in a podcast reel's budget; the tool cannot add it yet,
  and the podcast-reel scope line in the block says so.
- **Tool:** `tools/token_report.py` 1.3.0 (review 512656d round-1 fixes). Its rules are unit-tested in
  `tests/test_token_report_budget.py` on the committed fixture:
  - budgets are in the M5.2 unit, and the verdict is `binding: false`;
  - the median of ≥ 3 complete runs (an even count takes the upper middle) is at or under the budget, and no run is
    over 1.25×;
  - every run passed every grader any run of its mode ran;
  - not counted: runs holding an API error record, duplicates, and incomplete runs;
  - each run's lead model is detected, and a different lead or an unknown commit is NOT COMPARABLE;
  - run, grader and video names are anonymised;
  - the plain fixture → PASS;
  - the planted ×3 run → FAIL naming the run.

## The `whynot-test` project folder (Task 60 fu1, read 2026-10-20)
Allowed by the plan session and the executor: read in place, local only, aggregate numbers only. Every number in this
section is **PROVISIONAL (source: old session logs)** and is replaced by a real measurement after the tag.

| Measure (`token_report.py` 1.2.0, whole folder) | PROVISIONAL (source: old session logs) |
|---|---|
| Sessions / assistant messages / tool calls | 1 / 1 / 0 |
| Session length | about 4 s (2026-10-18) |
| `reel` commands (stage markers) | 0: everything is stage `setup`, no video named |
| Raw: fresh / 1 h cache write / cache read / output | 2 / 37,239 / 27,885 / 4 |
| Weighted, M5.2 unit (published prices) | 77,288 (75,894) |
| Lead context per turn: median / p90 / max | 65,126 / 65,126 / 65,126 (0 turns over 150,000) |
| Model mix | claude-opus-5-5 100 % |

- **Mode: none, so no row.** The session made one model reply with no tool call and ran no `reel` command, so it
  names no video and no pipeline stage. It is no single clip, podcast reel or motion run, so it adds no provisional
  row to any mode, and no verdict changes. All three modes stay NOT MEASURED.
- **It is not the M5.2 pipeline session.** M5.2 measured 3 single clips, 1 podcast episode and 10 reels, with stages
  such as previews (12.3M), plan (12.2M) and ppro-build (7.3M). This folder has one 4-second session from
  2026-10-18, after M5.2 was measured (2026-10-16), with no stage at all. A stage-by-stage comparison with M5.2
  therefore has nothing to compare. The M5.2 session is not in any of the three project folders read so far.

## The run that replaces this
Per mode, 3 attended runs at one commit, each in its own Claude Code project folder (or `claude plugin eval
--keep-temp` + `tools/eval_transcripts.py`):
1. single clip on a fresh `/XJ` copy of `whynot-test` with the R02 clip, raw → Premiere project → QC;
2. one podcast reel, picked candidate → Premiere → QC;
3. one motion video, script → AE render → QC.

Write a budget runs file. Each run gets its mode, transcripts, `status`, the quality graders' results and the
`speech_transcript` (format in the tool's docstring). Then:
`python tools/token_report.py --budget runs.json --json <out> --md <block>` and paste the block below.

<!-- generated by tools/token_report.py 1.3.0 --budget: do not edit this block by hand -->

**Report-only at Gate 4.** No verdict below is binding; the budgets bind from Gate 6. token_report.py 1.3.0, repo HEAD a31c54245c4c when generated (an uncommitted working tree is not detected), report date 2026-10-20.

Unit: M5.2 unit (lead-model fresh input equivalents, fixed multipliers 1 / 1.25 / 2 / 0.1 / 5). A mode passes when the median of at least 3 complete runs is <= its budget, no run is over 1.25x the budget and every run passed every quality grader any run of its mode ran. The median of an even number of runs is the upper middle one. Runs cut by an API error record, incomplete runs and duplicates are listed and never counted. Lead-context guard rail: 150,000 per turn (reported, not judged).

### single-clip: NOT MEASURED (report-only, n=0)

Scope: raw -> Premiere project -> QC. Budget 2,500,000, run cap 3,125,000, stretch 1,500,000 (printed, not judged).

Verdict: not measured (no clean run: needs an attended lead session (edit skill, production model mix) through the Premiere build and QC).

Baseline rows (provisional, n=3: development sessions, an upper bound, never judged):

| Run | Status | Item | Weighted, M5.2 unit | Weighted, published prices | Raw tokens | Speech min | M5.2 unit per speech min | Lead context median / p90 / max | Guard rail | API errors | Lead model | Commit | Model mix (M5.2 unit) | Quality | Label |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| run-01 | complete | item-01 | 219,620,768 | 163,820,035 | 1,191,205,195 | n/a | n/a | 264,765 / 639,074 / 736,499 | over on 543 of 621 turns (max 736,499) | 58 | claude-opus-5-5 | unknown | claude-opus-5-5 99.7 %, claude-sonnet-5-5 0.3 % | not measured | provisional, n=3; item-filtered: setup kept, other videos left out |
| run-02 | complete | item-02 | 12,408,548 | 7,104,970 | 106,661,581 | n/a | n/a | 523,358 / 827,950 / 884,124 | over on 200 of 200 turns (max 884,124) | 0 | claude-opus-5-5 | unknown | claude-opus-5-5 100.0 % | not measured | provisional, n=3; item-filtered: setup kept, other videos left out |
| run-03 | complete | item-03 | 18,102,485 | 10,886,101 | 145,999,334 | n/a | n/a | 535,010 / 808,729 / 893,366 | over on 255 of 263 turns (max 893,366) | 0 | claude-opus-5-5 | unknown | claude-opus-5-5 99.9 %, claude-sonnet-5-5 0.1 %, claude-haiku-5-5 0.0 % | not measured | provisional, n=3; item-filtered: setup kept, other videos left out |

### podcast-reel: NOT MEASURED (report-only, n=0)

Scope: picked candidate -> Premiere -> QC; episode share not included (M5.3 wants it included: the tool cannot add it yet, so a podcast-reel row is short by that share). Budget 2,500,000, run cap 3,125,000, stretch 1,500,000 (printed, not judged).

Verdict: not measured (no clean run: needs an attended lead session and an Adobe slot (Premiere / After Effects), not given (Q60-1)).

Baseline rows (provisional, n=3: development sessions, an upper bound, never judged):

| Run | Status | Item | Weighted, M5.2 unit | Weighted, published prices | Raw tokens | Speech min | M5.2 unit per speech min | Lead context median / p90 / max | Guard rail | API errors | Lead model | Commit | Model mix (M5.2 unit) | Quality | Label |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| run-01 | complete | item-04 | 13,036,342 | 8,514,654 | 91,789,221 | n/a | n/a | 400,946 / 852,215 / 886,692 | over on 209 of 232 turns (max 886,692) | 0 | claude-opus-5-5 | unknown | claude-opus-5-5 100.0 % | not measured | provisional, n=3; item-filtered: setup kept, other videos left out |
| run-02 | complete | item-05 | 12,957,633 | 9,739,108 | 69,384,121 | n/a | n/a | 393,370 / 431,887 / 444,836 | over on 24 of 24 turns (max 444,836) | 0 | claude-opus-5-5 | unknown | claude-opus-5-5 96.1 %, claude-sonnet-5-5 3.9 % | not measured | provisional, n=3; item-filtered: setup kept, other videos left out |
| run-03 | complete | item-06 | 13,274,994 | 8,083,975 | 104,858,495 | n/a | n/a | 243,326 / 825,678 / 878,313 | over on 246 of 285 turns (max 878,313) | 0 | claude-opus-5-5 | unknown | claude-opus-5-5 100.0 % | not measured | provisional, n=3; item-filtered: setup kept, other videos left out |

### motion: NOT MEASURED (report-only, n=0)

Scope: script -> AE render -> QC (placeholder budget until Gate 6). Budget 3,500,000 (placeholder), run cap 4,375,000, stretch none (printed, not judged).

Verdict: not measured (no clean run: needs an attended lead session and an Adobe slot (Premiere / After Effects), not given (Q60-1)).

Baseline rows (provisional, n=1: development sessions, an upper bound, never judged):

| Run | Status | Item | Weighted, M5.2 unit | Weighted, published prices | Raw tokens | Speech min | M5.2 unit per speech min | Lead context median / p90 / max | Guard rail | API errors | Lead model | Commit | Model mix (M5.2 unit) | Quality | Label |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| run-01 | complete | item-07 | 30,396,528 | 19,427,335 | 209,140,595 | n/a | n/a | 362,163 / 561,733 / 966,825 | over on 482 of 529 turns (max 966,825) | 8 | claude-opus-5-5 | unknown | claude-opus-5-5 86.4 %, claude-fable-5-1 13.6 % | not measured | provisional, n=1; item-filtered: setup kept, other videos left out |

Assumptions: budgets are judged in the M5.2 unit (the unit M5.3's budgets were set in); `weighted` at published prices is printed beside it; report-only at Gate 4: no verdict is binding before Gate 6; the median of an even number of runs is the upper middle one (statistics.median_high), the stricter choice; a run's tokens are every usage record of its transcripts; with `item`, the usage attributed to that video plus the setup before the first `reel` command of its sessions (labelled item-filtered); a run holding an API error record (usage limit or crash) is cut and never counted, whatever its status says; two runs sharing an API message id are one run: the later name is a duplicate and never counted; speech minutes = the transcript's meta.duration_ms (the decoded audio length), not the talking time alone.

<!-- end of the generated block -->

## Not verified
- **No mode has a clean run:** single clip, podcast reel and motion are all NOT MEASURED. No budget pass or fail
  exists for any mode.
- **The mode of a provisional row comes from its video id**, a heuristic. The rows mix development and pipeline work.
- **The M5.2 real pipeline session was not found.** The `whynot-test` project folder was read in fu1 and holds no
  pipeline run (see above). Where the session M5.2 measured lives on this PC is still unknown, so M5.2's stage table
  is still not reproduced.
- **The eval-runner path is unchecked on a live run:** `eval_run` reads `eval_transcripts` folders, but the
  eval-runner transcript layout itself is still unchecked live (Task 57).
- **The production model mix is not checked:** the rows record the measured mix, not a comparison against the
  shipped agent frontmatter.
- **The prices are from the published page as read on 2026-10-18.** count_tokens re-checks them when the API resumes
  (November).
