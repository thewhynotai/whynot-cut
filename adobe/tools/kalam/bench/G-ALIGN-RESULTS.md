# G-ALIGN — which forced aligner places WhyNot Kalam's Arabic words more accurately (3.0 Task 18b)

Measured 2026-10-16/17 on the development PC (i7-14700HX, RTX 4060 Laptop 8 GB, Windows 11). Every utterance of both
sets was run on both devices; there was no sampling. The numbers below come from real runs of
`adobe/tools/kalam/bench/g_align.py`. The raw `results.json` files stay in the scratch folder (see "Reproduce").

## Answer (fix round 1)

**v3.0.0 keeps MMS.** It is the full trial edition, and per owner decision G8
(docs/legal/third-party-licences.md, "How to read this file", row M8 and §3) nothing is swapped for licence reasons
in 3.0. Kalam 3.0 aligns with MMS-300m, as upstream does. This benchmark does not change the 3.0 default.

**Recommendation for the commercial edition: ar-sep, for Arabic-script words only, provisional.** It is a candidate
under docs/legal §4, gated on two things:
- Task 12b, a multi-dialect, code-switched benchmark with real ASR word times (briefed separately);
- §4's pass test against MMS: equal or better on median **and** p90 onset **and** % within 50 ms, for Arabic **and**
  English, with no caption-rule regressions.

English needs its own candidate per §4: `facebook/wav2vec2-base-960h` or Parakeet's word times. **Not measured
yet.** If no candidate passes, §3 lists the fallbacks: FastConformer CTC (B), stable-ts (C), or a commercial MMS
licence from Meta.

What ar-sep means in `align_w2v`:
- `Aligner("ar", word_sep=True)` with `jonatasgrosman/wav2vec2-large-xlsr-53-arabic` @ `af46c2d8…` (Apache-2.0)
  aligns the words the Arabic model can represent.
- Every other word (Latin, digits, other scripts) keeps the transcriber's time and is flagged `aligned: false`. Its
  window's Arabic words are still aligned.
- A clip with no Arabic-script word runs no aligner at all.
- The per-word fallback and the `aligned` flag apply to `kind="mms"` too. With MMS an unreadable word is one
  `roman()` cannot read, e.g. Cyrillic or CJK.

