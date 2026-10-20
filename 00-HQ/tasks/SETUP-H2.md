# SETUP-H2 — first session of Helper 2

- **Assigned:** H2 (marketing@)    **Model:** Sonnet 5.5 high    **Size:** S    **Status:** READY
- **Tier:** LIGHT (baseline)

Same as `SETUP-H1.md`, with `h2` everywhere:
- shortcut «WhyNot - Helper 2»;
- worktree `D:\WNC-work\h2`;
- branch `h2/SETUP-H2`;
- author "WhyNot Helper 2";
- queue label `h2-setup`;
- report in `00-HQ\inbox\h2\`.

Extra for the panel side:
1. List the panel tooling under `adobe/panel-ui/` that runs without Premiere (the mock host, the render or
   screenshot scripts) by reading its README / package.json.
2. If it needs Node packages, install them inside your worktree only, with the lockfile:
   `bash C:/Users/LOQ/AppData/Roaming/Claude/side-session-notes/local_263cabbf-75e3-42a1-b384-1753a7bd4dad/heavy.sh job h2-npm -- npm ci` in that folder. Never use a global install.
3. Run one render of an existing screen and report whether it works, with the output path.

## Answer (2026-10-19 20:46)
Master decision on the PARTIAL report: the empty helper engine home was the cause. The suite reads the real runtime
(venv, pinned ffmpeg) READ-ONLY through `plat.engine_home()`, and `tests/_isolation.py` sandboxes every write. So the
launcher no longer overrides `WHYNOT_HOME`; helpers use the same engine home as the executor. Re-run the baseline
with label `h2-setup3` and the card's command unchanged, then write a NEW report with the numbers. If failures
still name missing packages or ffmpeg, list 3 full tracebacks and stop (do not fix).

## Answer (2026-10-20 08:26)
Master decision on the BLOCKED report `inbox\h2\2026-10-20-SETUP-H2.md`:
- **The queue check without `heavy.sh status`.** `heavy.sh status` is denied in both helper profiles on purpose
  (the deny rule `Bash(*side-session-notes*heavy.sh status*)`; a deny beats the allow `Bash(bash *heavy.sh*)`). The
  settings stay as they are. The PLAYBOOK §3d status check is done like this instead (H1 does the same):
  1. `ls D:/ClaudeData/Temp/wnc-locks/wait/` lists the waiting tickets.
  2. `cat` each ticket to read its label.
  3. If any label starts with a prefix from `00-HQ/YIELD.txt` (read it with the Read tool), write a PARTIAL report
     "yielded to the Gate 4 queue" and stop.
  4. Otherwise queue your job with `bash C:/Users/LOQ/AppData/Roaming/Claude/side-session-notes/local_263cabbf-75e3-42a1-b384-1753a7bd4dad/heavy.sh suite|job <label> -- ...`.
     This is allowed: your own BL-16 peer review ran `peer-BL-16*` through it today.
  If even `ls` on that folder is denied, report BLOCKED with the exact denial text.
- **`npm ci` runs in `adobe/`.** That folder is the npm workspace root: `adobe/package.json` has
  `"workspaces": ["panel-ui", "premiere-uxp"]` and holds `package-lock.json`. Use
  `heavy.sh job h2-npm -- npm ci` from `adobe/`. The panel tests exist on release/3.0 in `adobe/panel-ui/test/*.test.ts`.
  If your worktree shows none, fast-forward or branch from the current release/3.0 first.
- Then do the card's steps: the baseline suite (`h2-setup3`), `npm ci`, and one rendered screen. In the report, state
  the account e-mail, the suite numbers and the failure names.
