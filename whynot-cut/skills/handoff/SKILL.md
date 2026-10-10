---
name: handoff
description: "This skill should be used when preparing the editor handoff for a finished or paused edit — \"write the handoff\", \"package it for the editor\", \"I'm moving to another device\", \"summarise what's left\"."
argument-hint: "[clip id]"
allowed-tools: Bash(reel *), PowerShell(reel *)
---

# Handoff

1. `reel qc` (this message), then `reel handoff`. This writes `09_handoff/README.md` and `final-editor-checklist.md`.
2. Update the client folder's `HANDOFF.md` (create it if missing) so the work can continue on another device. Include:
   - what was done, with dates
   - where everything is (paths relative to the client folder)
   - how to resume on another Mac or PC: install WhyNot Cut from the marketplace (`/plugin marketplace add <marketplace>`,
     `/plugin install whynot-cut@thewhynot-ai`), run `/whynot-cut:start`, then `/whynot-cut:status`
   - the open items ("Needs you"), with evidence
   - known caveats
3. Never describe something as done unless it's verified (see `/whynot-cut:status`). Keep "Not verified" honest.
