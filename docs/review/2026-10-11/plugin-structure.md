# WhyNot Cut — Claude Code plugin structure review

Reviewer scope: the plugin *as a Claude Code plugin* (manifests, skills, agents, hooks, bin, config, evals, tests, UX,
platform features). Read-only review; nothing in the repos was changed.

**Baseline.** `main` moved three times during the review: 39026fb (2.2.0) → 920b9ff (fix/motion-minors, 2.2.1) →
**cb0539f** (fix/r4-a + fix/r4-b fast-forwarded: G62, G63, G64, G67, G68). All line numbers below are for
**main @ cb0539f** unless a branch is named. Paths are relative to `whynot-cut-marketplace/whynot-cut/` unless they start
with `../` (marketplace root).

Still in flight at the end of the review:

| Branch | Commits (main..branch) | What it changes |
|---|---|---|
| `fix/r4-c` | 574881f G65 (intake scans the whole episode for name supers: new `overlay_scan.py`, `episode.py`), 63d823a G66 (`reel --version`, every error tagged "WhyNot Cut <ver>", new `selfid.py`, `doctor` → `reel_command` PATH scan, start/setup skill text), 3ccaf02 G69 (`media_pending.py`, `ppro_build.py`: re-export "Media pending" frames; qc-craft/qc-reviewer/frame-inspector text) | 26 files, based on old main (14 commits behind) |
| `fix/motion-minors-2` | dbe8f3c, dfc3333, 95a9fca: `--run-script` refuses on unsaved AE project, audio_sync test, **edits the 2.2.1 CHANGELOG section** | 5 files |
| `fix/r4-a`, `fix/r4-b` | merged into main (branches deleted) | — |

Severity: **Critical** = breaks a supported install path / ships something that must not ship / breaks this machine.
**Important** = wrong behaviour or real user-facing risk; fix before the next release. **Minor** = polish, consistency.

---

## 1. Manifests, versions, branding

