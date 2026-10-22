# OPS-09 — Parallel full suite: `tools/test.sh --parallel N`, failure re-run that only labels, per-commit cache

- **Assigned:** MASTER (built by a fresh executor sub-agent in its own worktree; reviewed by a separate fresh sub-agent)
  **Size:** M    **Status:** IN PROGRESS (opened 2026-10-22 by the owner's explicit approval in chat)
- **Tier:** LIGHT (dev tooling: it decides nothing an editor or a client sees). But it is the runner every gate trusts,
  so its acceptance below is strict: a parallel run must mean exactly what a serial run means.
- **Owner words (chat, 2026-10-22):** «افتح كارت الـ parallel suite دلوقتي ونفّذه (tests + مراجعة مستقلة)، بالقاعدة
  الأشد: أي فشل في أول تشغيل يفضل فشل». Request from the audit session (`local_eab80a9e`): "use it everywhere".

## Why
heavy.sh stats (137 runs): a full suite averages 68 min run + 51 min queue wait, and two suites together use ~12 % CPU
on a 28-thread PC: the suite is single-core bound. The audit session's measurement (clean export of c963132, 6
processes, `D:\ClaudeData\Temp\shard-test-6`, prototype `…\eab80a9e…\scratchpad\shard_suite.py`): 9,459 tests, 5 of 6
shards 12–25 min, one unbalanced shard 42.7 min, RAM peak 76 %, CPU ~40 %. Balanced, a full run is ≈ 22–30 min.

## Design (binding)
- `tools/test.sh --parallel N` (N ≥ 2) resolves the interpreter exactly as today, sets the same TEMP rule, then runs a
  new stdlib-only `tools/test_parallel.py` with that interpreter. Without `--parallel`, `tools/test.sh` is byte-for-byte
  the same behaviour as today (serial `unittest discover`).
- **Units = modules.** The test modules are exactly the ones `unittest discover -s whynot-cut/tests` finds
  (top-level `test*.py`; there are no test packages today; if one appears, the tool must say so and exit 2, never
  silently skip it). Each module runs in its **own fresh process** with the same flags as serial
  (`-s` if the runtime uses it, `-B -W error::ResourceWarning`, `PYTHONUTF8=1`, `PYTHONDONTWRITEBYTECODE=1`) and
  TEMP/TMP/TMPDIR inherited unchanged from `tools/test.sh`, byte-identical to serial (changed in fix round 3: a
  per-module TEMP made paths longer than serial and broke semgrep; never give workers a different TEMP). N workers take modules from a queue, longest first (recorded duration from the last complete
  run; file size when there is none). Durations are stored after every complete run.
- **RAM brake:** no new module process starts while RAM ≥ 85 %; it waits (nothing is killed, nothing skipped). On a
  system where RAM can't be read, say so once and go on.
- **Serial lane:** a named list in the tool of load-sensitive tests is taken out of the parallel run and run alone,
  serially, after it: `test_identity_scan.TestRealTree.test_full_repo_scan_is_fast`, and the `test_serve_progress`
  classes `AdapterRun` and `ThroughTheDaemon` (exact ids checked against the code). Their results count like any other.
- **The strict rule (owner):** every test that FAILS or ERRORS in its first run counts as a failure, full stop.
  Afterwards each such test is re-run alone, serially, only to **label** it in the report: `fails alone too` or
  `load-sensitive (passed alone)`. The label never changes the exit code or the FAILED line.
- **Output** keeps what every reader greps today: the FAIL/ERROR blocks with tracebacks, then `Ran <N> tests in <s>s`,
  then `OK` / `OK (skipped=K)` / `FAILED (failures=F, errors=E[, skipped=K])`, plus a short `parallel:` summary
  (workers, wall, slowest modules, RAM peak, the label list). Exit 0 only when complete and green; 1 when complete
  with failures; 2 when the run is incomplete or broken.
- **Complete or nothing:** a run counts only if every module's worker wrote its result record (tests run, failures,
  errors, skips, duration, `complete: true`) and exited by itself. A killed, crashed or timed-out worker, a missing
  record, or a total that does not equal the sum makes the run **incomplete**: exit 2, the text says which module, and
  no cache entry and no durations are written. (Lesson of 10:19: a `taskkill` read as `rc=0` through the msys wrapper.
  The cache and the result must come from the records, never from an exit code alone.)
