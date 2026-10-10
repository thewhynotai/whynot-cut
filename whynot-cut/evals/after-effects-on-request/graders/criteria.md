---
type: llm
weight: 1
---

Pass if the response accepts the explicit request and describes the opt-in extras path (`reel mogrt-build --extras` or the AE build with `--extras`), notes the plan-approval gate for builds, and says success is judged by produced/validated files (not AE's stdout). Fail if it refuses AE outright or ignores the --extras opt-in.
