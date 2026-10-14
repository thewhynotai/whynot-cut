# Mac inbox (mac/dev to Windows)

The Mac side (branch `mac/dev`) adds one entry here for every feature or fix it commits. The Windows executor works
through this list at each task boundary:
1. It fetches `mac/dev` and reads this file.
2. It runs the Windows suite and the live checks.
3. It merges `mac/dev` into `release/3.0`, or sends fixes back on `mac/dev`.
4. It sets the entry's Status.

Every phase gate covers both platforms.

Rules for entries:
- Newest first.
- One `###` block per feature or fix.
- Every change is written cross-platform: macOS and Windows paths, shell, fonts and Adobe folders, with tests for both.
- A fix needed in a path listed in `LOCKED-AREAS.md` is described here (repro and a proposed diff), never committed.

Entry format (the five fields are required; `tools/release.py` parses them):

```
### 2026-10-20: <short title>
- Added: <what changed and why, one or two lines>
- Commits: <sha>, <sha>
- Tests: <test files / names, macOS result>
- Needs Windows verification: <the exact checks the Windows side must run>
- Status: open | needs Windows fix | verified on Windows (<date>, <sha>) | sent back (<why>)
```

## Entries

(none yet)
