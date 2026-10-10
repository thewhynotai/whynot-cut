# Automation Matrix (audited on macOS 27, Apple M4 Pro, Adobe 2026 apps; Windows equivalents noted)

Levels: 1 fully automated · 2 automated via configured integration · 3 script-assisted, needs local execution ·
4 human interaction · 5 unsupported.

| Component | Level | How |
|---|---|---|
| Input discovery, classification, doc reading (MD/RTF/DOCX/PDF) | 1 | Python + textutil |
| Image indexing (EXIF orientation, alpha, RAW derivatives) | 1 | Pillow + sips (macOS) / rawpy (Windows, optional) |
| Font inspection | 1 | fontTools |
| Media preflight | 1 | PyAV + ffmpeg (imageio-ffmpeg) |
| Whisper transcription + word timing + SRT | 1 | faster-whisper large-v3 (CPU int8) |
| Transcript verification | 4 | editor checks subtitle-review.md |
| Reference measurements | 1 | ffmpeg scene/astats |
| Reference interpretation, semantic analysis, edit decisions | 2 | Claude (whynot-cut plugin) writes files |
| Plan compile / frame math / manifests | 1 | plan.py |
| PNG previews + QC composites | 1 | Pillow |
| SFX | 1 | procedural synthesis (original) |
| AE comps + .aep | 2 | osascript DoScriptFile → AE (macOS); AfterFX.exe -r (Windows) |
| AE renders | 2 | aerender |
| PSDs | 2 | osascript do javascript → Photoshop (macOS); COM DoJavaScriptFile (Windows) |
| Native .prproj (footage, punch-ins, clean dialogue, SFX, animated graphics, captions) | 2 | WhyNot Cut Bridge (CEP panel) runs `nh_ppro_lib.jsx` inside Premiere |
| Premiere sequence preview settings | 2 | `setSettings` + read-back via the bridge |
| Caption track | 2 | animated caption stills (default) or native track (`native_caption_track`) |
| Standalone FCP7 XML (fallback) | 3 | manual File › Import |
| Music | 4 | requires licensed/approved file from client |
| Generated illustrative B-roll (Type E) | 5 | no approved provider configured |
| Final mix, polish, render | 4 | editor |

## Application-level verification (2026-10-10, first job C0238)
- After Effects 2026: `ae-build` created `C0238_NH_GFX.aep` in-app; `aerender` rendered 12 comps (11 events + CAPTIONS) in ~64 s → ProRes 4444 `yuva444p12le`, 1080×1920, 24 fps. Arabic shaping/RTL correct in renders.
- Photoshop 2026 (27.11): `ps-build` created 2 layered PSDs (editable text, RTL fixed via ActionManager) + PNG previews.
- Premiere Pro 26.5.2: native `.prproj` built through the bridge; 10/10 settings read-back checks; frames exported by Premiere and viewed.
- AE DoScript returns only "0" (not the script result), so success is judged by the files produced, never by stdout.
