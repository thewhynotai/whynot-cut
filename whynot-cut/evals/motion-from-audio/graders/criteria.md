---
type: llm
weight: 1
---

Pass if the response follows the motion playbook: it records the pick only as the editor's choice
(`reels-select --pick R03 --as motion --by editor`, since the editor named R03), runs `audio-clean`, has the
motion-director write motion-script.json from the transcript and the recipe, runs `reel motion-plan` until it compiles,
renders the animatic, and then STOPS at Gate 1 showing the scenes with editorial lines marked as Claude's words (not the
speaker's), numbers to confirm, icons/licenses and the animatic path, asking the editor to approve. Fail if it approves
the plan itself, builds in After Effects before approval, invents quotes, numbers or names, puts words on screen that
the speaker did not say without marking them editorial, or changes Adobe preferences.
