# STATUS (edited by the MASTER only)

## Now: 2026-10-23 05:30 Cairo (evidence-checked by the plan chat `local_263cabbf`; **master from 05:40 = `local_a36b6974`**, D-013)
- **Milestone:** M1 = Gate 4 → tag `v3.0.0-p4` (target Tue 27 Oct; about 55%). M0 (AI-infra restart, Phases 0–8)
  closed 05:00 and was re-audited read-only at 05:17: 7 of 10 areas VERIFIED; 3 PARTIAL, all of them stale text, not broken work.
- **Git:** `release/3.0` = `abdece5` = origin (pushed 05:02). Merged since 22 Oct: OPS-09 `b81baaa`, BL-20 `032ff99`,
  S6b `f3995f9`, BL-03 `abdece5`. `ops/hq` = `f2ddaa2` = origin.
- **Seats:** H1 (mayar@) run 9 on BL-17 since 04:52. H2 (marketing@) run 3 on the BL-04 FIX round 1 since 02:32, now in
  its suite. Its worktree is on a detached HEAD at `b7e2190` with 10 changed files, to be checked at its DONE report.
  MAIN (info@) is the master plus the executor (Gate 4 rounds).
- **Automation:** C1 intake hourly :37, C2 reports 09/13/17/21, C3 watchdog, helper keepalive. WNC-Queue (C10) stays
  disabled: its queue is empty and all suites run through heavy.sh, so nothing waits on it.
- **Money:** the $500 API plan is PREPARED / NOT AUTHORIZED (owner word «نفذ خطة الـ API»). Reviews use subscription subagents.
- **Needs Yunus (intake 2026-10-23 06:21):** BL-02 — the GPLv3 §7 NVIDIA permission you approved covers only the NVIDIA
  CUDA/cuDNN libraries inside the PyTorch packages. `reel gpu-enable` also installs cuBLAS 12, loaded in the same
  process. Widen the text to "the NVIDIA CUDA libraries that WhyNot Cut installs or that ship inside the PyTorch
  packages"? (yes/no; the executor's Opus review at the gate either way)
- **Last intake:** 2026-10-23 23:30 (`local_f2ec7e34`): BL-27 (executor fallback, DONE 23:07) ACCEPTED, r1 PASS-WITH-MINORS (3 P3), read-only, nothing to merge. 13 STALE skips (patches landed, tests pass alone) and the NEW religious row `test_bl24_verse_guard.py:83` (motion verse tests are expectedFailure until the BL-24 motion_plan patch lands) are for the executor gate record. Earlier 22:45: BL-27 moved from H2; BL-04 awaiting-peer; H2 topped up (BL-29, S1-SA2).
- **Previous intake:** 2026-10-23 06:21 (`local_acb772ae`). S6b ACCEPTED 03:05 (peer h2; merged since). BL-02 r2 reviewed (master
  Opus + full suite 8830, no new failure) → FIX round 1 (2 P2). BL-20 new report: decided by the master session.
- **Next READY:** S1-R51 (H1 after BL-17), BL-22 (H2 after BL-04), BL-02 (intake: finish the r2 review).
- **Latest Premiere build seen live:** PREVIEW `322d8a5` installed 21 Oct (CEP bridge 3.0.0 / protocol 4, UXP 3.0.0).
  The panel loaded and authenticated in Premiere 26.5.2 4 times; no build or feature call was made. The last full live
  round trip is 14–15 Oct (`docs/adobe/live-roundtrip-2026-10-14.md`). No Gate 4 feature has run live yet
  (`gate4-live-checklist.md` rows A1–C5 are empty).

## History (before 2026-10-23)

- **Last intake (old):** 2026-10-20 16:40 (Cairo). Two DONE reports: BL-03 (H2, 13:46) and BL-02-r2 (H1, 14:09). Both are awaiting-peer: no peer review yet, both under 4 h. The master reviews them itself from 17:46 / 18:09 if no valid peer review lands. Nothing to merge.
- **10:10:** API lane 1 is stopped (owner budget ruling 10:03).
  - BL-16 → H1 (Mayar) and BL-04 → H2 (marketing@), as cards with claims reserved. If not started by 25 Oct, both
    fall back to the executor.
  - BL-14 → executor (handover file).