- **Per-commit cache:** key = commit sha + a hash of the dirty tree (`git diff HEAD` + untracked, non-ignored files
  under `whynot-cut/` and `tools/`) + runtime id + the tool's own version. A complete run stores its full report;
  `--parallel` with a cache hit prints the stored report with a first line `reused: <key> from <date>` and exits with
  the stored code. `--fresh` ignores the cache. Cache folder: `$WHYNOT_SUITE_CACHE`, else
  `D:/ClaudeData/suite-cache` when `D:/ClaudeData` exists, else `<WHYNOT_HOME>/suite-cache`.
- **heavy.sh** (`side-session-notes/…/heavy.sh`, with `heavy-test.sh`): new kind `psuite` = one job that holds BOTH
  suite slots and two heavy slots, starts only at RAM < 75 %, first come first served like `suite`. Stats/log show the
  kind. No other behaviour of heavy.sh changes.

## Fence
- WhyNotCut repo, branch `ops/OPS-09` from `release/3.0`, worktree `D:\WNC-work\ops-09`:
  `tools/test.sh` (only the `--parallel` dispatch), new `tools/test_parallel.py`, new
  `whynot-cut/tests/test_test_parallel.py` + `whynot-cut/tests/fixtures/test_parallel/**` (fixture files named
  `case_*.py`, never `test_*.py`).
- `heavy.sh` + `heavy-test.sh` (backup copy first, next to them, dated).
- After acceptance only: the suite command in `00-HQ/PLAYBOOK.md` §2, `00-HQ/roles/MASTER-INTAKE.md` 1B,
  `D:\ClaudeData\accounts\helper_loop.py` prompts, `00-HQ/README.md` startup prompts, and a note to the executor.

## Acceptance (each line is checkable)
- [ ] Tests first: `test_test_parallel.py` red before `tools/test_parallel.py` exists, then green. They cover: module
      discovery equals `discover`; LPT ordering from durations and from sizes; a failing fixture counted as failure;
      a fixture that fails only under load labelled `load-sensitive` and STILL failure / exit 1; a killed worker → exit
      2, no cache, no durations; a missing record → exit 2; cache hit reuses and says so; a dirty-tree change misses
      the cache; `--fresh`; the serial lane runs its ids alone and they count; Arabic (UTF-8) test names and messages
      print correctly; RAM brake waits (simulated RAM).
- [ ] heavy.sh: `heavy-test.sh` extended for `psuite` (holds both suite slots, blocks a `suite`, waits at RAM ≥ 75 %)
      and the whole old `heavy-test.sh` still passes.
- [ ] **Equivalence on the real repo** (both through heavy.sh, same clean export of the branch tip, same machine):
      a serial `tools/test.sh` and `tools/test.sh --parallel 6`: **identical test count**, identical skip count, and the
      **identical set of failing test ids** (the environment baseline; at c963132 it was 4: 2× non-ASCII temp naming,
      gpu_accel libx264, media_normalise av-sync). Any extra parallel failure is listed with its label; it is a
      finding to explain, not to wave away.
- [ ] Wall time of the parallel run ≤ 30 min (state the RAM peak and what else was running).
- [ ] Serial `tools/test.sh` without `--parallel` unchanged (diff shows only the dispatch lines).
- [ ] Mac: plain `python3` + bash 3.2 compatible (no Windows-only call without a fallback); Mac CI green on push.
- [ ] One fresh independent review (sub-agent with no history), at most 2 fix rounds; open points written as known
      limits.
- [ ] Then: switch the suite command in PLAYBOOK §2, MASTER-INTAKE 1B (keep its reuse-by-sha rule; the cache now does
      it too), helper_loop.py prompts and the README startup prompts to
      `bash <heavy.sh> psuite <label> -- env PYTHONDONTWRITEBYTECODE=1 PYTHONUTF8=1 bash tools/test.sh --parallel 6`;
      tell the executor in writing; `hq_status` tests still green.

## Pre-mortem
- **Will it work for its real users (intake, peer reviewers, executor)?** Only if they can trust a green parallel run
  as much as a serial one. Hence: same count, same failing set, strict failure rule, complete-or-exit-2.
