---
name: audio-craft
description: "This skill should be used when cleaning dialogue or removing pauses in a whynot-cut project — noise, hum, loudness, multi-mic selection, pause detection, proving no speech was cut. Knowledge for the audio-engineer agent."
user-invocable: false
---

# Audio craft

```bash
reel audio-clean --root "<CLIENT>" --video-id <ID> [--min-pause 250] [--pad 80] [--no-verify]
```
It needs `02_transcription/transcript.json` with word times, so transcribe first.

**What it does:**
1. Picks the best mic per transcript segment, for multi-mic shoots.
2. Applies the chain: high-pass 90 Hz (twice), notches at 100–500 Hz for mains hum, `afftdn` adaptive denoise, gentle compression, then two-pass loudnorm to −14 LUFS / −1.5 dBTP.
3. Detects pauses on the **cleaned** audio (the noise hid them before). Each pause keeps 80 ms of breath at both ends.
4. Re-transcribes the tightened audio with a vocabulary prompt and compares the word sequences, to prove no speech was cut.

**Outputs** (`06_audio/dialogue/`):
- `dialogue_clean.wav` (placed on A1/A2 and linked to V1; the original camera audio stays muted on A7/A8)
- `pauses.json`
- `cut-verification.json`
- `dialogue-clean-report.json`
- spectrograms in `08_quality_control/audio/`

**Check before you report:**
- The speech-to-noise figure improved. A first attempt once made it worse (16.6 → 10.2 dB with nf −40). Measure every time.
- View `spectrogram_before.png` and `spectrogram_after.png`: the hum lines should be gone, and the speech harmonics should still be there.
- `missing` in `cut-verification.json` is empty. If Whisper "misses" a loanword, check whether it's also missing from the raw-audio transcript before calling it a bad cut.
- Note any mic surprises. On C0238 the question was read by an off-camera interviewer on ch2, not by the doctor.

You can't hear the result. Say so, and give the editor the knobs for a gentler result: `nr`, `--min-pause`, `--pad`.

Details: `references/sound-design.md`.