- **Helpers:**
  - H1 = mayar@thewhynot.ai, H2 = marketing@thewhynot.ai. Both are logged in to the Team org "thewhynot.ai org";
    the profiles were checked.
  - **15:01: AUTO mode is ON for both** (owner-approved; PLAYBOOK §3b). Each one started its SETUP card and queued
    the full suite through heavy.sh.
  - Auto-mode tests: 17/17 PASS with a fake Claude (limit and reset, idle, a BOARD edit during a run, BLOCKED,
    stalled, stale lock, stop, reload).
- **Intake (receiving the helpers' work):** the scheduled task "whynot-cut-hq-intake" runs hourly at :37 and
  follows `roles/MASTER-INTAKE.md`.
  - Fresh Opus review with the full suite.
  - Verdicts go into the cards and the BOARD.
  - Accepted work goes to the executor through `MERGE-QUEUE.md`.

  Test run with nothing new: finished in 24 s and left no lock.

  Two independent reviews of the hand-off found 8 defects, all fixed:
  - a FIX round that repeated;
  - a lost wake-up;
  - a dirty review folder;
  - lock TTL raised to 8 h;
  - only DONE/BLOCKED reports are reviewed;
  - no double review;
  - merged detection for cherry-picks;
  - ACCEPTED requires the full-suite line.
- **15:40, three limits made independent (PLAYBOOK §3c):**
  - Each helper holds 3 independent READY cards: H1 has BL-16, BL-02 and BL-17; H2 has BL-03, BL-04 and BL-18.
    BL-18 came over from the executor's queue.
  - Peer review: each helper's loop reviews the other's DONE code before its next card (Opus, full suite,
    mutants). The master decides from that review, and runs its own review only after 4 h with no peer review,
    or for "Risk: high" cards.
  - When the master is out of limit, the helpers keep building and reviewing. The intake catches up hourly after
    the reset.
  - Third independent review: 9 findings, all fixed, including a permission hole on `git -C`, a report that
    could get stuck in the intake, and a peer-review retry loop.
  - Tests: 21/21 (`D:\ClaudeData\accounts\test_helper_loop.py`).
- **The helpers' loops move to the new code when their current run ends** (watcher script; it never stops a run in
  the middle).
- **Stage:** 1 = Gate 4, ≈ 55%, target 1–3 Nov. No rush (owner).
- **Git:** `release/3.0` is 25 commits ahead of origin. The executor pushes after its batch suite on HEAD. Helpers
  don't push until then (PLAYBOOK §1).
- **Money:** October API plan A running (≈ 230 left, estimate). November plan B (450) starts 1 Nov.
- **Accounts:** master = info@thewhynot.ai (Claude app). H1/H2 profiles are ready
  (`D:\ClaudeData\accounts\h1|h2`) and wait for each helper's own seat and login. API lanes = Console login.

