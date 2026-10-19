# SETUP-H2 — first session of Helper 2

- **Assigned:** H2 (marketing@)    **Model:** Sonnet 5.5 high    **Size:** S    **Status:** IN PROGRESS
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
