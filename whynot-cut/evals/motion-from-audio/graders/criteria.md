---
type: llm
weight: 1
---

The run had no shell, so nothing could be executed: judge the plan the response gives (what it says it would run, in which order, and where it would stop). Saying honestly that nothing ran is correct. Pass if the response follows the motion playbook: it records the pick as the editor's choice (`reels-select --pick R03 --as motion --by editor`, since the editor named R03), cleans the audio, has the motion-director write the motion script from the transcript, compiles it with `reel motion-plan`, renders the animatic, and then STOPS asking the editor to approve the plan, with editorial lines marked as not the speaker's words and numbers to confirm. Fail if it approves the plan itself, builds in After Effects before approval, invents quotes, numbers or names, or changes Adobe preferences.
