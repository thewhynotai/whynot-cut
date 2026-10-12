# Editing Reference Analysis (Stage 5)

References in `data/` may be **Markdown** (role `editing_reference_doc`) and/or **videos** (`editing_reference_video`).
Only files whose path names them as references count: everything under `data/References/` (the folder decides first:
`data/Raw/` is always source footage, `data/Broll/` B-roll), else a path with the WORD ref / reference (not
"Refractive" or "Preface"; discovery warns when a folder and a file name disagree). Another
loose document in `data/` stays `unclassified` and discovery warns about it: if it is a reels plan or a style note,
the editor moves it to `data/References/`.

Reference edits belong to the **client**: the style is written **once per client** and every video reuses it.

## Where it goes
`output/client_database/reference_style/` (client-researcher writes the first three):

| File | Content |
|---|---|
| `editing-style-analysis.md` | prose; every item marked *measured* or *inferred*, with its source file |
| `editing-style.json` | numbers and observed treatments (cuts/min, shot median, caption box/colour/position, B-roll, end card) |
| `editing-rules.json` | `mandatory` / `preferences` / `optional` / `conflicts` (each a list, empty if none) |
| `reference-set.json` | written by `reel ref-style --record`: the reference files (path, size, modification time) and their fingerprint |

Each video's copy is written by the engine, never by hand: `reel ref-style --apply --video-id <ID>` (also done by
`reel ref-analyze --video-id <ID>` when the client style is current) writes `01_analysis/editing-style.json` and
`01_analysis/editing-rules.json`, merged with the video's own `01_analysis/editing-style-overrides.json` if present:
```json
{"reason": "this reel is a list", "style": {"captions": {"size": 58}}, "rules": {"preferences": ["checklist"]}}
```
`style` is deep-merged into the client style; `rules` items are appended to the client's lists.

## States (`reel ref-style`, also in `reel next`, `reel inbox`, `qc` and the session start)
- **missing** → write the three files, then `reel ref-style --record --by client-researcher`.
- **unrecorded** → the files exist but were never recorded against the references: check them, then `--record`.
- **stale** → a reference was added, removed or edited (even touched) since the record; `reel next` shows
  "reference style stale — refresh client style + reel-profile style.json/notes.md (added/removed/edited: …)".
  Re-read or re-measure the changed references, update the three files and the client's `reel-profile/style.json` +
  `notes.md` where the standing style changed, then `--record`. `--record` warns when the profile or the style files
  were left unchanged. A client folder copied without its modification times also reads as stale: re-record after
  checking.
- **current** → don't re-author; `--apply` to each video. A video whose copy predates a later client change shows as
  outdated: re-apply before re-planning it.

## Markdown references
Read fully. Extract rhythm, camera, typography, B-roll, motion, sound, storytelling. Classify each rule as
mandatory / preference / optional. If several docs conflict, list conflicts; brand rules win over style docs.

## Video references
1. `reel ref-analyze --root "<CLIENT>"` → per video: scene cuts (ffmpeg scene score 0.30), shot stats, 1-fps contact
   sheets, frames at each cut, RMS loudness envelope (100 ms). Cached per client in
   `output/client_database/reference_analysis/` (a reference is measured once, whatever the number of videos).
2. **View every contact sheet** (Read tool on the JPGs) and extract a few full-res key frames for typography detail:
   `ffmpeg -ss <t> -i ref.mp4 -frames:v 1 -vf scale=540:-2 key.png`.
3. Interpret: caption font/colour/position/length, highlight treatment, cards, lists, full-screen B-roll,
   transitions, punch-ins, end cards. Loudness floor in pauses > −45 dBFS suggests a music bed (mark *inferred*).
4. Write the three files in `reference_style/` (measured vs inferred clearly marked), then `reel ref-style --record`.

Never copy third-party footage/music from references into the edit; they define style only.