**1.1 [Important] main contains unreleased fixes under an already-released version.**
Evidence: `.claude-plugin/plugin.json:4` = `2.2.1`, `../.claude-plugin/marketplace.json:10,17` = `2.2.1`,
`CHANGELOG.md:3` top entry = 2.2.1, but main now also contains G62/G63/G64/G67/G68 (cb0539f…a23c8d8) and the
CHANGELOG has no entry for any of them (`grep G6[2-8] CHANGELOG.md` → nothing). `fix/motion-minors-2` rewrites the
2.2.1 section again. Per the plugins reference, `version` pins installs ("Setting it keeps users on that version
until you change it"), so anyone who installed 2.2.1 never receives the round-4 fixes.
Fix: release the next version (2.2.2, or 2.3.0 if r4-c's `reel --version`/doctor changes count as features): bump
`plugin.json`, both marketplace version fields, add a CHANGELOG section listing G62–G69, and freeze the 2.2.1 section.

**1.2 [Minor] Version test is hard-coded and must be edited every release.**
`tests/test_motion.py:2058-2060` asserts the literal `"2.2.1"` three times. Fix: assert
`plugin.json.version == marketplace.metadata.version == marketplace.plugins[0].version == first "## x.y.z" heading
of CHANGELOG.md`. Optionally drop `version` from the marketplace entry (`../.claude-plugin/marketplace.json:17`):
the manifest's version wins anyway ("the manifest's `version` overrides the entry's").

**1.3 [Minor] Bridge content changed without a bridge version bump.**
`git diff 39026fb..HEAD -- templates` shows `templates/premiere/cep_bridge/js/bridge.js` and
`templates/after_effects/nh_ae_bridge.jsx` changed in 2.2.1, but `engine/reel/lib/ppro_bridge.py:22`
`BRIDGE_VERSION = "3.1.0"`, `templates/premiere/cep_bridge/CSXS/manifest.xml:2` `ExtensionBundleVersion="3.1.0"` and
`bridge.js:11` `VERSION = '3.1.0'` were not bumped. The three agree with each other (good), but two different panel
contents now share one version, so the downgrade guard (`ppro_bridge.py:69`) and `reel doctor` can't tell them apart.
Fix: bump to 3.1.1 in all three places whenever anything under `templates/premiere/cep_bridge/` changes, and add a
test that the three strings match.

**1.4 [Minor] No engine version string on main.** `engine/reel/cli.py` has no `--version`; nothing in the engine reads
`plugin.json`. r4-c's `selfid.py` + `ap.add_argument("--version", …)` fixes this; merge it. The CLI help docstring
(`engine/reel/cli.py:1-24`) still lists only the 2.0 commands (no `episodes`, `reels-*`, `publish-*`, `motion-*`,
`ae-*`), so `reel --help` under-describes 61 commands. Fix: regenerate the docstring from the command table.

**1.5 [Minor] Manifest details.**
- `plugin.json:12` `"license": "UNLICENSED"` is not an SPDX identifier (the reference says "SPDX identifier such as
  MIT"). Use `"LicenseRef-Proprietary"` (SPDX-style) and keep `LICENSE`.
- `plugin.json` description is 951 characters; the marketplace entry's 241-char one is the right length. Trim the
  manifest description to ~250 chars (it is shown in `/plugin`).
- No `repository`, `icon`, `documentationUrl`, `supportUrl`, `privacyPolicyUrl`. Only needed for Anthropic's
  directory; note that the plugin can never be installed on claude.ai/Cowork anyway because it has a top-level
  `bin/` ("claude.ai and Cowork don't install a plugin that has a top-level bin/ directory").
- `../.claude-plugin/marketplace.json:6` `owner.url` — run `claude plugin validate --strict ..` (CLI not available on
  this machine, so not run here) to confirm it isn't reported as an unknown field.
- Homepage/branding are consistent (`https://thewhynot.ai/`, `info@thewhynot.ai` in plugin.json, marketplace.json,
  README, LICENSE, help skill). Internal names still carry the first client's initials: `nh_ppro_lib.jsx`,
  `nh_ae_lib.jsx`, `nh_motion_lib.jsx`, `NHPP`/`NHM`/`NH_PERSISTENT`, env `NH_ENV_DIR` (`engine/reel/lib/plat.py:22`). See 10.2.

**1.6 [Minor] userConfig works but is under-used.** `plugin.json:34-46` declares `clients_root` and `engine_home`
(`type: directory`, valid schema). The other machine-wide preferences (`language`, `approval`, `whisper_model`,
`preview_video`, `notify_done`, `editor_name`) live only in `.claude/whynot-cut.local.md`. See 9.2 for adopting
`options` and the `/config` rows; see 4.4 for the bug that stops these two options reaching `reel` on Windows.

---

## 2. Skills (25)

Inventory (lines / description chars): adobe-extras 28/264 · audio-craft* 43/220 · autopilot 57/462 ·
client-craft* 53/265 · edit 150/558 · episode-craft* 64/391 · fix-audio 25/309 · handoff 18/198 · help 38/396 ·
medical-accuracy* 30/346 · motion 72/547 · motion-craft* 52/282 · new-client 31/292 · podcast 112/628 ·
preferences 44/416 · premiere-craft* 31/273 · preview 33/342 · publish-craft* 61/330 · qc-craft* 44/265 ·
revise 39/338 · setup 52/467 · start 118/457 · status 43/252 · story-craft* 51/273 · transcript-craft* 83/233
(\* = `user-invocable: false`, knowledge preloaded by agents). Total description text: **8,804 chars** (2.1.1: 8,257).

Checks that pass for all 25: frontmatter parses with PyYAML; `name` equals the directory; no BOM, no CRLF; every
SKILL.md is under the 500-line guidance (largest: edit, 150); no description is near the 1,536-char cap.

**2.1 [Important] Why `status`, `story-craft` and `transcript-craft` show no description — not a frontmatter bug.**
Their frontmatter is byte-identical in form to the others (verified with `od -c` and PyYAML, 2.1.1 and main).
Cause: the skill-listing character budget. Docs (skills → "Skill descriptions are cut short"): "if you have many
skills, Claude Code drops some descriptions to fit the listing's character budget… The budget scales at 1% of the
model's context window. When the listing overflows, Claude Code drops descriptions starting with the skills you invoke
least." This machine has ~150 skills enabled; the live listing also shows name-only entries for many windsor-ai,
marketing, rampstack-seo and superpowers skills — the same mechanism. `story-craft`/`transcript-craft` are only ever
*preloaded* into agents, never invoked through the Skill tool, so they are structurally "least invoked" and will always
be first to lose descriptions; `status` is simply rarely used. **The same happens in 2.2.x** (same frontmatter, plus
the 547-char `motion` description adds pressure). Users cannot fix it for plugin skills: "Plugin skills are not
affected by `skillOverrides`."
Impact: for the 10 craft skills it is harmless (the main thread shouldn't pick them anyway); for user-facing skills
(`status`, `handoff`, `preferences`, `adobe-extras`, `motion`) a dropped description means natural-language requests
("is it ready?", «خلاص جاهز؟») stop routing to them.
Fix (plugin side):
1. Cut every description to ≤ ~200 chars, key use first, 2–3 trigger phrases (EN + AR) max. Target total ≤ 4,000.
2. Craft skills: one short line, e.g. `"Reference for the transcript-editor agent (preloaded). Not for direct use."`
   (≈80 chars ×10 saves ~2,000 chars). Do **not** set `disable-model-invocation: true` on them: "You can't preload
   skills that set `disable-model-invocation: true`." Preloading by bare name was verified to work on this machine
   (subagent transcripts of `whynot-cut:transcript-editor`, `story-editor`, `client-researcher`, `episode-analyst`
   contain their craft skill's body).
3. Tell users to check `/doctor` (listing cost) and `/skill-doctor`; consider project-scope install (see 8.6).

**2.2 [Important] Trigger overlaps between skills.**
- "remove all pauses" is a trigger in both `skills/fix-audio/SKILL.md:3` and `skills/revise/SKILL.md:3`; "clean the
  noise"/"remove the noise/hum" likewise; `audio-craft:3` also claims "removing pauses". Fix: fix-audio = "audio-only
  request, no other comments"; revise = "two or more comments, or comments about graphics/timing"; craft = agent-only
  line (2.1).
- After Effects: `skills/motion/SKILL.md:3` lists "build it in After Effects" while `skills/adobe-extras/SKILL.md:3`
  claims "make it in After Effects" and says AE is used ONLY on explicit request. Fix: motion = "animated video from
  a podcast window's audio (motion mode)"; adobe-extras = "AE graphics project / MOGRT / PSD for an existing clip
  edit"; remove the bare "build it in After Effects" phrase from motion.
- `edit` vs `autopilot`, `start` vs `setup`, `help` vs `start` are already disambiguated in-text (good).

**2.3 [Important] `revise` has no motion-mode path.** `skills/revise/SKILL.md` routes only to Premiere-pipeline agents
and ends in `ppro-build --force` (line ~38); no mention of `_MO` projects, `motion-director`, `ae-builder`,
`motion-build --replace-edited`. `skills/motion/SKILL.md` has no revision section either (only
`agents/motion-director.md:23` "Revision"). An editor's comment on a motion video triggers `revise` and gets a
Premiere rebuild flow. Fix: add a "Motion projects (`<EP>_<ID>_MO`)" block to revise: route wording/scene changes to
motion-director → `motion-plan` → animatic → Gate 1 → ae-builder `motion-build --replace-edited` (editor OK) →
render/frames → qc-reviewer.

**2.4 [Important] Religious content review is skipped in podcast mode.** `skills/podcast/SKILL.md:87`: "The
medical-reviewer runs only for a medical client (`domain`); religious rules are in story-craft." But
`agents/medical-reviewer.md:3,11` and `skills/medical-accuracy/SKILL.md:3,12` say the reviewer covers religious
content (Quran wording, hadith) for `domain: religious`. The round-2 field test client (R02) was religious. Fix:
podcast line → "The medical-reviewer runs for `domain: medical` and `domain: religious` clients."

**2.5 [Minor] Help / discoverability text is out of step with 2.2.**
- `skills/help/SKILL.md:12-27` cheat-sheet table has no `/whynot-cut:motion` row; motion is appended as
  "## Motion mode (2.2)" (`:35`). Ten skills and five agents end with such "(2.1)/(2.2)" appendices
  (adobe-extras, episode-craft, help, motion-craft, podcast, publish-craft, qc-craft, setup, start, status;
  episode-analyst, frame-inspector, publish-writer, qc-reviewer, setup-doctor). Fix: fold them into the main text;
  version labels mean nothing to a user and grow every release.
- Arabic triggers are missing from `status` (eval `motion-qc-evidence` asks «خلاص الموشن جاهز؟»), `revise`,
  `handoff`, `adobe-extras`. Add one or two each («جاهز؟», «ملاحظات على الفيديو», «سلّم الشغل»).

**2.6 [Minor] `reel` command / flag cross-check.** Every `reel <cmd>` (281 code spans in skills, agents, README,
evals) resolves to one of the 61 registered subcommands (`engine/reel/cli.py:798` list + `lib/podcast_cli.py:10`
+ `lib/motion_cli.py:10` ARGS), and every `--flag` written after a known command exists on that subparser
(checked by introspecting argparse with the engine venv). **One mismatch:**
`skills/setup/references/platform-setup.md:29` "a venv built with `reel setup --system-site-packages`" — `reel setup`
only has `--no-bridge`; the flag belongs to `setup/setup_env.py:53`. Fix: write
`python setup/setup_env.py --system-site-packages`, or add the flag to `reel setup`.

**2.7 [Minor] File references.** All `${CLAUDE_PLUGIN_ROOT}/…` and `references/…` paths exist. Ambiguous relative
paths: `agents/medical-reviewer.md:11` "`references/religious-content.md` of the medical-accuracy skill",
`agents/motion-director.md:30` `skills/motion-craft/references/motion-scenes.md`, `skills/motion/SKILL.md:72`
`motion-craft/references/…`, `skills/setup/SKILL.md:46` `references/platform-setup.md`. Fix: use
`${CLAUDE_PLUGIN_ROOT}/skills/…` (agents, cross-skill) or `${CLAUDE_SKILL_DIR}/references/…` (own skill).

**2.8 [Minor] `start`/`setup` full-path fallback is bash-only.** `skills/start/SKILL.md:25` and
`skills/setup/SKILL.md:10` give `"${CLAUDE_PLUGIN_ROOT}/bin/reel"`; in the PowerShell tool (the primary shell on
Windows when enabled) that extensionless bash script does not run. Fix: give both
`& "${CLAUDE_PLUGIN_ROOT}/bin/reel.cmd" doctor` (PowerShell) and the bash form (r4-c's `selfid.scan_path` already
prints both; mirror it in the skill text).

**2.9 [Minor] `allowed-tools: Bash(reel *), PowerShell(reel *)`** (15 user skills) only covers the invoking turn
("The grant clears on your next message"), and doesn't cover `"${CLAUDE_PLUGIN_ROOT}/bin/reel" …` or subagents. Long
pipelines therefore prompt for `reel` repeatedly. Fix: in `/whynot-cut:start` Step 3, offer to add
`"permissions": {"allow": ["Bash(reel *)", "PowerShell(reel *)"]}` to the clients folder's `.claude/settings.json`
(ask first; plugins can't ship permission rules — plugin `settings.json` only honours `agent`/`subagentStatusLine`).

---

## 3. Agents (19)

Frontmatter (all parse; `name` = file stem; every agent has `name`, `description`, `tools`, `model`, `color`):

| Agent | model | tools | skills preloaded | spawns |
|---|---|---|---|---|
| ae-builder | sonnet | Read, Bash | motion-craft | — |
| audio-engineer | sonnet | Read, Bash | audio-craft | — |
| claim-checker | sonnet | Read, Grep | — | — |
| client-researcher | sonnet | Read, Write, Glob, Grep, Bash | client-craft | — |
| episode-analyst | opus | Read, Write, Edit, Grep, Bash, **Agent** | episode-craft | moment-scout |
| frame-inspector | sonnet | Read | — | — |
| graphic-checker | sonnet | Read | — | — |
| intake-inspector | sonnet | Read, Glob, Grep, Bash | — | — |
| medical-reviewer | opus | Read, Grep, Glob, **Agent** | medical-accuracy | claim-checker |
| moment-scout | sonnet | Read | — | — |
| motion-designer | sonnet | Read, Edit, Bash, **Agent** | motion-craft | graphic-checker |
| motion-director | opus | Read, Write, Edit, Grep, Bash | motion-craft, episode-craft | — |
| premiere-builder | sonnet | Read, Bash | premiere-craft | — |
| publish-writer | opus | Read, Write, Edit, Grep, Bash | publish-craft | — |
| qc-reviewer | opus | Read, Glob, Grep, Bash, **Agent** | qc-craft | frame-inspector |
| segment-proofreader | sonnet | Read | — | — |
| setup-doctor | sonnet | Read, Grep, Glob, Bash | — | — |
| story-editor | opus | Read, Write, Edit, Grep, Bash | story-craft | — |
| transcript-editor | opus | Read, Write, Grep, Bash, **Agent** | transcript-craft | segment-proofreader |

Tool sufficiency: every agent told to run `reel` has Bash; every agent that fans out has Agent; read-only reviewers
have no Write/Edit (and the guard also blocks them, `hooks/guard.py:25-26`). All 19 have a "## When to invoke"
section; 14 have the standard STATUS/FILES/COMMANDS/EVIDENCE/ISSUES report block (the 5 leaf checkers return a
table or JSON — fine).
Every agent is referenced by at least one skill and every agent a skill names exists. Combined agent descriptions:
7,060 chars (well under the 15,000-token warning).

**3.1 [Minor] Invalid colour.** `agents/motion-director.md:6` `color: magenta` — valid values are red, blue, green,
yellow, purple, orange, pink, cyan. Fix: `purple` (story roles) or `pink`.

**3.2 [Minor] motion-designer can't create a file it is told to fix.** `agents/motion-designer.md:4` tools
`Read, Edit, Bash, Agent`; `:25` "Fix problems through … the client profile's `graphics-templates.json`".
`profiles/_template/` has no `graphics-templates.json` (only brand, medical-glossary, notes, profile, style,
transcription), so for every client created with `client-init` the file doesn't exist and Edit can't create it.
Fix: add `Write` to motion-designer, or ship `profiles/_template/graphics-templates.json` (`{}` with comments in notes).

**3.3 [Minor] Un-namespaced subagent names.** `agents/episode-analyst.md:32` "Fan out `moment-scout` agents" and
`skills/transcript-craft/SKILL.md:80` "spawn `segment-proofreader`", while every other place uses
`whynot-cut:<agent>` (`skills/edit/SKILL.md:48`). The Agent tool needs `subagent_type: "whynot-cut:moment-scout"`.
Works today because Claude maps it, but make it explicit.

**3.4 [Minor] Descriptions point at text the router can't see.** All 19 descriptions end with "See \"When to invoke\"
in the agent body." The delegating model only sees the description, never the body. Fix: delete that sentence (saves
~800 chars) and keep the trigger list in the description.

**3.5 [Minor] Fan-out wording doesn't match current Claude Code.** `agents/medical-reviewer.md:24`,
`motion-designer.md:35`, `qc-reviewer.md:36`, `transcript-editor.md:33` say "spawn them all in ONE message with
`run_in_background: false`". In interactive sessions fork mode is on, and "Claude Code also removes the Agent tool's
`run_in_background` parameter". The intent (wait for every result) is right. Fix: "spawn them all in one message and
wait until every one has reported before writing your report". (Evidence that nesting works: 29
`whynot-cut:segment-proofreader` runs at `spawnDepth 2` in this project's subagent metadata.)

**3.6 [Minor] `segment-proofreader.md:9-16` is out of order**: "Return only this table:" (line 10) is followed by the
"## When to invoke" heading (12) and only then the table (16). Move the section above the instruction.

**3.7 [Minor] G67 text duplicated into 13 agents with hard-coded paths.** Each of ae-builder, audio-engineer,
client-researcher, episode-analyst, intake-inspector, motion-designer, motion-director, premiere-builder,
publish-writer, qc-reviewer, setup-doctor, story-editor, transcript-editor now carries the same 5-line block
(e.g. `agents/ae-builder.md:13-16`) naming `%USERPROFILE%\.whynot-cut\venv\…` / `~/.whynot-cut/venv/…` — wrong when
`engine_home`/`WHYNOT_HOME` moves the engine. Fix: add `reel py <script> [args]` (runs a script with the engine venv,
no `-I`) and replace the 13 blocks with one line "Run engine-side Python with `reel py`".

**3.8 [Minor] Unused agent frontmatter that would help.** None of the 19 sets `effort`, `maxTurns` or `omitClaudeMd`.
Suggested: `omitClaudeMd: true` on the 5 leaf checkers (claim-checker, frame-inspector, graphic-checker,
moment-scout, segment-proofreader — they never need the user's CLAUDE.md; v2.1.271+); `maxTurns` (e.g. 15) on leaves
so a stuck checker stops; `effort: high` on qc-reviewer/story-editor/motion-director, `effort: low` on
segment-proofreader. Plugin agents ignore `hooks`, `mcpServers`, `permissionMode`, `initialPrompt` — none are used (good).

### Orchestration graph (main @ cb0539f)

```
Main thread = lead editor (skills run in the main conversation; agents at depth 1, their fan-out at depth 2; limit 3)

/start ──────── setup-doctor · intake-inspector · → /new-client flow · → /autopilot
/setup ──────── setup-doctor
/new-client ─── client-researcher
/fix-audio ──── audio-engineer (· story-editor for global.remove_pauses)
/edit ───────── intake-inspector
                client-researcher (stages 1–2, 5 when client style missing/stale)
                transcript-editor ──▶ segment-proofreader ×N
                audio-engineer (3b)
                story-editor (6–7)
                medical-reviewer ──▶ claim-checker ×N      ∥   motion-designer ──▶ graphic-checker ×N
                [Gate 1: lead + editor]
                premiere-builder (10)
                qc-reviewer ──▶ frame-inspector ×N (12)
                [lead: verify --record, qc, handoff]
/autopilot ──── reads edit/SKILL.md; lead fans out one agent per clip per stage (no extra depth);
                episodes → /podcast up to Gate 0
/podcast ────── reads edit/SKILL.md; intake-inspector ∥ transcript-editor(▶ segment-proofreader)
                episode-analyst ──▶ moment-scout ×N ; [Gate 0] ; per reel → /edit agents ; publish-writer
/motion ─────── reads podcast + edit; audio-engineer ; motion-director ; [Gate 1] ; ae-builder ;
                qc-reviewer ──▶ frame-inspector ×N ; publish-writer
/revise ─────── audio-engineer · story-editor · motion-designer · transcript-editor · medical-reviewer ·
                premiere-builder · qc-reviewer   (no motion-mode route: 2.3)
/status /preview /handoff /preferences /help /adobe-extras ── no agents

Preloaded knowledge (agent `skills:`): audio-engineer←audio-craft · client-researcher←client-craft ·
episode-analyst←episode-craft · medical-reviewer←medical-accuracy · motion-designer←motion-craft ·
motion-director←motion-craft+episode-craft · ae-builder←motion-craft · premiere-builder←premiere-craft ·
publish-writer←publish-craft · qc-reviewer←qc-craft · story-editor←story-craft · transcript-editor←transcript-craft
Guard-enforced roles: subagents can't approve-plan, reels-select, settings --init, verify --record, ae-probe --record;
qc-reviewer can't run 20 build/plan commands; 9 reviewers can't Write/Edit (`hooks/guard.py:25-31, 267-292`).
```

---

## 4. Hooks

`hooks/hooks.json`: PreToolUse (`Bash|PowerShell|Write|Edit|MultiEdit|NotebookEdit`) → `guard.py`; SessionStart
(`startup|resume|clear|compact`) → `session_context.py`; both shell-form `bash "<root>/hooks/run_python.sh" …`,
timeout 10 s. Exit 2 + stderr blocks (correct per hooks reference); invalid input/no Python → exit 0 (fail-open by
design, documented in `guard.py:1-15`).

**4.1 [Important] The guard fires in every project and blocks unrelated work.** A "client folder" is any folder with
both `assets/` and `data/` (`hooks/guard.py:62-74`, `session_context.py:24-25`). That is also the standard layout of
Hugo sites and many web/ML repos. Verified with the guard script: `Write …/HugoSite/data/site.yaml` → exit 2
"the client's source folder (HugoSite/data) is read-only"; `Edit …/HugoSite/assets/main.scss` → exit 2. Because the
plugin is enabled at user scope, this hits every project on the machine, and `session_context` will announce "this is
a client folder". Fix: require a positive marker — e.g. `output/client_database/` or a `.whynot-client` file written
by `reel scaffold`/`client-init`, or the folder being under `clients_root` — before treating a folder as a client.

**4.2 [Important] Guard latency on every tool call (measured on this PC).** `bash run_python.sh guard.py` with a
trivial Bash input: **411 / 441 / 456 ms**; `python -B guard.py` directly: 152–194 ms; the Windows Store `python3`
stub probe alone: **237 ms** (exit 49). `run_python.sh:5` tries `python3` first, so on Windows every
Bash/PowerShell/Write/Edit call pays the stub probe plus two extra Python launches (version check + real run).
SessionStart: 563 ms. Fix: (a) skip candidates whose `command -v` path contains `/WindowsApps/`; (b) on MSYS/MINGW try
`py -3`/`python` first; (c) cache the resolved interpreter in `${CLAUDE_PLUGIN_DATA}/python` and `exec` it
directly; (d) drop the separate version probe (let guard.py check `sys.version_info` itself). Optionally split the
Write/Edit entry with `"if": "Write(**/data/**)"`-style rules so file edits outside sources don't spawn Python.

**4.3 [Important] Windows without Git Bash: guard and session context are silently off.** Hooks reference: shell-form
hooks "run through Git Bash on Windows. If Git Bash isn't installed, they run through PowerShell", and "On Windows
without Git Bash… Claude Code doesn't register the Bash tool at all." Then `bash "C:/…/run_python.sh"` either isn't
found or resolves to WSL's `bash.exe`, which can't see `C:/…` paths → non-zero, non-2 exit → "hook error" notice on
every tool call and no protection. Fix: keep the bash form (works on macOS and Git Bash) but make the failure visible:
have `session_context.py` write a heartbeat (`${CLAUDE_PLUGIN_DATA}/hooks-ok`) and `reel doctor` report
`guard_active: false` + "install Git for Windows" when it is stale; state the Git Bash requirement in README/start.
(Exec form needs a real `.exe`, and Git's `bash.exe` usually isn't on the Windows PATH, so it's not a drop-in fix.)

**4.4 [Important] Plugin options don't reach `reel` correctly (Arabic paths, PowerShell).**
`hooks/session_context.py:98` writes `export WHYNOT_HOME={json.dumps(v)}` to `CLAUDE_ENV_FILE`. `json.dumps` escapes
non-ASCII (`json.dumps('D:/عملاء')` → `"D:/\u0639\u0645…"`), and bash does not decode `\uXXXX` inside double quotes,
so an Arabic `clients_root`/`engine_home` becomes a wrong literal path. Separately, the hooks reference says PowerShell
commands receive `CLAUDE_ENV_FILE` variables only if every line is a plain assignment, and "On Windows, PowerShell
commands also don't receive a variable whose value contains `/` or `\`" — i.e. never a path. `bin/reel.cmd:5-8` then
falls back to `%USERPROFILE%\.whynot-cut`, so on Windows (PowerShell is the primary shell) a user who set
`engine_home` gets "engine not installed" or a second engine. Fix: (1) write values with `shlex.quote()` (single
quotes, UTF-8, `ensure_ascii` irrelevant); (2) for PowerShell, don't rely on the env file: have the engine read the
saved option itself (non-sensitive values are stored under `pluginConfigs` in `~/.claude/settings.json`) or have the
SessionStart hook write a pointer file (`~/.whynot-cut/plugin-options.json` or `${CLAUDE_PLUGIN_DATA}/options.json`)
that `plat.engine_home()` reads.

**4.5 [Important] Guard bypasses that matter on Windows.** Verified with the guard on a scratch client folder:
blocked — `rm data/Raw/a.mp4`, `cd data/Raw && rm a.mp4`, `mv … data/Raw/`, `Remove-Item data\Raw\a.mp4`;
**allowed** — `Get-ChildItem data/Raw | Remove-Item` (idiomatic PowerShell pipeline), `ls data/Raw/*.mp4 | xargs rm`,
`echo $(rm data/Raw/a.mp4)`, `[IO.File]::Delete("data/Raw/a.mp4")`, `git -C data checkout -- .`. Interpreter writes
(`python -c`) are documented as out of scope. Fix: in `check_powershell`, if any pipeline stage is a mutator and any
earlier stage names a protected path, block; treat `xargs <mutator>` as the mutator; re-parse `$( … )`/backtick
bodies; block `[IO.File]::`/`[System.IO.File]::` write/delete/move calls and `git` with a protected `-C`/path when the
subcommand is checkout/reset/clean/rm/mv.

**4.6 [Minor] Session context details.** `session_context.py:49` excludes any clip whose path contains the substring
`ref` (e.g. `data/Raw/Preface.mp4`, `data/Raw/Referral.mp4` are never reported as new). Match a path *segment*
(`/references/`, `/ref/`). The hook runs at every session start in every project (stdlib-only, never fails — good).
Missing: a `CwdChanged` hook (has `CLAUDE_ENV_FILE`) so `cd`-ing into a client folder mid-session gets the same
context; and a first-run nudge (once, flag in `${CLAUDE_PLUGIN_DATA}`) pointing to `/whynot-cut:start`.

**4.7 [Minor] Role detection keys on the bare agent name.** `guard.py:409-411` strips the plugin prefix
(`agent_type.split(":")[-1]`), so another plugin's `qc-reviewer` is also locked down. Compare the full
`whynot-cut:<name>` instead. `MultiEdit` in the matcher is harmless but no longer a Claude Code tool.

**4.8 [Minor] Evidence gate is prose only.** "Never say done unless `qc` passed in this message" lives in 8 skills.
A `Stop` hook of `type: "prompt"` (or `agent`) could check the final message for done/ready claims without a `reel qc`
call in the turn and ask Claude to continue. Optional; keep it cheap (prompt hooks default to 30 s).

---

## 5. `bin/reel` and `bin/reel.cmd`

**5.1 [Critical] `bin/reel` is not executable in git.** `git ls-files -s` → `100644 … whynot-cut/bin/reel` (also
`setup/setup_env.sh`, hooks). Only `../package.py:16` (EXEC set) restores 0755 inside the zip. The README offers "the
zip, a shared drive or a git repo" (`README.md:24`); a git-based marketplace (clone) or a copy from an NTFS share gives
macOS a non-executable `reel` → "Permission denied" for every command (the docs require `chmod +x` for `bin/`
files). Fix: `git update-index --chmod=+x whynot-cut/bin/reel whynot-cut/setup/setup_env.sh whynot-cut/hooks/run_python.sh`
(and the other EXEC entries), and add a test asserting the index mode.

**5.2 [Important] Wrong `reel` first on PATH (G66) — fix exists on `fix/r4-c`, not merged.** Docs: "Plugin `bin/`
directories come after the user's own PATH entries", and a session started before an install/update keeps the old
plugin's `bin/`. On this machine every shell resolves `reel` to
`~/.claude/plugins/cache/thewhynot-ai/whynot-cut/2.1.1/bin/reel`. r4-c (63d823a) adds `reel --version`, tags every
blocked/usage error with "WhyNot Cut <ver>" (`bin/reel` `tag()`, `bin/reel.cmd :blocked`, `cli.py NamedParser`), and a
`doctor` → `reel_command` PATH scan (`selfid.scan_path`). Review notes on it: good design; the `.cmd` path spawns
PowerShell only on the error path (fine); make sure `start`/`setup` check `reel --version` *before* any `reel setup`
(an old plugin's `setup` must never run — r4-c's start text says so). Merge r4-c.

**5.3 [Minor] Wrapper inconsistencies.** `bin/reel:10` falls back to `.reel-editor` and `.dr-nahla-editor`;
`bin/reel.cmd:11` only to `.reel-editor`. `reel.cmd:18` runs `py -3 … || python …`, so a failed `py` setup runs a
second setup with `python`, and there is no 3.9+ check or Store-stub skip (bin/reel has both). Python discovery in
`bin/reel:21` also tries `python3` first (Store stub on Windows; see 4.2). Arabic/space paths: both wrappers quote
`HERE`, `HOME_DIR`, `PY` correctly and set `PYTHONUTF8=1`/`PYTHONIOENCODING=utf-8`; `%*` passes Unicode arguments.
No wrapper is exercised by a test (only existence: `tests/test_crossplatform.py:506`).

**5.4 [Minor] Shared engine home across plugin versions.** `~/.whynot-cut` (venv, models, `ppro-scripts`,
`ae-scripts`, queues) is shared by every installed version. `ppro_bridge.sync_scripts()` (`ppro_bridge.py:33-45`)
overwrites the whitelisted JSX whenever its hash differs, so a 2.1.1 session and a 2.2.x session ping-pong
`nh_ppro_lib.jsx`. Fix: version-stamp the synced scripts and have `ppro-status`/`doctor` warn when the panel, the
synced JSX and the engine disagree.

---

## 6. Evals (14)

Format matches `claude plugin eval` exactly (`evals/<case>/prompt.md` with frontmatter + `graders/criteria.md` with
`type: llm`), so `claude plugin eval whynot-cut` runs them (README.md:219). Each run: fresh empty workspace, only this
plugin loaded, `allowed_tools: [Read, Glob, Grep, Skill]` (every `prompt.md:3`), 6–12 turns, 3 runs × 2 arms. They
need no Bash, so they run on native Windows (shell-granting suites need WSL2).

Coverage: after-effects-on-request, autopilot-new-clips, first-run-onboarding, motion-from-audio,
motion-qc-evidence, onboard-new-client, podcast-reels-plan, premiere-first-default, preview-before-premiere,
protect-client-sources, publish-package, revise-editor-comments, status-before-sending, windows-bridge-not-responding.

**6.1 [Important] They grade descriptions of a plan, not behaviour, and never measure triggering.** With no Bash,
no Agent and an empty workspace, Claude can't find "the Dr. Nahla folder", run `reel`, spawn agents, or touch the
guard; each case has a single `llm` grader on `last_message`. No case has a `tool_used: Skill` grader, so the
listing-budget problem in 2.1 (skills losing descriptions) is invisible to the suite — the docs call a failing
`tool_used: Skill` grader "the most common first finding". Fix per case: add
`graders/skill-fired.md` (`type: tool_used`, `tool: Skill`, `input_match: '"skill"\s*:\s*"(?:whynot-cut:)?podcast"'`);
add a `case.yaml` with `context.scaffold_script` that builds a tiny client folder (assets/, data/Raw, an episode
`.md`), and run with `--scaffold`; add `regex` graders on concrete strings (`reels-select`, `--by editor`).

**6.2 [Important] Missing cases.** No negative/should-not-trigger cases (e.g. "edit the hero image in my Hugo
`assets/`" must not invoke whynot-cut skills and must not be blocked); no Arabic-only prompts for edit/revise/status;
none for fix-audio, handoff, help, preferences (ask vs auto), setup on macOS, new-client reference style (2.2.0
client-level style), transcript words-to-confirm, medical/religious approvals, motion revision, wrong `reel` on PATH
(G66), Gate-0 "you choose" delegation. Also: prompts hard-code the shipped "Dr. Nahla" client (`autopilot-new-clips`,
`podcast-reels-plan`, `motion-from-audio`…) — switch to a neutral fixture client (see 10.1).

**6.3 [Minor] `evals/results/` is not ignored.** `../.gitignore` lacks `evals/results/` and `../package.py` doesn't
skip it, so a local eval run would be committed/zipped. Add both.

---

## 7. Tests

Files on main (test methods): `test_crossplatform.py` 62 · `test_motion.py` 146 · `test_pipeline.py` 25 ·
`test_plugin.py` 23 · `test_podcast.py` 102 · `test_ref_style.py` 19 · `test_round4_brand.py` 29 ·
`test_round4_reels.py` 30 = **436** (README.md:214 still says "72 tests"). r4-c adds `test_round4_intake.py`.

Areas without tests (not run here):
- **Plugin structure** — `test_plugin.py:302-313` only checks `name:`/`description:` substrings and <400 lines. Missing:
  full YAML parse of every SKILL.md/agent, valid `color` values (would catch 3.1), every `skills:` entry exists, every
  `whynot-cut:<agent>` mentioned exists, every `reel <cmd> --flag` in docs exists (would catch 2.6), description
  length budget (would guard 2.1), version consistency (1.2), bridge version triple (1.3), git exec bits (5.1).
- **Wrappers and hook launcher** — `bin/reel`, `bin/reel.cmd`, `hooks/run_python.sh` are never executed by a test.
- **Engine modules with no direct test:** `adobe_run.py`, `mogrt_builder.py`, `ps_builder.py` (the AE/PS extras).
- **Packaging** — only `test_package_rules`; nothing checks the zip's modes.
- **Hooks** — guard tests exist (`test_plugin.py:42-136`, `test_crossplatform.py:137-160, 240-256`) but none for the
  bypasses in 4.5, the Hugo false positive in 4.1, or the env-file encoding in 4.4.
- `examples/make_demo.py:15-18` imports `tests/test_pipeline.py`, so `tests/` must ship with the plugin; fine, but note it.

---

## 8. Discoverability and UX for a brand-new video editor

Strengths: one clear entry point (`/whynot-cut:start`, a wizard that verifies each step), an Arabic quick-start
(`README.md:130-142`), SessionStart context that names the next command inside client folders, plain
Verified / Not verified / Needs you reports, Arabic trigger phrases on 11 skills.

**8.1 [Important] Too many concepts before the first video.** A new editor meets ≈20 concepts: client folder and its
six sub-folders; clients folder; engine/`reel`; engine home; Premiere bridge + PlayerDebugMode; preferences file and
7 keys; client profile vs reel-profile vs shipped profile vs prefix; client reference style (record/apply/overrides);
clip/episode/reel/topic ids and the `_MO` suffix; Gate 0/1/2; stage numbers; editor vs delegated approval; preview vs
final render; words to confirm by ear; medical approvals/domain; content types and recipes; podcast mode; motion mode;
AE/PS extras; handoff — and 15 slash commands. Fix: user-facing text uses three verbs only ("drop files", "say edit
the new videos", "approve the plan") and hides the rest unless asked; rename gates in user text (Gate 0 → "pick the
reels", Gate 1 → "approve the plan", Gate 2 → "proof check"); stage numbers stay internal.

**8.2 [Minor] Stage numbering is confusing.** `skills/edit/SKILL.md:56-68`: 1–2, 3, 4 ∥ 5, **3b runs after 4**, 6–7,
7b ∥ 8, 8b, 9, 10, **no 11**, 12, 13. Renumber 1…12 in execution order.

**8.3 [Minor] "RE" default prefix.** `config/defaults/profile.json:4` and `engine/reel/lib/common.py:381` default the
file-name prefix to `RE` (from "reel-editor"), producing `C0238_RE_EDIT.prproj` for any client without a prefix.
Fix: derive it from the client folder's initials, else `WN`.

**8.4 [Minor] Messages and language.** Engine errors are English JSON (`{"blocked": …, "how": …}`); skills tell Claude
to translate (fine). `start` puts commands on their own lines for RTL safety (good). Missing: an Arabic line in
`/whynot-cut:help`'s table header and Arabic triggers on status/revise/handoff (2.5).

**8.5 [Minor] Motion is the exception to "Premiere only".** `README.md:168` "After Effects / Photoshop commands need
`--extras`" and `skills/edit/SKILL.md:146` say AE is extras-only, while motion mode is AE by design without
`--extras` (`skills/adobe-extras/SKILL.md:20-23`). State the rule once: "Clip edits → Premiere. Motion videos →
After Effects. AE/PS for clip graphics → only on request."

**8.6 [Important] Always-on cost in unrelated projects.** Installed at user scope, the plugin loads 25 skill
descriptions (8.8k chars) + 19 agent descriptions (7.1k chars) into every session, runs SessionStart Python at every
start (≈0.56 s here) and the guard on every Bash/Write/Edit (≈0.4 s here), in every project on the machine (this
agency also does SEO/marketing work in Claude Code). Fix: recommend installing with project scope in the clients
folder (`/plugin install whynot-cut@thewhynot-ai --scope project` from that folder) in README/start, plus 2.1 and 4.2.

---

## 9. Claude Code plugin features to adopt

Sources: code.claude.com/docs/en/plugins-reference (manifest), plugins/components, skills, sub-agents, hooks, mcp,
plugin-evals (fetched 2026-10-11).

| Capability | Used now? | Recommendation |
|---|---|---|
| `.mcp.json` / `mcpServers` | No | Bundle Magnific (9.1) |
| `userConfig` | 2 directory options | Add `language`, `approval`, `whisper_model` with `options` + `default` (picker in `/config`; needs v2.1.271+ for `options`) (9.2) |
| `${user_config.KEY}` in skill/agent content | No | Use for `language` so skills know it without running `reel settings` |
| `${CLAUDE_PLUGIN_DATA}` | No (dir exists empty: `~/.claude/plugins/data/whynot-cut-thewhynot-ai`) | Interpreter cache, hooks heartbeat, welcome-once flag, options pointer (4.2, 4.3, 4.4, 4.6). Keep models in `~/.whynot-cut` (uninstall deletes the data dir) |
| `${CLAUDE_SKILL_DIR}` | No | Own-skill references (2.7) |
| Skill `when_to_use` | No | Optional: split "what" from trigger phrases (same 1,536 cap, no budget gain) |
| Skill `paths` | No | Optional for craft skills (`**/output/projects/**`) to stop auto-activation outside client folders |
| Skill `context: fork` | No | `help` could run forked to keep the main context small |
| Agent `effort`, `maxTurns`, `omitClaudeMd` | No | See 3.8 |
| Agent `background`, `memory`, `isolation` | No | Not needed |
| Plugin `settings.json` (`agent`, `subagentStatusLine`) | No | `subagentStatusLine` to show which stage/agent runs; don't set `agent` at user scope (it would take over every session) |
| Output styles (`output-styles/`) | No | Optional "WhyNot Cut editor" style (RTL-safe command blocks, Verified/Not verified/Needs you); low priority |
| Monitors (`experimental.monitors`) | No | e.g. `when: "on-skill-invoke:podcast"` tail of `episode-transcribe` progress / bridge heartbeat changes; interactive sessions only; can't use `${user_config.*}` |
| Hooks: `if`, `onFailure`, exec form, `shell` | No | `if` to skip Python for writes outside sources (4.2); keep fail-open (no `onFailure: block`) |
| Hook events `CwdChanged`, `Stop`, `SubagentStart` | No | CwdChanged (4.6); Stop prompt-hook evidence gate (4.8) |
| Commands vs skills | Skills only | Correct — "Commands are the older format" |
| `claude plugin eval` | Yes (format ok) | Add `tool_used` graders, scaffolds, mocks (6.1) |
| `claude plugin validate --strict` | README mentions it | Run in CI before each zip (CLI not installed on this PC) |
| `bin/` | Yes | Note: blocks claude.ai/Cowork installs |
| LSP, channels, themes, workflows, `dependencies` | No | Not relevant |

**9.1 Bundling the Magnific MCP (HTTP + OAuth).** Add `whynot-cut/.mcp.json`:
```json
{ "mcpServers": { "magnific": { "type": "http", "url": "https://mcp.magnific.com" } } }
```
(`type` is required — "An entry with a `url` but no `type` is a configuration error"; the URL matches this user's
existing user-scope `magnific` entry in `~/.claude.json`.) OAuth: the user authenticates once in `/mcp`, where it
appears as `plugin:whynot-cut:magnific`; tokens refresh automatically; add `"oauth": {"scopes": "…"}` only if Magnific
needs pinned scopes. Tools are named `mcp__plugin_whynot-cut_magnific__<tool>` — use that in skill `allowed-tools`,
in agent `tools:` (an agent with an explicit `tools` list gets no MCP tools otherwise; plugin agents can't declare
`mcpServers`), and in any hook matcher. Caveats: (a) the user already has a user-scope `magnific` server → two
servers and two OAuth sessions; tell users to remove theirs, or don't bundle and document the user-scope install;
(b) policy: `skills/story-craft/SKILL.md:37` says "Never download or generate footage. No AI likeness", and motion
assets must come from licensed packs (`engine/reel/lib/motion_library.py:1-6`, licences CC0/MIT/ISC/Apache/CC-BY/
commercial-with-proof). Route Magnific output only into a library pack with `pack.json` `license: commercial` +
`proof`, never depicting the client, and update story-craft/motion-craft accordingly; (c) evals can mock it under
`evals/mocks/magnific/<tool>.md`; `claude plugin validate` (v2.1.281+) checks the remote URL.

**9.2 userConfig additions (example).**
```json
"language": {"type": "string", "title": "Language", "description": "Language Claude uses with the editor",
             "options": ["en", "ar"], "default": "ar"},
"approval": {"type": "string", "title": "Plan approval", "description": "ask = wait for your OK before building",
             "options": ["ask", "auto"], "default": "ask"}
```
Keep `.claude/whynot-cut.local.md` for per-client overrides; document precedence.

---

## 10. Other: stale, duplicated, risky

**10.1 [Critical — before any distribution outside The Why Not AI] A real client's profile ships in the product.**
`profiles/dr-nahla-hunter/` (7 files) contains the client's name and credentials (`notes.md:13` "Kasr Al-Ainy Faculty of
Medicine, Professor of Dermatology"), brand colours and font, the editor's standing decisions, and recording details
(`notes.md:25-27` "ch2 = the off-camera interviewer reading the question… Her lips are closed"), plus a first-production
path (`notes.md:3`). `session_context.py:129-135` and the engine auto-apply it to any folder whose name contains
"nahla". Tests (`test_plugin.py:167` `test_merged_nahla_equals_v2_skill_config`) and evals depend on it. Fix: move it
to that client's own `output/client_database/reel-profile/` (or a private profiles pack outside the plugin); ship a
neutral fictional `example-client` profile for tests/evals/demo; remove the folder-name auto-match for shipped
profiles.

**10.2 [Minor] First-client naming in internals.** `nh_*` JSX files and `NHPP`/`NHM` namespaces (1.5). Rename to
`wnc_*`/`WNC` in a major version (bridge whitelist and synced-script names change together).

**10.3 [Minor] THIRD_PARTY_NOTICES.** Lucide (ISC) + Feather (MIT) notices are complete and match
`templates/motion/icons/lucide/LICENSE` (2,114 SVGs, 3.1 MB, vendored by `../tools/vendor_lucide.py` with sha512
check — good). Not mentioned: components `reel setup` downloads (faster-whisper/CTranslate2 MIT, Whisper weights MIT,
PyAV BSD with FFmpeg LGPL, imageio-ffmpeg's FFmpeg binary (GPL build), python-bidi LGPL-3.0, uharfbuzz/HarfBuzz,
freetype-py (FTL/GPL), OpenCV Apache-2.0, pyobjc MIT). They aren't redistributed in the zip, so no notice is strictly
required, but list them under "Installed at setup time" for transparency. Thmanyah Serif Display is referenced by name
only (not shipped) — fine.

**10.4 [Critical — this PC] The installed 2.1.1 can break the 3.1.0 bridge and motion mode.** Installed:
`~/.claude/plugins/cache/thewhynot-ai/whynot-cut/2.1.1` (17 agents, 24 skills, no `motion`, `ae-builder`,
`motion-director`; guard without AE-preference or `ae-probe --record` rules). Its `ppro_bridge.install()`
unconditionally `rmtree`s and copies bridge **3.0.0** (PPRO host only), while this machine's CEP folder has
**3.1.0** (PPRO + AEFT). Every shell here resolves `reel` to 2.1.1, so any `reel setup`/`ppro-install` (the setup
skill's own trigger "after a plugin update") silently removes After Effects support. Fix now: rebuild the zip from
main, refresh the directory marketplace (`~/.whynot-cut/marketplace`), `/plugin marketplace update thewhynot-ai`,
update, restart Claude Code; verify `reel --version` (after r4-c) and `reel ae-status`.

**10.5 [Minor] Marketplace lives inside the engine home.** `~/.claude/plugins/known_marketplaces.json` →
`thewhynot-ai` source `directory C:\Users\LOQ\.whynot-cut\marketplace`. Deleting `~/.whynot-cut` to rebuild the
engine also deletes the marketplace source. Keep the marketplace in its own folder (or a private git repo once 5.1 is
fixed). Stale data dirs from `--plugin-dir` runs: `~/.claude/plugins/data/reel-editor-inline`, `whynot-cut-inline`.

**10.6 [Minor] Template placeholders survive `client-init`.** `profiles/_template/profile.json:13`
`"<folder-name-token>"` and `:16` `"domain": "medical | religious | general"` are copied verbatim; `cli.py
cmd_client_init` only sets `id`/`prefix`. If the researcher doesn't fill `domain`, every domain check sees an invalid
string. Fix: `client-init --domain medical|religious|general` (required) and drop `match` from client copies.

**10.7 [Minor] README drift.** `README.md:214` "72 tests" (436 on main); the "How it works" diagram and the help
cheat sheet omit `/whynot-cut:motion` in places (2.5); `README.md:168` extras rule (8.5).
