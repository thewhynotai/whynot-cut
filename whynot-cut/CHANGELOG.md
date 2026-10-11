# Changelog

## 3.0.0 (unreleased)

### Added
- Positive client-folder marker (structure 4.1): `reel scaffold` and `reel client-init` write `.whynot-client`
  (`{"whynot_client": 1, "created": ...}`) at the client root; `reel doctor --fix` writes it for an existing client that
  lacks it (only at the client root, never in `assets/` or `data/`). New `lib/client_marker.py` (stdlib only) is shared
  by the engine, the guard and the SessionStart hook.
- `reel doctor` reports `guard_active` (a `guard-ok` heartbeat, touched by guard.py itself on every tool call it
  inspects, under `${CLAUDE_PLUGIN_DATA}` or `~/.claude/plugins/data/whynot-cut*/`, younger than 24 h; the runner's
  `hooks-ok` is shown as `runner_file`) with a fix ("install Git for Windows" on Windows), and
  `client_markers` (present / missing / written) for `--root`, the current client folder and every folder in
  `clients_root`.
- People, gender and honorifics (T1.7): profile.json gets `people[]` (`name`, `role`, `gender`: male | female |
  unknown, `honorific_ar`, `honorific_en`, `pronouns`); `_template` ships an empty list with a note, `example-clinic`
  a filled one. The client-researcher fills it only from the client's material and never infers gender from a name
  (`unknown` = ask the editor); the story-editor and publish-writer take every honorific from it. New `lib/people.py`
  (deterministic: tashkeel/tatweel stripped, alef forms, ة/ه, ى/ي unified, «ال» and و/ف/ب/ل/ك clitics, «د.»/«د/»
  treated as ungendered): `reel plan` (on-screen text) and `reel publish-check` (titles, description, chapters, tags,
  captions, Shorts, thumbnail text) give an **error** for الدكتور/الدكتورة, الأستاذ/الأستاذة, الشيخ/الشيخة or
  المهندس/المهندسة of the wrong gender before a person's name, a **warning** for a gendered honorific with a person
  whose gender is `unknown`, and a warning for a past-tense verb of the other gender (قال/قالت ...) next to the
  mention. A real run had written «الدكتورة» for a male client from his first name. Review round 1: a name word
  that is also a common word after folding («على» vs علي, «مني» vs منى) gives a warning, not an error; `/ : - « “ (`
  right after an honorific and invisible direction marks/ZWJ/ZWNJ don't hide the name; chained honorifics («الأستاذة
  الدكتور كريم») are each checked; `honorific_ar` that contradicts `gender` is reported; description link labels are
  checked; `reel plan` warns on a nameless «الدكتورة» when everyone in `people[]` is male (and the mirror case); the
  lead skills (start, new-client, edit, podcast) take «الدكتور/الدكتورة» and he/she only from `people[]`.
- One writer per client folder (T1.8): two Claude sessions had taken turns on one client folder and their work
  crossed. The first `reel` command of a session that writes into a client folder takes a **session lease**,
  `output/.whynot-lock` (`{session_id, pid, pid_created, host, started_at, updated_at, command}`, created with
  O_EXCL); each later writing command of the same session refreshes it (touch + `command`), and a long command touches
  it every 10 min. A writing command of another session gets `{"blocked", "how"}` and exit 2. The holder is the
  session's Claude Code process (`CLAUDE_PID`); at a plain terminal it is the command's own process, so the lock lasts
  for that command only. The lease is stale, and taken over with a line in `output/logs/pipeline.log`, when that
  process is gone on this computer (OpenProcess/GetProcessTimes on Windows, kill 0 + start time on macOS/Linux: a
  reused pid with another start time counts as gone) or after 2 h without a writing command. Otherwise it ends only by
  `reel lock --release` (the lead, on the editor's word) or the new SessionEnd hook (`hooks/session_end.py`, removes the
  ending session's own lease only). Same session = same id, re-entrant (the lead and its subagents share it):
  `WHYNOT_LOCK_SESSION` inherited from a parent reel, `CLAUDE_SESSION_ID`, `CLAUDE_CODE_SESSION_ID`, `CLAUDE_PID`,
  else the process id. Each command is classified in the command table (`CORE_WRITES` / `CORE_READS` / `WRITES_IF` in
  cli.py, `WRITES` / `READS` in podcast_cli and motion_cli; a test makes every new command choose): `next`, `status`,
  `inbox --no-refresh` (with a discovery), `doctor` without `--fix`, `settings` without `--init`, `ppro-status`,
  `ae-status`, `episode-next`, `music`, `lock` never take it. New `reel lock --status` / `reel lock --release`; the
  guard blocks `--release` and deleting/overwriting `output/.whynot-lock` for every subagent; the SessionStart context
  warns "another session is working in this client (<command>, since <time>)"; the edit, autopilot and podcast skills
  stop and tell the editor on a `blocked` from another session.

### Changed
- No real client ships in the product: the real client's profile folder was removed from `profiles/`. The plugin now
  ships only the blank `_template` and a fictional `example-clinic` ("Example Clinic / عيادة مثال", Dr. Sample Example,
  `domain: medical`, with every file kind: brand, medical glossary, notes, profile, style, transcription, graphics
  templates). Tests, evals and docs use `example-clinic`.
- A shipped profile is applied only when it is named: `--profile <id>` or the `id` in the client's own
  `output/client_database/reel-profile/profile.json`. The folder-name auto-match (`match.folder_contains`, in the engine
  and in the SessionStart hook) is removed, and the `match` key is gone from `_template/profile.json` and
  `config/defaults/profile.json`; an old profile that still carries it is ignored. A client folder with no profile of
  its own now shows "Profile: NONE" until `/whynot-cut:new-client` (or `reel client-init`) creates one.
- `package.py` refuses to build (exit 1, with a `how:` hint) when `whynot-cut/profiles/` contains any folder other than
  `_template` and `example-*`.
- A folder is a client folder only with a positive sign: a `.whynot-client` file, an `output/client_database/` folder,
  or lying under the configured `clients_root` (plugin option / `WHYNOT_CLIENTS_ROOT`, else the preferences file). Before,
  any folder with `assets/` and `data/` counted, so the guard blocked edits in Hugo sites and other repos with that
  layout, and the SessionStart hook called them client folders.
- `hooks/run_python.sh` (structure 4.2, 4.3; engine IM-17) tries the engine runtime first (`$WHYNOT_HOME` or
  `~/.whynot-cut`: `venv/Scripts/python.exe` / `venv/bin/python`), then the interpreter cached in
  `${CLAUDE_PLUGIN_DATA}/python`, then `python3` / `python` / `py` on PATH, skipping `*/WindowsApps/*` stubs and, on macOS,
  `/usr/bin/python3` without the Command Line Tools. It `exec`s the interpreter directly (no separate version probe: the
  hook scripts check `sys.version_info`) and touches `${CLAUDE_PLUGIN_DATA}/hooks-ok` on every run. Guard latency on the
  Windows dev PC: about 250-300 ms per tool call before, about 105 ms after.
- Role rules for WhyNot Cut's own agents match the full `whynot-cut:<name>` agent type (structure 4.7): another
  plugin's `qc-reviewer` is no longer restricted. Gate rules (approve-plan, reels-select, verify --record, settings
  --init, ae-probe --record, transcript-verify --by editor) still bind every subagent.
- Version hygiene (structure 1.1-1.4): plugin, marketplace (both fields) and the newest CHANGELOG heading are 3.0.0, and
  `tests/test_release_hygiene.py` fails if any of them drifts; the Premiere bridge keeps its own version (3.1.0 until the
  bridge changes) and the test checks its three places (`ppro_bridge.BRIDGE_VERSION`, CEP `CSXS/manifest.xml`
  `ExtensionBundleVersion`, `bridge.js` `VERSION`) agree. `test_motion.py` no longer hard-codes the release number.
- `reel --version` prints two lines: `WhyNot Cut <version>` and `plugin root: <folder>`.
- `reel --help` is generated from the command table (`CORE_COMMANDS` in `cli.py`, `HELP` in `lib/podcast_cli.py` and
  `lib/motion_cli.py`): every subcommand with its one line, replacing the stale list in the module docstring. A test
  fails when a command handler or registered subcommand is missing from the table.
- Skill listing budget (D11): Claude Code drops skill descriptions when the listing overflows, so `status`,
  `handoff` and others stopped auto-triggering. All 25 skill descriptions are rewritten: 8,804 -> 3,241 characters in
  total; a user-facing skill is at most 200 characters, key use first, with 2-3 English and 1-2 Arabic triggers
  (`status` «جاهز؟», `revise` «ملاحظات على الفيديو», `handoff` «سلّم الشغل»); the 10 craft skills are the one line
  "Reference for the <agent> agent (preloaded). Not for direct use." (no `disable-model-invocation`, so agents can still
  preload them). Trigger overlaps are resolved: `fix-audio` is the audio-only request, `revise` is two or more comments
  including a non-audio one, or any non-audio comment, `motion` is an animated video from a podcast window's audio
  ("animate this podcast part"), `adobe-extras` is After Effects / Photoshop output only on explicit request. The 19
  agent descriptions lose the sentence `See "When to invoke" in the agent body.`; the `plugin.json` description is 219
  characters. `TestListingBudget` guards all of it (total <= 4,000).
