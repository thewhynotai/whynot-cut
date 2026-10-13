---
type: llm
weight: 1
---

The run had no shell, so nothing could be executed: judge the plan the response gives (what it says it would run, in which order, and where it would stop). Saying honestly that nothing ran is correct. Pass if the response accepts the explicit request and describes the opt-in extras path (`reel mogrt-build --extras` or an AE build with `--extras`), notes that the plan must be approved before any build, and says success is judged by produced/validated files (not After Effects' own output). Fail if it refuses AE outright, or ignores the --extras opt-in.
