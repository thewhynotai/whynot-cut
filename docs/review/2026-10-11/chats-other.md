# WhyNot Cut: what the other chats say (extraction for the master enhancement plan)

Scope: 9 session digests (all except the current session db6fbee3 and the big sessions 3e1731a4, 9301b09f, e15d7086,
2d167d3a, which belong to other reviewers). Times are UTC. For 3 sessions the digest only kept end-of-turn text, so I
also read the raw transcripts (read-only) to get missing details. These are marked **[raw]**:
- 35f79f46: the AskUserQuestion answers, tool errors and the handover steps
- 0bba621d: the brief, the fresh-review findings, the live evidence and the state after the digest ends
- cc327f47: the assistant's full Stage-5 analysis

Two facts come from a sibling digest or the shared side-notes, marked **[x-ref]**:
- the 2.2.1 item list, quoted from e15d7086
- the 2.2.1 hand-over table, `side-session-notes/local_982c28e5…/motion-2.2.1-minors.md`

Lineage in one line: the user's uploaded **Reel Editor 1.0.5** (by DOMA Studio, Mac-only) was:
1. re-owned to thewhynot.ai and moved to 1.0.6 / 1.0.7 on 2026-10-10 (c2d3338a, 976c8a16);
2. requested to be rebuilt under a "why not" name (41ea4e3c, interrupted; the rebuild became **WhyNot Cut 2.x** in
   another session);
3. then 2.1.1 (podcast minors, bfe3f99b), client-level reference style (cc327f47 → 3aaabb4f, folded into 2.2.0), the
   first real onboarding (35f79f46) and 2.2.1 (motion minors + Arabic-path bugs, 0bba621d, still running).

---

## Session c2d3338a: "Plugin installation" (Reel Editor 1.0.5 → 1.0.7)
**When:** 2026-10-10 21:02 → 21:46.
**Purpose:** install the user's Reel Editor plugin (`1.0.5.zip`) and helper tooling on this Windows PC; rebrand it to
thewhynot.ai; make it pass validation and tests on Windows.

### 1. User requirements & wishes
- "install this plugin in this folder" (the Editing Plugin folder).
- "fix the hooks to use C:\Python313\python".
- Install the skill-finder skill (from ckorhonen/claude-skills).
- `/skill-finder now find a skill to enhace and test plugins to achive the goals`. The user wants tooling to
  **enhance and test** the plugin.
- "install Anthropic's official plugin-dev", then "test that … plugin-dev is installed and working".
- "remove the doma-studio registration and folder and change the plugin owner from DOMA Studio … to be
  http://thewhynot.ai/". Branding wish: the owner is The Why Not AI. The user explicitly kept **http** (a later
  session's switch to https was reverted).
- "update the README too"; "update the zip with these changes too"; "rename the marketplace in marketplace.json to
  thewhynot-ai".
- "remove the duplicate reel-editor install"; "delete the .bak backups"; "archive the smoke-test session".
- "review the changes and update the zip"; "bump the version to 1.0.6"; "re-upload 1.0.6.zip to the desktop app".
- "install jq"; "install PIL so the remaining tests pass".
- «عدّل الاختبارات عشان تعدّي على ويندوز» ("fix the tests so they pass on Windows"). Windows parity matters to the
  user.
- «حدّث البلجن في تطبيق الديسكتوب» ("update the plugin in the desktop app").
- "anything eles, tell me", then "do the best and /reload-plugins". This is the start of the decide-and-continue
  preference: let Claude pick the best option.

### 2. Complaints / friction
- **The plugin was Mac-only.** Setup installs Mac-only Python packages and looks for Adobe apps in /Applications, so
  `/reel-editor:setup`, transcription and Premiere builds would fail on Windows.
- **`python3` on Windows is the Microsoft Store alias.** The hooks errored on every tool call, and the read-only guard
  for client `assets/`/`data/` silently did not work.
- **The `claude` CLI is not on PATH** in the agent's shell. Plugins had to be registered through `.claude/settings.json`.
  Later the desktop app's bundled CLI was found and used (`claude plugin validate/update/marketplace …`).
- A headless `claude` session isn't logged in (see a6fcc96f: "Not logged in · Please run /login"), so a CLI smoke
  test can't be automated.
- New plugins and changes load only in a new session. `/reload-plugins` must be typed by the user; Claude can't run
  built-in commands.
- **Edits made in the installed cache are lost on reinstall or re-upload.** Every change had to be re-packed into the
  zip.
- **The same version number hides updates.** Changes went in under 1.0.6 after it was installed, so other machines
  wouldn't see them. Hence 1.0.7.
- Duplicate installs were confusing: a user-level desktop-app upload plus a project-level `doma-studio` registration.
- The assistant contradicted itself: it said `doma-studio` was "never added", which was wrong; it had been registered
  globally. It cleaned this up later.
- jq on PATH works only in new terminals. plugin-dev's `hook-linter.sh` gives a false "Unknown event type: PreToolUse"
  because of Windows jq CRLF output. `validate-hook-schema.sh` only understands the settings.json layout, not a
  plugin's `hooks.json`.
- A side session (976c8a16) went beyond its read-only brief and edited the installed plugin; the main session had to
  review that after the fact.

### 3. Decisions (and why)
- **Hooks use a launcher, `hooks/run_python.sh`.** It tries `python3` → `python` → `py` and takes the first real
  Python ≥3.8, so the same hooks work on Mac and Windows. If no Python exists, the hooks **pass (fail-open)** with a
  message instead of erroring.
- **Owner:** `"author": {"name": "thewhynot.ai", "email": "media@thewhynot.ai", "url": "http://thewhynot.ai/"}`.
  The README got the line "By thewhynot.ai", and the marketplace name `doma-studio` became `thewhynot-ai` in the
  commands.
- **"DOMA 2.5 SS" (drive) and `~/Developer/doma-studio` (source repo) were left in the README** because they are real
  Mac locations.
- **The `LICENSE` file a side session added was kept:** "all rights reserved", contact media@thewhynot.ai, matching
  `UNLICENSED`. The user was asked to read the legal text.
- **Version bumped to 1.0.6, then 1.0.7.** Reason: a new number is needed so installs see the update. Old zips were
  deleted, so the folder holds `.claude/` plus one zip.
- **skill-finder edited to ask before installing or creating skills.** Reason: the community-install risk.
- **Two engine bugs found while fixing the Windows tests were fixed in engine code, not hidden in tests:**
  - `discover.py` wrote backslash paths, so `data/` docs weren't recognised as references.
  - `previews.py` left a temp image open, so Windows couldn't delete it.