- Engine ready for a long-lived process (T2.17, engine MI-6/7/8): the engine home, bridge queues and script folders
  are resolved on every call (a `WHYNOT_HOME` set after import is honoured; `common.ENV_DIR`, `ppro_bridge.QUEUE` and
  friends remain for 3.0 as live aliases); an explicit `Context` (client root, profile layers, engine home, the
  request's caches) replaces the module-level context; installed-font caches follow the font folders.
  `compile_plan` is a chain of pure steps (`validate_decisions`, `build_camera`, `apply_framing`, `apply_timemap`,
  `build_audio`, `final_checks`) between one read and one write step, with byte-identical outputs. New
  `lib/media_util.py`: one time parser, one frame grab and one contact-sheet builder replace four, four and seven
  copies.

### Fixed
- Contact sheets lay out exactly the tiles they are given (G73): the previews sheet had six columns for three
  composites, half of it black. Sheets with fewer tiles than columns are now that many tiles wide.
- Resource leaks (MI-9): every preview probe left a 2-4 MB temp PNG and an open descriptor in `%TEMP%` (the frame now
  comes through a pipe); images, font files and the motion animatic's ffmpeg pipe are closed. `tools/test.sh` runs with
  `-W error::ResourceWarning` and the suite fails on any unclosed file, pipe or process.
- Executable bits are set in git's index (`100755`) for `bin/reel`, `hooks/run_python.sh`, `hooks/*.py`,
  `setup/setup_env.sh`, `setup/setup_env.py`, `examples/make_demo.py` and `tools/test.sh`. Windows checkouts had them as
  `100644`. Tests pin the index modes and the `package.py` zip exec set to the same list.
- Clip ids work for every file name (engine CR-1). `reel inbox` handed out `slug(stem)` while the per-clip commands
  matched the raw stem, so `Dr Sherif intro.mp4` (id `DR_SHERIF_INTRO`) was rejected, and Arabic names all collapsed to
  `VIDEO` and shared one project folder. New `lib/clip_ids.py`: ASCII names keep their slug (existing projects keep
  their ids); Arabic or letter-less names get `CLIP_<hash>` (the episode rule, now shared as `common.stable_id`); the
  same stem with another extension gets `_<EXT>` (`C0239.mov` -> `C0239_MOV`), other collisions a name or path hash.
  Ids are stored in `output/discovery/clip-ids.json` (`{id: relative path}`) and never change or get reused.
  `main_footage` accepts the id (any case), the raw stem or the 2.x slug; `inbox`, the single-clip `--video-id`
  auto-fill and the SessionStart "new clips" line use the same ids. A lone Arabic clip whose 2.x project is
  `output/projects/VIDEO` keeps that project.
- A raw stem (`--video-id "Dr Sherif intro"`), the 2.x slug or another case is rewritten to the clip's inbox id (one
  `note:` on stderr) unless a project folder with the given name already exists, so the work never lands in a folder
  `inbox` does not track. An id whose clip left `data/` is refused ("restore it or pass --footage") instead of
  resolving to a sibling with the same stem; a raw stem shared by two files is refused too. Relative paths compare
  case-insensitively (`C0239.MP4` renamed `C0239.mp4` keeps its id). The SessionStart hook picks raw clips with
  discovery's classifier, so it shows the ids `inbox` will hand out.
- The Gate 1 plan approval covers the whole plan (engine IM-3). `plan_fingerprint` hashed only the bytes after `"events"`
  in `01_analysis/timeline-spec.json`, so a camera move, the framing (9:16 / 4:5), the base scale, `main_footage` or the
  duration could change after approval and `ppro-build`, `ae-build`, `ps-build` and QC still saw the plan as approved.
  It now hashes every field of the spec except `generated` (sorted keys, 16 hex characters, as before), so a re-compile
  that changes nothing stays approved and anything that changes what gets built needs a new approval.
- Guard bypasses closed (structure 4.5; engine §10). Each is blocked when it targets a client's `assets/` or `data/`:
  a PowerShell pipeline whose earlier stage names a source path and whose later stage deletes, moves or writes the
  piped items (`Get-ChildItem data/Raw | Remove-Item`, `... | % { $_.Delete() }`); `xargs <mutator>`
  (`ls data/Raw/*.mp4 | xargs rm`); `$( ... )`, `<( ... )` and backtick bodies (`echo $(rm data/Raw/a.mp4)`), plus
  subshells and `then`/`do` bodies; `[IO.File]::` / `[System.IO.Directory]::` write, delete, move and copy calls;
  `git -C <source> checkout|reset|clean|rm|mv|restore`, `git checkout -- data/...` and whole-tree `git clean` /
  `reset --hard` in a client root; and commands run through `cmd /c`, `powershell|pwsh -Command|-EncodedCommand` and
  `bash|sh -c`, which now get the same checks, so `cmd /c reg add ...CSXS...` and
  `powershell -Command "Set-ItemProperty ...CSXS..."` no longer bypass the PlayerDebugMode rule.
- Guard review round 1: `cmd //c` (the Git Bash form) and cmd's own `&`, `&&`, `||`, `|` and `^`; PowerShell script
  blocks (`& { ... }`, `try { ... }`, `foreach (...) { ... }`, `if (...) { ... }`) and `$_` inside a block fed from a
  client source; the client folder itself and folders holding one (`rm -rf .`, `rm -rf *`, `rm -rf <client>` from its
  parent, `Remove-Item -Recurse`, `mv <client>`); globs matched against the folder (`rm -rf da*`); `$PWD`, `$(pwd)`,
  `$HOME`, `$env:USERPROFILE`, `~`; variables set from a source in the same command (`for f in data/Raw/*`,
  `f=data/...`, `$f = Get-ChildItem data`); `timeout`, `nice`, `nohup`, `env`, `time`, `eval`, `Invoke-Expression`;
  `(Get-Item ...).Delete()` and `[IO.File]::` outside pipelines; heredocs and here-strings fed to a shell
  (`bash <<'EOF'`, `bash <<< "..."`); `xargs` forms (`rm.exe`, `xargs.exe`, `xargs sh -c`, `-I{} cp /dev/null {}`);
  command names in any case (`RM`) and not-yet-existing paths in any case (`DATA/new`); `git stash` in a client root;
  `cd HKCU:\Software\Adobe; Set-ItemProperty CSXS.11 ...`; deleting or overwriting `<client>/.whynot-client`; role
  rules through wrappers (`timeout 600 reel ...`, `bash .../bin/reel ...`, `py -3 .../cli.py ...`). `git rm --cached`
  stays allowed. The SessionStart hook points to `reel doctor --fix` when it opens at the root of a folder that looks
  like an unmarked client (assets/, data/, output/ and START_HERE.md, output/projects/ or output/discovery/).
- Guard review round 2: `[IO.File]::` / `[IO.Directory]::` arguments are split bracket-aware and sub-expressions count
  again (`(Join-Path $PWD 'data/...')`, `(Resolve-Path ...)`, `[IO.Path]::Combine(...)`, `'a' + 'b'`; Copy checks only
  the destination, WriteAllText only the file); a loop or assigned variable counts only when it starts the path, so
  `ffmpeg -i "$f" "output/$(basename "$f").wav"` and `"output/${f##*/}.wav"` are allowed again. Also blocked now: cmd
  `if exist ... CMD`, `for %f in (...) do CMD`, `%CD%`, `cmd /cdel`; `foreach($f in ...)`; `rm -rf {assets,data}`;
  `Get-ChildItem | Remove-Item -Recurse` and `ls | xargs rm -rf` in a client folder; `Invoke-Expression -Command`,
  `"..." | iex`, `echo|printf "..." | bash|sh`, `'...' | powershell -Command -`, `iex $s` of a here-string;
  `export|declare|readonly D=data`, `a=(data assets)`, `$env:X = "data"`, `"da" + "ta"`; `[IO.FileInfo]::new(...)`;
  `cd -- data`; `bash -e .../bin/reel`; `winpty`, `flock`, `watch`, `parallel CMD ::: ARGS`; deleting
  `output/client_database` of a client that has no `.whynot-client` (it is that client's only marker). The guard's
  docstring lists what is still not inspected.
- Guard review round 3: a word starting with `$( ... )` keeps the taint of what it wraps when that is a path
  (`"$($_.FullName)"`, `"$($_.DirectoryName)/x.wav"`, `"$(dirname "$f")/x.wav"`, `"./$f"`), while `$($_.BaseName)`,
  `$(basename "$f")` and `${f##*/}` stay bare names; a Bash loop variable with a suffix (`"$f.wav"`, `"${f%.mp4}.wav"`)
  still writes next to the source and is blocked. A listing narrowed by a filter (`find -name`, `-Filter`, `-Include`,
  `-File`, `| grep`, `| Where-Object`) no longer counts as deleting the whole client folder, and filter values
  (`-Filter *data*`, `find -name 'assets*'`, grep patterns) are not read as paths. Joined .NET paths are judged as a
  whole (`(Join-Path 'output' 'data')` is fine; a base that is an unknown variable counts only when tainted). Also
  blocked: `rsync --remove-source-files <source>` and cmd `for /r <source> %f in (...) do ...`.
- Role holes (engine §10): subagents may not run `reel transcript-verify --by editor`; qc-reviewer may not run
  `ref-analyze` (it applies the client style, getting around the `ref-style --apply` block); setup-doctor may not run
  `reel setup`, `model-download`, `gpu-enable`, `ppro-install` or `doctor --fix`.
- The guard no longer fails silently (engine IM-17): with no Python at all, `run_python.sh` still exits 0 (fail-open)
  but the SessionStart hook gets "WhyNot Cut protection is OFF: no Python found — run reel doctor"; the SessionStart
  context starts with a loud warning when the `hooks-ok` heartbeat is missing or older than 24 h.
- Plugin options reach `reel` on every shell (T1.9). The SessionStart hook wrote `export WHYNOT_HOME="…"` with
  `json.dumps`, so an Arabic `engine_home`/`clients_root` became a literal `\u0639…` path in bash; it now uses shell
  quoting. PowerShell commands never receive a path-valued variable from `CLAUDE_ENV_FILE`, so the hook also writes
  `~/.whynot-cut/plugin-options.json` (`{clients_root, engine_home, updated}`, only from the installed plugin's hook and
  only when the options change). `plat.engine_home()`, `plat.clients_root_setting()`, the preferences lookup and both
  wrappers read it after the environment, then Claude Code's own record (`~/.claude/settings.json` →
  `pluginConfigs["whynot-cut@…"].options`), then the default and legacy homes; `bin/reel` and `reel.cmd` resolve the
  same order without starting Python. `~/.whynot-cut` counts as the engine home only when it holds a `venv/`, so the
  pointer file never hides a legacy engine (also in `hooks/run_python.sh`).
