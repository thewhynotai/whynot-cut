# SETUP-H1 — first session of Helper 1

- **Assigned:** H1    **Model:** Sonnet 5.5 high    **Size:** S    **Status:** ACCEPTED
- **Tier:** LIGHT (baseline)

## Before this card (the helper's human, once)
1. Double-click «WhyNot - Helper 1». The first time, the window opens Claude **without** a task.
2. Type `/login` and choose the Claude account (subscription) option, not Console.
3. When the browser opens, **copy the link into a private window** (Chrome Incognito, Ctrl+Shift+N; or Edge
   InPrivate). The normal browser is signed in as Yunus, and authorizing there would log this profile into
   Yunus's account. Sign in there with **your own** e-mail, approve, and paste the code back into the window if
   it asks for one.
4. Type `/exit`, then double-click the shortcut again. The launcher checks the login. It refuses if the profile
   shows Yunus's account (info@thewhynot.ai), and otherwise sends the kickoff line.

## Goal
Prove three things: this profile is yours, your worktree is clean, and the suite is green from your worktree when
run through the shared job queue.

## Steps
1. Interactive: `/status` shows **your** e-mail and the organization **thewhynot.ai org** (the Team), not a
   personal or Pro account. AUTO mode: skip this step; the launcher already checked the e-mail and the
   organization in the profile before starting. If either is wrong, stop and tell your human (fix: `/logout`, then `/login` and pick the Team
   organization).
2. In `D:\WNC-work\h1`:
   1. Check that `git status` is clean.
   2. Run `git switch -c h1/SETUP-H1 release/3.0`.
   3. Check that `git var GIT_AUTHOR_IDENT` contains "WhyNot Helper 1" (every `git config` command is blocked for helpers).
3. Run the full suite **through the queue** (never directly). From the worktree root:
   `bash C:/Users/LOQ/AppData/Roaming/Claude/side-session-notes/local_263cabbf-75e3-42a1-b384-1753a7bd4dad/heavy.sh suite h1-setup -- env PYTHONDONTWRITEBYTECODE=1 PYTHONUTF8=1 ~/.whynot-cut/venv/Scripts/python.exe -B -m unittest discover -s whynot-cut/tests`
   - Use that literal queue path (the allow list matches it). The engine home is the real one (read-only for tests: `tests/_isolation.py` sandboxes every write).
   - Expect waiting time plus up to about an hour of run time.
4. Write `00-HQ\inbox\h1\<date>-SETUP-H1.md` from `templates/UPDATE-REPORT.md`. Include the numbers (OK, skipped,
   failed) and the names of any failures.
5. Don't fix failures in this task: list them. There is nothing to push.
   - If failures name the engine home (missing models, missing pointers), say so. The master then decides whether
     `WHYNOT_HOME` isolation needs a seeded home. Never point it at the real `~/.whynot-cut` yourself.

## Acceptance
- [ ] `/status` shows your own account
- [ ] suite numbers reported
- [ ] worktree clean at the end; the claims folder and 00-HQ were the only places written outside it

## Answer (2026-10-19 20:46)
Master decision on the PARTIAL report: the empty helper engine home was the cause. The suite reads the real runtime
(venv, pinned ffmpeg) READ-ONLY through `plat.engine_home()`, and `tests/_isolation.py` sandboxes every write. So the
launcher no longer overrides `WHYNOT_HOME`; helpers use the same engine home as the executor. Re-run the baseline
with label `h1-setup3` and the card's command unchanged, then write a NEW report with the numbers. If failures
still name missing packages or ffmpeg, list 3 full tracebacks and stop (do not fix).

## Answer (2026-10-20 02:49)
Master (Command Center) decision on the BLOCKED report r2: the cause is the environment, not the code, and it is fixed
(card ENV-01). The engine packages existed only in Claude's sandboxed AppData, so your unsandboxed suite had no
numpy/PIL/av/imageio-ffmpeg. They are now installed inside the engine venv itself (same 47 pinned versions); the 4
modules your tracebacks named pass 104/104 from the real environment. Re-run the baseline with label `h1-setup4` and the
card's command unchanged, then write a NEW report with the numbers. Any remaining failure is now a real one: list it.


## Intake decision (2026-10-20 08:26)
ACCEPTED on report r3 (`inbox\h1\2026-10-20-SETUP-H1-r3.md`, review `reviews\SETUP-H1-r3.md`). The baseline is
8226 run / 27 F / 24 E / 87 skipped, all environmental, load-timing or already fixed on release/3.0. The ENV-01 gaps
(pinned ffmpeg not used, venv on Python 3.13) are routed to ENV-01 and the executor. You do not need to re-run
h1-setup5 for this card. ENV-01 will ask for a re-run when its fix lands. Next time, write the account e-mail in
SETUP reports.
