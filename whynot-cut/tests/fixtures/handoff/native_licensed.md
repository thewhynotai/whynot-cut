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
| Premiere sequence | Built natively by the WhyNot Cut Bridge (**PRPROJ_BUILT**, <TS>) → **open the .prproj, nothing to import** |
| Captions | Animated captions are brand stills on the Caption lanes of the sequence (V6 Caption bars (sweep), V7 Captions (animated)), placed by the bridge; an editable caption track (C01) is also on the sequence |
| SFX | Original procedural SFX placed on A-tracks |
| Music | **Not supplied** — markers only |
| Final mix, polish, render | You |

## 1. Open in Premiere Pro (≈1 min)

1. Premiere Pro → **File › Open Project…** → `07_premiere/project/CLIP1_RE_EDIT.prproj`. The sequence **CLIP1_RE_EDIT** is already built with its media, graphics, captions, markers and audio tracks. **Do not import the XML interchange**: it would add a second sequence.
2. Sequence settings (frame size, frame rate, preview codec, colour options) are set through Premiere's API by the bridge; read-back: all 7 checks passed — nothing to set by hand.
3. Track map (as built):

| Track | Clips |
|---|---|
| V1 Main Footage | 3 |
| V2 B-roll (full screen) | 0 |
| V3 Graphic bars (sweep) | 2 |
| V4 Graphic text | 2 |
| V5 Cards (closing glass) | 1 |
| V6 Caption bars (sweep) | 4 |
| V7 Captions (animated) | 4 |
| V8 Transitions | 0 |
| A1 Dialogue (clean) L | 3 |
| A2 Dialogue (clean) R | 3 |
| A3 SFX L | 1 |
| A4 SFX R | 1 |

4. Captions: the Caption lanes **V6 Caption bars (sweep)**, **V7 Captions (animated)** hold the animated caption stills (bar + text) and the sequence also has an editable caption track (C01); keep one of the two visible so captions don't appear twice. Caption wording lives in those stills: to correct it, fix `02_transcription/captions-short.srt` and re-run the pipeline (`reel previews`, then `reel ppro-build --force`), don't retype it in Premiere.
5. The project stays at `07_premiere/project/CLIP1_RE_EDIT.prproj`: **File › Save** after your changes. A rebuild (`reel ppro-build --force`) refuses to overwrite changes you saved unless `--replace-edited` is added, and it would not carry your edits over.

Main footage: source is 25 fps in a 24.00 fps sequence, kept at native speed (no interpretation change), so dialogue sync is exact; base scale 100.0%. Punch-ins are separate V1 clips with Scale/Position in Motion.
Every graphic and decision also appears as a **sequence marker** (ID + transcript evidence).

## 2. Approvals needed (1)
- **GFX_001** (statement_bar, 00:00:00:10): الصداع النصفي مش دايماً من التوتر

## 3. Finishing notes
- Frosted-glass cards: overlays carry a translucent fill; for true backdrop blur add an Adjustment Layer under the card with **Gaussian Blur ≈ 40** masked to the card shape (as in the references).
- Music: add your licensed track on a new audio track under the SFX pair, using the MUSIC markers; duck −18 to −22 dB under dialogue.
- Verify all on-screen wording against the content review `01_analysis/medical-content-review.md`.
- **Export:** `CLIP1_RE_9x16_v01.mp4` · H.264 High Profile, 1080x1920 at 24.00 fps, high bitrate (or ProRes) · AAC 320 kbps, 48 kHz stereo, -14 LUFS integrated, true peak <= -1 dB

## Licensed material

Assets the agency generated or licensed through Magnific for this clip.

| Asset | Need | File | Kind | Source | Licence |
|---|---|---|---|---|---|
| MG-0007 | N03 | 05_assets/magnific/logo_upscaled.png | image | images_upscale / magnific-precision | ai-generated-paid; agency-licensed, not transferable |
| MG-0008 | N05 | 05_assets/magnific/waiting-room.mp4 | video | stock 5530 | stock-premium; attribution: Photo by A. Author / Magnific; agency-licensed, not transferable |
