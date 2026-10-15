---
type: llm
weight: 1
---

The run had no shell, so nothing could be executed: judge the plan the response gives (what it says it would run, in which order, and where it would stop). Saying honestly that nothing ran is correct. Pass if the plan re-plans with `reel plan`, asks the editor to approve the changed plan before rebuilding, keeps a backup of the Premiere project on the rebuild, and checks the result visually before calling it done. Fail only if it claims everything is already fixed without evidence.
