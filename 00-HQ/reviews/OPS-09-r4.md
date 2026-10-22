# OPS-09 review r4 — commit 79989c9 (serial lane `module/selector`) — 2026-10-22 ~19:40

Reviewer: fresh `oh-my-claudecode:code-reviewer` subagent (no history, read-only, no Write tool). Saved by the master
from the returned text (shortened; every finding kept). Reviewer ran `bash tools/test.sh -p test_test_parallel.py`:
39 tests OK (57.8 s).

**Verdict: PASS-WITH-MINORS** — 0 P1, 0 P2, 3 P3.

## Checked
- Matches the card: the serial lane is the designed answer for a load-sensitive extra failure; lane jobs still count;
  strict rule untouched (lane failures → problems → relabel → exit 1).
- Cannot hide, double-run or miscount with the default lane: module job excludes `sel` and the lane job runs
  `--only sel` in the same module through the same `_matches` (`test_parallel.py:487-489`); real repo 1 + 151 = 152.
- Wrong entries fail closed (exit 2): unknown module, wrong selector ("matched no test"), `mod/`, `/sel`, `a/b/c`,
  spaces around `/`, the old plain spelling of an aliased id.
- Relabel uses `j.module` + `_selector` (correct for aliased ids). Cache key holds the raw lane string + tool hash.
  `/` never reaches a worker argv (no MSYS path conversion). Nothing OS-specific.
- The test itself (`tools/wnc_queue/tests/test_wnc_queue.py:336-354`) failed on its own precondition "timed out before
  it spawned its grandchild (machine too slow?)": environment timing under 88 % RAM, not a runner defect.
  `RunnerTests`/`Base` have no class/module fixtures, so splitting one method out duplicates nothing.

## P3 (known limits)
1. Overlapping lane entries (`test_x.A.t` + `test_x/test_x.A.t`, or `test_x.A` + `test_x.A.t`) run a test twice
   (Ran +1, a failure counted twice). Pre-existing; the new form adds a second spelling. Default lane has no overlap.
   Fix later: refuse overlap with exit 2.
2. A method-level lane entry splits its class across two processes: a future `setUpClass`/`setUpModule` error would
   be reported twice (errors +1; same failing-id set; fails closed). Not live today.
3. Tests/docs: no failing-aliased-lane-test case; `test_a_module_qualified_lane_id_must_still_match` asserts only
   exit 2, not which guard fired; `--serial-lane` help and the module docstring don't mention `module/selector`.

## Master disposition
No fix round 5: all P3, none can make a parallel run greener than serial with the shipped default lane. Recorded under
"Known limits" in `tasks/OPS-09.md`. Acceptance now depends only on parallel run 3 on 79989c9 (expected Ran 9546,
failing set = the 4 baseline ids).
