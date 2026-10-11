# Example Clinic / عيادة مثال — client notes

**This is a fictional example.** Example Clinic, Dr. Sample Example (د. سامبل إكزامبل) and every value here are made up so
the plugin can show what a filled-in profile looks like. A real client's profile belongs in that client's own folder
(`output/client_database/reel-profile/`, created by `reel client-init`), never in the plugin.

Apply it explicitly to try it: `reel next --root "<folder>" --profile example-clinic`. It is never matched by folder name.

Client folder: any folder with `assets/` (brand files) and `data/` (footage, `data/Ref/` reference edits).
Always re-read the client database (`output/client_database/`). These notes are a reminder, not a source of facts.

## Brand
- Colours (fictional): blue `#2A7FBA`, white `#FFFFFF`. Derived tints (not official): paper `#D6E8F5`, ink `#10304A`.
- Font **Cairo** (Arabic + Latin, open licence), in `assets/Font/*.ttf`. Install it before building.
  Stills are shaped by CoreText (macOS) or HarfBuzz (Windows). Never accept the arabic_reshaper fallback for Arabic
  captions (`reel doctor` must show uharfbuzz).
- Logo: a simple blue "EC" monogram.
- Name-card wording comes from approved reference material, e.g. "Dr. Sample Example, Consultant Dermatologist,
  Example Clinic". Use the client's approved wording exactly; never paraphrase it.

## People (see `profile.json` → `people`)
- Dr. Sample Example (د. سامبل إكزامبل): male, «الدكتور» / "Dr.", he/him (fictional; a real profile cites the source,
  e.g. the approved name card).
- The off-camera interviewer, Nour Placeholder (نور بليسهولدر): gender `unknown` (the brief doesn't say, and "Nour"
  is used for men and women) — ask the editor before writing a gendered word about them.
- Never infer gender from a name. `reel plan` and `reel publish-check` flag a wrong-gender honorific next to a name.

## Editor's standing style (see `style.json`)
- **Pauses removed.** Cuts are hidden by alternating 100/106 % zoom. min pause 250 ms, 80 ms breath pad. Re-transcribe to prove no words were lost.
- **Captions:** keyword captions animated as graphics. White text pops in, and on keyword cues a blue box sweeps in right-to-left.
  Captions are hidden while a graphic carries the same words. The CC sidecar is `02_transcription/subtitles-seq.srt`, not a native caption track.
- **Key statements:** white text on blue boxes (`statement_highlight`). Boxes sweep right-to-left and the text pops in.
- **Glassy design ONLY on the closing name card.** No glass cards mid-video.
- Hook titles use the same full boxes as statements (`bar_style: box`). Checklist items slide in one at a time.
- All animation is Premiere keyframes (Motion › Crop Left for the sweep). No After Effects unless the editor asks.

## Audio facts (example)
- Two mics on ch1/ch2: ch1 = the doctor, ch2 = the off-camera interviewer reading the questions. Check the correlation
  and listen before choosing a channel; the opening question may not be the doctor's voice.
- Mains hum at 50 Hz (or 60 Hz) plus harmonics is common in clinics, so the cleanup chain includes notches.

## Medical
- Dermatology and laser content. Every on-screen medical statement is marked `approval_required: true` until the doctor approves it.
- Keep the doctor's hedges ("يمكن", "ممكن"). Never strengthen a claim.
- Confirm who a photo shows before using it as the doctor's photo.

## Worked example: C0001 (fictional)
- 60 s → 52 s after removing pauses. No speech lost at any cut (re-transcription + sample check).
- Still open: human transcript check, medical approvals, licensed music, final mix/render.
