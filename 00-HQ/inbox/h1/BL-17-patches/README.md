# BL-17 patches (outside H1's fence) — h1 — 2026-10-23 06:05 (Cairo)

Exact source: local commit `f2ff7c6` on branch `h1/BL-17-patched` (in the shared repo, on top of `1c110df` =
`h1/BL-17`). Its diff is these four files together; `git cherry-pick f2ff7c6` onto `h1/BL-17` gives the same result.
The patch files were written from that diff (1, 2, 4 by hand from `git diff`, 3 from git's own header plus the file):
run `git apply --check` on each before using them.

Apply on top of `h1/BL-17` (they need its engine half: `plat.install_options_file` / `install_root_file`), in order:

| # | File | Touches | What |
|---|---|---|---|
| 1 | `1-hooks-session_context-own-pointers.patch` | `whynot-cut/hooks/session_context.py`, `whynot-cut/hooks/README.md` | SessionStart writes this install's `plugin-options.<id>.json` and `plugin-root.<id>.json`, plus the shared `plugin-options.json` / `plugin-root.json` (the last session's, for the installer and earlier releases) |
| 2 | `2-wrappers-bin-reel-own-pointer.patch` | `whynot-cut/bin/reel`, `whynot-cut/bin/reel.cmd` (CRLF in the working tree, LF in git: `.gitattributes`) | Both wrappers work out their install id from their own folder (`<...>/plugins/cache/<marketplace>/<plugin>/<version>` → marketplace, else `inline`; the same rule as `plat.install_id`) and read their own pointer first, then the shared one, then settings.json. Never keyed when `WHYNOT_OPTIONS_FILE` is set |
| 3 | `3-tests-two-installs-AFTER-1-and-2.patch` | new `whynot-cut/tests/test_install_pointers_two.py` | Two cache-layout installs in one temp home: each SessionStart writes only its own pointer; each install's `reel.cmd`, `bin/reel` and `plat` find their own engine home; the upgrade path (only the old shared file) and an own pointer with `engine_home ""`. Fails without 1 and 2, which is why it is not on `h1/BL-17` |
| 4 | `4-skills-platform-setup-two-installs.patch` | `whynot-cut/skills/setup/references/platform-setup.md` | The REL-PREVIEW (2) docs: the `WHYNOT_OPTIONS_FILE` row, and a "Two WhyNot Cut installs on one account" section (own records, the shared files, full isolation with `WHYNOT_OPTIONS_FILE` + `WHYNOT_HOME`, the doctor rule from (1), plugin `bin/` appended to PATH and how to see it and fix it) |

NOT yet run: the suite with 1-4 applied (see the report `../2026-10-23-BL-17.md`).
