# Editing Reference Analysis (Stage 5)

References in `data/` may be **Markdown** (role `editing_reference_doc`) and/or **videos** (`editing_reference_video`).

## Markdown references
Read fully. Extract rhythm, camera, typography, B-roll, motion, sound, storytelling. Classify each rule as
mandatory / preference / optional. If several docs conflict, list conflicts; brand rules win over style docs.

## Video references
1. `reel ref-analyze` → per video: scene cuts (ffmpeg scene score 0.30), shot stats, 1-fps contact sheets,
   frames at each cut, RMS loudness envelope (100 ms).
2. **View every contact sheet** (Read tool on the JPGs) and extract a few full-res key frames for typography detail:
   `ffmpeg -ss <t> -i ref.mp4 -frames:v 1 -vf scale=540:-2 key.png`.
3. Interpret: caption font/colour/position/length, highlight treatment, cards, lists, full-screen B-roll,
   transitions, punch-ins, end cards. Loudness floor in pauses > −45 dBFS suggests a music bed (mark *inferred*).
4. Write `01_analysis/editing-style-analysis.md` (measured vs inferred clearly marked),
   `editing-style.json` (numbers), `editing-rules.json` (`mandatory` / `preferences` / `optional` / `conflicts`).

Never copy third-party footage/music from references into the edit; they define style only.
