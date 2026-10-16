# G-ALIGN — which forced aligner places WhyNot Kalam's Arabic words more accurately (3.0 Task 18b)

Measured 2026-10-16 on the development PC (i7-14700HX, RTX 4060 Laptop 8 GB, Windows 11). Every utterance of both
sets was run on both devices; there was no sampling. The numbers below come from real runs of
`adobe/tools/kalam/bench/g_align.py`. The raw `results.json` files stay in the scratch folder (see "Reproduce").

## Answer

| | |
|---|---|
| **Rule (brief)** | The winner on the test set's onset median **and** p95. A tie goes to words lost, then to the main set. |
| **Test set (held out)** | Split: **mms-kalam** has the best onset median (69.0 vs 71.0 ms); **ar** has the best p95 (115.0 vs 120.0 ms). Neither gap is clearly real (95 % intervals below). |
| **Words lost (test)** | 0 / 0 / 0 → tie. |
| **Main set** | **ar-sep** beats mms-kalam on both: median 38.0 vs 39.0 ms, p95 109.7 vs 114.0 ms. **ar** wins p95 only and loses the median (44.0 ms). |
| **Rule outcome** | **ar-sep**: `Aligner("ar", word_sep=True)` with `jonatasgrosman/wav2vec2-large-xlsr-53-arabic` @ `af46c2d8…`, Apache-2.0. |
| **Strength of evidence** | **Weak for onsets, strong for offsets.** The main-set tie-break is contaminated: the ar model was fine-tuned on that exact data (see "Contamination"). Onsets are a statistical tie on held-out audio. Word ends are clearly better with ar/ar-sep, on held-out audio too: offset p95 −41 ms, 95 % interval [−67, −29]. |

**Recommendation.** Ship **ar-sep** as Kalam's aligner and drop the CC-BY-NC MMS checkpoint. The reasons:
- on held-out audio it is no worse on word starts, within about 2 ms at the median;
- it is clearly better on word ends;
- it loses no more words;
- it removes the only non-commercial licence from Kalam's model chain.