- **Tests:** they now read files as UTF-8 explicitly. The AE/PS tests fall back from `osascript` to Node.js.

### 4. Verified working (evidence)
- The guard hook on Windows: deleting in `assets/` is blocked, writing into `data/` is blocked, writing into
  `output/` is allowed. Checked with sample inputs and a throwaway client folder.
- plugin-dev loads: 7 skills, 3 agents (`agent-creator`, `plugin-validator`, `skill-reviewer`) and
  `/plugin-dev:create-plugin`. Confirmed in a fresh session (976c8a16, "RESULT: PASS").
- `claude plugin validate` passes on 1.0.6 and 1.0.7. `claude plugin update` reported 1.0.5→1.0.6→1.0.7. The installed
  copy matches the zip file for file (119 files).
- jq 1.8.2 is installed (winget `jqlang.jq`). `validate-hook-schema.sh` passes on the hooks content.
- **The full test suite passes on Windows: 48 ran, 0 failed**, under both the default encoding and UTF-8 mode, after
  installing Pillow 11.3.0 and fixing the tests. 4 are skipped by design: 2 Whisper, 1 needing the client font
  installed, 1 CoreText/Mac-only.

### 5. Failures, bugs, gaps
- **Fixed:** hooks' `python3` path; the guard bypasses (see 976c8a16); `clients_root` being ignored; the Premiere
  bridge hang; `discover.py` backslash paths; `previews.py` file left open; tests without UTF-8; the osascript-only AE/PS
  tests.
- **Still in place:**
  - Hooks fail open when no Python is installed (the safety hook is off on such a machine).
  - The guard does not inspect writes made from inside Python or Node scripts (documented in `guard.py`).
  - `__MACOSX/._*` junk is in the zip (to exclude when packaging).

### 6. Open / deferred / unverified at the end
- **Nothing was tested on a Mac:** the launcher, the guard changes, the bridge timeout and the tests. Suggested:
  `~/.reel-editor/venv/bin/python -m unittest discover -s reel-editor/tests`.
- **The Mac source repo `~/Developer/doma-studio` is behind.** Its `marketplace.json` `"name"` must become
  `thewhynot-ai`, then `./publish.sh`. Until then the README install commands point at a marketplace that doesn't
  exist.
- The user still has to read the LICENSE text.
- The Dr. Nahla Hunter client profile ships inside the plugin. That's fine only while the plugin is private.

### 7. Environment facts
- Windows 11.
  - Real Python is `C:\Python313\python.exe` (3.13.2).
  - `python3` is the MS Store alias. It can be turned off under Settings › Apps › Advanced app settings › App execution
    aliases (untested).
