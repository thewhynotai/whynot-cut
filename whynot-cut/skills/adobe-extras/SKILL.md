---
name: adobe-extras
description: "This skill should be used ONLY when the editor explicitly asks for After Effects or Photoshop output — \"make it in After Effects\", \"build MOGRTs\", \"make a Photoshop cover/thumbnail PSD\". The default pipeline is Premiere-only; never use this on your own initiative."
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
