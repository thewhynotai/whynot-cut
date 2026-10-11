---
type: llm
weight: 1
---

Pass if the response follows the podcast playbook: it finds the episode with `reel episodes`/`reel inbox` (not by guessing), runs `episode-prep`, the intake check and `episode-transcribe`, has the episode-analyst (with moment-scouts) author topics/speakers/reels-plan and runs `reel reels-plan` until it compiles, renders candidate previews, and then STOPS at Gate 0 with a table of candidates (id, score, content type, timecodes, hook, flags) asking the editor which to make. Fail if it runs `reels-select` itself without the editor's choice, starts building reels before the editor picks, invents quotes or timecodes, or treats the episode as one clip to edit.
