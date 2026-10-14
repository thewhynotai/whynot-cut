# CI on macOS (G-T13)

WhyNot Cut's unit tests run on GitHub's Apple-silicon Mac runners (`macos-14`, arm64), in the private repo
`thewhynotai/whynot-cut`. The workflow is `.github/workflows/macos.yml`. Its helpers are in `tools/ci/`.
Windows tests still run locally (`tools/test.sh` / `tools/test.ps1`), as Addendum F says.
CI can't run Premiere or After Effects. The live-Mac end-to-end test (G11, G12 Phase 12) is still required before the beta.

## What runs when

| Trigger | Job | What it does | Wall time | Billed (x10) |
|---|---|---|---|---|
| Push to `release/3.0` or `mac/dev` (the agency Mac's branch, G12 Phase 12) (pushes that change only `PROGRESS.md`, `docs/superpowers/**`, `docs/design/**` or this file are skipped) | **smoke** | Builds the engine venv from the smoke slice of the lock and fetches the pinned ffmpeg. Runs `bash -n` on the shell scripts with bash 3.2 and `install.sh --dry-run` in a throwaway HOME. Then runs the unit subset below. | ~5 min (cap 12) | ~50–60 |
| Tag `v3.0.0-*` (phase tags `v3.0.0-pN`, release candidates `v3.0.0-rcN`) | **full** | Builds the engine venv from the whole runtime lock and fetches the pinned ffmpeg. Runs the same shell checks, then the whole suite, `bash tools/test.sh`. | ~20–25 min (cap 45) | ~200–250 (cap 450) |
| Actions → macOS → Run workflow (or `gh workflow run macos.yml --ref release/3.0 -f suite=smoke\|full`) | smoke or full | As above, on demand | as above | as above |

A newer push to the same ref cancels the older run. A tag's full run is never cancelled by its branch push, because they're different refs.
Every job has a `timeout-minutes` cap, so a hung run can't burn the month's budget.

To push without starting the smoke job, put `[skip ci]` in the head commit's message. Use it for doc-only batches, or when the budget is low.

### The smoke subset, and why each file is in it

`tools/ci/smoke.sh` holds the list. It runs one `bash tools/test.sh -p <file>` per entry and prints a timing table at the end.

| Test file | Why |
|---|---|
| `test_cli_consistency.py` | Engine CLI parsing: every `reel` command, alias, flag and exit code. |
| `test_structure.py` | Plugin structure: skill/agent frontmatter, references, and every `reel` flag a skill names actually exists. |
| `test_skill_text.py` | What the skill texts must and must not say. |
| `test_hooks_t34.py` | The hooks running under macOS bash/python: file filters, CwdChanged, the stop gate. |
| `test_guard_p2.py` | The guard: shell-command parsing and refusals. |
| `test_crossplatform.py` | macOS vs Windows: paths, CoreText Arabic shaping, preferences, onboarding. |
| `test_portability.py` | Arabic/space paths, the ffmpeg choice, macOS app and lock paths. |
| `test_wrappers.py` | The `bin/reel` bash wrapper with odd paths and plugin options, under bash 3.2. |
| `test_board.py` | `reel board` and the start/help/status texts. |
| `test_isolation.py` | The G79 sandbox itself: no test reaches the real engine home. |
| `test_installer.py -k TestBash -k TestShellScripts -k TestStaticChecks -k TestInstallDryRun -k TestEngineHomeInTheShells` | The installer's bash core on mac-arm64: `install.sh`/`bootstrap.sh` install, uninstall, engine home, countdown and dry run. The PowerShell classes skip off Windows anyway. |

Left out on purpose, because the full run covers them:
- the transcription, audio, media and motion files: they need faster-whisper/ctranslate2 or long renders;
- `test_errors.py`: slow, and `test_cli_consistency.py` already covers exit codes;
- serve, contract and the Adobe JS tests.

If the smoke step starts taking more than about 6 minutes, check the timing table and move the slowest file to the full run.

### How CI matches a real Mac

- **Python.** `actions/setup-python` 3.12 builds `$HOME/.whynot-cut/venv`, the venv `tools/test.sh` falls back to, from `whynot-cut/setup/locks/runtime-mac-arm64.lock`.
  - Install is `--require-hashes --only-binary :all:`, like the installer.
  - The smoke job installs only what its subset imports: PyYAML, Pillow, numpy, PyAV, fontTools, arabic-reshaper, python-bidi, uharfbuzz, freetype-py, imageio-ffmpeg and pyobjc CoreText/Quartz/Vision.
  - `tools/ci/lock_subset.py` cuts that slice from the lock, together with the slice's locked dependencies.
- **ffmpeg.** `tools/ci/fetch_ffmpeg.py` downloads the product's pinned build: `components.json` → `ffmpeg.assets.mac-arm64`, checked against the pinned size and sha256.
  - It goes into `~/.whynot-cut/ffmpeg/<version>/`, the same place the installer uses, and is cached between runs.
  - Homebrew is only a CI fallback, used if that download fails. The product never needs Homebrew.
- **bash.** `bash` is Apple's `/bin/bash` 3.2 for every step, so the installer and wrapper tests run on the shell a tester's Mac has.
- **Isolation.** Tests never touch a real engine home: every test module imports `tests/_isolation.py` first (the G79 sandbox). On CI, HOME is the runner's throwaway home.
- **Zero cost.**
  - The jobs use GitHub-hosted runners only, with no secrets and `permissions: contents: read`.
  - Third-party code is limited to `actions/checkout`, `actions/setup-python` and `actions/cache`, pinned by full commit SHA. The version tag is in a comment next to each pin.
  - To update an action, look up the new tag's SHA with `gh api repos/actions/<name>/git/ref/tags/<tag>` (read-only).

## Minutes budget

GitHub Free gives 2,000 Actions minutes a month. A macOS minute counts as **10**, and every job rounds up to whole minutes. So the month holds about 200 macOS minutes:

- one smoke run ≈ 50–60 weighted minutes;
- one full run ≈ 200–250 (capped at 450 by the timeouts);
- a typical month of 3–4 phase tags plus about 15 smoke pushes ≈ 1,700. That fits, with little to spare.

Pushes happen at phase closes, in batches, so the smoke job runs a few times a phase, not once per commit. The same goes for the agency Mac on `mac/dev`: push in batches, never after every commit, because every push there costs a smoke run too.

### Checking it: at every phase close

The executor runs this **before** pushing a phase batch or a tag:

```bash
bash tools/ci/minutes.sh            # read-only: only GET calls through gh api
```

It prints this month's macOS / Windows / Linux minutes, the weighted total, what's left, and roughly how many smoke and full runs that buys.

| Exit code | Meaning | What to do |
|---|---|---|
| 0 | Fine | Push. |
| 3 | Fewer than `WNC_CI_WARN_LEFT` (default 400) weighted minutes left | Push the batch (release/3.0 or mac/dev) with `[skip ci]`, don't push a tag until the 1st, run the suite locally, and note it in PROGRESS.md. |
| 2 | gh isn't installed or logged in, or GitHub didn't answer | Fix gh, then check again. |

Where the numbers come from:
- With the gh token's `user` scope, it reads the account's billing usage report. That figure is exact and covers every repository.
  - Today the token has `repo`/`workflow` but not `user`, so the script falls back to an estimate from this repository's own runs: each job's time, rounded up and weighted.
  - Yunus can add the scope once with `gh auth refresh -h github.com -s user`. The executor doesn't change the token.
- The authoritative page is github.com → Settings → Billing and plans.

## Reading results

```bash
gh run list --workflow macos.yml -L 5          # latest runs: status, trigger, branch/tag, duration
gh run watch <run-id>                          # follow a run live
gh run view <run-id> --log-failed              # only the failing step's log
```

- **Smoke.** The last lines of "Unit subset" are a per-file table (`<file>  <seconds>s  ok|FAILED (exit n)`) followed by `smoke: all passed` or the list of failures.
  - The log is folded per file, so open the failed file's group. Each file runs even after an earlier one fails.
  - "Shell checks" prints `ok` per script and the dry run's full output.
- **Full.** The last lines are unittest's `Ran N tests … OK` or `FAILED (failures=…, errors=…)`. Search the log for `FAIL:` / `ERROR:`.
- **Setup.**
  - "Engine venv …" ends by printing the interpreter `tools/test.sh` will use and the ffmpeg the engine picks (`source: pinned (engine home)` is the expected one).
  - A pip hash error there means the lock changed without being recompiled. The command is at the top of the lock.
- **A Mac-only failure** blocks the gate exactly like a Windows failure (G11). Fix it with a test, by the normal TDD + review rules. Before fixing, reproduce it with `bash tools/ci/smoke.sh tests` locally (it works in Git Bash too) or on the agency Mac.

## Files

- `.github/workflows/macos.yml`: the two jobs.
- `tools/ci/setup_engine.sh smoke|full`: the venv from the lock, plus the pinned ffmpeg (macOS runners only).
- `tools/ci/smoke.sh [shell|tests|all]`: the shell checks and the unit subset, with its reasons.
- `tools/ci/lock_subset.py`: a hash-pinned slice of a runtime lock, closed over its locked dependencies.
- `tools/ci/fetch_ffmpeg.py`: the pinned ffmpeg/ffprobe into an engine home, size- and sha256-checked.
- `tools/ci/minutes.sh`: Actions minutes used and left this month (read-only).