- `reel.cmd`: an engine home with `)` or `&` (`C:\Tools (x86)\…`) broke the script ("… was unexpected at this time")
  because `%HOME_DIR%` was unquoted inside a `( )` block; every path is now quoted and `%*` is expanded once, outside
  any block, with delayed expansion off, so `100% Natural`, `!`, `$`, `)` and Arabic reach the engine intact (with
  DelayedExpansion on, `!` used to be eaten). It also reads the legacy `.dr-nahla-editor` home like `bin/reel`. `reel
  setup` builds the engine once: `py -3` when the launcher exists (no second run with `python` after a failure), else
  the first `python` on PATH that is not a Windows Store stub; with neither it refuses with bin/reel's "no Python 3.9+
  found to build the engine" and the winget command (it used to say "engine not installed — run reel setup", a loop).
  Its "engine not installed" hint matches `bin/reel` (`run: reel setup`). Its own variables are `WNC_*` and are
  cleared before the engine starts. `tests/test_wrappers.py` runs both wrappers as subprocesses (`cmd /c`, Git Bash)
  against a real venv and a test-only argv echo in `cli.py` (`WHYNOT_TEST_ECHO_ARGV=1`).
- The option readers agree (plat, `bin/reel`, `reel.cmd`): a pointer without an `"engine_home"` string or its closing
  brace is ignored the same way (settings.json is used instead), and with two `whynot-cut@*` entries in settings.json
  all prefer `whynot-cut@thewhynot-ai`. `bin/reel` also reads a one-line pointer. The Premiere/After Effects bridge's
  fallback (no `bridge-config.json`) now also needs a `venv` inside `~/.whynot-cut` or a legacy home, so the folder the
  pointer creates is not taken for the engine. The pointer's temp file is removed when the final rename fails.
- One Python phrase in the docs, skills and agents: "Python 3.12 (installed by WhyNot Cut)" replaces "3.10–3.12" advice
  (the engine's own minimum-version checks are unchanged).
- Guard, Phase 1 review minors. A listing that is fed to a delete is narrowed only by a name/path/regex/newer predicate
  or a `-Filter`/`-Include` that matches none of the client's own files (`-name '*.tmp'` narrows; `-name '*.mp4'`,
  `-name '*'`, `-Filter *` do not), by a grep or Where-Object stage, or by `-File` without `-Recurse`; `-type`,
  `-maxdepth`/`-mindepth`, `-empty`, `-Directory`, `-Exclude`, `head`/`tail` no longer do, and a recursive listing
  (`find`, `gci -Recurse`) of the client folder counts as listing its sources. `find . -name '*.tmp' -delete` /
  `-exec rm {} +` follow the same rule as the `| xargs rm` form (allowed when narrowed). A .NET `Delete`/`Move` with an
  unknown `$base` and a multi-segment source literal (`Join-Path $root 'data/Raw/x.mp4'`) is blocked.
  `rsync --remove-sent-files` is treated like `--remove-source-files`. `-Filter`/`-Include`/`-Exclude` values are not
  paths on any cmdlet (`Remove-Item output -Filter *data* -Recurse` is allowed). The writer-lock rule applies the
  file-tool branch to Write/Edit/MultiEdit/NotebookEdit only (a subagent may Read the lock), ignores `2>`, `2>&1` and
  `>&` redirects that do not point at the lock, counts `sc ac mi ni ri py sh` only as a command's first word, and also
  blocks `find … -name .whynot-lock -delete` and globs that match the lock (`rm output/.whynot-l*`).
  Review fixes: in `find`, a predicate after `!`/`-not` (or inside `! ( … )`) or in a branch with `-prune` does not
  narrow, with `-o` every branch needs a narrowing predicate, and `-newer` alone does not narrow
  (`find . ! -name '*.tmp' -delete`, `find . -name '*.tmp' -o -type f -delete` are blocked). The comparison with the
  client's files stops at the first match and shares one budget of 100,000 entries per guard call; past it only a
  temp-style pattern (`*.tmp`, `*.temp`, `*.log`, `*.bak`, `__pycache__`, `*.pyc`, `.DS_Store`, `Thumbs.db`,
  `*.part`) still narrows. An unnarrowed listing of a client folder fed to a delete is blocked because it names
  `.whynot-client` (`find . -maxdepth 1 | xargs rm`).
- Guard: a comment no longer hides the rest of a multi-line command (Phase 1 gate C1). Bash comments are removed line
  by line (`#` only at a word start outside quotes, so `a#b` and `${#x}` stay words) before the command is split, so
  `rm -rf data` on the line after `# they're stale` is checked; PowerShell skips `# …` to the end of the line and `<# … #>`
  blocks, and reads `@'…'@` / `@"…"@` here-strings as one string, so an apostrophe in a comment or here-string no
  longer opens a quote that swallows the following lines. The role gates (approve-plan, qc-reviewer, AE/PS extras)
  are covered the same way. Round 2: each physical line loses its comment before a trailing `\` joins the next line
  (bash does not continue a comment, so `# see C:\temp\` followed by `rm -rf data` runs the rm); `$'…'` quoting is
  tracked; `<<EOF` inside quotes opens no heredoc. In `find`, `,` splits branches like `-o`, parentheses are parsed,
  and when the expression has an action only the branches with an action must be narrowed
  (`find . -path ./data -prune -o -name '*.tmp' -delete` is allowed). A deleting consumer of a listing of the client
  folder is blocked also with `-File` (`gci -File | Remove-Item` would delete `.whynot-client`) unless a name filter,
  a grep/Where-Object stage or an `-Exclude` matching the marker spares it; other root files (START_HERE.md) are not
  protected by this rule.
- The SessionStart warning checks the guard's own heartbeat (`guard-ok`), not the runner's `hooks-ok`, which
  `run_python.sh` touches right before the hook runs and so was always fresh (gate G1). It warns only when `guard-ok` is
  missing or older than the previous SessionStart (recorded in `last-session-start`): sessions ran but the guard did
  not. A first session (nothing recorded) and days without sessions give no warning.
- Phase 1 gate fixes (engine). `reel doctor` takes no writer lease (G2): its only write is the idempotent
  `.whynot-client` at a client root, so `doctor --fix --root X` works while another session holds X. `write_json`
  writes through a unique temp name per call and retries the replace (and `read_json` the open) for a few ms on a
  Windows PermissionError, so parallel subagents writing `clip-ids.json` no longer collide or read a half-replaced
  file (G3). Shipped tests no longer name a real field-test client (G4; `REAL_CLIENT_TOKENS` also checks tests/). A
  writing `reel` command on a 2.x client folder (assets/ + data/ + output/ with a WhyNot Cut sign: output/discovery,
  output/projects, output/client_database, output/logs/pipeline.log or START_HERE.md; no marker) writes
  `.whynot-client` and logs it, so old clients are protected from their first use under 3.0 (G5). `reel inbox` lists project folders that
  match no clip, reel or motion id as `orphan_projects` with an `orphan_hint` (G6).
- `reel doctor --fix` writes the `.whynot-client` marker only for `--root` or the current client folder (G70: it wrote
  the marker into every client under `clients_root`, real client folders included). `reel doctor --fix --all-clients`
  lists the unmarked clients and writes nothing; with `--yes` it marks them all. `reel doctor` lists unmarked clients
  under `fixes` with `reel doctor --fix --all-clients` (or `--fix --root "<folder>"` for the current one) as the hint.
