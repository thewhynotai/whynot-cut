<!-- SPDX-License-Identifier: GPL-3.0-or-later -->
<!-- © 2026 The Why Not AI (thewhynot.ai) -->

# R-6B.1 Alignment contract in Kalam + the licence-clean Arabic aligner evaluation

Phase 6B (with Phase 4 Task 18b, G-ALIGN by measurement). Owner: tools track (`lib/align_w2v*.py`) / executor.

## Source-R behaviour

- Forced alignment is optional and aligns **reviewed text only**.
- Phrases must be ordered, non-overlapping and inside the source bounds; language Arabic or English.
- Pinned model revisions; CPU only (GPU explicitly refused).
- It never runs speech recognition, never edits text and never interpolates unresolved words; the output is a draft
  for listening review.
- It runs in a project-local virtual environment; the cache is keyed by the source sha256 + the request.
- Its Arabic model is the third-party Hugging Face model `jonatasgrosman/wav2vec2-large-xlsr-53-arabic` (stated
  Apache-2.0; verify the model card), and `facebook/wav2vec2-base-960h` for English. These are public third-party
  models, not Source-R names. Task 18b pins the exact revision it measures (commit hash) and its file hashes in our
  lock.

## Our version

### Contract (Kalam)
1. Input: reviewed words (transcript-editor output) with phrase boundaries; language per phrase (`ar`, `en`, mixed
   split into runs).
2. Validation: phrases ordered, non-overlapping, in bounds; refused otherwise with the phrase named.
3. Never: run ASR, edit text, interpolate unresolved words. Unresolved words keep their ASR timing and are flagged
   `align: unresolved` for review.
4. Output: word times + per-word alignment score + a provenance manifest (model id, revision, licence, device, source
   sha256, request hash); cache keyed by source sha256 + request hash under the engine home.
5. **GPU first** (CUDA on Windows, MPS/MLX on Mac), CPU fallback (R-T4); never CPU-only by design.

### Evaluation (G-ALIGN, Task 18b)
- Measure both aligners on our Arabic word-timing set: the current MMS-300m CTC aligner (non-commercial licence) and
  the Apache-2.0 Arabic wav2vec2 model: word-boundary error (median / p95 ms), words lost, speed on GPU and CPU.
- Keep the more accurate; each model keeps its own licence, is downloaded at install with its notice, and is never
  re-licensed. A model with non-commercial terms says so in THIRD-PARTY-NOTICES and the guide.

## Acceptance
Contract tests (refusals, no interpolation, provenance manifest, cache key); a measured table in `docs/benchmark/`;
the choice recorded in PROGRESS; notices updated (Task 18).
