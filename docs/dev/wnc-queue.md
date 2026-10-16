# wnc-queue — long non-AI jobs that keep running without Claude

A per-user job runner for dev work that should continue after a session ends, a usage limit hits or the Claude app
restarts: full suites, flaky-test hunts, benchmarks, render batches, downloads, Mac CI watches (`gh run watch`),
handoff builds. It is a dev tool (`tools/wnc_queue/`), not part of the shipped product.

**AI work never goes here.** No `claude`, no agents, nothing that needs a model. The queue never works around a usage
limit; it only keeps the machine busy with work that needs no AI.

## How it works

- Jobs are JSON files in `D:\ClaudeData\jobs\queue\`. The runner moves each one to `running\`, then writes the outcome
  to `done\<id>.json`. Output goes to `logs\<id>.log`.
- The runner is started by the scheduled task **WNC-Queue** (current user, no admin): at logon and every 10 minutes.
  `add` also starts it at once. The task runs it outside Claude's process tree, so closing or restarting Claude
  does not stop it. It exits when the queue is empty. A lock makes sure only one runner runs at a time.
- Every job goes through `heavy.sh` (COORDINATION rule 13), in the slot of its class: `suite`, `cpu` (heavy.sh `job`)
  or `gpu`. `none` is for light jobs (CI watch, a download) that need no slot. The timeout counts from when the slot
  is held, not while the job waits for one.
- If the runner dies in the middle of a job (crash, reboot, someone kills it), the job's whole process tree dies with
  it. On the next start the job goes back to the queue: finished runs are kept and the interrupted run starts again.
  After `max_attempts` (default 3) the job is marked `stranded`. If the runner itself keeps failing (30 errors in a
  row), it kills its jobs, leaves them in `running\` and exits. The next start re-queues them the same way.
- A queue file that is still not valid JSON after three passes and 5 seconds is refused. `done\<name>.json` gets
  status `error` and the file's first 2000 characters. A queue file with the id of a job that is running or done is
  refused too: its record gets a `.refused-<time>` name, so it never overwrites the real one.
- **STOP switch:** `wnc-queue stop` creates `D:\ClaudeData\jobs\STOP`. Running jobs are killed (status `stopped`),
  queued jobs wait, and nothing starts until `wnc-queue resume`.

## Use it (Git Bash, from the repo root)

Call it as `bash tools/wnc-queue …` (the file is not executable in git on purpose: a repo test fixes the exec bits).

```bash
bash tools/wnc-queue add --title "bridge flaky hunt" --class suite --until-fail 20 --timeout 30m --owner adobe -- bash tools/test.sh -p test_bridge_queue.py
```

```bash
bash tools/wnc-queue status --owner adobe
```

```bash
bash tools/wnc-queue result <id>
```

Everything prints **the result first** (COORDINATION rule 17), so a resuming session reads two to five lines:

```text
ATTENTION: 0 running, 0 queued, last 24 h 3 passed / 1 failed (owner adobe)
  ! 1 job(s) failed in the last 24 h
  FAILED   bridge-hunt  2h ago  run 7 of 20 failed after 6 passes: rc 1: AssertionError ...
  details: runner idle | task WNC-Queue | STOP no | 4 done records | D:\ClaudeData\jobs
