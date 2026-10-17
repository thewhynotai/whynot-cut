# SPDX-License-Identifier: GPL-3.0-or-later
# © 2026 The Why Not AI (thewhynot.ai)
"""Doctor safety and QC (Phase 4 Tasks 61–68, Addendum K1): checks that produce findings for people to decide on.

Nothing here approves medical or religious content. Every check explains itself in plain editor words, Arabic first.
The surfaces that today's Gate 4 runs exercise (the `reel plan` block, the `reel qc` hard fail, the hook check inside
`plan`/`reels-plan`, the builder fades) stay behind their own switch in config/defaults/safety.json (switches.py), off
until the Gate 4 tag; while off, today's output is byte-identical."""
