# WhyNot Cut 3.0 — executor checkpoint

Plan: `docs/superpowers/specs/2026-10-11-whynot-cut-3.0-master-plan.md` (evidence: `docs/review/2026-10-11/`).
Branch: `release/3.0` (from `main` = `v2.2.1` = `4831de5`). One commit per task; tag `v3.0.0-p<N>` per passed gate.
Executor session: "WhyNot Cut 3.0 executor" (started by local_263cabbf). Resume rule: trust this file + `git log`,
never redo a task marked done here.

## Baseline (2026-10-11)

| Item | Value |
|---|---|
| Code | `v2.2.1` = `4831de5` (main, only branch, no worktrees) |
| Unit suite (engine venv, `tools/test.sh`) | **483 OK / 4 skipped, 368 s** on release/3.0 @ 6edf4d0 |
| `claude plugin validate --strict` (CLI 2.1.295, bundled) | marketplace ✔ passed · plugin ✔ passed |
| Installed plugin on this PC | 2.1.1 → **2.2.1** (T0.2) · CEP bridge 3.1.0 kept (`reel ae-status` alive, bridge 3.1.0) |
| Tools | Claude Code CLI 2.1.295 (`tools/find_claude.py`), Node v26.7.0, Git 2.56 |
| Hosts | Premiere 26.5.2, After Effects 26.5 (Windows 11, RTX 4060) |

## Phase table

| Phase | State | Tag | Verified / Not verified / Needs you |
|---|---|---|---|
| 0 Baseline, one folder | **passed** | v3.0.0-p0 | Verified: suite 483/4s, validate --strict ✔ ×2, installed 2.2.1 + bridge 3.1.0, one folder, PROGRESS. Needs you: open a new Claude session so 2.2.1 skills load |
| 1 Ship-blockers | **passed** | v3.0.0-p1 | Verified: suite 725 OK/4s (424 s); validate --strict ×2; compileall; node --check; independent phase review (1 Critical found → fixed, re-reviewed clean); live smoke on PODCAST-TEST + Arabic 2-clip fixture (ids, raw-stem rewrite, plan/previews/preview-video, guard Hugo vs client, writer lease); guard 116–155 ms. Verified later the same day: T1.6 fresh headless session with the 3.0 plugin (`claude -p --plugin-dir`, installed 2.2.1 disabled) lists all 25 whynot-cut skills WITH descriptions, incl. status/story-craft/transcript-craft (evidence `docs/superpowers/evidence/2026-10-11-t1.6-fresh-session-skill-listing.txt`). Not verified: SessionEnd/`/clear` session-id live check (Phase 3). Needs you: — |
| 2 Engine robustness | | | |
| 3 Plugin layer | | | |
| 4 Editor features | | | |
| 5 Magnific | | | |
| 6 Native Adobe | | | |
| 7 Installer | | | |
| 8 Structure review | | | |
| 9 Full QA | | | |
| 10 Arabic PDF | | | |
| 11 Release | | | |

## Tasks

