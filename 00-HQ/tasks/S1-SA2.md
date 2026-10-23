# S1-SA2 — skip_audit: a machine skip inside the test body is classed platform/tool, not unknown

- **Assigned:** H2 (marketing@)    **Model:** Sonnet 5.5 (effort medium, LIGHT tier per PLAYBOOK §4)    **Size:** S/M (≤1 day)    **Status:** READY (2026-10-23 22:50, intake top-up)
- **Tier:** LIGHT (a dev-only gate tool, not shipped in the plugin. It changes no transcript word, caption, on-screen
  number, cut or religious content, and deletes or moves nothing.)
- **Stage / gate:** Gate 4 exit tooling (the BL-27 card's "Optional follow-up", built instead of only proposed)
  **Depends on:** `release/3.0` @ `5c2d7b3c` only (BL-20's `tools/skip_audit.py`, merged `032ff99`). No dependency
  on BL-27: the executor's register is pinned to `abdece5` / `5c2d7b3c` and never re-runs this tool on your branch.
  No dependency on BL-04, BL-22 or any H1 card.
- **Fallback:** if not started by **2026-10-30 12:00**, the master moves it to the executor.
- **Why H2:** H2 built `skip_audit.py` (BL-20) and holds only BL-22 READY (BL-04 in FIX, BL-27 moved to the
  executor). It needs 3 independent READY cards (PLAYBOOK §3c). The work is code + tests run with
  `bash tools/test.sh -p test_skip_audit.py`, which the AUTO profile allows.

## Goal (the editor's view)
Before every tag, the executor reads the list of skipped tests so no feature reaches an editor "green" only because
its test never ran. On `abdece5` the tool classed **202 skips as "unknown"**, most of them plain machine facts it could
not see ("cannot make a directory link here" ×30, "no bash" ×13, "no test font for HarfBuzz fitting" ×11). A list of
202 makes the few real ones (a skip that waits for a patch that has already landed) easy to miss, and the BL-27 hand
register costs a day per gate. After this card those machine skips class as `platform/tool`, the unknown list is
short, and a "waits for a patch" skip is still never hidden as platform/tool.

## Why
The BL-27 card explains the gap: the `skipTest` sits inside an `if` (or `except`) in the test body, and the
condition is a helper call or a local name the tool does not follow. Real example
(`whynot-cut/tests/test_installer.py` ~line 4414 on `5c2d7b3c`):
`if not make_dir_link(self.paths.downloads_dir, elsewhere): self.skipTest("cannot make a directory link here")`.
`audit_source` already reads the enclosing `if`/`except`, but `_collect_assigns` only follows module-level names, so
a name set in the test function (`bash = shutil.which("bash")`) or a same-file helper such as `make_dir_link` is never
looked into. Another shape: `except OSError as e: self.skipTest(f"cannot make a directory link here: {e}")` around an
`os.symlink` call (`test_eval_transcripts.py` ~line 209).

## Fence (the ONLY paths this task may change)
- `tools/skip_audit.py`
- `whynot-cut/tests/test_skip_audit.py` (your own BL-20 file: add tests, keep every existing one green and unchanged)
- new `whynot-cut/tests/fixtures/skip_audit/case_inbody_*.py` (the fixtures folder is excluded from the tool's own
  scan already)

**Not in the fence:** every other test file (read them, never edit them: no skip is removed or reworded here),
`tools/test.sh`, `tools/test_parallel.py`, `tools/ci/**`, PLAYBOOK, the BL-27 register files.

## Acceptance (each line is checkable)
- [ ] failing tests first: the new cases in `test_skip_audit.py` are red on `5c2d7b3c` (paste the run of
      `bash tools/test.sh -p test_skip_audit.py`).
- [ ] new `platform/tool` cases, each from a real shape (name its file:line on `5c2d7b3c` in the report, found with
      Grep):
  - an in-body `if not <same-file helper>(...)` whose helper body (one level deep) makes a link, checks the platform
    or looks for a tool;
  - a name set earlier in the same test function from `shutil.which(...)` / a platform check, then `if not <name>:`;
  - `except OSError` (or a subclass) around a call that makes a symlink or junction;
  - a `self.<method>()` helper defined in the same class (one level deep);
  - the "no test font" shape, whichever form it has in the real file.
- [ ] guard cases (these must stay as they are today):
  - temporary wording ("yet", "not built", "executor", "patch" …) in the reason, a comment on the skip, or now also
    in the followed helper's body or comments → `unknown`, never `platform/tool`;
  - every dated marker still → `dated` (all existing `TestClasses` tests green);
  - a helper that only reads a repo file ("is it there") and whose reason or body says the file "is not built yet"
    → `unknown`;
  - an empty reason with a condition you cannot follow → `unknown`;
  - a helper imported from another module is NOT followed (known limit, written in the docstring), and the
    recursion stops at one level (no loop on a helper that calls itself).
- [ ] the docstring's class rules are updated in the same words the code uses; `--since` gate mode is unchanged
      (existing `TestSince` green); the tool stays stdlib-only and read-only.
- [ ] full suite green on Windows through the queue (PLAYBOOK §2 step 3, label `h2-S1-SA2`, the §3d check first).
- [ ] no files outside the fence; nothing uncommitted.

## Pre-mortem (written by the master, upgraded by the builder)
- **Will it work end to end?** Yes, for its purpose: the next gate's executor runs `python tools/skip_audit.py --all
  --json` and gets a short unknown list. The risk is the opposite error: a real "waits for a patch" skip hidden as
  platform/tool. That is why the temporary-wording rule now also reads the followed helper, and why the master runs
  the before/after diff below.
- **Cheap smart additions (taken into acceptance):** cases from real file:line shapes, not invented ones; the
  one-level limit; the guard cases.
- **Prerequisites / must be ready first:** none beyond `5c2d7b3c`. Read `tools/skip_audit.py` (`audit_source`,
  `_collect_assigns`, `PLATFORM_RE`, `TEMPORARY_RE`, and the BL-20 round 1 commit `71a1a652`, which narrowed prose
  words on purpose: do not widen `REASON_PLATFORM_RE` to prose like "no bash" or "windows"; follow the CODE of the
  condition instead).
- **Holes and risks:**
  - Your AUTO profile refuses ad-hoc Python scripts (`inbox\h2\2026-10-23-2231-BL-27.md`): never run
    `python tools/skip_audit.py` yourself. All your evidence comes from `bash tools/test.sh -p test_skip_audit.py`.
    The real-tree before/after counts are the master's live check below; you do not need them to deliver.
  - `.exists()` / `.is_file()` already count as "a file in a checkout" (BL-20). A followed helper that only checks a
    repo file must not turn a pending-patch skip into platform/tool: the guard case above pins it.
  - Do not reclassify by reason text alone: the same text can sit on different conditions.
  - `test_installer.py` holds ~51 of the rows; its `make_dir_link` helper is the biggest single win. Read it once.

## Before you start
- Write the claim `D:\ClaudeData\claude-api-lane\claims\S1-SA2.claim` with the text
  `H2 (marketing@) via 00-HQ BOARD, <time>`. If a claim already names someone else, stop and report it.
- Branch `h2/S1-SA2` from `release/3.0`.

## Delivery
- Run the test, then the full suite through the queue.
- Commit with explicit paths on `h2/S1-SA2`. Do not push (PLAYBOOK §1: `release/3.0` has unpushed commits; write
  "not pushed: waiting for release/3.0 push").
- Write `00-HQ\inbox\h2\<date>-S1-SA2.md`, Status DONE, with the new rule in one paragraph and the list of real
  file:line shapes it covers.
- Review: peer review by H1 (PLAYBOOK §3c, one fresh review, LIGHT).

## Live checks needed (master runs them)
- `python tools/skip_audit.py --all --json` on `5c2d7b3c` and on `h2/S1-SA2`: `dated` stays 0, `unknown` drops; read
  every site that moved from `unknown` to `platform/tool` (expect the link / bash / font families) and check that
  none of them is a PENDING or STALE row of the executor's BL-27 register, when that register exists.

## FIX rounds (appended by the master)
