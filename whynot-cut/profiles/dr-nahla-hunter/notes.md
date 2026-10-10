# Dr. Nahla Hunter — client notes

Client folder: `nahla hunter` (first produced on macOS at `/Volumes/DOMA 2.5 SS/video editing/nahla hunter`; any location works on macOS or Windows). `assets/` brand files, `data/` footage + `data/Ref/` reference edits.
Always re-read the client database (`output/client_database/`). These notes are a reminder, not a source of facts.

## Brand
- Official colours (`assets/Color Palate/Colors.rtf`): teal `#20ACAF`, white `#FFFFFF`. Derived tints (not official): paper `#B1E2E3`, ink `#0D4546`.
- Font **Thmanyah Serif Display** (Light→Black, Arabic + Latin), in `assets/Font/*.otf`. Install it before building.
  Stills are shaped by CoreText (macOS; verified with this font in production) or HarfBuzz (Windows; full OpenType
  shaping like CoreText, not yet checked with this font: look at the first stills). Never accept the
  arabic_reshaper fallback for this font: it has only 89 presentation forms and breaks (`reel doctor` must show uharfbuzz).
- Logo: teal NH monogram.
- Name-card wording comes from approved reference material: name, Kasr Al-Ainy Faculty of Medicine, Professor of Dermatology,
  Cosmetic Dermatology & Laser. Use it exactly; never paraphrase it.

## Editor's standing style (2026-10-10, see `style.json`)
- **Pauses removed.** Cuts are hidden by alternating 100/106 % zoom. min pause 250 ms, 80 ms breath pad. Re-transcribe to prove no words were lost.
- **Captions:** keyword captions animated as graphics. White serif text pops in, and on keyword cues a teal box sweeps in right-to-left (Ref 1/3).
  Captions are hidden while a graphic carries the same words. The CC sidecar is `02_transcription/subtitles-seq.srt`, not a native caption track.
- **Key statements:** white text on teal boxes (`statement_highlight`, Ref 3). Boxes sweep right-to-left and the text pops in.
- **Glassy design ONLY on the closing name card.** No glass cards mid-video.
- Hook titles use the same full teal boxes as statements (`bar_style: box`). Checklist items slide in one at a time. One mint full-screen photo card with a white flash.
- All animation is Premiere keyframes (Motion › Crop Left for the sweep). No After Effects unless the editor asks.

## Audio facts learned on C0238
- Two different mics on ch1/ch2 (correlation 0.13): **ch2 = the off-camera interviewer reading the question**, ch1 = Dr. Nahla's answer.
  The opening question is NOT spoken by Dr. Nahla. Her lips are closed and she is looking away while it is asked.
- 100 Hz mains hum plus harmonics was 89 % of the residual noise, so the cleanup chain includes notches at 100–500 Hz.
  Delivered file (chain of 1.0.3+): speech-to-noise 16.6 → 22.8 dB at −14.6 LUFS. (23.7 dB is the denoise-only stage, not the delivered file.)

## Medical
- Dermatology content. Every on-screen medical statement is marked `approval_required: true` until the doctor approves it.
- Keep her hedges ("يمكن", "ممكن"). Never strengthen a claim.
- On C0238 these graphics were flagged for approval: GFX_003, 004, 006, 008, 009, 010.
- `assets/Photos/2.png` (curly hair, glasses) looks different from the on-camera speaker in C0238 — confirm who it shows before using it as her photo.

## Worked example: C0238
- 62.9 s → 54.6 s after removing 21 pauses (8.3 s, audio chain 1.0.3+). No speech lost at any cut (re-transcription + sample check);
  listen at ~17.9 s, 54.7 s, 60.1 s (source) where wording changed next to a cut.
- The Premiere project `07_premiere/project/C0238_NH_EDIT.prproj` has 47 animated layers on 11 named video tracks, and all 10 settings read-back checks pass.
- Still open: human transcript check, 6 medical approvals, licensed music, final mix/render.
