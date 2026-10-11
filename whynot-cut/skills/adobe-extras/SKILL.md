---
name: adobe-extras
description: "After Effects or Photoshop output for a clip edit, only when explicitly asked: \"make it in After Effects\", \"build MOGRTs\", \"Photoshop cover PSD\", «اعملها في أفتر إفكتس». Never unprompted."
argument-hint: "[ae|ps|mogrt] [clip id]"
---

# After Effects / Photoshop extras (opt-in)

The editor works in Premiere, so these tools are extras. The engine and a hook both block `reel ae-*`, `ps-*` and
`mogrt-build` unless you pass `--extras`. Pass it only when the editor asked for AE or PS **in this conversation**.

| Request | Commands | Output |
|---|---|---|
| Editable AE graphics project | `reel ae-script --extras`, then `reel ae-build --extras` (approval gate), then `reel ae-render --extras` | `04_after_effects/project/<ID>_<PREFIX>_GFX.aep` plus ProRes 4444 alpha renders |
| MOGRT templates for Premiere | `reel mogrt-build --extras` | `.mogrt` files (validated zips) |
| Cover / thumbnail PSD | `global.photoshop_jobs` in decisions, then `reel ps-build --extras` | layered PSD + preview PNG |

- Works on macOS (AppleScript) and Windows (`AfterFX.exe -r`, Photoshop COM). Judge success by the files produced and
  their timestamps, never by the return value (AE's DoScript always prints `0`; on Windows the launcher returns at once).
- View every render or PSD preview: RTL order, joined Arabic, no white box around the logo.
- If AE or PS isn't installed, deliver the JSX (SCRIPT_ONLY) and say so.

References: `references/adobe-automation.md`, `references/automation-matrix.md`.

## Motion mode (2.2)
Motion videos (`/whynot-cut:motion`, picked `--as motion` at Gate 0) are built in After Effects by design: their
commands (`ae-status`, `ae-probe`, `motion-*`) are not extras and need no `--extras`. The `ae-*`/`ps-*`/`mogrt-build`
graphics extras for clips keep their opt-in rule.
