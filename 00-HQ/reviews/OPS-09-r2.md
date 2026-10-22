reviewer: fresh sub-agent (independent)
sha: fb28e3f (+ heavy.sh psuite)
verdict: FAIL

# OPS-09 review, round 2 (LIGHT tier, strict acceptance)

Scope: `git -C D:/WNC-work/ops-09 diff 3aa6167 fb28e3f` (tools/test.sh +5, tools/test_parallel.py, tests, 14 fixtures),
the card, review r1, the fix-1 report, the project CLAUDE.md, and `diff -u` of heavy.sh / heavy-test.sh against their
`.bak-20261022-ops09` copies. Consumers of the heavy.sh text checked: `00-HQ/tools/agency_live.py` and
`00-HQ/control-center/app/*`.

Runs (the worktree and the live heavy locks were not touched):
- `bash tools/test.sh -p "test_test_parallel.py"` in the worktree: `Ran 32 tests in 43.285s`, `OK`.
- heavy-test.sh, run on COPIES of heavy.sh + heavy-test.sh in `D:\ClaudeData\Temp\ops09-review2\heavy\` (its own
  HEAVY_LOCKS under that folder): `passed 79, failed 0`.
- One experiment in `D:\ClaudeData\Temp\ops09-review2\aba\` (a throw-away git repo, its own WHYNOT_SUITE_CACHE).
  A second experiment, a psuite starvation demo, was blocked by the sandbox's rm check (heavy.sh itself runs
  `rm -rf` on slot folders). P2-1 below rests on reading the code.

## r1 findings: fixed?
| r1 | Status | Evidence |
|---|---|---|
| P1-1 sys.path | **Fixed** | `worker()` :139-141 replaces the script folder with the cwd, unless `safe_path` is set. `SameAsSerial` compares the full `sys.path` list with a real serial run, and runs a tools-only import in both modes. |
| P1-2 key before run | **Partly fixed**, see P1-1 below | :477 takes the key again after the run. An edit that is still there at the end is caught. An edit that is made and reverted during the run is not. |
| P2-1 CRLF | **Fixed** | :277-295 hash the raw bytes of every path that `git status -z` lists, and `--no-ext-diff --no-textconv` is passed. Tested. |
| P2-2 env | **Partly fixed**, see P2-2 below | prefixes `WHYNOT_`, `WNC_`, `NH_`. `WHYNOTCUT_*` is not in the key. |
| P2-3 xpass | Fixed (test added; the mutant is killed, per the fix report) | `Results.test_an_unexpected_success_is_a_failure` |
| P2-4 rc≠0 after record | Fixed (test added) | `case_exit_after_record` + `Incomplete.test_a_record_then_a_non_zero_exit_is_incomplete` |
| P3-1 labels before verdict | Fixed | `format_report` :329-356. The verdict is the last line, and cache notes are printed before the report (:477-491). |
| P3-2 incomplete line | Fixed | `FAILED (incomplete: …)` :346, exit 2 |
| P3-3 worker reconfigure | Fixed | :374-380 reconfigure only in the parent. Covered by the surrogate fixture. |
| P3-4 subtest label | Fixed | `SUBTEST_ID` :35, tested |
| P3-5 tool crash → 2 | Fixed | :381-388. A failed cache write is now a note, :489-490. |
| P3-6 RAM peak | Fixed | sampled every loop, at most once a second, :241-245 |
| P3-7 untracked anywhere | Fixed | whole-repo `git status --untracked-files=all` |
| P3-8 runtime id | Known limit (accepted) | — |

## P1

### P1-1: a tree that is edited and reverted DURING the run is still cached. A green result is reused for a commit whose serial run fails (r1 P1-2 only half closed)
- **Where:** `tools/test_parallel.py:411-418` (the key = git state at the moment of the call) and `:477` (the second
  call only compares the two end points).
- **Scenario (reproduced, `D:\ClaudeData\Temp\ops09-review2\aba\`):**
  1. The commit has `test_a` failing. Serial `python -m unittest discover`: `FAILED (failures=1)`.
  2. `--parallel 2` starts on the clean tree, which gives the start key.
  3. At 1 s, `test_a.py` is edited so that it passes. `test_a` runs during the edit.
  4. At 7 s, `git checkout -- test_a.py` reverts it. The run ends at 9 s.
  5. The end key equals the start key, so the run reports `OK`, rc 0, and stores the entry.
  6. The next `--parallel` prints `reused: a7e4a04cc619-… ` / `OK`, on the exact broken commit.

  This is r1's P1-2 with the revert moved inside the run window. In the shared checkout, "try an edit, then
  `git checkout --` it" within a 25-minute run is at least as likely as the revert-after case. It breaks the card's
  rule: "The cache must never serve a result for different code … when in doubt, miss".
- **Fix (small):** take a change stamp of the tree at the start and at the end, outside the key. Then:
  - For every path in `git ls-files -z --cached --others --exclude-standard`, record `(path, st_mtime_ns, st_size)`
    (or just hash that list).
  - If the start and end stamps differ, print `parallel: tree changed during the run; not cached` and store nothing.

  Any edit or revert, including `git checkout`, the Edit tool, or a formatter, bumps the mtime, so the edit-and-revert
  case is caught. A few thousand `stat` calls cost well under a second. Add a test: a fixture edits a tracked file
  and restores its exact bytes during its own test. Expected: the not-cached message, and no `reused:` on the next
  run.

## P2

### P2-1: heavy.sh keeps only ONE heavy slot free for a waiting psuite, which needs TWO. A stream of jobs can hold it off indefinitely. It should be 2
- **Where:** `heavy.sh:339-343` (`max=$((max - 1))` for any older suite or psuite) together with `:367`
  (psuite needs `HH + 2 <= max`).
- **Scenario:** RAM < 75 % gives ALLOWED = 4. A psuite P is the oldest suite ticket, and three jobs run, so HH = 3.
  1. Every new `job`/`gpu` sees P waiting and uses max = 3, so it may start while HH < 3.
  2. When one job ends, HH = 2. P (it needs HH ≤ 2) and any waiting or just-arrived job (it needs HH < 3) are both
     eligible. Whoever polls first wins, and a job asking at that instant usually wins, because P is in a NAP of
     20 s.
  3. HH goes back to 3, and the cycle repeats.

  For a plain `suite` the 1-slot reserve is enough: jobs can only reach max-1, so a suite always fits. A psuite needs
  2, so the same reserve doesn't protect it. Nothing makes the wait bounded: it is not a deadlock, but it can starve
  for as long as jobs keep coming. Meanwhile every younger suite is queued behind P (shared FIFO), so the suite lane
  stalls too. heavy-test P6 doesn't catch this. It runs at RAM 80 %, where P is blocked by RAM anyway, not by heavy
  slots.
- **Fix:**
  - In `ahead()`, also record the kind of the ticket found (`AHEADK="${TK[$i]}"`).
  - At `:340-341`, reserve 2 when `AHEADK = psuite`: `need=1; [ "$AHEADK" = psuite ] && need=2;
    max=$((max - need)); [ "$max" -lt 0 ] && max=0`.
  - Optionally, reserve 2 only while P's ticket code is `heavy`. While P waits for RAM or for a running suite, 1 is
    enough, and job throughput is kept.
  - Add a heavy-test case at RAM 50 with heavy-1..3 fake-live and P waiting. Free heavy-3, start a job at that
    instant. Expected: the job waits with "kept free for older 'P'", and P starts.
- **Judgement on the builder's known limit:** it should be 2, not 1.

### P2-2: `WHYNOTCUT_*` switches are not in the cache key (r1 P2-2 left one prefix out)
- **Where:** `tools/test_parallel.py:36` `ENV_KEY_PREFIXES = ("WHYNOT_", "WNC_", "NH_")`.
  `"WHYNOTCUT_SHELLCHECK".startswith("WHYNOT_")` is False.
- **Scenario:** `test_installer.py:9716-9718` (and the PSScriptAnalyzer check at `:4065`) skip unless
  `WHYNOTCUT_SHELLCHECK` / `WHYNOTCUT_PSSA_PATH` (or PATH) find the tool.
  1. A plain run is cached as `OK (skipped=K)`.
  2. A run with `WHYNOTCUT_SHELLCHECK=<path>` prints `reused:` / `OK`, rc 0, and shellcheck never ran. This is the
     "not every test ran" case from the central question.
- **Fix:** add `"WHYNOTCUT_"` to `ENV_KEY_PREFIXES`, and add it to `test_test_switch_env_vars_are_in_the_key`.
  Note in the known limits that skips decided by `shutil.which` (PATH) are not in the key, so after installing a tool
  you use `--fresh`. Alternatively, put a hash of PATH in the key.

## P3
- **P3-1, `tools/test_parallel.py:274-277`, git locks in the shared checkout.** `git status` takes `index.lock` for
  its opportunistic index refresh. Every `--parallel` (twice per run, plus each cache check) can make another
  session's `git commit` or `read-tree` in the same checkout fail with "index.lock exists". **Fix:** call
  `git --no-optional-locks …` (or set `GIT_OPTIONAL_LOCKS=0` in `g()`'s env).
- **P3-2, `:485-488`, cache and durations writes are not atomic.** Two runs in parallel (different worktrees share
  `D:/ClaudeData/suite-cache/durations.json`) can lose updates, or one can read a half file. This fails safe today
  (a ValueError means a miss, or `{}`). **Fix:** write to `*.tmp.<pid>`, then `os.replace`, as the worker record
  already does.
- **P3-3, `00-HQ/control-center/app/runlog.py:37-39`, outside the card's fence.** The regex `(suite|job|gpu)` does not
  match `heavy.sh psuite`. Once the suite command is switched to psuite, the control center shows a helper's suite as
  a generic "Shell: …" line instead of "Full test suite '…' (heavy queue)". RUNNING_TESTS / WAITING_QUEUE detection
  is not affected: it goes by label via `agency_live.parse_queue`, and the whitespace split is not affected by the
  kind column going from 5 to 6 characters. **Fix:** `(p?suite|job|gpu)`, mapping `psuite` to "Parallel test
  suite". Do it in the PLAYBOOK switch step.
- **P3-4, ABA within `dirty_key` itself.** Content that is identical at the start and the end but different in
  between is covered only by the P1-1 fix above. No separate action.

## Central question, round 2: can a parallel run report OK or be cached when serial would not be green, or not every test ran?
- **Exit 0 on the run itself:** I found no new path.
  - Discovery is the same, and packages are refused.
  - The import path is the same (tested against a real serial run).
  - The worker flags and stdio are the same.
  - The strict rule: the code and the FAILED line come only from first-run records, and labels are informative.
  - Complete-or-nothing: no record, a malformed record, rc≠0 after a record, or a lane id with 0 tests all give 2.
  - Unexpected successes count. A tool crash gives 2.
  - Remaining structural differences, as known limits: one fresh process per module (the card's pre-mortem hole 1);
    the worker's `__main__`/`sys.argv` are `tools/test_parallel.py`, not `unittest`; stdin is DEVNULL; the TEMP path
    is deeper. I found no test in the tree that reads its own `sys.argv` or `__main__`. These can only add failures
    or show up in the equivalence run; I see no way for them to hide one.
- **Cached:** yes, two ways: P1-1 (edit and revert during the run) and P2-2 (`WHYNOTCUT_*` switches).

## heavy.sh psuite
- **Atomic:** it takes suite-1, suite-2, heavy, heavy, then `admitted`, all or nothing. On any miss, `release` runs,
  and `wait_for` releases before it naps, so no slot is held while waiting. No deadlock.
- **FIFO with suite:** `ahead suite psuite` at :334 gives one shared queue in both directions (heavy-test P4, P5).
- **The gate still wins:** `gate_holder` runs before the queue, and `admitted()` re-checks after the takes (P7).
  A gate's drain counts the psuite's 4 slots.
- **RAM < 75 %:** yes (P3).
- **Nothing else changed:** the other diffs are the help text, the kind column widths (5→6, in status, log and stats),
  `suite` now queuing behind an older psuite (intended), and job/gpu keeping a slot for an older psuite (intended).
  `agency_live.parse_queue` splits on whitespace and is not affected. The control center only parses through it,
  apart from P3-3.
- **Starvation:** see P2-1. The reserve should be 2.

## Verdict
**FAIL.**
- P1-1 is a reproduced green cache entry for a commit whose serial run fails, the same defect class r1 asked to
  close.
- P2-1 (psuite reserve) and P2-2 (`WHYNOTCUT_` prefix) are small.

Each of the three fixes is a few lines plus one test. This is the last allowed fix round (LIGHT: at most 2). After it,
whatever is left goes into the known limits.
