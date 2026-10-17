<!-- SPDX-License-Identifier: GPL-3.0-or-later -->
<!-- © 2026 The Why Not AI (thewhynot.ai) -->

# G13: transcription precision per model, speed against the budgets (Phase 4 T4.14)

Measured on **2026-10-17** by the API-credit lane on the owner's PC: Lenovo LOQ, i7-14700HX, 32 GB, **RTX 4060 Laptop
8 GB** (driver idle VRAM 533 MB), Windows 11. Engine: the T4.11 + T4.14 code (snapshot of c6e80b5 + the T4.14 files),
faster-whisper 1.2.1 / CTranslate2 4.8.2, model **large-v3** (Systran CT2), the client's vocabulary hint on, a
scratch engine home (never `~/.whynot-cut`), `HF_HUB_OFFLINE=1`. Premiere and After Effects were **not running**
(process list checked before every run). Every run went through `heavy.sh gpu`; the machine was shared with other
sessions' test suites (CPU 70-80 % busy), which slows the CPU runs most. Raw rows: the lane's `work/t414/bench.jsonl`.

## Clips (test copies only, `../whynot-test`, copied to the scratch area)
- **(a)** 54.3 s of Arabic speech: the R02 window (125.15-179.45 s) of `Dr Sherin Helmy/data/Raw/EP02.mp4`. The plan
  names a 60 s clip from `عميل-تجربة-٣`, but its clips are 14 s and 0.1 s long, so R02 (the nearest 60 s Arabic clip
  of the test set) was used.
- **(b)** the first 300 s of the same EP02 (the plan names PODCAST-TEST EP02; that folder holds no media, the EP02 file
  is the Dr Sherin Helmy copy).
- **(c)** all of EP02 (34:41) with `reel episode-transcribe` (T4.11 job run, product default priority).

## Reference transcripts: none verified
No item in the test set has an editor-verified transcript (`02_transcription/verification.json` exists nowhere), so
**there is no reference** in the sense of the plan. For (a) the R02 `words.json` (machine words with the editor-side
corrections applied, NOT verified by ear) is used as an informational comparison, labelled "vs corrected"; it is not
used by the pick rule. (b) has only agreement between the decoders.

## Results (median of 3 runs where n = 3; RTF = minutes of audio per minute of decoding)
Equal batch (the T4.11 VRAM fit turned off in a measurement-only copy, so both precisions decode batch 4):

| Clip | Precision | n | RTF | decode s | load s | peak VRAM (machine) | WER / CER vs corrected |
|---|---|---|---|---|---|---|---|
| (a) 54 s | float16 | 3 | **13.91** | 3.90 | 4.24 | 5146 MB | 0.0989 / 0.040 |
| (a) 54 s | int8_float16 | 3 | 10.09 | 5.38 | 9.27 | 3514 MB | 0.1099 / 0.045 |
| (b) 300 s | float16 | 3 | **17.13** | 17.52 | 3.88 | 6778 MB | — |
| (b) 300 s | int8_float16 | 3 | 13.07 | 22.95 | 8.97 | 4730 MB | — |
| (a) 54 s | CPU int8 (20 threads) | 1 | 0.93 | 58.09 | 6.92 | — | 0.0879 / 0.0375 |
| (b) 300 s | CPU int8 (20 threads) | 1 | 1.15 | 261.5 | 6.55 | — | — |

The text of every run was identical across its 3 repeats. Agreement on (b): int8_float16 vs float16 differ in 6.0 %
of the words (20 substitutions, 3 deletions, 7 insertions of 497; CER 2.1 %); CPU int8 vs GPU float16 differ in
10.5 %. That is agreement, not accuracy: no reference says which one is right.

VRAM per batch size on (b) (machine peak minus the 533 MB idle):

| batch | 0 (sequential) | 2 | 3 | 4 |
|---|---|---|---|---|
| float16 | 4199 | 4613 | 5573 | 6245 |
| int8_float16 | 2341 | 3109 | 3621 | 4197 |

Whisper load and release (T4.11, one process, float16, 54 s decode): 533 MB before → 4392 after the load (3.2 s) →
5018 peak → **634 after `run.release()`** → 533 after the process ends.

## Decision, one precision per model (rule applied as written in the plan, not tuned)
- **large-v3: float16.** "Not verified: no reference" — by the rule int8_float16 cannot win without an editor-verified
  reference clip. The measurements point the same way: int8_float16 was **slower** here (RTF 13.1 vs 17.1 on (b),
  10.1 vs 13.9 on (a)), so it fails the "≥ 10 % faster" leg; it does use ~2 GB less VRAM (which would satisfy the
  "or ≥ 1 GB less" leg), and against the corrected (not verified) transcript its WER is 1.1 pp worse, which would
  fail the quality bar (≤ 0.5 pp).
- **large-v3-turbo: float16.** "Not verified: not measured" — the model is not downloaded on this PC; downloading it
  is a pin decision for the executor's Task 12 (not done by this lane).
- The shipped choice `{"large-v3": "float16", "large-v3-turbo": "float16"}` is `GPU_COMPUTE_TYPE_DEFAULTS` in
  `lib/whisper_backends.py` (moved out of `transcription.json` in the acceptance follow-up, batch A); the file's
  `gpu_compute_types` is `{}` for profiles to fill. Order: a profile's `gpu_compute_types[model]`, else the old
  `gpu_compute_type` from a profile, else the shipped choice, else float16 (transcription.json has no settings layer:
  the defaults merged with the shipped and client profiles; a per-model entry in any profile beats the old key in
  any profile). So a profile that set only
  the old key (for example int8_float16 on a small GPU) keeps it; before batch A a shipped per-model entry overrode it.