- The desktop app's upload marketplace is `local-desktop-app-uploads`, at
  `C:\Users\LOQ\.claude\plugins\marketplaces\local-desktop-app-uploads\reel-editor\`. The app reads the plugin from
  that folder.
- Plugin cache: `~/.claude/plugins/cache/…`. plugin-dev is at
  `~/.claude/plugins/cache/claude-plugins-official/plugin-dev/b8e53f1c05df` (CLI 2.1.295).
- Project-scope plugin enablement lives in `<folder>/.claude/settings.json`.
- Install alternatives:
  - `/plugin install plugin-dev@claude-plugins-official`
  - the desktop app's **+ › Plugins › Add plugin**
- Node.js is installed. `winget` is available.
- Mac-side install flow at the time:
  ```
  claude plugin marketplace add "/Volumes/DOMA 2.5 SS/claude-plugins"
  claude plugin install reel-editor@thewhynot-ai
  ```

### 8. Ideas floated but not implemented
- **Port the engine to Windows**, called "a big separate project". This was later done as WhyNot Cut 2.x elsewhere.
- Copy skill-finder to `~/.claude/skills/` for all projects (offered).
- Update the README's DOMA drive/folder names if renamed (offered).
- Use the `skill-creator` skill for eval-based testing of the plugin's skills (suggested; the plugin's `evals/`
  needed the Mac environment).

---

## Session a6fcc96f: tiny headless smoke test
**When:** 2026-10-10 21:12, instant.
**Purpose:** a scripted check that plugin-dev skills load.
- **Result:** "Not logged in · Please run /login". The headless CLI has no auth of its own.
- **Environment fact:** CLI-driven smoke tests or evals need the desktop app's session, or a logged-in CLI.

---

## Session 976c8a16: smoke test of plugin-dev, then validator fixes (side session)
**When:** 2026-10-10 21:15 → 21:26.
**Purpose:** confirm plugin-dev loads, then run `plugin-dev:plugin-validator` read-only on Reel Editor.

### 1. User requirements & wishes
- "fix the hooks.json python path back to python3"
- "what is delete the .bak files and it's important or not ?", then "move them outside the plugin folder"
- "fix the other warnings from the validator", then "fix the suggestions from the validator too"

### 2. Complaints / friction
- The test target `claude-plugins/reel-editor` didn't exist, so the validator reviewed the installed copy.
- The user asked to revert to `python3`, but another session had already replaced the hooks with `run_python.sh`.
  Two sessions were editing the same files.
- The user needed a plain explanation of what `.bak` files are. They are a non-developer-friendly concept.

### 3. Decisions (and why)
- **Kept `run_python.sh` instead of plain `python3`.** On this PC `python3` would break the hooks again.
- **Did not hide `adobe-extras` from model invocation.** The user would have to type `/reel-editor:adobe-extras` every
  time, and the AE eval case would break. "Only when asked" is already enforced: the engine and guard block AE/PS
  commands without `--extras`.
- **No examples on helper agents.** They are spawned only by parent agents; examples would invite direct use.
- **Agent colours:** claim-checker red, frame-inspector pink, graphic-checker orange, segment-proofreader blue.
- **Author link switched to https.** The main session later reverted it to http per the user.

### 4. Verified working
- RESULT: PASS. 7 skills, 3 agents and 1 command are present. The plugin-structure skill loaded ("# Plugin Structure
  for Claude Code").
- **A subagent can start another subagent on this Claude Code version.** It was tested, so medical-reviewer,
  motion-designer, qc-reviewer and transcript-editor can fan out to their helpers.
- Bridge fix checked with a fake Premiere.
- Tests pass except 2 PIL tests; PIL wasn't installed yet.

### 5. Failures, bugs, gaps (validator findings)
- **Critical (then):** the hardcoded `C:/Python313/python.exe` path would break on a Mac. Superseded by the launcher.
- **Guard bypasses, fixed in `guard.py` with 13 new tests:**
  - `cp -t data/ file`
  - `ffmpeg -i x data/out.mp4 -loglevel error` (output followed by more options)
  - `find data -delete` and `find assets -exec rm`
  - `find … -delete` from inside the client folder is also blocked (a bit strict)
- **`clients_root` was declared but unused.** Fixed: `reel --root "nahla hunter"` resolves by client name, the session
  hook lists the clients, and a missing `--root` lists them too.
- **A Premiere bridge job hung when its script was missing.** Fixed in `bridge.js`: an immediate error, and the queue
  frees itself after 20 minutes.
- **The `adobe-extras` skill can be auto-triggered.** Ruled acceptable.

### 6. Open
- The bridge fix needs `reel ppro-install` plus a Premiere restart on the Mac.
- Writes from Python or Node scripts are not guarded.

### 7. Environment facts
- Shared side-notes folders live at `C:\Users\LOQ\AppData\Roaming\Claude\side-session-notes\<session>\` and are used
  for hand-overs between sessions.

### 8. Ideas not implemented
- `disable-model-invocation` for adobe-extras (rejected).
- Examples on helper agents (rejected).

---

## Session 41ea4e3c: "Plugin settings enhancement" (origin of the WhyNot Cut name)
**When:** 2026-10-10 21:18:36 → 21:18:55. Interrupted by the user after one line.
**Purpose / request:** `/plugin-dev:plugin-settings` with the arguments: "now run all plugin skill, agency and sub
agents to enhance the plugin in this folder by The Why Not AI and it email info@thewhynot.ai develop it and enhance it
and give it a cool name that related to the why not".

### 1. Requirements & wishes
- Use **all** plugin-dev skills, agents and sub-agents to enhance the plugin.
- Owner: **The Why Not AI**, email **info@thewhynot.ai**. This is a different address from the media@thewhynot.ai used
  in c2d3338a.
- A **cool new name related to "why not"**. This became "WhyNot Cut".

### 2–8.
- Nothing else. The session was interrupted; the work continued in another session (3e1731a4, outside this set).
- **Inconsistency to resolve in the plan:** the owner email is `info@` here but was `media@` in 1.0.6/1.0.7.

---

## Session bfe3f99b: "WhyNot Cut 2.1.1 podcast minors"
**When:** 2026-10-11 07:12 → 08:27.
**Purpose:** fix the 11 deferred Minor findings of the 2.1.0 (podcast mode) review with test-first fixes (RED→GREEN),
then release 2.1.1. Branch `fix/podcast-minors` in worktree `whynot-cut-marketplace-podcast-minors`.

### 1. User requirements & wishes
From the brief, relayed:
- Decide and continue end to end without per-step approval. Merges, pushes and destructive actions stay the user's.
- `assets/` and `data/` are read-only. Never write Adobe security preferences.
- Done means:
  - every item has a test that failed first;
  - the full venv suite is green;
  - 2.1.1 is set in plugin.json, marketplace.json and the CHANGELOG;
  - the zip is rebuilt with `package.py`;
  - the branch is left unmerged.

From the user directly:
- "merge fix/podcast-minors into main"
- "check if you need yes, remove the worktree"

### 2. Complaints / friction
- **Two sessions edited the same engine files.** "Reel editing plugin enhancement" (local_b767610e) had field-test
  fixes G17–G61 in `audio_clean`, `previews`, `ppro_build` and `plan`, which needed coordination by SendMessage before
  any edit.
- `claude plugin validate` couldn't be run because the CLI isn't on PATH.
- The README still says "72 tests" (stale docs).

### 3. Decisions (and why)
- **Separate worktree,** so the shared checkout's branch never moved.
- **Arabic matching in `norm()`:**
  - ئ→ي and ؤ→و;
  - Arabic-Indic and Persian digits → 0–9;
  - after review, ئو→ؤو;
  - so «مسئول»=«مسؤول» and «شئون»=«شؤون».
- **URLs:** bare domains are read whole and checked against known endings. Added `youtu.be`, `linktr.ee`, `goo.gl`,
  `.dev`, `.info` and `.uk`. `file.app.js` is no longer treated as a link.
- **Quotations:** only «…» and "…" are checked as quotes; straight "…" in copy is not. No explicit quote field was
  added, because `publish.json` has none.
- **`pause_params`** labels the source of each value, e.g. "command line (min_pause_ms), recipe drama (pad_ms)".
- **New `publish.frame_at`** seeks to each sample time (4 parallel ffmpeg) instead of decoding the whole episode.
- **Thumbnails:**
  - `highlight` re-draws the word(s) in the brand colour and warns when the word isn't in the text.
  - A new `designs_max` setting (default 3) warns when there are more designs.
- **Footage lookup:** a helper picks the reel's own footage from preflight, also used in the 4:5 block.
  - The 4:5 framing **errors** when the reel's file isn't in preflight. Before, it silently built as 9:16.
  - The trigger is the 4:5 request alone; the peer's "4:5 plus a base scale" condition would never fire on a stale
    preflight.
- **`episode-next`** flags reels picked from an older reels plan. A re-pick clears the flag; `--resync` does not.
- **Inbox probe cache:** `output/discovery/raw-probe-cache.json`, keyed by path, mtime and size. A broken cache is
  rebuilt.
- **Stale-window refusal** extended to `audio-clean`, `previews`, `preview-video`, `ppro-build`, `premiere`,
  `ae-build` and `ps-build`.
- **Reviewer model:** the review ran on the most capable model listed (Fable).
- **Merge:** fast-forward to main `dad3f9d`, plus an annotated `v2.1.1` tag that the user hadn't asked for (they can
  delete it).

### 4. Verified working
- 13 new tests in `test_podcast.py`, each seen failing first; plus 5 assertions for the review fixes and 2 peer tests
  in `test_crossplatform.py`.
- Full venv suite: **212 OK, 4 skipped.** No ResourceWarnings (down from 6).
- Thumbnail candidates on a 10-minute 1080p file: **3.7 s → 1.4 s.**
- Highlight checked by eye on rendered Arabic and English thumbnails.
- `whynot-cut-2.1.1.zip`: 172 files, same file list as 2.1.0, manifest 2.1.1.
- Peer behaviours preserved (as the reel session asked):
  - `audio_clean.verify_cuts`: same-model readings at temperature 0, chunked ≤20 s;
  - `render_captions`: avoid bands, lead_in_ms, strip_punctuation;
  - `ppro_build`: `sharpen_settings` None on all-blur, `content_signature` after the close-save;
  - `plan`: the 4:5 block before `camera.sort`.

### 5. Failures, bugs, gaps (fixed in 2.1.1)
1. `norm()` missed Arabic-Indic digits and ؤ/ئ.
2. A bare `example.co.uk` was truncated to `example.co`, which could let another site pass the "links only from the
   sheet" check.
3. `pause_params` gave the wrong source label.
4. Thumbnail candidates decoded the whole episode.
5. `highlight` was ignored, and designs beyond 3 were dropped silently.
6. The per-shot block used the first preflight file.
7. Straight quotes were verified as quotations.
8. No stale-pick flag in `episode-next`.
9. The inbox re-probed every clip on every call.
10. Stale windows were enforced only in preflight and plan.
11. ResourceWarnings: `preview_video.py` didn't wait for its ffmpeg decoders.

Peer additions in the same release (from the reel session):
- Range reels without `global.main_footage` now get the face-centred reframe and card handling.
- A vertical 9:16 clip with 4:5 framing is now windowed instead of silently built as 9:16.
- `cutaway_bands` caption-avoid bands are sized from the reel's own footage (band 607 px instead of 5400 px).

### 6. Open / deferred / unverified
- Review #7: after transcript corrections, `--resync` doesn't clear the `episode-next` flag; each reel needs a re-pick.
- Review #10: the hygiene test also fails on third-party ResourceWarnings.
- `main.co.ts` still reads as a website.
- **Two Latin words in a row inside an Arabic line can be coloured in swapped places** (highlight). Documented only.
- `transcribe` still treats straight "…" as quotes (kept on purpose).
- The README "72 tests" is stale.
- **Not verified:** `claude plugin validate`; a real 90-minute episode; macOS; the highlight on the CoreText or plain
  fallback font.

### 7. Environment facts
- Repo: `whynot-cut-marketplace/`, a local git repo with **no remote**. Plugin in `whynot-cut/`, engine in
  `engine/reel/lib/`.
- Tests: `~/.whynot-cut/venv/Scripts/python.exe -m unittest discover -s tests`, run from `whynot-cut/`. **System
  Python silently skips the HarfBuzz tests.**
- The zip builder is `package.py`. The zip lands in the `Editing Plugin` folder.
- Skills used from the superpowers plugin 6.4.2: TDD, using-git-worktrees, requesting-code-review.

### 8. Ideas not implemented
- An explicit quote field in `publish.json`.
- `--resync` recording the current plan, so it clears the stale-pick flag.
- Isolating the hygiene test from third-party warnings.

---

## Session cc327f47: reference-folder organisation question
**When:** 2026-10-11 08:08 → 08:40.
**Purpose:** answer the user's question; the session then proposed a task card.

### 1. User requirements & wishes
> «هو في step ان فولدر الريفرينس يتراجع ويتحلل ويتعمل بيها توجهيات للفيديوهات اللي تتعمل مونتاج وان البلاجن دي تنظميه و بترتب كل حاجه ؟»

Translation: "Is there a step where the reference folder gets reviewed and analysed and turned into guidance for the
videos being edited, and does the plugin organise it and arrange everything?"

The wishes behind it:
- Reference edits should drive the style of every video.
- The plugin should organise the material.

### 2. Friction / gaps found [raw]
- Stage 5 exists:
  1. `discover` classifies the files;
  2. `ref-analyze` measures cuts/min, shot length, contact sheets and audio curves (cached per client);
  3. client-researcher interprets them into `reel-profile/` (`style.json`, `notes.md`, `graphics-templates.json`) and
     a per-video `01_analysis/editing-style.json`.
- **Problems found:**
  - **Two of the three promised files are never written.** The docs promise `editing-style-analysis.md`,
    `editing-style.json` and `editing-rules.json`; the engine checks only `editing-style.json`.
  - **The interpretation is re-authored for every video** (R02 and R05 each had their own). That costs tokens and
    risks inconsistent style.
  - **No staleness alert** when a reference is added or changed.
  - **Any loose Markdown under `data/` becomes a reference doc** (`discover.py:50`).
- **"Organises everything?"** Only the **output** is organised. `assets/` and `data/` are read-only (guard hook) and
  are never moved or renamed. Users may expect the plugin to tidy their source files; it won't.
- Field-test style as measured: about 10 cuts/min, no music, hard cuts, hook in a cream box at the top, white captions
  with a gold keyword, end card «الحلقة كاملة على القناة» ("full episode on the channel").

### 3. Decision
- Proposed a separate session, "Client-level reference style guide + staleness check". The user started it (3aaabb4f),
  and it was merged into main `e090994` by the coordinator.

### 4–8.
- See 3aaabb4f.

---

## Session 3aaabb4f: client-level reference style (became part of 2.2.0)
**When:** 2026-10-11 08:13 → 08:37.
**Purpose:** make Stage 5 a client-level artifact: authored once, reused per video, flagged when stale.
Branch `feat/client-ref-style`, worktree `whynot-cut-marketplace-ref-style`.

### 1. Requirements (brief, from the user's question above)
1. A client-level `output/client_database/reference_style/` holding the 3 files plus a fingerprint of the reference
   set. Per video: copy or point to it, with per-video overrides only.
2. `reel next` and the session-start hook report "reference style stale — refresh client style + reel-profile
   style.json/notes.md" when the fingerprint changes, and never ask to re-author when the style is current.
3. The engine's required files match the docs (client-craft, edit SKILL stage table, client-researcher, story-editor,
   story-craft, qc.py).
4. Optional: docs under `data/` without a reference hint become `unclassified` with a warning.

Rules:
- Test-first (TDD).
- Its own worktree; no version bump, zip, Premiere or merge.
- Dry run on a scratch copy; never touch the real client folder `00 TWN/Dr Sherin Helmy`.
- Write scripts with the Write tool, not Bash heredocs (Arabic and escape problems).

Coordinator relay of the user's words: "manage the running chat and make them work together, no stop until they finish
everything and give me the final result".

### 2. Friction
- `main` moved during the work (2.1.1 merged), so a rebase was needed. Only `CHANGELOG.md` conflicted.
- **Overlap with Phase 3 (`feat/ae-motion`)** in `discover.py`, `cli.py`, `qc.py`, hooks and the shared skills.
  The coordinator demanded small local edits so later rebases stay easy.
- **The Egyptian-Arabic summary calls the client «العميلة… دكتورة شيرين» (feminine).** The client is a man (see
  35f79f46): a repeated gender-guess error in user-facing copy.

### 3. Decisions
- **Location:** `output/client_database/reference_style/` holds `editing-style-analysis.md`, `editing-style.json`,
  `editing-rules.json` (mandatory/preferences/optional/conflicts) and `reference-set.json` (the fingerprint: path, size
  and mtime of each reference).
- **New command `reel ref-style`:**
  - `--record` marks the style as authored from the current references;
  - `--apply` copies it into the video, plus `editing-style-overrides.json`;
  - `ref-analyze` auto-applies when the style is current.
- **`reel next`:**
  - first video of a client: "author the style once";
  - later videos: `ref-style --apply` only;
  - when stale: names the changed file.
  - The warning also shows in the session-start hook, `inbox` and `discover`, and in `qc` as a warning only.
- **Guards:**
  - applying a stale style is refused (exit 2);
  - recording without updating the profile's `style.json`/`notes.md` warns;
  - qc-reviewer can't record or apply.
- **Item 4 done:** a loose doc in `data/` without "ref" in its path becomes `unclassified` with a "move it to
  `data/References`" warning.
- CHANGELOG notes under "## Unreleased", later folded into 2.2.0.

### 4. Verified
- **231 OK, 4 skipped** (212 + 19 new tests): fingerprint, staleness, reuse across two videos, overrides, `reel next`,
  the session hook, the guard, and docs-vs-engine checks.
- **Dry run on `whynot-test/_scratch-ref-style/`:** style authored once, reused for R07 and for R08 (with one
  override), flagged stale after touching a reference video in `reel next`, `reel ref-style` and the session-start
  message. Applying a stale style was refused.
- Log: `ref-style-dryrun.log` in the shared notes.
- Fast-forwarded into main at `e090994`.

### 5. Failures / gaps
- The real client's existing projects (R02, R05) still keep per-video style files; they weren't migrated.

### 6. Open
- Dr Sherin's first new video will ask for the client style to be written once. It can be seeded from R02's.
- `whynot-test/_scratch-ref-style` can be deleted (its raw footage is hard-linked).

### 7. Environment
- Bash-tool heredocs mangle Arabic and escapes, so scripts are written with the Write tool.
- Hard links were used to avoid copying GBs of footage.

### 8. Ideas not implemented
- Migrating existing per-video styles into the client-level style automatically, or with a command.

---

## Session 35f79f46: "Whynot cut start" (the first real onboarding with `/whynot-cut:start`)
**When:** 2026-10-11 09:47 → 10:00.
**Purpose:** first-time guided setup on the installed **2.1.1**, then the first real client folder, then podcast mode
on EP02. Handed over mid-way.

### 1. User requirements & wishes (AskUserQuestion answers) [raw]
- **Clients folder:** `D:\WhyNot Clients` (the recommended option; 277 GB free on D:, not synced to OneDrive).
- **Approval:** `ask`, meaning show the plan and preview and wait before building in Premiere.
- **Name:** typed "Yunus".
- **First client:** **Dr Sherin Helmy**. The wizard offered existing folder names it found under `00 TWN`: "Dr Sherif",
  "Dr Sherin Helmy". There is also a misspelled "dr shreif" folder.
- **Copy the test material:** «انسخ اللي اقترحته» ("copy what you suggested"). That meant:
  - 3 fonts, the brand poster, the photo and 2 references;
  - `EP02.mp4` into `data/Episodes`;
  - the tuned `reel-profile/`.
- **Start now?** «ابدأ دلوقتي» ("start now"): transcribe and plan reels right away rather than wait to add the logo
  and colours.
- **Told to a peer session** (relayed): «اعمل انت كل حاجه معاه وخلص كل حاجه، انا عاوز النتيجه النهائية، متسالش تاني»
  ("you do everything and finish everything; I want the final result; don't ask again"). The user delegates both gates
  and wants one owner for the whole run.

### 2. Complaints / friction (onboarding-specific)
- **The wizard was fast, about 3 minutes from `/whynot-cut:start` to an open client folder, but only because the machine
  was already fully set up** by earlier sessions: engine venv, large-v3, CUDA, bridge 3.1.0 and PlayerDebugMode were
  all in place. `reel doctor` returned READY immediately and `reel` was on PATH.
  - **The hard new-user steps were not exercised in this run:** engine install, Python missing, PATH after install,
    the PlayerDebugMode registry change, bridge install while Premiere runs.
- **A bridge downgrade trap in 2.1.1.** The coordinator had to warn: "don't run `reel setup` or `reel ppro-install`".
  - In 2.1.1 `cmd_setup` calls `ppro_bridge.install()` unconditionally whenever Premiere exists. That would put the
    Premiere-only bridge 3.0.0 over the PPRO+AEFT bridge 3.1.0 and break After Effects until a reinstall and restart.
  - Workaround: `reel setup --no-bridge`.
  - Fixed in 2.2.0 with a downgrade guard (`ppro_bridge.install(force=False)`, `ppro-install --force`).
- **Gender guess.** The assistant wrote «الدكتورة» (female "doctor") for Dr Sherin Helmy from the name alone, in the
  file table («صور الدكتورة المعتمدة», "the doctor's approved photos", feminine). That was wrong: the client is a man.
  It corrected itself at the end. 3aaabb4f made the same mistake.
- **Missing brand material found during onboarding:**
  - no logo (`assets/Logo`);
  - no HEX codes (the palette was only measured from the poster);
  - the 3 IBM Plex Sans Arabic fonts were **not installed** on the PC;
  - **no episode sheet** `EP02.md` (guest, host, links, sponsor, topics to avoid). Names and links in the publish
    package come only from that sheet.
  - The wizard can't create these; the user must add them.
- **The client database isn't portable.** When cloning a client from `whynot-test`, 6 files in
  `output/client_database/` hold **absolute paths**:
  - `asset-manifest.json`, `assets/asset-manifest.json`
  - `branding/typography.json`
  - `client-database-status.json`
  - `reference_analysis/cache.json` and `<ref>/measurements.json`

  Only `reel-profile/` was copyable. The rest had to be rebuilt.
- **Wrong folder placement in the test copy:**
  - the full episode sat in `data/Raw`; it was moved to `data/Episodes`;
  - a pre-cut excerpt `EP02_R02.mov` would have been re-edited as a new clip, so it was skipped;
  - a plan document `Reels_Plan_EP02.md` lived in `data/References` and was treated as a style reference.
- **Two sessions on one client folder, no lock.**
  - The onboarding session had launched 3 writing agents: transcript-editor, client-researcher, intake-inspector.
  - The peer session then claimed the run.
  - The onboarding session stopped its agents with TaskStop and killed the orphaned `episode-transcribe` python
    processes. Their messages crossed.
  - Nothing was half-written, but only by luck of timing.
- **Tool noise:**
  - robocopy exit code 1 (success) was reported as an error;
  - `python -I` with the engine venv couldn't import `av`, because the venv was built with
    `--system-site-packages` (later G67).
- A `watch_session.py` process from another session was tailing this session's transcript, so the onboarding was being
  monitored as a field test.

### 3. Decisions (and why)
- **Prefs are written machine-wide** in `C:\Users\LOQ\.claude\whynot-cut.local.md`:
  - editor_name Yunus, language ar, approval ask, whisper_model large-v3
  - clients_root `D:/WhyNot Clients`
  - preview_video true, notify_done true
  - A client folder can override them.
- **Only `reel-profile/` was copied** from the old client database. It was tuned and verified in Premiere:
  - sequence 29.97 (30 + ntsc);
  - captions y 1300, size 52, `box_all`, `lead_in_ms` 200, `strip_punctuation`;
  - card y positions that pass the safe-area QC;
  - sharpen 18 / grain 2;
  - the export name pattern;
  - the client Whisper prompt in `transcription.json`.

  The rest is rebuilt because of the absolute paths.
- `EP02.mp4` (1920x1080, 34.7 min) goes into `data/Episodes`, i.e. podcast mode. It is a host + guest episode.
- **Ownership handover:** the "Reel editing plugin enhancement" session (local_b767610e) owns EP02 from E2 on,
  following the user's "don't ask again". Onboarding stopped its writers.

### 4. Verified working (evidence) [raw]
- `reel doctor` READY:
  - Windows 11 10.0.26300, Python 3.13.2, venv_ok;
  - all modules present (faster_whisper, ctranslate2, av, numpy, PIL, fontTools, arabic_reshaper, bidi, uharfbuzz,
    freetype, pypdf, cv2);
  - whisper large-v3; GPU RTX 4060 Laptop 8 GB, whisper_device cuda;
  - Adobe Premiere Pro, After Effects and Photoshop 2026.
- `reel ppro-status`: alive, bridge 3.1.0, ping OK, Premiere 26.5.2.
- `reel settings --init "~" …` returned `_problems: []`.
- `reel scaffold` CREATED these folders, plus `START_HERE.md`:
  - `assets/Logo`, `assets/Fonts`, `assets/Photos`, `assets/Brand`
  - `data/Raw`, `data/Episodes`, `data/References`, `data/Broll`, `data/Music`, `data/SFX`
- `explorer.exe` opened the folder.
- `reel inbox` saw EP02 (state `new`, `sheet: null`) and reported missing material: logo, brief/HEX. Warnings: no
  music, no SFX library (SFX will be synthesised).
- `reel profile`: active `dr-sherin-helmy` (layers: `config/defaults` + the client's reel-profile).
- `reel episode-prep` wrote:
  - `episode.json`;
  - an intake sheet of 6 frames;
  - an estimate of **2.8 minutes on GPU vs 41.6 on CPU** for large-v3.

### 5. Failures, bugs, gaps
Intake findings that matter for the engine:
- **Multi-camera, 3-person programme,** not the single fixed camera the reels plan assumed: a wide three-shot,
  close-ups of the left and centre seats, and no close-up of the right seat. **Blind auto-reframe is unsafe;** it needs
  a human shot map or per-shot reframe.
- **Full-frame 16:9 graphic cards** at 2:53 and 26:01, inside reels R02 and R04.
  - They must be shown whole or letterboxed, never cropped.
  - They carry a tiny **third-party watermark** ("Noteb…") at the bottom right.
- **29.97 fps vs the plugin's 24 fps preflight standard.** This client requires 29.97.
- **Two audio streams** (AAC 2ch + AC3 2ch, 48 kHz). The extractor must pick one explicitly; mixing both or picking the
  wrong one for Whisper is a risk.
- **A low-bitrate 1080p source** (about 4.3 Mbps). A 9:16 crop is 608x1080, upscaled about 1.78x, so expect soft,
  blocky results.
- **The intake sheet samples only 6 frames, one every 5:47.** The first 2:53 and the last 2:53 were unseen, which is
  exactly where name supers usually sit. No burned subtitles, logo or lower thirds were seen, but that is unproven.
- **Gate approvals don't carry over:** the field-test approvals for R02/R05 don't apply to the real folder, and R02's
  closing statement still needs the content owner's OK.
- **Per-video vocabulary is lost on redo:** R02 had a per-video `00_inputs/vocabulary.txt` (نادال، ديوكوفيتش,
  "Nadal, Djokovic") that must be re-added if R02 is redone.

### 6. Open at the end (needs Yunus)
1. Install the 3 fonts from `D:\WhyNot Clients\Dr Sherin Helmy\assets\Fonts`.
2. Add the logo (transparent PNG or SVG) to `assets/Logo`.
3. Add the HEX colour codes to `assets/Brand`.
4. Write `data/Episodes/EP02.md`: the 3 names and seats (left/centre/right), who is host and who is guest, links, and
   topics to avoid.
5. Decide whether the "Noteb…" watermark on the cards can be published, or supply clean cards.

Also open:
- `brand-roles.json` was not assigned (that agent was stopped).
- R02 = 125.15–179.45 s and R05 = 833.0–886.9 s of EP02, if they are redone for real.

### 7. Environment facts
- Installed plugin: `C:\Users\LOQ\.claude\plugins\cache\thewhynot-ai\whynot-cut\2.1.1\`. `reel` = `…\bin\reel`, on
  PATH only in sessions started after the install.
- Engine home: `C:\Users\LOQ\.whynot-cut`, venv `…\venv\Scripts\python.exe`, built with `--system-site-packages`.
- ffmpeg comes from imageio_ffmpeg in the **user site-packages**:
  `C:\Users\LOQ\AppData\Roaming\Python\Python313\site-packages\imageio_ffmpeg\binaries\ffmpeg-win-x86_64-v7.1.exe`.
  This is a fragile dependency.
- Free space: C: 98 GB, D: 277 GB.
- Wizard rules (from the start SKILL):
  - quit Premiere before installing the bridge (Windows locks the panel folder);
  - run the PlayerDebugMode commands in **PowerShell**, because Git Bash mangles the `/v /d /f` switches;
  - `explorer.exe` needs backslash paths and returns exit code 1 even when it works;
  - avoid OneDrive/iCloud/Dropbox-synced client folders, because online-only files break transcription;
  - about 4 GB is needed for the engine and model;
  - a hook blocks Claude from changing PlayerDebugMode.
- Real client material lives under `D:\0 Work\0 Pegasus IMC Agency\00 TWN\` (Dr Sherif, dr shreif, Dr Sherin Helmy).
  The test copy is `…\Editing Plugin\whynot-test\Dr Sherin Helmy`.

### 8. Ideas floated but not implemented
- **A human shot map / speaker map** for multi-cam episodes (`00_inputs/speakers.json` from the analyst's turns plus
  the intake layout exists; the intake asked for human confirmation).
- **Ask the editor for a clean export** (no burned subtitles/logo) when burned elements are found. This is in the
  podcast SKILL as a manual step only.
- **Pass the 29.97 override** for clients whose plan requires it, instead of the 24 fps preflight standard.
- **Clone a client** without absolute paths (implied by the copy problem). There is no `reel client-clone`/relocate
  command.
- **Single-writer lock per client folder** (implied by the TaskStop collision).

---

## Session 0bba621d: "WhyNot Cut 2.2.1: fix the 2.2.0 deferred minors" (still running)
**When:** 2026-10-11 11:14 → 12:15 in the digest. **[raw]** It was still working at 12:17.
**Purpose:** fix the 2.2.0 (motion mode: audio → After Effects motion video) review's deferred Minors test-first, plus
two Arabic-path bugs found live. Bump to 2.2.1. Branch `fix/motion-minors`, worktree
`whynot-cut-marketplace-motion-minors`.

### 1. Requirements (brief + coordinator, from the user's words)
User relay:
> «خليه يكمل و يخلص كل حاجه لحد ما تقفل النتيجة النهائية وكل حاجه اتصلحت»

("keep going and finish everything until the final result is closed and everything is fixed") **[x-ref e15d7086]**.

User in this chat: "Try again" (after the usage limit) and "keep going until the review is done".

Items:
1. `check_fields` validates `transition_in`, `theme`, `captions` and `reveal`. A typo is an error **naming the scene**,
   not a silent cut or dark theme.
2. Per-scene `captions: "off"` (spec §3.4).
3. A speech-source comparison `verdict` that fails the speech check must not also go through `editorial_text`.
4. `motion_render` on Windows: an open player gives "close <file> and retry", not a raw PermissionError.
5. The QC render check fails with "the render has no audio stream".
6. `audio_sync` diagnostic when a music/SFX bed pulls the correlation under 0.9.
7. `NHM.P.progress`: an LTR bar grows left→right.
8. The `--run-script`/`--script-only` fallback needs a dirty check before `app.newProject()`.
9. No `--replace-edited` backup when the preconditions refuse.
10. Prune old `dialogue_motion_seq_*.wav` files.
11. `guard.py` AE-preferences message wording.
12. Remove the unused `motion_qc.plan_fonts`/`sha1`.
13. Cosmetics: the ternary spaces; `bridge.js` calling `hostId()` twice.
14. `nh_ae_bridge.jsx:17`: replace the raw U+FFFF in the escaper regex with an ASCII escape, and prove it live.
15. README plural for several fallback fonts.
16. **Live: a build from a client folder with an Arabic name.**
17. **(new)** FreeType can't open fonts under non-ANSI paths on Windows.
18. **(new)** aerender gets "???" for non-ASCII paths.

Ruled not bugs: the Task 13 per-word fallback, and the brand-font install (that's the user's job).

Rules:
- No Premiere: the user's real Dr Sherin job was running in it.
- Never close or restart AE or Premiere.
- No merge, push or zip. The coordinator fast-forwards, tags and zips.

### 2. Complaints / friction
- **The session limit hit four times in a row** ("You've hit your session limit · resets 2:50pm (Africa/Cairo)").
  About 20 minutes were lost and the user had to type "Try again".
- **Conflicting peer instructions within seconds:**
  - the coordinator said "do the live AE checks";
  - then "don't use AE, Phase 3 will";
  - then Phase 3 said "you run them yourself";
  - a stale "continue" message arrived after the work was done.
- **One test file for many commits.** The team had to use `git hash-object`/`update-index` staging tricks to keep one
  commit per group.
- Bash heredocs mangled the `\n` escape in the JSX regex; it was fixed by building the backslash with `chr(92)`.
- A **cp1252 console** crashed printing Arabic JSON, so `PYTHONIOENCODING=utf-8` is needed.

### 3. Decisions (and why) [raw / x-ref hand-over]
- **#17:** `hb_text._face` reads the font bytes once (`hb.Blob(data)`, `freetype.Face(io.BytesIO(data))`).
  `find_font_file` reads into memory only for non-ASCII paths (it doesn't load every system font). Pillow already
  copes.
- **#18:** `ae_render.render` on **Windows only** (review fix):
  - when the `.aep` or output path isn't ASCII, it copies the project to an ASCII temp stage
    (`whynot-aerender-*`), renders there, moves the file into place and removes the stage;
  - a non-ASCII TEMP gives a clear FAILED: "set TEMP to an ASCII folder";
  - a finished render that can't be moved is **kept and named** ("kept"), never deleted.
  - macOS renders in place (UTF-8 argv), with no copy of a multi-GB render.
- **#6:** when correlation < 0.9 and the plan has music or SFX, QC correlates the render against the engine's own mix
  of the plan:
  - match → "the voice is in sync, the bed lowers the correlation: lower music.level_db";
  - otherwise → "the voice or bed level in After Effects differs from the plan".
  - Missing planned files are named. The mix is made in a temp dir. **The 0.9 rule stays** (spec ruling).
- **#8:** one shared `NHM.mayDiscard` rule for the bridge and the fallback script, so they can't drift apart.
- **#10 (+ review):** pruning keeps any dialogue WAV named by:
  - the plan;
  - the last job;
  - **any project `.aep` or backup** (AE 26.5 stores footage paths as UTF-8 text, checked on a real project);
  - matched by file name (content hash), so paths from another computer still protect their file.
- **#1:** allowed themes and transitions come from `motion.json`, so a profile can add values.
- **Reviewer:** Fable 5.1, as the most capable model. No Critical, 2 Important, 6 Minor.
- **Release:** CHANGELOG "## 2.2.1 — 2026-10-11 · Motion mode polish, client folders with Arabic names", above 2.2.0.

### 4. Verified working (evidence)
- Every item has a RED→GREEN test in `tests/test_motion.py` (names per item in the hand-over table), e.g.
  `TestMotionTruth.test_field_value_typos`, `TestArabicPaths.*`, `TestAEHostBehaviour.test_bridge_escaper_ascii_under_any_decoding`.
- **Full suite:** 372 tests on `f2d53dc`: 1 failure (the stray-space test), fixed with a `tokenize`-based check. Then
  **372 OK, 4 skipped on `89834af`.** A targeted run of 31 tests after the review fixes was OK. The final full run on
  `920b9ff` was still running at the end.
- **Live in After Effects 26.5x89** from `whynot-test/بودكاست-تجربة` ("podcast-test" in Arabic), reel
  `EP02TEST_R02_MO`:
  - `ae-status`: bridge 3.1.0, host AEFT, debug_mode_ok;
  - `motion-plan` OK;
  - `motion-build --allow-fallback-font`: PROJECT_ASSEMBLED, read-back matches, **64 Arabic text layers through the
    ASCII-only escaper** (proves item 14; the installed JSX is identical to the committed one and has no raw U+FFFF);
  - `motion-render`: RENDERED via the ASCII stage, 1080x1920, 24 fps, 32.333 s, audio stream, **−14.3 LUFS**, stage
    removed;
  - 24 frames viewed (`run-20261011-150553`, and on the final tip `run-20261011-151644`), identical to the earlier
    `run-20261011-143335`;
  - **QC 10/10 PASS** (audio_sync 0.999, offset 0);
  - handoff **READY_FOR_HUMAN_EDITOR**.
  - This closes 2.2.0's "project folder with an Arabic name" gap.

### 5. Failures, bugs, gaps
- **Fixed:** items 1–15, 17, 18. Review fixes:
  - aerender staging is Windows-only;
  - pruning respects `.aep` references;
  - an unmovable render is kept;
  - planned-mix edge cases (missing files, "does not match", temp dir);
  - the `cmd =[` spacing slip.
- **The Arabic-path bugs hit far more than motion.**
  - **#17** breaks any client folder with an Arabic name, including podcast and Premiere graphics through `hb_text`,
    and font folders under a non-ASCII Windows profile name.
  - **#18** also breaks `ae-probe` for a Windows user whose profile name isn't ASCII.

### 6. Open / deferred / unverified (as of 12:17)
- **Not finished:** the final full suite on `920b9ff`, and the report to the coordinator (tip SHA, suite counts, each
  fix with its test, live evidence). Not merged, tagged or zipped; the coordinator will fast-forward main, tag v2.2.1
  and build the zip.
- **Review Minor 4 (left):** after the fallback script refuses an unsaved project, `motion-build --run-script` still
  waits the full `--timeout` (900 s), then reports FAILED with only "no read-back…" as the reason. A clearer, faster
  reason would help.
- **Review Minor 8 (left):** the near-miss test depends on a measured 0.86 correlation from amix/AAC; a future ffmpeg
  could move it.
- **Not verified live:**
  - the LTR progress bar (off in every recipe default; checked only in Node against a fake AE);
  - the fallback script's refusal of an unsaved project (Node only);
  - a Premiere `ppro-build` on bundle 3.1.0;
  - macOS;
  - a build in the client's brand font (the fallback Segoe UI Bold was used).
- **The handoff's "Needs you":** install the IBM Plex Sans Arabic fonts from `assets/Fonts`, restart AE and rebuild;
  add a licensed music track.
- The round-4 gaps G62–G69 from the real EP02 run are **not in this session**. They are in 2d167d3a (another
  reviewer's set): G63 `--adjust` snaps to the nearest word, G64 "did you mean" in evidence errors, G67 venv python
  without `-I`, plus G62/G65/G66/G68/G69.

### 7. Environment facts
- Run the CLI from a worktree as `C:/Users/LOQ/.whynot-cut/venv/Scripts/python.exe -B engine/reel/cli.py …` with
  `PYTHONIOENCODING=utf-8`.
- The suite takes about 6.5 min and is run in the background. Counts by release:

  | Release | Suite |
  |---|---|
  | 2.1.1 | 212 |
  | ref-style | 231 |
  | 2.2.0 | 350 |
  | 2.2.1 | 372 |

- The bridge's ae-scripts folder (`~/.whynot-cut/ae-scripts`) gets the JSX through `ae_bridge.sync_scripts()` on each
  submit, so **no reinstall is needed for JSX changes**.
- **Bridge 3.1.0 is one CEP bundle for Premiere (PPRO) and After Effects (AEFT).** A downgrade guard has existed since
  2.2.0 (`ppro-install --force` to override).
- aerender reads an ANSI command line on Windows. FreeType's file open can't take non-ANSI paths on Windows.
- Live checks must never close or restart Adobe apps, and must not use Premiere while a real client job runs in it.
  One AE driver at a time.

### 8. Ideas floated but not implemented
- **Fall back to the folder's 8.3 short name** when TEMP isn't ASCII. The peer suggested it; the team implemented a
  clear failure instead.
- **Correlate dry dialogue against the render's dialogue stem.** The peer suggested it; the team implemented the
  planned-mix comparison instead.
- A **clearer and faster refusal reason** for `--run-script`.
- A **sturdier near-miss test**.

---

## Cross-session synthesis (for the master plan)

### What the user wants (stable wishes)
- **One plugin any editor can install on Mac or Windows,** guided step by step, then "just drop files in a folder".
- **Arabic-first,** with Egyptian-Arabic conversation.
- **Decide and continue.** "do the best", «خليه يكمل و يخلص كل حاجه…» ("let it continue and finish everything…"),
  «متسالش تاني» ("don't ask again"). Gates may be delegated. Merges, pushes and destructive actions stay the user's.
- **Branding:** The Why Not AI / thewhynot.ai. The name relates to "why not", hence WhyNot Cut.
- **Reference edits must become client-level style guidance** reused by all of that client's videos.
- **Windows parity:** tests and engine must pass on Windows.
- **Final results, not progress reports.** The user asks to be told when a review or session finishes.

### Onboarding / installation friction worth fixing
1. Plugin changes load only in a new session; `/reload-plugins` is user-only. `reel` is on PATH only after a restart.
2. The `claude` CLI isn't on PATH in agent shells, and the headless CLI isn't logged in.
3. Installing from a zip makes in-cache edits fragile. The version must bump or other machines won't update.
4. 2.1.1's `reel setup` downgraded the bridge (fixed in 2.2.0); an "installed > shipped" check is needed everywhere.
5. Missing brand inputs are discovered late: logo, HEX codes, fonts not installed, episode sheet `<EP>.md`. Brand
   fonts not installed force the fallback font in AE.
6. The client database holds absolute paths, so it can't be cloned or moved.
7. No lock on a client folder, so two sessions or writers collide.
8. Folder misplacements: an episode in `data/Raw`, a plan document in `data/References`, a pre-cut excerpt in Raw.
9. Gendered Arabic copy guessed from a name.
10. The real new-user path (engine install, PlayerDebugMode, bridge install) was **never field-tested** in these
    chats; the onboarding ran on an already-configured PC.

### Unverified across releases
- macOS everywhere: hooks launcher, guard, bridge timeout, 2.1.1 highlight on CoreText, 2.2.x.
- A Premiere `ppro-build` on bridge 3.1.0.
- A real 90-minute episode.
- A build in the client's brand font.
- `claude plugin validate` for 2.1.1 (the CLI wasn't on PATH).
