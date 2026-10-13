---
type: llm
weight: 1
---

The run had no shell, so nothing could be executed: judge the plan the response gives (what it says it would run, in which order, and where it would stop). Saying honestly that nothing ran is correct. Pass if the response follows the podcast playbook: it finds the episode with `reel episodes`/`reel inbox` (not by guessing), prepares and transcribes the episode, has the episode-analyst author the reels plan and compiles it with `reel reels-plan`, renders candidate previews, and then STOPS asking the editor to pick the reels from a table (id, score, content type, timecodes, hook, flags). Fail if it runs `reels-select` itself without the editor's choice, starts building reels before the editor picks, invents quotes or timecodes, or treats the episode as one clip.