```

`status` starts with `OK` or `ATTENTION`, then lists only the running jobs and the jobs that failed (failed,
timeout, error, stranded) in the last 24 hours. Cancelled and stopped jobs are counted but not flagged. It also says
ATTENTION when work waits with no runner: jobs left in `running\`, a crashed last runner, or jobs queued for 15
minutes with nothing picking them up. `result` line 1 is the verdict and summary. It shows the output tail only when the job did not pass
(`--tail N` to choose). `result` exits with 0 = passed, 1 = failed, timed out or cancelled, 2 = not finished yet,
3 = unknown id. `--json` gives the full record. `list --owner TRACK` lists one track's jobs. Other commands:
`cancel <id>`, `stop`, `resume`, `paths`, `install`, `uninstall`.

Put the command after `--` as separate words. It is never passed through a shell, so quotes, spaces, `*` and Arabic
text arrive exactly as written.

### Options for `add`

| Option | Meaning |
|---|---|
| `--class suite\|cpu\|gpu\|none` | heavy.sh slot (default `cpu`) |
| `--timeout 30m` | per run, after the slot is held (default 1h; `90`, `90s`, `30m`, `2h`, `1d`) |
| `--max-wait 6h` | longest wait for a slot before the job gives up as `timeout` |
| `--repeat N` | run N times; it passes only if all N pass |
| `--until-fail N` | run up to N times and stop at the first failure (a flaky hunt) |
| `--until-streak K --max-runs N` | run until K passes in a row, at most N runs |
| `--until-match REGEX` | run once; pass and stop the process as soon as REGEX appears in its output |
| `--pass-regex R` / `--fail-regex R` | a run passes only if R appears / fails if R appears (on top of exit 0) |
| `--owner TRACK`, `--priority -100..100` | who queued it; higher priority runs first, then oldest first |
| `--cwd DIR`, `--env NAME=VALUE`, `--id ID` | the default cwd is the current folder; an id can't look like the runner's own files (`.spec`, `.cancel`, `.json`, `.log`, `.dup-` …) |
| `--file job.json` | a whole job as JSON (the same fields as a queue file) |

### What `done\<id>.json` holds

The keys are in reading order, so the first lines of the file are enough:
- **First:** `headline`, one line (e.g. `FAILED: run 7 of 20 failed after 6 passes: rc 1: AssertionError ...
  [bridge-hunt, adobe; ran 9m40s]`), then `status` (`passed`, `failed`, `timeout`, `cancelled`, `stopped`, `error`,
  `stranded`), `passed`, `summary` and `pressure`.
- **Memory pressure:** when system RAM peaked at 85% or more while a run was running, the record holds
  `pressure_ram_peak_pct`, `pressure_cause` and, where known, `pressure_job_mb` (the job's own memory when RAM
  peaked) and the machine's `pressure_ram_total_mb`. The headline says it first, and whose memory it was:
  - other programs filled RAM (`pressure: true`, cause `machine`):
    `FAILED (under memory pressure: RAM peak 89%, this job 1.3 GB of 31.7 GB; re-check before treating it as a code
    verdict): ...`. Treat such a failure or timeout as a machine verdict until a re-run on a quieter machine agrees.
  - the job filled it itself (`pressure: false`, cause `job`): its own peak is at least half the RAM in use, so it
    is a code verdict (a leak, or a job too big for the machine):
    `FAILED (RAM peak 89%, mostly this job: 18.0 GB of 31.7 GB; a code verdict): ...`. The job's figure is its Job
    Object commit sampled together with the machine's RAM peak, so memory it had already freed doesn't count (for a
    run too short for any sample during it, its whole-run peak stands in). Commit is not resident RAM, so it is an
    estimate. Without the job's figure (POSIX, old records) the wording stays the machine one.
  - a pass gets a note only (`PASSED (note: RAM peak 88% during the run, this job 830 MB): ...`).

  A failure or timeout gets a note only when **every** failed run ran at 85% or more (the headline shows the lowest
  of their peaks), so a run that failed at 60% stays a plain code verdict. If any failed run filled RAM itself, the
  cause is `job`. Cancelled, stopped, error and stranded jobs never get a note. `status` marks such a row
  `[RAM 89%: re-check]` or `[RAM 89%, mostly this job]`. Set the threshold with `pressure_ram_pct` in
  `config.json` (a bad value means 85).
- **Then:** `id`, `title`, `owner`, `finished_at`, `exit_code`, `iterations_run`, `passes`, `run_s`, `wait_s`, `log`
  and `peak`.
- **Last:** the long details: timestamps, `events`, `tail` (the last output lines), `iterations` (each run: rc, wait
  and run seconds, outcome, the last lines when it failed) and `job` (the spec).

`peak` holds:
- `ram_mb` and `cpu_pct`: the job's own process tree (Windows Job Object). `ram_mb` is peak commit and also counts
  heavy.sh while it waits for a slot;
- `sys_ram_pct`, `gpu_pct`, `vram_mb`: the whole machine while the job ran (sampled every 2 s, not while it waited
  for its slot).

## Rules for the tracks

1. **Before a limit or the end of a session**, queue long non-AI work instead of starting it in the foreground.
2. **On resume, read `done\` first:** run `bash tools/wnc-queue status --owner <track>`. If it says `OK`, you're
   done reading. Otherwise run `result <id>` for each job it lists. Report the outcome, and don't babysit a running
   job (rule 17). Don't delete records or logs: the runner prunes them after 30 days.
3. Put your track name in `--owner`. Use `--class suite` for full or large suites. Pick `cpu` or `gpu` from a
   measurement of which is faster and correct for that work (COORDINATION rule 16), not by habit. Don't queue more
   than you need: the runner runs up to 4 jobs at once and heavy.sh still guards RAM.
4. Use `cancel` for your own jobs only. Use `stop` only when the machine must be quiet at once (it stops everyone's jobs).

## Safety limits (enforced by the runner)

- **Executables:** only `python`, `py`, `bash`, `sh`, `node`, `npm`, `gh`, `git`, `ffmpeg`, `ffprobe`, `reel`, `uv`.
  `python` means the system Python; for the engine runtime use `bash tools/test.sh` or the runtime's full path.
  No `cmd`, `powershell`, `curl`, `npx` or `claude` (also not as `@anthropic-ai/claude-code`). No `bash -c` shell
  strings (also not after option clusters such as `-eo pipefail`): run a script file. `npm` and `reel` are `.cmd` files on Windows, so cmd.exe re-reads their arguments:
  arguments with `" % ^ & | < > !` are refused for them. No other program may be a batch file, whether named by
  path or found on PATH. Programs are looked up on PATH only, never in the current folder (the runner's own bash,
  nvidia-smi and taskkill too). The allowlist guards against mistakes; it is not a sandbox against someone trying
  to get around it.