- Engine, Phase 1 review minors. The approval fingerprint ignores timestamp keys of `source_range` (`set_at`,
  `selected_at`, any `*_at`), so re-running `reel range` with the same points and `reel plan` keeps the approval.
  `reel next` lists a stale approval as "PLAYBACK edit-plan.md to editor, then approve-plan (plan changed since
  approval — re-approve)", adding "(approval format changed in 3.0)" for a record written before 3.0, and the handoff
  no longer prints "approved by X" for it; new approvals carry `"format": 3`. The gender check also strips U+061C,
  U+2060, U+00AD and U+FEFF, reads one line break between an honorific and a name as a space, and gives one warning
  for a chain of nameless honorifics; motion-mode `reel next` shows the people[] notice too. `reel lock --status` adds
  `age_min`, `idle_min` (the 2 h clock) and a `how` line. A stale-lock takeover that has to put a newer lock back without
  hard links now uses an exclusive create, so it can never overwrite a lock created in the meantime.

### Migration
- The former `dr-nahla-hunter` shipped profile is kept as a private copy outside the product (not in the repo or the
  zip). A client folder that relied on the folder-name match must now have its own profile: copy that private profile
  into `<client>/output/client_database/reel-profile/`, or run `reel client-init --from-profile example-clinic` and fill
  it from the client's own documents. Existing client `reel-profile/` folders keep working unchanged.
- Existing plan approvals are invalidated once: the approval fingerprint has a new definition, so every project with a
  `plan-approval.json` written by 2.x is treated as changed. Re-approve the plan (`reel approve-plan --by editor`) before
  the next build or QC; the plan itself does not need recompiling.
- Clip ids are assigned once, the first time 3.0 runs `inbox` (or any per-clip command) for a client, in sorted
  relative-path order. A clip keeps its 2.x project folder when that folder is unambiguous: `output/projects/<slug>`
  (also `VIDEO` for a lone Arabic clip) or `output/projects/<raw file stem>`. For the same stem with two extensions the
  first in that order keeps the bare id (`C0239.MP4` before `C0239.mov`, so the `.mov` becomes `C0239_MOV`): if a 2.x
  project `C0239` was actually built from the `.mov`, edit `output/discovery/clip-ids.json` by hand before continuing.
  When both `output/projects/<slug>` and `output/projects/<raw file stem>` exist for one clip, the raw-stem folder wins
  (for ASCII and Arabic names alike); the other folder is left untouched, so move anything you still need from it.
- Existing client folders keep their protection when they have `output/client_database/` (every onboarded client) or
  lie under `clients_root`; they are recognised automatically. Any other existing client folder (only `assets/` and
  `data/`) is no longer protected until it gets the marker: run `reel doctor --fix --root "<client folder>"` (or
  `reel doctor --fix` inside it); `reel doctor` lists such folders under `client_markers.unprotected`. A folder that
  already has WhyNot Cut's `output/` gets the marker by itself on its first writing `reel` command.
- Existing client profiles have no `people[]`, so the gender/honorific checks in `reel plan` and `reel publish-check`
  are off for them until it is filled: `reel next` and `reel episode-next` show the notice "fill people[] in
  reel-profile/profile.json …". Add each person (name, role, gender, honorific_ar, honorific_en, pronouns) to
  `output/client_database/reel-profile/profile.json` from the client's own material; `unknown` until the editor
  confirms.
- Plugin options: nothing to do. The first session after updating writes `~/.whynot-cut/plugin-options.json`; until
  then `reel` falls back to `~/.claude/settings.json`. A Windows user who set `engine_home` and saw "engine not
  installed" (or got a second engine in `~/.whynot-cut`) in PowerShell gets the configured engine again; a stray
  second engine can be deleted by hand once `reel doctor` shows the right `engine_home`.
- Legacy engine homes `~/.reel-editor` (reel-editor 1.x) and `~/.dr-nahla-editor` (the original skill) are still found
  by both wrappers and the engine in 3.x, but **support for them is removed in 4.0**: move the engine to
  `~/.whynot-cut` (or set the `engine_home` plugin option to the old folder) before upgrading to 4.0.

## 2.2.1 — 2026-10-11 · Motion mode polish, client folders with Arabic names, field-test round 4
The minor findings of the 2.2.0 review, two bugs found by a live run from a client folder named in Arabic, and the gaps
G62–G69 found by the first real podcast run (installed 2.1.1, a 34-minute episode), each reproduced by a failing test
first.

**Fixed**
- Client folders with Arabic (any non-ASCII) names: `motion-plan`, and every HarfBuzz text measurement, opened the
  brand font through FreeType's file open, which cannot take a non-ANSI path on Windows ("cannot open resource"); font
  files are now read into memory. aerender (`motion-render`, `ae-probe`) on Windows reads its command line in the ANSI
  code page, so such a path arrived as "???": there the project is rendered from an ASCII temp copy and the file moved
  into place (a non-ASCII TEMP folder is reported as the problem; a render that cannot be moved into place is kept in
  the temp folder and named, never deleted). macOS renders in place as before.
- `motion-plan`: a typo in `transition_in`, `theme`, `captions` or `reveal` (in a scene or video-wide) is an error that
  names the scene and the allowed values, instead of a silent cut, dark theme, no captions or word reveal. A scene's
  own `captions` (`on` | `off`) overrides the video's (spec §3.4). A speech-source comparison `verdict` that is not
  said gives that one error, not also an editorial error and an editorial line.
- `motion-render`: a previous MOV/MP4 held open by a player (Windows) stops the render with "close the file" before
  aerender runs, instead of a raw PermissionError.