## Reorg (00-HQ)
- **Phase 0 (design):** done.
- **Phase 1 (groundwork):**
  - BOARD and STATUS are written.
  - Lanes 2/4 are on HOLD, so they can't restart on 1 Nov.
  - BL-02 and BL-03 are reserved for the helpers.
  - TRACKS and lane-watch know the new rules.
  - Still open: the push of the 25 commits (the executor's queue) and moving 00-HQ into the repo (at the Gate 4 tag).
- **Phase 2 (helper accounts):**
  - Done: profiles with house rules, deny lists and Sonnet default; worktrees `D:\WNC-work\h1|h2` with their own
    git author; launcher with login guards; desktop shortcuts.
  - Independent review: NOT READY → fixed → re-check passed.
  - Not verified yet: a real double-click with a real helper login (it can't be tested from inside Claude).

## Events
- **19:55, SETUP-H1's first suite hung (no completed run).** It came from the first interactive opening of
  «WhyNot - Helper 1» after the login (~10:52), which sent the kickoff and started the suite. The window was then
  closed, so the suite's processes were orphaned (bash 162156/134128, python 67376/158560, parent gone, 0 CPU).
  - They held both heavy.sh slots for about 4 h 45 min. The plan session released the slots
    (`wnc-locks\stale-h1setup-1052-*.stale`).
  - The processes are harmless (about 30 MB). The sandbox can't end them: Yunus can end them in Task Manager, or
    they go away at the next restart.
  - H1's AUTO run now has a fresh suite running (h1-setup2).
  - **Lesson:** never close a helper's interactive window while a test runs. Use AUTO mode. Interactive mode is
    only for talking to the helper.
- **19:58, owner quality tiers + Karpathy guidelines adopted** (from `Editing Plugin\CLAUDE.md`).
  - Added to the helper profiles, PLAYBOOK §2b, the peer-review prompt (mutants only for HIGH) and the intake
    (HIGH: 2 reviews, PARK after 3 FIX rounds; LIGHT: 1 review, accepted with known limits after 2).
  - Every card names its tier: BL-04 = HIGH, the rest = LIGHT.
- **20:17, helpers yield the heavy queue to Gate 4 (PLAYBOOK §3d, plan session request).**
  - H2's run 3 was stopped; its `h2-setup` / `h2-npm` tickets are withdrawn.
  - `YIELD.txt` and the loop gate are in place (tests 21/21). H2 restarts on the new code at the next keepalive
    and waits while Gate 4 jobs queue.
  - H1's running `h1-setup2` suite is left to finish.
  - Delete `YIELD.txt` at the v3.0.0-p4 tag.
- **20:32, Karpathy guidelines are always on for both helpers (Yunus request).**
  - The full text (identical to upstream, MIT) is appended to both profile CLAUDE.md files and the template.
  - Every AUTO and peer-review prompt now reads `Editing Plugin\CLAUDE.md` first.
  - Both loops were restarted hidden (pythonw); they are now yielding to Gate 4.
  - The plugin was not added: the same text would load twice.
- **20:46, master answer to SETUP-H1's PARTIAL report (563 errors/failures): the cause was the launcher.**
  - The launcher pointed `WHYNOT_HOME` at an EMPTY helper home. The suite reads the real runtime (venv, pinned
    ffmpeg) read-only, and `tests/_isolation.py` sandboxes every write.
  - The launcher no longer overrides it (backup: `Start-Helper.cmd.bak-20261019`).
  - `## Answer` added to both SETUP cards: re-run as `<h>-setup3`.
  - Loops restarted; they are yielding to Gate 4. H2 had no report yet: two runs ended on network errors
    (ENOTFOUND), and one was stopped for the yield.

## Risks
1. The Mac has never run anything real. Plan: a 1-hour Mac smoke right after Gate 4.
2. One PC for everyone: RAM is the brake (32 GB, peaks 94%). Every heavy job goes through `heavy.sh`.
3. H14 (Anthropic OK for panel chat on the editor's own login) is open. It matters only outside the agency.
4. Helper deny lists are guardrails, not a hard fence (Bash could still write anywhere). Helpers approve prompts
   with care.
5. (2026-10-20 08:27 intake) The engine venv on this PC (`~/.whynot-cut/venv`) runs imageio-ffmpeg 4.2.2 instead of the pinned
   ffmpeg, and Python 3.13 while the locks pin 3.12. Every full suite here (master and helpers) carries ~77
   environmental failures (test_media_normalise, test_t26_conform_wiring, the fuzz imports, bidi…). These could hide
   a real media regression. Owner: ENV-01 (see `reviews/SETUP-H1-r3.md`). Small cards are still to be written for
   the 2 darwin-only t45 tests on Windows and the fuzz modules' import-time crash.
6. (2026-10-21 03:45 intake) Intake lock loop: the BL-02 master review was lost 3 runs in a row (21:39, 02:38, 03:38).
   The Agent tool launches the reviewer async; the run then ended its turn while the reviewer waited on its
   queued suite, so the session went idle (`isRunning: false`) and the NEXT run judged the lock stale and ran
   `end-tag`, killing that review's suites. Fix in this run: the run keeps polling in the foreground until the
   reviewer returns. MASTER-INTAKE §1B should say so explicitly (owner of the procedure: master).