- **Holes:** (1) per-module processes are MORE isolated than one serial process: a test that only passes because an
  earlier module left state behind would now fail; that shows up in the equivalence check and is a real finding.
  (2) Six processes each import the engine: RAM. The brake + `psuite` at < 75 % cover it; the measurement peaked 76 %.
  (3) A module that hangs: give each worker no timeout by default (quality); the RAM-free parent shows which modules
  are still running every 5 min so a hang is visible. (4) The cache must never serve a result for different code:
  sha + dirty hash + runtime id + tool version; when in doubt, miss.
- **Prerequisites:** none; release/3.0 = 3aa6167 at opening. Main checkout has executor WIP: never touch it.

## Equivalence evidence (master, 2026-10-22)
- Serial reference on fb28e3f (clean worktree `D:\ClaudeData\Temp\ops09-eq`): `Ran 9539 tests in 4449s`, FAILED
  (failures=3, errors=1, skipped=48, expected failures=21, unexpected successes=2) = the 4 known env failures.
  Log `D:\ClaudeData\setup-phase6\ops09\serial.log`.
- Parallel run 1 (`--parallel 6 --fresh`, psuite): `Ran 9539 tests in 1725s` (28.7 min; slowest module
  test_installer 1708 s = the floor of module-level sharding), RAM peak 85–86 %. Same 4 env failures **plus 10 in
  test_security_scan, all `semgrep exit 2:` with no output**; the alone re-runs (16:4x) failed too.
  Investigation 16:50–16:55: the same tests pass through the exact worker command (one test, then the whole module,
  87 tests) and serially. Only test_security_scan calls semgrep; nothing concurrent explains it. Working theory: a
  machine-state window (RAM at the 85 % brake while semgrep-core starts) — unproven. Decision: a second parallel run
  before acceptance, not a waiver. Log `parallel-run1.log`.
- Tool gap found: logs of complete-but-failing modules are tidied away, so a worker's stderr is lost for diagnosis.
- **Root cause found 17:01 (deterministic, not machine state):** semgrep exits 2 with no output once TEMP is longer
  than ~46–48 chars (TEMP 28/31/37/41/45 → OK; 49/52/54/67 → `semgrep exit 2`). Serial TEMP =
  `D:\ClaudeData\Temp\wnc-tests` (28); the tool gave every worker `…\wnc-par-<pid>\m-<module>\tmp` (54–67). So the tool
  was NOT equivalent to serial. The queued 2nd run was cancelled (it would fail the same way).
- **Design change (master, 17:05):** workers inherit the serial TEMP/TMP/TMPDIR unchanged (no per-module TEMP).
  Identical path lengths; each module already makes its own sandbox inside TEMP; a cross-process collision can only
  add a failure, never hide one. A TEMP shorter than serial is forbidden (it could turn a serial failure into a pass).
  Failing modules keep their worker log. **Fix round 3** is beyond the LIGHT tier's 2 rounds on purpose: it is an
  acceptance blocker, and the owner's rule today is quality first.
- **Side finding for the executor (not this card):** `tools/security/scan.py` (semgrep) fails when the TEMP that
  `tools/test.sh` sets is longer than ~46 chars; semgrep itself receives the test sandbox `…\whynot-test-sandbox-XXXXXXXX\tmp`
  inside it, about 34 chars longer, so the real limit is on that inner path (≈ 80 chars; review r3 P3-7). A long
  Windows user name is enough. It fails loudly (`FAILED`), so it is not a false
  pass, but a developer would not know why. Candidate BACKLOG item: shorten semgrep's work path or say "TEMP path too
  long" in the note.
- **Equivalence plan after round 3:** the serial reference on fb28e3f stays valid for every module except
  `test_test_parallel` (round 3 changes only the tool, its own tests and fixtures; checked by `git diff --stat`), so
  the comparison excludes that one module rather than re-running a 74-min serial suite on unchanged code.
