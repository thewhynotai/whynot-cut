reviewer: fresh Opus subagent (Command Center review)
suite: Ran 27 tests in 6.342s — OK (`python -X utf8 -m unittest test_hq_status`)
verdict: PASS-WITH-MINORS

Dry run (`python -X utf8 hq_status.py`, no flags): no traceback, section 3 shows
`PREVIEW-3.0.0-p4 @ 322d8a5d (2026-10-19 01:55 UTC) — متحدّثة مع GitHub`. Real `wnc-queue status --owner release`
called from Python exactly as the code does (`["bash", WNC_QUEUE, ...]`): exit 0, resolves to Git bash on this PC.

## Acceptance
1. Report shows preview label/sha vs origin — **PARTLY OK**: label, LABEL commit and up-to-date/behind are shown;
   the origin sha that `--check` prints is discarded (see P3-1). Only the Windows folder's LABEL is read.
2. No build in the report run; refresh only queued through wnc-queue — **OK**: only `refresh.py --check` runs (it
   returns before any lock/build, refresh.py:400-403); the rebuild is only `wnc-queue add` and only under `--write`.
3. Runbook updated — **OK**: AUTOMATION_RUNBOOK.md:18 marks lane-watch DISABLED / RETIRED, points to OPS-03.

## Findings
**P2-1 Already-queued detection is blind to QUEUED jobs** — hq_status.py:169-173. `wnc-queue status` prints titles
only for running jobs (cli.py:221-223); queued ones are just a count. While STOP is set, the runner is down, or 4
jobs fill `max_parallel`, every `--write` report adds another "release preview refresh". (0f had the same text
check.) Fix: call `wnc-queue list --owner release --json` and test
`any(j["state"] in ("running","queued") and j.get("title")=="release preview refresh" for j in json.loads(out))`.
Add a test with a queued row.

**P2-2 FAILED refresh.log line dropped** — 0f step 3 reported a last refresh.log line containing "FAILED"; no
equivalent exists (grep: no `refresh.log` in hq_status.py). A failed rebuild is now silent. Fix: in
`preview_state` read the last line of `PREVIEW_DIR/"refresh.log"` (try/except OSError); if "FAILED" in it, set
`st["failed"]=line[:300]` and list it in section 5 (errors). Test both cases.

**P2-3 `add` can crash the report** — hq_status.py:174-177 is outside any try; `TimeoutExpired`/`OSError` abort
`main()` before the report is written. Fix: wrap in `try/except (subprocess.SubprocessError, OSError)`.

**P2-4 Failed `status` is read as "nothing queued"** — hq_status.py:169-173 uses `.stdout` even when the exit code
is non-zero (e.g. "Python 3.9+ not found", exit 2) → empty string → queues. Fix: return `st` unless
`returncode == 0`.

**P3-1** Keep `--check` stdout: parse `origin/release/3.0 = (\w+)` into `st["origin"]` and print it in
`preview_line` (hq_status.py:378-386) to fully meet acceptance 1.
**P3-2** `75` label (hq_status.py:381) is unreachable for `--check` (refresh.py:400-403 returns 0/10 or crashes
with 1). Map 1/2 to "الفحص فشل" plus the last stderr line instead.
**P3-3** Bare `"bash"`: Windows CreateProcess searches System32 before PATH, so a future WSL `bash.exe` would win.
Use `shutil.which("bash")` / Git's `usr\bin\bash.exe` (refresh.py uses `rel.find_bash()`).
**P3-4** A refresh.lock older than 4 h counts as stale for refresh.py (take_lock, refresh.py:117-124) but blocks
queuing here forever. Ignore locks older than 4 h.
**P3-5** The test's "busy" fixture (`running: release preview refresh`) does not match the real status format
(`  running  <id>  run N, <age>  <title>`). Use real output.
