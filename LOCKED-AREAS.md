# Locked areas (two-machine rule)

The Windows side is changing these paths in the current phase. The Mac side (branch `mac/dev`) **never edits,
moves, renames, deletes or reformats** anything that matches a pattern below, not even a one-line fix.

If a Mac bug lives in a locked path:
1. Don't touch the file.
2. Write a `MAC-INBOX.md` entry with the repro, the evidence and the proposed fix (as a diff in a fenced block).
3. Set the entry's Status to `needs Windows fix`.

The Windows side applies the fix and marks the entry done.

The Windows executor updates this list at every phase boundary. `tools/release.py handoff` copies it into the Mac
`START-HERE.md`. Patterns are git pathspec globs, relative to the repo root (`**` = any depth).

## Locked now

- `whynot-cut/evals/**`: T3.7 fix round
- `whynot-cut/hooks/**`: T3.7 fix round
- `whynot-cut/output-styles/**`: T3.7 fix round
- `whynot-cut/skills/status/**`: T3.7 fix round
- `adobe/**`: Adobe track
- `whynot-cut/engine/reel/serve/**`: Adobe track
- `whynot-cut/installer/**`: installer track
- `guide-ar/**`: guide track
