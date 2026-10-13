---
name: motion-craft
description: "Reference for the motion-designer agent (preloaded). Not for direct use."
user-invocable: false
---

# Motion craft

```bash
reel plan     --root "<CLIENT>" --video-id <ID>     # compile decisions → timeline-spec.json (fix all errors)
reel previews --root "<CLIENT>" --video-id <ID>     # layered PNG stills + QC composites + caption stills
reel sfx      --root "<CLIENT>" --video-id <ID>     # SFX for the cues: the client's mapped files (06_audio/sfx-map.json), original procedural sounds for the rest
```
**Layered stills** (Premiere animates each layer separately):
- `<id>_bar.png`: the brand box, animated with `bar_sweep`
- `<id>_fg.png`: the text, animated with `text_pop`
- checklist `<id>_title.png` plus one `<id>_i<k>.png` per item, animated with `slide`
- full-screen and card stills, including the podcast cards: `stat_card` (value + label on a dense card, brand accent
  bar; captions hidden during it) and `context_card` (a top pill with one editorial line); check them like the other
  cards
- caption stills `03_broll/captions/CAP_###_{fg,bar}.png` plus `captions-manifest.json`
QC composites over real frames go to `08_quality_control/previews/` (`_contact_sheet.jpg`).

**Look at the contact sheet and the composites.** Check every graphic for:
1. Exact text and order. RTL means the first word is on the **right**.
2. Joined Arabic letters: no isolated forms and no boxes. Stills are shaped by macOS CoreText (installed font) or
   HarfBuzz + FreeType (the client's font file, every OS). The arabic_reshaper fallback breaks fonts with few
   presentation forms: if `reel doctor` shows `uharfbuzz`/`freetype` missing, fix setup before judging Arabic.
   When the client's font has no Arabic, the system Arabic fallback draws (and `reel plan` warns). The font is chosen
   **per text block**, not per word: a Latin brand name inside an Arabic line is drawn in the fallback too, at the
   same size, so expect it in that face, not the brand's Latin font.
3. Inside the safe area from `subtitle-style.json` (default: y 250–1500, x 90–990). `qc` checks every overlay still's
   pixels against it. The verification sheet (`reel verify`, `08_quality_control/verify/`) checks each overlay's
   drawn area against fixed platform margins instead (`inside_safe_area`): 60 px at the sides, 150 px at the top, 200 px at the bottom (1080×1920 → x 60–1020, y 150–1720). The margins stay
   the same in pixels on a landscape 16:9 or a 4:5 frame (they are not scaled), so a landscape frame keeps the 9:16
   phone margins. Never over the face or eyes. Photo crops centre on the detected face (macOS Vision, OpenCV on Windows); set
   `crop_center: [x, y]` (0–1) in the decision params to override.
4. Brand colours and fonts only. No white box around the logo.
5. Nothing doubled. A caption hides while a graphic shows the same words. While a card (name card, glass card, CTA) is
   up, captions are lifted above its top edge automatically.
6. Style matches the profile (e.g. glass only on the closing card) and the reference clips. Hook bars: the template's
   `bar_style` is `underline` (half-height marker) or `box` (full box like statements; the `example-clinic` profile uses `box`).

To fix something, change the decision params or the profile's `graphics-templates.json`, re-run `previews`, and look again.
Never edit the PNGs by hand.

Animation presets and their Premiere keyframes: `${CLAUDE_PLUGIN_ROOT}/skills/premiere-craft/references/premiere-assembly.md`.
Typography rules: `${CLAUDE_SKILL_DIR}/references/arabic-typography.md`.

Fan-out: spawn `whynot-cut:graphic-checker` sub-agents in parallel, one per family (bars/statements, checklist, cards/B-roll, captions).
Give each its image paths and the expected texts. They return pass/fail per image.

If the Agent tool is unavailable (some Claude Code versions don't let subagents start subagents), do the batches in this agent one after another, with the same rows and format, and say "checked sequentially" in your report.

## Motion videos (built in After Effects)
Motion videos (`<EP>_<ID>_MO`: animated, from an episode window's audio): the scene vocabulary and truth rules are in
`${CLAUDE_SKILL_DIR}/references/motion-scenes.md`, recipes → beats → scenes and direction rules in
`${CLAUDE_SKILL_DIR}/references/motion-beats.md`, the After Effects bridge, probe, build, read-back, render and frames
in `${CLAUDE_SKILL_DIR}/references/ae-motion.md`. Check a draft script's shape with
`reel validate 01_analysis/motion-script.json --root "<CLIENT>" --video-id <EP>_<ID>_MO` before `reel motion-plan`.
