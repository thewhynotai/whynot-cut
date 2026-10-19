# ENV-01 — Engine runtime for unsandboxed processes (helper suites)

- **Assigned:** COMMAND CENTER (master)    **Model:** Opus 5.5    **Size:** S    **Status:** IN_PROGRESS
- **Tier:** LIGHT (dev workflow)    **Milestone:** M0    **Unblocks:** every helper card (SETUP-H1/H2 baseline, then all ACCEPTs)

## Goal
The full suite run from a helper worktree (real, unsandboxed Windows environment) has no environment errors.

## Root cause (verified 2026-10-20 01:20)
The 47 engine packages are installed in the user-site of Claude's **sandboxed** AppData view only. A read-only check
from the real terminal: `import numpy` → ModuleNotFoundError; `%APPDATA%\Python\Python313\site-packages\numpy` absent
(`scratchpad\envcheck-real.txt`). Also `tests/_isolation.py` points APPDATA at a temp dir, so test child processes can
never use a per-user site: the packages must live inside the venv's own site-packages.

## Fix (D:\ClaudeData\accounts\env-fix\)
1. `user-site-freeze-20261020.txt` = the exact 47 versions the sandboxed (passing) runs use.
2. Step 1 `install-real-user-site.ps1` (01:28): real user-site install → 104 targeted tests: 97 pass, 7 fail, all in child
   processes (APPDATA redirected). Proved the second cause.
3. Step 2 `install-into-venv.ps1`: remove step 1's copy, install the same versions into the venv; import check with
   APPDATA redirected. **Runs only after H1's two running suites finish** (never break a running helper job).

## Acceptance
1. Real-env import check with APPDATA redirected prints `IMPORTS OK`.
2. `verify-real-env.ps1` (test_align_w2v, test_structure, test_cli_consistency, test_podcast.TestHygiene): 0 failures.
3. A full suite from a helper context has no `ModuleNotFoundError` and no ffmpeg `NoneType` errors (H1's next suite or
   SETUP re-run), compared with the executor's 7,307-OK baseline.
4. The sandboxed sessions' runtime is unchanged in versions (same freeze list).

## Evidence
(filled at close)
