# OPS-09 review, round 3 (fix round 3, acceptance blocker)

- **Reviewed:** `97b076f` on `ops/OPS-09` (parent `b60b422`), worktree `D:\WNC-work\ops-09`
- **Date:** 2026-10-22
- **Reviewer:** fresh independent sub-agent (oh-my-claudecode:code-reviewer, read-only). Static review: the permission
  layer refused its run of `test_test_parallel.py`, so the red/green evidence is the builder's logs.
- **Saved by:** the master, from the reviewer's returned text (the reviewer type has no Write tool, and its Bash
  heredoc was refused by the WhyNot Cut `guard.py` hook, a false positive on the word "lock"). Text unchanged.
  Master spot-checked `tools/test.sh:40-57` and `whynot-cut/tests/_isolation.py:126-136,186-190`: claims hold.
- **Verdict:** **PASS-WITH-MINORS** (no P1, no P2). Acceptance still waits on parallel run 2, the equivalence check.

## Central question: can a parallel run report PASS where serial FAILS, or lose or misreport a result?
No new path found.

- **TEMP is byte-identical to serial.**
  - `tools/test.sh:42-49` exports TEMP, TMP and TMPDIR *before* the `--parallel` branch at `:51-54`. So the serial
    `exec` at `:57` and the parallel parent at `:53` start with the same three strings.
  - The parent never changes its environment. `tools/test_parallel.py` has no `os.environ[...]`, `pop`, `update`,
    `putenv` or `tempfile.tempdir`.
  - Workers get `dict(os.environ, PYTHONUTF8, PYTHONDONTWRITEBYTECODE)` (`tools/test_parallel.py:190`). The hand-off
    is Python to Python, so no MSYS path conversion happens.
  - Relabel and lane jobs use the same `Job` class, so they get the same env.
- **Every test process still gets its own sandbox.**
  - Every `whynot-cut/tests/test_*.py` imports `_isolation` (checked each file; `test_isolation.py:38` enforces it).
  - `_isolation._sandbox()` (`_isolation.py:126-163`) makes a unique `mkdtemp(prefix="whynot-test-sandbox-")` box. It
    then points TEMP, TMP, TMPDIR and `tempfile.tempdir` (`:190`) into `box/tmp`.
  - So inside a worker, `gettempdir()` is per process. The parallel run is more isolated than serial: one box per
    module instead of one for the whole run.
  - Only the items in the audit table below meet in the shared parent TEMP. None of them can hide a failure.
- **The path length is the same too.** The sandbox name has a fixed length (20-char prefix + 8 random chars), so
  `box/tmp` is the same length in both modes. That is the path semgrep sees: `tools/security/scan.py:95` passes the
  caller's env through `safe_env`.
- **The kept-log logic cannot change the result.**
  - The report and exit code are computed first (`tools/test_parallel.py:501`). The keep/tidy loop (`:502-509`) only
    decides which files stay.
  - The `log kept` lines go through `out()` (stdout, flushed) before `sys.stdout.write(report)` at `:533`, so the
    verdict stays the last line.
  - `report`, which is the cached text (`:529-530`), never contains those lines.
- **No stale record can be read.** A kept `wnc-par-<pid>` folder may still exist when a pid is reused.
  `Job.__init__` unlinks `record.json` before it spawns (`:179-180`), and the log is reopened with `"wb"`. If the
  unlink fails, it raises and the run ends `FAILED (incomplete: tool error ...)` with exit 2.
- **The cache cannot serve an old green.** `tool_ver` is the sha of `test_parallel.py` (`:441`), so every round-2
  entry, made with the long-TEMP tool, misses.

## Diff check (`git diff b60b422 97b076f`)
- **`Job.__init__` (`:188-190`):** the `tmp` creation and the TEMP overrides are gone. The comment is accurate.
- **`Job.tidy` (`:214-224`):** removes only its own two files, then its folder with `rmdir`, never recursively. The
  orphaned `tmp` rmdir was correctly removed.
- **`kept` (`:502-509`):**
  - Incomplete jobs are kept. This includes lane jobs with `tests_run == 0`, which `:481-485` moves to `incomplete`,
    so they are never in `results` and never tidied.
  - Every job in `results` with a non-empty `rec["problems"]` (FAIL, ERROR or UNEXPECTED SUCCESS) is kept, for both
    `m-` and `lane-` tags.
  - Clean jobs are tidied. Relabel jobs (`j not in results`) are always tidied.
  - `j.rec` is never None for a job in `results` (`:480`).
  - The membership test `j in results` compares identity (`Job` has no `__eq__`), which is correct. No job appears
    twice in `kept`.