| Task | State | Commit | Tests | Note |
|---|---|---|---|---|
| T0.1 | done (integrator) | 4831de5 | 483 OK / 4 skipped | v2.2.1 tagged, r4-c merged, worktrees removed |
| T0.3 | done | 6edf4d0 | — | renamed to WhyNotCut; old zips, `_source`, round4-gaps.md, WhyNot-Cut-3.0-Plan → `_archive/`; plan/evidence/brand copied in |
| T0.4 | done | 6edf4d0 | 483 OK | PROGRESS.md, tools/find_claude.py, tools/test.{sh,ps1}, .gitignore dist/ + evals/results/ |
| T1.1 | done | 12770ea (+ef52c10) | 495 | real client profile → `_private-profiles/`; fictional example-clinic; package.py refuses other profiles |
| T1.2 | done | 485e2fb | 497 | exec bits 100755 in git + zip EXEC test |
| T1.3 | done | 04ef340, 966afae | 530 | `lib/clip_ids.py`, `output/discovery/clip-ids.json`; raw-stem/case ids rewritten to the inbox id; 2.x folders adopted |
| T1.4 | done | bf21ece | 523 | fingerprint = whole spec minus `generated`/`*_at`; old approvals re-approve once |
| T1.5 | done | 2c46004, d17b477, 4a91941, 7d193fa (+phase-1 gate fixes) | 645 | positive client marker, bypasses, role holes, visible runner, heartbeat; 3 fix rounds |
| T1.6 | done | 5f45372 | 560 | descriptions 8,804 → 3,2xx chars (≤ 4,000 test) |
| T1.7 | done | bde5c55, 7073391 | 614 | people[] + gender/honorific checks in plan/publish-check; lead-skill rule |
| T1.8 | done | cb01d93, 09d698c | 651 | session lease `output/.whynot-lock`, `reel lock`, SessionEnd hook |
| T1.9 | done | 167ed3e, 86199cc | 703 | shlex env file, `~/.whynot-cut/plugin-options.json`, %-safe reel.cmd, no-Python hint |
| T1.10 | done | 40ab8b7 | 603 | 3.0.0 everywhere, version/bridge-triple tests, `--help` from the command table |
| Phase-1 minors + gate fixes | done | d868090…54d4f79 | 725 | review minors; G70, G74–G77 fixed |
| T0.2 | done | — | — | marketplace dir refreshed from `whynot-cut-2.2.1.zip`; `claude plugin update` 2.1.1→2.2.1; `reel --version` = 2.2.1 (installed cache); `ae-status` bridge 3.1.0 alive. Backup of the old marketplace dir in the executor scratchpad. Yunus must open a **new session** for skills/`bin` to switch |

- Integrator handover (local_74c8d6b7, 2026-10-11): role ended at v2.2.1; G69 ppro-frames 17/17 and AE qc 10/10 verified live on 2.2.1; still unverified: macOS, ppro-build on bridge 3.1.x, 60–90 min episode, speaker-follow two-shot, motion in brand font, motion music, G68 limits (unboxed captions/decorative bars not contrast-checked). Dr Sherin EP02 run stays PAUSED (Yunus).

## Decisions (Ruling: what — why — cost if wrong)

- Ruling: evidence files are read per phase, right before the phase that cites them (engine + plugin-structure read
  at start) — keeps the executor context small across 12 phases — a missed cross-reference costs a re-read.
- Ruling: phases are executed with one plan file per phase in `docs/superpowers/plans/` and small same-shape tasks
  batched into one implementer dispatch (SDD "batch small same-shape work") — the plan has ~100 tasks — cost: coarser
  per-task review granularity.
- Ruling: T0.2 done without waiting for an explicit OK — Yunus waived approval stops (decide-and-continue) and the
  update is reversible (backup kept) — cost: none expected.

- Ruling: Gate 0 independent code review skipped — Phase 0 changed only docs/dev tooling (no product code) — cost: none.
- Ruling: per-phase plans written up front for Phases 1–6 while waiting on the suite — saves wall-clock — cost: a plan may need edits when earlier phases change code.

- Ruling (T1.1/T1.9): the legacy engine-home names `.reel-editor` / `.dr-nahla-editor` stay readable in 3.0 (wrappers, plat, run_python.sh, bridge.js) and are dropped in 4.0 (CHANGELOG Migration) — a machine with only a legacy home would otherwise lose its engine on update — cost: the token `.dr-nahla-editor` remains in code; T1.1's grep acceptance is read as "no client DATA ships".
- Ruling (T1.5): the guard defends against accidental destructive commands by Claude/agents, not a deliberately adversarial local process; exotic forms (arrays, string building, functions, interpreters) are documented limits — cost: a creative destructive command can still slip through.
- Ruling (T1.8): the client lock is a session lease (holder CLAUDE_PID, refreshed per writing command, stale on dead holder/pid reuse or 2 h idle, released by `reel lock --release` or SessionEnd) — the field failure was sessions taking turns for hours — cost: an idle session blocks others up to 2 h unless the editor releases.
- Ruling (Phase 1 execution): implementers ran in parallel only on disjoint file sets (master plan §6.1), each committing only its own hunks — cost: occasional concurrent-suite noise, no lost work observed.

- Ruling: H11 deferred to Phase 3 T3.7 — Yunus didn't follow the CLI-login step and asked Claude to do it; a sign-in needs his own browser approval, so at T3.7 the executor will open the login ready in the Terminal panel and ask for just the one click; until then work continues without headless checks — cost: T1.6 listing proof and evals wait until then.

