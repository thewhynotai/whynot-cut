---
name: audio-craft
description: "Reference for the audio-engineer agent (preloaded). Not for direct use."
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
4. Proves no speech was cut, in ±3 s windows around every cut, including a removed lead-in or tail. Close cuts share
   one window of ≤ 20 s, and a long removed span is read in ≤ 20 s pieces. The same Whisper model reads the uncut
   window and the same window with the cuts applied, with identical, deterministic settings (temperature 0), and the
   two readings are compared. A word of the uncut reading missing next to a cut is a bad cut, and so is any word heard
   inside a long removed span. `ok` needs no missing word, ≥ 85 % of the words matched and every window read (words
   heard, audio not shorter than the span). Otherwise the verdict is "inconclusive" and the cuts need the editor's
   ear. Whisper can invent words in silence, so a word that only shows up where the audio sits at the noise floor is
   reported as a possible hallucination: the verdict is inconclusive, never a pass. `windows` in `cut-verification.json` lists each window with its word counts. Pauses the edit protects
   (`global.remove_pauses.protect`) are not cut, so they are not tested.

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

Details: `${CLAUDE_SKILL_DIR}/references/sound-design.md`.
