# OPS-09 — Parallel full suite: `tools/test.sh --parallel N`, failure re-run that only labels, per-commit cache

**Archived:** DONE_ARCHIVED 2026-10-23 05:50 (master). Merged on release/3.0 as b81baaa; origin = abdece5 (verified ls-remote).

- **Assigned:** MASTER (built by a fresh executor sub-agent in its own worktree; reviewed by a separate fresh sub-agent)
  **Size:** M    **Status:** ACCEPTED (2026-10-23 03:00, master; equivalence run 4 on 302df0d; see "Verdict" below)
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

- **Run 3 (2026-10-22 20:53–21:21, `ops09-parallel3`, commit 79989c9, log
  `D:\ClaudeData\setup-phase6\ops09\parallel-run3.log`):** Ran **9546** (as expected), wall 1693.9 s (28.2 min),
  RAM peak 84 %. FAILED (failures=4, errors=1, **skipped=49**, expected failures=21, unexpected successes=2). The
  round-4 lane worked (the wnc_queue timeout test passed in the serial lane). **Not equivalent yet:** (1) one extra
  failure, OPS-09's own `test_test_parallel.Cache.test_git_takes_no_optional_index_lock` (`.git/index` of the test's
  temp repo got a new mtime, same size, during the tool run; the tool labels it "load-sensitive (passed alone)");
  (2) one extra skip (49 vs 48 serial); the tool does not list skipped ids, so it cannot be named from this log (a
  free-RAM guard skip at 84 % is the likely class, unproven). Master check 21:25: `git maintenance --detach`
  (spawned by every commit) does not write the index (trace2); a 40-run trace2 probe under the real load is queued
  (`master-ops09-t2loop`). **Not accepted**: the strict rule allows no extra failure. Next: root cause from the probe,
  then fix round 5 (and the skipped-ids gap: compare skip sets too).

- **Root cause + fix round 5 (master, 22:28–22:45).** Probe `master-ops09-t2loop`: the test alone failed **20 of 40**
  runs, so not load: luck. git trace2 per process (`<scratchpad>/t2loop/run1`): the only writer of `.git/index` during
  the tool run is `git --no-optional-locks diff HEAD --binary …` (`do_write_index`), on a tracked file with a new
  mtime and the same bytes (git 2.56.0.windows.2 ignores the flag there). A real contract bug (review r2 P3-1: never
  write the index of a shared checkout). Fix `725b852`: `dirty_key` drops the `diff HEAD` bytes (status + raw bytes of
  every listed path already cover it); the test forces the stale stat entry (`os.utime` +2 s): red 5/5 before, green
  5/5 after, file 39/39. Review r5 (fresh) and equivalence run 4 (`ops09-parallel4`, expected Ran 9546, failing set =
  the 4 baseline ids) follow. The extra skip (49 vs 48) is still unnamed: the tool prints no skipped ids.
- **Review r5 (`reviews/OPS-09-r5.md`): PASS-WITH-MINORS** (0 P1/P2). Minors done in `302df0d`: the index test compares
  the index bytes (red 3/3 on the old tool, green 3/3; file 39/39); docstring names the key's known limit (submodule
  commit, mode-only bit, retargeted dir symlink: none in this repo). Run 4 runs on 302df0d (checkout moved before it
  started).
- **Run 4 (2026-10-23 02:30–02:58, `ops09-parallel4`, commit 302df0d, log
  `D:\ClaudeData\setup-phase6\ops09\parallel-run4.log`): EQUIVALENT.** (The first queueing at 22:37 waited 172 min and
  was dropped by an app restart at ~01:20 before it started; re-queued 01:26; it started at RAM 65 % with nothing else
  heavy running.) Ran **9546** (= 9539 serial − 32 + 39, `test_test_parallel` only) ✓; FAILED (failures=3, errors=1,
  **skipped=48**, expected failures=21, unexpected successes=2) = the serial line field by field ✓; failing set =
  exactly the 4 baseline ids (gpu_accel libx264 ERROR, ae_extras + motion non-ASCII, media_normalise av-sync), each
  labelled `fails alone too` ✓; no extra failure. Wall **1688 s (28.1 min)** ✓, RAM peak 73 %. The two fuzz modules'
  logs were kept only for their known unexpected successes (1 + 1 = the serial 2). Run 3's extra skip (49) did not
  recur; the tool still prints no skipped ids (known limit below).

## Verdict (master, 2026-10-23 03:00): ACCEPTED
- [x] Tests first: red 15 F + 5 E before the tool, green after (`inbox/master/2026-10-22-OPS-09-build.md`); now 39/39.
- [x] heavy.sh `psuite`: heavy-test passed 81 / failed 0 (`2026-10-22-OPS-09-fix2.md`), backups dated next to it.
- [x] Equivalence on the real repo: run 4 above against `serial.log` (same count rule, same skips, same failing set).
- [x] Wall time ≤ 30 min: 28.1 min (run 4), RAM peak 73 %, nothing else heavy running.
- [x] Serial `tools/test.sh` unchanged: only the 5 dispatch lines (build report; reviews r1–r5).
- [ ] **Mac CI green on push: OPEN.** Needs the owner's push decision (release/3.0 holds 115+ unpushed commits). The
      code is reviewed bash 3.2-safe; the macOS `vm_stat` RAM read has never run on a Mac (r1). Moves to the push.
- [x] Independent reviews: r1–r5 (r3, r4, r5 PASS-WITH-MINORS, 0 P1/P2). Fix rounds 3–5 went beyond the LIGHT limit on
      purpose (each was an equivalence blocker; owner's rule: quality first). P3s under Known limits.
- **Merge:** release/3.0 moved one commit since the branch point (b7e2190, test_ae_extras + test_motion only); no
  file overlap with OPS-09, so fast-forward is impossible but the merge is clean. Executor merges (merge commit, like
  BL-16) per `MERGE-QUEUE.md`. After b7e2190 the two non-ASCII tests should pass, so the next baseline should be 2
  failures; the first suite after the merge confirms it.
- **Then:** the suite command switch (PLAYBOOK §2, MASTER-INTAKE 1B, helper_loop.py prompts, README) follows the merge
  (the tool must be on release/3.0 before anyone is told to use it).

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
