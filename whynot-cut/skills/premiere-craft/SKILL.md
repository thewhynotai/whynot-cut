---
name: premiere-craft
description: "Reference for the premiere-builder agent (preloaded). Not for direct use."
user-invocable: false
---

# Premiere craft

```bash
reel ppro-status --root "<CLIENT>"                        # alive + ping. If not alive: Premiere running? restarted since install?
reel ppro-probe  --root "<CLIENT>"                        # what the bridge's host reports back (version, project, API); for diagnosis
reel serve status                                         # the engine the Premiere panel talks to (session start runs it; `reel serve ensure` starts it)
reel status      --root "<CLIENT>" --video-id <ID>        # the project's status record (status, history, blockers, parked_previous)
reel ppro-build  --root "<CLIENT>" --video-id <ID> [--force]   # needs the CURRENT plan approved (Gate 1)
reel premiere    --root "<CLIENT>" --video-id <ID>        # fallback standalone XML when the bridge can't run
```
- `--force` closes the open project in Premiere and keeps the previous file as `*_prev_<time>.prproj`. Make sure the editor
  has no unsaved work in it, and ask if unsure. Never delete the backups.
- **Success** means status `PRPROJ_BUILT` and every check in `07_premiere/ppro-build-result.json` is true:
  - the project was saved this run
  - codec ProRes 422 LT, 1080×1920, 24 fps
  - linear colour ON, max bit depth OFF, max render quality OFF
  - all graphics placed
  - dialogue on A1/A2

  `PRPROJ_BUILT_WITH_ISSUES` is not success. Report exactly which checks failed.
- The sequence settings are the editor's house spec (`config/defaults/sequence-settings.json`). Don't change them.
- `EDITOR_CHANGES_PRESENT` means the editor saved changes in Premiere after the last build. Stop and report it to the lead.
  `--replace-edited` is only for when the editor explicitly agrees that their manual edits won't carry over.
- Nothing built is never exit 0: `EXISTS` (the project is already there; `--force` rebuilds) and
  `EDITOR_CHANGES_PRESENT` / `PREVIOUS_PARKED` are refusals (exit 2, with `how`); `MISSING_GRAPHICS` is a failure
  (exit 1, `ok: false`).
- If `ppro-build` returns `MISSING_GRAPHICS`, run previews. If it returns `BRIDGE_NOT_RUNNING`, the editor must start Premiere.
  Don't try to start or quit Premiere yourself unless the editor asked. It may hold their unsaved work.

Full details, verified API facts and animation presets: `${CLAUDE_SKILL_DIR}/references/premiere-assembly.md`.
Known failures: `${CLAUDE_PLUGIN_ROOT}/skills/edit/references/troubleshooting.md`.