| | |
|---|---|
| **Rule (brief)** | The winner on the test set's onset median **and** p95. A tie goes to words lost, then to the main set. |
| **Test set** (held-out utterances, **same speaker**) | Split: **mms-kalam** has the best onset median (69.0 vs 71.0 ms), **ar** the best p95 (115.0 vs 120.0 ms). Neither gap is clearly real (95 % intervals below). |
| **Words lost (test)** | 0 / 0 / 0 → tie. |
| **Main set** (the ar model's own fine-tuning data) | **ar-sep** beats mms-kalam on both: median 38.0 vs 39.0 ms, p95 109.7 vs 114.0 ms. This step is contaminated in ar's favour. |
| **Rule outcome** | ar-sep, as the commercial-edition candidate for Arabic-script words (3.0 keeps MMS, G8). |
| **After bias correction** (each aligner's constant CTC offset removed, a measurement only; nothing is baked into `align_w2v`) | Onsets: a tie between ar-sep and MMS. Offsets: ar-sep has the tighter spread (test IQR 52 vs 74 ms, p90 88.5 vs 149 ms). |
| **ar-sep vs the no-aligner baseline** (the jittered input, test set) | **Raw: no.** It is barely better on onsets (median 71 vs 75 ms) and **worse on offsets** (86 / 154.5 / 221.5 vs 74.6 / 135.0 / 142.8 ms). **Bias-corrected: yes on onsets** (17 / 47 / 57 vs 60 / 125 / 152 ms; main → test calibration 33 / 64 / 78 vs 63 / 118 / 145). **Yes on offset median and p90** (26 / 88.5 vs 75 / 135 ms), **level at p95** (139 vs 142.5 ms). So the aligner is only useful once its lead-in and hold are calibrated. That calibration must come from human labels in the 12b gate set, not from this one speaker; ASC's own two sets disagree by 30 ms. |
| **Strength of evidence** | One male MSA speaker, studio audio, partly the ar model's training data (see "Contamination"). It shows nothing about dialects, code-switching or real ASR times. The docs/legal §4 commercial gate (≥ MMS on median **and** p90 onset **and** % ≤ 50 ms) is not met strictly: +2 ms median, +1 ms p90, inside label noise. This benchmark does **not** close licence row M8. |

## Method

- **Corpus.** Arabic Speech Corpus v2.0 (Halabi). It is one male speaker, read MSA, 48 kHz audio and Praat TextGrids with a
  "words" tier at a nominal 10 ms grid. Most word boundaries sit at the 10 ms grid; some carry finer HMM-aligned
  values.
  - test set: 100 utterances, 1,256 words, 17.2 min;
  - main set: 1,813 utterances, 16,020 words, 229.1 min.

  Licence: free for research, commercial use by agreement. So it is benchmark-only: no audio, transcript or word text
  is in the repo, and `results.json` holds utterance file ids and numbers only.
- **Audio.** Decoded with upstream Kalam's own `audio.load_16k` (48 kHz → 16 kHz by 3-sample mean), loaded from
  `_upstream` by path. This is the same path the product uses.
- **Truth.** The "words" tier without pause labels `sil`, `sp`, `-`, empty, and `dist` (the README's corrupt marker).
  The brief named `sil` and `-`; `sp` (HTK short pause, 42 intervals) and `dist` (2) are pauses too. The word text is
  Buckwalter converted to Arabic script. ASC writes ث as `^`. Harakat, shadda, sukun and dagger alef are removed, as
  in an ASR transcript. 15 labels had stray characters (a trailing `-`, `.`, `5` or spaces); these were removed. No
  unknown characters remained, and no word became empty.
- **Input times.** Every variant gets the same input: the truth times jittered by a seeded uniform ±150 ms on both edges.
  - The seed is `numpy.random.default_rng([20261016, crc32(utterance id)])`.
  - The times are then made monotonic: s_i ≥ e_{i−1}, e_i ≥ s_i + 10 ms.
  - Finally they are clipped to the file.

  Because ASC words abut, the monotonic step pushes starts later. The input itself therefore has a +44/+50 ms onset
  bias (main/test). The aligners must undo it.
- **Variants.** All variants use the identical upstream algorithm: 25 s windows cut at the biggest gap, audio window
  ±1.5 s capped at mid-gap, `(x − mean)/(std + 1e-7)`, fallbacks 0.5 / 0.0, rounding to ms.
  - `mms-kalam-A0`: upstream `engine/kalam/align.py` itself, with torchaudio `forced_align` and the
    `MahmoudAshraf/mms-300m-1130-forced-aligner` @ `49402e95…` model (CC-BY-NC-4.0). Words are romanized by
    upstream `roman()`. This is the reference.
  - `mms-kalam-A1`: `whynot-cut/engine/reel/lib/align_w2v.py`, kind `mms`, with the numpy `forced_align`.
  - `ar`: `align_w2v` kind `ar`, the xlsr-53-arabic letter vocabulary (`ar_tokens`), no word delimiter.
  - `ar-sep`: the same as `ar`, with the model's `|` word-delimiter token between words.

  Devices: GPU fp32 (cuDNN deterministic, so A0 and A1 see identical kernels) and CPU (`CUDA_VISIBLE_DEVICES=-1`).
  The device choice is the upstream rule: CUDA when a 0.2 s probe pass works, otherwise CPU.
- **Metrics** (per word; all words of the set are counted, including lost ones):
  - |s_pred − s_true| (onset) and |e_pred − e_true| (offset): median, p90, p95 and mean, in ms;
  - the share of onsets within 20 / 50 / 100 ms;
  - the signed median (the bias);
  - words lost = a fallback (input times returned unchanged with score 0.5 or 0.0) or a predicted interval that does
    not overlap the true one;
  - mean score;
  - wall time with the model load measured separately. The torchaudio parity check is timed and excluded.
  - RTF (real-time factor) = wall time / audio duration;
  - peak GPU memory.

  A paired bootstrap resamples utterances 2,000 times; all variants see the same resampled utterances. It gives
  95 % intervals of each variant's difference to mms-kalam-A0.

## Parity evidence (all required checks pass, with one float32 rounding case)

| Check | Result |
|---|---|
| Unit tests `bash tools/test.sh -p test_align_w2v.py` | 23 OK. They cover: Viterbi = brute-force enumeration on 240 seeded cases; torchaudio tie fixtures and errors; `mms_tokens` = upstream `roman`; `_windows` = upstream; `align()` with a fake model. |
| numpy vs torchaudio, random emissions (`selftest`) | 50,000 cases, a quarter of them all-tie: 0 label mismatches, max score difference **0.0**, error cases identical. |
| numpy vs torchaudio on every real window (A1, ar, ar-sep; GPU) | 3 × 1,929 windows: 0 label mismatches, max score difference **0.0**. |
| numpy vs torchaudio on every real window (CPU) | 3 × 1,929 windows: 0 label mismatches, max score difference **0.0**. |
| A0 vs A1, word for word (s, e, score), GPU | Test set: 1,256 / 1,256 identical. Main set: 16,019 / 16,020 identical. **One word differs, in score only** (`ARA NORM  0581` word 4: times 3.304–3.444 s identical, score 0.992 vs 0.991). |
| A0 vs A1, word for word, CPU | **17,276 / 17,276 identical** (test 1,256, main 16,020). |
| Fix round 1 re-checks (GPU) | `runs/gpu-r1` (round-1 code, all variants): every aggregate and per-utterance row equals round 0. `runs/gpu-r1b` (after the per-word fallback was extended to kind "mms"): A0 vs A1 again test 1,256 / 1,256, main 16,019 / 16,020 (the same 0581 score); numpy = torchaudio on every window. |

The one-word cause was traced (scratch `diag581.py`):
- `forced_align` labels and frame log-probs are bit-identical to torchaudio.
- `np.exp` and `torch.exp` (SLEEF) differ by 1 ulp on 240 of the window's 442 frames.
- The word's mean probability lands exactly on 0.9915, so `round(…, 3)` goes the other way.
- Fed torch's exp values, `merge_tokens` reproduces A0 exactly.

This is float32 libm noise at a rounding boundary. The algorithm does not diverge, and word times are never affected.

## Results — GPU (RTX 4060 Laptop, fp32)

Errors are in ms. "bias" is the signed median (pred − true) of onset / offset. Load times depend on the order of the
runs and on the disk cache (A0 is loaded cold, the others warm), so they are not a model property.

### Test set (held-out utterances of the same single speaker the ar model was fine-tuned on; 100 utt, 1,256 words, 17.2 min)

| variant | onset med | p90 | p95 | mean | offset med | p90 | p95 | mean | onsets ≤20 / 50 / 100 ms | bias on / off | words lost | mean score | wall s | RTF | peak GPU MB |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| input (jittered) | 75.1 | 133.2 | 142.3 | 75.5 | 74.6 | 135.0 | 142.8 | 75.5 | 12.3 / 33.3 / 66.0 % | +50.4 / +2.3 | 0 | — | — | — | — |
| mms-kalam-A0 | **69.0** | 101.0 | 120.0 | 71.5 | 97.0 | 223.5 | 262.5 | 111.7 | 2.9 / 20.6 / 89.7 % | +68.5 / −97.0 | 0 | 0.860 | 10.0 | 0.0097 | 1764 |
| mms-kalam-A1 | 69.0 | 101.0 | 120.0 | 71.5 | 97.0 | 223.5 | 262.5 | 111.7 | 2.9 / 20.6 / 89.7 % | +68.5 / −97.0 | 0 | 0.860 | 10.2 | 0.0099 | 1766 |
| ar | 71.0 | 102.0 | **115.0** | 70.1 | 86.0 | 155.5 | 223.5 | 92.7 | 4.1 / 20.7 / 88.9 % | +71.0 / −86.0 | 0 | 0.972 | 10.2 | 0.0099 | 1766 |
| ar-sep | 71.0 | 102.0 | 116.0 | 70.3 | 86.0 | 154.5 | 221.5 | 92.2 | 4.1 / 20.6 / 88.7 % | +71.0 / −86.0 | 0 | 0.972 | 9.4 | 0.0091 | 1766 |

Paired bootstrap, difference to mms-kalam-A0 in ms, point [95 % interval]; negative = more accurate:

| variant | onset median | onset p95 | offset median | offset p95 |
|---|---:|---:|---:|---:|
| ar | +2.0 [+0.0, +3.0] | −5.0 [−12.0, +1.0] | −11.0 [−14.0, −8.0] | −39.0 [−66.0, −28.4] |
| ar-sep | +2.0 [+0.0, +3.0] | −4.0 [−11.0, +2.0] | −11.0 [−14.0, −8.0] | −41.0 [−67.2, −29.0] |
| input (jittered) | +6.1 [+1.4, +11.0] | +22.3 [+14.2, +29.7] | −22.4 [−27.2, −17.8] | −119.7 [−137.4, −105.7] |

### Main set (the ar model's fine-tuning data; 1,813 utt, 16,020 words, 229.1 min)

| variant | onset med | p90 | p95 | mean | offset med | p90 | p95 | mean | onsets ≤20 / 50 / 100 ms | bias on / off | words lost | mean score | wall s | RTF | peak GPU MB |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| input (jittered) | 74.3 | 134.6 | 142.2 | 74.5 | 75.0 | 133.8 | 141.8 | 74.5 | 12.9 / 32.9 / 68.4 % | +43.6 / −0.9 | 9 (0.056 %) | — | — | — | — |
| mms-kalam-A0 | 39.0 | 93.7 | 114.0 | 46.7 | 117.0 | 250.0 | 285.0 | 135.0 | 25.5 / 60.6 / 91.9 % | +38.0 / −117.0 | 4 (0.025 %) | 0.873 | 124.3 | 0.0090 | 1764 |
| mms-kalam-A1 | 39.0 | 93.7 | 114.0 | 46.7 | 117.0 | 250.0 | 285.0 | 135.0 | 25.5 / 60.6 / 91.9 % | +38.0 / −117.0 | 4 (0.025 %) | 0.873 | 133.4 | 0.0097 | 1766 |
| ar | 44.0 | 92.0 | **108.0** | 49.0 | 103.0 | 202.0 | 235.0 | 112.6 | 24.0 / 54.5 / 93.0 % | +34.0 / −103.0 | 3 (0.019 %) | 0.935 | 134.2 | 0.0098 | 1766 |
| ar-sep | **38.0** | 92.0 | 109.7 | 45.8 | 103.0 | 201.0 | 234.0 | 112.7 | 25.5 / 60.9 / 92.6 % | +38.0 / −103.0 | 3 (0.019 %) | 0.956 | 131.3 | 0.0096 | 1766 |

Paired bootstrap, difference to mms-kalam-A0, ms:

| variant | onset median | onset p95 | offset median | offset p95 |
|---|---:|---:|---:|---:|
| ar | +5.0 [+4.0, +6.0] | −6.0 [−8.0, −4.0] | −14.0 [−15.8, −13.0] | −50.0 [−53.6, −47.0] |
| ar-sep | −1.0 [−2.0, +0.0] | −4.3 [−7.0, −2.5] | −14.0 [−15.0, −13.0] | −51.0 [−54.0, −47.0] |
| input (jittered) | +35.3 [+33.3, +36.9] | +28.2 [+25.7, +30.6] | −42.0 [−44.2, −40.8] | −143.2 [−146.3, −139.8] |

ar-sep vs ar, onset: the test set is +0.0 [+0.0, +1.0] (median) and +1.0 [+0.0, +2.0] (p95). The main set is
−6.0 [−7.0, −5.0] (median) and +1.7 [+0.0, +2.1] (p95). The word delimiter mainly helps the median.

GPU wall times come from the first, least contended run, `runs/gpu`. The rerun `runs/gpu2`, with signed errors and the
bootstrap sidecar, gave identical accuracy numbers on every row (deterministic). Its wall times were 5–21 % higher
because the CPU run overlapped it.

numpy `forced_align` cost, summed over both sets (246 min of audio):

| run | numpy `forced_align` | torchaudio C++ (same windows) |
|---|---:|---:|
| `runs/gpu` (least contended) | 14–19 s | 1.3–1.5 s |
| `runs/gpu2` (contended) | 36–41 s | 2.6–2.8 s |

On one 1250-frame × 300-target window numpy needs 62 ms and torchaudio 7 ms. That is about 5–10 s of CPU per hour of
audio: acceptable, and open to optimisation later.

## Results — CPU (i7-14700HX, torch intra-op threads default)

Accuracy on CPU equals GPU on every row and metric of both sets, with one exception: for mms-kalam (A0 and A1) on the
main set, the onset ≤20 / ≤50 ms shares are 25.50 / 60.61 % on CPU vs 25.51 / 60.62 % on GPU. One or two words move
by one frame between cuDNN and MKL float results; medians, p95s, words lost and scores are unchanged. The bootstrap
intervals on CPU are identical to the GPU ones above.

The CPU run was `runs/cpu2`: one uninterrupted run with all 4 variants, 6,652 s in total. "proc CPU s" is the process
CPU time over all threads.

| set | variant | onset med / p95 | offset med / p95 | lost | wall s | RTF | proc CPU s | load s |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| test | mms-kalam-A0 | 69.0 / 120.0 | 97.0 / 262.5 | 0 | 103.3 | 0.100 | 1,201 | 1.13 |
| test | mms-kalam-A1 | 69.0 / 120.0 | 97.0 / 262.5 | 0 | 90.5 | 0.088 | 1,143 | 0.08 |
| test | ar | 71.0 / 115.0 | 86.0 / 223.5 | 0 | 108.0 | 0.105 | 1,209 | 1.09 |
| test | ar-sep | 71.0 / 116.0 | 86.0 / 221.5 | 0 | 77.0 | 0.075 | 940 | 0.27 |
| main | mms-kalam-A0 | 39.0 / 114.0 | 117.0 / 285.0 | 4 | 1,252.7 | 0.091 | 14,788 | |
| main | mms-kalam-A1 | 39.0 / 114.0 | 117.0 / 285.0 | 4 | 1,234.9 | 0.090 | 14,631 | |
| main | ar | 44.0 / 108.0 | 103.0 / 235.0 | 3 | 1,146.3 | 0.083 | 13,540 | |
| main | ar-sep | 38.0 / 109.7 | 103.0 / 234.0 | 3 | 2,616.0 | 0.190 | 23,297 | |

The CPU wall times are upper bounds. The PC was shared with other sessions' jobs, including a full test suite that
took RAM to 90 %. The ar-sep main-set row ran under the heaviest load (heavy.sh logged an 88 % RAM peak for this
job), and its process CPU time rose with it (23,297 s vs 13,540 s for ar). So that RTF says nothing about the
model. ar-sep differs from ar by one extra target token per word.

On comparable load the two models cost the same: CPU RTF is about 0.08–0.10, i.e. ≈ 5–6 min of wall time per hour of
audio, against about 0.01 on the GPU. numpy `forced_align` on CPU took 15 s for each of A1 and ar over 246 min of
audio, and 30 s for ar-sep under load. torchaudio took 1.7–3.0 s.

The earlier v1 CPU run (`runs/cpu`, which died at a usage limit) had shown A1 at RTF 0.32 vs A0 0.11. cpu2 shows that
was machine load (A1 0.088–0.090 vs A0 0.091–0.100), not the port.

## Raw vs bias-corrected (I2)

"Bias" is the signed median error, pred − true: CTC's constant lead or lag. "Debiased" is |error − bias|, the
spread a perfectly calibrated constant would leave.
- "own" uses each set's own median. It is an oracle: the best a constant can do on that set.
- "main → test" applies the main set's median to the test set: a calibration that never sees the test labels.

The input row is the **no-aligner baseline**. These are measurements only: no lead-in or hold is applied in
`align_w2v`. The numbers come from the GPU round-1 run (`runs/gpu-r1`, identical to round 0 on every row); CPU gives
the same.

Test set (held-out utterances, same speaker), ms (med / p90 / p95):

| variant | onset raw | onset bias | onset debiased (own) | onset debiased (main → test) | onset IQR | offset raw | offset bias | offset debiased (own) | offset debiased (main → test) | offset IQR |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| no aligner (jittered input) | 75.1 / 133.2 / 142.3 | +50.4 | 60.3 / 124.9 / 152.2 | 63.2 / 118.1 / 145.3 | 125.8 | 74.6 / 135.0 / 142.8 | +2.3 | 74.9 / 135.2 / 142.5 | 74.7 / 135.0 / 143.0 | 149.7 |
| mms-kalam (A0 = A1) | 69.0 / 101.0 / 120.0 | +68.5 | 15.5 / 47.0 / 64.8 | 32.0 / 65.0 / 84.2 | 31.0 | 97.0 / 223.5 / 262.5 | −97.0 | 37.0 / 149.0 / 175.5 | 44.0 / 147.5 / 182.2 | 73.5 |
| ar | 71.0 / 102.0 / 115.0 | +71.0 | 17.0 / 47.0 / 57.0 | 37.0 / 68.0 / 82.0 | 33.0 | 86.0 / 155.5 / 223.5 | −86.0 | 26.0 / 90.5 / 140.2 | 31.0 / 96.0 / 125.2 | 53.0 |
| **ar-sep** | 71.0 / 102.0 / 116.0 | +71.0 | 17.0 / 47.0 / 57.0 | 33.0 / 64.0 / 78.0 | 33.0 | 86.0 / 154.5 / 221.5 | −86.0 | 26.0 / 88.5 / 139.0 | 31.0 / 95.0 / 124.0 | 52.2 |

Main set (the ar model's training data), ms (med / p90 / p95), own-median debiasing:

| variant | onset raw | onset bias | onset debiased | offset raw | offset bias | offset debiased |
|---|---:|---:|---:|---:|---:|---:|
| no aligner | 74.3 / 134.6 / 142.2 | +43.6 | 64.1 / 129.5 / 151.9 | 75.0 / 133.8 / 141.8 | −0.9 | 74.9 / 133.8 / 141.7 |
| mms-kalam | 39.0 / 93.7 / 114.0 | +38.0 | 23.0 / 61.0 / 82.0 | 117.0 / 250.0 / 285.0 | −117.0 | 44.0 / 136.0 / 168.0 |
| ar | 44.0 / 92.0 / 108.0 | +34.0 | 27.0 / 93.0 / 110.0 | 103.0 / 202.0 / 235.0 | −103.0 | 37.2 / 109.0 / 135.0 |
| ar-sep | 38.0 / 92.0 / 109.7 | +38.0 | 23.0 / 56.0 / 73.0 | 103.0 / 201.0 / 234.0 | −103.0 | 37.0 / 106.0 / 133.0 |

**Does ar-sep beat the no-aligner baseline after bias correction?**
- **Onsets: yes, clearly.** Test 17 / 47 / 57 ms vs 60 / 125 / 152 ms (own); 33 / 64 / 78 vs 63 / 118 / 145 ms
  (main → test).
- **Offsets: yes at the median and p90.** 26 / 88.5 vs 75 / 135 ms (own); 31 / 95 vs 75 / 135 ms (main → test).
  **Level at p95**: 139 vs 142.5 ms (own), 124 vs 143 ms (main → test).
- **Without bias correction, no.** Onsets are barely better (71 vs 75 ms median) and offsets are worse (86 / 154.5 /
  221.5 vs 74.6 / 135.0 / 142.8 ms).

So ar-sep only helps captions once a lead-in and hold are calibrated. That calibration belongs to Task 12b, on human
labels from many speakers.

**ar-sep vs MMS after bias correction.**
- Onsets are a tie: 17 vs 15.5 ms median, 47 vs 47 ms p90, 57 vs 64.8 ms p95.
- ar-sep's offsets are tighter: 26 vs 37 ms median, 88.5 vs 149 ms p90, IQR 52 vs 74 ms.

## Fix round 1: what changed in `align_w2v` and what it measures

- **I1 — per-word fallback, for every model kind.**
  - A word the model cannot represent is left out of the targets and keeps its transcriber time:
    - kind "ar": Latin, digits, other scripts (`ar_readable` False, so "بالـMRI" counts too);
    - kind "mms": a script `roman()` cannot read.
  - It is moved only as far as needed to stay after the previous word and before the next aligned word. It gets score
    0.5 and `aligned: false`.
  - The window's other words are aligned as usual.
  - A clip with no readable word runs no model. Under "ar" that includes an English-only clip.
  - Upstream fell back for the whole window instead. This is the first A0 deviation, and it applies only where upstream
    gave up.

  ASC has no such words, so its numbers are unchanged: gpu-r1 = gpu2 on every row, and A0 vs A1 was re-checked after
  the change in `runs/gpu-r1b` (see the parity table). Round 0 would have dropped the whole 25 s window for a single
  "MRI" or "2024" under "ar". The Kalam generality audit measured 33/33 words unaligned on a mixed clip.
- **I5 — never raises.**
  - A window whose targets cannot fit its frames (len + repeats > T, e.g. 40 × ه in 1.25 s) keeps the transcriber's
    times with score 0.0 and `aligned: false`. Upstream raised out of `align()` here; this is the second A0 deviation,
    and it only touches inputs on which A0 crashed.
  - 0 such windows on ASC (errors 0 in every run).
- **M1.** NFKC for Arabic presentation forms and ligatures (ﷺ ﻻ ﷲ), and ڨ→ق, ڭ→ك.
- **M4.** `align(audio_16k, words)` raises `ValueError` for non-mono or non-float audio.
- **I4 — harakat, dagger alef, Quranic marks and tatweel are stripped in the tokenizer** (ruling). The CPU re-run
  (`runs/cpu-r1-voc`) used ASC's fully vocalised text as input. Before is ar-sep with the round-0 tokenizer
  (harakat kept as targets); after is ar-sep with round 1 (stripped). ms (med / p90 / p95):

  | set | variant | onset raw | onset debiased (own) | offset raw | offset bias | offset debiased (own) | offset ≤ 50 ms debiased | words lost | RTF (CPU) |
  |---|---|---:|---:|---:|---:|---:|---:|---:|---:|
  | test | before (harakat kept) | 70.5 / 101.0 / 114.0 | 16.5 / 46.5 / 56.5 | **38.0** / 123.5 / 149.3 | −37.0 | 25.0 / 90.0 / **115.0** | **77.4 %** | 0 | 0.160 |
  | test | after (stripped) | 71.0 / 102.0 / 116.0 | 17.0 / 47.0 / 57.0 | 86.0 / 154.5 / 221.5 | −86.0 | 26.0 / 88.5 / 139.0 | 72.6 % | 0 | 0.118 |
  | main | before (harakat kept) | 38.0 / 91.0 / 108.0 | 22.6 / 55.6 / 72.4 | **58.0** / 144.0 / 175.0 | −57.0 | 29.0 / 96.0 / **127.0** | **73.1 %** | 3 | 0.133 |
  | main | after (stripped) | 38.0 / 92.0 / 109.7 | 23.0 / 56.0 / 73.0 | 103.0 / 201.0 / 234.0 | −103.0 | 37.0 / 106.0 / 133.0 | 62.1 % | 3 | 0.121 |

  - "After" on vocalised input equals plain ar-sep exactly: the stripped tokens are identical.
  - **Measured fact against the ruling's premise.** On this one MSA speaker, who pronounces the case endings, keeping
    the harakat helps **word ends**. Raw offset median 38 vs 86 ms; bias-corrected p95 115 vs 139 ms (test). The final
    vowel becomes a target and pulls the end to where the speaker stops. Onsets do not change (≤ 0.5 ms).
  - Stripping is cheaper (RTF 0.118 vs 0.160), lowers the I5 risk (+80 % targets on fully vocalised text) and matches
    unvocalised ASR transcripts exactly.
  - The ruling stands in the code. Whether vocalised input (Quranic verses, hadith) should keep its harakat is a
    question for Task 12b, measured on real vocalised speech from many speakers.

## Caveats

1. **Contamination (measured fact that contradicts the brief's assumption).** The brief assumed the xlsr model was
   "fine-tuned on Common Voice MSA". Its model card (rev `af46c2d8…`) says it was fine-tuned on "the train and
   validation splits of Common Voice 6.1 and Arabic Speech Corpus".
   - The ASC train split is exactly the main set used here. **Main-set numbers therefore overstate ar/ar-sep**, and
     the brief's main-set tie-break is biased in their favour.
   - The test set is held out by utterance but is the **same single speaker**. The ar model is speaker-adapted to it;
     MMS-FA (Meta's MMS forced-alignment data) is not.

   The test-set comparison (held-out utterances, same speaker) is therefore still tilted towards ar. The utterance
   bootstrap measures within-speaker noise only: effective n = 1 speaker, 1 dialect, 1 microphone. Even so, ar does
   not beat MMS on test-set onsets: the median favours MMS by 2 ms, and p95 favours ar by 4–5 ms with an interval
   through 0.
2. **One speaker, read MSA, studio audio.** Kalam's real input is mostly Egyptian colloquial, with many speakers,
   room noise and music. This benchmark cannot show how either model behaves there.
3. **The truth is not ground truth.** The labels look forced-aligned by an HMM system: 10 ms grid plus finer HMM
   values, with boundaries at segment starts. Errors below about 10–20 ms are not resolvable, so differences of
   1–2 ms between variants are not meaningful.
4. **CTC timing bias** (both models, both devices). Onsets land late (signed median +34…+71 ms) and offsets early
   (−86…−117 ms), because CTC emits a token on its most confident frames, not where the phone begins or ends.
   - Uncalibrated, the bias dominates what a user sees: raw ar-sep offsets are worse than the no-aligner input (see
     "Raw vs bias-corrected").
   - The bias does not transfer between sets. MMS, which never saw ASC, has an onset bias of +38 ms on main and
     +68.5 ms on test, so the two sets' labels follow different boundary conventions.
   - Any lead-in or hold must therefore be calibrated on the 12b gate set's human labels. Nothing is baked into
     `align_w2v`: a constant fitted to this one speaker would be exactly the case-specific tuning that is not
     allowed.
5. **Input jitter model.** Uniform ±150 ms plus the monotonic rule gives a +44/+50 ms onset bias in the input. Real
   Whisper or Parakeet word times have their own error shape. The aligner sees the input only through the window
   bounds (±1.5 s), but the no-aligner baseline is only as realistic as the jitter. Task 12b uses real ASR word
   times (`--input-times`).
6. **Device.** GPU and CPU give the same results to the reported precision, except 1–2 MMS main-set words that move by
   one frame (the ≤20/50 ms shares differ by 0.01 points). The ranking and the recommendation do not depend on the
   device.

## Not shown by this benchmark

- dialects (Egyptian, Gulf, Levantine, Maghrebi);
- multiple speakers;
- code-switched Arabic/English and digits (ASC has none, which is why round 0 missed the window-wide fallback);
- noise and music;
- 44.1 kHz and 8 kHz sources (only the 48 → 16 kHz path ran);
- real ASR word times;
- English or other-script clips (§4 needs an English candidate as well, e.g. `facebook/wav2vec2-base-960h` or
  Parakeet's word times; none is measured yet);
- any annotator-agreement figure for the labels.

Task 12b covers these.

## Licence consequences (owner decision G8, docs/legal §3–§4)

- **v3.0.0 (full trial edition) keeps MMS-300m** (G8). Nothing is swapped for licence reasons in 3.0. Its
  CC-BY-NC-4.0 licence is the open pre-sale row M8 for the commercial edition only.
- **ar-sep as the commercial-edition candidate for Arabic (provisional, §4).** The model is Apache-2.0, built on `facebook/wav2vec2-large-xlsr-53`
  (Apache-2.0). Its fine-tune data are Common Voice 6.1 (CC0) and the Arabic Speech Corpus.
  - Two sources disagree on ASC's licence:
    - the corpus README (v2.0, as downloaded here) says "free for research purposes … Commercial use only allowed
      after agreement with OWNER";
    - docs/legal/third-party-licences.md lists the HF dataset `halabi2016/arabic_speech_corpus` as CC-BY-4.0 with a
      credit line.

    Whether either reaches weights trained on the corpus is a question for the owner and the licence audit
    (Addendum G). If ar ships in the commercial edition, the notices carry the model licence plus the ASC CC-BY
    credit line.
  - The model is downloaded at first use, pinned to rev `af46c2d8531b8dcbb5e23b952f739b372c2e5d2d`, and not bundled.
  - **That revision ships only `pytorch_model.bin` (pickle), with no safetensors.** transformers ≥ 4.50 refuses
    `.bin` under torch < 2.6, and the safe `weights_only` load needs torch ≥ 2.6. Executor diff note (M3):
    - pin runtime torch ≥ 2.6;
    - verify the blob's sha256 at install;
    - optionally convert it once to safetensors locally and load with `use_safetensors=True`.
  - `align_w2v` needs no torchaudio at all.
- **Commercial edition, MMS's replacement.** The §4 bake-off decides it. ar-sep must pass §4's test against MMS
  (median and p90 onset and % within 50 ms, Arabic and English) after Task 12b, and English needs its own candidate.
  §3 lists the routes if no candidate passes:
  - FastConformer CTC (CC-BY-4.0) through our Viterbi;
  - stable-ts (MIT);
  - a commercial MMS licence from Meta.
- **Either way.** The GPL-3.0 port `align_w2v.py` replaces torchaudio's removed `forced_align` and has numpy as its
  only runtime dependency. torch and transformers load lazily, only when a model runs.

## Reproduce (scratch venv, never the engine runtime)

```
set HF_HOME=D:\ClaudeData\Temp\wnc-p4\align\hf & set HF_HUB_OFFLINE=1
heavy.sh job g-align-selftest -- <venv>\python -B adobe/tools/kalam/bench/g_align.py selftest --out runs/selftest
heavy.sh gpu g-align         -- <venv>\python -B adobe/tools/kalam/bench/g_align.py run --out runs/gpu
CUDA_VISIBLE_DEVICES=-1 heavy.sh job g-align-cpu2 -- <venv>\python -B adobe/tools/kalam/bench/g_align.py run --out runs/cpu2
<venv>\python -B adobe/tools/kalam/bench/g_align.py report --gpu runs/gpu2/results.json --cpu runs/cpu2/results.json
# fix round 1
heavy.sh gpu g-align-r1-gpu -- <venv>\python -B adobe/tools/kalam/bench/g_align.py run --out runs/gpu-r1
CUDA_VISIBLE_DEVICES=-1 heavy.sh job g-align-r1-cpu-voc -- <venv>\python -B adobe/tools/kalam/bench/g_align.py run --out runs/cpu-r1-voc --text buckwalter-vocalised --variants ar-sep-harakat,ar-sep
<venv>\python -B adobe/tools/kalam/bench/g_align.py report --gpu runs/gpu-r1/results.json --cpu runs/cpu-r1-voc/results.json
```

Versions:
- Python 3.12.15, torch 2.8.0+cu128, torchaudio 2.8.0+cu128, transformers 4.56.2;
- numpy 2.3.5 in the venv, 2.5.4 in the engine runtime;
- NVIDIA driver 617.42.

Seed 20261016, jitter ±0.150 s. `run` checkpoints each finished variant (`partial/`, numbers only) and resumes after an
interruption.

`g_align.py` was written for ASC, and its defaults are ASC's. Fix round 1 (M6) adds the options another corpus needs:
- `--set-dir NAME=DIR` (`wav/` + `textgrid/` with a "words" tier);
- `--text buckwalter|buckwalter-vocalised|arabic`;
- `--pauses`;
- `--input-times DIR` for real transcriber word times matched one-to-one to the truth words.

Matching real ASR words to the truth words, and multi-tier or other label formats, are left to Task 12b.