- **`RUN_DIR.rmdir()` (`:511`):** fails silently while kept folders exist, as intended.
- **Comments:** the docstring (`:3-9`) and the `RUN_DIR` comment (`:39`) match the new behaviour.

## Findings

### P1: none

### P2: none

### P3 (notes; none blocks)

- **P3-1. All workers share one sandbox when the parent already has `WHYNOT_TEST_SANDBOX`.**
  `_isolation.py:127-128` with `tools/test_parallel.py:190`. If `tools/test.sh --parallel 6` is started from an env
  that already holds `WHYNOT_TEST_SANDBOX` (e.g. from inside a test process), every worker skips sandboxing and all 6
  share one HOME, WHYNOT_HOME and TEMP at the same time. Normal runs (heavy.sh → test.sh) never have this variable.
  Mostly only adds failures; a test like "refuses while a lock exists" could pass on another module's lock. Fix:
  refuse with exit 2 in `parent()` when it is set, or drop it from the workers' env. Likelihood: LOW.
- **P3-2. Nothing pins that test.sh exports TEMP *before* the `--parallel` dispatch** (`tools/test.sh:42-54`;
  `ThroughTestSh`, `test_test_parallel.py:543-556`, checks only the dispatch). Fix: run the `tempenv` fixture through
  test.sh with `WHYNOT_TEST_TMP=<dir>` and assert the worker's TEMP/TMP/TMPDIR.
- **P3-3. TEMP is not in the cache key** (`tools/test_parallel.py:36,339-342`), and it is now known to change results.
  `WHYNOT_TEST_TMP` is in the key; the fallback is fixed per machine and the cache is per machine, so low risk. Cheap
  hardening: add TEMP, TMP, TMPDIR to `env_key()`.
- **P3-4. "The cached report has no paths" is true by construction but not asserted**
  (`test_cache_hit_reuses_the_report_and_says_so`, `:356-367`). Add `assertNotIn("log kept", out2)` and no `wnc-par-`
  in the stored report.
- **P3-5. The log of an incomplete relabel re-run is tidied away** (`:503-507`): diagnosis only; the label never
  changes the exit code. Optional: keep it when `r.rec is None` (needs a unique `relabel-<n>` tag).
- **P3-6. The new log test does not cover a `lane-` job with problems, nor assert the `relabel` folder is gone**
  (`:281-296`). Code handles both; coverage gap only.
- **P3-7. Card wording.** `00-HQ/tasks/OPS-09.md` "Design (binding)" still says each module gets "its own TEMP
  sub-folder"; a later round could "restore" it. Also the "~46 chars" semgrep threshold is the *outer* TEMP test.sh
  sets; semgrep receives the sandbox `box\tmp`, about 34 chars longer. Fix the BACKLOG side-finding wording to match.
  (Confidence on the exact figure: MEDIUM.)
- **P3-8. Known limit, accepted.** Kept `wnc-par-<pid>` folders are never pruned (`sweep_stale` ignores them).

