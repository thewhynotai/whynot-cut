# ENV-01 — Engine runtime for unsandboxed processes (helper suites)

- **Assigned:** COMMAND CENTER (master)    **Model:** Opus 5.5    **Size:** S    **Status:** IN_TESTING (waits for H1's h1-setup4 suite)
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

## Evidence (2026-10-20 02:49)
- Step 2 done without disturbing H1's running suite: `pip install --target <venv>\Lib\site-packages --no-deps -r freeze` (exit 0); import check with APPDATA redirected → `IMPORTS OK`, numpy and ffmpeg from the venv (`install-into-venv.log`). Acceptance 1 OK.
- `verify-real-env.ps1` from the real Terminal: **Ran 104 tests — OK** (was 7 failures after step 1). Acceptance 2 OK.
- Acceptance 3 (full suite from a helper context with no env errors) → H1's `h1-setup4` re-run; Answer written in SETUP-H1 02:49. OPEN until that report.
- Acceptance 4: same 47 versions (frozen from the sandbox view).
- Cleanup left: the step-1 per-user copy (~556 MB on C) is now a duplicate; remove it when no suite runs (`pip uninstall` with the venv copy taking precedence).
