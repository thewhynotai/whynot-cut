# OPS-09 review r5 — commit 725b852 (drop `git diff HEAD` from the cache key) — 2026-10-22 ~22:40

Reviewer: fresh `oh-my-claudecode:code-reviewer` subagent (no history, read-only). Saved by the master from the
returned text (shortened; every finding kept). Reviewer ran `bash tools/test.sh -p test_test_parallel.py`: 39 OK, and
probed git 2.56.0.windows.2 in scratch repos (nothing written to the project).

**Verdict: PASS-WITH-MINORS** — 0 P1, 0 P2, 3 P3.

## Checked (no new false cache hit)
- Staged vs unstaged give different XY codes; staged-then-reverted shows "MM" with HEAD bytes in the worktree = same
  test outcome (the old worktree-vs-HEAD diff never saw index content either).
- Deletions, renames/copies (`-z` "R new\0old" order parsed), untracked (`--untracked-files=all`) covered; ignored
  files never were (pre-existing).
- CRLF-only edits: still listed by status, raw bytes hashed.
- rev-parse, status, ls-files under --no-optional-locks left .git/index unchanged with a forced stale entry; `diff HEAD`
  rewrote it (root cause confirmed independently).

## P3
1. `tools/test_parallel.py:315-316` docstring overstated: the diff also told apart a submodule commit, a mode-only bit
   (macOS core.filemode=true) and a retargeted directory symlink. None exists in this repo; Windows filemode=false.
2. `test_test_parallel.py:439-442` compared only (mtime_ns, size): a coarse-mtime filesystem could give a false green;
   compare the index bytes instead.
3. No orphans; `time` still used; the one-git-entry assertion holds.

## Master disposition (302df0d)
P3-1: docstring reworded, the three cases written as a known limit. P3-2: the test compares `index.read_bytes()`
(red 3/3 on the 79989c9 tool, green 3/3 on 302df0d; file 39/39). Equivalence run 4 runs on 302df0d.