## The two new tests: do they pin the behaviour?
**`SameAsSerial.test_workers_keep_the_parent_temp_variables_unchanged` (`:181-204`): pinned.** The fixture does not
import `_isolation`, so it sees the inherited env as it is. Three different strings catch any swap or merge; the
no-TMPDIR case catches an invented one; the comparison with the parent catches any rewrite, including a shorter TEMP;
the comparison with serial covers `gettempdir()`. It fails on the b60b422 tool (builder's red log).

**`Results.test_problem_and_incomplete_modules_keep_their_log_clean_ones_do_not` (`:281-296`): pinned, with the gaps
in P3-4 and P3-6.** Covers FAIL + ERROR, UNEXPECTED SUCCESS and a killed worker, asserts each `log kept` line, and
catches keeping every log, tidying a problem log, and printing after the report.

## r1 and r2 fixes: regressed?
No: import path like serial (`:141-145`); key re-check and tree stamp (`:452`, `:517-520`); `WHYNOTCUT_` prefix
(`:36`); `--no-optional-locks` (`:268`); `atomic_write` (`:290`, `:527-530`); verdict-last ordering.

## Shared-TEMP audit (6 concurrent workers plus the parent, one parent TEMP)
Classes: **a** = can only add a visible failure; **b** = could pass or skip in parallel where serial fails (false
green); **none** = per process or unique.

| Path pattern | file:line | Class | Note |
|---|---|---|---|
| `mkdtemp(prefix="whynot-test-sandbox-")` in the parent TEMP | tests/_isolation.py:134 | none | O_EXCL random name, one per process |
| `sweep_stale(gettempdir())` (removes stale `whynot-test-sandbox-*`, marker > 24 h) | tests/_isolation.py:104-123,133 | a (theoretical) | Live marker written at creation; only a > 24 h run could be hit; `rmtree_retry` swallows `OSError`; never touches `wnc-par-*` |
| `wnc-par-<pid>/<tag>/record.json, worker.log` | tools/test_parallel.py:39,175-180 | none | Parent only, unique per pid; stale record unlinked before spawn |
| `WHYNOT_TEST_TMP/wnc-XXXX` | tests/test_installer.py:183-186 | none | `mkdtemp`, own cleanup |
| `gettempdir()/kalam-run-settings.json` | tests/test_kalam_engine_run.py:206-210 | none | Inside the per-process sandbox |
| `gettempdir()/../../escape.json` | tests/test_kalam_engine_run.py:230-232 | none | Never written; refusal asserted |
| `gettempdir()/whynot-test-clients-root-unset` | tests/test_writer_lock.py:37; tests/test_plugin.py:25 | none | Env value inside the sandbox |
| `gettempdir()/"C l"/عميل`, `/Fonts/f.ttf` | tests/test_t45_writers.py:132,137 | none | String path maths |
| `gettempdir()/no-such-tool-xyz.exe` | tests/test_sign_zxp.py:385 | none | Inside the sandbox |
| `gettempdir()/AR_DIR/...mp4` | tests/test_gpu_accel.py:354-355,1401 | none | argv strings for fake runners |
| `gettempdir()/ARABIC_HOME` | tests/test_installer.py:2407 | none | Path maths; sandbox |
| `gettempdir()/*/wnc-probe-<pid>-<id>` | tests/test_release_identity_gate.py:202-209 | none | Unique per pid and test |
| `gettempdir()` as home, cwd or Context | test_serve_app.py:1247; test_plugin.py:147,159; test_crossplatform.py:247,257; test_frame_size.py:316; test_cli_consistency.py:672; test_cli_perf_report.py:105 | none | Per-process sandbox |
| `mkdtemp(dir=os.environ["TMP"])` | tests/test_security_scan_findings.py:40,50; tests/security/fuzz/_hyp.py:551 | none | Unique; TMP is the sandbox |
| Engine `mkdtemp(prefix="whynot-aerender-")` | engine/reel/lib/ae_render.py:179,215 | none | Unique; `%ProgramData%\WhyNotCut\tmp` only with non-ASCII TEMP, unchanged |
| Engine `cep_log_dir()` = TEMP | engine/reel/lib/plat.py:788 | none | Location only; sandboxed |
| Engine kalam allow-roots `(run_dir, gettempdir())` | engine/reel/lib/kalam/store.py:91 | none | Allow-list, not a write |
| Test modules without `_isolation` | none | n/a | `test_parallel` fixtures run in nested tool runs with the test's own TEMP |

**Cleanup that could delete another module's live files:** only `sweep_stale`, guarded by prefix, marker and 24 h age.
**Out of scope, unchanged by round 3:** non-TEMP shared resources (fixed localhost ports, `%ProgramData%\WhyNotCut\tmp`);
workers already shared them in rounds 1 and 2.

## Verdict
**PASS-WITH-MINORS.** No path to a false green, a lost result or a misreported one. The P3s are optional hardening and
coverage. Acceptance still needs parallel run 2 on 97b076f to match the serial failing set (excluding
`test_test_parallel`).

## Master disposition (2026-10-22)
LIGHT tier, fix rounds already past the limit (round 3 was an acceptance blocker). No round 4: P3-1…P3-6 and P3-8 go
to the card's "Known limits" as follow-up hardening; P3-7 card wording fixed by the master now.
