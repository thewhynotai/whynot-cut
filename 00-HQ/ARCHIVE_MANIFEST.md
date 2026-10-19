# ARCHIVE_MANIFEST — what was archived, where it went, and what replaced it

Machine record (one JSON line per file, with sha256): `00-HQ/archive-manifest.jsonl`. Tool:
`00-HQ/tools/archive_docs.py` (dry run by default; `--apply`; `--undo` restores a batch after a sha256 check; plain
files only, refuses links/reparse points, all-or-nothing preflight; self-tested on a mirror tree 2026-10-20).
Archive is not deletion: everything below is in `Editing Plugin\_archive\plans-2026-10\` with its original sub-path,
and also in the baseline copy `D:\ClaudeData\backups\2026-10-20-baseline\` (SHA256SUMS.txt).

## Batch 2026-10-20-b1 (8 files)

| Original path | Class | Replaced by | Reason |
|---|---|---|---|
| `V1-SCOPE-AR.md` | REFERENCE_ONLY | V1 spec `WhyNotCut/docs/superpowers/specs/2026-10-18-v1-premiere-panel-design.md` | Superseded (DOC-MAP); the spec cites it as a source |
| `NEW-PLAN-BRIEF-AR.md` | REFERENCE_ONLY | the V1 spec | Owner answers folded into the spec; §4 = SAVED-LATER §4 |
| `WhyNot-Cut-3.1-Plan/WHYNOT-CUT-3.1-PLAN.md` (+ empty folder) | ARCHIVE_READY | master roadmap | "3.1" no longer used (DOC-MAP #8) |
| `PROJECT-PLAN-AR.md` | ARCHIVE_READY | `PROJECT_PLAN_AR.md` | Owner plan body of 10-17 |
| `API-LANES-PLAN.md` | ARCHIVE_READY | `00-HQ/BUDGET-API.md` + `roles/API-LANES.md` | 5-lane plan of 10-17 |
| `WhyNot-Cut-3.0-Addendum/ADDENDUM-K-adopted-ideas.md.bak-kt8` | DUPLICATE_VERIFIED | the live ADDENDUM-K | pre-kt8 backup |
| `WhyNot-Cut-3.0-Addendum/ADDENDUM-M-owner-requests-2026-10-16.md.bak-kt8` | DUPLICATE_VERIFIED | the live ADDENDUM-M | pre-kt8 backup |
| `00-HQ/MASTER-PLAN-AR.md` | ARCHIVE_READY | `PROJECT_PLAN_AR.md` (+ `PLAYBOOK.md`, `BUDGET-API.md`) | Owner plan v2 of 10-19 (the design Yunus approved); live view moved |

**References still pointing at old paths (history mentions, not live links):** the repo's master roadmap (line 29, 73)
and V1 spec (lines 8, 10) name `PROJECT-PLAN-AR.md`, `V1-SCOPE-AR.md`, `NEW-PLAN-BRIEF-AR.md`. They live in the
executor's tree (release/3.0, dirty), so they are fixed after the Gate 4 tag by card OPS-04, not now. 00-HQ references
(README, DOC-MAP, roles/API-LANES) were updated on 2026-10-20.

## Hold list (not moved, on purpose)

| Path | Why held |
|---|---|
| `API-PAUSE-AR.md` | Read by the lane-watch routine prompt (step 0c); historical once lane-watch is retired (OPS-03) |
| `PARKED-SESSIONS.md` | Referenced by `D:\ClaudeData\claude-api-lane\TRACKS.md` (old-system charters still running) |
| `Start-Claude-API-lane.cmd` | The way Yunus re-logs the API lane at API-500 activation |
| `كارت-جرّب-3.0.md` | Owner try card for the live preview (in use) |
| `T4.14-راجع-التفريغ/` | Open owner task (Q-001) |
| `new plugin code/` (Kalam/Hush/Tidy source + macOS `._` files) | Source reference for Addendum A / Stage 4; not referenced by name; decide at Stage 2 |
| `خد دا كوبي للويندوز/` · `خد دا كوبي للماك/` | Live preview folders (rebuilt by the release-preview refresher) |
| `WhyNot-Cut-3.0-Addendum/*` | Live feature detail the V1 spec links to |
| `COMPETITORS-AR.md`, `SAVED-LATER-licensing-updates-AR.md` | Current per DOC-MAP |
| `_archive/` (older zips, 3.0 plan, `_source`) · `_private-*` · `whynot-test/` | Already archive / private evidence / test fixtures |
| `D:\ClaudeData\claude-api-lane\*` (TRACKS, ledgers, notes) | Live old-system records until the Gate 4 tag |
