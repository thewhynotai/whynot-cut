---
type: llm
weight: 1
---

The run had no shell, so nothing could be executed: judge the plan the response gives (what it says it would run, in which order, and where it would stop). Saying honestly that nothing ran is correct. Pass if the response is a cheat sheet in the help skill's shape: it starts from where the editor is right now (on this fresh machine that means pointing to /whynot-cut:start first, or saying it would check `reel doctor` / `reel board` / `reel next`), gives the three steps (drop files, say what you want, approve the plan), names /whynot-cut:edit (one clip) or /whynot-cut:autopilot (every new clip) as the way to edit, and may add a table of the other commands. Fail if it uses internal jargon like 'Gate 1' or stage numbers, or names a /whynot-cut command that is not one of: start, help, edit, autopilot, podcast, motion, preview, revise, status, fix-audio, new-client, handoff, preferences, setup, adobe-extras.
