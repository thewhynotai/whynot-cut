<!-- SPDX-License-Identifier: GPL-3.0-or-later -->
<!-- © 2026 The Why Not AI (thewhynot.ai) -->

# M5 token baseline from `tools/token_report.py` (Addendum M, M5-T1)

> **PROVISIONAL.** The clean fixture runs of the three modes (single clip, built podcast reel, motion video) are
> still pending (Q57-3). The rates are re-checked with count_tokens when the API resumes (November). Until then
> these numbers are a measurement of this PC's transcripts, not a per-video baseline.

| | |
|---|---|
| Measured | 2026-10-18 (late evening run), read-only, on this PC's Claude Code transcripts |
| Tool | `tools/token_report.py` 1.0.0, repo commit 75e04ea (stamped by the tool) |
| Input | the two WhyNot Cut project folders under `~/.claude/projects`: A = the development folder (148 sessions), B = the repo folder (1 session). No other project folder was read. |
| Output kept | anonymised JSON outside the repo; this file holds aggregates only (stage names, model ids, counts, `item-NN` labels) |
| Prices | the published pricing page, read 2026-10-18 (constant block in the tool). Unit: one weighted token = one fresh input token of the lead model (`claude-opus-5-5`, $4/MTok). |
| Tests | `tests/test_token_report.py` (87), `tests/test_eval_transcripts.py` (12); mutation run 87 of 87 mutants killed |

## How the tool counts (short)
- Usage comes from `assistant` records only. One API response is written as several records with the same
  `message.id`; output tokens grow across them, and a tail record can be all zero. The tool keeps the last non-zero
  record per id and counts an id once per report. On folder B, 717 of 897 ids had more than one record, 151 had
  growing output, and the last record always held the largest usage.
- Subagent usage goes to the stage that was current when the main conversation started the subagent. On folder A all
  36,804 subagent messages resolved to their spawn (0 unattributed).
- Stage = the latest `reel <verb>` the main conversation ran. Before the first one, the stage is `setup`.
- Weighted per model at published prices. **Claude Opus 5.5 reads cache at 0.05x its input price, not the 0.1x of
  the M5.2 unit.** So the report prints both numbers: `weighted` (published prices) and the M5.2 unit (0.1x reads)
  for comparison with the M5.2 table.

## Results
| Measure | A, all sessions | A, sessions that ran `reel` (`--marked-only`) | B, all |
|---|---|---|---|
| Sessions / messages | 148 / 51,029 | 7 / 14,794 | 1 / 881 |
| Fresh input | 420,910 | 91,460 | 1,798 |
| Cache write 5 m / 1 h | 495.5M / 84.6M | 87.1M / 20.9M | 1.98M / 4.41M |
| Cache read | 13.02B | 3.75B | 206.9M |
| Output | 51.7M | 13.7M | 1.03M |
| Cache read share of raw tokens | 95.4 % | 96.9 % | 96.5 % |
| **Weighted** | **1.598B** | **388.1M** | **26.8M** |
| M5.2 unit (reads at 0.1x) | 2.217B | 569.2M | 37.1M |
| Model mix (weighted) | Opus 5.5 93.2 %, Sonnet 5.5 6.4 %, Fable 5.1 0.4 %, Haiku 5.5 0.01 % | Opus 5.5 94.2 %, Sonnet 5.5 5.0 %, Fable 5.1 0.8 % | Opus 5.5 100 % |
| Subagent share of weighted | 69.9 % | 58.7 % | 19.6 % |
| Lead context per turn: median / p90 / max | 306,949 / 643,284 / 967,183 | 407,460 / 773,863 / 967,183 | 261,073 / 487,849 / 568,149 |
| Lead turns over the 150k guard rail | 12,448 of 14,225 (87.5 %) | 4,191 of 4,515 (92.8 %) | 573 of 679 (84.4 %) |
| API error records (apart, zero tokens) | 522 | 103 | 16 |
| Unreadable lines | 0 | 0 | 0 |

Stages of A, marked sessions (weighted): setup 175.6M (45 %), approve-plan 67.5M (17 %), doctor 64.8M (17 %),
music 9.7M, ppro-install 9.4M, next 8.2M, motion-frames 7.5M, episode-next 5.0M, lock 4.9M, ae-status 3.9M; 45 stages
in all. The pipeline stages of M5.2 (audio-clean, transcribe, transcript-correct, plan, previews, ppro-build, qc,
motion-*, reels-*, preview-video, ppro-frames) add up to only 11.9M. 13 videos were named: item-02 127.1M (mostly
approve-plan and doctor), item-01 12.8M, every other one under 11M.

## What this does and does not show
1. **The M5.2 stage table is not reproduced from these folders.** M5.2 measured previews 12.3M, plan 12.2M and
   ppro-build 7.3M for one real pipeline session; here previews is 0.29M and plan 0.67M. These folders hold
   development sessions: the stage after a `reel doctor` or `reel approve-plan` run during development stays
   current for the rest of that session, so development work lands in those stages. The real pipeline session that
   M5.2 measured is not among the sessions of these two folders, or was run in another project folder that this run
   was not allowed to read.
2. **Development turns are not removed.** M5.2 removed them by hand (8.8 %). The tool has no rule for that, so every
   figure here is an upper bound for pipeline work.
3. **Any verb starts a stage.** A deliberately wrong command run in a test (`nonsense`, 38 messages) shows up as a
   stage. Follow-up for the executor: optionally restrict verbs to the `reel` command table.
4. **What holds regardless of attribution:** cache reads are 95–97 % of all tokens, and the lead's context is far
   above the 150k guard rail (median 307k, 87.5 % of turns over it). This agrees with M5.2's "the lead's context is
   the sink".
5. Not counted: calls Claude Code makes without a transcript record (titles, compaction summaries).

## What replaces this
- The clean fixture runs of the three modes (Q57-3), each run through `claude plugin eval ... --keep-temp`, collected
  with `python tools/eval_transcripts.py <aggregate-result.json> --out <folder>` and reported with
  `python tools/token_report.py <folder> --json <file>` (per case and per run). `--output-dir` alone keeps no
  transcripts. The eval-runner layout this relies on (`<temp>/out/trace.jsonl`, `<temp>/config/projects/`) is
  inferred from leftover temp folders and is not yet checked on a live run.
- The count_tokens re-check of the rates when the API resumes (November).

How to regenerate (read-only):
`python tools/token_report.py <project folder> [--marked-only] --json <file outside the repo>`
