reviewer: fresh sub-agent (independent)
sha: 20c430c
verdict: FAIL

# OPS-09 review, round 1 (LIGHT tier, strict acceptance)

Scope: `git show 20c430c` (tools/test.sh +5, tools/test_parallel.py, tests + fixtures), the card OPS-09.md, the build
report, the project CLAUDE.md. Ran `bash tools/test.sh -p "test_test_parallel.py"` in the worktree: `Ran 21 tests`,
`OK`. Experiments and mutants were run only in scratch copies under `D:\ClaudeData\Temp\ops09-review\` (exp1, exp2,
mut, crlf1). The worktree was not modified.

Main question: can a parallel run say OK (exit 0), or be cached as OK, when the same serial run would not be green?
**Yes, in two ways I reproduced (P1-1, P1-2).** Each one breaks the card's rule that a parallel run must mean exactly
what a serial run means. Both fixes are small.

## P1

### P1-1: the worker's `sys.path[0]` is `tools/`; the serial run's is the repo root. Parallel goes green where serial fails
- **Where:** `tools/test_parallel.py:175-177` starts each worker as a script (`python ... tools/test_parallel.py
  --worker ...`), so Python puts the script folder `tools/` on `sys.path`. The serial run is
  `python -m unittest discover` from the repo root, where `sys.path[0]` is the repo root and `tools/` is not on the
  path.
- **Failure scenario (reproduced, `exp1`):** a test module does `import helper_mod`, where `helper_mod.py` lives in
  `tools/`, and the test does not add `tools/` to `sys.path` itself. The serial run gives `Ran 2 tests` /
  `FAILED (errors=1)` (ModuleNotFoundError). The parallel run gives `Ran 2 tests` / `OK`, exit 0, and **writes a cache
  entry**. In the real repo, eight test modules import `tools/` modules (identity_scan, jsx_lint, token_report,
  eval_transcripts, sign_zxp). Today each of them inserts `tools/` itself. The next test that forgets to would pass the
  gate everyone trusts and fail serially (and on Mac CI). The path order also changes:
  `test_sign_zxp.py:26` and `test_installer.py:9432` insert `tools/` only `if ... not in sys.path`, so in the parallel
  run `tools/` stays behind the engine path instead of going first.
- **Fix:** make the worker's import path match serial. At the top of `worker()`, before `discover`, remove the script
  folder from the path and put the cwd (repo root) in its place: `sys.path[0] = os.getcwd()`, or
  `sys.path[:] = [p for p in sys.path if Path(p).resolve() != Path(__file__).resolve().parent]` followed by
  `sys.path.insert(0, a.repo)`. Better still, start the worker with `-c`/`-m`-style semantics:
  `[python, -s?, -B, -W error::ResourceWarning, -c, "import runpy,sys; sys.argv=[...]; ..."]`. That gives `sys.path[0]`
  = cwd, exactly like `-m unittest`. Add a fixture `case_tools_import.py` (it imports a module that exists only in
  `tools/`) and a test that the parallel result equals the serial result: an ERROR in both.

### P1-2: the cache key is taken BEFORE the run, so a run of edited code is stored under the key of the code before the edit
- **Where:** `tools/test_parallel.py:367-372` (key computed at start), `:430-438` (stored at the end under that key, with
  no re-check).
- **Failure scenario (reproduced, `exp2`):** commit `68b1c59` has a failing test (serial: `FAILED (failures=1)`).
  1. A parallel run starts on the clean tree.
  2. 1.5 s in, the failing test file is edited to pass (the shared checkout has executor WIP; helpers, editors and
     formatters write while a suite of about 25 minutes runs).
  3. The run reports `OK` and stores it under the clean-`68b1c59` key.
  4. The edit is reverted (`git checkout`), so the tree is back to exactly the broken commit.
  5. `--parallel` now prints `reused: 68b1c5947d68-... ` / `OK`, rc 0.

  The serial run of that same tree: `FAILED (failures=1)`. The cache served a green result for code that was never run
  green. This breaks the card's pre-mortem (4): "The cache must never serve a result for different code ... when in
  doubt, miss".
- **Fix:** compute `dirty_key()` again after the run, before writing anything. If it differs from the start key, store
  nothing: no cache entry. Durations are optional; they could still be kept. Print
  `parallel: tree changed during the run; not cached`. Add a test: a fixture that edits a tracked file during its own
  test, then a second run must not print `reused:`.

## P2

### P2-1: the cache key misses line-ending-only changes (`core.autocrlf=true` + `* text=auto eol=lf`)
- **Where:** `tools/test_parallel.py:262` hashes `git diff HEAD --binary`.
- **Failure scenario (reproduced, `crlf1`, with this repo's own settings: `core.autocrlf=true`, `.gitattributes` `* text=auto
  eol=lf`):** an LF file rewritten as CRLF. That is exactly the "Python write_text turns LF files CRLF" accident this
  project has already had. `git status` shows ` M f.py`, but `git diff HEAD --binary` is **0 bytes**. The key does not
  change, so a cached OK is reused, while tests that read bytes (`test_runtime.py`, `test_guard_p2.py`,
  `test_motion.py`, `test_t49_ref_style_adopt.py` all check CRLF/LF) or a CRLF `whynot-cut/bin/reel` would fail
  serially. The same blind spot exists for `diff.external`/textconv settings, because `--no-ext-diff --no-textconv` is
  not passed.
- **Fix:** hash the raw working-tree bytes of every path that `git status --porcelain=v1 -z --untracked-files=all`
  lists (modified, staged, deleted as a marker, untracked non-ignored). Do not rely on the diff text alone; at minimum
  add `--no-ext-diff --no-textconv` and hash the bytes of every path in `git diff HEAD --name-only -z`. Add a test that
  makes a CRLF-only change and expects a cache miss.

### P2-2: the cache key ignores the environment that switches tests on or off
- **Where:** `tools/test_parallel.py:366-372` (key = sha, dirty hash, runtime, tool hash, tests dir, lane).
- **Failure scenario:** the tests read `WHYNOT_SLOW_TESTS`, `WNC_INSTALLER_LIVE`, `NH_INTEGRATION`,
  `WHYNOT_PARITY_AUDIO`, `WNC_TEST_REAL_CREDSTORE`, `WNC_REQUIRE_SCANNERS`, `WHYNOT_TEST_ALLOW_LIVE_BRIDGE` and others
  (`test_audio_long.py:703`, `test_tidy_engine.py:860`, `test_installer.py:9738`, `test_pipeline.py:379`, ...). Example:
  1. A plain run (slow tests skipped) is cached as `OK (skipped=K)`.
  2. Someone runs with `WHYNOT_SLOW_TESTS=1` to actually run the 60-minute tests.
  3. They get `reused: ...` / `OK`, exit 0, and the slow tests never ran.

  The serial run with that environment might fail. This is the "did not actually run every test" case.
- **Fix:** add to the key a sorted hash of every environment variable whose name starts with `WHYNOT_`, `WNC_`, `NH_`,
  plus `PYTHONHASHSEED`. Leave out the values the tool sets itself: TEMP/TMP/TMPDIR, and `WHYNOT_SUITE_CACHE`. Better
  still, hash all variables except a short denylist of volatile ones. When in doubt, miss.

### P2-3: unexpected successes are counted as failures, but no test covers it (a surviving mutant hides a false green)
- **Where:** `tools/test_parallel.py:148-149`, `:295-309`; nothing in `whynot-cut/tests/test_test_parallel.py` covers it.
- **Evidence:** mutant 5 (`counts[...] += 1` skipped for `UNEXPECTED SUCCESS`) gives `Ran 21 tests`, `OK`: it survives.
  Under that mutant, a module whose `@expectedFailure` test starts passing reports `OK`, exit 0, and gets cached, while
  serial gives `FAILED (unexpected successes=1)`.
- **Fix:** add a fixture `case_xpass.py` with one `@unittest.expectedFailure` test that passes. Assert exit 1,
  `FAILED (unexpected successes=1)`, and no `\nOK`.

### P2-4: "a worker that writes a valid record and then exits non-zero is INCOMPLETE" has no test (surviving mutant)
- **Where:** `tools/test_parallel.py:203-204`. The `killed` fixture SIGTERMs before any record exists, so it never
  reaches this branch.
- **Evidence:** mutant 1 (delete the `elif self.rc != 0` branch) gives `Ran 21 tests`, `OK`: it survives. That branch
  is the card's 10:19 lesson ("exited by itself"): for example, a `tearDownModule`/atexit/thread crash after the record
  is written, or a worker killed during interpreter shutdown.
- **Fix:** add a fixture whose module registers `atexit.register(os._exit, 3)`. The record is written, then the exit
  code is 3. Assert exit 2, `INCOMPLETE`, the module named, and nothing stored.

## P3

- **P3-1, `tools/test_parallel.py:323-324`: labels come after the FAILED line.** With 9 or more labelled failures, the
  FAILED line falls out of `tail -n 10`, which MASTER-INTAKE 1B's reuse rule greps
  (`tail -n 10 "$L" | grep -qE '^(OK|FAILED)'`). That fails safe (it only re-runs), but the reuse rule stops working
  exactly when it matters. **Fix:** print the `parallel:` lines (labels included) before the `Ran`/`OK`/`FAILED` block,
  so the status line is last, as in serial.
- **P3-2, `:285-303`: an incomplete run still prints `Ran N tests in`, then `INCOMPLETE (...)`.** Any reader that
  checks only `^Ran ` and the absence of `FAILED` reads it as green. **Fix:** write it as
  `FAILED (incomplete=K: <modules>)`, so every OK/FAILED grep fails closed. The exit code stays 2.
- **P3-3, `:329-333`: `main()` reconfigures stdout/stderr to `errors="replace"` in worker mode too.** Serial unittest
  under `PYTHONUTF8=1` keeps `surrogateescape` on stdout and strict behaviour for lone surrogates, so a test that
  prints an unencodable string errors serially and passes in parallel. **Fix:** do the reconfigure only after the
  `if a.worker:` branch (the parent only).
- **P3-4, `:412`, the subtest label.** A subtest problem id such as `mod.C.test_x (i=1)` is not reduced by
  `HOLDER_ID`, so the relabel run matches 0 tests and the label is always "label unknown". This is informative only.
  **Fix:** strip a trailing ` (...)` when the part before it is a dotted test id.
- **P3-5, crashes inside the tool exit with code 1.** An uncaught exception in the parent (for example `Popen` failing
  in `Job.__init__`, or the cache folder not writable at `:431-438` after `OK` was already printed) ends in a
  traceback with exit 1, which the card defines as "complete with failures". **Fix:** wrap the parent in `try/except
  Exception` and return 2 with a `parallel: tool error:` line. Make the cache/durations write best-effort: warn, do not
  change the code.
- **P3-6, `:238-240`: `ram_peak` is sampled only when a module is about to start.** The long tail after the last start
  is never sampled, so the reported peak understates the real one, and the card asks for the peak.
  **Fix:** sample in every loop iteration (it is cheap).
- **P3-7, `:263`, by the card's letter but worth noting.** Untracked files outside `whynot-cut/` and `tools/`, and
  ignored files (local configs, downloaded fixtures), are not in the key. Tests such as release hygiene and identity
  scan walk the whole repo. Note it as a known limit, or widen the key to the whole repo's non-ignored untracked files.
- **P3-8, the runtime id is `sys.executable | sys.version | -s` (`:366`).** An in-place reinstall of packages in the
  same `runtimes/<id>` does not change the key. Add a hash of `pyvenv.cfg` plus the site-packages `*.dist-info` names,
  or note it as a known limit.

## Checked and fine
- **Discovery** (`:44-51`): it uses the same `VALID_MODULE_NAME` and `fnmatch` as `unittest.loader`. Packages are
  refused with exit 2. `whynot-cut/tests/{fixtures,security,test_kalam_fixtures}` have no `__init__.py`, as for
  serial. The worker uses `TestLoader().discover(pattern=<mod>.py)`, so import errors still count as `_FailedTest`
  errors.
- **Worker flags:** `-s` (when the parent has it), `-B`, `-W error::ResourceWarning`, PYTHONUTF8 and
  PYTHONDONTWRITEBYTECODE are passed. The cwd is the repo root. TEMP/TMP/TMPDIR is a per-module sub-folder under the
  test.sh TEMP rule.
- **The strict rule:** the exit code and the FAILED line come from first-run records only. Mutants 2 (labels change the
  count) and 3 (relabel skipped) were killed by the tests.
- **Complete or nothing:** a missing record, a malformed record, or a lane id with 0 tests gives exit 2 with nothing
  stored. A stale record is unlinked before each spawn. The record is written atomically.
- **Serial lane:** the exclusion uses `id == s or startswith(s + ".")`, so it never drops a neighbour with a prefix name.
  Lane results count.
- **Output** keeps the `Ran N tests in X.XXXs` / `OK (skipped=K)` / `FAILED (failures=…, errors=…, skipped=…)` order of
  `TextTestResult`. Arabic is UTF-8 end to end (test green).
- **tools/test.sh:** only the 5 dispatch lines are added. The serial `exec` line is unchanged. The code is bash 3.2-safe.
  The Windows RAM struct (GlobalMemoryStatusEx, 7 ULONGLONG fields) is correct. macOS `vm_stat` is an approximation, as
  the build report says, and has not run on a Mac.
- **Karpathy:** the diff is surgical and the size fits the scope. No over-engineering worth flagging.

## Note on the review itself
One experiment command was mis-composed: a backgrounded `cd` meant two commands ran from the session cwd, which is the
main `WhyNotCut` checkout.
- A `sed -i` on `whynot-cut/tests/test_b.py` and a `git checkout -- whynot-cut/tests/test_b.py` both failed because the
  file does not exist. Nothing changed.
- A serial `python -B -m unittest discover -s whynot-cut/tests` (system Python 3.13) ran there for under 2 minutes. It
  was stopped with TaskStop, and no process from it is left.

Its tests are sandboxed by `_isolation`. It may have left sandbox temp folders in the system TEMP.

## Verdict
**FAIL.**
- P1-1 and P1-2 are reproduced false greens, and P1-2 also reaches the cache.
- P2-1 and P2-2 are further ways to serve a cached OK for code or settings that were not run green.
- P2-3 and P2-4 are holes in the tests over the strict rule and the incomplete-run guard (2 of 5 mutants survived).

All fixes are small and local to `tools/test_parallel.py` plus fixtures.
