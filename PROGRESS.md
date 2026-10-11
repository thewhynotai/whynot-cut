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
| 1 Ship-blockers | | | |
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
| T0.2 | done | — | — | marketplace dir refreshed from `whynot-cut-2.2.1.zip`; `claude plugin update` 2.1.1→2.2.1; `reel --version` = 2.2.1 (installed cache); `ae-status` bridge 3.1.0 alive. Backup of the old marketplace dir in the executor scratchpad. Yunus must open a **new session** for skills/`bin` to switch |

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

## Gap log (G70+)

| ID | Symptom | Root cause | Fix |
|---|---|---|---|

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
| H10 | Standard Windows user "WN Test" | pending | Windows Sandbox if available, else documented gap |
