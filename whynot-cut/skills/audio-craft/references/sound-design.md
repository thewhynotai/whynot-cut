# Sound Design

- **Dialogue (A1/A2): cleaned** by `reel audio-clean` → `06_audio/dialogue/dialogue_clean.wav`, linked to V1, same clock as the camera file.
  The chain follows a measurement of the source: best mic per transcript segment (multi-mic shoots; one channel when both
  carry the same signal) → 2× high-pass 90 Hz → narrow notches only on mains-hum harmonics that stand out in the pauses
  (C0238: 100–500 Hz, hum was 89 % of residual noise) → afftdn nr 24 / nf −32 unless the source is already clean → gain +
  true-peak limiter to −14 LUFS.
  Evidence (C0238, camera mics): speech-to-noise 16.6 → 22.8 dB at −14.6 LUFS. EP02_R02 (a mastered episode, dual mono,
  55 dB S/N): one channel, one 100 Hz notch, no denoise, 56.9 → 58.9 dB at −14.3 LUFS. Spectrograms in
  `08_quality_control/audio/`. Original camera audio stays on A7/A8 **disabled** for A/B.
- **Pause removal:** `audio-clean` detects pauses on the CLEANED audio (noise hid them before), keeps 80 ms breath each side,
  then re-transcribes the tightened audio in ≤ 20 s chunks and diffs it (`cut-verification.json`); any missing word = bad
  cut, and too few matched words = inconclusive (listen). Enable with
  `global.remove_pauses` in edit-decisions; the planner remaps all graphics/captions/SFX and alternates a 6 % zoom at cuts.
- **SFX:** if `data/` contains an approved SFX library (role `sfx`), map kinds → files in `06_audio/sfx-map.json`.
  Otherwise `reel sfx` synthesizes **original** procedural cues (ffmpeg; no third-party audio):
  whoosh, whoosh_soft, pop, click, tick, riser_soft, hit_soft, shimmer (48 kHz/24-bit stereo).
- Cue sources: template defaults (graphic entries) + explicit `sound` entries in decisions. Restraint:
  ≤ ~12–18 cues/min, none on sensitive statements, none on every caption.
- Tracks: A03 general SFX, A04 transition whooshes, A05 graphic pops/ticks/clicks, A06 music.
- Gain: clip level from `gain_db` (default −14 dB; ticks −18 dB). Target dialogue ≈ −6 dBFS peaks.
- **Music:** never invented. Without a supplied licensed/approved track, A06 stays empty and music cue points
  become sequence markers ("MUSIC: …"). References suggest a continuous low bed ≈ 12–16 dB under dialogue.
- `06_audio/audio-cue-sheet.json`: cue id, timecode, frame, type, source file, segment, related visual, gain, fades.
