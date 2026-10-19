<!-- SPDX-License-Identifier: GPL-3.0-or-later -->
<!-- © 2026 The Why Not AI (thewhynot.ai) -->

# M5 token baseline from `tools/token_report.py` (Addendum M, M5-T1)

> **PROVISIONAL.** The clean fixture runs of the three modes (single clip, built podcast reel, motion video) are
> still pending (Q57-3). The rates are re-checked with count_tokens when the API resumes (November). Until then
> these numbers are a measurement of this PC's transcripts, not a per-video baseline.

| | |
|---|---|
| Measured | 2026-10-19 (regenerated after review efe8910; first run 2026-10-18), read-only, on this PC's Claude Code transcripts |
| Tool | `tools/token_report.py` 1.1.0, repo commit b2db1e7 (stamped by the tool) |
| Input | the two WhyNot Cut project folders under `~/.claude/projects`: A = the development folder (175 sessions), B = the repo folder (1 session). No other project folder was read. |
| Output kept | anonymised JSON outside the repo; this file holds aggregates only (stage names, model ids, counts, `item-NN` labels) |
| Prices | the published pricing page, read 2026-10-18 (constant block in the tool). Unit: one weighted token = one fresh input token of the lead model (`claude-opus-5-5`, $4/MTok). |
| Tests | `tests/test_token_report.py` (102), `tests/test_eval_transcripts.py` (15) |

## How the tool counts (short)
- **Usage records.**
  - Usage comes from `assistant` records only.
  - One API response is written as several records with the same `message.id`. Output tokens grow across them, a tail
    record can be all zero, and a resumed session can replay a stale copy.
  - Per id the record with the most tokens counts, whatever the order of the session files, and an id counts once
    per report.
  - On folder B, 717 of 897 ids had more than one record, 151 had growing output, and the last record always held
    the largest usage.
- **Subagents.** Subagent usage goes to the stage that was current when the main conversation started the
  subagent. On folder A all 38,373 subagent messages resolved to their spawn (0 unattributed).
- **Stage.** The stage is the latest `reel <verb>` the main conversation ran, read with the quoting rules of the tool
  that ran it (Bash or PowerShell).
  - Only verbs of the `reel` command table count. Two `reel` words on folder A were not commands and started no stage.
  - Read-only verbs (next, status, doctor, ...) never start a stage.
  - Before the first command, the stage is `setup`.
- **Video.** The video is the value of `--video-id` (else `--episode`): the CLI has no positional video id, so an
  option value is never a video.
- **Weighting.** Each model is weighted at its published prices. **Claude Opus 5.5 reads cache at 0.05x its input
  price, not the 0.1x of the M5.2 unit.** So the report prints both numbers:
  - `weighted`: the published prices;
  - the M5.2 unit: reads at 0.1x, for comparison with the M5.2 table.

## Results
| Measure | A, all sessions | A, sessions that ran a `reel` command (`--marked-only`) | B, all |
|---|---|---|---|
| Sessions / messages | 175 / 53,392 | 10 / 22,113 | 1 / 881 |
| Fresh input | 425,838 | 106,900 | 1,798 |
| Cache write 5 m / 1 h | 540.9M / 93.9M | 175.9M / 32.6M | 1.98M / 4.41M |
| Cache read | 13.87B | 5.85B | 206.9M |
| Output | 54.0M | 21.4M | 1.03M |
| Cache read share of raw tokens | 95.3 % | 96.2 % | 96.5 % |
| **Weighted** | **1.724B** | **661.3M** | **26.8M** |
| M5.2 unit (reads at 0.1x) | 2.386B | 946.3M | 37.1M |
| Model mix (weighted) | Opus 5.5 93.5 %, Sonnet 5.5 6.1 %, Fable 5.1 0.4 %, Haiku 5.5 < 0.01 % | Opus 5.5 95.4 %, Sonnet 5.5 3.9 %, Fable 5.1 0.8 % | Opus 5.5 100 % |
| Subagent share of weighted | 69.9 % | 64.4 % | 19.6 % |
| Lead context per turn: median / p90 / max | 313,331 / 652,508 / 967,183 | 375,368 / 751,723 / 967,183 | 261,073 / 487,849 / 568,149 |
| Lead turns over the 150k guard rail | 13,168 of 15,019 (87.7 %) | 6,264 of 6,780 (92.4 %) | 573 of 679 (84.4 %) |
| API error records (apart, zero tokens) | 575 | 187 | 16 |
| Unreadable lines, files or folders | 0 | 0 | 0 |

**Stages of A, marked sessions (weighted, 42 stages):**

| Stage | Weighted | Share |
|---|---|---|
| setup | 305.9M | 46 % |
| approve-plan | 127.3M | 19 % |
| removed-review | 106.3M | 16 % |
| plan | 16.7M | |
| lock | 16.3M | |
| handoff | 13.2M | |
| audio-clean | 12.3M | |
| ppro-install | 8.4M | |
| episode-transcribe | 7.4M | |
| episode-next | 5.0M | |

The pipeline stages of M5.2 add up to 41.2M: audio-clean, transcribe, transcript-correct, plan, previews, ppro-build,
qc, motion-*, reels-*, preview-video and ppro-frames.

**Videos:** 11 were named, all by `--video-id` / `--episode`, so none is a phantom from an option value. item-02 is
127.1M, item-05 18.9M, item-01 11.9M, and every other one is under 11M.

## What this does and does not show
1. **The M5.2 stage table is not reproduced from these folders.** M5.2 measured previews 12.3M, plan 12.2M and
   ppro-build 7.3M for one real pipeline session. Here previews is 0.29M, plan 16.7M and ppro-build 1.7M.
   - These folders hold development sessions. A stage set by a development `reel approve-plan` or
     `reel removed-review` run stays current for the rest of that session, so development work lands there.
   - The real pipeline session that M5.2 measured is not among these sessions, or was run in another project folder
     that this run was not allowed to read.
2. **Development turns are not removed.** M5.2 removed them by hand (8.8 %). The tool has no rule for that, so every
   figure here is an upper bound for pipeline work.
3. **What holds regardless of attribution:** cache reads are 95–97 % of all tokens, and the lead's context is far
   above the 150k guard rail (median 313k, 87.7 % of turns over it). This agrees with M5.2's "the lead's context is
   the sink".
4. Not counted: calls Claude Code makes without a transcript record (titles, compaction summaries).

## What replaces this
- The clean fixture runs of the three modes (Q57-3), each through these steps:
  1. run `claude plugin eval ... --keep-temp`;
  2. collect with `python tools/eval_transcripts.py <aggregate-result.json> --out <folder>`;
  3. report with `python tools/token_report.py <folder> --json <file>` (per case and per run).

  `--output-dir` alone keeps no transcripts. The eval-runner layout this relies on (`<temp>/out/trace.jsonl`,
  `<temp>/config/projects/`) is inferred from leftover temp folders and is not yet checked on a live run.
- The count_tokens re-check of the rates when the API resumes (November).

How to regenerate (read-only):
`python tools/token_report.py <project folder> [--marked-only] --json <file outside the repo>`
