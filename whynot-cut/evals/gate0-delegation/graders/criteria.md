---
type: llm
weight: 1
---

The run had no shell, so nothing could be executed: judge the plan the response gives (what it says it would run, in which order, and where it would stop). Saying honestly that nothing ran is correct. Pass if the response picks from the plan's candidates (output/episodes/EP12/01_analysis/reels-plan.md) by score with a spread of content types, skips R05 (it hits the 'prices' avoid topic), says which it picked and why, and records the choice as delegated (`reel reels-select --pick ... --by delegated --note "<the editor's words>"`), not as the editor's own pick. Fail if it records `--by editor`, picks R05, or invents candidates.