- `qc`: a render without an audio stream fails the render check by name (it used to fail later as "no audio to
  compare"). `audio_sync` keeps its 0.9 rule but explains a near miss, and when the plan has music or SFX it also
  compares the render with the planned mix: when that matches, the voice is in sync and the bed is the cause (lower
  `music.level_db`); when it does not, the voice or the bed level in After Effects differs from the plan; a planned
  file that is gone is named instead.
- `motion-build`: the `--script-only` / `--run-script` fallback refuses (an alert in After Effects) while the open
  project has unsaved changes, by the bridge's own rule (one shared `NHM.mayDiscard`). `--replace-edited` takes its
  backup only once the preconditions pass. Older `dialogue_motion_seq_*.wav` files that nothing names any more (not the
  plan, not the last build job, not any project `.aep` or backup) are removed; one After Effects still holds open is
  kept for a later run.
- After Effects library: the progress bar fills from the reading-start edge in LTR too (it grew from the centre). The
  bridge's JSON escaper regex is pure ASCII (it held a raw U+FFFF character).
- Handoff README: several missing brand fonts read as plural ("… are not installed: install them"). Guard: a shell
  write to an After Effects preference file gets the preferences message, not "the client's source folder".
- Code: removed the unused `motion_qc.plan_fonts` / `motion_qc.sha1`; the CEP bridge reads the host environment once.
- `motion-build --run-script` stops at once when After Effects has unsaved changes, naming the project (Windows: its
  window title ends with " *"; macOS: the script's own refusal, as osascript prints it), instead of waiting the whole
  `--timeout` for an .aep the script refused to build. A run that still times out says why the .aep may be missing,
  not only "no read-back". (The fallback script cannot write a marker file: After Effects' "Allow Scripts to Write
  Files" is off by default, and WhyNot Cut never changes it.)
- `audio_sync`'s near-miss note is a small function tested with fixed correlations; the ffmpeg-mixed test now checks
  only that the result agrees with the value it measured (a different ffmpeg build cannot break it).

**Verified live (Windows 11, After Effects 26.5x89)**
- From a copy of the test client in a folder named in Arabic (`whynot-test/بودكاست-تجربة`, reel EP02TEST_R02_MO):
  motion-plan, motion-build with the fallback font (read-back ok: 64 Arabic text layers through the ASCII-only
  escaper), motion-render through the ASCII stage (1080x1920, 24 fps, 32.3 s, −14.3 LUFS), 24 After Effects frames
  viewed (identical to the earlier run), `qc` 10/10, handoff READY_FOR_HUMAN_EDITOR. This closes 2.2.0's "project
  folder with an Arabic name" gap.
- `motion-build --run-script` with an unsaved change in the open project: After Effects' title read live ("… .aep *"),
  REFUSED within a second naming the project, nothing launched, the last build record untouched.

**Not verified live**
- The LTR progress bar (off in every recipe default; checked in node against a fake After Effects), the in-script
  refusal and its result through osascript (macOS); still from 2.2.0: a Premiere `ppro-build` on bundle 3.1.0, macOS,
  a build in the client's brand font.

### Field test round 4 (G62–G69)
- G62 role fonts: preview and caption stills, thumbnails, the animatic, motion plans and the After Effects /
  Photoshop / MOGRT font map take a role's font from typography.json `roles` (PostScript name, file, style or weight),
  then the reel-profile's brand.json `font_roles_fallback.weights`, then the nearest weight the family has. They no
  longer fall back to "the first file", which drew hook titles in Medium for a family without Black. One resolver:
  `lib/font_roles.py`.
- G68 highlight legibility: `publish-thumbnail` and preview stills measure a brand-coloured highlight against the frame
  behind it (WCAG contrast, motion.json thresholds: 3.0 at 64 px and larger, 4.5 below). Below the threshold the
  highlight is drawn in white/paper and the output warns: the field test's brown #81613D on a warm set measured 1.5:1.
  Readable brand colours are kept. New output keys: `highlights` (thumbnails) and `warnings` (previews). Not checked
  yet: unboxed caption stills and decorative bars.
- G63 `reels-select --adjust Rxx:in=|out=`: an explicit editor time snaps to the nearest word start or end (with the
  usual lead-in and tail). It never moves back onto a word the editor skipped. Automatic windows keep the
  sentence-start preference.
- G64 `reels-plan`: an evidence quote that no longer matches, for example after `transcript-correct`, ends with
  "did you mean: «…»". That is the current transcript at that time, ready to paste.
- G65 `episode-prep` scans the whole episode at 1 fps for name supers (lower thirds), including ones that start at a
  cut. It writes `_supers_sheet.jpg` and `_head_sheet.jpg` (every 10 s of the first 3 minutes), and `episode.json`
  gets `overlay_scan` and `lower_thirds_hint`. The intake inspector views every sheet before reporting none. Cost is
  about 1.9 s per minute of video (about 2 min for a 60-minute episode). Budget is 300 s
  (`WHYNOT_OVERLAY_SCAN_BUDGET_S`; 0 turns the scan off).
- G66 `reel` names itself (`WhyNot Cut <version>`) in its errors and in `reel --version`. `reel doctor` lists every
  `reel` on PATH and flags another plugin's (for example an old reel-editor) found first, with the fix: restart Claude
  Code, or call this plugin's `reel` by its full path.
- G67 docs: engine-side scripts run with the engine venv's python without `-I`. `-I`, `-s` and `-E -s` hide the user
  site-packages that a `--system-site-packages` venv uses on Windows; use `-E` alone for isolation.
- G69 `ppro-frames` detects Premiere's "Media pending" slate (media still loading right after a project opens) and
  re-exports those frames (`--pending-retries` 3, `--pending-wait` 5 s, doubling). Frames still pending are listed
  under `media_pending` with `ok: false` and are never shown as frames. QC docs: such a frame means re-export, never
  pass or fail.
- Verified live (Windows 11, Premiere 26.5.2, bridge 3.1.0): `ppro-frames` for the test reel EP02TEST_R02 exported 17
  of 17 frames with `media_pending: []` and no retries. All 17 frames were viewed: real shots, Arabic captions joined
  right to left. The slate path itself (media still loading) is proven by tests on a real slate captured in round 4,
  not by a live run. G65 was tuned on the real 34:41 episode: both real name supers came first. G66 was checked on
  this PC: it reports the old reel-editor 1.0.7 first on PATH in a session started before the install.

## 2.2.0 — 2026-10-11 · Motion mode and client-level reference style

### Motion mode
A window of a podcast episode's AUDIO becomes an animated motion-graphics video, built as a native After Effects
project by Claude through the WhyNot Cut Bridge, read back, rendered and QC'd from After Effects' own frames.

**New for users**
- `/whynot-cut:motion` (lead playbook). Gate 0 picks a reel candidate or a topic `--as motion`
  (`reels-select --pick R03 --as motion [--format 9x16|16x9]`, topics with `--type`); windows 15–180 s; projects
  `<EP>_<ID>_MO`. Audio-only episodes (`.mp3 .wav .m4a .aac .flac` in `data/Episodes/`) are accepted (motion only;
  their candidate previews are waveform cards).
- `motion-director` writes `motion-script.json`: the recipe's beats → 12 scene types (kinetic quote word-synced to the
  voice, title, stat counter, icon point, steps, comparison, timeline, quote card, context card, person card,
  licensed illustration, outro) plus background, captions, speaker badge, progress and voice pulse.
- `reel motion-plan` checks every on-screen word (the speaker's words in order, or editorial lines marked for Gate 1),
  numbers (as said, else the editor confirms), names (from the sheet), icons and licenses, recipe pacing; lays out text
  with HarfBuzz and WCAG colours; maps cues through pause removal without drift; writes `motion-plan.md`.
- `reel motion-animatic`: storyboard + MP4 with the mixed audio for Gate 1 (`approve-plan` approves the motion plan).
- After Effects: bridge 3.1.0 (one CEP bundle, Premiere + After Effects), `reel ae-status`, `reel ae-probe` (Arabic
  capability probe per AE version; the lead views frames and records the verdict), `reel motion-build` (preconditions,
  build, read-back of strings/fonts/composer/direction/boxes/cues, never overwrites unsaved or edited AE work;
  `--script-only`/`--run-script` without the bridge), `reel motion-render` (aerender master, MP4, cover, `--scenes`),
  `reel motion-frames` (frames with expectations), `qc`/`verify --record`/`next`/`handoff` for motion projects.
- Icons: Lucide (ISC, vendored 1.47.0) as native shape layers with draw-on; `reel motion-icons --search`. Licensed
  illustration packs with a license manifest: `reel motion-library`. CC-BY attributions are required in the captions.

**Verified live (Windows 11, After Effects 26.5x89)**
- The bridge loads in After Effects and Premiere (3.1.0); the probe renders joined Arabic, right-to-left order, the
  Universal composer and RTL direction persist, brand font via `fontObject`, icons draw.
- Found and fixed: libraries evaluated inside a function stayed local (`NHM is undefined`); a stale Trim Paths
  reference ("Object is invalid"); an expression selector "Based On: Words" maps `textIndex` inconsistently for RTL
  Arabic, so word reveals use one text layer per word (verified frame by frame).
- End to end on a test client (PODCAST-TEST, reel EP02TEST_R02_MO, 9 scenes, 32 s): Gate 0 `--as motion`,
  audio-clean with cut proof, motion-plan, animatic, motion-build (read-back ok), motion-render (1080x1920, 24 fps,
  −14.3 LUFS), 24 AE frames viewed, `qc` 10/10, handoff. Fixed on the way: transitions play after a scene's end;
  captions hide where speech is already on screen; per-role fonts take the nearest weight with its own PostScript
  name; the fallback-font build re-fits the layout (for the job only — the approved plan keeps the brand fonts);
  sequence dialogue is content-addressed (AE keeps imported audio open on Windows); 24-bit dialogue decodes through
  ffmpeg; hero frames follow every spoken word.
- Premiere 26.5.2 on bundle 3.1.0 (host PPRO): `ppro-frames` for the podcast reel EP02TEST_R02 exported Premiere's
  own 17 frames through the shared bridge (another open project untouched), QC ok.

**Not verified live**
- A Premiere `ppro-build` on bundle 3.1.0 (its code path is unchanged and its tests pass); macOS; a project folder
  with an Arabic name through ExtendScript `File()` (tested as a JSON round trip only); a build in the client's brand
  font (IBM Plex Sans Arabic was not installed — the live build used the Segoe UI Bold fallback).

**Engine**
- New: `cep_queue`, `ae_bridge`, `ae_probe`, `ae_render`, `motion_config`, `motion_icons`, `motion_library`,
  `motion_script`, `motion_timing`, `motion_layout`, `motion_plan`, `motion_audio`, `motion_animatic`,
  `motion_build`, `motion_readback`, `motion_render`, `motion_qc`, `motion_cli`; `templates/after_effects/
  nh_ae_bridge.jsx`, `nh_motion_lib.jsx`; `config/defaults/motion.json`; recipe `motion` blocks.
- `ppro_bridge` keeps its API (queue protocol moved to `cep_queue`). `reel ppro-install` / `reel setup` keep an
  installed bridge that is newer than the plugin's (reported as skipped); `ppro-install --force` replaces it.

### Client-level reference style
The reference edits in `data/` belong to the client, so their interpretation is now written once per client and
reused by every video, instead of being re-authored into each video's `01_analysis/`.

- `output/client_database/reference_style/`: `editing-style-analysis.md`, `editing-style.json`, `editing-rules.json`
  (client-researcher, once) + `reference-set.json` (`reel ref-style --record`: every reference file's path, size and
  modification time, and their fingerprint).
- `reel ref-style` shows missing | unrecorded | stale | current; `--apply --video-id <ID>` copies the current client
  style into `01_analysis/editing-style.json` + `editing-rules.json`, merged with the video's own
  `01_analysis/editing-style-overrides.json`. `ref-analyze --video-id` applies it automatically when current;
  `ref-analyze` without a video id measures for the client only (onboarding). A stale style is never copied.
- `reel next` lists "AUTHOR client reference style once …" for the first video, "ref-style --apply" for the next ones
  (no re-authoring), and "reference style stale — refresh client style + reel-profile style.json/notes.md (added /
  removed / edited: …)" when a reference changes. Videos authored before keep their own file (a notice, not a step).
  `reel discover`, `reel inbox`, `qc` (advisory) and the session start report the state too; `plan` points to
  `ref-style --apply` when the copy is missing. `--record` warns when the reel-profile `style.json`/`notes.md` or the
  style files were left unchanged after the references changed.
- Docs aligned with the engine (client-craft, editing-reference-analysis, edit, new-client, story-craft,
  client-researcher, story-editor): the docs no longer promise per-video `editing-style-analysis.md`/`editing-rules.json`
  that nothing checked.
- Discovery: a document in `data/` is an editing reference only when its path says so (`data/References/…`, "ref");
  other loose documents are `unclassified` with a warning (before, any notes file or `music.json` became a reference).
- Guard: qc-reviewer may read `reel ref-style` but not `--record`/`--apply`.

## 2.1.1 — 2026-10-11 · Podcast mode polish
The minor findings of the 2.1.0 review, each reproduced by a failing test first.

**Fixed**
- Arabic matching (`reels-plan` evidence, publish quotes, plan evidence, avoid topics) folds Arabic-Indic and Persian
  digits (٣ = ۳ = 3) and hamza seats (ئ → ي, ؤ → و: «دائما» = «دايما», «سؤال» = «سوال»), and treats the Egyptian ئو
  spelling as MSA ؤو («مسئول» = «مسؤول», «شئون» = «شؤون»).
- `publish-check` reads a bare multi-label domain whole (`example.co.uk`, `news.bbc.co.uk/x`): it was cut to
  `example.co`, which let a different site pass the "links only from the episode sheet" rule. Bare `youtu.be`,
  `linktr.ee`, `goo.gl`, `.dev`, `.info` links are now checked too; file names like `file.app.js` are not links.
- Straight double quotes "…" in publishing copy are emphasis, not a quotation: only «…» and “…” must be the speaker's
  words.
- `audio-clean` names each pause value's origin when only one of `--min-pause`/`--pad` is given
  (e.g. `command line (min_pause_ms), recipe drama (pad_ms)`).
- `publish-thumbnail --candidates` seeks to each sample instead of decoding the whole episode (a 90-minute episode
  takes seconds, not minutes).
- Thumbnail designs: `highlight` draws the named word(s) in the brand colour (a warning when they are not in the
  text); designs beyond 3 (`platform-limits.json` `thumbnail.designs_max`) are skipped with a warning instead of
  silently.
- The per-shot reframe and the 4:5 window are sized from the reel's own footage, not from the first file in
  preflight.json. When that footage is missing from preflight, a 4:5 (any non-9:16) framing is a `plan` error instead of
  a reel silently built as 9:16; a 9:16 reel gets a warning (per-shot framing skipped, picture fitted).
- Range reels without `global.main_footage` get the face-centred reframe and card handling (keyed on the source.json
  footage); caption bands over shown-whole cards are sized from the reel's own footage; a vertical clip with 4:5
  framing is windowed (fit scale as base) instead of silently built as 9:16.
- `episode-next` flags reels picked before the reels plan was re-validated until the editor confirms them again.
- `reel inbox` caches each Raw clip's probe by path, modification time and size (`output/discovery/raw-probe-cache.json`)
  instead of probing every clip on every call; a broken cache file is rebuilt.
- A reel whose episode file changed after selection is now also refused by `audio-clean`, `previews`, `preview-video`,
  `ppro-build`, `premiere`, `ae-build` and `ps-build` (before: only `preflight` and `plan`).
- `preview-video` reaps its ffmpeg decoders (no lingering process / ResourceWarning); the podcast tests close every
  file they open.

## 2.1.0 — 2026-10-11 · Podcast mode
A finished podcast episode becomes a reels plan, the editor picks, and each pick goes through the normal pipeline —
plus the episode's publishing package. One plugin: after Gate 0 a reel is an ordinary clip project.

**New for users**
- `/whynot-cut:podcast` (lead playbook) and `data/Episodes/` (+ optional `<name>.md` episode sheet: host, guest,
  links, sponsor, topics to avoid). `reel inbox` lists episodes and flags long 16:9 files left in `data/Raw`.
- `reel episodes`, `episode-prep` (probe, 6 intake frames, time estimate), `episode-transcribe` (whole episode in
  ~10-minute chunks with checkpoints; resumes after an interruption; VAD; language detected once), `episode-next`.
- Reels plan: the `episode-analyst` (fans out `moment-scout` per chunk) writes the topic map (= YouTube chapters),
  speaker turns with seating, and candidates with timecodes, content type, hook, score and risks. `reel reels-plan`
  validates them against the transcript (evidence near start/end, Arabic-normalised), snaps in/out to sentence
  boundaries, checks duration/overlap/avoid topics and writes `reels-plan.md`; `reels-preview` renders a quick 9:16
  preview of each candidate.
- **Gate 0**: `reel reels-select --pick … --by editor` (subagents blocked by the guard). Each pick becomes
  `output/projects/<EP>_<RID>/`, a window of the original episode file (shared `00_inputs/source.json` range format)
  with the sliced transcript, 16 kHz audio, speaker turns and its recipe. Unchanged picks are no-ops; moved windows need
  `--force`; `--resync` re-slices after episode corrections; a changed episode file is refused.
- **Per-shot 9:16 reframe** for episode reels: hard cuts plus face-presence runs (catches dissolves to cards), one face
  → framed on it, two-shots → follow the speaker (turns + seating, 1.5 s minimum hold), no face or unknown speaker →
  shown whole over the blurred fill; story camera moves compose on top. Verified on a real excerpt.
- **Content-type recipes** (`recipes.json`: storytelling, drama, success_story, advice, bold_opinion, emotional,
  comedy): pause thresholds applied by `audio-clean` (explicit > recipe > profile style.json > 250/80), graphics/zoom
  limits checked by `plan` (with `recipe_note` reasons in edit-plan.md), music mood, SFX palette, copy tone.
- Licensed music bed: `music.file` (data/Music only) on A06 at the recipe level with a fade-out, mixed into the preview;
  `reel music --list` with mood tags. `global.remove_pauses.protect` keeps chosen pauses.
- Templates `stat_card` (a number the speaker says) and `context_card` (one editorial line at the top).
- **Publish package**: `publish-writer` + `reel publish-check` (YouTube titles/description/chapters/tags/hashtags
  limits, Instagram/TikTok/Shorts limits from `platform-limits.json`, links only from the episode sheet, quotes only
  the speaker's words, episode SRT) and `reel publish-thumbnail` (face/sharpness-scored candidates, 1280×720 designs).
- QC: "Reel starts at its episode in-point", "Reel window inside the episode"; preflight flags variable frame rate.

**Fixed**
- HarfBuzz text used one FreeType face per font file and set its size only when created, so two sizes of one font in a
  still (a big value + a label, or a name card's name + lines for a one-weight client) rendered at the wrong size.

**Field test, round 3: reel R05 and the client's written reels plan, live in Premiere** (G46–G58)
- *GPU.* G54 `reel gpu-enable` takes cuBLAS 12 from NVIDIA's own redistributable (sha256 from NVIDIA's manifest, only
  the two DLLs kept in `<engine home>/cuda/bin`); pip stays the fallback. Measured: 2.4 MB/s vs 40 KB/s from PyPI.
  Whisper large-v3 on the RTX 4060 laptop: 9.7× real time (54 s of speech in 5.6 s); a reel's transcription went from
  1 min 50 s to 20 s.
- *The client's plan, followed.*
  - G46 Light Sharpen (+ optional grain) on the speaker clips when the 9:16 reframe upscales ≥ 150 %
    (`style.json reframe_sharpen`). Premiere 26's "Noise" is a grain effect whose Intensity defaults to 50; the bridge
    sets it. Read-back check `v1_sharpened`.
  - G47 **4:5 framing** (`global.framing: "4:5"`): the speaker in a 1080×1350 window over a blurred fill; story moves
    and jump-cut zooms stay inside it (FCP7 Crop, verified to import into Premiere); cards stay whole.
  - G48/G49 Burned captions can drop commas (`strip_punctuation`) and appear 0.2 s before the words (`lead_in_ms`),
    never over the previous line.
  - G51 The handoff names the export by the client's pattern (e.g. `EP02_R05_Traffic_Light_Shar_9x16_AR_v01.mp4`)
    with their codec, loudness and delivery folder (`style.json export`); "no music" clients aren't told to add music.
- *Transcription.*
  - G52 Per-video vocabulary `00_inputs/vocabulary.txt` (names of THIS reel, e.g. from the client's plan). The
    client-wide hint only reports misheard names at ≥ 0.8 similarity (it listed noise on every other reel).
  - G53 Known Whisper hallucinations («اشتركوا في القناة» at the out-point, no-speech 0.93) are dropped when they
    cannot be speech; the review lists them.
- *Who is on camera.* G55 A face is not enough: a cut to the host (similarity 0.65–0.67 vs the speaker's 0.87–0.93)
  counts as "another person on camera". It is shown whole over the blurred fill, and preflight warns that the words
  there may be theirs. On R05 the closing line was the host's; the reel now ends on the guest's last words.
- *Proof that no speech was cut.* G56 Protected pauses are not tested as cuts. G57 The check compares two
  deterministic Whisper readings (temperature 0) of the uncut and the cut audio, per chunk, instead of the corrected
  transcript. Coverage on a clean joke went from an "inconclusive" 0.82 to 1.0; on R02 0.90 → 0.945.
- *Speed.* G58 Reference edits are analysed once per client (cache), reused by every reel (5 s → 0.5 s).
- *Premiere with several reels open.*
  - G59 Captions over a card's bright blurred fill get the translucent box even for plain-caption clients; together
    with the podcast session's card bands, they now sit above the card instead of on its text.
  - G60 Building one reel made Premiere save another open reel's project, and that reel's next rebuild was refused as
    "editor changes". Premiere's auto-save does the same. Editor changes are now judged by a content signature (the
    project XML without Premiere's save stamp, ID counters and playhead, measured on an untouched re-save), not by
    the file time.
  - G61 `ppro-frames` looked for the sequence only in the active project; it now activates the reel's own project
    first.
- R05 (52 s, 9:16, punch-ins on the speeds, the joke's pauses kept, wide shot whole) and R02 rebuilt: QC ok,
  READY_FOR_HUMAN_EDITOR. 186 tests.

## 2.0.0 — 2026-10-11 · WhyNot Cut (renamed from reel-editor)
By The Why Not AI (info@thewhynot.ai). One plugin for macOS **and Windows**, from install to "drop your footage here".

**New for users**
- `/whynot-cut:start`: guided onboarding (engine, Premiere bridge, preferences, first client folder), each step verified.
- `/whynot-cut:autopilot`: edits every new clip in a client folder or across the clients folder, one combined approval.
- `/whynot-cut:preview` + `reel preview-video`: a watchable MP4 of the planned edit (pause cuts, zoom masks, every
  graphic/caption with its Premiere animation preset, cleaned dialogue, SFX), rendered by the engine without Premiere.
- `/whynot-cut:preferences` + `.claude/whynot-cut.local.md`: approval `ask|auto`, chat language (en/ar), Whisper model,
  preview on/off, clients folder. `/whynot-cut:help` cheat sheet.
- `reel doctor` (read-only readiness report with per-OS fixes), `reel scaffold` (ready-to-fill client folder with
  START_HERE.md in English and Arabic), `reel inbox` (every clip: new / in progress / done, missing brand material).
- Agents: `intake-inspector` (checks dropped material), `setup-doctor` (diagnoses machine/Premiere problems).
  All 14 agents now have "When to invoke" scenarios; all 21 skills have third-person trigger descriptions (incl. Arabic).

**Windows support (all verified by the test suite on Windows 11 + Python 3.13)**
- FCP7 XML `pathurl` is `file://localhost/C:/…` (1.x wrote `C%3A%5C…`, so Premiere on Windows could not link media).
- Arabic graphics shaped with HarfBuzz + FreeType from the client's font file (1.x fell back to arabic_reshaper, which
  breaks fonts with few presentation forms such as Thmanyah). Visually checked: joining, lam-alef, RTL base, LTR digits.
- Engine home and venv layout per OS, `reel.cmd` wrapper, cross-platform `setup/setup_env.py` installer with
  platform-marked requirements (pyobjc on macOS only; numpy/av ranges with Python 3.10–3.13 wheels).
- Premiere bridge installs into `%APPDATA%\Adobe\CEP\extensions`; PlayerDebugMode read from the registry (never written);
  `bridge-config.json` lets the panel find a custom engine home; the old `com.nh.bridge` panel is replaced.
- After Effects via `AfterFX.exe -r` and Photoshop via COM; aerender.exe; camera RAW via rawpy when installed (no crash).
- Briefs in `.docx`, `.rtf` and `.pdf` are read without macOS tools; fonts detected in Windows font folders by PostScript name.
- Face-aware photo crops with OpenCV when macOS Vision isn't available.
- CLI output is UTF-8 (Arabic JSON crashed on Windows code pages). Office lock files and desktop.ini are ignored.
- Guard hook covers the PowerShell tool (cmdlets, aliases, comma lists, redirection, -Destination/-OutFile) and Git Bash
  `/d/...` paths.

**Verified live on Windows 11 + Premiere Pro 26.5.2** (bridge 3.0.0): ping, native build with all 10 read-back checks
(ProRes 422 LT preview codec included), Premiere frame export, visual verification, QC pass, a forced rebuild with
backup, and a full revision cycle (text change → re-plan → approval gate → re-render → rebuild → frames). Fixed on the way:
- Frame export on Windows: Premiere's `exportFramePNG` accepts only backslash paths; a run where every frame failed had
  been reported as success (now `ok: false` with the per-frame errors).
- Premiere on Windows keeps imported stills locked until it quits: it now gets per-build copies of the stills, and
  unchanged stills are never rewritten, so revisions and rebuilds don't fail on locked files.
- A pipeline save-and-close before a rebuild no longer looks like an editor edit (`EDITOR_CHANGES_PRESENT`).
- Dialogue tracks are named "camera, not cleaned" when cleanup hasn't run; `reel next` asks for reference analysis
  only when the client has reference videos; `setup_env.py --system-site-packages` reuses installed packages.

**Field test on a real client clip** (Dr. Sherin Helmy, «وتزودوا بالتقوى» EP02 R02, a horizontal finished episode, religious
content, Windows). Every gap found was analysed and fixed in the plugin:
- G1 Horizontal (16:9) sources were fitted tiny into the vertical frame → **face-centred auto-reframe** (`global.base_scale_percent:
  "auto"`; preflight measures cover scale + face offset; Premiere XML and preview use it).
- G2 Whisper caches on the machine were 3 MB partial downloads, undetected → `reel doctor` reports complete vs partial models;
  `reel model-download` fetches/resumes deliberately. G2b Hugging Face "Xet" transfers died on Windows (WinError 10038) →
  the engine uses plain HTTPS downloads by default (`WHYNOT_HF_XET=1` re-enables Xet).
- G3 `Profile.jpg` was classified as a client brief → name hints are kind-aware (images get image roles; brand images
  get `brand_image`; licence files next to B-roll get `broll_license`).
- G4 Faces turned sideways weren't detected → OpenCV profile detector (both directions) as fallback (4/9 → 7/9 frames).
- G6 No HEX codes in any document (brand colours only in a poster) → `measured_palettes` from brand images, cited, for
  the client-researcher to assign; client-db reports roles honestly.
- G7 "Fonts not installed" was a mandatory QC failure although the build uses rendered stills → advisory unless live
  text is used (AE/PS extras, native caption track).
- G8 Graphic cards burned into a finished episode were cropped to 9:16 (text cut) → per-frame speaker/cutaway detection
  (face OR similarity to speaker frames; dissolves handled; measured 0.89–0.93 speaker vs 0.17–0.38 card) and cutaways
  shown whole. G10 Like the agency's editor: **the whole card over a blurred fill** (Premiere: cover copy on V1 +
  Gaussian Blur added by the bridge, card on its own track; preview the same).
- G9 Generic texts said "her words"/"she" (first client) → neutral "the speaker".
- G11 **Licensed stock B-roll videos** (`data/Broll` + SOURCES/licence): new `broll_video` template, video-only XML clips
  (B-roll audio can never reach the dialogue), preview playback, QC coverage, licence warning.
- G12 Generic docs said "Thmanyah only" → the client's brand fonts. G13 **Religious content review** (Quran wording from
  the Mushaf between ﴿ ﴾, hadith/story attribution, no fatwa on screen): the content reviewer follows the profile
  `domain` (medical | religious | general). G14 Template colours were hard-wired (primary box + white text) →
  `box_role`/`text_role` per template (e.g. a cream hook box with dark text). G15 one still-folder mapping
  (`still_category`) instead of five copies that had drifted apart. G16 a second audio stream (AAC + AC3) is reported.

**Field test, round 2: reel R02 cut from the full 29.97 fps episode, through a live Premiere build** (G17–G45)
- *Transcription.*
  - G17 Whisper crashed with newer PyAV (`metadata_errors`): the engine decodes the audio itself.
  - G18 An NVIDIA GPU silently fell back to the CPU (missing `cublas64_12.dll`). The doctor now names the GPU and the
    missing library, and `reel gpu-enable` installs it with the editor's OK. The GPU is skipped up front instead of
    failing after loading 3 GB.
  - G19 Glossary hits use Arabic normalisation (آمنوا = امنوا) and phrases. Short terms keep their hamza, so the
    verse word «آية» no longer matches Egyptian «ايه».
  - G20 The review lists profile names that Whisper wrote differently (نادال → «نضال», ديوكوفيتش → «جيكوفيتش», at
    high confidence).
  - G21 "Uncertain words never on a graphic" is enforced: corrections carry `flags`, `reel plan` refuses them on
    graphics, QC lists them, and a verification goes stale when the transcript changes. `reel transcript-relisten`
    re-decodes flagged words three ways («حضار المدر» → «هغير المضرب», 2 of 3).
  - G28 Quotes in the client's documents (a reels plan) are matched against the transcript.
  - G35 The editor's finished reel is a human transcript too: its captions settled «إيمانهم».
  - G37 Corrections re-anchor by word text after a re-transcription renumbers the words.
- *Audio.*
  - G24 The cut check passed a 36 s stretch that came back as one word. It now decodes ≤ 20 s chunks split at the
    cuts, counts collapsed stretches as missing, and needs ≥ 85 % of the words matched.
  - G25–G27 audio-clean measures the source first: dual-mono → one channel; hum notches only on mains harmonics
    (50/60 Hz) that stand out in the pauses; no spectral denoise on an already-clean master (55 dB S/N).
  - G38 Pause settings come from the client's style.
- *Reels from long files.*
  - G30 A reel is a range of a longer raw file: `reel range --in --out --snap`, `00_inputs/source.json`. Transcript,
    audio, preflight, previews, preview video and QC all work on the reel's clock, and Premiere links into the
    original with handles. Podcast mode reuses it.
  - G31 `--video-id` silently processed the FIRST raw clip of a folder; it now picks its own clip, or refuses.
  - G36 A range snaps to the nearest pause (the reel started mid-word).
- *Frame rate.*
  - G32 The sequence frame rate follows the client (`sequence-settings.json`, NTSC aware) instead of a fixed 24 fps,
    which juddered on this 29.97 fps client.
  - G33 FCP7 XML wrote invalid fractional timebases for 29.97 media; it now writes timebase 30 + NTSC, with exact
    ticks.
  - Premiere built R02 at 29.97 fps, and all read-back checks passed.
- *Edit and graphics.*
  - G29 `global.cut_words` cuts fillers (the plan's repeated «يعني») from picture, sound and captions.
  - G39 edit-plan.md reads on the reel's timeline: real camera moves, auto zooms apart, coverage including cutaways.
  - G40 Preview backgrounds used timeline time as source time after pause removal.
  - G41 Captions can sit on a translucent box, as in the editor's reel.
  - G42 Captions jumped off-screen to dodge cards placed at the top; they now move only on overlap.
- *QC and handoff.*
  - G34 Re-running preflight no longer moves a clip's status back.
  - G43 Premiere frames include the cutaways and camera moves.
  - G44 QC failed every bridge build (it looked for the fallback XML's manifest).
  - G45 Handoff texts said 24 fps.
  - QC dialogue sync is range-aware.
- R02 ends READY_FOR_HUMAN_EDITOR: QC ok, cutaway blur confirmed in Premiere's frames.

**Pipeline**
- Whisper uses an NVIDIA GPU automatically (float16) and retries on CPU if the CUDA libraries fail at first inference.
- Default caption hiding now covers every text graphic (hook, statement, term, checklist) unless the profile says
  otherwise; the preview showed captions repeating the hook and crossing a checklist under the old default.
- `reel next` includes the preview video step and its staleness. `inbox`/session hook treat a clip as started only
  once it has a transcript (preflight alone no longer marks it "in progress").
- Pillow 13 compatibility (no `mode` argument to `Image.fromarray`).
- Hardening from the plugin-validator and skill-reviewer passes: every agent/skill frontmatter is strict YAML; hooks
  never write `__pycache__` into the plugin; plugin options reach `reel` through `CLAUDE_ENV_FILE`; the guard blocks
  any write to Adobe's CSXS preferences and subagents changing preferences; `reel settings --set` rejects unknown keys
  and invalid values; `clients_root` from the preferences file makes `--root "<name>"` work anywhere; fan-out agents fall
  back to sequential checks when nested subagents aren't available; preferences and approvals are resolved per client.
- Tests: 72 (new `test_crossplatform.py`: paths, HarfBuzz shaping/RTL, PowerShell guard, preferences, onboarding,
  document readers, animation presets; the full chain now renders and probes the preview MP4).

## 1.0.7 — 2026-10-11 (Windows test fixes)
- Windows: the test suite passes (48 tests). Discovery stores paths with `/` on every OS (on Windows `data/`
  documents were not seen as editing references); the QC composite closes its temporary PNG before deleting it;
  the AE/PS syntax tests use Node.js when `osascript` is missing; tests read files as UTF-8.

## 1.0.6 — 2026-10-11 (plugin-validator warnings, thewhynot.ai ownership, portable hooks)
- Guard hook: destinations that are not the last argument are checked — `cp/ln/install -t DIR`, ffmpeg outputs
  followed by options (`ffmpeg -i x data/out.mp4 -loglevel error`), `-progress`/`-passlogfile` files — and
  `find` with `-delete`, `-exec rm|mv|…` or `-fprint*` on a client's sources (or from the client folder itself).
- Hooks run through `hooks/run_python.sh`, which picks the first real Python 3.8+ (skips the Windows Store stub).
- `clients_root` setting is used: `--root` takes a bare client folder name, the "--root required" error lists the
  clients there, and a session opened in that folder is told which client folders it holds.
- Premiere bridge: a job whose script is missing gets an error result instead of hanging until the caller times
  out; a lost `evalScript` reply releases the queue after 20 min (a late reply is ignored).
- Helper agents get the colour of the agent that starts them (claim-checker red, frame-inspector pink,
  graphic-checker orange, segment-proofreader blue). Author is thewhynot.ai (http://thewhynot.ai/). Proprietary `LICENSE` file added.

## 1.0.5 — 2026-10-10 (fixes from the independent QC re-test, applied to C0238)
- Jump cuts: every cut after a removed pause changes the zoom, also inside a punch-in that spans the cut (steps one
  mask increment in, or out above 1.2). QC check "Every jump cut changes the zoom". C0238 had 3 unmasked cuts.
- Photo crops centre on the detected face (macOS Vision, `pyobjc-framework-Vision`); `crop_center` overrides.
  C0238 GFX_006 had cut through the eyes.
- Hook titles: `bar_style` `underline` | `box`; the Nahla profile uses `box` (white text on full teal boxes).
- QC check: every overlay still inside the safe area (C0238 name card crossed the bottom UI zone; moved up).
- Captions lift above a card (name card / glass / CTA) instead of overlapping it.
- `captions_hidden_ranges` (source time) are remapped to the sequence clock on the native caption track and the AE
  extra too (the animated-caption path already did); both read the sequence-clock captions.
- `reel next` reports STALE steps (inputs changed after a step ran) instead of "done".
- QC no longer warns about missing AE renders / .aep / PSDs unless the AE/PS extra was used.
- Profile notes: delivered-audio numbers corrected (22.8 dB, not the 23.7 dB denoise-only stage).

## 1.0.4 — 2026-10-10
- Arabic lines always get a right-to-left base direction (CoreText and fallback renderer). A line starting with a Latin word
  ("evidence إنها ممكن تساعد", C0238 GFX_003) was laid out left-to-right with the first word on the wrong side.

## 1.0.3 — 2026-10-10 (fixes from the live end-to-end test)
- Audio: removed compressor + dynamic loudnorm (they gave back most of the denoise gain: 23.7 → 16.5 dB S/N); now gain + true-peak limiter (C0238: 16.6 → 22.8 dB on the delivered file, −14.6 LUFS). `--nr`, `--expander` options.
- QC judges speech-to-noise on the DELIVERED file (was an intermediate stage).
- Cut verification maps every difference to source time: "missing" only when a removed pause touches the words; lists cut points to listen to.
- Editor's own saves in Premiere no longer invalidate visual verification; `ppro-build` refuses to rebuild over them without `--replace-edited`; QC reports them.
- Guard hook follows `cd` in a command chain, treats each line as a command, ignores heredoc bodies.
- `transcribe --force` refreshes the machine originals used by corrections.
- `ppro-frames` probe times stay inside the sequence. Music cue points follow the pause-removal remap.
- Agents that fan out sub-agents wait for every result before reporting.

## 1.0.2 — 2026-10-10
- `ppro-frames` writes each run to a fresh `premiere_frames/run-<time>/` folder with a labelled `_sheet.jpg` (stale frames from an earlier build had sat next to new ones).
- Verified live: bridge 2.0 ping from the installed plugin; C0238 test build PRPROJ_BUILT 10/10 checks, 47 graphics, 13/13 frames.

## 1.0.1 — 2026-10-10
- `reel` accepts `--root/--video-id/--profile` after the command too (as the skills write them).
- Wrapper never writes `__pycache__` into the plugin folder. README, eval cases (6).

## 1.0.0 — 2026-10-10
First plugin release. Ported from the `dr-nahla-hunter-editor` skill (v2).
- Generic engine with client profiles; Dr. Nahla Hunter is the first profile (output for C0238 is byte-identical to v2).
- 16 skills (lead-editor `edit`, `revise`, `status`, `fix-audio`, `new-client`, `setup`, `handoff`, `adobe-extras` + 8 craft skills).
- 12 agents: 8 stage specialists + 4 parallel sub-agents (segment-proofreader, frame-inspector, graphic-checker, claim-checker).
- Hooks: client `assets/` and `data/` read-only; AE/PS opt-in (`--extras`); subagents can't approve plans or record verdicts; client-folder session context.
- Premiere bridge 2.0: whitelists the stable `~/.reel-editor/ppro-scripts` folder (plugin path changes on update).
- `reel` CLI on PATH, `reel setup`, `reel profile`, `reel client-init`; pinned `setup/requirements.txt`.