- Ruling (speed, Yunus approved "اعمل كده"): three parallel side sessions on disjoint folders — Adobe track [wnc-adobe, local_f9018851] (Phase 6: contract v4, panel-ui, premiere-uxp spike/scaffold), installer track [wnc-installer, local_61a829a1] (Phase 7: installer core/front ends, components.json, Git Bash, uninstall), guide track [wnc-guide, local_c357b152] (Phase 10: guide-ar pipeline + stable chapters); the executor keeps Phase 2→ and owns PROGRESS, gates, tags, engine/hooks/skills; status notes in the shared notes folder STATUS-*.md — cost: higher usage burn; gates for 6/7/10 still run in order after their dependencies.

- Fact (2026-10-11): Yunus connected the "Adobe for creativity" connector (account type `auth`). It is cloud-only (Express, Firefly, Acrobat, Adobe Fonts, Stock) — it does NOT drive the local Premiere/AE timeline, so it doesn't replace the UXP/CEP work. Uses planned: Adobe Fonts activation of IBM Plex Sans Arabic (unblocks the brand-font motion build — needs Yunus's OK because it adds fonts to his CC account); Acrobat `pdf_to_image`/`pdf_properties` as a second QC path for the Arabic guide (Phase 10).

## Gap log (G70+)

| ID | Symptom | Root cause | Fix |
|---|---|---|---|
| G70 | `reel doctor --fix` writes `.whynot-client` into EVERY client under clients_root (incl. the real `D:\WhyNot Clients` folder) | T1.5 marker repair scoped to all clients | fixed 3819817 (`doctor --fix` scoped; `--all-clients` lists, `--yes` writes) |
| G71 | `reel plan` ok:true without `global.main_footage` (non-range clip); previews/preview-video crash with TypeError | plan falls back to source_range footage = None | Phase 2 T2.2 (validate required fields before use) |
| G72 | Arabic graphic text renders as tofu in a tiny bitmap font when the client has no Arabic font; no warning | previews.py falls back to `ImageFont.load_default()` | Phase 2 T2.10 (system Arabic fallback + plan/previews warning) |
| G74 | A `#` comment in a multi-line command disabled every guard rule after it (Bash shlex commenters; PowerShell comments/apostrophes) — pre-existing since 2.x | guard joined lines with " ; " and lexed with `#` comments | fixed b2698fe + 54d4f79 |
| G75 | SessionStart heartbeat warning could never fire | run_python.sh touches hooks-ok right before session_context checks it | fixed b2698fe, 54d4f79 |
| G76 | `doctor --fix --root X` blocked by another session's lease, no report | doctor --fix classed as writer | fixed c6c585b |
| G77 | Parallel same-session writers collide on write_json's fixed .tmp name (clip-ids.json from reader commands) | fixed temp name | fixed c6c585b (unique temp + replace retry); T2.4 completes locking |
| G73 | previews contact sheet half empty / count mismatch | contact-sheet layout vs stills count | Phase 2 T2.17 (media_util sheet builder) |

## Needs you (H1–H10)

Asked once at the start (Egyptian Arabic, 2026-10-11 ~15:50).

| ID | Item | Status | Default if not done |
|---|---|---|---|
| H1 | Magnific `/mcp` → Authenticate | pending | Phase 5 ships with mocks; live test Not verified |
| H2 | Move `profiles/dr-nahla-hunter` to `_private-profiles` | default applies | move (copy kept) |
| H3 | Hosting `dl.thewhynot.ai` or public GitHub releases | pending | zip + installer scripts from the extracted zip |
| H4 | Apple Developer + Windows OV certificates | pending | one-liners only |
| H5 | Adobe Developer Distribution plugin ID | pending | development ID |
| H6 | A Mac (Apple Silicon) or private GitHub for macOS CI | pending | "macOS not verified live" |
| H7 | Close/reopen Premiere + AE on request; CC signed in; other unsigned panels? | pending | live Adobe checks wait |
| H8 | Dark logo variant approval | pending | white logo on dark only |
| H9 | 60–90 min episode test copy | pending | EP02 (35 min) |
| H11 | Bundled Claude Code CLI login | **done 2026-10-11** (`claude auth status`: loggedIn, claude.ai team, info@thewhynot.ai) | — |
| H10 | Standard Windows user "WN Test" | pending | Windows Sandbox if available, else documented gap |