- VRAM constants (T4.11 `fit_batch`) from the measured line + 10 %: large-v3 float16 3279 MB, int8_float16 2223 MB,
  `PER_BATCH_MB` 900 (816 / 544 measured); turbo rows keep the starting values. With the 1536 MB Premiere headroom an
  idle 8 GB laptop card now fits **batch 2** for large-v3 float16 (batch 4 peaked at 6245 MB + 533 idle = 6.8 GB of
  8.2 GB, leaving 1.4 GB). Batch 2 is ~20 % slower than 4 (RTF 13.6 vs 17.1). Batch 2 is the fit's arithmetic (batch 3 needs
  7515 MB free, the card showed 7424-7504), not a measured run at batch 2. This is the plan's headroom rule applied
  to measured numbers; `PER_BATCH_MB` is one value (float16's slope), so int8_float16 is over-reserved (its slope is
  544 MB); whether 1536 MB is the right headroom is an executor/owner choice (1024 MB would allow batch 3).

## Noise and the pick rule (why 0.5 pp WER / 0.3 pp CER)
- **Run-to-run noise is zero here.** Decoding is deterministic: the text of every run was identical across its 3
  repeats (above), so repeating a run cannot separate two precisions. Speed does vary run to run (the machine was
  shared), which is why RTF is a median of 3 and the speed leg asks for a clear margin (≥ 10 % faster), not any gain.
- **The noise that matters is which clips were measured.** One word in a 500-word clip is 0.2 pp of WER. If one
  clip's WER of about 0.10 is treated as a sample, its standard error is about √(0.1 × 0.9 / 500) ≈ 1.3 pp, larger
  than the 0.5 pp bar. Both precisions decode the same audio, so the paired difference is much tighter than that,
  but on one or two clips a difference under about 1 pp still cannot be told from chance.
- **Decision (the rule as written; not tuned to these numbers):** a difference inside the bar (≤ 0.5 pp WER and
  ≤ 0.3 pp CER) is treated as "no quality difference", and then speed or VRAM decides. A difference above the bar
  keeps float16, even when it could be noise. The rule is asymmetric on purpose: a wrong int8_float16 pick costs
  words (medical terms, doses) in every transcript, while a wrong float16 pick costs only speed and VRAM, which the
  T4.11 VRAM fit already manages. With no editor-verified reference the question does not come up: float16 by rule.
- **The bar is applied per clip** (as `pick_compute_type` is written): int8_float16 must stay within it on every
  reference clip. More clips therefore make an int8_float16 win harder (more chances to cross the bar by chance), not
  easier; that keeps the rule on the safe side.
- **What would change it:** an editor-verified reference set of at least ~2,000 words (several clips, Arabic and
  English), with the bar applied to the corpus total (`wer.total()` over the reference clips, where 0.5 pp is about
  10 words) instead of per clip. That is a change to `pick_compute_type`, for the executor to decide when such a set
  exists.

## Normaliser changes (batch A) and these numbers
The acceptance follow-up changed `lib/wer.py`: "5mg" = "5 mg" (a glued unit is its own word), "3,000" = "3000"
(thousands separators dropped; "0,125" and "1,5" stay decimals; the ambiguous "1,500" reads as thousands), ٱ folds to
ا, ".5" stays the decimal "0.5", a decimal inside a word keeps its point ("و٣٫٥" = "و" + "3.5"), and CER keeps a
space between two number tokens ("3 . 5" is never "35"). Re-checked on the saved hypotheses:
the (b) agreement numbers are unchanged (int8_float16 vs float16 WER 0.0604, 30 of 497; CPU vs GPU 0.1046), because
none of those words has a digit or ٱ. The (a) WER/CER above were not recomputed (the (a) hypotheses were not saved),
but the R02 reference has no digit or ٱ, and (a) is a window of the same audio as (b), whose hypotheses have none, so
they are expected to be the same (Not verified).

## Budgets
| Budget | Measured | Result |
|---|---|---|
| G2: a 60 s clip ≤ real time on the GPU (transcription share) | (a) 54 s: decode 3.9 s + load 4.2 s ≈ 8 s (`reel transcribe` end to end: 10.0 s wall) | **PASS** |
| Benchmark §5.1 proposal: 90 s raw clip → plan + preview ≤ 15 min (transcription's share) | ≈ 90 / 13.9 × 60 / 60 ≈ 6.5 s decode + 4 s load ≈ 11 s; preview-video of R02: 43.6 s | transcription share PASS (the whole budget is not measured here) |
| 35-min episode vs the 2.x ≈ 4 min | 160 s (batch 3) | **PASS** |
| CPU machines (G13 binds there too): 60 s clip real time | (a) on the CPU: 58 s for 54 s of audio (RTF 0.93), machine shared with other suites | **FAIL** (slower than real time on this loaded CPU) |

## Episode (c)
`reel episode-transcribe --episode EP02 --force` (34:41, 4 chunks, VAD, float16, product default priority
BelowNormal, the T4.11 starting constants that fitted **batch 3**): **160 s wall** (2.7 min; chunks of ~10 min took
44-46 s each), 3820 words, peak RSS 3.3 GB, peak VRAM 6153 MB (machine), GPU 74 % mean; VRAM back to 453 MB after
the process; no process left. Against the 2.x ≈ 4 min: **PASS**. With the measured constants of this commit an idle
8 GB card fits batch 2 (about 20 % slower on (b)), so the same episode would take an estimated ~3.2 min (not
measured), still under 4 min.

## Not verified
- English (H13 pending): no English clip was measured.
- Accuracy: no editor-verified reference exists; WER/CER above are against a corrected, unverified transcript.
- large-v3-turbo: not downloaded, not measured.
- Mac (MLX, CT2 CPU on Apple Silicon): needs a Mac (Step 7).
