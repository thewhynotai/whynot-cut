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

## Release identity gate (local, not CI)

`tools/release.py handoff` runs the keyed identity scan (Addendum H R-T6) once, as its last step before the new folder is swapped in. It scans the whole assembled `<out>.new`, so it covers exactly what ships:
- `Mac/repo`: the working tree, its full git history (every commit's author, committer, message and patch, `--all --reflog`, merges as `--cc`), every ref and tag name, tag messages, and the `.git` text files (objects and the index excepted);
- every generated file (README-AR.md, checksums.txt, START-HERE.md, the Mac guide, WHAT-WORKS-NOW-AR.md, LABEL.txt, sample-client/);
- the members (names and texts) of every `.zip` / `.ccx` / `.zxp`, nested ones too. The plugin zip holds the stage's shipped files, so they are covered there.

History text and archive members are written only to a temp folder outside the tree, and that folder is removed afterwards. A hit names the file, the commit (`Mac/repo@git:<sha12>:<path>` or `(message)`), the ref or the archive member (`<archive>!<member>`), never the token.

The scanner that runs is the release commit's own `tools/identity_scan.py`, with its own hash file and normaliser. A real release whose commit has none is refused; the log shows the copy and its sha256.

The scan is hard. A finding, an error, a timeout (30 min), a file it could not read while a key is in use, or a release without the key stops the hand-off. A PREVIEW without a key logs "skipped". The secret scan is report-only.

**Known limits.**
- **Binary files and files over 20 MB are scanned by name only.** Their count is logged as `name-only`. This covers the guide PDF, images, fonts and the sample client's clips.
  - The guide PDF is built from sources that are themselves in the scanned clone (working tree and history).
- **Unreachable objects are not scanned.** These are objects with no ref and no reflog entry. The hand-off's `git clone --no-local` copies only reachable objects, so its clone has none.

## Security watch

`.github/workflows/security-watch.yml` and its twin `.github/workflows/security-watch-paths.yml` are the cheap tripwire for R-T8. They open an issue assigned to `thewhynotai`, so GitHub emails the owner. Both run the same decision script, `tools/ci/security_watch.py`; the allowlist is `.github/security-allowlist.json` (pushers and commit emails).

**Why two files.** Several tracks push many times a day, so the main file must skip a normal push by the owner (see the cost below). A job-level `if:` can only read the push payload, and the Actions push payload has no `added`/`modified`/`removed` file lists (GitHub's docs say so; the lists exist only in the webhook payload). So `security-watch.yml` cannot tell that a push touched the watch itself. A `paths:` filter can. `security-watch-paths.yml` starts only for a push that changes `.github/**` or `tools/ci/security_watch.py`, and always reports those paths. GitHub ignores path filters on tag pushes, so the twin also runs on every tag push (rare); a tag push that touches none of the paths produces no finding. A push that is suspect and also touches those paths starts both files and may open two issues.

**What it watches**
- A push by a login outside the allowlist, or with a commit author or committer email outside it. A noreply address (`<id>+<login>@users.noreply.github.com`) counts only when that login is allowed.
- A force-push (history rewrite), or a deleted branch or tag, even from the owner.
- A push that changes anything under `.github/` or `tools/ci/security_watch.py`, even from the owner. You get an issue whenever the watch itself changes. That is rare, and it is intended.
- The repository being made public.

**A push cannot edit its own judge.** The job checks out the script and the allowlist from the commit before the push (`github.event.before`), or from `TRUSTED_BASE` (`release/3.0`, set in both files) for a new branch, a new tag or a non-push event. It never uses the pushed commit. Both files list the changed files with the compare API, because the Actions push payload has no added/modified/removed lists. In the main file that list is only defence in depth, for when its job runs anyway. If the list cannot be fetched, or GitHub cuts it at 300 files, the issue says the push could not be fully checked.

**What it costs in minutes.** It runs on `ubuntu-24.04`, which bills x1 against the free 2,000 a month the macOS jobs also use (x10).
- **Normal pushes cost nothing.** The main file's job-level `if:` skips a push when all four hold: the pusher is the allowed login, the push is not forced, it is not a deletion, and the head commit's author email is the allowed one. A skipped job bills nothing. That comes from a GitHub staff answer (https://github.com/orgs/community/discussions/26456), not from the billing docs. Confirm it once in Settings → Billing → Usage after the first few pushes.
- **A run costs about 1 minute** (cap 5): a suspect push, a `public` event or a manual run of the main file, and a push that touches `.github/` or the script (the twin). That is rare, so a few minutes a month, against the 300 to 600 pushes a month that are skipped.
- **The `if:` repeats the allowlisted login and email inline**, because it cannot read files. Change `.github/security-allowlist.json` and the `if:` together; a test fails when they differ.
- **Why only the head commit's author email gates the skip.** The pusher is the authenticated identity; commit authors and committers are free text anyone can write. So the `if:` gates on the pusher and the head commit's author, and the script (which checks every commit's author and committer) decides whenever the job runs. A multi-commit push by the owner with a foreign email under the head commit is skipped; the identity that made it is still the owner.

**What it does NOT cover**
- **A new collaborator.** `member` is not a workflow trigger, so Actions cannot see it.
- **A deploy key.** There is no workflow trigger for it, and `GITHUB_TOKEN` cannot list deploy keys. GitHub's own email on a new deploy key is documented only for organization owners (https://docs.github.com/en/subscriptions-and-notifications/how-tos/managing-organization-notifications). This repository is under a personal account, so no email is documented. Not covered: use the monthly check below. A push made WITH a deploy key is shown as pushed by the admin who verified the key (the owner), so with the owner's email it is skipped like a normal push: the monthly Deploy keys step is what protects against it.
- **A push with more than 300 changed files.** GitHub's `paths:` filter sees only the first 300 changed files. So an owner push of more than 300 files whose `.github/` (or `tools/ci/security_watch.py`) change comes after the first 300 starts neither workflow: the twin's filter misses it and the main file's `if:` skips an owner push. An outsider login still starts the main file. Step 6 of the monthly check covers it.
- **More than three tags at once.** Pushing or deleting more than three tags in one push creates no event.
- **`public` only runs from the default branch's copy of the workflow.** It alerts only once this file is on the default branch. The default branch is `main`, which holds no 3.0 files until release day, so a repo made public before then is NOT alerted (the monthly check covers it). For the same reason a new branch or tag is checked against `release/3.0` (`TRUSTED_BASE` in both files); switch it to the default branch when 3.0 lands on main.
- **A deleted branch or tag.** It is covered only if GitHub starts a push workflow for a deletion push. GitHub's docs don't say, so treat it as unverified. The `delete` event is not subscribed, so one deletion never opens two issues.
- **A push that edits the workflow file.** That push can switch the watch off from the same push. The pre-push checkout and the `.github/` finding flag it, but only if the edited workflow still runs.
- **A push that looks like the owner.** A stolen token pushing with the owner's email passes the allowlist. The push email and the local and Mac clones are the protection.
- Branch rules (no force-push, no deletion) are not available on a private Free repo; they go on with the public repo (Addendum I4).

**Monthly manual check** (about 5 minutes; this covers what the watch cannot see)
1. Repo Settings → Collaborators: only `thewhynotai` and people you know.
2. Repo Settings → Deploy keys: none you did not add.
3. Account Settings → SSH and GPG keys: only your own machines.
4. Settings → Developer settings → Personal access tokens: delete any you don't recognise or no longer use.
5. Settings → Security log: scan the month for logins, key or token events and repository changes you did not make.
6. In your clone: `git log --since="1 month ago" --stat -- .github tools/ci/security_watch.py` on `release/3.0` (and `main`): every change listed should be one you made.

**How to read an issue.** Open it from the email. The title says the event and ref. The body lists one line per finding (ref, short before..after SHAs, pusher, offending emails or paths, each in a code span) and links the run.
- If it was you, close the issue.
- If it was not, change your GitHub password, revoke tokens and SSH keys, and run the monthly check now.
- An issue titled "Security watch BROKE" means the watch could not check an event. Open the linked run to see why.

Check the script on a recorded payload without opening anything: `python tools/ci/security_watch.py --dry-run --event push --payload event.json --changed-files changed.txt`.
