---
name: audio-craft
description: "This skill should be used when cleaning dialogue or removing pauses in a whynot-cut project — noise, hum, loudness, multi-mic selection, pause detection, proving no speech was cut. Knowledge for the audio-engineer agent."
user-invocable: false
---

# Audio craft

```bash
reel audio-clean --root "<CLIENT>" --video-id <ID> [--min-pause 250] [--pad 80] [--nr 16|24] [--hum auto|off|50|60] [--no-verify]
```
It needs `02_transcription/transcript.json` with word times, so transcribe first.

**What it does:**
1. **Measures the source first** (`source_assessment` and `decisions` in the report):
   - identical channels (dual mono, a finished mix) or a mono file → one channel;
   - otherwise the best mic per transcript segment, for multi-mic shoots;
   - mains hum (50 or 60 Hz) measured in the pauses → notches only on the harmonics that stand out;
   - already clean (≥ 40 dB speech-to-noise, e.g. a mastered episode) → **no** spectral denoise, which would only add artefacts.
2. Chain: high-pass 90 Hz (twice) → [hum notches] → [`afftdn` denoise, 24 dB] → plain gain + true-peak limiter to −14 LUFS.
3. Detects pauses on the **cleaned** audio (the noise hid them before). Each pause keeps 80 ms of breath at both ends.
4. Re-transcribes the tightened audio in ≤ 20 s chunks split at the cuts (one long decode can skip a 30 s window and fake
   a lost sentence) and compares the word sequences, to prove no speech was cut. `ok` needs no missing word near a cut
   and ≥ 85 % of the words matched; otherwise the verdict is "inconclusive" and the cuts need the editor's ear.

**Outputs** (`06_audio/dialogue/`):
- `dialogue_clean.wav` (placed on A1/A2 and linked to V1; the original camera audio stays muted on A7/A8)
- `pauses.json`
- `cut-verification.json`
- `dialogue-clean-report.json`
- spectrograms in `08_quality_control/audio/`

**Check before you report:**
- The speech-to-noise figure improved (or, for an already-clean source, stayed). A first attempt once made it worse (16.6 → 10.2 dB with nf −40). Measure every time.
- View `spectrogram_before.png` and `spectrogram_after.png`: the hum lines should be gone, and the speech harmonics should still be there.
- `cut-verification.json` has `ok: true` and an empty `missing`. If Whisper "misses" a loanword, check whether it's also missing from the raw-audio transcript before calling it a bad cut.
- Note any mic surprises. On C0238 the question was read by an off-camera interviewer on ch2, not by the doctor.

You can't hear the result. Say so, and give the editor the knobs for a gentler result: `nr`, `--min-pause`, `--pad`.

Details: `references/sound-design.md`.
