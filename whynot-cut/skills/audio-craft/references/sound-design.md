# Sound Design

- **Dialogue (A1/A2): cleaned** by `reel audio-clean` → `06_audio/dialogue/dialogue_clean.wav`, linked to V1, same clock as the camera file.
  Chain (measured on C0238): best mic per transcript segment (multi-mic shoots) → 2× high-pass 90 Hz → narrow notches at
  100/200/300/400/500 Hz (mains hum was 89 % of residual noise) → afftdn nr 24 / nf −32 → gentle compression → two-pass loudnorm −14 LUFS.
  Evidence (C0238, delivered file): speech-to-noise 16.6 → 22.8 dB at −14.6 LUFS, spectrograms in `08_quality_control/audio/`. Original camera audio stays on A7/A8 **disabled** for A/B.
- **Pause removal:** `audio-clean` detects pauses on the CLEANED audio (noise hid them before), keeps 80 ms breath each side,
  then re-transcribes the tightened audio and diffs it (`cut-verification.json`); any missing word = bad cut. Enable with
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
