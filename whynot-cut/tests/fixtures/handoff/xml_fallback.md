# Handoff — CLIP1

Generated <TS> by the `whynot-cut` plugin (by The Why Not AI). QC: **PASSED** (see `08_quality_control/validation-report.md`).

## What was automated vs. what you do

| Component | Status |
|---|---|
| Transcription (Whisper large-v3, word timing) | Automated — **needs your verification** (`02_transcription/subtitle-review.md`) |
| Topic / narrative / statement analysis | Automated by Claude (`01_analysis/`) |
| Edit plan → frame-accurate timeline spec | Automated (`01_analysis/timeline-spec.json`, readable: `edit-plan.md`) |
| Edit plan approval | approved by editor |
| Visual verification of renders/PSDs | NOT PASSED: no visual verification recorded — run `reel verify`, view the sheet, then --record |
| Premiere sequence | FCP7 XML interchange (automated) → **you import + save as .prproj** |
| Captions | SRT only (`02_transcription/subtitles.srt`): the XML carries no animated captions — build natively (`reel ppro-build`) for those |
| SFX | Original procedural SFX placed on A-tracks |
| Music | **Not supplied** — markers only |
| Final mix, polish, render | You |

## 1. Open in Premiere Pro (≈3 min)

This clip was not built natively yet (no `07_premiere/ppro-build-result.json`). The preferred path is `reel ppro-build` (Premiere open with the WhyNot Cut Bridge); import the XML only if that cannot run.

1. Premiere Pro → open/create your project → **File › Import…** → `07_premiere/interchange/CLIP1_RE_EDIT.xml`.
   Premiere creates a bin with the sequence **CLIP1_RE_EDIT** and all linked media.
2. Open the sequence → **Sequence › Sequence Settings…** and confirm/set the values the XML cannot carry:
   - Editing Mode **Custom**, Display Format **24 fps Timecode**, Audio Display Format **Audio Samples**
   - Preview File Format **QuickTime**, Codec **Apple ProRes 422 LT**, Preview **1080 × 1920**
   - Maximum Bit Depth **off**, Maximum Render Quality **off**, **Composite in Linear Color on**
   - (Verify XML-set values: 1080×1920, 24.00 fps, Square Pixels, No Fields, 48000 Hz stereo.)
3. The XML carries no animated captions. **File › Import…** `02_transcription/subtitles.srt` → drag onto the sequence to get an editable caption track (C01), or ask for the native build (`reel ppro-build`, Premiere open with the WhyNot Cut Bridge) which places the animated captions.
4. Rename tracks (Premiere does not read track names from XML):

| XML track | Role | Clips |
|---|---|---|
| V1 | V1 — Main footage | 3 |
| V2 | C02 — Captions | 0 |
| A1-2 | A1 — Dialogue (L/R mono pair) | 3 |

5. **File › Save As…** `07_premiere/project/CLIP1_RE_EDIT.prproj`.

Main footage: source is 25 fps in a 24.00 fps sequence, kept at native speed (no interpretation change), so dialogue sync is exact; base scale 100.0%. Punch-ins are separate V1 clips with Scale/Position in Motion.
Every graphic and decision also appears as a **sequence marker** (ID + transcript evidence).

## 2. Approvals needed (1)
- **GFX_001** (statement_bar, 00:00:00:10): الصداع النصفي مش دايماً من التوتر

## 3. Finishing notes
- Frosted-glass cards: overlays carry a translucent fill; for true backdrop blur add an Adjustment Layer under the card with **Gaussian Blur ≈ 40** masked to the card shape (as in the references).
- Music: add your licensed track to A06 using the MUSIC markers; duck −18 to −22 dB under dialogue.
- Verify all on-screen wording against the content review `01_analysis/medical-content-review.md`.
- **Export:** `CLIP1_RE_9x16_v01.mp4` · H.264 High Profile, 1080x1920 at 24.00 fps, high bitrate (or ProRes) · AAC 320 kbps, 48 kHz stereo, -14 LUFS integrated, true peak <= -1 dB