- **Fix round 3 = 97b076f** (parent b60b422; diff = `tools/test_parallel.py`, `test_test_parallel.py`, fixture
  `case_tempenv.py` only; `tools/test.sh` unchanged). Workers get `dict(os.environ, PYTHONUTF8, PYTHONDONTWRITEBYTECODE)`:
  TEMP/TMP/TMPDIR byte-identical to serial; records and logs stay in `<gettempdir>\wnc-par-<pid>\` (not the tests'
  TEMP). Problem and incomplete modules keep `worker.log` (`parallel: log kept: …` printed before the report; the
  verdict stays the last line). Tests: red on b60b422 (FAILED failures=3), green 37/37; neighbours OK. Review r3 and
  parallel run 2 (`ops09-parallel2`, log `D:\ClaudeData\setup-phase6\ops09\parallel-run2.log`) on 97b076f follow.
  Known limit: kept run folders are never pruned by the tool.
- **Review r3 (`reviews/OPS-09-r3.md`): PASS-WITH-MINORS**, 0 P1 / 0 P2 / 8 P3. Shared-TEMP audit: every test module
  sandboxes itself (`_isolation`), no path can turn a serial failure into a parallel pass. No fix round 4 (LIGHT).
- **Parallel run 2 on 97b076f (18:39–19:11, `parallel-run2.log`): NOT equivalent (strict rule).** Ran 9544 (= 9539 −
  32 + 37, `test_test_parallel` at fb28e3f vs 97b076f) ✓, skipped 48 ✓, expected failures 21 ✓, unexpected successes
  2 ✓; failing set = the 4 baseline ids **+ 1**: `wnc_queue_tool_tests.RunnerTests.test_timeout_kills_the_whole_tree`
  (label: load-sensitive, passed alone). Wall 1892.5 s (31.5 min; `test_installer` alone 1880.9 s), RAM peak 88 %
  (the BL-20 peer suite was not yet running; ~33 idle Claude processes held ~9 GB). The semgrep failures of run 1 are gone.
- **Fix round 4 = 79989c9 (master ruling, beyond the LIGHT limit again, on purpose):** the acceptance line says an extra
  parallel failure is "a finding to explain, not to wave away", and the designed answer for a load-sensitive timing
  test is the serial lane. The lane could not name this test: `test_wnc_queue.py` loads it under the module name
  `wnc_queue_tool_tests`, so its id does not start with the discovered module. Change: lane entries may be
  `module/selector` (`lane_entry()`), and that test joins `DEFAULT_SERIAL_LANE`. Tests first (red 2, green 39/39);
  real-repo check: worker `--only` that id ran 1 test, `--exclude` 151, whole module 152
  (`D:\ClaudeData\setup-phase8\ops09-r4\`). Review r4 and parallel run 3 (`ops09-parallel3`, expected Ran 9546) follow.
- **Wall-time line:** run 1 met it (28.7 min); run 2 missed by 1.5 min because one module (`test_installer`, 31.3 min
  under 88 % RAM) is the floor. Not fixable inside the tool (module-level sharding); recorded under known limits.

## Known limits (accepted at review r3; follow-up hardening, not blockers)
- P3-1: a parent env that already holds `WHYNOT_TEST_SANDBOX` makes all workers share one sandbox (normal runs never
  have it). Fix later: refuse with exit 2 or drop it from the workers' env.
- P3-2: no test pins that `tools/test.sh` exports TEMP before the `--parallel` dispatch.
- P3-3: TEMP/TMP/TMPDIR are not in the cache key (per-machine cache, fixed fallback: low risk).
- P3-4 / P3-6: "no paths in the cached report", a lane job with problems, and the relabel folder removal are not asserted.
- P3-5: an incomplete relabel re-run's log is tidied (diagnosis only).
- P3-8: kept `wnc-par-<pid>` folders are never pruned.
- RAM: a psuite peaked 85–86 %; two suites together peak 86–88 %. heavy.sh `psuite` starts only below 75 %.
- Module-level sharding floor: `test_installer` alone is ~28 min, so wall time cannot drop below it (31.3 min under
  88 % RAM in run 2: the "≤ 30 min" line holds only on a machine that is not already loaded).
- Review r4 (`reviews/OPS-09-r4.md`, PASS-WITH-MINORS, 0 P1/P2): P3-1 overlapping lane entries would run a test twice
  (refuse overlap later); P3-2 a method-level lane entry splits its class across two processes (a future class-fixture
  error would count twice); P3-3 no failing-aliased-lane-test case, guard text not asserted, `--serial-lane` help does
  not mention `module/selector`.

## Delivery
Branch `ops/OPS-09` (commit with explicit paths), report `00-HQ/inbox/master/2026-10-22-OPS-09.md`, review in
`00-HQ/reviews/OPS-09-r1.md`. Merge into release/3.0 by fast-forward only, after acceptance.
