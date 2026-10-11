# EP12_R01_MO — motion video handoff

Generated <TS> · QC: PASSED · 9:16 · 30.0 s · 24.000 fps

## Open it

- After Effects project: `<ROOT>/output/projects/EP12_R01_MO/04_after_effects/project/EP12_R01_MO_RE_MOTION.aep`
- Main comp: `MAIN_EP12_R01_MO` (scenes, persistent layers, audio)
- Master render: `<ROOT>/output/projects/EP12_R01_MO/04_after_effects/render/EP12_R01_MO_MAIN.mov`
- Posting MP4: `(render first)` · Cover: `—`

## How it is organised

- `NH_BRAND/BRAND_CONTROLS`: brand colours; layers whose colour equals a brand colour follow these controls.
- `NH_SCENES/<scene>_<type>`: one comp per scene, placed in MAIN at its frames with its transition.
- Word-by-word text: each word is its own layer (`<name>_wN`) chained right-to-left by expressions; the guide layer `<name>` (not rendered) holds the whole line. To change a word, edit its word layer.
- `NH_PERSISTENT`: background, captions, speaker badge, progress, voice pulse.
- Audio layers in MAIN: DIALOGUE (pauses removed, on the sequence clock), MUSIC, SFX_*.

## Fonts After Effects needs

- Arial-BoldMT
- ArialMT

## Scenes

- S01 hook — frames 0-240
- S02 stat — frames 240-720

## Licenses and attributions

- people/doctor: CC-BY-4.0 — publish with: **People by X (CC BY 4.0)**

## Needs you

- [ ] doctor to approve the statistic on S02
- [ ] music: add a licensed track (the motion video has dialogue and SFX only)
- [ ] final look in After Effects, then render/export for posting
- [ ] post with the reel's captions from publish/reels (attributions included)