- **Command-line length:** the command line Windows builds (quoting doubles quotes and backslash runs) must fit
  32 766 characters, or 8191 for `npm` and `reel` (they run inside cmd.exe). A longer one is refused when it is
  queued, with the reason, instead of failing later as rc 127. Put long input in a file.
- **No recursive deletes** in a job's arguments: `rm` with any recursive flag (`-rf`, `-r -f`, `--recursive`, `-R`),
  `Remove-Item -Recurse`, `rmdir /s`, `rd /s`, `del /s` (also as `rd/s/q`), `robocopy /MIR`, `/MOV`, `/MOVE` or
  `/PURGE`. Words like `del` inside a path (`D:/x/del/s.py`) are fine. They follow junctions (COORDINATION rule 15). A job's own TEMP folder
  is removed afterwards without following links. If the job turned TEMP into a junction, only the link is removed.
  On Windows each folder is held open while it is emptied, so nothing can swap it for a junction mid-delete.
- **cwd:** must be inside the repo, `D:\ClaudeData` or `D:\Claude`. TEMP and TMP point to
  `D:\ClaudeData\Temp\wnc-queue\<id>`.
- **Env:** `--env` reaches only your command. heavy.sh always runs with the runner's own environment, so a job's PATH
  can't change how heavy.sh measures RAM or takes its slot. A job sees `JOB_QUEUE_ID=<id>`. No `WNC_*` variable
  reaches a job unless you pass it with `--env`: the product reserves that prefix, and its wrapper tests fail on any
  `WNC_*` name that reaches the engine.
- **Long heavy runs:** heavy.sh takes over any slot older than 3 hours. While a job runs, the runner refreshes its slot
  every 10 minutes, so runs longer than 3 hours keep their slot.
- **Kills:** a timeout, cancel or STOP kills only the job's own process tree (its Job Object), never another process.
- **Off limits:** any argument, env value or cwd under `WhyNot Clients` or the Adobe preference folders is refused.
- **Network:** URLs written in a job must point at the dev allowlist (GitHub, npm, PyPI, Hugging Face, the FFmpeg
  builds). This checks the job text only. What a program downloads by itself is not sandboxed, because the firewall
  is never changed.
- **Logs:** a job's log rotates to `.log.1` above 50 MB. Logs and records older than 30 days are pruned, and all logs
  together stay under 2 GB.
- **Settings:** `D:\ClaudeData\jobs\config.json` can override `max_parallel`, `heavy_sh`, `max_log_mb`,
  `retention_days`, `extra_executables` and `extra_hosts`.

## Install, check, remove

```bash
bash tools/wnc-queue install
```

```bash
bash tools/wnc-queue status
```

```bash
bash tools/wnc-queue uninstall
```

`install` registers the task with the Python that ran it (keep using the system Python, `C:\Python313`).

Tests (2 to 4 minutes, longer while other heavy jobs run): with the engine runtime, as part of the shared suite
(`whynot-cut/tests/test_wnc_queue.py` loads the tool's tests under the G79 sandbox):

```bash
bash tools/test.sh -p test_wnc_queue.py
```

or with the system Python alone (the tool is stdlib only):

```bash
python -B -W error::ResourceWarning -m unittest discover -s tools/wnc_queue/tests -v
```

The runner and the scheduled task use the system Python, not the engine runtime: the runtime's folder changes with
every `reel setup`, and FREEZE (COORDINATION rule 14) must be able to stop everything that runs it.

**Later (not built):** a macOS launchd agent (`~/Library/LaunchAgents`, `StartInterval` 600, `RunAtLoad`) running the
same `wnc-queue.py run`. On POSIX the runner already kills the job's whole process group, but a process that left
the group (setsid) and closed its output can outlive a job; peak RAM/CPU and the memory-pressure job figure are only
measured on Windows for now. Both need a Mac to build and test.