The onset decision rests on a single-speaker MSA corpus that the ar model partly trained on. Before 3.0 is final, run the same benchmark on one held-out, multi-speaker set with word timings, ideally Egyptian Arabic (Kalam's real input). `g_align.py` takes any Praat word-tier corpus with a path change. If that run reverses the onset result, the shipped `Aligner` switches with one argument (`kind`).

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

The one-word cause was traced (scratch `diag581.py`):
- `forced_align` labels and frame log-probs are bit-identical to torchaudio.
- `np.exp` and `torch.exp` (SLEEF) differ by 1 ulp on 240 of the window's 442 frames.
- The word's mean probability lands exactly on 0.9915, so `round(…, 3)` goes the other way.
- Fed torch's exp values, `merge_tokens` reproduces A0 exactly.

This is float32 libm noise at a rounding boundary. The algorithm does not diverge, and word times are never affected.

## Results — GPU (RTX 4060 Laptop, fp32)

Errors are in ms. "bias" is the signed median (pred − true) of onset / offset. Load times depend on the order of the
runs and on the disk cache (A0 is loaded cold, the others warm), so they are not a model property.

### Test set (held out from the ar model's training; 100 utt, 1,256 words, 17.2 min)

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

## Caveats

1. **Contamination (measured fact that contradicts the brief's assumption).** The brief assumed the xlsr model was
   "fine-tuned on Common Voice MSA". Its model card (rev `af46c2d8…`) says it was fine-tuned on "the train and
   validation splits of Common Voice 6.1 and Arabic Speech Corpus".
   - The ASC train split is exactly the main set used here. **Main-set numbers therefore overstate ar/ar-sep**, and
     the brief's main-set tie-break is biased in their favour.
   - The test set is held out by utterance but is the **same single speaker**. The ar model is speaker-adapted to it;
     MMS-FA (Meta's MMS forced-alignment data) is not.

   The held-out comparison is therefore still tilted towards ar. Even so, ar does not beat MMS on test-set onsets: the
   median favours MMS by 2 ms, and p95 favours ar by 4–5 ms with an interval through 0.
2. **One speaker, read MSA, studio audio.** Kalam's real input is mostly Egyptian colloquial, with many speakers,
   room noise and music. This benchmark cannot show how either model behaves there.
3. **The truth is not ground truth.** The labels look forced-aligned by an HMM system: 10 ms grid plus finer HMM
   values, with boundaries at segment starts. Errors below about 10–20 ms are not resolvable, so differences of
   1–2 ms between variants are not meaningful.
4. **CTC timing bias** (both models, both devices). Onsets land late (signed median +34…+71 ms) and offsets early
   (−86…−117 ms). CTC emits a token on its most confident frames, not where the phone begins or ends. This is
   systematic and shared, so it does not decide the comparison. It does matter for captions: a constant lead-in
   (onset −40 ms) and a hold on the last token (offset +80…+100 ms) would cut both errors. That is a separate tuning
   task, not part of the A0 port.
5. **Input jitter model.** Uniform ±150 ms plus the monotonic rule gives a +44/+50 ms onset bias in the input. Real
   Whisper or Parakeet word times have their own error shape. The aligner sees the input only through the window
   bounds (±1.5 s), so the result is insensitive to the jitter's exact form.
6. **Device.** GPU and CPU give the same results to the reported precision, except 1–2 MMS main-set words that move by
   one frame (the ≤20/50 ms shares differ by 0.01 points). The ranking and the recommendation do not depend on the
   device.

## Licence consequences

- **Shipping ar-sep.** The model is Apache-2.0, built on `facebook/wav2vec2-large-xlsr-53` (Apache-2.0). Its training
  data are Common Voice (CC0) and the Arabic Speech Corpus.
  - ASC's own licence restricts commercial use of the corpus. Whether that reaches weights trained on it is a legal
    question; the model's licence makes no such restriction. Record it in the third-party notices.
  - The notices need the model licence and attribution. The model is downloaded at first use, pinned to rev
    `af46c2d8531b8dcbb5e23b952f739b372c2e5d2d`, and not bundled.
  - `align_w2v` needs no torchaudio at all.
- **Keeping mms-kalam.** CC-BY-NC-4.0 forbids commercial use. That conflicts with the paid edition (Addendum G),
  which is why the owner's I1 rule made it a measurement question. MMS also needs its romanizer: upstream `roman()` is
  a coarse Egyptian-ish map in which ق→a and ع→a.
- **Either way.** The GPL-3.0 port `align_w2v.py` replaces torchaudio's removed `forced_align` and has numpy as its
  only runtime dependency. torch and transformers load lazily, only when a model runs.

## Reproduce (scratch venv, never the engine runtime)

```
set HF_HOME=D:\ClaudeData\Temp\wnc-p4\align\hf & set HF_HUB_OFFLINE=1
heavy.sh job g-align-selftest -- <venv>\python -B adobe/tools/kalam/bench/g_align.py selftest --out runs/selftest
heavy.sh gpu g-align         -- <venv>\python -B adobe/tools/kalam/bench/g_align.py run --out runs/gpu
CUDA_VISIBLE_DEVICES=-1 heavy.sh job g-align-cpu2 -- <venv>\python -B adobe/tools/kalam/bench/g_align.py run --out runs/cpu2
<venv>\python -B adobe/tools/kalam/bench/g_align.py report --gpu runs/gpu2/results.json --cpu runs/cpu2/results.json
```

Versions:
- Python 3.12.15, torch 2.8.0+cu128, torchaudio 2.8.0+cu128, transformers 4.56.2;
- numpy 2.3.5 in the venv, 2.5.4 in the engine runtime;
- NVIDIA driver 617.42.

Seed 20261016, jitter ±0.150 s. `run` checkpoints each finished variant (`partial/`, numbers only) and resumes after an
interruption.
